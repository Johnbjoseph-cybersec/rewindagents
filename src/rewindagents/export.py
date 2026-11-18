"""Export a recorded session as one self-contained HTML page: the replay you can hand to someone.

The page lists every step (number, tool, what it touched), each step's input and result, and for every
file a step checkpointed the change that step made: a unified diff of the file's bytes before the step
against its bytes after it (the next checkpoint of that file in the session, or the file as it is now).

It is one file with inline CSS only: no scripts, no fonts or images fetched from anywhere, nothing that
phones home, so it can go into a bug report, a code review or a lesson as it is. Paths inside the project
are written relative to it; the project's location on disk is not in the page.

Export reads the log and the object store and writes the page. It changes nothing else.
"""
from __future__ import annotations

import datetime as _dt
import difflib
import html
import json
import os
import re
import secrets
import sys
from pathlib import Path
from typing import Any

from . import __version__, log, ospaths, rewind
from . import redact as _redact

# BRAND.md palette; tests/test_export.py checks every value against the table there.
PALETTE = {"Leader": "#F2F4F1", "Reel": "#121412", "Spool": "#1C201D", "Tape": "#55605A",
           "Record": "#B82A16", "Rewind": "#FF7A59", "Playhead": "#B9C2BB", "Rule": "#838C86"}
MAX_DIFF_BYTES = 256 * 1024      # a side larger than this is described, not diffed
MAX_DIFF_LINES = 400             # diff lines shown per file before "... n more"
CREDIT = "made by John B Joseph"


class ExportError(Exception):
    pass


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _short(sha: str | None) -> str:
    return sha[:12] if sha else "-"


def _text(data: bytes | None) -> list[str] | None:
    """The file's lines for diffing, or None when it is not UTF-8 text."""
    if data is None:
        return []
    try:
        return data.decode("utf-8").splitlines(keepends=True)
    except UnicodeDecodeError:
        return None


def _read_object(objects: Path, sha: str | None) -> bytes | None:
    if sha is None:
        return None
    obj = objects / sha
    return obj.read_bytes() if obj.is_file() else None


def _after(all_steps: list[dict], i: int, path: str, root: Path, objects: Path) -> tuple[bytes | None, str]:
    """Bytes of `path` right after step i (0-based): the next checkpoint of it, else the file as it is now."""
    for later in all_steps[i + 1:]:
        for cp in later["checkpoints"]:
            if cp["path"] == path:
                if cp.get("skipped"):
                    return None, f"unknown ({cp['skipped']} at step {later['step']})"
                data = _read_object(objects, cp.get("sha256"))
                if cp.get("sha256") and data is None:
                    return None, "unknown (stored copy missing)"
                return data, "absent" if cp.get("sha256") is None else _short(cp["sha256"])
    p = Path(path)
    if p.is_file():
        try:
            return p.read_bytes(), "now"
        except OSError:
            return None, "unknown (unreadable now)"
    return None, "absent now"


def file_change(before: bytes | None, after: bytes | None, before_label: str, after_label: str) -> dict:
    """Describe one file's change as the page shows it: a diff, or why there is none."""
    out: dict[str, Any] = {"kind": "diff", "lines": [], "more": 0, "note": ""}
    if before is None and after is None:
        out.update(kind="note", note="absent before and after")
        return out
    for side, data in (("before", before), ("after", after)):
        if data is not None and len(data) > MAX_DIFF_BYTES:
            out.update(kind="note", note=f"{side} is {len(data):,} bytes, over the {MAX_DIFF_BYTES // 1024} KB diff limit")
            return out
    b, a = _text(before), _text(after)
    if b is None or a is None:
        out.update(kind="note", note=f"binary: {len(before or b'')} bytes before, {len(after or b'')} bytes after")
        return out
    if before == after:
        out.update(kind="note", note="unchanged")
        return out
    lines = list(difflib.unified_diff(b, a, fromfile=before_label, tofile=after_label, n=3))
    out["lines"] = [l.rstrip("\n") for l in lines[:MAX_DIFF_LINES]]
    out["more"] = max(0, len(lines) - MAX_DIFF_LINES)
    return out


