"""Build brand/demo.gif (task RB2b): a wrecked project put back by `rewindagent rewind`, in under 20 seconds,
every line of it real.

brand/demo/scenario.py makes a small project in a temp folder, runs fourteen agent steps through the real
Claude Code hook (the last two delete the tests and overwrite the config), then runs the four commands the
clip shows and records what they printed. The frames are drawn from that record, so the GIF cannot show
output the code does not produce. tests/test_demo.py plays the same scenario and compares every line, and
reads the finished GIF's size, frame count, play time, delays and colour table with brand/demo/gifinfo.py.

Look (BRAND.md): the light Leader ground with a Spool terminal on it, text in Leader, comments and the prompt
in Playhead, and Rewind for the one block to look at in a view: the two steps that wrecked the repo, then the
restored files. The mark sits in the title bar in mono Leader, so Rewind stays the one accent. Text is
outlined from the OFL font files (Commit Mono for the terminal, Bricolage Grotesque for the name, Hanken
Grotesk for the small print), so the frames render the same with no fonts installed.

Usage: .venv/bin/python brand/demo/build.py [<.brandcache dir>]
Run it with the venv Python that has rewindagent installed, so the undo hint the clip shows is the one the
installed command prints. Needs fontTools in .venv and the @fontsource packages plus @resvg/resvg-js in
.brandcache (brand/logo/requirements.txt), node and ffmpeg on PATH. Writes brand/demo.gif,
brand/demo/manifest.json (storyboard, timing, GIF facts), brand/demo/keyframes/*.png (full size, for looking
at) and brand/demo/contact-sheet.png.
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BRAND = os.path.dirname(HERE)
ROOT = os.path.dirname(BRAND)
sys.path.insert(0, BRAND)
sys.path.insert(0, HERE)

import rewindagent  # noqa: E402
from rewindagent import cli  # noqa: E402
from contrast_check import PALETTE as C  # noqa: E402
from gifinfo import info as gif_info  # noqa: E402
import scenario  # noqa: E402


def load_logo_build():
    spec = importlib.util.spec_from_file_location("logo_build", os.path.join(BRAND, "logo", "build.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---- timing (every duration on ffmpeg's 40 ms grid) --------------------------------------------------------
GRID = 0.04
FIRST_DT, CAPTION_DT, TYPE_DT, ENTER_DT, STREAM_DT = 0.40, 0.40, 0.08, 0.16, 0.04
TYPE_CHARS = 2                  # characters per typing frame: 25 characters a second
MAX_SECONDS = 20.0              # BRAND_KIT.md: demo.gif, real product, <= 20 s

# ---- layout -----------------------------------------------------------------------------------------------
W, H = 1200, 675
PX, PY, PW, PH = 40, 40, 1120, 580          # the terminal (Spool) on the Leader ground
TITLE_H = 44
FONT, LH = 17.0, 26                         # terminal text size and line pitch
TX = PX + 28                                # text left edge
BASE0 = PY + TITLE_H + 20 + 14              # first baseline
ROWS = (PH - TITLE_H - 40) // LH            # lines that fit; older lines leave at the top, as in a terminal
NAME = "rewindagent"
TAGLINE = "Ctrl+Z for AI coding agents"
CREDIT = "made by John B Joseph"
COLOURS = {"caption": "Playhead", "prompt": "Playhead", "command": "Leader", "output": "Leader",
           "accent": "Rewind", "cursor": "Leader"}
FORBIDDEN_TEXT = ("/var/", "/private/", "/tmp", "/Users/", "/home/")   # the project's path never shows


def storyboard(beats):
    """Frames from the recorded beats. A frame is (lines, seconds); a line is a list of (text, role)
    segments; a ("", "cursor") segment draws a block. Returns (frames, key frame indexes)."""
    frames, keyframes, lines = [], [], []
    prompt = [("$ ", "prompt"), ("", "cursor")]

    def emit(seconds):
        frames.append(([list(l) for l in lines], seconds))

    lines.append(list(prompt))
    emit(FIRST_DT)
    for b in beats:
        lines[-1] = [(b["caption"], "caption")]           # the comment takes the waiting prompt's line
        lines.append(list(prompt))
        emit(CAPTION_DT)
        cmd = b["command"]
        for n in range(TYPE_CHARS, len(cmd) + TYPE_CHARS, TYPE_CHARS):
            n = min(n, len(cmd))
            lines[-1] = [("$ ", "prompt"), (cmd[:n], "command"), ("", "cursor")]
            emit(TYPE_DT)
            if n == len(cmd):
                break
        lines[-1] = [("$ ", "prompt"), (cmd, "command")]
        emit(ENTER_DT)
        # a new accent block retires the previous one, so each view has one thing to look at
        for line in lines:
            for i, (text, role) in enumerate(line):
                if role == "accent":
                    line[i] = (text, "output")
        out_lines = b["output"].rstrip("\n").split("\n") if b["output"].strip() else []
        for i, text in enumerate(out_lines):
            lines.append([(text, "accent" if i in b["accent_rows"] else "output")])
            if b.get("stream") and i < len(out_lines) - 1:
                emit(STREAM_DT)
        lines.append(list(prompt))
        emit(b["hold"])
        keyframes.append(len(frames) - 1)
    return frames, keyframes


# ---- drawing ----------------------------------------------------------------------------------------------
class Mono:
    """Commit Mono glyphs as <defs> paths in font units, placed with <use>; one definition per glyph."""

    def __init__(self, face):
        self.face = face
        self.s = FONT / face.upm
        self.adv = face.hmtx[face.cmap[ord("x")]][0] * self.s
        self.cache = {}

    def d(self, ch):
        if ch not in self.cache:
            from fontTools.pens.svgPathPen import SVGPathPen
            g = self.face.cmap[ord(ch)]                    # KeyError = a character the font lacks: stop
            pen = SVGPathPen(self.face.gs)
            self.face.gs[g].draw(pen)
            self.cache[ch] = pen.getCommands()
        return self.cache[ch]

    def defs(self, chars):
        return "".join('<path id="c%d" transform="scale(%.5f %.5f)" d="%s"/>' % (ord(ch), self.s, -self.s, self.d(ch))
                       for ch in sorted(chars) if self.d(ch))


def chrome(logo, disp, small):
    """Everything that does not change between frames: the terminal, its title bar, the mark, the name, the
    tagline and the credit."""
    panel = '<rect x="%d" y="%d" width="%d" height="%d" fill="%s"/>' % (PX, PY, PW, PH, C["Spool"])
    rule = '<rect x="%d" y="%d" width="%d" height="1" fill="%s"/>' % (PX, PY + TITLE_H - 1, PW, C["Rule"])
    k = 2.2                                                  # the mark: 9 grid rows tall = 19.8 px
    mark = logo.place(logo.mark_shapes(logo.THEMES["dark"], mono=C["Leader"]), PX + 24, PY + 12, k)
    nsize = 19.0
    asc = disp.bounds("d", nsize)[3]
    base = PY + (TITLE_H + asc) / 2
    name, _ = disp.outline(NAME, nsize, PX + 24 + 16 * k + 12, base, tracking=-0.02)
    tw = small.outline(TAGLINE, 14, 0, 0)[1]
    tag, _ = small.outline(TAGLINE, 14, PX + PW - 24 - tw, PY + (TITLE_H + small.x_height(14)) / 2)
    credit, _ = small.outline(CREDIT, 14, PX, H - 20)
    return (panel + rule + mark + '<g fill="%s">%s</g>' % (C["Leader"], name)
            + '<g fill="%s">%s</g>' % (C["Playhead"], tag) + '<g fill="%s">%s</g>' % (C["Tape"], credit))


def frame_svg(logo, mono, static, lines):
    return logo.svg(W, H, frame_body(mono, static, lines), bg=C["Leader"], title="rewindagent demo")


def frame_body(mono, static, lines):
    """One frame's drawing without the <svg> wrapper (brand/demo/launch_mp4.py places it inside a larger frame)."""
    body, chars = [], set()
    for row, segs in enumerate(lines[-ROWS:]):
        x, base = TX, BASE0 + row * LH
        for text, role in segs:
            if role == "cursor":
                body.append('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" fill="%s"/>'
                            % (x, base - FONT * 0.78, mono.adv, FONT * 0.98, C[COLOURS["cursor"]]))
                continue
            uses = []
            for ch in text:
                chars.add(ch)
                if mono.d(ch):
                    uses.append('<use href="#c%d" x="%.2f" y="%.2f"/>' % (ord(ch), x, base))
                x += mono.adv
            if uses:
                body.append('<g fill="%s">%s</g>' % (C[COLOURS[role]], "".join(uses)))
    return "<defs>%s</defs>" % mono.defs(chars) + static + "".join(body)


