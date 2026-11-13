"""`rewindagents ui`: the local timeline server. Security properties first, then what the page shows and does."""
import json
import socket
import sys
import threading
import unittest
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rewindagents import log, rewind, ui  # noqa: E402
from test_rewind import Agent, cli  # noqa: E402


def wrecked(d, session="s1"):
    a = Agent(d, session)
    a.write("app.py", "def main():\n    return 1\n")                       # 1
    a.write("app.py", "def main():\n    return 2\n")                       # 2
    a.write("junk.py", "x = 1\n")                                          # 3
    a.write("app.py", "def main():\n    raise SystemExit('wrecked')\n")    # 4
    return a


class Server:
    """A UI server on an ephemeral port in a thread, and a urllib client for it."""

    def __init__(self, log_path, session=None):
        self.srv = ui.make_server(log_path, port=0, session=session)
        self.port, self.token = self.srv.port, self.srv.token
        self.thread = threading.Thread(target=self.srv.serve_forever, args=(0.05,), daemon=True)
        self.thread.start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()

    def req(self, path, token=True, method="GET", body=None, host=None, origin=True, headers=None, raw_query=None):
        q = raw_query if raw_query is not None else (("t=" + self.token) if token is True else
                                                     ("t=" + token) if token else "")
        sep = "&" if "?" in path else "?"
        url = f"http://127.0.0.1:{self.port}{path}{sep + q if q else ''}"
        h = {"Host": host or f"127.0.0.1:{self.port}"}
        data = None
        if method == "POST":
            data = json.dumps(body if body is not None else {}).encode()
            h["Content-Type"] = "application/json"
            if origin is True:
                h["Origin"] = f"http://127.0.0.1:{self.port}"
            elif origin:
                h["Origin"] = origin
        h.update(headers or {})
        r = urllib.request.Request(url, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(r, timeout=10) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as e:
            with e:
                return e.code, dict(e.headers), e.read()

    def json(self, *a, **k):
        code, headers, body = self.req(*a, **k)
        return code, json.loads(body)


class UICase(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.a = wrecked(self.d)
        self.s = Server(self.a.log)

    def tearDown(self):
        self.s.close()
        self.tmp.cleanup()


class TestToken(UICase):
    PATHS = ["/", "/app.js", "/app.css", "/favicon.svg", "/api/sessions", "/api/session?s=s1", "/api/step?s=s1&n=1"]

    def test_missing_token_is_403_on_page_assets_and_api(self):
        for p in self.PATHS:
            with self.subTest(p):
                self.assertEqual(self.s.req(p, token=None)[0], 403)

    def test_wrong_token_is_403_on_page_assets_and_api(self):
        for p in self.PATHS:
            with self.subTest(p):
                self.assertEqual(self.s.req(p, token="x" * len(self.s.token))[0], 403)
                self.assertEqual(self.s.req(p, token=self.s.token[:-1])[0], 403)

    def test_right_token_is_200(self):
        for p in self.PATHS:
            with self.subTest(p):
                self.assertEqual(self.s.req(p)[0], 200)

    def test_wrong_token_is_403_on_actions_and_nothing_changes(self):
        before = self.a.log.read_bytes()
        for p in ("/api/preview", "/api/rewind"):
            code, _ = self.s.json(p, token="nope", method="POST", body={"session": "s1", "step": 0, "confirm": True})
            self.assertEqual(code, 403)
        self.assertEqual(self.a.log.read_bytes(), before)
        self.assertIn("raise SystemExit", (self.d / "app.py").read_text())

    def test_token_is_compared_in_constant_time(self):
        with mock.patch.object(ui.hmac, "compare_digest", wraps=ui.hmac.compare_digest) as cd:
            self.s.req("/api/sessions", token="nope")
            self.s.req("/api/sessions")
        self.assertEqual(cd.call_count, 2)

    def test_each_server_gets_its_own_random_token(self):
        other = ui.make_server(self.a.log)
        try:
            self.assertNotEqual(other.token, self.s.token)
            self.assertGreaterEqual(len(self.s.token), 40)
        finally:
            other.server_close()

    def test_non_ascii_token_is_403_not_a_crash(self):
        self.assertEqual(self.s.req("/api/sessions", raw_query="t=%C3%A9")[0], 403)


class TestHostAndOrigin(UICase):
    def test_foreign_host_header_is_403_even_with_the_token(self):
        for host in ("evil.example", f"evil.example:{self.s.port}", f"127.0.0.1:{self.s.port + 1}",
                     f"127.0.0.1.evil.example:{self.s.port}", "127.0.0.1"):
            with self.subTest(host):
                self.assertEqual(self.s.req("/api/sessions", host=host)[0], 403)
                self.assertEqual(self.s.req("/", host=host)[0], 403)

    def test_localhost_host_header_is_allowed(self):
        self.assertEqual(self.s.req("/api/sessions", host=f"localhost:{self.s.port}")[0], 200)

    def test_post_needs_a_same_origin_origin_header(self):
        body = {"session": "s1", "step": 2}
        self.assertEqual(self.s.json("/api/preview", method="POST", body=body)[0], 200)
        self.assertEqual(self.s.json("/api/preview", method="POST", body=body, origin=None)[0], 403)
        self.assertEqual(self.s.json("/api/preview", method="POST", body=body, origin="http://evil.example")[0], 403)
        self.assertEqual(self.s.json("/api/preview", method="POST", body=body, origin="null")[0], 403)
        self.assertEqual(self.s.json("/api/preview", method="POST", body=body,
                                     headers={"Sec-Fetch-Site": "cross-site"})[0], 403)

    def test_post_needs_json(self):
        code, _, _ = self.s.req("/api/preview", method="POST", body={"session": "s1", "step": 2},
                                headers={"Content-Type": "text/plain"})
        self.assertEqual(code, 415)


class TestMethods(UICase):
    def test_get_on_action_endpoints_is_405(self):
        for p in ("/api/preview", "/api/rewind"):
            with self.subTest(p):
                code, headers, _ = self.s.req(p)
                self.assertEqual(code, 405)
                self.assertEqual(headers.get("Allow"), "POST")

    def test_post_on_read_endpoints_is_405(self):
        self.assertEqual(self.s.json("/api/sessions", method="POST")[0], 405)

    def test_other_methods_are_405_and_unknown_paths_404(self):
        for m in ("PUT", "DELETE", "OPTIONS", "PATCH"):
            with self.subTest(m):
                self.assertEqual(self.s.req("/api/rewind", method=m)[0], 405)
        self.assertEqual(self.s.req("/etc/passwd")[0], 404)
        self.assertEqual(self.s.req("/api/session?s=nope")[0], 404)

    def test_rewind_without_confirm_changes_nothing(self):
        before = self.a.log.read_bytes()
        code, j = self.s.json("/api/rewind", method="POST", body={"session": "s1", "step": 0})
        self.assertEqual(code, 400)
        self.assertEqual(self.a.log.read_bytes(), before)

    def test_bad_steps_and_paths_are_refused(self):
        for body in ({"session": "s1", "step": -1}, {"session": "s1", "step": "2"}, {"session": "s1", "step": True},
                     {"session": "s1", "step": 99}, {"session": "nope", "step": 0}):
            with self.subTest(body):
                self.assertIn(self.s.json("/api/preview", method="POST", body=body)[0], (400, 404, 409))
        if ui.only_supported():
            for path in ("../../etc/passwd", "/etc/passwd", str(self.d / "app.py"), "never-touched.py", ""):
                with self.subTest(path):
                    code, _ = self.s.json("/api/rewind", method="POST",
                                          body={"session": "s1", "step": 1, "path": path, "confirm": True})
                    self.assertEqual(code, 400)


class TestHeaders(UICase):
    def test_strict_csp_and_no_cors_on_every_response(self):
        for p, kw in (("/", {}), ("/app.js", {}), ("/api/sessions", {}), ("/api/sessions", {"token": None}),
                      ("/api/rewind", {})):
            with self.subTest(p, **kw):
                _, h, _ = self.s.req(p, **kw)
                csp = h.get("Content-Security-Policy", "")
                self.assertIn("default-src 'none'", csp)
                self.assertIn("script-src 'self'", csp)
                self.assertNotIn("unsafe-inline", csp)
                self.assertNotIn("unsafe-eval", csp)
                self.assertEqual(h.get("Referrer-Policy"), "no-referrer")
                self.assertEqual(h.get("X-Content-Type-Options"), "nosniff")
                self.assertFalse([k for k in h if k.lower().startswith("access-control-")], h)
                self.assertNotIn("Python", h.get("Server", ""))


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts, self.styles, self.style_attrs, self.inline_handlers, self.urls, self.inline_js = [], 0, 0, 0, [], 0
        self._in_script = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "script":
            self.scripts.append(a.get("src"))
            self._in_script = True
        if tag == "style":
            self.styles += 1
        if "style" in a:
            self.style_attrs += 1
        self.inline_handlers += sum(1 for k in a if k.startswith("on"))
        for k in ("src", "href"):
            if a.get(k):
                self.urls.append(a[k])

    def handle_endtag(self, tag):
        if tag == "script":
            self._in_script = False

    def handle_data(self, data):
        if self._in_script and data.strip():
            self.inline_js += 1


class TestPage(UICase):
    def test_page_has_no_inline_code_and_fetches_nothing_from_elsewhere(self):
        code, h, body = self.s.req("/")
        self.assertEqual(code, 200)
        p = Page()
        p.feed(body.decode())
        self.assertEqual(p.scripts, [f"/app.js?t={self.s.token}"])
        self.assertEqual((p.styles, p.style_attrs, p.inline_handlers, p.inline_js), (0, 0, 0, 0))
        for u in p.urls:
            self.assertTrue(u.startswith("/") and not u.startswith("//"), u)
        js = self.s.req("/app.js")[2].decode()
        css = self.s.req("/app.css")[2].decode()
        for text in (js, css):
            self.assertNotIn("http://", text)
            self.assertNotIn("https://", text)
            self.assertNotIn("@import", text)
            self.assertNotIn("url(", text)
        self.assertNotIn("innerHTML", js)
        self.assertNotIn("eval(", js)

    def test_page_uses_the_brand_palette_and_type(self):
        css = self.s.req("/app.css")[2].decode()
        for hexv in ("#F2F4F1", "#121412", "#1C201D", "#B82A16", "#FF7A59"):
            self.assertIn(hexv, css)
        for font in ("Bricolage Grotesque", "Hanken Grotesk", "Commit Mono"):
            self.assertIn(font, css)
        self.assertIn("made by John B Joseph", self.s.req("/")[2].decode())

    def test_input_and_result_wrap_diffs_do_not(self):
        # R34: the same sideways scroll R33 fixed in export; a clipped 4,000-char input ran off the panel.
        import re
        css = self.s.req("/app.css")[2].decode()
        js = self.s.req("/app.js")[2].decode()
        rules = dict(re.findall(r"^(pre[.\w]*)\{([^}]*)\}", css, re.M))
        self.assertIn("white-space:pre-wrap", rules["pre.io"])
        self.assertIn("overflow-wrap:anywhere", rules["pre.io"])
        self.assertNotIn("white-space", rules["pre"])               # diffs keep the browser's pre, columns line up
        self.assertNotIn("pre.diff{", css)                          # nothing gives diffs a wrapping rule
        self.assertIn('el("summary", "", "Input"), el("pre", "io", d.input)', js)
        self.assertIn('el("pre", "io", d.result)', js)
        self.assertIn('var pre = el("pre", "diff");', js)
        self.assertEqual(len(re.findall(r'el\("pre", "io"', js)), 2)  # input + result, nothing else

    def test_narrow_layout_fits_the_viewport(self):
        # R35: at 390 px the page was 448 wide: the header never wrapped (the chain line sat past the edge) and a
        # step row's 1fr track kept its chips' min-content width inside a 190 px timeline column.
        import re
        css = self.s.req("/app.css")[2].decode()
        media = dict(re.findall(r"@media \(max-width:(\d+)px\)\{(.*?\})\}\s*$", css, re.M | re.S))
        rules = lambda body: {k.strip(): v for k, v in re.findall(r"([^{}]+)\{([^}]*)\}", body)}
        step = dict(re.findall(r"^(\.step>button)\{([^}]*)\}", css, re.M))[".step>button"]
        self.assertIn("grid-template-columns:44px minmax(0,1fr)", step)   # the text track may shrink below its content
        self.assertIn("grid-template-columns:200px minmax(0,1fr)", rules(media["1100"])[".app"])
        narrow = rules(media["640"])
        self.assertIn("grid-template-columns:minmax(0,1fr)", narrow[".app"])  # one column: sessions, timeline, detail
        self.assertIn("flex-wrap:wrap", narrow[".bar"])
        self.assertIn("min-width:0", narrow[".project"])
        self.assertIn("overflow-wrap:anywhere", narrow[".project"])
        self.assertNotIn("1fr)", re.sub(r"minmax\([^)]*\)", "", css))     # no bare 1fr track anywhere

    def test_keyboard_keys_are_wired(self):
        js = self.s.req("/app.js")[2].decode()
        for key in ('"j"', '"k"', '"d"', '"r"'):
            self.assertIn("e.key === " + key, js)


class TestBind(unittest.TestCase):
    def test_refuses_any_address_but_127_0_0_1(self):
        with TemporaryDirectory() as d:
            for host in ("0.0.0.0", "", "::", "localhost", "192.168.1.1"):
                with self.subTest(host):
                    with self.assertRaises(ValueError):
                        ui.make_server(Path(d) / "log.jsonl", host=host)

    def test_listens_on_127_0_0_1_and_a_random_free_port(self):
        with TemporaryDirectory() as d:
            a, b = ui.make_server(Path(d, "l")), ui.make_server(Path(d, "l"))
            try:
                self.assertEqual(a.socket.getsockname()[0], "127.0.0.1")
                self.assertEqual(a.socket.family, socket.AF_INET)
                self.assertNotEqual(a.port, 0)
                self.assertNotEqual(a.port, b.port)
                self.assertTrue(a.url.startswith(f"http://127.0.0.1:{a.port}/?t="))
            finally:
                a.server_close()
                b.server_close()

    def test_cli_registers_ui_and_rejects_a_bad_port_without_serving(self):
        with TemporaryDirectory() as d:
            code, out, err = cli("--log", str(Path(d, "log.jsonl")), "ui", "--no-open", "--port", "70000")
            self.assertEqual(code, 2)
            self.assertIn("port", err)

    def test_cli_ui_serves_then_stops_on_ctrl_c(self):
        with TemporaryDirectory() as d:
            opened = []
            with mock.patch.object(ui.UIServer, "serve_forever", side_effect=KeyboardInterrupt), \
                    mock.patch.object(ui.webbrowser, "open", side_effect=opened.append):
                code, out, _ = cli("--log", str(Path(d, "log.jsonl")), "ui", "--no-open")
                self.assertEqual((code, opened), (0, []))
                self.assertIn("http://127.0.0.1:", out)
                self.assertIn("stopped", out)
                code, out, _ = cli("--log", str(Path(d, "log.jsonl")), "ui")
                self.assertEqual(len(opened), 1)
                self.assertTrue(opened[0].startswith("http://127.0.0.1:") and "?t=" in opened[0])


class TestData(UICase):
    def test_sessions_and_the_timeline(self):
        Agent(self.d, "s0").write("other.txt", "x\n")
        code, m = self.s.json("/api/sessions")
        self.assertEqual(code, 200)
        self.assertTrue(m["exists"])
        self.assertTrue(m["chain"]["ok"])
        self.assertEqual([e["session"] for e in m["sessions"]], ["s0", "s1"])   # newest first
        self.assertEqual(m["initial"], "s0")
        code, t = self.s.json("/api/session?s=s1")
        self.assertEqual([r["step"] for r in t["steps"]], [1, 2, 3, 4])
        self.assertEqual([r["tool"] for r in t["steps"]], ["Write"] * 4)
        r1 = t["steps"][0]
        self.assertEqual(r1["summary"], "app.py")
        self.assertEqual(r1["checkpoints"], 1)
        self.assertEqual((r1["files"][0]["path"], r1["files"][0]["adds"], r1["files"][0]["dels"]), ("app.py", 2, 0))
        r2 = t["steps"][1]["files"][0]
        self.assertEqual((r2["adds"], r2["dels"]), (1, 1))
        self.assertRegex(r1["time"], r"^\d\d:\d\d:\d\d$")

    def test_initial_session_from_the_command_line(self):
        Agent(self.d, "s0").write("other.txt", "x\n")
        s2 = Server(self.a.log, session="s1")
        try:
            self.assertEqual(s2.json("/api/sessions")[1]["initial"], "s1")
        finally:
            s2.close()

    def test_step_detail_has_the_diff_input_and_result_without_the_project_path(self):
        code, d = self.s.json("/api/step?s=s1&n=2")
        self.assertEqual(code, 200)
        f = d["files"][0]
        self.assertIn("-    return 1", f["change"]["lines"])
        self.assertIn("+    return 2", f["change"]["lines"])
        self.assertIn('"file_path": "app.py"', d["input"])
        self.assertIn('"ok": true', d["result"])
        self.assertNotIn(str(self.d.resolve()), json.dumps(d))

    def test_long_input_is_cut(self):
        Agent(self.d, "big").write("big.txt", "y" * (ui.MAX_TEXT + 500))
        code, d = self.s.json("/api/step?s=big&n=1")
        self.assertIn(f"... first 4,000 of {ui.MAX_TEXT + 500:,} characters kept in the log", d["input"])  # R30 cut, R32 note
        self.assertNotIn('"truncated"', d["input"])
        self.assertLess(len(d["input"]), ui.MAX_TEXT + 100)
        # a record written before the hook cut inputs keeps the whole text: the page still cuts that
        long = "y" * (ui.MAX_TEXT + 500)
        self.assertEqual(ui._clip(long), long[:ui.MAX_TEXT] + "\n... 500 more characters")

    def test_missing_log_is_an_empty_state(self):
        with TemporaryDirectory() as d:
            s = Server(Path(d, ".rewindagents", "log.jsonl"))
            try:
                code, m = s.json("/api/sessions")
                self.assertEqual((code, m["exists"], m["sessions"]), (200, False, []))
                self.assertIn("rewindagents init", s.req("/app.js")[2].decode())
                self.assertEqual(s.req("/api/session?s=s1")[0], 404)
            finally:
                s.close()


def _rewind_record(log_path):
    """The last record, with what differs between two projects (paths, times, hashes) made comparable."""
    root = rewind.project_root(log_path)
    r = log.read(log_path)[-1]
    args = dict(r["args"])
    args["checkpoints"] = [dict(cp, path=rewind.relative(cp["path"], root)) for cp in args["checkpoints"]]
    return {k: v for k, v in r.items() if k not in ("ts", "hash", "prev")} | {"args": args}


class TestActions(UICase):
    def test_preview_lists_what_rewind_would_change_and_changes_nothing(self):
        before = self.a.log.read_bytes()
        code, p = self.s.json("/api/preview", method="POST", body={"session": "s1", "step": 2})
        self.assertEqual(code, 200, p)
        got = {c["path"]: c["action"] for c in p["changes"]}
        self.assertEqual(got, {"app.py": "restore", "junk.py": "delete"})
        app = next(c for c in p["changes"] if c["path"] == "app.py")
        self.assertTrue(any("return 2" in l and l.startswith("+") for l in app["change"]["lines"]), app)
        self.assertEqual(p["new_step"], 5)
        self.assertEqual(self.a.log.read_bytes(), before)
        cli_plan = rewind.rewind(self.a.log, 2, "s1", dry_run=True)
        self.assertEqual(sorted(got), sorted(rewind.relative(x, rewind.project_root(self.a.log))
                                             for x in [p for p, _ in cli_plan["restore"]] + cli_plan["delete"]))

    def test_rewind_via_the_ui_writes_the_same_log_record_as_the_cli(self):
        code, r = self.s.json("/api/rewind", method="POST", body={"session": "s1", "step": 2, "confirm": True})
        self.assertEqual(code, 200, r)
        self.assertEqual((r["new_step"], r["undo_to"], r["record"]), (5, 4, len(log.read(self.a.log))))
        with TemporaryDirectory() as d2:
            b = wrecked(d2)
            code_cli, out, err = cli("--log", str(b.log), "rewind", "2", "--session", "s1")
            self.assertEqual(code_cli, 0, err)
            self.assertEqual(_rewind_record(self.a.log), _rewind_record(b.log))
            for name in ("app.py", "junk.py"):
                self.assertEqual((self.d / name).exists(), (Path(d2) / name).exists())
            self.assertEqual((self.d / "app.py").read_text(), (Path(d2) / "app.py").read_text())
        self.assertEqual((self.d / "app.py").read_text(), "def main():\n    return 2\n")
        self.assertFalse((self.d / "junk.py").exists())
        self.assertTrue(log.verify(self.a.log)[0])

    def test_the_timeline_shows_the_new_step_and_the_rewind_can_be_undone(self):
        self.s.json("/api/rewind", method="POST", body={"session": "s1", "step": 2, "confirm": True})
        t = self.s.json("/api/session?s=s1")[1]
        last = t["steps"][-1]
        self.assertEqual((last["step"], last["event"], last["to_step"]), (5, "rewind", 2))
        self.assertEqual([r["undone_by"] for r in t["steps"]], [None, None, 5, 5, None])
        code, u = self.s.json("/api/rewind", method="POST", body={"session": "s1", "step": 4, "confirm": True})
        self.assertEqual(code, 200, u)
        self.assertIn("raise SystemExit", (self.d / "app.py").read_text())
        self.assertEqual((self.d / "junk.py").read_text(), "x = 1\n")
        self.assertEqual(len(self.s.json("/api/session?s=s1")[1]["steps"]), 6)

    def test_a_log_that_does_not_verify_refuses_preview_and_rewind(self):
        lines = self.a.log.read_text().splitlines(True)
        rec = json.loads(lines[1])
        rec["args"]["input"]["content"] = "tampered"
        lines[1] = json.dumps(rec, sort_keys=True) + "\n"
        self.a.log.write_text("".join(lines))
        m = self.s.json("/api/sessions")[1]
        self.assertFalse(m["chain"]["ok"])
        for p in ("/api/preview", "/api/rewind"):
            code, j = self.s.json(p, method="POST", body={"session": "s1", "step": 1, "confirm": True})
            self.assertEqual(code, 409)
            self.assertIn("does not verify", j["error"])
        self.assertIn("raise SystemExit", (self.d / "app.py").read_text())

    @unittest.skipUnless(ui.only_supported(), "rewind --only is not in this tree")
    def test_rewind_just_this_file(self):
        code, p = self.s.json("/api/preview", method="POST", body={"session": "s1", "step": 2, "path": "app.py"})
        self.assertEqual(code, 200, p)
        self.assertEqual([c["path"] for c in p["changes"]], ["app.py"])
        code, r = self.s.json("/api/rewind", method="POST",
                              body={"session": "s1", "step": 2, "path": "app.py", "confirm": True})
        self.assertEqual(code, 200, r)
        self.assertEqual((self.d / "app.py").read_text(), "def main():\n    return 2\n")
        self.assertTrue((self.d / "junk.py").exists())          # the other file stays
        self.assertEqual(log.read(self.a.log)[-1]["args"]["only"], ["app.py"])
        self.assertTrue(self.s.json("/api/sessions")[1]["can_only"])


if __name__ == "__main__":
    unittest.main()
