"""RB2f logo directions (brand/logo/round2-concepts/): five concepts, each a geometry whose 16 px drawing is
point-sampled from the same primitives as the mark, palette colours only, the committed SVGs equal what
concepts.py draws, the review sheet exists at its built size, and the critic's review is pinned to the
sheet it looked at. Stdlib only."""
import hashlib
import json
import os
import re
import struct
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, "brand", "logo", "round2-concepts")
sys.path.insert(0, DIR)

import concepts as K  # noqa: E402


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    assert head[:8] == b"\x89PNG\r\n\x1a\n", path
    return struct.unpack(">II", head[16:24])


def read(name):
    with open(os.path.join(DIR, name), encoding="utf-8") as f:
        return f.read()


class TestRound2Concepts(unittest.TestCase):
    def test_five_named_directions(self):
        self.assertEqual(list(K.CONCEPTS), ["A", "B", "C", "D", "E"])
        names = [c["name"] for c in K.CONCEPTS.values()]
        self.assertEqual(len(set(names)), 5)
        for c in K.CONCEPTS.values():
            self.assertTrue(c["idea"])

    def test_favicon_is_16_by_16_with_ink_and_accent(self):
        for k in K.CONCEPTS:
            grid = K.favicon_grid(k)
            self.assertEqual([len(r) for r in grid], [16] * 16, k)
            flat = [v for r in grid for v in r]
            self.assertGreaterEqual(flat.count("accent"), 4, k)
            self.assertGreaterEqual(flat.count("ink"), 10, k)
            # the drawing stays off the outer pixel ring on at least three sides (room in a tab)
            edges = [grid[0], grid[15], [r[0] for r in grid], [r[15] for r in grid]]
            self.assertGreaterEqual(sum(1 for e in edges if not any(e)), 3, k)

    def test_favicon_svg_whole_pixels(self):
        for k in K.CONCEPTS:
            s = K.favicon_svg(k, K.THEMES["light"])
            for m in re.finditer(r'<rect ([^>]*)/>', s):
                for attr in ("x", "y", "width", "height"):
                    v = re.search(r'\b%s="([^"]*)"' % attr, m.group(1))
                    if v:
                        self.assertTrue(float(v.group(1)).is_integer(), (k, m.group(0)))

    def test_palette_only(self):
        allowed = {v.upper() for v in K.PALETTE.values()}
        for k in K.CONCEPTS:
            for t in K.THEMES.values():
                for s in (K.mark_svg(k, t), K.favicon_svg(k, t)):
                    used = {h.upper() for h in re.findall(r"#[0-9A-Fa-f]{6}", s)}
                    self.assertTrue(used <= allowed, (k, used - allowed))

    def test_point_test_agrees_with_the_drawing(self):
        # centre of each concept's accent part is accent in role_at, so the 16 px drawing and the mark agree
        probes = {"A": (9.0, 8.0), "B": (11.0, 7.0), "C": (2.5, 12.4), "D": (6.0, 10.25), "E": (12.5, 12.1)}
        for k, (x, y) in probes.items():
            self.assertEqual(K.role_at(k, x, y), "accent", k)
        self.assertIsNone(K.role_at("D", 10.0, 4.75))      # inside the back card: ground, not ink
        self.assertEqual(K.role_at("A", 9.0, 2.75), "ink")  # top of the loop
        self.assertIsNone(K.role_at("A", 5.5, 12.0))        # the open lower-left quarter

    def test_committed_svgs_match_concepts(self):
        L = K.THEMES["light"]
        for k in K.CONCEPTS:
            self.assertIn(K.mark_svg(k, L), read("%s-mark.svg" % k), k)
            self.assertIn(K.favicon_svg(k, L), read("%s-favicon.svg" % k), k)
        sheet = read("sheet.svg")
        for k in K.CONCEPTS:
            self.assertIn(K.mark_svg(k, K.THEMES["dark"]), sheet, k)

    def test_sheet_rendered(self):
        self.assertEqual(png_size(os.path.join(DIR, "sheet.png")), (1320, 1500))
        self.assertEqual(png_size(os.path.join(DIR, "tiles.png")), (1520, 624))

    def test_review_pinned_to_the_sheet(self):
        with open(os.path.join(DIR, "review.json"), encoding="utf-8") as f:
            review = json.load(f)
        with open(os.path.join(DIR, "sheet.png"), "rb") as f:
            self.assertEqual(review["sheet_sha256"], hashlib.sha256(f.read()).hexdigest())
        self.assertEqual(sorted(c["key"] for c in review["concepts"]), list(K.CONCEPTS))
        for c in review["concepts"]:
            self.assertTrue(c["first_reading"], c["key"])
            self.assertIsInstance(c["score"], (int, float), c["key"])
        self.assertEqual(review["decides"], "John")


if __name__ == "__main__":
    unittest.main()
