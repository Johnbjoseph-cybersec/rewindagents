"""One file's track through time. `history app.py` answers "when did this file get created, changed or
deleted, and by which step" -- the forensic view you reach for when an agent broke one file over several steps
and you want to scrub back to the version that worked. Read only; it points at `rewind N --only FILE` to put a
version back, so it adds no new restore path of its own."""
from __future__ import annotations

from pathlib import Path

from . import rewind


def file_history(log_path, path, session: str | None = None) -> tuple[list[dict], str]:
    """Every step that touched `path`, oldest first. Each row: step, tool, the kind of change, and the step's
    one-line summary. Returns (rows, the absolute path it traced)."""
    target = str(Path(path).resolve())

    def same(p) -> bool:          # the log may hold /var/... where resolve() gives /private/var/... (macOS)
        return bool(p) and (p == target or str(Path(p).resolve()) == target)

    rows: list[dict] = []
    for s in rewind.steps(log_path, session):
        cp = next((c for c in s.get("checkpoints") or [] if same(c.get("path"))), None)
        after = next((e for e in s.get("after") or [] if same(e.get("path"))), None)
        if cp is None and after is None:
            continue
        if cp is not None and cp.get("skipped"):
            change = "changed (too big to checkpoint)"
        elif cp is not None and cp.get("sha256") is None and (after is None or after.get("after") is not None):
            change = "created"
        elif after is not None and after.get("after") is None:
            change = "deleted"
        else:
            change = "modified"
        rows.append({"step": s["step"], "tool": s["tool"], "change": change, "summary": rewind.summary(s)})
    return rows, target
