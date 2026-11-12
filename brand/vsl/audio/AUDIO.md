# rewindagents VSL audio (text-only films, no voice over)

Made 2026-11-12 by Sana Qureshi (Creative Studio sound). Replaces the sine pad + metronome in `render.py score()`.
Generator: `~/ai-creative-studio/studio/sound_rewind_bed.py` (deterministic, numpy/scipy only, uses `studio/sound_dsp.py` for the
true-peak limiter and meters). Card times read from `brand/vsl/beats.json` as of md5 3630c3d4 (22 cards, 90.0 s).
Format: 48 kHz, 24-bit PCM stereo WAV. Not listened to by a human (no ears here): judged by measurement, spectrogram and level traces.

## Files and measurements (ffmpeg ebur128 peak=true, astats)

| file | length | target | integrated | true peak | LRA | LRA low/high | energy above 2 kHz (HP 2 kHz, LUFS) |
|---|---|---|---|---|---|---|---|
| bed-vsl-90s.wav | 90.000 s | -16 | -16.0 LUFS | -1.9 dBTP | 10.4 LU | -21.5 / -11.1 | -22.1 (above 8 kHz: -27.3) |
| bed-vsl-30s.wav | 29.550 s | -16 | -16.0 LUFS | -1.9 dBTP | 12.4 LU | -23.1 / -10.7 | -18.1 (above 8 kHz: -22.2) |
| bed-vsl-15s-vertical.wav | 14.000 s | -14 | -14.0 LUFS | -1.9 dBTP | 9.9 LU | -20.5 / -10.6 | -18.1 (above 8 kHz: -22.1) |
| sfx-rewind.wav | 0.900 s | - | - | peak -8.0 dBFS | - | - | - |
| sfx-tick.wav | 0.090 s | - | - | peak -12.0 dBFS | - | - | - |

Lengths follow the current beats.json totals (90.00 / 29.55 / 14.00 s), not the nominal 90/30/15. If a render's total changes, re-run
the generator (below) so the resolve and the fade still land on the last frame.

Per-file checks (all three beds): sample 0 is exactly 0.0 and the fade-in is a raised-cosine over 0.8 s (0.5 s for the 15 s), first
sample above -60 dBFS at 73 / 75 / 24 ms; last non-zero sample at 89.921 / 29.478 / 13.928 s, so the final 79 / 72 / 72 ms are exact digital
silence; DC offset below 2e-5; peak -1.9 dBFS. Level traces (3 s LUFS windows) are in the table below.

Short-term loudness (3 s window centred on t) shows the arc:
- 90 s: 1 s -24, 10 s -21, 19 s -21 | lift 22 s -16, 40 s -14 | question 46 s -19 | payoff 52 s -10, 58 s -12 | break 64-73 s -18 | bridge 79 s -17 | close 85 s -19, 88 s -24.
- 30 s: 1 s -24, 7 s -22 | build 10 s -16, 16 s -18 | payoff 19 s -11, 22 s -12 | close 25 s -19.
- 15 s: 1 s -22 | payoff 4 s -10, 7 s -13 | close 10 s -18.

Band shares of power (Welch), 90 s: below 250 Hz -2.4 dB, 250-2 kHz -4.7, 2-8 kHz -12.0, above 8 kHz -18.1 (30 s: -9.7 and -15.1; 15 s: -10.5 and -14.6).
The 90 s bed is the darkest because the tension, break and close acts are deliberately pad-led; the payoff and lift acts carry hats, shaker,
bright plucks, bells and the impact air. This is the weakest number against "full band": energy above 2 kHz is real but 22 LU under total on the 90 s.

## Sections (90 s film) and edit points

Each section owns a whole number of bars (tempo = 240 x bars / length), so it ends on a bar line exactly at the next card start. Pad notes
cross-fade over 0.8 s and hits/bells ring across the boundary, so section edges overlap-add with no seam. The edit point is the section start.

| # | section | start - end (s) | cards | bars @ bpm | chords | what plays |
|---|---|---|---|---|---|---|
| 1 | tension (the problem) | 0.00 - 23.60 | hook .. "Claude Code's docs" | 9 @ 91.5 | Am Am Fmaj7 Esus (x2, ends Esus) | low A drone with a minor-second shadow swelling every other bar, soft wood tick on beats 2/4 and sub pulse from "deleted your tests" (3.30), sparse low pluck from "Can you get them back" (7.65), high glints from "Why can't git" (14.95); dark noise+tone riser over the last 2.6 s |
| 2 | lift (the idea) | 23.60 - 43.90 | "flight recorder" .. "Before each edit" | 8 @ 94.6 | C G Am Fmaj7 (x2) | soft landing hit + A6 bell at 23.60, open pad, 8th plucks with ping-pong delay, bass + hats from "keeps every move" (27.55), kick from "how does rewindagents record" (31.80), shaker from "hash-chained" (35.35), 16th arpeggio from "Before each edit" (39.45); short riser last 1.4 s |
| 3 | question + build | 43.90 - 52.60 | "which step", "Twelve, because" | 3 @ 82.8 | Am Fmaj7 Esus | stripped back: pad + sparse plucks, sub pulse from "Twelve" (49.40), bright 2.5 s riser into the payoff (unresolved Esus) |
| 4 | payoff (rewind 12, four files back) | 52.60 - 61.35 | "four files come back", "Even the rewind" | 3 @ 82.3 | Aadd9 Dmaj7 A | RESOLVE at 52.60: impact + three bells (A6 E6 A5) landing on A major (the tension was A minor), kick, snap, 16th arpeggio, hats, shaker, open pad |
| 5 | break + recap (warm) | 61.35 - 79.20 | "Where does the analogy break" .. "You can now see" | 7 @ 94.1 | Dmaj7 A Bm7 E (x2) | settles 3-4 LU under the payoff: pad, bass, 8th plucks, hats from "Unlike a recorder" (65.85), kick and shaker later; small bell at 61.35 |
| 6 | bridge | 79.20 - 84.20 | "Apache-2.0..." | 2 @ 96.0 | Dmaj7 A | pad, bass, plucks, light hats |
| 7 | close (end card) | 84.20 - 90.00 | "Your editor has had undo" | 2 @ 82.8 | Dmaj7 Aadd9 | drums stop, pad + slow plucks + two bells, long reverb tail, cosine fade over the last 3.4 s to digital silence at 89.92 |

30 s film (29.55 s): tension 0.00-10.80 (4 bars, Am Fmaj7 Am Esus), question + build 10.80-19.50 (3 bars, C G Esus; riser 2.4 s), payoff +
warm close 19.50-29.55 (4 bars, Aadd9 Dmaj7 A Aadd9; full payoff for 2 bars to the "editor has had undo" card at 23.75, then pad + plucks, fade over the last 3.2 s).
15 s vertical (14.00 s): cold-open tension 0.00-3.45 (1 bar, drone + pulse + riser 1.9 s into the hit), payoff + close 3.45-14.00 (4 bars, same as the 30 s payoff; drums to 8.20, fade over the last 3.0 s).
Full per-section data (bars, bpm, chords, layer bar ranges) is in `sections.json` (written by the generator).

## When card times move (the next render)

Section starts are found by card text, not by id, so a renumbered beats.json still works. Re-run (about 1 minute, nice 10):

    nice -n 10 ~/ai-creative-studio/.venv-voice/bin/python ~/ai-creative-studio/studio/sound_rewind_bed.py \
        --beats ~/fire/rewindagent/brand/vsl/beats.json --out ~/fire/rewindagent/brand/vsl/audio
    # a card start that the renderer measured differently, in ms:  --starts "vsl-90s:b14=55000,b07=25000"   (only: --only vsl-90s)

Anchor names (b02, b07, b12, b14, ...) are the legacy ids and map to card text in ALIASES inside the script. A shift of a few seconds keeps
the bed in time (tested: b14 +2.4 s and b07 +1.4 s rebuilt without error). If you only trim by under about 0.5 s, cut at the section start and use a 0.4 s crossfade.

## SFX layer (kept separate, not in the beds)

- `sfx-rewind.wav` (0.90 s, peak -8 dBFS, integrated -19 LUFS): tape-style falling noise/tone sweep (7.5 kHz to 260 Hz) with a wow flutter and a
  tick train that slows and stops 120 ms before the landing at 0.72 s (click + soft thump + A5 bell; round 3). Place it so the LANDING (0.72 s into the file) meets the wipe's end:
  start = wipe_end - 0.72 s.
