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
        if os.name == "nt":
            # msvcrt has no shared lock: a shared request takes the exclusive one there (module docstring),
            # so on the real Windows backend a second shared holder is refused rather than admitted.
            with self.path.open("a+") as a, self.path.open("a+") as b:
                filelock.acquire(a, exclusive=False)
                with self.assertRaises(BlockingIOError):
                    filelock.acquire(b, exclusive=False, blocking=False)
                filelock.release(a)
                filelock.acquire(b, exclusive=False, blocking=False)
                filelock.release(b)
            return
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

    def bounded(self, fn, seconds=5.0):
        """Run fn in a thread; fail (instead of hanging the suite, as Windows CI did for 20 min) if it is not done."""
        out = []
        t = threading.Thread(target=lambda: out.append(fn()), daemon=True)
        t.start()
        t.join(seconds)
        self.assertFalse(t.is_alive(), f"still waiting after {seconds:g} s: the nested acquire spins on its own lock")
        return out[0]

    def test_nested_shared_store_lock_in_one_process_does_not_wait_on_itself(self):
        # CI run 43437432241: a shared hold, then a step recorded in the same process (a second shared hold).
        # msvcrt has no shared lock, so the second handle waited for the first forever.
        store = self.root / ".rewindagents"

        def nest():
            with hook.store_lock(store):
                with hook.store_lock(store):
                    with hook.store_lock(store):
                        return dict(self.ms.table)
        with mock.patch.object(filelock, "_backend", self.ms):
            held = self.bounded(nest)
        self.assertEqual(len(held), 1, "one OS lock for the whole nest")
        self.assertEqual(self.ms.table, {}, "a lock outlived its with-block")

    def test_a_step_recorded_inside_a_held_store_lock_on_the_windows_path(self):
        # test_gc.test_hooks_share_the_lock_with_each_other, through the stand-in: the real hook.handle, in-process
        root = self.root / "proj"
        root.mkdir()
        f = root / "f.txt"

        def step():
            with hook.store_lock(root / ".rewindagents"):
                for event in ("PreToolUse", "PostToolUse"):
                    hook.handle({"session_id": "s1", "hook_event_name": event, "tool_name": "Write", "cwd": str(root),
                                 "tool_input": {"file_path": str(f), "content": "1"}, "tool_response": {"ok": True}})
                    f.write_text("1")
            return log.verify(root / ".rewindagents" / "log.jsonl")
        with mock.patch.object(filelock, "_backend", self.ms):
            ok, n, msg = self.bounded(step)
        self.assertEqual((ok, n), (True, 2), msg)
        self.assertEqual(self.ms.table, {})

    def test_a_nested_hold_still_keeps_gc_out_until_the_outermost_ends(self):
        store = self.root / ".rewindagents"
        with mock.patch.object(filelock, "_backend", self.ms):
            def check():
                with hook.store_lock(store):
                    with hook.store_lock(store):
                        pass                                   # inner hold ended; the outer one still holds
                    with self.assertRaises(TimeoutError):
                        with hook.store_lock(store, exclusive=True, timeout=0.2):
                            pass
                with hook.store_lock(store, exclusive=True, timeout=0.2):
                    return True
            self.assertTrue(self.bounded(check))
        self.assertEqual(self.ms.table, {})

    def test_threads_sharing_a_hold_release_it_once_the_last_one_leaves(self):
        store = self.root / ".rewindagents"
        inside, go = threading.Barrier(5), threading.Event()

        def holder():
            with hook.store_lock(store):
                inside.wait(5)
                go.wait(5)
        with mock.patch.object(filelock, "_backend", self.ms):
            ts = [threading.Thread(target=holder, daemon=True) for _ in range(4)]  # daemon: old code spins forever
            for t in ts:
                t.start()
            inside.wait(5)                                     # all 4 inside at once: they share one hold
            self.assertEqual(len(self.ms.table), 1)
            with self.assertRaises(TimeoutError):
                with hook.store_lock(store, exclusive=True, timeout=0.2):
                    pass
            go.set()
            for t in ts:
                t.join(5)
            with hook.store_lock(store, exclusive=True, timeout=0.2):
                pass
        self.assertEqual(self.ms.table, {})


class TestStoreLockUnix(unittest.TestCase):
    def test_nested_hold_keeps_another_process_out_until_the_outermost_ends(self):
        with tempfile.TemporaryDirectory() as d:
            store = Path(d, ".rewindagents")
            probe = ("import sys; sys.path.insert(0, sys.argv[1]); from pathlib import Path; from rewindagents import hook\n"
                     "try:\n    with hook.store_lock(Path(sys.argv[2]), exclusive=True, timeout=0.2): print('got')\n"
                     "except TimeoutError: print('busy')")

            def other():
                import subprocess
                return subprocess.run([sys.executable, "-c", probe, str(SRC.parent), str(store)], capture_output=True,
                                      text=True, timeout=60).stdout.strip()
            with hook.store_lock(store):
                with hook.store_lock(store):
                    pass
                self.assertEqual(other(), "busy")
            self.assertEqual(other(), "got")


class TestOneLockModule(unittest.TestCase):
    def test_only_filelock_imports_a_platform_lock(self):
        for f in SRC.glob("*.py"):
            if f.name == "filelock.py":
                continue
            text = f.read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"^\s*(import|from)\s+(fcntl|msvcrt)\b", text, re.M), f.name)


if __name__ == "__main__":
    unittest.main()
