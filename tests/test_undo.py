"""`undo` / `redo`: the no-step-numbers front door over rewind. These prove the thing a panicking user
needs -- `undo` takes back the agent's last change, `undo N` the last N, repeated `undo` walks back through
the agent's work (never flip-flops with its own records), a Read/test-run in between is skipped, `redo`
reverses it, and a hand edit is protected."""
import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from rewindagents import hook, rewind, verify  # noqa: E402
from rewindagents.cli import main  # noqa: E402


class Agent:
    """Drives the real hook the way Claude Code does: pre record, the change, post record."""

    def __init__(self, cwd, session="s1"):
        self.cwd, self.session = Path(cwd), session

    def _p(self, event, tool, tool_input, response=None):
        p = {"session_id": self.session, "cwd": str(self.cwd), "hook_event_name": event,
             "tool_name": tool, "tool_input": tool_input}
        if response is not None:
            p["tool_response"] = response
        return p

    def write(self, name, text):
        inp = {"file_path": str(self.cwd / name), "content": text}
        hook.handle(self._p("PreToolUse", "Write", inp))
        (self.cwd / name).parent.mkdir(parents=True, exist_ok=True)
        (self.cwd / name).write_text(text)
        hook.handle(self._p("PostToolUse", "Write", inp, {"ok": True}))

    def bash(self, command, action=None):
        inp = {"command": command}
        hook.handle(self._p("PreToolUse", "Bash", inp))
        if action:
            action(self.cwd)
        hook.handle(self._p("PostToolUse", "Bash", inp, {"stdout": ""}))

    @property
    def log(self):
        return self.cwd / ".rewindagents" / "log.jsonl"


def cli(*args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(list(args))
    return code, out.getvalue(), err.getvalue()


class TestUndo(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.a = Agent(self.d)
        self.a.write("app.py", "v1")        # step 1
        self.a.write("app.py", "v2")        # step 2
        self.a.write("new.py", "junk")      # step 3: creates a file
        self.a.write("app.py", "wrecked")   # step 4

    def tearDown(self):
        self.tmp.cleanup()

    def _log_args(self):
        # every cli() call must point at this project's log (there is no cwd-based discovery in the test)
        return ("--log", str(self.a.log))

    def undo(self, *extra):
        return cli(*self._log_args(), "undo", *extra)

    def redo(self, *extra):
        return cli(*self._log_args(), "redo", *extra)

    def test_bare_undo_takes_back_the_last_change(self):
        code, out, _ = self.undo()
        self.assertEqual(code, 0)
        self.assertEqual((self.d / "app.py").read_text(), "v2")   # step 4's wreck is gone
        self.assertTrue((self.d / "new.py").exists())             # step 3 is untouched
        self.assertIn("reverse this with:", out)                  # the reverse is advertised
        self.assertTrue(verify(self.a.log)[0])

    def test_undo_n_takes_back_the_last_n_changes(self):
        code, _, _ = self.undo("2")
        self.assertEqual(code, 0)
        self.assertEqual((self.d / "app.py").read_text(), "v2")
        self.assertFalse((self.d / "new.py").exists())            # step 3 (new.py) also taken back

    def test_undo_all_returns_to_pristine(self):
        code, _, _ = self.undo("--all")
        self.assertEqual(code, 0)
        self.assertFalse((self.d / "app.py").exists())
        self.assertFalse((self.d / "new.py").exists())

    def test_repeated_undo_walks_back_and_never_flip_flops(self):
        self.undo()                                               # -> app.py v2, new.py present
        self.assertEqual((self.d / "app.py").read_text(), "v2")
        self.undo()                                               # -> takes back step 3, not the undo
        self.assertEqual((self.d / "app.py").read_text(), "v2")
        self.assertFalse((self.d / "new.py").exists())
        self.undo()                                               # -> app.py v1
        self.assertEqual((self.d / "app.py").read_text(), "v1")
        self.undo()                                               # -> pristine
        self.assertFalse((self.d / "app.py").exists())
        code, _, err = self.undo()                                # -> nothing left
        self.assertEqual(code, 1)
        self.assertIn("nothing to undo", err)
        self.assertTrue(verify(self.a.log)[0])

    def test_undo_skips_a_step_that_changed_no_file(self):
        with TemporaryDirectory() as d:
            a = Agent(d)
            a.write("app.py", "good")       # step 1: a real change
            a.bash("pytest", action=None)   # step 2: runs, changes nothing -> no checkpoints
            code, _, _ = cli("--log", str(a.log), "undo")
            self.assertEqual(code, 0)
            self.assertFalse((Path(d) / "app.py").exists())   # undo reached past the test run to the write

    def test_redo_reverses_the_last_undo(self):
        self.undo()
        self.assertEqual((self.d / "app.py").read_text(), "v2")
        code, out, _ = self.redo()
        self.assertEqual(code, 0)
        self.assertEqual((self.d / "app.py").read_text(), "wrecked")
        self.assertTrue((self.d / "new.py").exists())
        self.assertTrue(verify(self.a.log)[0])

    def test_redo_with_nothing_to_redo_exits_one(self):
        code, _, err = self.redo()
        self.assertEqual(code, 1)
        self.assertIn("nothing to redo", err)

    def test_dry_run_changes_nothing(self):
        before = self.a.log.read_text()
        code, out, _ = self.undo("-n")
        self.assertEqual((self.d / "app.py").read_text(), "wrecked")
        self.assertEqual(self.a.log.read_text(), before)
        self.assertIn("preview", out)

    def test_undo_refuses_over_a_hand_edit_then_force_wins(self):
        (self.d / "app.py").write_text("mine")          # the human edits after the agent
        code, _, err = self.undo()
        self.assertEqual(code, 1)
        self.assertIn("refused", err)
        self.assertEqual((self.d / "app.py").read_text(), "mine")   # nothing was overwritten
        code, _, _ = self.undo("--force")
        self.assertEqual(code, 0)
        self.assertEqual((self.d / "app.py").read_text(), "v2")

    def test_only_restricts_to_one_file(self):
        # --only resolves against the process cwd (here the repo root), so pass the file's full path
        code, _, _ = self.undo("--all", "--only", str(self.d / "new.py"))
        self.assertEqual(code, 0)
        self.assertFalse((self.d / "new.py").exists())
        self.assertEqual((self.d / "app.py").read_text(), "wrecked")   # app.py left alone

    def test_nothing_recorded_yet_exits_one(self):
        with TemporaryDirectory() as d:
            log = Path(d) / ".rewindagents" / "log.jsonl"
            log.parent.mkdir(parents=True)
            log.write_text("")
            code, _, err = cli("--log", str(log), "undo")
            self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
