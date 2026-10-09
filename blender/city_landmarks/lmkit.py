"""lmkit: core of the city landmark / district building generator (Blender 5.2 headless).

Built on the environment pipeline's envkit (primitives, Part, placed(), finalize, LODs, FBX export, records) so the
kit follows the same conventions: metres, Blender Z up, FRONT = Blender -Y (= Unity +Z), pivot base-centre, UV0 in
metres for tiling materials, export axis settings identical to the env kit.

Material model (<= 8 slots per asset):
  * tiling walls/roofs: env kit materials (concrete, concrete_dark, concrete_wet, plaster, brick, metal_plate,
    corrugated, metal_rusted, grating, glass) and this kit's lm_* materials (lmmats.py, macro-varied 2K sets)
  * every small material -> building_trim_atlas (trim bands + flat colour cells)
  * every emissive / window / sign / screen material -> emit_building_atlas
The builders model with readable material names (env names, atlas entry names such as 'win_tv_room',
'office_04_partial', 'sign_03', 'lacquer_red'); finalize_lods() remaps them onto the two atlases (atlas_remap.py).
"""
import json
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lmpaths  # noqa: E402
sys.path.insert(1, lmpaths.ENV_SRC)

import bmesh  # noqa: E402
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import envkit as K  # noqa: E402
import matdefs  # noqa: E402
import atlas_remap as R  # noqa: E402

TRIM, EMIT = R.TRIM, R.EMIT

# ============================================================================================== material registry
_LAYOUT = json.load(open(lmpaths.ATLAS_LAYOUT))
LM_TILE = {"lm_concrete_weathered": (6.0, "#7c7a75"), "lm_mosaic_tile": (3.0, "#9cbdb2"), "lm_brick_soot": (4.0, "#6a3a2c"),
           "lm_cladding_dark": (4.8, "#2b3036"), "lm_corrugated_painted": (4.0, "#55716e"), "lm_plaster_pastel": (4.0, "#c08a7b"),
           "lm_roof_tiles": (2.0, "#1f4f49")}


def _register():
    reg = matdefs.REGISTRY
    for n, (tile, hx) in LM_TILE.items():
        reg[n] = {"kind": "baked", "uv": "world", "tile": tile, "params": {"base": matdefs.lin(hx)}, "unity": {}}
    for atlas, a in _LAYOUT["atlases"].items():
        for n, e in a["entries"].items():
            if n in reg:
                continue
            uv = {"cell": "fit", "strip": "strip", "band": "world", "flat": "world"}[e["kind"]]
            reg[n] = {"kind": "param" if e["kind"] == "flat" else "baked", "uv": uv, "tile": 1.0,
                      "params": {"base": (0.4, 0.4, 0.4)}, "preview": (0.4, 0.4, 0.4), "unity": {}}
    for a in ("building_trim_atlas", "emit_building_atlas"):
        reg.setdefault(a, {"kind": "param", "unity": {}, "preview": (0.3, 0.3, 0.3)})


_register()

# every atlas entry name (and the env names they replace) -> (atlas, entry)
MAPPING = dict(R.ENV_TO_ATLAS)
for _atlas, _a in _LAYOUT["atlases"].items():
    for _n in _a["entries"]:
        MAPPING[_n] = (_atlas, _n)

ENTRY = {n: _LAYOUT["atlases"][MAPPING[n][0]]["entries"][MAPPING[n][1]] for n in MAPPING}
SRC_MODES = {}
for _n, _e in ENTRY.items():
    SRC_MODES[_n] = {"cell": "fit", "strip": "strip", "band": "world", "flat": "param"}[_e["kind"]]
for _n in R.ENV_TO_ATLAS:     # env sources keep their own UV mode (fit / strip / world / param)
    SRC_MODES.pop(_n, None)

WIN_LIT = ["window_lit_warm", "window_lit_cool", "win_warm_living", "win_tv_room", "win_neon_room", "win_blinds_warm", "win_plants",
           "win_fluoro_kitchen", "win_curtains_closed", "win_monitor_den", "win_frosted"]
