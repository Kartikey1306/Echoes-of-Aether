"""Vehicles: compact car (+ wrecked), transit bus, metro train car. Long axis = Blender Y, FRONT at -Y
(Unity +Z), pivot at ground centre."""
import math
import random

from mathutils import Matrix, Vector

import envkit as K
from envkit import box, cyl, lathe, loft, rounded_section, boolean, torus, tube, beam, faces_where, detail


def _vnoise(seed):
    rnd = random.Random(seed)
    ph = [rnd.uniform(0, 100) for _ in range(9)]

    def f(x, y, z):
        return (math.sin(x * 3.1 + ph[0]) * math.sin(y * 2.3 + ph[1]) * math.sin(z * 4.1 + ph[2])
                + 0.5 * math.sin(x * 7.3 + ph[3]) * math.sin(y * 6.1 + ph[4]) * math.sin(z * 5.7 + ph[5]))
    return f


def wheel(at, side, r=0.335, w=0.21, rim_mat="metal_dark"):
    """Tyre + rim + spokes; axle along X, outer face toward side (+1 => +X)."""
    hw = w / 2
    parts = []
    parts.append(lathe([(r - 0.11, -hw), (r - 0.035, -hw - 0.004), (r - 0.008, -hw + 0.02), (r, -hw + 0.05), (r, hw - 0.05),
                        (r - 0.008, hw - 0.02), (r - 0.035, hw + 0.004), (r - 0.11, hw)], 24, mat="rubber",
                       close_bottom=False, close_top=False))
    ri = r - 0.11
    parts.append(lathe([(ri, hw), (ri - 0.012, hw - 0.004), (ri - 0.03, hw - 0.04), (0.075, hw - 0.055), (0.07, hw - 0.03),
                        (0.0, hw - 0.025)], 20, mat=rim_mat, close_bottom=False, close_top=False))
    parts.append(cyl(ri, 0.02, 20, at=(0, 0, -hw + 0.01), mat="black"))
    n = 5 if detail() else 0
    for i in range(n):
        a = i * 360 / n
        sp = box(0.045, ri - 0.08, 0.025, at=(0, (ri + 0.07) / 2, hw - 0.035), mat=rim_mat, bevel=0.006)
        sp.rot(z=a)
        parts.append(sp)
    if detail():
        parts.append(cyl(0.045, 0.02, 10, at=(0, 0, hw - 0.03), mat="metal_bare"))
        parts.append(cyl(ri - 0.04, 0.025, 20, at=(0, 0, -0.03), mat="metal_rusted"))
    for p in parts:
        p.rot(y=90 * side).move(*at)
    return parts


# ============================================================================================== car
CAR_L, CAR_W = 4.3, 1.84
AXLE_F, AXLE_R, WR, TRACK = -1.33, 1.36, 0.335, 0.78

# lower body stations: (y, half-width bottom, half-width top, z bottom, z top)
BODY = [
    (-2.15, 0.76, 0.70, 0.31, 0.60), (-2.11, 0.84, 0.78, 0.27, 0.635), (-2.03, 0.88, 0.83, 0.245, 0.665),
    (-1.88, 0.905, 0.86, 0.235, 0.70), (-1.62, 0.915, 0.875, 0.22, 0.76), (-1.30, 0.92, 0.88, 0.205, 0.82),
    (-1.00, 0.92, 0.885, 0.195, 0.875), (-0.60, 0.92, 0.885, 0.19, 0.915), (-0.20, 0.92, 0.885, 0.19, 0.925),
    (0.20, 0.92, 0.885, 0.19, 0.93), (0.60, 0.92, 0.885, 0.19, 0.93), (1.00, 0.92, 0.885, 0.195, 0.93),
    (1.36, 0.92, 0.88, 0.205, 0.925), (1.66, 0.915, 0.87, 0.22, 0.915), (1.90, 0.90, 0.85, 0.235, 0.895),
    (2.06, 0.87, 0.82, 0.25, 0.87), (2.15, 0.82, 0.77, 0.27, 0.84), (2.19, 0.74, 0.70, 0.30, 0.80),
]
# cabin stations: (y, roof z, roof half-width); cabin bottom z=0.9, bottom half-width 0.79
CABIN = [
    (-1.02, 0.95, 0.70), (-0.88, 1.05, 0.68), (-0.70, 1.17, 0.665), (-0.50, 1.30, 0.655), (-0.30, 1.41, 0.645),
    (-0.15, 1.44, 0.64), (0.25, 1.45, 0.64), (0.37, 1.45, 0.64), (0.75, 1.44, 0.64), (0.95, 1.40, 0.645),
    (1.15, 1.30, 0.655), (1.32, 1.17, 0.67), (1.48, 1.05, 0.69), (1.62, 0.95, 0.71),
]
WINDSCREEN = range(0, 4)
SIDE_FRONT = range(1, 6)
SIDE_REAR = range(7, 10)
REAR_GLASS = range(9, 13)


