Returns the absolute Unix timestamp in seconds since Unix epoch at which
the given hash key fields will expire.

@return

@array-reply: For each field, `-2` if no such field exists in the provided
hash key, or the provided key does not exist; `-1` if the field exists but
has no associated expiration; otherwise the expiration Unix timestamp in
seconds.

@examples

```cli
HSET mykey field1 "hello"
HEXPIRE mykey 300 FIELDS 1 field1
HEXPIRETIME mykey FIELDS 1 field1
```

https://redis.io/commands/hexpiretime
