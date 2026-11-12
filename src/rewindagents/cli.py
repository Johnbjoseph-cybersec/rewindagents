"""rewindagents command line: record, verify, head, show, hook, install, uninstall, replay, rewind, branch,
export, sessions, bundle, import, gc."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, agents, bundle, export, gc, hook, log, rewind, sessions


def invocation() -> str:
    """How the user runs us: the console command once installed, the module from a clone."""
    return "rewindagents" if hook.installed() else "python3 -m rewindagents"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="rewindagents")
    ap.add_argument("--version", action="version", version=f"rewindagents {__version__}")
    ap.add_argument("--log", default=".rewindagents/log.jsonl", help="log file (default: %(default)s)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("record", help="append one tool call, read as JSON from stdin")
    r.add_argument("--session", required=True)
    v = sub.add_parser("verify", help="check the hash chain")
    v.add_argument("--head", help="pinned head hash; also catches records cut from the end")
    sub.add_parser("head", help="print the current head hash")
    s = sub.add_parser("show", help="print recorded calls")
    s.add_argument("--session")
    hk = sub.add_parser("hook", help="hook entry point (reads the agent's hook JSON on stdin; never blocks)")
    hk.add_argument("--agent", choices=sorted(agents.AGENTS), default=agents.DEFAULT,
                    help="which agent is calling (default: %(default)s)")
    i = sub.add_parser("install", help="add the hook to an agent's config file")
    i.add_argument("--agent", choices=sorted(agents.AGENTS), default=agents.DEFAULT,
                   help="claude: .claude/settings.json, codex: .codex/hooks.json, cursor: .cursor/hooks.json "
                        "(default: %(default)s)")
    i.add_argument("--settings", help="config file to write (default: the agent's file in the current project)")
    un = sub.add_parser("uninstall", help="remove the hook `install` wrote; other hooks and the recorded history stay")
    un.add_argument("--agent", choices=sorted(agents.AGENTS), default=agents.DEFAULT,
                    help="claude: .claude/settings.json, codex: .codex/hooks.json, cursor: .cursor/hooks.json "
                         "(default: %(default)s)")
    un.add_argument("--settings", help="config file to change (default: the agent's file in the current project)")
    rp = sub.add_parser("replay", help="list a session's steps, or show one step in full")
    rp.add_argument("--session", help="default: the session that wrote the last record")
    rp.add_argument("--step", type=int, help="show this step's full input, checkpoints and result")
    rw = sub.add_parser("rewind", help="put the files back the way they were right after step N")
    rw.add_argument("step", type=int, help="step number from `replay` (0 = before the first step)")
    rw.add_argument("--session", help="default: the session that wrote the last record")
    rw.add_argument("--dry-run", action="store_true", help="print what would change, change nothing")
    br = sub.add_parser("branch", help="keep the current files as a branch, then rewind to step N")
    br.add_argument("step", type=int)
    br.add_argument("--name", required=True, help="branch name (git: rewindagents/<name>)")
    br.add_argument("--session", help="default: the session that wrote the last record")
    ex = sub.add_parser("export", help="write a session as one self-contained HTML page (steps, inputs, results, file diffs)")
    ex.add_argument("--session", help="default: the session that wrote the last record")
    ex.add_argument("--out", help="file to write (default: .rewindagents/replay-<session>.html)")
    ex.add_argument("--no-contents", action="store_true",
                    help="leave inputs, results and diffs out: steps, tools and paths only")
    se = sub.add_parser("sessions", help="list every session in the log: id, first and last time, steps, files touched")
    se.add_argument("--grep", metavar="TEXT",
                    help="only sessions with a step whose command, file or input mentions TEXT (any case); "
                         "the matching steps are listed")
    bu = sub.add_parser("bundle", help="write one session and the file copies it names to one file, "
                                       "to replay and rewind it on another machine or clone")
    bu.add_argument("--session", help="default: the session that wrote the last record")
    bu.add_argument("--out", required=True, help="file to write")
    im = sub.add_parser("import", help="check a bundle, then add its session to this project's log; "
                                       "file paths move to this project")
    im.add_argument("file", help="a file written by `bundle`")
    g = sub.add_parser("gc", help="delete stored file copies that no log record and no pending scan names")
    g.add_argument("--dry-run", action="store_true", help="print what would be deleted, delete nothing")
    g.add_argument("--drop-pending-older-than", type=float, metavar="DAYS",
                   help="first remove pending scans older than DAYS (at least 1): a command whose after-scan "
                        "never ran (agent killed, crash); its step then rewinds as unscanned")

    a = ap.parse_args(argv)
    if a.cmd == "hook":
        return hook.run(agent=a.agent)
    if a.cmd == "install":
        target = a.settings or agents.config_path(agents.AGENTS[a.agent])
        changed = hook.install(target, agent=a.agent)
        print(f"{'installed in' if changed else 'already installed in'} {target}")
        return 0
    if a.cmd == "uninstall":
        target = a.settings or agents.config_path(agents.AGENTS[a.agent])
        changed = hook.uninstall(target, agent=a.agent)
        print(f"removed from {target}" if changed else f"not installed in {target}; left unchanged")
        return 0
    if a.cmd in ("verify", "show", "replay", "rewind", "branch", "export", "sessions", "bundle", "gc") \
            and not Path(a.log).exists():
        print(f"rewindagents: no log at {a.log}", file=sys.stderr)
        return 2
    if a.cmd == "gc":
        try:
            d = gc.gc(a.log, dry_run=a.dry_run, drop_older_than=a.drop_pending_older_than)
        except gc.GcError as e:
            print(f"rewindagents: {e}", file=sys.stderr)
            return 1
        for line in gc.lines(d):
            print(line)
        return 0
    if a.cmd in ("bundle", "import"):
        root = rewind.project_root(a.log)
        try:
            if a.cmd == "bundle":
                d = bundle.bundle(a.log, a.out, a.session)
            else:
                d = bundle.import_bundle(a.file, a.log)
        except bundle.BundleError as e:
            print(f"rewindagents: {e}", file=sys.stderr)
            return 1
        if a.cmd == "bundle":
            print(f"wrote {rewind.relative(d['out'], root)}: session {d['session']}, {d['steps']} steps, "
                  f"{d['records']} records, {d['objects']} stored files, {d['bytes']:,} bytes")
        else:
            print(f"imported session {d['session']}: {d['steps']} steps, {d['records']} records, "
                  f"{d['objects']} stored files ({d['already_here']} already here)")
            print(f"  file paths moved from {d['from_root']} to {d['root']}")
            print(f"  replay it with: {invocation()} replay --session {d['session']}")
        return 0
    if a.cmd == "replay":
        return _replay(a.log, a.session, a.step)
    if a.cmd == "sessions":
        found = sessions.sessions(a.log, a.grep)
        for line in sessions.lines(found, root=rewind.project_root(a.log)):
            print(line)
        if a.grep and not found:
            print(f"rewindagents: no session mentions {a.grep!r}", file=sys.stderr)
            return 1
        return 0
    if a.cmd == "export":
        try:
            d = export.export(a.log, a.session, a.out, contents=not a.no_contents)
        except export.ExportError as e:
            print(f"rewindagents: {e}", file=sys.stderr)
            return 1
        print(f"wrote {rewind.relative(d['out'], rewind.project_root(a.log))}: session {d['session']}, "
              f"{len(d['steps'])} steps, {d['bytes']:,} bytes")
        if not d["chain_ok"]:
            print(f"rewindagents: the log does not verify ({d['chain_msg']}); the page says so", file=sys.stderr)
            return 1
        return 0
    if a.cmd in ("rewind", "branch"):
        try:
            if a.cmd == "rewind":
                p = rewind.rewind(a.log, a.step, a.session, dry_run=a.dry_run)
            else:
                p = rewind.branch(a.log, a.step, a.name, a.session)
        except rewind.RewindError as e:
            print(f"rewindagents: {e}", file=sys.stderr)
            return 1
        _report(p, dry_run=getattr(a, "dry_run", False), root=rewind.project_root(a.log))
        # README: "If anything could not be restored, the exit code is 1" - an unscanned step counts.
        return 1 if p["cannot"] or p["bash_uncovered"] else 0
    if a.cmd == "record":
        try:
            call = json.load(sys.stdin)
        except ValueError as e:
            print(f"rewindagents: stdin is not JSON: {e}", file=sys.stderr)
            return 2
        if not isinstance(call, dict) or "tool" not in call:
            print("rewindagents: stdin must be an object with a 'tool' key", file=sys.stderr)
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
        print(f"rewindagents: step {step} is out of range (1-{len(all_steps)})", file=sys.stderr)
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
        where = f"git branch {b['git_ref']} ({b['commit'][:12]})" if b["git_ref"] else "the rewindagents log only (not a git repo)"
        print(f"  previous files kept in {where}")
    if p.get("record"):
        print(f"  this {('branch' if p.get('branch') else 'rewind')} is step {p['steps'] + 1}; "
              f"undo it with: {invocation()} rewind {p['steps']} --session {p['session']}")
    if p["bash_uncovered"]:
        print(f"  note: {p['bash_uncovered']} step(s) after step {p['to_step']} were not scanned before and after "
              f"(a command or edit whose scan did not finish); files they changed were not put back")


if __name__ == "__main__":
    sys.exit(main())
