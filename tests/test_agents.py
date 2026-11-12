"""Codex and Cursor hooks (R7): the documented payloads go through the same recorder and the same
checkpoint store as Claude Code's, the project scan covers edits whose input shape is not documented, the
hook answers each agent the way its docs require and never blocks, and `install` writes each agent's file.

The payloads here are the ones the vendors' docs describe (src/rewindagents/agents.py quotes the sources).
They are not recordings of a live Codex or Cursor session; the README says so.
"""
import io
import json
import os
import re
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from rewindagents import agents, hook, read, rewind  # noqa: E402
from rewindagents.cli import main  # noqa: E402

ROOT = SRC.parent


def cursor(cwd, event, tool, tool_input, tool_output=None, conv="conv-1", tid="abc123"):
    """A Cursor hook payload with the fields its docs list for preToolUse / postToolUse."""
    p = {"conversation_id": conv, "generation_id": "gen-1", "hook_event_name": event, "workspace_roots": [str(cwd)],
         "tool_name": tool, "tool_input": tool_input, "tool_use_id": tid, "cwd": str(cwd)}
    if tool_output is not None:
        p["tool_output"] = json.dumps(tool_output)      # "JSON-stringified result payload from the tool"
        p["duration"] = 12
    return p


def codex(cwd, event, tool, tool_input, tool_response=None, session="codex-1", tid="call_1"):
    """A Codex hook payload with the fields its docs list for PreToolUse / PostToolUse."""
    p = {"session_id": session, "transcript_path": str(Path(cwd, "t.jsonl")), "cwd": str(cwd),
         "hook_event_name": event, "model": "m", "tool_name": tool, "tool_use_id": tid, "tool_input": tool_input}
    if tool_response is not None:
        p["tool_response"] = tool_response
    return p


def run_hook(stdin_text, cwd, agent):
    env = dict(os.environ, PYTHONPATH=str(SRC))
    return subprocess.run([sys.executable, "-m", "rewindagents", "hook", "--agent", agent], input=stdin_text,
                          capture_output=True, text=True, cwd=cwd, env=env)


def cli(*argv):
    out = io.StringIO()
    with redirect_stdout(out):
        code = main(list(argv))
    return code, out.getvalue()


