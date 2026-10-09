"""Tattoo library: six invented cyberpunk designs per hero (circuit traces, tech-tribal, glyphs, neck/face lines, back
piece, sleeves). No real logos or letters: glyphs are random stroke clusters on a 3x3 grid inside frames.

  blender -b --python blender/custom/tattoo.py -- <cid> [design,...]

Every design is defined in 3-D on the rest body (limb / neck / head / back / front parameterisations in metres) and
rasterised into the hero's exported Body UV layout (U_Body):
  Tattoos/<cid>_<id>_Ink.png   Unity Lit "Detail Albedo x2" map: 0.5 = no change, darker = ink. Import as linear
                               (sRGB off).
  Tattoos/<cid>_<id>_Glow.png  emission mask, RGB pattern (sRGB), black = none.
Preview / thumbnail textures are also rasterised into the MakeHuman UV of the full base body (cache/ only).
"""
import bpy, os, sys, math, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from mathutils import Vector, Matrix
import common as C
import gear, texbake as TB
import studio, texstage
from common import ss, nrm, nrm_rows

OUT_DIR = os.path.join(C.CUSTOM_OUT, "Tattoos")
THUMB_DIR = os.path.join(C.CUSTOM_OUT, "Thumbs")
PREV_DIR = os.path.join(C.PREVIEWS, "tattoo")
SIZE = 2048


# ============================================================================= 2-D pattern


class Pat:
    """Vector drawing in a 2-D chart (metres). Layers: 0 ink, 1 glow A, 2 glow B (glow lines are also lightly inked)."""

    def __init__(self):
        self.segs, self.polys, self.dots = [], [], []

    def line(self, pts, w=0.0012, layer=0, taper=None):
        pts = [tuple(map(float, p)) for p in pts]
        n = len(pts) - 1
        for i, (a, b) in enumerate(zip(pts[:-1], pts[1:])):
            if taper:
                w0 = w * (1 - (1 - taper) * i / max(n, 1)); w1 = w * (1 - (1 - taper) * (i + 1) / max(n, 1))
            else:
                w0 = w1 = w
            self.segs.append((a[0], a[1], b[0], b[1], w0, w1, layer))

    def poly(self, pts, layer=0):
        self.polys.append((np.asarray(pts, np.float64), layer))

    def dot(self, x, y, r, ring=0.0, layer=0):
        self.dots.append((float(x), float(y), float(r), float(ring), layer))

    def eval(self, X, Y, soft=0.00028):
        cov = np.zeros((3, len(X)), np.float32)
        for (ax, ay, bx, by, w0, w1, ly) in self.segs:
            m = max(w0, w1)
            sel = np.where((X > min(ax, bx) - m) & (X < max(ax, bx) + m) & (Y > min(ay, by) - m) & (Y < max(ay, by) + m))[0]
            if not len(sel):
                continue
            d, t = TB.line_sdf2(X[sel], Y[sel], ax, ay, bx, by)
            hw = (w0 + (w1 - w0) * t) * 0.5
            cov[ly, sel] = np.maximum(cov[ly, sel], 1 - ss(hw - soft, hw + soft, d))
        for (pts, ly) in self.polys:
            mn = pts.min(0); mx = pts.max(0)
            sel = np.where((X > mn[0] - soft) & (X < mx[0] + soft) & (Y > mn[1] - soft) & (Y < mx[1] + soft))[0]
            if not len(sel):
                continue
            px, py = X[sel], Y[sel]
            inside = np.zeros(len(sel), bool)
            dmin = np.full(len(sel), 1e9)
            n = len(pts)
            for i in range(n):
                x0, y0 = pts[i]; x1, y1 = pts[(i + 1) % n]
                c = ((y0 > py) != (y1 > py)) & (px < (x1 - x0) * (py - y0) / (y1 - y0 + 1e-15) + x0)
                inside ^= c
                d, _ = TB.line_sdf2(px, py, x0, y0, x1, y1)
                dmin = np.minimum(dmin, d)
            sd = np.where(inside, -dmin, dmin)
            cov[ly, sel] = np.maximum(cov[ly, sel], 1 - ss(-soft, soft, sd))
        for (x, y, r, ring, ly) in self.dots:
            R = r + soft
            sel = np.where((np.abs(X - x) < R) & (np.abs(Y - y) < R))[0]
            if not len(sel):
                continue
            d = np.hypot(X[sel] - x, Y[sel] - y)
            if ring > 0:
                v = 1 - ss(ring * 0.5 - soft, ring * 0.5 + soft, np.abs(d - (r - ring * 0.5)))
            else:
                v = 1 - ss(r - soft, r + soft, d)
            cov[ly, sel] = np.maximum(cov[ly, sel], v)
        return cov

    # ------------------------------------------------------------------ generators
    def trace(self, rng, start, heading, n, step=(0.006, 0.014), w=0.0011, layer=0, bounds=None, turn=0.45, via=True, via_layer=None):
        pts = [np.array(start, float)]
        hd = heading
        for _ in range(n):
            if rng.random() < turn:
                hd += rng.choice([-1, 1]) * math.pi / 4
            p = pts[-1] + np.array((math.cos(hd), math.sin(hd))) * rng.uniform(*step)
            if bounds is not None and not (bounds[0] <= p[0] <= bounds[1] and bounds[2] <= p[1] <= bounds[3]):
                break
            pts.append(p)
        if len(pts) > 1:
            self.line(pts, w, layer)
        if via:
            self.dot(pts[-1][0], pts[-1][1], w * 1.9, w * 0.75, layer if via_layer is None else via_layer)
        return pts

    def bus(self, start, dirs, lengths, count=4, spacing=0.0028, w=0.0009, layer=0, glow_every=0, glow_layer=1, vias=True):
        """Parallel traces following the same 45-degree path (dirs: headings in radians, lengths in metres)."""
        for k in range(count):
            off = (k - (count - 1) / 2) * spacing
            pts = []
            p = np.array(start, float)
            h0 = dirs[0]
            p = p + np.array((-math.sin(h0), math.cos(h0))) * off
            pts.append(p.copy())
            for h, L in zip(dirs, lengths):
                # keep spacing through the bend: shorten/lengthen per lane
                p = p + np.array((math.cos(h), math.sin(h))) * (L + off * 0.4 * (1 if h > h0 else -1))
                pts.append(p.copy())
                h0 = h
            ly = glow_layer if (glow_every and k % glow_every == 0) else layer
            self.line(pts, w, ly)
            if vias:
                self.dot(pts[-1][0], pts[-1][1], w * 2.0, w * 0.8, ly)

    def blade(self, a, b, w, bend=0.3, layer=0, n=14, hook=0.0):
        """Tapered curved spike (filled) from a (wide base) to b (tip)."""
        a = np.asarray(a, float); b = np.asarray(b, float)
        d = b - a; L = np.linalg.norm(d)
        t_ = d / max(L, 1e-9); nn = np.array((-t_[1], t_[0]))
        left, right = [], []
        for t in np.linspace(0, 1, n):
            c = a + d * t + nn * (bend * L * math.sin(t * math.pi) * 0.35 + hook * L * t ** 3)
            hw = w * 0.5 * (1 - t) ** 0.9
            left.append(c + nn * hw); right.append(c - nn * hw)
        self.poly(left + right[::-1], layer)
        mid = [a + d * t + nn * (bend * L * math.sin(t * math.pi) * 0.35 + hook * L * t ** 3) for t in np.linspace(0.05, 0.8, 8)]
        return mid

    def glyph(self, rng, cx, cy, s, layer=0, w=None, frame=True, glow_layer=None):
        """Invented glyph: 2-4 strokes on a 3x3 grid (diagonals, arcs, hooks) + nodes, inside an optional frame."""
        w = w or s * 0.11
        g = [(cx + (i - 1) * s * 0.32, cy + (j - 1) * s * 0.32) for j in range(3) for i in range(3)]
        used = set()
        for k in range(int(rng.integers(2, 5))):
            a, b = rng.choice(9, 2, replace=False)
            if (a, b) in used:
                continue
            used.add((a, b))
            pa, pb = np.array(g[a]), np.array(g[b])
            if rng.random() < 0.45:  # arc
                mid = (pa + pb) / 2 + np.array((-(pb - pa)[1], (pb - pa)[0])) * rng.uniform(-0.45, 0.45)
                pts = [pa * (1 - t) ** 2 + mid * 2 * t * (1 - t) + pb * t * t for t in np.linspace(0, 1, 7)]
            else:
                pts = [pa, pb]
            self.line(pts, w, glow_layer if (glow_layer is not None and k == 0) else layer)
        for k in rng.choice(9, int(rng.integers(1, 3)), replace=False):
            self.dot(g[k][0], g[k][1], w * 1.1, 0, layer)
        if frame:
            h = s * 0.55
            if rng.random() < 0.5:
                self.line([(cx - h, cy - h), (cx + h, cy - h), (cx + h, cy + h), (cx - h, cy + h), (cx - h, cy - h)], w * 0.6, layer)
            else:
                self.dot(cx, cy, h * 1.15, w * 0.6, layer)

    def chevrons(self, cx, cy, n, s, w, layer=0, up=True, gap=None):
        gap = gap or s * 0.6
        for i in range(n):
            y = cy + i * gap * (1 if up else -1)
            self.line([(cx - s, y), (cx, y + s * 0.6 * (1 if up else -1)), (cx + s, y)], w, layer)


