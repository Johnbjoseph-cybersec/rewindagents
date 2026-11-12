"""`rewindagents status` also reports the project's log: records, the time of the last one, and whether the chain
verifies, so 'hook in place but nothing recorded' shows up next to the hook lines. Read-only."""
import io
import json
import subprocess
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from rewindagents import hook, init, log  # noqa: E402


class StatusLogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        t = Path(self.tmp.name).resolve()
        self.root, self.home = t / "proj", t / "home"
        self.root.mkdir()
        self.home.mkdir()
        self.lp = self.root / ".rewindagents" / "log.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def run_status(self, **kw):
        out = io.StringIO()
        return init.status(root=self.root, home=self.home, out=out, **kw), out.getvalue()

    def log_line(self, out):
        return [l for l in out.splitlines() if l.strip().startswith("log ")][-1]

    def files(self):
        return {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}

    def test_no_log_says_nothing_recorded_exits_0_and_creates_nothing(self):
        code, out = self.run_status()
        self.assertEqual(code, 0, out)
        self.assertEqual(self.log_line(out), "  log      none     .rewindagents/log.jsonl  (nothing recorded yet)")
        self.assertFalse((self.root / ".rewindagents").exists())
        self.assertNotIn("A hook is in place", out)          # no hook either: nothing to warn about

    def test_hook_in_place_and_no_record_is_called_out(self):
        hook.install(self.root / ".claude/settings.json", agent="claude")
        code, out = self.run_status()
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"claude\s+ok\s+")
        self.assertIn("A hook is in place but nothing is recorded yet", out)

    def test_an_empty_log_file_counts_as_nothing_recorded(self):
        self.lp.parent.mkdir()
        self.lp.write_text("")
        code, out = self.run_status()
        self.assertEqual(code, 0, out)
        self.assertIn("(nothing recorded yet)", self.log_line(out))

    def test_records_count_last_time_and_chain_intact(self):
        rec = log.Recorder(self.lp)
        rec.record("s1", "Read", {"file_path": "a"}, ts=1_700_000_000.0)
        rec.record("s1", "Edit", {"file_path": "a"}, ts=1_700_000_123.0)
        hook.install(self.root / ".claude/settings.json", agent="claude")
        before = self.files()
        code, out = self.run_status()
        self.assertEqual(code, 0, out)
        when = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(1_700_000_123.0))
        self.assertEqual(self.log_line(out),
                         f"  log      ok       .rewindagents/log.jsonl  (2 records, last {when}, chain intact)")
        self.assertNotIn("nothing is recorded yet", out)
        self.assertEqual(self.files(), before)

    def test_one_record_is_singular(self):
        log.Recorder(self.lp).record("s1", "Read", {}, ts=1_700_000_000.0)
        self.assertIn("(1 record, last ", self.log_line(self.run_status()[1]))

    def test_an_edited_record_is_broken_and_exits_1(self):
        rec = log.Recorder(self.lp)
        for i in range(3):
            rec.record("s1", "Read", {"i": i})
        lines = self.lp.read_text().splitlines()
        lines[1] = lines[1].replace('"i": 1', '"i": 7')
        self.lp.write_text("\n".join(lines) + "\n")
        before = self.files()
        code, out = self.run_status()
        self.assertEqual(code, 1, out)
        self.assertEqual(self.log_line(out),
                         "  log      BROKEN   .rewindagents/log.jsonl  (record 2: contents altered)")
        self.assertIn("The log does not verify", out)
        self.assertIn("Details: ", out)
        self.assertEqual(self.files(), before)

    def test_a_removed_record_is_broken(self):
        rec = log.Recorder(self.lp)
        for i in range(3):
            rec.record("s1", "Read", {"i": i})
        lines = self.lp.read_text().splitlines()
        self.lp.write_text("\n".join([lines[0], lines[2]]) + "\n")
        code, out = self.run_status()
        self.assertEqual(code, 1, out)
        self.assertIn("record 2: chain broken", self.log_line(out))

    def test_garbage_and_undecodable_logs_are_broken_not_a_crash(self):
        self.lp.parent.mkdir()
        self.lp.write_text("not json\n")
        code, out = self.run_status()
        self.assertEqual(code, 1, out)
        self.assertIn("record 1: not a valid record", self.log_line(out))
        self.lp.write_bytes(b"\xff\xfe\x00junk\n")
        code, out = self.run_status()
        self.assertEqual(code, 1, out)
        self.assertIn("BROKEN", self.log_line(out))
        self.assertIn("cannot be read", self.log_line(out))

    def test_a_stale_hook_and_a_good_log_still_exit_1(self):
        log.Recorder(self.lp).record("s1", "Read", {})
        f = self.root / ".claude/settings.json"
        f.parent.mkdir()
        gone = self.root / "deleted-venv" / "bin" / "python"
        f.write_text(json.dumps({"hooks": {e: [{"matcher": "*", "hooks": [
            {"type": "command", "command": f"{gone} -m rewindagents hook"}]}] for e in ("PreToolUse", "PostToolUse")}}))
        code, out = self.run_status()
        self.assertEqual(code, 1, out)
        self.assertIn("chain intact", self.log_line(out))

    def test_log_path_option_is_honoured_and_named_in_the_fix(self):
        other = self.root / "elsewhere.jsonl"
        log.Recorder(other).record("s1", "Read", {})
        other.write_text(other.read_text().replace('"Read"', '"Edit"'))
        code, out = self.run_status(log_path="elsewhere.jsonl")
        self.assertEqual(code, 1, out)
        self.assertRegex(self.log_line(out), r"log\s+BROKEN\s+elsewhere\.jsonl  ")
        self.assertIn("--log elsewhere.jsonl verify", out)

    def test_cli_status_reads_the_global_log_option(self):
        p = self.root / "custom.jsonl"
        log.Recorder(p).record("s1", "Read", {})
        r = subprocess.run([sys.executable, "-m", "rewindagents", "--log", "custom.jsonl", "status"], cwd=self.root,
                           env={"PYTHONPATH": str(SRC), "HOME": str(self.home), "PATH": "/usr/bin:/bin"},
                           capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(r.stdout, r"log\s+ok\s+custom\.jsonl  \(1 record, last .*, chain intact\)")


if __name__ == "__main__":
    unittest.main()
