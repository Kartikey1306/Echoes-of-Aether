"""Eyewear library: rigid glasses fitted to each hero's eyes, nose bridge and temples (procedural, no textures).

  blender -b --python blender/custom/eyewear.py -- <cid> [item,...]

Material slots: EyewearFrame, EyewearLens (tinted glass), Glow. Exported with the rigid-attachment transform (identity
local transform under mixamorig:Head in Unity). Suggested material values are written to the catalog entry.
"""
import bpy, os, sys, math, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from mathutils import Vector, Matrix
import common as C
import gear, studio
from gear import Part
from common import ss, nrm, nrm_rows

OUT_DIR = os.path.join(C.CUSTOM_OUT, "Eyewear")
THUMB_DIR = os.path.join(C.CUSTOM_OUT, "Thumbs")
PREV_DIR = os.path.join(C.PREVIEWS, "eyewear")


# ============================================================================= geometry helpers


def prof_rect(w, d, bevel=0.25):
    """Beveled rectangle profile (w along N, d along B), counter-clockwise."""
    a, b = w / 2, d / 2
    c = min(a, b) * bevel
    return np.array([(a, b - c), (a - c, b), (-a + c, b), (-a, b - c), (-a, -b + c), (-a + c, -b), (a - c, -b), (a, -b + c)])


def prof_circle(r, m=8):
    t = np.linspace(0, 2 * math.pi, m, endpoint=False)
    return np.stack([np.cos(t) * r, np.sin(t) * r], 1)


def sweep(part, P, N, B, prof, mat, closed=False, cap=True, scale=None):
    P = np.asarray(P, float); N = np.asarray(N, float); B = np.asarray(B, float)
    n, m = len(P), len(prof)
    sc = np.ones(n) if scale is None else np.asarray(scale, float)
    V = P[:, None, :] + (prof[None, :, 0, None] * N[:, None, :] + prof[None, :, 1, None] * B[:, None, :]) * sc[:, None, None]
    faces = []
    rng = range(n) if closed else range(n - 1)
    for i in rng:
        i2 = (i + 1) % n
        for j in range(m):
            j2 = (j + 1) % m
            faces.append([i * m + j, i * m + j2, i2 * m + j2, i2 * m + j])
    if cap and not closed:
        faces.append([j for j in range(m)][::-1])
        faces.append([(n - 1) * m + j for j in range(m)])
    part.add(V.reshape(-1, 3), faces, mat)


def path_frame(P, up=(0, 0, 1.0)):
    P = np.asarray(P, float)
    T = np.zeros_like(P)
    T[1:-1] = P[2:] - P[:-2]; T[0] = P[1] - P[0]; T[-1] = P[-1] - P[-2]
    T = nrm_rows(T)
    B = np.asarray(up, float) - T * (T @ np.asarray(up, float))[:, None]
    B = nrm_rows(B)
    N = np.cross(T, B)
    return T, N, B


def smooth_path(pts, n=40, iters=3):
    pts = np.asarray(pts, float)
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    arc = np.concatenate([[0], np.cumsum(seg)])
    t = np.linspace(0, arc[-1], n)
    P = np.stack([np.interp(t, arc, pts[:, k]) for k in range(3)], 1)
    for _ in range(iters):
        P[1:-1] = P[1:-1] * 0.5 + (P[:-2] + P[2:]) * 0.25
    return P


def outline(shape, w, h, n=48):
    """Closed lens outline in lens 2-D coords (u outward from the nose, v up), metres."""
    t = np.linspace(0, 2 * math.pi, n, endpoint=False)
    c, s = np.cos(t), np.sin(t)
    a, b = w / 2, h / 2
    if shape == "round":
        return np.stack([c * a, s * a], 1)
    if shape == "aviator":
        x = a * c
        y = np.where(s > 0, b * 0.82 * np.abs(s) ** 0.75, -b * np.abs(s) * (1.0 + 0.32 * np.clip(-c, 0, 1) - 0.12 * np.clip(c, 0, 1)))
        y = y + 0.06 * b * c  # top line rises slightly outward
        return np.stack([x, y], 1)
    if shape == "rect":
        e = 2 / 5.0
        return np.stack([a * np.sign(c) * np.abs(c) ** e, b * np.sign(s) * np.abs(s) ** e], 1)
    if shape == "wayfarer":
        e = 2 / 3.6
        x = a * np.sign(c) * np.abs(c) ** e
        y = b * np.sign(s) * np.abs(s) ** e
        x = x * (1 + 0.1 * (y / b))           # wider at the top
        y = y + 0.12 * b * np.clip(x / a, 0, 1) * (y > 0)
        return np.stack([x, y], 1)
    if shape == "cateye":
        e = 2 / 3.2
        x = a * np.sign(c) * np.abs(c) ** e
        y = b * np.sign(s) * np.abs(s) ** e
        wing = np.clip(x / a, 0, 1) ** 3 * np.clip(y / b + 0.2, 0, 1.2)
        y = y + 0.6 * b * wing
        x = x + 0.18 * a * wing
        y = np.where(y < 0, y * (1 - 0.25 * np.clip(x / a, 0, 1)), y)
        return np.stack([x, y], 1)
    raise ValueError(shape)


