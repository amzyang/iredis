import sys
import tempfile
from unittest.mock import patch

import click
import pytest
from prompt_toolkit.formatted_text import FormattedText

from iredis.entry import (
    SkipAuthFileHistory,
    create_prompt_session,
    gather_args,
    greetings,
    is_too_tall,
    main,
    parse_url,
    write_result,
)
from iredis.utils import DSN


@pytest.mark.parametrize(
    "is_tty,raw_arg_is_raw,final_config_is_raw",
    [
        (True, None, False),
        (True, True, True),
        (True, False, False),
        (False, None, True),
        (False, True, True),
        (False, False, True),  # not tty
    ],
)
def test_command_entry_tty(is_tty, raw_arg_is_raw, final_config_is_raw, config):
    # is tty + raw -> raw
    with patch("sys.stdout.isatty") as patch_tty:
        patch_tty.return_value = is_tty
        if raw_arg_is_raw is None:
            call = ["iredis"]
        elif raw_arg_is_raw is True:
            call = ["iredis", "--raw"]
        elif raw_arg_is_raw is False:
            call = ["iredis", "--no-raw"]
        else:
            raise Exception()
        gather_args.main(call, standalone_mode=False)
        assert config.raw == final_config_is_raw


def test_disable_pager():
    from iredis.config import config

    gather_args.main(["iredis", "--decode", "utf-8"], standalone_mode=False)
    assert config.enable_pager

    gather_args.main(["iredis", "--no-pager"], standalone_mode=False)
    assert not config.enable_pager


def test_command_with_decode_utf_8():
    from iredis.config import config

    gather_args.main(["iredis", "--decode", "utf-8"], standalone_mode=False)
    assert config.decode == "utf-8"

    gather_args.main(["iredis"], standalone_mode=False)
    assert config.decode == ""


def test_command_with_shell_pipeline():
    from iredis.config import config

    gather_args.main(["iredis", "--no-shell"], standalone_mode=False)
    assert config.shell is False

    gather_args.main(["iredis"], standalone_mode=False)
    assert config.shell is True


def test_command_shell_options_higher_priority():
    from textwrap import dedent

    from iredis.config import config

    config_content = dedent(
        """
        [main]
        shell = False
        """
    )
    with open("/tmp/iredisrc", "w+") as etc_config:
        etc_config.write(config_content)

    gather_args.main(["iredis", "--iredisrc", "/tmp/iredisrc"], standalone_mode=False)
    assert config.shell is False

    gather_args.main(
        ["iredis", "--shell", "--iredisrc", "/tmp/iredisrc"], standalone_mode=False
    )
    assert config.shell is True


def test_command_with_theme():
    from iredis.config import config

    gather_args.main(["iredis"], standalone_mode=False)
    assert config.theme == "default"

    gather_args.main(["iredis", "--theme", "classic"], standalone_mode=False)
    assert config.theme == "classic"


def test_command_theme_options_higher_priority():
    from textwrap import dedent

    from iredis.config import config

    config_content = dedent(
        """
        [main]
        theme = classic
        """
    )
    with open("/tmp/iredisrc", "w+") as etc_config:
        etc_config.write(config_content)

    gather_args.main(["iredis", "--iredisrc", "/tmp/iredisrc"], standalone_mode=False)
    assert config.theme == "classic"

    gather_args.main(
        ["iredis", "--theme", "default", "--iredisrc", "/tmp/iredisrc"],
        standalone_mode=False,
    )
    assert config.theme == "default"


def test_command_with_vi_mode():
    from iredis.config import config

    gather_args.main(["iredis"], standalone_mode=False)
    assert config.vi_mode is False

    gather_args.main(["iredis", "--vi"], standalone_mode=False)
    assert config.vi_mode is True


def test_command_vi_options_higher_priority():
    from textwrap import dedent

    from iredis.config import config

    config_content = dedent(
        """
        [main]
        vi_mode = True
        """
    )
    with open("/tmp/iredisrc", "w+") as etc_config:
        etc_config.write(config_content)

    gather_args.main(["iredis", "--iredisrc", "/tmp/iredisrc"], standalone_mode=False)
    assert config.vi_mode is True

    gather_args.main(
        ["iredis", "--no-vi", "--iredisrc", "/tmp/iredisrc"],
        standalone_mode=False,
    )
    assert config.vi_mode is False


