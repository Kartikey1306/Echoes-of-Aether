"""Posture stage of the CMU retarget (blender/anim/cmu_retarget.py): "proper humanoid" clips at the source.

The raw CMU retarget carries the capture subjects' posture and calibration offsets: run 34-36 deg of trunk lean with the
neck at 41 deg, arms-crossed idle 33-36 deg, heads tilted sideways, wrists bent, soft knees in every idle. This stage
runs on each clip after retiming / smoothing and before grounding and foot locking, in the pipeline's own space
(Blender, Z up, the character faces -Y; L = rest-relative local quats [N,B,4], H = hips head [N,3]):

  1. Re-centre:  the clip's mean local rotation of the spine (Spine, Spine1, Spine2), neck, head and wrists becomes the
                 rig's upright rest (straight spine curve, level head, straight wrist); the motion around the mean is kept
                 (scaled by a per-category gain), so breathing, gestures and the run's counter-rotation stay.
  1b. Twist:     the clip-average yaw of the chest (Spine2) against the pelvis is removed by one constant twist spread
                 over Spine / Spine1 / Spine2 (about the parent's up axis), then the head's average yaw against the
                 pelvis over Neck / Head: the trunk and head face where the pelvis faces, square ("90 degrees") at rest.
                 Only the constant offset goes; the per-frame twist (the gait's shoulder counter-rotation, glances)
                 stays, now centred on 0. Standing idles and the combat stance keep their head glances within 10 degrees
                 of the chest (the capture subjects looked around up to 25 degrees), carried by the head (the neck takes
                 NECK_SHARE), so the neck stays within a few degrees of the trunk.
  2. Trunk:      the clip-average lean of the trunk (hips -> neck) is brought into its band (pitch) and to zero roll by
                 one constant rotation of the pelvis and upper body about the hips, in the character's frame; the legs
                 keep their world motion (their local rotations are re-solved), so the feet stay where they were.
  3. Neck:       the average neck segment stays within a few degrees of the trunk (no head pushed forward), no sideways
                 neck lean.
  4. Head:       average head roll levelled, average gaze inside its band (level for idles, slightly down for running).
  5. Knees:      standing idles are raised until the straighter leg is nearly straight (foot locking then re-plants
                 the feet with leg IK).

Every correction is a constant (per clip) rotation in the character frame or a re-centring, so loops stay seamless and
attack timing is untouched. Combat clips only get their head and neck levelled and their trunk lean capped; their
athletic crouch and strike motion are kept. Measured before/after values are logged per clip ("[posture]").
"""
import math

import numpy as np

import qmath as Q

UP = np.array([0.0, 0.0, 1.0])
FWD = np.array([0.0, -1.0, 0.0])

# Gains: share of the motion around the mean that is kept (1 = only the constant offset is removed).
# twist: square the chest and head to the pelvis (step 1b: their clip-average yaw against the pelvis removed);
# glance: largest head yaw against the chest kept (the look-around of the standing idles is compressed into it).
STAND = dict(spine=0.6, neck=0.6, head=0.6, wrist=0.5, torso=(-1.0, 4.0), roll=2.0, neck_max=6.0, gaze=(-6.0, 1.0), head_roll=2.0, knees=4.0, twist=True, glance=10.0)
LOCO = dict(spine=0.8, neck=0.6, head=0.6, wrist=0.5, roll=2.0, neck_max=5.0, gaze=(-10.0, 0.0), head_roll=2.0, twist=True)
# combat stance: the guard's spine is not re-centred (crouch and guard kept), but the trunk and head are squared to
# the pelvis
STANCE = dict(neck=0.7, head=0.7, wrist=0.7, torso=(2.0, 8.0), roll=3.0, neck_max=6.0, gaze=(-8.0, 0.0), head_roll=2.0, twist=True, glance=10.0)
STRIKE = dict(neck=1.0, head=1.0, wrist=0.7, torso=(-6.0, 14.0), neck_max=10.0, gaze=(-14.0, 4.0), head_roll=3.0)
REACT = dict(neck=1.0, head=1.0, wrist=0.7, head_roll=3.0, neck_max=12.0, gaze=(-20.0, 4.0))
# Acrobatics and hands-down work (leaps, spin kick, picking up, kneeling, climbing): the head keeps its own pitch (the
# performer looks where the move needs); only sideways head tilt and the wrists are cleaned.
ACRO = dict(wrist=0.7, head_roll=3.0)

