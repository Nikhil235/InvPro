import asyncio
from datetime import datetime
from pydantic import BaseModel
import uuid

# Import system
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from core.database import Database
from core.clock import ClockService
from core.event_bus import EventBus
from core.session_manager import SessionManager
from core.replay_engine import ReplayEngine
from paper_trading.core.paper_broker import PaperBroker
from paper_trading.core.risk_manager import RiskManager
from paper_trading.core.account_ledger import AccountLedger
from paper_trading.core.signal_router import SignalRouter
from core.strategy import TradingStrategy

async def test_replay():
    db = Database()
    clock = ClockService(mode="live")
    event_bus = EventBus()
    
    session_id = f"replay_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    clock._mode = "replay"
    
    print("creating ledger")
    ledger = AccountLedger(db, clock, event_bus, session_id, 10000.0)
    print("creating broker")
    broker = PaperBroker(db, clock, event_bus, ledger, session_id)
    print("creating risk mgr")
    risk_mgr = RiskManager(clock, event_bus, ledger, session_id)
    print("creating router")
    signal_router = SignalRouter(broker, risk_mgr, event_bus)
    print("creating strategy")
    strategy = TradingStrategy()
    
    print("creating engine")
    engine = ReplayEngine(db, clock, event_bus, broker, strategy, signal_router, session_id, 1.0)
    print("starting engine")
    await engine.start()
    print("success")

asyncio.run(test_replay())
