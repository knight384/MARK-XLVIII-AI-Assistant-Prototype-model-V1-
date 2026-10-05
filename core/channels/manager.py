import asyncio
import logging
from typing import Dict, List, Optional
from core.channels.base import Channel, ChannelMessage, ChannelEvent

logger = logging.getLogger(__name__)

class ChannelManager:
    """Manages all interaction channels (Voice, WebSocket, Terminal, etc.)."""
    
    def __init__(self):
        self._channels: Dict[str, Channel] = {}
        self._running = False
        
    def register_channel(self, channel: Channel):
        if channel.channel_id in self._channels:
            raise ValueError(f"Channel {channel.channel_id} already registered.")
        
        self._channels[channel.channel_id] = channel
        channel.set_on_message(self._handle_channel_message)
        logger.info(f"[ChannelManager] Registered channel {channel.channel_id} ({channel.channel_type.name})")

    def unregister_channel(self, channel_id: str):
        if channel_id in self._channels:
            del self._channels[channel_id]
            logger.info(f"[ChannelManager] Unregistered channel {channel_id}")

    def get_channel(self, channel_id: str) -> Optional[Channel]:
        return self._channels.get(channel_id)

    def list_channels(self) -> List[Channel]:
        return list(self._channels.values())

    async def _handle_channel_message(self, msg: ChannelMessage):
        """Route incoming messages from any channel to the appropriate MARK Runtime service."""
        logger.info(f"[ChannelManager] Received message from {msg.source}: {msg.content}")
        # In a full implementation, this routes through the EventBus, PolicyEngine,
        # or directly to an LLM Session/Agent for response.
        # For now we broadcast it out.
        await self.broadcast_text(f"MARK received: {msg.content}")

    async def broadcast_text(self, text: str):
        """Broadcast text to all connected channels."""
        for ch in self._channels.values():
            try:
                await ch.send_text(text)
            except Exception as e:
                logger.error(f"[ChannelManager] Error broadcasting to {ch.channel_id}: {e}")

    async def broadcast_audio(self, audio_data: bytes):
        """Broadcast audio data to all connected channels that support audio."""
        for ch in self._channels.values():
            try:
                await ch.send_audio(audio_data)
            except Exception as e:
                logger.error(f"[ChannelManager] Error broadcasting audio to {ch.channel_id}: {e}")

    async def broadcast_event(self, event: ChannelEvent):
        """Broadcast structured events to all connected channels."""
        for ch in self._channels.values():
            try:
                await ch.send_event(event)
            except Exception as e:
                logger.error(f"[ChannelManager] Error broadcasting event to {ch.channel_id}: {e}")

    async def start(self):
        self._running = True
        for ch in self._channels.values():
            await ch.start()
        logger.info("[ChannelManager] Started.")

    async def stop(self):
        self._running = False
        for ch in list(self._channels.values()):
            await ch.stop()
        logger.info("[ChannelManager] Stopped.")
