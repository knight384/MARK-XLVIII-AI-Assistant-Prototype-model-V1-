import asyncio
import logging
import signal
from typing import Optional

from .mode import RuntimeMode
from .identity import RuntimeIdentity
from .services import ServiceRegistry

logger = logging.getLogger(__name__)

class MarkRuntime:
    """Core MARK XLVIII Application Runtime."""
    def __init__(self, mode: RuntimeMode = RuntimeMode.LOCAL):
        self.mode = mode
        self.identity = RuntimeIdentity(mode=self.mode)
        self.services = ServiceRegistry()
        self._shutdown_event = asyncio.Event()
        
    async def initialize(self):
        """Phase 1: Configure system and register services."""
        logger.info(f"[Runtime] Initializing MARK XLVIII (Mode: {self.mode.name})")
        # TODO: Register core services (Memory, Policy, Orchestrator, WS/API)
        
    async def start(self):
        """Phase 2: Start all registered services in order."""
        await self.services.start_all()
        logger.info(f"[Runtime] MARK XLVIII Runtime Started (ID: {self.identity.runtime_id})")
        
    async def wait_until_shutdown(self):
        """Phase 3: Wait for shutdown signal."""
        await self._shutdown_event.wait()
        
    async def stop(self):
        """Phase 4: Graceful teardown of all services in reverse order."""
        logger.info("[Runtime] Shutting down MARK XLVIII...")
        await self.services.stop_all()
        logger.info("[Runtime] Shutdown complete.")

    def trigger_shutdown(self):
        self._shutdown_event.set()
