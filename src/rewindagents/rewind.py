"""Replay a recorded session step by step, rewind the working tree to any step, branch from a step.

A step is one tool call (its "pre" record, paired with the "post" record that answered it), or a
rewind/branch this module made. Steps are numbered from 1 within a session.

`rewind(N)` puts every checkpointed file back the way it was right after step N: for each file a
later step checkpointed, the first such checkpoint holds its bytes at that moment. A file that did not
exist then is deleted. Before changing anything, rewind checkpoints the current bytes of every file it
will touch and records itself as a step, so a rewind can be rewound too.

Safety: nothing is written unless the log's hash chain verifies and every stored copy still matches its
SHA-256. Files outside the project (the directory holding .rewindagents/) are never touched. A step whose
before/after scan did not finish (a Bash, Shell or apply_patch call in a project too big to scan, or one
whose post event never arrived) is counted and reported; the files it changed are not undone.

Later changes: the plan also lists, in p["drift"], every file it would restore or delete whose bytes changed
after the steps it takes back, by another session or outside any recorded step (by hand, by a tool with no
hook): the record of each step holds the file's hash right after it (hook.after_hash), so a file whose bytes
are not what the log last recorded was changed by someone else. A rewind would overwrite those changes, so
`rewind` refuses (DriftError) unless force=True; with force the current bytes are checkpointed as always, so
the rewind can itself be rewound. Logs written before after-hashes were recorded only show other sessions'
changes.

`rewind(N, only=[PATH, ...])` does the same for the named files only (a directory names every file under it):
the same checks, the same checkpoint of the current bytes, recorded as a step the same way. `diff.py` shows
what a rewind would change by reading the same plan(), so the two cannot disagree.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from . import log
from .hook import FILE_TOOLS, checkpoint, store_lock

STEP_EVENTS_SKIPPED = {"post"}


class RewindError(Exception):
    pass


class DriftError(RewindError):
    """A rewind would overwrite changes made after the steps it takes back. Carries the plan (p["drift"])."""

    def __init__(self, message: str, plan: dict):
        super().__init__(message)
        self.plan = plan


class StepRangeError(RewindError):
    """The step number is not one of the session's. The CLI exits 2 for it, as for any argument it cannot use."""


def range_message(n: int, session: str | None, count: int, lowest: int = 0) -> str:
    """One wording for an out-of-range step, in every command: the step, the session, the numbers it has."""
    if count < lowest:
        return f"step {n} is out of range: session {session} has no steps"
    return (f"step {n} is out of range: session {session} has {count} step{'s' if count != 1 else ''}, "
            f"so use {lowest}-{count}" + (" (0 = before the first step)" if lowest == 0 else "")
            + "; `replay` lists them")


UNKNOWN = object()      # a file's hash at some moment that the log does not hold


def project_root(log_path: str | Path) -> Path:
    """The directory whose .rewindagents/ holds this log."""
    return Path(log_path).resolve().parent.parent


def latest_session(log_path: str | Path) -> str | None:
    recs = log.read(log_path)
    return recs[-1]["session"] if recs else None


def steps(log_path: str | Path, session: str | None = None) -> list[dict]:
    """The session's steps in order. Default session: the one that wrote the last record."""
    session = session or latest_session(log_path)
    return steps_from(log.read(log_path, session))


def steps_from(recs: list[dict]) -> list[dict]:
    """Pair one session's records (in log order) into numbered steps: see steps()."""
    out: list[dict] = []
    open_calls: list[dict] = []
    for r in recs:
        if r.get("event") == "post":
            inp = (r.get("args") or {}).get("input")
            for s in open_calls:
                if s["tool"] == r["tool"] and s["input"] == inp:
                    s["result"] = r.get("result")
                    pargs = r.get("args") if isinstance(r.get("args"), dict) else {}
                    s["checkpoints"].extend(pargs.get("checkpoints") or [])
                    if "bash_scan" in pargs and "skipped" not in s.get("bash_scan", {}):
                        s["bash_scan"] = pargs["bash_scan"]   # a skip before the command says why
                    if isinstance(pargs.get("after"), list):
                        s["after"] = pargs["after"]           # each file's hash right after the call
                    open_calls.remove(s)
                    break
            continue
        args = r.get("args") if isinstance(r.get("args"), dict) else {}
        cps = list(args.get("checkpoints") or [])
        if args.get("checkpoint"):
            cps.append(args["checkpoint"])
        s = {"step": len(out) + 1, "seq": r["seq"], "event": r.get("event"), "tool": r["tool"],
             "input": args.get("input", r.get("args")), "checkpoints": cps, "result": None,
             "scanned": "bash_scan" in args}      # a before/after scan of the project was started for it
        if args.get("agent"):
            s["agent"] = args["agent"]
        if args.get("to_step") is not None:
            s["to_step"] = args["to_step"]
        if args.get("only"):
            s["only"] = args["only"]
        if args.get("branch"):
            s["branch"] = args["branch"]
        if r.get("event") != "pre" and isinstance(args.get("after"), list):
            s["after"] = args["after"]                        # a rewind's own record: what it left
        if isinstance(args.get("bash_scan"), dict) and "skipped" in args["bash_scan"]:
            s["bash_scan"] = args["bash_scan"]
        out.append(s)
        if r.get("event") == "pre":
            open_calls.append(s)
    return out