def merge(frames):
    """Consecutive identical frames become one longer frame (fewer GIF frames, same play time)."""
    out = []
    for lines, sec in frames:
        if out and out[-1][0] == lines:
            out[-1] = (lines, round(out[-1][1] + sec, 2))
        else:
            out.append((lines, sec))
    return out


def check(beats, frames, cols, root):
    """Refuse to draw anything the brand or the product would not stand behind."""
    for b in beats:
        if b["exit"] != 0:
            raise SystemExit("%r exited %d:\n%s" % (b["command"], b["exit"], b["output"]))
        if b["command"].startswith("rewindagent") and "rewindagent:" in b["output"]:
            raise SystemExit("%r printed an error: %s" % (b["command"], b["output"]))
    texts = {t for lines, _ in frames for line in lines for t, _ in line}
    for t in texts:
        if len(t) > cols:
            raise SystemExit("line of %d characters does not fit %d columns: %r" % (len(t), cols, t))
        if any(bad in t for bad in FORBIDDEN_TEXT) or root in t:
            raise SystemExit("a frame shows a path from this machine: %r" % t)
    total = round(sum(sec for _, sec in frames), 2)
    if total > MAX_SECONDS:
        raise SystemExit("storyboard is %.2f s, over the %.0f s limit" % (total, MAX_SECONDS))
    for _, sec in frames:
        if abs(round(sec / GRID) * GRID - sec) > 1e-6:
            raise SystemExit("duration %.3f is not on the %.0f ms grid" % (sec, GRID * 1000))
    return total


