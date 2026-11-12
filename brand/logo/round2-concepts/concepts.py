"""Five new logo directions for rewindagent (task RB2f). John rejected every earlier mark on 2026-11-12 (the
playhead head, candidates A, B and C), so nothing here uses the ruler, tick or playhead family.

Every concept is one geometry on a 16-unit grid, kept as primitives that know two things: how to draw
themselves as SVG (the mark, sharp at any size), and whether a point is inside them. The 16 px favicon is
the same geometry point-sampled at pixel centres, so it is whole pixels with no anti-aliasing and cannot
drift from the mark. Stdlib only (no fonts): tests import this module directly.

  A  Counter-clock   a thick loop running anticlockwise (bottom, right, top, left), arrowhead at its end,
                     a red dot at its centre: time running backwards round one point
  B  Skip-back r     a lowercase r whose arm is a red back-pointing triangle, so it also reads as skip-back
  C  Loop track      a track that loops over itself once, a red dot where it starts
  D  Snapshot stack  three cards stacked back to front, the front one red: the checkpoints
  E  Reverse prompt  a terminal prompt turned round, '<' with a red cursor: the agent's shell, going back
"""
import math

PALETTE = {"Leader": "#F2F4F1", "Reel": "#121412", "Spool": "#1C201D", "Tape": "#55605A",
           "Record": "#B82A16", "Rewind": "#FF7A59", "Playhead": "#B9C2BB", "Rule": "#838C86"}
THEMES = {
    "light": {"ground": PALETTE["Leader"], "ink": PALETTE["Reel"], "accent": PALETTE["Record"]},
    "dark": {"ground": PALETTE["Reel"], "ink": PALETTE["Leader"], "accent": PALETTE["Rewind"]},
}


def g(v):
    return "%g" % round(v, 4)


