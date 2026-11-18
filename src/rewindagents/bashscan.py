"""Checkpoints for files a Bash command changes (sed -i, rm, mv, a script that rewrites files).

A Bash command does not say which files it will touch, so the hook looks at the whole project instead:
- before the command (PreToolUse), every project file's bytes go into the object store and the list of
  {path: sha256} is kept in .rewindagents/pending/<call>.json;
- after it (PostToolUse), the project is scanned again and only the files that differ are checkpointed in
  the "post" record: changed or deleted files with their bytes from before, new files as absent.

Project files: in a git work tree, `git ls-files --cached` plus `--others --exclude-standard` (tracked plus
untracked, but not untracked files under SKIP_DIRS such as `__pycache__/`), plus the files git ignores one by one (`.env`, `config.local.json`, `*.log`) but not the directories
it ignores as a whole (`node_modules/`, `build/`, `.venv/`): a deleted `.env` is the one file neither git nor the
agent can bring back, while an ignored directory is usually rebuilt output. Elsewhere, a walk that skips
SKIP_DIRS. Symlinks are not followed or saved.
A stat cache (.rewindagents/index.json) means only files whose size, mtime or mode changed are read again.
In the pending scan a file is "<sha256>:<permission bits in octal>", so a `chmod` alone is a change too and a
deleted script comes back executable.
"""
from __future__ import annotations

import json
import os
import stat
import threading
from pathlib import Path

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import Any

from .hook import MAX_CHECKPOINT_BYTES, checkpoint
from .log import sha256

SKIP_DIRS = {".git", ".rewindagents", "node_modules", ".venv", "venv", "__pycache__"}
MAX_SCAN_FILES = 20000


