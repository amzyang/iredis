from unittest.mock import MagicMock

from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.data_structures import Point
from prompt_toolkit.document import Document
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.mouse_events import MouseButton, MouseEvent, MouseEventType

from iredis.browser import (
    TREE_WIDTH,
    KeyBrowser,
    RecentPatternCompleter,
    normalize_pattern,
    single_chain_paths,
    tree_rows,
    value_text,
)

MEDIS_KEYS = [
    ("task:scheduler:device_load:xiaohongshu", "zset"),
    ("task:scheduler:device_load:douyin", "zset"),
    ("task:scheduler:device_info:2:3010202049028", "hash"),
    ("task:scheduler:device_info:1:3010202056849", "hash"),
    ("task:scheduler:offline_search_daily_count:douyin:20260709", "zset"),
    ("task:scheduler:offline_search_devices:a", "zset"),
    ("task:scheduler:offline_search_devices:b", "zset"),
]


def test_tree_rows_collapsed_root():
    assert tree_rows(MEDIS_KEYS, set()) == [("group", "task", 7, 0, False)]


def test_tree_rows_expanded_levels():
    rows = tree_rows(MEDIS_KEYS, {"task", "task:scheduler"})
    assert ("group", "task", 7, 0, True) in rows
    assert ("group", "task:scheduler", 7, 1, True) in rows
    assert ("group", "task:scheduler:device_load", 2, 2, False) in rows
    assert ("group", "task:scheduler:device_info", 2, 2, False) in rows
    # a single-key bucket renders as the full key, not a nested group
    assert (
        "key",
        "task:scheduler:offline_search_daily_count:douyin:20260709",
        "zset",
        2,
    ) in rows


def test_tree_rows_group_expansion_shows_children():
    keys = [("user:1", "string"), ("user:2", "string")]
    assert tree_rows(keys, set()) == [("group", "user", 2, 0, False)]
    assert tree_rows(keys, {"user"}) == [
        ("group", "user", 2, 0, True),
        ("key", "user:1", "string", 1),
        ("key", "user:2", "string", 1),
    ]


def test_tree_rows_single_key_bucket_and_flat_key_are_leaves():
    rows = tree_rows([("user:1", "string"), ("online", "string")], set())
    assert rows == [
        ("key", "user:1", "string", 0),
        ("key", "online", "string", 0),
    ]


def test_tree_rows_key_equal_to_namespace():
    keys = [("task", "string"), ("task:a", "string"), ("task:b", "string")]
    assert tree_rows(keys, {"task"}) == [
        ("group", "task", 3, 0, True),
        ("key", "task", "string", 1),
        ("key", "task:a", "string", 1),
        ("key", "task:b", "string", 1),
    ]


def test_single_chain_paths_for_group_pattern():
    keys = [(f"user:{i}", "string") for i in range(3)]
    assert single_chain_paths(keys) == ["user"]


def test_single_chain_paths_descends_nested_single_chain():
    assert single_chain_paths(MEDIS_KEYS) == ["task", "task:scheduler"]


def test_single_chain_paths_empty_for_mixed_root():
    keys = [("user:1", "string"), ("queue:1", "list"), ("online", "string")]
    assert single_chain_paths(keys) == []


def make_browser(keys, cursor=0, pattern="user:*", history=None):
    client = MagicMock()
    client.scan_keys.return_value = ([key for key, _ in keys], cursor)
    client._fetch_types.return_value = [key_type for _, key_type in keys]
    return KeyBrowser(client, pattern, history=history)


def test_browser_auto_expands_single_chain_and_selects_first_key():
    browser = make_browser([("user:1", "string"), ("user:2", "string")])
    assert browser.expanded == {"user"}
    assert browser.rows()[browser.index][0] == "key"


def test_browser_toggle_group_folds_and_unfolds():
    browser = make_browser([("user:1", "string"), ("user:2", "string")])
    browser.index = 0  # the "user" group row
    assert browser.toggle_selected() is True
    assert browser.rows() == [("group", "user", 2, 0, False)]
    assert browser.toggle_selected() is True
    assert len(browser.rows()) == 3


