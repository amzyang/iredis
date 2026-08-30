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

All redis I/O runs on a single worker thread so the panel shows up
instantly and never blocks: SCAN batches stream in, key types are fetched
lazily for the visible rows only (a slow proxy pays per command), and the
detail pane peeks the selected key in the background. The worker is the
sole connection user while the browser is open -- the REPL is parked in
``run()`` -- and is drained before the connection is handed back.

Key bindings:
    /                        edit the pattern: a menu offers recently used
                             patterns, Enter rescans, Esc cancels
    Tab                      cycle the focus: key tree → detail pane → repl
    Up/Down/PageUp/PageDown  move the selection, or scroll the detail pane
                             when it has the focus (vim j/k work too)
    Left/Right (h/l)         fold a group / unfold it (Left on a key jumps
                             to its parent group)
    Space                    scan more keys (continue the SCAN cursor)
    Enter                    unfold a group, or exit and PEEK the key
    y / Y                    copy the selected key's value / name
    d d                      delete the selected key (press twice to confirm)
    q / Esc / Ctrl-C         exit

Below the detail pane a 5-row repl runs redis commands on the same
connection: Enter runs the input line, Up/Down recall its history,
PageUp/PageDown scroll the output above it. Commands that take over the
connection (MONITOR, SUBSCRIBE) or park the worker waiting for data
(BLPOP, WAIT, XREAD BLOCK) are rejected, and dangerous commands are too
while the warning config is on -- there is no room to confirm here.

The mouse works too: click a key to select it (a group folds/unfolds),
the wheel scrolls any pane, a click on the 🔍 box edits the pattern, and
dragging the ``│`` separator resizes the two panes.
"""

import logging
from concurrent.futures import ThreadPoolExecutor

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
    Container,
    Dimension,
    Float,
    FloatContainer,
    FormattedTextControl,
    HSplit,
    Layout,
    ScrollablePane,
    VSplit,
    Window,
)
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.mouse_events import MouseButton, MouseEventType
from prompt_toolkit.utils import get_cwidth

from .commands import split_command_args, split_unknown_args
from .config import config
from .exceptions import AmbiguousCommand, InvalidArguments
from .style import get_style
from .utils import ESCAPE_FLUSH_TIMEOUT, copy_to_clipboard, ensure_str
from .warning import is_dangerous

logger = logging.getLogger(__name__)

# rows used by the pattern bar and the footer around the key list
CHROME_HEIGHT = 2
# initial width of the keys panel, like Medis' sidebar; dragging the pane
# separator resizes it, but neither pane ever collapses below its minimum
TREE_WIDTH = 40
TREE_MIN_WIDTH = 20
DETAIL_MIN_WIDTH = 20
# namespace separator for grouping keys into a tree, like Medis
SEPARATOR = ":"
# buckets smaller than this render as plain keys instead of a group
GROUP_MIN_KEYS = 2
# columns of the keys panel's type column: a 4-char abbreviation + a space
TYPE_WIDTH = 5

# short type names for the type column; full words waste the narrow panel
TYPE_ABBREV = {
    "string": "str",
    "list": "list",
    "set": "set",
    "hash": "hash",
    "zset": "zset",
    "stream": "strm",
}

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

# rows of the repl output pane; with its input line the repl is 5 rows
REPL_OUTPUT_HEIGHT = 4
# commands that switch the shared connection into a streaming mode the
# browser's single worker can't host
REPL_UNSUPPORTED = ("MONITOR", "SUBSCRIBE", "PSUBSCRIBE", "SSUBSCRIBE")
# commands that park the worker waiting for data: every queued scan, peek
# and repl job stalls behind them, and closing the browser joins the
# worker, so a timeout of 0 would hang the whole process
REPL_BLOCKING = (
    "BLPOP",
    "BRPOP",
    "BLMOVE",
    "BRPOPLPUSH",
    "BLMPOP",
    "BZPOPMIN",
    "BZPOPMAX",
    "BZMPOP",
    "WAIT",
    "WAITAOF",
)


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


def _fit(text, width):
    """Truncate text to the display width, appending ``…`` when clipped.

    Widths follow the terminal cells (CJK characters take two), so the
    keys panel clips loudly instead of prompt_toolkit's silent cut."""
    if get_cwidth(text) <= width:
        return text
    used = 0
    out = []
    for char in text:
        used += get_cwidth(char)
        if used > width - 1:
            break
        out.append(char)
    return "".join(out) + "…"


