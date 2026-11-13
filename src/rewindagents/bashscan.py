"""Checkpoints for files a Bash command changes (sed -i, rm, mv, a script that rewrites files).

A Bash command does not say which files it will touch, so the hook looks at the whole project instead:
- before the command (PreToolUse), every project file's bytes go into the object store and the list of
  {path: sha256} is kept in .rewindagents/pending/<call>.json;
- after it (PostToolUse), the project is scanned again and only the files that differ are checkpointed in
  the "post" record: changed or deleted files with their bytes from before, new files as absent.

Project files: in a git work tree, `git ls-files --cached --others --exclude-standard` (tracked plus
untracked, minus ignored); elsewhere, a walk that skips SKIP_DIRS. Symlinks are not followed or saved.
A stat cache (.rewindagents/index.json) means only files whose size or mtime changed are read again.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from .hook import MAX_CHECKPOINT_BYTES, checkpoint

SKIP_DIRS = {".git", ".rewindagents", "node_modules", ".venv", "venv", "__pycache__"}
MAX_SCAN_FILES = 20000


def project_files(root: Path) -> list[str] | None:
    """Relative paths of the project's regular files, or None when there are more than MAX_SCAN_FILES."""
    rels: list[str] | None = None
    try:
        p = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others",
                            "--exclude-standard"], capture_output=True, timeout=20)
        if p.returncode == 0:
            rels = [r for r in p.stdout.decode("utf-8", "surrogateescape").split("\0") if r]
    except (OSError, subprocess.TimeoutExpired):
        pass
    if rels is None:
        rels = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for f in filenames:
                rels.append(os.path.relpath(os.path.join(dirpath, f), root))
                if len(rels) > MAX_SCAN_FILES:
                    return None
    out = []
    for r in rels:
        if Path(r).parts[0] in (".git", ".rewindagents"):
            continue
        full = root / r
        if full.is_symlink() or not full.is_file():
            continue
        out.append(r)
    return None if len(out) > MAX_SCAN_FILES else sorted(out)


def _load_index(store: Path) -> dict:
    try:
        idx = json.loads((store / "index.json").read_text(encoding="utf-8"))
        return idx if isinstance(idx, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_index(store: Path, idx: dict) -> None:
    tmp = store / f".index.{os.getpid()}.tmp"
    tmp.write_text(json.dumps(idx), encoding="utf-8")
    os.replace(tmp, store / "index.json")


def snapshot(root: Path, store: Path, save: bool) -> dict[str, Any] | None:
    """{relative path: sha256, or {"skipped": why}} for every project file. None if the project is too big.

    With save=True every file's bytes are put in the object store (unchanged files are already there).
    """
    rels = project_files(root)
    if rels is None:
        return None
    idx, new_idx = _load_index(store), {}
    objects = store / "objects"
    out: dict[str, Any] = {}
    for r in rels:
        full = root / r
        try:
            st = full.stat()
        except OSError:
            continue
        if st.st_size > MAX_CHECKPOINT_BYTES:
            out[r] = {"skipped": f"larger than {MAX_CHECKPOINT_BYTES} bytes",
                      "stat": [st.st_mtime_ns, st.st_size]}
            continue
        cached = idx.get(r)
        sha = cached[2] if (isinstance(cached, list) and len(cached) == 3
                            and cached[:2] == [st.st_mtime_ns, st.st_size]) else None
        if sha and (not save or (objects / sha).is_file()):
            out[r] = sha
        else:
            try:
                if save:
                    sha = checkpoint(full, objects).get("sha256")
                else:
                    sha = hashlib.sha256(full.read_bytes()).hexdigest()
            except OSError:
                continue
            if sha is None:
                continue
            out[r] = sha
        new_idx[r] = [st.st_mtime_ns, st.st_size, out[r]]
    _save_index(store, new_idx)
    return out


def _key(payload: dict) -> str:
    """Pairs a call's pre and post events: Claude Code's tool_use_id, else session + input."""
    tid = payload.get("tool_use_id")
    basis = str(tid) if tid else json.dumps([payload.get("session_id"), payload.get("tool_input")],
                                            sort_keys=True, default=str)
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:32]


def before(payload: dict, root: Path, store: Path) -> dict:
    """PreToolUse: save every project file and remember the list. Returns what goes in the pre record:
    the file count and the pending scan's name, so `gc` can say which command a stale scan belongs to."""
    snap = snapshot(root, store, save=True)
    if snap is None:
        return {"skipped": f"more than {MAX_SCAN_FILES} files"}
    pending = store / "pending"
    pending.mkdir(parents=True, exist_ok=True)
    key = _key(payload)
    tmp = pending / f".{key}.{os.getpid()}.tmp"
    tmp.write_text(json.dumps(snap), encoding="utf-8")
    os.replace(tmp, pending / f"{key}.json")
    return {"files": len(snap), "pending": key}


def after(payload: dict, root: Path, store: Path, afters: list | None = None) -> tuple[dict, list[dict]]:
    """PostToolUse: the checkpoints for files the command changed, created or deleted. When `afters` is a
    list, one entry per such file is appended to it with its hash right after the command (hook.after_hash's
    shape: {"path", "after": sha256 or None}, or {"path", "skipped"})."""
    pend = store / "pending" / f"{_key(payload)}.json"
    try:
        old = json.loads(pend.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"skipped": "no scan from before the command"}, []
    pend.unlink(missing_ok=True)
    new = snapshot(root, store, save=False)
    if new is None:
        return {"skipped": f"more than {MAX_SCAN_FILES} files"}, []
    cps: list[dict] = []
    for r in sorted(set(old) | set(new)):
        was, now = old.get(r), new.get(r)
        if was == now:
            continue
        path = str(root / r)
        if was is None:
            cps.append({"path": path, "sha256": None})                    # created by the command
        elif isinstance(was, dict):
            cps.append({"path": path, "sha256": None, "skipped": was["skipped"]})
        else:
            cps.append({"path": path, "sha256": was})                     # changed or deleted
        if afters is not None:
            if isinstance(now, dict):
                afters.append({"path": path, "skipped": now["skipped"]})
            else:
                afters.append({"path": path, "after": now})              # None: deleted by the command
    scan: dict[str, Any] = {"changed": len(cps)}
    if background(payload):
        scan["early"] = EARLY
    return scan, cps


EARLY = "run_in_background: the after-scan may have run before the command finished"


def background(payload: dict) -> bool:
    """Claude Code's Bash input carries `run_in_background` ("Whether to run the command in background",
    https://code.claude.com/docs/en/hooks, read 2026-11-12). The same page documents no hook event for a
    background shell finishing, so the after-scan of such a call may run while the command is still going:
    files it changes later are missing from this step's checkpoints."""
    ti = payload.get("tool_input")
    return isinstance(ti, dict) and ti.get("run_in_background") is True
