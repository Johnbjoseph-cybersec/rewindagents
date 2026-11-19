"""`rewindagents init [--yes] [--global]`: find the supported coding agents and add the hook to each.

An agent counts as present when its config directory exists (in the project, or in the home directory) or
its command is on PATH. Command names, read from each vendor's docs on 2026-11-12: Claude Code `claude`
(code.claude.com/docs/en/quickstart), Codex `codex` (learn.chatgpt.com/docs/codex/cli), Gemini CLI `gemini`
(geminicli.com/docs/get-started), Copilot CLI `copilot` (docs.github.com .../use-copilot-cli), Droid `droid`
(docs.factory.com/cli/getting-started/quickstart), Qwen Code `qwen` (github.com/QwenLM/qwen-code). Cursor's
CLI is now `agent` (cursor.com/docs/cli/overview); that name is too generic to mean Cursor, so only
`cursor-agent` (its earlier name) and `cursor` (the editor's command; Cursor's hooks.json serves its agent)
are looked for.

The hook is written by hook.install(), the code path `rewindagents install` uses, so it is never added twice
and every other hook in the file stays. An agent whose file already holds a different rewindagents hook
command (another interpreter, or a clone) is reported and left alone rather than given a second hook, unless
that command can no longer run (hook.stale: its interpreter or PYTHONPATH is gone); then it is replaced.
`rewindagents status` reports the same per file and writes nothing.

Where `--global` writes (the user-level file of each agent, from the docs cited in agents.py): Claude Code
~/.claude/settings.json; Codex ~/.codex/hooks.json; Cursor ~/.cursor/hooks.json; Gemini CLI
~/.gemini/settings.json; Copilot CLI ~/.copilot/hooks/rewindagents.json; Droid ~/.factory/hooks.json when it
exists, else ~/.factory/settings.json (docs.factory.com/reference/hooks-reference); Qwen Code
~/.qwen/settings.json (the Qwen docs say "user configuration files" without naming the path; this is the user
twin of .qwen/settings.json). A global hook still records into the .rewindagents/ of the project the agent
runs in.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from . import agents, hook, log as hlog

BINARIES: dict[str, tuple[str, ...]] = {
    "claude": ("claude",), "codex": ("codex",), "cursor": ("cursor-agent", "cursor"), "gemini": ("gemini",),
    "copilot": ("copilot",), "droid": ("droid",), "qwen": ("qwen",),
}
PROJECT_DIRS = {"claude": ".claude", "codex": ".codex", "cursor": ".cursor", "gemini": ".gemini",
                "copilot": ".github/hooks", "droid": ".factory", "qwen": ".qwen"}
USER_DIRS = {"claude": ".claude", "codex": ".codex", "cursor": ".cursor", "gemini": ".gemini",
             "copilot": ".copilot", "droid": ".factory", "qwen": ".qwen"}
NOTES = {"codex": "Codex asks you to trust a new hook once: run /hooks in Codex"}


EXCLUDE_START = "# rewindagents init: hook files naming this machine's Python (`rewindagents init --undo` removes this block)"
EXCLUDE_END = "# end rewindagents"


def _git(root: Path, *args: str) -> str | None:
    try:
        p = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout.strip() if p.returncode == 0 else None


def _exclude_file(root: Path) -> tuple[Path, Path] | None:
    """(the repository's top directory, its .git/info/exclude) when root is in a git work tree, else None."""
    top = _git(root, "rev-parse", "--show-toplevel")
    ex = _git(root, "rev-parse", "--git-path", "info/exclude")
    if not top or not ex:
        return None
    ex_p = Path(ex) if Path(ex).is_absolute() else root / ex
    return Path(top).resolve(), ex_p


def _block(text: str) -> tuple[list[str], list[str]]:
    """(lines outside our block, the patterns inside it)."""
    outside, inside, inblock = [], [], False
    for line in text.splitlines():
        if line == EXCLUDE_START:
            inblock = True
        elif line == EXCLUDE_END and inblock:
            inblock = False
        elif inblock:
            if line.strip():
                inside.append(line)
        else:
            outside.append(line)
    return outside, inside


def set_excluded(root: Path, add: list[Path] = (), remove: list[Path] = ()) -> list[str]:
    """Keep the config files init created out of git: add (or remove) them in our block of .git/info/exclude,
    which is this clone's own ignore list (never committed, unlike .gitignore). Returns the patterns now in the
    block. Files git already ignores, or that git tracks, are not added. Not a git work tree: does nothing."""
    found = _exclude_file(root)
    if not found:
        return []
    top, ex = found
    try:
        text = ex.read_text(encoding="utf-8") if ex.is_file() else ""
    except (OSError, UnicodeDecodeError):
        return []
    outside, inside = _block(text)

    def pat(f: Path) -> str | None:
        try:
            return "/" + Path(f).resolve().relative_to(top).as_posix()
        except ValueError:
            return None
    for f in add:
        q = pat(f)
        if not q or q in inside:
            continue
        rel = q[1:]
        if _git(top, "ls-files", "--error-unmatch", rel) is not None:
            continue                                 # tracked: excluding it would do nothing
        if _git(top, "check-ignore", "-q", rel) is not None:
            continue                                 # already ignored
        inside.append(q)
    gone = {pat(f) for f in remove}
    inside = [q for q in inside if q not in gone]
    while outside and not outside[-1].strip():
        outside.pop()
    lines = outside + ([""] if outside and inside else []) + ([EXCLUDE_START, *inside, EXCLUDE_END] if inside else [])
    new = "\n".join(lines) + ("\n" if lines else "")
    if new != text:
        ex.parent.mkdir(parents=True, exist_ok=True)
        ex.write_text(new, encoding="utf-8")
    return inside


def _tracked(path: Path) -> bool:
    return _git(path.parent, "ls-files", "--error-unmatch", path.name) is not None


_WINDOWS = os.name == "nt"


def _windows_console(fd: int) -> bool:
    """True when fd is a Windows console handle (GetConsoleMode succeeds on consoles only). The fd's handle
    comes from the C runtime CPython itself uses (ucrtbase _get_osfhandle): msvcrt stays filelock.py's."""
    import ctypes
    crt = ctypes.CDLL("ucrtbase")
    crt._get_osfhandle.restype = ctypes.c_void_p
    crt._get_osfhandle.argtypes = [ctypes.c_int]
    handle = crt._get_osfhandle(fd)
    mode = ctypes.c_uint32()
    return bool(ctypes.windll.kernel32.GetConsoleMode(ctypes.c_void_p(handle), ctypes.byref(mode)))


def is_terminal(stream) -> bool:
    """True when stream is a terminal to ask on. On Windows isatty() is also True for NUL (a character
    device: `< NUL`, subprocess.DEVNULL), which can never answer; there only a console handle counts.
    A stream without a file descriptor is judged by its own isatty()."""
    if not (hasattr(stream, "isatty") and stream.isatty()):
        return False
    if not _WINDOWS:
        return True
    try:
        fd = stream.fileno()
    except (AttributeError, OSError, ValueError):
        return True
    try:
        return _windows_console(fd)
    except (OSError, AttributeError, ImportError):
        return True


def target(name: str, root: Path, home: Path | None, global_: bool) -> Path | None:
    """The config file init writes for this agent, or None when global_ is requested but no home directory
    is known (Path.home() could not tell: no HOME/USERPROFILE, seen on windows-latest CI) -- there is
    nowhere to write a global file, same as "not found" rather than a path to dereference."""
    ag = agents.AGENTS[name]
    if not global_:
        return root / agents.config_path(ag, root)
    if home is None:
        return None
    if name == "copilot":
        return home / ".copilot" / "hooks" / "rewindagents.json"
    return home / agents.config_path(ag, home)


def detect(root: Path, home: Path | None, global_: bool = False, path: str | None = None) -> list[dict]:
    """One entry per supported agent: {"agent", "found": [why], "target"}. `found` is empty when absent.

    `home` is None when Path.home() could not tell (no HOME/USERPROFILE: seen on windows-latest CI); the
    home-directory half of detection is then simply skipped, same as project.py's find_store_root. A
    --global request with no home to search finds nothing at all (there is nowhere to write a user-level
    file): no agent is listed, the same per-agent skip status() and undo() already apply."""
    out = []
    for name in agents.AGENTS:
        if global_ and home is None:
            continue   # cannot find, or write, a user config file without a home directory to look in
        found = []
        if not global_ and (root / PROJECT_DIRS[name]).is_dir():
            found.append(f"{PROJECT_DIRS[name]}/")
        if home is not None and (home / USER_DIRS[name]).is_dir():
            found.append(f"~/{USER_DIRS[name]}/")
        found += [f"{b} on PATH" for b in BINARIES[name] if shutil.which(b, path=path)]
        out.append({"agent": name, "found": found, "target": target(name, root, home, global_)})
    return out


def state(name: str, path: Path, command: str) -> tuple[str, str]:
    """("install" | "stale" | "already" | "other" | "error", detail) for this agent's config file.

    "stale": the file holds a rewindagents hook that can no longer run (hook.stale: its interpreter or
    PYTHONPATH is gone), so the agent records nothing; applying replaces it with `command`.
    """
    try:
        if not path.exists() or not path.read_text(encoding="utf-8").strip():
            return "install", ""     # agents.install reads a blank file as {}
    except (OSError, UnicodeDecodeError) as e:
        return "error", f"cannot read it: {e}"
    try:
        have = agents.commands_in(agents.AGENTS[name], path)
    except (ValueError, OSError, AttributeError, TypeError, KeyError) as e:
        return "error", f"cannot read it: {e}"
    events = list(have.values())
    dead = hook.stale_hooks(path, name)
    if dead:
        return "stale", f"stale: {dead[0][1]}; replaced by this Python's hook"
    if events and all(command in cmds for cmds in events):
        return "already", ""
    others = sorted({c for cmds in events for c in cmds if hook.ours(c) and c != command})
    if others:
        return "other", f"holds another rewindagents hook ({others[0]}); left as is"
    return "install", ""


def recording(path: Path) -> tuple[str, str]:
    """(state, detail) of the project's log: 'none' (no file, or no record), 'ok' or 'BROKEN' (does not verify).
    Reads only."""
    if not path.is_file():
        return "none", "nothing recorded yet"
    try:
        ok, n, msg = hlog.verify(path)
    except (OSError, UnicodeDecodeError) as e:
        return "BROKEN", f"cannot be read: {e}"
    if not ok:
        return "BROKEN", msg
    if not n:
        return "none", "nothing recorded yet"
    with path.open(encoding="utf-8") as fh:
        last = None
        for line in fh:
            if line.strip():
                last = line
    ts = json.loads(last).get("ts")
    when = f", last {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))}" if isinstance(ts, (int, float)) else ""
    return "ok", f"{n:,} record{'s' if n != 1 else ''}{when}, chain intact"


def probe_hooks(name: str, path: Path, timeout: float = 30.0) -> str | None:
    """Run the hook command this install writes for `name` the way the agent would (through the shell, a tool
    call's JSON on stdin) in a scratch directory, and check that it wrote a record there. Returns why it did not
    (the hook's own stderr, last line), or None when it recorded. Nothing is written in the project: the scratch
    directory is a new temporary one, removed afterwards. Not run on Windows, where the agents' shells differ
    (agents.py).

    Only hook.hook_command(name) is ever run, and only when the config file holds exactly that command. A
    command is never taken from the file itself: a cloned project's config is untrusted, and a command that
    merely mentions `rewindagents hook` could run anything (`touch x; python -m rewindagents hook`)."""
    if os.name != "posix":
        return None
    mine = hook.hook_command(name)
    try:
        have = agents.commands_in(agents.AGENTS[name], path)
    except (ValueError, OSError, AttributeError, TypeError, KeyError):
        return None
    if not any(c == mine for cmds in have.values() for c in cmds):
        return None
    for cmd in (mine,):
        with tempfile.TemporaryDirectory(prefix="rewindagents-probe-") as d:
            payload = {"session_id": "rewindagents-status-probe", "cwd": d, "hook_event_name": "PreToolUse",
                       "tool_name": "Read", "tool_input": {"file_path": os.path.join(d, "probe.txt")}}
            env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
            try:
                r = subprocess.run(cmd, shell=True, input=json.dumps(payload), capture_output=True, text=True,
                                   cwd=d, env=env, timeout=timeout)
            except (OSError, subprocess.TimeoutExpired) as e:
                return f"the hook did not finish: {e}"
            logp = Path(d) / ".rewindagents" / "log.jsonl"
            if not (logp.is_file() and logp.read_text(encoding="utf-8").strip()):
                err = [l for l in (r.stderr or "").splitlines() if l.strip()]
                return ("ran but recorded nothing: " + err[-1].strip()[:200]) if err else \
                    f"ran but recorded nothing (exit {r.returncode}, no error message)"
    return None


def store_size(store: Path) -> int:
    total = 0
    for dirpath, _, files in os.walk(store):
        for f in files:
            try:
                total += os.lstat(os.path.join(dirpath, f)).st_size
            except OSError:
                pass
    return total


def human(n: int) -> str:
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:,} bytes" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1024
    return str(n)


