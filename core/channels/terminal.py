import asyncio
import sys
import logging
from typing import Optional
from core.channels.base import Channel, ChannelType, ChannelMessage, ChannelEvent

logger = logging.getLogger(__name__)

class TerminalChannel(Channel):
    """A basic terminal-based interaction channel for MARK."""
    
    def __init__(self, channel_id: str = "terminal"):
        super().__init__(channel_id, ChannelType.TERMINAL)
        self._listen_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        self._running = True
        self._listen_task = asyncio.create_task(self._listen_loop())
        logger.info("[TerminalChannel] Started.")

    async def stop(self):
        self._running = False
        if self._listen_task:
            self._listen_task.cancel()
        logger.info("[TerminalChannel] Stopped.")

    async def _listen_loop(self):
        """Asynchronously read from stdin."""
        loop = asyncio.get_event_loop()
        while self._running:
            try:
                line = await loop.run_in_executor(None, sys.stdin.readline)
                if not line:
                    break
                
                text = line.strip()
                if text:
                    msg = ChannelMessage(content=text, source=self.channel_id)
                    await self._emit_message(msg)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[TerminalChannel] Error reading stdin: {e}")

    async def send_text(self, text: str):
        # Using print to sys.stdout ensures output
        print(f"\n[MARK] {text}")
        sys.stdout.flush()

    async def send_audio(self, audio_data: bytes):
        # Terminal channel ignores audio data
        logger.debug(f"[TerminalChannel] Ignored {len(audio_data)} bytes of audio data.")

    async def send_event(self, event: ChannelEvent):
        # Dump structured events
        print(f"\n[Event - {event.event_type}] {event.data}")
        sys.stdout.flush()
