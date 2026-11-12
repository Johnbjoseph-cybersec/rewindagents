"""Render the three VSLs (task RB4b, remade 2026-11-12 as text-led kinetic explainers) from brand/vsl/beats.json:
brand/vsl-90s.mp4, brand/vsl-30s.mp4 and brand/vsl-15s-vertical.mp4, each with its captions beside it
(brand/<name>.srt, a copy of brand/vsl/<name>.srt).

No voice (John, 2026-11-12: "remove the voice over altogether, explain through text, make it clear, very clear, add
motion graphics and good animations and the best transitions in the industry"). Each beat is a card: its line is set
big on paper and builds word by word out of a mask; under it the proof, the real terminal lines of the recorded demo
session (brand/demo/manifest.json) or a diagram. What is on screen comes from beats.json and nowhere else; the
DIRECTION table below says which kind of card each beat is and what moves in it, and when.

Motion, all of it in the brand system (paper and ink, one accent, the step ruler and its playhead):
- the rewind wipe: between scenes the playhead drops from the ruler and scrubs right to left across the frame; the
  new scene is revealed behind it while the old one slides back under it. Time going back is the transition. It
  comes in three weights (WIPES: light within a section, section, story for the two rewinds of the story, slower
  with a longer tape trail); the new card's line starts 170 ms in so it is revealed behind the playhead, and the
  ruler's own playhead hides while the wipe's is on screen, then drops back into place.
- a scene that continues (beats.json "cont") keeps its canvas: the old line accelerates up out of its mask and
  fades, the new one starts rising before it has gone, so no frame shows an empty slot or a leftover descender.
- masked word builds for every line of text; terminal commands type, output lines rise out of their row.
- the step ruler at the top is one persistent spine: ticks grow, the playhead scrubs back when the story rewinds.
- deleted paths are struck through; in the rewind the strikes pull back right to left as the files are restored.
- a slow eased push on every scene; a match cut from the wipe's playhead to the real rewindagents ui timeline
  (brand/ui-timeline.png), whose current-step stripe the playhead becomes.
Nothing spins, bounces or blurs. Easing is smoothstep / ease-out cubic.

Sound: music and two SFX only (score()). The studio's produced bed per cut and its sfx-rewind / sfx-tick
(brand/vsl/audio/, AUDIO.md there) are used when on disk: the rewind sound under every wipe (by weight), under the
ruler going back and the rewind command; the tick where the ruler grows a tick and on every swap. If a file is
missing, the old synthesised pad stands in and the manifest's audio.music says "synth fallback". Mastered with a
one measured linear gain to -16 LUFS and the studio limiter; the measured loudness, the source files' sha256 and the mix's sha256 go into the
manifest. There is no voice track (tests/test_vsl_render.py).

Text is outlined from the OFL font files, so frames render the same with no fonts installed.

Usage: .venv/bin/python brand/vsl/render.py [<.brandcache dir>] [--only NAME]
Needs fontTools in .venv, @fontsource packages and @resvg/resvg-js in .brandcache (brand/logo/requirements.txt),
node and ffmpeg (with libx264) on PATH. Writes the mp4s and .srt files in brand/, brand/vsl/manifest.json,
full-size key frames taken from the finished mp4s in brand/vsl/keyframes/ (the middle, the end and the transition
of every card) and a contact sheet per video. Per-frame SVG/PNG sources go to brand/vsl/frames/ (git-ignored).
"""
import array
import base64
import hashlib
import importlib.util
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
BRAND = os.path.dirname(HERE)
ROOT = os.path.dirname(BRAND)
sys.path.insert(0, HERE)
sys.path.insert(0, BRAND)

from contrast_check import PALETTE as C  # noqa: E402
from mp4info import info as mp4_info  # noqa: E402


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


vsl = load("vsl_build", os.path.join(HERE, "build.py"))

FPS = 30
SWAP_MS = 320           # a continuing scene: the old line leaves in this long
SWAP_LEAD_MS = 160      # ...and the new line starts rising this long before the old one has left (no empty slot)
SWAP_TRAVEL = 1.6       # the leaving line travels this many font sizes: its descenders clear the mask too
WIPE_HEAD_MS = 170      # a wiped-in card's first word starts this far into the wipe, revealed behind the playhead
# ...except after a light wipe, whose words start with it (review-textcut-r3.json fix 3): the 450 ms out-eased playhead
# is at x~550 by 150 ms and only words right of it show, so a head of 170 (or the sheet's 100) left 150-250 ms of bare
# paper; 0 puts headline ink right of the playhead from 150 ms on all seven light wipes (the outgoing line still
# fades on WIPE_HEAD_MS, so no frame carries two lines: tests/test_vsl_wipes.py)
WIPE_HEAD_LIGHT_MS = 0
ERASE_RAMP = 240        # in a wipe each word of the outgoing line fades over this many px ahead of the playhead
HEAD_DROP_MS = 240      # after a wipe the ruler's own playhead drops back into place (hidden while the wipe's runs)
# the rewind wipe in three weights (review-textcut.json fix 7): quick within a section, the full wipe at a section
# change, a slow wide one with a long tape trail for the story's own rewinds. trail: (offset px, opacity) per line.
WIPES = {
    "light": dict(ms=450, slide=60, ease="out", head=4.5, line=3,
                  trail=((16, 0.45), (36, 0.22))),
    "section": dict(ms=650, slide=90, ease="smooth", head=5.0, line=4,
                    trail=((18, 0.5), (40, 0.28), (70, 0.14))),
    "story": dict(ms=900, slide=160, ease="smooth", head=6.0, line=5,
                  trail=((16, 0.62), (38, 0.44), (66, 0.32), (104, 0.22), (150, 0.13), (210, 0.07))),
}
SFX_GAIN = {"light": 0.35, "section": 0.55, "story": 1.0}   # the rewind sound under a wipe, by its weight
WORD_MS = 420           # one word rising out of its mask
WORD_GAP_MS = 48        # between the start of one word and the next
TYPE_MS = 28            # a command types at about 36 characters a second
ENTER_MS = 220          # between the end of a typed command and its output
LINE_MS = 70            # between two output lines
RISE_MS = 300           # an output line rising out of its row
STRIKE_MS = 360
CHAPTER_MS = 950        # a chapter card (b04's roadmap, one part further on) holds this long before its line builds
CHAPTER_OUT_MS = 300    # ...then rises out and fades as the line starts
CHAPTER_INK_MS = 150    # the part reached turns from Record to ink over the hold's last 150 ms (r3 fix 5)
PANEL_OPEN_MS = 260     # a new terminal panel opens to its title bar and prompt row in this long...
PANEL_LEAD_MS = 120     # ...and grows a row this long before the line that needs it arrives
PANEL_GROW_MS = 220     # over this long         # a strike drawing through a path, or pulling back
PUSH = 0.022            # the slow push on every scene: scale grows by this much over the scene
SLOTS = 15              # the ruler has room for fifteen steps (the session has fourteen; the rewind is fifteen)
SAMPLE_RATE = 48000
HEAD_GAP = 40           # the least room between a card's line (its descenders) and the proof under it
SAFE = 60               # no text closer than this to a frame edge (feeds crop and overlay the edges)
TARGET_LUFS = -16.0
# the stream's own VUI says BT.709 primaries, transfer and matrix, limited range (libx264 left primaries/transfer unset)
BT709_BSF = "h264_metadata=colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1:video_full_range_flag=0"
LOUDNESS = "linear gain to -16 LUFS integrated + alimiter limit 0.76 (true peak <= -1.5 dBTP, measured after AAC)"
AUDIO_DIR = os.path.join(HERE, "audio")        # the studio's produced bed and SFX (AUDIO.md there says what they are)
FADE_MS = 1500                                 # the bed fades out over the last 1.5 s of every film
REWIND_LAND_MS = 720                           # sfx-rewind.wav lands (thump + bell) this far into the file (AUDIO.md)
LIMITER = "alimiter=limit=0.76:attack=5:release=50:level=0"   # AUDIO.md's mix advice for bed + SFX
UI_SHOT = os.path.join(BRAND, "ui-timeline.png")
UI_CROP = (241, 104, 999, 740)   # x, y, w, h in the 1440 x 900 screenshot: the timeline column from its red stripe
# x, y, w, h of the push's end: from step 14's '14 Write' header (ink from y 635) to the bottom of step 15's last chip
# row (y 819), every chip and timestamp whole (review-textcut-r2.json fix 2: the old 232 px-high close sliced
# 'tests/test_confi'; r3 fix 2: the 160 px close opened on step 14's chips without their header). w sets the scale:
# 1600 / 528 = 3.03, so the 9 px timestamp digits run >= 27 px; the window is then 190 x 3.03 = 576 px high
UI_CLOSE = (241, 632, 528, 190)
UI_COLUMN_X1 = 773               # the timeline column's right edge in the screenshot (the diff pane starts there)
UI_STRIP = 96                    # source rows per strip of the screenshot (Kit.ui_strips)
UI_BOX_H = 576                   # the window's height on screen; it widens from the column's width to X1 as it pushes
UI_TOP = 440                     # its top: under the headline's descenders; the chip + note sit right of the line's end
UI_LABEL = 34                    # the 127.0.0.1 note's size there (40 does not fit beside the chip and the line)
# the whole column for 0.7 s, then the push to the close crop, which lands ~2.9 s in and holds ~2.25 s (r3 fix 2)
UI_HOLD_MS, UI_PUSH_MS = 700, 2200

# Lines on screen that are commands (typed at a prompt) and lines that are terminal output; anything else in a
# terminal card is a note. Same patterns as tests/test_vsl.py, plus `cd`.
COMMAND = re.compile(r"^(rewindagents|python3 -m rewindagents|pipx|pip|git|echo|cd)\b")
OUTPUT = re.compile(r"^\s*(\d+\s+(Read|Edit|Write|Bash|MultiEdit|NotebookEdit)\b|restore\s|session \w+: rewind|"
                    r"this rewind is step|[ MD?]{2,3}\S)")

# A screen line "strap: <words>" is the card's strap: a small label set over its line, not a panel line. The words
# count toward the card's reading time (build.py reading_ms). The vertical's b01 uses it so the 14 s cut says what
# the tool is before its question (review-textcut-r3.json, vertical story row).
STRAP = "strap: "
STRAP_SIZE = {"16:9": 40, "9:16": 46}

