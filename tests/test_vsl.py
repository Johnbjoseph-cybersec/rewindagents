"""brand/vsl (RB4a): the three VSL scripts and their captions are rendered from beats.json; every command on
screen is a README command or one of the four commands of the recorded demo session; every terminal line on
screen is a line that session printed; every number spoken or shown comes from the code or that session; the
words BRAND.md never uses are absent; nothing is blocked, judged or stopped except in a sentence that says so;
planned things are called planned; the product's address is a placeholder, never typed; narration fits the time;
the end card is the end card; the claim review is someone else's. Stdlib only."""
import hashlib
import importlib.util
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VSL = os.path.join(ROOT, "brand", "vsl")
MANIFEST = os.path.join(ROOT, "brand", "demo", "manifest.json")
sys.path.insert(0, os.path.join(ROOT, "src"))

from rewindagent import __version__  # noqa: E402
from rewindagent.bashscan import MAX_SCAN_FILES  # noqa: E402
from rewindagent.export import MAX_DIFF_BYTES, MAX_DIFF_LINES  # noqa: E402
from rewindagent.hook import MAX_CHECKPOINT_BYTES, MAX_RESULT_CHARS  # noqa: E402
from rewindagent.sessions import SHOW_FILES  # noqa: E402

VIDEOS = {"vsl-90s": ("16:9", 90000), "vsl-30s": ("16:9", 30000), "vsl-15s-vertical": ("9:16", 15000)}
# BRAND.md "Words we never use" and "Don't", plus the pitch words it rules out
NEVER = ["revolutionary", "seamless", "unleash", "ai-powered", "game-changer", "game changer", "secure",
         "protect", "protects", "protected", "defend", "defends", "testimonial", "guardrail", "guardrails",
         "firewall", "gateway", "policy", "enforcement", "compliance", "governance", "red team", "jailbreak",
         "prompt injection", "monitoring"]
# allowed only in a sentence that negates them: "It never blocks, judges or stops an action."
ONLY_NEGATED = ["block", "blocks", "blocking", "judge", "judges", "stop", "stops", "security"]
HOST = re.compile(r"[\w-]+\.(github\.io|com|dev|io|app|org|net|sh|co|ai)\b", re.I)
EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")
# a screen line that looks like a command of ours must be one the README or the demo session has
COMMAND = re.compile(r"^(rewindagent|python3 -m rewindagent|pipx|pip|git|echo)\b")
# a screen line that looks like terminal output must be a line the recorded session printed
OUTPUT = re.compile(r"^\s*(\d+\s+(Read|Edit|Write|Bash|MultiEdit|NotebookEdit)\b|restore\s|session \w+: rewind|"
                    r"this rewind is step|[ MD?]{2,3}\S)")