- `sfx-tick.wav` (90 ms, peak -12 dBFS): firm card-change tick (1.85 kHz body, 3.1 kHz, noise click). Starts at zero, fade-out to zero.
- Both are 48 kHz 24-bit stereo, start and end at exactly 0.

Mix advice (measured on a test mix of bed-vsl-90s + a tick on all 22 cards + two sweeps at unity gain): the sum peaks at +0.8 dBTP because the
ticks and the sweep land on bed peaks, with integrated -16.0 LUFS. Run the final audio through a limiter:
`-af alimiter=limit=0.76:attack=5:release=50:level=0` gave -16.0 LUFS (unchanged to 0.1), -1.9 dBFS true peak, LRA 9.5 on that test mix
(limit=0.80 gave -1.4, which fails -1.5: ebur128 true peak reads about 0.5 dB over the sample peak). Check with `ebur128=peak=true`
on the muxed file. For -14 LUFS vertical raise the bed, not the SFX, and keep the same limiter.

## Sources and licences

No third-party audio, sample, loop or download. Every sound (pad, drone, bass, plucks, bells, drums, risers, impacts, SFX) is generated by
`sound_rewind_bed.py` from sines, additive saw partials and filtered noise with fixed seeds; reverb is a synthetic noise impulse response
(`sound_dsp.ir`). Licence `original` (our own work, no third-party rights, nothing registered with Content ID). Attribution owed: none.
Recorded in `~/ai-creative-studio/audio/LICENSES.md` (section "rewindagents VSL bed").

## Round 3 (2026-11-12, Sana Qureshi; Quinn r2 audio row 8.0, fix 3)

Changes in `sound_rewind_bed.py`: (1) the hook act now has a quiet heartbeat (lub-dub, 60-118 Hz thump with 2nd/3rd harmonic, every beat) from
0.04 s, a wood tick from bar 0, a 5-12 kHz air swell from bar 1 (2.6 s in the 90 s), sparse low plucks from bar 1 and glints from bar 2 (they were
3.3 / 7.65 / 14.95 s before); the fade-in is now 0.15 s (was 0.8 s) so the first thump is heard, sample 0 is still exactly 0.0. (2) The first level points are
raised 3.7-4.0 dB over the hook (see table). (3) The break and the close are 1-1.5 dB lower so LRA stays at 8 or more. (4) `sfx-rewind.wav` has no tick
inside the last 120 ms and a 12 ms broadband click at exactly 0.720 s, so the landing is also the file's highest >4 kHz event. (5) `--only` no longer
overwrites sections.json (it merges). (6) Determinism, below. A-minor tension to A-major payoff at the restore is unchanged (52.60 s, Aadd9).

Measured (ffmpeg ebur128 peak=true on the files in this folder; short-term = 3 s window centred on t, zero-padded before 0, same method as the table above):

| file | integrated | true peak | LRA | LRA low / high | hook act short-term (t = 1, 2, 3, 4, 5, 6, 7, 7.65 s) | round 2 hook (same method) |
|---|---|---|---|---|---|---|
| bed-vsl-90s.wav | -16.0 LUFS | -1.9 dBTP | 8.1 LU | -19.4 / -11.3 | -19.7, -18.9, -18.4, -18.1, -17.9, -17.5, -17.5, -17.7 | -23.7, -22.8, -22.2, -21.9, -21.9, -21.6, -21.5, -21.6 |
| bed-vsl-30s.wav | -16.0 LUFS | -1.9 dBTP | 9.1 LU | -20.1 / -11.0 | -20.1, -19.5, -18.8, -18.8, -18.7, -18.6, -18.2, -18.3 | about -24 to -22 |
| bed-vsl-15s-vertical.wav | -14.0 LUFS | -1.9 dBTP | 10.3 LU | -21.0 / -10.7 | cold open -18.1 at 1 s, -13.7 at 2 s, -10.5 at 4 s (the hit is at 3.45 s) | -22 at 1 s |

