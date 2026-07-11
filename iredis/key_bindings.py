import logging

from prompt_toolkit.filters import completion_is_selected
from prompt_toolkit.key_binding import KeyBindings

logger = logging.getLogger(__name__)

kb = KeyBindings()


@kb.add("enter", filter=completion_is_selected)
def _(event):
    """Makes the enter key work as the tab key only when showing the menu.
    In other words, don't execute query when enter is pressed in
    the completion dropdown menu, instead close the dropdown menu
    (accept current selection).
    """
    logger.debug("Detected enter key.")

    event.current_buffer.complete_state = None
    b = event.app.current_buffer
    b.complete_state = None


@kb.add("f3")
def _(event):
    """F3: run `BROWSE`, opening the key browser over the whole keyspace.

    Only fires on an empty prompt, so it never clobbers typed input.
    """
    buf = event.app.current_buffer
    if buf.text:
        return
    buf.insert_text("BROWSE")
    buf.validate_and_handle()
