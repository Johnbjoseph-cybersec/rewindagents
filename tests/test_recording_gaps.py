"""Two recording gaps found in real Claude Code sessions (ux-review/DOGFOOD.md, F5 and F11): Python bytecode
reported as changes in a git repo, and a failing shell command whose changes were never checkpointed."""
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from rewindagents import agents, bashscan, hook, rewind  # noqa: E402
from test_rewind import Agent, git  # noqa: E402


def git_repo(d):
    git(d, "init", "-q")
    git(d, "config", "user.email", "t@t")
    git(d, "config", "user.name", "t")


class TestBytecodeIsNotAChange(unittest.TestCase):
    """F5: in a git repo whose .gitignore does not name __pycache__, every python run showed .pyc changes."""

    def test_untracked_pycache_is_not_scanned_but_a_tracked_file_there_still_is(self):
        with TemporaryDirectory() as d:
            d = Path(d)
            git_repo(d)
            (d / "app.py").write_text("x = 1\n")
            (d / "vendor" / "__pycache__").mkdir(parents=True)
            (d / "vendor" / "__pycache__" / "kept.txt").write_text("tracked on purpose\n")
            git(d, "add", "-A")
            (d / "__pycache__").mkdir()
            (d / "__pycache__" / "app.cpython-315.pyc").write_bytes(b"\x00pyc")
            files = bashscan.project_files(d, ignored_files=True)
            self.assertIn("app.py", files)
            self.assertIn("vendor/__pycache__/kept.txt", files)
            self.assertNotIn("__pycache__/app.cpython-315.pyc", files)
            a = Agent(d)
            a.bash("python app.py", lambda c: (c / "__pycache__" / "app.cpython-315.pyc").write_bytes(b"\x00new"))
            self.assertEqual(rewind.steps(a.log)[0]["checkpoints"], [])


class TestFailedCommandIsCheckpointed(unittest.TestCase):
    """F11: Claude Code sends a failed call (a command exiting non-zero) to PostToolUseFailure, not PostToolUse.
    The hook was not installed there, so the after-scan never ran and what the command changed was lost."""

    def test_init_installs_on_the_failure_event(self):
        with TemporaryDirectory() as d:
            f = Path(d) / ".claude/settings.json"
            hook.install(f, agent="claude")
            self.assertIn("PostToolUseFailure", agents.commands_in(agents.AGENTS["claude"], f))

    def test_a_failing_command_is_rewound(self):
        with TemporaryDirectory() as d:
            d = Path(d)
            (d / "notes.txt").write_text("keep me\n")
            a = Agent(d)
            inp = {"command": "rm notes.txt && ls does-not-exist"}
            hook.handle(a._p("PreToolUse", "Bash", inp))
            (d / "notes.txt").unlink()
            hook.handle({"session_id": "s1", "cwd": str(d), "hook_event_name": "PostToolUseFailure",
                         "tool_name": "Bash", "tool_input": inp, "error": "Exit code 1"})
            st = rewind.steps(a.log)
            self.assertEqual(st[0]["bash_scan"], {"changed": 1})
            rewind.rewind(a.log, 0)
            self.assertEqual((d / "notes.txt").read_text(), "keep me\n")


if __name__ == "__main__":
    unittest.main()
