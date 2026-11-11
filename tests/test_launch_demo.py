"""brand/launch-demo.mp4 (RB4c): the demo session as a screen recording. It is the SAME session as demo.gif: the
manifest carries the fingerprint of brand/demo/manifest.json's beats, which tests/test_demo.py replays against the
real CLI byte for byte, and its terminal time is the GIF storyboard's. Size, rate, length and tracks are read from
the file itself (brand/vsl/mp4info.py, stdlib); the captions burnt in are the beats' comments, and the .srt beside
the video says the same words at the same times; the build code types no address and no colour. Stdlib only."""
import hashlib
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRAND = os.path.join(ROOT, "brand")
DEMO = os.path.join(BRAND, "demo")
sys.path.insert(0, os.path.join(BRAND, "vsl"))

from mp4info import info  # noqa: E402

MP4 = os.path.join(BRAND, "launch-demo.mp4")
SRT = os.path.join(BRAND, "launch-demo.srt")


def read(path, mode="r"):
    with open(path, mode, **({} if "b" in mode else {"encoding": "utf-8"})) as f:
        return f.read()


def srt_cues(text):
    out = []
    for block in text.strip().split("\n\n"):
        rows = block.split("\n")
        a, b = rows[1].split(" --> ")
        ms = [((int(t[0:2]) * 60 + int(t[3:5])) * 60 + int(t[6:8])) * 1000 + int(t[9:12]) for t in (a, b)]
        out.append((ms[0], ms[1], rows[2:]))
    return out


class TestLaunchDemo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = json.loads(read(os.path.join(DEMO, "launch-manifest.json")))
        cls.gif = json.loads(read(os.path.join(DEMO, "manifest.json")))

    def test_it_is_the_session_the_gif_shows(self):
        beats = self.gif["beats"]
        self.assertEqual(self.m["demo_beats_sha256"],
                         hashlib.sha256(json.dumps(beats, sort_keys=True).encode("utf-8")).hexdigest(),
                         "brand/demo/manifest.json changed after the mp4 was built: run brand/demo/launch_mp4.py")
        self.assertEqual(self.m["commands"], [b["command"] for b in beats])
        self.assertEqual((self.m["session"], self.m["version"]), (self.gif["session"], self.gif["version"]))
        self.assertEqual(self.m["terminal_seconds"], self.gif["storyboard_seconds"])

    def test_file_has_the_size_rate_and_length_the_manifest_says(self):
        f = info(MP4)
        self.assertEqual((f["width"], f["height"]), (1920, 1080))
        self.assertEqual(f["fps"], self.m["fps"])
        self.assertEqual(f["frames"], self.m["frames"])
        total = self.m["terminal_seconds"] + self.m["end_card_seconds"]
        self.assertEqual(self.m["frames"], round(total * self.m["fps"]))
        self.assertAlmostEqual(f["video_seconds"], total, delta=0.05)
        self.assertLessEqual(self.m["terminal_seconds"], 20.0, "the session part keeps the demo GIF's 20 s limit")
        self.assertEqual(f["video_codec"], "avc1")
        self.assertTrue(f["faststart"], "moov after mdat: a browser must download it all to play")
        self.assertEqual(self.m["mp4_facts"]["sha256"], hashlib.sha256(read(MP4, "rb")).hexdigest(),
                         "the manifest describes an earlier build")

    def test_no_sound_and_it_says_so(self):
        self.assertNotIn("audio_codec", info(MP4), "a screen recording with a sound track the manifest denies")
        self.assertTrue(self.m["audio"].startswith("none"))

    def test_captions_are_the_beat_comments_and_the_srt_matches(self):
        want = [b["caption"][2:] for b in self.gif["beats"]]
        self.assertTrue(all(b["caption"].startswith("# ") for b in self.gif["beats"]))
        self.assertEqual(self.m["captions_burnt_in"], want)
        cues = srt_cues(read(SRT))
        self.assertEqual([" ".join(lines) for _, _, lines in cues], want)
        self.assertEqual([[c["start_ms"], c["end_ms"], c["lines"]] for c in self.m["cues"]],
                         [[s, e, lines] for s, e, lines in cues])
        for (s, e, lines), (s2, _, _) in zip(cues, cues[1:] + [(None, None, None)]):
            self.assertGreaterEqual(e - s, 1200, lines)
            if s2 is not None:
                self.assertEqual(e, s2, "a gap or overlap between cues")
        self.assertLessEqual(cues[-1][1], round(self.m["terminal_seconds"] * 1000))

    def test_key_frames_and_sheet_exist(self):
        self.assertEqual(len(self.m["keyframes"]), len(self.gif["beats"]) + 1)
        for k in self.m["keyframes"] + [self.m["contact_sheet"]]:
            self.assertTrue(os.path.isfile(os.path.join(BRAND, k)), k)

    def test_build_code_types_no_address_and_no_colour(self):
        src = read(os.path.join(DEMO, "launch_mp4.py"))
        hosts = [m.group(0) for m in re.finditer(r"[\w-]+\.(github\.io|com|dev|io|app|org|net|sh|co|ai)\b", src)]
        self.assertEqual(hosts, [])
        self.assertIn('"site", "config.json"', src)
        self.assertIsNone(re.search(r"#[0-9A-Fa-f]{6}\b", src), "colours come from contrast_check.PALETTE only")
        self.assertNotIn(chr(0x2014), src)
        self.assertNotIn(chr(0xA7), src)
        for path in (SRT, os.path.join(DEMO, "launch-manifest.json")):
            self.assertNotIn("github.io", read(path), path)


if __name__ == "__main__":
    unittest.main()
