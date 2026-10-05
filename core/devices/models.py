from enum import Enum
from typing import List, Optional, Dict
from pydantic import BaseModel, Field
from datetime import datetime, timezone

class DeviceStatus(str, Enum):
    UNENROLLED = "unenrolled"
    ENROLLED = "enrolled"
    REVOKED = "revoked"

class ConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    READY = "ready"
    DEGRADED = "degraded"

class SidecarCapability(str, Enum):
    TEXT = "text"
    MICROPHONE = "microphone"
    SPEAKER = "speaker"
    AUDIO_STREAM = "audio_stream"
    SCREEN = "screen"
    CAMERA = "camera"
    KEYBOARD = "keyboard"
    MOUSE = "mouse"
    FILES = "files"
    NOTIFICATIONS = "notifications"
    BROWSER = "browser"
    OCR = "ocr"

class DeviceIdentity(BaseModel):
    device_id: str
    device_name: str
    device_type: str = "sidecar"
    platform: Optional[str] = None
    client_version: Optional[str] = None
    capabilities: List[SidecarCapability] = Field(default_factory=list)
    status: DeviceStatus = DeviceStatus.UNENROLLED
    connection_state: ConnectionState = ConnectionState.DISCONNECTED
    last_seen: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict:
        return {
            "device_id": self.device_id,
            "device_name": self.device_name,
            "device_type": self.device_type,
            "platform": self.platform,
            "client_version": self.client_version,
            "capabilities": [c.value for c in self.capabilities],
            "status": self.status.value,
            "connection_state": self.connection_state.value,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }
