"""Ground-floor storefront modules (wall-mounted, pivot = wall plane at pavement level, front -Y in Blender / +Z in Unity).

Every module is 4.25 m tall and has the same envelope so modules can be lined up along a whole building face:
  * shop body 0.75 m deep (pilasters, bulkhead, mullions, glass at y = -0.70), interior card at y = -0.33 (emissive
    render of a real 3D room, emit_st_interiors) with modelled props in between for parallax;
  * canopy z 3.24..3.50 projecting 1.75 m (it hides the procedural awnings BoxBuildings puts on the same faces);
  * fascia lightbox z 3.52..4.22, 0.42 m proud of the wall (emit_st_signs atlas, invented glyphs only).
Collider: one box over the 0.75 m body (z 0..3.2); canopy and signs are above head height.
"""
import math

import st_layout as LY
from stgeo import K, Meta, bmin, front_card, side_card, card

BODY = 0.75        # shop body depth (front of pilasters)
GLASS = 0.70       # glass plane
BACK = 0.33        # interior card plane
BULK = 0.42        # bulkhead (stall riser) height
HEAD = 2.95        # window head
CAN0, CAN1 = 3.24, 3.50
FAS0, FAS1 = 3.52, 4.22
TOP = 4.25

SHOP_INTERIOR = {"noodle": "noodle", "pharmacy": "pharmacy", "clinic": "clinic", "pawn": "pawn", "capsule": "capsule",
                 "arcade": "arcade", "shuttered": "storeroom", "wall": "kitchen_dark"}


def interior_uv(kind, width):
    """Crop of the 6 m x 3 m interior render for a window `width` x 2.53 m (centred)."""
    r = LY.uv(SHOP_INTERIOR[kind])
    fw = min(1.0, width / 6.0)
    fh = min(1.0, (HEAD - BULK) / 3.0)
    return LY.sub(r, 0.5 - fw / 2, (0.42 / 3.0), 0.5 + fw / 2, (0.42 / 3.0) + fh)


def frame_common(W, M, kind, clad="st_tile_wall", canopy="metal", led="emit_st_led_white", fascia=None, k=0):
    """Pilasters, bulkhead, interior bay (back card + side returns + soffit light), canopy, fascia. Returns inner x range."""
    xi0, xi1 = -W / 2 + 0.24, W / 2 - 0.24
    # pilasters (clad), with a metal cap strip at the top
    for s in (-1, 1):
        x = s * (W / 2 - 0.12)
        p = bmin(x - 0.12, -BODY, 0, x + 0.12, 0, CAN0, clad, bevel=0.012)
        bmin(x - 0.13, -BODY - 0.01, 0, x + 0.13, -BODY + 0.02, 0.12, "metal_dark")            # kick plate
    # interior bay: back card, side returns, floor / display deck, soffit with a downlight strip
    if kind not in ("shuttered", "wall"):
        front_card("emit_st_interiors", xi0, xi1, -BACK, BULK, HEAD, interior_uv(kind, xi1 - xi0))
        bmin(xi0, -GLASS, HEAD, xi1, -BACK, HEAD + 0.05, "black")                                 # soffit
        bmin(xi0 + 0.1, -GLASS + 0.06, HEAD - 0.02, xi1 - 0.1, -GLASS + 0.12, HEAD, led)         # light strip
        for x in (xi0, xi1):
            bmin(x - 0.01, -GLASS, BULK, x + 0.01, -BACK, HEAD, "plastic_dark")
    # canopy (+ fabric awning top for 'awning' styles), LED edge and downlights
    if canopy == "metal" or canopy.startswith("st_awning"):
        bmin(-W / 2, -1.75, CAN0, W / 2, 0, CAN1, "metal_dark", bevel=0.01)
        bmin(-W / 2 + 0.02, -1.74, CAN0 - 0.025, W / 2 - 0.02, -1.70, CAN0, led)
        if K.detail():
            for i in range(max(2, int(W / 1.6))):
                x = -W / 2 + (i + 0.5) * W / max(2, int(W / 1.6))
                K.cyl(0.07, 0.015, 12, at=(x, -1.1, CAN0 - 0.015), mat="emit_st_led_white")
    if canopy.startswith("st_awning"):
        # sloped fabric awning on top of the canopy frame with a scalloped-less straight valance
        hi, lo = TOP - 0.15, CAN1 + 0.02
        L = math.hypot(1.85, hi - lo)
        a = K.box(W - 0.04, L, 0.03, at=(0, -0.925, (hi + lo) / 2), mat=canopy, name="awning")
        a.rot_about((0, -0.925, (hi + lo) / 2), x=-math.degrees(math.atan2(hi - lo, 1.85)))
        bmin(-W / 2 + 0.02, -1.86, lo - 0.28, W / 2 - 0.02, -1.83, lo + 0.02, canopy)            # valance
        for s in (-1, 1):
            K.tube([(s * (W / 2 - 0.05), -0.02, hi), (s * (W / 2 - 0.05), -1.82, lo)], 0.012, 6, mat="metal_dark")
    # fascia lightbox standing on the canopy's front edge (reads from the pavement and across the street)
    if fascia:
        fw = W - 0.3
        y0, y1 = -1.76, -1.52
        bmin(-fw / 2, y0, CAN1, fw / 2, y1, FAS1, "metal_dark", bevel=0.008)
        uvr = LY.uv(fascia)
        frac = min(1.0, (fw / (FAS1 - CAN1)) / 8.0)
        if frac < 1.0:
            uvr = LY.sub(uvr, 0, 0, frac, 1)
        front_card("emit_st_signs", -fw / 2 + 0.02, fw / 2 - 0.02, y0 - 0.005, CAN1 + 0.03, FAS1 - 0.03, uvr)
        for s in (-1, 1):
            bmin(s * fw / 2 - 0.01, y0 - 0.01, CAN1, s * fw / 2 + 0.01, y1, FAS1, "metal_bare")
        # a slimmer back panel on the wall above the canopy (wall-mounted name strip)
        bmin(-fw / 2 + 0.4, -0.16, CAN1 + 0.1, fw / 2 - 0.4, -0.04, FAS1 - 0.1, "metal_dark")
    M.col((0, -BODY / 2, 1.6), (W, BODY, 3.2))
    return xi0, xi1


def mullions(xi0, xi1, n, z0=BULK, z1=HEAD, mat="metal_dark", glass=True, transom=None):
    bmin(xi0, -BODY, z0 - 0.05, xi1, -GLASS + 0.02, z0, mat)                                 # sill
    bmin(xi0, -BODY, z1, xi1, -GLASS + 0.02, z1 + 0.06, mat)                                 # head
    for i in range(n + 1):
        x = xi0 + (xi1 - xi0) * i / n
        bmin(x - 0.03, -BODY, z0, x + 0.03, -GLASS + 0.02, z1, mat)
    if transom:
        bmin(xi0, -BODY, transom - 0.025, xi1, -GLASS + 0.02, transom + 0.025, mat)
    if glass:
        K.plane(xi1 - xi0, z1 - z0, at=(0, 0, 0), mat="glass").rot(x=90).move((xi0 + xi1) / 2, -GLASS, (z0 + z1) / 2)


