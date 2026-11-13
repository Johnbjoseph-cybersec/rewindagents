"""Daily-use fixes from the dogfood journal (ux-review/DOGFOOD.md). Each test names the friction it covers;
every one fails on the code before these fixes (the flag, command or behaviour did not exist)."""
import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from rewindagents import agents, bashscan, hook, init, rewind  # noqa: E402
from test_rewind import Agent, cli, git  # noqa: E402


def git_repo(d):
    git(d, "init", "-q")
    git(d, "config", "user.email", "t@t")
    git(d, "config", "user.name", "t")


class Here:
    """chdir for the duration of a test (the CLI reads the project from the working directory)."""

    def __init__(self, d):
        self.d, self.old = d, os.getcwd()

    def __enter__(self):
        os.chdir(self.d)

    def __exit__(self, *a):
        os.chdir(self.old)


class TestReplayStep(unittest.TestCase):
    """F3: `replay 2` failed with "unrecognized arguments: 2" while diff/rewind/revert take N positionally."""

    def test_positional_step_is_the_same_as_step_option(self):
        with TemporaryDirectory() as d:
            a = Agent(d)
            a.write("app.py", "v1\n")
            a.write("app.py", "v2\n")
            with Here(d):
                c1, o1, _ = cli("replay", "2")
                c2, o2, _ = cli("replay", "--step", "2")
                c3, o3, _ = cli("replay", "2", "--diff")
                c4, _, e4 = cli("replay", "1", "--step", "2")
        self.assertEqual((c1, c2), (0, 0))
        self.assertEqual(o1, o2)
        self.assertIn('"step": 2', o1)
        self.assertEqual(c3, 0)
        self.assertIn("-v1", o3)
        self.assertIn("+v2", o3)
        self.assertEqual(c4, 2)
        self.assertIn("name different steps", e4)


