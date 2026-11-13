"""Half-open integer intervals [start, end), as (start, end) tuples."""


def merge(intervals):
    items = []
    for s, e in intervals:
        if s > e:
            raise ValueError("start > end: %r" % ((s, e),))
        if s < e:
            items.append((s, e))
    items.sort()
    out = []
    for s, e in items:
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def total_length(intervals):
    return sum(e - s for s, e in merge(intervals))


def subtract(intervals, cut):
    cs, ce = cut
    if cs > ce:
        raise ValueError("start > end")
    out = []
    for s, e in merge(intervals):
        if cs >= ce or ce <= s or cs >= e:
            out.append((s, e))
            continue
        if s < cs:
            out.append((s, cs))
        if ce < e:
            out.append((ce, e))
    return merge(out)
