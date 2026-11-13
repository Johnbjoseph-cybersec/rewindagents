"""Take back one step and keep everything after it: `rewindagents revert K`.

`rewind N` puts files back as they were at step N, so it also takes back every later step, and it refuses when a
file changed by hand since (see rewind.drift). `revert K` reverses step K alone. For each file step K changed it
merges three versions of the file (merge.merge3):

- base:   the file right after step K (the copy the hook keeps since this version, see hook.after_hash);
- theirs: the file right before step K (step K's checkpoint);
- ours:   the file now, with every later step and hand edit in it.

So a later agent step or a hand edit to another part of the same file stays, and step K's lines go back. A file
step K created is removed only if it is unchanged since; a file it deleted comes back only if nothing re-created
it. When step K's change and a later change touch the same lines, or both sides of a create or delete disagree, it
is a conflict: revert changes NOTHING (no file, no log record) and names the files.

Before writing, the current bytes of every file it changes are checkpointed and the revert is recorded as a step
(event "revert"), the same safety as rewind: `rewind <its step - 1>` or `revert <its step>` takes it back.

Same limits as rewind: the log's hash chain and every stored copy must verify; files outside the project, files
over 20 MB, a symlink where the file was, and a step whose before/after scan did not finish are reported as
`cannot` and left alone (exit 1). When the bytes right after step K were not kept (a log written before this
version) they are taken from a later checkpoint or the file now when either has the hash the log recorded;
otherwise that file is `cannot`, never guessed.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from . import log, merge
from .hook import MAX_CHECKPOINT_BYTES, checkpoint, store_lock
from .rewind import (RewindError, StepRangeError, _inside, latest_session, project_root, range_message, relative,
                     steps, timeline)

ABSENT = None


class ConflictError(RewindError):
    """Step K's change and a later change overlap in at least one file. Nothing was changed. Carries the plan."""

    def __init__(self, message: str, plan: dict):
        super().__init__(message)
        self.plan = plan


def _obj(objects: Path, sha: str) -> bytes | None:
    """A stored copy's bytes when it is there and still has its hash."""
    p = objects / sha
    if not p.is_file():
        return None
    data = p.read_bytes()
    return data if hashlib.sha256(data).hexdigest() == sha else None


def _now(path: Path) -> tuple[Any, str | None]:
    """(bytes or ABSENT, why it cannot be read for a merge, or None)."""
    if path.is_symlink():
        return ABSENT, "a symlink is there now (revert does not follow or replace links)"
    if not path.exists():
        return ABSENT, None
    if not path.is_file():
        return ABSENT, "not a regular file now"
    if path.stat().st_size > MAX_CHECKPOINT_BYTES:
        return ABSENT, f"larger than {MAX_CHECKPOINT_BYTES} bytes now"
    return path.read_bytes(), None


def _before(step: dict, path_s: str, objects: Path) -> tuple[Any, int | None, str | None]:
    """The file right before the step: (bytes or ABSENT, mode, why not known)."""
    cp = next(c for c in step["checkpoints"] if c["path"] == path_s)
    if cp.get("skipped"):
        return ABSENT, None, f"not checkpointed before step {step['step']} ({cp['skipped']})"
    if cp.get("sha256") is None:
        return ABSENT, None, None
    data = _obj(objects, cp["sha256"])
    if data is None:
        return ABSENT, None, "stored copy missing or altered"
    return data, cp.get("mode"), None


