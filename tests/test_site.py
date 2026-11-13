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

PAGES = ["index.html", "pricing.html", "docs/index.html"]
SKIP_DIRS = {".git", ".venv", ".brandcache", "node_modules", "__pycache__", "build", "dist", "assets", "frames", "fonts"}
# A hostname that would tie the product to a domain nobody has bought (FIRE, 2026-11-11). github.io is the one
# address in use, and it may appear only in config.json and in the pages built from it.
PRODUCT_HOST = re.compile(r"rewindagents\.(com|dev|io|app|org|net|sh|co|ai)\b|[\w.-]+\.github\.io", re.I)
HOST_ALLOWED = {"brand/site/config.json", "brand/site/manifest.json", "tests/test_site.py"} | {"brand/site/" + p for p in PAGES}
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
                self.assertTrue(url.startswith(ok), "%s: %s" % (p, url))

    def test_pages_rebuild_byte_for_byte(self):
        build = load_build()
        with tempfile.TemporaryDirectory() as d:
            with redirect_stdout(io.StringIO()):
                build.build(out=d)
            for rel in PAGES + ["manifest.json"]:
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
                # scripts: the JSON-LD block, and local files only (vendor/ + site.js); nothing inline runs, the CSP says so
                raw = read(p, d)
                srcs = re.findall(r'<script src="([^"]+)"', raw)
                self.assertEqual(doc.scripts.count("application/ld+json"), 1, p)
                self.assertEqual(len(doc.scripts), len(srcs) + 1, "%s: every other script has a src" % p)
                for src in srcs:
                    self.assertRegex(src, r"^(\.\./)?(vendor/[\w.]+\.js|site\.js)$", "%s: script %s" % (p, src))
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

    def test_site_js_loads_and_injects_nothing(self):
        js = read("site.js")
        self.assertNotRegex(js, r"\bfetch\(|XMLHttpRequest|WebSocket|\beval\(|new Function|innerHTML|outerHTML|insertAdjacentHTML|document\.write|import\(",
                            "site.js only animates what is on the page; it loads and parses nothing")
        for name in ("gsap.min.js", "ScrollTrigger.min.js", "SplitText.min.js"):
            head = read(os.path.join("vendor", name))[:200]
            self.assertIn("3.13.0", head, name)
            self.assertNotIn("sourceMappingURL", read(os.path.join("vendor", name)), name)

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
        self.assertIn('poster="assets/film-poster.jpg"', index)
        self.assertTrue(os.path.isfile(os.path.join(BRAND, "vsl", "vsl-90s-poster.jpg")))

    def test_hero_panel_shows_lines_the_session_printed(self):
        # The hero leads with the course (John, 2026-11-13): fork and compare, quoted from brand/demo/runs.json, which
        # tests/test_runs_demo.py proves try-runs.sh still prints. The rewind session stays on the page as the base:
        # tests/test_demo.py proves brand/demo/manifest.json is what the CLI prints today, and the page quotes it all.
        m = manifest()
        build = load_build()
        self.assertEqual(m["course"], build.COURSE)
        self.assertIn(build.COURSE, read("BRAND.md", BRAND))
        self.assertIn('<h1 id="h1">%s</h1>' % build.COURSE, read("index.html"))
        runs = json.loads(read(os.path.join("demo", "runs.json"), BRAND))
        printed = {ln for lines in runs["output"].values() for ln in lines}
        kinds = [k for k, _ in m["hero"]]
        self.assertEqual([t for k, t in m["hero"] if k == "cmd"], [runs["commands"]["fork"], runs["commands"]["compare"]])
        for kind, text in m["hero"]:
            if kind in ("out", "hit", "tab", "tabhit"):
                self.assertIn(text, printed, text)
        hits = [t for k, t in m["hero"] if k in ("hit", "tabhit")]
        self.assertEqual(len(hits), 1)
        self.assertTrue(hits[0].strip().startswith("clamp") and hits[0].endswith("pass"), hits)
        self.assertIn("cmd", kinds)
        index = read("index.html")
        shown = unesc(re.sub(r"<[^>]+>", "", index))
        for _, text in m["hero"]:
            self.assertIn(text, shown, text)
        # the clip's four commands and every line they printed are on the page as text too
        demo = json.loads(read(os.path.join("demo", "manifest.json"), BRAND))
        for b in demo["beats"]:
            self.assertIn(b["command"], index)
            for ln in b["output"].rstrip("\n").split("\n"):
                self.assertIn(ln.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), index, ln)

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
            self.assertIn("It has not run on GitHub yet: this repository is not public.", said)
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
                    self.assertRegex(low, r"not on pypi|no package on pypi", "%s: %s" % (p, sentence))
        # the pages carry the same caveat the README does, and name the unscanned tools from the code
        for p in ("index.html", "docs/index.html"):
            self.assertIn("not yet in a live session", text_of(p), p)
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
