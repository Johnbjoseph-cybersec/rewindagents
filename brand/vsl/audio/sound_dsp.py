"""Shared DSP for the sound-design pipeline: io, filters, loudness, true peak, dynamics, reverb, voice chain.

Pure numpy/scipy/soundfile/pyloudnorm (all in .venv-voice). No network, no model weights.
Every function takes and returns float64 arrays shaped (n,) mono or (n, 2) stereo at SR unless noted.
"""
from __future__ import annotations

import numpy as np
import pyloudnorm as pyln
import soundfile as sf
from scipy import signal

SR = 48000


# ------------------------------------------------------------------ io
def load(path, sr=SR, mono=False):
    x, r = sf.read(str(path), always_2d=True, dtype="float64")
    if r != sr:
        g = np.gcd(int(r), int(sr))
        x = signal.resample_poly(x, sr // g, r // g, axis=0)
    if mono:
        return x.mean(1)
    if x.shape[1] == 1:
        x = np.repeat(x, 2, axis=1)
    return x[:, :2]


def save(path, x, sr=SR, bits=24):
    x = np.asarray(x, dtype="float64")
    sf.write(str(path), np.clip(x, -1, 1), sr, subtype="PCM_24" if bits == 24 else "PCM_16")


def stereo(x):
    return x if x.ndim == 2 else np.stack([x, x], 1)


def mono(x):
    return x if x.ndim == 1 else x.mean(1)


def fit(x, n):
    """Pad with zeros or trim to exactly n samples."""
    if len(x) >= n:
        return x[:n]
    pad = [(0, n - len(x))] + [(0, 0)] * (x.ndim - 1)
    return np.pad(x, pad)


def pan(x, p):
    """Constant-power pan of a mono signal, p in [-1, 1]."""
    a = (p + 1) * np.pi / 4
    return np.stack([x * np.cos(a), x * np.sin(a)], 1)


def db(x):
    return 20 * np.log10(np.maximum(np.abs(x), 1e-12))


def undb(d):
    return 10 ** (np.asarray(d) / 20)


# ------------------------------------------------------------------ filters (zero-phase where it does not matter)
def _sos(kind, f, sr=SR, order=2):
    return signal.butter(order, f, btype=kind, fs=sr, output="sos")


def hpf(x, f, order=2, sr=SR):
    return signal.sosfilt(_sos("highpass", f, sr, order), x, axis=0)


def lpf(x, f, order=2, sr=SR):
    return signal.sosfilt(_sos("lowpass", f, sr, order), x, axis=0)


def bpf(x, lo, hi, order=2, sr=SR):
    return signal.sosfilt(_sos("bandpass", [lo, hi], sr, order), x, axis=0)


def _biquad(kind, f0, gain_db, q=0.707, sr=SR):
    """RBJ cookbook biquads: 'peak', 'lowshelf', 'highshelf'."""
    A = 10 ** (gain_db / 40)
    w0 = 2 * np.pi * f0 / sr
    alpha = np.sin(w0) / (2 * q)
    c = np.cos(w0)
    if kind == "peak":
        b = [1 + alpha * A, -2 * c, 1 - alpha * A]
        a = [1 + alpha / A, -2 * c, 1 - alpha / A]
    elif kind == "lowshelf":
        s = 2 * np.sqrt(A) * alpha
        b = [A * ((A + 1) - (A - 1) * c + s), 2 * A * ((A - 1) - (A + 1) * c), A * ((A + 1) - (A - 1) * c - s)]
        a = [(A + 1) + (A - 1) * c + s, -2 * ((A - 1) + (A + 1) * c), (A + 1) + (A - 1) * c - s]
    elif kind == "highshelf":
        s = 2 * np.sqrt(A) * alpha
        b = [A * ((A + 1) + (A - 1) * c + s), -2 * A * ((A - 1) + (A + 1) * c), A * ((A + 1) + (A - 1) * c - s)]
        a = [(A + 1) - (A - 1) * c + s, 2 * ((A - 1) - (A + 1) * c), (A + 1) - (A - 1) * c - s]
    else:
        raise ValueError(kind)
    return np.array(b) / a[0], np.array(a) / a[0]


def eq(x, kind, f0, gain_db, q=0.707, sr=SR):
    b, a = _biquad(kind, f0, gain_db, q, sr)
    return signal.lfilter(b, a, x, axis=0)


# ------------------------------------------------------------------ loudness / peak
_meters = {}


def _meter(sr):
    if sr not in _meters:
        _meters[sr] = pyln.Meter(sr)
    return _meters[sr]


def lufs(x, sr=SR):
    x = stereo(x)
    if len(x) < int(0.5 * sr) or not np.any(x):
        return -70.0
    v = _meter(sr).integrated_loudness(x)
    return float(v) if np.isfinite(v) else -70.0


def kweight(x, sr=SR):
    m = _meter(sr)
    y = np.asarray(x, dtype="float64")
    for f in m._filters.values():
        y = f.apply_filter(y)
    return y


def window_loudness(x, win=0.4, hop=0.1, sr=SR):
    """Momentary-style loudness per window (LUFS, K-weighted, channel-summed). Returns (times, lufs)."""
    w, h = int(win * sr), int(hop * sr)
    x = stereo(x)
    if len(x) < w + 1:
        x = np.pad(x, ((0, w + 1 - len(x)), (0, 0)))
    k = stereo(kweight(x, sr))
    p = (k ** 2).sum(1)
    c = np.concatenate([[0], np.cumsum(p)])
    starts = np.arange(0, max(1, len(p) - w), h)
    ms = (c[starts + w] - c[starts]) / w
    return (starts + w / 2) / sr, -0.691 + 10 * np.log10(ms + 1e-12)


def max_momentary(x, sr=SR):
    _, l = window_loudness(x, 0.4, 0.05, sr)
    return float(l.max()) if len(l) else -70.0


def true_peak_db(x, sr=SR):
    x = stereo(x)
    up = signal.resample_poly(x, 4, 1, axis=0)
    return float(db(np.max(np.abs(up))))


def normalize_lufs(x, target, sr=SR):
    return x * undb(target - lufs(x, sr))


def normalize_momentary(x, target, sr=SR):
    return x * undb(target - max_momentary(x, sr))


# ------------------------------------------------------------------ envelopes / dynamics
def _smooth_gain_db(target_db, sr, attack, release, block=32):
    """Asymmetric one-pole smoothing of a gain curve (dB, <= 0 means reduction) at block rate."""
    n = len(target_db)
    nb = int(np.ceil(n / block))
    t = np.pad(target_db, (0, nb * block - n), mode="edge").reshape(nb, block).min(1)
    a_att = np.exp(-block / (attack * sr))
    a_rel = np.exp(-block / (release * sr))
    out = np.empty(nb)
    g = 0.0
    for i in range(nb):
        v = t[i]
        a = a_att if v < g else a_rel
        g = a * g + (1 - a) * v
        out[i] = g
    xb = np.arange(nb) * block + block / 2
    return np.interp(np.arange(n), xb, out)


def rms_env(x, win, sr=SR):
    m = mono(x) ** 2
    w = max(1, int(win * sr))
    c = np.concatenate([[0], np.cumsum(m)])
    idx = np.arange(len(m))
    lo = np.clip(idx - w // 2, 0, len(m))
    hi = np.clip(idx + w // 2 + 1, 0, len(m))
    return np.sqrt((c[hi] - c[lo]) / np.maximum(hi - lo, 1))


def compress(x, threshold_db, ratio=4.0, attack=0.005, release=0.08, knee=6.0, sr=SR, detector=None):
    """Feed-forward RMS compressor with soft knee. detector: optional signal to key from (sidechain)."""
    lvl = db(rms_env(x if detector is None else detector, 0.01, sr))
    over = lvl - threshold_db
    gr = np.where(over <= -knee / 2, 0.0,
                  np.where(over >= knee / 2, over * (1 / ratio - 1),
                           (1 / ratio - 1) * (over + knee / 2) ** 2 / (2 * knee)))
    g = undb(_smooth_gain_db(gr, sr, attack, release))
    return x * (g[:, None] if x.ndim == 2 else g)


def limit(x, ceiling_db=-1.0, lookahead=0.005, release=0.06, sr=SR):
    """Lookahead true-peak limiter: 4x-oversampled peak detection, gain reaches its minimum before the peak."""
    x = stereo(x)
    up = np.abs(signal.resample_poly(x, 4, 1, axis=0)).max(1)
    n = len(x)
    pk = np.pad(up, (0, max(0, 4 * n - len(up))))[: 4 * n].reshape(n, 4).max(1)
    pk = np.maximum(pk, np.abs(x).max(1))
    ceil = undb(ceiling_db)
    req = np.minimum(1.0, ceil / np.maximum(pk, 1e-12))
    L = max(1, int(lookahead * sr))
    from scipy.ndimage import minimum_filter1d, uniform_filter1d
    req = minimum_filter1d(req, size=2 * L + 1, origin=0)  # covers +-L around each peak
    req_db = db(req)
    g_db = _smooth_gain_db(req_db, sr, attack=lookahead / 3, release=release, block=16)
    g_db = np.minimum(g_db, uniform_filter1d(req_db, size=L))  # never above the requirement around peaks
    g = undb(g_db)
    return x * g[:, None]


def master(x, target_lufs, tp_ceiling, sr=SR, tries=6):
    """Gain to target integrated loudness, then true-peak limit; iterate until both hold."""
    y = x
    ceil = tp_ceiling - 0.3
    gain = target_lufs - lufs(x, sr)
    for _ in range(tries):
        y = limit(x * undb(gain), ceil, sr=sr)
        err = target_lufs - lufs(y, sr)
        tp = true_peak_db(y, sr)
        if tp > tp_ceiling:
            ceil -= (tp - tp_ceiling) + 0.1
            continue
        if abs(err) <= 0.1:
            break
        gain += err
    return y


# ------------------------------------------------------------------ reverb
def ir(rt60=2.4, predelay=0.02, damp=0.6, width=1.0, seed=1, sr=SR):
    """Synthetic stereo hall impulse response: decorrelated noise, exponential decay, frequency-dependent damping."""
    rng = np.random.default_rng(seed)
    n = int((rt60 * 1.2 + predelay) * sr)
    t = np.arange(n) / sr
    env = np.exp(-6.9 * t / rt60)
    out = np.zeros((n, 2))
    for ch in range(2):
        nz = rng.standard_normal(n) * env
        # split into low and high parts; highs decay faster (air absorption)
        hi = hpf(nz, 3000)
        lo = nz - hi
        nz = lo + hi * np.exp(-6.9 * t / (rt60 * (1 - damp) + 1e-3))
        out[:, ch] = nz
    m, s = out.mean(1), (out[:, 0] - out[:, 1]) / 2
    out = np.stack([m + width * s, m - width * s], 1)
    pd = int(predelay * sr)
    out = np.pad(out, ((pd, 0), (0, 0)))[:n]
    out[: int(0.004 * sr)] *= np.linspace(0, 1, int(0.004 * sr))[:, None]
    return out / np.sqrt((out ** 2).sum() / 2)


def reverb(x, impulse, wet=0.3, sr=SR):
    x = stereo(x)
    w = np.stack([signal.oaconvolve(x[:, c], impulse[:, c])[: len(x)] for c in range(2)], 1)
    return x * (1 - wet) + w * wet * 0.35


# ------------------------------------------------------------------ voice chain
BANDS = [(80, 250, "low"), (250, 2000, "mid"), (2000, 6000, "presence"), (6000, 12000, "air")]


def tone_share(x, sr=SR, seconds=30):
    """Same definition as studio/measure_refs.py: band energy share of 80-12000 Hz, first 30 s."""
    m = mono(x)[: sr * seconds]
    spec = np.abs(np.fft.rfft(m)) ** 2
    f = np.fft.rfftfreq(len(m), 1 / sr)
    tot = spec[(f >= 80) & (f < 12000)].sum() + 1e-20
    return {lbl: float(spec[(f >= lo) & (f < hi)].sum() / tot) for lo, hi, lbl in BANDS}


def sibilance_db(x, sr=SR):
    """Peak 10 ms RMS of the 5 kHz+ band relative to the 95th-percentile 10 ms RMS of the whole voice."""
    return float(db(rms_env(hpf(x, 5000, order=4), 0.01, sr)).max() - np.percentile(db(rms_env(x, 0.01, sr)), 95))


def de_ess_rel(x, below_vowel_db=9.0, sr=SR):
    """Sibilance ceiling: the 5 kHz+ band may not exceed (vowel p95 - below_vowel_db)."""
    th = float(np.percentile(db(rms_env(x, 0.01, sr)), 95)) - below_vowel_db
    for _ in range(3):
        x = de_ess(x, 4500, th, ratio=20.0, sr=sr)
    return x


def de_ess(x, f=5000, threshold_db=-30, ratio=4.0, sr=SR):
    hi = hpf(x, f, order=2)
    lvl = db(rms_env(hi, 0.005, sr))
    over = np.maximum(0, lvl - threshold_db)
    g = undb(_smooth_gain_db(-over * (1 - 1 / ratio), sr, 0.001, 0.05, block=16))
    return x + (g - 1) * hi


def voice_chain(v, targets=None, sr=SR, log=None, tilt=None):
    """Clean voice + gentle corrective EQ only. Mono in, mono out.

    HARD RULE (John, 2026-10-23: "sounds like the speaker broke"): never synthesise high frequencies - no exciter,
    waveshaper, harmonic generation or bandwidth extension, and no EQ chasing the presence/air reference shares.
    A dark source stays dark until the voice model is fixed upstream (voice/, Arjun). sound_design.py guards this.

    HPF 80 Hz, -2 dB bell at 250 Hz, +2.5 dB bell at 3 kHz (the maximum allowed), light 3:1 compression,
    de-ess only if real sibilance is hot, -16 LUFS, lookahead peak limiter (gain only, no clipping).

    tilt (2026-10-25, long-form narration only, John's lead asked for more presence/air from a dark voice model):
    an optional LINEAR presence/air tilt = {"peak3k": dB, "shelf_f": Hz, "shelf_db": dB, "air_f": Hz, "air_db": dB}.
    Biquad peaking/shelf filters only - still no exciter, no nonlinearity, no synthesis. The caller must run
    voice_guard and back the gains off if it fails (sound_design.design does)."""
    log = log if log is not None else {}
    v = mono(v)
    v = hpf(v, 80, order=2)
    v = eq(v, "peak", 250, -2.0, q=0.9)
    v = eq(v, "peak", 3000, (tilt or {}).get("peak3k", 2.5), q=0.8)
    if tilt:
        if tilt.get("shelf_db"):
            v = eq(v, "highshelf", tilt["shelf_f"], tilt["shelf_db"])
        if tilt.get("air_db"):
            v = eq(v, "highshelf", tilt["air_f"], tilt["air_db"])
        log["tilt"] = tilt
    act = rms_env(v, 0.01, sr)
    loud = float(db(np.percentile(act[act > np.percentile(act, 40)], 90)))
    v = compress(v, loud - 10, ratio=3.0, attack=0.010, release=0.15, knee=8.0, sr=sr)
    sib = sibilance_db(v, sr)
    log["sibilance_db_vs_vowels_in"] = round(sib, 1)
    if sib > -6.0:  # only when the recording really has hot esses
        v = de_ess_rel(v, 6.0, sr)
        log["de_ess"] = True
    else:
        log["de_ess"] = False
    v = v * undb(-16 - lufs(v, sr))
    v = limit(v, -4.0, lookahead=0.005, release=0.12, sr=sr)[:, 0]
    log["tone_final"] = {k: round(val, 3) for k, val in tone_share(v, sr).items()}
    log["sibilance_db_vs_vowels"] = round(sibilance_db(v, sr), 1)
    return v


# ------------------------------------------------------------------ voice integrity metrics (the guard)
def hf_flatness(x, sr=SR, lo=6000, hi=16000, nper=2048):
    """Median spectral flatness (geometric/arithmetic mean of power) over 6-16 kHz, on frames where the voice is
    active. Real speech highs are peaky (formants/sibilant shape) -> low; synthesised fizz/noise -> high."""
    from scipy import signal as _s
    m = mono(x)
    f, t, Z = _s.stft(m, sr, nperseg=nper, noverlap=nper // 2)
    P = np.abs(Z) ** 2
    fr = P.sum(0)
    act = fr > np.percentile(fr, 95) * 10 ** (-30 / 10)
    band = P[(f >= lo) & (f < hi)][:, act] + 1e-20
    flat = np.exp(np.mean(np.log(band), 0)) / np.mean(band, 0)
    return float(np.median(flat))


def clip_pct(x, thresh=0.999):
    a = np.abs(np.asarray(x))
    return float(100.0 * np.mean(a >= thresh))


def nonlinear_residual_db(x_in, x_out, sr=SR, lo=150, hi=8000):
    """Distortion estimate: 1 - magnitude-squared coherence between input and output, power-weighted over lo-hi Hz.
    EQ, slow gain changes and limiting keep coherence near 1; waveshaping/harmonic synthesis destroys it.
    Returned as 10*log10((1-C)/C): more negative = cleaner."""
    from scipy import signal as _s
    a, b = mono(x_in), mono(x_out)
    n = min(len(a), len(b))
    f, C = _s.coherence(a[:n], b[:n], fs=sr, nperseg=4096)
    _, P = _s.welch(a[:n], fs=sr, nperseg=4096)
    sel = (f >= lo) & (f < hi)
    c = float(np.sum(C[sel] * P[sel]) / np.sum(P[sel]))
    c = min(max(c, 1e-6), 1 - 1e-9)
    return float(10 * np.log10((1 - c) / c))


# ------------------------------------------------------------------ tonal match to a reference voice (John's real recorded clips)
def ltas_bands(lo=100, hi=10000, per_oct=3):
    n = int(np.floor(np.log2(hi / lo) * per_oct)) + 1
    return [lo * 2 ** (i / per_oct) for i in range(n)]


def ltas(x, sr=SR, lo=100, hi=10000, per_oct=3):
    """Long-term average spectrum of the SPEAKING frames (frames within 30 dB of the 95th percentile level),
    in dB per third-octave band, normalised so the 300-3000 Hz mean is 0 dB. Returns (centres, dB)."""
    m = mono(x)
    n = 4096
    k = (len(m) - n) // (n // 2)
    fr = np.stack([m[i * (n // 2): i * (n // 2) + n] for i in range(k)]) * np.hanning(n)
    lev = 10 * np.log10(np.mean(fr ** 2, axis=1) + 1e-20)
    fr = fr[lev > np.percentile(lev, 95) - 30]
    p = (np.abs(np.fft.rfft(fr, axis=1)) ** 2).mean(axis=0)
    f = np.fft.rfftfreq(n, 1 / sr)
    edges = ltas_bands(lo, hi, per_oct)
    cen, out = [], []
    for a in edges[:-1]:
        b = a * 2 ** (1 / per_oct)
        sel = (f >= a) & (f < b)
        cen.append(float(np.sqrt(a * b)))
        out.append(10 * np.log10(p[sel].sum() + 1e-20))
    out = np.array(out)
    ref = np.array(cen)
    out -= 10 * np.log10(np.mean(10 ** (out[(ref >= 300) & (ref <= 3000)] / 10)) + 1e-20)
    return np.array(cen), out


def ltas_distance(a, b, sr=SR, lo=100, hi=10000):
    """RMS difference (dB) of two voices' LTAS over third-octave bands lo-hi, plus the per-band differences."""
    c, la = ltas(a, sr, lo, hi)
    _, lb = ltas(b, sr, lo, hi)
    diff = la - lb
    return float(np.sqrt(np.mean(diff ** 2))), {int(round(f)): round(float(v), 1) for f, v in zip(c, diff)}


def ltas_match(x, ref, sr=SR, max_db=4.0, lo=100, hi=9000, taps=2049, max_db_hf=None, hf_from=3000):
    """LINEAR-PHASE FIR equaliser that moves x's LTAS toward ref's, correction clamped to +-max_db per band and
    smoothed across bands. A fixed filter (no signal dependence): no exciter, no synthesis. Caller runs voice_guard."""
    from scipy import signal as sg
    c, la = ltas(x, sr, lo, hi)
    _, lb = ltas(ref, sr, lo, hi)
    lim = np.where(np.array(c) >= hf_from, max_db_hf if max_db_hf else max_db, max_db)  # the dark-vs-bright gap lives above 3 kHz
    corr = np.clip(lb - la, -lim, lim)
    corr = np.convolve(np.pad(corr, 1, mode="edge"), np.ones(3) / 3, mode="valid")  # smooth across bands
    freqs = np.concatenate([[0], c, [sr / 2]])
    gains = np.concatenate([[corr[0]], corr, [corr[-1]]])
    h = sg.firwin2(taps, freqs / (sr / 2), 10 ** (gains / 20))
    y = sg.fftconvolve(mono(x), h, mode="full")[taps // 2: taps // 2 + len(mono(x))]
    return y, {int(round(f)): round(float(g), 1) for f, g in zip(c, corr)}
