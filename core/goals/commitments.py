from __future__ import annotations
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

class CommitmentState(Enum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    OVERDUE = "OVERDUE"
    CANCELLED = "CANCELLED"

@dataclass
class Commitment:
    id: str
    what: str
    due_at: Optional[float] = None
    state: CommitmentState = CommitmentState.ACTIVE
    related_goal_id: Optional[str] = None
    related_mission_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "what": self.what,
            "due_at": self.due_at,
            "state": self.state.value,
            "related_goal_id": self.related_goal_id,
            "related_mission_id": self.related_mission_id,
            "created_at": self.created_at
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> Commitment:
        return cls(
            id=data["id"],
            what=data["what"],
            due_at=data.get("due_at"),
            state=CommitmentState(data.get("state", "ACTIVE")),
            related_goal_id=data.get("related_goal_id"),
            related_mission_id=data.get("related_mission_id"),
            created_at=data.get("created_at", time.time())
        )