def relative(path: str | Path, root: Path | None) -> str:
    """The path relative to root when it is inside root, else unchanged."""
    if root is None:
        return str(path)
    try:
        return str(Path(path).resolve().relative_to(root))
    except (ValueError, OSError):
        return str(path)


def summary(step: dict, width: int = 80, root: Path | None = None) -> str:
    """One line describing what the step did."""
    inp = step.get("input")
    if step["event"] == "fork" and isinstance(inp, dict):
        text = f"run {inp.get('fork')} starts here: the files as they were right after step {inp.get('from_step')}"
    elif step["event"] in ("rewind", "branch"):
        text = f"rewound to step {step.get('to_step')}"
        if step.get("only"):
            text += f" (only {', '.join(step['only'])})"
        if step.get("branch"):
            text += f", branch {step['branch'].get('name')}"
    elif step["tool"] in FILE_TOOLS and isinstance(inp, dict):
        text = relative(inp.get(FILE_TOOLS[step["tool"]], ""), root)
    elif isinstance(inp, dict) and isinstance(inp.get("file_path"), str):
        text = relative(inp["file_path"], root)      # Read and other file tools: the file, not raw JSON
    elif isinstance(inp, dict) and "command" in inp:
        cmd = inp["command"]            # a string (Claude Code, Cursor) or a list of words
        text = " ".join(str(w) for w in cmd) if isinstance(cmd, list) else str(cmd)
    else:
        text = json.dumps(inp, ensure_ascii=False, default=str)
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 3] + "..."


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root)
        return True
    except ValueError:
        return False


def _matcher(only: list[str | Path], cwd: Path | None = None):
    """A test for "is this file one of the --only paths": the same file, or a file under a named directory.
    Relative paths are read from `cwd` (default: the current directory), as the user typed them."""
    base = Path(cwd) if cwd is not None else Path.cwd()
    wanted = [((base / q) if not Path(q).is_absolute() else Path(q)).resolve() for q in only]

    def hits(path_s: str) -> list[int]:
        f = Path(path_s).resolve()
        return [i for i, q in enumerate(wanted) if f == q or q in f.parents]
    return hits


def timeline(log_path: str | Path) -> list[dict]:
    """Every session's steps in one list, in log order, each with its "session"."""
    by: dict[str, list[dict]] = {}
    for r in log.read(log_path):
        by.setdefault(r["session"], []).append(r)
    out = []
    for sid, recs in by.items():
        for st in steps_from(recs):
            st["session"] = sid
            out.append(st)
    return sorted(out, key=lambda st: st["seq"])


def _before_of(step: dict, path_s: str):
    for cp in step["checkpoints"]:
        if cp["path"] == path_s:
            return UNKNOWN if cp.get("skipped") else cp.get("sha256")
    return UNKNOWN


def _after_of(step: dict, path_s: str):
    for a in step.get("after") or []:
        if isinstance(a, dict) and a.get("path") == path_s:
            return UNKNOWN if a.get("skipped") or "after" not in a else a["after"]
    return UNKNOWN


def _touches(step: dict, path_s: str) -> bool:
    return any(cp["path"] == path_s for cp in step["checkpoints"]) or \
        any(isinstance(a, dict) and a.get("path") == path_s for a in step.get("after") or [])


def sha_now(path: Path) -> str | None:
    """The file's SHA-256 now, None when it is absent."""
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def drift(log_path: str | Path, session: str, first_seq: dict[str, int],
          all_steps: list[dict] | None = None) -> list[dict]:
    """The files of `first_seq` ({path: seq of the first step the plan takes back for it}) that changed after
    that step other than by this session's own steps: by a step of another session, or outside any recorded
    step (a step's hash before it is not the previous step's hash after it, or the file now is not what the
    last step left). One entry per such file: path, sessions [(session, step)], outside (bool)."""
    if not first_seq:
        return []
    tl = all_steps if all_steps is not None else timeline(log_path)
    out = []
    for path_s, seq0 in first_seq.items():
        expect: Any = UNKNOWN
        outside, others = False, []
        for st in tl:
            if st["seq"] < seq0 or not _touches(st, path_s):
                continue
            before = _before_of(st, path_s)
            if st["seq"] != seq0 and expect is not UNKNOWN and before is not UNKNOWN and before != expect:
                outside = True
            if st["session"] != session:
                others.append((st["session"], st["step"]))
            expect = _after_of(st, path_s)
        if expect is not UNKNOWN and sha_now(Path(path_s)) != expect:
            outside = True
        if outside or others:
            out.append({"path": path_s, "sessions": others, "outside": outside})
    return out


