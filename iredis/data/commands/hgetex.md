Get the value of one or more fields of a given hash key and optionally set
their expiration time or time-to-live (TTL).

## Options

The `HGETEX` command supports a set of options that modify its behavior:

* `EX` *seconds* -- Set the specified expiration time, in seconds.
* `PX` *milliseconds* -- Set the specified expiration time, in milliseconds.
* `EXAT` *timestamp-seconds* -- Set the specified Unix time at which the fields will expire, in seconds.
* `PXAT` *timestamp-milliseconds* -- Set the specified Unix time at which the fields will expire, in milliseconds.
* `PERSIST` -- Remove the TTL associated with the fields.

@return

@array-reply: the values associated with the specified fields, in the same
order as they are requested. `nil` for fields that do not exist.

@examples

```cli
HSET mykey field1 "Hello" field2 "World"
HGETEX mykey EX 120 FIELDS 1 field1
HTTL mykey FIELDS 2 field1 field2
```

https://redis.io/commands/hgetex
