"""Eyewear v2: real-proportion glasses fitted to the v2 hero heads (replaces eyewear.py's builder).

  blender -b --python blender/custom/eyewear2.py -- <cid> [item,...] [--no-export]

Fitting (per hero, from the reference body):
  * frame front width from the face width at the temples; lens width = what remains after bridge and endpieces;
  * lens plane: pantoscopic tilt + face-form wrap, then pushed forward until every rim / lens point clears the face
    (brow ridge, cheeks, nose) by >= 3 mm and the vertex distance to the cornea is >= 11 mm;
  * nose pads (metal) or moulded pads (acetate) touch the sides of the nose;
  * ears are found by scanning the side profile of the head (bulge over the skull); temples run back along the head,
    sit in the groove on top of the ear root and bend down behind the ear.
Slots: EyewearFrame, EyewearLens, Glow. Rigid, exported for an identity transform under mixamorig:Head.
"""
import bpy, os, sys, math, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from mathutils import Vector
import common as C
import gear, studio
from gear import Part
from common import ss, nrm, nrm_rows
from eyewear import sweep, path_frame, smooth_path, prof_circle, finish, preview_mats, restore_mats, OUT_DIR, THUMB_DIR, PREV_DIR

R_ = math.radians


def prof_round_rect(w, d, r=0.45, n=4):
    """Rounded rectangle profile (w along N, d along B), corner radius r*min(w,d)/2, n points per corner."""
    a, b = w / 2, d / 2
    rr = min(a, b) * r * 2 * 0.5
    pts = []
    for cx, cy, a0 in ((a - rr, b - rr, 0), (-a + rr, b - rr, 90), (-a + rr, -b + rr, 180), (a - rr, -b + rr, 270)):
        for k in range(n):
            t = math.radians(a0 + 90 * k / (n - 1))
            pts.append((cx + rr * math.cos(t), cy + rr * math.sin(t)))
    return np.array(pts)


def lens_outline(shape, w, h, n=40):
    t = np.linspace(0, 2 * math.pi, n, endpoint=False)
    c, s = np.cos(t), np.sin(t)
    a, b = w / 2, h / 2
    if shape == "round":
        e = 2 / 2.15
        return np.stack([a * np.sign(c) * np.abs(c) ** e, b * np.sign(s) * np.abs(s) ** e], 1)
    if shape == "aviator":     # teardrop: flat-ish top, deep rounded bottom towards the nose
        x = a * c
        y = np.where(s > 0, b * 0.78 * np.abs(s) ** 0.55, -b * np.abs(s) ** 0.9 * (1.08 + 0.22 * np.clip(-c, 0, 1) - 0.16 * np.clip(c, 0, 1)))
        y = y + 0.05 * b * c
        return np.stack([x, y], 1)
    if shape == "rect":
        e = 2 / 4.2
        return np.stack([a * np.sign(c) * np.abs(c) ** e, b * np.sign(s) * np.abs(s) ** e * (1 - 0.06 * np.clip(-c, 0, 1))], 1)
    if shape == "wayfarer":    # trapezoid: wider top, outer top corner lifted
        e = 2 / 3.6
        x = a * np.sign(c) * np.abs(c) ** e
        y = b * np.sign(s) * np.abs(s) ** e
        x = x * (1 + 0.08 * (y / b))
        y = y + 0.1 * b * np.clip(x / a, 0, 1) * (y > 0)
        return np.stack([x, y], 1)
    if shape == "cateye":
        e = 2 / 3.0
        x = a * np.sign(c) * np.abs(c) ** e
        y = b * np.sign(s) * np.abs(s) ** e
        wing = np.clip(x / a, 0, 1) ** 2.5 * np.clip(y / b + 0.25, 0, 1.25)
        y = y + 0.42 * b * wing
        x = x + 0.12 * a * wing
        y = np.where(y < 0, y * (1 - 0.22 * np.clip(x / a, 0, 1)), y)
        return np.stack([x, y], 1)
    raise ValueError(shape)


