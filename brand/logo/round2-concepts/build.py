"""One review sheet for the five RB2f logo directions (concepts.py), each shown where it will be seen:
the mark large on light and dark, a Product Hunt thumbnail (240 x 240), a README header on a light and a
dark page, browser tabs with the favicon at true 16 px, the same drawing at 32 px, and the GitHub avatar
circle at 96 and 20 px. Text is outlined from the brand fonts (brand/logo/build.py's Face), so the sheet
renders the same with no fonts installed. Review material only: nothing here is shipped.

Usage: .venv/bin/python brand/logo/round2-concepts/build.py [<fonts-dir>]
       node brand/logo/round2-concepts/render.mjs        (sheet.svg -> sheet.png, tiles.svg -> tiles.png)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import concepts as K  # noqa: E402
import build as LB  # noqa: E402  (brand/logo/build.py: Face, svg)

P = K.PALETTE
L, D = K.THEMES["light"], K.THEMES["dark"]
PH = {"ground": P["Record"], "ink": P["Leader"], "accent": P["Reel"]}
TAGLINE = LB.TAGLINE
ROW_H = 300
SHEET_W = 1320


def place(shapes, x, y, size):
    """The 16-grid drawing scaled so the grid is `size` px square, top-left at (x, y)."""
    return '<g transform="translate(%s %s) scale(%s)">%s</g>' % (K.g(x), K.g(y), K.g(size / 16.0), shapes)


def text(face, s, size, x, baseline, fill, tracking=0.0):
    d, adv = face.outline(s, size, x, baseline, tracking)
    return '<g fill="%s">%s</g>' % (fill, d), adv


def wordmark(key, disp, t, x, y, width):
    """Mark + 'rewindagent' laid out at 100 px type, scaled to `width`. The mark's grid is 1.9x the ascender
    (the drawings leave about a fifth of the grid empty) and centred on the middle of the ascender."""
    size = 100.0
    asc = disp.bounds("d", size)[3]
    grid = 1.9 * asc
    gap = 0.22 * size
    name, adv = text(disp, "rewindagent", size, grid + gap, asc + (grid - asc) / 2, t["ink"], tracking=-0.02)
    w = grid + gap + adv
    s = width / w
    return ('<g transform="translate(%s %s) scale(%s)">%s%s</g>'
            % (K.g(x), K.g(y), K.g(s), place(K.mark_svg(key, t), 0, 0, grid), name)), grid * s


def circle(key, cx, cy, r, uid, small=False):
    """The avatar as GitHub crops it. 96 px uses the mark; 20 px uses the 16 px pixel drawing at 1.25x."""
    inner = (place(K.favicon_svg(key, L), cx - r, cy - r, 2 * r) if small
             else place(K.mark_svg(key, L), cx - r * 0.8, cy - r * 0.8, 1.6 * r))
    return ('<clipPath id="%s"><circle cx="%s" cy="%s" r="%s"/></clipPath><g clip-path="url(#%s)">'
            '<circle cx="%s" cy="%s" r="%s" fill="%s"/>%s</g>'
            % (uid, cx, cy, r, uid, cx, cy, r, L["ground"], inner))


def row(key, disp, body, y0):
    c = K.CONCEPTS[key]
    out = []
    head, adv = text(disp, "%s  %s" % (key, c["name"]), 22, 24, y0 + 30, P["Reel"])
    idea, _ = text(body, c["idea"], 16, 24 + adv + 16, y0 + 30, P["Spool"])
    out += [head, idea]
    top = y0 + 46
    # 1. the mark large, light and dark grounds
    for i, t in enumerate((L, D)):
        x = 24 + i * 212
        out.append(LB.rect(x, top, 200, 240, t["ground"]) + place(K.mark_svg(key, t), x + 20, top + 40, 160))
    # 2. Product Hunt thumbnail 240 x 240 on the brand red, so it is not a copy of the dark tile
    out.append(LB.rect(460, top, 240, 240, PH["ground"]) + place(K.mark_svg(key, PH), 460 + 45, top + 45, 150))
    # 3. README header, light page and dark page
    for i, t in enumerate((L, D)):
        y = top + i * 124
        wm, mh = wordmark(key, disp, t, 744, y + 18, 300)
        tag, _ = text(body, TAGLINE, 13, 744, y + 18 + mh + 26, t["ink"])
        out.append(LB.rect(724, y, 380, 116, t["ground"]) + wm + tag)
    # 4. browser tabs at true size (light, dark), the 16 px drawing at 32 px, avatar circles 96 and 20
    for i, (t, strip) in enumerate(((L, P["Playhead"]), (D, P["Spool"]))):
        y = top + i * 44
        title, _ = text(body, "rewindagent", 13, 1162, y + 26, t["ink"])
        out.append(LB.rect(1124, y, 176, 38, strip)
                   + '<rect x="1130" y="%d" width="164" height="32" rx="6" fill="%s"/>' % (y + 6, t["ground"])
                   + place(K.favicon_svg(key, t), 1138, y + 14, 16) + title)
    out.append(place(K.favicon_svg(key, L), 1124, top + 100, 32))
    lab, _ = text(body, "16 px drawing at 32", 11, 1164, top + 120, P["Spool"])
    out.append(lab)
    out.append(circle(key, 1172, top + 188, 48, "a96" + key))
    out.append(circle(key, 1262, top + 188, 10, "a20" + key, small=True))
    return "".join(out)


def sheet(disp, body):
    parts = [row(k, disp, body, i * ROW_H) for i, k in enumerate(K.CONCEPTS)]
    return LB.svg(SHEET_W, ROW_H * len(K.CONCEPTS), "".join(parts), bg="#9AA39C",
                  title="rewindagent logo directions A to E, in use")


def tiles():
    """Each 16 px drawing at true size and at 8x, for pixel inspection (rendered with nearest neighbour)."""
    parts = []
    for i, k in enumerate(K.CONCEPTS):
        x = 10 + i * 150
        parts.append(place(K.favicon_svg(k, L), x, 10, 16) + place(K.favicon_svg(k, L), x, 36, 128)
                     + place(K.favicon_svg(k, D), x, 174, 128))
    return LB.svg(10 + 150 * len(K.CONCEPTS), 312, "".join(parts), bg="#9AA39C",
                  title="rewindagent logo directions, 16 px drawings")


def main(fonts):
    fs = os.path.join(fonts, "node_modules", "@fontsource")
    disp = LB.Face(os.path.join(fs, "bricolage-grotesque", "files", "bricolage-grotesque-latin-800-normal.woff"))
    body = LB.Face(os.path.join(fs, "hanken-grotesk", "files", "hanken-grotesk-latin-600-normal.woff"))
    files = {"sheet.svg": sheet(disp, body), "tiles.svg": tiles()}
    for k in K.CONCEPTS:
        files["%s-mark.svg" % k] = LB.svg(16, 16, K.mark_svg(k, L))
        files["%s-favicon.svg" % k] = LB.svg(16, 16, K.favicon_svg(k, L))
    for name, s in files.items():
        with open(os.path.join(HERE, name), "w", encoding="utf-8") as f:
            f.write(s)
    print("wrote %d files in brand/logo/round2-concepts/" % len(files))


if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(root, ".brandcache"))
