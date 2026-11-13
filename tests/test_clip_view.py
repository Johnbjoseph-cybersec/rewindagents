"""R32: a clipped value reads as its head plus one line, not as the clip dict's JSON, in every replay surface.

The hook records a long input or result as {"truncated": true, "chars": N, "head": <first 4,000>}
(hook.clip_input, hook._clip). The export page, the ui step panel and `replay --step` used to print that dict
as it is. Driven through the real hook process; every number the tests expect is read from the log record.
"""
from __future__ import annotations

import html
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from rewindagents import cli, export, log, redact, ui  # noqa: E402


def run_hook(payload: dict, cwd: Path) -> None:
    env = dict(os.environ, PYTHONPATH=str(SRC))
    r = subprocess.run([sys.executable, "-m", "rewindagents", "hook", "--agent", "claude"],
                       input=json.dumps(payload).encode("utf-8"), capture_output=True, cwd=cwd, env=env, timeout=120)
    assert r.returncode == 0 and b"not recorded" not in r.stderr, r.stderr


def record(root: Path, content: str, response: str) -> Path:
    """Step 1: a Write of `content` (input clipped). Step 2: a Read answered with `response` (result clipped)."""
    target = root / "big.txt"
    target.write_text("old\n", encoding="utf-8")
    w = {"session_id": "s1", "cwd": str(root), "tool_name": "Write",
         "tool_input": {"file_path": str(target), "content": content}}
    run_hook({**w, "hook_event_name": "PreToolUse"}, root)
    target.write_text(content, encoding="utf-8")
    run_hook({**w, "hook_event_name": "PostToolUse", "tool_response": {"success": True}}, root)
    r = {"session_id": "s1", "cwd": str(root), "tool_name": "Read", "tool_input": {"file_path": str(target)}}
    run_hook({**r, "hook_event_name": "PreToolUse"}, root)
    run_hook({**r, "hook_event_name": "PostToolUse", "tool_response": response}, root)
    return root / ".rewindagents" / "log.jsonl"


def notes_from_log(lg: Path) -> tuple[str, str]:
    """(input note, result note), with the numbers taken from the post records."""
    posts = [r for r in log.read(lg) if r["event"] == "post"]
    c_in = posts[0]["args"]["input"]["content"]
    c_res = posts[1]["result"]
    assert redact.is_clip(c_in) and redact.is_clip(c_res)
    return (export.clip_note(len(c_in["head"]), c_in["chars"]), export.clip_note(len(c_res["head"]), c_res["chars"]))


class ClipThroughEverySurface(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.content = "line of the new file\n" * 600            # 12,600 characters
        self.response = "x" * 9000 + "END"
        self.lg = record(self.root, self.content, self.response)
        self.in_note, self.res_note = notes_from_log(self.lg)

    def tearDown(self):
        self.tmp.cleanup()

    def test_numbers_are_the_records(self):
        self.assertEqual(self.in_note, f"... first 4,000 of {len(self.content):,} characters kept in the log")
        self.assertIn("of 9,0", self.res_note)       # the result is JSON-encoded text, so the record says how long

    def test_export_page(self):
        export.export(self.lg, out=self.root / "page.html")
        page = (self.root / "page.html").read_text(encoding="utf-8")
        self.assertNotIn("truncated", page)
        self.assertNotIn("&quot;chars&quot;", page)
        self.assertIn(html.escape(self.in_note), page)
        self.assertIn(html.escape(self.res_note), page)
        # the head is shown, and the note is the line right after it
        head = json.dumps(self.content[:4000], ensure_ascii=False)
        self.assertIn(html.escape(f'"content": {head},\n  {self.in_note}\n  "file_path"'), page)  # log sorts keys
        self.assertIn(html.escape(f"{'x' * 4000}\n{self.res_note}"), page)
        self.assertNotIn("END", page)

    def test_ui_step_panel(self):
        d1, d2 = ui.step_detail(self.lg, "s1", 1), ui.step_detail(self.lg, "s1", 2)
        self.assertNotIn("truncated", d1["input"] + d2["result"])
        self.assertIn(self.in_note, d1["input"])
        self.assertEqual(d2["result"].split("\n")[-1], self.res_note)

    def test_replay_step(self):
        for n, note in (("1", self.in_note), ("2", self.res_note)):
            out = io.StringIO()
            with redirect_stdout(out):
                code = cli.main(["--log", str(self.lg), "replay", "--step", n])
            self.assertEqual(code, 0)
            self.assertNotIn("truncated", out.getvalue())
            self.assertIn(note, out.getvalue())

    def test_redacted_head_keeps_the_logs_number(self):
        """Redaction can change the head's length; the note still says what the log kept."""
        tok = "gh" + "p_" + "A1b2C3d4" * 5
        content = "a " * 1995 + tok + " tail" * 400             # the token straddles the cut at 4,000
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            lg = record(root, content, "short")
            export.export(lg, out=root / "page.html")
            page = (root / "page.html").read_text(encoding="utf-8")
            self.assertIn("[redacted github token]", page)
            self.assertIn(f"... first 4,000 of {len(content):,} characters kept in the log", page)
            self.assertNotIn("truncated", page)


class Show(unittest.TestCase):
    def test_without_clips_it_is_the_json(self):
        v = {"file_path": "a.py", "edits": [{"old": "x", "new": "y"}], "n": 1, "ok": True, "none": None}
        self.assertEqual(export.show(v), json.dumps(v, indent=2, ensure_ascii=False))

    def test_nested_in_a_list(self):
        c = {"truncated": True, "chars": 5000, "head": "h" * 10}
        out = export.show({"edits": [{"new_string": c}, {"new_string": "y"}]})
        lines = out.split("\n")
        i = lines.index('      "new_string": "hhhhhhhhhh"')
        self.assertEqual(lines[i + 1], "      ... first 10 of 5,000 characters kept in the log")
        self.assertIn('"new_string": "y"', out)

    def test_after_a_comma(self):
        c = {"truncated": True, "chars": 50, "head": "abc"}
        lines = export.show({"content": c, "file_path": "f"}).split("\n")
        self.assertEqual(lines[1:3], ['  "content": "abc",', "  ... first 3 of 50 characters kept in the log"])

    def test_whole_value_clipped(self):
        c = {"truncated": True, "chars": 9, "head": "one\ntwo"}
        self.assertEqual(export.show(c), "one\ntwo\n... first 7 of 9 characters kept in the log")

    def test_not_a_clip_stays_json(self):
        v = {"truncated": True, "chars": 2, "head": "abc"}             # chars not over the head: not the hook's
        self.assertEqual(export.show(v), json.dumps(v, indent=2))

    def test_found_from_before_redaction_wins(self):
        raw = {"content": {"truncated": True, "chars": 6000, "head": "z" * 4000}}
        shown = {"content": {"truncated": True, "chars": 6000, "head": "z" * 3990 + "[redacted github token]"}}
        out = export.show(shown, export.clips(raw))
        self.assertIn("... first 4,000 of 6,000 characters kept in the log", out)
        self.assertNotIn("truncated", out)


if __name__ == "__main__":
    unittest.main()
