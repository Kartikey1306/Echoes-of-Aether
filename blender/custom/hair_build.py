"""Hair library build: fitted hair-card styles for KAEL (20) and GIVA/lyra (14).

  blender -b --python blender/custom/hair_build.py -- <cid> [style,style,...] [--no-export] [--no-thumbs]

Per style: FBX (Resources/Characters/Custom/Hair/<cid>_<style>.fbx), the 2048 atlas
(Hair/Textures/<cid>_<style>_Hair.png, neutral grey RGBA, alpha-tested), a 256 thumbnail (Thumbs/hair_<cid>_<style>.png),
review renders (blender/custom/previews/hair/) and its catalog entry (cache/catalog/hair/).
"""
import bpy, os, sys, math, json, importlib, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from mathutils import Vector, Matrix
import common as C
import gear, texbake as TB
import hairlib as HL
import studio
from hairlib import sheet_strips
from hairlib import (flow_forward, flow_back, flow_down, flow_from, flow_to, flow_part, blend_flows, grow, shape, cut, clump,
                     Lock, build_cards, braid3, fishtail, bun as bun_geo, volume_shell, paint_tiles, paint_volume, finish_atlas,
                     card_normals, hair_weights, tangents, resample, arclen, frame, dirv)
from common import ss, nrm, nrm_rows

R_ = np.radians
OUT_DIR = os.path.join(C.CUSTOM_OUT, "Hair")
TEX_DIR = os.path.join(OUT_DIR, "Textures")
THUMB_DIR = os.path.join(C.CUSTOM_OUT, "Thumbs")
PREV_DIR = os.path.join(C.PREVIEWS, "hair")


def knots(az, pairs):
    """Piecewise-linear function of |az| (degrees) from [(az_deg, value), ...]."""
    a, v = zip(*pairs)
    return np.interp(np.degrees(np.abs(az)), a, v)


# ============================================================================= style builder


