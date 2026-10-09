#!/usr/bin/env python3
"""Procedural weapon one-shots for Echoes of Aether (no samples, no AI): FM, filtered noise and struck-metal partials.

Writes mono 44.1 kHz 16-bit WAVs to unity/EchoesOfAether/Assets/Resources/Audio/SFX/<id>[_v<n>].wav, loaded by
AudioManager's naming convention (gain 1.0; levels baked in to sit with combat_sfx.py).

  python3 tools/audio/weapon_sfx.py

ids: pistol_shot, pistol_draw, pistol_holster, casing_tink, blade_ignite, blade_retract, claw_extend, gauntlet_shot,
     blaster_shot, impact_energy, cannon_charge, blade_deploy, parry_spark
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from combat_sfx import (SR, OUT, t_axis, env_exp, onepole_lp, svf_bandpass, highpass, norm, write, metal)  # noqa: E402


def fm(t, f, ratio, index):
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph + index * np.sin(ph * ratio))


def pistol_shot(seed):
    """Aether pistol: a hard transient crack, a descending FM 'zap' body and a short coil whine tail."""
    rng = np.random.default_rng(seed)
    t = t_axis(0.42)
    crack = highpass(rng.normal(0, 1, len(t)), 1800) * env_exp(t, 0.006, 0.0002) * 2.2
    f = 1500 * np.exp(-t / 0.03) + 180 + rng.uniform(-8, 8)
    body = fm(t, f, 1.48, 4 * np.exp(-t / 0.04) + 0.6) * env_exp(t, 0.09, 0.0006)
    thump = np.sin(2 * np.pi * np.cumsum(120 * np.exp(-t / 0.05) + 55) / SR) * env_exp(t, 0.05, 0.001) * 1.3
    whine = np.sin(2 * np.pi * np.cumsum(5200 - 1800 * t) / SR) * env_exp(t, 0.14, 0.004) * 0.12
    y = crack + body * 0.9 + thump + whine
    d = int(0.018 * SR)
    tail = np.zeros_like(y)
    tail[d:] = onepole_lp(y[:-d], 2500) * 0.3
    return norm(y + tail, -3)


def gauntlet_shot(seed):
    """Giva's palm blast: a softer pulse with a rising shimmer and a sub thump."""
    rng = np.random.default_rng(seed)
    t = t_axis(0.38)
    f = 420 + 900 * np.exp(-t / 0.05)
    body = fm(t, f, 2.01, 2.5 * np.exp(-t / 0.06)) * env_exp(t, 0.1, 0.002)
    air = svf_bandpass(rng.normal(0, 1, len(t)), 2200 + 2500 * np.exp(-t / 0.04), 2.2) * env_exp(t, 0.05, 0.001) * 1.2
    sub = np.sin(2 * np.pi * np.cumsum(90 * np.exp(-t / 0.06) + 45) / SR) * env_exp(t, 0.07, 0.002)
    sparkle = sum(np.sin(2 * np.pi * f0 * t + k) * env_exp(t, 0.08, 0.004) * 0.08 for k, f0 in enumerate((2637, 3520, 4699)))
    return norm(body + air + sub + sparkle, -4)


def pistol_draw(seed):
    """Polymer-on-holster slide and a metallic charge-up chirp."""
    rng = np.random.default_rng(seed)
    t = t_axis(0.3)
    u = t / 0.3
    slide = svf_bandpass(rng.normal(0, 1, len(t)), 1400 + 1800 * u, 1.5) * np.sin(np.pi * np.clip(u / 0.55, 0, 1)) * 0.6
    chirp = np.sin(2 * np.pi * np.cumsum(900 + 2600 * np.clip((u - 0.45) / 0.5, 0, 1)) / SR) * (u > 0.45) * env_exp(np.clip(t - 0.14, 0, None), 0.08, 0.004) * 0.35
    click = metal(np.clip(t - 0.12, 0, None), 2400, [1, 2.7, 5.1], [0.02, 0.012, 0.008], [1, 0.5, 0.3], rng) * (t > 0.12) * 0.8
    return norm(slide + chirp + click, -12)