def build(cache):
    if cli.invocation() != "rewindagent":
        raise SystemExit("run build.py with the Python that has rewindagent installed (the clip types "
                         "`rewindagent ...`, so the undo hint it shows must say the same)")
    logo = load_logo_build()
    fs = os.path.join(cache, "node_modules", "@fontsource")
    mono = Mono(logo.Face(os.path.join(fs, "commit-mono", "files", "commit-mono-latin-400-normal.woff")))
    disp = logo.Face(os.path.join(fs, "bricolage-grotesque", "files", "bricolage-grotesque-latin-800-normal.woff"))
    small = logo.Face(os.path.join(fs, "hanken-grotesk", "files", "hanken-grotesk-latin-400-normal.woff"))
    static = chrome(logo, disp, small)
    cols = int((PW - 2 * (TX - PX)) // mono.adv)

    with tempfile.TemporaryDirectory() as d:
        beats = scenario.play(d)
        root = os.path.realpath(d)
    frames, keyframes = storyboard(beats)
    key_lines = [frames[k][0] for k in keyframes]
    frames = merge(frames)
    total = check(beats, frames, cols, root)
    keyframes = [0] + [next(i for i, (lines, _) in enumerate(frames) if lines == kl) for kl in key_lines]

    fdir = os.path.join(HERE, "frames")
    shutil.rmtree(fdir, ignore_errors=True)
    os.makedirs(fdir)
    palette = {v.upper() for v in C.values()}
    table = []
    for i, (lines, sec) in enumerate(frames):
        name = "%04d" % i
        svg = frame_svg(logo, mono, static, lines)
        off = {f.upper() for f in re.findall(r'fill="(#[0-9A-Fa-f]{6})"', svg)} - palette
        if off:
            raise SystemExit("frame %s uses colours outside the palette: %s" % (name, sorted(off)))
        with open(os.path.join(fdir, name + ".svg"), "w", encoding="utf-8") as f:
            f.write(svg)
        table.append({"svg": name + ".svg", "png": name + ".png", "duration": sec})
    with open(os.path.join(fdir, "frames.json"), "w", encoding="utf-8") as f:
        json.dump({"width": W, "height": H, "frames": table, "keyframes": keyframes}, f)
    subprocess.run(["node", os.path.join(HERE, "render.mjs"), os.path.join(cache, "node_modules")], check=True)

    # ffmpeg: concat demuxer with one duration per frame, one palette for the whole clip, no dither
    # (flat colours and crisp text), variable frame rate so holds are single frames with a long delay
    lst = os.path.join(fdir, "list.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for row in table:
            f.write("file '%s'\nduration %.2f\n" % (row["png"], row["duration"]))
        f.write("file '%s'\n" % table[-1]["png"])
    gif = os.path.join(BRAND, "demo.gif")
    vf = "split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=none:diff_mode=rectangle"
    base = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst]
    for vfr in (["-fps_mode", "vfr"], ["-vsync", "vfr"]):
        p = subprocess.run(base + vfr + ["-vf", vf, "-loop", "0", gif], capture_output=True, text=True)
        if p.returncode == 0:
            break
    else:
        raise SystemExit("ffmpeg failed:\n" + p.stderr)

    facts = gif_info(gif)
    colors = set(facts.pop("colors"))
    missing = [n for n in ("Leader", "Spool", "Playhead", "Rewind") if C[n].upper() not in colors]
    if missing:
        raise SystemExit("the GIF's colour table lost these brand colours: %s" % missing)
    facts["bytes"] = os.path.getsize(gif)
    manifest = {
        "gif": "demo.gif", "version": rewindagent.__version__, "invocation": cli.invocation(),
        "session": scenario.SESSION, "steps": len(scenario.STEPS), "good_step": scenario.GOOD_STEP,
        "limit_seconds": MAX_SECONDS, "storyboard_seconds": total, "grid_seconds": GRID,
        "beats": [{k: b[k] for k in ("caption", "command", "output", "exit", "hold", "accent_rows")} for b in beats],
        "title_right": TAGLINE, "credit": CREDIT, "rows": ROWS, "cols": cols,
        "colours": COLOURS,
        "fonts": ["Commit Mono 400 (terminal)", "Bricolage Grotesque 800 (name)", "Hanken Grotesk 400 (small print)"],
        "gif_facts": facts,
    }
    with open(os.path.join(HERE, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
        f.write("\n")
    print("storyboard %.2f s in %d frames; gif %dx%d, %d frames, %.2f s, %d KB, loops=%s, delays(cs)=%s"
          % (total, len(frames), facts["width"], facts["height"], facts["frames"], facts["seconds"],
             facts["bytes"] // 1024, facts["loops"], facts["delays_cs"]))


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, ".brandcache"))
