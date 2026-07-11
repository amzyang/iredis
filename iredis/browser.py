"""
Interactive dual-pane key browser for the ``BROWSE`` command.

Runs a temporary full-screen prompt_toolkit Application on the terminal's
alternate screen: the top bar holds an editable pattern box, the left pane
lists keys matching the pattern (scanned incrementally with SCAN, one
batch at a time), grouped into a collapsible namespace tree by ``:``
segments like Medis' sidebar; the right pane shows the selected key's
detail (reusing PEEK). Without a pattern argument the whole keyspace
(``*``) is browsed. When the browser exits, the alternate screen is
dropped and the REPL, along with its scrollback, is restored untouched.

Key bindings:
    /                        edit the pattern: a menu offers recently used
                             patterns, Enter rescans, Esc cancels
    Tab                      switch focus between the key tree and the
                             detail pane
    Up/Down/PageUp/PageDown  move the selection, or scroll the detail pane
                             when it has the focus (vim j/k work too)
    Left/Right (h/l)         fold a group / unfold it (Left on a key jumps
                             to its parent group)
    Space                    scan more keys (continue the SCAN cursor)
    Enter                    unfold a group, or exit and PEEK the key
    y / Y                    copy the selected key's value / name
    d d                      delete the selected key (press twice to confirm)
    q / Esc / Ctrl-C         exit
"""

import logging

from prompt_toolkit.application import Application, get_app
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.filters import completion_is_selected, has_focus
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import (
    BufferControl,
    Dimension,
    Float,
    FloatContainer,
    FormattedTextControl,
    HSplit,
    Layout,
    VSplit,
    Window,
)
from prompt_toolkit.layout.menus import CompletionsMenu

from .config import config
from .style import get_style
from .utils import ESCAPE_FLUSH_TIMEOUT, copy_to_clipboard, ensure_str

logger = logging.getLogger(__name__)

# rows used by the pattern bar and the footer around the key list
CHROME_HEIGHT = 2
# namespace separator for grouping keys into a tree, like Medis
SEPARATOR = ":"
# buckets smaller than this render as plain keys instead of a group
GROUP_MIN_KEYS = 2

# per-type command to fetch a key's raw value for the clipboard
VALUE_COMMANDS = {
    "string": ("GET",),
    "list": ("LRANGE", 0, -1),
    "set": ("SMEMBERS",),
    "hash": ("HGETALL",),
    "zset": ("ZRANGE", 0, -1, "WITHSCORES"),
}
# types whose response is a flat [a, b, a, b, ...] pair list
PAIRED_TYPES = ("hash", "zset")


def _bucket_level(items, separator):
    """Bucket one tree level of ``(rest, key, type)`` by leading segment.

    Returns (order, buckets, leaves): first-seen order entries, segment ->
    child items, and the keys ending exactly at this level (rest is None).
    """
    order = []
    buckets = {}
    leaves = []
    for rest, key, key_type in items:
        if rest is None:
            order.append(("leaf", len(leaves)))
            leaves.append((key, key_type))
            continue
        seg, sep, tail = rest.partition(separator)
        if seg not in buckets:
            buckets[seg] = []
            order.append(("bucket", seg))
        buckets[seg].append((tail if sep else None, key, key_type))
    return order, buckets, leaves


def tree_rows(keys, expanded, separator=SEPARATOR):
    """Flatten scanned ``(key, type)`` pairs into visible tree rows.

    Keys are grouped by leading ``separator`` segments into a namespace
    tree: a bucket holding at least GROUP_MIN_KEYS keys renders as a
    collapsible ``("group", path, count, depth, is_open)`` row, a
    single-key bucket (and a key without separator) renders as a
    ``("key", key, type, depth)`` row showing the full key.
    """
    rows = []

    def walk(items, path, depth):
        order, buckets, leaves = _bucket_level(items, separator)
        for kind, ref in order:
            if kind == "leaf":
                key, key_type = leaves[ref]
                rows.append(("key", key, key_type, depth))
                continue
            children = buckets[ref]
            if len(children) < GROUP_MIN_KEYS:
                _, key, key_type = children[0]
                rows.append(("key", key, key_type, depth))
                continue
            child_path = f"{path}{separator}{ref}" if path else ref
            is_open = child_path in expanded
            rows.append(("group", child_path, len(children), depth, is_open))
            if is_open:
                walk(children, child_path, depth + 1)

    walk([(key, key, key_type) for key, key_type in keys], "", 0)
    return rows


