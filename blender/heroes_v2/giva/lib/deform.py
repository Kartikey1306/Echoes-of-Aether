"""Deformation toolkit: twist bones, weight cleanup/smoothing/twist split, numpy linear blend skinning and
Delta-Mush corrective blend shapes (rest-space deltas)."""
import bpy, math
import numpy as np
from mathutils import Vector, Quaternion, Matrix
import gv

P = gv.P

TWIST = {  # twist bone -> (parent, fraction along parent)
    "LeftForeArmTwist": ("LeftForeArm", 0.6), "RightForeArmTwist": ("RightForeArm", 0.6),
    "LeftArmTwist": ("LeftArm", 0.6), "RightArmTwist": ("RightArm", 0.6),
}


def add_twist_bones(rig):
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    eb = rig.data.edit_bones
    for name, (par, f) in TWIST.items():
        if P + name in eb:
            eb.remove(eb[P + name])
        p = eb[P + par]
        b = eb.new(P + name)
        d = p.tail - p.head
        b.head = p.head + d * f
        b.tail = p.head + d * min(1.0, f + 0.25)
        b.align_roll(p.z_axis)
        b.parent = p
        b.use_connect = False
        b.use_deform = True
        b.inherit_scale = "FULL"
    bpy.ops.object.mode_set(mode="OBJECT")
    gv.log("twist bones", list(TWIST))


# ----------------------------------------------------------------------------- weights

def seg_dist(X, a, b):
    ab = b - a
    t = np.clip(((X - a) @ ab) / max(ab @ ab, 1e-12), 0, 1)
    return np.linalg.norm(X - (a + t[:, None] * ab), axis=1), t


def remove_strays(W, names, X, rig):
    """Drop influences of bones far from the vertex (distance to the bone segment)."""
    removed = 0
    for j, n in enumerate(names):
        b = rig.data.bones.get(n)
        if b is None:
            continue
        s = n[len(P):]
        if "Hand" in s and s not in ("LeftHand", "RightHand"):
            R = 0.05
        elif s in ("LeftHand", "RightHand"):
            R = 0.12
        elif s in ("LeftForeArm", "RightForeArm", "LeftArm", "RightArm"):
            R = 0.15
        elif s in ("LeftShoulder", "RightShoulder"):
            R = 0.2
        elif "Leg" in s or "Foot" in s or "Toe" in s:
            R = 0.2
        elif s in ("Jaw", "LeftEye", "RightEye") or "Orbicularis" in s:
            R = 0.12
        else:
            R = 0.35
        nz = np.nonzero(W[:, j] > 0)[0]
        if not len(nz):
            continue
        d, _ = seg_dist(X[nz], np.array(b.head_local), np.array(b.tail_local))
        far = nz[d > R]
        removed += len(far)
        W[far, j] = 0
    s = W.sum(1, keepdims=True)
    W = np.where(s > 0, W / np.maximum(s, 1e-12), W)
    gv.log("stray influences removed", removed)
    return W


def joint_mask(W, ix, X, rig, pair, radius, minsum=0.9, child_axis=True):
    """Vertices of a limb joint zone: weight mostly on the (parent, child) pair and within `radius` (metres,
    measured along the child bone axis) of the joint."""
    par, ch = pair
    b = rig.data.bones[P + ch]
    j = np.array(b.head_local)
    ax = np.array(b.tail_local) - j
    ax /= np.linalg.norm(ax)
    t = (X - j) @ ax
    s = W[:, ix[P + par]] + W[:, ix[P + ch]]
    return (s > minsum) & (np.abs(t) < radius), t


def smooth_weights(W, off, idx, mask, iters=8, lam=0.5):
    """Laplacian smoothing of all weight columns on masked vertices (others pinned)."""
    m = mask.astype(np.float64)
    for _ in range(iters):
        avg = gv.laplacian_avg(W, off, idx)
        W = W + (avg - W) * (lam * m)[:, None]
    s = W.sum(1, keepdims=True)
    return np.where(s > 0, W / np.maximum(s, 1e-12), W)


def twist_split(W, names, X, rig):
    """Move part of the forearm / upper-arm weights onto the twist bones (ramped along the bone)."""
    names = list(names)
    ix = {n: i for i, n in enumerate(names)}
    add = []
    for side in ("Left", "Right"):
        # forearm: elbow keeps ForeArm, wrist side goes to ForeArmTwist (driven at 50 % of the hand twist)
        fa = rig.data.bones[P + side + "ForeArm"]
        a, b = np.array(fa.head_local), np.array(fa.tail_local)
        t = ((X - a) @ (b - a)) / ((b - a) @ (b - a))
        w = W[:, ix[P + side + "ForeArm"]]
        wt = w * gv.ss(0.3, 0.92, t)
        W[:, ix[P + side + "ForeArm"]] = w - wt
        add.append((P + side + "ForeArmTwist", wt))
        # upper arm: shoulder side goes to ArmTwist (it keeps 50 % of the upper-arm twist), elbow side stays Arm
        ua = rig.data.bones[P + side + "Arm"]
        a, b = np.array(ua.head_local), np.array(ua.tail_local)
        t = ((X - a) @ (b - a)) / ((b - a) @ (b - a))
        w = W[:, ix[P + side + "Arm"]]
        wt = w * (1 - gv.ss(0.25, 0.8, t))
        W[:, ix[P + side + "Arm"]] = w - wt
        add.append((P + side + "ArmTwist", wt))
    for n, col in add:
        names.append(n)
        W = np.concatenate([W, col[:, None]], 1)
    return W, names


