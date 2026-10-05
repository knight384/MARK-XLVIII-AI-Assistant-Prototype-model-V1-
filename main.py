import platform as _platform
import subprocess as _subprocess

# ── Nuclear: force CREATE_NO_WINDOW on EVERY subprocess call on Windows ───────
# This patches Popen itself, so no per-file flag is needed anywhere.
if _platform.system() == "Windows":
    _OrigPopen = _subprocess.Popen

    class _Popen(_OrigPopen):
        def __init__(self, args, **kw):
            kw["creationflags"] = kw.get("creationflags", 0) | _subprocess.CREATE_NO_WINDOW
            kw.pop("startupinfo", None)   # drop any stale/shared STARTUPINFO
            super().__init__(args, **kw)

    _subprocess.Popen = _Popen
# ─────────────────────────────────────────────────────────────────────────────

import asyncio
import logging
import re
import threading
import time
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

from google.genai import types
from ui import JarvisUI
from memory.memory_manager import (
    load_memory, format_memory_for_prompt,
)
from core.logging_setup import configure_logging, register_secret
from core.config import get_config_service
from core.llm.providers.gemini_live import GeminiLiveAdapter
from core.tools import get_default_registry, ToolContext, ToolExecutor

configure_logging()
logger = logging.getLogger(__name__)

# Phase 3: individual actions/*.py functions are no longer imported directly
# here — each is invoked lazily from inside its Tool wrapper in
# core/tools/definitions.py. Only cross-cutting runtime helpers stay imported
# in main.py itself.
from actions.system_monitor    import SystemMonitor
from actions.proactive         import ProactiveEngine


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR        = get_base_dir()
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"
LIVE_MODEL          = "models/gemini-2.5-flash-native-audio-preview-12-2025"
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024

_config = get_config_service()
if _config.migration_note:
    logger.info(_config.migration_note)


def _get_api_key() -> str:
    """Single application entry point for the Gemini API key (Phase 1: routed
    through ConfigService/SecretStore instead of a plaintext JSON read)."""
    key = _config.get_gemini_api_key()
    register_secret(key)  # ensure it's redacted from logs even if echoed accidentally
    return key


def _load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return (
            "You are JARVIS, Tony Stark's AI assistant. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool."
        )

_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)

def _clean_transcript(text: str) -> str:    
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    return text.strip()

# Phase 3: TOOL_DECLARATIONS is now generated from the Tool Registry
# (core/tools/) instead of being hardcoded here. This variable name is
# kept for backward compatibility with anything still referencing it.
from core.tools import get_default_registry, ToolContext, ToolExecutor
# Phase 4: registers the one additional `run_agent_task` tool that bridges
# into the multi-agent Orchestrator. Everything else about tool dispatch
# below is unchanged — Gemini decides whether to call it, like any other
# tool. See core/agent/entrypoint.py for the full rationale.
from core.agent import register_agent_tools

_tool_registry = get_default_registry()
register_agent_tools(_tool_registry)
_tool_executor = ToolExecutor(_tool_registry)
TOOL_DECLARATIONS = _tool_registry.generate_gemini_declarations()

# --- Plugin system ---