# ============================================================================= body charts


class Charts:
    """3-D -> 2-D parameterisations of body parts (all in metres) with region masks from bone weights."""

    def __init__(self, ctx):
        self.ctx = ctx
        L, T = ctx.L, ctx.T
        self.L, self.T = L, T
        eye = (L["LeftEye"] + L["RightEye"]) * 0.5
        self.eye = eye
        self.hc = np.array((0.0, eye[1] + 0.083, eye[2] + 0.012))
        self.neck0 = L["Neck"]; self.neck1 = L["Head"]

    def arm(self, P, side):
        S = "Left" if side > 0 else "Right"
        L = self.L
        sh, el, wr = L[S + "Arm"], L[S + "ForeArm"], L[S + "Hand"]
        Lu = np.linalg.norm(el - sh)
        front = (0, -1.0, 0)
        tu, pu, ru = gear.limb_coords(P, sh, el, front)
        tf, pf, rf = gear.limb_coords(P, el, wr, front)
        uf = tu > Lu
        t = np.where(uf, Lu + tf, tu)
        phi = np.where(uf, pf, pu)
        phi = phi * side          # mirror so +X is towards the outside for both arms
        r = np.where(uf, rf, ru)
        return phi * 0.042, t, r, Lu, Lu + np.linalg.norm(wr - el)

    def hand(self, P, side):
        S = "Left" if side > 0 else "Right"
        L = self.L
        a, b = L[S + "Hand"], L[S + "HandMiddle1"] if (S + "HandMiddle1") in L else self.T[S + "Hand"]
        t, phi, r = gear.limb_coords(P, a, b, (0, 0, 1.0))
        return phi * side * 0.03, t, r

    def neck(self, P):
        a, b = self.neck0, self.neck1
        t, phi, r = gear.limb_coords(P, a, b, (0, -1.0, 0))
        # phi 0 = front, + towards the character's left
        return phi * 0.055, P[:, 2], r

    def side(self, P):
        """Side projection (y forward/back, z) for the head/neck sides (mirrored: + = back)."""
        return P[:, 1] - self.hc[1], P[:, 2] - self.hc[2]

    def front(self, P):
        return P[:, 0], P[:, 2]

    def back(self, P):
        return P[:, 0], P[:, 2]


