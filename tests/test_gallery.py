"""brand/launch/ph-1.png .. ph-5.png (RB5b): the Product Hunt gallery producthunt.md lists. Each PNG's size and
colours are read from the file (brand/logo/pngsample.py, stdlib) and its SHA-256 matches gallery.json; every
terminal line is a line the recorded demo session printed (brand/demo/manifest.json, which tests/test_demo.py
replays against the real CLI), whole and in order; every command is a demo or README command; the headlines are
the session's own comments or producthunt.md's words; Rewind marks one block per image and it is the block the
gallery list names; the build code types no colour and no address; the image review is someone else's and pinned
to the PNGs it looked at. Stdlib only."""
import hashlib
import importlib.util
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRAND = os.path.join(ROOT, "brand")
LAUNCH = os.path.join(BRAND, "launch")
sys.path.insert(0, os.path.join(BRAND, "logo"))

from pngsample import load_png, pixel  # noqa: E402
from contrast_check import PALETTE  # noqa: E402


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


vsl = load("gallery_vsl_helpers", os.path.join(ROOT, "tests", "test_vsl.py"))
launch = load("gallery_launch_helpers", os.path.join(ROOT, "tests", "test_launch.py"))


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


def text_of(row):
    return "".join(t for t, _ in row)


def gallery_items():
    body = read(LAUNCH, "producthunt.md").split("## Gallery", 1)[1].split("\n## ", 1)[0]
    return {int(n): t.strip() for n, t in re.findall(r"^(\d)\. (.+)$", body, re.M)}


def readme_lines():
    """{command: comment} for every line of every ```sh block in README.md."""
    out = {}
    for block in re.findall(r"```sh\n(.*?)```", read(ROOT, "README.md"), re.S):
        for line in block.split("\n"):
            m = re.match(r"^(.*?)(\s+#\s*(.*))?$", line)
            if m.group(1).strip():
                out[m.group(1).strip()] = (m.group(3) or "").strip()
    return out


