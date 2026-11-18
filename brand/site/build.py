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
  python3 brand/site/build.py cards DIR  -> the share cards (og 1200x630, linkedin 1200x627, portrait 1080x1350) as
                                            HTML in DIR; ux-review/tools/cards.mjs renders them to PNG
"""
import html
import importlib.util
import json
import os
import re
import shutil
import subprocess
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
# Headline John approved 2026-11-18 (launch: lead with the shell gap; fork/compare stays as the second section). BRAND.md carries
# it word for word (tests/test_site.py); the promise above stays the base it is built on.
COURSE = "Your coding agent ran rm -rf. Take it back."
# The hero sets the headline on three lines at display size (2026-11-18, bold round); they must join back to COURSE.
COURSE_LINES = ("Your coding agent", "ran rm -rf.", "Take it back.")
FORK = "Fork a step, compare the runs"      # the README section the fork-and-compare panels come from
CREDIT = "made by John B Joseph"
LICENCE = "Apache-2.0"
PAGES = {"index.html": "", "pricing.html": "pricing.html", "docs/index.html": "docs/"}
# brand/ files the pages use, copied into brand/site/assets/ at build time (assets/ is git-ignored; the Pages
# workflow runs this build, so the published site carries the current clip and logo files).
ASSETS = ["ui-timeline.png", "demo.gif", "logo-wordmark.svg", "logo-wordmark-reverse.svg", "logo-mark.svg", "favicon.svg",
          "favicon-32.png", "social-preview-1280x640.png"]
# brand/site/og/ files, copied into assets/ next to the brand/ ones. The share card is rendered from this build's
# own pages (`build.py cards DIR`, then ux-review/tools/cards.mjs), so it is committed as a PNG here.
SITE_ASSETS = ["og-1200x630.png"]
OG_ALT = ("rewindagents: Your coding agent ran rm -rf. Take it back. A terminal shows rewindagents replay with steps "
          "13 and 14 (rm -rf tests, a config overwrite) struck through, then rewindagents rewind 12 restoring four files.")
FONTS = {"bricolage-grotesque": (700, 800), "hanken-grotesk": (400, 600), "commit-mono": (400, 700)}
C = {"Leader": "#F2F4F1", "Reel": "#121412", "Spool": "#1C201D", "Tape": "#55605A",
     "Record": "#B82A16", "Rewind": "#FF7A59", "Playhead": "#B9C2BB", "Rule": "#838C86"}
# The paid tier, as BRAND.md puts it. Each phrase must appear in BRAND.md (tests/test_site.py).
# The hosted layer from ux-review/ROADMAP.md (opt-in; the local tool never needs it). Planned, not built, not priced.
PLANNED = [("a shared page per comparison", "A shared page per comparison, linkable from a pull request or a chat"),
           ("parallel cloud sandboxes", "Saved starting points run in parallel cloud sandboxes, so ten attempts do not occupy a laptop"),
           ("comparison history", "A team's comparison history across repos and people: which agent, model or prompt wins on which kind of task"),
           ("scheduled re-runs", "Scheduled re-runs of a team's starting points when a model, prompt or CLAUDE.md changes, with a report of what got worse"),
           ("retention, SSO, seats", "Retention, SSO, seats: the things an organisation buys")]

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
STATUS_SENTENCES = ("After the hooks come this project's log", "Each hook that is in place is also run once",
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
MCP_HEADING = "The agent can undo its own steps: MCP server"
MCP_SENTENCES = ("The agent then gets seven tools", "They refuse, and")
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
                  "Without `--yes` and without a terminal to ask on", "`--agent claude` sets up only that agent",
                  "In a git repository the config files `init`", "`rewindagents init --undo` takes it all out again")
MORE_AGENTS = "Gemini CLI, Copilot CLI, Droid and Qwen Code hooks"
# The three commands after a bad run, under "After a bad run" on the docs page, with the README's words.
RESCUE = "After a bad run"
RESCUE_SENTENCES = ("Three commands, in the order you need them", "`rewind` and `revert` refuse, change nothing",
                    "Every rewind is itself a step")
# The README's words for fork and compare, on the landing page and under "Fork and compare" on the docs page.
FORK_SENTENCES = ("A recorded step is a starting point", "`rewindagents fork 12 --name try2` makes",
                  "In a git repository it is a", "Run any agent there")
COMPARE_SENTENCES = ("Back in the project, `rewindagents compare`", "`rewindagents compare --check",
                     "`rewindagents compare --diff proj try2`")
# The landing page's short form of the two (John, 2026-11-13: at most two short sentences each; the README's full
# sentences stay on the docs page, which the landing page links to). Every claim here is one the README makes.
FORK_SHORT = ("`rewindagents fork 12 --name try2` makes a new directory holding the project as `rewind 12` would leave it.",
              "Run any agent there, or edit by hand.")
COMPARE_SHORT = ("`rewindagents compare` lines up the project and every run forked from the same step: files changed, "
                 "lines added and removed.", "`--check` runs your own check in each run and reports pass or the exit code.")
FORK_LIMIT_SENTENCES = ("`fork` refuses a step", "`compare` writes nothing", "Runs from different steps are not mixed")
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
            ("record", "Use it"), ("tests", "Tests"), ("quick", "Quick start"), ("ui", "Timeline UI"), ("mcp", MCP_HEADING))},
        "quick_use": readme_blocks(readme, "Quick start")[1],
        "channels": readme_blocks(readme, "Install")[1],
        "editors": readme_sentence(readme, "In VS Code, search"),
        "rescue": readme_block(readme, RESCUE),
        "rescue_says": [readme_sentence(readme, s) for s in RESCUE_SENTENCES],
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
        "mcp_says": [readme_sentence(readme, s) for s in MCP_SENTENCES],
        "attach": next(blk for blk in readme_blocks(readme, "Attach a replay to a pull request")
                       if blk[0].startswith("rewindagents bundle")),
        "attach_yaml": readme_blocks(readme, "Attach a replay to a pull request", "yaml")[0],
        "attach_says": [readme_sentence(readme, s) for s in ATTACH_SENTENCES],
        "action_says": [readme_sentence(readme, s) for s in ATTACH_ACTION_SENTENCES],
        "beats": demo["beats"],
        "fork": readme_block(readme, FORK),
        "fork_lead": readme_sentence(readme, "Rewind to any step, fork it"),
        "fork_says": [readme_sentence(readme, s) for s in FORK_SENTENCES],
        "compare_says": [readme_sentence(readme, s) for s in COMPARE_SENTENCES],
        "fork_limits": [readme_sentence(readme, s) for s in FORK_LIMIT_SENTENCES],
        "runs": json.loads(read("brand", "demo", "runs.json")),
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


RUNS_FORK, RUNS_COMPARE, RUNS_DIFF = ("fork step 2 into a second attempt", "compare, with the test file as the check",
                                     "how the second attempt differs")


def runs_rows(runs, part):
    """Panels quoting brand/demo/runs.json, what ux-review/try-runs.sh printed against an installed build
    (brand/demo/runs.py). Every cmd row is a command the script runs and every out/hit row a line it printed;
    lines naming the script's temporary directory are left out, never rewritten. tests/test_runs_demo.py runs
    the script again and fails if a quoted line changes. part: "hero" (fork + compare) or "diff"."""
    o, c = runs["output"], runs["commands"]
    tmp = [ln for ln in o[RUNS_FORK] if ln.startswith("run clamp: ")]
    if not tmp:
        raise SystemExit("brand/demo/runs.json: fork output changed shape; update runs_rows()")
    if part == "diff":
        body = [ln for ln in o[RUNS_DIFF] if not ln.startswith(("# a/ = run", "(left in "))]
        return [("cmd", c["diff"])] + [("hit" if ln.startswith("+ ") or (ln.startswith("+") and not ln.startswith("+++")) else "out", ln)
                                       for ln in body]
    fork = [ln for ln in o[RUNS_FORK] if ln.strip().startswith("2 files as they were")]
    cmp_ = o[RUNS_COMPARE]
    table = cmp_[:cmp_.index("  - = as at the start; the same letter in a row = the same bytes in those runs.")]
    rows = [("cmd", c["fork"])] + [("out", ln) for ln in fork] + [("cmd", c["compare"])]
    for ln in table:      # the two tables keep their columns: "tab" rows never wrap (the panel scrolls instead)
        if ln.endswith("  pass"):
            rows.append(("tabhit", ln))
        elif ln.startswith("  "):
            rows.append(("tab", ln))
        else:
            rows.append(("out", ln))
    while rows[-1] == ("out", ""):
        rows.pop()
    return rows


def nowrap_urls(text, flags=False):
    """A URL on a phone may break only after a slash, never at a hyphen inside a name: each slash-delimited
    piece is kept whole and a <wbr> sits between the pieces. With `flags` (command rows only), a `--flag` and
    its value are kept whole too, so a wrap never falls between the two hyphens of `--settings` (UX audit F4).
    The tags change no text: the README-block test strips them before it compares."""
    def url(w):
        pieces = re.split(r"(?<=/)(?!/)", w)
        return "<wbr>".join('<span class="nb">%s</span>' % e(p) for p in pieces if p)
    def word(w):
        if "://" in w:
            return url(w)
        if "-" in w.strip("-") and len(w) > 2:         # your-project, --session-id: never split at the hyphen
            return '<span class="nb">%s</span>' % e(w)
        return e(w)
    words, out, i = text.split(" "), [], 0
    while i < len(words):
        w = words[i]
        if flags and w.startswith("--") and len(w) > 2:
            group = [w]
            if i + 1 < len(words) and words[i + 1] and not words[i + 1].startswith(("-", "#")):
                group.append(words[i + 1])
                i += 1
            out.append('<span class="nb">%s</span>' % e(" ".join(group)))
        else:
            out.append(word(w))
        i += 1
    return " ".join(out)


def hang(text):
    """Where a wrapped output row continues, in characters: under its last column when the row is a table
    (`replay` lines continue under the command, `restore` lines under the path), else two past its own indent.
    Without it a wrapped `-q` or `[1 checkpointed]` fell back to the panel's left edge (UX audit F4)."""
    lead = len(text) - len(text.lstrip(" "))
    cols = [m.end() for m in re.finditer(r"\S {2,}(?=\S)", text) if m.end() <= 24]
    return min(cols[-1] if cols else lead + 2, HANG_MAX)


