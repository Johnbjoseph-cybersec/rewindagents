"""`rewindagents gc`: delete the stored copies no record and no pending scan names; keep every rewind working."""
import hashlib
import json
import os
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rewindagents import gc, hook, rewind, verify  # noqa: E402
from test_rewind import Agent, cli  # noqa: E402


def objects(d):
    o = Path(d, ".rewindagents", "objects")
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
            pend = Path(d, ".rewindagents", "pending")
            pend.mkdir(exist_ok=True)
            (pend / "broken.json").write_text("{not json")
            before = objects(d)
            with self.assertRaisesRegex(gc.GcError, "broken.json"):
                gc.gc(a.log)
            self.assertEqual(objects(d), before)

    def test_leaves_files_that_are_not_stored_copies(self):
        with TemporaryDirectory() as d:
            a = project(d)
            odd = Path(d, ".rewindagents", "objects", ".abc.123.tmp")
            odd.write_text("half-written")
            gc.gc(a.log)
            self.assertTrue(odd.exists())

    def test_waits_for_a_hook_holding_the_store_and_gives_up_without_deleting(self):
        with TemporaryDirectory() as d:
            a = project(d)
            before = objects(d)
            with hook.store_lock(Path(d, ".rewindagents")):         # a hook between its copy and its record
                with self.assertRaisesRegex(gc.GcError, "still in use"):
                    gc.gc(a.log, timeout=0.2)
            self.assertEqual(objects(d), before)
            self.assertEqual(len(gc.gc(a.log)["deleted"]), 3)    # free again

    def test_lists_each_pending_scan_with_its_age_and_command(self):
        with TemporaryDirectory() as d:
            a = Agent(d)
            Path(d, "app.py").write_text("x = 1\n")
            a.bash("sed -i s/1/2/ app.py", post=False)          # the agent was killed before the after-scan
            (scan,) = Path(d, ".rewindagents", "pending").glob("*.json")
            got = gc.gc(a.log, dry_run=True, now=scan.stat().st_mtime + 3 * 86400)
            self.assertEqual(len(got["scans"]), 1)
            s = got["scans"][0]
            self.assertEqual((s["name"], s["tool"], s["command"], s["session"]),
                             (scan.name, "Bash", "sed -i s/1/2/ app.py", "s1"))
            self.assertAlmostEqual(s["age_days"], 3.0, places=6)
            self.assertEqual(gc.lines(got)[1:], [
                "  1 pending scan(s) (a command whose after-scan has not run) keep their copies",
                "    3.0 days old  Bash: sed -i s/1/2/ app.py"])

    def test_drop_removes_only_scans_older_than_days_then_collects_their_copies(self):
        with TemporaryDirectory() as d:
            a = Agent(d)
            Path(d, "app.py").write_text("x = 1\n")
            a.bash("sed -i s/1/2/ app.py", post=False)          # killed half way: app.py changed, no after-scan
            pend = Path(d, ".rewindagents", "pending")
            (old,) = pend.glob("*.json")
            Path(d, "app.py").write_text("x = 2\n")
            a.bash("cat app.py", post=False)                    # still running
            (new,) = set(pend.glob("*.json")) - {old}
            now = time.time()
            os.utime(old, (now - 3 * 86400, now - 3 * 86400))
            os.utime(new, (now - 3600, now - 3600))
            log_before = a.log.read_bytes()
            got = gc.gc(a.log, drop_older_than=2, now=now)
            self.assertEqual([s["name"] for s in got["dropped"]], [old.name])
            self.assertEqual(sorted(p.name for p in pend.glob("*.json")), [new.name])
            self.assertEqual(got["deleted"], [sha("x = 1\n")])  # only the dropped scan named it
            self.assertEqual((got["kept"], got["pending"]), (1, 1))
            self.assertEqual(a.log.read_bytes(), log_before)    # the log is never written
            self.assertEqual(gc.lines(got)[1:3], ["  dropped 1 pending scan(s) older than 2 days:",
                                                  "    3.0 days old  Bash: sed -i s/1/2/ app.py"])

    def test_drop_with_dry_run_reports_and_removes_nothing(self):
        with TemporaryDirectory() as d:
            a = Agent(d)
            Path(d, "app.py").write_text("x = 1\n")
            a.bash("sed -i s/1/2/ app.py", post=False)
            (scan,) = Path(d, ".rewindagents", "pending").glob("*.json")
            before = objects(d)
            got = gc.gc(a.log, dry_run=True, drop_older_than=1, now=scan.stat().st_mtime + 2 * 86400)
            self.assertEqual(([s["name"] for s in got["dropped"]], got["deleted"], got["pending"]),
                             ([scan.name], [sha("x = 1\n")], 0))
            self.assertTrue(scan.exists())
            self.assertEqual(objects(d), before)
            self.assertIn("  would drop 1 pending scan(s) older than 1 days:", gc.lines(got))

    def test_never_drops_a_scan_younger_than_a_day(self):
        with TemporaryDirectory() as d:
            a = Agent(d)
            Path(d, "app.py").write_text("x = 1\n")
            a.bash("sed -i s/1/2/ app.py", post=False)
            (scan,) = Path(d, ".rewindagents", "pending").glob("*.json")
            for days in (0.5, 0, -1, float("nan")):
                with self.assertRaisesRegex(gc.GcError, "never dropped"):
                    gc.gc(a.log, drop_older_than=days, now=scan.stat().st_mtime + 10 * 86400)
                self.assertTrue(scan.exists())
            got = gc.gc(a.log, drop_older_than=1, now=scan.stat().st_mtime + 0.9 * 86400)
            self.assertEqual((got["dropped"], got["deleted"], got["pending"]), ([], [], 1))
            self.assertTrue(scan.exists())

    def test_a_scan_no_record_names_is_listed_and_an_unreadable_old_one_can_be_dropped(self):
        with TemporaryDirectory() as d:
            a = project(d)
            pend = Path(d, ".rewindagents", "pending")
            pend.mkdir(exist_ok=True)
            orphan = pend / ("0" * 32 + ".json")              # e.g. written before the pre record named it
            orphan.write_text(json.dumps({"keep.txt": sha("v2\n")}))
            broken = pend / "broken.json"
            broken.write_text("{not json")
            now = time.time()
            os.utime(broken, (now - 5 * 86400, now - 5 * 86400))
            got = gc.gc(a.log, drop_older_than=4, now=now)     # without the drop it refuses (test above)
            self.assertEqual([s["name"] for s in got["dropped"]], ["broken.json"])
            self.assertFalse(broken.exists())
            self.assertIn(sha("v2\n"), objects(d))             # the orphan scan still keeps its copy
            self.assertEqual(gc.lines(got)[-1], "    0.0 days old  command not recorded "
                                                "(scan made before rewindagents named it in the log)")

    # Unix only: msvcrt has no shared lock, so on Windows a shared request takes the exclusive one (filelock.py) and
    # a second holder in the same process waits for the first forever. CI run 43437432241 hung here for 20 min.
    @unittest.skipIf(os.name == "nt", "msvcrt has no shared lock: shared holders take turns on Windows (filelock.py)")
    def test_hooks_share_the_lock_with_each_other(self):
        with TemporaryDirectory() as d:
            a = Agent(d)
            with hook.store_lock(Path(d, ".rewindagents")):
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

    def test_cli_drops_stale_pending_scans_and_refuses_under_a_day(self):
        with TemporaryDirectory() as d:
            a = Agent(d)
            Path(d, "app.py").write_text("x = 1\n")
            a.bash("sed -i s/1/2/ app.py", post=False)
            (scan,) = Path(d, ".rewindagents", "pending").glob("*.json")
            code, _, err = cli("--log", str(a.log), "gc", "--drop-pending-older-than", "0.5")
            self.assertEqual(code, 1)
            self.assertIn("never dropped", err)
            old = time.time() - 3 * 86400
            os.utime(scan, (old, old))
            code, out, err = cli("--log", str(a.log), "gc", "--drop-pending-older-than", "2")
            self.assertEqual((code, err), (0, ""))
            self.assertEqual(out, "deleted 1 stored copies (6 bytes freed); kept 0 that the log or a pending scan "
                                  "names\n  dropped 1 pending scan(s) older than 2 days:\n"
                                  "    3.0 days old  Bash: sed -i s/1/2/ app.py\n")
            self.assertFalse(scan.exists())

    def test_readme_documents_gc(self):
        readme = (Path(__file__).resolve().parent.parent / "README.md").read_text(encoding="utf-8")
        self.assertIn("rewindagents gc --dry-run", readme)
        self.assertIn("pending scan", readme)
        self.assertIn("rewindagents gc --drop-pending-older-than 7", readme)
        self.assertIn(f"younger than {gc.MIN_DROP_DAYS:g} day", readme)


if __name__ == "__main__":
    unittest.main()