def load_build():
    spec = importlib.util.spec_from_file_location("vsl_build", os.path.join(VSL, "build.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def beats():
    return json.loads(read(os.path.join(VSL, "beats.json")))


def manifest():
    return json.loads(read(MANIFEST))


def readme_commands():
    """Every command line of every ```sh block in README.md, without its trailing comment."""
    out = set()
    for block in re.findall(r"```sh\n(.*?)```", read(os.path.join(ROOT, "README.md")), re.S):
        for line in block.split("\n"):
            cmd = re.sub(r"\s+#.*$", "", line).strip()
            if cmd:
                out.add(cmd)
    return out


def demo_commands():
    return {b["command"] for b in manifest()["beats"]}


def demo_output_lines():
    out = set()
    for b in manifest()["beats"]:
        for line in b["output"].split("\n"):
            if line.strip():
                out.add(line.rstrip())
    return out


def allowed_numbers():
    """Every number the scripts may state: the package's limits, the version, and what the demo session printed."""
    nums = {MAX_CHECKPOINT_BYTES // (1024 * 1024), MAX_SCAN_FILES, MAX_RESULT_CHARS, MAX_DIFF_BYTES // 1024,
            MAX_DIFF_LINES, SHOW_FILES,
            0, 1, 2, 3,  # exit codes, "one command", "the last two steps", three agents
            2004}  # Apache License 2.0, January 2004
    allowed = set()
    for n in nums:
        allowed.add(str(n))
        allowed.add("{:,}".format(n))
    for line in demo_output_lines() | demo_commands():
        allowed.update(re.findall(r"\d+", line))
    return allowed


def text_fields(video):
    for b in video["beats"]:
        yield b["id"], "voice", b["voice"]
        for s in b["screen"]:
            yield b["id"], "screen", s
        yield b["id"], "visual", b["visual"]


def sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+|\n", text) if s.strip()]


def hosts(text):
    return [m.group(0) for m in HOST.finditer(text) if "example" not in m.group(0).lower()]


class TestVsl(unittest.TestCase):
    def test_three_videos_with_the_required_shape(self):
        data = beats()
        self.assertNotIn(data["written_by"], ("", "fire", "builder"))
        names = [v["name"] for v in data["videos"]]
        self.assertEqual(sorted(names), sorted(VIDEOS))
        for v in data["videos"]:
            aspect, max_ms = VIDEOS[v["name"]]
            self.assertEqual(v["aspect"], aspect)
            self.assertEqual(v["max_ms"], max_ms)
            self.assertTrue(v["title"].strip())
            ids = [b["id"] for b in v["beats"]]
            self.assertEqual(ids, ["b%02d" % i for i in range(1, len(ids) + 1)], v["name"])
            for b in v["beats"]:
                self.assertEqual(set(b), {"id", "ms", "voice", "screen", "visual", "cites"}, b["id"])
                self.assertIsInstance(b["ms"], int)
                self.assertIsInstance(b["screen"], list)
                self.assertIsInstance(b["cites"], list)
                self.assertTrue(b["visual"].strip(), "%s %s has no visual" % (v["name"], b["id"]))
            # the end card is fixed text (test_end_card_and_placeholders) and wraps on the vertical frame
            printed, cols = demo_output_lines(), manifest()["cols"]
            for b in v["beats"][:-1]:
                width = 32 if v["aspect"] == "9:16" else 60
                for s in b["screen"]:
                    # a line the demo session printed may run to the demo terminal's width on a 16:9 frame
                    limit = cols if (v["aspect"] == "16:9" and s.rstrip() in printed) else width
                    self.assertLessEqual(len(s), limit, "%s %s screen line too long: %r" % (v["name"], b["id"], s))

    def test_timing_and_word_rate(self):
        self.assertEqual(load_build().violations(), [])

    def test_committed_scripts_and_captions_are_the_build_output(self):
        b = load_build()
        for rel, text in b.outputs().items():
            self.assertEqual(read(os.path.join(VSL, rel)), text,
                             "%s differs from build.py's output: run python3 brand/vsl/build.py" % rel)
        for name in VIDEOS:
            for ext in (".md", ".srt"):
                self.assertTrue(os.path.isfile(os.path.join(VSL, name + ext)), name + ext)

    def test_every_command_on_screen_is_a_readme_or_demo_command(self):
        ok = readme_commands() | demo_commands()
        for v in beats()["videos"]:
            for b in v["beats"][:-1]:  # the end card names the product, it is not a command
                for s in b["screen"]:
                    if COMMAND.match(s.strip()):
                        self.assertIn(s.strip(), ok, "%s %s shows a command neither the README nor the demo has: %r"
                                      % (v["name"], b["id"], s))

    def test_every_terminal_line_on_screen_is_one_the_demo_session_printed(self):
        printed = demo_output_lines()
        for v in beats()["videos"]:
            for b in v["beats"]:
                for s in b["screen"]:
                    if OUTPUT.match(s) and not COMMAND.match(s.strip()):
                        self.assertIn(s.rstrip(), printed, "%s %s shows output the session did not print: %r"
                                      % (v["name"], b["id"], s))

    def test_each_video_shows_the_real_wreck_and_the_real_rewind(self):
        printed = demo_output_lines()
        for v in beats()["videos"]:
            screen = [s for _, f, s in text_fields(v) if f == "screen"]
            self.assertIn("rewindagent rewind 12", screen, "%s never shows the rewind command" % v["name"])
            self.assertTrue(any(s.rstrip() in printed for s in screen), "%s shows no real output" % v["name"])
        long = next(v for v in beats()["videos"] if v["name"] == "vsl-90s")
        texts = " ".join(t for _, _, t in text_fields(long))
        for phrase in ("rewindagent replay", "rm -rf tests", "restore  tests/test_config.py", "Apache-2.0",
                       "planned", "hash", "not yet in a live session", "undo it with"):
            self.assertIn(phrase, texts, "vsl-90s does not say %r" % phrase)

    def test_numbers_come_from_the_code_or_the_session(self):
        allowed = allowed_numbers()
        quoted = demo_output_lines() | demo_commands() | readme_commands()
        for v in beats()["videos"]:
            for bid, field, text in text_fields(v):
                if field == "visual":
                    continue
                t = text
                for line in quoted:  # a command or output line shown on screen is quoted, not claimed
                    t = t.replace(line.strip(), " ")
                t = t.replace(__version__, " ").replace("3.10", " ").replace("SHA-256", " ").replace("Apache-2.0", " ")
                t = re.sub(r"\{site_url\}|\{repo_url\}|\b9:16\b|\b16:9\b|Ctrl\+Z", " ", t)
                for n in re.findall(r"\d[\d,]*(?:\.\d+)?", t):
                    self.assertIn(n, allowed, "%s %s %s states the number %s: %r" % (v["name"], bid, field, n, text))

    def test_words_never_used_no_address_no_price_no_emoji(self):
        for v in beats()["videos"]:
            for bid, field, text in text_fields(v):
                low = text.lower()
                for w in NEVER:
                    self.assertNotRegex(low, r"\b%s\b" % re.escape(w), "%s %s %s says %r" % (v["name"], bid, field, w))
                for w in ONLY_NEGATED:
                    for s in sentences(low):
                        if re.search(r"\b%s\b" % w, s):
                            self.assertRegex(s, r"\b(not|never|no|nothing)\b",
                                             "%s %s %s: %r without a negation" % (v["name"], bid, field, s))
                self.assertEqual(hosts(text), [], "%s %s %s types an address: %s" % (v["name"], bid, field, text))
                self.assertNotRegex(text, r"[$€£]\s?\d|\d+\s?(/|per )(mo|month|year|seat)", "price")
                self.assertNotIn(chr(0xA7), text)
                self.assertIsNone(EMOJI.search(text), text)
                self.assertNotIn("\u2014", text, "em dash")
                self.assertNotIn("!", text, "%s %s %s: no exclamation marks" % (v["name"], bid, field))
        for rel in os.listdir(VSL):
            if rel.endswith((".md", ".srt", ".json")):
                self.assertEqual(hosts(read(os.path.join(VSL, rel))), [], rel)

    def test_planned_things_are_called_planned(self):
        for v in beats()["videos"]:
            for bid, field, text in text_fields(v):
                if field == "visual":
                    continue
                low = text.lower()
                if re.search(r"\b(paid|cloud|pro tier|sync|retention|shareable)\b", low):
                    self.assertIn("planned", low, "%s %s %s: paid tier without 'planned': %r" % (v["name"], bid, field, text))
                    self.assertNotRegex(low, r"\b(buy|price|pricing|subscribe)\b", text)
                if "pypi" in low:
                    self.assertRegex(low, r"\b(not|yet|no)\b", "%s %s %s: PyPI without the status: %r" % (v["name"], bid, field, text))
                if re.search(r"\b(codex|cursor)\b", low) and field == "voice":
                    self.assertNotRegex(low, r"\b(has run|have run|live session[s]? (has|have)|runs in)\b",
                                        "%s %s claims a live Codex or Cursor run: %r" % (v["name"], bid, text))

    def test_end_card_and_placeholders(self):
        b = load_build()
        for v in beats()["videos"]:
            self.assertEqual(v["beats"][-1]["screen"], b.END_CARD, v["name"])
            credits = [s for _, f, s in text_fields(v) if f == "screen" and b.CREDIT in s]
            self.assertEqual(len(credits), 1, "%s: the credit line appears %d times" % (v["name"], len(credits)))
        brand = read(os.path.join(ROOT, "brand", "BRAND.md"))
        self.assertIn(b.PROMISE, brand)
        self.assertIn("Credit line, used exactly in footers: %s" % b.CREDIT, brand)
        for name in VIDEOS:
            self.assertIn("{site_url}", read(os.path.join(VSL, name + ".md")))

    def test_captions_cover_every_spoken_word_in_order_and_fit_two_lines(self):
        b = load_build()
        for v in beats()["videos"]:
            spoken = " ".join(" ".join(b.words(x["voice"])) for x in v["beats"] if x["voice"].strip())
            text = read(os.path.join(VSL, v["name"] + ".srt"))
            cues = re.findall(r"(\d+)\n(\d\d:\d\d:\d\d,\d{3}) --> (\d\d:\d\d:\d\d,\d{3})\n((?:.+\n?)+?)(?:\n|\Z)", text)
            self.assertTrue(cues, v["name"])
            self.assertEqual([int(c[0]) for c in cues], list(range(1, len(cues) + 1)))
            captioned = " ".join(" ".join(c[3].split()) for c in cues)
            self.assertEqual(captioned, spoken, v["name"])
            last_end = 0
            for _, start, end, body in cues:
                lines = body.strip("\n").split("\n")
                self.assertLessEqual(len(lines), b.CAPTION_LINES, body)
                for line in lines:
                    self.assertLessEqual(len(line), b.CAPTION_CHARS, line)
                s, e = (int(x[:2]) * 3600000 + int(x[3:5]) * 60000 + int(x[6:8]) * 1000 + int(x[9:]) for x in (start, end))
                self.assertGreaterEqual(s, last_end)
                self.assertGreater(e, s)
                last_end = e
            self.assertLessEqual(last_end, VIDEOS[v["name"]][1])

    def test_claim_review_is_independent_and_nothing_blocked_remains(self):
        r = json.loads(read(os.path.join(VSL, "claims.json")))
        self.assertNotIn(r["reviewer"], ("", "fire", "builder", beats()["written_by"]))
        self.assertTrue(r["claims"])
        for c in r["claims"]:
            self.assertIn(c["verdict"], ("CLEAR", "UNVERIFIED", "BLOCK"))
            self.assertNotEqual(c["verdict"], "BLOCK", "a blocked claim is still in the scripts: %r" % c)
            self.assertTrue(c["source"].strip(), c)
        self.assertEqual(r["blocked_in_scripts"], 0)
        self.assertEqual(r["beats_sha256"], hashlib.sha256(read(os.path.join(VSL, "beats.json")).encode("utf-8")).hexdigest(),
                         "beats.json changed after the claim review: run claim-verifier again")


if __name__ == "__main__":
    unittest.main()
