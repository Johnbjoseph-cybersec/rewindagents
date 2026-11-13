"""`python -m rewindagents ...`, and, from a clone, `python <clone>/src/rewindagents/__main__.py ...`.

The second form is what hook.hook_command writes for a Windows interpreter from an uninstalled clone: the hook
shells there (Git Bash, PowerShell, cmd.exe) share no syntax for a PYTHONPATH prefix, but all of them run
`<python> <file> hook`. Run as a file, this module has no package, so it makes the clone's src/ importable and
runs the package the normal way."""
import sys

if __package__:
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
