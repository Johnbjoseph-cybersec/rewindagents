import io
import json
import multiprocessing as mp
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rewindagents import GENESIS, Recorder, head, read, verify  # noqa: E402
from rewindagents.cli import main  # noqa: E402


def _write_many(path, worker, count):
    rec = Recorder(path)
    for i in range(count):
        rec.record(f"s{worker}", "Bash", {"command": f"echo {worker}-{i}"})


class LogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.path = Path(self.tmp.name) / "log.jsonl"
        r = Recorder(self.path)
        r.record("s1", "Bash", {"command": "ls"}, {"exit": 0})
        r.record("s1", "Edit", {"file": "a.py"}, "ok")
        r.record("s2", "Bash", {"command": "rm -rf build"}, {"exit": 0})

    def tearDown(self):
        self.tmp.cleanup()

    def lines(self):
        return self.path.read_text().splitlines()

    def write(self, lines):
        self.path.write_text("\n".join(lines) + "\n")

    def test_intact_chain_verifies(self):
        self.assertEqual(verify(self.path), (True, 3, "chain intact"))

    def test_first_record_links_to_genesis(self):
        self.assertEqual(json.loads(self.lines()[0])["prev"], GENESIS)

    def test_edited_args_detected(self):
        lines = self.lines()
        lines[1] = lines[1].replace("a.py", "b.py")
        self.write(lines)
        ok, n, msg = verify(self.path)
        self.assertFalse(ok)
        self.assertEqual(n, 2)
        self.assertIn("altered", msg)

    def test_deleted_middle_record_detected(self):
        lines = self.lines()
        del lines[1]
        self.write(lines)
        ok, n, _ = verify(self.path)
        self.assertFalse(ok)
        self.assertEqual(n, 2)

    def test_reordered_records_detected(self):
        lines = self.lines()
        lines[1], lines[2] = lines[2], lines[1]
        self.write(lines)
        self.assertFalse(verify(self.path)[0])

    def test_rehashed_forgery_still_breaks_next_link(self):
        lines = self.lines()
        rec = json.loads(lines[0])
        rec["args"] = {"command": "pwd"}
        rec.pop("hash")
        from rewindagents.log import _digest
        rec["hash"] = _digest(rec)
        lines[0] = json.dumps(rec, sort_keys=True)
        self.write(lines)
        ok, n, msg = verify(self.path)
        self.assertFalse(ok)
        self.assertEqual(n, 2)
        self.assertIn("chain broken", msg)

    def test_truncated_tail_caught_only_with_pinned_head(self):
        pinned = head(self.path)
        self.write(self.lines()[:2])
        self.assertTrue(verify(self.path)[0])
        ok, _, msg = verify(self.path, expected_head=pinned)
        self.assertFalse(ok)
        self.assertIn("head", msg)

    def test_garbage_line_detected(self):
        self.write(self.lines() + ["not json"])
        ok, n, _ = verify(self.path)
        self.assertFalse(ok)
        self.assertEqual(n, 4)

    def test_new_recorder_continues_existing_chain(self):
        Recorder(self.path).record("s3", "Read", {"file": "x"})
        self.assertEqual(verify(self.path), (True, 4, "chain intact"))

    def test_read_filters_by_session(self):
        self.assertEqual([r["tool"] for r in read(self.path, "s1")], ["Bash", "Edit"])

    def test_concurrent_writers_keep_one_chain(self):
        procs = [mp.Process(target=_write_many, args=(self.path, w, 25)) for w in range(4)]
        for p in procs:
            p.start()
        for p in procs:
            p.join()
        self.assertEqual(verify(self.path), (True, 103, "chain intact"))


class CliTest(unittest.TestCase):
    def run_cli(self, *argv, stdin=""):
        out = io.StringIO()
        old = sys.stdin
        sys.stdin = io.StringIO(stdin)
        try:
            with redirect_stdout(out):
                code = main(list(argv))
        finally:
            sys.stdin = old
        return code, out.getvalue()

    def test_record_verify_show_head(self):
        with TemporaryDirectory() as d:
            lg = str(Path(d) / "l.jsonl")
            code, h = self.run_cli("--log", lg, "record", "--session", "s1",
                                   stdin=json.dumps({"tool": "Bash", "args": {"command": "ls"}}))
            self.assertEqual(code, 0)
            self.assertEqual(self.run_cli("--log", lg, "head")[1].strip(), h.strip())
            self.assertEqual(self.run_cli("--log", lg, "verify"), (0, "OK: 1 records, chain intact\n"))
            self.assertIn('Bash  {"command": "ls"}', self.run_cli("--log", lg, "show")[1])
            code, out = self.run_cli("--log", lg, "verify", "--head", "f" * 64)
            self.assertEqual(code, 1)
            self.assertTrue(out.startswith("TAMPERED"))

    def test_missing_log_is_an_error_not_a_crash(self):
        with TemporaryDirectory() as d:
            lg = str(Path(d) / "none.jsonl")
            self.assertEqual(self.run_cli("--log", lg, "verify")[0], 2)
            self.assertEqual(self.run_cli("--log", lg, "show")[0], 2)

    def test_record_rejects_bad_stdin(self):
        with TemporaryDirectory() as d:
            lg = str(Path(d) / "l.jsonl")
            self.assertEqual(self.run_cli("--log", lg, "record", "--session", "s", stdin="nope")[0], 2)
            self.assertEqual(self.run_cli("--log", lg, "record", "--session", "s", stdin="{}")[0], 2)
            self.assertFalse(Path(lg).exists())


if __name__ == "__main__":
    unittest.main()
