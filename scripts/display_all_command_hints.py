from prompt_toolkit import print_formatted_text

from iredis.commands import commands_summary
from iredis.style import STYLE
from iredis.utils import command_syntax

for command, info in commands_summary.items():
    print_formatted_text(command_syntax(command, info), style=STYLE)