def status(global_: bool = False, root: Path | None = None, home: Path | None = None, out=None,
           log_path: str | Path | None = None, probe: bool = True) -> int:
    """`rewindagents status`: one line per agent config file that exists: hook ok, stale, another one, or none;
    then one line for this project's log: records, time of the last one, and whether the chain verifies.
    Writes nothing. Exit 1 when any file holds a stale hook (or cannot be read) or the log does not verify."""
    root = Path(root or Path.cwd()).resolve()
    if home is None:
        try:
            home = Path.home()
        except RuntimeError:  # no HOME/USERPROFILE in this environment (seen on windows-latest CI); see
            home = None       # project.py's find_store_root -- a non-global status still works without it
    else:
        home = Path(home)
    out = out or sys.stdout
    run = hook.invocation()
    bad, shown, hooked, failing, partial, unprobed = 0, 0, 0, 0, 0, 0
    for name in agents.AGENTS:
        if global_ and home is None:
            continue   # cannot find a user config file without a home directory to look in
        t = target(name, root, home, global_)
        if not t.is_file():
            continue
        shown += 1
        where = t.relative_to(home if global_ else root).as_posix()
        where = ("~/" if global_ else "") + where
        st, detail = state(name, t, hook.hook_command(name))
        if st == "stale":
            bad += 1
            line, why = "STALE", detail.split("; ")[0].removeprefix("stale: ")
        elif st == "error":
            bad += 1
            line, why = "error", detail
        elif st == "already":
            line, why = "ok", ""
            hooked += 1
        elif st == "other":
            # Not run by the probe: only the command this install writes is ever executed (probe_hooks).
            line, why = "ok", "another rewindagents hook, not tested by status"
            hooked += 1
            unprobed += 1
        elif any(hook.ours(c) for cmds in agents.commands_in(agents.AGENTS[name], t).values() for c in cmds):
            # e.g. a config from before PostToolUseFailure was hooked: failed shell commands go unrecorded.
            line, why = "PARTIAL", "not on every event: some steps are not recorded"
            bad += 1
            partial += 1
        else:
            line, why = "no hook", ""
        if line == "ok" and probe:
            failed = probe_hooks(name, t)
            if failed:
                bad += 1
                failing += 1
                line, why = "FAILING", failed
        print((f"  {name:<8} {line:<8} {where}" + (f"  ({why})" if why else "")).rstrip(), file=out)
    if not shown:
        print(f"No agent config file {'in your home directory' if global_ else 'in this project'}. "
              f"To add the hook: {run} init", file=out)
    if partial:
        print(f"A PARTIAL hook misses some steps (such as a shell command that fails), so they cannot be undone. "
              f"Fix: {run} init --yes" + (" --global" if global_ else ""), file=out)
    if bad > failing + partial:
        print(f"A stale hook records nothing. Fix: {run} init --yes" + (" --global" if global_ else ""), file=out)
    if failing:
        print(f"A FAILING hook records nothing, and your agent does not show its error. Reinstall rewindagents "
              f"(pipx install --force ...), then: {run} init --yes" + (" --global" if global_ else ""), file=out)
    if not bad and hooked > unprobed and probe and os.name == "posix":
        print("Recording works: each hook above ran once in a scratch folder and wrote a record"
              + (", except those marked not tested." if unprobed else "."), file=out)
    # The log is always this project's: a global hook records into the project the agent runs in too.
    default = ".rewindagents/log.jsonl"
    lp = Path(log_path or default)
    lp = lp if lp.is_absolute() else root / lp
    if str(log_path or default) != default:
        run = f"{run} --log {log_path}"
    try:
        where = lp.relative_to(root).as_posix()
    except ValueError:
        where = str(lp)
    rec, detail = recording(lp)
    print(f"  {'log':<8} {rec:<8} {where}  ({detail})", file=out)
    if rec == "BROKEN":
        print(f"The log does not verify: a record was edited, removed or damaged. Details: {run} verify", file=out)
    elif rec == "none" and hooked:
        print("A hook is in place but nothing is recorded yet: run your agent once, then "
              f"`{run} summary`.", file=out)
    store = lp.parent
    if store.is_dir():
        size = store_size(store)
        print(f"  {'store':<8} {human(size):<8} {where.rsplit('/', 1)[0] + '/' if '/' in where else where}  "
              f"(the log plus a copy of each project file a step may need; `{run} gc` frees what no step needs)",
              file=out)
    if not global_ and (hooked or rec != "none"):
        from . import bashscan
        if bashscan.project_files(root, ignored_files=True) is None:
            print(f"WARNING: this project has more than {bashscan.MAX_SCAN_FILES:,} files, so shell commands "
                  f"(rm, sed -i, scripts) are NOT checkpointed here; edits made with the agent's file tools are. "
                  f"Add big generated directories to .gitignore to get under the limit.", file=out)
    return 1 if bad or rec == "BROKEN" else 0


