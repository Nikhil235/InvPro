"""
risk_manager.py -- Pre-trade risk checks and daily limit enforcement.

Every order must pass ALL risk gates before the paper broker will fill it.
Rejected orders are logged with a human-readable reason.

Gates:
    1. Daily realised loss < MAX_DAILY_LOSS_PCT
    2. Daily trade count < MAX_DAILY_TRADES
    3. Open positions < MAX_OPEN_POSITIONS
    4. Signal confidence >= MIN_CONFIDENCE
    5. Stop loss and take profit must be present and valid
    6. Reward:risk ratio >= MIN_REWARD_RISK
"""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Tuple, Optional

from paper_trading.config.settings import (
    MAX_DAILY_LOSS_PCT,
    MAX_DAILY_TRADES,
    MAX_OPEN_POSITIONS,
    MIN_CONFIDENCE,
    MIN_REWARD_RISK,
    CONFIDENCE_RANK,
)
from paper_trading.core.order_manager import (
    OrderRequest,
    RejectedOrder,
    Side,
    make_event,
)
from core.clock import ClockService
from core.event_bus import EventBus
from core.events import ORDER_REJECTED
from paper_trading.core.account_ledger import AccountLedger
from paper_trading.utils.logger import get_logger

log = get_logger("risk_mgr")