def pistol_holster(seed):
    rng = np.random.default_rng(seed)
    t = t_axis(0.26)
    u = t / 0.26
    slide = svf_bandpass(rng.normal(0, 1, len(t)), 2400 - 1400 * u, 1.5) * np.sin(np.pi * np.clip(u / 0.6, 0, 1)) * 0.5
    seat = metal(np.clip(t - 0.15, 0, None), 1500, [1, 2.4, 4.6], [0.03, 0.02, 0.01], [1, 0.5, 0.3], rng) * (t > 0.15)
    thud = np.sin(2 * np.pi * 160 * t) * env_exp(np.clip(t - 0.15, 0, None), 0.02) * (t > 0.15) * 0.6
    return norm(slide + seat + thud, -13)


def casing_tink(seed):
    rng = np.random.default_rng(seed)
    t = t_axis(0.25)
    y = metal(t, rng.uniform(3600, 4600), [1, 1.52, 2.73, 3.9], [0.07, 0.05, 0.03, 0.02], [1, 0.6, 0.4, 0.25], rng)
    return norm(y + highpass(rng.normal(0, 1, len(t)), 5000) * env_exp(t, 0.002, 0.0001) * 0.5, -14)


def blade_ignite(seed):
    """Hard-light blade forming: rising buzz + crackle into a steady hum."""
    rng = np.random.default_rng(seed)
    t = t_axis(0.55)
    u = np.clip(t / 0.12, 0, 1)
    f = 90 + 70 * u
    ph = 2 * np.pi * np.cumsum(f) / SR
    hum = (np.sin(ph) + 0.6 * np.sin(2 * ph + 0.3) + 0.35 * np.sign(np.sin(3 * ph)) * 0.4) * (u ** 0.5) * env_exp(np.clip(t - 0.1, 0, None), 0.35, 0.001)
    rise = np.sin(2 * np.pi * np.cumsum(400 + 3200 * u ** 2) / SR) * np.clip(1 - t / 0.16, 0, 1) * 0.35
    crackle = (rng.random(len(t)) < 0.03).astype(float) * rng.normal(0, 1, len(t))
    crackle = svf_bandpass(crackle, 3000, 2.0) * env_exp(t, 0.12, 0.002) * 2.5
    return norm(hum * 0.6 + rise + crackle, -12)


def blade_retract(seed):
    rng = np.random.default_rng(seed)
    t = t_axis(0.3)
    u = t / 0.3
    f = 160 * (1 - 0.6 * u) + 40
    ph = 2 * np.pi * np.cumsum(f) / SR
    hum = (np.sin(ph) + 0.5 * np.sin(2 * ph)) * (1 - u) ** 1.5
    fall = np.sin(2 * np.pi * np.cumsum(2600 * (1 - u) + 200) / SR) * (1 - u) ** 2 * 0.25
    air = svf_bandpass(rng.normal(0, 1, len(t)), 1800 - 1200 * u, 1.4) * (1 - u) ** 2 * 0.4
    return norm(hum * 0.6 + fall + air, -16)


def claw_extend(seed):
    """Three quick hard-light 'shing's for the claws."""
    rng = np.random.default_rng(seed)
    t = t_axis(0.35)
    y = np.zeros_like(t)
    for k in range(3):
        t0 = 0.018 * k + rng.uniform(0, 0.006)
        tt = np.clip(t - t0, 0, None)
        f = 3800 + 900 * k - 1600 * np.exp(-tt / 0.02)
        y += np.sin(2 * np.pi * np.cumsum(f) / SR) * env_exp(tt, 0.06, 0.001) * (t >= t0) * 0.4
        y += svf_bandpass(rng.normal(0, 1, len(t)), 5200, 3.0) * env_exp(tt, 0.02, 0.0005) * (t >= t0) * 0.5
    hum = np.sin(2 * np.pi * 230 * t) * env_exp(t, 0.12, 0.01) * 0.3
    return norm(y + hum, -13)


