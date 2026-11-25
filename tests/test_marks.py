"""Marks: bookmarks in time. `mark NAME` labels the current point; `rewind-to NAME` jumps back to it with
every `rewind` safety check; `marks`/`unmark` manage them. Proven through the real hook."""
import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from rewindagents import hook, marks, verify  # noqa: E402
from rewindagents.cli import main  # noqa: E402


class Agent:
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

    @property
    def log(self):
        return self.cwd / ".rewindagents" / "log.jsonl"


def cli(*args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(list(args))
    return code, out.getvalue(), err.getvalue()


class TestMarks(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.a = Agent(self.d)
        self.a.write("app.py", "safe")      # step 1

    def tearDown(self):
        self.tmp.cleanup()

    def L(self):
        return ("--log", str(self.a.log))

    def test_mark_then_rewind_to_returns_to_the_marked_state(self):
        code, out, _ = cli(*self.L(), "mark", "before-refactor")
        self.assertEqual(code, 0)
        self.assertIn("rewind-to before-refactor", out)
        self.a.write("app.py", "refactored-and-broken")   # step 2: the risky work
        self.a.write("extra.py", "junk")                  # step 3
        code, out, _ = cli(*self.L(), "rewind-to", "before-refactor")
        self.assertEqual(code, 0)
        self.assertEqual((self.d / "app.py").read_text(), "safe")
        self.assertFalse((self.d / "extra.py").exists())

    def test_mark_captures_a_fixed_step_that_later_work_does_not_move(self):
        cli(*self.L(), "mark", "here")
        m = marks.get(self.a.log, "here")
        self.assertEqual(m["step"], 1)
        self.a.write("app.py", "more")
        self.a.write("app.py", "yet more")
        self.assertEqual(marks.get(self.a.log, "here")["step"], 1)   # unchanged by new steps

    def test_marks_lists_and_unmark_removes(self):
        cli(*self.L(), "mark", "one")
        cli(*self.L(), "mark", "two")
        code, out, _ = cli(*self.L(), "marks")
        self.assertEqual(code, 0)
        self.assertIn("one", out)
        self.assertIn("two", out)
        code, _, _ = cli(*self.L(), "unmark", "one")
        self.assertEqual(code, 0)
        _, out, _ = cli(*self.L(), "marks")
        self.assertNotIn("one ", out)
        self.assertIn("two", out)

    def test_rewind_to_unknown_mark_exits_two_and_lists_marks(self):
        cli(*self.L(), "mark", "real")
        code, _, err = cli(*self.L(), "rewind-to", "typo")
        self.assertEqual(code, 2)
        self.assertIn("no mark named 'typo'", err)
        self.assertIn("real", err)

    def test_a_bare_number_is_rejected_as_a_mark_name(self):
        code, _, err = cli(*self.L(), "mark", "3")
        self.assertEqual(code, 2)
        self.assertIn("not a usable mark name", err)

    def test_rewind_to_then_redo_reverses_the_jump(self):
        cli(*self.L(), "mark", "pin")
        self.a.write("app.py", "changed")
        cli(*self.L(), "rewind-to", "pin")
        self.assertEqual((self.d / "app.py").read_text(), "safe")
        code, _, _ = cli(*self.L(), "redo")
        self.assertEqual(code, 0)
        self.assertEqual((self.d / "app.py").read_text(), "changed")
        self.assertTrue(verify(self.a.log)[0])

    def test_rewind_to_refuses_over_a_hand_edit(self):
        cli(*self.L(), "mark", "pin")
        self.a.write("app.py", "agent-change")
        (self.d / "app.py").write_text("my own edit")      # human edits after the agent
        code, _, err = cli(*self.L(), "rewind-to", "pin")
        self.assertEqual(code, 1)
        self.assertIn("refused", err)
        self.assertEqual((self.d / "app.py").read_text(), "my own edit")

    def test_mark_with_nothing_recorded_exits_two(self):
        with TemporaryDirectory() as d:
            log = Path(d) / ".rewindagents" / "log.jsonl"
            log.parent.mkdir(parents=True)
            log.write_text("")
            code, _, err = cli("--log", str(log), "mark", "x")
            self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
