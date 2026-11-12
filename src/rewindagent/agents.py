"""The coding agents rewindagent hooks into, and how each one's hook protocol differs.

The hook body (hook.py) is the same for all of them: record the call, checkpoint first, never block. This
module holds what differs: where the hook is configured, the shape of that file, the names of the fields in
the JSON the agent sends on stdin, what the hook must print, and which tools are known not to change files.

Sources, read on 2026-11-11 (every field name below is quoted from them):

- Cursor: https://cursor.com/docs/agent/hooks
  Config: `.cursor/hooks.json` in the project (or `~/.cursor/hooks.json`), `{"version": 1, "hooks": {"<event>":
  [{"command": "..."}]}}`; a hook with no "matcher" runs for every tool. Events `preToolUse` and `postToolUse`.
  Common stdin fields: `conversation_id`, `generation_id`, `hook_event_name`, `workspace_roots`. preToolUse adds
  `tool_name`, `tool_input`, `tool_use_id`, `cwd`; postToolUse adds `tool_output` ("JSON-stringified result
  payload from the tool") and `duration`. Tool names: `Shell`, `Read`, `Write`, `Grep`, `Delete`, `Task`,
  `MCP:<tool_name>`. The documented `tool_input` is Shell's: `{"command": ..., "working_directory": ...}`; the
  input of `Write` is not documented, so this module never reads a file path out of a Cursor payload. Output:
  preToolUse is a permission hook and "invalid JSON or a response that doesn't match the schema blocks the
  action", so the hook prints `{"permission": "allow"}` (a deny from any other hook still wins: "deny beats ask
  beats allow"); postToolUse prints `{}`. Exit 2 blocks; the hook exits 0.

- Codex: https://developers.openai.com/codex/hooks (served from https://learn.chatgpt.com/docs/hooks)
  Config: `.codex/hooks.json` in the project (or `~/.codex/hooks.json`), the same shape as Claude Code's
  settings: `{"hooks": {"PreToolUse": [{"matcher": "...", "hooks": [{"type": "command", "command": "..."}]}]}}`.
  Stdin: `session_id`, `cwd`, `hook_event_name`, `tool_name`, `tool_use_id`, `tool_input`, and on PostToolUse
  `tool_response`. Tool names: shell commands match as `Bash`, file edits as `apply_patch`, MCP tools as
  `mcp__<server>__<tool>`, other local tools by their function name (for example `update_plan`). Plain text on
  stdout is ignored for PreToolUse and PostToolUse and exit 0 with no output is success, so the hook prints
  nothing. Codex asks the user to trust a hook before it runs (`/hooks`), and remembers the trust by the hook's
  hash; project hooks load only when the project's `.codex/` layer is trusted.

- Claude Code: `.claude/settings.json`, events `PreToolUse` and `PostToolUse`, fields `session_id`, `cwd`,
  `hook_event_name`, `tool_name`, `tool_input`, `tool_use_id`, `tool_response`; stdout empty. Built in R2 and
  driven by a real Claude Code session; the fixtures in tests/test_hook.py are its payloads.

What is and is not verified: the Codex and Cursor payloads in tests/test_agents.py are the documented ones, and
the hook has not yet run inside a live Codex or Cursor session. The README says so.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CURSOR_DOCS = "https://cursor.com/docs/agent/hooks"
CODEX_DOCS = "https://developers.openai.com/codex/hooks"
DOCS_READ = "2026-11-11"


@dataclass(frozen=True)
class Agent:
    name: str
    settings: str                 # default config file, relative to the project
    events: tuple[str, str]       # the pre and post event names as the agent spells them
    shape: str                    # config file shape: "groups" (Claude Code, Codex) or "cursor"
    reply: dict[str, str] = field(default_factory=dict)   # what to print on stdout per event ("" = nothing)
    read_only: frozenset = frozenset()   # tools the docs name that cannot change files: not scanned
    file_tools: bool = False      # True when the pre payload names the file an edit tool will change


AGENTS: dict[str, Agent] = {
    "claude": Agent("claude", ".claude/settings.json", ("PreToolUse", "PostToolUse"), "groups", file_tools=True),
    "codex": Agent("codex", ".codex/hooks.json", ("PreToolUse", "PostToolUse"), "groups",
                   read_only=frozenset({"update_plan"})),
    "cursor": Agent("cursor", ".cursor/hooks.json", ("preToolUse", "postToolUse"), "cursor",
                    reply={"pre": '{"permission": "allow"}', "post": "{}", "unknown": '{"permission": "allow"}'},
                    read_only=frozenset({"Read", "Grep"})),
}
DEFAULT = "claude"


def normalize(payload: dict) -> dict[str, Any]:
    """The fields the hook needs, under one set of names, whichever agent sent the payload."""
    raw = str(payload.get("hook_event_name") or "")
    event = {"pretooluse": "pre", "posttooluse": "post"}.get(raw.lower(), raw or "unknown")
    cwd = payload.get("cwd")
    if not cwd:
        roots = payload.get("workspace_roots")
        cwd = roots[0] if isinstance(roots, list) and roots and isinstance(roots[0], str) else os.getcwd()
    if "tool_response" in payload:
        response = payload["tool_response"]
    else:
        response = payload.get("tool_output")           # Cursor: a JSON string; keep it as sent if it is not
        if isinstance(response, str):
            try:
                response = json.loads(response)
            except ValueError:
                pass
    return {"event": event, "session": payload.get("session_id") or payload.get("conversation_id") or "unknown",
            "cwd": Path(cwd), "tool": payload.get("tool_name", "?"), "input": payload.get("tool_input") or {},
            "response": response}


def scans(agent: Agent, tool: str) -> bool:
    """Whether the project is scanned before and after this call (bashscan.py).

    Claude Code: Bash only (Write/Edit/MultiEdit/NotebookEdit name their file and are checkpointed directly).
    Codex and Cursor: every call except the tools the docs name that cannot change files, because the input
    shape of their edit tools is not documented and a scan needs no shape.
    """
    if agent.file_tools:
        return tool == "Bash"
    return tool not in agent.read_only


def install(agent: Agent, settings_path: str | Path, command: str) -> bool:
    """Add the hook command to the agent's config file. Keeps everything already there.

    Returns True if the file changed, False if the hook was already installed.
    """
    p = Path(settings_path)
    text = p.read_text(encoding="utf-8") if p.exists() else ""
    settings = json.loads(text) if text.strip() else {}
    if not isinstance(settings, dict):
        raise ValueError(f"{p} does not hold a JSON object")
    hooks = settings.setdefault("hooks", {})
    changed = False
    if agent.shape == "cursor":
        if settings.get("version") is None:
            settings = {"version": 1, **settings}
            changed = True
        for event in agent.events:
            entries = hooks.setdefault(event, [])
            if not any(isinstance(h, dict) and h.get("command") == command for h in entries):
                entries.append({"command": command})
                changed = True
    else:
        for event in agent.events:
            groups = hooks.setdefault(event, [])
            present = any(h.get("command") == command for g in groups for h in g.get("hooks", []))
            if not present:
                groups.append({"matcher": "*", "hooks": [{"type": "command", "command": command}]})
                changed = True
    if changed:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".rewindagent.tmp")
        tmp.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, p)
    return changed


def uninstall(agent: Agent, settings_path: str | Path, command: str) -> bool:
    """Remove the hook entries whose command is exactly `command` (the one `install` writes). Keeps every other
    hook and key; a group or event list is dropped only when removing our entry left it empty.

    Returns True if the file changed. When nothing matches (or the file does not exist) the file is not
    rewritten, so it stays byte-identical.
    """
    p = Path(settings_path)
    if not p.exists():
        return False
    text = p.read_text(encoding="utf-8")
    settings = json.loads(text) if text.strip() else {}
    if not isinstance(settings, dict):
        raise ValueError(f"{p} does not hold a JSON object")
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return False
    changed = False
    for event in agent.events:
        entries = hooks.get(event)
        if not isinstance(entries, list):
            continue
        kept = []
        for e in entries:
            if agent.shape == "cursor":
                if isinstance(e, dict) and e.get("command") == command:
                    changed = True
                    continue
            elif isinstance(e, dict) and isinstance(e.get("hooks"), list):
                inner = [h for h in e["hooks"] if not (isinstance(h, dict) and h.get("command") == command)]
                if len(inner) != len(e["hooks"]):
                    changed = True
                    if not inner:
                        continue
                    e = {**e, "hooks": inner}
            kept.append(e)
        if kept != entries:
            if kept:
                hooks[event] = kept
            else:
                del hooks[event]
    if not changed:
        return False
    if not hooks:
        del settings["hooks"]
    tmp = p.with_name(p.name + ".rewindagent.tmp")
    tmp.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, p)
    return True


def commands_in(agent: Agent, settings_path: str | Path) -> dict[str, list[str]]:
    """The hook commands a config file holds, per event. Used by the tests to read back what `install` wrote."""
    settings = json.loads(Path(settings_path).read_text(encoding="utf-8"))
    out: dict[str, list[str]] = {}
    for event in agent.events:
        entries = settings.get("hooks", {}).get(event, [])
        if agent.shape == "cursor":
            out[event] = [h["command"] for h in entries if isinstance(h, dict) and "command" in h]
        else:
            out[event] = [h["command"] for g in entries for h in g.get("hooks", [])]
    return out