# ---- direction: what each card is and what moves in it ----------------------------------------------------
# kind: type (the line alone, centred), term (a terminal panel), rows (ruled rows on paper), roadmap, quote, map,
#   chain, ui (the real timeline screenshot), end (the end card on Reel).
# Times are ms after the card's proof starts (P: the moment its line has finished building).
# ruler: (ticks, playhead step, at, ms) - the ruler moves there at P+at over ms (at < 0 counts from the card start).
# accent: [[at, [line indexes]]] lines in Rewind from then (the latest group wins). strike: [at, [indexes]] the path
#   on those lines struck through. unstrike: [at, [indexes], stagger] strikes on lines that appeared struck pull back.
# word: [at, index, text] that text on that line turns Rewind. notes_side: notes beside a panel sized to its lines.
# panel_fit: the panel as wide as its lines need, notes under it. bullets: notes under a panel get the bullet squares.
# appear_on: per row, the word of the card's line on which that row rises in.
# wipe: light / section / story (WIPES); unset, a wipe is "section" where beats.json's section changes, else "light".
# brackets: two Rule brackets round that ruler tick. rows_colour: per row Reel/Tape/Record; new_rows: rows that
#   arrive in this card (the others are already there).
DIRECTION = {
    "vsl-90s": {
        "b01": dict(kind="type", ruler=(14, 14, -300, 1500)),
        "b02": dict(kind="term", accent=[[300, [1, 2]]]),
        "b03": dict(kind="term", strike=[250, [4, 5]]),
        "b04": dict(kind="roadmap"),
        "b05": dict(kind="term", ruler=(14, 6, -200, 900), brackets=6, accent=[[150, [0]]], wipe="story"),
        "b06": dict(kind="quote", underline="isn't tracked"),
        "b07": dict(kind="type", chapter=(1, CHAPTER_MS)),     # the roadmap returns: 'how it works' (r2 fix 6)
        "b08": dict(kind="map", rows_colour=["Reel"], new_rows=[0]),
        "b09": dict(kind="map", rows_colour=["Tape", "Record"], new_rows=[1]),
        "b10": dict(kind="chain"),
        "b11": dict(kind="term", ruler=(14, 13, -200, 300), brackets=13, word=[250, 0, "[3 checkpointed]"]),
        "b12": dict(kind="term", ruler=(14, 14, -200, 300), chapter=(2, CHAPTER_MS)),   # ...and 'the fix'
        "b13": dict(kind="term", accent=[[-250, [2]]], ruler=(14, 12, -150, 600)),
        "b14": dict(kind="term", struck=[2, 3, 4, 5], unstrike=[250, [2, 3, 4, 5], 260], wipe="story"),
        "b15": dict(kind="term", accent=[[100, [6]]], ruler=(15, 12, 100, 300)),
        "b16": dict(kind="map", rows_colour=["Tape", "Tape", "Reel"], new_rows=[2]),
        "b17": dict(kind="map", rows_colour=["Tape", "Tape", "Tape", "Record"], new_rows=[3]),
        # one real line of output under each chip (r2 fix 5, r3 fix 4): diff 12's '+++' line, and the second line
        # `rewind 12 --only app/config.py` prints on the demo session; the second chip waits for the first's output
        "b18": dict(kind="rows", appear_on=["diff", None, "--only", None], out_rows=[1, 3]),
        "b19": dict(kind="ui", wipe="section"),   # the match cut keeps the full wipe
        "b20": dict(kind="rows"),     # the old b20 'Up next' card folded in here (fix 6); no row in the accent (fix 8)
        "b21": dict(kind="end", wipe="section"),
    },
    "vsl-30s": {
        "b01": dict(kind="type", ruler=(14, 14, -300, 1500)),
        "b02": dict(kind="term", accent=[[300, [1, 2]]]),
        "b03": dict(kind="term", strike=[250, [4, 5]]),
        "b04": dict(kind="term", ruler=(14, 14, -200, 300), wipe="section"),
        "b05": dict(kind="term", accent=[[-250, [2]]], ruler=(14, 12, -150, 600)),
        "b06": dict(kind="term", struck=[2, 3, 4, 5], unstrike=[250, [2, 3, 4, 5], 260], wipe="story"),
        "b07": dict(kind="end", wipe="section"),
    },
    "vsl-15s-vertical": {
        "b01": dict(kind="term", ruler=(14, 14, -600, 1), strike=[200, [0, 1]]),
        "b02": dict(kind="term", ruler=(14, 12, -200, 600), struck=[1, 2, 3, 4], unstrike=[250, [1, 2, 3, 4], 230],
                    wipe="story"),
        "b03": dict(kind="end", wipe="section"),
    },
}

LAYOUT = {
    "16:9": dict(W=1920, H=1080, X0=160, X1=1760, RULER_Y=150, HEAD=84, HEAD_TOP=236, TYPE=124, PROOF=452,
                 SIDE_W=980, MONO=40, TITLE=50, PAD=32, NOTE=40, ROW=48, ROW_H=104, QUOTE=54, BOTTOM=1010),
    "9:16": dict(W=1080, H=1920, X0=80, X1=1000, RULER_Y=300, HEAD=92, HEAD_TOP=420, TYPE=112, PROOF=760,
                 SIDE_W=920, MONO=46, TITLE=58, PAD=34, NOTE=44, ROW=48, ROW_H=110, QUOTE=46, BOTTOM=1840),
}


# ---- text: glyphs outlined once per font, placed with <use> ------------------------------------------------
class Font:
    def __init__(self, path, prefix):
        from fontTools.ttLib import TTFont
        self.font = TTFont(path)
        self.gs = self.font.getGlyphSet()
        self.cmap = self.font.getBestCmap()
        self.upm = self.font["head"].unitsPerEm
        self.hmtx = self.font["hmtx"]
        self.prefix = prefix
        self.paths = {}

    def d(self, ch):
        if ch not in self.paths:
            from fontTools.pens.svgPathPen import SVGPathPen
            pen = SVGPathPen(self.gs)
            self.gs[self.cmap[ord(ch)]].draw(pen)       # KeyError = a character the font lacks: stop
            self.paths[ch] = pen.getCommands()
        return self.paths[ch]

    def width(self, text, size, tracking=0.0):
        return sum(self.hmtx[self.cmap[ord(ch)]][0] + tracking * self.upm for ch in text) * size / self.upm

    def cap(self, size):
        from fontTools.pens.boundsPen import BoundsPen
        bp = BoundsPen(self.gs)
        self.gs[self.cmap[ord("H")]].draw(bp)
        return bp.bounds[3] * size / self.upm


class Canvas:
    """One frame: SVG parts plus the glyphs and clip paths they use, so <defs> holds each once."""

    def __init__(self, W, H, ground):
        self.W, self.H, self.parts, self.used, self.clips = W, H, [rect(0, 0, W, H, C[ground])], {}, []

    def add(self, s):
        self.parts.append(s)

    def clip(self, x, y, w, h):
        cid = "k%d" % len(self.clips)
        self.clips.append('<clipPath id="%s"><rect x="%.2f" y="%.2f" width="%.2f" height="%.2f"/></clipPath>'
                          % (cid, x, y, max(0.0, w), max(0.0, h)))
        return cid

    def text(self, font, text, size, x, base, colour, tracking=0.0, check=True):
        s = size / font.upm
        uses, cx = [], 0.0
        for ch in text:
            if font.d(ch):
                gid = "%s%d" % (font.prefix, ord(ch))
                self.used[gid] = (font, ch)
                uses.append('<use href="#%s" x="%.1f"/>' % (gid, cx))      # font units, like the paths
            cx += font.hmtx[font.cmap[ord(ch)]][0] + tracking * font.upm
        if uses:
            if check and (x < SAFE or x + cx * s > self.W - SAFE or base > self.H - SAFE):
                raise SystemExit("text leaves the %d px safe margin: %r at x %.0f to %.0f, baseline %.0f"
                                 % (SAFE, text, x, x + cx * s, base))
            self.add('<g fill="%s" transform="translate(%.2f %.2f) scale(%.5f %.5f)">%s</g>'
                     % (C[colour], x, base, s, -s, "".join(uses)))
        return cx * s

    def svg(self):
        defs = "".join('<path id="%s" d="%s"/>' % (gid, f.d(ch)) for gid, (f, ch) in sorted(self.used.items()))
        return ('<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 %d %d" '
                'width="%d" height="%d"><defs>%s%s</defs>%s</svg>\n'
                % (self.W, self.H, self.W, self.H, defs, "".join(self.clips), "".join(self.parts)))


def rect(x, y, w, h, fill):
    return '<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" fill="%s"/>' % (x, y, max(0.0, w), max(0.0, h), fill)


def outline(x, y, w, h, colour, sw):
    return ('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" fill="none" stroke="%s" stroke-width="%g"/>'
            % (x + sw / 2, y + sw / 2, w - sw, h - sw, C[colour], sw))


def ease(p):
    p = min(max(p, 0.0), 1.0)
    return p * p * (3 - 2 * p)


def out_cubic(p):
    p = min(max(p, 0.0), 1.0)
    return 1 - (1 - p) ** 3


def wrap(font, text, size, width):
    lines, cur = [], ""
    for w in text.split():
        trial = (cur + " " + w).strip()
        if cur and font.width(trial, size) > width:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    return lines + ([cur] if cur else [])


def wrap_sentences(font, text, size, width):
    """Lines for a card: one sentence a line when every sentence fits, else greedy wrapping."""
    parts = [x for x in re.split(r"(?<=[.?!:])\s+", text) if x]
    if 1 < len(parts) <= 3 and all(font.width(x, size) <= width for x in parts):
        return parts
    lines = wrap(font, text, size, width)
    if len(lines) > 1 and len(lines[-1].split()) == 1:          # no orphan: take a word down from the line above
        head = lines[-2].split()
        lines[-2:] = [" ".join(head[:-1]), head[-1] + " " + lines[-1]]
    return lines


def fill(text, cfg):
    return text.replace("{site_url}", cfg["site_url"]).replace("{repo_url}", cfg["repo_url"])


# ---- the plan: every card turned into timed events ---------------------------------------------------------
def accent_words(text, accent):
    """Indexes of the words of `text` that the accent phrase covers."""
    if not accent or accent not in text:
        return set()
    a0 = text.index(accent)
    a1 = a0 + len(accent)
    out, pos = set(), 0
    for i, w in enumerate(text.split()):
        s = text.index(w, pos)
        if s < a1 and s + len(w) > a0:
            out.add(i)
        pos = s + len(w)
    return out


