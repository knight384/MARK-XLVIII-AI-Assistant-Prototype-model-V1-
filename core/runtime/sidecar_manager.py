import logging
import time
from typing import Dict, List, Optional, Any
from core.channels.sidecar import SidecarChannel
from core.channels.manager import ChannelManager
from core.config.secrets import SecretStore
from core.devices.registry import DeviceRegistry
from core.devices.models import DeviceIdentity, DeviceStatus, ConnectionState, SidecarCapability
import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

logger = logging.getLogger(__name__)

class SidecarManager:
    """
    Manages sidecar authentication, keys, and tracking connected sidecars.
    Integrates heavily with the Multichannel architecture.
    """
    def __init__(self, channel_manager: ChannelManager, secret_store: SecretStore, registry: Optional[DeviceRegistry] = None):
        self.channel_manager = channel_manager
        self.secret_store = secret_store
        self.registry = registry if registry is not None else DeviceRegistry()
        self._connected_sidecars: Dict[str, SidecarChannel] = {}
        
        self._private_key: Optional[ec.EllipticCurvePrivateKey] = None
        self._public_key: Optional[ec.EllipticCurvePublicKey] = None
        self._key_id = "mark_xlviii_sidecar_key"
        self._load_or_generate_keys()

    def _load_or_generate_keys(self):
        priv_pem = self.secret_store.get("sidecar_private_key")
        if priv_pem:
            self._private_key = serialization.load_pem_private_key(
                priv_pem.encode('utf-8'), password=None
            )
            self._public_key = self._private_key.public_key()
            logger.info("[SidecarManager] Loaded existing ES256 keys for sidecars.")
        else:
            logger.info("[SidecarManager] Generating new ES256 keys for sidecars.")
            self._private_key = ec.generate_private_key(ec.SECP256R1())
            self._public_key = self._private_key.public_key()
            priv_bytes = self._private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )
            self.secret_store.set("sidecar_private_key", priv_bytes.decode('utf-8'))

    def generate_enrollment_token(self, sidecar_id: str) -> str:
        """Issue long-lived token (no aud) for initial connection/refresh."""
        if not self._private_key:
            raise RuntimeError("Sidecar keys not loaded.")
        payload = {
            "sid": sidecar_id,
            "iat": int(time.time()),
        }
        return jwt.encode(payload, self._private_key, algorithm="ES256", headers={"kid": self._key_id})

    def issue_access_token(self, sidecar_id: str) -> str:
        """Issue short-lived token (aud=brain-api) for active sessions."""
        if not self._private_key:
            raise RuntimeError("Sidecar keys not loaded.")
        payload = {
            "sid": sidecar_id,
            "aud": "brain-api",
            "iat": int(time.time()),
            "exp": int(time.time()) + 600 # 10 mins
        }
        return jwt.encode(payload, self._private_key, algorithm="ES256", headers={"kid": self._key_id})

    def validate_access_token(self, token: str) -> Optional[str]:
        """Returns sidecar_id if valid, else None."""
        if not self._public_key:
            return None
        try:
            payload = jwt.decode(token, self._public_key, algorithms=["ES256"], audience="brain-api")
            return payload.get("sid")
        except jwt.PyJWTError as e:
            logger.warning(f"[SidecarManager] Token validation failed: {e}")
            return None

    def validate_enrollment_token(self, token: str) -> Optional[str]:
        """Validate long-lived token."""
        if not self._public_key:
            return None
        try:
            # decode without audience
            payload = jwt.decode(token, self._public_key, algorithms=["ES256"], options={"verify_aud": False})
            if payload.get("aud") == "brain-api":
                return None # reject short-lived token
            return payload.get("sid")
        except jwt.PyJWTError as e:
            logger.warning(f"[SidecarManager] Enrollment token validation failed: {e}")
            return None

    def enroll_device(self, device_name: str, platform: str = "unknown") -> str:
        """Enroll a new device and generate an enrollment token."""
        import uuid
        device_id = str(uuid.uuid4())
        device = DeviceIdentity(
            device_id=device_id,
            device_name=device_name,
            platform=platform,
            status=DeviceStatus.ENROLLED
        )
        self.registry.register_device(device)
        return self.generate_enrollment_token(device_id)

    def revoke_device(self, device_id: str):
        """Revoke a device."""
        self.registry.revoke_device(device_id)
        # Disconnect if currently connected
        self.remove_sidecar(device_id)

    async def connect_sidecar(self, sidecar_id: str, websocket) -> SidecarChannel:
        """Accepts a WS connection, wraps it in SidecarChannel, and registers it."""
        device = self.registry.get_device(sidecar_id)
        if not device or device.status == DeviceStatus.REVOKED:
            raise PermissionError("Device not enrolled or revoked.")
            
        channel = SidecarChannel(sidecar_id, websocket, self.registry)
        self._connected_sidecars[sidecar_id] = channel
        self.channel_manager.register_channel(channel)
        
        self.registry.update_connection_state(sidecar_id, ConnectionState.CONNECTING)
        await channel.start()
        self.registry.update_connection_state(sidecar_id, ConnectionState.READY)
        
        return channel

    def remove_sidecar(self, sidecar_id: str):
        channel = self._connected_sidecars.pop(sidecar_id, None)
        if channel:
            self.channel_manager.unregister_channel(channel.channel_id)
        self.registry.update_connection_state(sidecar_id, ConnectionState.DISCONNECTED)

    def get_sidecar(self, sidecar_id: str) -> Optional[SidecarChannel]:
        return self._connected_sidecars.get(sidecar_id)

    def list_sidecars(self) -> List[SidecarChannel]:
        return list(self._connected_sidecars.values())