class HB:
    def __init__(self, H, ctx, cid, sid, seed=1):
        self.H, self.ctx, self.cid, self.sid = H, ctx, cid, sid
        self.rng = np.random.default_rng(seed)
        self.seed = seed
        self.locks = []
        self.part = gear.Part(sid + "_struct")
        self.hairline = "female" if cid == "lyra" else "male"
        self.hairline_soft = 4.0
        self.fade = None
        self.design = None
        self.partline = None
        self.vol_thick = lambda az, el: np.full(np.shape(az), 0.004)
        self.vol_tex = "straight"
        self.vol_lum = 0.7
        self.flow = lambda P: flow_down(H, P)
        self.tiles = ["straight"] * 24
        self.lum_mul = [0.86 + 0.14 * (k % 16) / 15 for k in range(16)] + [0.92] * 8
        self.kind = "rigid"
        self.cutoff = 0.4
        self.notes = ""
        self.nap = True
        self.face_clip = True
        self.nap_n = 420
        self.nap_len = 0.02
        self.nap_gap = 0.012
        self.nap_tiles = (0, 7)

    # ------------------------------------------------------------------ guards
    def guard_brow(self, margin=0.02, jitter=0.006, sides=0.0):
        """Fringe stops at the brow line (front of the face); returns None to end the lock."""
        H = self.H
        ph = self.rng.uniform(0, 6.28)

        def g(q, p):
            lim = H.brow_z + margin + jitter * (math.sin(q[0] * 260 + ph) * 0.6 + math.sin(q[0] * 731 + ph * 2) * 0.4)
            if q[1] < H.eye[1] + 0.03 and abs(q[0]) < H.face_hw + 0.012 + sides and q[2] < lim:
                return None
            return q
        return g

    def guard_face(self, pad=0.012, cover=None):
        """Long hair: never in front of the face. Points inside the face box are projected to its nearest side
        (outwards in x or backwards in y); cover=(sign, z_min) lets a fringe cover one eye."""
        H = self.H

        def g(q, p):
            if q[2] < H.brow_z + 0.012 and q[2] > H.jaw_z - 0.06:
                hw = H.face_hw + pad
                ylim = H.eye[1] + 0.045
                if abs(q[0]) < hw and q[1] < ylim:
                    if cover is not None and np.sign(q[0] + 1e-6) == cover[0] and q[2] > cover[1]:
                        return q
                    q = q.copy()
                    dx = hw - abs(q[0]); dy = ylim - q[1]
                    if dx < dy * 1.6:
                        q[0] = math.copysign(hw, q[0] if abs(q[0]) > 1e-4 else (p[0] if abs(p[0]) > 1e-4 else 1.0))
                    else:
                        q[1] = ylim
            return q
        return g

    # ------------------------------------------------------------------ locks
    def locks_(self, n, where, length, flow=None, segs=14, lift=0.2, stiff=1.0, grav=0.3, off=(0.004, 0.012), hug=0.0,
               rise=0.0, width=(0.012, 0.005), tiles=(0, 15), wave=None, curl=None, flick=0.0, frizz=0.0, clump_=0.0,
               cutf=None, guard=None, min_d=0.008, attract=None, att_k=0.0, stop_r=0.0, mode="flat", jitter=0.12,
               dir_jitter=0.12, body_clear=0.006, curve=None, ramp=(0.08, 0.4), weight=None, ringlet_w=0.9, lift_fn=None):
        H = self.H
        mask, az, el = H.scalp(self.hairline)
        co = self.ctx.basis
        m = mask & where(az, el, co)
        roots, nr = H.sample_roots(m, n, min_d, self.seed + len(self.locks) * 7 + n, weight=weight)
        if not len(roots):
            print("no roots for", self.sid)
            return []
        F0 = (flow or self.flow)(roots)
        rng = self.rng
        new = []
        for i, (p, nn) in enumerate(zip(roots, nr)):
            a, e, _ = H.angles(p[None])
            a, e = a[0], e[0]
            L = (length(a, e, p) if callable(length) else length) * rng.uniform(1 - jitter, 1 + jitter)
            if L < 0.004:
                continue
            offr = off(a, e, p) if callable(off) else off
            o = rng.uniform(*offr)
            f = (o - offr[0]) / max(offr[1] - offr[0], 1e-9)
            d = F0[i] + rng.normal(0, dir_jitter, 3)
            nrad = H.radial(p[None])[0]
            nn = nrm(nn * 0.4 + nrad * 0.6)
            lf = lift_fn(a, e, p) if lift_fn else lift
            att = attract(p) if callable(attract) else attract
            if callable(attract) and flow is None:
                d = H.tangent(p[None], (att - p)[None])[0] + rng.normal(0, dir_jitter, 3)
            P = grow(H, p, nn, L, d, segs, lf, stiff, grav, o, hug, rise, att, att_k, stop_r, clear=o * 0.7, guard=guard,
                     body_clear=body_clear, curve=curve)
            if cutf is not None:
                P = cut(P, cutf)
            if len(P) < 3:
                continue
            P2, side, lockn = shape(H, P, rng, wave, curl, flick, frizz, clear=o * 0.6, body_clear=body_clear, ramp=ramp)
            if self.face_clip:
                bad = ((P2[:, 1] < H.eye[1] + 0.012) & (P2[:, 2] < H.brow_z + 0.005) & (P2[:, 2] > H.jaw_z - 0.09)
                       & (np.abs(P2[:, 0]) < H.face_hw + 0.03))
                if bad.any():
                    k_ = int(np.argmax(bad))
                    if k_ < 3:
                        continue
                    P2 = P2[:k_]
                    if side is not None:
                        side = side[:k_]
                    lockn = lockn[:k_]
            lo, hi = tiles
            t = int(np.clip(lo + round(f * (hi - lo) + rng.uniform(-1.2, 1.2)), lo, hi))
            w0 = width[0] * rng.uniform(0.8, 1.2)
            if curl is not None:
                lk = Lock(P2, f, t, curl[1] * ringlet_w, mode="ringlet", w_tip=curl[1] * ringlet_w * 0.7)
                lk.attrs = (side, lockn)
            else:
                lk = Lock(P2, f, t, w0, mode=mode, w_tip=width[1] * rng.uniform(0.8, 1.2))
                lk.attrs = None
            new.append(lk)
        if clump_:
            clump(new, frac=0.3, strength=clump_, seed=self.seed)
        self.locks += new
        return new

    # ------------------------------------------------------------------ structures
    def anchor(self, az_deg, el_deg, h=0.0):
        return self.H.surf(np.array(R_(az_deg)), np.array(R_(el_deg)), h)

    def gather(self, n, where, A, off=(0.003, 0.009), width=(0.016, 0.012), tiles=(0, 15), stop_r=0.014, hug=1.2, loose=0.0,
               segs=22, min_d=0.008, Lmax=0.32):
        """Locks combed from their roots to an anchor A along the scalp (sleek: hug high, loose 0)."""
        H = self.H
        fl = (lambda P: flow_to(H, P, A)) if not callable(A) else (lambda P: np.stack([flow_to(H, q[None], A(q))[0] for q in P]))
        return self.locks_(n, where, Lmax, flow=fl, segs=segs, lift=0.02, stiff=0.55, grav=0.0, off=off,
                           hug=hug, rise=0.0, width=width, tiles=tiles, attract=A, att_k=0.45, stop_r=stop_r, min_d=min_d,
                           jitter=0.0, dir_jitter=0.03 + loose * 0.2, frizz=loose * 0.0015)

    def tail(self, A, d0, L, n=80, r0=0.011, r1=0.035, segs=24, grav=0.9, stiff=1.0, wave=None, curl=None, tiles=(0, 15),
             width=(0.02, 0.01), clear=0.02, ringlet_w=0.9, end_taper=0.55, spread=None):
        H = self.H
        rng = self.rng
        d0 = nrm(d0)
        axis = grow(H, A, d0, L, d0, segs, lift=1.0, stiff=stiff, grav=grav, off=0.0, hug=0.0, clear=0.0, body_clear=clear)
        axis = resample(axis, segs + 1)
        T = tangents(axis)
        ref = np.array((1.0, 0, 0))
        Av = nrm_rows(np.cross(T, ref))
        for i in range(1, len(axis)):
            a = Av[i - 1] - T[i] * np.dot(Av[i - 1], T[i])
            Av[i] = nrm(a)
        Bv = np.cross(T, Av)
        s = np.linspace(0, 1, len(axis))
        rad = r0 + (r1 - r0) * ss(0.0, 0.3, s) - r1 * (1 - end_taper) * ss(0.6, 1.0, s)
        out = []
        for k in range(n):
            rho = math.sqrt(rng.uniform(0.05, 1.0))
            ph = rng.uniform(0, 2 * math.pi) + s * rng.normal(0, 0.6)
            dirs = Av * np.cos(ph)[:, None] + Bv * np.sin(ph)[:, None]
            P = axis + dirs * (rho * rad)[:, None]
            Lk = rng.uniform(0.78, 1.0)
            m = s <= Lk
            P = P[m]
            if len(P) < 4:
                continue
            P = np.array([P[0]] + [H.collide(q, 0.002, clear * 0.7) for q in P[1:]])
            P2, side, lockn = shape(H, P, rng, wave, curl, 0.0, 0.0, clear=0.002, body_clear=clear * 0.6, ramp=(0.05, 0.3))
            f = rho
            lo, hi = tiles
            t = int(np.clip(lo + round(f * (hi - lo) + rng.uniform(-1.5, 1.5)), lo, hi))
            if curl is not None:
                lk = Lock(P2, f, t, curl[1] * ringlet_w, mode="ringlet", w_tip=curl[1] * ringlet_w * 0.7)
                lk.attrs = (side, lockn)
            else:
                Tt = tangents(P2)
                radial = nrm_rows(P2 - axis[:len(P2)])
                side_ = nrm_rows(np.cross(Tt, radial))
                lk = Lock(P2, f, t, width[0] * rng.uniform(0.8, 1.2), mode="ringlet", w_tip=width[1])
                lk.attrs = (side_, radial)
            out.append(lk)
        self.locks += out
        return axis

    def wrap(self, A, axis_dir, radius=0.013, turns=1.6, width=0.012, tile=8):
        """A lock wrapped around the base of a ponytail (hides the tie)."""
        H = self.H
        ax = nrm(axis_dir)
        ref = np.array((0, 0, 1.0)) if abs(ax[2]) < 0.9 else np.array((1.0, 0, 0))
        Av = nrm(np.cross(ax, ref)); Bv = np.cross(ax, Av)
        th = np.linspace(0, 2 * math.pi * turns, 40)
        P = np.array([A + ax * (0.004 + 0.012 * t / th[-1]) + (Av * math.cos(t) + Bv * math.sin(t)) * radius for t in th])
        rad = nrm_rows(P - (A + ax[None] * 0.01))
        lk = Lock(P, 1.0, tile, width, mode="ringlet", w_tip=width * 0.9)
        lk.attrs = (np.broadcast_to(ax, P.shape).copy(), rad)
        self.locks.append(lk)

    # ------------------------------------------------------------------ sheets (continuous curtains for long hair)
    def sheets(self, L, part_x=None, layers=((0.004, (0, 5)), (0.009, (6, 11)), (0.014, (10, 15))), az_min=42.0, az_max=178.0,
               step=3.4, wave=None, curl_amp=0.0, grav=0.85, hug=0.9, rise=0.004, guard=None, cutf=None, segs=26, crown_el=56.0,
               back_from=112.0, sides=(1, -1), tip_jitter=0.08, flick=0.0, body_clear=0.009, root_el=None, cols_per_tile=3):
        """Hair curtains from the part line (or a crown ring) down past the hairline: guides per azimuth column grown
        over the scalp towards the hairline then falling with gravity; adjacent columns joined into quad strips."""
        H = self.H
        rng = self.rng
        azs = np.arange(az_min, az_max + 1e-6, step)
        cols = []
        if -1 in sides:
            cols += [-a for a in azs[::-1]]
        if 1 in sides:
            cols += list(azs)

        def root_for(az_c, jit):
            s = 1.0 if az_c > 0 else -1.0
            a = abs(az_c)
            if part_x is not None and a <= back_from:
                t = (a - az_min) / max(back_from - az_min, 1e-6)
                th = R_(36 + t * (118 - 36) + jit)
                d = np.array((0.0, -math.cos(th), math.sin(th)))
                p = H.hc + d * 0.1
                p[0] = part_x + s * 0.005
                az_, el_, _ = H.angles(p[None])
                return H.surf(az_, el_)[0]
            e = root_el(a) if root_el else crown_el
            return H.surf(np.array([R_(s * min(a, 179.0))]), np.array([R_(e + jit)]))[0]

        for li, (off, tiles) in enumerate(layers):
            guides, normals = [], []
            ph0 = rng.uniform(0, 6.28)
            for ci, az_c in enumerate(cols):
                azj = az_c + (step * 0.5 if li % 2 else 0.0) * (1 if az_c > 0 else -1)
                azj = float(np.clip(azj, -179.5, 179.5))
                root = root_for(azj, rng.uniform(-2, 2))
                a, e, _ = H.angles(root[None])
                tgt_el = H.hairline_el(np.array(R_(azj)), self.hairline) + R_(4)
                target = H.surf(np.array([R_(azj)]), np.atleast_1d(tgt_el), off)[0]
                Lc = (L(abs(azj)) if callable(L) else L) * rng.uniform(1 - tip_jitter, 1 + tip_jitter * 0.3)
                nrad = H.radial(root[None])[0]
                d0 = H.tangent(root[None], (target - root)[None])[0]
                tz = float(target[2])
                curve = (lambda tz, target: (lambda s, p, d: nrm(target - p) * 0.6 if p[2] > tz + 0.004 else np.zeros(3)))(tz, target)
                P = grow(H, root, nrad, Lc, d0, segs, 0.03, 1.0, grav, off, hug, rise, None, 0.0, 0.0, clear=off * 0.7,
                         guard=guard, body_clear=body_clear + off * 0.5, curve=curve)
                if cutf is not None:
                    P = cut(P, cutf)
                if len(P) < 4:
                    guides.append(None); normals.append(None)
                    continue
                P = resample(P, segs + 1)
                T, S, Nn = frame(H, P)
                arc = arclen(P)
                sN = arc / max(arc[-1], 1e-6)
                if wave:
                    amp, lam = wave
                    ph = ph0 + R_(azj) * 2.2 + rng.normal(0, 0.25)
                    th = 2 * math.pi * arc / lam + ph
                    k = ss(0.15, 0.5, sN)
                    P = P + S * (amp * k * np.sin(th))[:, None] + Nn * (amp * 0.6 * k * np.cos(th) + curl_amp * k * np.sin(2 * th))[:, None]
                if flick:
                    P = P + Nn * (flick * ss(0.7, 1.0, sN) ** 2)[:, None]
                P = np.array([P[0]] + [H.collide(q, off * 0.6, body_clear + off * 0.5) for q in P[1:]])
                guides.append(P); normals.append(Nn)
            sheet_strips(self.part, guides, tiles[0], tiles[1], 0.3 + 0.2 * li, normals, cols_per_tile=cols_per_tile, max_gap=0.055,
                         rng=rng)

    # ------------------------------------------------------------------ nap (short flat hair where only the volume shows)
    def nap_pass(self):
        if not self.nap:
            return
        H = self.H
        from mathutils.kdtree import KDTree
        roots = [lk.P[0] for lk in self.locks if len(lk.P)]
        kd = KDTree(max(1, len(roots)))
        for i, p in enumerate(roots):
            kd.insert(Vector(p), i)
        kd.balance()
        fade = self.fade

        def where(az, el, P):
            ok = np.ones(len(P), bool)
            if fade is not None:
                ok &= fade(az, el, P) > 0.62
            if roots:
                ok &= np.array([kd.find(Vector(p))[2] > self.nap_gap for p in P])
            return ok
        dens = (lambda a, e, p: float(fade(np.array([a]), np.array([e]), p[None])[0])) if fade is not None else (lambda a, e, p: 1.0)
        self.locks_(self.nap_n, where, lambda a, e, p: self.nap_len * (0.6 + 0.4 * dens(a, e, p)), segs=6, lift=0.08, stiff=1.0,
                    grav=0.15, off=(0.0015, 0.004), hug=1.0, width=(0.009, 0.004), tiles=self.nap_tiles, min_d=0.0055, jitter=0.2,
                    dir_jitter=0.2)

    # ------------------------------------------------------------------ build
    def build(self):
        H = self.H
        self.nap_pass()
        mask, az, el = H.scalp(self.hairline)
        vol = volume_shell(H, self.ctx, self.sid + "_vol", mask, self.vol_thick)
        cards = build_cards(H, self.locks, self.sid + "_cards", self.rng)
        objs = [vol] + ([cards] if cards else [])
        if self.part.F:
            objs.append(self.part.build(mat_order=["Hair"], max_edge=None))
        img = np.zeros((HL.ATLAS, HL.ATLAS, 4), np.float32)
        paint_tiles(img, self.tiles, self.rng, self.lum_mul)
        st = {"flow": self.flow, "vol_tex": self.vol_tex, "fade": self.fade, "design": self.design, "part": self.partline,
              "hairline": self.hairline, "vol_lum": self.vol_lum, "hairline_soft": self.hairline_soft}
        paint_volume(H, vol, img, st, self.rng)
        atlas = finish_atlas(img)
        obj = gear.join(objs, f"{self.cid}_{self.sid}")
        for p in obj.data.polygons:
            p.use_smooth = True
        card_normals(obj, H.hc + np.array((0, 0.01, -0.01)), card_mix=0.6)
        return obj, atlas


