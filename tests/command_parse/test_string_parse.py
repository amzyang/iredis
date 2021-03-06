def test_set(judge_command):
    judge_command(
        "SET abc bar",
        {"command_key_value_expiration_condition": "SET", "key": "abc", "value": "bar"},
    )
    judge_command(
        "SET abc bar EX 10",
        {
            "command_key_value_expiration_condition": "SET",
            "key": "abc",
            "value": "bar",
            "expiration": "EX",
            "millisecond": "10",
        },
    )
    judge_command(
        "SET abc bar px 10000",
        {
            "command_key_value_expiration_condition": "SET",
            "key": "abc",
            "value": "bar",
            "expiration": "px",
            "millisecond": "10000",
        },
    )
    judge_command(
        "SET abc bar px 10000 nx",
        {
            "command_key_value_expiration_condition": "SET",
            "key": "abc",
            "value": "bar",
            "expiration": "px",
            "millisecond": "10000",
            "condition": "nx",
        },
    )
    judge_command(
        "SET abc bar px 10000 XX",
        {
            "command_key_value_expiration_condition": "SET",
            "key": "abc",
            "value": "bar",
            "expiration": "px",
            "millisecond": "10000",
            "condition": "XX",
        },
    )
    judge_command(
        "SET abc bar XX",
        {
            "command_key_value_expiration_condition": "SET",
            "key": "abc",
            "value": "bar",
            "condition": "XX",
        },
    )


def test_append(judge_command):
    judge_command(
        "append foo bar", {"command_key_value": "append", "key": "foo", "value": "bar"}
    )
    judge_command(
        "APPEND foo 'bar'",
        {"command_key_value": "APPEND", "key": "foo", "value": "'bar'"},
    )
    judge_command("APPEND foo", None)


def test_bitcount(judge_command):
    judge_command("bitcount foo", {"command_key_start_end_x": "bitcount", "key": "foo"})
    judge_command(
        "bitcount foo 1 5",
        {"command_key_start_end_x": "bitcount", "key": "foo", "start": "1", "end": "5"},
    )
    judge_command(
        "bitcount foo 1 -5",
        {
            "command_key_start_end_x": "bitcount",
            "key": "foo",
            "start": "1",
            "end": "-5",
        },
    )
    judge_command(
        "bitcount foo -2 -1",
        {
            "command_key_start_end_x": "bitcount",
            "key": "foo",
            "start": "-2",
            "end": "-1",
        },
    )
    judge_command("bitcount foo -2", None)


def test_getrange(judge_command):
    judge_command("getrange foo", None)
    judge_command(
        "getrange foo 1 5",
        {"command_key_start_end": "getrange", "key": "foo", "start": "1", "end": "5"},
    )
    judge_command(
        "getrange foo 1 -5",
        {"command_key_start_end": "getrange", "key": "foo", "start": "1", "end": "-5"},
    )
    judge_command(
        "getrange foo -2 -1",
        {"command_key_start_end": "getrange", "key": "foo", "start": "-2", "end": "-1"},
    )
    judge_command("getrange foo -2", None)


def test_get_set(judge_command):
    judge_command(
        "GETSET abc bar", {"command_key_value": "GETSET", "key": "abc", "value": "bar"}
    )


def test_incr(judge_command):
    judge_command("INCR foo", {"command_key": "INCR", "key": "foo"})
    judge_command("INCR", None)
    judge_command("INCR foo 1", None)


def test_incr_by(judge_command):
    judge_command("INCRBY foo", None)
    judge_command("INCRBY", None)
    judge_command(
        "INCRBY foo 1", {"command_key_delta": "INCRBY", "key": "foo", "delta": "1"}
    )
    judge_command(
        "INCRBY foo 200", {"command_key_delta": "INCRBY", "key": "foo", "delta": "200"}
    )
    judge_command(
        "INCRBY foo -21", {"command_key_delta": "INCRBY", "key": "foo", "delta": "-21"}
    )


def test_decr(judge_command):
    judge_command("DECR foo", {"command_key": "DECR", "key": "foo"})
    judge_command("DECR", None)
    judge_command("DECR foo 1", None)


def test_decr_by(judge_command):
    judge_command("DECRBY foo", None)
    judge_command("DECRBY", None)
    judge_command(
        "DECRBY foo 1", {"command_key_delta": "DECRBY", "key": "foo", "delta": "1"}
    )
    judge_command(
        "DECRBY foo 200", {"command_key_delta": "DECRBY", "key": "foo", "delta": "200"}
    )
    judge_command(
        "DECRBY foo -21", {"command_key_delta": "DECRBY", "key": "foo", "delta": "-21"}
    )