def blaster_shot(seed):
    """Drone blaster: snappy pew with a buzzy square-ish body."""
    rng = np.random.default_rng(seed)
    t = t_axis(0.3)
    f = 2200 * np.exp(-t / 0.025) + 320 + rng.uniform(-20, 20)
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.tanh(3 * np.sin(ph)) * env_exp(t, 0.06, 0.0005)
    crack = highpass(rng.normal(0, 1, len(t)), 2500) * env_exp(t, 0.004, 0.0002) * 1.4
    return norm(body * 0.8 + crack, -7)


def impact_energy(seed):
    rng = np.random.default_rng(seed)
    t = t_axis(0.35)
    burst = svf_bandpass(rng.normal(0, 1, len(t)), 2400 * np.exp(-t / 0.05) + 400, 1.2) * env_exp(t, 0.05, 0.0005) * 1.6
    sizzle = svf_bandpass((rng.random(len(t)) < 0.05).astype(float) * rng.normal(0, 1, len(t)), 6000, 2.0) * env_exp(t, 0.12, 0.002) * 3
    thump = np.sin(2 * np.pi * np.cumsum(140 * np.exp(-t / 0.04) + 60) / SR) * env_exp(t, 0.05, 0.001)
    return norm(burst + sizzle + thump, -7)


def cannon_charge(seed):
    """Guardian arm cannon spooling up before the beam: rising FM drone with capacitor ticks."""
    rng = np.random.default_rng(seed)
    t = t_axis(0.95)
    u = t / 0.95
    f = 55 + 220 * u ** 1.6
    drone = fm(t, f, 1.5, 1.5 + 3 * u) * (0.2 + 0.8 * u) * np.clip((1 - u) / 0.06, 0, 1)
    whine = np.sin(2 * np.pi * np.cumsum(600 + 3400 * u ** 2) / SR) * u ** 2 * 0.25
    ticks = np.zeros_like(t)
    for k in range(10):
        t0 = 0.95 * (1 - (1 - k / 10) ** 0.6)
        tt = np.clip(t - t0, 0, None)
        ticks += metal(tt, 1800 + 200 * k, [1, 2.3], [0.015, 0.01], [1, 0.4], rng) * (t >= t0) * 0.3
    return norm(drone + whine + ticks, -6)


def blade_deploy(seed):
    """Heavy mechanical fold-out: servo whine, latch clank, ringing steel."""
    rng = np.random.default_rng(seed)
    t = t_axis(0.8)
    u = t / 0.8
    servo = np.sin(2 * np.pi * np.cumsum(180 + 500 * np.clip(u / 0.4, 0, 1)) / SR) * np.clip(u / 0.05, 0, 1) * np.clip((0.42 - u) / 0.05, 0, 1) * 0.3
    servo += svf_bandpass(rng.normal(0, 1, len(t)), 900, 2.0) * np.clip((0.42 - u) / 0.42, 0, 1) * 0.25
    clank = metal(np.clip(t - 0.34, 0, None), 320, [1, 2.76, 5.4, 8.9], [0.25, 0.16, 0.1, 0.06], [1, 0.7, 0.45, 0.3], rng) * (t > 0.34)
    hit = np.sin(2 * np.pi * np.cumsum(90 * np.exp(-np.clip(t - 0.34, 0, None) / 0.08) + 40) / SR) * env_exp(np.clip(t - 0.34, 0, None), 0.1, 0.001) * (t > 0.34)
    return norm(servo + clank + hit * 1.2, -5)


