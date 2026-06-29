"""
dependencies.py -- FastAPI Dependency Injection
"""

from core.database import Database
from core.event_bus import EventBus
from core.clock import ClockService

class AppState:
    db: Database
    event_bus: EventBus
    clock: ClockService
    
    # Active engine instances (SessionManager or ReplayEngine)
    current_engine = None 

app_state = AppState()

def get_db() -> Database:
    return app_state.db

def get_event_bus() -> EventBus:
    return app_state.event_bus

def get_clock() -> ClockService:
    return app_state.clock

def get_app_state() -> AppState:
    return app_state
