"""
core.policy.approval — the ApprovalManager (Phase 6 spec, Parts 12-17, 47).
"""
from __future__ import annotations

import hashlib
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum

from core.tools.metadata import RiskLevel

from .errors import ApprovalDeniedError, ApprovalMismatchError, ApprovalNotFoundError, ApprovalTimeoutError
from .models import RequestSource

logger = logging.getLogger(__name__)


class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


def _fingerprint(tool_name: str, argument_summary: str, session_id: str | None) -> str:
    """Binds an approval to the exact operation (spec Part 16) — a safe,
    non-secret fingerprint, never the raw arguments/secrets themselves."""
    raw = f"{tool_name}|{argument_summary}|{session_id or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


@dataclass
class ApprovalRequest:
    tool: str
    agent: str | None
    task: str | None
    action_summary: str
    risk_level: RiskLevel
    source: RequestSource
    session_id: str | None = None
    approval_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    requested_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + 120.0)
    status: ApprovalStatus = ApprovalStatus.PENDING
    fingerprint: str = ""
    resolved_at: float | None = None
    resolution_reason: str = ""

    def __post_init__(self):
        if not self.fingerprint:
            self.fingerprint = _fingerprint(self.tool, self.action_summary, self.session_id)

    def is_expired(self, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        return now >= self.expires_at

    def human_readable(self) -> str:
        """spec Part 13 — what the user actually sees."""
        return (
            f"JARVIS wants to:\n\n{self.action_summary}\n\n"
            f"Risk: {self.risk_level.value}\n\nAllow?"
        )


class ApprovalManager:
    """UI-independent (spec Part 45) — exposes `on_requested`/`on_resolved`
    callback hooks that a desktop UI or dashboard can subscribe to render
    the prompt; this class itself has no rendering logic."""

    def __init__(self, default_timeout_seconds: float = 120.0):
        self._requests: dict[str, ApprovalRequest] = {}
        self._lock = threading.Lock()
        self._default_timeout = default_timeout_seconds
        self.on_requested = None    # Callable[[ApprovalRequest], None]
        self.on_resolved = None     # Callable[[ApprovalRequest], None]

    def request(self, tool: str, action_summary: str, risk_level: RiskLevel, *,
                agent: str | None = None, task: str | None = None,
                source: RequestSource = RequestSource.LOCAL_AGENT,
                session_id: str | None = None,
                timeout_seconds: float | None = None) -> ApprovalRequest:
        req = ApprovalRequest(
            tool=tool, agent=agent, task=task, action_summary=action_summary,
            risk_level=risk_level, source=source, session_id=session_id,
            expires_at=time.time() + (timeout_seconds or self._default_timeout),
        )
        with self._lock:
            self._requests[req.approval_id] = req
        logger.info("[Approval] requested id=%s tool=%s risk=%s source=%s",
                     req.approval_id, tool, risk_level.value, source.value)
        if self.on_requested:
            try:
                self.on_requested(req)
            except Exception:
                logger.warning("[Approval] on_requested callback raised.")
        return req

    def approve(self, approval_id: str, *, session_id: str | None = None) -> ApprovalRequest:
        req = self._get_pending(approval_id)
        self._check_session(req, session_id)
        req.status = ApprovalStatus.APPROVED
        req.resolved_at = time.time()
        req.resolution_reason = "approved"
        logger.info("[Approval] granted id=%s tool=%s", approval_id, req.tool)
        self._notify_resolved(req)
        return req

    def deny(self, approval_id: str, *, reason: str = "denied by user",
              session_id: str | None = None) -> ApprovalRequest:
        req = self._get_pending(approval_id)
        self._check_session(req, session_id)
        req.status = ApprovalStatus.DENIED
        req.resolved_at = time.time()
        req.resolution_reason = reason
        logger.info("[Approval] denied id=%s tool=%s reason=%s", approval_id, req.tool, reason)
        self._notify_resolved(req)
        return req

    def cancel(self, approval_id: str) -> ApprovalRequest:
        req = self._get_pending(approval_id)
        req.status = ApprovalStatus.CANCELLED
        req.resolved_at = time.time()
        self._notify_resolved(req)
        return req

    def get(self, approval_id: str) -> ApprovalRequest | None:
        with self._lock:
            return self._requests.get(approval_id)

    def check_and_consume(self, approval_id: str, tool: str, action_summary: str,
                           session_id: str | None = None) -> bool:
        """Validates an approval is APPROVED, matches the exact operation
        fingerprint (spec Part 16), and hasn't expired — then marks it
        consumed (single-use, spec Part 47) by flipping it to a terminal
        'used' state so it can never authorize a second call."""
        with self._lock:
            req = self._requests.get(approval_id)
            if req is None:
                raise ApprovalNotFoundError(f"No approval found for id '{approval_id}'.")
            if req.status != ApprovalStatus.APPROVED:
                raise ApprovalDeniedError(
                    f"Approval '{approval_id}' is {req.status.value}, not APPROVED.",
                    reason=req.resolution_reason,
                )
            if req.is_expired():
                req.status = ApprovalStatus.EXPIRED
                raise ApprovalTimeoutError(f"Approval '{approval_id}' has expired.")

            expected = _fingerprint(tool, action_summary, session_id)
            if expected != req.fingerprint:
                raise ApprovalMismatchError(
                    f"Approval '{approval_id}' was granted for a different operation "
                    f"(tool/arguments/session do not match)."
                )

            # Single-use: consume immediately so a replay can never succeed.
            req.status = ApprovalStatus.CANCELLED
            req.resolution_reason = "consumed"
            return True

    def expire_stale(self) -> int:
        now = time.time()
        expired = 0
        with self._lock:
            for req in self._requests.values():
                if req.status == ApprovalStatus.PENDING and req.is_expired(now):
                    req.status = ApprovalStatus.EXPIRED
                    req.resolved_at = now
                    expired += 1
        return expired

    def _get_pending(self, approval_id: str) -> ApprovalRequest:
        with self._lock:
            req = self._requests.get(approval_id)
        if req is None:
            raise ApprovalNotFoundError(f"No approval found for id '{approval_id}'.")
        if req.is_expired() and req.status == ApprovalStatus.PENDING:
            req.status = ApprovalStatus.EXPIRED
        if req.status != ApprovalStatus.PENDING:
            raise ApprovalDeniedError(f"Approval '{approval_id}' is no longer pending "
                                       f"(status={req.status.value}).")
        return req

    def _check_session(self, req: ApprovalRequest, session_id: str | None) -> None:
        """spec Part 14: 'must not assume that an approval from one session
        automatically authorizes another unrelated session.' Only enforced
        when the request itself was bound to a session AND the resolver
        supplies one that differs — an unbound (session_id=None) request
        can be resolved by any caller, matching today's single-user desktop
        assumption while remaining ready for multi-session enforcement."""
        if req.session_id is not None and session_id is not None and req.session_id != session_id:
            raise ApprovalMismatchError(
                f"Approval '{req.approval_id}' belongs to a different session."
            )

    def _notify_resolved(self, req: ApprovalRequest) -> None:
        if self.on_resolved:
            try:
                self.on_resolved(req)
            except Exception:
                logger.warning("[Approval] on_resolved callback raised.")


_default_manager: ApprovalManager | None = None
_default_lock = threading.Lock()


def get_default_approval_manager() -> ApprovalManager:
    global _default_manager
    with _default_lock:
        if _default_manager is None:
            _default_manager = ApprovalManager()
        return _default_manager
