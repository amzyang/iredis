Set the value of one or more fields of a given hash key, and optionally set
their expiration time or time-to-live (TTL).

## Options

The `HSETEX` command supports a set of options that modify its behavior:

* `FNX` -- Only set the fields if none of them already exist.
* `FXX` -- Only set the fields if all of them already exist.
* `EX` *seconds* -- Set the specified expiration time, in seconds.
* `PX` *milliseconds* -- Set the specified expiration time, in milliseconds.
* `EXAT` *timestamp-seconds* -- Set the specified Unix time at which the fields will expire, in seconds.
* `PXAT` *timestamp-milliseconds* -- Set the specified Unix time at which the fields will expire, in milliseconds.
* `KEEPTTL` -- Retain the TTL associated with the fields.

@return

@integer-reply: `0` if no fields were set (because of the `FNX` or `FXX`
condition); `1` if all the fields were set.

@examples

```cli
HSETEX mykey EX 300 FIELDS 2 field1 "Hello" field2 "World"
HTTL mykey FIELDS 2 field1 field2
```

https://redis.io/commands/hsetex
