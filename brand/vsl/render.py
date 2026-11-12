"""Render the three VSLs (task RB4b) from brand/vsl/beats.json: brand/vsl-90s.mp4, brand/vsl-30s.mp4 and
brand/vsl-15s-vertical.mp4, each with its captions beside it (brand/<name>.srt, a copy of brand/vsl/<name>.srt).

What is on screen comes from beats.json and nowhere else: the lines of each beat's `screen`, placed by the
DIRECTION table below (which shot a beat is, which lines take the accent and when, where the step ruler's
playhead stands). Commands type at 25 characters a second, output prints a line at a time, as in the demo GIF.
The captions burnt into the picture are the cues of brand/vsl/build.py (the same cues as the .srt), so the
words on screen and in the sidecar file cannot drift. {site_url} and {repo_url} are filled from
brand/site/config.json here, at render time, and nowhere else.

Sound: no narration. The scripts were written for John's cloned voice, and that voice is approved for his
YouTube channels only (ai-creative-studio voice/VOICE_LOCK.json), so a product video waits for his yes
(state/NEEDS_JOHN.md in FIRE). Until then the captions carry the words, as most feed video is watched muted,
and the sound is a music bed this file synthesises (score()): a slow four-chord pad, a soft tick on every
quarter note like a tape counter, a firmer tick on every beat change and a short falling sweep under the
rewind. Made here, so there is no licence to check. Mastered with ffmpeg loudnorm; the measured loudness goes
into the manifest.

Look (BRAND.md): Leader ground, Spool terminal panels with Leader text, Playhead prompts, Rewind for the one
block to look at in a panel, Record for the one accent on paper and for the playhead of the step ruler that
runs across the top of every shot. The end card is Reel, like the end of a tape. Text is outlined from the
OFL font files, so frames render the same with no fonts installed.

Usage: .venv/bin/python brand/vsl/render.py [<.brandcache dir>] [--only NAME]
Needs fontTools in .venv, @fontsource packages and @resvg/resvg-js in .brandcache (brand/logo/requirements.txt),
node and ffmpeg (with libx264) on PATH. Writes the mp4s and .srt files in brand/, brand/vsl/manifest.json,
full-size key frames taken from the finished mp4s in brand/vsl/keyframes/ and a contact sheet per video.
Per-frame SVG/PNG sources go to brand/vsl/frames/ (git-ignored).
"""
import array
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
TYPE_MS = 40            # one character every 40 ms: 25 characters a second, as in the demo GIF
ENTER_MS = 250          # pause between the end of a typed command and its output
STREAM_MS = 60          # one output line every 60 ms
ACCENT_DELAY_MS = 300   # an accent lands this long after the last of its lines appears
STAGGER_MS = 600        # accents that land one per spoken item
SLOTS = 15              # the ruler has room for fifteen steps (the session has fourteen; the rewind is fifteen)
SAMPLE_RATE = 48000
SAFE = 60               # no text closer than this to a frame edge (feeds crop and overlay the edges)
LOUDNESS = "loudnorm=I=-16:TP=-1.5:LRA=7"

# Lines on screen that are commands (typed at a prompt) and lines that are terminal output; anything else in a
# terminal shot is a note set under or beside the panel. Same patterns as tests/test_vsl.py, plus `cd`.
COMMAND = re.compile(r"^(rewindagents|python3 -m rewindagents|pipx|pip|git|echo|cd)\b")
OUTPUT = re.compile(r"^\s*(\d+\s+(Read|Edit|Write|Bash|MultiEdit|NotebookEdit)\b|restore\s|session \w+: rewind|"
                    r"this rewind is step|[ MD?]{2,3}\S)")

