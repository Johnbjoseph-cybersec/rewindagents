"""Demo GIF (RB2b): the file is a looping GIF of the stated size under 20 s, and every command and every
line of output it shows is what the CLI and git print today for the same session. Stdlib only; the fonts
and the renderer are not needed. With REWINDAGENT_BIN set (.fire-test-cmd sets it) the rewind the clip
shows is also run through the installed binary, undo hint included."""
import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRAND = os.path.join(ROOT, "brand")
DEMO = os.path.join(BRAND, "demo")
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, BRAND)
sys.path.insert(0, DEMO)

import rewindagent  # noqa: E402
from rewindagent import cli  # noqa: E402
from contrast_check import PALETTE  # noqa: E402
from gifinfo import info  # noqa: E402
import scenario  # noqa: E402

LIMIT = 20.0   # BRAND_KIT.md: demo.gif, real product, <= 20 s
GIF = os.path.join(BRAND, "demo.gif")


def manifest():
    with open(os.path.join(DEMO, "manifest.json"), encoding="utf-8") as f:
        return json.load(f)


def lines(text):
    return text.rstrip("\n").split("\n") if text.strip() else []


class TestDemoGif(unittest.TestCase):
    def test_gif_is_real_and_under_the_limit(self):
        facts = info(GIF)
        colors = set(facts.pop("colors"))
        m = manifest()
        self.assertEqual((facts["width"], facts["height"]), (1200, 675))
        self.assertEqual(facts["loops"], 0, "should loop forever")
        self.assertGreater(facts["frames"], 40)
        self.assertLessEqual(facts["seconds"], LIMIT)
        self.assertGreater(facts["seconds"], 10.0, "a demo this short would be a flicker")
        grid = round(m["grid_seconds"] * 100)
        for d in facts["delays_cs"]:
            self.assertEqual(d % grid, 0, "delay %d cs is off the %d cs grid" % (d, grid))
        self.assertGreaterEqual(max(facts["delays_cs"]), 200, "no hold of two seconds or more")
        # the manifest describes this file, not an earlier build
        self.assertEqual(facts, {k: v for k, v in m["gif_facts"].items() if k != "bytes"})
        self.assertEqual(m["gif_facts"]["bytes"], os.path.getsize(GIF))
        self.assertAlmostEqual(facts["seconds"], m["storyboard_seconds"], delta=0.5)
        # the flat brand colours survive quantisation; the GIF carries them exactly
        for name in ("Leader", "Spool", "Playhead", "Rewind"):
            self.assertIn(PALETTE[name].upper(), colors, name)

    def test_the_gif_shows_the_current_version(self):
        self.assertEqual(manifest()["version"], rewindagent.__version__)

    def test_every_shown_command_replays_exactly(self):
        # The same project, the same fourteen agent steps through the hook, the same four commands:
        # output must match to the byte. The clip types `rewindagent ...`, so the undo hint it shows is the
        # installed command's; this source-tree run says so through the same function.
        m = manifest()
        self.assertEqual(m["invocation"], "rewindagent")
        self.assertEqual(len(m["beats"]), len(scenario.SHOWN))
        with TemporaryDirectory() as d, mock.patch.object(cli, "invocation", lambda: m["invocation"]):
            beats = scenario.play(d)
        for want, got in zip(m["beats"], beats):
            self.assertEqual(want["command"], got["command"])
            self.assertEqual(want["output"], got["output"], want["command"])
            self.assertEqual(want["exit"], got["exit"], want["command"])
            self.assertEqual(want["accent_rows"], got["accent_rows"], want["command"])
            self.assertEqual(want["caption"], got["caption"])
            self.assertEqual(want["hold"], got["hold"])

    def test_the_story_is_wreck_then_rewind(self):
        m = manifest()
        n, good = len(scenario.STEPS), scenario.GOOD_STEP
        self.assertEqual((m["steps"], m["good_step"]), (n, good))
        self.assertEqual([b["command"] for b in m["beats"]],
                         ["rewindagent replay", "git status --short", "rewindagent rewind %d" % good,
                          "git status --short"])
        replay, before, rw, after = (lines(b["output"]) for b in m["beats"])
        self.assertEqual(len(replay), n, "replay lists every agent step")
        self.assertRegex(replay[0], r"^\s+1\s+Read\s+README\.md$")
        self.assertIn("rm -rf tests", replay[-2])
        self.assertTrue(replay[-2].endswith("[3 checkpointed]"), replay[-2])
        self.assertIn("app/config.py", replay[-1])
        self.assertEqual(m["beats"][0]["accent_rows"], [n - 2, n - 1])
        self.assertIn(" D tests/test_config.py", before)
        self.assertIn(" D tests/test_server.py", before)
        self.assertEqual(rw[0], "session %s: rewind to step %d of %d (did change 4 files)" % (m["session"], good, n))
        restored = [l.split()[1] for l in rw if l.startswith("  restore")]
        self.assertEqual(sorted(restored), ["app/config.py", "tests/test_config.py", "tests/test_server.py",
                                            "tests/test_timeout.py"])
        self.assertEqual(m["beats"][2]["accent_rows"], [i for i, l in enumerate(rw) if l.startswith("  restore")])
        self.assertEqual(rw[-1], "  this rewind is step %d; undo it with: rewindagent rewind %d --session %s"
                         % (n + 1, n, m["session"]))
        self.assertFalse(any(l.startswith(" D ") for l in after), after)
        self.assertIn("?? tests/test_timeout.py", after)
        self.assertEqual([l for l in after if l.startswith(" M ")], [l for l in before if l.startswith(" M ")],
                         "the agent's first %d steps are kept" % good)

    def test_words_on_the_frames(self):
        m = manifest()
        self.assertEqual(m["title_right"], "Ctrl+Z for AI coding agents")
        self.assertEqual(m["credit"], "made by John B Joseph")
        banned = re.compile(r"revolutionary|seamless|unleash|AI-powered|game-changer|secure|protect|defend|"
                            r"magic|never lose|instant", re.I)
        for b in m["beats"]:
            self.assertTrue(b["caption"].startswith("# "), b["caption"])
            self.assertIsNone(banned.search(b["caption"]), b["caption"])
            self.assertLessEqual(len(b["caption"]), m["cols"])
            for l in lines(b["output"]):
                self.assertLessEqual(len(l), m["cols"], l)
                for bad in ("/var/", "/private/", "/tmp", "/Users/", "/home/"):
                    self.assertNotIn(bad, l)
        with open(os.path.join(BRAND, "BRAND.md"), encoding="utf-8") as f:
            brand = f.read()
        for role, colour in m["colours"].items():
            self.assertIn(colour, PALETTE, (role, colour))
        self.assertEqual(m["colours"]["accent"], "Rewind")   # BRAND.md: Rewind is the accent on dark
        self.assertIn("## Demo GIF", brand)

    def test_readme_embeds_the_gif(self):
        with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
            readme = f.read()
        self.assertIn("](brand/demo.gif)", readme)
        self.assertIn("rewindagent rewind %d" % scenario.GOOD_STEP, readme)

    @unittest.skipUnless(os.environ.get("REWINDAGENT_BIN"), "REWINDAGENT_BIN not set (.fire-test-cmd sets it)")
    def test_installed_binary_prints_the_rewind_the_clip_shows(self):
        # The hint line is what the installed command prints, not a patched string.
        m = manifest()
        want = next(b for b in m["beats"] if b["command"].startswith("rewindagent rewind"))
        with TemporaryDirectory() as d:
            root = Path(os.path.realpath(d))
            scenario.make_project(root)
            agent = scenario.Agent(root)
            for tool, spec in scenario.STEPS:
                agent.step(tool, spec)
            env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
            p = subprocess.run([os.environ["REWINDAGENT_BIN"]] + want["command"].split()[1:], cwd=root, env=env,
                               capture_output=True, text=True)
        self.assertEqual(p.returncode, want["exit"], p.stderr)
        self.assertEqual(p.stdout + p.stderr, want["output"])


if __name__ == "__main__":
    unittest.main()
