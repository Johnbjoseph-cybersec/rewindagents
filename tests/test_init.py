"""`rewindagents init`: find the agents, show the plan, install the hook once each, keep the user's hooks."""
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

from rewindagents import agents, hook, init  # noqa: E402


class Tty(io.StringIO):
    def isatty(self):
        return True


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        t = Path(self.tmp.name).resolve()
        self.root, self.home, self.bin = t / "proj", t / "home", t / "bin"
        for p in (self.root, self.home, self.bin):
            p.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def on_path(self, *names):
        for n in names:
            f = self.bin / n
            f.write_text("#!/bin/sh\n")
            f.chmod(0o755)

    def run_init(self, *, yes=False, global_=False, stdin=None):
        out = io.StringIO()
        code = init.main(yes=yes, global_=global_, root=self.root, home=self.home, path=str(self.bin),
                         stdin=stdin if stdin is not None else io.StringIO(""), out=out)
        return code, out.getvalue()

    def line(self, out, agent):
        """The last line about this agent: after a prompt, the result line follows the plan line."""
        return [l for l in out.splitlines() if l.strip().startswith(agent + " ")][-1]


class TestDetect(Base):
    def test_config_dir_in_project_user_dir_or_binary_on_path(self):
        (self.root / ".claude").mkdir()
        (self.home / ".codex").mkdir()
        self.on_path("cursor-agent", "qwen")
        (self.root / ".github" / "hooks").mkdir(parents=True)
        found = {f["agent"]: f["found"] for f in init.detect(self.root, self.home, path=str(self.bin))}
        self.assertEqual(found["claude"], [".claude/"])
        self.assertEqual(found["codex"], ["~/.codex/"])
        self.assertEqual(found["cursor"], ["cursor-agent on PATH"])
        self.assertEqual(found["qwen"], ["qwen on PATH"])
        self.assertEqual(found["copilot"], [".github/hooks/"])
        self.assertEqual(found["gemini"], [])
        self.assertEqual(found["droid"], [])

    def test_a_plain_github_dir_does_not_mean_copilot_and_agent_is_not_cursor(self):
        (self.root / ".github").mkdir()
        self.on_path("agent")
        found = {f["agent"]: f["found"] for f in init.detect(self.root, self.home, path=str(self.bin))}
        self.assertEqual((found["copilot"], found["cursor"]), ([], []))

    def test_every_supported_agent_has_a_binary_and_dirs(self):
        self.assertEqual(set(init.BINARIES), set(agents.AGENTS))
        self.assertEqual(set(init.PROJECT_DIRS), set(agents.AGENTS))
        self.assertEqual(set(init.USER_DIRS), set(agents.AGENTS))

    def test_global_targets_are_the_user_files(self):
        t = {f["agent"]: f["target"] for f in init.detect(self.root, self.home, global_=True, path="")}
        self.assertEqual(t["claude"], self.home / ".claude/settings.json")
        self.assertEqual(t["copilot"], self.home / ".copilot/hooks/rewindagents.json")
        self.assertEqual(t["droid"], self.home / ".factory/settings.json")
        (self.home / ".factory").mkdir()
        (self.home / ".factory/hooks.json").write_text("{}")
        t = {f["agent"]: f["target"] for f in init.detect(self.root, self.home, global_=True, path="")}
        self.assertEqual(t["droid"], self.home / ".factory/hooks.json")

    def test_global_ignores_project_dirs(self):
        (self.root / ".claude").mkdir()
        found = {f["agent"]: f["found"] for f in init.detect(self.root, self.home, global_=True, path="")}
        self.assertEqual(found["claude"], [])


