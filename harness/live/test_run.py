"""Regression tests for harness/live/run.py and harness/live/validate.py themselves -- not for rewindagents
the product. These guard the defects a reviewer found in this harness:

1. `run._run_isolated` must kill a timed-out child's *whole process group*, not just the one process
   `subprocess.run` would otherwise signal. Reproduced before the fix: a fake agent binary that forked a
   long-sleeping grandchild left that grandchild running as an orphan well after the harness had already
   returned a FAILED/timeout result and moved on to the next agent.
2. `validate.py`'s VERIFIED_LIVE invariant must reject a record that claims VERIFIED_LIVE with every
   `asserted` flag true and `log_records > 0` but an empty `commands` list and a null `scratch_dir` -- the
   exact shape of a hand-edited, fabricated evidence file, as opposed to one this harness actually produced.
3. (sprint-1 gate hygiene finding) `run.py` must scrub this machine's home-directory prefix to "~" in
   `commands`, `scratch_dir`, and `real_config_check["path"]` before writing evidence, and `validate.py`
   must reject any evidence file where that scrub did not happen (a literal "/Users/" or "/home/" segment
   left in one of those three fields).
4. (sprint-2 hygiene finding, HIGH) `validate.py`'s `main()` must actually honor the paths passed to it --
   before the fix it unconditionally re-checked the hardcoded AGENT_KEYS x EVIDENCE_DIR list and ignored
   `argv`/`sys.argv` entirely, so `validate.py <any path(s)>` -- a corrupted scratch copy, a nonexistent
   path, or even `--help --bogus-flag` -- printed "OK" and exited 0 regardless of what was passed, every
   previous `ValidateCatchesFabricatedVerifiedLiveTests` / `ValidateRejectsHomeDirectoryLeakTests` test
   called `validate.validate_one(agent, path)` directly and never exercised `main()` or the CLI at all, so
   none of them could have caught this.

Python standard library only, same convention as run.py/validate.py and the project's own tests/ (unittest).
Not under tests/ -- these test the harness, not the package, and this task's write scope is harness/ and
docs/live-verification.md only.

Run directly:
    PYTHONPATH=src .venv/bin/python -m unittest harness/live/test_run.py -v
or, from anywhere:
    .venv/bin/python harness/live/test_run.py
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

HARNESS_LIVE_DIR = Path(__file__).resolve().parent


def _load(name: str, path: Path):
    """Load run.py / validate.py by file path under a private module name, rather than `import run` /
    `import validate` off sys.path -- those names are generic enough to collide with an unrelated module of
    the same name imported earlier elsewhere in a full-repo test run."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


run = _load("_rewindagents_harness_live_run", HARNESS_LIVE_DIR / "run.py")
validate = _load("_rewindagents_harness_live_validate", HARNESS_LIVE_DIR / "validate.py")

# A disposable test fixture, not a real agent: it forks a long-sleeping grandchild, records that
# grandchild's pid to the file named on argv[1], then hangs itself -- the same shape a real hung agent CLI
# that has backgrounded its own worker would have.
FAKE_AGENT_SOURCE = (
    "import subprocess, sys, time\n"
    "gc = subprocess.Popen(['sleep', '30'])\n"
    "with open(sys.argv[1], 'w') as f:\n"
    "    f.write(str(gc.pid))\n"
    "time.sleep(30)\n"
)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, just owned by someone else -- still alive
    return True


class RunIsolatedNormalPathTests(unittest.TestCase):
    """_run_isolated must still behave like subprocess.run when nothing times out."""

    def test_normal_completion_returns_output_and_exit_code(self):
        r = run._run_isolated([sys.executable, "-c", "print('hi')"], timeout=10)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "hi")

    def test_nonzero_exit_is_not_an_exception(self):
        r = run._run_isolated([sys.executable, "-c", "import sys; sys.exit(3)"], timeout=10)
        self.assertEqual(r.returncode, 3)

    def test_missing_binary_raises_oserror(self):
        with self.assertRaises(OSError):
            run._run_isolated(["/no/such/binary-rewindagents-test"], timeout=10)


