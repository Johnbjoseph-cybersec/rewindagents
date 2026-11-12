"""No narration on the VSLs, and the site's copy of the film (brand/vsl/narration.py, remade 2026-11-12).

John, 2026-11-12: "remove the voice over altogether, explain through text". The films carry the cards and the music
bed only, so nothing that makes or ships a voice may remain: no brand/vsl/voice/ directory, no narrate_synth.py or
narrate_female.py, no "narration" block in brand/vsl/manifest.json, no mix step in narration.py. What narration.py
still does is the web export, tested here against the file it was made from: brand/vsl/vsl-90s-web.mp4 is a stream
copy of brand/vsl-90s.mp4 (picture re-encoded only when the source is over WEB_MAX_BYTES; sound always copied) with
faststart, at most WEB_MAX_BYTES, voice false; the poster is a real frame from the
last moment of b14, "One command, and four files come back.". Stdlib only, plus ffmpeg where it is on PATH.
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRAND = os.path.join(ROOT, "brand")
VSL = os.path.join(BRAND, "vsl")
sys.path.insert(0, VSL)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


N = load("vsl_narration", os.path.join(VSL, "narration.py"))
VIDEOS = ("vsl-90s", "vsl-30s", "vsl-15s-vertical")


def manifest():
    with open(os.path.join(VSL, "manifest.json"), encoding="utf-8") as f:
        return json.load(f)


def stream_md5(mp4, stream):
    p = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", mp4, "-map", "0:%s" % stream,
                        "-c", "copy", "-f", "md5", "-"], capture_output=True, text=True, check=True)
    return p.stdout.strip().split("=", 1)[1]


class TestNoVoice(unittest.TestCase):
    def test_nothing_that_makes_or_ships_a_voice_remains(self):
        for rel in ("voice", "narrate_synth.py", "narrate_female.py"):
            self.assertFalse(os.path.exists(os.path.join(VSL, rel)), "brand/vsl/%s must not ship" % rel)
        self.assertFalse(os.path.exists(os.path.join(BRAND, "vsl-15s-vertical-reels.mp4")),
                         "the Reels cut of the old voice mix is gone: the vertical itself has no voice")
        self.assertNotIn("narration", manifest())

    def test_narration_py_is_the_web_export_only(self):
        with open(os.path.join(VSL, "narration.py"), encoding="utf-8") as f:
            src = f.read()
        for word in ("def mix", "VOICE_LOCK", "Kokoro", "narrate_synth", "loudnorm", "amix", "sidechain"):
            self.assertNotIn(word, src, "narration.py still carries the voice step: %r" % word)
        self.assertEqual(N.POSTER_BEAT, "b14")
        self.assertEqual(N.WEB_MAX_BYTES, 12 * 1024 * 1024)

    def test_no_card_has_a_voice_field(self):
        for v in N.vsl.beats()["videos"]:
            for b in v["beats"]:
                self.assertNotIn("voice", b, "%s %s" % (v["name"], b["id"]))

    def test_poster_beat_is_the_restore(self):
        video = next(v for v in N.vsl.beats()["videos"] if v["name"] == N.WEB_NAME)
        b = next(x for x in video["beats"] if x["id"] == N.POSTER_BEAT)
        self.assertEqual(b["text"], "One command, and four files come back.")
        self.assertTrue(any(re.match(r"^\s*restore\s", s) for s in b["screen"]))


class TestSiteExport(unittest.TestCase):
    """brand/vsl/vsl-90s-web.mp4 and its poster, for the site."""

    @classmethod
    def setUpClass(cls):
        cls.w = manifest().get("web")

    def setUp(self):
        if not self.w:
            self.fail("no site export: python3 brand/vsl/narration.py web")

    def test_the_export_is_the_committed_file_and_fits(self):
        from mp4info import info
        path = os.path.join(BRAND, self.w["mp4"])
        self.assertEqual(N.sha256(path), self.w["sha256"])
        self.assertLessEqual(os.path.getsize(path), N.WEB_MAX_BYTES)
        f = info(path)
        self.assertEqual((f["width"], f["height"], f["video_codec"]), (1920, 1080, "avc1"))
        self.assertTrue(f["faststart"])

    def test_the_export_is_the_current_90s_video(self):
        self.assertEqual(N.sha256(os.path.join(BRAND, "vsl-90s.mp4")), self.w["source_sha256"],
                         "brand/vsl-90s.mp4 changed after the export: run brand/vsl/narration.py web")

    def test_the_export_has_no_voice(self):
        self.assertIs(self.w["voice"], False)

    def test_poster_is_a_real_frame_from_the_restore(self):
        path = os.path.join(BRAND, self.w["poster"])
        self.assertEqual(N.sha256(path), self.w["poster_sha256"])
        with open(path, "rb") as f:
            self.assertEqual(f.read(3), b"\xff\xd8\xff")
        self.assertGreater(self.w["poster_mean_luma"], 60)
        self.assertEqual(self.w["poster_beat"], "b14")
        videos = {v["name"]: v for v in N.vsl.beats()["videos"]}
        a, b = N.beat_start(videos["vsl-90s"], self.w["poster_beat"])
        self.assertTrue(a <= self.w["poster_ms"] < b)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg not on PATH")
    def test_streams_are_copies_of_the_source_and_the_bed_is_the_only_audio(self):
        src = os.path.join(BRAND, "vsl-90s.mp4")
        out = os.path.join(BRAND, self.w["mp4"])
        # the picture is copied when the source fits WEB_MAX_BYTES, else re-encoded; the sound is always copied
        if os.path.getsize(src) <= N.WEB_MAX_BYTES:
            self.assertTrue(self.w["from"].startswith("stream copy"), self.w["from"])
            self.assertEqual(stream_md5(out, "v"), stream_md5(src, "v"))
        else:
            self.assertTrue(self.w["from"].startswith("re-encoded"), self.w["from"])
        self.assertEqual(stream_md5(out, "a"), stream_md5(src, "a"))
        self.assertEqual(stream_md5(out, "a"), manifest()["videos"]["vsl-90s"]["audio"]["audio_stream_md5"])
        kinds = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", out],
                               capture_output=True, text=True, check=True).stdout.split()
        self.assertEqual(sorted(kinds), ["audio", "video"], kinds)


if __name__ == "__main__":
    unittest.main()
