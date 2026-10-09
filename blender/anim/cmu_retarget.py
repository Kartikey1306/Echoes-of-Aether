"""CMU motion capture -> MPFB `mixamo_unity` rig: BVH import, retarget, cleanup, bake, preview and FBX export.

The data used in this project was obtained from mocap.cs.cmu.edu.
The database was created with funding from NSF EIA-0196217.

Run inside a hero .blend that holds the target rig (it is never saved):

  blender -b blender/out/kael_export.blend --python blender/anim/cmu_retarget.py -- male [options]
  blender -b blender/out/lyra_export.blend --python blender/anim/cmu_retarget.py -- female [options]

Options
  --clips a,b,c     only these clips (default: all clips in clips_cmu.py)
  --preview         render preview frames to blender/anim/previews/frames/ (compose with tools/anim/previews.py)
  --frames N        preview frames per clip (default 8)
  --export          write unity/EchoesOfAether/Assets/Art/Animations/Anim_<Style>.fbx
  --meta            merge this style's durations, loop flags and events into clips_meta.json
  --report          print per-clip diagnostics (foot slide, loop seam, ranges)
  --no-posture      skip the posture stage (posture.py), for before/after comparisons

Pipeline per clip (recipes in clips_cmu.py):
  1. ASF/AMC -> BVH (tools/anim/cmu.py), BVH import with Blender's importer, sample world rotations relative to the
     CMU T-pose rest (cached in blender/anim/cmu/cache/).
  2. Source edits: frame range, mirror, facing (+Z forward in Unity = -Y in Blender), root in-place handling.
  3. Time: uniform scale (locomotion speed matching), target duration or a piecewise retiming warp (attacks).
  4. Retarget: hierarchical rest-pose alignment (the A-posed MPFB rig is brought into the CMU T-pose bone by bone),
     then world-space rotation transfer; hips position scaled by leg length.
  5. Cleanup: anti-aliased resampling to 30 fps, smoothing, seamless loops (error distribution), posture stage
     (posture.py: spine / neck / head / wrists re-centred on the upright rest, trunk lean into a natural band with the
     legs kept, neck in line, level head and gaze, straight standing knees), foot contact locking with two-bone leg IK,
     grounding, wrist limits, procedural finger poses.
  6. Bake: one action per clip on the target armature, exported as FBX takes named after the clips, preceded by a
     two-frame "_rest" take holding the rig's rest pose (see REST_TAKE).
"""
import importlib
import json
import math
import os
import sys
import time

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
for p in (HERE, os.path.join(ROOT, "tools", "anim")):
    if p not in sys.path:
        sys.path.insert(0, p)
import cmu  # noqa: E402
import qmath as Q  # noqa: E402
import clips_cmu  # noqa: E402
import posture  # noqa: E402

importlib.reload(Q)
importlib.reload(clips_cmu)
importlib.reload(posture)

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
STYLE = ARGS[0] if ARGS and not ARGS[0].startswith("--") else "male"


def opt(name, default=None):
    if name in ARGS:
        i = ARGS.index(name)
        if i + 1 < len(ARGS) and not ARGS[i + 1].startswith("--"):
            return ARGS[i + 1]
        return True
    return default


FPS = 30
PRE = "mixamorig:"
M3 = np.array(((1, 0, 0), (0, 0, -1), (0, 1, 0)), float)  # CMU / BVH (Y up, +Z forward) -> Blender (Z up, -Y forward)
FWD = np.array([0.0, -1.0, 0.0])
CACHE = os.path.join(cmu.CMU_DIR, "cache")
UNITY_ANIM = os.path.join(ROOT, "unity", "EchoesOfAether", "Assets", "Art", "Animations")
PREVIEW_DIR = os.path.join(HERE, "previews")

# Target bone (without prefix) -> CMU bone driving it.
TMAP = {"Hips": "root", "Spine": "lowerback", "Spine1": "upperback", "Spine2": "thorax", "Neck": "neck*", "Head": "head",
        "LeftShoulder": "lclavicle", "LeftArm": "lhumerus", "LeftForeArm": "lradius", "LeftHand": "lhand",
        "RightShoulder": "rclavicle", "RightArm": "rhumerus", "RightForeArm": "rradius", "RightHand": "rhand",
        "LeftUpLeg": "lfemur", "LeftLeg": "ltibia", "LeftFoot": "lfoot", "LeftToeBase": "ltoes",
        "RightUpLeg": "rfemur", "RightLeg": "rtibia", "RightFoot": "rfoot", "RightToeBase": "rtoes"}

FINGERS = ["Index", "Middle", "Ring", "Pinky", "Thumb"]


def log(*a):
    print("[cmu]", *a, flush=True)


def iter_fcurves(act):
    """All F-curves of an action (Blender 4.4+ layered actions, with a fallback to the legacy API)."""
    try:
        for layer in act.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    for fc in bag.fcurves:
                        yield fc
        return
    except AttributeError:
        pass
    for fc in act.fcurves:
        yield fc


# =============================================================================================== source data

