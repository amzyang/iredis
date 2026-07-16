import os  # noqa: F401

import pytest
from packaging.version import parse as version_parse  # noqa: F401

pytestmark = pytest.mark.skipif(
    "version_parse(os.environ['REDIS_VERSION']) < version_parse('7.4')"
)


def test_hexpire_and_httl(clean_redis, cli):
    cli.sendline("hset foo f1 v1")
    cli.expect("1")

    cli.sendline("hexpire foo 100 FIELDS 1 f1")
    cli.expect('"1"')

    cli.sendline("httl foo FIELDS 1 f1")
    cli.expect(r'"\d+"')

    cli.sendline("hpersist foo FIELDS 1 f1")
    cli.expect('"1"')

    cli.sendline("httl foo FIELDS 1 f1")
    cli.expect('"-1"')


def test_hexpire_on_missing_field(clean_redis, cli):
    cli.sendline("hexpire nonexist 100 FIELDS 1 f1")
    cli.expect('"-2"')


@pytest.mark.skipif("version_parse(os.environ['REDIS_VERSION']) < version_parse('8')")
def test_hgetdel(clean_redis, cli):
    cli.sendline("hset foo f1 v1 f2 v2")
    cli.expect("2")

    cli.sendline("hgetdel foo FIELDS 1 f1")
    cli.expect('"v1"')

    cli.sendline("hget foo f1")
    cli.expect("(nil)")


@pytest.mark.skipif("version_parse(os.environ['REDIS_VERSION']) < version_parse('8')")
def test_hsetex(clean_redis, cli):
    cli.sendline("hsetex foo EX 300 FIELDS 1 f1 v1")
    cli.expect("1")

    cli.sendline("httl foo FIELDS 1 f1")
    cli.expect(r'"\d+"')
