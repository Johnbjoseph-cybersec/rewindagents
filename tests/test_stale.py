"""Stale hooks: a rewindagents hook whose interpreter (or clone PYTHONPATH) is gone records nothing, silently.
`init` and `install` replace it, `status` reports it; every other hook stays."""
import io
import json
import os
import re
import shlex
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from rewindagents import agents, hook, init  # noqa: E402



def write_hooks(path: Path, name: str, commands: list[str]) -> None:
    """A config file holding these commands on every event `install` writes, in the agent's own shape."""
    ag = agents.AGENTS[name]
    events = ag.events + ag.also_post
    if ag.shape == "cursor":
        body = {"version": 1, "hooks": {e: [{**dict(ag.entry), ag.command_key: c} for c in commands]
                                        for e in events}}
    else:
        body = {"hooks": {e: [{"matcher": "*", "hooks": [{"type": "command", "command": c}]} for c in commands]
                          for e in events}}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body))


class StaleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        t = Path(self.tmp.name).resolve()
        self.root, self.home, self.bin = t / "proj", t / "home", t / "bin"
        for p in (self.root, self.home, self.bin):
            p.mkdir()
        self.gone = t / "deleted-venv" / "bin" / "python"      # never created
        self.dead = f"{self.gone} -m rewindagents hook"

    def tearDown(self):
        self.tmp.cleanup()

    def run_init(self, **kw):
        out = io.StringIO()
        code = init.main(root=self.root, home=self.home, path=str(self.bin), stdin=io.StringIO(""), out=out, **kw)
        return code, out.getvalue()

    def run_status(self):
        out = io.StringIO()
        return init.status(root=self.root, home=self.home, out=out), out.getvalue()

    def line(self, out, agent):
        return [l for l in out.splitlines() if l.strip().startswith(agent + " ")][-1]

    # hook.stale -----------------------------------------------------------------------------------------------
    def test_a_missing_interpreter_is_stale_and_says_which(self):
        self.assertEqual(hook.stale(self.dead), f"{self.gone} no longer exists")
        self.assertEqual(hook.stale(f"{shlex.quote(str(self.gone))} -m rewindagents hook --agent copilot || true"),
                         f"{self.gone} no longer exists")
        spaced = self.root / "my venv" / "python"
        self.assertEqual(hook.stale(f"{shlex.quote(str(spaced))} -m rewindagents hook"),
                         f"{spaced} no longer exists")

    def test_a_missing_pythonpath_dir_is_stale(self):
        cmd = f"PYTHONPATH={self.root / 'old-clone' / 'src'} {sys.executable} -m rewindagents hook"
        self.assertEqual(hook.stale(cmd), f"PYTHONPATH {self.root / 'old-clone' / 'src'} no longer exists")

    def test_a_runnable_or_bare_command_is_not_stale(self):
        for name in agents.AGENTS:
            self.assertIsNone(hook.stale(hook.hook_command(name)), name)
        self.assertIsNone(hook.stale("rewindagents hook"))           # looked up on PATH at run time
        self.assertIsNone(hook.stale("uvx rewindagents hook"))
        self.assertIsNone(hook.stale("'unbalanced quote"))

    def test_stale_hooks_reads_only_rewindagents_commands(self):
        f = self.root / ".claude/settings.json"
        write_hooks(f, "claude", [f"{self.gone} my-linter", self.dead])   # the user's own dead hook is not ours
        self.assertEqual(hook.stale_hooks(f, "claude"), [(self.dead, f"{self.gone} no longer exists")])
        self.assertEqual(hook.stale_hooks(self.root / "missing.json", "claude"), [])

    # init -----------------------------------------------------------------------------------------------------
    def test_init_dry_run_says_will_replace_and_writes_nothing(self):
        f = self.root / ".claude/settings.json"
        write_hooks(f, "claude", [self.dead])
        before = f.read_bytes()
        code, out = self.run_init()
        self.assertEqual(code, 0, out)
        self.assertIn("will replace", self.line(out, "claude"))
        self.assertIn(f"stale: {self.gone} no longer exists", self.line(out, "claude"))
        self.assertEqual(f.read_bytes(), before)

    def test_init_yes_replaces_the_stale_hook_in_every_config_shape_and_keeps_the_users_hooks(self):
        # The real interpreter, on every OS. `dead` is shaped like the interpreter path of this OS (a Windows
        # path on Windows), and init replaces it with hook_command()'s form for this OS. (Patching
        # sys.executable to /usr/bin/python3 here, tried for R94, made the replacement itself stale on
        # Windows, where that file does not exist. The copilot failure it was meant to fix was a real bug:
        # agents.uninstall looked only under the key install would pick, `powershell` for a Windows
        # command, so a stale one under `bash` stayed.)
        for name in ("claude", "cursor", "copilot", "droid"):
            ag = agents.AGENTS[name]
            with self.subTest(agent=name):
                f = self.root / ag.settings
                dead = self.dead + (f" --agent {name}" if name != "claude" else "") + \
                    (" || true" if ag.fail_closed else "")
                write_hooks(f, name, ["my-own-hook", dead])
                code, out = self.run_init(yes=True)
                self.assertEqual(code, 0, out)
                self.assertIn("replaced", self.line(out, name))
                self.assertIn(f"was stale: {self.gone} no longer exists", self.line(out, name))
                got = agents.commands_in(ag, f)
                self.assertEqual(set(got), set(ag.events + ag.also_post))
                for event, cmds in got.items():
                    self.assertEqual(cmds, ["my-own-hook", hook.hook_command(name)], (name, event))
                self.assertEqual(hook.stale_hooks(f, name), [])
                code, out = self.run_init(yes=True)
            self.assertIn("already there", self.line(out, name))

    def test_a_stale_hook_next_to_a_runnable_other_one_is_removed_and_nothing_is_added(self):
        f = self.root / ".claude/settings.json"
        live = f"PYTHONPATH={self.root} {sys.executable} -m rewindagents hook"
        write_hooks(f, "claude", [self.dead, live])
        code, out = self.run_init(yes=True)
        self.assertEqual(code, 0, out)
        self.assertIn("removed stale", self.line(out, "claude"))
        got = agents.commands_in(agents.AGENTS["claude"], f)
        ag = agents.AGENTS["claude"]
        self.assertEqual(got, {e: [live] for e in ag.events + ag.also_post})

    # status ---------------------------------------------------------------------------------------------------
    def test_status_reports_each_file_writes_nothing_and_exits_1_on_stale(self):
        write_hooks(self.root / ".claude/settings.json", "claude", [hook.hook_command("claude")])
        write_hooks(self.root / ".cursor/hooks.json", "cursor", [self.dead + " --agent cursor"])
        write_hooks(self.root / ".gemini/settings.json", "gemini", ["my-own-hook"])
        q = self.root / ".qwen/settings.json"
        q.parent.mkdir()
        q.write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [
            {"type": "command", "command": hook.hook_command("qwen")}]}]}}))
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        code, out = self.run_status()
        self.assertEqual(code, 1, out)
        self.assertRegex(self.line(out, "claude"), r"claude\s+ok\s+\.claude/settings\.json$")
        self.assertRegex(self.line(out, "cursor"),
                         rf"cursor\s+STALE\s+\.cursor/hooks\.json  \({re.escape(str(self.gone))} no longer exists\)$")
        self.assertRegex(self.line(out, "gemini"), r"gemini\s+no hook\s+")
        self.assertRegex(self.line(out, "qwen"), r"qwen\s+PARTIAL\s+")
        self.assertNotIn("codex", out)                    # no file, no line
        self.assertIn("A stale hook records nothing. Fix: ", out)
        self.assertIn("init --yes", out)
        self.assertEqual({p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}, before)
        init.main(yes=True, root=self.root, home=self.home, path=str(self.bin), stdin=io.StringIO(""),
                  out=io.StringIO())
        code, out = self.run_status()
        self.assertEqual(code, 0, out)
        self.assertRegex(self.line(out, "cursor"), r"cursor\s+ok\s+")

    def test_status_with_no_config_says_how_to_start(self):
        code, out = self.run_status()
        self.assertEqual(code, 0)
        self.assertIn("No agent config file in this project", out)

    # install through the CLI (source tree) ----------------------------------------------------------------------
    def test_cli_install_replaces_a_stale_hook_and_status_turns_ok(self):
        f = self.root / ".claude/settings.json"
        write_hooks(f, "claude", ["my-own-hook", self.dead])
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        env.update(HOME=str(self.home), PYTHONPATH=str(SRC))

        def cli(*argv):
            return subprocess.run([sys.executable, "-m", "rewindagents", *argv], cwd=self.root, env=env,
                                  capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
        r = cli("status")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("STALE", r.stdout)
        r = cli("install")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines(), [
            "installed in .claude/settings.json",
            f"  replaced a stale rewindagents hook: {self.gone} no longer exists"])
        cmds = agents.commands_in(agents.AGENTS["claude"], f)
        self.assertEqual(len({c for v in cmds.values() for c in v if hook.ours(c)}), 1, cmds)
        self.assertTrue(all(v[0] == "my-own-hook" for v in cmds.values()), cmds)
        r = cli("status")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(r.stdout, r"claude\s+ok\s+\.claude/settings\.json")


if __name__ == "__main__":
    unittest.main()
