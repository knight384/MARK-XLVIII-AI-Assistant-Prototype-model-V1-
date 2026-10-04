"""
core.agent.complexity — a deterministic, non-LLM heuristic for judging
whether a request likely warrants multi-agent orchestration vs. a single
direct tool call (Phase 4 spec, Part 32: "Prefer explicit/internal
deterministic routing first... Do not make 'complexity detection' a giant
AI subsystem.").

This is NOT wired to automatically gate anything in this phase — the actual
entry point into the Agent Runtime is the explicit `run_agent_task` tool
(core/agent/entrypoint.py), which is opt-in by construction (Gemini Live
only invokes it when it decides a request needs multi-step handling, the
same mechanism as every other tool). `is_complex_request()` is provided as
a documented, tested utility for a future phase (or a future revision of
this one) that wants to route deterministically instead of relying on the
model's own tool-selection judgement.
"""
from __future__ import annotations

import re

_SEQUENCE_MARKERS = (
    " and then ", " then ", " after that ", " once that", " afterwards",
    " next, ", " finally, ", "önce", "sonra",  # a couple of non-English markers, kept minimal
)

_MULTI_DOMAIN_VERB_PAIRS = (
    ("research", "implement"), ("research", "recommend"), ("analyze", "fix"),
    ("find", "fix"), ("compare", "recommend"), ("build", "test"),
    ("build", "deploy"), ("prepare", "deploy"), ("fix", "verify"),
    ("fix", "test"), ("investigate", "resolve"),
)

_LONG_GOAL_WORD_THRESHOLD = 25


def is_complex_request(text: str) -> bool:
    """Returns True if `text` shows structural signs of a multi-step,
    multi-domain request. Heuristic, deterministic, cheap — no model call."""
    if not text:
        return False
    lower = f" {text.lower().strip()} "

    if any(marker in lower for marker in _SEQUENCE_MARKERS):
        return True

    if any(a in lower and b in lower for a, b in _MULTI_DOMAIN_VERB_PAIRS):
        return True

    if len(re.findall(r"\w+", text)) >= _LONG_GOAL_WORD_THRESHOLD and lower.count(",") >= 2:
        return True

    return False
