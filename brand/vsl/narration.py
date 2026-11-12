"""Narration on the accepted VSLs (task RB4d): John's cloned voice placed on each caption cue, the music bed ducked
under it, muxed into brand/vsl-90s.mp4, vsl-30s.mp4 and vsl-15s-vertical.mp4 with the picture stream copied, never
re-encoded (John, 2026-11-12: round 2 visuals accepted as they are; cloned voice yes).

What is said is the caption text of brand/vsl/<name>.srt (the cues of build.py), turned into spoken form by
SPOKEN below: "rewindagents" is read as "rewind agents", "Apache-2.0" as "Apache two point oh", "PyPI" as
"pie-P-I", "HTML" as "H-T-M-L". Nothing else is added or dropped; tests/test_narration.py checks it, and the
words the studio's speech recogniser heard are kept per take in brand/vsl/voice/report.json.

The voice is the studio's locked Voice A (ai-creative-studio voice/VOICE_LOCK.json grc_voice_A: engine
voice/synth.py and its reference recording, both sha256-pinned and checked before any take is made). It runs in
the studio's own venv, so it is a separate step:

  ~/ai-creative-studio/.venv-voice/bin/python ~/fire/rewindagent/brand/vsl/narrate_synth.py   -> voice/<name>/<nn>.wav
  python3 ~/fire/rewindagent/brand/vsl/narration.py mix                                       -> the three mp4s + manifest
  python3 ~/fire/rewindagent/brand/vsl/narration.py web                                       -> site export + poster

mix (stdlib + ffmpeg) keeps the voice-free mix it started from as brand/vsl/voice/<name>.music.m4a (the music bed,
stream-copied out of the accepted mp4 once) and writes brand/vsl-15s-vertical-reels.mp4, the voice-free cut for
Instagram Reels (John: Reels stay voice-free). Each cue's speech starts LEAD_MS after its cue's t0; when the cue
before it is still speaking, it starts GAP_MS after that speech ends, and if a cue cannot finish by the end of its
beat at normal pace it is sped up by at most MAX_TEMPO (an overrun past that is recorded, not hidden). The
placement, tempo and measured levels go into brand/vsl/manifest.json under "narration". mix ends by running web.

web writes brand/vsl/vsl-90s-web.mp4 (the 90 s video for the site: H.264 1920x1080, faststart, at most WEB_MAX_BYTES,
picture and sound copied from brand/vsl-90s.mp4 when it already fits) and brand/vsl/vsl-90s-poster.jpg (the frame
POSTER_MS into the 90 s video: "Four files back", the restore lines). manifest "web" records whether the export
carries the voice, so the site never claims narration the file does not have.
"""
import array
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
BRAND = os.path.dirname(HERE)
ROOT = os.path.dirname(BRAND)
VOICE_DIR = os.path.join(HERE, "voice")
sys.path.insert(0, HERE)

import build as vsl  # noqa: E402

STUDIO = os.path.expanduser("~/ai-creative-studio")
VOICE_LOCK = os.path.join(STUDIO, "voice", "VOICE_LOCK.json")
SR = 48000
GAP_MS = 120              # least silence between two cues' speech
LEAD_MS = 60              # speech starts this long after its cue appears
MAX_TEMPO = 1.12          # the most a cue may be sped up to fit its beat
SPEECH_DB = -40.0         # a 10 ms window louder than this (dBFS) counts as speech
VOICE_OVER_MUSIC_DB = 19.0  # studio target 17-21 dB while talking (audio/REFERENCE_TARGETS.json)
# integrated LUFS: 16:9 stays at the accepted render's -16 (render.py LOUDNESS); 9:16 at the Shorts/Reels target
MASTER = {"16:9": -16.0, "9:16": -11.5}
TRUE_PEAK = -1.0
VOICE_CHAIN = "highpass=f=80,acompressor=threshold=-20dB:ratio=2.5:attack=8:release=120"  # VOICE_LOCK master_chain

WEB_NAME = "vsl-90s"
WEB_MP4 = os.path.join(HERE, "vsl-90s-web.mp4")
WEB_POSTER = os.path.join(HERE, "vsl-90s-poster.jpg")
WEB_MAX_BYTES = 12 * 1024 * 1024
POSTER_BEAT = "b08"       # "Four files back: all three tests and the config." - the restore, in the accent colour

