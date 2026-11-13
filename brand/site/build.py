"""Build the rewindagents site (task RB3): brand/site/index.html, pricing.html and docs/index.html.

Nothing on the pages is typed from memory:
- every command block is a ```sh block of README.md, found by its section heading;
- every number (version, the 4,000-character result cut, the 20 MB file limit, the 20,000-file scan limit, the
  diff limits, the step numbers in the clip) is read from the package or from brand/demo/scenario.py;
- the terminal panels quote brand/demo/manifest.json, the record of the real session behind brand/demo.gif,
  which tests/test_demo.py replays byte for byte;
- everything called planned on the pricing page is a phrase of brand/BRAND.md;
- the only address the site knows is site_url in config.json. checkout_url is null until a Polar product exists.

Static HTML that reads complete with scripts off; local scripts only animate it (CSP 'self'). Standard library only, so the fresh-clone gate and the Pages workflow need no toolchain.
tests/test_site.py rebuilds the pages into a temp folder and fails if the committed files differ.

  python3 brand/site/build.py            -> writes the pages, manifest.json and assets/ (git-ignored) in brand/site/
  python3 brand/site/build.py fonts      -> copies the brand WOFF2 files + licences from .brandcache into fonts/
  python3 brand/site/build.py open DIR   -> a copy of the site in DIR (outside brand/site, e.g. build/site-open) plus
                                            DIR/index-open.html with every answer open, for review renders only
"""
import html
import importlib.util
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BRAND = os.path.dirname(HERE)
ROOT = os.path.dirname(BRAND)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(BRAND, "demo"))

import rewindagents  # noqa: E402
from rewindagents import agents, bashscan, export, hook, sessions  # noqa: E402
import scenario  # noqa: E402

NAME = "rewindagents"
PROMISE = "Ctrl+Z for AI coding agents: record, replay, rewind."
CREDIT = "made by John B Joseph"
LICENCE = "Apache-2.0"
PAGES = {"index.html": "", "pricing.html": "pricing.html", "docs/index.html": "docs/"}
# brand/ files the pages use, copied into brand/site/assets/ at build time (assets/ is git-ignored; the Pages
# workflow runs this build, so the published site carries the current clip and logo files).
ASSETS = ["ui-timeline.png", "demo.gif", "logo-wordmark.svg", "logo-wordmark-reverse.svg", "logo-mark.svg", "favicon.svg",
          "favicon-32.png", "social-preview-1280x640.png"]
FONTS = {"bricolage-grotesque": (700, 800), "hanken-grotesk": (400, 600), "commit-mono": (400, 700)}
C = {"Leader": "#F2F4F1", "Reel": "#121412", "Spool": "#1C201D", "Tape": "#55605A",
     "Record": "#B82A16", "Rewind": "#FF7A59", "Playhead": "#B9C2BB", "Rule": "#838C86"}
# The paid tier, as BRAND.md puts it. Each phrase must appear in BRAND.md (tests/test_site.py).
PLANNED = [("cloud sync", "Cloud sync of session history across your machines"),
           ("shareable replay links", "Shareable replay links: the export page, hosted, for a code review or a bug report"),
           ("long retention", "Long retention of sessions"),
           ("session search", "Session search across all of them")]

e = html.escape