class Source:
    """One CMU trial, imported through its BVH and sampled into world-space rotation deltas (Blender axes)."""

    _cache = {}

    @classmethod
    def get(cls, trial):
        if trial not in cls._cache:
            cls._cache[trial] = Source(trial)
        return cls._cache[trial]

    def __init__(self, trial):
        self.trial = trial
        self.fps = cmu.trial_fps(trial)
        asf, amc = cmu.fetch(trial)
        self.skel = cmu.Skeleton(asf)
        self.bvh = cmu.to_bvh(trial)
        self.nframes = self._bvh_frames()
        self.ob = None
        os.makedirs(CACHE, exist_ok=True)
        self.cpath = os.path.join(CACHE, trial + ".npz")
        self.names = None
        if os.path.exists(self.cpath) and os.path.getmtime(self.cpath) >= os.path.getmtime(self.bvh):
            d = np.load(self.cpath, allow_pickle=True)
            self.names = list(d["names"])
            self.Q, self.P, self.T = d["Q"], d["P"], d["T"]
            self.have = d["have"] if "have" in d else np.ones(len(self.Q), bool)
        if self.names is None or len(self.Q) != self.nframes:
            self.names = self._bvh_joints()
            B = len(self.names)
            self.Q = np.tile(np.array([1.0, 0, 0, 0]), (self.nframes, B, 1))
            self.P = np.zeros((self.nframes, B, 3))
            self.T = np.zeros((self.nframes, B, 3))
            self.have = np.zeros(self.nframes, bool)
        self.idx = {n: i for i, n in enumerate(self.names)}
        s = self.skel.scale()
        # Rest directions / lengths in Blender axes.
        self.dir = {n: M3 @ (b.direction / max(1e-9, np.linalg.norm(b.direction))) for n, b in self.skel.bones.items() if n != "root"}
        self.len = {n: b.length * s for n, b in self.skel.bones.items()}
        ln, un = self.skel.bones["lowerneck"], self.skel.bones["upperneck"]
        nd = M3 @ (ln.direction * ln.length + un.direction * un.length)
        self.dir["neck*"] = nd / np.linalg.norm(nd)
        self.leg = 0.5 * (self.len["lfemur"] + self.len["ltibia"] + self.len["rfemur"] + self.len["rtibia"])
        # Floor of the capture volume: low percentile of the toe / ankle heights over the whole trial (fast numpy FK).
        _, Pn, En = cmu.fk_arrays(self.skel, cmu.read_amc(amc))
        feet = np.concatenate([En["ltoes"][:, 1], En["rtoes"][:, 1], Pn["lfoot"][:, 1] - 0.07, Pn["rfoot"][:, 1] - 0.07])
        self.floor = float(np.percentile(feet, 2))

    def _bvh_joints(self):
        out = []
        with open(self.bvh) as f:
            for line in f:
                p = line.split()
                if p and p[0] in ("ROOT", "JOINT"):
                    out.append(p[1])
                if p and p[0] == "MOTION":
                    break
        return out

    def _bvh_frames(self):
        with open(self.bvh) as f:
            for line in f:
                if line.startswith("Frames:"):
                    return int(line.split()[1])
        return 0

    def _import_range(self, lo, hi):
        """Write a cropped BVH (frames lo..hi), import it with Blender's BVH importer and evaluate its F-curves."""
        t0 = time.time()
        sk, fr = cmu.load(self.trial)
        path = os.path.join(cmu.BVH_DIR, "crop", f"{self.trial}_{lo}_{hi}.bvh")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        cmu.write_bvh(sk, fr, path, self.fps, frame_range=(lo, hi + 1))
        before = set(bpy.data.objects)
        bpy.ops.import_anim.bvh(filepath=path, target="ARMATURE", global_scale=1.0, frame_start=1, use_fps_scale=False,
                                update_scene_fps=False, update_scene_duration=False, use_cyclic=False,
                                rotate_mode="NATIVE", axis_forward="-Z", axis_up="Y")
        ob = [o for o in bpy.data.objects if o not in before and o.type == "ARMATURE"][0]
        names = [b.name for b in ob.data.bones]
        if self.names is not None and names != self.names:
            raise RuntimeError("bone order changed for " + self.trial)
        self.names = names
        n = hi - lo + 1
        act = ob.animation_data.action
        mw = np.array(ob.matrix_world)
        bones = list(ob.data.bones)
        B = len(bones)
        rest = np.array([np.array(b.matrix_local) for b in bones])
        par = [names.index(b.parent.name) if b.parent else -1 for b in bones]
        # read the baked channels (the importer keys every frame)
        from mathutils import Euler
        rot = np.zeros((n, B, 3, 3))
        loc = np.zeros((n, B, 3))
        curves = {}
        for fc in iter_fcurves(act):
            curves[(fc.data_path, fc.array_index)] = fc
        for i, pb in enumerate(ob.pose.bones):
            base = f'pose.bones["{pb.name}"]'
            mode = pb.rotation_mode
            if mode in ("QUATERNION", "AXIS_ANGLE"):
                raise RuntimeError("unexpected rotation mode " + mode)
            e = np.zeros((n, 3))
            for c in range(3):
                fc = curves.get((base + ".rotation_euler", c))
                if fc is not None:
                    e[:, c] = [fc.evaluate(lo * 0 + f + 1) for f in range(n)]
                fl = curves.get((base + ".location", c))
                if fl is not None:
                    loc[:, i, c] = [fl.evaluate(f + 1) for f in range(n)]
            for f in range(n):
                rot[f, i] = np.array(Euler(e[f], mode).to_matrix())
        # pose matrices (armature space): M_b = M_p @ (R_p^-1 R_b) @ basis
        M = np.zeros((n, B, 4, 4))
        for i in range(B):
            basis = np.tile(np.eye(4), (n, 1, 1))
            basis[:, :3, :3] = rot[:, i]
            basis[:, :3, 3] = loc[:, i]
            if par[i] < 0:
                M[:, i] = rest[i] @ basis
            else:
                M[:, i] = M[:, par[i]] @ (np.linalg.inv(rest[par[i]]) @ rest[i]) @ basis
        W = mw @ M
        rest_w_inv = np.linalg.inv(mw[:3, :3] @ rest[:, :3, :3])
        deltas = W[:, :, :3, :3] @ rest_w_inv[None]
        lengths = np.array([b.length for b in bones])
        frames = np.arange(lo, hi + 1)
        self.Q[frames] = Q.qhemi(Q.qfrommat(deltas))
        self.P[frames] = W[:, :, :3, 3]
        self.T[frames] = W[:, :, :3, 3] + W[:, :, :3, 1] * lengths[None, :, None]
        self.have[frames] = True
        bpy.data.objects.remove(ob, do_unlink=True)
        if act.users == 0:
            bpy.data.actions.remove(act)
        for a in list(bpy.data.armatures):
            if a.users == 0:
                bpy.data.armatures.remove(a)
        log(f"BVH import {os.path.basename(path)}: {n} frames, {B} joints ({time.time() - t0:.1f}s)")

    def ensure(self, a, b):
        """Make sure source frames a..b (inclusive, 0-based) are sampled (cropped BVH import, cached)."""
        a, b = max(0, int(a)), min(self.nframes - 1, int(b))
        need = [f for f in range(a, b + 1) if not self.have[f]]
        if not need:
            return
        if self.names is None:
            self.names = None
        lo, hi = min(need), max(need)
        first = self.Q is None
        self._import_range(lo, hi)
        np.savez_compressed(self.cpath, names=np.array(self.names), Q=self.Q, P=self.P, T=self.T, have=self.have)

    @classmethod
    def cleanup(cls):
        pass

    def joint(self, name, frames=None, end=False):
        a = self.T if end else self.P
        return a[:, self.idx[name]] if frames is None else a[frames, self.idx[name]]


MIRROR_NAME = {}
for _n in ["hipjoint", "femur", "tibia", "foot", "toes", "clavicle", "humerus", "radius", "wrist", "hand", "fingers", "thumb"]:
    MIRROR_NAME["l" + _n] = "r" + _n
    MIRROR_NAME["r" + _n] = "l" + _n


class Seg:
    """Edited source motion in source frames: world rotation deltas Qw[F,B,4] and joint positions P/T[F,B,3]."""

    def __init__(self, src: Source, a, b, mirror=False, margin=12):
        self.src = src
        self.fps = src.fps
        F = len(src.Q)
        self.a, self.b = a, b
        self.lo = max(0, a - margin)
        self.hi = min(F - 1, b + margin)
        src.ensure(self.lo, self.hi)
        sl = slice(self.lo, self.hi + 1)
        self.names = src.names
        self.idx = src.idx
        self.Qw = Q.qhemi(src.Q[sl].copy())
        self.P = src.P[sl].copy()
        self.T = src.T[sl].copy()
        self.P[..., 2] -= src.floor
        self.T[..., 2] -= src.floor
        self.dir = dict(src.dir)
        if mirror:
            perm = [self.idx.get(MIRROR_NAME.get(n, n), i) for i, n in enumerate(self.names)]
            self.Qw = self.Qw[:, perm] * np.array([1.0, 1.0, -1.0, -1.0])
            self.P = self.P[:, perm] * np.array([-1.0, 1.0, 1.0])
            self.T = self.T[:, perm] * np.array([-1.0, 1.0, 1.0])
            # Rest directions are (near) symmetric; use the mirrored partner's direction.
            self.dir = {n: (src.dir[MIRROR_NAME.get(n, n)] * np.array([-1.0, 1, 1])) if n in MIRROR_NAME else d for n, d in src.dir.items()}

    def i(self, f):
        """Source frame -> local index."""
        return f - self.lo

    def jp(self, name, end=False):
        return (self.T if end else self.P)[:, self.idx[name]]

    def facing_corr(self, f=None):
        """Per frame: yaw (radians about +Z) that turns the body's forward (pelvis + thorax) to -Y."""
        fwd = Q.qrot(self.Qw[:, self.idx["root"]], FWD) + Q.qrot(self.Qw[:, self.idx["thorax"]], FWD)
        corr = np.arctan2(-fwd[:, 0], -fwd[:, 1])
        if f is None:
            return corr
        return corr[self.i(f)]

    def rotate(self, ang, pivot):
        """Rotate everything about the vertical axis through pivot (xy) by ang radians."""
        q = Q.yaw_quat(ang)
        self.Qw = Q.qmul(np.broadcast_to(q, self.Qw.shape), self.Qw)
        for arr in (self.P, self.T):
            v = arr.copy()
            v[..., :2] -= pivot[:2]
            v = Q.qrot(q, v)
            v[..., :2] += pivot[:2]
            arr[...] = v

    def translate(self, d):
        """d: [F,3] or [3] offsets (applied to all joints)."""
        d = np.asarray(d, float)
        if d.ndim == 1:
            d = np.broadcast_to(d, (len(self.P), 3))
        self.P += d[:, None, :]
        self.T += d[:, None, :]


def yaw_of(v):
    """Rotation angle about +Z that takes the horizontal direction v to -Y (forward)."""
    return math.atan2(-v[0], -v[1])


# =============================================================================================== target rig