def test_command_set_range(judge_command):
    judge_command(
        "SETRANGE foo 10 bar",
        {
            "command_key_offset_value": "SETRANGE",
            "key": "foo",
            "offset": "10",
            "value": "bar",
        },
    )
    judge_command("SETRANGE foo bar", None)
    judge_command(
        "SETRANGE Redis 10 'hello world'",
        {
            "command_key_offset_value": "SETRANGE",
            "key": "Redis",
            "offset": "10",
            "value": "'hello world'",
        },
    )


def test_command_set_ex(judge_command):
    judge_command(
        "SETEX key 10 value",
        {
            "command_key_second_value": "SETEX",
            "key": "key",
            "second": "10",
            "value": "value",
        },
    )
    judge_command("SETEX foo 10", None)
    judge_command(
        "setex Redis 10 'hello world'",
        {
            "command_key_second_value": "setex",
            "key": "Redis",
            "second": "10",
            "value": "'hello world'",
        },
    )


def test_command_setbit(judge_command):
    judge_command(
        "SETBIT key 10 0",
        {"command_key_offset_bit": "SETBIT", "key": "key", "offset": "10", "bit": "0"},
    )
    judge_command(
        "SETBIT foo 10 1",
        {"command_key_offset_bit": "SETBIT", "key": "foo", "offset": "10", "bit": "1"},
    )
    judge_command("SETBIT foo 10 10", None)
    judge_command("SETBIT foo 10 abc", None)
    judge_command("SETBIT foo 10", None)
    judge_command("SETBIT foo", None)


def test_command_getbit(judge_command):
    judge_command(
        "GETBIT key 10", {"command_key_offset": "GETBIT", "key": "key", "offset": "10"}
    )
    judge_command(
        "GETBIT foo 0", {"command_key_offset": "GETBIT", "key": "foo", "offset": "0"}
    )
    judge_command("GETBIT foo -1", None)
    judge_command("SETBIT foo abc", None)
    judge_command("SETBIT foo", None)


def test_command_incrbyfloat(judge_command):
    judge_command("INCRBYFLOAT key", None)
    judge_command(
        "INCRBYFLOAT key 1.1",
        {"command_key_float": "INCRBYFLOAT", "key": "key", "float": "1.1"},
    )
    judge_command(
        "INCRBYFLOAT key .1",
        {"command_key_float": "INCRBYFLOAT", "key": "key", "float": ".1"},
    )
    judge_command(
        "INCRBYFLOAT key 1.",
        {"command_key_float": "INCRBYFLOAT", "key": "key", "float": "1."},
    )
    judge_command(
        "INCRBYFLOAT key 5.0e3",
        {"command_key_float": "INCRBYFLOAT", "key": "key", "float": "5.0e3"},
    )
    judge_command(
        "INCRBYFLOAT key -5.0e3",
        {"command_key_float": "INCRBYFLOAT", "key": "key", "float": "-5.0e3"},
    )


def test_command_mget(judge_command):
    judge_command("mget foo bar", {"command_keys": "mget", "keys": "foo bar"})


def test_mset(judge_command):
    judge_command(
        "mset foo bar", {"command_key_valuess": "mset", "key": "foo", "value": "bar"}
    )
    judge_command(
        "mset foo bar hello world",
        {"command_key_valuess": "mset", "key": "hello", "value": "world"},
    )


def test_psetex(judge_command):
    judge_command(
        "psetex foo 1000 bar",
        {
            "command_key_millisecond_value": "psetex",
            "key": "foo",
            "value": "bar",
            "millisecond": "1000",
        },
    )
    judge_command("psetex foo bar", None)


def test_bitop(judge_command):
    judge_command(
        "BITOP AND dest key1 key2",
        {
            "command_operation_key_keys": "BITOP",
            "operation": "AND",
            "key": "dest",
            "keys": "key1 key2",
        },
    )
    judge_command(
        "BITOP AND dest key1",
        {
            "command_operation_key_keys": "BITOP",
            "operation": "AND",
            "key": "dest",
            "keys": "key1",
        },
    )
    judge_command("BITOP AND dest", None)


def test_bitpos(judge_command):
    judge_command(
        "BITPOS mykey 1 3 5",
        {
            "command_key_bit_start_end": "BITPOS",
            "key": "mykey",
            "bit": "1",
            "start": "3",
            "end": "5",
        },
    )
    judge_command(
        "BITPOS mykey 1",
        {"command_key_bit_start_end": "BITPOS", "key": "mykey", "bit": "1"},
    )
    judge_command(
        "BITPOS mykey 1 3",
        {
            "command_key_bit_start_end": "BITPOS",
            "key": "mykey",
            "bit": "1",
            "start": "3",
        },
    )
