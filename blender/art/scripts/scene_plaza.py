"""Central Plaza (The Fallen District): night, heavy rain. Kael and Lyra cross the flooded square toward the
broken Aether Monument; the survivors' camp glows behind it, the facility gate and dead civic blocks beyond.

  Blender -b --factory-startup --python scene_plaza.py -- [--quick] [--shot loading|keyart|keyart_wide|banner|social|itch]

Layout follows src/world/zones/PlazaZone.ts (prototype metres, three.js -> Blender: (x, y, z) -> (x, -z, y)).
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

AMBER = A.hexlin("#ffb02e")

P = A.proto


def ground():
    # plaza paving raised 15 cm, ring road asphalt, wet sidewalks, curbs
    A.plane(64, 64, (0, 0, 0.15), "paving", name="Paving")
    A.plane(220, 220, (0, 20, 0.0), "asphalt", name="Road")
    for (x, y, w, d) in [(0, 32.2, 64.6, 0.4), (0, -32.2, 64.6, 0.4), (-32.2, 0, 0.4, 64.6), (32.2, 0, 0.4, 64.6)]:
        A.box((w, d, 0.36), (x, y, 0.0), "concrete", name="Curb")
    for (x, y, w, d) in [(0, 47, 96, 6), (-47, 0, 6, 100), (47, 0, 6, 100)]:
        A.box((w, d, 0.2), (x, y, 0.05), "concrete_wet", name="Sidewalk")
    # lane markings (amber, subtle)
    for yy in range(-28, 29, 6):
        for xx in (38, -38):
            A.box((0.15, 2.5, 0.01), (xx, yy, 0.005), A.emissive("lane", (1.0, 0.55, 0.15), 0.25), name="Lane")


def monument():
    z = 0.15
    A.place("Monument_Base", (0, 0, z))
    pl = A.manifest()["Monument_Base"]["placements"]
    for part, u in pl.items():
        loc = Vector(A.unity_to_blender(u)) + Vector((0, 0, z))
        rot = (0, 0, 0)
        if part == "Monument_Ring_A":
            rot = (math.degrees(0.25), 0, 150)
        elif part == "Monument_Ring_B":
            rot = (math.degrees(-0.35), 0, -60)
        elif part == "Monument_UpperShard":
            rot = (0, 4, 0)
        elif part == "Monument_Ring_Fallen":
            rot = (0, 0, 35)
        A.place(part, tuple(loc), rot)
    core = Vector((0, 0, 7.45 + z))
    A.light("POINT", core, 4200, A.CYAN, size=0.6, name="CoreLight")
    A.light("POINT", core + Vector((0, 0, -5.5)), 260, A.CYAN, size=1.5, name="BasinGlow")
    # inner heart of the core (prototype: emissive inner sphere)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=0.36, location=core)
    heart = bpy.context.active_object
    heart.data.materials.append(A.aether_material("core_heart", strength=22.0, core=True, rim=1.0))
    return core


KIT = {"A": ("Building_MidRise_A", 12.0), "B": ("Building_MidRise_B", 20.0), "C": ("Building_MidRise_C", 16.0), "D": ("Building_HighRise_D", 16.0)}


def street_wall(start, end, face_yaw, seq, gap=0.8, z=0.0):
    """Line of city-kit buildings from `start` to `end` (Blender XY), fronts facing face_yaw (deg, 0 = -Y)."""
    s0, s1 = Vector(start), Vector(end)
    d = (s1 - s0).normalized()
    t, i = 0.0, 0
    L = (s1 - s0).length
    while t < L:
        name, w = KIT[seq[i % len(seq)]]
        if t + w > L + 2:
            break
        c = s0 + d * (t + w / 2)
        A.place(name, (c.x, c.y, z), face_yaw)
        t += w + gap
        i += 1


FACE_YAW = {"s": 0, "n": 180, "e": 90, "w": -90}
SODIUM = (1.0, 0.52, 0.18)
KEYART_EYEWEAR = True


def buildings():
    """The plaza's street walls: the bespoke Plaza_Block_00..22 buildings from the city-landmark kit, placed at their
    prototype block positions (plazaBlock x / z / faces in the kit manifest), then the city's landmark skyline
    (Jade Lantern Tower, Helix Arcology, Meridian Spire, The Stack, Signal Spire, Bridge Twins ...) and the
    Skyline_* megatowers behind."""
    lm = A._kitman("landmarks")["_assets"]
    for name, rec in sorted(lm.items()):
        pb = rec.get("plazaBlock")
        if not pb:
            continue
        A.place(name, P(pb["x"], 0, pb["z"]), FACE_YAW.get(pb["faces"][0], 0))
    sky = [("LM_AG_HelixArcology", -40, 230, 10), ("LM_NM_JadeLanternTower", 70, 150, -20), ("LM_AG_MeridianSpire", -120, 190, 25),
           ("LM_KS_TheStack", 140, 210, -35), ("LM_KS_SignalSpire", 30, 290, 0), ("LM_KS_BridgeTwins", -170, 130, 60),
           ("LM_AG_ExchangeAtrium", -10, 150, 0), ("LB_AG_Office_B", 100, 120, -10), ("LB_KS_Tenement_B", -90, 115, 15),
           ("LB_AG_Office_A", 40, 120, 0), ("LB_KS_Slab_C", -60, 140, 5), ("LM_FR_CoolingTower", 220, 280, 0),
           ("LB_KS_Tenement_A", 125, 95, -60), ("LB_NM_Shophouse_B", -120, 80, 70)]
    for name, x, y, rz in sky:
        try:
            A.place(name, (x, y, 0), rz)
        except KeyError:
            pass
    r = random.Random(9)
    for name, x, y, rz, sc in [("Skyline_Twin_D", -220, 380, 10, 1.1), ("Skyline_Tower_A", 180, 360, -15, 1.3), ("Skyline_Tower_B", 260, 200, -40, 1.3),
                               ("Skyline_Tower_C", -260, 240, 40, 1.2), ("Skyline_Tower_A", -330, 160, 60, 1.2), ("Skyline_Tower_B", 90, 460, 0, 1.5),
                               ("Skyline_Tower_C", 330, 330, -50, 1.4)]:
        A.place(name, (x, y, 0), rz + r.uniform(-4, 4), scale=sc)


def gate():
    g = Vector(P(0, 0, -46))
    A.place("Gate_Facility_Frame", tuple(g), 0)
    A.place("Gate_Facility_Leaf", tuple(g + Vector((-6, 0, 0))), 0)
    A.place("Gate_Facility_Leaf", tuple(g + Vector((6, 0, 0))), 0)
    for x in (-10, 10):
        A.light("POINT", g + Vector((x, -1.2, 9.0)), 25, (1, 0.2, 0.15), size=0.15, name="GateLamp")
    # header sign: invented glyph script (no real-world words)
    C.glyph_sign(g + Vector((0, -1.4, 9.6)), 0, n=7, height=0.8, color=C.NCYAN, strength=14, seed=21, backing=False, frame=False)


def sign(loc, text, size, color, strength, rot=(90, 0, 0), font="Rajdhani/Rajdhani-SemiBold.ttf"):
    cu = bpy.data.curves.new("SignText", "FONT")
    cu.body = text
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.size = size
    cu.font = bpy.data.fonts.load(os.path.join(A.FONTS, font), check_existing=True)
    cu.extrude = 0.004
    ob = bpy.data.objects.new("SignText", cu)
    ob.location = loc
    ob.rotation_euler = [math.radians(a) for a in rot]
    cu.materials.append(A.emissive("signtext", color, strength))
    A.link(ob)
    return ob


def elevated_rail():
    for y in range(-70, 71, 14):
        A.place("ElevatedRail_Pier", (52, y, 0), 90)
    for y in range(-63, 64, 14):
        A.place("ElevatedRail_Deck_14m", (52, y, 8 + 2.73), 0)


def street():
    cars = [((-38, -20, 0.1), "CyberCar_Sedan_Wrecked"), ((-39, 18, math.pi + 0.3), "CyberCar_Taxi"), ((38, -24, math.pi - 0.15), "CyberCar_Coupe"),
            ((37, 26, 0.6), "CyberVan_Burnt"), ((-18, -38, math.pi / 2 + 0.2), "CyberCar_Sedan"), ((16, 38, -math.pi / 2), "CyberCar_Sedan_Wrecked"),
            ((-5, 40, math.pi / 2 + 0.5), "CyberVan"), ((-36.5, -2.0, -0.25), "CyberCar_Sedan_Wrecked")]
    for (x, z, yaw), kind in cars:
        A.place_vehicle(kind, P(x, 0, z), math.degrees(yaw))
    A.place_vehicle("CyberBike", P(-11.2, 0.15, 23.6), 130)
    # flyers over the ring road and between the towers
    for name, p, yaw in [("HoverCar_A", (-12, 22, 21), 75), ("HoverCar_B", (24, 40, 33), -110), ("HoverTruck", (-34, 72, 48), 95),
                         ("HoverCar_A", (16, 95, 66), 20)]:
        A.place_vehicle(name, p, yaw)
    A.place("Bus_Transit", P(39, 0, -6), math.degrees(0.05 + math.pi / 2))
    for x, z, y in [(-34, -34, 0.8), (-33, -30, 0.4), (34, 34, 2.4), (30, -40, 0.2), (-26, 34, 1.4)]:
        A.place("Barrier_Jersey", P(x, 0, z), math.degrees(y))
    A.place("Barrier_Jersey_Broken", P(-10, 0, 44), 6)
    debris = [(-26, -26), (26, 26), (-22, 28), (36, 12), (-36, -6), (8, -38), (-12, 22.5)]
    rr = random.Random(4)
    for i, (x, z) in enumerate(debris):
        A.place(rr.choice(["Debris_Pile_A", "Debris_Pile_C", "Debris_Pile_A", "Debris_Pile_B"]), P(x, 0.15 if abs(x) < 32 and abs(z) < 32 else 0, z), rr.uniform(0, 360))
    for x, z, y in [(-12, -18, 0.3), (14, 16, 1.6), (-16, 18, -0.9), (-24, -10, 1.0)]:
        A.place("Bench_Street", P(x, 0.15, z), math.degrees(y))
    for x, z, t in [(-14, -20, False), (16, 18, True), (28, 10, False), (-20, 24, True)]:
        A.place("TrashBin_Tipped" if t else "TrashBin", P(x, 0.15, z), rr.uniform(0, 360))
    for x, z in [(-20, -20), (20, 20), (-20, 20), (24, -4), (-24, -4)]:
        A.place("Planter_DeadTree", P(x, 0.15, z), rr.uniform(0, 90))
    for x in range(-12, 13, 3):
        A.place("Bollard", P(x, 0.15, -31.0), 0)
    A.place("Slab_Broken_Flat", P(-14.5, 0.15, 10.5), 25)
    A.place("Rebar_Cluster", P(-13.2, 0.15, 9.2), 40)
    A.place("TrafficCone", P(-10.5, 0.15, 21.8), 0)
    A.place("TrafficCone", P(-11.3, 0.15, 22.6), 0, scale=1.0)
    A.place("StreetLight_Broken", P(-30, 0.15, 30), math.degrees(3 * math.pi / 4))
    lamps = [(30, -30, math.pi / 4 + math.pi, True), (-30, -30, -math.pi / 4, True), (-30, -6, math.pi / 2, True), (30, -10, -math.pi / 2, True),
             (0, -30, 0, True), (30, 30, -3 * math.pi / 4, True), (-30, 6, math.pi / 2, False)]
    for x, z, y, on in lamps:
        ob = A.place("StreetLight" if on else "StreetLight_Broken", P(x, 0.15, z), math.degrees(y))
        if on:
            off = A.anchor("StreetLight", "light")
            bpy.context.view_layer.update()
            wl = ob.matrix_world @ off
            A.light("SPOT", wl - Vector((0, 0, 0.15)), 4200, SODIUM, size=0.25, rot=(0, 0, 0), spot=120, blend=0.7,
                    name="StreetLamp")
            A.light("POINT", wl, 60, SODIUM, size=0.3, name="StreetLampGlow")


def sodium_row():
    """Extra sodium street lamps on the north sidewalk and the ring road (amber pools on the wet paving)."""
    for x in (-44, -22, 22, 44):
        ob = A.place("StreetLight", (x, 45.4, 0.05), 180)
        bpy.context.view_layer.update()
        wl = ob.matrix_world @ A.anchor("StreetLight", "light")
        A.light("SPOT", wl - Vector((0, 0, 0.15)), 4200, SODIUM, size=0.25, spot=120, blend=0.7, name="StreetLamp")
        A.light("POINT", wl, 60, SODIUM, size=0.3, name="StreetLampGlow")


def camp():
    cx, cz = 22, -22
    c = lambda dx, dz, y=0.15: P(cx + dx, y, cz + dz)  # noqa: E731
    A.place("TarpShelter_Large", c(4, -4), math.degrees(0.3))
    A.place("TarpShelter_Blue", c(-3, -6), math.degrees(-0.2))
    A.place("TarpShelter", c(6, 3), math.degrees(1.2))
    rr = random.Random(5)
    for i in range(5):
        A.place(rr.choice(["Crate_Stack", "Crate_Cargo", "Crate_Wood", "Crate_Cargo_Yellow"]), c(-6 + (i % 3) * 2.2, 5 + (i // 3) * 2), math.degrees(i * 0.4))
    A.place("Generator_Industrial", c(-7, -1), 90)
    A.place("FireBarrel", c(0, 0), 0)
    fire = Vector(c(0, 0)) + Vector((0, 0, 1.15))
    A.light("POINT", fire, 2600, (1.0, 0.42, 0.14), size=0.35, name="Fire")
    A.light("POINT", fire + Vector((0, 0, 0.7)), 300, (1.0, 0.55, 0.2), size=0.6, name="FireGlow")
    # work lights hung under the tarps
    for dx, dz in [(4, -4), (-3, -6), (6, 3)]:
        A.light("POINT", Vector(c(dx, dz)) + Vector((0, 0, 2.2)), 220, (1.0, 0.68, 0.38), size=0.12, name="TarpLamp")
    A.place("Antenna_Mast_5m", c(6, -3.4), 0)
    A.place("Terminal_Desk", c(4.5, -2.6), 180)
    A.place("Terminal_Kiosk", c(-8.5, 2.5), math.degrees(math.pi / 2 + 0.3))
    A.place("MarketStall", c(-1, -9), 180)
    for x, z, y in [(-10, -8, 0.4), (9, 8, -0.7), (-10, 8, 2.2)]:
        A.place("Barrier_Jersey", c(x, z), math.degrees(y))
    lant = Vector(c(3.5, -5)) + Vector((0, 0, 2.0))
    A.light("POINT", lant, 90, (1.0, 0.6, 0.3), size=0.15, name="Lantern")
    gen = Vector(c(-7, -1))
    A.light("POINT", gen + Vector((0, -1.0, 1.0)), 6, (0.3, 1.0, 0.5), size=0.05, name="GenLED")


def npcs(full=True):
    out = []
    if full:
        out.append(A.load_character("oren", P(19, 0.15, -15.5), math.degrees(math.pi * 1.1) + 180, pose=("npc_crossed", 30), detail=False))
        out.append(A.load_character("mira", P(26.5, 0.15, -23.6), math.degrees(math.pi * 0.5) + 180, pose=("npc_work", 10), detail=False))
        A.load_robot("bolt", P(14.5, 0.15, -26.5), 200, pose={"head": (10, -20, 0), "upperarm_L": (-20, 0, 10), "forearm_L": (-40, 0, 0)})
    return out


def drones():
    ds = []
    for (x, y, z, yaw) in [(13, 5.2, -6, 200), (-4, 7.5, -27, 160)]:
        d = A.load_robot("drone", P(x, y, z), yaw, pose="combat")
        ds.append(d)
        A.light("POINT", Vector(P(x, y, z)) + Vector((0, 0, -0.5)), 15, A.CYAN, size=0.1, name="DroneGlow")
    return ds


def foreground():
    A.place_vehicle("CyberCar_Sedan_Wrecked", P(13.6, 0.15, 20.2), 64)
    A.place("Barrier_Jersey_Broken", P(-6.5, 0.15, 24.5), -15)
    A.place("Debris_Pile_C", P(12.2, 0.15, 19.2), 30)


def cyber():
    """Neon dressing: city-kit neon/signage (LED billboards, glyph columns, blade lightboxes, holo ad frames and
    glyph projectors, ramen stall, vending machines, neon bus shelter, cyber traffic lights, lantern strings,
    sagging cable bundles), plus scene-only pieces from cyberkit (giant holo figure, holo adverts over the road,
    curb light strips, searchlights, air traffic)."""
    # LED walls and glyph columns on the north and east street walls
    for x, z, n in [(-62, 9, "Billboard_LED_Wall_6x3"), (-30, 12, "Billboard_LED_Wall_6x3_B"), (34, 10, "Billboard_LED_Wall_6x3_C"),
                    (70, 14, "Billboard_LED_Wall_6x3_Screen")]:
        A.place(n, (x, 49.8, z), 0)
    for y, z, n in [(-26, 8, "Billboard_LED_Wall_6x3_C"), (8, 11, "Billboard_LED_Wall_6x3"), (30, 7, "Billboard_LED_Wall_6x3_B")]:
        A.place(n, (54.8, y, z), -90)
    for x, z, n in [(-44, 6, "Neon_Glyph_Column"), (-21, 4.5, "Neon_Glyph_A"), (24, 5, "Neon_Glyph_B"), (46, 7, "Neon_Glyph_Column"), (58, 4, "Neon_Glyph_C")]:
        A.place(n, (x, 49.8, z), 0)
    for y, z, n in [(-38, 6, "Neon_Ring_Double"), (-12, 4.5, "Neon_Circle"), (20, 5.5, "Neon_Arrow_Down"), (40, 4, "Neon_Bowl")]:
        A.place(n, (54.8, y, z), -90)
    for y, z, n in [(-30, 5, "Neon_Glyph_Column"), (-8, 6, "Sign_Blade_C"), (18, 4.5, "Neon_Glyph_B")]:
        A.place(n, (-49.4, y, z), 90)
    # street-level kit: stalls, vending machines, shelters, holo frames, traffic lights
    for name, p, rz in [("Ramen_Stall", (-40, 45.6), 180), ("Street_Food_Counter", (-26, 46.2), 180), ("Vending_Machine_Drinks", (14, 46.6), 180),
                        ("Vending_Machine_Food", (15.1, 46.6), 180), ("Kiosk_Neon", (30, 46.0), 180), ("Bus_Shelter_Neon", (47.5, 18, 0), -90),
                        ("Holo_Ad_Frame", (-12.5, 34.0), 200), ("Holo_Sign_Glyph", (12.0, 33.2), 160), ("Holo_Ad_Frame", (44.6, -20), -90),
                        ("Traffic_Light_Cyber", (-34.6, 34.6), 0), ("Traffic_Light_Cyber", (34.6, -34.6), 180), ("Traffic_Light_Pole_Small", (34.6, 34.6), -90)]:
        A.place(name, (p[0], p[1], 0.05 if abs(p[0]) > 32 or abs(p[1]) > 32 else 0.15), rz)
    for x in (-40, -30, -20, 20, 30, 40):
        A.place("Lantern_String_4m", (x - 2, 46.4, 4.2), 0)
    for x in (-46, -24, 22):
        A.place("Cable_Bundle_Sag_8m", (x, 49.6, 7.5), 0)
    # camp lantern strings (kit) under the tarps
    cx, cy = 22, 22
    A.place("Lantern_String_4m", (cx - 5, cy + 4, 2.9), 10)
    A.place("Lantern_String_4m", (cx + 1, cy - 2, 3.0), -20)
    # holo adverts and a giant holographic figure (scene-only, cyberkit)
    C.holo_panel((-30, 44, 20), 10, (12, 7), C.NCYAN, (0.1, 0.3, 1.0), 2.2, symbol="eye", seed=31)
    C.holo_panel((44, 30, 23), -35, (11, 7), C.NCYAN, C.YELLOW, 2.2, symbol="chevrons", seed=32)
    C.holo_figure("maren", (-44, 82, 24), 160, 17.0, (0.05, 0.55, 0.9), C.NCYAN, pose=("talk", 40), strength=1.4)
    # elevated rail underglow, curb strips
    C.strip((49.6, -70, 8.0), (49.6, 70, 8.0), AMBER, 5.0, 0.06)
    C.strip((54.4, -70, 8.0), (54.4, 70, 8.0), C.NCYAN, 7.0, 0.05)
    C.strip((-32.4, -32.4, 0.25), (32.4, -32.4, 0.25), C.NCYAN, 4.0, 0.03)
    C.strip((-32.4, 32.4, 0.25), (32.4, 32.4, 0.25), AMBER, 4.0, 0.03)
    C.strip((32.4, -32.4, 0.25), (32.4, 32.4, 0.25), C.NCYAN, 4.0, 0.03)
    for p, t, col in [((-60, 120, 110), (-5, 20, 0), (0.7, 0.85, 1.0)), ((70, 110, 120), (20, 10, 0), (1.0, 0.45, 0.9)),
                      ((20, 160, 150), (6, 30, 0), (0.6, 1.0, 1.0))]:
        A.light("SPOT", p, 6.0e5, col, size=0.6, target=t, spot=6, blend=0.3, name="Searchlight")
    C.air_traffic((0, 160), (360, 260), count=60, seed=12, z=(60, 190))


def heroes(shot):
    if shot == "loading":
        k = A.load_character("kael", (5.6, -17.2, 0.15), 180 + 22, pose=("walk", 7))
        l = A.load_character("lyra", (7.5, -18.4, 0.15), 180 + 14, pose=("walk", 19))
        A.light("AREA", (6.5, -21.0, 3.2), 220, (0.85, 0.9, 1.0), size=3, target=(6.5, -17.8, 1.3), name="HeroKey")
    else:
        kp, lp = (-0.95, -13.0, 0.15), (0.95, -13.35, 0.15)
        k = A.load_character("kael", kp, A.yaw_to(kp, (0.2, -18.4), 16), pose=("idle", 40))
        l = A.load_character("lyra", lp, A.yaw_to(lp, (0.2, -18.4), -14), pose=("idle", 90))
        A.rot_bone(k, "Head", x=-4)
        A.rot_bone(l, "Head", x=-3)
        if KEYART_EYEWEAR:
            A.attach_custom(k, "eyewear", "aviator")
            A.attach_custom(l, "eyewear", "cyber_visor")
    return k, l


PANO_ROT = 180.0  # puts the storm deck's amber industry glow over the north street, magenta district off to the side
SHOTS = {
    # name: (res, cam loc, target, lens, fstop)
    "loading": ((1920, 1080), (7.5, -31.0, 1.65), (6.4, 6.0, 4.6), 28, 8.0),
    "keyart": ((1920, 1080), (0.1, -17.3, 0.85), (0.0, -6.0, 3.1), 28, 2.8),
}


def build(shot="loading", quick=False):
    A.reset()
    A.WET = 1.0
    A.EMIT_SCALE = 1.0
    res, cl, ct, lens, fstop = SHOTS[shot]
    if quick:
        res = (res[0] // 2, res[1] // 2)
    A.setup_render(res, samples=48 if quick else 128, look="AgX - Medium High Contrast", exposure=0.3, adaptive=0.035)
    bpy.context.scene.cycles.volume_step_rate = 3.0
    A.world_pano(strength=0.55, rot_deg=PANO_ROT)
    A.light("SUN", (0, 0, 50), 0.10, (0.6, 0.78, 0.9), size=6, rot=(55, 0, 145), name="Moon")
    ground()
    core = monument()
    buildings()
    gate()
    elevated_rail()
    street()
    sodium_row()
    camp()
    npcs()
    drones()
    foreground()
    cyber()
    k, l = heroes(shot)
    # soft fill from behind the camera so the suits read (wet street-light bounce)
    A.light("AREA", Vector(cl) + Vector((-3, -2, 3.5)), 260 if shot == "loading" else 420, (0.85, 0.88, 1.0), size=6,
            target=tuple(k.rig.location + Vector((0, 0, 1.2))), name="HeroFill")
    # neon rim lights on the heroes (magenta from the left signage, cyan from the monument side)
    mid = (k.rig.location + l.rig.location) / 2 + Vector((0, 0, 1.3))
    rim = 1.0 if shot == "loading" else 1.6
    A.light("AREA", mid + Vector((-5.0, 6.0, 1.5)), 260 * rim, SODIUM, size=2.0, target=tuple(mid), name="RimSodium")
    A.light("AREA", mid + Vector((5.0, 5.0, 1.2)), 360 * rim, C.NCYAN, size=2.0, target=tuple(mid), name="RimCyan")
    A.light("AREA", mid + Vector((6.0, -1.0, 2.5)), 160 * rim, AMBER, size=2.5, target=tuple(mid), name="RimAmber")
    cam = A.camera(cl, ct, lens=lens, fstop=fstop, focus=(Vector(cl) - Vector(k.rig.location)).length)
    # atmosphere: big low-density volume (light shafts around the core and lamps) + denser ground haze
    A.fog_box((10, 60, 60), (260, 300, 130), density=0.008, color=(0.62, 0.8, 0.86), anisotropy=0.5,
              falloff_z=(2, 120), noise=0.45, noise_scale=0.04, name="Fog")
    A.rain((cl[0] + 4, cl[1] + 27, 8), (46, 42, 18), count=22000 if not quick else 12000, length=(0.35, 0.75), width=0.005,
           wind=(0.18, 0.06), cam=cam, brightness=0.32)
    A.compositor(bloom=0.45, bloom_size=0.7, threshold=0.9, dispersion=0.005, vignette=0.3, saturation=1.08)
    return cam


def main():
    a = A.args()
    quick = "--quick" in a
    shot = a[a.index("--shot") + 1] if "--shot" in a else "loading"
    build(shot, quick)
    tag = f"plaza_{shot}" + ("_quick" if quick else "")
    if shot == "loading" and not quick:
        A.render(os.path.join(A.PREVIEWS, "loading_plaza.png"), os.path.join(A.RES_ART, "Loading", "plaza.jpg"))
        A.save_scene("plaza_loading")
    else:
        A.render(os.path.join(A.PREVIEWS, "tests", tag + ".png"))


if __name__ == "__main__":
    main()
