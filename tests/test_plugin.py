"""tests/test_plugin.py -- proves plugin/ matches the frozen Claude Code plugin layout.

Four things are checked against a live source of truth rather than a second hardcoded copy:
  - plugin/.mcp.json against the exact shape docs/mcp.md (line ~39-41) promises.
  - plugin/hooks/hooks.json's events against `agents.AGENTS["claude"]` (`.events` + `.also_post`),
    imported and read here at test time -- a change to that Agent record changes this test's
    expectation, not just the file's.
  - that "claude" is still a real key, and that the real CLI parser still accepts a `hook`
    subcommand with an `--agent` flag, by spawning `python -m rewindagents hook --help` rather
    than re-describing the parser in this test.
  - plugin/hooks/hooks.json's command string itself: built from the console-script name read out
    of pyproject.toml's own [project.scripts] table (never assumed to be the literal string
    "rewindagents") plus "hook"/"--agent"/the agent key, each proven live against the real CLI's
    own --help output. Nothing here pastes hooks.json's command a second time as a hardcoded
    string to compare it against -- a rename of the installed command's name, the `hook`
    subcommand, or the `--agent` flag breaks this test before it ever reaches an assertEqual.

The on-PATH form of the hook command itself ("rewindagents hook --agent claude", no absolute
interpreter path) is a packaging decision, not something `hook.hook_command()` can produce: that
function always bakes in one machine's `sys.executable`, which would be wrong for every other
machine this plugin installs onto. plugin/.mcp.json already makes the same bet (`"command":
"rewindagents"`, trusting PATH) -- see docs/plugin.md for why.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from rewindagents import __version__ as PACKAGE_VERSION  # noqa: E402
from rewindagents import agents  # noqa: E402

PLUGIN = ROOT / "plugin"

AGENT_KEY = "claude"
if AGENT_KEY not in agents.AGENTS:
    raise AssertionError(f"{AGENT_KEY!r} is no longer a key in agents.AGENTS -- plugin/hooks/hooks.json "
                          f"was written for an agent record that no longer exists")

COMMAND_FILES = (
    "rewind-status.md",
    "rewind-replay.md",
    "rewind-diff.md",
    "rewind-preview.md",
    "rewind-to-step.md",
)

# The same banned-wording shape launch_gate.sh's scope regex checks for outside tests/ (see
# CLAUDE.md's wording rule for this campaign): never describe this plugin's own
# confirm-before-destructive-action feature as blocking, a gateway, a guardrail or red-teaming.
_BANNED = re.compile(
    r"gateway|guardrail|red[- ]team|block(?:s|ed|ing)?\s+(?:the|a|an)\s+(?:call|action|command|tool)",
    re.IGNORECASE,
)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _text_files():
    """Every .json/.md file this squad shipped: plugin/ plus the one docs file it owns."""
    yield ROOT / "docs" / "plugin.md"
    for path in sorted(PLUGIN.rglob("*")):
        if path.is_file() and path.suffix in (".json", ".md"):
            yield path


class TestMcpJson(unittest.TestCase):
    """plugin/.mcp.json -- the exact shape docs/mcp.md's Registering-it section promises."""

    def test_file_exists(self):
        self.assertTrue((PLUGIN / ".mcp.json").is_file())

    def test_parses_and_matches_frozen_shape(self):
        data = _load_json(PLUGIN / ".mcp.json")
        self.assertEqual(data, {"mcpServers": {"rewindagents": {"command": "rewindagents", "args": ["mcp"]}}})

    def test_byte_content_has_no_surprise_whitespace_games(self):
        # Belt-and-suspenders: the acceptance check in the task brief parses this file directly
        # with json.load and asserts equality against the same literal dict above.
        text = (PLUGIN / ".mcp.json").read_text(encoding="utf-8")
        self.assertEqual(json.loads(text), {"mcpServers": {"rewindagents": {"command": "rewindagents",
                                                                              "args": ["mcp"]}}})