def build(log_path: str | Path, session: str | None = None, contents: bool = True, redact: bool = True) -> dict:
    """Everything the page needs, as data. Reads only.

    contents=False leaves out inputs, results and diffs (a Write's input is the file's content), so the
    page holds steps, tools and paths only, plus the one-line summary `replay` prints for each step.
    redact=True replaces secrets (redact.py) in every summary, input, result and diff; 'redacted' counts them.
    """
    diffs = contents
    redacted = 0
    root = rewind.project_root(log_path)
    # The project's location is scrubbed from everything the page prints: the resolved root and the root
    # as the log was addressed (macOS gives /var/... and /private/var/... for the same directory).
    roots = sorted({str(root), str(Path(log_path).absolute().parent.parent)}, key=len, reverse=True)
    objects = root / ".rewindagents" / "objects"
    ok, n, msg = log.verify(log_path)
    session = session or rewind.latest_session(log_path)
    all_steps = rewind.steps(log_path, session)
    if not all_steps:
        raise ExportError(f"no steps for session {session!r}")
    steps_out = []
    for i, s in enumerate(all_steps):
        files = []
        for cp in s["checkpoints"]:
            rel = rewind.relative(cp["path"], root)
            entry: dict[str, Any] = {"path": rel, "before": "absent" if cp.get("sha256") is None else _short(cp["sha256"])}
            if cp.get("skipped"):
                entry["before"] = f"not checkpointed ({cp['skipped']})"
            if diffs:
                if cp.get("skipped"):
                    entry["change"] = {"kind": "note", "note": f"not checkpointed ({cp['skipped']})", "lines": [], "more": 0}
                else:
                    before = _read_object(objects, cp.get("sha256"))
                    if cp.get("sha256") and before is None:
                        entry["change"] = {"kind": "note", "note": "stored copy missing", "lines": [], "more": 0}
                    else:
                        after, after_label = _after(all_steps, i, cp["path"], root, objects)
                        entry["after"] = after_label
                        if after_label.startswith("unknown"):
                            entry["change"] = {"kind": "note", "note": after_label, "lines": [], "more": 0}
                        else:
                            changed = before != after
                            if redact:
                                env = _redact.is_env_file(rel)
                                before, k1 = _redact.data(before, env)
                                after, k2 = _redact.data(after, env)
                                redacted += k1 + k2
                            entry["change"] = file_change(before, after, f"{rel} (before step {s['step']})",
                                                          f"{rel} (after step {s['step']})")
                            if changed and entry["change"]["note"] == "unchanged":
                                entry["change"]["note"] = "changed only inside redacted values"
            files.append(entry)
        (summary, k), step_in, step_res = _summary(s, root, roots, redact=redact), s.get("input"), s.get("result")
        redacted += k
        in_clips, res_clips = clips(step_in), clips(step_res)
        if redact:
            step_in, k1 = _redact.value(step_in)
            step_res, k2 = _redact.value(step_res)
            redacted += (k1 + k2) if contents else 0
        steps_out.append({"step": s["step"], "tool": s["tool"], "event": s["event"],
                          "summary": summary,
                          "input": step_in, "result": step_res, "files": files,
                          "input_clips": in_clips, "result_clips": res_clips,
                          "to_step": s.get("to_step"), "branch": s.get("branch"),
                          "bash_scan": s.get("bash_scan")})
    return {"project": root.name, "roots": roots, "session": session, "steps": steps_out,
            "records": n, "chain_ok": ok, "chain_msg": msg, "head": log.head(log_path),
            "exported": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "version": __version__, "contents": contents, "redact": redact, "redacted": redacted}


