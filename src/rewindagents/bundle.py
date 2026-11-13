"""`rewindagents bundle` and `rewindagents import`: move one session to another machine or clone.

A bundle is one JSON file holding a session's log records, exactly as the log has them (each still carries
the SHA-256 the chain gave it), and every stored file copy those records name, so the session can be
replayed and rewound where it lands. Nothing goes over a network; carry the file however you like.

`bundle` refuses a log whose hash chain does not verify, and a session whose stored copies are missing or
altered: a bundle that cannot be rewound is not worth carrying.

`import` checks everything before it writes anything:
- the file's own SHA-256 (over everything in it but that field);
- every record's hash, that every record belongs to the bundled session, and that they are in log order;
- every stored copy against its SHA-256, and that every copy a record names is in the bundle;
- that the destination log verifies, does not already hold the session, and that no stored copy already
  there under the same name differs.
Then it writes the stored copies and appends the records to the destination log, in order, with their
original times. They join the destination's own chain, so they get new sequence numbers and new hashes.

The one exception to "the destination log verifies" is a log whose only damage is torn writes (log.check
torn_only), as `gc` allows: refusing would lock the project out of every import after one full disk. The torn
line stays where it is (every byte already in the log is kept; the recorder starts the first imported record
on a fresh line), the records chain on from the last whole record, and the result carries the torn-write
message so the CLI can say so and exit 1. `bundle` still refuses such a log as a source.

Paths: a record names files by absolute path on the machine that recorded it. On import, every path under
the source project is moved under the destination project (the directory holding .rewindagents/), so
`rewind` there puts the files back in the clone, not at the old address. Commands and results keep their
text as recorded. The source project can appear under more than one spelling (on macOS a temporary
directory is /var/... in the hook's input and /private/var/... once resolved); `bundle` lists each
spelling the records use, and `import` moves all of them.

Secrets: by default `bundle` replaces secrets (redact.py) in the records' inputs and results and in the
stored copies. A copy that changed is carried under its new SHA-256, and a record that changed carries the
SHA-256 of its new body, so `import` checks them as it checks any other. Rewinding such a file in the
other clone writes the placeholder, not the secret. `--no-redact` carries everything exactly as recorded.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from . import __version__, log, ospaths, rewind
from . import redact as _redact
from .hook import store_lock

FORMAT = "rewindagents-bundle"
VERSION = 1
_SHA = re.compile(r"[0-9a-f]{64}")


class BundleError(Exception):
    pass


def _canon(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(bundle: dict) -> str:
    """SHA-256 of the bundle without its own "digest" field."""
    return hashlib.sha256(_canon({k: v for k, v in bundle.items() if k != "digest"})).hexdigest()


def _strings(obj: Any):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def named_objects(obj: Any) -> set[str]:
    """The stored copies a record's args name: the sha256 of every {"path": ..., "sha256": ...} in them."""
    out: set[str] = set()
    if isinstance(obj, dict):
        if "path" in obj and isinstance(obj.get("sha256"), str):
            out.add(obj["sha256"])
        for v in obj.values():
            out |= named_objects(v)
    elif isinstance(obj, list):
        for v in obj:
            out |= named_objects(v)
    return out


def root_spellings(records: list[dict], root: Path) -> list[str]:
    """Every spelling of the project directory the records' args use, longest first."""
    found = {str(root)}
    for rec in records:
        for s in _strings(rec.get("args")):
            if not s.startswith("/") or "\n" in s:
                continue
            try:
                rel = Path(os.path.realpath(s)).relative_to(root)
            except ValueError:
                continue
            tail = "" if str(rel) == "." else str(rel)
            if not tail:
                found.add(s.rstrip("/") or "/")
            elif s.endswith("/" + tail):
                found.add(s[: -len(tail) - 1])
    return sorted(found, key=len, reverse=True)


def move_paths(obj: Any, spellings: list[str], dest: Path) -> Any:
    """obj with every string that is, or is under, one of the spellings moved under dest."""
    if isinstance(obj, str):
        for sp in (f for s in spellings for f in ospaths.forms(s)):   # Windows: C:\proj\a.py, C:/proj/a.py
            if obj == sp:
                return str(dest)
            sep = ospaths.seps(sp)
            base = sp.rstrip(sep)
            if len(obj) > len(base) and obj.startswith(base) and obj[len(base)] in sep:
                rest = obj[len(base) + 1:]
                for c in sep:
                    rest = rest.replace(c, os.sep)
                return str(dest) + os.sep + rest
        return obj
    if isinstance(obj, dict):
        return {k: move_paths(v, spellings, dest) for k, v in obj.items()}
    if isinstance(obj, list):
        return [move_paths(v, spellings, dest) for v in obj]
    return obj


