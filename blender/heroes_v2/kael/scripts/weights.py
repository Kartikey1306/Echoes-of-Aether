"""Skin weights for Kael v2 (body and attachments).

The MPFB `mixamo_unity` weights (CC0) are the starting point. On the subdivided body they are cleaned up:
  - helper bones that the game never animates (breast, buttock, jaw, eyelids) are folded into their animated parents;
  - limb hinges (elbow, knee, wrist, ankle) get a clean, symmetric blend band centred on the joint bisector plane
    (width ~ half the limb diameter): a defined bend line without rubber-hosing or collapse;
  - forearm / upper-arm roll is split onto the twist bones along the bone (TwistBones.cs drives them);
  - Laplacian smoothing (sum preserving) over the joint regions, then at most 4 influences, renormalised.
"""
import bpy
import numpy as np
import meshops
import kcommon as K

PRE = K.PRE


def bone_frame(rig, name):
    b = rig.data.bones[PRE + name]
    mw = np.array(rig.matrix_world)
    h = (mw @ np.append(np.array(b.head_local), 1))[:3]
    t = (mw @ np.append(np.array(b.tail_local), 1))[:3]
    return h, t


def col(names, n):
    return names.index(PRE + n) if PRE + n in names else None


def ensure(names, W, n):
    if PRE + n not in names:
        names.append(PRE + n)
        W = np.concatenate([W, np.zeros((len(W), 1))], 1)
    return names, W


def fold(names, W, src, dst_shares):
    """Move the weight of bone src to dst bones by shares [(name, share)]."""
    i = col(names, src)
    if i is None:
        return W
    w = W[:, i].copy()
    W[:, i] = 0
    for n, s in dst_shares:
        j = col(names, n)
        if j is not None:
            W[:, j] += w * s
    return W


def hinge(names, W, co, rig, upper, lower, width, region_min=0.35, extent=2.5):
    """Re-blend between bone groups `upper` and `lower` across the joint (head of lower[0]) with a smoothstep band
    of +-width (metres) along the bisector normal."""
    hu, tu = bone_frame(rig, upper[0])
    hl, tl = bone_frame(rig, lower[0])
    du = K.nrm(tu - hu); dl = K.nrm(tl - hl)
    n = K.nrm(du + dl)
    s = (co - hl) @ n
    iu = [col(names, b) for b in upper if col(names, b) is not None]
    il = [col(names, b) for b in lower if col(names, b) is not None]
    Wu = W[:, iu].sum(1); Wl = W[:, il].sum(1)
    tot = Wu + Wl
    zone = (tot > region_min) & (np.abs(s) < width * extent)
    # radial guard: only near the limb axis (not the other arm/leg or the torso)
    r = np.linalg.norm((co - hl) - s[:, None] * n, axis=1)
    zone &= r < 0.12
    want_l = K.ss(-width, width, s)                     # fraction on the lower side
    # keep the relative split inside each group
    for idx, frac in ((iu, 1 - want_l), (il, want_l)):
        g = W[:, idx]
        gs = g.sum(1, keepdims=True)
        rel = np.where(gs > 1e-9, g / np.maximum(gs, 1e-9), 0)
        # a group with no weight yet takes its first bone
        rel[(gs[:, 0] <= 1e-9), 0] = 1.0
        newg = rel * (tot * frac)[:, None]
        W[np.ix_(zone, idx)] = newg[zone]
    return W


def twist_split(names, W, co, rig, bone, twist, t0, t1, invert=False):
    """Move part of `bone`'s weight to `twist` as a smooth ramp along the bone (t in 0..1 head->tail)."""
    h, t = bone_frame(rig, bone)
    d = t - h
    tt = (co - h) @ d / max(d @ d, 1e-12)
    share = K.ss(t0, t1, tt)
    if invert:
        share = 1 - share
    i = col(names, bone); j = col(names, twist)
    w = W[:, i].copy()
    W[:, i] = w * (1 - share)
    W[:, j] += w * share
    return W