class Target:
    def __init__(self, rig):
        self.rig = rig
        bones = rig.data.bones
        self.names = [b.name for b in bones]
        self.idx = {n: i for i, n in enumerate(self.names)}
        self.short = [n[len(PRE):] if n.startswith(PRE) else n for n in self.names]
        self.sidx = {s: i for i, s in enumerate(self.short)}
        self.parent = np.array([self.idx[b.parent.name] if b.parent else -1 for b in bones])
        self.R = Q.qfrommat(np.array([np.array(b.matrix_local)[:3, :3] for b in bones]))
        self.head = np.array([np.array(b.head_local) for b in bones])
        self.tail = np.array([np.array(b.tail_local) for b in bones])
        self.deform = [b.use_deform for b in bones]
        n = len(bones)
        self.dir = (self.tail - self.head) / np.linalg.norm(self.tail - self.head, axis=1, keepdims=True)
        self.leg = 0.5 * sum(np.linalg.norm(self.tail[self.sidx[s]] - self.head[self.sidx[s]]) for s in ("LeftUpLeg", "LeftLeg", "RightUpLeg", "RightLeg"))
        self.mid_hip = 0.5 * (self.head[self.sidx["LeftUpLeg"]] + self.head[self.sidx["RightUpLeg"]])
        self.hips = self.sidx["Hips"]
        self.height = float(self.tail[self.sidx["Head"], 2])
        # Sole reference points per foot, relative to the ankle (foot bone head) / toe bone head at rest.
        self.feet = {}
        for side in ("Left", "Right"):
            fo, to = self.sidx[side + "Foot"], self.sidx[side + "ToeBase"]
            ank, ball, tip = self.head[fo], self.head[to], self.tail[to]
            self.feet[side] = dict(foot=fo, toe=to, thigh=self.sidx[side + "UpLeg"], shin=self.sidx[side + "Leg"],
                                   heel=np.array([ank[0], ank[1] + 0.045, 0.0]) - ank,
                                   ball=np.array([ball[0], ball[1], 0.0]) - ank,
                                   tip=np.array([tip[0], tip[1], 0.0]) - ball,
                                   ank_h=float(ank[2]))
        self.A = None

    def align(self, src_dir):
        """Hierarchical rest alignment: A[b] rotates the target rest pose into the source T-pose."""
        n = len(self.names)
        A = np.tile(np.array([1.0, 0, 0, 0]), (n, 1))
        for i in range(n):
            p = self.parent[i]
            Ap = A[p] if p >= 0 else np.array([1.0, 0, 0, 0])
            s = self.short[i]
            if s == "Hips" or s == "Root":
                A[i] = np.array([1.0, 0, 0, 0])
            elif s in TMAP:
                d = Q.qrot(Ap, self.dir[i])
                A[i] = Q.qmul(Q.qfromto(d, src_dir[TMAP[s]]), Ap)
            else:
                A[i] = Ap
        self.A = A

    # ---------------------------------------------------------------- kinematics on [N, B, 4] local quats

    def fk(self, L, H):
        """Local basis quats L[N,B,4] + hips head positions H[N,3] -> world deltas D[N,B,4], heads P[N,B,3]."""
        N, B = L.shape[:2]
        D = np.zeros((N, B, 4))
        P = np.zeros((N, B, 3))
        for i in range(B):
            p = self.parent[i]
            loc = Q.qmul(Q.qmul(self.R[i], L[:, i]), Q.qconj(self.R[i]))
            if p < 0:
                D[:, i] = loc
                P[:, i] = self.head[i]
            else:
                D[:, i] = Q.qmul(D[:, p], loc)
                P[:, i] = P[:, p] + Q.qrot(D[:, p], self.head[i] - self.head[p])
            if i == self.hips:
                P[:, i] = H
        return D, P

    def local(self, D):
        N, B = D.shape[:2]
        L = np.zeros_like(D)
        for i in range(B):
            p = self.parent[i]
            dp = D[:, p] if p >= 0 else np.tile([1.0, 0, 0, 0], (N, 1))
            L[:, i] = Q.qmul(Q.qmul(Q.qconj(self.R[i]), Q.qmul(Q.qconj(dp), D[:, i])), self.R[i])
        return Q.qhemi(L)

    def sole_points(self, D, P, side):
        f = self.feet[side]
        ank = P[:, f["foot"]]
        heel = ank + Q.qrot(D[:, f["foot"]], f["heel"])
        ball = ank + Q.qrot(D[:, f["foot"]], f["ball"])
        tip = P[:, f["toe"]] + Q.qrot(D[:, f["toe"]], f["tip"])
        return heel, ball, tip


# =============================================================================================== time warps

def pchip(xk, yk, x):
    """Monotone cubic (Fritsch-Carlson) interpolation."""
    xk, yk = np.asarray(xk, float), np.asarray(yk, float)
    x = np.asarray(x, float)
    if len(xk) == 2:
        return np.interp(x, xk, yk)
    h = np.diff(xk)
    dl = np.diff(yk) / h
    m = np.zeros_like(yk)
    for k in range(1, len(xk) - 1):
        if dl[k - 1] * dl[k] <= 0:
            m[k] = 0
        else:
            w1, w2 = 2 * h[k] + h[k - 1], h[k] + 2 * h[k - 1]
            m[k] = (w1 + w2) / (w1 / dl[k - 1] + w2 / dl[k])
    m[0], m[-1] = dl[0], dl[-1]
    j = np.clip(np.searchsorted(xk, x) - 1, 0, len(xk) - 2)
    t = (x - xk[j]) / h[j]
    t2, t3 = t * t, t * t * t
    return ((2 * t3 - 3 * t2 + 1) * yk[j] + (t3 - 2 * t2 + t) * h[j] * m[j]
            + (-2 * t3 + 3 * t2) * yk[j + 1] + (t3 - t2) * h[j] * m[j + 1])


class Warp:
    """Output time (s) <-> source frame mapping."""

    def __init__(self, keys):  # keys: [(src_frame, out_time)], increasing
        keys = sorted(keys, key=lambda k: k[1])
        self.t = np.array([k[1] for k in keys], float)
        self.f = np.array([k[0] for k in keys], float)

    def src(self, t):
        return pchip(self.t, self.f, t)

    def out(self, f):
        tt = np.linspace(self.t[0], self.t[-1], 4000)
        ff = self.src(tt)
        return float(np.interp(f, ff, tt))

    @property
    def duration(self):
        return float(self.t[-1] - self.t[0])


# =============================================================================================== clip building

def sample_seg(seg: Seg, sframes):
    """Anti-aliased sampling of a Seg at fractional source frames -> (Qw[N,B,4], P[N,B,3], T[N,B,3])."""
    sframes = np.asarray(sframes, float)
    step = np.abs(np.diff(sframes)).mean() if len(sframes) > 1 else 1.0
    sigma = max(0.0, 0.42 * step - 0.2)
    Qs = Q.qsmooth(seg.Qw, sigma)
    Ps = Q.smooth(seg.P, sigma)
    Ts = Q.smooth(seg.T, sigma)
    x = np.clip(sframes - seg.lo, 0, len(Qs) - 1.000001)
    i0 = np.floor(x).astype(int)
    i1 = np.minimum(i0 + 1, len(Qs) - 1)
    w = (x - i0)[:, None]
    Qo = Q.qslerp(Qs[i0], Qs[i1], np.broadcast_to(w, (len(x), Qs.shape[1])))
    Po = Ps[i0] * (1 - w[..., None]) + Ps[i1] * w[..., None]
    To = Ts[i0] * (1 - w[..., None]) + Ts[i1] * w[..., None]
    return Qo, Po, To


def retarget(tg: Target, seg: Seg, Qw, P, scale):
    """Source world deltas -> target local basis quats + hips head positions."""
    N = len(Qw)
    B = len(tg.names)
    D = np.zeros((N, B, 4))
    D[:] = np.array([1.0, 0, 0, 0])
    si = seg.idx
    for i in range(B):
        s = tg.short[i]
        p = tg.parent[i]
        if s in TMAP:
            sn = TMAP[s]
            if sn == "neck*":
                qs = Q.qslerp(Qw[:, si["lowerneck"]], Qw[:, si["upperneck"]], 0.5)
            else:
                qs = Qw[:, si[sn]]
            D[:, i] = Q.qmul(qs, np.broadcast_to(tg.A[i], (N, 4)))
        elif p >= 0:
            # follow the parent rigidly (fingers, face, breasts...)
            D[:, i] = Q.qmul(D[:, p], np.broadcast_to(Q.qmul(Q.qconj(tg.A[p]), tg.A[i]), (N, 4)))
    # Hips: place the target's mid-hip point on the scaled source mid-hip point.
    mid = 0.5 * (P[:, si["lfemur"]] + P[:, si["rfemur"]]) * scale
    H = mid - Q.qrot(D[:, tg.hips], tg.mid_hip - tg.head[tg.hips])
    L = tg.local(D)
    return L, H


# ----------------------------------------------------------------------------------------------- fingers