def parry_spark(seed):
    rng = np.random.default_rng(seed)
    t = t_axis(0.4)
    zing = np.sin(2 * np.pi * np.cumsum(5200 - 2500 * np.clip(t / 0.25, 0, 1)) / SR) * env_exp(t, 0.1, 0.001) * 0.4
    sparks = np.zeros_like(t)
    for _ in range(14):
        t0 = rng.uniform(0, 0.18)
        tt = np.clip(t - t0, 0, None)
        sparks += np.sin(2 * np.pi * rng.uniform(4000, 9000) * tt) * env_exp(tt, rng.uniform(0.005, 0.02), 0.0003) * (t >= t0) * rng.uniform(0.2, 0.5)
    snap = highpass(rng.normal(0, 1, len(t)), 3000) * env_exp(t, 0.004, 0.0002) * 1.5
    return norm(zing + sparks + snap, -7)


IDS = ["pistol_shot", "gauntlet_shot", "casing_tink", "blaster_shot", "impact_energy", "parry_spark", "pistol_draw",
       "pistol_holster", "blade_ignite", "blade_retract", "claw_extend", "cannon_charge", "blade_deploy"]
MANIFEST = os.path.join(OUT, "..", "manifest.json")


def update_manifest():
    """Merge the weapon clips into Resources/Audio/manifest.json (replaces entries with the same id, keeps the rest)."""
    import json
    import wave
    with open(MANIFEST, encoding="utf-8") as f:
        man = json.load(f)
    clips = [c for c in man["clips"] if c.get("id") not in IDS]
    for cid in IDS:
        files = []
        names = [f"{cid}.wav"] if os.path.exists(os.path.join(OUT, cid + ".wav")) else [f"{cid}_v{v}.wav" for v in range(1, 5) if os.path.exists(os.path.join(OUT, f"{cid}_v{v}.wav"))]
        for n in names:
            with wave.open(os.path.join(OUT, n)) as w:
                frames = w.getnframes()
                a = np.frombuffer(w.readframes(frames), np.int16).astype(np.float64) / 32767
            peak = 20 * np.log10(max(1e-9, np.abs(a).max()))
            rms = 20 * np.log10(max(1e-9, np.sqrt(np.mean(a * a))))
            files.append({"path": "SFX/" + n[:-4], "samples": frames, "duration": round(frames / SR, 4),
                          "peakDb": round(float(peak), 2), "rmsDb": round(float(rms), 2), "gain": 1.0})
        clips.append({"id": cid, "kind": "sfx", "bus": "sfx", "loop": False, "randomized": len(files) > 1, "files": files,
                      "source": "tools/audio/weapon_sfx.py (procedural)"})
    man["clips"] = clips
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(man, f, indent=1, ensure_ascii=False)
        f.write("\n")
    print("manifest: merged", len(IDS), "weapon clips")


def main():
    for v in range(3):
        write(f"pistol_shot_v{v + 1}", pistol_shot(100 + v))
        write(f"gauntlet_shot_v{v + 1}", gauntlet_shot(110 + v))
        write(f"casing_tink_v{v + 1}", casing_tink(120 + v))
        write(f"blaster_shot_v{v + 1}", blaster_shot(130 + v))
        write(f"impact_energy_v{v + 1}", impact_energy(140 + v))
        write(f"parry_spark_v{v + 1}", parry_spark(150 + v))
    for v in range(2):
        write(f"pistol_draw_v{v + 1}", pistol_draw(160 + v))
        write(f"pistol_holster_v{v + 1}", pistol_holster(170 + v))
        write(f"blade_ignite_v{v + 1}", blade_ignite(180 + v))
        write(f"blade_retract_v{v + 1}", blade_retract(190 + v))
        write(f"claw_extend_v{v + 1}", claw_extend(200 + v))
    write("cannon_charge", cannon_charge(210))
    write("blade_deploy", blade_deploy(220))
    update_manifest()


if __name__ == "__main__":
    main()
