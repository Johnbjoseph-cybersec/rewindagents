"""The launch clip's page: rewind in action, from a live run of the real CLI.

Runs brand/demo/scenario.py in a temporary project (fourteen agent steps through the real hook, then the four
commands), checks every line against brand/demo/manifest.json (the record tests/test_demo.py replays), and writes
DIR/reel.html: the site's own CSS, one terminal panel, and a show(t) function that draws the session at second t.
ux-review/tools/reel.mjs screenshots it frame by frame. Nothing on a frame is typed by hand.

  python3 ux-review/tools/reel.py DIR
"""
import html
import json
import os
import shutil
import sys
import tempfile
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [os.path.join(ROOT, "src"), os.path.join(ROOT, "brand", "demo")]

import importlib.util  # noqa: E402
from rewindagents import cli  # noqa: E402
import scenario  # noqa: E402

# the site's build.py, by path: brand/demo has a build.py of its own
_spec = importlib.util.spec_from_file_location("site_build", os.path.join(ROOT, "brand", "site", "build.py"))
build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build)

out = sys.argv[1]
os.makedirs(out, exist_ok=True)
manifest = json.load(open(os.path.join(ROOT, "brand", "demo", "manifest.json"), encoding="utf-8"))
with tempfile.TemporaryDirectory() as d, mock.patch.object(cli, "invocation", lambda: manifest["invocation"]):
    beats = scenario.play(d)
for want, got in zip(manifest["beats"], beats):
    assert (want["command"], want["output"], want["accent_rows"]) == (got["command"], got["output"], got["accent_rows"]), want["command"]
print("live run matches brand/demo/manifest.json: %d commands" % len(beats))

shutil.copyfile(os.path.join(ROOT, "brand", "site", "site.css"), os.path.join(out, "site.css"))
shutil.copytree(os.path.join(ROOT, "brand", "site", "fonts"), os.path.join(out, "fonts"), dirs_exist_ok=True)
shutil.copyfile(os.path.join(ROOT, "brand", "logo-wordmark.svg"), os.path.join(out, "logo-wordmark.svg"))
HOST = build.config()["site_url"].split("//", 1)[1].rstrip("/")
n, good = len(scenario.STEPS), scenario.GOOD_STEP
data = [{"caption": b["caption"], "command": b["command"], "rows": b["output"].rstrip("\n").split("\n"),
         "accent": b["accent_rows"]} for b in beats]