class Face:
    """Fitting landmarks from the reference body."""

    def __init__(self, ctx, rig):
        self.ctx = ctx
        L = ctx.L
        self.eyeL, self.eyeR = np.array(L["LeftEye"]), np.array(L["RightEye"])
        self.eye = (self.eyeL + self.eyeR) * 0.5
        eye_obj = next(o for o in bpy.data.objects if o.type == "MESH" and "high-poly" in o.name and not o.name.startswith("U_"))
        self.cornea_y = float(C.get_co(eye_obj)[:, 1].min())
        co = ctx.basis
        head = ctx.region["head"] > 0.5
        mid = head & (np.abs(co[:, 0]) < 0.004)
        def front_y(dz):
            s = mid & (np.abs(co[:, 2] - (self.eye[2] + dz)) < 0.003)
            return float(co[s, 1].min())
        self.bridge_y = front_y(0.0)
        self.bridge_y_up = front_y(0.008)
        self.tree = ctx.tree
        self.hc_y = self.eye[1] + 0.083

    def side_x(self, y, z, side=1):
        o = Vector((0.25 * side, y, z))
        hit, n, _, d = self.tree.ray_cast(o, Vector((-side, 0, 0)), 0.3)
        return abs(hit.x) if hit else 0.075

    def nose_point(self, x, z):
        """Nose surface point near (x, ., z) (ray from the front)."""
        o = Vector((x, self.cornea_y - 0.08, z))
        hit, n, _, d = self.tree.ray_cast(o, Vector((0, 1, 0)), 0.2)
        return np.array(hit) if hit else np.array((x, self.bridge_y, z))


# ============================================================================= builder


