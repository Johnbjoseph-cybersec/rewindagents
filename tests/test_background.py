"""Background Bash calls (R20). Claude Code's Bash input carries `run_in_background` ("Whether to run the command
in background", https://code.claude.com/docs/en/hooks, read 2026-11-12). The same page documents no hook event
for a background shell finishing, and no tool_response shape for one, so the after-scan may run while the command
is still going. These tests drive the real hook process with that documented input field; the tool_response used
here is a stand-in, not a documented shape. Stdlib only."""
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from rewindagents import bashscan, export, rewind, ui, verify  # noqa: E402
from test_rewind import cli  # noqa: E402
from test_subagent import call  # noqa: E402


def background_session(d):
    """Step 1: a background build that writes out.txt before its after-scan and app.py after it."""
    Path(d, "app.py").write_text("good\n")
    inp = {"command": "make build", "description": "Build", "run_in_background": True}
    call(d, "PreToolUse", "Bash", inp, use_id="toolu_bg")
    Path(d, "out.txt").write_text("partial\n")            # changed before the hook's after-scan
    call(d, "PostToolUse", "Bash", inp, {"stdout": ""}, use_id="toolu_bg")
    Path(d, "app.py").write_text("rebuilt\n")             # changed after it: the scan cannot see this
    return Path(d, ".rewindagents", "log.jsonl")


class TestBackgroundBash(unittest.TestCase):
    def test_step_is_marked_and_what_was_seen_is_still_rewound(self):
        with TemporaryDirectory() as d:
            log = background_session(d)
            self.assertTrue(verify(log)[0])
            s = rewind.steps(log)[0]
            self.assertEqual(s["bash_scan"], {"changed": 1, "early": bashscan.EARLY})
            p = rewind.rewind(log, 0)
            self.assertEqual((p["scan_early"], p["bash_uncovered"], p["cannot"]), (1, 0, []))
            self.assertFalse(Path(d, "out.txt").exists())                        # seen: undone
            self.assertEqual(Path(d, "app.py").read_text(), "rebuilt\n")         # unseen: stays, and is reported

    def test_cli_marks_replay_and_rewind_and_diff_exit_1(self):
        with TemporaryDirectory() as d:
            log = background_session(d)
            code, out, _ = cli("--log", str(log), "replay")
            self.assertEqual(code, 0)
            self.assertIn("[background: scan may be early]", out)
            code, _, err = cli("--log", str(log), "diff", "0")
            self.assertEqual(code, 1)
            self.assertIn("1 step(s) after step 0 ran a command in the background", err)
            code, out, _ = cli("--log", str(log), "rewind", "0", "--dry-run")
            self.assertEqual(code, 1)
            self.assertIn("may not have been put back", out)
            self.assertEqual(cli("--log", str(log), "rewind", "1", "--dry-run")[0], 0)   # nothing after step 1

    def test_export_page_and_ui_carry_the_note(self):
        with TemporaryDirectory() as d:
            log = background_session(d)
            out = export.export(log, None, str(Path(d, "page.html")))["out"]
            self.assertIn("This command ran in the background", Path(out).read_text(encoding="utf-8"))
            session = rewind.latest_session(log)
            self.assertTrue(ui.timeline(log, session)["steps"][0]["scan_early"])
            self.assertEqual(ui.preview(log, {"session": session, "step": 0})["scan_early"], 1)

    def test_foreground_and_other_values_are_not_marked(self):
        for ti in ({"command": "ls"}, {"command": "ls", "run_in_background": False},
                   {"command": "ls", "run_in_background": "true"}, None):
            self.assertFalse(bashscan.background({"tool_input": ti}), ti)
        with TemporaryDirectory() as d:
            inp = {"command": "touch x", "run_in_background": False}
            call(d, "PreToolUse", "Bash", inp, use_id="toolu_fg")
            Path(d, "x").write_text("")
            call(d, "PostToolUse", "Bash", inp, {"stdout": ""}, use_id="toolu_fg")
            log = Path(d, ".rewindagents", "log.jsonl")
            self.assertEqual(rewind.steps(log)[0]["bash_scan"], {"changed": 1})
            self.assertEqual(rewind.rewind(log, 0, dry_run=True)["scan_early"], 0)


if __name__ == "__main__":
    unittest.main()