SPEC = {
    "idle": STAND, "talk": STAND, "npc_crossed": STAND, "npc_hips": STAND, "wave": STAND,
    "npc_look": dict(STAND, spine=0.8, neck=0.9, head=0.9, torso=(0.0, 6.0), gaze=(-10.0, 4.0), glance=None),  # looks around
    "npc_work": dict(STAND, torso=(2.0, 10.0), neck_max=12.0, gaze=(-30.0, 0.0)),
    "npc_react": dict(REACT, neck=0.9, head=0.9, torso=(-2.0, 8.0), roll=3.0, neck_max=10.0, gaze=(-12.0, 3.0)),
    "interact": dict(REACT, torso=(-2.0, 8.0), roll=3.0, neck_max=10.0, gaze=(-12.0, 3.0)),
    "walk": dict(LOCO, torso=(2.0, 5.0)), "run": dict(LOCO, torso=(10.0, 12.0)), "sprint": dict(LOCO, torso=(12.0, 14.0)),
    "combat_idle": STANCE,
    # crouch: trunk inclined into the crouch, head up and level (knees are bent afterwards by cmu_retarget.crouch)
    "crouch_idle": dict(STAND, torso=(14.0, 20.0), neck_max=8.0, gaze=(-6.0, 2.0), knees=None),
    "crouch_walk": dict(LOCO, torso=(16.0, 22.0), neck_max=8.0, gaze=(-8.0, 1.0)),
    "k_light1": STRIKE, "k_light2": STRIKE, "k_light3": STRIKE, "k_heavy": dict(STRIKE, torso=(-6.0, 16.0)), "k_pulse": STRIKE,
    "l_quick1": STRIKE, "l_quick2": STRIKE, "l_heavy": STRIKE, "l_echo": dict(STRIKE, torso=(-6.0, 18.0)),
    "k_ult": ACRO, "l_ult": dict(wrist=0.7),  # l_ult spins 360 deg: no facing-relative averages
    "dash": dict(STRIKE, torso=(-6.0, 18.0)), "phase_step": STRIKE,
    "aim_l": dict(STRIKE, torso=(-3.0, 6.0), gaze=(-8.0, 3.0)), "aim_r": dict(STRIKE, torso=(-3.0, 6.0), gaze=(-8.0, 3.0)),
    "fire_l": dict(STRIKE, torso=(-3.0, 6.0), gaze=(-8.0, 3.0)), "fire_r": dict(STRIKE, torso=(-3.0, 6.0), gaze=(-8.0, 3.0)),
    "hit": dict(REACT, gaze=(-30.0, 4.0)), "stagger": dict(REACT, neck_max=15.0, gaze=(-35.0, 4.0)), "land": dict(REACT, torso=(-5.0, 25.0)), "jump": dict(REACT, torso=(-5.0, 15.0)),
    "fall": dict(REACT, torso=(4.0, 12.0), roll=3.0),
    "sit": dict(spine=0.7, neck=0.6, head=0.6, wrist=0.5, torso=(8.0, 14.0), roll=2.0, neck_max=8.0, gaze=(-12.0, 3.0), head_roll=2.0, twist=True, glance=10.0),
    "kneel_work": ACRO, "climb": ACRO, "pickup": ACRO,
    # lying / falling over / getting up: left as captured
    "lie": None, "death": None, "wake": None,
}


# ----------------------------------------------------------------------------------------------- helpers

def _norm(v):
    return v / np.maximum(1e-9, np.linalg.norm(v, axis=-1, keepdims=True))


