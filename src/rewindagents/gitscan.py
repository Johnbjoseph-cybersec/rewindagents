"""The Bash scan for big git projects: ask git what is dirty instead of reading every file twice.

bashscan.py looks at every project file before and after a command. That is a stat per file, twice: fine at
10,000 files (about 70 ms), 13 s at 2,000,000. In a git work tree whose top is the project, this module does it
with `git status` instead, whose cost git itself keeps low (untracked cache, and for the biggest projects its
built-in fsmonitor, both switched on per command with `-c`; nothing is written to the repository's config):

- before the command: `git status` lists the files that are already dirty, untracked or ignored one by one
  (D0). Their bytes go into the object store, as bashscan does for every file, and the pending scan keeps the
  list, the HEAD commit and each file's hash. A file git does not list is clean: its bytes are the ones in HEAD
  (no staged change, no edit), so they need not be read now;
- after: `git status` again (D1), and, if HEAD moved (checkout, reset, commit, pull), the files that differ
  between the two commits. A file can have been changed only if it is in D0, in D1 or in that difference. Each is
  compared with its state before: the pending scan's hash for a file in D0, its blob in the old HEAD otherwise
  (written into the store only if the command changed it). The checkpoints and "after" entries are the ones
  bashscan.after makes, so rewind, revert, gc and bundle see no difference.

What this does not see: files marked `skip-worktree` or `assume-unchanged` (git itself does not look at them),
and files inside submodules (bashscan's scan does not either; a submodule is a directory).

Line-ending conversion and filters. A clean file's bytes are its blob only when no conversion applies. The
scan therefore takes the old whole-project path when the project has at most bashscan.MAX_SCAN_FILES files and a
conversion is configured (core.autocrlf true/input, or a text/eol/ident/filter/working-tree-encoding attribute in
the root .gitattributes, .git/info/attributes or core.attributesFile). Larger projects (and a nested
.gitattributes anywhere) take the blob as `git checkout` would write it (`git cat-file --filters`), which is the
file's bytes except for a clean file with mixed line endings; a file with an external `filter=` is recorded as
skipped rather than guessed.

Not a git work tree, git missing or failing, or the project not at the top of the repository: unchanged, the
old scan with its 20,000-file limit. So are git projects of up to 20,000 tracked files (as fast, and exact).
REWINDAGENTS_BASH_SCAN=full forces the old scan everywhere, =git the git path at any size (used to compare the two).
"""
from __future__ import annotations

import json
import os
import stat

from . import bashscan
from .bashscan import GIT_KEY, MAX_SCAN_FILES, _under_skip, snapshot_found
from .hook import MAX_CHECKPOINT_BYTES
from .log import sha256

MAX_GIT_FILES = 2_000_000        # tracked files (the index's entry count)
MAX_GIT_DIRTY = 200_000          # files git lists as dirty, untracked or ignored, or that differ between two HEADs
FSMONITOR_FROM = 200_000         # tracked files from which git's built-in fsmonitor is switched on for the command
UNTRACKED_CACHE_FROM = 50_000    # ... and its untracked cache
INDEX = "index.git.json"
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
CONVERT_ATTRS = ("text", "eol", "ident", "filter", "working-tree-encoding")


def _git(root, *args, data=None, cfg=(), literal=False, timeout=300):
    """stdout of `git -C root <args>`, or None if git cannot run it or it fails."""
    import subprocess
    cmd = ["git"] + (["--literal-pathspecs"] if literal else [])
    for c in cfg:
        cmd += ["-c", c]
    cmd += ["-C", str(root), *args]
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    try:
        p = subprocess.run(cmd, input=data, capture_output=True, timeout=timeout, env=env)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout if p.returncode == 0 else None


def _text(b: bytes) -> str:
    return b.decode("utf-8", "surrogateescape")


class Plan:
    """What the git path needs to know about the project: how many tracked files, whether to speed git up."""

    def __init__(self, count: int, risk: bool):
        self.count, self.risk = count, risk
        self.cfg: list[str] = []
        if count >= UNTRACKED_CACHE_FROM:
            self.cfg.append("core.untrackedCache=true")
        if count >= FSMONITOR_FROM and os.environ.get("REWINDAGENTS_FSMONITOR") != "0":
            self.cfg.append("core.fsmonitor=true")