def plan(video, cfg, L, kit):
    """Per card: absolute times, its line's layout, the proof's start P and its panel lines (a continuing scene
    keeps the lines it already has)."""
    direction = DIRECTION[video["name"]]
    cards, t0, scene = [], 0, -1
    lines = []
    for i, b in enumerate(video["beats"]):
        d = direction[b["id"]]
        cont = bool(b.get("cont")) and i > 0
        if not cont:
            scene += 1
            lines = []
        wipe = None
        if i > 0 and not cont:
            prev_section = video["beats"][i - 1].get("section")
            wipe = d.get("wipe") or ("section" if b.get("section") != prev_section else "light")
        hs = 160 if i == 0 else (SWAP_MS - SWAP_LEAD_MS if cont else
                                 WIPE_HEAD_LIGHT_MS if wipe == "light" else WIPE_HEAD_MS)
        if d.get("chapter"):
            hs = d["chapter"][1] + CHAPTER_OUT_MS // 2      # the line starts rising as the roadmap leaves
        n_words = len(b["text"].split())
        p = hs + WORD_GAP_MS * (n_words - 1) + WORD_MS + 120
        screen = [fill(s, cfg) for s in b["screen"]]
        strap = [s[len(STRAP):] for s in screen if s.startswith(STRAP)]
        screen = [s for s in screen if not s.startswith(STRAP)]
        card = {"i": i, "id": b["id"], "beat": b, "d": d, "kind": d["kind"], "start": t0, "end": t0 + b["ms"],
                "cont": cont, "scene": scene, "hs": hs, "P": p, "screen": screen, "strap": strap[0] if strap else None,
                "wipe": wipe, "wipe_ms": WIPES[wipe]["ms"] if wipe else 0,
                "accent_idx": accent_words(b["text"], b.get("accent")),
                "prev_kind": cards[-1]["kind"] if cards else None}
        if d["kind"] == "term":
            t = t0 + p
            lines = [dict(x) for x in lines]
            card["notes"] = []
            card["refs"] = {}
            for k, s in enumerate(card["screen"]):
                old = next((x for x in lines if x["text"] == s), None)
                if old:
                    card["refs"][k] = old
                    continue
                if COMMAND.match(s.strip()):
                    ln = {"kind": "cmd", "text": s.strip(), "at": t, "typed": t + TYPE_MS * len(s.strip())}
                    t = ln["typed"] + ENTER_MS
                elif OUTPUT.match(s):
                    ln = {"kind": "out", "text": s, "at": t}
                    t += LINE_MS
                else:
                    note = {"text": s, "at": t + 120, "index": len(card["notes"])}
                    if note_continues(note):     # a run-on line rises with the line it finishes, never after it
                        note["at"] = card["notes"][-1]["at"]
                    else:
                        t += 120
                    card["notes"].append(note)
                    continue
                lines.append(ln)
                card["refs"][k] = ln
            card["lines"] = lines
            card["printed"] = t          # when the last of its lines has appeared
        cards.append(card)
        t0 += b["ms"]
    # each scene's panel is as tall as the most it ever shows (lines plus the prompt)
    adv = kit.mono.width("x", 100) / 100
    # a line too long for the panel at full size breaks at its semicolon onto a second, indented row (the text stays
    # the session's own line, only the break is added: review-textcut.json fix 4) instead of shrinking the type
    full_cols = int((L["X1"] - L["X0"] - 2 * L["PAD"] - 4) / (adv * L["MONO"]))
    for c in cards:
        for ln in c.get("lines", []):
            ln["segs"] = split_line(ln["text"], full_cols - 2)
    rows = {}
    for c in cards:
        if c["kind"] == "term":
            rows[c["scene"]] = max(rows.get(c["scene"], 0), sum(len(x["segs"]) for x in c["lines"]))
    # and its type as big as the longest line it ever shows allows
    longest = {}
    for c in cards:
        if c["kind"] == "term":
            longest[c["scene"]] = max([longest.get(c["scene"], 0)] + [len(g) + 2 for x in c["lines"] for g in x["segs"]])
    for c in cards:
        if c["kind"] == "term":
            c["rows"] = rows[c["scene"]]
            w = L["X1"] - L["X0"]
            if c["d"].get("notes_side") or c["d"].get("panel_fit"):
                # a panel beside notes is as wide as its longest line needs, so the notes get the rest of the row
                w = min(L["SIDE_W"], max(560, int(longest[c["scene"]] * adv * L["MONO"] + 2 * L["PAD"] + 8)))
                c["panel_w"] = w
                nw = L["X1"] - (L["X0"] + w + 56) - 28
                c["notes_h"] = L["TITLE"] + 18 + sum(len(wrap(kit.body, n["text"], L["NOTE"], nw)) * L["NOTE"] * 1.28
                                                     + L["NOTE"] * 0.7 for n in c["notes"])
            c["mono"] = min(L["MONO"], int((w - 2 * L["PAD"] - 4) / (longest[c["scene"]] * adv)))
            c["lh"] = round(c["mono"] * 1.5)
            c["prompt"] = True
            # a panel taller than the frame allows first drops its trailing prompt, then closes its line spacing
            # (never below 1.3 lines); the type size is never what gives
            room = L["BOTTOM"] - L["PROOF"] - L["TITLE"] - 2 * L["PAD"] - c["mono"]
            if (c["rows"]) * c["lh"] > room:
                c["prompt"] = False
                n = max(1, c["rows"] - 1)
                if n * c["lh"] > room:
                    c["lh"] = int(room / n)
                    if c["lh"] < 1.3 * c["mono"]:
                        raise SystemExit("card %s: its panel does not fit at %d px" % (c["id"], c["mono"]))
    # a proof never sits on its line: a card whose line runs to three rows moves its proof down (the whole scene
    # moves the same, so a continuing scene never jumps)
    for c in cards:
        c["pshift"] = 0
        if c["kind"] in ("type", "end", "ui"):
            continue
        size, hl, _ = headline_layout(kit, L, c)
        c["pshift"] = max(0, int(math.ceil(hl[-1][1] + 0.2 * size + HEAD_GAP - L["PROOF"])))
    for sc in {c["scene"] for c in cards}:
        group = [c for c in cards if c["scene"] == sc]
        m = max(c["pshift"] for c in group)
        for c in group:
            c["pshift"] = m
    # the ruler: (time, ticks, playhead, ms) moves in order
    moves = [(0, 0, 0, 1)]
    for c in cards:
        if "ruler" in c["d"]:
            n, ph, at, ms = c["d"]["ruler"]
            moves.append((c["start"] + rel(c, at), n, ph, ms))
    # balance each scene in the space under the ruler: its line and proof move down together by half the room
    # the scene leaves at the bottom (the scene's tallest card decides, so a continuing scene never jumps)
    for c in cards:
        c["bottom"] = proof_bottom(L, c) + c["pshift"]
        if c["bottom"] > L["BOTTOM"]:
            raise SystemExit("card %s: its proof ends at %d, below %d" % (c["id"], c["bottom"], L["BOTTOM"]))
    for sc in {c["scene"] for c in cards}:
        group = [c for c in cards if c["scene"] == sc]
        if group[0]["kind"] in ("type", "end", "ui"):
            continue
        bottom = max(c["bottom"] for c in group)
        dy = max(0, round((L["BOTTOM"] - bottom) / 2 - 20))
        for c in group:
            c["dy"] = dy
    first_ruled = next((c for c in cards if "ruler" in c["d"]), None)
    return {"cards": cards, "moves": sorted(moves), "total": t0,
            "ruled_from": first_ruled["start"] if first_ruled else 0}


def split_line(text, cols):
    """A terminal line as the rows it is shown on: itself, or, when longer than `cols` and it has a semicolon, the
    part up to the semicolon and the rest on a second row indented two more spaces than the line."""
    if len(text) <= cols or "; " not in text:
        return [text]
    a, b = text.split("; ", 1)
    indent = len(text) - len(text.lstrip()) + 2
    return [a + ";", " " * indent + b]


def proof_bottom(L, c):
    """Where a card's proof ends (an estimate from its layout), for balancing the scene vertically."""
    k, top = c["kind"], L["PROOF"]
    if k == "term":
        n = max(2, c["rows"] + (1 if c["prompt"] else 0))
        h = L["TITLE"] + 2 * L["PAD"] + n * c["lh"] - (c["lh"] - c["mono"])
        if c["d"].get("notes_side"):
            return top + max(h, c["notes_h"])
        return top + h + len(c["notes"]) * L["NOTE"] * 2
    if k in ("rows", "map"):
        return top + 20 + len(c["screen"]) * L["ROW_H"]
    if k == "quote":
        return top + 300
    if k == "chain":
        return top + 10 + 128 + 70 + 2 * L["ROW_H"]
    if k == "roadmap":
        return top + 290
    return L["BOTTOM"]


def rel(card, at):
    """A DIRECTION time as ms after the card's start: at >= 0 is after its proof starts (P), at < 0 is -at after
    the card's start (things that move while the line is still building, like the ruler scrubbing back)."""
    return -at if at < 0 else card["P"] + at


def ruler_state(p, t):
    """(ticks shown as a float, playhead step as a float): every move eases from where the last one settled."""
    n, ph = 0.0, 0.0
    for at, tn, tph, ms in p["moves"]:
        if at > t:
            break
        k = ease((t - at) / max(1, ms))
        n0, ph0 = n, ph
        n = n0 + (tn - n0) * k
        ph = ph0 + (tph - ph0) * k
    return n, ph


def tick_times(p):
    """ms at which a ruler tick is born (its count passes i + 0.5); ticks closer than 40 ms are one sound."""
    out, n = [], 0.0
    for at, tn, tph, ms in p["moves"]:
        if tn > n + 0.25:
            for i in range(int(math.floor(n + 0.5)), int(math.ceil(tn - 0.5))):
                want = (i + 0.5 - n) / (tn - n)
                lo, hi = 0.0, 1.0
                for _ in range(30):                       # invert the smoothstep the ruler eases with
                    mid = (lo + hi) / 2
                    lo, hi = (mid, hi) if ease(mid) < want else (lo, mid)
                out.append(at + lo * max(1, ms))
        n = tn
    merged = []
    for t in sorted(out):
        if not merged or t - merged[-1] >= 40:
            merged.append(t)
    return merged


def sfx_events(p):
    """{"rewind": [(ms, gain)], "tick": [(ms, gain)]}: the rewind sound under every wipe (louder the heavier the
    wipe), under the ruler going back outside a wipe and under the rewind command; a tick where the ruler grows a
    tick and on every swap. Nothing at 0 ms (review-textcut.json: the old bed clicked at sample 0). A rewind's ms is
    where it LANDS: the wipe's end, the scrub's end, the command's enter (AUDIO.md: the sound lands REWIND_LAND_MS in)."""
    rewind, tick = [], []
    wipes = [(c["start"], c["start"] + c["wipe_ms"]) for c in p["cards"] if c["wipe"]]
    for c in p["cards"]:
        if c["wipe"]:
            rewind.append((c["start"] + c["wipe_ms"], SFX_GAIN[c["wipe"]]))
    last = 0
    for at, tn, tph, ms in p["moves"]:
        if tph < last and not any(a <= at <= b for a, b in wipes):
            rewind.append((at + ms, 0.7))
        last = tph
    for c in p["cards"]:
        for ln in c.get("lines", []):
            if ln["kind"] == "cmd" and ln["text"].startswith("rewindagents rewind") and c["start"] <= ln["at"] < c["end"]:
                rewind.append((ln["typed"] + ENTER_MS, 0.8))
    kept = []
    for t, g in sorted(rewind):
        if t >= 40 and (not kept or t - kept[-1][0] >= 600):
            kept.append((t, g))
    tick = [(t, 0.8) for t in tick_times(p) if t >= 40]
    tick += [(c["start"], 0.5) for c in p["cards"] if c["cont"]]
    return {"rewind": kept, "tick": sorted(tick)}


def sweeps(p):
    """ms of every rewind sound (the manifest lists them)."""
    return [int(t) for t, _ in sfx_events(p)["rewind"]]


# ---- drawing ------------------------------------------------------------------------------------------------
class Kit:
    def __init__(self, cache):
        self.logo = load("logo_build", os.path.join(BRAND, "logo", "build.py"))
        fs = os.path.join(cache, "node_modules", "@fontsource")
        self.mono = Font(os.path.join(fs, "commit-mono", "files", "commit-mono-latin-400-normal.woff"), "m")
        self.disp = Font(os.path.join(fs, "bricolage-grotesque", "files", "bricolage-grotesque-latin-800-normal.woff"), "d")
        self.body = Font(os.path.join(fs, "hanken-grotesk", "files", "hanken-grotesk-latin-400-normal.woff"), "b")
        self.bold = Font(os.path.join(fs, "hanken-grotesk", "files", "hanken-grotesk-latin-600-normal.woff"), "s")
        self.logo_disp = self.logo.Face(os.path.join(fs, "bricolage-grotesque", "files",
                                                     "bricolage-grotesque-latin-800-normal.woff"))
        # the timeline column of the screenshot as horizontal strips (UI_STRIP source px, overlapping by 2 so no seam
        # shows when scaled): resvg cuts a raster image off about twice the canvas height below its top edge when it
        # sits under a clip layer (the wipe's), and at the push's 3x a whole-column image is 2,400 px tall
        cx, cy = UI_CROP[0], UI_CROP[1]
        self.ui_strips = []
        for y0 in range(cy, 900, UI_STRIP):
            a, b = max(cy, y0 - 2), min(900, y0 + UI_STRIP + 2)
            png = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", UI_SHOT, "-vf",
                                  "crop=%d:%d:%d:%d" % (UI_COLUMN_X1 - cx, b - a, cx, a), "-f", "image2pipe",
                                  "-vcodec", "png", "-"], capture_output=True, check=True).stdout
            self.ui_strips.append((a, b - a, "data:image/png;base64," + base64.b64encode(png).decode("ascii")))


def playhead_shape(x, top, k, colour):
    """The logo's editor handle: a small pentagon pointing down, centred on x."""
    return ('<g transform="translate(%.2f %.2f) scale(%.3f)"><path d="M0 0H4V2L2.5 3.5H1.5L0 2Z" fill="%s"/></g>'
            % (x - 2 * k, top, k, C[colour]))