# Written form -> spoken form, applied in this order. Only what a voice cannot read as written.
SPOKEN = [
    (r"\brewindagents\b", lambda m: "rewind agents"),
    (r"\bApache-2\.0\b", lambda m: "Apache two point oh"),
    (r"\bPyPI\b", lambda m: "pie-P-I"),
    (r"\bHTML\b", lambda m: "H-T-M-L"),
    (r"\b(\d+)\b", lambda m: number(m.group(1))),
]

ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen " \
       "seventeen eighteen nineteen".split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def number(digits):
    """66 -> sixty-six, 110 -> one hundred and ten, 20000 -> twenty thousand."""
    n = int(digits)
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + ("" if n % 10 == 0 else "-" + ONES[n % 10])
    if n < 1000:
        rest = n % 100
        return ONES[n // 100] + " hundred" + ("" if rest == 0 else " and " + number(str(rest)))
    if n < 100000:
        rest = n % 1000
        head = number(str(n // 1000)) + " thousand"
        if rest == 0:
            return head
        return head + (" and " if rest < 100 else " ") + number(str(rest))
    raise ValueError("no spoken form for %s" % digits)


def spoken(text):
    for pattern, repl in SPOKEN:
        text = re.sub(pattern, repl, text)
    return text[:1].upper() + text[1:]


def units(video):
    """The video's caption cues joined into whole sentences: a cue that ends mid-sentence (build.py cuts a sentence
    longer than one cue) is spoken in one clip with the cue after it, so no take starts or stops inside a sentence.
    [(start ms, end ms, caption text, [cue numbers from 1])]."""
    out, cur = [], None
    for i, (start, end, lines) in enumerate(vsl.cues(video), 1):
        text = " ".join(lines)
        if cur is None:
            cur = [start, end, text, [i]]
        else:
            cur[1], cur[2], cur[3] = end, cur[2] + " " + text, cur[3] + [i]
        if re.search(r"[.?!]$", text):
            out.append(tuple(cur))
            cur = None
    if cur is not None:
        out.append(tuple(cur))
    return out


def cue_jobs():
    """[(video name, unit number from 1, start ms, end ms, caption text, spoken text)] for all three videos."""
    out = []
    for video in vsl.beats()["videos"]:
        for i, (start, end, caption, _cues) in enumerate(units(video), 1):
            out.append((video["name"], i, start, end, caption, spoken(caption)))
    return out


def beat_ends(video):
    t, out = 0, []
    for b in video["beats"]:
        t += b["ms"]
        out.append(t)
    return out


def beat_start(video, beat_id):
    t = 0
    for b in video["beats"]:
        if b["id"] == beat_id:
            return t, t + b["ms"]
        t += b["ms"]
    raise KeyError(beat_id)


# ---- audio helpers (stdlib wave + ffmpeg) ---------------------------------------------------------------------
def read_wav(path):
    with wave.open(path, "rb") as w:
        if w.getsampwidth() != 2 or w.getnchannels() != 1:
            raise SystemExit("%s: want 16-bit mono" % path)
        sr = w.getframerate()
        data = array.array("h")
        data.frombytes(w.readframes(w.getnframes()))
    return data, sr


def decode(path, sr=SR):
    """Any audio (or the audio of a video) as mono 16-bit samples at sr, through ffmpeg."""
    p = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", path, "-map", "0:a:0", "-ac", "1",
                        "-ar", str(sr), "-f", "s16le", "-"], capture_output=True, check=True)
    data = array.array("h")
    data.frombytes(p.stdout)
    return data


def window_db(data, sr, ms=10):
    """dBFS of each `ms` window."""
    n = int(sr * ms / 1000)
    out = []
    for i in range(0, len(data) - n + 1, n):
        s = 0
        for v in data[i:i + n]:
            s += v * v
        rms = (s / n) ** 0.5 / 32768.0
        out.append(-120.0 if rms <= 1e-6 else 20 * math.log10(rms))
    return out


def speech_bounds(data, sr, ms=10):
    """(first, last) ms of speech in a clip: the first and last window above SPEECH_DB."""
    db = window_db(data, sr, ms)
    loud = [i for i, v in enumerate(db) if v > SPEECH_DB]
    if not loud:
        return None
    return loud[0] * ms, (loud[-1] + 1) * ms


def rms_db(data, sr, a_ms, b_ms):
    seg = data[int(sr * a_ms / 1000):int(sr * b_ms / 1000)]
    if not seg:
        return -120.0
    s = sum(v * v for v in seg) / len(seg)
    rms = s ** 0.5 / 32768.0
    return -120.0 if rms <= 1e-6 else 20 * math.log10(rms)


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def stream_md5(mp4, stream="v"):
    """md5 of one stream's packets (v or a): equal before and after a mux that copies that stream."""
    p = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", mp4, "-map", "0:%s:0" % stream,
                        "-c", "copy", "-f", "md5", "-"], capture_output=True, text=True, check=True)
    return p.stdout.strip().split("=", 1)[1]


