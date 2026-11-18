"""Gemini CLI, GitHub Copilot CLI, Factory Droid and Qwen Code hooks: the documented payloads go through the same
recorder and checkpoint store as Claude Code's, the project scan covers every call the docs do not name as
read-only, each agent gets the reply its docs require and is never blocked, and `install` / `uninstall` write
each agent's own file.

The payloads are built from the field lists on the vendors' hook pages (src/rewindagents/agents.py quotes them,
with URLs and the date read). They are not recordings of live sessions; the README says so.
"""
import io
import json
import os
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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import live_evidence  # noqa: E402

ROOT = SRC.parent
TS = "2026-11-12T10:00:00Z"


def gemini(cwd, event, tool, tool_input, tool_response=None, session="gem-1"):
    """Gemini CLI: base fields session_id, transcript_path, cwd, hook_event_name, timestamp; BeforeTool adds
    tool_name, tool_input; AfterTool adds tool_response {llmContent, returnDisplay, error}. No call id."""
    p = {"session_id": session, "transcript_path": str(Path(cwd, "t.json")), "cwd": str(cwd),
         "hook_event_name": event, "timestamp": TS, "tool_name": tool, "tool_input": tool_input}
    if tool_response is not None:
        p["tool_response"] = tool_response
    return p


def copilot(cwd, event, tool, tool_input, tool_result=None, error=None, session="cop-1"):
    """Copilot CLI, VS Code format (PascalCase events): hook_event_name, session_id, timestamp, cwd, tool_name,
    tool_input; PostToolUse adds tool_result {result_type, text_result_for_llm}; PostToolUseFailure adds error."""
    p = {"hook_event_name": event, "session_id": session, "timestamp": TS, "cwd": str(cwd), "tool_name": tool,
         "tool_input": tool_input}
    if tool_result is not None:
        p["tool_result"] = {"result_type": "success", "text_result_for_llm": tool_result}
    if error is not None:
        p["error"] = error
    return p


def droid(cwd, event, tool, tool_input, tool_response=None, session="droid-1"):
    """Factory Droid: session_id, transcript_path, cwd, permission_mode, hook_event_name, tool_name, tool_input;
    PostToolUse adds tool_response. No call id."""
    p = {"session_id": session, "transcript_path": str(Path(cwd, "s.jsonl")), "cwd": str(cwd),
         "permission_mode": "off", "hook_event_name": event, "tool_name": tool, "tool_input": tool_input}
    if tool_response is not None:
        p["tool_response"] = tool_response
    return p


def qwen(cwd, event, tool, tool_input, tool_response=None, error=None, session="qwen-1", tid="toolu_1"):
    """Qwen Code: session_id, transcript_path, cwd, hook_event_name, timestamp, permission_mode; tool events add
    tool_name, tool_input, tool_use_id; PostToolUse adds tool_response, duration_ms; PostToolUseFailure adds
    error, is_interrupt."""
    p = {"session_id": session, "transcript_path": str(Path(cwd, "t.jsonl")), "cwd": str(cwd),
         "hook_event_name": event, "timestamp": TS, "permission_mode": "default", "tool_name": tool,
         "tool_input": tool_input, "tool_use_id": tid}
    if tool_response is not None:
        p["tool_response"] = tool_response
        p["duration_ms"] = 12
    if error is not None:
        p["error"] = error
        p["is_interrupt"] = False
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


def log(d):
    return Path(d, ".rewindagents", "log.jsonl")