WIN_WARM = ["window_lit_warm", "win_warm_living", "win_blinds_warm", "win_plants", "win_curtains_closed", "win_fluoro_kitchen"]
WIN_DARK = ["win_dark", "win_standby", "win_papered", "win_dark"]
OFFICE = sorted(n for n, e in ENTRY.items() if e.get("group") == "office")
OFFICE_LIT = [n for n in OFFICE if ENTRY[n].get("lit")]
# weighted: mostly white / warm open-plan floors, an occasional blinds floor, rare lounge (magenta) and server (cyan) floors
OFFICE_LIT = [n for n in OFFICE_LIT for _ in range(1 if ("lounge" in n or "server" in n) else 3)]
WIN_INDUSTRIAL = ["win_fluoro_kitchen", "window_lit_warm", "win_blinds_warm", "win_frosted", "win_fluoro_kitchen", "window_lit_cool"]
OFFICE_DARK = [n for n in OFFICE if not ENTRY[n].get("lit")]
SIGNS = sorted(n for n, e in ENTRY.items() if e.get("group") == "sign")
NEONS = ["emit_neon_magenta", "emit_neon_pink", "emit_neon_cyan", "emit_neon_blue", "emit_neon_yellow", "emit_neon_violet"]
STRIPS = ["emit_strip_cyan", "emit_strip_violet", "emit_strip_magenta", "emit_strip_pink", "emit_strip_blue", "emit_strip_yellow", "emit_strip_warm"]
ADS = ["screen_ad_a", "screen_ad_b", "screen_ad_c"]
NEON_HEX = {"magenta": "#ff2bd6", "pink": "#ff4f9a", "cyan": "#00e5ff", "blue": "#3d7bff", "yellow": "#ffe14d", "violet": "#9b5cff",
            "warm": "#ffb070", "red": "#ff3a2e", "amber": "#ffa21f", "white": "#e8f2ff"}


def h(*args):
    """Stable (process independent) hash for seeding."""
    import zlib
    return zlib.crc32(repr(args).encode())


def glow_hex(mat):
    for k, v in NEON_HEX.items():
        if k in mat:
            return v
    return "#ffb070"


class Floors:
    """Per-building lit-window model: every floor gets its own activity (some floors dark, some fully lit), each
    window a deterministic variant, so LOD0/1/2 agree and the facade never shows one repeated pattern."""

    def __init__(self, seed, base=0.38, warm_bias=0.5, office=False, pool=None):
        self.pool = pool
        self.rng = random.Random(seed)
        self.seed = seed
        self.base = base
        self.warm_bias = warm_bias
        self.office = office
        self.act = {}

    def activity(self, f):
        if f not in self.act:
            r = random.Random(self.seed * 131 + f * 17)
            roll = r.random()
            a = 0.04 if roll < 0.14 else (0.9 if roll > 0.9 else min(0.95, max(0.05, self.base + r.uniform(-0.28, 0.28))))
            self.act[f] = a
        return self.act[f]

    def window(self, f, key):
        if self.office:
            return self.office_pane(f, key)
        r = random.Random(h(self.seed, f, key))
        if r.random() < self.activity(f):
            pool = self.pool or (WIN_WARM if r.random() < self.warm_bias else WIN_LIT)
            return pool[r.randrange(len(pool))]
        return WIN_DARK[r.randrange(len(WIN_DARK))]

    def office_pane(self, f, key):
        r = random.Random(h(self.seed, f, key, "o"))
        # offices light whole floors: activity decides the floor, a few panes differ
        lit = (r.random() < 0.85) == (self.activity(f) > 0.35)
        pool = OFFICE_LIT if lit else OFFICE_DARK
        return pool[(h(self.seed, f) + (h(key) if r.random() < 0.3 else 0)) % len(pool)]


# ============================================================================================== face frames
class Frame:
    """Local frame of a wall: origin at the left end of the wall line (seen from outside) at z=0, U along the wall,
    N outward. Local (u, z, w) -> Blender (O + U*u + N*w, z)."""

    def __init__(self, ox, oy, ux, uy, length):
        self.o = Vector((ox, oy, 0.0))
        self.u = Vector((ux, uy, 0.0)).normalized()
        self.n = Vector((self.u.y, -self.u.x, 0.0))   # right-hand: outward = U rotated -90 deg (CCW footprint)
        self.length = length

    def p(self, u, z, w=0.0):
        return self.o + self.u * u + self.n * w + Vector((0, 0, z))

    @property
    def angle(self):
        return math.degrees(math.atan2(self.u.y, self.u.x))

    def matrix(self):
        """Matrix mapping face-local (x=u, y=-w, z) boxes into the world (local -Y = outward)."""
        return Matrix.Translation(self.o) @ Matrix.Rotation(math.radians(self.angle), 4, "Z")


def rect_frames(x0, y0, x1, y1):
    """Four outward frames of an axis-aligned footprint, CCW: south (-Y, front), east (+X), north (+Y), west (-X)."""
    return {
        "s": Frame(x0, y0, 1, 0, x1 - x0),
        "e": Frame(x1, y0, 0, 1, y1 - y0),
        "n": Frame(x1, y1, -1, 0, x1 - x0),
        "w": Frame(x0, y1, 0, -1, y1 - y0),
    }


