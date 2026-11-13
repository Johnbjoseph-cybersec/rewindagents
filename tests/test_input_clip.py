"""R30: a big tool input (a Write of a 10 MB file) is clipped in the log, not stored twice whole.

Driven through the real hook process. The file's bytes come back from the stored copy, so rewind still restores
them; replay pairs pre and post, and export, sessions --grep and bundle/import still work on the clipped log."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from rewindagents import bundle, export, hook, log, rewind, sessions  # noqa: E402

BIG = 10 * 1024 * 1024
LOG_BOUND = 64 * 1024      # two records of a clipped 10 MB input; whole, they were 20,972,561 bytes


def run_hook(agent: str, payload: dict, cwd: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(SRC))
    return subprocess.run([sys.executable, "-m", "rewindagents", "hook", "--agent", agent],
                          input=json.dumps(payload).encode("utf-8"), capture_output=True, cwd=cwd, env=env,
                          timeout=300)


def big_write(root: Path, agent: str, tool: str) -> tuple[Path, str]:
    """Pre event, the tool writes the file, post event. Returns (file, content)."""
    target = root / "big.txt"
    target.write_text("old\n", encoding="utf-8")
    content = "x" * (BIG - 6) + "SECRET"   # the end of the content is past any head
    base = {"session_id": "s1", "cwd": str(root), "tool_name": tool,
            "tool_input": {"file_path": str(target), "content": content}}
    for event, extra in (("PreToolUse", {}), ("PostToolUse", {"tool_response": {"success": True}})):
        if event == "PostToolUse":
            target.write_text(content, encoding="utf-8")
        r = run_hook(agent, {**base, "hook_event_name": event, **extra}, root)
        assert r.returncode == 0 and b"not recorded" not in r.stderr, r.stderr
    return target, content


class BigInputThroughHook(unittest.TestCase):
    def check(self, agent: str, tool: str) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            target, content = big_write(root, agent, tool)
            lg = root / ".rewindagents" / "log.jsonl"
            self.assertLess(lg.stat().st_size, LOG_BOUND)
            self.assertTrue(log.verify(lg)[0])
            recs = log.read(lg)
            self.assertEqual([r["event"] for r in recs], ["pre", "post"])
            for r in recs:
                inp = r["args"]["input"]
                self.assertEqual(sorted(inp), ["content", "file_path"])          # every key kept
                self.assertEqual(inp["file_path"], str(target))                    # path whole
                self.assertEqual(inp["content"], {"truncated": True, "chars": len(content),
                                                  "head": content[:hook.MAX_INPUT_CHARS]})
            self.assertNotIn("SECRET", lg.read_text(encoding="utf-8"))
            steps = rewind.steps(lg)
            self.assertEqual(len(steps), 1)                                        # pre and post paired
            self.assertEqual(steps[0]["result"], {"success": True})
            # rewind restores the bytes from the stored copy, not from the input
            rewind.rewind(lg, 0)
            self.assertEqual(target.read_text(encoding="utf-8"), "old\n")
            # sessions --grep still finds the step by its path; export and bundle/import still work
            hits = sessions.sessions(lg, grep="big.txt")
            self.assertEqual(len(hits), 1)
            page = export.export(lg, out=root / "page.html")
            self.assertLess(page["bytes"], LOG_BOUND * 4)
            self.assertIn("big.txt", (root / "page.html").read_text(encoding="utf-8"))
            with tempfile.TemporaryDirectory() as d2:
                dest = Path(d2).resolve()
                bundle.bundle(lg, root / "s.bundle")
                bundle.import_bundle(root / "s.bundle", dest / ".rewindagents" / "log.jsonl")
                self.assertTrue(log.verify(dest / ".rewindagents" / "log.jsonl")[0])

    def test_claude_write(self):        # checkpointed from the input's file_path
        self.check("claude", "Write")

    def test_droid_create(self):        # scanned before and after; the scan pairs on the whole input
        self.check("droid", "Create")


class ClipInput(unittest.TestCase):
    def test_short_input_unchanged(self):
        inp = {"file_path": "a.py", "old_string": "x", "new_string": "y", "replace_all": False}
        self.assertEqual(hook.clip_input(inp), inp)

    def test_keep_whole_fields_are_never_clipped(self):
        long = "y" * (hook.MAX_INPUT_CHARS + 1)
        inp = {k: long for k in hook.KEEP_WHOLE}
        self.assertEqual(hook.clip_input(inp), inp)

    def test_nested_strings_clipped_keys_kept(self):
        long = "z" * (hook.MAX_INPUT_CHARS + 10)
        inp = {"file_path": "n.ipynb", "edits": [{"old_string": "a", "new_string": long}],
               "meta": {"command": long}}       # only top-level fields are kept whole
        out = hook.clip_input(inp)
        self.assertEqual(out["edits"][0]["old_string"], "a")
        clipped = {"truncated": True, "chars": len(long), "head": long[:hook.MAX_INPUT_CHARS]}
        self.assertEqual(out["edits"][0]["new_string"], clipped)
        self.assertEqual(out["meta"]["command"], clipped)

    def test_input_that_is_a_string(self):
        long = "q" * (hook.MAX_INPUT_CHARS * 2)
        self.assertEqual(hook.clip_input(long)["chars"], len(long))
        self.assertEqual(hook.clip_input("ls"), "ls")

    def test_bound_is_exact(self):
        at = "a" * hook.MAX_INPUT_CHARS
        self.assertEqual(hook.clip_input({"content": at}), {"content": at})
        self.assertTrue(hook.clip_input({"content": at + "a"})["content"]["truncated"])


if __name__ == "__main__":
    unittest.main()
