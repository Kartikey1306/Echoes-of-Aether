"""Contact sheets for review (system python3 with Pillow).

  python3 blender/custom/contact.py <out.png> <cols> <cell_px> <title> <img|label> [<img|label> ...]
  python3 blender/custom/contact.py --glob <out.png> <cols> <cell_px> <title> <pattern>   (label = file stem)
Each argument is an image path, optionally followed by '|label'. Rows of related views can be passed as
'a.png+b.png+c.png|label' (side by side in one cell).
"""
import sys, os, glob
from PIL import Image, ImageDraw, ImageFont


def font(sz):
    for p in ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc", "/Library/Fonts/Arial.ttf"):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, sz)
            except Exception:
                pass
    return ImageFont.load_default()


def sheet(out, cols, cell, title, items):
    f = font(max(12, cell // 16)); ft = font(max(16, cell // 10))
    cells = []
    for it in items:
        paths, _, label = it.partition("|")
        ims = [Image.open(p).convert("RGB") for p in paths.split("+") if os.path.exists(p)]
        if not ims:
            continue
        w = cell * len(ims)
        c = Image.new("RGB", (w, cell + cell // 9), (12, 13, 16))
        for k, im in enumerate(ims):
            im = im.resize((cell, cell), Image.LANCZOS)
            c.paste(im, (k * cell, 0))
        d = ImageDraw.Draw(c)
        d.text((6, cell + 2), label or os.path.splitext(os.path.basename(paths.split("+")[0]))[0], fill=(220, 225, 235), font=f)
        cells.append(c)
    if not cells:
        return
    cw = max(c.width for c in cells); ch = max(c.height for c in cells)
    rows = (len(cells) + cols - 1) // cols
    th = cell // 6
    S = Image.new("RGB", (cw * cols, ch * rows + th), (6, 7, 9))
    d = ImageDraw.Draw(S)
    d.text((8, 4), title, fill=(120, 230, 255), font=ft)
    for i, c in enumerate(cells):
        S.paste(c, ((i % cols) * cw, th + (i // cols) * ch))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    S.save(out, optimize=True)
    print("SHEET", out, S.size)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[0] == "--glob":
        out, cols, cell, title, pat = a[1], int(a[2]), int(a[3]), a[4], a[5]
        items = sorted(glob.glob(pat))
        sheet(out, cols, cell, title, items)
    else:
        sheet(a[0], int(a[1]), int(a[2]), a[3], a[4:])