def poly_frames(pts):
    """Frames along a CCW polygon [(x, y), ...]."""
    out = []
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L > 1e-3:
            out.append(Frame(a[0], a[1], (b[0] - a[0]) / L, (b[1] - a[1]) / L, L))
    return out


# ============================================================================================== quad mesher
class Mesh:
    """Accumulates explicit-UV quads into one envkit Part (material slots by name). Faces are KEEP-UV: U = metres
    along the quad's first edge, V = metres along its second (wall quads: U along the wall, V = height)."""

    def __init__(self, first_mat, name="mesh"):
        self.part = K._new(first_mat, name)
        self.bm = self.part.bm

    def quad(self, a, b, c, d, mat, uv=None):
        bm, p = self.bm, self.part
        try:
            f = bm.faces.new([bm.verts.new(a), bm.verts.new(b), bm.verts.new(c), bm.verts.new(d)])
        except ValueError:
            return None
        f[p.mats] = p.slot(mat)
        f[p.uvm] = K.UVM_KEEP
        if uv is None:
            a_, b_, d_ = Vector(a), Vector(b), Vector(d)
            eu = (b_ - a_)
            ev = (d_ - a_)
            lu, lv = eu.length, ev.length
            uv = ((0, 0), (lu, 0), (lu, lv), (0, lv))
        for l, t in zip(f.loops, uv):
            l[p.uvl].uv = t
        return f

    def wall(self, F, u0, u1, z0, z1, w, mat, uoff=0.0):
        """Wall quad on frame F (outward facing) at offset w; UV = (u + uoff, z) metres."""
        return self.quad(F.p(u0, z0, w), F.p(u1, z0, w), F.p(u1, z1, w), F.p(u0, z1, w), mat,
                         ((u0 + uoff, z0), (u1 + uoff, z0), (u1 + uoff, z1), (u0 + uoff, z1)))

    def reveal(self, F, u0, u1, z0, z1, depth, mat, back_mat, bottom_mat=None, w0=0.0):
        """Recessed opening: 4 reveal quads going `depth` into the wall and the back pane (fit UV by its material)."""
        wb = w0 - depth
        # left jamb (faces +U), right jamb (faces -U), sill (faces up), head (faces down)
        self.quad(F.p(u0, z0, w0), F.p(u0, z0, wb), F.p(u0, z1, wb), F.p(u0, z1, w0), mat,
                  ((0, z0), (depth, z0), (depth, z1), (0, z1)))
        self.quad(F.p(u1, z0, wb), F.p(u1, z0, w0), F.p(u1, z1, w0), F.p(u1, z1, wb), mat,
                  ((0, z0), (depth, z0), (depth, z1), (0, z1)))
        self.quad(F.p(u0, z0, w0), F.p(u1, z0, w0), F.p(u1, z0, wb), F.p(u0, z0, wb), bottom_mat or mat,
                  ((u0, 0), (u1, 0), (u1, depth), (u0, depth)))
        self.quad(F.p(u0, z1, wb), F.p(u1, z1, wb), F.p(u1, z1, w0), F.p(u0, z1, w0), mat,
                  ((u0, 0), (u1, 0), (u1, depth), (u0, depth)))
        if back_mat:
            self.quad(F.p(u0, z0, wb), F.p(u1, z0, wb), F.p(u1, z1, wb), F.p(u0, z1, wb), back_mat,
                      ((0, 0), (1, 0), (1, 1), (0, 1)))

    def cap(self, pts, z, mat, down=False):
        """Horizontal polygon (CCW pts) at height z (roof / soffit), UV = world xy."""
        bm, p = self.bm, self.part
        vs = [bm.verts.new((x, y, z)) for x, y in (reversed(pts) if down else pts)]
        try:
            f = bm.faces.new(vs)
        except ValueError:
            return None
        f[p.mats] = p.slot(mat)
        f[p.uvm] = K.UVM_KEEP
        for l in f.loops:
            l[p.uvl].uv = (l.vert.co.x, l.vert.co.y)
        return f


def fbox(F, u0, u1, z0, z1, w0, w1, mat, bevel=0.0):
    """Box in frame space (u0..u1 along the wall, w0..w1 outward offsets, z0..z1)."""
    if u1 - u0 < 1e-4 or z1 - z0 < 1e-4 or abs(w1 - w0) < 1e-4:
        return None
    wl, wh = min(w0, w1), max(w0, w1)
    b = K.box(u1 - u0, wh - wl, z1 - z0, at=((u0 + u1) / 2, -(wl + wh) / 2, z0), mat=mat, base=True, bevel=bevel)
    b.xform(F.matrix())
    return b


