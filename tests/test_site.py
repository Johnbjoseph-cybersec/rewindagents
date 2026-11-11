"""Site (RB3): the pages are a build output of brand/site/build.py; every command on them is the README's, every
number is the code's, every terminal line is one the real session printed (brand/demo/manifest.json, which
tests/test_demo.py replays); the only hostname for the product lives in brand/site/config.json; the pages are
well-formed, self-contained (no scripts, nothing loaded from outside) and every local link resolves. Stdlib
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
SRC = os.path.join(ROOT, "src", "rewindagent")
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, BRAND)

from contrast_check import PALETTE  # noqa: E402
import rewindagent  # noqa: E402
from rewindagent import agents, bashscan, export, hook  # noqa: E402

PAGES = ["index.html", "pricing.html", "docs/index.html"]
SKIP_DIRS = {".git", ".venv", ".brandcache", "node_modules", "__pycache__", "build", "dist", "assets", "frames", "fonts"}
# A hostname that would tie the product to a domain nobody has bought (FIRE, 2026-11-11). github.io is the one
# address in use, and it may appear only in config.json and in the pages built from it.
PRODUCT_HOST = re.compile(r"rewindagent\.(com|dev|io|app|org|net|sh|co|ai)\b|[\w.-]+\.github\.io", re.I)
HOST_ALLOWED = {"brand/site/config.json", "brand/site/manifest.json", "tests/test_site.py"} | {"brand/site/" + p for p in PAGES}
THIRD_PARTY = ("https://schema.org",)
BANNED = re.compile(r"revolutionary|seamless|unleash|AI-powered|game-changer|secure|protect|defend|magic|"
                    r"never lose|instant|bulletproof|foolproof|guaranteed", re.I)
NETWORK = re.compile(r"^\s*(?:import|from)\s+(socket|http|urllib|ssl|smtplib|ftplib|xmlrpc|requests|httpx)\b", re.M)
VOID = {"meta", "link", "img", "br", "hr", "input", "source", "wbr"}
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
        self.assertTrue(cfg["site_url"].endswith("/rewindagent/"), cfg["site_url"])
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
                self.assertEqual(doc.scripts, ["application/ld+json"], "%s: only the JSON-LD block may be a script" % p)
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

    def test_hero_panel_shows_lines_the_session_printed(self):
        # tests/test_demo.py proves brand/demo/manifest.json is what the CLI prints today; the hero must quote it.
        m = manifest()
        demo = json.loads(read(os.path.join("demo", "manifest.json"), BRAND))
        commands = [b["command"] for b in demo["beats"]]
        outputs = {ln for b in demo["beats"] for ln in b["output"].rstrip("\n").split("\n")}
        kinds = [k for k, _ in m["hero"]]
        self.assertEqual([k for k in kinds if k == "cmd"], ["cmd", "cmd"])
        for kind, text in m["hero"]:
            if kind == "cmd":
                self.assertIn(text, commands, text)
            elif kind in ("out", "hit"):
                self.assertIn(text, outputs, text)
            else:
                self.assertEqual((kind, text.strip()), ("gap", "..."))
        hits = [t for k, t in m["hero"] if k == "hit"]
        self.assertEqual(len(hits), 4)
        self.assertTrue(all(t.startswith("  restore") for t in hits), hits)
        self.assertTrue(any("undo it with: rewindagent rewind" in t for _, t in m["hero"]))
        index = read("index.html")
        for _, text in m["hero"]:
            self.assertIn(text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), index, text)
        # the clip's four commands and every line they printed are on the page as text too
        for b in demo["beats"]:
            self.assertIn(b["command"], index)
            for ln in b["output"].rstrip("\n").split("\n"):
                self.assertIn(ln.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), index, ln)

    def test_numbers_come_from_the_code(self):
        f = manifest()["facts"]
        self.assertEqual(f["version"], rewindagent.__version__)
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
        self.assertIn("v%s" % rewindagent.__version__, index)
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
            for block in re.findall(r'<pre class="term[^"]*"><code>(.*?)</code></pre>', html, re.S):
                rows = block.split("\n")
                for i, row in enumerate(rows):
                    if not row.startswith('<span class="l"><span class="p">$ </span>'):
                        continue
                    cmd = unesc(re.sub(r"<[^>]+>", "", row)[2:])
                    if cmd in beat_commands or cmd == "rewindagent --version":
                        continue
                    # the README's trailing comment sits on the row before (describes) or after (alternative)
                    near = [unesc(re.sub(r"<[^>]+>", "", rows[j])) for j in (i - 1, i + 1)
                            if 0 <= j < len(rows) and 'class="c"' in rows[j]]
                    ok = cmd in readme_lines or any(ln.startswith(cmd) and ln.endswith(c) for ln in readme_lines for c in near)
                    self.assertTrue(ok, "%s: command not in README: %r" % (p, cmd))
        # the one output line not from the session is the version line, and it is what the binary prints
        self.assertIn("rewindagent %s" % rewindagent.__version__, text_of("docs/index.html"))

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
        # the "no network connections" answer is a test, not a sentence
        for name in sorted(os.listdir(SRC)):
            if name.endswith(".py"):
                with open(os.path.join(SRC, name), encoding="utf-8") as fh:
                    self.assertIsNone(NETWORK.search(fh.read()), name)
        self.assertIn("no network connections", text_of("index.html"))

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
