import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from typing import List
import json
import logging

from .models import SignalUpdate, Trade, Metrics, Settings, LogEntry, AlertRule, BrokerEvent
from .store import store

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Live Trading Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        dead_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                dead_connections.append(connection)
        
        for dead in dead_connections:
            self.disconnect(dead)

manager = ConnectionManager()

@app.get("/api/v1/health")
async def health_check():
    return {"status": "ok"}

@app.get("/api/v1/signal/current")
async def get_current_signal():
    signal = store.get_current_signal()
    return signal if signal else {"status": "No signal available"}

@app.get("/api/v1/trades")
async def get_trades(limit: int = 50, offset: int = 0):
    return store.get_trades(limit, offset)

@app.get("/api/v1/positions")
async def get_positions():
    return store.get_active_positions()

@app.get("/api/v1/orders")
async def get_orders():
    return []

@app.get("/api/v1/metrics")
async def get_metrics():
    return store.get_metrics()

@app.get("/api/v1/chart/candles")
async def get_candles(limit: int = 500):
    return store.get_candles(limit)

@app.get("/api/v1/alerts")
async def get_alerts():
    return store.get_alert_rules()

@app.post("/api/v1/alerts")
async def add_alert(rule: AlertRule):
    store.add_alert_rule(rule)
    return {"status": "ok"}

@app.delete("/api/v1/alerts/{rule_id}")
async def delete_alert(rule_id: int):
    store.delete_alert_rule(rule_id)
    return {"status": "ok"}

@app.get("/api/v1/logs")
async def get_logs(limit: int = 100, offset: int = 0):
    return store.get_logs(limit, offset)

@app.post("/api/v1/logs")
async def add_log(entry: LogEntry):
    store.add_log(entry)
    return {"status": "ok"}

@app.get("/api/v1/settings")
async def get_settings():
    return store.get_settings()

@app.post("/api/v1/settings")
async def update_settings(settings: Settings):
    store.update_settings(settings)
    return {"status": "ok"}

@app.post("/api/v1/internal/update")
async def receive_update(data: SignalUpdate):
    store.update_signal(data)
    await manager.broadcast({
        "type": "SIGNAL_UPDATE",
        "payload": data.model_dump()
    })
    
    # Broadcast any triggered alerts
    alerts = store.pop_triggered_alerts()
    for alert_msg in alerts:
        await manager.broadcast({
            "type": "ALERT_TRIGGERED",
            "payload": {"message": alert_msg}
        })
        
    return {"status": "ok"}

@app.post("/api/v1/internal/event")
async def receive_event(event: BrokerEvent):
    store.process_broker_event(event)
    await manager.broadcast({
        "type": "BROKER_EVENT",
        "payload": event.model_dump()
    })
    return {"status": "ok"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Send initial state
        current = store.get_current_signal()
        if current:
            await websocket.send_json({
                "type": "SIGNAL_UPDATE",
                "payload": current.model_dump()
            })
        while True:
            # Keep connection open, wait for client messages if any
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
