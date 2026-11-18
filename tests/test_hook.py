import hashlib
import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from rewindagents import hook, read, verify  # noqa: E402

# A POSIX-shaped interpreter path, used where a test means "assume the interpreter is POSIX": the real
# sys.executable is itself a Windows path on windows-latest CI, same stand-in test_windows_hook.py uses (R94).
POSIX_PY = "/usr/bin/python3"


def payload(cwd, event, tool, tool_input, response=None, session="s1"):
    p = {"session_id": session, "cwd": str(cwd), "hook_event_name": event,
         "tool_name": tool, "tool_input": tool_input}
    if response is not None:
        p["tool_response"] = response
    return p


def run_hook_process(stdin_text, cwd):
    env = dict(os.environ, PYTHONPATH=str(SRC))
    return subprocess.run([sys.executable, "-m", "rewindagents", "hook"], input=stdin_text,
                          capture_output=True, text=True, cwd=cwd, env=env)


class TestCheckpoint(unittest.TestCase):
    def test_edit_checkpoints_the_bytes_before_the_change(self):
        with TemporaryDirectory() as d:
            f = Path(d, "app.py")
            f.write_text("print('v1')\n", newline="")
            rec = hook.handle(payload(d, "PreToolUse", "Edit", {"file_path": str(f)}))
            cp = rec["args"]["checkpoint"]
            self.assertEqual(cp["sha256"], hashlib.sha256(b"print('v1')\n").hexdigest())
            f.write_text("print('broken')\n", newline="")   # the agent's change happens after the hook
            saved = Path(d, ".rewindagents", "objects", cp["sha256"]).read_bytes()
            self.assertEqual(saved, b"print('v1')\n")

    def test_relative_path_resolved_against_cwd(self):
        with TemporaryDirectory() as d:
            Path(d, "a.txt").write_text("x", newline="")
            rec = hook.handle(payload(d, "PreToolUse", "Write", {"file_path": "a.txt"}))
            self.assertEqual(rec["args"]["checkpoint"]["path"], str(Path(d, "a.txt")))
            self.assertIsNotNone(rec["args"]["checkpoint"]["sha256"])

    def test_new_file_recorded_as_absent(self):
        with TemporaryDirectory() as d:
            rec = hook.handle(payload(d, "PreToolUse", "Write", {"file_path": str(Path(d, "new.py"))}))
            self.assertIsNone(rec["args"]["checkpoint"]["sha256"])
            self.assertNotIn("size", rec["args"]["checkpoint"])

    def test_notebook_edit_uses_notebook_path(self):
        with TemporaryDirectory() as d:
            nb = Path(d, "n.ipynb")
            nb.write_text("{}", newline="")
            rec = hook.handle(payload(d, "PreToolUse", "NotebookEdit", {"notebook_path": str(nb)}))
            self.assertEqual(rec["args"]["checkpoint"]["path"], str(nb))

    def test_identical_content_stored_once(self):
        with TemporaryDirectory() as d:
            for name in ("a.txt", "b.txt"):
                Path(d, name).write_text("same", newline="")
                hook.handle(payload(d, "PreToolUse", "Edit", {"file_path": name}))
            objs = [p for p in Path(d, ".rewindagents", "objects").iterdir()]
            self.assertEqual(len(objs), 1)

    def test_oversized_file_skipped_not_stored(self):
        with TemporaryDirectory() as d:
            Path(d, "big.bin").write_bytes(b"0" * 64)
            old = hook.MAX_CHECKPOINT_BYTES
            hook.MAX_CHECKPOINT_BYTES = 10
            try:
                rec = hook.handle(payload(d, "PreToolUse", "Write", {"file_path": "big.bin"}))
            finally:
                hook.MAX_CHECKPOINT_BYTES = old
            self.assertIsNone(rec["args"]["checkpoint"]["sha256"])
            self.assertIn("skipped", rec["args"]["checkpoint"])
            self.assertFalse(Path(d, ".rewindagents", "objects").exists())

    def test_non_file_tool_has_no_checkpoint(self):
        with TemporaryDirectory() as d:
            rec = hook.handle(payload(d, "PreToolUse", "Bash", {"command": "ls"}))
            self.assertNotIn("checkpoint", rec["args"])
            self.assertEqual(rec["args"]["input"], {"command": "ls"})


class TestRecording(unittest.TestCase):
    def test_pre_and_post_form_one_verified_chain(self):
        with TemporaryDirectory() as d:
            hook.handle(payload(d, "PreToolUse", "Bash", {"command": "ls"}))
            hook.handle(payload(d, "PostToolUse", "Bash", {"command": "ls"}, {"stdout": "a.txt"}))
            lg = Path(d, ".rewindagents", "log.jsonl")
            recs = read(lg)
            self.assertEqual([r["event"] for r in recs], ["pre", "post"])
            self.assertEqual(recs[1]["result"], {"stdout": "a.txt"})
            self.assertEqual(verify(lg), (True, 2, "chain intact"))

    def test_store_ignores_itself_in_git(self):
        with TemporaryDirectory() as d:
            hook.handle(payload(d, "PreToolUse", "Bash", {"command": "ls"}))
            self.assertEqual(Path(d, ".rewindagents", ".gitignore").read_text(), "*\n")

    def test_long_response_is_clipped(self):
        with TemporaryDirectory() as d:
            rec = hook.handle(payload(d, "PostToolUse", "Bash", {"command": "x"}, "y" * 10000))
            self.assertTrue(rec["result"]["truncated"])
            self.assertEqual(rec["result"]["chars"], 10000)
            self.assertEqual(len(rec["result"]["head"]), hook.MAX_RESULT_CHARS)


