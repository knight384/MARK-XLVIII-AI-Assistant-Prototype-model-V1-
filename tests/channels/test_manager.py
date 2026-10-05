import pytest
import asyncio
from typing import List
from core.channels.base import Channel, ChannelType, ChannelMessage, ChannelEvent
from core.channels.manager import ChannelManager

class MockChannel(Channel):
    def __init__(self, channel_id: str):
        super().__init__(channel_id, ChannelType.TEXT)
        self.sent_texts: List[str] = []
        self.sent_audio: List[bytes] = []
        self.sent_events: List[ChannelEvent] = []
        self.started = False

    async def start(self):
        self.started = True

    async def stop(self):
        self.started = False

    async def send_text(self, text: str):
        self.sent_texts.append(text)

    async def send_audio(self, audio_data: bytes):
        self.sent_audio.append(audio_data)

    async def send_event(self, event: ChannelEvent):
        self.sent_events.append(event)
        
    async def simulate_receive(self, text: str):
        msg = ChannelMessage(content=text, source=self.channel_id)
        await self._emit_message(msg)

@pytest.mark.asyncio
async def test_channel_manager_registration():
    mgr = ChannelManager()
    ch1 = MockChannel("mock1")
    mgr.register_channel(ch1)
    
    assert mgr.get_channel("mock1") is ch1
    assert len(mgr.list_channels()) == 1
    
    with pytest.raises(ValueError):
        mgr.register_channel(ch1)
        
    mgr.unregister_channel("mock1")
    assert len(mgr.list_channels()) == 0

@pytest.mark.asyncio
async def test_channel_manager_broadcast():
    mgr = ChannelManager()
    ch1 = MockChannel("mock1")
    ch2 = MockChannel("mock2")
    mgr.register_channel(ch1)
    mgr.register_channel(ch2)
    
    await mgr.broadcast_text("Hello World")
    assert "Hello World" in ch1.sent_texts
    assert "Hello World" in ch2.sent_texts
    
    await mgr.broadcast_audio(b"audio")
    assert b"audio" in ch1.sent_audio
    assert b"audio" in ch2.sent_audio
    
    event = ChannelEvent("test", {"key": "value"})
    await mgr.broadcast_event(event)
    assert event in ch1.sent_events
    assert event in ch2.sent_events

@pytest.mark.asyncio
async def test_channel_manager_routing():
    mgr = ChannelManager()
    ch1 = MockChannel("mock1")
    mgr.register_channel(ch1)
    
    await ch1.simulate_receive("Ping")
    
    # Manager default implementation echoes back "MARK received: Ping"
    assert "MARK received: Ping" in ch1.sent_texts
