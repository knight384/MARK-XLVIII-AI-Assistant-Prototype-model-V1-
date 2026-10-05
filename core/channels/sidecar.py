import asyncio
import logging
from typing import Dict, Any, Optional

from core.channels.base import Channel, ChannelType, ChannelMessage, ChannelEvent

logger = logging.getLogger(__name__)

class SidecarChannel(Channel):
    """
    Channel representing a single remote device/sidecar connection.
    Translates raw WebSocket JSON/Binary into MARK-native ChannelMessages.
    """
    
    def __init__(self, sidecar_id: str, websocket, registry):
        super().__init__(f"sidecar_{sidecar_id}", ChannelType.WEBSOCKET)
        self.sidecar_id = sidecar_id
        self._ws = websocket
        self._registry = registry
        self._running = False
        self._recv_task = None
        self.state = "CONNECTED" # CONNECTING, AUTHENTICATING, CONNECTED, READY, DISCONNECTED
        
    async def start(self):
        self._running = True
        self.state = "READY"
        self._recv_task = asyncio.create_task(self._recv_loop())
        logger.info(f"[{self.__class__.__name__}] Started sidecar channel: {self.channel_id}")
        await self.send_event(ChannelEvent("channel.connected", {"sidecar_id": self.sidecar_id}))

    async def stop(self):
        self._running = False
        self.state = "DISCONNECTED"
        if self._recv_task:
            self._recv_task.cancel()
        try:
            await self._ws.close()
        except Exception:
            pass
        logger.info(f"[{self.__class__.__name__}] Stopped sidecar channel: {self.channel_id}")
        await self.send_event(ChannelEvent("channel.disconnected", {"sidecar_id": self.sidecar_id}))

    async def _recv_loop(self):
        """Consume messages from the WebSocket."""
        try:
            from fastapi import WebSocketDisconnect
            while self._running:
                data = await self._ws.receive()
                if "text" in data:
                    # Parse protocol
                    import json
                    try:
                        msg = json.loads(data["text"])
                        await self._handle_protocol_message(msg)
                    except json.JSONDecodeError:
                        logger.warning(f"[SidecarChannel] Malformed JSON from {self.sidecar_id}")
                elif "bytes" in data:
                    # Binary data (e.g., audio chunks)
                    await self._handle_binary_message(data["bytes"])
        except Exception as e:
            if self._running:
                logger.warning(f"[SidecarChannel] Error receiving from {self.sidecar_id}: {e}")
        finally:
            if self._running:
                # Cleanup if connection drops unexpectedly
                await self.stop()

    async def _handle_protocol_message(self, msg: dict):
        msg_type = msg.get("type")
        if msg_type == "register":
            device = self._registry.get_device(self.sidecar_id)
            if device:
                # Update device info based on registration payload
                device.platform = msg.get("platform", device.platform)
                device.client_version = msg.get("version", device.client_version)
                from core.devices.models import SidecarCapability
                caps_list = msg.get("capabilities", [])
                capabilities = []
                for cap in caps_list:
                    try:
                        capabilities.append(SidecarCapability(cap))
                    except ValueError:
                        pass
                device.capabilities = capabilities
                self._registry.register_device(device)
                logger.info(f"[SidecarChannel] Registered sidecar {self.sidecar_id} on {device.platform} with capabilities: {caps_list}")
                
        elif msg_type == "capabilities_update":
            device = self._registry.get_device(self.sidecar_id)
            if device:
                from core.devices.models import SidecarCapability
                caps_list = msg.get("capabilities", [])
                capabilities = []
                for cap in caps_list:
                    try:
                        capabilities.append(SidecarCapability(cap))
                    except ValueError:
                        pass
                device.capabilities = capabilities
                self._registry.register_device(device)
                logger.info(f"[SidecarChannel] Updated capabilities for {self.sidecar_id}: {caps_list}")

        elif msg_type == "text_message":
            # Standard typed text
            text = msg.get("text", "")
            if text:
                logger.info(f"[SidecarChannel] Text from {self.sidecar_id}: {text}")
                await self._emit_message(ChannelMessage(content=text, source=self.channel_id, metadata={"sidecar_id": self.sidecar_id}))
        elif msg_type == "rpc_request":
            # Sidecar is trying to do an RPC. We must pass this to the Runtime to enforce Policy Engine.
            # Convert to a ChannelMessage or emit a specific event that a Runtime Agent handles.
            # Step 15: "Never allow Sidecar -> arbitrary tool... must follow SidecarChannel -> ChannelManager -> Runtime -> Agent/Workflow -> ToolExecutor -> PolicyEngine"
            # So we emit it as a structured request event.
            await self._emit_message(ChannelMessage(
                content=f"RPC Request: {msg.get('method')}",
                source=self.channel_id,
                metadata={
                    "is_rpc": True,
                    "method": msg.get("method"),
                    "params": msg.get("params", {}),
                    "rpc_id": msg.get("id")
                }
            ))
        elif msg_type == "event":
            # Forward sidecar events
            event_name = msg.get("event", "unknown")
            await self._emit_message(ChannelMessage(
                content=f"Event: {event_name}",
                source=self.channel_id,
                metadata={"is_event": True, "event_name": event_name, "payload": msg.get("payload", {})}
            ))
        else:
            logger.debug(f"[SidecarChannel] Unhandled message type '{msg_type}' from {self.sidecar_id}")

    async def _handle_binary_message(self, data: bytes):
        """Audio over sidecar (Step 13)"""
        # Buffer this or emit it to a connected VoiceChannel/STT.
        # Since Phase 13 treats VoiceChannel as the audio handler, 
        # SidecarChannel might just emit the audio bytes via the manager.
        await self._emit_message(ChannelMessage(
            content="[Audio Data]",
            source=self.channel_id,
            metadata={"is_audio": True, "audio_bytes": data}
        ))

    async def send_text(self, text: str):
        if self.state == "READY":
            await self._ws.send_json({"type": "text_message", "text": text})

    async def send_audio(self, audio_data: bytes):
        """Send bound audio chunks to sidecar"""
        if self.state == "READY":
            await self._ws.send_bytes(audio_data)

    async def send_event(self, event: ChannelEvent):
        """Send events (including RPC responses) back to sidecar"""
        if self.state == "READY":
            await self._ws.send_json({
                "type": "event",
                "event": event.event_type,
                "payload": event.data
            })
            
    async def send_rpc_response(self, rpc_id: str, result: Any = None, error: Any = None):
        """Send an RPC response back."""
        if self.state == "READY":
            payload = {"type": "rpc_response", "id": rpc_id}
            if error:
                payload["error"] = error
            else:
                payload["result"] = result
            await self._ws.send_json(payload)
