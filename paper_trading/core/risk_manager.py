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

WARNING: Paper trading only. No live execution. All results are simulated.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Tuple

from paper_trading.config.settings import (
    INITIAL_CAPITAL,
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
from paper_trading.utils.logger import get_logger

log = get_logger("risk_mgr")


class RiskManager:
    """
    Stateful risk manager that tracks daily limits.

    Resets automatically at the day boundary.
    """

    def __init__(self, initial_capital: float = INITIAL_CAPITAL) -> None:
        self._initial_capital = initial_capital
        self._current_date: date = date.today()
        self._daily_trades: int = 0
        self._daily_realised_pnl: float = 0.0
        self._rejections: List[RejectedOrder] = []

    # ── Public API ────────────────────────────────────────────────

    def check_order(
        self,
        request: OrderRequest,
        open_position_count: int,
        current_balance: float,
        timestamp: Optional[datetime] = None,
    ) -> Tuple[bool, str]:
        """
        Run all risk gates on an incoming order request.

        Args:
            timestamp: Optional datetime to use for day-boundary checks.
                       In replay mode, pass the row's timestamp so that
                       daily limits reset at the correct date boundary
                       (instead of using ``date.today()``).

        Returns:
            (approved, reason) -- True if all gates pass, False with reason.
        """
        self._maybe_reset_day(override_date=timestamp.date() if timestamp else None)

        # Gate 1: Daily loss limit
        max_loss = self._initial_capital * MAX_DAILY_LOSS_PCT
        if self._daily_realised_pnl < 0 and abs(self._daily_realised_pnl) >= max_loss:
            reason = (
                f"Daily loss limit reached: "
                f"${abs(self._daily_realised_pnl):,.2f} losses today "
                f"(limit: ${max_loss:,.2f} = {MAX_DAILY_LOSS_PCT*100:.1f}% of capital)"
            )
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
        # Add a tolerance epsilon (0.05) to avoid rejections caused by 
        # 2-decimal price rounding in the strategy layer which can make 
        # an exact 2.0 R:R appear as 1.99.
        if rr_ratio < (MIN_REWARD_RISK - 0.05):
            reason = (
                f"R:R too low: {rr_ratio:.2f} "
                f"(minimum: {MIN_REWARD_RISK:.1f})"
            )
            self._reject(request, reason)
            return False, reason

        # All gates passed
        log.debug(
            f"Order #{request.order_id} approved: "
            f"{request.side.value} {request.lots:.4f} lots, "
            f"confidence={request.confidence}, R:R={rr_ratio:.2f}"
        )
        return True, "APPROVED"

    def record_trade_result(self, pnl: float, timestamp: Optional[datetime] = None) -> None:
        """Record a closed trade's P&L for daily tracking."""
        self._maybe_reset_day(override_date=timestamp.date() if timestamp else None)
        self._daily_realised_pnl += pnl
        self._daily_trades += 1
        log.debug(
            f"Daily stats: trades={self._daily_trades}, "
            f"realised_pnl=${self._daily_realised_pnl:,.2f}"
        )

    @property
    def daily_trades(self) -> int:
        self._maybe_reset_day()
        return self._daily_trades

    @property
    def daily_pnl(self) -> float:
        self._maybe_reset_day()
        return self._daily_realised_pnl

    @property
    def rejections(self) -> List[RejectedOrder]:
        return self._rejections

    def reset(self) -> None:
        """Force reset daily counters (used in replay mode)."""
        self._daily_trades = 0
        self._daily_realised_pnl = 0.0
        self._current_date = date.today()

    # ── Private ───────────────────────────────────────────────────

    def _maybe_reset_day(self, override_date: Optional[date] = None) -> None:
        """Reset daily counters if the date has changed.

        Args:
            override_date: If provided, use this date instead of
                ``date.today()``.  Essential for replay mode where
                wall-clock time doesn't advance.
        """
        today = override_date or date.today()
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
        """Log and record a rejected order."""
        rejection = RejectedOrder(
            order_id=request.order_id,
            side=request.side,
            requested_price=request.requested_price,
            lots=request.lots,
            confidence=request.confidence,
            rejection_reason=reason,
            timestamp=datetime.now(),
        )
        self._rejections.append(rejection)
        log.warning(f"Order #{request.order_id} REJECTED: {reason}")