FINGER_POSES = {
    # per finger: (curl1, curl2, curl3, spread) degrees; thumb: (opp, curl1, curl2, curl3)
    # relaxed / loose: a hand hanging at rest curls more towards the little finger (the earlier, nearly straight poses
    # read as stiff "mannequin" hands and were re-curled at Unity import)
    "relaxed": {"Index": (16, 40, 22, 2), "Middle": (22, 46, 25, 0), "Ring": (28, 50, 27, -2), "Pinky": (34, 52, 27, -5), "Thumb": (14, 10, 16, 12)},
    "loose":   {"Index": (10, 28, 16, 3), "Middle": (14, 34, 18, 0), "Ring": (18, 38, 20, -3), "Pinky": (24, 40, 20, -6), "Thumb": (8, 6, 12, 8)},
    "fist":    {"Index": (78, 98, 55, 0), "Middle": (82, 100, 55, 0), "Ring": (86, 100, 55, -1), "Pinky": (90, 98, 55, -3), "Thumb": (38, 30, 35, 40)},
    "grip":    {"Index": (50, 60, 35, 0), "Middle": (55, 65, 35, 0), "Ring": (60, 65, 35, -2), "Pinky": (65, 65, 35, -4), "Thumb": (30, 20, 25, 25)},
    "open":    {"Index": (2, 4, 2, 6), "Middle": (2, 4, 2, 0), "Ring": (3, 5, 3, -6), "Pinky": (4, 6, 3, -12), "Thumb": (0, 0, 2, -5)},
    "spread":  {"Index": (6, 10, 6, 12), "Middle": (8, 10, 6, 2), "Ring": (10, 12, 6, -10), "Pinky": (12, 12, 6, -20), "Thumb": (-5, 0, 5, -10)},
    "claw":    {"Index": (30, 45, 30, 10), "Middle": (32, 48, 32, 2), "Ring": (34, 48, 32, -8), "Pinky": (36, 48, 32, -16), "Thumb": (10, 15, 20, 5)},
    "point":   {"Index": (4, 6, 4, 4), "Middle": (75, 95, 50, 0), "Ring": (82, 95, 50, -2), "Pinky": (86, 95, 50, -4), "Thumb": (35, 25, 30, 30)},
    "flat":    {"Index": (0, 2, 2, 2), "Middle": (0, 2, 2, 0), "Ring": (0, 2, 2, -2), "Pinky": (0, 2, 2, -4), "Thumb": (-5, 0, 0, -4)},
}


def finger_quats(tg: Target, pose_l, pose_r, w=None):
    """-> {bone_index: quat[4]} local basis rotations for one frame (dicts of FINGER_POSES)."""
    out = {}
    for side, pose in (("Left", pose_l), ("Right", pose_r)):
        for fname in FINGERS:
            vals = pose[fname]
            for j in (1, 2, 3):
                bn = f"{side}Hand{fname}{j}"
                if bn not in tg.sidx:
                    continue
                if fname == "Thumb":
                    opp, c1, c2, c3 = vals
                    if j == 1:
                        q = Q.qmul(Q.qaxis([0, 0, 1], math.radians(-opp if side == "Left" else opp)), Q.qaxis([1, 0, 0], math.radians(c1)))
                    else:
                        q = Q.qaxis([1, 0, 0], math.radians(c2 if j == 2 else c3))
                else:
                    c = vals[j - 1]
                    q = Q.qaxis([1, 0, 0], math.radians(c))
                    if j == 1 and vals[3]:
                        sp = vals[3] if side == "Left" else -vals[3]
                        q = Q.qmul(Q.qaxis([0, 0, 1], math.radians(sp)), q)
                out[tg.sidx[bn]] = q
    return out


def blend_pose(a, b, w):
    return {k: tuple(a[k][i] * (1 - w) + b[k][i] * w for i in range(4)) for k in a}


def finger_track(spec, N, dur):
    """spec: name | (left, right) | [(t, name_or_pair), ...] -> per-frame (left_pose, right_pose)."""
    def pair(x):
        if isinstance(x, (tuple, list)) and len(x) == 2 and all(isinstance(s, str) for s in x):
            return FINGER_POSES[x[0]], FINGER_POSES[x[1]]
        return FINGER_POSES[x], FINGER_POSES[x]
    if isinstance(spec, list):
        keys = [(t, pair(p)) for t, p in spec]
    else:
        keys = [(0.0, pair(spec))]
    out = []
    for k in range(N):
        t = k / FPS
        if t <= keys[0][0] or len(keys) == 1:
            out.append(keys[0][1])
            continue
        for (t0, p0), (t1, p1) in zip(keys, keys[1:]):
            if t0 <= t <= t1:
                w = (t - t0) / max(1e-6, t1 - t0)
                w = w * w * (3 - 2 * w)
                out.append((blend_pose(p0[0], p1[0], w), blend_pose(p0[1], p1[1], w)))
                break
        else:
            out.append(keys[-1][1])
    return out


# ----------------------------------------------------------------------------------------------- leg IK

def two_bone_ik(hip, knee, ankle, target, pole_dir=None):
    """Return new knee position for reaching target from hip, keeping the knee's bend plane (or bending towards
    pole_dir[N,3] when given)."""
    l1 = np.linalg.norm(knee - hip, axis=-1)
    l2 = np.linalg.norm(ankle - knee, axis=-1)
    d_vec = target - hip
    d = np.linalg.norm(d_vec, axis=-1)
    d = np.clip(d, np.abs(l1 - l2) + 1e-4, (l1 + l2) * 0.9995)
    w = d_vec / np.maximum(1e-9, np.linalg.norm(d_vec, axis=-1, keepdims=True))
    pole = knee - hip if pole_dir is None else pole_dir
    pole = pole - np.sum(pole * w, -1, keepdims=True) * w
    pn = np.linalg.norm(pole, axis=-1, keepdims=True)
    pole = np.where(pn > 1e-6, pole / np.maximum(pn, 1e-9), np.array([0, -1.0, 0]))
    cos_a = np.clip((l1 ** 2 + d ** 2 - l2 ** 2) / (2 * l1 * d), -1, 1)
    sin_a = np.sqrt(1 - cos_a ** 2)
    knee_new = hip + l1[..., None] * (cos_a[..., None] * w + sin_a[..., None] * pole)
    target_new = hip + w * d[..., None]
    return knee_new, target_new


def apply_leg_ik(tg: Target, L, H, side, ankle_target, weight, pole_hint=None):
    """Move the ankle towards ankle_target[N,3] with weight[N] (0..1), keeping the foot's world orientation.
    pole_hint[N,3] (optional): direction the knee should point (e.g. forward) when the leg starts almost straight."""
    D, P = tg.fk(L, H)
    f = tg.feet[side]
    th, sh, fo = f["thigh"], f["shin"], f["foot"]
    hip, knee, ank = P[:, th], P[:, sh], P[:, fo]
    tgt = ank + (ankle_target - ank) * weight[:, None]
    knee_n, ank_n = two_bone_ik(hip, knee, ank, tgt, pole_hint)
    r1 = Q.qfromto(knee - hip, knee_n - hip)
    Dth = Q.qmul(r1, D[:, th])
    shin_dir = Q.qrot(r1, ank - knee)
    r2 = Q.qfromto(shin_dir, ank_n - knee_n)
    Dsh = Q.qmul(r2, Q.qmul(r1, D[:, sh]))
    D2 = D.copy()
    D2[:, th] = Dth
    D2[:, sh] = Dsh
    # keep the foot (and toes) world orientation
    Lnew = L.copy()
    for i in (th, sh, fo):
        p = tg.parent[i]
        Lnew[:, i] = Q.qmul(Q.qmul(Q.qconj(tg.R[i]), Q.qmul(Q.qconj(D2[:, p]), D2[:, i])), tg.R[i])
    return Q.qhemi(Lnew)


def crouch(tg: Target, L, H, drop):
    """Procedural crouch: lower the hips by `drop` (m) while leg IK keeps both ankles on their original paths, so the
    knees bend and the feet keep their stride and contacts (the foot lock afterwards re-plants them as usual)."""
    _, P = tg.fk(L, H)
    H2 = H - np.array([0.0, 0.0, drop])
    for side in ("Left", "Right"):
        f = tg.feet[side]
        ank = P[:, f["foot"]].copy()
        # knees track over the toes: bend plane from the foot's pointing direction (no knock-knees)
        toe = P[:, f["toe"]] - ank
        toe[:, 2] = 0
        toe /= np.maximum(1e-6, np.linalg.norm(toe, axis=1, keepdims=True))
        L = apply_leg_ik(tg, L, H2, side, ank, np.ones(len(L)), pole_hint=toe)
    return L, H2


