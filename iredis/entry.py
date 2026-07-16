import codecs
import logging
import os
import platform
import sys
import time
from pathlib import Path

import click
from prompt_toolkit import PromptSession, print_formatted_text
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.cursor_shapes import ModalCursorShapeConfig
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding.bindings.named_commands import (
    register as prompt_register,
)

from . import __version__
from .bottom import BottomToolbar
from .client import Client
from .completers import IRedisCompleter
from .config import (
    config,
    load_config_files,
    pwd_config_file,
    read_config_file,
    system_config_file,
)
from .key_bindings import kb as key_bindings
from .lexer import IRedisLexer
from .processors import PasswordProcessor, UpdateBottomProcessor, UserInputCommand
from .sentry import run_diagnose, setup_sentry
from .style import THEMES, get_style
from .utils import (
    ESCAPE_FLUSH_TIMEOUT,
    convert_formatted_text_to_bytes,
    exit,
    parse_url,
    timer,
)

logger = logging.getLogger(__name__)


class SkipAuthFileHistory(FileHistory):
    """Exactly like FileHistory, but won't save `AUTH` command into history
    file."""

    def append_string(self, string: str) -> None:
        if string.lstrip().upper().startswith("AUTH"):
            return
        super().append_string(string)


def setup_log():
    if config.log_location:
        logging.basicConfig(
            filename=os.path.expanduser(config.log_location),
            filemode="a",
            format="%(levelname)5s %(message)s",
            level="DEBUG",
        )
    else:
        logging.disable(logging.CRITICAL)
    logger.info("------ iRedis ------")


def greetings():
    lines = [f"iredis  {__version__} (Python {platform.python_version()})"]
    if not config.no_info:
        if config.no_version_reason:
            reason = f"({config.no_version_reason})"
        else:
            reason = ""
        lines.append(f"redis-server  {config.version or 'Unknown'} {reason}")
    lines.append("Home:   https://github.com/amzyang/iredis")
    lines.append("Issues: https://github.com/amzyang/iredis/issues")
    display = "\n".join(lines)
    if config.raw:
        display = display.encode()
    write_result(display)


def print_help_msg(command):
    with click.Context(command) as ctx:
        click.echo(command.get_help(ctx))


def is_too_tall(text, max_height):
    if isinstance(text, FormattedText):
        text = convert_formatted_text_to_bytes(text)
    lines = len(text.split(b"\n"))
    return lines > max_height


def write_result(text, max_height=None):
    """
    When config.raw set to True, write text(must be bytes in that case)
    directly to stdout, same if text is bytes.

    :param text: is_raw: bytes or str, not raw: FormattedText
    :is_raw: bool
    """
    logger.info(f"Print result {type(text)}: {text}"[:200])

    # this function only handle bytes or FormattedText
    # if it's str, convert to bytes
    if isinstance(text, str):
        if config.decode:
            text = text.encode(config.decode)
        else:
            text = text.encode()

    # using pager if too tall
    if max_height and config.enable_pager and is_too_tall(text, max_height):
        if isinstance(text, FormattedText):
            text = convert_formatted_text_to_bytes(text)
            os.environ["LESS"] = "-SRX"
        # click.echo_via_pager only accepts str
        if config.decode:
            text = text.decode(config.decode)
        else:
            text = text.decode()
        # TODO current pager doesn't support colors
        click.echo_via_pager(text)
        return

    if isinstance(text, bytes):
        sys.stdout.buffer.write(text)
        sys.stdout.write("\n")
    else:
        print_formatted_text(text, end="", style=get_style(config.theme))
        print_formatted_text()


class Rainbow:
    color = [
        "#cc2244",
        "#bb4444",
        "#996644",
        "#cc8844",
        "#ccaa44",
        "#bbaa44",
        "#99aa44",
        "#778844",
        "#55aa44",
        "#33aa44",
        "#11aa44",
        "#11aa66",
        "#11aa88",
        "#11aaaa",
        "#11aacc",
        "#11aaee",
    ]

    def __init__(self):
        self.current = -1
        self.forward = 1

    def __iter__(self):
        return self

    def __next__(self):
        self.current += self.forward
        if 0 <= self.current < len(self.color):
            # not to the end
            return self.color[self.current]
        else:
            self.forward = -self.forward
            self.current += 2 * self.forward
            return self.color[self.current]


def prompt_message(client):
    text = str(client)
    if config.rainbow:
        return list(zip(Rainbow(), text))
    return text


