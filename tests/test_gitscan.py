"""The git path of the Bash scan (gitscan.py): the same checkpoints and the same rewind as the whole-project scan,
read from `git status` instead of a stat of every file."""
import hashlib
import io
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from rewindagents import bashscan, gitscan, rewind  # noqa: E402
from test_rewind import Agent, git  # noqa: E402


def tree(d, skip=("build",)):
    return {str(p.relative_to(d)): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mode & 0o777)
            for p in sorted(Path(d).rglob("*"))
            if p.is_file() and not ({".rewindagents", ".git"} | set(skip)) & set(p.relative_to(d).parts)}


def sh(cmd):
    return lambda cwd: subprocess.run(["sh", "-c", cmd], cwd=cwd, check=True, capture_output=True)


class Base(unittest.TestCase):
    """The git path at any size (it takes projects of more than 20,000 tracked files, which a test cannot build)."""

    def setUp(self):
        p = mock.patch.dict(os.environ, {"REWINDAGENTS_BASH_SCAN": "git"})
        p.start()
        self.addCleanup(p.stop)


class GitCase(Base):
    def setUp(self):
        super().setUp()
        self.tmp = TemporaryDirectory()
        self.d = Path(self.tmp.name).resolve()
        git(self.d, "init", "-q")
        for n, t in (("a.txt", "a\n"), ("b.txt", "b\n"), ("src/c.py", "c = 1\n"), ("src/d.py", "d = 1\n")):
            Path(self.d, n).parent.mkdir(exist_ok=True)
            Path(self.d, n).write_text(t)
        Path(self.d, "run.sh").write_text("#!/bin/sh\n")
        os.chmod(self.d / "run.sh", 0o755)
        Path(self.d, ".gitignore").write_text(".env\nbuild/\n")
        git(self.d, "add", "-A")
        git(self.d, "commit", "-qm", "init")
        self.a = Agent(self.d)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cmd(self, cmd):
        """One Bash step running `cmd`; returns (the step, the tree before it)."""
        before = tree(self.d)
        self.a.bash(cmd, sh(cmd))
        return rewind.steps(self.a.log)[-1], before

    def names(self, step):
        return sorted(Path(c["path"]).name for c in step["checkpoints"])

    def assert_rewinds(self, before, step_no=0):
        rewind.rewind(self.a.log, step_no)
        self.assertEqual(tree(self.d), before)

    def used_git(self):
        recs = [r for r in __import__("rewindagents").log.read(self.a.log)]
        return bool(recs[0]["args"]["bash_scan"].get("git"))


