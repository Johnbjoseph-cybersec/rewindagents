"""`rewindagent export`: one self-contained HTML page per session, with file diffs."""
import json
import os
import re
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import rewindagent  # noqa: E402
from rewindagent import export, hook, rewind  # noqa: E402
from test_rewind import Agent, cli  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


class Balance(HTMLParser):
    """Counts open/close of the tags the page is built from, so a broken f-string fails a test."""
    VOID = {"meta", "br", "hr", "img", "input", "link"}

    def __init__(self):
        super().__init__()
        self.depth, self.scripts, self.external = {}, 0, []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.depth[tag] = self.depth.get(tag, 0) + 1
        if tag in ("script", "link", "img", "iframe"):
            self.scripts += 1
        for k, v in attrs:
            if k in ("src", "href") and v and v.startswith(("http", "//")):
                self.external.append(v)

    def handle_endtag(self, tag):
        self.depth[tag] = self.depth.get(tag, 0) - 1


def wrecked(d, session="s1"):
    """A session: app.py written, edited, broken; a junk file created; a Bash step that renames."""
    a = Agent(d, session)
    a.write("app.py", "def main():\n    return 1\n")                       # 1 creates
    a.write("app.py", "def main():\n    return 2\n")                       # 2 edits
    a.write("junk.py", "x = 1\n")                                          # 3 creates
    a.write("app.py", "def main():\n    raise SystemExit('wrecked')\n")    # 4 breaks
    a.bash("mv junk.py moved.py", action=lambda cwd: os.rename(cwd / "junk.py", cwd / "moved.py"))  # 5
    return a


class TestBuild(unittest.TestCase):
    def test_diff_is_before_the_step_against_after_it(self):
        with TemporaryDirectory() as d:
            a = wrecked(d)
            data = export.build(a.log)
            self.assertEqual([s["step"] for s in data["steps"]], [1, 2, 3, 4, 5])
            s1 = data["steps"][0]["files"][0]
            self.assertEqual((s1["path"], s1["before"]), ("app.py", "absent"))
            self.assertIn("+    return 1", s1["change"]["lines"])
            s2 = data["steps"][1]["files"][0]
            self.assertIn("-    return 1", s2["change"]["lines"])
            self.assertIn("+    return 2", s2["change"]["lines"])
            s4 = data["steps"][3]["files"][0]        # after step 4 = the file as it is now
            self.assertEqual(s4["after"], "now")
            self.assertIn("+    raise SystemExit('wrecked')", s4["change"]["lines"])

    def test_bash_rename_shows_the_deleted_and_the_created_file(self):
        with TemporaryDirectory() as d:
            a = wrecked(d)
            files = {f["path"]: f for f in export.build(a.log)["steps"][4]["files"]}
            self.assertEqual(set(files), {"junk.py", "moved.py"})
            self.assertEqual(files["junk.py"]["after"], "absent now")
            self.assertIn("-x = 1", files["junk.py"]["change"]["lines"])
            self.assertEqual(files["moved.py"]["before"], "absent")
            self.assertIn("+x = 1", files["moved.py"]["change"]["lines"])

    def test_after_is_the_next_checkpoint_when_the_file_changed_again_later(self):
        with TemporaryDirectory() as d:
            a = Agent(d)
            a.write("f.txt", "one\n")
            a.write("f.txt", "two\n")
            a.write("f.txt", "three\n")
            s2 = export.build(a.log)["steps"][1]["files"][0]
            self.assertEqual(s2["change"]["lines"][-2:], ["-one", "+two"])
            self.assertNotEqual(s2["after"], "now")

    def test_binary_and_oversize_files_are_described_not_diffed(self):
        with TemporaryDirectory() as d:
            a = Agent(d)
            a.write("img.bin", "x")
            Path(d, "img.bin").write_bytes(b"\xff\xfe\x00\x01")
            a.write("big.txt", "a" * (export.MAX_DIFF_BYTES + 1))
            steps = export.build(a.log)["steps"]
            self.assertEqual(steps[0]["files"][0]["change"]["kind"], "note")
            self.assertIn("binary", steps[0]["files"][0]["change"]["note"])
            self.assertIn("over the", steps[1]["files"][0]["change"]["note"])

    def test_long_diffs_are_cut_with_a_count(self):
        with TemporaryDirectory() as d:
            a = Agent(d)
            a.write("f.txt", "".join(f"{i}\n" for i in range(1000)))
            a.write("f.txt", "")
            ch = export.build(a.log)["steps"][1]["files"][0]["change"]
            self.assertEqual(len(ch["lines"]), export.MAX_DIFF_LINES)
            self.assertGreater(ch["more"], 0)

    def test_no_contents_leaves_inputs_results_and_diffs_out(self):
        with TemporaryDirectory() as d:
            a = wrecked(d)
            data = export.build(a.log, contents=False)
            self.assertTrue(all("change" not in f for s in data["steps"] for f in s["files"]))
            page = export.render(data)
            self.assertFalse("return 1" in page, "a Write input (file content) leaked")
            self.assertFalse('"ok": true' in page or "&quot;ok&quot;: true" in page, "a result leaked")
            self.assertIn("mv junk.py moved.py", page)        # the replay summary line stays
            self.assertIn("app.py", page)

    def test_rewind_step_and_unknown_session(self):
        with TemporaryDirectory() as d:
            a = wrecked(d)
            rewind.rewind(a.log, 2)
            last = export.build(a.log)["steps"][-1]
            self.assertEqual((last["event"], last["to_step"]), ("rewind", 2))
            self.assertIn("Rewound the files to how they were after step 2", export.render(export.build(a.log)))
            with self.assertRaises(export.ExportError):
                export.build(a.log, "nope")