# ---- direction: which shot each beat is and what changes in it -------------------------------------------
# kind: term (terminal panel), page (rows on paper), end (the end card).
# clear: start a fresh panel; otherwise the panel keeps the previous beat's lines and lines already on it are
#   not printed again. accent: groups of screen-line indexes, each [at_ms or None, [indexes]]; None lands
#   ACCENT_DELAY_MS after the lines appear (or at the start if they were already there), "stagger" lands one
#   group every STAGGER_MS. ruler: (ticks shown, playhead step), the playhead slides there at ruler_at ms.
# notes_side: notes set in a column beside a narrower panel. note_accent: the note index in Record.
# page: rows = the screen lines; accent_row / accent_word in Record, tape_rows in Tape, chain = the record
#   chain drawing, brackets = two brackets round a ruler tick.
DIRECTION = {
    "vsl-90s": {
        "b01": dict(kind="term", clear=True, ruler=(13, 13), accent=[[None, [0]]]),
        "b02": dict(kind="term", ruler=(14, 14), ruler_at=300, start=300, accent=[[None, [0, 1]]]),
        "b03": dict(kind="term", clear=True, accent=[[None, [4, 5]]]),
        "b04": dict(kind="term", clear=True, brackets=6, start=300, accent=[[None, [0]]]),
        "b05": dict(kind="term", clear=True, ruler=(14, 14), accent=[[None, [4, 5]]]),
        "b06": dict(kind="term", ruler=(14, 12), ruler_at=200, accent=[[200, [0]]]),
        "b07": dict(kind="term"),
        "b08": dict(kind="term", stagger=True, accent=[[None, [1]], [None, [1, 2]], [None, [1, 2, 3]],
                                                       [None, [1, 2, 3, 4]]]),
        "b09": dict(kind="term", ruler=(15, 12), ruler_at=400, accent=[[None, [0]]], note_accent=None),
        "b10": dict(kind="term", clear=True, accent=[[None, [4]]]),
        "b11": dict(kind="page", chain=True, accent_row=None),
        "b12": dict(kind="page", tape_rows=[0], copy=True),
        "b13": dict(kind="term", clear=True, brackets=13, accent=[[None, [0]]],
                    accent_word="[3 checkpointed]"),
        "b14": dict(kind="term", clear=True, notes_side=True),
        "b15": dict(kind="term", notes_side=True, note_accent=2),
        "b16": dict(kind="page", accent_word="reported"),
        "b17": dict(kind="term", clear=True, notes_side=True, note_accent=None),
        "b18": dict(kind="page", accent_row=3),
        "b19": dict(kind="page", heading=0, label="planned", tape_rows=[1, 2]),
        "b20": dict(kind="end"),
    },
    "vsl-30s": {
        "b01": dict(kind="term", clear=True, ruler=(13, 13), accent=[[None, [0]]]),
        "b02": dict(kind="term", ruler=(14, 14), ruler_at=300, start=300, accent=[[None, [0, 1]]]),
        "b03": dict(kind="term", clear=True, ruler=(14, 12), ruler_at=2300, accent=[[2300, [1]]]),
        "b04": dict(kind="term"),
        "b05": dict(kind="term", stagger=True, accent=[[None, [1]], [None, [1, 2]], [None, [1, 2, 3]],
                                                       [None, [1, 2, 3, 4]]]),
        "b06": dict(kind="term", ruler=(15, 12), extra_out=["  this rewind is step 15; undo it with: "
                                                            "rewindagents rewind 14 --session demo"],
                    accent=[[None, ["extra0"]]]),
        "b07": dict(kind="page", accent_row=0, tape_rows=[1]),
        "b08": dict(kind="end"),
    },
    "vsl-15s-vertical": {
        "b01": dict(kind="term", clear=True, ruler=(14, 14), accent=[[None, [0, 1]]]),
        "b02": dict(kind="term", start=150, accent=[[None, [0]]]),
        "b03": dict(kind="term", clear=True, ruler=(14, 12), ruler_at=900),
        "b04": dict(kind="term", accent=[[None, [0, 1, 2, 3]]]),
        "b05": dict(kind="end"),
    },
}

