"""The hook command on Windows (R42), driven on any OS.

`install` writes one command string into the agent's config, and on Windows that string is run by Git Bash
(Claude Code), PowerShell (Cursor, Copilot's `powershell` key) or a shell the agent's docs do not name (Codex,
Gemini CLI, Droid, Qwen Code; agents.py quotes each page). The POSIX form, `PYTHONPATH=... '<python>' -m
rewindagents hook`, is shell syntax none of those share: the env-var prefix is bash-only, single quotes are not
PowerShell quoting, and a double-quoted path on its own is a string in PowerShell, not a command.

Here the form is chosen from the interpreter path's own shape (C:/... or C:\\...), never from the OS running
the test, so every Windows string below is produced and checked on this machine. What cannot be driven here:
running the string under Git Bash, PowerShell or cmd.exe on Windows. Git Bash runs it on windows-latest CI
(test_agents_more.py); PowerShell and cmd.exe do not, and the README says so."""
import json
import os
import shlex
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from rewindagents import agents, hook, log as hlog  # noqa: E402

PY = r"C:\Users\dev\AppData\Local\Programs\Python\Python312\python.exe"
PY_FWD = "C:/Users/dev/AppData/Local/Programs/Python/Python312/python.exe"
VENV = r"C:\Users\dev\proj\.venv\Scripts\python.exe"
SPACED = r"C:\Program Files\Python312\python.exe"
SPACED_FWD = "C:/Program Files/Python312/python.exe"
MAIN = SRC / "rewindagents" / "__main__.py"
# A stand-in for "the interpreter is a POSIX path", driven the same way the Windows paths above are: by the
# path's own shape, not by which OS runs the test. `sys.executable` is NOT this on windows-latest CI (R42
# found it there: the real interpreter path IS a Windows one, so hook.hook_command() takes the Windows branch
# for it too), so a test that wants "the POSIX form is unchanged" must say so with a POSIX path of its own.
POSIX_PY = "/usr/bin/python3"


def agent_tail(name):
    return "" if name == agents.DEFAULT else f" --agent {name}"