def window_display(xi0, xi1, rng_seed=1, tiers=2, z0=BULK, colours=("paint_glossy_white", "car_paint_teal", "car_paint_yellow", "paint_glossy_red", "car_paint_white")):
    """Modelled window display between the glass and the interior card (real parallax): a two-tier stand with small
    product boxes / bottles silhouetted against the lit interior."""
    import random as _r
    r = _r.Random(rng_seed)
    y0, y1 = -GLASS + 0.08, -BACK - 0.05
    for t in range(tiers):
        z = z0 + 0.02 + t * 0.42
        bmin(xi0 + 0.1, y0, z, xi1 - 0.1, y1, z + 0.025, "metal_bare")
        if not K.detail():
            continue
        x = xi0 + 0.15
        while x < xi1 - 0.2:
            w = r.uniform(0.06, 0.16)
            h = r.uniform(0.1, 0.3)
            if r.random() < 0.75:
                if r.random() < 0.6:
                    bmin(x, y0 + 0.03, z + 0.025, x + w, y0 + 0.03 + r.uniform(0.05, 0.12), z + 0.025 + h, r.choice(colours))
                else:
                    K.cyl(w * 0.4, h, 8, at=(x + w / 2, (y0 + y1) / 2, z + 0.025), mat=r.choice(colours))
            x += w + r.uniform(0.02, 0.1)


def bulkhead(xi0, xi1, mat="st_tile_wall"):
    bmin(xi0, -BODY + 0.02, 0, xi1, -BACK, BULK - 0.05, mat)
    bmin(xi0 - 0.01, -BODY, BULK - 0.06, xi1 + 0.01, -BACK, BULK - 0.04, "metal_bare")


def shutter_box(xi0, xi1, down=0.0):
    """Roll-shutter housing under the canopy; `down` = fraction of the opening covered (from the head)."""
    bmin(xi0, -BODY - 0.02, HEAD + 0.06, xi1, -BODY + 0.24, CAN0, "metal_dark", bevel=0.01)
    if down > 0:
        z0 = HEAD - (HEAD - 0.02) * down
        p = bmin(xi0 + 0.02, -BODY - 0.01, z0, xi1 - 0.02, -BODY + 0.02, HEAD + 0.06, "st_shutter")
        bmin(xi0 + 0.02, -BODY - 0.03, z0, xi1 - 0.02, -BODY + 0.03, z0 + 0.05, "metal_bare")   # bottom bar
        for x in (xi0 + 0.01, xi1 - 0.01):
            bmin(x - 0.02, -BODY - 0.03, 0, x + 0.02, -BODY + 0.03, HEAD + 0.06, "metal_bare")   # guide rails


def blade(x, z0, h, name, depth=0.75):
    """Double-sided vertical blade sign perpendicular to the wall (atlas blade_*), with brackets."""
    w = h / 3.0
    y0, y1 = -0.12, -0.12 - w
    bmin(x - 0.05, y1 - 0.02, z0 - 0.02, x + 0.05, y0 + 0.02, z0 + h + 0.02, "metal_dark", bevel=0.006)
    r = LY.uv(name)
    side_card("emit_st_signs", x + 0.052, y0, y1, z0, z0 + h, r, facing=1)
    side_card("emit_st_signs", x - 0.052, y0, y1, z0, z0 + h, r, facing=-1)
    for z in (z0 + 0.1, z0 + h - 0.1):
        bmin(x - 0.02, y0, z - 0.02, x + 0.02, 0, z + 0.02, "metal_bare")


def lantern(x, y, z, r=0.17, h=0.42, mat="emit_st_lantern_red"):
    prof = [(r * 0.45, 0), (r * 0.85, h * 0.12), (r, h * 0.5), (r * 0.85, h * 0.88), (r * 0.45, h)]
    K.lathe(prof, 14, at=(x, y, z), mat=mat)
    K.cyl(r * 0.5, 0.04, 10, at=(x, y, z - 0.03), mat="black")
    K.cyl(r * 0.5, 0.04, 10, at=(x, y, z + h - 0.01), mat="black")
    if K.detail():
        for i in range(5):
            zz = z + h * (0.2 + 0.15 * i)
            rr = max(pp for pp, q in prof if abs(q - (zz - z)) < h * 0.4) * 1.01
            K.torus(rr, 0.004, n_major=14, n_minor=4, mat="black").move(x, y, zz)
        K.tube([(x, y, z + h + 0.03), (x, y, CAN0 - 0.02)], 0.006, 4, mat="black")
        K.tube([(x, y, z - 0.03), (x, y, z - 0.25)], 0.012, 4, mat="emit_st_lantern_red")


