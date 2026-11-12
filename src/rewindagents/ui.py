"""`rewindagents ui`: the flight recorder's timeline, served on your own machine.

A small web page over the log: the sessions on the left, the chosen session as a vertical timeline of
steps in the middle (tool, file or command, time, files changed with +/- line counts, checkpoints, rewind
steps), and the chosen step on the right (each file's diff, the input and the result). From any step you
can preview what rewinding to it would change and then rewind, through the same code `rewindagents rewind`
runs: the hash chain is verified first, the rewind is recorded as a new step, and it can be undone.

Standard library only (http.server). How it is locked down:
- It listens on 127.0.0.1 only; asking for any other address is refused. The port is a free one picked by
  the system unless --port is given.
- Every request, page and API alike, must carry this run's random token in the URL (?t=...), compared in
  constant time. The token is new each time the command starts.
- The Host header must be 127.0.0.1:PORT or localhost:PORT, so a web page that points its own domain name
  at 127.0.0.1 (DNS rebinding) gets a 403.
- Actions are POST only, with a JSON body and an Origin header naming this server. No CORS headers.
- Responses carry a strict Content-Security-Policy (no inline script or style: /app.css and /app.js are
  separate files), no-referrer, no-store, and nothing on the page is fetched from anywhere else.
- A client never names a file path: "rewind just this file" sends a path that must be one the session
  checkpointed, and is mapped back to the logged absolute path on the server.
"""
from __future__ import annotations

import hmac
import inspect
import json
import secrets
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from . import __version__, export, log, rewind, sessions

try:                                   # `rewindagents diff`: the same plan as rewind, with a diff per file
    from . import diff as _diffmod
except ImportError:                    # older tree: fall back to the dry-run plan + export's diff code
    _diffmod = None

HOST = "127.0.0.1"
MAX_BODY = 16 * 1024          # bytes of JSON an action may send
MAX_TEXT = 20_000             # characters of a step's input or result shown before "... n more"
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; "
       "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
GET_ROUTES = ("/", "/app.css", "/app.js", "/favicon.svg", "/api/sessions", "/api/session", "/api/step")
POST_ROUTES = ("/api/preview", "/api/rewind")


class UIError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def only_supported() -> bool:
    """True when rewind.rewind() takes `only` (rewind a single file). The button is hidden otherwise."""
    try:
        return "only" in inspect.signature(rewind.rewind).parameters
    except (TypeError, ValueError):
        return False


def _only_arg(path: str) -> Any:
    """`only` as rewind.rewind() declares it: a list of paths, or one path."""
    ann = str(inspect.signature(rewind.rewind).parameters["only"].annotation)
    return [path] if any(w in ann for w in ("list", "List", "Sequence", "Iterable", "tuple", "set")) else path


# ---------------------------------------------------------------------------------------------- data

def _clip(text: str) -> str:
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + f"\n... {len(text) - MAX_TEXT:,} more characters"


def _counts(change: dict | None) -> dict:
    """+/- line counts of one file's diff as the page shows it; `cut` when the diff was cut."""
    if not change or change.get("kind") != "diff":
        return {"adds": None, "dels": None, "cut": False, "note": (change or {}).get("note", "")}
    lines = change["lines"]
    adds = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
    dels = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
    return {"adds": adds, "dels": dels, "cut": bool(change.get("more")), "note": ""}


def overview(log_path: str | Path, initial: str | None = None) -> dict:
    """The session list and the log's state."""
    path = Path(log_path)
    root = rewind.project_root(path)
    out: dict[str, Any] = {"project": root.name, "log": rewind.relative(path.absolute(), root),
                           "exists": path.is_file(), "sessions": [], "initial": None,
                           "can_only": only_supported(), "version": __version__,
                           "chain": {"ok": True, "records": 0, "msg": "no log"}}
    if not out["exists"]:
        return out
    ok, n, msg = log.verify(path)
    out["chain"] = {"ok": ok, "records": n, "msg": msg}
    found = sessions.sessions(path)
    out["sessions"] = [{"session": e["session"], "first": sessions.when(e["first"]), "last": sessions.when(e["last"]),
                        "steps": e["steps"], "rewinds": e["rewinds"], "files": len(e["files"]),
                        "latest": e["latest"]} for e in reversed(found)]
    ids = {e["session"] for e in found}
    out["initial"] = initial if initial in ids else rewind.latest_session(path)
    return out


def _session_ids(log_path: str | Path) -> set[str]:
    if not Path(log_path).is_file():
        return set()
    return {r["session"] for r in log.read(log_path)}


def _check_session(log_path: str | Path, session: Any) -> str:
    if not isinstance(session, str) or session not in _session_ids(log_path):
        raise UIError(404, "no such session")
    return session


def _build(log_path: str | Path, session: str) -> tuple[dict, list[dict], dict[int, float]]:
    try:
        data = export.build(log_path, session, contents=True, redact=False)  # 127.0.0.1 only: nothing leaves
    except export.ExportError as e:
        raise UIError(404, str(e))
    raw = rewind.steps(log_path, session)
    ts = {r["seq"]: r["ts"] for r in log.read(log_path, session)}
    return data, raw, ts


def _step_row(s: dict, raw: dict, ts: dict[int, float], undone_by: int | None) -> dict:
    files = []
    for f in s["files"]:
        files.append({"path": f["path"], **_counts(f.get("change"))})
    t = ts.get(raw["seq"])
    scan = s.get("bash_scan") or {}
    return {"step": s["step"], "tool": s["tool"], "agent": raw.get("agent"), "event": s["event"],
            "summary": s["summary"], "time": time.strftime("%H:%M:%S", time.localtime(t)) if t else "",
            "when": sessions.when(t) if t else "", "files": files, "checkpoints": len(raw["checkpoints"]),
            "to_step": s.get("to_step"), "branch": (s.get("branch") or {}).get("name"), "only": raw.get("only"),
            "unscanned": scan.get("skipped"), "scan_early": bool(scan.get("early")), "undone_by": undone_by}