class TestWindowsForm(unittest.TestCase):
    """What `install` writes when the interpreter is a Windows path."""

    def test_a_plain_path_is_written_bare_with_forward_slashes_and_no_env_prefix(self):
        # Bare and forward-slashed, so the same string runs in Git Bash, PowerShell and cmd.exe alike.
        with patch.object(hook, "installed", return_value=True):
            for name in agents.AGENTS:
                with self.subTest(agent=name):
                    cmd = hook.hook_command(name, python=PY)
                    self.assertTrue(cmd.startswith(f"{PY_FWD} -m rewindagents hook{agent_tail(name)}"), cmd)
                    for bad in ("PYTHONPATH", "'", "\\", "|| true"):
                        self.assertNotIn(bad, cmd, (name, cmd))
                    self.assertTrue(hook.ours(cmd), cmd)
                    self.assertTrue(agents.windows_command(cmd), cmd)
            self.assertEqual(hook.hook_command("claude", python=PY), f"{PY_FWD} -m rewindagents hook")
            self.assertEqual(hook.hook_command("cursor", python=VENV),
                             "C:/Users/dev/proj/.venv/Scripts/python.exe -m rewindagents hook --agent cursor")

    def test_copilots_fail_closed_guard_is_powershell_not_bash(self):
        # Copilot's Windows key is `powershell`; `|| true` is bash (and `true` is not a PowerShell command).
        # Driven by the interpreter path's own shape (module docstring), not by the OS running this test: on
        # windows-latest CI the real `sys.executable` IS a Windows path, so a POSIX stand-in proves the POSIX
        # form separately from proving the Windows one above (R94, CI run 44161605918).
        with patch.object(hook, "installed", return_value=True):
            self.assertEqual(hook.hook_command("copilot", python=PY),
                             f"{PY_FWD} -m rewindagents hook --agent copilot; exit 0")
            self.assertEqual(hook.hook_command("copilot", python=POSIX_PY),
                             f"{shlex.quote(POSIX_PY)} -m rewindagents hook --agent copilot || true")

    def test_a_path_with_a_space_is_quoted_for_the_agents_documented_windows_shell(self):
        with patch.object(hook, "installed", return_value=True):
            got = {name: hook.hook_command(name, python=SPACED) for name in agents.AGENTS}
        # Git Bash (Claude Code's documented default) and cmd.exe run a double-quoted path as a command.
        self.assertEqual(got["claude"], f'"{SPACED_FWD}" -m rewindagents hook')
        # PowerShell prints a quoted string unless `&` precedes it (Claude Code's own page says so; Cursor and
        # Copilot's `powershell` key run PowerShell).
        self.assertEqual(got["cursor"], f'& "{SPACED_FWD}" -m rewindagents hook --agent cursor')
        self.assertEqual(got["copilot"], f'& "{SPACED_FWD}" -m rewindagents hook --agent copilot; exit 0')
        for name in ("codex", "gemini", "droid", "qwen"):        # shell not documented: the plain quoted form
            self.assertEqual(got[name], f'"{SPACED_FWD}" -m rewindagents hook --agent {name}', name)
        for name, cmd in got.items():
            self.assertEqual(cmd.startswith("& "), agents.AGENTS[name].win_shell == "powershell", (name, cmd))
            self.assertNotIn("'", cmd)
            self.assertTrue(hook.ours(cmd), cmd)
        self.assertEqual({n for n, a in agents.AGENTS.items() if a.win_shell == "powershell"}, {"cursor", "copilot"})
        self.assertEqual({n for n, a in agents.AGENTS.items() if a.win_shell == "bash"}, {"claude"})

    def test_from_a_clone_the_package_runs_by_file_path_instead_of_a_pythonpath_prefix(self):
        with patch.object(hook, "installed", return_value=False), \
                patch.object(hook, "source_dir", return_value=Path(r"C:\clone\src")):
            self.assertEqual(hook.hook_command("codex", python=PY),
                             f"{PY_FWD} C:/clone/src/rewindagents/__main__.py hook --agent codex")
            self.assertEqual(hook.hook_command("cursor", python=SPACED),       # a plain file path stays bare
                             f'& "{SPACED_FWD}" C:/clone/src/rewindagents/__main__.py hook --agent cursor')
        with patch.object(hook, "installed", return_value=False), \
                patch.object(hook, "source_dir", return_value=Path(r"C:\my clone\src")):
            self.assertEqual(hook.hook_command("claude", python=PY),
                             f'{PY_FWD} "C:/my clone/src/rewindagents/__main__.py" hook')
        # The POSIX clone form is unchanged. A POSIX stand-in, not the real `sys.executable`: on windows-latest
        # CI that is a Windows path, and this block means to prove the *other* branch (R94).
        with patch.object(hook, "installed", return_value=False):
            self.assertEqual(hook.hook_command("codex", python=POSIX_PY),
                             f"PYTHONPATH={shlex.quote(str(SRC))} {shlex.quote(POSIX_PY)} -m rewindagents hook --agent codex")

    def test_the_posix_form_is_unchanged_for_every_agent(self):
        # A POSIX stand-in, not the real `sys.executable`: the form is chosen from the interpreter path's own
        # shape (module docstring), and on windows-latest CI the real interpreter IS a Windows path, so asking
        # for "the POSIX form" must say so explicitly rather than ride on whatever OS happens to run this (R94,
        # CI run 44161605918: this test failed there comparing a Windows hook_command() output to a POSIX one).
        py = shlex.quote(POSIX_PY)
        with patch.object(hook, "installed", return_value=True):
            for name, ag in agents.AGENTS.items():
                self.assertEqual(hook.hook_command(name, python=POSIX_PY),
                                 f"{py} -m rewindagents hook{agent_tail(name)}" + (" || true" if ag.fail_closed else ""))
                self.assertFalse(agents.windows_command(hook.hook_command(name, python=POSIX_PY)))

    def test_windows_command_is_told_by_the_paths_own_shape(self):
        for cmd in (PY, f"{PY_FWD} -m rewindagents hook", f'& "{SPACED_FWD}" -m x', f'"{SPACED}" -m x',
                    r"\\server\share\py\python.exe -m x"):
            self.assertTrue(agents.windows_command(cmd), cmd)
        for cmd in ("/usr/bin/python3 -m rewindagents hook", "rewindagents hook", "uvx rewindagents hook",
                    "python3 -c print(1)", "PYTHONPATH=/src /usr/bin/python3 -m rewindagents hook"):
            self.assertFalse(agents.windows_command(cmd), cmd)


