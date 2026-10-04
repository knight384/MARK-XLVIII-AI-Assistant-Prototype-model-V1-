import logging
from typing import Any, Callable
from .models import Mission, MissionState

logger = logging.getLogger(__name__)

class ConditionEvaluator:
    """
    Evaluates conditions for WAITING_CONDITION missions.
    Separates observation from authorization.
    """
    def __init__(self):
        self._handlers: dict[str, Callable[[Mission, Any], bool]] = {}
        
    def register_handler(self, condition_type: str, handler: Callable[[Mission, Any], bool]):
        self._handlers[condition_type] = handler

    def evaluate(self, mission: Mission, event_data: Any = None) -> bool:
        if mission.state != MissionState.WAITING_CONDITION:
            return False
            
        condition_type = mission.condition_metadata.get("type")
        if not condition_type:
            logger.warning(f"Mission {mission.id} has no condition type metadata.")
            return False
            
        handler = self._handlers.get(condition_type)
        if not handler:
            logger.warning(f"No handler registered for condition type: {condition_type}")
            return False
            
        try:
            return handler(mission, event_data)
        except Exception as e:
            logger.error(f"Error evaluating condition '{condition_type}' for mission {mission.id}: {e}")
            return False

_default_evaluator: ConditionEvaluator | None = None

def get_default_evaluator() -> ConditionEvaluator:
    global _default_evaluator
    if _default_evaluator is None:
        _default_evaluator = ConditionEvaluator()
    return _default_evaluator
