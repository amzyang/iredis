def test_browse(judge_command):
    judge_command("BROWSE", {"command": "BROWSE"})
    judge_command("browse", {"command": "browse"})
    judge_command("BROWSE user:*", {"command": "BROWSE", "pattern": "user:*"})
    judge_command(
        "browse 'session:*'",
        {"command": "browse", "pattern": "'session:*'"},
    )
