"""Tests for partial take-profit exits (TP1/TP2/TP3) and trailing stop loss logic."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
import math

from paper_trading.core.paper_broker import PaperBroker
from paper_trading.core.order_manager import OrderRequest, Side, ExitReason, Position, ClosedTrade


def _make_order(**overrides) -> OrderRequest:
    defaults = {
        "side": Side.LONG,
        "requested_price": 4100.00,
        "stop_loss": 4090.00,
        "take_profit": 4130.00,
        "tp1": 4110.00,
        "tp2": 4120.00,
        "tp3": 4130.00,
        "lots": 0.3,
        "confidence": "HIGH",
        "bias": "Bullish",
        "risk_amount": 100.0,
        "signal_time": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return OrderRequest(**defaults)


class TestPartialTP:
    def setup_method(self):
        import os
        from core.database import Database
        from core.clock import ClockService
        from core.event_bus import EventBus
        from paper_trading.core.account_ledger import AccountLedger
        
        self.db_path = "test_trading_partial_tp.db"
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
        if hasattr(self, 'db'):
            self.db = None
        
        import time
        time.sleep(0.1)
        
        if hasattr(self, 'db_path') and os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    def test_partial_take_profit_lifecycle(self):
        # 1. Submit long order with lots = 0.3
        order = _make_order(side=Side.LONG, lots=0.3)
        fill = self.broker.submit_order(order)
        
        assert self.broker.open_position_count == 1
        pos = self.broker.open_positions[0]
        assert pos.lots == 0.3
        assert pos.tp1 == 4110.00
        assert pos.tp2 == 4120.00
        assert pos.tp3 == 4130.00
        assert pos.tp1_hit is False
        assert pos.stop_loss == 4090.00
        
        # 2. Trigger TP1 (Price moves to 4111.00)
        closed = self.broker.tick(4111.00)
        assert len(closed) == 1
        trade1 = closed[0]
        assert trade1.exit_reason == ExitReason.TP1_HIT
        assert trade1.exit_price == 4110.00
        assert trade1.lots == 0.1 # 1/3 of 0.3
        
        # Check active position
        assert self.broker.open_position_count == 1
        pos = self.broker.open_positions[0]
        assert pos.lots == 0.2
        assert pos.tp1_hit is True
        assert pos.stop_loss == pos.fill_price # Breakeven
        
        # 3. Trigger TP2 (Price moves to 4121.00)
        closed = self.broker.tick(4121.00)
        assert len(closed) == 1
        trade2 = closed[0]
        assert trade2.exit_reason == ExitReason.TP2_HIT
        assert trade2.exit_price == 4120.00
        assert trade2.lots == 0.1
        
        # Check active position
        assert self.broker.open_position_count == 1
        pos = self.broker.open_positions[0]
        assert pos.lots == 0.1
        assert pos.tp2_hit is True
        
        # 4. Trigger TP3 (Price moves to 4131.00)
        closed = self.broker.tick(4131.00)
        assert len(closed) == 1
        trade3 = closed[0]
        assert trade3.exit_reason == ExitReason.TP3_HIT
        assert trade3.exit_price == 4130.00
        assert trade3.lots == 0.1
        
        # Position should now be fully closed
        assert self.broker.open_position_count == 0

    def test_sl_hit_closes_remaining_position(self):
        # 1. Submit long order with lots = 0.3
        order = _make_order(side=Side.LONG, lots=0.3)
        self.broker.submit_order(order)
        
        # 2. Trigger TP1 (Price moves to 4111.00)
        closed = self.broker.tick(4111.00)
        assert len(closed) == 1
        assert closed[0].exit_reason == ExitReason.TP1_HIT
        
        pos = self.broker.open_positions[0]
        assert pos.lots == 0.2
        assert pos.stop_loss == pos.fill_price # Breakeven
        
        # 3. Trigger SL (Price falls back to entry fill price)
        entry_fill_price = pos.fill_price
        closed = self.broker.tick(entry_fill_price - 1.0)
        assert len(closed) == 1
        trade = closed[0]
        assert trade.exit_reason == ExitReason.SL_HIT
        assert trade.lots == 0.2
        
        # Position should be fully closed
        assert self.broker.open_position_count == 0

    def test_trailing_sl_updates(self):
        # LONG position
        order = _make_order(side=Side.LONG, lots=0.3, requested_price=4100.0, stop_loss=4090.0, tp3=9999.0) # original risk dist = 10
        self.broker.submit_order(order)
        pos = self.broker.open_positions[0]
        
        # Trigger TP1 -> SL moves to breakeven (which is fill_price)
        self.broker.tick(4111.00)
        pos = self.broker.open_positions[0]
        assert pos.stop_loss == pos.fill_price
        
        # Trigger TP2 -> Trailing SL is enabled.
        risk_dist = pos.fill_price - pos.initial_sl
        assert risk_dist > 0
        
        self.broker.tick(4121.00)
        pos = self.broker.open_positions[0]
        assert pos.tp2_hit is True
        
        # Price goes up to 4140.00
        # New sl should trail the price by risk_dist
        self.broker.tick(4140.00)
        pos = self.broker.open_positions[0]
        expected_sl = 4140.00 - risk_dist
        assert pos.stop_loss == expected_sl
        
        # Price drops to expected_sl -> SL hits
        closed = self.broker.tick(expected_sl - 1.0)
        assert len(closed) == 1
        assert closed[0].exit_reason == ExitReason.SL_HIT
        assert self.broker.open_position_count == 0

    def test_invalid_close_price_validation(self):
        order = _make_order(lots=0.3)
        self.broker.submit_order(order)
        pos_id = list(self.broker._positions.keys())[0]
        
        # Close with NaN price should fall back to fill price
        closed = self.broker.close_position(pos_id, price=float('nan'))
        assert closed is not None
        assert math.isfinite(closed.exit_price)
        assert closed.exit_price == closed.fill_price