def repl(client, session, start_time):
    command_holder = UserInputCommand()
    timer(f"First REPL command enter, time cost: {time.time() - start_time}")

    while True:
        logger.info("↓↓↓↓" * 10)
        logger.info("REPL waiting for command...")

        try:
            command = session.prompt(
                prompt_message(client),
                bottom_toolbar=(
                    BottomToolbar(command_holder).render if config.bottom_bar else None
                ),
                input_processors=[
                    UpdateBottomProcessor(command_holder, session),
                    PasswordProcessor(),
                ],
                rprompt=lambda: "<transaction>" if config.transaction else None,
                key_bindings=key_bindings,
                enable_suspend=True,
            )

        except KeyboardInterrupt:
            logger.warning("KeyboardInterrupt!")
            continue
        except EOFError:
            exit()
        command = command.strip()
        logger.info(f"[Command] {command}")

        # blank input
        if not command:
            continue

        try:
            answers = client.send_command(command, session.completer)
            for answer in answers:
                write_result(
                    answer,
                    # -1 is because 127.0.0.1:6379> takes one line
                    session.output.get_size().rows - session.reserve_space_for_menu - 1,
                )
        # Error with previous command or exception
        except Exception as e:
            logger.exception(e)
            # TODO red error color
            print("(error)", str(e))


RAW_HELP = """
Use raw formatting for replies (default when STDOUT is not a tty). \
However, you can use --no-raw to force formatted output even \
when STDOUT is not a tty.
"""
DECODE_HELP = """
decode response, default is No decode, which will output all bytes literals. \
Accepts any Python codec name or alias (e.g. utf-8, gbk, latin-1).
"""
RAINBOW = "Display colorful prompt."
VI_HELP = """Use vi keybindings to edit the input, like `set -o vi` in bash."""
DSN_HELP = """
Use DSN configured into the [alias_dsn] section of iredisrc file. \
(Can set with env `IREDIS_DSN`)
"""
URL_HELP = """
Use Redis URL to indicate connection(Can set with env `IREDIS_URL`), Example:
    redis://[[username]:[password]]@localhost:6379/0
    rediss://[[username]:[password]]@localhost:6379/0
    unix://[[username]:[password]]@/path/to/socket.sock?db=0
"""
SHELL = """Allow to run shell commands, default to True."""
THEME_HELP = """
Color theme. "default" only uses your terminal's ANSI colors, so iredis \
looks consistent with your terminal color scheme; "classic" is the original \
iredis color scheme with hardcoded colors. The "catppuccin-*" themes use the \
official Catppuccin palette (https://catppuccin.com): latte is the light \
flavor; frappe, macchiato and mocha are progressively darker.
"""
PAGER_HELP = """Using pager when output is too tall for your window, default to True."""
VERIFY_SSL_HELP = """Set the TLS certificate verification strategy"""

COMMON_DECODE_ENCODINGS = [
    "ascii",
    "big5",
    "cp1252",
    "euc-jp",
    "euc-kr",
    "gb18030",
    "gbk",
    "latin-1",
    "shift-jis",
    "utf-8",
    "utf-16",
]