def _repoint(obj: Any, moved: dict[str, str]) -> Any:
    """obj with every {"path": ..., "sha256": old} naming a redacted copy pointed at the redacted one."""
    if isinstance(obj, dict):
        out = {k: _repoint(v, moved) for k, v in obj.items()}
        if "path" in out and out.get("sha256") in moved:
            out["sha256"] = moved[out["sha256"]]
        return out
    if isinstance(obj, list):
        return [_repoint(v, moved) for v in obj]
    return obj


def _copy_paths(obj: Any) -> dict[str, set[str]]:
    """sha256 -> the paths the record names it under."""
    out: dict[str, set[str]] = {}
    if isinstance(obj, dict):
        if isinstance(obj.get("path"), str) and isinstance(obj.get("sha256"), str):
            out.setdefault(obj["sha256"], set()).add(obj["path"])
        for v in obj.values():
            for k, ps in _copy_paths(v).items():
                out.setdefault(k, set()).update(ps)
    elif isinstance(obj, list):
        for v in obj:
            for k, ps in _copy_paths(v).items():
                out.setdefault(k, set()).update(ps)
    return out


def redact_session(records: list[dict], objects: dict[str, bytes]) -> tuple[list[dict], dict[str, bytes], int]:
    """Records and stored copies with secrets replaced (redact.py). A copy whose bytes change is stored
    under its new SHA-256 and every record naming it is pointed there; a record whose body changes gets
    the SHA-256 of its new body, so `check` still holds. Returns (records, objects, values replaced)."""
    total, moved, out_objects = 0, {}, {}
    paths: dict[str, set[str]] = {}
    for r in records:
        for k, ps in _copy_paths(r.get("args")).items():
            paths.setdefault(k, set()).update(ps)
    for sha, raw in objects.items():
        env = any(_redact.is_env_file(p) for p in paths.get(sha, ()))
        new, n = _redact.data(raw, env)
        total += n
        new_sha = hashlib.sha256(new).hexdigest() if n else sha
        moved.update({sha: new_sha} if n else {})
        out_objects[new_sha] = new
    out_records = []
    for r in records:
        args, n1 = _redact.value(r.get("args"))
        result, n2 = _redact.value(r.get("result"))
        total += n1 + n2
        args = _repoint(args, moved)
        if n1 or n2 or args != r.get("args"):
            body = {k: v for k, v in r.items() if k != "hash"}
            body.update(args=args, result=result)
            r = {**body, "hash": hashlib.sha256(_canon(body)).hexdigest()}
        out_records.append(r)
    return out_records, out_objects, total


def bundle(log_path: str | Path, out: str | Path, session: str | None = None, redact: bool = True) -> dict:
    """Write one session of the log, and the stored copies it names, to `out`. redact=True replaces
    secrets in the records and the stored copies first (see redact_session)."""
    ok, _, msg = log.verify(log_path)
    if not ok:
        raise BundleError(f"log does not verify ({msg}); refusing to bundle from it")
    session = session or rewind.latest_session(log_path)
    records = log.read(log_path, session)
    if not records:
        raise BundleError(f"no session {session!r} in the log")
    root = rewind.project_root(log_path)
    store = root / ".rewindagents" / "objects"
    raw: dict[str, bytes] = {}
    for sha in sorted(set().union(*(named_objects(r.get("args")) for r in records))):
        obj = store / sha
        data = obj.read_bytes() if _SHA.fullmatch(sha) and obj.is_file() else None
        if data is None or hashlib.sha256(data).hexdigest() != sha:
            raise BundleError(f"stored copy {sha[:12]} is missing or altered; refusing to bundle a session "
                              f"that could not be rewound")
        raw[sha] = data
    spellings = root_spellings(records, root)
    redacted = 0
    if redact:
        records, raw, redacted = redact_session(records, raw)
    objects = {sha: base64.b64encode(data).decode("ascii") for sha, data in sorted(raw.items())}
    b = {"format": FORMAT, "version": VERSION, "made_with": f"rewindagents {__version__}",
         "session": session, "root": str(root), "root_spellings": spellings,
         "records": records, "objects": objects, "redacted": redacted if redact else None}
    b["digest"] = digest(b)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f".{out.name}.rewindagents.tmp")
    tmp.write_bytes(_canon(b) + b"\n")
    os.replace(tmp, out)
    return {"out": out, "session": session, "records": len(records),
            "steps": len(rewind.steps_from(records)), "objects": len(objects), "bytes": out.stat().st_size,
            "redacted": b["redacted"]}