class Glasses:
    def __init__(self, F, cid, spec):
        self.F, self.cid, self.spec = F, cid, spec
        self.part = Part("eyewear")
        self.lens_part = Part("lens")

    def lens_frame(self, side, cx, cz, wrap, tilt):
        """Basis of a lens: centre c, U (outward), V (up), Fw (forward, away from the face)."""
        F = self.F
        y = F.cornea_y - self.spec.get("vertex", 0.0115)
        c = np.array((side * cx, y, cz))
        w = math.radians(wrap); t = math.radians(tilt)
        U = np.array((side * math.cos(w), math.sin(w), 0.0))
        Fw = np.array((side * math.sin(w) * -1, -math.cos(w), 0.0)) * -1
        Fw = nrm(np.cross(U, (0, 0, 1.0))) * (1 if side > 0 else -1)
        if Fw[1] > 0:
            Fw = -Fw
        V = np.array((0, 0, 1.0))
        # pantoscopic tilt: bottom towards the face (rotate V, Fw around U)
        V = nrm(V * math.cos(t) + Fw * math.sin(t))
        Fw = nrm(np.cross(V, U)) * (1 if side > 0 else -1)
        if Fw[1] > 0:
            Fw = -Fw
        return c, U, V, Fw

    def lens_pt(self, c, U, V, Fw, uv, base_r=0.09):
        r2 = (uv ** 2).sum(-1)
        return c + uv[..., :1] * U + uv[..., 1:2] * V - Fw * (r2 / (2 * base_r))[..., None]

    def add_lens(self, c, U, V, Fw, ol, thick=0.0019, rings=3, mat="EyewearLens", shrink=0.0, bevel=0.00045):
        """Curved lens filling outline ol (n,2): front and back surfaces plus a chamfered edge (the front/back rims
        are inset by `bevel`, the edge band sits at full size at mid thickness)."""
        part = self.lens_part if mat == "EyewearLens" else self.part
        n = len(ol)
        ol2 = ol * (1 - shrink)
        size = max(np.ptp(ol2[:, 0]), 1e-3)
        bi = 1.0 - 2 * bevel / size
        verts = [self.lens_pt(c, U, V, Fw, np.zeros(2))]
        for k in range(1, rings + 1):
            f = k / rings * (bi if k == rings else 1.0)
            for j in range(n):
                verts.append(self.lens_pt(c, U, V, Fw, ol2[j] * f))
        verts = np.array(verts)
        faces = []
        for j in range(n):
            faces.append([0, 1 + j, 1 + (j + 1) % n])
        for k in range(1, rings):
            for j in range(n):
                a = 1 + (k - 1) * n + j; b = 1 + (k - 1) * n + (j + 1) % n
                faces.append([a, a + n, b + n, b])
        front = verts + Fw * thick * 0.5
        back = verts - Fw * thick * 0.5
        mid = np.array([self.lens_pt(c, U, V, Fw, ol2[j]) for j in range(n)])
        nv = len(verts)
        allv = np.vstack([front, back, mid])
        allf = [f[::-1] for f in faces] + [[i + nv for i in f] for f in faces]
        rim0 = 1 + (rings - 1) * n
        m0 = 2 * nv
        for j in range(n):
            a = rim0 + j; b = rim0 + (j + 1) % n
            ma, mb = m0 + j, m0 + (j + 1) % n
            allf.append([a, b, mb, ma])
            allf.append([ma, mb, b + nv, a + nv])
        part.add(allv, allf, mat)
        return np.array([self.lens_pt(c, U, V, Fw, ol[j]) for j in range(n)])

    def hinge(self, p, up, out, metal=True):
        """Barrel hinge: knuckle cylinder along `up` with a small mounting plate (EyewearFrame)."""
        up = nrm(up); out = nrm(out)
        P = np.array([p - up * 0.0042, p + up * 0.0042])
        T, N, B = path_frame(P, out)
        sweep(self.part, P, N, B, prof_circle(0.0016, 10), "EyewearFrame", closed=False)
        for dz in (-0.0022, 0.0022):
            q = p + up * dz
            Q = np.array([q - out * 0.0002, q + out * 0.0026])
            T, N, B = path_frame(Q, up)
            sweep(self.part, Q, N, B, prof_rect(0.0018, 0.003, 0.4), "EyewearFrame", closed=False)

    def rim(self, pts, c, Fw, prof, mat="EyewearFrame", scale=None):
        P = np.asarray(pts)
        T = np.roll(P, -1, 0) - np.roll(P, 1, 0)
        T = nrm_rows(T)
        B = np.broadcast_to(Fw, P.shape).copy()
        B = nrm_rows(B - T * (T * B).sum(1, keepdims=True))
        N = np.cross(T, B)
        # N should point outward from the lens centre
        sgn = np.sign(((P - c) * N).sum(1, keepdims=True)); sgn[sgn == 0] = 1
        N = N * sgn
        sweep(self.part, P, N, B, prof, mat, closed=True, scale=scale)
        return N

    def bar(self, pts, prof, mat="EyewearFrame", up=(0, 0, 1.0), n=None, scale=None):
        P = smooth_path(pts, n or max(8, len(pts) * 6), 2)
        T, N, B = path_frame(P, up)
        sweep(self.part, P, N, B, prof, mat, closed=False, scale=scale)
        return P

    def temple(self, side, hinge, prof, z_drop=0.0, clear=0.004, tip=True, mat="EyewearFrame", tip_mat=None):
        """Temple arm from the hinge back along the side of the head, over the ear, then down behind it."""
        F = self.F
        ys = np.linspace(hinge[1] + 0.006, F.hc_y + 0.012, 9)
        pts = [hinge]
        for i, y in enumerate(ys):
            z = hinge[2] + (F.eye[2] + 0.009 - hinge[2]) * min(1, (i + 1) / 5) - z_drop * (i / 8)
            x = max(F.side_x(y, z, side), F.side_x(y, z - 0.004, side) - 0.002) + clear
            x = max(x, abs(hinge[0]) - 0.003 * i * 0)
            pts.append(np.array((side * x, y, z)))
        if tip:
            last = pts[-1]
            for dy, dz, dx in ((0.012, -0.006, -0.002), (0.02, -0.018, -0.004), (0.024, -0.032, -0.006)):
                pts.append(np.array((last[0] + side * dx, last[1] + dy, last[2] + dz)))
        P = smooth_path(np.array(pts), 30, 2)
        T, N, B = path_frame(P, (0, 0, 1.0))
        # profile: tall flat bar; temple tip thickens behind the ear
        sc = 1.0 + 0.45 * ss(0.72, 0.95, np.linspace(0, 1, len(P))) if tip else None
        sweep(self.part, P, N, B, prof, mat, closed=False, scale=sc)
        return P


def fit(F, spec):
    """Lens centres / height for a hero: lens width w, bridge gap -> centre x."""
    w = spec["w"]
    cx = spec.get("bridge", 0.018) / 2 + w / 2
    cz = F.eye[2] + spec.get("dz", 0.003)
    return cx, cz


