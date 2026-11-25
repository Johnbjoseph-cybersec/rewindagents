"""`guard`: protected files. The hook never blocks, but on a guarded change Claude Code gets a systemMessage
(to the user) and additionalContext (to the agent); other agents keep their fixed stdout reply and get the
warning on stderr. `guard --check` lists guarded files still changed; `undo --only FILE` takes back the last
change to that file."""
import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from rewindagents import guard, hook  # noqa: E402
from rewindagents.cli import main  # noqa: E402


def cli(*args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(list(args))
    return code, out.getvalue(), err.getvalue()


def run_hook(payload, agent="claude"):
    """The real entry point (`python -m rewindagents hook`), stdin -> stdout/stderr."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = hook.run(io.StringIO(json.dumps(payload)), agent=agent)
    return code, out.getvalue(), err.getvalue()


class Project:
    def __init__(self, d):
        self.d = Path(d)
        self.log = self.d / ".rewindagents" / "log.jsonl"

    def p(self, event, tool, inp, resp=None, session="s1"):
        x = {"session_id": session, "cwd": str(self.d), "hook_event_name": event, "tool_name": tool,
             "tool_input": inp}
        if resp is not None:
            x["tool_response"] = resp
        return x

    def write(self, name, text, agent="claude"):
        inp = {"file_path": str(self.d / name), "content": text}
        run_hook(self.p("PreToolUse", "Write", inp), agent)
        (self.d / name).parent.mkdir(parents=True, exist_ok=True)
        (self.d / name).write_text(text)
        return run_hook(self.p("PostToolUse", "Write", inp, {"ok": True}), agent)

    def bash(self, command, action, agent="claude"):
        inp = {"command": command}
        run_hook(self.p("PreToolUse", "Bash", inp), agent)
        action(self.d)
        return run_hook(self.p("PostToolUse", "Bash", inp, {"stdout": ""}), agent)


class TestMatch(unittest.TestCase):
    def test_patterns(self):
        pats = [".env", "secrets/", "*.pem", "config"]
        self.assertEqual(guard.match(".env", pats), ".env")
        self.assertEqual(guard.match("secrets/db.txt", pats), "secrets/")
        self.assertEqual(guard.match("keys/server.pem", pats), "*.pem")
        self.assertEqual(guard.match("config/app.yml", pats), "config")   # a bare name covers a directory
        self.assertIsNone(guard.match("src/.env.example", pats))
        self.assertIsNone(guard.match("app.py", pats))

    def test_normalize_strips_dot_slash(self):
        self.assertEqual(guard.normalize("./.env"), ".env")


class TestGuardHook(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.pr = Project(self.tmp.name)
        (self.pr.d / ".env").write_text("KEY=original\n")
        self.pr.write("app.py", "v1")                          # step 1 (creates the log)
        code, _, _ = cli("--log", str(self.pr.log), "guard", ".env", "secrets/")
        self.assertEqual(code, 0)

    def tearDown(self):
        self.tmp.cleanup()

    def test_unguarded_change_prints_nothing_for_claude(self):
        code, out, err = self.pr.write("app.py", "v2")
        self.assertEqual((code, out), (0, ""))                 # no change to the normal contract

    def test_guarded_bash_change_warns_user_and_agent_in_claude_code(self):
        code, out, _ = self.pr.bash("echo KEY=leaked > .env", lambda d: (d / ".env").write_text("KEY=leaked\n"))
        self.assertEqual(code, 0)                               # never blocks
        reply = json.loads(out)
        self.assertIn(".env", reply["systemMessage"])
        self.assertIn("undo --only .env", reply["systemMessage"])
        self.assertEqual(reply["hookSpecificOutput"]["hookEventName"], "PostToolUse")
        self.assertIn("guarded", reply["hookSpecificOutput"]["additionalContext"])

    def test_guarded_write_into_a_guarded_directory_warns(self):
        code, out, _ = self.pr.write("secrets/token.txt", "abc")
        self.assertIn("secrets/token.txt", json.loads(out)["systemMessage"])

    def test_other_agents_keep_their_stdout_reply_and_get_stderr(self):
        code, out, err = self.pr.bash("echo x > .env", lambda d: (d / ".env").write_text("x\n"), agent="cursor")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "{}")                    # Cursor's documented post reply, unchanged
        self.assertIn("guarded file: .env", err)

    def test_check_lists_the_guarded_file_and_undo_only_puts_it_back(self):
        self.pr.bash("echo KEY=leaked > .env", lambda d: (d / ".env").write_text("KEY=leaked\n"))
        self.pr.write("app.py", "v2")                           # a later, unrelated change
        code, out, _ = cli("--log", str(self.pr.log), "guard", "--check")
        self.assertEqual(code, 1)
        self.assertIn(".env", out)
        code, _, _ = cli("--log", str(self.pr.log), "undo", "--only", str(self.pr.d / ".env"))
        self.assertEqual(code, 0)
        self.assertEqual((self.pr.d / ".env").read_text(), "KEY=original\n")
        self.assertEqual((self.pr.d / "app.py").read_text(), "v2")   # the later change is kept
        code, out, _ = cli("--log", str(self.pr.log), "guard", "--check")
        self.assertEqual(code, 0)

    def test_list_and_unguard(self):
        _, out, _ = cli("--log", str(self.pr.log), "guard")
        self.assertIn(".env", out)
        self.assertEqual(cli("--log", str(self.pr.log), "unguard", ".env")[0], 0)
        self.assertEqual(cli("--log", str(self.pr.log), "unguard", ".env")[0], 1)
        code, out, _ = self.pr.bash("echo x > .env", lambda d: (d / ".env").write_text("x\n"))
        self.assertEqual(out, "")                               # no longer guarded

    def test_a_broken_guard_file_never_costs_the_recording(self):
        (self.pr.d / ".rewindagents" / "guard.json").write_text("{not json")
        before = len(self.pr.log.read_text().splitlines())
        code, out, _ = self.pr.write("app.py", "v3")
        self.assertEqual((code, out), (0, ""))
        self.assertEqual(len(self.pr.log.read_text().splitlines()), before + 2)


if __name__ == "__main__":
    unittest.main()
