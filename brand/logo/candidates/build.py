"""Three candidate marks for the logo concept pick (task RB2d), drawn from the round-6 fix list in brand/review.json.

Six polish rounds on one shape went 7.71 -> 8.50 and the fixes started to flip, so this is a concept pick, not
another polish: each candidate is a different answer to "a playhead on a step ruler, scrubbed back".
  A: a short, wide flat-topped head tapering straight into a hairline (no neck), on the rule
  B: no head at all, a heavy playhead bar crossing a thin ruler
  C: the head as a filled square sitting on the rule (a slider thumb), a hairline rising from it
All three share the ruler the review asked for: thin ticks, wider gaps, a taller major tick every fourth step,
recorded (ink) left of the playhead and rewound (grey) right of it.

Each candidate is shown IN USE through brand/logo/build.py's own in_use() sheet (browser tab at true 16 px,
README header light and dark, avatar circles 96/48/20), so the comparison is the places the mark will be seen.
Review material only: nothing here is shipped. Usage:
  .venv/bin/python brand/logo/candidates/build.py [<fonts-dir>]   then   node brand/logo/candidates/render.mjs
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import build as B  # noqa: E402  (brand/logo/build.py)

rect = B.rect


def ruler(t, mono, rule_y, rule_h, tick_w, minor, major, left, right, split, majors=(0, 4)):
    """Rule split at the playhead (ink before, grey after) and ticks whose bottoms sit on the rule top.
    left/right are tick x positions; `majors` are indexes over left+right that get the taller tick."""
    ink, undone = mono or t["ink"], mono or t["undone"]
    lo, hi = split
    parts = [rect(0, rule_y, lo, rule_h, ink), rect(hi, rule_y, 16 - hi, rule_h, undone)]
    for i, x in enumerate(list(left) + list(right)):
        h = major if i in majors else minor
        parts.append(rect(x, rule_y - h, tick_w, h, ink if x < lo else undone))
    return parts


def fav_ruler(t, rule_y, left, right, split, majors=(0, 4)):
    """The 16 px version: whole pixels, rewound part in the secondary text colour (as build.favicon_shapes)."""
    lo, hi = split
    parts = [rect(0, rule_y, lo, 1, t["ink"]), rect(hi, rule_y, 16 - hi, 1, t["sub"])]
    for i, x in enumerate(list(left) + list(right)):
        h = 4 if i in majors else 2
        parts.append(rect(x, rule_y - h, 1, h, t["ink"] if x < lo else t["sub"]))
    return parts


def head(d, t, mono=None):
    return '<path d="%s" fill="%s"/>' % (d, mono or t["head"])


CANDIDATES = {
    "A": {
        "label": "A  wide flat head, no neck, hairline line, thin ticks, major every 4th",
        "mark": lambda t, mono=None: "".join(
            ruler(t, mono, 12, 0.5, 0.5, 1.5, 3, (0.5, 2.5, 4.5, 6.5), (9.5, 11.5, 13.5, 15.5), (8, 8.5))
            + [head("M6.5 3.5H10V5L8.5 6.5V12.5H8V6.5L6.5 5Z", t, mono)]),
        "fav": lambda t: "".join(
            fav_ruler(t, 13, (0, 2, 4, 6), (10, 12, 14), (8, 9))
            + [head("M6 3H11V5H10V6H9V14H8V6H7V5H6Z", t)]),
    },
    "B": {
        "label": "B  no head, a heavy playhead bar crossing a thin ruler",
        "mark": lambda t, mono=None: "".join(
            ruler(t, mono, 10, 0.5, 0.5, 1.5, 3, (0.5, 2.5, 4.5), (11, 13, 15), (7, 9))
            + [head("M7 3.5H9V12.5H7Z", t, mono)]),
        "fav": lambda t: "".join(
            fav_ruler(t, 10, (1, 3, 5), (10, 12, 14), (7, 9))
            + [head("M7 3H9V14H7Z", t)]),
    },
    "C": {
        "label": "C  square head sitting on the rule (a slider thumb), hairline above",
        "mark": lambda t, mono=None: "".join(
            ruler(t, mono, 12, 0.5, 0.5, 1.5, 3, (0.5, 2.5, 4.5), (11.5, 13.5, 15.5), (6.5, 10))
            + [head("M6.5 8.5H8V3.5H8.5V8.5H10V12.5H6.5Z", t, mono)]),
        "fav": lambda t: "".join(
            fav_ruler(t, 13, (0, 2, 4), (12, 14), (6, 11))
            + [head("M6 9H8V3H9V9H11V14H6Z", t)]),
    },
}


def use(c):
    """Point build.py's drawing functions at candidate c, so its in_use() and wordmark() draw it."""
    B.mark_shapes = c["mark"]
    B.favicon_shapes = c["fav"]
    B.MARK_TOP, B.MARK_BOTTOM = 3.5, 12.5      # every candidate keeps the current visible rows
    B.MARK_H = B.MARK_BOTTOM - B.MARK_TOP


