Issue #52: the cache serves expired values

After `ttl` seconds an entry should be gone, but `get` still returns it, and every `get` seems to keep it
alive for longer. The class docstring describes how expiry, recency and capacity are supposed to interact;
the implementation does not follow it.