class TestNeverBlocks(unittest.TestCase):
    """Claude Code treats exit 2 or a stdout decision as a block. The hook must produce neither."""

    def test_real_process_records_and_prints_nothing(self):
        with TemporaryDirectory() as d:
            Path(d, "f.txt").write_text("v1", newline="")
            p = run_hook_process(json.dumps(payload(d, "PreToolUse", "Edit", {"file_path": "f.txt"})), d)
            self.assertEqual((p.returncode, p.stdout), (0, ""))
            self.assertEqual(len(read(Path(d, ".rewindagents", "log.jsonl"))), 1)

    def test_garbage_input_exits_zero_silently(self):
        with TemporaryDirectory() as d:
            for bad in ("not json", "[1, 2]", ""):
                p = run_hook_process(bad, d)
                self.assertEqual((p.returncode, p.stdout), (0, ""), bad)
                self.assertIn("not recorded", p.stderr)

    def test_unwritable_store_exits_zero(self):
        with TemporaryDirectory() as d:
            Path(d, ".rewindagents").write_text("a file where the store directory should be", newline="")
            p = run_hook_process(json.dumps(payload(d, "PreToolUse", "Bash", {"command": "ls"})), d)
            self.assertEqual((p.returncode, p.stdout), (0, ""))
            self.assertIn("not recorded", p.stderr)

    def test_run_returns_zero_in_process(self):
        self.assertEqual(hook.run(io.StringIO("{")), 0)


class TestInstall(unittest.TestCase):
    def test_install_adds_both_events_and_keeps_existing_settings(self):
        with TemporaryDirectory() as d:
            s = Path(d, ".claude", "settings.json")
            s.parent.mkdir()
            existing = {"model": "x", "hooks": {"PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "other"}]}]}}
            s.write_text(json.dumps(existing), newline="")
            self.assertTrue(hook.install(s, command="rw"))
            got = json.loads(s.read_text())
            self.assertEqual(got["model"], "x")
            self.assertEqual(got["hooks"]["PreToolUse"][0]["hooks"][0]["command"], "other")
            for ev in ("PreToolUse", "PostToolUse"):
                cmds = [h["command"] for g in got["hooks"][ev] for h in g["hooks"]]
                self.assertIn("rw", cmds)

    def test_install_twice_is_a_no_op(self):
        with TemporaryDirectory() as d:
            s = Path(d, "settings.json")
            self.assertTrue(hook.install(s, command="rw"))
            before = s.read_text()
            self.assertFalse(hook.install(s, command="rw"))
            self.assertEqual(s.read_text(), before)

    def test_install_cli(self):
        from contextlib import redirect_stdout
        from rewindagents.cli import main
        with TemporaryDirectory() as d:
            s = str(Path(d, "settings.json"))
            for expect in ("installed in", "already installed in"):
                out = io.StringIO()
                with redirect_stdout(out):
                    self.assertEqual(main(["install", "--settings", s]), 0)
                self.assertTrue(out.getvalue().startswith(expect))

    def test_hook_command_from_a_clone_carries_pythonpath(self):
        import shlex
        from unittest.mock import patch
        # python=POSIX_PY, not the real sys.executable: on windows-latest CI the real interpreter path is a
        # Windows path, which takes hook.hook_command()'s Windows branch (R42/R94), not this POSIX form.
        with patch.object(hook, "installed", return_value=False):
            cmd = hook.hook_command(python=POSIX_PY)
        self.assertEqual(cmd, f"PYTHONPATH={shlex.quote(str(SRC))} {shlex.quote(POSIX_PY)} -m rewindagents hook")

    def test_hook_command_when_installed_needs_no_pythonpath(self):
        import shlex
        from unittest.mock import patch
        with patch.object(hook, "installed", return_value=True):
            cmd = hook.hook_command(python=POSIX_PY)
        self.assertEqual(cmd, f"{shlex.quote(POSIX_PY)} -m rewindagents hook")

    def test_installed_means_this_file_lives_in_site_packages(self):
        import site
        from unittest.mock import patch
        # These tests import the package from src/, so from here it is never "installed"...
        self.assertFalse(hook.installed())
        # ...even though `pip install .` leaves src/rewindagents.egg-info behind, which a metadata lookup would trust.
        with patch.object(site, "getsitepackages", return_value=[str(SRC)]):
            self.assertTrue(hook.installed())
        with patch.object(site, "getsitepackages", return_value=[]), \
                patch.object(site, "getusersitepackages", return_value=str(SRC.parent)):
            self.assertTrue(hook.installed())

    def test_installed_command_actually_runs_the_hook(self):
        with TemporaryDirectory() as d:
            s = Path(d, "settings.json")
            hook.install(s)
            cmd = json.loads(s.read_text())["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
            p = subprocess.run(cmd, shell=True, cwd=d, capture_output=True, text=True,
                               input=json.dumps(payload(d, "PreToolUse", "Bash", {"command": "ls"})))
            self.assertEqual((p.returncode, p.stdout), (0, ""), p.stderr)
            self.assertEqual(len(read(Path(d, ".rewindagents", "log.jsonl"))), 1)


if __name__ == "__main__":
    unittest.main()
