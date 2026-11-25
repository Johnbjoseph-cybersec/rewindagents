"""Runs the console script that `pip install .` put in .venv, not the source tree.

.fire-test-cmd builds .venv, installs the package into it and sets REWINDAGENTS_BIN, so in the launch gate's
fresh clone these tests always run. Without REWINDAGENTS_BIN they are skipped (a plain `unittest discover`).
The README check at the bottom runs either way.
"""
import json
import os
import re
import shlex
import subprocess
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
from rewindagents import agents  # noqa: E402  (only for the agents' event names; the binary under test runs without src)
BIN = os.environ.get("REWINDAGENTS_BIN")
VERSION = re.search(r'^__version__ = "([^"]+)"', (SRC / "rewindagents" / "__init__.py").read_text(), re.M).group(1)
SUBCOMMANDS = set(re.findall(r'sub\.add_parser\("([\w-]+)"', (SRC / "rewindagents" / "cli.py").read_text()))


def clean_env():
    return {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}


@unittest.skipUnless(BIN, "REWINDAGENTS_BIN not set; .fire-test-cmd sets it after pip install")
class InstalledCommandTest(unittest.TestCase):
    def _run(self, *argv, cwd, stdin=None):
        return subprocess.run([BIN, *argv], cwd=cwd, env=clean_env(), input=stdin,
                              capture_output=True, text=True, timeout=120)

    def test_binary_exists_and_reports_the_source_version(self):
        self.assertTrue(Path(BIN).is_file(), BIN)
        with TemporaryDirectory() as d:
            r = self._run("--version", cwd=d)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, f"rewindagents {VERSION}"), r.stderr)

    def test_package_is_imported_from_the_install_not_src(self):
        py = Path(BIN).parent / "python"
        with TemporaryDirectory() as d:
            r = subprocess.run([str(py), "-I", "-c", "import rewindagents; print(rewindagents.__file__)"],
                               cwd=d, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("site-packages", r.stdout)
        self.assertNotIn(str(SRC), r.stdout)

    def test_install_writes_a_hook_command_without_pythonpath(self):
        with TemporaryDirectory() as proj:
            r = self._run("install", cwd=proj)
            self.assertEqual((r.returncode, r.stdout.strip()), (0, "installed in .claude/settings.json"), r.stderr)
            settings = json.loads(Path(proj, ".claude", "settings.json").read_text())
            cmds = {h["command"] for ev in ("PreToolUse", "PostToolUse")
                    for g in settings["hooks"][ev] for h in g["hooks"]}
        self.assertEqual(len(cmds), 1, cmds)
        cmd = cmds.pop()
        self.assertNotIn("PYTHONPATH", cmd)
        words = shlex.split(cmd)
        self.assertEqual(words[1:], ["-m", "rewindagents", "hook"], cmd)
        self.assertTrue(Path(words[0]).is_absolute(), cmd)
        # The named interpreter must import the package on its own, with nothing inherited from this process.
        with TemporaryDirectory() as d:
            r = subprocess.run([words[0], "-I", "-c", "import rewindagents; print(rewindagents.__file__)"],
                               cwd=d, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("site-packages", r.stdout)

    def test_hook_from_the_settings_file_records_a_real_sed_and_the_binary_rewinds_it(self):
        with TemporaryDirectory() as proj:
            Path(proj, "app.py").write_text("x = 1\n")
            self.assertEqual(self._run("install", cwd=proj).returncode, 0)
            cmd = json.loads(Path(proj, ".claude", "settings.json").read_text())["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
            shell = "sed -i.bak s/1/2/ app.py && rm app.py.bak"

            def hook_call(event):
                payload = {"session_id": "inst", "cwd": proj, "hook_event_name": event, "tool_name": "Bash",
                           "tool_input": {"command": shell}, "tool_use_id": "toolu_1"}
                p = subprocess.run(cmd, shell=True, cwd=proj, env=clean_env(), input=json.dumps(payload),
                                   capture_output=True, text=True, timeout=120)
                self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "", ""))

            hook_call("PreToolUse")
            subprocess.run(["sh", "-c", shell], cwd=proj, check=True)
            hook_call("PostToolUse")
            self.assertEqual(Path(proj, "app.py").read_text(), "x = 2\n")

            r = self._run("replay", cwd=proj)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("sed -i.bak", r.stdout)
            r = self._run("rewind", "0", cwd=proj)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(Path(proj, "app.py").read_text(), "x = 1\n")
            self.assertIn("undo it with: rewindagents rewind 1 --session inst", r.stdout)
            r = self._run("verify", cwd=proj)
            self.assertEqual((r.returncode, r.stdout.strip()), (0, "OK: 3 records, chain intact"), r.stderr)
            r = self._run("sessions", cwd=proj)                    # the Bash step and the rewind: 2 steps, app.py
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertRegex(r.stdout.splitlines()[0], r"^inst  .* to .*  2 steps \(1 rewind\)  1 files  \(latest\)$")
            self.assertEqual(r.stdout.splitlines()[1], "    files: app.py")
            self.assertNotIn(proj, r.stdout)
            r = self._run("sessions", "--grep", "SED", cwd=proj)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("sed -i.bak", r.stdout)
            self.assertEqual(self._run("sessions", "--grep", "nothing-here", cwd=proj).returncode, 1)

    def test_bundle_from_one_project_imports_into_another_and_rewinds_there(self):
        with TemporaryDirectory() as src, TemporaryDirectory() as dst, TemporaryDirectory() as carry:
            Path(src, "app.py").write_text("x = 1\n")
            self.assertEqual(self._run("install", cwd=src).returncode, 0)
            cmd = json.loads(Path(src, ".claude", "settings.json").read_text())["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
            shell = "sed -i.bak s/1/2/ app.py && rm app.py.bak"
            for event in ("PreToolUse", "PostToolUse"):
                payload = {"session_id": "moved", "cwd": src, "hook_event_name": event, "tool_name": "Bash",
                           "tool_input": {"command": shell}, "tool_use_id": "toolu_1"}
                p = subprocess.run(cmd, shell=True, cwd=src, env=clean_env(), input=json.dumps(payload),
                                   capture_output=True, text=True, timeout=120)
                self.assertEqual((p.returncode, p.stderr), (0, ""))
                if event == "PreToolUse":
                    subprocess.run(["sh", "-c", shell], cwd=src, check=True)
            out = str(Path(carry, "moved.bundle"))
            r = self._run("bundle", "--out", out, cwd=src)
            self.assertEqual(r.returncode, 0, r.stderr)
            # app.py before the command and app.py as the command left it (the copy `revert` merges from)
            self.assertIn("session moved, 1 steps, 2 records, 2 stored files", r.stdout)
            r = self._run("import", out, cwd=dst)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("imported session moved: 1 steps, 2 records", r.stdout)
            self.assertIn("replay it with: rewindagents replay --session moved", r.stdout)
            r = self._run("verify", cwd=dst)
            self.assertEqual((r.returncode, r.stdout.strip()), (0, "OK: 2 records, chain intact"), r.stderr)
            r = self._run("replay", "--session", "moved", cwd=dst)
            self.assertIn("sed -i.bak", r.stdout)
            self.assertFalse(Path(dst, "app.py").exists())
            r = self._run("rewind", "0", "--session", "moved", cwd=dst)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(Path(dst, "app.py").read_text(), "x = 1\n")      # put back in the clone
            self.assertEqual(Path(src, "app.py").read_text(), "x = 2\n")      # the source is left alone
            self.assertEqual(self._run("import", out, cwd=dst).returncode, 1)  # the session is already here

    def test_gc_through_the_binary_frees_the_scan_copies_and_rewind_still_works(self):
        with TemporaryDirectory() as proj:
            Path(proj, "app.py").write_text("x = 1\n")
            Path(proj, "big.txt").write_text("b" * 1000)
            self.assertEqual(self._run("install", cwd=proj).returncode, 0)
            cmd = json.loads(Path(proj, ".claude", "settings.json").read_text())["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
            shell = "sed -i.bak s/1/2/ app.py && rm app.py.bak"
            for event in ("PreToolUse", "PostToolUse"):
                payload = {"session_id": "gc", "cwd": proj, "hook_event_name": event, "tool_name": "Bash",
                           "tool_input": {"command": shell}, "tool_use_id": "toolu_1"}
                p = subprocess.run(cmd, shell=True, cwd=proj, env=clean_env(), input=json.dumps(payload),
                                   capture_output=True, text=True, timeout=120)
                self.assertEqual((p.returncode, p.stderr), (0, ""))
                if event == "PreToolUse":
                    subprocess.run(["sh", "-c", shell], cwd=proj, check=True)
            # the scan saved app.py, big.txt and .claude/settings.json; only app.py changed, so the log names
            # app.py before the command and app.py as the command left it (the copy `revert` merges from)
            settings_size = Path(proj, ".claude", "settings.json").stat().st_size
            r = self._run("gc", "--dry-run", cwd=proj)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout, f"would delete 2 stored copies ({1000 + settings_size:,} bytes); "
                                       "kept 2 that the log or a pending scan names\n")
            r = self._run("gc", cwd=proj)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("deleted 2 stored copies", r.stdout)
            self.assertEqual(len(list(Path(proj, ".rewindagents", "objects").iterdir())), 2)
            r = self._run("rewind", "0", cwd=proj)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(Path(proj, "app.py").read_text(), "x = 1\n")
            r = self._run("verify", cwd=proj)
            self.assertEqual((r.returncode, r.stdout.strip()), (0, "OK: 3 records, chain intact"), r.stderr)

    def test_gc_through_the_binary_lists_and_drops_a_stale_pending_scan(self):
        with TemporaryDirectory() as proj:
            Path(proj, "app.py").write_text("x = 1\n")
            self.assertEqual(self._run("install", cwd=proj).returncode, 0)
            cmd = json.loads(Path(proj, ".claude", "settings.json").read_text())["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
            payload = {"session_id": "killed", "cwd": proj, "hook_event_name": "PreToolUse", "tool_name": "Bash",
                       "tool_input": {"command": "make build"}, "tool_use_id": "toolu_9"}
            p = subprocess.run(cmd, shell=True, cwd=proj, env=clean_env(), input=json.dumps(payload),
                               capture_output=True, text=True, timeout=120)
            self.assertEqual((p.returncode, p.stderr), (0, ""))   # no PostToolUse: the agent was killed
            (scan,) = Path(proj, ".rewindagents", "pending").glob("*.json")
            old = time.time() - 3 * 86400
            os.utime(scan, (old, old))
            r = self._run("gc", "--dry-run", cwd=proj)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("    3.0 days old  Bash: make build\n", r.stdout)
            self.assertEqual(self._run("gc", "--drop-pending-older-than", "0.5", cwd=proj).returncode, 1)
            r = self._run("gc", "--drop-pending-older-than", "2", cwd=proj)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("dropped 1 pending scan(s) older than 2 days:", r.stdout)
            self.assertFalse(scan.exists())
            self.assertEqual(list(Path(proj, ".rewindagents", "objects").iterdir()), [])
            r = self._run("verify", cwd=proj)
            self.assertEqual((r.returncode, r.stdout.strip()), (0, "OK: 1 records, chain intact"), r.stderr)

    def test_gc_through_the_binary_runs_after_a_torn_write_and_exits_1(self):
        with TemporaryDirectory() as proj:
            Path(proj, "app.py").write_text("x = 1\n")
            Path(proj, "big.txt").write_text("b" * 1000)
            self.assertEqual(self._run("install", cwd=proj).returncode, 0)
            cmd = json.loads(Path(proj, ".claude", "settings.json").read_text())["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
            shell = "sed -i.bak s/1/2/ app.py && rm app.py.bak"
            for event in ("PreToolUse", "PostToolUse"):
                payload = {"session_id": "torn", "cwd": proj, "hook_event_name": event, "tool_name": "Bash",
                           "tool_input": {"command": shell}, "tool_use_id": "toolu_1"}
                p = subprocess.run(cmd, shell=True, cwd=proj, env=clean_env(), input=json.dumps(payload),
                                   capture_output=True, text=True, timeout=120)
                self.assertEqual((p.returncode, p.stderr), (0, ""))
                if event == "PreToolUse":
                    subprocess.run(["sh", "-c", shell], cwd=proj, check=True)
            lp = Path(proj, ".rewindagents", "log.jsonl")
            last = lp.read_bytes().splitlines()[-1]
            with lp.open("ab") as fh:                              # a write cut off before its newline
                fh.write(last[: len(last) // 2])
            r = self._run("gc", cwd=proj)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("deleted 2 stored copies", r.stdout)
            self.assertIn("note: the log has a torn write (record 3: torn write at the end of the log", r.stdout)
            r = self._run("rewind", "0", cwd=proj)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertEqual(Path(proj, "app.py").read_text(), "x = 1\n")

    def test_import_through_the_binary_into_a_torn_log_exits_1_and_rewinds(self):
        with TemporaryDirectory() as src, TemporaryDirectory() as dst, TemporaryDirectory() as carry:
            for proj, session, name in ((src, "moved", "app.py"), (dst, "here", "own.py")):
                shell = f"sed -i.bak s/1/2/ {name} && rm {name}.bak"
                Path(proj, name).write_text("x = 1\n")
                self.assertEqual(self._run("install", cwd=proj).returncode, 0)
                cmd = json.loads(Path(proj, ".claude", "settings.json").read_text())["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
                for event in ("PreToolUse", "PostToolUse"):
                    payload = {"session_id": session, "cwd": proj, "hook_event_name": event, "tool_name": "Bash",
                               "tool_input": {"command": shell}, "tool_use_id": "toolu_1"}
                    p = subprocess.run(cmd, shell=True, cwd=proj, env=clean_env(), input=json.dumps(payload),
                                       capture_output=True, text=True, timeout=120)
                    self.assertEqual((p.returncode, p.stderr), (0, ""))
                    if event == "PreToolUse":
                        subprocess.run(["sh", "-c", shell], cwd=proj, check=True)
            out = str(Path(carry, "moved.bundle"))
            self.assertEqual(self._run("bundle", "--out", out, cwd=src).returncode, 0)
            lp = Path(dst, ".rewindagents", "log.jsonl")
            last = lp.read_bytes().splitlines()[-1]
            with lp.open("ab") as fh:                              # a write cut off before its newline
                fh.write(last[: len(last) // 2])
            before = lp.read_bytes()
            r = self._run("import", out, cwd=dst)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("imported session moved: 1 steps, 2 records", r.stdout)
            self.assertIn("note: this log has a torn write (record 3: not a valid record", r.stdout)
            self.assertTrue(lp.read_bytes().startswith(before))
            r = self._run("verify", cwd=dst)
            self.assertEqual(r.returncode, 1)
            self.assertIn("the 2 records after it chain on intact", r.stdout + r.stderr)
            self.assertFalse(Path(dst, "app.py").exists())
            r = self._run("rewind", "0", "--session", "moved", cwd=dst)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("torn write", r.stdout + r.stderr)
            self.assertEqual(Path(dst, "app.py").read_text(), "x = 1\n")       # put back in this clone
            self.assertEqual(Path(dst, "own.py").read_text(), "x = 2\n")       # its own session left alone

    def test_install_for_codex_and_cursor_writes_commands_their_payloads_drive(self):
        """`install --agent codex|cursor` through the binary; then the command from the written file, run as the
        agent would run it (no PYTHONPATH, the documented payload on stdin), records a shell edit that the binary
        rewinds. Codex: stdout empty. Cursor: the required `{"permission": "allow"}` / `{}` answers."""
        shell = "sed -i.bak s/1/2/ app.py && rm app.py.bak"
        cases = {
            "cursor": (".cursor/hooks.json", '{"permission": "allow"}\n', "{}\n",
                       lambda proj, ev: {"conversation_id": "c9", "generation_id": "g1", "hook_event_name": ev,
                                         "workspace_roots": [proj], "cwd": proj, "tool_name": "Shell", "tool_use_id": "abc123",
                                         "tool_input": {"command": shell, "working_directory": proj}},
                       {"tool_output": json.dumps({"output": "", "exit_code": 0}), "duration": 3}),
            "codex": (".codex/hooks.json", "", "",
                      lambda proj, ev: {"session_id": "c9", "cwd": proj, "hook_event_name": ev, "tool_name": "Bash",
                                        "tool_use_id": "call_9", "tool_input": {"command": shell}},
                      {"tool_response": {"output": ""}}),
        }
        for agent, (path, pre_reply, post_reply, payload, post_extra) in cases.items():
            with TemporaryDirectory() as proj:
                Path(proj, "app.py").write_text("x = 1\n")
                r = self._run("install", "--agent", agent, cwd=proj)
                self.assertEqual((r.returncode, r.stdout.strip()), (0, "installed in %s" % path), r.stderr)
                settings = json.loads(Path(proj, path).read_text())
                pre_event, post_event = agents.AGENTS[agent].events
                if agent == "cursor":
                    self.assertEqual(settings["version"], 1)
                    cmds = {ev: [h["command"] for h in settings["hooks"][ev]] for ev in (pre_event, post_event)}
                else:
                    cmds = {ev: [h["command"] for g in settings["hooks"][ev] for h in g["hooks"]] for ev in (pre_event, post_event)}
                self.assertEqual(cmds[pre_event], cmds[post_event])
                self.assertEqual(len(cmds[pre_event]), 1)
                cmd = cmds[pre_event][0]
                self.assertNotIn("PYTHONPATH", cmd)
                words = shlex.split(cmd)
                self.assertEqual(words[1:], ["-m", "rewindagents", "hook", "--agent", agent], cmd)
                self.assertTrue(Path(words[0]).is_absolute(), cmd)

                def hook_call(ev, extra, want):
                    p = subprocess.run(cmd, shell=True, cwd=proj, env=clean_env(), input=json.dumps({**payload(proj, ev), **extra}),
                                       capture_output=True, text=True, timeout=120)
                    self.assertEqual((p.returncode, p.stdout, p.stderr), (0, want, ""), agent)

                hook_call(pre_event, {}, pre_reply)
                subprocess.run(["sh", "-c", shell], cwd=proj, check=True)
                hook_call(post_event, post_extra, post_reply)
                self.assertEqual(Path(proj, "app.py").read_text(), "x = 2\n")
                r = self._run("replay", cwd=proj)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIn("sed -i.bak", r.stdout)
                self.assertIn("[1 checkpointed]", r.stdout)
                r = self._run("rewind", "0", cwd=proj)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(Path(proj, "app.py").read_text(), "x = 1\n")
                self.assertIn("undo it with: rewindagents rewind 1 --session c9", r.stdout)
                self.assertNotIn("not scanned", r.stdout)
                r = self._run("verify", cwd=proj)
                self.assertEqual((r.returncode, r.stdout.strip()), (0, "OK: 3 records, chain intact"), r.stderr)

    def test_uninstall_removes_what_install_wrote_for_every_agent(self):
        """Install then uninstall through the binary for all three agents, next to a hook of the user's own:
        the user's entry survives exactly, ours is gone, a second uninstall leaves the file byte-identical,
        and .rewindagents/ is untouched."""
        for agent in sorted(agents.AGENTS):
            ag = agents.AGENTS[agent]
            with self.subTest(agent=agent), TemporaryDirectory() as proj:
                f = Path(proj, ag.settings)
                f.parent.mkdir(parents=True)
                if ag.shape == "cursor":
                    mine = {"version": 1, "hooks": {ag.events[0]: [{"command": "my-own-hook"}]}}
                else:
                    mine = {"hooks": {ag.events[0]: [{"matcher": "Bash", "hooks": [
                        {"type": "command", "command": "my-own-hook"}]}]}}
                f.write_text(json.dumps(mine))
                Path(proj, ".rewindagents").mkdir()
                Path(proj, ".rewindagents", "log.jsonl").write_text("kept\n")
                r = self._run("install", "--agent", agent, cwd=proj)
                self.assertEqual((r.returncode, r.stdout.strip()), (0, "installed in %s" % ag.settings), r.stderr)
                self.assertNotEqual(json.loads(f.read_text()), mine)
                r = self._run("uninstall", "--agent", agent, cwd=proj)
                self.assertEqual((r.returncode, r.stdout.strip()), (0, "removed from %s" % ag.settings), r.stderr)
                self.assertEqual(json.loads(f.read_text()), mine)
                raw = f.read_bytes()
                r = self._run("uninstall", "--agent", agent, cwd=proj)
                self.assertEqual((r.returncode, r.stdout.strip()),
                                 (0, "not installed in %s; left unchanged" % ag.settings), r.stderr)
                self.assertEqual(f.read_bytes(), raw)
                self.assertEqual(Path(proj, ".rewindagents", "log.jsonl").read_text(), "kept\n")


    def test_status_flags_a_hook_whose_interpreter_was_deleted_and_install_replaces_it(self):
        """A config naming a deleted venv's python: status exits 1 STALE, install swaps in the binary's own
        hook (the user's hook stays), status exits 0."""
        with TemporaryDirectory() as proj:
            gone = Path(proj, "deleted-venv", "bin", "python")
            f = Path(proj, ".claude", "settings.json")
            f.parent.mkdir()
            f.write_text(json.dumps({"hooks": {e: [{"matcher": "*", "hooks": [
                {"type": "command", "command": "my-own-hook"},
                {"type": "command", "command": f"{gone} -m rewindagents hook"}]}]
                for e in ("PreToolUse", "PostToolUse")}}))
            r = self._run("status", cwd=proj)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertRegex(r.stdout, r"claude\s+STALE\s+\.claude/settings\.json")
            self.assertIn("Fix: rewindagents init --yes", r.stdout)
            r = self._run("install", cwd=proj)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("replaced a stale rewindagents hook", r.stdout)
            cmds = {h["command"] for ev in ("PreToolUse", "PostToolUse")
                    for g in json.loads(f.read_text())["hooks"][ev] for h in g["hooks"]}
            self.assertEqual(len(cmds), 2, cmds)
            self.assertIn("my-own-hook", cmds)
            self.assertNotIn(f"{gone} -m rewindagents hook", cmds)
            r = self._run("status", cwd=proj)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertRegex(r.stdout, r"claude\s+ok\s+")

    def test_status_reports_the_log_nothing_then_records_then_a_broken_chain(self):
        """Hook in place with no record: status says so (exit 0). After one real hook call: the record count
        and 'chain intact'. After a record is edited: BROKEN and exit 1. status writes nothing."""
        with TemporaryDirectory() as proj:
            self.assertEqual(self._run("install", cwd=proj).returncode, 0)
            r = self._run("status", cwd=proj)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertRegex(r.stdout, r"log\s+none\s+\.rewindagents/log\.jsonl  \(nothing recorded yet\)")
            self.assertIn("A hook is in place but nothing is recorded yet", r.stdout)
            self.assertFalse(Path(proj, ".rewindagents").exists())
            cmd = json.loads(Path(proj, ".claude", "settings.json").read_text())["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
            for event in ("PreToolUse", "PostToolUse"):
                payload = {"session_id": "st", "cwd": proj, "hook_event_name": event, "tool_name": "Bash",
                           "tool_input": {"command": "true"}, "tool_use_id": "toolu_1"}
                p = subprocess.run(cmd, shell=True, cwd=proj, env=clean_env(), input=json.dumps(payload),
                                   capture_output=True, text=True, timeout=120)
                self.assertEqual(p.returncode, 0, p.stderr)
            lp = Path(proj, ".rewindagents", "log.jsonl")
            n = len([l for l in lp.read_text().splitlines() if l.strip()])
            self.assertGreater(n, 0)
            before = lp.read_bytes()
            r = self._run("status", cwd=proj)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertRegex(r.stdout, rf"log\s+ok\s+\.rewindagents/log\.jsonl  \({n} records?, last "
                                       r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d, chain intact\)")
            self.assertNotIn("nothing is recorded yet", r.stdout)
            self.assertEqual(lp.read_bytes(), before)
            lp.write_text(before.decode().replace('"session": "st"', '"session": "xx"', 1))
            r = self._run("status", cwd=proj)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertRegex(r.stdout, r"log\s+BROKEN\s+\.rewindagents/log\.jsonl  \(record 1: contents altered\)")
            self.assertIn("Details: rewindagents verify", r.stdout)


class ReadmeCommandsTest(unittest.TestCase):
    def test_every_rewindagents_command_in_the_readme_is_a_real_subcommand(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        blocks = re.findall(r"```sh\n(.*?)```", readme, re.S)
        self.assertTrue(blocks)
        seen = set()
        for line in "\n".join(blocks).splitlines():
            line = line.strip().lstrip("$ ")
            m = re.match(r"(?:python3 -m )?rewindagents (\S+)", line.split("|")[-1].strip())
            if m and not m.group(1).startswith("-"):
                self.assertIn(m.group(1), SUBCOMMANDS, line)
                seen.add(m.group(1))
        self.assertTrue({"install", "uninstall", "replay", "rewind", "branch", "verify", "export", "sessions", "bundle",
                         "import", "gc"} <= seen, seen)

    def test_readme_says_the_package_is_on_pypi(self):
        # v0.0.8 is on PyPI (2026-11-18, release workflow publish.yml); the README installs from there
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("no pip package yet", readme.lower())
        self.assertNotIn("not on pypi yet", readme.lower())
        self.assertIn("pipx install rewindagents", readme)
        self.assertNotIn("pipx install git+", readme)
        self.assertIn(f"v{VERSION},", readme)


if __name__ == "__main__":
    unittest.main()
