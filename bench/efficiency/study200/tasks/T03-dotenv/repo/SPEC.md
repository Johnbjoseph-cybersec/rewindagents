# envfile: dumps (planned)

`dumps(mapping)` returns .env text, one `NAME=VALUE` line per item in the mapping's order, each line ending
with `\n`, such that `parse(dumps(m)) == m` for every mapping of valid names to strings.

- A value made only of letters, digits and `_ - . / : @ ,` (and not empty) is written bare.
- Any other value is written in double quotes, escaping `\` as `\\`, `"` as `\"` and a newline as `\n`.
- An invalid name raises ValueError.
