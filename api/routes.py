"""
routes.py -- REST endpoints (session, trades, ledger).
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid

from api.dependencies import get_db, get_app_state, AppState
from core.database import Database
from core.session_manager import SessionManager
from core.replay_engine import ReplayEngine
from paper_trading.core.paper_broker import PaperBroker
from paper_trading.core.risk_manager import RiskManager
from paper_trading.core.account_ledger import AccountLedger
from paper_trading.core.signal_router import SignalRouter
from core.strategy import TradingStrategy

router = APIRouter()

class StartLiveRequest(BaseModel):
    initial_capital: float = 10000.0

class StartReplayRequest(BaseModel):
    initial_capital: float = 10000.0
    speed: float = 1.0

class InternalEvent(BaseModel):
    event_type: str
    payload: dict

@router.post("/internal/push_event")
async def internal_push_event(req: InternalEvent, state: AppState = Depends(get_app_state)):
    if req.event_type == "SESSION_STATUS":
        state.external_session_id = req.payload.get("session_id")
        state.external_session_state = req.payload.get("state")
    state.event_bus.publish(req.event_type, req.payload)
    return {"status": "ok"}

@router.post("/session/live/start")
async def start_live_session(req: StartLiveRequest, state: AppState = Depends(get_app_state)):
    if getattr(state, 'external_session_state', None) == "running" or (state.current_engine and getattr(state.current_engine, 'is_running', False)):
        raise HTTPException(status_code=400, detail="A session is already running")
        
    session_id = f"live_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    
    # Initialize DB record
    state.db.execute("""
        INSERT INTO sessions (session_id, mode, started_at, initial_capital, status)
        VALUES (?, ?, ?, ?, ?)
    """, (session_id, "live", state.clock.now().isoformat(), req.initial_capital, 'active'))
    
    state.external_session_id = session_id
    state.external_session_state = "running"
    
    return {"status": "success", "session_id": session_id, "mode": "live"}

@router.post("/session/replay/start")
async def start_replay_session(req: StartReplayRequest, state: AppState = Depends(get_app_state)):
    if state.current_engine and getattr(state.current_engine, 'is_running', False):
        raise HTTPException(status_code=400, detail="A session is already running")
        
    session_id = f"replay_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    
    state.clock._mode = "replay"
    
    ledger = AccountLedger(state.db, state.clock, state.event_bus, session_id, req.initial_capital)
    broker = PaperBroker(state.db, state.clock, state.event_bus, ledger, session_id)
    risk_mgr = RiskManager(state.clock, state.event_bus, ledger, session_id)
    signal_router = SignalRouter(broker, risk_mgr, state.event_bus)
    strategy = TradingStrategy()
    
    engine = ReplayEngine(state.db, state.clock, state.event_bus, broker, strategy, signal_router, session_id, req.speed)
    state.current_engine = engine
    
    await engine.start()
    return {"status": "success", "session_id": session_id, "mode": "replay"}

@router.post("/session/stop")
async def stop_session(state: AppState = Depends(get_app_state)):
    stopped = False
    
    # 1. Handle live dry-run session from DB/in-memory
    session_id = getattr(state, 'external_session_id', None)
    if not session_id:
        # Check DB for active live session
        row = state.db.fetchone("SELECT session_id FROM sessions WHERE status = 'active' AND mode = 'live' ORDER BY started_at DESC LIMIT 1")
        if row:
            session_id = row["session_id"]
            
    if session_id:
        state.db.execute(
            "UPDATE sessions SET status = 'completed', ended_at = ? WHERE session_id = ?",
            (state.clock.now().isoformat(), session_id)
        )
        state.external_session_state = "stopped"
        state.external_session_id = None
        state.clock._mode = "live"
        stopped = True

    # 2. Handle replay session stop
    if state.current_engine:
        await state.current_engine.stop()
        state.clock._mode = "live" # Reset clock
        state.current_engine = None
        stopped = True
        
    if not stopped:
        raise HTTPException(status_code=400, detail="No active session")
        
    return {"status": "stopped"}

@router.get("/session/status")
async def get_session_status(state: AppState = Depends(get_app_state)):
    # 1. Check in-memory state first
    if getattr(state, 'external_session_state', None) == "running":
        return {
            "state": "running",
            "session_id": getattr(state, 'external_session_id', None),
            "mode": getattr(state.clock, '_mode', 'live')
        }
    if state.current_engine and getattr(state.current_engine, 'is_running', False):
        return {
            "state": "running",
            "session_id": state.current_engine.session_id,
            "mode": getattr(state.clock, '_mode', 'live')
        }
        
    # 2. Check DB for any active session (in case API restarted)
    row = state.db.fetchone("SELECT session_id, mode FROM sessions WHERE status = 'active' ORDER BY started_at DESC LIMIT 1")
    if row:
        state.external_session_id = row["session_id"]
        state.external_session_state = "running"
        state.clock._mode = row["mode"]
        return {
            "state": "running",
            "session_id": row["session_id"],
            "mode": row["mode"]
        }
        
    # 3. Fallback: If no active session, return the LATEST session info so the UI isn't wiped out
    last_row = state.db.fetchone("SELECT session_id, mode, status FROM sessions ORDER BY started_at DESC LIMIT 1")
    if last_row:
        return {
            "state": last_row["status"],
            "session_id": last_row["session_id"],
            "mode": last_row["mode"]
        }
        
    return {"state": "idle", "session_id": None}

@router.get("/ledger")
async def get_ledger(session_id: str, db: Database = Depends(get_db)):
    row = db.fetchone("SELECT * FROM ledger WHERE session_id = ? ORDER BY id DESC LIMIT 1", (session_id,))
    if not row:
        return {"status": "no data"}
    return dict(row)

@router.get("/trades")
async def get_trades(session_id: str, limit: int = 50, offset: int = 0, db: Database = Depends(get_db)):
    rows = db.fetchall("SELECT * FROM trades WHERE session_id = ? ORDER BY close_time DESC LIMIT ? OFFSET ?", (session_id, limit, offset))
    return [dict(row) for row in rows]
    
@router.get("/positions")
async def get_positions(session_id: str, db: Database = Depends(get_db)):
    rows = db.fetchall("SELECT * FROM positions WHERE session_id = ?", (session_id,))
    return [dict(row) for row in rows]

@router.get("/orders/pending")
async def get_pending_orders(session_id: str, db: Database = Depends(get_db)):
    rows = db.fetchall("SELECT * FROM orders WHERE session_id = ? AND status = 'PENDING'", (session_id,))
    return [dict(row) for row in rows]

@router.get("/news/events")
async def get_news_events(
    limit: int = 50, 
    offset: int = 0, 
    impact: Optional[str] = None, 
    target: Optional[str] = None, 
    db: Database = Depends(get_db)
):
    query = "SELECT * FROM news_events"
    params = []
    conditions = []
    
    if impact:
        conditions.append("impact_score = ?")
        params.append(impact)
    if target:
        conditions.append("target_market LIKE ?")
        params.append(f"%{target}%")
        
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
        
    query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    rows = db.fetchall(query, tuple(params))
    return [dict(row) for row in rows]

class AnalyzeNewsRequest(BaseModel):
    headline: str
    summary: Optional[str] = ""
    url: Optional[str] = None

@router.post("/news/analyze")
async def analyze_news_event(
    req: AnalyzeNewsRequest,
    db: Database = Depends(get_db),
    state: AppState = Depends(get_app_state)
):
    from core.news_classifier import classify_event
    from datetime import datetime, timezone
    
    article = {
        "headline": req.headline,
        "summary": req.summary or "",
        "url": req.url
    }
    
    classification = classify_event(article)
    
    # Save to db
    try:
        db.execute("""
            INSERT INTO news_events (
                timestamp, headline, summary, source_url, sentiment, 
                impact_score, confidence, target_market, horizon_hours
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now(timezone.utc).isoformat(),
            req.headline,
            req.summary or classification.get("summary"),
            req.url,
            classification["sentiment"],
            classification["impact_score"],
            classification["confidence"],
            classification["target_market"],
            classification["horizon_hours"]
        ))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save to database: {e}")
        
    # Publish to EventBus
    try:
        state.event_bus.publish("NEWS_ALERT", {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "headline": req.headline,
            "summary": req.summary or classification.get("summary"),
            "source_url": req.url,
            "sentiment": classification["sentiment"],
            "impact_score": classification["impact_score"],
            "target_market": classification["target_market"],
            "confidence": classification["confidence"],
            "horizon_hours": classification["horizon_hours"]
        })
    except Exception as e:
        print(f"Failed to publish to event_bus: {e}")
        
    return {
        "status": "success",
        "classification": classification
    }

