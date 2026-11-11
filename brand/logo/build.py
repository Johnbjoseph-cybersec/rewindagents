"""Build the rewindagent logo set as SVG (task RB2). render.mjs turns the SVGs into PNGs.

The mark is drawn on a 16-unit grid so it stays sharp at 16 px: a step ruler (baseline + ticks) with a
red playhead standing on the third of four ticks, one behind the last. The tick after the playhead is drawn
in Rule grey: the step that was rewound. (The brief's left-pointing flag was dropped: bar + flag read as "1".)

Text is outlined from the OFL font files, so every SVG renders the same with no fonts installed.
Usage: .venv/bin/python brand/logo/build.py <fonts-dir>
<fonts-dir> holds the @fontsource packages (npm install --prefix .brandcache @fontsource/bricolage-grotesque
@fontsource/hanken-grotesk @fontsource/commit-mono).
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

THEMES = {
    "light": {"ground": C["Leader"], "ink": C["Reel"], "undone": C["Rule"], "head": C["Record"], "sub": C["Tape"]},
    "dark": {"ground": C["Reel"], "ink": C["Leader"], "undone": C["Rule"], "head": C["Rewind"], "sub": C["Playhead"]},
}

TAGLINE = "Ctrl+Z for AI coding agents: record, replay, rewind."
COMMAND = "python3 -m rewindagent rewind 12"
CREDIT = "made by John B Joseph"


def mark_shapes(t, mono=None):
    """The mark on its 16x16 grid, for 32 px and up. Ruler (ticks + 2-unit rule) spans y 6..14; the
    rewound tick is solid Rule grey. Returns SVG elements (no wrapper)."""
    ink = mono or t["ink"]
    undone = mono or t["undone"]
    head = mono or t["head"]
    return "".join([
        '<rect x="0" y="12" width="16" height="2" fill="%s"/>' % ink,           # rule
        '<rect x="1" y="6" width="2" height="6" fill="%s"/>' % ink,             # step 1
        '<rect x="5" y="6" width="2" height="6" fill="%s"/>' % ink,             # step 2
        '<rect x="13" y="6" width="2" height="6" fill="%s"/>' % undone,         # step 4, rewound
        '<path d="%s" fill="%s"/>' % (playhead(9, 1, 15, 1), head),             # playhead on step 3
    ])


def favicon_shapes(t):
    """A separate drawing for 16 px: one tick, the playhead, the rewound tick in Tape (holds 5.9:1)."""
    return "".join([
        '<rect x="0" y="12" width="16" height="2" fill="%s"/>' % t["ink"],
        '<rect x="2" y="6" width="2" height="6" fill="%s"/>' % t["ink"],
        '<rect x="12" y="6" width="2" height="6" fill="%s"/>' % t["sub"],
        '<path d="%s" fill="%s"/>' % (playhead(7, 1, 15, 1), t["head"]),
    ])


def playhead(bx, top, bottom, u):
    """Timeline marker: a pointer (6u wide, 3u tall, pointing down) detached by 1u above a 2u bar whose left
    edge is bx. Kept apart on purpose: joined to the bar, every cap tried read as a letter (1, T) or a pin."""
    return ("M%g %gH%gL%g %gZM%g %gH%gV%gH%gZ"
            % (bx - 2 * u, top, bx + 4 * u, bx + u, top + 3 * u,
               bx, top + 4 * u, bx + 2 * u, bottom, bx))


def svg(w, h, body, bg=None, title="rewindagent"):
    ground = '<rect width="%g" height="%g" fill="%s"/>' % (w, h, bg) if bg else ""
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %g %g" width="%g" height="%g" role="img">'
            '<title>%s</title>%s%s</svg>\n' % (w, h, w, h, title, ground, body))


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
            g = self.cmap[ord(ch)]
            pen = SVGPathPen(self.gs)
            self.gs[g].draw(pen)
            d = pen.getCommands()
            if d:
                parts.append('<path transform="translate(%.3f %.3f) scale(%.5f %.5f)" d="%s"/>'
                             % (x0 + x * s, baseline, s, -s, d))
            x += self.hmtx[g][0] + tracking * self.upm
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
    """Mark + 'rewindagent'. The ruler (grid y 6..14) is 1.25 x-heights tall, so the mark's strokes carry
    the weight of the 800 letter stems; the text baseline is the bottom of the rule."""
    size = 100.0
    xh = face.x_height(size)
    k = xh * 1.25 / 8.0
    pad = 8.0
    mark_w = 16 * k
    base_y = pad + 14 * k
    glyphs, adv = face.outline("rewindagent", size, pad + mark_w + 0.42 * size, base_y, tracking=-0.02)
    w = pad + mark_w + 0.42 * size + adv + pad
    h = base_y + max(1 * k, face.descent("g", size)) + pad
    body = ('<g transform="translate(%.3f %.3f) scale(%.4f)">%s</g>' % (pad, pad, k, mark_shapes(t, mono))
            + '<g fill="%s">%s</g>' % (mono or t["ink"], glyphs))
    return w, h, body


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
    # square logos: stacked lockup (mark over the name), so the square is filled, not a strip in the middle
    _, adv100 = disp.outline("rewindagent", 100, 0, 0, tracking=-0.02)
    size = 100 * 760 / adv100
    asc, desc = disp.bounds("d", size)[3], disp.descent("g", size)
    mark_px, gap = 384, 72
    top = (1024 - (mark_px + gap + asc + desc)) / 2
    for theme, t in (("light", L), ("dark", D)):
        name, _ = disp.outline("rewindagent", size, (1024 - 760) / 2, top + mark_px + gap + asc, tracking=-0.02)
        g = ('<g transform="translate(%.2f %.2f) scale(%.4f)">%s</g>' % ((1024 - mark_px) / 2, top, mark_px / 16,
                                                                         mark_shapes(t))
             + '<g fill="%s">%s</g>' % (t["ink"], name))
        src["logo-%s.png" % theme] = (svg(1024, 1024, g, bg=t["ground"]), 1024)
    src["avatar-512.png"] = (svg(512, 512, '<g transform="translate(72 72) scale(23)">%s</g>' % mark_shapes(L),
                                 bg=C["Leader"]), 512)
    src["favicon-32.png"] = (svg(16, 16, favicon_shapes(L), bg=C["Leader"]), 32)

    # social preview 1280x640: name, tagline on two lines, one real command and the credit on the left;
    # the mark, large, on the right. Everything inside a 96 px margin (GitHub crops the edges on some cards).
    nsize = 100 * 600 / adv100
    name, _ = disp.outline("rewindagent", nsize, 96, 176, tracking=-0.02)
    head, tail = TAGLINE.split(": ")
    tag1, _ = body.outline(head + ":", 46, 96, 268)
    tag2, _ = body.outline(tail, 46, 96, 326)
    cmd, cw = mono.outline("$ " + COMMAND, 30, 122, 420)
    cred, _ = body.outline(CREDIT, 22, 96, 560)
    mpx = 304
    social = ('<g fill="%s">%s</g>' % (L["ink"], name)
              + '<g fill="%s">%s%s</g>' % (L["ink"], tag1, tag2)
              + '<rect x="96" y="374" width="%.1f" height="70" fill="%s"/>' % (cw + 52, C["Spool"])
              + '<g fill="%s">%s</g>' % (C["Leader"], cmd)
              + '<g fill="%s">%s</g>' % (L["sub"], cred)
              + '<g transform="translate(%d %d) scale(%g)">%s</g>' % (1184 - mpx, (640 - mpx) / 2, mpx / 16,
                                                                     mark_shapes(L)))
    src["social-preview-1280x640.png"] = (svg(1280, 640, social, bg=C["Leader"]), 1280)

    for name, text in out.items():
        with open(os.path.join(BRAND, name), "w", encoding="utf-8") as f:
            f.write(text)
    srcdir = os.path.join(HERE, "src")
    os.makedirs(srcdir, exist_ok=True)
    manifest = {}
    for name, (text, width) in src.items():
        sname = name[:-4] + ".svg"
        with open(os.path.join(srcdir, sname), "w", encoding="utf-8") as f:
            f.write(text)
        manifest[name] = {"src": "logo/src/" + sname, "width": width}
    with open(os.path.join(HERE, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
        f.write("\n")
    print("wrote %d SVGs in brand/, %d PNG sources in brand/logo/src/" % (len(out), len(src)))


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(BRAND), ".brandcache"))