_CSS = """
:root{--bg:%(Leader)s;--fg:%(Reel)s;--muted:%(Tape)s;--accent:%(Record)s;--rule:%(Rule)s;--code-bg:%(Spool)s;
--code-fg:%(Leader)s;--code-muted:%(Playhead)s;--code-accent:%(Rewind)s}
@media (prefers-color-scheme:dark){:root{--bg:%(Reel)s;--fg:%(Leader)s;--muted:%(Playhead)s;--accent:%(Rewind)s}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 "Hanken Grotesk",system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:960px;margin:0 auto;padding:32px 16px 64px}
h1{font-family:"Bricolage Grotesque",system-ui,sans-serif;font-weight:800;letter-spacing:-.02em;font-size:28px;margin:0 0 4px}
h1 span{color:var(--accent)}
.meta{color:var(--muted);font-size:14px;margin:0 0 24px}
.meta code,.row code,.files code,.tamper code{font-family:"Commit Mono",ui-monospace,Menlo,Consolas,monospace;font-size:.92em}
.tamper{border:1px solid var(--accent);color:var(--accent);padding:8px 12px;margin:0 0 24px;font-size:14px}
ol.steps{list-style:none;margin:0;padding:0;border-top:1px solid var(--rule)}
ol.steps>li{border-bottom:1px solid var(--rule)}
summary{display:grid;grid-template-columns:3.5em 7em 1fr auto;gap:12px;align-items:baseline;padding:10px 0;cursor:pointer;list-style:none}
summary::-webkit-details-marker{display:none}
summary .n{font-family:"Commit Mono",ui-monospace,Menlo,monospace;font-variant-numeric:tabular-nums;color:var(--muted)}
details[open] summary .n{color:var(--accent)}
summary .tool{font-weight:600}
summary .what{font-family:"Commit Mono",ui-monospace,Menlo,monospace;font-size:14px;overflow-wrap:anywhere}
summary .cps{color:var(--muted);font-size:13px;white-space:nowrap}
.body{padding:0 0 16px 3.5em}
.body h3{font-size:13px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;margin:12px 0 4px}
pre{margin:0;background:var(--code-bg);color:var(--code-fg);padding:12px;overflow:auto;font:13px/1.45 "Commit Mono",ui-monospace,Menlo,Consolas,monospace;border-radius:2px}
pre.io{white-space:pre-wrap;overflow-wrap:anywhere}
pre.diff .add{color:var(--code-accent)}
pre.diff .del{color:var(--code-muted);text-decoration:line-through}
pre.diff .hunk{color:var(--code-muted)}
.files p{margin:8px 0 4px;font-size:14px}
.note{color:var(--muted);font-size:14px;margin:4px 0 0}
footer{margin-top:40px;padding-top:12px;border-top:1px solid var(--rule);color:var(--muted);font-size:13px;display:flex;justify-content:space-between;gap:16px}
@media (max-width:600px){summary{grid-template-columns:3em 1fr;grid-auto-rows:auto}summary .what{grid-column:1/-1}.body{padding-left:0}}
""" % PALETTE


def scrub(text: str, roots: list[str]) -> str:
    """Drop the project's location: a path inside it becomes relative, the bare root (`cd /abs/proj`,
    a Cursor working_directory) becomes `.`. A longer path that only starts with the root is left alone."""
    for root in roots:
        for r in ospaths.forms(root):   # a Windows root: C:\proj\a.py and C:/proj/a.py
            spelled = [(r, ospaths.seps(r))]
            if "\\" in r:               # ...and inside a JSON-shown input, where each \ prints as \\
                spelled.append((r.replace("\\", "\\\\"), ("\\\\", "/")))
            for form, seps in spelled:
                for sep in seps:
                    text = text.replace(form + sep, "")
                text = re.sub(r"(?<![\w.-])" + re.escape(form) + r"(?![\w.-])", ".", text)
    return text