def contacts(heights, speeds, h_thr, v_thr, min_len=3, gap=2, cyclic=False):
    c = (heights < h_thr) & (speeds < v_thr)
    n = len(c)
    # fill small gaps
    def runs(mask):
        out, s = [], None
        for i, m in enumerate(mask):
            if m and s is None:
                s = i
            if not m and s is not None:
                out.append((s, i))
                s = None
        if s is not None:
            out.append((s, len(mask)))
        return out
    for s, e in runs(~c):
        if e - s <= gap and s > 0 and e < n:
            c[s:e] = True
    for s, e in runs(c):
        if e - s < min_len:
            c[s:e] = False
    return c, runs(c)


def foot_lock(tg: Target, L, H, travel_v, cyclic, opts):
    """Rolling-contact foot planting in the frame that moves with the character controller.
    While a foot is planted, whichever sole point is currently lowest (heel, ball or toe tip) is the pivot: it is
    pinned where it first touched down and put exactly on the floor. The ankle is moved by the resulting offset
    (smoothed, ramped in and out) and the leg is re-solved with two-bone IK; the foot keeps its orientation."""
    N = len(L)
    h_thr = opts.get("h", 0.05)
    v_thr = opts.get("v", 0.6 + 0.25 * travel_v)
    ramp = opts.get("ramp", 3)
    t = np.arange(N) / FPS
    shift = (travel_v * t)[:, None] * FWD[None, :]  # in-place -> controller frame
    span = travel_v * N / FPS * FWD
    for side in ("Left", "Right"):
        D, P = tg.fk(L, H)
        pts = [p + shift for p in tg.sole_points(D, P, side)]
        ank = P[:, tg.feet[side]["foot"]]
        if cyclic:
            pts3 = [np.concatenate([p - span, p, p + span]) for p in pts]
        else:
            pts3 = pts
        M = len(pts3[0])
        z = np.stack([p[:, 2] for p in pts3], 1)
        k = np.argmin(z, axis=1)
        zmin = z[np.arange(M), k]
        low = np.stack([pts3[j][i] for i, j in enumerate(k)])
        vel = np.zeros(M)
        for i in range(M):
            a_, b_ = max(0, i - 1), min(M - 1, i + 1)
            vel[i] = np.linalg.norm(pts3[k[i]][b_, :2] - pts3[k[i]][a_, :2]) * FPS / max(1, b_ - a_)
        floor = np.percentile(zmin, 5)
        c, rs = contacts(zmin - floor, vel, h_thr, v_thr)
        delta3 = np.zeros((M, 3))
        w3 = np.zeros(M)
        for s0, e0 in rs:
            anchors = {}
            for i in range(s0, e0):
                kk = int(k[i])
                if kk not in anchors:
                    anc = pts3[kk][i].copy()
                    anc[2] = 0.0
                    anchors[kk] = anc
                delta3[i] = anchors[kk] - pts3[kk][i]
                w3[i] = 1.0
            for r in range(1, ramp + 1):
                wv = 1.0 - r / (ramp + 1)
                for j, src in ((s0 - r, s0), (e0 - 1 + r, e0 - 1)):
                    if 0 <= j < M and w3[j] < wv:
                        w3[j] = wv
                        delta3[j] = delta3[src]
        delta3 = Q.smooth(delta3, 1.0)
        if cyclic:
            delta, w = delta3[N:2 * N], w3[N:2 * N]
        else:
            delta, w = delta3, w3
        L = apply_leg_ik(tg, L, H, side, ank + delta, w)
    return L


def leg_stats(tg: Target, L, H, travel_v, cyclic=False):
    """Foot slide of planted feet in the frame moving with the character controller.
    A foot is planted while its lowest sole point is within 2.5 cm of the floor. Returns per foot
    (fraction of frames planted, median slide m/s, 90th percentile slide m/s)."""
    D, P = tg.fk(L, H)
    N = len(L)
    shift = (travel_v * np.arange(N) / FPS)[:, None] * FWD[None, :]
    out = []
    for side in ("Left", "Right"):
        pts = [p + shift for p in tg.sole_points(D, P, side)]
        z = np.stack([p[:, 2] for p in pts], 1)
        k = np.argmin(z, axis=1)
        low = np.stack([pts[j][i] for i, j in enumerate(k)])
        zmin = z.min(axis=1)
        planted = zmin < 0.025
        v = np.full(N, np.nan)
        for i in range(N):
            j = (i + 1) % N if cyclic else min(i + 1, N - 1)
            if j == i:
                continue
            nxt = pts[k[i]][j] + (np.array([0, -travel_v * N / FPS, 0]) if (cyclic and j < i) else 0)
            v[i] = np.linalg.norm((nxt - low[i])[:2]) * FPS
        sel = planted & ~np.isnan(v)
        out.append((float(planted.mean()), float(np.median(v[sel])) if sel.any() else 0.0, float(np.percentile(v[sel], 90)) if sel.any() else 0.0))
    return out


# ----------------------------------------------------------------------------------------------- the clip

GROUND_POINTS = None


def ground_offset(tg: Target, L, H, mode):
    D, P = tg.fk(L, H)
    pts = []
    for side in ("Left", "Right"):
        heel, ball, tip = tg.sole_points(D, P, side)
        pts += [heel[:, 2], ball[:, 2], tip[:, 2]]
    if mode == "feet":
        z = np.min(np.stack(pts, 1), axis=1)
        return -float(np.percentile(z, 3))
    # whole body (lying, kneeling, sitting on the floor): joints with a rough flesh radius
    radius = {"Hips": 0.11, "Spine": 0.11, "Spine1": 0.11, "Spine2": 0.12, "Neck": 0.07, "Head": 0.1,
              "LeftArm": 0.06, "RightArm": 0.06, "LeftForeArm": 0.05, "RightForeArm": 0.05, "LeftHand": 0.03, "RightHand": 0.03,
              "LeftLeg": 0.06, "RightLeg": 0.06, "LeftShoulder": 0.08, "RightShoulder": 0.08}
    for s, r in radius.items():
        pts.append(P[:, tg.sidx[s], 2] - r)
    pts.append(P[:, tg.sidx["Head"], 2] + Q.qrot(D[:, tg.sidx["Head"]], np.array([0, 0, 0.12]))[:, 2] - 0.1)
    z = np.min(np.stack(pts, 1), axis=1)
    return -float(np.percentile(z, 3))


def wrist_limit(tg: Target, L, limit_deg):
    for s in ("LeftHand", "RightHand"):
        i = tg.sidx[s]
        q = Q.qhemi(L[:, i], np.array([1.0, 0, 0, 0]))
        ang = Q.qangle(q)
        lim = math.radians(limit_deg)
        over = ang > lim
        if over.any():
            k = np.where(over, lim / np.maximum(ang, 1e-6), 1.0)
            L[:, i] = Q.qpow(q, k)
    return L


LOOP_JOINTS = ["root", "lowerback", "thorax", "head", "lhumerus", "lradius", "lhand", "rhumerus", "rradius", "rhand",
               "lfemur", "ltibia", "lfoot", "ltoes", "rfemur", "rtibia", "rfoot", "rtoes"]


def find_loop(seg: Seg, a, b, min_s, max_s):
    """Best loop window inside [a, b]: start/end poses (root-relative joints, heading-free) and velocities match."""
    fps = seg.fps
    idx = [seg.idx[j] for j in LOOP_JOINTS]
    P = seg.P[:, idx] - seg.P[:, [seg.idx["root"]]] * np.array([1, 1, 0])
    P = Q.smooth(P, 1.5)
    V = np.zeros_like(P)
    V[1:-1] = (P[2:] - P[:-2]) * fps / 2
    lo, hi = seg.i(a), seg.i(b)
    mn, mx = int(min_s * fps), int(max_s * fps)
    best = (1e9, a, b)
    step = max(1, int(fps / 30))
    for i in range(lo, max(lo + 1, hi - mn), step):
        js = np.arange(i + mn, min(hi, i + mx) + 1, step)
        if len(js) == 0:
            continue
        dp = np.sum((P[js] - P[i]) ** 2, axis=(1, 2))
        dv = np.sum((V[js] - V[i]) ** 2, axis=(1, 2)) * 0.01
        k = int(np.argmin(dp + dv))
        cost = float(dp[k] + dv[k])
        if cost < best[0]:
            best = (cost, i + seg.lo, int(js[k]) + seg.lo)
    log(f"loop search {seg.src.trial} {a}-{b}: best {best[1]}-{best[2]} ({(best[2] - best[1]) / fps:.2f}s) cost {best[0]:.4f}")
    return best[1], best[2]


