import pytest
import jwt
from core.runtime.sidecar_manager import SidecarManager
from core.channels.manager import ChannelManager
from core.config.secrets import SecretStore

class MockSecretStore(SecretStore):
    def __init__(self):
        self._secrets = {}
        
    def get(self, name):
        return self._secrets.get(name)
        
    def set(self, name, value):
        self._secrets[name] = value

@pytest.fixture
def sidecar_manager():
    ch_mgr = ChannelManager()
    store = MockSecretStore()
    return SidecarManager(ch_mgr, store)

def test_sidecar_enrollment(sidecar_manager):
    token = sidecar_manager.generate_enrollment_token("device123")
    assert token is not None
    
    # Validate it
    sid = sidecar_manager.validate_enrollment_token(token)
    assert sid == "device123"
    
def test_sidecar_access_token(sidecar_manager):
    # Issue access token
    acc_token = sidecar_manager.issue_access_token("device123")
    assert acc_token is not None
    
    # Validating as access token should succeed
    sid = sidecar_manager.validate_access_token(acc_token)
    assert sid == "device123"
    
    # Validating an access token as an enrollment token should FAIL (audience mismatch/rejection)
    sid_enroll = sidecar_manager.validate_enrollment_token(acc_token)
    assert sid_enroll is None

def test_sidecar_invalid_token(sidecar_manager):
    assert sidecar_manager.validate_access_token("not.a.token") is None
    assert sidecar_manager.validate_enrollment_token("not.a.token") is None

def test_sidecar_keys_persist():
    store = MockSecretStore()
    ch_mgr = ChannelManager()
    sm1 = SidecarManager(ch_mgr, store)
    
    token = sm1.generate_enrollment_token("device123")
    
    # Simulate restart
    sm2 = SidecarManager(ch_mgr, store)
    sid = sm2.validate_enrollment_token(token)
    assert sid == "device123" # Must be able to validate token minted by sm1