class TestPluginManifest(unittest.TestCase):
    def test_plugin_json_parses_with_required_fields(self):
        data = _load_json(PLUGIN / ".claude-plugin" / "plugin.json")
        self.assertEqual(data["name"], "rewindagents")
        self.assertEqual(data["version"], PACKAGE_VERSION, "plugin.json's version has drifted from "
                                                            "rewindagents.__version__ -- bump it")
        self.assertTrue(data["description"])
        self.assertEqual(data["author"]["name"], "John B Joseph")

    def test_marketplace_json_parses_and_lists_the_plugin(self):
        data = _load_json(PLUGIN / ".claude-plugin" / "marketplace.json")
        self.assertIn("plugins", data)
        names = [p["name"] for p in data["plugins"]]
        self.assertIn("rewindagents", names)
        entry = next(p for p in data["plugins"] if p["name"] == "rewindagents")
        self.assertEqual(entry["source"], "./")
        self.assertTrue(entry["description"])

    @unittest.skipUnless(shutil.which("claude"), "claude CLI is not on PATH in this environment")
    def test_claude_cli_validates_both_manifests(self):
        for target in (PLUGIN / ".claude-plugin" / "plugin.json", PLUGIN / ".claude-plugin" / "marketplace.json"):
            out = subprocess.run(["claude", "plugin", "validate", str(target), "--json"],
                                  capture_output=True, text=True, timeout=30)
            self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
            report = json.loads(out.stdout)
            self.assertTrue(report["success"], report)
            self.assertEqual(report["manifest"]["errors"], [])


class TestHooksJson(unittest.TestCase):
    """events and command are computed from agents.AGENTS[AGENT_KEY] and the real CLI parser at
    test time -- not pasted a second time as a hardcoded duplicate of hooks.json's own content."""

    def setUp(self):
        self.agent = agents.AGENTS[AGENT_KEY]
        self.data = _load_json(PLUGIN / "hooks" / "hooks.json")

    def test_events_match_agents_module(self):
        expected_events = sorted(self.agent.events + self.agent.also_post)
        self.assertEqual(sorted(self.data["hooks"].keys()), expected_events)

    def test_every_group_matches_every_tool(self):
        for groups in self.data["hooks"].values():
            for group in groups:
                self.assertEqual(group["matcher"], "*")

    def _console_script_name(self) -> str:
        """The installed command name, read from pyproject.toml's own [project.scripts] table --
        never assumed to be the literal string "rewindagents". Looked up by reverse-matching the
        entry-point target (`rewindagents.cli:main`) rather than by key, so a rename of the
        console-script's *name* changes what this method returns, not just what it is compared
        against."""
        try:
            import tomllib
        except ImportError:
            self.skipTest("tomllib is not available on this interpreter (needs Python 3.11+)")
        data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        scripts = data["project"]["scripts"]
        names = [name for name, target in scripts.items() if target == "rewindagents.cli:main"]
        self.assertEqual(len(names), 1,
                          f"expected exactly one console script pointing at rewindagents.cli:main "
                          f"in pyproject.toml, found {names}")
        return names[0]

    def _hook_help_text(self) -> str:
        """`--help` for the real `hook` subcommand, spawned fresh each call rather than cached, so a
        rename of the subcommand or a dropped `--agent` flag is caught by whichever test asks for it."""
        out = subprocess.run([sys.executable, "-m", "rewindagents", "hook", "--help"],
                              cwd=ROOT, env={"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin"},
                              capture_output=True, text=True, timeout=15)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        return out.stdout

    def test_command_is_the_on_path_form_for_this_agent(self):
        """The expected hooks.json command is computed, not pasted a second time: the console-script
        name comes from pyproject.toml's [project.scripts] (read-only, above), and 'hook'/'--agent'/
        the agent key are proven live against the real CLI's own --help output rather than assumed --
        so a rename anywhere in that chain (the installed command's name, the `hook` subcommand, the
        `--agent` flag, or AGENT_KEY ceasing to be a real choice) breaks this test before it ever
        reaches the `assertEqual` against hooks.json."""
        script = self._console_script_name()
        help_text = self._hook_help_text()
        self.assertIn("--agent", help_text)
        self.assertIn(AGENT_KEY, help_text)
        expected_command = f"{script} hook --agent {AGENT_KEY}"
        for event in self.agent.events + self.agent.also_post:
            commands = [h["command"] for group in self.data["hooks"][event] for h in group["hooks"]]
            self.assertEqual(commands, [expected_command], f"event {event!r}")

    def test_hook_subcommand_still_takes_an_agent_flag(self):
        # Spawn the real CLI rather than re-describe its parser: if `hook` is renamed or `--agent`
        # is dropped, this fails even though nothing above re-parsed argparse's internals.
        help_text = self._hook_help_text()
        self.assertIn("--agent", help_text)
        self.assertIn(AGENT_KEY, help_text)

    def test_console_script_name_matches_pyproject(self):
        try:
            import tomllib
        except ImportError:
            self.skipTest("tomllib is not available on this interpreter (needs Python 3.11+)")
        data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(data["project"]["scripts"].get("rewindagents"), "rewindagents.cli:main")