class TestCursor(unittest.TestCase):
    def test_shell_command_is_recorded_scanned_and_rewound(self):
        with TemporaryDirectory() as d:
            Path(d, "f.txt").write_text("1\n")
            inp = {"command": "sed -i '' s/1/2/ f.txt", "working_directory": d}
            hook.handle(cursor(d, "preToolUse", "Shell", inp), "cursor")
            Path(d, "f.txt").write_text("2\n")
            hook.handle(cursor(d, "postToolUse", "Shell", inp, {"output": "", "exit_code": 0}), "cursor")
            lg = Path(d, ".rewindagents", "log.jsonl")
            recs = read(lg)
            self.assertEqual([r["session"] for r in recs], ["conv-1", "conv-1"], "session is conversation_id")
            self.assertEqual([r["args"]["agent"] for r in recs], ["cursor", "cursor"])
            s = rewind.steps(lg)
            self.assertEqual(len(s), 1)
            self.assertEqual((s[0]["tool"], s[0]["bash_scan"], s[0]["agent"]), ("Shell", {"changed": 1}, "cursor"))
            self.assertEqual(s[0]["result"], {"output": "", "exit_code": 0}, "tool_output is decoded from its JSON string")
            self.assertEqual(rewind.summary(s[0], root=Path(d)), "sed -i '' s/1/2/ f.txt")
            p = rewind.rewind(lg, 0)
            self.assertEqual((p["cannot"], p["bash_uncovered"]), ([], 0))
            self.assertEqual(Path(d, "f.txt").read_text(), "1\n")

    def test_write_with_an_undocumented_input_shape_is_covered_by_the_scan(self):
        # Cursor does not document Write's tool_input. Whatever it is, the hook never reads a path out of it:
        # the before/after scan finds the changed and created files on its own.
        with TemporaryDirectory() as d:
            Path(d, "app.py").write_text("v1\n")
            inp = {"some_field": "app.py", "contents": "v2\n"}       # an invented shape, on purpose
            pre = hook.handle(cursor(d, "preToolUse", "Write", inp), "cursor")
            self.assertNotIn("checkpoint", pre["args"])
            self.assertEqual(pre["args"]["bash_scan"]["files"], 1)
            Path(d, "app.py").write_text("v2\n")
            Path(d, "new.py").write_text("made by the agent\n")
            hook.handle(cursor(d, "postToolUse", "Write", inp, {"ok": True}), "cursor")
            s = rewind.steps(Path(d, ".rewindagents", "log.jsonl"))[0]
            self.assertEqual(sorted(Path(c["path"]).name for c in s["checkpoints"]), ["app.py", "new.py"])
            rewind.rewind(Path(d, ".rewindagents", "log.jsonl"), 0)
            self.assertEqual(Path(d, "app.py").read_text(), "v1\n")
            self.assertFalse(Path(d, "new.py").exists())

    def test_delete_and_mcp_tools_are_scanned_too(self):
        with TemporaryDirectory() as d:
            Path(d, "keep.txt").write_text("k\n")
            for tool, tid in (("Delete", "t1"), ("MCP:filesystem_write", "t2")):
                hook.handle(cursor(d, "preToolUse", tool, {"x": 1}, tid=tid), "cursor")
                Path(d, "keep.txt").unlink() if tool == "Delete" else Path(d, "keep.txt").write_text("mcp\n")
                hook.handle(cursor(d, "postToolUse", tool, {"x": 1}, {"ok": True}, tid=tid), "cursor")
            lg = Path(d, ".rewindagents", "log.jsonl")
            self.assertEqual([s["bash_scan"] for s in rewind.steps(lg)], [{"changed": 1}, {"changed": 1}])
            rewind.rewind(lg, 0)
            self.assertEqual(Path(d, "keep.txt").read_text(), "k\n")

    def test_read_and_grep_are_recorded_but_not_scanned(self):
        with TemporaryDirectory() as d:
            Path(d, "f.txt").write_text("1\n")
            for tool in ("Read", "Grep"):
                pre = hook.handle(cursor(d, "preToolUse", tool, {"query": "x"}), "cursor")
                self.assertNotIn("bash_scan", pre["args"])
                self.assertNotIn("checkpoint", pre["args"])
                post = hook.handle(cursor(d, "postToolUse", tool, {"query": "x"}, {"lines": []}), "cursor")
                self.assertNotIn("checkpoints", post["args"])
            self.assertFalse(Path(d, ".rewindagents", "objects").exists(), "nothing was saved")
            self.assertFalse(Path(d, ".rewindagents", "pending").exists(), "no scan was started")
            self.assertEqual(len(rewind.steps(Path(d, ".rewindagents", "log.jsonl"))), 2, "both calls are steps")
            self.assertEqual(agents.AGENTS["cursor"].read_only, {"Read", "Grep"})

    def test_a_shell_call_without_its_post_event_is_reported_as_not_scanned(self):
        with TemporaryDirectory() as d:
            Path(d, "f.txt").write_text("1\n")
            hook.handle(cursor(d, "preToolUse", "Shell", {"command": "rm -rf build", "working_directory": d}), "cursor")
            lg = Path(d, ".rewindagents", "log.jsonl")
            self.assertEqual(rewind.rewind(lg, 0, dry_run=True)["bash_uncovered"], 1)
            code, out = cli("--log", str(lg), "rewind", "0", "--dry-run")
            self.assertEqual(code, 1)        # README: anything not restored -> exit 1
            self.assertIn("1 step(s) after step 0 were not scanned", out)

    def test_process_answers_allow_before_a_call_and_an_empty_object_after_it(self):
        # Cursor: a permission hook whose output is empty or invalid can block the action, so the hook must
        # answer; "allow" is the one answer that changes nothing (another hook's deny still wins).
        with TemporaryDirectory() as d:
            Path(d, "f.txt").write_text("1\n")
            inp = {"command": "ls", "working_directory": d}
            p = run_hook(json.dumps(cursor(d, "preToolUse", "Shell", inp)), d, "cursor")
            self.assertEqual((p.returncode, p.stdout, p.stderr), (0, '{"permission": "allow"}\n', ""))
            p = run_hook(json.dumps(cursor(d, "postToolUse", "Shell", inp, {"output": "f.txt"})), d, "cursor")
            self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "{}\n", ""))
            self.assertEqual(len(read(Path(d, ".rewindagents", "log.jsonl"))), 2)
            for bad in ("not json", "[1, 2]", ""):
                p = run_hook(bad, d, "cursor")
                self.assertEqual((p.returncode, p.stdout), (0, '{"permission": "allow"}\n'), bad)
                self.assertIn("not recorded", p.stderr)
            self.assertEqual(json.loads(p.stdout)["permission"], "allow")

    def test_install_writes_hooks_json_and_keeps_what_is_there(self):
        with TemporaryDirectory() as d:
            f = Path(d, ".cursor", "hooks.json")
            f.parent.mkdir()
            f.write_text(json.dumps({"version": 1, "hooks": {"preToolUse": [{"command": "other", "matcher": "Shell"}],
                                                              "stop": [{"command": "bye"}]}}))
            self.assertTrue(hook.install(f, command="rw", agent="cursor"))
            got = json.loads(f.read_text())
            self.assertEqual(got["version"], 1)
            self.assertEqual(got["hooks"]["preToolUse"], [{"command": "other", "matcher": "Shell"}, {"command": "rw"}])
            self.assertEqual(got["hooks"]["postToolUse"], [{"command": "rw"}])
            self.assertEqual(got["hooks"]["stop"], [{"command": "bye"}])
            self.assertFalse(hook.install(f, command="rw", agent="cursor"), "second install is a no-op")
            fresh = Path(d, "fresh", "hooks.json")
            self.assertTrue(hook.install(fresh, command="rw", agent="cursor"))
            self.assertEqual(json.loads(fresh.read_text()),
                             {"version": 1, "hooks": {"preToolUse": [{"command": "rw"}], "postToolUse": [{"command": "rw"}]}})

    def test_the_installed_command_runs_from_hooks_json(self):
        with TemporaryDirectory() as d:
            f = Path(d, ".cursor", "hooks.json")
            hook.install(f, agent="cursor")
            cmds = agents.commands_in(agents.AGENTS["cursor"], f)
            self.assertEqual(cmds["preToolUse"], cmds["postToolUse"])
            cmd = cmds["preToolUse"][0]
            self.assertTrue(cmd.endswith(" -m rewindagents hook --agent cursor"), cmd)
            Path(d, "f.txt").write_text("1\n")
            payload = cursor(d, "preToolUse", "Shell", {"command": "ls", "working_directory": d})
            p = subprocess.run(cmd, shell=True, cwd=d, capture_output=True, text=True, input=json.dumps(payload))
            self.assertEqual((p.returncode, p.stdout), (0, '{"permission": "allow"}\n'), p.stderr)
            recs = read(Path(d, ".rewindagents", "log.jsonl"))
            self.assertEqual((len(recs), recs[0]["args"]["agent"], recs[0]["tool"]), (1, "cursor", "Shell"))


