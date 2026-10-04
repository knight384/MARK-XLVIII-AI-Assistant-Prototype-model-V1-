from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from enum import Enum, auto

from core.tools.metadata import ToolMetadata

class CapabilityLocality(Enum):
    LOCAL = auto()
    REMOTE = auto()
    HYBRID = auto()

@dataclass
class CapabilityDefinition:
    """A MARK-native capability representing something the runtime can do."""
    id: str
    description: str
    available: bool
    unavailable_reason: Optional[str]
    locality: CapabilityLocality
    provider_id: str
    metadata: Optional[ToolMetadata] = None
    environment_requirements: Dict[str, Any] = field(default_factory=dict)
