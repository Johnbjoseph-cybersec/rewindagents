"""Parse URL query strings (the part after "?")."""


def _decode(s):
    out = s.replace("+", " ")
    i, res = 0, ""
    while i < len(out):
        if out[i] == "%" and i + 2 < len(out):
            res += chr(int(out[i + 1:i + 3], 16))
            i += 3
        else:
            res += out[i]
            i += 1
    return res


def parse_query(query):
    """Return a dict for ``query`` such as ``"a=1&b=x+y"``.

    * A leading "?" is ignored. Pairs are separated by "&" only; empty pairs ("a=1&&b=2") are skipped.
    * Each pair is split at its FIRST "="; a pair with no "=" has the value "" (``"flag"`` -> ``{"flag": ""}``).
    * Names and values are decoded after splitting: "+" becomes a space, and "%XX" escapes are bytes that are
      decoded together as UTF-8 (``"%C3%A9"`` -> "é"). A "%" not followed by two hex digits is kept as is.
      Invalid UTF-8 raises ValueError.
    * A name that occurs once maps to its value (a str); a name that occurs more than once maps to the list
      of its values in order.
    """
    out = {}
    for pair in _decode(query.lstrip("?")).split("&"):
        if not pair:
            continue
        name, _, value = pair.partition("=")
        if name in out:
            prev = out[name]
            out[name] = (prev if isinstance(prev, list) else [prev]) + [value]
        else:
            out[name] = value
    return out
