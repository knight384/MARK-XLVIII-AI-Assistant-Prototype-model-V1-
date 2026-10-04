"""
core.config.certs — local, self-signed TLS certificate generation.

Phase 0 found a private TLS key and certificate checked into source control
at config/certs/jarvis.key / jarvis.crt. That is fixed by:
  1. removing those tracked files from the repository,
  2. gitignoring config/certs/ entirely, and
  3. generating a fresh self-signed cert/key pair here, at runtime, the first
     time the dashboard needs one and none exists on disk.

IMPORTANT — scope: this produces a self-signed certificate suitable for
local/self-hosted development use only (the same trust model the app already
had, just no longer with a shared private key baked into every clone of the
repository). It is NOT a production/public-Internet TLS solution — that is
explicitly deferred to a later phase's cloud/deployment architecture work
(see the Phase 0 audit, Part 15 / hybrid deployment).

Uses the `cryptography` package, which the dashboard already depends on.
"""
from __future__ import annotations

import datetime
import logging
import socket
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def ensure_self_signed_cert(cert_file: Path, key_file: Path,
                             common_name: Optional[str] = None) -> bool:
    """Ensure cert_file/key_file exist, generating a local self-signed pair
    if not. Returns True if a usable cert/key pair is present on disk after
    this call, False if generation was attempted and failed (fails safe —
    the dashboard's existing `_ssl_enabled()` check will then simply see no
    cert and fall back to plain HTTP, exactly as it does today when no certs
    were provisioned).
    """
    if cert_file.exists() and key_file.exists():
        return True

    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except ImportError:
        logger.warning(
            "cryptography package not installed — cannot generate a local TLS "
            "certificate. Dashboard will fall back to plain HTTP (matches "
            "existing behavior when no cert is present)."
        )
        return False

    try:
        cert_file.parent.mkdir(parents=True, exist_ok=True)

        cn = common_name or _best_effort_hostname()

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, cn),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "JARVIS Local Dev (self-signed)"),
        ])

        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=825))  # local-dev shelf life
            .add_extension(
                x509.SubjectAlternativeName([
                    x509.DNSName("localhost"),
                    x509.DNSName(cn),
                    x509.IPAddress(__import__("ipaddress").ip_address("127.0.0.1")),
                ]),
                critical=False,
            )
            .sign(key, hashes.SHA256())
        )

        key_file.write_bytes(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

        try:
            import os
            import stat
            os.chmod(key_file, stat.S_IRUSR | stat.S_IWUSR)  # best-effort, POSIX only
        except Exception:
            pass

        logger.info(
            "Generated local self-signed TLS certificate at %s (dev/local use only).",
            cert_file,
        )
        return True

    except Exception as exc:
        logger.error(
            "Failed to generate local self-signed TLS certificate (%s). "
            "Dashboard will fall back to plain HTTP.", type(exc).__name__,
        )
        return False


def _best_effort_hostname() -> str:
    try:
        return socket.gethostname() or "localhost"
    except Exception:
        return "localhost"
