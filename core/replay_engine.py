"""
replay_engine.py -- Replays historical data through the full execution pipeline.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Union, Optional, List, Dict
from datetime import datetime
import json

from core.clock import ClockService
from core.event_bus import EventBus
from core.database import Database
from core.events import TICK, REPLAY_PROGRESS, SESSION_STATUS
from paper_trading.core.paper_broker import PaperBroker
from core.strategy import TradingStrategy
from paper_trading.core.signal_router import SignalRouter
from utils.logger import get_logger

log = get_logger("replay")

class ReplayProgress:
    def __init__(self):
        self.current_row = 0
        self.total_rows = 0
        self.sim_time: Optional[datetime] = None

    @property
    def pct(self) -> float:
        if self.total_rows == 0:
            return 0.0
        return (self.current_row / self.total_rows) * 100

class ReplayEngine:
    """Replays historical data through the full execution pipeline."""
    
    def __init__(
        self,
        db: Database,
        clock: ClockService,
        event_bus: EventBus,
        broker: PaperBroker,
        strategy: TradingStrategy,
        router: SignalRouter,
        session_id: str,
        speed: float = 1.0,         # 1.0 = real-time, 0 = instant
    ) -> None:
        self._db = db
        self._clock = clock
        self._event_bus = event_bus
        self._broker = broker
        self._strategy = strategy
        self._router = router
        self._session_id = session_id
        
        self._speed = speed
        self._is_running = False
        self._is_paused = False
        self._progress = ReplayProgress()
        self._task: Optional[asyncio.Task] = None
        
        # We assume the source is the snapshots table in the DB.
        # If an Excel file needs to be imported, it should be done prior to instantiating this engine.
        self._rows: List[Dict] = []
        
        # Init session in DB
        self._db.execute("""
            INSERT INTO sessions (session_id, mode, started_at, initial_capital, status)
            VALUES (?, ?, ?, ?, ?)
        """, (self._session_id, 'replay', self._clock.now().isoformat(), self._broker._ledger._balance, 'active'))

    async def _load_data(self) -> None:
        # Load from snapshots table ordered by time
        rows = self._db.fetchall("SELECT * FROM snapshots ORDER BY timestamp ASC")
        self._rows = [dict(row) for row in rows]
        self._progress.total_rows = len(self._rows)
        log.info(f"Loaded {self._progress.total_rows} rows for replay")

    async def start(self) -> None:
        if self._is_running:
            return
            
        await self._load_data()
        
        self._is_running = True
        self._is_paused = False
        self._progress.current_row = 0
        
        self._event_bus.publish(SESSION_STATUS, {
            "state": "scraping",  # Pretend we are scraping for the UI
            "uptime": 0,
            "session_id": self._session_id,
            "mode": "replay"
        })
        
        # Start background task
        self._task = asyncio.create_task(self._run_loop())

    async def pause(self) -> None:
        self._is_paused = True

    async def resume(self) -> None:
        self._is_paused = False

    async def stop(self) -> None:
        self._is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._finalize()

    async def set_speed(self, multiplier: float) -> None:
        self._speed = multiplier

    async def _run_loop(self) -> None:
        try:
            while self._is_running and self._progress.current_row < self._progress.total_rows:
                if self._is_paused:
                    await asyncio.sleep(0.1)
                    continue
                    
                row = self._rows[self._progress.current_row]
                row_ts = datetime.fromisoformat(row['timestamp'])
                
                # Update clock
                self._clock.set_replay_time(row_ts)
                self._progress.sim_time = row_ts
                
                # Strategy evaluation needs the row to look like parser output
                parser_row = {
                    "Date-Time": row_ts,
                    "Price": row['price'],
                    "1 min": row.get('signal_1m', 'N/A'),
                    "5 min": row.get('signal_5m', 'N/A'),
                    "15 min": row.get('signal_15m', 'N/A'),
                    "30 min": row.get('signal_30m', 'N/A'),
                    "Hourly": row.get('signal_1h', 'N/A'),
                    "5 Hours": row.get('signal_5h', 'N/A'),
                    "Daily": row.get('signal_daily', 'N/A'),
                    "Weekly": row.get('signal_weekly', 'N/A'),
                    "Monthly": row.get('signal_monthly', 'N/A'),
                }
                
                # 1. Strategy
                strategy_signal = self._strategy.evaluate(parser_row)
                
                # 2. Broker Tick (process pending orders, SL/TP)
                self._broker.tick(row['price'], timestamp=row_ts)
                
                # 3. Router (process new signal)
                if strategy_signal:
                    self._router.process_signal(strategy_signal, row['price'], timestamp=row_ts)
                    
                # 4. Publish TICK event
                signals_dict = {k: v for k, v in parser_row.items() if k not in ("Date-Time", "Price")}
                self._event_bus.publish(TICK, {
                    "price": row['price'],
                    "timestamp": row_ts.isoformat(),
                    "signals": signals_dict,
                    "direction": strategy_signal.direction if strategy_signal else "FLAT"
                })
                
                self._progress.current_row += 1
                
                # Publish progress every 100 rows or at speed=0 (instant)
                if self._progress.current_row % 100 == 0 or self._progress.current_row == self._progress.total_rows:
                    self._event_bus.publish(REPLAY_PROGRESS, {
                        "current_row": self._progress.current_row,
                        "total_rows": self._progress.total_rows,
                        "pct": self._progress.pct,
                        "speed": self._speed,
                        "sim_time": row_ts.isoformat(),
                        "session_id": self._session_id
                    })
                
                if self._speed > 0:
                    # In real-time (speed=1.0), we would sleep the delta between rows.
                    # For simplicity in replay, we just sleep a small tick amount.
                    # Assume data is 5 seconds apart, so real-time means sleeping 5s.
                    # actual_sleep = 5.0 / self._speed
                    # We can use a fixed base sleep since the snapshots might not be exactly 5s apart.
                    
                    if self._progress.current_row < self._progress.total_rows:
                        next_row = self._rows[self._progress.current_row]
                        next_ts = datetime.fromisoformat(next_row['timestamp'])
                        time_delta = (next_ts - row_ts).total_seconds()
                        if time_delta > 0:
                            sleep_time = time_delta / self._speed
                            # Cap max sleep to avoid hanging on weekends
                            sleep_time = min(sleep_time, 2.0 / self._speed)
                            await asyncio.sleep(sleep_time)
                else:
                    # Instant replay
                    if self._progress.current_row % 1000 == 0:
                        await asyncio.sleep(0) # yield event loop

            # Replay complete
            log.info("Replay completed.")
            self._finalize()
            
        except asyncio.CancelledError:
            log.info("Replay cancelled.")
        except Exception as e:
            log.error(f"Replay error: {e}", exc_info=True)
            self._finalize(status="error")

    def _finalize(self, status: str = "completed"):
        self._is_running = False
        
        # Close all open positions at the end of the simulation
        if self._progress.current_row > 0 and self._rows:
            last_price = self._rows[self._progress.current_row - 1]['price']
            self._broker.close_all_positions(price=last_price, timestamp=self._clock.now())
            
        self._db.execute("UPDATE sessions SET ended_at = ?, status = ?, final_equity = ?, net_pnl = ? WHERE session_id = ?", 
            (self._clock.now().isoformat(), status, self._broker._ledger.equity, self._broker._ledger.equity - self._broker._ledger._balance, self._session_id))
            
        self._event_bus.publish(SESSION_STATUS, {
            "state": status,
            "uptime": 0,
            "session_id": self._session_id,
            "mode": "replay"
        })

    @property
    def progress(self) -> ReplayProgress:
        return self._progress

    @property
    def is_running(self) -> bool:
        return self._is_running