def _after(step: dict, path_s: str, objects: Path, later: list[dict], now: Any) -> tuple[Any, int | None, str | None]:
    """The file right after the step: (bytes or ABSENT, mode or None, why not known).

    From the step's after entry: the stored copy with the recorded hash (the hook's own, or a later checkpoint of
    the same bytes), else the file now when it still has that hash. With no after entry at all (the step's post event never arrived, or
    a log from before after-hashes), the next checkpoint of the file in this session, as `replay --diff` uses."""
    entry = next((a for a in step.get("after") or [] if isinstance(a, dict) and a.get("path") == path_s), None)
    if entry is not None:
        if entry.get("skipped"):
            return ABSENT, None, f"not hashed after step {step['step']} ({entry['skipped']})"
        if "after" not in entry:
            entry = None
    if entry is not None:
        sha = entry["after"]
        if sha is None:
            return ABSENT, None, None
        data = _obj(objects, sha)      # kept by the hook, or a later step's checkpoint of the same bytes
        if data is None and now is not ABSENT and hashlib.sha256(now).hexdigest() == sha:
            data = now
        if data is None:
            return ABSENT, None, (f"the file as step {step['step']} left it was not kept (recorded by an older "
                                  f"version); `rewind {step['step'] - 1} --only` puts the whole file back")
        return data, entry.get("mode"), None
    for st in later:
        if st.get("session") != step.get("session"):
            continue
        cp = next((c for c in st["checkpoints"] if c["path"] == path_s), None)
        if cp is not None:
            if cp.get("skipped"):
                break
            if cp.get("sha256") is None:
                return ABSENT, None, None
            data = _obj(objects, cp["sha256"])
            if data is not None:
                return data, cp.get("mode"), None
            break
    return ABSENT, None, (f"no record of the file right after step {step['step']}; "
                          f"`rewind {step['step'] - 1} --only` puts the whole file back")


def _mode_now(path: Path) -> int | None:
    try:
        return path.stat().st_mode & 0o777
    except OSError:
        return None


def plan(log_path: str | Path, k: int, session: str | None = None) -> dict:
    """What reverting step k would do. Reads only.

    p["write"]: [(path, bytes, mode or None)], p["merged"]: the written paths that keep later changes (the rest
    get exactly their bytes from before step K), p["delete"]: [path], p["same"]: files already as the revert would
    leave them, p["conflict"]: [(path, why)], p["cannot"]: [(path, why)]."""
    ok, _, msg, torn_only = log.check(log_path)
    if not ok and not torn_only:
        raise RewindError(f"log does not verify ({msg}); refusing to revert from it")
    session = session or latest_session(log_path)
    all_steps = steps(log_path, session)
    if not 1 <= k <= len(all_steps):
        raise StepRangeError(range_message(k, session, len(all_steps), 1))
    step = dict(all_steps[k - 1], session=session)
    root = project_root(log_path)
    objects = root / ".rewindagents" / "objects"
    later = [st for st in timeline(log_path) if st["seq"] > step["seq"]]
    p: dict[str, Any] = {"session": session, "step": k, "steps": len(all_steps), "write": [], "delete": [],
                         "same": [], "conflict": [], "cannot": [], "merged": [], "torn": None if ok else msg,
                         "uncovered": (step["tool"] == "Bash" or step.get("scanned"))
                         and "changed" not in (step.get("bash_scan") or {})}
    if (step.get("bash_scan") or {}).get("early"):
        p["early"] = True
    paths = list(dict.fromkeys(cp["path"] for cp in step["checkpoints"]))
    if not paths and p["uncovered"]:
        raise RewindError(f"step {k} ran a command whose before/after scan did not finish, so what it changed is "
                          f"not known; nothing to revert. `replay --step {k}` shows the step")
    if not paths:
        scope = (" (a command's scan covers the regular files inside the project: a file outside it or a symlink "
                 "it changed is not recorded)" if step.get("scanned") or step["tool"] == "Bash" else "")
        raise RewindError(f"step {k} changed no file the log knows of{scope}; nothing to revert "
                          f"(`replay --step {k}` shows the step)")
    for path_s in paths:
        path = Path(path_s)
        if not _inside(path, root):
            p["cannot"].append((path_s, "outside the project"))
            continue
        ours, why = _now(path)
        if why is None:
            theirs, t_mode, why = _before(step, path_s, objects)
        if why is None:
            base, b_mode, why = _after(step, path_s, objects, later, ours)
        if why is not None:
            p["cannot"].append((path_s, why))
            continue
        o_mode = _mode_now(path) if ours is not ABSENT else None
        if ours == theirs and (ours is ABSENT or t_mode is None or o_mode == t_mode):
            p["same"].append(path_s)
            continue
        if ours == base:
            # nothing changed it since step K: the file goes back to exactly what it was before step K
            if theirs is ABSENT:
                p["delete"].append(path_s)
            else:
                mode = t_mode if (b_mode is None or o_mode == b_mode) else o_mode
                p["write"].append((path_s, theirs, mode))
            continue
        if ours is ABSENT:
            p["conflict"].append((path_s, f"deleted after step {k}, which changed it"
                                  if theirs is not ABSENT else f"deleted after step {k}"))
            continue
        if theirs is ABSENT:
            p["conflict"].append((path_s, f"step {k} created it, and it changed after step {k}"))
            continue
        if base is ABSENT:
            p["conflict"].append((path_s, f"step {k} deleted it, and it was created again after step {k}"))
            continue
        if b"\0" in base + ours + theirs:
            p["conflict"].append((path_s, f"binary file changed both by step {k} and after it"))
            continue
        try:
            merged = merge.merge3(base, ours, theirs)
        except merge.Conflict as c:
            where = ", ".join(f"line {a}" if b <= a else f"lines {a}-{b}" for a, b in c.hunks)
            p["conflict"].append((path_s, f"step {k} and a later change both changed {where} (lines of the file "
                                          f"as step {k} left it)"))
            continue
        # the executable bit: step K's own mode change goes back unless the mode changed again since
        mode = t_mode if (t_mode is not None and b_mode is not None and o_mode == b_mode) else None
        if merged == ours and (mode is None or mode == o_mode):
            p["same"].append(path_s)
        else:
            p["write"].append((path_s, merged, mode))
            p["merged"].append(path_s)      # later changes kept in it: not simply the bytes from before step K
    return p


