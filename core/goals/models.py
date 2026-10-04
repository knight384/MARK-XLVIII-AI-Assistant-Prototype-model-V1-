from __future__ import annotations
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, List

class GoalState(Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    AT_RISK = "AT_RISK"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    ARCHIVED = "ARCHIVED"

@dataclass
class Milestone:
    id: str
    title: str
    description: str
    is_completed: bool = False
    completed_at: Optional[float] = None
    evidence: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "is_completed": self.is_completed,
            "completed_at": self.completed_at,
            "evidence": self.evidence
        }

    @classmethod
    def from_dict(cls, data: dict) -> Milestone:
        return cls(
            id=data["id"],
            title=data["title"],
            description=data["description"],
            is_completed=data.get("is_completed", False),
            completed_at=data.get("completed_at"),
            evidence=data.get("evidence")
        )

@dataclass
class Goal:
    id: str
    title: str
    description: str
    owner: str
    state: GoalState
    priority: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    target_time: Optional[float] = None
    progress: float = 0.0
    
    parent_id: Optional[str] = None
    milestones: List[Milestone] = field(default_factory=list)
    related_projects: List[str] = field(default_factory=list)
    related_missions: List[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "owner": self.owner,
            "state": self.state.value,
            "priority": self.priority,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "target_time": self.target_time,
            "progress": self.progress,
            "parent_id": self.parent_id,
            "milestones": [m.to_dict() for m in self.milestones],
            "related_projects": self.related_projects,
            "related_missions": self.related_missions,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: dict) -> Goal:
        return cls(
            id=data["id"],
            title=data["title"],
            description=data["description"],
            owner=data.get("owner", "user"),
            state=GoalState(data["state"]),
            priority=data.get("priority", 0),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            target_time=data.get("target_time"),
            progress=data.get("progress", 0.0),
            parent_id=data.get("parent_id"),
            milestones=[Milestone.from_dict(m) for m in data.get("milestones", [])],
            related_projects=data.get("related_projects", []),
            related_missions=data.get("related_missions", []),
            metadata=data.get("metadata", {})
        )