class FaceFit:
    def __init__(self, ctx):
        self.ctx = ctx
        L = ctx.L
        self.eyeL, self.eyeR = np.array(L["LeftEye"]), np.array(L["RightEye"])
        self.eye = (self.eyeL + self.eyeR) * 0.5
        eo = next(o for o in bpy.data.objects if o.type == "MESH" and "high-poly" in o.name and not o.name.startswith("U_"))
        self.cornea_y = float(C.get_co(eo)[:, 1].min())
        self.tree = ctx.tree
        self.ear = {s: self.ear_scan(s) for s in (1, -1)}

    def side_x(self, y, z, side=1):
        hit, n, _, d = self.tree.ray_cast(Vector((0.3 * side, y, z)), Vector((-side, 0, 0)), 0.35)
        return abs(hit.x) if hit else 0.07

    def front_y(self, x, z):
        hit, n, _, d = self.tree.ray_cast(Vector((x, self.eye[1] - 0.25, z)), Vector((0, 1, 0)), 0.4)
        return hit.y if hit else self.cornea_y

    def nose_pt(self, x, z):
        hit, n, _, d = self.tree.ray_cast(Vector((x, self.eye[1] - 0.25, z)), Vector((0, 1, 0)), 0.4)
        return (np.array(hit), np.array(n)) if hit else (np.array((x, self.cornea_y, z)), np.array((0, -1.0, 0)))

    def clearance(self, P):
        """Signed distance of points to the head surface (positive outside)."""
        out = np.zeros(len(P))
        for i, p in enumerate(P):
            hit, n, _, d = self.tree.find_nearest(Vector(p), 0.1)
            out[i] = (Vector(p) - hit).dot(n) if hit is not None else 0.1
        return out

    def skull_in(self, y, z, side=1):
        """Skull surface from inside the head (ignores the ear flap)."""
        hit, n, _, d = self.tree.ray_cast(Vector((0.0, y, z)), Vector((side, 0, 0)), 0.2)
        return abs(hit.x) if hit else self.side_x(y, z, side)

    def ear_scan(self, side):
        """The ear is a narrow bump on the side profile: it sticks out beyond the skull on both sides along y."""
        ys = self.eye[1] + np.arange(0.03, 0.13, 0.0025)
        zs = self.eye[2] + np.arange(-0.05, 0.035, 0.0025)
        X = np.array([[self.side_x(y, z, side) for y in ys] for z in zs])
        k = 5
        bmax = np.full_like(X, -1.0); bmean = np.full_like(X, -1.0)
        bmax[:, k:-k] = X[:, k:-k] - np.maximum(X[:, :-2 * k], X[:, 2 * k:])
        bmean[:, k:-k] = X[:, k:-k] - 0.5 * (X[:, :-2 * k] + X[:, 2 * k:])
        core = bmax > 0.003
        m = np.zeros_like(core)
        if core.any():
            cr, cc = np.where(core)
            cols = np.zeros(len(ys), bool); cols[max(cc.min() - 6, 0):cc.max() + 7] = True
            m = (bmean > 0.004) & cols[None, :]
            m[zs > zs[cr.max()] + 0.006] = False
        rows = np.where(m.any(1))[0]
        if not len(rows):
            C.log("WARNING no ear found", side)
            return dict(top=self.eye[2] + 0.004, z=self.eye[2] + 0.007, front=self.eye[1] + 0.07, back_top=self.eye[1] + 0.09,
                        backs=(zs, np.full(len(zs), self.eye[1] + 0.095)), x=0.075)
        top_r = rows.max()
        top = zs[top_r]
        near = [r for r in rows if zs[r] >= top - 0.012]
        cols = np.where(m[near].any(0))[0]
        front = ys[cols.min()]
        back_top = ys[np.where(m[[r for r in rows if zs[r] >= top - 0.006]].any(0))[0].max()]
        backs = np.array([ys[np.where(m[r])[0].max()] if m[r].any() else np.nan for r in range(len(zs))])
        ok = ~np.isnan(backs)
        backs = np.interp(zs, zs[ok], backs[ok])
        return dict(top=top, z=top + 0.0035, front=front, back_top=back_top, backs=(zs, backs), x=float(X[top_r + 1:top_r + 3, cols].max()))