def _car_body(paint, glass, wreck=False):
    secs = []
    for (y, hb, ht, zb, zt) in BODY:
        pts, idx = rounded_section(hb, ht, zb, zt, 0.07, 0.13, n_flat=2, n_arc=3, n_side=3, bulge=0.03, y=y)
        secs.append(pts)
    body = loft(secs, mat=paint, name="body")
    # wheel wells
    for yc in (AXLE_F, AXLE_R):
        for s in (-1, 1):
            c = cyl(0.405, 0.6, 24, at=(s * 0.92, yc, 0.34), mat="black", center=True, axis="X")
            boolean(body, c)
    # cabin
    csecs, cidx = [], None
    for (y, zt, ht) in CABIN:
        pts, cidx = rounded_section(0.79, ht, 0.9, zt, 0.0, 0.1, n_flat=2, n_arc=3, n_side=4, bulge=0.0, y=y)
        csecs.append(pts)
    sr0, sr1 = cidx["side_r"]
    sl0, sl1 = cidx["side_l"]
    t0, t1 = cidx["top"]

    def fm(i, k):
        if t0 <= k < t1 and (i in WINDSCREEN or i in REAR_GLASS):
            if wreck and i in WINDSCREEN and k < (t0 + t1) // 2 and i < 3:
                return "black"
            return glass
        side_win = i in SIDE_FRONT or i in SIDE_REAR
        if side_win and sr0 + 1 <= k < sr1:
            return glass
        if side_win and sl0 <= k < sl1 - 1:
            if wreck and i in SIDE_FRONT and i > 2:
                return "black"
            return glass
        return None

    cab = loft(csecs, mat=paint, face_mat=fm, name="cabin")
    # window seals: inset glass regions slightly
    if detail():
        g = [f for f in cab.bm.faces if cab.matnames[f[cab.mats]] in (glass, "black")]
        import bmesh
        res = bmesh.ops.inset_region(cab.bm, faces=g, thickness=0.012, depth=-0.008, use_even_offset=True)
        ri = cab.slot("rubber")
        for f in res["faces"]:
            f[cab.mats] = ri
    return body, cab


