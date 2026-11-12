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
import sys
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


def target(name: str, root: Path, home: Path, global_: bool) -> Path:
    """The config file init writes for this agent."""
    ag = agents.AGENTS[name]
    if not global_:
        return root / agents.config_path(ag, root)
    if name == "copilot":
        return home / ".copilot" / "hooks" / "rewindagents.json"
    return home / agents.config_path(ag, home)


def detect(root: Path, home: Path, global_: bool = False, path: str | None = None) -> list[dict]:
    """One entry per supported agent: {"agent", "found": [why], "target"}. `found` is empty when absent."""
    out = []
    for name in agents.AGENTS:
        found = []
        if not global_ and (root / PROJECT_DIRS[name]).is_dir():
            found.append(f"{PROJECT_DIRS[name]}/")
        if (home / USER_DIRS[name]).is_dir():
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


def status(global_: bool = False, root: Path | None = None, home: Path | None = None, out=None,
           log_path: str | Path | None = None) -> int:
    """`rewindagents status`: one line per agent config file that exists: hook ok, stale, another one, or none;
    then one line for this project's log: records, time of the last one, and whether the chain verifies.
    Writes nothing. Exit 1 when any file holds a stale hook (or cannot be read) or the log does not verify."""
    root = Path(root or Path.cwd()).resolve()
    home = Path(home or Path.home())
    out = out or sys.stdout
    run = "rewindagents" if hook.installed() else "python3 -m rewindagents"
    bad, shown, hooked = 0, 0, 0
    for name in agents.AGENTS:
        t = target(name, root, home, global_)
        if not t.is_file():
            continue
        shown += 1
        where = str(t.relative_to(home if global_ else root))
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
            line, why = "ok", "another rewindagents hook, which can run"
            hooked += 1
        elif any(hook.ours(c) for cmds in agents.commands_in(agents.AGENTS[name], t).values() for c in cmds):
            line, why = "partial", "not on every event"
        else:
            line, why = "no hook", ""
        print((f"  {name:<8} {line:<8} {where}" + (f"  ({why})" if why else "")).rstrip(), file=out)
    if not shown:
        print(f"No agent config file {'in your home directory' if global_ else 'in this project'}. "
              f"To add the hook: {run} init", file=out)
    if bad:
        print(f"A stale hook records nothing. Fix: {run} init --yes" + (" --global" if global_ else ""), file=out)
    # The log is always this project's: a global hook records into the project the agent runs in too.
    default = ".rewindagents/log.jsonl"
    lp = Path(log_path or default)
    lp = lp if lp.is_absolute() else root / lp
    if str(log_path or default) != default:
        run = f"{run} --log {log_path}"
    try:
        where = str(lp.relative_to(root))
    except ValueError:
        where = str(lp)
    rec, detail = recording(lp)
    print(f"  {'log':<8} {rec:<8} {where}  ({detail})", file=out)
    if rec == "BROKEN":
        print(f"The log does not verify: a record was edited, removed or damaged. Details: {run} verify", file=out)
    elif rec == "none" and hooked:
        print("A hook is in place but nothing is recorded yet. Run the agent once; if it made a tool call and "
              "there is still no record, the hook is failing: run the hook command by hand to see why.", file=out)
    return 1 if bad or rec == "BROKEN" else 0


def main(yes: bool = False, global_: bool = False, root: Path | None = None, home: Path | None = None,
         path: str | None = None, stdin=None, out=None) -> int:
    root = Path(root or Path.cwd()).resolve()
    home = Path(home or Path.home())
    stdin, out = stdin or sys.stdin, out or sys.stdout

    def show(p: Path) -> str:
        for base, label in ((root, ""), (home, "~/")):
            try:
                return label + str(p.relative_to(base))
            except ValueError:
                pass
        return str(p)

    def say(name: str, status: str, where: str = "", why: str = "") -> None:
        line = f"  {name:<8} {status:<14} {where}"
        print((line + (f"  ({why})" if why else "")).rstrip(), file=out)

    kind = hook.ephemeral()
    if kind:
        print(f"rewindagents init: nothing written: {hook.ephemeral_message(kind)}", file=out)
        return 2
    run = "rewindagents" if hook.installed() else "python3 -m rewindagents"
    found = detect(root, home, global_, path)
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
        if not (hasattr(stdin, "isatty") and stdin.isatty()):
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
    notes = []
    for name, status, where, why in rows:
        if name not in wanted:
            say(name, status, where, why)
            continue
        t = next(f["target"] for f in todo if f["agent"] == name)
        try:
            dead = hook.replace_stale(t, agent=name)
            if dead and state(name, t, hook.hook_command(name))[0] == "other":
                say(name, "removed stale", where, "another rewindagents hook, which can run, is left as is")
                continue
            changed = hook.install(t, agent=name)
        except (ValueError, OSError) as e:
            errors += 1
            say(name, "error", where, f"not written: {e}")
            continue
        if dead:
            say(name, "replaced", where, f"was stale: {dead[0][1]}")
        else:
            say(name, "installed" if changed else "already there", where)
        if name in NOTES:
            notes.append(f"{name}: {NOTES[name]}")
    for n in notes:
        print(n, file=out)
    print(f"Next: run your agent as usual, then `{run} replay` to see what it did.", file=out)
    return 1 if errors else 0
