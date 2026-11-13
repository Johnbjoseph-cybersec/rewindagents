"""Path spellings from either OS, for the strings rewindagents reads back (bundle import, page scrubbing).

A bundle can be made on Windows and imported on macOS, and a Windows log names C:\\proj\\a.py or, written by
an agent, C:/proj/a.py. These helpers judge a spelling by its own shape, never by the OS reading it."""
from __future__ import annotations

import ntpath
import posixpath


def isabs(s: str) -> bool:
    """Absolute on either OS: /proj, C:\\proj, C:/proj, \\\\server\\share\\proj."""
    return posixpath.isabs(s) or ntpath.isabs(s)


def seps(spelling: str) -> str:
    """The separators that may follow a root spelling: a Windows path takes both, a POSIX path only '/'."""
    return "\\/" if ntpath.splitdrive(spelling)[0] else "/"


def forms(spelling: str) -> list[str]:
    """The spelling and, for a Windows path, the same path with forward slashes (what agents often write)."""
    if seps(spelling) == "/":
        return [spelling]
    return list(dict.fromkeys([spelling, spelling.replace("\\", "/")]))
