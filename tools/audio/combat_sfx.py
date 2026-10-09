#!/usr/bin/env python3
"""Procedural combat one-shots for Echoes of Aether (no samples, no AI): additive / FM / filtered-noise synthesis.

Writes mono 44.1 kHz 16-bit WAVs to unity/EchoesOfAether/Assets/Resources/Audio/SFX/<id>_v<n>.wav. These ids are not in
manifest.json, so AudioManager loads them by naming convention at gain 1.0: levels are baked into the files to sit with
the rendered prototype set (hit -3 dB peak, swings around -17 dB, telegraph -19 dB).

  python3 tools/audio/combat_sfx.py
"""
import os, wave
import numpy as np

SR = 44100
OUT = os.path.join(os.path.dirname(__file__), "..", "..", "unity", "EchoesOfAether", "Assets", "Resources", "Audio", "SFX")


def t_axis(dur):
    return np.arange(int(SR * dur)) / SR


def env_exp(t, tau, attack=0.002):
    a = np.clip(t / max(attack, 1e-5), 0, 1)
    return a * np.exp(-t / tau)


def onepole_lp(x, fc):
    a = np.exp(-2 * np.pi * fc / SR)
    y = np.zeros_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc = (1 - a) * v + a * acc
        y[i] = acc
    return y


def svf_bandpass(x, fc, q):
    """State-variable band-pass with per-sample centre frequency (array) or constant."""
    fc = np.broadcast_to(np.asarray(fc, dtype=float), x.shape)
    low = band = 0.0
    y = np.zeros_like(x)
    damp = 1.0 / q
    for i, v in enumerate(x):
        f = 2 * np.sin(np.pi * min(fc[i], SR * 0.2) / SR)
        low += f * band
        high = v - low - damp * band
        band += f * high
        y[i] = band
    return y


def highpass(x, fc):
    return x - onepole_lp(x, fc)


def norm(x, peak_db):
    x = x - np.mean(x)
    m = np.max(np.abs(x)) + 1e-9
    # Short fade-out to avoid clicks.
    n = min(len(x), int(0.008 * SR))
    x[-n:] *= np.linspace(1, 0, n)
    return x / m * (10 ** (peak_db / 20))


