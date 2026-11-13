"""A torn write: a record cut off before its newline (disk full, process killed mid-write). The recorder must
keep recording after it, keep the fragment where it is (nothing already written is rewritten), and verify must
still name it. Driven through the real hook process where the hook is involved.

Before this fix the next append json-loaded the fragment, raised, and the hook - which never blocks - exited 0
having recorded nothing, for every call from then on.
"""
import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from rewindagents import init, log  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_hook_hardening import payload, reply, run_hook  # noqa: E402


def cli(cwd, *argv):
    env = dict(os.environ, PYTHONPATH=str(SRC))
    return subprocess.run([sys.executable, "-m", "rewindagents", *argv], capture_output=True, text=True,
                          cwd=cwd, env=env, timeout=120)


class TornWrite(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.d = Path(self.tmp.name).resolve()
        self.lp = self.d / ".rewindagents" / "log.jsonl"
        self.app = self.d / "app.py"
        self.app.write_text("print('v1')\n")

    def tearDown(self):
        self.tmp.cleanup()

    def hook(self, when, **kw):
        p = run_hook(json.dumps(payload("claude", self.d, when, **kw)), self.d, "claude")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout, reply("claude", payload("claude", self.d, when)["hook_event_name"]))
        self.assertNotIn(b"Traceback", p.stdout + p.stderr)
        return p

    def write_step(self, text):
        """One Write of app.py through the real hook: pre (checkpoint), the write, post."""
        args = {"tool": "Write", "tool_input": {"file_path": str(self.app), "content": text}}
        self.hook("pre", **args)
        self.app.write_text(text)
        self.hook("post", **args)

    def tear(self, cut=0.5):
        """Append the first `cut` of a would-be record, with no newline, as a cut-off write leaves it."""
        whole = self.lp.read_bytes().splitlines()[-1]
        frag = whole[: int(len(whole) * cut)]
        with self.lp.open("ab") as fh:
            fh.write(frag)
        return self.lp.read_bytes()

    # -------------------------------------------------------------------------------- recording goes on
    def test_hook_keeps_recording_after_a_torn_tail_and_keeps_the_fragment(self):
        self.write_step("print('v2')\n")                       # records 1-2
        torn = self.tear()                                      # line 3: a fragment
        self.write_step("print('v3')\n")                       # records 4-5
        raw = self.lp.read_bytes()
        self.assertTrue(raw.startswith(torn), "bytes already in the log were rewritten")
        self.assertEqual(raw[len(torn):len(torn) + 1], b"\n", "the next record must start on a line of its own")
        self.assertTrue(raw.endswith(b"\n"))
        self.assertEqual([r["seq"] for r in log.read(self.lp)], [1, 2, 4, 5])   # the fragment keeps number 3
        ok, n, msg, torn_only = log.check(self.lp)
        self.assertEqual((ok, n, torn_only), (False, 5, True))
        self.assertEqual(msg, "record 3: not a valid record (not JSON, as a torn write leaves; "
                              "the 2 records after it chain on intact)")
        self.assertEqual(log.head(self.lp), log.read(self.lp)[-1]["hash"])

    def test_cut_inside_a_multibyte_character(self):
        self.write_step("print('café → 日本')\n")
        whole = self.lp.read_bytes().splitlines()[-1]
        i = whole.index("日".encode()) + 1                   # inside the 3-byte character
        with self.lp.open("ab") as fh:
            fh.write(whole[:i])
        self.write_step("print('v3')\n")
        self.assertEqual(len(log.read(self.lp)), 4)
        self.assertTrue(log.check(self.lp)[3])

    def test_a_whole_record_that_only_lost_its_newline_is_kept_as_a_record(self):
        self.write_step("print('v2')\n")
        self.lp.write_bytes(self.lp.read_bytes()[:-1])         # cut exactly before the newline
        self.write_step("print('v3')\n")
        self.assertEqual(log.verify(self.lp), (True, 4, "chain intact"))

    def test_record_and_newline_go_out_in_one_write(self):
        rec = log.Recorder(self.lp)
        rec.record("s", "Read", {"file_path": "a"})
        real, calls = os.write, []

        def spy(fd, data):
            calls.append(bytes(data))
            return real(fd, data)
        with mock.patch.object(log.os, "write", spy):
            body = rec.record("s", "Read", {"file_path": "b" * 5000})
        self.assertEqual(len(calls), 1, "a record must be one write, so a cut leaves at most one torn line")
        self.assertTrue(calls[0].endswith(b"\n"))
        self.assertEqual(json.loads(calls[0]), body)

    # -------------------------------------------------------------------------------- verify names it
    def test_a_lone_torn_tail_is_named_as_such(self):
        self.write_step("print('v2')\n")
        self.tear()
        ok, n, msg, torn_only = log.check(self.lp)
        self.assertEqual((ok, n, torn_only), (False, 3, True))
        self.assertEqual(msg, "record 3: torn write at the end of the log (cut off before its newline; "
                              "the 2 records before it verify)")
        p = cli(self.d, "verify")
        self.assertEqual(p.returncode, 1)
        self.assertIn("torn write at the end of the log", p.stdout)

    def test_status_names_the_torn_write_and_exits_1(self):
        self.write_step("print('v2')\n")
        self.tear()
        out = io.StringIO()
        code = init.status(root=self.d, home=self.d / "home", out=out)
        self.assertEqual(code, 1, out.getvalue())
        line = [l for l in out.getvalue().splitlines() if l.strip().startswith("log ")][-1]
        self.assertIn("BROKEN", line)
        self.assertIn("record 3: torn write at the end of the log", line)

    def test_json_that_is_not_a_record_still_stops_the_check(self):
        self.write_step("print('v2')\n")
        lines = self.lp.read_bytes().splitlines()
        self.lp.write_bytes(b"\n".join([lines[0], b'{"x": 1}', lines[1]]) + b"\n")
        self.assertEqual(log.check(self.lp), (False, 2, "record 2: not a valid record", False))

    def test_a_record_replaced_by_garbage_breaks_the_chain(self):
        self.write_step("print('v2')\n")
        self.write_step("print('v3')\n")
        lines = self.lp.read_bytes().splitlines()
        lines[1] = lines[1][:40]                                # record 2 swapped for a fragment
        self.lp.write_bytes(b"\n".join(lines) + b"\n")
        ok, n, msg, torn_only = log.check(self.lp)
        self.assertEqual((ok, n, torn_only), (False, 3, False))
        self.assertIn("record 3: chain broken", msg)

    # -------------------------------------------------------------------------------- undo still works
    def test_rewind_after_a_torn_write_restores_and_says_why_it_exits_1(self):
        self.write_step("print('v2')\n")
        self.tear()
        p = cli(self.d, "rewind", "0")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertEqual(self.app.read_text(), "print('v1')\n")
        self.assertIn("note: the log has a torn write (record 3: torn write at the end of the log", p.stdout)
        d = cli(self.d, "diff", "0")
        self.assertEqual(d.returncode, 1)
        self.assertIn("torn write", d.stderr)

    def test_gc_and_bundle_still_refuse_a_log_that_does_not_verify(self):
        self.write_step("print('v2')\n")
        self.tear()
        for argv in (("gc", "--dry-run"), ("bundle", "--out", str(self.d / "b.json"))):
            p = cli(self.d, *argv)
            self.assertNotEqual(p.returncode, 0, argv)
            self.assertIn("torn write", p.stdout + p.stderr, argv)


if __name__ == "__main__":
    unittest.main()
