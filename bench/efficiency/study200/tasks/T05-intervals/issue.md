Issue #19: merge() keeps touching intervals apart

`merge([(1, 3), (3, 5)])` returns `[(1, 3), (3, 5)]`; for half-open intervals that is one span, `(1, 5)`.
The docstring of `merge` says what it should return. While there: we call it from several places, so it has
to behave exactly as documented.
