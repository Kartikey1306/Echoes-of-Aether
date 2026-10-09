"""Street-kit modelling helpers on top of envkit (Blender). Coordinates: Blender metres, Z up, asset FRONT = -Y.

Wall-mounted assets (storefronts, signs, fire escapes, AC units) have their pivot at the wall plane: y = 0 is the
building face and everything protrudes toward -Y; z = 0 is the pavement (or the mounting height for wall items).
"""
import math

import bmesh  # noqa: F401
from mathutils import Vector

import stkit

K = stkit.K


class Meta:
    """Colliders / light anchors / steam anchors / screens in Blender space -> manifest extras (Unity space)."""

    def __init__(self):
        self.cols, self.lights, self.steam, self.extra = [], [], [], {}

    def col(self, center, size):
        self.cols.append((tuple(center), tuple(size)))

    def light(self, p, hexc, rng=4.0, inten=1.5):
        self.lights.append((tuple(p), hexc, rng, inten))

    def vent(self, p):
        self.steam.append(tuple(p))

    def done(self):
        r3 = lambda v: [round(float(x), 3) + 0.0 for x in v]
        out = {"colliders": [K.collider_box(c, s) for c, s in self.cols] if self.cols else [{"type": "none"}]}
        if self.lights:
            ls = [{"position": r3(K.to_unity_vec(p)), "color": h, "range": round(rg, 2), "intensity": round(it, 2)} for p, h, rg, it in self.lights]
            out["light"] = ls[0]
            out["lights"] = ls
            out["glow"] = ls[0]["color"]
        if self.steam:
            out["steam"] = [r3(K.to_unity_vec(p)) for p in self.steam]
        out.update(self.extra)
        return out


def card(mat, corners, uvrect, flip_u=False, name="card", two_sided=False):
    """Quad with explicit atlas UVs (kept by envkit: 'world0' materials + UVM_KEEP faces).
    corners: BL, BR, TR, TL as seen from the side the card faces (the face normal points at the viewer)."""
    p = K._new(mat, name)
    bm = p.bm
    vs = [bm.verts.new(c) for c in corners]
    f = bm.faces.new(vs)
    u0, v0, u1, v1 = uvrect
    if flip_u:
        u0, u1 = u1, u0
    for l, uv in zip(f.loops, ((u0, v0), (u1, v0), (u1, v1), (u0, v1))):
        l[p.uvl].uv = uv
    f[p.uvm] = K.UVM_KEEP
    if two_sided:
        vs2 = [bm.verts.new(c) for c in corners]
        f2 = bm.faces.new(list(reversed(vs2)))
        for l, uv in zip(f2.loops, ((u0, v1), (u1, v1), (u1, v0), (u0, v0))):
            l[p.uvl].uv = uv
        f2[p.uvm] = K.UVM_KEEP
    return p


def front_card(mat, x0, x1, y, z0, z1, uvrect, **kw):
    """Card in the XZ plane at depth y facing -Y (toward the street)."""
    return card(mat, [(x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1)], uvrect, **kw)


def side_card(mat, x, y0, y1, z0, z1, uvrect, facing=1, **kw):
    """Card in the YZ plane at x facing +X (facing=1) or -X; U runs away from the wall (toward -Y) seen from that side."""
    if facing > 0:
        return card(mat, [(x, y0, z0), (x, y1, z0), (x, y1, z1), (x, y0, z1)], uvrect, **kw)
    return card(mat, [(x, y1, z0), (x, y0, z0), (x, y0, z1), (x, y1, z1)], uvrect, **kw)


def bx(sx, sy, sz, x, y, z, mat, bevel=0.0, name="box"):
    """Box from its min corner-ish: centre (x, y) on the floor plane z (base)."""
    return K.box(sx, sy, sz, at=(x, y, z), mat=mat, base=True, bevel=bevel, name=name)


def bmin(x0, y0, z0, x1, y1, z1, mat, bevel=0.0, name="box"):
    """Axis-aligned box between two corners."""
    return K.box(abs(x1 - x0), abs(y1 - y0), abs(z1 - z0), at=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), mat=mat, bevel=bevel, name=name)


def catenary(a, b, sag, n=10):
    a, b = Vector(a), Vector(b)
    pts = []
    for i in range(n + 1):
        t = i / n
        p = a.lerp(b, t)
        p.z -= sag * 4 * t * (1 - t)
        pts.append(tuple(p))
    return pts
