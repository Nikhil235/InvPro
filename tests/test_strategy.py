"""Tests for core.strategy — bias detection, confirmation, ATR, signals."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
from typing import Dict, Any

from core.strategy import TradingStrategy, ATRApproximator, StrategySignal


# ── ATRApproximator ───────────────────────────────────────────────────

class TestATRApproximator:
    def test_not_ready_initially(self):
        atr = ATRApproximator(period=3, window_size=5)
        assert atr.ready is False
        assert atr.atr is None

    def test_ready_after_enough_windows(self):
        atr = ATRApproximator(period=3, window_size=5)
        # Feed 2 windows of 5 ticks each (need >=2 ranges)
        prices = [100, 101, 99, 102, 98,  # window 1: range=4
                  100, 103, 97, 101, 99]   # window 2: range=6
        for p in prices:
            atr.update(p)
        assert atr.ready is True
        assert atr.atr == pytest.approx(5.0, abs=0.01)  # mean(4, 6) = 5.0
        assert atr.data_points == 2

    def test_data_points_count(self):
        atr = ATRApproximator(period=14, window_size=3)
        for i in range(9):  # 3 windows of 3 ticks
            atr.update(100 + i)
        assert atr.data_points == 3

    def test_save_and_load_state(self):
        atr = ATRApproximator(period=3, window_size=5)
        prices = [100, 101, 99, 102, 98, 100, 103, 97, 101, 99]
        for p in prices:
            atr.update(p)

        state = atr.save_state()
        atr2 = ATRApproximator(period=3, window_size=5)
        atr2.load_state(state)

        assert atr2.ready == atr.ready
        assert atr2.atr == atr.atr
        assert atr2.data_points == atr.data_points


# ── TradingStrategy ──────────────────────────────────────────────────

class TestTradingStrategy:
    def setup_method(self):
        self.strategy = TradingStrategy()

    def _warm_atr(self, price: float = 4100.0) -> None:
        """Feed enough ticks to make ATR ready."""
        atr = self.strategy._atr
        # Need at least 2 completed windows
        for i in range(atr._window_size * 3):
            variation = (i % 5) * 0.5  # small price variation
            atr.update(price + variation)

    # ── Bias detection ────────────────────────────────────────────

    def test_flat_when_no_bias(self, neutral_row):
        self._warm_atr()
        self.strategy._cycle = 29  # next cycle triggers eval
        signal = self.strategy.evaluate(neutral_row)
        assert signal is not None
        assert signal.direction == "FLAT"

    def test_long_bias_with_bullish_signals(self, bullish_row):
        self._warm_atr(bullish_row["Price"])
        self.strategy._cycle = 29
        signal = self.strategy.evaluate(bullish_row)
        assert signal is not None
        assert signal.direction == "LONG"
        assert "Bullish" in signal.bias

    def test_short_bias_with_bearish_signals(self, bearish_row):
        self._warm_atr(bearish_row["Price"])
        self.strategy._cycle = 29
        signal = self.strategy.evaluate(bearish_row)
        assert signal is not None
        assert signal.direction == "SHORT"
        assert "Bearish" in signal.bias

    # ── Entry confirmation ────────────────────────────────────────

    def test_flat_when_confirmation_missing(self, bullish_row):
        """Bullish bias but bearish H1/H4 => FLAT."""
        self._warm_atr(bullish_row["Price"])
        row = {**bullish_row, "Hourly": "Strong Sell", "5 Hours": "Sell"}
        self.strategy._cycle = 29
        signal = self.strategy.evaluate(row)
        assert signal.direction == "FLAT"
        assert "NOT confirmed" in signal.reason

    # ── ATR gates ─────────────────────────────────────────────────

    def test_flat_when_atr_not_ready(self, bullish_row):
        """ATR not warmed up => FLAT even with perfect signals."""
        self.strategy._cycle = 29
        signal = self.strategy.evaluate(bullish_row)
        assert signal.direction == "FLAT"
        assert "ATR not ready" in signal.reason

    def test_flat_when_price_missing(self):
        row = {"Date-Time": datetime.now(timezone.utc), "Price": None}
        self.strategy._cycle = 29
        signal = self.strategy.evaluate(row)
        assert signal.direction == "FLAT"

    # ── Signal computation ────────────────────────────────────────

    def test_stop_loss_long(self, bullish_row):
        self._warm_atr(bullish_row["Price"])
        self.strategy._cycle = 29
        signal = self.strategy.evaluate(bullish_row)
        assert signal.stop_loss is not None
        assert signal.stop_loss < signal.entry_price

    def test_stop_loss_short(self, bearish_row):
        self._warm_atr(bearish_row["Price"])
        self.strategy._cycle = 29
        signal = self.strategy.evaluate(bearish_row)
        assert signal.stop_loss is not None
        assert signal.stop_loss > signal.entry_price

    def test_take_profit_long(self, bullish_row):
        self._warm_atr(bullish_row["Price"])
        self.strategy._cycle = 29
        signal = self.strategy.evaluate(bullish_row)
        assert signal.take_profit is not None
        assert signal.take_profit > signal.entry_price

    def test_take_profit_short(self, bearish_row):
        self._warm_atr(bearish_row["Price"])
        self.strategy._cycle = 29
        signal = self.strategy.evaluate(bearish_row)
        assert signal.take_profit is not None
        assert signal.take_profit < signal.entry_price

    def test_position_sizing_positive(self, bullish_row):
        self._warm_atr(bullish_row["Price"])
        self.strategy._cycle = 29
        signal = self.strategy.evaluate(bullish_row)
        assert signal.position_size_lots > 0

    def test_risk_amount_matches_config(self, bullish_row):
        from config.settings import ACCOUNT_BALANCE, RISK_PER_TRADE_PCT
        self._warm_atr(bullish_row["Price"])
        self.strategy._cycle = 29
        signal = self.strategy.evaluate(bullish_row)
        expected_risk = ACCOUNT_BALANCE * RISK_PER_TRADE_PCT
        assert signal.risk_amount == pytest.approx(expected_risk, abs=0.01)

    # ── Eval interval ─────────────────────────────────────────────

    def test_non_eval_cycle_reuses_last_signal(self, bullish_row):
        """Between eval cycles, the last signal is returned."""
        self._warm_atr(bullish_row["Price"])
        # Force an eval cycle
        self.strategy._cycle = 29
        sig1 = self.strategy.evaluate(bullish_row)
        # Next cycle is NOT an eval cycle
        sig2 = self.strategy.evaluate(bullish_row)
        assert sig2 is sig1  # same object reference

    # ── Confidence scoring ────────────────────────────────────────

    def test_confidence_is_valid(self, bullish_row):
        self._warm_atr(bullish_row["Price"])
        self.strategy._cycle = 29
        signal = self.strategy.evaluate(bullish_row)
        assert signal.confidence in ("HIGH", "MEDIUM", "LOW")

    # ── StrategySignal.to_row_dict ────────────────────────────────

    def test_signal_to_row_dict(self, bullish_row):
        self._warm_atr(bullish_row["Price"])
        self.strategy._cycle = 29
        signal = self.strategy.evaluate(bullish_row)
        d = signal.to_row_dict()
        assert "Signal" in d
        assert "Entry" in d
        assert "Stop Loss" in d
        assert "Take Profit" in d
        assert d["Signal"] == signal.direction
