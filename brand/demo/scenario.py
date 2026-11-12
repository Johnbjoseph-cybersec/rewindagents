"""The demo session behind brand/demo.gif (task RB2b), shared by the builder and its test.

`play(root)` makes a small project in `root` (a git repo with one commit), runs fourteen agent steps
through the real Claude Code hook the way Claude Code drives it (pre record, the change, post record;
Bash commands really run), then runs the four commands the clip shows and returns what each printed.
The last two agent steps wreck the project: `rm -rf tests`, then a Write that overwrites app/config.py.
`rewindagents rewind 12` puts the files back the way they were right after step 12.

brand/demo/build.py draws the frames from this record; tests/test_demo.py plays the same session again
and compares every line, so the GIF cannot show output the code does not produce.
"""
from __future__ import annotations

import io
import os
import subprocess
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from rewindagents import hook
from rewindagents.cli import main as cli_main

SESSION = "demo"
WRECK_STEPS = 2          # the last two agent steps undo the work

TEST_CONFIG = '''import unittest

from app.config import HOST, PORT


class ConfigTest(unittest.TestCase):
    def test_port_is_a_number(self):
        self.assertIsInstance(PORT, int)

    def test_host_is_local(self):
        self.assertEqual(HOST, "127.0.0.1")
'''

TEST_SERVER = '''import unittest

from app.server import serve


class ServerTest(unittest.TestCase):
    def test_serve_names_the_address(self):
        self.assertIn("127.0.0.1:8080", serve())
'''

TEST_TIMEOUT = '''import unittest

from app.config import TIMEOUT


class TimeoutTest(unittest.TestCase):
    def test_timeout_is_set(self):
        self.assertEqual(TIMEOUT, 30)
'''

FILES = {
    "README.md": "# tally\n\nA small counter service.\n",
    ".gitignore": "__pycache__/\n",
    "app/__init__.py": "",
    "app/config.py": 'HOST = "127.0.0.1"\nPORT = 8080\nDEBUG = False\n',
    "app/server.py": 'from app.config import HOST, PORT\n\n\ndef serve():\n    return f"listening on {HOST}:{PORT}"\n',
    "tests/test_config.py": TEST_CONFIG,
    "tests/test_server.py": TEST_SERVER,
}

TEST_CMD = "python3 -m unittest discover -s tests -t . -q"

# (tool, spec): Read -> path; Edit -> (path, old, new); Write -> (path, content); Bash -> command
STEPS = [
    ("Read", "README.md"),
    ("Read", "app/config.py"),
    ("Edit", ("app/config.py", "DEBUG = False\n", "DEBUG = False\nTIMEOUT = 30\n")),
    ("Read", "app/server.py"),
    ("Edit", ("app/server.py", "import HOST, PORT\n", "import HOST, PORT, TIMEOUT\n")),
    ("Write", ("tests/test_timeout.py", TEST_TIMEOUT)),
    ("Bash", TEST_CMD),
    ("Edit", ("app/server.py", '{HOST}:{PORT}"', '{HOST}:{PORT}, timeout {TIMEOUT}s"')),
    ("Bash", TEST_CMD),
    ("Edit", ("README.md", "A small counter service.\n",
              "A small counter service.\n\nRequests time out after 30 seconds.\n")),
    ("Bash", "git status --short"),
    ("Read", "tests/test_server.py"),
    ("Bash", "rm -rf tests"),
    ("Write", ("app/config.py", 'HOST = "0.0.0.0"\nPORT = 80\n')),
]
GOOD_STEP = len(STEPS) - WRECK_STEPS

# The commands the clip shows, in order. `hold` is how long the finished output stays on screen.
# `accent`: which output lines are drawn in the accent colour (one block per view).
SHOWN = [
    {"caption": "# a coding agent has been working in this repo; rewindagents recorded every step",
     "command": "rewindagents replay", "hold": 2.40, "stream": True, "accent": "wreck"},
    {"caption": "# its last two steps deleted the tests and overwrote the config",
     "command": "git status --short", "hold": 2.00},
    {"caption": "# put the files back the way they were right after step %d" % GOOD_STEP,
     "command": "rewindagents rewind %d" % GOOD_STEP, "hold": 2.80, "accent": "restore"},
    {"caption": "# the tests are back; the first %d steps stay" % GOOD_STEP,
     "command": "git status --short", "hold": 3.20},
]