class TestGitPath(GitCase):
    def test_the_git_path_is_used_and_is_the_default_in_a_work_tree(self):
        step, before = self.run_cmd("sed -i.bak s/a/A/ a.txt; rm b.txt")
        self.assertTrue(self.used_git())
        self.assertEqual(self.names(step), ["a.txt", "a.txt.bak", "b.txt"])
        self.assert_rewinds(before)

    def test_clean_files_are_not_read_before_the_command(self):
        with mock.patch.object(gitscan, "snapshot_found", wraps=gitscan.snapshot_found) as sf:
            self.a.bash("true")
        self.assertEqual(sf.call_args_list[0].args[2], [])          # nothing dirty: nothing listed, nothing read

    def test_deleted_tracked_file_and_created_file(self):
        step, before = self.run_cmd("rm src/c.py; echo n > new.txt")
        self.assertEqual(self.names(step), ["c.py", "new.txt"])
        self.assert_rewinds(before)
        self.assertFalse(Path(self.d, "new.txt").exists())

    def test_rename_tracked_and_untracked(self):
        Path(self.d, "u.txt").write_text("untracked\n")
        step, before = self.run_cmd("mv a.txt a2.txt; mv u.txt u2.txt; git mv b.txt b2.txt")
        self.assertEqual(self.names(step), ["a.txt", "a2.txt", "b.txt", "b2.txt", "u.txt", "u2.txt"])
        self.assert_rewinds(before)

    def test_tracked_dirty_and_untracked_before_the_command(self):
        Path(self.d, "a.txt").write_text("dirty\n")
        Path(self.d, "u.txt").write_text("untracked\n")
        step, before = self.run_cmd("echo more >> a.txt; echo more >> u.txt; rm src/d.py")
        self.assertEqual(self.names(step), ["a.txt", "d.py", "u.txt"])
        self.assert_rewinds(before)
        self.assertEqual(Path(self.d, "a.txt").read_text(), "dirty\n")      # the dirty version, not HEAD's

    def test_staged_then_changed_again(self):
        Path(self.d, "a.txt").write_text("staged\n")
        git(self.d, "add", "a.txt")
        step, before = self.run_cmd("echo again >> a.txt")
        self.assertEqual(self.names(step), ["a.txt"])
        self.assert_rewinds(before)
        self.assertEqual(Path(self.d, "a.txt").read_text(), "staged\n")

    def test_the_command_runs_git_add_and_commit(self):
        step, before = self.run_cmd("echo x >> a.txt; git add a.txt; git commit -qm c; echo y >> b.txt")
        self.assertEqual(self.names(step), ["a.txt", "b.txt"])
        self.assertEqual(step["bash_scan"], {"changed": 2})
        self.assert_rewinds(before)

    def test_git_add_alone_changes_no_file(self):
        Path(self.d, "a.txt").write_text("dirty\n")
        step, _ = self.run_cmd("git add -A")
        self.assertEqual(step["bash_scan"], {"changed": 0})

    def test_head_moves_checkout_of_another_branch(self):
        git(self.d, "checkout", "-q", "-b", "other")
        Path(self.d, "a.txt").write_text("other branch\n")
        Path(self.d, "extra.txt").write_text("only there\n")
        git(self.d, "add", "-A")
        git(self.d, "commit", "-qm", "o")
        git(self.d, "checkout", "-q", "-")
        step, before = self.run_cmd("git checkout -q other")
        self.assertEqual(self.names(step), ["a.txt", "extra.txt"])
        self.assertEqual(Path(self.d, "a.txt").read_text(), "other branch\n")
        self.assert_rewinds(before)
        self.assertFalse(Path(self.d, "extra.txt").exists())

    def test_head_moves_reset_hard_and_stash(self):
        Path(self.d, "a.txt").write_text("v2\n")
        git(self.d, "commit", "-qam", "v2")
        step, before = self.run_cmd("git reset -q --hard HEAD~1")
        self.assertEqual(self.names(step), ["a.txt"])
        self.assert_rewinds(before)

    def test_stash(self):
        Path(self.d, "b.txt").write_text("dirty b\n")
        step, before = self.run_cmd("git stash -q")
        self.assertEqual(self.names(step), ["b.txt"])
        self.assertEqual(Path(self.d, "b.txt").read_text(), "b\n")
        self.assert_rewinds(before)

    def test_gitignored_directory_is_not_scanned_but_ignored_files_are(self):
        Path(self.d, ".env").write_text("K=1\n")
        Path(self.d, "build").mkdir()
        Path(self.d, "build", "out.bin").write_text("o\n")
        step, before = self.run_cmd("rm .env build/out.bin; echo n > build/new.bin")
        self.assertEqual(self.names(step), [".env"])
        self.assert_rewinds(before)

    def test_untracked_files_under_skip_dirs_are_not_scanned(self):
        step, _ = self.run_cmd("mkdir -p node_modules/x __pycache__; echo 1 > node_modules/x/i.js; echo 2 > __pycache__/m.pyc")
        self.assertEqual(step["bash_scan"], {"changed": 0})

    def test_chmod_alone_is_a_change_and_comes_back(self):
        step, before = self.run_cmd("chmod -x run.sh; chmod +x a.txt")
        self.assertEqual(self.names(step), ["a.txt", "run.sh"])
        self.assert_rewinds(before)
        self.assertTrue(os.access(self.d / "run.sh", os.X_OK))

    def test_a_deleted_executable_comes_back_executable(self):
        step, before = self.run_cmd("rm run.sh")
        self.assert_rewinds(before)
        self.assertTrue(os.access(self.d / "run.sh", os.X_OK))

    def test_big_file_over_the_limit_is_recorded_as_skipped(self):
        big = self.d / "big.bin"
        big.write_bytes(b"\0" * (bashscan.MAX_CHECKPOINT_BYTES + 1))
        git(self.d, "add", "big.bin")
        git(self.d, "commit", "-qm", "big")
        step, _ = self.run_cmd("rm big.bin")
        self.assertEqual([c.get("skipped") for c in step["checkpoints"]],
                         [f"larger than {bashscan.MAX_CHECKPOINT_BYTES} bytes"])

    def test_symlink_is_not_followed(self):
        os.symlink("a.txt", self.d / "ln")
        git(self.d, "add", "ln")
        git(self.d, "commit", "-qm", "ln")
        step, _ = self.run_cmd("rm ln")
        self.assertEqual(step["bash_scan"], {"changed": 0})

    def test_files_with_odd_names(self):
        Path(self.d, "sp ace.txt").write_text("s\n")
        Path(self.d, "ünï.txt").write_text("u\n")
        git(self.d, "add", "-A")
        git(self.d, "commit", "-qm", "odd")
        step, before = self.run_cmd("rm 'sp ace.txt' ünï.txt")
        self.assertEqual(self.names(step), ["sp ace.txt", "ünï.txt"])
        self.assert_rewinds(before)

    def test_submodule_contents_are_not_scanned(self):
        with TemporaryDirectory() as sub:
            git(sub, "init", "-q")
            Path(sub, "s.txt").write_text("s\n")
            git(sub, "add", "-A")
            git(sub, "commit", "-qm", "s")
            subprocess.run(["git", "-C", str(self.d), "-c", "protocol.file.allow=always", "submodule", "add", "-q", sub, "mod"],
                           check=True, capture_output=True, env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                                                                      GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t"))
            git(self.d, "commit", "-qm", "submodule")
            step, _ = self.run_cmd("echo changed > mod/s.txt; echo x > mod/new.txt; echo y >> a.txt")
            self.assertEqual(self.names(step), ["a.txt"])

    def test_nothing_runs_when_nothing_changes(self):
        step, _ = self.run_cmd("ls")
        self.assertEqual(step["bash_scan"], {"changed": 0})


class TestNoCommits(Base):
    def test_repository_without_a_commit(self):
        with TemporaryDirectory() as t:
            d = Path(t).resolve()
            git(d, "init", "-q")
            Path(d, "staged.txt").write_text("s\n")
            Path(d, "loose.txt").write_text("l\n")
            git(d, "add", "staged.txt")
            a = Agent(d)
            before = tree(d)
            a.bash("rm staged.txt loose.txt; echo n > new.txt", sh("rm staged.txt loose.txt; echo n > new.txt"))
            step = rewind.steps(a.log)[-1]
            self.assertEqual(sorted(Path(c["path"]).name for c in step["checkpoints"]), ["loose.txt", "new.txt", "staged.txt"])
            rewind.rewind(a.log, 0)
            self.assertEqual(tree(d), before)

    def test_first_commit_made_by_the_command(self):
        with TemporaryDirectory() as t:
            d = Path(t).resolve()
            git(d, "init", "-q")
            Path(d, "f.txt").write_text("f\n")
            a = Agent(d)
            before = tree(d)
            cmd = "git add f.txt; git commit -qm one; echo more >> f.txt"
            a.bash(cmd, sh(cmd))
            step = rewind.steps(a.log)[-1]
            self.assertEqual([Path(c["path"]).name for c in step["checkpoints"]], ["f.txt"])
            rewind.rewind(a.log, 0)
            self.assertEqual(tree(d), before)


class TestConversion(Base):
    def make(self, d, attrs="* text eol=crlf\n"):
        git(d, "init", "-q")
        Path(d, ".gitattributes").write_text(attrs)
        Path(d, "w.txt").write_bytes(b"one\r\ntwo\r\n")
        Path(d, "keep.txt").write_bytes(b"keep\r\n")
        git(d, "add", "-A")
        git(d, "commit", "-qm", "crlf")

    def test_small_project_with_a_conversion_takes_the_exact_whole_project_scan(self):
        with TemporaryDirectory() as t:
            d = Path(t).resolve()
            self.make(d)
            a = Agent(d)
            Path(d, "w.txt").write_bytes(b"one\r\ntwo\r\n")
            a.bash("rm w.txt", sh("rm w.txt"))
            pre = rewind.steps(a.log)
            from rewindagents import log
            self.assertFalse(log.read(a.log)[0]["args"]["bash_scan"].get("git"))
            rewind.rewind(a.log, 0)
            self.assertEqual(Path(d, "w.txt").read_bytes(), b"one\r\ntwo\r\n")

    def test_big_project_with_a_conversion_restores_the_bytes_checkout_wrote(self):
        with TemporaryDirectory() as t:
            d = Path(t).resolve()
            self.make(d)
            self.assertEqual(Path(d, "w.txt").read_bytes(), b"one\r\ntwo\r\n")
            a = Agent(d)
            with mock.patch.object(gitscan, "MAX_SCAN_FILES", 0):
                a.bash("rm w.txt", sh("rm w.txt"))
            from rewindagents import log
            self.assertTrue(log.read(a.log)[0]["args"]["bash_scan"].get("git"))
            rewind.rewind(a.log, 0)
            self.assertEqual(Path(d, "w.txt").read_bytes(), b"one\r\ntwo\r\n")

    def test_nested_gitattributes_conversion_is_applied_by_checkout_rules(self):
        with TemporaryDirectory() as t:
            d = Path(t).resolve()
            git(d, "init", "-q")
            Path(d, "sub").mkdir()
            Path(d, "sub", ".gitattributes").write_text("*.txt text eol=crlf\n")
            Path(d, "sub", "n.txt").write_bytes(b"x\r\ny\r\n")
            Path(d, "plain.txt").write_bytes(b"p\n")
            git(d, "add", "-A")
            git(d, "commit", "-qm", "n")
            a = Agent(d)
            a.bash("rm sub/n.txt plain.txt", sh("rm sub/n.txt plain.txt"))
            from rewindagents import log
            self.assertTrue(log.read(a.log)[0]["args"]["bash_scan"].get("git"))
            rewind.rewind(a.log, 0)
            self.assertEqual(Path(d, "sub", "n.txt").read_bytes(), b"x\r\ny\r\n")
            self.assertEqual(Path(d, "plain.txt").read_bytes(), b"p\n")

    def test_external_filter_is_skipped_not_guessed(self):
        with TemporaryDirectory() as t:
            d = Path(t).resolve()
            git(d, "init", "-q")
            Path(d, ".gitattributes").write_text("*.dat filter=lfsish\n")
            Path(d, "x.dat").write_text("data\n")
            git(d, "add", "-A")
            git(d, "commit", "-qm", "f")
            a = Agent(d)
            with mock.patch.object(gitscan, "MAX_SCAN_FILES", 0):
                a.bash("rm x.dat", sh("rm x.dat"))
            step = rewind.steps(a.log)[-1]
            self.assertIn("filter", step["checkpoints"][0]["skipped"])


class TestFallbacks(Base):
    def test_project_below_the_top_of_a_repository_uses_the_old_scan(self):
        with TemporaryDirectory() as t:
            top = Path(t).resolve()
            git(top, "init", "-q")
            (top / "proj").mkdir()
            Path(top, "proj", "f.txt").write_text("f\n")
            git(top, "add", "-A")
            git(top, "commit", "-qm", "p")
            a = Agent(top / "proj")
            (top / "proj" / ".rewindagents").mkdir()
            a.bash("rm f.txt", sh("rm f.txt"))
            from rewindagents import log
            self.assertFalse(log.read(a.log)[0]["args"]["bash_scan"].get("git"))
            self.assertEqual(rewind.steps(a.log)[-1]["bash_scan"], {"changed": 1})

    def test_small_git_project_takes_the_old_scan_by_default(self):
        with TemporaryDirectory() as t:
            d = Path(t).resolve()
            git(d, "init", "-q")
            Path(d, "f.txt").write_text("f\n")
            git(d, "add", "-A")
            a = Agent(d)
            with mock.patch.dict(os.environ, {"REWINDAGENTS_BASH_SCAN": ""}):
                a.bash("rm f.txt", sh("rm f.txt"))
            from rewindagents import log
            self.assertFalse(log.read(a.log)[0]["args"]["bash_scan"].get("git"))

    def test_not_a_repository_keeps_the_old_scan_and_its_limit(self):
        with TemporaryDirectory() as t:
            d = Path(t).resolve()
            Path(d, "f.txt").write_text("f\n")
            a = Agent(d)
            with mock.patch.object(bashscan, "MAX_SCAN_FILES", 0):
                a.bash("rm f.txt", sh("rm f.txt"))
            self.assertEqual(rewind.steps(a.log)[-1]["bash_scan"], {"skipped": "more than 0 files"})

    def test_git_status_failing_falls_back_to_the_old_scan(self):
        with TemporaryDirectory() as t:
            d = Path(t).resolve()
            git(d, "init", "-q")
            Path(d, "f.txt").write_text("f\n")
            a = Agent(d)
            with mock.patch.object(gitscan, "_status", return_value=None):
                a.bash("rm f.txt", sh("rm f.txt"))
            self.assertEqual(rewind.steps(a.log)[-1]["bash_scan"], {"changed": 1})

    def test_forced_full_scan(self):
        with TemporaryDirectory() as t:
            d = Path(t).resolve()
            git(d, "init", "-q")
            Path(d, "f.txt").write_text("f\n")
            a = Agent(d)
            with mock.patch.dict(os.environ, {"REWINDAGENTS_BASH_SCAN": "full"}):
                a.bash("rm f.txt", sh("rm f.txt"))
            from rewindagents import log
            self.assertFalse(log.read(a.log)[0]["args"]["bash_scan"].get("git"))


class TestLimits(Base):
    def test_limit_is_two_million_tracked_files_and_status_warns_above_it(self):
        self.assertEqual(gitscan.MAX_GIT_FILES, 2_000_000)
        with TemporaryDirectory() as t:
            d = Path(t).resolve()
            git(d, "init", "-q")
            Path(d, "f.txt").write_text("f\n")
            git(d, "add", "-A")
            self.assertIs(gitscan.too_big(d), False)
            with mock.patch.object(gitscan, "MAX_GIT_FILES", 0):
                self.assertIs(gitscan.too_big(d), True)
                a = Agent(d)
                a.bash("rm f.txt", sh("rm f.txt"))
                self.assertEqual(rewind.steps(a.log)[-1]["bash_scan"], {"skipped": "more than 0 files"})
                from rewindagents import init
                out = io.StringIO()
                self.assertTrue(init.too_many_files(d))

    def test_more_dirty_files_than_the_limit_is_reported_not_guessed(self):
        with TemporaryDirectory() as t:
            d = Path(t).resolve()
            git(d, "init", "-q")
            for i in range(5):
                Path(d, f"u{i}.txt").write_text("u\n")
            a = Agent(d)
            with mock.patch.object(gitscan, "MAX_GIT_DIRTY", 3):
                a.bash("rm u0.txt", sh("rm u0.txt"))
            self.assertIn("more than 3", rewind.steps(a.log)[-1]["bash_scan"]["skipped"])

    def test_pending_scan_is_readable_by_gc(self):
        with TemporaryDirectory() as t:
            d = Path(t).resolve()
            git(d, "init", "-q")
            Path(d, "f.txt").write_text("f\n")
            a = Agent(d)
            a.bash("rm f.txt", sh("rm f.txt"), post=False)
            from rewindagents import gc
            named, n = gc.needed(a.log)
            self.assertEqual(n, 1)
            self.assertEqual(len(named), 1)


class TestQuickMode(GitCase):
    def test_ignored_skip_mode_still_finds_untracked_files_in_new_directories(self):
        Path(self.d, "newdir/deep").mkdir(parents=True)
        Path(self.d, "newdir/deep/x.txt").write_text("x\n")
        Path(self.d, ".env").write_text("one\n")
        with mock.patch.dict(os.environ, {"REWINDAGENTS_IGNORED": "skip"}):
            step, before = self.run_cmd("rm newdir/deep/x.txt .env; echo n > newdir/y.txt")
        self.assertEqual(self.names(step), ["x.txt", "y.txt"])         # the ignored file is the documented trade-off


if __name__ == "__main__":
    unittest.main()
