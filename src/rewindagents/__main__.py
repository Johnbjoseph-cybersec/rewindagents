"""`python -m rewindagents ...`, and, from a clone, `python <clone>/src/rewindagents/__main__.py ...`.

The second form is what hook.hook_command writes for a Windows interpreter from an uninstalled clone: the hook
shells there (Git Bash, PowerShell, cmd.exe) share no syntax for a PYTHONPATH prefix, but all of them run
`<python> <file> hook`. Run as a file, this module has no package, so it makes the clone's src/ importable and
runs the package the normal way."""
import sys



def _hook_agent(argv: list[str]) -> str | None:
    """The agent named by `hook [--agent X | --agent=X]`, or None when argv is anything else (then cli parses it,
    so every other form and every error message stays argparse's)."""
    if argv[:1] != ["hook"]:
        return None
    from .agents import AGENTS, DEFAULT
    rest = argv[1:]
    if not rest:
        return DEFAULT
    if len(rest) == 2 and rest[0] == "--agent":
        name = rest[1]
    elif len(rest) == 1 and rest[0].startswith("--agent="):
        name = rest[0][8:]
    else:
        return None
    return name if name in AGENTS else None


if __package__:
    # The hook runs twice per tool call: go straight to hook.py, without importing the CLI (argparse, bundle,
    # export, rewind, ...) that the hook does not use.
    _agent = _hook_agent(sys.argv[1:])
    if _agent is not None:
        from .hook import run

        sys.exit(run(agent=_agent))
    from .cli import main

    sys.exit(main())

import runpy  # noqa: E402
from pathlib import Path  # noqa: E402

_here = Path(__file__).resolve()
# Python put this package directory first on sys.path; src/ belongs there instead.
if sys.path and Path(sys.path[0] or ".").resolve() == _here.parent:
    sys.path[0] = str(_here.parent.parent)
else:
    sys.path.insert(0, str(_here.parent.parent))
runpy.run_module("rewindagents", run_name="__main__", alter_sys=True)
