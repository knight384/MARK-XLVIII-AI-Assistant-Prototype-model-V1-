"""core.tools.registry — the Tool Registry (Phase 3 spec, Part 12)."""
from __future__ import annotations

import logging
import threading

from .base import Tool
from .errors import ToolRegistrationError
from .metadata import ToolCategory

logger = logging.getLogger(__name__)


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._aliases: dict[str, str] = {}   # alias -> canonical name
        self._lock = threading.Lock()

    def register(self, tool: Tool, *, aliases: tuple[str, ...] = ()) -> None:
        with self._lock:
            if tool.name in self._tools:
                raise ToolRegistrationError(
                    f"A tool named '{tool.name}' is already registered.", tool_name=tool.name,
                )
            for alias in aliases:
                if alias in self._tools or alias in self._aliases:
                    raise ToolRegistrationError(
                        f"Alias '{alias}' for tool '{tool.name}' conflicts with an existing name/alias.",
                        tool_name=tool.name,
                    )
            self._tools[tool.name] = tool
            for alias in aliases:
                self._aliases[alias] = tool.name

    def unregister(self, name: str) -> None:
        with self._lock:
            self._tools.pop(name, None)
            for alias, target in list(self._aliases.items()):
                if target == name:
                    del self._aliases[alias]

    def get(self, name: str) -> Tool | None:
        canonical = self._aliases.get(name, name)
        return self._tools.get(canonical)

    def exists(self, name: str) -> bool:
        return self.get(name) is not None

    def list(self) -> list[Tool]:
        return list(self._tools.values())

    def list_names(self) -> list[str]:
        return list(self._tools.keys())

    def list_by_category(self, category: ToolCategory) -> list[Tool]:
        return [t for t in self._tools.values() if t.metadata.category == category]

    def generate_gemini_declarations(self) -> list[dict]:
        """The canonical source of Gemini function declarations (Phase 3
        spec, Part 16) — replaces main.py's hardcoded TOOL_DECLARATIONS."""
        return [tool.gemini_declaration() for tool in self._tools.values()]


_default_registry: ToolRegistry | None = None
_default_lock = threading.Lock()


def get_default_registry() -> ToolRegistry:
    global _default_registry
    with _default_lock:
        if _default_registry is None:
            from .definitions import register_all_tools
            registry = ToolRegistry()
            register_all_tools(registry)
            _default_registry = registry
        return _default_registry
