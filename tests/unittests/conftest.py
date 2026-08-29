import pytest


@pytest.fixture(autouse=True)
def isolate_iredisrc(monkeypatch, tmp_path):
    """防止本机 /etc/iredisrc、~/.iredisrc、$PWD/.iredisrc 泄漏进测试。"""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr("iredis.config.system_config_file", str(tmp_path / "etc"))
    monkeypatch.setattr("iredis.config.pwd_config_file", str(tmp_path / "pwd"))
