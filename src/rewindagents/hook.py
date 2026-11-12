"""Pre / post tool-use hook for Claude Code, Codex, Cursor, Gemini CLI, Copilot CLI, Droid and Qwen Code: record
every call, checkpoint files first.

The agent runs the hook with one JSON object on stdin (field names per agent: agents.py). The hook:
- appends a "pre" record (tool + input) before the call and a "post" record (tool + response) after it;
- Claude Code: before Write, Edit, MultiEdit and NotebookEdit, copies the current bytes of the target file
  into a content-addressed store (.rewindagents/objects/<sha256>) and puts the hash in the "pre" record, so
  the file can be put back later. A file that does not exist yet is recorded as absent;
- around Bash (Claude Code) and around every call of the other agents that is not known to be read-only,
  saves the project's files before the call and checkpoints, in the "post" record, the ones it changed,
  created or deleted (see bashscan.py).

It never blocks, never decides and never changes the call: it always exits 0, even when its own input is
broken or the disk is full, and prints nothing to stdout except the answer an agent's docs require (Cursor's
permission hook: `{"permission": "allow"}`; Gemini CLI, which parses stdout as JSON: `{}`). Problems go to
stderr only.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shlex
import site
import sys
import time
from pathlib import Path
from typing import Any

from . import agents, filelock
from .log import Recorder

FILE_TOOLS = {"Write": "file_path", "Edit": "file_path", "MultiEdit": "file_path",
              "NotebookEdit": "notebook_path"}
MAX_CHECKPOINT_BYTES = 20 * 1024 * 1024
MAX_RESULT_CHARS = 4000


def store_dir(cwd: str | Path) -> Path:
    return Path(cwd) / ".rewindagents"


@contextlib.contextmanager
def store_lock(store: Path, exclusive: bool = False, timeout: float = 30.0):
    """Lock on .rewindagents/lock. Everything that saves a stored copy and then writes the record naming it
    (the hook, rewind, branch, import) holds it shared from the copy to the record; `gc` holds it exclusive,
    so it never sees a copy whose record is not written yet. Several shared holders run at once.

    Shared: if the lock file cannot be opened or locked, carry on unlocked (recording matters more).
    Exclusive: wait up to `timeout` seconds, then raise TimeoutError."""
    try:
        store.mkdir(parents=True, exist_ok=True)
        fh = (store / "lock").open("a+")
    except OSError:
        if exclusive:
            raise
        yield
        return
    locked = False
    try:
        if exclusive:
            deadline = time.monotonic() + timeout
            while True:
                try:
                    filelock.acquire(fh, exclusive=True, blocking=False)
                    locked = True
                    break
                except BlockingIOError:
                    if time.monotonic() > deadline:
                        raise TimeoutError(f"the store was still in use after {timeout:g} s")
                    time.sleep(0.05)
        else:
            try:
                filelock.acquire(fh, exclusive=False)
                locked = True
            except OSError:
                pass
        yield
    finally:
        if locked:
            with contextlib.suppress(OSError):
                filelock.release(fh)   # Windows wants an explicit unlock before close
        fh.close()


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


def handle(payload: dict, agent: str = agents.DEFAULT) -> dict:
    """Record one hook event from `agent` (a key of agents.AGENTS). Returns the record written."""
    ag = agents.AGENTS[agent]
    n = agents.normalize(payload)
    store = store_dir(n["cwd"])
    rec = Recorder(store / "log.jsonl")
    ignore = store / ".gitignore"
    if not ignore.exists():  # keep the log and checkpoints out of the user's commits
        ignore.write_text("*\n", encoding="utf-8")
    with store_lock(store):  # from the stored copy to the record that names it: see store_lock
        return _handle(payload, ag, agent, n, store, rec)


def _handle(payload: dict, ag, agent: str, n: dict, store: Path, rec: Recorder) -> dict:
    cwd, event, tool, tool_input, session = n["cwd"], n["event"], n["tool"], n["input"], n["session"]
    if event == "pre":
        args: dict[str, Any] = {"input": tool_input, "agent": agent}
        key = FILE_TOOLS.get(tool) if ag.file_tools else None
        if key and isinstance(tool_input, dict) and tool_input.get(key):
            target = Path(tool_input[key])
            if not target.is_absolute():
                target = cwd / target
            args["checkpoint"] = checkpoint(target, store / "objects")
        elif agents.scans(ag, tool):
            from . import bashscan
            args["bash_scan"] = bashscan.before(payload, cwd, store)
        return rec.record(session, tool, args, None, event="pre")
    if event == "post":
        args = {"input": tool_input, "agent": agent}
        if agents.scans(ag, tool):
            from . import bashscan
            args["bash_scan"], args["checkpoints"] = bashscan.after(payload, cwd, store)
        return rec.record(session, tool, args, _clip(n["response"]), event="post")
    return rec.record(session, tool, {"input": tool_input, "agent": agent}, None, event=event)


def run(stdin=None, agent: str = agents.DEFAULT) -> int:
    """Hook entry point. Always returns 0. Writes nothing to stdout, except the agent's required reply
    (Cursor: `{"permission": "allow"}` before a call, `{}` after one; the same allow if the input could not
    be read, so a broken payload still never turns into a block. Gemini CLI: `{}` always)."""
    event = "unknown"
    try:
        payload = json.load(stdin or sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook input is not a JSON object")
        event = agents.normalize(payload)["event"]
        handle(payload, agent)
    except Exception as e:  # never let a recording failure reach the agent as a block
        print(f"rewindagents hook: not recorded: {e}", file=sys.stderr)
    reply = agents.AGENTS[agent].reply.get(event, agents.AGENTS[agent].reply.get("unknown", ""))
    if reply:
        print(reply)
    return 0


def installed() -> bool:
    """True when this copy of the package lives in a site-packages directory of this interpreter
    (pip, pipx, a venv): then `python -m rewindagents` works without PYTHONPATH and the `rewindagents`
    command exists. False when running from a clone with PYTHONPATH=src.

    Not a metadata lookup: `pip install .` leaves `src/rewindagents.egg-info` behind in the clone, which
    makes importlib.metadata report the clone as installed when src is on sys.path.
    """
    here = Path(__file__).resolve()
    dirs = list(site.getsitepackages()) if hasattr(site, "getsitepackages") else []
    if hasattr(site, "getusersitepackages"):
        dirs.append(site.getusersitepackages())
    return any(here.is_relative_to(Path(d).resolve()) for d in dirs if d)


def hook_command(agent: str = agents.DEFAULT) -> str:
    """The command the agent will run for every hook event.

    It names the interpreter by absolute path, so it works whether or not a virtualenv is active.
    From a clone (not installed) it carries the PYTHONPATH that makes the package importable.
    For every agent but Claude Code it carries `--agent`, so the hook reads their payload and answers their way.
    For an agent where a non-zero exit counts as a deny (agents.Agent.fail_closed: Copilot CLI's preToolUse) it
    ends in `|| true`, so not even a missing interpreter can turn into a block.
    """
    run = f"{shlex.quote(sys.executable)} -m rewindagents hook"
    if agent != agents.DEFAULT:
        run += f" --agent {agent}"
    if not installed():
        src = Path(__file__).resolve().parent.parent
        run = f"PYTHONPATH={shlex.quote(str(src))} {run}"
    return run + " || true" if agents.AGENTS[agent].fail_closed else run


def install(settings_path: str | Path | None = None, command: str | None = None,
            agent: str = agents.DEFAULT) -> bool:
    """Add the hook to the agent's config file (default: the agent's project file, agents.AGENTS[agent].settings).
    Keeps everything already there. Returns True if the file changed, False if the hook was already installed.
    """
    ag = agents.AGENTS[agent]
    return agents.install(ag, settings_path or agents.config_path(ag), command or hook_command(agent))


def uninstall(settings_path: str | Path | None = None, command: str | None = None,
              agent: str = agents.DEFAULT) -> bool:
    """Remove the hook `install` would write from the agent's config file; every other entry stays.
    Never touches .rewindagents/, so recorded sessions can still be replayed and rewound.
    Returns True if the file changed, False if there was nothing of ours in it.
    """
    ag = agents.AGENTS[agent]
    return agents.uninstall(ag, settings_path or agents.config_path(ag), command or hook_command(agent))
