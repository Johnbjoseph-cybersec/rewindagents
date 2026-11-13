"""Pre / post tool-use hook for Claude Code, Codex, Cursor, Gemini CLI, Copilot CLI, Droid and Qwen Code: record
every call, checkpoint files first.

The agent runs the hook with one JSON object on stdin (field names per agent: agents.py). The hook:
- appends a "pre" record (tool + input) before the call and a "post" record (tool + response) after it;
- Claude Code: before Write, Edit, MultiEdit and NotebookEdit, copies the current bytes of the target file
  into a content-addressed store (.rewindagents/objects/<sha256>) and puts the hash in the "pre" record, so
  the file can be put back later. A file that does not exist yet is recorded as absent;
- around Bash (Claude Code) and around every call of the other agents that is not known to be read-only,
  saves the project's files before the call and checkpoints, in the "post" record, the ones it changed,
  created or deleted (see bashscan.py);
- in the "post" record, the SHA-256 of each file the call wrote or changed as it is right after the call
  (args["after"]), so a later rewind can tell when a file changed outside any recorded step.

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
import re
import shlex
import site
import sys
import threading
import time
from pathlib import Path
from typing import Any

from . import agents, filelock, ospaths, project
from .log import Recorder

FILE_TOOLS = {"Write": "file_path", "Edit": "file_path", "MultiEdit": "file_path",
              "NotebookEdit": "notebook_path"}
MAX_CHECKPOINT_BYTES = 20 * 1024 * 1024
MAX_RESULT_CHARS = 4000
MAX_INPUT_CHARS = 4000
# Input fields kept whole however long: what replay shows, rewind restores and the checkpoint reads.
KEEP_WHOLE = frozenset({"file_path", "notebook_path", "path", "command", "working_directory", "cwd"})


def store_dir(cwd: str | Path) -> Path:
    return Path(cwd) / ".rewindagents"


# Store locks this process holds: lock path -> [holders, open file]. A shared request for a lock the process
# already holds joins that hold instead of opening a second handle: on Windows (no shared lock in msvcrt) a
# second handle would wait for the first forever (CI run 43437432241). The OS lock goes when the last leaves.
_HELD: dict[str, list] = {}
_HELD_GUARD = threading.Lock()


@contextlib.contextmanager
def store_lock(store: Path, exclusive: bool = False, timeout: float = 30.0):
    """Lock on .rewindagents/lock. Everything that saves a stored copy and then writes the record naming it
    (the hook, rewind, branch, import) holds it shared from the copy to the record; `gc` holds it exclusive,
    so it never sees a copy whose record is not written yet. Several shared holders run at once.

    Shared: if the lock file cannot be opened or locked, carry on unlocked (recording matters more). Inside a
    hold of the same store in this process, a shared request joins that hold.
    Exclusive: wait up to `timeout` seconds, then raise TimeoutError. It never joins: inside a hold of its own
    process it times out, as it would against another process."""
    key = os.path.abspath(store / "lock")
    fh = None
    if exclusive or not _join(key):
        try:
            store.mkdir(parents=True, exist_ok=True)
            fh = (store / "lock").open("a+")
        except OSError:
            if exclusive:
                raise
            yield
            return
    if fh is not None:
        locked = joined = False
        try:
            deadline = time.monotonic() + timeout
            while True:
                if not exclusive and _join(key):   # another thread of this process took it meanwhile: share it
                    joined = True
                    break
                try:
                    filelock.acquire(fh, exclusive=exclusive, blocking=False)
                    locked = True
                    break
                except BlockingIOError:
                    if exclusive and time.monotonic() > deadline:
                        raise TimeoutError(f"the store was still in use after {timeout:g} s")
                    time.sleep(0.05)
                except OSError:
                    if exclusive:
                        raise
                    break                          # shared: carry on unlocked
        except BaseException:
            fh.close()
            raise
        if locked:
            with _HELD_GUARD:
                held = _HELD.get(key)
                if held:                           # a thread here locked it at the same moment: share that one
                    held[0] += 1
                else:
                    _HELD[key] = [1, fh]
            if held:
                with contextlib.suppress(OSError):
                    filelock.release(fh)
                fh.close()
        else:
            fh.close()
            if not joined:                         # shared and unlocked: carry on, as before
                yield
                return
    try:
        yield
    finally:
        _leave(key)


def _join(key: str) -> bool:
    """Join this process's hold of the store lock at `key`, if there is one."""
    with _HELD_GUARD:
        held = _HELD.get(key)
        if held:
            held[0] += 1
        return bool(held)