The 90 s hook is 3.7 to 4.0 dB louder than round 2 (target 3-4 dB). Hook (0-7.65 s) power share above 2.4 kHz was -54 dB, now -16.5 dB (above 5 kHz -16.9 dB).
Bed + SFX test mix (bed + every manifest sweep at its renderer weight 0.35 / 0.55 / 1.0 + every manifest tick at 0.8, through the renderer's
`alimiter=limit=0.76:attack=5:release=50:level=0`): 90 s -16.0 LUFS, -1.9 dBTP, LRA 7.8 (the SFX fill the quiet moments, so the mixed LRA is 0.3 under the bed's);
30 s -15.9 / -1.8 / 8.9; 15 s -14.0 / -1.9 / 10.3. The first 8 s of the 90 s mix reads -19.2, -18.6, -18.3, -18.1, -17.9, -17.5, -17.4, -17.6. Clean start and
end are unchanged: sample 0 = 0.0 on all three, first sample above -60 dBFS at 18.6 / 18.6 / 6.2 ms, last non-zero sample at 89.920 / 29.478 / 13.928 s, DC under 1.1e-5.
Resolved hook layers (bars of the act): 90 s 9 bars @ 91.5 bpm, heart 0-9, tick 0-9, drone 0-9, air 1-9, pulse 1-9, pluck4 1-9, glint 2-9; 30 s 4 bars @ 88.9, same
shape; 15 s 1 bar @ 69.6, everything on from bar 0.

Sweep offsets (document of the hit): `sfx-rewind.wav` lands at LAND_S = 0.720 s into the file (click starts at 0.720 s, thump and A5 bell attack at 0.720 s, 5 ms-smoothed
>4 kHz envelope peak at 0.7225 s, full-band peak at 0.729 s). render.py puts the file at `ms - 720` where `ms` is the manifest's `sweeps_ms`, i.e. the wipe's end
(card start + wipe ms). Checked against the current manifest.json (beats sha 01088f27): all 17 / 6 / 3 sweeps (90 s / 30 s / 15 s) land at manifest ms + 2.5 ms on a sweeps-only
stem (that 2.5 ms is the detector's smoothing), and every wipe end listed in the beats (14 / 4 / 2 wipes: b04 11250, b10 35800 and the rest) equals a sweep ms exactly (gap 0 ms).
So the renderer's placement and the file's landing agree to under 3 ms. The 0.10-0.14 s early reading at b04 and b10 (light wipes, weight 0.35, 9 dB under the story sweep)
was not the thump: the old file's tick train ran to 0.70 s and the bed's hats and bells sit in the same >4 kHz band, so a peak picker found a tick or a hat instead of the landing. The ticks inside the last 120 ms are gone, and
the click makes the landing the highest >4 kHz event in the file (the old file's whole-file >4 kHz maximum was at 0.23 s, the new one's is at 0.7225 s). Nothing for render.py to change on
this point; if Quinn still reads 0.1 s early on a light wipe in the next render, send the exact detector and the mixed track so it can be reproduced.
Two sweeps in the manifest are not wipe ends (90 s: 50150 and 54434 and 74700; 30 s: 17050 and 21334; 15 s: 5284): they are the ruler's scrub-back and the rewind command's enter, by design.

Determinism: the generator draws only from `np.random.default_rng` with fixed seeds (SEED = 42 for the bed, fixed seeds inside every voice, 300 + bar for the air, 23 for the click,
7 for the reverb IR); there is no time, os or `random` use, no dither, and the cache only stores deterministic arrays. Checked: two runs in separate processes from different working directories (one from `/`)
gave identical sha256 on all five audio files and sections.json, and the run that wrote this folder matches them. Same numpy/scipy/ffmpeg-free path (soundfile writes 24-bit PCM); a different numpy or scipy
version could change low bits, so the repo test should pin the environment (`~/ai-creative-studio/.venv-voice`).

| file | sha256 (round 3) |
|---|---|
| bed-vsl-90s.wav | 4dfabfdb9e951018bab9d7936979e98ed7f90572809073ad4e4e1b8ed750e979 |
| bed-vsl-30s.wav | abd04e3dd5dcd6b1b1b4ecfeaf2d72cd2874db392ce59c11cfbf3e94049b5ba5 |
| bed-vsl-15s-vertical.wav | 100f8257dc455130d97681ea000870628f6a4fe0c8bf82f769ccfcf70a3efe84 |
| sfx-rewind.wav | 930a2c56f29a0c4d3df3c9ce544d58b96553407d3ea590a6ef7568b8b38c3c08 |
| sfx-tick.wav | e4fc16617cd90919f3112c3a56fd622cc73c68dbb5723fd152d23529cf17138a |
| sections.json | 009822aba5d7b50367ae957d2edfd86612387a0f7718d5e15a278ad0edd92bd1 |

Card timings: sections are still fitted by card text (ALIASES), so b16/b17 shortening or b07/b12 beat moves only need a re-run; the sha256 above are for beats.json as it stands now.
Listening excerpt: `listen-excerpt.m4a` (30 s AAC 192k = 0-20 s and 48-58 s of the 90 s film, bed + sweeps + ticks at the renderer's weights and limiter, joined with 60 ms fades, about -15.7 LUFS, -2.4 dBFS peak).
It is built from the new bed on the current manifest times, not from a re-rendered film, so it is the sound the next render will carry.

## Still weak (be honest)

- Round 3: nobody has listened (I cannot). The heartbeat and the air swell were set by reasoning and metering; the 5-12 kHz swell is about -17 dB of the hook's power and could read as hiss on a laptop speaker. `listen-excerpt.m4a` is for John's ears. Chords, arpeggio patterns and levels were set by reasoning and metering; a human ear may want the plucks or the bell
  brighter or quieter. The tonal design (A minor tension, A major payoff) is the main creative bet.
- LRA is 10-12 LU, well over the 4 LU floor but wide for a bed under a silent film: the tension act sits about 10 LU below the payoff.
  If it reads too quiet in the first 20 s, raise the first points of `level` in plan_90 (a 2 dB change moves LRA about 1 LU).
- Tempo changes per section (83 to 96 bpm) because each section is fitted to whole bars; the drums restart on each section downbeat.
- The 90 s LRA is 8.1 alone and 7.8 with the SFX, just under Quinn's 'stay at 8 or more' once mixed; a 1 dB lower close or break would put it back.
- Above 8 kHz the 90 s bed is thin (-27 LUFS high-passed); the pad-led acts have little air.

## Render round 3 (2026-11-12, FIRE; review-textcut-r2.json fixes 4 and 6)

- The generator now lives in this repo: `make_bed.py` (round-3 `sound_rewind_bed.py`, source sha256 c1f57121...) and `sound_dsp.py`, with
  `requirements.txt` (numpy 1.26.4, scipy 1.17.1, pyloudnorm 0.2.0, soundfile 0.14.0) and `LICENSES.md`. The WAVs are git-ignored;
  `brand/vsl/render.py` runs `make_bed.py` when any is missing ($REWINDAGENTS_BED_PYTHON, else the running Python, else the studio venv).
  `tests/test_vsl_audio.py` regenerates into a temp dir and compares every file with the manifest's pinned sha256.
- Bit-deterministic as stated above, checked again on the repo copy: two runs in separate processes (cwd `/` and the scratch dir) gave identical
  sha256 for all five audio files and sections.json; the 30 s, 15 s and both SFX equal the round-3 table exactly.
- The 90 s card times moved (b06 +1.0 s, b07 +0.3 s for the roadmap beat, b12 +0.3 s, b16 -0.7 s, b17 -0.9 s; total still 90.0 s) and b16/b17
  have new text ("The analogy breaks: recorders can't undo a crash." / "This one puts your files back."), so `make_bed.py` carries those
  texts in ALIASES and the 90 s bed was regenerated: sections now start at 24.60 (lift), 45.20 (question), 54.20 (payoff), 62.95 (break),
  79.20, 84.20. bed-vsl-90s.wav sha256 82ef39914bec0d8e83cf9ca21ca7a0cc14cf1565518c007d40e65e8381d0a217, sections.json 0d66e301....
- Sweep placement unchanged in render.py: the landing (0.72 s) is put on each wipe's end, as this file's round-3 note says it should be.
- Still nobody has listened. listen-excerpt.m4a was made on the old card times (git-ignored, for John's ears).