def test_prompt_session_flushes_escape_key_quickly():
    from prompt_toolkit.application import create_app_session
    from prompt_toolkit.input import create_pipe_input
    from prompt_toolkit.output import DummyOutput

    gather_args.main(["iredis", "--vi"], standalone_mode=False)
    with create_pipe_input() as pipe_input:
        with create_app_session(input=pipe_input, output=DummyOutput()):
            session = create_prompt_session()
    assert session.app.ttimeoutlen <= 0.1


@pytest.mark.parametrize(
    "url,dsn",
    [
        (
            "redis://localhost:6379/3",
            DSN(
                scheme="redis",
                host="localhost",
                port=6379,
                path=None,
                db=3,
                username=None,
                password=None,
                verify_ssl=None,
            ),
        ),
        (
            "redis://localhost:6379",
            DSN(
                scheme="redis",
                host="localhost",
                port=6379,
                path=None,
                db=0,
                username=None,
                password=None,
                verify_ssl=None,
            ),
        ),
        (
            "rediss://localhost:6379",
            DSN(
                scheme="rediss",
                host="localhost",
                port=6379,
                path=None,
                db=0,
                username=None,
                password=None,
                verify_ssl=None,
            ),
        ),
        (
            "rediss://localhost:6379/1?ssl_cert_reqs=optional",
            DSN(
                scheme="rediss",
                host="localhost",
                port=6379,
                path=None,
                db=1,
                username=None,
                password=None,
                verify_ssl="optional",
            ),
        ),
        (
            "redis://username:password@localhost:6379",
            DSN(
                scheme="redis",
                host="localhost",
                port=6379,
                path=None,
                db=0,
                username="username",
                password="password",
                verify_ssl=None,
            ),
        ),
        (
            "redis://:password@localhost:6379",
            DSN(
                scheme="redis",
                host="localhost",
                port=6379,
                path=None,
                db=0,
                username=None,
                password="password",
                verify_ssl=None,
            ),
        ),
        (
            "redis://username:pass@word@localhost:12345/2",
            DSN(
                scheme="redis",
                host="localhost",
                port=12345,
                path=None,
                db=2,
                username="username",
                password="pass@word",
                verify_ssl=None,
            ),
        ),
        (
            "redis://username@localhost:12345",
            DSN(
                scheme="redis",
                host="localhost",
                port=12345,
                path=None,
                db=0,
                username="username",
                password=None,
                verify_ssl=None,
            ),
        ),
        (
            # query string won't work for redis://
            "redis://username@localhost:6379?db=2",
            DSN(
                scheme="redis",
                host="localhost",
                port=6379,
                path=None,
                db=0,
                username="username",
                password=None,
                verify_ssl=None,
            ),
        ),
        (
            "unix://username:password2@/tmp/to/socket.sock?db=0",
            DSN(
                scheme="unix",
                host=None,
                port=None,
                path="/tmp/to/socket.sock",
                db=0,
                username="username",
                password="password2",
                verify_ssl=None,
            ),
        ),
        (
            "unix://:password3@/path/to/socket.sock",
            DSN(
                scheme="unix",
                host=None,
                port=None,
                path="/path/to/socket.sock",
                db=0,
                username=None,
                password="password3",
                verify_ssl=None,
            ),
        ),
        (
            "unix:///tmp/socket.sock",
            DSN(
                scheme="unix",
                host=None,
                port=None,
                path="/tmp/socket.sock",
                db=0,
                username=None,
                password=None,
                verify_ssl=None,
            ),
        ),
    ],
)
def test_parse_url(url, dsn):
    assert parse_url(url) == dsn


@pytest.mark.parametrize(
    "command,record",
    [
        ("set foo bar", True),
        ("set auth bar", True),
        ("auth 123", False),
        ("AUTH hello", False),
        ("AUTH hello world", False),
    ],
)
def test_history(command, record):
    f = tempfile.TemporaryFile("w+")
    history = SkipAuthFileHistory(f.name)
    assert history._loaded_strings == []
    history.append_string(command)
    assert (command in history._loaded_strings) is record


def test_write_result_for_str(capsys):
    write_result("hello")
    captured = capsys.readouterr()
    assert captured.out == "hello\n"


def test_write_result_for_bytes(capsys):
    write_result(b"hello")
    captured = capsys.readouterr()
    assert captured.out == "hello\n"


def test_write_result_for_formatted_text():
    ft = FormattedText([("class:keyword", "set"), ("class:string", "hello world")])
    # just this test not raise means ok
    write_result(ft)


