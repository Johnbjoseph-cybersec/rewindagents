Issue #77: an encoded `&` in a value is treated as a separator

`parse_query("q=rock%26roll&n=1")` returns `{"q": "rock", "roll": "", "n": "1"}`. The value should be
`"rock&roll"`. Non-ASCII values come out garbled too (`"%C3%A9"` gives `"Ã©"`). The docstring describes the
intended behaviour; please make `parse_query` follow it.
