import sqlite3
import json
from pathlib import Path
from typing import List, Optional, Dict
import logging
from datetime import datetime, timezone
from core.devices.models import DeviceIdentity, DeviceStatus, ConnectionState, SidecarCapability

logger = logging.getLogger(__name__)

class DeviceRegistry:
    def __init__(self, db_path: str = ".data/devices.db"):
        self.db_path = db_path
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn_str = str(self.db_path)
        else:
            self._conn_str = "file::memory:?cache=shared"
        self._init_db()

    def _get_conn(self):
        return sqlite3.connect(self._conn_str, uri=(self.db_path == ":memory:"))

    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS devices (
                    device_id TEXT PRIMARY KEY,
                    device_name TEXT NOT NULL,
                    device_type TEXT NOT NULL,
                    platform TEXT,
                    client_version TEXT,
                    capabilities TEXT,
                    status TEXT NOT NULL,
                    connection_state TEXT NOT NULL,
                    last_seen TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

    def _row_to_device(self, row: tuple) -> DeviceIdentity:
        capabilities = []
        if row[5]:
            try:
                cap_strs = json.loads(row[5])
                capabilities = [SidecarCapability(c) for c in cap_strs]
            except Exception as e:
                logger.error(f"Error parsing capabilities: {e}")

        return DeviceIdentity(
            device_id=row[0],
            device_name=row[1],
            device_type=row[2],
            platform=row[3],
            client_version=row[4],
            capabilities=capabilities,
            status=DeviceStatus(row[6]),
            connection_state=ConnectionState(row[7]),
            last_seen=datetime.fromisoformat(row[8]) if row[8] else None,
            created_at=datetime.fromisoformat(row[9]),
            updated_at=datetime.fromisoformat(row[10])
        )

    def register_device(self, device: DeviceIdentity) -> None:
        device.updated_at = datetime.now(timezone.utc)
        caps = json.dumps([c.value for c in device.capabilities])
        
        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO devices (
                    device_id, device_name, device_type, platform, client_version, 
                    capabilities, status, connection_state, last_seen, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                device.device_id, device.device_name, device.device_type, device.platform,
                device.client_version, caps, device.status.value, device.connection_state.value,
                device.last_seen.isoformat() if device.last_seen else None,
                device.created_at.isoformat(), device.updated_at.isoformat()
            ))

    def get_device(self, device_id: str) -> Optional[DeviceIdentity]:
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT * FROM devices WHERE device_id = ?", (device_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_device(row)
        return None

    def update_status(self, device_id: str, status: DeviceStatus):
        with self._get_conn() as conn:
            conn.execute("UPDATE devices SET status = ?, updated_at = ? WHERE device_id = ?",
                         (status.value, datetime.now(timezone.utc).isoformat(), device_id))

    def update_connection_state(self, device_id: str, state: ConnectionState):
        now = datetime.now(timezone.utc)
        with self._get_conn() as conn:
            conn.execute("UPDATE devices SET connection_state = ?, last_seen = ?, updated_at = ? WHERE device_id = ?",
                         (state.value, now.isoformat(), now.isoformat(), device_id))

    def list_devices(self) -> List[DeviceIdentity]:
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT * FROM devices")
            return [self._row_to_device(row) for row in cursor.fetchall()]

    def revoke_device(self, device_id: str):
        self.update_status(device_id, DeviceStatus.REVOKED)
        self.update_connection_state(device_id, ConnectionState.DISCONNECTED)
