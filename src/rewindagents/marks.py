"""Marks: bookmarks in time. Drop a named point before you let an agent do something risky
(`mark before-refactor`), then jump straight back to it (`rewind-to before-refactor`) without working out a
step number. A mark is just a label for "session S, right after step N"; `rewind-to` hands that step to the
same machinery `rewind` uses, so every safety check (drift, a missing stored copy, a torn log) still applies.

Marks live in .rewindagents/marks.json -- a convenience pointer beside the log, not part of the tamper-evident
chain. They are per project and survive new steps: the step number a mark captured does not move when the agent
works on."""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from . import log, rewind

NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*$")      # a label, not a path or a number


class MarkError(rewind.RewindError):
    pass


def _store(log_path: str | Path) -> Path:
    return rewind.project_root(log_path) / ".rewindagents" / "marks.json"


def load(log_path: str | Path) -> dict:
    f = _store(log_path)
    if not f.is_file():
        return {}
    try:
        data = json.loads(f.read_text())
        return data if isinstance(data, dict) else {}
    except (ValueError, OSError):
        return {}


def _save(log_path: str | Path, data: dict) -> None:
    f = _store(log_path)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_name(f".{f.name}.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
    os.replace(tmp, f)


def set_mark(log_path: str | Path, name: str, session: str | None = None) -> dict:
    """Mark the current point of `session` (default: the session that wrote the last record)."""
    if not NAME.match(name or "") or name.isdigit():
        raise MarkError(f"'{name}' is not a usable mark name: use letters, digits, '.', '_' or '-', "
                        f"starting with a letter or digit (and not a bare number)")
    session = session or rewind.latest_session(log_path)
    if session is None:
        raise MarkError("nothing is recorded yet, so there is no point to mark")
    step = len(rewind.steps(log_path, session))
    data = load(log_path)
    data[name] = {"session": session, "step": step, "head": log.head(log_path), "created": time.time()}
    _save(log_path, data)
    return data[name]


def get(log_path: str | Path, name: str) -> dict:
    data = load(log_path)
    if name not in data:
        have = ", ".join(sorted(data)) or "none yet"
        raise MarkError(f"no mark named '{name}' (marks: {have})")
    return data[name]


def remove(log_path: str | Path, name: str) -> None:
    data = load(log_path)
    if name not in data:
        raise MarkError(f"no mark named '{name}'")
    del data[name]
    _save(log_path, data)


def listing(log_path: str | Path) -> list[dict]:
    """Every mark, newest first, each with whether its step still exists in its session."""
    data = load(log_path)
    out = []
    for name, m in data.items():
        steps = len(rewind.steps(log_path, m["session"]))
        out.append({"name": name, **m, "live": m["step"] <= steps, "session_steps": steps})
    return sorted(out, key=lambda m: m["created"], reverse=True)
