"""
core.llm — the Model Gateway package (Phase 2).

Typical usage for a simple "send a prompt, get text back" call (the most
common pattern in this codebase's actions/*.py modules):

    from core.llm.gateway import generate_text
    reply = generate_text("Summarize this...", task_type="coding")

For more control (tools, task-type routing, explicit provider override):

    from core.llm.gateway import get_default_gateway
    from core.llm.types import ModelRequest, Message

    gateway = get_default_gateway()
    response = gateway.generate(
        ModelRequest(messages=[Message(role="user", content="...")], tools=[...]),
        task_type="vision",
    )

Gemini Live (the realtime voice session) is NOT part of this synchronous
Gateway — see `core.llm.providers.gemini_live.GeminiLiveAdapter`.
"""
from .gateway import ModelGateway, generate_text, get_default_gateway
from .registry import ProviderRegistry, get_default_registry
from .router import ModelRouter, NoCompatibleModelError, RoutingDecision
from .types import Message, ModelRequest, ModelResponse

__all__ = [
    "ModelGateway", "generate_text", "get_default_gateway",
    "ProviderRegistry", "get_default_registry",
    "ModelRouter", "NoCompatibleModelError", "RoutingDecision",
    "Message", "ModelRequest", "ModelResponse",
]
