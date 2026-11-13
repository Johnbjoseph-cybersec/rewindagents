"""Half-open integer intervals [start, end), as (start, end) tuples."""


def merge(intervals):
    """Return the union of ``intervals`` as a sorted list of disjoint, non-adjacent (start, end) tuples.

    Intervals are half-open: (1, 3) covers 1 and 2. Overlapping intervals and intervals that touch
    ((1, 3) and (3, 5)) are merged into one. Empty intervals (start == end) cover nothing and do not appear
    in the result. The input may be in any order and may be any iterable of pairs (tuples or lists); it is
    not modified. An interval with start > end raises ValueError.
    """
    intervals.sort()
    out = []
    for s, e in intervals:
        if out and s < out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def total_length(intervals):
    """Number of integers covered by at least one interval."""
    return sum(e - s for s, e in merge(intervals))
