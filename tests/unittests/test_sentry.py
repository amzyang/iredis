import sys
import types
from textwrap import dedent

from iredis.config import load_config_files
from iredis.sentry import resolve_dsn, setup_sentry


def test_resolve_dsn_env_var_wins():
    environ = {"IREDIS_SENTRY_DSN": "https://env@sentry.io/1"}
    assert (
        resolve_dsn(config_dsn="https://rc@sentry.io/2", environ=environ)
        == "https://env@sentry.io/1"
    )


def test_resolve_dsn_config_over_build_dsn(monkeypatch):
    monkeypatch.setattr("iredis.sentry.BUILD_DSN", "https://build@sentry.io/3")
    assert (
        resolve_dsn(config_dsn="https://rc@sentry.io/2", environ={})
        == "https://rc@sentry.io/2"
    )


def test_resolve_dsn_falls_back_to_build_dsn(monkeypatch):
    monkeypatch.setattr("iredis.sentry.BUILD_DSN", "https://build@sentry.io/3")
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
