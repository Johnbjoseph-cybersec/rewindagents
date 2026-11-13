# globmatch: filter_paths (planned)

`filter_paths(patterns, paths)` returns the paths (in their original order) that are selected by a list of
patterns, gitignore-style:

- a path starts NOT selected; the patterns are applied in order and the LAST pattern that matches the path
  decides;
- a pattern starting with `!` is a negation: when it is the last match, the path is NOT selected
  (the `!` is not part of the pattern);
- a pattern starting with `\!` matches a literal leading `!` (the backslash is dropped);
- empty patterns and patterns starting with `#` are ignored.

Matching uses `match()`.
