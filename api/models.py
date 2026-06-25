from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class SignalUpdate(BaseModel):
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp")
    price: float = Field(..., description="Current price")
    direction: str = Field(..., description="LONG, SHORT, or FLAT")
    signals: Dict[str, Any] = Field(default_factory=dict, description="Technical indicator signals")
    row_count: int = Field(default=0, description="Total rows processed")

class Trade(BaseModel):
    id: Optional[int] = None
    timestamp: str
    action: str
    price: float
    size: float
    pnl: Optional[float] = 0.0

class Metrics(BaseModel):
    balance: float
    win_rate: float
    total_trades: int
    open_pnl: float

class Settings(BaseModel):
    risk_per_trade_pct: float = Field(default=0.01)
    max_daily_drawdown: float = Field(default=300.0)
    telegram_alerts: bool = Field(default=True)
    auto_trading: bool = Field(default=False)

class LogEntry(BaseModel):
    id: Optional[int] = None
    timestamp: str
    level: str
    message: str

class Candle(BaseModel):
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = 0.0

class AlertRule(BaseModel):
    id: Optional[int] = None
    condition: str  # e.g., 'price_above', 'price_below'
    value: float
    is_active: bool = True

class ActivePosition(BaseModel):
    position_id: int
    order_id: str
    side: str
    entry_price: float
    lots: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    open_time: str
    unrealised_pnl: float = 0.0

class BrokerEvent(BaseModel):
    type: str
    payload: Dict[str, Any]
