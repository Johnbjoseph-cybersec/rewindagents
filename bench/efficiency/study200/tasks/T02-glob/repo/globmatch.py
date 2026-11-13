"""Match "/"-separated relative paths against gitignore-like glob patterns.

Pattern syntax (the whole path must match; matching is case-sensitive):

* ``?`` matches exactly one character other than "/";
* ``*`` matches any run of characters (possibly empty) that contains no "/";
* ``[abc]``, ``[a-z]`` and ``[!abc]`` match one character (other than "/") in / not in the set;
* ``**`` as a whole path segment matches zero or more whole segments: ``**/x`` matches ``x`` and ``a/b/x``;
  ``a/**`` matches everything under ``a`` (but not ``a`` itself); ``a/**/b`` matches ``a/b`` and ``a/x/y/b``.
  ``**`` that is not a whole segment (``a**b``) behaves like ``*``.
* every other character matches itself (``.`` is not special).
"""
import re


def _translate(pattern):
    out = []
    i, n = 0, len(pattern)
    while i < n:
        c = pattern[i]
        if c == "*":
            if pattern[i:i + 2] == "**":
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        elif c == "[":
            j = pattern.find("]", i + 1)
            if j == -1:
                out.append(re.escape(c))
            else:
                body = pattern[i + 1:j]
                if body.startswith("!"):
                    body = "^" + body[1:]
                out.append("[" + body + "]")
                i = j
        else:
            out.append(re.escape(c))
        i += 1
    return "".join(out)


def match(pattern, path):
    """True if the whole of ``path`` matches ``pattern``."""
    return re.fullmatch(_translate(pattern), path) is not None
