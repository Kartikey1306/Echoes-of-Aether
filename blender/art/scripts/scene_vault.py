"""Underground Aether Vault, the resonance lock chamber: three resonator pillars, hexagonal glyph plates, the sealed
lock door with its violet seam. Lyra attunes the central resonator while Kael watches the dark; a Phase Stalker
waits on the high grating ledge.

  Blender -b --factory-startup --python scene_vault.py -- [--quick]

Layout from src/world/zones/VaultZone.ts: lock chamber x[-14,14] z[40,60] (10 m high), resonators at (-8,50),
(0,54), (8,50), glyph plates at (-13.75,4,46), (0,6,59.75), (13.75,4,46), lock door at z=60.2, grating ledge
at (12,3,56) with stairs from z=47.
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

H = 10.0


def room():
    for x in range(-14, 14, 4):
        for y in range(-60, -36, 4):
            A.place("Floor_Grate_4m", (x + 2, y + 2, 0), 0)
    # walls of heavy panels (two rows) + plain band above
    for x in range(-14, 14, 4):
        cx = x + 2
        for z in (0, 4):
            if abs(cx) < 3.1 and z == 0:
                continue  # lock door opening
            A.place("Vault_Wall_Panel_4m_Cyan" if (z == 0 and cx in (-10, 10)) else "Vault_Wall_Panel_4m", (cx, -60.0, z), 180)
    A.box((28, 0.5, 2.0), (0, -60.2, 9.0), "metal_dark", name="NorthBand")
    for y in range(-60, -36, 4):
        cy = y + 2
        for z in (0, 4):
            A.place("Vault_Wall_Panel_4m", (-14.0, cy, z), 90)
            A.place("Vault_Wall_Panel_4m" if z else "Vault_Wall_Panel_4m_Cyan", (14.0, cy, z), -90)
    A.box((0.5, 26, 2.0), (-14.2, -48, 9.0), "metal_dark", name="WestBand")
    A.box((0.5, 26, 2.0), (14.2, -48, 9.0), "metal_dark", name="EastBand")
    A.box((29, 26, 0.4), (0, -48, H + 0.2), "metal_plate", name="Ceiling")
    # ceiling ribs + hanging conduits
    for y in range(-58, -38, 4):
        A.box((28, 0.4, 0.7), (0, y, H - 0.35), "metal_dark", name="Rib")
    # corner pillars
    for x, y in [(-12.6, -58.6), (12.6, -58.6), (-12.6, -41.5), (12.6, -41.5)]:
        A.place("Pillar_Vault_4m", (x, y, 0), 0)
        A.place("Pillar_Vault_4m", (x, y, 4), 0)
    # pipes along the west wall
    for y in range(-58, -40, 1):
        A.place("Pipe_Straight_1m", (-13.4, y + 0.5, 2.6), 90)
    for y in (-56, -50, -44):
        A.place("Pipe_Bracket", (-13.6, y, 2.6 - 0.2), 90)


def lock_door():
    A.place("Vault_LockDoor_Half", (1.5, -60.2, 0), 0)
    A.place("Vault_LockDoor_Half", (-1.5, -60.2, 0), 180)
    amber = A.emissive("beacon_amber", (1.0, 0.55, 0.12), 12.0)
    for x in (-3.4, 3.4):
        A.cylinder(0.12, 0.22, (x, -59.7, 5.0), amber, n=16, name="Beacon")
        A.light("POINT", (x, -59.4, 5.15), 40, (1.0, 0.5, 0.12), size=0.1, name="BeaconLight")
    A.box((7.4, 0.9, 0.6), (0, -60.2, 5.3), "metal_dark", name="DoorHeader")
    for x in (-3.4, 3.4):
        A.box((0.8, 0.9, 5.6), (x, -60.2, 2.8), "metal_dark", name="DoorPost")
    A.place("Vault_GlyphPlate", (0, -59.75, 7.2), 180)
    A.light("POINT", (0, -59.3, 2.6), 650, A.VIOLET, size=0.2, name="SeamGlow")
    A.light("POINT", (0, -59.0, 7.2), 160, A.VIOLET, size=0.6, name="GlyphGlow")
    A.set_emit("emit_violet", 9.0)
    # Vault darkness behind the door seam
    A.box((7, 3, 6), (0, -62.2, 3), "black", name="Behind")


def resonators():
    pts = [((-8, -50), A.VIOLET, 0.0), ((0, -54), A.CYAN, 1.0), ((8, -50), A.VIOLET, 0.0)]
    for (x, y), col, attuned in pts:
        A.place("Vault_ResonatorPillar", (x, y, 0), 0)
        r = A.place("Vault_ResonatorRing", (x, y, 2.2), 25 * x)
        if attuned:
            ring = A.emissive("ring_attuned", A.CYAN, 6.0)
            for slot in r.material_slots:
                slot.link = "OBJECT"
                slot.material = ring
        cr = A.place("Vault_Crystal", (x, y, 3.1), 15 * x)
        A.light("POINT", (x, y, 3.2), 300 if attuned else 110, col, size=0.3, name="CrystalGlow")
        A.light("POINT", (x, y, 1.0), 60 if attuned else 25, col, size=0.6, name="PillarGlow")
    # a thin beam of Aether between the attuned resonator and the door glyph
    return pts


def glyphs():
    for loc, rot in [((-13.65, -46, 4), 90), ((13.65, -46, 4), -90)]:
        A.place("Vault_GlyphPlate", loc, rot)
        d = Vector((1 if rot == 90 else -1, 0, 0))
        A.light("POINT", Vector(loc) + d * 0.6, 70, A.VIOLET, size=0.5, name="GlyphGlow")


def ledge():
    A.box((3, 7, 0.25), (12, -56, 3.0), "grating", name="Ledge")
    for y in (-59, -53):
        A.box((0.15, 0.15, 3.0), (10.6, y, 1.5), "metal_dark", name="LedgePost")
    A.place("Stairs_Metal_3m", (12.2, -47.4, 0), 0)
    A.place("Railing_2m", (10.55, -55.0, 3.1), 90)
    A.place("Railing_2m", (10.55, -57.0, 3.1), 90)
    A.place("Crate_Small", (12.6, -58.4, 3.12), 15)


def cyber():
    """Vault neon: hazard-yellow door frame, magenta security lasers across the lock, glyph columns on the walls,
    holographic glyph halos over the resonators."""
    for x in (-3.85, 3.85):
        C.strip((x, -59.6, 0.1), (x, -59.6, 5.6), C.YELLOW, 10.0, 0.04)
    C.strip((-3.85, -59.6, 5.75), (3.85, -59.6, 5.75), C.YELLOW, 10.0, 0.04)
    for z in (0.6, 1.3, 2.0, 2.7, 3.4):
        C.strip((-3.6, -59.0, z), (3.6, -59.0, z), C.MAGENTA, 14.0, 0.008)
    for i, (x, rot, col) in enumerate([(-13.75, 90, C.MAGENTA), (13.75, -90, C.NCYAN)]):
        for j, y in enumerate((-55.0, -43.0)):
            C.glyph_sign((x, y, 5.2), rot, n=4, height=0.5, color=col, strength=10, seed=400 + i * 2 + j, vertical=True, backing=False, frame=False)
    for x, y, col in ((-8, -50, C.MAGENTA), (0, -54, C.NCYAN), (8, -50, C.MAGENTA)):
        segs = []
        for k in range(12):
            if k % 2:
                continue
            a0 = k / 12 * math.tau
            segs.append([Vector((x + math.cos(a0 + t * 0.09) * 1.15, y + math.sin(a0 + t * 0.09) * 1.15, 4.1)) for t in range(6)])
        C.tubes(segs, col, 8.0, 0.012, name="HoloHalo")
    C.holo_panel((0, -59.4, 8.3), 180, (6.0, 2.2), C.NCYAN, C.MAGENTA, 1.6, symbol=None, seed=410)


def clutter():
    A.place("Debris_Pile_Dark", (-9.5, -43.6, 0), 30)
    A.place("Debris_Pile_C", (6.0, -42.6, 0), 200)
    A.place("Rubble_Chunk_S", (-3.0, -45.0, 0), 50)
    A.place("Junction_Box", (-13.6, -52.5, 0), 90)
    A.place("Terminal_Kiosk", (-11.8, -57.0, 0), 35)


def actors():
    lp, kp = (0.7, -50.9, 0), (-1.9, -46.9, 0)
    l = A.load_character("lyra", lp, A.yaw_to(lp, (0, -54), 5), pose=("l_echo", 10))
    k = A.load_character("kael", kp, A.yaw_to(kp, (-5.6, -49.6), 10), pose=("combat_idle", 30))
    A.curl_fingers(k, "Left", 65)
    A.curl_fingers(k, "Right", 65)
    hl, hr = l.bone_world("LeftHand", tail=True), l.bone_world("RightHand", tail=True)
    hand = hl if hl.z > hr.z else hr
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=0.06, location=hand)
    bpy.context.active_object.data.materials.append(A.aether_material("echo_charge", color=A.CYAN, color2=A.VIOLET, strength=14.0, core=True))
    A.light("POINT", hand, 30, (0.45, 0.75, 1.0), size=0.05, name="EchoCharge")
    sp = (-5.6, -49.6, 0)
    st = A.load_robot("stalker", sp, A.yaw_to(sp, kp, 0) + 15, pose={
        "hips": (0, 0, 0), "spine": (22, 0, 0), "chest": (18, 10, 0), "neck": (-10, 0, 0), "head": (-28, -10, 0),
        "clavicle_L": (0, 0, 10), "upperarm_L": (-30, 0, 40), "forearm_L": (-70, 0, 0), "hand_L": (-10, 0, 0),
        "clavicle_R": (0, 0, -10), "upperarm_R": (-50, 0, -35), "forearm_R": (-60, 0, 0),
        "thigh_L": (-80, 0, 12), "shin_L": (110, 0, 0), "foot_L": (-25, 0, 0),
        "thigh_R": (-40, 0, -12), "shin_R": (95, 0, 0), "foot_R": (-50, 0, 0)})
    st.glow(7.0)
    A.light("POINT", (-6.6, -51.5, 3.0), 90, A.VIOLET, size=0.4, name="StalkerRim")
    A.light("POINT", (-4.0, -46.5, 2.2), 30, (0.75, 0.7, 1.0), size=0.3, name="StalkerFill")
    return k, l


def build(quick=False):
    A.reset()
    A.WET = 0.0
    A.EMIT_SCALE = 1.0
    res = (960, 540) if quick else (1920, 1080)
    A.setup_render(res, samples=48 if quick else 128, look="AgX - Medium High Contrast", exposure=1.0, adaptive=0.035)
    bpy.context.scene.cycles.volume_step_rate = 3.0
    A.world_gradient((0, 0, 0), (0, 0, 0), (0, 0, 0), strength=0.0)
    room()
    A.set_emit("emit_strip_violet", 0.9)
    A.set_emit("emit_strip_cyan", 0.9)
    lock_door()
    resonators()
    glyphs()
    clutter()
    cyber()
    k, l = actors()
    # cold work lights high on the ribs (most of the hall is unlit)
    for x, y, e in [(-8, -50, 700), (8, -50, 700), (0, -54.5, 900), (0, -45.5, 500)]:
        A.light("SPOT", (x, y, H - 0.8), e, (0.72, 0.8, 1.0), size=0.15, rot=(0, 0, 0), spot=28, blend=0.5, name="Shaft")
    A.light("AREA", (0, -38.5, 4.0), 260, (0.6, 0.66, 0.9), size=8, rot=(80, 0, 180), name="BackFill")
    cl = (0.9, -37.6, 1.5)
    ct = (0.0, -60.0, 3.7)
    cam = A.camera(cl, ct, lens=22, fstop=7.1, focus=(Vector(cl) - k.rig.location).length)
    mid = (k.rig.location + l.rig.location) / 2 + Vector((0, 0, 1.3))
    A.light("AREA", mid + Vector((4.0, -5.0, 1.5)), 140, C.MAGENTA, size=1.5, target=tuple(mid), name="RimMagenta")
    A.light("AREA", mid + Vector((-4.0, -5.0, 1.5)), 120, C.NCYAN, size=1.5, target=tuple(mid), name="RimCyan")
    A.light("AREA", (2.5, -44.0, 3.0), 60, (0.75, 0.82, 1.0), size=3.0, target=tuple(k.rig.location + Vector((0, 0, 1.3))), name="HeroFill")
    A.fog_box((0, -50, 5), (28, 22, 10), density=0.022, color=(0.86, 0.85, 0.98), anisotropy=0.6, noise=0.6, noise_scale=0.18, name="Haze")
    A.compositor(bloom=0.5, bloom_size=0.75, threshold=0.8, dispersion=0.006, vignette=0.32, saturation=1.18)
    A.screen({"kael": k.rig.location + Vector((0, 0, 1)), "lyra": l.rig.location + Vector((0, 0, 1)), "door": (0, -60.2, 2.5),
              "res_c": (0, -54, 3), "res_l": (-8, -50, 3), "res_r": (8, -50, 3), "stalker": (-5.6, -49.6, 1.2), "glyph": (0, -59.75, 7.2)})
    return cam


def main():
    a = A.args()
    quick = "--quick" in a
    build(quick)
    if quick:
        A.render(os.path.join(A.PREVIEWS, "tests", "vault_quick.png"))
    else:
        A.render(os.path.join(A.PREVIEWS, "loading_vault.png"), os.path.join(A.RES_ART, "Loading", "vault.jpg"))
        A.save_scene("vault_loading")


if __name__ == "__main__":
    main()