class Ring:
    """An annulus centred (cx, cy) from r0 to r1, minus the screen-angle range `gap` (degrees, y down)."""

    def __init__(self, role, cx, cy, r0, r1, gap=None):
        self.role, self.cx, self.cy, self.r0, self.r1, self.gap = role, cx, cy, r0, r1, gap

    def svg(self, fill):
        cx, cy, r0, r1 = self.cx, self.cy, self.r0, self.r1
        if not self.gap:
            return ('<path fill-rule="evenodd" fill="%s" d="M%s %sa%s %s 0 1 0 %s 0a%s %s 0 1 0 %s 0Z'
                    'M%s %sa%s %s 0 1 0 %s 0a%s %s 0 1 0 %s 0Z"/>'
                    % (fill, g(cx - r1), g(cy), g(r1), g(r1), g(2 * r1), g(r1), g(r1), g(-2 * r1),
                       g(cx - r0), g(cy), g(r0), g(r0), g(2 * r0), g(r0), g(r0), g(-2 * r0)))
        a0, a1 = self.gap                      # draw from a1 round (decreasing angle) to a0 + 360
        p = lambda r, a: (cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
        large = 1 if (360 - (a1 - a0)) > 180 else 0
        (x1, y1), (x2, y2) = p(r1, a0), p(r1, a1)
        (x3, y3), (x4, y4) = p(r0, a1), p(r0, a0)
        return ('<path fill="%s" d="M%s %sA%s %s 0 %d 0 %s %sL%s %sA%s %s 0 %d 1 %s %sZ"/>'
                % (fill, g(x1), g(y1), g(r1), g(r1), large, g(x2), g(y2), g(x3), g(y3), g(r0), g(r0),
                   large, g(x4), g(y4)))

    def inside(self, x, y):
        d = math.hypot(x - self.cx, y - self.cy)
        if not self.r0 <= d <= self.r1:
            return False
        if self.gap:
            a = math.degrees(math.atan2(y - self.cy, x - self.cx))
            return not self.gap[0] < a < self.gap[1]
        return True


class Dot:
    def __init__(self, role, cx, cy, r):
        self.role, self.cx, self.cy, self.r = role, cx, cy, r

    def svg(self, fill):
        return '<circle cx="%s" cy="%s" r="%s" fill="%s"/>' % (g(self.cx), g(self.cy), g(self.r), fill)

    def inside(self, x, y):
        return math.hypot(x - self.cx, y - self.cy) <= self.r


class Poly:
    def __init__(self, role, pts):
        self.role, self.pts = role, pts

    def svg(self, fill):
        return '<path fill="%s" d="M%sZ"/>' % (fill, "L".join("%s %s" % (g(x), g(y)) for x, y in self.pts))

    def inside(self, x, y):
        n, c = len(self.pts), False
        for i in range(n):
            (x1, y1), (x2, y2) = self.pts[i], self.pts[i - 1]
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                c = not c
        return c


def box(role, x, y, w, h):
    return Poly(role, [(x, y), (x + w, y), (x + w, y + h), (x, y + h)])


class Card:
    """A rounded card: filled with `fill_role`, or a ground-filled card with an `edge`-wide outline inside it
    (outline role `role`), so a card in front hides the ones behind it."""

    def __init__(self, role, x, y, w, h, r, edge=None):
        self.role, self.x, self.y, self.w, self.h, self.r, self.edge = role, x, y, w, h, r, edge

    def _in(self, px, py, x, y, w, h, r):
        if not (x <= px <= x + w and y <= py <= y + h):
            return False
        cx = min(max(px, x + r), x + w - r)
        cy = min(max(py, y + r), y + h - r)
        return math.hypot(px - cx, py - cy) <= r

    def svg(self, fill, ground=None):
        if self.edge is None:
            return '<rect x="%s" y="%s" width="%s" height="%s" rx="%s" fill="%s"/>' % (
                g(self.x), g(self.y), g(self.w), g(self.h), g(self.r), fill)
        e = self.edge
        return ('<rect x="%s" y="%s" width="%s" height="%s" rx="%s" fill="%s"/>'
                '<rect x="%s" y="%s" width="%s" height="%s" rx="%s" fill="%s"/>'
                % (g(self.x), g(self.y), g(self.w), g(self.h), g(self.r), fill,
                   g(self.x + e), g(self.y + e), g(self.w - 2 * e), g(self.h - 2 * e), g(max(self.r - e, 0)),
                   ground))

    def cover(self, px, py):
        """'role' on the outline (or the whole card when filled), 'ground' inside an outlined card, else None."""
        if not self._in(px, py, self.x, self.y, self.w, self.h, self.r):
            return None
        if self.edge is None:
            return self.role
        e = self.edge
        inner = self._in(px, py, self.x + e, self.y + e, self.w - 2 * e, self.h - 2 * e, max(self.r - e, 0))
        return "ground" if inner else self.role


class Stroke:
    """A polyline of width w with round joins (point test) drawn as an SVG stroke with miter joins."""

    def __init__(self, role, pts, w):
        self.role, self.pts, self.w = role, pts, w

    def svg(self, fill):
        return ('<polyline points="%s" fill="none" stroke="%s" stroke-width="%s" stroke-linejoin="miter" '
                'stroke-linecap="butt"/>' % (" ".join("%s,%s" % (g(x), g(y)) for x, y in self.pts), fill,
                                             g(self.w)))

    def inside(self, x, y):
        for (x1, y1), (x2, y2) in zip(self.pts, self.pts[1:]):
            dx, dy = x2 - x1, y2 - y1
            t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
            if math.hypot(x - x1 - t * dx, y - y1 - t * dy) <= self.w / 2:
                return True
        return False


CONCEPTS = {
    "A": {
        "name": "Counter-clock",
        "idea": "a loop running anticlockwise round a red dot: time going backwards round one point",
        "parts": [Ring("ink", 9.0, 8.0, 3.75, 5.75, gap=(90, 180)),
                  Poly("ink", [(1.0, 8.0), (7.5, 8.0), (4.25, 12.0)]),
                  Dot("accent", 9.0, 8.0, 1.65)],
    },
    "B": {
        "name": "Skip-back r",
        "idea": "a lowercase r whose arm is a red back-pointing triangle, so it also reads as skip-back",
        "parts": [box("ink", 3.0, 3.5, 3.0, 10.0),
                  Poly("accent", [(5.5, 7.0), (13.0, 3.25), (13.0, 10.75)])],
    },
    "C": {
        "name": "Loop track",
        "idea": "a track that loops back over itself once, a red dot where it starts",
        "parts": [box("ink", 2.0, 11.5, 13.5, 1.75),
                  Ring("ink", 10.0, 7.75, 3.5, 5.5),
                  Dot("accent", 2.5, 12.375, 2.0)],
    },
    "D": {
        "name": "Snapshot stack",
        "idea": "three cards stacked back to front, the front one red: the checkpoints",
        "cards": [Card("ink", 5.75, 3.0, 8.5, 6.5, 1.25, edge=1.25),
                  Card("ink", 3.75, 5.0, 8.5, 6.5, 1.25, edge=1.25),
                  Card("accent", 1.75, 7.0, 8.5, 6.5, 1.25)],
    },
    "E": {
        "name": "Reverse prompt",
        "idea": "a terminal prompt turned round, '<' with a red cursor: the agent's shell, going back",
        "parts": [Stroke("ink", [(8.0, 3.5), (3.0, 8.5), (8.0, 13.5)], 2.25),
                  box("accent", 10.0, 11.0, 5.0, 2.25)],
    },
}


def mark_svg(key, t):
    """The mark's SVG elements on the 16 grid, coloured for theme t."""
    c = CONCEPTS[key]
    if "cards" in c:
        return "".join(card.svg(t[card.role], t["ground"]) for card in c["cards"])
    return "".join(p.svg(t[p.role]) for p in c["parts"])


def role_at(key, x, y):
    """Which role covers grid point (x, y): the last drawn part wins, as in the SVG."""
    c = CONCEPTS[key]
    if "cards" in c:
        hit = None
        for card in c["cards"]:
            r = card.cover(x, y)
            if r is not None:
                hit = None if r == "ground" else r
        return hit
    hit = None
    for p in c["parts"]:
        if p.inside(x, y):
            hit = p.role
    return hit


def favicon_grid(key):
    """The 16 px drawing: 16 rows of 16 roles (None = ground), sampled at pixel centres."""
    return [[role_at(key, i + 0.5, j + 0.5) for i in range(16)] for j in range(16)]


def favicon_svg(key, t):
    """The 16 px drawing as whole-pixel rects (runs merged per row) on the theme ground."""
    out = ['<rect width="16" height="16" fill="%s"/>' % t["ground"]]
    for j, row in enumerate(favicon_grid(key)):
        i = 0
        while i < 16:
            if row[i] is None:
                i += 1
                continue
            k = i
            while k < 16 and row[k] == row[i]:
                k += 1
            out.append('<rect x="%d" y="%d" width="%d" height="1" fill="%s"/>' % (i, j, k - i, t[row[i]]))
            i = k
    return "".join(out)


def ascii_grid(key):
    sym = {None: ".", "ink": "#", "accent": "o"}
    return "\n".join("".join(sym[r] for r in row) for row in favicon_grid(key))


if __name__ == "__main__":
    for k, c in CONCEPTS.items():
        print("%s  %s\n%s\n" % (k, c["name"], ascii_grid(k)))