def _leave(key: str) -> None:
    """One holder of a store lock this process holds is done; the last one unlocks and closes the file."""
    with _HELD_GUARD:
        held = _HELD[key]
        held[0] -= 1
        if held[0]:
            return
        del _HELD[key]
    fh = held[1]
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


def after_hash(path: Path) -> dict:
    """What a file holds right after a step, as a hash only (no copy is stored): {"path", "after": sha256 or
    None when the file is absent}, or {"path", "skipped": why} when it is too big to hash here. rewind compares
    it with the file's bytes later, to tell a change made outside the log (by hand, by another tool) from
    the step's own. The key is "after", not "sha256", so bundle and gc never look for a stored copy of it."""
    entry: dict[str, Any] = {"path": str(path)}
    if not path.is_file():
        entry["after"] = None
        return entry
    if path.stat().st_size > MAX_CHECKPOINT_BYTES:
        entry["skipped"] = f"larger than {MAX_CHECKPOINT_BYTES} bytes"
        return entry
    entry["after"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return entry


def _clip(value: Any) -> Any:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= MAX_RESULT_CHARS:
        return value
    return {"truncated": True, "chars": len(text), "head": text[:MAX_RESULT_CHARS]}


def clip_input(value: Any, top: bool = True) -> Any:
    """The tool input as recorded: every string longer than MAX_INPUT_CHARS (a Write's content, an Edit's
    new_string) becomes {"truncated": True, "chars": <length>, "head": <first MAX_INPUT_CHARS>}; every key
    stays, and the top-level fields in KEEP_WHOLE stay whole. The file's bytes are in the stored copy, not
    here. Pre and post records clip the same way, so they still pair (rewind.steps_from compares inputs)."""
    if isinstance(value, str):
        if len(value) <= MAX_INPUT_CHARS:
            return value
        return {"truncated": True, "chars": len(value), "head": value[:MAX_INPUT_CHARS]}
    if isinstance(value, list):
        return [clip_input(v, False) for v in value]
    if isinstance(value, dict):
        return {k: v if top and k in KEEP_WHOLE else clip_input(v, False) for k, v in value.items()}
    return value


def handle(payload: dict, agent: str = agents.DEFAULT) -> dict:
    """Record one hook event from `agent` (a key of agents.AGENTS). Returns the record written."""
    ag = agents.AGENTS[agent]
    n = agents.normalize(payload)
    if not n["cwd"].is_dir():  # never create a project directory the agent named but that is not there
        raise FileNotFoundError(f"cwd is not a directory: {n['cwd']}")
    # After `cd sub` the agent's cwd is sub; the session still belongs to the project's one log (project.py).
    root = project.root_for(n["cwd"])
    store = store_dir(root)
    rec = Recorder(store / "log.jsonl")
    ignore = store / ".gitignore"
    if not ignore.exists():  # keep the log and checkpoints out of the user's commits
        ignore.write_text("*\n", encoding="utf-8")
    with store_lock(store):  # from the stored copy to the record that names it: see store_lock
        return _handle(payload, ag, agent, n, store, rec, root)


def _handle(payload: dict, ag, agent: str, n: dict, store: Path, rec: Recorder, root: Path | None = None) -> dict:
    cwd, event, tool, tool_input, session = n["cwd"], n["event"], n["tool"], n["input"], n["session"]
    root = root or cwd   # the project: scanned around a command. cwd: where a relative file path starts
    recorded = clip_input(tool_input)   # the checkpoint and the scan key read the whole input, not this
    if event == "pre":
        args: dict[str, Any] = {"input": recorded, "agent": agent}
        key = FILE_TOOLS.get(tool) if ag.file_tools else None
        if key and isinstance(tool_input, dict) and tool_input.get(key):
            target = Path(tool_input[key])
            if not target.is_absolute():
                target = cwd / target
            args["checkpoint"] = checkpoint(target, store / "objects")
        elif agents.scans(ag, tool):
            from . import bashscan
            args["bash_scan"] = bashscan.before(payload, root, store)
        return rec.record(session, tool, args, None, event="pre")
    if event == "post":
        args = {"input": recorded, "agent": agent}
        key = FILE_TOOLS.get(tool) if ag.file_tools else None
        if key and isinstance(tool_input, dict) and tool_input.get(key):
            target = Path(tool_input[key])
            if not target.is_absolute():
                target = cwd / target
            args["after"] = [after_hash(target)]
        elif agents.scans(ag, tool):
            from . import bashscan
            afters: list[dict] = []
            args["bash_scan"], args["checkpoints"] = bashscan.after(payload, root, store, afters)
            args["after"] = afters
        return rec.record(session, tool, args, _clip(n["response"]), event="post")
    return rec.record(session, tool, {"input": recorded, "agent": agent}, None, event=event)


def _read(stdin=None) -> str:
    """The hook input as text. Bytes that are not UTF-8 become U+FFFD, so a command line holding them is still
    recorded (with that mark in their place) rather than lost."""
    stream = stdin or sys.stdin
    data = getattr(stream, "buffer", stream).read()
    return data.decode("utf-8", "replace") if isinstance(data, bytes) else data


def _clean(value: Any) -> Any:
    """Replace lone surrogates (valid JSON escapes such as \\udc80, but not encodable as UTF-8) with U+FFFD, so
    the record can be hashed and written. Walks the value only when it holds one."""
    try:
        json.dumps(value, ensure_ascii=False).encode("utf-8")
        return value
    except UnicodeEncodeError:
        pass

    def fix(v: Any) -> Any:
        if isinstance(v, str):
            return v.encode("utf-16", "surrogatepass").decode("utf-16", "replace")
        if isinstance(v, list):
            return [fix(x) for x in v]
        if isinstance(v, dict):
            return {fix(k): fix(x) for k, x in v.items()}
        return v
    return fix(value)


def run(stdin=None, agent: str = agents.DEFAULT) -> int:
    """Hook entry point. Always returns 0. Writes nothing to stdout, except the agent's required reply
    (Cursor: `{"permission": "allow"}` before a call, `{}` after one; the same allow if the input could not
    be read, so a broken payload still never turns into a block. Gemini CLI: `{}` always)."""
    event = "unknown"
    try:
        payload = _clean(json.loads(_read(stdin)))
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


class EphemeralPython(ValueError):
    """install was run from a throwaway environment (uvx, pipx run) that its tool may delete."""


def ephemeral(prefix: str | Path | None = None, env: dict | None = None,
              home: str | Path | None = None) -> str | None:
    """'uvx' or 'pipx run' when this interpreter's environment lives in that tool's cache, else None.

    A hook command names the interpreter by absolute path; from a cached environment that path can vanish.
    uv keeps `uvx` (`uv tool run`) environments in its cache and treats them as disposable; `uv tool install`
    puts them in the tools directory instead (docs.astral.sh/uv/concepts/tools, read 2026-11-13). Cache dir:
    --cache-dir / UV_CACHE_DIR, else $XDG_CACHE_HOME/uv, $HOME/.cache/uv, %LOCALAPPDATA%\\uv\\cache
    (docs.astral.sh/uv/concepts/cache and /reference/storage, read 2026-11-13). `pipx run` caches its
    environments in PIPX_HOME/.cache when PIPX_HOME is set, else platformdirs' user cache dir for "pipx";
    `pipx install` puts them under PIPX_HOME/venvs (github.com/pypa/pipx src/pipx/paths.py, read 2026-11-13).
    A --cache-dir passed on uv's command line is not visible here.
    """
    env = os.environ if env is None else env
    home = Path(home or Path.home())
    here = Path(prefix or sys.prefix).resolve()
    xdg = env.get("XDG_CACHE_HOME")
    local = env.get("LOCALAPPDATA")
    roots = {
        "uvx": [env.get("UV_CACHE_DIR"), xdg and Path(xdg) / "uv", home / ".cache" / "uv",
                local and Path(local) / "uv" / "cache"],
        "pipx run": [env.get("PIPX_HOME") and Path(env["PIPX_HOME"]) / ".cache",
                     home / ".local" / "pipx" / ".cache", home / "pipx" / ".cache",
                     xdg and Path(xdg) / "pipx", home / ".cache" / "pipx", home / "Library" / "Caches" / "pipx",
                     local and Path(local) / "pipx" / "Cache"],
    }
    for kind, dirs in roots.items():
        for d in dirs:
            if d and here.is_relative_to(Path(d).resolve()):
                return kind
    return None


def ephemeral_message(kind: str) -> str:
    return (f"this Python is a {kind} environment in a cache that may be deleted, which would leave a hook "
            f"that cannot run ({sys.prefix}). Install it for good, then run install again: "
            f"`uv tool install rewindagents` or `pipx install rewindagents`")


def source_dir() -> Path | None:
    """The clone's src/ directory when this package runs from a clone (not installed), else None."""
    return None if installed() else Path(__file__).resolve().parent.parent


def hook_command(agent: str = agents.DEFAULT, python: str | None = None) -> str:
    """The command the agent will run for every hook event.

    It names the interpreter (`python`, default this one) by absolute path, so it works whether or not a
    virtualenv is active. For every agent but Claude Code it carries `--agent`, so the hook reads their payload
    and answers their way. For an agent where a non-zero exit counts as a deny (agents.Agent.fail_closed:
    Copilot CLI's preToolUse) it ends in a guard, so not even a missing interpreter can turn into a block.

    POSIX form (`/usr/bin/python3`): `'<python>' -m rewindagents hook [--agent X] [|| true]`; from a clone it
    carries the `PYTHONPATH=<src>` prefix that makes the package importable.

    Windows form, chosen by the interpreter path's own shape (`C:\\...`, `C:/...`; the OS running this does not
    decide): forward slashes; a path with nothing but letters, digits, `_ . / + -` is written bare, which Git
    Bash, PowerShell and cmd.exe all run; any other path is double-quoted and, for an agent whose docs say it
    runs hooks in PowerShell (agents.Agent.win_shell), preceded by `&`, since PowerShell prints a quoted string
    that stands alone. No env-var prefix (bash-only syntax): from a clone the package is run by file path,
    `<python> <src>/rewindagents/__main__.py hook ...`, which __main__.py supports. The fail-closed guard is
    `; exit 0` under PowerShell (`|| true` is bash). Sources per agent: agents.py, read 2026-11-14.
    """
    python = python or sys.executable
    ag = agents.AGENTS[agent]
    tail = f" --agent {agent}" if agent != agents.DEFAULT else ""
    src = source_dir()
    if agents.windows_command(python):
        return _windows_command(ag, python, src, tail)
    run = f"{shlex.quote(python)} -m rewindagents hook{tail}"
    if src is not None:
        run = f"PYTHONPATH={shlex.quote(str(src))} {run}"
    return run + " || true" if ag.fail_closed else run


_PLAIN_WIN = re.compile(r"^[A-Za-z]:/[A-Za-z0-9_./+-]*$")


def _win_word(path: str | Path) -> str:
    """A Windows path as one command word: forward slashes, bare when every shell reads it as one word, else
    double-quoted (Git Bash and cmd.exe; PowerShell needs `&` in front, which the caller adds)."""
    p = str(path).replace("\\", "/")
    return p if _PLAIN_WIN.match(p) else f'"{p}"'


def _windows_command(ag: agents.Agent, python: str, src: Path | None, tail: str) -> str:
    words = [_win_word(python)]
    if src is None:
        words += ["-m", "rewindagents"]
    else:
        words.append(_win_word(f"{str(src).replace(chr(92), '/')}/rewindagents/__main__.py"))
    cmd = " ".join(words) + " hook" + tail
    if ag.win_shell == "powershell" and words[0].startswith('"'):
        cmd = "& " + cmd
    if ag.fail_closed:
        cmd += "; exit 0" if ag.win_shell == "powershell" else " || true"
    return cmd


# `... -m rewindagents hook`, `rewindagents hook` (on PATH), or the clone-by-file form `.../rewindagents/__main__.py hook`
# (a quote may close the path first).
_OURS = re.compile(r"rewindagents(?:[/\\]__main__\.py)?\"?\s+hook\b")


def ours(command: str) -> bool:
    """True for a hook command that runs rewindagents' hook (any interpreter, any agent, either OS form)."""
    return bool(_OURS.search(command))


def words(command: str) -> list[str]:
    """The command's words with their quotes removed. POSIX rules, unless the command names a Windows path: then
    backslashes are kept (shlex's POSIX mode reads `C:\\Users` as `C:Users`), surrounding double quotes are
    stripped and a leading PowerShell `&` is dropped. Raises ValueError on an unbalanced quote, as shlex does."""
    if not agents.windows_command(command):
        return shlex.split(command)
    out = []
    for w in shlex.split(command, posix=False):
        if w == "&" and not out:
            continue
        out.append(w[1:-1] if len(w) >= 2 and w[0] == w[-1] == '"' else w)
    return out


def stale(command: str) -> str | None:
    """Why this hook command can no longer run, or None when nothing it names is missing.

    A hook names its interpreter by absolute path (and, from a clone, a PYTHONPATH directory or the package's
    __main__.py). When that venv is deleted, a uv/pipx cache is cleared or Python is upgraded, the agent still
    runs the command, it fails, and nothing is recorded, with no message the user sees. Only absolute paths are
    judged: a bare command name is looked up on PATH at run time and may well work.
    """
    try:
        ws = words(command)
    except ValueError:
        return None
    env = {}
    while ws and "=" in ws[0] and ws[0].split("=", 1)[0].isidentifier():
        k, v = ws.pop(0).split("=", 1)
        env[k] = v
    if ws and ospaths.isabs(ws[0]) and not Path(ws[0]).exists():
        return f"{ws[0]} no longer exists"
    if len(ws) > 1 and ws[1].lower().endswith("__main__.py") and ospaths.isabs(ws[1]) and not Path(ws[1]).exists():
        return f"{ws[1]} no longer exists"
    pp = env.get("PYTHONPATH")
    if pp and ospaths.isabs(pp) and not Path(pp).is_dir():
        return f"PYTHONPATH {pp} no longer exists"
    return None


def stale_hooks(settings_path: str | Path, agent: str = agents.DEFAULT) -> list[tuple[str, str]]:
    """(command, why) for each rewindagents hook in the config file that can no longer run."""
    p = Path(settings_path)
    if not p.is_file() or not p.read_text(encoding="utf-8").strip():
        return []
    have = agents.commands_in(agents.AGENTS[agent], p)
    seen = dict.fromkeys(c for cmds in have.values() for c in cmds if ours(c))
    return [(c, why) for c in seen if (why := stale(c))]


def replace_stale(settings_path: str | Path, agent: str = agents.DEFAULT) -> list[tuple[str, str]]:
    """Remove every rewindagents hook in the file that can no longer run (agents.uninstall: exact command
    match, every other hook and key stays). Returns what was removed; the caller installs the current one."""
    dead = stale_hooks(settings_path, agent)
    for cmd, _ in dead:
        agents.uninstall(agents.AGENTS[agent], settings_path, cmd)
    return dead


def install(settings_path: str | Path | None = None, command: str | None = None,
            agent: str = agents.DEFAULT) -> bool:
    """Add the hook to the agent's config file (default: the agent's project file, agents.AGENTS[agent].settings).
    Keeps everything already there. Returns True if the file changed, False if the hook was already installed.
    Raises EphemeralPython, writing nothing, when no command is given and this Python is a uvx / pipx run one.
    """
    ag = agents.AGENTS[agent]
    kind = None if command else ephemeral()
    if kind:
        raise EphemeralPython(ephemeral_message(kind))
    return agents.install(ag, settings_path or agents.config_path(ag), command or hook_command(agent))


def uninstall(settings_path: str | Path | None = None, command: str | None = None,
              agent: str = agents.DEFAULT) -> bool:
    """Remove the hook `install` would write from the agent's config file; every other entry stays.
    Never touches .rewindagents/, so recorded sessions can still be replayed and rewound.
    Returns True if the file changed, False if there was nothing of ours in it.
    """
    ag = agents.AGENTS[agent]
    return agents.uninstall(ag, settings_path or agents.config_path(ag), command or hook_command(agent))