def _summary(step: dict, root: Path, roots: list[str], width: int = 120, redact: bool = False) -> tuple[str, int]:
    """The `replay` line and how many secrets it lost, scrubbed and redacted before it is cut so a cut
    cannot leave half the root, or half a token, behind."""
    text, n = scrub(rewind.summary(step, width=sys.maxsize, root=root), roots), 0
    if redact:
        text, n = _redact.text(text)
    return (text if len(text) <= width else text[: width - 3] + "..."), n


def clips(value: Any, path: tuple = ()) -> list[dict]:
    """Every clipped value (redact.is_clip) inside `value`: where it sits, how many characters the log kept
    and how long the text was. Taken from the value as recorded, before redaction can change a head's length."""
    if _redact.is_clip(value):
        return [{"path": list(path), "kept": len(value["head"]), "chars": value["chars"]}]
    if isinstance(value, dict):
        return [c for k, v in value.items() for c in clips(v, path + (k,))]
    if isinstance(value, list):
        return [c for i, v in enumerate(value) for c in clips(v, path + (i,))]
    return []


def clip_note(kept: int, chars: int) -> str:
    return f"... first {kept:,} of {chars:,} characters kept in the log"


def show(value: Any, found: list[dict] | None = None) -> str:
    """A recorded input, result or step as readable text: JSON, except that each clipped value prints as its
    head followed by one line saying how much of it the log kept. `found` is clips() of the value as
    recorded (export passes it because redaction runs in between); by default it is read from `value`."""
    found = clips(value) if found is None else found
    whole = next((c for c in found if not c["path"]), None)       # the value itself was clipped
    if whole and isinstance(value, dict) and isinstance(value.get("head"), str):
        return value["head"] + "\n" + clip_note(whole["kept"], whole["chars"])
    marks: dict[str, dict] = {}
    copy = json.loads(json.dumps(value, ensure_ascii=False, default=str))
    tag = secrets.token_hex(8)
    for i, c in enumerate(found):
        node = copy
        try:
            for key in c["path"][:-1]:
                node = node[key]
            head = node[c["path"][-1]]["head"]
        except (KeyError, IndexError, TypeError):
            continue
        token = f"clip-{tag}-{i}"
        node[c["path"][-1]] = token
        marks[json.dumps(token)] = {"head": head, **c}
    lines = []
    for line in json.dumps(copy, indent=2, ensure_ascii=False).split("\n"):
        hit = next((m for m in marks if m in line), None)
        if hit is None:
            lines.append(line)
            continue
        c = marks[hit]
        lines.append(line.replace(hit, json.dumps(c["head"], ensure_ascii=False), 1))
        lines.append(" " * (len(line) - len(line.lstrip(" "))) + clip_note(c["kept"], c["chars"]))
    return "\n".join(lines)


def _json(value: Any, roots: list[str], found: list[dict] | None = None) -> str:
    return _esc(scrub(show(value, found), roots))


def _diff_html(change: dict) -> str:
    if change["kind"] == "note":
        return f'<p class="note">{_esc(change["note"])}</p>'
    parts = []
    for l in change["lines"]:
        cls = "hunk" if l.startswith(("@@", "---", "+++")) else "add" if l.startswith("+") else "del" if l.startswith("-") else ""
        parts.append(f'<span class="{cls}">{_esc(l)}</span>' if cls else _esc(l))
    more = f'\n<span class="hunk">... {change["more"]} more lines</span>' if change["more"] else ""
    return f'<pre class="diff">{chr(10).join(parts)}{more}</pre>'


def _redaction_note(data: dict) -> str:
    if not data.get("redact", False):
        return "Exported with --no-redact: secrets were not looked for."
    n = data.get("redacted", 0)
    return (f"{n} secret value{'s' if n != 1 else ''} replaced with [redacted ...]."
            " Secrets of other shapes are not caught: read the page before you pass it on.")


