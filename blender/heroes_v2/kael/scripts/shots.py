"""Detail renders of the current blend with its materials (no rebuild).

  blender -b <blend> --python shots.py -- <tag> [--shots boots,chest,...] [--light menu|night]
"""
import bpy, sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kcommon as K
from mathutils import Vector

SH = {
    "front": (0, 3.4, 1.0, 0.95, 50), "q34": (35, 3.4, 1.05, 0.95, 50), "back": (180, 3.4, 1.0, 0.95, 50), "side": (90, 3.4, 1.0, 0.95, 50),
    "chest": (12, 1.1, 1.42, 1.36, 50), "chest34": (38, 1.15, 1.42, 1.36, 50), "back_up": (175, 1.3, 1.45, 1.35, 50),
    "shoulderL": (70, 0.9, 1.52, 1.44, 50), "shoulderR": (-70, 0.9, 1.52, 1.44, 50), "armR": (-35, 0.95, 1.28, 1.22, 50),
    "legs": (25, 1.6, 0.6, 0.55, 50), "legs_side": (85, 1.6, 0.6, 0.55, 50), "boots": (25, 0.85, 0.3, 0.2, 50),
    "hand": (-20, 0.55, 1.16, 1.13, 50), "waist": (15, 1.0, 1.08, 1.05, 50),
}
a = K.args()
tag = a[0]
shots = (K.opt(a, "--shots") or "front,q34,back,chest,shoulderR,legs,boots,hand").split(",")
light = K.opt(a, "--light") or "menu"
for o in bpy.data.objects:
    if o.type == "MESH" and (o.name in ("BodyMH", "BodyFull") or o.name.endswith(("_HI", "_HIB", "_HPG"))):
        o.hide_render = True
    if o.type == "MESH" and (o.name.startswith("Hair_") or o.name.startswith("Facial_")):
        o.hide_render = True
out = []
for s in shots:
    yaw, dist, z, aim, lens = SH[s]
    K.clear_preview()
    K.cycles(samples=64, res=(800, 1000))
    K.world((0.03, 0.033, 0.04), 1.0)
    K.floor((0.06, 0.065, 0.07), 0.6)
    K.rig_lights(light, Vector((0, 0, aim)), 1.6 if dist > 2.5 else 1.0)
    r = math.radians(yaw)
    K.camera(Vector((math.sin(r) * dist, -math.cos(r) * dist, z)), Vector((0, 0, aim)) if s not in ("shoulderL", "shoulderR", "armR", "hand", "boots")
             else Vector(({"shoulderL": 0.22, "shoulderR": -0.22, "armR": -0.42, "hand": -0.5, "boots": 0.0}[s], -0.05 if s != "boots" else -0.05, aim)), lens)
    out.append(K.render_to(os.path.join(K.PREVIEWS, "outfit", f"{tag}_{s}.png")))
K.contact_sheet(out, os.path.join(K.PREVIEWS, "outfit", f"{tag}_sheet.png"), cols=4, width=500)
