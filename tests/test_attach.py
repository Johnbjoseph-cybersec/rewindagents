"""The `attach` GitHub Action: attach/action.yml (pinned, token only where the comment is posted) and
attach/attach.py (prepare: import + verify + export; comment: one PR comment, updated on later pushes),
the comment step driven against a fake GitHub API on 127.0.0.1."""
import contextlib
import io
import json
import os
import re
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "attach"))

import attach  # noqa: E402
from rewindagents import bundle  # noqa: E402
from test_rewind import Agent  # noqa: E402

ACTION = (ROOT / "attach" / "action.yml").read_text(encoding="utf-8")
GH = "gh" + "p_" + "A1b2C3d4" * 5   # a fake token shape, built at run time
TOKEN = "fake" + "-token-" + "9z" * 10


def recorded(d, session="s1"):
    a = Agent(d, session)
    a.write("a.txt", "v1\n")
    a.write("config.py", "TOKEN = '%s'\n" % GH)
    a.bash("rm a.txt", action=lambda cwd: (cwd / "a.txt").unlink())
    return a


def run_main(argv, env=None):
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.dict(os.environ, env or {}, clear=False), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = attach.main(argv)
    return code, out.getvalue(), err.getvalue()


def steps_of(yml):
    """Split the composite action's steps into their text blocks."""
    body = yml.split("  steps:\n", 1)[1]
    return re.split(r"\n    - ", "\n" + body)[1:]


class TestActionFile(unittest.TestCase):
    def test_every_action_it_calls_is_pinned_to_a_commit(self):
        uses = re.findall(r"^\s+uses: (\S+)", ACTION, re.M)   # step lines, not the usage comment
        self.assertEqual(len(uses), 1)
        for u in uses:
            self.assertRegex(u, r"^[\w.-]+/[\w.-]+@[0-9a-f]{40}$")

    def test_the_token_reaches_the_comment_step_only(self):
        steps = steps_of(ACTION)
        self.assertEqual(len(steps), 5)
        with_token = [s for s in steps if "inputs.token" in s or "GH_TOKEN" in s]
        self.assertEqual(len(with_token), 1)
        self.assertIn("Comment on the pull request", with_token[0])
        self.assertIn("github.event.pull_request.number", with_token[0])
        self.assertIn("pull-requests: write", ACTION)

    def test_no_expression_is_pasted_into_a_shell_line(self):
        # every value reaches the shell through env:, so a session id or branch name cannot inject commands
        for s in steps_of(ACTION):
            if "run:" in s:
                run = s.split("run:", 1)[1]
                self.assertNotIn("${{", run, s.splitlines()[0])

    def test_it_installs_the_tool_from_its_own_commit_and_never_turns_redaction_off(self):
        self.assertIn('install -q --disable-pip-version-check "$GITHUB_ACTION_PATH/.."', ACTION)
        self.assertNotIn("no-redact", ACTION)
        self.assertNotIn("no_redact", (ROOT / "attach" / "attach.py").read_text())
        self.assertIn("archive: false", ACTION)

    def test_a_log_that_does_not_verify_fails_the_job_after_the_upload(self):
        names = [s.splitlines()[0] for s in steps_of(ACTION)]
        self.assertLess(names.index("name: Upload the page"),
                        names.index("name: Fail if the log does not verify"))
        self.assertIn("exit 1", steps_of(ACTION)[-1])

    def test_readme_shows_the_action_at_a_pinned_sha_placeholder(self):
        readme = (ROOT / "README.md").read_text()
        self.assertIn("## Attach a replay to a pull request", readme)
        self.assertIn("uses: Johnbjoseph-cybersec/rewindagents/attach@<commit sha>", readme)
        for line in ("rewindagents bundle --out .rewindagents-pr.bundle", "git add .rewindagents-pr.bundle"):
            self.assertIn(line, readme)


class TestPrepare(unittest.TestCase):
    def test_writes_the_page_redacted_and_reports_through_github_output(self):
        with TemporaryDirectory() as d, TemporaryDirectory() as out:
            recorded(d)
            gh_out = Path(out, "gh_output")
            code, stdout, _ = run_main(["prepare", "--project", d, "--out-dir", out],
                                       {"GITHUB_OUTPUT": str(gh_out)})
            self.assertEqual(code, 0)
            o = dict(line.split("=", 1) for line in gh_out.read_text().splitlines())
            self.assertEqual((o["session"], o["steps"], o["chain_ok"], o["head_pinned"]), ("s1", "3", "true", "false"))
            self.assertGreater(int(o["redacted"]), 0)
            page = Path(o["page"]).read_text()
            self.assertEqual(Path(o["page"]).name, "rewindagents-replay-s1.html")
            self.assertNotIn(GH, page)
            self.assertNotIn(str(Path(d).resolve()), page)
            self.assertIn("chain intact", stdout)

    def test_a_bundle_committed_in_the_repo_is_imported_into_an_empty_checkout(self):
        with TemporaryDirectory() as dev, TemporaryDirectory() as ci, TemporaryDirectory() as out:
            a = recorded(dev, session="feat-42")
            bundle.bundle(a.log, Path(ci, ".rewindagents-pr.bundle"))
            res = attach.prepare(ci, out, ".rewindagents-pr.bundle")
            self.assertEqual((res["session"], res["steps"], res["chain_ok"]), ("feat-42", 3, "true"))
            self.assertNotIn(GH, Path(ci, ".rewindagents-pr.bundle").read_text())  # bundle redacts too

    def test_a_tampered_log_still_gets_a_page_and_reports_the_break(self):
        with TemporaryDirectory() as d, TemporaryDirectory() as out:
            a = recorded(d)
            lines = Path(a.log).read_text().splitlines()
            lines[1] = lines[1].replace('"Write"', '"Edit"', 1)
            Path(a.log).write_text("\n".join(lines) + "\n")
            res = attach.prepare(d, out)
            self.assertEqual(res["chain_ok"], "false")
            self.assertTrue(res["chain_msg"])
            self.assertIn("does not verify", Path(res["page"]).read_text())

    def test_a_wrong_pinned_head_fails_the_chain_check(self):
        with TemporaryDirectory() as d, TemporaryDirectory() as out:
            recorded(d)
            res = attach.prepare(d, out, head="0" * 64)
            self.assertEqual((res["chain_ok"], res["head_pinned"]), ("false", "true"))

    def test_no_log_and_no_bundle_says_how_to_bring_one(self):
        with TemporaryDirectory() as d, TemporaryDirectory() as out:
            with self.assertRaises(SystemExit) as e:
                attach.prepare(d, out)
            self.assertIn("rewindagents bundle --out", str(e.exception))


