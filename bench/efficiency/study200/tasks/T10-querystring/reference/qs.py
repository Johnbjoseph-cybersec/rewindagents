"""Parse URL query strings (the part after "?")."""
import re

_HEX = "0123456789abcdefABCDEF"


def _decode(s):
    s = s.replace("+", " ")
    buf, i = bytearray(), 0
    while i < len(s):
        c = s[i]
        if c == "%" and i + 2 < len(s) and s[i + 1] in _HEX and s[i + 2] in _HEX:
            buf.append(int(s[i + 1:i + 3], 16))
            i += 3
        else:
            buf += c.encode("utf-8")
            i += 1
    try:
        return buf.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError(str(e))


def parse_query(query):
    if query.startswith("?"):
        query = query[1:]
    out = {}
    for pair in query.split("&"):
        if not pair:
            continue
        name, _, value = pair.partition("=")
        name, value = _decode(name), _decode(value)
        if name in out:
            prev = out[name]
            out[name] = (prev if isinstance(prev, list) else [prev]) + [value]
        else:
            out[name] = value
    return out


def _enc(s):
    out = []
    for c in s:
        if re.match(r"[A-Za-z0-9\-._~]$", c):
            out.append(c)
        elif c == " ":
            out.append("+")
        else:
            out.extend("%%%02X" % b for b in c.encode("utf-8"))
    return "".join(out)


def build_query(params):
    pairs = []
    for k, v in params.items():
        vals = [v] if isinstance(v, str) else v
        if not isinstance(vals, list) or not all(isinstance(x, str) for x in vals):
            raise TypeError("values must be str or list of str")
        pairs.extend("%s=%s" % (_enc(k), _enc(x)) for x in vals)
    return "&".join(pairs)
