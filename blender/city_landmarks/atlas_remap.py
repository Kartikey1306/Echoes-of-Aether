"""Remap a finalized mesh object (envkit conventions) from many small materials onto the shared building atlases.

Per UV island (faces of one material connected through shared UVs):
  * world-tiled source  -> trim band (tiles along U). The island is turned so its short side runs along V; if it
                           fits the band height it keeps its exact metric scale (random V offset inside the band),
                           otherwise it is scaled down UNIFORMLY to fit (lower texel density, never stretched).
  * 'fit' source (0..1) -> atlas cell rect (inset by a half texel pad). Groups (window interiors, office panes,
                           signs) can pick a variant per island.
  * 'strip' source      -> strip band (U metres along, V 0..1 across).
  * parameter source    -> flat colour cell (all UVs at the cell centre).
Choices are seeded by the island centroid, so LOD0/LOD1/LOD2 of one asset pick the same variants.
"""
import hashlib
import json
import math
import random

import bmesh
import bpy
import numpy as np

import lmpaths

_layout = None


def layout():
    global _layout
    if _layout is None:
        _layout = json.load(open(lmpaths.ATLAS_LAYOUT))
    return _layout


def entry(atlas, name):
    return layout()["atlases"][atlas]["entries"][name]


def group_names(atlas, group, lit=None):
    out = []
    for n, e in layout()["atlases"][atlas]["entries"].items():
        if e.get("group") == group and (lit is None or e.get("lit", True) == lit):
            out.append(n)
    return sorted(out)


# Env kit materials -> atlas entries (used by the Building_* reduction and by the landmark builders' remap pass).
TRIM = "building_trim_atlas"
EMIT = "emit_building_atlas"
ENV_TO_ATLAS = {}
for _n in ("metal_dark", "metal_painted", "metal_painted_white", "metal_rusted", "wood", "paint_glossy_dark", "tile_grimy", "tarp",
           "tarp_blue", "metal_painted_yellow", "metal_painted_red", "metal_bare", "chrome_scratched", "paint_glossy_red", "rubber",
           "plastic_dark", "plastic_orange", "black", "terracotta"):
    ENV_TO_ATLAS[_n] = (TRIM, _n)
for _n in ("window_lit_warm", "window_lit_cool", "screen_ad_a", "screen_ad_b", "screen_ad_c", "screen", "emit_panel_cyan",
           "emit_panel_violet", "emit_panel_white", "emit_panel_warm", "emit_panel_magenta", "emit_panel_yellow",
           "emit_strip_cyan", "emit_strip_violet", "emit_strip_warm", "emit_strip_magenta", "emit_strip_pink", "emit_strip_blue",
           "emit_strip_yellow", "emit_red", "emit_green", "emit_amber", "emit_white", "emit_cyan", "emit_violet", "glass_dark",
           "emit_neon_magenta", "emit_neon_pink", "emit_neon_cyan", "emit_neon_blue", "emit_neon_yellow", "emit_neon_violet"):
    ENV_TO_ATLAS[_n] = (EMIT, _n)


def _seed(*vals):
    h = hashlib.md5(("|".join(f"{v:.2f}" if isinstance(v, float) else str(v) for v in vals)).encode()).hexdigest()
    return int(h[:8], 16)


class _UF:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, a):
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            self.p[b] = a


def _islands(bm, uvl, faces):
    idx = {f.index: i for i, f in enumerate(faces)}
    uf = _UF(len(faces))
    fset = set(idx)
    for f in faces:
        for e in f.edges:
            for g in e.link_faces:
                if g is f or g.index not in fset or g.index < f.index or g.material_index != f.material_index:
                    continue
                la = {l.vert: l[uvl].uv for l in f.loops}
                lb = {l.vert: l[uvl].uv for l in g.loops}
                ok = all((la[v] - lb[v]).length < 1e-4 for v in e.verts)
                if ok:
                    uf.union(idx[f.index], idx[g.index])
    groups = {}
    for f in faces:
        groups.setdefault(uf.find(idx[f.index]), []).append(f)
    return list(groups.values())


def _centroid(isl):
    c = [0.0, 0.0, 0.0]
    n = 0
    for f in isl:
        m = f.calc_center_median()
        c[0] += m.x; c[1] += m.y; c[2] += m.z
        n += 1
    return [round(x / n, 1) for x in c]


