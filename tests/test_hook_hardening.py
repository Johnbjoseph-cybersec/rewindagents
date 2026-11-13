"""The real hook process, for every agent, fed broken input: it must exit 0, print exactly the reply that
agent's docs require for that event (agents.AGENTS[...].reply; nothing for most), never print a traceback,
leave the log verifying with no half-written line, and record what it can.

Payload fields are the ones the vendors' pages list (src/rewindagents/agents.py quotes them); the breakage is
ours. No payload shape here is claimed to be one a live agent sends.
"""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from rewindagents import agents, log  # noqa: E402

SHELL = {"claude": "Bash", "codex": "Bash", "cursor": "Shell", "gemini": "run_shell_command", "copilot": "bash",
         "droid": "Execute", "qwen": "run_shell_command"}


def payload(agent, cwd, when, tool=None, tool_input=None, response=None):
    """A documented-shape payload for `agent` (when = "pre" or "post")."""
    ag = agents.AGENTS[agent]
    p = {"hook_event_name": ag.events[0 if when == "pre" else 1], "cwd": str(cwd),
         "tool_name": tool or SHELL[agent], "tool_input": {"command": "ls"} if tool_input is None else tool_input}
    if agent == "cursor":
        p.update(conversation_id="conv-1", generation_id="gen-1", workspace_roots=[str(cwd)], tool_use_id="t1")
        if when == "post":
            p["tool_output"] = json.dumps(response if response is not None else {"output": "", "exit_code": 0})
        return p
    p["session_id"] = "s-1"
    if agent in ("claude", "codex", "qwen"):
        p["tool_use_id"] = "t1"
    if when == "post":
        if agent == "copilot":
            p["tool_result"] = {"result_type": "success", "text_result_for_llm": response or "ok"}
        else:
            p["tool_response"] = response if response is not None else {"output": "ok"}
    return p


def run_hook(stdin, cwd, agent):
    env = dict(os.environ, PYTHONPATH=str(SRC))
    data = stdin if isinstance(stdin, bytes) else stdin.encode("utf-8")
    return subprocess.run([sys.executable, "-m", "rewindagents", "hook", "--agent", agent], input=data,
                          capture_output=True, cwd=cwd, env=env, timeout=120)


def reply(agent, event):
    r = agents.AGENTS[agent].reply
    text = r.get(event, r.get("unknown", ""))
    return (text + "\n").encode() if text else b""


def records(d):
    f = Path(d, ".rewindagents", "log.jsonl")
    return log.read(f) if f.exists() else []


