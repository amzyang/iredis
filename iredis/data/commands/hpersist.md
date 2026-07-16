Remove the existing expiration on one or more hash key fields, turning the
fields from volatile (fields with expiration) to persistent (fields that
will never expire as no TTL is associated).

@return

@array-reply: For each field, `-2` if no such field exists in the provided
hash key, or the provided key does not exist; `-1` if the field exists but
has no associated expiration; `1` if the expiration was removed.

@examples

```cli
HSET mykey field1 "hello"
HEXPIRE mykey 300 FIELDS 1 field1
HPERSIST mykey FIELDS 1 field1
HTTL mykey FIELDS 1 field1
```

https://redis.io/commands/hpersist