class TestSlashCommands(unittest.TestCase):
    def test_exactly_five_command_files_exist(self):
        found = sorted(p.name for p in (PLUGIN / "commands").glob("*.md"))
        self.assertEqual(found, sorted(COMMAND_FILES))

    def test_no_other_files_in_commands_dir(self):
        found = sorted(p.name for p in (PLUGIN / "commands").iterdir())
        self.assertEqual(found, sorted(COMMAND_FILES))

    def test_each_command_names_its_mcp_tool(self):
        tool_for = {
            "rewind-status.md": ("rewind_sessions", "rewind_summary"),
            "rewind-replay.md": ("rewind_replay",),
            "rewind-diff.md": ("rewind_diff",),
            "rewind-preview.md": ("rewind_preview",),
            "rewind-to-step.md": ("rewind_to_step",),
        }
        for name, tools in tool_for.items():
            text = (PLUGIN / "commands" / name).read_text(encoding="utf-8")
            for tool in tools:
                self.assertIn(tool, text, f"{name} does not name {tool}")
            self.assertEqual(set(tool_for), set(COMMAND_FILES))

    def test_rewind_to_step_mentions_confirm_after_asking_the_user(self):
        text = (PLUGIN / "commands" / "rewind-to-step.md").read_text(encoding="utf-8")
        self.assertIn("confirm: true", text)
        self.assertIn("requires", text.lower())
        # "asks first" / "ask the user" must appear before the confirm:true call in the file, so
        # the command tells the agent to get a human answer before it ever sets confirm.
        ask_at = text.lower().find("ask")
        confirm_at = text.find("confirm: true")
        self.assertNotEqual(ask_at, -1)
        self.assertLess(ask_at, confirm_at)

    def test_every_command_file_has_frontmatter_description(self):
        for name in COMMAND_FILES:
            text = (PLUGIN / "commands" / name).read_text(encoding="utf-8")
            self.assertTrue(text.startswith("---\n"), f"{name} is missing YAML frontmatter")
            self.assertIn("description:", text.split("---", 2)[1])


class TestNoExecutableFiles(unittest.TestCase):
    def test_no_py_or_js_files_under_plugin(self):
        offenders = [str(p.relative_to(PLUGIN)) for p in PLUGIN.rglob("*") if p.suffix in (".py", ".js")]
        self.assertEqual(offenders, [])


class TestWordingRules(unittest.TestCase):
    def test_no_banned_wording(self):
        for path in _text_files():
            text = path.read_text(encoding="utf-8")
            match = _BANNED.search(text)
            self.assertIsNone(match, f"{path}: banned wording {match and match.group(0)!r}")

    def test_no_section_sign(self):
        section_sign = chr(0xA7)  # built at runtime so this source file never embeds the glyph itself
        for path in _text_files():
            text = path.read_text(encoding="utf-8")
            self.assertNotIn(section_sign, text, f"{path} contains the section sign")

    def test_no_emoji_in_plugin_or_docs(self):
        emoji_pattern = re.compile(
            "[\U0001F300-\U0001FAFF\U00002700-\U000027BF\U00002600-\U000026FF\U0001F1E6-\U0001F1FF]"
        )
        for path in _text_files():
            text = path.read_text(encoding="utf-8")
            match = emoji_pattern.search(text)
            self.assertIsNone(match, f"{path} contains an emoji-range character {match and match.group(0)!r}")


class TestDocsPluginExists(unittest.TestCase):
    def test_docs_plugin_md_exists_and_is_honest_about_status(self):
        path = ROOT / "docs" / "plugin.md"
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8").lower()
        self.assertIn("not", text)
        self.assertIn("marketplace", text)


if __name__ == "__main__":
    unittest.main()
