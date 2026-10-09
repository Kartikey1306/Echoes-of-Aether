"""Wheels: tyre with modelled tread, rim barrel, spokes / aero disc, brake disc, lug nuts, glyph centre cap.

Built centred at the origin with the axle along X and the OUTER face toward +X (right-hand side).
Left wheels are mirrored by the caller.  All parts in one Part; returns the Part.
"""
import math

from mathutils import Matrix, Vector

import vkit as K
import vtex


def tyre_profile(R, W, rim_r, grooves=True):
    """(r, x) points from the inner bead round the tread to the outer bead, and closing under the bead."""
    h = W / 2
    side = [(rim_r + 0.006, -h * 0.86), (rim_r + (R - rim_r) * 0.45, -h * 1.0),
            (R - 0.03, -h * 0.97), (R - 0.008, -h * 0.88)]
    tread = [(R, -h * 0.74)]
    if grooves:
        for c in (-0.36, 0.36):
            tread += [(R, h * (c - 0.07)), (R - 0.011, h * (c - 0.05)), (R - 0.011, h * (c + 0.05)), (R, h * (c + 0.07))]
    tread += [(R, h * 0.74)]
    out = [(r, -x) for (r, x) in reversed(side)]
    return side + tread + out


def build_tyre(p, R, W, rim_r, n, mat="veh_rubber", lod=0):
    prof = tyre_profile(R, W, rim_r, grooves=(lod == 0))
    if lod >= 2:
        prof = [(rim_r + 0.01, -W / 2 * 0.9), (R - 0.02, -W / 2), (R, -W / 2 * 0.7), (R, W / 2 * 0.7), (R - 0.02, W / 2), (rim_r + 0.01, W / 2 * 0.9)]
    rings, fs = K.lathe(p, prof, n=n, m=mat, closed=True)
    if lod == 0:
        # tread blocks: alternate rings pull the shoulder + centre tread in -> lateral sipes / directional blocks
        npf = len(prof)
        tread_idx = [k for k, (r, x) in enumerate(prof) if abs(r - R) < 1e-6]
        for a, ring in enumerate(rings):
            if a % 2 == 1:
                for k in tread_idx:
                    v = ring[k]
                    rv = Vector((0, v.co.y, v.co.z))
                    x = v.co.x
                    depth = 0.009 if abs(x) > W / 2 * 0.45 else 0.004
                    v.co.y, v.co.z = (rv * ((R - depth) / R)).y, (rv * ((R - depth) / R)).z
    return rings


