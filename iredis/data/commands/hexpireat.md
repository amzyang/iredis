Set an expiration (TTL) on one or more fields of a given hash key, as an
absolute Unix timestamp in seconds since Unix epoch. A timestamp in the past
deletes the field immediately.

## Options

The `HEXPIREAT` command supports a set of options that modify its behavior:

* `NX` -- For each specified field, set expiration only when the field has no expiration.
* `XX` -- For each specified field, set expiration only when the field has an existing expiration.
* `GT` -- For each specified field, set expiration only when the new expiration is greater than current one.
* `LT` -- For each specified field, set expiration only when the new expiration is less than current one.

@return

@array-reply: For each field, `-2` if no such field exists in the provided
hash key, or the provided key does not exist; `0` if the specified `NX`,
`XX`, `GT`, or `LT` condition has not been met; `1` if the expiration time
was set or updated; `2` when the field is deleted because the provided
expiration time is in the past.

@examples

```cli
HSET mykey field1 "hello"
HEXPIREAT mykey 1735689600 FIELDS 1 field1
HTTL mykey FIELDS 1 field1
```

https://redis.io/commands/hexpireat