def test_browser_toggle_on_key_row_returns_false():
    browser = make_browser([("user:1", "string"), ("user:2", "string")])
    assert browser.rows()[browser.index][0] == "key"
    assert browser.toggle_selected() is False


def test_browser_selected_key_is_none_on_group_row():
    browser = make_browser([("user:1", "string"), ("user:2", "string")])
    browser.index = 0
    assert browser.selected_key is None
    browser.index = 1
    assert browser.selected_key == "user:1"


def test_browser_delete_selected_key():
    browser = make_browser([("user:1", "string"), ("user:2", "string")])
    browser.index = 1
    browser.delete_selected()
    browser.client.execute.assert_called_once_with("DEL", "user:1")
    assert [row for row in browser.rows() if row[0] == "key"] == [
        ("key", "user:2", "string", 0)
    ]


def test_browser_delete_is_noop_on_group_row():
    browser = make_browser([("user:1", "string"), ("user:2", "string")])
    browser.index = 0
    browser.delete_selected()
    browser.client.execute.assert_not_called()


def test_browser_collapse_or_parent_jumps_to_parent_group():
    browser = make_browser([("user:1", "string"), ("user:2", "string")])
    browser.index = 2  # user:2 key row
    browser.collapse_or_parent()
    assert browser.index == 0
    # a second left folds the now-selected open group
    browser.collapse_or_parent()
    assert browser.rows() == [("group", "user", 2, 0, False)]


def test_browser_index_clamps_after_fold():
    browser = make_browser([("user:1", "string"), ("user:2", "string")])
    browser.index = 2
    browser.expanded.clear()
    assert browser.selected_row == ("group", "user", 2, 0, False)


def tree_handlers(browser):
    return {
        binding.keys[0]: binding.handler
        for binding in browser.tree_key_bindings().bindings
    }


def test_browser_binds_vim_hjkl_alongside_arrows():
    browser = make_browser([("user:1", "string"), ("user:2", "string")])
    bound = {
        key for binding in browser.tree_key_bindings().bindings for key in binding.keys
    }
    assert {"h", "j", "k", "l", "up", "down", "left", "right"} <= bound


def test_browser_hjkl_navigation_behaviour():
    browser = make_browser([("user:1", "string"), ("user:2", "string")])
    event = MagicMock()
    handlers = tree_handlers(browser)

    browser.index = 1
    handlers["j"](event)
    assert browser.index == 2
    handlers["k"](event)
    assert browser.index == 1
    handlers["h"](event)  # jump to the parent group row
    assert browser.index == 0
    handlers["h"](event)  # fold the open group
    assert browser.rows() == [("group", "user", 2, 0, False)]
    handlers["l"](event)  # unfold it again
    assert len(browser.rows()) == 3


# === pattern input, history, recents menu ===


def test_normalize_pattern_appends_trailing_star():
    assert normalize_pattern("task:") == "task:*"
    assert normalize_pattern("task:*") == "task:*"
    assert normalize_pattern("   ") == "*"
    assert normalize_pattern("*") == "*"


def test_browser_initial_pattern_gets_trailing_star():
    browser = make_browser(
        [("task:1", "string"), ("task:2", "string")], pattern="task:"
    )
    assert browser.pattern == "task:*"
    browser.client.scan_keys.assert_called_with("task:*", 0)
    assert browser.pattern_buffer.text == "task:*"
    assert list(browser.history.load_history_strings()) == ["task:*"]


def test_browser_submit_pattern_appends_trailing_star():
    browser = make_browser([("user:1", "string")])
    browser.client.scan_keys.return_value = ([], 0)
    browser.client._fetch_types.return_value = []
    browser.pattern_buffer.text = "task:"

    browser.submit_pattern()

    assert browser.pattern == "task:*"
    assert browser.pattern_buffer.text == "task:*"
    assert "task:*" in list(browser.history.load_history_strings())