class TestMainByFilePath(unittest.TestCase):
    """`<python> <clone>/src/rewindagents/__main__.py hook` must work the same as `-m rewindagents hook`:
    it is what the Windows clone form runs. Proved here with this machine's Python and a real hook event."""

    def run_main(self, argv, cwd, stdin_text=""):
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        return subprocess.run([sys.executable, str(MAIN), *argv], input=stdin_text, capture_output=True,
                              text=True, cwd=cwd, env=env, timeout=60)

    def test_hook_records_and_the_cli_answers_when_run_as_a_file(self):
        with TemporaryDirectory() as d:
            Path(d, "a.txt").write_text("one\n", encoding="utf-8")
            pre = {"session_id": "s1", "cwd": d, "hook_event_name": "PreToolUse", "tool_name": "Write",
                   "tool_input": {"file_path": str(Path(d, "a.txt")), "content": "two\n"}, "tool_use_id": "t1"}
            p = self.run_main(["hook"], d, json.dumps(pre))
            self.assertEqual((p.returncode, p.stdout), (0, ""), p.stderr)
            self.assertNotIn("Traceback", p.stderr)
            ok, n, _ = hlog.verify(Path(d, ".rewindagents", "log.jsonl"))
            self.assertEqual((ok, n), (True, 1))
            p = self.run_main(["--version"], d)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertTrue(p.stdout.startswith("rewindagents "), p.stdout)
            p = self.run_main(["sessions"], d)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("s1", p.stdout)

    def test_the_file_path_form_is_ours_and_not_stale_while_the_file_exists(self):
        cmd = f"{shlex.quote(sys.executable)} {shlex.quote(str(MAIN))} hook --agent codex"
        self.assertTrue(hook.ours(cmd))
        self.assertIsNone(hook.stale(cmd))
        gone = f"{shlex.quote(sys.executable)} /gone/clone/src/rewindagents/__main__.py hook"
        self.assertTrue(hook.ours(gone))
        self.assertEqual(hook.stale(gone), "/gone/clone/src/rewindagents/__main__.py no longer exists")


class TestStaleOnWindowsCommands(unittest.TestCase):
    """hook.stale used shlex.split in POSIX mode, which reads C:\\Users\\dev as C:Usersdev."""

    def test_backslashes_survive_and_a_missing_windows_interpreter_is_named_as_written(self):
        gone = r"C:\Users\dev\gone\python.exe"
        self.assertEqual(hook.stale(f"{gone} -m rewindagents hook"), f"{gone} no longer exists")
        self.assertNotIn("C:Usersdevgone", hook.stale(f"{gone} -m rewindagents hook"))
        self.assertEqual(hook.stale(f"{PY_FWD} -m rewindagents hook --agent cursor"), f"{PY_FWD} no longer exists")
        self.assertEqual(hook.stale(f'& "{SPACED_FWD}" -m rewindagents hook --agent cursor'),
                         f"{SPACED_FWD} no longer exists")
        self.assertEqual(hook.stale(f'& "{SPACED_FWD}" -m rewindagents hook --agent copilot; exit 0'),
                         f"{SPACED_FWD} no longer exists")
        self.assertEqual(hook.stale(f'{PY_FWD} "C:/my clone/src/rewindagents/__main__.py" hook'),
                         f"{PY_FWD} no longer exists")   # the interpreter is judged first

    def test_words_strip_quotes_and_the_powershell_call_operator(self):
        self.assertEqual(hook.words(f'& "{SPACED_FWD}" "C:/my clone/src/rewindagents/__main__.py" hook --agent cursor'),
                         [SPACED_FWD, "C:/my clone/src/rewindagents/__main__.py", "hook", "--agent", "cursor"])
        self.assertEqual(hook.words(f"{VENV} -m rewindagents hook"), [VENV, "-m", "rewindagents", "hook"])
        self.assertEqual(hook.words("PYTHONPATH=/s '/my venv/bin/python' -m rewindagents hook"),
                         ["PYTHONPATH=/s", "/my venv/bin/python", "-m", "rewindagents", "hook"])
        self.assertIsNone(hook.stale('"unbalanced C:/x'))

    def test_ours_knows_every_form_and_nothing_else(self):
        for cmd in ("/usr/bin/python3 -m rewindagents hook", "rewindagents hook", "uvx rewindagents hook",
                    f"{PY_FWD} -m rewindagents hook --agent cursor",
                    f"{PY_FWD} C:/clone/src/rewindagents/__main__.py hook",
                    f'& "{SPACED_FWD}" "C:/my clone/src/rewindagents/__main__.py" hook --agent cursor',
                    r"C:\py\python.exe C:\clone\src\rewindagents\__main__.py hook"):
            self.assertTrue(hook.ours(cmd), cmd)
        for cmd in ("my-linter", "/usr/bin/python3 -m rewindagents verify", "rewindagents-hook x",
                    "echo rewindagents hooked"):
            self.assertFalse(hook.ours(cmd), cmd)


