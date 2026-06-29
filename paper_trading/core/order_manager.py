"""
order_manager.py -- Order lifecycle management and core dataclasses.

Defines the data structures shared across the paper trading platform.
Each state transition is tracked with timestamps and metadata for
the validation layer and trade journal.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from paper_trading.utils.logger import get_logger

log = get_logger("order_mgr")

# ── Enums ─────────────────────────────────────────────────────────────

class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"

class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"

class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"

class ExitReason(str, Enum):
    SL_HIT = "SL_HIT"
    TP_HIT = "TP_HIT"
    TP1_HIT = "TP1_HIT"
    TP2_HIT = "TP2_HIT"
    TP3_HIT = "TP3_HIT"
    SIGNAL_REVERSAL = "SIGNAL_REVERSAL"
    MANUAL_CLOSE = "MANUAL_CLOSE"
    END_OF_SESSION = "END_OF_SESSION"
    RISK_LIMIT = "RISK_LIMIT"

# ── Dataclasses ───────────────────────────────────────────────────────

@dataclass
class OrderRequest:
    side: Side
    requested_price: float
    stop_loss: float
    take_profit: float
    lots: float
    confidence: str
    bias: str
    risk_amount: float
    signal_time: datetime
    tp1: Optional[float] = None
    tp2: Optional[float] = None
    tp3: Optional[float] = None
    order_type: OrderType = OrderType.MARKET
    reason: str = ""
    order_id: int = 0
    session_id: str = ""
    status: OrderStatus = OrderStatus.PENDING
    strategy_blob: Optional[str] = None
    execution_mode: str = "live"
    slippage_model: str = "random_uniform"

    @property
    def parsed_strategy(self) -> dict:
        if not self.strategy_blob:
            return {}
        try:
            import json
            data = json.loads(self.strategy_blob)
            if isinstance(data, dict):
                return data.get("data", data)
            log.warning(f"Strategy blob is not a JSON object. Raw: {self.strategy_blob}")
            return {}
        except Exception as e:
            log.error(f"Malformed strategy_blob JSON detected. Exception: {e}", exc_info=True)
            return {}
    
    @classmethod
    def from_db_row(cls, row: sqlite3.Row) -> OrderRequest:
        return cls(
            order_id=row["order_id"],
            side=Side(row["side"]),
            requested_price=row["requested_price"],
            stop_loss=row["stop_loss"],
            take_profit=row["take_profit"],
            tp1=row["tp1"] if "tp1" in row.keys() else None,
            tp2=row["tp2"] if "tp2" in row.keys() else None,
            tp3=row["tp3"] if "tp3" in row.keys() else None,
            lots=row["lots"],
            order_type=OrderType(row["order_type"]),
            confidence=row["confidence"],
            bias=row["bias"],
            risk_amount=row["risk_amount"],
            signal_time=datetime.fromisoformat(row["signal_time"]),
            reason=row["reason"],
            session_id=row["session_id"],
            status=OrderStatus(row["status"]),
            strategy_blob=row["strategy_blob"] if "strategy_blob" in row.keys() else None,
            execution_mode=row["execution_mode"] if "execution_mode" in row.keys() and row["execution_mode"] else "live",
            slippage_model=row["slippage_model"] if "slippage_model" in row.keys() and row["slippage_model"] else "random_uniform"
        )

@dataclass
class Fill:
    order_id: int
    fill_price: float
    spread_cost: float
    slippage: float
    fill_time: datetime
    status: OrderStatus = OrderStatus.FILLED

@dataclass
class Position:
    position_id: int
    order_id: int
    side: Side
    entry_price: float
    fill_price: float
    stop_loss: float
    take_profit: float
    lots: float
    open_time: datetime
    confidence: str
    bias: str
    risk_amount: float
    tp1: Optional[float] = None
    tp2: Optional[float] = None
    tp3: Optional[float] = None
    tp1_hit: bool = False
    tp2_hit: bool = False
    tp3_hit: bool = False
    realised_pnl: float = 0.0
    initial_lots: float = 0.0
    initial_sl: Optional[float] = None
    session_id: str = ""
    reason: str = ""
    strategy_blob: Optional[str] = None
    execution_mode: str = "live"
    slippage_model: str = "random_uniform"
    slippage_points_applied: float = 0.0

    @property
    def parsed_strategy(self) -> dict:
        if not self.strategy_blob:
            return {}
        try:
            import json
            data = json.loads(self.strategy_blob)
            if isinstance(data, dict):
                return data.get("data", data)
            return {}
        except Exception:
            return {}

    unrealised_pnl: float = 0.0
    current_price: float = 0.0

    @classmethod
    def from_db_row(cls, row: sqlite3.Row) -> Position:
        return cls(
            position_id=row["position_id"],
            order_id=row["order_id"],
            side=Side(row["side"]),
            entry_price=row["entry_price"],
            fill_price=row["fill_price"],
            stop_loss=row["stop_loss"],
            take_profit=row["take_profit"],
            lots=row["lots"],
            open_time=datetime.fromisoformat(row["open_time"]),
            confidence=row["confidence"],
            bias=row["bias"],
            risk_amount=row["risk_amount"],
            tp1=row["tp1"] if "tp1" in row.keys() else None,
            tp2=row["tp2"] if "tp2" in row.keys() else None,
            tp3=row["tp3"] if "tp3" in row.keys() else None,
            tp1_hit=bool(row["tp1_hit"]) if "tp1_hit" in row.keys() and row["tp1_hit"] is not None else False,
            tp2_hit=bool(row["tp2_hit"]) if "tp2_hit" in row.keys() and row["tp2_hit"] is not None else False,
            tp3_hit=bool(row["tp3_hit"]) if "tp3_hit" in row.keys() and row["tp3_hit"] is not None else False,
            realised_pnl=row["realised_pnl"] if "realised_pnl" in row.keys() and row["realised_pnl"] is not None else 0.0,
            initial_lots=row["initial_lots"] if "initial_lots" in row.keys() and row["initial_lots"] is not None else (row["lots"] if "lots" in row.keys() else 0.0),
            initial_sl=row["initial_sl"] if "initial_sl" in row.keys() else None,
            session_id=row["session_id"],
            reason=row["reason"],
            unrealised_pnl=row["unrealised_pnl"] if "unrealised_pnl" in row.keys() and row["unrealised_pnl"] is not None else 0.0,
            current_price=row["current_price"] if "current_price" in row.keys() and row["current_price"] is not None else 0.0,
            strategy_blob=row["strategy_blob"] if "strategy_blob" in row.keys() else None,
            execution_mode=row["execution_mode"] if "execution_mode" in row.keys() and row["execution_mode"] else "live",
            slippage_model=row["slippage_model"] if "slippage_model" in row.keys() and row["slippage_model"] else "random_uniform",
            slippage_points_applied=row["slippage_points_applied"] if "slippage_points_applied" in row.keys() and row["slippage_points_applied"] is not None else 0.0
        )

    def update_pnl(self, price: float, lot_size: int = 100) -> None:
        self.current_price = price
        if self.side == Side.LONG:
            self.unrealised_pnl = (price - self.fill_price) * self.lots * lot_size
        else:
            self.unrealised_pnl = (self.fill_price - price) * self.lots * lot_size

    def check_sl_tp(self, price: float) -> Optional[ExitReason]:
        if self.side == Side.LONG:
            if price <= self.stop_loss:
                return ExitReason.SL_HIT
            if price >= self.take_profit:
                return ExitReason.TP_HIT
        else:
            if price >= self.stop_loss:
                return ExitReason.SL_HIT
            if price <= self.take_profit:
                return ExitReason.TP_HIT
        return None

@dataclass
class ClosedTrade:
    trade_id: int
    order_id: int
    position_id: int
    side: Side
    entry_price: float
    fill_price: float
    stop_loss: float
    take_profit: float
    exit_price: float
    lots: float
    open_time: datetime
    close_time: datetime
    exit_reason: ExitReason
    gross_pnl: float
    commission: float
    net_pnl: float
    risk_amount: float
    rr_achieved: float
    confidence: str
    bias: str
    balance_after: float
    tp1: Optional[float] = None
    tp2: Optional[float] = None
    tp3: Optional[float] = None
    session_id: str = ""
    reason: str = ""
    strategy_blob: Optional[str] = None
    execution_mode: str = "live"
    slippage_model: str = "random_uniform"
    slippage_points_applied: float = 0.0

    @property
    def parsed_strategy(self) -> dict:
        if not self.strategy_blob:
            return {}
        try:
            import json
            data = json.loads(self.strategy_blob)
            if isinstance(data, dict):
                return data.get("data", data)
            log.warning(f"Strategy blob is not a JSON object. Raw: {self.strategy_blob}")
            return {}
        except Exception as e:
            log.error(f"Malformed strategy_blob JSON detected. Exception: {e}", exc_info=True)
            return {}

    @classmethod
    def from_db_row(cls, row: sqlite3.Row) -> ClosedTrade:
        return cls(
            trade_id=row["trade_id"],
            order_id=row["order_id"],
            position_id=row["position_id"],
            side=Side(row["side"]),
            entry_price=row["entry_price"],
            fill_price=row["fill_price"],
            stop_loss=row["stop_loss"],
            take_profit=row["take_profit"],
            exit_price=row["exit_price"],
            lots=row["lots"],
            open_time=datetime.fromisoformat(row["open_time"]),
            close_time=datetime.fromisoformat(row["close_time"]),
            exit_reason=ExitReason(row["exit_reason"]),
            gross_pnl=row["gross_pnl"],
            commission=row["commission"],
            net_pnl=row["net_pnl"],
            risk_amount=row["risk_amount"],
            rr_achieved=row["rr_achieved"],
            confidence=row["confidence"],
            bias=row["bias"],
            balance_after=row["balance_after"],
            tp1=row["tp1"] if "tp1" in row.keys() else None,
            tp2=row["tp2"] if "tp2" in row.keys() else None,
            tp3=row["tp3"] if "tp3" in row.keys() else None,
            session_id=row["session_id"],
            reason=row["reason"],
            strategy_blob=row["strategy_blob"] if "strategy_blob" in row.keys() else None,
            execution_mode=row["execution_mode"] if "execution_mode" in row.keys() and row["execution_mode"] else "live",
            slippage_model=row["slippage_model"] if "slippage_model" in row.keys() and row["slippage_model"] else "random_uniform",
            slippage_points_applied=row["slippage_points_applied"] if "slippage_points_applied" in row.keys() and row["slippage_points_applied"] is not None else 0.0
        )

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
    order_id: int
    side: Side
    requested_price: float
    lots: float
    confidence: str
    rejection_reason: str
    timestamp: datetime
    session_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["side"] = self.side.value
        d["timestamp"] = self.timestamp.isoformat()
        return d

def make_event(event_type: str, timestamp: Optional[datetime] = None, **kwargs) -> Dict[str, Any]:
    event = {
        "type": event_type,
        "timestamp": (timestamp or datetime.now(timezone.utc)).isoformat(),
    }
    for k, v in kwargs.items():
        if isinstance(v, datetime):
            event[k] = v.isoformat()
        elif isinstance(v, Enum):
            event[k] = v.value
        else:
            event[k] = v
    return event
