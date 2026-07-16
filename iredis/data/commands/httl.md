Returns the remaining TTL (time to live) of one or more hash key fields, in
seconds.

@return

@array-reply: For each field, `-2` if no such field exists in the provided
hash key, or the provided key does not exist; `-1` if the field exists but
has no associated expiration; otherwise the TTL in seconds.

@examples

```cli
HSET mykey field1 "hello"
HEXPIRE mykey 300 FIELDS 1 field1
HTTL mykey FIELDS 1 field1
```

https://redis.io/commands/httl
