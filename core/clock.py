"""
clock.py -- UTC-safe time service for live and replay modes.
"""

from datetime import datetime, timezone, timedelta
from typing import Literal

class ClockService:
    """
    UTC-safe time provider. In LIVE mode, returns datetime.now(UTC).
    In REPLAY mode, returns the timestamp of the current replayed row.
    """
    
    def __init__(self, mode: Literal["live", "replay"] = "live") -> None:
        self._mode = mode
        self._replay_time: datetime = datetime.now(timezone.utc)
        
    def now(self) -> datetime:
        """Always returns a UTC-aware datetime."""
        if self._mode == "live":
            return datetime.now(timezone.utc)
        return self._replay_time
        
    def set_replay_time(self, ts: datetime) -> None:
        """Update the internal clock during replay mode."""
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        self._replay_time = ts
        
    def elapsed_since(self, ts: datetime) -> timedelta:
        """Calculate timedelta since a given timestamp."""
        return self.now() - ts
        
    @property
    def mode(self) -> str:
        return self._mode
