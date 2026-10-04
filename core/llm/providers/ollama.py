"""
core.llm.providers.ollama — Ollama native (/api/chat) provider adapter.

Extracted/adapted from core/llm_client.py (Phase 0's orphaned Ollama client —
implemented but never wired into the app). This adapter is the version that
actually gets used, via the Provider interface; core/llm_client.py is left
in place unmodified as-is (still functionally independent, not imported by
this module) rather than deleted, per the Phase 2 spec's "do not discard it."
"""
from __future__ import annotations

import json
import logging
import re
import time

import requests

from ..capabilities import ModelCapabilities
from ..errors import (
    ConnectionError as LLMConnectionError, ModelError, ModelUnavailableError,
    ProviderError, TimeoutError as LLMTimeoutError,
)
from ..types import ContentBlock, ModelRequest, ModelResponse, StreamEvent, ToolCall, Usage
from .base import HealthStatus, ModelInfo, Provider

logger = logging.getLogger(__name__)

_SENT_END = re.compile(r'(?<=[.!?])\s+|(?<=\n)\s*\n')


class OllamaProvider(Provider):
    provider_id = "ollama"
    display_name = "Ollama (local)"

    def __init__(self, base_url_getter, model_getter):
        """base_url_getter/model_getter: zero-arg callables, normally backed by
        ConfigService (e.g. lambda: config.get('llm_url', 'http://localhost:11434'))."""
        self._base_url_getter = base_url_getter
        self._model_getter = model_getter

    def _base_url(self) -> str:
        return self._base_url_getter().rstrip("/")

    def is_configured(self) -> bool:
        return bool(self._base_url())

    def list_models(self) -> list[ModelInfo]:
        """Tool-calling support varies by model — we don't claim it uniformly
        (Phase 2 spec, Part 9: 'Do not claim tool calling is supported for
        every Ollama model'). The configured default model is reported with
        tool_calling left False unless explicitly known-good; callers that
        need tool calling should route to Gemini instead unless they've
        verified their local model supports it."""
        model = self._model_getter()
        return [
            ModelInfo(
                model_id=model, provider_id=self.provider_id, display_name=f"Ollama: {model}",
                capabilities=ModelCapabilities(
                    text_generation=True, streaming=True, local_execution=True,
                ),
                cost_profile="free", local_or_cloud="local",
            )
        ]

    def health_check(self) -> HealthStatus:
        url = self._base_url()
        if not url:
            return HealthStatus(healthy=False, detail="No Ollama base_url configured.")
        try:
            resp = requests.get(f"{url}/api/tags", timeout=3)
            if resp.status_code != 200:
                return HealthStatus(healthy=False, detail=f"Ollama returned HTTP {resp.status_code}.")
            pulled = [m.get("name", "") for m in resp.json().get("models", [])]
            model = self._model_getter()
            model_base = model.split(":")[0]
            found = any(m == model or m == model_base or m.startswith(model_base + ":") for m in pulled)
            if not found:
                return HealthStatus(
                    healthy=True,  # server IS up — just missing this specific model
                    detail=f"Ollama reachable, but model '{model}' is not pulled (available: {', '.join(pulled) or 'none'}).",
                    checked_models=pulled,
                )
            return HealthStatus(healthy=True, detail=f"Ollama reachable, '{model}' available.", checked_models=pulled)
        except Exception as exc:
            return HealthStatus(healthy=False, detail=f"Ollama unreachable at {url}: {exc}")

    def generate(self, request: ModelRequest, model_id: str) -> ModelResponse:
        url = self._base_url()
        messages = self._to_ollama_messages(request)
        payload = {
            "model": model_id, "messages": messages, "stream": False,
            "keep_alive": -1, "options": {"num_predict": 600},
        }
        if request.tools:
            payload["tools"] = request.tools

        t0 = time.perf_counter()
        try:
            resp = requests.post(f"{url}/api/chat", json=payload, timeout=120)
            resp.raise_for_status()
        except requests.exceptions.ConnectionError as exc:
            raise LLMConnectionError(f"Cannot connect to Ollama at {url}.", provider=self.provider_id, model=model_id, cause=exc) from exc
        except requests.exceptions.Timeout as exc:
            raise LLMTimeoutError("Ollama request timed out.", provider=self.provider_id, model=model_id, cause=exc) from exc
        except requests.exceptions.HTTPError as exc:
            if resp.status_code == 404:
                raise ModelUnavailableError(f"Model '{model_id}' not available on Ollama.", provider=self.provider_id, model=model_id, cause=exc) from exc
            raise ProviderError(f"Ollama HTTP error {resp.status_code}.", provider=self.provider_id, model=model_id, cause=exc) from exc
        latency_ms = (time.perf_counter() - t0) * 1000

        data = resp.json()
        msg = data.get("message", {})
        text = (msg.get("content") or "").strip()
        raw_tool_calls = msg.get("tool_calls") or []
        tool_calls = [
            ToolCall(id=tc.get("id", ""), name=tc.get("function", {}).get("name", ""),
                      arguments=tc.get("function", {}).get("arguments", {}) or {})
            for tc in raw_tool_calls
        ]
        return ModelResponse(
            content=text,
            content_blocks=[ContentBlock(type="text", text=text)] if text else [],
            tool_calls=tool_calls,
            usage=Usage(),
            finish_reason="stop",
            model=model_id, provider=self.provider_id, latency_ms=latency_ms,
        )

    def stream(self, request: ModelRequest, model_id: str):
        url = self._base_url()
        messages = self._to_ollama_messages(request)
        payload = {
            "model": model_id, "messages": messages, "stream": True,
            "keep_alive": -1, "options": {"num_predict": 150},
        }
        if request.tools:
            payload["tools"] = request.tools

        try:
            with requests.post(f"{url}/api/chat", json=payload, timeout=120, stream=True) as resp:
                resp.raise_for_status()
                for raw in resp.iter_lines():
                    if not raw:
                        continue
                    try:
                        chunk = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    delta = (chunk.get("message", {}).get("content") or "")
                    if delta:
                        yield StreamEvent(type="text_delta", text=delta)
                    if chunk.get("done"):
                        yield StreamEvent(type="done")
                        return
        except requests.exceptions.ConnectionError as exc:
            yield StreamEvent(type="error", error=f"Cannot connect to Ollama at {url}: {exc}")
        except Exception as exc:
            yield StreamEvent(type="error", error=str(exc))

    @staticmethod
    def _to_ollama_messages(request: ModelRequest) -> list[dict]:
        out = []
        if request.system_instruction:
            out.append({"role": "system", "content": request.system_instruction})
        for m in request.messages:
            out.append({"role": m.role, "content": m.content})
        return out
