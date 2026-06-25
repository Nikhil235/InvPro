"""
signal_router.py -- Routes StrategySignal objects into paper trading orders.

Translates advisory signals from the strategy layer into OrderRequests,
validates them through the risk manager, and submits approved orders
to the paper broker.  Handles signal direction changes (close + reverse).

WARNING: Paper trading only. No live execution. All results are simulated.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from core.strategy import StrategySignal

from paper_trading.core.order_manager import (
    OrderRequest,
    ClosedTrade,
    Side,
    ExitReason,
    make_event,
)
from paper_trading.core.paper_broker import PaperBroker
from paper_trading.core.risk_manager import RiskManager
from paper_trading.utils.logger import get_logger

log = get_logger("router")


class SignalRouter:
    """
    Converts StrategySignal -> OrderRequest and manages the flow:
        Signal -> Validate -> Risk Check -> Broker Submit

    Also handles position reversal when the signal direction flips
    (e.g. LONG->SHORT closes the LONG and opens a SHORT).
    """

    def __init__(
        self,
        broker: PaperBroker,
        risk_manager: RiskManager,
    ) -> None:
        self._broker = broker
        self._risk = risk_manager
        self._last_direction: Optional[str] = None
        self._signals_received: int = 0
        self._signals_acted: int = 0
        self._signals_skipped: int = 0

    # ── Public API ────────────────────────────────────────────────

    def process_signal(
        self,
        signal: StrategySignal,
        current_price: float,
        timestamp: Optional[datetime] = None,
    ) -> Optional[ClosedTrade]:
        """
        Process an advisory signal from the strategy layer.

        Returns a ClosedTrade if a position was closed on direction change,
        otherwise None.

        Flow:
            1. Skip FLAT signals (no action)
            2. Skip if direction unchanged and position already open
            3. Close existing position on direction reversal
            4. Build OrderRequest from signal
            5. Run risk checks
            6. Submit to broker if approved
        """
        if timestamp is None:
            timestamp = datetime.now()

        self._signals_received += 1
        closed_trade = None

        # Step 1: FLAT = no action
        if signal.direction == "FLAT":
            self._signals_skipped += 1
            log.debug(f"Signal #{self._signals_received}: FLAT -- skipped")
            return None

        # Step 2: Skip if same direction and we already have a position
        if (
            signal.direction == self._last_direction
            and self._broker.open_position_count > 0
        ):
            self._signals_skipped += 1
            return None

        # Step 3: Direction reversal -> close existing positions
        if (
            self._last_direction is not None
            and signal.direction != self._last_direction
            and self._broker.open_position_count > 0
        ):
            log.info(
                f"Direction reversal: {self._last_direction} -> {signal.direction}. "
                f"Closing {self._broker.open_position_count} open position(s)."
            )
            closed = self._broker.close_all_positions(
                price=current_price,
                timestamp=timestamp,
                reason=ExitReason.SIGNAL_REVERSAL,
            )
            for t in closed:
                self._risk.record_trade_result(t.net_pnl)
            if closed:
                closed_trade = closed[-1]  # Return last closed trade

        self._last_direction = signal.direction

        # Step 4: Validate signal has required fields
        if not self._validate_signal(signal):
            self._signals_skipped += 1
            return closed_trade

        # Step 5: Build order request
        side = Side.LONG if signal.direction == "LONG" else Side.SHORT
        request = OrderRequest(
            side=side,
            requested_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            lots=signal.position_size_lots,
            confidence=signal.confidence,
            bias=signal.bias,
            risk_amount=signal.risk_amount or 0.0,
            signal_time=signal.timestamp,
            reason=signal.reason,
        )

        # Step 6: Risk check
        approved, reason = self._risk.check_order(
            request,
            open_position_count=self._broker.open_position_count,
            current_balance=self._broker.balance,
        )

        if not approved:
            self._signals_skipped += 1
            self._broker._emit_event(make_event(
                "ORDER_REJECTED",
                order_id=request.order_id,
                side=request.side,
                reason=reason,
            ))
            return closed_trade

        # Step 7: Submit to broker
        self._broker.submit_order(request, fill_time=timestamp)
        self._signals_acted += 1

        return closed_trade

    # ── Validation ────────────────────────────────────────────────

    def _validate_signal(self, signal: StrategySignal) -> bool:
        """Validate that a signal has all required fields for order creation."""
        if signal.entry_price is None:
            log.warning(
                f"Signal rejected: missing entry_price "
                f"(direction={signal.direction})"
            )
            return False

        if signal.stop_loss is None:
            log.warning(
                f"Signal rejected: missing stop_loss "
                f"(direction={signal.direction}, entry={signal.entry_price})"
            )
            return False

        if signal.take_profit is None:
            log.warning(
                f"Signal rejected: missing take_profit "
                f"(direction={signal.direction}, entry={signal.entry_price})"
            )
            return False

        if signal.position_size_lots is None or signal.position_size_lots <= 0:
            log.warning(
                f"Signal rejected: invalid lots={signal.position_size_lots} "
                f"(direction={signal.direction})"
            )
            return False

        return True

    # ── Stats ─────────────────────────────────────────────────────

    @property
    def signals_received(self) -> int:
        return self._signals_received

    @property
    def signals_acted(self) -> int:
        return self._signals_acted

    @property
    def signals_skipped(self) -> int:
        return self._signals_skipped
