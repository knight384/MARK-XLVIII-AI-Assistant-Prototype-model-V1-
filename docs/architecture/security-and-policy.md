# Security & Policy Architecture

Phase 6 adds `core/policy/` (authorization) and `core/sandbox/` (isolated
execution), and wires both into Phase 3's `ToolExecutor` — turning the
risk *metadata* every tool and agent already declared (Phases 3-4) into
actual enforcement.

## Before vs after

**Before Phase 6**: `ToolMetadata.risk_level` and `AgentMetadata.max_declared_risk`
existed but nothing read them at execution time — every tool call that
passed schema validation executed immediately, regardless of risk.

**After Phase 6**: every tool call passes through
`PolicyEngine.evaluate()` before it runs. The decision is one of `ALLOW`,
`APPROVAL_REQUIRED`, or `DENY` — computed deterministically (no model
call), enforced in exactly one place (`ToolExecutor`), for every caller
(realtime voice, Agent Runtime, and — via a request-source tag — the
dashboard).

## PolicyEngine

```python
PolicyEngine.evaluate(PolicyContext) -> PolicyResult
```

`PolicyContext` carries: `tool_name`, `risk_level`, `capabilities`,
`agent_id`/`agent_max_risk`, `task_id`/`request_id`, `source` (local
voice/local agent/dashboard/system), `session_id`, and a safe
`argument_summary` — never raw secrets, never raw private memory.

Rules run in priority order (`core/policy/rules.py`); the first match
wins:

1. `rule_agent_risk_limit` — an agent can never exceed its own declared
   `max_declared_risk`, under any policy configuration, including a
   disabled policy engine (spec Part 51: no silent escalation, ever).
2. `rule_policy_disabled` — LOW/MEDIUM degrade to ALLOW when the policy
   engine is administratively disabled; HIGH/CRITICAL still fail closed to
   APPROVAL_REQUIRED (spec Part 50).
3. `rule_critical_commands_disabled` — a config kill-switch.
4. `rule_remote_critical` — CRITICAL from the dashboard denies by default.
5. `rule_remote_high_disabled` / `rule_local_high_disabled` — configurable
   stricter handling per source.
6. `rule_sandbox_required_unavailable` — a tool that declared
   `requires_sandbox=True` is denied outright if `SandboxManager` reports
   no acceptable backend, rather than silently falling back to an
   unsandboxed host run.
7. `rule_default_risk_action` — the baseline table (see below), always
   matches if nothing stricter fired first.

Any rule-chain exception is caught and treated as `APPROVAL_REQUIRED`
(fail closed — spec Part 50), never as a silent allow.

## Default policy table (spec Part 10)

| Risk | Default action | Configurable via |
|---|---|---|
| LOW | ALLOW | `default_low_risk_action` |
| MEDIUM | ALLOW | `default_medium_risk_action` |
| HIGH | APPROVAL_REQUIRED | `default_high_risk_action` |
| CRITICAL | APPROVAL_REQUIRED | `default_critical_risk_action` |

Plus: `allow_local_high_risk`, `allow_remote_high_risk`,
`allow_critical_commands`, `approval_timeout_seconds`,
`deny_remote_critical` — all routed through Phase 1's `ConfigService`
(`core/policy/config.py::load_policy_config()`), no second config system.

## Agent risk-limit enforcement (spec Part 19)

Every `AgentMetadata.max_declared_risk` from Phase 4 is now load-bearing:
`ToolExecutor` passes `context.agent_id`/`context.agent_max_risk` into the
`PolicyContext`, and `rule_agent_risk_limit` denies outright — no approval
path — if the tool's risk exceeds what the calling agent may request. A
`ResearchAgent` (max LOW) can never trigger `dev_agent` (CRITICAL), even
with a human standing by ready to approve; the agent's own ceiling is not
something an approval elevates.

## Local vs remote (spec Part 20)

`RequestSource`: `local_voice` (Gemini Live mic), `local_agent` (Agent
Runtime), `dashboard` (remote web UI), `system`. Dashboard-originated tool
calls are tagged via a short-lived flag set in `main.py`'s
`_process_dashboard_commands()` right before relaying a dashboard-typed
command into the Gemini Live session, consumed by the next
`_execute_tool()` call (see "Known limitation" below for the precision
tradeoff this implies). CRITICAL from the dashboard denies by default;
HIGH from the dashboard is configurable independently from HIGH locally.

