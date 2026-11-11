"""Runs the console script that `pip install .` put in .venv, not the source tree.

.fire-test-cmd builds .venv, installs the package into it and sets REWINDAGENT_BIN, so in the launch gate's
fresh clone these tests always run. Without REWINDAGENT_BIN they are skipped (a plain `unittest discover`).
The README check at the bottom runs either way.
"""
import json
import os
import re
import shlex
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SRC = ROOT / "src"
BIN = os.environ.get("REWINDAGENT_BIN")
VERSION = re.search(r'^__version__ = "([^"]+)"', (SRC / "rewindagent" / "__init__.py").read_text(), re.M).group(1)
SUBCOMMANDS = set(re.findall(r'sub\.add_parser\("(\w+)"', (SRC / "rewindagent" / "cli.py").read_text()))


def clean_env():
    return {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}


@unittest.skipUnless(BIN, "REWINDAGENT_BIN not set; .fire-test-cmd sets it after pip install")
class InstalledCommandTest(unittest.TestCase):
    def _run(self, *argv, cwd, stdin=None):
        return subprocess.run([BIN, *argv], cwd=cwd, env=clean_env(), input=stdin,
                              capture_output=True, text=True, timeout=120)

    def test_binary_exists_and_reports_the_source_version(self):
        self.assertTrue(Path(BIN).is_file(), BIN)
        with TemporaryDirectory() as d:
            r = self._run("--version", cwd=d)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, f"rewindagent {VERSION}"), r.stderr)

    def test_package_is_imported_from_the_install_not_src(self):
        py = Path(BIN).parent / "python"
        with TemporaryDirectory() as d:
            r = subprocess.run([str(py), "-I", "-c", "import rewindagent; print(rewindagent.__file__)"],
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
        self.assertEqual(words[1:], ["-m", "rewindagent", "hook"], cmd)
        self.assertTrue(Path(words[0]).is_absolute(), cmd)
        # The named interpreter must import the package on its own, with nothing inherited from this process.
        with TemporaryDirectory() as d:
            r = subprocess.run([words[0], "-I", "-c", "import rewindagent; print(rewindagent.__file__)"],
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
            self.assertIn("undo it with: rewindagent rewind 1 --session inst", r.stdout)
            r = self._run("verify", cwd=proj)
            self.assertEqual((r.returncode, r.stdout.strip()), (0, "OK: 3 records, chain intact"), r.stderr)


class ReadmeCommandsTest(unittest.TestCase):
    def test_every_rewindagent_command_in_the_readme_is_a_real_subcommand(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        blocks = re.findall(r"```sh\n(.*?)```", readme, re.S)
        self.assertTrue(blocks)
        seen = set()
        for line in "\n".join(blocks).splitlines():
            line = line.strip().lstrip("$ ")
            m = re.match(r"(?:python3 -m )?rewindagent (\S+)", line.split("|")[-1].strip())
            if m and not m.group(1).startswith("-"):
                self.assertIn(m.group(1), SUBCOMMANDS, line)
                seen.add(m.group(1))
        self.assertTrue({"install", "replay", "rewind", "branch", "verify"} <= seen, seen)

    def test_readme_says_the_package_exists_and_is_not_on_pypi(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("no pip package yet", readme.lower())
        self.assertIn("not on pypi yet", readme.lower())
        self.assertIn(f"v{VERSION},", readme)


if __name__ == "__main__":
    unittest.main()
