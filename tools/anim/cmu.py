"""CMU Graphics Lab Motion Capture Database helpers (mocap.cs.cmu.edu).

The data used in this project was obtained from mocap.cs.cmu.edu.
The database was created with funding from NSF EIA-0196217.

* ASF/AMC parsing and forward kinematics (Acclaim convention used by the CMU files).
* BVH writer (Y up, metres, the CMU T-pose as the rest pose, 120 fps like the source).
* Small analysis helpers used to choose clips (speeds, foot contacts, stick-figure strips).

Only numpy is required (plus matplotlib for the strips). Runs with any Python 3.9+.
"""
from __future__ import annotations

import math
import os
import re
import urllib.request

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
CMU_DIR = os.path.join(ROOT, "blender", "anim", "cmu")
RAW_DIR = os.path.join(CMU_DIR, "raw")
BVH_DIR = os.path.join(CMU_DIR, "bvh")
BASE_URL = "http://mocap.cs.cmu.edu/subjects"

# CMU lengths are in (1/0.45) inches: metres = value / 0.45 * 0.0254
CMU_TO_M = 0.0254 / 0.45

# Capture rate of the AMC files (from the database index): 120 fps except these subjects/trials.
FPS60_SUBJECTS = {"33", "34", "42", "60", "61", "62", "74", "75", "77", "79", "80", "87", "88", "89"}
FPS60_TRIALS = {"136_19"}


def trial_fps(trial: str) -> float:
    return 60.0 if trial.split("_")[0] in FPS60_SUBJECTS or trial in FPS60_TRIALS else 120.0


# ----------------------------------------------------------------------------------------------- download

def fetch(trial: str) -> tuple[str, str]:
    """Download <subject>.asf and <trial>.amc (e.g. '135_04') into blender/anim/cmu/raw/<subject>/."""
    subj = trial.split("_")[0]
    d = os.path.join(RAW_DIR, subj)
    os.makedirs(d, exist_ok=True)
    out = []
    for name in (f"{subj}.asf", f"{trial}.amc"):
        p = os.path.join(d, name)
        if not os.path.exists(p) or os.path.getsize(p) == 0:
            url = f"{BASE_URL}/{subj}/{name}"
            tmp = p + ".part"
            with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
                f.write(r.read())
            os.replace(tmp, p)
        out.append(p)
    return out[0], out[1]


# ----------------------------------------------------------------------------------------------- maths

def rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def rot_y(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


ROT = {"x": rot_x, "y": rot_y, "z": rot_z}


def euler_to_mat(angles_deg, order="XYZ"):
    """Acclaim 'axis ... XYZ' / dof order: the rotation about the first axis is applied first,
    i.e. M = R_last @ ... @ R_first (column vectors)."""
    m = np.eye(3)
    for a, ax in zip(angles_deg, order.lower()):
        m = ROT[ax](math.radians(a)) @ m
    return m


def mat_to_euler_zyx(m):
    """Matrix -> BVH 'Zrotation Yrotation Xrotation' angles (degrees), M = Rz @ Ry @ Rx."""
    sy = -m[2, 0]
    sy = max(-1.0, min(1.0, sy))
    y = math.asin(sy)
    if abs(sy) < 0.999999:
        x = math.atan2(m[2, 1], m[2, 2])
        z = math.atan2(m[1, 0], m[0, 0])
    else:  # gimbal lock
        x = math.atan2(-m[1, 2], m[1, 1])
        z = 0.0
    return math.degrees(z), math.degrees(y), math.degrees(x)


# ----------------------------------------------------------------------------------------------- ASF / AMC

class Bone:
    def __init__(self, name):
        self.name = name
        self.direction = np.zeros(3)
        self.length = 0.0
        self.axis = np.zeros(3)
        self.axis_order = "XYZ"
        self.dof: list[str] = []
        self.parent: Bone | None = None
        self.children: list[Bone] = []
        self.C = np.eye(3)
        self.Cinv = np.eye(3)


class Skeleton:
    def __init__(self, path):
        self.bones: dict[str, Bone] = {}
        self.order: list[str] = []
        self.root_order = ["TX", "TY", "TZ", "RX", "RY", "RZ"]
        self.root_axis = "XYZ"
        self.length_scale = 1.0
        self._parse(path)

    def _parse(self, path):
        lines = [l.rstrip() for l in open(path, encoding="latin-1")]
        i = 0
        section = None
        root = Bone("root")
        self.bones["root"] = root
        self.order.append("root")
        cur = None
        while i < len(lines):
            line = lines[i].strip()
            i += 1
            if not line or line.startswith("#"):
                continue
            if line.startswith(":"):
                parts = line.split()
                section = parts[0][1:]
                if section == "units":
                    pass
                continue
            if section == "units":
                p = line.split()
                if p[0] == "length":
                    self.length_scale = float(p[1])
            elif section == "root":
                p = line.split()
                if p[0] == "order":
                    self.root_order = [x.upper() for x in p[1:]]
                elif p[0] == "axis":
                    self.root_axis = p[1].upper()
            elif section == "bonedata":
                p = line.split()
                if p[0] == "begin":
                    cur = None
                elif p[0] == "name":
                    cur = Bone(p[1])
                    self.bones[p[1]] = cur
                    self.order.append(p[1])
                elif p[0] == "direction":
                    cur.direction = np.array([float(x) for x in p[1:4]])
                elif p[0] == "length":
                    cur.length = float(p[1])
                elif p[0] == "axis":
                    cur.axis = np.array([float(x) for x in p[1:4]])
                    cur.axis_order = p[4].upper() if len(p) > 4 else "XYZ"
                elif p[0] == "dof":
                    cur.dof = [x.lower() for x in p[1:]]
            elif section == "hierarchy":
                p = line.split()
                if p[0] in ("begin", "end"):
                    continue
                par = self.bones[p[0]]
                for c in p[1:]:
                    self.bones[c].parent = par
                    par.children.append(self.bones[c])
        for b in self.bones.values():
            b.C = euler_to_mat(b.axis, b.axis_order)
            b.Cinv = b.C.T
        # Topological order (parents first).
        topo = []

        def walk(b):
            topo.append(b.name)
            for c in b.children:
                walk(c)
        walk(root)
        self.order = topo

    def scale(self):
        """Metres per ASF length unit."""
        return (1.0 / self.length_scale) * 0.0254

    def rest_offsets(self):
        """Joint position of each bone's START relative to its parent's start (metres, Y up)."""
        s = self.scale()
        off = {}
        for n in self.order:
            b = self.bones[n]
            if b.parent is None:
                off[n] = np.zeros(3)
            else:
                p = b.parent
                off[n] = p.direction * p.length * s if p.name != "root" else np.zeros(3)
        return off


def read_amc(path):
    """-> list of {bone: [values...]} per frame."""
    frames = []
    cur = None
    for line in open(path, encoding="latin-1"):
        line = line.strip()
        if not line or line.startswith("#") or line.startswith(":"):
            continue
        if re.match(r"^\d+$", line):
            cur = {}
            frames.append(cur)
            continue
        p = line.split()
        cur[p[0]] = [float(x) for x in p[1:]]
    return frames


def _rot_stack(axis, ang_deg):
    a = np.radians(ang_deg)
    c, s = np.cos(a), np.sin(a)
    m = np.zeros((len(a), 3, 3))
    if axis == "x":
        m[:, 0, 0] = 1; m[:, 1, 1] = c; m[:, 1, 2] = -s; m[:, 2, 1] = s; m[:, 2, 2] = c
    elif axis == "y":
        m[:, 1, 1] = 1; m[:, 0, 0] = c; m[:, 0, 2] = s; m[:, 2, 0] = -s; m[:, 2, 2] = c
    else:
        m[:, 2, 2] = 1; m[:, 0, 0] = c; m[:, 0, 1] = -s; m[:, 1, 0] = s; m[:, 1, 1] = c
    return m


def fk_arrays(skel: Skeleton, frames):
    """Vectorised forward kinematics. Returns dicts bone -> world rotation [F,3,3], start [F,3], end [F,3]
    (metres, Y up). At the ASF rest pose every world rotation is the identity."""
    s = skel.scale()
    F = len(frames)
    R, P, E = {}, {}, {}
    for n in skel.order:
        b = skel.bones[n]
        if n == "root":
            vals = np.array([fr.get("root", [0] * 6) for fr in frames], float).reshape(F, -1)
            tr = np.zeros((F, 3))
            m = np.tile(np.eye(3), (F, 1, 1))
            for k, ch in enumerate(skel.root_order):
                if ch.startswith("T"):
                    tr[:, "XYZ".index(ch[1])] = vals[:, k]
                else:
                    m = _rot_stack(ch[1].lower(), vals[:, k]) @ m
            R[n] = m
            P[n] = tr * s
            E[n] = P[n]
            continue
        nd = len(b.dof)
        m = np.tile(np.eye(3), (F, 1, 1))
        if nd:
            vals = np.array([fr.get(n, [0] * nd) for fr in frames], float).reshape(F, nd)
            for k, ax in enumerate(b.dof):
                m = _rot_stack(ax[1], vals[:, k]) @ m
        local = b.C @ m @ b.Cinv
        R[n] = R[b.parent.name] @ local
        P[n] = E[b.parent.name]
        E[n] = P[n] + R[n] @ (b.direction * b.length * s)
    return R, P, E


def fk(skel: Skeleton, frames):
    """Per-frame dict form of fk_arrays: (world_rot[F][bone], joint_start[F][bone], bone_end[F][bone])."""
    R, P, E = fk_arrays(skel, frames)
    F = len(frames)
    return ([{n: R[n][i] for n in skel.order} for i in range(F)],
            [{n: P[n][i] for n in skel.order} for i in range(F)],
            [{n: E[n][i] for n in skel.order} for i in range(F)])


# ----------------------------------------------------------------------------------------------- BVH

def write_bvh(skel: Skeleton, frames, path, fps=120.0, frame_range=None):
    """Write a BVH (metres, Y up) whose zero pose is the ASF rest pose. Joint frames are aligned with the
    world at rest, so each joint's rotation channels are its local rotation relative to the parent."""
    R_all, P_all, _ = fk(skel, frames if frame_range is None else frames[frame_range[0]:frame_range[1]])
    off = skel.rest_offsets()
    s = skel.scale()
    lines = ["HIERARCHY"]
    chan_order = []

    def emit(n, depth):
        b = skel.bones[n]
        ind = "  " * depth
        o = off[n]
        if n == "root":
            lines.append(f"ROOT {n}")
            lines.append("{")
            lines.append(f"  OFFSET 0.000000 0.000000 0.000000")
            lines.append("  CHANNELS 6 Xposition Yposition Zposition Zrotation Yrotation Xrotation")
        else:
            lines.append(f"{ind}JOINT {n}")
            lines.append(f"{ind}{{")
            lines.append(f"{ind}  OFFSET {o[0]:.6f} {o[1]:.6f} {o[2]:.6f}")
            lines.append(f"{ind}  CHANNELS 3 Zrotation Yrotation Xrotation")
        chan_order.append(n)
        if b.children:
            for c in b.children:
                emit(c.name, depth + 1)
        elif n != "root":
            e = b.direction * b.length * s
            lines.append(f"{ind}  End Site")
            lines.append(f"{ind}  {{")
            lines.append(f"{ind}    OFFSET {e[0]:.6f} {e[1]:.6f} {e[2]:.6f}")
            lines.append(f"{ind}  }}")
        lines.append(f"{ind}}}")

    emit("root", 0)
    lines.append("MOTION")
    lines.append(f"Frames: {len(R_all)}")
    lines.append(f"Frame Time: {1.0 / fps:.8f}")
    for R, P in zip(R_all, P_all):
        vals = []
        for n in chan_order:
            b = skel.bones[n]
            if n == "root":
                vals += list(P[n])
                local = R[n]
            else:
                local = R[b.parent.name].T @ R[n]
            vals += list(mat_to_euler_zyx(local))
        lines.append(" ".join(f"{v:.5f}" for v in vals))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return path


def load(trial):
    asf, amc = fetch(trial)
    sk = Skeleton(asf)
    fr = read_amc(amc)
    return sk, fr


def to_bvh(trial, fps=None):
    fps = fps or trial_fps(trial)
    sk, fr = load(trial)
    out = os.path.join(BVH_DIR, f"{trial}.bvh")
    if not os.path.exists(out) or os.path.getmtime(out) < os.path.getmtime(os.path.join(RAW_DIR, trial.split('_')[0], trial + '.amc')):
        write_bvh(sk, fr, out, fps)
    return out


# ----------------------------------------------------------------------------------------------- analysis

def positions(trial):
    sk, fr = load(trial)
    R, P, E = fk_arrays(sk, fr)
    names = sk.order
    J = np.stack([P[n] for n in names], 1)  # joint starts [F,B,3]
    Ee = np.stack([E[n] for n in names], 1)
    return sk, names, J, Ee


SEGS = [("root", "lhipjoint"), ("lfemur", "ltibia"), ("ltibia", "lfoot"), ("lfoot", "ltoes"),
        ("root", "rhipjoint"), ("rfemur", "rtibia"), ("rtibia", "rfoot"), ("rfoot", "rtoes"),
        ("root", "lowerback"), ("lowerback", "upperback"), ("upperback", "thorax"), ("thorax", "lowerneck"),
        ("lowerneck", "upperneck"), ("upperneck", "head"), ("thorax", "lclavicle"), ("lhumerus", "lradius"),
        ("lradius", "lwrist"), ("lwrist", "lhand"), ("thorax", "rclavicle"), ("rhumerus", "rradius"),
        ("rradius", "rwrist"), ("rwrist", "rhand"), ("lclavicle", "lhumerus"), ("rclavicle", "rhumerus"),
        ("lhipjoint", "lfemur"), ("rhipjoint", "rfemur")]


def strip(trial, frames, out_png, title=None, view="side"):
    """Stick figures of the given frames side by side (front view and side view rows)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    sk, names, J, E = positions(trial)
    idx = {n: i for i, n in enumerate(names)}
    frames = [f for f in frames if 0 <= f < len(J)]
    n = len(frames)
    fig, axes = plt.subplots(2, n, figsize=(1.6 * n, 6.4), squeeze=False)
    # Heading of the first frame to orient the views consistently.
    for col, f in enumerate(frames):
        P = J[f].copy()
        Eh = E[f]
        P[:, [0, 2]] -= P[idx["root"], [0, 2]]
        for row, (a, b) in enumerate(((0, 1), (2, 1))):
            ax = axes[row][col]
            for s0, s1 in SEGS:
                if s0 in idx and s1 in idx:
                    p0, p1 = P[idx[s0]], P[idx[s1]]
                    left = s1.startswith("l") and s1 not in ("lowerback", "lowerneck")
                    ax.plot([p0[a], p1[a]], [p0[b], p1[b]], color="tab:blue" if left else "tab:red" if s1.startswith("r") and s1 != "root" else "k", lw=1.5)
            # head end + hands
            for nm in ("head", "lhand", "rhand"):
                e = Eh[idx[nm]].copy()
                e[[0, 2]] -= J[f][idx["root"], [0, 2]]
                ax.plot([P[idx[nm]][a], e[a]], [P[idx[nm]][b], e[b]], color="k", lw=1.5)
            ax.set_xlim(-1.2, 1.2)
            ax.set_ylim(-0.1, 2.3)
            ax.set_aspect("equal")
            ax.set_xticks([])
            ax.set_yticks([])
            if row == 0:
                ax.set_title(str(f), fontsize=8)
        axes[1][col].axhline(0, color="#aaa", lw=0.5)
    fig.suptitle(title or trial, fontsize=10)
    fig.tight_layout()
    fig.savefig(out_png, dpi=60)
    plt.close(fig)
    return out_png


def summary(trial):
    sk, names, J, E = positions(trial)
    idx = {n: i for i, n in enumerate(names)}
    root = J[:, idx["root"]]
    F = len(J)
    fps = trial_fps(trial)
    v = np.linalg.norm(np.diff(root[:, [0, 2]], axis=0), axis=1) * fps
    return {"frames": F, "fps": fps, "seconds": F / fps, "root_h_mean": float(root[:, 1].mean()),
            "speed_med": float(np.median(v)) if len(v) else 0.0, "speed_max": float(np.percentile(v, 95)) if len(v) else 0.0,
            "height": float((E[0, idx["head"], 1] - min(J[0, idx["ltoes"], 1], J[0, idx["rtoes"], 1])))}


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1]
    if cmd == "fetch":
        for t in sys.argv[2:]:
            print(t, fetch(t))
    elif cmd == "fetch-all":
        # every trial used by blender/anim/clips_cmu.py
        sys.path.insert(0, os.path.join(ROOT, "blender", "anim"))
        import clips_cmu
        trials = sorted({s[0] for st in ("male", "female") for r in clips_cmu.recipes(st).values() for s in r["src"]})
        for t in trials:
            print(t, fetch(t))
    elif cmd == "bvh":
        for t in sys.argv[2:]:
            print(to_bvh(t))
    elif cmd == "summary":
        for t in sys.argv[2:]:
            print(t, summary(t))
