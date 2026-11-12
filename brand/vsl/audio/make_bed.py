"""Music bed + SFX for the rewindagents text-only product films (vsl-90s, vsl-30s, vsl-15s-vertical).

Everything is synthesised here from sines, saw partials and noise (licence `original`, no sample, no loop, no third-party
material). Deterministic (fixed seeds).

Vendored into the rewindagents repo on 2026-11-12 as brand/vsl/audio/make_bed.py (with sound_dsp.py beside it) from the
Creative Studio's studio/sound_rewind_bed.py, round 3 (source sha256 c1f57121e06e9b9bd3adf64476260fb49b11d04509b3f2a6b2d527f3c2b529a1),
so the films can be rebuilt from this repository: brand/vsl/render.py runs it when the WAVs are missing (they are not
committed). Licence note kept from the source: licence `original` (our own work, no sample, no loop, no third-party
material; see brand/vsl/audio/LICENSES.md). One change here: ALIASES carries the round-3 card text of b16/b17
("The analogy breaks", "This one puts your files back") beside the old text. Dependencies, pinned for bit-identical
output: brand/vsl/audio/requirements.txt.

Run with the studio venv (or any Python with requirements.txt installed):

  ~/ai-creative-studio/.venv-voice/bin/python ~/ai-creative-studio/studio/sound_rewind_bed.py \
      --beats ~/fire/rewindagent/brand/vsl/beats.json --out ~/fire/rewindagent/brand/vsl/audio [--only vsl-90s]
      [--starts vsl-90s:b07=23300,b13=47750]      # override a card start in ms when the render timings moved

Each film is built as sections (one per story act). A section owns a whole number of bars: its tempo is
240*bars/length so the section ends exactly on a bar line at the next card start. Sections overlap-add (pad notes
cross-fade over 0.8 s, hits and bells ring across the edit point), so a section can be moved by re-running with new
card starts without audible seams. SFX (rewind sweep, tick) are written separately, never mixed into the bed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy import signal
from scipy.interpolate import PchipInterpolator

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sound_dsp as dsp  # noqa: E402

SR = 48000
SEED = 42   # the only seed the bed builder draws from; every other noise source below has its own fixed seed
NOTE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
TYPES = {"m": [0, 3, 7], "m7": [0, 3, 7, 10], "mb9": [0, 1, 3, 7], "": [0, 4, 7], "maj7": [0, 4, 7, 11],
         "add9": [0, 4, 7, 14], "sus": [0, 5, 7], "7": [0, 4, 7, 10]}


def hz(m):
    return 440.0 * 2 ** ((np.asarray(m, dtype=float) - 69) / 12)


def parse_chord(name):
    """'Am' -> root pc 9 ; returns (pc, intervals)."""
    pc = NOTE[name[0]] + (1 if name[1:2] == "#" else 0)
    typ = name[2:] if name[1:2] == "#" else name[1:]
    return pc, TYPES[typ]


def bass_midi(pc, low=28):
    m = low + ((pc - low) % 12)
    return m


def pool(pc, ints, lo=60, hi=88):
    pcs = {(pc + i) % 12 for i in ints}
    return [m for m in range(lo, hi + 1) if m % 12 in pcs]


def padnotes(pc, ints):
    base = 48 + ((pc - 48) % 12)
    out = [base + i for i in ints]
    return out + [base + 12 + ints[0], base + 12 + ints[1]]


# ------------------------------------------------------------------ voices
def smooth_env(n, att, rel, sr=SR):
    e = np.ones(n)
    a, r = int(att * sr), int(rel * sr)
    if a:
        e[:a] = np.sin(0.5 * np.pi * np.arange(a) / a) ** 2
    if r:
        e[n - r:] *= np.cos(0.5 * np.pi * np.arange(r) / r) ** 2
    return e


_cache = {}


def saw_stack(f, n, K, detune_cents, phase=0.0):
    t = np.arange(n) / SR
    f = f * 2 ** (detune_cents / 1200)
    k = max(1, min(K, int(7000 / f)))
    ph = 2 * np.pi * f * t + phase
    s = np.zeros(n)
    for h in range(1, k + 1):
        s += np.sin(h * ph) / h ** 1.15
    return s


def pad_note(m, dur, K, att=0.8, rel=0.8):
    n = int(dur * SR)
    L = saw_stack(hz(m), n, K, -7, 0.3) + 0.6 * saw_stack(hz(m), n, K // 2, 3, 1.1)
    R = saw_stack(hz(m), n, K, 7, 2.0) + 0.6 * saw_stack(hz(m), n, K // 2, -3, 0.2)
    e = smooth_env(n, att, rel)
    return np.stack([L * e, R * e], 1) * 0.045


def pluck(m, dur=0.9, bright=1.0):
    key = ("pl", m, round(bright, 2))
    if key in _cache:
        return _cache[key]
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = hz(m)
    s = np.zeros(n)
    for h in range(1, 17):
        if f * h > 14000:
            break
        tau = 0.30 / (1 + 0.55 * h) * (0.8 + 0.4 * bright)
        a = (1 / h ** 0.9) * (1.0 if h < 9 else bright)
        s += a * np.sin(2 * np.pi * f * h * t * (1 + 0.0002 * h * h)) * np.exp(-t / tau)
    rng = np.random.default_rng(m)
    tr = dsp.hpf(rng.standard_normal(n), 3500) * np.exp(-t / 0.004) * 0.25 * bright
    s = (s + tr) * np.minimum(1, t / 0.0015)
    s *= np.cos(0.5 * np.pi * np.clip((t - (dur - 0.1)) / 0.1, 0, 1)) ** 2
    _cache[key] = s * 0.12
    return _cache[key]


def bell(m, dur=3.2, amp=1.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = hz(m)
    s = np.zeros(n)
    for r, a, tau in [(1, 1.0, 1.4), (2.0, 0.45, 0.9), (2.76, 0.5, 0.7), (4.07, 0.28, 0.45), (5.4, 0.25, 0.35),
                      (8.93, 0.14, 0.2), (13.3, 0.07, 0.12)]:
        if f * r < 15000:
            s += a * np.sin(2 * np.pi * f * r * t) * np.exp(-t / tau)
    s *= np.minimum(1, t / 0.002) * np.cos(0.5 * np.pi * np.clip((t - (dur - 0.4)) / 0.4, 0, 1)) ** 2
    return s * 0.09 * amp


def sub_note(m, dur, amp=1.0, att=0.01):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = hz(m)
    s = np.sin(2 * np.pi * f * t) + 0.25 * np.sin(4 * np.pi * f * t) + 0.08 * np.sin(6 * np.pi * f * t)
    e = np.minimum(1, t / att) * np.exp(-t / (dur * 0.7)) * smooth_env(n, 0, 0.05)
    return s * e * 0.30 * amp


def kick(amp=1.0):
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    f = 46 + 90 * np.exp(-t / 0.022)
    ph = 2 * np.pi * np.cumsum(f) / SR
    s = np.sin(ph) * np.exp(-t / 0.16) * np.minimum(1, t / 0.0008)
    rng = np.random.default_rng(3)
    s += 0.22 * dsp.lpf(rng.standard_normal(n), 2500) * np.exp(-t / 0.004)
    return s * 0.55 * amp


def hat(seed, open_=False, amp=1.0):
    key = ("hat", seed, open_)
    if key in _cache:
        return _cache[key] * amp
    n = int((0.16 if open_ else 0.07) * SR)
    t = np.arange(n) / SR
    rng = np.random.default_rng(100 + seed)
    s = dsp.hpf(rng.standard_normal(n), 6500, order=3) * np.exp(-t / (0.06 if open_ else 0.018))
    s *= np.minimum(1, t / 0.0008)
    _cache[key] = s * 0.11
    return _cache[key] * amp


def shaker(seed):
    key = ("sh", seed)
    if key not in _cache:
        n = int(0.11 * SR)
        t = np.arange(n) / SR
        rng = np.random.default_rng(200 + seed)
        s = dsp.bpf(rng.standard_normal(n), 4500, 11000, order=2) * np.sin(np.pi * np.clip(t / 0.11, 0, 1)) ** 2
        _cache[key] = s * 0.10
    return _cache[key]


def heartbeat(amp=1.0):
    """Soft lub-dub: two short low thumps (pitch falling 118 -> 60 Hz, a 2nd/3rd harmonic so small speakers hear it) 0.22 s apart."""
    n = int(0.55 * SR)
    t = np.arange(n) / SR

    def thump(at, g):
        f = 60 + 58 * np.exp(-t / 0.035)
        ph = 2 * np.pi * np.cumsum(f) / SR
        s = (np.sin(ph) + 0.35 * np.sin(2 * ph) + 0.12 * np.sin(3 * ph)) * np.exp(-t / 0.075) * np.minimum(1, t / 0.004)
        out = np.zeros(n)
        i = int(at * SR)
        out[i:] = s[: n - i] * g
        return out
    return (thump(0.0, 1.0) + thump(0.22, 0.62)) * 0.34 * amp


def air_swell(dur, seed):
    """Quiet band-passed noise swell (5-12 kHz), the only top-end in the hook act besides the ticks and glints."""
    n = int(dur * SR)
    rng = np.random.default_rng(seed)
    s = dsp.bpf(rng.standard_normal(n), 5000, 12000, order=2)
    e = np.sin(np.pi * np.arange(n) / n) ** 2
    return s * e * 0.07


def snap(amp=1.0):
    n = int(0.22 * SR)
    t = np.arange(n) / SR
    rng = np.random.default_rng(9)
    s = dsp.bpf(rng.standard_normal(n), 1400, 7000) * np.exp(-t / 0.05) * 0.5
    s += 0.4 * np.sin(2 * np.pi * 190 * t) * np.exp(-t / 0.03)
    return s * np.minimum(1, t / 0.001) * 0.25 * amp


def woodtick(amp=1.0):
    n = int(0.06 * SR)
    t = np.arange(n) / SR
    s = np.sin(2 * np.pi * 1450 * t) * np.exp(-t / 0.012) + 0.5 * np.sin(2 * np.pi * 2210 * t) * np.exp(-t / 0.008)
    return s * np.minimum(1, t / 0.001) * 0.10 * amp


def glint(m):
    n = int(2.4 * SR)
    t = np.arange(n) / SR
    f = hz(m)
    s = np.sin(2 * np.pi * f * t) * np.exp(-t / 0.7) + 0.35 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t / 0.4)
    s += 0.12 * np.sin(2 * np.pi * 3.01 * f * t) * np.exp(-t / 0.25)
    return s * np.minimum(1, t / 0.002) * np.cos(0.5 * np.pi * np.clip((t - 2.0) / 0.4, 0, 1)) ** 2 * 0.06


def sweep_noise(dur, f0, f1, seed=1, bands=18):
    """Band-limited noise whose centre frequency moves f0 -> f1 (log), built by cross-fading fixed band-passes."""
    n = int(dur * SR)
    t = np.linspace(0, 1, n)
    rng = np.random.default_rng(seed)
    nz = rng.standard_normal(n)
    centres = np.geomspace(min(f0, f1), max(f0, f1), bands)
    pos = np.log(centres / min(f0, f1)) / np.log(max(f0, f1) / min(f0, f1))
    cur = (np.log(f0 / min(f0, f1)) / np.log(max(f0, f1) / min(f0, f1))) * (1 - t) + \
          (np.log(f1 / min(f0, f1)) / np.log(max(f0, f1) / min(f0, f1))) * t
    out = np.zeros(n)
    for c, p in zip(centres, pos):
        w = np.exp(-0.5 * ((cur - p) / (1.3 / bands)) ** 2)
        if w.max() < 0.02:
            continue
        out += dsp.bpf(nz, c / 1.35, min(c * 1.35, 21000), order=2) * w
    return out


def riser(dur, bright=1.0, seed=5):
    n = int(dur * SR)
    t = np.linspace(0, 1, n)
    amp = t ** 2.2
    nz = sweep_noise(dur, 350, 9000 * (0.6 + 0.4 * bright), seed)
    f = 160 * 2 ** (2.6 * t)
    tone = (np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.4 * np.sin(4 * np.pi * np.cumsum(f) / SR)) * 0.12
    s = (nz * 0.7 + tone) * amp
    return s * np.cos(0.5 * np.pi * np.clip((t - 0.985) / 0.015, 0, 1)) ** 2


def impact(scale=1.0, bright=1.0):
    n = int(3.6 * SR)
    t = np.arange(n) / SR
    f = 34 + 55 * np.exp(-t / 0.09)
    boom = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.9)
    rng = np.random.default_rng(11)
    wash = dsp.lpf(rng.standard_normal(n), 5000 * bright) * np.exp(-t / 0.45) * 0.30
    air = dsp.hpf(rng.standard_normal(n), 5000, order=2) * np.exp(-t / 0.25) * 0.22 * bright
    s = (boom * 0.6 + wash + air) * np.minimum(1, t / 0.0015) * np.cos(0.5 * np.pi * np.clip((t - 3.2) / 0.4, 0, 1)) ** 2
    return s * scale * 0.9


# ------------------------------------------------------------------ mixing helpers
class Bus:
    def __init__(self, n):
        self.x = np.zeros((n, 2))

    def add(self, sig, t, gain=1.0, pan=0.0):
        i = int(round(t * SR))
        if sig.ndim == 1:
            a = np.cos((pan + 1) * np.pi / 4)
            b = np.sin((pan + 1) * np.pi / 4)
            sig = np.stack([sig * a * 1.414, sig * b * 1.414], 1)
        if i >= len(self.x) or i + len(sig) <= 0:
            return
        lo = max(0, -i)
        hi = min(len(sig), len(self.x) - i)
        self.x[i + lo:i + hi] += sig[lo:hi] * gain


# ------------------------------------------------------------------ section engine
def render_section(sec, n_total, buses, rng):
    """Synthesise one section into the shared buses. sec keys: t0 t1 prog final layers bright hit riser."""
    t0, t1 = sec["t0"], sec["t1"]
    dur = t1 - t0
    N = sec["bars"] or max(1, int(round(dur / 2.609)))
    sec["bars"] = N
    bar = dur / N
    beat = bar / 4
    step = beat / 4
    sec["bpm"] = round(60 / beat, 2)
    chords = [sec["prog"][b % len(sec["prog"])] for b in range(N)]
    if sec.get("final"):
        chords[-1] = sec["final"]
    sec["chords"] = chords
    lay = {}
    for k, v in sec["layers"].items():
        on = 0 if v[0] is None else int(round((v[0] - t0) / bar))
        off = N if v[1] is None else int(round((v[1] - t0) / bar))
        lay[k] = (max(0, on), min(N, off))
    sec["layer_bars"] = {k: list(v) for k, v in lay.items()}

    def active(k, b):
        return k in lay and lay[k][0] <= b < lay[k][1]

    K = sec.get("bright", 10)
    amp = sec.get("amp", {})
    for b in range(N):
        tb = t0 + b * bar
        pc, ints = parse_chord(chords[b])
        bm = bass_midi(pc)
        if active("pad", b):
            for m in padnotes(pc, ints):
                buses["pad"].add(pad_note(m, bar + 0.8, K), tb - 0.4, amp.get("pad", 1.0))
        if active("drone", b):
            # dark root drone + a minor-second shadow that swells every other bar (tension)
            root = bm + 12
            buses["pad"].add(pad_note(root, bar + 0.8, 5), tb - 0.4, 1.2 * amp.get("drone", 1.0))
            buses["pad"].add(pad_note(root + 12, bar + 0.8, 4), tb - 0.4, 0.6 * amp.get("drone", 1.0))
            sw = pad_note(root + 13 if b % 2 == 0 else root + 7, bar + 0.8, 4, att=bar * 0.45, rel=bar * 0.45)
            buses["pad"].add(sw, tb - 0.4, (1.0 if b % 2 == 0 else 0.6) * amp.get("drone", 1.0))
        if active("bass", b):
            for st, ln in [(0, 5), (6, 3), (10, 3)] if sec.get("bass_pat", "full") == "full" else [(0, 12)]:
                buses["bass"].add(sub_note(bm, ln * step, amp.get("bass", 1.0)), tb + st * step)
        if active("pulse", b):
            for q in range(4):
                buses["bass"].add(sub_note(bm, 0.5, 0.9 * amp.get("pulse", 1.0), att=0.004) * (1 if q % 2 == 0 else 0.7),
                                  tb + q * beat)
        pl = pool(pc, ints)
        pat = [0, 2, 4, 2, 1, 3, 5, 3]
        if active("pluck4", b):
            for q in range(4):
                m = pl[(pat[q * 2 % 8] + b) % len(pl)] - (12 if sec.get("low_pluck") else 0)
                buses["pluck"].add(pluck(m, bright=sec.get("pl_bright", 0.8)), tb + q * beat,
                                   amp.get("pluck", 1.0) * (1.0 if q == 0 else 0.7), pan=(-0.3 if q % 2 else 0.3))
        if active("pluck8", b):
            for s in range(0, 16, 2):
                m = pl[(pat[(s // 2) % 8] + (b % 2)) % len(pl)]
                buses["pluck"].add(pluck(m, bright=sec.get("pl_bright", 0.9)), tb + s * step,
                                   amp.get("pluck", 1.0) * (1.0 if s % 4 == 0 else 0.62), pan=-0.5 + (s % 8) / 8)
        if active("pluck16", b):
            for s in range(16):
                m = pl[(pat[s % 8] + (s // 8)) % len(pl)]
                buses["pluck"].add(pluck(m, bright=sec.get("pl_bright", 1.0)), tb + s * step,
                                   amp.get("pluck", 1.0) * (1.0 if s % 4 == 0 else 0.55 if s % 2 == 0 else 0.4),
                                   pan=-0.6 + 1.2 * ((s * 5) % 16) / 16)
        if active("kick", b):
            for s in [0, 8] + ([6] if sec.get("kick_syn") else []) + ([14] if sec.get("kick_syn") else []):
                buses["drum"].add(kick(amp.get("kick", 1.0) * (0.8 if s in (6, 14) else 1.0)), tb + s * step)
        if active("snap", b):
            buses["drum"].add(snap(amp.get("snap", 1.0)), tb + 4 * step)
            buses["drum"].add(snap(amp.get("snap", 1.0)), tb + 12 * step)
        if active("hat8", b):
            for s in range(2, 16, 4):
                buses["drum"].add(hat(int(rng.integers(0, 5)), open_=(s == 14), amp=amp.get("hat", 1.0)), tb + s * step,
                                  pan=0.35)
            for s in range(0, 16, 4):
                buses["drum"].add(hat(int(rng.integers(0, 5)), amp=0.45 * amp.get("hat", 1.0)), tb + s * step, pan=-0.3)
        if active("hat16", b):
            for s in range(16):
                v = 1.0 if s % 4 == 2 else 0.55 if s % 2 == 0 else 0.33
                buses["drum"].add(hat(int(rng.integers(0, 5)), amp=v * amp.get("hat", 1.0)), tb + s * step,
                                  pan=0.4 if s % 2 else -0.4)
        if active("shaker", b):
            for s in range(16):
                buses["drum"].add(shaker(int(rng.integers(0, 4))), tb + s * step,
                                  amp.get("shaker", 1.0) * (1.0 if s % 4 == 2 else 0.5), pan=-0.5 if s % 2 else 0.5)
        if active("heart", b):
            for q in range(4):
                buses["bass"].add(heartbeat(amp.get("heart", 1.0) * (1.0 if q % 2 == 0 else 0.8)), tb + 0.04 + q * beat)
        if active("air", b):
            buses["pluck"].add(air_swell(bar, 300 + b), tb, amp.get("air", 1.0), pan=-0.4 if b % 2 else 0.4)
        if active("tick", b):
            for q in (1, 3):
                buses["drum"].add(woodtick(amp.get("tick", 1.0)), tb + q * beat + (rng.random() - 0.5) * 0.004,
                                  pan=0.5 if q == 1 else -0.5)
        if active("glint", b):
            seq = [pl[-1], pl[-3], pl[-2]]
            buses["pluck"].add(glint(seq[b % 3]), tb + 6 * step, amp.get("glint", 1.0), pan=0.6 if b % 2 else -0.6)

    # section-edge material
    h = sec.get("hit")
    if h:
        buses["hit"].add(impact(h["scale"], h.get("bright", 1.0)), t0 + h.get("at", 0.0))
        for k, m in enumerate(h.get("bells", [])):
            buses["pluck"].add(bell(m, amp=h.get("bell_amp", 1.0) * (1 - 0.15 * k)), t0 + h.get("at", 0.0) + 0.012 * k,
                               pan=(-0.4, 0.4, 0.0)[k % 3])
    r = sec.get("riser")
    if r:
        sig = riser(r["dur"], r.get("bright", 1.0))
        buses["hit"].add(sig, t1 - r["dur"], r.get("amp", 0.7))


def level_curve(points, n):
    ts, ds = zip(*points)
    f = PchipInterpolator(ts, ds)
    t = np.arange(n) / SR
    return 10 ** (f(np.clip(t, ts[0], ts[-1])) / 20)


def build_bed(plan, duration):
    n = int(round(duration * SR))
    tail = int(4 * SR)
    buses = {k: Bus(n + tail) for k in ["pad", "pluck", "drum", "bass", "hit"]}
    rng = np.random.default_rng(SEED)
    for sec in plan["sections"]:
        render_section(sec, n, buses, rng)
    beat0 = 60 / plan["sections"][min(2, len(plan["sections"]) - 1)]["bpm"]
    d = plan.get("delay_beat", beat0)
    pl = buses["pluck"].x
    pl_d = pl.copy()
    for k in range(1, 4):
        sh = int(0.75 * d * SR * k)
        tap = np.pad(dsp.lpf(pl[:, ::-1] if k % 2 else pl, 4800, order=1), ((sh, 0), (0, 0)))[: len(pl)]
        pl_d += tap * (0.38 ** k)
    ir = dsp.ir(rt60=2.4, predelay=0.018, damp=0.55, width=1.0, seed=7)
    send = buses["pad"].x * 0.55 + pl_d * 0.65 + buses["hit"].x * 0.25 + buses["drum"].x * 0.10
    wet = np.stack([signal.oaconvolve(send[:, c], ir[:, c])[: len(send)] for c in range(2)], 1) * 0.55
    dry = buses["pad"].x + pl_d + buses["drum"].x + buses["bass"].x + buses["hit"].x
    mix = (dry + wet)[:n]
    t = np.arange(n) / SR
    mix = mix * level_curve(plan["level"], n)[:, None]
    # fade in (never a click at sample 0) and fade out to digital silence
    fi = int(plan.get("fade_in", 0.8) * SR)
    mix[:fi] *= (np.sin(0.5 * np.pi * np.arange(fi) / fi) ** 2)[:, None]
    fo0, fo1 = plan["fade_out"]
    a, b = int(fo0 * SR), int((duration - fo1) * SR)
    ramp = np.ones(n)
    ramp[a:b] = np.cos(0.5 * np.pi * (np.arange(b - a) / (b - a))) ** 2
    ramp[b:] = 0.0
    mix *= ramp[:, None]
    # remove DC / sub rumble below 25 Hz
    mix = dsp.hpf(mix, 25, order=2)
    mix[-int(0.02 * SR):] = 0.0
    return mix


# ------------------------------------------------------------------ plans
ALIASES = {
    "vsl-90s": {"b02": ["deleted your tests"], "b03": ["get them back"], "b05": ["Why can't git"],
                "b06": ["Claude Code's docs"], "b07": ["flight recorder"], "b08": ["keeps every move"],
                "b09": ["how does rewindagents record"], "b10": ["hash-chained"], "b11": ["Before each edit"],
                "b12": ["which step"], "b13": ["Twelve, because"], "b14": ["four files come back"],
                "b15": ["Even the rewind"], "b16": ["Where does the analogy", "The analogy breaks"],
                "b17": ["Unlike a recorder", "This one puts your files back"],
                "b18": ["Preview with diff"], "b19": ["You can now see"], "b20": ["Up next", "Apache"],
                "b22": ["editor has had undo"]},
    "vsl-30s": {"b02": ["deleted your tests"], "b03": ["get them back"], "b04": ["which step"], "b05": ["Twelve, because"],
                "b06": ["four files come back"], "b07": ["editor has had undo"]},
    "vsl-15s-vertical": {"b02": ["four files come back"], "b03": ["editor has had undo"]},
}


def starts_for(video, overrides):
    """Card start times (s) keyed by the plan's anchor names, found by card text so id renumbering cannot break it."""
    t, real, cards = 0.0, {}, []
    for b in video["beats"]:
        cards.append((t, b["text"]))
        real[b["id"]] = t
        t += b["ms"] / 1000
    out = {}
    for key, subs in ALIASES[video["name"]].items():
        hit = [st for st, tx in cards if any(x.lower() in tx.lower() for x in subs)]
        if hit:
            out[key] = hit[0]
    for k, v in overrides.items():
        out[k] = v / 1000
    return out, t


