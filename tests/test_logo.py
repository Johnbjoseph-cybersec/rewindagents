"""Logo set (RB2): files exist at the right pixel sizes, SVGs use only the palette, text is outlined,
the command printed on the social preview is one the CLI accepts, and the rendered PNGs' pixels match the
BRAND.md hex values at the points build.py recorded. Stdlib only: the renderer is not needed."""
import io
import json
import os
import re
import struct
import sys
import unittest
import xml.etree.ElementTree as ET
from contextlib import redirect_stderr, redirect_stdout
from tempfile import TemporaryDirectory

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRAND = os.path.join(ROOT, "brand")
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, BRAND)
sys.path.insert(0, os.path.join(BRAND, "logo"))

from contrast_check import PALETTE  # noqa: E402
from rewindagent.cli import main  # noqa: E402
import pngsample  # noqa: E402

PNGS = {"logo-light.png": (1024, 1024), "logo-dark.png": (1024, 1024), "avatar-512.png": (512, 512),
        "favicon-32.png": (32, 32), "social-preview-1280x640.png": (1280, 640)}
SVGS = ["logo-mark.svg", "logo-mark-reverse.svg", "logo-mark-mono.svg", "logo-wordmark.svg",
        "logo-wordmark-reverse.svg", "logo-wordmark-mono.svg", "favicon.svg"]
NS = "{http://www.w3.org/2000/svg}"


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    assert head[:8] == b"\x89PNG\r\n\x1a\n", path
    return struct.unpack(">II", head[16:24])


def all_svgs():
    out = [os.path.join(BRAND, n) for n in SVGS]
    src = os.path.join(BRAND, "logo", "src")
    out += [os.path.join(src, n) for n in sorted(os.listdir(src)) if n.endswith(".svg")]
    return out


def mark_geometry():
    """The '<' polygon and the cursor (x, y, w, h) read from brand/logo-mark.svg."""
    root = ET.parse(os.path.join(BRAND, "logo-mark.svg")).getroot()
    d = next(root.iter(NS + "path")).attrib["d"]
    nums = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", d)]
    pts = list(zip(nums[::2], nums[1::2]))
    r = next(root.iter(NS + "rect")).attrib
    return pts, tuple(float(r[k]) for k in ("x", "y", "width", "height"))


