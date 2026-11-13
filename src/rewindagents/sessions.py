"""`rewindagents sessions`: every session in a log, and the ones whose steps mention a text.

A session is whatever wrote records under one session id: Claude Code's session_id through the hook,
or the --session given to `record`. One pass over the log; the records of each session are paired into
steps exactly as `replay` pairs them, so the step numbers here are the ones `replay` and `rewind` use.

"Files touched" are the files a step checkpointed: what Write, Edit, MultiEdit, NotebookEdit, a Bash
command or a rewind changed, created or deleted. A file that was only read is not touched.

`--grep TEXT` keeps the sessions with at least one step that mentions TEXT (case-insensitive) in the
text `replay` shows for the step (the command, the file, or the input) or in a path it checkpointed.
"""
from __future__ import annotations

import time
from pathlib import Path

from . import log, rewind

SHOW_FILES = 5   # files named on a session's line; the rest are counted


def touched(steps: list[dict], root: Path | None) -> list[str]:
    """Paths (relative to the project) the steps checkpointed, in first-seen order, no repeats."""
    seen: dict[str, None] = {}
    for s in steps:
        for cp in s["checkpoints"]:
            seen.setdefault(rewind.relative(cp["path"], root), None)
    return list(seen)


def mentions(step: dict, text: str, root: Path | None) -> bool:
    """True when the step's replay line or one of its checkpointed paths contains text (any case)."""
    needle = text.lower()
    haystack = [rewind.summary(step, width=1 << 30, root=root)]
    haystack += [rewind.relative(cp["path"], root) for cp in step["checkpoints"]]
    return any(needle in h.lower() for h in haystack)


def sessions(log_path: str | Path, grep: str | None = None) -> list[dict]:
    """Every session in the log, in the order they first wrote to it.

    With grep, only the sessions with a matching step, each with its matching steps under "hits".
    Each entry: session, first and last record time (epoch seconds), steps, rewinds (rewind and branch
    steps among them), files (touched, relative to the project), hits, latest (wrote the log's last record).
    """
    recs = log.read(log_path)
    root = rewind.project_root(log_path)
    by_id: dict[str, list[dict]] = {}
    for r in recs:
        by_id.setdefault(r["session"], []).append(r)
    last_writer = recs[-1]["session"] if recs else None
    out: list[dict] = []
    for sid, srecs in by_id.items():
        steps = rewind.steps_from(srecs)
        hits = [s for s in steps if mentions(s, grep, root)] if grep else []
        if grep and not hits:
            continue
        out.append({"session": sid, "first": srecs[0]["ts"], "last": srecs[-1]["ts"], "steps": len(steps),
                    "rewinds": sum(1 for s in steps if s["event"] in ("rewind", "branch", "revert")),
                    "files": touched(steps, root), "hits": hits, "latest": sid == last_writer})
    return out


def when(ts: float) -> str:
    """A record's time as local clock time."""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def lines(entries: list[dict], root: Path | None = None, width: int = 80) -> list[str]:
    """The text `rewindagents sessions` prints for these entries."""
    out: list[str] = []
    for e in entries:
        tail = "  (latest)" if e["latest"] else ""
        rw = f" ({e['rewinds']} rewind{'s' if e['rewinds'] != 1 else ''})" if e["rewinds"] else ""
        out.append(f"{e['session']}  {when(e['first'])} to {when(e['last'])}  "
                   f"{e['steps']} steps{rw}  {len(e['files'])} files{tail}")
        if e["files"]:
            names = ", ".join(e["files"][:SHOW_FILES])
            more = len(e["files"]) - SHOW_FILES
            out.append(f"    files: {names}{f' (+{more} more)' if more > 0 else ''}")
        for s in e["hits"]:
            out.append(f"    {s['step']:>5}  {s['tool']:<12}  {rewind.summary(s, width=width, root=root)}")
    return out


class SessionError(Exception):
    pass


def resolve(log_path: str | Path, given: str) -> str:
    """The session id `given` names: an exact id, or the start of exactly one id (as a short commit hash
    names a commit; Claude Code session ids are 36-character UUIDs). Raises SessionError naming the sessions
    there are, so a typo is never answered with an empty replay."""
    recs = log.read(log_path)
    ids: list[str] = []
    for r in recs:
        if r["session"] not in ids:
            ids.append(r["session"])
    if given in ids:
        return given
    matches = [i for i in ids if i.startswith(given)]
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise SessionError(f"session {given!r} is ambiguous: it starts {len(matches)} sessions "
                           f"({', '.join(matches[:5])}{', ...' if len(matches) > 5 else ''}); type more of it")
    if not ids:
        raise SessionError(f"no session {given!r}: the log holds no records yet")
    latest = recs[-1]["session"]
    shown = list(reversed(ids))[:5]
    listed = ", ".join(f"{i} (latest)" if i == latest else i for i in shown)
    more = f" and {len(ids) - 5} more" if len(ids) > 5 else ""
    raise SessionError(f"no session {given!r} in this log. Sessions, newest first: {listed}{more}. "
                       f"`rewindagents sessions` lists them all; a unique start of an id is enough")
