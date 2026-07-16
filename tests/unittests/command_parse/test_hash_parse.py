def test_hdel(judge_command):
    judge_command("HDEL foo bar", {"command": "HDEL", "key": "foo", "fields": "bar"})
    judge_command(
        "HDEL foo bar hello world",
        {"command": "HDEL", "key": "foo", "fields": "bar hello world"},
    )


def test_hmset(judge_command):
    judge_command(
        "HMSET foo bar hello-world",
        {"command": "HMSET", "key": "foo", "field": "bar", "value": "hello-world"},
    )
    judge_command(
        "HMSET foo bar hello-world key2 value2",
        {"command": "HMSET", "key": "foo", "field": "key2", "value": "value2"},
    )


def test_hexists(judge_command):
    judge_command(
        "HEXISTS foo bar", {"command": "HEXISTS", "key": "foo", "field": "bar"}
    )
    judge_command("HEXISTS foo bar hello-world", None)


def test_hincrby(judge_command):
    judge_command(
        "HINCRBY foo bar 12",
        {"command": "HINCRBY", "key": "foo", "field": "bar", "delta": "12"},
    )


def test_hincrbyfloat(judge_command):
    judge_command(
        "HINCRBYFLOAT foo bar 12.1",
        {"command": "HINCRBYFLOAT", "key": "foo", "field": "bar", "float": "12.1"},
    )


def test_hset(judge_command):
    judge_command(
        "HSET foo bar hello",
        {"command": "HSET", "key": "foo", "field": "bar", "value": "hello"},
    )


def test_hrandfield(judge_command):
    judge_command(
        "HRANDFIELD coin",
        {"command": "HRANDFIELD", "key": "coin"},
    )
    judge_command(
        "HRANDFIELD coin -5 WITHVALUES",
        {
            "command": "HRANDFIELD",
            "key": "coin",
            "count": "-5",
            "withvalues_const": "WITHVALUES",
        },
    )
    judge_command(
        "HRANDFIELD coin -5",
        {"command": "HRANDFIELD", "key": "coin", "count": "-5"},
    )
    judge_command("HRANDFIELD coin WITHVALUES", None)


def test_hexpire(judge_command):
    judge_command(
        "HEXPIRE mykey 300 FIELDS 2 field1 field2",
        {
            "command": "HEXPIRE",
            "key": "mykey",
            "second": "300",
            "fields_const": "FIELDS",
            "count": "2",
            "fields": "field1 field2",
        },
    )
    judge_command(
        "HEXPIRE mykey 300 NX FIELDS 1 field1",
        {
            "command": "HEXPIRE",
            "key": "mykey",
            "second": "300",
            "expire_condition": "NX",
            "fields_const": "FIELDS",
            "count": "1",
            "fields": "field1",
        },
    )
    judge_command(
        "HEXPIRE mykey 300 GT FIELDS 1 field1",
        {"command": "HEXPIRE", "expire_condition": "GT"},
    )
    # FIELDS block is mandatory
    judge_command("HEXPIRE mykey 300", None)
    # conditions are mutually exclusive
    judge_command("HEXPIRE mykey 300 NX XX FIELDS 1 field1", None)


def test_hpexpire(judge_command):
    judge_command(
        "HPEXPIRE mykey 60000 LT FIELDS 1 field1",
        {
            "command": "HPEXPIRE",
            "key": "mykey",
            "millisecond": "60000",
            "expire_condition": "LT",
            "fields_const": "FIELDS",
            "count": "1",
            "fields": "field1",
        },
    )
    judge_command("HPEXPIRE mykey FIELDS 1 field1", None)


def test_hexpireat(judge_command):
    judge_command(
        "HEXPIREAT mykey 1735689600 XX FIELDS 1 field1",
        {
            "command": "HEXPIREAT",
            "key": "mykey",
            "timestamp": "1735689600",
            "expire_condition": "XX",
            "fields_const": "FIELDS",
            "count": "1",
            "fields": "field1",
        },
    )


def test_hpexpireat(judge_command):
    judge_command(
        "HPEXPIREAT mykey 1735689600000 FIELDS 1 field1",
        {
            "command": "HPEXPIREAT",
            "key": "mykey",
            "timestampms": "1735689600000",
            "fields_const": "FIELDS",
            "count": "1",
            "fields": "field1",
        },
    )


def test_httl_family(judge_command):
    for command in [
        "HTTL",
        "HPTTL",
        "HEXPIRETIME",
        "HPEXPIRETIME",
        "HPERSIST",
        "HGETDEL",
    ]:
        judge_command(
            f"{command} mykey FIELDS 2 field1 field2",
            {
                "command": command,
                "key": "mykey",
                "fields_const": "FIELDS",
                "count": "2",
                "fields": "field1 field2",
            },
        )
        judge_command(f"{command} mykey field1", None)


def test_hgetex(judge_command):
    judge_command(
        "HGETEX mykey FIELDS 1 field1",
        {
            "command": "HGETEX",
            "key": "mykey",
            "fields_const": "FIELDS",
            "count": "1",
            "fields": "field1",
        },
    )
    judge_command(
        "HGETEX mykey EX 120 FIELDS 1 field1",
        {
            "command": "HGETEX",
            "key": "mykey",
            "expiration": "EX",
            "millisecond": "120",
            "fields_const": "FIELDS",
            "count": "1",
            "fields": "field1",
        },
    )
    judge_command(
        "HGETEX mykey PERSIST FIELDS 1 field1",
        {
            "command": "HGETEX",
            "key": "mykey",
            "persist_const": "PERSIST",
            "fields_const": "FIELDS",
            "count": "1",
            "fields": "field1",
        },
    )
    # expiration options are mutually exclusive
    judge_command("HGETEX mykey EX 5 PERSIST FIELDS 1 field1", None)


def test_hsetex(judge_command):
    judge_command(
        "HSETEX mykey FIELDS 1 field1 value1",
        {
            "command": "HSETEX",
            "key": "mykey",
            "fields_const": "FIELDS",
            "count": "1",
            "field": "field1",
            "value": "value1",
        },
    )
    judge_command(
        "HSETEX mykey FNX EX 300 FIELDS 2 field1 value1 field2 value2",
        {
            "command": "HSETEX",
            "key": "mykey",
            "fnx_fxx": "FNX",
            "expiration": "EX",
            "millisecond": "300",
            "fields_const": "FIELDS",
            "count": "2",
            "field": "field2",
            "value": "value2",
        },
    )
    judge_command(
        "HSETEX mykey KEEPTTL FIELDS 1 field1 value1",
        {
            "command": "HSETEX",
            "key": "mykey",
            "keepttl": "KEEPTTL",
            "fields_const": "FIELDS",
            "count": "1",
            "field": "field1",
            "value": "value1",
        },
    )
    # FNX/FXX are mutually exclusive
    judge_command("HSETEX mykey FNX FXX FIELDS 1 field1 value1", None)
    # field without value doesn't match
    judge_command("HSETEX mykey FIELDS 1 field1", None)


def test_getex_persist(judge_command):
    judge_command(
        "GETEX mykey PERSIST",
        {"command": "GETEX", "key": "mykey", "persist_const": "PERSIST"},
    )
