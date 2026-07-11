import logging

from prompt_toolkit.application import get_app
from prompt_toolkit.formatted_text import FormattedText, to_formatted_text
from prompt_toolkit.formatted_text.utils import fragment_list_width

from .commands import commands_summary
from .utils import command_syntax

BUTTOM_TEXT = "Ctrl-D to exit;"
F3_HINT = "F3 browse"
logger = logging.getLogger(__name__)


def append_right_hint(fragments, columns, hint=F3_HINT):
    """Right-align hint on a columns-wide bar; dropped when there's no room."""
    padding = columns - fragment_list_width(fragments) - len(hint) - 1
    if padding < 1:
        return fragments
    return fragments + [
        ("", " " * padding),
        ("class:bottom-toolbar.on", hint),
        ("", " "),
    ]


class BottomToolbar:
    CHAR = "⣾⣷⣯⣟⡿⢿⣻⣽"

    def __init__(self, command_holder):
        self.index = 0
        # BottomToolbar can only read this variable
        self.command_holder = command_holder

    def get_animation_char(self):
        animation = self.CHAR[self.index]

        self.index += 1
        if self.index == len(self.CHAR):
            self.index = 0
        return animation

    def render(self):
        text = BUTTOM_TEXT
        # add command help if valid
        if self.command_holder.command:
            try:
                command_info = commands_summary[self.command_holder.command]
                text = command_syntax(self.command_holder.command, command_info)
            except KeyError as e:
                logger.exception(e)

        fragments = list(to_formatted_text(text))
        columns = get_app().output.get_size().columns
        return FormattedText(append_right_hint(fragments, columns))
