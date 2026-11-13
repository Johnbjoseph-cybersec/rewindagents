"""rewindagents command line: init, status, record, verify, head, show, hook, install, uninstall, replay, diff,
rewind, revert, branch, fork, compare, export, sessions, bundle, import, gc."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, agents, bundle, export, gc, hook, log, project, rewind, runs, sessions
from . import diff as diffs, init as setup, revert as reverts, summary as summaries


def invocation() -> str:
    """How the user runs us: the console command once installed, the module from a clone."""
    return "rewindagents" if hook.installed() else "python3 -m rewindagents"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="rewindagents",
        description="The flight recorder for coding agents: see exactly what your agent did, and take back any "
                    "part of it. Start with `rewindagents init`; then `summary`, `replay`, `diff N`, `rewind N [--only PATH]`, "
                    "`revert K` (take back step K alone, keep everything after it).",
        epilog="Exit codes: 0 done; 1 it ran but something was not done or does not check out (a file a rewind "
               "could not put back or refused to overwrite, a log that does not verify); 2 it could not run as "
               "asked (an option it cannot parse, a step number the session does not have, or no log yet). A --session, "
               "run, --name or --dir that matches nothing, is taken or is not allowed exits 1 and says why.")
    ap.add_argument("--version", action="version", version=f"rewindagents {__version__}")
    ap.add_argument("--log", help="log file (default: .rewindagents/log.jsonl here, or in the nearest parent "
                                  "directory that has one, as git finds a repository)")
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
    sm = sub.add_parser("summary", help="what the agent just did: each file it created, changed or deleted (lines "
                                        "added and removed, which steps), and the commands that take it back")
    sm.add_argument("--session", help="default: the session that wrote the last record")
    rp = sub.add_parser("replay", help="list a session's steps, or show one step in full (replay N)")
    rp.add_argument("n", nargs="?", type=int, metavar="STEP", help="show this step's full input, checkpoints and "
                                                                    "result (same as --step)")
    rp.add_argument("--session", help="default: the session that wrote the last record")
    rp.add_argument("--step", type=int, help="show this step's full input, checkpoints and result")
    rp.add_argument("--diff", action="store_true",
                    help="with --step N: what step N itself changed, as a unified diff per file (before the step "
                         "-> right after it)")
    rp.add_argument("--no-redact", action="store_true",
                    help="show secrets (API keys, tokens, private keys, .env values) as recorded; by default they "
                         "are replaced, as in export")
    rw = sub.add_parser("rewind", help="put the files back the way they were right after step N")
    rw.add_argument("step", type=int, help="step number from `replay` (0 = before the first step)")
    rw.add_argument("--session", help="default: the session that wrote the last record")
    rw.add_argument("--dry-run", action="store_true", help="print what would change, change nothing")
    rw.add_argument("--only", action="append", metavar="PATH",
                    help="put back only this file (or the files under this directory); repeat for more")
    rw.add_argument("--force", action="store_true",
                    help="rewind even when a file changed after the steps it takes back (by hand or another "
                         "session); those bytes are kept as a step, so the rewind can be undone")
    rv = sub.add_parser("revert", help="take back step K alone and keep every later step and hand edit: a three-way "
                                       "merge per file; on a conflict nothing changes (exit 1)")
    rv.add_argument("step", type=int, help="step number from `replay`")
    rv.add_argument("--session", help="default: the session that wrote the last record")
    rv.add_argument("--dry-run", action="store_true", help="print what would change, change nothing")
    dfp = sub.add_parser("diff", help="show what `rewind N` would change, as a unified diff (now -> step N)")
    dfp.add_argument("step", type=int, help="step number from `replay` (0 = before the first step)")
    dfp.add_argument("paths", nargs="*", metavar="PATH", help="only these files (or the files under these directories)")
    dfp.add_argument("--session", help="default: the session that wrote the last record")
    ini = sub.add_parser("init", help="find the coding agents you use and add the hook to each (asks first)")
    ini.add_argument("--yes", "-y", action="store_true", help="install without asking")
    ini.add_argument("--global", dest="global_", action="store_true",
                     help="write each agent's user config (every project) instead of this project's")
    ini.add_argument("--agent", action="append", choices=sorted(agents.AGENTS), metavar="NAME",
                     help="set up only this agent (repeat for more), even when it is not detected: "
                          + ", ".join(sorted(agents.AGENTS)))
    ini.add_argument("--undo", action="store_true",
                     help="remove every rewindagents hook init added (other hooks and settings stay; files that "
                          "held only our hook are deleted); the recorded history is kept")
    st = sub.add_parser("status", help="say, per agent config file, whether the rewindagents hook is there and "
                                       "can still run, then how many records this project's log holds, when the "
                                       "last was written and whether it verifies (exit 1 when a hook is stale or "
                                       "the log does not verify)")
    st.add_argument("--global", dest="global_", action="store_true", help="check each agent's user config instead")
    br = sub.add_parser("branch", help="keep the current files as a branch, then rewind to step N")
    br.add_argument("step", type=int)
    br.add_argument("--name", required=True, help="branch name (git: rewindagents/<name>)")
    br.add_argument("--session", help="default: the session that wrote the last record")
    br.add_argument("--force", action="store_true",
                    help="branch even when a file changed after the steps it takes back (see rewind --force)")
    fk = sub.add_parser("fork", help="start a separate run from step N: a new directory (a git worktree in a repo) "
                                     "holding the files as they were right after step N, with its own log")
    fk.add_argument("step", type=int, help="step number from `replay` (0 = before the first step)")
    fk.add_argument("--name", required=True, help="the run's name (git branch rewindagents/run/<name>)")
    fk.add_argument("--session", help="default: the session that wrote the last record")
    fk.add_argument("--dir", help="where to make it (default: next to the project, <project>-<name>)")
    cp = sub.add_parser("compare", help="line up runs forked from the same step: steps, agents, files and lines "
                                        "changed, which runs ended the same, and your check command in each")
    cp.add_argument("runs", nargs="*", metavar="RUN",
                    help="run names or directories (default: this project and every run forked from it)")
    cp.add_argument("--check", metavar="CMD", help="run this command (your tests) in each run; its exit code "
                                                   "is the result")
    cp.add_argument("--check-timeout", type=float, default=600.0, metavar="SECONDS",
                    help="stop a check after this long (default: %(default)g)")
    cp.add_argument("--diff", action="store_true", help="with two runs: how they differ, as a unified diff")
    cp.add_argument("--json", action="store_true", help="print the comparison as JSON")
    ex = sub.add_parser("export", help="write a session as one self-contained HTML page (steps, inputs, results, file diffs)")
    ex.add_argument("--session", help="default: the session that wrote the last record")
    ex.add_argument("--out", help="file to write (default: .rewindagents/replay-<session>.html)")
    ex.add_argument("--no-contents", action="store_true",
                    help="leave inputs, results and diffs out: steps, tools and paths only")
    ex.add_argument("--no-redact", action="store_true",
                    help="keep secrets (API keys, tokens, private keys, .env values) as recorded")
    se = sub.add_parser("sessions", help="list every session in the log: id, first and last time, steps, files touched")
    se.add_argument("--grep", metavar="TEXT",
                    help="only sessions with a step whose command, file or input mentions TEXT (any case); "
                         "the matching steps are listed")
    bu = sub.add_parser("bundle", help="write one session and the file copies it names to one file, "
                                       "to replay and rewind it on another machine or clone")
    bu.add_argument("--session", help="default: the session that wrote the last record")
    bu.add_argument("--out", required=True, help="file to write")
    bu.add_argument("--no-redact", action="store_true",
                    help="carry secrets (API keys, tokens, private keys, .env values) as recorded")
    im = sub.add_parser("import", help="check a bundle, then add its session to this project's log; "
                                       "file paths move to this project")
    im.add_argument("file", help="a file written by `bundle`")
    g = sub.add_parser("gc", help="delete stored file copies that no log record and no pending scan names")
    g.add_argument("--dry-run", action="store_true", help="print what would be deleted, delete nothing")
    g.add_argument("--drop-pending-older-than", type=float, metavar="DAYS",
                   help="first remove pending scans older than DAYS (at least 1): a command whose after-scan "
                        "never ran (agent killed, crash); its step then rewinds as unscanned")
    ui_p = sub.add_parser("ui", help="open the timeline in your browser: every step, its diffs, rewind from any step "
                                     "(127.0.0.1 only, one-time link)")
    ui_p.add_argument("--session", help="session to show first (default: the latest)")
    ui_p.add_argument("--port", type=int, default=0, help="port on 127.0.0.1 (default: a free one)")
    ui_p.add_argument("--no-open", action="store_true", help="print the link, do not open a browser")

    a = ap.parse_args(argv)
    explicit_log = a.log is not None
    if not explicit_log:
        a.log = str(project.default_log())
    try:
        return _dispatch(a, explicit_log)
    except sessions.SessionError as e:
        print(f"rewindagents: {e}", file=sys.stderr)
        return 1
    except OSError as e:   # a file we were asked to write or read: say which and why, not a traceback
        what = f"{e.strerror}: {e.filename}" if e.strerror and e.filename else str(e)
        print(f"rewindagents: {what}", file=sys.stderr)
        return 1


def _dispatch(a: argparse.Namespace, explicit_log: bool) -> int:
    if getattr(a, "session", None) and a.cmd not in ("record", "hook") and Path(a.log).exists():
        a.session = sessions.resolve(a.log, a.session)     # exact id, or a unique prefix of one
    if a.cmd == "ui":
        from . import ui
        return ui.run(a.log, a.session, a.port, open_browser=not a.no_open)
    if a.cmd == "hook":
        return hook.run(agent=a.agent)
    if a.cmd == "install":
        target = a.settings or agents.config_path(agents.AGENTS[a.agent])
        kind = hook.ephemeral()
        if kind:
            print(f"rewindagents: not installed: {hook.ephemeral_message(kind)}", file=sys.stderr)
            return 2
        dead = hook.replace_stale(target, agent=a.agent)
        changed = hook.install(target, agent=a.agent)
        print(f"{'installed in' if changed else 'already installed in'} {target}")
        for _, why in dead:
            print(f"  replaced a stale rewindagents hook: {why}")
        return 0
    if a.cmd == "status":
        here = Path(".rewindagents/log.jsonl")
        if not explicit_log and Path(a.log) != here:     # found in a parent directory: that is the project
            root = rewind.project_root(a.log)
            print(f"project: {root}")
            return setup.status(global_=a.global_, root=root)
        return setup.status(global_=a.global_, log_path=a.log)
    if a.cmd == "uninstall":
        target = a.settings or agents.config_path(agents.AGENTS[a.agent])
        changed = hook.uninstall(target, agent=a.agent)
        print(f"removed from {target}" if changed else f"not installed in {target}; left unchanged")
        return 0
    if a.cmd == "init":
        if a.undo:
            return setup.undo(global_=a.global_, only=a.agent)
        return setup.main(yes=a.yes, global_=a.global_, only=a.agent)
    if a.cmd == "compare":
        return _compare(a)
    if a.cmd in ("verify", "show", "replay", "rewind", "revert", "branch", "export", "sessions", "bundle", "gc", "diff", "fork",
                 "summary") \
            and not Path(a.log).exists():
        print(f"rewindagents: no log at {a.log}" + ("" if explicit_log else ", here or in a parent directory"),
              file=sys.stderr)
        if not explicit_log:
            print(f"Nothing has been recorded for this project yet. Add the hook with `{invocation()} init`, run "
                  f"your agent, then try again; `{invocation()} status` checks the hook.", file=sys.stderr)
        return 2
    if a.cmd == "fork":
        try:
            d = runs.fork(a.log, a.step, a.name, a.session, a.dir)
        except rewind.StepRangeError as e:
            print(f"rewindagents: {e}", file=sys.stderr)
            return 2
        except (runs.RunError, rewind.RewindError) as e:
            print(f"rewindagents: {e}", file=sys.stderr)
            return 1
        where = f"git worktree on branch {d['git_branch']}" if d["git_branch"] else "a plain directory (not a git repo)"
        print(f"run {d['name']}: {d['dir']}")
        print(f"  {d['files']} files as they were right after step {d['step']} of session {d['session']}; {where}")
        if d.get("drift"):
            print(f"  WARNING  {len(d['drift'])} file(s) changed after the steps this run starts before, so the run "
                  f"starts without those changes (your project keeps them):")
            for x in d["drift"]:
                print(f"    {x['path']}: {x['why']}")
        if d["hooked"]:
            print(f"  recorded there: {', '.join(d['hooked'])} (their hook is in the run's config or your global one)")
        else:
            print(f"  no agent hook reaches it, so an agent's steps there will not be recorded: run "
                  f"`{invocation()} init` in it (compare still compares the files)")
        print(f"  next: cd {d['dir']} and let any agent (or you) continue; then, back here: {invocation()} compare")
        return 0
    if a.cmd == "gc":
        try:
            d = gc.gc(a.log, dry_run=a.dry_run, drop_older_than=a.drop_pending_older_than)
        except gc.GcError as e:
            print(f"rewindagents: {e}", file=sys.stderr)
            return 1
        for line in gc.lines(d):
            print(line)
        return 1 if d["torn"] else 0
    if a.cmd in ("bundle", "import"):
        root = rewind.project_root(a.log)
        try:
            if a.cmd == "bundle":
                d = bundle.bundle(a.log, a.out, a.session, redact=not a.no_redact)
            else:
                d = bundle.import_bundle(a.file, a.log)
        except bundle.BundleError as e:
            print(f"rewindagents: {e}", file=sys.stderr)
            return 1
        if a.cmd == "bundle":
            print(f"wrote {rewind.relative(d['out'], root)}: session {d['session']}, {d['steps']} steps, "
                  f"{d['records']} records, {d['objects']} stored files, {d['bytes']:,} bytes")
            print(_redaction_line(d["redacted"]))
        else:
            print(f"imported session {d['session']}: {d['steps']} steps, {d['records']} records, "
                  f"{d['objects']} stored files ({d['already_here']} already here)")
            print(f"  file paths moved from {d['from_root']} to {d['root']}")
            print(f"  replay it with: {invocation()} replay --session {d['session']}")
            if d["torn"]:
                print(f"  note: this log has a torn write ({d['torn']}); the torn line stays where it is and the "
                      f"imported records chain on from the last whole record")
                return 1
        return 0
    if a.cmd == "diff":
        return diffs.run(a.log, a.step, a.session, a.paths)
    if a.cmd == "summary":
        try:
            d = summaries.summarize(a.log, a.session)
        except rewind.RewindError as e:
            print(f"rewindagents: {e}", file=sys.stderr)
            return 1
        for line in summaries.lines(d, invocation(), explicit_session=bool(a.session)):
            print(line)
        return 0
    if a.cmd == "replay":
        if a.n is not None:
            if a.step is not None and a.step != a.n:
                print(f"rewindagents: replay {a.n} and --step {a.step} name different steps; give one",
                      file=sys.stderr)
                return 2
            a.step = a.n
        if a.diff and a.step is None:
            print("rewindagents: --diff needs a step: replay N --diff, or --step N --diff (diff N compares now with "
                  "step N)",
                  file=sys.stderr)
            return 2
        return _replay(a.log, a.session, a.step, a.diff, redact=not a.no_redact)
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
            d = export.export(a.log, a.session, a.out, contents=not a.no_contents, redact=not a.no_redact)
        except export.ExportError as e:
            print(f"rewindagents: {e}", file=sys.stderr)
            return 1
        print(f"wrote {rewind.relative(d['out'], rewind.project_root(a.log))}: session {d['session']}, "
              f"{len(d['steps'])} steps, {d['bytes']:,} bytes")
        print(_redaction_line(d["redacted"] if d["redact"] else None))
        if not d["chain_ok"]:
            print(f"rewindagents: the log does not verify ({d['chain_msg']}); the page says so", file=sys.stderr)
            return 1
        return 0
    if a.cmd == "revert":
        return _revert(a)
    if a.cmd in ("rewind", "branch"):
        try:
            if a.cmd == "rewind":
                p = rewind.rewind(a.log, a.step, a.session, dry_run=a.dry_run, only=a.only, force=a.force)
            else:
                p = rewind.branch(a.log, a.step, a.name, a.session, force=a.force)
        except rewind.DriftError as e:
            _refused(e.plan, a)
            return 1
        except rewind.StepRangeError as e:
            print(f"rewindagents: {e}", file=sys.stderr)
            return 2
        except rewind.RewindError as e:
            print(f"rewindagents: {e}", file=sys.stderr)
            return 1
        _report(p, dry_run=getattr(a, "dry_run", False), root=rewind.project_root(a.log))
        # README: "If anything could not be restored, the exit code is 1" - an unscanned step counts, and so
        # does a background command whose after-scan may have been early (nobody can say it was all restored).
        if p.get("drift") and getattr(a, "dry_run", False) and not a.force:
            return 1        # the real rewind would refuse
        return 1 if p["cannot"] or p["bash_uncovered"] or p["scan_early"] or p.get("torn") else 0
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


def _revert(a: argparse.Namespace) -> int:
    root = rewind.project_root(a.log)
    try:
        p = reverts.revert(a.log, a.step, a.session, dry_run=a.dry_run)
    except reverts.ConflictError as e:
        _revert_conflict(e.plan, root)
        return 1
    except rewind.StepRangeError as e:
        print(f"rewindagents: {e}", file=sys.stderr)
        return 2
    except rewind.RewindError as e:
        print(f"rewindagents: {e}", file=sys.stderr)
        return 1
    k, sid = p["step"], p["session"]
    if p["conflict"]:              # --dry-run: the same message a real revert gives, on stdout
        _revert_conflict(p, root, sys.stdout, dry_run=True)
        return 1
    verb = "would" if a.dry_run else "did"
    n = len(p["write"]) + len(p["delete"])
    print(f"session {sid}: revert step {k} of {p['steps']}, keeping the steps after it ({verb} change "
          f"{n} file{'s' if n != 1 else ''})")
    for q, _, _ in p["write"]:
        if q in p["merged"]:
            print(f"  merge    {rewind.relative(q, root)}: step {k}'s change taken out, later changes kept")
        else:
            print(f"  restore  {rewind.relative(q, root)}")
    for q in p["delete"]:
        print(f"  delete   {rewind.relative(q, root)}")
    for q in p["same"]:
        print(f"  same     {rewind.relative(q, root)}: already without step {k}'s change")
    for q, why in p["cannot"]:
        print(f"  CANNOT   {rewind.relative(q, root)}: {why}")
    if p.get("record"):
        print(f"  this revert is step {p['steps'] + 1}; undo it with: {invocation()} rewind {p['steps']} "
              f"--session {sid}")
    if p.get("early"):
        print(f"  note: step {k} ran a command in the background, so its after-scan may have run before it "
              f"finished; files it changed later were not seen")
    if p.get("torn"):
        print(f"  note: the log has a torn write ({p['torn']}); the call it was recording is not in the log")
    return 1 if p["cannot"] or p.get("early") or p.get("torn") else 0


def _revert_conflict(p: dict, root, out=None, dry_run: bool = False) -> None:
    out = out or sys.stderr
    k, sid = p["step"], p["session"]
    n = len(p["conflict"])
    head = "would conflict" if dry_run else "refused, nothing changed"
    print(f"rewindagents: revert {k} {head}: {n} file{'s' if n != 1 else ''} changed after step {k} where "
          f"step {k} changed {'them' if n != 1 else 'it'}:", file=out)
    for q, why in p["conflict"]:
        print(f"  CONFLICT {rewind.relative(q, root)}: {why}", file=out)
    print(f"  what step {k} changed: {invocation()} replay --step {k} --diff --session {sid}", file=out)
    only = " ".join(f"--only {rewind.relative(q, root)}" for q, _ in p["conflict"])
    print(f"  then either edit those lines back by hand, or put {'those files' if n != 1 else 'the file'} back as "
          f"{'they were' if n != 1 else 'it was'} before step {k}, losing the later changes in "
          f"{'them' if n != 1 else 'it'} (kept as a step, so it can be undone): "
          f"{invocation()} rewind {k - 1} {only} --force --session {sid}", file=out)


def _compare(a: argparse.Namespace) -> int:
    try:
        if a.diff:
            if len(a.runs) != 2:
                print("rewindagents: --diff needs exactly two runs: compare --diff RUN_A RUN_B", file=sys.stderr)
                return 2
            for text in runs.diff_runs(Path.cwd(), a.runs[0], a.runs[1]):
                sys.stdout.write(text)
            return 0
        c = runs.compare(Path.cwd(), a.runs or None, a.check, a.check_timeout)
    except (runs.RunError, rewind.RewindError) as e:
        print(f"rewindagents: {e}", file=sys.stderr)
        return 1
    if a.json:
        print(json.dumps(c, indent=1, sort_keys=True))
    else:
        for line in runs.lines(c):
            print(line)
    return 0


def _redaction_line(n: int | None) -> str:
    if n is None:
        return "  secrets kept as recorded (--no-redact)"
    return f"  {n} secret value{'s' if n != 1 else ''} replaced with [redacted ...]; --no-redact keeps them"


def _replay(log_path: str, session: str | None, step: int | None, show_diff: bool = False,
            redact: bool = True) -> int:
    """With redact (the default, as for export and bundle), secrets in summaries, inputs, results and diffs are
    replaced before they reach the terminal: terminal output gets pasted into issues and chats."""
    from . import redact as _redact
    all_steps = rewind.steps(log_path, session)
    root = rewind.project_root(log_path)
    if step is None:
        found = 0
        for s in all_steps:
            mark = f"  [{len(s['checkpoints'])} checkpointed]" if s["checkpoints"] else ""
            if (s.get("bash_scan") or {}).get("early"):
                mark += "  [background: scan may be early]"
            skipped = (s.get("bash_scan") or {}).get("skipped")
            if skipped and not s["checkpoints"]:
                mark += f"  [NOT checkpointed: {skipped}]"
            line = rewind.summary(s, width=sys.maxsize, root=root)
            if redact:
                line, k = _redact.text(line)
                found += k
            line = line if len(line) <= 80 else line[:77] + "..."   # redacted before the cut: no half token
            print(f"{s['step']:>5}  {s['tool']:<12}  {line}{mark}")
        diffs.redaction_note(found, sys.stderr)
        return 0
    if not 1 <= step <= len(all_steps):
        print(f"rewindagents: {rewind.range_message(step, session or rewind.latest_session(log_path), len(all_steps), 1)}",
              file=sys.stderr)
        return 2
    if show_diff:
        return diffs.step_run(log_path, all_steps, step, root, redact=redact)
    value = all_steps[step - 1]
    if not redact:
        print(export.show(value))
        return 0
    found = export.clips(value)                  # clip lengths as recorded, before redaction changes a head
    value, k = _redact.value(value)
    print(export.show(value, found))
    diffs.redaction_note(k, sys.stderr)
    return 0


def drift_lines(p: dict, root, indent: str = "  ") -> list[str]:
    """The files a rewind to p["to_step"] would overwrite although they changed after the steps it takes back."""
    out = []
    for d in p.get("drift") or []:
        out.append(f"{indent}{rewind.relative(d['path'], root)}: {rewind.drift_why(d)}")
    return out


def _refused(p: dict, a: argparse.Namespace) -> None:
    root = rewind.project_root(a.log)
    cmd = "rewind" if a.cmd == "rewind" else "branch"
    n = len(p["drift"])
    print(f"rewindagents: {cmd} refused, nothing changed: {n} file{'s' if n != 1 else ''} changed after the steps "
          f"it takes back, and it would overwrite {'those changes' if n != 1 else 'that change'}:", file=sys.stderr)
    for line in drift_lines(p, root):
        print(line, file=sys.stderr)
    print(f"  see exactly what would be lost: {invocation()} diff {p['to_step']} --session {p['session']}", file=sys.stderr)
    print(f"  {cmd} anyway with --force: the current bytes are kept as a step, so it can be undone with "
          f"`{invocation()} rewind {p['steps']} --session {p['session']}`", file=sys.stderr)


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
    for q in p.get("unmatched") or []:
        print(f"  skip     {q}: no step after step {p['to_step']} changed it")
    if p.get("drift"):
        n = len(p["drift"])
        if dry_run:
            print(f"  WARNING  {n} file{'s' if n != 1 else ''} changed after the steps this rewind takes back; "
                  f"rewinding would overwrite {'those changes' if n != 1 else 'that change'}:")
        else:
            print(f"  overwrote {n} file{'s' if n != 1 else ''} that changed after the steps it took back "
                  f"(--force); their bytes before this rewind are kept in it:")
        for line in drift_lines(p, root, "    "):
            print(line)
        if dry_run:
            print("  a real rewind refuses this unless you add --force (it then keeps the current bytes as a step, "
                  "so it can be undone)")
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
    if p["scan_early"]:
        print(f"  note: {p['scan_early']} step(s) after step {p['to_step']} ran a command in the background, so "
              f"their after-scan may have run before it finished; files it changed later may not have been put back")
    if p.get("torn"):
        print(f"  note: the log has a torn write ({p['torn']}); the call it was recording is not in the log, "
              f"so files it changed may not have been put back")


if __name__ == "__main__":
    sys.exit(main())