def test_browser_records_initial_pattern_in_history():
    browser = make_browser([("user:1", "string")])
    assert list(browser.history.load_history_strings()) == ["user:*"]


def test_browser_star_pattern_not_recorded_in_history():
    browser = make_browser([("user:1", "string")], pattern="*")
    assert list(browser.history.load_history_strings()) == []


def test_browser_rerun_with_same_pattern_not_duplicated():
    history = InMemoryHistory()
    history.append_string("user:*")
    browser = make_browser([("user:1", "string")], history=history)
    assert list(browser.history.load_history_strings()) == ["user:*"]


def test_browser_apply_pattern_resets_state():
    browser = make_browser([("user:1", "string"), ("user:2", "string")])
    browser.index = 2
    browser.detail_pane.vertical_scroll = 3
    browser.client.scan_keys.return_value = (["queue:a", "queue:b"], 0)
    browser.client._fetch_types.return_value = ["list", "list"]

    browser.apply_pattern("queue:*")

    assert browser.pattern == "queue:*"
    browser.client.scan_keys.assert_called_with("queue:*", 0)
    assert [key for key, _ in browser.keys] == ["queue:a", "queue:b"]
    assert browser.expanded == {"queue"}
    assert browser.rows()[browser.index][0] == "key"
    assert browser.detail_pane.vertical_scroll == 0
    # keys of every browsed pattern feed the REPL completer on exit
    assert set(browser.seen_keys) == {"user:1", "user:2", "queue:a", "queue:b"}


def test_browser_submit_pattern_applies_and_saves_history():
    browser = make_browser([("user:1", "string"), ("user:2", "string")])
    browser.client.scan_keys.return_value = (["queue:a"], 0)
    browser.client._fetch_types.return_value = ["list"]
    browser.pattern_buffer.text = "queue:*"

    browser.submit_pattern()

    assert browser.pattern == "queue:*"
    assert list(browser.history.load_history_strings()) == ["queue:*", "user:*"]


def test_browser_submit_empty_pattern_falls_back_to_star():
    browser = make_browser([("user:1", "string")])
    browser.client.scan_keys.return_value = ([], 0)
    browser.client._fetch_types.return_value = []
    browser.pattern_buffer.text = "   "

    browser.submit_pattern()

    assert browser.pattern == "*"
    assert browser.pattern_buffer.text == "*"
    # `*` is noise in the recents menu, never recorded
    assert list(browser.history.load_history_strings()) == ["user:*"]


def test_browser_resubmit_current_pattern_rescans_without_history_dup():
    browser = make_browser([("user:1", "string")])
    browser.pattern_buffer.text = "user:*"
    browser.submit_pattern()
    assert browser.pattern == "user:*"
    assert list(browser.history.load_history_strings()) == ["user:*"]


def test_browser_cancel_input_restores_current_pattern():
    browser = make_browser([("user:1", "string")])
    browser.pattern_buffer.text = "half-typed"
    browser.cancel_input()
    assert browser.pattern_buffer.text == "user:*"


def test_recent_pattern_completer_most_recent_first_dedup():
    history = InMemoryHistory()
    for pattern in ["user:*", "queue:*", "user:*"]:
        history.append_string(pattern)
    completer = RecentPatternCompleter(history)
    completions = list(completer.get_completions(Document(""), CompleteEvent()))
    assert [c.text for c in completions] == ["user:*", "queue:*"]


def test_recent_pattern_completer_filters_by_substring():
    history = InMemoryHistory()
    for pattern in ["user:*", "queue:*"]:
        history.append_string(pattern)
    completer = RecentPatternCompleter(history)
    completions = list(completer.get_completions(Document("que"), CompleteEvent()))
    assert [c.text for c in completions] == ["queue:*"]
    assert completions[0].start_position == -3


# === focus switching, detail scrolling ===


