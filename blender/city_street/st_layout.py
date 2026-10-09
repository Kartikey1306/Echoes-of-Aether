"""Atlas layouts shared by the texture generators (numpy) and the asset builders (Blender UVs). Pure python.

Rects are pixel boxes (x, y, w, h) with y measured from the BOTTOM of the atlas (Blender UV convention: v = 0 at the
bottom row); uv(name) returns (u0, v0, u1, v1).
"""

SIGNS_W = SIGNS_H = 2048
SHOPS = ["noodle", "pharmacy", "clinic", "pawn", "capsule", "arcade"]


def _signs():
    r = {}
    # fascia lightboxes 1024 x 128 (8:1), two colourways per shop type: rows from the top
    for i, s in enumerate(SHOPS):
        for k in range(2):
            r[f"fascia_{s}_{k}"] = (k * 1024, SIGNS_H - 128 * (i + 1), 1024, 128)
    # dark fascia for closed shops (unlit faded lightbox)
    r["fascia_dead_0"] = (0, SIGNS_H - 128 * 7, 1024, 128)
    r["fascia_dead_1"] = (1024, SIGNS_H - 128 * 7, 1024, 128)
    # vertical blade signs 128 x 384 (1:3): 16 across
    y = SIGNS_H - 128 * 7 - 384
    for i in range(16):
        r[f"blade_{i}"] = (i * 128, y, 128, 384)
    # square signs / menu boards / icons 256 x 256: 8 across, 2 rows
    y2 = y - 256
    for i in range(8):
        r[f"square_{i}"] = (i * 256, y2, 256, 256)
    y3 = y2 - 256
    for i in range(8):
        r[f"square_{8 + i}"] = (i * 256, y3, 256, 256)
    # noren curtains / cloth banners 512 x 256 (2:1): 4 across
    y4 = y3 - 256
    assert y4 == 0, y4
    for i in range(4):
        r[f"cloth_{i}"] = (i * 512, y4, 512, 256)
    return r


SIGN_RECTS = _signs()

INTERIORS_W, INTERIORS_H = 2048, 2048
# 8 interior renders of 1024 x 512 (2:1, window-shaped)
INTERIORS = ["noodle", "pharmacy", "clinic", "pawn", "capsule", "arcade", "kitchen_dark", "storeroom"]
INTERIOR_RECTS = {n: ((i % 2) * 1024, INTERIORS_H - 512 * (i // 2 + 1), 1024, 512) for i, n in enumerate(INTERIORS)}


def uv(name, inset_px=2):
    if name in SIGN_RECTS:
        x, y, w, h = SIGN_RECTS[name]
        W, H = SIGNS_W, SIGNS_H
    else:
        x, y, w, h = INTERIOR_RECTS[name]
        W, H = INTERIORS_W, INTERIORS_H
    return ((x + inset_px) / W, (y + inset_px) / H, (x + w - inset_px) / W, (y + h - inset_px) / H)


def sub(rect, fu0, fv0, fu1, fv1):
    """Sub-rectangle of a uv rect by fractions (crop for windows of another aspect)."""
    u0, v0, u1, v1 = rect
    return (u0 + (u1 - u0) * fu0, v0 + (v1 - v0) * fv0, u0 + (u1 - u0) * fu1, v0 + (v1 - v0) * fv1)
