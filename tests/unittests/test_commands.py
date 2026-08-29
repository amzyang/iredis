from iredis.commands import suggest_commands


def test_suggest_commands_finds_close_match():
    assert suggest_commands("delete") == ["DEL"]


def test_suggest_commands_is_case_insensitive():
    assert suggest_commands("DELETE") == ["DEL"]


def test_suggest_commands_returns_empty_for_gibberish():
    assert suggest_commands("xqzwvk") == []


def test_suggest_commands_excludes_exact_match():
    # a valid command unknown to an old redis-server should not
    # suggest itself
    assert "GETDEL" not in suggest_commands("getdel")