class JarvisLive:

    def __init__(self, ui: JarvisUI):
        self.ui             = ui
        self.session              = None
        self.audio_in_queue       = None
        self.out_queue            = None
        self._loop                = None
        self._is_speaking         = False
        self._speaking_lock       = threading.Lock()
        self._phone_active        = False   # True while phone mic is streaming; pauses PC mic
        self._pending_vision       = None    # (img_bytes, mime_type, question, angle) to inject after tool response
        self._vision_cam_active    = False   # True if camera was opened for vision → auto-close after response
        self._vision_close_pending = False   # True after vision injected; next turn_complete closes camera
        self._vision_last_time     = 0.0     # monotonic time of last screen_process call (cooldown guard)
        self._vision_busy          = False   # True while a vision capture/inject cycle is in flight
        self._interrupted          = False   # True while draining audio after user interrupt
        self.ui.on_text_command   = self._on_text_command
        self.ui.on_remote_clicked = self._make_remote_key
        self.ui.on_interrupt      = self.interrupt
        self._turn_done_event: asyncio.Event | None = None
        self._dashboard     = None
        self._briefing_sent    = False          # morning briefing fires once per process
        self._sys_monitor      = SystemMonitor()  # persistent cooldown state
        self._proactive        = ProactiveEngine()
        self._last_user_speech = time.monotonic()  # updated on every user utterance
        self._live_adapter     = GeminiLiveAdapter(api_key_getter=_get_api_key)
        self._channel_manager  = None

    def _make_remote_key(self):
        """Called from Qt main thread when user presses Remote Control."""
        if self._dashboard is None:
            self.ui.write_log(
                "SYS: Dashboard unavailable. "
                "Run: pip install fastapi \"uvicorn[standard]\" cryptography"
            )
            return None
        key    = self._dashboard.new_key()
        url    = self._dashboard.get_url()
        manual = self._dashboard.get_manual_url()
        return url, key, f"{url}/auto-login?key={key}", manual

    def _on_text_command(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted:
            self.ui.set_state("LISTENING")

    def interrupt(self) -> None:
        """Stop JARVIS mid-speech: drain queued audio and open mic immediately."""
        self._interrupted = True
        q = self.audio_in_queue
        if q:
            drained = 0
            while True:
                try:
                    q.get_nowait()
                    drained += 1
                except Exception:
                    break
            if drained:
                logger.info(f"[JARVIS] ✋ Interrupted — {drained} audio chunks discarded")
        self.set_speaking(False)
        if self._turn_done_event:
            self._turn_done_event.clear()
        self.ui.write_log("SYS: Interrupted — listening...")

    def speak(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        self.speak(f"Sir, {tool_name} encountered an error. {short}")

    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime

        memory     = load_memory()
        mem_str    = format_memory_for_prompt(memory)
        sys_prompt = _load_system_prompt()

        now      = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")
        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Right now it is: {time_str}\n"
            f"Use this to calculate exact times for reminders.\n\n"
        )

        parts = [time_ctx]
        if mem_str:
            parts.append(mem_str)
        parts.append(sys_prompt)

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": TOOL_DECLARATIONS}],
            session_resumption=types.SessionResumptionConfig(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Charon"
                    )
                )
            ),
        )

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        """Phase 3: routes through the Tool Registry / Tool Executor
        (core/tools/) instead of a hardcoded if/elif dispatcher. Special
        JARVIS-runtime-coupled tools (save_memory, screen_process,
        close_camera, shutdown_jarvis) get their needed state via
        ToolContext.extra['live'] — see core/tools/definitions.py."""
        name = fc.name
        args = dict(fc.args or {})

        logger.info(f"[JARVIS] 🔧 {name}  {args}")
        self.ui.set_state("THINKING")

        # Phase 6: dashboard-originated turns are marked via
        # self._pending_request_source (set by _process_dashboard_commands
        # right before relaying dashboard text into the session) so the
        # PolicyEngine can apply stricter remote-request rules. Single-use:
        # consumed and reset here so it only tags the tool call(s) that
        # immediately follow a dashboard-relayed turn, not the whole session.
        source = getattr(self, "_pending_request_source", "local_voice")
        self._pending_request_source = "local_voice"

        context = ToolContext(
            extra={"ui": self.ui, "speak": self.speak, "live": self},
            source=source, session_id=getattr(self, "_session_id", None),
        )
        tool_result = await _tool_executor.execute(name, args, context)
        result = tool_result.as_model_text()

        if not tool_result.success:
            logger.error(f"[JARVIS] Tool '{name}' failed: {tool_result.error}")
            self.speak_error(name, RuntimeError(tool_result.error or "unknown error"))

        if not self.ui.muted:
            self.ui.set_state("LISTENING")

        logger.info(f"[JARVIS] 📤 {name} → {str(result)[:80]}")

        response_payload = {"result": result}
        if tool_result.metadata.get("silent"):
            response_payload["silent"] = True

        return types.FunctionResponse(
            id=fc.id, name=name,
            response=response_payload
        )

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            await self.session.send_realtime_input(media=msg)

    async def _listen_audio(self):
        logger.info("[JARVIS] 🎤 Mic started")
        loop = asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
            with self._speaking_lock:
                jarvis_speaking = self._is_speaking
            if not jarvis_speaking and not self.ui.muted and not self._phone_active:
                data = indata.tobytes()
                loop.call_soon_threadsafe(
                    self.out_queue.put_nowait,
                    {"data": data, "mime_type": "audio/pcm"}
                )

        try:
            with sd.InputStream(
                samplerate=SEND_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                callback=callback,
            ):
                logger.info("[JARVIS] 🎤 Mic stream open")
                while True:
                    await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"[JARVIS] ❌ Mic: {e}")
            raise

    async def _receive_audio(self):
        logger.info("[JARVIS] 👂 Recv started")
        out_buf, in_buf = [], []

        try:
            while True:
                async for response in self.session.receive():

                    if response.data:
                        if self._interrupted:
                            pass  # discard: interrupted
                        else:
                            if self._turn_done_event and self._turn_done_event.is_set():
                                self._turn_done_event.clear()
                            # Split into ~50 ms chunks so interrupt() stops audio within 50 ms
                            # (24000 Hz × 2 bytes/sample × 0.05 s = 2400 bytes per slice)
                            _audio_data = response.data
                            _SLICE = 2400
                            for _i in range(0, len(_audio_data), _SLICE):
                                chunk = _audio_data[_i : _i + _SLICE]
                                if getattr(self, "_channel_manager", None):
                                    asyncio.create_task(self._channel_manager.broadcast_audio(chunk))

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt and txt != (out_buf[-1] if out_buf else ""):
                                out_buf.append(txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = _clean_transcript(sc.input_transcription.text)
                            if txt:
                                in_buf.append(txt)
                                self._last_user_speech = time.monotonic()

                        if sc.turn_complete:
                            if self._turn_done_event:
                                self._turn_done_event.set()

                            if self._interrupted:
                                self._interrupted = False
                                in_buf  = []
                                out_buf = []
                                continue

                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                self.ui.write_log(f"You: {full_in}")
                                if hasattr(self, "_channel_manager"):
                                    asyncio.create_task(self._channel_manager.broadcast_text(f"You: {full_in}"))
                            in_buf = []

                            full_out = " ".join(out_buf).strip()
                            if full_out:
                                self.ui.write_log(f"Jarvis: {full_out}")
                                if hasattr(self, "_channel_manager"):
                                    asyncio.create_task(self._channel_manager.broadcast_text(f"Jarvis: {full_out}"))
                            out_buf = []

                            # Vision injection: model finished tool-response turn → now send the image
                            if self._pending_vision and self.session:
                                import base64 as _b64
                                img_b, mime_t, question, angle = self._pending_vision
                                self._pending_vision = None
                                b64 = _b64.b64encode(img_b).decode("ascii")
                                logger.info(f"[Vision] 📤 {len(img_b):,} bytes (angle={angle}) → main session")
                                await self.session.send_client_content(
                                    turns={"parts": [
                                        {"inline_data": {"mime_type": mime_t, "data": b64}},
                                        {"text": question},
                                    ]},
                                    turn_complete=True,
                                )
                                # Mark next turn_complete behaviour depending on angle
                                if self._vision_cam_active:
                                    # Camera: keep busy until JARVIS finishes speaking the answer
                                    self._vision_cam_active    = False
                                    self._vision_close_pending = True
                                else:
                                    # Screen-only: no camera to close; release busy flag now
                                    self._vision_busy = False
                            elif self._vision_close_pending:
                                # This turn_complete IS the vision answer — close camera + release busy flag
                                self._vision_close_pending = False
                                self._vision_busy = False
                                async def _cam_close():
                                    await asyncio.sleep(2.0)
                                    self.ui.stop_camera_stream()
                                asyncio.create_task(_cam_close())

                    if response.tool_call:
                        fn_responses = []
                        for fc in response.tool_call.function_calls:
                            logger.info(f"[JARVIS] 📞 {fc.name}")
                            fr = await self._execute_tool(fc)
                            fn_responses.append(fr)
                        await self.session.send_tool_response(
                            function_responses=fn_responses
                        )
        except Exception as e:
            logger.error(f"[JARVIS] ❌ Recv: {e}")
            traceback.print_exc()
            raise

    # ── Morning briefing ────────────────────────────────────────────────────────

    async def _send_startup_briefing(self) -> None:
        """
        Two-phase briefing for instant perceived response:
          Phase 1 — immediate greeting (no tools, no fetch) → Jarvis speaks in <2s
          Phase 2 — news fetched in background, injected after greeting finishes
        """
        await asyncio.sleep(0.3)
        if not self.session:
            return

        # ── memory ───────────────────────────────────────────────────────────
        memory   = load_memory()
        identity = memory.get("identity", {})

        def _val(k: str) -> str:
            e = identity.get(k, {})
            return (e.get("value", "") if isinstance(e, dict) else str(e)).strip()

        lang = _val("language")
        name = _val("name")

        from datetime import datetime
        time_str = datetime.now().strftime("%H:%M")

        # ── Phase 1: instant greeting — one simple sentence ──────────────────
        lang_clause = f" Respond in {lang}." if lang else ""
        name_clause = f" Address the user as {name}." if name else ""
        p1 = (
            f"Greet the user, mention it is {time_str}, and say you are fetching today's news headlines now. "
            f"One short sentence only. Do not call any tools.{lang_clause}{name_clause}"
        )

        await self.session.send_client_content(
            turns={"parts": [{"text": p1}]},
            turn_complete=True,
        )
        self.ui.write_log("SYS: Briefing phase 1 (greeting) sent.")

        # ── Phase 2: fetch news in background, deliver after greeting plays ───
        async def _guarded_news():
            try:
                await self._briefing_news_phase(lang)
            except Exception as e:
                logger.error(f"[Briefing] Phase 2 error: {e}")
                self.ui.write_log(f"SYS: Briefing news phase failed: {e}")
        asyncio.create_task(_guarded_news())

    async def _briefing_news_phase(self, lang: str) -> None:
        """
        Sends phase-2 (news) to Gemini ~1.5 s after phase-1 is dispatched so
        Gemini starts working on it while phase-1 audio is still playing.
        """
        lang_str = f" Respond in {lang}." if lang else ""

        # 1.5 s is enough for Gemini to finish generating phase-1 audio on its
        # side (turn_complete) while the greeting is still being played locally.
        await asyncio.sleep(1.5)

        if not self.session:
            return

        p2 = (
            "[BRIEFING] Call web_search with mode='news' and query='top world news today' "
            "to find actual recent news articles with real event headlines (not just website names). "
            "After the search, say ONE specific news event from the results in one sentence, "
            f"then say the full list is displayed on screen.{lang_str}"
        )

        await self.session.send_client_content(
            turns={"parts": [{"text": p2}]},
            turn_complete=True,
        )
        self.ui.write_log("SYS: Briefing phase 2 (news) sent.")

    # ── System monitor ──────────────────────────────────────────────────────────

    async def _run_system_monitor(self) -> None:
        """Background task: voice alerts when metrics exceed thresholds."""
        while True:
            await asyncio.sleep(10)
            alert = await asyncio.to_thread(self._sys_monitor.check)
            if alert and self.session:
                try:
                    await self.session.send_client_content(
                        turns={"parts": [{"text": alert}]},
                        turn_complete=True,
                    )
                except Exception as e:
                    logger.warning(f"[Monitor] ⚠️ Could not send alert: {e}")

    # ── Proactive mode ──────────────────────────────────────────────────────────

    async def _run_proactive_mode(self) -> None:
        """
        Background task: periodically checks if the user has been silent long enough,
        then hands time + memory context to Gemini so it can decide what (if anything)
        to say proactively. No hardcoded rules — Gemini makes the call.
        """
        while True:
            await asyncio.sleep(60)   # evaluate once per minute

            if not self.session:
                continue

            with self._speaking_lock:
                speaking = self._is_speaking
            if speaking:
                continue

            if not self._proactive.should_trigger(self._last_user_speech):
                continue

            self._proactive.mark_triggered()

            try:
                memory = await asyncio.to_thread(load_memory)
                prompt = self._proactive.build_prompt(memory)
                await self.session.send_client_content(
                    turns={"parts": [{"text": prompt}]},
                    turn_complete=True,
                )
                self.ui.write_log("SYS: Proactive check-in.")
            except Exception as e:
                logger.warning(f"[Proactive] ⚠️ {e}")


    async def _handle_channel_message(self, msg):
        """Phase 13: Handle inbound ChannelMessage from any source."""
        if not self.session:
            return
            
        if msg.metadata.get("is_audio"):
            # Stream raw audio to Gemini Live
            audio_bytes = msg.metadata.get("audio_bytes")
            if audio_bytes:
                self.out_queue.put_nowait({"data": audio_bytes, "mime_type": "audio/pcm"})
        elif msg.metadata.get("is_rpc"):
            # Sidecar is directly invoking a tool over RPC
            method = msg.metadata.get("method")
            params = msg.metadata.get("params", {})
            rpc_id = msg.metadata.get("rpc_id")
            
            logger.info(f"[RPC] Request from {msg.source}: {method}")
            
            # Use local ToolExecutor to process the RPC.
            # This implicitly goes through PolicyEngine, ApprovalManager, etc.
            self._pending_request_source = msg.source
            context = ToolContext(
                extra={"ui": self.ui, "speak": self.speak, "live": self},
                source=msg.source, session_id=getattr(self, "_session_id", None),
            )
            
            try:
                # _tool_executor is global in main.py
                tool_result = await _tool_executor.execute(method, params, context)
                
                # Send the response back
                if hasattr(self, "_channel_manager") and self._channel_manager:
                    channel = self._channel_manager.get_channel(msg.source)
                    if channel and hasattr(channel, "send_rpc_response"):
                        if tool_result.success:
                            await channel.send_rpc_response(rpc_id, result=tool_result.as_model_text())
                        else:
                            await channel.send_rpc_response(rpc_id, error=tool_result.error)
            except Exception as e:
                logger.error(f"[RPC] Execution failed: {e}")
                if hasattr(self, "_channel_manager") and self._channel_manager:
                    channel = self._channel_manager.get_channel(msg.source)
                    if channel and hasattr(channel, "send_rpc_response"):
                        await channel.send_rpc_response(rpc_id, error=str(e))
        else:
            # Handle text message
            self._pending_request_source = msg.source
            await self.session.send_client_content(
                turns={"parts": [{"text": msg.content}]},
                turn_complete=True
            )
            self.ui.write_log(f"[{msg.source}]: {msg.content}")

    # ── main loop ───────────────────────────────────────────────────────────

    async def run(self):
        self._loop = asyncio.get_event_loop()
        # Dashboard logic is now managed by WebSocketChannel in main()
        self._dashboard = None

        while True:
            try:
                logger.info("[JARVIS] Connecting...")
                self.ui.set_state("THINKING")
                config = self._build_config()

                # Fresh client on every reconnect — avoids stale HTTP session state.
                # (Phase 2: client construction + connect() now live behind
                # GeminiLiveAdapter, the specialized realtime provider boundary —
                # see core/llm/providers/gemini_live.py. The send/receive/audio
                # loop below is completely unchanged.)
                async with (
                    self._live_adapter.connect(model=LIVE_MODEL, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session          = session
                    self.audio_in_queue   = asyncio.Queue()
                    self.out_queue        = asyncio.Queue(maxsize=200)
                    self._turn_done_event = asyncio.Event()

                    # Reset transient state that must not carry over from a previous session
                    self._pending_vision       = None
                    self._vision_cam_active    = False
                    self._vision_close_pending = False
                    self._vision_busy          = False
                    self._vision_last_time     = 0.0
                    self._interrupted          = False

                    logger.info("[JARVIS] Connected.")
                    self.ui.set_state("LISTENING")
                    self.ui.write_log("SYS: JARVIS online.")

                    if self._dashboard:
                        await self._dashboard.broadcast({"type": "status", "state": "active"})

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._run_system_monitor())
                    tg.create_task(self._run_proactive_mode())

                    # Morning briefing — fires once per process launch
                    if not self._briefing_sent:
                        self._briefing_sent = True
                        tg.create_task(self._send_startup_briefing())

            except KeyboardInterrupt:
                raise
            except SystemExit:
                raise
            except BaseException as e:
                # Catches both Exception and BaseExceptionGroup (Python 3.11+
                # TaskGroup raises BaseExceptionGroup when tasks are cancelled
                # externally, which `except Exception` would miss, letting the
                # exception escape the while-loop and causing asyncio.run() to
                # start shutdown — resulting in "executor after shutdown" errors).
                err_str = str(e)
                logger.error(f"[JARVIS] Error ({type(e).__name__}): {e}")
                traceback.print_exc()

                # Invalid API key — stop hammering the API, prompt re-configuration
                if "API key not valid" in err_str or "1007" in err_str:
                    self.ui.write_log("ERR: API key invalid — please re-enter your key.")
                    self.ui.set_state("SLEEPING")
                    self.ui.prompt_reconfig()
                    while not self.ui._win._ready:
                        await asyncio.sleep(1)
                    logger.info("[JARVIS] New API key saved — reconnecting...")
                    _conn_backoff = 3
                    continue

                # Network / timeout errors — log clearly and back off
                is_net_err = any(k in err_str for k in (
                    "TimeoutError", "timed out", "getaddrinfo", "CancelledError",
                    "ConnectionRefusedError", "OSError", "Cannot connect",
                ))
                if is_net_err:
                    _conn_backoff = min(getattr(self, "_conn_backoff", 3) * 2, 60)
                    self._conn_backoff = _conn_backoff
                    self.ui.write_log(
                        f"NET: Bağlantı kurulamadı — {_conn_backoff}s sonra tekrar deneniyor. "
                        "(VPN gerekiyor olabilir)"
                    )
                else:
                    self._conn_backoff = 3
            finally:
                self.session = None

            self.set_speaking(False)
            self.ui.set_state("SLEEPING")

            if self._dashboard:
                await self._dashboard.broadcast({"type": "status", "state": "sleeping"})

            delay = getattr(self, "_conn_backoff", 3)
            logger.info(f"[JARVIS] Reconnecting in {delay}s...")
            await asyncio.sleep(delay)

def setup_channels(runtime, jarvis):
    # Setup Phase 13 channels
    from core.channels.voice import VoiceChannel
    from core.channels.websocket import WebSocketChannel
    
    # 1. VoiceChannel (configured to stream raw PCM directly to Gemini Live)
    voice_ch = VoiceChannel("voice")
    voice_ch._stream_raw_audio = True
    runtime.channel_manager.register_channel(voice_ch)
    
    # 2. WebSocketChannel (Dashboard)
    try:
        from dashboard.server import DashboardServer
        # We give the dashboard instance to JarvisLive so it can broadcast
        jarvis._dashboard = DashboardServer()
        ws_ch = WebSocketChannel(jarvis._dashboard, "dashboard")
        runtime.channel_manager.register_channel(ws_ch)
    except Exception as e:
        logger.info(f"[Dashboard] Disabled: {e}")
        
    # Hook JarvisLive into ChannelManager
    jarvis._channel_manager = runtime.channel_manager
    async def _msg_handler(msg):
        await jarvis._handle_channel_message(msg)
    runtime.channel_manager._handle_channel_message = _msg_handler


def main():
    import sys
    from core.runtime.app import MarkRuntime
    from core.runtime.mode import RuntimeMode
    
    is_headless = "--headless" in sys.argv
    mode = RuntimeMode.HEADLESS if is_headless else RuntimeMode.DESKTOP
    
    runtime = MarkRuntime(mode=mode)
    
    if is_headless:
        from core.runtime.headless import HeadlessUI
        ui = HeadlessUI()
        
        async def headless_runner():
            await runtime.initialize()
            
            jarvis = JarvisLive(ui)
            setup_channels(runtime, jarvis)
            
            await runtime.start()
            
            # Start jarvis.run as task
            jarvis_task = asyncio.create_task(jarvis.run())
            
            try:
                # Wait until interrupted
                while True:
                    await asyncio.sleep(3600)
            except asyncio.CancelledError:
                pass
            finally:
                jarvis_task.cancel()
                await runtime.stop()
                
        try:
            asyncio.run(headless_runner())
        except KeyboardInterrupt:
            logger.info("\n🔴 Shutting down...")
    else:
        ui = JarvisUI("face.png")

        def runner():
            async def desktop_runner():
                await runtime.initialize()
                
                jarvis = JarvisLive(ui)
                setup_channels(runtime, jarvis)
                
                await runtime.start()
                
                ui.wait_for_api_key()
                
                jarvis_task = asyncio.create_task(jarvis.run())
                
                try:
                    await runtime.wait_until_shutdown()
                finally:
                    jarvis_task.cancel()
                    await runtime.stop()
                    
            try:
                asyncio.run(desktop_runner())
            except KeyboardInterrupt:
                logger.info("\n🔴 Shutting down...")

        threading.Thread(target=runner, daemon=True).start()
        try:
            ui.root.mainloop()
        finally:
            runtime.trigger_shutdown()

if __name__ == "__main__":
    main()