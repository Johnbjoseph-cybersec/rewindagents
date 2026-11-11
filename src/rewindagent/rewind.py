"""Replay a recorded session step by step, rewind the working tree to any step, branch from a step.

A step is one tool call (its "pre" record, paired with the "post" record that answered it), or a
rewind/branch this module made. Steps are numbered from 1 within a session.

`rewind(N)` puts every checkpointed file back the way it was right after step N: for each file a
later step checkpointed, the first such checkpoint holds its bytes at that moment. A file that did not
exist then is deleted. Before changing anything, rewind checkpoints the current bytes of every file it
will touch and records itself as a step, so a rewind can be rewound too.

Safety: nothing is written unless the log's hash chain verifies and every stored copy still matches its
SHA-256. Files outside the project (the directory holding .rewindagent/) are never touched. A step whose
before/after scan did not finish (a Bash, Shell or apply_patch call in a project too big to scan, or one
whose post event never arrived) is counted and reported; the files it changed are not undone.
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
from .hook import FILE_TOOLS, checkpoint

STEP_EVENTS_SKIPPED = {"post"}


class RewindError(Exception):
    pass


def project_root(log_path: str | Path) -> Path:
    """The directory whose .rewindagent/ holds this log."""
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
        if args.get("branch"):
            s["branch"] = args["branch"]
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
    if step["event"] in ("rewind", "branch"):
        text = f"rewound to step {step.get('to_step')}"
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


def plan(log_path: str | Path, n: int, session: str | None = None) -> dict:
    """Work out what rewinding to step n would change. Reads only."""
    ok, _, msg = log.verify(log_path)
    if not ok:
        raise RewindError(f"log does not verify ({msg}); refusing to rewind from it")
    session = session or latest_session(log_path)
    all_steps = steps(log_path, session)
    if not 0 <= n <= len(all_steps):
        raise RewindError(f"step {n} is out of range: session {session} has {len(all_steps)} steps")
    root = project_root(log_path)
    objects = root / ".rewindagent" / "objects"
    first: dict[str, dict] = {}
    for s in all_steps[n:]:
        for cp in s["checkpoints"]:
            first.setdefault(cp["path"], cp)
    p: dict[str, Any] = {"session": session, "to_step": n, "steps": len(all_steps),
                         "restore": [], "delete": [], "cannot": [],
                         # steps whose before/after scan did not finish: Bash, or any Codex/Cursor call that
                         # was scanned (see agents.scans), without a "changed" count from the post event
                         "bash_uncovered": sum(1 for s in all_steps[n:] if (s["tool"] == "Bash" or s.get("scanned"))
                                               and "changed" not in (s.get("bash_scan") or {}))}
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
            elif not path.is_file() or path.read_bytes() != obj.read_bytes():
                p["restore"].append((path_s, cp["sha256"]))
    return p


def _apply(log_path: str | Path, p: dict, event: str, extra: dict | None = None) -> dict:
    root = project_root(log_path)
    objects = root / ".rewindagent" / "objects"
    touched = [path for path, _ in p["restore"]] + p["delete"]
    saved = [checkpoint(Path(path), objects) for path in touched]
    args = {"input": {"to_step": p["to_step"]}, "to_step": p["to_step"], "checkpoints": saved}
    args.update(extra or {})
    rec = log.Recorder(log_path).record(p["session"], "rewindagent", args, None,
                                        actor="user", event=event)
    for path_s, sha in p["restore"]:
        path = Path(path_s)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.rewindagent.tmp")
        tmp.write_bytes((objects / sha).read_bytes())
        os.replace(tmp, path)
    for path_s in p["delete"]:
        Path(path_s).unlink()
    return rec


def rewind(log_path: str | Path, n: int, session: str | None = None, dry_run: bool = False) -> dict:
    p = plan(log_path, n, session)
    if not dry_run:
        p["record"] = _apply(log_path, p, "rewind")["seq"]
    return p


def _git(root: Path, *args: str, env: dict | None = None) -> str:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                          check=True, env=env).stdout.strip()


def git_snapshot(root: Path, name: str) -> str | None:
    """Commit the whole working tree (tracked + untracked, minus ignored) to refs/heads/rewindagent/<name>.

    Uses a throwaway index, so the user's index, HEAD and current branch are left alone.
    Returns the commit id, or None if root is not a git work tree.
    """
    try:
        if _git(root, "rev-parse", "--is-inside-work-tree") != "true":
            return None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    ref = f"refs/heads/rewindagent/{name}"
    try:
        _git(root, "check-ref-format", ref)
    except subprocess.CalledProcessError:
        raise RewindError(f"{name!r} is not a valid branch name")
    try:
        _git(root, "rev-parse", "--verify", "--quiet", ref)
        raise RewindError(f"branch rewindagent/{name} already exists")
    except subprocess.CalledProcessError:
        pass
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(d, "index")),
                   GIT_AUTHOR_NAME="rewindagent", GIT_AUTHOR_EMAIL="rewindagent@localhost",
                   GIT_COMMITTER_NAME="rewindagent", GIT_COMMITTER_EMAIL="rewindagent@localhost")
        _git(root, "add", "-A", ".", env=env)
        tree = _git(root, "write-tree", env=env)
        parent: list[str] = []
        try:
            parent = ["-p", _git(root, "rev-parse", "--verify", "--quiet", "HEAD")]
        except subprocess.CalledProcessError:
            pass
        commit = _git(root, "commit-tree", tree, *parent, "-m",
                      f"rewindagent: working tree before branching ({name})", env=env)
    _git(root, "update-ref", ref, commit)
    return commit


def branch(log_path: str | Path, n: int, name: str, session: str | None = None) -> dict:
    """Keep the current timeline, then rewind to step n so the agent can try again from there.

    The current files are always checkpointed in the log (as for rewind). In a git work tree the whole
    working tree is also committed to the branch rewindagent/<name>, without touching HEAD or the index.
    """
    p = plan(log_path, n, session)
    commit = git_snapshot(project_root(log_path), name)
    info = {"name": name, "git_ref": f"rewindagent/{name}" if commit else None, "commit": commit}
    p["branch"] = info
    p["record"] = _apply(log_path, p, "branch", {"branch": info})["seq"]
    return p