class Broken(unittest.TestCase):
    def check(self, agent, d, stdin, event, recorded):
        """Run the hook once; assert exit 0, the exact reply, no traceback, a whole and verifying log, and
        whether one record was added."""
        before = len(records(d))
        p = run_hook(stdin, d, agent)
        what = f"{agent}: {stdin[:80]!r}"
        self.assertEqual(p.returncode, 0, what)
        self.assertEqual(p.stdout, reply(agent, event), what + " " + p.stderr.decode(errors="replace"))
        self.assertNotIn(b"Traceback", p.stdout + p.stderr, what)
        f = Path(d, ".rewindagents", "log.jsonl")
        if f.exists():
            raw = f.read_bytes()
            self.assertTrue(raw == b"" or raw.endswith(b"\n"), what + ": a half-written line")
            ok, n, msg = log.verify(f)
            self.assertTrue(ok, what + ": " + msg)
        self.assertEqual(len(records(d)), before + (1 if recorded else 0), what + " " + p.stderr.decode())
        if not recorded:
            self.assertIn(b"not recorded", p.stderr, what)
        return records(d)[-1] if recorded else None

    def test_unreadable_input_records_nothing_and_still_answers(self):
        for agent in agents.AGENTS:
            with self.subTest(agent=agent), TemporaryDirectory() as d:
                good = json.dumps(payload(agent, d, "pre"))
                self.check(agent, d, good, "pre", True)
                for bad in ("", "   \n", good[: len(good) // 2], "[1, 2]", "null", "42", '"text"',
                            b'{"hook_event_name": "x", "cwd": "\xff\xfe'):
                    self.check(agent, d, bad, "unknown", False)

    def test_wrong_types_are_recorded_under_safe_names(self):
        for agent in agents.AGENTS:
            with self.subTest(agent=agent), TemporaryDirectory() as d:
                p = payload(agent, d, "pre", tool_input="ls -la")          # tool_input a string
                r = self.check(agent, d, json.dumps(p), "pre", True)
                self.assertEqual(r["args"]["input"], "ls -la")
                p = payload(agent, d, "pre")
                p["tool_name"] = {"name": SHELL[agent]}                      # tool_name not a string
                r = self.check(agent, d, json.dumps(p), "pre", True)
                self.assertIsInstance(r["tool"], str)
                p = payload(agent, d, "pre")
                p.pop("session_id", None)
                p.pop("conversation_id", None)                               # no session id at all
                r = self.check(agent, d, json.dumps(p), "pre", True)
                self.assertEqual(r["session"], "unknown")
                p = payload(agent, d, "pre")
                p["session_id" if agent != "cursor" else "conversation_id"] = {"id": 7}   # session not a string
                r = self.check(agent, d, json.dumps(p), "pre", True)
                self.assertIsInstance(r["session"], str)
                p = payload(agent, d, "pre")
                p["hook_event_name"] = ["PreToolUse"]                        # event not a string
                r = self.check(agent, d, json.dumps(p), "unknown", True)
                self.assertEqual(r["event"], "unknown")

    def test_a_cwd_that_is_a_number_falls_back_to_where_the_hook_runs(self):
        for agent in agents.AGENTS:
            with self.subTest(agent=agent), TemporaryDirectory() as d:
                p = payload(agent, d, "pre")
                p["cwd"] = 42
                p.pop("workspace_roots", None)
                self.check(agent, d, json.dumps(p), "pre", True)
                self.assertFalse(Path(d, "42").exists())

    def test_a_cwd_that_does_not_exist_is_not_created(self):
        for agent in agents.AGENTS:
            with self.subTest(agent=agent), TemporaryDirectory() as d:
                gone = Path(d, "no", "such", "project")
                p = payload(agent, gone, "pre")
                self.check(agent, d, json.dumps(p), "pre", False)
                self.assertFalse(Path(d, "no").exists(), "the hook made directories for a project that is not there")

    def test_strings_that_are_not_valid_unicode_are_recorded(self):
        for agent in agents.AGENTS:
            with self.subTest(agent=agent), TemporaryDirectory() as d:
                p = payload(agent, d, "pre", tool_input={"command": "echo X"})
                raw = json.dumps(p).replace("echo X", "echo \\udc80\\ud800 end").encode()   # lone surrogates
                r = self.check(agent, d, raw, "pre", True)
                self.assertEqual(r["args"]["input"]["command"], "echo �� end")
                raw = json.dumps(p).encode().replace(b"echo X", b"echo \xff\xfe end")    # bytes that are not UTF-8
                r = self.check(agent, d, raw, "pre", True)
                self.assertEqual(r["args"]["input"]["command"], "echo �� end")

    def test_a_ten_megabyte_response_is_recorded_clipped(self):
        for agent in agents.AGENTS:
            with self.subTest(agent=agent), TemporaryDirectory() as d:
                self.check(agent, d, json.dumps(payload(agent, d, "pre")), "pre", True)
                big = "x" * (10 * 1024 * 1024)
                resp = big if agent == "copilot" else {"output": big}
                r = self.check(agent, d, json.dumps(payload(agent, d, "post", response=resp)), "post", True)
                self.assertTrue(r["result"]["truncated"])
                self.assertLess(Path(d, ".rewindagents", "log.jsonl").stat().st_size, 1024 * 1024)

    def test_a_post_with_no_matching_pre_is_recorded_as_unscanned(self):
        for agent in agents.AGENTS:
            with self.subTest(agent=agent), TemporaryDirectory() as d:
                r = self.check(agent, d, json.dumps(payload(agent, d, "post")), "post", True)
                self.assertEqual(r["args"]["bash_scan"], {"skipped": "no scan from before the command"})


if __name__ == "__main__":
    unittest.main()
