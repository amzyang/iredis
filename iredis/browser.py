"""
Interactive dual-pane key browser for the ``PATTERN BROWSE`` command.

Runs a temporary full-screen prompt_toolkit Application on the terminal's
alternate screen: the left pane lists keys matching a pattern (scanned
incrementally with SCAN, one batch at a time), grouped into a collapsible
namespace tree by ``:`` segments like Medis' sidebar; the right pane shows
the selected key's detail (reusing PEEK). Without a group argument the
whole keyspace (``*``) is browsed. When the browser exits, the alternate
screen is dropped and the REPL, along with its scrollback, is restored
untouched.

Key bindings:
    Up/Down/PageUp/PageDown  move the selection (vim j/k work too)
    Left/Right (h/l)         fold a group / unfold it (Left on a key jumps
                             to its parent group)
    Space                    scan more keys (continue the SCAN cursor)
    Tab                      show/hide the detail pane
    Enter                    unfold a group, or exit and PEEK the key
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
from .utils import ESCAPE_FLUSH_TIMEOUT, ensure_str

logger = logging.getLogger(__name__)

# rows used by the title bar and the footer around the key list
CHROME_HEIGHT = 2
# namespace separator for grouping keys into a tree, like Medis
SEPARATOR = ":"
# buckets smaller than this render as plain keys instead of a group
GROUP_MIN_KEYS = 2


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


class PatternBrowser:
    def __init__(self, client, group, pattern):
        self.client = client
        self.group = group
        self.pattern = pattern
        # (key, type) pairs, both str, in scan order
        self.keys = []
        # str keys ever scanned, to feed the REPL's key completer on exit
        self.seen_keys = []
        self.cursor = 0
        self.scan_finished = False
        self.index = 0
        self.show_detail = True
        self.confirm_delete = False
        self.expanded = set()
        self._detail_cache = {}
        self.load_more()
        self.expanded = set(single_chain_paths(self.keys))
        self.index = self._first_key_row()

    def load_more(self):
        if self.scan_finished:
            return
        keys, self.cursor = self.client.scan_keys(self.pattern, self.cursor)
        self.scan_finished = self.cursor == 0
        types = self.client._fetch_types(keys)
        str_keys = ensure_str(keys)
        self.keys.extend(zip(str_keys, types))
        self.seen_keys.extend(str_keys)

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
                return

    def _page_size(self):
        return max(1, get_app().output.get_size().rows - CHROME_HEIGHT - 1)

    def _count_text(self, count):
        bound = "" if self.scan_finished else ">= "
        unit = "key" if count == 1 else "keys"
        return f"{bound}{count} {unit}"

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
                " ↑/↓/j/k move  ←/→/h/l fold/unfold  Space scan more"
                "  Tab detail  Enter unfold/peek & exit  d delete  q quit ",
            )
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

    # === application ===

    def key_bindings(self):
        kb = KeyBindings()

        def reset_confirm(handler):
            def wrapped(event):
                self.confirm_delete = False
                handler(event)

            return wrapped

        def open_or_pick(event):
            if not self.toggle_selected():
                event.app.exit(result=self.selected_key)

        kb.add("q")(reset_confirm(lambda event: event.app.exit(result=None)))
        kb.add("escape", eager=True)(
            reset_confirm(lambda event: event.app.exit(result=None))
        )
        kb.add("c-c")(reset_confirm(lambda event: event.app.exit(result=None)))
        kb.add("enter")(reset_confirm(open_or_pick))
        for key in ("up", "k"):
            kb.add(key)(reset_confirm(lambda event: self.move(-1)))
        for key in ("down", "j"):
            kb.add(key)(reset_confirm(lambda event: self.move(1)))
        kb.add("pageup")(reset_confirm(lambda event: self.move(-self._page_size())))
        kb.add("pagedown")(reset_confirm(lambda event: self.move(self._page_size())))
        for key in ("left", "h"):
            kb.add(key)(reset_confirm(lambda event: self.collapse_or_parent()))
        for key in ("right", "l"):
            kb.add(key)(reset_confirm(lambda event: self.expand_selected()))
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

        return kb

    def run(self):
        """Show the browser, return the picked key (or None)."""
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
            key_bindings=self.key_bindings(),
            full_screen=True,
            style=get_style(config.theme),
        )
        application.ttimeoutlen = ESCAPE_FLUSH_TIMEOUT
        return application.run()