def plan_90(S, total):
    T = lambda i: S[i]
    end = total
    secs = [
        dict(name="1 tension (the problem)", t0=0.0, t1=T("b07"), bars=None, prog=["Am", "Am", "Fmaj7", "Esus"], final="Esus",
             layers=dict(drone=(None, None), heart=(None, None), air=(2.6, None), tick=(None, None),
                         pulse=(T("b02"), None), pluck4=(2.6, None), glint=(5.2, None)),
             bright=6, low_pluck=True, pl_bright=0.6,
             amp=dict(drone=1.0, heart=1.0, air=0.7, pulse=0.7, tick=0.8, pluck=0.85, glint=1.1),
             riser=dict(dur=2.6, bright=0.4, amp=0.55)),
        dict(name="2 lift (the idea)", t0=T("b07"), t1=T("b12"), bars=None, prog=["C", "G", "Am", "Fmaj7"],
             layers=dict(pad=(None, None), bass=(T("b08"), None), pluck8=(None, None), hat8=(T("b08"), None),
                         kick=(T("b09"), None), shaker=(T("b10"), None), pluck16=(T("b11"), None)),
             bright=12, pl_bright=0.9, amp=dict(pad=1.0, bass=0.9, pluck=0.9, hat=0.8, kick=0.8, shaker=0.7),
             hit=dict(scale=0.35, bright=0.7, bells=[81]),
             riser=dict(dur=1.4, bright=0.6, amp=0.3)),
        dict(name="3 question + build (which step?)", t0=T("b12"), t1=T("b14"), bars=None, prog=["Am", "Fmaj7", "Esus"],
             final="Esus", layers=dict(pad=(None, None), pluck4=(None, None), pulse=(T("b13"), None)),
             bright=8, pl_bright=0.7, amp=dict(pad=0.9, pluck=0.8, pulse=0.9),
             riser=dict(dur=2.5, bright=1.0, amp=0.85)),
        dict(name="4 payoff (rewind 12, four files back)", t0=T("b14"), t1=T("b16"), bars=None, prog=["Aadd9", "Dmaj7", "A"],
             layers=dict(pad=(None, None), bass=(None, None), kick=(None, None), snap=(None, None),
                         pluck16=(None, None), hat16=(None, None), shaker=(None, None)),
             bright=18, pl_bright=1.2, kick_syn=True,
             amp=dict(pad=1.1, bass=1.0, pluck=1.0, hat=1.0, kick=1.0, snap=0.6, shaker=0.9),
             hit=dict(scale=1.0, bright=1.1, bells=[93, 88, 81], bell_amp=1.0)),
        dict(name="5 break + recap (warm, explaining)", t0=T("b16"), t1=T("b20"), bars=None, prog=["Dmaj7", "A", "Bm7", "E"],
             layers=dict(pad=(None, None), bass=(None, None), pluck8=(None, None), hat8=(T("b17"), None),
                         kick=(T("b17"), None), shaker=(T("b18"), None)),
             bright=12, pl_bright=0.9, bass_pat="full",
             amp=dict(pad=1.0, bass=0.8, pluck=0.8, hat=0.7, kick=0.65, shaker=0.7),
             hit=dict(scale=0.18, bright=0.6, bells=[81, 88], bell_amp=0.5)),
        dict(name="6 bridge (what is next)", t0=T("b20"), t1=T("b22"), bars=None, prog=["Dmaj7", "A", "Dmaj7"],
             layers=dict(pad=(None, None), bass=(None, None), pluck8=(None, None), hat8=(None, None)),
             bright=11, pl_bright=0.85, amp=dict(pad=1.0, bass=0.8, pluck=0.75, hat=0.55)),
        dict(name="7 close (end card)", t0=T("b22"), t1=end, bars=None, prog=["Dmaj7", "Aadd9"], final="Aadd9",
             layers=dict(pad=(None, None), pluck4=(T("b22"), None)),
             bright=10, pl_bright=0.7, amp=dict(pad=1.0, pluck=0.7),
             hit=dict(scale=0.22, bright=0.7, bells=[93, 88], bell_amp=0.7)),
    ]
    level = [(0, -1.4), (T("b03"), -0.9), (T("b06"), -1.8), (T("b07") - 0.6, -2.1), (T("b07") + 0.8, -3.0),
             (T("b11"), -1.8), (T("b12") - 0.5, -3.5), (T("b13") + 1.5, -1.5), (T("b14") - 0.1, -1.0), (T("b14") + 0.3, 1.5),
             (T("b15"), 0.5), (T("b16"), -3.5), (T("b16") + 3, -5.6), (T("b19"), -4.4), (T("b20"), -5.4),
             (T("b22") - 0.5, -5.8), (T("b22") + 1.0, -6.2), (end, -8.5)]
    return dict(sections=secs, level=level, fade_out=(end - 3.4, 0.08), delay_beat=60 / 96, fade_in=0.15)


