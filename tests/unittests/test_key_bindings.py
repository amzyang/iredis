from unittest.mock import MagicMock

from prompt_toolkit.keys import Keys

from iredis.key_bindings import kb


def get_f3_handler():
    for binding in kb.bindings:
        if binding.keys == (Keys.F3,):
            return binding.handler
    raise AssertionError("no F3 binding registered")


def make_event(buffer_text):
    event = MagicMock()
    event.app.current_buffer.text = buffer_text
    return event


def test_f3_prefills_pattern_browse_on_empty_prompt():
    event = make_event("")
    get_f3_handler()(event)

    buf = event.app.current_buffer
    buf.insert_text.assert_called_once_with("PATTERN BROWSE ")
    buf.start_completion.assert_called_once_with(select_first=False)


def test_f3_is_noop_when_prompt_not_empty():
    event = make_event("GET foo")
    get_f3_handler()(event)

    buf = event.app.current_buffer
    buf.insert_text.assert_not_called()
    buf.start_completion.assert_not_called()
