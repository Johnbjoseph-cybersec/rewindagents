Issue #7: allocate() loses (or invents) cents

`allocate(100, [1, 1, 1])` returns `[33, 33, 33]`, which adds up to 99. Splitting an invoice must never lose
or create a cent. The docstring of `allocate` describes the intended behaviour; please make it do that.
