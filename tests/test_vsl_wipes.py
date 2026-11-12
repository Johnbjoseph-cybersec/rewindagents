"""brand/vsl wipes (review-textcut-r2.json fix 1): no frame of any rewind wipe shows two headlines at once. Round 2 had
the incoming line start 170 ms into the wipe on the outgoing line's baseline, so for 200-300 ms the frame read as one
fused line ('Twelve, bed, and four files'). For every wipe of all three films, at 30 fps, this computes the outgoing
line's opacity (render.py: faded ahead of the playhead over ERASE_RAMP px, and gone on time by WIPE_HEAD_MS) at every
frame where any word of the incoming line has begun to rise right of the playhead, and requires it to be <= 0.30
(the critic's bound). It mirrors frame()'s wipe geometry; it needs the fonts in .brandcache (brand/logo/requirements.txt)
and fontTools, and is skipped without them."""
import importlib.util
import json
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, ".brandcache")


class TestVslWipes(unittest.TestCase):
    def test_no_wipe_frame_shows_two_headlines(self):
        try:
            import fontTools  # noqa: F401
        except ImportError:
            self.skipTest("fontTools not installed (brand/logo/requirements.txt)")
        if not os.path.isdir(os.path.join(CACHE, "node_modules", "@fontsource")):
            self.skipTest("no .brandcache fonts (brand/logo/requirements.txt)")
        spec = importlib.util.spec_from_file_location("vsl_render", os.path.join(ROOT, "brand", "vsl", "render.py"))
        R = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(R)
        with open(os.path.join(ROOT, "brand", "site", "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        kit = R.Kit(CACHE)
        checked = 0
        for video in R.vsl.beats()["videos"]:
            L = R.LAYOUT[video["aspect"]]
            p = R.plan(video, cfg, L, kit)
            for c in p["cards"]:
                if not c["wipe"]:
                    continue
                prev = p["cards"][c["i"] - 1]
                wp = R.WIPES[c["wipe"]]
                size, plines, x = R.headline_layout(kit, L, prev)
                right = max(x + kit.disp.width(" ".join(ws), size, -0.01) for ws, _ in plines)
                nsize, nlines, nx = R.headline_layout(kit, L, c)
                ax = L["X0"]
                sc = [q for q in p["cards"] if q["scene"] == prev["scene"]]
                push = 1 + R.PUSH * R.ease((prev["end"] - 1 - sc[0]["start"]) / max(1, sc[-1]["end"] - sc[0]["start"]))
                f = int(c["start"] * 30 / 1000) + 1
                while f * 1000 / 30 < c["start"] + c["wipe_ms"]:
                    u = f * 1000 / 30 - c["start"]
                    xk = u / c["wipe_ms"]
                    k = R.out_cubic(xk) if wp["ease"] == "out" else R.ease(xk)
                    stop = L["X0"] if c["kind"] == "ui" else -40
                    lx = L["W"] + 40 + (stop - L["W"] - 40) * k
                    erase = ax + ((lx - wp["slide"] * k) - ax) / push
                    op = min(1.0, max(0.0, (erase - right) / R.ERASE_RAMP), 1 - R.ease(u / R.WIPE_HEAD_MS))
                    idx, vis = 0, False
                    for words, _ in nlines:
                        cx = nx
                        for w in words:
                            wd = kit.disp.width(w, nsize, -0.01)
                            if R.out_cubic((u - c["hs"] - R.WORD_GAP_MS * idx) / R.WORD_MS) > 0 and \
                                    cx + wd + wp["slide"] * (1 - k) > lx:
                                vis = True
                            cx += wd + kit.disp.width(" ", nsize)
                            idx += 1
                    if vis:
                        checked += 1
                        self.assertLessEqual(op, 0.30, "%s %s at %.0f ms: the outgoing line is at %.2f while the "
                                             "incoming one shows" % (video["name"], c["id"], c["start"] + u, op))
                    f += 1
        self.assertGreater(checked, 100)

    def load(self):
        try:
            import fontTools  # noqa: F401
        except ImportError:
            self.skipTest("fontTools not installed (brand/logo/requirements.txt)")
        if not os.path.isdir(os.path.join(CACHE, "node_modules", "@fontsource")):
            self.skipTest("no .brandcache fonts (brand/logo/requirements.txt)")
        spec = importlib.util.spec_from_file_location("vsl_render", os.path.join(ROOT, "brand", "vsl", "render.py"))
        R = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(R)
        with open(os.path.join(ROOT, "brand", "site", "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        kit = R.Kit(CACHE)
        plans = {v["name"]: R.plan(v, cfg, R.LAYOUT[v["aspect"]], kit) for v in R.vsl.beats()["videos"]}
        return R, kit, plans

    def test_light_wipes_show_headline_ink_from_150_ms(self):
        # review-textcut-r3.json fix 3: the 450 ms light wipes showed ~200 ms of bare paper with only the playhead.
        # At every 30 fps frame from 150 ms to the wipe's end, a word of the incoming line that has risen at least a
        # quarter of the way is right of the playhead (only that side of the frame shows the incoming scene).
        R, kit, plans = self.load()
        checked = 0
        for name, p in plans.items():
            L = R.LAYOUT["9:16" if "vertical" in name else "16:9"]
            for c in p["cards"]:
                if c["wipe"] != "light":
                    continue
                wp = R.WIPES["light"]
                nsize, nlines, nx = R.headline_layout(kit, L, c)
                f = int(c["start"] * 30 / 1000) + 1
                while f * 1000 / 30 < c["start"] + c["wipe_ms"]:
                    u = f * 1000 / 30 - c["start"]
                    f += 1
                    if u < 150:
                        continue
                    k = R.out_cubic(u / c["wipe_ms"])
                    lx = L["W"] + 40 + (-40 - L["W"] - 40) * k
                    idx, vis, cx = 0, False, None
                    for words, _ in nlines:
                        cx = nx
                        for w in words:
                            wd = kit.disp.width(w, nsize, -0.01)
                            if R.out_cubic((u - c["hs"] - R.WORD_GAP_MS * idx) / R.WORD_MS) >= 0.25 and \
                                    cx + wd + wp["slide"] * (1 - k) > lx:
                                vis = True
                            cx += wd + kit.disp.width(" ", nsize)
                            idx += 1
                    self.assertTrue(vis, "%s %s at %.0f ms (%.0f ms into the light wipe): bare paper"
                                    % (name, c["id"], c["start"] + u, u))
                    checked += 1
        self.assertGreater(checked, 40)

    def test_chapter_accent_leaves_before_the_line_accent_rises(self):
        # r3 fix 5: the chapter's part label (Record) was still fading out while the line's Record words rose, ~150 ms
        # of two accents. Draw the chapter alone at every ms from the first accent word's start to the chapter's
        # exit: no Record fill may be in it.
        R, kit, plans = self.load()
        n = 0
        for name, p in plans.items():
            L = R.LAYOUT["9:16" if "vertical" in name else "16:9"]
            for c in p["cards"]:
                if not c["d"].get("chapter"):
                    continue
                hold = c["d"]["chapter"][1]
                acc = set() if R.proof_accented(c) else c["accent_idx"]
                self.assertTrue(acc, "%s %s: no accent word to test" % (name, c["id"]))
                first = min(c["hs"] + R.WORD_GAP_MS * i for i in acc)
                for u in range(int(first), hold + R.CHAPTER_OUT_MS + 1, 5):
                    cv = R.Canvas(L["W"], L["H"], "Leader")
                    R.draw_chapter(cv, kit, L, p, c, u)
                    self.assertNotIn(R.C["Record"], "".join(cv.parts) if hasattr(cv, "parts") else cv.svg(),
                                     "%s %s at %d ms: the chapter is still in Record while the line's accent rises"
                                     % (name, c["id"], u))
                n += 1
        self.assertEqual(n, 2)

    def test_b18_one_chip_types_at_a_time_and_each_has_its_output(self):
        # r3 fix 4: '$ rewindagents di' over '$ rewin' at 72.2 s. The second chip starts after the first has typed
        # and printed; each chip has an output row under it.
        R, kit, plans = self.load()
        c = next(c for c in plans["vsl-90s"]["cards"] if c["id"] == "b18")
        rows, d = c["screen"], c["d"]
        self.assertEqual(d["out_rows"], [1, 3])
        appear = R.rows_appear(c)        # the renderer's own timing, not a copy of it
        for i in range(1, len(rows)):           # each chip starts after everything above it has typed / printed
            if R.COMMAND.match(rows[i]):
                done = max(appear[j] + (R.TYPE_MS * len(rows[j]) if R.COMMAND.match(rows[j]) else 0) for j in range(i))
                self.assertGreater(appear[i], done, "b18 row %d types while row above it still types" % i)
        self.assertLessEqual(appear[3] + R.RISE_MS, c["end"] - c["start"] - 600, "b18's last output lands too late")

    def test_b19_close_opens_on_step_14_and_reads_at_27_px(self):
        # r3 fix 2: the push lands by ~2.9 s and holds >= 2 s; the close shows the '14 Write' header (source y 635)
        # to step 15's last chip (y 819) at a scale where the 9 px timestamp digits run >= 27 px.
        R, kit, plans = self.load()
        L = R.LAYOUT["16:9"]
        c = next(c for c in plans["vsl-90s"]["cards"] if c["kind"] == "ui")
        land = R.UI_HOLD_MS + R.UI_PUSH_MS
        self.assertGreaterEqual(c["end"] - c["start"] - land, 2000)
        sx, sy, s, vw, vh = R.ui_view(L, land)
        self.assertGreaterEqual(s * 9, 27)
        self.assertLessEqual(sy, 635)
        self.assertGreaterEqual(sy + vh / s, 819)
        self.assertLessEqual(R.UI_TOP + vh, L["H"] - R.SAFE)


if __name__ == "__main__":
    unittest.main()
