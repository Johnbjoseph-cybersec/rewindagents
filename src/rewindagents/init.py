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
command (another interpreter, or a clone) is reported and left alone rather than given a second hook.

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
from pathlib import Path

from . import agents, hook

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
    """("install" | "already" | "other" | "error", detail) for this agent's config file."""
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
    if events and all(command in cmds for cmds in events):
        return "already", ""
    others = sorted({c for cmds in events for c in cmds if "rewindagents hook" in c and c != command})
    if others:
        return "other", f"holds another rewindagents hook ({others[0]}); left as is"
    return "install", ""


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
            changed = hook.install(t, agent=name)
        except (ValueError, OSError) as e:
            errors += 1
            say(name, "error", where, f"not written: {e}")
            continue
        say(name, "installed" if changed else "already there", where)
        if name in NOTES:
            notes.append(f"{name}: {NOTES[name]}")
    for n in notes:
        print(n, file=out)
    print(f"Next: run your agent as usual, then `{run} replay` to see what it did.", file=out)
    return 1 if errors else 0