@router.post("/news/trigger_mock")
async def trigger_mock_event(
    state: AppState = Depends(get_app_state)
):
    if not hasattr(state, "news_ingestor") or not state.news_ingestor:
        raise HTTPException(status_code=400, detail="News Ingestor is not active")
        
    import random
    
    mock_templates = [
        {
            "headline": "Geopolitical tensions rise as primary Middle East oil supply route experiences naval blockade",
            "summary": "Tensions intensified today following naval blockades along primary container and shipping routes, exposing crude oil markets.",
            "url": "https://example.com/geo-oil-route"
        },
        {
            "headline": "US Core CPI Print matches estimates, Fed policy decision rates expected to hold next week",
            "summary": "Core Consumer Price Index inflation rates remain flat. Markets project FOMC will keep current rates unchanged.",
            "url": "https://example.com/cpi-rates-usd"
        },
        {
            "headline": "RBI Governor hints at monetary policy rates hikes if Nifty inflation breaches target limits",
            "summary": "Reserve Bank of India warns of local liquidity tightening depending on inflation growth prints.",
            "url": "https://example.com/rbi-inflation-rates"
        },
        {
            "headline": "OPEC+ members agree to additional voluntary crude oil production cuts",
            "summary": "OPEC+ members agree to cut oil supply by 1.5 million barrels per day starting next month to support market stability.",
            "url": "https://example.com/opec-cuts"
        },
        {
            "headline": "Dovish Fed comments suggest rate easing cycle may begin earlier than expected",
            "summary": "Federal Reserve officials hint at potential interest rate cuts later this year if inflation continues its downward trajectory.",
            "url": "https://example.com/fed-dovish-easing"
        },
        {
            "headline": "Escalating tensions in the Middle East drive heavy safe-haven demand for Gold bullion",
            "summary": "A sudden escalation of geopolitical conflict has sparked a global flight to safety, sending spot gold prices to new intraday highs.",
            "url": "https://example.com/gold-safe-haven"
        },
        {
            "headline": "10-Year US Treasury yields surge to new yearly highs",
            "summary": "Treasury yields spike following stronger-than-expected economic growth data, applying pressure to non-yielding gold assets.",
            "url": "https://example.com/treasury-yields-spike"
        },
        {
            "headline": "India trade deficit widens as gold imports surge ahead of major festive season",
            "summary": "The Ministry of Commerce reported a substantial increase in gold imports, putting negative pressure on the USD/INR currency pair.",
            "url": "https://example.com/india-trade-deficit"
        },
        {
            "headline": "Severe port congestion and logistical blockades raise global inflation concerns",
            "summary": "Global supply chain disruptions intensify as major shipping ports experience severe delays, boosting commodity pricing pressure.",
            "url": "https://example.com/supply-chain-blockade"
        },
        {
            "headline": "European Central Bank announces surprise 25 bps rate cut to bolster Eurozone growth",
            "summary": "The ECB lowering its benchmark interest rates surprised economists, signaling concerns over slowing regional macroeconomic momentum.",
            "url": "https://example.com/ecb-rate-cut"
        },
        {
            "headline": "US Non-Farm Payrolls exceed forecasts by a wide margin, reinforcing USD strength",
            "summary": "The US labor market added 275,000 jobs last month, far exceeding expectations and locking in hawkish rate expectations for the greenback.",
            "url": "https://example.com/nfp-strong-usd"
        },
        {
            "headline": "Major gold mine strikes in South Africa tighten global physical bullion supply",
            "summary": "Industry representatives warn of prolonged shutdowns at major operations, creating immediate price support for physical gold.",
            "url": "https://example.com/gold-mine-strikes"
        }
    ]
    
    evt = random.choice(mock_templates).copy()
    if "cpi-rates-usd" in evt["url"]:
        cpi_val = round(random.uniform(2.8, 4.2), 1)
        evt["headline"] = f"US Core CPI Print registers at {cpi_val}%, Fed policy rates expected to hold"
        evt["summary"] = f"Core Consumer Price Index inflation rates printed at {cpi_val}% annually. Markets project FOMC will keep rates unchanged."
    elif "opec-cuts" in evt["url"]:
        cut_val = round(random.uniform(0.5, 2.0), 1)
        evt["headline"] = f"OPEC+ members agree to voluntary crude oil cuts of {cut_val}M bpd"
        evt["summary"] = f"OPEC+ members agree to cut oil supply by {cut_val} million barrels per day starting next month to support market stability."
    elif "treasury-yields-spike" in evt["url"]:
        yield_val = round(random.uniform(4.2, 5.1), 2)
        evt["headline"] = f"10-Year US Treasury yields surge to {yield_val}% yearly highs"
        evt["summary"] = f"Treasury yields spike to {yield_val}% following stronger-than-expected economic growth data, applying pressure to gold assets."
        
    await state.news_ingestor.process_article(evt)
    return {"status": "success", "event": evt}
