"""`rewindagents gc`: delete stored copies nothing needs any more.

Why the store grows: before every Bash call the hook saves a copy of every project file
(.rewindagents/objects/<sha256>), and only the copies of files the command changed are named in the log
afterwards. The rest stay on disk unless something removes them.

A stored copy is kept when:
- a log record names it (any session; the args or the result hold {"path": ..., "sha256": <it>}), or
- a pending scan (.rewindagents/pending/<call>.json, a command whose after-scan has not run) lists it.
Everything else under objects/ whose name is a SHA-256 is deleted. Other files there are left alone.

gc refuses to run when the log does not verify, and it never writes to the log: the chain stays whole.
It holds the store lock exclusively (hook.store_lock), so a hook, rewind or import that has saved a copy
but not yet written the record naming it finishes first, and the next one waits until gc is done.
Bytes freed are the sizes of the files actually deleted, read from disk just before each delete.

Stale pending scans: when a command's after-scan never runs (the agent was killed, a crash), its pending scan
keeps every copy it lists forever. gc lists each pending scan with its age (the file's mtime: it is written
once, before the command) and the command it belongs to (the pre record that names it), and with
drop_older_than (days, at least MIN_DROP_DAYS) removes the older ones first, so their copies can go too.
A rewind of such a step then reports it as unscanned, which it already did while the scan was pending.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from . import bundle, log
from .hook import store_lock

_SHA = re.compile(r"[0-9a-f]{64}")
MIN_DROP_DAYS = 1.0   # never drop a scan younger than this: its command may still be running


class GcError(Exception):
    pass


def pending_scans(log_path: str | Path, now: float | None = None) -> list[dict]:
    """Each pending scan: {"name", "age_days", "command", "tool", "session"}. The last three are None when no
    pre record names the scan (records written before the pre record carried the scan's name)."""
    now = time.time() if now is None else now
    owners: dict[str, dict] = {}
    for rec in log.read(log_path):
        scan = (rec.get("args") or {}).get("bash_scan") if isinstance(rec.get("args"), dict) else None
        if rec.get("event") == "pre" and isinstance(scan, dict) and isinstance(scan.get("pending"), str):
            owners[scan["pending"]] = rec
    out = []
    for p in sorted((Path(log_path).parent / "pending").glob("*.json")):
        try:
            age = max(0.0, (now - p.stat().st_mtime) / 86400)
        except OSError:
            continue
        rec = owners.get(p.stem)
        inp = rec["args"].get("input") if rec else None
        cmd = inp.get("command") if isinstance(inp, dict) and isinstance(inp.get("command"), str) else inp
        out.append({"name": p.name, "age_days": age,
                    "command": None if rec is None else (cmd if isinstance(cmd, str)
                                                         else json.dumps(cmd, sort_keys=True, default=str)),
                    "tool": rec.get("tool") if rec else None, "session": rec.get("session") if rec else None})
    return out


def needed(log_path: str | Path, skip: frozenset[str] = frozenset()) -> tuple[set[str], int]:
    """(the copies the log or a pending scan names, number of pending scans). Pending scans named in skip
    (dropped ones) are left out. Raises GcError when a pending scan cannot be read, since then nobody can
    say what it needs."""
    named: set[str] = set()
    for rec in log.read(log_path):
        named |= bundle.named_objects(rec.get("args")) | bundle.named_objects(rec.get("result"))
    pending = [p for p in sorted((Path(log_path).parent / "pending").glob("*.json")) if p.name not in skip]
    for p in pending:
        try:
            snap = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise GcError(f"cannot read pending scan {p.name} ({e}); nothing deleted")
        if not isinstance(snap, dict):
            raise GcError(f"pending scan {p.name} is not a scan; nothing deleted")
        named |= {v for v in snap.values() if isinstance(v, str)}
    return named, len(pending)


def gc(log_path: str | Path, dry_run: bool = False, timeout: float = 30.0,
       drop_older_than: float | None = None, now: float | None = None) -> dict:
    """Delete (or with dry_run, list) the stored copies nothing needs. With drop_older_than (days), first
    remove the pending scans older than that. Returns counts, bytes and the pending scans."""
    if drop_older_than is not None and not drop_older_than >= MIN_DROP_DAYS:
        raise GcError(f"pending scans younger than {MIN_DROP_DAYS:g} day are never dropped "
                      f"(got {drop_older_than:g}); nothing deleted")
    store = Path(log_path).parent
    objects = store / "objects"
    try:
        with store_lock(store, exclusive=True, timeout=timeout):
            ok, _, msg = log.verify(log_path)
            if not ok:
                raise GcError(f"log does not verify ({msg}); refusing to delete anything")
            scans = pending_scans(log_path, now)
            dropped = [s for s in scans if drop_older_than is not None and s["age_days"] > drop_older_than]
            if not dry_run:
                for s in dropped:
                    (store / "pending" / s["name"]).unlink(missing_ok=True)
            keep, pending = needed(log_path, frozenset(s["name"] for s in dropped))
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
    return {"deleted": deleted, "bytes": freed, "kept": kept, "pending": pending, "dry_run": dry_run,
            "dropped": dropped, "scans": [s for s in scans if s not in dropped],
            "drop_older_than": drop_older_than}


def _scan_line(s: dict) -> str:
    what = (f"{s['tool']}: {s['command']}" if s["command"] is not None
            else "command not recorded (scan made before rewindagents named it in the log)")
    what = " ".join(what.split())
    return f"    {s['age_days']:.1f} days old  {what[:100] + '...' if len(what) > 100 else what}"


def lines(d: dict) -> list[str]:
    n = len(d["deleted"])
    head = (f"would delete {n} stored copies ({d['bytes']:,} bytes)" if d["dry_run"]
            else f"deleted {n} stored copies ({d['bytes']:,} bytes freed)")
    out = [f"{head}; kept {d['kept']} that the log or a pending scan names"]
    if d.get("dropped"):
        out.append(f"  {'would drop' if d['dry_run'] else 'dropped'} {len(d['dropped'])} pending scan(s) "
                   f"older than {d['drop_older_than']:g} days:")
        out += [_scan_line(s) for s in d["dropped"]]
    if d["pending"]:
        out.append(f"  {d['pending']} pending scan(s) (a command whose after-scan has not run) keep their copies")
        out += [_scan_line(s) for s in d.get("scans", [])]
    return out