class Shared:
    """The same four checks for every agent; each subclass names its payload builder and tool names."""
    agent = shell = write = None
    read_tools = ()

    def pre(self, d, tool, inp, **kw):
        raise NotImplementedError

    def post(self, d, tool, inp, **kw):
        raise NotImplementedError

    def test_shell_command_is_recorded_scanned_and_rewound(self):
        with TemporaryDirectory() as d:
            Path(d, "f.txt").write_text("1\n")
            inp = {"command": "sed -i '' s/1/2/ f.txt"}
            hook.handle(self.pre(d, self.shell, inp), self.agent)
            Path(d, "f.txt").write_text("2\n")
            hook.handle(self.post(d, self.shell, inp), self.agent)
            s = rewind.steps(log(d))
            self.assertEqual(len(s), 1)
            self.assertEqual((s[0]["tool"], s[0]["agent"], s[0]["bash_scan"]), (self.shell, self.agent, {"changed": 1}))
            self.assertEqual([r["args"]["agent"] for r in read(log(d))], [self.agent, self.agent])
            self.assertEqual(rewind.summary(s[0]), "sed -i '' s/1/2/ f.txt")
            p = rewind.rewind(log(d), 0)
            self.assertEqual((p["cannot"], p["bash_uncovered"]), ([], 0))
            self.assertEqual(Path(d, "f.txt").read_text(), "1\n")

    def test_file_write_is_covered_by_the_scan(self):
        with TemporaryDirectory() as d:
            Path(d, "app.py").write_text("v1\n")
            inp = {"file_path": str(Path(d, "app.py")), "content": "v2\n"}
            pre = hook.handle(self.pre(d, self.write, inp), self.agent)
            self.assertEqual(pre["args"]["bash_scan"]["files"], 1)
            self.assertNotIn("checkpoint", pre["args"], "no path is read out of the payload")
            Path(d, "app.py").write_text("v2\n")
            Path(d, "new.py").write_text("made by the agent\n")
            hook.handle(self.post(d, self.write, inp), self.agent)
            s = rewind.steps(log(d))[0]
            self.assertEqual(sorted(Path(c["path"]).name for c in s["checkpoints"]), ["app.py", "new.py"])
            rewind.rewind(log(d), 0)
            self.assertEqual(Path(d, "app.py").read_text(), "v1\n")
            self.assertFalse(Path(d, "new.py").exists())

    def test_read_only_tools_are_recorded_but_not_scanned(self):
        self.assertEqual(agents.AGENTS[self.agent].read_only, frozenset(self.read_tools))
        with TemporaryDirectory() as d:
            Path(d, "f.txt").write_text("1\n")
            for tool in self.read_tools:
                pre = hook.handle(self.pre(d, tool, {"q": tool}), self.agent)
                self.assertNotIn("bash_scan", pre["args"], tool)
                post = hook.handle(self.post(d, tool, {"q": tool}), self.agent)
                self.assertNotIn("checkpoints", post["args"], tool)
            self.assertFalse(Path(d, ".rewindagents", "pending").exists(), "no scan was started")
            self.assertEqual(len(rewind.steps(log(d))), len(self.read_tools))

    def test_an_unlisted_tool_is_scanned(self):
        with TemporaryDirectory() as d:
            Path(d, "f.txt").write_text("1\n")
            pre = hook.handle(self.pre(d, "mcp_fs_write", {"p": "f.txt"}), self.agent)
            self.assertEqual(pre["args"]["bash_scan"]["files"], 1)

    def test_the_installed_command_runs_and_records(self):
        ag = agents.AGENTS[self.agent]
        with TemporaryDirectory() as d:
            f = Path(d, ag.settings)
            self.assertTrue(hook.install(f, agent=self.agent))
            self.assertFalse(hook.install(f, agent=self.agent), "second install is a no-op")
            cmds = agents.commands_in(ag, f)
            self.assertEqual(sorted(cmds), sorted(ag.events + ag.also_post))
            self.assertEqual(len({c for v in cmds.values() for c in v}), 1, "one command for every event")
            self.assertTrue(all(len(v) == 1 for v in cmds.values()), cmds)
            cmd = cmds[ag.events[0]][0]
            # Not "-m rewindagents hook ...": from a clone, a Windows interpreter path takes the file-path
            # form (no "-m"); "hook --agent X" is the part both forms share (R94).
            self.assertIn("hook --agent %s" % self.agent, cmd)
            Path(d, "f.txt").write_text("1\n")
            p = subprocess.run(["bash", "-c", cmd], cwd=d, capture_output=True, text=True,
                               input=json.dumps(self.pre(d, self.shell, {"command": "ls"})))
            self.assertEqual((p.returncode, p.stdout), (0, self.reply_pre), p.stderr)
            recs = read(log(d))
            self.assertEqual((len(recs), recs[0]["args"]["agent"], recs[0]["tool"]), (1, self.agent, self.shell))
            self.assertTrue(hook.uninstall(f, agent=self.agent))
            self.assertEqual(sum(map(len, agents.commands_in(ag, f).values())), 0)

    def test_process_exits_zero_and_prints_only_the_documented_reply(self):
        with TemporaryDirectory() as d:
            inp = {"command": "ls"}
            p = run_hook(json.dumps(self.pre(d, self.shell, inp)), d, self.agent)
            self.assertEqual((p.returncode, p.stdout, p.stderr), (0, self.reply_pre, ""))
            p = run_hook(json.dumps(self.post(d, self.shell, inp)), d, self.agent)
            self.assertEqual((p.returncode, p.stdout, p.stderr), (0, self.reply_post, ""))
            self.assertEqual(len(read(log(d))), 2)
            for bad in ("not json", "[1, 2]", ""):
                p = run_hook(bad, d, self.agent)
                self.assertEqual((p.returncode, p.stdout), (0, self.reply_pre), bad)
                self.assertIn("not recorded", p.stderr)


