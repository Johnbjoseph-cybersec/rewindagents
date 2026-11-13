"""A step number the session does not have exits 2 in every command, with one wording.

FIRST_RUN.md friction 6: `rewind 99` exited 1 ("step 99 is out of range: session ... has 5 steps") and
`replay --step 9` exited 2 ("step 9 is out of range (1-5)"). Exit 2 is what argparse and a missing log already
use for "could not run as asked"; 1 stays for "ran, but something was not done".
"""
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_rewind import Agent, cli  # noqa: E402


class TestOutOfRange(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.old = os.getcwd()
        os.chdir(self.tmp.name)
        a = Agent(Path(self.tmp.name).resolve(), "s1")
        a.write("a.py", "1\n")
        a.write("b.py", "2\n")
        self.before = a.log.read_bytes()
        self.log = a.log

    def tearDown(self):
        os.chdir(self.old)
        self.tmp.cleanup()

    def test_every_command_exits_2_and_says_the_range(self):
        dest = str(Path(self.tmp.name).resolve()) + "-run"
        cases = {
            ("replay", "--step", "9"): "use 1-2",
            ("replay", "--step", "0"): "use 1-2",
            ("replay", "--step", "9", "--diff"): "use 1-2",
            ("rewind", "99"): "use 0-2",
            ("rewind", "99", "--dry-run"): "use 0-2",
            ("rewind", "-1"): "use 0-2",
            ("diff", "99"): "use 0-2",
            ("branch", "99", "--name", "x"): "use 0-2",
            ("fork", "99", "--name", "x", "--dir", dest): "use 0-2",
        }
        for args, rng in cases.items():
            code, out, err = cli(*args)
            self.assertEqual(code, 2, f"{args}: {err}")
            self.assertIn("step", err)
            self.assertIn("is out of range: session s1 has 2 steps, so " + rng, err, args)
        self.assertEqual(self.log.read_bytes(), self.before)       # nothing recorded
        self.assertFalse(Path(dest).exists())

    def test_a_name_that_matches_nothing_or_is_taken_exits_1(self):
        # README "Exit codes": exit 2 is for options it cannot parse, step numbers and a missing log; a --session,
        # run, --name or --dir that matches nothing, is taken or is not allowed exits 1 and says why
        root = Path(self.tmp.name).resolve()
        dest = str(root) + "-run"
        cases = [
            (("replay", "--session", "nope"), "no session 'nope'"),
            (("rewind", "0", "--session", "nope"), "no session 'nope'"),
            (("fork", "1", "--name", "bad name!", "--dir", dest), "not a run name"),
            (("fork", "1", "--name", "x", "--dir", str(root / "sub")), "inside the project"),
            (("compare", "zz"), "no run"),
        ]
        for args, says in cases:
            code, out, err = cli(*args)
            self.assertEqual(code, 1, f"{args}: {err}")
            self.assertIn(says, err, args)
        self.assertEqual(self.log.read_bytes(), self.before)       # nothing recorded
        self.assertFalse(Path(dest).exists())
        code, out, err = cli("fork", "1", "--name", "x", "--dir", dest)
        self.assertEqual(code, 0, err)
        code, out, err = cli("fork", "1", "--name", "x", "--dir", dest + "2")
        self.assertEqual(code, 1, err)
        self.assertIn("already has a run named 'x'", err)

    def test_help_documents_the_exit_codes(self):
        import io
        from contextlib import redirect_stdout
        from rewindagents.cli import main
        buf = io.StringIO()
        with redirect_stdout(buf), self.assertRaises(SystemExit):
            main(["--help"])
        self.assertIn("Exit codes: 0 done; 1", " ".join(buf.getvalue().split()))


if __name__ == "__main__":
    unittest.main()
