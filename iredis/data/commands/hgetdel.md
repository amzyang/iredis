Get and delete the value of one or more fields of a given hash key. When
the last field is deleted, the key will also be deleted.

@return

@array-reply: the values associated with the specified fields, in the same
order as they are requested. `nil` for fields that do not exist.

@examples

```cli
HSET mykey field1 "Hello" field2 "World"
HGETDEL mykey FIELDS 1 field1
HGETALL mykey
```

https://redis.io/commands/hgetdel
