import asyncio
import logging
import threading
import time
import numpy as np
try:
    import sounddevice as sd
    _SD_AVAILABLE = True
except ImportError:
    sd = None
    _SD_AVAILABLE = False
    
from typing import Optional, Callable
from collections import deque

from core.channels.base import Channel, ChannelType, ChannelMessage, ChannelEvent
from core.stt import WhisperSTT, VoskSTT
from core.tts import create_tts_player, TTSPlayer

logger = logging.getLogger(__name__)

class STTAdapter:
    """Base Adapter for STT engines."""
    def __init__(self):
        pass
        
    async def transcribe_buffer(self, audio_data: np.ndarray) -> str:
        raise NotImplementedError
        
    async def process_stream(self, audio_bytes: bytes) -> tuple[str, bool]:
        raise NotImplementedError


class WhisperSTTAdapter(STTAdapter):
    """Adapts WhisperSTT for the VoiceChannel."""
    def __init__(self, whisper: WhisperSTT):
        super().__init__()
        self.whisper = whisper
        
    async def transcribe_buffer(self, audio_data: np.ndarray) -> str:
        # Offload transcription to thread to avoid blocking event loop
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.whisper.transcribe, audio_data)

    async def process_stream(self, audio_bytes: bytes) -> tuple[str, bool]:
        # Whisper doesn't stream well, simulate by failing back to buffering.
        raise NotImplementedError("Whisper does not support true streaming.")


class TTSAdapter:
    """Adapts TTSPlayer for the VoiceChannel."""
    def __init__(self, tts_player: TTSPlayer):
        self.tts = tts_player
        
    def speak(self, text: str, on_start=None, on_done=None):
        self.tts.speak(text, on_start, on_done)
        
    def stop(self):
        self.tts.stop()

    @property
    def is_playing(self) -> bool:
        return self.tts.is_playing


