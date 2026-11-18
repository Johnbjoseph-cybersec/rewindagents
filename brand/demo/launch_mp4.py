"""Build brand/launch-demo.mp4 (task RB4c): the demo session as a screen recording for launch posts, with the
captions burnt in and brand/launch-demo.srt beside it.

Same session and same frame path as brand/demo.gif: the beats come from brand/demo/manifest.json (the record
tests/test_demo.py replays against the real CLI byte for byte), the storyboard is brand/demo/build.py's
storyboard() and every terminal frame is its frame_body(). Nothing is re-typed here. Each GIF frame lasts a
whole number of 40 ms steps, so at 25 frames a second every GIF frame is a whole number of video frames and
the timing is the GIF's exactly.

What the mp4 adds: the frame is 1920x1080 with the terminal scaled up, the beat's caption (its `# ` comment,
without the `# `) burnt in under the terminal in Hanken Grotesk 600 so it reads on a phone with the sound off,
and the VSLs' end card (brand/vsl/render.py draw_end: wordmark, the one-line promise, the site address read from
brand/site/config.json at render time, the credit). No sound track: it is a screen recording, and the manifest
says so.

Usage: .venv/bin/python brand/demo/launch_mp4.py [<.brandcache dir>]
Needs what brand/vsl/render.py needs (fontTools in .venv, @fontsource + @resvg/resvg-js in .brandcache, node and
ffmpeg with libx264). Writes brand/launch-demo.mp4, brand/launch-demo.srt, brand/demo/launch-manifest.json,
key frames taken from the finished file in brand/demo/launch-keyframes/ and brand/demo/launch-contact-sheet.png.
Frame sources go to brand/demo/frames/launch/ (git-ignored).
"""
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BRAND = os.path.dirname(HERE)
ROOT = os.path.dirname(BRAND)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


demo = load("demo_build", os.path.join(HERE, "build.py"))
render = load("vsl_render", os.path.join(BRAND, "vsl", "render.py"))
scenario = demo.scenario
C = demo.C

FPS = 25                       # 40 ms a frame: the GIF's timing grid
W, H = 1920, 1080
SCALE = 1.3                    # the 1200x675 demo frame drawn at 1560x877.5
DX, DY = (W - demo.W * SCALE) / 2, 24
CAP, CAP_LH = 40, 52           # caption size and line pitch
CAP_TOP = DY + demo.H * SCALE + 60      # first caption baseline
CAP_X, CAP_W = DX + demo.PX * SCALE, demo.PW * SCALE    # captions share the terminal's left edge and width
END_SECONDS = 3.0
OUT = "launch-demo"


def beats_sha256(beats):
    """Fingerprint of the recorded session as brand/demo/manifest.json keeps it."""
    return hashlib.sha256(json.dumps(beats, sort_keys=True).encode("utf-8")).hexdigest()


def read_demo_manifest():
    with open(os.path.join(HERE, "manifest.json"), encoding="utf-8") as f:
        return json.load(f)


def timeline(m):
    """[(lines, frames, caption)] for the terminal part, from the GIF's own storyboard; the caption is the
    latest beat comment that has appeared, without its `# `."""
    if len(m["beats"]) != len(scenario.SHOWN):
        raise SystemExit("brand/demo/manifest.json has %d beats, scenario.SHOWN %d" % (len(m["beats"]), len(scenario.SHOWN)))
    beats = [dict(b, stream=s.get("stream")) for b, s in zip(m["beats"], scenario.SHOWN)]
    frames = demo.merge(demo.storyboard(beats)[0])
    total = demo.check(beats, frames, m["cols"], "\0")
    if abs(total - m["storyboard_seconds"]) > 1e-6:
        raise SystemExit("storyboard is %.2f s, the GIF's manifest says %.2f s" % (total, m["storyboard_seconds"]))
    out, caption = [], ""
    for lines, sec in frames:
        shown = [line[0][0] for line in lines if len(line) == 1 and line[0][1] == "caption"]
        if shown:
            caption = shown[-1][2:] if shown[-1].startswith("# ") else shown[-1]
        n = round(sec * FPS)
        if abs(n / FPS - sec) > 1e-6:
            raise SystemExit("frame of %.3f s is not a whole number of %d fps frames" % (sec, FPS))
        out.append((lines, n, caption))
    return out