class TestGemini(Shared, unittest.TestCase):
    agent, shell, write = "gemini", "run_shell_command", "write_file"
    read_tools = ("read_file", "read_many_files", "list_directory", "glob", "grep_search", "search_file_content",
                  "google_web_search", "web_fetch")
    reply_pre = reply_post = "{}\n"

    def pre(self, d, tool, inp, **kw):
        return gemini(d, "BeforeTool", tool, inp, **kw)

    def post(self, d, tool, inp, **kw):
        return gemini(d, "AfterTool", tool, inp, {"llmContent": "ok", "returnDisplay": "ok"}, **kw)

    def test_replace_is_scanned_and_the_reply_is_json_with_no_decision(self):
        # Gemini parses stdout as JSON on exit 0 and only "deny"/"block", continue:false or exit 2 stop a call.
        self.assertEqual(json.loads(self.reply_pre), {})
        with TemporaryDirectory() as d:
            Path(d, "a.py").write_text("old\n")
            inp = {"file_path": str(Path(d, "a.py")), "old_string": "old", "new_string": "new", "instruction": "x"}
            hook.handle(self.pre(d, "replace", inp), "gemini")
            Path(d, "a.py").write_text("new\n")
            hook.handle(self.post(d, "replace", inp), "gemini")
            s = rewind.steps(log(d))[0]
            self.assertEqual(s["result"], {"llmContent": "ok", "returnDisplay": "ok"})
            self.assertEqual(read(log(d))[0]["session"], "gem-1")
            rewind.rewind(log(d), 0)
            self.assertEqual(Path(d, "a.py").read_text(), "old\n")

    def test_install_writes_settings_json_with_a_match_all_group_and_keeps_what_is_there(self):
        with TemporaryDirectory() as d:
            f = Path(d, ".gemini", "settings.json")
            f.parent.mkdir()
            mine = {"model": {"name": "x"}, "hooks": {"BeforeTool": [{"matcher": "write_file|replace", "hooks": [
                {"name": "security-check", "type": "command", "command": "sec.sh", "timeout": 5000}]}]}}
            f.write_text(json.dumps(mine))
            self.assertTrue(hook.install(f, command="rw", agent="gemini"))
            got = json.loads(f.read_text())
            self.assertEqual(got["model"], {"name": "x"})
            self.assertEqual(got["hooks"]["BeforeTool"][0], mine["hooks"]["BeforeTool"][0])
            self.assertEqual(got["hooks"]["AfterTool"], [{"matcher": "*", "hooks": [{"type": "command", "command": "rw"}]}])
            self.assertTrue(hook.uninstall(f, command="rw", agent="gemini"))
            self.assertEqual(json.loads(f.read_text()), mine)