class G2:
    def __init__(self, F, sp):
        self.F, self.sp = F, sp
        self.frame = Part("frame")
        self.lens = Part("lens")
        self.glow = Part("glow")

    # ------------------------------------------------------------------ lens geometry
    def basis(self, side, cx, cz, y, wrap, tilt):
        w = R_(wrap) * side
        U = np.array((math.cos(R_(wrap)) * side, math.sin(R_(wrap)), 0.0))
        Fw = np.array((math.sin(R_(wrap)) * side * 1.0, -math.cos(R_(wrap)), 0.0))
        Fw = nrm(Fw - U * np.dot(Fw, U))
        if Fw[1] > 0:
            Fw = -Fw
        t = R_(tilt)
        V = nrm(np.array((0, 0, 1.0)) * math.cos(t) + Fw * math.sin(t))
        Fw = nrm(np.cross(U, V))
        if Fw[1] > 0:
            Fw = -Fw
        c = np.array((cx * side, y, cz))
        return c, U, V, Fw

    @staticmethod
    def lp(c, U, V, Fw, uv, base_r=0.12):
        uv = np.asarray(uv, float)
        r2 = (uv ** 2).sum(-1)
        return c + uv[..., :1] * U + uv[..., 1:2] * V - Fw * (r2 / (2 * base_r))[..., None]

    def lens_mesh(self, c, U, V, Fw, ol, thick=0.0018, rings=3, part=None):
        part = part or self.lens
        n = len(ol)
        size = np.ptp(ol[:, 0])
        bi = 1 - 2 * 0.0004 / size
        verts = [self.lp(c, U, V, Fw, (0, 0))]
        for k in range(1, rings + 1):
            f = k / rings * (bi if k == rings else 1.0)
            verts += list(self.lp(c, U, V, Fw, ol * f))
        verts = np.array(verts)
        faces = [[0, 1 + j, 1 + (j + 1) % n] for j in range(n)]
        for k in range(1, rings):
            for j in range(n):
                a = 1 + (k - 1) * n + j; b = 1 + (k - 1) * n + (j + 1) % n
                faces.append([a, a + n, b + n, b])
        fr = verts + Fw * thick * 0.5; bk = verts - Fw * thick * 0.5
        mid = self.lp(c, U, V, Fw, ol)
        nv = len(verts)
        allf = [f[::-1] for f in faces] + [[i + nv for i in f] for f in faces]
        r0 = 1 + (rings - 1) * n
        for j in range(n):
            a = r0 + j; b = r0 + (j + 1) % n
            allf += [[a, b, 2 * nv + (j + 1) % n, 2 * nv + j], [2 * nv + j, 2 * nv + (j + 1) % n, b + nv, a + nv]]
        part.add(np.vstack([fr, bk, mid]), allf, "EyewearLens")

    def rim(self, pts, c, Fw, prof, mat="EyewearFrame", part=None, push=0.0):
        P = np.asarray(pts)
        T = nrm_rows(np.roll(P, -1, 0) - np.roll(P, 1, 0))
        B = nrm_rows(np.broadcast_to(Fw, P.shape) - T * (T * Fw).sum(1, keepdims=True))
        N = np.cross(T, B)
        sg = np.sign(((P - c) * N).sum(1, keepdims=True)); sg[sg == 0] = 1
        N = N * sg
        sweep(part or self.frame, P + N * push, N, B, prof, mat, closed=True)
        return N

    def bar(self, pts, prof, mat="EyewearFrame", up=(0, 0, 1.0), n=None, part=None, scale=None, smooth=2):
        P = smooth_path(np.asarray(pts, float), n or max(6, len(pts) * 5), smooth)
        T, N, B = path_frame(P, up)
        sc = None if scale is None else np.interp(np.linspace(0, 1, len(P)), np.linspace(0, 1, len(scale)), scale)
        sweep(part or self.frame, P, N, B, prof, mat, closed=False, scale=sc)
        return P

    # ------------------------------------------------------------------ temples
    def temple(self, side, start, h, t, tip=(0.0028, 0.0034), clear=0.0022, taper=True):
        """Straight-ish arm from the hinge to the front of the ear, over the ear root, then bent down behind the ear.
        Profile h (vertical) x t (lateral); the tip thickens to `tip` (acetate sleeve / temple tip)."""
        F = self.F
        E = F.ear[side]
        zt = E["z"]
        cl = clear + t * 0.5
        y_e0 = E["front"] - 0.004
        x_e0 = max(F.side_x(y_e0, zt, side), F.side_x(y_e0, zt - h * 0.5, side)) + cl
        S = np.asarray(start, float)
        E0 = np.array((side * x_e0, y_e0, zt))
        pts = []
        for u in np.linspace(0, 1, 10):
            p = S + (E0 - S) * u
            p[2] = S[2] + (zt - S[2]) * ss(0.0, 1.0, u)
            xs = max(F.side_x(p[1], p[2] + dz, side) for dz in (-h * 0.5, 0.0, h * 0.5)) + cl
            p[0] = side * max(abs(p[0]), xs)
            pts.append(p)
        zs, backs = E["backs"]
        y_b = E["back_top"] + 0.002
        for u in np.linspace(0.25, 1, 4):
            y = y_e0 + (y_b - y_e0) * u
            z = zt - 0.0012 * u
            xs = max(F.side_x(y, z + dz, side) for dz in (-h * 0.5, 0.0, h * 0.5)) + cl
            pts.append(np.array((side * max(xs, abs(pts[-1][0]) - 0.0015), y, z)))
        last = pts[-1]
        ylast = last[1]
        for dz in (-0.004, -0.009, -0.015, -0.022, -0.029):
            z = zt + dz
            y = max(ylast + 0.0012, float(np.interp(z, zs, backs)) + 0.0045 + 0.0002 * dz * 1000 * 0)
            ylast = y
            x = F.skull_in(y, z, side) + clear + tip[1] * 0.5
            pts.append(np.array((side * x, y, z)))
        P = smooth_path(np.array(pts), 40, 2)
        T, N, B = path_frame(P, (side * 1.0, 0, 0))
        s_ = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]); s_ /= s_[-1]
        nb = len(pts) - 5
        # thickness profile: slim through the middle, tip sleeve after the ear
        u_bend = float(np.interp(nb - 1, np.arange(len(pts)), np.linspace(0, 1, len(pts))))
        hs = np.interp(s_, [0, 0.12, 0.6, u_bend, min(1, u_bend + 0.06), 1], [1.0, 0.92, 0.82, 0.8, tip[0] / h, tip[0] / h * 0.92]) if taper else np.ones_like(s_)
        ts = np.interp(s_, [0, u_bend, min(1, u_bend + 0.06), 1], [1.0, 1.0, tip[1] / t, tip[1] / t])
        prof = prof_round_rect(1.0, 1.0, 0.6, 3)
        V = P[:, None, :] + prof[None, :, 0, None] * N[:, None, :] * (h * hs)[:, None, None] + prof[None, :, 1, None] * B[:, None, :] * (t * ts)[:, None, None]
        m = len(prof); n = len(P)
        faces = [[i * m + j, i * m + (j + 1) % m, (i + 1) * m + (j + 1) % m, (i + 1) * m + j] for i in range(n - 1) for j in range(m)]
        faces += [list(range(m))[::-1], [(n - 1) * m + j for j in range(m)]]
        self.frame.add(V.reshape(-1, 3), faces, "EyewearFrame")
        return P

    def hinge(self, p, up, out):
        up = nrm(up); out = nrm(out)
        Pp = np.array([p - up * 0.0036, p + up * 0.0036])
        T, N, B = path_frame(Pp, out)
        sweep(self.frame, Pp, N, B, prof_circle(0.0013, 10), "EyewearFrame", closed=False)


