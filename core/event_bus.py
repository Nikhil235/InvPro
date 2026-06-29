"""
event_bus.py -- In-process async pub/sub for decoupling execution from API/WS.
"""

import asyncio
from typing import Callable, Dict, List, Any
from utils.logger import get_logger

log = get_logger("event_bus")

class EventBus:
    """Typed publish-subscribe bus. Listeners receive events asynchronously."""
    
    def __init__(self) -> None:
        self._subscribers: Dict[str, List[Callable]] = {}
        
    def subscribe(self, event_type: str, handler: Callable) -> None:
        """Subscribe to an event type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        if handler not in self._subscribers[event_type]:
            self._subscribers[event_type].append(handler)
            
    def publish(self, event_type: str, payload: dict) -> None:
        """Publish an event synchronously (handlers run immediately or scheduled)."""
        if event_type in self._subscribers:
            for handler in self._subscribers[event_type]:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        try:
                            loop = asyncio.get_running_loop()
                            loop.create_task(handler(payload))
                        except RuntimeError:
                            # Not in async context
                            asyncio.run(handler(payload))
                    else:
                        handler(payload)
                except Exception as e:
                    log.error(f"Error in event handler for {event_type}: {e}", exc_info=True)
                    
    def publish_async(self, event_type: str, payload: dict) -> None:
        """Helper to explicitly publish to async handlers from non-async contexts."""
        self.publish(event_type, payload)