def car(paint="car_paint_grey", wreck=False, seed=3):
    glass = "glass_dark"
    body, cab = _car_body(paint, glass, wreck)
    parts_body = [body, cab]
    # bumpers, skirts, cladding
    fb = box(1.72, 0.22, 0.13, at=(0, -2.03, 0.29), mat="plastic_dark", bevel=0.035, bseg=2)
    rb = box(1.72, 0.2, 0.13, at=(0, 2.09, 0.31), mat="plastic_dark", bevel=0.035, bseg=2)
    parts_body += [fb, rb]
    for s in (-1, 1):
        parts_body.append(box(0.05, 1.86, 0.1, at=(s * 0.905, 0.01, 0.255), mat="plastic_dark", bevel=0.018))
        for yc in (AXLE_F, AXLE_R):
            t = torus(0.425, 0.028, arc=180, n_major=14, n_minor=6, mat="plastic_dark", start=0)
            t.rot(x=90).rot(z=90).move(s * 0.905, yc, 0.34)
            parts_body.append(t)
    # lights
    lit_h = "black" if wreck else "car_headlight"
    lit_t = "black" if wreck else "car_taillight"
    parts_body.append(box(1.25, 0.03, 0.04, at=(0, -2.152, 0.545), mat=lit_h, bevel=0.01))
    for s in (-1, 1):
        h = box(0.34, 0.06, 0.07, at=(0, 0, 0), mat=lit_h, bevel=0.015)
        h.rot(z=-s * 14).move(s * 0.6, -2.085, 0.58)
        parts_body.append(h)
        t = box(0.36, 0.05, 0.08, at=(0, 0, 0), mat=lit_t, bevel=0.015)
        t.rot(z=s * 14).move(s * 0.6, 2.15, 0.76)
        parts_body.append(t)
    parts_body.append(box(1.1, 0.03, 0.035, at=(0, 2.185, 0.76), mat=lit_t, bevel=0.008))
    parts_body.append(box(0.72, 0.04, 0.12, at=(0, -2.14, 0.4), mat="plastic_dark", bevel=0.02))
    if detail():
        for s in (-1, 1):
            m = box(0.17, 0.09, 0.1, at=(0, 0, 0), mat=paint, bevel=0.025, bseg=2)
            m.move(s * 0.93, -0.86, 1.0)
            parts_body.append(m)
            parts_body.append(box(0.06, 0.04, 0.03, at=(s * 0.84, -0.86, 0.97), mat="plastic_dark"))
            for y in (-0.3, 0.62):
                parts_body.append(box(0.025, 0.16, 0.025, at=(s * 0.93, y, 0.84), mat="plastic_dark", bevel=0.006))
        parts_body.append(box(0.36, 0.015, 0.11, at=(0, 2.20, 0.52), mat="metal_painted_white"))
        parts_body.append(box(0.36, 0.015, 0.11, at=(0, -2.18, 0.31), mat="metal_painted_white"))
    wheels = []
    skip = set()
    if wreck:
        skip = {(AXLE_F, -1)}
    for yc in (AXLE_F, AXLE_R):
        for s in (-1, 1):
            if (yc, s) in skip:
                # exposed brake disc / hub
                parts_body.append(cyl(0.16, 0.05, 16, at=(s * 0.7, yc, 0.34), mat="metal_rusted", center=True, axis="X"))
                continue
            wheels += wheel((s * TRACK, yc, WR), s)
    if wreck:
        nz = _vnoise(seed)
        body_parts = [body, cab, fb]

        def crumple(co):
            x, y, z = co
            if y < -1.45:
                t = (-1.45 - y) / 0.75
                y += 0.32 * t * t + 0.04 * nz(x, y, z)
                z += 0.05 * math.sin(x * 6) * t + 0.03 * nz(y, z, x) * t
                x *= 1.0 - 0.04 * t
            if z > 1.3:
                z -= 0.07 * max(0.0, 1 - ((y - 0.2) / 0.7) ** 2 - (x / 0.6) ** 2)
            return (x, y, z)
        for p in body_parts:
            p.displace(crumple)
        fb.move(0, 0, -0.08).rot_about((0, -2.0, 0.3), x=8)
        # rest on 3 wheels + the hub: rotate about the rear-left / front-right contact diagonal
        a = Vector((-TRACK, AXLE_R, 0.0))
        b = Vector((TRACK, AXLE_F, 0.0))
        axis = (b - a).normalized()
        R = Matrix.Translation(a) @ Matrix.Rotation(math.radians(-4.2), 4, axis) @ Matrix.Translation(-a)
        for p in list(K._parts):
            p.xform(R)
        K.ground()
        # fallen wheel trim / debris
        if detail():
            rnd = random.Random(seed)
            for i in range(3):
                r = K.rock((rnd.uniform(0.05, 0.12), rnd.uniform(0.05, 0.1), 0.02), seed + i, cuts=6, mat=paint)
                r.move(rnd.uniform(-1.2, -0.6), rnd.uniform(-2.6, -2.2), 0.01)
    return {"colliders": [K.collider_box((0, 0, 0.75), (CAR_W, CAR_L, 1.3))],
            "lights": {"head": K.to_unity_vec((0, -2.16, 0.56)), "tail": K.to_unity_vec((0, 2.19, 0.77))}}


ASSETS = {
    "Car_Sedan": dict(fn=car, cat="vehicles", zones=["plaza"],
                      notes="Compact ground car 4.3 m. Front = +Z. Paint slot car_paint_grey (swap: car_paint_dark/red/white). "
                            "car_headlight / car_taillight have emission 0 by default; raise emissionIntensity to switch lights on."),
    "Car_Sedan_Red": dict(fn=car, kw={"paint": "car_paint_red"}, cat="vehicles", zones=["plaza"], notes="Red paint variant."),
    "Car_Sedan_Wrecked": dict(fn=car, kw={"paint": "car_paint_dark", "wreck": True}, cat="vehicles", zones=["plaza"],
                              notes="Crashed: crumpled front, dented roof, smashed glass, front-left wheel missing (rests on the hub), dead lights."),
}


