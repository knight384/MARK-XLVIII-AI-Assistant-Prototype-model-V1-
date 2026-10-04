from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any

class SignalCategory(Enum):
    MISSION_EVENT = "MISSION_EVENT"
    TASK_EVENT = "TASK_EVENT"
    GOAL_EVENT = "GOAL_EVENT"
    PROJECT_EVENT = "PROJECT_EVENT"
    SYSTEM_EVENT = "SYSTEM_EVENT"
    DEVELOPER_EVENT = "DEVELOPER_EVENT"

@dataclass
class AwarenessSignal:
    id: str
    category: SignalCategory
    type: str # e.g. "task_failed", "goal_at_risk", "project_switched"
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "category": self.category.value,
            "type": self.type,
            "payload": self.payload,
            "timestamp": self.timestamp
        }