def draw_ruler(cv, kit, L, state, brackets=None, head=1.0):
    """The step ruler. head: None hides its playhead (a wipe's playhead is on screen); 0..1 drops it into place."""
    nf, ph = state
    if nf <= 0.001:
        return
    x0, x1, y = L["X0"], L["X1"], L["RULER_Y"]
    pitch = (x1 - x0) / (SLOTS - 1)
    th = 26 if L["W"] > L["H"] else 30
    xs = [x0 + i * pitch for i in range(SLOTS)]
    n = int(math.ceil(nf - 1e-6))
    last = x0 + (nf - 1) * pitch if nf >= 1 else x0
    php = x0 + (max(ph, 1) - 1) * pitch
    cv.add(rect(x0 - 2, y, php - x0 + 2, 2, C["Reel"]))
    cv.add(rect(php, y, max(0.0, last + 2 - php), 2, C["Rule"]))
    size = 24 if L["W"] > L["H"] else 28
    for i in range(n):
        grow = min(1.0, nf - i)
        h = th * ease(grow)
        step = i + 1
        cv.add(rect(xs[i] - 2, y - h, 4, h, C["Reel"] if step <= ph + 0.01 else C["Rule"]))
        if grow > 0.5:
            label = str(step)                     # step numbers are text: Tape, never Rule (BRAND.md)
            w = kit.mono.width(label, size)
            cv.text(kit.mono, label, size, xs[i] - w / 2, y + 12 + size, "Tape")
    if brackets and brackets <= n:
        bx = xs[brackets - 1]
        for side in (-1, 1):
            x = bx + side * pitch * 0.42
            cv.add(rect(x - 1, y - th - 16, 2, th + 30, C["Rule"]))
            cv.add(rect(min(x, x - side * 14), y - th - 16, 14, 2, C["Rule"]))
            cv.add(rect(min(x, x - side * 14), y + 12, 14, 2, C["Rule"]))
    if ph >= 1 and head is not None and head > 0:
        k = 5.0 if L["W"] > L["H"] else 5.5
        top = y - th - 40
        drop = (1 - head) * 30
        cv.add('<g opacity="%.2f">' % head)
        cv.add(playhead_shape(php, top - drop, k, "Record"))
        cv.add(rect(php - 1.5, top - drop + 3.5 * k - 1, 3, y + 2 - (top + 3.5 * k - 1), C["Record"]))
        cv.add("</g>")


def headline_layout(kit, L, card):
    """(size, [(line words, baseline)], x): a type card is centred on the frame, larger; the others sit under the
    ruler. The end card's line sits at the top of the Reel ground."""
    kind = card["kind"]
    text = card["beat"]["text"]
    width = L["X1"] - L["X0"]
    if kind == "type":
        size = L["TYPE"]
    else:
        size = L["HEAD"]
    lines = wrap_sentences(kit.disp, text, size, width)
    lh = size * 1.14
    cap = kit.disp.cap(size)
    if kind == "type":
        block = cap + lh * (len(lines) - 1)
        top = (L["H"] + L["RULER_Y"]) / 2 - block / 2
    elif kind == "end":
        top = 220 if L["W"] > L["H"] else 460
    else:
        top = L["HEAD_TOP"]
    return size, [(ln.split(), top + cap + k * lh) for k, ln in enumerate(lines)], L["X0"]


def proof_accented(card):
    """True when the card's proof carries the accent (a Rewind/Record row, strike, word, underline, label, the
    screenshot's red stripe). BRAND.md allows one Record/Rewind per view, so on such a card the proof keeps it and
    the line's accent phrase is set in the ink at the same weight (review-textcut.json fix 8: one rule, every card)."""
    d, kind = card["d"], card["kind"]
    return bool(d.get("accent") or d.get("strike") or d.get("struck") or d.get("unstrike") or d.get("word")
                or d.get("underline") or d.get("note_accent") is not None or d.get("accent_row") is not None
                or "Record" in d.get("rows_colour", []) or kind in ("roadmap", "chain", "ui"))


def draw_headline(cv, kit, L, card, u, leaving=None, dark=False, erase=None):
    """The card's line, word by word out of a mask; `leaving` = ms since it began to leave: it rises out by
    SWAP_TRAVEL sizes, far enough that its descenders and full stop clear the mask as well (fix 1).
    `erase` = (the wipe's playhead in this line's own x, a time fade): the line fades out over the ERASE_RAMP px
    before the playhead reaches the line's right-most edge, and by the time fade at the latest, so the outgoing line is gone wherever the incoming one
    shows and no frame reads two lines as one (review-textcut-r2.json fix 1)."""
    size, lines, x = headline_layout(kit, L, card)
    acc = set() if proof_accented(card) else card["accent_idx"]
    space = kit.disp.width(" ", size)
    idx = 0
    ink, accent = ("Leader", "Rewind") if dark else ("Reel", "Record")
    # the old line accelerates up out of its mask and fades as it goes: a mask alone lets the descenders and the
    # full stop trail behind for frames (review-textcut.json fix 1); the new line has begun rising by then
    pl = min(max(leaving / SWAP_MS, 0.0), 1.0) if leaving is not None else 0.0
    out_k = pl * pl
    if leaving is not None:
        cv.add('<g opacity="%.3f">' % (1 - ease((pl - 0.15) / 0.45)))
    # the whole line fades as one block, keyed to its right-most word: a word kept at full ink at the left would
    # still share a baseline with the incoming line (r3 frames: 'Twelve, because' + 'and four files')
    right = max(x + kit.disp.width(" ".join(ws), size, -0.01) for ws, _ in lines)
    for words, base in lines:
        cid = cv.clip(x - 20, base - size * 1.02, L["X1"] - x + 40, size * 1.32)
        cv.add('<g clip-path="url(#%s)">' % cid)
        cx = x
        for w in words:
            t_w = card["hs"] + WORD_GAP_MS * idx
            k = out_cubic((u - t_w) / WORD_MS)
            dy = (1 - k) * size * 1.05 - out_k * size * SWAP_TRAVEL
            wd = kit.disp.width(w, size, -0.01)
            fade = 1.0 if erase is None else min(1.0, max(0.0, (erase[0] - right) / ERASE_RAMP), erase[1])
            if k > 0 and fade > 0:
                if fade < 1:
                    cv.add('<g opacity="%.3f">' % fade)
                cv.text(kit.disp, w, size, cx, base + dy, accent if idx in acc else ink, tracking=-0.01, check=False)
                if fade < 1:
                    cv.add("</g>")
            cx += wd + space
            idx += 1
        cv.add("</g>")
        if cx - space > L["X1"] + 1:
            raise SystemExit("headline too wide: %r" % " ".join(words))
    if card.get("strap"):
        # the strap: Hanken bold in Tape over the line, rising out of its mask just before the line's first word,
        # and fading with the line in a wipe (its own right edge, the same time bound)
        ssize = STRAP_SIZE["9:16" if L["H"] > L["W"] else "16:9"]
        sbase = lines[0][1] - kit.disp.cap(size) - ssize * 0.9
        sw = kit.bold.width(card["strap"], ssize)
        fade = 1.0 if erase is None else min(1.0, max(0.0, (erase[0] - (x + sw)) / ERASE_RAMP), erase[1])
        k = out_cubic((u - max(0, card["hs"] - 60)) / WORD_MS)
        if k > 0 and fade > 0:
            cid = cv.clip(x - 20, sbase - ssize * 1.1, sw + 40, ssize * 1.4)
            cv.add('<g clip-path="url(#%s)" opacity="%.3f">' % (cid, fade))
            cv.text(kit.bold, card["strap"], ssize, x, sbase + (1 - k) * ssize * 1.1, "Tape")
            cv.add("</g>")
    if leaving is not None:
        cv.add("</g>")


def panel_geom(L, card, side):
    x, y = L["X0"], L["PROOF"]
    w = card.get("panel_w") or (L["SIDE_W"] if side else L["X1"] - L["X0"])
    n = max(2, card["rows"] + (1 if card["prompt"] else 0))
    h = L["TITLE"] + 2 * L["PAD"] + n * card["lh"] - (card["lh"] - card["mono"])
    return x, y, w, h


def cursor_on(card, t):
    """True when the panel's trailing "$ " prompt row shows at t: before its first line, and whenever its last shown
    line is output that has finished rising and nothing new has started (a continuing scene keeps it until the next
    command types into that row). A panel whose prompt was dropped for room shows it only before its first line."""
    shown = [ln for ln in card["lines"] if ln["at"] <= t]
    if not shown:
        return True
    if not card["prompt"]:
        return False
    last = shown[-1]
    return last["kind"] == "out" and t >= last["at"] + RISE_MS


def panel_rows_target(card, t):
    return sum(len(ln["segs"]) for ln in card["lines"] if ln["at"] <= t) + (1 if cursor_on(card, t) else 0)


def panel_rows(card, t):
    """The panel's height in rows at t, eased: it opens a row PANEL_LEAD_MS before a line arrives and closes one as
    the prompt row is taken, so the panel is never taller than what it shows (review-textcut-r2.json fix 5: no
    empty dark block on entry, no rows held for lines a later card prints)."""
    if card.get("_events") is None:
        cand = sorted({ln["at"] for ln in card["lines"]} | {ln["at"] + RISE_MS for ln in card["lines"]})
        ev, n = [], 1
        for c in cand:
            m = panel_rows_target(card, c)
            if m != n:
                ev.append((c, m - n))
                n = m
        card["_events"] = ev
    return 1 + sum(dn * ease((t - at + PANEL_LEAD_MS) / PANEL_GROW_MS) for at, dn in card["_events"])


