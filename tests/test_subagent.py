"""Subagent steps (RB6): Claude Code's hooks doc says a subagent's tool calls fire the same PreToolUse and
PostToolUse hooks as the main conversation, with `agent_id` and `agent_type` added to the input
(https://code.claude.com/docs/en/hooks, "Hook locations", read 2026-11-12). Its checkpointing doc says those
edits are usually not in the session's checkpoints. The README's first screen claims rewindagents takes them back;
this test drives the real hook process with payloads shaped that way and rewinds them. Stdlib only."""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from rewindagents import rewind, verify  # noqa: E402

SUBAGENT = {"agent_id": "a7f3c2", "agent_type": "general-purpose"}


def call(cwd, event, tool, tool_input, response=None, sub=False, use_id=None):
    p = {"session_id": "s1", "cwd": str(cwd), "hook_event_name": event, "tool_name": tool, "tool_input": tool_input}
    if response is not None:
        p["tool_response"] = response
    if sub:
        p.update(SUBAGENT)
    if use_id:
        p["tool_use_id"] = use_id
    env = dict(os.environ, PYTHONPATH=str(SRC))
    r = subprocess.run([sys.executable, "-m", "rewindagents", "hook"], input=json.dumps(p),
                       capture_output=True, text=True, cwd=cwd, env=env)
    assert (r.returncode, r.stdout) == (0, ""), (r.returncode, r.stdout, r.stderr)


def write(cwd, name, text, sub=False):
    inp = {"file_path": str(Path(cwd, name)), "content": text}
    call(cwd, "PreToolUse", "Write", inp, sub=sub)
    Path(cwd, name).write_text(text)
    call(cwd, "PostToolUse", "Write", inp, {"ok": True}, sub=sub)


class TestSubagentSteps(unittest.TestCase):
    def test_subagent_edit_and_shell_delete_are_rewound(self):
        with TemporaryDirectory() as d:
            Path(d, "tests.py").write_text("assert True\n")
            write(d, "app.py", "v1\n")                                   # step 1, main conversation
            write(d, "config.toml", "debug = false\n", sub=True)         # step 2, subagent creates a file
            inp = {"command": "rm tests.py"}
            call(d, "PreToolUse", "Bash", inp, sub=True, use_id="toolu_1")
            Path(d, "tests.py").unlink()                                 # step 3, subagent's shell command
            call(d, "PostToolUse", "Bash", inp, {"stdout": ""}, sub=True, use_id="toolu_1")

            log = Path(d, ".rewindagents", "log.jsonl")
            self.assertTrue(verify(log)[0])
            steps = rewind.steps(log)
            self.assertEqual([s["tool"] for s in steps], ["Write", "Write", "Bash"], "one session, three steps")
            self.assertEqual(steps[2]["bash_scan"], {"changed": 1})

            p = rewind.rewind(log, 1)
            self.assertEqual((p["cannot"], p["bash_uncovered"]), ([], 0))
            self.assertEqual(Path(d, "tests.py").read_text(), "assert True\n")
            self.assertFalse(Path(d, "config.toml").exists())
            self.assertEqual(Path(d, "app.py").read_text(), "v1\n")


if __name__ == "__main__":
    unittest.main()