class TestSummary(unittest.TestCase):
    """F4: no short answer to "what did the agent just do?"."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.d = Path(self.tmp.name)
        (self.d / "src").mkdir()
        (self.d / "src" / "app.py").write_text("a\nb\nc\n")
        (self.d / "tests.py").write_text("t1\nt2\n")
        self.a = Agent(self.d)

    def tearDown(self):
        self.tmp.cleanup()

    def run_summary(self, *args):
        with Here(self.d):
            return cli("summary", *args)

    def test_lists_net_file_changes_with_lines_steps_and_the_undo_commands(self):
        self.a.write("src/app.py", "a\nB\nc\nd\n")                            # step 1: +2 -1
        self.a.bash("rm tests.py", lambda c: (c / "tests.py").unlink())          # step 2: deleted, 2 lines
        self.a.write("NEW.md", "one\ntwo\nthree\n")                              # step 3: created, 3 lines
        self.a.bash("pytest")                                                    # step 4: nothing
        code, out, err = self.run_summary()
        self.assertEqual(code, 0, err)
        lines = out.splitlines()
        self.assertRegex(lines[0], r"^Session s1 \(claude, .*\): 4 steps, 2 shell commands\.$")
        self.assertEqual(lines[1], "3 files different now from before its first step:")
        self.assertRegex(lines[2], r"^  deleted  tests\.py\s+-2\s+step 2$")
        self.assertRegex(lines[3], r"^  changed  src/app\.py\s+\+2 -1\s+step 1$")
        self.assertRegex(lines[4], r"^  created  NEW\.md\s+\+3\s+step 3$")
        self.assertEqual(lines[5], "Take it back:")
        self.assertRegex(lines[6], r"^  (rewindagents|python3 -m rewindagents) diff 0\s+every change above")
        self.assertRegex(lines[7], r"revert 3\s+take back only step 3 \(the last that changed files\)")
        self.assertRegex(lines[8], r"rewind 0\s+put every file above back")
        # the list is exactly what `rewind 0` puts back
        p = rewind.rewind(self.a.log, 0, dry_run=True)
        self.assertEqual(len(p["restore"]) + len(p["delete"]), 3)

    def test_a_file_changed_and_changed_back_is_not_listed(self):
        self.a.write("src/app.py", "x\n")
        self.a.write("src/app.py", "a\nb\nc\n")
        code, out, _ = self.run_summary()
        self.assertEqual(code, 0)
        self.assertIn("No file is different now from before this session", out)
        self.assertNotIn("Take it back", out)

    def test_other_session_and_explicit_session_flag(self):
        Agent(self.d, "older-session").write("src/app.py", "old\n")
        self.a.write("tests.py", "t1\n")
        code, out, _ = self.run_summary("--session", "older")
        self.assertEqual(code, 0)
        self.assertIn("Session older-s", out)
        self.assertIn("rewind 0 --session older-s", out)
        self.assertIn("1 other session in this log", out)

    def test_unscanned_command_steps_are_called_out(self):
        with mock.patch.object(bashscan, "MAX_SCAN_FILES", 1):
            self.a.bash("rm -rf src", lambda c: (c / "src" / "app.py").unlink())
        code, out, _ = self.run_summary()
        self.assertIn("1 command step(s) were not scanned", out)

    def test_no_log_says_how_to_start(self):
        with TemporaryDirectory() as d, Here(d):
            code, _, err = cli("summary")
        self.assertEqual(code, 2)
        self.assertIn("init", err)


class TestNotScannedIsVisible(unittest.TestCase):
    """F6: over the file limit, shell steps were silently not checkpointed."""

    def test_replay_marks_the_step_and_status_warns(self):
        with TemporaryDirectory() as d:
            d = Path(d).resolve()
            (d / "a.txt").write_text("a")
            (d / "b.txt").write_text("b")
            a = Agent(d)
            with mock.patch.object(bashscan, "MAX_SCAN_FILES", 1):
                a.bash("rm a.txt", lambda c: (c / "a.txt").unlink())
                with Here(d):
                    code, out, _ = cli("replay")
                st = io.StringIO()
                hook.install(d / ".claude/settings.json", agent="claude")
                init.status(root=d, home=d / "home", out=st, probe=False)
            self.assertEqual(code, 0)
            self.assertIn("[NOT checkpointed: more than 1 files]", out)
            self.assertIn("more than 1 files, so shell commands", st.getvalue())


class TestStatus(unittest.TestCase):
    """F7 store size; F8/F9 a hook that runs but records nothing is found and named."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        t = Path(self.tmp.name).resolve()
        self.root, self.home = t / "proj", t / "home"
        self.root.mkdir()
        self.home.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def status(self, **kw):
        out = io.StringIO()
        return init.status(root=self.root, home=self.home, out=out, **kw), out.getvalue()

    @unittest.skipUnless(os.name == "posix", "the probe runs on POSIX shells only")
    def test_a_working_hook_is_proven_by_a_probe_that_writes_nothing_here(self):
        hook.install(self.root / ".claude/settings.json", agent="claude")
        code, out = self.status()
        self.assertEqual(code, 0, out)
        self.assertIn("Recording works: each hook above ran once in a scratch folder", out)
        self.assertFalse((self.root / ".rewindagents").exists())

    @unittest.skipUnless(os.name == "posix", "the probe runs on POSIX shells only")
    def test_a_hook_that_runs_but_cannot_record_is_failing_and_exits_1(self):
        broken = (f"{sys.executable} -c \"import sys; sys.stderr.write('No module named rewindagents\\n')\" "
                  f"rewindagents hook")
        # The realistic case: the config holds exactly the command this install writes, but it cannot record
        # (the package was removed from that interpreter). Only that command is ever probed.
        with mock.patch.object(hook, "hook_command", return_value=broken):
            hook.install(self.root / ".claude/settings.json", command=broken, agent="claude")
            self.assertEqual(hook.stale(broken), None)       # the stale check cannot see this one
            code, out = self.status()
        self.assertEqual(code, 1, out)
        self.assertRegex(out, r"claude\s+FAILING\s+\.claude/settings\.json  \(ran but recorded nothing: "
                              r"No module named rewindagents\)")
        self.assertIn("A FAILING hook records nothing", out)
        self.assertNotIn("Recording works", out)

    @unittest.skipUnless(os.name == "posix", "the probe runs on POSIX shells only")
    def test_status_never_runs_a_command_taken_from_the_config(self):
        # A cloned project's config is untrusted: a command that only mentions `rewindagents hook` must not run.
        pwned = self.root / "PWNED"
        evil = f"touch {pwned}; {sys.executable} -m rewindagents hook"
        hook.install(self.root / ".claude/settings.json", command=evil, agent="claude")
        code, out = self.status()
        self.assertFalse(pwned.exists(), out)
        self.assertRegex(out, r"claude\s+ok\s+\.claude/settings\.json  \(another rewindagents hook, not tested")
        self.assertNotIn("Recording works", out)

    def test_a_hook_missing_an_event_is_partial_and_exits_1(self):
        # A config from before PostToolUseFailure was hooked: failed shell commands would go unrecorded.
        cfg = self.root / ".claude/settings.json"
        hook.install(cfg, agent="claude")
        data = json.loads(cfg.read_text())
        self.assertIn("PostToolUseFailure", data["hooks"])
        del data["hooks"]["PostToolUseFailure"]
        cfg.write_text(json.dumps(data))
        code, out = self.status(probe=False)
        self.assertEqual(code, 1, out)
        self.assertRegex(out, r"claude\s+PARTIAL\s+\.claude/settings\.json  \(not on every event")
        self.assertIn("A PARTIAL hook misses some steps", out)
        self.assertIn("init --yes", out)

    def test_store_size_is_shown(self):
        store = self.root / ".rewindagents" / "objects"
        store.mkdir(parents=True)
        (store / ("0" * 64)).write_bytes(b"x" * 3000)
        code, out = self.status(probe=False)
        self.assertRegex(out, r"  store    2\.9 KB\s+\.rewindagents/  \(the log plus a copy")
        self.assertIn("gc` frees what no step needs", out)


