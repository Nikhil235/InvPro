"""
order_manager.py -- Order lifecycle management and core dataclasses.

Defines the data structures shared across the paper trading platform:
    OrderRequest  ->  Fill  ->  Position  ->  ClosedTrade

Each state transition is tracked with timestamps and metadata for
the validation layer and trade journal.

WARNING: Paper trading only. No live execution. All results are simulated.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from paper_trading.utils.logger import get_logger

log = get_logger("order_mgr")

# ── Auto-incrementing ID generators ──────────────────────────────────
_order_counter = itertools.count(1)
_trade_counter = itertools.count(1)


def reset_counters() -> None:
    """Reset all module-level ID counters.  Use in tests or multi-session replays."""
    global _order_counter, _trade_counter
    _order_counter = itertools.count(1)
    _trade_counter = itertools.count(1)


# ── Enums ─────────────────────────────────────────────────────────────

class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class ExitReason(str, Enum):
    SL_HIT = "SL_HIT"
    TP_HIT = "TP_HIT"
    SIGNAL_REVERSAL = "SIGNAL_REVERSAL"
    MANUAL_CLOSE = "MANUAL_CLOSE"
    END_OF_SESSION = "END_OF_SESSION"
    RISK_LIMIT = "RISK_LIMIT"


# ── Dataclasses ───────────────────────────────────────────────────────

@dataclass
class OrderRequest:
    """
    A request to open a new position.  Produced by the SignalRouter
    after converting a StrategySignal.
    """
    side:            Side
    requested_price: float          # Advisory entry price from strategy
    stop_loss:       float
    take_profit:     float
    lots:            float
    confidence:      str            # "HIGH", "MEDIUM", "LOW"
    bias:            str            # e.g. "Bullish (Daily=Buy, Weekly=Strong Buy)"
    risk_amount:     float          # Dollar risk from strategy
    signal_time:     datetime       # When the strategy generated the signal
    reason:          str = ""       # Strategy reason string
    order_id:        int = 0

    def __post_init__(self) -> None:
        if self.order_id == 0:
            self.order_id = next(_order_counter)


@dataclass
class Fill:
    """Result of a simulated order fill from the paper broker."""
    order_id:     int
    fill_price:   float             # Actual fill price (after spread + slippage)
    spread_cost:  float             # Spread component
    slippage:     float             # Slippage component
    fill_time:    datetime
    status:       OrderStatus = OrderStatus.FILLED


@dataclass
class Position:
    """An open position being tracked by the broker."""
    position_id:  int
    order_id:     int
    side:         Side
    entry_price:  float             # Requested entry from strategy
    fill_price:   float             # Actual fill (entry + spread + slippage)
    stop_loss:    float
    take_profit:  float
    lots:         float
    open_time:    datetime
    confidence:   str
    bias:         str
    risk_amount:  float
    reason:       str = ""

    # Computed at each tick
    unrealised_pnl: float = 0.0
    current_price:  float = 0.0

    def update_pnl(self, price: float, lot_size: int = 100) -> None:
        """Recalculate unrealised P&L at the current market price."""
        self.current_price = price
        if self.side == Side.LONG:
            self.unrealised_pnl = (price - self.fill_price) * self.lots * lot_size
        else:
            self.unrealised_pnl = (self.fill_price - price) * self.lots * lot_size

    def check_sl_tp(self, price: float) -> Optional[ExitReason]:
        """
        Check whether the current price has hit the stop loss or take profit.

        Returns the ExitReason if triggered, otherwise None.
        """
        if self.side == Side.LONG:
            if price <= self.stop_loss:
                return ExitReason.SL_HIT
            if price >= self.take_profit:
                return ExitReason.TP_HIT
        else:  # SHORT
            if price >= self.stop_loss:
                return ExitReason.SL_HIT
            if price <= self.take_profit:
                return ExitReason.TP_HIT
        return None


@dataclass
class ClosedTrade:
    """A fully resolved trade with entry, exit, and P&L."""
    trade_id:        int
    order_id:        int
    position_id:     int
    side:            Side
    entry_price:     float          # Advisory price from strategy
    fill_price:      float          # Actual fill
    stop_loss:       float
    take_profit:     float
    exit_price:      float
    lots:            float
    open_time:       datetime
    close_time:      datetime
    exit_reason:     ExitReason
    gross_pnl:       float
    commission:      float
    net_pnl:         float
    risk_amount:     float
    rr_achieved:     float          # Actual reward / risk
    confidence:      str
    bias:            str
    balance_after:   float
    reason:          str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict for JSON / DataFrame conversion."""
        d = asdict(self)
        d["side"] = self.side.value
        d["exit_reason"] = self.exit_reason.value
        d["open_time"] = self.open_time.isoformat()
        d["close_time"] = self.close_time.isoformat()
        return d

    @property
    def is_winner(self) -> bool:
        return self.net_pnl > 0

    @property
    def holding_time_seconds(self) -> float:
        return (self.close_time - self.open_time).total_seconds()


@dataclass
class RejectedOrder:
    """Record of an order that was rejected by the risk manager."""
    order_id:      int
    side:          Side
    requested_price: float
    lots:          float
    confidence:    str
    rejection_reason: str
    timestamp:     datetime

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["side"] = self.side.value
        d["timestamp"] = self.timestamp.isoformat()
        return d


# ── Event factory ─────────────────────────────────────────────────────

def make_event(event_type: str, timestamp: Optional[datetime] = None, **kwargs) -> Dict[str, Any]:
    """
    Create a structured event dict for the JSON event log.

    Every event has a ``type``, ``timestamp``, and arbitrary payload fields.
    If *timestamp* is not provided, the current time is used.
    """
    event = {
        "type": event_type,
        "timestamp": (timestamp or datetime.now()).isoformat(),
    }
    for k, v in kwargs.items():
        if isinstance(v, datetime):
            event[k] = v.isoformat()
        elif isinstance(v, Enum):
            event[k] = v.value
        else:
            event[k] = v
    return event