LAYOUT = {
    "16:9": dict(W=1920, H=1080, X0=160, X1=1760, RULER_Y=150, PANEL=(160, 230, 1600, 560), SIDE_W=1020,
                 MONO=30, LH=44, NOTE=34, NOTE_GAP=50, CAP=40, CAP_LH=54, CAP_BASE=966, CAP_CHARS=vsl.CAPTION_CHARS,
                 ROW=40, ROW_H=96, ROWS_TOP=330, TITLE=44),
    "9:16": dict(W=1080, H=1920, X0=80, X1=1000, RULER_Y=330, PANEL=(80, 430, 920, 720), SIDE_W=920,
                 MONO=40, LH=60, NOTE=44, NOTE_GAP=60, CAP=54, CAP_LH=70, CAP_BASE=1180, CAP_CHARS=28,
                 ROW=46, ROW_H=110, ROWS_TOP=560, TITLE=56),
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
    """One frame: SVG parts plus the glyphs they use, so <defs> holds each glyph once."""

    def __init__(self, W, H, ground):
        self.W, self.H, self.parts, self.used = W, H, [rect(0, 0, W, H, C[ground])], {}

    def add(self, s):
        self.parts.append(s)

    def text(self, font, text, size, x, base, colour, tracking=0.0):
        s = size / font.upm
        uses, cx = [], 0.0
        for ch in text:
            if font.d(ch):
                gid = "%s%d" % (font.prefix, ord(ch))
                self.used[gid] = (font, ch)
                uses.append('<use href="#%s" x="%.1f"/>' % (gid, cx))      # font units, like the paths
            cx += font.hmtx[font.cmap[ord(ch)]][0] + tracking * font.upm
        if uses:
            if x < SAFE or x + cx * s > self.W - SAFE or base > self.H - SAFE:
                raise SystemExit("text leaves the %d px safe margin: %r at x %.0f to %.0f, baseline %.0f"
                                 % (SAFE, text, x, x + cx * s, base))
            self.add('<g fill="%s" transform="translate(%.2f %.2f) scale(%.5f %.5f)">%s</g>'
                     % (C[colour], x, base, s, -s, "".join(uses)))
        return cx * s

    def svg(self):
        defs = "".join('<path id="%s" d="%s"/>' % (gid, f.d(ch)) for gid, (f, ch) in sorted(self.used.items()))
        return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d">'
                '<defs>%s</defs>%s</svg>\n' % (self.W, self.H, self.W, self.H, defs, "".join(self.parts)))


def rect(x, y, w, h, fill):
    return '<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" fill="%s"/>' % (x, y, w, h, fill)


def outline(x, y, w, h, colour, sw):
    return ('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" fill="none" stroke="%s" stroke-width="%g"/>'
            % (x + sw / 2, y + sw / 2, w - sw, h - sw, C[colour], sw))


def ease(p):
    p = min(max(p, 0.0), 1.0)
    return p * p * (3 - 2 * p)


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


# ---- the plan: every beat turned into timed events ---------------------------------------------------------
def fill(text, cfg):
    return text.replace("{site_url}", cfg["site_url"]).replace("{repo_url}", cfg["repo_url"])


def plan(video, cfg):
    """Absolute-time events for one video: panel lines, accents, notes, ruler moves, shots."""
    direction = DIRECTION[video["name"]]
    lines, accents, ruler, shots = [], [], [], []
    panel_has_cmd = False
    t0 = 0
    panel_id = 0
    for b in video["beats"]:
        d = direction[b["id"]]
        screen = [fill(s, cfg) for s in b["screen"]]
        shot = {"id": b["id"], "kind": d["kind"], "start": t0, "end": t0 + b["ms"], "d": d, "screen": screen,
                "notes": []}
        shots.append(shot)
        if "ruler" in d:
            ruler.append((t0 + d.get("ruler_at", 0), d["ruler"]))
        if d["kind"] == "term":
            if d.get("clear"):
                panel_id += 1
                panel_has_cmd = False
            shot["panel"] = panel_id
            t = t0 + d.get("start", 0)
            refs = {}
            todo = [(i, s) for i, s in enumerate(screen)]
            todo += [("extra%d" % i, s) for i, s in enumerate(d.get("extra_out", []))]
            for i, s in todo:
                if COMMAND.match(s.strip()):
                    if t == t0:
                        t += 200
                    ln = {"panel": panel_id, "kind": "cmd", "text": s.strip(), "at": t, "typed": t + TYPE_MS * len(s.strip())}
                    lines.append(ln)
                    refs[i] = ln
                    t = ln["typed"] + ENTER_MS
                    panel_has_cmd = True
                elif OUTPUT.match(s):
                    old = next((x for x in lines if x["panel"] == panel_id and x["text"] == s), None)
                    if old:
                        refs[i] = old
                        continue
                    ln = {"panel": panel_id, "kind": "out", "text": s, "at": t}
                    lines.append(ln)
                    refs[i] = ln
                    t += STREAM_MS
                else:
                    shot["notes"].append({"text": s, "at": t + 150, "index": len(shot["notes"])})
                    t += 150
            shot["prompt_after"] = t if panel_has_cmd else None
            shot["typing_end"] = t
            when = None
            for n, (at, idx) in enumerate(d.get("accent", [])):
                group = [refs[i] for i in idx if i in refs]
                if at is not None:
                    when = t0 + at
                elif d.get("stagger") and when is not None:
                    when += STAGGER_MS
                else:
                    new = [x["at"] for x in group if x["at"] >= t0]
                    when = (max(new) + ACCENT_DELAY_MS) if new else t0
                accents.append((when, panel_id, [id(x) for x in group]))
        t0 += b["ms"]
    # each panel is as tall as the most it ever shows (its lines plus the prompt), never a dark empty box
    rows = {}
    for ln in lines:
        rows[ln["panel"]] = rows.get(ln["panel"], 0) + 1
    return {"rows": rows, "lines": lines, "accents": sorted(accents, key=lambda a: a[0]), "ruler": ruler, "shots": shots,
            "total": t0}


