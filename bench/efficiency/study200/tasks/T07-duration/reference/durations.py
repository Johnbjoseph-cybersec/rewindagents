"""Parse human-written durations such as "1h30m" or "2.5s" into seconds."""
import re

UNITS = {"d": 86400, "h": 3600, "m": 60, "s": 1, "ms": 0.001}
ORDER = ["d", "h", "m", "s", "ms"]
_PART = re.compile(r"(\d+(?:\.\d+)?)(ms|d|h|m|s)")


def parse_duration(text):
    t = text.strip()
    neg = t.startswith("-")
    if neg:
        t = t[1:]
    if not t:
        raise ValueError("bad duration: %r" % text)
    pos, last, total = 0, -1, 0.0
    while pos < len(t):
        if pos and t[pos] == " ":
            pos += 1
            if pos >= len(t) or t[pos] == " ":
                raise ValueError("bad duration: %r" % text)
        m = _PART.match(t, pos)
        if not m:
            raise ValueError("bad duration: %r" % text)
        k = ORDER.index(m.group(2))
        if k <= last:
            raise ValueError("bad duration: %r" % text)
        last = k
        total += float(m.group(1)) * UNITS[m.group(2)]
        pos = m.end()
    return -total if neg else total


def format_duration(seconds):
    ms = int(round(seconds * 1000))
    if ms == 0:
        return "0s"
    sign = "-" if ms < 0 else ""
    ms = abs(ms)
    out = []
    for u, size in (("d", 86400000), ("h", 3600000), ("m", 60000), ("s", 1000), ("ms", 1)):
        q, ms = divmod(ms, size)
        if q:
            out.append("%d%s" % (q, u))
    return sign + "".join(out)