def video_md5(mp4):
    return stream_md5(mp4, "v")


def loudness(path):
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-map", "0:a", "-af", "ebur128=peak=true",
                        "-f", "null", "-"], capture_output=True, text=True)
    i = re.findall(r"I:\s+(-?[\d.]+) LUFS", p.stderr)
    tp = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", p.stderr)
    return {"integrated_lufs": float(i[-1]) if i else None, "true_peak_dbfs": float(tp[-1]) if tp else None}


def ff(*args):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


# ---- placement ------------------------------------------------------------------------------------------------
def place(video, spans, clips):
    """Start time and tempo per unit. spans: [(start ms, end ms, ...)] from units(); clips: {n: (speech_start_ms,
    speech_end_ms)} measured in the unit's wav. A unit starts LEAD_MS after its t0 or GAP_MS after the previous
    unit's speech, whichever is later; if it would then run past the end of its beat, it is sped up (at most
    MAX_TEMPO) so it ends there."""
    ends = beat_ends(video)
    out, prev_end = [], -10 ** 9
    for n, (start, end, *_rest) in enumerate(spans, 1):
        s0, s1 = clips[n]
        length = s1 - s0
        at = max(start + LEAD_MS, prev_end + GAP_MS)
        beat_end = next(e for e in ends if e >= end)
        room = beat_end - at - 40
        tempo = 1.0
        if length > room:
            tempo = round(min(MAX_TEMPO, length / max(1, room)) + 0.005, 3)
        spoken_ms = round(length / tempo)
        out.append({"cue": n, "cue_start_ms": start, "cue_end_ms": end, "beat_end_ms": beat_end, "at_ms": at,
                    "tempo": tempo, "speech_ms": spoken_ms, "speech_end_ms": at + spoken_ms,
                    "overrun_ms": max(0, at + spoken_ms - beat_end)})
        prev_end = at + spoken_ms
    return out


def voice_stem(name, placement, total_ms, workdir):
    """All cues of one video on one 48 kHz mono track, each trimmed to its speech, sped up if placed so, and
    put at its at_ms. Returns the stem path."""
    parts, labels = [], []
    for p in placement:
        src = os.path.join(VOICE_DIR, name, "%02d.wav" % p["cue"])
        data, sr = read_wav(src)
        s0, s1 = speech_bounds(data, sr)
        chain = "atrim=start=%.3f:end=%.3f,asetpts=PTS-STARTPTS,aresample=%d" % (s0 / 1000, s1 / 1000, SR)
        if p["tempo"] != 1.0:
            chain += ",atempo=%.3f" % p["tempo"]
        chain += ",adelay=%d|%d" % (p["at_ms"], p["at_ms"])
        parts.append(src)
        labels.append("[%d:a]%s[v%d]" % (len(parts) - 1, chain, p["cue"]))
    mix = "".join("[v%d]" % p["cue"] for p in placement)
    graph = ";".join(labels) + ";%samix=inputs=%d:normalize=0:dropout_transition=0,%s,apad,atrim=end=%.3f[out]" % (
        mix, len(placement), VOICE_CHAIN, total_ms / 1000)
    stem = os.path.join(workdir, name + ".voice.wav")
    args = []
    for src in parts:
        args += ["-i", src]
    ff(*args, "-filter_complex", graph, "-map", "[out]", "-ac", "1", "-ar", str(SR), "-c:a", "pcm_s16le", stem)
    return stem


def decode_ducked(stem, music, gain, workdir, name):
    """The bed alone, at its mix gain and ducked by the voice, as it sits in the final mix (before the master)."""
    out = os.path.join(workdir, name + ".bed.wav")
    graph = ("[1:a]aresample=%d,volume=%.2fdB[bed];[0:a]asplit=2[vo][sc];[vo]anullsink;"
             "[bed][sc]sidechaincompress=threshold=0.02:ratio=3:attack=20:release=400[out]" % (SR, gain))
    ff("-i", stem, "-i", music, "-filter_complex", graph, "-map", "[out]", "-ac", "1", "-c:a", "pcm_s16le", out)
    return decode(out)