def revert(log_path: str | Path, k: int, session: str | None = None, dry_run: bool = False) -> dict:
    """Reverse step k's changes and keep every later one. Raises ConflictError (changing nothing) on a conflict.
    See plan()."""
    p = plan(log_path, k, session)
    if p["conflict"]:
        root = project_root(log_path)
        files = "; ".join(f"{relative(q, root)} ({why})" for q, why in p["conflict"])
        if not dry_run:
            raise ConflictError(f"nothing changed: step {k} cannot be reverted cleanly: {files}", p)
        return p
    if dry_run or not (p["write"] or p["delete"]):
        return p
    root = project_root(log_path)
    objects = root / ".rewindagents" / "objects"
    touched = [q for q, _, _ in p["write"]] + p["delete"]
    with store_lock(root / ".rewindagents"):
        saved = [checkpoint(Path(q), objects) for q in touched]      # the revert itself can be taken back
        after = []
        for q, data, mode in p["write"]:
            sha = hashlib.sha256(data).hexdigest()
            obj = objects / sha
            if not obj.exists():
                tmp = objects / f".{sha}.{os.getpid()}.tmp"
                tmp.write_bytes(data)
                os.replace(tmp, obj)
            final_mode = mode if mode is not None else _mode_now(Path(q))
            entry = {"path": q, "after": sha, "sha256": sha}
            if final_mode is not None:
                entry["mode"] = final_mode
            after.append(entry)
        after += [{"path": q, "after": None} for q in p["delete"]]
        args = {"input": {"revert": k}, "revert": k, "checkpoints": saved, "after": after}
        rec = log.Recorder(log_path).record(p["session"], "rewindagents", args, None, actor="user", event="revert")
    for q, data, mode in p["write"]:
        path = Path(q)
        path.parent.mkdir(parents=True, exist_ok=True)
        old_mode = _mode_now(path)
        tmp = path.with_name(f".{path.name}.rewindagents.tmp")
        tmp.write_bytes(data)
        if mode is not None or old_mode is not None:
            os.chmod(tmp, mode if mode is not None else old_mode)
        os.replace(tmp, path)
    for q in p["delete"]:
        Path(q).unlink()
    p["record"] = rec["seq"]
    return p
