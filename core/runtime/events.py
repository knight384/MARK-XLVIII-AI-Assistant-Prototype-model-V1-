import time
import uuid
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Dict, Any, Callable, List

class EventPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"

@dataclass
class RuntimeEvent:
    """A MARK-native operational event."""
    event_type: str
    payload: Dict[str, Any]
    priority: EventPriority = EventPriority.NORMAL
    timestamp: float = field(default_factory=time.time)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))

class EventBus:
    """Central event bus for operational events."""
    def __init__(self):
        self._subscribers: List[Callable[[RuntimeEvent], None]] = []
        
    def subscribe(self, callback: Callable[[RuntimeEvent], None]):
        self._subscribers.append(callback)
        
    def publish(self, event: RuntimeEvent):
        for sub in self._subscribers:
            try:
                sub(event)
            except Exception:
                # Event handlers must not crash the bus or the caller
                pass

# Global default bus for the runtime
_default_bus = None

def get_default_bus() -> EventBus:
    global _default_bus
    if _default_bus is None:
        _default_bus = EventBus()
    return _default_bus