def single_chain_paths(keys, separator=SEPARATOR):
    """Group paths to auto-expand: descend while a level is one single group.

    A narrow pattern (e.g. ``user:*``) puts every key under one namespace
    chain; unfolding it upfront saves a pointless drill-down.
    """
    paths = []
    items = [(key, key, key_type) for key, key_type in keys]
    path = ""
    while True:
        _, buckets, leaves = _bucket_level(items, separator)
        if leaves or len(buckets) != 1:
            return paths
        seg, children = next(iter(buckets.items()))
        if len(children) < GROUP_MIN_KEYS:
            return paths
        path = f"{path}{separator}{seg}" if path else seg
        paths.append(path)
        items = children


def _clip_str(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def value_text(client, key, key_type):
    """The key's raw value serialized as clipboard-friendly text.

    Collections are one element per line, hash fields and zset scores
    tab-separated. None for types without a plain representation.
    """
    if key_type not in VALUE_COMMANDS:
        return None
    command, *args = VALUE_COMMANDS[key_type]
    resp = client.execute(command, key, *args)
    if key_type == "string":
        return _clip_str(resp) if resp is not None else ""
    items = [_clip_str(item) for item in resp]
    if key_type in PAIRED_TYPES:
        return "\n".join(f"{a}\t{b}" for a, b in zip(items[::2], items[1::2]))
    return "\n".join(items)


class RecentPatternCompleter(Completer):
    """Recently used BROWSE patterns, most recent first, like a searchbox's
    recents menu. Substring-matched against the typed text."""

    def __init__(self, history):
        self.history = history

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        seen = set()
        for pattern in self.history.load_history_strings():
            if pattern in seen:
                continue
            seen.add(pattern)
            if text not in pattern:
                continue
            yield Completion(pattern, start_position=-len(text))


class KeyBrowser:
    def __init__(self, client, pattern, history=None):
        self.client = client
        self.history = history or InMemoryHistory()
        # record the REPL-given pattern in the recents, dupes of the last
        # run and the noise `*` excluded
        last = next(iter(self.history.load_history_strings()), None)
        if pattern not in ("*", last):
            self.history.append_string(pattern)
        self.pattern = pattern
        # (key, type) pairs, both str, in scan order
        self.keys = []
        # str keys ever scanned, to feed the REPL's key completer on exit
        self.seen_keys = []
        self.cursor = 0
        self.scan_finished = False
        self.index = 0
        self.confirm_delete = False
        # one-shot footer message (e.g. "value copied"), cleared on any key
        self.notice = None
        self.expanded = set()
        self._detail_cache = {}
        self._build_layout()
        self.apply_pattern(pattern)

    def load_more(self):
        if self.scan_finished:
            return
        keys, self.cursor = self.client.scan_keys(self.pattern, self.cursor)
        self.scan_finished = self.cursor == 0
        types = self.client._fetch_types(keys)
        str_keys = ensure_str(keys)
        self.keys.extend(zip(str_keys, types))
        self.seen_keys.extend(str_keys)

    def apply_pattern(self, pattern):
        """Rescan the keyspace with pattern, resetting every view state."""
        self.pattern = pattern
        self.keys = []
        self.cursor = 0
        self.scan_finished = False
        self.confirm_delete = False
        self._detail_cache.clear()
        self.detail_window.vertical_scroll = 0
        self.load_more()
        self.expanded = set(single_chain_paths(self.keys))
        self.index = self._first_key_row()

    def submit_pattern(self):
        """Apply the pattern box's text: record it and rescan."""
        pattern = self.pattern_buffer.text.strip() or "*"
        if pattern not in ("*", self.pattern):
            self.history.append_string(pattern)
        self.pattern_buffer.document = Document(pattern, len(pattern))
        self.apply_pattern(pattern)

    def cancel_input(self):
        """Drop the pattern box's edit, back to the active pattern."""
        self.pattern_buffer.document = Document(self.pattern, len(self.pattern))

    def rows(self):
        return tree_rows(self.keys, self.expanded)

    def _first_key_row(self):
        for i, row in enumerate(self.rows()):
            if row[0] == "key":
                return i
        return 0

    @property
    def selected_row(self):
        rows = self.rows()
        if not rows:
            return None
        self.index = min(self.index, len(rows) - 1)
        return rows[self.index]

    @property
    def selected_key(self):
        row = self.selected_row
        if row is None or row[0] != "key":
            return None
        return row[1]

    def delete_selected(self):
        key = self.selected_key
        if key is None:
            return
        self.client.execute("DEL", key)
        self.keys = [item for item in self.keys if item[0] != key]
        self._detail_cache.pop(key, None)
        self.move(0)

    def move(self, delta):
        rows = self.rows()
        if rows:
            self.index = max(0, min(len(rows) - 1, self.index + delta))
        self.detail_window.vertical_scroll = 0

    def toggle_selected(self):
        """Fold/unfold the selected group; False when not on a group row."""
        row = self.selected_row
        if row is None or row[0] != "group":
            return False
        self.expanded.symmetric_difference_update({row[1]})
        return True

    def expand_selected(self):
        row = self.selected_row
        if row is not None and row[0] == "group":
            self.expanded.add(row[1])

    def collapse_or_parent(self):
        """Fold an open group, else jump to the parent group row."""
        row = self.selected_row
        if row is None:
            return
        if row[0] == "group" and row[1] in self.expanded:
            self.expanded.discard(row[1])
            return
        rows = self.rows()
        for i in range(self.index - 1, -1, -1):
            if rows[i][0] == "group" and rows[i][3] < row[3]:
                self.index = i
                self.detail_window.vertical_scroll = 0
                return

    def copy_selected_key(self):
        key = self.selected_key
        if key is None:
            self.notice = "select a key first"
            return
        copy_to_clipboard(key, get_app().output)
        self.notice = f"key copied: {key}"

    def copy_selected_value(self):
        row = self.selected_row
        if row is None or row[0] != "key":
            self.notice = "select a key first"
            return
        _, key, key_type, _ = row
        text = value_text(self.client, key, key_type)
        if text is None:
            # no plain representation (e.g. stream): copy the detail text
            text = "".join(fragment for _, fragment in self.detail_rows())
        copy_to_clipboard(text, get_app().output)
        self.notice = f"value copied ({len(text)} chars)"

    def _page_size(self):
        return max(1, get_app().output.get_size().rows - CHROME_HEIGHT - 1)

    def _count_text(self, count):
        bound = "" if self.scan_finished else ">= "
        unit = "key" if count == 1 else "keys"
        return f"{bound}{count} {unit}"

    # === render callables, called by prompt_toolkit on every repaint ===

    def stats_text(self):
        state = (
            "scan finished"
            if self.scan_finished
            else f"cursor {self.cursor}, Space to scan more"
        )
        return [
            ("class:bottom-toolbar", f" {len(self.keys)} keys  [{state}] "),
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
        if self.notice:
            return [("class:bottom-toolbar.on", f" {self.notice} ")]
        layout = get_app().layout
        if layout.has_focus(self.pattern_buffer):
            return [
                ("class:bottom-toolbar.on", " [pattern] "),
                (
                    "class:bottom-toolbar",
                    "Enter rescan  Esc cancel  ↑/↓ recent patterns ",
                ),
            ]
        if layout.has_focus(self.detail_window):
            return [
                ("class:bottom-toolbar.on", " [detail] "),
                (
                    "class:bottom-toolbar",
                    "j/k scroll  y/Y copy value/key  / pattern  Tab keys  q quit ",
                ),
            ]
        return [
            ("class:bottom-toolbar.on", " [keys] "),
            (
                "class:bottom-toolbar",
                "j/k move  h/l fold  Space scan  Enter peek  d delete"
                "  y/Y copy value/key  / pattern  Tab detail  q quit ",
            ),
        ]

    def key_rows(self):
        rows = self.rows()
        if not rows:
            return [("class:type", " (no key matched)")]
        out = []
        page = self._page_size()
        start = max(0, min(self.index - page // 2, len(rows) - page))
        for i, row in list(enumerate(rows))[start : start + page]:
            selected = i == self.index
            indent = "  " * row[3]
            if row[0] == "group":
                _, path, count, _, is_open = row
                name = path.rsplit(SEPARATOR, 1)[-1]
                arrow = "▾" if is_open else "▸"
                if selected:
                    out.append(
                        (
                            "class:selected",
                            f" {indent}{arrow} {name}  {self._count_text(count)}",
                        )
                    )
                else:
                    out.append(("class:group", f" {indent}{arrow} {name}"))
                    out.append(("class:type", f"  {self._count_text(count)}"))
            else:
                _, key, key_type, _ = row
                if selected:
                    out.append(("class:selected", f" {indent}{key_type:8}{key}"))
                else:
                    out.append((f"class:type-{key_type}", f" {indent}{key_type:8}"))
                    out.append(("class:key", key))
            out.append(("", "\n"))
        return out

    def detail_rows(self):
        row = self.selected_row
        if row is None:
            return []
        if row[0] == "group":
            _, path, count, _, _ = row
            return [
                ("class:group", path),
                ("class:type", f"{SEPARATOR}*  {self._count_text(count)}"),
            ]
        key = row[1]
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

    # === layout & key bindings ===

    def _build_layout(self):
        self.pattern_buffer = Buffer(
            multiline=False,
            history=self.history,
            completer=RecentPatternCompleter(self.history),
            complete_while_typing=True,
            document=Document(self.pattern, len(self.pattern)),
        )
        self.input_window = Window(
            BufferControl(self.pattern_buffer, key_bindings=self.input_key_bindings()),
            height=1,
            style="class:pattern",
        )
        self.tree_window = Window(
            FormattedTextControl(
                lambda: FormattedText(self.key_rows()),
                focusable=True,
                key_bindings=self.tree_key_bindings(),
            ),
            width=Dimension(weight=1),
        )
        self.detail_window = Window(
            FormattedTextControl(
                lambda: FormattedText(self.detail_rows()),
                focusable=True,
                key_bindings=self.detail_key_bindings(),
            ),
            width=Dimension(weight=1),
            wrap_lines=True,
        )

    def _root_container(self):
        pattern_bar = VSplit(
            [
                Window(
                    FormattedTextControl(" pattern: "),
                    dont_extend_width=True,
                    style="class:bottom-toolbar",
                ),
                self.input_window,
                Window(
                    FormattedTextControl(lambda: FormattedText(self.stats_text())),
                    dont_extend_width=True,
                    style="class:bottom-toolbar",
                ),
            ]
        )
        body = VSplit(
            [
                self.tree_window,
                Window(width=1, char="│", style="class:bottom-toolbar"),
                self.detail_window,
            ]
        )
        footer = Window(
            FormattedTextControl(lambda: FormattedText(self.footer_bar())),
            height=1,
            style="class:bottom-toolbar",
        )
        # the float pops the recent-pattern menu right under the pattern box
        return FloatContainer(
            content=HSplit([pattern_bar, body, footer]),
            floats=[
                Float(
                    xcursor=True,
                    ycursor=True,
                    content=CompletionsMenu(max_height=12, scroll_offset=1),
                )
            ],
        )

    def _reset_transients(self, handler):
        def wrapped(event):
            self.confirm_delete = False
            self.notice = None
            handler(event)

        return wrapped

    def _focus_input(self, event):
        event.app.layout.focus(self.input_window)
        self.pattern_buffer.cursor_position = len(self.pattern_buffer.text)
        self.pattern_buffer.start_completion(select_first=False)

    def tree_key_bindings(self):
        kb = KeyBindings()
        reset = self._reset_transients

        def open_or_pick(event):
            if not self.toggle_selected():
                event.app.exit(result=self.selected_key)

        kb.add("enter")(reset(open_or_pick))
        for key in ("up", "k"):
            kb.add(key)(reset(lambda event: self.move(-1)))
        for key in ("down", "j"):
            kb.add(key)(reset(lambda event: self.move(1)))
        kb.add("pageup")(reset(lambda event: self.move(-self._page_size())))
        kb.add("pagedown")(reset(lambda event: self.move(self._page_size())))
        for key in ("left", "h"):
            kb.add(key)(reset(lambda event: self.collapse_or_parent()))
        for key in ("right", "l"):
            kb.add(key)(reset(lambda event: self.expand_selected()))
        kb.add("space")(reset(lambda event: self.load_more()))
        kb.add("y")(reset(lambda event: self.copy_selected_value()))
        kb.add("Y")(reset(lambda event: self.copy_selected_key()))
        kb.add("/")(reset(self._focus_input))

        @kb.add("d")
        def _(event):
            self.notice = None
            if self.confirm_delete:
                self.confirm_delete = False
                self.delete_selected()
            elif self.selected_key is not None:
                self.confirm_delete = True

        return kb

    def detail_key_bindings(self):
        kb = KeyBindings()
        reset = self._reset_transients

        def scroll(delta_of_event):
            def handler(event):
                window = self.detail_window
                window.vertical_scroll = max(
                    0, window.vertical_scroll + delta_of_event(event)
                )

            return handler

        for key in ("down", "j"):
            kb.add(key)(reset(scroll(lambda event: 1)))
        for key in ("up", "k"):
            kb.add(key)(reset(scroll(lambda event: -1)))
        kb.add("pagedown")(reset(scroll(lambda event: self._page_size())))
        kb.add("pageup")(reset(scroll(lambda event: -self._page_size())))
        kb.add("y")(reset(lambda event: self.copy_selected_value()))
        kb.add("Y")(reset(lambda event: self.copy_selected_key()))
        kb.add("/")(reset(self._focus_input))
        return kb

    def input_key_bindings(self):
        """Bindings of the pattern box; control-level, so the tree's and the
        app's single-letter bindings can never swallow typed text."""
        kb = KeyBindings()

        @kb.add("enter")
        def _(event):
            self.submit_pattern()
            event.app.layout.focus(self.tree_window)

        # registered after the plain enter, so it wins while the recents
        # menu has a highlighted entry: accept it, stay in the box
        @kb.add("enter", filter=completion_is_selected)
        def _(event):
            self.pattern_buffer.complete_state = None

        @kb.add("escape", eager=True)
        def _(event):
            self.cancel_input()
            event.app.layout.focus(self.tree_window)

        @kb.add("tab")
        def _(event):
            event.app.layout.focus(self.tree_window)

        return kb

    def app_key_bindings(self):
        kb = KeyBindings()
        in_input = has_focus(self.pattern_buffer)

        def do_exit(event):
            event.app.exit(result=None)

        kb.add("q", filter=~in_input)(do_exit)
        kb.add("escape", filter=~in_input, eager=True)(do_exit)
        kb.add("c-c")(do_exit)

        @kb.add("tab", filter=~in_input)
        def _(event):
            layout = event.app.layout
            if layout.has_focus(self.detail_window):
                layout.focus(self.tree_window)
            else:
                layout.focus(self.detail_window)

        return kb

    def run(self):
        """Show the browser, return the picked key (or None)."""
        application = Application(
            layout=Layout(self._root_container(), focused_element=self.tree_window),
            key_bindings=self.app_key_bindings(),
            full_screen=True,
            style=get_style(config.theme),
        )
        application.ttimeoutlen = ESCAPE_FLUSH_TIMEOUT
        return application.run()