def drift_why(d: dict) -> str:
    """One drift entry in words: who changed the file after the steps a rewind takes back."""
    parts = [f"by session {sid[:8]} step {n}" for sid, n in d["sessions"]]
    if d["outside"]:
        parts.append("outside any recorded step (by hand, or by a tool with no hook)")
    return "changed " + ", and ".join(parts) if parts else "changed"


def plan(log_path: str | Path, n: int, session: str | None = None,
         only: list[str | Path] | None = None) -> dict:
    """Work out what rewinding to step n would change. Reads only.

    With `only`, the plan covers just those files (or the files under those directories); `p["unmatched"]`
    lists the `only` entries that no step after n changed, so they are already as they were at step n
    (as far as the log knows)."""
    ok, _, msg, torn_only = log.check(log_path)
    if not ok and not torn_only:
        raise RewindError(f"log does not verify ({msg}); refusing to rewind from it")
    session = session or latest_session(log_path)
    all_steps = steps(log_path, session)
    if not 0 <= n <= len(all_steps):
        raise StepRangeError(range_message(n, session, len(all_steps)))
    root = project_root(log_path)
    objects = root / ".rewindagents" / "objects"
    first: dict[str, dict] = {}
    first_seq: dict[str, int] = {}
    for s in all_steps[n:]:
        for cp in s["checkpoints"]:
            if cp["path"] not in first:
                first[cp["path"]] = cp
                first_seq[cp["path"]] = s["seq"]
    unmatched: list[str] = []
    if only:
        hits = _matcher(only)
        matched: set[int] = set()
        kept = {}
        for path_s, cp in first.items():
            h = hits(path_s)
            if h:
                kept[path_s] = cp
                matched.update(h)
        first = kept
        unmatched = [str(q) for i, q in enumerate(only) if i not in matched]
    p: dict[str, Any] = {"session": session, "to_step": n, "steps": len(all_steps),
                         "restore": [], "delete": [], "cannot": [], "modes": {},
                         # steps whose before/after scan did not finish: Bash, or any Codex/Cursor call that
                         # was scanned (see agents.scans), without a "changed" count from the post event
                         "bash_uncovered": sum(1 for s in all_steps[n:] if (s["tool"] == "Bash" or s.get("scanned"))
                                               and "changed" not in (s.get("bash_scan") or {})),
                         # background commands whose after-scan may have run before they finished (bashscan.EARLY)
                         "scan_early": sum(1 for s in all_steps[n:] if (s.get("bash_scan") or {}).get("early")),
                         "only": [str(q) for q in only] if only else None, "unmatched": unmatched,
                         # every record verifies, but a write was cut off: the call it recorded is not in the log
                         "torn": None if ok else msg}
    for path_s, cp in first.items():
        path = Path(path_s)
        if not _inside(path, root):
            p["cannot"].append((path_s, "outside the project"))
        elif cp.get("skipped"):
            p["cannot"].append((path_s, f"not checkpointed ({cp['skipped']})"))
        elif cp.get("sha256") is None:
            if path.exists():
                p["delete"].append(path_s)
        else:
            obj = objects / cp["sha256"]
            if not obj.is_file() or hashlib.sha256(obj.read_bytes()).hexdigest() != cp["sha256"]:
                p["cannot"].append((path_s, "stored copy missing or altered"))
            elif (not path.is_file() or path.read_bytes() != obj.read_bytes()
                  or ("mode" in cp and path.stat().st_mode & 0o777 != cp["mode"])):
                p["restore"].append((path_s, cp["sha256"]))
                if "mode" in cp:            # recorded since takeback-bench S11; older records hold no mode
                    p["modes"][path_s] = cp["mode"]
    # only a file that is there now can lose bytes: restoring a file that is absent overwrites nothing
    touched = {path_s for path_s, _ in p["restore"] if Path(path_s).is_file()} | set(p["delete"])
    p["drift"] = drift(log_path, session, {q: first_seq[q] for q in first_seq if q in touched})
    return p