class TestCodex(unittest.TestCase):
    def test_bash_goes_through_the_claude_code_path(self):
        with TemporaryDirectory() as d:
            Path(d, "f.txt").write_text("1\n")
            inp = {"command": ["bash", "-lc", "sed -i '' s/1/2/ f.txt"]}
            hook.handle(codex(d, "PreToolUse", "Bash", inp), "codex")
            Path(d, "f.txt").write_text("2\n")
            hook.handle(codex(d, "PostToolUse", "Bash", inp, {"output": "", "metadata": {"exit_code": 0}}), "codex")
            lg = Path(d, ".rewindagents", "log.jsonl")
            s = rewind.steps(lg)
            self.assertEqual((len(s), s[0]["tool"], s[0]["agent"], s[0]["bash_scan"]), (1, "Bash", "codex", {"changed": 1}))
            self.assertEqual(s[0]["result"], {"output": "", "metadata": {"exit_code": 0}})
            self.assertEqual(rewind.summary(s[0]), "bash -lc sed -i '' s/1/2/ f.txt", "a list command is shown as words")
            rewind.rewind(lg, 0)
            self.assertEqual(Path(d, "f.txt").read_text(), "1\n")
            self.assertEqual(read(lg)[0]["session"], "codex-1")

    def test_apply_patch_is_scanned_without_reading_its_input(self):
        with TemporaryDirectory() as d:
            Path(d, "a.py").write_text("old\n")
            inp = {"input": "*** Begin Patch\n*** Update File: a.py\n-old\n+new\n*** End Patch"}   # opaque to the hook
            pre = hook.handle(codex(d, "PreToolUse", "apply_patch", inp), "codex")
            self.assertEqual(pre["args"]["bash_scan"]["files"], 1)
            self.assertNotIn("checkpoint", pre["args"])
            Path(d, "a.py").write_text("new\n")
            hook.handle(codex(d, "PostToolUse", "apply_patch", inp, {"output": "Success."}), "codex")
            lg = Path(d, ".rewindagents", "log.jsonl")
            self.assertEqual([Path(c["path"]).name for c in rewind.steps(lg)[0]["checkpoints"]], ["a.py"])
            rewind.rewind(lg, 0)
            self.assertEqual(Path(d, "a.py").read_text(), "old\n")

    def test_update_plan_is_not_scanned_and_mcp_tools_are(self):
        with TemporaryDirectory() as d:
            Path(d, "f.txt").write_text("1\n")
            pre = hook.handle(codex(d, "PreToolUse", "update_plan", {"plan": []}), "codex")
            self.assertNotIn("bash_scan", pre["args"])
            pre = hook.handle(codex(d, "PreToolUse", "mcp__fs__write_file", {"p": "f.txt"}, tid="call_2"), "codex")
            self.assertEqual(pre["args"]["bash_scan"]["files"], 1)
            self.assertEqual(agents.AGENTS["codex"].read_only, {"update_plan"})

    def test_process_prints_nothing_and_exits_zero(self):
        with TemporaryDirectory() as d:
            p = run_hook(json.dumps(codex(d, "PreToolUse", "Bash", {"command": "ls"})), d, "codex")
            self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "", ""))
            p = run_hook("garbage", d, "codex")
            self.assertEqual((p.returncode, p.stdout), (0, ""))
            self.assertIn("not recorded", p.stderr)

    def test_install_writes_hooks_json_in_the_claude_code_shape(self):
        with TemporaryDirectory() as d:
            f = Path(d, ".codex", "hooks.json")
            f.parent.mkdir()
            f.write_text(json.dumps({"description": "mine", "hooks": {"PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "other"}]}]}}))
            self.assertTrue(hook.install(f, agent="codex"))
            got = json.loads(f.read_text())
            self.assertEqual(got["description"], "mine")
            self.assertEqual(got["hooks"]["PreToolUse"][0]["hooks"][0]["command"], "other")
            cmds = agents.commands_in(agents.AGENTS["codex"], f)
            self.assertEqual(len(cmds["PreToolUse"]), 2)
            self.assertEqual(cmds["PostToolUse"], [cmds["PreToolUse"][1]])
            cmd = cmds["PostToolUse"][0]
            self.assertTrue(cmd.endswith(" -m rewindagents hook --agent codex"), cmd)
            self.assertEqual(got["hooks"]["PostToolUse"][0]["matcher"], "*")
            self.assertFalse(hook.install(f, agent="codex"))
            p = subprocess.run(cmd, shell=True, cwd=d, capture_output=True, text=True,
                               input=json.dumps(codex(d, "PreToolUse", "Bash", {"command": "ls"})))
            self.assertEqual((p.returncode, p.stdout), (0, ""), p.stderr)
            self.assertEqual(read(Path(d, ".rewindagents", "log.jsonl"))[0]["args"]["agent"], "codex")


class TestCli(unittest.TestCase):
    def test_install_agent_flag_picks_the_agents_file_in_the_current_project(self):
        with TemporaryDirectory() as d:
            here = os.getcwd()
            os.chdir(d)
            try:
                for agent, path in (("cursor", ".cursor/hooks.json"), ("codex", ".codex/hooks.json"), ("claude", ".claude/settings.json")):
                    self.assertEqual(cli("install", "--agent", agent), (0, "installed in %s\n" % path))
                    self.assertTrue(Path(d, path).is_file(), path)
                    self.assertEqual(cli("install", "--agent", agent), (0, "already installed in %s\n" % path))
                    self.assertEqual(agents.AGENTS[agent].settings, path)
                self.assertEqual(cli("install"), (0, "already installed in .claude/settings.json\n"), "default is Claude Code")
                self.assertEqual(cli("install", "--agent", "cursor", "--settings", "u/hooks.json"), (0, "installed in u/hooks.json\n"))
                self.assertEqual(json.loads(Path(d, "u", "hooks.json").read_text())["version"], 1)
            finally:
                os.chdir(here)
            with self.assertRaises(SystemExit) as cm:
                cli("install", "--agent", "copilot")
            self.assertEqual(cm.exception.code, 2)

    def test_hook_command_carries_the_agent_and_claude_codes_is_unchanged(self):
        import shlex
        py = shlex.quote(sys.executable)
        with patch.object(hook, "installed", return_value=True):
            self.assertEqual(hook.hook_command(), f"{py} -m rewindagents hook")
            self.assertEqual(hook.hook_command("claude"), f"{py} -m rewindagents hook")
            self.assertEqual(hook.hook_command("cursor"), f"{py} -m rewindagents hook --agent cursor")
            self.assertEqual(hook.hook_command("codex"), f"{py} -m rewindagents hook --agent codex")
        with patch.object(hook, "installed", return_value=False):
            self.assertEqual(hook.hook_command("codex"),
                             f"PYTHONPATH={shlex.quote(str(SRC))} {py} -m rewindagents hook --agent codex")

    def test_claude_code_records_carry_their_agent_and_still_print_nothing(self):
        with TemporaryDirectory() as d:
            rec = hook.handle({"session_id": "s", "cwd": d, "hook_event_name": "PreToolUse", "tool_name": "Bash",
                               "tool_input": {"command": "ls"}})
            self.assertEqual(rec["args"]["agent"], "claude")
            self.assertEqual(hook.run(io.StringIO("{")), 0)
            self.assertEqual(agents.AGENTS["claude"].reply, {})


class TestDocs(unittest.TestCase):
    def test_the_module_cites_the_vendor_docs_and_the_date_they_were_read(self):
        doc = agents.__doc__
        for s in (agents.CURSOR_DOCS, agents.CODEX_DOCS, agents.DOCS_READ, "preToolUse", "postToolUse", "tool_output",
                  "conversation_id", "apply_patch", "tool_response", "not yet run inside a live"):
            self.assertIn(s, doc, s)

    def test_readme_describes_the_hooks_as_the_code_has_them(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for agent in ("codex", "cursor"):
            self.assertIn("rewindagents install --agent %s" % agent, readme)
            self.assertIn(agents.AGENTS[agent].settings, readme)
        self.assertIn('{"permission": "allow"}', readme)
        for tool in sorted(agents.AGENTS["cursor"].read_only | agents.AGENTS["codex"].read_only):
            self.assertIn("`%s`" % tool, readme, "the README names every tool the hook does not scan around")
        low = readme.lower()
        self.assertIn("not yet in a live", low, "the README says the Codex and Cursor hooks have not run in a live session")
        self.assertNotRegex(low, r"planned:\s*hooks for codex", "the hooks exist; the README must not call them planned")
        for line in readme.splitlines():
            if "planned" in line.lower():
                self.assertNotRegex(line, r"Codex|Cursor", "planned no longer applies to the hooks: %s" % line)


if __name__ == "__main__":
    unittest.main()
