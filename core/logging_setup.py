"""
core.logging_setup — centralized stdlib logging configuration (Phase 1).

Replaces scattered `print()` calls used for operational events (startup,
tool dispatch, errors, dashboard status, installer progress) with standard
`logging`. Deliberately stdlib-only — no third-party logging framework.

Usage (once, at process startup — e.g. top of main.py):
    from core.logging_setup import configure_logging
    configure_logging()

Everywhere else:
    import logging
    logger = logging.getLogger(__name__)
    logger.info("Dashboard listening on %s", url)

Secret redaction: a logging.Filter strips any Gemini API key, bearer token,
or other configured secret value out of every record before it is emitted,
so a secret ending up in an f-string passed to logger.info(...) does not
leak into console or file logs. This is a safety net, not a substitute for
simply not logging secrets in the first place.
"""
from __future__ import annotations

import logging
import logging.handlers
import re
import sys
from pathlib import Path
from typing import Iterable

_REDACTED = "***REDACTED***"

# Patterns that are structurally likely to be secrets, independent of any
# specific known value (belt-and-suspenders alongside the exact-value filter
# below, which redacts the actual configured Gemini key/tokens).
_SECRET_PATTERNS = [
    re.compile(r"(gemini_api_key[\"']?\s*[:=]\s*[\"']?)([^\s\"',}]+)", re.IGNORECASE),
    re.compile(r"(api[_-]?key[\"']?\s*[:=]\s*[\"']?)([^\s\"',}]+)", re.IGNORECASE),
    re.compile(r"(bearer\s+)([A-Za-z0-9\-._~+/]+=*)", re.IGNORECASE),
    re.compile(r"(authorization[\"']?\s*[:=]\s*[\"']?)([^\s\"',}]+)", re.IGNORECASE),
]


class SensitiveDataFilter(logging.Filter):
    """Redacts known secret values and secret-shaped substrings from every
    log record before it's formatted/emitted."""

    def __init__(self, known_secrets: Iterable[str] = ()):
        super().__init__()
        self._known_secrets = [s for s in known_secrets if s]

    def add_secret(self, value: str) -> None:
        if value and value not in self._known_secrets:
            self._known_secrets.append(value)

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True  # never block logging due to a formatting error here

        redacted = msg
        for secret in self._known_secrets:
            if secret and secret in redacted:
                redacted = redacted.replace(secret, _REDACTED)
        for pattern in _SECRET_PATTERNS:
            redacted = pattern.sub(lambda m: m.group(1) + _REDACTED, redacted)

        if redacted != msg:
            record.msg = redacted
            record.args = ()
        return True


_sensitive_filter = SensitiveDataFilter()
_configured = False


def register_secret(value: str) -> None:
    """Register a live secret value (e.g. the loaded Gemini API key) so it is
    scrubbed from logs even if some call site logs it directly by mistake."""
    _sensitive_filter.add_secret(value)


def configure_logging(level: int = logging.INFO,
                       log_dir: Path | None = None,
                       log_to_file: bool = True) -> None:
    """Idempotent — safe to call more than once (later calls are no-ops)."""
    global _configured
    if _configured:
        return
    _configured = True

    root = logging.getLogger()
    root.setLevel(level)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler(stream=sys.stdout)
    console.setFormatter(fmt)
    console.addFilter(_sensitive_filter)
    root.addHandler(console)

    if log_to_file:
        try:
            log_dir = log_dir or (Path(__file__).resolve().parent.parent / "logs")
            log_dir.mkdir(parents=True, exist_ok=True)
            file_handler = logging.handlers.RotatingFileHandler(
                log_dir / "jarvis.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8",
            )
            file_handler.setFormatter(fmt)
            file_handler.addFilter(_sensitive_filter)
            root.addHandler(file_handler)
        except Exception:
            # Logging setup must never crash the app; console logging above
            # is already in place as a fallback.
            root.warning("Could not set up file logging; console logging only.")

    # Quiet down noisy third-party libraries at INFO/DEBUG unless the user
    # explicitly wants verbose output from them.
    for noisy in ("urllib3", "asyncio", "websockets"):
        logging.getLogger(noisy).setLevel(max(level, logging.WARNING))


def is_configured() -> bool:
    return _configured
