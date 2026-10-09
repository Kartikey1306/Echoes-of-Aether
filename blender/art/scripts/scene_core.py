"""The Aether Core, heart of Aether-9: the circular chamber with the Core suspended above the heart pedestal,
broken orbit rings and six energy tethers. The Aether Guardian rises between the pedestal and Kael and Lyra.

  Blender -b --factory-startup --python scene_core.py -- [--quick]

Layout from src/world/zones/CoreZone.ts: arena disc r 27 (Core_ArenaFloor), machinery wall at r 33 (gap at the
south lift), heart pedestal at the centre, Core r 6 at y 15 with inner r 3.6, four rings R 8..12.8, six tethers
from anchors at r 20, cover blocks at r 14-22, floating debris.
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from mathutils import Euler, Vector  # noqa: E402

import artkit as A  # noqa: E402
import cyberkit as C  # noqa: E402

CORE = Vector((0, 0, 15))


def arena():
    A.place("Core_ArenaFloor", (0, 0, 0), 0)
    A.place("Core_Pedestal", (0, 0, 0), 0)
    rr = random.Random(404)
    for i in range(36):
        a = (i / 36) * math.tau
        if abs(math.sin(a / 2 + math.pi / 2)) < 0.06:  # gap at the lift (south = -Y)
            continue
        r = 33
        pos = (math.sin(a) * r, math.cos(a) * r, 0)
        h = ("12m", "16m", "20m")[i % 3]
        A.place(f"Core_Machinery_{h}", pos, A.yaw_to(pos, (0, 0)))
    for i in range(8):
        a = (i / 8) * math.tau + 0.2
        d = 14 + rr.random() * 8
        if 1.7 < a < 3.4:  # keep the camera's sightline (south-east) clear
            continue
        pos = (math.sin(a) * d, math.cos(a) * d, 0)
        A.place("Core_CoverBlock_Large" if i % 2 else "Core_CoverBlock", pos, math.degrees(a) + 90 + rr.uniform(-8, 8))
    A.place("Debris_Pile_Dark", (-12, 10, 0), 30)
    A.place("Debris_Pile_Dark", (14, -6, 0), 160)
    A.place("Debris_Pile_Dark", (-7.5, -13.5, 0), 80)
    # lift landing (south)
    A.box((8, 8, 0.5), (0, -31, -0.25), "metal_dark", name="Lift")
    A.set_emit("emit_strip_cyan", 2.2)
    A.set_emit("emit_strip_violet", 2.2)


def core():
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=5, radius=6.0, location=CORE)
    shell = bpy.context.active_object
    shell.data.materials.append(A.aether_material("core_shell", strength=0.55, rim=2.6, scale=1.2))
    bpy.ops.object.shade_smooth()
    shell.visible_shadow = False
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=4, radius=3.6, location=CORE)
    inner = bpy.context.active_object
    inner.data.materials.append(A.aether_material("core_inner", strength=1.9, core=True, rim=0.8, scale=2.0))
    bpy.ops.object.shade_smooth()
    inner.visible_shadow = False
    A.light("POINT", CORE, 1.4e4, (0.55, 0.85, 1.0), size=3.6, name="CoreLight")
    for i, ring in enumerate(("Core_Ring_A", "Core_Ring_B", "Core_Ring_C", "Core_Ring_D")):
        A.place(ring, tuple(CORE), (math.degrees(i * 0.7 + 0.35), math.degrees(0.25 * i), math.degrees(i * 1.3)))
    # six energy tethers from the floor anchors to the Core
    tms = [A.aether_material("tether_c", color=C.NCYAN, color2=A.CYAN, strength=0.7, rim=1.4, scale=6.0),
           A.aether_material("tether_m", color=C.MAGENTA, color2=A.VIOLET, strength=0.7, rim=1.4, scale=6.0)]
    for i in range(6):
        a = (i / 6) * math.tau + 0.92
        base = Vector((math.sin(a) * 20, math.cos(a) * 20, 0))
        A.place("Core_TetherAnchor", tuple(base), math.degrees(a))
        b0 = base + Vector((0, 0, 1.7))
        top = CORE + Vector((math.sin(a) * 4, math.cos(a) * 4, -2))
        d = top - b0
        bpy.ops.mesh.primitive_cone_add(vertices=16, radius1=0.2, radius2=0.07, depth=d.length, location=(b0 + top) / 2, end_fill_type="NOTHING")
        t = bpy.context.active_object
        t.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
        t.data.materials.append(tms[i % 2])
        bpy.ops.object.shade_smooth()
        t.visible_shadow = False
        A.light("POINT", b0 + Vector((0, 0, 0.4)), 180, A.CYAN, size=0.4, name="AnchorGlow")


def cyber():
    # magenta neon ring on the arena rim, glyph columns on the machinery, holographic data rings around the Core
    ring = [Vector((math.sin(t) * 27.2, math.cos(t) * 27.2, 0.12)) for t in [i / 128 * math.tau for i in range(129)]]
    C.tubes([ring], C.MAGENTA, 6.0, 0.06, name="RimNeon")
    ring2 = [Vector((math.sin(t) * 5.0, math.cos(t) * 5.0, 0.03)) for t in [i / 64 * math.tau for i in range(65)]]
    C.tubes([ring2], C.NCYAN, 8.0, 0.04, name="PedestalNeon")
    for i in range(12):
        a = (i / 12) * math.tau + 0.13
        if abs(math.sin(a / 2 + math.pi / 2)) < 0.25:
            continue
        p = Vector((math.sin(a) * 31.6, math.cos(a) * 31.6, 6.0))
        C.glyph_sign(p, A.yaw_to(p, (0, 0)), n=5, height=0.9, color=C.MAGENTA if i % 2 else C.NCYAN, strength=10, seed=600 + i,
                     vertical=True, backing=False, frame=False)
    for k, (r, rx, rz, col) in enumerate([(15.5, 72, 20, C.MAGENTA), (17.0, 105, -40, C.NCYAN)]):
        segs = []
        for j in range(40):
            if j % 4 == 3:
                continue
            a0 = j / 40 * math.tau
            segs.append([Vector((math.cos(a0 + t * 0.03) * r, math.sin(a0 + t * 0.03) * r, 0)) for t in range(5)])
        ob = C.tubes(segs, col, 5.0, 0.05, name="DataRing")
        ob.location = CORE
        ob.rotation_euler = (math.radians(rx), 0, math.radians(rz))


def debris():
    rr = random.Random(405)
    mats = [A.env_material("metal_dark"), A.env_material("metal_rusted"), A.env_material("concrete_dark")]
    for i in range(30):
        r = rr.uniform(10, 27)
        a = rr.uniform(0, math.tau)
        z = rr.uniform(5, 26)
        s = (rr.uniform(0.6, 2.4), rr.uniform(0.4, 1.4), rr.uniform(0.6, 2.0))
        A.box(s, (math.sin(a) * r, math.cos(a) * r, z), mats[i % 3], rot=(rr.uniform(0, 360), rr.uniform(0, 360), rr.uniform(0, 360)), name="Float", bevel=0.04)
    for i in range(10):
        a = rr.uniform(0, math.tau)
        r = rr.uniform(12, 24)
        A.place(rr.choice(["Rubble_Chunk_L", "Rubble_Chunk_S"]), (math.sin(a) * r, math.cos(a) * r, rr.uniform(3, 18)),
                (rr.uniform(0, 360), rr.uniform(0, 360), rr.uniform(0, 360)), scale=rr.uniform(0.8, 1.6))


def actors():
    gp = (3.6, -7.6, 0)
    kp, lp = (8.6, -14.2, 0), (11.4, -12.0, 0)
    g = A.load_robot("guardian", gp, A.yaw_to(gp, kp, -8), pose={
        "hips": (0, 6, 0), "spine": (10, 0, 0), "chest": (8, -6, 0), "neck": (-6, 0, 0), "head": (-12, 8, 0),
        "clavicle_L": (0, 0, 8), "upperarm_L": (-60, 0, 26), "forearm_L": (-60, 0, 0), "hand_L": (-10, 0, 0),
        "clavicle_R": (0, 0, -8), "upperarm_R": (-35, 0, -30), "forearm_R": (-70, 0, 0), "hand_R": (-6, 0, 0),
        "thigh_L": (-28, 0, 8), "shin_L": (34, 0, 0), "foot_L": (-6, 0, 0), "thigh_R": (12, 0, -8), "shin_R": (26, 0, 0), "foot_R": (-12, 0, 0)})
    for n, sx in (("plate_L", 1), ("plate_R", -1)):
        if n in g.objs:
            g.objs[n].location = g.objs[n].location + Vector((sx * 0.3, 0, 0))
    g.glow(6.0)
    A.light("POINT", Vector(gp) + Vector((1.2, -1.5, 4.2)), 260, A.CYAN, size=0.5, name="GuardianCoreGlow")
    k = A.load_character("kael", kp, A.yaw_to(kp, gp, 22), pose=("combat_idle", 40))
    l = A.load_character("lyra", lp, A.yaw_to(lp, gp, 10), pose=("combat_idle", 14))
    A.curl_fingers(k, "Left", 70)
    A.curl_fingers(k, "Right", 70)
    A.curl_fingers(l, "Left", 40)
    A.curl_fingers(l, "Right", 40)
    return k, l, g


def build(quick=False):
    A.reset()
    A.WET = 0.0
    A.EMIT_SCALE = 1.0
    res = (960, 540) if quick else (1920, 1080)
    A.setup_render(res, samples=48 if quick else 128, look="AgX - Medium High Contrast", exposure=0.0, adaptive=0.035)
    bpy.context.scene.cycles.volume_step_rate = 3.0
    A.world_gradient((0.002, 0.004, 0.01), (0.006, 0.01, 0.02), (0.002, 0.002, 0.004), strength=1.0)
    arena()
    core()
    cyber()
    debris()
    k, l, g = actors()
    cl = (16.5, -22.5, 1.4)
    ct = (0.0, -2.0, 8.7)
    cam = A.camera(cl, ct, lens=22, fstop=8.0, focus=(Vector(cl) - k.rig.location).length)
    mid = (k.rig.location + l.rig.location) / 2 + Vector((0, 0, 1.3))
    A.light("AREA", mid + Vector((-3.0, 4.5, 1.5)), 260, C.MAGENTA, size=2.0, target=tuple(mid), name="RimMagenta")
    A.light("AREA", (12.0, -20.5, 3.5), 220, (0.8, 0.88, 1.0), size=3.0, target=tuple(k.rig.location + Vector((0, 0, 1.4))), name="HeroFill")
    A.light("AREA", (0, 0, 30), 600, (0.55, 0.45, 1.0), size=30, rot=(0, 0, 0), name="VioletTop")
    A.fog_box((0, 0, 14), (70, 70, 30), density=0.0035, color=(0.8, 0.88, 1.0), anisotropy=0.6, noise=0.5, noise_scale=0.06, name="Haze")
    A.compositor(bloom=0.55, bloom_size=0.8, threshold=0.9, dispersion=0.006, vignette=0.32, saturation=1.18)
    A.screen({"kael": k.rig.location + Vector((0, 0, 1)), "lyra": l.rig.location + Vector((0, 0, 1)), "guardian": (3.6, -7.6, 3),
              "core": tuple(CORE), "core_top": tuple(CORE + Vector((0, 0, 6))), "pedestal": (0, 0, 1)})
    return cam


def main():
    a = A.args()
    quick = "--quick" in a
    build(quick)
    if quick:
        A.render(os.path.join(A.PREVIEWS, "tests", "core_quick.png"))
    else:
        A.render(os.path.join(A.PREVIEWS, "loading_core.png"), os.path.join(A.RES_ART, "Loading", "core.jpg"))
        A.save_scene("core_loading")


if __name__ == "__main__":
    main()
