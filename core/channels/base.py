from abc import ABC, abstractmethod
from typing import Any, Callable, Awaitable, Optional
from enum import Enum

class ChannelType(Enum):
    TEXT = "text"
    VOICE = "voice"
    WEBSOCKET = "websocket"
    TERMINAL = "terminal"

class ChannelMessage:
    def __init__(self, content: str, source: str, metadata: Optional[dict] = None):
        self.content = content
        self.source = source
        self.metadata = metadata or {}

class ChannelEvent:
    def __init__(self, event_type: str, data: Any):
        self.event_type = event_type
        self.data = data

class Channel(ABC):
    def __init__(self, channel_id: str, channel_type: ChannelType):
        self.channel_id = channel_id
        self.channel_type = channel_type
        self._on_message_callback: Optional[Callable[[ChannelMessage], Awaitable[None]]] = None

    def set_on_message(self, callback: Callable[[ChannelMessage], Awaitable[None]]):
        self._on_message_callback = callback

    async def _emit_message(self, msg: ChannelMessage):
        if self._on_message_callback:
            await self._on_message_callback(msg)

    @abstractmethod
    async def start(self):
        pass

    @abstractmethod
    async def stop(self):
        pass

    @abstractmethod
    async def send_text(self, text: str):
        pass

    @abstractmethod
    async def send_audio(self, audio_data: bytes):
        pass

    @abstractmethod
    async def send_event(self, event: ChannelEvent):
        pass
