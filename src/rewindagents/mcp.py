"""`rewindagents mcp`: a stdio MCP server, Python standard library only (json, sys -- nothing else).

Newline-delimited JSON-RPC 2.0 on stdin and stdout. One process per client; it runs until stdin
closes, then exits 0. It never crashes on bad input: a line that is not JSON gets a parse error
(-32700), an unrecognised method gets -32601, and a notification (any "notifications/..." method, or
a request with no "id") never gets a reply at all, as JSON-RPC and the Model Context Protocol both
require. One more fence sits around every tool call (`serve`'s `except Exception`): a bug in one call
must not end the stdio session for every call after it; it answers with an internal-error response
(or, for a notification, a line on stderr) and keeps reading.

Seven tools, two kinds:
- read-only (rewind_sessions, rewind_summary, rewind_diff, rewind_replay, rewind_preview): each wraps
  the matching `jsonout.py` shape -- the same one the CLI's `--json` flag prints -- as the tool
  result's text, so an agent reading this server and a script reading `rewindagents diff --step N
  --json` read the same JSON. Two of the five redact secrets by default, unlike their CLI
  counterparts: `rewind_replay` always (no argument turns it off -- see `_tool_rewind_replay`) and
  `rewind_diff` unless the call sets `reveal_secrets: true` (see `_tool_rewind_diff`). A result from
  this server is as likely to end up in another LLM's own context as in a terminal, which the CLI's
  unredacted `diff` default never had to consider.
- destructive (rewind_to_step, rewind_revert_step): both need `confirm: true` in the call's own
  arguments -- there is no `force` argument on either, and the server never retries past a refusal.
  Missing it comes back as an error telling the caller to ask the user and call again. A refusal that
  `rewind.py` or `revert.py` already enforces (a file changed since, the step doesn't merge cleanly)
  comes back as that module's own message, unchanged -- this file never writes `force=True` on a
  caller's behalf and never tries a second time.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

from . import __version__, jsonout, project, rewind, sessions
from . import revert as reverts

PROTOCOL_VERSION = "2025-06-18"
KNOWN_PROTOCOL_VERSIONS = frozenset({PROTOCOL_VERSION})


def _ok(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": False}


def _err(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": True}


def _log_path() -> Path:
    """The project log the CLI uses with no --log: this directory's, else the nearest parent's."""
    return Path(project.default_log())


def _resolve_session(log_path: Path, session: str | None) -> str | None:
    """None stays None (the latest session); an id or a unique prefix of one becomes the exact id."""
    return session if session is None else sessions.resolve(log_path, session)


def _no_log_message() -> str:
    return ("no rewindagents log in this project yet: run the hook at least once (`rewindagents init`, "
            "then let the agent make a call) before using this tool")


def _require_log(log_path: Path) -> str | None:
    """None when the log is there to read; otherwise the message to answer with."""
    return None if log_path.exists() else _no_log_message()


def _want_int(args: dict, key: str, required: bool = True) -> tuple[int | None, str | None]:
    """(value, None) when args[key] is an int (never a bool, which is also an int in Python) and is
    there or optional-and-absent; otherwise (None, the message to answer with)."""
    v = args.get(key)
    if v is None:
        if required:
            return None, f"needs an integer '{key}'"
        return None, None
    if not isinstance(v, int) or isinstance(v, bool):
        return None, f"'{key}' must be an integer, not {v!r}"
    return v, None


def _confirmed(args: dict) -> bool:
    """True only for the JSON boolean `true` -- never a string, a number, or a missing key."""
    return args.get("confirm") is True


def _reveal_secrets(args: dict) -> bool:
    """True only for the JSON boolean `true` -- the explicit, documented opt-in to raw, unredacted
    diff text on `rewind_diff` (see TOOLS and `_tool_rewind_diff`). Unlike `confirm`, declining this
    opt-in is never wrong, so anything else -- missing, `false`, a string, a number -- just means
    "redact", never an error: there is nothing to ask the caller to fix."""
    return args.get("reveal_secrets") is True


def _tool_rewind_sessions(args: dict, log_path: Path) -> dict:
    missing = _require_log(log_path)
    if missing:
        return _err(missing)
    return _ok(json.dumps(jsonout.sessions_payload(log_path), ensure_ascii=False))


def _tool_rewind_summary(args: dict, log_path: Path) -> dict:
    missing = _require_log(log_path)
    if missing:
        return _err(missing)
    try:
        session = _resolve_session(log_path, args.get("session"))
        payload = jsonout.summary_payload(log_path, session)
    except (sessions.SessionError, rewind.RewindError) as e:
        return _err(str(e))
    return _ok(json.dumps(payload, ensure_ascii=False))


def _tool_rewind_diff(args: dict, log_path: Path) -> dict:
    missing = _require_log(log_path)
    if missing:
        return _err(missing)
    step, why = _want_int(args, "step")
    if why:
        return _err(f"rewind_diff {why}")
    try:
        session = _resolve_session(log_path, args.get("session"))
        # redacted by default -- unlike the plain `diff` command, whose unredacted default this
        # argument never passes to jsonout.diff_payload (see its docstring); reveal_secrets:true is
        # the explicit, documented opt-in back to raw text, same shape otherwise either way.
        payload, _ = jsonout.diff_payload(log_path, step, session, redact_secrets=not _reveal_secrets(args))
    except (sessions.SessionError, rewind.RewindError) as e:
        return _err(str(e))
    return _ok(json.dumps(payload, ensure_ascii=False))


def _tool_rewind_replay(args: dict, log_path: Path) -> dict:
    missing = _require_log(log_path)
    if missing:
        return _err(missing)
    from_seq, why = _want_int(args, "from_seq", required=False)
    if why:
        return _err(f"rewind_replay {why}")
    to_seq, why = _want_int(args, "to_seq", required=False)
    if why:
        return _err(f"rewind_replay {why}")
    try:
        session = _resolve_session(log_path, args.get("session"))
        # always redacted: this tool has no --no-redact equivalent, so there is no way to ask for raw
        # secrets through it, by design (see the module and jsonout.replay_payload docstrings)
        payload = jsonout.replay_payload(log_path, session, from_seq=from_seq, to_seq=to_seq, redact_secrets=True)
    except (sessions.SessionError, rewind.RewindError) as e:
        return _err(str(e))
    return _ok(json.dumps(payload, ensure_ascii=False))


def _tool_rewind_preview(args: dict, log_path: Path) -> dict:
    missing = _require_log(log_path)
    if missing:
        return _err(missing)
    to_step, why = _want_int(args, "to_step")
    if why:
        return _err(f"rewind_preview {why}")
    try:
        session = _resolve_session(log_path, args.get("session"))
        p = rewind.rewind(log_path, to_step, session, dry_run=True)
    except (sessions.SessionError, rewind.RewindError) as e:
        return _err(str(e))
    root = rewind.project_root(log_path)
    return _ok(json.dumps(jsonout.rewind_plan_payload(p, root), ensure_ascii=False))


def _tool_rewind_to_step(args: dict, log_path: Path) -> dict:
    missing = _require_log(log_path)
    if missing:
        return _err(missing)
    to_step, why = _want_int(args, "to_step")
    if why:
        return _err(f"rewind_to_step {why}")
    if not _confirmed(args):
        return _err(f"rewind_to_step requires confirmation: ask the user before putting this project's files "
                    f"back to step {to_step}, then call again with confirm set to true")
    try:
        session = _resolve_session(log_path, args.get("session"))
        p = rewind.rewind(log_path, to_step, session, dry_run=False)
    except (sessions.SessionError, rewind.RewindError) as e:
        # DriftError is a RewindError: its own message (which files, by whom) reaches the caller as it
        # is, verbatim -- this handler adds nothing and does not retry with force=True on its own.
        return _err(str(e))
    root = rewind.project_root(log_path)
    payload = jsonout.rewind_plan_payload(p, root)
    payload["record"] = p.get("record")
    return _ok(json.dumps(payload, ensure_ascii=False))


def _tool_rewind_revert_step(args: dict, log_path: Path) -> dict:
    missing = _require_log(log_path)
    if missing:
        return _err(missing)
    step, why = _want_int(args, "step")
    if why:
        return _err(f"rewind_revert_step {why}")
    if not _confirmed(args):
        return _err(f"rewind_revert_step requires confirmation: ask the user before reverting step {step}, "
                    f"then call again with confirm set to true")
    try:
        session = _resolve_session(log_path, args.get("session"))
        p = reverts.revert(log_path, step, session, dry_run=False)
    except (sessions.SessionError, reverts.ConflictError, rewind.RewindError) as e:
        # ConflictError is a RewindError too: its own message (which files, why) reaches the caller as
        # it is, verbatim -- this handler adds nothing and does not retry on its own.
        return _err(str(e))
    root = rewind.project_root(log_path)
    return _ok(json.dumps(jsonout.revert_result_payload(p, root), ensure_ascii=False))


_HANDLERS: dict[str, Callable[[dict, Path], dict]] = {
    "rewind_sessions": _tool_rewind_sessions,
    "rewind_summary": _tool_rewind_summary,
    "rewind_diff": _tool_rewind_diff,
    "rewind_replay": _tool_rewind_replay,
    "rewind_preview": _tool_rewind_preview,
    "rewind_to_step": _tool_rewind_to_step,
    "rewind_revert_step": _tool_rewind_revert_step,
}

_NO_ARGS = {"type": "object", "properties": {}, "additionalProperties": False}

TOOLS: list[dict] = [
    {"name": "rewind_sessions",
     "description": "List every session recorded for this project: its id, step count, and first and last "
                     "timestamp.",
     "inputSchema": _NO_ARGS, "annotations": {"readOnlyHint": True}},
    {"name": "rewind_summary",
     "description": "List a session's steps in order: each one's time, actor, tool and the files it touched.",
     "inputSchema": {"type": "object", "properties": {"session": {"type": "string"}},
                      "additionalProperties": False},
     "annotations": {"readOnlyHint": True}},
    {"name": "rewind_diff",
     "description": "Show what rewinding to a step would change, as a unified diff per file (now -> that step). "
                     "Secrets in the diff text are replaced with [redacted ...] by default; set "
                     "reveal_secrets:true for the raw text (dangerous -- only for your own eyes, never pass it "
                     "on unchanged).",
     "inputSchema": {"type": "object",
                      "properties": {"step": {"type": "integer", "description": "step number from rewind_summary "
                                                                                "or rewind_replay (0 = before "
                                                                                "the first step)"},
                                     "session": {"type": "string"},
                                     "reveal_secrets": {"type": "boolean", "description": "must be true to get "
                                                                                          "the raw, unredacted "
                                                                                          "diff text; default "
                                                                                          "false (redacted)"}},
                      "required": ["step"], "additionalProperties": False},
     "annotations": {"readOnlyHint": True}},
    {"name": "rewind_replay",
     "description": "List a session's steps with each one's result, optionally only those between two "
                     "sequence numbers from rewind_summary.",
     "inputSchema": {"type": "object",
                      "properties": {"from_seq": {"type": "integer"}, "to_seq": {"type": "integer"},
                                     "session": {"type": "string"}},
                      "additionalProperties": False},
     "annotations": {"readOnlyHint": True}},
    {"name": "rewind_preview",
     "description": "Show what rewinding to a step would restore, delete and overwrite, without changing "
                     "anything: a dry run.",
     "inputSchema": {"type": "object",
                      "properties": {"to_step": {"type": "integer", "description": "step number from "
                                                                                    "rewind_summary or "
                                                                                    "rewind_replay (0 = before "
                                                                                    "the first step)"},
                                     "session": {"type": "string"}},
                      "required": ["to_step"], "additionalProperties": False},
     "annotations": {"readOnlyHint": True}},
    {"name": "rewind_to_step",
     "description": "Put this project's files back the way they were right after a step. Destructive: needs "
                     "confirm:true, and refuses (telling you why) when a file changed outside the steps this "
                     "would take back. Preview it first with rewind_preview.",
     "inputSchema": {"type": "object",
                      "properties": {"to_step": {"type": "integer"}, "session": {"type": "string"},
                                     "confirm": {"type": "boolean", "description": "must be true; ask the user "
                                                                                   "first"}},
                      "required": ["to_step", "confirm"], "additionalProperties": False},
     "annotations": {"destructiveHint": True}},
    {"name": "rewind_revert_step",
     "description": "Take back one step alone and keep every later step and hand edit. Destructive: needs "
                     "confirm:true, and refuses (telling you why) on a conflict with a later change to the "
                     "same lines.",
     "inputSchema": {"type": "object",
                      "properties": {"step": {"type": "integer"}, "session": {"type": "string"},
                                     "confirm": {"type": "boolean", "description": "must be true; ask the user "
                                                                                   "first"}},
                      "required": ["step", "confirm"], "additionalProperties": False},
     "annotations": {"destructiveHint": True}},
]


class _MethodNotFound(Exception):
    def __init__(self, method: Any):
        super().__init__(method)
        self.method = method


def _handle_initialize(params: dict) -> dict:
    requested = params.get("protocolVersion")
    version = requested if requested in KNOWN_PROTOCOL_VERSIONS else PROTOCOL_VERSION
    return {"protocolVersion": version, "capabilities": {"tools": {}},
            "serverInfo": {"name": "rewindagents", "version": __version__}}


def _handle_tools_call(params: dict) -> dict:
    name = params.get("name")
    args = params.get("arguments")
    if not isinstance(args, dict):
        args = {}
    handler = _HANDLERS.get(name)
    if handler is None:
        return _err(f"no such tool: {name!r}; tools/list names the {len(_HANDLERS)} this server has")
    return handler(args, _log_path())


def _dispatch(method: str, params: Any) -> Any:
    params = params if isinstance(params, dict) else {}
    if method == "initialize":
        return _handle_initialize(params)
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        return _handle_tools_call(params)
    raise _MethodNotFound(method)


def _response(id_: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def _error(id_: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


def _handle_message(msg: Any) -> dict | None:
    """One JSON-RPC message in, one response out -- or None for a notification, which gets no reply."""
    if not isinstance(msg, dict):
        return _error(None, -32600, "invalid request: not a JSON object")
    has_id = "id" in msg
    id_ = msg.get("id")
    method = msg.get("method")
    if not isinstance(method, str) or not method:
        return _error(id_, -32600, "invalid request: missing 'method'") if has_id else None
    if method.startswith("notifications/"):
        return None             # fire-and-forget, whether or not this server knows the name
    try:
        result = _dispatch(method, msg.get("params"))
    except _MethodNotFound:
        return _error(id_, -32601, f"method not found: {method}") if has_id else None
    return _response(id_, result) if has_id else None


def _write(stream, obj: dict) -> None:
    stream.write(json.dumps(obj, ensure_ascii=False) + "\n")
    stream.flush()


def serve(stdin=None, stdout=None) -> int:
    """Read one JSON-RPC message per line from stdin, write one per line to stdout, until stdin ends."""
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    for raw in stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            _write(stdout, _error(None, -32700, "parse error: not valid JSON"))
            continue
        try:
            response = _handle_message(msg)
        except Exception as e:  # one bad call must not end the session for every call after it (see module docstring)
            if isinstance(msg, dict) and "id" in msg:
                _write(stdout, _error(msg.get("id"), -32603, f"internal error: {e}"))
            else:
                print(f"rewindagents mcp: internal error on a notification: {e}", file=sys.stderr)
            continue
        if response is not None:
            _write(stdout, response)
    return 0
