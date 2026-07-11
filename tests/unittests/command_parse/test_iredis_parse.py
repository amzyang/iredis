def test_pattern(judge_command):
    judge_command("PATTERN", {"command": "PATTERN"})
    judge_command("pattern", {"command": "pattern"})
    judge_command("PATTERN users", {"command": "PATTERN", "pattern_name": "users"})
    judge_command(
        "PATTERN users 100",
        {"command": "PATTERN", "pattern_name": "users", "cursor": "100"},
    )


def test_pattern_add(judge_command):
    judge_command(
        "PATTERN ADD users user:*",
        {"command": "PATTERN ADD", "pattern_name": "users", "pattern": "user:*"},
    )
    judge_command(
        "pattern add sessions 'session:*'",
        {
            "command": "pattern add",
            "pattern_name": "sessions",
            "pattern": "'session:*'",
        },
    )
    judge_command("PATTERN ADD users", None)


def test_pattern_rm(judge_command):
    judge_command(
        "PATTERN RM users", {"command": "PATTERN RM", "pattern_name": "users"}
    )


def test_pattern_browse(judge_command):
    judge_command("PATTERN BROWSE", {"command": "PATTERN BROWSE"})
    judge_command(
        "PATTERN BROWSE users",
        {"command": "PATTERN BROWSE", "pattern_name": "users"},
    )
