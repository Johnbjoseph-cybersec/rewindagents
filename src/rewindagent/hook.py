"""Claude Code PreToolUse / PostToolUse hook: record every call, checkpoint files first.

Claude Code runs the hook with one JSON object on stdin. The hook:
- appends a "pre" record (tool + input) before the call and a "post" record (tool + response) after it;
- before Write, Edit, MultiEdit and NotebookEdit, copies the current bytes of the target file into a
  content-addressed store (.rewindagent/objects/<sha256>) and puts the hash in the "pre" record, so the
  file can be put back later. A file that does not exist yet is recorded as absent;
- around Bash, saves the project's files before the command and checkpoints, in the "post" record,
  the ones it changed, created or deleted (see bashscan.py).

It never blocks, never decides and never changes the call: it prints nothing to stdout and always
exits 0, even when its own input is broken or the disk is full. Problems go to stderr only.
"""
from __future__ import annotations

import hashlib
import json
import os
import shlex
import site
import sys
from pathlib import Path
from typing import Any

from .log import Recorder

FILE_TOOLS = {"Write": "file_path", "Edit": "file_path", "MultiEdit": "file_path",
              "NotebookEdit": "notebook_path"}
MAX_CHECKPOINT_BYTES = 20 * 1024 * 1024
MAX_RESULT_CHARS = 4000


def store_dir(cwd: str | Path) -> Path:
    return Path(cwd) / ".rewindagent"


def checkpoint(path: Path, objects: Path) -> dict:
    """Copy the file's current bytes into the object store; return what was saved."""
    entry: dict[str, Any] = {"path": str(path)}
    if not path.is_file():
        entry["sha256"] = None
        return entry
    size = path.stat().st_size
    entry["size"] = size
    if size > MAX_CHECKPOINT_BYTES:
        entry["sha256"] = None
        entry["skipped"] = f"larger than {MAX_CHECKPOINT_BYTES} bytes"
        return entry
    data = path.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    objects.mkdir(parents=True, exist_ok=True)
    obj = objects / sha
    if not obj.exists():
        tmp = objects / f".{sha}.{os.getpid()}.tmp"
        tmp.write_bytes(data)
        os.replace(tmp, obj)
    entry["sha256"] = sha
    return entry


def _clip(value: Any) -> Any:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= MAX_RESULT_CHARS:
        return value
    return {"truncated": True, "chars": len(text), "head": text[:MAX_RESULT_CHARS]}


def handle(payload: dict) -> dict:
    """Record one hook event. Returns the record written."""
    cwd = Path(payload.get("cwd") or os.getcwd())
    event = payload.get("hook_event_name", "")
    tool = payload.get("tool_name", "?")
    tool_input = payload.get("tool_input") or {}
    session = payload.get("session_id", "unknown")
    store = store_dir(cwd)
    rec = Recorder(store / "log.jsonl")
    ignore = store / ".gitignore"
    if not ignore.exists():  # keep the log and checkpoints out of the user's commits
        ignore.write_text("*\n", encoding="utf-8")

    if event == "PreToolUse":
        args: dict[str, Any] = {"input": tool_input}
        key = FILE_TOOLS.get(tool)
        if key and isinstance(tool_input, dict) and tool_input.get(key):
            target = Path(tool_input[key])
            if not target.is_absolute():
                target = cwd / target
            args["checkpoint"] = checkpoint(target, store / "objects")
        elif tool == "Bash":
            from . import bashscan
            args["bash_scan"] = bashscan.before(payload, cwd, store)
        return rec.record(session, tool, args, None, event="pre")
    if event == "PostToolUse":
        args = {"input": tool_input}
        if tool == "Bash":
            from . import bashscan
            args["bash_scan"], args["checkpoints"] = bashscan.after(payload, cwd, store)
        return rec.record(session, tool, args, _clip(payload.get("tool_response")), event="post")
    return rec.record(session, tool, {"input": tool_input}, None, event=event or "unknown")


def run(stdin=None) -> int:
    """Hook entry point. Always returns 0 and writes nothing to stdout."""
    try:
        payload = json.load(stdin or sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook input is not a JSON object")
        handle(payload)
    except Exception as e:  # never let a recording failure reach the agent as a block
        print(f"rewindagent hook: not recorded: {e}", file=sys.stderr)
    return 0


def installed() -> bool:
    """True when this copy of the package lives in a site-packages directory of this interpreter
    (pip, pipx, a venv): then `python -m rewindagent` works without PYTHONPATH and the `rewindagent`
    command exists. False when running from a clone with PYTHONPATH=src.

    Not a metadata lookup: `pip install .` leaves `src/rewindagent.egg-info` behind in the clone, which
    makes importlib.metadata report the clone as installed when src is on sys.path.
    """
    here = Path(__file__).resolve()
    dirs = list(site.getsitepackages()) if hasattr(site, "getsitepackages") else []
    if hasattr(site, "getusersitepackages"):
        dirs.append(site.getusersitepackages())
    return any(here.is_relative_to(Path(d).resolve()) for d in dirs if d)


def hook_command() -> str:
    """The command Claude Code will run for every hook event.

    It names the interpreter by absolute path, so it works whether or not a virtualenv is active.
    From a clone (not installed) it carries the PYTHONPATH that makes the package importable.
    """
    run = f"{shlex.quote(sys.executable)} -m rewindagent hook"
    if installed():
        return run
    src = Path(__file__).resolve().parent.parent
    return f"PYTHONPATH={shlex.quote(str(src))} {run}"


def install(settings_path: str | Path, command: str | None = None) -> bool:
    """Add the hook to a Claude Code settings file. Keeps everything already there.

    Returns True if the file changed, False if the hook was already installed.
    """
    p = Path(settings_path)
    cmd = command or hook_command()
    text = p.read_text(encoding="utf-8") if p.exists() else ""
    settings = json.loads(text) if text.strip() else {}
    hooks = settings.setdefault("hooks", {})
    changed = False
    for event in ("PreToolUse", "PostToolUse"):
        groups = hooks.setdefault(event, [])
        present = any(h.get("command") == cmd for g in groups for h in g.get("hooks", []))
        if not present:
            groups.append({"matcher": "*", "hooks": [{"type": "command", "command": cmd}]})
            changed = True
    if changed:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".rewindagent.tmp")
        tmp.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, p)
    return changed
