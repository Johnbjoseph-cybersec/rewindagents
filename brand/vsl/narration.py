"""The site's copy of the film: brand/vsl/vsl-90s-web.mp4 and its poster brand/vsl/vsl-90s-poster.jpg, both from
brand/vsl-90s.mp4 as render.py wrote it.

The films carry no narration (John, 2026-11-12: "remove the voice over altogether, explain through text"). The file
keeps its name because brand/site/build.py points here for the web export; there is no voice to lay, so there is
no mix, no voice clips and no brand/vsl/voice/ directory. The only sound is render.py's music bed.

  .venv/bin/python brand/vsl/render.py    -> the three mp4s, captions, manifest
  python3 brand/vsl/narration.py web      -> brand/vsl/vsl-90s-web.mp4 + brand/vsl/vsl-90s-poster.jpg, manifest "web"

web: a stream copy of brand/vsl-90s.mp4 (picture and sound unchanged) with the moov atom first (faststart) when the
source is at most WEB_MAX_BYTES, else a re-encode of the picture at crf 23 with the sound copied. The poster is the
last moment of POSTER_BEAT, "One command, and four files come back.", when every restore line is on screen.
"""
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BRAND = os.path.dirname(HERE)
ROOT = os.path.dirname(BRAND)
sys.path.insert(0, HERE)

import build as vsl  # noqa: E402

WEB_NAME = "vsl-90s"
WEB_MP4 = os.path.join(HERE, "vsl-90s-web.mp4")
WEB_POSTER = os.path.join(HERE, "vsl-90s-poster.jpg")
WEB_MAX_BYTES = 12 * 1024 * 1024
# the stream's own VUI says BT.709 primaries, transfer and matrix, limited range (libx264 left primaries/transfer unset)
BT709_BSF = "h264_metadata=colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1:video_full_range_flag=0"
POSTER_BEAT = "b14"       # "One command, and four files come back." - its last moment has every restore line lit
POSTER_BEFORE_END_MS = 200


def beat_start(video, beat_id):
    """(start, end) in ms of a beat in its video."""
    t = 0
    for b in video["beats"]:
        if b["id"] == beat_id:
            return t, t + b["ms"]
        t += b["ms"]
    raise KeyError(beat_id)


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def ff(*args):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"] + list(args), check=True)


def gray_mean(jpg):
    p = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", jpg, "-vf", "scale=64:36,format=gray",
                        "-f", "rawvideo", "-"], capture_output=True, check=True)
    return sum(p.stdout) / len(p.stdout)


def web(workdir):
    """brand/vsl/vsl-90s-web.mp4 + brand/vsl/vsl-90s-poster.jpg for the site, from brand/vsl-90s.mp4."""
    video = next(v for v in vsl.beats()["videos"] if v["name"] == WEB_NAME)
    src = os.path.join(BRAND, WEB_NAME + ".mp4")
    tmp = os.path.join(workdir, os.path.basename(WEB_MP4))
    if os.path.getsize(src) <= WEB_MAX_BYTES:
        ff("-i", src, "-map", "0:v:0", "-map", "0:a:0", "-c", "copy", "-movflags", "+faststart",
           "-map_metadata", "-1", "-metadata", "title=" + video["title"], tmp)
        how = "stream copy of brand/%s.mp4 (picture and sound unchanged)" % WEB_NAME
    else:
        ff("-i", src, "-map", "0:v:0", "-map", "0:a:0", "-c:v", "libx264", "-preset", "slow", "-crf", "23",
           "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
           "-color_range", "tv", "-bsf:v", BT709_BSF, "-c:a", "copy", "-movflags", "+faststart", "-map_metadata", "-1",
           "-metadata", "title=" + video["title"], tmp)
        how = "re-encoded from brand/%s.mp4 at crf 23 to fit %d bytes, sound copied" % (WEB_NAME, WEB_MAX_BYTES)
    if os.path.getsize(tmp) > WEB_MAX_BYTES:
        raise SystemExit("web export is %d bytes, over %d" % (os.path.getsize(tmp), WEB_MAX_BYTES))
    os.replace(tmp, WEB_MP4)
    _, end = beat_start(video, POSTER_BEAT)
    poster_ms = end - POSTER_BEFORE_END_MS
    ff("-ss", "%.3f" % (poster_ms / 1000), "-i", src, "-frames:v", "1", "-q:v", "3", WEB_POSTER)
    return {"mp4": os.path.relpath(WEB_MP4, BRAND), "sha256": sha256(WEB_MP4), "bytes": os.path.getsize(WEB_MP4),
            "from": how, "source_sha256": sha256(src), "voice": False,
            "poster": os.path.relpath(WEB_POSTER, BRAND), "poster_ms": poster_ms, "poster_beat": POSTER_BEAT,
            "poster_sha256": sha256(WEB_POSTER), "poster_mean_luma": round(gray_mean(WEB_POSTER), 1)}


def main(argv):
    if argv[:1] != ["web"]:
        print(__doc__)
        return 2
    work = os.path.join(ROOT, "build", "narration")
    os.makedirs(work, exist_ok=True)
    mpath = os.path.join(HERE, "manifest.json")
    with open(mpath, encoding="utf-8") as f:
        manifest = json.load(f)
    manifest.pop("narration", None)
    manifest["web"] = web(work)
    print("web: %s" % json.dumps(manifest["web"], sort_keys=True))
    with open(mpath, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
        f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