def sheet(disp, body, mono):
    """One sheet: per candidate a label band with the mark large on light and dark, then build.in_use()."""
    L, D = B.THEMES["light"], B.THEMES["dark"]
    band, use_h = 260, 460
    parts = []
    for i, (key, c) in enumerate(CANDIDATES.items()):
        use(c)
        y0 = i * (band + use_h + 40)
        label, _ = body.outline(c["label"], 22, 24, y0 + 40)
        parts.append('<g fill="%s">%s</g>' % (C_INK, label))
        for j, (t, ground) in enumerate(((L, B.C["Leader"]), (D, B.C["Reel"]))):
            x0 = 24 + j * 230
            parts.append(rect(x0, y0 + 60, 200, 180, ground))
            k = 160 / 16
            parts.append(B.place(c["mark"](t), x0 + 20, y0 + 60 + (180 - B.MARK_H * k) / 2, k))
        for j, (t, ground) in enumerate(((L, B.C["Leader"]), (D, B.C["Reel"]))):
            x0 = 520 + j * 400
            w, h, wm = B.wordmark(disp, t)
            s = 340.0 / w
            parts.append(rect(x0, y0 + 60, 380, 180, ground)
                         + '<g transform="translate(%d %.1f) scale(%.4f)">%s</g>' % (x0 + 20, y0 + 150 - h * s / 2, s, wm))
        inner = B.in_use(disp, body, mono)
        inner = inner[inner.index(">") + 1:inner.rindex("</svg>")]
        parts.append('<g transform="translate(0 %d)">%s</g>' % (y0 + band, inner))
    h = len(CANDIDATES) * (band + use_h + 40) - 40
    return B.svg(1320, h, "".join(parts), bg="#9AA39C", title="rewindagent logo candidates A, B, C")


C_INK = B.C["Reel"]


def main(fonts):
    fs = os.path.join(fonts, "node_modules", "@fontsource")
    disp = B.Face(os.path.join(fs, "bricolage-grotesque", "files", "bricolage-grotesque-latin-800-normal.woff"))
    body = B.Face(os.path.join(fs, "hanken-grotesk", "files", "hanken-grotesk-latin-600-normal.woff"))
    mono = B.Face(os.path.join(fs, "commit-mono", "files", "commit-mono-latin-400-normal.woff"))
    L = B.THEMES["light"]
    for key, c in CANDIDATES.items():
        with open(os.path.join(HERE, "%s-mark.svg" % key), "w", encoding="utf-8") as f:
            f.write(B.svg(16, 16, c["mark"](L)))
        with open(os.path.join(HERE, "%s-favicon.svg" % key), "w", encoding="utf-8") as f:
            f.write(B.svg(16, 16, c["fav"](L), bg=B.C["Leader"]))
    with open(os.path.join(HERE, "sheet.svg"), "w", encoding="utf-8") as f:
        f.write(sheet(disp, body, mono))
    print("wrote %d candidates + brand/logo/candidates/sheet.svg" % len(CANDIDATES))


if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(root, ".brandcache"))