def region_attrs(obj, ctx_like=None):
    """Per-vertex region weights from bone vertex groups (head, neck, torso, armL, armR, handL, handR)."""
    me = obj.data
    names = {g.index: g.name for g in obj.vertex_groups}
    keys = {"rhead": ("Head", "HeadTop_End", "LeftEye", "RightEye"), "rneck": ("Neck",),
            "rtorso": ("Spine", "Spine1", "Spine2", "LeftShoulder", "RightShoulder", "Hips", "LeftBreast", "RightBreast"),
            "rarmL": ("LeftArm", "LeftForeArm"), "rarmR": ("RightArm", "RightForeArm"), "rhandL": ("LeftHand",), "rhandR": ("RightHand",)}
    arr = {k: np.zeros(len(me.vertices)) for k in keys}
    for v in me.vertices:
        for g in v.groups:
            n = names.get(g.group, "")
            if not n.startswith("mixamorig:"):
                continue
            b = n[10:]
            for k, bl in keys.items():
                if b in bl or (k in ("rhandL", "rhandR") and b.startswith(bl[0])):
                    arr[k][v.index] += g.weight
    for k, a in arr.items():
        gear.set_attr(obj, k, a)
    return list(keys)


# ============================================================================= designs

CYAN, MAG, VIO = (0.0, 0.9, 1.0), (1.0, 0.17, 0.84), (0.55, 0.36, 1.0)