HANG_MAX = 24   # site.css carries .l.i0 .. .l.i24 (the CSP allows no inline style, so the indent is a class)


def term(rows, struck=()):
    """Rows of a terminal panel as HTML, one block per row (a wrapped row gets a hanging indent): the prompt and
    comments in Playhead, hit rows in Rewind. Output rows carry their own indent in --i (see hang()).
    A command's text sits in .sel, which selects whole on one click (user-select: all) and leaves the `$` out:
    the scriptless copy (UX audit F2). Rows whose index is in `struck` get .x, a strike-through that marks
    steps a rewind undid (the hero; UX audit F3): a mark on the CLI's own text, never a change to it."""
    out = []
    for i, (kind, text) in enumerate(rows):
        t = nowrap_urls(text, flags=(kind == "cmd"))
        x = " x" if i in struck else ""
        if kind == "cmd":
            out.append('<span class="l"><span class="p">$ </span><span class="sel">%s</span></span>' % t)
        elif kind in ("gap", "c"):
            out.append('<span class="l"><span class="c">%s</span></span>' % t)
        elif kind in ("tab", "tabhit"):
            body = '<span class="hit">%s</span>' % t if kind == "tabhit" else t
            out.append('<span class="l t">%s</span>' % body)
        elif kind == "hit":
            out.append('<span class="l i%d"><span class="hit">%s</span></span>' % (hang(text), t))
        elif x:     # the strike starts at the text, not at the row's leading spaces
            lead = len(text) - len(text.lstrip(" "))
            out.append('<span class="l i%d">%s<span class="x">%s</span></span>'
                       % (hang(text), " " * lead, nowrap_urls(text[lead:])))
        else:
            out.append('<span class="l i%d">%s</span>' % (hang(text), t))
    return "\n".join(out)


def panel(rows, cls="", struck=()):
    return '<pre class="term%s"><code>%s</code></pre>' % (" " + cls if cls else "", term(rows, struck))


STAGE_TOOLS = ("Read", "Edit", "Write", "MultiEdit", "NotebookEdit")


def replay_steps(beats):
    """The replay lines as (step, tool, target, line), parsed from what the CLI printed."""
    out = []
    for ln in beats[0]["output"].rstrip("\n").split("\n"):
        m = re.match(r"^\s*(\d+)\s+(\w+)\s+(.*?)(?:\s+\[\d+ checkpointed\])?$", ln)
        if not m:
            raise SystemExit("replay line changed shape: %r" % ln)
        out.append((int(m.group(1)), m.group(2), m.group(3), ln))
    return out


def stage_rows(beats):
    """The hero stage's terminal: the whole `replay` (every step as printed), then the whole `rewind`."""
    replay, rewind = beats[0], beats[2]
    rows = [("cmd", replay["command"])] + [("out", ln) for ln in replay["output"].rstrip("\n").split("\n")]
    rows.append(("cmd", rewind["command"]))
    for i, ln in enumerate(rewind["output"].rstrip("\n").split("\n")):
        rows.append(("hit" if i in rewind["accent_rows"] else "out", ln))
    return rows


def stage_tree(beats, wreck_steps):
    """The project's files as the session saw them, derived from the recorded lines, never typed:
    - a file is on the tree when a replay line names it as a file tool's target or the rewind restores it;
    - a file is born at its first Write when the final `git status` lists it as untracked (`??`), else it was there
      before step 1;
    - `rm -rf DIR` (a Bash step) deletes every file under DIR that exists at that step;
    - a file comes back at the rewind output row that restores it.
    Returns [(dir, [(path, born, gone, back_row, touches)])], dirs in `ls` order (root first)."""
    steps = replay_steps(beats)
    files = {}
    for step, tool, target, _ in steps:
        if tool in STAGE_TOOLS:
            files.setdefault(target, []).append((step, tool))
    rew = beats[2]["output"].rstrip("\n").split("\n")
    back = {}
    for i, ln in enumerate(rew):
        m = re.match(r"^\s+restore\s+(\S+)$", ln)
        if m:
            back[m.group(1)] = i
            files.setdefault(m.group(1), [])
    untracked = {ln[3:] for ln in beats[3]["output"].rstrip("\n").split("\n") if ln.startswith("?? ")}
    born = {f: (min(s for s, t in files[f] if t == "Write") if f in untracked else 0) for f in files}
    gone = {}
    for step, tool, target, _ in steps:
        m = re.match(r"^rm -rf (\S+)$", target) if tool == "Bash" else None
        if m:
            d = m.group(1).rstrip("/") + "/"
            for f in files:
                if f.startswith(d) and born[f] <= step:
                    gone[f] = step
                    files[f].append((step, tool))
    for f in files:
        wrecked = [s for s, _ in files[f] if s in wreck_steps]
        if wrecked and f not in back:
            raise SystemExit("stage: %s was wrecked at step %s and the rewind does not restore it" % (f, wrecked))
    groups = {}
    for f in sorted(files):
        groups.setdefault(f.rsplit("/", 1)[0] + "/" if "/" in f else "", []).append(
            (f, born[f], gone.get(f, 0), back.get(f, -1), sorted(files[f])))
    return [(d, groups[d]) for d in sorted(groups)]


def stage_html(f):
    """The hero stage: a big ruler of the session's steps, the project's files, and the terminal that printed it.
    Built as the still (after the rewind), complete without a script. site.js plays it from the data attributes and,
    on scroll, scrubs it both ways; it shows and hides rows by visibility only, so nothing on the page moves."""
    beats, n, good, wreck = f["beats"], f["steps"], f["good_step"], f["wreck_steps"]
    rows = stage_rows(beats)
    wreck_lines = {ln for i, ln in enumerate(beats[0]["output"].rstrip("\n").split("\n")) if i in beats[0]["accent_rows"]}
    struck = {i for i, (k, t) in enumerate(rows) if k == "out" and t in wreck_lines}
    first_wreck = n - wreck + 1
    ticks = "".join('<span class="sr-tk%s" data-n="%d"><i>%d</i></span>'
                    % (" w" if k >= first_wreck else (" at" if k == good else ""), k, k) for k in range(1, n + 1))
    restore_word = re.match(r"^\s+(\w+)\s", next(ln for ln in beats[2]["output"].split("\n") if ln.strip().startswith("restore"))).group(1)
    groups = []
    for d, items in stage_tree(beats, set(range(first_wreck, n + 1))):
        lis = []
        for path, born, gone, back, touches in items:
            still = restore_word if back >= 0 else "%s %d" % (touches[-1][1], touches[-1][0]) if touches else ""
            cls = "ff" + (" back" if back >= 0 else "")
            lis.append('<li class="%s" data-born="%d" data-gone="%d" data-back="%d" data-touch="%s" data-still="%s">'
                       '<span class="fn"><span class="fd">%s</span>%s</span><span class="ftg">%s</span></li>'
                       % (cls, born, gone, back, ",".join("%d:%s" % t for t in touches), e(still), e(d), e(path[len(d):]), e(still)))
        groups.append('<div class="fgrp"><p class="fdir">%s</p><ul>%s</ul></div>' % (e(d or "./"), "".join(lis)))
    return """<div class="stage" id="stage">
<div class="stage-pin">
<div class="st-head"><span class="st-name">%(n)d steps; the last %(w)d wrecked the repo</span><span class="st-at">rewind %(good)d</span><span class="st-ctl"></span></div>
<div class="sruler" aria-hidden="true"><span class="sr-base"><span class="sr-fill"></span></span>%(ticks)s<span class="sr-phw"><span class="sr-ph"></span></span></div>
<div class="st-body">
<div class="ftree" role="group" aria-label="The project's files after the rewind">%(groups)s</div>
<div class="st-term">%(term)s</div>
</div>
</div>
<p class="caption st-cap">Lines the recorded session printed, unedited; the files are the ones those lines name. The strike-through is ours: it marks the two steps the rewind undid. A test replays the session and fails if a line changes; see <a href="#tested">Tested</a>.</p>
</div>""" % {"n": n, "w": wreck, "good": good, "ticks": ticks, "groups": "".join(groups),
             "term": panel(rows, struck=struck)}


