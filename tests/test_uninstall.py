"""`uninstall` (R13): removes only the hook entries `install` wrote, for every agent; every other hook and key
survives; a file holding none of ours is left byte-identical and says so; .rewindagent/ is never touched."""
import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from rewindagent import agents, hook  # noqa: E402
from rewindagent.cli import main  # noqa: E402

ROOT = SRC.parent
OTHER_GROUPS = {"description": "mine", "hooks": {
    "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "other-pre"}]}],
    "Stop": [{"hooks": [{"type": "command", "command": "other-stop"}]}]}, "model": "x"}
OTHER_CURSOR = {"version": 1, "hooks": {"preToolUse": [{"command": "other-pre", "matcher": "Shell"}],
                                        "stop": [{"command": "other-stop"}]}}


def cli(*argv):
    out = io.StringIO()
    with redirect_stdout(out):
        code = main(list(argv))
    return code, out.getvalue()


class TestUninstall(unittest.TestCase):
    def test_install_then_uninstall_gives_back_the_same_settings_for_every_agent(self):
        for agent, before in (("claude", OTHER_GROUPS), ("codex", OTHER_GROUPS), ("cursor", OTHER_CURSOR)):
            with self.subTest(agent=agent), TemporaryDirectory() as d:
                f = Path(d, "settings.json")
                f.write_text(json.dumps(before))
                self.assertTrue(hook.install(f, command="rw", agent=agent))
                self.assertIn("rw", agents.commands_in(agents.AGENTS[agent], f)[agents.AGENTS[agent].events[1]])
                self.assertTrue(hook.uninstall(f, command="rw", agent=agent))
                self.assertEqual(json.loads(f.read_text()), before, "every other hook and key survives")
                for cmds in agents.commands_in(agents.AGENTS[agent], f).values():
                    self.assertNotIn("rw", cmds)

    def test_a_group_shared_with_another_hook_keeps_the_other_hook(self):
        with TemporaryDirectory() as d:
            f = Path(d, "settings.json")
            f.write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [
                {"type": "command", "command": "other"}, {"type": "command", "command": "rw"}]}]}}))
            self.assertTrue(hook.uninstall(f, command="rw"))
            self.assertEqual(json.loads(f.read_text()), {"hooks": {"PreToolUse": [
                {"matcher": "*", "hooks": [{"type": "command", "command": "other"}]}]}})

    def test_only_the_exact_command_is_removed(self):
        # a command that merely contains ours (another Python, an extra flag) is not ours
        with TemporaryDirectory() as d:
            f = Path(d, "hooks.json")
            body = json.dumps({"version": 1, "hooks": {"preToolUse": [{"command": "rw --agent cursor x"},
                                                                      {"command": "/other/python rw"}]}})
            f.write_text(body)
            self.assertFalse(hook.uninstall(f, command="rw", agent="cursor"))
            self.assertEqual(f.read_text(), body)

    def test_a_file_with_nothing_of_ours_is_left_byte_identical(self):
        with TemporaryDirectory() as d:
            for agent, before in (("claude", OTHER_GROUPS), ("cursor", OTHER_CURSOR)):
                f = Path(d, agent + ".json")
                raw = json.dumps(before, indent=4) + "\n\n"        # formatting install would not write
                f.write_text(raw)
                mtime = f.stat().st_mtime_ns
                self.assertFalse(hook.uninstall(f, command="rw", agent=agent))
                self.assertEqual(f.read_bytes(), raw.encode())
                self.assertEqual(f.stat().st_mtime_ns, mtime, "not rewritten")
            f = Path(d, "empty.json")
            f.write_text("")
            self.assertFalse(hook.uninstall(f, command="rw"))
            self.assertEqual(f.read_text(), "")
            self.assertFalse(hook.uninstall(Path(d, "missing.json"), command="rw"))
            self.assertFalse(Path(d, "missing.json").exists(), "a missing file is not created")

    def test_not_a_json_object_is_refused_and_unchanged(self):
        with TemporaryDirectory() as d:
            f = Path(d, "s.json")
            f.write_text("[1]")
            with self.assertRaises(ValueError):
                hook.uninstall(f, command="rw")
            self.assertEqual(f.read_text(), "[1]")

    def test_the_default_command_is_the_one_install_writes(self):
        with TemporaryDirectory() as d:
            for agent in sorted(agents.AGENTS):
                f = Path(d, agent + ".json")
                self.assertTrue(hook.install(f, agent=agent))
                self.assertTrue(hook.uninstall(f, agent=agent))
                self.assertEqual(sum(map(len, agents.commands_in(agents.AGENTS[agent], f).values())), 0, agent)


class TestCli(unittest.TestCase):
    def test_uninstall_cli_per_agent_and_history_stays(self):
        with TemporaryDirectory() as d:
            here = os.getcwd()
            os.chdir(d)
            try:
                store = Path(d, ".rewindagent")
                store.mkdir()
                Path(store, "log.jsonl").write_text("{}\n")
                for agent, path in (("cursor", ".cursor/hooks.json"), ("codex", ".codex/hooks.json"),
                                    ("claude", ".claude/settings.json")):
                    self.assertEqual(cli("uninstall", "--agent", agent),
                                     (0, "not installed in %s; left unchanged\n" % path))
                    self.assertFalse(Path(d, path).exists())
                    self.assertEqual(cli("install", "--agent", agent)[0], 0)
                    self.assertEqual(cli("uninstall", "--agent", agent), (0, "removed from %s\n" % path))
                    self.assertEqual(cli("uninstall", "--agent", agent),
                                     (0, "not installed in %s; left unchanged\n" % path))
                self.assertEqual(cli("install", "--settings", "u/s.json")[0], 0)
                self.assertEqual(cli("uninstall", "--settings", "u/s.json"), (0, "removed from u/s.json\n"))
                self.assertEqual(Path(store, "log.jsonl").read_text(), "{}\n", ".rewindagent/ untouched")
            finally:
                os.chdir(here)

    def test_readme_gives_the_undo_line(self):
        readme = " ".join((ROOT / "README.md").read_text(encoding="utf-8").split())
        self.assertIn("rewindagent uninstall", readme)
        self.assertIn("never touches `.rewindagent/`", readme)


if __name__ == "__main__":
    unittest.main()
