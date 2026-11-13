"""The README documents the three launch fixes where users look (the "Replay, rewind, branch" section), and
every flag it names there is one the command actually takes."""
import io
import re
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from rewindagents.cli import main  # noqa: E402


def section(title: str) -> str:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    start = text.index(f"## {title}\n")
    end = text.find("\n## ", start + 1)
    return " ".join(text[start:end].split())


def help_of(*cmd: str) -> str:
    buf = io.StringIO()
    with redirect_stdout(buf):
        try:
            main([*cmd, "--help"])
        except SystemExit:
            pass
    return " ".join(buf.getvalue().split())


class TestReadme(unittest.TestCase):
    def setUp(self):
        self.s = section("Replay, rewind, branch")

    def test_overwrite_refusal_and_force(self):
        self.assertIn("A rewind does not silently overwrite later work.", self.s)
        self.assertIn("`rewind N` and `branch N` refuse and change nothing; `--force`", self.s)
        self.assertIn("`fork N` changes nothing in the project, so it only warns", self.s)
        self.assertIn("--force", help_of("rewind"))
        self.assertIn("--force", help_of("branch"))

    def test_replay_redaction_and_its_flag(self):
        self.assertRegex(self.s, r"`replay` replaces secrets the way `export` does")
        self.assertIn("`--no-redact` shows them as recorded", self.s)
        self.assertIn("--no-redact", help_of("replay"))

    def test_exit_codes(self):
        self.assertIn("Exit codes, the same in every command: 0", self.s)
        m = re.search(r"A step number the session does not have is a bad argument in (.+?) alike: exit 2", self.s)
        self.assertIsNotNone(m)
        for cmd in ("replay --step", "rewind", "diff", "branch", "fork"):
            self.assertIn(f"`{cmd}`", m.group(1))
        self.assertIn("Exit codes: 0 done; 1", help_of())


if __name__ == "__main__":
    unittest.main()
