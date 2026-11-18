"""The site's fork-and-compare panels quote brand/demo/runs.json, which brand/demo/runs.py wrote from a run of
ux-review/try-runs.sh against an installed build. These tests run the script again (against the source tree) and
fail if a quoted line changes, so the panels cannot show output the CLI no longer prints."""
import html
import importlib.util
import json
import os
import re
import shutil
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "brand", "site")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


@unittest.skipUnless(shutil.which("git") and shutil.which("sh"), "needs git and sh")
@unittest.skipIf(os.name == "nt", "try-runs.sh is a POSIX sh demo (mktemp, /tmp paths, python3) whose POSIX "
                                  "output the site quotes; Windows has no POSIX sh (windows-latest: the runner's "
                                  "sh exited 2 on it)")
class TestRunsDemo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = load("site_build_runs", os.path.join(SITE, "build.py"))
        cls.runs = load("demo_runs", os.path.join(ROOT, "brand", "demo", "runs.py"))
        cls.stored = json.loads(read("brand", "demo", "runs.json"))
        old = os.environ.get("PYTHONPATH")
        os.environ["PYTHONPATH"] = os.path.join(ROOT, "src") + (os.pathsep + old if old else "")
        try:
            cls.fresh = cls.runs.run("%s -m rewindagents" % sys.executable)
        finally:
            if old is None:
                os.environ.pop("PYTHONPATH")
            else:
                os.environ["PYTHONPATH"] = old

    def quoted(self):
        rows = self.build.runs_rows(self.stored, "hero") + self.build.runs_rows(self.stored, "diff")
        self.assertTrue(rows)
        return rows

    def test_every_quoted_line_is_what_the_script_prints(self):
        fresh = {ln for lines in self.fresh.values() for ln in lines}
        stored = {ln for lines in self.stored["output"].values() for ln in lines}
        for kind, text in self.quoted():
            if kind == "cmd":
                continue
            self.assertIn(text, stored, "not in brand/demo/runs.json: %r" % text)
            self.assertIn(text, fresh, "try-runs.sh no longer prints: %r" % text)
        # and nothing quoted names the script's temporary folder
        for _, text in self.quoted():
            self.assertNotRegex(text, r"/(tmp|var/folders)/", text)

    def test_quoted_commands_are_the_scripts_commands(self):
        script = read("ux-review", "try-runs.sh")
        for kind, text in self.quoted():
            if kind == "cmd":
                self.assertTrue(text.startswith("rewindagents "), text)
                self.assertIn("$RA " + text[len("rewindagents "):], script, text)

    def test_the_tables_match_the_fresh_run_line_for_line(self):
        b = self.build
        for head in (b.RUNS_FORK, b.RUNS_COMPARE, b.RUNS_DIFF):
            # temporary paths differ per run, and a failing check's last lines depend on the Python that ran it
            # the fork's hint names the command as it was invoked: here `python -m rewindagents`
            keep = lambda ls: [re.sub(r"[^\s`]*python[\d.]* -m rewindagents", "rewindagents", ln) for ln in ls  # noqa: E731
                               if not re.search(r"/(tmp|var/folders|private)/", ln) and not ln.startswith("  shop: ")]
            self.assertEqual(keep(self.fresh[head]), keep(self.stored["output"][head]), head)

    def test_the_pages_carry_the_panels(self):
        for page in ("index.html", os.path.join("docs", "index.html")):
            with open(os.path.join(SITE, page), encoding="utf-8") as fh:
                text = html.unescape(re.sub(r"<[^>]+>", "", fh.read()))
            for _, row in self.quoted():
                self.assertIn(row, text, "%s: %r" % (page, row))


if __name__ == "__main__":
    unittest.main()
