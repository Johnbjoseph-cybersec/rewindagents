#!/usr/bin/env python3
"""WCAG 2.x contrast checker for every text/background pair listed in BRAND.md.

Stdlib only. Prints a table. Exit 1 if any body pair < 4.5 or any large pair < 3.0.
kind: body = normal text (needs 4.5), large = >= 24px regular or >= 18.66px bold (needs 3.0).
"""
import sys

PALETTE = {
    "Leader":    "#F2F4F1",  # paper ground
    "Reel":      "#121412",  # ink / dark ground
    "Spool":     "#1C201D",  # dark surface (terminal, code)
    "Tape":      "#55605A",  # secondary text on Leader
    "Record":    "#B82A16",  # accent on Leader
    "Rewind":    "#FF7A59",  # accent on Reel / Spool
    "Playhead":  "#B9C2BB",  # secondary text on Reel / Spool
    "Rule":      "#838C86",  # hairlines, ticks (non-text, informational)
}

# (foreground, background, kind, usage)
PAIRS = [
    ("Reel",     "Leader", "body",  "body text on paper"),
    ("Tape",     "Leader", "body",  "secondary text on paper"),
    ("Record",   "Leader", "body",  "links and accent text on paper"),
    ("Leader",   "Record", "body",  "label on accent button / tag"),
    ("Leader",   "Reel",   "body",  "body text on dark"),
    ("Playhead", "Reel",   "body",  "secondary text on dark"),
    ("Rewind",   "Reel",   "body",  "accent text on dark"),
    ("Leader",   "Spool",  "body",  "terminal text on dark surface"),
    ("Playhead", "Spool",  "body",  "terminal comments on dark surface"),
    ("Rewind",   "Spool",  "body",  "terminal accent on dark surface"),
    ("Reel",     "Rewind", "body",  "label on accent block, dark ground"),
    ("Record",   "Leader", "large", "display headline accent on paper"),
    ("Rewind",   "Reel",   "large", "display headline accent on dark"),
    ("Rule",     "Leader", "large", "rules and tick marks (graphical, 3.0)"),
    ("Rule",     "Reel",   "large", "rules and tick marks on dark (graphical, 3.0)"),
]


def _lin(c):
    c /= 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hexv):
    h = hexv.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def ratio(fg, bg):
    a, b = luminance(fg), luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def main():
    need = {"body": 4.5, "large": 3.0}
    print("%-9s %-9s %-7s %-7s %-6s %-5s %s" % ("text", "on", "fg", "bg", "ratio", "need", "result / use"))
    fails = 0
    for fg, bg, kind, use in PAIRS:
        f, b = PALETTE[fg], PALETTE[bg]
        r = ratio(f, b)
        ok = r >= need[kind]
        fails += 0 if ok else 1
        print("%-9s %-9s %-7s %-7s %-6s %-5s %s (%s, %s)" % (
            fg, bg, f, b, "%.2f" % r, "%.1f" % need[kind], "PASS" if ok else "FAIL", kind, use))
    print("%d pairs, %d failing" % (len(PAIRS), fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