def timeline(log_path: str | Path, session: Any) -> dict:
    """One session as timeline rows (no inputs, results or diff lines: those come per step)."""
    session = _check_session(log_path, session)
    data, raw, ts = _build(log_path, session)
    undone: dict[int, int] = {}
    for s in data["steps"]:                     # a rewind to t at step k undid the steps t+1 .. k-1
        if s["event"] in ("rewind", "branch") and s.get("to_step") is not None:
            for j in range(s["to_step"] + 1, s["step"]):
                undone.setdefault(j, s["step"])
    rows = [_step_row(s, r, ts, undone.get(s["step"])) for s, r in zip(data["steps"], raw)]
    return {"session": session, "steps": rows, "chain": {"ok": data["chain_ok"], "msg": data["chain_msg"],
            "records": data["records"], "head": data["head"][:12]}}


def step_detail(log_path: str | Path, session: Any, n: Any) -> dict:
    """One step in full: input, result and each file's diff (cut like `export` cuts them)."""
    session = _check_session(log_path, session)
    try:
        n = int(n)
    except (TypeError, ValueError):
        raise UIError(400, "step must be a number")
    data, raw, ts = _build(log_path, session)
    if not 1 <= n <= len(data["steps"]):
        raise UIError(404, f"step {n} is out of range (1-{len(data['steps'])})")
    s = data["steps"][n - 1]
    roots = data["roots"]
    row = _step_row(s, raw[n - 1], ts, None)
    row["input"] = _clip(export.scrub(json.dumps(s["input"], indent=2, ensure_ascii=False, default=str), roots))
    row["result"] = None if s["result"] is None else _clip(
        export.scrub(json.dumps(s["result"], indent=2, ensure_ascii=False, default=str), roots))
    row["files"] = [{"path": f["path"], "before": f["before"], "after": f.get("after"),
                     "change": f.get("change"), **_counts(f.get("change"))} for f in s["files"]]
    return row


def _target(log_path: str | Path, session: str, rel: Any) -> str:
    """The logged absolute path of a file the session checkpointed, from its project-relative name."""
    if not isinstance(rel, str) or not rel:
        raise UIError(400, "path must be a file the session changed")
    root = rewind.project_root(log_path)
    for s in rewind.steps(log_path, session):
        for cp in s["checkpoints"]:
            if rewind.relative(cp["path"], root) == rel:
                return cp["path"]
    raise UIError(400, "path must be a file the session changed")


def _step_arg(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise UIError(400, "step must be a whole number, 0 or more")
    return value


def _plan_view(log_path: str | Path, p: dict, only: str | None, diffs: bool) -> dict:
    root = rewind.project_root(log_path)
    objects = root / ".rewindagents" / "objects"
    keep = (lambda path: path == only) if only else (lambda path: True)
    changes = []
    for path, sha in p["restore"]:
        if keep(path):
            rel = rewind.relative(path, root)
            item: dict[str, Any] = {"path": rel, "action": "restore"}
            if diffs:
                now = Path(path).read_bytes() if Path(path).is_file() else None
                item["change"] = export.file_change(now, (objects / sha).read_bytes(), f"{rel} (now)",
                                                    f"{rel} (after step {p['to_step']})")
            changes.append(item)
    for path in p["delete"]:
        if keep(path):
            rel = rewind.relative(path, root)
            item = {"path": rel, "action": "delete"}
            if diffs:
                now = Path(path).read_bytes() if Path(path).is_file() else None
                item["change"] = export.file_change(now, None, f"{rel} (now)", f"{rel} (after step {p['to_step']})")
            changes.append(item)
    cannot = [{"path": rewind.relative(path, root), "why": why} for path, why in p["cannot"] if keep(path)]
    return {"session": p["session"], "to_step": p["to_step"], "steps": p["steps"], "changes": changes,
            "cannot": cannot, "bash_uncovered": p["bash_uncovered"], "scan_early": p["scan_early"], "only": rewind.relative(only, root) if only else None,
            "new_step": p["steps"] + 1}


def preview(log_path: str | Path, body: dict) -> dict:
    """What `rewind N` (or N for one file) would change: the dry-run plan, with each file's diff from now."""
    session = _check_session(log_path, body.get("session"))
    n = _step_arg(body.get("step"))
    only = None
    if body.get("path") is not None:
        if not only_supported():
            raise UIError(400, "this version cannot rewind a single file")
        only = _target(log_path, session, body["path"])
    try:
        if _diffmod is not None and hasattr(_diffmod, "diff"):
            p = _diffmod.diff(log_path, n, session, paths=[only] if only else None)
            if only and p.get("unmatched") and len(p["unmatched"]) == 1:
                raise rewind.RewindError(f"no step after step {n} changed {body['path']}; nothing to put back")
            out = _plan_view(log_path, p, only, diffs=False)
            texts = {rewind.relative(path, rewind.project_root(log_path)): text for path, text in p["files"]}
            for c in out["changes"]:
                c["change"] = _diff_lines(texts.get(c["path"], ""))
            return out
        p = rewind.rewind(log_path, n, session, dry_run=True, **({"only": _only_arg(only)} if only else {}))
    except rewind.RewindError as e:
        raise UIError(409, str(e))
    return _plan_view(log_path, p, only, diffs=True)


def _diff_lines(text: str) -> dict:
    """diff.py's git-style text as the page's diff shape, cut at export's line limit."""
    lines = text.splitlines()
    return {"kind": "diff", "lines": lines[:export.MAX_DIFF_LINES], "more": max(0, len(lines) - export.MAX_DIFF_LINES),
            "note": ""}


def do_rewind(log_path: str | Path, body: dict) -> dict:
    """Rewind through rewind.rewind(), the code `rewindagents rewind` runs. Needs {"confirm": true}."""
    session = _check_session(log_path, body.get("session"))
    n = _step_arg(body.get("step"))
    if body.get("confirm") is not True:
        raise UIError(400, "a rewind needs confirm: true")
    only = None
    if body.get("path") is not None:
        if not only_supported():
            raise UIError(400, "this version cannot rewind a single file")
        only = _target(log_path, session, body["path"])
    try:
        if only:
            p = rewind.rewind(log_path, n, session, only=_only_arg(only))
        else:
            p = rewind.rewind(log_path, n, session)
    except rewind.RewindError as e:
        raise UIError(409, str(e))
    out = _plan_view(log_path, p, only, diffs=False)
    out.update(record=p.get("record"), undo_to=p["steps"])
    return out


# ---------------------------------------------------------------------------------------------- server

class UIServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, log_path: str | Path, host: str = HOST, port: int = 0, session: str | None = None):
        if host != HOST:
            raise ValueError(f"rewindagents ui only listens on {HOST}, not {host!r}")
        if not isinstance(port, int) or not 0 <= port <= 65535:
            raise ValueError(f"port must be 0-65535, not {port!r}")
        self.log_path = str(Path(log_path).absolute())
        self.token = secrets.token_urlsafe(32)
        self.initial = session
        self.action_lock = threading.Lock()
        super().__init__((host, port), Handler)

    @property
    def port(self) -> int:
        return self.server_address[1]

    @property
    def hosts(self) -> set[str]:
        return {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}

    @property
    def origins(self) -> set[str]:
        return {f"http://{h}" for h in self.hosts}

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/?t={self.token}"