def check(b: Any) -> dict[str, bytes]:
    """Raise BundleError unless the bundle is whole and unaltered; return its stored copies, decoded."""
    if not isinstance(b, dict) or b.get("format") != FORMAT:
        raise BundleError("not a rewindagents bundle")
    if b.get("version") != VERSION:
        raise BundleError(f"bundle version {b.get('version')!r} is not one this rewindagents reads ({VERSION})")
    if b.get("digest") != digest(b):
        raise BundleError("bundle altered: its SHA-256 does not match")
    session, records, objects = b.get("session"), b.get("records"), b.get("objects")
    if not isinstance(session, str) or not isinstance(records, list) or not records or not isinstance(objects, dict):
        raise BundleError("bundle is missing its session, records or stored copies")
    if not isinstance(b.get("root_spellings"), list) or not all(isinstance(s, str) and ospaths.isabs(s)
                                                                for s in b["root_spellings"]):
        raise BundleError("bundle is missing the source project's path")
    last = 0
    for i, rec in enumerate(records, 1):
        if not isinstance(rec, dict) or not isinstance(rec.get("hash"), str):
            raise BundleError(f"record {i}: not a valid record")
        body = {k: v for k, v in rec.items() if k != "hash"}
        if hashlib.sha256(_canon(body)).hexdigest() != rec["hash"]:
            raise BundleError(f"record {i}: contents altered")
        if rec.get("session") != session:
            raise BundleError(f"record {i}: belongs to session {rec.get('session')!r}, not {session!r}")
        if not isinstance(rec.get("seq"), int) or rec["seq"] <= last:
            raise BundleError(f"record {i}: out of log order")
        if not isinstance(rec.get("tool"), str) or not isinstance(rec.get("ts"), (int, float)):
            raise BundleError(f"record {i}: not a valid record")
        last = rec["seq"]
    data: dict[str, bytes] = {}
    for sha, enc in objects.items():
        if not _SHA.fullmatch(sha):
            raise BundleError(f"stored copy {sha[:40]!r} is not named by a SHA-256")
        try:
            raw = base64.b64decode(enc, validate=True)
        except (ValueError, TypeError):
            raise BundleError(f"stored copy {sha[:12]} is not valid base64")
        if hashlib.sha256(raw).hexdigest() != sha:
            raise BundleError(f"stored copy {sha[:12]} altered: its bytes do not match its SHA-256")
        data[sha] = raw
    for rec in records:
        missing = named_objects(rec.get("args")) - set(data)
        if missing:
            raise BundleError(f"record seq {rec['seq']} names stored copy {sorted(missing)[0][:12]}, "
                              f"which the bundle does not carry")
    return data


def import_bundle(path: str | Path, log_path: str | Path) -> dict:
    """Check the bundle and the destination, then add the session to the destination log. All or nothing:
    any failed check raises BundleError before a byte is written."""
    try:
        b = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise BundleError(f"cannot read {path}: {e}")
    data = check(b)
    session = b["session"]
    log_path = Path(log_path)
    root = rewind.project_root(log_path)
    store = root / ".rewindagents"
    torn = False
    if log_path.exists():
        ok, _, msg, torn_only = log.check(log_path)
        if not ok and not torn_only:
            raise BundleError(f"this log does not verify ({msg}); refusing to add to it")
        torn = not ok
        if log.read(log_path, session):
            raise BundleError(f"this log already holds session {session!r}; nothing imported")
    have = 0
    for sha, raw in data.items():
        obj = store / "objects" / sha
        if obj.exists():
            if not obj.is_file() or hashlib.sha256(obj.read_bytes()).hexdigest() != sha:
                raise BundleError(f"stored copy {sha[:12]} here is altered; nothing imported")
            have += 1
    # every check passed: write
    store.mkdir(parents=True, exist_ok=True)
    ignore = store / ".gitignore"
    if not ignore.exists():  # as the hook does: keep the log and stored copies out of the user's commits
        ignore.write_text("*\n", encoding="utf-8")
    (store / "objects").mkdir(exist_ok=True)
    with store_lock(store):  # `gc` must not delete the copies before the records naming them are written
        for sha, raw in data.items():
            obj = store / "objects" / sha
            if not obj.exists():
                tmp = obj.with_name(f".{sha}.{os.getpid()}.tmp")
                tmp.write_bytes(raw)
                os.replace(tmp, obj)
        rec = log.Recorder(log_path)
        for r in b["records"]:
            rec.record(session, r["tool"], move_paths(r.get("args"), b["root_spellings"], root), r.get("result"),
                       actor=r.get("actor", "agent"), event=r.get("event", "tool_call"), ts=r.get("ts"))
    return {"session": session, "records": len(b["records"]), "steps": len(rewind.steps_from(b["records"])),
            "objects": len(data), "already_here": have, "from_root": b.get("root"), "root": root,
            "torn": log.check(log_path)[2] if torn else None}
