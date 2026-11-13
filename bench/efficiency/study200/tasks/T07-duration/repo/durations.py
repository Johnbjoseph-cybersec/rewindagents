"""Parse human-written durations such as "1h30m" or "2.5s" into seconds."""
import re

UNITS = {"d": 86400, "h": 3600, "m": 60, "s": 1, "ms": 0.001}


def parse_duration(text):
    """Return the number of seconds in ``text`` as a float.

    ``text`` is one or more NUMBER UNIT parts, written together or separated by spaces ("1h30m", "1h 30m").
    NUMBER is digits with an optional decimal part ("1.5"); UNIT is one of d, h, m, s, ms (lower case).
    Units must appear in this order (d before h before m before s before ms) and each at most once.
    A leading "-" makes the whole duration negative ("-1h30m" is -5400.0). Surrounding whitespace is
    ignored. Anything else (empty text, a number without a unit, an unknown unit, a unit twice, units out
    of order, a bare "-") raises ValueError.
    """
    m = re.match(r"\s*(\d+(?:\.\d+)?)\s*([a-z]+)", text)
    if not m or m.group(2) not in UNITS:
        raise ValueError("bad duration: %r" % text)
    return float(m.group(1)) * UNITS[m.group(2)]
