from unittest.mock import MagicMock

from prompt_toolkit.formatted_text import to_formatted_text
from prompt_toolkit.formatted_text.utils import (
    fragment_list_to_text,
    fragment_list_width,
)

from iredis.bottom import F3_HINT, BottomToolbar, append_right_hint


def test_append_right_hint_pads_to_full_width():
    fragments = [("", "Ctrl-D to exit;")]
    padded = append_right_hint(fragments, 40)
    assert fragment_list_to_text(padded).endswith(f"{F3_HINT} ")
    assert fragment_list_width(padded) == 40


def test_append_right_hint_dropped_when_no_room():
    fragments = [("", "a long left text taking the whole bar")]
    assert append_right_hint(fragments, 40) == fragments


def test_bottom_bar_render_shows_f3_hint_right_aligned():
    holder = MagicMock()
    holder.command = None
    rendered = to_formatted_text(BottomToolbar(holder).render())
    # DummyOutput reports an 80-column terminal
    assert fragment_list_to_text(rendered).endswith(f"{F3_HINT} ")
    assert fragment_list_width(rendered) == 80
