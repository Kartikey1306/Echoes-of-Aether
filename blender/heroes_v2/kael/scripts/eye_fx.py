"""Kael makeover - eye occlusion shell and tear-meniscus strip (shared eye shading, EOA/EyeOcclusion + EOA/EyeWet).

EyeOcclusion: per eye a thin spherical shell just in front of the eyeball, behind the lids. UV.x = occlusion, measured
from the real lid aperture (radial ray casts from the eyeball against the face): strongest under the upper lid and
lashes, a narrower band along the lower lid, darker corners. Multiply-blended in Unity, so the eyes sit in the sockets.

EyeWet: per eye a 3-row strip along the lower lid margin with normals rolling from the eyeball normal up towards the
lid shelf (concave meniscus). UV.x = mask. Additive specular only in Unity.

Both are Head-rigid and carry the Eyes' per-eye morph deltas (so the export's baked face morphs move them with the
eyeballs). The lid aperture is measured on the body WITH the export's baked morphs (build_export_morphs.BAKE_MORPHS).
Hidden from the Blender preview renders.
"""
import bpy, bmesh, math
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
import kcommon as K
import meshops

PRE = "mixamorig:"


def _fit_sphere(P):
    A = np.c_[2 * P, np.ones(len(P))]
    b = (P ** 2).sum(1)
    x = np.linalg.lstsq(A, b, rcond=None)[0]
    c = x[:3]
    return c, math.sqrt(max(x[3] + c @ c, 1e-12))


def _world(o, co):
    M = np.array(o.matrix_world)
    return co @ M[:3, :3].T + M[:3, 3]


def _group_ids(o, name, thr=0.5):
    g = o.vertex_groups.get(name)
    if g is None:
        return np.zeros(0, int)
    out = []
    for v in o.data.vertices:
        for gg in v.groups:
            if gg.group == g.index and gg.weight > thr:
                out.append(v.index)
    return np.array(out, int)


def _baked(o, bake):
    basis, shapes = meshops.shape_arrays(o)
    co = basis.copy()
    for n, w in bake.items():
        if n in shapes:
            co += w * (shapes[n] - basis)
    return basis, shapes, co


