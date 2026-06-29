"""
session_manager.py -- Wraps GoldScraper with expiry detection and health monitoring.
"""

from enum import Enum
from typing import Optional, Dict
from datetime import datetime
import asyncio
import json

from core.scraper import GoldScraper
from core.clock import ClockService
from core.event_bus import EventBus
from core.database import Database
from core.events import SESSION_STATUS
from utils.logger import get_logger

log = get_logger("session_mgr")

class SessionState(Enum):
    IDLE = "idle"
    STARTING = "starting"
    AUTHENTICATED = "authenticated"
    SCRAPING = "scraping"
    EXPIRED = "expired"
    RECONNECTING = "reconnecting"
    ERROR = "error"

class SessionManager:
    """Wraps GoldScraper with expiry detection, health monitoring, and auto-recovery."""
    
    def __init__(self, clock: ClockService, event_bus: EventBus, db: Database, session_id: str, mode: str = "live", initial_capital: float = 10000.0) -> None:
        self._clock = clock
        self._event_bus = event_bus
        self._db = db
        self._session_id = session_id
        self._mode = mode
        
        self._scraper = GoldScraper()
        self._state = SessionState.IDLE
        self._last_successful_scrape: Optional[datetime] = None
        self._consecutive_failures = 0
        self._start_time: Optional[datetime] = None
        
        # Initialize session in DB
        self._db.execute("""
            INSERT INTO sessions (session_id, mode, started_at, initial_capital, status)
            VALUES (?, ?, ?, ?, ?)
        """, (self._session_id, self._mode, self._clock.now().isoformat(), initial_capital, 'active'))

    async def start(self) -> None:
        self._set_state(SessionState.STARTING)
        self._start_time = self._clock.now()
        
        try:
            self._scraper.start()
            self._set_state(SessionState.AUTHENTICATED)
        except Exception as e:
            log.error(f"Failed to start scraper: {e}")
            self._set_state(SessionState.ERROR)

    async def stop(self) -> None:
        self._scraper.stop()
        self._set_state(SessionState.IDLE)
        self._db.execute("UPDATE sessions SET ended_at = ?, status = 'completed' WHERE session_id = ?", (self._clock.now().isoformat(), self._session_id))

    def _set_state(self, new_state: SessionState) -> None:
        if self._state != new_state:
            self._state = new_state
            self._event_bus.publish(SESSION_STATUS, {
                "state": self._state.value,
                "uptime": self.uptime_seconds,
                "last_scrape": self._last_successful_scrape.isoformat() if self._last_successful_scrape else None,
                "error": None if self._state != SessionState.ERROR else "Session error",
                "session_id": self._session_id
            })

    async def scrape_tick(self) -> Optional[Dict]:
        if self._state in (SessionState.ERROR, SessionState.IDLE):
            return None
            
        try:
            raw_data = self._scraper.read_snapshot()
            
            if await self._check_expiry():
                self._set_state(SessionState.EXPIRED)
                await self._attempt_recovery()
                return None
                
            self._last_successful_scrape = self._clock.now()
            self._consecutive_failures = 0
            
            if self._state != SessionState.SCRAPING:
                self._set_state(SessionState.SCRAPING)
                
            return raw_data
            
        except Exception as e:
            self._consecutive_failures += 1
            log.warning(f"Scrape failed ({self._consecutive_failures} consecutive): {e}")
            
            if self._consecutive_failures >= 5:
                self._set_state(SessionState.RECONNECTING)
                success = await self._attempt_recovery()
                if not success:
                    self._set_state(SessionState.ERROR)
            
            return None

    async def _check_expiry(self) -> bool:
        # Check if InvestingPro session is locked, but at most once per 60 seconds
        import time
        now = time.time()
        last_check = getattr(self, '_last_expiry_check_time', 0.0)
        if now - last_check < 60.0:
            return False
            
        self._last_expiry_check_time = now
        try:
            if hasattr(self._scraper, '_is_pro_locked') and self._scraper._is_pro_locked():
                return True
        except Exception:
            pass
        return False

    async def _attempt_recovery(self) -> bool:
        log.info("Attempting session recovery...")
        try:
            self._scraper.force_reload()
            await asyncio.sleep(5)
            # Try a test scrape
            self._scraper.read_snapshot()
            self._set_state(SessionState.SCRAPING)
            self._consecutive_failures = 0
            log.info("Session recovery successful")
            return True
        except Exception as e:
            log.error(f"Reload failed: {e}")
            
        # Try full restart
        try:
            log.info("Attempting full browser restart...")
            self._scraper.stop()
            await asyncio.sleep(2)
            self._scraper.start()
            self._set_state(SessionState.SCRAPING)
            self._consecutive_failures = 0
            log.info("Full restart successful")
            return True
        except Exception as e:
            log.error(f"Full restart failed: {e}")
            return False

    @property
    def state(self) -> SessionState:
        return self._state

    @property
    def last_successful_scrape(self) -> Optional[datetime]:
        return self._last_successful_scrape

    @property
    def uptime_seconds(self) -> float:
        if not self._start_time:
            return 0.0
        return (self._clock.now() - self._start_time).total_seconds()

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures
