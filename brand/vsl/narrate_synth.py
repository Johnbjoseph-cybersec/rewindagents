"""Make one narration clip per spoken unit (caption cues joined into whole sentences, narration.units) in John's cloned voice (task RB4d), in the studio's voice venv:

  ~/ai-creative-studio/.venv-voice/bin/python ~/fire/rewindagent/brand/vsl/narrate_synth.py [--only NAME] [--force]

Voice A exactly as locked in ai-creative-studio voice/VOICE_LOCK.json grc_voice_A: the engine voice/synth.py and
the lock's reference recording are checked against their pinned sha256 first (a mismatch stops the run), the synth
args are the lock's, and the take is chosen the way voice/synth_verified.py chooses it (imported, not copied):
every take is transcribed and scored for word errors against the spoken text, a failing take is retried, and the
passing take with the fewest errors, then the best pitch score, is kept. The studio's voice files are only read.

Writes brand/vsl/voice/<name>/<nn>.wav (mono, 16-bit, the take as generated plus the engine's room tone) and
brand/vsl/voice/report.json (spoken text, what the recogniser heard, word error rate, takes). A clip whose spoken
text has not changed is kept unless --force. Then: python3 ~/fire/rewindagent/brand/vsl/narration.py mix
"""
import hashlib
import json
import os
import sys

STUDIO = os.path.expanduser("~/ai-creative-studio")
# the Voice A engine lives in the studio cache; a global HF_HOME (e.g. the archive SSD cache) must not win, and the
# model must never be fetched at render time
os.environ["HF_HOME"] = os.path.join(STUDIO, ".models", "hf")
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ.setdefault("HF_HUB_OFFLINE", "1")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "voice")
MAX_WER = 0.12
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(STUDIO, "voice"))
sys.path.insert(0, os.path.join(STUDIO, "voice", "align"))

import narration  # noqa: E402  (the cue list and spoken forms; stdlib only)


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main(argv):
    only = argv[argv.index("--only") + 1] if "--only" in argv else None
    force = "--force" in argv
    with open(os.path.join(STUDIO, "voice", "VOICE_LOCK.json"), encoding="utf-8") as f:
        lock = json.load(f)["grc_voice_A"]
    engine = os.path.join(STUDIO, "voice", "synth.py")
    ref = os.path.join(STUDIO, lock["reference"])
    if sha256(engine) != lock["engine_sha256"] or sha256(ref) != lock["reference_sha256"]:
        raise SystemExit("Voice A is not the locked one: engine or reference sha256 differs from VOICE_LOCK.json")
    args = lock["synth_args"]
    ex, cfg, temp = (float(args[args.index(k) + 1]) for k in ("--exaggeration", "--cfg", "--temperature"))
    takes_n = int(lock["takes_per_sentence"])

    import torch
    import torchaudio
    import synth as S
    import synth_verified as V

    rpath = os.path.join(OUT, "report.json")
    report = {}
    if os.path.exists(rpath):
        with open(rpath, encoding="utf-8") as f:
            report = json.load(f)
    report["voice"] = {"lock": "VOICE_LOCK.json grc_voice_A", "engine_sha256": lock["engine_sha256"],
                       "reference_sha256": lock["reference_sha256"], "exaggeration": ex, "cfg": cfg,
                       "temperature": temp, "takes_per_sentence": takes_n, "max_wer": MAX_WER}
    clips = report.setdefault("clips", {})
    model = None
    for name, n, start, end, caption, said in narration.cue_jobs():
        if only and name != only:
            continue
        key = "%s/%02d" % (name, n)
        wav_path = os.path.join(OUT, name, "%02d.wav" % n)
        if not force and os.path.exists(wav_path) and clips.get(key, {}).get("spoken") == said:
            continue
        if model is None:
            model = S.ChatterboxTTS.from_pretrained(device="mps")
        sr = model.sr
        parts, rows = [], []
        sentences = S.split_sentences(said)
        prev_hz = None
        for i, sentence in enumerate(sentences):
            takes = []

            def make(t):
                wav = model.generate(sentence, audio_prompt_path=ref, exaggeration=ex, cfg_weight=cfg,
                                     temperature=temp + 0.04 * (t % takes_n))
                m = S.measure(wav, sr, sentence)
                heard = V.asr(wav, sr)
                e, nw = V.word_errors(sentence, heard)
                tr = V.truncated(wav, sr, sentence)
                return {"take": t, "wav": wav, "m": m, "score": S.score(m, prev_hz), "wer": e / nw, "errors": e,
                        "heard": heard, "truncated": tr, "ok": (e == 0 or e / nw <= MAX_WER) and not tr}

            for t in range(takes_n):
                takes.append(make(t))
            t = takes_n
            while not any(r["ok"] for r in takes) and t < takes_n + 3:
                takes.append(make(t))
                t += 1
            pool = [r for r in takes if r["ok"]] or takes
            best = min(pool, key=lambda r: (r["wer"], -r["score"]))
            prev_hz = best["m"]["median_hz"] if best["m"] else prev_hz
            parts.append(best["wav"].cpu())
            if i < len(sentences) - 1:
                parts.append(torch.zeros(1, int(sr * 0.3)))
            rows.append({"sentence": sentence, "take": best["take"], "wer": round(best["wer"], 3),
                         "heard": best["heard"], "asr_fail": not best["ok"],
                         "takes": [{"take": r["take"], "wer": round(r["wer"], 3), "truncated": r["truncated"],
                                    "score": round(r["score"], 2), "heard": r["heard"]} for r in takes]})
        audio = torch.cat(parts, dim=-1)
        g = torch.Generator().manual_seed(n)
        tone = torch.randn(audio.shape, generator=g)
        tone = torchaudio.functional.lowpass_biquad(tone, sr, 3000) * (10 ** (S.ROOM_TONE_DBFS / 20))
        os.makedirs(os.path.dirname(wav_path), exist_ok=True)
        torchaudio.save(wav_path, (audio + tone).clamp(-1, 1), sr, encoding="PCM_S", bits_per_sample=16)
        clips[key] = {"caption": caption, "spoken": said, "cue_ms": [start, end], "sentences": rows,
                      "seconds": round(audio.shape[-1] / sr, 3), "wav_sha256": sha256(wav_path)}
        print("%s %.2f s for a %.2f s cue%s" % (key, audio.shape[-1] / sr, (end - start) / 1000,
                                                "  ASR-FAIL" if any(r["asr_fail"] for r in rows) else ""),
              flush=True)
        os.makedirs(OUT, exist_ok=True)
        with open(rpath, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=1, sort_keys=True)
            f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