def main(yes: bool = False, global_: bool = False, root: Path | None = None, home: Path | None = None,
         path: str | None = None, stdin=None, out=None, only: list[str] | None = None) -> int:
    """`only`: the agents named with --agent; they are set up even when not detected, and no other is."""
    root = Path(root or Path.cwd()).resolve()
    if home is None:
        try:
            home = Path.home()
        except RuntimeError:  # no HOME/USERPROFILE in this environment (seen on windows-latest CI); see
            home = None       # project.py's find_store_root -- a project-local init still works without it
    else:
        home = Path(home)
    stdin, out = stdin or sys.stdin, out or sys.stdout

    def show(p: Path) -> str:
        bases = [(root, "")] + ([(home, "~/")] if home is not None else [])
        for base, label in bases:
            try:
                return label + p.relative_to(base).as_posix()
            except ValueError:
                pass
        return str(p)

    def say(name: str, status: str, where: str = "", why: str = "") -> None:
        line = f"  {name:<8} {status:<14} {where}"
        print((line + (f"  ({why})" if why else "")).rstrip(), file=out)

    try:
        kind = hook.ephemeral()
    except RuntimeError:  # hook.ephemeral()'s own Path.home() call, unguarded (hook.py, a different squad's
        kind = None       # file): no HOME/USERPROFILE means the cache-location check just can't run here
    if kind:
        print(f"rewindagents init: nothing written: {hook.ephemeral_message(kind)}", file=out)
        return 2
    run = hook.invocation()
    found = detect(root, home, global_, path)
    if only:
        found = [dict(f, found=f["found"] or ["--agent"]) for f in found if f["agent"] in only]
    print(f"rewindagents init: {'your user config (every project)' if global_ else 'project ' + str(root)}",
          file=out)
    todo, rows, errors = [], [], 0
    for f in found:
        name = f["agent"]
        if not f["found"]:
            rows.append((name, "not found", "", ""))
            continue
        cmd = hook.hook_command(name)
        st, detail = state(name, f["target"], cmd)
        why = "found: " + ", ".join(f["found"])
        if st == "install":
            todo.append(f)
            rows.append((name, "will install", show(f["target"]), why))
        elif st == "stale":
            todo.append(f)
            rows.append((name, "will replace", show(f["target"]), detail))
        elif st == "already":
            rows.append((name, "already there", show(f["target"]), ""))
        elif st == "other":
            rows.append((name, "already there", show(f["target"]), detail))
        else:
            errors += 1
            rows.append((name, "error", show(f["target"]), detail))
    if not todo:
        for r in rows:
            say(*r)
        if not any(f["found"] for f in found):
            print("No supported agent found (claude, codex, cursor, gemini, copilot, droid, qwen). "
                  "Install one, or add the hook by hand: rewindagents install --agent NAME", file=out)
            return 1
        return 1 if errors else 0
    if not yes:
        for r in rows:
            say(*r)
        if not is_terminal(stdin):
            print("Dry run: nothing written (no --yes, and no terminal to ask on). "
                  f"To install: {run} init --yes" + (" --global" if global_ else ""), file=out)
            return 0
        print(f"Install the hook for {len(todo)} agent{'s' if len(todo) != 1 else ''}? [y/N] ", end="",
              file=out, flush=True)
        answer = stdin.readline().strip().lower()
        if answer not in ("y", "yes"):
            print("Nothing written.", file=out)
            return 0
    wanted = {f["agent"] for f in todo}
    notes, created, tracked = [], [], []
    for name, status, where, why in rows:
        if name not in wanted:
            say(name, status, where, why)
            continue
        t = next(f["target"] for f in todo if f["agent"] == name)
        existed = t.exists()
        try:
            dead = hook.replace_stale(t, agent=name)
            if dead and state(name, t, hook.hook_command(name))[0] == "other":
                say(name, "removed stale", where, "another rewindagents hook, which can run, is left as is")
                continue
            # Pass the already-computed command: hook.install() only calls the unguarded hook.ephemeral()
            # itself when `command` is omitted, and the `kind` check above already covers that for this run.
            changed = hook.install(t, command=hook.hook_command(name), agent=name)
        except (ValueError, OSError) as e:
            errors += 1
            say(name, "error", where, f"not written: {e}")
            continue
        if changed and not global_:
            if not existed:
                created.append(t)
            elif _tracked(t):
                tracked.append(where)
        if dead:
            say(name, "replaced", where, f"was stale: {dead[0][1]}")
        else:
            say(name, "installed" if changed else "already there", where)
        if name in NOTES:
            notes.append(f"{name}: {NOTES[name]}")
    for n in notes:
        print(n, file=out)
    now_excluded = set_excluded(root, add=created) if created else []
    hidden = [show(t) for t in created if "/" + show(t) in now_excluded or any(
        q.endswith("/" + show(t)) for q in now_excluded)]
    if hidden:
        print(f"Kept out of git (.git/info/exclude, this clone only): {', '.join(hidden)}. "
              f"{'They name' if len(hidden) > 1 else 'It names'} this machine's Python; teammates run "
              f"`rewindagents init` themselves.", file=out)
    for w in tracked:
        print(f"Note: {w} is tracked by git and now names this machine's Python; do not commit that hook "
              f"(or use `{run} init --global` instead).", file=out)
    print(f"Next: run your agent as usual, then `{run} summary` to see what it did. "
          f"Undo this setup: `{run} init --undo`.", file=out)
    return 1 if errors else 0


