"""The five --json shapes (jsonout.py), and the CLI flags that print them: sessions, summary, diff and
replay take a plain --json; rewind takes --dry-run --json (a real rewind is not available as JSON on the
CLI -- see mcp.py's rewind_to_step for that). Every case here checks the shape against the contract in
the campaign brief, not just that *some* JSON came out.
"""
import json
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rewindagents import jsonout, rewind, revert  # noqa: E402
from test_rewind import Agent, cli  # noqa: E402


# a key-shaped test value built from pieces, so no key-shaped string sits in the repository
FAKE_KEY = "sk-" + "ant-" + 'abcdefghijklmnopqrstuvwxyz'


def one_object(stdout: str) -> dict:
    """stdout must be exactly one JSON object and nothing else -- the whole point of --json."""
    lines = [l for l in stdout.splitlines() if l.strip()]
    assert len(lines) == 1, f"expected exactly one line of JSON, got {len(lines)}: {stdout!r}"
    obj = json.loads(lines[0])
    assert isinstance(obj, dict)
    return obj


class TestSessionsPayload(unittest.TestCase):
    def test_shape(self):
        with TemporaryDirectory() as d:
            a = Agent(d, "s1")
            a.write("a.py", "1\n")
            a.bash("pytest")
            payload = jsonout.sessions_payload(a.log)
            self.assertEqual(payload["format"], "rewindagents-sessions")
            self.assertEqual(payload["version"], 1)
            self.assertEqual(len(payload["sessions"]), 1)
            e = payload["sessions"][0]
            self.assertEqual(e, {"session": "s1", "steps": 2,
                                  "first_ts": e["first_ts"], "last_ts": e["last_ts"]})
            for key in ("first_ts", "last_ts"):
                self.assertRegex(e[key], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")

    def test_grep_filters_the_same_way_as_the_text_command(self):
        with TemporaryDirectory() as d:
            Agent(d, "one").write("keep.py", "1\n")
            Agent(d, "two").write("drop.py", "1\n")
            payload = jsonout.sessions_payload(Agent(d).log, grep="keep")
            self.assertEqual([e["session"] for e in payload["sessions"]], ["one"])

    def test_cli_json_is_one_object_and_matches_the_function(self):
        with TemporaryDirectory() as d:
            os.chdir(d)
            try:
                a = Agent(d, "s1")
                a.write("a.py", "1\n")
                code, out, err = cli("sessions", "--json")
                self.assertEqual(code, 0, err)
                self.assertEqual(one_object(out), jsonout.sessions_payload(a.log))
            finally:
                os.chdir(Path(d).parent)

    def test_cli_json_grep_no_match_exits_1(self):
        with TemporaryDirectory() as d:
            os.chdir(d)
            try:
                Agent(d, "s1").write("a.py", "1\n")
                code, out, err = cli("sessions", "--grep", "nope", "--json")
                self.assertEqual(code, 1)
                self.assertEqual(one_object(out)["sessions"], [])
            finally:
                os.chdir(Path(d).parent)


class TestSummaryPayload(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.a = Agent(self.d, "s1")
        self.a.write("app.py", "v1")      # step 1
        self.a.bash("pytest")             # step 2

    def tearDown(self):
        self.tmp.cleanup()

    def test_shape_and_content(self):
        payload = jsonout.summary_payload(self.a.log)
        self.assertEqual(payload["format"], "rewindagents-summary")
        self.assertEqual(payload["version"], 1)
        self.assertEqual(payload["session"], "s1")
        self.assertEqual(len(payload["steps"]), 2)
        s1 = payload["steps"][0]
        self.assertEqual(s1["tool"], "Write")
        self.assertEqual(s1["actor"], "agent")
        self.assertEqual(s1["event"], "pre")
        self.assertEqual(s1["files"], ["app.py"])
        self.assertEqual(set(s1), {"seq", "ts", "actor", "event", "tool", "files"})
        self.assertEqual(payload["steps"][1]["tool"], "Bash")

    def test_default_session_is_the_latest(self):
        Agent(self.d, "later").write("other.py", "x")
        payload = jsonout.summary_payload(self.a.log)
        self.assertEqual(payload["session"], "later")

    def test_cli_json_matches_the_function(self):
        os.chdir(self.d)
        try:
            code, out, err = cli("summary", "--json")
            self.assertEqual(code, 0, err)
            self.assertEqual(one_object(out), jsonout.summary_payload(self.a.log, "s1"))
        finally:
            os.chdir(self.d.parent)

    def test_cli_json_unknown_session_is_an_error_before_jsonout_ever_runs(self):
        os.chdir(self.d)
        try:
            code, out, err = cli("summary", "--session", "no-such-session", "--json")
            self.assertEqual(code, 1)
            self.assertEqual(out, "")                 # SessionError is caught in main(), not printed as JSON
            self.assertIn("no session", err)
        finally:
            os.chdir(self.d.parent)


class TestDiffPayload(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.a = Agent(self.d, "s1")
        self.a.write("app.py", "v1")        # step 1
        self.a.write("app.py", "v2")        # step 2
        self.a.write("new.py", "junk")      # step 3: creates a file

    def tearDown(self):
        self.tmp.cleanup()

    def test_modified_file(self):
        payload, p = jsonout.diff_payload(self.a.log, 1)
        self.assertEqual(payload["format"], "rewindagents-diff")
        self.assertEqual(payload["session"], "s1")
        self.assertEqual(payload["step"], 1)
        by_path = {f["path"]: f for f in payload["files"]}
        self.assertEqual(by_path["app.py"]["change"], "modified")
        self.assertIn("-v2", by_path["app.py"]["unified"])
        self.assertIn("+v1", by_path["app.py"]["unified"])
        self.assertEqual(by_path["new.py"]["change"], "deleted")
        self.assertEqual(jsonout.diff_exit_code(p), 0)

    def test_created_file_when_the_target_step_is_before_a_delete(self):
        (self.d / "app.py").unlink()        # app.py missing now; step 1 would restore it
        payload, _ = jsonout.diff_payload(self.a.log, 1)
        by_path = {f["path"]: f for f in payload["files"]}
        self.assertEqual(by_path["app.py"]["change"], "created")

    def test_step_range_error_matches_other_commands_exit_2(self):
        with self.assertRaises(rewind.StepRangeError):
            jsonout.diff_payload(self.a.log, 99)

    def test_diff_is_never_redacted_under_json_either(self):
        # diff_payload's own default (redact_secrets=False, matching the plain `diff` command, which
        # has no --no-redact flag because it has nothing to turn off). This is the CLI-facing default
        # this test guards; the MCP rewind_diff tool is a different caller with its own, opposite
        # default -- see test_redact_secrets_true_redacts_the_unified_diff_text below and test_mcp.py.
        self.a.write(".env", "API_KEY=" + FAKE_KEY)
        payload, _ = jsonout.diff_payload(self.a.log, 3)
        by_path = {f["path"]: f for f in payload["files"]}
        self.assertIn("API_KEY=" + FAKE_KEY, by_path[".env"]["unified"])

    def test_redact_secrets_true_redacts_the_unified_diff_text(self):
        # the explicit opt-in mcp.py's rewind_diff tool uses by default (redact_secrets=True); the
        # shape is otherwise identical -- same files, same "change", only "unified" differs.
        self.a.write(".env", "API_KEY=" + FAKE_KEY)
        payload, _ = jsonout.diff_payload(self.a.log, 3, redact_secrets=True)
        by_path = {f["path"]: f for f in payload["files"]}
        self.assertNotIn(FAKE_KEY, by_path[".env"]["unified"])
        self.assertIn("[redacted", by_path[".env"]["unified"])
        self.assertEqual(by_path[".env"]["change"], "deleted")

    def test_cli_json_diff_still_never_redacted_with_a_secret_present(self):
        # locks in that this sprint's MCP-only redaction default never reached the CLI: cli.py's
        # _diff_json calls jsonout.diff_payload with no redact_secrets argument at all.
        self.a.write(".env", "API_KEY=" + FAKE_KEY)
        os.chdir(self.d)
        try:
            code, out, err = cli("diff", "3", "--json")
            self.assertEqual(code, 0, err)
            by_path = {f["path"]: f for f in one_object(out)["files"]}
            self.assertIn(FAKE_KEY, by_path[".env"]["unified"])
        finally:
            os.chdir(self.d.parent)

    def test_cli_json_matches_the_function_and_prints_only_one_object(self):
        os.chdir(self.d)
        try:
            code, out, err = cli("diff", "1", "--json")
            self.assertEqual(code, 0, err)
            payload, _ = jsonout.diff_payload(self.a.log, 1, "s1")
            self.assertEqual(one_object(out), payload)
        finally:
            os.chdir(self.d.parent)

    def test_cli_json_step_out_of_range_exits_2_with_error_shape(self):
        os.chdir(self.d)
        try:
            code, out, err = cli("diff", "99", "--json")
            self.assertEqual(code, 2)
            obj = one_object(out)
            self.assertEqual(obj["format"], "rewindagents-error")
            self.assertIn("out of range", obj["error"])
        finally:
            os.chdir(self.d.parent)


class TestDiffExitCode(unittest.TestCase):
    def test_drift_alone_fails(self):
        self.assertEqual(jsonout.diff_exit_code({"cannot": [], "bash_uncovered": 0, "scan_early": 0,
                                                 "drift": [{"path": "x"}], "torn": None}), 1)

    def test_nothing_wrong_passes(self):
        self.assertEqual(jsonout.diff_exit_code({"cannot": [], "bash_uncovered": 0, "scan_early": 0,
                                                 "drift": [], "torn": None}), 0)

    def test_cannot_fails(self):
        self.assertEqual(jsonout.diff_exit_code({"cannot": [("x", "why")], "bash_uncovered": 0, "scan_early": 0,
                                                 "drift": [], "torn": None}), 1)

    def test_torn_fails(self):
        self.assertEqual(jsonout.diff_exit_code({"cannot": [], "bash_uncovered": 0, "scan_early": 0,
                                                 "drift": [], "torn": "message"}), 1)


class TestRewindDryRunExitCode(unittest.TestCase):
    CLEAN = {"cannot": [], "bash_uncovered": 0, "scan_early": 0, "torn": None}

    def test_no_drift_no_force_passes(self):
        self.assertEqual(jsonout.rewind_dry_run_exit_code({**self.CLEAN, "drift": []}, force=False), 0)

    def test_drift_without_force_fails(self):
        self.assertEqual(jsonout.rewind_dry_run_exit_code({**self.CLEAN, "drift": [{"path": "x"}]}, force=False), 1)

    def test_drift_with_force_passes(self):
        # a real --force rewind would proceed despite the drift; the dry-run preview says so, not 1
        self.assertEqual(jsonout.rewind_dry_run_exit_code({**self.CLEAN, "drift": [{"path": "x"}]}, force=True), 0)

    def test_cannot_fails_even_with_no_drift(self):
        p = {**self.CLEAN, "drift": [], "cannot": [("x", "why")]}
        self.assertEqual(jsonout.rewind_dry_run_exit_code(p, force=False), 1)


class TestReplayPayload(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.a = Agent(self.d, "s1")
        self.a.write("app.py", "v1")       # step 1
        self.a.bash("pytest")              # step 2

    def tearDown(self):
        self.tmp.cleanup()

    def test_full_list_shape(self):
        payload = jsonout.replay_payload(self.a.log)
        self.assertEqual(payload["format"], "rewindagents-replay")
        self.assertEqual(payload["session"], "s1")
        self.assertEqual(len(payload["steps"]), 2)
        s1 = payload["steps"][0]
        self.assertEqual(set(s1), {"seq", "ts", "actor", "event", "tool", "files", "result"})
        self.assertIsInstance(s1["result"], str)
        self.assertEqual(json.loads(s1["result"]), {"ok": True})

    def test_single_step_selection(self):
        payload = jsonout.replay_payload(self.a.log, step=2)
        self.assertEqual(len(payload["steps"]), 1)
        self.assertEqual(payload["steps"][0]["tool"], "Bash")

    def test_step_out_of_range_raises(self):
        with self.assertRaises(rewind.StepRangeError):
            jsonout.replay_payload(self.a.log, step=0)
        with self.assertRaises(rewind.StepRangeError):
            jsonout.replay_payload(self.a.log, step=99)

    def test_seq_range_filters(self):
        all_steps = jsonout.replay_payload(self.a.log)["steps"]
        first_seq = all_steps[0]["seq"]
        payload = jsonout.replay_payload(self.a.log, from_seq=first_seq + 1)
        self.assertEqual([s["tool"] for s in payload["steps"]], ["Bash"])
        payload = jsonout.replay_payload(self.a.log, to_seq=first_seq)
        self.assertEqual([s["tool"] for s in payload["steps"]], ["Write"])

    def test_secrets_redacted_by_default_and_kept_with_redact_secrets_false(self):
        inp = {"command": "cat .env"}
        from rewindagents import hook
        hook.handle(self.a._p("PreToolUse", "Bash", inp))
        hook.handle(self.a._p("PostToolUse", "Bash", inp, {"stdout": "API_KEY=" + FAKE_KEY}))
        payload = jsonout.replay_payload(self.a.log)
        last = payload["steps"][-1]
        self.assertNotIn(FAKE_KEY, last["result"])
        self.assertIn("[redacted", last["result"])
        raw = jsonout.replay_payload(self.a.log, redact_secrets=False)
        self.assertIn(FAKE_KEY, raw["steps"][-1]["result"])

    def test_cli_json_matches_the_function(self):
        os.chdir(self.d)
        try:
            code, out, err = cli("replay", "--json")
            self.assertEqual(code, 0, err)
            self.assertEqual(one_object(out), jsonout.replay_payload(self.a.log, "s1"))
        finally:
            os.chdir(self.d.parent)

    def test_cli_json_with_diff_flag_is_a_usage_error(self):
        os.chdir(self.d)
        try:
            code, out, err = cli("replay", "--step", "1", "--diff", "--json")
            self.assertEqual(code, 2)
            self.assertEqual(out, "")
            self.assertIn("--diff and --json", err)
        finally:
            os.chdir(self.d.parent)

    def test_cli_json_honours_no_redact(self):
        inp = {"command": "cat .env"}
        from rewindagents import hook
        hook.handle(self.a._p("PreToolUse", "Bash", inp))
        hook.handle(self.a._p("PostToolUse", "Bash", inp, {"stdout": "API_KEY=" + FAKE_KEY}))
        os.chdir(self.d)
        try:
            code, out, err = cli("replay", "--json")
            self.assertNotIn(FAKE_KEY, out)
            code, out, err = cli("replay", "--json", "--no-redact")
            self.assertEqual(code, 0, err)
            self.assertIn(FAKE_KEY, out)
        finally:
            os.chdir(self.d.parent)


class TestRewindPlanPayload(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.a = Agent(self.d, "s1")
        self.a.write("app.py", "v1")        # step 1
        self.a.write("app.py", "v2")        # step 2
        self.a.write("new.py", "junk")      # step 3

    def tearDown(self):
        self.tmp.cleanup()

    def test_restore_action_when_the_file_still_exists(self):
        p = rewind.rewind(self.a.log, 1, dry_run=True)
        payload = jsonout.rewind_plan_payload(p, rewind.project_root(self.a.log))
        self.assertEqual(payload["format"], "rewindagents-rewind-plan")
        self.assertEqual(payload["to"], 1)
        by_path = {r["path"]: r["action"] for r in payload["restores"]}
        self.assertEqual(by_path["app.py"], "restore")
        self.assertEqual(by_path["new.py"], "delete")
        self.assertEqual(payload["drift"], [])

    def test_create_action_when_the_file_is_currently_missing(self):
        (self.d / "app.py").unlink()
        p = rewind.rewind(self.a.log, 1, dry_run=True)
        payload = jsonout.rewind_plan_payload(p, rewind.project_root(self.a.log))
        by_path = {r["path"]: r["action"] for r in payload["restores"]}
        self.assertEqual(by_path["app.py"], "create")

    def test_drift_entry_names_the_reason(self):
        (self.d / "app.py").write_text("by hand")      # changed outside any recorded step
        p = rewind.rewind(self.a.log, 1, dry_run=True)
        payload = jsonout.rewind_plan_payload(p, rewind.project_root(self.a.log))
        self.assertEqual(len(payload["drift"]), 1)
        d = payload["drift"][0]
        self.assertEqual(d["path"], "app.py")
        self.assertIn("outside any recorded step", d["reason"])

    def test_dry_run_changes_nothing_on_disk_or_in_the_log(self):
        before_log = self.a.log.read_bytes()
        before_file = (self.d / "app.py").read_text()
        rewind.rewind(self.a.log, 1, dry_run=True)
        self.assertEqual(self.a.log.read_bytes(), before_log)
        self.assertEqual((self.d / "app.py").read_text(), before_file)

    def test_cli_rewind_json_matches_the_function(self):
        os.chdir(self.d)
        try:
            code, out, err = cli("rewind", "1", "--dry-run", "--json")
            self.assertEqual(code, 0, err)
            p = rewind.rewind(self.a.log, 1, "s1", dry_run=True)
            self.assertEqual(one_object(out), jsonout.rewind_plan_payload(p, rewind.project_root(self.a.log)))
        finally:
            os.chdir(self.d.parent)

    def test_cli_rewind_json_without_dry_run_is_a_usage_error_and_changes_nothing(self):
        os.chdir(self.d)
        try:
            before = self.a.log.read_bytes()
            code, out, err = cli("rewind", "1", "--json")
            self.assertEqual(code, 2)
            self.assertEqual(out, "")
            self.assertIn("--dry-run", err)
            self.assertEqual(self.a.log.read_bytes(), before)       # nothing was recorded
            self.assertEqual((self.d / "app.py").read_text(), "v2")  # nothing was restored
        finally:
            os.chdir(self.d.parent)

    def test_cli_rewind_json_drift_exits_1_but_still_prints_the_plan(self):
        (self.d / "app.py").write_text("by hand")
        os.chdir(self.d)
        try:
            code, out, err = cli("rewind", "1", "--dry-run", "--json")
            self.assertEqual(code, 1)
            obj = one_object(out)
            self.assertEqual(len(obj["drift"]), 1)
        finally:
            os.chdir(self.d.parent)


class TestRevertResultPayload(unittest.TestCase):
    def test_shape_after_a_real_revert(self):
        with TemporaryDirectory() as d:
            a = Agent(d, "s1")
            a.write("app.py", "v1")      # step 1: creates the file
            a.write("app.py", "v2")      # step 2: changes it, nothing touches it after
            p = revert.revert(a.log, 2)
            payload = jsonout.revert_result_payload(p, rewind.project_root(a.log))
            self.assertEqual(payload["format"], "rewindagents-revert-result")
            self.assertEqual(payload["step"], 2)
            self.assertIn("app.py", payload["delete"] + payload["write"] + payload["same"])
            self.assertIsInstance(payload["record"], int)
            self.assertEqual((Path(d) / "app.py").read_text(), "v1")

    def test_conflict_raises_and_changes_nothing(self):
        with TemporaryDirectory() as d:
            a = Agent(d, "s1")
            a.write("app.py", "v1")      # step 1: creates the file
            a.write("app.py", "v2")      # step 2: changes it again (a later change on the same lines)
            before = a.log.read_bytes()
            with self.assertRaises(revert.ConflictError) as ctx:
                revert.revert(a.log, 1)       # reverting the create conflicts with step 2's later change
            self.assertIn("step 1", str(ctx.exception))
            self.assertEqual(a.log.read_bytes(), before)


class TestErrorPayload(unittest.TestCase):
    def test_shape(self):
        self.assertEqual(jsonout.error_payload("boom"),
                         {"format": "rewindagents-error", "version": 1, "error": "boom"})


if __name__ == "__main__":
    unittest.main()