def design(cid, did, ch, rng):
    """Returns list of (fn(P, A) -> (X, Y, mask), Pat) and the glow colours (A, B)."""
    L = ch.L
    out = []
    hc = ch.hc
    nz0, nz1 = ch.neck0[2], ch.neck1[2]
    if cid == "kael":
        cols = (CYAN, MAG)
        if did == "circuit_neck":
            p = Pat()
            # bus of traces from the right collarbone up the right side of the neck towards the ear
            p.bus((-0.035, nz0 - 0.03), [math.pi / 2, math.pi * 0.75, math.pi / 2], [0.04, 0.018, 0.05], count=5, spacing=0.0032,
                  w=0.001, glow_every=2)
            for k in range(9):
                p.trace(rng, (-0.03 - rng.uniform(0, 0.03), nz0 - 0.02 + rng.uniform(0, 0.09)), math.pi * rng.choice([0.5, 0.75, 1.0]), 4,
                        (0.004, 0.009), 0.0009, 1 if k % 3 == 0 else 0, (-0.12, 0.0, nz0 - 0.05, nz1 + 0.04))
            for k in range(4):
                p.dot(-0.05 - 0.006 * k, nz0 + 0.025 + 0.012 * k, 0.0022, 0.0008, 1)
            out.append((lambda P, A: (*ch.neck(P)[:2], (A["rneck"] + A["rtorso"] * 0.5 > 0.4) & (P[:, 0] < 0.012)), p))
            q = Pat()  # behind the right ear up to the temple (side projection, character's right)
            q.bus((0.035, -0.05), [math.pi * 0.62, math.pi * 0.75, math.pi * 0.9], [0.035, 0.03, 0.03], count=3, spacing=0.003, w=0.0009,
                  glow_every=2)
            for k in range(5):
                q.trace(rng, (0.02 - 0.012 * k, -0.01 + 0.008 * k), math.pi * 0.75, 3, (0.004, 0.008), 0.0008, 1 if k == 2 else 0)
            out.append((lambda P, A: (*ch.side(P), (A["rhead"] > 0.5) & (P[:, 0] < -0.05)), q))
        elif did == "tech_tribal":
            p = Pat()
            # sweeping blades from the nape round the left side of the neck and up behind the left ear (side chart)
            base = [(0.06, -0.12), (0.05, -0.1), (0.04, -0.08), (0.03, -0.06)]
            tips = [(-0.01, -0.03), (-0.025, 0.0), (-0.035, 0.03), (-0.03, 0.06)]
            for (a, b_), wd in zip(zip(base, tips), (0.03, 0.026, 0.022, 0.018)):
                mid = p.blade(a, b_, wd, bend=-0.35, hook=0.15)
                p.line(mid, 0.0011, 1)
            for k in range(3):
                p.blade((0.075, -0.13 + 0.02 * k), (0.11, -0.06 + 0.03 * k), 0.016, bend=0.4)
            p.dot(0.05, -0.04, 0.004, 0.0012, 1)
            out.append((lambda P, A: (*ch.side(P), (A["rhead"] + A["rneck"] > 0.5) & (P[:, 0] > 0.035)), p))
        elif did == "glyph_collar":
            p = Pat()
            zc = nz0 + (nz1 - nz0) * 0.55
            p.line([(-0.2, zc - 0.012), (0.2, zc - 0.012)], 0.0009, 0)
            p.line([(-0.2, zc + 0.013), (0.2, zc + 0.013)], 0.0009, 0)
            for k, x in enumerate(np.arange(-0.16, 0.161, 0.0165)):
                p.glyph(rng, x, zc, 0.012, 0, frame=False, glow_layer=1 if k % 3 == 0 else None)
            out.append((lambda P, A: (*ch.neck(P)[:2], A["rneck"] + A["rhead"] * 0.3 > 0.4), p))
            q = Pat()
            for k in range(4):
                q.glyph(rng, 0.03, -0.035 - 0.014 * k, 0.011, 0, frame=True, glow_layer=1 if k == 1 else None)
            out.append((lambda P, A: (*ch.side(P), (A["rhead"] > 0.5) & (P[:, 0] < -0.05)), q))
        elif did == "face_lines":
            p = Pat()
            e = ch.eye
            for sg in (1, -1):
                ex = L["LeftEye"][0] * sg
                y0 = e[2] - 0.022
                p.line([(ex - sg * 0.012, y0), (ex + sg * 0.006, y0 - 0.004), (ex + sg * 0.03, y0 + 0.006), (ex + sg * 0.05, y0 + 0.024)], 0.0011, 1)
                p.line([(ex - sg * 0.004, y0 - 0.008), (ex + sg * 0.014, y0 - 0.012), (ex + sg * 0.034, y0 - 0.004)], 0.0008, 0)
                for k in range(3):
                    p.dot(ex + sg * (0.04 + 0.006 * k), y0 - 0.014 - 0.004 * k, 0.0012, 0, 0)
                p.chevrons(ex + sg * 0.046, e[2] - 0.05, 2, 0.006, 0.0011, 0)
            p.line([(0, e[2] - 0.11), (0, e[2] - 0.128)], 0.0016, 0)
            p.dot(0, e[2] - 0.133, 0.0018, 0, 1)
            p.line([(0, e[2] + 0.045), (0, e[2] + 0.06)], 0.0011, 1)
            p.dot(0, e[2] + 0.066, 0.0021, 0.0008, 0)
            out.append((lambda P, A: (*ch.front(P), (A["rhead"] > 0.5) & (P[:, 1] < ch.eye[1] + 0.035)), p))
        elif did == "spine_piece":
            p = Pat()
            z0 = L["Spine"][2] - 0.05
            z1 = nz1 + 0.03
            p.line([(0, z0), (0, z1)], 0.0022, 0)
            p.line([(0, z0 + 0.02), (0, z1 - 0.02)], 0.0008, 1)
            zs = np.linspace(z0 + 0.03, z1 - 0.03, 15)
            for k, z in enumerate(zs):
                wdt = 0.012 + 0.05 * math.sin(math.pi * (z - z0) / (z1 - z0)) ** 1.5 * (1 if z < nz0 else 0.25)
                for sg in (1, -1):
                    p.line([(sg * 0.004, z), (sg * wdt * 0.5, z + 0.006), (sg * wdt, z - 0.002)], 0.0011, 1 if k % 3 == 0 else 0)
                    p.dot(sg * wdt, z - 0.002, 0.0016, 0.0007, 0)
                p.dot(0, z, 0.0032, 0.0012, 0)
            for sg in (1, -1):
                for k in range(3):
                    p.blade((sg * 0.02, nz0 - 0.02 - 0.03 * k), (sg * (0.12 - 0.02 * k), nz0 + 0.03 - 0.05 * k), 0.016, bend=0.2 * sg)
            out.append((lambda P, A: (*ch.back(P), (P[:, 1] > ch.L["Spine2"][1] - 0.005) & (A["rtorso"] + A["rneck"] + A["rhead"] > 0.5) & (P[:, 2] < ch.hc[2])), p))
        elif did == "full_sleeve":
            p = Pat()
            Lu = np.linalg.norm(L["RightForeArm"] - L["RightArm"]); Lt = Lu + np.linalg.norm(L["RightHand"] - L["RightForeArm"])
            # hex armour cells + circuit seams
            hx_r = 0.011
            for j, y in enumerate(np.arange(-0.02, Lt, hx_r * 1.5)):
                for i, x in enumerate(np.arange(-0.12, 0.12, hx_r * 1.732)):
                    xx = x + (hx_r * 0.866 if j % 2 else 0)
                    if rng.random() < 0.55:
                        pts = [(xx + hx_r * math.cos(a), y + hx_r * math.sin(a)) for a in np.linspace(math.pi / 6, math.pi / 6 + 2 * math.pi, 7)]
                        p.line(pts, 0.0009, 1 if rng.random() < 0.12 else 0)
                        if rng.random() < 0.25:
                            p.poly(pts[:-1], 0)
            for k in range(14):
                p.trace(rng, (rng.uniform(-0.1, 0.1), rng.uniform(0, Lt)), math.pi / 2 * rng.choice([1, -1]), 6, (0.008, 0.016), 0.0011,
                        1 if k % 4 == 0 else 0)
            out.append((lambda P, A: (lambda X, Y, r, a_, b_: (X, Y, (A["rarmR"] > 0.35) & (Y > -0.03) & (Y < b_ + 0.01) & (r < 0.08)))(*ch.arm(P, -1)), p))
            q = Pat()  # continues over the shoulder up the right side of the neck
            q.bus((-0.07, nz0 - 0.04), [math.pi * 0.6, math.pi / 2], [0.03, 0.05], count=4, spacing=0.004, w=0.0011, glow_every=2)
            for k in range(3):
                q.blade((-0.08 - 0.01 * k, nz0 - 0.03), (-0.04 - 0.008 * k, nz0 + 0.06 - 0.01 * k), 0.014, bend=0.3)
            out.append((lambda P, A: (*ch.neck(P)[:2], (A["rneck"] + A["rtorso"] > 0.4) & (P[:, 0] < 0.0) & (P[:, 2] > nz0 - 0.08)), q))
        elif did == "throat_sigil":
            p = Pat()
            zc = nz0 + (nz1 - nz0) * 0.42
            for r_, w_, ly in ((0.019, 0.0013, 0), (0.0145, 0.0008, 1), (0.007, 0.0011, 0)):
                p.dot(0.0, zc, r_, w_, ly)
            for k in range(8):
                a_ = k * math.pi / 4 + math.pi / 8
                p.line([(math.cos(a_) * 0.0075, zc + math.sin(a_) * 0.0075), (math.cos(a_) * 0.0145, zc + math.sin(a_) * 0.0145)], 0.0009,
                       1 if k % 2 else 0)
                p.dot(math.cos(a_) * 0.024, zc + math.sin(a_) * 0.024, 0.0014, 0, 0)
            for sg in (1, -1):
                p.line([(sg * 0.02, zc), (sg * 0.045, zc), (sg * 0.06, zc + 0.012)], 0.0011, 0)
                p.dot(sg * 0.062, zc + 0.014, 0.0018, 0.0007, 1)
            out.append((lambda P, A: (*ch.neck(P)[:2], A["rneck"] + A["rhead"] * 0.3 > 0.4), p))
        elif did == "hex_temple":
            p = Pat()
            hr = 0.0065
            for j in range(9):
                for i in range(9):
                    cx = -0.045 + i * hr * 1.732 + (hr * 0.866 if j % 2 else 0)
                    cy = -0.04 + j * hr * 1.5
                    fall = math.hypot(cx + 0.005, cy - 0.005)
                    if fall > 0.05 or rng.random() < fall / 0.06:
                        continue
                    pts = [(cx + hr * math.cos(a_), cy + hr * math.sin(a_)) for a_ in np.linspace(math.pi / 6, math.pi / 6 + 2 * math.pi, 7)]
                    p.line(pts, 0.0008, 1 if rng.random() < 0.18 else 0)
                    if rng.random() < 0.2:
                        p.poly(pts[:-1], 0)
            for k in range(4):
                p.trace(rng, (0.03, -0.03 + 0.012 * k), math.pi * 0.0, 4, (0.005, 0.01), 0.0009, 1 if k == 1 else 0)
            out.append((lambda P, A: (*ch.side(P), (A["rhead"] > 0.5) & (np.abs(P[:, 0]) > 0.045)), p))
    else:
        cols = (MAG, VIO)
        if did == "neon_vine":
            p = Pat()
            Lu = np.linalg.norm(L["LeftForeArm"] - L["LeftArm"]); Lt = Lu + np.linalg.norm(L["LeftHand"] - L["LeftForeArm"])
            ys = np.linspace(Lt + 0.03, -0.02, 90)
            xs = 0.03 * np.sin(ys / 0.09 * math.pi) - 0.005
            stem = list(zip(xs, ys))
            p.line(stem, 0.0022, 0, taper=0.5)
            p.line(stem[5:-5], 0.0008, 1)
            for k in range(1, 17):
                i = int(k * len(stem) / 17)
                x, y = stem[i]
                sg = 1 if k % 2 else -1
                tip = (x + sg * rng.uniform(0.02, 0.032), y + rng.uniform(-0.03, -0.012))
                mid = p.blade((x, y), tip, 0.012, bend=0.5 * sg)
                p.line(mid[1:6], 0.0007, 1 if k % 3 else 2)
                if k % 4 == 0:
                    ang = np.linspace(0, 3.5 * math.pi, 18)
                    rr = np.linspace(0.008, 0.002, 18)
                    p.line([(x - sg * 0.006 + sg * r_ * math.cos(a_), y + r_ * math.sin(a_)) for a_, r_ in zip(ang, rr)], 0.0008, 0)
            out.append((lambda P, A: (lambda X, Y, r, a_, b_: (X, Y, (A["rarmL"] + A["rhandL"] > 0.35) & (Y > -0.03) & (r < 0.08)))(*ch.arm(P, 1)), p))
        elif did == "circuit_sleeve":
            p = Pat()
            Lu = np.linalg.norm(L["RightForeArm"] - L["RightArm"]); Lt = Lu + np.linalg.norm(L["RightHand"] - L["RightForeArm"])
            for k in range(4):
                x0 = -0.05 + 0.033 * k
                p.bus((x0, Lt + 0.005), [-math.pi / 2, -math.pi * 0.25 if k % 2 else -math.pi * 0.75, -math.pi / 2], [0.05, 0.02, 0.09],
                      count=3, spacing=0.0028, w=0.0009, glow_every=3 if k % 2 else 0, glow_layer=2)
            for k in range(22):
                p.trace(rng, (rng.uniform(-0.09, 0.09), rng.uniform(Lu * 0.3, Lt)), math.pi / 2 * rng.choice([1, -1, 0, 2]), 6, (0.006, 0.012),
                        0.0009, 2 if k % 5 == 0 else 0)
            for k in range(5):
                cx, cy = rng.uniform(-0.05, 0.05), rng.uniform(Lu * 0.5, Lt - 0.03)
                w_, h_ = rng.uniform(0.008, 0.014), rng.uniform(0.01, 0.018)
                p.line([(cx - w_, cy - h_), (cx + w_, cy - h_), (cx + w_, cy + h_), (cx - w_, cy + h_), (cx - w_, cy - h_)], 0.001, 0)
                for j in range(4):
                    p.line([(cx - w_, cy - h_ + (j + 0.5) * h_ / 2), (cx - w_ - 0.004, cy - h_ + (j + 0.5) * h_ / 2)], 0.0008, 0)
                    p.line([(cx + w_, cy - h_ + (j + 0.5) * h_ / 2), (cx + w_ + 0.004, cy - h_ + (j + 0.5) * h_ / 2)], 0.0008, 0)
                p.dot(cx, cy, 0.003, 0, 2)
            out.append((lambda P, A: (lambda X, Y, r, a_, b_: (X, Y, (A["rarmR"] > 0.35) & (Y > -0.03) & (r < 0.08)))(*ch.arm(P, -1)), p))
        elif did == "glyph_sleeves":
            for side in (1, -1):
                p = Pat()
                Lu = np.linalg.norm(L["LeftForeArm"] - L["LeftArm"]); Lt = Lu + np.linalg.norm(L["LeftHand"] - L["LeftForeArm"])
                xc = -0.035
                for k, y in enumerate(np.arange(Lu + 0.03, Lt - 0.015, 0.017)):
                    p.glyph(rng, xc, y, 0.012, 0, frame=k % 3 != 1, glow_layer=1 if k % 2 == 0 else None)
                p.line([(xc - 0.012, Lu + 0.02), (xc - 0.012, Lt - 0.012)], 0.0007, 0)
                p.line([(xc + 0.012, Lu + 0.02), (xc + 0.012, Lt - 0.012)], 0.0007, 0)
                for yb, ly in ((Lt - 0.004, 1), (Lt - 0.009, 0)):
                    p.line([(-0.15, yb), (0.15, yb)], 0.0012, ly)
                out.append(((lambda s: lambda P, A: (lambda X, Y, r, a_, b_: (X, Y, (A["rarmL" if s > 0 else "rarmR"] + A["rhandL" if s > 0 else "rhandR"] > 0.35) & (Y > -0.03) & (r < 0.08)))(*ch.arm(P, s)))(side), p))
        elif did == "neck_lines":
            p = Pat()
            p.line([(0, nz0 - 0.005), (0, nz1 - 0.03)], 0.0011, 0)
            for k, z in enumerate(np.linspace(nz0 + 0.005, nz1 - 0.04, 5)):
                p.dot(0, z, 0.0016 + 0.0004 * (k % 2), 0.0006 if k % 2 else 0, 1 if k % 2 else 0)
            for sg in (1, -1):
                p.line([(sg * 0.06, nz0 - 0.01), (sg * 0.075, nz0 + 0.03), (sg * 0.07, nz1 - 0.01)], 0.0009, 1)
                p.line([(sg * 0.068, nz0 - 0.006), (sg * 0.083, nz0 + 0.03), (sg * 0.079, nz1 - 0.012)], 0.0007, 0)
            out.append((lambda P, A: (*ch.neck(P)[:2], A["rneck"] + A["rtorso"] * 0.6 > 0.4), p))
            q = Pat()
            e = ch.eye
            for sg in (1, -1):
                ex = L["LeftEye"][0] * sg
                for k in range(4):
                    q.dot(ex + sg * (0.002 + 0.006 * k), e[2] - 0.021 - 0.0025 * k, 0.0011 - 0.0001 * k, 0, 2 if k == 0 else 0)
                q.line([(ex + sg * 0.018, e[2] + 0.002), (ex + sg * 0.03, e[2] + 0.006), (ex + sg * 0.042, e[2] + 0.018)], 0.0008, 1)
            out.append((lambda P, A: (*ch.front(P), (A["rhead"] > 0.5) & (P[:, 1] < ch.eye[1] + 0.035)), q))
        elif did == "back_piece":
            p = Pat()
            zc = L["Spine2"][2]
            for sg in (1, -1):
                for k in range(6):
                    a = (sg * 0.012, zc + 0.04 - 0.012 * k)
                    tip = (sg * (0.17 - 0.012 * k), zc + 0.1 - 0.045 * k)
                    mid = p.blade(a, tip, 0.024 - 0.002 * k, bend=0.3 * sg)
                    p.line(mid[1:7], 0.0009, 1 if k % 2 == 0 else 2)
            p.line([(0, L["Spine"][2] - 0.04), (0, nz1 - 0.01)], 0.0018, 0)
            for z in np.arange(L["Spine"][2] - 0.02, nz1 - 0.01, 0.022):
                p.dot(0, z, 0.003, 0.001, 1)
            out.append((lambda P, A: (*ch.back(P), (P[:, 1] > ch.L["Spine2"][1] - 0.005) & (A["rtorso"] + A["rneck"] > 0.4) & (P[:, 2] < nz1 + 0.01)), p))
        elif did == "cheek_circuit":
            p = Pat()
            e = ch.eye
            for sg in (1, -1):
                ex = L["LeftEye"][0] * sg
                pts = [(ex - sg * 0.004, e[2] - 0.03), (ex + sg * 0.012, e[2] - 0.034), (ex + sg * 0.03, e[2] - 0.022), (ex + sg * 0.042, e[2] - 0.004),
                       (ex + sg * 0.046, e[2] + 0.02)]
                p.line(pts, 0.0009, 1)
                for k, q in enumerate(pts[1:4]):
                    p.dot(q[0], q[1], 0.0014, 0.0006, 0 if k % 2 else 2)
                p.line([(ex + sg * 0.03, e[2] - 0.022), (ex + sg * 0.036, e[2] - 0.036), (ex + sg * 0.03, e[2] - 0.05)], 0.0007, 0)
            p.line([(0, e[2] + 0.04), (0, e[2] + 0.052)], 0.0009, 1)
            p.dot(0, e[2] + 0.034, 0.0016, 0, 2)
            out.append((lambda P, A: (*ch.front(P), (A["rhead"] > 0.5) & (P[:, 1] < ch.eye[1] + 0.04)), p))
        elif did == "wrist_bands":
            for side in (1, -1):
                p = Pat()
                Lu = np.linalg.norm(L["LeftForeArm"] - L["LeftArm"]); Lt = Lu + np.linalg.norm(L["LeftHand"] - L["LeftForeArm"])
                for k, y in enumerate((Lt - 0.012, Lt - 0.03, Lt - 0.05)):
                    p.line([(-0.16, y), (0.16, y)], 0.0013 if k != 1 else 0.0008, 0 if k != 1 else 1)
                for x in np.arange(-0.13, 0.13, 0.016):
                    p.chevrons(x, Lt - 0.024, 1, 0.004, 0.0008, 0)
                    p.dot(x + 0.008, Lt - 0.04, 0.0011, 0, 2 if int(x * 1000) % 3 == 0 else 0)
                out.append(((lambda s: lambda P, A: (lambda X, Y, r, a_, b_: (X, Y, (A["rarmL" if s > 0 else "rarmR"] + A["rhandL" if s > 0 else "rhandR"] > 0.35) & (Y > Lu) & (r < 0.07)))(*ch.arm(P, s)))(side), p))
        elif did == "tech_tribal":
            p = Pat()
            Lu = np.linalg.norm(L["LeftForeArm"] - L["LeftArm"]); Lt = Lu + np.linalg.norm(L["LeftHand"] - L["LeftForeArm"])
            for k in range(5):
                a = (0.06 - 0.02 * k, -0.02 + 0.012 * k)
                tip = (0.0 - 0.025 * k + 0.05, Lu * (0.6 + 0.25 * k / 4) + 0.06)
                mid = p.blade(a, tip, 0.03 - 0.003 * k, bend=0.25 * (1 if k % 2 else -1), hook=0.05)
                p.line(mid[1:7], 0.0009, 1 if k % 2 == 0 else 2)
            for k in range(3):
                p.blade((-0.03 + 0.03 * k, Lt - 0.02), (-0.02 + 0.03 * k, Lu + 0.03), 0.014, bend=0.2)
            out.append((lambda P, A: (lambda X, Y, r, a_, b_: (X, Y, (A["rarmL"] > 0.35) & (Y > -0.05) & (r < 0.08)))(*ch.arm(P, 1)), p))
            q = Pat()  # collarbone sweep (front chart)
            sh = L["LeftShoulder"]
            for k in range(3):
                mid = q.blade((0.02 + 0.015 * k, sh[2] - 0.035 - 0.012 * k), (0.16 + 0.01 * k, sh[2] + 0.005 - 0.01 * k), 0.016, bend=-0.3)
                q.line(mid[1:6], 0.0008, 1)
            out.append((lambda P, A: (*ch.front(P), (A["rtorso"] > 0.4) & (P[:, 0] > 0.0) & (P[:, 1] < ch.L["Spine2"][1]) & (P[:, 2] > sh[2] - 0.09)), q))
    return out, cols


