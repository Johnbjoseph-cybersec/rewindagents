"""rewindagent command line: record, verify, head, show, hook, install, replay, rewind, branch."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import hook, log, rewind


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="rewindagent")
    ap.add_argument("--log", default=".rewindagent/log.jsonl", help="log file (default: %(default)s)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("record", help="append one tool call, read as JSON from stdin")
    r.add_argument("--session", required=True)
    v = sub.add_parser("verify", help="check the hash chain")
    v.add_argument("--head", help="pinned head hash; also catches records cut from the end")
    sub.add_parser("head", help="print the current head hash")
    s = sub.add_parser("show", help="print recorded calls")
    s.add_argument("--session")
    sub.add_parser("hook", help="Claude Code hook entry point (reads the hook JSON on stdin; never blocks)")
    i = sub.add_parser("install", help="add the hook to a Claude Code settings file")
    i.add_argument("--settings", default=".claude/settings.json", help="settings file (default: %(default)s)")
    rp = sub.add_parser("replay", help="list a session's steps, or show one step in full")
    rp.add_argument("--session", help="default: the session that wrote the last record")
    rp.add_argument("--step", type=int, help="show this step's full input, checkpoints and result")
    rw = sub.add_parser("rewind", help="put the files back the way they were right after step N")
    rw.add_argument("step", type=int, help="step number from `replay` (0 = before the first step)")
    rw.add_argument("--session", help="default: the session that wrote the last record")
    rw.add_argument("--dry-run", action="store_true", help="print what would change, change nothing")
    br = sub.add_parser("branch", help="keep the current files as a branch, then rewind to step N")
    br.add_argument("step", type=int)
    br.add_argument("--name", required=True, help="branch name (git: rewindagent/<name>)")
    br.add_argument("--session", help="default: the session that wrote the last record")

    a = ap.parse_args(argv)
    if a.cmd == "hook":
        return hook.run()
    if a.cmd == "install":
        changed = hook.install(a.settings)
        print(f"{'installed in' if changed else 'already installed in'} {a.settings}")
        return 0
    if a.cmd in ("verify", "show", "replay", "rewind", "branch") and not Path(a.log).exists():
        print(f"rewindagent: no log at {a.log}", file=sys.stderr)
        return 2
    if a.cmd == "replay":
        return _replay(a.log, a.session, a.step)
    if a.cmd in ("rewind", "branch"):
        try:
            if a.cmd == "rewind":
                p = rewind.rewind(a.log, a.step, a.session, dry_run=a.dry_run)
            else:
                p = rewind.branch(a.log, a.step, a.name, a.session)
        except rewind.RewindError as e:
            print(f"rewindagent: {e}", file=sys.stderr)
            return 1
        _report(p, dry_run=getattr(a, "dry_run", False), root=rewind.project_root(a.log))
        return 1 if p["cannot"] else 0
    if a.cmd == "record":
        try:
            call = json.load(sys.stdin)
        except ValueError as e:
            print(f"rewindagent: stdin is not JSON: {e}", file=sys.stderr)
            return 2
        if not isinstance(call, dict) or "tool" not in call:
            print("rewindagent: stdin must be an object with a 'tool' key", file=sys.stderr)
            return 2
        rec = log.Recorder(a.log).record(a.session, call["tool"], call.get("args"), call.get("result"),
                                         actor=call.get("actor", "agent"))
        print(rec["hash"])
        return 0
    if a.cmd == "verify":
        ok, n, msg = log.verify(a.log, a.head)
        print(f"{'OK' if ok else 'TAMPERED'}: {n} records, {msg}")
        return 0 if ok else 1
    if a.cmd == "head":
        print(log.head(a.log))
        return 0
    for rec in log.read(a.log, a.session):
        print(f"{rec['seq']:>5}  {rec['session']}  {rec.get('event', '')}  {rec['tool']}  "
              f"{json.dumps(rec['args'], ensure_ascii=False)}")
    return 0


def _replay(log_path: str, session: str | None, step: int | None) -> int:
    all_steps = rewind.steps(log_path, session)
    root = rewind.project_root(log_path)
    if step is None:
        for s in all_steps:
            mark = f"  [{len(s['checkpoints'])} checkpointed]" if s["checkpoints"] else ""
            print(f"{s['step']:>5}  {s['tool']:<12}  {rewind.summary(s, root=root)}{mark}")
        return 0
    if not 1 <= step <= len(all_steps):
        print(f"rewindagent: step {step} is out of range (1-{len(all_steps)})", file=sys.stderr)
        return 2
    print(json.dumps(all_steps[step - 1], indent=2, ensure_ascii=False, default=str))
    return 0


def _report(p: dict, dry_run: bool, root) -> None:
    verb = "would" if dry_run else "did"
    print(f"session {p['session']}: rewind to step {p['to_step']} of {p['steps']} ({verb} change "
          f"{len(p['restore']) + len(p['delete'])} files)")
    for path, _ in p["restore"]:
        print(f"  restore  {rewind.relative(path, root)}")
    for path in p["delete"]:
        print(f"  delete   {rewind.relative(path, root)}")
    for path, why in p["cannot"]:
        print(f"  CANNOT   {rewind.relative(path, root)}: {why}")
    if p.get("branch"):
        b = p["branch"]
        where = f"git branch {b['git_ref']} ({b['commit'][:12]})" if b["git_ref"] else "the rewindagent log only (not a git repo)"
        print(f"  previous files kept in {where}")
    if p.get("record"):
        print(f"  this {('branch' if p.get('branch') else 'rewind')} is step {p['steps'] + 1}; "
              f"undo it with: python3 -m rewindagent rewind {p['steps']} --session {p['session']}")
    if p["bash_after"]:
        print(f"  note: {p['bash_after']} Bash step(s) after step {p['to_step']}; "
              f"files they changed are not checkpointed and were not put back")


if __name__ == "__main__":
    sys.exit(main())