def unturn(tg: Target, L, H, t_from):
    """Rotate the whole body about the vertical axis so the last frame faces like the first (spinning kicks, hooks).
    The correction ramps in (smoothstep) from t_from to the end so the strike itself is untouched."""
    h = tg.hips
    Dh = Q.qmul(Q.qmul(tg.R[h], L[:, h]), Q.qconj(tg.R[h]))
    fwd = Q.qrot(Dh, FWD)
    yaw = np.unwrap(np.arctan2(fwd[:, 0], -fwd[:, 1]))
    total = yaw[-1] - yaw[0]
    N = len(L)
    t = np.arange(N) / FPS
    w = np.clip((t - t_from) / max(1e-6, t[-1] - t_from), 0, 1)
    w = w * w * (3 - 2 * w)
    q = Q.qaxis([0, 0, 1], -total * w)  # +angle about +Z increases this yaw measure, so rotate back by -total
    Dh2 = Q.qmul(q, Dh)
    L = L.copy()
    L[:, h] = Q.qmul(Q.qmul(Q.qconj(tg.R[h]), Dh2), tg.R[h])
    H = Q.qrot(q, H)
    log(f"unturn: removed {np.degrees(total):.0f} deg after {t_from:.2f}s")
    return Q.qhemi(L), H


def build_clip(tg: Target, name, rc):
    """Build one clip from its recipe -> dict(L, H, events, loop, speed, notes)."""
    segs_out = []
    loop = bool(rc.get("loop", False))
    travel_v = float(rc.get("speed", 0.0))
    srcs = rc["src"]
    if isinstance(srcs, tuple):
        srcs = [srcs]
    events = []
    t_offset = 0.0
    for si, sspec in enumerate(srcs):
        trial, a, b = sspec[:3]
        sopt = sspec[3] if len(sspec) > 3 else {}
        S = Source.get(trial)
        seg = Seg(S, a, b, mirror=sopt.get("mirror", rc.get("mirror", False)))
        if tg.A is None:
            tg.align(seg.dir)
        if loop and sopt.get("loop_search", rc.get("loop_search")):
            a, b = find_loop(seg, a, b, *sopt.get("loop_search", rc.get("loop_search")))
            seg.a, seg.b = a, b
        scale = tg.leg / S.leg
        # --------------------------------------------------- facing
        face = sopt.get("face", rc.get("face", "mean"))
        ia, ib = seg.i(a), seg.i(b)
        root = seg.jp("root")
        if face == "travel":
            d = root[ib] - root[ia]
            ang = yaw_of(d)
        elif face == "mean":
            c = seg.facing_corr()[ia:ib + 1]
            ang = math.atan2(np.mean(np.sin(c)), np.mean(np.cos(c)))
        elif isinstance(face, tuple) and face[0] == "frame":
            ang = seg.facing_corr(face[1])
        elif isinstance(face, tuple) and face[0] == "effector":
            # direction from the root (or thorax) to an end effector at a frame
            _, jn, fr = face[:3]
            k = seg.i(fr)
            e = seg.jp(jn, end=True)[k] - seg.jp("root")[k]
            ang = yaw_of(e)
        else:
            ang = 0.0
        ang += math.radians(sopt.get("yaw", rc.get("yaw", 0.0)))
        seg.rotate(ang, root[ia].copy())
        if rc.get("track_yaw"):
            # remove slow turning (keeps sway): smoothed facing correction per frame
            c = np.unwrap(seg.facing_corr())
            sm = Q.smooth(c[:, None], rc["track_yaw"] * seg.fps)[:, 0]
            for k in range(len(sm)):
                q = Q.yaw_quat(sm[k])
                seg.Qw[k] = Q.qmul(np.broadcast_to(q, seg.Qw[k].shape), seg.Qw[k])
                pv = seg.P[k, seg.idx["root"]].copy()
                for arr in (seg.P, seg.T):
                    v = arr[k] - pv
                    arr[k] = Q.qrot(q, v) + pv
        # --------------------------------------------------- root XY handling (source frames)
        root = seg.jp("root").copy()
        rmode = sopt.get("root", rc.get("root", "pin"))
        Fn = len(root)
        fidx = np.arange(Fn)
        if rmode == "loop":
            v = (root[ib, :2] - root[ia, :2]) / max(1, ib - ia)
            off = np.zeros((Fn, 3))
            off[:, :2] = -(root[ia, :2] + np.outer(fidx - ia, v))
            seg.translate(off)
        elif rmode == "start":
            off = np.zeros(3)
            off[:2] = -root[ia, :2]
            seg.translate(off)
        elif rmode == "pin":
            off = np.zeros((Fn, 3))
            off[:, :2] = -root[:, :2]
            seg.translate(off)
        elif rmode == "damp":
            sm = Q.smooth(root[:, :2], sopt.get("damp", rc.get("damp", 0.35)) * seg.fps)
            off = np.zeros((Fn, 3))
            off[:, :2] = -sm
            seg.translate(off)
        elif rmode == "center":
            off = np.zeros(3)
            off[:2] = -np.mean(root[ia:ib + 1, :2], axis=0)
            seg.translate(off)
        elif rmode == "end":
            off = np.zeros(3)
            off[:2] = -root[ib, :2]
            seg.translate(off)
        # --------------------------------------------------- time mapping
        if "warp" in sopt or ("warp" in rc and len(srcs) == 1):
            warp = Warp(sopt.get("warp", rc.get("warp")))
            dur = warp.duration
            N = int(round(dur * FPS)) + 1
            sfr = warp.src(warp.t[0] + np.arange(N) / FPS)
            to_out = lambda f, w=warp: w.out(f) - w.t[0]
        else:
            src_dur = (b - a) / seg.fps
            if loop and travel_v > 0:
                v_src = np.linalg.norm(S.P[b, S.idx["root"], :2] - S.P[a, S.idx["root"], :2]) / src_dur
                k = travel_v / (v_src * scale)
                dur = src_dur / k
            elif "dur" in sopt or "dur" in rc:
                dur = float(sopt.get("dur", rc.get("dur")))
            else:
                dur = src_dur / float(sopt.get("rate", rc.get("rate", 1.0)))
            if loop and rc.get("pingpong"):
                N = max(4, int(round(dur * FPS)))
                x = np.arange(N + 1) / N
                tri = 1 - np.abs(2 * x - 1)
                sfr = a + (b - a) * (0.5 - 0.5 * np.cos(np.pi * tri))  # ease at the turning points
            elif loop:
                N = max(4, int(round(dur * FPS)))
                sfr = a + (b - a) * np.arange(N + 1) / N  # N frames + the end sample (for the seam)
            else:
                N = int(round(dur * FPS)) + 1
                sfr = a + (b - a) * np.arange(N) / (N - 1)
            to_out = lambda f, a=a, b=b, N=N: (f - a) / (b - a) * ((N if loop else N - 1) / FPS)
        Qw, P, T = sample_seg(seg, sfr)
        L, H = retarget(tg, seg, Qw, P, scale)
        for ev in sopt.get("events", rc.get("events", []) if len(srcs) == 1 else []):
            nm, val = ev[0], ev[1]
            tt = val if isinstance(val, float) else to_out(val)
            events.append((nm, t_offset + tt))
        nb = srcs[si + 1][3].get("blend", 4) if si + 1 < len(srcs) and len(srcs[si + 1]) > 3 else 4
        segs_out.append(dict(L=L, H=H, blend=sopt.get("blend", 4), notes=f"{trial} {'mirrored ' if sopt.get('mirror', rc.get('mirror')) else ''}frames {a}-{b}"))
        t_offset += ((len(L) - nb) if nb > 0 else (len(L) - 1)) / FPS
    # --------------------------------------------------- concatenate segments
    L, H = segs_out[0]["L"], segs_out[0]["H"]
    for s in segs_out[1:]:
        n = s["blend"]
        L2, H2 = s["L"], s["H"].copy()
        H2[:, :2] += H[-n if n else -1, :2] - H2[0, :2]
        if n > 0:
            w = np.linspace(0, 1, n + 2)[1:-1]
            w = w * w * (3 - 2 * w)
            Lb = Q.qslerp(L[-n:], L2[:n], np.broadcast_to(w[:, None], (n, L.shape[1])))
            Hb = H[-n:] * (1 - w[:, None]) + H2[:n] * w[:, None]
            L = np.concatenate([L[:-n], Lb, L2[n:]])
            H = np.concatenate([H[:-n], Hb, H2[n:]])
        else:
            L = np.concatenate([L, L2[1:]])
            H = np.concatenate([H, H2[1:]])
    L = Q.qhemi(L)
    # --------------------------------------------------- seamless loop (error distribution)
    if loop:
        N = len(L) - 1
        e = Q.qmul(Q.qconj(L[N]), L[0])
        k = (np.arange(N + 1) / N)[:, None]
        L = Q.qmul(L, Q.qpow(np.broadcast_to(e, L.shape), np.broadcast_to(k, L.shape[:2])))
        H = H + (H[0] - H[N])[None, :] * k
        L, H = L[:N], H[:N]
    # --------------------------------------------------- smoothing
    sig = float(rc.get("smooth", 0.7))
    if sig > 0:
        L = Q.qsmooth(L, sig, cyclic=loop)
        H = Q.smooth(H, sig, cyclic=loop)
    hs = float(rc.get("hand_smooth", 1.4))
    for s in ("LeftHand", "RightHand"):
        i = tg.sidx[s]
        L[:, i] = Q.qsmooth(L[:, i], hs, cyclic=loop)
    L = wrist_limit(tg, L, float(rc.get("wrist_limit", 60)))
    # --------------------------------------------------- un-turn (end facing back to the start facing)
    if rc.get("unturn") is not None and rc.get("unturn") is not False:
        L, H = unturn(tg, L, H, float(rc["unturn"]) if not isinstance(rc["unturn"], bool) else 0.0)
    # --------------------------------------------------- posture (upright trunk, neck in line, level head, straight wrists)
    plog = None
    if not opt("--no-posture") and not rc.get("no_posture"):
        L, H, plog = posture.fix(tg, name, L, H, cyclic=loop)
    if rc.get("crouch"):
        L, H = crouch(tg, L, H, float(rc["crouch"]))
        if plog is not None:
            plog["crouch_drop"] = float(rc["crouch"])
    # --------------------------------------------------- ground + feet
    g = rc.get("ground", "feet")
    if isinstance(g, (int, float)):
        H = H + np.array([0, 0, float(g)])
    elif g in ("feet", "body"):
        H = H + np.array([0, 0, ground_offset(tg, L, H, g)])
    if rc.get("ground_add"):
        H = H + np.array([0, 0, float(rc["ground_add"])])
    zl = rc.get("zlock")
    if zl == "first":
        H[:, 2] = H[0, 2]
    elif zl == "stand":
        H[:, 2] = tg.head[tg.hips][2] - 0.03
    elif isinstance(zl, (int, float)) and not isinstance(zl, bool):
        H[:, 2] = float(zl)
    if rc.get("zloop"):
        # vertical in place (ladder climbing): remove the linear rise over the loop, keep the bob
        n = len(H)
        H[:, 2] -= np.linspace(0, 1, n) * (H[-1, 2] - H[0, 2]) if not loop else (np.arange(n) / n) * 0
        H[:, 2] += (tg.head[tg.hips][2] + float(rc.get("zloop_offset", 0.0))) - H[:, 2].mean()
    if rc.get("feet", "lock") == "lock":
        if plog is not None:
            # standing idles: straighter knees (the foot lock below re-plants the feet with leg IK)
            H, plog["knee_raise"] = posture.straighten_knees(tg, name, L, H)
        L = foot_lock(tg, L, H, travel_v, loop, rc.get("feet_opts", {}))
        if g == "feet":
            H = H + np.array([0, 0, ground_offset(tg, L, H, "feet")])
    # --------------------------------------------------- hold
    if rc.get("hold_end"):
        n = int(round(float(rc["hold_end"]) * FPS))
        L = np.concatenate([L, np.repeat(L[-1:], n, 0)])
        H = np.concatenate([H, np.repeat(H[-1:], n, 0)])
    # --------------------------------------------------- fingers
    Nf = len(L)
    track = finger_track(rc.get("fingers", "relaxed"), Nf, Nf / FPS)
    for k in range(Nf):
        for i, q in finger_quats(tg, track[k][0], track[k][1]).items():
            L[k, i] = q
    L = Q.qhemi(L)
    if loop:
        L = np.concatenate([L, L[:1]])
        H = np.concatenate([H, H[:1]])
    dur = (len(L) - 1) / FPS
    events = sorted([(n, round(min(max(t, 0.0), dur), 3)) for n, t in events], key=lambda e: e[1])
    if plog is not None:
        plog["final"] = posture.measure(tg, L[:-1] if loop else L, H[:-1] if loop else H, loop)
    return dict(L=L, H=H, loop=loop, speed=travel_v, events=events, duration=dur, posture=plog,
                notes="; ".join(s["notes"] for s in segs_out))