def draw_panel(cv, kit, L, card, t):
    d = card["d"]
    side = d.get("notes_side", False)
    x, y, w, _ = panel_geom(L, card, side)
    first = min(ln["at"] for ln in card["lines"]) if card["lines"] else t
    had_panel = card["cont"] and card["i"] > 0 and card["prev_kind"] == "term"
    # a new panel opens to its title bar and one prompt row (the cursor waiting), then grows with its lines
    grow = 1.0 if had_panel or any(ln["at"] < card["start"] for ln in card["lines"]) else \
        ease((t - first + PANEL_OPEN_MS + PANEL_LEAD_MS) / PANEL_OPEN_MS)
    if grow <= 0:
        return
    n = panel_rows(card, t)
    h = L["TITLE"] + 2 * L["PAD"] + n * card["lh"] - (card["lh"] - card["mono"])
    vis_h = h * grow
    cv.add(rect(x, y, w, vis_h, C["Spool"]))
    tb = L["TITLE"]
    if vis_h < tb:
        return
    cv.add('<g clip-path="url(#%s)">' % cv.clip(x, y, w, vis_h))
    cv.add(rect(x, y + tb - 1, w, 1, C["Rule"]))
    lg = kit.logo
    k = tb * 0.45 / lg.MARK_H
    cv.add(lg.place(lg.mark_shapes(lg.THEMES["dark"], mono=C["Leader"]), x + 24, y + (tb - lg.MARK_H * k) / 2, k))
    nsize = tb * 0.5
    cv.text(kit.disp, "rewindagents", nsize, x + 24 + 16 * k + 12, y + (tb + kit.disp.cap(nsize)) / 2, "Leader",
            tracking=-0.02)
    mono, size, lh, pad = kit.mono, card["mono"], card["lh"], L["PAD"]
    adv = mono.width("x", size)
    cols = int((w - 2 * pad) // adv)
    u = t - card["start"]
    hot = set()
    for at, idx in d.get("accent", []):
        if u >= rel(card, at):
            hot = {id(card["refs"][i]) for i in idx if i in card["refs"]}
    struck = {id(card["refs"][i]) for i in d.get("struck", []) if i in card["refs"]}
    strike_at = {}
    if "strike" in d:
        at, idx = d["strike"]
        for n, i in enumerate(idx):
            strike_at[id(card["refs"][i])] = card["start"] + rel(card, at) + 180 * n
    unstrike_at = {}
    if "unstrike" in d:
        at, idx, stagger = d["unstrike"]
        base_t = card["printed"] + at
        for n, i in enumerate(idx):
            unstrike_at[id(card["refs"][i])] = base_t + stagger * n
    word = d.get("word")
    base0 = y + tb + pad + mono.cap(size)
    shown = [ln for ln in card["lines"] if ln["at"] <= t]
    r = 0
    for ln in shown:
        base = base0 + r * lh
        cx = x + pad
        if max(len(g) for g in ln["segs"]) > cols:
            raise SystemExit("line of %d characters does not fit %d columns: %r" % (len(ln["text"]), cols, ln["text"]))
        if len(ln["segs"]) > 1:
            # a line broken at its semicolon: each row rises like an output line, the second 90 ms after the first
            colour = "Rewind" if id(ln) in hot else "Leader"
            for j, seg in enumerate(ln["segs"]):
                k = out_cubic((t - ln["at"] - 90 * j) / RISE_MS)
                b = base + j * lh
                cid = cv.clip(x, b - size * 1.0, w, lh)
                cv.add('<g clip-path="url(#%s)">' % cid)
                if k > 0:
                    cv.text(mono, seg, size, cx, b + (1 - k) * lh * 0.9, colour)
                cv.add("</g>")
            r += len(ln["segs"])
            continue
        if ln["kind"] == "cmd":
            n = min(len(ln["text"]), int((t - ln["at"]) // TYPE_MS) + 1)
            cv.text(mono, "$ ", size, cx, base, "Playhead")
            cv.text(mono, ln["text"][:n], size, cx + 2 * adv, base, "Leader")
            if t < ln["typed"]:
                cv.add(rect(cx + (2 + n) * adv, base - size * 0.78, adv, size * 0.98, C["Leader"]))
        else:
            k = out_cubic((t - ln["at"]) / RISE_MS)
            cid = cv.clip(x, base - size * 1.0, w, lh)
            cv.add('<g clip-path="url(#%s)">' % cid)
            dy = (1 - k) * lh * 0.9
            unstruck = id(ln) in unstrike_at and t >= unstrike_at[id(ln)]
            colour = "Rewind" if (id(ln) in hot or unstruck) else "Leader"
            if word and u >= rel(card, word[0]) and card["refs"].get(word[1]) is ln and word[2] in ln["text"]:
                a = ln["text"].index(word[2])
                cv.text(mono, ln["text"][:a], size, cx, base + dy, "Leader")
                cv.text(mono, word[2], size, cx + a * adv, base + dy, "Rewind")
                cv.text(mono, ln["text"][a + len(word[2]):], size, cx + (a + len(word[2])) * adv, base + dy, "Leader")
            else:
                cv.text(mono, ln["text"], size, cx, base + dy, colour)
            cv.add("</g>")
            # the path part of the line (after the status or the verb) is what a strike runs through
            m = re.match(r"^(\s*(?:restore\s+|[ MD?]{2,3}))(\S.*)$", ln["text"])
            if m and (id(ln) in strike_at or id(ln) in struck):
                sx = cx + len(m.group(1)) * adv
                sw = len(m.group(2)) * adv
                if id(ln) in strike_at:
                    frac = ease((t - strike_at[id(ln)]) / STRIKE_MS)
                else:
                    frac = 1.0                           # appeared struck (the deleted files, before the rewind)
                    if id(ln) in unstrike_at:
                        frac = 1 - ease((t - unstrike_at[id(ln)]) / STRIKE_MS)
                if frac > 0:
                    cv.add(rect(sx - 4, base - size * 0.34, (sw + 8) * frac, 3, C["Rewind"]))
        r += 1
    if cursor_on(card, t):
        base = base0 + r * lh
        cv.text(mono, "$ ", size, x + pad, base, "Playhead")
        cv.add(rect(x + pad + 2 * adv, base - size * 0.78, adv, size * 0.98, C["Leader"]))
    cv.add("</g>")
    draw_notes(cv, kit, L, card, t, (x, y, w, h), side)


def note_continues(note):
    """A note that starts in lower case runs on from the one above it (one bullet split over two screen lines)."""
    return note["index"] > 0 and note["text"][:1].islower()


def draw_notes(cv, kit, L, card, t, box, side):
    x, y, w, h = box
    size = L["NOTE"]
    acc = card["d"].get("note_accent")
    bullets = side or card["d"].get("bullets", False)
    if side:
        nx = x + w + 56
        nw = L["X1"] - nx
        base = y + L["TITLE"] + 18 + kit.body.cap(size)
    else:
        nx, nw = x, L["X1"] - x
        base = y + h + 36 + kit.body.cap(size)
    colour = None
    for note in card["notes"]:
        k = out_cubic((t - note["at"]) / RISE_MS)
        if k <= 0:
            continue
        cont = note_continues(note)
        if cont:
            base -= size * 0.7                       # the bullet above runs on: no gap, no square, its colour
        else:
            colour = "Record" if acc == note["index"] else ("Reel" if bullets else "Tape")
        lines = wrap(kit.body, note["text"], size, nw - (28 if bullets else 0))
        for line in lines:
            cid = cv.clip(nx, base - size * 1.05, nw + 20, size * 1.35)
            cv.add('<g clip-path="url(#%s)">' % cid)
            if bullets and line is lines[0] and not cont:
                cap = kit.body.cap(size)
                cv.add(rect(nx, base - cap / 2 - 5 + (1 - k) * size, 10, 10, C["Record"] if colour == "Record" else C["Rule"]))
            cv.text(kit.body, line, size, nx + (28 if bullets else 0), base + (1 - k) * size * 1.1, colour)
            cv.add("</g>")
            base += size * 1.28
        base += size * 0.7


def word_time(card, phrase):
    """ms after the card's start at which the first word of `phrase` in the card's line has risen in."""
    norm = lambda w: w.lower().strip(".,:?")
    words = [norm(w) for w in card["beat"]["text"].split()]
    want = [norm(w) for w in phrase.split()]
    for i in range(len(words) - len(want) + 1):
        if words[i:i + len(want)] == want:
            return card["hs"] + WORD_GAP_MS * i + WORD_MS * 0.6
    return card["P"]


def draw_rows(cv, kit, L, card, t, rows, colours, appear, mono_size=None, out_rows=()):
    """Ruled rows on paper; commands in a small Spool chip. appear: per row the ms (card time) it rises in.
    out_rows: rows that are the output of the command chip above them, set close under it, aligned with the
    command's text, in Tape, with no rule."""
    x, w = L["X0"], L["X1"] - L["X0"]
    size, rh = mono_size or L["ROW"], L["ROW_H"]
    y = L["PROOF"] + 20
    u = t - card["start"]
    pull = 0
    for i, row in enumerate(rows):
        if i in out_rows:
            pull += rh - size * 1.55             # an output row sits one line under its chip, not a full row
            base = y + i * rh + size - pull
            k = out_cubic((u - appear[i]) / RISE_MS)
            if k > 0:
                cid = cv.clip(x - 10, base - size - 6, w + 20, size * 1.5)
                cv.add('<g clip-path="url(#%s)">' % cid)
                # the printed line without the terminal's own indent, so it starts under the command's first letter
                cv.text(kit.mono, row.lstrip(), size, x + 28 + kit.mono.width("$ ", size), base + (1 - k) * size, "Tape")
                cv.add("</g>")
            pull -= size * 0.35                  # and the next chip keeps a gap under the output
            continue
        base = y + i * rh + size - pull
        if base > L["BOTTOM"]:
            raise SystemExit("row %r falls below the frame" % row)
        k = out_cubic((u - appear[i]) / RISE_MS) if appear[i] is not None else 1.0
        if k <= 0:
            continue
        cid = cv.clip(x - 10, base - size - 30, w + 20, rh)
        cv.add('<g clip-path="url(#%s)">' % cid)
        dy = (1 - k) * rh * 0.8
        if COMMAND.match(row):
            n = len(row) if appear[i] is None else min(len(row), int(max(0, u - appear[i]) // TYPE_MS) + 1)
            mono_w = kit.mono.width("$ " + row, size)
            cv.add(rect(x, base - size - 12 + dy, mono_w + 56, size + 30, C["Spool"]))
            cv.text(kit.mono, "$ ", size, x + 28, base + dy, "Playhead")
            cv.text(kit.mono, row[:n], size, x + 28 + kit.mono.width("$ ", size), base + dy, "Leader")
        else:
            cv.text(kit.mono, row, size, x, base + dy, colours[i])
            cv.add(rect(x, base + rh - size - 30 + dy, w * ease(k), 1.5, C["Rule"]))
        cv.add("</g>")


def rows_appear(card):
    """Per row of a "rows" card, the ms (card time) it rises in: every 220 ms from P, or with appear_on each row on
    the word of the line that names it, None = the output of the command above it, once that has typed and entered.
    One cursor at a time: a chip types only after the row above it has typed or printed (r3 fix 4: '$ rewindagents
    di' over '$ rewin' at 72.2 s)."""
    d, rows = card["d"], card["screen"]
    if not d.get("appear_on"):
        return [card["P"] + 220 * i for i in range(len(rows))]
    appear = []
    for i, w in enumerate(d["appear_on"]):
        if not w:
            appear.append(appear[-1] + TYPE_MS * len(rows[i - 1]) + ENTER_MS)
            continue
        at = word_time(card, w)
        if i > 0:
            prev = appear[-1] + (TYPE_MS * len(rows[i - 1]) if COMMAND.match(rows[i - 1]) else 0)
            at = max(at, prev + LINE_MS)
        appear.append(at)
    return appear


def draw_proof(cv, kit, L, card, t, p):
    d, kind = card["d"], card["kind"]
    u = t - card["start"]
    P = card["P"]
    rows = card["screen"]
    if kind == "term":
        draw_panel(cv, kit, L, card, t)
    elif kind == "rows":
        appear = rows_appear(card)
        colours = ["Record" if i == d.get("accent_row") else "Reel" for i in range(len(rows))]
        draw_rows(cv, kit, L, card, t, rows, colours, appear, out_rows=d.get("out_rows", ()))
    elif kind == "map":
        new = d.get("new_rows", [])
        appear = [P + 150 * new.index(i) if i in new else None for i in range(len(rows))]
        draw_rows(cv, kit, L, card, t, rows, d["rows_colour"], appear, mono_size=L["ROW"] + 4)
        if 2 in new:
            pass
    elif kind == "roadmap":
        draw_roadmap(cv, kit, L, card, t)
    elif kind == "quote":
        draw_quote(cv, kit, L, card, t)
    elif kind == "chain":
        draw_chain(cv, kit, L, card, t)
    elif kind == "ui":
        draw_ui(cv, kit, L, card, t)


def draw_roadmap(cv, kit, L, card, t):
    u = t - card["start"]
    x0, x1 = L["X0"], L["X1"]
    y = L["PROOF"] + 150
    labels = card["screen"]
    span = (x1 - x0 - 200) / (len(labels) - 1)
    k_line = ease((u - card["hs"]) / 900)
    cv.add(rect(x0, y, (x1 - x0 - 200 + 4) * k_line, 2, C["Rule"]))
    size = 44
    for i, label in enumerate(labels):
        at = word_time(card, label)
        k = out_cubic((u - at) / RISE_MS)
        x = x0 + i * span
        if k <= 0:
            continue
        colour = "Record" if i == 0 else "Tape"
        cv.add(rect(x - 2, y - 30 * ease(k), 4, 30 * ease(k), C["Record"] if i == 0 else C["Rule"]))
        cid = cv.clip(x - 10, y + 12, span, size * 3)
        cv.add('<g clip-path="url(#%s)">' % cid)
        cv.text(kit.mono, str(i + 1), 26, x - kit.mono.width("1", 26) / 2, y + 30 + 26 + (1 - k) * 60, "Tape")
        cv.text(kit.bold, label, size, x - 2, y + 64 + size + (1 - k) * 80, colour)
        cv.add("</g>")


def draw_chapter(cv, kit, L, p, card, u):
    """b04's roadmap again at the start of a part (review-textcut-r2.json fix 6): the same rule, ticks and labels in
    the same places, the part reached marked in Record with the rule drawn in Record up to it, the others in Tape.
    It is on the paper as the wipe reveals the card, holds, then rises out and fades while the card's line builds."""
    idx, hold = card["d"]["chapter"]
    if u >= hold + CHAPTER_OUT_MS:
        return
    road = next(c for c in p["cards"] if c["kind"] == "roadmap")
    labels = road["screen"]
    x0, x1 = L["X0"], L["X1"]
    span = (x1 - x0 - 200) / (len(labels) - 1)
    y = (L["H"] + L["RULER_Y"]) / 2 - 40
    out = ease((u - hold) / CHAPTER_OUT_MS)
    lift = out * out * 90
    cv.add('<g opacity="%.3f" transform="translate(0 %.2f)">' % (1 - out, -lift))
    cv.add(rect(x0, y, x1 - x0 - 200 + 4, 2, C["Rule"]))
    size = 44
    for i, label in enumerate(labels):
        if i != idx:
            x = x0 + i * span
            cv.add(rect(x - 2, y - 30, 4, 30, C["Rule"]))
            cv.text(kit.mono, str(i + 1), 26, x - kit.mono.width("1", 26) / 2, y + 30 + 26, "Tape")
            cv.text(kit.bold, label, size, x - 2, y + 64 + size, "Tape")
    # the part reached: progress rule, tick and label in Record, which turn to ink over the hold's last CHAPTER_INK_MS
    # so the accent has left the rule before the line's own Record words rise (review-textcut-r3.json fix 5: 'the
    # fix' and 'which step' both in Record for ~150 ms at 45.9 s); two layers, as a colour tween leaves the palette
    m = ease((u - (hold - CHAPTER_INK_MS)) / CHAPTER_INK_MS)
    x = x0 + idx * span
    for colour, op in (("Record", 1 - m), ("Reel", m)):
        if op <= 0:
            continue
        cv.add('<g opacity="%.3f">' % op)
        cv.add(rect(x0, y - 1, (idx * span) * ease((u - 150) / 600), 4, C[colour]))   # drawn on as the card opens
        cv.add(rect(x - 2, y - 30, 4, 30, C[colour]))
        cv.text(kit.mono, str(idx + 1), 26, x - kit.mono.width("1", 26) / 2, y + 30 + 26, "Tape")
        cv.text(kit.bold, labels[idx], size, x - 2, y + 64 + size, colour)
        cv.add("</g>")
    cv.add("</g>")


def draw_quote(cv, kit, L, card, t):
    u = t - card["start"]
    quote, source = card["screen"]
    size = L["QUOTE"]
    y = L["PROOF"] + 40
    x = L["X0"]
    one = int((L["X1"] - L["X0"]) / kit.mono.width(quote, 1))
    if one >= 40:
        size = min(size, one)
    lines = wrap(kit.mono, quote, size, L["X1"] - L["X0"])
    under = card["d"].get("underline")
    adv = kit.mono.width("x", size)
    for k_line, line in enumerate(lines):
        base = y + size + k_line * size * 1.5
        at = card["P"] + 140 * k_line
        k = out_cubic((u - at) / (RISE_MS + 100))
        if k <= 0:
            continue
        cid = cv.clip(x - 10, base - size * 1.1, L["X1"] - x + 20, size * 1.5)
        cv.add('<g clip-path="url(#%s)">' % cid)
        cv.text(kit.mono, line, size, x, base + (1 - k) * size * 1.3, "Reel")
        cv.add("</g>")
        if under and under in line:
            a = line.index(under)
            frac = ease((u - card["P"] - 600) / 500)
            cv.add(rect(x + a * adv, base + 12, len(under) * adv * frac, 4, C["Record"]))
    base = y + size + len(lines) * size * 1.5 + 30
    k = out_cubic((u - card["P"] - 300) / RISE_MS)
    if k > 0:
        cv.add(rect(x, base - 40, 60 * ease(k), 2, C["Rule"]))
        cv.text(kit.body, source, L["NOTE"], x, base + 10 + (1 - k) * 30, "Tape")


def draw_chain(cv, kit, L, card, t):
    u = t - card["start"]
    x, w = L["X0"], L["X1"] - L["X0"]
    y = L["PROOF"] + 10
    n, box = 7, 128
    span = (w - n * box) / (n - 1)
    for i in range(n):
        at = card["P"] + 150 * i
        k = out_cubic((u - at) / 360)
        if k <= 0:
            continue
        bx = x + i * (box + span)
        if i > 0:
            lk = ease((u - at) / 260)
            cv.add(rect(bx - span, y + box / 2 - 1, span * lk, 2, C["Rule"]))
        by = y + (1 - k) * 40
        cv.add(rect(bx, by, box, box, C["Spool"]))
        for j in range(3):
            ww = box * (0.62 if j != 1 else 0.44) * ease((u - at - 120) / 300)
            cv.add(rect(bx + 20, by + 32 + j * 28, ww, 6, C["Playhead"]))
        # the hash of the one before: a short Rewind bar at the card's bottom edge
        if i > 0:
            cv.add(rect(bx + 20, by + box - 22, 26 * ease((u - at - 200) / 300), 6, C["Rewind"]))
    rows = card["screen"]
    appear = [card["P"] + 150 * n + 100, card["P"] + 150 * n + 300]
    yy = y + box + 70
    for i, row in enumerate(rows):
        k = out_cubic((u - appear[i]) / RISE_MS)
        if k <= 0:
            continue
        base = yy + i * L["ROW_H"] + L["ROW"]
        cid = cv.clip(x - 10, base - L["ROW"] - 30, w + 20, L["ROW_H"])
        cv.add('<g clip-path="url(#%s)">' % cid)
        cv.text(kit.mono, row, L["ROW"], x, base + (1 - k) * 60, "Reel" if i == 0 else "Tape")
        cv.add("</g>")


def ui_view(L, u):
    """(source x, y, scale, window w, window h) of the timeline window at card time u. The whole column is held for
    UI_HOLD_MS, then the push: the scale grows geometrically while the window widens from the column's width to the
    full content width (X0..X1), so the close crop's step text reads at >= 24 px cap with no chip cut at the edge.
    The left edge (the red current-step stripe, where the wipe's playhead landed) never moves."""
    cx, cy, _, ch = UI_CROP
    cw = UI_COLUMN_X1 - cx
    x1, y1, w1, h1 = UI_CLOSE
    s0, s1 = UI_BOX_H / ch, (L["X1"] - L["X0"]) / w1
    e = ease((u - UI_HOLD_MS) / UI_PUSH_MS)
    s = s0 * (s1 / s0) ** e
    vw = cw * s0 + ((L["X1"] - L["X0"]) - cw * s0) * e
    f = (1 / s0 - 1 / s) / (1 / s0 - 1 / s1)
    # never past the timeline column's right edge: the diff pane beside it would show sliced at the window's edge
    vw = min(vw, (UI_COLUMN_X1 - cx) * s)
    return cx + (x1 - cx) * f, cy + (y1 - cy) * f, s, vw, UI_BOX_H


def draw_ui(cv, kit, L, card, t):
    """The real rewindagents ui timeline (screenshot of the demo session), its red current-step stripe placed where
    the wipe's playhead stops: the match cut. Then a push into step 14's chips and the step 15 Rewind row until they
    fill the content width. The command chip and the 127.0.0.1 note sit on one row under the window."""
    u = t - card["start"]
    sx, sy, s, vw, vh = ui_view(L, u)
    # a nested viewport onto the screenshot, not a clip on the whole scaled image: resvg drops most of an image that
    # large when it sits under the wipe's own clip and slide (r3 frames 79.2-79.5 s showed one row of it)
    strips = "".join('<image x="%d" y="%d" width="%d" height="%d" preserveAspectRatio="none" href="%s"/>'
                     % (UI_CROP[0], a, UI_COLUMN_X1 - UI_CROP[0], h, href)
                     for a, h, href in kit.ui_strips if a < sy + vh / s and a + h > sy)
    cv.add('<svg x="%.2f" y="%.2f" width="%.2f" height="%.2f" viewBox="%.3f %.3f %.3f %.3f" preserveAspectRatio="none">'
           '%s</svg>' % (L["X0"], UI_TOP, vw, vh, sx, sy, vw / s, vh / s, strips))
    cv.add(outline(L["X0"] - 1, UI_TOP - 1, vw + 2, vh + 2, "Rule", 1))
    if UI_TOP + vh > L["H"] - SAFE:
        raise SystemExit("the ui window runs into the bottom margin: %d" % (UI_TOP + vh))
    # the command chip and the 127.0.0.1 note on the headline's last baseline, right-aligned to X1 (the window takes
    # the room under it: r3 fix 2 needs a 576 px window to show step 14's header to step 15's last chip at 3x)
    cmd, note = card["screen"]
    hsize, hlines, hx = headline_layout(kit, L, card)
    last_words, last_base = hlines[-1]
    line_end = hx + kit.disp.width(" ".join(last_words), hsize, -0.01)
    size = 28
    mono_w = kit.mono.width("$ " + cmd, size)
    x0 = L["X1"] - (mono_w + 48 + 32 + kit.body.width(note, UI_LABEL))
    if x0 < line_end + 48:
        raise SystemExit("the ui chip and note do not fit beside the line: %r" % note)
    k = out_cubic((u - card["P"]) / RISE_MS)
    if k > 0:
        n = min(len(cmd), int(max(0, u - card["P"]) // TYPE_MS) + 1)
        dy = (1 - k) * 24
        base = last_base + dy
        cv.add(rect(x0, base - 15 - size * 0.8, mono_w + 48, size + 30, C["Spool"]))
        cv.text(kit.mono, "$ ", size, x0 + 24, base, "Playhead")
        cv.text(kit.mono, cmd[:n], size, x0 + 24 + kit.mono.width("$ ", size), base, "Leader")
        k2 = out_cubic((u - card["P"] - 500) / RISE_MS)
        if k2 > 0:
            cv.text(kit.body, note, UI_LABEL, x0 + mono_w + 48 + 32, last_base + (1 - k2) * 24, "Tape")


def draw_end(cv, kit, L, cfg, card, t):
    lg = kit.logo
    W, H = L["W"], L["H"]
    wide = W > H
    u = t - card["start"]
    ww, wh, body = lg.wordmark(kit.logo_disp, lg.THEMES["dark"])
    target = 980 if wide else 860
    s = target / ww
    x = L["X0"] if wide else (W - target) / 2
    top = 450 if wide else 920
    # the end card builds with its line, not after it: the wordmark rises while the line's words do, so the wipe
    # never lands on a near-empty frame and the whole card is settled for the last ~4 s (fixes 6 and 7)
    P = card["hs"] + 300

    def rise(at, h):
        k = out_cubic((u - at) / 420)
        return k, (1 - k) * h

    k, dy = rise(P, 60)
    if k > 0:
        cid = cv.clip(0, top - 20, W, wh * s + 40)
        cv.add('<g clip-path="url(#%s)"><g transform="translate(%.2f %.2f) scale(%.4f)">%s</g></g>'
               % (cid, x, top + dy, s, body))
    y = top + wh * s + (70 if wide else 110)
    psize = 46 if wide else 60                  # on a phone (9:16) every end-card line reads at >= 40 px cap (fix 10)
    promise = vsl.PROMISE
    plines = [promise] if wide else [promise.split(": ")[0] + ":", promise.split(": ")[1]]
    k, dy = rise(P + 160, 40)
    for line in plines:
        if k > 0:
            cv.text(kit.body, line, psize, x, y + dy, "Playhead")
        y += psize * 1.3
    url = cfg["site_url"]
    usize = 34.0 if wide else 64.0
    if not wide and kit.mono.width(url, usize) > target:      # a phone shows the address as it is typed
        url = re.sub(r"^https?://", "", url).rstrip("/")
    ulines = [url]
    if kit.mono.width(url, usize) > target:
        cut = url.index("/", len("https://")) + 1
        ulines = [url[:cut], url[cut:]]
    y += 30
    k, dy = rise(P + 300, 30)
    for line in ulines:
        if k > 0:
            cv.text(kit.mono, line, usize, x, y + dy, "Leader")
        y += usize * 1.35
    y += 16
    cv.add(rect(x, y, target * ease((u - P - 420) / 500), 1.5, C["Rule"]))
    csize = 32 if wide else 52
    y += 30 + csize
    k, dy = rise(P + 520, 20)
    if k > 0:
        cv.text(kit.body, vsl.CREDIT, csize, x, y + dy, "Playhead")


def draw_scene(cv, kit, L, cfg, p, card, t, swap=True, erase=None):
    """One card's content at time t (no ruler, no transition): its line, its proof, the slow push. `erase` = the
    wipe's playhead on screen less this scene's own slide (the outgoing scene of a wipe, see draw_headline)."""
    u = t - card["start"]
    dark = card["kind"] == "end"
    scene_cards = [c for c in p["cards"] if c["scene"] == card["scene"]]
    s0, s1 = scene_cards[0]["start"], scene_cards[-1]["end"]
    push = 1 + PUSH * ease((t - s0) / max(1, s1 - s0))
    if card["kind"] == "ui":
        push = 1.0                                   # the screenshot has its own push, anchored on step 15
    ax, ay = L["X0"], L["PROOF"]
    dy = card.get("dy", 0)
    cv.add('<g transform="translate(%.2f %.2f) scale(%.5f) translate(%.2f %.2f)">' % (ax, ay, push, -ax, -ay))
    cv.add('<g transform="translate(0 %d)">' % dy)
    if card["cont"] and swap and u < SWAP_MS:
        prev = p["cards"][card["i"] - 1]
        draw_headline(cv, kit, L, prev, prev["end"] - prev["start"], leaving=u)
    if card["d"].get("chapter"):
        draw_chapter(cv, kit, L, p, card, u)
    draw_headline(cv, kit, L, card, u, dark=dark,
                  erase=None if erase is None else (ax + (erase[0] - ax) / push, erase[1]))
    if dark:
        draw_end(cv, kit, L, cfg, card, t)
    else:
        cv.add('<g transform="translate(0 %d)">' % card["pshift"])
        draw_proof(cv, kit, L, card, t, p)
        cv.add("</g>")
    cv.add("</g></g>")


def frame(kit, L, p, cfg, t):
    card = next(c for c in p["cards"] if c["start"] <= t < c["end"])
    u = t - card["start"]
    dark = card["kind"] == "end"
    wiping = bool(card["wipe"]) and u < card["wipe_ms"]
    prev = p["cards"][card["i"] - 1] if card["i"] > 0 else None
    ground = "Reel" if dark and not wiping else "Leader"
    cv = Canvas(L["W"], L["H"], ground)
    if wiping:
        wp = WIPES[card["wipe"]]
        x = u / card["wipe_ms"]
        k = out_cubic(x) if wp["ease"] == "out" else ease(x)
        stop = L["X0"] if card["kind"] == "ui" else -40        # the match cut: the playhead becomes the UI's stripe
        lx = L["W"] + 40 + (stop - L["W"] - 40) * k
        # the old scene, left of the playhead, sliding back under it
        cid = cv.clip(0, 0, max(0.0, lx), L["H"])
        cv.add('<g clip-path="url(#%s)">' % cid)
        if prev["kind"] == "end":
            cv.add(rect(0, 0, L["W"], L["H"], C["Reel"]))
        cv.add('<g transform="translate(%.2f 0)">' % (wp["slide"] * k))
        # the outgoing line fades ahead of the playhead and, on time, is gone by the time the incoming line's first
        # word starts (on a 9:16 frame the incoming slide puts words right of the playhead almost at once)
        draw_scene(cv, kit, L, cfg, p, prev, prev["end"] - 1, swap=False,
                   erase=(lx - wp["slide"] * k, 1 - ease(u / WIPE_HEAD_MS)))
        cv.add("</g></g>")
        # the new scene, right of it, sliding in from the right as the playhead crosses (it lands as k -> 1), so the
        # two scenes part at the playhead instead of meeting on one baseline (review-textcut-r2.json fix 1)
        cid = cv.clip(lx, 0, L["W"] - lx, L["H"])
        cv.add('<g clip-path="url(#%s)">' % cid)
        if dark:
            cv.add(rect(0, 0, L["W"], L["H"], C["Reel"]))
        cv.add('<g transform="translate(%.2f 0)">' % (wp["slide"] * (1 - k)))
        draw_scene(cv, kit, L, cfg, p, card, t)
        cv.add("</g></g>")
    else:
        draw_scene(cv, kit, L, cfg, p, card, t)
    if not dark or wiping:
        bracket = card["d"].get("brackets") if u >= card["P"] - 200 else None
        if t >= p["ruled_from"]:
            if wiping and dark:
                cv.add('<g clip-path="url(#%s)">' % cv.clip(0, 0, max(0.0, lx), L["H"]))
            # one Record playhead on screen at a time: the ruler's is hidden while the wipe's runs, then drops back
            # into place at the new step (fix 7)
            head = 1.0
            if card["wipe"]:
                head = None if wiping else ease((u - card["wipe_ms"]) / HEAD_DROP_MS)
            draw_ruler(cv, kit, L, ruler_state(p, t), brackets=bracket, head=head)
            if wiping and dark:
                cv.add("</g>")
    if wiping:
        top = L["RULER_Y"] - 66
        lw = wp["line"]
        cv.add(rect(lx - lw / 2, top + 16, lw, L["H"] - top, C["Record"]))
        cv.add(playhead_shape(lx, top, wp["head"], "Record"))
        for off, op in wp["trail"]:                       # the tape running back: a trail, longer the bigger the rewind
            cv.add('<rect x="%.2f" y="%.2f" width="1.5" height="%.2f" fill="%s" opacity="%.2f"/>'
                   % (lx + off * (1 - k * 0.3), top + 16, L["H"] - top, C["Rule"], op * (1 - abs(2 * k - 1))))
    palette = {v.upper() for v in C.values()}
    svg = cv.svg()
    off = {f.upper() for f in re.findall(r'(?:fill|stroke)="(#[0-9A-Fa-f]{6})"', svg)} - palette
    if off:
        raise SystemExit("colours outside the palette: %s" % sorted(off))
    return svg, card["id"], card["beat"]["text"]


# ---- sound ----------------------------------------------------------------------------------------------------
BED_FILES = ("bed-vsl-90s.wav", "bed-vsl-30s.wav", "bed-vsl-15s-vertical.wav", "sfx-rewind.wav", "sfx-tick.wav")


def bed_python():
    """The interpreter for audio/make_bed.py: $REWINDAGENTS_BED_PYTHON, else this one, else the Creative Studio's venv
    (where the pinned numpy/scipy/pyloudnorm/soundfile of audio/requirements.txt live); None when none can import them."""
    cands = [os.environ.get("REWINDAGENTS_BED_PYTHON"), sys.executable,
             os.path.expanduser("~/ai-creative-studio/.venv-voice/bin/python")]
    for c in cands:
        if c and os.path.isfile(c) and subprocess.run(
                [c, "-c", "import numpy, scipy, pyloudnorm, soundfile"], capture_output=True).returncode == 0:
            return c
    return None


def ensure_beds():
    """The WAVs are not committed (.gitignore; review-textcut-r2.json fix 4): rebuild them from audio/make_bed.py when
    any is missing. The generator is deterministic, so the manifest's audio sha256 say whether the rebuild matches."""
    if all(os.path.isfile(os.path.join(AUDIO_DIR, f)) for f in BED_FILES):
        return
    py = bed_python()
    if not py:
        print("render.py: audio/*.wav missing and no Python with audio/requirements.txt; the synth fallback stands in "
              "(set REWINDAGENTS_BED_PYTHON)", file=sys.stderr)
        return
    subprocess.run([py, os.path.join(AUDIO_DIR, "make_bed.py"), "--beats", os.path.join(HERE, "beats.json"),
                    "--out", AUDIO_DIR], check=True)


def studio_audio(name):
    """The studio's files for this cut, or None when any is missing: (bed, rewind sfx, tick sfx)."""
    paths = (os.path.join(AUDIO_DIR, "bed-%s.wav" % name), os.path.join(AUDIO_DIR, "sfx-rewind.wav"),
             os.path.join(AUDIO_DIR, "sfx-tick.wav"))
    return paths if all(os.path.isfile(x) and os.path.getsize(x) > 44 for x in paths) else None


def score(name, total_ms, p, path):
    """The film's sound, written to `path` (48 kHz stereo WAV, before mastering); returns what it is made of.

    The studio's produced bed (brand/vsl/audio/bed-<name>.wav, see AUDIO.md there for its source and licence) is
    used when it and both SFX are on disk: trimmed or padded to the film, a 20 ms fade in, FADE_MS out, with
    sfx-rewind.wav under the wipes and sfx-tick.wav on the ruler's ticks (sfx_events). Only when a file is missing
    does the old synthesised pad stand in (synth_score), and the manifest says so ("source": "synth fallback")."""
    ev = sfx_events(p)
    files = studio_audio(name)
    if not files:
        synth_score(total_ms, ev, path)
        return {"source": "synth fallback: brand/vsl/audio/ files missing; render.py synth_score(), 84 BPM Am-F-C-G "
                          "sine pad (placeholder, not release grade)", "files": {}}
    bed, rew, tic = files
    T = total_ms / 1000
    graph = ["[0:a]aresample=%d,aformat=sample_fmts=fltp:channel_layouts=stereo,apad,atrim=0:%.3f,"
             "afade=t=in:d=0.02,afade=t=out:st=%.3f:d=%.3f[bed]" % (SAMPLE_RATE, T, T - FADE_MS / 1000, FADE_MS / 1000)]
    labels = ["[bed]"]
    for idx, (key, src) in ((1, ("rewind", rew)), (2, ("tick", tic))):
        events = ev[key]
        if not events:
            continue
        graph.append("[%d:a]aresample=%d,aformat=sample_fmts=fltp:channel_layouts=stereo,asplit=%d%s"
                     % (idx, SAMPLE_RATE, len(events), "".join("[%s%d]" % (key, j) for j in range(len(events)))))
        for j, (ms, gain) in enumerate(events):
            at = max(0, ms - (REWIND_LAND_MS if key == "rewind" else 0))     # the rewind sound lands on the event
            graph.append("[%s%d]volume=%.3f,adelay=%d:all=1[%s%dd]" % (key, j, gain, int(round(at)), key, j))
            labels.append("[%s%dd]" % (key, j))
    # AUDIO.md: ticks and sweeps land on bed peaks, so the sum goes through the studio's limiter before mastering
    graph.append("%samix=inputs=%d:normalize=0:duration=first,atrim=0:%.3f,%s[out]" % ("".join(labels), len(labels), T,
                                                                                     LIMITER))
    script = path + ".filter"
    with open(script, "w", encoding="utf-8") as f:
        f.write(";\n".join(graph))
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", bed, "-i", rew, "-i", tic,
                    "-/filter_complex", script, "-map", "[out]", "-c:a", "pcm_s24le", "-ar", str(SAMPLE_RATE),
                    path], check=True)
    return {"source": "studio: brand/vsl/audio/ (bed-%s.wav, sfx-rewind.wav, sfx-tick.wav; AUDIO.md)" % name,
            "files": {os.path.relpath(x, BRAND): sha256(x) for x in files}}


def synth_score(total_ms, ev, path):
    """Fallback only (studio files missing): the old synthesised bed. 84 BPM, A minor / F / C / G, one chord a
    bar; pad (sine + a soft octave), a low root, a quiet tick every quarter note from 40 ms in, the event ticks and
    falling sweeps of sfx_events, the last chord faded over FADE_MS. Mono, 48 kHz, 16-bit."""
    sr = SAMPLE_RATE
    n = int(sr * total_ms / 1000)
    out = array.array("f", [0.0]) * n
    bar = 4 * 60.0 / 84
    chords = [(57, 60, 64), (53, 57, 60), (48, 52, 55), (55, 59, 62)]   # MIDI: Am, F, C, G

    def hz(m):
        return 440.0 * 2 ** ((m - 69) / 12)

    table = [math.sin(2 * math.pi * i / 4096) for i in range(4096)]
    nbars = int(math.ceil(total_ms / 1000 / bar)) + 1
    for b in range(nbars):
        chord = chords[b % 4]
        s0 = int(b * bar * sr)
        s1 = min(n, int((b + 1) * bar * sr) + int(0.25 * sr))
        if s0 >= n:
            break
        voices = [(hz(m), 0.050) for m in chord] + [(hz(m + 12), 0.012) for m in chord] + [(hz(chord[0] - 12), 0.060)]
        length = s1 - s0
        for f, amp in voices:
            step = f * 4096 / sr
            ph = random.Random(b * 31 + int(f)).random() * 4096
            for i in range(length):
                env = min(1.0, i / (0.35 * sr)) * min(1.0, (length - i) / (0.25 * sr))
                out[s0 + i] += amp * env * table[int(ph) & 4095]
                ph += step
    rnd = random.Random(7)
    click = [rnd.uniform(-1, 1) * math.exp(-i / (0.0025 * sr)) for i in range(int(0.03 * sr))]
    q = 60.0 / 84
    t = 0.04
    while t * 1000 < total_ms:
        s0 = int(t * sr)
        for i, v in enumerate(click):
            if s0 + i < n:
                out[s0 + i] += 0.05 * v
        t += q
    for ms, gain in ev["tick"]:
        s0 = int(ms * sr / 1000)
        for i, v in enumerate(click):
            if s0 + i < n:
                out[s0 + i] += 0.16 * gain * v
    for ms, gain in ev["rewind"]:
        s0 = int(ms * sr / 1000)
        dur = int(0.7 * sr)
        ph = 0.0
        for i in range(dur):
            if s0 + i >= n:
                break
            f = 900 * (1 - i / dur) + 140
            ph += f * 4096 / sr
            env = math.sin(math.pi * i / dur)
            out[s0 + i] += 0.07 * gain * env * table[int(ph) & 4095]
    fade = int(FADE_MS / 1000 * sr)
    for i in range(fade):
        out[n - fade + i] *= 1 - i / fade
    peak = max(abs(v) for v in out) or 1.0
    pcm = array.array("h", (int(32767 * 0.8 * v / peak) for v in out))
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def master(src, dst):
    """Measure the mix's integrated loudness, then one linear gain to TARGET_LUFS and the studio's limiter (a
    no-op unless the gain pushes a peak up): the bed's own dynamics are kept (loudnorm fell back to its dynamic mode
    on these beds, LRA 10-13 LU, and still let the 90 s reach -1.4 dBTP after AAC). Returns the measurement."""
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", src, "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True, check=True)
    i = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", p.stderr)[-1])
    lra = float(re.findall(r"LRA:\s+(-?[\d.]+) LU", p.stderr)[-1])
    tp = float(re.findall(r"Peak:\s+(-?[\d.]+) dBFS", p.stderr)[-1])
    gain = TARGET_LUFS - i
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-af",
                    "volume=%.2fdB,%s,aresample=%d" % (gain, LIMITER, SAMPLE_RATE), "-ar", str(SAMPLE_RATE),
                    "-c:a", "pcm_s24le", dst], check=True)
    return {"input_i": i, "input_lra": lra, "input_tp": tp, "gain_db": round(gain, 2)}


def loudness(path):
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-map", "0:a", "-af", "ebur128=peak=true",
                        "-f", "null", "-"], capture_output=True, text=True)
    i = re.findall(r"I:\s+(-?[\d.]+) LUFS", p.stderr)
    tp = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", p.stderr)
    return {"integrated_lufs": float(i[-1]) if i else None, "true_peak_dbfs": float(tp[-1]) if tp else None}