def _ls(root: Path, *args: str) -> list[str] | None:
    import subprocess   # only a Bash call scans; the Read/Edit hook never needs it
    try:
        p = subprocess.run(["git", "-C", str(root), "ls-files", "-z", *args], capture_output=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if p.returncode != 0:
        return None
    return [r for r in p.stdout.decode("utf-8", "surrogateescape").split("\0") if r]


def _git_lists(root: Path, ignored_files: bool) -> list[list[str] | None]:
    """The `git ls-files` outputs project_files needs, run at the same time: each is a process start plus a read
    of the index, and they do not depend on one another."""
    argsets = [("--cached",), ("--others", "--exclude-standard")]
    if ignored_files:
        argsets.append(("--others", "--ignored", "--exclude-standard", "--directory"))
    results: list[list[str] | None] = [None] * len(argsets)

    def work(i: int) -> None:
        results[i] = _ls(root, *argsets[i])

    threads = [threading.Thread(target=work, args=(i,)) for i in range(1, len(argsets))]
    for t in threads:
        t.start()
    work(0)
    for t in threads:
        t.join()
    return results


def _under_skip(rel: str) -> bool:
    """True when a git-style (forward-slash) relative path has a SKIP_DIRS name in any position."""
    return not SKIP_DIRS.isdisjoint(rel.split("/"))


def project_files(root: Path, ignored_files: bool = False) -> list[str] | None:
    """Relative paths of the project's regular files, or None when there are more than MAX_SCAN_FILES.

    ignored_files=True adds the files git ignores one by one, never the contents of a directory it ignores as
    a whole, nor anything under SKIP_DIRS (the Bash scan uses this; `fork` does not, as a fresh worktree
    would not have them)."""
    found = _scan(root, ignored_files)
    return None if found is None else [r for r, _ in found]


def _scan(root: Path, ignored_files: bool) -> list[tuple[str, os.stat_result]] | None:
    """project_files with each file's lstat result (one stat call per file, which also tells a symlink from a
    regular file), sorted by path."""
    lists = _git_lists(root, ignored_files)
    rels = lists[0]
    if rels is not None:
        # untracked files under SKIP_DIRS (a __pycache__ or venv the .gitignore does not name) are rebuilt
        # output, as in the walk below: scanning them turned every `python` command into .pyc "changes"
        rels += [r for r in lists[1] or [] if not _under_skip(r)]
    if rels is not None and ignored_files:
        rels += [r for r in lists[2] or [] if not r.endswith("/") and not _under_skip(r)]
    if rels is None:
        rels = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for f in filenames:
                # forward-slash, like the git-ls-files branch above and rewind.relative()'s as_posix():
                # on Windows os.path.relpath returns '\\'-separated paths, which would otherwise be a
                # different dict key from the same file's path elsewhere in this project (runs.start_state
                # keys one dict partly from this, partly from rewind.relative()). Replacing the literal
                # backslash (not os.sep, which is "/" here on POSIX and would make this a no-op even when
                # a path was built with Windows semantics, e.g. under test) matches PureWindowsPath's own
                # as_posix(): POSIX filenames essentially never contain one.
                rels.append(os.path.relpath(os.path.join(dirpath, f), root).replace("\\", "/"))
                if len(rels) > MAX_SCAN_FILES:
                    return None
    out = []
    base = str(root)
    lstat, S_ISREG = os.lstat, stat.S_ISREG
    for r in rels:
        if r.split("/", 1)[0] in (".git", ".rewindagents"):
            continue
        try:
            st = lstat(os.path.join(base, r))
        except OSError:
            continue
        if S_ISREG(st.st_mode):      # a symlink's lstat is S_IFLNK, a directory (submodule) S_IFDIR: both skipped
            out.append((r, st))
    if len(out) > MAX_SCAN_FILES:
        return None
    out.sort(key=lambda t: t[0])
    return out


def _load_index(store: Path) -> dict:
    try:
        idx = json.loads((store / "index.json").read_text(encoding="utf-8"))
        return idx if isinstance(idx, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_index(store: Path, idx: dict, old: dict | None = None) -> None:
    if old is not None and idx == old:      # nothing changed since it was read: no need to write 10k entries again
        return
    tmp = store / f".index.{os.getpid()}.tmp"
    tmp.write_text(json.dumps(idx), encoding="utf-8")
    os.replace(tmp, store / "index.json")


def snapshot(root: Path, store: Path, save: bool) -> dict[str, Any] | None:
    """{relative path: sha256, or {"skipped": why}} for every project file. None if the project is too big.

    With save=True every file's bytes are put in the object store (unchanged files are already there).
    """
    found = _scan(root, ignored_files=True)
    if found is None:
        return None
    idx, new_idx = _load_index(store), {}
    objects = store / "objects"
    have: set[str] = set()
    if save:        # one directory read instead of a stat per file to learn which objects are stored
        try:
            have = set(os.listdir(objects))
        except OSError:
            pass
    base = str(root)
    out: dict[str, Any] = {}
    for r, st in found:
        if st.st_size > MAX_CHECKPOINT_BYTES:
            out[r] = {"skipped": f"larger than {MAX_CHECKPOINT_BYTES} bytes",
                      "stat": [st.st_mtime_ns, st.st_size]}
            continue
        mode = st.st_mode & 0o777
        cached = idx.get(r)
        sha = cached[3] if (isinstance(cached, list) and len(cached) == 4
                            and cached[:3] == [st.st_mtime_ns, st.st_size, mode]) else None
        if sha and (not save or sha in have):
            out[r] = sha
        else:
            full = Path(base, r)
            try:
                if save:
                    sha = checkpoint(full, objects).get("sha256")
                else:
                    sha = sha256(full.read_bytes()).hexdigest()
            except OSError:
                continue
            if sha is None:
                continue
            out[r] = sha
        new_idx[r] = [st.st_mtime_ns, st.st_size, mode, out[r]]
        out[r] = "%s:%o" % (out[r], mode)
    _save_index(store, new_idx, idx)
    return out


def _split(v: str) -> tuple[str, int | None]:
    sha, _, mode = v.partition(":")
    return sha, (int(mode, 8) if mode else None)


def _key(payload: dict) -> str:
    """Pairs a call's pre and post events: Claude Code's tool_use_id, else session + input."""
    tid = payload.get("tool_use_id")
    basis = str(tid) if tid else json.dumps([payload.get("session_id"), payload.get("tool_input")],
                                            sort_keys=True, default=str)
    return sha256(basis.encode("utf-8")).hexdigest()[:32]


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
    shape: {"path", "after": sha256 or None, with "sha256" and "mode" when a copy is stored}, or
    {"path", "skipped"})."""
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
            sha, mode = _split(was)
            cp = {"path": path, "sha256": sha}                            # changed or deleted
            if mode is not None:
                cp["mode"] = mode
            cps.append(cp)
        if afters is not None:
            if isinstance(now, dict):
                afters.append({"path": path, "skipped": now["skipped"]})
            elif now is None:                                             # deleted by the command
                afters.append({"path": path, "after": None})
            else:
                afters.append(_after_copy(Path(path), store / "objects", *_split(now)))
    scan: dict[str, Any] = {"changed": len(cps)}
    if background(payload):
        scan["early"] = EARLY
    return scan, cps


def _after_copy(path: Path, objects: Path, sha: str, mode: int | None) -> dict:
    """The after entry for a file the command changed: its hash from the scan, plus a stored copy ("sha256",
    "mode") when the bytes are still the scanned ones (`revert` merges from them). A file that changed again
    between the scan and the copy keeps the scan's hash only."""
    entry: dict[str, Any] = {"path": str(path), "after": sha}
    try:
        cp = checkpoint(path, objects)
    except OSError:
        return entry
    if cp.get("sha256") == sha:
        entry["sha256"] = sha
        entry["mode"] = cp["mode"] if mode is None else mode
    return entry


EARLY = "run_in_background: the after-scan may have run before the command finished"


def background(payload: dict) -> bool:
    """Claude Code's Bash input carries `run_in_background` ("Whether to run the command in background",
    https://code.claude.com/docs/en/hooks, read 2026-11-12). The same page documents no hook event for a
    background shell finishing, so the after-scan of such a call may run while the command is still going:
    files it changes later are missing from this step's checkpoints."""
    ti = payload.get("tool_input")
    return isinstance(ti, dict) and ti.get("run_in_background") is True