def make_server(log_path: str | Path, port: int = 0, session: str | None = None, host: str = HOST) -> UIServer:
    return UIServer(log_path, host=host, port=port, session=session)


class Handler(BaseHTTPRequestHandler):
    server: UIServer
    server_version = "rewindagents"
    sys_version = ""

    def log_message(self, format: str, *args: Any) -> None:   # the URL holds the token: keep it off stderr
        pass

    def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, obj: Any, extra: dict | None = None) -> None:
        self._send(status, json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"),
                   "application/json; charset=utf-8", extra)

    def _guard(self) -> tuple[str, dict] | None:
        """Host and token checks for every request. Sends the 403 itself and returns None on failure."""
        host = (self.headers.get("Host") or "").strip().lower()
        parts = urlsplit(self.path)
        given = (parse_qs(parts.query).get("t") or [""])[0]
        token_ok = hmac.compare_digest(given.encode("utf-8"), self.server.token.encode("utf-8"))
        if host not in self.server.hosts or not token_ok:
            self._json(403, {"error": "forbidden"})
            return None
        return parts.path, parse_qs(parts.query)

    def do_GET(self) -> None:
        g = self._guard()
        if g is None:
            return
        path, q = g
        if path in POST_ROUTES:
            self._json(405, {"error": "use POST"}, {"Allow": "POST"})
            return
        if path not in GET_ROUTES:
            self._json(404, {"error": "not found"})
            return
        try:
            if path == "/":
                self._send(200, PAGE.replace("{token}", self.server.token).encode("utf-8"), "text/html; charset=utf-8")
            elif path == "/app.css":
                self._send(200, CSS.encode("utf-8"), "text/css; charset=utf-8")
            elif path == "/app.js":
                self._send(200, JS.encode("utf-8"), "text/javascript; charset=utf-8")
            elif path == "/favicon.svg":
                self._send(200, MARK_SVG.encode("utf-8"), "image/svg+xml")
            elif path == "/api/sessions":
                self._json(200, overview(self.server.log_path, self.server.initial))
            elif path == "/api/session":
                self._json(200, timeline(self.server.log_path, (q.get("s") or [None])[0]))
            elif path == "/api/step":
                self._json(200, step_detail(self.server.log_path, (q.get("s") or [None])[0], (q.get("n") or [None])[0]))
        except UIError as e:
            self._json(e.status, {"error": str(e)})

    def do_POST(self) -> None:
        g = self._guard()
        if g is None:
            return
        path, _ = g
        if path in GET_ROUTES:
            self._json(405, {"error": "use GET"}, {"Allow": "GET"})
            return
        if path not in POST_ROUTES:
            self._json(404, {"error": "not found"})
            return
        if self.headers.get("Origin") not in self.server.origins:
            self._json(403, {"error": "forbidden"})
            return
        if self.headers.get("Sec-Fetch-Site", "same-origin") != "same-origin":
            self._json(403, {"error": "forbidden"})
            return
        if (self.headers.get("Content-Type") or "").split(";")[0].strip().lower() != "application/json":
            self._json(415, {"error": "send application/json"})
            return
        try:
            length = int(self.headers.get("Content-Length") or "-1")
        except ValueError:
            length = -1
        if not 0 <= length <= MAX_BODY:
            self._json(413, {"error": f"body must be 0-{MAX_BODY} bytes"})
            return
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                raise ValueError
        except ValueError:
            self._json(400, {"error": "body is not a JSON object"})
            return
        try:
            if path == "/api/preview":
                self._json(200, preview(self.server.log_path, body))
            else:
                with self.server.action_lock:
                    self._json(200, do_rewind(self.server.log_path, body))
        except UIError as e:
            self._json(e.status, {"error": str(e)})

    def _not_allowed(self) -> None:
        if self._guard() is not None:
            self._json(405, {"error": "method not allowed"}, {"Allow": "GET, POST"})

    do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_HEAD = _not_allowed


