"""Tests for paper_trading.core.risk_manager — all 6 risk gates."""

from __future__ import annotations

import pytest
from datetime import datetime, date, timezone, timedelta

from paper_trading.core.risk_manager import RiskManager
from paper_trading.core.order_manager import OrderRequest, Side


def _make_order(**overrides) -> OrderRequest:
    """Create a valid OrderRequest with sensible defaults."""
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


class TestRiskManager:
    def setup_method(self):
        self.rm = RiskManager(initial_capital=10_000.0)

    # ── Gate 1: Daily loss ────────────────────────────────────────

    def test_approved_normal_order(self):
        order = _make_order()
        ok, reason = self.rm.check_order(order, open_position_count=0, current_balance=10_000)
        assert ok is True
        assert reason == "APPROVED"

    def test_rejected_daily_loss_limit(self):
        # Simulate large losses
        self.rm.record_trade_result(-350.0)  # > 3% of 10k
        order = _make_order()
        ok, reason = self.rm.check_order(order, open_position_count=0, current_balance=9_650)
        assert ok is False
        assert "Daily loss limit" in reason

    # ── Gate 2: Daily trade count ─────────────────────────────────

    def test_rejected_daily_trade_count(self):
        for _ in range(10):
            self.rm.record_trade_result(10.0)
        order = _make_order()
        ok, reason = self.rm.check_order(order, open_position_count=0, current_balance=10_000)
        assert ok is False
        assert "trade limit" in reason.lower()

    # ── Gate 3: Open positions ────────────────────────────────────

    def test_rejected_max_open_positions(self):
        order = _make_order()
        ok, reason = self.rm.check_order(order, open_position_count=2, current_balance=10_000)
        assert ok is False
        assert "open positions" in reason.lower()

    # ── Gate 4: Confidence ────────────────────────────────────────

    def test_rejected_low_confidence(self):
        order = _make_order(confidence="LOW")
        ok, reason = self.rm.check_order(order, open_position_count=0, current_balance=10_000)
        assert ok is False
        assert "Confidence" in reason

    # ── Gate 5: SL/TP validation ──────────────────────────────────

    def test_rejected_missing_sl(self):
        order = _make_order(stop_loss=None)
        ok, reason = self.rm.check_order(order, open_position_count=0, current_balance=10_000)
        assert ok is False
        assert "stop loss" in reason.lower()

    def test_rejected_invalid_long_sl(self):
        """Long SL above entry price."""
        order = _make_order(side=Side.LONG, requested_price=4100, stop_loss=4200)
        ok, reason = self.rm.check_order(order, open_position_count=0, current_balance=10_000)
        assert ok is False
        assert "Invalid LONG SL" in reason

    def test_rejected_invalid_short_sl(self):
        """Short SL below entry price."""
        order = _make_order(side=Side.SHORT, requested_price=4100, stop_loss=4000, take_profit=4080)
        ok, reason = self.rm.check_order(order, open_position_count=0, current_balance=10_000)
        assert ok is False
        assert "Invalid SHORT SL" in reason

    # ── Gate 6: R:R ratio ─────────────────────────────────────────

    def test_rejected_low_rr(self):
        """R:R of 1:1 should be rejected (min is 1:2)."""
        order = _make_order(
            requested_price=4100, stop_loss=4090, take_profit=4110,
        )
        ok, reason = self.rm.check_order(order, open_position_count=0, current_balance=10_000)
        assert ok is False
        assert "R:R too low" in reason

    def test_rr_tolerance_epsilon(self):
        """R:R of 1.99 should pass due to epsilon tolerance."""
        order = _make_order(
            requested_price=4100.00, stop_loss=4090.00, take_profit=4119.90,
        )
        ok, reason = self.rm.check_order(order, open_position_count=0, current_balance=10_000)
        assert ok is True

    # ── Day rollover ──────────────────────────────────────────────

    def test_replay_day_rollover(self):
        """Passing different timestamps resets daily counters."""
        ts_day1 = datetime(2026, 6, 23, 10, 0, 0, tzinfo=timezone.utc)
        ts_day2 = datetime(2026, 6, 24, 10, 0, 0, tzinfo=timezone.utc)

        # Exhaust daily trades on day 1
        for _ in range(10):
            self.rm.record_trade_result(10.0, timestamp=ts_day1)

        order = _make_order(signal_time=ts_day1)

        # Should be rejected on day 1
        ok1, _ = self.rm.check_order(order, 0, 10_000, timestamp=ts_day1)
        assert ok1 is False

        # Should pass on day 2 (counters reset)
        ok2, _ = self.rm.check_order(order, 0, 10_000, timestamp=ts_day2)
        assert ok2 is True