# ============================================================================================== shop types
def shop(kind="noodle", W=6.0, variant=0):
    M = Meta()
    if kind == "noodle":
        xi0, xi1 = frame_common(W, M, kind, clad="wood" if variant else "st_tile_wall", canopy="st_awning_red", fascia=f"fascia_noodle_{variant}")
        # open counter: wood top proud of the façade, tiled front, stools tucked under
        bmin(xi0, -BODY + 0.02, 0, xi1, -BACK, 1.0, "st_tile_wall")
        bmin(xi0 - 0.02, -0.98, 1.0, xi1 + 0.02, -BACK, 1.07, "wood", bevel=0.01)
        for i in range(int((xi1 - xi0) / 1.1)):
            x = xi0 + 0.55 + i * 1.1
            K.cyl(0.17, 0.05, 14, at=(x, -1.22, 0.72), mat="st_awning_red")
            K.cyl(0.025, 0.72, 8, at=(x, -1.22, 0.0), mat="metal_bare")
            K.cyl(0.14, 0.02, 10, at=(x, -1.22, 0.0), mat="metal_dark")
            if K.detail():
                K.torus(0.12, 0.008, n_major=12, n_minor=4, mat="metal_bare").move(x, -1.22, 0.3)
        if K.detail():
            for i in range(5):  # bowls / chopstick holders on the counter
                x = xi0 + 0.4 + i * (xi1 - xi0 - 0.8) / 4
                K.lathe([(0.05, 0), (0.1, 0.05), (0.11, 0.08)], 12, at=(x, -0.7, 1.07), mat="paint_glossy_white", close_top=False)
        # noren: cloth strips under the head, slits between them
        n = 5
        cw = (xi1 - xi0) / n
        for i in range(n):
            r = LY.sub(LY.uv("cloth_0" if variant == 0 else "cloth_1"), i / n + 0.004, 0, (i + 1) / n - 0.004, 1)
            x0 = xi0 + i * cw + 0.015
            front_card("emit_st_signs", x0, x0 + cw - 0.03, -GLASS - 0.02, 2.15, HEAD, r, two_sided=True)
        bmin(xi0, -GLASS - 0.04, HEAD - 0.03, xi1, -GLASS, HEAD + 0.02, "wood")
        for x in (-W / 2 + 0.6, W / 2 - 0.6):
            lantern(x, -1.45, 2.55)
            M.light((x, -1.45, 2.75), "#ff5a2a", 4.0, 1.2)
        side_card("emit_st_signs", -W / 2 - 0.005, -0.25, -0.65, 1.3, 1.7, LY.uv("square_0"), facing=-1)
        M.vent((0, -0.6, 1.2))
        M.light((0, -1.2, 2.2), "#ffb46a", 6.0, 1.6)
    elif kind == "pharmacy":
        xi0, xi1 = frame_common(W, M, kind, clad="paint_glossy_white", led="emit_st_led_white", fascia=f"fascia_pharmacy_{variant}")
        bulkhead(xi0, xi1, "paint_glossy_white")
        dw = 1.05
        mullions(xi0 + dw, xi1, 2, transom=2.45)
        # glass door with push bar
        bmin(xi0, -BODY, 0, xi0 + 0.05, -GLASS + 0.02, HEAD, "metal_dark")
        bmin(xi0 + dw - 0.05, -BODY, 0, xi0 + dw, -GLASS + 0.02, HEAD, "metal_dark")
        K.plane(dw - 0.1, HEAD - 0.05, mat="glass").rot(x=90).move(xi0 + dw / 2, -GLASS, HEAD / 2)
        bmin(xi0 + 0.15, -BODY - 0.05, 1.0, xi0 + dw - 0.15, -BODY - 0.02, 1.04, "metal_bare")
        bmin(xi0, -BODY + 0.05, 0, xi0 + dw, -BACK, 0.02, "st_tile_wall")
        front_card("emit_st_signs", xi0 + dw + 0.3, xi0 + dw + 0.85, -GLASS + 0.01, 1.7, 2.25, LY.uv("square_10"))
        window_display(xi0 + dw, xi1, rng_seed=3 + variant)
        blade(W / 2 - 0.12, 3.6, 1.5, f"blade_{1 if variant == 0 else 7}")
        M.light((0, -1.0, 2.4), "#e8fff2", 6.0, 1.8)
    elif kind == "clinic":
        xi0, xi1 = frame_common(W, M, kind, clad="metal_dark", led="emit_st_led_cyan", canopy="metal", fascia=f"fascia_clinic_{variant}")
        bulkhead(xi0, xi1, "carbon_panel")
        mullions(xi0, xi1, 3, transom=1.9)
        # frosted privacy band: dark smoked panel behind the lower glass
        bmin(xi0 + 0.05, -GLASS + 0.04, BULK, xi1 - 0.05, -GLASS + 0.06, 1.85, "glass_dark")
        # recliner silhouette behind the privacy band, robotic arm above it
        bmin(-0.8, -0.5, 1.2, 0.8, -0.4, 1.45, "paint_glossy_white", bevel=0.02)
        K.beam((0.6, -0.45, 2.8), (0.2, -0.45, 2.05), 0.06, mat="chrome_scratched")
        K.cyl(0.04, 0.12, 8, at=(0.2, -0.45, 1.93), mat="emit_st_led_cyan")
        for x in (-W / 2 + 0.02, W / 2 - 0.02):
            bmin(x - 0.015, -BODY - 0.02, 0.1, x + 0.015, -BODY + 0.01, CAN0 - 0.05, "emit_st_led_cyan")
        K.plane(1.4, 0.9, mat="holo_cyan").rot(x=90).move(xi1 - 1.2, -0.5, 2.3)
        blade(-W / 2 + 0.12, 3.6, 1.5, f"blade_{2 if variant == 0 else 14}")
        M.light((0, -1.0, 2.6), "#5fe8ff", 6.0, 1.5)
    elif kind == "pawn":
        xi0, xi1 = frame_common(W, M, kind, clad="metal_painted", canopy="metal", fascia=f"fascia_pawn_{variant}", led="emit_st_led_amber")
        bulkhead(xi0, xi1, "metal_rusted")
        mullions(xi0, xi1, 2)
        window_display(xi0, xi1, rng_seed=9 + variant, tiers=2, colours=("black", "plastic_dark", "metal_bare", "screen_ad_a", "screen_ad_c"))
        shutter_box(xi0, xi1, down=0.38)
        # security grille over the lower glass
        for i in range(int((xi1 - xi0) / 0.12)):
            x = xi0 + 0.06 + i * 0.12
            K.cyl(0.008, 1.5, 6, at=(x, -BODY - 0.02, BULK), mat="metal_dark")
        for z in (BULK + 0.05, BULK + 0.75, BULK + 1.45):
            bmin(xi0, -BODY - 0.035, z, xi1, -BODY - 0.005, z + 0.03, "metal_dark")
        front_card("emit_st_signs", xi1 - 0.75, xi1 - 0.15, -GLASS + 0.01, 1.1, 1.7, LY.uv("square_3"))
        side_card("emit_st_signs", W / 2 + 0.005, -0.3, -0.7, 1.4, 1.8, LY.uv("square_6"), facing=1)
        M.light((0, -1.0, 2.6), "#ffd890", 5.0, 1.2)
    elif kind == "capsule":
        xi0, xi1 = frame_common(W, M, kind, clad="paint_glossy_white", canopy="metal", fascia=f"fascia_capsule_{variant}", led="emit_st_led_white")
        bulkhead(xi0, xi1 - 2.2, "st_tile_wall")
        bulkhead(xi1 - 0.25, xi1, "st_tile_wall")
        mullions(xi0, xi1 - 2.2, 1)
        # recessed sliding-door entrance (two leaves) on the right with a lit threshold
        d0, d1 = xi1 - 2.2, xi1 - 0.25
        bmin(d0, -BODY, 0, d0 + 0.06, -BACK, HEAD, "metal_dark")
        bmin(d1 - 0.06, -BODY, 0, d1, -BACK, HEAD, "metal_dark")
        for k2 in range(2):
            x0 = d0 + 0.06 + k2 * (d1 - d0 - 0.12) / 2
            K.plane((d1 - d0 - 0.12) / 2 - 0.02, HEAD - 0.1, mat="glass").rot(x=90).move(x0 + (d1 - d0 - 0.12) / 4, -0.5 - k2 * 0.04, (HEAD - 0.1) / 2)
            bmin(x0 + 0.01, -0.53 - k2 * 0.04, 0, x0 + 0.04, -0.49 - k2 * 0.04, HEAD - 0.1, "metal_bare")
        bmin(d0, -BODY, 0, d1, -BACK, 0.02, "emit_st_led_white")
        blade(-W / 2 + 0.12, 3.55, 1.8, f"blade_{4 if variant == 0 else 10}")
        M.light((xi1 - 1.2, -1.0, 2.6), "#dfe9ff", 5.0, 1.5)
    elif kind == "arcade":
        xi0, xi1 = frame_common(W, M, kind, clad="carbon_panel", canopy="metal", fascia=f"fascia_arcade_{variant}", led="emit_st_led_magenta")
        bmin(xi0, -BODY + 0.02, 0, xi1, -BACK, 0.12, "black")
        shutter_box(xi0, xi1, down=0.0)
        # neon tube frame around the open front + rubber floor mat
        for (a, b) in (((xi0 + 0.05, -BODY - 0.03, 0.2), (xi0 + 0.05, -BODY - 0.03, HEAD - 0.05)),
                       ((xi1 - 0.05, -BODY - 0.03, 0.2), (xi1 - 0.05, -BODY - 0.03, HEAD - 0.05)),
                       ((xi0 + 0.05, -BODY - 0.03, HEAD - 0.05), (xi1 - 0.05, -BODY - 0.03, HEAD - 0.05))):
            K.tube([a, b], 0.018, 8, mat="emit_neon_magenta" if variant == 0 else "emit_neon_violet")
        bmin(xi0 + 0.3, -1.6, 0, xi1 - 0.3, -BODY, 0.015, "rubber")
        if K.detail():
            # two cabinets at the mouth (their screens face the street)
            for x in (xi0 + 0.55, xi1 - 0.55):
                bmin(x - 0.35, -GLASS + 0.05, 0.12, x + 0.35, -BACK, 1.85, "paint_glossy_dark")
                front_card("emit_st_signs", x - 0.28, x + 0.28, -GLASS + 0.045, 1.05, 1.5, LY.uv("square_1" if x < 0 else "square_9"))
        blade(W / 2 - 0.12, 3.6, 1.5, f"blade_{5 if variant == 0 else 11}")
        M.light((0, -1.0, 2.0), "#ff4fd8", 6.0, 1.6)
    elif kind == "shuttered":
        xi0, xi1 = frame_common(W, M, kind, clad="concrete_dark", canopy="metal", fascia=f"fascia_dead_{variant}", led="black")
        bmin(xi0, -BODY + 0.05, 0, xi1, -BACK, HEAD, "black")
        shutter_box(xi0, xi1, down=1.0)
        if K.detail():
            K.box(0.12, 0.05, 0.08, at=(0, -BODY - 0.04, 0.1), mat="metal_bare")      # padlock hasp
    else:  # wall: plain bay with a steel service door, meter box and conduit
        xi0, xi1 = frame_common(W, M, kind, clad="concrete", canopy="metal", fascia=None, led="emit_st_led_amber")
        bmin(xi0, -BODY + 0.05, 0, xi1, -BACK, HEAD + 0.06, "concrete_dark")
        bmin(-0.5, -BODY + 0.03, 0, 0.5, -BODY + 0.06, 2.2, "metal_painted", bevel=0.005)
        bmin(-0.56, -BODY + 0.02, 0, 0.56, -BODY + 0.05, 2.26, "metal_dark")
        bmin(0.32, -BODY + 0.0, 1.0, 0.4, -BODY + 0.03, 1.05, "metal_bare")
        bmin(xi1 - 0.45, -BODY - 0.1, 1.4, xi1 - 0.1, -BODY + 0.05, 1.9, "metal_painted_white", bevel=0.01)
        K.cyl(0.03, HEAD, 8, at=(xi1 - 0.2, -BODY - 0.05, 0), mat="metal_rusted")
        K.cyl(0.08, 0.04, 10, at=(0, -BODY - 0.02, 2.5), mat="emit_st_led_amber")
    return M.done()


