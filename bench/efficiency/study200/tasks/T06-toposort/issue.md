Issue #23: dependency cycles are accepted silently

`toposort({"a": ["b"], "b": ["a"]})` returns `["b", "a"]` instead of raising CycleError, so our build starts
in an impossible order. Also, the order we get changes when the dict is built in a different order, but the
docstring promises a deterministic order. Please make `toposort` do what its docstring says.
