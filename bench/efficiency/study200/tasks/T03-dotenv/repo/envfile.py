"""Read .env files.

Rules, one assignment per line:

* blank lines and lines whose first non-space character is ``#`` are skipped;
* an optional ``export`` keyword (followed by whitespace) before the name is ignored;
* ``NAME=VALUE``; spaces around the name and around ``=`` are ignored; NAME is letters, digits and ``_``,
  not starting with a digit (anything else: ValueError naming the line number, counted from 1);
* an unquoted value ends at the first `` #`` (a ``#`` preceded by whitespace starts a comment); trailing
  whitespace is stripped; ``a#b`` keeps its ``#``;
* a value in single quotes is taken literally up to the closing quote;
* a value in double quotes may contain ``\\n`` (newline), ``\\"``, and ``\\\\`` escapes, and ``#``;
  any other backslash is kept as is;
* after a closing quote only whitespace or a comment may follow (else ValueError naming the line);
* a later assignment of the same NAME overrides an earlier one.
"""
import re

_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*$")


def parse(text):
    """Return a dict of the assignments in ``text``."""
    out = {}
    for no, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:]
        if "#" in line:
            line = line[:line.index("#")]
        name, sep, value = line.partition("=")
        name = name.strip()
        if not sep or not _NAME.match(name):
            raise ValueError("line %d: not an assignment" % no)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        out[name] = value
    return out
