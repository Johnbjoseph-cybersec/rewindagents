"""One log per project, from any directory; session ids by prefix; what one step changed; errors without tracebacks.

First-run journal (ux-review/FIRST_RUN.md): after the agent ran `cd sub`, its next step went into
sub/.rewindagents/ and vanished from `replay` at the project root; `replay` from a subdirectory said "no log";
`replay --session nope` printed nothing and exited 0; `bundle --out` to a bad path printed a traceback."""
import os
import subprocess
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_rewind import Agent, cli  # noqa: E402

from rewindagents import hook, project, sessions  # noqa: E402


@contextmanager
def inside(d):
    old = os.getcwd()
    os.chdir(d)
    try:
        yield
    finally:
        os.chdir(old)


def git_init(d: Path):
    subprocess.run(["git", "init", "-q", str(d)], check=True)


class TestFindRoot(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.d = Path(self.tmp.name).resolve()
        self.home = self.d / "home"
        self.proj = self.home / "proj"
        (self.proj / "src" / "deep").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_nearest_parent_with_a_store_wins(self):
        (self.proj / ".rewindagents").mkdir()
        self.assertEqual(project.find_store_root(self.proj / "src" / "deep", self.home), self.proj)
        self.assertEqual(project.root_for(self.proj / "src" / "deep", env={}, home=self.home), self.proj)

    def test_walk_stops_at_the_repository_root(self):
        (self.home / ".rewindagents").mkdir()
        git_init(self.proj)
        self.assertIsNone(project.find_store_root(self.proj / "src", self.d / "elsewhere"))

    def test_never_adopts_the_home_store_from_below(self):
        (self.home / ".rewindagents").mkdir()
        self.assertIsNone(project.find_store_root(self.proj / "src", self.home))
        self.assertEqual(project.find_store_root(self.home, self.home), self.home)   # unless started there

    def test_claude_project_dir_when_nothing_recorded_yet(self):
        env = {"CLAUDE_PROJECT_DIR": str(self.proj)}
        self.assertEqual(project.root_for(self.proj / "src", env=env, home=self.home), self.proj)
        other = self.d / "other"
        other.mkdir()
        self.assertEqual(project.root_for(other, env=env, home=self.home), other)    # not inside it: cwd
        self.assertEqual(project.root_for(self.proj / "src", env={}, home=self.home), self.proj / "src")


class TestHookFromASubdirectory(unittest.TestCase):
    def test_a_step_after_cd_lands_in_the_project_log_and_rewinds(self):
        with TemporaryDirectory() as d:
            d = Path(d).resolve()
            Agent(d).write("a.txt", "1")                        # step 1, at the root: creates the store
            (d / "sub").mkdir()
            sub = Agent(d / "sub")
            sub.write("b.txt", "2")                             # step 2: the agent ran `cd sub` first
            sub.bash("rm ../a.txt", lambda cwd: (cwd / ".." / "a.txt").unlink())   # step 3, from sub
            self.assertFalse((d / "sub" / ".rewindagents").exists())
            with inside(d / "sub"):
                code, out, err = cli("replay")
                self.assertEqual(code, 0, err)
                self.assertEqual([l.split()[1] for l in out.splitlines()], ["Write", "Write", "Bash"])
                self.assertIn("sub/b.txt", out)
                code, out, err = cli("rewind", "1")
                self.assertEqual(code, 0, err + out)
            self.assertEqual((d / "a.txt").read_text(), "1")   # the Bash step's scan covered the whole project
            self.assertFalse((d / "sub" / "b.txt").exists())

    def test_hook_process_uses_claude_project_dir(self):
        with TemporaryDirectory() as d:
            d = Path(d).resolve()
            (d / "sub").mkdir()
            old = os.environ.get("CLAUDE_PROJECT_DIR")
            os.environ["CLAUDE_PROJECT_DIR"] = str(d)
            try:
                Agent(d / "sub").write("x.txt", "x")
            finally:
                if old is None:
                    del os.environ["CLAUDE_PROJECT_DIR"]
                else:
                    os.environ["CLAUDE_PROJECT_DIR"] = old
            self.assertTrue((d / ".rewindagents" / "log.jsonl").is_file())
            self.assertFalse((d / "sub" / ".rewindagents").exists())


class TestCliFromAnywhere(unittest.TestCase):
    def test_status_from_a_subdirectory_names_the_project(self):
        with TemporaryDirectory() as d:
            d = Path(d).resolve()
            Agent(d).write("a.txt", "1")
            (d / "sub").mkdir()
            with inside(d / "sub"):
                code, out, _ = cli("status")
            self.assertEqual(code, 0)
            self.assertIn(f"project: {d}", out)
            self.assertIn("2 records", out)

    def test_no_log_anywhere_says_what_to_do(self):
        with TemporaryDirectory() as d, inside(d):
            code, _, err = cli("replay")
        self.assertEqual(code, 2)
        self.assertIn("here or in a parent directory", err)
        self.assertIn("init", err)

    def test_explicit_log_is_taken_as_given(self):
        with TemporaryDirectory() as d:
            code, _, err = cli("--log", str(Path(d, "none.jsonl")), "replay")
        self.assertEqual(code, 2)
        self.assertNotIn("parent", err)

    def test_unwritable_out_is_one_line_not_a_traceback(self):
        with TemporaryDirectory() as d:
            d = Path(d).resolve()
            Agent(d).write("a.txt", "1")
            (d / "blocker").write_text("a file, not a directory", newline="")
            code, out, err = cli("--log", str(d / ".rewindagents/log.jsonl"), "bundle", "--out", str(d / "blocker/x.bundle"))
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith("rewindagents: "), err)
        self.assertNotIn("Traceback", err)
        self.assertEqual(len(err.strip().splitlines()), 1)


