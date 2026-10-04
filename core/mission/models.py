from __future__ import annotations
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

class MissionState(Enum):
    DRAFT = "DRAFT"
    SCHEDULED = "SCHEDULED"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    WAITING_CONDITION = "WAITING_CONDITION"
    PAUSED = "PAUSED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"

class TriggerType(Enum):
    MANUAL = "MANUAL"
    CRON = "CRON"
    EVENT = "EVENT"
    CONDITION = "CONDITION"

@dataclass
class Mission:
    id: str
    name: str
    description: str
    owner: str
    state: MissionState
    trigger_type: TriggerType
    created_at: float
    updated_at: float
    
    # Scheduling & Conditions
    scheduled_at: Optional[float] = None
    timezone: str = "UTC"
    cron_expression: Optional[str] = None
    trigger_event: Optional[str] = None
    condition_metadata: dict[str, Any] = field(default_factory=dict)
    
    # Execution
    priority: int = 0
    current_task_id: Optional[str] = None
    last_execution_at: Optional[float] = None
    next_execution_at: Optional[float] = None
    
    # Retry state
    max_attempts: int = 1
    attempt_count: int = 0
    retry_metadata: dict[str, Any] = field(default_factory=dict)
    
    # Results
    result_summary: Optional[str] = None
    error_state: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "owner": self.owner,
            "state": self.state.value,
            "trigger_type": self.trigger_type.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "scheduled_at": self.scheduled_at,
            "timezone": self.timezone,
            "cron_expression": self.cron_expression,
            "trigger_event": self.trigger_event,
            "condition_metadata": self.condition_metadata,
            "priority": self.priority,
            "current_task_id": self.current_task_id,
            "last_execution_at": self.last_execution_at,
            "next_execution_at": self.next_execution_at,
            "max_attempts": self.max_attempts,
            "attempt_count": self.attempt_count,
            "retry_metadata": self.retry_metadata,
            "result_summary": self.result_summary,
            "error_state": self.error_state,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Mission:
        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            owner=data.get("owner", "system"),
            state=MissionState(data["state"]),
            trigger_type=TriggerType(data["trigger_type"]),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            scheduled_at=data.get("scheduled_at"),
            timezone=data.get("timezone", "UTC"),
            cron_expression=data.get("cron_expression"),
            trigger_event=data.get("trigger_event"),
            condition_metadata=data.get("condition_metadata", {}),
            priority=data.get("priority", 0),
            current_task_id=data.get("current_task_id"),
            last_execution_at=data.get("last_execution_at"),
            next_execution_at=data.get("next_execution_at"),
            max_attempts=data.get("max_attempts", 1),
            attempt_count=data.get("attempt_count", 0),
            retry_metadata=data.get("retry_metadata", {}),
            result_summary=data.get("result_summary"),
            error_state=data.get("error_state"),
            metadata=data.get("metadata", {}),
        )
