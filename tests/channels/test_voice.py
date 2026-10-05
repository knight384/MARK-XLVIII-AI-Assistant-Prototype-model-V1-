import pytest
import asyncio
import numpy as np
from core.channels.voice import VoiceChannel, STTAdapter, TTSAdapter
from core.channels.base import ChannelEvent, ChannelMessage
from unittest.mock import AsyncMock, MagicMock

class MockSTTAdapter(STTAdapter):
    def __init__(self):
        super().__init__()
        self.transcribe_buffer = AsyncMock(return_value="mock transcript")

class MockTTSAdapter(TTSAdapter):
    def __init__(self):
        self.speak = MagicMock()
        self.stop = MagicMock()
        self._is_playing = False
        
    @property
    def is_playing(self) -> bool:
        return self._is_playing

@pytest.mark.asyncio
async def test_voice_channel_lifecycle():
    stt = MockSTTAdapter()
    tts = MockTTSAdapter()
    vc = VoiceChannel("test_voice", stt, tts)
    
    assert vc.state == "IDLE"
    await vc.start()
    assert vc.state == "IDLE"
    
    # Simulate VAD triggering a process_utterance
    dummy_audio = np.zeros(16000, dtype="float32")
    
    received_msgs = []
    async def mock_callback(msg: ChannelMessage):
        received_msgs.append(msg)
        
    vc.set_on_message(mock_callback)
    
    await vc._process_utterance(dummy_audio)
    
    assert stt.transcribe_buffer.called
    assert len(received_msgs) == 1
    assert received_msgs[0].content == "mock transcript"
    
    await vc.stop()
    assert vc.state == "DISABLED"

@pytest.mark.asyncio
async def test_voice_channel_barge_in():
    stt = MockSTTAdapter()
    tts = MockTTSAdapter()
    tts._is_playing = True # Simulate TTS is currently speaking
    
    vc = VoiceChannel("test_voice", stt, tts)
    await vc.start()
    
    dummy_audio = np.zeros(16000, dtype="float32")
    await vc._process_utterance(dummy_audio)
    
    # Should have called tts.stop() due to barge-in
    assert tts.stop.called
    
    await vc.stop()