DESIGNS = {
    "kael": [("circuit_neck", "Circuit Traces", ["neck", "temple"]), ("tech_tribal", "Tech-Tribal", ["neck", "scalp side"]),
             ("glyph_collar", "Glyph Collar", ["neck", "behind ear"]), ("face_lines", "Face Lines", ["face"]),
             ("spine_piece", "Spine Back Piece", ["nape (rest under outfit)"]), ("full_sleeve", "Full Sleeve", ["neck (arm part under the jacket sleeve)"]),
             ("throat_sigil", "Throat Sigil", ["throat"]), ("hex_temple", "Hex Temple", ["temples / shaved sides"])],
    "lyra": [("neon_vine", "Neon Vine Sleeve", ["left forearm", "left hand"]), ("circuit_sleeve", "Circuit Sleeve", ["right forearm"]),
             ("glyph_sleeves", "Glyph Sleeves", ["both forearms", "wrists"]), ("neck_lines", "Neck & Face Lines", ["neck", "face"]),
             ("back_piece", "Winged Back Piece", ["nape / upper back neckline"]), ("tech_tribal", "Tech-Tribal", ["left arm", "collarbone"]),
             ("cheek_circuit", "Cheek Circuit", ["face"]), ("wrist_bands", "Wrist Bands", ["both wrists"])],
}
FOCUS = {  # thumbnail framing: (focus: bone or 'eye' / 'neck' / 'back', yaw, pitch, distance)
    "circuit_neck": ("neck", -70, 5, 0.55), "tech_tribal_kael": ("neck", 110, 5, 0.6), "glyph_collar": ("neck", -30, 5, 0.55),
    "face_lines": ("eye", 15, 0, 0.42), "spine_piece": ("back", 180, 4, 0.66), "full_sleeve": ("armR", -60, 5, 0.95),
    "neon_vine": ("farmL", 58, 2, 0.36), "circuit_sleeve": ("farmR", -58, 2, 0.36), "glyph_sleeves": ("farmL", 52, 2, 0.36),
    "neck_lines": ("neck", 20, 3, 0.55), "throat_sigil": ("neck", 10, 5, 0.5), "hex_temple": ("eye", 70, 8, 0.5),
    "cheek_circuit": ("eye", 18, 0, 0.42), "wrist_bands": ("farmL", 58, 2, 0.32), "back_piece": ("back", 180, 4, 0.62), "tech_tribal_lyra": ("armL", 135, 6, 0.62),
}