class TestInit(Base):
    def test_without_yes_and_no_terminal_it_is_a_dry_run(self):
        self.on_path("claude", "gemini")
        code, out = self.run_init()
        self.assertEqual(code, 0)
        self.assertIn("will install", self.line(out, "claude"))
        self.assertIn("not found", self.line(out, "codex"))
        self.assertIn("Dry run: nothing written", out)
        self.assertFalse((self.root / ".claude").exists())
        self.assertFalse((self.root / ".gemini").exists())

    def test_yes_installs_one_line_per_agent_and_a_second_run_changes_nothing(self):
        self.on_path("claude", "codex", "cursor", "gemini", "copilot", "droid")
        code, out = self.run_init(yes=True)
        self.assertEqual(code, 0, out)
        for name in ("claude", "codex", "cursor", "gemini", "copilot", "droid"):
            self.assertIn("installed", self.line(out, name), name)
            ag = agents.AGENTS[name]
            cmds = agents.commands_in(ag, self.root / ag.settings)
            self.assertEqual(set(cmds), set(ag.events + ag.also_post))
            for event, got in cmds.items():
                self.assertEqual(got, [hook.hook_command(name)], (name, event))
        self.assertIn("not found", self.line(out, "qwen"))
        self.assertEqual(len([l for l in out.splitlines() if l.startswith("  ")]), 7)
        self.assertIn("codex: Codex asks you to trust a new hook once", out)
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        code, out = self.run_init(yes=True)
        self.assertEqual(code, 0)
        for name in ("claude", "codex", "cursor", "gemini", "copilot", "droid"):
            self.assertIn("already there", self.line(out, name))
        self.assertEqual({p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}, before)

    def test_the_users_existing_hooks_and_keys_stay(self):
        (self.root / ".claude").mkdir()
        mine = {"model": "x", "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
            {"type": "command", "command": "my-linter"}]}]}}
        (self.root / ".claude/settings.json").write_text(json.dumps(mine))
        code, out = self.run_init(yes=True)
        self.assertEqual(code, 0, out)
        s = json.loads((self.root / ".claude/settings.json").read_text())
        self.assertEqual(s["model"], "x")
        self.assertEqual(agents.commands_in(agents.AGENTS["claude"], self.root / ".claude/settings.json")
                         ["PreToolUse"], ["my-linter", hook.hook_command("claude")])

    def test_a_partial_install_is_completed_without_duplicates(self):
        (self.root / ".claude").mkdir()
        cmd = hook.hook_command("claude")
        partial = {"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": cmd}]}]}}
        (self.root / ".claude/settings.json").write_text(json.dumps(partial))
        self.run_init(yes=True)
        got = agents.commands_in(agents.AGENTS["claude"], self.root / ".claude/settings.json")
        ag = agents.AGENTS["claude"]       # PreToolUse, PostToolUse and PostToolUseFailure (a failed call)
        self.assertEqual(got, {e: [cmd] for e in ag.events + ag.also_post})

    def test_another_rewindagents_hook_is_left_alone_not_doubled(self):
        (self.root / ".claude").mkdir()
        # a different command that can still run (both paths exist); a missing one is stale (test_stale.py)
        old = f"PYTHONPATH={self.root} {sys.executable} -m rewindagents hook"
        s = {"hooks": {e: [{"matcher": "*", "hooks": [{"type": "command", "command": old}]}]
                       for e in ("PreToolUse", "PostToolUse")}}
        (self.root / ".claude/settings.json").write_text(json.dumps(s))
        before = (self.root / ".claude/settings.json").read_bytes()
        code, out = self.run_init(yes=True)
        self.assertEqual(code, 0)
        self.assertIn("already there", self.line(out, "claude"))
        self.assertIn("another rewindagents hook", self.line(out, "claude"))
        self.assertEqual((self.root / ".claude/settings.json").read_bytes(), before)

    def test_unreadable_config_is_an_error_and_the_others_still_install(self):
        (self.root / ".claude").mkdir()
        (self.root / ".claude/settings.json").write_text("{not json")
        self.on_path("gemini")
        code, out = self.run_init(yes=True)
        self.assertEqual(code, 1)
        self.assertIn("error", self.line(out, "claude"))
        self.assertEqual((self.root / ".claude/settings.json").read_text(), "{not json")
        self.assertIn("installed", self.line(out, "gemini"))

    def test_terminal_prompt_yes_installs_and_no_does_not(self):
        self.on_path("qwen")
        code, out = self.run_init(stdin=Tty("n\n"))
        self.assertEqual(code, 0)
        self.assertIn("Install the hook for 1 agent? [y/N]", out)
        self.assertIn("Nothing written.", out)
        self.assertFalse((self.root / ".qwen").exists())
        code, out = self.run_init(stdin=Tty("y\n"))
        self.assertEqual(code, 0)
        self.assertIn("installed", self.line(out, "qwen"))
        self.assertTrue((self.root / ".qwen/settings.json").is_file())

    def test_terminal_prompt_empty_answer_means_no(self):
        self.on_path("qwen")
        _, out = self.run_init(stdin=Tty("\n"))
        self.assertIn("Nothing written.", out)
        self.assertFalse((self.root / ".qwen").exists())

    def test_global_writes_the_user_files(self):
        self.on_path("claude", "copilot")
        code, out = self.run_init(yes=True, global_=True)
        self.assertEqual(code, 0, out)
        self.assertIn("~/.claude/settings.json", self.line(out, "claude"))
        self.assertTrue((self.home / ".claude/settings.json").is_file())
        self.assertTrue((self.home / ".copilot/hooks/rewindagents.json").is_file())
        self.assertFalse((self.root / ".claude").exists())

    def test_nothing_found_says_how_to_proceed(self):
        code, out = self.run_init(yes=True)
        self.assertEqual(code, 1)
        self.assertIn("No supported agent found", out)
        self.assertEqual(sum("not found" in l for l in out.splitlines()), 7)


class TestCli(Base):
    def test_cli_init_end_to_end_with_home_and_path(self):
        self.on_path("claude")
        env = {"HOME": str(self.home), "PATH": str(self.bin), "PYTHONPATH": str(SRC)}
        r = subprocess.run([sys.executable, "-m", "rewindagents", "init"], cwd=self.root, env=env,
                           capture_output=True, text=True, stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Dry run", r.stdout)
        r = subprocess.run([sys.executable, "-m", "rewindagents", "init", "--yes"], cwd=self.root, env=env,
                           capture_output=True, text=True, stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertRegex(r.stdout, r"claude\s+installed\s+\.claude/settings\.json")
        self.assertTrue((self.root / ".claude/settings.json").is_file())

    def test_help_mentions_the_new_commands(self):
        env = dict(os.environ, PYTHONPATH=str(SRC))
        r = subprocess.run([sys.executable, "-m", "rewindagents", "--help"], env=env, capture_output=True, text=True)
        for word in ("init", "diff", "flight recorder"):
            self.assertIn(word, r.stdout)
        r = subprocess.run([sys.executable, "-m", "rewindagents", "rewind", "--help"], env=env,
                           capture_output=True, text=True)
        self.assertIn("--only", r.stdout)


if __name__ == "__main__":
    unittest.main()
