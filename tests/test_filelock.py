"""filelock: one lock for Unix (fcntl) and Windows (msvcrt).

The Unix path runs for real here. The Windows path runs against a stand-in for msvcrt that keeps a byte-range
lock table like the real one (a byte held by another handle raises PermissionError, unlocking a byte you do not
hold raises too). That proves our side of the contract - seek to byte 0, retry, map the error, unlock before
close - not Windows itself; only a Windows run can do that, and the README says so."""
import errno
import os
import re
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rewindagents import filelock, hook, log  # noqa: E402

SRC = Path(__file__).resolve().parent.parent / "src" / "rewindagents"


class FakeMsvcrt:
    LK_UNLCK, LK_LOCK, LK_NBLCK = 0, 1, 2

    def __init__(self):
        self.table = {}          # (inode, offset) -> fd
        self.offsets = []        # every offset asked for, to check byte 0
        self.guard = threading.Lock()

    def locking(self, fd, mode, nbytes):
        assert nbytes == 1
        key = (os.fstat(fd).st_ino, os.lseek(fd, 0, os.SEEK_CUR))
        self.offsets.append(key[1])
        with self.guard:
            holder = self.table.get(key)
            if mode == self.LK_UNLCK:
                if holder != fd:
                    raise PermissionError(errno.EACCES, "not locked by this handle")
                del self.table[key]
            elif mode == self.LK_NBLCK:
                if holder is not None:
                    raise PermissionError(errno.EACCES, "Permission denied")
                self.table[key] = fd
            else:
                raise AssertionError("only LK_NBLCK and LK_UNLCK are used")


class TestUnixPath(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "lock"

    def tearDown(self):
        self.tmp.cleanup()

    def test_exclusive_excludes_and_release_frees(self):
        with self.path.open("a+") as a, self.path.open("a+") as b:
            filelock.acquire(a, exclusive=True)
            with self.assertRaises(BlockingIOError):
                filelock.acquire(b, exclusive=True, blocking=False)
            filelock.release(a)
            filelock.acquire(b, exclusive=True, blocking=False)
            filelock.release(b)

    def test_shared_holders_coexist_and_keep_exclusive_out(self):
        with self.path.open("a+") as a, self.path.open("a+") as b, self.path.open("a+") as c:
            filelock.acquire(a, exclusive=False)
            filelock.acquire(b, exclusive=False, blocking=False)
            with self.assertRaises(BlockingIOError):
                filelock.acquire(c, exclusive=True, blocking=False)
            filelock.release(a)
            filelock.release(b)
            filelock.acquire(c, exclusive=True, blocking=False)
            filelock.release(c)


class TestWindowsPath(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path = self.root / "lock"
        self.ms = FakeMsvcrt()

    def tearDown(self):
        self.tmp.cleanup()

    def test_second_handle_gets_blocking_io_error_until_release(self):
        with self.path.open("a+") as a, self.path.open("a+") as b:
            filelock.acquire(a, backend=self.ms)
            with self.assertRaises(BlockingIOError):
                filelock.acquire(b, blocking=False, backend=self.ms)
            filelock.release(a, backend=self.ms)
            filelock.acquire(b, blocking=False, backend=self.ms)
            filelock.release(b, backend=self.ms)
        self.assertEqual(self.ms.table, {})

    def test_shared_request_is_exclusive_on_windows(self):
        with self.path.open("a+") as a, self.path.open("a+") as b:
            filelock.acquire(a, exclusive=False, backend=self.ms)
            with self.assertRaises(BlockingIOError):
                filelock.acquire(b, exclusive=False, blocking=False, backend=self.ms)
            filelock.release(a, backend=self.ms)

    def test_always_byte_zero_even_after_writing(self):
        with self.path.open("a+") as a:
            a.write("x" * 500)
            a.flush()
            filelock.acquire(a, backend=self.ms)
            a.seek(0, os.SEEK_END)
            a.write("more")
            a.flush()
            filelock.release(a, backend=self.ms)
        self.assertEqual(set(self.ms.offsets), {0})

    def test_blocking_acquire_waits_for_the_holder(self):
        with self.path.open("a+") as a, self.path.open("a+") as b:
            filelock.acquire(a, backend=self.ms)
            got = []
            t = threading.Thread(target=lambda: (filelock.acquire(b, backend=self.ms), got.append(time.monotonic())))
            t.start()
            time.sleep(0.3)
            self.assertEqual(got, [], "acquired while another handle held the lock")
            freed = time.monotonic()
            filelock.release(a, backend=self.ms)
            t.join(5)
            self.assertEqual(len(got), 1)
            self.assertGreaterEqual(got[0], freed)
            filelock.release(b, backend=self.ms)

    def test_recorder_threads_keep_one_chain_on_the_windows_path(self):
        p = self.root / "log.jsonl"
        with mock.patch.object(filelock, "_backend", self.ms):
            threads = [threading.Thread(target=lambda i=i: [log.Recorder(p).record("s", "Bash", {"i": i, "k": k})
                                                            for k in range(10)]) for i in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(30)
        ok, n, msg = log.verify(p)
        self.assertTrue(ok, msg)
        self.assertEqual(n, 80)
        self.assertEqual(self.ms.table, {})

    def test_store_lock_on_the_windows_path(self):
        store = self.root / ".rewindagents"
        with mock.patch.object(filelock, "_backend", self.ms):
            with hook.store_lock(store):
                with self.assertRaises(TimeoutError):
                    with hook.store_lock(store, exclusive=True, timeout=0.2):
                        pass
            with hook.store_lock(store, exclusive=True, timeout=0.2):
                pass
        self.assertEqual(self.ms.table, {}, "a lock outlived its with-block")


class TestOneLockModule(unittest.TestCase):
    def test_only_filelock_imports_a_platform_lock(self):
        for f in SRC.glob("*.py"):
            if f.name == "filelock.py":
                continue
            text = f.read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"^\s*(import|from)\s+(fcntl|msvcrt)\b", text, re.M), f.name)


if __name__ == "__main__":
    unittest.main()