# ----------------------------------------------------------------------------- skinning

def skin_mats(rig, names):
    """(B,4,4) armature-space skinning matrices for the current pose."""
    M = np.zeros((len(names), 4, 4))
    for j, n in enumerate(names):
        pb = rig.pose.bones[n]
        M[j] = np.array(pb.matrix @ rig.data.bones[n].matrix_local.inverted())
    return M


def lbs(X, W, M):
    """Linear blend skinning: X (N,3), W (N,B), M (B,4,4) -> (N,3) and per-vertex blended 3x3 (N,3,3)."""
    Xh = np.concatenate([X, np.ones((len(X), 1))], 1)
    Mv = np.einsum("nb,bij->nij", W, M)
    P_ = np.einsum("nij,nj->ni", Mv, Xh)[:, :3]
    return P_, Mv[:, :3, :3]


def pose_single(rig, bone, axis, deg):
    for pb in rig.pose.bones:
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = Quaternion()
        pb.location = Vector()
    if bone:
        rig.pose.bones[bone].rotation_quaternion = Quaternion(Vector(axis).normalized(), math.radians(deg))
    bpy.context.view_layer.update()


# ----------------------------------------------------------------------------- delta mush

class DeltaMush:
    def __init__(self, X, tris, off, idx, iters=20, lam=0.5):
        self.off, self.idx, self.iters, self.lam = off, idx, iters, lam
        self.tris = tris
        Xs = self.smooth(X)
        F = self.frames(Xs)
        self.d = np.einsum("nji,nj->ni", F, X - Xs)    # local coords (F^T (X - Xs))

    def smooth(self, X):
        return gv.smooth(X, self.off, self.idx, self.iters, self.lam)

    def frames(self, Xs):
        n = gv.vertex_normals(Xs, self.tris)
        first = self.idx[np.minimum(self.off[:-1], len(self.idx) - 1)]
        e = Xs[first] - Xs
        e = e - n * (e * n).sum(1, keepdims=True)
        t = gv.nrm(e)
        b = np.cross(n, t)
        return np.stack([t, b, n], axis=2)            # columns t, b, n

    def apply(self, P_):
        Ps = self.smooth(P_)
        G = self.frames(Ps)
        return Ps + np.einsum("nij,nj->ni", G, self.d)


def corrective(rig, X, W, names, dm, bone, axis, deg, mask_radius=0.28, base_deg=None):
    """Rest-space corrective delta that turns LBS at `deg` about `axis` (bone-local) into the Delta-Mush result.
    With base_deg, the delta of the base angle is subtracted (piecewise shapes)."""
    def at(angle):
        pose_single(rig, bone, axis, angle)
        M = skin_mats(rig, names)
        P_, Mv = lbs(X, W, M)
        T = dm.apply(P_)
        j = np.array(rig.pose.bones[bone].head)
        d = np.linalg.norm(P_ - j, axis=1)
        m = 1 - gv.ss(mask_radius * 0.6, mask_radius, d)
        D = (T - P_) * m[:, None]
        inv = np.linalg.inv(Mv + np.eye(3)[None] * 1e-9)
        return np.einsum("nij,nj->ni", inv, D)
    delta = at(deg)
    if base_deg is not None:
        delta = delta - at(base_deg)
    pose_single(rig, None, None, 0)
    return delta


# ----------------------------------------------------------------------------- runtime-equivalent driver (preview)

MAIN_CHILD = {"Hand": "HandMiddle1"}


def main_child(rig, bone):
    """Main child like TwistBones.LocalDirection: Middle1 for hands, else the farthest non-twist child."""
    b = rig.data.bones[bone]
    side = "Left" if "Left" in bone else ("Right" if "Right" in bone else "")
    if bone.endswith("Hand"):
        return P + side + "HandMiddle1"
    best, bl = None, -1
    for c in b.children:
        if "Twist" in c.name:
            continue
        l = (c.head_local - b.head_local).length
        if l > bl:
            best, bl = c.name, l
    return best


def swing_angle(rig, bone, parent, axis_world, child=None):
    """Runtime-equivalent bend angle (CorrectiveShapes.cs): rotation of the bone->child direction in the parent's
    frame away from its rest direction, signed by the right-hand rule about axis (Blender rest world space)."""
    child = child or main_child(rig, bone)
    pb, pc, pp = rig.pose.bones[bone], rig.pose.bones[child], rig.pose.bones[parent]
    rb, rc, rp = rig.data.bones[bone], rig.data.bones[child], rig.data.bones[parent]
    Pp = pp.matrix.to_3x3().inverted()
    Rp = rp.matrix_local.to_3x3().inverted()
    cur = (Pp @ (pc.head - pb.head)).normalized()
    rest = (Rp @ (rc.head_local - rb.head_local)).normalized()
    ax = (Rp @ Vector(axis_world)).normalized()
    cr = rest.cross(cur)
    sn = cr.length
    if sn < 1e-7:
        return 0.0
    return math.degrees(math.atan2(sn, rest.dot(cur))) * (cr / sn).dot(ax)


