"""
core.llm.types — provider-neutral request/response/streaming types.

Deliberately does NOT try to force Gemini Live's realtime audio session into
this synchronous request/response shape (Phase 2 spec, Part 6 & 8) — that
lives in providers/gemini_live.py's RealtimeModelSession instead. These types
are for ordinary "send messages, get a response" calls: standard Gemini
generate_content, Ollama chat, OpenAI-compatible chat/completions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class Message:
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    name: str | None = None            # tool name, when role == "tool"
    tool_call_id: str | None = None    # links a tool result back to its call


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    tool_call_id: str
    name: str
    content: str


@dataclass
class ModelRequest:
    messages: list[Message]
    system_instruction: str | None = None
    tools: list[dict[str, Any]] | None = None          # provider-neutral tool schemas (JSON-schema-ish)
    response_format: str | None = None                  # e.g. "json" — best-effort, not all providers support it
    stream: bool = False
    session_mode: Literal["stateless", "realtime_session"] = "stateless"
    metadata: dict[str, Any] = field(default_factory=dict)  # task_type, privacy hints, etc. for routing/telemetry


@dataclass
class ContentBlock:
    type: Literal["text", "tool_call", "image"]
    text: str | None = None
    tool_call: ToolCall | None = None
    image_data: bytes | None = None
    mime_type: str | None = None


@dataclass
class Usage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


@dataclass
class ModelResponse:
    content: str                          # convenience: concatenated text content
    content_blocks: list[ContentBlock] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    finish_reason: str | None = None
    model: str | None = None
    provider: str | None = None
    latency_ms: float | None = None


@dataclass
class StreamEvent:
    type: Literal["text_delta", "tool_call", "usage", "done", "error"]
    text: str | None = None
    tool_call: ToolCall | None = None
    usage: Usage | None = None
    error: str | None = None


@dataclass
class SimpleTextResponse:
    """Minimal `.text`-compatible shim, for call sites migrating off a raw
    google.genai response object (which also exposes `.text`) onto the
    Gateway, without having to touch every downstream `response.text` access
    individually."""
    text: str
