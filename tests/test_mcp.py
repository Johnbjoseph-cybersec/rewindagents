"""`rewindagents mcp`: the real server, as a subprocess talking newline-delimited JSON-RPC over its own
stdin/stdout pipes -- the same way an MCP client actually runs it. Nothing here imports mcp.py directly;
every assertion is about what came back over the pipe, so a bug that only shows up when the process is
really spawned (stdout buffering, a stray print, the exit code on EOF) cannot hide behind an in-process
call.
"""
import json
import os
import queue
import subprocess
import sys
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from rewindagents import __version__  # noqa: E402
from test_rewind import Agent  # noqa: E402

TIMEOUT = 10


# a key-shaped test value built from pieces, so no key-shaped string sits in the repository
FAKE_KEY = "sk-" + "ant-" + 'abcdefghijklmnopqrstuvwxyz'


class Server:
    """The real `rewindagents mcp` process, cwd set to a project, talked to over its own pipes.

    A dedicated thread does nothing but block on `stdout.readline()` and push every line onto a
    queue; the test code only ever takes from that queue, with a timeout. Checking `select()` on the
    pipe between separately-timed `readline()` calls looks like the obvious way to add a timeout, but
    is not: a `readline()` call can pull more than one line out of the OS pipe into Python's own text
    buffer in a single read, and a `select()` call afterwards only sees the (now empty) OS pipe, not
    that buffer -- so a second response already sitting in Python's memory reads as "nothing waiting"
    and times out a call that actually already has its answer. One thread, one blocking reader, a
    queue: no call ever has to guess what the stream's internal buffer currently holds.
    """

    def __init__(self, cwd):
        env = dict(os.environ, PYTHONPATH=str(SRC))
        self.proc = subprocess.Popen([sys.executable, "-m", "rewindagents", "mcp"], cwd=str(cwd), env=env,
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     text=True, bufsize=1)
        self._lines: "queue.Queue[str]" = queue.Queue()
        self._reader = threading.Thread(target=self._pump, daemon=True)
        self._reader.start()

    def _pump(self) -> None:
        try:
            for raw in self.proc.stdout:
                self._lines.put(raw)
        except (ValueError, OSError):
            pass             # stdout was closed out from under this thread by kill()/close_and_wait()
        self._lines.put("")  # sentinel: stdout ended (EOF, or the except above)

    def send_raw(self, line: str) -> None:
        self.proc.stdin.write(line.rstrip("\n") + "\n")
        self.proc.stdin.flush()

    def send(self, msg: dict) -> None:
        self.send_raw(json.dumps(msg))

    def recv_line(self, timeout: float = TIMEOUT) -> str:
        try:
            line = self._lines.get(timeout=timeout)
        except queue.Empty:
            self.kill()
            raise AssertionError("the server did not answer within the timeout")
        if line == "":
            raise AssertionError("the server closed stdout without answering")
        return line

    def recv(self) -> dict:
        return json.loads(self.recv_line())

    def nothing_waiting(self, timeout: float = 0.2) -> bool:
        """True when no reply arrived within `timeout` (used to prove a notification got none). If one
        did arrive, it is put straight back -- the test is about to fail either way, but a later recv()
        must not lose a reply only because this check happened to run first."""
        try:
            line = self._lines.get(timeout=timeout)
        except queue.Empty:
            return True
        self._lines.put(line)
        return False

    def call(self, name: str, arguments: dict | None = None, id_: int = 1) -> dict:
        self.send({"jsonrpc": "2.0", "id": id_, "method": "tools/call",
                   "params": {"name": name, "arguments": arguments or {}}})
        return self.recv()

    def close_and_wait(self) -> int:
        self.proc.stdin.close()
        code = self.proc.wait(timeout=TIMEOUT)
        self._reader.join(timeout=TIMEOUT)
        self._close_pipes()
        return code

    def kill(self) -> None:
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(timeout=TIMEOUT)
        self._reader.join(timeout=TIMEOUT)
        self._close_pipes()

    def _close_pipes(self) -> None:
        for pipe in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            if pipe is not None and not pipe.closed:
                try:
                    pipe.close()
                except OSError:
                    pass