def corrective_weights(rig, defs):
    out = {}
    for d in defs:
        ang = swing_angle(rig, d["bone"], d["parent"], d["axis"], d.get("child"))
        f, t = d["from"], d["to"]
        w = float(np.clip((ang - f) / max(t - f, 1e-6), 0, 1))
        out[d["shape"]] = w ** d.get("power", 1.0)
    return out


def pose_swing(rig, bone, axis_world, deg):
    """Rest pose except `bone`, swung `deg` about the world-space axis (parent at rest)."""
    al = rig.data.bones[bone].matrix_local.to_3x3().inverted() @ Vector(axis_world)
    pose_single(rig, bone, al, deg)


def drive_correctives(rig, objs, defs, enable=True):
    w = corrective_weights(rig, defs) if enable else {d["shape"]: 0.0 for d in defs}
    for o in objs:
        ks = o.data.shape_keys
        if not ks:
            continue
        for n, v in w.items():
            k = ks.key_blocks.get(n)
            if k is not None:
                k.value = v
    return w


# ----------------------------------------------------------------------------- CoR (optimized centres of rotation)

def descendants(rig, bone):
    out = {bone}
    for b in rig.data.bones[bone].children_recursive:
        out.add(b.name)
    return out


def cor_corrective(rig, X, W, names, tris, bone, axis, deg, base_deg=None, sigma=0.1, mask_radius=0.35, world_axis=True):
    """Rest-space corrective: optimised-centre-of-rotation skinning (Le & Hodgins 2016) minus LBS, for a
    single joint `bone` rotated `deg` about `axis` (bone-local). The joint is a two-part problem: alpha = weight
    on bone + descendants (they all move with the same rigid transform)."""
    desc = descendants(rig, bone)
    cols = [j for j, n in enumerate(names) if n in desc]
    alpha = W[:, cols].sum(1)
    zone = (alpha > 1e-3) & (alpha < 1 - 1e-3)
    at = alpha[tris].mean(1)
    A = 0.5 * np.linalg.norm(np.cross(X[tris[:, 1]] - X[tris[:, 0]], X[tris[:, 2]] - X[tris[:, 0]]), axis=1)
    C = X[tris].mean(1)
    tz = (at > 1e-3) & (at < 1 - 1e-3)
    tA, tC, ta = A[tz], C[tz], at[tz]
    vi = np.nonzero(zone)[0]
    pstar = np.zeros((len(vi), 3))
    for s0 in range(0, len(vi), 512):
        av = alpha[vi[s0:s0 + 512]][:, None]
        s = 2 * av * (1 - av) * ta[None] * (1 - ta[None]) * np.exp(-((av - ta[None]) ** 2) / sigma ** 2) * tA[None]
        den = s.sum(1, keepdims=True)
        pstar[s0:s0 + 512] = (s @ tC) / np.maximum(den, 1e-20)

    def at_angle(angle):
        if world_axis:
            pose_swing(rig, bone, axis, angle)
        else:
            pose_single(rig, bone, axis, angle)
        M = skin_mats(rig, names)
        P_, Mv = lbs(X, W, M)
        MB = np.array(rig.pose.bones[bone].matrix @ rig.data.bones[bone].matrix_local.inverted())
        qB = Matrix(MB[:3, :3].tolist()).to_quaternion()
        T = P_.copy()
        av = alpha[vi]
        # quaternion blend between identity and qB
        q = np.stack([(1 - av) + av * qB.w, av * qB.x, av * qB.y, av * qB.z], 1)
        q /= np.linalg.norm(q, axis=1, keepdims=True)
        w, x, y, z = q.T
        R = np.stack([np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)], 1),
                      np.stack([2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)], 1),
                      np.stack([2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)], 1)], 1)
        ps_moved = pstar @ MB[:3, :3].T + MB[:3, 3]
        lbs_p = (1 - av)[:, None] * pstar + av[:, None] * ps_moved
        T[vi] = np.einsum("nij,nj->ni", R, X[vi] - pstar) + lbs_p
        j = np.array(rig.pose.bones[bone].head)
        d = np.linalg.norm(P_ - j, axis=1)
        m = 1 - gv.ss(mask_radius * 0.7, mask_radius, d)
        D = (T - P_) * m[:, None]
        inv = np.linalg.inv(Mv + np.eye(3)[None] * 1e-9)
        return np.einsum("nij,nj->ni", inv, D)

    delta = at_angle(deg)
    if base_deg is not None:
        delta = delta - at_angle(base_deg)
    pose_single(rig, None, None, 0)
    return delta
