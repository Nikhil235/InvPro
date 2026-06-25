import sqlite3
import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import os

from .models import SignalUpdate, Trade, Metrics, Settings, LogEntry, Candle, AlertRule, ActivePosition, BrokerEvent

DB_PATH = "trading_state.db"

class Store:
    def __init__(self):
        self._current_signal: Optional[SignalUpdate] = None
        self._metrics: Metrics = Metrics(balance=10000.0, win_rate=0.0, total_trades=0, open_pnl=0.0)
        self._settings: Settings = Settings()
        self._triggered_alerts: List[str] = []
        self._active_positions: Dict[int, ActivePosition] = {}
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    action TEXT,
                    price REAL,
                    size REAL,
                    pnl REAL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    level TEXT,
                    message TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS candles (
                    time TEXT PRIMARY KEY,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume REAL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS alert_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    condition TEXT,
                    value REAL,
                    is_active INTEGER
                )
            """)
            conn.commit()

    def _aggregate_candle(self, timestamp: str, price: float):
        # timestamp format: "2026-06-25T13:30:22.123456+00:00" or similar
        # Extract the minute base string: "2026-06-25T13:30:00Z" (just as a consistent string)
        # Using string manipulation for simplicity since we want 1M candles
        try:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            dt_minute = dt.replace(second=0, microsecond=0)
            # Lightweight charts prefers YYYY-MM-DD string or unix timestamp.
            # We will store ISO strings, but the key is the minute.
            minute_str = dt_minute.isoformat()
            
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.execute("SELECT * FROM candles WHERE time = ?", (minute_str,))
                row = cursor.fetchone()
                
                if row:
                    new_high = max(row[2], price)
                    new_low = min(row[3], price)
                    conn.execute("""
                        UPDATE candles SET high = ?, low = ?, close = ? WHERE time = ?
                    """, (new_high, new_low, price, minute_str))
                else:
                    conn.execute("""
                        INSERT INTO candles (time, open, high, low, close, volume)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (minute_str, price, price, price, price, 0))
                conn.commit()
        except Exception as e:
            pass # Silently fail aggregation on malformed date

    def _evaluate_alerts(self, price: float):
        alerts_to_trigger = []
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM alert_rules WHERE is_active = 1")
            rules = cursor.fetchall()
            
            for rule in rules:
                rule_id = rule['id']
                condition = rule['condition']
                value = rule['value']
                triggered = False
                
                if condition == 'price_above' and price > value:
                    triggered = True
                elif condition == 'price_below' and price < value:
                    triggered = True
                    
                if triggered:
                    alerts_to_trigger.append(f"Alert triggered! {condition} {value} (Price: {price})")
                    # Disable to prevent spam
                    conn.execute("UPDATE alert_rules SET is_active = 0 WHERE id = ?", (rule_id,))
            
            conn.commit()
            
        if alerts_to_trigger:
            self._triggered_alerts.extend(alerts_to_trigger)

    def pop_triggered_alerts(self) -> List[str]:
        alerts = self._triggered_alerts[:]
        self._triggered_alerts = []
        return alerts

    def update_signal(self, signal: SignalUpdate):
        self._current_signal = signal
        if signal.price and signal.price > 0:
            self._aggregate_candle(signal.timestamp, signal.price)
            self._evaluate_alerts(signal.price)

    def get_current_signal(self) -> Optional[SignalUpdate]:
        return self._current_signal

    def add_trade(self, trade: Trade):
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute("""
                INSERT INTO trades (timestamp, action, price, size, pnl)
                VALUES (?, ?, ?, ?, ?)
            """, (trade.timestamp, trade.action, trade.price, trade.size, trade.pnl))
            trade.id = cursor.lastrowid
            conn.commit()

    def get_trades(self, limit: int = 50, offset: int = 0) -> List[Trade]:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset))
            rows = cursor.fetchall()
            return [Trade(**dict(row)) for row in rows]

    def get_active_positions(self) -> List[ActivePosition]:
        return list(self._active_positions.values())

    def process_broker_event(self, event: BrokerEvent):
        payload = event.payload
        if event.type == "ORDER_FILLED":
            pos = ActivePosition(
                position_id=payload.get("position_id"),
                order_id=str(payload.get("order_id")),
                side=payload.get("side", {}).get("value", payload.get("side")) if isinstance(payload.get("side"), dict) else str(payload.get("side")),
                entry_price=payload.get("fill_price"),
                lots=payload.get("lots"),
                stop_loss=payload.get("stop_loss"),
                take_profit=payload.get("take_profit"),
                open_time=datetime.now(timezone.utc).isoformat(),
                unrealised_pnl=0.0
            )
            self._active_positions[pos.position_id] = pos
            
        elif event.type == "TRADE_CLOSED":
            pos_id = payload.get("position_id")
            if pos_id in self._active_positions:
                del self._active_positions[pos_id]
            
            # Record trade
            side_val = payload.get("side", {}).get("value", payload.get("side")) if isinstance(payload.get("side"), dict) else str(payload.get("side"))
            trade = Trade(
                timestamp=datetime.now(timezone.utc).isoformat(),
                action=side_val,
                price=payload.get("exit_price", payload.get("fill_price", 0.0)),
                size=payload.get("lots", 0.0), # might not be in payload, we could fall back
                pnl=payload.get("net_pnl", 0.0)
            )
            # Fetch size from active pos if available
            self.add_trade(trade)
            
            # Update metrics
            self._metrics.balance = payload.get("balance_after", self._metrics.balance)
            self._metrics.total_trades += 1
            if trade.pnl and trade.pnl > 0:
                # Approximate win rate (we don't have total wins stored, so we just do a rough moving average or skip precise win_rate for now)
                pass

        elif event.type == "POSITION_UPDATE":
            for p_data in payload.get("positions", []):
                pid = p_data.get("position_id")
                if pid in self._active_positions:
                    self._active_positions[pid].unrealised_pnl = p_data.get("unrealised_pnl", 0.0)
            self._metrics.open_pnl = payload.get("total_unrealised_pnl", 0.0)

    def update_metrics(self, metrics: Metrics):
        self._metrics = metrics

    def get_metrics(self) -> Metrics:
        return self._metrics

    def add_log(self, log: LogEntry):
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute("""
                INSERT INTO logs (timestamp, level, message)
                VALUES (?, ?, ?)
            """, (log.timestamp, log.level, log.message))
            log.id = cursor.lastrowid
            conn.commit()

    def get_logs(self, limit: int = 100, offset: int = 0) -> List[LogEntry]:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM logs ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset))
            rows = cursor.fetchall()
            return [LogEntry(**dict(row)) for row in rows]

    def get_candles(self, limit: int = 500) -> List[Candle]:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            # Lightweight charts needs chronological order (oldest to newest)
            cursor = conn.execute("SELECT * FROM (SELECT * FROM candles ORDER BY time DESC LIMIT ?) ORDER BY time ASC", (limit,))
            rows = cursor.fetchall()
            return [Candle(**dict(row)) for row in rows]

    def add_alert_rule(self, rule: AlertRule):
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute("""
                INSERT INTO alert_rules (condition, value, is_active)
                VALUES (?, ?, ?)
            """, (rule.condition, rule.value, 1 if rule.is_active else 0))
            rule.id = cursor.lastrowid
            conn.commit()

    def get_alert_rules(self) -> List[AlertRule]:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM alert_rules ORDER BY id DESC")
            rows = cursor.fetchall()
            return [AlertRule(**dict(row)) for row in rows]

    def delete_alert_rule(self, rule_id: int):
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM alert_rules WHERE id = ?", (rule_id,))
            conn.commit()

    def update_settings(self, settings: Settings):
        self._settings = settings

    def get_settings(self) -> Settings:
        return self._settings

# Global store instance
store = Store()