def point_in(pts, x, y):
    c = False
    for i in range(len(pts)):
        (x1, y1), (x2, y2) = pts[i], pts[i - 1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def manifest():
    with open(os.path.join(BRAND, "logo", "manifest.json"), encoding="utf-8") as f:
        return json.load(f)


class TestLogo(unittest.TestCase):
    def test_pngs_exist_at_size(self):
        for name, size in PNGS.items():
            self.assertEqual(png_size(os.path.join(BRAND, name)), size, name)

    def test_manifest_lists_every_png(self):
        m = manifest()
        self.assertEqual(set(m), set(PNGS))
        for name, spec in m.items():
            self.assertEqual(spec["width"], PNGS[name][0], name)
            self.assertTrue(os.path.isfile(os.path.join(BRAND, spec["src"])), spec["src"])
            self.assertGreaterEqual(len(spec["samples"]), 4, name)

    def test_svgs_use_only_the_palette(self):
        allowed = {v.upper() for v in PALETTE.values()} | {"CURRENTCOLOR", "NONE"}
        for path in all_svgs():
            root = ET.parse(path).getroot()
            for el in root.iter():
                tag = el.tag.replace(NS, "")
                self.assertNotIn(tag, ("text", "linearGradient", "radialGradient", "filter"), path)
                for attr in ("fill", "stroke"):
                    if attr in el.attrib:
                        self.assertIn(el.attrib[attr].upper(), allowed, "%s: %s=%s" % (path, attr, el.attrib[attr]))

    def test_mark_sits_on_the_16_grid(self):
        # The favicon is a whole-unit drawing (sharp at 16 px); the mark may use halves (sharp from 32 px).
        for name, step in (("logo-mark.svg", 0.5), ("favicon.svg", 1.0)):
            root = ET.parse(os.path.join(BRAND, name)).getroot()
            self.assertEqual(root.attrib["viewBox"], "0 0 16 16", name)
            for el in root.iter(NS + "rect"):
                for k in ("x", "y", "width", "height"):
                    self.assertTrue((float(el.attrib.get(k, 0)) / step).is_integer(), (name, el.attrib))
            for el in root.iter(NS + "path"):
                for n in re.findall(r"-?\d+(?:\.\d+)?", el.attrib["d"]):
                    self.assertTrue((float(n) / step).is_integer(), (name, el.attrib["d"]))

    def test_social_command_is_accepted_by_the_cli(self):
        with open(os.path.join(BRAND, "logo", "build.py"), encoding="utf-8") as f:
            cmd = re.search(r'^COMMAND = "([^"]+)"', f.read(), re.M).group(1)
        prefixes = ("rewindagent ", "python3 -m rewindagent ")
        prefix = next((p for p in prefixes if cmd.startswith(p)), None)
        self.assertIsNotNone(prefix, cmd)
        with TemporaryDirectory() as d:
            argv = ["--log", os.path.join(d, "log.jsonl")] + cmd[len(prefix):].split() + ["--dry-run"]
            err = io.StringIO()
            try:
                with redirect_stdout(io.StringIO()), redirect_stderr(err):
                    main(argv)
            except SystemExit as e:
                # argparse exits 2 on a bad command line; anything else (an empty log) is past parsing.
                self.assertNotEqual(e.code, 2, err.getvalue())
            except Exception:  # noqa: BLE001 - only the parse matters here
                pass

    def test_mark_is_unchanged_in_every_variant(self):
        # Reverse and mono variants differ from the mark only in colour.
        def shapes(name):
            root = ET.parse(os.path.join(BRAND, name)).getroot()
            return [(el.tag, {k: v for k, v in el.attrib.items() if k != "fill"}) for el in root.iter()
                    if el.tag in (NS + "rect", NS + "path")]
        base = shapes("logo-mark.svg")
        for name in ("logo-mark-reverse.svg", "logo-mark-mono.svg"):
            self.assertEqual(shapes(name), base, name)

    def test_mark_is_a_reverse_prompt(self):
        # The concept (RB2f pick E, John 2026-11-12): a '<' in ink and a block cursor in Record. The '<' has
        # 45-degree arms of equal width, a point on the left, flat cuts at top and bottom; the cursor sits on
        # the '<''s bottom line (one typed line), right of the '<' and clear of it.
        pts, cur = mark_geometry()
        self.assertEqual(len(pts), 6, pts)
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        top, bottom = min(ys), max(ys)
        apex = min(pts)
        self.assertEqual(apex[1], (top + bottom) / 2, "the point is not halfway down")
        for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
            dx, dy = abs(x2 - x1), abs(y2 - y1)
            self.assertTrue(dy == 0 or dx == dy, "edge %s-%s is neither a flat cut nor 45 degrees"
                            % ((x1, y1), (x2, y2)))
        cuts = sorted(abs(x2 - x1) for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]) if y1 == y2)
        self.assertEqual(len(cuts), 2)
        self.assertEqual(cuts[0], cuts[1], "the two arms differ in width")
        cx, cy, cw, ch = cur
        self.assertEqual(cy + ch, bottom, "the cursor is not on the '<''s bottom line")
        self.assertGreaterEqual(cx - max(xs), 1, "the cursor touches the '<'")
        self.assertGreater(cw, ch, "the cursor is not a low block")
        self.assertLessEqual(cx + cw, 16)
        root = ET.parse(os.path.join(BRAND, "logo-mark.svg")).getroot()
        fills = {el.tag.replace(NS, ""): el.attrib["fill"].upper() for el in root.iter()
                 if el.tag in (NS + "rect", NS + "path")}
        self.assertEqual(fills, {"path": PALETTE["Reel"].upper(), "rect": PALETTE["Record"].upper()})

    def test_favicon_is_the_mark_sampled_on_whole_pixels(self):
        # The 16 px drawing cannot drift from the mark: each pixel is the mark's role at the pixel centre
        # (nudged a quarter pixel right, so a 45-degree edge through a centre falls on one side).
        pts, (cx, cy, cw, ch) = mark_geometry()
        want = {}
        for j in range(16):
            for i in range(16):
                x, y = i + 0.75, j + 0.5
                if cx <= x < cx + cw and cy <= y < cy + ch:
                    want[(i, j)] = PALETTE["Record"].upper()
                elif point_in(pts, x, y):
                    want[(i, j)] = PALETTE["Reel"].upper()
        got = {}
        root = ET.parse(os.path.join(BRAND, "favicon.svg")).getroot()
        for el in root.iter(NS + "rect"):
            a = el.attrib
            if "x" not in a:                      # the ground
                self.assertEqual(a["fill"].upper(), PALETTE["Leader"].upper())
                continue
            self.assertEqual(a["height"], "1", a)
            for i in range(int(a["x"]), int(a["x"]) + int(a["width"])):
                got[(i, int(a["y"]))] = a["fill"].upper()
        self.assertEqual(got, want)
        rows = {}
        for (i, j), fill in got.items():
            if fill == PALETTE["Reel"].upper():
                rows.setdefault(j, []).append(i)
        self.assertEqual(len({len(v) for v in rows.values()}), 1, "the '<' is not an even staircase")
        for j, xs in rows.items():
            self.assertEqual(xs, list(range(min(xs), max(xs) + 1)), "row %d has a hole" % j)
        cursor_x = min(i for (i, j), f in got.items() if f == PALETTE["Record"].upper())
        foot = max(max(xs) for xs in rows.values())
        self.assertGreaterEqual(cursor_x - foot - 1, 1, "no clear pixel between the '<' and the cursor")

    def test_png_pixels_match_brand_md(self):
        # Palette fidelity is measured, not eyeballed: build.py records where each colour must appear.
        results = list(pngsample.check())
        self.assertGreaterEqual(len(results), 20)
        for png, x, y, name, want, got, ok in results:
            self.assertTrue(ok, "%s (%d,%d): %s should be %s, sampled %s" % (png, x, y, name, want, got))
        self.assertEqual({r[3] for r in results} >= {"Leader", "Reel", "Record", "Rewind"}, True)

    def test_in_use_install_line_is_the_readme_install_line(self):
        # The in-use sheet shows an install command; it must be the one the README gives, not a variant.
        with open(os.path.join(BRAND, "logo", "build.py"), encoding="utf-8") as f:
            install = re.search(r'^INSTALL = "([^"]+)"', f.read(), re.M).group(1)
        with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
            self.assertIn(install, f.read())

    def test_in_use_sheet_exists(self):
        # The reviewer judges the mark where it is seen (tab, README, avatar crops), not alone.
        self.assertEqual(png_size(os.path.join(BRAND, "logo", "in-use.png")), (1320, 460))


if __name__ == "__main__":
    unittest.main()
