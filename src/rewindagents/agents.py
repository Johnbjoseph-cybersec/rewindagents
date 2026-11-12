"""The coding agents rewindagents hooks into, and how each one's hook protocol differs.

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

Read on 2026-11-12 (same rule: every field name quoted from the vendor page named):

- Gemini CLI: https://geminicli.com/docs/hooks/ , https://geminicli.com/docs/hooks/reference/ and the tool list
  https://geminicli.com/docs/reference/tools/
  Config: `.gemini/settings.json` in the project (or `~/.gemini/settings.json`), `{"hooks": {"BeforeTool":
  [{"matcher": "...", "hooks": [{"type": "command", "command": "..."}]}]}}`; `"*"` or `""` matches every tool.
  Events `BeforeTool` and `AfterTool`. Stdin: `session_id`, `transcript_path`, `cwd`, `hook_event_name`,
  `timestamp`; BeforeTool adds `tool_name`, `tool_input`, `mcp_context`, `original_request_name`; AfterTool adds
  `tool_response` (`llmContent`, `returnDisplay`, `error`). No call id. Tools: `run_shell_command`; `write_file`
  and `replace` (kind Edit); read-only: `read_file`, `read_many_files`, `list_directory`, `glob`, `grep_search`
  (alias `search_file_content`), `google_web_search`, `web_fetch`. Output: on exit 0 "stdout is parsed as JSON"
  and the script "must not print any plain text to stdout other than the final JSON"; only `"decision": "deny"`
  (or `"block"`), `continue: false` and exit 2 stop anything. So the hook prints `{}` (no decision field) for
  every event. The page notes Gemini CLI was replaced by Antigravity CLI on June 18th, 2026 for unpaid tier and
  Google One users.

- GitHub Copilot CLI: https://docs.github.com/en/copilot/reference/hooks-configuration and
  https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/use-hooks
  Config: `.github/hooks/<NAME>.json` in the repository (or `~/.copilot/hooks/`), `{"version": 1, "hooks":
  {"<event>": [{"type": "command", "bash": "..."}]}}`; no "matcher" = every tool. "Two payload formats are
  supported, selected by the event name used in the hook configuration": camelCase `preToolUse` sends
  `sessionId`/`toolName`/`toolArgs` and no event name; PascalCase `PreToolUse`/`PostToolUse` selects the VS Code
  format with `hook_event_name`, `session_id`, `timestamp`, `cwd`, `tool_name`, `tool_input` and, after the call,
  `tool_result` (`result_type`, `text_result_for_llm`). rewindagents installs the PascalCase events so the payload
  names its event. Tools: `bash` (shell), `create`, `edit`; read and search: `view`, `grep`, `glob`; `web_fetch`.
  Output: empty stdout "falls through to default behavior" (preToolUse) and "Return {} or empty output to keep
  the original successful result" (postToolUse), so the hook prints nothing. A failed call goes to
  `PostToolUseFailure` (`error` in place of `tool_result`); the hook is installed there too, to close the scan. But "Command preToolUse hooks are
  fail-closed on errors": "a crash or non-zero exit (including exit 2) denies the tool call". The hook exits 0,
  and the installed command ends in `|| true`, so even an interpreter that is missing (the cloud agent's sandbox
  does not have this machine's Python) exits 0 and blocks nothing; there it records nothing.

- Factory Droid: https://docs.factory.com/reference/hooks-reference (was docs.factory.ai)
  Config: `.factory/hooks.json` (keyed by event name at the top level) or, "if hooks.json is absent", the
  `hooks` key of `.factory/settings.json`; groups of `{"matcher": ..., "hooks": [{"type": "command", "command":
  ...}]}`, matcher optional, `*` matches everything. So install writes `.factory/hooks.json` when it exists and
  `.factory/settings.json` otherwise: creating hooks.json would hide hooks the user keeps in settings.json.
  Stdin: `session_id`, `transcript_path`, `cwd`, `permission_mode`, `hook_event_name`, `tool_name`, `tool_input`
  and on PostToolUse `tool_response`. No call id. Tools: `Execute` (`tool_input.command`), `Create`
  (`file_path`, `content`), `Edit`, `ApplyPatch`, `Task`; read-only: `Read`, `LS`, `Glob`, `Grep`, `FetchUrl`,
  `WebSearch`. Exit 0 is success (stdout is shown in transcript views), exit 2 blocks PreToolUse, other codes
  are non-blocking. The hook prints nothing.

- Qwen Code: https://github.com/QwenLM/qwen-code/blob/main/docs/users/features/hooks.md and the tool ids
  https://github.com/QwenLM/qwen-code/blob/main/docs/developers/tools/file-system.md (the same pages the
  project publishes as its docs site)
  Config: `.qwen/settings.json`, `{"hooks": {"PreToolUse": [{"matcher": "...", "hooks": [{"type": "command",
  "command": "..."}]}]}}`; a matcher entry of `*` or `.*` matches every tool. Stdin: `session_id`,
  `transcript_path`, `cwd`, `hook_event_name`, `timestamp`, `permission_mode`; PreToolUse adds `tool_name`,
  `tool_input`, `tool_use_id`, `tool_call_id`; PostToolUse ("after a tool completes successfully") adds
  `tool_response` and `duration_ms`; PostToolUseFailure ("when a tool execution fails") has `tool_use_id`,
  `tool_name`, `tool_input`, `error`, `is_interrupt`. A failed call can still have changed files, so the hook
  is installed on PostToolUseFailure too and that event closes the scan like PostToolUse. Tools:
  `run_shell_command`, `write_file`, `edit`, `notebook_edit`; read-only: `read_file`, `list_directory`, `glob`,
  `grep_search`. Exit 0 with a JSON object controls behaviour, other stdout is "kept as a system message",
  exit 2 blocks; the hook prints nothing.

Not supported, and why (same date): Windsurf's Cascade hooks page now redirects to Devin's
(docs.devin.ai/desktop/cascade/hooks); Devin's hooks (https://docs.devin.ai/cli/extensibility/hooks/overview.md)
document no `cwd` and not where the command runs, so the project cannot be found from the payload (Devin also
reads `.claude/settings.json` by default, so a Claude Code install fires there too, as the Claude Code hook).
Kiro (https://kiro.dev/docs/hooks/types/) documents the PreToolUse payload but not PostToolUse's. Cline
(https://docs.cline.bot/customization/hooks.md -> SDK plugins), OpenCode (https://opencode.ai/docs/plugins/) and
Amp (https://ampcode.com/docs/plugin-api) are JavaScript/TypeScript plugins, not command hooks. Roo Code, Zed,
Warp and Replit document no tool hooks.

What is and is not verified: the Codex, Cursor, Gemini CLI, Copilot CLI, Droid and Qwen Code payloads in
tests/test_agents*.py are the documented ones, and the hook has not yet run inside a live session of any of
them. The README says so.
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
GEMINI_DOCS = "https://geminicli.com/docs/hooks/reference/"
COPILOT_DOCS = "https://docs.github.com/en/copilot/reference/hooks-configuration"
DROID_DOCS = "https://docs.factory.com/reference/hooks-reference"
QWEN_DOCS = "https://github.com/QwenLM/qwen-code/blob/main/docs/users/features/hooks.md"
DOCS_READ_2 = "2026-11-12"


@dataclass(frozen=True)
class Agent:
    name: str
    settings: str                 # default config file, relative to the project
    events: tuple[str, str]       # the pre and post event names as the agent spells them
    shape: str                    # "groups": {"hooks": {event: [{"matcher", "hooks": [...]}]}} (Claude Code, Codex,
                                  # Gemini CLI, Droid, Qwen Code); "cursor": {"version": 1, "hooks": {event:
                                  # [entry]}} (Cursor, Copilot CLI)
    reply: dict[str, str] = field(default_factory=dict)   # what to print on stdout per event ("" = nothing)
    read_only: frozenset = frozenset()   # tools the docs name that cannot change files: not scanned
    file_tools: bool = False      # True when the pre payload names the file an edit tool will change
    entry: tuple = ()             # "cursor" shape: the documented keys of one entry before the command
    command_key: str = "command"  # "cursor" shape: the key that holds the command (Copilot: "bash")
    fail_closed: bool = False     # a non-zero exit counts as a deny: the command is written with `|| true`
    prefer: str = ""              # a config file used in place of `settings` when it exists (Droid)
    flat: frozenset = frozenset()  # file names whose top level IS the hooks object (Droid's hooks.json)
    also_post: tuple = ()         # more events that end a call (a failed call): installed, and read as "post"


AGENTS: dict[str, Agent] = {
    "claude": Agent("claude", ".claude/settings.json", ("PreToolUse", "PostToolUse"), "groups", file_tools=True),
    "codex": Agent("codex", ".codex/hooks.json", ("PreToolUse", "PostToolUse"), "groups",
                   read_only=frozenset({"update_plan"})),
    "cursor": Agent("cursor", ".cursor/hooks.json", ("preToolUse", "postToolUse"), "cursor",
                    reply={"pre": '{"permission": "allow"}', "post": "{}", "unknown": '{"permission": "allow"}'},
                    read_only=frozenset({"Read", "Grep"})),
    "gemini": Agent("gemini", ".gemini/settings.json", ("BeforeTool", "AfterTool"), "groups",
                    reply={"pre": "{}", "post": "{}", "unknown": "{}"},
                    read_only=frozenset({"read_file", "read_many_files", "list_directory", "glob", "grep_search",
                                         "search_file_content", "google_web_search", "web_fetch"})),
    "copilot": Agent("copilot", ".github/hooks/rewindagents.json", ("PreToolUse", "PostToolUse"), "cursor",
                     read_only=frozenset({"view", "grep", "glob", "web_fetch"}),
                     entry=(("type", "command"),), command_key="bash", fail_closed=True,
                     also_post=("PostToolUseFailure",)),
    "droid": Agent("droid", ".factory/settings.json", ("PreToolUse", "PostToolUse"), "groups",
                   read_only=frozenset({"Read", "LS", "Glob", "Grep", "FetchUrl", "WebSearch"}),
                   prefer=".factory/hooks.json", flat=frozenset({"hooks.json"})),
    "qwen": Agent("qwen", ".qwen/settings.json", ("PreToolUse", "PostToolUse"), "groups",
                  read_only=frozenset({"read_file", "list_directory", "glob", "grep_search"}),
                  also_post=("PostToolUseFailure",)),
}
DEFAULT = "claude"


def normalize(payload: dict) -> dict[str, Any]:
    """The fields the hook needs, under one set of names, whichever agent sent the payload."""
    raw = str(payload.get("hook_event_name") or "")
    event = {"pretooluse": "pre", "posttooluse": "post", "posttoolusefailure": "post",
             "beforetool": "pre", "aftertool": "post"}.get(
        raw.lower(), raw or "unknown")
    cwd = payload.get("cwd")
    if not cwd:
        roots = payload.get("workspace_roots")
        cwd = roots[0] if isinstance(roots, list) and roots and isinstance(roots[0], str) else os.getcwd()
    if "tool_response" in payload:
        response = payload["tool_response"]
    elif "tool_result" in payload:                      # Copilot CLI, VS Code format
        response = payload["tool_result"]
    elif "error" in payload:                            # PostToolUseFailure (Copilot CLI, Qwen Code)
        response = {"error": payload["error"]}
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
    Every other agent: every call except the tools the docs name that cannot change files, because the input
    shape of some edit tools is not documented (Codex's apply_patch, Cursor's Write, Droid's Edit), a shell or
    MCP call names no file at all, and a scan needs no shape.
    """
    if agent.file_tools:
        return tool == "Bash"
    return tool not in agent.read_only


