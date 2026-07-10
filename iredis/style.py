import logging
from functools import lru_cache

from prompt_toolkit.styles import Style, merge_styles

logger = logging.getLogger(__name__)

override_style = Style([("bottom-toolbar", "noreverse")])


def _build_theme(redis_token, doc, ui, toolbar_bg):
    """Assemble the full style dict of one theme.

    :param redis_token: colors for redis response tokens (key, string, ...)
    :param doc: colors for command doc rendering.
    :param ui: colors for iredis's own UI (prompt, toolbar, completion menu...)
    :param toolbar_bg: background color of the bottom toolbar, redis tokens
        rendered in the toolbar reuse their own color upon this background.
    """
    theme = dict(redis_token)
    theme.update(ui)
    theme.update(
        {
            f"bottom-toolbar.{token}": f"bg:{toolbar_bg} {token_style}"
            for token, token_style in redis_token.items()
        }
    )
    theme.update(doc)
    return theme


# "default" theme only uses the 16 ANSI colors, so iredis will follow
# whatever palette the terminal is configured with, and looks consistent
# with the terminal on both dark and light backgrounds.
DEFAULT_REDIS_TOKEN = {
    "key": "ansigreen",
    "important-key": "bold ansigreen",
    "pattern": "bold ansigreen",
    "string": "ansiyellow",
    "member": "ansiyellow",
    "command": "bold ansigreen",
    "integer": "ansimagenta",
    "const": "bold ansimagenta",
    "time": "ansimagenta",
    "double": "ansibrightmagenta",
    "nil": "ansibrightblack",
    "bit": "ansibrightblue",
    "field": "ansicyan",
    "group": "ansiblue",
    "username": "ansiblue",
}

DEFAULT_DOC = {
    "doccommand": "bold",
    "dockey": "ansiyellow",
    "code": "ansigray",
    "h2": "bold ansigreen",
}

DEFAULT_UI = {
    # User input (default text), inherit terminal's default foreground.
    "": "",
    # Prompt.
    "rprompt": "bg:ansired ansiwhite",
    "hostname": "",
    "index": "ansired",
    "trailing-input": "bg:ansired ansiblack",
    "password": "hidden",
    "success": "ansigreen bold",
    "queued": "ansigreen bold",
    "error": "ansired bold",
    "type": "ansibrightblack",
    "channel": "ansibrightblack",
    # bottom-toolbar
    "bottom-toolbar": "bg:ansiblack ansigray",
    "bottom-toolbar.on": "bg:ansiblack ansiwhite",
    "bottom-toolbar.off": "bg:ansiblack ansibrightblack",
    "bottom-toolbar.loaded": "bg:ansiblack ansigreen",
    "bottom-toolbar.since": "bg:ansiblack ansiyellow",
    "bottom-toolbar.complexity": "bg:ansiblack ansibrightblack",
    "bottom-toolbar.group": "bg:ansiblack ansired bold",
    # completion
    "completion-menu.completion.current": "bg:ansiwhite ansiblack",
    "completion-menu.completion": "bg:ansicyan ansiwhite",
    "completion-menu.meta.completion.current": "bg:ansibrightcyan ansiblack",
    "completion-menu.meta.completion": "bg:ansicyan ansiwhite",
    "completion-menu.multi-column-meta": "bg:ansibrightcyan ansiblack",
    "scrollbar.arrow": "bg:ansiblack",
    "scrollbar": "bg:ansicyan",
    "selected": "ansiwhite bg:ansiblue",
    "search": "ansiwhite bg:ansiblue",
    "search.current": "ansiwhite bg:ansigreen",
    "search-toolbar": "noinherit bold",
    "search-toolbar.text": "nobold",
    "system-toolbar": "noinherit bold",
    "arg-toolbar": "noinherit bold",
    "arg-toolbar.text": "nobold",
}

# "classic" theme is the original iredis color scheme, colors are
# hardcoded 24-bit values so it looks the same on every terminal.
CLASSIC_REDIS_TOKEN = {
    "key": "#33aa33",
    "important-key": "#058B06",
    "pattern": "bold #33aa33",
    "string": "#FD971F",
    "member": "#FD971F",
    "command": "bold #008000",
    "integer": "#AE81FF",
    "const": "bold #AE81FF",
    "time": "#aa22ff",
    "double": "#bb6688",
    "nil": "#808080",
    "bit": "#8541FF",
    "field": "cyan",
    "group": "ansiblue",
    "username": "blue",
}

CLASSIC_DOC = {
    "doccommand": "bold",
    "dockey": "#E6DB74",
    "code": "#aaaaaa",
    "h2": "bold #33aa33",
}

CLASSIC_UI = {
    # User input (default text).
    "": "",
    # Prompt.
    "rprompt": "bg:#ff0066 #ffffff",
    "hostname": "",
    "index": "#ff0000",
    "trailing-input": "bg:#ff0000 #000000",
    "password": "hidden",
    "success": "#00ff5f bold",
    "queued": "#32CD32 bold",
    "error": "#ff005f bold",
    "type": "#888",
    "channel": "#888",  # FIXME
    # colors below copied from mycli project, ~~love~~
    # bottom-toolbar
    "bottom-toolbar": "bg:#222222 #aaaaaa",
    "bottom-toolbar.on": "bg:#222222 #ffffff",
    "bottom-toolbar.off": "bg:#222222 #888888",
    "bottom-toolbar.loaded": "bg:#222222 #44aa44",
    "bottom-toolbar.since": "bg:#222222 #bc7a00",
    "bottom-toolbar.complexity": "bg:#222222 #666666",
    "bottom-toolbar.group": "bg:#222222 #d2413a bold",
    # completion
    "completion-menu.completion.current": "bg:#ffffff #000000",
    "completion-menu.completion": "bg:#008888 #ffffff",
    "completion-menu.meta.completion.current": "bg:#44aaaa #000000",
    "completion-menu.meta.completion": "bg:#448888 #ffffff",
    "completion-menu.multi-column-meta": "bg:#aaffff #000000",
    "scrollbar.arrow": "bg:#003333",
    "scrollbar": "bg:#00aaaa",
    "selected": "#ffffff bg:#6666aa",
    "search": "#ffffff bg:#4444aa",
    "search.current": "#ffffff bg:#44aa44",
    "search-toolbar": "noinherit bold",
    "search-toolbar.text": "nobold",
    "system-toolbar": "noinherit bold",
    "arg-toolbar": "noinherit bold",
    "arg-toolbar.text": "nobold",
}

THEMES = {
    "default": _build_theme(DEFAULT_REDIS_TOKEN, DEFAULT_DOC, DEFAULT_UI, "ansiblack"),
    "classic": _build_theme(CLASSIC_REDIS_TOKEN, CLASSIC_DOC, CLASSIC_UI, "#222222"),
}


@lru_cache(maxsize=None)
def get_style(theme_name=None):
    """Return the prompt_toolkit Style of the given theme.

    Unset or unknown theme names fall back to "default", which follows the
    terminal's own color palette.
    """
    if not theme_name:
        theme_name = "default"
    theme = THEMES.get(theme_name)
    if theme is None:
        logger.warning(
            f"Unknown theme: {theme_name}, supported themes:"
            f" {', '.join(THEMES)}. Using default theme."
        )
        theme = THEMES["default"]
    return merge_styles([override_style, Style.from_dict(theme)])


# kept for backward compatibility
STYLE = get_style()