def remap(ob, mapping=None, pick=None, src_modes=None, name_salt=""):
    """mapping: material name -> (atlas, entry) ; pick: optional fn(src_name, centroid, rng) -> entry name override.
    src_modes: material name -> 'world' | 'fit' | 'strip' | 'param' (defaults from the env manifest / registry)."""
    mapping = ENV_TO_ATLAS if mapping is None else mapping
    me = ob.data
    names = [m.name.split(".")[0] if m else "" for m in me.materials]
    if not any(n in mapping for n in names):
        return ob
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    uvl = bm.loops.layers.uv.active
    # new material list: kept ones first (original order), then the atlases in use
    keep = [n for n in names if n not in mapping]
    atl = []
    for n in names:
        if n in mapping and mapping[n][0] not in atl:
            atl.append(mapping[n][0])
    new_names = []
    for n in keep + atl:
        if n not in new_names:
            new_names.append(n)
    by_mat = {}
    for f in bm.faces:
        by_mat.setdefault(f.material_index, []).append(f)
    L = layout()
    for mi, faces in by_mat.items():
        src = names[mi]
        if src not in mapping:
            for f in faces:
                f.material_index = new_names.index(src)
            continue
        atlas, ename = mapping[src]
        mode = (src_modes or {}).get(src) or _mode(src)
        for isl in _islands(bm, uvl, faces):
            cen = _centroid(isl)
            rng = random.Random(_seed(ob.name.split("_LOD")[0], name_salt, src, *cen))
            en = pick(src, cen, rng) if pick else None
            en = en or ename
            e = L["atlases"][atlas]["entries"][en]
            _apply(isl, uvl, e, mode, rng)
            for f in isl:
                f.material_index = new_names.index(atlas)
    bm.to_mesh(me)
    bm.free()
    idx = np.zeros(len(me.polygons), np.int32)
    me.polygons.foreach_get("material_index", idx)
    me.materials.clear()
    for n in new_names:
        me.materials.append(_material(n))
    me.polygons.foreach_set("material_index", idx)
    me.update()
    return ob


def _material(name):
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
    return m


_MODES = None


def _mode(name):
    global _MODES
    if _MODES is None:
        man = json.load(open(lmpaths.ENV_KIT + "/manifest.json"))["materials"]
        _MODES = {k: ("param" if v.get("kind") == "param" else v.get("uvMode", "world")) for k, v in man.items()}
    return _MODES.get(name, "world")


def _apply(isl, uvl, e, mode, rng):
    kind = e["kind"]
    if kind == "flat" or mode == "param":
        u, v = e["uv"] if "uv" in e else ((e["rect"][0] + e["rect"][2]) / 2, (e["rect"][1] + e["rect"][3]) / 2)
        for f in isl:
            for l in f.loops:
                l[uvl].uv = (u, v)
        return
    u0, v0, u1, v1 = e["rect"]
    if kind == "cell":
        pu, pv = e.get("pad", [0.0, 0.0])
        flip = e.get("allowFlip", False) and rng.random() < 0.5
        for f in isl:
            if mode != "fit":
                _fit_face(f, uvl)
            for l in f.loops:
                a, b = l[uvl].uv
                a = min(1.0, max(0.0, a))
                b = min(1.0, max(0.0, b))
                if flip:
                    a = 1 - a
                l[uvl].uv = (u0 + pu + a * (u1 - u0 - 2 * pu), v0 + pv + b * (v1 - v0 - 2 * pv))
        return
    if kind == "strip":
        pv = e.get("pad_v", 0.0)
        span = e["span_u_m"]
        off = rng.random()
        for f in isl:
            for l in f.loops:
                a, b = l[uvl].uv
                if mode != "strip":
                    b = 0.5
                b = min(1.0, max(0.0, b))
                l[uvl].uv = (a / span + off, v0 + pv + b * (v1 - v0 - 2 * pv))
        return
    # band: metric island -> band (tiles along U)
    span_u, span_v = e["span_u_m"], e["span_v_m"]
    pad_m = e.get("pad_v", 0.0) / max(v1 - v0, 1e-9) * span_v
    usable = max(span_v - 2 * pad_m, 1e-4)
    uvs = [(l, l[uvl].uv.copy()) for f in isl for l in f.loops]
    if mode == "fit":   # 0..1 per face: treat as 1 m
        pass
    us = [p[1][0] for p in uvs]
    vs = [p[1][1] for p in uvs]
    du, dv = max(us) - min(us), max(vs) - min(vs)
    swap = dv > du * 1.05
    if swap:
        uvs = [(l, (uv[1], uv[0])) for l, uv in uvs]
        du, dv = dv, du
    vmin = min(p[1][1] for p in uvs)
    if dv <= usable:
        s = 1.0
        voff = pad_m + rng.random() * (usable - dv)
    else:
        s = usable / dv
        voff = pad_m
    uoff = rng.random() * span_u
    for l, (a, b) in uvs:
        uu = (a * s + uoff) / span_u
        vv = ((b - vmin) * s + voff) / span_v
        l[uvl].uv = (uu, v0 + vv * (v1 - v0))


def _fit_face(f, uvl):
    """0..1 face-fit UVs (wall-like faces: U horizontal, V up), like envkit._fit_uv."""
    from mathutils import Vector
    n = f.normal
    if abs(n.z) < 0.7:
        t = Vector((0, 0, 1)).cross(n).normalized()
    else:
        t = Vector((1, 0, 0))
    b = n.cross(t).normalized()
    cs = [(l.vert.co.dot(t), l.vert.co.dot(b)) for l in f.loops]
    us, vs = [c[0] for c in cs], [c[1] for c in cs]
    a0, a1, b0, b1 = min(us), max(us), min(vs), max(vs)
    for l, (a, bb) in zip(f.loops, cs):
        l[uvl].uv = ((a - a0) / max(a1 - a0, 1e-6), (bb - b0) / max(b1 - b0, 1e-6))
