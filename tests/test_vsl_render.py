"""brand/vsl-*.mp4 (RB4b): the three VSL renders exist and are what the scripts say. Size, frame rate, length and
codecs are read from the files themselves (brand/vsl/mp4info.py, stdlib); the length is the beats' total; the
captions burnt into the picture are the cues of brand/vsl/build.py word for word, and the .srt beside each video
is the committed brand/vsl/<name>.srt; the manifest describes the committed files (SHA-256); the render code types
no address and draws only palette colours; the frame review is someone else's. Stdlib only."""
import hashlib
import importlib.util
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRAND = os.path.join(ROOT, "brand")
VSL = os.path.join(BRAND, "vsl")
sys.path.insert(0, VSL)

from mp4info import info  # noqa: E402

VIDEOS = {"vsl-90s": (1920, 1080), "vsl-30s": (1920, 1080), "vsl-15s-vertical": (1080, 1920)}
FPS = 30


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read(path, mode="r"):
    with open(path, mode, **({} if "b" in mode else {"encoding": "utf-8"})) as f:
        return f.read()


class TestVslRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = load("vsl_build", os.path.join(VSL, "build.py"))
        cls.manifest = json.loads(read(os.path.join(VSL, "manifest.json")))
        cls.videos = {v["name"]: v for v in cls.build.beats()["videos"]}

    def test_files_have_the_size_rate_and_length_the_beats_set(self):
        for name, (w, h) in VIDEOS.items():
            path = os.path.join(BRAND, name + ".mp4")
            self.assertTrue(os.path.isfile(path), name)
            f = info(path)
            total = sum(b["ms"] for b in self.videos[name]["beats"])
            self.assertEqual((f["width"], f["height"]), (w, h), name)
            self.assertEqual(f["fps"], FPS, name)
            self.assertEqual(f["frames"], total * FPS // 1000, name)
            self.assertAlmostEqual(f["video_seconds"], total / 1000, delta=0.05)
            self.assertLessEqual(f["seconds"], self.videos[name]["max_ms"] / 1000 + 0.05)
            self.assertEqual(f["video_codec"], "avc1", name)
            self.assertEqual((f["audio_codec"], f["sample_rate"], f["channels"]), ("mp4a", 48000, 2), name)
            self.assertAlmostEqual(f["audio_seconds"], total / 1000, delta=0.1)
            self.assertTrue(f["faststart"], "%s: moov after mdat, a browser must download it all to play" % name)

    def test_manifest_describes_the_committed_files(self):
        self.assertEqual(self.manifest["beats_sha256"],
                         hashlib.sha256(read(os.path.join(VSL, "beats.json")).encode("utf-8")).hexdigest(),
                         "beats.json changed after the render: run brand/vsl/render.py")
        for name in VIDEOS:
            m = self.manifest["videos"][name]
            data = read(os.path.join(BRAND, name + ".mp4"), "rb")
            self.assertEqual(m["mp4_facts"]["sha256"], hashlib.sha256(data).hexdigest(), name)
            self.assertEqual([b["id"] for b in m["beats"]], [b["id"] for b in self.videos[name]["beats"]])
            for key in m["keyframes"]:
                self.assertTrue(os.path.isfile(os.path.join(BRAND, key["png"])), key)
            self.assertTrue(os.path.isfile(os.path.join(BRAND, m["contact_sheet"])))
            loud = m["audio"]["measured"]
            self.assertIsNotNone(loud["integrated_lufs"], name)
            self.assertLess(abs(loud["integrated_lufs"] - (-16)), 1.5, name)

    def test_burnt_in_captions_are_the_srt_cues_and_the_srt_sits_beside_the_video(self):
        for name in VIDEOS:
            cues = [" ".join(lines) for _, _, lines in self.build.cues(self.videos[name])]
            shown = self.manifest["videos"][name]["captions_burnt_in"]
            self.assertEqual([" ".join(c.split()) for c in shown], cues, name)
            self.assertEqual(read(os.path.join(BRAND, name + ".srt")), read(os.path.join(VSL, name + ".srt")), name)

    def test_render_code_types_no_address_and_uses_the_palette(self):
        src = read(os.path.join(VSL, "render.py"))
        hosts = [m.group(0) for m in re.finditer(r"[\w-]+\.(github\.io|com|dev|io|app|org|net|sh|co|ai)\b", src)]
        self.assertEqual([h for h in hosts if h != "w3.org"], [], "the SVG namespace is the only address allowed")
        self.assertIn('cfg["site_url"]', src)
        self.assertIn('"site", "config.json"', src)
        self.assertNotIn(chr(0x2014), src)
        self.assertNotIn(chr(0xA7), src)
        self.assertIsNone(re.search(r"#[0-9A-Fa-f]{6}\b", src), "colours come from contrast_check.PALETTE only")

    def test_voice_status_is_stated_not_implied(self):
        for name in VIDEOS:
            self.assertTrue(self.manifest["videos"][name]["audio"]["voice"].startswith("none"), name)

    def test_frame_review_is_independent_and_passed(self):
        path = os.path.join(VSL, "review.json")
        if not os.path.exists(path):
            self.skipTest("no independent review yet")
        r = json.loads(read(path))
        self.assertNotIn(r["reviewer"], ("", "fire", "builder"))
        self.assertEqual(sorted(r["videos"]), sorted(VIDEOS))
        for name in VIDEOS:
            self.assertEqual(r["videos"][name]["mp4_sha256"], self.manifest["videos"][name]["mp4_facts"]["sha256"],
                             "%s changed after the review" % name)


if __name__ == "__main__":
    unittest.main()