# =============================================================================================== bake / export

def bake_action(tg: Target, name, clip):
    rig = tg.rig
    act = bpy.data.actions.get(name)
    if act:
        bpy.data.actions.remove(act)
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    rig.animation_data_create()
    rig.animation_data.action = act
    L, H = clip["L"], clip["H"]
    N = len(L)
    frames = np.arange(1, N + 1, dtype=float)
    for pb in rig.pose.bones:
        pb.rotation_mode = "QUATERNION"
    hips_rest_inv = np.linalg.inv(np.array(rig.data.bones[tg.names[tg.hips]].matrix_local)[:3, :3])
    loc = (H - tg.head[tg.hips]) @ hips_rest_inv.T

    def fc(path, index, group, values):
        c = act.fcurve_ensure_for_datablock(rig, path, index=index, group_name=group)
        c.keyframe_points.clear()
        c.keyframe_points.add(N)
        co = np.empty(2 * N)
        co[0::2] = frames
        co[1::2] = values
        c.keyframe_points.foreach_set("co", co)
        c.keyframe_points.foreach_set("interpolation", [bpy.types.Keyframe.bl_rna.properties["interpolation"].enum_items["LINEAR"].value] * N)
        c.update()

    for i, bn in enumerate(tg.names):
        if not tg.deform[i]:
            continue
        path = f'pose.bones["{bn}"].rotation_quaternion'
        for c in range(4):
            fc(path, c, bn, L[:, i, c])
    hn = tg.names[tg.hips]
    for c in range(3):
        fc(f'pose.bones["{hn}"].location', c, hn, loc[:, c])
    act["eoa_loop"] = bool(clip["loop"])
    act["eoa_duration"] = float(clip["duration"])
    act.use_frame_range = True
    act.frame_start = 1
    act.frame_end = N
    return act


# Unity poses an imported model with animation in the first frame of its first take, and CharacterBuilder builds the
# animation avatar's T-pose (the humanoid muscle reference) from that pose. Without this take the first take was aim_l,
# whose torso is turned 26 deg against the pelvis while aiming: every clip then arrived on the heroes with the trunk
# turned 22-24 deg left of the pelvis. "_rest" sorts before every clip name (actions export in name order), so the
# avatar is built from the true rest pose.
REST_TAKE = "_rest"


def bake_rest(tg: Target):
    N = 2
    L = np.tile(np.array([1.0, 0, 0, 0]), (N, len(tg.names), 1))
    H = np.tile(tg.head[tg.hips], (N, 1))
    act = bake_action(tg, REST_TAKE, dict(L=L, H=H, loop=False, duration=(N - 1) / FPS))
    first = bpy.data.actions[0].name
    if first != REST_TAKE:
        raise RuntimeError(f"{REST_TAKE} is not the first action ({first}): Unity would build the avatar from another take")
    return act


def export_fbx(tg: Target, path):
    bake_rest(tg)
    rig = tg.rig
    rig.animation_data.action = None
    for pb in rig.pose.bones:
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)
    bpy.context.scene.render.fps = FPS
    bpy.context.scene.render.fps_base = 1.0
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={"ARMATURE"}, apply_scale_options="FBX_SCALE_ALL",
                             axis_forward="-Z", axis_up="Y", bake_space_transform=True, add_leaf_bones=False,
                             use_armature_deform_only=True, bake_anim=True, bake_anim_use_all_actions=True,
                             bake_anim_use_nla_strips=False, bake_anim_force_startend_keying=True, bake_anim_simplify_factor=0.0,
                             bake_anim_step=1.0)
    log("EXPORTED", path)


# =============================================================================================== previews