def plan_30(S, total):
    T = lambda i: S[i]
    end = total
    secs = [
        dict(name="1 tension (the problem)", t0=0.0, t1=T("b04"), bars=None, prog=["Am", "Fmaj7", "Am", "Esus"], final="Esus",
             layers=dict(drone=(None, None), heart=(None, None), air=(2.7, None), tick=(None, None), pulse=(T("b02"), None),
                         pluck4=(2.7, None), glint=(5.4, None)),
             bright=6, low_pluck=True, pl_bright=0.6, amp=dict(drone=1.0, heart=1.0, air=0.7, pulse=0.7, tick=0.8, pluck=0.85,
                                                              glint=1.1),
             riser=dict(dur=1.8, bright=0.4, amp=0.5)),
        dict(name="2 question + build (which step?)", t0=T("b04"), t1=T("b06"), bars=None, prog=["C", "G", "Esus"], final="Esus",
             layers=dict(pad=(None, None), bass=(None, None), pluck8=(None, None), hat8=(T("b04") + 2.5, None),
                         pulse=(T("b05"), None)),
             bright=10, pl_bright=0.85, amp=dict(pad=1.0, bass=0.9, pluck=0.9, hat=0.7, pulse=0.8),
             hit=dict(scale=0.3, bright=0.7, bells=[81]),
             riser=dict(dur=2.4, bright=1.0, amp=0.85)),
        dict(name="3 payoff + warm close", t0=T("b06"), t1=end, bars=None, prog=["Aadd9", "Dmaj7", "A", "Aadd9"], final="Aadd9",
             layers=dict(pad=(None, None), bass=(None, end - 2.6), kick=(None, T("b07")), snap=(None, T("b07")),
                         pluck16=(None, T("b07")), hat16=(None, T("b07")), shaker=(None, T("b07")), pluck4=(T("b07"), None)),
             bright=18, pl_bright=1.2, kick_syn=True,
             amp=dict(pad=1.1, bass=1.0, pluck=1.0, hat=1.0, kick=1.0, snap=0.6, shaker=0.9),
             hit=dict(scale=1.0, bright=1.1, bells=[93, 88, 81])),
    ]
    level = [(0, 1.0), (T("b03"), 1.0), (T("b04") - 0.5, 0.0), (T("b04") + 0.8, -3.0), (T("b05") + 1.0, -2.0),
             (T("b06") - 0.1, -1.0), (T("b06") + 0.3, 1.5), (T("b06") + 3.5, 0.0), (T("b07"), -3.5), (end - 3.2, -5.5),
             (end, -8.0)]
    return dict(sections=secs, level=level, fade_out=(end - 3.2, 0.08), delay_beat=60 / 100, fade_in=0.15)


