"""Append-only, hash-chained log of agent tool calls.

Each record carries the SHA-256 of the record before it, so editing, deleting
or reordering any record breaks verification from that point on. Plain JSONL:
no server, no database.

Appends take an exclusive lock and re-read the chain head under it, so several
hook processes writing to the same log at once still produce one valid chain.

A chain alone cannot detect records cut off the END of the file. To catch that,
keep the head hash somewhere else (`rewindagents head`) and pass it to `verify`.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

GENESIS = "0" * 64


def _digest(record: dict) -> str:
    canon = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canon.encode()).hexdigest()


def _last_hash(fh) -> tuple[str, int]:
    fh.seek(0)
    last, n = None, 0
    for line in fh:
        if line.strip():
            last, n = line, n + 1
    return (json.loads(last)["hash"] if last else GENESIS), n


class Recorder:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, session: str, tool: str, args: Any, result: Any = None,
               actor: str = "agent", event: str = "tool_call", ts: float | None = None) -> dict:
        """Append one record. `ts` defaults to now; `import` passes the original time of a moved record."""
        with self.path.open("a+", encoding="utf-8") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                prev, n = _last_hash(fh)
                body = {"seq": n + 1, "ts": round(time.time() if ts is None else ts, 3), "session": session,
                        "actor": actor, "event": event, "tool": tool,
                        "args": args, "result": result, "prev": prev}
                body["hash"] = _digest(body)
                fh.seek(0, os.SEEK_END)
                fh.write(json.dumps(body, sort_keys=True, ensure_ascii=False) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)
        return body


def head(path: str | Path) -> str:
    p = Path(path)
    if not p.exists():
        return GENESIS
    with p.open(encoding="utf-8") as fh:
        return _last_hash(fh)[0]


def verify(path: str | Path, expected_head: str | None = None) -> tuple[bool, int, str]:
    """Return (ok, records_checked, message)."""
    prev, n = GENESIS, 0
    with Path(path).open(encoding="utf-8") as fh:
        for n, line in enumerate((l for l in fh if l.strip()), 1):
            try:
                rec = json.loads(line)
                claimed = rec.pop("hash")
            except (ValueError, KeyError):
                return False, n, f"record {n}: not a valid record"
            if rec.get("prev") != prev:
                return False, n, f"record {n}: chain broken (prev does not match)"
            if rec.get("seq") != n:
                return False, n, f"record {n}: sequence number is {rec.get('seq')}"
            if _digest(rec) != claimed:
                return False, n, f"record {n}: contents altered"
            prev = claimed
    if expected_head is not None and prev != expected_head:
        return False, n, "head does not match the pinned hash (records removed from the end?)"
    return True, n, "chain intact"


def read(path: str | Path, session: str | None = None) -> list[dict]:
    with Path(path).open(encoding="utf-8") as fh:
        recs = [json.loads(l) for l in fh if l.strip()]
    return [r for r in recs if session is None or r["session"] == session]
