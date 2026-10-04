"""
core.llm.providers.gemini_live — specialized realtime session adapter.

Gemini Live is fundamentally different from the stateless `generate()` calls
the rest of this package models (Phase 2 spec, Part 8): it's a persistent,
bidirectional, audio-streaming session, not a request/response call. Forcing
it through `Provider.generate()` would either break streaming semantics or
require a fake synchronous wrapper that lies about what's actually
happening. So it gets its own class, `GeminiLiveAdapter`, instead.

This module is the one deliberate exception to "the rest of JARVIS depends
on the Gateway, not on individual AI vendors" (Part 25/37): it *is* the
provider boundary for realtime audio, and it uses `google.genai` directly,
exactly as the spec allows ("The low-level Gemini Live Adapter may directly
use google.genai because it is itself the provider boundary.").

Design choice for Phase 2: this wraps *session creation* (client + connect)
behind a stable interface, without touching the send/receive/audio-queue
loop in main.py, which is the highest-risk, most latency-sensitive part of
the app. `main.py`'s task-group loop (`_send_realtime`, `_listen_audio`,
`_receive_audio`, `_play_audio`, interrupt handling) is unchanged — it just
receives its `session` object from `GeminiLiveAdapter.connect()` instead of
constructing a `genai.Client` inline. This keeps the realtime audio path's
behavior byte-for-byte identical while still centralizing "how do we get a
Gemini Live session" behind one adapter, so a future second realtime
provider (should one ever exist) has a defined seam to implement against.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class GeminiLiveAdapter:
    """Realtime session provider boundary for Gemini Live.

    Usage (mirrors the previous inline main.py code exactly):

        adapter = GeminiLiveAdapter(api_key_getter=config.get_gemini_api_key)
        async with adapter.connect(model=LIVE_MODEL, config=live_config) as session:
            ...  # existing send/receive/audio loop, unchanged
    """

    provider_id = "gemini_live"
    display_name = "Google Gemini Live"

    def __init__(self, api_key_getter, api_version: str = "v1beta"):
        self._api_key_getter = api_key_getter
        self._api_version = api_version

    def is_configured(self) -> bool:
        try:
            self._api_key_getter()
            return True
        except Exception:
            return False

    def _new_client(self):
        """A fresh client per connect() call — matches the existing
        behavior in main.py ('Fresh client on every reconnect — avoids
        stale HTTP session state'), preserved deliberately."""
        from google import genai
        return genai.Client(
            api_key=self._api_key_getter(),
            http_options={"api_version": self._api_version},
        )

    @asynccontextmanager
    async def connect(self, model: str, config):
        """Async context manager yielding the native google.genai Live
        session object, unchanged from what main.py used to get directly
        from `client.aio.live.connect(...)`. Callers keep using it exactly
        as before (session.send(...), async for msg in session.receive(), etc.) —
        this adapter only owns client construction, not the session protocol,
        so Phase 2 does not risk regressing the realtime audio path."""
        client = self._new_client()
        async with client.aio.live.connect(model=model, config=config) as session:
            yield session