def evaluate(regs, P, A, rng):
    ink = np.zeros(len(P), np.float32)
    glow = np.zeros((len(P), 3), np.float32)
    for fn, pat in regs[0]:
        X, Y, m = fn(P, A)
        idx = np.where(m)[0]
        if not len(idx):
            continue
        cv = pat.eval(np.asarray(X)[idx], np.asarray(Y)[idx])
        ink[idx] = np.maximum(ink[idx], np.maximum(cv[0], 0.45 * np.maximum(cv[1], cv[2])))
        for li, col in ((1, regs[1][0]), (2, regs[1][1])):
            glow[idx] = np.maximum(glow[idx], cv[li][:, None] * np.array(col, np.float32))
    return ink, glow


def raster_maps(obj, regs, size, rng, mat):
    keys = region_attrs(obj)
    T = TB.raster([obj], mat, size, attrs=tuple(keys))
    idx = np.where(T.cov)[0]
    P = T.P[idx].astype(np.float64)
    A = {k: T.A[k][idx] for k in keys}
    ink, glow = evaluate(regs, P, A, rng)
    # subtle healed-ink variation
    ink = ink * (0.86 + 0.14 * TB.fbm3(P, 180.0, 2, 4.0))
    inkv = np.full(size * size, 0.5, np.float32)
    inkv[idx] = 0.5 * (1 - 0.82 * ink)
    g = np.zeros((size * size, 3), np.float32)
    g[idx] = glow
    cov = T.cov.reshape(size, size)
    iv = TB.dilate(inkv.reshape(size, size, 1), cov, 4)[..., 0]
    iv = np.where(cov, inkv.reshape(size, size), iv)
    gv = TB.dilate(g.reshape(size, size, 3), cov, 4)
    return iv, gv, float((ink > 0.3).mean()), int((ink > 0.3).sum())


