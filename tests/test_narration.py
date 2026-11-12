"""Narration on the VSLs (task RB4d): brand/vsl/narration.py and brand/vsl/narrate_synth.py.

The spoken form of every cue, the sentence units, the placement rules and the speech detector are tested here on
their own. The site export (brand/vsl/vsl-90s-web.mp4 + poster) is tested against the file it was made from. The
files the voice step writes (brand/vsl/voice/, manifest.json "narration") are tested once they exist: until the
studio's voice venv has made the clips, those tests skip and say so, and the manifest still says "none" for the
voice (tests/test_vsl_render.py holds that side).
"""
import array
import importlib.util
import json
import math
import os
import re
import shutil
import sys
import tempfile
import unittest
import wave

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


def tone_wav(path, lead_ms, tone_ms, tail_ms, sr=24000):
    """Silence, a 220 Hz tone at about -12 dBFS, silence: a stand-in clip with known speech bounds."""
    data = array.array("h")
    data.extend([0] * int(sr * lead_ms / 1000))
    for i in range(int(sr * tone_ms / 1000)):
        data.append(int(8000 * math.sin(2 * math.pi * 220 * i / sr)))
    data.extend([0] * int(sr * tail_ms / 1000))
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data.tobytes())


def srt_blocks(name):
    with open(os.path.join(VSL, name + ".srt"), encoding="utf-8") as f:
        return [" ".join(b.split("\n")[2:]) for b in f.read().strip().split("\n\n") if b]