SPECS = {
    "aviator": dict(label="Aviator", shape="aviator", w=0.056, h=0.048, bridge=0.017, wrap=7, tilt=8, frame="wire", fw=0.0016,
                    frame_col="#b89a5a", metal=1.0, smooth=0.85, lens="#3a4a3c", lens_a=0.72, glow=None),
    "round_wire": dict(label="Round Wire", shape="round", w=0.046, h=0.046, bridge=0.02, wrap=4, tilt=6, frame="wire", fw=0.0013,
                       frame_col="#c9ccd1", metal=1.0, smooth=0.85, lens="#a9c6d8", lens_a=0.22, glow=None),
    "rect_smart": dict(label="Smart Rectangles", shape="rect", w=0.054, h=0.036, bridge=0.018, wrap=6, tilt=7, frame="acetate", fw=0.0045,
                       fd=0.0042, frame_col="#20242a", metal=0.0, smooth=0.82, lens="#6fd8ff", lens_a=0.18, glow="#00e5ff", hud=True),
    "cyber_visor": dict(label="Cyber Visor", shape="visor", w=0.15, h=0.042, frame_col="#1b1e24", metal=0.6, smooth=0.75, lens="#0aa8ff",
                        lens_a=0.55, glow="#00f0ff"),
    "shades_led": dict(label="LED Shades", shape="wayfarer", w=0.055, h=0.04, bridge=0.017, wrap=8, tilt=8, frame="acetate", fw=0.0055,
                       fd=0.006, frame_col="#0b0b0d", metal=0.0, smooth=0.86, lens="#050608", lens_a=0.92, glow="#ff2bd6", led=True),
    "monocle_hud": dict(label="Monocle HUD", shape="round", w=0.04, h=0.04, frame="tech", fw=0.0045, fd=0.006, frame_col="#2a2f37",
                        metal=0.8, smooth=0.7, lens="#7ff7ff", lens_a=0.25, glow="#00e5ff", hud=True),
    "tactical_goggles": dict(label="Tactical Goggles", shape="rect", w=0.052, h=0.04, bridge=0.016, wrap=13, tilt=6, frame="acetate", fw=0.009,
                             fd=0.013, frame_col="#2b2f26", metal=0.0, smooth=0.4, lens="#ffb02e", lens_a=0.5, glow="#00e5ff", led=True),
    "cat_eye_tech": dict(label="Cat-Eye Tech", shape="cateye", w=0.054, h=0.04, bridge=0.017, wrap=8, tilt=8, frame="acetate", fw=0.005,
                         fd=0.0048, frame_col="#2a1630", metal=0.0, smooth=0.86, lens="#d27bff", lens_a=0.3, glow="#ff2bd6", wing=True),
}
ITEMS = {"kael": ["aviator", "round_wire", "rect_smart", "cyber_visor", "shades_led", "monocle_hud", "tactical_goggles"],
         "lyra": ["aviator", "round_wire", "rect_smart", "cyber_visor", "shades_led", "monocle_hud", "cat_eye_tech", "tactical_goggles"]}


