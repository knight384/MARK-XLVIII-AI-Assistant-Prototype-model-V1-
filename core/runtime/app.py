import asyncio
import logging
import signal
from typing import Optional

from .mode import RuntimeMode
from .identity import RuntimeIdentity
from .services import ServiceRegistry
from core.channels.manager import ChannelManager
from core.runtime.sidecar_manager import SidecarManager
from core.config.secrets import SecretStore
from pathlib import Path

logger = logging.getLogger(__name__)

class MarkRuntime:
    """Core MARK XLVIII Application Runtime."""
    def __init__(self, mode: RuntimeMode = RuntimeMode.LOCAL):
        self.mode = mode
        self.identity = RuntimeIdentity(mode=self.mode)
        self.services = ServiceRegistry()
        self.channel_manager = ChannelManager()
        
        # SecretStore and SidecarManager initialization
        # Use default paths relative to execution
        import sys
        if getattr(sys, "frozen", False):
            base_dir = Path(sys.executable).parent
        else:
            base_dir = Path(__file__).resolve().parents[2]
        self.secret_store = SecretStore(base_dir / "config" / "secrets.json")
        self.sidecar_manager = SidecarManager(self.channel_manager, self.secret_store)
        
        self._shutdown_event = asyncio.Event()
        
    async def initialize(self):
        """Phase 1: Configure system and register services."""
        logger.info(f"[Runtime] Initializing MARK XLVIII (Mode: {self.mode.name})")
        # TODO: Register core services (Memory, Policy, Orchestrator, WS/API)
        
    async def start(self):
        """Phase 2: Start all registered services in order."""
        await self.services.start_all()
        await self.channel_manager.start()
        logger.info(f"[Runtime] MARK XLVIII Runtime Started (ID: {self.identity.runtime_id})")
        
    async def wait_until_shutdown(self):
        """Phase 3: Wait for shutdown signal."""
        await self._shutdown_event.wait()
        
    async def stop(self):
        """Phase 4: Graceful teardown of all services in reverse order."""
        logger.info("[Runtime] Shutting down MARK XLVIII...")
        await self.channel_manager.stop()
        await self.services.stop_all()
        logger.info("[Runtime] Shutdown complete.")

    def trigger_shutdown(self):
        self._shutdown_event.set()
