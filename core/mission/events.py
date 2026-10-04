import logging
from typing import Optional

from core.runtime.events import get_default_bus, RuntimeEvent
from .store import MissionStore
from .models import MissionState, TriggerType
from .conditions import get_default_evaluator

logger = logging.getLogger(__name__)

class MissionEventListener:
    """
    Subscribes to the EventBus to trigger event-based missions or evaluate conditions.
    Separates EVENT OBSERVATION from ACTION AUTHORIZATION.
    """
    def __init__(self, store: MissionStore):
        self.store = store
        self.evaluator = get_default_evaluator()
        
    def start(self):
        bus = get_default_bus()
        bus.subscribe(self._handle_event)
        logger.info("[MissionEventListener] Subscribed to EventBus for mission conditions and triggers.")

    def _handle_event(self, event: RuntimeEvent):
        # 1. Event Triggers (TriggerType.EVENT)
        # Find missions waiting for this event to trigger them.
        event_missions = self.store.list_missions(state=MissionState.READY)
        for mission in event_missions:
            if mission.trigger_type == TriggerType.EVENT and mission.trigger_event == event.event_type:
                logger.info(f"[MissionEventListener] Event '{event.event_type}' triggered mission {mission.id}")
                mission.state = MissionState.SCHEDULED
                self.store.save(mission)

        # 2. Condition Evaluations (WAITING_CONDITION)
        condition_missions = self.store.list_missions(state=MissionState.WAITING_CONDITION)
        for mission in condition_missions:
            try:
                # Evaluating condition does not authorize execution. It only changes state.
                if self.evaluator.evaluate(mission, event):
                    logger.info(f"[MissionEventListener] Condition met for mission {mission.id} due to event '{event.event_type}'")
                    mission.state = MissionState.SCHEDULED
                    self.store.save(mission)
            except Exception as e:
                logger.error(f"[MissionEventListener] Error evaluating condition for {mission.id}: {e}")

_default_listener: Optional[MissionEventListener] = None

def get_default_mission_listener(store: Optional[MissionStore] = None) -> MissionEventListener:
    global _default_listener
    if _default_listener is None:
        if store is None:
            raise ValueError("MissionStore required for first initialization of MissionEventListener")
        _default_listener = MissionEventListener(store)
    return _default_listener
