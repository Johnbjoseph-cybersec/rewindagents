"""Logo set (RB2): files exist at the right pixel sizes, SVGs use only the palette, text is outlined,
and the command printed on the social preview is one the CLI accepts. Stdlib only: the renderer is not needed."""
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

from contrast_check import PALETTE  # noqa: E402
from rewindagent.cli import main  # noqa: E402

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


class TestLogo(unittest.TestCase):
    def test_pngs_exist_at_size(self):
        for name, size in PNGS.items():
            self.assertEqual(png_size(os.path.join(BRAND, name)), size, name)

    def test_manifest_lists_every_png(self):
        with open(os.path.join(BRAND, "logo", "manifest.json"), encoding="utf-8") as f:
            manifest = json.load(f)
        self.assertEqual(set(manifest), set(PNGS))
        for name, spec in manifest.items():
            self.assertEqual(spec["width"], PNGS[name][0], name)
            self.assertTrue(os.path.isfile(os.path.join(BRAND, spec["src"])), spec["src"])

    def test_svgs_use_only_the_palette(self):
        allowed = {v.upper() for v in PALETTE.values()} | {"CURRENTCOLOR"}
        for path in all_svgs():
            root = ET.parse(path).getroot()
            for el in root.iter():
                tag = el.tag.replace(NS, "")
                self.assertNotIn(tag, ("text", "linearGradient", "radialGradient", "filter"), path)
                for attr in ("fill", "stroke"):
                    if attr in el.attrib:
                        self.assertIn(el.attrib[attr].upper(), allowed, "%s: %s=%s" % (path, attr, el.attrib[attr]))

    def test_mark_sits_on_the_16_grid(self):
        # Integer coordinates keep the mark and the separate 16 px favicon drawing sharp.
        for name in ("logo-mark.svg", "favicon.svg"):
            root = ET.parse(os.path.join(BRAND, name)).getroot()
            self.assertEqual(root.attrib["viewBox"], "0 0 16 16", name)
            for el in root.iter(NS + "rect"):
                for k in ("x", "y", "width", "height"):
                    self.assertTrue(float(el.attrib.get(k, 0)).is_integer(), (name, el.attrib))
            for el in root.iter(NS + "path"):
                for n in re.findall(r"-?\d+(?:\.\d+)?", el.attrib["d"]):
                    self.assertTrue(float(n).is_integer(), (name, el.attrib["d"]))

    def test_social_command_is_accepted_by_the_cli(self):
        with open(os.path.join(BRAND, "logo", "build.py"), encoding="utf-8") as f:
            cmd = re.search(r'^COMMAND = "([^"]+)"', f.read(), re.M).group(1)
        prefix = "python3 -m rewindagent "
        self.assertTrue(cmd.startswith(prefix), cmd)
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


if __name__ == "__main__":
    unittest.main()