def ruler_state(p, t):
    """(ticks shown, playhead position as a float step, growth 0..1 of a tick just added, ticks before it).
    The playhead slides from where the previous move settled, 140 ms a step, at most 900 ms."""
    n, ph, grow, before = 0, 0.0, 1.0, 0
    settled = None
    for at, (tn, tph) in p["ruler"]:
        if at > t:
            break
        start = float(tph) if settled is None else settled
        dur = min(900, 140 * abs(tph - start)) or 1
        ph = start + (tph - start) * ease((t - at) / dur)
        before = n
        grow = ease((t - at) / 200) if (settled is not None and tn > n) else 1.0
        n, settled = tn, float(tph)
    return n, ph, grow, before


def accent_ids(p, panel, t):
    """The lines of this panel in the accent colour at time t: the latest accent group that has landed."""
    ids = set()
    for at, pid, group in p["accents"]:
        if at <= t and pid == panel:
            ids = set(group)
    return ids


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


def draw_ruler(cv, L, state, brackets=None, mono=None):
    n, ph, grow, prev_n = state
    if n == 0:
        return
    x0, x1, y = L["X0"], L["X1"], L["RULER_Y"]
    pitch = (x1 - x0) / (SLOTS - 1)
    th = 26 if L["W"] > L["H"] else 30
    xs = [x0 + i * pitch for i in range(SLOTS)]
    last = xs[n - 1]
    php = x0 + (ph - 1) * pitch
    cv.add(rect(x0 - 2, y, php - x0 + 2, 2, C["Reel"]))
    cv.add(rect(php, y, max(0.0, last + 2 - php), 2, C["Rule"]))
    for i in range(n):
        h = th * (grow if (i == n - 1 and n > prev_n) else 1.0)
        step = i + 1
        cv.add(rect(xs[i] - 2, y - h, 4, h, C["Reel"] if step <= ph + 0.01 else C["Rule"]))
        size = 18 if L["W"] > L["H"] else 22
        label = str(step)                     # step numbers are text: Tape, never Rule (BRAND.md)
        w = mono.width(label, size)
        cv.text(mono, label, size, xs[i] - w / 2, y + 12 + size, "Tape")
    if brackets:
        bx = xs[brackets - 1]
        for side in (-1, 1):
            x = bx + side * pitch * 0.42
            cv.add(rect(x - 1, y - th - 16, 2, th + 30, C["Rule"]))
            cv.add(rect(min(x, x - side * 14), y - th - 16, 14, 2, C["Rule"]))
            cv.add(rect(min(x, x - side * 14), y + 12, 14, 2, C["Rule"]))
    # the playhead: the logo's editor handle on a line that ends on the rule
    k = 5.0 if L["W"] > L["H"] else 5.5
    head_w = 4 * k
    top = y - th - 40
    cv.add('<g transform="translate(%.2f %.2f) scale(%.3f)"><path d="M0 0H4V2L2.5 3.5H1.5L0 2Z" fill="%s"/></g>'
           % (php - head_w / 2, top, k, C["Record"]))
    cv.add(rect(php - 1.5, top + 3.5 * k - 1, 3, y + 2 - (top + 3.5 * k - 1), C["Record"]))


def pad_of(L):
    return 28 if L["W"] > L["H"] else 32


def panel_h(L, p, panel):
    """Height for a panel's content: title bar, padding, its rows plus the prompt (at least three), at most
    the layout's panel."""
    n = max(3, p["rows"].get(panel, 0) + 1)
    return min(L["PANEL"][3], L["TITLE"] + 2 * pad_of(L) + n * L["LH"] - (L["LH"] - L["MONO"]))