def build(F, cid, iid):
    sp = dict(SPECS[iid])
    if cid == "lyra" and sp["shape"] != "visor":
        sp["w"] *= 0.95; sp["h"] *= 0.95
    g = Glasses(F, cid, sp)
    if sp["shape"] == "visor":
        return build_visor(F, g, sp)
    if iid == "monocle_hud":
        return build_monocle(F, g, sp)
    cx, cz = fit(F, sp)
    ol = outline(sp["shape"], sp["w"], sp["h"])
    prof = prof_circle(sp["fw"] / 2, 8) if sp["frame"] == "wire" else prof_rect(sp["fw"], sp.get("fd", sp["fw"]), 0.35)
    inner, outer, tops = {}, {}, {}
    for side in (1, -1):
        olS = ol.copy()
        if side < 0:
            pass
        c, U, V, Fw = g.lens_frame(side, cx, cz, sp["wrap"], sp["tilt"])
        rimpts = g.add_lens(c, U, V, Fw, olS, shrink=0.0)
        g.rim(rimpts + Fw * 0.0003, c, Fw, prof)
        uv = olS
        inner[side] = g.lens_pt(c, U, V, Fw, uv[np.argmin(uv[:, 0] - 0.4 * np.abs(uv[:, 1]))])
        top_i = np.argmax(uv[:, 1] - 0.3 * uv[:, 0])
        tops[side] = g.lens_pt(c, U, V, Fw, uv[top_i])
        # hinge on the outer rim, upper third
        hi = np.argmax(uv[:, 0] + 0.6 * uv[:, 1])
        hinge = g.lens_pt(c, U, V, Fw, uv[hi]) + U * sp["fw"] * 0.6 + Fw * -0.002
        outer[side] = hinge
        if sp.get("hud"):
            for k, (r0, a0, a1) in enumerate(((0.012, 30, 140), (0.016, 200, 290))):
                if side > 0:
                    th = np.radians(np.linspace(a0, a1, 18))
                    pts = [g.lens_pt(c, U, V, Fw, np.array((r0 * math.cos(t) + 0.004, r0 * math.sin(t) + 0.002))) - Fw * 0.0012 for t in th]
                    g.bar(pts, prof_rect(0.0007, 0.0003, 0.2), "Glow", up=Fw)
            if side > 0:
                for k in range(3):
                    a = np.array((0.008 + k * 0.004, -0.008)); b = a + np.array((0.0, -0.0025 - 0.002 * k))
                    g.bar([g.lens_pt(c, U, V, Fw, a) - Fw * 0.0012, g.lens_pt(c, U, V, Fw, b) - Fw * 0.0012], prof_rect(0.0012, 0.0003, 0.2), "Glow", up=Fw)
        if sp.get("led"):
            ti = np.where(uv[:, 1] > sp["h"] * 0.25)[0]
            ti = ti[np.argsort(np.arctan2(uv[ti, 1], uv[ti, 0]))]
            pts = [g.lens_pt(c, U, V, Fw, uv[j] + np.array((0, 0.0015))) - Fw * (sp.get("fd", 0.004) * 0.5 + 0.0003) for j in ti]
            g.bar(pts, prof_rect(0.0012, 0.0005, 0.2), "Glow", up=V)
        if sp.get("wing"):
            wi = np.where((uv[:, 0] > sp["w"] * 0.15) & (uv[:, 1] > 0))[0]
            wi = wi[np.argsort(uv[wi, 0])]
            pts = [g.lens_pt(c, U, V, Fw, uv[j] * 1.0 + np.array((0, 0.0005))) - Fw * (sp.get("fd", 0.004) * 0.5 + 0.0003) for j in wi]
            g.bar(pts, prof_rect(0.001, 0.0005, 0.2), "Glow", up=V)
            # metal tip accent on the wing
            j = wi[-1]
            p0 = g.lens_pt(c, U, V, Fw, uv[j])
            g.bar([p0 - U * 0.004, p0 + U * 0.004], prof_rect(0.003, 0.0055, 0.3), "EyewearFrame")
        # temple arm
        tprof = prof_rect(0.0016, 0.0042 if sp["frame"] != "wire" else 0.0014, 0.4) if sp["frame"] != "wire" else prof_circle(0.0008, 8)
        # endpiece connecting rim and hinge
        g.bar([g.lens_pt(c, U, V, Fw, uv[hi]), hinge], prof_rect(0.003, 0.004, 0.3) if sp["frame"] != "wire" else prof_circle(0.001, 8))
        arm = g.temple(side, hinge, tprof, clear=0.0045)
        g.hinge(hinge + Fw * -0.0005, V, U * side * 0 + nrm(U), metal=True)
        if sp["frame"] == "wire":
            # acetate ear tips
            tipP = arm[-10:]
            T, N, B = path_frame(tipP)
            sweep(g.part, tipP, N, B, prof_rect(0.0032, 0.0045, 0.5), "EyewearFrame")
        if sp.get("led"):
            P2 = arm[2:16]
            T, N, B = path_frame(P2)
            sweep(g.part, P2 + N * 0.0009 * side * 0 + B * 0.0, N, B, prof_rect(0.0018, 0.0011, 0.2) + np.array((0.0009 * 0, 0.0)), "Glow")
        if cid and sp.get("hud") and side > 0:
            # camera / sensor module on the hinge
            T, N, B = path_frame(arm[1:5])
            sweep(g.part, arm[1:5] + N[:1] * 0.0, N, B, prof_rect(0.0045, 0.008, 0.4), "EyewearFrame")
            g.bar([arm[2] + B[1] * 0.0045 + N[1] * 0.0005, arm[3] + B[2] * 0.0045 + N[2] * 0.0005], prof_rect(0.0012, 0.0006, 0.2), "Glow")
    # bridge(s)
    a, b = inner[1], inner[-1]
    mid = (a + b) / 2 + np.array((0, -0.001, 0.0045 if sp["frame"] == "wire" else 0.003))
    nose = F.nose_point(0.0, mid[2])
    if mid[1] > nose[1] - 0.0025:
        mid[1] = nose[1] - 0.0025
    g.bar([a, (a + mid) / 2 + np.array((0, 0, 0.001)), mid, (b + mid) / 2 + np.array((0, 0, 0.001)), b], prof if sp["frame"] == "wire" else prof_rect(sp["fw"] * 0.9, sp.get("fd", 0.004), 0.35))
    if sp["shape"] == "aviator":
        ta, tb = tops[1], tops[-1]
        midt = (ta + tb) / 2 + np.array((0, -0.0005, 0.002))
        g.bar([ta, midt, tb], prof_circle(0.0008, 8))
    if sp["frame"] != "wire":
        # moulded acetate nose pads on the inner rims
        for side in (1, -1):
            a_ = inner[side] + np.array((0, 0.0015, -0.006))
            b_ = a_ + np.array((-side * 0.0012, 0.003, -0.008))
            g.bar([a_, b_], prof_rect(0.0032, 0.0022, 0.5), "EyewearFrame", up=(side * 1.0, 0, 0))
    if sp["frame"] == "wire":
        # nose pads on wire arms
        for side in (1, -1):
            npt = F.nose_point(side * 0.0075, F.eye[2] - 0.006)
            pad_c = npt + np.array((side * 0.0025, -0.0012, 0))
            anchor = inner[side] + np.array((0, 0.001, -0.003))
            g.bar([anchor, anchor + np.array((0, 0.004, -0.002)), pad_c], prof_circle(0.0005, 6))
            # pad: small rounded plate facing the nose
            n = nrm(np.array((side * 1.0, -0.6, 0)))
            T = np.array((0, 0, 1.0))
            Bv = nrm(np.cross(n, T))
            ell = np.array([pad_c + T * 0.0055 * math.cos(t) * 0.5 + Bv * 0.0035 * math.sin(t) * 0.5 for t in np.linspace(0, 2 * math.pi, 12, endpoint=False)])
            g.part.add(np.vstack([ell, ell + n * 0.0012]), [list(range(12))[::-1], [12 + i for i in range(12)]] +
                       [[i, (i + 1) % 12, 12 + (i + 1) % 12, 12 + i] for i in range(12)], "EyewearLens")
    return g