class TestPage(unittest.TestCase):
    def test_page_is_self_contained_balanced_and_escaped(self):
        with TemporaryDirectory() as d:
            a = wrecked(d)
            a.bash('echo "<script>alert(1)</script>" > x.html',
                   action=lambda cwd: (cwd / "x.html").write_text("<script>alert(1)</script>\n"))
            page = export.render(export.build(a.log))
            b = Balance()
            b.feed(page)
            self.assertEqual({k: v for k, v in b.depth.items() if v}, {}, "unbalanced tags")
            self.assertEqual(b.scripts, 0)
            self.assertEqual(b.external, [])
            self.assertFalse("<script>" in page, "unescaped script tag")
            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)
            self.assertFalse("url(" in page, "css url()")

    def test_project_location_is_not_in_the_page(self):
        with TemporaryDirectory() as d:
            a = wrecked(d)
            page = export.render(export.build(a.log))
            for root in (str(Path(d)), str(Path(d).resolve())):
                self.assertFalse(root in page, f"project location {root} is in the page")
            self.assertIn("&quot;file_path&quot;: &quot;app.py&quot;", page)   # inputs show the relative path

    def test_bare_root_in_a_command_or_input_is_not_in_the_page(self):
        # R11: `cd /abs/proj`, a Cursor-style working_directory, and the Bash summary line all carried the
        # bare root, which the old root+separator scrub missed.
        with TemporaryDirectory() as d:
            a = wrecked(d)
            for root in (str(Path(d)), str(Path(d).resolve())):
                a.bash(f"cd {root} && ls")
                a.bash(f"cat {root}/app.py")
                inp = {"command": "make", "working_directory": root}
                hook.handle(a._p("PreToolUse", "Bash", inp))
                hook.handle(a._p("PostToolUse", "Bash", inp, {"stdout": f"in {root}\n"}))
            for contents in (True, False):
                page = export.render(export.build(a.log, contents=contents))
                for root in (str(Path(d)), str(Path(d).resolve())):
                    self.assertFalse(root in page, f"project location {root} is in the page (contents={contents})")
                self.assertIn("cd . &amp;&amp; ls", page)
                self.assertIn("cat app.py", page)

    def test_a_long_command_is_scrubbed_before_it_is_cut(self):
        with TemporaryDirectory() as d:
            a = Agent(d)
            root = str(Path(d).resolve())
            a.bash("x" * 99 + f" {root}")       # the root starts at 100: a 120-character cut keeps 17 of it
            page = export.render(export.build(a.log))
            self.assertFalse(root[:12] in page, "half the root survived the cut")

    def test_scrub_leaves_a_sibling_that_only_starts_with_the_root(self):
        self.assertEqual(export.scrub("cd /p/proj; cd /p/proj2; cat /p/proj/a", ["/p/proj"]),
                         "cd .; cd /p/proj2; cat a")

    def test_page_carries_the_steps_the_credit_and_the_version(self):
        with TemporaryDirectory() as d:
            a = wrecked(d)
            page = export.render(export.build(a.log))
            self.assertIn("5 steps", page)
            self.assertIn("mv junk.py moved.py", page)
            self.assertIn(export.CREDIT, page)
            self.assertIn(f"rewindagent {rewindagent.__version__}", page)
            self.assertIn("chain intact", page)

    def test_tampered_log_still_exports_and_says_so(self):
        with TemporaryDirectory() as d:
            a = wrecked(d)
            lines = a.log.read_text().splitlines()
            rec = json.loads(lines[1])
            rec["tool"] = "Edit"
            lines[1] = json.dumps(rec, sort_keys=True)
            a.log.write_text("\n".join(lines) + "\n")
            page = export.render(export.build(a.log))
            self.assertIn("This log does not verify", page)
            self.assertIn("record 2: contents altered", page)

    def test_palette_in_export_is_the_brand_palette(self):
        brand = (ROOT / "brand" / "BRAND.md").read_text(encoding="utf-8")
        rows = dict(re.findall(r"^\| (\w+) \| (#[0-9A-Fa-f]{6}) \|", brand, re.M))
        self.assertEqual({k: v.upper() for k, v in export.PALETTE.items()}, {k: v.upper() for k, v in rows.items()})
        for hexval in re.findall(r"#[0-9A-Fa-f]{6}", export._CSS):
            self.assertIn(hexval.upper(), {v.upper() for v in rows.values()})

    def test_readme_limit_is_the_real_one(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(f"{export.MAX_DIFF_BYTES // 1024} KB", readme)
        self.assertIn(f"{export.MAX_DIFF_LINES} lines", readme)


class TestCli(unittest.TestCase):
    def test_export_writes_the_default_file_and_reports_it(self):
        with TemporaryDirectory() as d:
            a = wrecked(d)
            code, out, err = cli("--log", str(a.log), "export")
            self.assertEqual((code, err), (0, ""))
            page = Path(d, ".rewindagent", "replay-s1.html")
            self.assertTrue(page.is_file())
            self.assertIn(f"wrote .rewindagent/replay-s1.html: session s1, 5 steps, {page.stat().st_size:,} bytes", out)
            self.assertTrue(page.read_text().startswith("<!doctype html>"))

    def test_out_session_and_no_diffs_flags(self):
        with TemporaryDirectory() as d:
            wrecked(d, "old")
            a = wrecked(d, "new")
            target = Path(d, "share", "replay.html")
            code, out, _ = cli("--log", str(a.log), "export", "--session", "old", "--out", str(target), "--no-contents")
            self.assertEqual(code, 0)
            self.assertIn("session old", out)
            text = target.read_text()
            self.assertIn("Exported without contents", text)
            self.assertFalse("return 1" in text, "file content leaked")

    def test_exit_codes(self):
        with TemporaryDirectory() as d:
            a = wrecked(d)
            self.assertEqual(cli("--log", str(Path(d, "none.jsonl")), "export")[0], 2)
            code, _, err = cli("--log", str(a.log), "export", "--session", "nope")
            self.assertEqual(code, 1)
            self.assertIn("no steps for session 'nope'", err)
            lines = a.log.read_text().splitlines()
            rec = json.loads(lines[0])
            rec["tool"] = "Edit"
            lines[0] = json.dumps(rec, sort_keys=True)
            a.log.write_text("\n".join(lines) + "\n")
            code, out, err = cli("--log", str(a.log), "export")
            self.assertEqual(code, 1)
            self.assertIn("wrote", out)                 # the page is still written
            self.assertIn("does not verify", err)


if __name__ == "__main__":
    unittest.main()
