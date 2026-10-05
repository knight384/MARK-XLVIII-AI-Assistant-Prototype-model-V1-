from __future__ import annotations
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

class WorkflowState(Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"

class WorkflowRunStatus(Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    WAITING_CONDITION = "WAITING_CONDITION"
    RETRYING = "RETRYING"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"

class StepType(Enum):
    AGENT = "AGENT"
    TOOL = "TOOL"
    CONDITION = "CONDITION"
    WAIT = "WAIT"
    APPROVAL = "APPROVAL"
    NOTIFICATION = "NOTIFICATION"
    JOIN = "JOIN"

@dataclass
class WorkflowNode:
    id: str
    type: StepType
    name: str
    config: Dict[str, Any] = field(default_factory=dict)
    next_nodes: List[str] = field(default_factory=list)

@dataclass
class WorkflowDefinition:
    id: str
    version: int
    name: str
    state: WorkflowState
    nodes: Dict[str, WorkflowNode]
    start_node_id: str
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

@dataclass
class WorkflowRun:
    id: str
    workflow_id: str
    workflow_version: int
    mission_id: Optional[str]
    status: WorkflowRunStatus
    current_node_id: Optional[str]
    context: Dict[str, Any]
    correlation_id: str
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    error: Optional[str] = None
    attempt: int = 1
    max_attempts: int = 1
    locked_until: Optional[float] = None

@dataclass
class WorkflowStepRun:
    id: str
    run_id: str
    node_id: str
    status: WorkflowRunStatus
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    attempt: int = 1