class TestSessionIds(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.d = Path(self.tmp.name).resolve()
        Agent(self.d, "8f3c2a91-77d4-4b0e-9a1c-2f6d5e4b3a10").write("a.txt", "1")
        Agent(self.d, "8f3d0000-0000-0000-0000-000000000000").write("b.txt", "1")
        Agent(self.d, "c0ffee00-0000-0000-0000-000000000000").write("c.txt", "1")
        self.log = str(self.d / ".rewindagents/log.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_unique_prefix_names_the_session(self):
        self.assertEqual(sessions.resolve(self.log, "8f3c"), "8f3c2a91-77d4-4b0e-9a1c-2f6d5e4b3a10")
        code, out, err = cli("--log", self.log, "replay", "--session", "8f3c")
        self.assertEqual(code, 0, err)
        self.assertIn("a.txt", out)
        self.assertNotIn("c.txt", out)

    def test_ambiguous_prefix_lists_the_candidates(self):
        code, out, err = cli("--log", self.log, "rewind", "0", "--session", "8f3")
        self.assertEqual(code, 1)
        self.assertIn("ambiguous", err)
        self.assertIn("8f3c2a91", err)
        self.assertIn("8f3d0000", err)
        self.assertTrue((self.d / "a.txt").exists())       # nothing rewound

    def test_unknown_session_is_an_error_that_lists_sessions(self):
        for cmd in (["replay"], ["diff", "0"], ["export"], ["show"]):
            code, out, err = cli("--log", self.log, *cmd, "--session", "nope")
            self.assertEqual(code, 1, cmd)
            self.assertIn("no session 'nope'", err)
            self.assertIn("c0ffee00-0000-0000-0000-000000000000 (latest)", err)
            self.assertEqual(out, "", cmd)


class TestStepDiff(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.d = Path(self.tmp.name).resolve()
        a = Agent(self.d)
        a.write("app.py", "a\nb\n")                                             # 1 created
        a.write("app.py", "a\nB\n")                                             # 2 changed
        a.bash("rm app.py", lambda cwd: (cwd / "app.py").unlink())              # 3 deleted
        a.bash("ls")                                                            # 4 nothing
        self.log = str(self.d / ".rewindagents/log.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def step(self, n):
        return cli("--log", self.log, "replay", "--step", str(n), "--diff")

    def test_each_kind_with_its_own_diff(self):
        code, out, _ = self.step(1)
        self.assertEqual(code, 0)
        self.assertIn("  created   app.py", out)
        self.assertIn("new file mode", out)
        code, out, _ = self.step(2)
        self.assertIn("  changed   app.py", out)
        self.assertIn("-b\n+B\n", out)
        self.assertNotIn("+a", out)              # only this step's change, not the session's
        code, out, _ = self.step(3)
        self.assertIn("  deleted   app.py", out)
        self.assertIn("+++ /dev/null", out)
        code, out, _ = self.step(4)
        self.assertEqual(code, 0)
        self.assertIn("no file changes recorded: it changed no file", out)

    def test_reverse_applying_a_step_diff_undoes_exactly_that_step(self):
        _, out, _ = self.step(2)
        patch = out[out.index("diff --git"):]
        work = self.d / "w"
        work.mkdir()
        (work / "app.py").write_text("a\nB\n", newline="")
        # The patch goes in as bytes: a text-mode pipe on Windows writes every \n as \r\n, and git then
        # finds no matching context. core.autocrlf=false: Git for Windows is installed with it on, and
        # git apply would then write the patched files with \r\n.
        r = subprocess.run(["git", "-c", "core.autocrlf=false", "apply", "-R", "-"], input=patch.encode("utf-8"),
                           cwd=work, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
        self.assertEqual((work / "app.py").read_text(), "a\nb\n")

    def test_diff_needs_a_step(self):
        code, _, err = cli("--log", self.log, "replay", "--diff")
        self.assertEqual(code, 2)
        self.assertIn("--step", err)


if __name__ == "__main__":
    unittest.main()