def render(data: dict) -> str:
    """The page, as a string."""
    root = data["roots"]
    items = []
    for s in data["steps"]:
        cps = f'<span class="cps">{len(s["files"])} file{"s" if len(s["files"]) != 1 else ""}</span>' if s["files"] else '<span class="cps"></span>'
        body = []
        if s["event"] in ("rewind", "branch"):
            text = f"Rewound the files to how they were after step {s['to_step']}."
            if s.get("branch"):
                b = s["branch"]
                text += f" Previous files kept in git branch {_esc(b.get('git_ref'))}." if b.get("git_ref") else " Previous files kept in the log."
            body.append(f"<p>{text}</p>")
        elif not data["contents"]:
            body.append('<p class="note">Input and result left out (exported without contents).</p>')
        else:
            body.append(f'<h3>Input</h3><pre class="io">{_json(s["input"], root, s.get("input_clips"))}</pre>')
            if s["result"] is not None:
                body.append(f'<h3>Result</h3><pre class="io">{_json(s["result"], root, s.get("result_clips"))}</pre>')
            elif s["tool"] != "rewindagents":
                body.append('<p class="note">No result was recorded for this call.</p>')
        if s.get("bash_scan") and "skipped" in s["bash_scan"]:
            body.append(f'<p class="note">Files changed by this command were not checkpointed: {_esc(s["bash_scan"]["skipped"])}.</p>')
        elif s.get("bash_scan") and s["bash_scan"].get("early"):
            body.append('<p class="note">This command ran in the background: its after-scan may have run before it '
                        'finished, so files it changed later may be missing from this step.</p>')
        if s["files"]:
            body.append("<h3>Files</h3><div class=\"files\">")
            for f in s["files"]:
                line = f'<code>{_esc(f["path"])}</code> <span class="note">before: {_esc(f["before"])}'
                if "after" in f:
                    line += f', after: {_esc(f["after"])}'
                body.append(f"<p>{line}</span></p>")
                if "change" in f:
                    body.append(_diff_html(f["change"]))
            body.append("</div>")
        items.append(
            f'<li><details><summary><span class="n">{s["step"]}</span><span class="tool">{_esc(s["tool"])}</span>'
            f'<span class="what">{_esc(s["summary"])}</span>{cps}</summary>'
            f'<div class="body">{"".join(body)}</div></details></li>')
    chain = "chain intact" if data["chain_ok"] else "chain does not verify"
    tamper = "" if data["chain_ok"] else (
        f'<p class="tamper">This log does not verify: <code>{_esc(data["chain_msg"])}</code>. '
        f'Steps from that record on may not be what happened.</p>')
    n = len(data["steps"])
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>rewindagents replay: {_esc(data["project"])} session {_esc(data["session"])}</title>
<style>{_CSS}</style>
</head>
<body>
<main>
<h1>rewind<span>agents</span> replay</h1>
<p class="meta">{_esc(data["project"])}, session <code>{_esc(data["session"])}</code>: {n} step{"s" if n != 1 else ""}.
Log: {data["records"]} records, {chain}, head <code>{_esc(_short(data["head"]))}</code>. Exported {_esc(data["exported"])}.
{"File changes are shown as diffs." if data["contents"] else "Exported without contents: no inputs, results or diffs."}
{_redaction_note(data)}</p>
{tamper}
<ol class="steps">
{chr(10).join(items)}
</ol>
<footer><span>{CREDIT}</span><span>rewindagents {_esc(data["version"])}</span></footer>
</main>
</body>
</html>
"""


def export(log_path: str | Path, session: str | None = None, out: str | Path | None = None,
           contents: bool = True, redact: bool = True) -> dict:
    """Write the page. Returns the build data plus 'out' (the path written) and 'bytes'."""
    data = build(log_path, session, contents, redact)
    page = render(data)
    path = Path(out) if out else rewind.project_root(log_path) / ".rewindagents" / f"replay-{data['session']}.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.rewindagents.tmp")
    tmp.write_text(page, encoding="utf-8", newline="")   # the same bytes on every OS: no \r\n on Windows
    os.replace(tmp, path)
    data["out"], data["bytes"] = str(path), len(page.encode("utf-8"))
    return data