def validate_decode(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return value
    try:
        codecs.lookup(value)
    except LookupError:
        raise click.BadParameter(f"unknown encoding: {value}")
    return value


def complete_decode(ctx, param, incomplete):
    return [e for e in COMMON_DECODE_ENCODINGS if e.startswith(incomplete.lower())]


def validate_url(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return value
    try:
        parse_url(value)
    except ValueError as e:
        raise click.BadParameter(str(e))
    return value


def validate_natmap(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return value
    natmap = {}
    try:
        for entry in value.split(","):
            remote_host, remote_port, local_host, local_port = entry.strip().split(":")
            natmap[f"{remote_host}:{remote_port}"] = (local_host, int(local_port))
    except ValueError:
        raise click.BadParameter(
            "natmap must be in format "
            "remoteHost:remotePort:localHost:localPort (comma-separated "
            f"for multiple nodes), got: {value}"
        )
    return natmap


def complete_dsn(ctx, param, incomplete):
    # completion callbacks must never raise or print
    try:
        iredisrc = ctx.params.get("iredisrc") or "~/.iredisrc"
        aliases = {}
        for f in [system_config_file, iredisrc, pwd_config_file]:
            parsed = read_config_file(f)
            if parsed:
                aliases.update(parsed.get("alias_dsn") or {})
        return sorted(a for a in aliases if a.startswith(incomplete))
    except Exception:
        return []


# command line entry here...
@click.command()
@click.pass_context
@click.option("-h", help="Server hostname (default: 127.0.0.1).", default="127.0.0.1")
@click.option("-p", help="Server port (default: 6379).", default="6379")
@click.option(
    "-s",
    "--socket",
    default=None,
    type=click.Path(),
    help="Server socket (overrides hostname and port).",
)
@click.option(
    "-n",
    type=int,
    help="Database number.(overwrites dsn/url's db number)",
    default=None,
)
@click.option(
    "-u",
    "--username",
    help="User name used to auth, will be ignore for redis version < 6.",
)
@click.option("-a", "--password", help="Password to use when connecting to the server.")
@click.option(
    "--url", default=None, envvar="IREDIS_URL", callback=validate_url, help=URL_HELP
)
@click.option(
    "-d",
    "--dsn",
    default=None,
    envvar="IREDIS_DSN",
    shell_complete=complete_dsn,
    help=DSN_HELP,
)
@click.option(
    "--newbie/--no-newbie",
    default=None,
    is_flag=True,
    help="Show command hints and useful helps.",
)
@click.option(
    "--iredisrc",
    default="~/.iredisrc",
    envvar="IREDIS_CONFIG",
    type=click.Path(),
    help=(
        "Config file for iredis, default is ~/.iredisrc. "
        "You can also set config path via environment variable `IREDIS_CONFIG`."
    ),
)
@click.option(
    "--decode",
    default=None,
    callback=validate_decode,
    shell_complete=complete_decode,
    help=DECODE_HELP,
)
@click.option("--client_name", help="Assign a name to the current connection.")
@click.option("--raw/--no-raw", default=None, is_flag=True, help=RAW_HELP)
@click.option("--rainbow/--no-rainbow", default=None, is_flag=True, help=RAINBOW)
@click.option("--vi/--no-vi", default=None, is_flag=True, help=VI_HELP)
@click.option(
    "--theme", default=None, type=click.Choice(sorted(THEMES)), help=THEME_HELP
)
@click.option("--shell/--no-shell", default=None, is_flag=True, help=SHELL)
@click.option("--pager/--no-pager", default=None, is_flag=True, help=PAGER_HELP)
@click.option(
    "--greetings/--no-greetings",
    default=None,
    is_flag=True,
    help="Enable or disable greeting messages",
)
@click.option(
    "--verify-ssl",
    default=None,
    type=click.Choice(["none", "optional", "required"]),
    help=VERIFY_SSL_HELP,
)
@click.option(
    "--prompt",
    default=None,
    help=(
        "Prompt format (supported interpolations: {client_name}, {db}, {host}, {path},"
        " {port}, {username}, {client_addr}, {client_id})."
    ),
)
@click.option(
    "--natmap",
    default=None,
    callback=validate_natmap,
    metavar="REMOTE_HOST:REMOTE_PORT:LOCAL_HOST:LOCAL_PORT[,...]",
    help=(
        "NAT map for Redis cluster behind SSH tunnels. "
        "Format: remoteHost:remotePort:localHost:localPort "
        "(comma-separated for multiple nodes)."
    ),
)
@click.version_option()
@click.argument("cmd", nargs=-1)
def gather_args(
    ctx,
    h,
    p,
    n,
    username,
    password,
    client_name,
    newbie,
    iredisrc,
    decode,
    raw,
    rainbow,
    vi,
    theme,
    cmd,
    dsn,
    url,
    socket,
    shell,
    pager,
    greetings,
    verify_ssl,
    prompt,
    natmap,
):
    """
    IRedis: Interactive Redis

    When no command is given, IRedis starts in interactive mode.

    \b
    Examples:
      - iredis
      - iredis -d dsn
      - iredis -h 127.0.0.1 -p 6379
      - iredis -h 127.0.0.1 -p 6379 -a <password>
      - iredis --url redis://localhost:7890/3

    Type "help" in interactive mode for information on available commands
    and settings.
    """
    load_config_files(iredisrc)
    setup_log()
    logger.info(
        f"[commandline args] host={h}, port={p}, db={n}, user={username},"
        f" newbie={newbie}, iredisrc={iredisrc}, decode={decode}, raw={raw}, cmd={cmd},"
        f" rainbow={rainbow}."
    )
    # raw config
    if raw is not None:
        config.raw = raw
    if not sys.stdout.isatty():
        config.raw = True

    if newbie is not None:
        config.newbie_mode = newbie

    if decode is not None:
        config.decode = decode
    if rainbow is not None:
        config.rainbow = rainbow
    if vi is not None:
        config.vi_mode = vi
    if theme is not None:
        config.theme = theme
    if shell is not None:
        config.shell = shell
    if pager is not None:
        config.enable_pager = pager
    if verify_ssl is not None:
        config.verify_ssl = verify_ssl
    if greetings is not None:
        config.greetings = greetings

    if natmap:
        config.natmap = natmap

    return ctx


@prompt_register("edit-and-execute-command")
def edit_and_execute(event):
    """Different from the prompt-toolkit default, we want to have a choice not
    to execute a query after editing, hence validate_and_handle=False."""
    buff = event.current_buffer
    # this will prevent running command immediately when exit editor.
    buff.open_in_editor(validate_and_handle=False)


def resolve_dsn(dsn):
    try:
        dsn_uri = (config.alias_dsn or {})[dsn]
    except KeyError:
        click.secho(
            "Could not find the specified DSN in the config file. "
            'Please check the "[alias_dsn]" section in your '
            "iredisrc.",
            err=True,
            fg="red",
        )
        sys.exit(1)
    return dsn_uri


def create_client(params):
    """
    Create a Client.
    :param params: commandline params.
    """
    host = params["h"]
    port = params["p"]
    db = params["n"]
    username = params["username"]
    password = params["password"]
    client_name = params["client_name"]
    prompt = params["prompt"]
    # config.verify_ssl already merges iredisrc and the command line flag
    verify_ssl = params["verify_ssl"] or config.verify_ssl

    dsn_from_url = None
    dsn = params["dsn"]
    try:
        if dsn:
            dsn_from_url = parse_url(resolve_dsn(dsn))
        if params["url"]:
            dsn_from_url = parse_url(params["url"])
    except ValueError as e:
        click.secho(str(e), err=True, fg="red")
        sys.exit(1)
    if dsn_from_url:
        # db from command line options should be high priority,
        # an explicit `-n 0` overrides the db in dsn/url as well
        db = db if db is not None else dsn_from_url.db
        verify_ssl = verify_ssl or dsn_from_url.verify_ssl
        return Client(
            host=dsn_from_url.host,
            port=dsn_from_url.port,
            db=db,
            password=dsn_from_url.password,
            path=dsn_from_url.path,
            scheme=dsn_from_url.scheme,
            username=dsn_from_url.username,
            client_name=client_name,
            prompt=prompt,
            verify_ssl=verify_ssl,
        )
    if db is None:
        db = 0
    if params["socket"]:
        return Client(
            scheme="unix",
            path=params["socket"],
            db=db,
            username=username,
            password=password,
            client_name=client_name,
            prompt=prompt,
        )
    return Client(
        host=host,
        port=port,
        db=db,
        username=username,
        password=password,
        client_name=client_name,
        prompt=prompt,
        verify_ssl=verify_ssl,
    )


def create_prompt_session():
    session = PromptSession(
        history=SkipAuthFileHistory(
            Path(os.path.expanduser(config.history_location))  # ty: ignore[no-matching-overload]
        ),
        style=get_style(config.theme),
        auto_suggest=AutoSuggestFromHistory(),
        complete_while_typing=True,
        lexer=IRedisLexer(),
        completer=IRedisCompleter(
            hint=config.newbie_mode, completion_casing=config.completion_casing
        ),
        enable_open_in_editor=True,
        tempfile_suffix=".redis",
        vi_mode=config.vi_mode,  # ty: ignore[invalid-argument-type]
        cursor=ModalCursorShapeConfig() if config.vi_mode else None,
    )
    session.app.ttimeoutlen = ESCAPE_FLUSH_TIMEOUT
    return session


def main():
    enter_main_time = time.time()  # just for logs

    # invoke in non-standalone mode to gather args
    ctx = None
    try:
        ctx = gather_args.main(standalone_mode=False)
    except click.exceptions.NoSuchOption as nosuchoption:
        nosuchoption.show()
    except click.exceptions.BadOptionUsage as badoption:
        if badoption.option_name == "-h":
            # -h without host, is short command for --help
            # like redis-cli
            print_help_msg(gather_args)
        return
    except click.exceptions.UsageError as e:
        e.show()
    if not ctx:  # called help
        return

    # hidden diagnostic subcommand: `iredis sentry` (exact lowercase, no
    # extra args) verifies telemetry end to end without touching redis;
    # any other casing still goes to the server as a regular command
    if ctx.params["cmd"] == ("sentry",):
        sys.exit(run_diagnose(config.sentry_dsn, enabled=config.sentry))

    setup_sentry(config.sentry_dsn, enabled=config.sentry)

    # redis client
    client = create_client(ctx.params)

    if not sys.stdin.isatty():
        for line in sys.stdin.readlines():
            logger.debug(f"[Command stdin] {line}")
            for answer in client.send_command(line, None):
                write_result(answer)
        if client.command_failed:
            sys.exit(1)
        return

    # no interactive mode, directly run a command
    if ctx.params["cmd"]:
        answers = client.send_command(" ".join(ctx.params["cmd"]), None)
        for answer in answers:
            write_result(answer)
        logger.warning("[OVER] command executed, exit...")
        if client.command_failed:
            sys.exit(1)
        return

    session = create_prompt_session()

    # print hello message
    if config.greetings:
        if not config.no_info:
            # bounded wait so the greeting can show the server version:
            # normal servers finish the probe in milliseconds, a slow
            # server only delays the greeting by 1 second at most
            client.wait_for_version_probe(timeout=1)
        greetings()
    repl(client, session, enter_main_time)
