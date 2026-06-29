"""
signal_router.py -- Routes StrategySignal objects into paper trading orders.

Translates advisory signals from the strategy layer into OrderRequests,
validates them through the risk manager, and submits approved orders
to the paper broker. Handles signal direction changes (close + reverse).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.strategy import StrategySignal
from core.event_bus import EventBus
from core.events import SIGNAL
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
    def __init__(
        self,
        broker: PaperBroker,
        risk_manager: RiskManager,
        event_bus: EventBus,
    ) -> None:
        self._broker = broker
        self._risk = risk_manager
        self._event_bus = event_bus
        
        # Sync last_direction with actual open positions on startup
        open_pos = self._broker.open_positions
        if open_pos:
            self._last_direction = open_pos[-1].side.value
        else:
            self._last_direction = None
            
        self._signals_received = 0
        self._signals_acted = 0
        self._signals_skipped = 0
        self._paused = False

    def pause(self) -> None:
        if not self._paused:
            log.warning("Signal router PAUSED due to stale data")
            self._paused = True

    def resume(self) -> None:
        if self._paused:
            log.info("Signal router RESUMED")
            self._paused = False

    def pause_and_liquidate(self, price: float, timestamp: datetime) -> None:
        if not self._paused:
            log.warning("Signal router PAUSED due to stale data. Liquidating all positions.")
            self._paused = True
            
            # Force close all positions immediately to protect capital
            closed = self._broker.close_all_positions(
                price=price,
                timestamp=timestamp,
                reason=ExitReason.RISK_LIMIT, # Treat stale feed as risk limit breach
            )
            for t in closed:
                self._risk.record_trade_result(t.net_pnl)
            
            self._last_direction = "FLAT"

    def process_signal(
        self,
        signal: StrategySignal,
        current_price: float,
        timestamp: Optional[datetime] = None,
    ) -> Optional[ClosedTrade]:
        if self._paused:
            return None
        if timestamp is None:
            timestamp = datetime.now()

        self._signals_received += 1
        closed_trade = None
        
        # Publish SIGNAL event
        self._event_bus.publish(SIGNAL, {
            "direction": signal.direction,
            "bias": signal.bias,
            "confidence": signal.confidence,
            "entry": signal.entry_price,
            "sl": signal.stop_loss,
            "tp": signal.take_profit,
            "tp1": signal.tp1,
            "tp2": signal.tp2,
            "tp3": signal.tp3,
            "lots": signal.position_size_lots,
            "reason": signal.reason,
            "timestamp": signal.timestamp.isoformat()
        })

        if signal.direction == "FLAT":
            self._signals_skipped += 1
            log.debug(f"Signal #{self._signals_received}: FLAT -- skipped")
            return None

        if (
            signal.direction == self._last_direction
            and self._broker.open_position_count > 0
        ):
            self._signals_skipped += 1
            return None

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
                closed_trade = closed[-1]

        self._last_direction = signal.direction

        if not self._validate_signal(signal):
            self._signals_skipped += 1
            return closed_trade

        side = Side.LONG if signal.direction == "LONG" else Side.SHORT
        request = OrderRequest(
            side=side,
            requested_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            tp1=signal.tp1,
            tp2=signal.tp2,
            tp3=signal.tp3,
            lots=signal.position_size_lots,
            confidence=signal.confidence,
            bias=signal.bias,
            risk_amount=signal.risk_amount or 0.0,
            signal_time=signal.timestamp,
            reason=signal.reason,
            strategy_blob=json.dumps({
                "version": "1.0",
                "timestamp": signal.timestamp.isoformat(),
                "data": signal.to_row_dict()
            })
        )

        approved, reason = self._risk.check_order(
            request,
            open_position_count=self._broker.open_position_count,
        )

        if not approved:
            self._signals_skipped += 1
            return closed_trade

        self._broker.submit_order(request, fill_time=timestamp)
        self._signals_acted += 1

        return closed_trade

    def _validate_signal(self, signal: StrategySignal) -> bool:
        if signal.entry_price is None:
            return False
        if signal.stop_loss is None:
            return False
        if signal.take_profit is None:
            return False
        if signal.position_size_lots is None or signal.position_size_lots <= 0:
            return False
        return True

    @property
    def signals_received(self) -> int:
        return self._signals_received

    @property
    def signals_acted(self) -> int:
        return self._signals_acted

    @property
    def signals_skipped(self) -> int:
        return self._signals_skipped
