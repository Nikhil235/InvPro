"""
app.py -- FastAPI application and lifespan management.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.database import Database
from core.event_bus import EventBus
from core.clock import ClockService
from api.routes import router
from api.ws import ws_router, setup_ws_broadcaster
from api.dependencies import app_state
from api.server import legacy_router
from utils.logger import get_logger

log = get_logger("api")

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting up API...")
    
    app_state.db = Database()
    app_state.db.migrate()
    app_state.event_bus = EventBus()
    app_state.clock = ClockService(mode="live")
    
    app.state.ws_broadcaster = setup_ws_broadcaster(app_state.event_bus)
    
    # Start background news ingestor
    from core.news_ingestor import NewsIngestor
    from api.store import store
    app_state.news_ingestor = NewsIngestor(app_state.db, app_state.event_bus, settings_getter=store.get_settings)
    await app_state.news_ingestor.start()
    
    yield
    
    log.info("Shutting down API...")
    if hasattr(app_state, "news_ingestor") and app_state.news_ingestor:
        try:
            await app_state.news_ingestor.stop()
        except Exception:
            pass
    if hasattr(app.state, "ws_broadcaster"):
        app.state.ws_broadcaster.cancel()
    if hasattr(app_state, 'current_engine') and app_state.current_engine:
        try:
            import asyncio
            asyncio.create_task(app_state.current_engine.stop())
        except:
            pass

app = FastAPI(title="InvPro Trading Simulator", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
app.include_router(ws_router, prefix="/ws")
app.include_router(legacy_router)