class TestCopilotWindowsKey(unittest.TestCase):
    """Copilot CLI: `bash` is "Shell command for Unix." and `powershell` "Shell command for Windows."; an entry
    with only `bash` never runs on Windows. A Windows command goes under `powershell`; a POSIX one under `bash`."""

    def setUp(self):
        self.ag = agents.AGENTS["copilot"]
        self.win = f"{PY_FWD} -m rewindagents hook --agent copilot; exit 0"
        self.posix = "/usr/bin/python3 -m rewindagents hook --agent copilot || true"

    def test_install_writes_the_powershell_key_reads_it_back_and_uninstall_removes_only_it(self):
        with TemporaryDirectory() as d:
            f = Path(d, ".github", "hooks", "rewindagents.json")
            f.parent.mkdir(parents=True)
            mine = {"version": 1, "hooks": {"PreToolUse": [{"type": "command", "bash": "other"}]}}
            f.write_text(json.dumps(mine), encoding="utf-8")
            self.assertTrue(hook.install(f, command=self.win, agent="copilot"))
            got = json.loads(f.read_text(encoding="utf-8"))
            entry = {"type": "command", "powershell": self.win}
            self.assertEqual(got["hooks"]["PreToolUse"], [{"type": "command", "bash": "other"}, entry])
            for event in ("PostToolUse", "PostToolUseFailure"):
                self.assertEqual(got["hooks"][event], [entry])
            self.assertNotIn('"bash": "' + self.win[:10], f.read_text(encoding="utf-8"))
            self.assertFalse(hook.install(f, command=self.win, agent="copilot"), "already there")
            cmds = agents.commands_in(self.ag, f)
            self.assertEqual(cmds["PreToolUse"], ["other", self.win])
            self.assertEqual(cmds["PostToolUse"], [self.win])
            # A POSIX command still goes under `bash`, beside the Windows one.
            self.assertTrue(hook.install(f, command=self.posix, agent="copilot"))
            got = json.loads(f.read_text(encoding="utf-8"))
            self.assertEqual(got["hooks"]["PostToolUse"], [entry, {"type": "command", "bash": self.posix}])
            self.assertEqual(agents.commands_in(self.ag, f)["PostToolUse"], [self.win, self.posix])
            self.assertTrue(hook.uninstall(f, command=self.win, agent="copilot"))
            got = json.loads(f.read_text(encoding="utf-8"))
            self.assertEqual(got["hooks"]["PreToolUse"],
                             [{"type": "command", "bash": "other"}, {"type": "command", "bash": self.posix}])
            self.assertEqual(got["hooks"]["PostToolUse"], [{"type": "command", "bash": self.posix}])
            self.assertTrue(hook.uninstall(f, command=self.posix, agent="copilot"))
            self.assertEqual(json.loads(f.read_text(encoding="utf-8")), mine)

    def test_a_stale_powershell_entry_is_found_and_replaced(self):
        with TemporaryDirectory() as d:
            f = Path(d, "rewindagents.json")
            f.write_text(json.dumps({"version": 1, "hooks": {
                e: [{"type": "command", "powershell": self.win}] for e in ("PreToolUse", "PostToolUse", "PostToolUseFailure")}}),
                encoding="utf-8")
            self.assertEqual(hook.stale_hooks(f, "copilot"), [(self.win, f"{PY_FWD} no longer exists")])
            self.assertEqual(hook.replace_stale(f, "copilot"), [(self.win, f"{PY_FWD} no longer exists")])
            self.assertEqual(json.loads(f.read_text(encoding="utf-8")), {"version": 1})

    def test_a_stale_windows_command_under_the_bash_key_is_removed_too(self):
        # windows-latest CI: init --yes reported "replaced" for a stale Windows-path copilot hook stored under
        # `bash` (as written before the `powershell` key existed, or by hand), but uninstall looked only under
        # `powershell`, so the dead entry stayed beside the new one.
        dead = r"C:\Users\dev\gone-venv\Scripts\python.exe -m rewindagents hook --agent copilot || true"
        with TemporaryDirectory() as d:
            f = Path(d, "rewindagents.json")
            mine = {"type": "command", "bash": "my-own-hook"}
            f.write_text(json.dumps({"version": 1, "hooks": {
                e: [mine, {"type": "command", "bash": dead}] for e in ("PreToolUse", "PostToolUse", "PostToolUseFailure")}}),
                encoding="utf-8")
            self.assertEqual([c for c, _ in hook.replace_stale(f, "copilot")], [dead])
            self.assertEqual(hook.stale_hooks(f, "copilot"), [])
            self.assertEqual(agents.commands_in(self.ag, f)["PreToolUse"], ["my-own-hook"])

    def test_every_other_agent_has_one_key(self):
        self.assertEqual([n for n, a in agents.AGENTS.items() if a.win_command_key], ["copilot"])
        self.assertEqual(self.ag.win_command_key, "powershell")


