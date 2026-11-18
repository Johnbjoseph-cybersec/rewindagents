"""`python -m rewindagents hook` runs twice per tool call: it must not import the CLI or anything else the hook does not use."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
PAYLOAD = {"hook_event_name": "PreToolUse", "session_id": "s", "tool_name": "Read", "tool_input": {"file_path": "x"}}


def run_hook(argv, cwd):
    env = dict(os.environ, PYTHONPATH=str(SRC))
    return subprocess.run([sys.executable] + argv, input=json.dumps(dict(PAYLOAD, cwd=str(cwd))), text=True,
                          capture_output=True, cwd=cwd, env=env)


class FastPath(unittest.TestCase):
    def test_hook_does_not_import_cli_or_its_modules(self):
        with tempfile.TemporaryDirectory() as d:
            probe = ("import sys, runpy; sys.argv = ['rewindagents', 'hook']\n"
                     "try:\n    runpy.run_module('rewindagents', run_name='__main__', alter_sys=True)\n"
                     "except SystemExit:\n    pass\n"
                     "bad = [m for m in ('rewindagents.cli', 'rewindagents.rewind', 'rewindagents.bundle', 'rewindagents.export',"
                     " 'argparse', 'subprocess', 'tempfile', 'shutil') if m in sys.modules]\n"
                     "sys.stderr.write('IMPORTED' + (' ' + ','.join(bad) if bad else ''))\n")
            p = run_hook(["-c", probe], d)
            self.assertEqual(p.stderr.strip(), "IMPORTED")

    def test_hook_forms_record_and_exit_zero(self):
        for argv in (["-m", "rewindagents", "hook"], ["-m", "rewindagents", "hook", "--agent", "claude"],
                     ["-m", "rewindagents", "hook", "--agent=claude"], [str(SRC / "rewindagents" / "__main__.py"), "hook"]):
            with self.subTest(argv=argv), tempfile.TemporaryDirectory() as d:
                p = run_hook(argv, d)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertEqual(len(Path(d, ".rewindagents", "log.jsonl").read_text().splitlines()), 1)

    def test_cursor_and_gemini_answers_unchanged(self):
        for agent, want in (("gemini", "{}\n"),):
            with tempfile.TemporaryDirectory() as d:
                p = run_hook(["-m", "rewindagents", "hook", "--agent", agent], d)
                self.assertEqual((p.returncode, p.stdout), (0, want))

    def test_bad_agent_still_goes_through_argparse(self):
        with tempfile.TemporaryDirectory() as d:
            p = run_hook(["-m", "rewindagents", "hook", "--agent", "nope"], d)
            self.assertEqual(p.returncode, 2)
            self.assertIn("invalid choice", p.stderr)

    def test_package_attributes_still_import(self):
        sys.path.insert(0, str(SRC))
        import rewindagents
        from rewindagents import GENESIS, Recorder, head, read, verify  # noqa: F401
        self.assertRegex(rewindagents.__version__, r"^\d+\.\d+\.\d+$")  # any release; never pin a number here
        self.assertIs(rewindagents.Recorder, Recorder)
        with self.assertRaises(AttributeError):
            rewindagents.nope


if __name__ == "__main__":
    unittest.main()
