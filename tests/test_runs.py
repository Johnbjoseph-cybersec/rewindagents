"""fork + compare (runs.py): a recorded session forked at a step into a separate run that any agent continues,
then runs lined up against their shared starting point. Driven through the real hook (test_rewind.Agent)."""
import contextlib
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from rewindagents import bashscan, gc, log, rewind, runs  # noqa: E402
from test_rewind import Agent, cli, git  # noqa: E402


@contextlib.contextmanager
def cwd(path):
    old = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def files_of(d):
    """{relative path: bytes} of a directory, minus .git and .rewindagents."""
    out = {}
    for p in sorted(Path(d).rglob("*")):
        rel = p.relative_to(d)
        if p.is_file() and rel.parts[0] not in (".git", ".rewindagents"):
            out[str(rel)] = p.read_bytes()
    return out


class Session:
    """A git project with one commit, then a recorded session: step 1 adds div, step 2 adds a test file,
    step 3 is a Bash `rm` of the README, step 4 rewrites calc.py badly. Plus an uncommitted, unrecorded note."""

    def __init__(self, base, use_git=True):
        self.root = Path(base) / "proj"
        self.root.mkdir()
        (self.root / "calc.py").write_text("def add(a, b):\n    return a + b\n", newline="")
        (self.root / "README.md").write_text("calc\n", newline="")
        if use_git:
            git(self.root, "init", "-q")
            git(self.root, "add", ".")
            git(self.root, "commit", "-qm", "init")
        (self.root / "notes.txt").write_text("mine, untracked\n", newline="")
        self.agent = Agent(self.root, "sess-aaaa-1111")
        self.agent.write("calc.py", "def add(a, b):\n    return a + b\n\n\ndef div(a, b):\n    return a / b\n")
        self.agent.write("test_calc.py", "from calc import div\nassert div(4, 2) == 2\n")
        self.agent.bash("rm README.md", action=lambda c: (c / "README.md").unlink())
        self.agent.write("calc.py", "broken\n")
        self.log = self.agent.log


