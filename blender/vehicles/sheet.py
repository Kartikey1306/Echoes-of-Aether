"""Contact sheets (python3 + Pillow): `python3 sheet.py renders <out.png> img...` or `python3 sheet.py textures <out.png>`."""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

import vpaths


def font(sz):
    for p in ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc"):
        if os.path.exists(p):
            return ImageFont.truetype(p, sz)
    return ImageFont.load_default()


def grid(paths, out, cols=2, cell=(960, 540), labels=None):
    rows = (len(paths) + cols - 1) // cols
    W, H = cell
    sheet = Image.new("RGB", (cols * W, rows * H), (12, 12, 14))
    d = ImageDraw.Draw(sheet)
    f = font(max(14, H // 26))
    for i, p in enumerate(paths):
        im = Image.open(p).convert("RGB")
        im.thumbnail((W, H))
        x, y = (i % cols) * W, (i // cols) * H
        sheet.paste(im, (x + (W - im.width) // 2, y + (H - im.height) // 2))
        lab = labels[i] if labels else os.path.splitext(os.path.basename(p))[0]
        d.rectangle([x, y + H - f.size - 14, x + W, y + H], fill=(0, 0, 0))
        d.text((x + 10, y + H - f.size - 9), lab, fill=(230, 230, 235), font=f)
    sheet.save(out, optimize=True)
    print("wrote", out, sheet.size)


def textures(out):
    items = []
    for d in sorted(os.listdir(vpaths.TEXTURES)):
        full = os.path.join(vpaths.TEXTURES, d)
        if not os.path.isdir(full):
            continue
        for f in sorted(os.listdir(full)):
            if f.endswith(".png") and ("BaseColor" in f or "Emission" in f or "Normal" in f):
                items.append(os.path.join(full, f))
    grid(items, out, cols=8, cell=(256, 256))


if __name__ == "__main__":
    if sys.argv[1] == "textures":
        textures(sys.argv[2])
    else:
        grid(sys.argv[3:], sys.argv[2], cols=int(os.environ.get("COLS", 2)))
