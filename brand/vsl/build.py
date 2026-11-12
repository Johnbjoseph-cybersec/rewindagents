"""Render the VSL scripts and captions (task RB4a, remade 2026-11-12) from brand/vsl/beats.json, the single source of truth.

  python3 brand/vsl/build.py            -> writes brand/vsl/<name>.md and brand/vsl/<name>.srt per video
  python3 brand/vsl/build.py fit        -> sets every beat's ms from reading time (then build, then render.py)
  python3 brand/vsl/build.py check      -> prints the timing table, exit 1 on a violation

The films have no voice (John, 2026-11-12: "remove the voice over altogether, explain through text, make it clear").
Each beat is one card: its `text` is the line the viewer reads, set big on screen by render.py, and the same line is
the caption cue in the .srt (the site's film ruler reads its chapters from it). A card stays up long enough to be
read twice: READ_MS_PER_WORD a word plus READ_MS_BASE, at least MIN_BEAT_MS, plus the card's own `proof_ms` (the
time its terminal lines or diagram need to animate). fit writes exactly that; check holds every card to it.

The scripts and captions keep the {site_url} and {repo_url} placeholders: the product's address lives in
brand/site/config.json only (tests/test_site.py) and is substituted when the videos are rendered, so a bought
domain is a one-line change there and a re-render, never a rewrite. Stdlib only. tests/test_vsl.py rebuilds the
outputs and fails if the committed files differ, and pins every command, output line and number on screen to
README.md and to brand/demo/manifest.json (the recorded session behind the demo GIF).

A video with "new_terms" (the 90 s film) also gets a teaching script in its .md, in the studio's NARRATOR: /
[OST: ...] / [PAUSE ...] format under the blueprint headings of each card's "section" (the card text stands where
narration would): that is the file the explainer-teaching gate reads (teach_lint.py brand/vsl/vsl-90s.md).
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BRAND = os.path.dirname(HERE)
ROOT = os.path.dirname(BRAND)

READ_MS_PER_WORD = 350  # John's brief: about 0.35 s a word + 0.8 s, so a card can be read twice
READ_MS_BASE = 800
MIN_BEAT_MS, MAX_BEAT_MS = 2000, 9000
MAX_CARD_WORDS = 11     # one idea per card, about ten words a line, at most two lines on screen
CAPTION_CHARS = 42  # one caption line
CAPTION_LINES = 2
PLACEHOLDERS = ("{site_url}", "{repo_url}")
PROMISE = "Ctrl+Z for AI coding agents: record, replay, rewind."  # BRAND.md "One-line promise", verbatim
CREDIT = "made by John B Joseph"
END_CARD = ["rewindagents", PROMISE, "{site_url}", CREDIT]


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def beats():
    return json.loads(read("brand", "vsl", "beats.json"))


def words(text):
    return [w for w in re.split(r"\s+", text.strip()) if w]


def reading_ms(beat):
    """How long a card must stay up: reading time of its text (twice), plus its proof animation."""
    return max(MIN_BEAT_MS, READ_MS_PER_WORD * len(words(beat["text"])) + READ_MS_BASE) + beat.get("proof_ms", 0)


def srt_time(ms):
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


CONJUNCTIONS = ("and", "but", "or", "so", "because", "then", "unlike")
CAPTION_MIN_WORDS = 3   # a second caption line carries at least this many words (review-textcut.json fix 9)


def wrap_caption(text, width=CAPTION_CHARS):
    """Caption lines, broken by phrase (review-textcut.json fix 9: no 1-2 word second line). A cue that fits one line
    stays on one line. Otherwise the break goes, in order of preference, after punctuation, then before a
    conjunction, then wherever the two lines are most even; each line fits `width` and each carries at least
    CAPTION_MIN_WORDS words. Only when no such break exists does the greedy wrap below decide."""
    ws = words(text)
    if len(text.strip()) <= width:
        return [" ".join(ws)]
    best = None
    for i in range(CAPTION_MIN_WORDS, len(ws) - CAPTION_MIN_WORDS + 1):
        a, b = " ".join(ws[:i]), " ".join(ws[i:])
        if len(a) > width or len(b) > width:
            continue
        rank = 0 if re.search(r"[.?!:;,]$", ws[i - 1]) else (1 if ws[i].lower() in CONJUNCTIONS else 2)
        key = (rank, abs(len(a) - len(b)))
        if best is None or key < best[0]:
            best = (key, [a, b])
    if best:
        return best[1]
    return greedy_caption(text, width)


def greedy_caption(text, width=CAPTION_CHARS):
    """Greedy wrap into lines of at most `width` characters (a word longer than that stands alone)."""
    lines, cur = [], ""
    for w in words(text):
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= width:
            cur += " " + w
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def cues(video):
    """One caption cue per card: the card's text, up for the card's whole time."""
    out, t = [], 0
    for b in video["beats"]:
        if b["text"].strip():
            out.append((t, t + b["ms"], wrap_caption(b["text"])))
        t += b["ms"]
    return out


def srt(video):
    parts = []
    for i, (start, end, lines) in enumerate(cues(video), 1):
        parts.append("%d\n%s --> %s\n%s\n" % (i, srt_time(start), srt_time(end), "\n".join(lines)))
    return "\n".join(parts)


def script_md(video):
    total = sum(b["ms"] for b in video["beats"])
    n_words = sum(len(words(b["text"])) for b in video["beats"])
    out = [
        "# %s: %s" % (video["name"], video["title"]),
        "",
        "Aspect %s. %d cards, %s s of %s s allowed, %d words on the cards. No voice: the cards carry the words, over "
        "the music bed. Rendered from beats.json by build.py; edit beats.json, not this file." % (
            video["aspect"], len(video["beats"]), fmt_s(total), fmt_s(video["max_ms"]), n_words),
        "",
        "`{site_url}` and `{repo_url}` are substituted from brand/site/config.json when the video is rendered. "
        "Every command and every output line on screen is one the README or the recorded demo session "
        "(brand/demo/manifest.json) actually has; tests/test_vsl.py checks each one.",
        "",
        "| # | Time | Card | Proof on screen | Motion |",
        "|---|---|---|---|---|",
    ]
    t = 0
    for b in video["beats"]:
        screen = "<br>".join(cell(s) for s in b["screen"]) or ""
        cites = (" Cites: " + ", ".join("`%s`" % c for c in b["cites"])) if b["cites"] else ""
        card = cell(b["text"]).replace(cell(b["accent"]), "**%s**" % cell(b["accent"]), 1) if b.get("accent") else cell(b["text"])
        out.append("| %s | %s-%s | %s | %s | %s%s |" % (
            b["id"], fmt_s(t), fmt_s(t + b["ms"]), card, screen, cell(b["visual"]), cites))
        t += b["ms"]
    if video.get("new_terms"):
        out += teaching_script(video)
    out += ["", "## Cards only", ""]
    for b in video["beats"]:
        out.append(b["text"].strip())
        out.append("")
    out.append(CREDIT)
    return "\n".join(out) + "\n"


def teaching_script(video):
    """The card text in the studio script format under the blueprint headings, for teach_lint: one NARRATOR: line
    per card (the text stands where narration would), the card's proof lines as [OST: ...], and a [PAUSE] block
    where a card holds for the viewer to decide."""
    out = ["", "## Teaching script", "",
           "The input of the explainer-teaching gate: `teach_lint.py brand/vsl/%s.md`. There is no voice; each "
           "NARRATOR: line is a card's on-screen text." % video["name"], "",
           "- New terms: %s" % ", ".join(video["new_terms"])]
    section = None
    for b in video["beats"]:
        if b.get("section") != section:
            section = b.get("section")
            out += ["", "## %s" % section]
        for s in b["screen"]:
            out.append("[OST: %s]" % s.strip())
        out.append("NARRATOR: %s" % b["text"].strip())
        if b.get("pause"):
            out += ["[PAUSE %s.%s]" % (video["name"], b["id"]), "- Line: %s" % b["text"].strip(),
                    "- Hold: %s s" % fmt_s(b["ms"]), "- Answer: %s" % b["pause"]["answer"]]
    return out


def cell(text):
    return text.replace("|", "\\|").replace("\n", " ")


def fmt_s(ms):
    s = ms / 1000
    return ("%.1f" % s).rstrip("0").rstrip(".")


def outputs():
    """{relative path under brand/vsl: text} for every video."""
    out = {}
    for v in beats()["videos"]:
        out[v["name"] + ".md"] = script_md(v)
        out[v["name"] + ".srt"] = srt(v)
    return out


def violations():
    """Timing and reading rules every card must meet (also enforced by tests/test_vsl.py)."""
    bad = []
    for v in beats()["videos"]:
        total = sum(b["ms"] for b in v["beats"])
        if total > v["max_ms"]:
            bad.append("%s runs %d ms, allowed %d" % (v["name"], total, v["max_ms"]))
        if total < 0.85 * v["max_ms"]:
            bad.append("%s runs %d ms, under 85%% of %d" % (v["name"], total, v["max_ms"]))
        for b in v["beats"]:
            if not MIN_BEAT_MS <= b["ms"] <= MAX_BEAT_MS:
                bad.append("%s %s: %d ms card" % (v["name"], b["id"], b["ms"]))
            if b["ms"] < reading_ms(b):
                bad.append("%s %s: %d ms, reading needs %d" % (v["name"], b["id"], b["ms"], reading_ms(b)))
            if not b["text"].strip():
                bad.append("%s %s: a card with no text" % (v["name"], b["id"]))
            if len(words(b["text"])) > MAX_CARD_WORDS:
                bad.append("%s %s: %d words on one card" % (v["name"], b["id"], len(words(b["text"]))))
            if b.get("accent") and b["accent"] not in b["text"]:
                bad.append("%s %s: accent %r is not in the text" % (v["name"], b["id"], b["accent"]))
        if v["beats"][-1]["screen"] != END_CARD:
            bad.append("%s: last beat is not the end card" % v["name"])
    return bad


def fit():
    data = beats()
    for v in data["videos"]:
        for b in v["beats"]:
            b["ms"] = reading_ms(b)
    with open(os.path.join(HERE, "beats.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def main(argv):
    if argv[:1] == ["fit"]:
        fit()
        argv = ["check"]
    if argv[:1] == ["check"]:
        for v in beats()["videos"]:
            total = sum(b["ms"] for b in v["beats"])
            n = sum(len(words(b["text"])) for b in v["beats"])
            print("%-18s %s  %5d ms of %5d  %3d words  %d cards" % (v["name"], v["aspect"], total, v["max_ms"], n,
                                                                   len(v["beats"])))
        bad = violations()
        for line in bad:
            print("VIOLATION", line)
        return 1 if bad else 0
    for rel, text in outputs().items():
        with open(os.path.join(HERE, rel), "w", encoding="utf-8") as f:
            f.write(text)
        print("wrote brand/vsl/%s" % rel)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