class ProcessGroupKillTests(unittest.TestCase):
    """The regression test for the HIGH finding: a timed-out child's whole process group is killed, so a
    descendant it forked does not outlive the harness."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.fake_agent = Path(self.tmp.name) / "fake_agent.py"
        self.fake_agent.write_text(FAKE_AGENT_SOURCE, encoding="utf-8")
        self.pidfile = Path(self.tmp.name) / "grandchild.pid"

    def test_grandchild_is_killed_when_the_top_level_process_times_out(self):
        cmd = [sys.executable, str(self.fake_agent), str(self.pidfile)]
        with self.assertRaises(subprocess.TimeoutExpired):
            run._run_isolated(cmd, timeout=0.5)

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not self.pidfile.exists():
            time.sleep(0.05)
        self.assertTrue(self.pidfile.exists(), "fake agent never recorded its grandchild's pid in time")
        grandchild_pid = int(self.pidfile.read_text().strip())

        # The grandchild was told to sleep 30s; the harness's own timeout above was 0.5s. If the harness
        # only killed the direct child (subprocess.run's default behavior), the grandchild -- forked before
        # the kill and never waited on -- would still be alive here, several seconds later.
        time.sleep(3)
        self.assertFalse(_pid_alive(grandchild_pid),
                          f"grandchild pid {grandchild_pid} survived the harness's process-group kill -- "
                          "the whole group was not actually killed on timeout")


class ValidateCatchesFabricatedVerifiedLiveTests(unittest.TestCase):
    """The regression test for the MEDIUM finding: validate.py must reject a VERIFIED_LIVE record whose
    commands/scratch_dir show no real run ever happened, regardless of what the boolean flags claim."""

    # scratch_dir and real_config_check.path are written here already scrubbed (as run.py's own
    # _scrub_evidence_paths leaves them) -- neither contains a literal "/Users/" or "/home/" segment, so this
    # fixture is the "a real, already-scrubbed run" baseline the home-path-leak tests below are compared
    # against.
    VALID_CLAUDE_RECORD = {
        "agent": "claude", "status": "VERIFIED_LIVE", "agent_version": "2.1.294 (Claude Code)",
        "ran_at": "2026-11-17T20:48:04+00:00", "scratch_dir": "/tmp/rewindagents-live-claude-xxxx",
        "commands": [
            "/usr/local/bin/claude --version",
            "/usr/local/bin/claude -p 'prompt' --permission-mode bypassPermissions "
            "--setting-sources project --output-format json",
        ],
        "log_records": 2,
        "asserted": {"pre_event": True, "post_event": True, "checkpoint_restored": True},
        "notes": "",
        "real_config_check": {"path": "~/.claude/settings.json", "unchanged": True},
    }

    def _check(self, agent: str, data: dict) -> list[str]:
        with TemporaryDirectory() as td:
            path = Path(td) / f"{agent}.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            return validate.validate_one(agent, path)

    def test_a_genuinely_verified_live_record_has_no_violations(self):
        self.assertEqual(self._check("claude", dict(self.VALID_CLAUDE_RECORD)), [])

    def test_fabricated_record_with_empty_commands_and_null_scratch_dir_is_rejected(self):
        """The exact corruption the reviewer applied to a copy of codex.json: VERIFIED_LIVE, log_records=5,
        every asserted flag true, but commands=[], scratch_dir=null, agent_version=null. Before this fix
        validate.py printed 'OK' and exited 0 on this file."""
        fabricated = {
            "agent": "codex", "status": "VERIFIED_LIVE", "agent_version": None,
            "ran_at": "2026-11-17T20:48:21+00:00", "scratch_dir": None, "commands": [],
            "log_records": 5,
            "asserted": {"pre_event": True, "post_event": True, "checkpoint_restored": True},
            "notes": "",
            "real_config_check": {"path": "/home/user/.codex/hooks.json", "unchanged": True},
        }
        problems = self._check("codex", fabricated)
        self.assertTrue(problems, "a VERIFIED_LIVE claim with commands=[] and scratch_dir=null must be "
                                   "rejected -- it is indistinguishable from a hand-edited fabrication")
        joined = " ".join(problems)
        self.assertIn("commands", joined)
        self.assertIn("scratch_dir", joined)

    def test_verified_live_whose_commands_never_mention_the_agents_own_binary_is_rejected(self):
        suspicious = dict(self.VALID_CLAUDE_RECORD)
        # deliberately contains no substring "claude" anywhere -- only the internal `rewindagents` commands,
        # never the agent's own binary
        suspicious["commands"] = ["/usr/bin/python3 -m rewindagents rewind 0 --dry-run"]
        problems = self._check("claude", suspicious)
        self.assertTrue(problems, "a VERIFIED_LIVE claim whose commands never invoke the claude binary "
                                   "itself must be rejected")
        self.assertTrue(any("own binary" in p for p in problems), problems)

    def test_missing_real_config_check_field_is_rejected(self):
        incomplete = dict(self.VALID_CLAUDE_RECORD)
        del incomplete["real_config_check"]
        problems = self._check("claude", incomplete)
        self.assertTrue(problems, "a record missing 'real_config_check' entirely must be rejected")
        self.assertTrue(any("real_config_check" in p for p in problems), problems)

    def test_real_config_check_with_wrong_shape_is_rejected(self):
        malformed = dict(self.VALID_CLAUDE_RECORD)
        malformed["real_config_check"] = {"path": "/home/user/.claude/settings.json"}  # missing "unchanged"
        problems = self._check("claude", malformed)
        self.assertTrue(problems, "a 'real_config_check' missing 'unchanged' must be rejected")
        self.assertTrue(any("real_config_check" in p for p in problems), problems)


class ScrubHomeTests(unittest.TestCase):
    """Unit tests for run.py's own scrub helpers (sprint-1 gate hygiene finding: an evidence file must
    never embed this machine's real username in an absolute path)."""

    def test_scrub_home_replaces_the_home_prefix_with_tilde(self):
        home = os.path.expanduser("~")
        self.assertEqual(run._scrub_home(f"{home}/.claude/settings.json"), "~/.claude/settings.json")
        self.assertEqual(
            run._scrub_home(f"PYTHONPATH={home}/fire/rewindagent/src {home}/fire/rewindagent/.venv/bin/python"),
            "PYTHONPATH=~/fire/rewindagent/src ~/fire/rewindagent/.venv/bin/python",
        )

    def test_scrub_home_leaves_non_home_paths_and_none_untouched(self):
        self.assertEqual(run._scrub_home("/var/folders/xx/tmp-scratch"), "/var/folders/xx/tmp-scratch")
        self.assertIsNone(run._scrub_home(None))

    def test_scrub_evidence_paths_covers_commands_scratch_dir_and_real_config_check_path_only(self):
        home = os.path.expanduser("~")
        raw = {
            "agent": "claude", "status": "VERIFIED_LIVE", "agent_version": "2.1.294 (Claude Code)",
            "ran_at": "2026-11-17T21:50:07+00:00",
            "scratch_dir": "/var/folders/pl/tmp/rewindagents-live-claude-iw4gw_oh",
            "commands": [f"{home}/.local/bin/claude --version"],
            "log_records": 2, "notes": "",
            "asserted": {"pre_event": True, "post_event": True, "checkpoint_restored": True},
            "real_config_check": {"path": f"{home}/.claude/settings.json", "unchanged": True},
        }
        scrubbed = run._scrub_evidence_paths(raw)
        self.assertEqual(scrubbed["commands"], ["~/.local/bin/claude --version"])
        self.assertEqual(scrubbed["real_config_check"]["path"], "~/.claude/settings.json")
        # a non-home path (the tempfile.mkdtemp() default, under /var/folders on macOS) is left alone
        self.assertEqual(scrubbed["scratch_dir"], "/var/folders/pl/tmp/rewindagents-live-claude-iw4gw_oh")
        # every other field, including the nested real_config_check["unchanged"], passes through unchanged
        for field in ("agent", "status", "agent_version", "ran_at", "log_records", "notes", "asserted"):
            self.assertEqual(scrubbed[field], raw[field], field)
        self.assertEqual(scrubbed["real_config_check"]["unchanged"], True)

    def test_write_evidence_scrubs_before_touching_disk(self):
        home = os.path.expanduser("~")
        data = {
            "agent": "claude", "status": "NOT_INSTALLED", "agent_version": None,
            "ran_at": "2026-11-17T21:50:07+00:00", "scratch_dir": None,
            "commands": [f"{home}/.local/bin/claude --version"],
            "log_records": 0, "notes": "", "asserted": no_asserted(),
            "real_config_check": {"path": f"{home}/.claude/settings.json", "unchanged": True},
        }
        original_evidence_dir = run.EVIDENCE_DIR
        with TemporaryDirectory() as td:
            run.EVIDENCE_DIR = Path(td)
            try:
                path = run._write_evidence(data)
                text = path.read_text(encoding="utf-8")
            finally:
                run.EVIDENCE_DIR = original_evidence_dir
        self.assertNotIn(home, text)
        self.assertIn("~/.local/bin/claude --version", text)
        self.assertIn("~/.claude/settings.json", text)


