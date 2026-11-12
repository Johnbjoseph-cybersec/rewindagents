"""`rewind N --only PATH`: put back just the named files, with the same checks, recorded as an undoable step."""
import json
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_rewind import Agent, cli  # noqa: E402

from rewindagents import rewind, verify  # noqa: E402


class TestRewindOnly(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.d = Path(self.tmp.name).resolve()
        self.a = Agent(self.d)
        self.a.write("app.py", "v1\n")          # step 1
        self.a.write("cfg.toml", "good\n")      # step 2
        self.a.write("app.py", "v2-good\n")     # step 3: the agent's good work
        self.a.write("cfg.toml", "broken\n")    # step 4: the agent's bad change
        self.a.write("lib/x.py", "x\n")         # step 5: creates a file in a directory
        self.a.write("lib/y.py", "y\n")         # step 6

    def tearDown(self):
        self.tmp.cleanup()

    def read(self, name):
        p = self.d / name
        return p.read_text() if p.exists() else None

    def test_only_the_named_file_goes_back_the_rest_stays(self):
        p = rewind.rewind(self.a.log, 2, only=[self.d / "cfg.toml"])
        self.assertEqual(self.read("cfg.toml"), "good\n")
        self.assertEqual(self.read("app.py"), "v2-good\n")        # kept: not named
        self.assertEqual(self.read("lib/x.py"), "x\n")
        self.assertEqual([Path(x).name for x, _ in p["restore"]], ["cfg.toml"])
        self.assertEqual(p["delete"], [])

    def test_a_directory_names_every_file_under_it(self):
        rewind.rewind(self.a.log, 4, only=[self.d / "lib"])
        self.assertIsNone(self.read("lib/x.py"))
        self.assertIsNone(self.read("lib/y.py"))
        self.assertEqual(self.read("cfg.toml"), "broken\n")

    def test_it_is_recorded_as_a_step_and_can_be_undone(self):
        rewind.rewind(self.a.log, 2, only=[self.d / "cfg.toml"])
        steps = rewind.steps(self.a.log)
        self.assertEqual(len(steps), 7)
        last = steps[-1]
        self.assertEqual((last["event"], last["to_step"], last["only"]), ("rewind", 2, ["cfg.toml"]))
        self.assertEqual([Path(c["path"]).name for c in last["checkpoints"]], ["cfg.toml"])
        self.assertIn("only cfg.toml", rewind.summary(last))
        rewind.rewind(self.a.log, 6)                               # undo it
        self.assertEqual(self.read("cfg.toml"), "broken\n")
        self.assertEqual(self.read("app.py"), "v2-good\n")
        self.assertTrue(verify(self.a.log)[0])

    def test_relative_paths_are_read_from_the_current_directory(self):
        old = os.getcwd()
        os.chdir(self.d / "lib")
        try:
            code, out, err = cli("--log", str(self.a.log), "rewind", "5", "--only", "y.py")
        finally:
            os.chdir(old)
        self.assertEqual(code, 0, err)
        self.assertIsNone(self.read("lib/y.py"))
        self.assertEqual(self.read("lib/x.py"), "x\n")
        self.assertIn("delete   lib/y.py", out)

    def test_cli_repeats_only_and_reports_paths_nothing_changed(self):
        code, out, err = cli("--log", str(self.a.log), "rewind", "3",
                             "--only", str(self.d / "cfg.toml"), "--only", str(self.d / "app.py"))
        self.assertEqual(code, 0, err)
        self.assertIn("restore  cfg.toml", out)
        self.assertIn(f"skip     {self.d / 'app.py'}: no step after step 3 changed it", out)
        self.assertIn("undo it with:", out)
        self.assertEqual(self.read("cfg.toml"), "good\n")
        self.assertEqual(self.read("app.py"), "v2-good\n")

    def test_a_path_no_later_step_changed_is_refused_and_nothing_is_recorded(self):
        before = self.a.log.read_text()
        code, out, err = cli("--log", str(self.a.log), "rewind", "2", "--only", str(self.d / "nope.py"))
        self.assertEqual(code, 1)
        self.assertIn("no step after step 2 changed", err)
        self.assertEqual(self.a.log.read_text(), before)

    def test_dry_run_with_only_changes_nothing(self):
        before = self.a.log.read_text()
        p = rewind.rewind(self.a.log, 2, dry_run=True, only=[self.d / "cfg.toml"])
        self.assertEqual(self.read("cfg.toml"), "broken\n")
        self.assertEqual(self.a.log.read_text(), before)
        self.assertEqual(len(p["restore"]), 1)

    def test_tampered_log_is_refused_before_anything_changes(self):
        lines = self.a.log.read_text().splitlines()
        rec = json.loads(lines[0])
        rec["tool"] = "Edit"
        lines[0] = json.dumps(rec, sort_keys=True)
        self.a.log.write_text("\n".join(lines) + "\n")
        with self.assertRaises(rewind.RewindError):
            rewind.rewind(self.a.log, 2, only=[self.d / "cfg.toml"])
        self.assertEqual(self.read("cfg.toml"), "broken\n")

    def test_altered_stored_copy_is_reported_not_restored(self):
        cp = rewind.steps(self.a.log)[3]["checkpoints"][0]       # step 4 saved cfg.toml = "good"
        obj = self.d / ".rewindagents" / "objects" / cp["sha256"]
        obj.write_text("evil\n")
        p = rewind.rewind(self.a.log, 2, only=[self.d / "cfg.toml"])
        self.assertEqual(self.read("cfg.toml"), "broken\n")
        self.assertEqual([(Path(x).name, why) for x, why in p["cannot"]],
                         [("cfg.toml", "stored copy missing or altered")])


if __name__ == "__main__":
    unittest.main()