def config_path(agent: Agent, root: str | Path = ".") -> str:
    """The agent's config file in the project at `root`, relative to it: `agent.prefer` when that file exists
    (Droid reads settings.json's hooks only when hooks.json is absent), else `agent.settings`."""
    if agent.prefer and (Path(root) / agent.prefer).exists():
        return agent.prefer
    return agent.settings


def _hooks(agent: Agent, p: Path, settings: dict, create: bool) -> dict | None:
    """The object keyed by event name: the file itself for a flat file, else its "hooks" key."""
    if p.name in agent.flat:
        return settings
    if create:
        return settings.setdefault("hooks", {})
    h = settings.get("hooks")
    return h if isinstance(h, dict) else None


def install(agent: Agent, settings_path: str | Path, command: str) -> bool:
    """Add the hook command to the agent's config file. Keeps everything already there.

    Returns True if the file changed, False if the hook was already installed.
    """
    p = Path(settings_path)
    text = p.read_text(encoding="utf-8") if p.exists() else ""
    settings = json.loads(text) if text.strip() else {}
    if not isinstance(settings, dict):
        raise ValueError(f"{p} does not hold a JSON object")
    hooks = _hooks(agent, p, settings, create=True)
    changed = False
    if agent.shape == "cursor":
        if settings.get("version") is None:
            settings = {"version": 1, **settings}
            changed = True
        for event in agent.events + agent.also_post:
            entries = hooks.setdefault(event, [])
            if not any(isinstance(h, dict) and h.get(agent.command_key) == command for h in entries):
                entries.append({**dict(agent.entry), agent.command_key: command})
                changed = True
    else:
        for event in agent.events + agent.also_post:
            groups = hooks.setdefault(event, [])
            present = any(h.get("command") == command for g in groups for h in g.get("hooks", []))
            if not present:
                groups.append({"matcher": "*", "hooks": [{"type": "command", "command": command}]})
                changed = True
    if changed:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".rewindagents.tmp")
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
    hooks = _hooks(agent, p, settings, create=False)
    if hooks is None:
        return False
    changed = False
    for event in agent.events + agent.also_post:
        entries = hooks.get(event)
        if not isinstance(entries, list):
            continue
        kept = []
        for e in entries:
            if agent.shape == "cursor":
                if isinstance(e, dict) and e.get(agent.command_key) == command:
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
    if not hooks and hooks is not settings:
        del settings["hooks"]
    tmp = p.with_name(p.name + ".rewindagents.tmp")
    tmp.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, p)
    return True


def commands_in(agent: Agent, settings_path: str | Path) -> dict[str, list[str]]:
    """The hook commands a config file holds, per event. Used by the tests to read back what `install` wrote."""
    settings = json.loads(Path(settings_path).read_text(encoding="utf-8"))
    out: dict[str, list[str]] = {}
    hooks = _hooks(agent, Path(settings_path), settings, create=False) or {}
    for event in agent.events + agent.also_post:
        entries = hooks.get(event, [])
        if agent.shape == "cursor":
            k = agent.command_key
            out[event] = [h[k] for h in entries if isinstance(h, dict) and k in h]
        else:
            out[event] = [h["command"] for g in entries for h in g.get("hooks", [])]
    return out