def _pad(text, width):
    """Pad by display width so the highlight covers the whole panel."""
    return text + " " * max(0, width - get_cwidth(text))


def _clickable(fragments, handler):
    """Attach one mouse handler to every fragment of a pane's text."""
    return FormattedText([(style, text, handler) for style, text in fragments])


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


def normalize_pattern(text):
    """Empty input browses everything; like a searchbox, a pattern without
    a trailing ``*`` gets one appended, so ``task:`` means ``task:*``."""
    pattern = text.strip() or "*"
    if not pattern.endswith("*"):
        pattern += "*"
    return pattern


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


class SeparatorControl(FormattedTextControl):
    """The pane separator column: it renders no text, so the default
    content-cell lookup would drop its mouse events; the whole control
    is one handler instead."""

    def __init__(self, handler):
        super().__init__("")
        self._handler = handler

    def mouse_handler(self, mouse_event):
        return self._handler(mouse_event)


class SeparatorDragZone(Container):
    """Wraps the browser body to track an active separator drag.

    The handlers each pane registers per cell receive positions
    translated to *content* coordinates -- clipped to each line's text,
    so they lie over blank cells. This range handler, laid over the
    whole body after the panes rendered, receives absolute screen
    coordinates instead: the pointer column is the wanted tree width.
    Outside a drag nothing is registered and the panes behave as usual.
    """

    def __init__(self, content, browser):
        self.content = content
        self.browser = browser

    def reset(self):
        self.content.reset()

    def preferred_width(self, max_available_width):
        return self.content.preferred_width(max_available_width)

    def preferred_height(self, width, max_available_height):
        return self.content.preferred_height(width, max_available_height)

    def get_children(self):
        return [self.content]

    def write_to_screen(
        self, screen, mouse_handlers, write_position, parent_style, erase_bg, z_index
    ):
        self.content.write_to_screen(
            screen, mouse_handlers, write_position, parent_style, erase_bg, z_index
        )
        if not self.browser.separator_dragging:
            return
        mouse_handlers.set_mouse_handler_for_range(
            x_min=write_position.xpos,
            x_max=write_position.xpos + write_position.width,
            y_min=write_position.ypos,
            y_max=write_position.ypos + write_position.height,
            handler=self.browser.body_drag_handler(write_position.xpos),
        )