def fcyl(F, u, z, w, r, h, mat, n=10, axis="Z", r2=None):
    c = K.cyl(r, h, n, at=(0, 0, 0), mat=mat, axis=axis, r2=r2)
    c.move(u, -w, z)
    c.xform(F.matrix())
    return c


def ftube(F, pts_uzw, r, mat, n=6):
    pts = [tuple(F.p(u, z, w)) for (u, z, w) in pts_uzw]
    return K.tube(pts, r, n, mat)


def box(x0, x1, y0, y1, z0, z1, mat, bevel=0.0):
    if x1 - x0 < 1e-4 or y1 - y0 < 1e-4 or z1 - z0 < 1e-4:
        return None
    return K.box(x1 - x0, y1 - y0, z1 - z0, at=((x0 + x1) / 2, (y0 + y1) / 2, z0), mat=mat, base=True, bevel=bevel)


# ============================================================================================== finalize / export
def _drop_unused_slots(ob):
    me = ob.data
    idx = np.zeros(len(me.polygons), np.int32)
    me.polygons.foreach_get("material_index", idx)
    used = sorted(set(idx.tolist()))
    if len(used) == len(me.materials):
        return
    mats = [me.materials[i] for i in used]
    remap = {o: n for n, o in enumerate(used)}
    idx = np.array([remap[i] for i in idx], np.int32)
    me.materials.clear()
    for m in mats:
        me.materials.append(m)
    me.polygons.foreach_set("material_index", idx)
    me.update()


def build_lods(name, builder, lods=3, **kw):
    """LOD0..LOD(lods-1) by re-running the builder at each K.LOD (no decimation: the builders reduce by construction),
    then the atlas remap. Returns the objects."""
    out = []
    for lv in range(lods):
        K.set_lod(lv)
        builder(**kw)
        out.append(K.finalize(f"{name}_LOD{lv}"))
    K.set_lod(0)
    finalize_lods(out)
    return out


def finalize_lods(lods):
    for ob in lods:
        _drop_unused_slots(ob)
        R.remap(ob, mapping=MAPPING, src_modes=SRC_MODES)
        _drop_unused_slots(ob)


def build(name, builder, category, notes="", lods=3, folder=None, pivot="base-centre", lod1_ratio=0.5, lod2_ratio=0.15, **kw):
    """Run builder for LOD0..2, remap materials onto the atlases, export the FBX into the landmark kit, write a record."""
    K.reset()
    meta = {}

    def runner(**kk):
        r = builder(**kk)
        if K.LOD == 0 and isinstance(r, dict):
            meta.update(r)

    objs = build_lods(name, runner, lods=lods, **kw)
    lod0, lod1 = objs[0], objs[1]
    lod2 = objs[2] if len(objs) > 2 else None
    rel = f"Models/{folder or category.title()}/{name}.fbx"
    K.export_fbx(objs, os.path.join(lmpaths.KIT, rel))
    extra = {k: v for k, v in meta.items() if k != "colliders"}
    rec = K.record(name, category, meta.pop("zones", ["plaza"]) if "zones" in meta else ["plaza"], lod0, lod1, rel,
                   colliders=meta.get("colliders"), pivot=pivot, notes=notes, extra=extra or None, lod2=lod2)
    if len(rec["materials"]) > 8:
        print(f"[lm] WARNING {name}: {len(rec['materials'])} materials (> 8)", flush=True)
    path = os.path.join(lmpaths.RECORDS, name + ".json")
    json.dump(rec, open(path, "w"), indent=1)
    print(f"[lm] {name:34s} LOD0 {rec['tris']['LOD0']:7d} LOD1 {rec['tris']['LOD1']:6d} LOD2 {rec['tris'].get('LOD2', 0):6d}  "
          f"mats {len(rec['materials'])} {rec['materials']}  size {rec['size']}", flush=True)
    return rec, objs


def collider(cx, cy, cz, sx, sy, sz):
    """Box collider from Blender centre/size."""
    return K.collider_box((cx, cy, cz), (sx, sy, sz))


def unity_pt(x, y, z):
    return [round(v, 3) for v in K.to_unity_vec((x, y, z))]


def light(x, y, z, mat_or_hex, rng=12.0, intensity=1.0, source=""):
    col = mat_or_hex if mat_or_hex.startswith("#") else glow_hex(mat_or_hex)
    return {"position": unity_pt(x, y, z), "color": col, "range": rng, "intensity": intensity, "source": source}


def detail():
    return K.LOD == 0


def lod():
    return K.LOD
