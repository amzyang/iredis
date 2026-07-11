"""
Interactive dual-pane key browser for the ``PATTERN BROWSE`` command.

Runs a temporary full-screen prompt_toolkit Application on the terminal's
alternate screen: the left pane lists keys matching a pattern group
(scanned incrementally with SCAN, like Medis' key list), the right pane
shows the selected key's detail (reusing PEEK). When the browser exits,
the alternate screen is dropped and the REPL, along with its scrollback,
is restored untouched.

Key bindings:
    Up/Down/PageUp/PageDown  move the selection
    Space                    scan more keys (continue the SCAN cursor)
    Tab                      show/hide the detail pane
    Enter                    exit and PEEK the selected key in the REPL
    d d                      delete the selected key (press twice to confirm)
    q / Esc / Ctrl-C         exit
"""

import logging

from prompt_toolkit.application import Application, get_app
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import (
    ConditionalContainer,
    Dimension,
    FormattedTextControl,
    HSplit,
    Layout,
    VSplit,
    Window,
)

from .config import config
from .style import get_style
from .utils import ensure_str

logger = logging.getLogger(__name__)

# rows used by the title bar and the footer around the key list
CHROME_HEIGHT = 2


class PatternBrowser:
    def __init__(self, client, group, pattern):
        self.client = client
        self.group = group
        self.pattern = pattern
        # (key, type) pairs, both str
        self.keys = []
        # str keys ever scanned, to feed the REPL's key completer on exit
        self.seen_keys = []
        self.cursor = 0
        self.scan_finished = False
        self.index = 0
        self.show_detail = True
        self.confirm_delete = False
        self._detail_cache = {}
        self.load_more()

    def load_more(self):
        if self.scan_finished:
            return
        keys, self.cursor = self.client.scan_keys(self.pattern, self.cursor)
        self.scan_finished = self.cursor == 0
        types = self.client._fetch_types(keys)
        str_keys = ensure_str(keys)
        self.keys.extend(zip(str_keys, types))
        self.seen_keys.extend(str_keys)

    @property
    def selected_key(self):
        if not self.keys:
            return None
        return self.keys[self.index][0]

    def delete_selected(self):
        key = self.selected_key
        if key is None:
            return
        self.client.execute("DEL", key)
        del self.keys[self.index]
        self._detail_cache.pop(key, None)
        if self.index >= len(self.keys) and self.index > 0:
            self.index -= 1

    def move(self, delta):
        if self.keys:
            self.index = max(0, min(len(self.keys) - 1, self.index + delta))

    def _page_size(self):
        return max(1, get_app().output.get_size().rows - CHROME_HEIGHT - 1)

    # === render callables, called by prompt_toolkit on every repaint ===

    def title_bar(self):
        state = (
            "scan finished"
            if self.scan_finished
            else f"cursor {self.cursor}, Space to scan more"
        )
        return [
            ("class:bottom-toolbar", " browse "),
            ("class:bottom-toolbar.group", self.group),
            ("class:bottom-toolbar", f" ({self.pattern})  {len(self.keys)} keys"),
            ("class:bottom-toolbar", f"  [{state}] "),
        ]

    def footer_bar(self):
        if self.confirm_delete and self.selected_key is not None:
            return [
                (
                    "class:error",
                    f" delete {self.selected_key}? press `d` again to"
                    " confirm, any other key to cancel ",
                )
            ]
        return [
            (
                "class:bottom-toolbar",
                " ↑/↓ move  Space scan more  Tab detail  Enter peek & exit"
                "  d delete  q quit ",
            )
        ]

    def key_rows(self):
        if not self.keys:
            return [("class:type", " (no key matched)")]
        rows = []
        page = self._page_size()
        start = max(0, min(self.index - page // 2, len(self.keys) - page))
        for i, (key, key_type) in list(enumerate(self.keys))[start : start + page]:
            selected = i == self.index
            row_style = "class:selected" if selected else ""
            rows.append((row_style if selected else "class:string", f" {key_type:8}"))
            rows.append((row_style if selected else "class:key", key))
            rows.append(("", "\n"))
        return rows

    def detail_rows(self):
        key = self.selected_key
        if key is None:
            return []
        if key not in self._detail_cache:
            try:
                detail = []
                for answer in self.client.do_peek(key):
                    if isinstance(answer, str):
                        detail.append(("", answer))
                    else:
                        detail.extend(answer)
                self._detail_cache[key] = detail
            except Exception as e:
                logger.exception(e)
                self._detail_cache[key] = [("class:error", f"(error) {str(e)}")]
        return self._detail_cache[key]

    # === application ===

    def run(self):
        """Show the browser, return the picked key (or None)."""
        kb = KeyBindings()

        def reset_confirm(handler):
            def wrapped(event):
                self.confirm_delete = False
                handler(event)

            return wrapped

        kb.add("q")(reset_confirm(lambda event: event.app.exit(result=None)))
        kb.add("escape", eager=True)(
            reset_confirm(lambda event: event.app.exit(result=None))
        )
        kb.add("c-c")(reset_confirm(lambda event: event.app.exit(result=None)))
        kb.add("enter")(
            reset_confirm(lambda event: event.app.exit(result=self.selected_key))
        )
        kb.add("up")(reset_confirm(lambda event: self.move(-1)))
        kb.add("down")(reset_confirm(lambda event: self.move(1)))
        kb.add("pageup")(reset_confirm(lambda event: self.move(-self._page_size())))
        kb.add("pagedown")(reset_confirm(lambda event: self.move(self._page_size())))
        kb.add("space")(reset_confirm(lambda event: self.load_more()))
        kb.add("tab")(
            reset_confirm(
                lambda event: setattr(self, "show_detail", not self.show_detail)
            )
        )

        @kb.add("d")
        def _(event):
            if self.confirm_delete:
                self.confirm_delete = False
                self.delete_selected()
            elif self.selected_key is not None:
                self.confirm_delete = True

        body = VSplit(
            [
                Window(
                    FormattedTextControl(lambda: FormattedText(self.key_rows())),
                    width=Dimension(weight=1),
                ),
                Window(width=1, char="│", style="class:bottom-toolbar"),
                ConditionalContainer(
                    Window(
                        FormattedTextControl(lambda: FormattedText(self.detail_rows())),
                        width=Dimension(weight=1),
                        wrap_lines=True,
                    ),
                    Condition(lambda: self.show_detail),
                ),
            ]
        )
        root = HSplit(
            [
                Window(
                    FormattedTextControl(lambda: FormattedText(self.title_bar())),
                    height=1,
                    style="class:bottom-toolbar",
                ),
                body,
                Window(
                    FormattedTextControl(lambda: FormattedText(self.footer_bar())),
                    height=1,
                    style="class:bottom-toolbar",
                ),
            ]
        )
        application = Application(
            layout=Layout(root),
            key_bindings=kb,
            full_screen=True,
            style=get_style(config.theme),
        )
        return application.run()
