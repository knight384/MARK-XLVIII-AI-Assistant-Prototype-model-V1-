import logging
import uuid
import time
from typing import List, Dict

from core.runtime.events import get_default_bus, RuntimeEvent
from .signals import AwarenessSignal, SignalCategory

logger = logging.getLogger(__name__)

class AwarenessTracker:
    """
    Bounded tracker that records meaningful contextual changes.
    Does not continuously record everything. Retains a bounded history of signals.
    """
    def __init__(self, max_history: int = 100):
        self.max_history = max_history
        self._signals: List[AwarenessSignal] = []
        self._enabled = True
        self._excluded_categories = set()

    def enable(self):
        self._enabled = True

    def disable(self):
        self._enabled = False

    def exclude_category(self, category: SignalCategory):
        self._excluded_categories.add(category)

    def include_category(self, category: SignalCategory):
        self._excluded_categories.discard(category)

    def start(self):
        bus = get_default_bus()
        bus.subscribe(self._on_runtime_event)
        logger.info("[AwarenessTracker] Subscribed to EventBus for contextual signals.")

    def _on_runtime_event(self, event: RuntimeEvent):
        if not self._enabled:
            return

        # Map RuntimeEvents to AwarenessSignals where meaningful
        signal = self._map_event_to_signal(event)
        if signal:
            if signal.category in self._excluded_categories:
                logger.debug(f"[AwarenessTracker] Ignored excluded signal category: {signal.category.name}")
                return
                
            self.add_signal(signal)

    def _map_event_to_signal(self, event: RuntimeEvent) -> AwarenessSignal | None:
        # Bounded explicit signal mapping
        if event.event_type.startswith("task_"):
            return AwarenessSignal(
                id=str(uuid.uuid4()),
                category=SignalCategory.TASK_EVENT,
                type=event.event_type,
                payload=event.payload,
                timestamp=event.timestamp
            )
        elif event.event_type.startswith("mission_"):
            return AwarenessSignal(
                id=str(uuid.uuid4()),
                category=SignalCategory.MISSION_EVENT,
                type=event.event_type,
                payload=event.payload,
                timestamp=event.timestamp
            )
        elif event.event_type.startswith("goal_"):
            return AwarenessSignal(
                id=str(uuid.uuid4()),
                category=SignalCategory.GOAL_EVENT,
                type=event.event_type,
                payload=event.payload,
                timestamp=event.timestamp
            )
        elif event.event_type.startswith("developer_"):
            return AwarenessSignal(
                id=str(uuid.uuid4()),
                category=SignalCategory.DEVELOPER_EVENT,
                type=event.event_type,
                payload=event.payload,
                timestamp=event.timestamp
            )
        return None

    def add_signal(self, signal: AwarenessSignal):
        if not self._enabled:
            return
            
        self._signals.append(signal)
        # Deduplication (e.g. repeated task failures of the same type within 1 minute)
        # Bounded retention
        if len(self._signals) > self.max_history:
            self._signals = self._signals[-self.max_history:]
            
        # Feed into Opportunity Engine asynchronously in a full implementation,
        # but here we can just log or trigger it.
        logger.debug(f"[AwarenessTracker] Tracked signal: {signal.type}")

    def get_recent_signals(self, limit: int = 20) -> List[AwarenessSignal]:
        return self._signals[-limit:]

    def clear(self):
        self._signals.clear()

_default_tracker: AwarenessTracker | None = None

def get_default_tracker() -> AwarenessTracker:
    global _default_tracker
    if _default_tracker is None:
        _default_tracker = AwarenessTracker()
    return _default_tracker
