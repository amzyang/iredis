from unittest.mock import MagicMock

from iredis.browser import PatternBrowser, single_chain_paths, tree_rows

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


def make_browser(keys, cursor=0):
    client = MagicMock()
    client.scan_keys.return_value = ([key for key, _ in keys], cursor)
    client._fetch_types.return_value = [key_type for _, key_type in keys]
    return PatternBrowser(client, "users", "user:*")


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


def test_browser_binds_vim_hjkl_alongside_arrows():
    browser = make_browser([("user:1", "string"), ("user:2", "string")])
    bound = {key for binding in browser.key_bindings().bindings for key in binding.keys}
    assert {"h", "j", "k", "l", "up", "down", "left", "right"} <= bound


def test_browser_hjkl_navigation_behaviour():
    browser = make_browser([("user:1", "string"), ("user:2", "string")])
    event = MagicMock()
    handlers = {
        binding.keys[0]: binding.handler for binding in browser.key_bindings().bindings
    }

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