def test_tab_moves_focus_from_tree_to_detail_and_back():
    browser = make_browser([("user:1", "string")])
    handlers = {
        binding.keys[0]: binding.handler
        for binding in browser.app_key_bindings().bindings
    }
    event = MagicMock()

    event.app.layout.has_focus = lambda target: False  # tree focused
    handlers["c-i"](event)  # prompt_toolkit normalizes "tab" to "c-i"
    event.app.layout.focus.assert_called_once_with(browser.detail_window)

    event.app.layout.focus.reset_mock()
    event.app.layout.has_focus = lambda target: target is browser.detail_window
    handlers["c-i"](event)
    event.app.layout.focus.assert_called_once_with(browser.tree_window)


def test_detail_bindings_scroll_and_move_resets():
    browser = make_browser([("user:1", "string"), ("user:2", "string")])
    handlers = {
        binding.keys[0]: binding.handler
        for binding in browser.detail_key_bindings().bindings
    }
    event = MagicMock()

    handlers["j"](event)
    handlers["j"](event)
    assert browser.detail_pane.vertical_scroll == 2
    handlers["k"](event)
    assert browser.detail_pane.vertical_scroll == 1
    handlers["k"](event)
    handlers["k"](event)  # clamped at the top
    assert browser.detail_pane.vertical_scroll == 0

    browser.detail_pane.vertical_scroll = 5
    browser.move(1)
    assert browser.detail_pane.vertical_scroll == 0


def test_detail_pane_keeps_manual_scroll():
    # the ScrollablePane must not chase an invisible cursor back to the
    # top: both keep-visible behaviours are disabled
    browser = make_browser([("user:1", "string")])
    assert not browser.detail_pane.keep_cursor_visible()
    assert not browser.detail_pane.keep_focused_window_visible()


# === mouse support ===


def mouse(event_type):
    return MouseEvent(
        position=Point(0, 0),
        event_type=event_type,
        button=MouseButton.LEFT,
        modifiers=frozenset(),
    )


def row_fragments(browser):
    """key_rows fragments grouped per visible row, newlines dropped."""
    rows, current = [], []
    for fragment in browser.key_rows():
        if fragment[1] == "\n":
            rows.append(current)
            current = []
        else:
            current.append(fragment)
    return rows


def test_key_rows_fragments_carry_mouse_handlers():
    browser = make_browser([("user:1", "string"), ("user:2", "string")])
    for row in row_fragments(browser):
        assert all(len(fragment) == 3 and callable(fragment[2]) for fragment in row)


def test_keys_panel_has_fixed_width():
    browser = make_browser([("user:1", "string")])
    assert browser.tree_window.width == TREE_WIDTH


def test_selected_row_background_spans_panel_width():
    browser = make_browser([("user:1", "string"), ("user:2", "string")])
    rows = row_fragments(browser)
    selected = [
        fragment for row in rows for fragment in row if fragment[0] == "class:selected"
    ]
    assert len(selected) == 1
    assert len(selected[0][1]) == TREE_WIDTH  # padded to fill the panel


def test_tree_click_selects_key_row(monkeypatch):
    browser = make_browser([("user:1", "string"), ("user:2", "string")])
    handler = row_fragments(browser)[2][0][2]  # the user:2 key row
    app = MagicMock()
    monkeypatch.setattr("iredis.browser.get_app", lambda: app)

    handler(mouse(MouseEventType.MOUSE_UP))

    assert browser.index == 2
    assert browser.selected_key == "user:2"
    app.layout.focus.assert_called_once_with(browser.tree_window)


def test_tree_click_on_group_row_toggles_fold(monkeypatch):
    browser = make_browser([("user:1", "string"), ("user:2", "string")])
    handler = row_fragments(browser)[0][0][2]  # the open "user" group row
    monkeypatch.setattr("iredis.browser.get_app", lambda: MagicMock())

    handler(mouse(MouseEventType.MOUSE_UP))

    assert browser.rows() == [("group", "user", 2, 0, False)]


