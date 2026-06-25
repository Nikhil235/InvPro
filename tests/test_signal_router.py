"""Tests for paper_trading.core.signal_router — routing, reversal, validation."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from core.strategy import StrategySignal
from paper_trading.core.paper_broker import PaperBroker
from paper_trading.core.risk_manager import RiskManager
from paper_trading.core.signal_router import SignalRouter


def _make_signal(direction="LONG", **overrides) -> StrategySignal:
    defaults = {
        "timestamp": datetime.now(timezone.utc),
        "direction": direction,
        "bias": "Bullish",
        "entry_confirmed": True,
        "confidence": "HIGH",
        "entry_price": 4100.00,
        "stop_loss": 4090.00,
        "take_profit": 4120.00,
        "position_size_lots": 0.1,
        "risk_amount": 100.0,
        "reason": "Test signal",
    }
    defaults.update(overrides)
    return StrategySignal(**defaults)


class TestSignalRouter:
    def setup_method(self):
        self.broker = PaperBroker(initial_capital=10_000.0)
        self.risk = RiskManager(initial_capital=10_000.0)
        self.router = SignalRouter(self.broker, self.risk)

    def test_flat_signal_skipped(self):
        signal = _make_signal(direction="FLAT")
        result = self.router.process_signal(signal, current_price=4100.0)
        assert result is None
        assert self.router.signals_skipped == 1
        assert self.broker.open_position_count == 0

    def test_long_signal_opens_position(self):
        signal = _make_signal(direction="LONG")
        self.router.process_signal(signal, current_price=4100.0)
        assert self.broker.open_position_count == 1
        assert self.router.signals_acted == 1

    def test_same_direction_same_position_skipped(self):
        sig1 = _make_signal(direction="LONG")
        sig2 = _make_signal(direction="LONG")
        self.router.process_signal(sig1, current_price=4100.0)
        self.router.process_signal(sig2, current_price=4101.0)
        assert self.broker.open_position_count == 1  # still just 1
        assert self.router.signals_skipped == 1

    def test_direction_reversal_closes_and_opens(self):
        sig_long = _make_signal(direction="LONG")
        sig_short = _make_signal(
            direction="SHORT",
            stop_loss=4110.0, take_profit=4080.0,
        )
        self.router.process_signal(sig_long, current_price=4100.0)
        assert self.broker.open_position_count == 1

        result = self.router.process_signal(sig_short, current_price=4100.0)
        # Old long should be closed, new short opened
        assert self.broker.open_position_count == 1
        assert len(self.broker.closed_trades) >= 1

    def test_signal_missing_fields_rejected(self):
        signal = _make_signal(direction="LONG", entry_price=None)
        self.router.process_signal(signal, current_price=4100.0)
        assert self.broker.open_position_count == 0
        assert self.router.signals_skipped == 1
