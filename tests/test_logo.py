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

    def test_rewound_steps_are_drawn_after_the_playhead(self):
        # The concept (RB2d pick B): a headless playhead bar crossing a thin ruler. Everything right of the bar
        # is the rewound part (grey rule, grey ticks). Ticks are thin, at an even pitch each side, with the same
        # gap to the bar on both sides; the taller tick is only at the two outer ends; the bar is the only tall
        # element.
        root = ET.parse(os.path.join(BRAND, "logo-mark.svg")).getroot()
        rects = [el.attrib for el in root.iter(NS + "rect")]
        bar = next(el for el in root.iter(NS + "path")).attrib["d"]
        xs = [float(v) for v in re.findall(r"[MH](-?[\d.]+)", bar)]
        ys = [float(v) for v in re.findall(r"(?:M-?[\d.]+ |V)(-?[\d.]+)", bar)]
        lo, hi = min(xs), max(xs)
        ink, grey = PALETTE["Reel"].upper(), PALETTE["Rule"].upper()
        ticks = sorted((r for r in rects if float(r["height"]) > float(r["width"])), key=lambda r: float(r["x"]))
        rules = [r for r in rects if float(r["width"]) > float(r["height"])]
        left = [r for r in ticks if float(r["x"]) < lo]
        right = [r for r in ticks if float(r["x"]) >= hi]
        self.assertEqual(len(left) + len(right), len(ticks), "a tick under the bar")
        self.assertEqual(len(left), len(right))
        self.assertGreaterEqual(len(left), 3)
        self.assertEqual({r["width"] for r in ticks}, {"0.5"}, "ticks are thin")
        self.assertEqual(round(lo - (float(left[-1]["x"]) + 0.5), 3), round(float(right[0]["x"]) - hi, 3),
                         "gaps to the bar differ")
        for side in (left, right):
            pitches = {round(float(b["x"]) - float(a["x"]), 3) for a, b in zip(side, side[1:])}
            self.assertEqual(len(pitches), 1, pitches)
        heights = [float(r["height"]) for r in ticks]
        tall = max(heights)
        self.assertEqual([i for i, h in enumerate(heights) if h == tall], [0, len(ticks) - 1], heights)
        self.assertEqual(len(set(heights)), 2, heights)
        rule_top = min(float(r["y"]) for r in rules)
        for r in ticks:
            self.assertEqual(float(r["y"]) + float(r["height"]), rule_top, "tick not standing on the rule")
            self.assertEqual(r["fill"].upper(), ink if float(r["x"]) < lo else grey, r)
        self.assertGreater(max(ys) - min(ys), 2.5 * tall)
        self.assertEqual({r["fill"].upper() for r in rules if float(r["x"]) < lo}, {ink})
        self.assertEqual({r["fill"].upper() for r in rules if float(r["x"]) >= hi}, {grey})

    def test_png_pixels_match_brand_md(self):
        # Palette fidelity is measured, not eyeballed: build.py records where each colour must appear.
        results = list(pngsample.check())
        self.assertGreaterEqual(len(results), 20)
        for png, x, y, name, want, got, ok in results:
            self.assertTrue(ok, "%s (%d,%d): %s should be %s, sampled %s" % (png, x, y, name, want, got))
        self.assertEqual({r[3] for r in results} >= {"Leader", "Reel", "Record", "Rewind", "Rule", "Tape"}, True)

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
