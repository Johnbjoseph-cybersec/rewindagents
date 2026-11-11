"""Build the rewindagent logo set as SVG (task RB2; round 4 is RB2c). render.mjs turns the SVGs into PNGs.

The mark is a timeline playhead on a step ruler, scrubbed back, drawn on a 16-unit grid: seven short, equal
ticks at an even pitch on a hairline rule, and a red playhead (a triangle head joined to a thin line, as audio
and video editors draw it) standing on the ruler as its only tall element. Everything after the playhead is the
rewound part: the rule and the ticks turn grey, like the unplayed part of a scrubber. The mark uses half units
(sharp from 32 px up); favicon_shapes is a separate drawing on whole units for 16 px.

Text is outlined from the OFL font files, so every SVG renders the same with no fonts installed.
Usage: .venv/bin/python brand/logo/build.py <fonts-dir>
<fonts-dir> holds the @fontsource packages (npm install --prefix .brandcache @fontsource/bricolage-grotesque
@fontsource/hanken-grotesk @fontsource/commit-mono).

Every PNG source also gets a list of sample points (pixel, expected palette name) in manifest.json;
pngsample.py reads the rendered PNGs and compares, and tests/test_logo.py runs the same comparison.
"""
import json
import os
import sys

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont

HERE = os.path.dirname(os.path.abspath(__file__))
BRAND = os.path.dirname(HERE)

C = {"Leader": "#F2F4F1", "Reel": "#121412", "Spool": "#1C201D", "Tape": "#55605A",
     "Record": "#B82A16", "Rewind": "#FF7A59", "Playhead": "#B9C2BB", "Rule": "#838C86"}
NAME = {v: k for k, v in C.items()}

THEMES = {
    "light": {"ground": C["Leader"], "ink": C["Reel"], "undone": C["Rule"], "head": C["Record"], "sub": C["Tape"]},
    "dark": {"ground": C["Reel"], "ink": C["Leader"], "undone": C["Rule"], "head": C["Rewind"], "sub": C["Playhead"]},
}

TAGLINE = "Ctrl+Z for AI coding agents: record, replay, rewind."
COMMAND = "rewindagent rewind 12"
CREDIT = "made by John B Joseph"
INSTALL = "pipx install git+https://github.com/Johnbjoseph-cybersec/rewindagent"

# Visible rows of the mark on the 16 grid (the playhead's head top and its line bottom); x spans 0..16.
MARK_TOP, MARK_BOTTOM = 3.5, 12.5
MARK_H = MARK_BOTTOM - MARK_TOP


def g(v):
    return "%g" % v


def rect(x, y, w, h, fill):
    return '<rect x="%s" y="%s" width="%s" height="%s" fill="%s"/>' % (g(x), g(y), g(w), g(h), fill)


# The playhead: an editor-style handle (flat-topped pentagon, 4 wide, 2 flat + 1.5 taper) on a 1-wide line,
# centre x 9, ending flush with the rule bottom. No neck between head and line.
PLAYHEAD = "M7 3.5H11V5.5L9.5 7V12.5H8.5V7L7 5.5Z"
TICK_H = 3.0            # short ticks from y 9.5, overlapping the half-unit rule (no seams)


def mark_shapes(t, mono=None):
    """The mark on its 16x16 grid, for 32 px and up: a timeline playhead (an editor's handle on a thin line)
    standing on a step ruler of seven short, equal ticks at a 2-unit pitch (x 1, 3, 5, 7 recorded; 11, 13, 15
    rewound) on a half-unit rule. The playhead is the only tall element. Returns SVG elements (no wrapper)."""
    ink = mono or t["ink"]
    undone = mono or t["undone"]
    head = mono or t["head"]
    parts = [rect(0, 12, 9, 0.5, ink), rect(9, 12, 7, 0.5, undone)]      # rule: recorded, then rewound
    parts += [rect(x - 0.5, 9.5, 1, TICK_H, ink) for x in (1, 3, 5, 7)]
    parts += [rect(x - 0.5, 9.5, 1, TICK_H, undone) for x in (11, 13, 15)]
    parts.append('<path d="%s" fill="%s"/>' % (PLAYHEAD, head))
    return "".join(parts)


MARK_SAMPLES = [  # (grid x, grid y, theme key) of solid areas, for pixel sampling
    (9, 9, "head"), (1, 11, "ink"), (15, 11, "undone"), (4, 12.25, "ink"), (12, 12.25, "undone")]


