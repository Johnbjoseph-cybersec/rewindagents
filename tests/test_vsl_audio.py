"""brand/vsl/audio (review-textcut-r2.json fix 4): the films' music beds and SFX are rebuilt from the repository, not
committed. The generator (make_bed.py + sound_dsp.py), its pinned requirements, its licence note, AUDIO.md and
sections.json are in the repo; the WAVs are git-ignored; brand/vsl/render.py rebuilds them when missing; and the
generator is deterministic, so regenerating gives exactly the bytes the manifest pins (manifest.videos.*.audio.files).

The regeneration test needs a Python with brand/vsl/audio/requirements.txt (numpy, scipy, pyloudnorm, soundfile):
$REWINDAGENTS_BED_PYTHON, this interpreter, or the Creative Studio venv render.py also looks for. Without one it is
skipped and says so. Stdlib otherwise."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VSL = os.path.join(ROOT, "brand", "vsl")
AUDIO = os.path.join(VSL, "audio")
BED_FILES = ("bed-vsl-90s.wav", "bed-vsl-30s.wav", "bed-vsl-15s-vertical.wav", "sfx-rewind.wav", "sfx-tick.wav")


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def pinned():
    """{file name: sha256} for every audio file a film's manifest entry pins."""
    with open(os.path.join(VSL, "manifest.json"), encoding="utf-8") as f:
        m = json.load(f)
    out = {}
    for name, v in m["videos"].items():
        files = v["audio"]["files"]
        if not files:
            raise AssertionError("%s was mixed from the synth fallback: no studio audio files pinned" % name)
        for rel, h in files.items():
            self_name = os.path.basename(rel)
            if self_name in out:
                assert out[self_name] == h, "two films pin different bytes for %s" % self_name
            out[self_name] = h
    return out


def bed_python():
    cands = [os.environ.get("REWINDAGENTS_BED_PYTHON"), sys.executable,
             os.path.expanduser("~/ai-creative-studio/.venv-voice/bin/python")]
    for c in cands:
        if c and os.path.isfile(c) and subprocess.run(
                [c, "-c", "import numpy, scipy, pyloudnorm, soundfile"], capture_output=True).returncode == 0:
            return c
    return None


class TestVslAudio(unittest.TestCase):
    def test_sources_are_in_the_repo_and_the_wavs_are_ignored(self):
        for f in ("make_bed.py", "sound_dsp.py", "requirements.txt", "LICENSES.md", "AUDIO.md", "sections.json"):
            self.assertTrue(os.path.isfile(os.path.join(AUDIO, f)), f)
        with open(os.path.join(ROOT, ".gitignore"), encoding="utf-8") as f:
            self.assertIn("brand/vsl/audio/*.wav", f.read().split("\n"))
        with open(os.path.join(AUDIO, "make_bed.py"), encoding="utf-8") as f:
            head = f.read(3000)
        self.assertIn("licence `original`", head)
        with open(os.path.join(AUDIO, "requirements.txt"), encoding="utf-8") as f:
            reqs = [ln for ln in f.read().split("\n") if ln and not ln.startswith("#")]
        self.assertEqual(sorted(r.split("==")[0] for r in reqs), ["numpy", "pyloudnorm", "scipy", "soundfile"])
        self.assertTrue(all("==" in r for r in reqs), reqs)

    def test_the_manifest_pins_every_bed_and_sfx(self):
        self.assertEqual(set(pinned()), set(BED_FILES))

    def test_render_rebuilds_missing_beds(self):
        with open(os.path.join(VSL, "render.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn("def ensure_beds():", src)
        self.assertIn('"make_bed.py"', src)
        main = src[src.index("def main(argv):"):]
        self.assertLess(main.index("ensure_beds()"), main.index("render_video("))

    def test_files_on_disk_are_the_pinned_bytes(self):
        on_disk = [f for f in BED_FILES if os.path.isfile(os.path.join(AUDIO, f))]
        if not on_disk:
            self.skipTest("no WAVs on disk (a fresh clone): test_regenerating_gives_the_pinned_bytes covers it")
        pins = pinned()
        for f in on_disk:
            self.assertEqual(sha256(os.path.join(AUDIO, f)), pins[f], f)

    def test_regenerating_gives_the_pinned_bytes(self):
        py = bed_python()
        if not py:
            self.skipTest("no Python with brand/vsl/audio/requirements.txt (set REWINDAGENTS_BED_PYTHON)")
        pins = pinned()
        with tempfile.TemporaryDirectory() as d:
            subprocess.run([py, os.path.join(AUDIO, "make_bed.py"), "--beats", os.path.join(VSL, "beats.json"),
                            "--out", d], check=True, capture_output=True, cwd=d)
            for f in BED_FILES:
                self.assertEqual(sha256(os.path.join(d, f)), pins[f], "%s regenerated differs from the manifest" % f)
            with open(os.path.join(d, "sections.json"), "rb") as a, open(os.path.join(AUDIO, "sections.json"), "rb") as b:
                self.assertEqual(a.read(), b.read(), "sections.json regenerated differs from the committed one")


if __name__ == "__main__":
    unittest.main()