def plan(root) -> Plan | None:
    """A Plan when the git path applies to this project, else None (the old scan)."""
    out = _git(root, "rev-parse", "--show-toplevel", "--git-path", "index", timeout=20)
    if out is None:
        return None
    lines = _text(out).split("\n")
    if len(lines) < 2 or os.path.realpath(lines[0]) != os.path.realpath(str(root)):
        return None                        # a subdirectory of a bigger repository: paths would differ
    index = lines[1] if os.path.isabs(lines[1]) else os.path.join(str(root), lines[1])
    try:
        with open(index, "rb") as fh:
            head = fh.read(12)
    except FileNotFoundError:
        head = b"DIRC" + bytes(8)          # nothing added yet
    except OSError:
        return None
    if head[:4] != b"DIRC":
        return None
    count = int.from_bytes(head[8:12], "big")
    # Up to the old limit the whole-project scan is as fast (about 70 ms at 10,000 files, against a handful of git
    # processes here) and exact; the git path is for the projects it could not scan at all.
    if count <= (-1 if os.environ.get("REWINDAGENTS_BASH_SCAN") == "git" else MAX_SCAN_FILES):
        return None
    risk = _conversion_configured(root)
    if risk and count <= MAX_SCAN_FILES:
        return None                        # small enough for the exact old scan
    return Plan(count, risk)


def _conversion_configured(root) -> bool:
    for key in ("core.autocrlf",):
        v = _git(root, "config", "--get", key, timeout=20)
        if v and _text(v).strip().lower() in ("true", "input"):
            return True
    files = [os.path.join(str(root), ".gitattributes")]
    info = _git(root, "rev-parse", "--git-path", "info/attributes", timeout=20)
    if info:
        p = _text(info).strip()
        files.append(p if os.path.isabs(p) else os.path.join(str(root), p))
    af = _git(root, "config", "--get", "core.attributesfile", timeout=20)
    if af:
        files.append(os.path.expanduser(_text(af).strip()))
    for f in files:
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    for t in line.split()[1:]:
                        if (t in ("text", "ident", "crlf") or t.startswith(("text=", "eol=", "filter=", "crlf=",
                                                                              "working-tree-encoding="))):
                            return True
        except OSError:
            pass
    return False


def _status(root, pl: Plan):
    """{relative path: kind} for every path `git status` lists: kind "t" (tracked, with any change), "?" untracked
    file, "!" ignored file (a directory git ignores as a whole is not listed). None when git fails."""
    # Ignored files cost git a walk of every directory (no cache helps): about the time of `find` over the tree.
    # REWINDAGENTS_IGNORED=skip leaves them out (a deleted dotenv file is then not checkpointed) and lets git use
    # its untracked cache, which only works for --untracked-files=normal; the untracked directories that shows
    # collapsed ("dir/") are listed below.
    quick = os.environ.get("REWINDAGENTS_IGNORED") == "skip"
    args = ["status", "--porcelain=v2", "-z", "--untracked-files=" + ("normal" if quick else "all"),
            "--ignored=" + ("no" if quick else "matching"), "--ignore-submodules=all", "--no-renames"]
    out = _git(root, *args, cfg=pl.cfg)
    if out is None and "core.fsmonitor=true" in pl.cfg:
        pl.cfg.remove("core.fsmonitor=true")      # not supported here: carry on without it
        out = _git(root, *args, cfg=pl.cfg)
    if out is None:
        return None
    found: dict[str, str] = {}
    collapsed: list[str] = []
    for rec in _text(out).split("\0"):
        if len(rec) < 3:
            continue
        c = rec[0]
        if c == "1":
            found[rec.split(" ", 8)[8]] = "t"
        elif c == "u":
            found[rec.split(" ", 10)[10]] = "t"
        elif c in "?!":
            p = rec[2:]
            if p.endswith("/"):
                if quick and c == "?":
                    collapsed.append(p)
            elif not _under_skip(p):
                found[p] = c
    if collapsed:
        for i in range(0, len(collapsed), 300):
            res = _git(root, "ls-files", "-z", "--others", "--exclude-standard", "--", *collapsed[i:i + 300],
                       literal=True)
            if res is None:
                return None
            for p in _text(res).split("\0"):
                if p and not _under_skip(p):
                    found[p] = "?"
    return found


def _head(root) -> str | None:
    out = _git(root, "rev-parse", "--verify", "-q", "HEAD", timeout=20)
    return _text(out).strip() if out else None


def _real_files(root, rels) -> list:
    """(rel, lstat) for the regular, non-symlink files among rels, as bashscan._scan sees them."""
    base, found = str(root), []
    for r in sorted(rels):
        if r.split("/", 1)[0] in (".git", ".rewindagents"):
            continue
        try:
            st = os.lstat(os.path.join(base, r))
        except OSError:
            continue
        if stat.S_ISREG(st.st_mode):
            found.append((r, st))
    return found