# ============================================================================================== bus
def bus(paint="metal_painted", L=11.0, W=2.55, H=3.05, wreck=True, seed=8):
    """Transit bus: low-floor body, window band both sides, doors on the right (+X) side, roof pods."""
    rnd = random.Random(seed)
    y0, y1 = -L / 2, L / 2
    ys = [y0, y0 + 0.08, y0 + 0.3, y0 + 0.8] + [y0 + 0.8 + i * (L - 1.6) / 8 for i in range(1, 8)] + [y1 - 0.8, y1 - 0.3, y1 - 0.08, y1]
    secs, idx = [], None
    for y in ys:
        e = min(y - y0, y1 - y)
        k = min(1.0, e / 0.3)
        hw = W / 2 * (0.94 + 0.06 * k)
        zb = 0.32 + 0.06 * (1 - k)
        zt = H - 0.08 * (1 - k)
        pts, idx = rounded_section(hw, hw * 0.97, zb, zt, 0.08, 0.28, n_flat=2, n_arc=3, n_side=6, bulge=0.0, y=y)
        secs.append(pts)
    sr0, sr1 = idx["side_r"]
    sl0, sl1 = idx["side_l"]
    t0, t1 = idx["top"]
    door_bays = {3, 8}  # station-pair indices with doors on the right side

    def fm(i, k):
        if i in (0, 1, 2) and (sr1 - 1 <= k < t1 or sl0 <= k <= sl0 + 1 or k in range(idx["arc_tr"][0], idx["arc_tl"][1])):
            pass
        front = i <= 1
        rear = i >= len(ys) - 3
        side_band_r = sr0 + 3 <= k < sr1
        side_band_l = sl0 <= k < sl1 - 3
        if front and (side_band_r or side_band_l or idx["arc_tr"][0] <= k < idx["arc_tl"][1]):
            return None
        if 2 <= i < len(ys) - 3:
            if i in door_bays and sl0 <= k < sl1 - 1:
                return "glass_dark"
            if side_band_r or side_band_l:
                return "glass_dark"
        return None

    body = loft(secs, mat=paint, face_mat=fm, name="bus")
    # windscreen / rear window: cap faces are triangulated; add separate glass panels instead
    ws = box(W * 0.88, 0.04, 1.45, mat="glass_dark", bevel=0.05)
    ws.rot(x=-6).move(0, y0 + 0.02, 1.95)
    rw = box(W * 0.8, 0.04, 0.9, mat="glass_dark", bevel=0.04)
    rw.move(0, y1 - 0.02, 2.2)
    # wheel arches + wheels (2 axles, rear dual)
    for yc in (y0 + 2.4, y1 - 3.0):
        for s in (-1, 1):
            c = cyl(0.56, 0.7, 24, at=(s * W / 2, yc, 0.5), mat="black", center=True, axis="X")
            boolean(body, c)
            if not (wreck and yc < 0 and s < 0):
                wheel((s * (W / 2 - 0.2), yc, 0.5), s, r=0.5, w=0.3)
            else:
                cyl(0.25, 0.08, 16, at=(s * (W / 2 - 0.3), yc, 0.32), mat="metal_rusted", center=True, axis="X")
    # door leaves on the kerb side (Blender -X = Unity +X, the bus's right)
    for i in door_bays:
        yc = (ys[i] + ys[i + 1]) / 2
        dw = ys[i + 1] - ys[i]
        box(0.03, 0.05, 2.5, at=(-W / 2 - 0.01, yc, 0.4), mat="plastic_dark", base=True)
        for e in (-1, 1):
            box(0.03, 0.06, 2.5, at=(-W / 2 - 0.01, yc + e * dw / 2, 0.4), mat="plastic_dark", base=True)
        box(0.03, dw, 0.06, at=(-W / 2 - 0.01, yc, 2.88), mat="plastic_dark", base=True)
        box(0.03, dw - 0.1, 0.5, at=(-W / 2 - 0.012, yc, 0.42), mat=paint, base=True)
    # side light strip (prototype cyan), skirts, bumpers, lights, roof pods, destination sign
    for s in (-1, 1):
        box(0.02, L - 1.6, 0.06, at=(s * (W / 2 + 0.005), 0, 1.25), mat="emit_strip_cyan" if not wreck else "emit_strip_cyan")
        box(0.03, L - 1.0, 0.18, at=(s * (W / 2 - 0.01), 0, 0.42), mat="plastic_dark", bevel=0.02)
    box(W - 0.1, 0.18, 0.28, at=(0, y0 + 0.02, 0.45), mat="plastic_dark", bevel=0.04)
    box(W - 0.1, 0.18, 0.28, at=(0, y1 - 0.02, 0.45), mat="plastic_dark", bevel=0.04)
    for s in (-1, 1):
        box(0.4, 0.05, 0.12, at=(s * 0.9, y0 - 0.06, 0.8), mat="black" if wreck else "car_headlight", bevel=0.02)
        box(0.3, 0.05, 0.25, at=(s * 1.0, y1 + 0.06, 0.9), mat="car_taillight", bevel=0.02)
    box(1.6, 0.06, 0.3, at=(0, y0 + 0.03, H - 0.35), mat="screen")
    box(1.8, 3.4, 0.35, at=(0, 1.0, H), mat=paint, base=True, bevel=0.08, bseg=2)
    if detail():
        for k in range(3):
            box(1.5, 0.6, 0.02, at=(0, 0.0 + k * 0.9, H + 0.35), mat="grating")
        for s in (-1, 1):
            m = box(0.06, 0.25, 0.35, mat="plastic_dark", bevel=0.02)
            m.move(s * (W / 2 + 0.15), y0 + 0.3, 2.3)
            beam((s * W / 2, y0 + 0.4, 2.6), (s * (W / 2 + 0.15), y0 + 0.3, 2.45), 0.03, mat="metal_dark")
    if wreck:
        nz = _vnoise(seed)

        def dent(co):
            x, y, z = co
            if z > H - 0.4 and abs(y - 1.5) < 2.0:
                z -= 0.12 * max(0.0, 1 - ((y - 1.5) / 2.0) ** 2)
            if y < y0 + 0.7:
                y += 0.06 * nz(x * 2, z * 2, 1.0)
            return (x, y, z)
        body.displace(dent)
        a = Vector((W / 2 - 0.2, y1 - 3.0, 0))
        b = Vector((W / 2 - 0.2, y0 + 2.4, 0))
        R = Matrix.Translation(a) @ Matrix.Rotation(math.radians(3.0), 4, (b - a).normalized()) @ Matrix.Translation(-a)
        for p in list(K._parts):
            p.xform(R)
        K.ground()
    return {"colliders": [K.collider_box((0, 0, H / 2 + 0.15), (W, L, H - 0.3))]}


