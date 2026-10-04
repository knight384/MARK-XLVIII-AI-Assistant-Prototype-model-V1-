import pytest
import asyncio
from core.runtime.app import MarkRuntime
from core.runtime.mode import RuntimeMode
from core.runtime.services import Service, ServiceStatus

class DummyService:
    def __init__(self, name):
        self._name = name
        self._status = ServiceStatus.STOPPED
        
    @property
    def name(self):
        return self._name
        
    async def start(self):
        self._status = ServiceStatus.RUNNING
        
    async def stop(self):
        self._status = ServiceStatus.STOPPED
        
    def status(self):
        return self._status

@pytest.mark.asyncio
async def test_runtime_lifecycle():
    runtime = MarkRuntime(mode=RuntimeMode.HEADLESS)
    assert runtime.mode == RuntimeMode.HEADLESS
    
    svc = DummyService("test_service")
    runtime.services.register(svc)
    
    await runtime.initialize()
    await runtime.start()
    
    assert runtime.services.get_status()["test_service"] == ServiceStatus.RUNNING
    
    await runtime.stop()
    assert runtime.services.get_status()["test_service"] == ServiceStatus.STOPPED

@pytest.mark.asyncio
async def test_headless_mode_enum():
    assert RuntimeMode.HEADLESS.name == "HEADLESS"
    assert RuntimeMode.DESKTOP.name == "DESKTOP"
