"""
account_ledger.py -- Tracks balance, equity, margin, and drawdown with DB persistence.
"""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List

from core.database import Database
from core.clock import ClockService
from core.events import ACCOUNT_SNAPSHOT
from core.event_bus import EventBus
from utils.logger import get_logger

log = get_logger("account_ledger")

@dataclass
class AccountSnapshot:
    timestamp: datetime
    balance: float
    equity: float
    unrealised_pnl: float
    margin_used: float
    peak_equity: float
    drawdown_abs: float
    drawdown_pct: float
    open_positions: int
    session_id: str

    def to_db_dict(self):
        d = asdict(self)
        d['timestamp'] = self.timestamp.isoformat()
        return d


class AccountLedger:
    """Tracks balance, equity, margin, drawdown with DB persistence."""
    
    def __init__(self, db: Database, clock: ClockService, event_bus: EventBus, session_id: str, initial_capital: float):
        self._db = db
        self._clock = clock
        self._event_bus = event_bus
        self._session_id = session_id
        
        self._balance = initial_capital
        self._unrealised_pnl = 0.0
        self._margin_used = 0.0
        self._peak_equity = initial_capital
        self._peak_equity_today = initial_capital
        
        from datetime import timezone, timedelta
        self._ist_tz = timezone(timedelta(hours=5, minutes=30))
        self._current_trading_day = clock.now().astimezone(self._ist_tz).date()
        self._last_db_snapshot = 0.0
        self._open_positions_count = 0
        
        self._load_state()
        self._persist_to_db()

    def _load_state(self):
        row = self._db.fetchone("SELECT * FROM ledger WHERE session_id = ? ORDER BY timestamp DESC LIMIT 1", (self._session_id,))
        if row:
            self._balance = row["balance"]
            self._unrealised_pnl = row["unrealised_pnl"]
            self._margin_used = row["margin_used"]
            self._peak_equity = row["peak_equity"]
            self._open_positions_count = row["open_positions"]
            
            try:
                from datetime import datetime, timezone
                last_ts = datetime.fromisoformat(row["timestamp"])
                if last_ts.tzinfo is None:
                    last_ts = last_ts.replace(tzinfo=timezone.utc)
                
                last_ts_ist = last_ts.astimezone(self._ist_tz)
                    
                # Strict rollover using single captured startup date in IST
                if last_ts_ist.date() == self._current_trading_day:
                    self._peak_equity_today = row["peak_equity"]
                else:
                    self._peak_equity_today = self.equity
            except Exception as e:
                log.warning(f"Failed to parse ledger timestamp '{row['timestamp']}': {e}. Defaulting to current equity for today's peak.")
                self._peak_equity_today = self.equity
                
            log.info(f"Loaded ledger state: Balance ${self._balance:.2f}, Equity ${self.equity:.2f}, Peak Today ${self._peak_equity_today:.2f}")

    def debit(self, amount: float, reason: str) -> None:
        """Subtract from balance (e.g., loss, commission)."""
        self._balance -= amount
        log.debug(f"Debit {amount:.2f} ({reason}), new balance: {self._balance:.2f}")

    def credit(self, amount: float, reason: str) -> None:
        """Add to balance (e.g., profit)."""
        self._balance += amount
        log.debug(f"Credit {amount:.2f} ({reason}), new balance: {self._balance:.2f}")

    def update_equity(self, unrealised_pnl: float, open_count: int, margin_used: float = 0.0) -> None:
        """Update floating values based on open positions."""
        self._unrealised_pnl = unrealised_pnl
        self._open_positions_count = open_count
        self._margin_used = margin_used
        
        current_equity = self.equity
        if current_equity > self._peak_equity:
            self._peak_equity = current_equity
            
        now_date = self._clock.now().astimezone(self._ist_tz).date()
        if not hasattr(self, '_current_trading_day') or self._current_trading_day != now_date:
            self._current_trading_day = now_date
            self._peak_equity_today = current_equity
            
        if current_equity > self._peak_equity_today:
            self._peak_equity_today = current_equity
            
        # Publish real-time event to EventBus for the UI
        self._event_bus.publish(ACCOUNT_SNAPSHOT, {
            "type": ACCOUNT_SNAPSHOT,
            "timestamp": self._clock.now().isoformat(),
            "balance": self.balance,
            "equity": self.equity,
            "margin_used": self._margin_used,
            "drawdown_pct": self.drawdown_pct,
            "peak": self._peak_equity_today,
            "drawdown_abs": self.drawdown_abs,
            "session_id": self._session_id
        })
        
        # Persist to SQLite on every update for crash safety (WAL mode absorbs the IO)
        self._persist_to_db()

    def _persist_to_db(self) -> AccountSnapshot:
        """Persist current state to DB."""
        snapshot = AccountSnapshot(
            timestamp=self._clock.now(),
            balance=self.balance,
            equity=self.equity,
            unrealised_pnl=self._unrealised_pnl,
            margin_used=self._margin_used,
            peak_equity=self._peak_equity_today,
            drawdown_abs=self.drawdown_abs,
            drawdown_pct=self.drawdown_pct,
            open_positions=self._open_positions_count,
            session_id=self._session_id
        )
        
        sql = """
            INSERT INTO ledger (
                timestamp, balance, equity, unrealised_pnl, margin_used, 
                peak_equity, drawdown_abs, drawdown_pct, open_positions, session_id
            ) VALUES (
                :timestamp, :balance, :equity, :unrealised_pnl, :margin_used,
                :peak_equity, :drawdown_abs, :drawdown_pct, :open_positions, :session_id
            )
        """
        self._db.execute(sql, snapshot.to_db_dict())
        
        return snapshot

    def get_history(self) -> List[AccountSnapshot]:
        sql = "SELECT * FROM ledger WHERE session_id = ? ORDER BY timestamp ASC"
        rows = self._db.fetchall(sql, (self._session_id,))
        return [
            AccountSnapshot(
                timestamp=datetime.fromisoformat(row['timestamp']),
                balance=row['balance'],
                equity=row['equity'],
                unrealised_pnl=row['unrealised_pnl'],
                margin_used=row['margin_used'],
                peak_equity=row['peak_equity'],
                drawdown_abs=row['drawdown_abs'],
                drawdown_pct=row['drawdown_pct'],
                open_positions=row['open_positions'],
                session_id=row['session_id']
            ) for row in rows
        ]

    @property
    def balance(self) -> float:
        return self._balance

    @property
    def equity(self) -> float:
        return self._balance + self._unrealised_pnl

    @property
    def peak_equity(self) -> float:
        return self._peak_equity_today
        
    @property
    def drawdown_abs(self) -> float:
        dd = self._peak_equity_today - self.equity
        return max(0.0, dd)

    @property
    def drawdown_pct(self) -> float:
        if self._peak_equity_today <= 0:
            return 0.0
        return self.drawdown_abs / self._peak_equity_today
