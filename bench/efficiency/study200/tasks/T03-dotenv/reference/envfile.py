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


def _bad(no, why):
    return ValueError("line %d: %s" % (no, why))


def parse(text):
    """Return a dict of the assignments in ``text``."""
    out = {}
    for no, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"export\s+", line)
        if m:
            line = line[m.end():]
        name, sep, rest = line.partition("=")
        name = name.strip()
        if not sep or not _NAME.match(name):
            raise _bad(no, "not an assignment")
        rest = rest.lstrip()
        if rest[:1] == "'":
            end = rest.find("'", 1)
            if end == -1:
                raise _bad(no, "unterminated quote")
            value, tail = rest[1:end], rest[end + 1:]
        elif rest[:1] == '"':
            buf, i = [], 1
            while True:
                if i >= len(rest):
                    raise _bad(no, "unterminated quote")
                c = rest[i]
                if c == "\\" and i + 1 < len(rest) and rest[i + 1] in 'n"\\':
                    buf.append("\n" if rest[i + 1] == "n" else rest[i + 1])
                    i += 2
                    continue
                if c == '"':
                    break
                buf.append(c)
                i += 1
            value, tail = "".join(buf), rest[i + 1:]
        else:
            m = re.search(r"(^|\s)#", rest)
            value = (rest[:m.start()] if m else rest).rstrip()
            tail = ""
        tail = tail.strip()
        if tail and not tail.startswith("#"):
            raise _bad(no, "text after closing quote")
        out[name] = value
    return out


_BARE = re.compile(r"[A-Za-z0-9_\-./:@,]+$")


def dumps(mapping):
    lines = []
    for k, v in mapping.items():
        if not _NAME.match(k):
            raise ValueError("bad name: %r" % k)
        if _BARE.match(v):
            lines.append("%s=%s\n" % (k, v))
        else:
            e = v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            lines.append('%s="%s"\n' % (k, e))
    return "".join(lines)
