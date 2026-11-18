"""PyPI readiness, local only: what the sdist and wheel carry, and install from a throwaway uvx / pipx run Python.

The archives are built by .fire-test-cmd with `python -m build` (sdist first, then the wheel from that sdist),
into the directory named by REWINDAGENTS_DIST; these tests read the files themselves. Nothing is uploaded.
"""
from __future__ import annotations

import io
import os
import sys
import tarfile
import unittest
import zipfile
from contextlib import redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
from rewindagents import __version__, cli, hook  # noqa: E402

DIST = os.environ.get("REWINDAGENTS_DIST")
MODULES = sorted(p.name for p in (SRC / "rewindagents").glob("*.py"))


@unittest.skipUnless(DIST, "REWINDAGENTS_DIST not set; .fire-test-cmd sets it after python -m build")
class DistributionFilesTest(unittest.TestCase):
    def one(self, pattern: str) -> Path:
        found = sorted(Path(DIST).glob(pattern))
        self.assertEqual(len(found), 1, f"{pattern} in {DIST}: {found}")
        return found[0]

    def test_wheel_carries_only_the_package_and_its_metadata(self):
        whl = self.one(f"rewindagents-{__version__}-py3-none-any.whl")
        names = zipfile.ZipFile(whl).namelist()
        info = f"rewindagents-{__version__}.dist-info/"
        package = sorted(n for n in names if not n.startswith(info))
        self.assertEqual(package, [f"rewindagents/{m}" for m in MODULES])
        meta = sorted(n[len(info):] for n in names if n.startswith(info))
        self.assertTrue({"METADATA", "RECORD", "WHEEL", "entry_points.txt", "top_level.txt"} <= set(meta), meta)
        self.assertTrue(set(meta) <= {"METADATA", "RECORD", "WHEEL", "entry_points.txt", "top_level.txt",
                                      "licenses/LICENSE"}, meta)
        eps = zipfile.ZipFile(whl).read(info + "entry_points.txt").decode()
        self.assertIn("rewindagents = rewindagents.cli:main", eps)

    def test_sdist_prunes_tests_brand_bench_attach_billing(self):
        sd = self.one(f"rewindagents-{__version__}.tar.gz")
        top = f"rewindagents-{__version__}/"
        with tarfile.open(sd) as t:
            names = sorted(m.name[len(top):] for m in t.getmembers() if m.isfile())
        egg = [n for n in names if n.startswith("src/rewindagents.egg-info/")]
        rest = sorted(set(names) - set(egg))
        self.assertEqual(rest, sorted(["LICENSE", "MANIFEST.in", "PKG-INFO", "README.md", "pyproject.toml",
                                       "setup.cfg"] + [f"src/rewindagents/{m}" for m in MODULES]))
        for d in ("tests/", "brand/", "bench/", "attach/", "billing/"):
            self.assertFalse([n for n in names if n.startswith(d)], d)

    def test_metadata_names_the_console_script_python_and_licence(self):
        whl = self.one("*.whl")
        meta = zipfile.ZipFile(whl).read(f"rewindagents-{__version__}.dist-info/METADATA").decode()
        self.assertIn("Name: rewindagents", meta)
        self.assertIn(f"Version: {__version__}", meta)
        self.assertIn("Requires-Python: >=3.10", meta)
        self.assertNotIn("Requires-Dist:", meta)  # stdlib only