rulers = {str(at): build.ruler(at, n=n, w=4 + 10 * (n - 1), h=20, dark=True) for at in (n, good)}
page = """<!doctype html><html lang="en"><head><meta charset="utf-8"><link rel="stylesheet" href="site.css"><style>
html, body { margin: 0; background: var(--leader); }
.stage { width: 1280px; height: 720px; box-sizing: border-box; padding: 40px 64px 44px; display: flex; flex-direction: column; gap: 22px; }
.top { display: flex; justify-content: space-between; align-items: center; }
.top img { height: 30px; width: auto; }
.top .promise { font-family: var(--display); font-weight: 800; font-size: 24px; letter-spacing: -0.02em; }
.panel { flex: 1; display: flex; flex-direction: column; min-height: 0; }
.panel-head { font-size: 15px; padding: 14px 22px; }
.panel-head .tl { gap: 14px; }
.screen { flex: 1; min-height: 0; overflow: hidden; display: flex; flex-direction: column; justify-content: flex-end; }
pre.term { font-size: 17.5px; line-height: 1.5; padding: 18px 24px; border-radius: 0; }
pre.term .l { white-space: pre; }
.cursor { display: inline-block; width: 0.6em; height: 1.1em; vertical-align: -0.2em; background: var(--leader); }
.bottom { display: flex; justify-content: space-between; font-family: var(--mono); font-size: 15px; color: var(--tape); }
.bottom b { color: var(--reel); }
</style></head><body><div class="stage">
<div class="top"><img src="logo-wordmark.svg" alt=""><span class="promise">%(promise)s</span></div>
<div class="panel"><div class="panel-head"><span id="head">a session of %(n)d steps</span><span class="tl" id="tl"></span></div>
<div class="screen"><pre class="term"><code id="code"></code></pre></div></div>
<div class="bottom"><span>%(sub)s</span><span><b>%(host)s</b> &middot; %(credit)s</span></div>
</div><script>
const BEATS = %(data)s, RULERS = %(rulers)s, N = %(n)d, GOOD = %(good)d;
const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
// timeline (frame 0 already shows the first caption and prompt, so a paused clip is never blank): per beat, the command typed at 22 chars/s, the output, then the beat's hold
const TYPE = 1 / 22, HOLD = [3.2, 2.4, 3.6, 3.0];
let t0 = 0; const plan = BEATS.map((b, i) => { const s = t0, typed = s + b.command.length * TYPE + 0.25; t0 = typed + HOLD[i] + 0.5; return { s, typed }; });
window.DURATION = t0 + 0.4;
// the screen shows whole lines only: its height is a whole number of lines, so a scrolled line is never cut in half
const fit = () => { const scr = document.querySelector(".screen"); if (scr.dataset.fit) return; const pre = scr.querySelector("pre"); const cs = getComputedStyle(pre), lh = parseFloat(cs.lineHeight), pb = parseFloat(cs.paddingBottom), H = scr.getBoundingClientRect().height; const k = Math.floor((H - pb - 16) / lh); scr.style.flex = "none"; scr.style.height = (k * lh + pb) + "px"; scr.style.marginTop = (H - k * lh - pb) + "px"; pre.style.paddingTop = "0"; scr.dataset.fit = "1"; };
window.show = (t) => { fit();
  const lines = []; let rewound = false;
  BEATS.forEach((b, i) => {
    const p = plan[i]; if (t < p.s) return;
    lines.push('<span class="l"><span class="c">' + esc(b.caption) + '</span></span>');
    const k = Math.min(b.command.length, Math.floor((t - p.s) / TYPE));
    const typing = t < p.typed;
    lines.push('<span class="l"><span class="p">$ </span>' + esc(b.command.slice(0, k)) + (typing ? '<span class="cursor"></span>' : '') + '</span>');
    if (!typing) {
      b.rows.forEach((r, j) => lines.push('<span class="l">' + (b.accent.includes(j) ? '<span class="hit">' + esc(r) + '</span>' : esc(r)) + '</span>'));
      if (b.command.includes(" rewind ")) rewound = true;
    }
  });
  const last = BEATS.length - 1;
  if (t >= plan[last].typed) lines.push('<span class="l"><span class="p">$ </span><span class="cursor"></span></span>');
  document.getElementById("code").innerHTML = lines.join("\\n");
  document.getElementById("tl").innerHTML = RULERS[rewound ? GOOD : N] + "<span>" + (rewound ? "rewound to step " + GOOD : "step " + N + " of " + N) + "</span>";
  document.getElementById("head").textContent = rewound ? "the last 2 steps undone, 12 kept" : "a session of " + N + " steps; the last 2 wrecked the repo";
};
show(0);
</script></body></html>""" % {"promise": html.escape(build.PROMISE), "sub": "undo, the base: rewind any step", "host": HOST, "credit": html.escape(build.CREDIT), "n": n, "good": good, "data": json.dumps(data), "rulers": json.dumps(rulers)}
with open(os.path.join(out, "reel.html"), "w", encoding="utf-8") as fh:
    fh.write(page)
print("wrote", os.path.join(out, "reel.html"))


