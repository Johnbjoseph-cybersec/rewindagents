"""Which project a directory belongs to: the one place the hook writes and the CLI reads.

An agent's working directory moves. Claude Code's hook input `cwd` is "the new directory after Claude runs
`cd`" (code.claude.com/docs/en/hooks, read 2026-11-13), and people run `rewindagents replay` from wherever
their shell is. If each directory got its own `.rewindagents/`, one session would be split across several
logs and `rewind` from the project root would miss the steps recorded below it.

So the project is found the way git finds a repository: walk up from the directory to the nearest one that
already holds `.rewindagents/`. The walk stops after the first directory holding `.git` (a repository root;
a project never spans two repositories) and never looks in your home directory or above it unless it started
there. When nothing is found, the hook uses Claude Code's `CLAUDE_PROJECT_DIR` ("the project root where the
session started", same page) if the directory is inside it, and otherwise the directory itself, as before.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

STORE = ".rewindagents"


def _resolve(p: str | Path) -> Path:
    try:
        return Path(p).resolve()
    except OSError:
        return Path(os.path.abspath(p))


def find_store_root(start: str | Path, home: str | Path | None = None) -> Path | None:
    """The nearest directory at or above `start` that holds `.rewindagents/`, within the limits above;
    None when there is none."""
    # Walk the path as given (not resolved): recorded paths keep the spelling the agent used, and a resolved
    # root (/private/var/... on macOS) would name the same files differently. Compare resolved forms only.
    start = Path(os.path.abspath(start))
    home = _resolve(home if home is not None else Path.home())
    for d in (start, *start.parents):
        rd = _resolve(d)
        if d != start and (rd == home or rd in home.parents):
            break                       # never adopt ~/.rewindagents (or one above it) from a subdirectory
        if (d / STORE).is_dir():
            return d
        if (d / ".git").exists():
            break                       # repository root reached
    return None


def root_for(cwd: str | Path, env: Mapping[str, str] | None = None, home: str | Path | None = None) -> Path:
    """The project directory the hook records into for an agent working in `cwd`."""
    found = find_store_root(cwd, home)
    if found is not None:
        return found
    cwd = Path(cwd)
    env = os.environ if env is None else env
    proj = env.get("CLAUDE_PROJECT_DIR")
    if proj:
        p, rc = _resolve(proj), _resolve(cwd)
        if p.is_dir() and p != rc and p in rc.parents:
            return Path(os.path.abspath(cwd)).parents[len(rc.relative_to(p).parts) - 1]   # cwd's spelling
    return cwd


def default_log(cwd: str | Path | None = None, home: str | Path | None = None) -> Path:
    """The log the CLI uses when `--log` is not given: this directory's, else the nearest parent project's."""
    cwd = Path.cwd() if cwd is None else Path(cwd)
    here = Path(STORE) / "log.jsonl"
    if (cwd / here).exists():
        return here
    found = find_store_root(cwd, home)
    if found is not None and (found / here).exists():
        return found / here
    return here
