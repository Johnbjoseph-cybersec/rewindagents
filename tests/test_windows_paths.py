"""Windows path spellings, driven on any OS (R41: the Windows port, local half).

No Windows machine is needed: a Windows path is just a string here (C:\\proj, C:/proj), and the code that
reads paths recorded on another machine (bundle import) or scrubs them out of a page (export) must accept
both separators for a Windows root. Paths this machine resolves itself stay this machine's business."""
import hashlib
import json
import os
import sys
import unittest
from pathlib import Path, PureWindowsPath
from unittest import mock
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from rewindagents import bundle, export, rewind, verify  # noqa: E402
from test_bundle import recorded, tree  # noqa: E402

WIN = "C:\\Users\\dev\\proj"


def windowsify(obj, spellings):
    """obj with every path under one of the spellings re-spelled as if recorded under WIN on Windows."""
    if isinstance(obj, str):
        for sp in spellings:
            if obj == sp:
                return WIN
            # the source session was recorded on this machine: on Windows its own paths use \\
            if any(obj.startswith(sp + sep) for sep in {"/", os.sep}):
                return WIN + "\\" + obj[len(sp) + 1:].replace("/", "\\")
        return obj
    if isinstance(obj, dict):
        return {k: windowsify(v, spellings) for k, v in obj.items()}
    if isinstance(obj, list):
        return [windowsify(v, spellings) for v in obj]
    return obj