def _apply(log_path: str | Path, p: dict, event: str, extra: dict | None = None) -> dict:
    root = project_root(log_path)
    objects = root / ".rewindagents" / "objects"
    touched = [path for path, _ in p["restore"]] + p["delete"]
    with store_lock(root / ".rewindagents"):  # `gc` must not delete these copies before the record names them
        saved = [checkpoint(Path(path), objects) for path in touched]
        after = [{"path": path_s, "after": sha} for path_s, sha in p["restore"]] + \
            [{"path": path_s, "after": None} for path_s in p["delete"]]
        args = {"input": {"to_step": p["to_step"]}, "to_step": p["to_step"], "checkpoints": saved,
                "after": after}
        if p.get("only"):
            args["input"]["only"] = args["only"] = [relative(q, root) for q in p["only"]]
        args.update(extra or {})
        rec = log.Recorder(log_path).record(p["session"], "rewindagents", args, None,
                                            actor="user", event=event)
    for path_s, sha in p["restore"]:
        path = Path(path_s)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.rewindagents.tmp")
        tmp.write_bytes((objects / sha).read_bytes())
        if path_s in p.get("modes", {}):
            os.chmod(tmp, p["modes"][path_s])
        os.replace(tmp, path)
    for path_s in p["delete"]:
        Path(path_s).unlink()
    return rec


def refuse_drift(p: dict, log_path: str | Path) -> None:
    """Raise DriftError when the plan would overwrite later changes (p["drift"])."""
    if not p.get("drift"):
        return
    root = project_root(log_path)
    files = "; ".join(f"{relative(d['path'], root)} ({drift_why(d)})" for d in p["drift"])
    raise DriftError(f"nothing changed: {len(p['drift'])} file(s) changed after the steps this rewind takes "
                     f"back, and rewinding would overwrite that: {files}. `diff {p['to_step']}` shows it; "
                     f"`rewind {p['to_step']} --force` does it anyway, keeping the current bytes as a step so it "
                     f"can be undone", p)


def rewind(log_path: str | Path, n: int, session: str | None = None, dry_run: bool = False,
           only: list[str | Path] | None = None, force: bool = False) -> dict:
    """Put files back as they were right after step n (all of them, or just `only`). See plan().
    Refuses (DriftError) when that would overwrite later changes (p["drift"]), unless force or dry_run."""
    p = plan(log_path, n, session, only)
    if only and len(p["unmatched"]) == len(only):
        raise RewindError(f"no step after step {n} changed {', '.join(map(str, only))}; nothing to put back "
                          f"(`replay` lists the steps and their files)")
    if not dry_run and not force:
        refuse_drift(p, log_path)
    if not dry_run:
        p["record"] = _apply(log_path, p, "rewind")["seq"]
    return p


def _git(root: Path, *args: str, env: dict | None = None) -> str:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                          check=True, env=env).stdout.strip()


def git_snapshot(root: Path, name: str) -> str | None:
    """Commit the whole working tree (tracked + untracked, minus ignored) to refs/heads/rewindagents/<name>.

    Uses a throwaway index, so the user's index, HEAD and current branch are left alone.
    Returns the commit id, or None if root is not a git work tree.
    """
    try:
        if _git(root, "rev-parse", "--is-inside-work-tree") != "true":
            return None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    ref = f"refs/heads/rewindagents/{name}"
    try:
        _git(root, "check-ref-format", ref)
    except subprocess.CalledProcessError:
        raise RewindError(f"{name!r} is not a valid branch name")
    try:
        _git(root, "rev-parse", "--verify", "--quiet", ref)
        raise RewindError(f"branch rewindagents/{name} already exists")
    except subprocess.CalledProcessError:
        pass
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(d, "index")),
                   GIT_AUTHOR_NAME="rewindagents", GIT_AUTHOR_EMAIL="rewindagents@localhost",
                   GIT_COMMITTER_NAME="rewindagents", GIT_COMMITTER_EMAIL="rewindagents@localhost")
        _git(root, "add", "-A", ".", env=env)
        tree = _git(root, "write-tree", env=env)
        parent: list[str] = []
        try:
            parent = ["-p", _git(root, "rev-parse", "--verify", "--quiet", "HEAD")]
        except subprocess.CalledProcessError:
            pass
        commit = _git(root, "commit-tree", tree, *parent, "-m",
                      f"rewindagents: working tree before branching ({name})", env=env)
    _git(root, "update-ref", ref, commit)
    return commit


def branch(log_path: str | Path, n: int, name: str, session: str | None = None, force: bool = False) -> dict:
    """Keep the current timeline, then rewind to step n so the agent can try again from there.

    The current files are always checkpointed in the log (as for rewind). In a git work tree the whole
    working tree is also committed to the branch rewindagents/<name>, without touching HEAD or the index.
    """
    p = plan(log_path, n, session)
    if not force:
        refuse_drift(p, log_path)
    commit = git_snapshot(project_root(log_path), name)
    info = {"name": name, "git_ref": f"rewindagents/{name}" if commit else None, "commit": commit}
    p["branch"] = info
    p["record"] = _apply(log_path, p, "branch", {"branch": info})["seq"]
    return p
