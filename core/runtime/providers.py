from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from .capabilities import CapabilityDefinition, CapabilityLocality

class CapabilityProvider(ABC):
    """Base class for any source of capabilities (local or remote)."""
    
    @property
    @abstractmethod
    def provider_id(self) -> str:
        pass
        
    @abstractmethod
    async def discover(self) -> List[CapabilityDefinition]:
        """Discover available capabilities."""
        pass
        
    @abstractmethod
    async def execute(self, cap_id: str, args: Dict[str, Any], context: Any) -> Any:
        """Execute a capability."""
        pass

class LocalCapabilityProvider(CapabilityProvider):
    """Wraps MARK's local ToolRegistry as a Capability Provider."""
    def __init__(self, tool_registry):
        self._registry = tool_registry
        
    @property
    def provider_id(self) -> str:
        return "local_tools"
        
    async def discover(self) -> List[CapabilityDefinition]:
        caps = []
        for name, tool in self._registry._tools.items():
            caps.append(CapabilityDefinition(
                id=name,
                description=tool.__doc__ or name,
                available=True, # Local tools are checked for availability at registration
                unavailable_reason=None,
                locality=CapabilityLocality.LOCAL,
                provider_id=self.provider_id,
                metadata=tool.metadata
            ))
        return caps
        
    async def execute(self, cap_id: str, args: Dict[str, Any], context: Any) -> Any:
        # For actual execution, the ToolExecutor is used instead of directly calling this.
        # This is purely a bridge if needed. The execution always routes through ToolExecutor/PolicyEngine.
        tool = self._registry.get(cap_id)
        if not tool:
            raise ValueError(f"Capability {cap_id} not found in local provider")
        return await tool.execute(args, context)