def made_on_windows(path):
    """Rewrite a bundle as the same session recorded in C:\\Users\\dev\\proj (record hashes + digest redone)."""
    b = json.loads(Path(path).read_text(encoding="utf-8"))
    spellings = b["root_spellings"]
    for i, r in enumerate(b["records"]):
        r = windowsify(r, spellings)
        r["hash"] = hashlib.sha256(json.dumps({k: v for k, v in r.items() if k != "hash"}, sort_keys=True,
                                              separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        b["records"][i] = r
    b["root"], b["root_spellings"] = WIN, [WIN]
    b["digest"] = bundle.digest(b)
    Path(path).write_text(json.dumps(b), encoding="utf-8")


class TestBundleFromWindows(unittest.TestCase):
    def test_a_bundle_recorded_on_windows_imports_replays_and_rewinds_here(self):
        with TemporaryDirectory() as src, TemporaryDirectory() as dst:
            a = recorded(src)
            out = Path(src, "win.bundle")
            bundle.bundle(a.log, out)
            made_on_windows(out)
            self.assertIn(WIN + "\\a.txt", out.read_text(encoding="utf-8").replace("\\\\", "\\"))
            dest_log = Path(dst, ".rewindagents", "log.jsonl")
            got = bundle.import_bundle(out, dest_log)
            self.assertEqual((got["session"], got["steps"]), ("s1", 4))
            self.assertTrue(verify(dest_log)[0])
            text = dest_log.read_text(encoding="utf-8")
            if os.name == "nt":   # the destination is on a drive letter too: only the source root must be gone
                self.assertNotIn(json.dumps(WIN)[1:-1], text)
                self.assertNotIn(WIN.replace("\\", "/"), text)
            else:
                self.assertNotIn("C:", text)   # every Windows path moved here
            rewind.rewind(dest_log, 2, "s1")
            self.assertEqual(tree(dst), {"a.txt": "v2\n"})
            rewind.rewind(dest_log, 1, "s1")
            self.assertEqual(tree(dst), {"a.txt": "v1\n"})

    def test_move_paths_takes_both_windows_separators_and_this_machines_separator_out(self):
        # bundle.move_paths joins the moved part onto `dest` with os.sep: "this machine's business" (module
        # docstring). `dest` is given here as a POSIX-looking string; on a real Windows run `Path` renders it
        # (and os.sep) the Windows way, so the expectation is built the same way move_paths builds it, not
        # hardcoded to '/' (R94: this literal comparison was the CI failure on windows-latest).
        dest = Path("/home/me/proj")
        self.assertEqual(bundle.move_paths(WIN + "\\src\\a.py", [WIN], dest), str(dest / "src" / "a.py"))
        self.assertEqual(bundle.move_paths("C:/Users/dev/proj/src/a.py", [WIN], dest), str(dest / "src" / "a.py"))
        self.assertEqual(bundle.move_paths(WIN, [WIN], dest), str(dest))
        self.assertEqual(bundle.move_paths(WIN + "2\\a.py", [WIN], dest), WIN + "2\\a.py")   # a sibling stays
        self.assertEqual(bundle.move_paths("/src/proj/a/b.py", ["/src/proj"], dest), str(dest / "a" / "b.py"))

    def test_check_still_refuses_a_relative_root(self):
        with TemporaryDirectory() as src:
            a = recorded(src)
            out = Path(src, "b")
            bundle.bundle(a.log, out)
            b = json.loads(out.read_text(encoding="utf-8"))
            b["root_spellings"] = ["proj"]
            b["digest"] = bundle.digest(b)
            with self.assertRaisesRegex(bundle.BundleError, "source project's path"):
                bundle.check(b)


class TestRootSpellingsOnWindows(unittest.TestCase):
    """bundle.root_spellings() as a Windows run reaches it: the records name the project the way the hook was
    handed it (a temp dir under its 8.3 short name, C:\\Users\\RUNNER~1), the root is the resolved long name,
    and the relative tail comes back with backslashes. Driven here with PureWindowsPath and a stand-in
    realpath, the two things that differ on a real Windows host (windows-latest CI failed exactly this)."""

    LONG = "C:\\Users\\runneradmin\\AppData\\Local\\Temp\\tmp4u"
    SHORT = "C:\\Users\\RUNNER~1\\AppData\\Local\\Temp\\tmp4u"

    def spellings(self, *paths):
        records = [{"args": {"input": {"file_path": p}}} for p in paths]
        with mock.patch.object(bundle, "Path", PureWindowsPath), \
                mock.patch.object(bundle.os.path, "realpath", lambda s: s.replace("RUNNER~1", "runneradmin")):
            return bundle.root_spellings(records, PureWindowsPath(self.LONG))

    def test_the_short_name_the_hook_saw_is_a_spelling_of_the_root(self):
        got = self.spellings(self.SHORT + "\\a.txt", self.SHORT + "\\sub\\b.txt")
        self.assertEqual(sorted(got), sorted([self.LONG, self.SHORT]))

    def test_forward_slashes_and_the_bare_root_are_spellings_too(self):
        fwd = self.SHORT.replace("\\", "/")
        got = self.spellings(fwd + "/sub/b.txt", self.SHORT + "\\")
        self.assertIn(fwd, got)
        self.assertIn(self.SHORT, got)

    def test_case_does_not_hide_a_spelling(self):
        # NTFS ignores case: the agent may spell sub\\b.txt as SUB\\B.TXT, and realpath gives the disk's case
        real = lambda s: s.replace("RUNNER~1", "runneradmin").replace("SUB\\B.TXT", "sub\\b.txt")  # noqa: E731
        with mock.patch.object(bundle, "Path", PureWindowsPath), mock.patch.object(bundle.os.path, "realpath", real):
            got = bundle.root_spellings([{"args": {"p": self.SHORT + "\\SUB\\B.TXT"}}], PureWindowsPath(self.LONG))
        self.assertIn(self.SHORT, got)

    def test_a_path_outside_the_root_adds_nothing(self):
        self.assertEqual(self.spellings("C:\\elsewhere\\a.txt"), [self.LONG])


class TestScrubWindowsRoot(unittest.TestCase):
    def test_a_windows_root_inside_json_text_is_scrubbed(self):
        # A page shows inputs as JSON, where each backslash of C:\\proj\\a.py prints doubled (windows-latest:
        # the page kept "C:\\\\Users\\\\...\\\\app.py" while every other spelling was scrubbed).
        self.assertEqual(export.scrub(json.dumps({"file_path": WIN + "\\app.py"}), [WIN]), '{"file_path": "app.py"}')
        self.assertEqual(export.scrub(json.dumps({"cwd": WIN}), [WIN]), '{"cwd": "."}')
        self.assertEqual(export.scrub(json.dumps({"p": WIN + "2\\a.py"}), [WIN]), json.dumps({"p": WIN + "2\\a.py"}))

    def test_both_separators_after_a_windows_root_are_scrubbed(self):
        self.assertEqual(export.scrub("edit " + WIN + "\\src\\a.py", [WIN]), "edit src\\a.py")
        self.assertEqual(export.scrub("edit C:/Users/dev/proj/src/a.py", [WIN]), "edit src/a.py")
        self.assertEqual(export.scrub("cd C:/Users/dev/proj && ls", [WIN]), "cd . && ls")
        self.assertEqual(export.scrub("cd " + WIN, [WIN]), "cd .")

    def test_a_sibling_that_only_starts_with_the_root_is_left_alone(self):
        self.assertEqual(export.scrub(WIN + "2\\a.py", [WIN]), WIN + "2\\a.py")

    def test_posix_roots_are_unchanged(self):
        self.assertEqual(export.scrub("cat /p/proj/a.txt; cd /p/proj", ["/p/proj"]), "cat a.txt; cd .")


if __name__ == "__main__":
    unittest.main()