class TestSpokenForm(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(N.number("12"), "twelve")
        self.assertEqual(N.number("66"), "sixty-six")
        self.assertEqual(N.number("110"), "one hundred and ten")
        self.assertEqual(N.number("20000"), "twenty thousand")

    def test_names_a_voice_cannot_read_as_written(self):
        self.assertEqual(N.spoken("rewindagents install adds the hook."), "Rewind agents install adds the hook.")
        self.assertEqual(N.spoken("Apache-2.0, standard library only. Not on PyPI yet."),
                         "Apache two point oh, standard library only. Not on pie-P-I yet.")
        self.assertEqual(N.spoken("Export it as one HTML page."), "Export it as one H-T-M-L page.")

    def test_every_unit_is_speakable(self):
        jobs = N.cue_jobs()
        self.assertEqual(len(jobs), 22 + 8 + 5)   # 23 + 8 + 5 srt cues; 90s cues 16+17 are one sentence
        for name, n, start, end, caption, said in jobs:
            self.assertFalse(re.search(r"\d|rewindagents|PyPI|HTML|[{}]", said), (name, n, said))
            self.assertRegex(said, r"[.?!]$", "a clip ends on a sentence end")
            self.assertTrue(said[:1].isupper(), (name, n, said))

    def test_only_the_written_forms_change(self):
        """Take out every replaced span: what is left is word for word the caption."""
        for name, n, start, end, caption, said in N.cue_jobs():
            plain = caption
            for pattern, _ in N.SPOKEN:
                plain = re.sub(pattern, "#", plain)
            for w in [w for w in re.split(r"[#\s]+", plain) if w]:
                self.assertIn(w.lower(), said.lower(), (name, n))

    def test_units_are_the_srt_cues_joined_at_sentence_ends(self):
        videos = {v["name"]: v for v in N.vsl.beats()["videos"]}
        for name in VIDEOS:
            blocks = srt_blocks(name)
            units = N.units(videos[name])
            self.assertEqual([i for u in units for i in u[3]], list(range(1, len(blocks) + 1)), name)
            for start, end, caption, nums in units:
                self.assertEqual(caption, " ".join(blocks[i - 1] for i in nums), name)
        self.assertEqual([u[3] for u in N.units(videos["vsl-90s"]) if len(u[3]) > 1], [[16, 17]])


class TestPlacement(unittest.TestCase):
    VIDEO = {"beats": [{"ms": 3000}, {"ms": 4000}]}
    SPANS = [(0, 3000, "a", [1]), (3000, 7000, "b", [2])]

    def test_a_unit_starts_at_its_own_time(self):
        p = N.place(self.VIDEO, self.SPANS, {1: (0, 2000), 2: (0, 2500)})
        self.assertEqual([x["at_ms"] for x in p], [N.LEAD_MS, 3000 + N.LEAD_MS])
        self.assertEqual([x["tempo"] for x in p], [1.0, 1.0])
        self.assertEqual([x["overrun_ms"] for x in p], [0, 0])

    def test_a_late_unit_waits_for_the_one_before(self):
        p = N.place(self.VIDEO, self.SPANS, {1: (0, 3300), 2: (0, 1000)})
        self.assertGreaterEqual(p[1]["at_ms"], p[0]["speech_end_ms"] + N.GAP_MS)

    def test_speed_up_is_capped_and_an_overrun_is_reported(self):
        p = N.place(self.VIDEO, self.SPANS, {1: (0, 9000), 2: (0, 1000)})
        self.assertLessEqual(p[0]["tempo"], N.MAX_TEMPO + 0.01)
        self.assertGreater(p[0]["overrun_ms"], 0)
        self.assertEqual(p[0]["overrun_ms"], p[0]["speech_end_ms"] - 3000)

    def test_speech_bounds_on_a_known_clip(self):
        d = tempfile.mkdtemp()
        try:
            path = os.path.join(d, "c.wav")
            tone_wav(path, 300, 1200, 400)
            data, sr = N.read_wav(path)
            a, b = N.speech_bounds(data, sr)
            self.assertAlmostEqual(a, 300, delta=10)
            self.assertAlmostEqual(b, 1500, delta=10)
        finally:
            shutil.rmtree(d)

    def test_masters(self):
        # 16:9 keeps the accepted render's level (render.py LOUDNESS), 9:16 the Shorts/Reels target
        with open(os.path.join(VSL, "render.py"), encoding="utf-8") as f:
            render_src = f.read()
        self.assertIn('LOUDNESS = "loudnorm=I=%d:' % N.MASTER["16:9"], render_src)
        self.assertEqual(N.MASTER["9:16"], -11.5)
        self.assertLess(N.TRUE_PEAK - 0.5, N.TRUE_PEAK)


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not on PATH")
class TestMixOnASyntheticClip(unittest.TestCase):
    def test_voice_stem_places_the_clip(self):
        d = tempfile.mkdtemp()
        old = N.VOICE_DIR
        try:
            N.VOICE_DIR = d
            os.makedirs(os.path.join(d, "x"))
            tone_wav(os.path.join(d, "x", "01.wav"), 250, 800, 250)
            stem = N.voice_stem("x", [{"cue": 1, "at_ms": 1000, "tempo": 1.0}], 3000, d)
            data = N.decode(stem)
            a, b = N.speech_bounds(data, N.SR)
            self.assertAlmostEqual(a, 1000, delta=20)
            self.assertAlmostEqual(b, 1800, delta=30)
            self.assertAlmostEqual(len(data) / N.SR, 3.0, delta=0.02)
        finally:
            N.VOICE_DIR = old
            shutil.rmtree(d)


class TestSiteExport(unittest.TestCase):
    """brand/vsl/vsl-90s-web.mp4 and its poster, for the site (RB4d note)."""

    @classmethod
    def setUpClass(cls):
        cls.w = manifest().get("web")

    def setUp(self):
        if not self.w:
            self.skipTest("no site export yet: python3 brand/vsl/narration.py web")

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

    def test_voice_flag_matches_the_narration(self):
        self.assertEqual(self.w["voice"], bool(manifest().get("narration", {}).get("videos", {}).get("vsl-90s")))

    def test_poster_is_a_real_frame_not_black(self):
        path = os.path.join(BRAND, self.w["poster"])
        self.assertEqual(N.sha256(path), self.w["poster_sha256"])
        with open(path, "rb") as f:
            self.assertEqual(f.read(3), b"\xff\xd8\xff")
        self.assertGreater(self.w["poster_mean_luma"], 60)
        videos = {v["name"]: v for v in N.vsl.beats()["videos"]}
        a, b = N.beat_start(videos["vsl-90s"], self.w["poster_beat"])
        self.assertTrue(a <= self.w["poster_ms"] < b)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not on PATH")
    def test_streams_are_copies_of_the_source(self):
        src = os.path.join(BRAND, "vsl-90s.mp4")
        out = os.path.join(BRAND, self.w["mp4"])
        if self.w["from"].startswith("stream copy"):
            self.assertEqual(N.stream_md5(out, "v"), N.stream_md5(src, "v"))
        self.assertEqual(N.stream_md5(out, "a"), N.stream_md5(src, "a"))


class TestNarratedFiles(unittest.TestCase):
    """Runs once brand/vsl/narration.py mix has written the manifest's "narration" block."""

    @classmethod
    def setUpClass(cls):
        cls.n = manifest().get("narration")

    def setUp(self):
        if not self.n:
            self.skipTest("no narration yet: the voice clips are made in the studio's voice venv (RB4d)")

    def test_every_unit_is_spoken_inside_its_beat(self):
        jobs = {(j[0], j[1]): j for j in N.cue_jobs()}
        for name, v in self.n["videos"].items():
            self.assertEqual(len(v["cues"]), len([k for k in jobs if k[0] == name]), name)
            for c in v["cues"]:
                self.assertGreaterEqual(c["at_ms"], c["cue_start_ms"], (name, c["cue"]))
                self.assertLess(c["at_ms"], c["cue_end_ms"], (name, c["cue"]))
                self.assertLessEqual(c["overrun_ms"], 250, (name, c["cue"]))
                self.assertLessEqual(c["tempo"], N.MAX_TEMPO + 0.01)
                self.assertEqual(c["spoken"], jobs[(name, c["cue"])][5])

    def test_the_voice_is_in_the_mp4(self):
        for name, v in self.n["videos"].items():
            mp4 = os.path.join(BRAND, name + ".mp4")
            self.assertEqual(N.sha256(mp4), v["mp4_sha256"], name)
            for c in v["cues"]:
                self.assertGreaterEqual(c["final_minus_bed_db"], 6.0, (name, c["cue"]))

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not on PATH")
    def test_picture_is_the_accepted_one(self):
        for name, v in self.n["videos"].items():
            self.assertEqual(N.video_md5(os.path.join(BRAND, name + ".mp4")), v["video_md5"], name)

    def test_clips_are_the_reported_takes(self):
        with open(os.path.join(VSL, "voice", "report.json"), encoding="utf-8") as f:
            report = json.load(f)
        for name, v in self.n["videos"].items():
            for c in v["cues"]:
                r = report["clips"]["%s/%02d" % (name, c["cue"])]
                self.assertEqual(r["wav_sha256"], c["wav_sha256"])
                self.assertEqual(r["spoken"], c["spoken"])
                for s in r["sentences"]:
                    self.assertLessEqual(s["wer"], 0.12, (name, c["cue"], s["heard"]))

    def test_levels(self):
        for name, v in self.n["videos"].items():
            self.assertLessEqual(v["measured"]["true_peak_dbfs"], N.TRUE_PEAK, name)
            self.assertLess(abs(v["measured"]["integrated_lufs"] - v["master"]["integrated_lufs_target"]), 1.5)
            self.assertTrue(17 <= v["voice_over_music_rms_db_while_talking"] <= 21, name)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not on PATH")
    def test_reels_cut_has_no_voice(self):
        r = self.n["reels"]
        out = os.path.join(BRAND, r["mp4"])
        self.assertEqual(N.sha256(out), r["sha256"])
        bed = os.path.join(BRAND, self.n["videos"]["vsl-15s-vertical"]["music_bed"])
        self.assertEqual(N.stream_md5(out, "a"), N.stream_md5(bed, "a"))


if __name__ == "__main__":
    unittest.main()