def no_asserted() -> dict[str, bool]:
    return {"pre_event": False, "post_event": False, "checkpoint_restored": False}


class ValidateRejectsHomeDirectoryLeakTests(unittest.TestCase):
    """The regression test for the sprint-1 gate hygiene finding: validate.py must reject an evidence file
    whose commands/scratch_dir/real_config_check.path still carry a literal '/Users/' or '/home/' segment --
    the shape every evidence file had before run.py was taught to scrub them."""

    BASE = dict(ValidateCatchesFabricatedVerifiedLiveTests.VALID_CLAUDE_RECORD)

    def _check(self, agent: str, data: dict) -> list[str]:
        with TemporaryDirectory() as td:
            path = Path(td) / f"{agent}.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            return validate.validate_one(agent, path)

    def test_leak_in_real_config_check_path_is_rejected(self):
        leaking = dict(self.BASE)
        leaking["real_config_check"] = {"path": "/Users/alice/.claude/settings.json", "unchanged": True}
        problems = self._check("claude", leaking)
        self.assertTrue(problems, "a real_config_check.path containing '/Users/' must be rejected")
        self.assertTrue(any("real_config_check.path" in p for p in problems), problems)

    def test_leak_in_commands_is_rejected(self):
        leaking = dict(self.BASE)
        leaking["commands"] = ["/Users/alice/.local/bin/claude --version"]
        problems = self._check("claude", leaking)
        self.assertTrue(problems, "a commands entry containing '/Users/' must be rejected")
        self.assertTrue(any("'commands'" in p or "home-directory path" in p for p in problems), problems)

    def test_leak_in_scratch_dir_is_rejected(self):
        leaking = dict(self.BASE)
        leaking["scratch_dir"] = "/home/alice/tmp/rewindagents-live-claude-xxxx"
        problems = self._check("claude", leaking)
        self.assertTrue(problems, "a scratch_dir containing '/home/' must be rejected")
        self.assertTrue(any("scratch_dir" in p for p in problems), problems)

    def test_scrubbed_tilde_path_has_no_home_leak_violation(self):
        clean = dict(self.BASE)
        clean["real_config_check"] = {"path": "~/.claude/settings.json", "unchanged": True}
        problems = self._check("claude", clean)
        self.assertEqual(problems, [], "a '~'-scrubbed path must never be flagged as a home-directory leak")


