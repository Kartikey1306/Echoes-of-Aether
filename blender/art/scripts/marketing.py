"""Key art + store art from the neon plaza scene (scene_plaza.build('keyart')): Kael and Lyra face the camera
in front of the Aether Monument, the megacity and its holo adverts behind them, rain in the foreground. The
rendered logo (Resources/Art/Title/logo.png, from logo.py) is composited in Blender's compositor.

  Blender -b --factory-startup --python marketing.py -- [key|banner|social|itch ...] [--quick]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import artkit as A  # noqa: E402
import scene_plaza  # noqa: E402

LOGO = os.path.join(A.RES_ART, "Title", "logo.png")
# name: (resolution, camera location, target, lens, logo box (cx, cy, width as frame fraction), output file)
SHOTS = {
    "key": ((1920, 1080), (0.1, -17.7, 0.85), (0.0, -6.0, 3.0), 28, (0.5, 0.87, 0.42), "key_art_1920x1080.png"),
    "social": ((1200, 630), (0.1, -17.9, 0.85), (0.0, -6.0, 2.9), 28, (0.5, 0.87, 0.44), "social_1200x630.png"),
    "itch": ((630, 500), (0.1, -18.3, 0.85), (0.0, -6.0, 3.3), 28, (0.5, 0.83, 0.72), "itch_cover_630x500.png"),
    "title_bg": ((1920, 1080), (0.1, -17.7, 0.85), (0.0, -6.0, 3.0), 28, None, "title_background_1920x1080.png"),
    "banner": ((1920, 480), (-2.2, -19.6, 1.05), (-1.1, -6.0, 2.0), 30, (0.24, 0.52, 0.36), "banner_1920x480.png"),
}


def main():
    a = A.args()
    quick = "--quick" in a
    which = [x for x in a if x in SHOTS] or [k for k in SHOTS if k != "title_bg"]
    scene_plaza.build("keyart", quick=quick)
    sc = bpy.context.scene
    cam = sc.camera
    k = [o for o in bpy.data.objects if o.type == "ARMATURE" and o.name.startswith("Kael")][0]
    l = [o for o in bpy.data.objects if o.type == "ARMATURE" and o.name.startswith("Lyra")][0]
    mid = (k.location + l.location) / 2 + Vector((0, 0, 1.45))
    # hero key: soft cool-white box above the lens, warm amber kicker from the camp side
    A.light("AREA", mid + Vector((-1.2, -3.2, 1.6)), 240, (0.85, 0.92, 1.0), size=2.5, target=tuple(mid), name="KeyFront")
    A.light("AREA", mid + Vector((2.8, -1.5, 0.6)), 120, A.hexlin("#ffb02e"), size=1.5, target=tuple(mid), name="KickAmber")
    os.makedirs(A.MARKETING, exist_ok=True)
    for name in which:
        res, cl, ct, lens, box, fname = SHOTS[name]
        if quick:
            res = (res[0] // 2, res[1] // 2)
        sc.render.resolution_x, sc.render.resolution_y = res
        cam.location = cl
        A.look_at(cam, ct)
        cam.data.lens = lens
        cam.data.dof.focus_distance = (Vector(cl) - k.location).length
        has_logo = os.path.exists(LOGO) and box is not None
        A.compositor(bloom=0.45, bloom_size=0.7, threshold=0.9, dispersion=0.005, vignette=0.3, saturation=1.08,
                     logo=LOGO if has_logo else None, logo_box=box)
        out = os.path.join(A.PREVIEWS, "tests", "mk_" + fname) if quick else os.path.join(A.MARKETING, fname)
        A.render(out)
    if not quick:
        A.save_scene("keyart")


if __name__ == "__main__":
    main()
