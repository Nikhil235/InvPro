import sqlite3
import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import os
import contextlib
import logging

logger = logging.getLogger("store")

from .models import SignalUpdate, Trade, Metrics, Settings, LogEntry, Candle, AlertRule, ActivePosition, BrokerEvent, PendingOrder, AccountState

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
        with contextlib.closing(sqlite3.connect(DB_PATH, timeout=30.0)) as conn:
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
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pending_orders (
                    order_id INTEGER PRIMARY KEY,
                    type TEXT,
                    side TEXT,
                    requested_price REAL,
                    lots REAL,
                    stop_loss REAL,
                    take_profit REAL,
                    status TEXT,
                    created_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS account_state (
                    timestamp TEXT PRIMARY KEY,
                    balance REAL,
                    equity REAL,
                    peak_equity REAL,
                    drawdown_pct REAL
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
            
            with contextlib.closing(sqlite3.connect(DB_PATH, timeout=30.0)) as conn:
                cursor = conn.execute("SELECT * FROM candles WHERE time = ?", (minute_str,))
                row = cursor.fetchone()
                
                if row:
                    new_high = max(row[2], price)
                    new_low = min(row[3], price)
                    conn.execute("""
                        UPDATE candles SET high = ?, low = ?, close = ?, tick_count = tick_count + 1 WHERE time = ?
                    """, (new_high, new_low, price, minute_str))
                else:
                    conn.execute("""
                        INSERT INTO candles (time, open, high, low, close, tick_count)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (minute_str, price, price, price, price, 1))
                conn.commit()
        except Exception as e:
            print(f"Error aggregating candle: {e}")

    def _evaluate_alerts(self, price: float):
        alerts_to_trigger = []
        with contextlib.closing(sqlite3.connect(DB_PATH, timeout=30.0)) as conn:
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
        with contextlib.closing(sqlite3.connect(DB_PATH, timeout=30.0)) as conn:
            try:
                cursor = conn.execute("""
                    INSERT INTO trades (timestamp, action, price, size, pnl)
                    VALUES (?, ?, ?, ?, ?)
                """, (trade.timestamp, trade.action, trade.price, trade.size, trade.pnl))
                trade.id = cursor.lastrowid
                conn.commit()
            except sqlite3.OperationalError as e:
                logger.warning(f"add_trade skipped legacy insert (database table has paper-trading schema): {e}")

    def get_trades(self, limit: int = 50, offset: int = 0) -> List[Trade]:
        with contextlib.closing(sqlite3.connect(DB_PATH, timeout=30.0)) as conn:
            conn.row_factory = sqlite3.Row
            try:
                cursor = conn.execute("SELECT * FROM trades ORDER BY trade_id DESC LIMIT ? OFFSET ?", (limit, offset))
                rows = cursor.fetchall()
                return [Trade(
                    id=row["trade_id"],
                    timestamp=row["close_time"],
                    action=row["side"],
                    price=row["entry_price"],
                    size=row["lots"],
                    pnl=row["net_pnl"] if "net_pnl" in list(row.keys()) else (row["pnl"] if "pnl" in list(row.keys()) else 0.0)
                ) for row in rows]
            except sqlite3.OperationalError:
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
                unrealised_pnl=0.0,
                tp1=payload.get("tp1"),
                tp2=payload.get("tp2"),
                tp3=payload.get("tp3"),
                tp1_hit=bool(payload.get("tp1_hit", 0)),
                tp2_hit=bool(payload.get("tp2_hit", 0)),
                tp3_hit=bool(payload.get("tp3_hit", 0)),
                realised_pnl=payload.get("realised_pnl", 0.0),
                initial_lots=payload.get("initial_lots", payload.get("lots", 0.0))
            )
            self._active_positions[pos.position_id] = pos
            
            # Remove from pending if it was there
            store.delete_pending_order(payload.get("order_id"))
            
        elif event.type == "ORDER_PENDING":
            pending = PendingOrder(
                order_id=payload.get("order_id"),
                type=payload.get("order_type", "LIMIT"),
                side=payload.get("side", {}).get("value", payload.get("side")) if isinstance(payload.get("side"), dict) else str(payload.get("side")),
                requested_price=payload.get("requested_price"),
                lots=payload.get("lots"),
                stop_loss=payload.get("stop_loss"),
                take_profit=payload.get("take_profit"),
                status="PENDING",
                created_at=datetime.now(timezone.utc).isoformat()
            )
            self.add_pending_order(pending)

        elif event.type == "ORDER_CANCELLED":
            self.delete_pending_order(payload.get("order_id"))
        elif event.type == "TRADE_CLOSED":
            pos_id = payload.get("position_id")
            # Only remove from active positions if it is a full close
            if payload.get("is_full_close", True) and pos_id in self._active_positions:
                del self._active_positions[pos_id]
            
            # Record trade
            side_val = payload.get("side", {}).get("value", payload.get("side")) if isinstance(payload.get("side"), dict) else str(payload.get("side"))
            trade = Trade(
                timestamp=datetime.now(timezone.utc).isoformat(),
                action=side_val,
                price=payload.get("exit_price", payload.get("fill_price", 0.0)),
                size=payload.get("lots", 0.0),
                pnl=payload.get("net_pnl", 0.0)
            )
            self.add_trade(trade)
            
            # Update metrics
            self._metrics.balance = payload.get("balance_after", self._metrics.balance)
            self._metrics.total_trades += 1
            if trade.pnl and trade.pnl > 0:
                pass

        elif event.type == "POSITION_UPDATE":
            for p_data in payload.get("positions", []):
                pid = p_data.get("position_id") or p_data.get("id")
                if pid in self._active_positions:
                    self._active_positions[pid].unrealised_pnl = p_data.get("unrealised_pnl", 0.0)
                    self._active_positions[pid].lots = p_data.get("lots", self._active_positions[pid].lots)
                    self._active_positions[pid].stop_loss = p_data.get("stop_loss", self._active_positions[pid].stop_loss)
                    self._active_positions[pid].tp1_hit = bool(p_data.get("tp1_hit", self._active_positions[pid].tp1_hit))
                    self._active_positions[pid].tp2_hit = bool(p_data.get("tp2_hit", self._active_positions[pid].tp2_hit))
                    self._active_positions[pid].tp3_hit = bool(p_data.get("tp3_hit", self._active_positions[pid].tp3_hit))
                    self._active_positions[pid].realised_pnl = p_data.get("realised_pnl", self._active_positions[pid].realised_pnl)
            self._metrics.open_pnl = payload.get("total_unrealised_pnl", 0.0)

        elif event.type == "ACCOUNT_STATE":
            state = AccountState(
                timestamp=payload.get("timestamp"),
                balance=payload.get("balance"),
                equity=payload.get("equity"),
                peak_equity=payload.get("peak_equity"),
                drawdown_pct=payload.get("drawdown_pct")
            )
            self.record_account_state(state)

    def update_metrics(self, metrics: Metrics):
        self._metrics = metrics

    def get_metrics(self) -> Metrics:
        return self._metrics

    def add_log(self, log: LogEntry):
        with contextlib.closing(sqlite3.connect(DB_PATH, timeout=30.0)) as conn:
            cursor = conn.execute("""
                INSERT INTO logs (timestamp, level, message)
                VALUES (?, ?, ?)
            """, (log.timestamp, log.level, log.message))
            log.id = cursor.lastrowid
            conn.commit()

    def get_logs(self, limit: int = 100, offset: int = 0) -> List[LogEntry]:
        with contextlib.closing(sqlite3.connect(DB_PATH, timeout=30.0)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM logs ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset))
            rows = cursor.fetchall()
            return [LogEntry(**dict(row)) for row in rows]

    def get_candles(self, limit: int = 500) -> List[Candle]:
        with contextlib.closing(sqlite3.connect(DB_PATH, timeout=30.0)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM (SELECT * FROM candles ORDER BY time DESC LIMIT ?) ORDER BY time ASC", (limit,))
            rows = cursor.fetchall()
            return [Candle(
                time=row['time'],
                open=row['open'],
                high=row['high'],
                low=row['low'],
                close=row['close'],
                volume=row['tick_count']
            ) for row in rows]

    def add_alert_rule(self, rule: AlertRule):
        with contextlib.closing(sqlite3.connect(DB_PATH, timeout=30.0)) as conn:
            cursor = conn.execute("""
                INSERT INTO alert_rules (condition, value, is_active)
                VALUES (?, ?, ?)
            """, (rule.condition, rule.value, 1 if rule.is_active else 0))
            rule.id = cursor.lastrowid
            conn.commit()

    def get_alert_rules(self) -> List[AlertRule]:
        with contextlib.closing(sqlite3.connect(DB_PATH, timeout=30.0)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM alert_rules ORDER BY id DESC")
            rows = cursor.fetchall()
            return [AlertRule(**dict(row)) for row in rows]

    def delete_alert_rule(self, rule_id: int):
        with contextlib.closing(sqlite3.connect(DB_PATH, timeout=30.0)) as conn:
            conn.execute("DELETE FROM alert_rules WHERE id = ?", (rule_id,))
            conn.commit()

    def update_settings(self, settings: Settings):
        self._settings = settings

    def get_settings(self) -> Settings:
        return self._settings

    # Pending Orders
    def add_pending_order(self, order: PendingOrder):
        with contextlib.closing(sqlite3.connect(DB_PATH, timeout=30.0)) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO pending_orders (order_id, type, side, requested_price, lots, stop_loss, take_profit, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (order.order_id, order.type, order.side, order.requested_price, order.lots, order.stop_loss, order.take_profit, order.status, order.created_at))
            conn.commit()

    def get_pending_orders(self) -> List[PendingOrder]:
        with contextlib.closing(sqlite3.connect(DB_PATH, timeout=30.0)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM pending_orders WHERE status = 'PENDING' ORDER BY created_at ASC")
            rows = cursor.fetchall()
            return [PendingOrder(**dict(row)) for row in rows]

    def delete_pending_order(self, order_id: int):
        with contextlib.closing(sqlite3.connect(DB_PATH, timeout=30.0)) as conn:
            conn.execute("DELETE FROM pending_orders WHERE order_id = ?", (order_id,))
            conn.commit()

    # Account State
    def record_account_state(self, state: AccountState):
        with contextlib.closing(sqlite3.connect(DB_PATH, timeout=30.0)) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO account_state (timestamp, balance, equity, peak_equity, drawdown_pct)
                VALUES (?, ?, ?, ?, ?)
            """, (state.timestamp, state.balance, state.equity, state.peak_equity, state.drawdown_pct))
            conn.commit()

    def get_latest_account_state(self) -> Optional[AccountState]:
        with contextlib.closing(sqlite3.connect(DB_PATH, timeout=30.0)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM account_state ORDER BY timestamp DESC LIMIT 1")
            row = cursor.fetchone()
            return AccountState(**dict(row)) if row else None

# Global store instance
store = Store()