class EphemeralPythonTest(unittest.TestCase):
    HOME = Path("/home/u")

    def kind(self, prefix, env=None):
        return hook.ephemeral(prefix=prefix, env=env or {}, home=self.HOME)

    def test_uvx_cache_default_xdg_and_override(self):
        self.assertEqual(self.kind("/home/u/.cache/uv/archive-v0/AbC123"), "uvx")
        self.assertEqual(self.kind("/x/cache/uv/archive-v0/AbC", {"XDG_CACHE_HOME": "/x/cache"}), "uvx")
        self.assertEqual(self.kind("/scratch/uvc/archive-v0/AbC", {"UV_CACHE_DIR": "/scratch/uvc"}), "uvx")

    def test_pipx_run_cache_paths(self):
        self.assertEqual(self.kind("/home/u/.local/pipx/.cache/3f2a"), "pipx run")
        self.assertEqual(self.kind("/home/u/Library/Caches/pipx/3f2a"), "pipx run")
        self.assertEqual(self.kind("/home/u/.cache/pipx/3f2a"), "pipx run")
        self.assertEqual(self.kind("/opt/px/.cache/3f2a", {"PIPX_HOME": "/opt/px"}), "pipx run")

    def test_lasting_installs_are_not_ephemeral(self):
        for prefix in ("/home/u/.local/share/uv/tools/rewindagents",  # uv tool install
                       "/home/u/.local/pipx/venvs/rewindagents",       # pipx install
                       "/home/u/proj/.venv", "/usr", "/home/u/.cache-not-uv/x"):
            self.assertIsNone(self.kind(prefix), prefix)

    def test_install_refuses_from_a_uvx_python_and_writes_nothing(self):
        with TemporaryDirectory() as d:
            cache = Path(d) / "uvcache"
            prefix = cache / "archive-v0" / "AbC123"
            target = Path(d) / ".claude" / "settings.json"
            env = dict(os.environ, UV_CACHE_DIR=str(cache))
            err = io.StringIO()
            with mock.patch.object(sys, "prefix", str(prefix)), mock.patch.dict(os.environ, env, clear=True), \
                    redirect_stderr(err):
                rc = cli.main(["install", "--settings", str(target)])
            self.assertEqual(rc, 2)
            self.assertFalse(target.exists())
            self.assertIn("uvx", err.getvalue())
            self.assertIn("uv tool install rewindagents", err.getvalue())
            self.assertIn("pipx install rewindagents", err.getvalue())

    def test_install_from_a_lasting_python_still_writes_the_hook(self):
        with TemporaryDirectory() as d:
            target = Path(d) / "settings.json"
            with mock.patch.dict(os.environ, {"UV_CACHE_DIR": str(Path(d) / "uvcache")}):
                self.assertTrue(hook.install(target))
            # Two separate checks, not one "rewindagents hook" substring: from a clone, a Windows interpreter
            # path takes the file-path form (.../rewindagents/__main__.py hook), so "rewindagents" and "hook"
            # are not adjacent there the way they are in the POSIX "-m rewindagents hook" form (R94).
            written = target.read_text()
            self.assertIn("rewindagents", written)
            self.assertIn(" hook", written)

    def test_cli_install_completes_when_path_home_raises(self):
        """Review-round finding: `hook.ephemeral()` (hook.py, a different squad's file) calls
        `Path.home()` completely unguarded. `cli.py`'s `install` command (the `rewindagents install`
        entry point) called it unconditionally, so a host with no HOME/USERPROFILE (windows-latest
        CI's F3 trigger) crashed here too, even once every `init.py`-owned `Path.home()` call was
        guarded. `hook.ephemeral` is NOT patched out (unlike the uvx/pipx cases above): this proves the
        real function, called for real with `Path.home()` raising, no longer crashes `cli.main()`.
        Fails with the uncaught `RuntimeError` before this fix; passes after."""
        with TemporaryDirectory() as d:
            target = Path(d) / ".claude" / "settings.json"
            with mock.patch.object(Path, "home", side_effect=RuntimeError("no HOME/USERPROFILE")):
                rc = cli.main(["install", "--settings", str(target)])
            self.assertEqual(rc, 0)
            self.assertTrue(target.is_file())

    def test_init_refuses_before_its_plan_and_writes_nothing(self):
        from rewindagents import init
        with TemporaryDirectory() as d:
            root = Path(d) / "proj"
            (root / ".claude").mkdir(parents=True)
            cache = Path(d) / "uvcache"
            out = io.StringIO()
            with mock.patch.object(sys, "prefix", str(cache / "archive-v0" / "X")), \
                    mock.patch.dict(os.environ, {"UV_CACHE_DIR": str(cache)}):
                rc = init.main(yes=True, root=root, home=Path(d) / "home", path="", out=out)
            self.assertEqual(rc, 2, out.getvalue())
            self.assertIn("nothing written", out.getvalue())
            self.assertIn("uv tool install rewindagents", out.getvalue())
            self.assertFalse((root / ".claude" / "settings.json").exists())


class ReadmeInstallLinesTest(unittest.TestCase):
    def test_pypi_lines_are_current_and_nothing_says_it_is_not_on_pypi(self):
        # Before 0.0.8 this rule required the PyPI lines to be marked "after the first release" and forbade any
        # claim that the package was on PyPI. 0.0.8 is on PyPI, so the rule flips, just as strict: the README
        # gives the PyPI install, and nothing in it still says (or plans as if) it is not there.
        readme = (ROOT / "README.md").read_text()
        self.assertIn("uv tool install rewindagents", readme)
        self.assertIn("pipx install rewindagents", readme)
        self.assertNotRegex(readme, r"(?i)not (yet )?on PyPI|on PyPI yet|not there yet")
        self.assertNotRegex(readme, r"(?i)after (the )?(first )?release")
        self.assertNotRegex(readme, r"(?im)^- Publish on PyPI")


if __name__ == "__main__":
    unittest.main()