## Approval workflow

`ApprovalManager` (`core/policy/approval.py`):

- `request()` creates a `PENDING` `ApprovalRequest` with a safe
  fingerprint (`sha256(tool|argument_summary|session_id)`) binding it to
  the exact operation (spec Part 16) — never the raw arguments.
- `approve()`/`deny()`/`cancel()` resolve it; `check_and_consume()`
  validates status + fingerprint + expiry, then **immediately flips it to
  a consumed terminal state** — single-use (spec Part 47), a replay
  attempt raises `ApprovalDeniedError`.
- Requests expire (`approval_timeout_seconds`, default 120s); an expired
  approval can never be granted.
- Session-bound when the original request carried a `session_id` — a
  different session's resolution attempt raises `ApprovalMismatchError`
  (spec Part 14). An unbound request (no `session_id`) can be resolved by
  any caller, matching today's single-user desktop assumption.
- `on_requested`/`on_resolved` callbacks let a UI render the prompt
  without `ApprovalManager` knowing anything about rendering (spec Part
  45) — `req.human_readable()` produces the spec's example text:
  ```
  JARVIS wants to:

  <action_summary>

  Risk: HIGH

  Allow?
  ```

**`ToolExecutor` actually waits** (spec Part 12: "execution must pause
until approval is received") — an `async` polling loop, bounded by
`approval_timeout_seconds`, that doesn't block the process (other asyncio
tasks, including the realtime audio loop, continue running). A caller
that already has an approval (e.g. from a prior `APPROVAL_REQUIRED`
response) passes `ToolContext.approval_id` to skip the wait.

## Audit events (spec Part 21-22)

`core/policy/audit.py::SecurityAuditEvent` — one of `PolicyEvaluated`,
`ApprovalRequested`, `ApprovalGranted`, `ApprovalDenied`, `ToolAllowed`,
`ToolDenied`, `ToolExecuted` — emitted through Phase 1's `logging`
(WARNING for denials/failures, INFO otherwise). Fields: timestamp,
request_id, task_id, agent_id, tool_name, risk_level, decision, source,
duration_ms, result_status. **Never** the raw arguments, never memory
content — `metadata` on an event is limited to things like
`{"matched_rule": "..."}` or `{"approval_id": "..."}`.

## ToolExecutor integration (spec Part 17)

```
validate -> build PolicyContext -> PolicyEngine.evaluate()
    ALLOW              -> execute
    APPROVAL_REQUIRED  -> ApprovalManager.request() -> await (bounded) -> execute or fail
    DENY               -> fail safely, never execute
```

This is the only place any of this happens — see
`tests/policy/test_architecture.py` for the static checks confirming
`core/agent/` implements no second policy decision, imports no provider
SDK, and imports no `actions.*` directly, and that exactly one
`ToolExecutor` class exists in the codebase.

## Fail-closed summary (spec Part 50)

| Condition | Result |
|---|---|
| Policy engine disabled | LOW/MEDIUM allow, HIGH/CRITICAL still APPROVAL_REQUIRED |
| A policy rule raises | APPROVAL_REQUIRED |
| Approval times out / is denied / mismatches | tool never executes |
| Required sandbox unavailable | DENY |
| Agent exceeds its own risk ceiling | DENY, unconditionally |

## Known limitation: dashboard source tagging precision

Gemini Live shares one realtime session for both microphone input and
dashboard-relayed text — there is no per-tool-call "this came from the
dashboard" channel in the underlying API. The current implementation sets
a single-use flag before relaying dashboard text into the session and
consumes it on the *next* tool call; if a dashboard-triggered turn results
in more than one tool call, only the first is reliably tagged
`source=dashboard`. This is disclosed here rather than glossed over — a
more precise mechanism would require deeper changes to the realtime
session's turn-tracking, which is out of scope for Phase 6 (spec: "Do not
completely redesign dashboard authentication in Phase 6 unless necessary
for the policy boundary" — the policy boundary itself works; only the
edge case of multi-tool-call dashboard turns has reduced precision).

See `docs/security-model.md` for the full threat model and
`docs/sandbox.md` for the isolation layer.
