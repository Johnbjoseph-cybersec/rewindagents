import hashlib
import io
import json
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from rewindagent import hook, read, rewind, verify  # noqa: E402
from rewindagent.cli import main  # noqa: E402


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

    def bash(self, command, action=None, post=True):
        """Pre hook, then `action` (the command's effect on the files), then the post hook."""
        inp = {"command": command}
        hook.handle(self._p("PreToolUse", "Bash", inp))
        if action:
            action(self.cwd)
        if post:
            hook.handle(self._p("PostToolUse", "Bash", inp, {"stdout": ""}))

    @property
    def log(self):
        return self.cwd / ".rewindagent" / "log.jsonl"


def cli(*args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(list(args))
    return code, out.getvalue(), err.getvalue()


class TestSteps(unittest.TestCase):
    def test_pre_and_post_pair_into_numbered_steps(self):
        with TemporaryDirectory() as d:
            a = Agent(d)
            a.write("app.py", "v1")
            a.bash("pytest")
            got = rewind.steps(a.log)
            self.assertEqual([(s["step"], s["tool"]) for s in got], [(1, "Write"), (2, "Bash")])
            self.assertEqual(got[0]["result"], {"ok": True})
            self.assertEqual(got[1]["result"], {"stdout": ""})
            self.assertEqual(rewind.summary(got[1]), "pytest")

    def test_default_session_is_the_latest_and_sessions_number_separately(self):
        with TemporaryDirectory() as d:
            Agent(d, "old").write("a.txt", "1")
            Agent(d, "new").bash("ls")
            self.assertEqual([s["tool"] for s in rewind.steps(Agent(d).log)], ["Bash"])
            self.assertEqual([s["tool"] for s in rewind.steps(Agent(d).log, "old")], ["Write"])


class TestRewind(unittest.TestCase):
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

    def test_rewind_to_step_restores_the_files_as_they_were_after_it(self):
        p = rewind.rewind(self.a.log, 2)
        self.assertEqual((self.d / "app.py").read_text(), "v2")
        self.assertFalse((self.d / "new.py").exists())
        self.assertEqual(p["cannot"], [])

    def test_rewind_to_zero_undoes_the_whole_session(self):
        rewind.rewind(self.a.log, 0)
        self.assertFalse((self.d / "app.py").exists())   # app.py did not exist before step 1
        self.assertFalse((self.d / "new.py").exists())

    def test_rewind_can_itself_be_rewound(self):
        rewind.rewind(self.a.log, 1)
        self.assertEqual((self.d / "app.py").read_text(), "v1")
        rw_step = len(rewind.steps(self.a.log))
        self.assertEqual(rw_step, 5)
        rewind.rewind(self.a.log, rw_step - 1)          # undo the rewind
        self.assertEqual((self.d / "app.py").read_text(), "wrecked")
        self.assertEqual((self.d / "new.py").read_text(), "junk")
        self.assertTrue(verify(self.a.log)[0])

    def test_dry_run_changes_nothing_and_records_nothing(self):
        before = self.a.log.read_text()
        p = rewind.rewind(self.a.log, 1, dry_run=True)
        self.assertEqual((self.d / "app.py").read_text(), "wrecked")
        self.assertEqual(self.a.log.read_text(), before)
        self.assertEqual([Path(x).name for x, _ in p["restore"]], ["app.py"])
        self.assertEqual([Path(x).name for x in p["delete"]], ["new.py"])

    def test_already_matching_file_is_left_alone(self):
        p = rewind.rewind(self.a.log, 4)
        self.assertEqual((p["restore"], p["delete"]), ([], []))

    def test_tampered_log_is_refused_and_nothing_changes(self):
        lines = self.a.log.read_text().splitlines()
        rec = json.loads(lines[0])
        rec["tool"] = "Edit"
        lines[0] = json.dumps(rec, sort_keys=True)
        self.a.log.write_text("\n".join(lines) + "\n")
        with self.assertRaises(rewind.RewindError):
            rewind.rewind(self.a.log, 1)
        self.assertEqual((self.d / "app.py").read_text(), "wrecked")

    def test_altered_stored_copy_is_not_written_back(self):
        sha = hashlib.sha256(b"v1").hexdigest()
        (self.d / ".rewindagent" / "objects" / sha).write_bytes(b"evil")
        p = rewind.rewind(self.a.log, 1)
        self.assertEqual(p["cannot"], [(str(self.d / "app.py"), "stored copy missing or altered")])
        self.assertEqual((self.d / "app.py").read_text(), "wrecked")
        self.assertFalse((self.d / "new.py").exists())   # the rest of the rewind still happens

    def test_out_of_range_step_is_an_error(self):
        for n in (-1, 5):
            with self.assertRaises(rewind.RewindError):
                rewind.rewind(self.a.log, n)


class TestLimits(unittest.TestCase):
    def test_file_outside_the_project_is_never_touched(self):
        with TemporaryDirectory() as d, TemporaryDirectory() as other:
            outside = Path(other, "x.txt")
            outside.write_text("before")
            a = Agent(d)
            hook.handle(a._p("PreToolUse", "Write", {"file_path": str(outside)}))
            outside.write_text("after")
            p = rewind.rewind(a.log, 0)
            self.assertEqual(p["cannot"], [(str(outside), "outside the project")])
            self.assertEqual(outside.read_text(), "after")

    def test_bash_steps_without_a_finished_scan_are_counted(self):
        with TemporaryDirectory() as d:
            a = Agent(d)
            a.write("f.txt", "1")
            a.bash("sed -i '' s/1/2/ f.txt")             # scanned before and after
            a.bash("rm -rf build", post=False)           # no PostToolUse arrived
            self.assertEqual(rewind.rewind(a.log, 1, dry_run=True)["bash_uncovered"], 1)


def git(cwd, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@t")
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                          check=True, env=env).stdout.strip()


class TestBranch(unittest.TestCase):
    def test_git_branch_keeps_the_current_files_without_touching_head_or_index(self):
        with TemporaryDirectory() as d:
            git(d, "init", "-q")
            Path(d, "app.py").write_text("committed")
            git(d, "add", "app.py")
            git(d, "commit", "-qm", "init")
            head, status = git(d, "rev-parse", "HEAD"), git(d, "status", "--porcelain")
            a = Agent(d)
            a.write("app.py", "attempt-1")
            a.write("extra.py", "attempt-1 extra")
            p = rewind.branch(a.log, 0, "try1")
            self.assertEqual(Path(d, "app.py").read_text(), "committed")
            self.assertFalse(Path(d, "extra.py").exists())
            self.assertEqual(git(d, "show", "rewindagent/try1:app.py"), "attempt-1")
            self.assertEqual(git(d, "show", "rewindagent/try1:extra.py"), "attempt-1 extra")
            self.assertEqual(git(d, "rev-parse", "HEAD"), head)
            self.assertEqual(git(d, "status", "--porcelain"), status)
            self.assertEqual(git(d, "rev-parse", "rewindagent/try1^"), head)
            self.assertNotIn(".rewindagent/log.jsonl", git(d, "ls-tree", "-r", "--name-only", "rewindagent/try1"))
            self.assertEqual(p["branch"]["git_ref"], "rewindagent/try1")
            with self.assertRaises(rewind.RewindError):     # same name twice is refused
                rewind.branch(a.log, 0, "try1")

    def test_branch_outside_git_still_rewinds_and_is_undoable(self):
        with TemporaryDirectory() as d:
            a = Agent(d)
            a.write("app.py", "v1")
            a.write("app.py", "v2")
            p = rewind.branch(a.log, 1, "retry")
            self.assertIsNone(p["branch"]["git_ref"])
            self.assertEqual(Path(d, "app.py").read_text(), "v1")
            rewind.rewind(a.log, 2)
            self.assertEqual(Path(d, "app.py").read_text(), "v2")


class TestCli(unittest.TestCase):
    def test_replay_lists_steps_and_shows_one(self):
        with TemporaryDirectory() as d:
            a = Agent(d)
            a.write("app.py", "v1")
            a.bash("pytest -q")
            code, out, _ = cli("--log", str(a.log), "replay")
            self.assertEqual(code, 0)
            lines = out.splitlines()
            self.assertEqual(len(lines), 2)
            self.assertIn("Write", lines[0])
            self.assertIn("[1 checkpointed]", lines[0])
            self.assertIn("  app.py  ", lines[0])          # shown relative to the project
            self.assertNotIn(str(Path(d).resolve()), out)
            self.assertIn("pytest -q", lines[1])
            code, out, _ = cli("--log", str(a.log), "replay", "--step", "2")
            self.assertEqual(json.loads(out)["input"], {"command": "pytest -q"})
            self.assertEqual(cli("--log", str(a.log), "replay", "--step", "9")[0], 2)

    def test_wrecked_project_restored_in_one_command_from_its_own_directory(self):
        with TemporaryDirectory() as d:
            a = Agent(d)
            a.write("app.py", "good")
            a.write("app.py", "broken")
            a.write("junk.py", "x")
            env = dict(os.environ, PYTHONPATH=str(SRC))
            p = subprocess.run([sys.executable, "-m", "rewindagent", "rewind", "1"], cwd=d, env=env,
                               capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(Path(d, "app.py").read_text(), "good")
            self.assertFalse(Path(d, "junk.py").exists())
            self.assertIn("undo it with: python3 -m rewindagent rewind 3 --session s1", p.stdout)

    def test_rewind_cli_exit_codes(self):
        with TemporaryDirectory() as d:
            a = Agent(d)
            a.write("app.py", "v1")
            self.assertEqual(cli("--log", str(a.log), "rewind", "7")[0], 1)
            self.assertEqual(cli("--log", str(Path(d, "none.jsonl")), "rewind", "0")[0], 2)
            code, out, _ = cli("--log", str(a.log), "rewind", "0", "--dry-run")
            self.assertEqual(code, 0)
            self.assertIn("would change 1 files", out)
            self.assertTrue(Path(d, "app.py").exists())

    def test_rewind_cli_exits_1_when_a_file_cannot_be_restored(self):
        with TemporaryDirectory() as d:
            a = Agent(d)
            a.write("app.py", "v1")
            a.write("app.py", "v2")
            (Path(d, ".rewindagent", "objects") / hashlib.sha256(b"v1").hexdigest()).write_bytes(b"x")
            code, out, _ = cli("--log", str(a.log), "rewind", "1")
            self.assertEqual(code, 1)
            self.assertIn("CANNOT", out)
            self.assertEqual(Path(d, "app.py").read_text(), "v2")


if __name__ == "__main__":
    unittest.main()