def plan_15(S, total):
    T = lambda i: S[i]
    end = total
    secs = [
        dict(name="1 tension (cold open)", t0=0.0, t1=T("b02"), bars=None, prog=["Am", "Esus"], final="Esus",
             layers=dict(drone=(None, None), heart=(None, None), air=(None, None), tick=(None, None), pulse=(0.9, None),
                         pluck4=(None, None)),
             bright=6, low_pluck=True, pl_bright=0.6, amp=dict(drone=1.0, heart=1.0, air=0.7, pulse=0.7, tick=0.8, pluck=0.85),
             riser=dict(dur=1.9, bright=1.0, amp=0.85)),
        dict(name="2 payoff + warm close", t0=T("b02"), t1=end, bars=None, prog=["Aadd9", "Dmaj7", "A", "Aadd9"], final="Aadd9",
             layers=dict(pad=(None, None), bass=(None, end - 2.7), kick=(None, T("b03")), snap=(None, T("b03")),
                         pluck16=(None, T("b03")), hat16=(None, T("b03")), shaker=(None, T("b03")), pluck4=(T("b03"), None)),
             bright=18, pl_bright=1.2, kick_syn=True,
             amp=dict(pad=1.1, bass=1.0, pluck=1.0, hat=1.0, kick=1.0, snap=0.6, shaker=0.9),
             hit=dict(scale=1.0, bright=1.1, bells=[93, 88, 81])),
    ]
    level = [(0, 1.0), (T("b02") - 1.0, 0.5), (T("b02") - 0.1, -4.0), (T("b02") + 0.3, 1.5), (T("b02") + 3.0, 0.0),
             (T("b03"), -3.0), (end - 3.0, -5.0), (end, -8.0)]
    return dict(sections=secs, level=level, fade_out=(end - 3.0, 0.08), delay_beat=60 / 98, fade_in=0.15)