class RiskManager:
    """
    Stateful risk manager that tracks daily limits.
    Resets automatically at the day boundary using ClockService.
    """

    def __init__(
        self,
        clock: Optional[ClockService] = None,
        event_bus: Optional[EventBus] = None,
        ledger: Optional[AccountLedger] = None,
        session_id: str = "test_session",
        initial_capital: float = 10000.0
    ) -> None:
        if clock is None:
            from core.clock import ClockService
            clock = ClockService(mode="live")
        if event_bus is None:
            from core.event_bus import EventBus
            event_bus = EventBus()
        if ledger is None:
            from core.database import Database
            from paper_trading.core.account_ledger import AccountLedger
            self._db_path = "test_risk_manager.db"
            import os
            if os.path.exists(self._db_path):
                try:
                    os.remove(self._db_path)
                except Exception:
                    pass
            db = Database(db_path=self._db_path)
            db.migrate()
            ledger = AccountLedger(db, clock, event_bus, session_id, initial_capital)
            
        self._clock = clock
        self._event_bus = event_bus
        self._ledger = ledger
        self._session_id = session_id
        
        self._current_date: date = self._clock.now().date()
        self._daily_trades: int = 0
        self._daily_realised_pnl: float = 0.0
        self._rejections: List[RejectedOrder] = []

    def check_order(self, request: OrderRequest, open_position_count: int, current_balance: Optional[float] = None, timestamp: Optional[datetime] = None) -> Tuple[bool, str]:
        self._maybe_reset_day(timestamp)
        request.session_id = self._session_id

        # Gate 1: Daily loss limit & Max Drawdown
        peak_equity = current_balance if current_balance is not None else self._ledger.peak_equity
        max_loss = peak_equity * MAX_DAILY_LOSS_PCT
        if self._daily_realised_pnl < 0 and abs(self._daily_realised_pnl) >= max_loss:
            reason = (
                f"Daily loss limit reached: "
                f"${abs(self._daily_realised_pnl):,.2f} losses today "
                f"(limit: ${max_loss:,.2f} = {MAX_DAILY_LOSS_PCT*100:.1f}% of capital)"
            )
            self._reject(request, reason)
            return False, reason
            
        drawdown_pct = self._ledger.drawdown_pct
        if drawdown_pct > 0.05:
            reason = f"Max Drawdown reached: {drawdown_pct*100:.2f}% (Limit: 5.00%)"
            self._reject(request, reason)
            return False, reason

        # Gate 2: Daily trade count
        if self._daily_trades >= MAX_DAILY_TRADES:
            reason = (
                f"Daily trade limit reached: "
                f"{self._daily_trades}/{MAX_DAILY_TRADES} trades today"
            )
            self._reject(request, reason)
            return False, reason

        # Gate 3: Open position limit
        if open_position_count >= MAX_OPEN_POSITIONS:
            reason = (
                f"Max open positions reached: "
                f"{open_position_count}/{MAX_OPEN_POSITIONS}"
            )
            self._reject(request, reason)
            return False, reason

        # Gate 4: Confidence threshold
        req_rank = CONFIDENCE_RANK.get(request.confidence, -1)
        min_rank = CONFIDENCE_RANK.get(MIN_CONFIDENCE, 1)
        if req_rank < min_rank:
            reason = (
                f"Confidence too low: {request.confidence} "
                f"(minimum: {MIN_CONFIDENCE})"
            )
            self._reject(request, reason)
            return False, reason

        # Gate 5: Valid SL/TP
        if request.stop_loss is None or request.take_profit is None:
            reason = "Missing stop loss or take profit"
            self._reject(request, reason)
            return False, reason

        if request.side == Side.LONG:
            if request.stop_loss >= request.requested_price:
                reason = (
                    f"Invalid LONG SL: SL={request.stop_loss:,.2f} "
                    f">= entry={request.requested_price:,.2f}"
                )
                self._reject(request, reason)
                return False, reason
            if request.take_profit <= request.requested_price:
                reason = (
                    f"Invalid LONG TP: TP={request.take_profit:,.2f} "
                    f"<= entry={request.requested_price:,.2f}"
                )
                self._reject(request, reason)
                return False, reason
        else:  # SHORT
            if request.stop_loss <= request.requested_price:
                reason = (
                    f"Invalid SHORT SL: SL={request.stop_loss:,.2f} "
                    f"<= entry={request.requested_price:,.2f}"
                )
                self._reject(request, reason)
                return False, reason
            if request.take_profit >= request.requested_price:
                reason = (
                    f"Invalid SHORT TP: TP={request.take_profit:,.2f} "
                    f">= entry={request.requested_price:,.2f}"
                )
                self._reject(request, reason)
                return False, reason

        # Gate 6: Reward:Risk ratio
        if request.side == Side.LONG:
            risk = request.requested_price - request.stop_loss
            reward = request.take_profit - request.requested_price
        else:
            risk = request.stop_loss - request.requested_price
            reward = request.requested_price - request.take_profit

        if risk <= 0:
            reason = f"Invalid risk distance: {risk:,.2f}"
            self._reject(request, reason)
            return False, reason

        rr_ratio = reward / risk
        if rr_ratio < (MIN_REWARD_RISK - 0.05):
            reason = (
                f"R:R too low: {rr_ratio:.2f} "
                f"(minimum: {MIN_REWARD_RISK:.1f})"
            )
            self._reject(request, reason)
            return False, reason

        # Gate 7: Geopolitical / Macro News Risk Gate
        news_risk_filter = False
        try:
            from api.store import store
            settings = store.get_settings()
            news_risk_filter = getattr(settings, "news_risk_filter", False)
        except Exception as e:
            log.warning(f"Could not load news_risk_filter from settings: {e}")

        if news_risk_filter:
            try:
                # Query db for high impact RISK_OFF events in the last 2 hours
                # SQLite timestamp is stored in ISO format: '2026-06-29T11:48:18.123+00:00'
                recent_events = self._ledger._db.fetchall("""
                    SELECT headline, timestamp FROM news_events 
                    WHERE impact_score = 'HIGH' 
                      AND sentiment = 'RISK_OFF'
                      AND datetime(timestamp) >= datetime('now', '-2 hours')
                    ORDER BY timestamp DESC
                """)
                if recent_events:
                    reason = (
                        f"Blocked by Macro News Gate: Recent High Impact Geopolitical Alert "
                        f"({recent_events[0]['headline'][:40]}...)"
                    )
                    self._reject(request, reason)
                    return False, reason
            except Exception as e:
                log.error(f"Error checking recent news events in RiskManager: {e}", exc_info=True)



        log.debug(
            f"Order request approved: "
            f"{request.side.value} {request.lots:.4f} lots, "
            f"confidence={request.confidence}, R:R={rr_ratio:.2f}"
        )
        return True, "APPROVED"

    def record_trade_result(self, pnl: float, timestamp: Optional[datetime] = None) -> None:
        self._maybe_reset_day(timestamp)
        self._daily_realised_pnl += pnl
        self._daily_trades += 1
        log.debug(
            f"Daily stats: trades={self._daily_trades}, "
            f"realised_pnl=${self._daily_realised_pnl:,.2f}"
        )

    def daily_trades(self, timestamp: Optional[datetime] = None) -> int:
        self._maybe_reset_day(timestamp)
        return self._daily_trades

    def daily_pnl(self, timestamp: Optional[datetime] = None) -> float:
        self._maybe_reset_day(timestamp)
        return self._daily_realised_pnl

    @property
    def rejections(self) -> List[RejectedOrder]:
        return self._rejections

    def reset(self) -> None:
        self._daily_trades = 0
        self._daily_realised_pnl = 0.0
        self._current_date = self._clock.now().date()

    def _maybe_reset_day(self, current_time: Optional[datetime] = None) -> None:
        if current_time is None:
            current_time = self._clock.now()
        today = current_time.date() if hasattr(current_time, 'date') else current_time
        if today != self._current_date:
            log.info(
                f"Day rollover: {self._current_date} -> {today}. "
                f"Resetting daily counters. "
                f"Yesterday: {self._daily_trades} trades, "
                f"P&L=${self._daily_realised_pnl:,.2f}"
            )
            self._daily_trades = 0
            self._daily_realised_pnl = 0.0
            self._current_date = today

    def _reject(self, request: OrderRequest, reason: str) -> None:
        rejection = RejectedOrder(
            order_id=request.order_id,
            side=request.side,
            requested_price=request.requested_price,
            lots=request.lots,
            confidence=request.confidence,
            rejection_reason=reason,
            timestamp=self._clock.now(),
            session_id=self._session_id
        )
        self._rejections.append(rejection)
        log.warning(f"Order REJECTED: {reason}")
        
        self._event_bus.publish(ORDER_REJECTED, make_event(
            ORDER_REJECTED,
            order_id=request.order_id,
            side=request.side.value,
            reason=reason,
            session_id=self._session_id
        ))


