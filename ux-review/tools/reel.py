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
</style></head><body><div class="stage">
<div class="top"><img src="logo-wordmark.svg" alt=""><span class="promise">%(promise)s</span></div>
<div class="panel"><div class="panel-head"><span id="head">a session of %(n)d steps</span><span class="tl" id="tl"></span></div>
<div class="screen"><pre class="term"><code id="code"></code></pre></div></div>
</div><script>
const BEATS = %(data)s, RULERS = %(rulers)s, N = %(n)d, GOOD = %(good)d;
const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
// timeline (frame 0 already shows the first caption and prompt, so a paused clip is never blank): per beat, the command typed at 22 chars/s, the output, then the beat's hold
const TYPE = 1 / 22, HOLD = [3.2, 2.4, 3.6, 3.0];
let t0 = 0; const plan = BEATS.map((b, i) => { const s = t0, typed = s + b.command.length * TYPE + 0.25; t0 = typed + HOLD[i] + 0.5; return { s, typed }; });
window.DURATION = t0 + 0.4;
window.show = (t) => {
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
</script></body></html>""" % {"promise": html.escape(build.PROMISE), "n": n, "good": good, "data": json.dumps(data), "rulers": json.dumps(rulers)}
with open(os.path.join(out, "reel.html"), "w", encoding="utf-8") as fh:
    fh.write(page)
print("wrote", os.path.join(out, "reel.html"))
