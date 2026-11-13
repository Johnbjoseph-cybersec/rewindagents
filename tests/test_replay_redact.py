"""`replay` redacts secrets by default, as `export` and `bundle` do; `--no-redact` shows them.

FIRST_RUN.md friction 4: `replay` printed `echo 'API_TOKEN=sk-ant-api03-...` and `replay --step 2 --diff`
printed the whole token, while `export` replaced it. Terminal output gets pasted into issues and chats.
"""
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_redact import ANT, BEARER, GH, OAI, secret_session  # noqa: E402
from test_rewind import cli  # noqa: E402


class TestReplayRedacts(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.old = os.getcwd()
        os.chdir(self.tmp.name)
        secret_session(self.tmp.name)

    def tearDown(self):
        os.chdir(self.old)
        self.tmp.cleanup()

    def test_the_step_list_hides_a_token_in_a_command(self):
        code, out, err = cli("replay")
        self.assertEqual(code, 0)
        self.assertNotIn(BEARER, out)
        self.assertIn("[redacted", out)
        self.assertIn("--no-redact shows them", err)

    def test_one_step_hides_the_secrets_in_its_input(self):
        for n, secret in ((1, OAI), (2, GH), (3, BEARER), (4, ANT)):
            code, out, err = cli("replay", "--step", str(n))
            self.assertEqual(code, 0)
            self.assertNotIn(secret, out, f"step {n}")
            self.assertIn("[redacted", out, f"step {n}")

    def test_a_step_diff_hides_the_secrets_on_both_sides(self):
        code, out, err = cli("replay", "--step", "2", "--diff")   # .env: the key changed from OAI to GH
        self.assertEqual(code, 0, err)
        self.assertNotIn(OAI, out)
        self.assertNotIn(GH, out)
        self.assertIn("changed only inside redacted values", out)
        code, out, err = cli("replay", "--step", "4", "--diff")
        self.assertNotIn(ANT, out)
        self.assertIn("+KEY = \"[redacted anthropic key]\"", out)

    def test_no_redact_shows_them_as_recorded(self):
        code, out, err = cli("replay", "--no-redact")
        self.assertIn(BEARER, out)
        self.assertNotIn("--no-redact shows them", err)
        code, out, err = cli("replay", "--step", "4", "--no-redact")
        self.assertIn(ANT, out)
        code, out, err = cli("replay", "--step", "2", "--diff", "--no-redact")
        self.assertIn(OAI, out)
        self.assertIn(GH, out)


if __name__ == "__main__":
    unittest.main()
