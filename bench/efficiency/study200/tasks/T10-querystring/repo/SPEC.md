# qs: build_query (planned)

`build_query(params)` is the inverse of `parse_query`: it takes a dict whose values are strings or lists of
strings and returns a query string (no leading "?") such that `parse_query(build_query(p)) == p` whenever
every list has at least two items.

- Pairs are written in the dict's order; a list value writes one `name=value` pair per item, in order.
- Letters, digits and `- . _ ~` are written as they are; a space is written as `+`; every other character is
  UTF-8 encoded and written as `%XX` with upper-case hex digits. Names are encoded the same way.
- An empty list writes nothing; any value that is neither a str nor a list of str raises TypeError.
