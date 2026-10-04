"""
core.llm.providers.openai_compatible — generic OpenAI-compatible chat
completions adapter (LM Studio, Jan, LocalAI, vLLM, llama.cpp server, etc.).

Configurable base_url/api_key/model/timeout (Phase 2 spec, Part 10) so new
OpenAI-compatible backends can be added purely through configuration,
without touching the Gateway or writing a new adapter.
"""
from __future__ import annotations

import json
import logging
import time

import requests

from ..capabilities import ModelCapabilities
from ..errors import (
    AuthenticationError, ConnectionError as LLMConnectionError, ModelError,
    ProviderError, RateLimitError, TimeoutError as LLMTimeoutError,
)
from ..types import ContentBlock, ModelRequest, ModelResponse, StreamEvent, ToolCall, Usage
from .base import HealthStatus, ModelInfo, Provider

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider(Provider):
    provider_id = "openai_compatible"
    display_name = "OpenAI-compatible (local/self-hosted)"

    def __init__(self, base_url_getter, model_getter, api_key_getter=None, timeout: int = 120):
        self._base_url_getter = base_url_getter
        self._model_getter = model_getter
        self._api_key_getter = api_key_getter  # optional — most local servers don't require one
        self._timeout = timeout

    def _base_url(self) -> str:
        return self._base_url_getter().rstrip("/")

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self._api_key_getter:
            try:
                key = self._api_key_getter()
                if key:
                    headers["Authorization"] = f"Bearer {key}"
            except Exception:
                pass
        return headers

    def is_configured(self) -> bool:
        return bool(self._base_url())

    def list_models(self) -> list[ModelInfo]:
        model = self._model_getter()
        return [
            ModelInfo(
                model_id=model, provider_id=self.provider_id, display_name=f"OpenAI-compatible: {model}",
                capabilities=ModelCapabilities(text_generation=True, streaming=True, local_execution=True),
                cost_profile="local", local_or_cloud="local",
            )
        ]

    def health_check(self) -> HealthStatus:
        url = self._base_url()
        if not url:
            return HealthStatus(healthy=False, detail="No base_url configured.")
        try:
            resp = requests.get(f"{url}/v1/models", headers=self._headers(), timeout=5)
            if resp.status_code == 200:
                return HealthStatus(healthy=True, detail=f"Reachable at {url}.")
            return HealthStatus(healthy=False, detail=f"Server returned HTTP {resp.status_code}.")
        except Exception as exc:
            return HealthStatus(healthy=False, detail=f"Unreachable at {url}: {exc}")

    def generate(self, request: ModelRequest, model_id: str) -> ModelResponse:
        url = self._base_url()
        messages = self._to_openai_messages(request)
        payload: dict = {"model": model_id, "messages": messages, "stream": False, "max_tokens": 600}
        if request.tools:
            payload["tools"] = request.tools
            payload["tool_choice"] = "auto"

        t0 = time.perf_counter()
        try:
            resp = requests.post(f"{url}/v1/chat/completions", json=payload,
                                  headers=self._headers(), timeout=self._timeout)
            resp.raise_for_status()
        except requests.exceptions.ConnectionError as exc:
            raise LLMConnectionError(f"Cannot reach OpenAI-compatible server at {url}.",
                                      provider=self.provider_id, model=model_id, cause=exc) from exc
        except requests.exceptions.Timeout as exc:
            raise LLMTimeoutError("OpenAI-compatible request timed out.",
                                   provider=self.provider_id, model=model_id, cause=exc) from exc
        except requests.exceptions.HTTPError as exc:
            status = resp.status_code
            if status in (401, 403):
                raise AuthenticationError("Authentication failed.", provider=self.provider_id, model=model_id, cause=exc) from exc
            if status == 429:
                raise RateLimitError("Rate limited.", provider=self.provider_id, model=model_id, cause=exc) from exc
            raise ProviderError(f"HTTP error {status}.", provider=self.provider_id, model=model_id, cause=exc) from exc
        latency_ms = (time.perf_counter() - t0) * 1000

        choice = resp.json().get("choices", [{}])[0]
        msg = choice.get("message", {})
        text = (msg.get("content") or "").strip()
        raw_tc = msg.get("tool_calls") or []
        tool_calls = []
        for t in raw_tc:
            fn = t.get("function", {})
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {"_raw": args}
            tool_calls.append(ToolCall(id=t.get("id", ""), name=fn.get("name", ""), arguments=args))

        return ModelResponse(
            content=text,
            content_blocks=[ContentBlock(type="text", text=text)] if text else [],
            tool_calls=tool_calls,
            usage=Usage(),
            finish_reason=choice.get("finish_reason"),
            model=model_id, provider=self.provider_id, latency_ms=latency_ms,
        )

    def stream(self, request: ModelRequest, model_id: str):
        url = self._base_url()
        messages = self._to_openai_messages(request)
        payload: dict = {"model": model_id, "messages": messages, "stream": True, "max_tokens": 600}
        if request.tools:
            payload["tools"] = request.tools
            payload["tool_choice"] = "auto"
        try:
            with requests.post(f"{url}/v1/chat/completions", json=payload,
                                headers=self._headers(), timeout=self._timeout, stream=True) as resp:
                resp.raise_for_status()
                for raw in resp.iter_lines():
                    if not raw:
                        continue
                    line = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        yield StreamEvent(type="done")
                        return
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    text = delta.get("content") or ""
                    if text:
                        yield StreamEvent(type="text_delta", text=text)
        except requests.exceptions.ConnectionError as exc:
            yield StreamEvent(type="error", error=f"Cannot reach server at {url}: {exc}")
        except Exception as exc:
            yield StreamEvent(type="error", error=str(exc))

    @staticmethod
    def _to_openai_messages(request: ModelRequest) -> list[dict]:
        out = []
        if request.system_instruction:
            out.append({"role": "system", "content": request.system_instruction})
        for m in request.messages:
            out.append({"role": m.role, "content": m.content})
        return out