def build(rig, body, eyes, bake=None, step_deg=3.5, step_y_deg=1.75, log=K.log):
    bake = bake or {}
    _, _, bco = _baked(body, bake)
    bco = _world(body, bco)
    e_basis, e_shapes = meshops.shape_arrays(eyes)
    e_world = _world(eyes, e_basis)
    head_w = np.zeros(len(bco))
    hid = _group_ids(body, PRE + "Head", 0.3)
    head_w[hid] = 1
    faces = [list(p.vertices) for p in body.data.polygons]
    made = {}
    occ_V, occ_F, occ_U, occ_side = [], [], [], []
    wet_V, wet_F, wet_U, wet_N, wet_side = [], [], [], [], []
    report = {}
    centres = {}
    for side, bone in (("L", "LeftEye"), ("R", "RightEye")):
        ids = _group_ids(eyes, PRE + bone)
        if len(ids) < 20:
            log("EYEFX no eyeball verts for", bone)
            continue
        P = e_world[ids]
        c0, R = _fit_sphere(P)
        res = np.abs(np.linalg.norm(P - c0, axis=1) - R)
        c0, R = _fit_sphere(P[res < 0.0003]) if (res < 0.0003).sum() > 20 else (c0, R)
        # per-eye rigid morph deltas (rebuild_eyes keeps each eyeball rigid: mean delta)
        dk = {n: (sc[ids] - e_basis[ids]).mean(0) @ np.array(eyes.matrix_world)[:3, :3].T for n, sc in e_shapes.items()}
        cb = c0 + sum((w * dk[n] for n, w in bake.items() if n in dk), np.zeros(3))
        b = rig.data.bones[PRE + bone]
        fwd = K.nrm(np.array(rig.matrix_world @ b.tail_local) - np.array(rig.matrix_world @ b.head_local))
        up = K.nrm(np.array((0, 0, 1.0)) - fwd * fwd[2])
        rt = np.cross(fwd, up)
        theta_l = math.asin(min(0.98, 0.00575 / R)) if R > 0.006 else math.radians(28)

        def dirs(ax, ay):
            ax = np.asarray(ax, float); ay = np.asarray(ay, float)
            return (fwd[None] * (np.cos(ay) * np.cos(ax))[..., None] + rt[None] * (np.cos(ay) * np.sin(ax))[..., None]
                    + up[None] * np.sin(ay)[..., None])

        def bulge(d):
            th = np.arccos(np.clip(d @ fwd, -1, 1))
            return 0.0007 * np.maximum(0.0, np.cos(np.minimum(th / (theta_l * 1.1), 1.0) * math.pi / 2)) ** 1.2

        # ---- local face BVH around this eye (baked lids)
        near = (np.linalg.norm(bco - cb, axis=1) < 0.035) & (head_w > 0)
        fsel = [f for f in faces if near[f].all()]
        vids = sorted({v for f in fsel for v in f})
        remap = {v: i for i, v in enumerate(vids)}
        tree = BVHTree.FromPolygons([Vector(bco[v]) for v in vids], [[remap[v] for v in f] for f in fsel])
        # ---- coverage grid (fine): radial ray from the eyeball surface; a hit within 1 cm = under the lid
        g = math.radians(1.0)
        AX = np.arange(-math.radians(68), math.radians(68) + 1e-9, g)
        AY = np.arange(-math.radians(52), math.radians(52) + 1e-9, g)
        GX, GY = np.meshgrid(AX, AY)
        D = dirs(GX, GY)
        surf = cb + D * (R + bulge(D.reshape(-1, 3)).reshape(GX.shape) + 0.00005)[..., None]
        cov = np.zeros(GX.shape, bool)
        for iy in range(GX.shape[0]):
            for ix in range(GX.shape[1]):
                hit = tree.ray_cast(Vector(surf[iy, ix]), Vector(D[iy, ix]), 0.01)
                cov[iy, ix] = hit[0] is not None
        # aperture = uncovered region connected to the cornea centre
        iy0, ix0 = np.argmin(np.abs(AY)), np.argmin(np.abs(AX))
        if cov[iy0, ix0]:
            # eye centre covered (closed lids?): use the nearest open cell
            open_ = np.argwhere(~cov)
            if not len(open_):
                log("EYEFX", bone, "no aperture found")
                continue
            iy0, ix0 = open_[np.argmin(np.hypot(open_[:, 0] - iy0, open_[:, 1] - ix0))]
        ap = np.zeros_like(cov)
        stack = [(iy0, ix0)]
        while stack:
            y, x = stack.pop()
            if y < 0 or x < 0 or y >= cov.shape[0] or x >= cov.shape[1] or ap[y, x] or cov[y, x]:
                continue
            ap[y, x] = True
            stack += [(y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)]
        cols = np.where(ap.any(0))[0]
        if len(cols) < 6:
            log("EYEFX", bone, "aperture too small", len(cols))
            continue
        y_up = np.full(len(AX), np.nan); y_lo = np.full(len(AX), np.nan)
        for ix in cols:
            r_ = np.where(ap[:, ix])[0]
            y_up[ix] = AY[r_.max()]; y_lo[ix] = AY[r_.min()]
        ax_min, ax_max = AX[cols.min()], AX[cols.max()]
        report[bone] = {"R_mm": round(R * 1000, 2), "aperture_deg": [round(math.degrees(ax_min), 1), round(math.degrees(ax_max), 1),
                        round(math.degrees(np.nanmin(y_lo)), 1), round(math.degrees(np.nanmax(y_up)), 1)],
                        "open_cells": int(ap.sum())}
        apc = np.stack([GX[ap], GY[ap]], 1)          # aperture cells (angles)
        clc = np.stack([GX[~ap], GY[~ap]], 1)        # everything else counts as lid

        def interp_col(arr, ax):
            ok = ~np.isnan(arr)
            return np.interp(ax, AX[ok], arr[ok])

        # ---- occlusion shell grid
        s = math.radians(step_deg); sy_ = math.radians(step_y_deg)
        SX = np.arange(ax_min - 2 * s, ax_max + 2 * s + 1e-9, s)
        SY = np.arange(np.nanmin(y_lo) - 3 * sy_, np.nanmax(y_up) + 3 * sy_ + 1e-9, sy_)
        VX, VY = np.meshgrid(SX, SY)
        vx, vy = VX.ravel(), VY.ravel()
        # angular distances (metres on the eyeball) to the lid and to the aperture
        dl = np.sqrt(((vx[:, None] - clc[None, :, 0]) * np.cos(vy)[:, None]) ** 2 + (vy[:, None] - clc[None, :, 1]) ** 2).min(1) * R
        da = np.sqrt(((vx[:, None] - apc[None, :, 0]) * np.cos(vy)[:, None]) ** 2 + (vy[:, None] - apc[None, :, 1]) ** 2).min(1) * R
        inside = da < 0.5 * g * R
        up_m = interp_col(y_up, np.clip(vx, ax_min, ax_max))
        s_up = np.maximum(up_m - vy, 0.0) * R
        horiz = np.clip((vx - ax_min) / max(ax_max - ax_min, 1e-6), 0, 1)
        lash = 0.75 + 0.25 * np.sin(horiz * math.pi)              # upper-lid shadow strongest mid-lid (lashes, lid fold)
        o_up = np.exp(-s_up / 0.0023) * lash
        o_any = 0.5 * np.exp(-dl / 0.0009)
        corner = np.minimum(np.abs(vx - ax_min), np.abs(vx - ax_max)) * R
        o_cn = 0.4 * np.exp(-corner / 0.0024)
        occ = np.clip(np.maximum.reduce([o_up, o_any, o_cn]), 0, 1)
        occ = np.where(inside, occ, 1.0)
        Dv = dirs(vx, vy)
        th = np.arccos(np.clip(Dv @ fwd, -1, 1))
        rad = R + 0.00025 + 0.0007 * K.ss(math.radians(55), math.radians(30), th)
        pos = cb + Dv * rad[:, None]
        keep_v = da < 0.0012
        nx = len(SX)
        base = len(occ_V)
        vmap = -np.ones(len(vx), int)
        quads = []
        for iy in range(len(SY) - 1):
            for ix in range(nx - 1):
                q = [iy * nx + ix, iy * nx + ix + 1, (iy + 1) * nx + ix + 1, (iy + 1) * nx + ix]
                if keep_v[q].any() and not (occ[q] > 0.995).all():
                    quads.append(q)
        for q in quads:
            for v in q:
                if vmap[v] < 0:
                    vmap[v] = len(occ_V)
                    occ_V.append(pos[v] - (cb - c0))      # basis space (the export adds the baked eye delta back)
                    occ_U.append((float(occ[v]), 0.0))
                    occ_side.append(side)
            # winding: outward (towards the camera)
            occ_F.append([int(vmap[v]) for v in q])
        report[bone]["occ_quads"] = len(quads)
        # ---- tear meniscus strip along the lower lid
        ncol = 22
        a0 = ax_min + 0.04 * (ax_max - ax_min); a1 = ax_max - 0.04 * (ax_max - ax_min)
        wb = len(wet_V)
        for k in range(ncol):
            t = k / (ncol - 1)
            ax = a0 + (a1 - a0) * t
            lo = float(interp_col(y_lo, ax))
            endm = K.ss(0.0, 0.16, t) * K.ss(1.0, 0.84, t)
            for dy, m, tilt in ((-math.radians(0.8), 0.0, 55.0), (math.radians(1.6), 1.0, 28.0), (math.radians(5.5), 0.0, 0.0)):
                d = dirs(ax, lo + dy).reshape(3)
                p = cb + d * (R + float(bulge(d[None])[0]) + 0.0003)
                # normal: radial rolled towards the eye's up (concave fillet up onto the lid shelf)
                tang = K.nrm(up - d * (d @ up))
                nn = K.nrm(d * math.cos(math.radians(tilt)) + tang * math.sin(math.radians(tilt)))
                wet_V.append(p - (cb - c0)); wet_U.append((float(m * endm), 0.0)); wet_N.append(nn); wet_side.append(side)
        for k in range(ncol - 1):
            for r in range(2):
                a_ = wb + k * 3 + r
                wet_F.append([a_, a_ + 3, a_ + 4, a_ + 1])
        made[side] = dk
        centres[side] = c0
    if not occ_V:
        return None
    objs = []
    for name, V, F, U, S_, N in (("EyeOcclusion", occ_V, occ_F, occ_U, occ_side, None), ("EyeWet", wet_V, wet_F, wet_U, wet_side, wet_N)):
        old = bpy.data.objects.get(name)
        if old is not None:
            bpy.data.objects.remove(old, do_unlink=True)
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        vs = [bm.verts.new(Vector(p)) for p in V]
        uvl = bm.loops.layers.uv.new("UVMap")
        for f in F:
            fc = bm.faces.new([vs[i] for i in f])
            fc.smooth = True
            for lp, i in zip(fc.loops, f):
                lp[uvl].uv = U[i]
        bm.normal_update()
        bm.to_mesh(me); bm.free()
        # outward orientation check (towards the eye's forward): flip if most faces point inward
        o = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(o)
        co = K.get_co(o)
        fn = np.array([p.normal[:] for p in me.polygons])
        fc_ = np.array([co[list(p.vertices)].mean(0) for p in me.polygons])
        sides = np.array([S_[p.vertices[0]] for p in me.polygons])
        out = 0
        for sd, cen in centres.items():
            m = sides == sd
            if m.any():
                out += int(((fn[m] * (fc_[m] - cen)).sum(1) > 0).sum())
        if out < len(fn) / 2:
            bm = bmesh.new(); bm.from_mesh(me)
            bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
            bm.to_mesh(me); bm.free()
        if N is not None:
            me.normals_split_custom_set_from_vertices([tuple(n) for n in N])
        me.materials.append(bpy.data.materials.get(name) or bpy.data.materials.new(name))
        # Head-rigid, per-eye morph deltas from the eyeballs
        vg = o.vertex_groups.new(name=PRE + "Head")
        vg.add(list(range(len(V))), 1.0, "REPLACE")
        basis = K.get_co(o)
        shapes = {}
        Sarr = np.array(S_)
        for n in sorted({k for d in made.values() for k in d}):
            sc = basis.copy()
            for sd, dk in made.items():
                if n in dk:
                    sc[Sarr == sd] += dk[n]
            if np.abs(sc - basis).max() > 1e-6:
                shapes[n] = sc
        meshops.set_shapes(o, basis, shapes)
        o.parent = rig
        o.matrix_parent_inverse = rig.matrix_world.inverted()
        mod = o.modifiers.new("Armature", "ARMATURE"); mod.object = rig
        o.hide_render = True
        objs.append(o)
        report[name] = {"verts": len(V), "tris": sum(len(f) - 2 for f in F), "shapes": len(shapes)}
    log("EYEFX", report)
    return report