def test_is_too_tall_for_formatted_text():
    ft = FormattedText([("class:key", f"key-{index}\n") for index in range(21)])
    assert is_too_tall(ft, 20)
    assert not is_too_tall(ft, 22)


def test_is_too_tall_for_bytes():
    byte_text = b"".join([b"key\n" for index in range(21)])
    assert is_too_tall(byte_text, 20)
    assert not is_too_tall(byte_text, 23)


def test_natmap_parsed_into_config():
    from iredis.config import config

    gather_args.main(
        [
            "iredis",
            "--natmap",
            "node1.example.com:6379:127.0.0.1:6371,node2.example.com:6379:127.0.0.1:6372",
        ],
        standalone_mode=False,
    )
    assert config.natmap == {
        "node1.example.com:6379": ("127.0.0.1", 6371),
        "node2.example.com:6379": ("127.0.0.1", 6372),
    }


def test_greetings_show_server_version(config, capsys):
    config.version = "7.0.5"
    greetings()
    assert "redis-server  7.0.5" in capsys.readouterr().out


def test_greetings_hide_server_version_when_no_info(config, capsys):
    config.version = "7.0.5"
    config.no_info = True
    greetings()
    out = capsys.readouterr().out
    assert "iredis" in out
    assert "redis-server" not in out


@pytest.mark.parametrize("shell", ["bash", "zsh", "fish"])
def test_shell_completion_source_short_circuits_main(monkeypatch, capsys, shell):
    monkeypatch.setattr(sys, "argv", ["iredis"])
    monkeypatch.setenv("_IREDIS_COMPLETE", f"{shell}_source")
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0
    assert "_IREDIS_COMPLETE" in capsys.readouterr().out


def test_shell_completion_completes_options(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["iredis"])
    monkeypatch.setenv("_IREDIS_COMPLETE", "zsh_complete")
    monkeypatch.setenv("COMP_WORDS", "iredis --the")
    monkeypatch.setenv("COMP_CWORD", "1")
    with pytest.raises(SystemExit):
        main()
    assert "--theme" in capsys.readouterr().out


def test_decode_rejects_invalid_encoding():
    with pytest.raises(click.exceptions.BadParameter):
        gather_args.main(["iredis", "--decode", "not-a-codec"], standalone_mode=False)


def test_decode_accepts_codec_alias(config):
    gather_args.main(["iredis", "--decode", "u8"], standalone_mode=False)
    assert config.decode == "u8"


def test_main_invalid_decode_shows_error_not_traceback(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["iredis", "--decode", "bogus"])
    main()
    assert "Invalid value" in capsys.readouterr().err


def _complete(monkeypatch, comp_words, comp_cword):
    monkeypatch.setattr(sys, "argv", ["iredis"])
    monkeypatch.setenv("_IREDIS_COMPLETE", "zsh_complete")
    monkeypatch.setenv("COMP_WORDS", comp_words)
    monkeypatch.setenv("COMP_CWORD", comp_cword)
    with pytest.raises(SystemExit) as exc_info:
        main()
    return exc_info.value.code


def test_shell_completion_decode_suggests_encodings(monkeypatch, capsys):
    _complete(monkeypatch, "iredis --decode", "2")
    assert "utf-8" in capsys.readouterr().out


def test_shell_completion_decode_filters_by_prefix(monkeypatch, capsys):
    _complete(monkeypatch, "iredis --decode gb", "2")
    out = capsys.readouterr().out
    assert "gbk" in out
    assert "gb18030" in out
    assert "utf-8" not in out


def test_shell_completion_dsn_reads_aliases_from_iredisrc(
    monkeypatch, capsys, tmp_path
):
    iredisrc = tmp_path / "iredisrc"
    iredisrc.write_text("[alias_dsn]\ndev = redis://localhost:6379/0\n")
    monkeypatch.chdir(tmp_path)
    _complete(monkeypatch, f"iredis --iredisrc {iredisrc} --dsn", "4")
    assert "dev" in capsys.readouterr().out


def test_shell_completion_dsn_missing_config_is_silent(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    exit_code = _complete(
        monkeypatch, "iredis --iredisrc /nonexistent/iredisrc --dsn", "4"
    )
    assert exit_code == 0
    assert capsys.readouterr().out.strip() == ""


@pytest.mark.parametrize("option", ["--iredisrc", "--socket"])
def test_shell_completion_path_options_use_file_type(monkeypatch, capsys, option):
    _complete(monkeypatch, f"iredis {option}", "2")
    assert "file" in capsys.readouterr().out
