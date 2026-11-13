# spans: subtract (planned)

`subtract(intervals, cut)` returns what is left of the union of `intervals` after removing the half-open
interval `cut` = (start, end): a list in the same form `merge()` returns (sorted, disjoint, non-adjacent, no
empty intervals). An empty `cut` removes nothing. `cut` with start > end raises ValueError, as does any such
interval in `intervals`. The input is not modified.

Example: `subtract([(0, 10)], (3, 5))` -> `[(0, 3), (5, 10)]`.
