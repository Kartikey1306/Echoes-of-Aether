"""Compose the preview frames rendered by blender/anim/cmu_retarget.py --preview into strips, a contact sheet and GIFs.

python3 tools/anim/previews.py [--gif clip1,clip2] [--sheet] [style_clip ...]

Input:  blender/anim/previews/frames/<style>_<clip>/NNNN.png (+ info.json)
Output: blender/anim/previews/<style>_<clip>.png         (frame strip with frame numbers and event marks)
        blender/anim/previews/<style>_<clip>.gif         (with --gif, needs every frame: render with --frames all)
        blender/anim/previews/contact_<style>.png        (with --sheet: first strip row of every clip)
"""
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
PREV = os.path.join(ROOT, "blender", "anim", "previews")
FR = os.path.join(PREV, "frames")


def font(size):
    for p in ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc", "/Library/Fonts/Arial.ttf"):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                pass
    return ImageFont.load_default()


def load(d):
    info = json.load(open(os.path.join(d, "info.json")))
    files = sorted(f for f in os.listdir(d) if f.endswith(".png"))
    return info, [(int(f[:-4]), Image.open(os.path.join(d, f)).convert("RGB")) for f in files]


def strip(key, max_frames=12, scale=0.6):
    d = os.path.join(FR, key)
    info, frames = load(d)
    if len(frames) > max_frames:
        step = len(frames) / max_frames
        frames = [frames[int(i * step)] for i in range(max_frames)]
    w, h = frames[0][1].size
    w2, h2 = int(w * scale), int(h * scale)
    head = 26
    img = Image.new("RGB", (w2 * len(frames), h2 + head), (24, 26, 30))
    dr = ImageDraw.Draw(img)
    f1, f2 = font(15), font(12)
    ev = info.get("events", [])
    dr.text((6, 5), f"{info['style']} {info['clip']}  {info['duration']:.2f}s  {'loop' if info['loop'] else 'once'}"
                    + (f"  {info['speed']} m/s" if info.get("speed") else "")
                    + ("  events: " + ", ".join(f"{n}@{t:.2f}" for n, t in ev) if ev else ""), fill=(235, 235, 235), font=f1)
    for i, (k, im) in enumerate(frames):
        img.paste(im.resize((w2, h2), Image.LANCZOS), (i * w2, head))
        t = k / info["fps"]
        mark = [n for n, te in ev if abs(te - t) < 0.5 / info["fps"] + 1e-6]
        dr.text((i * w2 + 4, head + 3), f"{k} ({t:.2f}s)" + (" " + ",".join(mark) if mark else ""), fill=(255, 220, 90) if mark else (20, 20, 20), font=f2)
    out = os.path.join(PREV, f"{key}.png")
    img.save(out, optimize=True)
    return out, img


def gif(key, scale=0.5):
    d = os.path.join(FR, key)
    info, frames = load(d)
    ims = [im.resize((int(im.size[0] * scale), int(im.size[1] * scale)), Image.LANCZOS).quantize(colors=64) for _, im in frames]
    out = os.path.join(PREV, f"{key}.gif")
    loops = 3 if info["loop"] and info["duration"] < 1.2 else 1
    seq = ims * loops if info["loop"] else ims + [ims[-1]] * 10
    seq[0].save(out, save_all=True, append_images=seq[1:], duration=int(1000 / info["fps"]), loop=0, optimize=True)
    return out


def sheet(style, keys):
    rows = []
    for k in keys:
        try:
            _, img = strip(k, max_frames=8, scale=0.45)
            rows.append(img)
        except Exception as e:  # noqa
            print("skip", k, e)
    if not rows:
        return None
    w = max(r.size[0] for r in rows)
    h = sum(r.size[1] for r in rows)
    out = Image.new("RGB", (w, h), (24, 26, 30))
    y = 0
    for r in rows:
        out.paste(r, (0, y))
        y += r.size[1]
    p = os.path.join(PREV, f"contact_{style}.png")
    out.save(p, optimize=True)
    return p


if __name__ == "__main__":
    a = sys.argv[1:]
    gifs = []
    if "--gif" in a:
        gifs = a[a.index("--gif") + 1].split(",")
        a = [x for x in a if x not in ("--gif", ",".join(gifs))]
    do_sheet = "--sheet" in a
    a = [x for x in a if x != "--sheet"]
    keys = a or sorted(os.listdir(FR))
    for k in keys:
        if os.path.isdir(os.path.join(FR, k)):
            print(strip(k)[0])
    for g in gifs:
        print(gif(g))
    if do_sheet:
        for st in ("male", "female"):
            ks = [k for k in sorted(os.listdir(FR)) if k.startswith(st + "_")]
            if ks:
                print(sheet(st, ks))
