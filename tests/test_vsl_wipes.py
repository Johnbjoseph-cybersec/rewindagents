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


if __name__ == "__main__":
    unittest.main()