def favicon_shapes(t):
    """A separate drawing for 16 px, whole units only so nothing is anti-aliased: the same ruler with 1 px
    ticks at a 2 px pitch (three each side) on a 1 px rule, a 2 px playhead line with a flat-topped stepped
    head (two rows of 6 px, one of 4 px), and the rewound rule and ticks in the secondary text colour (Tape
    on Leader holds 5.9:1 at 1 px). Also used, scaled by whole pixels, at 64 px and in the 20 px avatar crop."""
    head = "M5 3H11V5H10V6H9V13H7V6H6V5H5Z"
    parts = [rect(0, 12, 8, 1, t["ink"]), rect(8, 12, 8, 1, t["sub"])]
    parts += [rect(x, 9, 1, 4, t["ink"]) for x in (1, 3, 5)]
    parts += [rect(x, 9, 1, 4, t["sub"]) for x in (11, 13, 15)]
    parts.append('<path d="%s" fill="%s"/>' % (head, t["head"]))
    return "".join(parts)


FAVICON_SAMPLES = [(8, 9, "head"), (1.5, 10.5, "ink"), (15.5, 10.5, "sub"), (6, 12.5, "ink"), (12, 12.5, "sub")]


def svg(w, h, body, bg=None, title="rewindagent"):
    ground = '<rect width="%s" height="%s" fill="%s"/>' % (g(w), g(h), bg) if bg else ""
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %s %s" width="%s" height="%s" role="img">'
            '<title>%s</title>%s%s</svg>\n' % (g(w), g(h), g(w), g(h), title, ground, body))


def place(shapes, x, top, k):
    """Scale the 16-grid mark by k and put its visible top-left corner at (x, top)."""
    return '<g transform="translate(%.3f %.3f) scale(%.4f)">%s</g>' % (x, top - MARK_TOP * k, k, shapes)


def samples(points, t, x, top, k, scale=1.0):
    """Pixel sample points for a placed mark: [[px, py, palette name], ...]."""
    out = []
    for gx, gy, key in points:
        px = (x + gx * k) * scale
        py = (top + (gy - MARK_TOP) * k) * scale
        out.append([int(px), int(py), NAME[t[key]]])
    return out


class Face:
    """One font file: outline a string as a single SVG path, in font units, baseline at y=0."""

    def __init__(self, path):
        self.font = TTFont(path)
        self.gs = self.font.getGlyphSet()
        self.cmap = self.font.getBestCmap()
        self.upm = self.font["head"].unitsPerEm
        self.hmtx = self.font["hmtx"]

    def outline(self, text, size, x0, baseline, tracking=0.0):
        """Path data for text at `size` px, starting at x0 on `baseline`. Returns (d, advance_px)."""
        s = size / self.upm
        x = 0.0
        parts = []
        for ch in text:
            gl = self.cmap[ord(ch)]
            pen = SVGPathPen(self.gs)
            self.gs[gl].draw(pen)
            d = pen.getCommands()
            if d:
                parts.append('<path transform="translate(%.3f %.3f) scale(%.5f %.5f)" d="%s"/>'
                             % (x0 + x * s, baseline, s, -s, d))
            x += self.hmtx[gl][0] + tracking * self.upm
        return "".join(parts), x * s

    def bounds(self, ch, size):
        bp = BoundsPen(self.gs)
        self.gs[self.cmap[ord(ch)]].draw(bp)
        return [v * size / self.upm for v in bp.bounds]

    def x_height(self, size):
        return self.bounds("x", size)[3]

    def descent(self, ch, size):
        return -self.bounds(ch, size)[1]


def wordmark(face, t, mono=None):
    """Mark + 'rewindagent'. One grid unit is the 'd' ascender height over 8.5, so the playhead (9 units tall)
    rises a little above the ascenders; the text baseline is the bottom of the rule and of the playhead."""
    size = 100.0
    k = face.bounds("d", size)[3] / 8.5
    pad = 8.0
    mark_w = 16 * k
    base_y = pad + (MARK_BOTTOM - MARK_TOP) * k
    glyphs, adv = face.outline("rewindagent", size, pad + mark_w + 0.36 * size, base_y, tracking=-0.02)
    w = pad + mark_w + 0.36 * size + adv + pad
    h = base_y + face.descent("g", size) + pad
    body = (place(mark_shapes(t, mono), pad, pad, k)
            + '<g fill="%s">%s</g>' % (mono or t["ink"], glyphs))
    return w, h, body


def circle_mark(shapes, cx, cy, r, uid, bg):
    """The mark inside a circular crop of radius r (how GitHub shows an avatar)."""
    k = 2 * r * 0.72 / 16
    x, top = cx - 8 * k, cy - MARK_H * k / 2
    return ('<clipPath id="%s"><circle cx="%s" cy="%s" r="%s"/></clipPath>'
            '<g clip-path="url(#%s)"><circle cx="%s" cy="%s" r="%s" fill="%s"/>%s</g>'
            % (uid, g(cx), g(cy), g(r), uid, g(cx), g(cy), g(r), bg, place(shapes, x, top, k)))


