import logging
import sys
import types
from textwrap import dedent

from iredis.config import load_config_files
from iredis.sentry import (
    SentryTestError,
    collect_status,
    resolve_dsn,
    run_diagnose,
    setup_sentry,
)


def test_resolve_dsn_env_var_wins():
    environ = {"IREDIS_SENTRY_DSN": "https://env@sentry.io/1"}
    assert (
        resolve_dsn(config_dsn="https://rc@sentry.io/2", environ=environ)
        == "https://env@sentry.io/1"
    )


def test_resolve_dsn_config_over_stamped_dsn(monkeypatch):
    monkeypatch.setattr("iredis.sentry.SENTRY_DSN", "https://build@sentry.io/3")
    assert (
        resolve_dsn(config_dsn="https://rc@sentry.io/2", environ={})
        == "https://rc@sentry.io/2"
    )


def test_resolve_dsn_falls_back_to_stamped_dsn(monkeypatch):
    monkeypatch.setattr("iredis.sentry.SENTRY_DSN", "https://build@sentry.io/3")
    assert resolve_dsn(config_dsn="", environ={}) == "https://build@sentry.io/3"


def test_resolve_dsn_empty_when_nothing_configured():
    assert resolve_dsn(config_dsn=None, environ={}) == ""


def test_setup_sentry_disabled_by_config():
    assert setup_sentry("https://rc@sentry.io/2", enabled=False, environ={}) is False


def test_setup_sentry_empty_dsn_disables_telemetry():
    assert setup_sentry(config_dsn="", environ={}) is False


def test_setup_sentry_without_sdk_installed(monkeypatch):
    monkeypatch.setitem(sys.modules, "sentry_sdk", None)
    assert setup_sentry("https://rc@sentry.io/2", environ={}) is False


def test_setup_sentry_initializes_sdk(monkeypatch):
    calls = []
    fake_sdk = types.SimpleNamespace(init=lambda **kwargs: calls.append(kwargs))
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake_sdk)

    assert setup_sentry("https://rc@sentry.io/2", environ={}) is True

    (kwargs,) = calls
    assert kwargs["dsn"] == "https://rc@sentry.io/2"
    assert kwargs["release"].startswith("iredis@")
    assert kwargs["traces_sample_rate"] == 0
    assert kwargs["send_default_pii"] is False


def test_collect_status_nothing_configured():
    status = collect_status(config_dsn=None, environ={})
    assert status["dsn"] == ""
    assert status["dsn_source"] is None
    assert status["host"] is None
    assert status["public_key"] is None
    assert status["project"] is None
    assert status["enabled"] is True
    assert status["release"].startswith("iredis@")


def test_collect_status_parses_env_dsn():
    environ = {"IREDIS_SENTRY_DSN": "https://key123@sentry.example.com:9000/42"}
    status = collect_status(config_dsn=None, environ=environ)
    assert status["dsn_source"] == "environment"
    assert status["dsn"] == "https://key123@sentry.example.com:9000/42"
    assert status["host"] == "sentry.example.com:9000"
    assert status["public_key"] == "key123"
    assert status["project"] == "42"


def test_collect_status_iredisrc_source():
    status = collect_status(config_dsn="https://rc@sentry.io/2", environ={})
    assert status["dsn_source"] == "iredisrc"
    assert status["host"] == "sentry.io"


def test_collect_status_build_time_source(monkeypatch):
    monkeypatch.setattr("iredis.sentry.SENTRY_DSN", "https://build@sentry.io/3")
    status = collect_status(config_dsn=None, environ={})
    assert status["dsn_source"] == "build-time"


def test_collect_status_sdk_not_installed(monkeypatch):
    monkeypatch.setitem(sys.modules, "sentry_sdk", None)
    status = collect_status(config_dsn=None, environ={})
    assert status["sdk_version"] is None


def test_collect_status_sdk_version(monkeypatch):
    fake_sdk = types.SimpleNamespace(VERSION="9.9.9")
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake_sdk)
    status = collect_status(config_dsn=None, environ={})
    assert status["sdk_version"] == "9.9.9"


def test_setup_sentry_debug_passthrough(monkeypatch):
    calls = []
    fake_sdk = types.SimpleNamespace(init=lambda **kwargs: calls.append(kwargs))
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake_sdk)

    assert setup_sentry("https://rc@sentry.io/2", environ={}, debug=True) is True

    (kwargs,) = calls
    assert kwargs["debug"] is True


def test_run_diagnose_inactive_prints_status_and_returns_1(capsys):
    assert run_diagnose(config_dsn=None, enabled=True, environ={}) == 1
    out = capsys.readouterr().out
    assert "not configured" in out
    assert "inactive" in out


def test_run_diagnose_disabled_by_config_returns_1(capsys):
    assert run_diagnose("https://rc@sentry.io/2", enabled=False, environ={}) == 1
    out = capsys.readouterr().out
    assert "inactive" in out


def test_run_diagnose_lifts_global_logging_disable():
    logging.disable(logging.CRITICAL)
    run_diagnose(config_dsn=None, environ={})
    assert logging.root.manager.disable == logging.NOTSET


def test_run_diagnose_sends_test_events(monkeypatch, capsys):
    captured = {}

    def fake_init(**kwargs):
        captured["init"] = kwargs

    def fake_capture_message(message):
        captured["message"] = message
        return "msg-id-1"

    def fake_capture_exception(error):
        captured["exception"] = error
        return "exc-id-2"

    def fake_flush(timeout=None):
        captured["flush"] = timeout

    fake_sdk = types.SimpleNamespace(
        VERSION="9.9.9",
        init=fake_init,
        capture_message=fake_capture_message,
        capture_exception=fake_capture_exception,
        flush=fake_flush,
    )
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake_sdk)

    assert run_diagnose("https://rc@sentry.io/2", environ={}) == 0

    assert captured["init"]["debug"] is True
    assert isinstance(captured["exception"], SentryTestError)
    assert captured["flush"] == 5
    out = capsys.readouterr().out
    assert "msg-id-1" in out
    assert "exc-id-2" in out


def test_load_config_files_reads_sentry_options(config, tmp_path):
    iredisrc = tmp_path / "iredisrc"
    iredisrc.write_text(
        dedent(
            """
            [main]
            sentry = False
            sentry_dsn = https://rc@sentry.io/2
            """
        )
    )
    load_config_files(str(iredisrc))
    assert config.sentry is False
    assert config.sentry_dsn == "https://rc@sentry.io/2"


def test_load_config_files_sentry_defaults(config, tmp_path):
    iredisrc = tmp_path / "iredisrc"
    iredisrc.write_text("")
    load_config_files(str(iredisrc))
    assert config.sentry is True
    assert config.sentry_dsn == ""