def mix_video(video, cues, workdir):
    name = video["name"]
    mp4 = os.path.join(BRAND, name + ".mp4")
    music = os.path.join(VOICE_DIR, name + ".music.m4a")
    if not os.path.exists(music):        # first run: the accepted, voice-free mix is the bed; keep it
        ff("-i", mp4, "-map", "0:a:0", "-c", "copy", music)
    total_ms = sum(b["ms"] for b in video["beats"])
    clips = {}
    for n in range(1, len(cues) + 1):
        data, sr = read_wav(os.path.join(VOICE_DIR, name, "%02d.wav" % n))
        bounds = speech_bounds(data, sr)
        if bounds is None:
            raise SystemExit("%s cue %d: the clip has no speech above %.0f dBFS" % (name, n, SPEECH_DB))
        clips[n] = bounds
    placement = place(video, cues, clips)
    stem = voice_stem(name, placement, total_ms, workdir)

    # the bed's static level so that it sits VOICE_OVER_MUSIC_DB under the voice while the voice speaks,
    # measured as RMS over the speech windows; then a sidechain duck under the voice on top of that
    v = decode(stem)
    m = decode(music)
    windows = [(p["at_ms"], p["speech_end_ms"]) for p in placement]

    def over(vd, md):
        vs = [rms_db(vd, SR, a, b) for a, b in windows]
        ms = [rms_db(md, SR, a, b) for a, b in windows]
        return sum(vs) / len(vs) - sum(ms) / len(ms)

    gain = over(v, m) - VOICE_OVER_MUSIC_DB                 # dB to apply to the bed (negative = quieter)
    for _ in range(2):                                      # the duck takes the bed down further: correct for it
        gain += over(v, decode_ducked(stem, music, gain, workdir, name)) - VOICE_OVER_MUSIC_DB
    gain = round(gain, 2)
    target = MASTER[video["aspect"]]
    graph = ("[1:a]aresample=%d,volume=%.2fdB[bed];[0:a]asplit=2[vo][sc];"
             "[bed][sc]sidechaincompress=threshold=0.02:ratio=3:attack=20:release=400[duck];"
             "[vo][duck]amix=inputs=2:normalize=0:duration=first,"
             "loudnorm=I=%.1f:TP=%.1f:LRA=11,aresample=%d[out]" % (SR, gain, target, TRUE_PEAK - 0.5, SR))
    mixed = os.path.join(workdir, name + ".mix.wav")
    ff("-i", stem, "-i", music, "-filter_complex", graph, "-map", "[out]", "-ac", "2", "-c:a", "pcm_s16le", mixed)

    before = video_md5(mp4)
    tmp = os.path.join(workdir, name + ".mp4")
    ff("-i", mp4, "-i", mixed, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
       "-ar", str(SR), "-t", "%.3f" % (total_ms / 1000), "-movflags", "+faststart", "-map_metadata", "-1",
       "-metadata", "title=" + video["title"], tmp)
    after = video_md5(tmp)
    if before != after:
        raise SystemExit("%s: the picture stream changed in the mux" % name)
    os.replace(tmp, mp4)

    # measured on the files as written
    final = decode(mp4)
    bed_only = decode(music)
    voice_db = [rms_db(v, SR, a, b) for a, b in windows]
    ducked = decode_ducked(stem, music, gain, workdir, name)
    res = {
        "mp4_sha256": sha256(mp4), "video_md5": after, "music_bed": os.path.relpath(music, BRAND),
        "music_bed_sha256": sha256(music), "bed_gain_db": gain,
        "master": {"integrated_lufs_target": target, "true_peak_max": TRUE_PEAK}, "measured": loudness(mp4),
        "voice_over_music_rms_db_while_talking": round(
            sum(voice_db) / len(voice_db) - sum(rms_db(ducked, SR, a, b) for a, b in windows) / len(windows), 1),
        "cues": [],
    }
    for p, (start, end, caption, cue_numbers) in zip(placement, cues):
        a, b = p["at_ms"], p["speech_end_ms"]
        p.update(caption=caption, spoken=spoken(caption), srt_cues=cue_numbers,
                 wav="vsl/voice/%s/%02d.wav" % (name, p["cue"]),
                 wav_sha256=sha256(os.path.join(VOICE_DIR, name, "%02d.wav" % p["cue"])),
                 final_minus_bed_db=round(rms_db(final, SR, a, b) - rms_db(bed_only, SR, a, b), 1))
        res["cues"].append(p)
    return res


def reels_cut(workdir):
    """brand/vsl-15s-vertical-reels.mp4: the vertical with its voice-free bed, for Instagram Reels."""
    name = "vsl-15s-vertical"
    out = os.path.join(BRAND, name + "-reels.mp4")
    tmp = os.path.join(workdir, name + "-reels.mp4")
    ff("-i", os.path.join(BRAND, name + ".mp4"), "-i", os.path.join(VOICE_DIR, name + ".music.m4a"),
       "-map", "0:v:0", "-map", "1:a:0", "-c", "copy", "-movflags", "+faststart", "-map_metadata", "-1", tmp)
    os.replace(tmp, out)
    return {"mp4": os.path.basename(out), "sha256": sha256(out), "audio": "music bed only, no voice",
            "video_md5": video_md5(out)}


