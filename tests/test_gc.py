"""`rewindagent gc`: delete the stored copies no record and no pending scan names; keep every rewind working."""
import hashlib
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rewindagent import gc, hook, rewind, verify  # noqa: E402
from test_rewind import Agent, cli  # noqa: E402


def objects(d):
    o = Path(d, ".rewindagent", "objects")
    return sorted(p.name for p in o.iterdir()) if o.is_dir() else []


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def project(d):
    """Step 1 creates keep.txt (v1), step 2 overwrites it (v2: names the v1 copy), then two files appear and
    step 3 is a Bash `ls` that changes nothing: its scan saves copies of all three files and names none."""
    a = Agent(d)
    a.write("keep.txt", "v1\n")
    a.write("keep.txt", "v2\n")
    Path(d, "x.txt").write_text("x" * 100)
    Path(d, "y.txt").write_text("y" * 50)
    a.bash("ls")
    return a


class TestGc(unittest.TestCase):
    def test_deletes_only_unnamed_copies_measures_bytes_and_rewind_still_works(self):
        with TemporaryDirectory() as d:
            a = project(d)
            self.assertEqual(objects(d), sorted([sha("v1\n"), sha("v2\n"), sha("x" * 100), sha("y" * 50)]))
            log_before = a.log.read_bytes()
            got = gc.gc(a.log)
            self.assertEqual(sorted(got["deleted"]), sorted([sha("v2\n"), sha("x" * 100), sha("y" * 50)]))
            self.assertEqual(got["bytes"], 3 + 100 + 50)        # the sizes of the deleted files
            self.assertEqual((got["kept"], got["pending"]), (1, 0))
            self.assertEqual(objects(d), [sha("v1\n")])
            self.assertEqual(a.log.read_bytes(), log_before)   # the log is never written
            self.assertEqual(verify(a.log)[0], True)
            rewind.rewind(a.log, 1)
            self.assertEqual(Path(d, "keep.txt").read_text(), "v1\n")
            self.assertEqual(gc.gc(a.log)["deleted"], [])      # nothing left to delete

    def test_dry_run_reports_the_same_and_deletes_nothing(self):
        with TemporaryDirectory() as d:
            a = project(d)
            before = objects(d)
            got = gc.gc(a.log, dry_run=True)
            self.assertEqual((len(got["deleted"]), got["bytes"], got["kept"]), (3, 153, 1))
            self.assertEqual(objects(d), before)
            self.assertEqual(gc.lines(got), ["would delete 3 stored copies (153 bytes); "
                                             "kept 1 that the log or a pending scan names"])

    def test_a_pending_scan_keeps_its_copies_until_the_command_finishes(self):
        with TemporaryDirectory() as d:
            a = Agent(d)
            Path(d, "app.py").write_text("x = 1\n")
            Path(d, "other.py").write_text("o\n")
            a.bash("sed -i s/1/2/ app.py", post=False)          # the command is still running
            got = gc.gc(a.log)
            self.assertEqual((got["deleted"], got["kept"], got["pending"]), ([], 2, 1))
            self.assertIn("1 pending scan(s)", "\n".join(gc.lines(got)))
            Path(d, "app.py").write_text("x = 2\n")
            hook.handle(a._p("PostToolUse", "Bash", {"command": "sed -i s/1/2/ app.py"}, {"stdout": ""}))
            got = gc.gc(a.log)                                   # now only app.py's before-copy is named
            self.assertEqual((got["deleted"], got["kept"], got["pending"]), ([sha("o\n")], 1, 0))
            rewind.rewind(a.log, 0)
            self.assertEqual(Path(d, "app.py").read_text(), "x = 1\n")

    def test_the_next_bash_call_saves_again_a_copy_gc_deleted(self):
        """bashscan's stat cache still lists x.txt's hash; the copy is gone, so the next scan must save it
        again, or a rewind of the next command could not put x.txt back."""
        with TemporaryDirectory() as d:
            a = project(d)
            gc.gc(a.log)
            self.assertNotIn(sha("x" * 100), objects(d))
            a.bash("sed -i s/x/z/g x.txt", action=lambda cwd: (cwd / "x.txt").write_text("z" * 100))
            p = rewind.rewind(a.log, 3)
            self.assertEqual(p["cannot"], [])
            self.assertEqual(Path(d, "x.txt").read_text(), "x" * 100)

    def test_refuses_a_log_that_does_not_verify(self):
        with TemporaryDirectory() as d:
            a = project(d)
            lines = a.log.read_text().splitlines()
            lines[0] = lines[0].replace("keep.txt", "kept.txt")
            a.log.write_text("\n".join(lines) + "\n")
            before = objects(d)
            with self.assertRaisesRegex(gc.GcError, "does not verify"):
                gc.gc(a.log)
            self.assertEqual(objects(d), before)

    def test_refuses_when_a_pending_scan_cannot_be_read(self):
        with TemporaryDirectory() as d:
            a = project(d)
            pend = Path(d, ".rewindagent", "pending")
            pend.mkdir(exist_ok=True)
            (pend / "broken.json").write_text("{not json")
            before = objects(d)
            with self.assertRaisesRegex(gc.GcError, "broken.json"):
                gc.gc(a.log)
            self.assertEqual(objects(d), before)

    def test_leaves_files_that_are_not_stored_copies(self):
        with TemporaryDirectory() as d:
            a = project(d)
            odd = Path(d, ".rewindagent", "objects", ".abc.123.tmp")
            odd.write_text("half-written")
            gc.gc(a.log)
            self.assertTrue(odd.exists())

    def test_waits_for_a_hook_holding_the_store_and_gives_up_without_deleting(self):
        with TemporaryDirectory() as d:
            a = project(d)
            before = objects(d)
            with hook.store_lock(Path(d, ".rewindagent")):         # a hook between its copy and its record
                with self.assertRaisesRegex(gc.GcError, "still in use"):
                    gc.gc(a.log, timeout=0.2)
            self.assertEqual(objects(d), before)
            self.assertEqual(len(gc.gc(a.log)["deleted"]), 3)    # free again

    def test_hooks_share_the_lock_with_each_other(self):
        with TemporaryDirectory() as d:
            a = Agent(d)
            with hook.store_lock(Path(d, ".rewindagent")):
                a.write("f.txt", "1")                            # does not wait on the other shared holder
            self.assertEqual([s["tool"] for s in rewind.steps(a.log)], ["Write"])