def run(log_path: str | Path, session: str | None = None, port: int = 0, open_browser: bool = True) -> int:
    """The `ui` command: serve until Ctrl+C."""
    try:
        srv = make_server(log_path, port=port, session=session)
    except ValueError as e:
        print(f"rewindagents: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"rewindagents: cannot listen on {HOST}:{port}: {e.strerror or e}", file=sys.stderr)
        return 1
    print(f"rewindagents timeline: {srv.url}", flush=True)
    print("Only this machine can open it, and only with that link. Ctrl+C stops it.", flush=True)
    if open_browser:
        webbrowser.open(srv.url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped", flush=True)
    finally:
        srv.server_close()
    return 0


# ---------------------------------------------------------------------------------------------- page
# BRAND.md palette (export.PALETTE), type with system fallbacks: nothing is fetched, the page works offline.

MARK_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">'
            '<rect width="16" height="16" fill="#F2F4F1"/>'
            '<path d="M6 3L9.5 3L4.5 8L9.5 13L6 13L1 8Z" fill="#121412"/>'
            '<rect x="10.5" y="10.5" width="4.5" height="2.5" fill="#B82A16"/></svg>')

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>rewindagents timeline</title>
<link rel="icon" href="/favicon.svg?t={token}" type="image/svg+xml">
<link rel="stylesheet" href="/app.css?t={token}">
<script src="/app.js?t={token}" defer></script>
</head>
<body>
<header class="bar">
  <span class="brand"><svg class="mark" viewBox="0 0 16 16" aria-hidden="true"><path d="M6 3L9.5 3L4.5 8L9.5 13L6 13L1 8Z"/><rect class="cursor" x="10.5" y="10.5" width="4.5" height="2.5"/></svg><span class="name">rewindagents</span></span>
  <span class="project" id="project"></span>
  <span class="chain" id="chain"></span>
  <span class="keys"><kbd>j</kbd><kbd>k</kbd> step <kbd>d</kbd> diffs <kbd>r</kbd> rewind</span>
</header>
<div class="app" id="app">
  <nav class="sessions" aria-label="Sessions"><h2>Sessions</h2><ul id="sessions"></ul></nav>
  <section class="timeline" aria-label="Timeline"><div class="thead" id="thead"></div><ol id="steps"></ol></section>
  <section class="detail" id="detail" aria-live="polite"></section>
</div>
<div class="empty" id="empty" hidden></div>
<dialog id="dlg" aria-labelledby="dlg-title">
  <h2 id="dlg-title"></h2>
  <p class="lead" id="dlg-lead"></p>
  <div class="plan" id="dlg-plan"></div>
  <div class="actions"><button type="button" class="btn" id="dlg-cancel">Cancel</button><button type="button" class="btn primary" id="dlg-go" disabled>Rewind</button></div>
</dialog>
<footer class="foot"><span>made by John B Joseph</span><span id="ver"></span></footer>
</body>
</html>
"""
# {token} is filled in per request; only a request that already carried the token gets the page.

CSS = """
:root{--leader:%(Leader)s;--reel:%(Reel)s;--spool:%(Spool)s;--tape:%(Tape)s;--record:%(Record)s;--rewind:%(Rewind)s;
--playhead:%(Playhead)s;--rule:%(Rule)s;
--display:"Bricolage Grotesque",system-ui,-apple-system,"Segoe UI",sans-serif;
--body:"Hanken Grotesk",system-ui,-apple-system,"Segoe UI",sans-serif;
--mono:"Commit Mono",ui-monospace,"SF Mono",Menlo,Consolas,monospace}
*{box-sizing:border-box}
html,body{height:100%%}
body{margin:0;background:var(--leader);color:var(--reel);font:15px/1.5 var(--body);display:flex;flex-direction:column}
button{font:inherit;color:inherit}
kbd,code,.mono{font-family:var(--mono)}
.bar{display:flex;align-items:center;gap:20px;padding:10px 20px;border-bottom:1px solid var(--rule);flex:none}
.brand{display:flex;align-items:center;gap:8px}
.mark{width:22px;height:22px;fill:var(--reel)}
.mark .cursor{fill:var(--record)}
.name{font:800 20px/1 var(--display);letter-spacing:-.02em}
.project{font-family:var(--mono);font-size:13px;color:var(--tape)}
.chain{font-size:13px;color:var(--tape)}
.chain.bad{color:var(--record);font-weight:600}
.keys{margin-left:auto;font-size:12px;color:var(--tape)}
.keys kbd{display:inline-block;min-width:1.6em;text-align:center;border:1px solid var(--rule);border-radius:3px;padding:0 4px;margin:0 2px;font-size:11px;color:var(--reel)}
.app{flex:1;min-height:0;display:grid;grid-template-columns:240px minmax(360px,1fr) minmax(420px,1.25fr)}
.sessions{border-right:1px solid var(--rule);overflow:auto;padding:16px 0}
h2{font:700 12px/1 var(--body);text-transform:uppercase;letter-spacing:.06em;color:var(--tape);margin:0 16px 10px}
.sessions ul{list-style:none;margin:0;padding:0}
.sessions button{display:block;width:100%%;text-align:left;background:none;border:0;border-left:3px solid transparent;padding:8px 13px;cursor:pointer}
.sessions button:hover{background:rgba(18,20,18,.05)}
.sessions button[aria-current=true]{border-left-color:var(--reel);background:rgba(18,20,18,.06)}
.sessions .sid{font-family:var(--mono);font-size:13px;font-weight:700;overflow-wrap:anywhere}
.sessions .latest{font:600 10px/1 var(--body);text-transform:uppercase;letter-spacing:.06em;color:var(--tape);margin-left:6px}
.sessions .sm{display:block;font-size:12px;color:var(--tape)}
.timeline{background:var(--spool);color:var(--leader);overflow:hidden;display:flex;flex-direction:column;min-height:0}
.thead{flex:none;padding:16px 20px 12px;border-bottom:1px solid #2c322e}
.thead .t1{font:800 18px/1.2 var(--display);letter-spacing:-.02em}
.thead .t2{font-size:12px;color:var(--playhead);margin-top:4px}
.timeline ol{list-style:none;margin:0;padding:8px 0 40px;flex:1;min-height:0;overflow:auto}
.step{position:relative}
.step::before{content:"";position:absolute;left:62px;top:0;bottom:0;border-left:1px solid var(--rule)}
.step>button{display:grid;grid-template-columns:44px 1fr;gap:0 24px;width:100%%;text-align:left;background:none;border:0;border-left:3px solid transparent;padding:9px 18px 9px 13px;cursor:pointer;position:relative}
.step>button::before{content:"";position:absolute;left:58px;top:17px;width:9px;height:1px;background:var(--rule)}
.step>button:hover{background:rgba(242,244,241,.04)}
.step.sel>button{border-left-color:var(--rewind);background:var(--reel)}
.step.sel>button::before{background:var(--rewind);height:3px;top:16px}
.n{font-family:var(--mono);font-variant-numeric:tabular-nums;text-align:right;color:var(--playhead);font-size:13px;padding-top:1px}
.step.sel .n{color:var(--rewind);font-weight:700}
.top{display:flex;gap:10px;align-items:baseline}
.tool{font-weight:700;font-size:14px}
.agent{font-size:11px;color:var(--playhead);border:1px solid #3a413c;border-radius:3px;padding:0 5px}
.time{margin-left:auto;font-family:var(--mono);font-size:12px;color:var(--playhead);font-variant-numeric:tabular-nums}
.what{display:block;font-family:var(--mono);font-size:13px;color:var(--leader);overflow-wrap:anywhere;margin-top:1px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:5px}
.chip{font-family:var(--mono);font-size:11.5px;color:var(--playhead);border:1px solid #3a413c;border-radius:3px;padding:1px 6px}
.chip .a{color:var(--leader);font-weight:700}
.chip .d{color:var(--playhead)}
.chip.cp{border-style:dashed}
.chip.rw{color:var(--reel);background:var(--rewind);border-color:var(--rewind);font-weight:700}
.chip.warn{color:var(--leader);border-color:var(--playhead)}
.step.undone .what,.step.undone .tool{color:var(--playhead);text-decoration:line-through;text-decoration-color:var(--rule)}
.step.isrw>button{background:rgba(255,122,89,.07)}
.step.isrw.sel>button{background:var(--reel)}
.detail{overflow:auto;padding:20px 24px 48px}
.detail h1{font:800 26px/1.15 var(--display);letter-spacing:-.02em;margin:0}
.detail .sub{font-family:var(--mono);font-size:13px;color:var(--tape);margin:6px 0 0;overflow-wrap:anywhere}
.detail .meta{font-size:13px;color:var(--tape);margin:6px 0 0}
.acts{display:flex;flex-wrap:wrap;gap:10px;margin:16px 0 4px}
.btn{border:1px solid var(--reel);background:var(--leader);color:var(--reel);border-radius:3px;padding:7px 14px;font-weight:600;font-size:14px;cursor:pointer}
.btn:hover{background:rgba(18,20,18,.06)}
.btn.primary{background:var(--record);border-color:var(--record);color:var(--leader)}
.btn.primary:hover{background:#9e2412}
.btn.small{padding:2px 8px;font-size:12px;font-weight:600}
.btn:disabled{opacity:.45;cursor:default}
.btn:focus-visible,.sessions button:focus-visible,.step>button:focus-visible{outline:2px solid var(--record);outline-offset:2px}
.hint{font-size:13px;color:var(--tape);margin:4px 0 0}
.flash{border:1px solid var(--reel);padding:10px 12px;margin:0 0 16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;font-size:14px}
.flash.err{border-color:var(--record);color:var(--record)}
h3{font:700 12px/1 var(--body);text-transform:uppercase;letter-spacing:.06em;color:var(--tape);margin:24px 0 8px}
.file{margin:0 0 14px}
.fh{display:flex;gap:10px;align-items:center;flex-wrap:wrap;font-size:13px;margin:0 0 6px}
.fh code{font-weight:700;font-size:13px}
.fh .cnt{font-family:var(--mono);font-size:12px;color:var(--tape)}
pre{margin:0;background:var(--spool);color:var(--leader);padding:12px;overflow:auto;font:12.5px/1.5 var(--mono);border-radius:3px;max-height:420px;white-space:pre}
pre.diff .add{color:var(--rewind)}
pre.diff .del{color:var(--playhead);text-decoration:line-through}
pre.diff .hunk{color:var(--playhead)}
body.nodiff .diffbox{display:none}
.note{color:var(--tape);font-size:13px;margin:4px 0 0}
details.io{margin:14px 0 0;border-top:1px solid var(--rule);padding-top:8px}
details.io summary{cursor:pointer;font:700 12px/1.8 var(--body);text-transform:uppercase;letter-spacing:.06em;color:var(--tape)}
details.io pre{margin-top:6px}
.planbox{border:1px solid var(--rule);padding:12px 14px;margin:14px 0 0}
.planbox h4,.plan h4{margin:0 0 8px;font:700 14px/1.3 var(--body)}
.pl{list-style:none;margin:0 0 6px;padding:0}
.pl li{margin:0 0 10px}
.pl .act{display:inline-block;font:700 11px/1.6 var(--mono);text-transform:uppercase;letter-spacing:.04em;min-width:64px;color:var(--tape)}
.pl .act.cannot{color:var(--record)}
.empty{flex:1;display:flex;align-items:center;justify-content:center;padding:40px}
.empty[hidden]{display:none}
.empty .box{max-width:560px}
.empty h1{font:800 32px/1.1 var(--display);letter-spacing:-.02em;margin:0 0 12px}
.empty pre{margin:16px 0}
dialog{border:1px solid var(--reel);border-radius:4px;background:var(--leader);color:var(--reel);width:min(760px,92vw);max-height:86vh;padding:22px 24px;overflow:auto}
dialog::backdrop{background:rgba(18,20,18,.55)}
dialog h2{font:800 22px/1.2 var(--display);letter-spacing:-.02em;color:var(--reel);text-transform:none;margin:0 0 6px}
dialog .lead{margin:0 0 12px;font-size:14px}
dialog .actions{display:flex;justify-content:flex-end;gap:10px;margin-top:16px;position:sticky;bottom:-22px;background:var(--leader);padding:12px 0 2px}
.foot{flex:none;display:flex;justify-content:space-between;padding:6px 20px;border-top:1px solid var(--rule);font-size:12px;color:var(--tape)}
@media (max-width:1100px){.app{grid-template-columns:200px 1fr;grid-template-rows:minmax(0,1fr) minmax(0,1fr)}.detail{grid-column:1/-1;border-top:1px solid var(--rule)}.keys{display:none}}
""" % export.PALETTE

JS = r"""
(function () {
"use strict";
var T = new URLSearchParams(location.search).get("t") || "";
var S = {meta: null, session: null, rows: [], sel: -1, detail: null, flash: null, flashStep: null};
var $ = function (id) { return document.getElementById(id); };

function apiUrl(p, params) {
  var u = new URLSearchParams({t: T});
  if (params) Object.keys(params).forEach(function (k) { u.set(k, params[k]); });
  return p + "?" + u.toString();
}
function req(p, params, body) {
  var opt = {cache: "no-store", credentials: "same-origin"};
  if (body !== undefined) { opt.method = "POST"; opt.headers = {"Content-Type": "application/json"}; opt.body = JSON.stringify(body); }
  return fetch(apiUrl(p, params), opt).then(function (r) {
    return r.json().catch(function () { return {error: r.status + " " + r.statusText}; }).then(function (j) {
      if (!r.ok) throw new Error(j.error || ("HTTP " + r.status));
      return j;
    });
  });
}
function el(tag, cls, text) {
  var e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined && text !== null) e.textContent = String(text);
  return e;
}
function add(parent) { for (var i = 1; i < arguments.length; i++) if (arguments[i]) parent.appendChild(arguments[i]); return parent; }
function clear(e) { while (e.firstChild) e.removeChild(e.firstChild); return e; }
function plural(n, w) { return n + " " + w + (n === 1 ? "" : "s"); }

function chipFile(f) {
  var c = el("span", "chip");
  c.appendChild(document.createTextNode(f.path + " "));
  if (f.adds === null || f.adds === undefined) { c.appendChild(el("span", "d", f.note || "")); return c; }
  add(c, el("span", "a", "+" + f.adds), document.createTextNode(" "), el("span", "d", "-" + f.dels + (f.cut ? " (cut)" : "")));
  return c;
}

function boot() {
  req("/api/sessions").then(function (m) {
    S.meta = m;
    $("ver").textContent = "rewindagents " + m.version;
    $("project").textContent = m.project + "  " + m.log;
    var ch = $("chain");
    ch.textContent = m.exists ? (m.chain.ok ? "log verifies: " + plural(m.chain.records, "record") + ", chain intact" : "log does not verify: " + m.chain.msg) : "";
    ch.className = "chain" + (m.chain.ok ? "" : " bad");
    if (!m.exists || !m.sessions.length) return empty(m);
    renderSessions();
    return openSession(S.session || m.initial);
  }).catch(fatal);
}

function empty(m) {
  $("app").hidden = true;
  var box = el("div", "box");
  add(box, el("h1", "", "Nothing recorded here yet"),
    el("p", "", m.exists ? "The log at " + m.log + " has no sessions in it yet. Start your coding agent in this project and its steps appear here." :
      "There is no log at " + m.log + ". Run this in your project to set up the recorder for your agent, then start the agent:"),
    m.exists ? null : el("pre", "", "rewindagents init"),
    el("p", "hint", "Then run rewindagents ui again from the same folder."));
  var e = $("empty"); clear(e).appendChild(box); e.hidden = false;
}

function fatal(err) {
  var d = clear($("detail"));
  add(d, el("div", "flash err", String(err && err.message || err)));
}

function renderSessions() {
  var ul = clear($("sessions"));
  S.meta.sessions.forEach(function (s) {
    var b = el("button");
    b.type = "button";
    b.setAttribute("aria-current", s.session === S.session ? "true" : "false");
    var top = el("span", "sid", s.session);
    add(b, top, s.latest ? el("span", "latest", "latest") : null,
      el("span", "sm", s.first.slice(0, 16) + " to " + s.last.slice(11, 16)),
      el("span", "sm", plural(s.steps, "step") + ", " + plural(s.files, "file") + (s.rewinds ? ", " + plural(s.rewinds, "rewind") : "")));
    b.addEventListener("click", function () { S.flash = null; openSession(s.session); });
    add(ul, add(el("li"), b));
  });
}

function openSession(id, selectStep) {
  return req("/api/session", {s: id}).then(function (t) {
    S.session = t.session; S.rows = t.steps;
    renderSessions();
    var th = clear($("thead"));
    var files = {};
    t.steps.forEach(function (r) { r.files.forEach(function (f) { files[f.path] = 1; }); });
    add(th, el("div", "t1", "Session " + t.session),
      el("div", "t2", plural(t.steps.length, "step") + ", " + plural(Object.keys(files).length, "file") + " changed. Head " + t.chain.head + "."));
    renderSteps();
    select(selectStep ? selectStep - 1 : t.steps.length - 1);
  }).catch(fatal);
}

function renderSteps() {
  var ol = clear($("steps"));
  S.rows.forEach(function (r, i) {
    var li = el("li", "step" + (r.event === "rewind" || r.event === "branch" ? " isrw" : "") + (r.undone_by ? " undone" : ""));
    var b = el("button"); b.type = "button";
    b.setAttribute("aria-label", "Step " + r.step + ", " + r.tool + ", " + r.summary);
    var body = el("span");
    var top = add(el("span", "top"), el("span", "tool", r.event === "rewind" ? "Rewind" : r.event === "branch" ? "Branch" : r.tool),
      r.agent ? el("span", "agent", r.agent) : null, el("span", "time", r.time));
    top.lastChild.title = r.when;
    var chips = el("span", "chips");
    if (r.event === "rewind" || r.event === "branch") add(chips, el("span", "chip rw", "<< to step " + r.to_step + (r.only ? ", only " + r.only.join(", ") : "") + (r.branch ? ", branch " + r.branch : "")));
    r.files.slice(0, 4).forEach(function (f) { add(chips, chipFile(f)); });
    if (r.files.length > 4) add(chips, el("span", "chip", "+" + (r.files.length - 4) + " more"));
    if (r.checkpoints) add(chips, el("span", "chip cp", plural(r.checkpoints, "checkpoint")));
    if (r.unscanned) add(chips, el("span", "chip warn", "not scanned: " + r.unscanned));
    if (r.scan_early) add(chips, el("span", "chip warn", "background: scan may be early"));
    if (r.undone_by) add(chips, el("span", "chip", "rewound by step " + r.undone_by));
    add(body, top, r.event === "rewind" || r.event === "branch" ? null : el("span", "what", r.summary), chips.childNodes.length ? chips : null);
    add(b, el("span", "n", r.step), body);
    b.addEventListener("click", function () { select(i); });
    add(ol, add(li, b));
  });
}

function select(i) {
  if (!S.rows.length) return;
  i = Math.max(0, Math.min(S.rows.length - 1, i));
  S.sel = i;
  var items = $("steps").children;
  for (var k = 0; k < items.length; k++) items[k].classList.toggle("sel", k === i);
  var btn = items[i].firstChild;
  btn.scrollIntoView({block: "nearest"});
  if (document.activeElement && document.activeElement.closest && document.activeElement.closest("#steps")) btn.focus({preventScroll: true});
  var r = S.rows[i];
  req("/api/step", {s: S.session, n: r.step}).then(function (d) {
    if (S.rows[S.sel] !== r) return;
    S.detail = d; renderDetail(d);
  }).catch(fatal);
}

function diffBox(change) {
  var box = el("div", "diffbox");
  if (!change) return box;
  if (change.kind === "note") { add(box, el("p", "note", change.note)); return box; }
  var pre = el("pre", "diff");
  change.lines.forEach(function (l, i) {
    var cls = /^(@@|---|\+\+\+)/.test(l) ? "hunk" : l.charAt(0) === "+" ? "add" : l.charAt(0) === "-" ? "del" : "";
    add(pre, cls ? el("span", cls, l) : document.createTextNode(l), document.createTextNode("\n"));
  });
  if (change.more) add(pre, el("span", "hunk", "... " + change.more + " more lines"));
  return add(box, pre);
}

function renderDetail(d) {
  var box = clear($("detail"));
  if (S.flash && S.flashStep === d.step) box.appendChild(S.flash);
  var isRw = d.event === "rewind" || d.event === "branch";
  add(box, el("h1", "", "Step " + d.step + " " + (isRw ? (d.event === "branch" ? "Branch" : "Rewind") : d.tool)),
    el("p", "sub", isRw ? "Put the files back the way they were right after step " + d.to_step + (d.branch ? "; previous files kept as branch " + d.branch : "") + "." : d.summary),
    el("p", "meta", d.when + (d.agent ? "  |  " + d.agent : "") + "  |  " + plural(d.files.length, "file") + " changed"));
  var acts = el("div", "acts");
  var pv = el("button", "btn", "Preview rewind to here"); pv.type = "button";
  var go = el("button", "btn primary", "Rewind to here"); go.type = "button";
  pv.addEventListener("click", function () { inlinePreview(d.step); });
  go.addEventListener("click", function () { confirmRewind(d.step, null); });
  if (!S.meta.chain.ok) { pv.disabled = go.disabled = true; }
  add(box, add(acts, pv, go), el("p", "hint", "Rewind to here puts every file back the way it was right after step " + d.step + ". It is recorded as a new step, so you can undo it."));
  var slot = el("div"); slot.id = "inline"; add(box, slot);
  if (d.files.length) {
    add(box, el("h3", "", "Files this step changed"));
    d.files.forEach(function (f) {
      var fh = add(el("div", "fh"), el("code", "", f.path), el("span", "cnt", f.adds === null ? (f.note || "") : "+" + f.adds + " -" + f.dels + (f.cut ? " (diff cut)" : "")),
        el("span", "note", "before: " + f.before + (f.after ? ", after: " + f.after : "")));
      if (S.meta.can_only && !isRw) {
        var one = el("button", "btn small", "Rewind just this file"); one.type = "button";
        one.addEventListener("click", function () { confirmRewind(d.step, f.path); });
        add(fh, one);
      }
      add(box, add(el("div", "file"), fh, diffBox(f.change)));
    });
  }
  if (!isRw) {
    var inp = el("details", "io"); inp.open = !d.files.length;
    add(inp, el("summary", "", "Input"), el("pre", "", d.input));
    add(box, inp);
    var res = el("details", "io");
    add(res, el("summary", "", "Result"), d.result === null ? el("p", "note", "No result was recorded for this call.") : el("pre", "", d.result));
    add(box, res);
  }
}

function planList(p) {
  var ul = el("ul", "pl");
  p.changes.forEach(function (c) {
    var li = add(el("li"), el("span", "act", c.action), el("code", "", c.path));
    if (c.change) add(li, diffBox(c.change));
    add(ul, li);
  });
  p.cannot.forEach(function (c) { add(ul, add(el("li"), el("span", "act cannot", "cannot"), el("code", "", c.path), el("span", "note", "  " + c.why))); });
  return ul;
}
function planText(p) {
  var n = p.changes.length;
  var t = n ? "Would change " + plural(n, "file") + (p.only ? " (only " + p.only + ")" : "") + "." : "No file would change: they already match step " + p.to_step + ".";
  if (p.cannot.length) t += " " + plural(p.cannot.length, "file") + " cannot be put back.";
  if (p.bash_uncovered) t += " " + plural(p.bash_uncovered, "step") + " after step " + p.to_step + " were not scanned before and after, so files they changed stay as they are.";
  if (p.scan_early) t += " " + plural(p.scan_early, "step") + " after step " + p.to_step + " ran a command in the background; files it changed after its scan may stay as they are.";
  return t;
}

function inlinePreview(step) {
  var slot = $("inline"); clear(slot);
  var box = add(el("div", "planbox"), el("p", "note", "Working out what would change..."));
  slot.appendChild(box);
  req("/api/preview", null, {session: S.session, step: step}).then(function (p) {
    clear(box);
    add(box, el("h4", "", "If you rewind to step " + step), el("p", "note", planText(p)), planList(p));
    var go = el("button", "btn primary", "Rewind to here"); go.type = "button";
    go.addEventListener("click", function () { confirmRewind(step, null); });
    add(box, add(el("div", "acts"), go));
  }).catch(function (e) { clear(box); add(box, el("p", "flash err", e.message)); });
}

var pending = null;
function confirmRewind(step, path) {
  if (!S.meta.chain.ok) return;
  var dlg = $("dlg"), go = $("dlg-go");
  pending = {session: S.session, step: step, path: path};
  $("dlg-title").textContent = path ? "Rewind " + path + " to step " + step + "?" : "Rewind to step " + step + "?";
  $("dlg-lead").textContent = "Working out what would change...";
  clear($("dlg-plan"));
  go.disabled = true; go.textContent = "Rewind";
  if (!dlg.open) dlg.showModal();
  var body = {session: S.session, step: step};
  if (path) body.path = path;
  req("/api/preview", null, body).then(function (p) {
    if (!pending || pending.step !== step) return;
    $("dlg-lead").textContent = planText(p) + " The rewind is recorded as step " + p.new_step + " and can be undone.";
    add($("dlg-plan"), planList(p));
    go.textContent = p.changes.length ? "Rewind " + plural(p.changes.length, "file") : "Record the rewind";
    go.disabled = false; go.focus();
  }).catch(function (e) { $("dlg-lead").textContent = e.message; });
}

function doRewind() {
  if (!pending) return;
  var go = $("dlg-go"); go.disabled = true; go.textContent = "Rewinding...";
  var body = {session: pending.session, step: pending.step, confirm: true};
  if (pending.path) body.path = pending.path;
  req("/api/rewind", null, body).then(function (r) {
    $("dlg").close(); pending = null;
    var f = el("div", "flash");
    add(f, el("span", "", "Rewound to step " + r.to_step + (r.only ? " (" + r.only + ")" : "") + ": " + plural(r.changes.length, "file") + " changed" +
      (r.cannot.length ? ", " + r.cannot.length + " could not be put back" : "") + ". Recorded as step " + r.new_step + "."));
    var u = el("button", "btn small", "Undo (rewind to step " + r.undo_to + ")"); u.type = "button";
    u.addEventListener("click", function () { confirmRewind(r.undo_to, null); });
    add(f, u);
    S.flash = f; S.flashStep = r.new_step;
    return req("/api/sessions").then(function (m) { S.meta = m; return openSession(r.session, r.new_step); });
  }).catch(function (e) { $("dlg-lead").textContent = e.message; go.textContent = "Rewind"; go.disabled = false; });
}

document.addEventListener("keydown", function (e) {
  if ($("dlg").open || e.metaKey || e.ctrlKey || e.altKey) return;
  var t = e.target && e.target.tagName;
  if (t === "INPUT" || t === "TEXTAREA") return;
  if (e.key === "j") { select(S.sel + 1); e.preventDefault(); }
  else if (e.key === "k") { select(S.sel - 1); e.preventDefault(); }
  else if (e.key === "d") { document.body.classList.toggle("nodiff"); e.preventDefault(); }
  else if (e.key === "r" && S.sel >= 0) { confirmRewind(S.rows[S.sel].step, null); e.preventDefault(); }
});
document.addEventListener("DOMContentLoaded", function () {
  $("dlg-cancel").addEventListener("click", function () { pending = null; $("dlg").close(); });
  $("dlg-go").addEventListener("click", doRewind);
  $("dlg").addEventListener("close", function () { pending = null; });
  boot();
});
})();
"""