def test_tree_wheel_scrolls_selection():
    browser = make_browser([(f"user:{i}", "string") for i in range(10)])
    handler = row_fragments(browser)[0][0][2]
    browser.index = 1

    handler(mouse(MouseEventType.SCROLL_DOWN))
    assert browser.index == 4
    handler(mouse(MouseEventType.SCROLL_UP))
    assert browser.index == 1


def test_detail_mouse_wheel_scrolls_and_click_focuses(monkeypatch):
    browser = make_browser([("user:1", "string")])
    app = MagicMock()
    monkeypatch.setattr("iredis.browser.get_app", lambda: app)

    browser.detail_mouse_handler(mouse(MouseEventType.SCROLL_DOWN))
    assert browser.detail_pane.vertical_scroll == 3
    browser.detail_mouse_handler(mouse(MouseEventType.SCROLL_UP))
    browser.detail_mouse_handler(mouse(MouseEventType.SCROLL_UP))
    assert browser.detail_pane.vertical_scroll == 0  # clamped at the top

    browser.detail_mouse_handler(mouse(MouseEventType.MOUSE_UP))
    app.layout.focus.assert_called_once_with(browser.detail_window)


# === copy shortcuts ===


def test_value_text_string():
    client = MagicMock()
    client.execute.return_value = b"hello"
    assert value_text(client, "k", "string") == "hello"
    client.execute.assert_called_once_with("GET", "k")


def test_value_text_list_and_set_one_element_per_line():
    client = MagicMock()
    client.execute.return_value = [b"a", b"b"]
    assert value_text(client, "k", "list") == "a\nb"
    client.execute.assert_called_with("LRANGE", "k", 0, -1)
    assert value_text(client, "k", "set") == "a\nb"
    client.execute.assert_called_with("SMEMBERS", "k")


def test_value_text_hash_fields_tab_separated():
    client = MagicMock()
    client.execute.return_value = [b"f1", b"v1", b"f2", b"v2"]
    assert value_text(client, "k", "hash") == "f1\tv1\nf2\tv2"
    client.execute.assert_called_with("HGETALL", "k")


def test_value_text_zset_member_score_pairs():
    client = MagicMock()
    client.execute.return_value = [b"m1", b"1", b"m2", b"2"]
    assert value_text(client, "k", "zset") == "m1\t1\nm2\t2"
    client.execute.assert_called_with("ZRANGE", "k", 0, -1, "WITHSCORES")


def test_value_text_unknown_type_returns_none():
    client = MagicMock()
    assert value_text(client, "k", "stream") is None
    client.execute.assert_not_called()


def test_copy_selected_value_sends_raw_value_to_clipboard(monkeypatch):
    browser = make_browser([("user:1", "string"), ("user:2", "string")])
    copied = {}
    monkeypatch.setattr(
        "iredis.browser.copy_to_clipboard",
        lambda text, output=None: copied.setdefault("text", text),
    )
    browser.client.execute.return_value = b"hello"
    browser.index = 1  # user:1

    browser.copy_selected_value()

    assert copied["text"] == "hello"
    assert "copied" in browser.notice


def test_copy_selected_key_sends_key_name_to_clipboard(monkeypatch):
    browser = make_browser([("user:1", "string"), ("user:2", "string")])
    copied = {}
    monkeypatch.setattr(
        "iredis.browser.copy_to_clipboard",
        lambda text, output=None: copied.setdefault("text", text),
    )
    browser.index = 2  # user:2

    browser.copy_selected_key()

    assert copied["text"] == "user:2"
    assert "copied" in browser.notice


def test_copy_on_group_row_flashes_notice_without_clipboard(monkeypatch):
    browser = make_browser([("user:1", "string"), ("user:2", "string")])
    monkeypatch.setattr(
        "iredis.browser.copy_to_clipboard",
        lambda text, output=None: (_ for _ in ()).throw(AssertionError),
    )
    browser.index = 0  # the "user" group row

    browser.copy_selected_value()
    assert "select a key" in browser.notice
    browser.copy_selected_key()
    assert "select a key" in browser.notice
