"""Crash telemetry via Sentry, disabled unless a DSN is available.

Only iredis's own unhandled crashes are reported, never user commands or
redis data. Telemetry silently stays off when no DSN is configured or
sentry-sdk is not installed (install with `pip install iredis[sentry]`).

The hidden `iredis sentry` subcommand (see entry.main) prints this module's
resolved configuration and fires test events, for end-to-end verification.
"""

import logging
import os
from urllib.parse import urlsplit

import click

from . import __version__

logger = logging.getLogger(__name__)

# Release-build fallback DSN, the Python counterpart of an ldflags-injected
# value: the release process may stamp a real DSN here; an empty string
# (local checkouts, forks) means telemetry disabled — never a failure.
SENTRY_DSN = ""

DSN_ENVIRON = "IREDIS_SENTRY_DSN"


class SentryTestError(Exception):
    """Raised and captured on purpose by the hidden `iredis sentry` check."""


def resolve_dsn(config_dsn=None, environ=os.environ):
    """DSN priority: environment variable > iredisrc > build-time fallback."""
    return environ.get(DSN_ENVIRON) or config_dsn or SENTRY_DSN


def setup_sentry(config_dsn=None, enabled=True, environ=os.environ, debug=False):
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
        debug=debug,
    )
    logger.info("sentry telemetry enabled")
    return True


def collect_status(config_dsn=None, enabled=True, environ=os.environ):
    """Snapshot the telemetry configuration as a dict, without initializing
    the SDK, so the diagnostic can show it even when telemetry is off."""
    dsn = resolve_dsn(config_dsn, environ)
    if environ.get(DSN_ENVIRON):
        dsn_source = "environment"
    elif config_dsn:
        dsn_source = "iredisrc"
    elif SENTRY_DSN:
        dsn_source = "build-time"
    else:
        dsn_source = None
    try:
        import sentry_sdk  # ty: ignore[unresolved-import]

        sdk_version = getattr(sentry_sdk, "VERSION", "unknown")
    except ImportError:
        sdk_version = None
    parts = urlsplit(dsn) if dsn else None
    host = parts.hostname if parts else None
    if parts and parts.port:
        host = f"{host}:{parts.port}"
    return {
        "enabled": enabled,
        "sdk_version": sdk_version,
        "dsn": dsn,
        "dsn_source": dsn_source,
        "host": host,
        "public_key": parts.username if parts else None,
        "project": parts.path.strip("/") if parts else None,
        "release": f"iredis@{__version__}",
    }


def send_test_events():
    """Fire one message and one exception at Sentry, return their event ids."""
    import sentry_sdk  # ty: ignore[unresolved-import]

    message_id = sentry_sdk.capture_message("iredis sentry e2e test message")
    try:
        raise SentryTestError("iredis sentry e2e test exception")
    except SentryTestError as error:
        exception_id = sentry_sdk.capture_exception(error)
    sentry_sdk.flush(timeout=5)
    return message_id, exception_id


def run_diagnose(config_dsn=None, enabled=True, environ=os.environ):
    """Hidden `iredis sentry` subcommand: print the resolved telemetry
    status, then send one test message and one test exception if telemetry
    can be activated. Returns the process exit code: 0 when the test events
    were flushed, 1 when telemetry is inactive."""
    # iredis silences logging entirely when log_location is unset (see
    # entry.setup_log); lift that or the SDK's debug transport logs below
    # would never reach stderr
    logging.disable(logging.NOTSET)
    status = collect_status(config_dsn, enabled, environ)
    click.secho("Sentry telemetry status", bold=True)
    rows = [
        ("sentry-sdk", status["sdk_version"] or "not installed"),
        ("enabled", str(status["enabled"])),
        ("dsn", status["dsn"] or "(not configured)"),
        ("dsn source", status["dsn_source"] or "-"),
        ("host", status["host"] or "-"),
        ("public key", status["public_key"] or "-"),
        ("project", status["project"] or "-"),
        ("release", status["release"]),
    ]
    for name, value in rows:
        click.echo(f"  {name:<11}: {value}")

    # debug=True makes the SDK print transport logs to stderr, so a bad
    # host or rejected key is visible right here instead of failing silently
    if not setup_sentry(config_dsn, enabled=enabled, environ=environ, debug=True):
        click.secho("Telemetry is inactive, no test events sent.", fg="yellow")
        return 1
    click.echo("Sending a test message and a test exception...")
    message_id, exception_id = send_test_events()
    click.echo(f"  message event id  : {message_id}")
    click.echo(f"  exception event id: {exception_id}")
    click.secho(
        "Events flushed, check the Sentry project for both event ids.", fg="green"
    )
    return 0