def in_use(disp, body, mono):
    """A sheet of the identity in the places it will actually be seen: a browser tab (favicon at true 16 px),
    a README header on a light and a dark page, and the avatar at GitHub's circle sizes. Review material
    only (brand/logo/in-use.png). Palette colours only, so the two dark grounds agree."""
    L, D = THEMES["light"], THEMES["dark"]
    parts = []
    # row A: browser tab strips, light and dark, favicon at 1:1
    for i, (t, strip, tab, fav) in enumerate(((L, C["Playhead"], C["Leader"], favicon_shapes(L)),
                                             (D, C["Spool"], C["Reel"], favicon_shapes(D)))):
        x0 = 680 * i
        title, _ = body.outline("rewindagent", 13, x0 + 54, 39)
        parts.append(rect(x0, 0, 640, 56, strip)
                     + '<rect x="%d" y="10" width="270" height="46" rx="8" fill="%s"/>' % (x0 + 12, tab)
                     + '<g transform="translate(%d 25)">%s</g>' % (x0 + 30, fav)
                     + '<g fill="%s">%s</g>' % (t["ink"], title))
    # row B: README header on a light page and on a dark page
    for i, (t, page, m) in enumerate(((L, C["Leader"], None), (D, C["Reel"], None))):
        x0 = 680 * i
        w, h, wm = wordmark(disp, t, m)
        s = 300.0 / w
        line1, _ = body.outline(TAGLINE, 16, x0 + 40, 90 + h * s + 32)
        line2, _ = mono.outline("$ " + INSTALL, 14, x0 + 40, 90 + h * s + 64)
        parts.append(rect(x0, 80, 640, 200, page)
                     + '<g transform="translate(%d 90) scale(%.4f)">%s</g>' % (x0 + 40, s, wm)
                     + '<g fill="%s">%s</g><g fill="%s">%s</g>' % (t["ink"], line1, t["sub"], line2))
    # row C: avatar in GitHub's circle crops (org header 96 px, list 48 px, comment 20 px) on a light page
    parts.append(rect(0, 300, 1320, 160, C["Leader"]))
    for j, (r, cx) in enumerate(((48, 88), (24, 400))):
        parts.append(circle_mark(mark_shapes(L), cx, 380, r, "c%d" % j, C["Leader"]))
    # the 20 px comment avatar uses the 16 px drawing, scaled 1.25
    parts.append('<clipPath id="c2"><circle cx="600" cy="380" r="10"/></clipPath>'
                 '<g clip-path="url(#c2)"><circle cx="600" cy="380" r="10" fill="%s"/>'
                 '<g transform="translate(590 370) scale(1.25)">%s</g></g>' % (C["Leader"], favicon_shapes(L)))
    org, _ = disp.outline("rewindagent", 26, 156, 372)
    sub, _ = body.outline("Ctrl+Z for AI coding agents", 15, 156, 398)
    parts.append('<g fill="%s">%s</g><g fill="%s">%s</g>' % (L["ink"], org, L["sub"], sub))
    cm, _ = body.outline("rewindagent", 15, 436, 385)
    parts.append('<g fill="%s">%s</g>' % (L["ink"], cm))
    cm2, _ = body.outline("rewindagent", 13, 618, 384)
    parts.append('<g fill="%s">%s</g>' % (L["ink"], cm2))
    return svg(1320, 460, "".join(parts), bg="#9AA39C", title="rewindagent, in use")