class ServerCase(unittest.TestCase):
    """A fresh project directory and a running server in it, torn down even when a test fails midway."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.server = Server(self.d)
        self.addCleanup(self.server.kill)
        self.addCleanup(self.tmp.cleanup)

    def log_path(self) -> Path:
        return self.d / ".rewindagents" / "log.jsonl"


class TestHandshake(ServerCase):
    def test_initialize_echoes_a_known_protocol_version_and_names_the_server(self):
        self.server.send({"jsonrpc": "2.0", "id": 1,
                          "method": "initialize", "params": {"protocolVersion": "2025-06-18"}})
        resp = self.server.recv()
        self.assertEqual(resp["jsonrpc"], "2.0")
        self.assertEqual(resp["id"], 1)
        r = resp["result"]
        self.assertEqual(r["protocolVersion"], "2025-06-18")
        self.assertEqual(r["serverInfo"], {"name": "rewindagents", "version": __version__})
        self.assertIn("tools", r["capabilities"])

    def test_initialize_falls_back_to_its_own_version_for_one_it_does_not_know(self):
        self.server.send({"jsonrpc": "2.0", "id": 1,
                          "method": "initialize", "params": {"protocolVersion": "1999-01-01"}})
        resp = self.server.recv()
        self.assertEqual(resp["result"]["protocolVersion"], "2025-06-18")

    def test_notification_gets_no_reply_a_following_request_still_does(self):
        self.server.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertTrue(self.server.nothing_waiting())
        self.server.send({"jsonrpc": "2.0", "id": 9, "method": "ping"})
        resp = self.server.recv()
        self.assertEqual(resp, {"jsonrpc": "2.0", "id": 9, "result": {}})

    def test_ping(self):
        self.server.send({"jsonrpc": "2.0", "id": 2, "method": "ping"})
        self.assertEqual(self.server.recv(), {"jsonrpc": "2.0", "id": 2, "result": {}})


class TestToolsList(ServerCase):
    def test_exactly_seven_tools(self):
        self.server.send({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        tools = self.server.recv()["result"]["tools"]
        self.assertEqual(len(tools), 7)
        names = {t["name"] for t in tools}
        self.assertEqual(names, {"rewind_sessions", "rewind_summary", "rewind_diff", "rewind_replay",
                                 "rewind_preview", "rewind_to_step", "rewind_revert_step"})

    def test_every_tool_has_a_schema_and_the_right_hint(self):
        self.server.send({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        tools = {t["name"]: t for t in self.server.recv()["result"]["tools"]}
        destructive = {"rewind_to_step", "rewind_revert_step"}
        for name, t in tools.items():
            self.assertIn("description", t)
            self.assertEqual(t["inputSchema"]["type"], "object")
            if name in destructive:
                self.assertTrue(t["annotations"].get("destructiveHint"))
                self.assertNotIn("readOnlyHint", t["annotations"])
                self.assertIn("confirm", t["inputSchema"]["required"])
            else:
                self.assertTrue(t["annotations"].get("readOnlyHint"))
                self.assertNotIn("destructiveHint", t["annotations"])

    def test_required_arguments_match_the_frozen_contract(self):
        self.server.send({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        tools = {t["name"]: t for t in self.server.recv()["result"]["tools"]}
        self.assertEqual(tools["rewind_sessions"]["inputSchema"].get("required", []), [])
        self.assertEqual(tools["rewind_summary"]["inputSchema"].get("required", []), [])
        self.assertEqual(tools["rewind_diff"]["inputSchema"]["required"], ["step"])
        self.assertIn("reveal_secrets", tools["rewind_diff"]["inputSchema"]["properties"])
        self.assertEqual(tools["rewind_diff"]["inputSchema"]["properties"]["reveal_secrets"]["type"], "boolean")
        self.assertEqual(tools["rewind_replay"]["inputSchema"].get("required", []), [])
        self.assertEqual(tools["rewind_preview"]["inputSchema"]["required"], ["to_step"])
        self.assertEqual(set(tools["rewind_to_step"]["inputSchema"]["required"]), {"to_step", "confirm"})
        self.assertEqual(set(tools["rewind_revert_step"]["inputSchema"]["required"]), {"step", "confirm"})
        for name in tools:
            self.assertNotIn("force", tools[name]["inputSchema"]["properties"])


class TestProtocolRobustness(ServerCase):
    def test_bad_json_gets_a_parse_error_and_the_server_keeps_going(self):
        self.server.send_raw("{not json at all")
        resp = self.server.recv()
        self.assertEqual(resp["error"]["code"], -32700)
        self.assertIsNone(resp["id"])
        self.server.send({"jsonrpc": "2.0", "id": 1, "method": "ping"})
        self.assertEqual(self.server.recv()["result"], {})

    def test_unknown_method_gets_method_not_found(self):
        self.server.send({"jsonrpc": "2.0", "id": 5, "method": "nonexistent/thing"})
        resp = self.server.recv()
        self.assertEqual(resp["error"]["code"], -32601)
        self.assertEqual(resp["id"], 5)

    def test_unknown_notification_gets_no_reply_either(self):
        self.server.send({"jsonrpc": "2.0", "method": "notifications/something_this_server_never_heard_of"})
        self.assertTrue(self.server.nothing_waiting())
        self.server.send({"jsonrpc": "2.0", "id": 1, "method": "ping"})
        self.assertEqual(self.server.recv()["result"], {})

    def test_eof_on_stdin_exits_0(self):
        self.server.send({"jsonrpc": "2.0", "id": 1, "method": "ping"})
        self.server.recv()
        code = self.server.close_and_wait()
        self.assertEqual(code, 0)

    def test_blank_lines_are_skipped_not_answered(self):
        self.server.send_raw("")
        self.server.send_raw("   ")
        self.server.send({"jsonrpc": "2.0", "id": 1, "method": "ping"})
        self.assertEqual(self.server.recv()["result"], {})


class TestUnknownTool(ServerCase):
    def test_unknown_tool_name_is_a_tool_error_not_a_protocol_error(self):
        resp = self.server.call("rewind_nonexistent")
        self.assertNotIn("error", resp)
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("no such tool", resp["result"]["content"][0]["text"])


class TestNoLogYet(ServerCase):
    def test_every_tool_refuses_gracefully_with_no_log_in_the_project(self):
        for name, args in [("rewind_sessions", {}), ("rewind_summary", {}), ("rewind_diff", {"step": 1}),
                           ("rewind_replay", {}), ("rewind_preview", {"to_step": 0}),
                           ("rewind_to_step", {"to_step": 0, "confirm": True}),
                           ("rewind_revert_step", {"step": 1, "confirm": True})]:
            resp = self.server.call(name, args)
            self.assertTrue(resp["result"]["isError"], name)
            self.assertIn("no rewindagents log", resp["result"]["content"][0]["text"], name)


class TestBadArguments(ServerCase):
    def setUp(self):
        super().setUp()
        Agent(self.d, "s1").write("app.py", "v1")

    def test_non_integer_step_is_an_error_not_a_crash(self):
        resp = self.server.call("rewind_diff", {"step": "one"})
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("integer", resp["result"]["content"][0]["text"])

    def test_boolean_is_not_accepted_as_the_integer_it_technically_is_in_python(self):
        resp = self.server.call("rewind_preview", {"to_step": True})
        self.assertTrue(resp["result"]["isError"])

    def test_missing_required_argument_is_an_error(self):
        resp = self.server.call("rewind_preview", {})
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("to_step", resp["result"]["content"][0]["text"])

    def test_unknown_session_names_what_sessions_there_are(self):
        resp = self.server.call("rewind_summary", {"session": "does-not-exist"})
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("no session", resp["result"]["content"][0]["text"])


class TestReadOnlyToolsAgainstAFixture(ServerCase):
    """Built with the same Agent helper test_rewind.py uses for the real hook, before the server ever
    starts: the server reads it fresh on every call, so no caching between tool calls can be hiding here."""

    def setUp(self):
        super().setUp()
        self.a = Agent(self.d, "s1")
        self.a.write("app.py", "v1")         # step 1
        self.a.write("app.py", "v2")         # step 2
        self.a.write("new.py", "junk")       # step 3

    def _text(self, resp: dict) -> dict:
        self.assertFalse(resp["result"]["isError"], resp["result"])
        return json.loads(resp["result"]["content"][0]["text"])

    def test_rewind_sessions(self):
        payload = self._text(self.server.call("rewind_sessions"))
        self.assertEqual(payload["format"], "rewindagents-sessions")
        self.assertEqual([s["session"] for s in payload["sessions"]], ["s1"])
        self.assertEqual(payload["sessions"][0]["steps"], 3)

    def test_rewind_summary(self):
        payload = self._text(self.server.call("rewind_summary"))
        self.assertEqual(payload["format"], "rewindagents-summary")
        self.assertEqual(len(payload["steps"]), 3)
        self.assertEqual(payload["steps"][2]["files"], ["new.py"])

    def test_rewind_diff(self):
        payload = self._text(self.server.call("rewind_diff", {"step": 1}))
        self.assertEqual(payload["format"], "rewindagents-diff")
        by_path = {f["path"]: f for f in payload["files"]}
        self.assertEqual(by_path["new.py"]["change"], "deleted")
        self.assertEqual(by_path["app.py"]["change"], "modified")

    def test_rewind_diff_out_of_range_step_is_an_error(self):
        resp = self.server.call("rewind_diff", {"step": 999})
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("out of range", resp["result"]["content"][0]["text"])

    def test_rewind_replay(self):
        payload = self._text(self.server.call("rewind_replay"))
        self.assertEqual(payload["format"], "rewindagents-replay")
        self.assertEqual(len(payload["steps"]), 3)
        self.assertIsInstance(payload["steps"][0]["result"], str)

    def test_rewind_replay_seq_range(self):
        full = self._text(self.server.call("rewind_replay"))
        middle_seq = full["steps"][1]["seq"]
        payload = self._text(self.server.call("rewind_replay", {"from_seq": middle_seq, "to_seq": middle_seq}))
        self.assertEqual(len(payload["steps"]), 1)
        self.assertEqual(payload["steps"][0]["seq"], middle_seq)

    def test_rewind_preview_writes_nothing(self):
        before = (self.d / "app.py").read_bytes()
        before_log = self.log_path().read_bytes()
        payload = self._text(self.server.call("rewind_preview", {"to_step": 1}))
        self.assertEqual(payload["format"], "rewindagents-rewind-plan")
        self.assertEqual(payload["to"], 1)
        by_path = {r["path"]: r["action"] for r in payload["restores"]}
        self.assertEqual(by_path["app.py"], "restore")
        self.assertEqual(by_path["new.py"], "delete")
        self.assertEqual((self.d / "app.py").read_bytes(), before)
        self.assertEqual(self.log_path().read_bytes(), before_log)


class TestRewindDiffRedaction(ServerCase):
    """rewind_diff redacts secrets in the unified diff text by default -- unlike the plain CLI `diff`
    command (jsonout.diff_payload's own default is unredacted; see test_jsonout.py) -- because a
    result from this tool is as likely to land in another LLM's own context as in a terminal."""

    def setUp(self):
        super().setUp()
        self.a = Agent(self.d, "s1")
        self.a.write("app.py", "v1")                                      # step 1
        self.a.write(".env", "API_KEY=" + FAKE_KEY)  # step 2

    def _text(self, resp: dict) -> dict:
        self.assertFalse(resp["result"]["isError"], resp["result"])
        return json.loads(resp["result"]["content"][0]["text"])

    def test_redacted_by_default(self):
        payload = self._text(self.server.call("rewind_diff", {"step": 1}))
        by_path = {f["path"]: f for f in payload["files"]}
        self.assertEqual(by_path[".env"]["change"], "deleted")
        self.assertNotIn(FAKE_KEY, by_path[".env"]["unified"])
        self.assertIn("[redacted", by_path[".env"]["unified"])

    def test_reveal_secrets_true_returns_the_raw_text(self):
        payload = self._text(self.server.call("rewind_diff", {"step": 1, "reveal_secrets": True}))
        by_path = {f["path"]: f for f in payload["files"]}
        self.assertIn(FAKE_KEY, by_path[".env"]["unified"])

    def test_reveal_secrets_anything_but_the_json_boolean_true_still_redacts(self):
        for bad in (False, "true", 1, None):
            payload = self._text(self.server.call("rewind_diff", {"step": 1, "reveal_secrets": bad}))
            by_path = {f["path"]: f for f in payload["files"]}
            self.assertNotIn(FAKE_KEY, by_path[".env"]["unified"], repr(bad))


class TestDestructiveConfirmRefusal(ServerCase):
    def setUp(self):
        super().setUp()
        self.a = Agent(self.d, "s1")
        self.a.write("app.py", "v1")

    def test_rewind_to_step_without_confirm_is_refused(self):
        resp = self.server.call("rewind_to_step", {"to_step": 0})
        self.assertTrue(resp["result"]["isError"])
        text = resp["result"]["content"][0]["text"]
        self.assertIn("confirm", text)
        self.assertEqual((self.d / "app.py").read_bytes(), b"v1")

    def test_confirm_false_is_refused(self):
        resp = self.server.call("rewind_to_step", {"to_step": 0, "confirm": False})
        self.assertTrue(resp["result"]["isError"])

    def test_confirm_as_a_string_is_not_the_boolean_true_and_is_refused(self):
        resp = self.server.call("rewind_to_step", {"to_step": 0, "confirm": "true"})
        self.assertTrue(resp["result"]["isError"])

    def test_confirm_as_the_integer_one_is_refused(self):
        resp = self.server.call("rewind_to_step", {"to_step": 0, "confirm": 1})
        self.assertTrue(resp["result"]["isError"])

    def test_revert_step_without_confirm_is_refused(self):
        resp = self.server.call("rewind_revert_step", {"step": 1})
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("confirm", resp["result"]["content"][0]["text"])

    def test_no_tool_schema_exposes_a_force_argument(self):
        self.server.send({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        for t in self.server.recv()["result"]["tools"]:
            self.assertNotIn("force", t["inputSchema"]["properties"], t["name"])

    def test_confirmed_rewind_actually_writes(self):
        resp = self.server.call("rewind_to_step", {"to_step": 0, "confirm": True})
        self.assertFalse(resp["result"]["isError"], resp["result"])
        self.assertFalse((self.d / "app.py").exists())


class TestDriftRefusal(ServerCase):
    """A file changed outside the steps a rewind would take back: rewind_to_step must refuse (DriftError,
    verbatim), write nothing, and refuse again the same way on a second, identical call -- it never
    retries and there is no force argument to retry with."""

    def setUp(self):
        super().setUp()
        self.a = Agent(self.d, "s1")
        self.a.write("calc.py", "v1")
        self.a.write("calc.py", "v2")
        (self.d / "calc.py").write_text("hand-edited after the session's last step")

    def test_refuses_and_changes_nothing(self):
        before_log = self.log_path().read_bytes()
        resp = self.server.call("rewind_to_step", {"to_step": 1, "confirm": True})
        self.assertTrue(resp["result"]["isError"])
        text = resp["result"]["content"][0]["text"]
        self.assertIn("calc.py", text)
        self.assertIn("changed", text)
        self.assertEqual((self.d / "calc.py").read_text(), "hand-edited after the session's last step")
        self.assertEqual(self.log_path().read_bytes(), before_log)

    def test_a_second_identical_call_refuses_the_same_way_again(self):
        first = self.server.call("rewind_to_step", {"to_step": 1, "confirm": True}, id_=1)
        second = self.server.call("rewind_to_step", {"to_step": 1, "confirm": True}, id_=2)
        self.assertTrue(first["result"]["isError"])
        self.assertTrue(second["result"]["isError"])
        self.assertEqual(first["result"]["content"][0]["text"], second["result"]["content"][0]["text"])
        self.assertEqual((self.d / "calc.py").read_text(), "hand-edited after the session's last step")


class TestRevertConflictRefusal(ServerCase):
    """Step 1 created the file and step 2 changed it: reverting step 1 (removing the create) conflicts
    with step 2's later change to the same file, so revert.py refuses (ConflictError) and changes nothing."""

    def setUp(self):
        super().setUp()
        self.a = Agent(self.d, "s1")
        self.a.write("app.py", "v1")
        self.a.write("app.py", "v2")

    def test_refuses_and_changes_nothing(self):
        before_log = self.log_path().read_bytes()
        resp = self.server.call("rewind_revert_step", {"step": 1, "confirm": True})
        self.assertTrue(resp["result"]["isError"])
        text = resp["result"]["content"][0]["text"]
        self.assertIn("step 1", text)
        self.assertEqual((self.d / "app.py").read_text(), "v2")
        self.assertEqual(self.log_path().read_bytes(), before_log)


class TestRealCliProjectSmoke(unittest.TestCase):
    """End-to-end smoke test: the scratch project's history is written by spawning the real
    `rewindagents hook --agent claude` subcommand (not by importing hook.py and calling handle() in
    process, the way the `Agent` helper above does for every other test in this file), and then the
    real `rewindagents mcp` server -- a second, independent subprocess -- is driven over its own pipe
    exactly as TestHandshake/TestToolsList above do. Two separate real processes, no in-process
    shortcut anywhere in the chain from 'a tool ran' to 'the MCP server answers tools/list and a
    tools/call about it'."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.env = dict(os.environ, PYTHONPATH=str(SRC))

    def _hook(self, payload: dict) -> None:
        p = subprocess.run([sys.executable, "-m", "rewindagents", "hook", "--agent", "claude"],
                            cwd=str(self.d), env=self.env, input=json.dumps(payload),
                            capture_output=True, text=True, timeout=TIMEOUT)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def _write_through_the_real_cli(self, name: str, text: str, session: str = "s1") -> None:
        """Pre hook, the actual file write, post hook -- each hook call a real `rewindagents hook`
        subprocess, the same command `rewindagents init`/`install` wire into an agent's own config."""
        target = self.d / name
        inp = {"file_path": str(target), "content": text}
        self._hook({"session_id": session, "cwd": str(self.d), "hook_event_name": "PreToolUse",
                    "tool_name": "Write", "tool_input": inp})
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        self._hook({"session_id": session, "cwd": str(self.d), "hook_event_name": "PostToolUse",
                    "tool_name": "Write", "tool_input": inp, "tool_response": {"ok": True}})

    def test_initialize_list_and_one_call_over_a_real_pipe_against_a_real_cli_project(self):
        # The project's whole history comes from the real CLI subcommand, not a Python-level shortcut.
        self._write_through_the_real_cli("app.py", "v1")
        self.assertTrue((self.d / ".rewindagents" / "log.jsonl").is_file(),
                         "the real `rewindagents hook` subprocess did not create a log for this project")

        server = Server(self.d)
        self.addCleanup(server.kill)

        server.send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                     "params": {"protocolVersion": "2025-06-18"}})
        init_resp = server.recv()
        self.assertEqual(init_resp["result"]["serverInfo"], {"name": "rewindagents", "version": __version__})

        server.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = server.recv()["result"]["tools"]
        names = {t["name"] for t in tools}
        # The 7 frozen tool names -- no more, no fewer -- against a project the real CLI populated.
        self.assertEqual(names, {"rewind_sessions", "rewind_summary", "rewind_diff", "rewind_replay",
                                 "rewind_preview", "rewind_to_step", "rewind_revert_step"})
        self.assertEqual(len(tools), 7)

        resp = server.call("rewind_sessions", {}, id_=3)
        self.assertFalse(resp["result"]["isError"], resp["result"])
        payload = json.loads(resp["result"]["content"][0]["text"])
        self.assertEqual(payload["format"], "rewindagents-sessions")
        self.assertEqual([s["session"] for s in payload["sessions"]], ["s1"])
        self.assertEqual(payload["sessions"][0]["steps"], 1)

        code = server.close_and_wait()
        self.assertEqual(code, 0)


class TestStdoutPurity(ServerCase):
    """With a client sending several calls back to back, stdout must carry exactly one JSON object per
    reply and nothing that is not one of those objects -- no stray print, no half-written line."""

    def test_every_line_on_stdout_is_exactly_one_json_object_in_order(self):
        Agent(self.d, "s1").write("app.py", "v1")
        calls = [("rewind_sessions", {}), ("rewind_summary", {}), ("rewind_preview", {"to_step": 0}),
                (None, None)]  # a bare ping in between, by id
        ids = []
        for i, (name, args) in enumerate(calls, start=1):
            if name is None:
                self.server.send({"jsonrpc": "2.0", "id": 100 + i, "method": "ping"})
            else:
                self.server.send({"jsonrpc": "2.0", "id": 100 + i, "method": "tools/call",
                                  "params": {"name": name, "arguments": args}})
            ids.append(100 + i)
        for expected_id in ids:
            line = self.server.recv_line()
            self.assertTrue(line.endswith("\n"))
            obj = json.loads(line)        # raises if anything but one clean JSON object is on the line
            self.assertEqual(obj["id"], expected_id)
        self.assertTrue(self.server.nothing_waiting())


if __name__ == "__main__":
    unittest.main()