class TestDocs(unittest.TestCase):
    def test_agents_py_quotes_each_vendors_windows_shell_with_the_read_date(self):
        doc = " ".join(agents.__doc__.split())      # the docstring wraps at 110 columns; quotes may span a line
        self.assertEqual(agents.DOCS_READ_3, "2026-11-14")
        self.assertIn(agents.DOCS_READ_3, doc)
        for quote in ("Git Bash on Windows, or PowerShell when Git Bash isn't installed",   # Claude Code
                      "runs hook commands through PowerShell",                               # Cursor
                      "Shell command for Windows.",                                           # Copilot `powershell`
                      "`commandWindows` is an optional Windows-only command override",        # Codex
                      "Shell to use"):                                                        # Qwen `shell`
            self.assertIn(quote, doc, quote)
        self.assertIn("Gemini CLI", doc.split(agents.DOCS_READ_3, 1)[1])
        self.assertIn("Droid", doc.split(agents.DOCS_READ_3, 1)[1])

    def test_readme_states_the_windows_ci_result_and_what_it_does_not_cover(self):
        # The README may not call Windows supported, or unsupported, without the evidence: the windows-latest
        # result, that the live hook sessions were macOS only, that PowerShell is untested, and the CRLF gap.
        raw = (SRC.parent / "README.md").read_text(encoding="utf-8")
        text = " ".join(raw.split())
        self.assertNotIn("Windows is not supported", text)
        self.assertNotIn("Needs a Unix", text)
        self.assertIn("`src/rewindagents/__main__.py` by path", text)
        status = text.split("**Status: v", 1)[1].split("## Install", 1)[0]
        for fact in ("windows-latest", "`Ran 868 tests ... OK (skipped=38)`", "[docs/windows.md](docs/windows.md)",
                     "The live hook sessions ran on macOS only, not yet on Windows",
                     "tested under Git Bash, not under PowerShell"):
            self.assertIn(fact, status, fact)
        recorder = text.split("## Recorder", 1)[1].split("## Use it", 1)[0]
        for fact in ("the full test suite passes on windows-latest CI", "`Ran 868 tests ... OK (skipped=38)`",
                     "verified in live sessions on macOS, not yet on Windows", "under PowerShell",
                     "are not tested", "gets CRLF line endings and will not `git apply`"):
            self.assertIn(fact, recorder, fact)
        for word in ("Windows is supported", "supports Windows", "Windows support"):
            self.assertNotIn(word, text, word)

    def test_the_site_states_the_same_windows_facts(self):
        site = (SRC.parent / "brand" / "site" / "build.py").read_text(encoding="utf-8")
        self.assertNotIn("Needs a Unix", site)
        self.assertNotIn("tests have not run on Windows", site)
        limit = site.split("<li>Windows: ", 1)[1].split("</li>", 1)[0]
        for fact in ("the full test suite passes on Windows CI (windows-latest)",
                     "verified in live sessions on macOS only, not yet on Windows",
                     "hook commands under PowerShell are untested", "will not <code>git apply</code>"):
            self.assertIn(fact, limit, fact)

    def test_no_user_facing_text_says_windows_is_unsupported(self):
        root = SRC.parent
        files = [root / "README.md", root / "CONTRIBUTING.md", root / "brand" / "site" / "build.py",
                 *sorted((SRC / "rewindagents").glob("*.py"))]
        for f in files:
            text = " ".join(f.read_text(encoding="utf-8").split())
            for old in ("Windows is not supported", "Needs a Unix", "Not on Windows yet"):
                self.assertNotIn(old, text, "%s: %s" % (f.name, old))

    def test_windows_is_a_normal_ci_row(self):
        wf = (SRC.parent / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
        self.assertIn("- os: windows-latest", wf)
        self.assertNotIn("continue-on-error", wf)
        self.assertNotIn("experimental", wf)
        self.assertIn("permissions:\n  contents: read", wf)
        for line in wf.splitlines():
            if "uses:" in line:
                ref = line.split("@", 1)[1].split()[0]
                self.assertRegex(ref, r"^[0-9a-f]{40}$", line)


if __name__ == "__main__":
    unittest.main()