# ------------------------------------------------------------------ SFX
LAND_S = 0.72   # sfx-rewind.wav: the landing transient (click + thump + bell attack) starts this far into the file


def sfx_rewind():
    """0.9 s tape-style falling sweep with an accelerating tick train that lands on a small bell. Peak -8 dBFS."""
    dur = 0.9
    n = int(dur * SR)
    t = np.linspace(0, 1, n)
    nz = sweep_noise(dur, 7500, 260, seed=21)
    env = np.sin(np.pi * np.clip(t * 1.05, 0, 1)) ** 1.5
    f = 2200 * np.exp(-2.2 * t) + 110
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.35 * np.sin(4 * np.pi * np.cumsum(f) / SR)
    flut = 0.75 + 0.25 * np.sin(2 * np.pi * np.cumsum(34 - 22 * t) / SR)
    s = (nz * 0.8 + tone * 0.22) * env * flut
    # tick train: spacing grows as the "tape" slows (rewinding to a stop)
    pos, gap = 0.04, 0.012
    while pos < LAND_S - 0.12:   # no tick inside the last 120 ms: the landing is the only sharp event near it
        i = int(pos * SR)
        tk = woodtick(1.6)
        s[i:i + len(tk)] += tk[: n - i] * (1 - 0.5 * pos / dur)
        gap *= 1.16
        pos += gap
    # land: soft thump + A5 bell at 0.72 s
    land = int(LAND_S * SR)
    kn = int(0.012 * SR)
    kt = np.arange(kn) / SR
    click = dsp.hpf(np.random.default_rng(23).standard_normal(kn), 3000, order=2) * np.exp(-kt / 0.003)
    s[land:land + kn] += click * 0.9    # broadband attack at exactly LAND_S so a >4 kHz detector also finds the landing
    th = sub_note(45, 0.35, 1.8, att=0.003)
    s[land:land + len(th)] += th[: n - land]
    bl = bell(81, dur=0.9, amp=2.6)
    s[land:land + len(bl)] += bl[: n - land]
    s *= np.minimum(1, np.arange(n) / (0.004 * SR))
    s[-int(0.05 * SR):] *= np.linspace(1, 0, int(0.05 * SR))
    x = np.stack([s, np.roll(s, 24)], 1)
    x = x / np.abs(x).max() * dsp.undb(-8.0)
    x[-1] = 0
    return x