def draw_panel(cv, kit, L, p, shot, t, side):
    x, y, w, _ = L["PANEL"]
    h = panel_h(L, p, shot["panel"])
    if side:
        w = L["SIDE_W"]
    cv.add(rect(x, y, w, h, C["Spool"]))
    tb = L["TITLE"]
    cv.add(rect(x, y + tb - 1, w, 1, C["Rule"]))
    lg = kit.logo
    k = tb * 0.45 / lg.MARK_H
    cv.add(lg.place(lg.mark_shapes(lg.THEMES["dark"], mono=C["Leader"]), x + 24, y + (tb - lg.MARK_H * k) / 2, k))
    nsize = tb * 0.42
    cv.text(kit.disp, "rewindagents", nsize, x + 24 + 16 * k + 12, y + (tb + kit.disp.cap(nsize)) / 2, "Leader",
            tracking=-0.02)
    mono, size, lh = kit.mono, L["MONO"], L["LH"]
    pad = pad_of(L)
    rows = int((h - tb - 2 * pad + (lh - size)) // lh)
    hot = accent_ids(p, shot["panel"], t)
    visible = []
    for ln in p["lines"]:
        if ln["panel"] != shot["panel"] or ln["at"] > t:
            continue
        if ln["kind"] == "cmd":
            n = min(len(ln["text"]), int((t - ln["at"]) // TYPE_MS))
            done = t >= ln["typed"]
            visible.append([("$ ", "Playhead"), (ln["text"][:n], "Leader")] + ([] if done else [("", "cursor")]))
        else:
            colour = "Rewind" if id(ln) in hot else "Leader"
            word = shot["d"].get("accent_word")
            if word and colour == "Rewind" and word in ln["text"]:
                a = ln["text"].index(word)
                visible.append([(ln["text"][:a], "Leader"), (word, "Rewind"), (ln["text"][a + len(word):], "Leader")])
            else:
                visible.append([(ln["text"], colour)])
    shown = [ln for ln in p["lines"] if ln["panel"] == shot["panel"] and ln["at"] <= t]
    # the prompt comes back after output, not between a command and the output a later beat prints
    if shot.get("prompt_after") is not None and t >= shot["prompt_after"] and shown and shown[-1]["kind"] == "out":
        visible.append([("$ ", "Playhead"), ("", "cursor")])
    base0 = y + tb + pad + mono.cap(size)
    adv = mono.width("x", size)
    cols = int((w - 2 * pad) // adv)
    for r, segs in enumerate(visible[-rows:]):
        cx, base = x + pad, base0 + r * lh
        for text, colour in segs:
            if colour == "cursor":
                cv.add(rect(cx, base - size * 0.78, adv, size * 0.98, C["Leader"]))
                continue
            if len(text) > cols:
                raise SystemExit("line of %d characters does not fit %d columns: %r" % (len(text), cols, text))
            cv.text(mono, text, size, cx, base, colour)
            cx += adv * len(text)


def draw_notes(cv, kit, L, p, shot, t, side):
    x, y, w, _ = L["PANEL"]
    h = panel_h(L, p, shot["panel"])
    size, gap = L["NOTE"], L["NOTE_GAP"]
    acc = shot["d"].get("note_accent", "last" if len(shot["notes"]) == 1 else None)
    if side:
        nx, nw = x + L["SIDE_W"] + 56, w - L["SIDE_W"] - 56
        base = y + L["TITLE"] + 28 + kit.body.cap(size)
        for note in shot["notes"]:
            if note["at"] > t:
                continue
            colour = "Record" if acc == note["index"] else "Reel"
            cap = kit.body.cap(size)
            cv.add(rect(nx, base - cap / 2 - 5, 10, 10, C["Record"] if colour == "Record" else C["Rule"]))
            for line in wrap(kit.body, note["text"], size, nw - 28):
                cv.text(kit.body, line, size, nx + 28, base, colour)
                base += size * 1.25
            base += gap - size * 0.25
    else:
        base = y + h + 24 + kit.body.cap(size) + 10
        for note in shot["notes"]:      # under a panel that has the Rewind block: Tape, one accent per view
            if note["at"] > t:
                continue
            colour = "Tape"
            for line in wrap(kit.body, note["text"], size, w):
                cv.text(kit.body, line, size, x, base, colour)
                base += size * 1.3


def draw_page(cv, kit, L, shot, t):
    d, rows = shot["d"], shot["screen"]
    x, w = L["X0"], L["X1"] - L["X0"]
    size, rh = L["ROW"], L["ROW_H"]
    y = L["ROWS_TOP"]
    t_in = t - shot["start"]
    if d.get("chain"):
        n, box, gap = 7, 120, 0
        span = (w - n * box) / (n - 1)
        broken = t_in >= shot["end"] - shot["start"] - 2600
        for i in range(n):
            bx = x + i * (box + span)
            if i < n - 1:
                lx, lw = bx + box, span
                if broken and i == 3:
                    cv.add(rect(lx, y + box / 2 - 1, lw * 0.35, 2, C["Rule"]))
                    cv.add(rect(lx + lw * 0.65, y + box / 2 - 1, lw * 0.35, 2, C["Rule"]))
                else:
                    cv.add(rect(lx, y + box / 2 - 1, lw, 2, C["Rule"]))
            cv.add(rect(bx, y, box, box, C["Spool"]))
            for j in range(3):
                ww = box * (0.62 if j != 1 else 0.44)
                cv.add(rect(bx + 18, y + 30 + j * 26, ww, 6, C["Playhead"]))
            if broken and i == 4:
                cv.add(outline(bx - 8, y - 8, box + 16, box + 16, "Record", 4))
        y += box + 90
    if d.get("copy"):
        box = 120
        cv.add(rect(x, y, box, box, C["Spool"]))
        for j in range(3):
            cv.add(rect(x + 18, y + 30 + j * 26, box * (0.62 if j != 1 else 0.44), 6, C["Playhead"]))
        k = ease((t_in - 900) / 700)
        cx = x + 200 + 120 * k
        if t_in > 900:
            cv.add(rect(x + box, y + box / 2 - 1, cx - x - box, 2, C["Rule"]))
            cv.add(rect(cx, y, box, box, C["Leader"]))
            cv.add(outline(cx, y, box, box, "Record", 4))
            for j in range(3):
                cv.add(rect(cx + 18, y + 30 + j * 26, box * (0.62 if j != 1 else 0.44), 6, C["Tape"]))
        y += box + 90
    for i, row in enumerate(rows):
        at = 200 + i * 250
        if t_in < at:
            continue
        base = y + i * rh + size
        if i == d.get("heading"):
            hsize = size * 1.5
            label = d.get("label")
            head = row[:-len(label)].rstrip() if label and row.endswith(label) else row
            adv = cv.text(kit.disp, head, hsize, x, base, "Reel", tracking=-0.02)
            if head != row:                  # the status as an outlined label in Record, beside the heading
                lw = kit.mono.width(label, size * 0.8)
                lx = x + adv + 28
                cv.add(outline(lx, base - size * 0.8 - 14, lw + 32, size * 0.8 + 28, "Record", 3))
                cv.text(kit.mono, label, size * 0.8, lx + 16, base, "Record")
            continue
        if COMMAND.match(row):
            mono_w = kit.mono.width("$ " + row, size)
            cv.add(rect(x, base - size - 22, mono_w + 56, size + 44, C["Spool"]))
            cv.text(kit.mono, "$ ", size, x + 28, base, "Playhead")
            cv.text(kit.mono, row, size, x + 28 + kit.mono.width("$ ", size), base, "Leader")
            continue
        colour = "Record" if i == d.get("accent_row") else ("Tape" if i in d.get("tape_rows", []) else "Reel")
        x_row = x
        word = d.get("accent_word")
        if word and word in row:
            a = row.index(word)
            cx = x_row + cv.text(kit.mono, row[:a], size, x_row, base, colour)
            cx += cv.text(kit.mono, word, size, cx, base, "Record")
            cv.text(kit.mono, row[a + len(word):], size, cx, base, colour)
        else:
            cv.text(kit.mono, row, size, x_row, base, colour)
        cv.add(rect(x, base + rh - size - 26, w, 1.5, C["Rule"]))


def draw_end(cv, kit, L, cfg):
    lg = kit.logo
    W, H = L["W"], L["H"]
    wide = W > H
    ww, wh, body = lg.wordmark(kit.logo_disp, lg.THEMES["dark"])
    target = 980 if wide else 860
    s = target / ww
    x = L["X0"] if wide else (W - target) / 2
    top = 270 if wide else 380
    cv.add('<g transform="translate(%.2f %.2f) scale(%.4f)">%s</g>' % (x, top, s, body))
    y = top + wh * s + (70 if wide else 110)
    psize = 46 if wide else 56
    promise = vsl.PROMISE
    plines = [promise] if wide else [promise.split(": ")[0] + ":", promise.split(": ")[1]]
    for line in plines:
        cv.text(kit.body, line, psize, x, y, "Playhead")
        y += psize * 1.3
    url = cfg["site_url"]
    # the address on one line if it fits the wordmark's width at a readable size, else broken after the host
    usize = 34.0 if wide else 36.0
    ulines = [url]
    if kit.mono.width(url, usize) > target:
        cut = url.index("/", len("https://")) + 1
        ulines = [url[:cut], url[cut:]]
    y += 30
    for line in ulines:
        cv.text(kit.mono, line, usize, x, y, "Leader")
        y += usize * 1.35
    y += 16
    cv.add(rect(x, y, target, 1.5, C["Rule"]))
    csize = 28 if wide else 40
    y += 30 + csize
    cv.text(kit.body, vsl.CREDIT, csize, x, y, "Playhead")


def caption_lines(cue_lines, L, kit):
    if L["CAP_CHARS"] >= vsl.CAPTION_CHARS:
        return cue_lines
    return vsl.wrap_caption(" ".join(cue_lines), L["CAP_CHARS"])


def draw_caption(cv, kit, L, cues, t, dark):
    for start, end, lines in cues:
        if start <= t < end:
            lines = caption_lines(lines, L, kit)
            base = L["CAP_BASE"] if L["W"] > L["H"] else L["CAP_BASE"] + (4 - len(lines)) * L["CAP_LH"] // 2
            for line in lines:
                if kit.bold.width(line, L["CAP"]) > L["X1"] - L["X0"]:
                    raise SystemExit("caption too wide: %r" % line)
                cv.text(kit.bold, line, L["CAP"], L["X0"], base, "Leader" if dark else "Reel")
                base += L["CAP_LH"]
            return " ".join(lines)
    return ""


def frame(kit, L, p, cues, cfg, t):
    shot = next(s for s in p["shots"] if s["start"] <= t < s["end"])
    d = shot["d"]
    dark = d["kind"] == "end"
    cv = Canvas(L["W"], L["H"], "Reel" if dark else "Leader")
    if dark:
        draw_end(cv, kit, L, cfg)
    else:
        draw_ruler(cv, L, ruler_state(p, t), brackets=d.get("brackets"), mono=kit.mono)
        if d["kind"] == "term":
            side = d.get("notes_side", False)
            draw_panel(cv, kit, L, p, shot, t, side)
            draw_notes(cv, kit, L, p, shot, t, side)
        else:
            draw_page(cv, kit, L, shot, t)
    cap = draw_caption(cv, kit, L, cues, t, dark)
    palette = {v.upper() for v in C.values()}
    svg = cv.svg()
    off = {f.upper() for f in re.findall(r'(?:fill|stroke)="(#[0-9A-Fa-f]{6})"', svg)} - palette
    if off:
        raise SystemExit("colours outside the palette: %s" % sorted(off))
    return svg, shot["id"], cap


# ---- sound ----------------------------------------------------------------------------------------------------
def score(total_ms, beat_starts, sweep_at, path):
    """Synthesise the music bed: 84 BPM, A minor / F / C / G, one chord a bar; pad (sine + a soft octave),
    a low root, a quiet tick every quarter note, a firmer tick on every beat change, a falling sweep under the
    rewind, the last chord held and faded over the final 1.5 s. Mono, 48 kHz, 16-bit."""
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
    t = 0.0
    while t * 1000 < total_ms:
        s0 = int(t * sr)
        for i, v in enumerate(click):
            if s0 + i < n:
                out[s0 + i] += 0.05 * v
        t += q
    for ms in beat_starts:
        s0 = int(ms * sr / 1000)
        for i, v in enumerate(click):
            if s0 + i < n:
                out[s0 + i] += 0.16 * v
    for ms in sweep_at:
        s0 = int(ms * sr / 1000)
        dur = int(0.7 * sr)
        ph = 0.0
        for i in range(dur):
            if s0 + i >= n:
                break
            f = 900 * (1 - i / dur) + 140
            ph += f * 4096 / sr
            env = math.sin(math.pi * i / dur)
            out[s0 + i] += 0.07 * env * table[int(ph) & 4095]
    fade = int(1.5 * sr)
    for i in range(fade):
        out[n - fade + i] *= 1 - i / fade
    peak = max(abs(v) for v in out) or 1.0
    pcm = array.array("h", (int(32767 * 0.8 * v / peak) for v in out))
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def loudness(path):
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-map", "0:a", "-af", "ebur128=peak=true",
                        "-f", "null", "-"], capture_output=True, text=True)
    i = re.findall(r"I:\s+(-?[\d.]+) LUFS", p.stderr)
    tp = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", p.stderr)
    return {"integrated_lufs": float(i[-1]) if i else None, "true_peak_dbfs": float(tp[-1]) if tp else None}


# ---- build ----------------------------------------------------------------------------------------------------
def render_video(kit, video, cfg, cache):
    name = video["name"]
    L = LAYOUT[video["aspect"]]
    p = plan(video, cfg)
    cues = vsl.cues(video)
    total = p["total"]
    nframes = total * FPS // 1000
    fdir = os.path.join(HERE, "frames", name)
    shutil.rmtree(fdir, ignore_errors=True)
    os.makedirs(fdir)
    uniq, seq, shown_caps = [], [], []
    last = None
    for f in range(nframes):
        t = f * 1000 / FPS
        svg, bid, cap = frame(kit, L, p, cues, cfg, t)
        if svg != last:
            fn = "u%05d.svg" % len(uniq)
            with open(os.path.join(fdir, fn), "w", encoding="utf-8") as fh:
                fh.write(svg)
            uniq.append(fn)
            last = svg
        seq.append(len(uniq) - 1)
        if cap and (not shown_caps or shown_caps[-1] != cap):
            shown_caps.append(cap)
    with open(os.path.join(fdir, "frames.json"), "w", encoding="utf-8") as fh:
        json.dump({"width": L["W"], "height": L["H"], "svgs": uniq}, fh)
    subprocess.run(["node", os.path.join(HERE, "render.mjs"), fdir, os.path.join(cache, "node_modules")], check=True)
    sdir = os.path.join(fdir, "seq")
    os.makedirs(sdir)
    for f, u in enumerate(seq):
        os.symlink(os.path.join(fdir, uniq[u][:-4] + ".png"), os.path.join(sdir, "%05d.png" % f))

    beat_starts = [s["start"] for s in p["shots"]]
    sweeps = [ln["typed"] + ENTER_MS for ln in p["lines"] if ln["kind"] == "cmd" and ln["text"].startswith("rewindagents rewind")]
    wav = os.path.join(fdir, "score.wav")
    score(total, beat_starts, sweeps, wav)
    mp4 = os.path.join(BRAND, name + ".mp4")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-framerate", str(FPS), "-i", os.path.join(sdir, "%05d.png"),
           "-i", wav, "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-tune", "animation",
           "-pix_fmt", "yuv420p", "-r", str(FPS), "-af", LOUDNESS + ",aresample=48000", "-c:a", "aac", "-b:a", "160k",
           "-ac", "2", "-t", "%.3f" % (total / 1000), "-movflags", "+faststart", "-metadata", "title=" + video["title"], mp4]
    subprocess.run(cmd, check=True)
    shutil.copyfile(os.path.join(HERE, name + ".srt"), os.path.join(BRAND, name + ".srt"))

    # key frames from the finished file: the middle and the last moment of every beat
    kdir = os.path.join(HERE, "keyframes", name)
    shutil.rmtree(kdir, ignore_errors=True)
    os.makedirs(kdir)
    keys = []
    for s in p["shots"]:
        for tag, ms in (("a", (s["start"] + s["end"]) // 2), ("b", s["end"] - 200)):
            out = os.path.join(kdir, "%s%s.png" % (s["id"], tag))
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "%.3f" % (ms / 1000), "-i", mp4,
                            "-frames:v", "1", out], check=True)
            keys.append({"beat": s["id"], "ms": ms, "png": os.path.relpath(out, BRAND)})
    subprocess.run(["node", os.path.join(HERE, "sheet.mjs"), kdir, os.path.join(HERE, name + "-contact-sheet.png"),
                    os.path.join(cache, "node_modules")], check=True)

    facts = mp4_info(mp4)
    facts["bytes"] = os.path.getsize(mp4)
    facts["sha256"] = hashlib.sha256(open(mp4, "rb").read()).hexdigest()
    return {
        "mp4": name + ".mp4", "srt": name + ".srt", "aspect": video["aspect"], "fps": FPS,
        "width": L["W"], "height": L["H"], "storyboard_ms": total, "frames": nframes, "unique_frames": len(uniq),
        "beats": [{"id": s["id"], "kind": s["kind"], "start_ms": s["start"], "end_ms": s["end"]} for s in p["shots"]],
        "captions_burnt_in": shown_caps,
        "audio": {"voice": "none: captions carry the words until John approves his cloned voice for product videos",
                  "music": "synthesised by render.py score(), 84 BPM Am-F-C-G pad, quarter-note ticks, beat-change ticks, "
                           "a sweep under the rewind", "master": LOUDNESS, "measured": loudness(mp4)},
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
    mpath = os.path.join(HERE, "manifest.json")
    manifest = {"videos": {}}
    if os.path.exists(mpath):
        with open(mpath, encoding="utf-8") as f:
            manifest = json.load(f)
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
