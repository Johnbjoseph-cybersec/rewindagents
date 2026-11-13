"""Append-only, hash-chained log of agent tool calls.

Each record carries the SHA-256 of the record before it, so editing, deleting
or reordering any record breaks verification from that point on. Plain JSONL:
no server, no database.

Appends take an exclusive lock and re-read the chain head under it, so several
hook processes writing to the same log at once still produce one valid chain.

A chain alone cannot detect records cut off the END of the file. To catch that,
keep the head hash somewhere else (`rewindagents head`) and pass it to `verify`.

Torn writes. A record and its newline go to the file in one write, but a full
disk or a killed process can still cut one off, leaving a line that is not JSON
and has no newline. The next append does not stop at it: it starts on a fresh
line, chained to the last whole record, and leaves the fragment where it is
(nothing already in the file is ever rewritten). The fragment keeps its place in
the numbering, so `verify` names it - "torn write at the end of the log" while
nothing follows it, "not a valid record" once records follow - and still fails,
because the call it was recording is lost. A line that IS JSON but not a record
is not a torn write and stops the check where it is, as before.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from . import filelock

GENESIS = "0" * 64


def _digest(record: dict) -> str:
    canon = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canon.encode()).hexdigest()


def _lines(fh) -> tuple[list[bytes], bool]:
    """(every non-blank line of a binary file, whether the file ends part way through a line)."""
    fh.seek(0)
    data = fh.read()
    return [l for l in data.split(b"\n") if l.strip()], bool(data) and not data.endswith(b"\n")


def _json(raw: bytes) -> tuple[bool, Any]:
    """(parsed, value): parsed is False when the line is not UTF-8 JSON at all - what a torn write leaves."""
    try:
        return True, json.loads(raw.decode("utf-8"))
    except ValueError:              # JSONDecodeError and UnicodeDecodeError are both ValueErrors
        return False, None


def _record(raw: bytes) -> dict | None:
    ok, rec = _json(raw)
    return rec if ok and isinstance(rec, dict) and isinstance(rec.get("hash"), str) else None


def _last_hash(fh) -> tuple[str, int, bool]:
    """(hash of the last whole record, non-blank lines, file ends mid-line). A torn line keeps its number."""
    lines, cut = _lines(fh)
    last = next((r for r in map(_record, reversed(lines)) if r), None)
    return (last["hash"] if last else GENESIS), len(lines), cut


def _write_all(fd: int, data: bytes) -> None:
    while data:
        data = data[os.write(fd, data):]


class Recorder:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, session: str, tool: str, args: Any, result: Any = None,
               actor: str = "agent", event: str = "tool_call", ts: float | None = None) -> dict:
        """Append one record. `ts` defaults to now; `import` passes the original time of a moved record."""
        with self.path.open("a+b") as fh:
            filelock.acquire(fh, exclusive=True)
            try:
                prev, n, cut = _last_hash(fh)
                body = {"seq": n + 1, "ts": round(time.time() if ts is None else ts, 3), "session": session,
                        "actor": actor, "event": event, "tool": tool,
                        "args": args, "result": result, "prev": prev}
                body["hash"] = _digest(body)
                line = json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n"
                # one write for the record and its newline; after a torn write, start on a line of our own
                _write_all(fh.fileno(), (b"\n" if cut else b"") + line)
                os.fsync(fh.fileno())
            finally:
                filelock.release(fh)
        return body


def head(path: str | Path) -> str:
    p = Path(path)
    if not p.exists():
        return GENESIS
    with p.open("rb") as fh:
        return _last_hash(fh)[0]


def check(path: str | Path, expected_head: str | None = None) -> tuple[bool, int, str, bool]:
    """(ok, records_checked, message, torn_only). torn_only is True when every record verifies and chains
    and the only damage is torn lines (see the module docstring): the records are trustworthy, a call is lost."""
    prev, n, last_whole, torn = GENESIS, 0, 0, []
    with Path(path).open("rb") as fh:
        lines, cut = _lines(fh)
    for n, raw in enumerate(lines, 1):
        parsed, rec = _json(raw)
        if not parsed:
            torn.append(n)
            continue
        if not isinstance(rec, dict) or not isinstance(rec.get("hash"), str):
            return False, n, f"record {n}: not a valid record", False
        claimed = rec.pop("hash")
        if rec.get("prev") != prev:
            return False, n, f"record {n}: chain broken (prev does not match)", False
        if rec.get("seq") != n:
            return False, n, f"record {n}: sequence number is {rec.get('seq')}", False
        if _digest(rec) != claimed:
            return False, n, f"record {n}: contents altered", False
        prev, last_whole = claimed, n
    if expected_head is not None and prev != expected_head:
        return False, n, "head does not match the pinned hash (records removed from the end?)", False
    if not torn:
        return True, n, "chain intact", False
    k, more = torn[0], len(torn) - 1
    also = f" (and {more} more torn line{'s' if more != 1 else ''})" if more else ""
    if torn == [n] and cut:
        return False, n, (f"record {n}: torn write at the end of the log (cut off before its newline; "
                          f"the {last_whole} record{'s' if last_whole != 1 else ''} before it verify)"), True
    after = n - k - more
    return False, n, (f"record {k}: not a valid record (not JSON, as a torn write leaves{also}; the {after} "
                      f"record{'s' if after != 1 else ''} after it chain on intact)"), True


def verify(path: str | Path, expected_head: str | None = None) -> tuple[bool, int, str]:
    """Return (ok, records_checked, message)."""
    return check(path, expected_head)[:3]


def read(path: str | Path, session: str | None = None) -> list[dict]:
    """Every record, in order. A torn line (not a record) is skipped; `verify` is what reports it."""
    with Path(path).open("rb") as fh:
        recs = [r for r in map(_record, _lines(fh)[0]) if r]
    return [r for r in recs if session is None or r["session"] == session]