def _reg(name, kind, W, variant, notes):
    ASSETS[name] = dict(fn=shop, kw={"kind": kind, "W": W, "variant": variant}, cat="storefront", zones=["plaza"], pivot="wall-base",
                        notes=notes + f" Width {W} m, body 0.75 m, canopy 1.75 m, height 4.25 m; pivot at the wall plane / pavement.")


ASSETS = {}
_reg("St_Shop_Noodle_A", "noodle", 6.0, 0, "Noodle bar: open tiled counter with stools, noren cloths, red paper lanterns, red awning, warm kitchen interior.")
_reg("St_Shop_Noodle_B", "noodle", 6.0, 1, "Noodle bar variant (wood cladding, orange neon fascia).")
_reg("St_Shop_Pharmacy_A", "pharmacy", 4.0, 0, "Pharmacy: white gloss front, glass door, cross-pictogram blade sign, bright shelving interior.")
_reg("St_Shop_Pharmacy_B", "pharmacy", 4.0, 1, "Pharmacy variant (neon fascia).")
_reg("St_Shop_Clinic_A", "clinic", 6.0, 0, "Cyberware clinic: dark metal, smoked privacy band, cyan LED edges, holo panel, surgical interior.")
_reg("St_Shop_Clinic_B", "clinic", 6.0, 1, "Cyberware clinic variant (blue lightbox).")
_reg("St_Shop_Pawn_A", "pawn", 4.0, 0, "Pawn / electronics: half-down roll shutter, security grille, cluttered lit interior with screens.")
_reg("St_Shop_Pawn_B", "pawn", 4.0, 1, "Pawn / electronics variant (amber neon fascia).")
_reg("St_Shop_Capsule_A", "capsule", 4.0, 0, "Capsule hotel entrance: recessed sliding glass doors, lit threshold, capsule-corridor interior, blade sign.")
_reg("St_Shop_Capsule_B", "capsule", 4.0, 1, "Capsule hotel variant (violet neon).")
_reg("St_Shop_Arcade_A", "arcade", 6.0, 0, "Arcade: open front with magenta neon frame, cabinets at the mouth, glowing cabinet hall interior.")
_reg("St_Shop_Arcade_B", "arcade", 6.0, 1, "Arcade variant (violet neon, lightbox marquee).")
_reg("St_Shop_Shuttered_A", "shuttered", 4.0, 0, "Closed shop: full roll shutter (graffiti decals are added in game), dead fascia.")
_reg("St_Shop_Shuttered_B", "shuttered", 4.0, 1, "Closed shop variant.")
_reg("St_Shop_Wall_2m", "wall", 2.0, 0, "Filler bay: concrete with a steel service door, meter box, conduit, amber lamp; canopy continues.")
