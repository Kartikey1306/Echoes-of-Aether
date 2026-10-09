"""Abandoned Metro, Line B, Platform 2: dead station lit by red emergency lamps and a few surviving tubes, the
stalled train in the flooded track pit. Kael and Lyra advance along the platform; a Sentinel waits in the dark.

  Blender -b --factory-startup --python scene_metro.py -- [--quick]

Layout from src/world/zones/MetroZone.ts: platform hall x[-44,44], platform top y=0 with the edge at proto
z=52.1, track pit (floor -1.3) to z=58, columns every 8 m at z=45.5, emergency lights at x=-30,-6,18,38,
derailed train cars at x=-22 and x=-4, flooded track east of x=8.
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import artkit as A  # noqa: E402
import cyberkit as C  # noqa: E402

P = A.proto
EDGE_Y = -52.1     # platform edge (Blender y)
PIT = -1.3
RAIL = -0.85       # rail top


def hall():
    # platform slab + edge modules (pit toward -Y), back (north) wall with openings, track wall, ceiling
    A.plane(92, EDGE_Y + 41.75 + 0.1, (0, (EDGE_Y + -41.75) / 2 + 0.05, 0.0), "concrete", name="PlatformFloor")
    for x in range(-44, 45, 4):
        A.place("Platform_Edge_4m", (x + 2, EDGE_Y, 0), 0)
    A.plane(92, 7, (0, -55.5, PIT), "concrete_dark", name="PitFloor")
    for x in range(-44, 45, 8):
        A.place("Metro_Track_8m", (x + 4, -55.0, RAIL), 90)
    # flooded section east of x = 8 (prototype water plane at -0.95)
    A.plane(38, 5.6, (27, -55.1, -0.98), "water", name="Flood")
    # walls (tile) and ceiling (dark concrete)
    A.box((92, 0.5, 7.2), (0, -58.5, PIT + 3.6), "metro_tile", name="TrackWall")
    for x in range(-44, 45, 4):
        kind = "Wall_Metro_Door_4m" if x in (-36, -24) else ("Wall_Metro_Window_4m" if x in (28,) else "Wall_Metro_Straight_4m")
        A.place(kind, (x + 2, -41.6, 0), 180)
    A.box((92, 0.4, 2.0), (0, -41.6, 5.0), "metro_tile", name="WallTop")
    A.box((92, 18, 0.5), (0, -50, 5.25), "concrete_dark", name="Ceiling")
    for x in range(-40, 41, 8):
        A.place("Pillar_Metro_4m", (x, -45.5, 0), 0)
    # recessed light boxes along the ceiling over the track (dead)
    for x in range(-40, 41, 8):
        A.place("Lab_CeilingLight_Warm", (x + 4, -55.2, 5.0), 90)
    A.set_emit("emit_panel_warm", 0.0)


def lights(quick):
    # emergency lamps (prototype 0xff4030): one still red, the rest swapped for magenta neon fixtures
    red = (1.0, 0.16, 0.08)
    for x, col in ((-30, C.MAGENTA), (-6, red), (18, C.MAGENTA), (38, C.MAGENTA)):
        C.strip((x - 1.2, -46.2, 4.35), (x + 1.2, -46.2, 4.35), col, 10.0, 0.05)
        A.light("POINT", (x, -46.6, 4.0), 160, col, size=0.25, name="Emergency")
    # surviving fluorescent tubes (warm, one flickering low) hung between columns
    for x, on in [(-12, 1.0), (0, 0.0), (12, 0.35), (-24, 0.0), (24, 0.0)]:
        A.place("Metro_LampTube", (x, -48.5, 4.9), 0)
        if on > 0:
            tube = Vector((x, -48.5, 4.45))
            A.light("AREA", tube, 160 * on, (1.0, 0.86, 0.66), size=1.4, size_y=0.18, shape="RECTANGLE", rot=(0, 0, 0), name="Tube")
    A.set_emit("emit_panel_warm", 0.0)
    tube_on = A.emissive("tube_on", (1.0, 0.86, 0.66), 14.0)
    for ob in bpy.data.objects:
        if ob.name.startswith("Metro_LampTube") and abs(ob.location.x + 12) < 0.1:
            for i, slot in enumerate(ob.material_slots):
                if slot.material and slot.material.name.startswith("emit_panel_warm"):
                    slot.link = "OBJECT"
                    slot.material = tube_on
        if ob.name.startswith("Metro_LampTube") and abs(ob.location.x - 12) < 0.1:
            for i, slot in enumerate(ob.material_slots):
                if slot.material and slot.material.name.startswith("emit_panel_warm"):
                    slot.link = "OBJECT"
                    slot.material = A.emissive("tube_dim", (1.0, 0.86, 0.66), 4.0)
    # cold spill from the stairs (concourse) through the far north opening
    A.light("AREA", (-0.5, -41.0, 3.0), 120, (0.55, 0.75, 1.0), size=3.0, rot=(-90, 0, 0), name="StairSpill")


def train():
    # stalled, partly powered train: lead car lit dimly inside (warm windows, cyan side strip), rear car dark
    t1 = A.place("TrainCar_Metro_Lit", (2.0, -55.2, RAIL), (0, -0.6, -90 + 2.5))
    A.place("TrainCar_Metro", (19.6, -55.0, RAIL), (0, 0.4, -90 + 1.2))
    A.set_emit("window_lit_warm", 0.6)
    for x in (-4, 2, 8):
        A.light("POINT", (x, -55.2, RAIL + 2.4), 60, (1.0, 0.72, 0.45), size=0.6, name="TrainInterior")
    return t1


def props():
    rr = random.Random(11)
    A.place("Bench_Metal", (-12, -44.3, 0), 180)
    A.place("Bench_Metal", (12, -44.3, 0), 180)
    A.place("Crate_Stack", (24, -44.5, 0), 190)
    A.place("Crate_Stack", (-40, -47, 0), math.degrees(1.1))
    A.place("TrashBin_Tipped", (8, -43.6, 0), 40)
    A.place("TrashBin", (-19, -43.0, 0), 0)
    A.place("Debris_Pile_C", (30, -48, 0), 30)
    A.place("Slab_Collapsed", (7.5, -44.6, 0), 188)
    A.place("Debris_Pile_A", (4.6, -45.6, 0), 70)
    A.place("Rubble_Chunk_S", (-3.5, -49.5, 0), 20)
    A.place("Rubble_Chunk_S", (-2.4, -48.8, 0), 120)
    A.place("Rubble_Chunk_L", (1.8, -46.0, 0), 75)
    A.place("TrafficCone", (16.2, -50.7, 0), 0)
    A.place("Junction_Box", (6, -41.8, 0), 180)
    A.place("Terminal_Kiosk_Off", (-2.5, -42.6, 0), 180)
    A.place("Sign_Hanging", (-4, -49.0, 5.0), 90)
    # hanging platform sign: invented glyph script on both faces
    C.glyph_sign((-4 - 0.09, -49.0, 4.0), -90, n=6, height=0.34, color=C.NCYAN, strength=12, seed=101, backing=False, frame=False)
    C.glyph_sign((-4 + 0.09, -49.0, 4.0), 90, n=6, height=0.34, color=C.NCYAN, strength=12, seed=101, backing=False, frame=False)


def cyber():
    rr = random.Random(7)
    # city-kit metro signage: neon arrows, LED wayfinding strips, a line pylon
    for x in (-27.0, -11.0, 7.0, 21.0, 36.5):
        A.place("Metro_Neon_Arrow", (x, -41.8, 2.2), 0)
    for x in (-30.0, -2.0, 10.0, 26.0):
        A.place("Metro_Wayfinding_Wall_Strip_4m", (x, -41.8, 3.1), 0)
    A.place("Metro_Line_Pylon", (-15.0, -46.4, 0), 25)
    A.place("Metro_Wayfinding_Hanging", (12.0, -49.0, 5.0), 90)
    # holo adverts on the track wall above the train, glyph light boxes along the north wall
    for i, (x, col, col2, sym) in enumerate([(-14, C.MAGENTA, C.NCYAN, "eye"), (2, C.NCYAN, C.YELLOW, "chevrons"), (18, C.YELLOW, C.MAGENTA, "triangle"),
                                             (34, C.MAGENTA, C.NCYAN, "rings")]):
        C.holo_panel((x, -57.9, 3.6), 180, (6.5, 3.2), col, col2, 2.2, symbol=sym, seed=200 + i)
    for i, x in enumerate((-30, -18, 2, 14, 26)):
        C.light_box((x, -41.95, 3.1), 0, size=(3.2, 0.8), color=[C.YELLOW, C.NCYAN, C.MAGENTA][i % 3], n=4, seed=210 + i, strength=2.6)
    C.glyph_sign((-11.5, -41.9, 2.4), 0, n=3, height=0.6, color=C.MAGENTA, seed=220)
    C.glyph_sign((20.0, -41.9, 2.3), 0, n=4, height=0.5, color=C.NCYAN, seed=221)
    # pillar neon (alternate magenta / cyan) and a cyan platform-edge strip
    for i, x in enumerate(range(-40, 41, 8)):
        col = C.MAGENTA if i % 2 else C.NCYAN
        for dx, dy in ((-0.49, -0.49), (0.49, -0.49)):
            C.strip((x + dx, -45.5 + dy, 0.3), (x + dx, -45.5 + dy, 4.3), col, 6.0, 0.025)
    C.strip((-44, -52.2, 0.03), (44, -52.2, 0.03), C.NCYAN, 5.0, 0.02)
    # ceiling neon runs
    C.strip((-44, -47.8, 5.0), (44, -47.8, 5.0), C.MAGENTA, 5.0, 0.03)
    C.strip((-44, -55.2, 5.0), (44, -55.2, 5.0), C.NCYAN, 4.0, 0.03)
    # train: magenta underglow on the platform side + glyph destination board on the cab
    C.strip((-6.4, -53.6, RAIL + 0.35), (10.5, -53.6, RAIL + 0.35), C.MAGENTA, 12.0, 0.04)
    A.light("AREA", (2.0, -53.4, RAIL + 0.2), 220, C.MAGENTA, size=16, size_y=0.3, shape="RECTANGLE", rot=(0, 0, 0), name="Underglow")
    C.glyph_sign((-6.75, -55.2, RAIL + 3.05), -90, n=5, height=0.22, color=C.YELLOW, strength=10, seed=230, backing=False, frame=False)
    # light shafts from ceiling vents through the haze
    for x in (-12, 0, 12, 24):
        A.light("SPOT", (x, -48.5, 5.0), 900, (0.75, 0.85, 1.0), size=0.1, rot=(0, 0, 0), spot=14, blend=0.4, name="Shaft")
    C.cable((-30, -41.9, 4.6), (-10, -41.9, 4.5), sag=0.6)
    C.cable((5, -41.9, 4.7), (25, -41.9, 4.6), sag=0.5)


def sign(loc, text, size, color, strength, rot):
    cu = bpy.data.curves.new("SignText", "FONT")
    cu.body = text
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.size = size
    cu.font = bpy.data.fonts.load(os.path.join(A.FONTS, "Rajdhani/Rajdhani-SemiBold.ttf"), check_existing=True)
    ob = bpy.data.objects.new("SignText", cu)
    ob.location = loc
    ob.rotation_euler = [math.radians(a) for a in rot]
    cu.materials.append(A.emissive("signtext", color, strength))
    A.link(ob)
    return ob


def actors():
    k = A.load_character("kael", (-8.6, -49.6, 0), -90 + 18, pose=("walk", 4))
    l = A.load_character("lyra", (-6.6, -47.6, 0), -90 + 8, pose=("walk", 16))
    A.curl_fingers(k, "Left", 55)
    A.curl_fingers(k, "Right", 55)
    # Lyra lifts her left hand: Aether light in the palm (her Echo ability)
    s = A.load_robot("sentinel", (9.5, -48.9, 0), -90 - 10, pose={
        "hips": (0, 8, 0), "spine": (6, 0, 0), "chest": (4, -10, 0), "head": (-8, 14, 0),
        "upperarm_L": (-12, 0, 18), "forearm_L": (-20, 0, 0), "upperarm_R": (10, 0, -16), "forearm_R": (-35, 0, 0),
        "thigh_L": (-14, 0, 2), "shin_L": (18, 0, 0), "foot_L": (-4, 0, 0), "thigh_R": (10, 0, -2), "shin_R": (8, 0, 0)})
    s.glow(5.0)
    A.light("POINT", (8.0, -48.0, 3.2), 60, (1.0, 0.2, 0.1), size=0.4, name="SentinelRim")
    # neon rims on the heroes
    mid = (k.rig.location + l.rig.location) / 2 + Vector((0, 0, 1.3))
    A.light("AREA", mid + Vector((4.5, 3.0, 1.0)), 160, C.MAGENTA, size=1.5, target=tuple(mid), name="RimMagenta")
    A.light("AREA", mid + Vector((4.0, -4.0, 0.8)), 140, C.NCYAN, size=1.5, target=tuple(mid), name="RimCyan")
    return k, l


def build(quick=False):
    A.reset()
    A.WET = 0.65
    A.EMIT_SCALE = 1.0
    res = (960, 540) if quick else (1920, 1080)
    A.setup_render(res, samples=48 if quick else 128, look="AgX - Medium High Contrast", exposure=0.1, adaptive=0.035)
    bpy.context.scene.cycles.volume_step_rate = 3.0
    A.world_gradient((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), strength=0.0)
    hall()
    lights(quick)
    train()
    props()
    cyber()
    k, l = actors()
    cl = (-18.8, -48.9, 1.45)
    cam = A.camera(cl, (14, -51.2, 2.0), lens=30, fstop=5.6, focus=(Vector(cl) - k.rig.location).length)
    A.light("AREA", (-13.0, -50.4, 3.0), 55, (0.85, 0.9, 1.0), size=2.5, target=tuple(k.rig.location + Vector((0, 0, 1.4))), name="HeroFill")
    A.fog_box((0, -50, 1.9), (100, 18, 7.4), density=0.012, color=(0.9, 0.9, 0.92), anisotropy=0.55, noise=0.5, noise_scale=0.12, name="Haze")
    A.compositor(bloom=0.5, bloom_size=0.7, threshold=0.8, dispersion=0.006, vignette=0.32, saturation=1.18)
    return cam


def main():
    a = A.args()
    quick = "--quick" in a
    build(quick)
    if quick:
        A.render(os.path.join(A.PREVIEWS, "tests", "metro_quick.png"))
    else:
        A.render(os.path.join(A.PREVIEWS, "loading_metro.png"), os.path.join(A.RES_ART, "Loading", "metro.jpg"))
        A.save_scene("metro_loading")


if __name__ == "__main__":
    main()
