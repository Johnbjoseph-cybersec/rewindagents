"""A rewind must not silently overwrite a change made after the steps it takes back.

FIRST_RUN.md friction 2: after session A, a hand edit and session B, `rewind 0 --session A` put calc.py back
and dropped the hand edit and session B's change, and neither `diff` nor `rewind --dry-run` said so. Now the
log holds each file's hash right after every step, so a file whose bytes are not what the log last recorded
(or that a later session changed) is listed by diff and --dry-run, refused by rewind and branch unless
--force, and named by fork.
"""
import json
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_rewind import Agent, cli  # noqa: E402

from rewindagents import log, rewind, runs  # noqa: E402

ORIGINAL = "def add(a, b):\n    return a + b\n"
BY_A = ORIGINAL + "\ndef div(a, b):\n    return a / b\n"
BY_HAND = "# calculator\n" + BY_A
BY_B = BY_HAND.replace("    return a / b\n", "    if b == 0:\n        raise ZeroDivisionError('b is 0')\n"
                                                "    return a / b\n")


class DriftCase(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        (self.root / "calc.py").write_text(ORIGINAL, newline="")
        self.old = os.getcwd()
        os.chdir(self.root)
        self.a = Agent(self.root, "aaaaaaaa-1111")
        self.a.write("calc.py", BY_A)
        self.log = self.a.log

    def tearDown(self):
        os.chdir(self.old)
        self.tmp.cleanup()

    def calc(self):
        return (self.root / "calc.py").read_text()


class TestHandEdit(DriftCase):
    def setUp(self):
        super().setUp()
        (self.root / "calc.py").write_text(BY_HAND, newline="")       # by hand, after the session's last step

    def test_the_post_record_holds_the_hash_right_after_the_step(self):
        post = [r for r in log.read(self.log) if r["event"] == "post"][-1]
        self.assertEqual(len(post["args"]["after"]), 1)
        self.assertEqual(post["args"]["after"][0]["path"], str(self.root / "calc.py"))
        import hashlib
        self.assertEqual(post["args"]["after"][0]["after"], hashlib.sha256(BY_A.encode()).hexdigest())

    def test_rewind_refuses_and_changes_nothing(self):
        before_log = self.log.read_bytes()
        code, out, err = cli("rewind", "0")
        self.assertEqual(code, 1, out + err)
        self.assertEqual(self.calc(), BY_HAND)
        self.assertEqual(self.log.read_bytes(), before_log)       # not even a record
        self.assertIn("refused, nothing changed", err)
        self.assertIn("calc.py: changed outside any recorded step", err)
        self.assertIn("--force", err)

    def test_dry_run_warns_and_lists_the_file(self):
        code, out, err = cli("rewind", "0", "--dry-run")
        self.assertEqual(code, 1)
        self.assertIn("WARNING  1 file changed after the steps this rewind takes back", out)
        self.assertIn("calc.py: changed outside any recorded step", out)
        self.assertEqual(self.calc(), BY_HAND)

    def test_diff_warns(self):
        code, out, err = cli("diff", "0")
        self.assertEqual(code, 1)
        self.assertIn("-# calculator", out)                      # the diff itself still shows what would go
        self.assertIn("WARNING calc.py: changed outside any recorded step", err)

    def test_force_overwrites_and_the_printed_undo_brings_the_hand_edit_back(self):
        code, out, err = cli("rewind", "0", "--force")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.calc(), ORIGINAL)
        self.assertIn("overwrote 1 file that changed after the steps it took back", out)
        undo = next(line for line in out.splitlines() if "undo it with:" in line).split("undo it with: ")[1]
        words = undo.split()
        args = words[words.index("rewind"):]                      # drop the program ("python3 -m rewindagents")
        code, out, err = cli(*args)
        self.assertEqual(code, 0, out + err)                      # the undo is not itself refused
        self.assertEqual(self.calc(), BY_HAND)

    def test_rewinding_only_another_file_is_not_refused(self):
        self.a.write("notes.md", "x\n")
        code, out, err = cli("rewind", "1", "--only", "notes.md")
        self.assertEqual(code, 0, out + err)
        self.assertFalse((self.root / "notes.md").exists())
        self.assertEqual(self.calc(), BY_HAND)

    def test_branch_refuses_too(self):
        code, out, err = cli("branch", "0", "--name", "try")
        self.assertEqual(code, 1)
        self.assertIn("branch refused", err)
        self.assertEqual(self.calc(), BY_HAND)
        code, out, err = cli("branch", "0", "--name", "try", "--force")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.calc(), ORIGINAL)

    def test_the_ui_refuses_unless_forced(self):
        from rewindagents import ui
        with self.assertRaises(ui.UIError) as e:
            ui.do_rewind(self.log, {"session": "aaaaaaaa-1111", "step": 0, "confirm": True})
        self.assertEqual(e.exception.status, 409)
        self.assertIn("calc.py", str(e.exception))
        self.assertEqual(self.calc(), BY_HAND)
        view = ui.preview(self.log, {"session": "aaaaaaaa-1111", "step": 0})
        self.assertEqual([d["path"] for d in view["drift"]], ["calc.py"])
        ui.do_rewind(self.log, {"session": "aaaaaaaa-1111", "step": 0, "confirm": True, "force": True})
        self.assertEqual(self.calc(), ORIGINAL)