# ============================================================================================== metro train car
def train_car(lit=False, L=16.0, W=3.0, H=3.6, seed=81):
    """Metro car: body on two bogies; 3 door pairs per side; window band; cab with windscreen at the -Y end."""
    rnd = random.Random(seed)
    y0, y1 = -L / 2, L / 2
    ys = [y0, y0 + 0.06, y0 + 0.25, y0 + 0.6]
    n = 14
    for i in range(1, n):
        ys.append(y0 + 0.6 + i * (L - 1.2) / n)
    ys += [y1 - 0.6, y1 - 0.25, y1 - 0.06, y1]
    zb, zt = 0.85, H
    secs, idx = [], None
    for y in ys:
        e = min(y - y0, y1 - y)
        k = min(1.0, e / 0.25)
        hw = W / 2 * (0.95 + 0.05 * k)
        pts, idx = rounded_section(hw, hw * 0.9, zb + 0.04 * (1 - k), zt - 0.06 * (1 - k), 0.1, 0.45, n_flat=2, n_arc=3, n_side=6, bulge=0.05, y=y)
        secs.append(pts)
    sr0, sr1 = idx["side_r"]
    sl0, sl1 = idx["side_l"]
    win = "window_lit_warm" if lit else "glass_dark"
    pairs = len(ys) - 1
    door_pairs = {6, 10, 14}

    def fm(i, k):
        if i < 3 or i >= pairs - 3:
            return None
        side_r = sr0 + 2 <= k < sr1 - 1
        side_l = sl0 + 1 <= k < sl1 - 2
        if i in door_pairs:
            if sr0 <= k < sr1 - 1 or sl0 + 1 <= k < sl1:
                return "metal_painted_white"
            return None
        if side_r or side_l:
            return win
        return None

    body = loft(secs, mat="metal_painted", face_mat=fm, name="train")
    # door panels: emit strip + door seam + door windows
    for i in door_pairs:
        yc = (ys[i] + ys[i + 1]) / 2
        for s in (-1, 1):
            box(0.012, 0.012, 1.9, at=(s * (W / 2 + 0.05), yc, 0.95), mat="black", base=True)
            for dy in (-0.3, 0.3):
                box(0.01, 0.38, 0.75, at=(s * (W / 2 + 0.05), yc + dy, 2.0), mat=win, bevel=0.01)
            box(0.02, (ys[i + 1] - ys[i]) + 0.1, 0.05, at=(s * (W / 2 + 0.04), yc, 3.0), mat="emit_amber" if lit else "black")
    # cab end: windscreen + lights + coupler
    box(W * 0.78, 0.05, 1.1, at=(0, y0 - 0.005, 2.35), mat="glass_dark", bevel=0.04)
    for s in (-1, 1):
        box(0.35, 0.05, 0.1, at=(s * 0.95, y0 - 0.01, 1.3), mat="car_headlight" if lit else "black", bevel=0.02)
        box(0.2, 0.05, 0.08, at=(s * 0.95, y1 + 0.01, 1.3), mat="car_taillight", bevel=0.02)
    box(1.2, 0.06, 0.25, at=(0, y0 - 0.01, 3.25), mat="screen")
    box(W * 0.6, 0.05, 2.0, at=(0, y1 + 0.005, 0.95), mat="black", base=True)
    for yy, sg in ((y0, -1), (y1, 1)):
        cyl(0.09, 0.45, 10, at=(0, yy + sg * 0.22, 1.05), axis="Y", center=True, mat="metal_dark")
        box(0.3, 0.12, 0.25, at=(0, yy + sg * 0.48, 1.05), mat="metal_dark", bevel=0.02)
    # side stripe (prototype win_cool strip)
    for s in (-1, 1):
        box(0.02, L - 1.4, 0.05, at=(s * (W / 2 + 0.035), 0, 1.4), mat="emit_strip_cyan" if lit else "metal_painted_white")
    # underframe + bogies
    box(W - 0.4, L - 1.0, 0.35, at=(0, 0, 0.55), mat="metal_dark", base=True, bevel=0.02)
    for yb in (y0 + 2.8, y1 - 2.8):
        box(2.2, 2.6, 0.35, at=(0, yb, 0.32), mat="metal_dark", base=True, bevel=0.03)
        for dy in (-0.9, 0.9):
            for s in (-1, 1):
                cyl(0.42, 0.12, 20, at=(s * 0.75, yb + dy, 0.42), axis="X", center=True, mat="metal_rusted", bevel=0.01)
                if detail():
                    cyl(0.12, 0.16, 10, at=(s * 0.82, yb + dy, 0.42), axis="X", center=True, mat="metal_dark")
        if detail():
            for s in (-1, 1):
                cyl(0.09, 0.4, 10, at=(s * 1.05, yb, 0.55), mat="metal_bare")
                tube([(s * 1.0, yb - 0.6, 0.62), (s * 1.12, yb, 0.82), (s * 1.0, yb + 0.6, 0.62)], 0.06, 6, "metal_dark")
    # roof equipment
    for yy in (-4.0, 4.0):
        box(1.7, 2.6, 0.32, at=(0, yy, H - 0.02), mat="metal_dark", base=True, bevel=0.05)
        if detail():
            for s in (-1, 1):
                cyl(0.28, 0.04, 16, at=(s * 0.45, yy, H + 0.3), mat="grating")
    if detail():
        # pantograph-free third-rail shoes + cable conduit on the roof
        cyl(0.05, L - 3.0, 8, at=(0.9, -(L - 3.0) / 2, H + 0.02), axis="Y", mat="plastic_dark")
    return {"colliders": [K.collider_box((0, 0, 2.2), (W, L, H - 0.8)), K.collider_box((0, 0, 0.5), (W - 0.4, L - 1.0, 0.9))]}


ASSETS.update({
    "Bus_Transit": dict(fn=bus, cat="vehicles", zones=["plaza"],
                        notes="11 m transit bus (wrecked: dented roof, one front wheel missing, slight lean). Two double doors on the kerb side (Unity +X). Cyan side strip."),
    "Bus_Transit_Intact": dict(fn=bus, kw={"wreck": False, "seed": 9, "paint": "metal_painted_white"}, cat="vehicles", zones=["plaza"], notes="Undamaged white bus."),
    "TrainCar_Metro": dict(fn=train_car, cat="vehicles", zones=["metro"],
                           notes="16 m metro car on two bogies (wheel tops at rail height 0.0). Dark/unpowered: windows glass_dark. Cab end at +Z."),
    "TrainCar_Metro_Lit": dict(fn=train_car, kw={"lit": True}, cat="vehicles", zones=["metro"],
                               notes="Powered variant: window_lit_warm windows, cyan side strip, amber door lights."),
})
