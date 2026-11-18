"""A torn write: a record cut off before its newline (disk full, process killed mid-write). The recorder must
keep recording after it, keep the fragment where it is (nothing already written is rewritten), and verify must
still name it. Driven through the real hook process where the hook is involved.

Before this fix the next append json-loaded the fragment, raised, and the hook - which never blocks - exited 0
having recorded nothing, for every call from then on.
"""
import hashlib
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
        self.app.write_text("print('v1')\n", newline="", encoding="utf-8")

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
        # encoding="utf-8": Path.write_text()'s own default is the locale-preferred encoding (cp1252 on a
        # default windows-latest run), which cannot even represent this file's multibyte test content
        # (café, 日本) and would raise UnicodeEncodeError instead of writing it.
        self.app.write_text(text, newline="", encoding="utf-8")
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

    # -------------------------------------------------------------------------------- gc frees space anyway
    def stored(self, text):
        """Put a copy nothing names into the store, as a Bash pre-scan leaves an unchanged file; its name."""
        name = hashlib.sha256(text.encode()).hexdigest()
        (self.lp.parent / "objects").mkdir(exist_ok=True)
        (self.lp.parent / "objects" / name).write_text(text, newline="")
        return name

    def objects(self):
        return {p.name for p in (self.lp.parent / "objects").iterdir()}

    def test_gc_frees_space_after_a_torn_write_and_exits_1(self):
        self.write_step("print('v2')\n")
        named = self.objects()                                   # the checkpoint the pre record names
        self.assertTrue(named)
        orphan = self.stored("nobody names me\n")
        self.tear()
        raw = self.lp.read_bytes()
        p = cli(self.d, "gc", "--dry-run")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("would delete 1 stored copies (16 bytes)", p.stdout)
        self.assertIn("note: the log has a torn write (record 3: torn write at the end of the log", p.stdout)
        self.assertEqual(self.objects(), named | {orphan})
        p = cli(self.d, "gc")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("deleted 1 stored copies (16 bytes freed)", p.stdout)
        self.assertIn("torn write", p.stdout)
        self.assertEqual(self.objects(), named)
        self.assertEqual(self.lp.read_bytes(), raw, "gc never writes to the log")
        r = cli(self.d, "rewind", "0")                           # every whole record still rewinds
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(self.app.read_text(), "print('v1')\n")

    def test_gc_keeps_a_copy_only_the_torn_fragment_names(self):
        """A torn pre record may be the only line naming its checkpoint; gc cannot rule out that someone will
        recover it by hand, so every SHA-256 written in a torn line is kept."""
        self.write_step("print('v2')\n")
        frag_only = self.stored("checkpoint of the lost call\n")
        orphan = self.stored("nobody names me\n")
        with self.lp.open("ab") as fh:
            fh.write(('{"args": {"checkpoint": [{"path": "lost.py", "sha256": "%s"}]}, "ev' % frag_only).encode())
        self.assertTrue(log.check(self.lp)[3])
        p = cli(self.d, "gc")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn(frag_only, self.objects())
        self.assertNotIn(orphan, self.objects())

    def test_gc_still_refuses_a_log_damaged_other_than_by_a_torn_write(self):
        self.write_step("print('v2')\n")
        self.write_step("print('v3')\n")
        orphan = self.stored("nobody names me\n")
        lines = self.lp.read_bytes().splitlines()
        lines[1] = lines[1][:40]                                # chain broken, not torn-only
        self.lp.write_bytes(b"\n".join(lines) + b"\n")
        self.assertFalse(log.check(self.lp)[3])
        p = cli(self.d, "gc")
        self.assertEqual(p.returncode, 1)
        self.assertIn("refusing to delete anything", p.stderr)
        self.assertIn(orphan, self.objects())

    def test_bundle_still_refuses_a_torn_log(self):
        """A bundle carries records to another log, which would not show the torn line: the lost call would
        vanish from the record without a trace. So bundle keeps refusing."""
        self.write_step("print('v2')\n")
        self.tear()
        p = cli(self.d, "bundle", "--out", str(self.d / "b.json"))
        self.assertEqual(p.returncode, 1)
        self.assertIn("torn write", p.stderr)
        self.assertFalse((self.d / "b.json").exists())

    # ------------------------------------------------------------------------ import into a torn log
    def source_bundle(self, session="moved"):
        """Session `session`, one Write of lib.py recorded through the real hook in another project, bundled."""
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        src = Path(tmp.name).resolve()
        lib = src / "lib.py"
        lib.write_text("A = 1\n", newline="")
        for when in ("pre", "post"):
            p = payload("claude", src, when, tool="Write", tool_input={"file_path": str(lib), "content": "A = 2\n"})
            p["session_id"] = session
            r = run_hook(json.dumps(p), src, "claude")
            self.assertEqual(r.returncode, 0, r.stderr)
            if when == "pre":
                lib.write_text("A = 2\n", newline="")
        out = src / f"{session}.bundle"
        p = cli(src, "bundle", "--out", str(out))
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return out

    def test_import_adds_to_a_log_whose_only_damage_is_a_torn_write(self):
        """After one torn write a project must still take in a session: the torn line stays where it is (every
        byte before the import unchanged), the imported records chain on from the last whole record, and the
        command says so and exits 1, as rewind/diff/gc do."""
        b = self.source_bundle()
        self.write_step("print('v2')\n")                        # records 1-2, session s-1
        torn = self.tear()                                       # line 3: a fragment, no newline
        p = cli(self.d, "import", str(b))
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("imported session moved: 1 steps, 2 records", p.stdout)
        self.assertIn("note: this log has a torn write (record 3: not a valid record", p.stdout)
        raw = self.lp.read_bytes()
        self.assertTrue(raw.startswith(torn), "bytes already in the log were rewritten")
        self.assertEqual(raw[len(torn):len(torn) + 1], b"\n", "the first imported record must start a new line")
        recs = log.read(self.lp)
        self.assertEqual([(r["seq"], r["session"]) for r in recs], [(1, "s-1"), (2, "s-1"), (4, "moved"), (5, "moved")])
        self.assertEqual(recs[2]["prev"], recs[1]["hash"], "imported records chain to the last whole record")
        ok, n, msg, torn_only = log.check(self.lp)
        self.assertEqual((ok, n, torn_only), (False, 5, True))
        self.assertEqual(msg, "record 3: not a valid record (not JSON, as a torn write leaves; "
                              "the 2 records after it chain on intact)")
        r = cli(self.d, "rewind", "0", "--session", "moved")      # the imported session rewinds here
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual((self.d / "lib.py").read_text(), "A = 1\n")
        self.assertEqual(self.app.read_text(), "print('v2')\n")  # the other session is left alone
        again = cli(self.d, "import", str(b))                     # the session is here now
        self.assertEqual(again.returncode, 1)
        self.assertIn("already holds session 'moved'", again.stderr)

    def test_import_into_a_torn_log_still_runs_every_other_check_first(self):
        b = self.source_bundle()
        self.write_step("print('v2')\n")
        before = self.tear()
        objects = self.objects()
        bad = json.loads(b.read_text())
        bad["records"][0]["result"] = "edited"                    # altered after bundling
        alt = b.with_name("altered.bundle")
        alt.write_text(json.dumps(bad), newline="")
        p = cli(self.d, "import", str(alt))
        self.assertEqual(p.returncode, 1)
        self.assertIn("bundle altered", p.stderr)
        self.assertEqual(self.lp.read_bytes(), before, "nothing may be written when a check fails")
        self.assertEqual(self.objects(), objects)

    def test_import_still_refuses_a_log_damaged_other_than_by_a_torn_write(self):
        b = self.source_bundle()
        self.write_step("print('v2')\n")
        self.write_step("print('v3')\n")
        lines = self.lp.read_bytes().splitlines()
        lines[1] = lines[1][:40]                                # chain broken, not torn-only
        self.lp.write_bytes(b"\n".join(lines) + b"\n")
        before, objects = self.lp.read_bytes(), self.objects()
        self.assertFalse(log.check(self.lp)[3])
        p = cli(self.d, "import", str(b))
        self.assertEqual(p.returncode, 1)
        self.assertIn("this log does not verify (record 3: chain broken", p.stderr)
        self.assertIn("refusing to add to it", p.stderr)
        self.assertEqual(self.lp.read_bytes(), before)
        self.assertEqual(self.objects(), objects)


if __name__ == "__main__":
    unittest.main()
