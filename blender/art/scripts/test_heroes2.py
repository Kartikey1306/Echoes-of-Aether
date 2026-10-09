import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
from mathutils import Vector
import artkit as A
a = A.args()
clip = a[0] if a else "idle"; fr = int(a[1]) if len(a) > 1 else 30
A.reset()
A.setup_render((1280, 720), samples=64)
A.world_gradient((0.05, 0.06, 0.08), (0.12, 0.13, 0.15), (0.03, 0.03, 0.035), strength=1.0)
A.plane(40, 40, (0, 0, 0), A.principled("floor", (0.12, 0.12, 0.13), rough=0.6))
k = A.load_hero("kael", (-0.55, 0, 0), -12, pose=(clip, fr))
l = A.load_hero("lyra", (0.55, 0, 0), 12, pose=(clip, fr))
print("RIG", k.rig.name, tuple(k.rig.scale), tuple(k.rig.rotation_euler), "L", l.rig.name, tuple(l.rig.scale))
A.light("AREA", (2.5, -3, 3), 500, (1, 0.95, 0.9), size=2, target=(0, 0, 1.3))
A.light("AREA", (-3, 2, 2.5), 300, (0.6, 0.8, 1.0), size=2, target=(0, 0, 1.5))
A.light("AREA", (0, -4, 1.5), 120, (1, 1, 1), size=3, target=(0, 0, 1.0))
A.camera((0, -4.6, 1.2), (0, 0, 0.95), lens=40)
A.render(os.path.join(A.PREVIEWS, "tests", f"heroes2_{clip}.png"))
A.camera((0.0, -1.5, 1.62), (0.0, 0, 1.58), lens=60)
A.render(os.path.join(A.PREVIEWS, "tests", f"heroes2_{clip}_face.png"))