class TestCopilot(Shared, unittest.TestCase):
    agent, shell, write = "copilot", "bash", "create"
    read_tools = ("view", "grep", "glob", "web_fetch")
    reply_pre = reply_post = ""

    def pre(self, d, tool, inp, **kw):
        return copilot(d, "PreToolUse", tool, inp, **kw)

    def post(self, d, tool, inp, **kw):
        return copilot(d, "PostToolUse", tool, inp, tool_result="done", **kw)

    def test_a_failed_call_closes_the_scan_through_post_tool_use_failure(self):
        with TemporaryDirectory() as d:
            Path(d, "f.txt").write_text("1\n")
            inp = {"command": "echo 2 > f.txt; false"}
            hook.handle(self.pre(d, "bash", inp), "copilot")
            Path(d, "f.txt").write_text("2\n")
            hook.handle(copilot(d, "PostToolUseFailure", "bash", inp, error="exit code 1"), "copilot")
            s = rewind.steps(log(d))
            self.assertEqual((len(s), s[0]["bash_scan"], s[0]["result"]), (1, {"changed": 1}, {"error": "exit code 1"}))
            self.assertEqual(rewind.rewind(log(d), 0)["bash_uncovered"], 0)
            self.assertEqual(Path(d, "f.txt").read_text(), "1\n")

    def test_tool_result_is_the_recorded_result_and_edit_is_scanned(self):
        with TemporaryDirectory() as d:
            Path(d, "a.py").write_text("old\n")
            hook.handle(self.pre(d, "edit", {"path": "a.py"}), "copilot")
            Path(d, "a.py").write_text("new\n")
            hook.handle(self.post(d, "edit", {"path": "a.py"}), "copilot")
            s = rewind.steps(log(d))[0]
            self.assertEqual(s["result"], {"result_type": "success", "text_result_for_llm": "done"})
            self.assertEqual(read(log(d))[0]["session"], "cop-1")
            rewind.rewind(log(d), 0)
            self.assertEqual(Path(d, "a.py").read_text(), "old\n")

    def test_install_writes_a_version_1_file_with_pascal_case_events_and_bash_entries(self):
        with TemporaryDirectory() as d:
            f = Path(d, ".github", "hooks", "rewindagents.json")
            self.assertTrue(hook.install(f, command="rw", agent="copilot"))
            entry = {"type": "command", "bash": "rw"}
            self.assertEqual(json.loads(f.read_text()), {"version": 1, "hooks": {
                "PreToolUse": [entry], "PostToolUse": [entry], "PostToolUseFailure": [entry]}})
            mine = {"version": 1, "hooks": {"preToolUse": [{"type": "command", "bash": "./check.sh", "timeoutSec": 30}],
                                            "PreToolUse": [{"type": "command", "bash": "other"}]}}
            g = Path(d, "team.json")
            g.write_text(json.dumps(mine))
            self.assertTrue(hook.install(g, command="rw", agent="copilot"))
            self.assertEqual(json.loads(g.read_text())["hooks"]["PreToolUse"], [{"type": "command", "bash": "other"}, entry])
            self.assertTrue(hook.uninstall(g, command="rw", agent="copilot"))
            self.assertEqual(json.loads(g.read_text()), mine)

    def test_the_command_cannot_fail_closed(self):
        # Copilot: "a crash or non-zero exit (including exit 2) denies the tool call". The command ends in
        # `|| true`, so an interpreter that is not there (the cloud agent's sandbox) still exits 0.
        with patch.object(hook, "installed", return_value=True), \
                patch.object(hook.sys, "executable", "/nonexistent/python3"):
            cmd = hook.hook_command("copilot")
            plain = hook.hook_command("codex")
        self.assertEqual(cmd, "/nonexistent/python3 -m rewindagents hook --agent copilot || true")
        self.assertFalse(plain.endswith("|| true"), "only fail-closed agents get the guard")
        payload = json.dumps(copilot("/tmp", "PreToolUse", "bash", {"command": "ls"}))
        p = subprocess.run(["bash", "-c", cmd], input=payload, capture_output=True, text=True)
        self.assertEqual((p.returncode, p.stdout), (0, ""), "missing interpreter: still exit 0, still no output")
        p = subprocess.run(["bash", "-c", cmd[: -len(" || true")]], input=payload, capture_output=True, text=True)
        self.assertNotEqual(p.returncode, 0, "without the guard the same command would deny the call")
        self.assertEqual([a for a in sorted(agents.AGENTS) if agents.AGENTS[a].fail_closed], ["copilot"])

    def test_default_file_is_in_github_hooks(self):
        self.assertEqual(agents.AGENTS["copilot"].settings, ".github/hooks/rewindagents.json")