def setup_preview_scene(tg: Target):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    sh = scene.display.shading
    sh.light = "STUDIO"
    sh.color_type = "MATERIAL"
    sh.show_shadows = True
    sh.show_cavity = True
    sh.cavity_type = "WORLD"
    scene.display.shadow_focus = 0.6
    scene.render.resolution_x = int(opt("--res", 300))
    scene.render.resolution_y = int(int(opt("--res", 300)) * 4 / 3)
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    world = scene.world or bpy.data.worlds.new("W")
    scene.world = world
    # hide extra hair / facial variants
    keep = {"Hair_short", "Hair_ponytail", "Facial_beard"}
    for o in bpy.data.objects:
        if o.type == "MESH" and o.name.startswith(("Hair_", "Facial_")) and o.name not in keep:
            o.hide_render = True
    # floor with 0.5 m stripes to read foot sliding
    if "PreviewFloor" not in bpy.data.objects:
        mesh = bpy.data.meshes.new("PreviewFloor")
        verts, faces = [], []
        k = 0
        for i in range(-24, 24):
            for j in range(-8, 8):
                x0, y0 = j * 0.5, i * 0.5
                verts += [(x0, y0, 0), (x0 + 0.5, y0, 0), (x0 + 0.5, y0 + 0.5, 0), (x0, y0 + 0.5, 0)]
                faces.append((k, k + 1, k + 2, k + 3))
                k += 4
        mesh.from_pydata(verts, [], faces)
        mats = []
        for nm, col in (("FloorA", (0.55, 0.57, 0.6, 1)), ("FloorB", (0.42, 0.44, 0.48, 1))):
            m = bpy.data.materials.get(nm) or bpy.data.materials.new(nm)
            m.diffuse_color = col
            mesh.materials.append(m)
        for fi, poly in enumerate(mesh.polygons):
            i, j = divmod(fi, 16)
            poly.material_index = (i + j) % 2
        ob = bpy.data.objects.new("PreviewFloor", mesh)
        scene.collection.objects.link(ob)
    cam_data = bpy.data.cameras.get("PreviewCam") or bpy.data.cameras.new("PreviewCam")
    cam = bpy.data.objects.get("PreviewCam") or bpy.data.objects.new("PreviewCam", cam_data)
    if cam.name not in scene.collection.objects:
        scene.collection.objects.link(cam)
    cam_data.lens = 50
    scene.camera = cam
    return cam


def look_at(cam, eye, target):
    from mathutils import Vector
    eye, target = Vector(eye), Vector(target)
    cam.location = eye
    cam.rotation_euler = (target - eye).to_track_quat("-Z", "Y").to_euler()


def render_preview(tg: Target, name, clip, nframes, view="34"):
    scene = bpy.context.scene
    cam = setup_preview_scene(tg)
    act = bpy.data.actions[name]
    rig = tg.rig
    rig.animation_data.action = act
    N = len(clip["L"])
    out_dir = os.path.join(PREVIEW_DIR, "frames", f"{STYLE}_{name}" + ("" if view == "34" else "@" + view))
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):
        os.remove(os.path.join(out_dir, f))
    if isinstance(nframes, str) and nframes == "all":
        idx = list(range(N))
    else:
        nf = min(int(nframes), N)
        idx = sorted(set(np.linspace(0, N - 1 if not clip["loop"] else N - 2, nf).round().astype(int).tolist()))
    v = clip["speed"]
    H = clip["H"]
    h = tg.height
    for k in idx:
        t = k / FPS
        # move the rig like the character controller would
        rig.location = (0, -v * t, 0)
        scene.frame_set(k + 1)
        c = np.array([H[k, 0], H[k, 1] - v * t, 0.0])
        if view == "34":
            eye = c + np.array([2.6, -2.9, 1.25]) * (h / 1.8)
        elif view == "side":  # from the character's right
            eye = c + np.array([-4.2, -0.4, 1.0]) * (h / 1.8)
        elif view == "left":
            eye = c + np.array([4.2, -0.4, 1.0]) * (h / 1.8)
        elif view == "top":  # from above and behind: forward (-Y) points up in the image
            eye = c + np.array([0.0, 1.6, 4.6]) * (h / 1.8)
        elif view == "close":  # hands / upper body, front right
            eye = c + np.array([1.2, -1.6, 1.45]) * (h / 1.8)
        else:
            eye = c + np.array([0.3, -4.0, 1.1]) * (h / 1.8)
        tgt = c + np.array([0, 0, (1.15 if view == "close" else 0.85) * h / 1.8 if H[k, 2] > 0.6 else 0.4])
        look_at(cam, eye, tgt)
        scene.render.filepath = os.path.join(out_dir, f"{k:04d}.png")
        bpy.ops.render.render(write_still=True)
    rig.location = (0, 0, 0)
    with open(os.path.join(out_dir, "info.json"), "w") as f:
        json.dump(dict(clip=name, style=STYLE, frames=idx, n=N, fps=FPS, loop=clip["loop"], events=clip["events"],
                       speed=clip["speed"], duration=clip["duration"]), f)


# =============================================================================================== main

def main():
    t0 = time.time()
    rig = [o for o in bpy.data.objects if o.type == "ARMATURE"][0]
    tg = Target(rig)
    mod = clips_cmu
    if isinstance(opt("--recipes"), str):
        import importlib.util
        spec = importlib.util.spec_from_file_location("eoa_recipes_alt", opt("--recipes"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    recipes = mod.recipes(STYLE)
    names = list(recipes.keys())
    if opt("--clips"):
        names = [n for n in opt("--clips").split(",") if n]
    meta = {}
    report = []
    posture_report = {}
    for name in names:
        rc = recipes[name]
        t1 = time.time()
        clip = build_clip(tg, name, rc)
        bake_action(tg, name, clip)
        meta[name] = {"duration": round(clip["duration"], 4), "loop": clip["loop"],
                      "events": [{"t": t, "name": n} for n, t in clip["events"]], "speed": clip["speed"]}
        slide = leg_stats(tg, clip["L"][:-1] if clip["loop"] else clip["L"], clip["H"][:-1] if clip["loop"] else clip["H"], clip["speed"], clip["loop"])
        seam = float(np.degrees(np.max(Q.qangle(Q.qmul(Q.qconj(clip["L"][-1]), clip["L"][0]))))) if clip["loop"] else 0.0
        report.append((name, len(clip["L"]), clip["duration"], clip["loop"], slide, clip["notes"]))
        log(f"{name:12s} {len(clip['L']):4d}f {clip['duration']:.2f}s loop={clip['loop']} planted L/R={slide[0][0]:.0%}/{slide[1][0]:.0%} "
            f"slide med/p90 L={slide[0][1]:.2f}/{slide[0][2]:.2f} R={slide[1][1]:.2f}/{slide[1][2]:.2f} m/s "
            f"hipsZ={clip['H'][:, 2].min():.2f}..{clip['H'][:, 2].max():.2f} ev={clip['events']} ({time.time() - t1:.1f}s) [{clip['notes']}]")
        if clip.get("posture"):
            pl = clip["posture"]
            log(f"[posture] {name:12s} before: {posture.fmt(pl['before'])}")
            log(f"[posture] {name:12s} final:  {posture.fmt(pl.get('final', pl['after']))}  (knee raise {pl.get('knee_raise', 0.0) * 100:.1f} cm)")
            posture_report[name] = {k: v for k, v in pl.items() if k in ("before", "final", "knee_raise", "spec")}
        if opt("--preview"):
            for vw in str(opt("--view", "34")).split(","):
                render_preview(tg, name, clip, opt("--frames", 8), vw)
    if opt("--meta"):
        mp = os.path.join(UNITY_ANIM, "clips_meta.json")
        allm = json.load(open(mp)) if os.path.exists(mp) else {}
        st = allm.get(STYLE, {})
        st.update(meta)
        allm[STYLE] = st
        with open(mp, "w") as f:
            json.dump(allm, f, indent=1)
        log("META", mp)
    if posture_report:
        pr = os.path.join(HERE, f"posture_report_{STYLE}.json")
        with open(pr, "w") as f:
            json.dump(posture_report, f, indent=1)
        log("POSTURE REPORT", pr)
    Source.cleanup()
    if opt("--export"):
        export_fbx(tg, opt("--out") if isinstance(opt("--out"), str) else os.path.join(UNITY_ANIM, f"Anim_{STYLE.capitalize()}.fbx"))
    log(f"done in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