# ============================================================================= designs

SPECS = {
    "aviator": dict(label="Aviator", shape="aviator", frame="wire", wire_r=0.0006, h=0.045, wide=0.98, bridge=0.019, wrap=6, tilt=10, dz=-0.004,
                    frame_col="#c8a35a", metal=1.0, smooth=0.88, lens="#2f4a3a", lens_a=0.62, glow=None, top_bar=True),
    "round_wire": dict(label="Round Wire", shape="round", frame="wire", wire_r=0.00055, h=0.040, wide=0.86, bridge=0.021, wrap=3, tilt=10, dz=-0.004,
                       frame_col="#bfc4ca", metal=1.0, smooth=0.86, lens="#b9d4e4", lens_a=0.14, glow=None, keyhole=True),
    "rect_smart": dict(label="Smart Rectangles", shape="rect", frame="acetate", rim=(0.0032, 0.0040), h=0.034, wide=1.0, bridge=0.018, wrap=5,
                       tilt=10, dz=-0.004, frame_col="#1c1f24", metal=0.0, smooth=0.86, lens="#8fdcff", lens_a=0.16, glow="#00e5ff", hud=True),
    "shades_led": dict(label="LED Shades", shape="wayfarer", frame="acetate", rim=(0.0038, 0.0048), h=0.039, wide=1.03, bridge=0.017, wrap=7,
                       tilt=10, dz=-0.004, frame_col="#0c0c0e", metal=0.0, smooth=0.88, lens="#08090b", lens_a=0.82, glow="#ff2bd6", led=True),
    "tactical_goggles": dict(label="Tactical Goggles", shape="rect", frame="acetate", rim=(0.0042, 0.0058), h=0.038, wide=1.04, bridge=0.016,
                             wrap=12, tilt=9, dz=-0.003, heavy=True, frame_col="#2b2f26", metal=0.0, smooth=0.45, lens="#ffad2a", lens_a=0.5, glow="#00e5ff",
                             led=True),
    "cat_eye_tech": dict(label="Cat-Eye Tech", shape="cateye", frame="acetate", rim=(0.0034, 0.0042), h=0.036, wide=0.98, bridge=0.017, wrap=6,
                         tilt=10, dz=-0.003, frame_col="#2a1630", metal=0.0, smooth=0.88, lens="#d79bff", lens_a=0.26, glow="#ff2bd6", wing=True),
    "monocle_hud": dict(label="Monocle HUD", shape="round", frame="tech", rim=(0.0032, 0.0044), h=0.035, wide=0.75, bridge=0.02, wrap=3, tilt=9,
                        dz=-0.004, frame_col="#2a2f37", metal=0.85, smooth=0.75, lens="#7ff7ff", lens_a=0.2, glow="#00e5ff", hud=True, mono=True),
    "cyber_visor": dict(label="Cyber Visor", shape="visor", frame="visor", h=0.034, frame_col="#1b1e24", metal=0.6, smooth=0.8, lens="#18a8ff",
                        lens_a=0.5, glow="#00f0ff"),
}
ITEMS = {"kael": ["aviator", "round_wire", "rect_smart", "cyber_visor", "shades_led", "monocle_hud", "tactical_goggles"],
         "lyra": ["cat_eye_tech", "aviator", "round_wire", "rect_smart", "cyber_visor", "shades_led", "monocle_hud", "tactical_goggles"]}


def frame_dims(F, sp):
    """Lens width from the face: the frame front's outer edge sits just outside the temples."""
    half = F.side_x(F.eye[1] + 0.03, F.eye[2] + 0.004, 1) * 0.5 + F.side_x(F.eye[1] + 0.03, F.eye[2] + 0.004, -1) * 0.5
    half_front = half + 0.006
    rimw = sp.get("rim", (0.0012, 0.0012))[0] if sp["frame"] != "wire" else 0.0012
    end = 0.0045 if sp["frame"] != "wire" else 0.004
    w = (half_front - sp["bridge"] / 2 - end - rimw) * 2 / 2 * sp["wide"]
    w = float(np.clip(w * 1.0, 0.044, 0.06))
    cx = sp["bridge"] / 2 + rimw + w / 2
    return w, cx


def fit_y(F, g, sp, ol, cx, cz, rimw):
    """Lens plane y: >= 11 mm vertex distance, every rim point >= 3 mm off the face."""
    y = F.cornea_y - 0.011
    for _ in range(6):
        worst = 1.0
        for side in (1, -1):
            c, U, V, Fw = g.basis(side, cx, cz, y, sp["wrap"], sp["tilt"])
            grow = 1 + rimw / max(np.ptp(ol[:, 0]) * 0.5, 1e-3)
            P = g.lp(c, U, V, Fw, ol * grow) + Fw * (-0.002)
            cl = F.clearance(P)
            if cl.min() < worst:
                worst = float(cl.min()); wp = P[int(np.argmin(cl))] - F.eye
        need = sp.get("clear", 0.0022) - worst
        C.log("  fit y", round(y, 4), "worst mm", round(worst * 1000, 2), "at (mm from eye)", (wp * 1000).round(1))
        if need <= 0.0002:
            break
        y -= need + 0.0003
    return y


