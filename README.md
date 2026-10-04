# JARVIS / MARK XLVIII

A desktop AI assistant with realtime voice interaction (Google Gemini Live), a
PyQt6 HUD, and a broad set of tools: app launching, browser automation, file
management, computer control, a developer/coding agent, reminders, messaging,
system monitoring, and a phone-accessible remote-control dashboard.

## Status

This repository has completed **Phase 1** of a multi-phase refactor (see
`JARVIS_PHASE0_AUDIT.md` for the full audit and roadmap). Phase 1 is a
foundation/hygiene pass — it centralizes configuration, secret storage, TLS
certificate handling, and logging, **without changing any voice, tool, or UI
behavior**. Later phases (Model Gateway, Tool Registry, multi-agent runtime,
security sandboxing, etc.) are described in the audit but not yet implemented.

## Architecture (current)

```
ui.py (PyQt6 HUD)
   │
main.py — JarvisLive: a persistent Gemini Live (realtime audio) session
   │        with a 19-tool function-calling dispatcher
   │
actions/*.py — one module per tool (browser control, file management,
   │            computer control, developer agent, reminders, etc.)
   │
dashboard/server.py — FastAPI remote-control web server (phone/second device)
   │
core/config/ — centralized configuration & secret storage (Phase 1)
core/logging_setup.py — centralized logging (Phase 1)
memory/ — flat JSON user-preferences store
```

A full architectural breakdown, provider inventory, security assessment, and
phased roadmap toward a multi-agent / model-agnostic / local-Docker-cloud
hybrid platform is in `JARVIS_PHASE0_AUDIT.md`.

## Installation

Requires Python 3.10+.

```bash
pip install -r requirements.txt
python -m playwright install chromium   # one-time, for browser automation
```

`requirements.txt` is the source of truth for dependencies. `core/installer.py`
remains as a convenience fallback that auto-installs missing packages on
first launch, but is not the canonical way to set up an environment anymore.

## Configuration

On first launch, the app's setup wizard asks for your Gemini API key and OS.
This is stored via a centralized configuration service (`core/config/`):

- **Secrets** (currently: your Gemini API key) are stored via your OS
  keychain/credential manager (through the optional `keyring` package) when
  available, or in a local file at `config/secrets.json` — **never** in a
  file tracked by git.
- **Non-secret settings** (OS, STT/TTS engine choice, dashboard port, cached
  camera index, etc.) live in `config/app_config.json`.

If you have an older copy of this repo with `config/api_keys.json` still
present, it is automatically and non-destructively migrated the first time
the new config service runs (see `DEVELOPMENT.md` for details). The original
file is left in place, just no longer read.

## Running locally

```bash
python main.py
```

## Remote dashboard (phone control)

The dashboard serves a local web UI reachable from your phone on the same
network, with token-based pairing. It generates its own local self-signed
TLS certificate on first run (see `SECURITY.md` — this is for local/
self-hosted use, not public Internet exposure).

## Security

Please read `SECURITY.md` before exposing this application beyond your own
local network. It has broad computer-control and code-execution capabilities
that are appropriate for a trusted single-user local assistant, but have
**not** yet been hardened for untrusted or multi-user/public deployment —
that work is scoped for a later phase.

## Development

See `DEVELOPMENT.md` for project structure, running tests, and contribution
notes.
