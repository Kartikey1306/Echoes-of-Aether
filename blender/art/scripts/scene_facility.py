"""Research Facility, Aether Research Division: the atrium under its broken skylight. The containment exhibit (a
small Aether core above the hologram pedestal) still glows; a Warden drops in beside it as Kael and Lyra arrive
from the lobby. Containment pods glimpsed through the west wing glass.

  Blender -b --factory-startup --python scene_facility.py -- [--quick]

Layout from src/world/zones/FacilityZone.ts: atrium x[-14,14] z[0,30] (10 m tall, glass roof, columns at x=+-10,
z=5/15/25, balconies at 5 m), pedestal + core at (0, 15), lobby z[30,46] south, west wing pods/servers.
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
H = 10.0


def atrium():
    # floor (atrium + lobby), outer walls, balconies, columns, skylight beams + glass
    A.plane(30, 50, (0, -22, 0), "lab_floor", name="Floor")
    A.box((30, 0.4, H - 4), (0, 0.25, 4 + (H - 4) / 2), "lab_panel", name="NorthWallUpper")
    for i, x in enumerate(range(-12, 13, 4)):
        kind = "Wall_Lab_Door_Wide" if x == 0 else ("Wall_Lab_Window_4m" if x in (-8, 8) else "Corp_Wall_Panel_LED_4m")
        A.place(kind, (x, 0.0, 0), 180)
    for x in (-8, -4, 4, 8):
        A.place("Wall_Lab_Window_4m", (x, 0.0, 5.3), 180)
    A.place("Sign_Panel_M", (0, -0.25, 4.45), 0)
    C.glyph_sign((0, -0.45, 4.45), 0, n=6, height=0.42, color=C.NCYAN, strength=12, seed=301, backing=False, frame=False)
    A.place("Sign_Panel_S", (-14.0, -15.0, 4.7), 90)
    C.glyph_sign((-13.85, -15.0, 4.7), 90, n=4, height=0.36, color=C.YELLOW, strength=12, seed=302, backing=False, frame=False)
    # east wall: ground-level lab modules
    for y in range(-28, 0, 4):
        A.place("Wall_Lab_Window_4m" if y in (-24, -16) else "Wall_Lab_Straight_4m", (14.0, y + 2, 0), 90)
    A.box((0.4, 50, H), (-14.2, -22, H / 2), "lab_panel", name="WestWallUpper")
    A.box((0.4, 50, H - 4), (14.25, -22, 4 + (H - 4) / 2), "lab_panel", name="EastWall")
    # west wall has a wide opening to the containment lab at y in [-21, -9]
    bpy.data.objects.remove(bpy.data.objects["WestWallUpper"], do_unlink=True)
    A.box((0.4, 9, H), (-14.2, -25.5, H / 2), "lab_panel", name="WestWallS")
    A.box((0.4, 9, H), (-14.2, -4.5, H / 2), "lab_panel", name="WestWallN")
    A.box((0.4, 12, H - 4.2), (-14.2, -15, 4.2 + (H - 4.2) / 2), "lab_panel", name="WestLintel")
    for i in range(5):
        A.place("Glass_Partition_2_5m", (-14.2, -20.0 + i * 2.5, 0), 90)
    # south wall with the big lobby opening (12 m)
    A.box((8.5, 0.4, H), (-9.75, -30.2, H / 2), "lab_panel", name="SouthWallW")
    A.box((8.5, 0.4, H), (9.75, -30.2, H / 2), "lab_panel", name="SouthWallE")
    A.box((12, 0.4, H - 5), (0, -30.2, 5 + (H - 5) / 2), "lab_panel", name="SouthLintel")
    # balconies (3 m deep at 5 m) with railings
    for sx in (-1, 1):
        A.box((3.0, 30, 0.3), (sx * 12.5, -15, 5.0), "lab_panel", name="Balcony")
        for y in range(-29, 0, 2):
            A.place("Railing_2m", (sx * 11.0, y + 1, 5.15), 90)
        for y in (-27, -21, -15, -9, -3):
            A.place("Lab_CeilingLight", (sx * 12.5, y, 4.84), 90)
    for x in (-10, 10):
        for y in (-5, -15, -25):
            if (x, y) != (10, -25):
                A.place("Pillar_Concrete_10m", (x, y, 0), 0)
    beam = A.env_material("metal_dark")
    for x in range(-14, 15, 4):
        A.box((0.25, 30, 0.45), (x, -15, H + 0.2), beam, name="RoofBeam")
    for y in range(-30, 1, 5):
        A.box((28, 0.25, 0.45), (0, y, H + 0.2), beam, name="RoofBeam")
    glass = A.env_material("glass")
    A.box((28, 30, 0.05), (0, -15, H + 0.45), glass, name="Skylight")
    # a few panes are gone (sharper shafts)
    # lobby beyond (south): reception desk, sign, glass walls, dim lights
    A.place("Desk_Reception", (0, -37.0, 0), 0)
    A.box((26, 0.4, 5), (0, -46.2, 2.5), "lab_panel", name="LobbySouth")
    A.box((0.4, 16, 5), (-12.2, -38, 2.5), "lab_panel", name="LobbyW")
    A.box((0.4, 16, 5), (12.2, -38, 2.5), "lab_panel", name="LobbyE")
    A.box((26, 16, 0.3), (0, -38, 5.15), "lab_panel", name="LobbyCeil")
    for x in (-6, 0, 6):
        A.place("Lab_CeilingLight", (x, -40, 5.0), 0)
    C.glyph_sign((0, -30.5, 3.9), 180, n=7, height=0.6, color=C.NCYAN, strength=12, seed=303, backing=False, frame=False)


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


def exhibit():
    c = Vector((0, -15, 0))
    A.place("Holo_Pedestal", tuple(c), 0)
    core = c + Vector((0, 0, 3.6))
    core = c + Vector((0, 0, 2.6))
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=4, radius=0.55, location=core)
    s = bpy.context.active_object
    s.data.materials.append(A.aether_material("exhibit_core", strength=1.6, rim=2.0, scale=4.0))
    bpy.ops.object.shade_smooth()
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=0.2, location=core)
    bpy.context.active_object.data.materials.append(A.aether_material("exhibit_heart", strength=9.0, core=True, rim=0.6))
    ring = A.emissive("exhibit_ring", A.CYAN, 0.9)
    for i, (r, rx, rz) in enumerate([(0.95, 80, 0), (1.2, 62, 40)]):
        bpy.ops.mesh.primitive_torus_add(major_radius=r, minor_radius=0.008, major_segments=96, minor_segments=6, location=core,
                                         rotation=(math.radians(rx), 0, math.radians(rz)))
        bpy.context.active_object.data.materials.append(ring)
        bpy.context.active_object.visible_shadow = False
    A.light("POINT", core, 450, A.CYAN, size=0.5, name="CoreLight")
    A.light("POINT", c + Vector((0, 0, 0.9)), 60, A.CYAN, size=2.0, name="PedestalGlow")


def cyber():
    """Corporate-lab neon: balcony edge strips, floor perimeter light, holographic exhibit projection, wall
    holo screens, and the megacity glowing through the skylight."""
    for sx, col in ((-1, C.NCYAN), (1, C.MAGENTA)):
        C.strip((sx * 11.0, -30, 4.88), (sx * 11.0, 0, 4.88), col, 8.0, 0.03)
        C.strip((sx * 13.9, -30, 0.05), (sx * 13.9, 0, 0.05), col, 5.0, 0.03)
    C.strip((-14, -0.3, 0.05), (14, -0.3, 0.05), C.MAGENTA, 5.0, 0.03)
    for x in (-2.0, 2.0):
        C.strip((x, -0.35, 0.1), (x, -0.35, 3.3), C.YELLOW, 8.0, 0.03)
    # holo screens on the north wall above the balcony and on the east wall
    C.holo_panel((-7.0, -0.6, 7.6), 0, (6.0, 3.4), C.NCYAN, A.VIOLET, 2.2, symbol="rings", seed=311)
    C.holo_panel((7.0, -0.6, 7.6), 0, (6.0, 3.4), C.MAGENTA, C.NCYAN, 2.2, symbol="hex", seed=312)
    C.holo_panel((13.8, -12.0, 2.6), -90, (4.0, 2.2), C.YELLOW, C.MAGENTA, 2.0, symbol="chevrons", seed=313)
    # holographic projection around the exhibit core (big rotating data rings + glyph columns)
    core = Vector((0, -15, 2.6))
    for i, (r, rx, rz, col) in enumerate([(2.4, 90, 0, C.NCYAN), (2.9, 78, 35, C.MAGENTA), (3.5, 96, -20, C.NCYAN)]):
        segs = []
        for k in range(18):
            if k % 3 == 2:
                continue
            a0, a1 = k / 18 * math.tau, (k + 0.8) / 18 * math.tau
            pts = [Vector((math.cos(a0 + (a1 - a0) * t / 6) * r, math.sin(a0 + (a1 - a0) * t / 6) * r, 0)) for t in range(7)]
            segs.append(pts)
        ob = C.tubes(segs, col, 6.0, 0.012, name="HoloRing")
        ob.location = core
        ob.rotation_euler = (math.radians(rx), 0, math.radians(rz))
    for i in range(6):
        a = i / 6 * math.tau + 0.3
        C.glyph_sign(core + Vector((math.cos(a) * 3.9, math.sin(a) * 3.9, 0.6)), math.degrees(a) + 90, n=3, height=0.22,
                     color=C.NCYAN if i % 2 else C.MAGENTA, strength=8, seed=320 + i, backing=False, frame=False, vertical=True)
    # megacity above the skylight: tower crowns with neon + searchlight beams through the glass
    C.megacity((0, -15), 30, 90, 16, seed=33, hmin=40, hmax=120, lit=0.12, billboards=0.4)
    for p, col in (((-30, 30, 90), (1.0, 0.4, 0.9)), ((35, 10, 100), (0.5, 0.9, 1.0))):
        A.light("SPOT", p, 3.0e5, col, size=0.4, target=(0, -15, 0), spot=5, blend=0.3, name="Searchlight")


def corp_kit():
    """Corporate city-kit pieces: wall holo displays, a holo table, body scanners at the lobby, a glyph projector."""
    A.place("Holo_Display_Wall", (13.8, -20.0, 0), -90)
    A.place("Holo_Display_Wall", (13.8, -8.0, 0), -90)
    A.place("Holo_Table", (6.5, -5.5, 0), 20)
    for x in (-3.0, 3.0):
        A.place("Security_Gate_Scanner", (x, -31.5, 0), 0)
    A.place("Holo_Sign_Glyph", (-8.0, -26.0, 0), -30)


def west_lab():
    # containment pods behind the glass (prototype west wing)
    for i, (y, powered) in enumerate([(-19.5, True), (-16.5, False), (-13.0, True), (-10.0, True)]):
        A.place("CryoPod" if powered else "CryoPod_Empty", (-18.0, y, 0), 90)
        if powered:
            A.light("POINT", (-17.6, y, 1.4), 90, A.CYAN, size=0.4, name="PodGlow")
    A.plane(14, 22, (-21, -15, 0.0), "lab_floor", name="LabFloor")
    A.box((14, 22, 0.3), (-21, -15, 4.35), "lab_panel", name="LabCeil")
    A.box((0.4, 22, 4.2), (-25.2, -15, 2.1), "lab_panel", name="LabWall")
    for y in (-18, -12):
        A.place("Lab_CeilingLight", (-20, y, 4.2), 0)
    A.place("Server_Rack", (-24.5, -22.0, 0), -90)
    A.place("Server_Rack_Dark", (-24.5, -21.0, 0), -90)
    A.place("Lab_Bench", (-22.5, -8.0, 0), 180)


def clutter():
    rr = random.Random(21)
    A.place("Debris_Pile_C", (6.5, -9.0, 0), 20)
    A.place("Debris_Pile_C", (-6.0, -24.0, 0), 140)
    A.place("Slab_Collapsed", (9.0, -9.0, 0), 160)
    A.place("Office_Chair", (-8.5, -18.5, 0), 120)
    A.place("Terminal_Desk", (-9.0, -27.0, 0), 20)
    A.place("Bench_Street", (8.0, -28.4, 0), 180)
    A.place("Terminal_Kiosk", (11.6, -20.0, 0), -90)
    A.place("Crate_Small", (-3.5, -6.5, 0), 25)
    A.place("Rubble_Chunk_L", (3.2, -13.4, 0), 60)
    A.place("Rubble_Chunk_S", (-1.8, -19.6, 0), 10)
    A.place("Rubble_Chunk_S", (5.1, -16.9, 0), 100)
    for i in range(14):
        A.place("Rubble_Chunk_S", (rr.uniform(-9, 9), rr.uniform(-28, -3), 0), rr.uniform(0, 360), scale=rr.uniform(0.4, 0.9))


def actors():
    kp, lp, wp = (7.4, -22.1, 0), (5.2, -20.9, 0), (-2.2, -19.4, 0)
    w = A.load_robot("warden", wp, A.yaw_to(wp, kp, -10), pose={
        "hips": (0, -10, 0), "spine": (8, 0, 0), "chest": (6, 14, 0), "neck": (-4, 0, 0), "head": (-10, -8, 0),
        "clavicle_L": (0, 0, 6), "upperarm_L": (-70, 0, 30), "forearm_L": (-55, 0, 0), "hand_L": (-10, 0, 0),
        "clavicle_R": (0, 0, -6), "upperarm_R": (15, 0, -28), "forearm_R": (-40, 0, 0),
        "thigh_L": (-32, 0, 6), "shin_L": (40, 0, 0), "foot_L": (-10, 0, 0), "thigh_R": (16, 0, -4), "shin_R": (22, 0, 0), "foot_R": (-6, 0, 0)})
    w.glow(5.0)
    A.light("POINT", (-4.0, -13.4, 2.6), 80, (1.0, 0.2, 0.12), size=0.5, name="WardenGlow")
    k = A.load_character("kael", kp, A.yaw_to(kp, wp, 25), pose=("combat_idle", 12))
    l = A.load_character("lyra", lp, A.yaw_to(lp, wp, 15), pose=("l_echo", 9))
    A.curl_fingers(k, "Left", 70)
    A.curl_fingers(k, "Right", 70)
    # Lyra's Echo: a small violet-cyan charge in her raised palm
    hl, hr = l.bone_world("LeftHand", tail=True), l.bone_world("RightHand", tail=True)
    hand = hl if hl.z > hr.z else hr
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=0.07, location=hand + Vector((0, 0, 0.02)))
    bpy.context.active_object.data.materials.append(A.aether_material("echo_charge", color=A.VIOLET, color2=A.CYAN, strength=14.0, core=True))
    A.light("POINT", hand + Vector((0, 0, 0.05)), 25, (0.55, 0.45, 1.0), size=0.05, name="EchoCharge")
    return k, l, w


def build(quick=False):
    A.reset()
    A.WET = 0.0
    A.EMIT_SCALE = 1.0
    res = (960, 540) if quick else (1920, 1080)
    A.setup_render(res, samples=48 if quick else 128, look="AgX - Medium High Contrast", exposure=0.0, adaptive=0.035)
    bpy.context.scene.cycles.volume_step_rate = 3.0
    A.world_gradient((0.02, 0.03, 0.05), (0.04, 0.05, 0.07), (0.01, 0.01, 0.012), strength=0.6)
    atrium()
    exhibit()
    west_lab()
    clutter()
    cyber()
    corp_kit()
    k, l, w = actors()
    # moonlight through the skylight (shafts in the haze), cold overcast
    A.light("SUN", (0, 0, 30), 0.25, (0.62, 0.74, 0.95), size=8.0, rot=(12, 0, 145), name="Moon")
    # half of the balcony panels dead, one flickering dim
    A.set_emit("emit_panel_white", 1.4)
    for ob in bpy.data.objects:
        if ob.name.startswith("Lab_CeilingLight") and ob.location.z > 4.5 and abs(ob.location.x) > 11 and ob.location.y not in (-9.0, -27.0):
            for slot in ob.material_slots:
                if slot.material and slot.material.name.startswith("emit_panel_white"):
                    slot.link = "OBJECT"
                    slot.material = A.env_material("black")
    for x, y in [(12.5, -9.0), (-12.5, -9.0), (12.5, -27.0), (-12.5, -27.0)]:
        A.light("AREA", (x, y, 4.75), 70, (0.88, 0.94, 1.0), size=1.6, size_y=0.6, shape="RECTANGLE", name="Panel")
    A.light("AREA", (0, -40, 4.9), 220, (0.85, 0.92, 1.0), size=6, name="LobbyLight")
    A.light("POINT", (-9.5, -27.0, 3.4), 90, (1.0, 0.18, 0.12), size=0.2, name="Alarm")
    cl = (10.2, -29.8, 1.55)
    ct = (-1.2, -14.0, 2.5)
    cam = A.camera(cl, ct, lens=30, fstop=6.3, focus=(Vector(cl) - k.rig.location).length)
    A.light("AREA", (4.0, -26.0, 3.2), 70, (0.75, 0.88, 1.0), size=3.0, target=tuple(k.rig.location + Vector((0, 0, 1.4))), name="HeroFill")
    mid = (k.rig.location + l.rig.location) / 2 + Vector((0, 0, 1.3))
    A.light("AREA", mid + Vector((2.5, 5.5, 1.6)), 170, C.MAGENTA, size=1.2, target=tuple(mid), name="RimMagenta")
    A.light("AREA", mid + Vector((-4.5, 3.0, 1.0)), 200, C.NCYAN, size=1.8, target=tuple(mid), name="RimCyan")
    A.fog_box((0, -18, 5.2), (29, 40, 10.4), density=0.009, color=(0.85, 0.9, 0.95), anisotropy=0.6, noise=0.55, noise_scale=0.14, name="Haze")
    A.compositor(bloom=0.45, bloom_size=0.7, threshold=0.85, dispersion=0.005, vignette=0.3, saturation=1.18)
    return cam


def main():
    a = A.args()
    quick = "--quick" in a
    build(quick)
    if quick:
        A.render(os.path.join(A.PREVIEWS, "tests", "facility_quick.png"))
    else:
        A.render(os.path.join(A.PREVIEWS, "loading_facility.png"), os.path.join(A.RES_ART, "Loading", "facility.jpg"))
        A.save_scene("facility_loading")


if __name__ == "__main__":
    main()