class TestInitAgentAndExclude(unittest.TestCase):
    """F1: init wrote every detected agent's file into the repo, holding this machine's Python path."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        t = Path(self.tmp.name).resolve()
        self.root, self.home = t / "proj", t / "home"
        self.root.mkdir()
        for d in (".codex", ".gemini", ".claude"):
            (self.home / d).mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def run_init(self, **kw):
        out = io.StringIO()
        return init.main(root=self.root, home=self.home, path="", out=out, **kw), out.getvalue()

    def test_agent_option_sets_up_only_that_agent(self):
        code, out = self.run_init(yes=True, only=["claude"])
        self.assertEqual(code, 0, out)
        self.assertTrue((self.root / ".claude/settings.json").is_file())
        self.assertFalse((self.root / ".codex").exists())
        self.assertFalse((self.root / ".gemini").exists())
        self.assertNotIn("codex", out)

    def test_agent_option_installs_an_agent_that_is_not_detected(self):
        code, out = self.run_init(yes=True, only=["cursor"])
        self.assertEqual(code, 0, out)
        self.assertTrue((self.root / ".cursor/hooks.json").is_file())

    def test_created_files_are_kept_out_of_git_and_a_tracked_one_is_named(self):
        git_repo(self.root)
        (self.root / ".gemini").mkdir()
        (self.root / ".gemini/settings.json").write_text('{"theme": "x"}\n')
        git(self.root, "add", ".gemini/settings.json")
        code, out = self.run_init(yes=True)
        self.assertEqual(code, 0, out)
        status = git(self.root, "status", "--porcelain", "--untracked-files=all")
        self.assertNotIn(".claude", status)
        self.assertNotIn(".codex", status)
        self.assertIn(".gemini/settings.json", status)        # tracked and changed: shown, and named in the output
        self.assertIn("Kept out of git (.git/info/exclude, this clone only): .claude/settings.json, "
                      ".codex/hooks.json.", out)
        self.assertIn("Note: .gemini/settings.json is tracked by git", out)
        self.assertNotIn(".gitignore", [p.name for p in self.root.iterdir()])    # nothing committed-looking
        ex = (self.root / ".git/info/exclude").read_text()
        self.assertIn("/.claude/settings.json\n", ex)
        self.assertNotIn("/.gemini/settings.json", ex)
        # a second init adds nothing twice
        self.run_init(yes=True)
        self.assertEqual((self.root / ".git/info/exclude").read_text(), ex)

    def test_outside_git_nothing_is_excluded_and_nothing_breaks(self):
        code, out = self.run_init(yes=True)
        self.assertEqual(code, 0, out)
        self.assertNotIn("Kept out of git", out)
        self.assertFalse((self.root / ".git").exists())


class TestInitUndo(unittest.TestCase):
    """F2: no one-command undo of init."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        t = Path(self.tmp.name).resolve()
        self.root, self.home = t / "proj", t / "home"
        self.root.mkdir()
        for d in (".codex", ".claude"):
            (self.home / d).mkdir(parents=True)
        git_repo(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_undo_removes_exactly_what_init_added(self):
        before_ex = (self.root / ".git/info/exclude").read_text()
        (self.root / ".claude").mkdir()
        mine = {"model": "x", "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
            {"type": "command", "command": "my-linter"}]}]}}
        (self.root / ".claude/settings.json").write_text(json.dumps(mine))
        init.main(yes=True, root=self.root, home=self.home, path="", out=io.StringIO())
        Agent(self.root).write("a.txt", "1")                        # some recorded history
        self.assertTrue((self.root / ".codex/hooks.json").is_file())
        out = io.StringIO()
        code = init.undo(root=self.root, home=self.home, out=out)
        text = out.getvalue()
        self.assertEqual(code, 0, text)
        self.assertEqual(json.loads((self.root / ".claude/settings.json").read_text()), mine)
        self.assertFalse((self.root / ".codex").exists())           # held only our hook: file and dir gone
        self.assertRegex(text, r"codex\s+removed\s+\.codex/hooks\.json  \(file deleted: it held nothing else\)")
        self.assertRegex(text, r"claude\s+removed\s+\.claude/settings\.json  \(other settings and hooks kept\)")
        self.assertEqual((self.root / ".git/info/exclude").read_text().rstrip("\n"), before_ex.rstrip("\n"))
        self.assertTrue((self.root / ".rewindagents/log.jsonl").is_file())
        self.assertIn("recorded history in .rewindagents/ is kept", text)
        # nothing left: a second undo changes nothing and says so
        out = io.StringIO()
        self.assertEqual(init.undo(root=self.root, home=self.home, out=out), 0)
        self.assertIn("No rewindagents hook found; nothing changed.", out.getvalue())

    def test_undo_also_removes_a_stale_hook_from_another_python(self):
        f = self.root / ".claude/settings.json"
        dead = "/no/such/venv/bin/python -m rewindagents hook"
        hook.install(f, command=dead, agent="claude")
        init.undo(root=self.root, home=self.home, out=io.StringIO())
        self.assertFalse(f.exists())

    def test_cli_flag(self):
        hook.install(self.root / ".claude/settings.json", agent="claude")
        with Here(self.root), mock.patch.object(Path, "home", return_value=self.home):
            code, out, _ = cli("init", "--undo")
        self.assertEqual(code, 0)
        self.assertIn("removed", out)
        self.assertFalse((self.root / ".claude/settings.json").exists())


if __name__ == "__main__":
    unittest.main()
