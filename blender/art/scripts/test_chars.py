"""Quick validation render: characters (materials, default hair, pose) + robots."""
import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
import artkit as A

a = A.args()
which = a[0] if a else "kael,lyra"
clip = a[1] if len(a) > 1 else "combat_idle"
frame = int(a[2]) if len(a) > 2 else 1
A.reset()
A.setup_render((1280, 720), samples=64)
A.world_gradient((0.05, 0.06, 0.08), (0.12, 0.13, 0.15), (0.03, 0.03, 0.035), strength=1.0)
A.plane(40, 40, (0, 0, 0), A.principled("floor", (0.12, 0.12, 0.13), rough=0.6))
x = -1.2 * (len(which.split(",")) - 1) / 2
for cid in which.split(","):
    if cid in A.CHARS:
        ch = A.load_character(cid, (x, 0, 0), yaw=-20, pose=(clip, frame))
    else:
        A.load_robot(cid, (x, 0, 0), yaw=-20, pose="combat")
    x += 1.2
A.light("AREA", (2.5, -3, 3), 400, (1, 0.95, 0.9), size=2, target=(0, 0, 1.2))
A.light("AREA", (-3, 2, 2.5), 300, (0.6, 0.8, 1.0), size=2, target=(0, 0, 1.4))
A.light("AREA", (-2, -4, 1.5), 80, (1, 1, 1), size=3, target=(0, 0, 1.0))
n = len(which.split(","))
A.camera((0, -4.2 - n * 0.6, 1.3), (0, 0, 0.95), lens=40)
A.compositor(bloom=0.2, vignette=0.15)
A.render(os.path.join(A.PREVIEWS, "tests", f"test_{which.replace(',', '_')}_{clip}.png"))
