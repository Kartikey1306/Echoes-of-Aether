import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
from mathutils import Vector
import artkit as A
A.reset()
A.setup_render((1280, 720), samples=64)
A.world_gradient((0.05, 0.06, 0.08), (0.12, 0.13, 0.15), (0.03, 0.03, 0.035), strength=1.0)
A.plane(40, 40, (0, 0, 0), A.principled("floor", (0.12, 0.12, 0.13), rough=0.6))
k = A.load_character("kael", (-0.5, 0, 0), -15, pose=("combat_idle", 12))
A.dress_default(k, eyewear="aviator")
l = A.load_character("lyra", (0.5, 0, 0), 15, pose=("combat_idle", 12))
A.dress_default(l, eyewear="cyber_visor")
A.light("AREA", (2.5, -3, 3), 400, (1, 0.95, 0.9), size=2, target=(0, 0, 1.4))
A.light("AREA", (-3, 2, 2.5), 300, (0.6, 0.8, 1.0), size=2, target=(0, 0, 1.5))
A.camera((0, -2.2, 1.65), (0, 0, 1.55), lens=50)
A.render(os.path.join(A.PREVIEWS, "tests", "test_look.png"))
