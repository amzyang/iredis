def test_rpush(judge_command):
    judge_command(
        "RPUSH list1 foo bar hello world",
        {
            "command_key_values": "RPUSH",
            "key": "list1",
            "values": "foo bar hello world",
        },
    )
    judge_command(
        "LPUSH list1 foo",
        {"command_key_values": "LPUSH", "key": "list1", "values": "foo"},
    )


def test_lindex(judge_command):
    judge_command(
        "LINDEX list1 10",
        {"command_key_position": "LINDEX", "key": "list1", "position": "10"},
    )
    judge_command(
        "LINDEX list1 -10",
        {"command_key_position": "LINDEX", "key": "list1", "position": "-10"},
    )
    judge_command("LINDEX list1 1.1", None)


def test_lset(judge_command):
    judge_command(
        "LSET list1 10 newbie",
        {
            "command_key_position_value": "LSET",
            "key": "list1",
            "position": "10",
            "value": "newbie",
        },
    )
    judge_command(
        "LSET list1 -1 newbie",
        {
            "command_key_position_value": "LSET",
            "key": "list1",
            "position": "-1",
            "value": "newbie",
        },
    )


def test_brpoplpush(judge_command):
    judge_command(
        "BRPOPLPUSH list1 list2 10",
        {
            "command_key_newkey_timeout": "BRPOPLPUSH",
            "key": "list1",
            "newkey": "list2",
            "timeout": "10",
        },
    )
    judge_command(
        "BRPOPLPUSH list1 list2 0",
        {
            "command_key_newkey_timeout": "BRPOPLPUSH",
            "key": "list1",
            "newkey": "list2",
            "timeout": "0",
        },
    )
    judge_command("BRPOPLPUSH list1 list2 -1", None)


def test_linsert(judge_command):
    judge_command(
        'LINSERT mylist BEFORE "World" "There"',
        {
            "command_key_positionchoice_pivot_value": "LINSERT",
            "key": "mylist",
            "position_choice": "BEFORE",
            "value": ['"World"', '"There"'],
        },
    )
    judge_command(
        'LINSERT mylist after "World" "There"',
        {
            "command_key_positionchoice_pivot_value": "LINSERT",
            "key": "mylist",
            "position_choice": "after",
            "value": ['"World"', '"There"'],
        },
    )
