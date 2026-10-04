# Sandbox Architecture

`core/sandbox/` provides isolated execution for untrusted/model-generated
code and commands. It replaces the previous `exec()`-with-a-Python-builtins-
allowlist approach in `actions/desktop.py`, which was never a real security
boundary (Phase 0 audit finding) — see `docs/security-model.md` for the
threat model.

## Docker CLI vs Docker SDK — decision (spec Part 65)

**Decision: Docker CLI (subprocess), not the `docker` Python SDK.**

| Factor | CLI | SDK |
|---|---|---|
| New dependency | None — uses stdlib `subprocess` | Adds `docker` to `requirements.txt` |
| Error handling | Exit code + stderr, simple to reason about | SDK-specific exception hierarchy |
| Windows behavior (spec Part 66) | Identical whether Docker Desktop exposes a named pipe or TCP socket | SDK transport auto-detection is another thing to misconfigure |
| Portability | Same `docker run ...` invocation via WSL2/Docker Desktop/native Linux | SDK-specific setup per platform |
| What we need | `run`, `kill`, resource flags, volume mount — all one-shot CLI calls | Full client for a single-purpose "run this, capture output" use case |

Given this is a single-purpose "run this, capture output, clean up"
requirement, the CLI meets every actual need without adding a new pip
dependency or an API-version-compatibility surface to track.

## Architecture

```python
class Sandbox(ABC):
    backend_name: str
    is_real_isolation: bool
    def is_available(self) -> bool: ...
    def execute_command(self, command: list[str], workspace, limits, cancellation_token=None) -> SandboxResult: ...
    def execute_python(self, code: str, workspace, limits, cancellation_token=None) -> SandboxResult: ...
```

Two implementations:

- **`DockerSandbox`** (`is_real_isolation = True`) — `docker run --rm
  --network none --memory <N>m --cpus <N> --pids-limit <N> --security-opt
  no-new-privileges --cap-drop ALL -v <workspace>:/workspace -w /workspace
  <image> <command>`. Real isolation: no host filesystem access beyond the
  mounted workspace, no added Linux capabilities, network denied unless
  explicitly enabled.