def sfx_tick():
    """Firm card-change tick, 90 ms, peak -12 dBFS."""
    n = int(0.09 * SR)
    t = np.arange(n) / SR
    s = np.sin(2 * np.pi * 1850 * t) * np.exp(-t / 0.014) + 0.6 * np.sin(2 * np.pi * 3100 * t) * np.exp(-t / 0.008)
    s += 0.5 * np.sin(2 * np.pi * 620 * t) * np.exp(-t / 0.02)
    rng = np.random.default_rng(4)
    s += dsp.hpf(rng.standard_normal(n), 4000) * np.exp(-t / 0.003) * 0.3
    s *= np.minimum(1, t / 0.0012)
    s[-int(0.01 * SR):] *= np.linspace(1, 0, int(0.01 * SR))
    x = np.stack([s, s], 1)
    x = x / np.abs(x).max() * dsp.undb(-12.0)
    x[-1] = 0
    return x


# ------------------------------------------------------------------ main
TARGET = {"vsl-90s": (plan_90, "bed-vsl-90s.wav", -16.0), "vsl-30s": (plan_30, "bed-vsl-30s.wav", -16.0),
          "vsl-15s-vertical": (plan_15, "bed-vsl-15s-vertical.wav", -14.0)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--beats", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only")
    ap.add_argument("--starts", action="append", default=[], help="video:id=ms,id=ms")
    ap.add_argument("--trim", type=float, default=0.0, help="lufs offset added to the target (closed loop use)")
    a = ap.parse_args()
    out = Path(a.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    data = json.load(open(Path(a.beats).expanduser()))
    ov = {}
    for s in a.starts:
        v, kv = s.split(":")
        ov[v] = {k: float(x) for k, x in (p.split("=") for p in kv.split(","))}
    report = {}
    for vid in data["videos"]:
        name = vid["name"]
        if name not in TARGET or (a.only and a.only != name):
            continue
        fn, fname, tgt = TARGET[name]
        S, total = starts_for(vid, ov.get(name, {}))
        plan = fn(S, total)
        mix = build_bed(plan, total)
        mix = dsp.master(mix, tgt + a.trim, -1.6)
        mix[-int(0.02 * SR):] = 0.0
        dsp.save(out / fname, mix, bits=24)
        report[name] = dict(file=fname, duration=total, sections=[
            {k: sec[k] for k in ("name", "t0", "t1", "bars", "bpm", "chords", "layer_bars")} for sec in plan["sections"]])
        print(name, "ok", fname, round(total, 2), "s", "lufs", round(dsp.lufs(mix), 2), "tp", round(dsp.true_peak_db(mix), 2))
    sj = out / "sections.json"
    if a.only and sj.exists():
        old = json.load(open(sj))
        old.update(report)       # an --only run must not drop the other films' sections
        report = old
    json.dump(report, open(sj, "w"), indent=1)
    if not a.only or a.only == "sfx":
        dsp.save(out / "sfx-rewind.wav", sfx_rewind(), bits=24)
        dsp.save(out / "sfx-tick.wav", sfx_tick(), bits=24)


if __name__ == "__main__":
    main()
