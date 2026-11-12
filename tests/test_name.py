"""The product is called rewindagents (renamed from rewindagent on 2026-11-12, task RB0).

No tracked text file may still say the old name. Allowed: the internal lane path (~/fire/rewindagent, the
board file), which the FIRE runner keys on, and history that records what a critic saw at the time: review
and claim files, and the rejected logo concept folders.
"""
import fnmatch
import os
import re
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY = ["brand/logo/candidates/*", "brand/logo/round2-concepts/*", "*review*.json", "*/pick.json", "*/claims.json"]
OLD = re.compile(r"(?<!fire/)(?<!board-)rewindagent(?!s)", re.I)
TAG = re.compile(r"</?[a-zA-Z][^<>]*>")   # markup can split the name: rewind<span>agent</span>


def old_name_in(line):
    return OLD.search(line) or OLD.search(TAG.sub("", line))


def tracked():
    r = subprocess.run(["git", "-C", ROOT, "ls-files"], capture_output=True, text=True)
    if r.returncode != 0:
        raise unittest.SkipTest("not a git checkout")
    return r.stdout.split()


class TestName(unittest.TestCase):
    def test_no_tracked_file_uses_the_old_name(self):
        hits = []
        for f in tracked():
            if any(fnmatch.fnmatch(f, h) for h in HISTORY):
                continue
            self.assertNotRegex(f, OLD, "a tracked path still carries the old name")
            try:
                with open(os.path.join(ROOT, f), encoding="utf-8") as fh:
                    text = fh.read()
            except (UnicodeDecodeError, FileNotFoundError):
                continue
            for n, line in enumerate(text.splitlines(), 1):
                if old_name_in(line):
                    hits.append("%s:%d: %s" % (f, n, line.strip()[:100]))
        self.assertEqual(hits, [], "old product name still in use:\n" + "\n".join(hits[:20]))

    def test_package_and_console_script_carry_the_new_name(self):
        with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as fh:
            py = fh.read()
        self.assertIn('name = "rewindagents"', py)
        self.assertIn('rewindagents = "rewindagents.cli:main"', py)
        self.assertTrue(os.path.isdir(os.path.join(ROOT, "src", "rewindagents")))

    def test_the_guard_catches_the_old_name(self):
        self.assertTrue(OLD.search("pipx install rewindagent"))
        self.assertTrue(OLD.search("REWINDAGENT_BIN"))
        self.assertFalse(OLD.search("rewindagents rewind 12"))
        self.assertFalse(OLD.search("~/fire/rewindagent/tests"))
        self.assertTrue(old_name_in("<h1>rewind<span>agent</span> replay</h1>"))
        self.assertFalse(old_name_in("<h1>rewind<span>agents</span> replay</h1>"))

    def test_an_exported_page_names_the_product(self):
        import sys
        sys.path.insert(0, os.path.join(ROOT, "src"))
        from rewindagents import export
        with open(export.__file__, encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("rewind<span>agents</span> replay", src)


if __name__ == "__main__":
    unittest.main()