def build(F, cid, iid):
    sp = dict(SPECS[iid])
    if cid == "lyra":      # narrower, finer frames on Giva
        sp["h"] *= 0.95
        sp["wide"] = sp.get("wide", 1.0) * 0.93
        sp["bridge"] = sp.get("bridge", 0.018) * 0.92
    g = G2(F, sp)
    if sp["frame"] == "visor":
        return build_visor(F, g, sp)
    wire = sp["frame"] == "wire"
    w, cx = frame_dims(F, sp)
    h = sp["h"]
    if sp.get("mono"):
        w = h = 0.035
        cx = abs(F.eyeR[0]) + 0.001
    cz = F.eye[2] + sp["dz"]
    ol = lens_outline(sp["shape"], w, h)
    rimw, rimd = (0.0011, 0.0011) if wire else sp["rim"]
    y = fit_y(F, g, sp, ol, cx, cz, rimw)
    C.log(iid, "lens w", round(w * 1000, 1), "h", round(h * 1000, 1), "cx", round(cx * 1000, 1), "vertex mm", round((F.cornea_y - y) * 1000, 1))
    prof_r = prof_round_rect(0.0012, 0.0021, 0.9, 3) if wire else prof_round_rect(rimw, rimd, 0.5, 3)
    sides = (-1,) if sp.get("mono") else (1, -1)
    data = {}
    for side in sides:
        c, U, V, Fw = g.basis(side, cx, cz, y, sp["wrap"], sp["tilt"])
        g.lens_mesh(c, U, V, Fw, ol, thick=0.0016 if wire else 0.0019)
        rimpts = g.lp(c, U, V, Fw, ol)
        Nr = g.rim(rimpts, c, Fw, prof_r, push=(0.0003 if wire else rimw * 0.32))
        uv = ol
        i_in = int(np.argmin(uv[:, 0] + (0.0 if wire else 0.3) * np.abs(uv[:, 1] - h * 0.12)))
        i_hi = int(np.argmax(uv[:, 0] + 0.7 * uv[:, 1]))
        i_top_in = int(np.argmax(uv[:, 1] - 0.9 * uv[:, 0]))
        data[side] = dict(c=c, U=U, V=V, Fw=Fw, inner=rimpts[i_in] + Nr[i_in] * rimw * 0.5, top_in=rimpts[i_top_in] + Nr[i_top_in] * rimw * 0.5,
                          hi=rimpts[i_hi] + Nr[i_hi] * rimw * 0.7)
        # endpiece + hinge
        hp = data[side]["hi"] + U * (0.0045 if not wire else 0.003) + Fw * (-0.002)
        need = max(F.side_x(hp[1] + dy_, hp[2] + dz_, side) for dy_ in (0.004, 0.01, 0.016, 0.022) for dz_ in (-0.002, 0.0, 0.002)) \
            + 0.0035 - abs(hp[0])
        if need > 0:      # monocle: the lens sits inside the face width -> swept arm out to the temple line
            h0 = data[side]["hi"]
            hp = hp + np.array((side * need, 0.6 * need + 0.003, 0.0))
            arm = [h0 - U * 0.001, h0 + U * 0.004 + Fw * -0.0005, (h0 + hp) / 2 + U * 0.002 + Fw * -0.001, hp + Fw * 0.0005]
            g.bar(arm, prof_round_rect(rimd * 0.8, 0.0042, 0.45, 3), up=(0, 0, 1.0))
        elif wire:
            g.bar([data[side]["hi"], data[side]["hi"] + U * 0.002, hp], prof_round_rect(0.0016, 0.0021, 0.9, 3), up=Fw)
        else:
            g.bar([data[side]["hi"] - U * 0.001, hp + Fw * 0.0005], prof_round_rect(rimd * 0.95, 0.0055, 0.45, 3), up=Fw)
        g.hinge(hp + Fw * -0.0012, V, U)
        data[side]["hinge"] = hp
        # temple
        if wire:
            g.temple(side, hp + Fw * -0.0016, 0.0019, 0.0010, tip=(0.0027, 0.0031))
        else:
            g.temple(side, hp + Fw * -0.0022, 0.0042 if not sp.get("heavy") else 0.0058, 0.0019, tip=(0.0034, 0.0030))
        # glow details
        if sp.get("led"):
            ti = np.where(uv[:, 1] > h * 0.3)[0]
            ti = ti[np.argsort(-np.arctan2(uv[ti, 1], uv[ti, 0]))] if side > 0 else ti[np.argsort(np.arctan2(uv[ti, 1], -uv[ti, 0]))]
            pts = [g.lp(c, U, V, Fw, uv[j] * (1 + (rimw * 0.35) / (w / 2))) + Fw * (rimd * 0.5 + 0.0002) for j in ti]
            g.bar(pts, prof_round_rect(0.0009, 0.0005, 0.5, 2), "Glow", up=Fw, part=g.glow)
        if sp.get("wing"):
            wi = np.where((uv[:, 0] > w * 0.1) & (uv[:, 1] > h * 0.1))[0]
            wi = wi[np.argsort(uv[wi, 0])]
            pts = [g.lp(c, U, V, Fw, uv[j]) + Fw * (rimd * 0.5 + 0.0002) for j in wi]
            g.bar(pts, prof_round_rect(0.0008, 0.0005, 0.5, 2), "Glow", up=Fw, part=g.glow)
        if sp.get("hud") and side == -1:
            # micro projector on the right temple, light guide into the lens corner
            pod = []
            for dy in (0.004, 0.011, 0.018, 0.024):
                q_ = hp + np.array((0, dy, -0.0005))
                xq = max(abs(q_[0]) + 0.0016, max(F.side_x(q_[1], q_[2] + dz_, side) for dz_ in (-0.004, 0, 0.004)) + 0.0048)
                pod.append(np.array((side * xq, q_[1], q_[2])))
            g.bar(pod, prof_round_rect(0.0042, 0.0072, 0.5, 3), up=(0, 0, 1.0))
            gl = [pq + np.array((side * 0.0022, 0, 0)) for pq in pod[1:3]]
            g.bar(gl, prof_round_rect(0.0006, 0.0018, 0.5, 2), "Glow", part=g.glow)
            for k, (r0, a0, a1) in enumerate(((0.0105, 30, 140), (0.0135, 210, 300))):
                th = np.radians(np.linspace(a0, a1, 14))
                pts = [g.lp(c, U, V, Fw, (r0 * math.cos(t) * side, r0 * math.sin(t))) - Fw * 0.0011 for t in th]
                g.bar(pts, prof_round_rect(0.00045, 0.0002, 0.5, 2), "Glow", up=Fw, part=g.glow)
    if sp.get("mono"):
        return g
    # bridge
    a, b = data[1], data[-1]
    if wire:
        za = (a["inner"] + b["inner"]) / 2
        top = (a["top_in"] + b["top_in"]) / 2
        mid = np.array((0.0, min(za[1], F.front_y(0.0, za[2]) - 0.004), za[2] + 0.004))
        g.bar([a["inner"], (a["inner"] + mid) / 2 + np.array((0, -0.0005, 0.002)), mid, (b["inner"] + mid) / 2 + np.array((0, -0.0005, 0.002)),
               b["inner"]], prof_circle(sp["wire_r"] * 1.25, 8))
        if sp.get("top_bar"):
            tm = np.array((0.0, top[1] - 0.0008, top[2] + 0.0015))
            g.bar([a["top_in"], tm, b["top_in"]], prof_circle(sp["wire_r"] * 1.1, 8))
        # pad arms + pads on the nose
        for side in (1, -1):
            d = data[side]
            zp = F.eye[2] - 0.011
            npt, nn = F.nose_pt(side * 0.0085, zp)
            n2 = nrm(np.array((side * 1.0, -0.55, 0.05)) * 0.5 + nn * 0.5)
            pad_c = npt + n2 * 0.0012
            anchor = d["inner"] + np.array((0, 0.0005, -0.004))
            g.bar([anchor, anchor + np.array((-side * 0.0005, 0.004, -0.003)), pad_c + n2 * 0.0015], prof_circle(sp["wire_r"] * 0.9, 6))
            Tz = np.array((0, 0, 1.0)); Bv = nrm(np.cross(n2, Tz)); Tz = nrm(np.cross(Bv, n2))
            ell = np.array([pad_c + Tz * 0.0062 * math.cos(t) * 0.5 + Bv * 0.0042 * math.sin(t) * 0.5 for t in np.linspace(0, 2 * math.pi, 12, endpoint=False)])
            g.lens.add(np.vstack([ell, ell + n2 * 0.0012]), [list(range(12))[::-1], [12 + i for i in range(12)]] +
                       [[i, (i + 1) % 12, 12 + (i + 1) % 12, 12 + i] for i in range(12)], "EyewearLens")
    else:
        ta, tb = a["top_in"], b["top_in"]
        ia, ib = a["inner"], b["inner"]
        zb = (ta[2] + ia[2]) * 0.5 + 0.004
        mid = np.array((0.0, min((ta[1] + tb[1]) / 2, F.front_y(0.0, zb) - 0.003), zb))
        g.bar([ta - (ta - ia) * 0.15, (ta + mid) / 2 + np.array((0, -0.0004, 0.0015)), mid, (tb + mid) / 2 + np.array((0, -0.0004, 0.0015)),
               tb - (tb - ib) * 0.15], prof_round_rect(0.0036, sp["rim"][1], 0.5, 3), up=(0, -1.0, 0))
        # moulded nose pads resting on the nose sides
        for side in (1, -1):
            zp = F.eye[2] - 0.012
            npt, nn = F.nose_pt(side * 0.0078, zp)
            inn = data[side]["inner"]
            q = npt + nrm(nn) * 0.0021
            g.bar([inn + np.array((0, 0.0008, -0.002)), (inn + q) / 2 + np.array((0, 0, -0.001)), q],
                  prof_round_rect(0.0026, 0.0022, 0.5, 2), up=(side * 1.0, 0, 0))
    return g


