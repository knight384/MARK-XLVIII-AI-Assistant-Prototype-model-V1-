from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List

class EventPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"

@dataclass
class RPCRequest:
    id: str
    method: str
    params: Dict[str, Any]

@dataclass
class RPCResultPayload:
    rpc_id: str
    result: Any
    
@dataclass
class RPCErrorPayload:
    rpc_id: str
    error: Dict[str, str]

@dataclass
class SidecarRegistration:
    hostname: str
    os: str
    platform: str
    version: str
    capabilities: List[str]
    unavailable_capabilities: List[Dict[str, str]] = field(default_factory=list)
