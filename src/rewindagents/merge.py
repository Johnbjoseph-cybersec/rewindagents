"""A three-way merge of lines, stdlib only (the diff3 method: Khanna, Kunal and Pierce, "A Formal Investigation of
Diff3", FSTTCS 2007).

merge3(base, ours, theirs) keeps every change ours made to base and every change theirs made to base. Where both
changed the same lines differently, or changed lines with no unchanged line between them, it is a conflict.
`revert` uses it with base = a file right after step K, theirs = the file right before step K, ours = the file
now, so the result is the file now without step K's change.

It is not `git merge-file` and does not call it: the result must not depend on whether git is installed or on
its version. Like git, it diffs with a shortest edit script (Myers) after trimming the common start and end, and
treats changes on the same or adjacent lines as a conflict. git adds heuristics on top that slide a change among
repeated lines; where lines repeat a lot, the two can pair them differently. bench/merge_vs_git.py measures it:
against git 2.50.1, on 1,000 random three-way inputs built from only three distinct lines (seeds 7, 8, 9), 71.9-74.3%
merged cleanly in both with the same bytes, 23.1-25.7% were a conflict in both, 0.9-1.6% a conflict only here
(revert refuses), 1.0-1.1% only in git, and 0.1-0.4% merged cleanly in both with different bytes. On inputs whose
base lines are all different they agreed in all 300 cases of tests/test_revert.py.
"""
from __future__ import annotations

class Conflict(Exception):
    """Both sides changed the same lines. `hunks` lists (base_start, base_end) line ranges, 1-based, inclusive
    start, for the message ("lines 3-4"); an insertion at the same place is (n, n-1)."""

    def __init__(self, hunks: list[tuple[int, int]]):
        super().__init__(f"{len(hunks)} conflicting hunk(s)")
        self.hunks = hunks


class TooBig(Conflict):
    """One side differs from base in more than MAX_EDITS lines: not merged (treated as a conflict), because the
    shortest diff that far out costs too much time and memory to find and any other diff can pair up repeated
    lines the wrong way."""

    def __init__(self):
        Exception.__init__(self, f"more than {MAX_EDITS} changed lines on one side")
        self.hunks = []


MAX_EDITS = 2000


def lines(data: bytes) -> list[bytes]:
    """Lines with their endings kept, so joining them gives the bytes back exactly. Only \\n ends a line
    (a \\r\\n file keeps the \\r on each line, so endings merge as content)."""
    out = data.split(b"\n")
    tail = out.pop()
    out = [ln + b"\n" for ln in out]
    if tail:
        out.append(tail)
    return out


def _matches(base: list[bytes], other: list[bytes]) -> dict[int, int]:
    """base line index -> other line index for the lines a shortest diff keeps (Myers, "An O(ND) Difference
    Algorithm and Its Variations", 1986; git's default), after taking off the common start and end as git does.
    A shortest diff matters: with repeated lines (blank lines, closing braces) a longest-block diff such as
    difflib's can pair a line with the wrong copy of itself and the merge then drops or doubles a change."""
    n, m = len(base), len(other)
    lo = 0
    while lo < n and lo < m and base[lo] == other[lo]:
        lo += 1
    hi = 0
    while hi < n - lo and hi < m - lo and base[n - 1 - hi] == other[m - 1 - hi]:
        hi += 1
    out = {i: i for i in range(lo)}
    out.update({n - hi + d: m - hi + d for d in range(hi)})
    ids: dict[bytes, int] = {}
    a = [ids.setdefault(x, len(ids)) for x in base[lo:n - hi]]
    b = [ids.setdefault(x, len(ids)) for x in other[lo:m - hi]]
    for i, j in _myers(a, b):
        out[lo + i] = lo + j
    return out


def _myers(a: list[int], b: list[int]) -> list[tuple[int, int]]:
    """The (i, j) pairs a shortest edit script from a to b keeps. Raises TooBig past MAX_EDITS edits."""
    n, m = len(a), len(b)
    if not n or not m:
        return []
    v: dict[int, int] = {1: 0}
    trace: list[dict[int, int]] = []
    for d in range(n + m + 1):
        if d > MAX_EDITS:
            raise TooBig()
        trace.append(dict(v))
        for k in range(-d, d + 1, 2):
            if k == -d or (k != d and v[k - 1] < v[k + 1]):
                x = v[k + 1]
            else:
                x = v[k - 1] + 1
            y = x - k
            while x < n and y < m and a[x] == b[y]:
                x, y = x + 1, y + 1
            v[k] = x
            if x >= n and y >= m:
                return _back(trace, n, m)
    return []                      # not reached: d = n + m always ends it


def _back(trace: list[dict[int, int]], x: int, y: int) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    for d in range(len(trace) - 1, -1, -1):
        v, k = trace[d], x - y
        pk = k + 1 if (k == -d or (k != d and v[k - 1] < v[k + 1])) else k - 1
        px = v[pk]
        py = px - pk
        while x > px and y > py:
            x, y = x - 1, y - 1
            pairs.append((x, y))
        x, y = px, py
    return pairs


def merge3(base: bytes, ours: bytes, theirs: bytes) -> bytes:
    """The merged bytes, or raises Conflict. A side that equals base yields the other side unchanged."""
    if ours == base or ours == theirs:
        return theirs
    if theirs == base:
        return ours
    o, a, b = lines(base), lines(ours), lines(theirs)
    ma, mb = _matches(o, a), _matches(o, b)
    out: list[bytes] = []
    hunks: list[tuple[int, int]] = []
    i = j = k = 0                       # next line of base, ours, theirs
    while True:
        # the stable run: base lines matched to the next line on both sides, in step
        n = 0
        while i + n < len(o) and ma.get(i + n) == j + n and mb.get(i + n) == k + n:
            n += 1
        if n:
            out.extend(o[i:i + n])
            i, j, k = i + n, j + n, k + n
            continue
        # an unstable chunk: up to the next base line both sides still have, at or after where each side is
        nxt = next((x for x in range(i, len(o))
                    if x in ma and x in mb and ma[x] >= j and mb[x] >= k), None)
        if nxt is None:
            ci, cj, ck = len(o), len(a), len(b)
        else:
            ci, cj, ck = nxt, ma[nxt], mb[nxt]
        if (ci, cj, ck) == (i, j, k):   # nothing left on any side
            break
        oc, ac, bc = o[i:ci], a[j:cj], b[k:ck]
        if ac == oc:
            out.extend(bc)              # only theirs changed it
        elif bc == oc or ac == bc:
            out.extend(ac)              # only ours changed it, or both the same way
        else:
            hunks.append((i + 1, ci))
        i, j, k = ci, cj, ck
        if nxt is None:
            break
    if hunks:
        raise Conflict(hunks)
    return b"".join(out)
