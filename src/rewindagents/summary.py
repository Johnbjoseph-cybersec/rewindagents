"""`rewindagents summary`: what did the agent just do, in a few lines, and how to take it back.

The question after a run is rarely "which tool calls" (that is `replay`) but "which files are different now,
by how much, and how do I undo it". So the summary is the net change of one session: every file whose bytes
now differ from before the session's first step (created, changed, deleted), with lines added and removed
and the steps that touched it, then the three commands that undo it. It is read from the same plan
`rewind 0` acts on (rewind.plan), so the list is exactly what `rewind 0` would put back. A file the session
changed and then changed back is not listed: nothing about it is different now. Reads only.
"""
from __future__ import annotations

from pathlib import Path

from . import rewind, sessions
from .runs import _plus_minus

SHOW = 20                       # files listed before "... and N more"
USER_EVENTS = ("rewind", "branch", "revert", "fork")


def summarize(log_path: str | Path, session: str | None = None) -> dict:
    session = session or rewind.latest_session(log_path)
    all_steps = rewind.steps(log_path, session)
    root = rewind.project_root(log_path)
    objects = root / ".rewindagents" / "objects"
    p = rewind.plan(log_path, 0, session)
    by_path: dict[str, list[int]] = {}
    for s in all_steps:
        for cp in s["checkpoints"]:
            nums = by_path.setdefault(cp["path"], [])
            if s["step"] not in nums:
                nums.append(s["step"])
    files = []
    for path_s, sha in p["restore"]:
        path = Path(path_s)
        now = path.read_bytes() if path.is_file() else None
        before = (objects / sha).read_bytes()
        files.append({"path": path_s, "kind": "deleted" if now is None else "changed",
                      "lines": _plus_minus(before, now), "steps": by_path.get(path_s, [])})
    for path_s in p["delete"]:
        path = Path(path_s)
        files.append({"path": path_s, "kind": "created", "lines": _plus_minus(None, path.read_bytes()),
                      "steps": by_path.get(path_s, [])})
    order = {"deleted": 0, "changed": 1, "created": 2}
    files.sort(key=lambda f: (order[f["kind"]], f["path"]))
    agent_steps = [s for s in all_steps if s["event"] not in USER_EVENTS]
    changers = [s["step"] for s in agent_steps if s["checkpoints"]]
    info = next((e for e in sessions.sessions(log_path) if e["session"] == session), None)
    return {"session": session, "steps": len(all_steps), "root": root, "files": files, "cannot": p["cannot"],
            "drift": p["drift"], "uncovered": p["bash_uncovered"], "early": p["scan_early"],
            "agents": sorted({s["agent"] for s in all_steps if s.get("agent")}),
            "commands": sum(1 for s in agent_steps if isinstance(s.get("input"), dict) and "command" in s["input"]),
            "last_changer": changers[-1] if changers else None,
            "first": info["first"] if info else None, "last": info["last"] if info else None,
            "others": sum(1 for e in sessions.sessions(log_path) if e["session"] != session)}


def _lines_text(f: dict) -> str:
    if f["lines"] is None:
        return "binary"
    plus, minus = f["lines"]
    if f["kind"] == "created":
        return f"+{plus}"
    if f["kind"] == "deleted":
        return f"-{minus}"
    return f"+{plus} -{minus}"


def _steps_text(nums: list[int]) -> str:
    if not nums:
        return ""
    return ("step " if len(nums) == 1 else "steps ") + ", ".join(map(str, nums[:6])) + (" ..." if len(nums) > 6 else "")


def lines(d: dict, run: str = "rewindagents", explicit_session: bool = False) -> list[str]:
    root = d["root"]
    sid = d["session"]
    sess = f" --session {sid[:8]}" if explicit_session else ""
    who = ", ".join(d["agents"]) or "agent"
    when = ""
    if d["first"] is not None:
        a, b = sessions.when(d["first"]), sessions.when(d["last"])
        when = f", {a} to {b[11:] if a[:10] == b[:10] else b}"
    out = [f"Session {sid[:8]} ({who}{when}): {d['steps']} step{'s' if d['steps'] != 1 else ''}, "
           f"{d['commands']} shell command{'s' if d['commands'] != 1 else ''}."]
    if not d["files"]:
        out.append("No file is different now from before this session" +
                   (" (it read, searched or ran commands that changed nothing)." if d["steps"] else "."))
    else:
        out.append(f"{len(d['files'])} file{'s' if len(d['files']) != 1 else ''} different now from before "
                   f"its first step:")
        rels = [rewind.relative(f["path"], root) for f in d["files"][:SHOW]]
        w = min(max(len(r) for r in rels), 50)
        for f, rel in zip(d["files"][:SHOW], rels):
            out.append(f"  {f['kind']:<8} {rel:<{w}}  {_lines_text(f):<12} {_steps_text(f['steps'])}".rstrip())
        if len(d["files"]) > SHOW:
            out.append(f"  ... and {len(d['files']) - SHOW} more: {run} diff 0{sess}")
    for path_s, why in d["cannot"]:
        out.append(f"  CANNOT   {rewind.relative(path_s, root)}: {why}")
    if d["uncovered"]:
        out.append(f"  note: {d['uncovered']} command step(s) were not scanned (more files than the scan limit, or "
                   f"a scan that did not finish); files they changed are not listed and cannot be put back")
    if d["early"]:
        out.append(f"  note: {d['early']} command(s) ran in the background; files they changed after the "
                   f"after-scan are not listed")
    if d["drift"]:
        out.append(f"  note: {len(d['drift'])} of these also changed outside the agent afterwards (a hand edit?); "
                   f"`rewind 0` refuses to overwrite that until you add --force")
    if d["files"]:
        cmds = [(f"{run} diff 0{sess}", "every change above, as a diff")]
        if d["last_changer"]:
            cmds.append((f"{run} revert {d['last_changer']}{sess}",
                         f"take back only step {d['last_changer']} (the last that changed files), keep the rest"))
        cmds.append((f"{run} rewind 0{sess}", "put every file above back as it was before step 1"))
        w = max(len(c) for c, _ in cmds)
        out.append("Take it back:")
        out += [f"  {c:<{w}}  {why}" for c, why in cmds]
    if d["others"]:
        out.append(f"{d['others']} other session{'s' if d['others'] != 1 else ''} in this log: {run} sessions")
    return out
