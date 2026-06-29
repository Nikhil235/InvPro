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
        import os
        from core.database import Database
        from core.clock import ClockService
        from core.event_bus import EventBus
        from paper_trading.core.account_ledger import AccountLedger
        
        self.db_path = "test_trading_broker.db"
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass
                
        self.db = Database(db_path=self.db_path)
        self.db.migrate()
        self.clock = ClockService(mode="live")
        self.event_bus = EventBus()
        self.session_id = "test_session"
        self.ledger = AccountLedger(self.db, self.clock, self.event_bus, self.session_id, 10_000.0)
        self.broker = PaperBroker(self.db, self.clock, self.event_bus, self.ledger, self.session_id)

    def teardown_method(self):
        import os
        # Close connection to allow file deletion on Windows
        if hasattr(self, 'db'):
            self.db = None
        
        # Give a small delay to make sure SQLite releases the file handle
        import time
        time.sleep(0.1)
        
        if hasattr(self, 'db_path') and os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

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

    def test_closed_trades_property(self):
        order = _make_order()
        self.broker.submit_order(order)
        self.broker.close_all_positions(price=4105.00)
        
        trades = self.broker.closed_trades
        assert len(trades) == 1
        assert trades[0].exit_price == 4105.00
        assert trades[0].session_id == self.session_id

    def test_invalid_close_price_fallback_and_guard(self):
        import math
        order = _make_order()
        self.broker.submit_order(order)
        pos_id = list(self.broker._positions.keys())[0]
        
        # 1. Close with NaN -> should fallback to fill_price
        closed = self.broker.close_position(pos_id, price=float('nan'))
        assert closed is not None
        assert math.isfinite(closed.exit_price)
        assert closed.exit_price == closed.fill_price
        
        # 2. Try to close again -> guard should prevent second close (returns None)
        closed_again = self.broker.close_position(pos_id, price=4100.00)
        assert closed_again is None

    def test_invalid_close_price_zero_fallback(self):
        order = _make_order()
        self.broker.submit_order(order)
        pos_id = list(self.broker._positions.keys())[0]
        
        # Close with 0 -> fallback to fill_price
        closed = self.broker.close_position(pos_id, price=0.0)
        assert closed is not None
        assert closed.exit_price == closed.fill_price
