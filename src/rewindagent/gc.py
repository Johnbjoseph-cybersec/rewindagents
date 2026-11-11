"""`rewindagent gc`: delete stored copies nothing needs any more.

Why the store grows: before every Bash call the hook saves a copy of every project file
(.rewindagent/objects/<sha256>), and only the copies of files the command changed are named in the log
afterwards. The rest stay on disk unless something removes them.

A stored copy is kept when:
- a log record names it (any session; the args or the result hold {"path": ..., "sha256": <it>}), or
- a pending scan (.rewindagent/pending/<call>.json, a command whose after-scan has not run) lists it.
Everything else under objects/ whose name is a SHA-256 is deleted. Other files there are left alone.

gc refuses to run when the log does not verify, and it never writes to the log: the chain stays whole.
It holds the store lock exclusively (hook.store_lock), so a hook, rewind or import that has saved a copy
but not yet written the record naming it finishes first, and the next one waits until gc is done.
Bytes freed are the sizes of the files actually deleted, read from disk just before each delete.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import bundle, log
from .hook import store_lock

_SHA = re.compile(r"[0-9a-f]{64}")


class GcError(Exception):
    pass


def needed(log_path: str | Path) -> tuple[set[str], int]:
    """(the copies the log or a pending scan names, number of pending scans). Raises GcError when a
    pending scan cannot be read, since then nobody can say what it needs."""
    named: set[str] = set()
    for rec in log.read(log_path):
        named |= bundle.named_objects(rec.get("args")) | bundle.named_objects(rec.get("result"))
    pending = sorted((Path(log_path).parent / "pending").glob("*.json"))
    for p in pending:
        try:
            snap = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise GcError(f"cannot read pending scan {p.name} ({e}); nothing deleted")
        if not isinstance(snap, dict):
            raise GcError(f"pending scan {p.name} is not a scan; nothing deleted")
        named |= {v for v in snap.values() if isinstance(v, str)}
    return named, len(pending)


def gc(log_path: str | Path, dry_run: bool = False, timeout: float = 30.0) -> dict:
    """Delete (or with dry_run, list) the stored copies nothing needs. Returns counts and bytes."""
    store = Path(log_path).parent
    objects = store / "objects"
    try:
        with store_lock(store, exclusive=True, timeout=timeout):
            ok, _, msg = log.verify(log_path)
            if not ok:
                raise GcError(f"log does not verify ({msg}); refusing to delete anything")
            keep, pending = needed(log_path)
            deleted, freed, kept = [], 0, 0
            for obj in sorted(objects.iterdir()) if objects.is_dir() else []:
                if not _SHA.fullmatch(obj.name) or obj.is_symlink() or not obj.is_file():
                    continue
                if obj.name in keep:
                    kept += 1
                    continue
                size = obj.stat().st_size
                if not dry_run:
                    obj.unlink()
                deleted.append(obj.name)
                freed += size
    except TimeoutError as e:
        raise GcError(f"{e} (a hook, rewind or import kept writing); nothing deleted")
    return {"deleted": deleted, "bytes": freed, "kept": kept, "pending": pending, "dry_run": dry_run}


def lines(d: dict) -> list[str]:
    n = len(d["deleted"])
    head = (f"would delete {n} stored copies ({d['bytes']:,} bytes)" if d["dry_run"]
            else f"deleted {n} stored copies ({d['bytes']:,} bytes freed)")
    out = [f"{head}; kept {d['kept']} that the log or a pending scan names"]
    if d["pending"]:
        out.append(f"  {d['pending']} pending scan(s) (a command whose after-scan has not run) keep their copies")
    return out