class ValidateMainHonorsArgvTests(unittest.TestCase):
    """The regression test for the sprint-2 HIGH finding: `validate.py`'s `main()` must validate exactly
    the paths it is given on the command line, instead of silently re-checking the hardcoded
    AGENT_KEYS x EVIDENCE_DIR list no matter what was passed. Before the fix, every one of these scenarios
    printed the byte-identical 'OK: 7 agent evidence files all valid' and returned 0 -- demonstrated by the
    reviewer with a corrupted scratch copy of claude.json, and reproduced here the same way: write a copy
    of a valid record to a throwaway directory, re-insert a literal absolute home-directory path, and pass
    that file's path to `main()` (or to the script as a real subprocess) -- it must now report a VIOLATION
    naming the leaking field and exit 1."""

    VALID_CLAUDE_RECORD = ValidateCatchesFabricatedVerifiedLiveTests.VALID_CLAUDE_RECORD

    @staticmethod
    def _write(dirpath: Path, filename: str, data: dict) -> Path:
        path = dirpath / filename
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_main_rejects_a_scratch_copy_with_a_reinserted_absolute_path(self):
        """The reviewer's exact repro: a scratch copy of claude.json with an absolute '/Users/...' path
        reinserted into scratch_dir. Before the fix this printed 'OK' and returned 0 no matter what path
        was passed; the file name is unchanged ('claude.json') so only the leak itself is under test."""
        with TemporaryDirectory() as td:
            corrupted = dict(self.VALID_CLAUDE_RECORD)
            corrupted["scratch_dir"] = "/Users/someone/scratchdir-evil"
            path = self._write(Path(td), "claude.json", corrupted)

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = validate.main([str(path)])
        self.assertEqual(rc, 1, "a leaking evidence file passed on the command line must exit 1")
        output = buf.getvalue()
        self.assertIn("VIOLATION", output)
        self.assertIn("scratch_dir", output)

    def test_main_accepts_a_genuinely_clean_file_passed_as_an_argument(self):
        """The positive case: a file that really is clean, passed explicitly, must still pass -- this is
        the shape of the campaign's own acceptance command, `validate.py harness/live/evidence/*.json`."""
        with TemporaryDirectory() as td:
            path = self._write(Path(td), "claude.json", dict(self.VALID_CLAUDE_RECORD))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = validate.main([str(path)])
        self.assertEqual(rc, 0)
        self.assertIn("OK", buf.getvalue())

    def test_main_does_not_silently_ignore_a_nonexistent_path(self):
        """One of the reviewer's other repro shapes: a path that does not exist at all must not be
        silently dropped in favor of the hardcoded default list."""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = validate.main(["/no/such/path-rewindagents-test.json"])
        self.assertEqual(rc, 1, "a nonexistent path passed on the command line must not be silently ignored")
        self.assertIn("missing evidence file", buf.getvalue())

    def test_cli_subprocess_rejects_the_leaking_copy_and_exits_1(self):
        """Runs the real script as a subprocess (`python harness/live/validate.py <path>`), the same way
        the campaign's acceptance command and the reviewer's own repro invoke it -- this exercises the
        actual `if __name__ == '__main__': sys.exit(main())` entry point, not only the imported function."""
        with TemporaryDirectory() as td:
            corrupted = dict(self.VALID_CLAUDE_RECORD)
            corrupted["real_config_check"] = {"path": "/home/someone/.claude/settings.json",
                                               "unchanged": True}
            path = self._write(Path(td), "claude.json", corrupted)
            env = dict(os.environ)
            repo_root = HARNESS_LIVE_DIR.parents[1]
            env["PYTHONPATH"] = str(repo_root / "src")
            r = subprocess.run([sys.executable, str(HARNESS_LIVE_DIR / "validate.py"), str(path)],
                                capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("VIOLATION", r.stdout)
        self.assertIn("real_config_check.path", r.stdout)


if __name__ == "__main__":
    unittest.main()
