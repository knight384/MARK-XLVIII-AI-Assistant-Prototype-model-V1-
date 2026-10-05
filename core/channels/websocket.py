import asyncio
import logging
from core.channels.base import Channel, ChannelType, ChannelMessage, ChannelEvent
from dashboard.server import DashboardServer

logger = logging.getLogger(__name__)

class WebSocketChannel(Channel):
    """Integrates the Web UI Dashboard as a communication channel."""
    
    def __init__(self, dashboard: DashboardServer, channel_id: str = "dashboard"):
        super().__init__(channel_id, ChannelType.WEBSOCKET)
        self.dashboard = dashboard
        self._poll_task = None
        self._running = False

    async def start(self):
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_commands())
        logger.info(f"[{self.__class__.__name__}] Started polling dashboard commands.")

    async def stop(self):
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
        logger.info(f"[{self.__class__.__name__}] Stopped.")

    async def _poll_commands(self):
        while self._running:
            try:
                # Dashboard puts incoming text here
                text = await self.dashboard._command_queue.get()
                msg = ChannelMessage(content=text, source=self.channel_id)
                await self._emit_message(msg)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[{self.__class__.__name__}] Error reading command queue: {e}")

    async def send_text(self, text: str):
        # Format for the Web UI (it expects dicts mapped to specific event types)
        # Type "log" simulates the Jarvis log output on the UI.
        from datetime import datetime
        await self.dashboard.broadcast({
            "type": "log",
            "speaker": "jarvis",
            "text": text,
            "ts": datetime.now().isoformat()
        })

    async def send_audio(self, audio_data: bytes):
        """Audio streaming to browser clients."""
        # Typically requires a specific binary websocket endpoint.
        # dashboard/server doesn't have an outbound pcm stream built-in right now except via Gemini, 
        # but in Phase 13 we would implement this if needed.
        pass

    async def send_event(self, event: ChannelEvent):
        # Pass structured events directly to the dashboard broadcast
        await self.dashboard.broadcast({
            "type": "event",
            "event_type": event.event_type,
            "data": event.data
        })