def preview_material(name, skin_png, ink_png, glow_png, normal_png=None):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(b.outputs[0], out.inputs[0])
    sk = texstage.img_node(nt, skin_png, non_color=False)
    ik = texstage.img_node(nt, ink_png, non_color=True)
    gl = texstage.img_node(nt, glow_png, non_color=False)
    mul = nt.nodes.new("ShaderNodeVectorMath"); mul.operation = "MULTIPLY"
    sc = nt.nodes.new("ShaderNodeVectorMath"); sc.operation = "SCALE"; sc.inputs[3].default_value = 2.0
    nt.links.new(ik.outputs["Color"], sc.inputs[0])
    nt.links.new(sk.outputs["Color"], mul.inputs[0]); nt.links.new(sc.outputs[0], mul.inputs[1])
    nt.links.new(mul.outputs[0], b.inputs["Base Color"])
    nt.links.new(gl.outputs["Color"], b.inputs["Emission Color"])
    b.inputs["Emission Strength"].default_value = 4.0
    b.inputs["Roughness"].default_value = 0.5
    b.inputs["Subsurface Weight"].default_value = 0.12
    b.inputs["Subsurface Radius"].default_value = (0.9, 0.35, 0.2)
    b.inputs["Subsurface Scale"].default_value = 0.006
    b.inputs["Specular IOR Level"].default_value = 0.35
    if normal_png:
        nn = texstage.img_node(nt, normal_png)
        nm = nt.nodes.new("ShaderNodeNormalMap"); nm.inputs["Strength"].default_value = 0.5
        nt.links.new(nn.outputs["Color"], nm.inputs["Color"]); nt.links.new(nm.outputs[0], b.inputs["Normal"])
    return m


