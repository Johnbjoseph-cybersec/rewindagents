"""brand/launch (RB5): the launch kit is the seven files BRAND_KIT.md names, each with the sections a poster needs;
the product's address is a placeholder filled from brand/site/config.json by brand/launch/fill.py, never typed;
every command in the filled text is a README command or one of the recorded demo session's; every number is a
limit of the package, a number that session printed, or a platform limit named here; the words BRAND.md never
uses are absent; planned things are called planned and the Codex and Cursor status is said; the lengths fit the
platforms; the claim review is someone else's and pinned to the files it read. Stdlib only."""
import hashlib
import importlib.util
import io
import json
import os
import re
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAUNCH = os.path.join(ROOT, "brand", "launch")

# BRAND_KIT.md items 6 and 8, and the sections each file must have
FILES = {
    "producthunt.md": ["Name", "Tagline", "Description", "Topics", "Links", "Maker comment", "Gallery"],
    "show-hn.md": ["Title", "URL", "Text"],
    "x-thread.md": ["Post 1", "Post 2", "Post 3"],
    "reddit.md": ["Subreddits", "Title", "Body"],
    "linkedin-for-jj.md": ["Facts JJ can use", "Draft post", "Do not"],
    "waitlist-welcome.md": ["Subject", "Body"],
    "onboarding-3-emails.md": ["Email 1", "Email 2", "Email 3"],
}
# platform limits the kit is written to; the numbers may appear in the instructions around the copy.
# Product Hunt's help page (read 2026-11-12, claim review): tagline up to 60, description up to 500, gallery
# 1270x760 recommended. 260 is our cap, the length a listing preview shows. HN publishes no title limit; 80 is the
# figure reported by others, kept as our cap (claim review: UNVERIFIED, check the submit form on the day).
PH_TAGLINE, PH_DESCRIPTION = 60, 260
PH_GALLERY = (1270, 760)
HN_TITLE = 80
X_POST, X_URL = 280, 23  # X counts every link as 23 characters
SUBJECT = 60  # our cap, so a subject line is not cut in an inbox list


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


vsl = load("launch_vsl_helpers", os.path.join(ROOT, "tests", "test_vsl.py"))
fill = load("launch_fill", os.path.join(LAUNCH, "fill.py"))


def read(name):
    with open(os.path.join(LAUNCH, name), encoding="utf-8") as f:
        return f.read()


def sections(text):
    """{heading: body} for every '## ' heading."""
    out, cur = {}, None
    for line in text.split("\n"):
        m = re.match(r"^## (.+)$", line)
        if m:
            cur = m.group(1).strip()
            out[cur] = []
        elif cur is not None:
            out[cur].append(line)
    return {k: "\n".join(v).strip() for k, v in out.items()}


def paragraphs(text):
    return [p for p in re.split(r"\n\s*\n", text) if p.strip()]


def commands(text):
    """Every line of every ```sh block, and every inline code span that starts like one of our commands."""
    out = []
    for block in re.findall(r"```sh\n(.*?)```", text, re.S):
        out += [l.strip() for l in block.split("\n") if l.strip()]
    prose = re.sub(r"```.*?```", " ", text, flags=re.S)
    out += [c.strip() for c in re.findall(r"`([^`\n]+)`", prose) if vsl.COMMAND.match(c.strip())]
    return out


def x_length(post):
    return len(re.sub(r"\{(site_url|repo_url|waitlist_url)\}", "x" * X_URL, post))