# ---- the second clip: fork and compare, from brand/demo/runs.json (what ux-review/try-runs.sh printed against an
# installed build; tests/test_runs_demo.py runs the script again and fails if a quoted line changes). The rows are
# the site's own (build.runs_rows), so the clip shows nothing the pages do not. Captions are the script's headings.
runs = json.load(open(os.path.join(ROOT, "brand", "demo", "runs.json"), encoding="utf-8"))
hero, diff = build.runs_rows(runs, "hero"), build.runs_rows(runs, "diff")
cut = [i for i, r in enumerate(hero) if r[0] == "cmd"][1]
heads = {"fork": build.RUNS_FORK, "compare": build.RUNS_COMPARE, "diff": build.RUNS_DIFF}
def beat(key, rows):
    return {"caption": "# " + heads[key], "command": rows[0][1], "rows": [t for _, t in rows[1:]],
            "accent": [j for j, (k, _) in enumerate(rows[1:]) if k in ("hit", "tabhit")]}
rdata = [beat("fork", hero[:cut]), beat("compare", hero[cut:]), beat("diff", diff)]
fork_ruler = build.ruler(2, n=3, w=60, h=20, dark=True)
rpage = page.split("<script>")[0].replace(html.escape(build.PROMISE), html.escape(build.COURSE)).replace(
    "undo, the base: rewind any step", "fork any recorded step, compare the runs").replace(
    ".top .promise { font-family: var(--display); font-weight: 800; font-size: 24px;",
    ".top .promise { font-family: var(--display); font-weight: 800; font-size: 22px;") + """<script>
const BEATS = %(data)s;
const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const TYPE = 1 / 22, HOLD = [2.6, 4.2, 3.6];
let t0 = 0; const plan = BEATS.map((b, i) => { const s = t0, typed = s + b.command.length * TYPE + 0.25; t0 = typed + HOLD[i] + 0.5; return { s, typed }; });
window.DURATION = t0 + 0.4;
// the screen shows whole lines only: its height is a whole number of lines, so a scrolled line is never cut in half
const fit = () => { const scr = document.querySelector(".screen"); if (scr.dataset.fit) return; const pre = scr.querySelector("pre"); const cs = getComputedStyle(pre), lh = parseFloat(cs.lineHeight), pb = parseFloat(cs.paddingBottom), H = scr.getBoundingClientRect().height; const k = Math.floor((H - pb - 16) / lh); scr.style.flex = "none"; scr.style.height = (k * lh + pb) + "px"; scr.style.marginTop = (H - k * lh - pb) + "px"; pre.style.paddingTop = "0"; scr.dataset.fit = "1"; };
window.show = (t) => { fit();
  const lines = [];
  BEATS.forEach((b, i) => {
    const p = plan[i]; if (t < p.s) return;
    lines.push('<span class="l"><span class="c">' + esc(b.caption) + '</span></span>');
    const k = Math.min(b.command.length, Math.floor((t - p.s) / TYPE));
    const typing = t < p.typed;
    lines.push('<span class="l"><span class="p">$ </span>' + esc(b.command.slice(0, k)) + (typing ? '<span class="cursor"></span>' : '') + '</span>');
    if (!typing) b.rows.forEach((r, j) => lines.push('<span class="l">' + (b.accent.includes(j) ? '<span class="hit">' + esc(r) + '</span>' : esc(r)) + '</span>'));
  });
  if (t >= plan[BEATS.length - 1].typed) lines.push('<span class="l"><span class="p">$ </span><span class="cursor"></span></span>');
  document.getElementById("code").innerHTML = lines.join("\\n");
  document.getElementById("tl").innerHTML = %(ruler)s + "<span>fork 2</span>";
  document.getElementById("head").textContent = "a session, and a second try from step 2";
};
show(0);
</script></body></html>""" % {"data": json.dumps(rdata), "ruler": json.dumps(fork_ruler)}
os.makedirs(os.path.join(out, "runs"), exist_ok=True)
for name in ("site.css", "logo-wordmark.svg"):
    shutil.copyfile(os.path.join(out, name), os.path.join(out, "runs", name))
shutil.copytree(os.path.join(out, "fonts"), os.path.join(out, "runs", "fonts"), dirs_exist_ok=True)
with open(os.path.join(out, "runs", "reel.html"), "w", encoding="utf-8") as fh:
    fh.write(rpage)
print("wrote", os.path.join(out, "runs", "reel.html"))