def facing(tg, P, sigma=6.0, cyclic=False):
    """Per-frame character frame from the hip line: forward f[N,3], right r[N,3] (horizontal, smoothed)."""
    left = P[:, tg.sidx["LeftUpLeg"]] - P[:, tg.sidx["RightUpLeg"]]
    left[:, 2] = 0
    f = _norm(np.cross(_norm(left), UP))
    sigma = min(sigma, max(0.0, (len(f) - 1) / 3.5))  # the cyclic padding must fit in the clip
    f = _norm(Q.smooth(f, sigma, cyclic=cyclic))
    r = np.cross(f, UP)
    return f, r


def to_char(v, f, r):
    return np.stack([np.sum(v * r, -1), np.sum(v * f, -1), v[..., 2]], -1)


def pitch_deg(c):
    return np.degrees(np.arctan2(c[..., 1], c[..., 2]))


def roll_deg(c):
    return np.degrees(np.arctan2(c[..., 0], c[..., 2]))


def subtree(tg, root, exclude=()):
    out = []
    for i in range(len(tg.names)):
        j = i
        while j >= 0:
            if j in exclude:
                break
            if j == root:
                out.append(i)
                break
            j = tg.parent[j]
    return out


def char_rotation(f, r, q_char):
    """Constant rotation given in the character frame (r, f, up) -> per-frame world quaternions [N,4]."""
    w = float(np.clip(q_char[0], -1, 1))
    s = math.sqrt(max(0.0, 1 - w * w))
    if s < 1e-9:
        return np.tile([1.0, 0, 0, 0], (len(f), 1))
    a = q_char[1:] / s
    ang = 2 * math.acos(w)
    axis = _norm(a[0] * r + a[1] * f + a[2] * UP)
    return np.concatenate([np.full((len(f), 1), math.cos(ang / 2)), axis * math.sin(ang / 2)], -1)


def rotate_bones(tg, L, H, idx, q_world):
    """Rotate the world orientation of the bones idx (a subtree, given whole) by q_world[N,4]; others keep theirs."""
    D, _ = tg.fk(L, H)
    D2 = D.copy()
    D2[:, idx] = Q.qmul(q_world[:, None, :], D[:, idx])
    return tg.local(D2)


def yaw_rel(D, ref, i):
    """Per-frame yaw (degrees, + = towards the character's right) of bone i's forward against bone ref's, about ref's
    up axis (D: world deltas from the rest pose, so every bone's rest forward is the character's forward)."""
    up = Q.qrot(D[:, ref], UP)
    a = Q.qrot(D[:, ref], FWD)
    b = Q.qrot(D[:, i], FWD)
    a = a - up * np.sum(a * up, -1, keepdims=True)
    b = b - up * np.sum(b * up, -1, keepdims=True)
    # + about +Z turns left (the character faces -Y), so negate for "+ = right"
    return -np.degrees(np.arctan2(np.sum(up * np.cross(a, b), -1), np.sum(a * b, -1)))


def circ_mean(deg):
    r = np.radians(deg)
    return float(np.degrees(math.atan2(np.sin(r).mean(), np.cos(r).mean())))


def twist_bones(tg, L, shares, deg):
    """Yaw of deg (degrees, + = right; a constant or one value per frame) spread over bones ((short name, share), ...),
    each turned about its parent's up axis (left-multiplied local rotation): the subtree turns about the parent's
    vertical, the rest of the body is untouched."""
    deg = np.asarray(deg, float)
    for b, share in shares:
        i = tg.sidx[b]
        q = Q.qaxis([0, 0, 1], -np.radians(deg * share))  # + = right = negative about +Z (the character faces -Y)
        R = np.broadcast_to(tg.R[i], q.shape)
        tw = Q.qmul(Q.qmul(Q.qconj(R), q), R)
        L[:, i] = Q.qmul(np.broadcast_to(tw, L[:, i].shape), L[:, i])
    return L


SPINE_TWIST = (("Spine", 0.4), ("Spine1", 0.3), ("Spine2", 0.3))
HEAD_TWIST = (("Neck", 0.4), ("Head", 0.6))
NECK_SHARE = 0.1