def build_visor(F, g, sp):
    """Wraparound band shield on an elliptic cylinder that clears the face by >= 4 mm; frame bar on top, neon edges, temples."""
    zc = F.eye[2] + 0.002
    h = sp["h"]
    yc = F.eye[1] + 0.05
    a = F.side_x(F.eye[1] + 0.035, zc, 1) * 0.5 + F.side_x(F.eye[1] + 0.035, zc, -1) * 0.5 + 0.009
    b = yc - (F.cornea_y - 0.013)
    ang = np.radians(np.linspace(-80, 80, 45))
    vs = np.linspace(-0.5, 0.5, 7)

    def grid_at(a_, b_):
        out = []
        for t in ang:
            col = []
            e = abs(math.degrees(t)) / 80
            for v in vs:
                z = zc + v * h * (1 - 0.25 * e ** 2) + 0.004 * e ** 2
                if v < 0 and abs(t) < R_(12):
                    z = max(z, zc - h * 0.5 + 0.013 * (1 - abs(t) / R_(12)) ** 1.5)
                col.append((math.sin(t) * a_, yc - math.cos(t) * b_, z))
            out.append(col)
        return np.array(out)
    for _ in range(8):
        Gd = grid_at(a, b)
        cl = F.clearance(Gd.reshape(-1, 3)).min()
        if cl >= 0.004:
            break
        a += (0.004 - cl) * 0.6 + 0.0005
        b += (0.004 - cl) + 0.0005
    Gd = grid_at(a, b)
    C.log("visor a b", round(a, 4), round(b, 4), "clearance mm", round(float(F.clearance(Gd.reshape(-1, 3)).min()) * 1000, 1))
    na, nv = Gd.shape[:2]
    Fw = nrm_rows((Gd - np.array((0, yc, 0))) * np.array((1.0 / a ** 2, 1.0 / b ** 2, 0)))
    th = 0.0018
    verts = np.vstack([(Gd + Fw * th / 2).reshape(-1, 3), (Gd - Fw * th / 2).reshape(-1, 3)])
    faces = []
    off = na * nv
    for i in range(na - 1):
        for j in range(nv - 1):
            a_ = i * nv + j
            faces.append([a_, a_ + nv, a_ + nv + 1, a_ + 1])
            faces.append([off + a_, off + a_ + 1, off + a_ + nv + 1, off + a_ + nv])
    for i in range(na - 1):
        for j in (0, nv - 1):
            a_ = i * nv + j
            faces.append([a_, off + a_, off + a_ + nv, a_ + nv] if j == 0 else [a_, a_ + nv, off + a_ + nv, off + a_])
    for j in range(nv - 1):
        for i in (0, na - 1):
            a_ = i * nv + j
            faces.append([a_, a_ + 1, off + a_ + 1, off + a_] if i == 0 else [a_, off + a_, off + a_ + 1, a_ + 1])
    g.lens.add(verts, faces, "EyewearLens")
    top = Gd[:, -1] + Fw[:, -1] * 0.0005 + np.array((0, 0, 0.0016))
    g.bar(top, prof_round_rect(0.0034, 0.0042, 0.5, 3), up=(0, 0, 1.0), n=60)
    g.bar(top + Fw[:, -1] * 0.0024 + np.array((0, 0, -0.0004)), prof_round_rect(0.0010, 0.0006, 0.5, 2), "Glow", up=(0, 0, 1.0), n=60,
          part=g.glow)
    g.bar(Gd[:, 0] + Fw[:, 0] * 0.0012, prof_round_rect(0.0008, 0.0006, 0.5, 2), "Glow", up=(0, 0, 1.0), n=60, part=g.glow)
    for side in (1, -1):
        e = Gd[-1 if side > 0 else 0]
        pod = e.mean(0)
        g.bar([e[1], e[-1] + np.array((0, 0, 0.0016))], prof_round_rect(0.0042, 0.0052, 0.5, 3), up=(0, 1.0, 0))
        hp = pod + np.array((side * 0.0025, 0.004, 0.005))
        g.hinge(hp, (0, 0, 1.0), (side * 1.0, 0, 0))
        g.temple(side, hp + np.array((0, 0.002, 0)), 0.0045, 0.0019, tip=(0.0034, 0.0030))
    return g