class TestDroid(Shared, unittest.TestCase):
    agent, shell, write = "droid", "Execute", "Create"
    read_tools = ("Read", "LS", "Glob", "Grep", "FetchUrl", "WebSearch")
    reply_pre = reply_post = ""

    def pre(self, d, tool, inp, **kw):
        return droid(d, "PreToolUse", tool, inp, **kw)

    def post(self, d, tool, inp, **kw):
        return droid(d, "PostToolUse", tool, inp, {"output": "ok"}, **kw)

    def test_install_uses_hooks_json_when_it_exists_and_settings_json_otherwise(self):
        # Droid reads the hooks key of settings.json only "if hooks.json is absent": writing a new hooks.json
        # would hide the user's settings.json hooks, and writing settings.json next to a hooks.json does nothing.
        with TemporaryDirectory() as d:
            here = os.getcwd()
            os.chdir(d)
            try:
                self.assertEqual(cli("install", "--agent", "droid"), (0, "installed in .factory/settings.json\n"))
                self.assertFalse(Path(d, ".factory", "hooks.json").exists(), "hooks.json is not created")
                got = json.loads(Path(d, ".factory", "settings.json").read_text())
                self.assertEqual(sorted(got["hooks"]), ["PostToolUse", "PreToolUse"])
                self.assertEqual(cli("uninstall", "--agent", "droid"), (0, "removed from .factory/settings.json\n"))
                mine = {"PreToolUse": [{"matcher": "Execute", "hooks": [{"type": "command", "command": "guard.sh"}]}],
                        "Stop": [{"hooks": [{"type": "command", "command": "bye"}]}]}
                Path(d, ".factory", "hooks.json").write_text(json.dumps(mine))
                before = Path(d, ".factory", "settings.json").read_bytes()
                self.assertEqual(cli("install", "--agent", "droid"), (0, "installed in .factory/hooks.json\n"))
                self.assertEqual(Path(d, ".factory", "settings.json").read_bytes(), before, "settings.json untouched")
                got = json.loads(Path(d, ".factory", "hooks.json").read_text())
                self.assertNotIn("hooks", got, "hooks.json is keyed by event name at the top level")
                self.assertEqual(got["PreToolUse"][0], mine["PreToolUse"][0])
                self.assertEqual(got["PostToolUse"][0]["matcher"], "*")
                cmd = got["PostToolUse"][0]["hooks"][0]["command"]
                self.assertEqual(agents.commands_in(agents.AGENTS["droid"], Path(d, ".factory", "hooks.json")),
                                 {"PreToolUse": ["guard.sh", cmd], "PostToolUse": [cmd]})
                self.assertEqual(cli("install", "--agent", "droid"), (0, "already installed in .factory/hooks.json\n"))
                self.assertEqual(cli("uninstall", "--agent", "droid"), (0, "removed from .factory/hooks.json\n"))
                self.assertEqual(json.loads(Path(d, ".factory", "hooks.json").read_text()), mine)
            finally:
                os.chdir(here)

    def test_a_flat_file_with_only_our_hook_uninstalls_to_an_empty_object(self):
        with TemporaryDirectory() as d:
            f = Path(d, "hooks.json")
            self.assertTrue(hook.install(f, command="rw", agent="droid"))
            self.assertEqual(json.loads(f.read_text()), {
                "PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "rw"}]}],
                "PostToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "rw"}]}]})
            self.assertTrue(hook.uninstall(f, command="rw", agent="droid"))
            self.assertEqual(json.loads(f.read_text()), {})


class TestQwen(Shared, unittest.TestCase):
    agent, shell, write = "qwen", "run_shell_command", "write_file"
    read_tools = ("read_file", "list_directory", "glob", "grep_search")
    reply_pre = reply_post = ""

    def pre(self, d, tool, inp, **kw):
        return qwen(d, "PreToolUse", tool, inp, **kw)

    def post(self, d, tool, inp, **kw):
        return qwen(d, "PostToolUse", tool, inp, {"output": "ok"}, **kw)

    def test_a_failed_call_closes_the_scan_through_post_tool_use_failure(self):
        with TemporaryDirectory() as d:
            Path(d, "f.txt").write_text("1\n")
            inp = {"command": "rm f.txt && false"}
            hook.handle(qwen(d, "PreToolUse", "run_shell_command", inp, tid="toolu_9"), "qwen")
            Path(d, "f.txt").unlink()
            hook.handle(qwen(d, "PostToolUseFailure", "run_shell_command", inp, error="exit 1", tid="toolu_9"), "qwen")
            s = rewind.steps(log(d))
            self.assertEqual((len(s), s[0]["bash_scan"], s[0]["result"]), (1, {"changed": 1}, {"error": "exit 1"}))
            rewind.rewind(log(d), 0)
            self.assertEqual(Path(d, "f.txt").read_text(), "1\n")

    def test_install_adds_the_failure_event_and_keeps_what_is_there(self):
        with TemporaryDirectory() as d:
            f = Path(d, ".qwen", "settings.json")
            f.parent.mkdir()
            mine = {"hooks": {"PreToolUse": [{"matcher": "write_file", "hooks": [
                {"type": "command", "command": "\"$QWEN_PROJECT_DIR/.qwen/hooks/check.sh\"", "name": "check", "timeout": 10}]}]}}
            f.write_text(json.dumps(mine))
            self.assertTrue(hook.install(f, command="rw", agent="qwen"))
            got = json.loads(f.read_text())
            self.assertEqual(sorted(got["hooks"]), ["PostToolUse", "PostToolUseFailure", "PreToolUse"])
            self.assertEqual(got["hooks"]["PostToolUseFailure"], [{"matcher": "*", "hooks": [{"type": "command", "command": "rw"}]}])
            self.assertTrue(hook.uninstall(f, command="rw", agent="qwen"))
            self.assertEqual(json.loads(f.read_text()), mine)


class TestCliAndDocs(unittest.TestCase):
    NEW = {"gemini": ".gemini/settings.json", "copilot": ".github/hooks/rewindagents.json",
           "droid": ".factory/settings.json", "qwen": ".qwen/settings.json"}

    def test_install_agent_flag_writes_each_new_agents_file(self):
        with TemporaryDirectory() as d:
            here = os.getcwd()
            os.chdir(d)
            try:
                for agent, path in self.NEW.items():
                    self.assertEqual(agents.AGENTS[agent].settings, path)
                    self.assertEqual(cli("install", "--agent", agent), (0, "installed in %s\n" % path))
                    self.assertEqual(cli("install", "--agent", agent), (0, "already installed in %s\n" % path))
                    self.assertEqual(cli("uninstall", "--agent", agent), (0, "removed from %s\n" % path))
            finally:
                os.chdir(here)

    def test_the_module_cites_each_vendor_page_and_the_date_read(self):
        doc = agents.__doc__
        for s in (agents.GEMINI_DOCS, agents.COPILOT_DOCS, agents.DROID_DOCS, agents.QWEN_DOCS, agents.DOCS_READ_2,
                  "BeforeTool", "AfterTool", "tool_result", "PostToolUseFailure", "fail-closed", "if hooks.json is absent",
                  "Not supported, and why", "harness/live/evidence"):
            self.assertIn(s, doc, s)
        # the module's own live-status sentences follow harness/live/evidence/*.json, both directions
        self.assertEqual(live_evidence.mismatches(doc, live_evidence.load()), [])

    def test_readme_names_each_new_agent_its_file_and_its_unscanned_tools(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for agent in self.NEW:
            ag = agents.AGENTS[agent]
            self.assertIn("rewindagents install --agent %s" % agent, readme)
            self.assertIn(ag.settings, readme)
            for tool in sorted(ag.read_only):
                self.assertIn("`%s`" % tool, readme, tool)
        for s in ("|| true", ".factory/hooks.json", "PostToolUseFailure", "`{}`"):
            self.assertIn(s, readme, s)
        low = readme.lower()
        for name in ("gemini cli", "copilot cli", "droid", "qwen code"):
            self.assertIn(name, low)
        evidence = live_evidence.load()
        self.assertEqual(live_evidence.mismatches(readme, evidence), [])
        self.assertEqual(live_evidence.versions_missing(readme, evidence), [])



class TestLiveStatusCheck(unittest.TestCase):
    """The live-status check itself: it reads one evidence file per agent and it can fail in both directions, so a
    green README/site check above is not a check that could never fail."""

    def setUp(self):
        self.readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.evidence = live_evidence.load()

    def test_one_evidence_file_per_agent_with_a_known_status(self):
        self.assertEqual(sorted(self.evidence), sorted(agents.AGENTS))
        for key, ev in self.evidence.items():
            self.assertEqual(ev["agent"], key)
            self.assertIn(ev["status"], ("VERIFIED_LIVE", "NOT_INSTALLED", "INSTALL_BLOCKED", "RAN_NO_LOG", "FAILED"))

    def test_an_agent_that_ran_live_but_is_called_not_live_fails(self):
        for key, ev in self.evidence.items():
            if live_evidence.verified(ev):
                flipped = dict(self.evidence, **{key: dict(ev, status="RAN_NO_LOG")})
                self.assertTrue(live_evidence.mismatches(self.readme, flipped), key)

    def test_an_agent_that_did_not_run_live_but_is_called_live_fails(self):
        for key, ev in self.evidence.items():
            if not live_evidence.verified(ev):
                flipped = dict(self.evidence, **{key: dict(ev, status="VERIFIED_LIVE")})
                self.assertTrue(live_evidence.mismatches(self.readme, flipped), key)

    def test_the_old_wording_fails(self):
        old = ("The Claude Code hook has run in real sessions; the other six hooks are built from the vendors' hook "
               "documentation and tested with the documented payloads, not yet in a live session.")
        problems = live_evidence.mismatches(old, self.evidence)
        self.assertTrue(problems)
        self.assertTrue(any("without the date" in p for p in problems), problems)

    def test_a_live_claim_names_the_date_of_the_run(self):
        text = self.readme.replace("2026-11-18", "2026-01-01")
        self.assertTrue(any("without the date" in p for p in live_evidence.mismatches(text, self.evidence)))

if __name__ == "__main__":
    unittest.main()