def before(payload, root, store):
    """Pre record for the command, or None when this project takes the old scan."""
    pl = plan(root)
    if pl is None:
        return None
    if pl.count > MAX_GIT_FILES:
        return {"skipped": f"more than {MAX_GIT_FILES:,} files"}
    d0 = _status(root, pl)
    if d0 is None:
        return None
    if len(d0) > MAX_GIT_DIRTY:
        return {"skipped": f"more than {MAX_GIT_DIRTY:,} changed, untracked or ignored files"}
    head = _head(root)
    snap = snapshot_found(root, store, _real_files(root, d0), save=True, index_name=INDEX)
    snap[GIT_KEY] = {"head": head, "dirty": sorted(d0), "risk": pl.risk}
    pending = store / "pending"
    pending.mkdir(parents=True, exist_ok=True)
    key = bashscan._key(payload)
    tmp = pending / f".{key}.{os.getpid()}.tmp"
    tmp.write_text(json.dumps(snap), encoding="utf-8")
    os.replace(tmp, pending / f"{key}.json")
    rec = {"files": pl.count + sum(1 for k in d0.values() if k != "t"), "pending": key, "git": True}
    return rec


def after(payload, root, store, afters, old):
    """Post record's scan and checkpoints for a command whose pending scan came from before()."""
    meta = old.pop(GIT_KEY)
    head0, dirty0 = meta.get("head"), set(meta.get("dirty") or [])
    pl = plan_for_after(root, meta)
    d1 = _status(root, pl)
    if d1 is None:
        return {"skipped": "git status failed after the command"}, []
    if len(d1) > MAX_GIT_DIRTY:
        return {"skipped": f"more than {MAX_GIT_DIRTY:,} changed, untracked or ignored files"}, []
    cand = set(dirty0) | set(d1)
    head1 = _head(root)
    if head1 != head0:
        diff = _git(root, "diff-tree", "-r", "--name-only", "-z", "--no-renames", head0 or EMPTY_TREE,
                    head1 or EMPTY_TREE)
        if diff is None:
            return {"skipped": "git could not list the files that differ between the two commits"}, []
        names = [x for x in _text(diff).split("\0") if x]
        if len(names) > MAX_GIT_DIRTY:
            return {"skipped": f"more than {MAX_GIT_DIRTY:,} files differ between the two commits"}, []
        cand |= set(names)
    cand = {c for c in cand if c.split("/", 1)[0] not in (".git", ".rewindagents")}
    new = snapshot_found(root, store, _real_files(root, cand), save=False, index_name=INDEX)
    was_map: dict = {}
    from_head = []
    for c in cand:
        if c in dirty0:
            was_map[c] = old.get(c)                    # None: the file was absent when the command began
        else:
            from_head.append(c)
    was_map.update(_from_head(root, store, head0, from_head, new, meta.get("risk", False)))
    cps: list[dict] = []
    from pathlib import Path
    for r in sorted(cand):
        was, now = was_map.get(r), new.get(r)
        if was == now:
            continue
        path = str(root / r)
        if was is None:
            cps.append({"path": path, "sha256": None})
        elif isinstance(was, dict):
            cps.append({"path": path, "sha256": None, "skipped": was["skipped"]})
        else:
            sha, mode = bashscan._split(was)
            cp = {"path": path, "sha256": sha}
            if mode is not None:
                cp["mode"] = mode
            cps.append(cp)
        if afters is not None:
            if isinstance(now, dict):
                afters.append({"path": path, "skipped": now["skipped"]})
            elif now is None:
                afters.append({"path": path, "after": None})
            else:
                afters.append(bashscan._after_copy(Path(path), store / "objects", *bashscan._split(now)))
    scan = {"changed": len(cps)}
    if bashscan.background(payload):
        scan["early"] = bashscan.EARLY
    return scan, cps


def plan_for_after(root, meta) -> Plan:
    out = _git(root, "rev-parse", "--git-path", "index", timeout=20)
    count = 0
    if out:
        p = _text(out).strip()
        try:
            with open(p if os.path.isabs(p) else os.path.join(str(root), p), "rb") as fh:
                count = int.from_bytes(fh.read(12)[8:12], "big")
        except OSError:
            pass
    return Plan(count, bool(meta.get("risk")))


def _umask() -> int:
    m = os.umask(0)
    os.umask(m)
    return m


