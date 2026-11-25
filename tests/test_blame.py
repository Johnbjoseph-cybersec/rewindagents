"""`blame FILE[:LINE]`: which recorded step wrote each line, through the real hook."""
import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from rewindagents import blame, hook  # noqa: E402
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

    def bash(self, command, action):
        inp = {"command": command}
        hook.handle(self._p("PreToolUse", "Bash", inp))
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


def who(log, path):
    # write_text() writes "\r\n" on Windows; the attribution is what is tested, not the line ending
    return [(n, t.rstrip("\r\n")) for n, t in blame.blame(log, path)["lines"]]


class TestBlame(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.a = Agent(self.d)

    def tearDown(self):
        self.tmp.cleanup()

    def f(self, name="app.py"):
        return str(self.d / name)

    def test_lines_are_credited_to_the_step_that_wrote_them(self):
        self.a.write("app.py", "a\nb\n")                     # step 1
        self.a.write("app.py", "a\nB\nc\n")                  # step 2
        self.assertEqual(who(self.a.log, self.f()), [(1, "a"), (2, "B"), (2, "c")])

    def test_lines_there_before_the_session_are_before(self):
        (self.d / "app.py").write_text("x\ny\n")
        self.a.write("app.py", "x\nY\n")                     # step 1
        self.assertEqual(who(self.a.log, self.f()), [(blame.BEFORE, "x"), (1, "Y")])

    def test_a_bash_edit_is_credited_to_the_bash_step(self):
        self.a.write("app.py", "one\ntwo\n")                 # step 1
        self.a.bash("sed -i s/two/TWO/ app.py", lambda d: (d / "app.py").write_text("one\nTWO\n"))   # step 2
        self.assertEqual(who(self.a.log, self.f()), [(1, "one"), (2, "TWO")])

    def test_a_line_changed_after_the_agent_is_by_hand(self):
        self.a.write("app.py", "a\n")                        # step 1
        with open(self.d / "app.py", "a") as fh:
            fh.write("mine\n")
        self.assertEqual(who(self.a.log, self.f()), [(1, "a"), (blame.HAND, "mine")])

    def test_undo_keeps_the_original_authors(self):
        self.a.write("app.py", "a\nb\n")                     # step 1
        self.a.write("app.py", "a\nWRECK\n")                 # step 2
        self.assertEqual(cli("--log", str(self.a.log), "undo")[0], 0)   # step 3: back to step 1's bytes
        self.assertEqual(who(self.a.log, self.f()), [(1, "a"), (1, "b")])

    def test_cli_file_line_explains_and_gives_revert(self):
        self.a.write("app.py", "a\nb\n")
        self.a.write("app.py", "a\nBUG\n")
        code, out, _ = cli("--log", str(self.a.log), "blame", self.f() + ":2")
        self.assertEqual(code, 0)
        self.assertIn("BUG", out)
        self.assertIn("step 2", out)
        self.assertIn("revert 2", out)
        self.assertIn("replay --step 2 --diff", out)

    def test_cli_whole_file_listing(self):
        self.a.write("app.py", "a\nb\n")
        code, out, _ = cli("--log", str(self.a.log), "blame", self.f())
        self.assertEqual(code, 0)
        self.assertIn("step 1", out)
        self.assertIn("| a", out)

    def test_cli_line_out_of_range_exits_two(self):
        self.a.write("app.py", "a\n")
        self.assertEqual(cli("--log", str(self.a.log), "blame", self.f() + ":9")[0], 2)

    def test_untouched_or_deleted_file_exits_one(self):
        self.a.write("app.py", "a\n")
        self.assertEqual(cli("--log", str(self.a.log), "blame", self.f("never.py"))[0], 1)
        self.a.bash("rm app.py", lambda d: (d / "app.py").unlink())
        self.assertEqual(cli("--log", str(self.a.log), "blame", self.f())[0], 1)

    def test_binary_file_is_refused(self):
        self.a.write("data.bin", "ok")
        (self.d / "data.bin").write_bytes(b"\x00\x01")
        self.a.bash("touch", lambda d: (d / "data.bin").write_bytes(b"\x00\x02"))
        code, _, err = cli("--log", str(self.a.log), "blame", self.f("data.bin"))
        self.assertEqual(code, 1)
        self.assertIn("not text", err)


if __name__ == "__main__":
    unittest.main()
