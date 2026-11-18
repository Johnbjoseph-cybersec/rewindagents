"""Site (RB3): the pages are a build output of brand/site/build.py; every command on them is the README's, every
number is the code's, every terminal line is one the real session printed (brand/demo/manifest.json, which
tests/test_demo.py replays); the only hostname for the product lives in brand/site/config.json; the pages are
well-formed, self-contained (local scripts only under a 'self' CSP, nothing loaded from outside) and every local link resolves. Stdlib
only: no browser is needed here. The looking step is bin/render_html.sh in FIRE, run by hand."""
import importlib.util
import io
import json
import os
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRAND = os.path.join(ROOT, "brand")
SITE = os.path.join(BRAND, "site")
SRC = os.path.join(ROOT, "src", "rewindagents")
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, BRAND)

from contrast_check import PALETTE  # noqa: E402
import rewindagents  # noqa: E402
from rewindagents import agents, bashscan, export, hook  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import live_evidence  # noqa: E402

PAGES = ["index.html", "pricing.html", "docs/index.html"]
SKIP_DIRS = {".git", ".venv", ".brandcache", "node_modules", "__pycache__", "build", "dist", "assets", "frames", "fonts"}
# A hostname that would tie the product to a domain nobody has bought (FIRE, 2026-11-11). github.io is the one
# address in use, and it may appear only in config.json and in the pages built from it.
PRODUCT_HOST = re.compile(r"rewindagents\.(com|dev|io|app|org|net|sh|co|ai)\b|[\w.-]+\.github\.io", re.I)
HOST_ALLOWED = {"brand/site/config.json", "brand/site/manifest.json", "tests/test_site.py"} | {"brand/site/" + p for p in PAGES}
# The one source the landing page quotes (the gap section, 2026-11-18): the exact page the README cites for the
# checkpoint comparison, nothing else on that host. test_every_absolute_url_on_the_pages_comes_from_config checks
# the README still links it.
CITED = "https://code.claude.com/docs/en/checkpointing"
THIRD_PARTY = ("https://schema.org",)
BANNED = re.compile(r"revolutionary|seamless|unleash|AI-powered|game-changer|secure|protect|defend|magic|"
                    r"never lose|instant|bulletproof|foolproof|guaranteed", re.I)
NETWORK = re.compile(r"^\s*(?:import|from)\s+(socket|http|urllib|ssl|smtplib|ftplib|xmlrpc|requests|httpx)\b", re.M)
VOID = {"meta", "link", "img", "br", "hr", "input", "source", "track", "wbr"}
FONT_FAMILIES = {"Bricolage Grotesque", "Hanken Grotesk", "Commit Mono"}


