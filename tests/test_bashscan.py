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
sys.path.insert(0, str(Path(__file__).resolve().parent))

from rewindagents import bashscan, hook, rewind, verify  # noqa: E402
from test_rewind import Agent, cli, git  # noqa: E402


def rewrite(name, text):
    return lambda cwd: Path(cwd, name).write_text(text)


class TestBashCheckpoints(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.d = Path(self.tmp.name)
        Path(self.d, "src").mkdir()
        Path(self.d, "src", "app.py").write_text("good\n")
        Path(self.d, "notes.txt").write_text("keep\n")
        self.a = Agent(self.d)

    def tearDown(self):
        self.tmp.cleanup()

    def test_in_place_edit_is_put_back(self):
        self.a.bash("sed -i '' s/good/bad/ src/app.py", rewrite("src/app.py", "bad\n"))
        steps = rewind.steps(self.a.log)
        self.assertEqual(steps[0]["bash_scan"], {"changed": 1})
        self.assertEqual([Path(c["path"]).name for c in steps[0]["checkpoints"]], ["app.py"])
        p = rewind.rewind(self.a.log, 0)
        self.assertEqual(Path(self.d, "src", "app.py").read_text(), "good\n")
        self.assertEqual((p["cannot"], p["bash_uncovered"]), ([], 0))

    def test_deleted_file_comes_back_and_created_file_goes(self):
        def rm_and_make(cwd):
            Path(cwd, "notes.txt").unlink()
            Path(cwd, "build").mkdir()
            Path(cwd, "build", "out.bin").write_bytes(b"\x00\x01")
        self.a.bash("rm notes.txt && make", rm_and_make)
        rewind.rewind(self.a.log, 0)
        self.assertEqual(Path(self.d, "notes.txt").read_text(), "keep\n")
        self.assertFalse(Path(self.d, "build", "out.bin").exists())

    def test_rename_is_undone(self):
        self.a.bash("mv notes.txt n2.txt", lambda c: Path(c, "notes.txt").rename(Path(c, "n2.txt")))
        rewind.rewind(self.a.log, 0)
        self.assertEqual(Path(self.d, "notes.txt").read_text(), "keep\n")
        self.assertFalse(Path(self.d, "n2.txt").exists())

    def test_unchanged_files_are_not_checkpointed(self):
        self.a.bash("pytest -q")
        self.assertEqual(rewind.steps(self.a.log)[0]["checkpoints"], [])

    def test_rewind_to_a_middle_step_mixes_bash_and_write(self):
        self.a.write("src/app.py", "v2\n")                                     # step 1
        self.a.bash("sed", rewrite("src/app.py", "v3\n"))                      # step 2
        self.a.write("src/app.py", "v4\n")                                     # step 3
        self.a.bash("rm", lambda c: Path(c, "src", "app.py").unlink())         # step 4
        rewind.rewind(self.a.log, 2)
        self.assertEqual(Path(self.d, "src", "app.py").read_text(), "v3\n")
        rewind.rewind(self.a.log, 1)
        self.assertEqual(Path(self.d, "src", "app.py").read_text(), "v2\n")
        self.assertTrue(verify(self.a.log)[0])

    def test_no_pending_scans_left_behind(self):
        self.a.bash("sed", rewrite("notes.txt", "x"))
        self.assertEqual(list(Path(self.d, ".rewindagents", "pending").iterdir()), [])

    def test_tool_use_id_pairs_identical_commands(self):
        inp = {"command": "./gen.sh"}

        def ev(event, tid):
            return {"session_id": "s1", "cwd": str(self.d), "hook_event_name": event,
                    "tool_name": "Bash", "tool_input": inp, "tool_use_id": tid}
        hook.handle(ev("PreToolUse", "t1"))
        Path(self.d, "notes.txt").write_text("first\n")
        hook.handle(ev("PostToolUse", "t1"))
        hook.handle(ev("PreToolUse", "t2"))
        Path(self.d, "notes.txt").write_text("second\n")
        hook.handle(ev("PostToolUse", "t2"))
        rewind.rewind(self.a.log, 1)
        self.assertEqual(Path(self.d, "notes.txt").read_text(), "first\n")

    def test_same_size_rewrite_is_seen_through_the_stat_cache(self):
        self.a.bash("ls")                                   # fills the cache
        st = Path(self.d, "notes.txt").stat()
        self.a.bash("sed", lambda c: (Path(c, "notes.txt").write_text("KEEP\n"),
                                      os.utime(Path(c, "notes.txt"), ns=(st.st_atime_ns, st.st_mtime_ns + 1000))))
        rewind.rewind(self.a.log, 1)
        self.assertEqual(Path(self.d, "notes.txt").read_text(), "keep\n")


class TestBashLimits(unittest.TestCase):
    def test_too_many_files_is_reported_not_guessed(self):
        with TemporaryDirectory() as d:
            for i in range(3):
                Path(d, f"f{i}").write_text(str(i))
            a = Agent(d)
            with mock.patch.object(bashscan, "MAX_SCAN_FILES", 2):
                a.bash("rm f0", lambda c: Path(c, "f0").unlink())
            s = rewind.steps(a.log)[0]
            self.assertEqual(s["bash_scan"], {"skipped": "more than 2 files"})
            p = rewind.rewind(a.log, 0, dry_run=True)
            self.assertEqual(p["bash_uncovered"], 1)
            code, out, _ = cli("--log", str(a.log), "rewind", "0", "--dry-run")
            self.assertIn("1 step(s) after step 0 were not scanned", out)
            self.assertEqual(code, 1, "README: if anything could not be restored, the exit code is 1")
            self.assertEqual(cli("--log", str(a.log), "rewind", "0")[0], 1)

    def test_large_file_changed_by_bash_is_reported_as_cannot(self):
        with TemporaryDirectory() as d:
            Path(d, "big.bin").write_bytes(b"x" * 50)
            a = Agent(d)
            with mock.patch.object(bashscan, "MAX_CHECKPOINT_BYTES", 10):
                a.bash("truncate", lambda c: Path(c, "big.bin").write_bytes(b"y" * 60))
            p = rewind.rewind(a.log, 0, dry_run=True)
            self.assertEqual(p["cannot"], [(str(Path(d, "big.bin")), "not checkpointed (larger than 10 bytes)")])

    def test_git_ignored_files_are_not_scanned_untracked_ones_are(self):
        with TemporaryDirectory() as d:
            git(d, "init", "-q")
            Path(d, ".gitignore").write_text("dist/\n")
            Path(d, "dist").mkdir()
            Path(d, "dist", "bundle.js").write_text("old")
            Path(d, "draft.md").write_text("untracked")
            a = Agent(d)

            def act(c):
                Path(c, "dist", "bundle.js").write_text("new")
                Path(c, "draft.md").write_text("changed")
            a.bash("build", act)
            names = [Path(c["path"]).name for c in rewind.steps(a.log)[0]["checkpoints"]]
            self.assertEqual(names, ["draft.md"])

    def test_a_git_ignored_file_deleted_by_bash_is_put_back(self):
        """takeback-bench S06: `rm .env` was a silent miss (rewind exited 0, "did change 0 files")."""
        with TemporaryDirectory() as d:
            git(d, "init", "-q")
            Path(d, ".gitignore").write_text(".env\n*.log\nbuild/\n")
            Path(d, ".env").write_text("API_KEY=dev\n")
            Path(d, "src").mkdir()
            Path(d, "src", "local.log").write_text("log\n")
            Path(d, "build").mkdir()
            Path(d, "build", "out.js").write_text("old")
            a = Agent(d)

            def act(c):
                Path(c, ".env").unlink()
                Path(c, "src", "local.log").write_text("rotated\n")
                Path(c, "build", "out.js").write_text("new")
            a.bash("rm .env && make", act)
            names = sorted(Path(c["path"]).name for c in rewind.steps(a.log)[0]["checkpoints"])
            self.assertEqual(names, [".env", "local.log"])     # the ignored directory is still not scanned
            code, out, err = cli("--log", str(a.log), "rewind", "0")
            self.assertEqual(code, 0, out + err)
            self.assertEqual(Path(d, ".env").read_text(), "API_KEY=dev\n")
            self.assertEqual(Path(d, "src", "local.log").read_text(), "log\n")
            self.assertEqual(Path(d, "build", "out.js").read_text(), "new")

    @unittest.skipIf(os.name == "nt", "no POSIX mode bits on NTFS: os.chmod there only toggles read-only, "
                                       "so a chmod-only change or 0o700/0o750 cannot round-trip")
    def test_a_deleted_script_comes_back_executable(self):
        """takeback-bench S11: the bytes came back, the executable bit did not, and rewind exited 0."""
        with TemporaryDirectory() as d:
            git(d, "init", "-q")
            Path(d, "scripts").mkdir()
            s = Path(d, "scripts", "run.sh")
            s.write_text("#!/bin/sh\necho hi\n")
            s.chmod(0o755)
            Path(d, "tool.sh").write_text("#!/bin/sh\n")
            Path(d, "tool.sh").chmod(0o750)
            a = Agent(d)

            def act(c):
                s.unlink()
                Path(c, "tool.sh").chmod(0o640)          # a chmod alone, the bytes unchanged
            a.bash("rm -rf scripts && chmod -x tool.sh", act)
            self.assertEqual(sorted(Path(c["path"]).name for c in rewind.steps(a.log)[0]["checkpoints"]),
                             ["run.sh", "tool.sh"])
            self.assertEqual(cli("--log", str(a.log), "rewind", "0")[0], 0)
            self.assertEqual(s.stat().st_mode & 0o777, 0o755)
            self.assertEqual(s.read_text(), "#!/bin/sh\necho hi\n")
            self.assertEqual(Path(d, "tool.sh").stat().st_mode & 0o777, 0o750)

    @unittest.skipIf(os.name == "nt", "no POSIX mode bits on NTFS: os.chmod there only toggles read-only, "
                                       "so a chmod-only change or 0o700/0o750 cannot round-trip")
    def test_a_file_the_write_tool_replaced_gets_its_mode_back(self):
        with TemporaryDirectory() as d:
            s = Path(d, "deploy.sh")
            s.write_text("#!/bin/sh\n")
            s.chmod(0o700)
            a = Agent(d)
            a.bash("rm deploy.sh", lambda c: s.unlink())
            a.write("deploy.sh", "echo stub\n")
            self.assertEqual(cli("--log", str(a.log), "rewind", "0")[0], 0)
            self.assertEqual((s.read_text(), s.stat().st_mode & 0o777), ("#!/bin/sh\n", 0o700))

    def test_ignored_files_under_skip_dirs_are_not_scanned(self):
        with TemporaryDirectory() as d:
            git(d, "init", "-q")
            Path(d, ".gitignore").write_text("*.env\n")
            Path(d, "venv").mkdir()
            Path(d, "venv", "x.env").write_text("a")
            self.assertEqual(bashscan.project_files(Path(d), ignored_files=True), [".gitignore"])
            self.assertEqual(bashscan.project_files(Path(d)), [".gitignore"])

    def test_store_and_git_dir_never_scanned(self):
        with TemporaryDirectory() as d:
            git(d, "init", "-q")
            Path(d, "a.txt").write_text("a")
            a = Agent(d)
            a.bash("ls")
            pre = [json.loads(x) for x in a.log.read_text().splitlines()][0]
            self.assertEqual(pre["args"]["bash_scan"]["files"], 1)
            self.assertRegex(pre["args"]["bash_scan"]["pending"], r"^[0-9a-f]{32}$")   # its pending scan's name


class TestReadmeMatchesCode(unittest.TestCase):
    def test_limits_and_skip_list_in_readme_are_the_real_ones(self):
        import rewindagents
        readme = Path(__file__).resolve().parent.parent.joinpath("README.md").read_text()
        self.assertIn(f"more than {bashscan.MAX_SCAN_FILES:,} files", readme)
        self.assertIn(f"Files over {bashscan.MAX_CHECKPOINT_BYTES // (1024 * 1024)} MB", readme)
        for d in bashscan.SKIP_DIRS:
            self.assertIn(f"`{d}`", readme)
        self.assertIn(f"v{rewindagents.__version__},", readme)


class TestRealHookProcess(unittest.TestCase):
    def test_real_sed_and_rm_undone_through_the_installed_command_path(self):
        with TemporaryDirectory() as d:
            Path(d, "app.py").write_text("x = 1\n")
            Path(d, "data.csv").write_text("a,b\n")
            env = dict(os.environ, PYTHONPATH=str(SRC))
            cmd = "sed -i.bak s/1/2/ app.py && rm data.csv && rm app.py.bak"

            def hook_call(event):
                payload = {"session_id": "real", "cwd": d, "hook_event_name": event, "tool_name": "Bash",
                           "tool_input": {"command": cmd}, "tool_use_id": "toolu_1"}
                p = subprocess.run([sys.executable, "-m", "rewindagents", "hook"], input=json.dumps(payload),
                                   capture_output=True, text=True, cwd=d, env=env)
                self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "", ""))
            hook_call("PreToolUse")
            subprocess.run(["sh", "-c", cmd], cwd=d, check=True)
            hook_call("PostToolUse")
            self.assertEqual(Path(d, "app.py").read_text(), "x = 2\n")
            self.assertFalse(Path(d, "data.csv").exists())
            p = subprocess.run([sys.executable, "-m", "rewindagents", "rewind", "0"], cwd=d, env=env,
                               capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(Path(d, "app.py").read_text(), "x = 1\n")
            self.assertEqual(Path(d, "data.csv").read_text(), "a,b\n")
            self.assertFalse(Path(d, "app.py.bak").exists())
            self.assertNotIn("not scanned", p.stdout)


if __name__ == "__main__":
    unittest.main()
