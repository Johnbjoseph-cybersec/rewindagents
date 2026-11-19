"""Next-step hints from an editable install (`pip install -e .`) name the `rewindagents` command.

Before: hook.installed() is False for an editable install (the package files stay in the clone, not in
site-packages), so every hint (`summary`'s "Take it back", `revert`'s "undo it with", `status`'s "Fix") said
`python3 -m rewindagents ...`. Run from a venv that is not activated, that copy-pasted undo command fails with
"No module named rewindagents", although pip wrote the `rewindagents` command into the venv.
"""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
from rewindagents import cli, hook  # noqa: E402


def dist_info(site_dir: Path, url: str, editable=True, name="rewindagents-1.2.0.dist-info") -> None:
    """What pip writes for an install (PEP 610 direct_url.json); `editable` mirrors dir_info.editable."""
    info = site_dir / name
    info.mkdir(parents=True)
    (info / "direct_url.json").write_text(json.dumps({"dir_info": {"editable": editable}, "url": url}),
                                          encoding="utf-8")


def sites(*dirs):
    return mock.patch.multiple(hook.site, getsitepackages=lambda: [str(d) for d in dirs],
                               getusersitepackages=lambda: "")


class TestEditableDetection(unittest.TestCase):
    def test_editable_install_of_this_tree_hints_the_console_command(self):
        with TemporaryDirectory() as d:
            dist_info(Path(d), ROOT.resolve().as_uri())
            with sites(d), mock.patch.object(hook, "installed", return_value=False):
                self.assertTrue(hook.editable())
                self.assertEqual(cli.invocation(), "rewindagents")

    def test_a_bare_clone_still_hints_the_module(self):
        with TemporaryDirectory() as d, sites(d), mock.patch.object(hook, "installed", return_value=False):
            self.assertFalse(hook.editable())
            self.assertEqual(cli.invocation(), "python3 -m rewindagents")

    def test_only_an_editable_record_of_this_very_tree_counts(self):
        with TemporaryDirectory() as d, TemporaryDirectory() as other:
            dist_info(Path(d), Path(other).resolve().as_uri())                         # another checkout
            dist_info(Path(d), ROOT.resolve().as_uri(), editable=False, name="rewindagents-1.1.0.dist-info")
            bad = Path(d, "rewindagents-0.9.dist-info")
            bad.mkdir()
            (bad / "direct_url.json").write_text("{not json", encoding="utf-8")       # unreadable: skipped
            with sites(d), mock.patch.object(hook, "installed", return_value=False):
                self.assertFalse(hook.editable())
                self.assertEqual(cli.invocation(), "python3 -m rewindagents")

    def test_a_clone_path_with_spaces_matches_its_percent_encoded_url(self):
        self.assertEqual(hook._file_url_path("file:///a%20b/clone"), Path("/a b/clone"))
        self.assertEqual(hook._file_url_path("file://localhost/a/b"), Path("/a/b"))
        self.assertEqual(hook._file_url_path("file:///C:/Users/u/clone"), Path("C:/Users/u/clone"))
        for not_local in ("https://example.com/x", "file://server/share/x", "file:", None, 3):
            self.assertIsNone(hook._file_url_path(not_local), not_local)

    def test_a_regular_install_is_unchanged(self):
        with mock.patch.object(hook, "installed", return_value=True):
            self.assertEqual(cli.invocation(), "rewindagents")


class TestEditableVenvEndToEnd(unittest.TestCase):
    """A real venv laid out the way `pip install -e .` leaves it (a .pth naming src/ plus the dist-info
    record), so no network or build backend is needed. The hook records through the venv's interpreter
    with no PYTHONPATH, then `summary` and `revert` print their hints."""

    def test_summary_and_revert_hints_name_the_console_command(self):
        with TemporaryDirectory() as tmp:
            venv = Path(tmp, "venv")
            subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(venv)], check=True,
                           capture_output=True, timeout=120)
            py = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
            q = subprocess.run([str(py), "-c", "import site; print(next(p for p in site.getsitepackages() "
                                "if p.rstrip('/\\\\').endswith('site-packages')))"],
                               capture_output=True, text=True, env=env, check=True, timeout=60)
            site_dir = Path(q.stdout.strip())
            (site_dir / "__editable__.rewindagents-1.2.0.pth").write_text(str(SRC) + "\n", encoding="utf-8")
            dist_info(site_dir, ROOT.resolve().as_uri())

            proj = Path(tmp, "proj")
            proj.mkdir()
            f = proj / "a.txt"
            f.write_text("v1\n", encoding="utf-8")

            def run(*argv, stdin=None):
                return subprocess.run([str(py), "-m", "rewindagents", *argv], cwd=proj, env=env, input=stdin,
                                      capture_output=True, text=True, timeout=120)

            for event in ("PreToolUse", "PostToolUse"):
                if event == "PostToolUse":
                    f.write_text("v2\n", encoding="utf-8")
                p = run("hook", stdin=json.dumps({"session_id": "s1", "cwd": str(proj), "hook_event_name": event,
                                                  "tool_name": "Edit", "tool_input": {"file_path": str(f)}}))
                self.assertEqual(p.returncode, 0, p.stderr)

            s = run("summary")
            self.assertEqual(s.returncode, 0, s.stderr)
            self.assertIn("  rewindagents rewind 0", s.stdout)
            self.assertNotIn("python3 -m rewindagents", s.stdout)

            r = run("revert", "1")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("undo it with: rewindagents rewind 1 --session s1", r.stdout)


if __name__ == "__main__":
    unittest.main()