class VoiceChannel(Channel):
    """
    MARK-native Voice Channel.
    Owns microphone capture, STT routing, TTS playback, and audio lifecycle state.
    """
    
    # Audio constants from JarvisLive
    SEND_SAMPLE_RATE = 16000
    CHANNELS = 1
    CHUNK_SIZE = 1024

    def __init__(self, channel_id: str = "voice", stt_adapter: STTAdapter = None, tts_adapter: TTSAdapter = None):
        super().__init__(channel_id, ChannelType.VOICE)
        self.stt = stt_adapter
        self.tts = tts_adapter
        
        # State
        self.state = "IDLE" # DISABLED, IDLE, LISTENING, PROCESSING, SPEAKING, INTERRUPTED, ERROR
        self.muted = False
        
        self._running = False
        self._mic_stream = None
        
        # VAD & Buffering
        self._audio_buffer = []
        self._silence_chunks = 0
        self._is_recording = False
        self._energy_threshold = 0.01  # Basic RMS threshold
        self._silence_limit = int(1.5 * self.SEND_SAMPLE_RATE / self.CHUNK_SIZE)  # 1.5 seconds silence to split
        self._stream_raw_audio = False # Set to true to bypass STT and stream raw audio
        
        # Concurrency
        self._tasks = []
        
    def _set_state(self, state: str):
        if self.state != state:
            self.state = state
            asyncio.run_coroutine_threadsafe(
                self._emit_event("voice.state_changed", {"state": state}),
                asyncio.get_event_loop()
            )

    async def _emit_event(self, event_type: str, data: dict):
        # Fire event upward via ChannelManager
        await self.send_event(ChannelEvent(event_type, data))
        
    async def start(self):
        self._running = True
        
        # Ensure adapters exist
        if not self.stt:
            logger.info(f"[{self.__class__.__name__}] Defaulting to WhisperSTT.")
            # Default fallback to whisper
            self.stt = WhisperSTTAdapter(WhisperSTT())
            
        if not self.tts:
            logger.info(f"[{self.__class__.__name__}] Defaulting to TTS Engine.")
            self.tts = TTSAdapter(create_tts_player({"tts_engine": "edgetts"}))

        loop = asyncio.get_event_loop()
        
        # Mic Callback
        def _mic_callback(indata, frames, time_info, status):
            if status:
                logger.warning(f"[Mic] Status: {status}")
                
            if self.muted or self.state in ["SPEAKING", "DISABLED", "INTERRUPTED"]:
                return
                
            # Basic Voice Activity Detection using RMS energy
            audio_chunk = indata[:, 0].copy() # Mono
            rms = np.sqrt(np.mean(audio_chunk**2))
            
            if rms > self._energy_threshold:
                if not self._is_recording:
                    self._is_recording = True
                    self._audio_buffer = []
                    loop.call_soon_threadsafe(self._set_state, "LISTENING")
                self._silence_chunks = 0
            else:
                if self._is_recording:
                    self._silence_chunks += 1
            
            if self._is_recording:
                self._audio_buffer.append(audio_chunk)
                if self._stream_raw_audio:
                    # Stream immediately
                    raw_bytes = indata.tobytes()
                    loop.call_soon_threadsafe(
                        asyncio.create_task,
                        self._emit_message(ChannelMessage(
                            content="[Raw Audio Stream]",
                            source=self.channel_id,
                            metadata={"is_audio": True, "audio_bytes": raw_bytes}
                        ))
                    )
                
                # Check if silence limit reached
                if self._silence_chunks > self._silence_limit:
                    self._is_recording = False
                    
                    if not self._stream_raw_audio:
                        complete_audio = np.concatenate(self._audio_buffer)
                        # Offload to STT
                        if len(complete_audio) > self.SEND_SAMPLE_RATE * 0.5: # At least 0.5 sec
                            loop.call_soon_threadsafe(self._handle_utterance, complete_audio)
                    
                    self._audio_buffer = []

        try:
            if not _SD_AVAILABLE:
                raise RuntimeError("sounddevice module not available in this environment")
                
            self._mic_stream = sd.InputStream(
                samplerate=self.SEND_SAMPLE_RATE,
                channels=self.CHANNELS,
                dtype="float32", # Whisper natively wants float32
                blocksize=self.CHUNK_SIZE,
                callback=_mic_callback
            )
            self._mic_stream.start()
            self._set_state("IDLE")
            logger.info(f"[{self.__class__.__name__}] Started listening on mic.")
        except Exception as e:
            logger.error(f"[{self.__class__.__name__}] Mic init error: {e}")
            self._set_state("ERROR")
            
    def _handle_utterance(self, audio: np.ndarray):
        """Called thread-safely when an utterance buffer completes."""
        asyncio.create_task(self._process_utterance(audio))
        
    async def _process_utterance(self, audio: np.ndarray):
        self._set_state("PROCESSING")
        try:
            # Barge-in: If STT gets speech, interrupt TTS
            if self.tts.is_playing:
                logger.info(f"[{self.__class__.__name__}] Barge-in detected, stopping TTS.")
                self.tts.stop()
                self._set_state("INTERRUPTED")
                await self._emit_event("voice.interrupted", {})
                
            transcript = await self.stt.transcribe_buffer(audio)
            
            if transcript.strip():
                logger.info(f"[VoiceChannel] User: {transcript}")
                await self._emit_event("voice.transcript_final", {"text": transcript})
                
                # Send text upward to the manager -> runtime
                msg = ChannelMessage(content=transcript, source=self.channel_id)
                await self._emit_message(msg)
            else:
                self._set_state("IDLE")
        except Exception as e:
            logger.error(f"[VoiceChannel] STT error: {e}")
            self._set_state("ERROR")

    async def stop(self):
        self._running = False
        if self._mic_stream:
            self._mic_stream.stop()
            self._mic_stream.close()
            self._mic_stream = None
        self._set_state("DISABLED")
        logger.info(f"[{self.__class__.__name__}] Stopped.")

    async def send_text(self, text: str):
        """TTS reads the response."""
        self._set_state("SPEAKING")
        await self._emit_event("response.started", {})
        
        def _on_done():
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(self._set_state, "IDLE")
            loop.call_soon_threadsafe(
                asyncio.create_task,
                self._emit_event("response.completed", {})
            )
            
        def _on_start():
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(
                asyncio.create_task,
                self._emit_event("audio.playback_started", {})
            )
            
        # TTS generation can block, so we run in executor thread
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.tts.speak, text, _on_start, _on_done)

    async def send_audio(self, audio_data: bytes):
        """Raw audio stream directly out to speaker (e.g. from Gemini Live)."""
        logger.debug(f"[VoiceChannel] Playing {len(audio_data)} bytes of raw audio.")
        if _SD_AVAILABLE:
            try:
                # Assuming PCM 24kHz 16-bit mono as standard output from Gemini
                audio_array = np.frombuffer(audio_data, dtype=np.int16)
                sd.play(audio_array, 24000)
                sd.wait()
            except Exception as e:
                logger.error(f"[VoiceChannel] Error playing raw audio: {e}")

    async def send_event(self, event: ChannelEvent):
        """Events are largely passed upward, but can trigger channel state changes here."""
        if self._on_message_callback:
            # We wrap this to let Manager know of the event
            pass