from hair_styles import KAEL, LYRA, DEFAULTS


# ============================================================================= driver


def build_style(H, ctx, cid, sid, recipe, seed):
    b = HB(H, ctx, cid, sid, seed)
    recipe(b)
    obj, atlas = b.build()
    return b, obj, atlas


def preview_and_thumb(cid, sid, obj, tex_path, b, H):
    Hh = C.HEROES[cid]
    m = studio.hair_mat(f"prevhair_{sid}", tex_path, Hh["hair_preview"], b.cutoff)
    obj.data.materials[0] = m
    obj.hide_render = False
    hc = Vector(H.hc)
    female = cid == "lyra"
    aim = hc + Vector((0, 0, -0.035 if not female else -0.07))
    dist = 0.95 if not female else 1.25
    os.makedirs(PREV_DIR, exist_ok=True)
    os.makedirs(THUMB_DIR, exist_ok=True)
    studio.world_and_lights(hc, 0.6, rim=1.0, yaw=32)
    studio.camera(studio.view(aim, 32, 6, dist), aim, 70)
    thumb = os.path.join(THUMB_DIR, f"hair_{cid}_{sid}.png")
    studio.render(thumb, 512, 256)
    shots = [("q34", 32, 6), ("back", 150, 12), ("side", 90, 2), ("front", 0, 3)]
    out = []
    for tag, yaw, pitch in shots:
        studio.world_and_lights(hc, 0.6, rim=1.0, yaw=yaw)
        studio.camera(studio.view(aim, yaw, pitch, dist), aim, 70)
        p = os.path.join(PREV_DIR, f"{cid}_{sid}_{tag}.png")
        studio.render(p, 512)
        out.append(p)
    return thumb, out


