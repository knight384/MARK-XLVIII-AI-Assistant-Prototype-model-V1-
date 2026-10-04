from enum import Enum, auto
from typing import Dict, List, Optional, Protocol, runtime_checkable
import logging

logger = logging.getLogger(__name__)

class ServiceStatus(Enum):
    STOPPED = auto()
    STARTING = auto()
    RUNNING = auto()
    STOPPING = auto()
    ERROR = auto()

@runtime_checkable
class Service(Protocol):
    """Protocol for a runtime service."""
    
    @property
    def name(self) -> str:
        ...
        
    async def start(self) -> None:
        ...
        
    async def stop(self) -> None:
        ...
        
    def status(self) -> ServiceStatus:
        ...

class ServiceRegistry:
    """Manages lifecycle of all daemon services."""
    def __init__(self):
        self._services: Dict[str, Service] = {}
        self._status: Dict[str, ServiceStatus] = {}
        self._errors: Dict[str, Optional[str]] = {}
        
    def register(self, service: Service) -> None:
        if service.name in self._services:
            raise ValueError(f"Service '{service.name}' is already registered")
        self._services[service.name] = service
        self._status[service.name] = ServiceStatus.STOPPED
        self._errors[service.name] = None
        logger.info(f"[ServiceRegistry] Registered service: {service.name}")
        
    async def start_all(self) -> None:
        logger.info("[ServiceRegistry] Starting all services...")
        for name in self._services:
            await self.start_service(name)
        logger.info("[ServiceRegistry] All services started")
        
    async def stop_all(self) -> None:
        logger.info("[ServiceRegistry] Stopping all services...")
        for name in reversed(list(self._services.keys())):
            await self.stop_service(name)
        logger.info("[ServiceRegistry] All services stopped")
        
    async def start_service(self, name: str) -> None:
        if name not in self._services:
            raise ValueError(f"Service '{name}' not found")
            
        if self._status[name] == ServiceStatus.RUNNING:
            logger.info(f"[ServiceRegistry] Service '{name}' is already running")
            return
            
        try:
            self._status[name] = ServiceStatus.STARTING
            logger.info(f"[ServiceRegistry] Starting {name}...")
            
            await self._services[name].start()
            
            self._status[name] = ServiceStatus.RUNNING
            self._errors[name] = None
            logger.info(f"[ServiceRegistry] ✓ {name} started")
        except Exception as e:
            self._status[name] = ServiceStatus.ERROR
            self._errors[name] = str(e)
            logger.error(f"[ServiceRegistry] ✗ Failed to start {name}: {e}")
            raise
            
    async def stop_service(self, name: str) -> None:
        if name not in self._services:
            raise ValueError(f"Service '{name}' not found")
            
        if self._status[name] == ServiceStatus.STOPPED:
            logger.info(f"[ServiceRegistry] Service '{name}' is already stopped")
            return
            
        try:
            self._status[name] = ServiceStatus.STOPPING
            logger.info(f"[ServiceRegistry] Stopping {name}...")
            
            await self._services[name].stop()
            
            self._status[name] = ServiceStatus.STOPPED
            self._errors[name] = None
            logger.info(f"[ServiceRegistry] ✓ {name} stopped")
        except Exception as e:
            self._status[name] = ServiceStatus.ERROR
            self._errors[name] = str(e)
            logger.error(f"[ServiceRegistry] ✗ Failed to stop {name}: {e}")
            raise

    def get_status(self) -> Dict[str, ServiceStatus]:
        return dict(self._status)
        
    def get(self, name: str) -> Optional[Service]:
        return self._services.get(name)
        
    def list(self) -> List[str]:
        return list(self._services.keys())
        
    def has(self, name: str) -> bool:
        return name in self._services
