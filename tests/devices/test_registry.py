import pytest
from core.devices.registry import DeviceRegistry
from core.devices.models import DeviceIdentity, DeviceStatus, ConnectionState, SidecarCapability

@pytest.fixture
def registry():
    return DeviceRegistry(db_path=":memory:")

def test_register_and_get_device(registry):
    device = DeviceIdentity(
        device_id="test_123",
        device_name="Test Phone",
        platform="android",
        capabilities=[SidecarCapability.TEXT, SidecarCapability.MICROPHONE]
    )
    registry.register_device(device)
    
    loaded = registry.get_device("test_123")
    assert loaded is not None
    assert loaded.device_name == "Test Phone"
    assert loaded.platform == "android"
    assert len(loaded.capabilities) == 2
    assert SidecarCapability.TEXT in loaded.capabilities

def test_update_status_and_connection(registry):
    device = DeviceIdentity(device_id="test_123", device_name="Test Phone")
    registry.register_device(device)
    
    registry.update_status("test_123", DeviceStatus.ENROLLED)
    registry.update_connection_state("test_123", ConnectionState.READY)
    
    loaded = registry.get_device("test_123")
    assert loaded.status == DeviceStatus.ENROLLED
    assert loaded.connection_state == ConnectionState.READY
    assert loaded.last_seen is not None

def test_revoke_device(registry):
    device = DeviceIdentity(device_id="test_123", device_name="Test Phone")
    registry.register_device(device)
    
    registry.revoke_device("test_123")
    loaded = registry.get_device("test_123")
    
    assert loaded.status == DeviceStatus.REVOKED
    assert loaded.connection_state == ConnectionState.DISCONNECTED
