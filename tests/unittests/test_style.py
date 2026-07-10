import pytest

from iredis.style import STYLE, THEMES, get_style


def test_themes_have_same_token_classes():
    default_theme = THEMES["default"]
    classic_theme = THEMES["classic"]
    assert set(default_theme) == set(classic_theme)


def test_default_theme_only_uses_terminal_ansi_colors():
    # the default theme should follow the terminal's palette, so it can
    # not use any hardcoded 24-bit colors.
    for token, token_style in THEMES["default"].items():
        assert "#" not in token_style, f"{token} uses a hardcoded color"


@pytest.mark.parametrize("theme_name", [None, "", "default", "classic", "not-exist"])
def test_get_style_always_returns_a_style(theme_name):
    style = get_style(theme_name)
    assert style is not None
    assert style.style_rules


def test_get_style_unknown_theme_fallback_to_default():
    assert get_style("not-exist").style_rules == get_style("default").style_rules
    assert get_style().style_rules == get_style("default").style_rules


def test_classic_theme_keeps_original_colors():
    classic = dict(get_style("classic").style_rules)
    assert classic["key"] == "#33aa33"
    assert classic["string"] == "#FD971F"
    assert classic["bottom-toolbar.key"] == "bg:#222222 #33aa33"


def test_module_level_style_is_default_theme():
    assert STYLE.style_rules == get_style("default").style_rules
