"""Contact sheet: python3 sheet.py out.png img1 img2 ... [--h 600] [--cols N] (labels = file stems)."""
import sys, os
from PIL import Image, ImageDraw, ImageFont
a = sys.argv[1:]
h = 600; cols = None
if "--h" in a: i = a.index("--h"); h = int(a[i+1]); del a[i:i+2]
if "--cols" in a: i = a.index("--cols"); cols = int(a[i+1]); del a[i:i+2]
out, files = a[0], [f for f in a[1:] if os.path.exists(f)]
ims = []
for f in files:
    im = Image.open(f).convert("RGB"); w = int(im.width * h / im.height); ims.append((im.resize((w, h), Image.LANCZOS), os.path.basename(f)[:-4]))
cols = cols or len(ims)
rows = [ims[i:i+cols] for i in range(0, len(ims), cols)]
W = max(sum(im.width for im, _ in r) for r in rows); H = len(rows) * (h + 24)
sheet = Image.new("RGB", (W, H), (12, 12, 16)); d = ImageDraw.Draw(sheet)
try: font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
except Exception: font = None
y = 0
for r in rows:
    x = 0
    for im, lab in r:
        sheet.paste(im, (x, y + 24)); d.text((x + 6, y + 3), lab, fill=(150, 220, 255), font=font); x += im.width
    y += h + 24
sheet.save(out); print("sheet", out, sheet.size)