class TestLaunchKit(unittest.TestCase):
    def test_every_file_with_its_sections(self):
        for name, heads in FILES.items():
            got = sections(read(name))
            for h in heads:
                self.assertIn(h, got, "%s has no '## %s'" % (name, h))
                self.assertTrue(got[h], "%s: '## %s' is empty" % (name, h))

    def test_fill_replaces_every_placeholder_from_config(self):
        cfg = fill.config()
        for name in FILES:
            raw = read(name)
            self.assertIn("{repo_url}", raw, "%s does not link the repository" % name)
            out = fill.fill(raw)
            self.assertNotRegex(out, r"\{[a-z_]+\}", name)
            for key in fill.KEYS:
                if "{%s}" % key in raw:
                    self.assertIn(cfg[key], out)
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(fill.main([os.path.join(LAUNCH, name)]), 0)
            self.assertEqual(buf.getvalue(), out)
        with self.assertRaises(ValueError):
            fill.fill("{checkout_url}", cfg)  # null until a Polar product exists
        with self.assertRaises(ValueError):
            fill.fill("{homepage}", cfg)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "bad.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write("see {nowhere}\n")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(fill.main([p]), 1)

    def test_no_address_is_typed(self):
        # claims.json cites its sources by URL; a product hostname there is still caught by tests/test_site.py
        for name in list(FILES) + ["fill.py"]:
            self.assertEqual(vsl.hosts(read(name)), [], name)

    def test_every_command_is_a_readme_or_demo_command(self):
        ok = vsl.readme_commands() | vsl.demo_commands()
        for name in FILES:
            for c in commands(fill.fill(read(name))):
                self.assertIn(c, ok, "%s shows a command neither the README nor the demo has: %r" % (name, c))

    def test_numbers_come_from_the_code_the_session_or_a_platform_limit(self):
        allowed = vsl.allowed_numbers() | {str(n) for n in (PH_TAGLINE, PH_DESCRIPTION, HN_TITLE, X_POST, X_URL, SUBJECT)
                                           + PH_GALLERY}
        quoted = vsl.readme_commands() | vsl.demo_commands() | vsl.demo_output_lines()
        for name in FILES:
            t = read(name)
            for line in sorted(quoted, key=len, reverse=True):  # a quoted command is quoted, not claimed
                t = t.replace(line.strip(), " ")
            t = re.sub(r"\{[a-z_]+\}|SHA-256|Apache-2\.0|Python 3\.10|Ctrl\+Z|ph-\d\.png|RB5b|\b\d{4}-\d\d-\d\d\b", " ", t)
            for n in re.findall(r"\d[\d,]*(?:\.\d+)?", t):
                self.assertIn(n.rstrip(","), allowed, "%s states the number %s" % (name, n))

    def test_words_never_used_and_house_style(self):
        never = vsl.NEVER + ["magic", "never lose", "instant", "bulletproof", "foolproof", "guaranteed"]
        for name in FILES:
            text = read(name)
            low = text.lower()
            for w in never:
                self.assertNotRegex(low, r"\b%s\b" % re.escape(w), "%s says %r" % (name, w))
            for s in vsl.sentences(low):
                for w in vsl.ONLY_NEGATED:
                    if re.search(r"\b%s\b" % w, s):
                        self.assertRegex(s, r"\b(not|never|no|nothing)\b", "%s: %r without a negation" % (name, s))
            self.assertNotRegex(text, r"[$€£]\s?\d|\d+\s?(/|per )(mo|month|year|seat)", "%s: a price" % name)
            self.assertNotIn(chr(0xA7), text)
            self.assertIsNone(vsl.EMOJI.search(text), name)
            self.assertNotIn(chr(0x2014), text, "%s: em dash" % name)
            self.assertNotIn("!", text, "%s: no exclamation marks" % name)

    def test_status_is_said_where_it_matters(self):
        for name in FILES:
            text = read(name)
            for p in paragraphs(text.lower()):
                if re.search(r"\b(paid|cloud|pro tier|sync|retention|shareable)\b", p):
                    self.assertIn("planned", p, "%s: paid tier without 'planned': %r" % (name, p))
                    self.assertNotRegex(p, r"\b(buy|price|pricing|subscribe)\b", "%s: %r" % (name, p))
                if "pypi" in p:
                    self.assertRegex(p, r"\b(not|yet|no)\b", "%s: PyPI without the status: %r" % (name, p))
            if re.search(r"\b(codex|cursor)\b", text, re.I):
                self.assertIn("not yet in a live session", text, "%s names Codex or Cursor without the status" % name)
                for s in vsl.sentences(text.lower()):
                    if re.search(r"\b(codex|cursor)\b", s):
                        self.assertNotRegex(s, r"\b(has run|have run|runs in|in real sessions)\b",
                                            "%s claims a live Codex or Cursor run: %r" % (name, s))

    def test_lengths_fit_the_platforms(self):
        ph = sections(read("producthunt.md"))
        self.assertLessEqual(len(ph["Tagline"]), PH_TAGLINE, ph["Tagline"])
        self.assertLessEqual(len(ph["Description"]), PH_DESCRIPTION, len(ph["Description"]))
        self.assertEqual(ph["Name"], "rewindagent")
        title = sections(read("show-hn.md"))["Title"]
        self.assertTrue(title.startswith("Show HN: rewindagent"), title)
        self.assertLessEqual(len(title), HN_TITLE, title)
        self.assertEqual(sections(read("show-hn.md"))["URL"], "{repo_url}")
        posts = sections(read("x-thread.md"))
        self.assertEqual(list(posts), ["Post %d" % i for i in range(1, len(posts) + 1)])
        for head, post in posts.items():
            self.assertLessEqual(x_length(post), X_POST, "%s is %d characters" % (head, x_length(post)))
            self.assertNotIn("```", post, head)
        self.assertIn("{repo_url}", posts["Post 1"])
        self.assertLessEqual(len(sections(read("reddit.md"))["Title"]), 300)
        subjects = [sections(read("waitlist-welcome.md"))["Subject"]]
        for i in (1, 2, 3):
            body = sections(read("onboarding-3-emails.md"))["Email %d" % i]
            m = re.match(r"Subject: (.+)", body)
            self.assertTrue(m, "Email %d has no Subject line" % i)
            subjects.append(m.group(1))
        for s in subjects:
            self.assertLessEqual(len(s), SUBJECT, s)

    def test_drafts_say_who_posts_and_that_nothing_sends_itself(self):
        jj = read("linkedin-for-jj.md")
        self.assertIn("FIRE never posts to LinkedIn", jj)
        self.assertIn("fire.launch", jj)
        for name in ("waitlist-welcome.md", "onboarding-3-emails.md"):
            self.assertIn("nothing sends", read(name).lower(), name)
        for name in ("producthunt.md", "show-hn.md", "x-thread.md", "reddit.md"):
            self.assertIn("not posted", read(name), name)

    def test_claim_review_is_independent_and_pinned(self):
        r = json.loads(read("claims.json"))
        self.assertNotIn(r["reviewer"], ("", "fire", "builder"))
        self.assertTrue(r["claims"])
        for c in r["claims"]:
            self.assertIn(c["verdict"], ("CLEAR", "UNVERIFIED", "BLOCK"))
            self.assertNotEqual(c["verdict"], "BLOCK", "a blocked claim is still in the kit: %r" % c)
            self.assertTrue(c["source"].strip(), c)
            self.assertIn(c["file"], FILES)
        self.assertEqual(r["blocked_in_kit"], 0)
        h = hashlib.sha256()
        for name in sorted(FILES):
            h.update(read(name).encode("utf-8"))
        self.assertEqual(r["kit_sha256"], h.hexdigest(), "the kit changed after the claim review: run claim-verifier again")


if __name__ == "__main__":
    unittest.main()