class KeyBrowser:
    def __init__(self, client, pattern, history=None, executor=None):
        self.client = client
        self.history = history or InMemoryHistory()
        pattern = normalize_pattern(pattern)
        # record the REPL-given pattern in the recents, dupes of the last
        # run and the noise `*` excluded
        last = next(iter(self.history.load_history_strings()), None)
        if pattern not in ("*", last):
            self.history.append_string(pattern)
        self.pattern = pattern
        # str keys in scan order; types live apart so they can arrive later
        self.keys = []
        # key -> type, filled lazily for the visible rows only
        self.types = {}
        # str keys ever scanned, to feed the REPL's key completer on exit
        self.seen_keys = []
        self.cursor = 0
        self.scan_finished = False
        self.scanning = False
        self.index = 0
        self.confirm_delete = False
        # one-shot footer message (e.g. "value copied"), cleared on any key
        self.notice = None
        self.expanded = set()
        # panes resize by dragging the separator; the tree starts Medis-sized
        self.tree_width = TREE_WIDTH
        self.separator_dragging = False
        # repl under the detail pane: its own recall history, last output
        self.repl_history = InMemoryHistory()
        self.repl_output = [("class:type", "repl: type a redis command, Enter runs it")]
        self._detail_cache = {}
        self._type_pending = set()
        self._detail_pending = set()
        self._generation = 0
        self._closed = False
        self._app = None
        # the worker owns all redis I/O while the browser is open (the
        # REPL is parked in run(), so the shared connection is free);
        # injectable so tests run jobs inline
        self._executor = executor or ThreadPoolExecutor(max_workers=1)
        self._build_layout()
        self.apply_pattern(pattern)

    # === background worker: the only place redis commands run ===

    def _submit(self, fn, *args):
        """Queue a job on the worker; exceptions become a footer notice
        instead of dying silently in the thread."""

        def job():
            try:
                fn(*args)
            except Exception as e:
                logger.exception(e)
                self.notice = str(e)
                self._invalidate()

        self._executor.submit(job)

    def _stale(self, generation):
        """A job's results are dead once the pattern changed or the
        browser closed."""
        return self._closed or generation != self._generation

    def _invalidate(self):
        if self._app is not None:
            self._app.invalidate()

    def _scan_job(self, generation):
        if self._stale(generation):
            return

        def stop():
            return self._stale(generation)

        keys, cursor = self.client.scan_keys(self.pattern, self.cursor, stop_check=stop)
        if stop():
            return
        str_keys = ensure_str(keys)
        first_batch = not self.keys
        # rebind, don't mutate: the UI thread reads consistent snapshots
        self.keys = self.keys + str_keys
        self.seen_keys.extend(str_keys)
        self.cursor = cursor
        self.scan_finished = cursor == 0
        if first_batch:
            self.expanded = set(single_chain_paths([(k, None) for k in str_keys]))
            self.index = self._first_key_row()
        self.scanning = False
        self._invalidate()

    def _types_job(self, generation, keys):
        try:
            if self._stale(generation):
                return
            types = self.client._fetch_types(keys)
            if self._stale(generation):
                return
            self.types = {**self.types, **dict(zip(keys, types))}
        finally:
            self._type_pending.difference_update(keys)
        self._invalidate()

    def _request_types(self, keys):
        """Queue a pipelined TYPE fetch for the viewport keys not yet
        known nor in flight; the pending set stops repaint loops."""
        missing = [
            key
            for key in keys
            if key not in self.types and key not in self._type_pending
        ]
        if not missing:
            return
        self._type_pending.update(missing)
        self._submit(self._types_job, self._generation, missing)

    def load_more(self):
        if self.scanning or self.scan_finished:
            return
        self.scanning = True
        self._submit(self._scan_job, self._generation)

    def apply_pattern(self, pattern):
        """Rescan the keyspace with pattern, resetting every view state.

        The scan lands in batches from the worker; a stale generation
        makes any in-flight job drop its results."""
        self._generation += 1
        self.pattern = pattern
        self.keys = []
        self.types = {}
        self.cursor = 0
        self.scan_finished = False
        self.scanning = True
        self.confirm_delete = False
        self.expanded = set()
        self.index = 0
        self._detail_cache.clear()
        self._type_pending.clear()
        self._detail_pending.clear()
        self.detail_pane.vertical_scroll = 0
        self._submit(self._scan_job, self._generation)

    def submit_pattern(self):
        """Apply the pattern box's text: record it and rescan."""
        pattern = normalize_pattern(self.pattern_buffer.text)
        if pattern not in ("*", self.pattern):
            self.history.append_string(pattern)
        self.pattern_buffer.document = Document(pattern, len(pattern))
        self.apply_pattern(pattern)

    def cancel_input(self):
        """Drop the pattern box's edit, back to the active pattern."""
        self.pattern_buffer.document = Document(self.pattern, len(self.pattern))

    def rows(self):
        return tree_rows(
            [(key, self.types.get(key)) for key in self.keys], self.expanded
        )

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
        self._submit(self._delete_job, self._generation, key)

    def _delete_job(self, generation, key):
        if self._stale(generation):
            return
        self.client.execute("DEL", key)
        self.keys = [k for k in self.keys if k != key]
        self.types.pop(key, None)
        self._detail_cache.pop(key, None)
        self.move(0)
        self._invalidate()

    def move(self, delta):
        rows = self.rows()
        if rows:
            self.index = max(0, min(len(rows) - 1, self.index + delta))
        self.detail_pane.vertical_scroll = 0

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
                self.detail_pane.vertical_scroll = 0
                return

    def tree_row_mouse_handler(self, row_index):
        """Row-scoped mouse handler: a click selects the row (and folds or
        unfolds a group), the wheel moves the selection."""

        def handler(mouse_event):
            if mouse_event.event_type == MouseEventType.SCROLL_DOWN:
                self.move(3)
            elif mouse_event.event_type == MouseEventType.SCROLL_UP:
                self.move(-3)
            elif mouse_event.event_type == MouseEventType.MOUSE_UP:
                self.confirm_delete = False
                self.notice = None
                get_app().layout.focus(self.tree_window)
                self.index = row_index
                self.detail_pane.vertical_scroll = 0
                self.toggle_selected()
            else:
                return NotImplemented

        return handler

    def _pane_mouse_handler(self, mouse_event, pane, focus_target):
        """The wheel scrolls the pane, a click focuses the target."""
        if mouse_event.event_type == MouseEventType.SCROLL_DOWN:
            # the pane clips the bottom overshoot on the next repaint
            pane.vertical_scroll += 3
        elif mouse_event.event_type == MouseEventType.SCROLL_UP:
            pane.vertical_scroll = max(0, pane.vertical_scroll - 3)
        elif mouse_event.event_type == MouseEventType.MOUSE_UP:
            get_app().layout.focus(focus_target)
        else:
            return NotImplemented

    def detail_mouse_handler(self, mouse_event):
        """The wheel scrolls the detail pane, a click focuses it."""
        return self._pane_mouse_handler(
            mouse_event, self.detail_pane, self.detail_window
        )

    # === separator drag: resize the panes with the mouse ===

    def separator_mouse_handler(self, mouse_event):
        """A left press on the ``│`` separator starts the resize drag;
        the SeparatorDragZone laid over the body tracks it from there."""
        if (
            mouse_event.event_type == MouseEventType.MOUSE_DOWN
            and mouse_event.button == MouseButton.LEFT
        ):
            self.separator_dragging = True
            return None
        return NotImplemented

    def body_drag_handler(self, xpos):
        """One handler covering the whole body while a drag is active,
        called with absolute screen coordinates (xpos is the body's
        left edge, screen column 0 in practice)."""

        def handler(mouse_event):
            if not self.separator_dragging:
                return NotImplemented
            if (
                mouse_event.event_type == MouseEventType.MOUSE_MOVE
                and mouse_event.button == MouseButton.LEFT
            ):
                self._set_tree_width(mouse_event.position.x - xpos)
                return None
            # released, or moving with the button already up: drag over
            self.separator_dragging = False
            return None

        return handler

    def _set_tree_width(self, width):
        columns = get_app().output.get_size().columns
        self.tree_width = max(TREE_MIN_WIDTH, min(width, columns - DETAIL_MIN_WIDTH))

    # === repl: run any redis command without leaving the browser ===

    def _show_repl_output(self, command, fragments):
        """The echoed command line heads whatever the repl shows for it."""
        self.repl_output = [("class:key", f"> {command}"), ("", "\n"), *fragments]

    def run_repl_command(self, buffer):
        """Accept handler of the repl input: echo the command, then run
        it on the worker; False clears the input (it went to the history)."""
        command = buffer.text.strip()
        if not command:
            return False
        self._show_repl_output(command, [("class:type", "running…")])
        self.repl_pane.vertical_scroll = 0
        self._submit(self._repl_job, command)
        return False

    def _repl_job(self, command):
        # not generation-gated: the command's side effects happened on
        # the server either way, so the output always lands
        if self._closed:
            return
        self._show_repl_output(command, self._repl_fragments(command))
        # a write may have changed the selected key: peek it fresh
        self._detail_cache.clear()
        self._invalidate()

    def _repl_fragments(self, command):
        try:
            command_name, args = split_command_args(command)
        except InvalidArguments, AmbiguousCommand:
            command_name, args = split_unknown_args(command)
        upper_name = command_name.upper()
        if upper_name in REPL_UNSUPPORTED:
            return [
                (
                    "class:error",
                    f"{upper_name} takes over the connection, run it in the REPL",
                )
            ]
        if upper_name in REPL_BLOCKING or (
            upper_name in ("XREAD", "XREADGROUP")
            and any(arg.upper() == "BLOCK" for arg in args)
        ):
            return [
                (
                    "class:error",
                    f"{upper_name} blocks the browser's worker, run it in the REPL",
                )
            ]
        dangerous, reason = is_dangerous(upper_name)
        if config.warning and dangerous:
            return [("class:error", f"(danger) {reason}, run it in the REPL")]
        try:
            resp = self.client.execute(command_name, *args)
        except Exception as e:
            logger.exception(e)
            return [("class:error", f"(error) {e}")]
        rendered = self.client.render_response(resp, command_name)
        if isinstance(rendered, (bytes, str)):
            return [("", _clip_str(rendered))]
        return rendered

    def repl_output_mouse_handler(self, mouse_event):
        """The wheel scrolls the repl output, a click focuses the input."""
        return self._pane_mouse_handler(
            mouse_event, self.repl_pane, self.repl_input_window
        )

    def copy_selected_key(self):
        key = self.selected_key
        if key is None:
            self.notice = "select a key first"
            return
        copy_to_clipboard(key, get_app().output)
        self.notice = f"key copied: {key}"

    def copy_selected_value(self):
        key = self.selected_key
        if key is None:
            self.notice = "select a key first"
            return
        self.notice = "copying…"
        self._submit(self._copy_value_job, self._generation, key)

    def _copy_value_job(self, generation, key):
        if self._stale(generation):
            return
        key_type = self.types.get(key) or self.client._fetch_types([key])[0]
        text = value_text(self.client, key, key_type)
        if text is None:
            # no plain representation (e.g. stream): copy the detail text
            detail = self._detail_cache.get(key) or self._fetch_detail(key)
            text = "".join(fragment for _, fragment in detail)
        self._finish_copy(text, f"value copied ({len(text)} chars)")

    def _finish_copy(self, text, notice):
        """Clipboard and notice land on the UI thread: copy_to_clipboard
        may write OSC 52 to the terminal, racing the renderer otherwise."""

        def finish():
            app = self._app
            copy_to_clipboard(text, app.output if app else None)
            self.notice = notice
            self._invalidate()

        loop = self._app.loop if self._app else None
        if loop is None:
            finish()
        else:
            loop.call_soon_threadsafe(finish)

    def _page_size(self):
        return max(1, get_app().output.get_size().rows - CHROME_HEIGHT - 1)

    def _count_text(self, count):
        bound = "" if self.scan_finished else ">= "
        unit = "key" if count == 1 else "keys"
        return f"{bound}{count} {unit}"

    # === render callables, called by prompt_toolkit on every repaint ===

    def stats_text(self):
        if self.scanning:
            state = "scanning…"
        elif self.scan_finished:
            state = "scan finished"
        else:
            state = f"cursor {self.cursor}, Space to scan more"
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
        if layout.has_focus(self.repl_buffer):
            return [
                ("class:bottom-toolbar.on", " [repl] "),
                (
                    "class:bottom-toolbar",
                    "Enter run  ↑/↓ history  PgUp/PgDn scroll  Tab/Esc keys ",
                ),
            ]
        if layout.has_focus(self.detail_window):
            return [
                ("class:bottom-toolbar.on", " [detail] "),
                (
                    "class:bottom-toolbar",
                    "j/k scroll  y/Y copy value/key  / pattern  Tab repl  q quit ",
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
            state = " scanning…" if self.scanning else " (no key matched)"
            return [("class:type", state)]
        out = []
        page = self._page_size()
        start = max(0, min(self.index - page // 2, len(rows) - page))
        window = list(enumerate(rows))[start : start + page]
        # lazy types: only the rows on screen are worth a TYPE round-trip
        self._request_types([row[1] for _, row in window if row[0] == "key"])
        for i, row in window:
            selected = i == self.index
            indent = "  " * row[3]
            click = self.tree_row_mouse_handler(i)
            if row[0] == "group":
                _, path, count, _, is_open = row
                count_text = f"  {self._count_text(count)}"
                # the count stays visible, the name gets whatever is left
                name = _fit(
                    path.rsplit(SEPARATOR, 1)[-1],
                    max(4, self.tree_width - 3 - len(indent) - get_cwidth(count_text)),
                )
                arrow = "▾" if is_open else "▸"
                if selected:
                    text = f" {indent}{arrow} {name}{count_text}"
                    out.append(("class:selected", _pad(text, self.tree_width), click))
                else:
                    out.append(("class:group", f" {indent}{arrow} {name}", click))
                    out.append(("class:type", count_text, click))
            else:
                key = row[1]
                # read the dict, not the row: the fetch may just have landed
                key_type = self.types.get(key)
                abbrev = TYPE_ABBREV.get(key_type, key_type[:4]) if key_type else "…"
                style = f"class:type-{key_type}" if key_type else "class:type"
                name = _fit(key, self.tree_width - 1 - len(indent) - TYPE_WIDTH)
                if selected:
                    text = f" {indent}{abbrev:{TYPE_WIDTH}}{name}"
                    out.append(("class:selected", _pad(text, self.tree_width), click))
                else:
                    out.append((style, f" {indent}{abbrev:{TYPE_WIDTH}}", click))
                    out.append(("class:key", name, click))
            out.append(("", "\n"))
        return out

    def _fetch_detail(self, key):
        detail = []
        for answer in self.client.do_peek(key):
            if isinstance(answer, str):
                detail.append(("", answer))
            else:
                detail.extend(answer)
        return detail

    def _peek_job(self, generation, key):
        try:
            # latest wins: a key scrolled past isn't worth an expensive
            # PEEK; landing on it again resubmits
            if self._stale(generation) or self.selected_key != key:
                return
            try:
                detail = self._fetch_detail(key)
            except Exception as e:
                logger.exception(e)
                detail = [("class:error", f"(error) {str(e)}")]
            self._detail_cache[key] = detail
        finally:
            self._detail_pending.discard(key)
        self._invalidate()

    def _key_detail(self, key):
        if key not in self._detail_cache and key not in self._detail_pending:
            self._detail_pending.add(key)
            self._submit(self._peek_job, self._generation, key)
        return self._detail_cache.get(key, [("class:type", "loading…")])

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
        # the full name heads the pane: the tree may have clipped it
        return [("class:key", key), ("", "\n"), *self._key_detail(key)]

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
            style="class:pattern underline",
        )
        self.tree_window = Window(
            FormattedTextControl(
                lambda: FormattedText(self.key_rows()),
                focusable=True,
                key_bindings=self.tree_key_bindings(),
            ),
            width=lambda: self.tree_width,
        )
        self.detail_window = Window(
            FormattedTextControl(
                lambda: _clickable(self.detail_rows(), self.detail_mouse_handler),
                focusable=True,
                key_bindings=self.detail_key_bindings(),
            ),
            wrap_lines=True,
        )
        # a plain Window resets its scroll to chase the (invisible) cursor
        # on every repaint; the pane keeps manual scrolling and shows a
        # scrollbar
        self.detail_pane = ScrollablePane(
            self.detail_window,
            keep_cursor_visible=False,
            keep_focused_window_visible=False,
            display_arrows=False,
            width=Dimension(weight=1),
        )
        self.repl_buffer = Buffer(
            multiline=False,
            history=self.repl_history,
            accept_handler=self.run_repl_command,
        )
        self.repl_output_window = Window(
            FormattedTextControl(
                lambda: _clickable(self.repl_output, self.repl_output_mouse_handler),
            ),
            wrap_lines=True,
        )
        self.repl_pane = ScrollablePane(
            self.repl_output_window,
            keep_cursor_visible=False,
            keep_focused_window_visible=False,
            display_arrows=False,
            height=REPL_OUTPUT_HEIGHT,
        )
        self.repl_input_window = Window(
            BufferControl(
                self.repl_buffer,
                focus_on_click=True,
                key_bindings=self.repl_key_bindings(),
            ),
            height=1,
        )

    def _root_container(self):
        # the underlined run (padding + input) reads as one input box,
        # opened by the magnifier icon like a searchbox
        pattern_bar = VSplit(
            [
                Window(
                    FormattedTextControl(" 🔍 "),
                    dont_extend_width=True,
                    style="class:bottom-toolbar",
                ),
                Window(width=1, char=" ", style="class:pattern underline"),
                self.input_window,
                Window(width=1, char=" ", style="class:pattern underline"),
                Window(
                    FormattedTextControl(lambda: FormattedText(self.stats_text())),
                    dont_extend_width=True,
                    style="class:bottom-toolbar",
                ),
            ]
        )
        detail_column = HSplit(
            [
                self.detail_pane,
                Window(height=1, char="─", style="class:bottom-toolbar"),
                self.repl_pane,
                VSplit(
                    [
                        Window(
                            FormattedTextControl([("class:pattern", "> ")]),
                            dont_extend_width=True,
                        ),
                        self.repl_input_window,
                    ]
                ),
            ]
        )
        body = SeparatorDragZone(
            VSplit(
                [
                    self.tree_window,
                    Window(
                        SeparatorControl(self.separator_mouse_handler),
                        width=1,
                        char="│",
                        style="class:bottom-toolbar",
                    ),
                    detail_column,
                ]
            ),
            self,
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
                pane = self.detail_pane
                pane.vertical_scroll = max(
                    0, pane.vertical_scroll + delta_of_event(event)
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

    def repl_key_bindings(self):
        """Bindings of the repl input; control-level, like the pattern
        box, so no single-letter binding can swallow typed text."""
        kb = KeyBindings()

        @kb.add("escape", eager=True)
        def _(event):
            event.app.layout.focus(self.tree_window)

        @kb.add("tab")
        def _(event):
            event.app.layout.focus(self.tree_window)

        # the input keeps the focus: page keys scroll the output above it
        @kb.add("pagedown")
        def _(event):
            self.repl_pane.vertical_scroll += REPL_OUTPUT_HEIGHT

        @kb.add("pageup")
        def _(event):
            self.repl_pane.vertical_scroll = max(
                0, self.repl_pane.vertical_scroll - REPL_OUTPUT_HEIGHT
            )

        return kb

    def app_key_bindings(self):
        kb = KeyBindings()
        in_input = has_focus(self.pattern_buffer) | has_focus(self.repl_buffer)

        def do_exit(event):
            event.app.exit(result=None)

        kb.add("q", filter=~in_input)(do_exit)
        kb.add("escape", filter=~in_input, eager=True)(do_exit)
        kb.add("c-c")(do_exit)

        @kb.add("tab", filter=~in_input)
        def _(event):
            layout = event.app.layout
            if layout.has_focus(self.detail_window):
                layout.focus(self.repl_input_window)
            else:
                layout.focus(self.detail_window)

        return kb

    def run(self):
        """Show the browser, return the picked key (or None)."""
        application = Application(
            layout=Layout(self._root_container(), focused_element=self.tree_window),
            key_bindings=self.app_key_bindings(),
            full_screen=True,
            mouse_support=True,
            style=get_style(config.theme),
        )
        application.ttimeoutlen = ESCAPE_FLUSH_TIMEOUT
        self._app = application
        try:
            return application.run()
        finally:
            # hand the connection back quiet: the REPL peeks the picked
            # key on it right after
            self._closed = True
            self._executor.shutdown(wait=True, cancel_futures=True)
            self._app = None
