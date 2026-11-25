"""Which agent step wrote this line? `blame FILE` (or `blame FILE:LINE`) rebuilds every version of one file
the session recorded -- the copy saved before the first step that touched it, then the copy saved after each
step that changed it -- and carries each line forward through a line diff, the way `git blame` walks commits.
The last version is then compared with the file on disk, so a line someone changed after the agent shows as
"not from a recorded step". Read only.

A line is attributed to the step whose saved copy first held it; a line already there before the session's
first change to the file is "before the session". A version whose stored copy is missing or is not text stops
the walk with a reason instead of guessing."""
from __future__ import annotations

import difflib
from pathlib import Path

from . import rewind

BEFORE = 0          # attribution for lines the file held before the session first changed it
HAND = -1           # attribution for lines that differ from the last recorded version (changed after it)
_PENDING = object()  # a version whose bytes are only known from the next step's before-copy


class BlameError(rewind.RewindError):
    pass


def _lines(data: bytes | None) -> list[str] | None:
    """The text's lines (keeping their endings), [] for an absent file, None for binary content."""
    if data is None:
        return []
    if b"\x00" in data[:8192]:
        return None
    return data.decode("utf-8", "replace").splitlines(keepends=True)


def versions(log_path, path, session: str | None = None) -> tuple[list[tuple[int, dict, bytes | None]], str]:
    """[(step, step dict or {}, bytes or None when absent)] for `path`, oldest first; the first entry is the
    state before the first step that changed it (step 0 = before the session). Returns (versions, target)."""
    target = str(Path(path).resolve())

    def same(p) -> bool:          # the log may hold /var/... where resolve() gives /private/var/... (macOS)
        return bool(p) and (p == target or str(Path(p).resolve()) == target)

    objects = rewind.project_root(log_path) / ".rewindagents" / "objects"

    def read(sha):
        if sha is None:
            return None
        f = objects / sha
        if not f.is_file():
            raise BlameError(f"the stored copy {sha[:12]} of {path} is missing, so its history cannot be rebuilt")
        return f.read_bytes()

    out: list[tuple[int, dict, bytes | None]] = []
    for s in rewind.steps(log_path, session):
        cp = next((c for c in s.get("checkpoints") or [] if same(c.get("path"))), None)
        after = next((e for e in s.get("after") or [] if same(e.get("path"))), None)
        if cp is None and after is None:
            continue
        for e in (cp, after):
            if e is not None and e.get("skipped"):
                raise BlameError(f"step {s['step']} did not store {path} ({e['skipped']})")
        if not out:
            out.append((BEFORE, {}, read(cp.get("sha256")) if cp is not None else None))
        if after is not None:
            out.append((s["step"], s, read(after.get("after"))))
        else:   # a step with a before copy but no after entry: its result is the next step's before copy
            out.append((s["step"], s, _PENDING))
    # fill pending versions from the next step's before-copy of the file, or the last from the file on disk
    fixed: list[tuple[int, dict, bytes | None]] = []
    steps_list = rewind.steps(log_path, session)
    for n, s, data in out:
        if data is _PENDING:
            nxt = None
            for t in steps_list[n:]:
                c = next((c for c in t.get("checkpoints") or [] if same(c.get("path"))), None)
                if c is not None:
                    nxt = read(c.get("sha256"))
                    break
            else:
                p = Path(target)
                nxt = p.read_bytes() if p.is_file() else None
            data = nxt
        fixed.append((n, s, data))
    return fixed, target


def blame(log_path, path, session: str | None = None) -> dict:
    """{"lines": [(attribution, text)], "steps": {n: step}, "target": path, "last_step": n or None,
    "absent": bool}. attribution: a step number, BEFORE (0) or HAND (-1)."""
    vers, target = versions(log_path, path, session)
    p = Path(target)
    now = p.read_bytes() if p.is_file() else None
    if not vers:
        raise BlameError(f"no recorded step changed {path}; `history {path}` lists the steps that did")
    lines = None
    attr: list[int] = []
    steps: dict[int, dict] = {}
    seen: dict[bytes | None, list[int]] = {}     # a version's exact bytes -> the attribution it had
    for n, s, data in vers + [(HAND, {}, now)]:
        cur = _lines(data)
        if cur is None:
            raise BlameError(f"{path} is not text at step {n if n > 0 else 'before the session'}")
        if s:
            steps[n] = s
        if lines is None:
            lines, attr = cur, [n] * len(cur)
            seen[data] = attr
            continue
        if data in seen:      # an undo/rewind put back an earlier version: keep who wrote it originally
            lines, attr = cur, list(seen[data])
            continue
        new_attr: list[int] = []
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, lines, cur, autojunk=False).get_opcodes():
            if op == "equal":
                new_attr.extend(attr[i1:i2])
            elif op in ("replace", "insert"):
                new_attr.extend([n] * (j2 - j1))
        lines, attr = cur, new_attr
        seen[data] = attr
    last = max((n for n, _, _ in vers if n > 0), default=None)
    return {"lines": list(zip(attr, lines)), "steps": steps, "target": target, "last_step": last,
            "absent": now is None}
