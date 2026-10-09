#!/usr/bin/env python3
"""Procedural vehicle sounds for Echoes of Aether (no samples, no AI): additive, pulse-train and filtered-noise synthesis.

Loops are built to be exactly periodic (every partial an integer number of cycles per loop, noise shaped in the
frequency domain of the whole loop), so they wrap without a seam at any playback pitch:
  car_engine_low   idle / low-rev engine bed (firing pulses through exhaust resonances + a faint motor whine)
  car_engine_high  high-rev engine (brighter, more whine); CarAudio crossfades the two by RPM and pitches both
  car_skid_loop    tyre squeal (narrow-band squeal partials over hiss), volume from the slip
  car_road_loop    rolling tyre roar on wet asphalt, volume / pitch from the speed
  car_horn_loop    two-tone horn while the horn is held
  car_fire_loop    a burning car (roar + crackle), pooled voices in VehicleDamage
One-shots (AudioManager, randomized takes): car_horn (short honk: bumped traffic), car_impact_v1..3 (crash: thump,
crunch, metal ring, debris), car_door_v1..2 (latch + thunk), car_scrape_v1..3 (metal on concrete), car_explode_v1..3
(the blast: sub thump, darkening broadband burst, crack, metal ring, debris rain), car_ignite (fuel whoosh), car_fuse
(rising hiss and ticking before the blast).

Writes mono 44.1 kHz 16-bit WAVs to unity/EchoesOfAether/Assets/Resources/Audio/SFX and their entries in
Assets/Resources/Audio/manifest.json (replacing earlier car_* entries).

  python3 tools/audio/vehicle_sfx.py
"""
import json, os, wave
import numpy as np

SR = 44100
HERE = os.path.dirname(os.path.abspath(__file__))
AUDIO = os.path.join(HERE, "..", "..", "unity", "EchoesOfAether", "Assets", "Resources", "Audio")
OUT = os.path.join(AUDIO, "SFX")
SOURCE = "tools/audio/vehicle_sfx.py (procedural)"


def t_axis(dur):
    return np.arange(int(round(SR * dur))) / SR


def env_exp(t, tau, attack=0.002):
    a = np.clip(t / max(attack, 1e-5), 0, 1)
    return a * np.exp(-t / tau)


def spectral(x, shape):
    """Circular (periodic) filtering: multiply the loop's spectrum by shape(freqs)."""
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    return np.fft.irfft(X * shape(f), len(x))


def band(f, lo, hi, slope=2.0):
    """Smooth band-pass gain (1 inside [lo, hi], rolling off by `slope` orders per octave outside)."""
    f = np.maximum(f, 1e-3)
    g = np.ones_like(f)
    g = np.where(f < lo, (f / lo) ** (slope * 2), g)
    g = np.where(f > hi, (hi / f) ** (slope * 2), g)
    return g


def peak(f, fc, q, gain):
    """Resonance: Lorentzian bump of `gain` at fc."""
    bw = fc / q
    return gain / (1 + ((f - fc) / (bw / 2)) ** 2)


def norm(x, peak_db, fade=True):
    x = x - np.mean(x)
    m = np.max(np.abs(x)) + 1e-9
    if fade:
        n = min(len(x), int(0.008 * SR))
        x[-n:] *= np.linspace(1, 0, n)
    return x / m * (10 ** (peak_db / 20))


def norm_loop(x, rms_db, ceiling_db=-1.0):
    x = x - np.mean(x)
    rms = np.sqrt(np.mean(x ** 2)) + 1e-9
    x = x * (10 ** (rms_db / 20) / rms)
    pk = np.max(np.abs(x))
    lim = 10 ** (ceiling_db / 20)
    if pk > lim:
        x = x * (lim / pk)
    return x


def lp1(x, fc):
    a = np.exp(-2 * np.pi * fc / SR)
    y = np.zeros_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc = (1 - a) * v + a * acc
        y[i] = acc
    return y


written = []