def stream_md5(mp4, stream):
    p = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", mp4, "-map", "0:%s" % stream,
                        "-c", "copy", "-f", "md5", "-"], capture_output=True, text=True, check=True)
    return p.stdout.strip().split("=", 1)[1]


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


# ---- build ----------------------------------------------------------------------------------------------------
def render_video(kit, video, cfg, cache):
    name = video["name"]
    L = LAYOUT[video["aspect"]]
    p = plan(video, cfg, L, kit)
    total = p["total"]
    nframes = total * FPS // 1000
    fdir = os.path.join(HERE, "frames", name)
    shutil.rmtree(fdir, ignore_errors=True)
    os.makedirs(fdir)
    uniq, seq, shown = [], [], []
    last = None
    for f in range(nframes):
        t = f * 1000 / FPS
        svg, bid, text = frame(kit, L, p, cfg, t)
        if svg != last:
            fn = "u%05d.svg" % len(uniq)
            with open(os.path.join(fdir, fn), "w", encoding="utf-8") as fh:
                fh.write(svg)
            uniq.append(fn)
            last = svg
        seq.append(len(uniq) - 1)
        if not shown or shown[-1] != text:
            shown.append(text)
    with open(os.path.join(fdir, "frames.json"), "w", encoding="utf-8") as fh:
        json.dump({"width": L["W"], "height": L["H"], "svgs": uniq}, fh)
    subprocess.run(["node", os.path.join(HERE, "render.mjs"), fdir, os.path.join(cache, "node_modules")], check=True)
    sdir = os.path.join(fdir, "seq")
    os.makedirs(sdir)
    for f, u in enumerate(seq):
        os.symlink(os.path.join(fdir, uniq[u][:-4] + ".png"), os.path.join(sdir, "%05d.png" % f))

    wav = os.path.join(fdir, "score.wav")
    sound = score(name, total, p, wav)
    mastered = os.path.join(fdir, "master.wav")
    pass1 = master(wav, mastered)
    mp4 = os.path.join(BRAND, name + ".mp4")
    # BT.709 matrix, limited range, and the file says so (review-textcut.json: color_range was untagged)
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-framerate", str(FPS), "-i", os.path.join(sdir, "%05d.png"),
           "-i", mastered, "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-tune", "animation",
           "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p", "-colorspace", "bt709",
           "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv", "-bsf:v", BT709_BSF,
           "-r", str(FPS), "-c:a", "aac", "-b:a", "160k",
           "-ac", "2", "-t", "%.3f" % (total / 1000), "-movflags", "+faststart", "-map_metadata", "-1",
           "-metadata", "title=" + video["title"], mp4]
    subprocess.run(cmd, check=True)
    shutil.copyfile(os.path.join(HERE, name + ".srt"), os.path.join(BRAND, name + ".srt"))

    # key frames from the finished file: the transition (mid-wipe or mid-swap), the middle and the last moment of
    # every card, so the contact sheet shows every transition as well as every settled frame
    kdir = os.path.join(HERE, "keyframes", name)
    shutil.rmtree(kdir, ignore_errors=True)
    os.makedirs(kdir)
    keys = []
    for c in p["cards"]:
        marks = [("a", c["start"] + (c["wipe_ms"] // 2 if not c["cont"] else SWAP_MS // 2)) if c["i"] > 0 else None,
                 ("b", (c["start"] + c["end"]) // 2), ("c", c["end"] - 120)]
        for tag, ms in [m for m in marks if m]:
            out = os.path.join(kdir, "%s%s.png" % (c["id"], tag))
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "%.3f" % (ms / 1000), "-i", mp4,
                            "-frames:v", "1", out], check=True)
            keys.append({"beat": c["id"], "ms": ms, "png": os.path.relpath(out, BRAND)})
    subprocess.run(["node", os.path.join(HERE, "sheet.mjs"), kdir, os.path.join(HERE, name + "-contact-sheet.png"),
                    os.path.join(cache, "node_modules")], check=True)

    facts = mp4_info(mp4)
    facts["bytes"] = os.path.getsize(mp4)
    facts["sha256"] = sha256(mp4)
    return {
        "mp4": name + ".mp4", "srt": name + ".srt", "aspect": video["aspect"], "fps": FPS,
        "width": L["W"], "height": L["H"], "storyboard_ms": total, "frames": nframes, "unique_frames": len(uniq),
        "beats": [{"id": c["id"], "kind": c["kind"], "start_ms": c["start"], "end_ms": c["end"],
                   "transition": "first" if c["i"] == 0 else ("swap" if c["cont"] else "%s (%s, %d ms)" % (
                       "match cut" if c["kind"] == "ui" else "rewind wipe", c["wipe"], c["wipe_ms"]))}
                  for c in p["cards"]],
        "cards_on_screen": shown,
        "audio": {"voice": "none: no voice over (John, 2026-11-12); the cards carry the words",
                  "music": sound["source"], "files": sound["files"], "bed_sha256": sha256(wav),
                  "sweeps_ms": sweeps(p), "ticks_ms": [int(t) for t, _ in sfx_events(p)["tick"]],
                  "master": LOUDNESS, "first_pass": pass1,
                  "measured": loudness(mp4), "audio_stream_md5": stream_md5(mp4, "a")},
        "keyframes": keys, "contact_sheet": "vsl/%s-contact-sheet.png" % name,
        "mp4_facts": facts,
    }


def main(argv):
    only = None
    if "--only" in argv:
        only = argv[argv.index("--only") + 1]
        argv = [a for a in argv if a not in ("--only", only)]
    cache = argv[0] if argv else os.path.join(ROOT, ".brandcache")
    with open(os.path.join(BRAND, "site", "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    kit = Kit(cache)
    ensure_beds()
    mpath = os.path.join(HERE, "manifest.json")
    manifest = {"videos": {}}
    if os.path.exists(mpath):
        with open(mpath, encoding="utf-8") as f:
            manifest = json.load(f)
    manifest.pop("narration", None)
    data = vsl.beats()
    manifest["beats_sha256"] = hashlib.sha256(vsl.read("brand", "vsl", "beats.json").encode("utf-8")).hexdigest()
    manifest["note"] = ("Written by brand/vsl/render.py. The address in the videos comes from brand/site/config.json "
                        "at render time; this file keeps no address.")
    for video in data["videos"]:
        if only and video["name"] != only:
            continue
        manifest["videos"][video["name"]] = render_video(kit, video, cfg, cache)
        v = manifest["videos"][video["name"]]
        print("%s: %d x %d, %.2f s, %d frames (%d unique), %d KB, loudness %s" % (
            video["name"], v["mp4_facts"]["width"], v["mp4_facts"]["height"], v["mp4_facts"]["seconds"],
            v["frames"], v["unique_frames"], v["mp4_facts"]["bytes"] // 1024, v["audio"]["measured"]))
    with open(mpath, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
        f.write("\n")


if __name__ == "__main__":
    main(sys.argv[1:])