def test_function_count():
    """`def test_` across tests/*.py, counted statically (unittest runs more cases, through inherited classes, so the
    page says "test functions", never "tests pass")."""
    d = os.path.join(ROOT, "tests")
    return sum(len(re.findall(r"^\s*def test_", read("tests", name), re.M)) for name in sorted(os.listdir(d)) if name.endswith(".py"))


def counters(cfg, f):
    """Numbers from the repository, counted when the site is built, each with where it comes from. No live fetches:
    the CSP is connect-src 'none' and the footer promises no trackers."""
    deps = re.search(r"^dependencies = \[(.*?)\]", read("pyproject.toml"), re.M | re.S)
    if deps is None:
        raise SystemExit("pyproject.toml has no dependencies list")
    n_deps = len([x for x in deps.group(1).split(",") if x.strip()])
    restored = len([ln for ln in f["beats"][2]["output"].split("\n") if ln.strip().startswith("restore ")])
    repo, br = e(cfg["repo_url"]), e(cfg["branch"])
    items = [
        (len(agents.AGENTS), "coding agents with a hook", '<a href="%s/blob/%s/src/rewindagents/agents.py"><code>src/rewindagents/agents.py</code></a>' % (repo, br)),
        (test_function_count(), "test functions in the repository", '<code>def test_</code> in <a href="%s/tree/%s/tests"><code>tests/</code></a>' % (repo, br)),
        (len(PROOF), "claims on this page, each checked by a named test", 'the <a href="#tested">Tested</a> section'),
        (restored, "files back from one rewind, in the session above", "<code>brand/demo/manifest.json</code>"),
        (n_deps, "dependencies beyond the standard library", '<code>pyproject.toml</code>'),
    ]
    def slashes(src):        # a path breaks only after a slash on a phone
        return re.sub(r"<code>([^<]*)</code>", lambda m: "<code>%s</code>" % m.group(1).replace("/", "/<wbr>"), src)
    cells = "".join('<li><b class="cnt" data-to="%d">%d</b><span class="cnt-l">%s</span><span class="cnt-s">%s</span></li>'
                    % (v, v, e(lbl), slashes(src)) for v, lbl, src in items)
    return ('<ul class="counts" aria-labelledby="counts-note">%s</ul>'
            '<p class="small counts-note" id="counts-note">Counted from the repository when this page was built.</p>' % cells)


def split_comment(line):
    """A README sh line as (command, trailing `# comment` or None), the split code() makes."""
    m = re.match(r"^(.*?)(?:\s+(# .*))?$", line)
    return m.group(1), m.group(2)


