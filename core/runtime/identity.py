from dataclasses import dataclass, field
from typing import Dict, Any, List
import uuid
import time
import socket
from .mode import RuntimeMode

@dataclass
class RuntimeIdentity:
    """Identity and metadata for the current runtime instance."""
    runtime_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    runtime_name: str = field(default_factory=socket.gethostname)
    mode: RuntimeMode = RuntimeMode.LOCAL
    version: str = "7.0.0"
    startup_timestamp: float = field(default_factory=time.time)
    capabilities: List[str] = field(default_factory=list)
    model_tiers: List[str] = field(default_factory=list)
    runtime_metadata: Dict[str, Any] = field(default_factory=dict)