def _empty_config(settings) -> bool:
    """A config that holds nothing but empty hook containers ({}, {"hooks": {}}, {"version": 1, "hooks": {}})."""
    if not isinstance(settings, dict):
        return False
    rest = {k: v for k, v in settings.items() if k not in ("hooks", "version")}
    return not rest and not settings.get("hooks")


def undo(global_: bool = False, root: Path | None = None, home: Path | None = None, out=None,
         only: list[str] | None = None) -> int:
    """`rewindagents init --undo`: remove every rewindagents hook (any interpreter, stale or not) from each
    agent's config file that init writes, leaving every other hook and key. A file left holding nothing but
    empty hook containers is deleted, with the agent directory when that is then empty, and its line in
    .git/info/exclude goes too. The recorded history (.rewindagents/) is never touched."""
    root = Path(root or Path.cwd()).resolve()
    if home is None:
        try:
            home = Path.home()
        except RuntimeError:  # no HOME/USERPROFILE in this environment (seen on windows-latest CI); see
            home = None       # project.py's find_store_root -- a project-local undo still works without it
    else:
        home = Path(home)
    out = out or sys.stdout
    removed, deleted, errors = 0, [], 0
    print(f"rewindagents init --undo: {'your user config (every project)' if global_ else 'project ' + str(root)}",
          file=out)
    for name in agents.AGENTS:
        if only and name not in only:
            continue
        if global_ and home is None:
            continue   # cannot find a user config file without a home directory to look in
        t = target(name, root, home, global_)
        where = ("~/" if global_ else "") + t.relative_to(home if global_ else root).as_posix()
        if not t.is_file():
            continue
        try:
            have = agents.commands_in(agents.AGENTS[name], t) if t.read_text(encoding="utf-8").strip() else {}
            mine = sorted({c for cmds in have.values() for c in cmds if hook.ours(c)})
            for c in mine:
                agents.uninstall(agents.AGENTS[name], t, c)
        except (ValueError, OSError, AttributeError, TypeError, KeyError) as e:
            errors += 1
            print(f"  {name:<8} {'error':<14} {where}  (not changed: {e})", file=out)
            continue
        if not mine:
            print(f"  {name:<8} {'no hook':<14} {where}", file=out)
            continue
        removed += 1
        try:
            empty = _empty_config(json.loads(t.read_text(encoding="utf-8") or "{}"))
        except (ValueError, OSError):
            empty = False
        if empty:
            t.unlink()
            deleted.append(t)
            d = t.parent
            stop = home if global_ else root
            while d != stop and d.is_dir() and not any(d.iterdir()):
                d.rmdir()
                d = d.parent
            print(f"  {name:<8} {'removed':<14} {where}  (file deleted: it held nothing else)", file=out)
        else:
            print(f"  {name:<8} {'removed':<14} {where}  (other settings and hooks kept)", file=out)
    if deleted and not global_:
        set_excluded(root, remove=deleted)
    if not removed and not errors:
        print("No rewindagents hook found; nothing changed.", file=out)
    if not global_ and (root / ".rewindagents").is_dir():
        # the project's recorded history is per-project either way (a global hook still records into the
        # project the agent runs in): there is no "home" half of this to guard against home being None.
        print("Your recorded history in .rewindagents/ is kept: replay and rewind still work. "
              "To delete it too: rm -rf .rewindagents", file=out)
    return 1 if errors else 0