def write(name, x, loop=False):
    os.makedirs(OUT, exist_ok=True)
    pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    with wave.open(os.path.join(OUT, name + ".wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    f = pcm.astype(np.float64) / 32767
    written.append((name, len(pcm), loop, 20 * np.log10(np.max(np.abs(f)) + 1e-9), 20 * np.log10(np.sqrt(np.mean(f ** 2)) + 1e-9)))
    print("wrote", name, f"{len(x) / SR:.2f}s")


# ------------------------------------------------------------------------------------------------ loops

def engine(dur, f0, bright, whine, seed):
    """Firing pulse train (exactly f0 * dur pulses, per-pulse jitter) through exhaust / intake resonances."""
    rng = np.random.default_rng(seed)
    n = int(round(SR * dur))
    t = np.arange(n) / SR
    pulses = int(round(f0 * dur))
    period = n / pulses
    x = np.zeros(n)
    # One combustion event per pulse: a short decaying burst (low thump + a bit of noise), slight timing / level jitter.
    burst_n = int(period * 0.9)
    bt = np.arange(burst_n) / SR
    for k in range(pulses):
        start = int(round(k * period + rng.normal(0, period * 0.025))) % n
        amp = 1.0 + rng.normal(0, 0.12) + (0.18 if k % 4 == 0 else 0.0)  # one cylinder a touch louder: lope
        burst = np.exp(-bt / (period / SR * 0.28)) * (np.sin(2 * np.pi * f0 * 1.5 * bt) + 0.6 * rng.normal(0, 1, burst_n) * np.exp(-bt / 0.004))
        idx = (start + np.arange(burst_n)) % n
        x[idx] += amp * burst
    # Exhaust body: resonances (periodic filtering keeps the loop seamless).
    def shape(f):
        g = band(f, f0 * 0.5, 900 + 2600 * bright, 1.2)
        g = g * (0.35 + peak(f, 95, 1.6, 1.4) + peak(f, 260, 2.2, 0.9) + peak(f, 640, 3.0, 0.45 + 0.8 * bright) + peak(f, 1700, 4.0, 0.25 * bright))
        return g
    x = spectral(x, shape)
    # Rumble: low noise (periodic), and the motor whine of the hybrid drive (integer cycles per loop).
    rum = spectral(rng.normal(0, 1, n), lambda f: band(f, 30, 180, 1.5)) * 0.35
    w = np.zeros(n)
    for h, a in ((7, 1.0), (14, 0.35), (21, 0.15)):
        fw = round(f0 * h * dur) / dur
        w += a * np.sin(2 * np.pi * fw * t + rng.uniform(0, 6.28))
    w *= whine * (0.8 + 0.2 * np.sin(2 * np.pi * (round(3 * dur) / dur) * t))
    x = x / (np.std(x) + 1e-9) + rum / (np.std(rum) + 1e-9) * 0.35 + w * 0.6
    return x


def skid(dur, seed):
    rng = np.random.default_rng(seed)
    n = int(round(SR * dur))
    t = np.arange(n) / SR
    # Squeal: a few narrow noise bands (rubber stick-slip) whose level wobbles, over broadband hiss.
    sq = spectral(rng.normal(0, 1, n), lambda f: peak(f, 1150, 18, 1.0) + peak(f, 2310, 22, 0.55) + peak(f, 3480, 25, 0.25))
    wob = 0.65 + 0.35 * np.sin(2 * np.pi * (round(5.0 * dur) / dur) * t) * np.sin(2 * np.pi * (round(1.0 * dur) / dur) * t + 1.0)
    hiss = spectral(rng.normal(0, 1, n), lambda f: band(f, 700, 3200, 2.0))
    x = sq / np.std(sq) * wob + hiss / np.std(hiss) * 0.25
    return x


def road(dur, seed):
    rng = np.random.default_rng(seed)
    n = int(round(SR * dur))
    roar = spectral(rng.normal(0, 1, n), lambda f: band(f, 60, 420, 1.3) * (1 + peak(f, 180, 1.5, 0.8)))
    wet = spectral(rng.normal(0, 1, n), lambda f: band(f, 2200, 6000, 2.0))  # spray off wet asphalt
    return roar / np.std(roar) + wet / np.std(wet) * 0.16


def horn_tone(t, freqs):
    x = np.zeros_like(t)
    for f in freqs:
        for h in range(1, 12, 2):  # square-ish: odd harmonics
            x += np.sin(2 * np.pi * f * h * t) / h
    return x


def horn_loop(dur):
    n = int(round(SR * dur))
    t = np.arange(n) / SR
    x = horn_tone(t, (420.0, 525.0))
    return spectral(x, lambda f: band(f, 300, 2600, 1.2) * (1 + peak(f, 1050, 3, 0.8)))


# ------------------------------------------------------------------------------------------------ one-shots

def horn_honk(seed):
    rng = np.random.default_rng(seed)
    t = t_axis(0.5)
    a = np.clip(t / 0.012, 0, 1) * np.clip((0.5 - t) / 0.05, 0, 1)
    x = horn_tone(t, (420.0 * (1 + rng.normal(0, 0.004)), 525.0)) * a
    return norm(spectral(x, lambda f: band(f, 300, 2600, 1.2) * (1 + peak(f, 1050, 3, 0.8))), -4)


def metal(t, f0, ratios, taus, gains, rng):
    y = np.zeros_like(t)
    for r, tau, g in zip(ratios, taus, gains):
        f = f0 * r * (1 + rng.normal(0, 0.01))
        y += g * np.sin(2 * np.pi * f * t + rng.uniform(0, 6.28)) * np.exp(-t / tau)
    return y


def impact(seed):
    rng = np.random.default_rng(seed)
    t = t_axis(1.1)
    n = len(t)
    thump = np.sin(2 * np.pi * np.cumsum(38 + 70 * np.exp(-t / 0.05)) / SR) * env_exp(t, 0.16, 0.002) * 1.6
    crunch = spectral(rng.normal(0, 1, n), lambda f: band(f, 250, 3500, 1.0)) * env_exp(t, 0.09, 0.001)
    crunch /= np.std(crunch[: int(0.1 * SR)]) + 1e-9
    ring = metal(t, rng.uniform(260, 420), [1, 2.31, 3.92, 5.6], [0.35, 0.22, 0.14, 0.08], [0.5, 0.35, 0.25, 0.15], rng)
    debris = np.zeros(n)
    for _ in range(10):
        t0 = 0.05 + rng.uniform(0, 0.55) ** 1.5
        tt = np.clip(t - t0, 0, None)
        debris += np.sin(2 * np.pi * rng.uniform(1800, 5200) * tt) * env_exp(tt, rng.uniform(0.008, 0.03), 0.0005) * (t >= t0) * rng.uniform(0.1, 0.35)
    return norm(thump + crunch * 0.7 + ring + debris, -2)


def door(seed):
    rng = np.random.default_rng(seed)
    t = t_axis(0.42)
    n = len(t)
    click = spectral(rng.normal(0, 1, n), lambda f: band(f, 1800, 6000, 1.0)) * env_exp(t, 0.006, 0.0005)
    click /= np.max(np.abs(click)) + 1e-9
    t2 = np.clip(t - 0.035, 0, None)
    thunk = np.sin(2 * np.pi * np.cumsum(70 + 90 * np.exp(-t2 / 0.02)) / SR) * env_exp(t2, 0.07, 0.002) * (t >= 0.035)
    body = spectral(rng.normal(0, 1, n), lambda f: band(f, 120, 900, 1.2)) * env_exp(t2, 0.05, 0.002) * (t >= 0.035)
    body /= np.max(np.abs(body)) + 1e-9
    t3 = np.clip(t - 0.11 - rng.uniform(0, 0.03), 0, None)
    latch = spectral(rng.normal(0, 1, n), lambda f: band(f, 2500, 7000, 1.0)) * env_exp(t3, 0.004, 0.0003) * (t3 > 0)
    latch /= np.max(np.abs(latch)) + 1e-9
    return norm(click * 0.45 + thunk * 1.2 + body * 0.5 + latch * 0.3, -4)


def scrape(seed):
    rng = np.random.default_rng(seed)
    t = t_axis(0.32)
    n = len(t)
    grit = spectral(rng.normal(0, 1, n), lambda f: band(f, 1400, 6000, 1.0) * (1 + peak(f, 2900, 6, 1.2)))
    am = np.abs(lp1(rng.normal(0, 1, n), 60))
    am = am / (np.max(am) + 1e-9)
    x = grit / (np.std(grit) + 1e-9) * (0.4 + am) * np.clip(t / 0.02, 0, 1) * np.clip((0.32 - t) / 0.12, 0, 1)
    return norm(x, -8)


def explode(seed):
    """Car explosion: sub-bass thump, broadband blast decaying through a closing low-pass, metal ring, debris rain."""
    rng = np.random.default_rng(seed)
    t = t_axis(3.2)
    n = len(t)
    boom = np.sin(2 * np.pi * np.cumsum(28 + 90 * np.exp(-t / 0.08)) / SR) * env_exp(t, 0.55, 0.004) * 2.2
    blast = rng.normal(0, 1, n)
    # Darkening blast: spectrum shaped per segment (bright crack first, rumble tail).
    out = np.zeros(n)
    seg = int(0.05 * SR)
    for i in range(0, n, seg):
        j = min(n, i + seg)
        tc = i / SR
        hi = 6000 * np.exp(-tc / 0.18) + 260
        piece = blast[i:j]
        piece = np.fft.irfft(np.fft.rfft(piece) * band(np.fft.rfftfreq(len(piece), 1 / SR), 30, hi, 1.0), len(piece))
        out[i:j] = piece
    out = out / (np.std(out[: int(0.3 * SR)]) + 1e-9) * env_exp(t, 0.7, 0.002)
    crack = spectral(rng.normal(0, 1, n), lambda f: band(f, 1500, 9000, 1.0)) * env_exp(t, 0.03, 0.0005)
    crack /= np.max(np.abs(crack)) + 1e-9
    ring = metal(t, rng.uniform(180, 300), [1, 2.4, 3.9], [0.6, 0.35, 0.2], [0.4, 0.25, 0.15], rng)
    debris = np.zeros(n)
    for _ in range(26):
        t0 = 0.25 + rng.uniform(0, 2.2) ** 1.2
        tt = np.clip(t - t0, 0, None)
        debris += np.sin(2 * np.pi * rng.uniform(900, 4200) * tt) * env_exp(tt, rng.uniform(0.01, 0.04), 0.0005) * (t >= t0) * rng.uniform(0.05, 0.25)
    return norm(boom + out * 0.9 + crack * 0.6 + ring * 0.5 + debris, -1)


def ignite(seed):
    """Fuel catching: a rising whoosh."""
    rng = np.random.default_rng(seed)
    t = t_axis(1.1)
    n = len(t)
    x = rng.normal(0, 1, n)
    out = np.zeros(n)
    seg = int(0.04 * SR)
    for i in range(0, n, seg):
        j = min(n, i + seg)
        u = i / n
        piece = np.fft.irfft(np.fft.rfft(x[i:j]) * band(np.fft.rfftfreq(j - i, 1 / SR), 120, 400 + 2600 * u, 1.2), j - i)
        out[i:j] = piece
    a = np.clip(t / 0.5, 0, 1) ** 2 * np.clip((1.1 - t) / 0.45, 0, 1)
    thump = np.sin(2 * np.pi * 55 * t) * env_exp(np.clip(t - 0.45, 0, None), 0.2, 0.01) * (t > 0.45)
    return norm(out * a + thump * 0.6, -4)


def fire_loop(dur, seed):
    """Burning car: low roar plus random crackles (exactly periodic)."""
    rng = np.random.default_rng(seed)
    n = int(round(SR * dur))
    t = np.arange(n) / SR
    roar = spectral(rng.normal(0, 1, n), lambda f: band(f, 60, 700, 1.4))
    roar /= np.std(roar)
    cr = np.zeros(n)
    for _ in range(int(dur * 38)):
        t0 = int(rng.uniform(0, n))
        ln = int(rng.uniform(0.002, 0.012) * SR)
        idx = (t0 + np.arange(ln)) % n
        cr[idx] += rng.normal(0, 1, ln) * np.exp(-np.arange(ln) / (ln * 0.3)) * rng.uniform(0.3, 1.2)
    cr = spectral(cr, lambda f: band(f, 900, 7000, 1.0))
    cr /= np.std(cr) + 1e-9
    wob = 0.8 + 0.2 * np.sin(2 * np.pi * (round(0.7 * dur) / dur) * t)
    return roar * wob + cr * 0.55


def fuse(seed):
    """Warning before the blast: hissing that rises, with a fast electrical tick."""
    rng = np.random.default_rng(seed)
    t = t_axis(2.4)
    n = len(t)
    hiss = spectral(rng.normal(0, 1, n), lambda f: band(f, 2500, 8000, 1.0))
    hiss /= np.std(hiss)
    a = np.clip(t / 2.2, 0, 1) ** 1.5
    ticks = np.zeros(n)
    tt = 0.0
    while tt < 2.3:
        k = int(tt * SR)
        ln = int(0.006 * SR)
        ticks[k:k + ln] += np.sin(2 * np.pi * 2200 * np.arange(ln) / SR) * np.exp(-np.arange(ln) / (ln * 0.4))
        tt += 0.22 - 0.16 * min(1.0, tt / 2.2)
    return norm(hiss * a * 0.6 + ticks * 0.8, -6)


def main():
    write("car_engine_low", norm_loop(engine(2.0, 40.0, 0.2, 0.06, 1), -18), loop=True)
    write("car_engine_high", norm_loop(engine(2.0, 110.0, 0.8, 0.14, 2), -18), loop=True)
    write("car_skid_loop", norm_loop(skid(1.5, 3), -18), loop=True)
    write("car_road_loop", norm_loop(road(2.0, 4), -20), loop=True)
    write("car_horn_loop", norm_loop(horn_loop(1.0), -16), loop=True)
    for v in range(2):
        write(f"car_horn_v{v + 1}", horn_honk(10 + v))
    for v in range(3):
        write(f"car_impact_v{v + 1}", impact(20 + v))
        write(f"car_scrape_v{v + 1}", scrape(40 + v))
    for v in range(2):
        write(f"car_door_v{v + 1}", door(30 + v))
    for v in range(3):
        write(f"car_explode_v{v + 1}", explode(50 + v))
    write("car_ignite", ignite(60))
    write("car_fuse", fuse(61))
    write("car_fire_loop", norm_loop(fire_loop(3.0, 62), -18), loop=True)

    # Manifest: one entry per id (loops are played by CarAudio directly; one-shots through AudioManager).
    path = os.path.join(AUDIO, "manifest.json")
    with open(path, encoding="utf-8") as f:
        man = json.load(f)
    groups = {}
    for name, samples, loop, pk, rms in written:
        cid = name.rsplit("_v", 1)[0] if "_v" in name and name.rsplit("_v", 1)[1].isdigit() else name
        groups.setdefault(cid, []).append((name, samples, loop, pk, rms))
    gains = {"car_impact": 0.9, "car_door": 0.55, "car_horn": 0.6, "car_scrape": 0.5, "car_explode": 1.0, "car_ignite": 0.7, "car_fuse": 0.6}
    man["clips"] = [c for c in man["clips"] if not c["id"].startswith("car_")]
    for cid, files in groups.items():
        loop = files[0][2]
        man["clips"].append({
            "id": cid, "kind": "sfx", "bus": "sfx", "loop": loop, "randomized": len(files) > 1,
            "files": [{"path": "SFX/" + n, "samples": s, "duration": round(s / SR, 4), "peakDb": round(p, 2), "rmsDb": round(r, 2),
                       "gain": 1.0 if loop else gains.get(cid, 0.7)} for n, s, _, p, r in files],
            "source": SOURCE,
        })
    with open(path, "w", encoding="utf-8") as f:
        json.dump(man, f, indent=1, ensure_ascii=False)
    print("manifest:", ", ".join(groups))


if __name__ == "__main__":
    main()
