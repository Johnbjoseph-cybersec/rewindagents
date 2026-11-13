"""A three-way merge of lines, stdlib only (the diff3 method: Khanna, Kunal and Pierce, "A Formal Investigation of
Diff3", FSTTCS 2007).

merge3(base, ours, theirs) keeps every change ours made to base and every change theirs made to base. Where both
changed the same lines differently, or changed lines with no unchanged line between them, it is a conflict.
`revert` uses it with base = a file right after step K, theirs = the file right before step K, ours = the file
now, so the result is the file now without step K's change.

It is not `git merge-file` and does not call it: the result must not depend on whether git is installed or on
its version. Like git, it treats a change touching both sides of a line that the other side also changed as a
conflict; it does not try to be cleverer than that.
"""
from __future__ import annotations

from difflib import SequenceMatcher


class Conflict(Exception):
    """Both sides changed the same lines. `hunks` lists (base_start, base_end) line ranges, 1-based, inclusive
    start, for the message ("lines 3-4"); an insertion at the same place is (n, n-1)."""

    def __init__(self, hunks: list[tuple[int, int]]):
        super().__init__(f"{len(hunks)} conflicting hunk(s)")
        self.hunks = hunks


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
    """base line index -> other line index, for every line the longest-matching-blocks diff pairs up."""
    out: dict[int, int] = {}
    for a, b, n in SequenceMatcher(None, base, other, autojunk=False).get_matching_blocks():
        for d in range(n):
            out[a + d] = b + d
    return out


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
