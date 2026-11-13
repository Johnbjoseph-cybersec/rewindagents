# ttlcache: get_or_set (planned)

`cache.get_or_set(key, factory)` returns the live value for `key` if there is one (exactly like `get`,
including making it most recently used). Otherwise it calls `factory()` once, stores the result with `set`
and returns it. If `factory()` raises, the exception propagates and nothing is stored. A stored value of
`None` counts as present (the factory is not called again while it is live).
