"""
core.tools.schemas — provider-neutral tool input schema (Phase 3 spec, Part 9).

Canonical flow is Tool Definition → Provider Adapter → Gemini schema, never
the reverse. `to_gemini_declaration()` is the one place that knows Gemini's
particular JSON-schema-like dialect (uppercase type names: "STRING",
"OBJECT", etc.) — nothing else in the tool layer depends on that dialect.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ParamSchema:
    name: str
    type: str                        # "string" | "integer" | "number" | "boolean" | "array" | "object"
    description: str = ""
    required: bool = False
    enum: tuple[str, ...] | None = None
    default: Any = None
    items_type: str | None = None    # for type == "array"


@dataclass(frozen=True)
class ToolSchema:
    """A tool's full parameter list. Provider-neutral — see
    `to_gemini_declaration()` for the Gemini-specific projection."""
    parameters: tuple[ParamSchema, ...] = ()

    def required_names(self) -> list[str]:
        return [p.name for p in self.parameters if p.required]

    def validate(self, args: dict) -> list[str]:
        """Returns a list of human-readable validation error strings (empty
        list = valid). Deliberately simple (spec Part 19: 'use the simplest
        reliable validation mechanism') — not a full JSON-Schema validator."""
        errors: list[str] = []
        known = {p.name for p in self.parameters}
        by_name = {p.name: p for p in self.parameters}

        for name in self.required_names():
            if name not in args or args[name] in (None, ""):
                errors.append(f"Missing required field: '{name}'")

        for key, value in args.items():
            if key not in known:
                continue  # tolerate extra args — matches prior dispatcher's dict.get() leniency
            spec = by_name[key]
            if value is None:
                continue
            if not _type_ok(value, spec.type):
                errors.append(f"Field '{key}' expected type {spec.type}, got {type(value).__name__}")
            elif spec.enum and isinstance(value, str) and value not in spec.enum:
                errors.append(f"Field '{key}' must be one of {list(spec.enum)}, got '{value}'")

        return errors

    def to_gemini_declaration(self, name: str, description: str) -> dict:
        properties: dict[str, Any] = {}
        for p in self.parameters:
            entry: dict[str, Any] = {
                "type": _GEMINI_TYPE_MAP.get(p.type, "STRING"),
                "description": p.description,
            }
            if p.enum:
                entry["enum"] = list(p.enum)
            if p.type == "array":
                entry["items"] = {"type": _GEMINI_TYPE_MAP.get(p.items_type or "string", "STRING")}
            properties[p.name] = entry

        return {
            "name": name,
            "description": description,
            "parameters": {
                "type": "OBJECT",
                "properties": properties,
                "required": self.required_names(),
            },
        }


_GEMINI_TYPE_MAP = {
    "string": "STRING",
    "integer": "INTEGER",
    "number": "NUMBER",
    "boolean": "BOOLEAN",
    "array": "ARRAY",
    "object": "OBJECT",
}


def _type_ok(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "array":
        return isinstance(value, (list, tuple))
    if expected == "object":
        return isinstance(value, dict)
    return True  # unknown type name — don't block execution over a schema typo