class FakeGitHub(BaseHTTPRequestHandler):
    comments: list = []
    seen: list = []
    status = 200

    def _reply(self, code, obj):
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _handle(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n)) if n else None
        FakeGitHub.seen.append((self.command, self.path, self.headers.get("Authorization"), body))
        if FakeGitHub.status != 200:
            return self._reply(FakeGitHub.status, {"message": "Resource not accessible by integration"})
        if self.command == "GET":
            return self._reply(200, FakeGitHub.comments)
        if self.command == "POST":
            c = {"id": 100 + len(FakeGitHub.comments), "body": body["body"]}
            FakeGitHub.comments.append(c)
            return self._reply(201, c)
        cid = int(self.path.rsplit("/", 1)[1])
        for c in FakeGitHub.comments:
            if c["id"] == cid:
                c["body"] = body["body"]
        return self._reply(200, {"id": cid})

    do_GET = do_POST = do_PATCH = _handle

    def log_message(self, *a):
        pass


class TestComment(unittest.TestCase):
    def setUp(self):
        FakeGitHub.comments, FakeGitHub.seen, FakeGitHub.status = [{"id": 7, "body": "LGTM"}], [], 200
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeGitHub)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.env = {"GH_TOKEN": TOKEN, "GITHUB_API_URL": "http://127.0.0.1:%d" % self.srv.server_port}

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def args(self, url="https://github.com/o/r/actions/runs/1/artifacts/2", ok="true"):
        return ["comment", "--repo", "o/r", "--pr", "5", "--url", url, "--session", "s`1", "--steps", "3",
                "--chain-ok", ok, "--chain-msg", "record 2: hash mismatch", "--redacted", "2"]

    def test_posts_once_then_updates_the_same_comment(self):
        code, out, _ = run_main(self.args(), self.env)
        self.assertEqual(code, 0)
        self.assertIn("posted comment 101 on #5", out)
        code, out, _ = run_main(self.args(ok="false"), self.env)
        self.assertIn("updated comment 101 on #5", out)
        self.assertEqual(len(FakeGitHub.comments), 2)       # the reviewer's comment and ours, no second one
        ours = FakeGitHub.comments[1]["body"]
        self.assertTrue(ours.startswith(attach.MARKER))
        self.assertIn("**does not verify** (record 2: hash mismatch)", ours)
        self.assertIn("session `s_1`", ours)                 # a backtick cannot break out of the code span
        self.assertEqual(FakeGitHub.comments[0]["body"], "LGTM")
        paths = [(m, p.split("?")[0]) for m, p, _, _ in FakeGitHub.seen]
        self.assertEqual(paths, [("GET", "/repos/o/r/issues/5/comments"), ("POST", "/repos/o/r/issues/5/comments"),
                                 ("GET", "/repos/o/r/issues/5/comments"), ("PATCH", "/repos/o/r/issues/comments/101")])
        self.assertTrue(all(auth == "Bearer " + TOKEN for _, _, auth, _ in FakeGitHub.seen))

    def test_a_read_only_token_warns_and_never_prints_the_token(self):
        FakeGitHub.status = 403
        code, out, err = run_main(self.args(), self.env)
        self.assertEqual(code, 0)
        self.assertIn("::warning::", out)
        self.assertIn("HTTP 403", out)
        self.assertNotIn(TOKEN, out + err)

    def test_no_token_posts_nothing(self):
        code, out, _ = run_main(self.args(), {**self.env, "GH_TOKEN": ""})
        self.assertEqual(code, 0)
        self.assertIn("no GH_TOKEN", out)
        self.assertEqual(FakeGitHub.seen, [])

    def test_body_links_only_an_https_url_and_numbers_come_from_the_arguments(self):
        b = attach.body("s1", 3, True, "", True, 2, "javascript:alert(1)")
        self.assertNotIn("javascript", b)
        self.assertIn("The page upload failed.", b)
        self.assertIn("intact, matches the pinned head", b)
        self.assertIn(": 3 steps.", b)
        self.assertIn("Secrets replaced in the page: 2.", b)

    def test_a_malformed_repo_is_refused_before_any_request(self):
        code, out, _ = run_main(["comment", "--repo", "o/r/../x", "--pr", "5", "--session", "s", "--steps", "1",
                                 "--chain-ok", "true", "--redacted", "0"], self.env)
        self.assertEqual(code, 0)
        self.assertIn("not an owner/repo", out)
        self.assertEqual(FakeGitHub.seen, [])


if __name__ == "__main__":
    unittest.main()