def load_build():
    spec = importlib.util.spec_from_file_location("site_build", os.path.join(SITE, "build.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read(rel, base=SITE):
    with open(os.path.join(base, rel), encoding="utf-8") as f:
        return f.read()


def config():
    return json.loads(read("config.json"))


def manifest():
    return json.loads(read("manifest.json"))


def repo_text_files():
    for dirpath, dirs, files in os.walk(ROOT):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in files:
            path = os.path.join(dirpath, name)
            try:
                with open(path, encoding="utf-8") as f:
                    yield os.path.relpath(path, ROOT), f.read()
            except (UnicodeDecodeError, OSError):
                continue


class Doc(HTMLParser):
    """Tag balance, every href/src, scripts, h1 count and the visible text of a page."""

    def __init__(self):
        super().__init__()
        self.stack, self.refs, self.scripts, self.text, self.errors, self.h1 = [], [], [], [], [], 0
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for k in ("href", "src"):
            if k in a:
                self.refs.append((tag, k, a[k]))
        if tag == "script":
            self.scripts.append(a.get("type", ""))
        if tag in ("script", "style"):
            self._skip += 1
        if tag == "h1":
            self.h1 += 1
        if tag not in VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.stack.pop()

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if tag in ("script", "style"):
            self._skip -= 1
        if not self.stack or self.stack[-1] != tag:
            self.errors.append("unexpected </%s> at line %d (open: %s)" % (tag, self.getpos()[0], self.stack[-3:]))
            return
        self.stack.pop()

    def handle_data(self, data):
        if not self._skip:
            self.text.append(data)


def parse(rel, base=SITE):
    d = Doc()
    d.feed(read(rel, base))
    d.close()
    return d


def unesc(s):
    return s.replace("&lt;", "<").replace("&gt;", ">").replace("&#x27;", "'").replace("&quot;", '"').replace("&amp;", "&")


def text_of(rel, base=SITE):
    return " ".join(" ".join(parse(rel, base).text).split())


def demo_replay_lines():
    demo = json.loads(read(os.path.join("demo", "manifest.json"), BRAND))
    return demo["beats"][0]["output"].rstrip("\n").split("\n")


class TestSite(unittest.TestCase):
    def test_site_url_lives_in_config_only(self):
        cfg = config()
        self.assertTrue(cfg["site_url"].startswith("https://"), cfg["site_url"])
        # GitHub Pages project path until 2026-11-12, then John's domain https://rewindagents.com/
        self.assertTrue(cfg["site_url"].endswith("/"), cfg["site_url"])
        self.assertIsNone(cfg["checkout_url"], "checkout_url must stay null until a Polar product exists")
        for rel, text in repo_text_files():
            if rel in HOST_ALLOWED:
                continue
            m = PRODUCT_HOST.search(text)
            self.assertIsNone(m, "%s names a product hostname: %r" % (rel, m and m.group(0)))

    def test_every_absolute_url_on_the_pages_comes_from_config(self):
        cfg = config()
        ok = (cfg["site_url"], cfg["repo_url"]) + THIRD_PARTY
        for p in PAGES:
            for url in set(re.findall(r"https?://[^\s\"'<>]+", read(p))):
                if url == "https://...":        # the README's "or: pip install git+https://..." comment
                    continue
                if url == CITED:                # quoted source, exact URL only, and only while the README cites it
                    self.assertIn("(%s)" % CITED, read("README.md", ROOT), "the gap section cites what the README cites")
                    continue
                self.assertTrue(url.startswith(ok), "%s: %s" % (p, url))

    def test_pages_rebuild_byte_for_byte(self):
        build = load_build()
        with tempfile.TemporaryDirectory() as d:
            with redirect_stdout(io.StringIO()):
                build.build(out=d)
            for rel in PAGES + ["manifest.json", "site.min.css"]:
                self.assertEqual(read(rel, d), read(rel), "%s drifted: run python3 brand/site/build.py" % rel)

    def test_pages_are_well_formed_and_self_contained(self):
        cfg = config()
        build = load_build()
        with tempfile.TemporaryDirectory() as d:
            with redirect_stdout(io.StringIO()):
                build.build(out=d)
            for p in PAGES:
                doc = parse(p, d)
                self.assertEqual(doc.errors, [], p)
                self.assertEqual(doc.stack, [], "%s: unclosed %s" % (p, doc.stack))
                self.assertEqual(doc.h1, 1, "%s: one h1" % p)
                # scripts: the JSON-LD block and site.js, deferred; nothing inline runs (the CSP says so) and nothing
                # runs before first paint. GSAP is not on the page: site.js adds it after first paint (go-live, 2026-11-13).
                raw = read(p, d)
                srcs = re.findall(r'<script src="([^"]+)"', raw)
                self.assertEqual(doc.scripts.count("application/ld+json"), 1, p)
                self.assertEqual(len(doc.scripts), len(srcs) + 1, "%s: every other script has a src" % p)
                self.assertEqual([re.sub(r"^\.\./", "", x) for x in srcs], ["site.js"], "%s: scripts %s" % (p, srcs))
                self.assertRegex(raw, r'<script src="(\.\./)?site\.js" defer></script>', p)
                self.assertNotIn("vendor/gsap", raw, p)
                self.assertRegex(raw, r'<link rel="stylesheet" href="(\.\./)?site\.min\.css">', p)
                self.assertIn("content=\"default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; media-src 'self'; "
                              "font-src 'self'; connect-src 'none'; base-uri 'none'; form-action 'none'\"", raw, p)
                self.assertNotRegex(raw, r' style="| on[a-z]+="', "%s: inline style/handler would be blocked by the CSP" % p)
                ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', read(p, d), re.S).group(1))
                self.assertEqual(ld["url"], cfg["site_url"] + build.PAGES[p])
                here = os.path.dirname(os.path.join(d, p))
                for tag, attr, ref in doc.refs:
                    if ref.startswith("#"):
                        continue
                    if ref.startswith(("http://", "https://")):
                        if tag == "link":      # only the canonical link may be absolute, and only to site_url
                            self.assertTrue(ref.startswith(cfg["site_url"]), "%s: <link> to %s" % (p, ref))
                        else:
                            self.assertEqual(tag, "a", "%s: external %s on <%s>" % (p, ref, tag))
                        continue
                    target = os.path.normpath(os.path.join(here, ref.split("#")[0]))
                    if os.path.isdir(target):
                        target = os.path.join(target, "index.html")
                    self.assertTrue(os.path.isfile(target), "%s: %s=%s does not resolve" % (p, attr, ref))
                html = read(p, d)
                self.assertIn('<meta name="viewport"', html)
                self.assertIn('<link rel="canonical" href="%s%s">' % (cfg["site_url"], build.PAGES[p]), html)
                self.assertIn('property="og:image" content="%sassets/social-preview-1280x640.png"' % cfg["site_url"], html)
            # every in-page anchor points at an id on that page
            for p in PAGES:
                html = read(p, d)
                ids = set(re.findall(r' id="([^"]+)"', html))
                for href in re.findall(r' href="#([^"]+)"', html):
                    self.assertIn(href, ids, "%s: #%s" % (p, href))

    def test_site_js_adds_only_the_motion_files_and_only_after_first_paint(self):
        """The contract since go-live (John, 2026-11-13): site.js may add exactly three scripts, GSAP 3.13 from vendor/
        beside it, and only after both the load event and the browser's first contentful paint (or at the first
        scroll, touch or key). Everything else is as before: nothing fetched or parsed, no other origin, no inline
        style on the pages, and motion only for content still below the fold, so nothing on screen shifts."""
        js = read("site.js")
        self.assertNotRegex(js, r"\bfetch\(|XMLHttpRequest|WebSocket|sendBeacon|\beval\(|new Function|innerHTML|outerHTML|"
                                r"insertAdjacentHTML|document\.write|import\(|new Worker|importScripts",
                            "site.js only animates what is on the page; it fetches and parses nothing")
        self.assertNotRegex(js, r"https?:|//[\w-]+\.[\w.-]+/", "no URL to another origin in site.js")
        vendor = re.search(r"var VENDOR = \[([^\]]*)\];", js)
        self.assertIsNotNone(vendor, "the files site.js may add are one literal list")
        files = re.findall(r'"([^"]+)"', vendor.group(1))
        self.assertEqual(files, ["vendor/gsap.min.js", "vendor/ScrollTrigger.min.js", "vendor/SplitText.min.js"])
        for rel in files:
            body = read(rel)
            self.assertIn("3.13.0", body[:200], rel)
            self.assertNotIn("sourceMappingURL", body, rel)
        # one place makes a script element, and its src is a VENDOR entry resolved against site.js's own URL
        self.assertEqual(len(re.findall(r'createElement\("script"\)', js)), 1)
        self.assertEqual(len(re.findall(r"\.src = ", js)), 1)
        self.assertIn("tag.src = new URL(VENDOR[n++], here).href;", js)
        self.assertIn("var here = document.currentScript && document.currentScript.src;", js)
        self.assertEqual(sorted(set(re.findall(r'createElement\("(\w+)"\)', js))), ["button", "div", "script", "span"],
                         "copy buttons, the tape, and the one script tag; nothing else is made")
        # after first paint: the load event and the first-contentful-paint entry both, then an idle moment
        self.assertIn('getEntriesByName("first-contentful-paint")', js)
        self.assertIn('window.addEventListener("load", pass', js)
        self.assertIn("var gates = 2;", js)
        self.assertIn("requestIdleCallback", js)
        self.assertIn('if (reduce || !here) return;', js)
        # GSAP runs only on what is still below the fold: no tween is set up on anything already on screen. The one
        # exception is the hero stage (2026-11-18), which may change visibility and transform only, never layout or
        # opacity (test_hero_stage_is_the_recorded_session_and_never_moves_the_page), so the first paint never shifts
        self.assertIn("function below(el) { return el.getBoundingClientRect().top > window.innerHeight; }", js)
        self.assertNotIn('safe("hero"', js, "the hero's intro is CSS; GSAP never re-hides the first screen")
        for sel in ('$$(".sec .label").filter(below)', "$$(sel).filter(below)", '$$(".ledger .k").filter(below)',
                    "!below(frame)", "!below(c)"):
            self.assertIn(sel, js)
        # no CLS from the first screen: nothing is hidden waiting for a script, and the intro moves without fading
        css = read("site.css")
        self.assertNotRegex(css, r"js-motion|motion-ready|failsafe", "no class a script must add before the hero shows")
        rise = re.search(r"@keyframes rise \{(.*?)\}\s*\}", css, re.S)
        self.assertIsNotNone(rise)
        self.assertNotIn("opacity", rise.group(1), "the hero is painted from the first frame")
        self.assertFalse(os.path.exists(os.path.join(SITE, "vendor", "flag.js")), "no script runs before first paint")

    def test_agent_strip_shows_only_agents_with_a_hook(self):
        index = read("index.html")
        strip = re.search(r'<div class="agents">(.*?)</div>', index, re.S).group(1)
        names = re.findall(r'<li class="ag">.*?<span>([^<]+)</span></li>', strip)
        self.assertEqual(len(names), len(agents.AGENTS), names)
        for logo in re.findall(r'vendor/logos/([\w.-]+)', strip):
            self.assertTrue(os.path.isfile(os.path.join(SITE, "vendor", "logos", logo)), logo)
        self.assertNotRegex(strip, r"(?i)openai", "no OpenAI mark: Codex is shown by name")

    def test_film_captions_are_the_vsl_captions(self):
        build = load_build()
        cues = build.srt_cues("brand/vsl/%s.srt" % build.FILM)
        index = read("index.html")
        self.assertEqual(len(re.findall(r'class="ft(?: ch)?"', index)), len(cues), "one ruler tick per caption line")
        self.assertEqual(len(re.findall(r'class="ft ch"', index)), len(build.CHAPTERS), "every chapter is on the ruler")
        self.assertIn('src="assets/%s.vtt"' % build.FILM, index)
        self.assertTrue(os.path.isfile(os.path.join(BRAND, "vsl", "vsl-90s-poster.jpg")))

    def test_landing_fork_rows_are_short_and_link_the_docs(self):
        """John, 2026-11-13: on the landing page "Fork any recorded step" and "Compare the runs" say at most two short
        sentences each; the README's full sentences are on the docs page (checked above), and the section links there."""
        build = load_build()
        index = read("index.html")
        sec = re.search(r'<section class="sec" id="fork".*?</section>', index, re.S).group(0)
        for title, short in (("Fork any recorded step", build.FORK_SHORT), ("Compare the runs", build.COMPARE_SHORT)):
            m = re.search(r"<h3>%s</h3><p>(.*?)</p>" % re.escape(title), sec)
            self.assertIsNotNone(m, title)
            said = unesc(re.sub(r"</?code>", "`", m.group(1)))
            self.assertEqual(said, " ".join(short), title)
            sentences = re.findall(r".+?\.(?=\s|$)", said)
            self.assertLessEqual(len(sentences), 2, title)
            for s in sentences:
                self.assertLessEqual(len(s.split()), 20, "%s: %s" % (title, s))
        self.assertIn('<a href="docs/#fork">', sec)
        self.assertIn('<h2 id="fork">Fork and compare</h2>', read("docs/index.html"))
        # the long form lives on the docs page, word for word from the README
        docs = read("docs/index.html")
        for start in build.FORK_SENTENCES + build.COMPARE_SENTENCES:
            self.assertIn(build.md_inline(build.readme_sentence(read("README.md", ROOT), start)), docs, start)

    def test_film_poster_is_lazy_sized_and_never_fetched_at_load(self):
        """The poster is a lazy <picture> under the video, AVIF and WebP at POSTER_WIDTHS (a phone takes the 960 px
        one), not the video's poster attribute, which a browser fetches at once and at full size (go-live, 2026-11-13)."""
        build = load_build()
        index = read("index.html")
        video = re.search(r"<video [^>]*>", index).group(0)
        self.assertNotIn("poster=", video)
        self.assertIn('preload="none"', video)
        pic = re.search(r'<picture class="film-poster">(.*?)</picture>', index, re.S)
        self.assertIsNotNone(pic)
        self.assertLess(index.index('<picture class="film-poster">'), index.index("<video "), "under the video")
        img = re.search(r"<img [^>]*>", pic.group(1)).group(0)
        for attr in ('src="assets/film-poster.jpg"', 'alt=""', 'width="1920"', 'height="1080"', 'loading="lazy"',
                     'decoding="async"'):
            self.assertIn(attr, img)
        narration = read(os.path.join("vsl", "narration.py"), BRAND)
        self.assertIn("POSTER_WIDTHS = %r" % (build.POSTER_WIDTHS,), narration, "one list of sizes, two places")
        for fmt in ("avif", "webp"):
            srcset = re.search(r'<source type="image/%s" srcset="([^"]+)" sizes="([^"]+)">' % fmt, pic.group(1))
            self.assertIsNotNone(srcset, fmt)
            self.assertEqual(srcset.group(1), ", ".join("assets/film-poster-%d.%s %dw" % (w, fmt, w) for w in build.POSTER_WIDTHS))
            for w in build.POSTER_WIDTHS:
                src = os.path.join(BRAND, "vsl", "%s-poster-%d.%s" % (build.FILM, w, fmt))
                self.assertTrue(os.path.isfile(src), src)
                if w <= 960:        # what a phone fetches: small, after first paint
                    self.assertLess(os.path.getsize(src), 25000, src)
        css = read("site.css")
        self.assertIn(".film-poster img { position: absolute; inset: 0;", css, "no layout of its own: CLS stays 0")

    def test_fonts_before_first_paint_are_latin_only(self):
        """Commit Mono ships whole in fontsource's latin file (48 KB a weight); `build.py fonts` cuts it to the
        latin range (go-live, 2026-11-13). A re-copy of the whole font fails here."""
        build = load_build()
        for w in build.FONTS["commit-mono"]:
            path = os.path.join(SITE, "fonts", "commit-mono-latin-%d-normal.woff2" % w)
            self.assertLess(os.path.getsize(path), build.FONT_MAX_BYTES, path)
        for p in PAGES:
            for ch in text_of(p):
                self.assertTrue(ord(ch) <= 0xFF or 0x2000 <= ord(ch) <= 0x206F or ch in "\u20ac\u2122\u2191\u2193\u2212\u2215\ufeff\ufffd",
                                "%s: %r is outside the fonts' latin range" % (p, ch))

    def test_hero_panel_shows_lines_the_session_printed(self):
        # The hero leads with the launch headline (John, 2026-11-18): the wrecked-repo rewind, quoted from
        # brand/demo/manifest.json, which tests/test_demo.py proves is what the CLI prints today. Fork and compare
        # (brand/demo/runs.json, proved by tests/test_runs_demo.py) is the second section and must stay on the page.
        m = manifest()
        build = load_build()
        self.assertEqual(m["course"], build.COURSE)
        self.assertIn(build.COURSE, read("BRAND.md", BRAND))
        index = read("index.html")
        h1 = re.search(r'<h1 id="h1">(.*?)</h1>', index, re.S).group(1)
        self.assertEqual(unesc(re.sub(r"<[^>]+>", "", h1)), build.COURSE)
        self.assertIn('<span class="nw">rm -rf</span>', h1)   # never wraps as "rm -" / "rf"
        hero = index[index.index('<section class="hero"'):index.index("</section>", index.index('<section class="hero"'))]
        hero_text = unesc(re.sub(r"<[^>]+>", "", hero))
        demo_lines = {ln for b in json.loads(read(os.path.join("demo", "manifest.json"), BRAND))["beats"]
                      for ln in [b["command"]] + b["output"].rstrip("\n").split("\n")}
        rewind = m["rewind_rows"]
        self.assertEqual([k for k, _ in rewind][0], "cmd")
        for kind, text in rewind:
            if kind in ("out", "hit"):
                self.assertIn(text, demo_lines, text)
            if kind != "gap":
                self.assertIn(text, hero_text, text)
        self.assertNotIn("fork 2", hero_text)
        runs = json.loads(read(os.path.join("demo", "runs.json"), BRAND))
        printed = {ln for lines in runs["output"].values() for ln in lines}
        self.assertEqual([t for k, t in m["hero"] if k == "cmd"], [runs["commands"]["fork"], runs["commands"]["compare"]])
        shown = unesc(re.sub(r"<[^>]+>", "", index))
        for kind, text in m["hero"]:
            if kind in ("out", "hit", "tab", "tabhit"):
                self.assertIn(text, printed, text)
            self.assertIn(text, shown, text)
        # the clip's four commands and every line they printed are on the page as text too
        demo = json.loads(read(os.path.join("demo", "manifest.json"), BRAND))
        for b in demo["beats"]:
            self.assertIn(b["command"], index)
            for ln in b["output"].rstrip("\n").split("\n"):
                self.assertIn(ln.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), index, ln)

    def test_hero_stage_is_the_recorded_session_and_never_moves_the_page(self):
        """The hero stage (bold round, 2026-11-18; replaces the hero replay panel): a ruler of the session's steps,
        the project's files and the terminal that printed them. Every terminal row is a recorded line, the file tree is
        derived from those lines (never typed), the built page is the still after the rewind, and site.js plays and
        scrubs it after first paint by visibility and transform only, with a Stop control, never with reduced motion."""
        demo = json.loads(read(os.path.join("demo", "manifest.json"), BRAND))
        beats = demo["beats"]
        index = read("index.html")
        stage = index[index.index('<div class="stage" id="stage">'):index.index('<p class="caption st-cap">')]
        term = re.search(r'<pre class="term"><code>(.*?)</code></pre>', stage, re.S).group(1)
        rows = [unesc(re.sub(r"<[^>]+>", "", r)) for r in term.split("\n")]
        lines = lambda b: b["output"].rstrip("\n").split("\n")   # noqa: E731
        self.assertEqual(rows, ["$ " + beats[0]["command"]] + lines(beats[0]) + ["$ " + beats[2]["command"]] + lines(beats[2]),
                         "the whole replay, then the whole rewind, as printed")
        self.assertEqual(len(re.findall(r'class="sr-tk', stage)), demo["steps"], "one ruler tick per recorded step")
        # the tree: every file a file tool or the rewind names, born/gone/back from the recorded words
        steps = [re.match(r"^\s*(\d+)\s+(\w+)\s+(.*?)(?:\s+\[\d+ checkpointed\])?$", ln).groups() for ln in lines(beats[0])]
        restored = [ln.split()[1] for ln in lines(beats[2]) if ln.strip().startswith("restore ")]
        named = {t for _, tool, t in steps if tool in ("Read", "Edit", "Write")} | set(restored)
        tree = re.findall(r'<li class="ff[^"]*" data-born="(\d+)" data-gone="(\d+)" data-back="(-?\d+)" data-touch="([^"]*)" '
                          r'data-still="([^"]*)"><span class="fn"><span class="fd">([^<]*)</span>([^<]*)</span>', stage)
        self.assertEqual({d + f for *_, d, f in tree}, named)
        untracked = {ln[3:] for ln in lines(beats[3]) if ln.startswith("?? ")}
        wipe = next(int(n) for n, tool, t in steps if tool == "Bash" and t.startswith("rm -rf "))
        wiped = next(t for n, tool, t in steps if int(n) == wipe)[len("rm -rf "):] + "/"
        for born, gone, back, touch, still, d, f in tree:
            path = d + f
            first_write = min((int(n) for n, tool, t in steps if t == path and tool == "Write"), default=0)
            self.assertEqual(int(born), first_write if path in untracked else 0, path)
            self.assertEqual(int(gone), wipe if path.startswith(wiped) else 0, path)
            self.assertEqual(int(back), lines(beats[2]).index("  restore  " + path) if path in restored else -1, path)
            for t in filter(None, touch.split(",")):
                n, tool = t.split(":")
                self.assertTrue(any(int(m) == int(n) and tl == tool for m, tl, _ in steps), "%s: %s" % (path, t))
            self.assertEqual(still, "restore" if path in restored else (lambda t: "%s %s" % (t[1], t[0]))(touch.split(",")[-1].split(":")), path)
        # the script: after first paint, never with reduced motion, nothing typed of its own, nothing laid out
        js = read("site.js")
        body = js[js.index('safe("stage"'):js.index('safe("heads"')]
        self.assertLess(js.index('if (reduce || !here) return;'), js.index("function motion()"))
        self.assertNotRegex(body, r'"[^"]*rewindagents[^"]*"|"[^"]*(Bash|Write|Read|Edit|restore|README|tests/|app/)[^"]*"',
                            "no session text typed by the script")
        self.assertIn('"Stop the replay"', body)
        self.assertNotRegex(body, r"\.style\.(display|height|width|margin|padding|top|left)|opacity", "visibility and transform only")
        self.assertIn("window.scrollY < pinTop", body, "the pin never adds space above a reader who is past it")
        css = read("site.css")
        self.assertIn(".stage.live .l.off, .stage.live .ff.off { visibility: hidden; }", css)
        self.assertNotRegex(css, r"(^|[,}]\s*)\.stage(-pin)?\s*[,{][^}]*animation", "no transform on the pin's ancestors")
        self.assertIn('<span class="st-ctl"></span>', stage, "the Stop button has its slot before it exists")

    def test_counters_are_counted_from_the_repository(self):
        """The hero's counters are build-time numbers, each with its source on the page (no live fetches: the CSP is
        connect-src 'none'). The test count is the static count of test functions, never a claim that tests pass."""
        build = load_build()
        index = read("index.html")
        cells = re.findall(r'<li><b class="cnt" data-to="(\d+)">(\d+)</b><span class="cnt-l">([^<]+)</span><span class="cnt-s">(.*?)</span></li>', index)
        got = {lbl: (int(a), int(b), src) for a, b, lbl, src in cells}
        tests_dir = os.path.join(ROOT, "tests")
        defs = sum(len(re.findall(r"^\s*def test_", read(n, tests_dir), re.M)) for n in os.listdir(tests_dir) if n.endswith(".py"))
        demo = json.loads(read(os.path.join("demo", "manifest.json"), BRAND))
        restored = len([ln for ln in demo["beats"][2]["output"].split("\n") if ln.strip().startswith("restore ")])
        with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as fh:
            self.assertIn("dependencies = []", fh.read())
        want = {"coding agents with a hook": (len(agents.AGENTS), "src/<wbr>rewindagents/<wbr>agents.py"),
                "test functions in the repository": (defs, "def test_"),
                "claims on this page, each checked by a named test": (len(build.PROOF), 'href="#tested"'),
                "files back from one rewind, in the session above": (restored, "brand/<wbr>demo/<wbr>manifest.json"),
                "dependencies beyond the standard library": (0, "pyproject.toml")}
        self.assertEqual(set(got), set(want))
        for lbl, (n, src) in want.items():
            self.assertEqual(got[lbl][:2], (n, n), lbl)
            self.assertIn(src, got[lbl][2], lbl)
        self.assertNotRegex(text_of("index.html"), r"\d+ tests? pass", "a count of test functions, never a pass claim")

    def test_gap_section_is_the_readme_comparison(self):
        """'What Claude Code's checkpoints miss' quotes the README's table cells, cites the docs the README cites,
        and carries the README's own exception (its /rewind undoes Bash changes to a file Claude had edited)."""
        build = load_build()
        readme = read("README.md", ROOT)
        head, rows = build.readme_table(readme, "After your agent...")
        index = read("index.html")
        sec = re.search(r'<section class="sec" id="gap".*?</section>', index, re.S).group(0)
        text = unesc(re.sub(r"<[^>]+>", "", sec))
        for r in rows[:2]:
            self.assertIn(re.sub(r"`", "", r[0]), text)
            self.assertIn(re.match(r'^"([^"]+)"', r[1]).group(1), text)
            self.assertIn(r[2], text)
        self.assertNotIn(rows[2][0], text, "the third row is the agent strip's job")
        self.assertIn("does undo Bash changes to a file Claude had already edited", text)
        self.assertIn(build.GAP_NUANCE.replace("`", ""), text)
        rm_line = next(ln for ln in demo_replay_lines() if "rm -rf" in ln)
        self.assertIn(rm_line.strip(), text, "the evidence line is the session's own replay line")

    def test_numbers_come_from_the_code(self):
        f = manifest()["facts"]
        self.assertEqual(f["version"], rewindagents.__version__)
        self.assertEqual(f["result_chars"], hook.MAX_RESULT_CHARS)
        self.assertEqual(f["file_mb"] * 1024 * 1024, hook.MAX_CHECKPOINT_BYTES)
        self.assertEqual(f["scan_files"], bashscan.MAX_SCAN_FILES)
        self.assertEqual(f["diff_kb"] * 1024, export.MAX_DIFF_BYTES)
        self.assertEqual(f["diff_lines"], export.MAX_DIFF_LINES)
        index, docs = text_of("index.html"), text_of("docs/index.html")
        for page in (index, docs):
            self.assertIn("{:,} characters".format(hook.MAX_RESULT_CHARS), page)
            self.assertIn("%d MB" % (hook.MAX_CHECKPOINT_BYTES // 2 ** 20), page)
            self.assertIn("{:,} files".format(bashscan.MAX_SCAN_FILES), page)
            self.assertIn("%d KB" % (export.MAX_DIFF_BYTES // 1024), page)
            self.assertIn("%d lines" % export.MAX_DIFF_LINES, page)
            for d in bashscan.SKIP_DIRS:
                self.assertIn(d, page)
        self.assertIn("v%s" % rewindagents.__version__, index)
        with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as fh:
            self.assertIn('requires-python = "%s"' % f["py_req"], fh.read())

    def test_every_command_block_is_a_readme_block(self):
        readme = read("README.md", ROOT)
        sh = "\n".join(re.findall(r"```sh\n(.*?)```", readme, re.S))
        readme_lines = {ln.strip() for ln in sh.split("\n") if ln.strip()}
        # every `$ command` on the pages is a README line (with any trailing comment put back)
        for p in PAGES:
            html = read(p)
            beat_commands = {b["command"] for b in json.loads(read(os.path.join("demo", "manifest.json"), BRAND))["beats"]}
            # the fork-and-compare panels quote ux-review/try-runs.sh (tests/test_runs_demo.py checks them there)
            run_commands = set(json.loads(read(os.path.join("demo", "runs.json"), BRAND))["commands"].values())
            for block in re.findall(r'<pre class="term[^"]*"><code>(.*?)</code></pre>', html, re.S):
                rows = block.split("\n")
                for i, row in enumerate(rows):
                    if not row.startswith('<span class="l"><span class="p">$ </span>'):
                        continue
                    cmd = unesc(re.sub(r"<[^>]+>", "", row)[2:])
                    if cmd in beat_commands or cmd in run_commands or cmd == "rewindagents --version":
                        continue
                    # the README's trailing comment sits on the row before (describes) or after (alternative)
                    near = [unesc(re.sub(r"<[^>]+>", "", rows[j])) for j in (i - 1, i + 1)
                            if 0 <= j < len(rows) and 'class="c"' in rows[j]]
                    ok = cmd in readme_lines or any(ln.startswith(cmd) and ln.endswith(c) for ln in readme_lines for c in near)
                    self.assertTrue(ok, "%s: command not in README: %r" % (p, cmd))
        # the one output line not from the session is the version line, and it is what the binary prints
        self.assertIn("rewindagents %s" % rewindagents.__version__, text_of("docs/index.html"))

    def check_docs_answer(self, anchor, title, heading, first, sentences_from):
        """A docs section is one README sh block (picked by heading + first line) and README sentences, word for word."""
        readme = read("README.md", ROOT)
        html = read("docs/index.html")
        m = re.search(r'<h2 id="%s">%s</h2>\n(<pre class="term[^"]*"><code>.*?</code></pre>)\n<p>(.*?)</p>'
                      % (anchor, re.escape(title)), html, re.S)
        self.assertIsNotNone(m, "docs page has no '%s' answer" % title)
        self.assertIn('<a href="#%s">%s</a>' % (anchor, title), html)
        # the panel is exactly the README block, as code() renders it
        build = load_build()
        block = next(blk for blk in build.readme_blocks(readme, heading) if blk[0].startswith(first))
        self.assertEqual(m.group(1), build.code(block))
        page_cmds = [unesc(re.sub(r"<[^>]+>", "", r))[2:] for r in m.group(1).split("\n") if 'class="p"' in r]
        readme_cmds = [re.sub(r"\s+#.*", "", ln).strip() for ln in block if ln.strip() and not ln.startswith("#")]
        self.assertEqual(page_cmds, readme_cmds)
        # every sentence under it is a README sentence, word for word, one per listed opening
        prose = " ".join(readme.split())
        said = unesc(re.sub(r"</?code>", "`", m.group(2)))
        sentences = re.findall(r".+?\.(?=\s|$)", said)
        self.assertEqual(len(sentences), len(sentences_from))
        for s, start in zip(sentences, sentences_from):
            self.assertTrue(s.strip().startswith(start), s)
            self.assertIn(s.strip(), prose)
        return page_cmds

    def test_docs_status_answer_is_the_readme_block_and_words(self):
        build = load_build()
        cmds = self.check_docs_answer("status", "Is it recording?", "Claude Code hook", "rewindagents status",
                                      build.STATUS_SENTENCES)
        self.assertEqual(cmds, ["rewindagents status"])

    def test_docs_move_and_free_space_are_the_readme_blocks_and_words(self):
        build = load_build()
        cmds = self.check_docs_answer("bundle", "Move a session", "Move a session to another machine",
                                      "rewindagents bundle", build.MOVE_SENTENCES)
        self.assertIn("rewindagents import s1.bundle", cmds)
        cmds = self.check_docs_answer("gc", "Free space", "Clean up stored copies", "rewindagents gc",
                                      build.GC_SENTENCES)
        self.assertEqual(cmds[:2], ["rewindagents gc --dry-run", "rewindagents gc"])
        # the TOC lists them in page order
        html = read("docs/index.html")
        toc = re.findall(r'<a href="#([a-z]+)">', re.search(r'<nav class="toc".*?</nav>', html, re.S).group(0))
        heads = re.findall(r'<h2 id="([a-z]+)">', html)
        self.assertEqual(toc, [h for h in heads if h in toc])
        self.assertLess(toc.index("sessions"), toc.index("bundle"))

    def test_docs_timeline_and_attach_are_the_readme_blocks_and_words(self):
        build = load_build()
        cmds = self.check_docs_answer("ui", "Timeline in a browser", "Timeline UI", "rewindagents ui", build.UI_SENTENCES)
        self.assertEqual(cmds[0], "rewindagents ui")
        cmds = self.check_docs_answer("mcp", "MCP server", build.MCP_HEADING, "rewindagents mcp", build.MCP_SENTENCES)
        self.assertEqual(cmds[0], "rewindagents mcp")
        cmds = self.check_docs_answer("attach", "Attach to a PR", "Attach a replay to a pull request",
                                      "rewindagents bundle", build.ATTACH_SENTENCES)
        self.assertEqual(cmds[0], "rewindagents bundle --out .rewindagents-pr.bundle")
        # after the first answer: the README's yaml block as a plain panel, then the README's words about the action
        readme = read("README.md", ROOT)
        html = read("docs/index.html")
        m = re.search(r'<h2 id="attach">.*?</p>\n(<pre class="term file"><code>.*?</code></pre>)\n<p>(.*?)</p>', html, re.S)
        self.assertIsNotNone(m)
        yaml = build.readme_blocks(readme, "Attach a replay to a pull request", "yaml")[0]
        self.assertEqual(m.group(1), build.plain(yaml))
        shown = [unesc(re.sub(r"<[^>]+>", "", r)) for r in m.group(1)[len('<pre class="term file"><code>'):-len("</code></pre>")].split("\n")]
        self.assertEqual(shown, yaml)          # every line as written, nothing typed
        self.assertNotIn('class="p"', m.group(1))
        prose = " ".join(readme.split())
        said = unesc(re.sub(r"</?code>", "`", m.group(2)))
        sentences = re.findall(r".+?\.(?=\s|$)", said)
        self.assertEqual(len(sentences), len(build.ATTACH_ACTION_SENTENCES))
        for s, start in zip(sentences, build.ATTACH_ACTION_SENTENCES):
            self.assertTrue(s.strip().startswith(start), s)
            self.assertIn(s.strip(), prose)
        # the action has not run on GitHub (R18b): the page says so while the README does
        if "It has not run on GitHub yet" in prose:
            self.assertIn("It has not run on GitHub yet.", said)
        html_toc = re.search(r'<nav class="toc".*?</nav>', html, re.S).group(0)
        toc = re.findall(r'<a href="#([a-z]+)">', html_toc)
        self.assertLess(toc.index("branch"), toc.index("ui"))
        self.assertEqual(toc.index("bundle") + 1, toc.index("attach"))

    @staticmethod
    def docs_panel_commands(html):
        """Every `$ command` in a terminal panel on a page, as plain text."""
        cmds = set()
        for block in re.findall(r'<pre class="term[^"]*"><code>(.*?)</code></pre>', html, re.S):
            for row in block.split("\n"):
                if 'class="p"' in row:
                    cmds.add(unesc(re.sub(r"<[^>]+>", "", row))[2:])
        return cmds

    @staticmethod
    def readme_sh_sections(readme):
        """(heading, first command of each ```sh block) for every README ## section holding one. The first command
        is the first line that runs `rewindagents` (a URL ending in rewindagents does not count), else the first
        line; trailing comments are dropped."""
        out = []
        for m in re.finditer(r"^## ([^\n]+)\n(.*?)(?=^## |\Z)", readme, re.S | re.M):
            firsts = []
            for blk in re.findall(r"```sh\n(.*?)```", m.group(2), re.S):
                lines = [re.sub(r"\s+# .*", "", ln).strip() for ln in blk.split("\n") if ln.strip()]
                firsts.append(next((ln for ln in lines if re.search(r"(?<![/\w-])rewindagents ", ln)), lines[0]))
            if firsts:
                out.append((m.group(1), firsts))
        return out

    def test_every_readme_command_section_is_on_the_docs_page(self):
        """R14, R25, R26 and R27 each found a README section missing from the docs page by hand. This finds the
        next one: each README section with a sh block has each block's first command in a docs panel, or is in
        build.NOT_ON_DOCS with a reason."""
        build = load_build()
        sections = self.readme_sh_sections(read("README.md", ROOT))
        self.assertGreaterEqual(len(sections), 15)          # the walk found the README's sections, not none
        cmds = self.docs_panel_commands(read("docs/index.html"))
        missing = [(h, c) for h, firsts in sections if h not in build.NOT_ON_DOCS for c in firsts if c not in cmds]
        self.assertEqual(missing, [], "README commands with no docs panel: add a docs section rendering the README "
                                      "block, or list the heading in NOT_ON_DOCS with a reason")
        # the exceptions are real, reasoned, and still needed
        headings = {h for h, _ in sections}
        for h, why in build.NOT_ON_DOCS.items():
            self.assertIn(h, headings, "NOT_ON_DOCS names %r, which is not a README section with a sh block" % h)
            self.assertGreater(len(why.split()), 3, h)
            firsts = dict(sections)[h]
            self.assertFalse(all(c in cmds for c in firsts), "%r is on the docs page now; drop it from NOT_ON_DOCS" % h)

    def test_docs_init_and_more_agents_are_the_readme_blocks(self):
        build = load_build()
        readme = read("README.md", ROOT)
        html = read("docs/index.html")
        m = re.search(r'<h2 id="hook">Add the hook</h2>\n(<pre class="term"><code>.*?</code></pre>)\n<p>(.*?)</p>', html, re.S)
        self.assertIsNotNone(m, "docs 'Add the hook' does not open with the init block")
        self.assertEqual(m.group(1), build.code(build.readme_blocks(readme, "Quick start")[0]))
        prose = " ".join(readme.split())
        sentences = re.findall(r".+?\.(?=\s|$)", unesc(re.sub(r"</?code>", "`", m.group(2))))
        self.assertEqual(len(sentences), len(build.INIT_SENTENCES))
        for s, start in zip(sentences, build.INIT_SENTENCES):
            self.assertTrue(s.strip().startswith(start), s)
            self.assertIn(s.strip(), prose)
        block = build.readme_blocks(readme, build.MORE_AGENTS)[0]
        self.assertIn(build.code(block), html)
        others = [k for k in agents.AGENTS if k not in ("claude", "codex", "cursor")]
        self.assertEqual(re.findall(r"rewindagents install --agent (\w+)", "\n".join(block)), others)

    def test_yaml_panel_gets_a_copy_button(self):
        """site.js copies the prompt lines of a command panel and every line of a file panel (the workflow yaml)."""
        js = read("site.js")
        self.assertIn('pre.classList.contains("file")', js)
        self.assertIn('<pre class="term file">', read("docs/index.html"))

    def test_planned_items_are_brand_md_phrases_and_nothing_is_for_sale(self):
        build = load_build()
        brand_md = read("BRAND.md", BRAND)
        for phrase in manifest()["planned"]:
            self.assertIn(phrase, brand_md, phrase)
        self.assertEqual(build.PROMISE, "Ctrl+Z for AI coding agents: record, replay, rewind.")
        self.assertIn(build.PROMISE, brand_md)
        cfg = config()
        pricing = read("pricing.html")
        self.assertIn(cfg["waitlist_url"].replace("&", "&amp;"), pricing)
        self.assertNotIn("Buy Cloud", pricing)
        self.assertIn("waitlist", read("README.md", ROOT).lower(), "the pricing page's waitlist is backed by the README")
        for p in PAGES:
            text = text_of(p)
            self.assertIn(build.CREDIT, text, p)
            if p != "docs/index.html":
                self.assertIn("planned", text, p)
                self.assertIn("Not yet priced", text, p)
        with tempfile.TemporaryDirectory() as d:
            with redirect_stdout(io.StringIO()):
                build.build(out=d, cfg={**cfg, "checkout_url": cfg["site_url"] + "checkout-test"})
            paid = read("pricing.html", d)
            self.assertIn("Buy Cloud", paid)
            self.assertIn(cfg["site_url"] + "checkout-test", paid)
            self.assertNotIn("Join the waitlist", paid)

    def test_words_on_the_pages(self):
        for p in PAGES:
            text = text_of(p)
            m = BANNED.search(text)
            self.assertIsNone(m, "%s: %r" % (p, m and m.group(0)))
            raw = read(p)
            self.assertNotIn(chr(0xA7), raw, p)
            for ch in raw:
                self.assertFalse(0x2600 <= ord(ch) <= 0x27BF or 0x1F000 <= ord(ch) <= 0x1FAFF, "%s: emoji %r" % (p, ch))
            self.assertNotRegex(text, r"\d+ (stars|users|customers|downloads|teams|developers)\b", p)
            for sentence in re.split(r"(?<=[.!?])\s+", text):
                low = sentence.lower()
                if "codex" in low or "cursor" in low:
                    # R7: the hooks exist; a page may not call them planned, and every mention is about the hook
                    self.assertIn("hook", low, "%s: Codex/Cursor outside the hook: %s" % (p, sentence))
                    self.assertNotIn("planned", low, "%s: the Codex/Cursor hooks are built: %s" % (p, sentence))
                if "pypi" in low:
                    # on PyPI since v0.0.8 (2026-11-18): a page may not still say it is not
                    self.assertNotRegex(low, r"not on pypi|no package on pypi", "%s: %s" % (p, sentence))
        # the pages' live-status sentences follow harness/live/evidence/*.json in both directions, as the README's do
        evidence = live_evidence.load()
        for p in ("index.html", "docs/index.html"):
            self.assertEqual(live_evidence.mismatches(text_of(p), evidence), [], p)
        docs = text_of("docs/index.html")
        for t in sorted(agents.AGENTS["cursor"].read_only | agents.AGENTS["codex"].read_only):
            self.assertIn(t, docs, t)
        for a in agents.AGENTS.values():
            self.assertIn(a.settings, docs, a.settings)
        # the "no outbound network connections" answer is a test, not a sentence. The one exception is the timeline
        # UI, a server that may only ever listen on 127.0.0.1 (ui.HOST, refused otherwise; tests/test_ui.py binds it).
        from rewindagents import ui
        self.assertEqual(ui.HOST, "127.0.0.1")
        for name in sorted(os.listdir(SRC)):
            if name.endswith(".py") and name != "ui.py":
                with open(os.path.join(SRC, name), encoding="utf-8") as fh:
                    self.assertIsNone(NETWORK.search(fh.read()), name)
        with open(os.path.join(SRC, "ui.py"), encoding="utf-8") as fh:
            imports = set(re.findall(r"^\s*(?:import|from)\s+([\w.]+)", fh.read(), re.M))
        self.assertFalse({"socket", "urllib", "urllib.request", "ssl", "smtplib", "ftplib", "requests", "httpx"} & imports,
                         "ui.py serves locally; it never opens an outbound connection")
        self.assertIn("no outbound network connections", text_of("index.html"))
        self.assertIn("127.0.0.1 only", text_of("index.html"))

    def test_css_uses_only_the_palette_and_local_fonts(self):
        css = read("site.css")
        allowed = {v.upper() for v in PALETTE.values()}
        for hexv in set(re.findall(r"#[0-9A-Fa-f]{6}\b", css)):
            self.assertIn(hexv.upper(), allowed, hexv)
        self.assertNotRegex(css, r"rgba?\(|hsla?\(|gradient\(", "colours come from the palette only, no gradients")
        families = set(re.findall(r'@font-face \{ font-family: "([^"]+)"', css))
        self.assertEqual(families, FONT_FAMILIES)
        for url in re.findall(r'url\("([^"]+)"\)', css):
            self.assertTrue(os.path.isfile(os.path.join(SITE, url)), url)
        for fam in ("bricolage-grotesque", "hanken-grotesk", "commit-mono"):
            lic = read(os.path.join("fonts", "LICENSE-%s.txt" % fam))
            self.assertIn("SIL OPEN FONT LICENSE", lic.upper(), fam)
        # the inline rulers on the pages use palette colours only
        for p in PAGES:
            for hexv in set(re.findall(r"#[0-9A-Fa-f]{6}\b", read(p))):
                self.assertIn(hexv.upper(), allowed, "%s: %s" % (p, hexv))

    def test_pages_workflow_is_pinned_and_builds_the_site(self):
        wf = read(os.path.join(".github", "workflows", "pages.yml"), ROOT)
        uses = re.findall(r"uses: (\S+)", wf)
        self.assertGreaterEqual(len(uses), 4)
        for u in uses:
            self.assertRegex(u, r"^[\w.-]+/[\w.-]+@[0-9a-f]{40}$", u)
        self.assertIn("python3 brand/site/build.py", wf)
        self.assertIn("path: brand/site", wf)
        self.assertIn("persist-credentials: false", wf)

    def test_readme_and_brand_point_to_the_site_build(self):
        self.assertIn("brand/site/config.json", read("README.md", ROOT))
        self.assertIn("brand/site/build.py", read("BRAND.md", BRAND))
        self.assertIn("## Site", read("BRAND.md", BRAND))


if __name__ == "__main__":
    unittest.main()


class TestInstallChannels(unittest.TestCase):
    """The Homebrew, npm and plugin commands on both pages are the README's second Install block, word for word."""

    def test_channels_block_is_on_home_and_docs(self):
        build = load_build()
        readme = read("README.md", ROOT)
        block = build.readme_blocks(readme, "Install")[1]
        self.assertTrue(block[0].startswith("brew install"), block)
        for page in ("index.html", "docs/index.html"):
            self.assertIn(build.code(block), read(page), page)