def _from_head(root, store, head, rels, now_map, risk) -> dict:
    """{rel: "<sha256>:<mode>" | {"skipped"} | None} for files that were clean when the command began: what
    `head` holds for each. A file the command changed or deleted has its bytes put in the store."""
    out: dict = {}
    if not rels:
        return out
    if head is None:
        return {r: None for r in rels}
    rels = sorted(rels)
    entries: dict[str, tuple[str, bool, int]] = {}      # rel -> (blob sha1, executable, size)
    for i in range(0, len(rels), 300):
        res = _git(root, "ls-tree", "-z", "-l", head, "--", *rels[i:i + 300], literal=True)
        if res is None:
            for r in rels[i:i + 300]:
                out[r] = {"skipped": "git could not read the file as it was before the command"}
            continue
        for rec in _text(res).split("\0"):
            if not rec:
                continue
            meta, _, path = rec.partition("\t")
            mode, typ, sha1, size = meta.split()
            if typ == "blob" and mode in ("100644", "100755"):
                entries[path] = (sha1, mode == "100755", int(size))
    convert = _needs_conversion(root, entries) if entries else {}
    filemode = _git(root, "config", "--bool", "core.fileMode", timeout=20)
    filemode = filemode is None or _text(filemode).strip() != "false"
    um = _umask()
    raw = []
    for r in rels:
        e = entries.get(r)
        if e is None:
            if r not in out:
                out[r] = None                           # not a regular file in head: absent before
            continue
        sha1, exe, size = e
        if size > MAX_CHECKPOINT_BYTES:
            out[r] = {"skipped": f"larger than {MAX_CHECKPOINT_BYTES} bytes"}
        elif convert.get(r) == "filter":
            out[r] = {"skipped": "a git filter converts this file; its bytes before the command are not known"}
        elif convert.get(r) or risk:
            data = _git(root, "cat-file", "--filters", f"--path={r}", sha1)
            if data is None:
                out[r] = {"skipped": "git could not read the file as it was before the command"}
            else:
                out[r] = _was(store, r, data, exe, now_map.get(r), filemode, um)
        else:
            raw.append(r)
    if raw:
        res = _git(root, "cat-file", "--batch", data=("\n".join(entries[r][0] for r in raw) + "\n").encode())
        pos = 0
        for r in raw:
            if res is None:
                out[r] = {"skipped": "git could not read the file as it was before the command"}
                continue
            try:
                nl = res.index(b"\n", pos)
                size = int(res[pos:nl].split()[2])
            except (ValueError, IndexError):
                out[r] = {"skipped": "git could not read the file as it was before the command"}
                res = None
                continue
            data = res[nl + 1:nl + 1 + size]
            pos = nl + 1 + size + 1
            out[r] = _was(store, r, data, entries[r][1], now_map.get(r), filemode, um)
    return out


def _needs_conversion(root, entries) -> dict:
    """{rel: True | "filter"} for the entries a .gitattributes converts on checkout (absent: none)."""
    res = _git(root, "check-attr", "-z", "--stdin", *CONVERT_ATTRS,
               data="".join(p + "\0" for p in entries).encode("utf-8", "surrogateescape"))
    conv: dict = {}
    if res is None:
        return {p: True for p in entries}
    t = _text(res).split("\0")
    for i in range(0, len(t) - 2, 3):
        path, attr, val = t[i], t[i + 1], t[i + 2]
        if val in ("unspecified", "unset"):
            continue
        if attr == "text" and val == "false":
            continue
        conv[path] = "filter" if attr == "filter" else (conv.get(path) or True)
    return conv


def _was(store, rel, data: bytes, exe: bool, now, filemode: bool, um: int):
    """The pending-scan value for a file whose bytes before the command were `data`. When the file is as it was
    now, nothing is written; otherwise the bytes go into the store, which is what the checkpoint names."""
    sha = sha256(data).hexdigest()
    cur = None
    if isinstance(now, str):
        cur = bashscan._split(now)
    cur_mode = cur[1] if cur and cur[1] is not None else None
    if cur_mode is not None:
        mode = cur_mode
        if filemode:
            mode = (mode | 0o111) if exe else (mode & ~0o111)
    else:
        mode = (0o777 if exe else 0o666) & ~um
    value = "%s:%o" % (sha, mode)
    if value != now:
        objects = store / "objects"
        obj = objects / sha
        if not obj.exists():
            objects.mkdir(parents=True, exist_ok=True)
            tmp = objects / f".{sha}.{os.getpid()}.tmp"
            tmp.write_bytes(data)
            os.replace(tmp, obj)
    return value


def too_big(root) -> bool | None:
    """True when the project has more files than shell commands can be checkpointed for. None: not a git path."""
    pl = plan(root)
    return None if pl is None else pl.count > MAX_GIT_FILES