def build_visor(F, g, sp):
    """Wraparound shield over both eyes on a cylinder around the face; neon strips on the top/bottom edges."""
    yc = F.hc_y + 0.004
    R = yc - (F.cornea_y - 0.016)
    zc = F.eye[2] + 0.004
    h = sp["h"]
    ang = np.radians(np.linspace(-78, 78, 61))
    vs = np.linspace(-0.5, 0.5, 9)

    def P_(a, v):
        r = R + 0.004 * (1 - math.cos(a)) * 0 + 0.006 * (abs(math.degrees(a)) / 78) ** 2
        z = zc + v * h * (1 - 0.25 * (abs(math.degrees(a)) / 78) ** 2) + 0.004 * math.cos(a) * (v > 0)
        # nose cut-out at the bottom centre
        if v < 0 and abs(a) < math.radians(12):
            z = max(z, zc - h * 0.5 + 0.017 * (1 - abs(a) / math.radians(12)) ** 1.5 * 1.0)
        return np.array((math.sin(a) * r, yc - math.cos(a) * r, z))
    grid = np.array([[P_(a, v) for v in vs] for a in ang])
    na, nv = grid.shape[:2]
    Fw = nrm_rows((grid - np.array((0, yc, 0))) * np.array((1, 1, 0)))
    thick = 0.0018
    verts = np.vstack([(grid + Fw * thick / 2).reshape(-1, 3), (grid - Fw * thick / 2).reshape(-1, 3)])
    faces = []
    off = na * nv
    for i in range(na - 1):
        for j in range(nv - 1):
            a = i * nv + j
            faces.append([a, a + nv, a + nv + 1, a + 1])
            faces.append([off + a, off + a + 1, off + a + nv + 1, off + a + nv])
    for i in range(na - 1):
        for j in (0, nv - 1):
            a = i * nv + j
            faces.append([a, off + a, off + a + nv, a + nv] if j == 0 else [a, a + nv, off + a + nv, off + a])
    for j in range(nv - 1):
        for i in (0, na - 1):
            a = i * nv + j
            faces.append([a, a + 1, off + a + 1, off + a] if i == 0 else [a, off + a, off + a + 1, a + 1])
    g.lens_part.add(verts, faces, "EyewearLens")
    # frame band along the top edge, thin chrome along the bottom, neon strips
    top = grid[:, -1] + Fw[:, -1] * 0.0
    bot = grid[:, 0]
    g.bar(top + np.array((0, 0, 0.0018)), prof_rect(0.0045, 0.0055, 0.4), "EyewearFrame", up=(0, 0, 1.0), n=80)
    g.bar(top + Fw[:, -1] * 0.0032 + np.array((0, 0, 0.0005)), prof_rect(0.0014, 0.0008, 0.3), "Glow", up=(0, 0, 1.0), n=80)
    g.bar(bot + Fw[:, 0] * 0.0016, prof_rect(0.0011, 0.0009, 0.3), "Glow", up=(0, 0, 1.0), n=80)
    # side pods + arms
    for side in (1, -1):
        e = grid[-1 if side > 0 else 0]
        pod_c = e.mean(0)
        hinge = pod_c + np.array((side * 0.002, 0.004, 0.006))
        g.bar([e[2], e[-1] + np.array((0, 0, 0.002))], prof_rect(0.006, 0.006, 0.4), "EyewearFrame", up=(0, 1.0, 0))
        g.temple(side, hinge, prof_rect(0.0022, 0.006, 0.4), clear=0.005, tip=True)
        g.bar([pod_c + np.array((side * 0.0035, 0.0, -0.01)), pod_c + np.array((side * 0.0035, 0.0, 0.012))], prof_rect(0.0015, 0.001, 0.2), "Glow",
              up=(0, 1.0, 0))
    return g


