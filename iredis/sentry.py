"""Crash telemetry via Sentry, disabled unless a DSN is available.

Only iredis's own unhandled crashes are reported, never user commands or
redis data. Telemetry silently stays off when no DSN is configured or
sentry-sdk is not installed (install with `pip install iredis[sentry]`).
"""

import logging
import os

from . import __version__

logger = logging.getLogger(__name__)

# Release-build fallback DSN, the Python counterpart of an ldflags-injected
# value: the release process may stamp a real DSN here; an empty string
# (local checkouts, forks) means telemetry disabled — never a failure.
SENTRY_DSN = ""

DSN_ENVIRON = "IREDIS_SENTRY_DSN"


def resolve_dsn(config_dsn=None, environ=os.environ):
    """DSN priority: environment variable > iredisrc > build-time fallback."""
    return environ.get(DSN_ENVIRON) or config_dsn or SENTRY_DSN


def setup_sentry(config_dsn=None, enabled=True, environ=os.environ):
    """Initialize Sentry, returning whether telemetry is active."""
    if not enabled:
        return False
    dsn = resolve_dsn(config_dsn, environ)
    if not dsn:
        return False
    try:
        import sentry_sdk  # ty: ignore[unresolved-import]
    except ImportError:
        logger.info("sentry-sdk not installed, telemetry disabled")
        return False
    sentry_sdk.init(
        dsn=dsn,
        release=f"iredis@{__version__}",
        traces_sample_rate=0,
        send_default_pii=False,
    )
    logger.info("sentry telemetry enabled")
    return True