class TestLaterSession(DriftCase):
    """FIRST_RUN.md: session A, a hand edit, session B; then `rewind 0 --session A`."""

    def setUp(self):
        super().setUp()
        (self.root / "calc.py").write_text(BY_HAND, newline="")
        self.b = Agent(self.root, "bbbbbbbb-2222")
        self.b.write("calc.py", BY_B)

    def test_rewinding_the_older_session_names_the_later_session_and_the_hand_edit(self):
        code, out, err = cli("rewind", "0", "--session", "aaaaaaaa-1111")
        self.assertEqual(code, 1)
        self.assertEqual(self.calc(), BY_B)
        self.assertIn("calc.py: changed by session bbbbbbbb step 1, and outside any recorded step", err)

    def test_the_latest_session_alone_has_no_drift(self):
        code, out, err = cli("rewind", "0")                      # session B, nothing changed after it
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.calc(), BY_HAND)

    def test_fork_from_the_older_session_says_the_run_starts_without_the_later_changes(self):
        dest = Path(self.tmp.name + "-run")
        try:
            code, out, err = cli("fork", "0", "--name", "retry", "--session", "aaaaaaaa", "--dir", str(dest))
            self.assertEqual(code, 0, out + err)
            self.assertIn("WARNING  1 file(s) changed after the steps this run starts before", out)
            self.assertIn("calc.py: changed by session bbbbbbbb step 1", out)
            self.assertEqual(self.calc(), BY_B)                   # the source keeps its files
            first = log.read(dest / ".rewindagents" / "log.jsonl")[0]
            self.assertEqual(first["args"]["fork"]["drift"][0]["path"], "calc.py")
        finally:
            import shutil
            shutil.rmtree(dest, ignore_errors=True)


class TestBash(DriftCase):
    def test_a_file_a_command_changed_then_edited_by_hand_is_caught(self):
        self.a.bash("sed -i s/add/plus/ calc.py",
                    lambda cwd: (cwd / "calc.py").write_text(BY_A.replace("add", "plus"), newline=""))
        post = [r for r in log.read(self.log) if r["event"] == "post"][-1]
        self.assertEqual([x["path"] for x in post["args"]["after"]], [str(self.root / "calc.py")])
        (self.root / "calc.py").write_text("# mine\n", newline="")
        p = rewind.plan(self.log, 1)
        self.assertEqual([(rewind.relative(d["path"], self.root), d["outside"]) for d in p["drift"]],
                         [("calc.py", True)])
        with self.assertRaises(rewind.DriftError):
            rewind.rewind(self.log, 1)
        self.assertEqual(self.calc(), "# mine\n")

    def test_a_hand_edit_between_two_steps_of_the_same_session_is_caught(self):
        (self.root / "calc.py").write_text(BY_HAND, newline="")
        self.a.write("calc.py", BY_B)                            # the agent edits on top of the hand edit
        p = rewind.plan(self.log, 0)
        self.assertEqual(len(p["drift"]), 1)
        self.assertTrue(p["drift"][0]["outside"])
        self.assertEqual(p["drift"][0]["sessions"], [])

    def test_no_drift_no_refusal(self):
        p = rewind.rewind(self.log, 0)
        self.assertEqual(p["drift"], [])
        self.assertEqual(self.calc(), ORIGINAL)


if __name__ == "__main__":
    unittest.main()