def recentre(L, i, gain):
    q = Q.qhemi(L[:, i], np.array([1.0, 0, 0, 0]))
    m = Q.qnorm(q.mean(0))
    r = Q.qmul(np.broadcast_to(Q.qconj(m), q.shape), q)
    L[:, i] = Q.qpow(r, gain) if gain != 1.0 else r
    return L


def dir_with(c_mean, pitch=None, roll=0.0):
    """Unit char-frame direction with the given pitch / roll (degrees), from tan components."""
    p = math.radians(pitch if pitch is not None else math.degrees(math.atan2(c_mean[1], c_mean[2])))
    rl = math.radians(roll)
    return _norm(np.array([math.tan(rl), math.tan(p), 1.0]))


# ----------------------------------------------------------------------------------------------- measures

def measure(tg, L, H, cyclic=False):
    D, P = tg.fk(L, H)
    f, r = facing(tg, P, cyclic=cyclic)
    s = tg.sidx
    torso = to_char(P[:, s["Neck"]] - P[:, s["Hips"]], f, r)
    neck = to_char(P[:, s["Head"]] - P[:, s["Neck"]], f, r)
    gaze = to_char(Q.qrot(D[:, s["Head"]], FWD), f, r)
    hup = to_char(Q.qrot(D[:, s["Head"]], tg.dir[s["Head"]]), f, r)

    def knee(side):
        hip, kn, an = P[:, s[side + "UpLeg"]], P[:, s[side + "Leg"]], P[:, s[side + "Foot"]]
        a, b = _norm(hip - kn), _norm(an - kn)
        return 180.0 - np.degrees(np.arccos(np.clip(np.sum(a * b, -1), -1, 1)))

    def valgus(side):
        # knee offset from the hip-ankle line, sideways towards the body midline (+ = knock-kneed), degrees
        hip, kn, an = P[:, s[side + "UpLeg"]], P[:, s[side + "Leg"]], P[:, s[side + "Foot"]]
        ax = _norm(an - hip)
        off = (kn - hip) - np.sum((kn - hip) * ax, -1, keepdims=True) * ax
        inward = -r if side == "Right" else r  # towards the midline: left leg -> right side (+r), right leg -> -r
        lat = np.sum(off * inward, -1)
        L_ = np.linalg.norm(an - hip, axis=-1)
        return np.degrees(np.arctan2(lat, np.maximum(1e-6, L_ * 0.5)))

    wl = np.degrees(Q.qangle(L[:, s["LeftHand"]]))
    wr = np.degrees(Q.qangle(L[:, s["RightHand"]]))
    cy = yaw_rel(D, s["Hips"], s["Spine2"])
    ny = yaw_rel(D, s["Hips"], s["Neck"])
    hy = yaw_rel(D, s["Hips"], s["Head"])
    return dict(
        chest_yaw=circ_mean(cy), chest_yaw_max=float(np.abs(cy).max()), chest_yaw_sd=float(cy.std()),
        neck_yaw=circ_mean(ny), neck_yaw_max=float(np.abs(ny).max()),
        head_yaw=circ_mean(hy), head_yaw_max=float(np.abs(hy).max()),
        torso=float(pitch_deg(torso).mean()), torso_roll=float(roll_deg(torso).mean()),
        neck_rel=float((pitch_deg(neck) - pitch_deg(torso)).mean()), neck_roll=float(roll_deg(neck).mean()),
        head_roll=float(roll_deg(hup).mean()), gaze=float(np.degrees(np.arcsin(np.clip(gaze[:, 2], -1, 1))).mean()),
        gaze_yaw=float(np.degrees(np.arctan2(gaze[:, 0], gaze[:, 1])).mean()),
        knee_l=float(knee("Left").mean()), knee_r=float(knee("Right").mean()),
        valgus_l=float(valgus("Left").mean()), valgus_r=float(valgus("Right").mean()),
        wrist=float((wl.mean() + wr.mean()) / 2),
    )