def body_weights(body, rig):
    names, W = meshops.get_weights(body)
    co = K.get_co(body)
    mw = np.array(body.matrix_world)
    co = co @ mw[:3, :3].T + mw[:3, 3]
    E = meshops.edges_of(body)
    nb0 = int((W > 1e-4).sum(1).max())
    s = W.sum(1, keepdims=True)
    W = np.where(s > 0, W / np.maximum(s, 1e-9), 0)
    # --- fold helper bones
    for side in ("Left", "Right"):
        W = fold(names, W, side + "Breast", [("Spine2", 1.0)])
        W = fold(names, W, side + "Buttock", [("Hips", 0.6), (side + "UpLeg", 0.4)])
        W = fold(names, W, side + "OrbicularisTop", [("Head", 1.0)])
        W = fold(names, W, side + "OrbicularisBottom", [("Head", 1.0)])
        W = fold(names, W, side + "Eye", [("Head", 1.0)])
    W = fold(names, W, "Jaw", [("Head", 1.0)])
    for side in ("Left", "Right"):
        names, W = ensure(names, W, side + "ForeArmTwist")
        names, W = ensure(names, W, side + "ArmTwist")
    # --- pre-smooth the MPFB weights a little everywhere below the head (removes the low-res stair-steps)
    head = W[:, col(names, "Head")] if col(names, "Head") is not None else np.zeros(len(W))
    body_mask = 1 - K.ss(0.6, 0.95, head)
    W = meshops.smooth(W, E, iters=6, lam=0.5, mask=body_mask)
    # --- hinges
    for side in ("Left", "Right"):
        W = hinge(names, W, co, rig, [side + "Arm"], [side + "ForeArm"], 0.035)
        W = hinge(names, W, co, rig, [side + "ForeArm"], [side + "Hand"], 0.018, region_min=0.5)
        W = hinge(names, W, co, rig, [side + "UpLeg"], [side + "Leg"], 0.045)
        W = hinge(names, W, co, rig, [side + "Leg"], [side + "Foot"], 0.03, region_min=0.5)
    # --- twist zones
    for side in ("Left", "Right"):
        W = twist_split(names, W, co, rig, side + "ForeArm", side + "ForeArmTwist", 0.15, 0.85)
        W = twist_split(names, W, co, rig, side + "Arm", side + "ArmTwist", 0.25, 0.8, invert=True)
    # --- joint smoothing (sum preserving) then 4 influences
    W = meshops.smooth(W, E, iters=4, lam=0.5, mask=body_mask)
    W = meshops.limit_normalize(W, 4, 0.01)
    W = meshops.smooth(W, E, iters=2, lam=0.4, mask=body_mask)
    W = meshops.limit_normalize(W, 4, 0.01)
    meshops.set_weights(body, names, W)
    cnt = (W > 0).sum(1)
    return {"verts": len(W), "max_influences_before": nb0, "max_influences": int(cnt.max()),
            "hist": np.bincount(cnt, minlength=5).tolist(), "bones": int((W.max(0) > 0).sum())}


def rigid(o, bone):
    for g in list(o.vertex_groups):
        o.vertex_groups.remove(g)
    g = o.vertex_groups.new(name=PRE + bone)
    g.add(list(range(len(o.data.vertices))), 1.0, "REPLACE")


def attachment_weights(o, rig):
    if o.name == "Eyes":
        names, W = meshops.get_weights(o)
        keep = [n for n in names if n.endswith(("LeftEye", "RightEye", "Head"))]
        W = W[:, [names.index(n) for n in keep]]
        W = meshops.limit_normalize(W, 2, 0.01)
        # unweighted -> head
        if (W.sum(1) == 0).any() and PRE + "Head" in keep:
            W[W.sum(1) == 0, keep.index(PRE + "Head")] = 1
        meshops.set_weights(o, keep, W)
    else:
        rigid(o, "Head")
    if not any(m.type == "ARMATURE" for m in o.modifiers):
        m = o.modifiers.new("Armature", "ARMATURE"); m.object = rig
