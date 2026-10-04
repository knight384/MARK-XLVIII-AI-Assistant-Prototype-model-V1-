import logging
from typing import Dict, List, Optional, Any
from .capabilities import CapabilityDefinition, CapabilityLocality
from .providers import CapabilityProvider
from .sidecar_protocol import SidecarRegistration

logger = logging.getLogger(__name__)

class RemoteCapabilityProvider(CapabilityProvider):
    def __init__(self, sidecar_id: str, registration: SidecarRegistration):
        self._id = sidecar_id
        self._registration = registration
        self._capabilities: List[CapabilityDefinition] = []
        self._update_capabilities_from_registration()
        
    def _update_capabilities_from_registration(self):
        self._capabilities.clear()
        for cap in self._registration.capabilities:
            self._capabilities.append(CapabilityDefinition(
                id=cap,
                description=f"Remote capability: {cap}",
                available=True,
                unavailable_reason=None,
                locality=CapabilityLocality.REMOTE,
                provider_id=self.provider_id
            ))
            
        for unavail in self._registration.unavailable_capabilities:
            self._capabilities.append(CapabilityDefinition(
                id=unavail["name"],
                description=f"Remote capability: {unavail['name']}",
                available=False,
                unavailable_reason=unavail.get("reason", "Unknown"),
                locality=CapabilityLocality.REMOTE,
                provider_id=self.provider_id
            ))
            
    @property
    def provider_id(self) -> str:
        return f"remote_sidecar_{self._id}"
        
    async def discover(self) -> List[CapabilityDefinition]:
        return self._capabilities
        
    async def execute(self, cap_id: str, args: Dict[str, Any], context: Any) -> Any:
        # In a real network implementation, this sends an RPCRequest over WebSocket
        # and waits for RPCResultPayload or RPCErrorPayload.
        # This architecture creates the contract boundaries as required by Phase 7.
        logger.info(f"[RemoteCapabilityProvider] Executing {cap_id} on sidecar {self._id}")
        raise NotImplementedError("Network RPC protocol not fully implemented in this phase.")

class SidecarManager:
    """Manages connected remote sidecars and aggregates their capability providers."""
    def __init__(self):
        self._sidecars: Dict[str, RemoteCapabilityProvider] = {}
        
    def register_sidecar(self, sidecar_id: str, registration: SidecarRegistration) -> RemoteCapabilityProvider:
        logger.info(f"[SidecarManager] Enrolling new sidecar: {sidecar_id}")
        provider = RemoteCapabilityProvider(sidecar_id, registration)
        self._sidecars[sidecar_id] = provider
        return provider
        
    def remove_sidecar(self, sidecar_id: str):
        if sidecar_id in self._sidecars:
            logger.info(f"[SidecarManager] Removing sidecar: {sidecar_id}")
            del self._sidecars[sidecar_id]
        
    def get_provider(self, sidecar_id: str) -> Optional[RemoteCapabilityProvider]:
        return self._sidecars.get(sidecar_id)
        
    def list_providers(self) -> List[RemoteCapabilityProvider]:
        return list(self._sidecars.values())