def config(path=None):
    with open(path or os.path.join(HERE, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    for k in ("site_url", "repo_url", "branch", "waitlist_url"):
        if not cfg.get(k):
            raise SystemExit("config.json: %s is required" % k)
    if not cfg["site_url"].endswith("/"):
        raise SystemExit("config.json: site_url must end with /")
    return cfg


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def readme_block(readme, heading):
    """The first ```sh block under a README heading, as a list of lines."""
    m = re.search(r"^## %s\n.*?```sh\n(.*?)```" % re.escape(heading), readme, re.S | re.M)
    if not m:
        raise SystemExit("README has no sh block under '## %s'" % heading)
    return m.group(1).rstrip("\n").split("\n")


def readme_blocks(readme, heading, lang="sh"):
    """Every ```<lang> block in the section under a README heading (up to the next ## heading), as lists of lines."""
    m = re.search(r"^## %s\n(.*?)(?=^## |\Z)" % re.escape(heading), readme, re.S | re.M)
    if not m:
        raise SystemExit("README has no section '## %s'" % heading)
    return [blk.rstrip("\n").split("\n") for blk in re.findall(r"```%s\n(.*?)```" % lang, m.group(1), re.S)]


def readme_sentence(readme, start):
    """The README sentence that begins with `start` (line breaks folded), as markdown."""
    m = re.search(r"%s.*?\.(?=\s|\Z)" % re.escape(start), " ".join(readme.split()))
    if not m:
        raise SystemExit("README has no sentence starting %r" % start)
    return m.group(0)


def md_inline(s):
    """Escape a README sentence for HTML and turn its `code` spans into <code>."""
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", e(s))


# The README's own words for what `status` reports, quoted on the docs page under "Is it recording?" (R25).
# "exits 1." goes last so a wrap never starts a line with "1." (it read as a list item at 1440).
STATUS_SENTENCES = ("The last line of `status` is this project's log", "`status` writes nothing",
                    "A hook is stale when")
# The README's words under "Move a session" and "Free space" on the docs page (R26); none ends on a number.
MOVE_SENTENCES = ("Then `replay`, `rewind` and `branch` work on that session",
                  "By default, secrets are replaced in the records and the stored copies",
                  "`import` writes nothing until everything checks out", "Nothing goes over a network")
GC_SENTENCES = ("`gc` deletes every stored copy that no", "Every step of every session in the log can still be rewound",
                "It refuses to run when the log does not verify", "A scan whose after-scan never ran",
                "Scans younger than 1 day are never dropped")
# Under "Timeline in a browser" and "Attach to a PR" (R27). Sentences with **bold** labels are left out
# (md_inline renders code spans only). "It has not run on GitHub yet" must stay while the action has not run (R18b).
UI_SENTENCES = ("A local page over the log", "Click a step, or move with", "It listens on 127.0.0.1 only",
                "The link it prints carries a random token", "Rewinds are POST only",
                "No fonts, scripts or images are fetched")
ATTACH_SENTENCES = ("The `.rewindagents/` store is git-ignored",)
ATTACH_ACTION_SENTENCES = ("The action in `attach/` imports the bundle", "A later push updates that comment",
                           "Secrets are always replaced in the page", "It installs `rewindagents` from the same commit",
                           "The token is handed to the comment step only", "If the log does not verify, the page is uploaded",
                           "It has not run on GitHub yet")
# The README's words about `init`, under "Add the hook" on the docs page (R28).
INIT_SENTENCES = ("`init` looks for the agents it supports", "It prints the plan, asks", "It never adds a second copy",
                  "`--yes` skips the question", "`--global` writes each agent's user config instead",
                  "Without `--yes` and without a terminal to ask on")
MORE_AGENTS = "Gemini CLI, Copilot CLI, Droid and Qwen Code hooks"
# README sections with a ```sh block that the docs page leaves out on purpose, each with the reason.
# tests/test_site.py fails when any other section's commands are missing from a docs panel (R28).
NOT_ON_DOCS = {
    "Payments code (not live)": "checkout code for a tier that is not built; not part of the package and not a user command",
}


def facts():
    readme = read("README.md")
    demo = json.loads(read("brand", "demo", "manifest.json"))
    if demo["version"] != rewindagents.__version__:
        raise SystemExit("brand/demo/manifest.json is for %s, the package is %s" % (demo["version"], rewindagents.__version__))
    tested = re.search(r"tested on ([\d.]+), (\w+)", readme)
    return {
        "version": rewindagents.__version__,
        "py_req": re.search(r'requires-python = "([^"]+)"', read("pyproject.toml")).group(1),
        "tested_on": "Python %s on %s" % (tested.group(1), tested.group(2)),
        "result_chars": hook.MAX_RESULT_CHARS,
        "file_mb": hook.MAX_CHECKPOINT_BYTES // (1024 * 1024),
        "scan_files": bashscan.MAX_SCAN_FILES,
        "skip_dirs": sorted(bashscan.SKIP_DIRS),
        "diff_kb": export.MAX_DIFF_BYTES // 1024,
        "diff_lines": export.MAX_DIFF_LINES,
        "show_files": sessions.SHOW_FILES,
        "file_tools": list(hook.FILE_TOOLS),
        "agents": {k: {"settings": a.settings, "read_only": sorted(a.read_only)} for k, a in agents.AGENTS.items()},
        "steps": len(scenario.STEPS),
        "good_step": scenario.GOOD_STEP,
        "wreck_steps": scenario.WRECK_STEPS,
        "blocks": {k: readme_block(readme, h) for k, h in (
            ("install", "Install"), ("hook", "Claude Code hook"), ("agents", "Codex and Cursor hooks"),
            ("replay", "Replay, rewind, branch"),
            ("export", "Export a replay"), ("sessions", "Find a session"), ("verify", "What the chain does not catch"),
            ("record", "Use it"), ("tests", "Tests"), ("quick", "Quick start"), ("ui", "Timeline UI"))},
        "quick_use": readme_blocks(readme, "Quick start")[1],
        "init_says": [readme_sentence(readme, s) for s in INIT_SENTENCES],
        "more_agents": readme_blocks(readme, MORE_AGENTS)[0],
        "uninstall": next(blk for blk in readme_blocks(readme, "Claude Code hook") if blk[0].startswith("rewindagents uninstall")),
        "status": next(blk for blk in readme_blocks(readme, "Claude Code hook") if blk[0].startswith("rewindagents status")),
        "status_says": [readme_sentence(readme, s) for s in STATUS_SENTENCES],
        "bundle": next(blk for blk in readme_blocks(readme, "Move a session to another machine") if blk[0].startswith("rewindagents bundle")),
        "bundle_says": [readme_sentence(readme, s) for s in MOVE_SENTENCES],
        "gc": next(blk for blk in readme_blocks(readme, "Clean up stored copies") if blk[0].startswith("rewindagents gc")),
        "gc_says": [readme_sentence(readme, s) for s in GC_SENTENCES],
        "ui_says": [readme_sentence(readme, s) for s in UI_SENTENCES],
        "attach": next(blk for blk in readme_blocks(readme, "Attach a replay to a pull request")
                       if blk[0].startswith("rewindagents bundle")),
        "attach_yaml": readme_blocks(readme, "Attach a replay to a pull request", "yaml")[0],
        "attach_says": [readme_sentence(readme, s) for s in ATTACH_SENTENCES],
        "action_says": [readme_sentence(readme, s) for s in ATTACH_ACTION_SENTENCES],
        "beats": demo["beats"],
        "gif": {k: demo["gif_facts"][k] for k in ("width", "height", "seconds", "frames")},
    }


EYEBROW_MAX = 46   # the eyebrow is one unwrapped mono line in the 5/12 hero column at 1440; longer ran under the panel (R7)


def eyebrow(f):
    """The one-line tag under which the promise sits: the version is prepended by the template."""
    text = "hooks for %d coding agents" % len(agents.AGENTS)
    full = "v%s . %s" % (f["version"], text)
    if len(full) > EYEBROW_MAX:
        raise SystemExit("eyebrow is %d characters, over %d: it would run under the hero panel" % (len(full), EYEBROW_MAX))
    return text


def hero_rows(beats):
    """The terminal panel in the hero: the end of `replay` (the last four steps), then the whole `rewind`.
    Rows are (kind, text); every cmd row is a beat's command and every out row a line that beat printed."""
    replay, rewind = beats[0], beats[2]
    rl = replay["output"].rstrip("\n").split("\n")
    rows = [("cmd", replay["command"]), ("gap", "    ...")] + [("out", ln) for ln in rl[-4:]]
    rows.append(("cmd", rewind["command"]))
    for i, ln in enumerate(rewind["output"].rstrip("\n").split("\n")):
        rows.append(("hit" if i in rewind["accent_rows"] else "out", ln))
    return rows


def nowrap_urls(text):
    """A URL on a phone may break only after a slash, never at a hyphen inside a name: each slash-delimited
    piece is kept whole and a <wbr> sits between the pieces."""
    def url(w):
        pieces = re.split(r"(?<=/)(?!/)", w)
        return "<wbr>".join('<span class="nb">%s</span>' % e(p) for p in pieces if p)
    def word(w):
        if "://" in w:
            return url(w)
        if "-" in w.strip("-") and len(w) > 2:         # your-project, --session-id: never split at the hyphen
            return '<span class="nb">%s</span>' % e(w)
        return e(w)
    return " ".join(word(w) for w in text.split(" "))


def term(rows):
    """Rows of a terminal panel as HTML, one block per row (a wrapped row gets a hanging indent): the prompt and
    comments in Playhead, hit rows in Rewind."""
    out = []
    for kind, text in rows:
        t = nowrap_urls(text)
        if kind == "cmd":
            out.append('<span class="l"><span class="p">$ </span>%s</span>' % t)
        elif kind in ("gap", "c"):
            out.append('<span class="l"><span class="c">%s</span></span>' % t)
        elif kind == "hit":
            out.append('<span class="l"><span class="hit">%s</span></span>' % t)
        else:
            out.append('<span class="l">%s</span>' % t)
    return "\n".join(out)


def panel(rows, cls=""):
    return '<pre class="term%s"><code>%s</code></pre>' % (" " + cls if cls else "", term(rows))


def code(lines):
    """A README sh block as a terminal panel. A trailing `# comment` moves to its own line (the README aligns
    comments with spaces, which would force a wide block on a phone): before the command when it describes it,
    after the command when it offers an alternative (`# or: ...`). Words are untouched."""
    rows = []
    for line in lines:
        if not line.strip():
            continue
        m = re.match(r"^(.*?)(?:\s+(# .*))?$", line)
        body, comment = m.group(1), m.group(2)
        if comment and comment.startswith("# or"):
            rows += [("cmd", body), ("c", comment)]
        elif comment:
            rows += [("c", comment), ("cmd", body)]
        else:
            rows.append(("cmd", body))
    return panel(rows)


def plain(lines):
    """A README block that is not shell (the attach workflow's yaml) as a panel: every line as written, no prompt,
    comment lines in Playhead."""
    return panel([("c" if ln.lstrip().startswith("#") else "out", ln) for ln in lines], "file")


def beat_rows(b, lit=True):
    """One command of the clip: its caption, the command, every line it printed; hit rows lit only if `lit`."""
    rows = [("c", b["caption"]), ("cmd", b["command"])]
    for i, ln in enumerate(b["output"].rstrip("\n").split("\n")):
        rows.append(("hit" if lit and i in b["accent_rows"] else "out", ln))
    return rows


AGENT_MARKS = {"claude": ("Claude Code", "claude-code.svg"), "codex": ("Codex", None), "cursor": ("Cursor", "cursor.svg"),
               "gemini": ("Gemini CLI", "gemini.svg"), "copilot": ("GitHub Copilot", "github-copilot.svg"),
               "droid": ("Factory Droid", None), "qwen": ("Qwen Code", "qwen.svg")}


def more_agents_html(block):
    """The docs answer for every agent beyond Claude Code, Codex and Cursor: the README's install block for them.
    The build stops when that block and agents.AGENTS name different agents, so a new hook cannot ship without
    its README line, and the README line cannot name a hook that does not exist."""
    others = [k for k in agents.AGENTS if k not in ("claude", "codex", "cursor")]
    named = re.findall(r"rewindagents install --agent (\w+)", "\n".join(block))
    if named != others:
        raise SystemExit("README '## %s' installs %s, agents.AGENTS has %s" % (MORE_AGENTS, named, others))
    return ("<p>The other agents with a hook, each built from the vendor&#x27;s hook documentation and tested with the "
            "documented payloads, not yet in a live session:</p>\n%s" % code(block))


def agent_strip(rel=""):
    """'Hooks for' + the agents rewindagents has a hook for, read from the package. A mark is shown only for an
    agent in agents.AGENTS (no logo for an agent without a tested hook); Codex is shown by name (no OpenAI mark)."""
    missing = set(agents.AGENTS) - set(AGENT_MARKS)
    extra = set(AGENT_MARKS) - set(agents.AGENTS)
    if missing or extra:
        raise SystemExit("agent strip out of step with agents.AGENTS: missing %s, extra %s" % (sorted(missing), sorted(extra)))
    items = []
    for key in agents.AGENTS:
        name, mark = AGENT_MARKS[key]
        img = ('<img src="%svendor/logos/%s" alt="" width="22" height="22">' % (rel, mark)) if mark else '<span class="ag-glyph" aria-hidden="true">&gt;_</span>'
        items.append('<li class="ag">%s<span>%s</span></li>' % (img, e(name)))
    return '<div class="agents"><span class="ag-label">Hooks for</span><ul>%s</ul></div>' % "".join(items)


FILM = "vsl-90s"
# Chapters of the film, named by the caption that opens each one (matched by its first words, so a re-cut of the
# film that drops a line fails the build instead of mislabelling the ruler).
CHAPTERS = [("Your agent just ran", "The wreck"), ("Why can't git help?", "What git can't return"),
            ("So what would help?", "The analogy"), ("Every tool call goes", "The record"),
            ("So which step", "Which step?"), ("One command", "Rewind"),
            ("Even the rewind", "Undo the undo"), ("You can now see", "The timeline"),
            ("Apache-2.0.", "Status"), ("Your editor has had undo", "Undo, for agents")]      # brand/<FILM>.mp4 is the film on the landing page; its captions are brand/vsl/<FILM>.srt


def srt_cues(path):
    """[(start_s, end_s, text)] from an .srt file (the film's captions, written by brand/vsl/build.py)."""
    def secs(t):
        h, m, rest = t.split(":")
        s_, ms = rest.split(",")
        return int(h) * 3600 + int(m) * 60 + int(s_) + int(ms) / 1000
    cues = []
    for block in re.split(r"\n\s*\n", read(*path.split("/")).strip()):
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        a, b = [x.strip() for x in lines[1].split("-->")]
        cues.append((secs(a), secs(b), " ".join(x.strip() for x in lines[2:])))
    return cues


def vtt(cues):
    def t(x):
        return "%02d:%02d:%06.3f" % (x // 3600, x % 3600 // 60, x % 60)
    return "WEBVTT\n\n" + "\n\n".join("%d\n%s --> %s\n%s" % (i, t(a), t(b), txt) for i, (a, b, txt) in enumerate(cues, 1)) + "\n"


def film(cues):
    """The 90-second film as a full-bleed band. Native controls without scripts; site.js swaps in the ruler:
    one tick per caption line, so the progress bar is the film's own script."""
    total = cues[-1][1]
    length = "%d:%02d" % (round(total) // 60, round(total) % 60)
    starts = {}
    for words, title in CHAPTERS:
        hit = [i for i, (_, _, txt) in enumerate(cues) if txt.startswith(words)]
        if len(hit) != 1:
            raise SystemExit("film chapter %r: %d captions start with %r" % (title, len(hit), words))
        starts[hit[0]] = title
    ticks = "".join('<span class="ft%s" data-t="%.2f"%s></span>' % (" ch" if i in starts else "", a,
                    (' data-title="%s"' % e(starts[i])) if i in starts else "") for i, (a, _, _) in enumerate(cues))
    return """<div class="film" id="film" data-total="%(total).2f">
<div class="film-frame">
<video class="film-video" controls preload="none" playsinline poster="assets/film-poster.jpg" aria-label="The rewindagents film, %(len)s, with captions">
<source src="assets/%(name)s.mp4" type="video/mp4">
<track kind="captions" src="assets/%(name)s.vtt" srclang="en" label="English" default>
</video>
<button class="film-play" type="button" hidden><span class="film-play-dot" aria-hidden="true"><svg width="22" height="24" viewBox="0 0 22 24"><path d="M3 2l17 10L3 22z" fill="currentColor"/></svg></span><span class="film-play-label">Play the film</span><span class="film-len">%(len)s, with music</span></button>
</div>
<div class="wrap film-bar" hidden><div class="film-ruler" role="slider" tabindex="0" aria-label="Film position" aria-valuemin="0" aria-valuemax="%(totali)d" aria-valuenow="0"><span class="film-fill"></span>%(ticks)s</div><span class="film-time">0:00 / %(len)s</span><button class="film-fs" type="button" aria-label="Full screen">Full</button></div>
<p class="wrap film-now" aria-live="off"></p>
</div>""" % {"total": total, "totali": round(total), "len": length, "name": FILM, "ticks": ticks}


def ruler(at, n=7, w=84, h=18):
    """The brand motif as a small inline SVG: n short ticks on a rule, the playhead on tick `at` (1-based) in
    Record; ticks and rule after it in Rule grey (the rewound part). Decorative: aria-hidden."""
    pitch = (w - 4) / (n - 1)
    parts = []
    xs = [2 + i * pitch for i in range(n)]
    px = xs[at - 1]
    parts.append('<rect x="0" y="%d" width="%.1f" height="1" fill="%s"/>' % (h - 2, px, C["Reel"]))
    parts.append('<rect x="%.1f" y="%d" width="%.1f" height="1" fill="%s"/>' % (px, h - 2, w - px, C["Rule"]))
    for i, x in enumerate(xs, 1):
        if i == at:
            continue
        parts.append('<rect x="%.1f" y="%d" width="1" height="5" fill="%s"/>'
                     % (x - 0.5, h - 6, C["Reel"] if i < at else C["Rule"]))
    parts.append('<path d="M%.1f 1H%.1fV4L%.1f 6.5V%dH%.1fV6.5L%.1f 4Z" fill="%s"/>'
                 % (px - 3, px + 3, px + 1, h - 1, px - 1, px - 3, C["Record"]))
    return ('<svg class="ruler" width="%d" height="%d" viewBox="0 0 %d %d" aria-hidden="true">%s</svg>'
            % (w, h, w, h, "".join(parts)))


def label(n, text):
    return '<p class="label">%s<span class="n">%02d</span><span>%s</span></p>' % (ruler(n, n=8), n, e(text))


def page(cfg, path, title, description, body, current):
    rel = "../" if "/" in path else ""
    url = cfg["site_url"] + PAGES[path]
    links = [("How it works", rel + "index.html#how", "how"), ("Install", rel + "index.html#install", "install"),
             ("Pricing", rel + "pricing.html", "pricing"), ("Docs", rel + "docs/", "docs")]
    nav = "".join('<a href="%s"%s>%s</a>' % (e(h), ' aria-current="page"' if k == current else "", n)
                  for n, h, k in links) + '<a href="%s">GitHub</a>' % e(cfg["repo_url"])
    ld = {"@context": "https://schema.org", "@type": "SoftwareApplication", "name": NAME,
          "description": description, "applicationCategory": "DeveloperApplication", "operatingSystem": "macOS, Linux",
          "softwareVersion": rewindagents.__version__, "url": url, "codeRepository": cfg["repo_url"],
          "license": cfg["repo_url"] + "/blob/%s/LICENSE" % cfg["branch"],
          "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
          "author": {"@type": "Person", "name": "John B Joseph"}}
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; media-src 'self'; font-src 'self'; connect-src 'none'; base-uri 'none'; form-action 'none'">
<meta name="referrer" content="strict-origin-when-cross-origin">
<title>%(title)s</title>
<meta name="description" content="%(desc)s">
<link rel="canonical" href="%(url)s">
<meta property="og:type" content="website">
<meta property="og:site_name" content="%(name)s">
<meta property="og:title" content="%(title)s">
<meta property="og:description" content="%(desc)s">
<meta property="og:url" content="%(url)s">
<meta property="og:image" content="%(site)sassets/social-preview-1280x640.png">
<meta property="og:image:width" content="1280">
<meta property="og:image:height" content="640">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="%(rel)sassets/favicon.svg" type="image/svg+xml">
<link rel="icon" href="%(rel)sassets/favicon-32.png" sizes="32x32" type="image/png">
<link rel="stylesheet" href="%(rel)ssite.css">
<script src="%(rel)svendor/flag.js"></script>
<script src="%(rel)svendor/gsap.min.js" defer></script>
<script src="%(rel)svendor/ScrollTrigger.min.js" defer></script>
<script src="%(rel)svendor/SplitText.min.js" defer></script>
<script src="%(rel)ssite.js" defer></script>
<script type="application/ld+json">%(ld)s</script>
</head>
<body>
<header class="top"><div class="wrap">
<a class="brand" href="%(rel)sindex.html" aria-label="%(name)s home"><img src="%(rel)sassets/logo-wordmark.svg" alt="%(name)s" width="%(wm_w)d" height="30"></a>
<nav class="nav" aria-label="Site">%(nav)s</nav>
</div></header>
<main>
%(body)s
</main>
<footer class="foot"><div class="wrap">
<a class="brand" href="%(rel)sindex.html" aria-label="%(name)s home"><img src="%(rel)sassets/logo-wordmark-reverse.svg" alt="%(name)s" width="%(wmr_w)d" height="26"></a>
<span class="credit">%(credit)s</span>
<nav aria-label="Footer"><a href="%(rel)sdocs/">Docs</a><a href="%(rel)spricing.html">Pricing</a><a href="%(repo)s">GitHub</a><a href="%(repo)s/blob/%(branch)s/LICENSE">%(licence)s licence</a></nav>
<span class="note">No cookies, no analytics, no trackers. Scripts are local and only animate; the page works without them.</span>
</div></footer>
</body>
</html>
""" % {"title": e(title), "desc": e(description), "url": e(url), "site": e(cfg["site_url"]), "name": NAME, "rel": rel,
       "nav": nav, "body": body, "credit": CREDIT, "licence": LICENCE, "repo": e(cfg["repo_url"]),
       "branch": e(cfg["branch"]), "ld": json.dumps(ld, sort_keys=True),
       "wm_w": svg_width("logo-wordmark.svg", 30), "wmr_w": svg_width("logo-wordmark-reverse.svg", 26)}


def svg_width(name, height):
    """Display width of a brand/ SVG at `height` px, from its viewBox, so a logo change never stretches it."""
    with open(os.path.join(BRAND, name), encoding="utf-8") as f:
        _, _, w, h = (float(v) for v in re.search(r'viewBox="([^"]+)"', f.read()).group(1).split())
    return round(w * height / h)


# ---- pages ------------------------------------------------------------------------------------------------
def plans(cfg, rel):
    has = [("has", "The recorder and the Claude Code hook: every tool call in a hash-chained log, every file saved before it changes"),
           ("has", "<code>replay</code>, <code>rewind</code> and <code>branch</code>, and <code>verify</code> against a pinned head"),
           ("has", "<code>export</code>: one session as one HTML page, with the diff each step made"),
           ("has", "<code>sessions</code>: every session in the log, and search by command or path"),
           ("has", "Runs on your machine. Standard library only. No account.")]
    items = lambda xs: "".join('<li class="%s"><span>%s</span></li>' % (k, t) for k, t in xs)  # noqa: E731
    if cfg.get("checkout_url"):
        buy, status = '<a class="btn btn-primary" href="%s">Buy Cloud</a>' % e(cfg["checkout_url"]), "Checkout is open."
    else:
        buy = '<a class="btn btn-ghost" href="%s">Join the waitlist</a>' % e(cfg["waitlist_url"])
        status = ("Not for sale yet. No price has been set, so none is shown. If you want it, open the waitlist issue "
                  "on GitHub and say what you would pay for.")
    return ('<div class="plans">'
            '<section class="plan" aria-labelledby="plan-oss"><h3 id="plan-oss">Open source <span class="pill">%s</span></h3>'
            '<div class="price">Free</div><p class="pricenote">Everything the tool does today.</p><ul>%s</ul>'
            '<a class="btn btn-primary" href="%sindex.html#install">Install</a></section>'
            '<section class="plan" aria-labelledby="plan-cloud"><h3 id="plan-cloud">Cloud <span class="pill pill-planned">planned</span></h3>'
            '<div class="price">Not yet priced</div><p class="pricenote">%s</p><ul>%s</ul>%s</section></div>'
            % (LICENCE, items(has), rel, e(status), items([("planned", e(t)) for _, t in PLANNED]), buy))


def faq_html(items, open_all=False):
    return '<div class="faq">%s</div>' % "".join(
        '<details%s><summary>%s</summary><p>%s</p></details>' % (" open" if open_all else "", e(q), a) for q, a in items)


def index_html(cfg, f, hero, open_all=False):
    rel = ""
    b = f["blocks"]
    n, good = f["steps"], f["good_step"]
    desc = ("Open-source recorder for coding agents. Every tool call goes into a tamper-evident, hash-chained log and "
            "every file is saved before it changes. Replay a session step by step and rewind the working tree to any "
            "step. Hooks for Claude Code, Codex and Cursor.")
    hero_s = """
<section class="hero" aria-labelledby="h1"><div class="wrap">
<div class="hero-text">
<p class="eyebrow"><b>v%(v)s</b> %(eyebrow)s</p>
<h1 id="h1">%(promise)s</h1>
<p class="lede">rewindagents records every tool call your coding agent makes and saves a copy of each file before the agent changes it. Replay the session step by step. Rewind the working tree to any step, or keep the current files as a branch and then rewind. The agent works at full speed, and every step it takes can be taken back, within the <a href="#limits">limits</a> below.</p>
<div class="cta"><a class="btn btn-primary" href="#install">Install</a><a class="btn btn-ghost" href="docs/">Read the docs</a></div>
</div>
<div class="hero-panel">
<div class="panel"><div class="panel-head"><span>a session of %(n)d steps; the last %(wreck)d wrecked the repo</span></div>%(hero)s</div>
<p class="caption">Lines from the session behind the clip below. The recorder, the four files and the step numbers are real; a test replays the session and fails if a line changes.</p>
<ul class="facts"><li>standard library only</li><li>no network, no account</li><li>never stops or changes a call</li><li>%(licence)s</li></ul>
</div>
%(agents)s
</div></section>
""" % {"v": e(f["version"]), "eyebrow": e(eyebrow(f)), "licence": LICENCE, "promise": PROMISE, "n": n, "wreck": f["wreck_steps"], "hero": panel(hero), "agents": agent_strip()}

    right = beat_rows(f["beats"][1]) + beat_rows(f["beats"][2]) + beat_rows(f["beats"][3])
    demo = """
<section class="sec" id="demo" aria-labelledby="h-demo"><div class="wrap">
%(label)s
<div class="head"><h2 id="h-demo">A wrecked repo, put back in one command.</h2>
<p class="lede">An agent works in a small project for %(n)d steps. Steps %(s13)d and %(s14)d delete the tests and overwrite the config. <code>rewindagents rewind %(good)d</code> puts the files back the way they were right after step %(good)d. The first %(good)d steps stay.</p></div>
</div>
%(film)s
<div class="wrap">
<div class="session">
<div><p class="small">The session as text. First, every step the agent took.</p>%(left)s</div>
<div><p class="small">Then the damage, the rewind, and the project after it.</p>%(right)s</div>
</div>
</div></section>
""" % {"film": film(srt_cues("brand/vsl/%s.srt" % FILM)), "label": label(1, "The film"), "n": n, "good": good, "s13": n - 1, "s14": n, "gw": f["gif"]["width"],
       "gh": f["gif"]["height"], "secs": ("%.1f" % f["gif"]["seconds"]).rstrip("0").rstrip("."), "frames": f["gif"]["frames"],
       "left": panel(beat_rows(f["beats"][0], lit=False), "fill"), "right": panel(right, "fill")}


    timeline = """
<section class="sec" id="timeline" aria-labelledby="h-timeline"><div class="wrap">
%(label)s
<div class="head" data-reveal><h2 id="h-timeline">The flight recorder for your coding agent.</h2>
<p class="lede">See exactly what your agent did, step by step, with the diff each step made. Take back the whole session, one step, or one file, and preview the change before you make it.</p></div>
<figure class="shot"><img src="assets/ui-timeline.png" alt="rewindagents ui: the demo session as a timeline. Steps 13 and 14 are struck through as rewound by step 15; the right panel shows the diff step 15 restored, with Preview rewind to here and Rewind to here buttons" width="1440" height="900" loading="lazy">
<figcaption><code>rewindagents ui</code> on the demo session: steps 13 and 14 struck through, rewound by step 15. Local only, on 127.0.0.1, behind a one-time token.</figcaption></figure>
<div class="trio">
<div><h3>One command to set up</h3><p><code>init</code> finds the agents you have and adds the hook to each one, keeping every hook already there.</p>%(quick)s</div>
<div><h3>See it</h3><p>The timeline in your browser: every step, every file, every diff. <kbd>j</kbd> <kbd>k</kbd> to move, <kbd>r</kbd> to rewind.</p>%(ui)s</div>
<div><h3>Take back exactly what you mean</h3><p>Preview a rewind as a diff, then take back the whole session or a single file. Every rewind is a new step, so it can be undone.</p>%(precise)s</div>
</div>
</div></section>
""" % {"label": label(2, "The timeline"), "quick": code(b["quick"][:1]), "ui": code(b["ui"][:1]),
       "precise": code([ln for ln in f["quick_use"] if ln.lstrip().startswith(("rewindagents diff", "rewindagents rewind"))])}

    install = """
<section class="sec" id="install" aria-labelledby="h-install"><div class="wrap">
%(label)s
<div class="head"><h2 id="h-install">Install, then add the hook to a project.</h2>
<p class="lede">Python %(py)s. No dependencies beyond the standard library. Tested on %(tested)s. Not on PyPI yet, so install from the repository. The <a href="docs/">docs</a> walk through a first session.</p></div>
<div class="install-row"><div><h3>Get the command</h3><p><code>pipx</code> installs it from the repository, as in the panel. From a clone, <code>pip install .</code> works too; without installing, <code>PYTHONPATH=src python3 -m rewindagents</code> runs the same CLI.</p></div>%(install)s</div>
<div class="pair"><div><h3>Add the Claude Code hook</h3>%(hook)s</div><div><h3>Codex and Cursor hooks</h3>%(agents)s</div></div>
<div class="pair-note"><p><code>install</code> keeps everything already in the file and does nothing if the hook is already there. For Codex the file is <code>%(codex)s</code> and for Cursor <code>%(cursor)s</code>; those two hooks are tested with the payloads in the vendors&#x27; documentation, not yet in a live session. <code>.rewindagents/</code> gets its own <code>.gitignore</code>, so the log and the copies stay out of your commits.</p></div>
</div></section>
""" % {"label": label(3, "Install"), "py": e(f["py_req"]), "tested": e(f["tested_on"]), "install": code(b["install"]), "hook": code(b["hook"]),
       "agents": code(b["agents"]), "codex": e(f["agents"]["codex"]["settings"]), "cursor": e(f["agents"]["cursor"]["settings"])}

    how = """
<section class="sec" id="how" aria-labelledby="h-how"><div class="wrap">
%(label)s
<div class="head"><h2 id="h-how">Record. Checkpoint. Rewind.</h2>
<p class="lede">A hook runs before and after every tool call the agent makes. It never stops a call and never changes one: it always exits 0, even when its own input is broken or the disk is full, and prints nothing but the one answer Cursor requires from a permission hook.</p></div>
<ol class="steps">
<li>%(r1)s<h3>Record</h3><p>Every call gets a <code>pre</code> record (tool and input) and a <code>post</code> record (tool and response) in <code>.rewindagents/log.jsonl</code>. Each record carries the SHA-256 of the one before it, so editing, deleting or reordering any record makes <code>verify</code> fail and name the first bad record. Appends are locked, so several processes can write to one log.</p></li>
<li>%(r2)s<h3>Checkpoint</h3><p>Before <code>Write</code>, <code>Edit</code>, <code>MultiEdit</code> and <code>NotebookEdit</code>, the current bytes of the target file go to <code>.rewindagents/objects/&lt;sha256&gt;</code>. Around a <code>Bash</code> command, the project&#x27;s files are saved first and scanned after, and only the files the command changed, created or deleted are checkpointed. Copies are stored by hash, so an unchanged file is stored once.</p></li>
<li>%(r3)s<h3>Rewind</h3><p><code>rewind N</code> puts back every file a later step changed and deletes the files later steps created. It first checks the hash chain and the hash of every stored copy; if the chain is broken it changes nothing. A rewind saves the current files and records itself as a new step, so a rewind is undone with another rewind.</p></li>
</ol>
</div></section>
""" % {"label": label(4, "How it works"), "r1": ruler(2, n=5, w=60, h=16), "r2": ruler(3, n=5, w=60, h=16), "r3": ruler(4, n=5, w=60, h=16)}

    limits = """
<section class="sec" id="limits" aria-labelledby="h-limits"><div class="wrap">
%(label)s
<div class="head"><h2 id="h-limits">What it records, and where it stops.</h2>
<p class="lede">The real behaviour and the real limit, from the code. <code>rewind</code> reports every file it could not put back and exits 1 if there was one.</p></div>
<ul class="ledger">
<li><span class="k">%(chars)s characters</span><span>A tool response longer than this is cut in the log, with its full length noted.</span></li>
<li><span class="k">%(mb)d MB</span><span>A file over this size is noted and not copied, so it is reported and not restored.</span></li>
<li><span class="k">%(files)s files</span><span>A project with more than this many files is not scanned around <code>Bash</code> commands. The call is still recorded, and <code>rewind</code> says the step was not scanned.</span></li>
<li><span class="k">the project directory</span><span>Only files inside it are scanned, saved or restored. In a git repository, the scan is what <code>git ls-files --cached --others --exclude-standard</code> lists: tracked and untracked files, not git-ignored ones. Outside git, every file except under %(skip)s.</span></li>
<li><span class="k">symlinks, directories</span><span>Symlinks are not saved. Directories created by later steps stay, empty, after a rewind.</span></li>
<li><span class="k">the end of the log</span><span>A hash chain proves the records are unchanged relative to each other. It cannot tell that records were cut off the end or that the whole file was rewritten and re-hashed. Pin the head hash somewhere the agent cannot write and check against it with <code>verify --head</code>.</span></li>
</ul>
</div></section>
""" % {"label": label(5, "Limits"), "chars": "{:,}".format(f["result_chars"]), "mb": f["file_mb"],
       "files": "{:,}".format(f["scan_files"]), "skip": ", ".join("<code>%s</code>" % e(d) for d in f["skip_dirs"])}

    commands = """
<section class="sec" id="commands" aria-labelledby="h-cmd"><div class="wrap">
%(label)s
<div class="head"><h2 id="h-cmd">Six commands. All of them local.</h2>
<p class="lede">Run them from the project directory, the one holding <code>.rewindagents/</code>. They work on the latest session unless you pass <code>--session ID</code>.</p></div>
<div class="cmdlist">
<div class="cmdrow"><div><h3>Replay, rewind, branch</h3><p><code>branch N --name X</code> keeps the current files and, in a git repository, commits the whole working tree to <code>rewindagents/X</code> through a temporary index, so your <code>HEAD</code>, index and current branch stay as they were.</p></div>%(replay)s</div>
<div class="cmdrow"><div><h3>Export a replay</h3><p>One HTML file with every step, its input and result, and for every file a step touched, the change that step made as a unified diff. Inline CSS only, no scripts, nothing fetched, the project&#x27;s path not in the page. A file over %(kb)d KB is described, not diffed; a diff longer than %(lines)d lines is cut, with the count left out.</p></div>%(export)s</div>
<div class="cmdrow"><div><h3>Find a session</h3><p>One line per session: id, first and last time, steps (with how many are rewinds), files touched. The latest session is marked. <code>--grep</code> keeps the sessions with a step whose command, file or input mentions the text, and lists those steps with their numbers.</p></div>%(sessions)s</div>
<div class="cmdrow"><div><h3>Verify the chain</h3><p>Checks every record against the one before it and names the first bad one. With <code>--head</code>, also catches records cut from the end.</p></div>%(verify)s</div>
</div>
</div></section>
""" % {"label": label(6, "Commands"), "replay": code(b["replay"]), "export": code(b["export"]), "sessions": code(b["sessions"]),
       "verify": code(b["verify"]), "kb": f["diff_kb"], "lines": f["diff_lines"]}

    pricing = """
<section class="sec" id="pricing" aria-labelledby="h-pricing"><div class="wrap">
%(label)s
<div class="head"><h2 id="h-pricing">The tool is free. Cloud is planned.</h2>
<p class="lede">Everything that exists is open source under %(licence)s. A paid tier may come later; nothing is sold before it exists.</p></div>
%(plans)s
<p class="small more">Details on the <a href="pricing.html">pricing page</a>.</p>
</div></section>
""" % {"label": label(7, "Pricing"), "licence": LICENCE, "plans": plans(cfg, rel)}

    faq_items = [
        ("Does it stop or change what the agent does?",
         "No. The hook records and checkpoints, then exits 0. It has no opinion about any call. The agent runs exactly as it would without the hook; the difference is that afterwards every step is on record and every file change can be put back."),
        ("Does anything leave my machine?",
         "No. rewindagents makes no outbound network connections: a test checks that no module under <code>src/</code> imports <code>socket</code>, <code>http</code> or <code>urllib</code>, except the timeline UI, which serves <code>rewindagents ui</code> on 127.0.0.1 only and checks a one-time token on every request. The log and the file copies live in <code>.rewindagents/</code> inside your project, and nothing reads them but you."),
        ("Which agents does it work with?",
         "Claude Code, through its <code>PreToolUse</code> and <code>PostToolUse</code> hooks; Codex, through the same hook file shape in <code>%s</code>; Cursor, through <code>%s</code>. The Claude Code hook has run in real sessions. The Codex and Cursor hooks are built from the vendors&#x27; hook documentation and tested with the documented payloads, not yet in a live session; the README says the same." % (f["agents"]["codex"]["settings"], f["agents"]["cursor"]["settings"])),
        ("Does it need git?",
         "No. Recording, replay and rewind work in any directory. Git changes two things: around <code>Bash</code> commands the scan follows <code>git ls-files</code>, so git-ignored files are left alone, and <code>branch</code> commits the current files to a git branch. Outside git, <code>branch</code> keeps them in the log only."),
        ("What happens if the log is tampered with?",
         "<code>verify</code> names the first record that does not match the one before it, <code>rewind</code> changes nothing, and <code>export</code> still writes the page, with a notice naming the bad record, and exits 1. Records cut off the end are only caught against a pinned head hash."),
        ("Is it free?",
         "Yes, under %s: the recorder, the hook, replay, rewind, branch, export and sessions. A paid Cloud tier is planned and nothing is sold before it exists." % LICENCE),
    ]
    faq = """
<section class="sec" id="faq" aria-labelledby="h-faq"><div class="wrap">
%(label)s
<div class="head"><h2 id="h-faq">Questions.</h2></div>
%(items)s
</div></section>
""" % {"label": label(8, "Questions"), "items": faq_html(faq_items, open_all)}

    closing = """
<section class="sec close" aria-labelledby="h-close"><div class="wrap">
<div class="closegrid"><div><h2 id="h-close">Install it, add the hook, carry on.</h2>
<div class="cta"><a class="btn btn-primary" href="#install">Install</a><a class="btn btn-ghost" href="docs/">Read the docs</a></div></div>
%(install)s</div>
</div></section>
""" % {"install": code(b["install"][:1])}

    body = hero_s + demo + timeline + install + how + limits + commands + pricing + faq + closing
    return page(cfg, "index.html", "%s: %s" % (NAME, PROMISE.rstrip(".")), desc, body, "home")


def pricing_html(cfg, f):
    rel = ""
    desc = "rewindagents is free under %s. A Cloud tier is planned and not yet priced; the waitlist is a GitHub issue." % LICENCE
    items = [
        ("Will the open-source tool stay free?",
         "The code you have is %s, and that licence cannot be withdrawn from it. Nothing that exists today is behind a paywall: the recorder, the hook, replay, rewind, branch, export and sessions are all in the open-source tier." % LICENCE),
        ("What would Cloud add?",
         "Things that need a service rather than a command: the same session history on every machine you use, the export page hosted at a link you can hand to a reviewer, sessions kept for longer than a laptop keeps them, and search across all of them. None of it is built yet. <code>export</code> and <code>sessions</code> are the local halves and are free."),
        ("How does the waitlist work?",
         "It is a GitHub issue on the repository with the label <code>waitlist</code>, as the README says. Say what you would pay for. There is no form, no email list and no tracking on this site."),
        ("Can my company get an invoice or a quote today?",
         "No. Nothing is for sale yet. When Cloud exists, this page will carry the price and a checkout link, and the link will live in one config key until then."),
    ]
    body = """
<section class="sec first" aria-labelledby="h1"><div class="wrap">
%(label)s
<div class="head"><h1 id="h1" class="h1-small">The tool is free. Cloud is planned.</h1>
<p class="lede">What exists is open source. What is planned has no price and is not for sale.</p></div>
%(plans)s
</div></section>
<section class="sec" aria-labelledby="h-q"><div class="wrap">
%(label2)s
<div class="head"><h2 id="h-q">Before you ask.</h2></div>
%(faq)s
</div></section>
""" % {"label": label(1, "Pricing"), "plans": plans(cfg, rel), "label2": label(2, "Questions about paying"),
       "faq": faq_html(items, open_all=True)}
    return page(cfg, "pricing.html", "Pricing: %s" % NAME, desc, body, "pricing")


def docs_html(cfg, f):
    rel = "../"
    b = f["blocks"]
    desc = "Getting started with rewindagents: install, add the hook to Claude Code, Codex or Cursor, a first session, replay, rewind, branch, export, find a session, verify the log."
    toc = [("install", "Install"), ("hook", "Add the hook"), ("first", "A first session"), ("recorded", "What gets recorded"),
           ("replay", "Replay and rewind"), ("branch", "Branch"), ("ui", "Timeline in a browser"), ("export", "Export"),
           ("sessions", "Find a session"), ("bundle", "Move a session"), ("attach", "Attach to a PR"),
           ("verify", "Verify"), ("status", "Is it recording?"), ("gc", "Free space"),
           ("overhead", "Overhead"), ("limits", "Limits"),
           ("remove", "Remove it")]
    first = "".join('<li><p>%s</p>%s</li>' % (text, panel(beat_rows(bt, lit=(i == 2)))) for i, (text, bt) in enumerate(zip((
        "Ask Claude Code for anything in a project with the hook installed; here, %d steps that add a timeout to a small service, then two steps that delete the tests and overwrite the config. <code>replay</code> lists every step with its number." % f["good_step"],
        "git shows the damage: three files changed, two deleted.",
        "Rewind to the last good step. Every restored file is named, and the rewind is itself a step, so the last line says how to undo it.",
        "git shows the first %d steps kept and the tests back." % f["good_step"]), f["beats"])))
    body = """
<section class="sec first" aria-labelledby="h1"><div class="wrap">
%(label)s
<div class="head"><h1 id="h1" class="h1-small">Getting started.</h1>
<p class="lede">Install, add the hook to one project, let the agent work, then look at the session and step back when you need to. Every command here is the README&#x27;s, and a test checks that each one is a real subcommand.</p></div>
<div class="docs">
<nav class="toc" aria-label="On this page">%(toc)s</nav>
<article class="doc">
<h2 id="install">Install</h2>
<p>Python %(py)s, standard library only. Tested on %(tested)s. Not on PyPI yet, so install from the repository:</p>
%(install)s
<p>The last command prints the version it installed:</p>
%(version)s
<p>Or from a clone, <code>pip install .</code>. Without installing, <code>PYTHONPATH=src python3 -m rewindagents</code> runs the same CLI from a clone; then the undo hint says <code>python3 -m rewindagents</code> instead of <code>rewindagents</code>.</p>

<h2 id="hook">Add the hook</h2>
%(init)s
<p>%(init_says)s</p>
<p>Or add it to one agent at a time:</p>
%(hook)s
<p><code>install</code> adds a <code>PreToolUse</code> and a <code>PostToolUse</code> hook to the settings file, keeps everything already in it, and does nothing if the hook is already there. The command it writes names the Python that rewindagents was installed into by absolute path, so it runs whether or not a virtualenv is active. To remove the hook, run <code>rewindagents uninstall</code> (see <a href="#remove">Remove it</a>).</p>
%(agents)s
<p>For Codex the file is <code>%(codex)s</code>, in the same shape as Claude Code&#x27;s settings; Codex asks you to trust the hook once (<code>/hooks</code>) and remembers the trust by the hook&#x27;s hash. For Cursor the file is <code>%(cursor)s</code> with a <code>preToolUse</code> and a <code>postToolUse</code> entry; because Cursor&#x27;s <code>preToolUse</code> is a permission hook that treats an empty answer as a failure, the hook prints <code>{"permission": "allow"}</code> before a call and <code>{}</code> after one, which changes nothing (a deny from another hook still wins). The Codex and Cursor hooks are tested with the payloads in the vendors&#x27; documentation and through the installed command, not yet in a live session.</p>
%(more_agents)s

<h2 id="first">A first session</h2>
<p>The session behind the clip on the front page, as it ran. Every line below is what the command printed; <code>tests/test_demo.py</code> runs the same session and fails if a line changes.</p>
<ol class="walk">%(first)s</ol>

<h2 id="recorded">What gets recorded</h2>
<p>In each project the agent works in, with the hook installed:</p>
<ul>
<li>every tool call gets a <code>pre</code> record (tool and input) and a <code>post</code> record (tool and response) in <code>.rewindagents/log.jsonl</code>, in one hash chain. A response longer than %(chars)s characters is cut, with the full length noted.</li>
<li>in Claude Code, before %(tools)s, the current bytes of the target file are copied to <code>.rewindagents/objects/&lt;sha256&gt;</code> and the hash goes into the <code>pre</code> record. A file that does not exist yet is recorded as absent. Files over %(mb)d MB are noted and not copied.</li>
<li>around every <code>Bash</code> call, the project&#x27;s files are saved before the command and scanned again after it; the <code>post</code> record checkpoints only the files that were changed, deleted or created. Copies are stored by SHA-256, and a stat cache in <code>.rewindagents/index.json</code> means only files whose size or modification time changed are read again.</li>
<li>in Codex and Cursor, that same scan runs around every call except the tools their documentation names that cannot change files (Cursor: %(cursor_ro)s; Codex: %(codex_ro)s), because the input of their edit tools is not documented and the hook never reads a file path out of those payloads.</li>
<li><code>.rewindagents/</code> gets its own <code>.gitignore</code>, so the log and the copies stay out of your commits.</li>
</ul>
<p>The hook never stops a call and never changes one. It prints nothing and always exits 0; any problem goes to stderr only.</p>

<h2 id="replay">Replay and rewind</h2>
<p>Run these from the project directory. They work on the latest session unless you pass <code>--session ID</code>.</p>
%(replay)s
<p><code>replay</code> prints one line per step: number, tool, file or command, and how many files the step checkpointed. <code>replay --step N</code> shows one step in full. <code>rewind N</code> puts back every file that a step after N changed and deletes the files those steps created; <code>rewind 0</code> undoes the whole session. Before writing anything it checks the hash chain and the SHA-256 of every stored copy: if the chain is broken it changes nothing, and a copy that no longer matches is reported and left as it is.</p>
<p>A rewind is undoable. It first saves the current bytes of every file it will change and records itself as a new step, then prints <code>undo it with: rewindagents rewind &lt;step&gt; --session &lt;id&gt;</code>. In the session above, the rewind to step %(good)d of %(n)d became step %(n1)d, and undoing it is <code>rewind %(n)d</code>.</p>

<h2 id="branch">Branch</h2>
<p><code>branch N --name X</code> does what <code>rewind N</code> does and, in a git repository, first commits the whole current working tree to the branch <code>rewindagents/X</code>. It does this through a temporary index, so your <code>HEAD</code>, index and current branch stay as they were. Outside git, the current files are kept in the log only.</p>

<h2 id="ui">Timeline in a browser</h2>
%(ui)s
<p>%(ui_says)s</p>

<h2 id="export">Export</h2>
%(export)s
<p>One HTML file with the whole session: every step with its tool, input and result, and for every file a step checkpointed, the change that step made as a unified diff (the file before the step against the file after it: its next checkpoint in the session, or the file as it is now). Inline CSS only, no scripts, nothing fetched. Paths are shown relative to the project; where the project lives on disk is not in the page.</p>
<ul>
<li>A file over %(kb)d KB on either side is described, not diffed. A diff longer than %(lines)d lines is cut, with the count of lines left out. Binary files show their size before and after.</li>
<li><code>--no-contents</code> drops inputs, results and diffs and keeps the one-line summary of each step.</li>
<li>If the hash chain does not verify, the page is still written, with a notice naming the first bad record, and the command exits 1.</li>
</ul>

<h2 id="sessions">Find a session</h2>
%(sessions)s
<p>One line per session, in the order the sessions first wrote to the log: the session id, the local time of its first and last record, the number of steps (with how many of them are rewinds or branches) and the files it touched; a second line names the first %(show)d files and counts the rest. The session that wrote the last record is marked <code>(latest)</code>.</p>
<p><code>--grep TEXT</code> keeps the sessions with a step whose <code>replay</code> line or checkpointed path contains TEXT, in any case, and lists those steps with their numbers. Exit code 1 if no session matches.</p>

<h2 id="bundle">Move a session</h2>
%(bundle)s
<p>%(bundle_says)s</p>

<h2 id="attach">Attach to a PR</h2>
%(attach)s
<p>%(attach_says)s</p>
%(attach_yaml)s
<p>%(action_says)s</p>

<h2 id="verify">Verify</h2>
%(verify)s
<p><code>verify</code> checks every record against the one before it and names the first bad record. A hash chain cannot tell on its own that records were cut off the end or that the whole file was rewritten and re-hashed; <code>rewindagents head</code> prints the current head hash, and <code>verify --head</code> checks against a copy you pinned somewhere the agent cannot write.</p>
<p>The recorder also works on its own, without the hook:</p>
%(record)s

<h2 id="status">Is it recording?</h2>
%(status)s
<p>%(status_says)s</p>

<h2 id="gc">Free space</h2>
%(gc)s
<p>%(gc_says)s</p>

<h2 id="overhead">Overhead</h2>
%(overhead)s

<h2 id="limits">Limits</h2>
<ul>
<li>Only the project directory is scanned, saved and restored. A command that changes files elsewhere is recorded, not saved, and files outside the project are reported and left alone.</li>
<li>In a git repository the scan follows <code>git ls-files --cached --others --exclude-standard</code>, so git-ignored files are not saved. Outside git, every file under the project except under %(skip)s.</li>
<li>Symlinks are not saved. Files over %(mb)d MB are not copied. A project with more than %(files)s files is not scanned around <code>Bash</code> commands; the call is still recorded and <code>rewind</code> reports the step as not scanned.</li>
<li>Directories created by later steps stay, empty, after a rewind. If anything could not be restored, <code>rewind</code> lists it and exits 1.</li>
<li>Needs a Unix for now: the log lock has a Windows path (<code>msvcrt</code>), but the tests have not run on Windows yet. The Claude Code hook has run in real sessions; the Codex and Cursor hooks are tested with the documented payloads, not yet in a live session.</li>
</ul>

<h2 id="remove">Remove it</h2>
%(uninstall)s
<p><code>uninstall</code> removes only the hook entries <code>install</code> wrote, so every other hook and setting stays, and it never touches <code>.rewindagents/</code>: recorded sessions can still be replayed and rewound. To remove everything, also delete <code>.rewindagents/</code> in the project and uninstall the package (<code>pipx uninstall rewindagents</code> or <code>pip uninstall rewindagents</code>). Nothing else was created.</p>

<h2 id="tests">Tests</h2>
%(tests)s
<p>That runs against the source tree and skips the tests of the installed command. <code>.fire-test-cmd</code> in the repository holds the full command: it builds a venv, installs the package into it and runs every test, including the ones that drive the installed <code>rewindagents</code> binary, replay the session above, and rebuild this site byte for byte.</p>
</article>
</div>
</div></section>
""" % {"label": label(1, "Docs"), "toc": "".join('<a href="#%s">%s</a>' % (a, t) for a, t in toc), "py": e(f["py_req"]),
       "tested": e(f["tested_on"]), "install": code(b["install"]),
       "version": panel([("cmd", "rewindagents --version"), ("out", "rewindagents %s" % f["version"])]),
       "hook": code(b["hook"]), "agents": code(b["agents"]), "uninstall": code(f["uninstall"]),
       "status": code(f["status"]), "status_says": " ".join(md_inline(s) for s in f["status_says"]),
       "bundle": code(f["bundle"]), "bundle_says": " ".join(md_inline(s) for s in f["bundle_says"]),
       "gc": code(f["gc"]), "gc_says": " ".join(md_inline(s) for s in f["gc_says"]),
       "ui": code(b["ui"]), "ui_says": " ".join(md_inline(s) for s in f["ui_says"]),
       "attach": code(f["attach"]), "attach_says": " ".join(md_inline(s) for s in f["attach_says"]),
       "attach_yaml": plain(f["attach_yaml"]), "action_says": " ".join(md_inline(s) for s in f["action_says"]),
       "codex": e(f["agents"]["codex"]["settings"]),
       "cursor": e(f["agents"]["cursor"]["settings"]),
       "more_agents": more_agents_html(f["more_agents"]),
       "init": code(b["quick"]), "init_says": " ".join(md_inline(s) for s in f["init_says"]),
       "cursor_ro": ", ".join("<code>%s</code>" % e(t) for t in f["agents"]["cursor"]["read_only"]),
       "codex_ro": ", ".join("<code>%s</code>" % e(t) for t in f["agents"]["codex"]["read_only"]),
       "first": first, "chars": "{:,}".format(f["result_chars"]),
       "tools": ", ".join("<code>%s</code>" % t for t in f["file_tools"]), "mb": f["file_mb"], "replay": code(b["replay"]),
       "good": f["good_step"], "n": f["steps"], "n1": f["steps"] + 1, "export": code(b["export"]), "kb": f["diff_kb"],
       "lines": f["diff_lines"], "sessions": code(b["sessions"]), "show": f["show_files"], "verify": code(b["verify"]),
       "record": code(b["record"]), "skip": ", ".join("<code>%s</code>" % e(d) for d in f["skip_dirs"]),
       "files": "{:,}".format(f["scan_files"]), "tests": code(b["tests"]), "overhead": overhead_html()}
    return page(cfg, "docs/index.html", "Getting started: %s" % NAME, desc, body, "docs")


def overhead_html():
    """The docs page's Overhead section: only what bench/hook_overhead.py wrote to bench/results.json, with the
    machine and the date, worded by that script's own helpers."""
    spec = importlib.util.spec_from_file_location("hook_overhead", os.path.join(ROOT, "bench", "hook_overhead.py"))
    bench = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bench)
    r = json.loads(read("bench", "results.json"))
    ms = bench._ms
    rows = "".join(
        "<li>{:,} files: <code>Read</code> {}, <code>Edit</code> {}, <code>Bash</code> {} (90th percentile {}, {}, {}); "
        "the first <code>Bash</code> call, which copies every file into the empty store, {}.</li>".format(
            x["files"], *(ms(x["tools"][t]["median_ms"]) for t in bench.TOOLS),
            *(ms(x["tools"][t]["p90_ms"]) for t in bench.TOOLS), ms(x["first_bash_ms"]))
        for x in r["results"])
    return ("<p>Time the hook adds to one tool call (both hook processes, before and after the call), median of %d "
            "calls, measured by <code>bench/hook_overhead.py</code> on %s. Each hook event is a new Python process; "
            "starting one and importing the package alone takes %s (median), and every call starts two.</p>\n"
            "<ul>%s</ul>\n<p>Other machines, disks and projects will differ; <code>python3 bench/hook_overhead.py</code> "
            "measures yours. The raw numbers are in <code>bench/results.json</code>.</p>"
            % (r["results"][0]["tools"]["Read"]["runs"], e(bench.where(r)), ms(r["startup"]["median_ms"]), rows))


# ---- build ------------------------------------------------------------------------------------------------
def build(out=None, cfg=None, open_variant=False):
    out = out or HERE
    cfg = cfg or config()
    f = facts()
    hero = hero_rows(f["beats"])
    pages = {"index.html": index_html(cfg, f, hero), "pricing.html": pricing_html(cfg, f), "docs/index.html": docs_html(cfg, f)}
    if open_variant:        # review material only: the landing page with every answer open; never committed
        pages["index-open.html"] = index_html(cfg, f, hero, open_all=True)
    for rel, text in pages.items():
        path = os.path.join(out, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
    assets = os.path.join(out, "assets")
    os.makedirs(assets, exist_ok=True)
    for name in ASSETS:
        shutil.copyfile(os.path.join(BRAND, name), os.path.join(assets, name))
    if os.path.abspath(out) != HERE:        # a build elsewhere needs the static files beside the pages too
        shutil.copyfile(os.path.join(HERE, "site.css"), os.path.join(out, "site.css"))
        shutil.copyfile(os.path.join(HERE, "site.js"), os.path.join(out, "site.js"))
        for d in ("vendor",):
            shutil.copytree(os.path.join(HERE, d), os.path.join(out, d), dirs_exist_ok=True)
        shutil.copytree(os.path.join(HERE, "fonts"), os.path.join(out, "fonts"), dirs_exist_ok=True)
    # the film: brand/vsl/<FILM>-web.mp4 and its poster are written by brand/vsl/narration.py (web export, picture + music bed, no voice;
    # included once the narration exists); the captions are the VSL's own .srt
    shutil.copyfile(os.path.join(BRAND, "vsl", FILM + "-web.mp4"), os.path.join(assets, FILM + ".mp4"))
    shutil.copyfile(os.path.join(BRAND, "vsl", FILM + "-poster.jpg"), os.path.join(assets, "film-poster.jpg"))
    with open(os.path.join(assets, FILM + ".vtt"), "w", encoding="utf-8") as fh:
        fh.write(vtt(srt_cues("brand/vsl/%s.srt" % FILM)))
    manifest = {"pages": sorted(p for p in pages if p in PAGES), "facts": {k: v for k, v in f.items() if k != "beats"},
                "hero": [list(r) for r in hero], "assets": ASSETS, "credit": CREDIT, "promise": PROMISE,
                "planned": [p for p, _ in PLANNED], "site_url_key": "site_url", "checkout": bool(cfg.get("checkout_url"))}
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1, sort_keys=True)
        fh.write("\n")
    return pages


def fonts(cache=os.path.join(ROOT, ".brandcache")):
    """Copy the WOFF2 files the CSS declares, plus each family's OFL licence, into brand/site/fonts/."""
    out = os.path.join(HERE, "fonts")
    os.makedirs(out, exist_ok=True)
    for pkg, weights in FONTS.items():
        src = os.path.join(cache, "node_modules", "@fontsource", pkg)
        with open(os.path.join(src, "LICENSE"), encoding="utf-8") as fh:
            assert "SIL OPEN FONT LICENSE" in fh.read().upper(), pkg
        shutil.copyfile(os.path.join(src, "LICENSE"), os.path.join(out, "LICENSE-%s.txt" % pkg))
        for w in weights:
            name = "%s-latin-%d-normal.woff2" % (pkg, w)
            shutil.copyfile(os.path.join(src, "files", name), os.path.join(out, name))
            print("copied", name)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "build":
        pages = build()
        print("built %s in %s: %s" % (", ".join(sorted(pages)), HERE, config()["site_url"]))
    elif cmd == "fonts":
        fonts(*sys.argv[2:3])
    elif cmd == "open":
        if os.path.abspath(sys.argv[2]) == HERE:
            raise SystemExit("open: pick a directory outside brand/site (the open variant is never published)")
        print("built %s in %s" % (", ".join(sorted(build(out=sys.argv[2], open_variant=True))), sys.argv[2]))
    else:
        raise SystemExit("usage: build.py [build|fonts [cache]|open DIR]")