# ---- site export ----------------------------------------------------------------------------------------------
def gray_mean(jpg):
    """Mean 8-bit luma of an image, through ffmpeg (a 64x36 gray thumbnail)."""
    p = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", jpg, "-vf", "scale=64:36,format=gray",
                        "-f", "rawvideo", "-"], capture_output=True, check=True)
    return sum(p.stdout) / len(p.stdout)


def web(manifest, workdir):
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
           "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", "-map_metadata", "-1",
           "-metadata", "title=" + video["title"], tmp)
        how = "re-encoded from brand/%s.mp4 at crf 23 to fit %d bytes, sound copied" % (WEB_NAME, WEB_MAX_BYTES)
    if os.path.getsize(tmp) > WEB_MAX_BYTES:
        raise SystemExit("web export is %d bytes, over %d" % (os.path.getsize(tmp), WEB_MAX_BYTES))
    os.replace(tmp, WEB_MP4)
    a, b = beat_start(video, POSTER_BEAT)
    poster_ms = b - 200                                     # the beat's last moment: every restore line is on screen
    ff("-ss", "%.3f" % (poster_ms / 1000), "-i", src, "-frames:v", "1", "-q:v", "3", WEB_POSTER)
    narrated = bool(manifest.get("narration", {}).get("videos", {}).get(WEB_NAME))
    return {"mp4": os.path.relpath(WEB_MP4, BRAND), "sha256": sha256(WEB_MP4), "bytes": os.path.getsize(WEB_MP4),
            "from": how, "source_sha256": sha256(src), "voice": narrated,
            "poster": os.path.relpath(WEB_POSTER, BRAND), "poster_ms": poster_ms, "poster_beat": POSTER_BEAT,
            "poster_sha256": sha256(WEB_POSTER), "poster_mean_luma": round(gray_mean(WEB_POSTER), 1)}


def load_manifest():
    with open(os.path.join(HERE, "manifest.json"), encoding="utf-8") as f:
        return json.load(f)


def save_manifest(manifest):
    with open(os.path.join(HERE, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
        f.write("\n")


def main(argv):
    if not argv or argv[0] not in ("mix", "jobs", "web"):
        print(__doc__)
        return 2
    if argv[0] == "jobs":
        for row in cue_jobs():
            print("%s #%d %s" % (row[0], row[1], row[5]))
        return 0
    work = os.path.join(ROOT, "build", "narration")
    os.makedirs(work, exist_ok=True)
    manifest = load_manifest()
    if argv[0] == "mix":
        with open(VOICE_LOCK, encoding="utf-8") as f:
            lock = json.load(f)["grc_voice_A"]
        narration = {"voice": "John B Joseph's cloned voice, studio Voice A (VOICE_LOCK.json grc_voice_A, approved by "
                              "John %s; use on product VSLs approved by John 2026-11-12)" % lock["approved_on"],
                     "engine_sha256": lock["engine_sha256"], "reference_sha256": lock["reference_sha256"],
                     "synth_report": "vsl/voice/report.json", "videos": {}}
        for video in vsl.beats()["videos"]:
            cues = units(video)
            narration["videos"][video["name"]] = r = mix_video(video, cues, work)
            v = manifest["videos"][video["name"]]
            v["audio"] = {"voice": "narration: see narration.videos.%s" % video["name"],
                          "music": v["audio"]["music"].split("; ducked")[0] + "; ducked under the voice",
                          "measured": r["measured"],
                          "master": "loudnorm=I=%.1f:TP=%.1f" % (MASTER[video["aspect"]], TRUE_PEAK - 0.5)}
            v["mp4_facts"]["sha256"] = r["mp4_sha256"]
            v["mp4_facts"]["bytes"] = os.path.getsize(os.path.join(BRAND, video["name"] + ".mp4"))
            print("%s: %s, voice over bed %.1f dB, tempos %s, overruns %s" % (
                video["name"], r["measured"], r["voice_over_music_rms_db_while_talking"],
                [c["tempo"] for c in r["cues"]], [c["overrun_ms"] for c in r["cues"] if c["overrun_ms"]]))
        narration["reels"] = reels_cut(work)
        manifest["narration"] = narration
    manifest["web"] = web(manifest, work)
    print("web: %s" % json.dumps(manifest["web"], sort_keys=True))
    save_manifest(manifest)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