def build_monocle(F, g, sp):
    side = 1  # over the character's left eye (Kael's cyberware temple is on the left)
    cx = abs(F.eyeL[0]) + 0.002
    cz = F.eye[2] + 0.002
    c, U, V, Fw = g.lens_frame(side, cx, cz, 4, 4)
    ol = outline("round", sp["w"], sp["h"])
    rimpts = g.add_lens(c, U, V, Fw, ol)
    g.rim(rimpts, c, Fw, prof_rect(0.0045, 0.006, 0.4))
    g.rim(g.lens_pt(c, U, V, Fw, ol * 1.06) + Fw * 0.002, c, Fw, prof_rect(0.0012, 0.0016, 0.3), mat="Glow")
    # HUD arcs on the lens back
    for r0, a0, a1 in ((0.011, 20, 160), (0.0145, 200, 330), (0.006, 0, 300)):
        th = np.radians(np.linspace(a0, a1, 22))
        pts = [g.lens_pt(c, U, V, Fw, np.array((r0 * math.cos(t), r0 * math.sin(t)))) - Fw * 0.0012 for t in th]
        g.bar(pts, prof_rect(0.0006, 0.0003, 0.2), "Glow", up=Fw)
    for k in range(2):
        a = np.array((-0.017 + 0.034 * k, 0.0)); b = a + np.array((0.006 * (1 - 2 * k), 0))
        g.bar([g.lens_pt(c, U, V, Fw, a) - Fw * 0.0012, g.lens_pt(c, U, V, Fw, b) - Fw * 0.0012], prof_rect(0.0007, 0.0003, 0.2), "Glow", up=Fw)
    # mount: arm from the rim's outer edge back to an ear clip with a sensor pod at the temple
    hinge = g.lens_pt(c, U, V, Fw, np.array((sp["w"] * 0.5 + 0.003, 0.004)))
    g.bar([g.lens_pt(c, U, V, Fw, np.array((sp["w"] * 0.5, 0.002))), hinge], prof_rect(0.004, 0.005, 0.4))
    arm = g.temple(side, hinge, prof_rect(0.0022, 0.0055, 0.4), clear=0.005)
    T, N, B = path_frame(arm[4:11])
    sweep(g.part, arm[4:11] + N * 0.004, N, B, prof_rect(0.007, 0.011, 0.45), "EyewearFrame")
    g.bar([arm[5] + N[1] * 0.0076 + B[1] * 0.002, arm[9] + N[5] * 0.0076 + B[5] * 0.002], prof_rect(0.0012, 0.0008, 0.2), "Glow")
    return g


def finish(g, name):
    objs = []
    for p in (g.part, g.lens_part):
        if p.F:
            objs.append(p.build(mat_order=None, max_edge=None))
    obj = gear.join(objs, name)
    # ensure slot order EyewearFrame, EyewearLens, Glow
    me = obj.data
    order = ["EyewearFrame", "EyewearLens", "Glow"]
    have = [m.name for m in me.materials]
    idx = np.empty(len(me.polygons), np.int32); me.polygons.foreach_get("material_index", idx)
    names = np.array([have[i] for i in idx])
    me.materials.clear()
    for n in order:
        if n in have:
            me.materials.append(gear.get_mat(n))
    newn = [m.name for m in me.materials]
    me.polygons.foreach_set("material_index", np.array([newn.index(n) for n in names], np.int32))
    # flat shading for crisp frames, auto-smooth via custom normals is not needed
    for p in me.polygons:
        p.use_smooth = True
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    try:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(40))
    except Exception:
        pass
    obj.select_set(False)
    return obj


