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

# Official Catppuccin palette, https://github.com/catppuccin/palette
# 4 flavors share the same color names, latte is light, the other three
# are dark, from lighter to darker: frappe, macchiato, mocha.
CATPPUCCIN_PALETTES = {
    "catppuccin-latte": {
        "rosewater": "#dc8a78",
        "flamingo": "#dd7878",
        "pink": "#ea76cb",
        "mauve": "#8839ef",
        "red": "#d20f39",
        "maroon": "#e64553",
        "peach": "#fe640b",
        "yellow": "#df8e1d",
        "green": "#40a02b",
        "teal": "#179299",
        "sky": "#04a5e5",
        "sapphire": "#209fb5",
        "blue": "#1e66f5",
        "lavender": "#7287fd",
        "text": "#4c4f69",
        "subtext1": "#5c5f77",
        "subtext0": "#6c6f85",
        "overlay2": "#7c7f93",
        "overlay1": "#8c8fa1",
        "overlay0": "#9ca0b0",
        "surface2": "#acb0be",
        "surface1": "#bcc0cc",
        "surface0": "#ccd0da",
        "base": "#eff1f5",
        "mantle": "#e6e9ef",
        "crust": "#dce0e8",
    },
    "catppuccin-frappe": {
        "rosewater": "#f2d5cf",
        "flamingo": "#eebebe",
        "pink": "#f4b8e4",
        "mauve": "#ca9ee6",
        "red": "#e78284",
        "maroon": "#ea999c",
        "peach": "#ef9f76",
        "yellow": "#e5c890",
        "green": "#a6d189",
        "teal": "#81c8be",
        "sky": "#99d1db",
        "sapphire": "#85c1dc",
        "blue": "#8caaee",
        "lavender": "#babbf1",
        "text": "#c6d0f5",
        "subtext1": "#b5bfe2",
        "subtext0": "#a5adce",
        "overlay2": "#949cbb",
        "overlay1": "#838ba7",
        "overlay0": "#737994",
        "surface2": "#626880",
        "surface1": "#51576d",
        "surface0": "#414559",
        "base": "#303446",
        "mantle": "#292c3c",
        "crust": "#232634",
    },
    "catppuccin-macchiato": {
        "rosewater": "#f4dbd6",
        "flamingo": "#f0c6c6",
        "pink": "#f5bde6",
        "mauve": "#c6a0f6",
        "red": "#ed8796",
        "maroon": "#ee99a0",
        "peach": "#f5a97f",
        "yellow": "#eed49f",
        "green": "#a6da95",
        "teal": "#8bd5ca",
        "sky": "#91d7e3",
        "sapphire": "#7dc4e4",
        "blue": "#8aadf4",
        "lavender": "#b7bdf8",
        "text": "#cad3f5",
        "subtext1": "#b8c0e0",
        "subtext0": "#a5adcb",
        "overlay2": "#939ab7",
        "overlay1": "#8087a2",
        "overlay0": "#6e738d",
        "surface2": "#5b6078",
        "surface1": "#494d64",
        "surface0": "#363a4f",
        "base": "#24273a",
        "mantle": "#1e2030",
        "crust": "#181926",
    },
    "catppuccin-mocha": {
        "rosewater": "#f5e0dc",
        "flamingo": "#f2cdcd",
        "pink": "#f5c2e7",
        "mauve": "#cba6f7",
        "red": "#f38ba8",
        "maroon": "#eba0ac",
        "peach": "#fab387",
        "yellow": "#f9e2af",
        "green": "#a6e3a1",
        "teal": "#94e2d5",
        "sky": "#89dceb",
        "sapphire": "#74c7ec",
        "blue": "#89b4fa",
        "lavender": "#b4befe",
        "text": "#cdd6f4",
        "subtext1": "#bac2de",
        "subtext0": "#a6adc8",
        "overlay2": "#9399b2",
        "overlay1": "#7f849c",
        "overlay0": "#6c7086",
        "surface2": "#585b70",
        "surface1": "#45475a",
        "surface0": "#313244",
        "base": "#1e1e2e",
        "mantle": "#181825",
        "crust": "#11111b",
    },
}


def _catppuccin_theme(p):
    """Build one theme from a Catppuccin flavor palette.

    All 4 flavors share the same color names, so the semantic token
    mapping is defined once here, colors all come from the palette.
    """
    redis_token = {
        "key": p["green"],
        "important-key": f"bold {p['green']}",
        "pattern": f"bold {p['green']}",
        "string": p["yellow"],
        "member": p["yellow"],
        "command": f"bold {p['green']}",
        "integer": p["peach"],
        "const": f"bold {p['peach']}",
        "time": p["peach"],
        "double": p["pink"],
        "nil": p["overlay0"],
        "bit": p["sky"],
        "field": p["teal"],
        "group": p["blue"],
        "username": p["blue"],
    }
    doc = {
        "doccommand": "bold",
        "dockey": p["yellow"],
        "code": p["subtext0"],
        "h2": f"bold {p['green']}",
    }
    ui = {
        # User input (default text), inherit terminal's default foreground.
        "": "",
        # Prompt.
        "rprompt": f"bg:{p['red']} {p['base']}",
        "hostname": "",
        "index": p["red"],
        "trailing-input": f"bg:{p['red']} {p['base']}",
        "password": "hidden",
        "success": f"{p['green']} bold",
        "queued": f"{p['green']} bold",
        "error": f"{p['red']} bold",
        "type": p["overlay1"],
        "channel": p["overlay1"],
        # bottom-toolbar
        "bottom-toolbar": f"bg:{p['mantle']} {p['subtext0']}",
        "bottom-toolbar.on": f"bg:{p['mantle']} {p['text']}",
        "bottom-toolbar.off": f"bg:{p['mantle']} {p['overlay0']}",
        "bottom-toolbar.loaded": f"bg:{p['mantle']} {p['green']}",
        "bottom-toolbar.since": f"bg:{p['mantle']} {p['yellow']}",
        "bottom-toolbar.complexity": f"bg:{p['mantle']} {p['overlay0']}",
        "bottom-toolbar.group": f"bg:{p['mantle']} {p['red']} bold",
        # completion
        "completion-menu.completion.current": f"bg:{p['blue']} {p['base']}",
        "completion-menu.completion": f"bg:{p['surface0']} {p['text']}",
        "completion-menu.meta.completion.current": f"bg:{p['surface1']} {p['text']}",
        "completion-menu.meta.completion": f"bg:{p['surface0']} {p['subtext0']}",
        "completion-menu.multi-column-meta": f"bg:{p['surface1']} {p['subtext1']}",
        "scrollbar.arrow": f"bg:{p['surface0']}",
        "scrollbar": f"bg:{p['surface2']}",
        "selected": f"bg:{p['surface1']} {p['text']}",
        "search": f"bg:{p['blue']} {p['base']}",
        "search.current": f"bg:{p['green']} {p['base']}",
        "search-toolbar": "noinherit bold",
        "search-toolbar.text": "nobold",
        "system-toolbar": "noinherit bold",
        "arg-toolbar": "noinherit bold",
        "arg-toolbar.text": "nobold",
    }
    return _build_theme(redis_token, doc, ui, p["mantle"])


THEMES = {
    "default": _build_theme(DEFAULT_REDIS_TOKEN, DEFAULT_DOC, DEFAULT_UI, "ansiblack"),
    "classic": _build_theme(CLASSIC_REDIS_TOKEN, CLASSIC_DOC, CLASSIC_UI, "#222222"),
    **{name: _catppuccin_theme(p) for name, p in CATPPUCCIN_PALETTES.items()},
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
