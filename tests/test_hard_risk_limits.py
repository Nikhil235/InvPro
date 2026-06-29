"""Tests for hard risk limit controls: $100 per-trade cap and $1,000 daily trading basket."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
import math
from typing import Any, Optional

from core.database import Database
from core.clock import ClockService
from core.event_bus import EventBus
from paper_trading.core.account_ledger import AccountLedger
from paper_trading.core.paper_broker import PaperBroker
from paper_trading.core.risk_manager import RiskManager
from core.strategy import TradingStrategy
from paper_trading.core.order_manager import OrderRequest, Side, ExitReason, Position


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
        "risk_amount": 90.0,
        "signal_time": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return OrderRequest(**defaults)


class TestHardRiskLimits:
    def setup_method(self):
        import os
        self.db_path = "test_trading_hard_risk_limits.db"
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass
                
        self.db = Database(db_path=self.db_path)
        self.db.migrate()
        self.clock = ClockService(mode="live")
        self.event_bus = EventBus()
        self.session_id = "test_risk_session"
        self.ledger = AccountLedger(self.db, self.clock, self.event_bus, self.session_id, 20_000.0)
        self.broker = PaperBroker(self.db, self.clock, self.event_bus, self.ledger, self.session_id)
        self.risk_mgr = RiskManager(self.clock, self.event_bus, self.ledger, self.session_id)
        self.strategy = TradingStrategy(db=self.db, session_id=self.session_id, clock=self.clock)

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

    def test_per_trade_sizing_cap(self):
        # On a $20,000 balance, a 1% risk per trade is $200.
        # The strategy should automatically cap the risk_amount at $100.
        row = {
            "Date-Time": datetime.now(timezone.utc),
            "Price": 4100.0,
            "Daily": "Strong Buy",
            "Weekly": "Buy",
            "Hourly": "Strong Buy",
            "5 Hours": "Buy",
            "Monthly": "Buy",
        }
        # Ready the ATR estimator inside strategy
        self.strategy._atr._ranges.extend([5.0] * 15)
        self.strategy._atr._atr = 5.0
        
        # Run evaluate
        self.strategy._cycle = 29
        signal = self.strategy.evaluate(row, current_balance=20_000.0)
        assert signal is not None
        assert signal.direction == "LONG"
        # Risk amount should be capped at $100.00 (instead of $200.00)
        assert signal.risk_amount == 100.00
        # Position lots should be: 100.0 / (7.5 * 100) = 0.1333 lots
        assert signal.position_size_lots == 0.1333

    def test_daily_basket_sizing_cap_and_kill_switch(self):
        row = {
            "Date-Time": datetime.now(timezone.utc),
            "Price": 4100.0,
            "Daily": "Strong Buy",
            "Weekly": "Buy",
            "Hourly": "Strong Buy",
            "5 Hours": "Buy",
            "Monthly": "Buy",
        }
        self.strategy._atr._ranges.extend([5.0] * 15)
        self.strategy._atr._atr = 5.0
        
        # 1. Simulate existing committed risk of $950 today
        sql = """
            INSERT INTO trades (
                order_id, position_id, side, entry_price, fill_price, exit_price,
                stop_loss, take_profit, lots, open_time, close_time, exit_reason,
                gross_pnl, commission, net_pnl, risk_amount, rr_achieved,
                confidence, bias, balance_after, reason, session_id, strategy_blob
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        self.db.execute(sql, (
            1, 1, "LONG", 4100.0, 4100.0, 4110.0,
            4090.0, 4130.0, 0.95, datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat(),
            "TP_HIT", 950.0, 0.0, 950.0, 950.0, 1.0,
            "HIGH", "Bullish", 20950.0, "reason", self.session_id, "{}"
        ))
        
        # Now, remaining basket is 1000 - 950 = 50.
        self.strategy._cycle = 29
        signal = self.strategy.evaluate(row, current_balance=20_000.0)
        assert signal is not None
        assert signal.risk_amount == 50.00
        # Lots should be: 50.0 / (7.5 * 100) = 0.0667 lots
        assert signal.position_size_lots == 0.0667
        
        # 2. Add another trade of $50 risk to fully exhaust the basket
        self.db.execute(sql, (
            2, 2, "LONG", 4100.0, 4100.0, 4110.0,
            4090.0, 4130.0, 0.05, datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat(),
            "TP_HIT", 50.0, 0.0, 50.0, 50.0, 1.0,
            "HIGH", "Bullish", 21000.0, "reason", self.session_id, "{}"
        ))
        
        # Now, remaining basket is 0. Sizing should return None (Kill-switch!).
        self.strategy._cycle = 29
        signal2 = self.strategy.evaluate(row, current_balance=20_000.0)
        assert signal2 is None

    def test_risk_manager_gates(self):
        # 1. Gate 8: Per-trade risk cap ($100)
        # Risk = 12 * 0.1 * 100 = $120.00
        order_large = _make_order(lots=0.1, stop_loss=4088.0, requested_price=4100.0)
        approved, reason = self.risk_mgr.check_order(order_large, open_position_count=0)
        assert approved is False
        assert "exceeds per-trade risk limit of $100.00" in reason

        # Risk = 10 * 0.1 * 100 = $100.00
        order_ok = _make_order(lots=0.1, stop_loss=4090.0, requested_price=4100.0)
        approved, reason = self.risk_mgr.check_order(order_ok, open_position_count=0)
        assert approved is True

        # 2. Gate 9: Daily basket cap ($1000)
        # Fake daily committed risk of $950
        sql = """
            INSERT INTO trades (
                order_id, position_id, side, entry_price, fill_price, exit_price,
                stop_loss, take_profit, lots, open_time, close_time, exit_reason,
                gross_pnl, commission, net_pnl, risk_amount, rr_achieved,
                confidence, bias, balance_after, reason, session_id, strategy_blob
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        self.db.execute(sql, (
            3, 3, "LONG", 4100.0, 4100.0, 4110.0,
            4090.0, 4130.0, 0.95, datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat(),
            "TP_HIT", 950.0, 0.0, 950.0, 950.0, 1.0,
            "HIGH", "Bullish", 20950.0, "reason", self.session_id, "{}"
        ))
        
        # Order risking $60.00 should be rejected because 950 + 60 = 1010 > 1000.
        order_overflow = _make_order(lots=0.06, stop_loss=4090.0, requested_price=4100.0)
        approved, reason = self.risk_mgr.check_order(order_overflow, open_position_count=0)
        assert approved is False
        assert "would exceed daily committed risk limit of $1000.00" in reason

    def test_proportional_risk_partitioning(self):
        # 1. Fill order with $90 risk (lots = 0.3, sl = 4090, entry = 4100)
        order = _make_order(lots=0.3, stop_loss=4090.0, requested_price=4100.0)
        fill = self.broker.submit_order(order)
        
        pos = self.broker.open_positions[0]
        assert pos.lots == 0.3
        
        # Verify initial risk in DB
        row = self.db.fetchone("SELECT risk_amount FROM positions WHERE position_id = ?", (pos.position_id,))
        assert row[0] == 90.0
        
        # 2. Trigger partial close TP1 (lots_to_close = 0.1)
        closed = self.broker.tick(4110.0)
        assert len(closed) == 1
        trade = closed[0]
        
        # The trade leg's risk should be 1/3 of $90 = $30
        assert trade.risk_amount == 30.0
        
        # The remaining position size is 0.2 lots, risk is $60
        pos = self.broker.open_positions[0]
        assert pos.lots == 0.2
        assert pos.risk_amount == 60.0
        
        row_pos = self.db.fetchone("SELECT risk_amount FROM positions WHERE position_id = ?", (pos.position_id,))
        assert row_pos[0] == 60.0
        
        row_trade = self.db.fetchone("SELECT risk_amount FROM trades WHERE trade_id = ?", (trade.trade_id,))
        assert row_trade[0] == 30.0