def build(fonts):
    fs = os.path.join(fonts, "node_modules", "@fontsource")
    disp = Face(os.path.join(fs, "bricolage-grotesque", "files", "bricolage-grotesque-latin-800-normal.woff"))
    body = Face(os.path.join(fs, "hanken-grotesk", "files", "hanken-grotesk-latin-600-normal.woff"))
    mono = Face(os.path.join(fs, "commit-mono", "files", "commit-mono-latin-400-normal.woff"))
    out = {}
    L, D = THEMES["light"], THEMES["dark"]

    # 1. marks: transparent, theme colours; mono uses currentColor so it takes the page's text colour
    out["logo-mark.svg"] = svg(16, 16, mark_shapes(L))
    out["logo-mark-reverse.svg"] = svg(16, 16, mark_shapes(D))
    out["logo-mark-mono.svg"] = svg(16, 16, mark_shapes(L, mono="currentColor"))
    out["favicon.svg"] = svg(16, 16, favicon_shapes(L), bg=C["Leader"])

    # 2. wordmarks
    for name, t, m in (("logo-wordmark.svg", L, None), ("logo-wordmark-reverse.svg", D, None),
                       ("logo-wordmark-mono.svg", L, "currentColor")):
        w, h, b = wordmark(disp, t, m)
        out[name] = svg(round(w, 2), round(h, 2), b)

    # 3. PNG sources (rendered by render.mjs into brand/)
    src = {}
    # square logos: stacked lockup, the mark 72 percent of the name's width so the two read as one unit
    _, adv100 = disp.outline("rewindagent", 100, 0, 0, tracking=-0.02)
    name_w, mark_w, gap = 760.0, 544.0, 64.0
    size = 100 * name_w / adv100
    asc, desc = disp.bounds("d", size)[3], disp.descent("g", size)
    k = mark_w / 16
    top = (1024 - (MARK_H * k + gap + asc + desc)) / 2
    for theme, t in (("light", L), ("dark", D)):
        name, _ = disp.outline("rewindagent", size, (1024 - name_w) / 2, top + MARK_H * k + gap + asc,
                               tracking=-0.02)
        x = (1024 - mark_w) / 2
        body_svg = place(mark_shapes(t), x, top, k) + '<g fill="%s">%s</g>' % (t["ink"], name)
        src["logo-%s.png" % theme] = (svg(1024, 1024, body_svg, bg=t["ground"]), 1024,
                                      [[24, 24, NAME[t["ground"]]]] + samples(MARK_SAMPLES, t, x, top, k))
    # avatar: the visible mark centred in the 512 square (so also in the circular crop), 72 percent wide
    k = 23.0
    x, top = (512 - 16 * k) / 2, (512 - MARK_H * k) / 2
    assert ((x - 256) ** 2 + (top + 12 * k - 256) ** 2) ** 0.5 < 256, "rule corner outside the circle crop"
    src["avatar-512.png"] = (svg(512, 512, place(mark_shapes(L), x, top, k), bg=C["Leader"]), 512,
                             [[10, 10, "Leader"]] + samples(MARK_SAMPLES, L, x, top, k))
    src["favicon-32.png"] = (svg(16, 16, favicon_shapes(L), bg=C["Leader"]), 32,
                             [[1, 1, "Leader"]] + samples(FAVICON_SAMPLES, L, 0, MARK_TOP, 1, scale=2))

    # social preview 1280x640: name, tagline on two lines, one real command in an outlined block and the
    # credit on the left; the mark, large, on the right. Everything inside a 96 px margin (GitHub crops the
    # edges on some cards).
    nsize = 100 * 600 / adv100
    name, _ = disp.outline("rewindagent", nsize, 96, 176, tracking=-0.02)
    head, tail = TAGLINE.split(": ")
    tag1, _ = body.outline(head + ":", 46, 96, 268)
    tag2, _ = body.outline(tail, 46, 96, 326)
    cmd, cw = mono.outline("$ " + COMMAND, 30, 122, 420)
    cred, _ = body.outline(CREDIT, 24, 96, 560)
    k = 448 / 16
    name_top = 176 - disp.bounds("d", nsize)[3]
    x, top = 1184 - 448, (name_top + 443) / 2 - MARK_H * k / 2   # centred on the headline-to-command block
    social = ('<g fill="%s">%s</g>' % (L["ink"], name)
              + '<g fill="%s">%s%s</g>' % (L["ink"], tag1, tag2)
              + '<rect x="97.5" y="375.5" width="%.1f" height="67" fill="none" stroke="%s" stroke-width="3"/>'
              % (cw + 49, C["Tape"])
              + '<g fill="%s">%s</g>' % (L["ink"], cmd)
              + '<g fill="%s">%s</g>' % (L["ink"], cred)
              + place(mark_shapes(L), x, top, k))
    src["social-preview-1280x640.png"] = (svg(1280, 640, social, bg=C["Leader"]), 1280,
                                          [[40, 40, "Leader"]] + samples(MARK_SAMPLES, L, x, top, k))

    for name, text in out.items():
        with open(os.path.join(BRAND, name), "w", encoding="utf-8") as f:
            f.write(text)
    srcdir = os.path.join(HERE, "src")
    os.makedirs(srcdir, exist_ok=True)
    manifest = {}
    for name, (text, width, pts) in src.items():
        sname = name[:-4] + ".svg"
        with open(os.path.join(srcdir, sname), "w", encoding="utf-8") as f:
            f.write(text)
        manifest[name] = {"src": "logo/src/" + sname, "width": width, "samples": pts}
    with open(os.path.join(HERE, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
        f.write("\n")
    with open(os.path.join(HERE, "in-use.svg"), "w", encoding="utf-8") as f:
        f.write(in_use(disp, body, mono))
    print("wrote %d SVGs in brand/, %d PNG sources in brand/logo/src/, brand/logo/in-use.svg"
          % (len(out), len(src)))


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(BRAND), ".brandcache"))