class TestGallery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = json.loads(read(LAUNCH, "gallery.json"))
        cls.demo = json.loads(read(BRAND, "demo", "manifest.json"))
        cls.shots = {s["file"]: s for s in cls.g["shots"]}

    def test_five_images_at_product_hunts_size_and_the_files_are_the_ones_built(self):
        self.assertEqual([s["file"] for s in self.g["shots"]], ["ph-%d.png" % i for i in range(1, 6)])
        self.assertEqual((self.g["width"], self.g["height"]), launch.PH_GALLERY)
        for s in self.g["shots"]:
            path = os.path.join(LAUNCH, s["file"])
            w, h, _, _ = load_png(path, rows_needed=1)
            self.assertEqual((w, h), launch.PH_GALLERY, s["file"])
            with open(path, "rb") as f:
                self.assertEqual(hashlib.sha256(f.read()).hexdigest(), s["sha256"],
                                 "%s is not the file gallery.py built" % s["file"])

    def test_each_image_is_the_shot_producthunt_md_lists(self):
        items = gallery_items()
        self.assertEqual(sorted(items), [1, 2, 3, 4, 5])
        for n in range(1, 6):
            self.assertEqual(self.shots["ph-%d.png" % n]["item"], items[n])

    def test_built_from_the_recorded_session_as_it_is_now(self):
        self.assertEqual(self.g["demo_beats_sha256"],
                         hashlib.sha256(json.dumps(self.demo["beats"], sort_keys=True).encode("utf-8")).hexdigest(),
                         "brand/demo/manifest.json changed after the gallery was built: run brand/launch/gallery.py")

    def test_terminal_shots_show_a_whole_beat_of_the_session(self):
        want = {"ph-2.png": "rewindagent replay", "ph-3.png": "git status --short", "ph-4.png": "rewindagent rewind 12"}
        for name, cmd in want.items():
            s = self.shots[name]
            beat = self.demo["beats"][s["beat"]]
            self.assertEqual(beat["command"], cmd, name)
            rows = s["panels"][0]["rows"]
            self.assertEqual(rows[0], [["$ ", "Playhead"], [cmd, "Leader"]], name)
            self.assertEqual([text_of(r) for r in rows[1:]], beat["output"].rstrip("\n").split("\n"),
                             "%s must show everything the command printed, nothing cut or added" % name)
            caption = beat["caption"][2:]
            caption = caption[0].upper() + caption[1:]
            self.assertTrue(caption.startswith(s["headline"]), "%s: the headline is the start of the beat's comment"
                            % name)
            self.assertGreaterEqual(len(s["headline"].split()), 5, name)
        mono = {s["mono_px"] for s in self.g["shots"] if "mono_px" in s}
        self.assertEqual(len(mono), 1, "one terminal size across the set (review round 1)")
        # the wreck is the git status right after the session, not the one after the rewind
        self.assertLess(self.shots["ph-3.png"]["beat"], self.shots["ph-4.png"]["beat"])

    def test_rewind_marks_the_block_the_gallery_list_names(self):
        def accented(name):
            return [text_of(r) for r in self.shots[name]["panels"][0]["rows"] if r[0][1] == "Rewind"]

        self.assertEqual([re.split(r"\s+", t.strip())[0] for t in accented("ph-2.png")], ["13", "14"])
        self.assertEqual(accented("ph-3.png"), [" D tests/test_config.py", " D tests/test_server.py"])
        restored = accented("ph-4.png")
        self.assertEqual(len(restored), 4)
        self.assertTrue(all(t.startswith("  restore  ") for t in restored), restored)
        for name in ("ph-1.png", "ph-5.png"):
            for p in self.shots[name].get("panels", []):
                self.assertFalse([r for r in p["rows"] if any(c == "Rewind" for _, c in r)], name)

    def test_one_accent_block_per_image(self):
        for s in self.g["shots"]:
            for p in s.get("panels", []):
                flags = [any(c == "Rewind" for _, c in r) for r in p["rows"]]
                runs = sum(1 for i, f in enumerate(flags) if f and (i == 0 or not flags[i - 1]))
                self.assertLessEqual(runs, 1, s["file"])
                for r in p["rows"]:
                    for _, c in r:
                        self.assertIn(c, ("Leader", "Playhead", "Rewind"), s["file"])

    def test_install_shot_is_readme_lines(self):
        s = self.shots["ph-5.png"]
        sh = readme_lines()
        cmds = []
        for p in s["panels"]:
            self.assertIn(p["label"].lower(), s["item"].lower())
            for r in p["rows"]:
                self.assertEqual(r[0], ["$ ", "Playhead"])
                cmd = r[1][0]
                self.assertIn(cmd, sh)
                if len(r) > 2:
                    self.assertEqual(r[2][0], "  # " + sh[cmd], "the comment is the README's")
                cmds.append(cmd)
        self.assertEqual(len(cmds), 2)
        self.assertTrue(cmds[0].startswith("pipx install git+"))
        self.assertEqual(cmds[1], "rewindagent install")
        self.assertEqual(s["headline"], s["item"].split(":")[0])
        readme = " ".join(read(ROOT, "README.md").split())
        for note in s["notes"]:
            self.assertIn(note, readme)

    def test_title_shot_is_the_promise(self):
        s = self.shots["ph-1.png"]
        self.assertEqual(s["promise"], vsl.load_build().PROMISE)
        self.assertIn(s["promise"], read(BRAND, "BRAND.md"))

    def test_pixels_are_palette_colours(self):
        for s in self.g["shots"]:
            self.assertTrue(s["samples"], s["file"])
            for x, y, name in s["samples"]:
                self.assertEqual(pixel(os.path.join(LAUNCH, s["file"]), x, y), PALETTE[name].upper(),
                                 "%s at %d,%d should be %s" % (s["file"], x, y, name))

    def test_no_words_brand_md_never_uses(self):
        words = []
        for s in self.g["shots"]:
            words += [s.get("headline", ""), s.get("promise", "")] + s.get("notes", [])
            for p in s.get("panels", []):
                words += [p["label"] or ""] + [text_of(r) for r in p["rows"]]
        text = " ".join(words).lower()
        for w in vsl.NEVER:
            self.assertIsNone(re.search(r"\b%s\b" % re.escape(w), text), w)
        self.assertIsNone(vsl.EMOJI.search(text))

    def test_build_code_types_no_colour_and_no_address(self):
        src = read(LAUNCH, "gallery.py")
        self.assertIsNone(re.search(r"#[0-9A-Fa-f]{6}\b", src), "colours come from contrast_check.PALETTE only")
        self.assertEqual(vsl.hosts(src), [])
        self.assertNotIn(chr(0xA7), src)

    def test_image_review_is_independent_and_pinned(self):
        path = os.path.join(LAUNCH, "review.json")
        if not os.path.exists(path):
            self.skipTest("no independent review yet")
        r = json.loads(read(path))
        self.assertNotIn(r["reviewer"], ("", "fire", "builder"))
        self.assertEqual(sorted(r["images"]), sorted(self.shots))
        for name, row in r["images"].items():
            self.assertEqual(row["png_sha256"], self.shots[name]["sha256"], "%s changed after the review" % name)


if __name__ == "__main__":
    unittest.main()