- **`HostRestrictedSandbox`** (`is_real_isolation = False`) — **NOT
  equivalent to a real security boundary.** A plain OS subprocess with:
  `shell=False` always (spec Part 33 — no shell metacharacter
  interpretation), a stripped environment (no inherited API keys/tokens
  from the parent process), the workspace directory as `cwd`, and a hard
  timeout. It provides **no filesystem isolation** (can read/write
  anywhere the OS user account can), **no network isolation**, and **no
  memory/CPU containment on Windows** (POSIX `resource` rlimits used on
  Linux/macOS don't exist there). This exists only so JARVIS can still run
  low-risk generated code when Docker is unavailable — not to pretend
  equivalent safety.

`SandboxManager` picks between them:

```python
manager.select_backend(risk_level) -> Sandbox | None
```

- Docker available → always use it, regardless of risk level.
- Docker unavailable → `HostRestrictedSandbox` for LOW/MEDIUM/HIGH only.
- Docker unavailable + CRITICAL → **returns `None`** — the caller (and, at
  the tool layer, the PolicyEngine via `requires_sandbox`) must refuse to
  execute rather than silently downgrade to an unsandboxed host run (spec
  Part 25: "The system should be able to refuse dangerous execution if no
  safe sandbox is available.").

Docker availability is probed lazily (`docker info`) and cached for 30s
(spec Part 68 — don't add startup latency; don't re-probe every call).

## Workspace model (spec Part 28-29)

`SandboxWorkspace`: a unique temp directory per execution
(`tempfile.gettempdir()/jarvis_sandbox/<uuid>`), with `resolve()` refusing
any path that would escape it (path-traversal protection — tested against
both `../../etc/passwd` and nested `subdir/../../outside.txt` attempts).
Context-manager (`with SandboxWorkspace() as ws:`) guarantees cleanup even
on exception. By default, nothing outside the workspace is visible to
sandboxed code — no `$HOME`, no `%APPDATA%`, no credential stores, no SSH
keys, no browser profiles, no `.env` files.

For `DeveloperAgent`'s model-planned run command specifically
(`actions/dev_agent.py::_run_project`), `SandboxManager.execute_command_in_dir()`
runs against the **actual project directory** the agent already built
(not a throwaway copy) — the code being run needs to be the real generated
project, not a fresh sandbox clone of it. This is a deliberate, narrower
exception to the "fresh workspace per execution" model, used only for this
one call site.

## Resource limits (spec Part 31)

```python
@dataclass(frozen=True)
class ResourceLimits:
    timeout_seconds: float = 30.0
    cpu_limit: float = 1.0
    memory_limit_mb: int = 512
    process_limit: int = 64
    output_limit_bytes: int = 1_000_000
    network_enabled: bool = False   # default DENY (spec Part 30)
```

Docker enforces these via `--memory`/`--cpus`/`--pids-limit`/`--network`.
The host-restricted fallback applies memory/process rlimits on POSIX only
(best-effort, documented as such) and always applies the timeout and
output-byte cap regardless of platform.

## Timeout, cancellation, cleanup (spec Parts 35-37)

Both backends terminate the process/container on timeout
(`subprocess.TimeoutExpired` → `kill()` for the fallback; `docker kill
<container>` for Docker) rather than merely giving up waiting. Both check
`CancellationToken.is_cancelled` and terminate if set. `DockerSandbox`
kills the named container in a `finally` block as belt-and-suspenders on
top of `--rm`, so a container is never orphaned even on an unexpected
exception path. `SandboxWorkspace.cleanup()` runs via `__exit__` /
`finally` regardless of success/failure/timeout/cancellation.

## Network policy (spec Part 30)

Default `network_enabled=False` → Docker gets `--network none`; the
host-restricted fallback has no network isolation mechanism at all (it's
a plain OS process — see the module docstring's explicit limitation), so
`network_enabled` on that backend is currently advisory metadata rather
than an enforced restriction. This asymmetry is intentional and disclosed,
not hidden: it's exactly why CRITICAL-risk requests refuse the fallback
outright (see `SandboxManager.select_backend()` above).

## What is NOT sandboxed, and why (spec Part 59/67 — no security theater)

`actions/desktop.py`'s "task" action generates code that controls the
**host GUI directly** (`pyautogui` mouse/keyboard, window management,
registry reads). A Docker container has no access to the host's
display/input devices — sandboxing this would not secure the feature, it
would break it entirely. Rather than claim false isolation, Phase 6:

1. Keeps `desktop_control`'s `requires_sandbox=False` (explicitly, with
   the reasoning in code and in `docs/security-model.md`).
2. Relies on the real protection instead: CRITICAL risk classification
   means **every single call requires human approval** via the
   PolicyEngine, with the generated task description visible in the
   approval prompt for review before execution — transparency and consent
   in place of an isolation guarantee that isn't achievable here.

## Limitations

- Host-restricted fallback provides no real isolation (documented above,
  by design — not an oversight).
- No memory/CPU containment on Windows without Docker.
- Docker sandbox tests in `tests/sandbox/test_sandbox.py` are marked
  `skipif` when the `docker` binary isn't present — this development
  environment does not have Docker installed, so those specific tests are
  **NOT VERIFIED** here; everything else (workspace isolation, the
  host-restricted fallback's actual behavior, `SandboxManager`'s selection
  logic under mocked availability) is verified.
- `_install_dependencies` (pip install) in `dev_agent.py` still runs on
  the host directly into the project directory — sandboxing it would mean
  installed packages don't end up where the built project can use them.
  This is gated by the same mandatory CRITICAL-risk policy approval as
  every other `dev_agent` call, not by sandbox isolation.