def assemble(g, name):
    objs = []
    for p in (g.frame, g.lens, g.glow):
        if p.F:
            objs.append(p.build(mat_order=None, max_edge=None))
    obj = gear.join(objs, name)
    me = obj.data
    order = ["EyewearFrame", "EyewearLens", "Glow"]
    have = [m.name for m in me.materials]
    idx = np.empty(len(me.polygons), np.int32); me.polygons.foreach_get("material_index", idx)
    names = [have[i] for i in idx]
    me.materials.clear()
    for n in order:
        if n in have:
            me.materials.append(gear.get_mat(n))
    newn = [m.name for m in me.materials]
    me.polygons.foreach_set("material_index", np.array([newn.index(n) for n in names], np.int32))
    for p in me.polygons:
        p.use_smooth = True
    bpy.context.view_layer.objects.active = obj
    import bmesh
    bm = bmesh.new(); bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me); bm.free()
    obj.select_set(True)
    try:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(50))
    except Exception:
        pass
    obj.select_set(False)
    return obj


def main():
    a = C.args()
    cid = a[0]
    sel = a[1].split(",") if len(a) > 1 and not a[1].startswith("--") else ITEMS[cid]
    rig, body = C.load_ref(cid)
    ctx = gear.Ctx(body, rig, C.HEROES[cid]["name"])
    F = FaceFit(ctx)
    for s in (1, -1):
        E = F.ear[s]
        C.log("ear", s, "top z", round(E["top"], 4), "temple z", round(E.get("z", 0), 4), "y", round(E["front"], 4), round(E["back_top"], 4),
              "root x", round(E["x"], 4), "| eye", F.eye.round(4), "cornea y", round(F.cornea_y, 4))
    studio.hero_materials(cid)
    if "U_Visor" in bpy.data.objects:
        bpy.data.objects["U_Visor"].hide_render = True
    import hair_preview
    hair_preview.load_default_hair(cid)
    for d in (OUT_DIR, PREV_DIR, THUMB_DIR, os.path.join(C.CACHE, "catalog", "eyewear")):
        os.makedirs(d, exist_ok=True)
    M = C.rigid_matrix(cid)
    eye = Vector(F.eye)
    for iid in sel:
        t0 = time.time()
        sp = dict(SPECS[iid])
        g = build(F, cid, iid)
        obj = assemble(g, f"{cid}_{iid}")
        ntri = C.tris(obj)
        clr = F.clearance(C.get_co(obj))
        C.log(iid, "tris", ntri, "min clearance mm", round(float(clr.min()) * 1000, 2), "at", ((C.get_co(obj)[int(np.argmin(clr))] - F.eye) * 1000).round(1))
        # what CharacterModel.FitEyewear (runtime) would do with this item: lens sub-mesh AABB vs the eye bones
        me = obj.data
        li = [i for i, m in enumerate(me.materials) if m.name.startswith("EyewearLens")]
        if li:
            mi = np.empty(len(me.polygons), np.int32); me.polygons.foreach_get("material_index", mi)
            vi = sorted({v for p_ in me.polygons if p_.material_index in li for v in p_.vertices})
            co = C.get_co(obj)[vi]
            lo, hi = co.min(0), co.max(0)
            lc = (lo + hi) / 2
            ipd = float(np.linalg.norm(F.eyeL - F.eyeR))
            span = float(hi[0] - lo[0])
            pair = span > ipd * 1.4
            k = float(np.clip(ipd * 2.05 / span, 0.75, 1.25)) if pair else 1.0
            fwd = lc - F.eye; fwd[0] = 0; fwd /= np.linalg.norm(fwd)
            up = np.cross(fwd, np.array((-1.0, 0, 0))); up *= np.sign(up[2])
            piv = np.array(ctx.L["Head"])
            tgt = F.eye + (np.array(((lc - F.eye)[0], 0, 0)) if not pair else 0) + fwd * 0.024 - up * 0.004
            mv = tgt - (piv + (lc - piv) * k)
            C.log(iid, "runtime-fit prediction: lens centre", ((lc - F.eye) * 1000).round(1), "span mm", round(span * 1000, 1),
                  "scale", round(k, 3), "move mm", (mv * 1000).round(1))
        if "--fit-only" in a:
            bpy.data.objects.remove(obj, do_unlink=True)
            continue
        preview_mats(obj, sp)
        aim = eye + Vector((0, 0.01, 0.0))
        studio.world_and_lights(aim, 0.6, rim=1.0, yaw=28)
        studio.camera(studio.view(aim, 28, 4, 0.62), aim, 70)
        studio.render(os.path.join(THUMB_DIR, f"eyewear_{cid}_{iid}.png"), 512, 256)
        for tag, yaw, pitch, dist in (("q34", 28, 4, 0.62), ("front", 0, 2, 0.6), ("side", 82, 3, 0.55), ("top", 20, 55, 0.5)):
            studio.world_and_lights(aim, 0.6, rim=1.0, yaw=yaw)
            studio.camera(studio.view(aim, yaw, pitch, dist), aim, 70)
            studio.render(os.path.join(PREV_DIR, f"{cid}_{iid}_{tag}.png"), 512)
        restore_mats(obj)
        if "--no-export" not in a:
            obj.data.transform(M)
            obj.data.update()
            C.export_fbx(os.path.join(OUT_DIR, f"{cid}_{iid}.fbx"), [obj])
            e = {"id": iid, "label": sp["label"], "hero": cid, "file": f"Eyewear/{cid}_{iid}", "kind": "rigid", "bone": "mixamorig:Head",
                 "thumb": f"Thumbs/eyewear_{cid}_{iid}", "localPos": [0, 0, 0], "localRot": [0, 0, 0], "tris": ntri,
                 "materials": {"EyewearFrame": {"tint": sp["frame_col"]}, "EyewearLens": {"lensTint": sp["lens"], "lensAlpha": sp["lens_a"]}},
                 "frame": {"metallic": sp["metal"], "smoothness": sp["smooth"]}, "fitted": True,
                 "pipeline": "eyewear v2 (fitted to the hero head: brow/cheek clearance, temples over the ears)"}
            if sp.get("glow"):
                e["materials"]["Glow"] = {"color": sp["glow"], "intensity": 3.0}
            if cid == "lyra":
                e["hides"] = ["Visor"]
            with open(os.path.join(C.CACHE, "catalog", "eyewear", f"{cid}_{iid}.json"), "w") as f:
                json.dump(e, f, indent=1)
        C.log(iid, "done", round(time.time() - t0, 1))
        bpy.data.objects.remove(obj, do_unlink=True)
    import catalog
    catalog.merge()


if __name__ == "__main__":
    main()