def build_rim(p, rim_r, W, style, n, lod=0, spokes=5, accent=None, disc=True, paint="veh_metal"):
    """style: 'aero' (turbine disc + neon ring), 'multi' (twin spokes), 'six' (6 spoke), 'steel' (heavy van dish)."""
    h = W / 2
    face_x = h * 0.80           # outer face plane of the rim
    lip = [(rim_r + 0.008, -h * 0.84), (rim_r - 0.022, -h * 0.55), (rim_r - 0.022, h * 0.55), (rim_r - 0.004, h * 0.72),
           (rim_r + 0.014, h * 0.82), (rim_r + 0.006, h * 0.92), (rim_r - 0.016, h * 0.88), (rim_r - 0.036, h * 0.76)]
    if lod >= 2:
        lip = [(rim_r, -h * 0.85), (rim_r, h * 0.85), (rim_r - 0.03, h * 0.75)]
    lip_mat = "veh_chrome" if style in ("multi", "aero") else paint
    K.lathe(p, lip, n=n, m=lip_mat, mats=["veh_metal"] * 3 + [lip_mat] * 4 if lod < 2 else None)
    hub_r = 0.075
    # ------------------------------------------------------------------ brake disc + hat (rotates with wheel)
    if disc and lod < 2:
        dr = rim_r - 0.055
        K.lathe(p, [(0.09, -h * 0.30), (dr, -h * 0.30), (dr, -h * 0.05), (0.09, -h * 0.05)], n=max(12, n // 2), m="veh_metal", closed=True)
        if lod == 0 and style != "aero":
            # vented rotor slots: thin dark boxes on the face
            for k in range(8):
                a = 2 * math.pi * k / 8
                vs = K.box(p, (0.004, 0.006, dr * 0.42), m="veh_trim")
                p.transform(Matrix.Rotation(a, 4, "X") @ Matrix.Translation((-h * 0.045, 0, dr * 0.68)) @ Matrix.Rotation(math.radians(25), 4, "X"), vs)
    # ------------------------------------------------------------------ face
    if style == "aero":
        # concave turbine disc with 10 raised vanes + neon ring
        prof = [(hub_r, face_x + 0.012), (rim_r * 0.55, face_x - 0.004), (rim_r - 0.02, face_x - 0.016), (rim_r - 0.01, face_x - 0.05),
                (hub_r, face_x - 0.05)]
        K.lathe(p, prof, n=n, m=paint, closed=True)
        if lod < 2:
            nv = 10 if lod == 0 else 5
            for k in range(nv):
                a = 2 * math.pi * k / nv
                vs = K.box(p, (0.016, 0.022, rim_r * 0.62), at=(0, 0, 0), m="veh_chrome" if lod == 0 else paint, bevel=0.004)
                M = Matrix.Rotation(a, 4, "X") @ Matrix.Translation((face_x + 0.002, 0, rim_r * 0.52)) @ Matrix.Rotation(math.radians(28), 4, "Z")
                p.transform(M, vs)
            ring = [(rim_r - 0.028, face_x - 0.008), (rim_r - 0.017, face_x - 0.012), (rim_r - 0.017, face_x - 0.003), (rim_r - 0.028, face_x + 0.001)]
            K.lathe(p, ring, n=n, m=accent or "veh_neon", closed=True)
    elif style == "steel":
        prof = [(hub_r, face_x - 0.04), (rim_r * 0.55, face_x - 0.02), (rim_r * 0.72, face_x - 0.045), (rim_r - 0.022, face_x - 0.07),
                (rim_r - 0.022, face_x - 0.10), (hub_r, face_x - 0.10)]
        K.lathe(p, prof, n=n, m=paint, closed=True)
        if lod < 2:
            for k in range(8):
                a = 2 * math.pi * k / 8 + math.pi / 8
                vs = K.cyl(p, 0.028, 0.03, n=10, axis="X", m="veh_trim", at=(face_x - 0.03, 0, 0))
                p.transform(Matrix.Rotation(a, 4, "X") @ Matrix.Translation((0, 0, rim_r * 0.62)), vs)
        K.lathe(p, [(0.0, face_x + 0.005), (hub_r + 0.02, face_x - 0.005), (hub_r + 0.03, face_x - 0.05), (0, face_x - 0.05)], n=max(12, n // 2), m="veh_metal", closed=False)
    else:
        nsp = spokes if style == "six" else spokes
        twin = style == "multi"
        segs = 3 if lod == 0 else 2
        for k in range(nsp):
            for t in ((-1, 1) if twin and lod < 2 else (0,)):
                a = 2 * math.pi * k / nsp + t * math.radians(7.5)
                # spoke: tapered, dished sweep from the hub to the lip
                path = []
                for q in range(segs + 1):
                    u = q / segs
                    r = hub_r * 0.9 + (rim_r - 0.02 - hub_r * 0.9) * u
                    x = face_x - 0.012 - 0.03 * math.sin(math.pi * u * 0.5) - 0.005 * u
                    path.append(Vector((x, 0, r)))
                w0 = 0.034 if not twin else 0.020
                prof = [(-w0 / 2, -0.012), (w0 / 2, -0.012), (w0 * 0.35, 0.012), (-w0 * 0.35, 0.012)]
                sc = [(1.0 + 0.4 * (1 - q / segs), 1.0) for q in range(segs + 1)]
                p.begin()
                K.sweep(p, path, [(b, a2) for (a2, b) in prof], m=paint if style != "multi" else "veh_metal", up=Vector((1, 0, 0)), scales=sc)
                vs = p.end()
                p.transform(Matrix.Rotation(a, 4, "X"), vs)
        # spoke accent edges for 'six'
        K.lathe(p, [(0.0, face_x + 0.002), (hub_r, face_x - 0.004), (hub_r + 0.008, face_x - 0.04), (0.0, face_x - 0.04)], n=max(12, n // 2), m=paint, closed=False)
    # ------------------------------------------------------------------ lug nuts + centre cap
    if lod == 0:
        for k in range(5):
            a = 2 * math.pi * k / 5
            vs = K.cyl(p, 0.009, 0.02, n=6, axis="X", m="veh_chrome", at=(face_x + 0.006, 0, 0))
            p.transform(Matrix.Rotation(a, 4, "X") @ Matrix.Translation((0, 0, 0.052)), vs)
        # centre emblem: small octagon cap with the hub glyph (atlas)
        cap = [p.vert((face_x + 0.016, 0.03 * math.cos(2 * math.pi * k / 8), 0.03 * math.sin(2 * math.pi * k / 8))) for k in range(8)]
        f = p.face(cap, "veh_decal")
        if f:
            u0, v0, u1, v1 = vtex.atlas_rect("hub")
            for l in f.loops:
                l[p.uv].uv = (u0 + (l.vert.co.y / 0.06 + 0.5) * (u1 - u0), v0 + (l.vert.co.z / 0.06 + 0.5) * (v1 - v0))
    return p


def build_wheel(R=0.355, W=0.29, rim_r=0.255, style="multi", lod=0, spokes=5, accent=None, paint="veh_metal", tyre=True):
    p = K.Part("wheel")
    n = (40, 22, 12)[lod]
    if tyre:
        build_tyre(p, R, W, rim_r, n, lod=lod)
    build_rim(p, rim_r, W, style, (40, 20, 10)[lod], lod=lod, spokes=spokes, accent=accent, paint=paint)
    return p


def build_hubless(R=0.40, W=0.24, lod=0, glow="veh_neon"):
    """Hubless motorcycle wheel: fat tyre on a slim rim ring whose inner face is a glowing band."""
    p = K.Part("hubless")
    n = (48, 24, 12)[lod]
    rim_r = R - 0.085
    build_tyre(p, R, W, rim_r, n, lod=lod)
    h = W / 2
    ring = [(rim_r + 0.004, -h * 0.82), (rim_r - 0.035, -h * 0.80), (rim_r - 0.05, -h * 0.55), (rim_r - 0.05, h * 0.55), (rim_r - 0.035, h * 0.80),
            (rim_r + 0.004, h * 0.82)]
    mats = ["veh_chrome", "veh_metal", glow, "veh_metal", "veh_chrome"]
    K.lathe(p, ring, n=(48, 24, 12)[lod], m="veh_metal", mats=mats)
    if lod < 2:
        # inner glow ring flanks
        for sx in (-1, 1):
            K.lathe(p, [(rim_r - 0.052, sx * h * 0.62), (rim_r - 0.06, sx * h * 0.62), (rim_r - 0.06, sx * h * 0.70), (rim_r - 0.052, sx * h * 0.70)],
                    n=(48, 24, 12)[lod], m=glow, closed=True)
    return p