def code(lines):
    """A README sh block as a terminal panel. A trailing `# comment` moves to its own line (the README aligns
    comments with spaces, which would force a wide block on a phone): before the command when it describes it,
    after the command when it offers an alternative command (`# or: ...`). `# or for every project` describes
    its own line, so it goes before it (UX audit F5: after it, it read as the caption of the next block).
    Words are untouched."""
    rows = []
    for line in lines:
        if not line.strip():
            continue
        body, comment = split_comment(line)
        if comment and comment.startswith("# or:"):
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
            "documented payloads. The Gemini CLI and Copilot CLI hooks were also verified in a live session on 2026-11-18 "
            "(Gemini CLI 0.68.0, Copilot CLI 1.0.114); both run a project&#x27;s hooks only in a folder you have trusted. "
            "The Droid and Qwen Code hooks are not yet in a live session. To install any of them:</p>\n%s" % code(block))


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
%(poster)s
<video class="film-video" controls preload="none" playsinline aria-label="The rewindagents film, %(len)s, with captions">
<source src="assets/%(name)s.mp4" type="video/mp4">
<track kind="captions" src="assets/%(name)s.vtt" srclang="en" label="English" default>
</video>
<button class="film-play" type="button" hidden><span class="film-play-dot" aria-hidden="true"><svg width="22" height="24" viewBox="0 0 22 24"><path d="M3 2l17 10L3 22z" fill="currentColor"/></svg></span><span class="film-play-label">Play the film</span><span class="film-len">%(len)s, with music</span></button>
</div>
<div class="wrap film-bar" hidden><div class="film-ruler" role="slider" tabindex="0" aria-label="Film position" aria-valuemin="0" aria-valuemax="%(totali)d" aria-valuenow="0"><span class="film-fill"></span>%(ticks)s</div><span class="film-time">0:00 / %(len)s</span><button class="film-fs" type="button" aria-label="Full screen">Full</button></div>
<p class="wrap film-now" aria-live="off"></p>
</div>""" % {"total": total, "totali": round(total), "len": length, "name": FILM, "ticks": ticks, "poster": film_poster()}


# The film's poster at phone-to-desktop sizes, written by brand/vsl/narration.py (POSTER_WIDTHS there). A lazy <picture>
# under the video instead of the video's poster attribute, which a browser fetches at once and at full size: on a phone
# the 122 KB JPEG competed with the first screen (Lighthouse mobile, GATE.md pass 3). width/height keep CLS at 0.
POSTER_WIDTHS = (480, 960, 1440, 1920)
POSTER_SIZES = "(min-width: 1600px) 1600px, 100vw"


def film_poster():
    def srcset(fmt):
        return ", ".join("assets/film-poster-%d.%s %dw" % (w, fmt, w) for w in POSTER_WIDTHS)
    return ('<picture class="film-poster"><source type="image/avif" srcset="%s" sizes="%s">'
            '<source type="image/webp" srcset="%s" sizes="%s">'
            '<img src="assets/film-poster.jpg" alt="" width="1920" height="1080" loading="lazy" decoding="async"></picture>'
            % (srcset("avif"), POSTER_SIZES, srcset("webp"), POSTER_SIZES))


def ruler(at, n=8, w=84, h=18, dark=False, live=False):
    """The brand motif as a small inline SVG: n short ticks on a rule, the playhead on tick `at` (1-based) in
    Record; ticks and rule after it in Rule grey (the rewound part). `dark` draws it for a Spool ground: Playhead
    before the playhead, Tape after it. Decorative: aria-hidden. `live` (the hero's panel head) also draws the tick
    under the playhead and writes the geometry as data, so site.js can move the playhead step by step during the
    replay without making SVG nodes; the still it draws is the same picture."""
    ink, after = (C["Playhead"], C["Tape"]) if dark else (C["Reel"], C["Rule"])
    pitch = (w - 4) / (n - 1)
    parts = []
    xs = [2 + i * pitch for i in range(n)]
    px = xs[at - 1]
    parts.append('<rect x="0" y="%d" width="%.1f" height="1" fill="%s"/>' % (h - 2, px, ink))
    parts.append('<rect x="%.1f" y="%d" width="%.1f" height="1" fill="%s"/>' % (px, h - 2, w - px, after))
    for i, x in enumerate(xs, 1):
        if i == at and not live:
            continue
        parts.append('<rect x="%.1f" y="%d" width="1" height="5" fill="%s"/>'
                     % (x - 0.5, h - 6, ink if i <= at else after))
    parts.append('<path d="M%.1f 1H%.1fV4L%.1f 6.5V%dH%.1fV6.5L%.1f 4Z" fill="%s"/>'
                 % (px - 3, px + 3, px + 1, h - 1, px - 1, px - 3, C["Record"]))
    data = (' data-at="%d" data-n="%d" data-x0="2" data-pitch="%g" data-ink="%s" data-after="%s"'
            % (at, n, pitch, ink, after)) if live else ""
    return ('<svg class="ruler%s" width="%d" height="%d" viewBox="0 0 %d %d" aria-hidden="true"%s>%s</svg>'
            % (" live" if live else "", w, h, w, h, data, "".join(parts)))


SECTIONS = 11   # numbered sections on the landing page; the label ruler has one tick per section (UX audit F12)


def label(n, text):
    return '<p class="label">%s<span class="n">%02d</span><span>%s</span></p>' % (ruler(n, n=SECTIONS), n, e(text))


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
<meta property="og:image" content="%(site)sassets/og-1200x630.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="%(og_alt)s">
<meta property="og:image" content="%(site)sassets/social-preview-1280x640.png">
<meta property="og:image:width" content="1280">
<meta property="og:image:height" content="640">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="%(site)sassets/og-1200x630.png">
<meta name="twitter:image:alt" content="%(og_alt)s">
<link rel="icon" href="%(rel)sassets/favicon.svg" type="image/svg+xml">
<link rel="icon" href="%(rel)sassets/favicon-32.png" sizes="32x32" type="image/png">
<link rel="preload" href="%(rel)sfonts/bricolage-grotesque-latin-800-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="%(rel)sfonts/hanken-grotesk-latin-400-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="%(rel)sfonts/hanken-grotesk-latin-600-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="%(rel)sfonts/commit-mono-latin-400-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="%(rel)ssite.min.css">
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
       "nav": nav, "body": body, "og_alt": e(OG_ALT), "credit": CREDIT, "licence": LICENCE, "repo": e(cfg["repo_url"]),
       "branch": e(cfg["branch"]), "ld": json.dumps(ld, sort_keys=True),
       "wm_w": svg_width("logo-wordmark.svg", 30), "wmr_w": svg_width("logo-wordmark-reverse.svg", 26)}


def svg_width(name, height):
    """Display width of a brand/ SVG at `height` px, from its viewBox, so a logo change never stretches it."""
    with open(os.path.join(BRAND, name), encoding="utf-8") as f:
        _, _, w, h = (float(v) for v in re.search(r'viewBox="([^"]+)"', f.read()).group(1).split())
    return round(w * height / h)


# ---- pages ------------------------------------------------------------------------------------------------
def plans(cfg, rel, h="h3"):
    """Both plan cards. `h` is the card heading level: h3 under the landing page's h2, h2 under the pricing
    page's h1, so the outline never skips a level (Lighthouse heading-order)."""
    has = [("has", "The recorder and hooks for %d coding agents: every tool call in a hash-chained log, every file saved before it changes" % len(agents.AGENTS)),
           ("has", "<code>fork</code> any recorded step and <code>compare</code> the runs, with your own <code>--check</code>"),
           ("has", "<code>replay</code>, <code>rewind</code> and <code>branch</code>, and <code>verify</code> against a pinned head"),
           ("has", "<code>export</code>: one session as one HTML page, with the diff each step made"),
           ("has", "<code>sessions</code>: every session in the log, and search by command or path"),
           ("has", "Runs on your machine. Standard library only. No account.")]
    items = lambda xs: "".join('<li class="%s"><span>%s</span></li>' % (k, t) for k, t in xs)  # noqa: E731
    if cfg.get("checkout_url"):
        buy, status = '<a class="btn btn-primary" href="%s">Buy Cloud</a>' % e(cfg["checkout_url"]), "Checkout is open."
    else:
        buy = '<a class="btn btn-ghost" href="%s">Join the waitlist</a>' % e(cfg["waitlist_url"])
        status = ("Hosted and opt-in, for teams; the local tool never needs it. Not for sale yet. No price has been set, so none is shown. If you want it, open the waitlist issue "
                  "on GitHub and say what you would pay for.")
    return ('<div class="plans">'
            '<section class="plan" aria-labelledby="plan-oss"><%(h)s id="plan-oss">Open source <span class="pill">%(lic)s</span></%(h)s>'
            '<div class="price">Free</div><p class="pricenote">Everything the tool does today.</p><ul>%(has)s</ul>'
            '<a class="btn btn-primary" href="%(rel)sindex.html#install">Install</a></section>'
            '<section class="plan" aria-labelledby="plan-cloud"><%(h)s id="plan-cloud">Cloud <span class="pill pill-planned">planned</span></%(h)s>'
            '<div class="price">Not yet priced</div><p class="pricenote">%(status)s</p><ul>%(planned)s</ul>%(buy)s</section></div>'
            % {"h": h, "lic": LICENCE, "has": items(has), "rel": rel, "status": e(status),
               "planned": items([("planned", e(t)) for _, t in PLANNED]), "buy": buy})


def faq_html(items, open_all=False):
    return '<div class="faq">%s</div>' % "".join(
        '<details%s><summary>%s</summary><p>%s</p></details>' % (" open" if open_all else "", e(q), a) for q, a in items)


def hero_install(b):
    """The first screen's install block (UX audit F1): the README's install line with its `# or:` alternative,
    then the README's hook line with its comment, in the rows code() would make. Words are the README's."""
    pipx, alt = split_comment(b["install"][0])
    hook_cmd, hook_c = split_comment(b["hook"][1])
    if not (alt and alt.startswith("# or:") and hook_cmd == "rewindagents install" and hook_c):
        raise SystemExit("README install/hook blocks changed shape: update hero_install()")
    return panel([("cmd", pipx), ("c", alt), ("c", hook_c), ("cmd", hook_cmd)], "install")


# Claims the landing page makes, each with the tests that check it (UX audit F4). Names are checked against
# tests/ at build time, so a renamed or deleted test stops the build instead of leaving a dead citation.
PROOF = [
    ("Every line in the fork and compare panels is what <code>ux-review/try-runs.sh</code> printed.",
     [("test_runs_demo.py", "test_every_quoted_line_is_what_the_script_prints")]),
    ("<code>fork</code> rebuilds the step&#x27;s files and leaves the project, its <code>HEAD</code> and index alone.",
     [("test_runs.py", "test_fork_holds_the_files_as_they_were_right_after_the_step_and_leaves_the_project_alone")]),
    ("An agent in the run records into the run&#x27;s own log, not the project&#x27;s.",
     [("test_runs.py", "test_an_agent_in_the_run_records_into_the_run_not_into_the_project")]),
    ("<code>compare --check</code> runs your command in each run and reports its exit code.",
     [("test_runs.py", "test_check_runs_in_each_run_and_reports_its_exit_code")]),
    ("<code>compare --diff</code> is a diff <code>git apply</code> takes: the first run&#x27;s files become the second&#x27;s.",
     [("test_runs.py", "test_diff_between_two_runs_applies_with_git")]),
    ("A tampered log or a step that cannot be rebuilt exactly is refused, and nothing is left behind.",
     [("test_runs.py", "test_a_tampered_log_is_refused"), ("test_runs.py", "test_a_step_that_cannot_be_rebuilt_exactly_is_refused"),
      ("test_runs.py", "test_refusals_leave_nothing_behind")]),
    ("Every terminal line on this page and in the clip is what the CLI printed.",
     [("test_demo.py", "test_every_shown_command_replays_exactly"),
      ("test_demo.py", "test_installed_binary_prints_the_rewind_the_clip_shows")]),
    ("Editing, deleting or reordering a record makes <code>verify</code> fail.",
     [("test_log.py", "test_edited_args_detected"), ("test_log.py", "test_deleted_middle_record_detected"),
      ("test_log.py", "test_reordered_records_detected")]),
    ("Records cut off the end are caught only against a pinned head.",
     [("test_log.py", "test_truncated_tail_caught_only_with_pinned_head")]),
    ("<code>rewind</code> refuses a tampered log and changes nothing.",
     [("test_rewind.py", "test_tampered_log_is_refused_and_nothing_changes")]),
    ("A rewind can itself be rewound.",
     [("test_rewind.py", "test_rewind_can_itself_be_rewound")]),
    ("A real <code>sed</code> and <code>rm</code>, run through the installed command, are put back.",
     [("test_bashscan.py", "test_real_sed_and_rm_undone_through_the_installed_command_path")]),
    ("The hook prints nothing and exits 0, even on garbage input or a store it cannot write.",
     [("test_hook.py", "test_garbage_input_exits_zero_silently"), ("test_hook.py", "test_unwritable_store_exits_zero")]),
    ("<code>branch</code> keeps the current files without touching <code>HEAD</code> or the index.",
     [("test_rewind.py", "test_git_branch_keeps_the_current_files_without_touching_head_or_index")]),
    ("A file outside the project is never touched.",
     [("test_rewind.py", "test_file_outside_the_project_is_never_touched")]),
]


def proof_rows(cfg):
    rows = []
    for claim, tests in PROOF:
        cites = []
        for fname, test in tests:
            if not re.search(r"^\s*def %s\(" % re.escape(test), read("tests", fname), re.M):
                raise SystemExit("PROOF names tests/%s::%s, which does not exist" % (fname, test))
            cites.append('<a href="%s/blob/%s/tests/%s"><span class="f">tests/%s</span> %s</a>'
                         % (e(cfg["repo_url"]), e(cfg["branch"]), fname, fname, e(test).replace("_", "_<wbr>")))
        rows.append('<li><span class="claim">%s</span><span class="cites">%s</span></li>' % (claim, "".join(cites)))
    return "".join(rows)


# The gap a Claude Code user asks about first (2026-11-18): the README's comparison table, its first two rows (the
# third names the other agents, which the strip under the hero already shows), with the README's own words around it.
# Every phrase below is checked against README.md at build time, so the section cannot say more than the README does.
GAP_LEDE = ("Claude Code&#x27;s own %s name the gap this fills.",
            "rewindagents copies the project's files before every shell command and scans them after, so a `sed -i` or an `rm` is one more step you can rewind")
GAP_NUANCE = "its `/rewind` does undo Bash changes to a file Claude had already edited"
GAP_READ = "(read 2026-11-12)"
GAP_LIVE = "A live session in which a subagent"


def md_cell(s):
    """A README table cell as HTML: escaped, `code` spans, [text](url) links."""
    s = md_inline(s)
    return re.sub(r"\[([^\]]+)\]\((https://[^)\s]+)\)", r'<a href="\2">\1</a>', s)


def readme_table(readme, first_header):
    """The README's markdown table whose first header cell is `first_header`: (header cells, rows of cells)."""
    m = re.search(r"^\| %s \|.*?(?=^\s*$)" % re.escape(first_header), readme, re.S | re.M)
    if not m:
        raise SystemExit("README has no table starting %r" % first_header)
    lines = [ln.strip() for ln in m.group(0).strip().split("\n")]
    cells = [[c.strip() for c in ln.strip("|").split(" | ")] for ln in lines if not re.match(r"^\|[-| ]+\|$", ln)]
    return cells[0], cells[1:]


def gap_html(cfg, f):
    readme = read("README.md")
    flat = " ".join(readme.split())
    for phrase in (GAP_LEDE[1], GAP_NUANCE, GAP_READ, "Claude Code's own [checkpointing docs]", "name the gap this fills"):
        if phrase not in flat:
            raise SystemExit("gap section: README no longer says %r" % phrase)
    head, rows = readme_table(readme, "After your agent...")
    if len(head) != 3 or len(rows) < 2 or "shell command" not in rows[0][0] or "subagent" not in rows[1][0]:
        raise SystemExit("README comparison table changed shape: update gap_html()")
    docs = re.search(r"\[checkpointing docs\]\((https://[^)]+)\)", readme).group(1)
    replay = f["beats"][0]
    wreck = [ln for i, ln in enumerate(replay["output"].rstrip("\n").split("\n")) if i in replay["accent_rows"]]
    rm_line = next(ln for ln in wreck if "rm -rf" in ln)
    step = int(rm_line.split()[0])
    proof = ['<span class="gap-ev"><span class="gap-src">step %d of the session above, as replay printed it</span>'
             '<code class="gap-line">%s</code></span>' % (step, re.sub(r"(\[\d+ checkpointed\])", r'<span class="hit">\1</span>', e(rm_line.strip()))),
             '<span class="gap-ev">%s</span>' % md_inline(readme_sentence(readme, GAP_LIVE)).replace(
                 "<code>ux-review/DOGFOOD.md</code>",
                 '<a href="%s/blob/%s/ux-review/DOGFOOD.md"><code>ux-review/DOGFOOD.md</code></a>' % (e(cfg["repo_url"]), e(cfg["branch"])))]

    def said(cell):
        """'"quoted words" ([docs](url))' as the quote and its source link, the quote marks left to <q>."""
        m = re.match(r'^"([^"]+)" \(\[docs\]\((https://[^)]+)\)\)$', cell)
        if not m:
            raise SystemExit("README comparison cell changed shape: %r" % cell)
        return '<q>%s</q> <a class="gap-doc" href="%s">docs</a>' % (e(m.group(1)), e(m.group(2)))
    body = "".join(
        '<li><span class="gap-l"><span class="gap-when">%s</span>'
        '<span class="gap-cc"><span class="gap-k">%s</span>%s</span></span>'
        '<span class="gap-ra"><span class="gap-k">%s</span><b>%s</b>%s</span></li>'
        % (md_cell(r[0]), e(head[1]), said(r[1]), e(head[2]), md_cell(r[2]), proof[i])
        for i, r in enumerate(rows[:2]))
    return """
<section class="sec" id="gap" aria-labelledby="h-gap"><div class="wrap">
%(label)s
<div class="head"><h2 id="h-gap">What Claude Code&#x27;s checkpoints miss.</h2>
<p class="lede">%(lede0)s %(lede1)s.</p></div>
<div class="gap-grid">
<div class="gap-cols" aria-hidden="true"><span class="gap-l"><span>%(h0)s</span><span>%(h1)s</span></span><span>%(h2)s</span></div>
<ul class="gap">%(rows)s</ul>
</div>
<p class="small gap-note">Quotes from Claude Code&#x27;s <a href="%(docs)s">checkpointing docs</a> %(read)s. One exception they name: %(nuance)s.</p>
</div></section>
""" % {"label": label(1, "The gap"), "lede0": GAP_LEDE[0] % ('<a href="%s">checkpointing docs</a>' % e(docs)),
       "lede1": md_inline(GAP_LEDE[1]), "h0": e(head[0]), "h1": e(head[1]), "h2": e(head[2]), "rows": body,
       "docs": e(docs), "read": e(GAP_READ), "nuance": md_inline(GAP_NUANCE)}


def course_h1():
    """The headline as three line spans (one space between them, so its text is COURSE exactly)."""
    if " ".join(COURSE_LINES) != COURSE:
        raise SystemExit("COURSE_LINES do not join to COURSE")
    return " ".join('<span class="h1l">%s</span>' % e(ln).replace("rm -rf", '<span class="nw">rm -rf</span>') for ln in COURSE_LINES)


def index_html(cfg, f, hero, open_all=False):
    rel = ""
    b = f["blocks"]
    n, good = f["steps"], f["good_step"]
    desc = ("Undo for AI coding agents, including what they do in the shell: rm -rf, sed -i, a script. rewindagents saves "
            "each file before every step and takes back the whole session, one step or one file. Open source, local, "
            "standard library only. Hooks for Claude Code, Codex, Cursor, Gemini CLI, Copilot CLI, Droid and Qwen Code.")
    runs = f["runs"]
    hero_s = """
<section class="hero" aria-labelledby="h1"><div class="wrap">
<p class="eyebrow"><b>v%(v)s</b> %(eyebrow)s</p>
<h1 id="h1">%(course_h1)s</h1>
<div class="hero-install">
<p class="small"><b>Install.</b> From PyPI; then add the hook in a project. One click on a command selects all of it, without the prompt.</p>
%(install)s
</div>
<div class="hero-row">
<p class="lede">rewindagents records every step your coding agent takes and saves each file before it changes, including files only a shell command touched. When a run goes wrong, take back the whole session, one step, or one file.</p>
<p class="lede base">Then fork any recorded step, let another agent continue from there, and compare the runs, within the <a href="#limits">limits</a>.</p>
<div class="cta"><a class="btn btn-primary" href="#install">Install</a><a class="btn btn-ghost" href="%(repo)s">Source on GitHub</a></div>
<ul class="facts"><li>standard library only</li><li>no network, no account</li><li>never stops or changes a call</li><li>%(licence)s</li></ul>
</div>
</div>
%(stage)s
<div class="wrap">%(counts)s
%(agents)s</div>
</section>
""" % {"v": e(f["version"]), "eyebrow": e(eyebrow(f)), "licence": LICENCE, "course_h1": course_h1(),
       "repo": e(cfg["repo_url"]), "install": hero_install(b), "agents": agent_strip(), "stage": stage_html(f),
       "counts": counters(cfg, f)}

    fork = """
<section class="sec" id="fork" aria-labelledby="h-fork"><div class="wrap">
%(label)s
<div class="head"><h2 id="h-fork">Rewind to a step, fork it, compare.</h2>
<p class="lede">%(lead)s %(says0)s</p></div>
<div class="cmdlist">
<div class="cmdrow"><div><h3>Fork any recorded step</h3><p>%(fork_says)s</p></div>%(block)s</div>
<div class="cmdrow"><div><h3>A session, and a second try from step 2</h3><p>What <code>ux-review/try-runs.sh</code> printed against an installed build, unedited; lines naming its temporary folder are left out. <code>shop</code> is the agent&#x27;s run, recorded through the real hook; <code>clamp</code> is a second attempt made by hand in the fork.</p></div>%(runs)s</div>
<div class="cmdrow"><div><h3>Compare the runs</h3><p>%(compare_says)s</p></div>%(diff)s</div>
<div class="cmdrow"><div><h3>What it will not do</h3></div><ul class="plain-list">%(limits)s</ul></div>
</div>
<p class="small more">Every option, and how a fork works in a git repository, is on the <a href="docs/#fork">docs page</a>.</p>
</div></section>
""" % {"label": label(3, "Fork and compare"), "lead": md_inline(f["fork_lead"]), "says0": md_inline(f["fork_says"][0]),
       "fork_says": " ".join(md_inline(x) for x in FORK_SHORT),
       "compare_says": " ".join(md_inline(x) for x in COMPARE_SHORT),
       "limits": "".join("<li>%s</li>" % md_inline(x) for x in f["fork_limits"]),
       "block": code(f["fork"]), "runs": panel(runs_rows(runs, "hero")), "diff": panel(runs_rows(runs, "diff"))}

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
""" % {"film": film(srt_cues("brand/vsl/%s.srt" % FILM)), "label": label(2, "Undo"), "n": n, "good": good, "s13": n - 1, "s14": n, "gw": f["gif"]["width"],
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
""" % {"label": label(4, "The timeline"), "quick": code(b["quick"][:1]), "ui": code(b["ui"][:1]),
       "precise": code([ln for ln in f["quick_use"] if ln.lstrip().startswith(("rewindagents diff", "rewindagents rewind"))])}

    install = """
<section class="sec" id="install" aria-labelledby="h-install"><div class="wrap">
%(label)s
<div class="head"><h2 id="h-install">Install, then add the hook to a project.</h2>
<p class="lede">Python %(py)s. No dependencies beyond the standard library. Tested on %(tested)s. Install it from PyPI. The <a href="docs/">docs</a> walk through a first session.</p></div>
<div class="install-row"><div><h3>Get the command</h3><p><code>pipx</code> installs it from PyPI, as in the panel. From a clone, <code>pip install .</code> works too; without installing, <code>PYTHONPATH=src python3 -m rewindagents</code> runs the same CLI.</p></div>%(install)s</div>
<div class="install-row"><div><h3>Or with Homebrew, npm, or as a Claude Code plugin</h3><p>The same CLI from another package manager, or the plugin that brings the hook, the MCP server and the slash commands into Claude Code. %(editors)s</p></div>%(channels)s</div>
<div class="pair"><div><h3>Add the Claude Code hook</h3>%(hook)s</div><div><h3>Codex and Cursor hooks</h3>%(agents)s</div></div>
<div class="pair-note"><p><code>install</code> keeps everything already in the file and does nothing if the hook is already there. For Codex the file is <code>%(codex)s</code> and for Cursor <code>%(cursor)s</code>; those two hooks are tested with the payloads in the vendors&#x27; documentation and were verified in a live session on 2026-11-18. <code>.rewindagents/</code> gets its own <code>.gitignore</code>, so the log and the copies stay out of your commits.</p></div>
</div></section>
""" % {"label": label(5, "Install"), "py": e(f["py_req"]), "tested": e(f["tested_on"]), "install": code(b["install"]), "hook": code(b["hook"]),
       "channels": code(f["channels"]), "editors": md_inline(f["editors"]),
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
""" % {"label": label(6, "How it works"), "r1": ruler(2, n=5, w=60, h=16), "r2": ruler(3, n=5, w=60, h=16), "r3": ruler(4, n=5, w=60, h=16)}

    tested = """
<section class="sec" id="tested" aria-labelledby="h-tested"><div class="wrap">
%(label)s
<div class="head"><h2 id="h-tested">The claims on this page are tests.</h2>
<p class="lede">Each row is a claim made above and the test in the repository that checks it. The site build stops if a test named here no longer exists.</p></div>
<ul class="ledger proof">%(rows)s</ul>
<div class="cmdrow plain"><p class="small">Run every test from a clone, with the README&#x27;s command. The <a href="docs/#tests">docs</a> say which tests need the installed command.</p>%(run)s</div>
</div></section>
""" % {"label": label(7, "Tested"), "rows": proof_rows(cfg), "run": code(b["tests"])}

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
""" % {"label": label(8, "Limits"), "chars": "{:,}".format(f["result_chars"]), "mb": f["file_mb"],
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
""" % {"label": label(9, "Commands"), "replay": code(b["replay"]), "export": code(b["export"]), "sessions": code(b["sessions"]),
       "verify": code(b["verify"]), "kb": f["diff_kb"], "lines": f["diff_lines"]}

    pricing = """
<section class="sec" id="pricing" aria-labelledby="h-pricing"><div class="wrap">
%(label)s
<div class="head"><h2 id="h-pricing">The tool is free. Cloud is planned.</h2>
<p class="lede">Everything that exists is open source under %(licence)s. A paid tier may come later; nothing is sold before it exists.</p></div>
%(plans)s
<p class="small more">Details on the <a href="pricing.html">pricing page</a>.</p>
</div></section>
""" % {"label": label(10, "Pricing"), "licence": LICENCE, "plans": plans(cfg, rel)}

    faq_items = [
        ("Does it stop or change what the agent does?",
         "No. The hook records and checkpoints, then exits 0. It has no opinion about any call. The agent runs exactly as it would without the hook; the difference is that afterwards every step is on record and every file change can be put back."),
        ("Does anything leave my machine?",
         "No. rewindagents makes no outbound network connections: a test checks that no module under <code>src/</code> imports <code>socket</code>, <code>http</code> or <code>urllib</code>, except the timeline UI, which serves <code>rewindagents ui</code> on 127.0.0.1 only and checks a one-time token on every request. The log and the file copies live in <code>.rewindagents/</code> inside your project, and nothing reads them but you."),
        ("Which agents does it work with?",
         "Claude Code, through its <code>PreToolUse</code> and <code>PostToolUse</code> hooks; Codex, through the same hook file shape in <code>%s</code>; Cursor, through <code>%s</code>; and Gemini CLI, Copilot CLI, Droid and Qwen Code, each through its own project hook file (the docs page names them). The Claude Code, Codex and Cursor hooks were verified in a live session on 2026-11-18, and so were the Gemini CLI and Copilot CLI hooks. The Codex and Cursor hooks are also tested with the payloads in the vendors&#x27; hook documentation. The Droid and Qwen Code hooks are tested with the documented payloads, not yet in a live session; the README says the same." % (f["agents"]["codex"]["settings"], f["agents"]["cursor"]["settings"])),
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
""" % {"label": label(11, "Questions"), "items": faq_html(faq_items, open_all)}

    closing = """
<section class="sec close" aria-labelledby="h-close"><div class="wrap">
<div class="closegrid"><div><h2 id="h-close">Install it, add the hook, carry on.</h2>
<div class="cta"><a class="btn btn-primary" href="#install">Install</a><a class="btn btn-ghost" href="docs/">Read the docs</a></div></div>
%(install)s</div>
</div></section>
""" % {"install": code(b["install"][:1])}

    body = hero_s + gap_html(cfg, f) + demo + fork + timeline + install + how + tested + limits + commands + pricing + faq + closing
    return page(cfg, "index.html", "%s: %s" % (NAME, COURSE.rstrip(".")), desc, body, "home")


def pricing_html(cfg, f):
    rel = ""
    desc = ("rewindagents is free under %s, fork and compare included. A hosted Cloud tier for teams is planned and not yet "
            "priced; the waitlist is a GitHub issue." % LICENCE)
    items = [
        ("Will the open-source tool stay free?",
         "The code you have is %s, and that licence cannot be withdrawn from it. Nothing that exists today is behind a paywall: the recorder, the hooks, replay, rewind, branch, fork, compare, export and sessions are all in the open-source tier, and what an individual developer needs stays there." % LICENCE),
        ("What would Cloud add?",
         "Things that need a service rather than a command, for a team: a shared page per comparison you can link from a pull request, saved starting points run in parallel sandboxes instead of on a laptop, a history of which agent, model or prompt did best on which kind of task, and re-runs when a model or prompt changes. It is opt-in: the local tool never needs it and still makes no network connection. None of it is built yet. <code>fork</code> and <code>compare</code> are the local halves and are free."),
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
""" % {"label": label(1, "Pricing"), "plans": plans(cfg, rel, h="h2"), "label2": label(2, "Questions about paying"),
       "faq": faq_html(items, open_all=True)}
    return page(cfg, "pricing.html", "Pricing: %s" % NAME, desc, body, "pricing")


def docs_html(cfg, f):
    rel = "../"
    b = f["blocks"]
    desc = "Getting started with rewindagents: install, add the hook to Claude Code, Codex or Cursor, a first session, replay, rewind, branch, fork a step and compare the runs, export, find a session, verify the log."
    toc = [("install", "Install"), ("hook", "Add the hook"), ("after", "After a bad run"), ("first", "A first session"), ("recorded", "What gets recorded"),
           ("replay", "Replay and rewind"), ("branch", "Branch"), ("fork", "Fork and compare"), ("ui", "Timeline in a browser"), ("mcp", "MCP server"), ("export", "Export"),
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
<p>Python %(py)s, standard library only. Tested on %(tested)s. Install it from PyPI:</p>
%(install)s
<p>The last command prints the version it installed:</p>
%(version)s
<p>Or from a clone, <code>pip install .</code>. Without installing, <code>PYTHONPATH=src python3 -m rewindagents</code> runs the same CLI from a clone; then the undo hint says <code>python3 -m rewindagents</code> instead of <code>rewindagents</code>.</p>
<p>Other ways to install the same CLI, and the plugin for Claude Code:</p>
%(channels)s
<p>%(editors)s</p>

<h2 id="hook">Add the hook</h2>
%(init)s
<p>%(init_says)s</p>
<p>Or add it to one agent at a time:</p>
%(hook)s
<p><code>install</code> adds a <code>PreToolUse</code>, a <code>PostToolUse</code> and a <code>PostToolUseFailure</code> hook (a command that fails is checkpointed too) to the settings file, keeps everything already in it, and does nothing if the hook is already there. The command it writes names the Python that rewindagents was installed into by absolute path, so it runs whether or not a virtualenv is active. To remove the hook, run <code>rewindagents uninstall</code> (see <a href="#remove">Remove it</a>).</p>
%(agents)s
<p>For Codex the file is <code>%(codex)s</code>, in the same shape as Claude Code&#x27;s settings; Codex runs a project hook only after you review it once (<code>/hooks</code>), remembers that by the hook&#x27;s hash, and loads a project&#x27;s config only in a trusted project. For Cursor the file is <code>%(cursor)s</code> with a <code>preToolUse</code> and a <code>postToolUse</code> entry; because Cursor&#x27;s <code>preToolUse</code> is a permission hook that treats an empty answer as a failure, the hook prints <code>{"permission": "allow"}</code> before a call and <code>{}</code> after one, which changes nothing (a deny from another hook still wins). The Codex and Cursor hooks are tested with the payloads in the vendors&#x27; documentation and through the installed command, and were verified in a live session on 2026-11-18 (Codex 0.170.0, Cursor 2026.11.17-f532c45).</p>
%(more_agents)s
<p>Then use your agent as usual and:</p>
%(quick_use)s

<h2 id="after">After a bad run</h2>
%(rescue)s
<p>%(rescue_says)s</p>

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

<h2 id="fork">Fork and compare</h2>
%(fork)s
<p>%(fork_says)s</p>
<p>%(compare_says)s</p>
<p>From <code>ux-review/try-runs.sh</code>, against an installed build: the agent&#x27;s run <code>shop</code> fails the check, a second attempt <code>clamp</code> made in the fork passes, and this is how the two differ.</p>
%(runs)s
%(diff)s
<ul>%(fork_limits)s</ul>

<h2 id="ui">Timeline in a browser</h2>
%(ui)s
<p>%(ui_says)s</p>

<h2 id="mcp">MCP server</h2>
%(mcp)s
<p>%(mcp_says)s</p>

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
<li>In a git repository the scan follows <code>git ls-files --cached --others --exclude-standard</code>, plus the files git ignores one by one (<code>.env</code>, <code>*.log</code>), so a <code>rm .env</code> can be rewound; directories git ignores as a whole (<code>node_modules/</code>, <code>build/</code>) are not saved. Outside git, every file under the project except under %(skip)s.</li>
<li>Symlinks are not saved. File permissions are: a deleted script comes back executable. Files over %(mb)d MB are not copied. A project with more than %(files)s files is not scanned around <code>Bash</code> commands; the call is still recorded and <code>rewind</code> reports the step as not scanned.</li>
<li>Directories created by later steps stay, empty, after a rewind. If anything could not be restored, <code>rewind</code> lists it and exits 1.</li>
<li>Windows: the full test suite passes on Windows CI (windows-latest), but the hooks have been verified in live sessions on macOS only, not yet on Windows, and hook commands under PowerShell are untested. On Windows a patch from <code>diff</code> saved with <code>&gt;</code> gets CRLF line endings and will not <code>git apply</code>. The Claude Code, Codex, Cursor, Gemini CLI and Copilot CLI hooks were verified in a live session on 2026-11-18; the Droid and Qwen Code hooks are tested with the documented payloads, not yet in a live session.</li>
</ul>

<h2 id="remove">Remove it</h2>
%(uninstall)s
<p><code>rewindagents init --undo</code> removes the hook from every agent <code>init</code> set up, deletes a config file that held nothing else, and keeps what was recorded. <code>uninstall</code> removes only the hook entries <code>install</code> wrote, so every other hook and setting stays, and it never touches <code>.rewindagents/</code>: recorded sessions can still be replayed and rewound. To remove everything, also delete <code>.rewindagents/</code> in the project and uninstall the package (<code>pipx uninstall rewindagents</code> or <code>pip uninstall rewindagents</code>). Nothing else was created.</p>

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
       "fork": code(f["fork"]), "fork_says": " ".join(md_inline(x) for x in [f["fork_lead"]] + f["fork_says"]),
       "compare_says": " ".join(md_inline(x) for x in f["compare_says"]),
       "fork_limits": "".join("<li>%s</li>" % md_inline(x) for x in f["fork_limits"]),
       "runs": panel(runs_rows(f["runs"], "hero")), "diff": panel(runs_rows(f["runs"], "diff")),
       "ui": code(b["ui"]), "ui_says": " ".join(md_inline(s) for s in f["ui_says"]),
       "channels": code(f["channels"]), "editors": md_inline(f["editors"]),
       "mcp": code(b["mcp"]), "mcp_says": " ".join(md_inline(s) for s in f["mcp_says"]),
       "attach": code(f["attach"]), "attach_says": " ".join(md_inline(s) for s in f["attach_says"]),
       "attach_yaml": plain(f["attach_yaml"]), "action_says": " ".join(md_inline(s) for s in f["action_says"]),
       "codex": e(f["agents"]["codex"]["settings"]),
       "cursor": e(f["agents"]["cursor"]["settings"]),
       "more_agents": more_agents_html(f["more_agents"]),
       "init": code(b["quick"]), "init_says": " ".join(md_inline(s) for s in f["init_says"]),
       "quick_use": code(f["quick_use"]), "rescue": code(f["rescue"]),
       "rescue_says": " ".join(md_inline(s) for s in f["rescue_says"]),
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


def min_css(src):
    """site.css without comments and spare whitespace; the pages link this copy (13 KB fewer bytes before a phone's
    first screen). Quoted strings are kept exactly as written."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    parts = re.split(r'("(?:[^"\\\n]|\\.)*")', src)
    for i in range(0, len(parts), 2):
        p = re.sub(r"\s+", " ", parts[i])
        parts[i] = re.sub(r"\s*([{};,>])\s*", r"\1", p)
    return "".join(parts).strip() + "\n"


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
    for name in SITE_ASSETS:
        shutil.copyfile(os.path.join(HERE, "og", name), os.path.join(assets, name))
    with open(os.path.join(out, "site.min.css"), "w", encoding="utf-8") as fh:
        fh.write(min_css(read("brand", "site", "site.css")))
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
    for w in POSTER_WIDTHS:
        for fmt in ("avif", "webp"):
            shutil.copyfile(os.path.join(BRAND, "vsl", "%s-poster-%d.%s" % (FILM, w, fmt)),
                            os.path.join(assets, "film-poster-%d.%s" % (w, fmt)))
    with open(os.path.join(assets, FILM + ".vtt"), "w", encoding="utf-8") as fh:
        fh.write(vtt(srt_cues("brand/vsl/%s.srt" % FILM)))
    manifest = {"pages": sorted(p for p in pages if p in PAGES), "facts": {k: v for k, v in f.items() if k != "beats"},
                "hero": [list(r) for r in runs_rows(f["runs"], "hero")], "rewind_rows": [list(r) for r in hero],
                "assets": ASSETS + SITE_ASSETS, "credit": CREDIT, "promise": PROMISE, "course": COURSE,
                "planned": [p for p, _ in PLANNED], "site_url_key": "site_url", "checkout": bool(cfg.get("checkout_url"))}
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1, sort_keys=True)
        fh.write("\n")
    return pages


CARD_CSS = """
html, body { margin: 0; background: var(--leader); }
.card { box-sizing: border-box; overflow: hidden; background: var(--leader); color: var(--reel); position: relative; }
.card .mark { height: 34px; width: auto; align-self: flex-start; }
.card h1 { font-family: var(--display); font-weight: 800; letter-spacing: -0.03em; line-height: 1.02; margin: 0; text-wrap: balance; }
.card .sub { font-family: var(--body); color: var(--tape); margin: 0; max-width: none; text-wrap: balance; }
.card .meta { font-family: var(--mono); color: var(--tape); letter-spacing: 0.04em; margin: 0; max-width: none; }
.card .meta b { color: var(--reel); }
.card .panel-head { font-size: inherit; }
.card pre.term { font-size: inherit; padding: 18px 20px; }
.card pre.term .l { white-space: pre; padding-left: 0; text-indent: 0; }
.card .host { font-family: var(--mono); font-weight: 700; color: var(--reel); }
.card .credit { font-family: var(--mono); color: var(--reel); }
.wide { width: %(w)dpx; height: %(h)dpx; padding: 52px 60px 50px; display: grid; grid-template-columns: 410px minmax(0, 1fr); gap: 0 44px; align-items: center; }
.wide .left { display: flex; flex-direction: column; height: 100%%; justify-content: space-between; }
.wide h1 { font-size: 50px; margin-top: 28px; }
.wide .sub { font-size: 18px; line-height: 1.45; margin-top: 16px; }
.wide .meta { font-size: 14px; line-height: 1.65; }
.wide .panel { font-size: 12.6px; }
.tall { width: 1080px; height: 1350px; padding: 76px 72px 72px; display: flex; flex-direction: column; gap: 40px; }
.tall h1 { font-size: 88px; max-width: 12ch; }
.tall .sub { font-size: 27px; line-height: 1.4; margin-top: -12px; }
.tall .panel { font-size: 17.5px; }
.tall .meta { font-size: 19px; line-height: 1.6; }
.tall .install { font-size: 17px; }
.tall .foot2 { margin-top: auto; display: flex; justify-content: space-between; align-items: end; gap: 24px; }
"""


def cards(out):
    """Share images as HTML pages built from this site's CSS and the real runs (UX audit F5; course 2026-11-13):
    og (1200x630), linkedin (1200x627) and portrait (1080x1350). ux-review/tools/cards.mjs screenshots them; the og
    PNG is committed as brand/site/og/og-1200x630.png. The text is the page's own: the course line, the README
    install line, and lines from brand/demo/runs.json, which tests/test_runs_demo.py checks against a fresh run of
    ux-review/try-runs.sh. Every card carries the credit line. No full-bleed strip at the edge: the ruler is the
    one in the panel head (a strip there cropped to a stray tick on LinkedIn's 627 px)."""
    cfg, f = config(), facts()
    os.makedirs(out, exist_ok=True)
    shutil.copyfile(os.path.join(HERE, "site.css"), os.path.join(out, "site.css"))
    shutil.copytree(os.path.join(HERE, "fonts"), os.path.join(out, "fonts"), dirs_exist_ok=True)
    shutil.copyfile(os.path.join(BRAND, "logo-wordmark.svg"), os.path.join(out, "logo-wordmark.svg"))
    # launch headline (John, 2026-11-18): the cards show the wrecked-repo rewind, the same panel as the page's hero
    rows = hero_rows(f["beats"])
    replay = f["beats"][0]
    wreck = {ln for i, ln in enumerate(replay["output"].rstrip("\n").split("\n")) if i in replay["accent_rows"]}
    struck = {i for i, (k, t) in enumerate(rows) if k == "out" and t in wreck}
    n, good = f["steps"], f["good_step"]
    host = cfg["site_url"].split("//", 1)[1].rstrip("/")
    head = ('<div class="panel-head"><span>a session of %d steps; the last %d wrecked the repo</span>'
            '<span class="tl">%s<span>rewind %d</span></span></div>'
            % (n, f["wreck_steps"], ruler(good, n=n, w=4 + 6 * (n - 1), h=16, dark=True), good))
    short = rows
    pipx, _ = split_comment(f["blocks"]["install"][0])
    # no version on share cards (John, 2026-11-18): an uploaded social preview must not go stale with each release
    meta = '<b>open source</b>, %s<br>%s' % (e(LICENCE), e(eyebrow(f)))
    sub = "Undo for AI coding agents, including what they do in the shell. Seven agents, local, open source."
    h1 = e(COURSE).replace("rm -rf", '<span class="nw">rm -rf</span>')
    def doc(body, w, h):
        return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><link rel="stylesheet" href="site.css">'
                '<style>%s</style></head><body>%s</body></html>' % (CARD_CSS % {"w": w, "h": h}, body))
    for name, (w, h) in {"og": (1200, 630), "linkedin": (1200, 627)}.items():
        body = ('<div class="card wide"><div class="left"><img class="mark" src="logo-wordmark.svg" alt="">'
                '<div><h1>%s</h1><p class="sub">%s</p></div>'
                '<p class="meta">%s<br><span class="host">%s</span> &middot; <span class="credit">%s</span></p></div>'
                '<div class="panel">%s%s</div></div>'
                % (h1, e(sub), meta, e(host), e(CREDIT), head, panel(short, struck=struck)))
        with open(os.path.join(out, name + ".html"), "w", encoding="utf-8") as fh:
            fh.write(doc(body, w, h))
    body = ('<div class="card tall"><img class="mark" src="logo-wordmark.svg" alt="" style="height:44px">'
            '<h1>%s</h1><p class="sub">%s</p><div class="panel">%s%s</div>'
            '<div class="install">%s</div>'
            '<div class="foot2"><p class="meta">%s</p><p class="meta" style="text-align:right">'
            '<span class="host" style="font-size:24px">%s</span><br><span class="credit">%s</span></p></div></div>'
            % (h1, e(sub), head, panel(short, struck=struck), panel([("cmd", pipx)]), meta, e(host), e(CREDIT)))
    with open(os.path.join(out, "portrait.html"), "w", encoding="utf-8") as fh:
        fh.write(doc(body, 1080, 1350))
    return ["og.html", "linkedin.html", "portrait.html"]


# @fontsource/commit-mono's "latin" files hold the whole font (1,175 code points, Cyrillic and Greek included, 48 KB
# each); the other two families' latin files hold fontsource's latin range. `fonts` cuts Commit Mono to that same range
# with every OpenType feature kept, so Latin text renders the same at 21 KB a weight (a phone fetched 54 KB less before
# its first screen: GATE.md pass 4). Needs fontTools (`pip install fonttools brotli`), like the npm cache, by hand.
LATIN = ("U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,"
         "U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD")
SUBSET = {"commit-mono"}
FONT_MAX_BYTES = 25000


def fonts(cache=os.path.join(ROOT, ".brandcache")):
    """Copy the WOFF2 files the CSS declares, plus each family's OFL licence, into brand/site/fonts/; families in
    SUBSET are cut to LATIN (OFL 1.1 allows a subset; the font keeps its name, no Reserved Font Name is declared)."""
    out = os.path.join(HERE, "fonts")
    os.makedirs(out, exist_ok=True)
    for pkg, weights in FONTS.items():
        src = os.path.join(cache, "node_modules", "@fontsource", pkg)
        with open(os.path.join(src, "LICENSE"), encoding="utf-8") as fh:
            assert "SIL OPEN FONT LICENSE" in fh.read().upper(), pkg
        shutil.copyfile(os.path.join(src, "LICENSE"), os.path.join(out, "LICENSE-%s.txt" % pkg))
        for w in weights:
            name = "%s-latin-%d-normal.woff2" % (pkg, w)
            if pkg in SUBSET:
                subprocess.run(["pyftsubset", os.path.join(src, "files", name), "--unicodes=" + LATIN,
                                "--layout-features=*", "--name-IDs=*", "--notdef-outline", "--flavor=woff2",
                                "--output-file=" + os.path.join(out, name)], check=True)
                print("subset", name, os.path.getsize(os.path.join(out, name)), "bytes")
            else:
                shutil.copyfile(os.path.join(src, "files", name), os.path.join(out, name))
                print("copied", name)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "build":
        pages = build()
        print("built %s in %s: %s" % (", ".join(sorted(pages)), HERE, config()["site_url"]))
    elif cmd == "cards":
        if os.path.abspath(sys.argv[2]).startswith(HERE):
            raise SystemExit("cards: pick a directory outside brand/site (the card pages are never published)")
        print("cards %s in %s" % (", ".join(cards(sys.argv[2])), sys.argv[2]))
    elif cmd == "fonts":
        fonts(*sys.argv[2:3])
    elif cmd == "open":
        if os.path.abspath(sys.argv[2]) == HERE:
            raise SystemExit("open: pick a directory outside brand/site (the open variant is never published)")
        print("built %s in %s" % (", ".join(sorted(build(out=sys.argv[2], open_variant=True))), sys.argv[2]))
    else:
        raise SystemExit("usage: build.py [build|fonts [cache]|open DIR|cards DIR]")
