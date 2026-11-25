"""`history FILE`: one file's timeline -- created / modified / deleted, by step, in order."""
import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from rewindagents import history, hook  # noqa: E402
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


class TestHistory(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.a = Agent(self.d)
        self.a.write("app.py", "v1")                                   # step 1: created
        self.a.write("other.py", "x")                                  # step 2: unrelated
        self.a.write("app.py", "v2")                                   # step 3: modified
        self.a.bash("rm app.py", action=lambda d: (d / "app.py").unlink())   # step 4: deleted

    def tearDown(self):
        self.tmp.cleanup()

    def test_history_lists_create_modify_delete_in_order(self):
        rows, target = history.file_history(self.a.log, str(self.d / "app.py"))
        self.assertEqual(target, str((self.d / "app.py").resolve()))
        self.assertEqual([(r["step"], r["change"]) for r in rows],
                         [(1, "created"), (3, "modified"), (4, "deleted")])

    def test_unrelated_file_is_not_in_another_files_history(self):
        rows, _ = history.file_history(self.a.log, str(self.d / "other.py"))
        self.assertEqual([(r["step"], r["change"]) for r in rows], [(2, "created")])

    def test_cli_history_prints_the_timeline_and_a_restore_hint(self):
        code, out, _ = cli("--log", str(self.a.log), "history", str(self.d / "app.py"))
        self.assertEqual(code, 0)
        self.assertIn("created", out)
        self.assertIn("deleted", out)
        self.assertIn("--only", out)       # tells the user how to put a version back

    def test_cli_history_of_untouched_file_exits_one(self):
        code, _, _ = cli("--log", str(self.a.log), "history", str(self.d / "never.py"))
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