class TestFork(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_fork_holds_the_files_as_they_were_right_after_the_step_and_leaves_the_project_alone(self):
        s = Session(self.base)
        before = files_of(s.root)
        head_before = git(s.root, "rev-parse", "HEAD")
        status_before = git(s.root, "status", "--porcelain")
        d = runs.fork(s.log, 2, "try2")
        run = Path(d["dir"])
        self.assertEqual(run.resolve(), (self.base / "proj-try2").resolve())
        got = files_of(run)
        self.assertEqual(got["calc.py"], b"def add(a, b):\n    return a + b\n\n\ndef div(a, b):\n    return a / b\n")
        self.assertEqual(got["test_calc.py"], b"from calc import div\nassert div(4, 2) == 2\n")
        self.assertEqual(got["README.md"], b"calc\n")             # the Bash rm in step 3 is not in the run
        self.assertEqual(got["notes.txt"], b"mine, untracked\n")  # untracked work comes along
        # the source project: files, HEAD and index exactly as before; the fork is a branch, not a checkout
        self.assertEqual(files_of(s.root), before)
        self.assertEqual(git(s.root, "rev-parse", "HEAD"), head_before)
        self.assertEqual(git(s.root, "status", "--porcelain"), status_before)
        self.assertIn("rewindagents/run/try2", git(s.root, "branch", "--list", "rewindagents/run/*"))
        self.assertEqual(d["git_branch"], "rewindagents/run/try2")

    def test_the_run_has_its_own_verifying_log_that_names_where_it_came_from(self):
        s = Session(self.base)
        source_head = log.head(s.log)
        d = runs.fork(s.log, 2, "try2")
        run_log = Path(d["dir"]) / ".rewindagents" / "log.jsonl"
        self.assertTrue(log.verify(run_log)[0])
        origin, start, _ = runs.origin_of(Path(d["dir"]))
        self.assertEqual((origin["session"], origin["step"], origin["log_head"]), ("sess-aaaa-1111", 2, source_head))
        self.assertEqual(sorted(c["path"] for c in start), ["README.md", "calc.py", "notes.txt", "test_calc.py"])
        objects = Path(d["dir"]) / ".rewindagents" / "objects"
        self.assertTrue(all((objects / c["sha256"]).is_file() for c in start))
        self.assertEqual(runs.read_index(s.root)[0]["name"], "try2")
        self.assertTrue((Path(d["dir"]) / ".rewindagents" / ".gitignore").is_file())

    def test_an_agent_in_the_run_records_into_the_run_not_into_the_project(self):
        s = Session(self.base)
        d = runs.fork(s.log, 1, "other")
        project_log = s.log.read_text()
        Agent(d["dir"], "sess-bbbb-2222").write("calc.py", "def div(a, b):\n    return a // b\n")
        self.assertEqual(s.log.read_text(), project_log)
        run_steps = rewind.steps(Path(d["dir"]) / ".rewindagents" / "log.jsonl")
        self.assertEqual([st["tool"] for st in run_steps], ["Write"])
        # and the run is a full project: rewind works in it
        rewind.rewind(Path(d["dir"]) / ".rewindagents" / "log.jsonl", 0)
        self.assertIn(b"return a / b", (Path(d["dir"]) / "calc.py").read_bytes())

    def test_outside_git_the_run_is_a_plain_directory(self):
        s = Session(self.base, use_git=False)
        d = runs.fork(s.log, 3, "plain")
        self.assertIsNone(d["git_branch"])
        got = files_of(d["dir"])
        self.assertNotIn("README.md", got)                       # step 3 removed it
        self.assertEqual(got["calc.py"].count(b"def "), 2)

    def test_a_project_in_a_subdirectory_of_a_repository_is_forked_as_a_plain_directory(self):
        git(self.base, "init", "-q")
        (self.base / "top.txt").write_text("repository file\n", newline="")
        git(self.base, "add", "top.txt")
        git(self.base, "commit", "-qm", "outer")
        s = Session(self.base, use_git=False)                   # proj/ is a subdirectory of the repository
        d = runs.fork(s.log, 2, "sub")
        self.assertIsNone(d["git_branch"])
        self.assertEqual(sorted(files_of(d["dir"])), ["README.md", "calc.py", "notes.txt", "test_calc.py"])

    def test_nested_file_keys_match_between_project_files_and_rewind_relative_on_windows_shaped_paths(self):
        """Windows-shaped regression: runs.start_state() keys one dict partly from bashscan.project_files()
        (the "now" entries, line 69) and partly from rewind.relative() (the plan's restore/delete entries,
        lines 71/73) -- the SAME dict. Outside a git repository, project_files() falls back to os.walk +
        os.path.relpath, which on Windows returns '\\'-separated paths, while rewind.relative() always
        returns '/'-separated ones (.as_posix()). Before bashscan's fix those were two different strings
        for the same nested file: a restore would add a second dict key instead of overwriting the "now"
        one (both versions could land on disk, non-deterministically, depending on dict iteration order),
        and a delete's state.pop(key, None) would never find a match. This cannot be reproduced end-to-end
        through a real fork() on this machine: POSIX pathlib never treats '\\' as a separator, so
        `root / "sub\\a.py"` is a path to a literally-named nonexistent file, and project_files()'s own
        existence check (`full.is_file()`) silently drops that entry before it ever reaches the dict --
        masking the bug here in a way a real Windows run (where both spellings address the one real file)
        would not. So this proves the fix at its exact source: the two key-producing paths must agree,
        simulated by making os.path.relpath -- used nowhere else in this package -- return a
        backslash-joined path, the shape a real Windows os.path.relpath call on this project would
        produce."""
        orig_relpath = os.path.relpath

        def win_relpath(path, start=os.curdir):
            return orig_relpath(path, start).replace("/", "\\")

        with TemporaryDirectory() as d:
            root = Path(d).resolve() / "proj"
            (root / "sub").mkdir(parents=True)
            full = root / "sub" / "a.py"
            full.write_text("v1\n", newline="")
            with mock.patch("os.path.relpath", win_relpath):
                rels = bashscan.project_files(root)
            self.assertEqual(rels, ["sub/a.py"])                         # not "sub\\a.py"
            self.assertEqual(rels[0], rewind.relative(full, root))       # the exact two call sites agree

    def test_refusals_leave_nothing_behind(self):
        s = Session(self.base)
        for name, kwargs, says in (("bad name!", {}, "not a run name"),
                                   ("in", {"dest": s.root / "sub"}, "inside the project")):
            with self.assertRaises(runs.RunError) as e:
                runs.fork(s.log, 1, name, **kwargs)
            self.assertIn(says, str(e.exception))
        (self.base / "proj-taken").mkdir()
        with self.assertRaisesRegex(runs.RunError, "already exists"):
            runs.fork(s.log, 1, "taken")
        runs.fork(s.log, 1, "once")
        with self.assertRaisesRegex(runs.RunError, "already has a run named 'once'"):
            runs.fork(s.log, 1, "once", dest=self.base / "elsewhere")
        self.assertFalse((self.base / "elsewhere").exists())

    def test_a_step_that_cannot_be_rebuilt_exactly_is_refused(self):
        s = Session(self.base)
        s.agent.bash("make clean", post=False)                   # no after-scan: its changes are unknown
        with self.assertRaisesRegex(runs.RunError, "not scanned"):
            runs.fork(s.log, 1, "unknown")
        self.assertFalse((self.base / "proj-unknown").exists())
        self.assertEqual(git(s.root, "branch", "--list", "rewindagents/run/*"), "")

    def test_a_tampered_log_is_refused(self):
        s = Session(self.base)
        lines = s.log.read_text().splitlines()
        rec = json.loads(lines[0])
        rec["tool"] = "Edit"
        lines[0] = json.dumps(rec, sort_keys=True)
        s.log.write_text("\n".join(lines) + "\n", newline="")
        with self.assertRaises(rewind.RewindError):
            runs.fork(s.log, 1, "x")
        self.assertFalse((self.base / "proj-x").exists())

    def test_a_failure_half_way_removes_the_worktree_and_branch(self):
        s = Session(self.base)
        real = runs.checkpoint
        calls = []

        def boom(*a, **k):
            calls.append(1)
            raise OSError("disk full")
        runs.checkpoint = boom
        try:
            with self.assertRaises(OSError):
                runs.fork(s.log, 1, "half")
        finally:
            runs.checkpoint = real
        self.assertTrue(calls)
        self.assertFalse((self.base / "proj-half").exists())
        self.assertEqual(git(s.root, "branch", "--list", "rewindagents/run/*"), "")
        self.assertEqual(runs.read_index(s.root), [])


class TestCompare(unittest.TestCase):
    """The project's own continuation vs two forks from step 2, one by another agent."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.s = Session(self.base)
        self.a = Path(runs.fork(self.s.log, 2, "a")["dir"])
        self.b = Path(runs.fork(self.s.log, 2, "b")["dir"])
        good = "def add(a, b):\n    return a + b\n\n\ndef div(a, b):\n    if b == 0:\n        return None\n    return a / b\n"
        Agent(self.a, "sess-a").write("calc.py", good)
        ag_b = Agent(self.b, "sess-b")
        ag_b.write("calc.py", good)                             # same bytes as run a
        ag_b.bash("touch extra.txt", action=lambda c: (c / "extra.txt").write_text("x\n", newline=""))

    def tearDown(self):
        self.tmp.cleanup()

    def test_compare_lines_the_runs_up_against_their_start(self):
        c = runs.compare(self.s.root)
        by = {r["name"]: r for r in c["runs"]}
        self.assertEqual(list(by), ["proj", "a", "b"])
        self.assertEqual((c["session"], c["step"]), ("sess-aaaa-1111", 2))
        # the project went on with steps 3 (rm README) and 4 (broke calc.py): two agent steps
        self.assertEqual(by["proj"]["steps"], 2)
        self.assertEqual(by["proj"]["files"]["README.md"]["kind"], "deleted")
        self.assertEqual(by["a"]["steps"], 1)
        self.assertEqual(by["b"]["steps"], 2)
        self.assertEqual(by["b"]["files"]["extra.txt"]["kind"], "created")
        self.assertEqual(by["a"]["files"]["calc.py"]["lines"], (2, 0))
        # same bytes, same letter; the broken project file gets its own
        row = c["matrix"]["calc.py"]
        self.assertEqual(row["a"]["group"], row["b"]["group"])
        self.assertNotEqual(row["proj"]["group"], row["a"]["group"])
        self.assertEqual(c["matrix"]["extra.txt"]["a"]["kind"], "unchanged")

    def test_check_runs_in_each_run_and_reports_its_exit_code(self):
        c = runs.compare(self.s.root, check=f"{sys.executable} -c \"import calc; assert calc.div(1, 0) is None\"")
        got = {r["name"]: r["check"]["exit"] for r in c["runs"]}
        self.assertNotEqual(got["proj"], 0)                    # calc.py is 'broken' there
        self.assertEqual((got["a"], got["b"]), (0, 0))
        text = "\n".join(runs.lines(c))
        self.assertIn("FAIL (exit 1)", text)
        self.assertIn("pass", text)

    def test_diff_between_two_runs_applies_with_git(self):
        out = runs.diff_runs(self.s.root, "proj", "b")
        patch = "".join(out[1:])
        self.assertIn("diff --git a/calc.py b/calc.py", patch)
        self.assertIn("extra.txt", patch)
        p = subprocess.run(["git", "-C", str(self.s.root), "apply", "-"], input=patch, text=True, capture_output=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        for rel in ("calc.py", "extra.txt", "test_calc.py"):
            self.assertEqual((self.s.root / rel).read_bytes(), (self.b / rel).read_bytes(), rel)

    def test_compare_works_from_inside_a_run_and_names_runs(self):
        c = runs.compare(self.b, ["a", "b"])
        self.assertEqual([r["name"] for r in c["runs"]], ["a", "b"])
        with self.assertRaisesRegex(runs.RunError, "no run named 'zz'"):
            runs.compare(self.s.root, ["zz"])

    def test_caches_are_not_the_work(self):
        (self.a / "__pycache__").mkdir()
        (self.a / "__pycache__" / "calc.cpython-3.pyc").write_bytes(b"\0junk")
        c = runs.compare(self.s.root)
        self.assertNotIn("__pycache__/calc.cpython-3.pyc", c["matrix"])

    def test_gc_in_a_run_keeps_the_starting_copies(self):
        run_log = self.a / ".rewindagents" / "log.jsonl"
        gc.gc(run_log)
        c = runs.compare(self.s.root, ["a"])
        self.assertEqual(c["runs"][0]["files"]["calc.py"]["lines"], (2, 0))   # still diffable from the start

    def test_runs_from_different_steps_are_not_mixed(self):
        runs.fork(self.s.log, 1, "early")
        with self.assertRaisesRegex(runs.RunError, "start from different points"):
            runs.compare(self.s.root, ["a", "early"])
        # the default picks the newest run's starting point
        self.assertEqual([r["name"] for r in runs.compare(self.s.root)["runs"]], ["proj", "early"])


class TestCli(unittest.TestCase):
    def test_fork_then_compare_from_the_command_line(self):
        with TemporaryDirectory() as t:
            s = Session(Path(t))
            with cwd(s.root):
                code, out, err = cli("fork", "2", "--name", "try2", "--session", "sess-a")   # an id prefix works
                self.assertEqual(code, 0, err)
                self.assertIn("run try2:", out)
                self.assertIn("right after step 2 of session sess-aaaa-1111", out)
                self.assertIn("no agent hook reaches it", out)       # the test project has no agent config
                self.assertIn("compare", out)
                code, out, err = cli("compare")
                self.assertEqual(code, 0, err)
                self.assertIn("runs from session sess-aaa step 2 of proj", out)
                self.assertIn("compare --diff proj try2", out)
                code, out, err = cli("compare", "--json")
                self.assertEqual(json.loads(out)["step"], 2)
                code, out, err = cli("compare", "--diff", "proj")
                self.assertEqual(code, 2)
                self.assertIn("exactly two runs", err)
            with cwd(Path(t) / "proj-try2"):
                code, out, err = cli("replay")
                self.assertIn("run try2 starts here", out)

    def test_compare_before_any_fork_says_how_to_make_one(self):
        with TemporaryDirectory() as t:
            s = Session(Path(t))
            with cwd(s.root):
                code, out, err = cli("compare")
            self.assertEqual(code, 1)
            self.assertIn("rewindagents fork N --name NAME", err)

    def test_fork_with_no_log_points_at_init(self):
        with TemporaryDirectory() as t:
            with cwd(t):
                code, out, err = cli("fork", "1", "--name", "x")
            self.assertEqual(code, 2)
            self.assertIn("init", err)


if __name__ == "__main__":
    unittest.main()
