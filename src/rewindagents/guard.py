"""Guarded files: the ones you never want an agent to touch (.env, secrets/, *.pem, a lockfile).

`rewindagents guard .env 'secrets/' '*.pem'` writes the patterns to .rewindagents/guard.json. After each tool
call, the hook checks the files that call changed against them. On a hit it does NOT block the call (the hook
never blocks): Claude Code gets a warning shown to you (`systemMessage`) and a note to the agent
(`additionalContext`); every other agent gets the warning on stderr, because their stdout reply is fixed by
their docs. `guard --check` lists every guarded file the session's still-live steps changed.

A pattern is a path relative to the project root. One ending in '/' covers a directory; one with * ? [ is a
glob, matched against the relative path and against the file name; anything else is an exact file, or a
directory when it names one."""
from __future__ import annotations

import json
import os
from fnmatch import fnmatch
from pathlib import Path


def _file(root: Path) -> Path:
    return Path(root) / ".rewindagents" / "guard.json"


def load(root: Path) -> list[str]:
    f = _file(root)
    if not f.is_file():
        return []
    try:
        data = json.loads(f.read_text())
    except (ValueError, OSError):
        return []
    return [p for p in data if isinstance(p, str)] if isinstance(data, list) else []


def _save(root: Path, patterns: list[str]) -> None:
    f = _file(root)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_name(f".{f.name}.tmp")
    tmp.write_text(json.dumps(patterns, indent=2))
    os.replace(tmp, f)


def normalize(pattern: str) -> str:
    p = pattern.strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def add(root: Path, patterns: list[str]) -> list[str]:
    have = load(root)
    for p in map(normalize, patterns):
        if p and p not in have:
            have.append(p)
    _save(root, have)
    return have


def remove(root: Path, pattern: str) -> bool:
    have = load(root)
    p = normalize(pattern)
    if p not in have:
        return False
    have.remove(p)
    _save(root, have)
    return True


def rel(root: Path, path_s: str) -> str | None:
    """`path_s` relative to the project root (posix), or None when it is outside it."""
    try:
        r = os.path.relpath(os.path.realpath(path_s), os.path.realpath(root))
    except ValueError:              # another drive on Windows
        return None
    if r == ".." or r.startswith(".." + os.sep):
        return None
    return r.replace(os.sep, "/")


def match(relpath: str, patterns: list[str], root: Path | None = None) -> str | None:
    """The first pattern that covers `relpath`, or None."""
    name = relpath.rsplit("/", 1)[-1]
    for p in patterns:
        if p.endswith("/"):
            if relpath.startswith(p):
                return p
        elif any(c in p for c in "*?["):
            if fnmatch(relpath, p) or fnmatch(name, p):
                return p
        elif relpath == p or relpath.startswith(p + "/"):
            return p
    return None


def hits(root: Path, paths: list[str], patterns: list[str] | None = None) -> list[tuple[str, str]]:
    """(relative path, pattern) for each of `paths` a guard pattern covers, in order, without repeats."""
    patterns = load(root) if patterns is None else patterns
    out: list[tuple[str, str]] = []
    if not patterns:
        return out
    for path_s in paths:
        r = rel(root, path_s)
        if r is None:
            continue
        p = match(r, patterns)
        if p and (r, p) not in out:
            out.append((r, p))
    return out


def record_paths(rec: dict) -> list[str]:
    """Every file a post record says the call changed: Bash checkpoints, and the 'after' entries."""
    args = rec.get("args") if isinstance(rec.get("args"), dict) else {}
    out = [c.get("path") for c in args.get("checkpoints") or [] if isinstance(c, dict)]
    out += [e.get("path") for e in args.get("after") or [] if isinstance(e, dict)]
    return [p for p in out if isinstance(p, str)]


def warning(found: list[tuple[str, str]], run: str = "rewindagents") -> str:
    files = ", ".join(r for r, _ in found)
    first = found[0][0]
    return (f"rewindagents: the agent just changed a guarded file: {files}. "
            f"Put it back: `{run} undo --only {first}` (its history: `{run} history {first}`).")


def agent_note(found: list[tuple[str, str]]) -> str:
    files = ", ".join(r for r, _ in found)
    return (f"The user has marked {files} as guarded (rewindagents guard): they do not want an agent to change "
            f"it. Tell the user what you changed in it and why, and do not change it again unless they ask.")
