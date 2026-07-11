"""
Tests for the PATTERN BROWSE full-screen key browser.

The browser repaints the alternate screen with cell diffs, so raw pexpect
stream matching can't see full strings; instead the pty output is replayed
through pyte (a terminal emulator) and assertions run on the rendered
screen content.
"""

import os
import re
import subprocess
import tempfile
import time

import pexpect
import pyte
import pytest

TIMEOUT = 10
IREDISRC_CONTENT = (
    "[main]\n"
    "log_location =\n"
    "warning = False\n"
    "enable_pager = False\n"
    "[patterns]\n"
    "users = user:*\n"
)


class ScreenedCli:
    """iredis subprocess whose pty output is rendered by pyte."""

    def __init__(self, iredisrc):
        env = os.environ.copy()
        env["PROMPT_TOOLKIT_NO_CPR"] = "1"
        env["TERM"] = "xterm-256color"
        self.child = pexpect.spawn(
            f"iredis -n 15 --iredisrc {iredisrc}",
            timeout=TIMEOUT,
            env=env,
            dimensions=(24, 100),
            encoding="utf-8",
        )
        self.screen = pyte.Screen(100, 24)
        self.stream = pyte.Stream(self.screen)

    def pump(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            try:
                self.stream.feed(self.child.read_nonblocking(100000, timeout=0.2))
            except (pexpect.TIMEOUT, pexpect.EOF):
                pass

    def display(self):
        return "\n".join(line.rstrip() for line in self.screen.display)

    def wait_for(self, pattern, seconds=TIMEOUT):
        end = time.time() + seconds
        while time.time() < end:
            self.pump(0.3)
            matched = re.search(pattern, self.display())
            if matched:
                return matched
        raise AssertionError(f"{pattern!r} never showed on screen:\n{self.display()}")

    def wait_gone(self, pattern, seconds=TIMEOUT):
        end = time.time() + seconds
        while time.time() < end:
            self.pump(0.3)
            if not re.search(pattern, self.display()):
                return
        raise AssertionError(f"{pattern!r} still on screen:\n{self.display()}")


@pytest.fixture
def browse_cli(clean_redis):
    pipeline = clean_redis.pipeline()
    for i in range(500):
        pipeline.set(f"user:{i}", i)
    pipeline.execute()

    iredisrc = tempfile.mktemp(suffix=".iredisrc")
    with open(iredisrc, "w") as config_file:
        config_file.write(IREDISRC_CONTENT)

    cli = ScreenedCli(iredisrc)
    cli.wait_for(r"127\.0\.0\.1:6379\[15\]>")
    yield cli
    cli.child.close(force=True)
    os.remove(iredisrc)


def test_pattern_browse_dual_pane_flow(browse_cli):
    cli = browse_cli
    cli.child.sendline("PATTERN BROWSE users")

    # dual pane is up: title bar, pane divider, detail pane (peek output)
    cli.wait_for(r"browse users \(user:\*\)")
    cli.wait_for(r"│")
    cli.wait_for(r"value:")
    keys_shown = int(cli.wait_for(r"(\d+) keys").group(1))
    assert keys_shown < 500  # first batch only, cursor to be continued
    cli.wait_for(r"Space to scan more")

    # moving the selection updates the detail pane
    value_before = cli.wait_for(r'value: "(\d+)"').group(1)
    cli.child.send("\x1b[B\x1b[B")  # down down
    cli.wait_gone(rf'value: "{value_before}"')

    # Space continues the scan, one batch (~100 keys) at a time
    for _ in range(10):
        cli.child.send(" ")
        cli.pump(0.5)
        if re.search(r"scan finished", cli.display()):
            break
    cli.wait_for(r"500 keys")
    cli.wait_for(r"scan finished")

    # Tab hides / shows the detail pane
    cli.child.send("\t")
    cli.wait_gone(r"value:")
    cli.child.send("\t")
    cli.wait_for(r"value:")

    # delete needs a second `d` to confirm, other keys cancel
    cli.child.send("d")
    cli.wait_for(r"press `d` again to confirm")
    cli.child.send("\x1b[B")
    cli.wait_gone(r"press `d` again")
    cli.child.send("dd")
    cli.wait_for(r"499 keys")

    # Enter exits the browser and peeks the selected key in the REPL
    cli.child.send("\r")
    cli.wait_for(r"127\.0\.0\.1:6379\[15\]>")
    cli.wait_for(r"key: string")

    # the REPL survives the browser session
    cli.child.sendline("dbsize")
    cli.wait_for(r"\(integer\) 499")


def test_pattern_browse_refuses_non_tty():
    iredisrc = tempfile.mktemp(suffix=".iredisrc")
    with open(iredisrc, "w") as config_file:
        config_file.write(IREDISRC_CONTENT)
    result = subprocess.run(
        ["iredis", "-n", "15", "--iredisrc", iredisrc],
        input=b"PATTERN BROWSE users\n",
        capture_output=True,
        timeout=TIMEOUT,
    )
    os.remove(iredisrc)
    assert b"needs an interactive terminal" in result.stdout


def test_pattern_browse_unknown_group(browse_cli):
    cli = browse_cli
    cli.child.sendline("PATTERN BROWSE nosuch")
    cli.wait_for(r"doesn't exist")
