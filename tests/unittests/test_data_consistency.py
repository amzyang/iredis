"""Guard the consistency between the three command data files:

- iredis/data/command_syntax.csv (command -> grammar/render mapping)
- iredis/data/commands.json (command metadata from redis-doc)
- iredis/data/commands/*.md (documents for the HELP command)
"""

import csv
from importlib.resources import files

from iredis import data as project_data
from iredis.commands import commands_summary
from iredis.redis_grammar import GRAMMAR
from iredis.renders import OutputRender

# commands that redis-doc dropped but iredis still supports for old servers
LEGACY_COMMANDS = {"DEBUG OBJECT", "DEBUG SEGFAULT", "STRALGO"}


def load_syntax_rows():
    with (
        files(project_data)
        .joinpath("command_syntax.csv")
        .open("r", encoding="utf-8") as f
    ):
        return list(csv.reader(f))[1:]


def test_csv_rows_have_four_clean_columns():
    for row in load_syntax_rows():
        assert len(row) == 4, f"malformed row: {row}"
        for cell in row:
            assert cell == cell.strip(), f"cell with surrounding spaces: {row}"


def test_csv_syntax_names_exist_in_grammar():
    for _, command, syntax, _ in load_syntax_rows():
        assert syntax in GRAMMAR, f"{command}: unknown syntax {syntax}"


def test_csv_callbacks_are_output_render_methods():
    for _, command, _, callback in load_syntax_rows():
        if callback:
            assert hasattr(OutputRender, callback), (
                f"{command}: unknown callback {callback}"
            )


def test_csv_commands_have_metadata_in_commands_json():
    for group, command, _, _ in load_syntax_rows():
        if group == "iredis" or command in LEGACY_COMMANDS:
            continue
        assert command in commands_summary, f"{command}: missing in commands.json"


def test_commands_json_entries_have_help_documents():
    for command, info in commands_summary.items():
        if info.get("group") == "iredis":
            continue
        doc = files(project_data).joinpath(
            "commands", f"{command.replace(' ', '-').lower()}.md"
        )
        assert doc.is_file(), f"{command}: missing help document"
