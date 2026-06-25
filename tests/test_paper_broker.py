"""Tests for paper_trading.core.paper_broker — order fills, SL/TP, equity."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from paper_trading.core.paper_broker import PaperBroker
from paper_trading.core.order_manager import OrderRequest, Side, ExitReason


def _make_order(**overrides) -> OrderRequest:
    defaults = {
        "side": Side.LONG,
        "requested_price": 4100.00,
        "stop_loss": 4090.00,
        "take_profit": 4120.00,
        "lots": 0.1,
        "confidence": "HIGH",
        "bias": "Bullish",
        "risk_amount": 100.0,
        "signal_time": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return OrderRequest(**defaults)


class TestPaperBroker:
    def setup_method(self):
        self.broker = PaperBroker(initial_capital=10_000.0)

    # ── Order fill ────────────────────────────────────────────────

    def test_fill_returns_filled_status(self):
        order = _make_order()
        fill = self.broker.submit_order(order)
        assert fill.status.value == "FILLED"
        assert fill.fill_price > 0

    def test_fill_price_includes_spread_for_long(self):
        order = _make_order(side=Side.LONG)
        fill = self.broker.submit_order(order)
        # Long fills at ask (above requested price)
        assert fill.fill_price >= order.requested_price

    def test_fill_price_includes_spread_for_short(self):
        order = _make_order(side=Side.SHORT, stop_loss=4110, take_profit=4080)
        fill = self.broker.submit_order(order)
        # Short fills at bid (below requested price)
        assert fill.fill_price <= order.requested_price

    def test_position_created_after_fill(self):
        order = _make_order()
        self.broker.submit_order(order)
        assert self.broker.open_position_count == 1

    # ── SL/TP triggers ────────────────────────────────────────────

    def test_sl_hit_long(self):
        order = _make_order(side=Side.LONG, stop_loss=4090.00)
        self.broker.submit_order(order)
        closed = self.broker.tick(4089.00)  # below SL
        assert len(closed) == 1
        assert closed[0].exit_reason == ExitReason.SL_HIT
        assert closed[0].net_pnl < 0

    def test_tp_hit_long(self):
        order = _make_order(side=Side.LONG, take_profit=4120.00)
        self.broker.submit_order(order)
        closed = self.broker.tick(4121.00)  # above TP
        assert len(closed) == 1
        assert closed[0].exit_reason == ExitReason.TP_HIT

    def test_sl_hit_short(self):
        order = _make_order(
            side=Side.SHORT, requested_price=4100,
            stop_loss=4110, take_profit=4080,
        )
        self.broker.submit_order(order)
        closed = self.broker.tick(4111.00)  # above SL for short
        assert len(closed) == 1
        assert closed[0].exit_reason == ExitReason.SL_HIT

    def test_no_trigger_in_range(self):
        order = _make_order(stop_loss=4090, take_profit=4120)
        self.broker.submit_order(order)
        closed = self.broker.tick(4105.00)  # between SL and TP
        assert len(closed) == 0

    # ── Equity ────────────────────────────────────────────────────

    def test_equity_includes_unrealised_pnl(self):
        order = _make_order(side=Side.LONG)
        self.broker.submit_order(order)
        # Price goes up
        self.broker.tick(4110.00)
        # Equity should be above initial balance
        assert self.broker.equity > 9_900  # allowing for commission

    def test_close_all_positions(self):
        order1 = _make_order()
        order2 = _make_order()
        self.broker.submit_order(order1)
        self.broker.submit_order(order2)
        assert self.broker.open_position_count == 2
        closed = self.broker.close_all_positions(price=4105.00)
        assert len(closed) == 2
        assert self.broker.open_position_count == 0
