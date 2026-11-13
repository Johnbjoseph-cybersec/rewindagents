"""Money helpers. Amounts are integers in cents."""


def allocate(total, weights):
    weights = list(weights)
    if not weights or any(not isinstance(w, int) or w < 0 for w in weights) or not any(weights):
        raise ValueError("weights must be non-negative integers, at least one positive")
    if total < 0:
        return [-x for x in allocate(-total, weights)]
    s = sum(weights)
    base = [total * w // s for w in weights]
    rems = [total * w % s for w in weights]
    left = total - sum(base)
    order = sorted(range(len(weights)), key=lambda i: (-rems[i], i))
    for i in order[:left]:
        base[i] += 1
    return base


def format_cents(cents, symbol="$"):
    if type(cents) is not int:
        raise TypeError("cents must be an int")
    sign = "-" if cents < 0 else ""
    a = abs(cents)
    return "%s%s%s.%02d" % (sign, symbol, "{:,}".format(a // 100), a % 100)
