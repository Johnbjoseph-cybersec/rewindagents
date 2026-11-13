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


def _segment(seg):
    out = []
    i, n = 0, len(seg)
    while i < n:
        c = seg[i]
        if c == "*":
            while i + 1 < n and seg[i + 1] == "*":
                i += 1
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        elif c == "[":
            j = seg.find("]", i + 1)
            if j == -1:
                out.append(re.escape(c))
            else:
                body = seg[i + 1:j]
                neg = body.startswith("!")
                if neg:
                    body = body[1:]
                body = body.replace("\\", "\\\\")
                out.append("(?!/)[" + ("^" if neg else "") + body + "]")
                i = j
        else:
            out.append(re.escape(c))
        i += 1
    return "".join(out)


def _translate(pattern):
    segs = pattern.split("/")
    out = ""
    for k, seg in enumerate(segs):
        last = k == len(segs) - 1
        if seg == "**":
            if last:
                out += "[^/]+(?:/[^/]+)*" if k == 0 else "[^/]+(?:/[^/]+)*"
            else:
                out += "(?:[^/]+/)*"
        else:
            out += _segment(seg) + ("" if last else "/")
    return out


def match(pattern, path):
    """True if the whole of ``path`` matches ``pattern``."""
    return re.fullmatch(_translate(pattern), path) is not None


def filter_paths(patterns, paths):
    rules = []
    for p in patterns:
        if not p or p.startswith("#"):
            continue
        if p.startswith("!"):
            rules.append((False, p[1:]))
        elif p.startswith("\\!"):
            rules.append((True, p[1:]))
        else:
            rules.append((True, p))
    out = []
    for path in paths:
        sel = False
        for keep, pat in rules:
            if match(pat, path):
                sel = keep
        if sel:
            out.append(path)
    return out
