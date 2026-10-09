"""Voice-over for every scripted line (tools/vo/vo_lines.csv) with Kokoro-82M (Apache-2.0, offline ONNX).

Writes unity/EchoesOfAether/Assets/Resources/<file> (16-bit mono WAV, 24 kHz). Robots get a ring-modulated,
band-limited treatment. Re-run after script changes: tools/vo/.venv/bin/python tools/vo/gen_voices.py
"""
import csv, os, sys
import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
RES = os.path.join(ROOT, "unity", "EchoesOfAether", "Assets", "Resources")

# speaker -> (voice, speed, robot)
VOICES = {
    "kael": ("am_michael", 0.98, False),
    "lyra": ("af_heart", 1.0, False),       # Giva Vale
    "maren": ("bf_emma", 0.95, False),
    "oren": ("bm_george", 0.92, False),
    "tomas": ("am_eric", 1.0, False),
    "mira": ("af_nova", 1.03, False),
    "nia": ("af_sky", 1.05, False),
    "narrator": ("bm_fable", 0.9, False),
    "pa": ("am_echo", 0.95, True),
    "vendor": ("am_puck", 1.05, False),
    "bolt": ("am_echo", 1.05, True),
    "tech": ("am_liam", 1.0, False),
    "researcher": ("bf_isabella", 0.97, False),
    "parent": ("af_kore", 0.95, False),
    "guardian": ("am_onyx", 0.82, True),
    "anya": ("af_aoede", 1.0, False),
    "speaker": ("am_adam", 0.97, True),
}

def robotize(x, sr, deep=False):
    t = np.arange(len(x)) / sr
    mod = 0.65 + 0.35 * np.sin(2 * np.pi * (38 if deep else 55) * t)
    y = x * mod
    # light comb filter for a metallic resonance
    d = int(sr * 0.0045)
    y[d:] += 0.35 * y[:-d]
    return y / max(1e-6, np.abs(y).max()) * 0.9

def main():
    k = Kokoro(os.path.join(HERE, "models", "kokoro-v1.0.onnx"), os.path.join(HERE, "models", "voices-v1.0.bin"))
    rows = list(csv.DictReader(open(os.path.join(HERE, "vo_lines.csv"), encoding="utf-8")))
    only = set(sys.argv[1:])
    done = 0
    for r in rows:
        spk = r["speaker"]
        if only and spk not in only: continue
        voice, speed, robot = VOICES.get(spk, ("am_adam", 1.0, False))
        text = r["text"].strip()
        if not text: continue
        out = os.path.join(RES, r["file"])
        os.makedirs(os.path.dirname(out), exist_ok=True)
        samples, sr = k.create(text, voice=voice, speed=speed, lang="en-gb" if voice.startswith("b") else "en-us")
        x = np.asarray(samples, dtype=np.float32)
        if robot: x = robotize(x, sr, deep=(spk == "guardian"))
        # gentle fade in/out, 120 ms tail of silence
        f = int(sr * 0.01)
        x[:f] *= np.linspace(0, 1, f); x[-f:] *= np.linspace(1, 0, f)
        x = np.concatenate([x, np.zeros(int(sr * 0.12), np.float32)])
        peak = np.abs(x).max()
        if peak > 0: x = x / peak * 0.89
        sf.write(out, x, sr, subtype="PCM_16")
        done += 1
        if done % 20 == 0: print(f"{done} lines", flush=True)
    print(f"done: {done} lines")

if __name__ == "__main__":
    main()
