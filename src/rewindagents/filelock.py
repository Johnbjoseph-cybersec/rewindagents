"""One file lock for every platform: fcntl.flock on Unix, msvcrt.locking on Windows.

acquire(fh, exclusive=..., blocking=...) and release(fh) take an open file object. A non-blocking
acquire that finds the lock held raises BlockingIOError on both platforms.

Windows has no shared lock in msvcrt, so a shared request takes the exclusive one there: holders that
could run side by side on Unix (several hooks at once) take turns instead. Nothing in the package holds
two locks on the same file in one process, so this cannot deadlock. The Windows lock covers byte 0 of
the file (locking past the end is allowed), so the file's contents never matter.
"""
from __future__ import annotations

import os
import time

if os.name == "nt":  # pragma: no cover - exercised on Windows CI and through a stand-in module in tests
    import msvcrt as _backend
else:
    import fcntl as _backend

RETRY_SECONDS = 0.05


def acquire(fh, exclusive: bool = True, blocking: bool = True, *, backend=None) -> None:
    mod = backend or _backend
    if hasattr(mod, "flock"):
        flags = mod.LOCK_EX if exclusive else mod.LOCK_SH
        mod.flock(fh, flags if blocking else flags | mod.LOCK_NB)
        return
    while True:
        fh.seek(0)
        try:
            mod.locking(fh.fileno(), mod.LK_NBLCK, 1)
            return
        except OSError as exc:  # held by another handle: msvcrt says EACCES or EDEADLOCK
            if not blocking:
                raise BlockingIOError(*exc.args) from exc
            time.sleep(RETRY_SECONDS)


def release(fh, *, backend=None) -> None:
    mod = backend or _backend
    if hasattr(mod, "flock"):
        mod.flock(fh, mod.LOCK_UN)
        return
    fh.seek(0)
    mod.locking(fh.fileno(), mod.LK_UNLCK, 1)
