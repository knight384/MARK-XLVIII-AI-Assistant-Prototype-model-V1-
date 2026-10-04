"""tests/policy/test_approval.py"""
from __future__ import annotations

import time

import pytest

from core.policy.approval import ApprovalManager, ApprovalStatus
from core.policy.errors import ApprovalDeniedError, ApprovalMismatchError, ApprovalNotFoundError, ApprovalTimeoutError
from core.tools.metadata import RiskLevel


def test_request_creates_pending():
    mgr = ApprovalManager()
    req = mgr.request("file_controller", "delete file X", RiskLevel.HIGH)
    assert req.status == ApprovalStatus.PENDING
    assert req.approval_id


def test_approve():
    mgr = ApprovalManager()
    req = mgr.request("file_controller", "delete file X", RiskLevel.HIGH)
    resolved = mgr.approve(req.approval_id)
    assert resolved.status == ApprovalStatus.APPROVED


def test_deny():
    mgr = ApprovalManager()
    req = mgr.request("file_controller", "delete file X", RiskLevel.HIGH)
    resolved = mgr.deny(req.approval_id, reason="too risky")
    assert resolved.status == ApprovalStatus.DENIED
    assert resolved.resolution_reason == "too risky"


def test_cancel():
    mgr = ApprovalManager()
    req = mgr.request("x", "y", RiskLevel.LOW)
    resolved = mgr.cancel(req.approval_id)
    assert resolved.status == ApprovalStatus.CANCELLED


def test_get_missing_returns_none():
    mgr = ApprovalManager()
    assert mgr.get("nonexistent") is None


def test_approve_missing_raises():
    mgr = ApprovalManager()
    with pytest.raises(ApprovalNotFoundError):
        mgr.approve("nonexistent")


def test_approve_already_resolved_raises():
    mgr = ApprovalManager()
    req = mgr.request("x", "y", RiskLevel.LOW)
    mgr.approve(req.approval_id)
    with pytest.raises(ApprovalDeniedError):
        mgr.approve(req.approval_id)


# -- expiration (spec Part 15) ---------------------------------------------

def test_expired_request_cannot_be_approved():
    mgr = ApprovalManager()
    req = mgr.request("x", "y", RiskLevel.LOW, timeout_seconds=0.01)
    time.sleep(0.02)
    with pytest.raises(ApprovalDeniedError):
        mgr.approve(req.approval_id)
    assert mgr.get(req.approval_id).status == ApprovalStatus.EXPIRED


def test_expire_stale_marks_pending_as_expired():
    mgr = ApprovalManager()
    req = mgr.request("x", "y", RiskLevel.LOW, timeout_seconds=0.01)
    time.sleep(0.02)
    count = mgr.expire_stale()
    assert count == 1
    assert mgr.get(req.approval_id).status == ApprovalStatus.EXPIRED


def test_check_and_consume_raises_on_expired():
    mgr = ApprovalManager()
    req = mgr.request("tool", "summary", RiskLevel.HIGH, timeout_seconds=0.01)
    mgr.approve(req.approval_id)
    time.sleep(0.02)
    with pytest.raises(ApprovalTimeoutError):
        mgr.check_and_consume(req.approval_id, "tool", "summary")


# -- single-use (spec Part 47) ----------------------------------------------

def test_approval_is_single_use():
    mgr = ApprovalManager()
    req = mgr.request("file_controller", "delete file X", RiskLevel.HIGH)
    mgr.approve(req.approval_id)
    assert mgr.check_and_consume(req.approval_id, "file_controller", "delete file X") is True
    with pytest.raises(ApprovalDeniedError):
        mgr.check_and_consume(req.approval_id, "file_controller", "delete file X")


def test_replay_after_consumption_fails():
    mgr = ApprovalManager()
    req = mgr.request("x", "action summary", RiskLevel.HIGH)
    mgr.approve(req.approval_id)
    mgr.check_and_consume(req.approval_id, "x", "action summary")
    with pytest.raises(ApprovalDeniedError):
        mgr.check_and_consume(req.approval_id, "x", "action summary")


# -- operation binding (spec Part 16) ---------------------------------------

def test_approval_bound_to_exact_tool():
    mgr = ApprovalManager()
    req = mgr.request("file_controller", "delete file A", RiskLevel.HIGH)
    mgr.approve(req.approval_id)
    with pytest.raises(ApprovalMismatchError):
        mgr.check_and_consume(req.approval_id, "browser_control", "delete file A")


def test_approval_bound_to_exact_action_summary():
    """Approval for 'delete file A' must NOT authorize 'delete file B'."""
    mgr = ApprovalManager()
    req = mgr.request("file_controller", "delete file A", RiskLevel.HIGH)
    mgr.approve(req.approval_id)
    with pytest.raises(ApprovalMismatchError):
        mgr.check_and_consume(req.approval_id, "file_controller", "delete file B")


def test_matching_operation_succeeds():
    mgr = ApprovalManager()
    req = mgr.request("file_controller", "delete file A", RiskLevel.HIGH)
    mgr.approve(req.approval_id)
    assert mgr.check_and_consume(req.approval_id, "file_controller", "delete file A") is True


# -- session binding (spec Part 14) -----------------------------------------

def test_wrong_session_cannot_resolve_bound_approval():
    mgr = ApprovalManager()
    req = mgr.request("x", "y", RiskLevel.HIGH, session_id="session-A")
    with pytest.raises(ApprovalMismatchError):
        mgr.approve(req.approval_id, session_id="session-B")


def test_same_session_can_resolve():
    mgr = ApprovalManager()
    req = mgr.request("x", "y", RiskLevel.HIGH, session_id="session-A")
    resolved = mgr.approve(req.approval_id, session_id="session-A")
    assert resolved.status == ApprovalStatus.APPROVED


def test_unbound_approval_resolvable_by_any_caller():
    """No session_id set on the request -> matches today's single-user
    desktop assumption (spec Part 14 — implement the simplest reliable
    path needed now)."""
    mgr = ApprovalManager()
    req = mgr.request("x", "y", RiskLevel.HIGH)
    resolved = mgr.approve(req.approval_id, session_id="any-session")
    assert resolved.status == ApprovalStatus.APPROVED


# -- human-readable summary (spec Part 13) ----------------------------------

def test_human_readable_includes_risk_and_summary():
    mgr = ApprovalManager()
    req = mgr.request("file_controller", "Delete 14 files from build/", RiskLevel.HIGH)
    text = req.human_readable()
    assert "Delete 14 files" in text
    assert "HIGH" in text
    assert "Allow?" in text


# -- callbacks (spec Part 45) ------------------------------------------------

def test_on_requested_callback_fires():
    events = []
    mgr = ApprovalManager()
    mgr.on_requested = events.append
    mgr.request("x", "y", RiskLevel.LOW)
    assert len(events) == 1


def test_on_resolved_callback_fires():
    events = []
    mgr = ApprovalManager()
    mgr.on_resolved = events.append
    req = mgr.request("x", "y", RiskLevel.LOW)
    mgr.approve(req.approval_id)
    assert len(events) == 1


def test_broken_callback_does_not_break_request_flow():
    mgr = ApprovalManager()
    mgr.on_requested = lambda r: (_ for _ in ()).throw(RuntimeError("broken"))
    req = mgr.request("x", "y", RiskLevel.LOW)
    assert req.status == ApprovalStatus.PENDING