def preview_mats(obj, sp):
    fr = studio.flat(f"pv_frame_{obj.name}", sp["frame_col"], 1 - sp["smooth"], sp["metal"])
    ln = bpy.data.materials.new(f"pv_lens_{obj.name}")
    ln.use_nodes = True
    b = ln.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*C.srgb2lin(C.hx(sp["lens"])), 1)
    b.inputs["Roughness"].default_value = 0.04
    b.inputs["Alpha"].default_value = sp["lens_a"]
    b.inputs["Specular IOR Level"].default_value = 0.9
    if hasattr(ln, "surface_render_method"):
        ln.surface_render_method = "BLENDED"
    gl = studio.flat(f"pv_glow_{obj.name}", sp.get("glow") or "#00e5ff", 0.3, 0.0, (sp.get("glow") or "#00e5ff", 9.0))
    m = {"EyewearFrame": fr, "EyewearLens": ln, "Glow": gl}
    for i, mm in enumerate(obj.data.materials):
        obj.data.materials[i] = m[mm.name]


def restore_mats(obj):
    """Back to the Unity slot names after the preview materials."""
    for i, mm in enumerate(obj.data.materials):
        n = mm.name
        k = ("EyewearFrame" if n.startswith("pv_frame") or "EyewearFrame" in n else
             "EyewearLens" if n.startswith("pv_lens") or "EyewearLens" in n else "Glow")
        obj.data.materials[i] = gear.get_mat(k)


def main():
    a = C.args()
    cid = a[0]
    sel = a[1].split(",") if len(a) > 1 and not a[1].startswith("--") else ITEMS[cid]
    rig, body = C.load_ref(cid)
    ctx = gear.Ctx(body, rig, C.HEROES[cid]["name"])
    F = Face(ctx, rig)
    C.log("face", "cornea_y", round(F.cornea_y, 4), "bridge_y", round(F.bridge_y, 4), "eye", F.eye.round(4))
    studio.hero_materials(cid)
    if "U_Visor" in bpy.data.objects:      # Unity hides Giva's built-in visor while catalog eyewear is worn
        bpy.data.objects["U_Visor"].hide_render = True
    import hair_preview
    hair_preview.load_default_hair(cid)
    os.makedirs(OUT_DIR, exist_ok=True); os.makedirs(PREV_DIR, exist_ok=True); os.makedirs(THUMB_DIR, exist_ok=True)
    os.makedirs(os.path.join(C.CACHE, "catalog", "eyewear"), exist_ok=True)
    M = C.rigid_matrix(cid)
    eye = Vector(F.eye)
    for iid in sel:
        t0 = time.time()
        sp = dict(SPECS[iid])
        g = build(F, cid, iid)
        obj = finish(g, f"{cid}_{iid}")
        ntri = C.tris(obj)
        preview_mats(obj, sp)
        aim = eye + Vector((0, 0.01, 0.0))
        studio.world_and_lights(aim, 0.6, rim=1.0, yaw=28)
        studio.camera(studio.view(aim, 28, 4, 0.62), aim, 70)
        thumb = os.path.join(THUMB_DIR, f"eyewear_{cid}_{iid}.png")
        studio.render(thumb, 512, 256)
        for tag, yaw, pitch, dist in (("q34", 28, 4, 0.62), ("front", 0, 2, 0.6), ("side", 82, 3, 0.55)):
            studio.world_and_lights(aim, 0.6, rim=1.0, yaw=yaw)
            studio.camera(studio.view(aim, yaw, pitch, dist), aim, 70)
            studio.render(os.path.join(PREV_DIR, f"{cid}_{iid}_{tag}.png"), 512)
        restore_mats(obj)
        # export: rigid, identity local transform under the Head bone
        me = obj.data
        me.transform(M)
        me.update()
        path = os.path.join(OUT_DIR, f"{cid}_{iid}.fbx")
        C.export_fbx(path, [obj])
        e = {"id": iid, "label": sp["label"], "hero": cid, "file": f"Eyewear/{cid}_{iid}", "kind": "rigid", "bone": "mixamorig:Head",
             "thumb": f"Thumbs/eyewear_{cid}_{iid}", "localPos": [0, 0, 0], "localRot": [0, 0, 0], "tris": ntri,
             "materials": {"EyewearFrame": {"tint": sp["frame_col"]},
                           "EyewearLens": {"lensTint": sp["lens"], "lensAlpha": sp["lens_a"]}},
             "frame": {"metallic": sp["metal"], "smoothness": sp["smooth"]}}
        if sp.get("glow"):
            e["materials"]["Glow"] = {"color": sp["glow"], "intensity": 3.0}
        if cid == "lyra":
            e["hides"] = ["Visor"]
        with open(os.path.join(C.CACHE, "catalog", "eyewear", f"{cid}_{iid}.json"), "w") as f:
            json.dump(e, f, indent=1)
        C.log(iid, "tris", ntri, "s", round(time.time() - t0, 1))
        bpy.data.objects.remove(obj, do_unlink=True)
    import catalog
    catalog.merge()
    C.log("done")


if __name__ == "__main__":
    main()