def caption_lines(kit, text):
    return render.wrap(kit.bold, text, CAP, CAP_W)


def term_frame(kit, logo_mono, static, lines, caption):
    cv = render.Canvas(W, H, "Leader")
    cv.add('<svg x="%.2f" y="%.2f" width="%.2f" height="%.2f" viewBox="0 0 %d %d">%s%s</svg>'
           % (DX, DY, demo.W * SCALE, demo.H * SCALE, demo.W, demo.H,
              render.rect(0, 0, demo.W, demo.H, C["Leader"]), demo.frame_body(logo_mono, static, lines)))
    base = CAP_TOP
    for line in caption_lines(kit, caption) if caption else []:
        cv.text(kit.bold, line, CAP, CAP_X, base, "Reel")
        base += CAP_LH
    return cv.svg()


def end_frame(kit, cfg):
    cv = render.Canvas(W, H, "Reel")
    # draw_end animates the card; a still is the settled card: start 0, line at 0, read well after it lands
    render.draw_end(cv, kit, render.LAYOUT["16:9"], cfg, {"start": 0, "hs": 0}, 10000)
    return cv.svg()


def srt_time(ms):
    return "%02d:%02d:%02d,%03d" % (ms // 3600000, ms // 60000 % 60, ms // 1000 % 60, ms % 1000)


def cues(tl, kit):
    """(start ms, end ms, lines): one cue per caption, from the frame it appears to the frame it changes."""
    out, t = [], 0
    for _, n, caption in tl:
        ms = n * 1000 // FPS
        if caption and out and out[-1][3] == caption:
            out[-1][1] = t + ms
        elif caption:
            out.append([t, t + ms, caption_lines(kit, caption), caption])
        t += ms
    return [(s, e, lines) for s, e, lines, _ in out]


def write_srt(path, cue_list):
    with open(path, "w", encoding="utf-8") as f:
        for i, (s, e, lines) in enumerate(cue_list, 1):
            f.write("%d\n%s --> %s\n%s\n\n" % (i, srt_time(s), srt_time(e), "\n".join(lines)))


def build(cache):
    m = read_demo_manifest()
    with open(os.path.join(BRAND, "site", "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    kit = render.Kit(cache)
    logo = demo.load_logo_build()
    fs = os.path.join(cache, "node_modules", "@fontsource")
    mono = demo.Mono(logo.Face(os.path.join(fs, "commit-mono", "files", "commit-mono-latin-400-normal.woff")))
    disp = logo.Face(os.path.join(fs, "bricolage-grotesque", "files", "bricolage-grotesque-latin-800-normal.woff"))
    small = logo.Face(os.path.join(fs, "hanken-grotesk", "files", "hanken-grotesk-latin-400-normal.woff"))
    static = demo.chrome(logo, disp, small)

    tl = timeline(m)
    end_n = round(END_SECONDS * FPS)
    fdir = os.path.join(HERE, "frames", "launch")
    shutil.rmtree(fdir, ignore_errors=True)
    os.makedirs(fdir)
    palette = {v.upper() for v in C.values()}
    svgs, seq, shown_caps = [], [], []
    for i, (lines, n, caption) in enumerate(tl):
        svgs.append(term_frame(kit, mono, static, lines, caption))
        seq += [i] * n
        if caption and (not shown_caps or shown_caps[-1] != caption):
            shown_caps.append(caption)
    svgs.append(end_frame(kit, cfg))
    seq += [len(svgs) - 1] * end_n
    names = []
    for i, svg in enumerate(svgs):
        off = {f.upper() for f in re.findall(r'(?:fill|stroke)="(#[0-9A-Fa-f]{6})"', svg)} - palette
        if off:
            raise SystemExit("frame %d uses colours outside the palette: %s" % (i, sorted(off)))
        names.append("u%05d.svg" % i)
        with open(os.path.join(fdir, names[-1]), "w", encoding="utf-8") as f:
            f.write(svg)
    with open(os.path.join(fdir, "frames.json"), "w", encoding="utf-8") as f:
        json.dump({"width": W, "height": H, "svgs": names}, f)
    subprocess.run(["node", os.path.join(BRAND, "vsl", "render.mjs"), fdir, os.path.join(cache, "node_modules")], check=True)
    sdir = os.path.join(fdir, "seq")
    os.makedirs(sdir)
    for f, u in enumerate(seq):
        os.symlink(os.path.join(fdir, names[u][:-4] + ".png"), os.path.join(sdir, "%05d.png" % f))

    mp4 = os.path.join(BRAND, OUT + ".mp4")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-framerate", str(FPS),
                    "-i", os.path.join(sdir, "%05d.png"), "-c:v", "libx264", "-preset", "slow", "-crf", "18",
                    "-tune", "animation", "-pix_fmt", "yuv420p", "-r", str(FPS), "-an", "-movflags", "+faststart",
                    "-metadata", "title=rewindagents: a wrecked repo put back with rewindagents rewind", mp4], check=True)
    cue_list = cues(tl, kit)
    write_srt(os.path.join(BRAND, OUT + ".srt"), cue_list)

    # key frames from the finished file: the last moment of every beat's hold, and the end card
    kdir = os.path.join(HERE, "launch-keyframes")
    shutil.rmtree(kdir, ignore_errors=True)
    os.makedirs(kdir)
    keys = [(e - 200, "k%d" % i) for i, (_, e, _) in enumerate(cue_list)]
    keys.append((len(seq) * 1000 // FPS - 500, "k%d-end" % len(cue_list)))
    for ms, tag in keys:
        out = os.path.join(kdir, tag + ".png")
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "%.3f" % (ms / 1000), "-i", mp4,
                        "-frames:v", "1", out], check=True)
    subprocess.run(["node", os.path.join(BRAND, "vsl", "sheet.mjs"), kdir, os.path.join(HERE, "launch-contact-sheet.png"),
                    os.path.join(cache, "node_modules")], check=True)

    facts = render.mp4_info(mp4)
    facts["bytes"] = os.path.getsize(mp4)
    with open(mp4, "rb") as f:
        facts["sha256"] = hashlib.sha256(f.read()).hexdigest()
    manifest = {
        "mp4": OUT + ".mp4", "srt": OUT + ".srt", "fps": FPS, "width": W, "height": H,
        "frames": len(seq), "unique_frames": len(svgs),
        "terminal_seconds": m["storyboard_seconds"], "end_card_seconds": END_SECONDS,
        "session": m["session"], "version": m["version"], "commands": [b["command"] for b in m["beats"]],
        "demo_beats_sha256": beats_sha256(m["beats"]),
        "captions_burnt_in": shown_caps,
        "cues": [{"start_ms": s, "end_ms": e, "lines": lines} for s, e, lines in cue_list],
        "keyframes": [os.path.relpath(os.path.join(kdir, tag + ".png"), BRAND) for _, tag in keys],
        "contact_sheet": "demo/launch-contact-sheet.png",
        "audio": "none: a screen recording; the captions carry the words",
        "note": "Written by brand/demo/launch_mp4.py. The address on the end card comes from brand/site/config.json "
                "at render time; this file keeps no address.",
        "mp4_facts": facts,
    }
    with open(os.path.join(HERE, "launch-manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
        f.write("\n")
    print("%s: %d x %d, %.2f s, %d frames (%d unique), %d KB, %d cues"
          % (OUT, facts["width"], facts["height"], facts["seconds"], len(seq), len(svgs), facts["bytes"] // 1024,
             len(cue_list)))


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, ".brandcache"))