def mh_skin(gender):
    folder = {"male": "toigo_light_skin_male_bronze", "female": "toigo_light_skin_female_bronze"}[gender]
    d = os.path.join(C.MPFB_DATA, "skins", folder)
    f = [x for x in os.listdir(d) if x.lower().endswith(".png") and "nrm" not in x.lower() and "spec" not in x.lower()]
    return os.path.join(d, f[0])


def focus_point(ch, key):
    L = ch.L
    if key == "neck":
        return (ch.neck0 + ch.neck1) * 0.5 + np.array((0, 0, 0.02))
    if key == "eye":
        return ch.eye + np.array((0, 0.0, -0.02))
    if key == "back":
        return np.array((0.0, L["Spine2"][1], L["Spine2"][2] + 0.08))
    if key == "armL":
        return (L["LeftForeArm"] * 0.6 + L["LeftArm"] * 0.4)
    if key == "armR":
        return (L["RightForeArm"] * 0.6 + L["RightArm"] * 0.4)
    if key == "farmL":
        return (L["LeftForeArm"] * 0.45 + L["LeftHand"] * 0.55)
    if key == "farmR":
        return (L["RightForeArm"] * 0.45 + L["RightHand"] * 0.55)
    return ch.hc


def main():
    a = C.args()
    cid = a[0]
    sel = a[1].split(",") if len(a) > 1 and not a[1].startswith("--") else [d[0] for d in DESIGNS[cid]]
    rig, body = C.load_ref(cid)
    ctx = gear.Ctx(body, rig, C.HEROES[cid]["name"])
    ch = Charts(ctx)
    ub = bpy.data.objects["U_Body"]
    gender = C.HEROES[cid]["gender"]
    os.makedirs(OUT_DIR, exist_ok=True); os.makedirs(PREV_DIR, exist_ok=True); os.makedirs(THUMB_DIR, exist_ok=True)
    os.makedirs(os.path.join(C.CACHE, "catalog", "tattoos"), exist_ok=True)
    # preview scene: full base body (MakeHuman UVs) + eyes/brows/lashes of the base build, outfit hidden
    studio.hero_materials(cid, hide_outfit=True)
    ub.hide_render = True
    body.hide_render = False; body.hide_viewport = False
    for o in bpy.data.objects:
        if o.type == "MESH" and not o.name.startswith("U_") and o is not body:
            o.hide_render = True
    for n in ("U_Eyes", "U_Brows", "U_Lashes"):
        if n in bpy.data.objects:
            bpy.data.objects[n].hide_render = False
    hair = None
    try:
        import hair_preview
        hair = hair_preview.load_hair(cid, "edgy_caesar" if cid == "kael" else "high_ponytail")
    except Exception as ex:
        print("no preview hair", ex)
    skin_png = mh_skin(gender)
    entries = []
    for i, did in enumerate(sel):
        t0 = time.time()
        label, vis = next((l, v) for d, l, v in DESIGNS[cid] if d == did)
        rng = np.random.default_rng(1000 + i * 17 + (7 if cid == "lyra" else 0))
        regs = design(cid, did, ch, rng)
        st = rng.bit_generator.state
        iv, gv, frac, n_ink = raster_maps(ub, regs, SIZE, rng, ub.data.materials[0].name)
        ink_p = os.path.join(OUT_DIR, f"{cid}_{did}_Ink.png")
        glow_p = os.path.join(OUT_DIR, f"{cid}_{did}_Glow.png")
        C.write_png(np.stack([iv] * 3, -1), ink_p, "RGB")
        C.write_png(gv, glow_p, "RGB")
        # preview maps on the base body (MakeHuman UV)
        rng.bit_generator.state = st
        pv_i, pv_g, _, n_full = raster_maps(body, regs, 2048, rng, body.data.materials[0].name)
        pi = os.path.join(C.CACHE, f"tat_{cid}_{did}_ink_mh.png"); pg = os.path.join(C.CACHE, f"tat_{cid}_{did}_glow_mh.png")
        C.write_png(np.stack([pv_i] * 3, -1), pi, "RGB"); C.write_png(pv_g, pg, "RGB")
        m = preview_material(f"tat_{did}", skin_png, pi, pg)
        body.data.materials[0] = m
        for n in ("U_Top", "U_Pants", "U_Jacket"):
            if n in bpy.data.objects:
                bpy.data.objects[n].hide_render = True
        key = did + "_" + cid if did == "tech_tribal" else did
        fk, yaw, pitch, dist = FOCUS[key]
        fp = Vector(focus_point(ch, fk))
        studio.world_and_lights(fp, 0.6, rim=1.0, yaw=yaw)
        studio.camera(studio.view(fp, yaw, pitch, dist), fp, 70)
        thumb = os.path.join(THUMB_DIR, f"tattoo_{cid}_{did}.png")
        studio.render(thumb, 512, 256)
        prev = os.path.join(PREV_DIR, f"{cid}_{did}.png")
        studio.render(prev, 640)
        C.log(did, "visible ink texels", n_ink, "full-body ink texels", n_full, "s", round(time.time() - t0, 1))
        e = {"id": did, "label": label, "hero": cid, "ink": f"Tattoos/{cid}_{did}_Ink", "glow": f"Tattoos/{cid}_{did}_Glow",
             "thumb": f"Thumbs/tattoo_{cid}_{did}", "visibleOn": vis, "glowColors": [list(regs[1][0]), list(regs[1][1])],
             "uv": "Body UV0", "inkImport": "linear (sRGB off), Detail Albedo x2", "glowImport": "sRGB, emission mask",
             "visibleTexels": n_ink}
        with open(os.path.join(C.CACHE, "catalog", "tattoos", f"{cid}_{did}.json"), "w") as f:
            json.dump(e, f, indent=1)
    import catalog
    catalog.merge()
    C.log("done")


if __name__ == "__main__":
    main()