def write(name, x):
    os.makedirs(OUT, exist_ok=True)
    pcm = np.clip(x, -1, 1)
    pcm = (pcm * 32767).astype(np.int16)
    with wave.open(os.path.join(OUT, name + ".wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print("wrote", name, f"{len(x) / SR:.2f}s")


def metal(t, f0, ratios, taus, gains, rng, drop=0.0):
    """Inharmonic struck-metal partials with slight detune and an optional pitch drop."""
    y = np.zeros_like(t)
    for r, tau, g in zip(ratios, taus, gains):
        f = f0 * r * (1 + rng.uniform(-0.004, 0.004))
        ph = 2 * np.pi * np.cumsum(f * (1 - drop * (1 - np.exp(-t / 0.05)))) / SR
        y += g * np.sin(ph + rng.uniform(0, 6.28)) * env_exp(t, tau, 0.0008)
    return y


def impact_clang(seed):
    rng = np.random.default_rng(seed)
    t = t_axis(0.42)
    f0 = rng.uniform(620, 900)
    y = metal(t, f0, [1, 2.76, 5.40, 8.93, 13.3], [0.16, 0.11, 0.07, 0.045, 0.03], [1, 0.7, 0.5, 0.35, 0.2], rng, drop=0.03)
    click = highpass(rng.normal(0, 1, len(t)), 2500) * env_exp(t, 0.004, 0.0003) * 1.4
    body = np.sin(2 * np.pi * 140 * t) * env_exp(t, 0.03) * 0.6
    return norm(y + click + body, -9)


def impact_zap(seed):
    rng = np.random.default_rng(seed)
    t = t_axis(0.26)
    f = 2600 * np.exp(-t / 0.045) + 260
    mod = np.sin(2 * np.pi * np.cumsum(f * 1.5) / SR) * (3 + 6 * np.exp(-t / 0.05))
    y = np.sin(2 * np.pi * np.cumsum(f) / SR + mod) * env_exp(t, 0.07, 0.001)
    crackle = (rng.random(len(t)) < 0.02).astype(float) * rng.normal(0, 1, len(t))
    crackle = svf_bandpass(crackle, 3500, 2.0) * env_exp(t, 0.06) * 3
    y = np.round(y * 10) / 10  # light bit-crush grit
    return norm(y * 0.8 + crackle, -11)


def blade_swish(seed):
    rng = np.random.default_rng(seed)
    dur = rng.uniform(0.2, 0.26)
    t = t_axis(dur)
    u = t / dur
    shape = np.sin(np.pi * np.clip(u, 0, 1)) ** 1.6
    fc = 700 + 2600 * np.sin(np.pi * np.clip(u * 1.1, 0, 1))
    swish = svf_bandpass(rng.normal(0, 1, len(t)), fc, 1.6) * shape
    # Hard-light hum with a doppler bend.
    fh = 180 * (1 + 0.35 * np.sin(np.pi * u))
    ph = 2 * np.pi * np.cumsum(fh) / SR
    hum = (np.sin(ph) + 0.5 * np.sin(2 * ph) + 0.25 * np.sin(3.01 * ph)) * shape * 0.35
    return norm(swish + hum, -16)


def crit_hit(seed):
    rng = np.random.default_rng(seed)
    t = t_axis(0.55)
    ring = metal(t, rng.uniform(1300, 1500), [1, 2.32, 4.25, 6.8], [0.3, 0.2, 0.12, 0.08], [1, 0.6, 0.4, 0.25], rng)
    thump = np.sin(2 * np.pi * np.cumsum(70 * np.exp(-t / 0.08) + 45) / SR) * env_exp(t, 0.09, 0.001) * 1.6
    snap = highpass(rng.normal(0, 1, len(t)), 3000) * env_exp(t, 0.006, 0.0003)
    return norm(ring * 0.7 + thump + snap, -6)


def perfect_dodge(seed):
    rng = np.random.default_rng(seed)
    t = t_axis(0.75)
    u = t / 0.75
    swell = svf_bandpass(rng.normal(0, 1, len(t)), 400 + 3200 * u ** 1.5, 2.5) * np.clip(u / 0.28, 0, 1) ** 2 * np.exp(-np.clip(u - 0.28, 0, None) * 9)
    sweep = np.sin(2 * np.pi * np.cumsum(500 + 1700 * np.clip(u / 0.3, 0, 1)) / SR) * np.clip(u / 0.28, 0, 1) * np.exp(-np.clip(u - 0.28, 0, None) * 7) * 0.25
    shimmer = np.zeros_like(t)
    for k, f in enumerate([2093, 2637, 3136, 4186]):
        trem = 0.6 + 0.4 * np.sin(2 * np.pi * (11 + k) * t)
        shimmer += np.sin(2 * np.pi * f * t + k) * trem * env_exp(np.clip(t - 0.2, 0, None), 0.22, 0.01) * (t > 0.2) * (0.5 / (k + 1))
    return norm(swell * 0.8 + sweep + shimmer, -6)


def parry(seed):
    rng = np.random.default_rng(seed)
    t = t_axis(0.9)
    y = metal(t, rng.uniform(410, 470), [1, 2.41, 3.87, 5.95, 8.2, 11.1], [0.45, 0.3, 0.2, 0.14, 0.09, 0.06], [1, 0.8, 0.6, 0.45, 0.3, 0.2], rng, drop=0.02)
    hit = highpass(rng.normal(0, 1, len(t)), 1800) * env_exp(t, 0.01, 0.0003) * 2
    zing = np.sin(2 * np.pi * np.cumsum(3200 - 1400 * np.clip(t / 0.4, 0, 1)) / SR) * env_exp(t, 0.18, 0.002) * 0.25
    y = y + hit + zing
    # Small comb "room" tail.
    d = int(0.031 * SR)
    tail = np.zeros_like(y)
    tail[d:] = y[:-d] * 0.35
    return norm(y + tail, -3)


def poise_break(seed):
    rng = np.random.default_rng(seed)
    t = t_axis(0.6)
    crack = highpass(rng.normal(0, 1, len(t)), 2200) * env_exp(t, 0.035, 0.0005) * 1.8
    shards = np.zeros_like(t)
    for _ in range(9):
        t0 = rng.uniform(0, 0.25)
        tt = np.clip(t - t0, 0, None)
        shards += np.sin(2 * np.pi * rng.uniform(2500, 6000) * tt) * env_exp(tt, rng.uniform(0.02, 0.06), 0.0005) * (t >= t0) * rng.uniform(0.2, 0.5)
    drop = np.sin(2 * np.pi * np.cumsum(900 * np.exp(-t / 0.15) + 90) / SR) * env_exp(t, 0.16, 0.002) * 0.9
    return norm(crack + shards + drop, -5)


def enemy_glint(seed):
    rng = np.random.default_rng(seed)
    t = t_axis(0.32)
    y = (np.sin(2 * np.pi * 3150 * t) + 0.6 * np.sin(2 * np.pi * 4720 * t + 1) + 0.3 * np.sin(2 * np.pi * 6300 * t)) * env_exp(t, 0.08, 0.002)
    return norm(y, -14)


def robot_break(seed):
    rng = np.random.default_rng(seed)
    t = t_axis(0.9)
    y = np.zeros_like(t)
    for _ in range(14):
        t0 = rng.uniform(0, 0.6) ** 1.4
        tt = np.clip(t - t0, 0, None)
        y += metal(tt, rng.uniform(500, 2400), [1, 2.76, 5.4], [0.05, 0.035, 0.02], [1, 0.6, 0.3], rng) * (t >= t0) * rng.uniform(0.25, 0.8)
    crunch = svf_bandpass(rng.normal(0, 1, len(t)), 900, 1.2) * env_exp(t, 0.12, 0.002) * 1.2
    sub = np.sin(2 * np.pi * np.cumsum(60 * np.exp(-t / 0.2) + 35) / SR) * env_exp(t, 0.2, 0.003)
    return norm(y + crunch + sub, -5)


def main():
    for v in range(3):
        write(f"impact_clang_v{v + 1}", impact_clang(10 + v))
        write(f"impact_zap_v{v + 1}", impact_zap(20 + v))
        write(f"blade_swish_v{v + 1}", blade_swish(30 + v))
        write(f"robot_break_v{v + 1}", robot_break(40 + v))
    for v in range(2):
        write(f"crit_hit_v{v + 1}", crit_hit(50 + v))
        write(f"perfect_dodge_v{v + 1}", perfect_dodge(60 + v))
        write(f"parry_v{v + 1}", parry(70 + v))
        write(f"poise_break_v{v + 1}", poise_break(80 + v))
    write("enemy_glint", enemy_glint(90))


if __name__ == "__main__":
    main()
