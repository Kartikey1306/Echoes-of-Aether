"""Side-by-side comparison sheets (plain python + PIL): concept | image [| image ...], same height, labelled.

  python3 compose_cmp.py out.png concept.png img1.png [img2.png ...] [--labels "Concept,Blender,Unity"] [--crop x0,y0,x1,y1 ...]
"""
import sys
from PIL import Image, ImageDraw

args = sys.argv[1:]
labels = None
if "--labels" in args:
    i = args.index("--labels"); labels = args[i + 1].split(","); del args[i:i + 2]
out, imgs = args[0], args[1:]
H = 1200
tiles = []
for p in imgs:
    im = Image.open(p).convert("RGB")
    # trim uniform backdrop margins left/right so the figure fills the tile
    w = int(im.width * H / im.height)
    tiles.append(im.resize((w, H), Image.LANCZOS))
W = sum(t.width for t in tiles) + 16 * (len(tiles) - 1)
sheet = Image.new("RGB", (W, H + (40 if labels else 0)), (24, 24, 28))
x = 0
d = ImageDraw.Draw(sheet)
for k, t in enumerate(tiles):
    sheet.paste(t, (x, 40 if labels else 0))
    if labels and k < len(labels):
        d.text((x + 12, 12), labels[k], fill=(230, 230, 235))
    x += t.width + 16
sheet.save(out)
print("CMP", out, sheet.size)
