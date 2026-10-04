# Security

This document describes the current security posture of JARVIS / MARK XLVIII
after Phase 6 (Policy Engine, approval workflow, and execution sandbox).
**This application is not hardened for untrusted, multi-user, or
public-Internet deployment.** It is designed as a trusted, single-user,
local assistant with broad computer-control capabilities — treat it
accordingly. See `docs/security-model.md` for the full threat model and
`docs/architecture/security-and-policy.md` / `docs/sandbox.md` for the
architecture behind the summary below.

## What Phase 6 changed (the major update)

- **Every tool call now passes through a Policy Engine** before it
  executes — `ALLOW`, `APPROVAL_REQUIRED`, or `DENY`, decided
  deterministically from the tool's declared risk level, the calling
  agent's declared risk ceiling, and whether the request came from a local
  session or the remote dashboard. This replaces "risk metadata that
  existed but nothing enforced" (Phase 3-5) with actual enforcement.
- **HIGH and CRITICAL-risk actions require human approval by default** —
  file writes/deletes, browser control, computer control, code execution,
  and shell commands all pause for an explicit approve/deny before running.
  Approvals are single-use, time-limited (120s default), and bound to the
  exact operation (a "delete file A" approval cannot be replayed to
  authorize "delete file B").
- **An agent can never exceed its own declared risk ceiling** — this is a
  hard deny, enforced even if the policy engine is otherwise disabled, and
  cannot be bypassed by an agent "asking for" elevated permissions.
- **Remote (dashboard) requests are treated more strictly than local
  ones** — CRITICAL-risk actions from the dashboard are denied by default.
- **A real execution sandbox exists** (`core/sandbox/`) — Docker-based
  when Docker is available, with a clearly-documented-as-weaker
  host-process fallback otherwise, and outright refusal for CRITICAL-risk
  execution when neither is acceptable. `dev_agent`'s model-planned run
  commands now go through this sandbox rather than the host directly.
- **Browser automation now uses an isolated profile by default** —
  `browser_control` no longer tries your real, authenticated browser
  profile first; that requires an explicit opt-in argument, itself still
  subject to mandatory approval.
- **Security audit events** (`PolicyEvaluated`, `ApprovalRequested`,
  `ToolDenied`, `ToolExecuted`, etc.) are now emitted for every policy
  decision and tool execution, through Phase 1's structured logging.

### What did NOT change

- `actions/desktop.py`'s "task" action still uses a restricted `exec()` —
  this genuinely **cannot** be Docker-sandboxed, because it controls the
  host GUI directly (mouse/keyboard/windows), which a container has no
  access to. The real protection is now mandatory per-call human approval
  showing the generated task to you before it runs, not code isolation.
  See `docs/security-model.md` for the full reasoning — this is a
  documented, deliberate limitation, not an oversight.
- Dashboard authentication itself (pairing-key + bearer-token flow) was
  not redesigned — its cryptographic strength remains unassessed, flagged
  since the Phase 0 audit. **Do not expose the dashboard port beyond your
  local network / trusted devices.**
- The host-restricted sandbox fallback provides **no real filesystem or
  network isolation**, and no memory/CPU containment on Windows — it is
  explicitly not equivalent to Docker, and CRITICAL-risk execution refuses
  to use it.

## What Phase 1 changed (secrets/config foundation)

- **Secrets are no longer stored as plaintext, source-controllable JSON.**
  The Gemini API key is now stored via your OS keychain (through the
  optional `keyring` package) when available, or in a local file
  (`config/secrets.json`) that is excluded from git and created with
  owner-only permissions where the OS supports it.
- **No private TLS key is checked into the repository anymore.**
  `config/certs/jarvis.key` and `jarvis.crt` were removed from source
  control. The dashboard now generates its own local self-signed
  certificate at runtime if none exists, and `config/certs/` is gitignored.
- **Logs are redacted.** The centralized logging system
  (`core/logging_setup.py`) strips known secret values and secret-shaped
  substrings (API keys, bearer tokens) from every log line before it's
  written, as a safety net. Phase 6 adds a second, independent redaction
  pass for tool-call argument summaries shown in approval prompts and
  audit events.
- **`.gitignore` now covers** `config/api_keys.json`, `config/app_config.json`,
  `config/secrets.json`, `config/certs/`, `memory/long_term.json`,
  `memory/preferences.json`, `memory/memory.db`, and generated logs — none
  of these should ever be committed.

## Why self-signed certificates are for local use only

The dashboard's runtime-generated TLS certificate (`core/config/certs.py`)
is self-signed — your browser will show a one-time trust warning, which is
expected and appropriate for a certificate with no external Certificate
Authority behind it. This is suitable for **local network / self-hosted
development use**, where you personally accept the certificate on your own
devices. It is **not** equivalent to a CA-issued certificate and should not
be treated as production-grade TLS for a public-facing deployment. Public
TLS/cloud deployment architecture remains out of scope (see the Phase 0
audit's hybrid-deployment roadmap, not yet implemented).

## Configuring policy

See `docs/architecture/security-and-policy.md` for the full rule set. Quick
reference — all via `core.config.ConfigService`:

```
policy_enabled                    (default True)
default_low_risk_action           (default "allow")
default_medium_risk_action        (default "allow")
default_high_risk_action          (default "approval_required")
default_critical_risk_action      (default "approval_required")
allow_local_high_risk             (default True)
allow_remote_high_risk            (default True)
allow_critical_commands           (default True)
approval_timeout                  (default 120 seconds)
deny_remote_critical              (default True)
```

## Reporting

This is a personal/local project without a formal vulnerability disclosure
process at this time. If you fork or extend this project for broader use,
read `docs/security-model.md`'s "What Phase 6 does NOT claim" section
before considering it safe for anything beyond trusted, single-user,
local use.