def fmt(m):
    return (f"torso {m['torso']:.1f} (roll {m['torso_roll']:.1f}), neck vs torso {m['neck_rel']:.1f} (roll {m['neck_roll']:.1f}), "
            f"head roll {m['head_roll']:.1f}, gaze {m['gaze']:.1f} (yaw {m['gaze_yaw']:.1f}), knees {m['knee_l']:.0f}/{m['knee_r']:.0f}, "
            f"knee valgus {m['valgus_l']:.1f}/{m['valgus_r']:.1f}, wrists {m['wrist']:.0f}, "
            f"twist vs pelvis: chest {m.get('chest_yaw', 0):.1f} (max {m.get('chest_yaw_max', 0):.1f}), neck {m.get('neck_yaw', 0):.1f} "
            f"(max {m.get('neck_yaw_max', 0):.1f}), head {m.get('head_yaw', 0):.1f} (max {m.get('head_yaw_max', 0):.1f})")


# ----------------------------------------------------------------------------------------------- the stage

def fix(tg, name, L, H, cyclic=False):
    """Steps 1-4 (re-centre, trunk, neck, head). Returns new L, H and a log dict."""
    spec = SPEC.get(name, REACT)
    before = measure(tg, L, H, cyclic)
    if spec is None:
        return L, H, dict(before=before, after=before, spec="none")
    L = L.copy()
    s = tg.sidx
    # 1. re-centre on the upright rest
    for key, bones in (("spine", ("Spine", "Spine1", "Spine2")), ("neck", ("Neck",)), ("head", ("Head",)),
                       ("wrist", ("LeftHand", "RightHand"))):
        g = spec.get(key)
        if g is None:
            continue
        for b in bones:
            if b in s:
                L = recentre(L, s[b], g)
    L = Q.qhemi(L)
    # 1b. twist: the chest, then the head, squared to the pelvis (only the clip-average offset; two passes for the
    # coupling of the bones' axes), then the head's glances kept within the spec's limit
    if spec.get("twist"):
        hips = s["Hips"]
        for bones, measured in ((SPINE_TWIST, "Spine2"), (HEAD_TWIST, "Head")):
            for _ in range(2):
                D, _P = tg.fk(L, H)
                m = circ_mean(yaw_rel(D, hips, s[measured]))
                if abs(m) > 0.05:
                    L = twist_bones(tg, L, bones, -m)
        gl = spec.get("glance")
        if gl:
            # head yaw against the chest compressed into the limit and carried mostly by the head (the neck takes
            # NECK_SHARE), so the neck stays nearly square to the trunk
            D, _P = tg.fk(L, H)
            y = yaw_rel(D, s["Spine2"], s["Head"])
            want = y * min(1.0, gl / max(1e-6, float(np.abs(y).max())))
            L = twist_bones(tg, L, (("Neck", 1.0),), NECK_SHARE * want - yaw_rel(D, s["Spine2"], s["Neck"]))
            D, _P = tg.fk(L, H)
            L = twist_bones(tg, L, (("Head", 1.0),), want - yaw_rel(D, s["Spine2"], s["Head"]))
        L = Q.qhemi(L)

    def frame():
        D, P = tg.fk(L, H)
        f, r = facing(tg, P, cyclic=cyclic)
        return D, P, f, r

    # 2. trunk lean (pitch into band, roll to ~0) about the hips, legs kept in world space
    legs = set(subtree(tg, s["LeftUpLeg"])) | set(subtree(tg, s["RightUpLeg"]))
    upper = [i for i in subtree(tg, tg.hips) if i not in legs]
    if spec.get("torso") is not None or spec.get("roll") is not None:
        D, P, f, r = frame()
        c = to_char(P[:, s["Neck"]] - P[:, s["Hips"]], f, r).mean(0)
        p0, r0 = math.degrees(math.atan2(c[1], c[2])), math.degrees(math.atan2(c[0], c[2]))
        lo, hi = spec.get("torso") or (p0, p0)
        rl = spec.get("roll")
        p1 = min(max(p0, lo), hi)
        r1 = r0 if rl is None else min(max(r0, -rl), rl)
        if abs(p1 - p0) > 0.3 or abs(r1 - r0) > 0.3:
            q = Q.qfromto(_norm(c), dir_with(c, p1, r1))
            L = rotate_bones(tg, L, H, upper, char_rotation(f, r, q))
    # 3. neck in line with the trunk, no sideways neck lean
    nm = spec.get("neck_max")
    if nm is not None:
        D, P, f, r = frame()
        t = to_char(P[:, s["Neck"]] - P[:, s["Hips"]], f, r).mean(0)
        n = to_char(P[:, s["Head"]] - P[:, s["Neck"]], f, r).mean(0)
        tp = math.degrees(math.atan2(t[1], t[2]))
        npitch = math.degrees(math.atan2(n[1], n[2]))
        nroll = math.degrees(math.atan2(n[0], n[2]))
        target_p = min(max(npitch, tp - 4.0), tp + nm)
        if abs(target_p - npitch) > 0.3 or abs(nroll) > spec.get("head_roll", 3.0):
            q = Q.qfromto(_norm(n), dir_with(n, target_p, 0.0 if abs(nroll) > spec.get("head_roll", 3.0) else nroll))
            L = rotate_bones(tg, L, H, subtree(tg, s["Neck"]), char_rotation(f, r, q))
    # 4a. head roll level
    hr = spec.get("head_roll")
    if hr is not None:
        D, P, f, r = frame()
        u = to_char(Q.qrot(D[:, s["Head"]], tg.dir[s["Head"]]), f, r).mean(0)
        rr = math.degrees(math.atan2(u[0], u[2]))
        if abs(rr) > hr:
            q = Q.qfromto(_norm(u), dir_with(u, None, math.copysign(hr, rr)))
            L = rotate_bones(tg, L, H, subtree(tg, s["Head"]), char_rotation(f, r, q))
    # 4b. gaze band
    gb = spec.get("gaze")
    if gb is not None:
        D, P, f, r = frame()
        g = to_char(Q.qrot(D[:, s["Head"]], FWD), f, r).mean(0)
        g = _norm(g)
        gp = math.degrees(math.asin(max(-1.0, min(1.0, g[2]))))
        gt = min(max(gp, gb[0]), gb[1])
        if abs(gt - gp) > 0.3:
            h = math.hypot(g[0], g[1])
            tgt = np.array([g[0] / max(h, 1e-6) * math.cos(math.radians(gt)), g[1] / max(h, 1e-6) * math.cos(math.radians(gt)), math.sin(math.radians(gt))])
            q = Q.qfromto(g, tgt)
            L = rotate_bones(tg, L, H, subtree(tg, s["Head"]), char_rotation(f, r, q))
    L = Q.qhemi(L)
    after = measure(tg, L, H, cyclic)
    return L, H, dict(before=before, after=after, spec=name if name in SPEC else "default")


def straighten_knees(tg, name, L, H):
    """Step 5 (standing clips): raise the hips by a constant so the straighter leg reaches the target bend; the foot
    lock that follows pins the feet back to the floor with leg IK. Returns H and the raise (m)."""
    spec = SPEC.get(name, REACT)
    bend = spec.get("knees") if spec else None
    if not bend:
        return H, 0.0
    s = tg.sidx
    _, P = tg.fk(L, H)
    need = []
    for side in ("Left", "Right"):
        hip, kn, an = P[:, s[side + "UpLeg"]], P[:, s[side + "Leg"]], P[:, s[side + "Foot"]]
        a = np.linalg.norm(kn - hip, axis=-1)
        b = np.linalg.norm(an - kn, axis=-1)
        d = np.linalg.norm(an - hip, axis=-1)
        interior = math.radians(180.0 - bend)
        dt = np.sqrt(a * a + b * b - 2 * a * b * math.cos(interior))
        vert = np.abs(_norm(an - hip)[:, 2])
        need.append((dt - d) / np.maximum(0.5, vert))
    raise_ = float(np.clip(np.median(np.minimum(need[0], need[1])), 0.0, 0.06))
    return H + np.array([0, 0, raise_]), raise_
