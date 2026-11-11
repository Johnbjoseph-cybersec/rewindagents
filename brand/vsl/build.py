"""Render the VSL scripts and captions (task RB4a) from brand/vsl/beats.json, the single source of truth.

  python3 brand/vsl/build.py            -> writes brand/vsl/<name>.md and brand/vsl/<name>.srt per video
  python3 brand/vsl/build.py check      -> prints the timing and word-rate table, exit 1 on a violation

The scripts and captions keep the {site_url} and {repo_url} placeholders: the product's address lives in
brand/site/config.json only (tests/test_site.py) and is substituted when the videos are rendered, so a bought
domain is a one-line change there and a re-render, never a rewrite. Stdlib only. tests/test_vsl.py rebuilds the
outputs and fails if the committed files differ, and pins every command, output line and number on screen to
README.md and to brand/demo/manifest.json (the recorded session behind the demo GIF).
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BRAND = os.path.dirname(HERE)
ROOT = os.path.dirname(BRAND)

WORDS_PER_SECOND = 2.6  # ceiling for narration; the voice's pace is measured at render time, this keeps a margin
MIN_BEAT_MS, MAX_BEAT_MS = 1500, 9000
CAPTION_CHARS = 42  # one caption line
CAPTION_LINES = 2
PLACEHOLDERS = ("{site_url}", "{repo_url}")
PROMISE = "Ctrl+Z for AI coding agents: record, replay, rewind."  # BRAND.md "One-line promise", verbatim
CREDIT = "made by John B Joseph"
END_CARD = ["rewindagent", PROMISE, "{site_url}", CREDIT]


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def beats():
    return json.loads(read("brand", "vsl", "beats.json"))


def words(text):
    return [w for w in re.split(r"\s+", text.strip()) if w]


def srt_time(ms):
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def wrap_caption(text, width=CAPTION_CHARS):
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


def chunk_lines(voice):
    """Caption chunks of at most CAPTION_LINES lines, cut at sentence ends: whole sentences are packed into a
    cue while they fit, and only a sentence longer than one cue is cut inside (review round 1 of RB4b: a cue
    that ends mid-sentence leaves an orphan like "copies." on screen for a fraction of a second)."""
    chunks, cur = [], []
    for sentence in re.split(r"(?<=[.?!])\s+", voice):
        if cur and len(wrap_caption(" ".join(cur + [sentence]))) <= CAPTION_LINES:
            cur.append(sentence)
            continue
        if cur:
            chunks.append(wrap_caption(" ".join(cur)))
        lines = wrap_caption(sentence)
        while len(lines) > CAPTION_LINES:
            chunks.append(lines[:CAPTION_LINES])
            lines = wrap_caption(" ".join(lines[CAPTION_LINES:]))
        cur = [" ".join(lines)]
    if cur:
        chunks.append(wrap_caption(" ".join(cur)))
    return chunks


def cues(video):
    """One or more caption cues per spoken beat (chunk_lines), sharing the beat's time in proportion to their
    word count. Silent beats get no cue."""
    out, t = [], 0
    for b in video["beats"]:
        voice = b["voice"].strip()
        if voice:
            chunks = chunk_lines(voice)
            counts = [sum(len(words(l)) for l in c) for c in chunks]
            total = sum(counts)
            start = t
            for i, (chunk, n) in enumerate(zip(chunks, counts)):
                end = t + b["ms"] if i == len(chunks) - 1 else start + round(b["ms"] * n / total)
                out.append((start, end, chunk))
                start = end
        t += b["ms"]
    return out


def srt(video):
    parts = []
    for i, (start, end, lines) in enumerate(cues(video), 1):
        parts.append("%d\n%s --> %s\n%s\n" % (i, srt_time(start), srt_time(end), "\n".join(lines)))
    return "\n".join(parts)


def script_md(video):
    total = sum(b["ms"] for b in video["beats"])
    n_words = sum(len(words(b["voice"])) for b in video["beats"])
    out = [
        "# %s: %s" % (video["name"], video["title"]),
        "",
        "Aspect %s. %d beats, %s s of %s s allowed, %d spoken words. Rendered from beats.json by build.py; "
        "edit beats.json, not this file." % (video["aspect"], len(video["beats"]), fmt_s(total),
                                               fmt_s(video["max_ms"]), n_words),
        "",
        "`{site_url}` and `{repo_url}` are substituted from brand/site/config.json when the video is rendered. "
        "Every command and every output line on screen is one the README or the recorded demo session "
        "(brand/demo/manifest.json) actually has; tests/test_vsl.py checks each one.",
        "",
        "| # | Time | Voice | On screen | Visual |",
        "|---|---|---|---|---|",
    ]
    t = 0
    for b in video["beats"]:
        screen = "<br>".join(cell(s) for s in b["screen"]) or ""
        cites = (" Cites: " + ", ".join("`%s`" % c for c in b["cites"])) if b["cites"] else ""
        out.append("| %s | %s-%s | %s | %s | %s%s |" % (
            b["id"], fmt_s(t), fmt_s(t + b["ms"]), cell(b["voice"]) or "(silent)", screen, cell(b["visual"]), cites))
        t += b["ms"]
    out += ["", "## Narration only", ""]
    for b in video["beats"]:
        if b["voice"].strip():
            out.append(b["voice"].strip())
            out.append("")
    out.append(CREDIT)
    return "\n".join(out) + "\n"


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
    """Timing and rate rules every beat must meet; the writer's contract (also enforced by tests/test_vsl.py)."""
    bad = []
    for v in beats()["videos"]:
        total = sum(b["ms"] for b in v["beats"])
        if total > v["max_ms"]:
            bad.append("%s runs %d ms, allowed %d" % (v["name"], total, v["max_ms"]))
        if total < 0.85 * v["max_ms"]:
            bad.append("%s runs %d ms, under 85%% of %d" % (v["name"], total, v["max_ms"]))
        for b in v["beats"]:
            if not MIN_BEAT_MS <= b["ms"] <= MAX_BEAT_MS:
                bad.append("%s %s: %d ms beat" % (v["name"], b["id"], b["ms"]))
            n = len(words(b["voice"]))
            if n > b["ms"] / 1000 * WORDS_PER_SECOND:
                bad.append("%s %s: %d words in %d ms (%.2f/s)" % (v["name"], b["id"], n, b["ms"], n / (b["ms"] / 1000)))
        if v["beats"][-1]["screen"] != END_CARD:
            bad.append("%s: last beat is not the end card" % v["name"])
    return bad


def main(argv):
    if argv[:1] == ["check"]:
        for v in beats()["videos"]:
            total = sum(b["ms"] for b in v["beats"])
            n = sum(len(words(b["voice"])) for b in v["beats"])
            print("%-18s %s  %5d ms of %5d  %3d words  %.2f words/s  %d beats" % (
                v["name"], v["aspect"], total, v["max_ms"], n, n / (total / 1000), len(v["beats"])))
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