GIT_ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
               GIT_AUTHOR_NAME="demo", GIT_AUTHOR_EMAIL="demo@localhost",
               GIT_COMMITTER_NAME="demo", GIT_COMMITTER_EMAIL="demo@localhost")


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], env=GIT_ENV, capture_output=True, text=True,
                          check=True).stdout


def make_project(root: Path) -> None:
    for rel, text in FILES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    git(root, "init", "-q", "--initial-branch=main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "initial")


class Agent:
    """Drives the real hook the way Claude Code does: pre record, the change, post record."""

    def __init__(self, root: Path):
        self.root, self.n = root, 0

    def _p(self, event: str, tool: str, inp: dict, response=None) -> dict:
        p = {"session_id": SESSION, "cwd": str(self.root), "hook_event_name": event, "tool_name": tool,
             "tool_input": inp, "tool_use_id": "toolu_demo_%02d" % self.n}
        if response is not None:
            p["tool_response"] = response
        return p

    def step(self, tool: str, spec) -> None:
        self.n += 1
        if tool == "Read":
            path = self.root / spec
            inp = {"file_path": str(path)}
            hook.handle(self._p("PreToolUse", tool, inp))
            text = path.read_text(encoding="utf-8")
            hook.handle(self._p("PostToolUse", tool, inp, {"file": {"filePath": str(path), "content": text}}))
        elif tool == "Edit":
            rel, old, new = spec
            path = self.root / rel
            inp = {"file_path": str(path), "old_string": old, "new_string": new}
            hook.handle(self._p("PreToolUse", tool, inp))
            text = path.read_text(encoding="utf-8")
            if text.count(old) != 1:
                raise ValueError("edit target is not unique in %s: %r" % (rel, old))
            path.write_text(text.replace(old, new), encoding="utf-8")
            hook.handle(self._p("PostToolUse", tool, inp, {"filePath": str(path), "success": True}))
        elif tool == "Write":
            rel, content = spec
            path = self.root / rel
            inp = {"file_path": str(path), "content": content}
            hook.handle(self._p("PreToolUse", tool, inp))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            hook.handle(self._p("PostToolUse", tool, inp, {"filePath": str(path), "success": True}))
        elif tool == "Bash":
            inp = {"command": spec}
            hook.handle(self._p("PreToolUse", tool, inp))
            r = subprocess.run(spec, shell=True, cwd=self.root, env=GIT_ENV, capture_output=True, text=True)
            hook.handle(self._p("PostToolUse", tool, inp,
                                {"stdout": r.stdout, "stderr": r.stderr, "interrupted": False}))
        else:
            raise ValueError(tool)


def run_shown(root: Path, command: str) -> tuple[str, int]:
    """Run one shown command from the project directory; return (what it printed, exit code)."""
    words = command.split()
    if words[0] == "rewindagents":
        out, err = io.StringIO(), io.StringIO()
        cwd = os.getcwd()
        os.chdir(root)
        try:
            with redirect_stdout(out), redirect_stderr(err):
                code = cli_main(words[1:])
        finally:
            os.chdir(cwd)
        return out.getvalue() + err.getvalue(), code
    if words[0] == "git":
        r = subprocess.run(words, cwd=root, env=GIT_ENV, capture_output=True, text=True)
        return r.stdout + r.stderr, r.returncode
    raise ValueError("the demo only shows rewindagents and git commands: %r" % command)


def accent_rows(beat: dict, lines: list[str]) -> list[int]:
    if beat.get("accent") == "wreck":
        return list(range(len(lines) - WRECK_STEPS, len(lines)))
    if beat.get("accent") == "restore":
        return [i for i, line in enumerate(lines) if line.startswith("  restore")]
    return []


def play(root) -> list[dict]:
    """Make the project, run the agent session, run the shown commands. Returns SHOWN with the output,
    exit code and accent rows of each command added."""
    root = Path(os.path.realpath(root))
    make_project(root)
    agent = Agent(root)
    for tool, spec in STEPS:
        agent.step(tool, spec)
    out = []
    for beat in SHOWN:
        text, code = run_shown(root, beat["command"])
        lines = text.rstrip("\n").split("\n") if text.strip() else []
        out.append(dict(beat, output=text, exit=code, accent_rows=accent_rows(beat, lines)))
    return out