class TestGcCli(unittest.TestCase):
    def test_cli_prints_counts_and_exit_codes(self):
        with TemporaryDirectory() as d:
            a = project(d)
            code, out, err = cli("--log", str(a.log), "gc", "--dry-run")
            self.assertEqual((code, err), (0, ""))
            self.assertEqual(out, "would delete 3 stored copies (153 bytes); kept 1 that the log or a pending scan names\n")
            code, out, _ = cli("--log", str(a.log), "gc")
            self.assertEqual((code, out), (0, "deleted 3 stored copies (153 bytes freed); kept 1 that the log or a "
                                              "pending scan names\n"))
            a.log.write_text(a.log.read_text().replace("keep.txt", "kept.txt", 1))
            code, _, err = cli("--log", str(a.log), "gc")
            self.assertEqual(code, 1)
            self.assertIn("refusing to delete anything", err)
            code, _, err = cli("--log", str(Path(d, "nope.jsonl")), "gc")
            self.assertEqual(code, 2)

    def test_readme_documents_gc(self):
        readme = (Path(__file__).resolve().parent.parent / "README.md").read_text(encoding="utf-8")
        self.assertIn("rewindagent gc --dry-run", readme)
        self.assertIn("pending scan", readme)


if __name__ == "__main__":
    unittest.main()
