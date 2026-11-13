"""`rewindagents diff N [PATH ...]`: the unified diff from the files now to what `rewind N` would leave."""
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_rewind import Agent, cli  # noqa: E402

from rewindagents import diff, rewind  # noqa: E402


def dry_run_files(out: str) -> list[str]:
    """The file column of `rewind N --dry-run`: restore, delete and CANNOT lines."""
    return [m.group(2) for m in re.finditer(r"^  (restore|delete|CANNOT)\s+([^:\n]+?)(?::.*)?$", out, re.M)]


def diff_files(out: str, err: str) -> list[str]:
    """The files a diff names: one `diff --git` header each, plus the CANNOT lines on stderr."""
    return re.findall(r"^diff --git a/(\S+) b/", out, re.M) + re.findall(r"CANNOT (\S+):", err)


class TestDiff(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.d = Path(self.tmp.name).resolve()
        self.a = Agent(self.d)
        self.a.write("app.py", "a\nb\nc\n")          # step 1
        self.a.write("README", "hello\n")            # step 2
        self.a.write("app.py", "a\nB\nc\n")          # step 3
        self.a.write("new.py", "junk\n")             # step 4: creates a file
        self.a.write("README", "hello")              # step 5: drops the final newline
        self.log = str(self.a.log)

    def tearDown(self):
        self.tmp.cleanup()

    def test_diff_goes_from_now_to_the_rewind_state(self):
        code, out, err = cli("--log", self.log, "diff", "2")
        self.assertEqual(code, 0, err)
        self.assertIn("diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n", out)
        self.assertIn("-B\n+b\n", out)
        self.assertIn("diff --git a/new.py b/new.py\ndeleted file mode 100", out)
        self.assertIn("--- a/new.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-junk\n", out)
        self.assertIn("-hello\n\\ No newline at end of file\n+hello\n", out)

    def test_diff_lists_exactly_the_files_rewind_dry_run_lists(self):
        for n in range(0, 6):
            code_r, out_r, _ = cli("--log", self.log, "rewind", str(n), "--dry-run")
            code_d, out_d, err_d = cli("--log", self.log, "diff", str(n))
            self.assertEqual(sorted(diff_files(out_d, err_d)), sorted(dry_run_files(out_r)), f"step {n}")
            self.assertEqual(code_d, code_r, f"step {n}")
        self.assertEqual(sorted(diff_files(*cli("--log", self.log, "diff", "0")[1:])),
                         ["README", "app.py", "new.py"])

    def test_same_files_with_paths_and_after_a_cannot(self):
        obj = self.d / ".rewindagents" / "objects" / rewind.steps(self.log)[2]["checkpoints"][0]["sha256"]
        obj.write_text("tampered\n")               # step 3's copy of app.py ("a b c") no longer matches
        for args in ([], [str(self.d / "app.py")], [str(self.d / "new.py"), str(self.d / "README")]):
            code_r, out_r, _ = cli("--log", self.log, "rewind", "2", "--dry-run",
                                   *[x for p in args for x in ("--only", p)])
            code_d, out_d, err_d = cli("--log", self.log, "diff", "2", *args)
            self.assertEqual(sorted(diff_files(out_d, err_d)), sorted(dry_run_files(out_r)), args)
            self.assertEqual(code_d, code_r, args)
        _, _, err = cli("--log", self.log, "diff", "2")
        self.assertIn("CANNOT app.py: stored copy missing or altered", err)

    def test_paths_limit_the_diff(self):
        code, out, err = cli("--log", self.log, "diff", "0", str(self.d / "new.py"))
        self.assertEqual(code, 0, err)
        self.assertEqual(re.findall(r"^diff --git a/(\S+)", out, re.M), ["new.py"])

    def test_a_file_rewind_would_create_shows_as_new(self):
        (self.d / "app.py").unlink()               # deleted by hand after the session
        p = diff.diff(self.log, 1, paths=[self.d / "app.py"])   # step 3 changed it after step 1
        text = p["files"][0][1]
        self.assertIn("new file mode 100644\n--- /dev/null\n+++ b/app.py\n@@ -0,0 +1,3 @@\n+a\n+b\n+c\n", text)

    def test_binary_files_are_named_not_dumped(self):
        text = diff.file_diff("img.bin", b"\x00\x01", b"\x00\x02")
        self.assertIn("Binary files a/img.bin and b/img.bin differ", text)

    def test_nothing_to_change_says_so(self):
        code, out, err = cli("--log", self.log, "diff", "5")
        self.assertEqual((code, out), (0, ""))
        self.assertIn("would change nothing", err)

    def test_diff_writes_nothing(self):
        before = self.a.log.read_bytes(), (self.d / "app.py").read_bytes()
        cli("--log", self.log, "diff", "0")
        self.assertEqual((self.a.log.read_bytes(), (self.d / "app.py").read_bytes()), before)

    def test_out_of_range_step_is_an_error(self):
        code, _, err = cli("--log", self.log, "diff", "99")
        self.assertEqual(code, 2)          # a step the session does not have: 2 in every command (test_exit_codes)
        self.assertIn("out of range", err)

    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_git_apply_of_the_diff_does_what_rewind_does(self):
        _, patch, _ = cli("--log", self.log, "diff", "1")
        r = subprocess.run(["git", "apply", "-"], input=patch, text=True, cwd=self.d, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        got = {p: (self.d / p).read_text() if (self.d / p).exists() else None for p in ("app.py", "README", "new.py")}
        self.assertEqual(got, {"app.py": "a\nb\nc\n", "README": None, "new.py": None})


if __name__ == "__main__":
    unittest.main()
