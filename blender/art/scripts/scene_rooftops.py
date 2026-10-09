"""Rooftop Sector, above the market: night storm. From the entry roof (water tank, vents) Kael and Lyra look
across the plank bridge and the hollow roof toward the relay tower and its red beacon. The dead city lies below;
the Core's glow stains the clouds on the horizon; lightning in the distance.

  Blender -b --factory-startup --python scene_rooftops.py -- [--quick]

Layout from src/world/zones/RooftopsZone.ts: R1 x[-6,10] z[-6,10] top 14 (brick, water tank), R2 x[14,28] z[-4,8]
roof 15.5 (hatch), R3 x[-4,12] z[16,30] top 16 (shed), R4 x[18,30] z[18,32] top 16, R5 x[30,44] z[-10,6] top 19
(relay tower at (38, -2), transmitter), street lights far below, skyline ring at 70-110 m.
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import artkit as A  # noqa: E402
import cyberkit as C  # noqa: E402

FAC = {"brick": "Facade_Brick_Window", "concrete": "Facade_Concrete_Window", "plaster": "Facade_Plaster_Window",
       "concrete_dark": "Facade_Concrete_Window"}


def block(px0, pz0, px1, pz1, top, mat, floors=3, parapet=True, rr=None, lit=0.08):
    """Prototype rectangle (x, z) -> Blender block with roof slab, parapets and facade modules on the top floors."""
    rr = rr or random.Random(int(px0 * 7 + pz0 * 13))
    x0, x1 = px0, px1
    y0, y1 = -pz1, -pz0
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    w, d = x1 - x0, y1 - y0
    body_top = top - floors * 3.4
    A.box((w - 0.6, d - 0.6, body_top), (cx, cy, body_top / 2), mat, name="Body")
    A.box((w, d, 0.3), (cx, cy, top - 0.15), "concrete", name="Roof")
    A.box((w - 0.8, d - 0.8, top - body_top), (cx, cy, body_top + (top - body_top) / 2 - 0.3), mat, name="Core")
    for f in range(floors):
        z = body_top + f * 3.4
        for (ax, ay, n, length) in [((x0, y0), (1, 0), (0, -1), w), ((x0, y1), (1, 0), (0, 1), w), ((x0, y0), (0, 1), (-1, 0), d), ((x1, y0), (0, 1), (1, 0), d)]:
            pass
        for side in ("s", "n", "w", "e"):
            if side in ("s", "n"):
                n = (0, -1) if side == "s" else (0, 1)
                yy = y0 if side == "s" else y1
                count = int(w // 4)
                start = cx - count * 2 + 2
                for i in range(count):
                    lit_now = rr.random() < lit
                    kind = "Facade_Plaster_Window_Lit" if lit_now else FAC[mat]
                    if mat == "brick" and rr.random() < 0.15:
                        kind = "Facade_Brick_Window_Broken"
                    A.place(kind, (start + i * 4, yy + n[1] * 0.0, z), A.yaw_to((0, 0), n))
            else:
                n = (-1, 0) if side == "w" else (1, 0)
                xx = x0 if side == "w" else x1
                count = int(d // 4)
                start = cy - count * 2 + 2
                for i in range(count):
                    lit_now = rr.random() < lit
                    kind = "Facade_Plaster_Window_Lit" if lit_now else FAC[mat]
                    A.place(kind, (xx, start + i * 4, z), A.yaw_to((0, 0), n))
    if parapet:
        pk = "Roof_Parapet_4m_Brick" if mat == "brick" else "Roof_Parapet_4m"
        for i in range(int(w // 4)):
            px = cx - (int(w // 4)) * 2 + 2 + i * 4
            A.place(pk, (px, y0 + 0.17, top), 0)
            A.place(pk, (px, y1 - 0.17, top), 180)
        for i in range(int(d // 4)):
            py = cy - (int(d // 4)) * 2 + 2 + i * 4
            A.place(pk, (x0 + 0.17, py, top), 90)
            A.place(pk, (x1 - 0.17, py, top), -90)
        for x, y in [(x0, y0), (x0, y1), (x1, y0), (x1, y1)]:
            A.place("Roof_Parapet_Corner", (x + (0.16 if x == x0 else -0.16), y + (0.16 if y == y0 else -0.16), top), 0)


def roofs():
    block(-6, -6, 10, 10, 14, "brick")
    block(14, -4, 28, 8, 15.5, "concrete")
    block(-4, 16, 12, 30, 16, "concrete")
    block(18, 18, 30, 32, 16, "plaster")
    block(30, -10, 44, 6, 19, "concrete_dark")
    # R1 dressing
    A.place("WaterTank", (-3.0, 3.0, 14), 30)
    A.place("AC_Unit", (-1.0, -8.2, 14), math.degrees(0.3))
    A.place("Roof_Vent", (-2.0, -7.0, 14), 0)
    A.place("Roof_TurbineVent", (1.2, 1.5, 14), 0)
    A.place("Roof_TurbineVent", (3.0, 4.2, 14), 0)
    A.place("Terminal_Desk", (2.0, 3.6, 14), 180)
    A.place("Crate_Small", (3.6, 4.6, 14), 20)
    # R2: hatch, AC, vent
    A.place("Roof_Hatch_Frame", (20, -6, 15.5), 0)
    A.place("Roof_Hatch_Lid", (20, -6.75, 15.85), (-70, 0, 0))
    A.place("AC_Unit", (25, 2, 15.5), math.degrees(1.2))
    A.place("Roof_Vent", (17, 1, 15.5), 0)
    # R3 shed + antenna, R4 clutter
    A.place("Roof_Shed", (3, -23, 16), 180)
    A.place("Antenna_Mast_5m", (9, -28, 16), 0)
    A.place("AC_Unit", (26, -28, 16), 0)
    A.place("Crate_Stack", (28, -30, 16), math.degrees(0.6))
    # R5 relay tower + transmitter + generator
    A.place("RelayTower", (38, 2, 19), 0)
    A.place("Relay_Transmitter", (38, -2.2, 19), 0)
    A.place("Generator_Industrial", (33.5, -2.5, 19), 90)
    beacon = Vector((38, 2, 19)) + A.anchor("RelayTower", "beacon")
    A.light("POINT", beacon + Vector((0, 0, 0.25)), 220, (1.0, 0.12, 0.08), size=0.15, name="Beacon")
    A.light("POINT", (38, -3.6, 20.4), 60, (0.55, 0.85, 1.0), size=0.6, name="TransmitterGlow")
    # connections: plank ramp R1->R2, beam R2->R4, ladder R2->R5
    plank = A.box((4.4, 1.5, 0.12), (12.1, -2.0, 14.78), "wood", rot=(0, -19, 0), name="Plank")
    A.box((0.45, 10.4, 0.25), (24, -13.0, 15.7), "metal_painted_yellow", rot=(-2.8, 0, 0), name="Beam")
    A.place("Ladder_4m", (29.6, 0, 15.5), -90)


def city():
    A.plane(600, 600, (20, 0, 0), "asphalt", name="Street")
    rr = random.Random(77)
    # the district around the market roofs, from the city kit: mid-rise blocks and corporate towers 45-110 m out,
    # then the skyline megatowers 160-480 m out (Skyline_Tower_A/B/C, Skyline_Twin_D)
    kit = ["LB_KS_Tenement_B", "LB_NM_Shophouse_B", "LB_KS_Slab_C", "LB_AG_Office_A", "LB_NM_Arcade_C", "LB_KS_Tenement_A",
           "LB_AG_Office_B", "LB_NM_Shophouse_A", "LB_CW_House_B"]
    for i in range(22):
        a = math.radians(-15 + i * 9 + rr.uniform(-3, 3))
        d = rr.uniform(55, 115)
        x, y = 15 + math.sin(a) * d, -10 + math.cos(a) * d
        A.place(kit[i % len(kit)], (x, y, 0), A.yaw_to((x, y), (15, -10)))
    for name, x, y in [("LM_NM_JadeLanternTower", 150, 60), ("LM_KS_TheStack", 120, -60), ("LM_AG_HelixArcology", 260, 120),
                       ("LM_KS_SignalSpire", 95, 140), ("LM_AG_MeridianSpire", 230, -110), ("LM_KS_BridgeTwins", 60, 190)]:
        A.place(name, (x, y, 0), A.yaw_to((x, y), (15, -10)))
    sky = [("Skyline_Twin_D", 380, 160, -70, 1.2), ("Skyline_Tower_A", 260, -40, -95, 1.3), ("Skyline_Tower_A", 300, 260, -50, 1.4),
           ("Skyline_Tower_B", 200, 120, -60, 1.2), ("Skyline_Tower_C", 180, -110, -100, 1.3), ("Skyline_Tower_B", 420, 40, -90, 1.5),
           ("Skyline_Tower_C", 150, 230, -30, 1.2), ("Skyline_Tower_A", 90, 330, -10, 1.3), ("Skyline_Tower_B", 30, 260, 0, 1.2),
           ("Skyline_Tower_A", 480, -160, -110, 1.6), ("Skyline_Tower_C", 330, -220, -120, 1.4), ("Skyline_Twin_D", 200, 420, -25, 1.3)]
    for name, x, y, rz, sc in sky:
        A.place(name, (x, y, 0), rz, scale=sc)
    for i in range(14):
        a = rr.uniform(0, math.tau)
        d = 45 + rr.random() * 40
        A.place(rr.choice(["Building_Block_A", "Building_Block_D"]), (15 + math.cos(a) * d, -10 + math.sin(a) * d, 0), rr.uniform(0, 360),
                scale=(1, 1, rr.uniform(0.55, 0.8)))
    for i in range(18):
        x = -40 + (i % 6) * 22
        y = 40 - (i // 6) * 40
        A.place("StreetLight", (x, y, 0), rr.choice([0, 90, 180, 270]))
        A.light("POINT", (x, y, 6.0), 900, (1.0, 0.52, 0.18), size=0.3, name="Street")
    for i in range(10):
        A.place(rr.choice(["Car_Sedan_Wrecked", "Car_Sedan", "Bus_Transit"]), (rr.uniform(-40, 70), rr.uniform(-60, 50), 0), rr.uniform(0, 360))


def cyber():
    """Neon on the roofs: city-kit rooftop billboard, antenna clusters, roof dishes, water tower, wall LED walls and
    glyph signs on the nearby blocks, lantern string, sagging cable bundles; relay-tower edge neon, hover traffic."""
    t = Vector((38, 2, 19))
    for dx, dy in ((-2.0, -2.0), (2.0, -2.0)):
        C.strip(t + Vector((dx, dy, 0.5)), t + Vector((dx * 0.55, dy * 0.55, 12.5)), C.MAGENTA, 9.0, 0.04)
    A.place("Billboard_Rooftop_Rig_12x6", (24, -26, 16), 200)
    A.place("Antenna_Cluster_Roof", (26.5, 5.0, 15.5), 0)
    A.place("Satellite_Dish_Roof", (16.5, 6.0, 15.5), 150)
    A.place("Roof_Clutter_Pack_A", (8.0, -27.5, 16), 0)
    A.place("Water_Tower_Roof", (42.0, -7.5, 19), 20)
    A.place("Billboard_LED_Wall_6x3_B", (21.0, -4.1, 9.0), 180)
    A.place("Neon_Glyph_Column", (27.0, -4.1, 6.0), 180)
    A.place("Sign_Blade_B", (14.0, -4.1, 10.0), 180)
    A.place("Neon_Glyph_A", (44.1, -2.0, 14.0), -90)
    A.place("Billboard_LED_Wall_6x3_C", (37.0, -10.15, 13.0), 180)
    A.place("Lantern_String_4m", (-6, 6.2, 16.0), 0)
    A.place("Lantern_String_4m", (-2, 6.2, 16.0), 0)
    A.place("Cable_Bundle_Sag_8m", (10, 4.5, 17.0), 0)
    A.place("Cable_Bundle_Sag_8m", (22, -8.0, 21.5), 30)
    C.holo_panel((62.0, -40.0, 34.0), -20, (18, 10), C.YELLOW, C.MAGENTA, 2.0, symbol="triangle", seed=506)
    for name, p, yaw in [("HoverCar_A", (36, 24, 31), -120), ("HoverCar_B", (62, -6, 44), 160), ("HoverTruck", (96, 40, 58), -100),
                         ("HoverCar_A", (130, -20, 72), 70)]:
        A.place_vehicle(name, p, yaw)
    C.air_traffic((160, 40), (400, 340), count=70, seed=7, z=(60, 180))
    C.strip((-6, -10.05, 14.95), (10, -10.05, 14.95), C.NCYAN, 5.0, 0.03)


def sky():
    A.world_pano(strength=0.5, rot_deg=150)
    # storm clouds: thick volumetric layer lit by the city and a lightning flash inside it
    A.fog_box((330, 60, 175), (660, 760, 90), density=0.0, color=(0.75, 0.78, 0.85), anisotropy=0.2, noise=0.95,
              noise_scale=0.006, name="Clouds")
    # the Core's glow on the horizon (prototype: glow sprites at (-60, 30, -140)), placed behind the tower
    core = Vector((330, -70, 30))
    A.light("POINT", core, 1.0e5, (0.3, 0.62, 1.0), size=40, name="CoreHorizon")
    A.light("POINT", core + Vector((-30, 40, 30)), 0.5e5, (0.55, 0.35, 1.0), size=40, name="CoreHorizonViolet")
    # distant lightning bolt + flash in the clouds
    bolt((330, 300, 175), (300, 330, 0), seed=4, segs=40)
    A.light("AREA", (330, 300, 185), 3.2e5, (0.75, 0.82, 1.0), size=90, rot=(0, 0, 0), name="Flash")


def bolt(top, bottom, seed=1, segs=90, name="Lightning"):
    """Procedural lightning: a midpoint-displaced main channel that thins toward the ground, plus a few short
    forks. Thin emissive tubes; the bloom in the compositor gives the glow."""
    rr = random.Random(seed)
    top, bottom = Vector(top), Vector(bottom)

    def channel(a, b, n, amp):
        pts = [a, b]
        for level in range(7):
            new = [pts[0]]
            for i in range(len(pts) - 1):
                m = (pts[i] + pts[i + 1]) / 2
                d = (pts[i + 1] - pts[i]).length
                m += Vector((rr.uniform(-1, 1), rr.uniform(-1, 1), rr.uniform(-0.3, 0.3))) * d * amp
                new += [m, pts[i + 1]]
            pts = new
        return pts

    main = channel(top, bottom, segs, 0.22)
    chains = [(main, 1.0)]
    for b in range(6):
        i0 = rr.randint(len(main) // 8, int(len(main) * 0.7))
        a = main[i0]
        ln = rr.uniform(25, 70)
        end = a + Vector((rr.uniform(-1, 1), rr.uniform(-0.5, 0.5), -rr.uniform(0.6, 1.0))).normalized() * ln
        chains.append((channel(a, end, 30, 0.25), 0.4))
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = 0.28
    cu.bevel_resolution = 1
    for chain, w in chains:
        sp = cu.splines.new("POLY")
        sp.points.add(len(chain) - 1)
        for k, p in enumerate(chain):
            sp.points[k].co = (p.x, p.y, p.z, 1)
            sp.points[k].radius = w * (1.0 - 0.6 * k / len(chain))
    ob = bpy.data.objects.new(name, cu)
    cu.materials.append(A.emissive("lightning", (0.75, 0.85, 1.0), 45.0))
    ob.visible_shadow = False
    A.link(ob)
    return ob


def actors():
    kp, lp = (5.6, -4.0, 14), (4.6, -6.3, 14)
    tower = (38, 2)
    k = A.load_character("kael", kp, A.yaw_to(kp, tower, 6), pose=("npc_look", 60))
    l = A.load_character("lyra", lp, A.yaw_to(lp, (12, -2), 0), pose=("walk", 9))
    return k, l


def build(quick=False):
    A.reset()
    A.WET = 1.0
    A.EMIT_SCALE = 1.0
    res = (960, 540) if quick else (1920, 1080)
    A.setup_render(res, samples=48 if quick else 128, look="AgX - Medium High Contrast", exposure=0.3, adaptive=0.035)
    bpy.context.scene.cycles.volume_step_rate = 4.0
    bpy.context.scene.cycles.volume_max_steps = 256
    sky()
    roofs()
    city()
    cyber()
    k, l = actors()
    A.light("SUN", (0, 0, 60), 0.15, (0.6, 0.7, 0.95), size=4, rot=(60, 0, 250), name="Moon")
    # warm practical on R1 (terminal / work lamp) to model the heroes, cold rim from the storm
    A.light("AREA", (3.5, -8.5, 16.6), 110, (1.0, 0.8, 0.6), size=2.5, target=tuple(k.rig.location + Vector((0, 0, 1.4))), name="WorkLamp")
    A.light("AREA", (12.0, 9.0, 18.5), 420, C.NCYAN, size=6, target=tuple(k.rig.location + Vector((0, 0, 1.4))), name="StormRim")
    A.light("AREA", (12.0, -14.0, 17.5), 360, C.MAGENTA, size=4, target=tuple(l.rig.location + Vector((0, 0, 1.3))), name="RimMagenta")
    cl = (-3.2, -9.0, 16.2)
    ct = (36.0, 6.5, 21.0)
    cam = A.camera(cl, ct, lens=26, fstop=8.0, focus=(Vector(cl) - k.rig.location).length, clip_end=5000)
    A.fog_box((40, 0, 30), (240, 240, 60), density=0.004, color=(0.75, 0.8, 0.9), anisotropy=0.4, falloff_z=(5, 60), name="Mist")
    A.rain((cl[0] + 20, cl[1] + 10, 18), (44, 40, 16), count=12000 if not quick else 8000, length=(0.4, 0.8), width=0.005,
           wind=(0.35, 0.12), cam=cam, brightness=0.3)
    A.compositor(bloom=0.45, bloom_size=0.75, threshold=0.9, dispersion=0.005, vignette=0.3, saturation=1.18)
    A.screen({"kael": k.rig.location + Vector((0, 0, 1)), "lyra": l.rig.location + Vector((0, 0, 1)), "tower_top": (38, 2, 35),
              "tower_base": (38, 2, 19), "tank": (-3, 3, 17), "core": (330, -70, 30), "bolt": (500, 310, 100)})
    return cam


def main():
    a = A.args()
    quick = "--quick" in a
    build(quick)
    if quick:
        A.render(os.path.join(A.PREVIEWS, "tests", "rooftops_quick.png"))
    else:
        A.render(os.path.join(A.PREVIEWS, "loading_rooftops.png"), os.path.join(A.RES_ART, "Loading", "rooftops.jpg"))
        A.save_scene("rooftops_loading")


if __name__ == "__main__":
    main()