def export_hair(cid, sid, obj, b, H, rig):
    path = os.path.join(OUT_DIR, f"{cid}_{sid}.fbx")
    me = obj.data
    if b.kind == "rigid":
        M = C.rigid_matrix(cid)
        cn = np.empty(len(me.loops) * 3)
        me.corner_normals.foreach_get("vector", cn)
        cn = cn.reshape(-1, 3)
        R3 = np.array(M.to_3x3())
        for g in list(obj.vertex_groups):
            obj.vertex_groups.remove(g)
        obj.modifiers.clear()
        obj.parent = None
        obj.matrix_world = Matrix.Identity(4)
        me.transform(M)
        me.update()
        me.normals_split_custom_set([tuple(v) for v in nrm_rows(cn @ R3.T)])
        C.export_fbx(path, [obj])
    else:
        hair_weights(obj, H, "skinned")
        obj.parent = rig
        if not any(m.type == "ARMATURE" for m in obj.modifiers):
            mod = obj.modifiers.new("Armature", "ARMATURE"); mod.object = rig
        C.export_fbx(path, [obj], armature=rig)
    return path


def main():
    a = C.args()
    cid = a[0]
    table = KAEL if cid == "kael" else LYRA
    sel = [s for s in a[1].split(",")] if len(a) > 1 and not a[1].startswith("--") else list(table)
    if len(a) < 2 or a[1].startswith("--"):      # the defaults are built by hair_v4.py (v5 pipeline) - never overwrite them here
        from hair_styles import DEFAULTS as HDEF
        sel = [x for x in sel if x != HDEF.get(cid)]
    rig, body = C.load_ref(cid)
    ctx = gear.Ctx(body, rig, C.HEROES[cid]["name"])
    for o in bpy.data.objects:
        if o.type == "MESH" and o.name.startswith("U_") and o.name[2:] in ("Top", "Collar", "Jacket", "ChestRig", "PauldronL", "PauldronR",
                                                                         "PauldronLameL", "PauldronLameR", "ShoulderR", "Harness", "ChestPlate", "ChestUnit"):
            nf = HL.orient_outward(o, ctx)
            ctx.push_stack(o)
    H = HL.Head(ctx, female=cid == "lyra")
    C.log("head", "hc", H.hc.round(4), "top", round(H.top, 4), "brow", round(H.brow_z, 4), "face_hw", round(H.face_hw, 4), "half_w", round(H.half_w, 4))
    studio.hero_materials(cid)
    os.makedirs(TEX_DIR, exist_ok=True)
    for i, sid in enumerate(sel):
        label, recipe = table[sid]
        t0 = time.time()
        b, obj, atlas = build_style(H, ctx, cid, sid, recipe, seed=11 + i * 101 + len(sid))
        tex = os.path.join(TEX_DIR, f"{cid}_{sid}_Hair.png")
        C.write_png(atlas, tex, "RGBA")
        ntri = C.tris(obj)
        C.log(sid, "tris", ntri, "locks", len(b.locks), "build s", round(time.time() - t0, 1))
        if "--no-thumbs" not in a:
            thumb, prevs = preview_and_thumb(cid, sid, obj, tex, b, H)
            bpy.data.libraries.write(os.path.join(C.CACHE, f"hairobj_{cid}_{sid}.blend"), {obj}, fake_user=True, compress=True)
        if "--no-export" not in a:
            obj.data.materials[0] = gear.get_mat("Hair")
            export_hair(cid, sid, obj, b, H, rig)
            entry = {"id": sid, "label": label, "hero": cid, "file": f"Hair/{cid}_{sid}", "kind": b.kind, "bone": "mixamorig:Head",
                     "thumb": f"Thumbs/hair_{cid}_{sid}", "alphaCutoff": b.cutoff, "baseMap": f"Hair/Textures/{cid}_{sid}_Hair",
                     "material": "Hair", "tint": "hair", "tris": ntri, "localPos": [0, 0, 0], "localRot": [0, 0, 0]}
            if b.kind == "skinned":
                entry["bones"] = ["mixamorig:Head", "mixamorig:Neck", "mixamorig:Spine2"]
            os.makedirs(os.path.join(C.CACHE, "catalog", "hair"), exist_ok=True)
            with open(os.path.join(C.CACHE, "catalog", "hair", f"{cid}_{sid}.json"), "w") as f:
                json.dump(entry, f, indent=1)
        bpy.data.objects.remove(obj, do_unlink=True)
    C.log("done")


if __name__ == "__main__":
    main()
