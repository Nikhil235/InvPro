"""
ws.py -- WebSocket broadcaster attached to EventBus.
"""

import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List, Dict, Any
from core.event_bus import EventBus
from utils.logger import get_logger
import json

log = get_logger("ws")

ws_router = APIRouter()

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        log.info(f"WebSocket connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            log.info(f"WebSocket disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: str):
        for connection in self.active_connections.copy():
            try:
                await connection.send_text(message)
            except Exception as e:
                log.error(f"Error broadcasting to client: {e}")
                self.disconnect(connection)

manager = ConnectionManager()

@ws_router.websocket("")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

def setup_ws_broadcaster(event_bus: EventBus) -> asyncio.Task:
    """Subscribes to all events and broadcasts them over WebSockets."""
    
    async def broadcaster_loop():
        loop = asyncio.get_running_loop()
        queue = asyncio.Queue()
        
        def on_event(event_type: str, payload: Dict[str, Any]):
            loop.call_soon_threadsafe(queue.put_nowait, (event_type, payload))
            
        events_to_broadcast = [
            "TICK", "SIGNAL", "ORDER_SUBMITTED", "ORDER_FILLED", "ORDER_REJECTED",
            "ORDER_CANCELLED", "TRADE_CLOSED", "POSITION_UPDATE", "SESSION_STATUS",
            "REPLAY_PROGRESS", "LEDGER_UPDATE", "NEWS_ALERT"
        ]
        
        for event in events_to_broadcast:
            event_bus.subscribe(event, lambda payload, e=event: on_event(e, payload))
            
        while True:
            try:
                event_type, payload = await queue.get()
                message = json.dumps({"event": event_type, "data": payload}, default=str)
                await manager.broadcast(message)
                queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Broadcaster error: {e}")
                
    return asyncio.create_task(broadcaster_loop())
