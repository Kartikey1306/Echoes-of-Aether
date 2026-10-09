"""Verify exported robot FBX files against the C# contract (ROBOT_PARTS.md). Fails (exit code 1) on mismatch.

  /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python-exit-code 1 \
      --python check_robots.py -- [types...] [--dir other_folder]

Two independent readers are used for every file:
  1. Raw FBX (io_scene_fbx.parse_fbx): the node data Unity's importer sees -- unit scale, axes, root count,
     node names, parents, Lcl transforms (converted to Unity: x -> -x), material links, triangle counts.
  2. Blender re-import (bpy.ops.import_scene.fbx): names, parents, world pivots, rotations.
The contract (bone names + hierarchy tree, per-type joint tables, special parts, drone layout, heights, material
substrings, budgets) is parsed from ROBOT_PARTS.md at run time, so a contract change is picked up automatically.
`bolt` is not in the contract: it is checked against the same skeleton with joints from the RobotRig.ComputeJoints
port (robokit.compute_joints), which is itself validated against the four documented biped tables first.
"""
import json
import math
import os
import re
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import robokit as K  # noqa: E402
import roboscene as RS  # noqa: E402
from io_scene_fbx import parse_fbx  # noqa: E402

CONTRACT = os.path.join(RS.GAME, "unity", "EchoesOfAether", "Assets", "Scripts", "Enemies", "ROBOT_PARTS.md")
TOL = 0.01          # metres (contract: "a few cm")
EXTRA_BIPEDS = {"bolt": (1.55, 1.15)}   # not in the contract: (height, shoulder width) from Npc.ts
ALL = ["drone", "sentinel", "warden", "stalker", "guardian", "bolt"]


# ============================================================================ contract parsing
def parse_contract(path):
    txt = open(path, encoding="utf-8").read()
    c = {"tables": {}}
    # -- skeleton tree (code block after "Exactly these N transform names")
    m = re.search(r"Exactly these (\d+) transform names.*?```\n(.*?)```", txt, re.S)
    if not m:
        raise RuntimeError("contract: skeleton tree not found")
    c["bone_count"] = int(m.group(1))
    parents, order, stack = {}, [], []
    for line in m.group(2).splitlines():
        line = re.sub(r"\(.*?\)", "", line)
        toks = [(mm.start(), mm.group(0)) for mm in re.finditer(r"[A-Za-z]+(?:_[LR])?", line)]
        if not toks:
            continue
        col, name = toks[0]
        while stack and stack[-1][0] >= col:
            stack.pop()
        parents[name] = stack[-1][1] if stack else None
        order.append(name)
        stack.append((col, name))
        prev = name
        for _, nm in toks[1:]:
            parents[nm] = prev
            order.append(nm)
            prev = nm
    c["parents"] = parents
    c["bones"] = order
    # -- joint tables
    for sec in re.finditer(r"^### (\w+) \(height ([\d.]+) m, s = ([\d.]+), shoulderWidth ([\d.]+)\)\n(.*?)(?=^##)", txt, re.S | re.M):
        rows = {}
        for r in re.finditer(r"^\| `(\w+)` \| ([-+\d.]+) \| ([-+\d.]+) \| ([-+\d.]+) \|", sec.group(5), re.M):
            rows[r.group(1)] = tuple(float(r.group(i)) for i in (2, 3, 4))
        c["tables"][sec.group(1)] = {"height": float(sec.group(2)), "s": float(sec.group(3)),
                                     "shoulder": float(sec.group(4)), "joints": rows}
    # -- special parts
    m = re.search(r"\| `core`\s*\| `(\w+)`.*?\*\*\(([-\d.]+), ([-\d.]+), ([-\d.]+)\)\*\*", txt)
    c["core"] = {"parent": m.group(1), "pos": tuple(float(m.group(i)) for i in (2, 3, 4))}
    m = re.search(r"\| `plate_L`, `plate_R` \| `(\w+)`.*?Rest centres \(\+/-([\d.]+), ([\d.]+), ([\d.]+)\)", txt)
    c["plates"] = {"parent": m.group(1), "x": float(m.group(2)), "y": float(m.group(3)), "z": float(m.group(4))}
    m = re.search(r"slide sideways \(away from `core`, along local X\) by ([\d.]+) m", txt)
    c["plate_slide"] = float(m.group(1)) if m else None
    c["body_root_level"] = bool(re.search(r"\| `body`\s*\| prefab root \(drone\)", txt))
    m = re.search(r"\| `rotor_0`\.\.`rotor_(\d)` \| `(\w+)`", txt)
    c["rotors"] = {"count": int(m.group(1)) + 1, "parent": m.group(2)}
    m = re.search(r"\| `rotor_0\.\.\d` \| ([\d.]+) m out at the same angles, y ([\d.]+)", txt)
    c["rotors"]["radius"], c["rotors"]["y"] = float(m.group(1)), float(m.group(2))
    m = re.search(r"arms 0\.\.3 \| [\d.]+ m out at ([\d/]+) deg", txt)
    c["rotors"]["angles"] = [float(a) for a in m.group(1).split("/")]
    # -- heights, materials, budgets
    m = re.search(r"Overall heights \(feet to top of head\): (.*?)\.\n", txt)
    c["heights"] = {k: float(v) for k, v in re.findall(r"(\w+) ([\d.]+)", m.group(1))}
    m = re.search(r"### Materials.*?\n\| Substring.*?\n\|[-| ]+\|\n(.*?)\n\n", txt, re.S)
    subs = []
    for row in m.group(1).splitlines():
        subs += re.findall(r"`(\w+)`", row.split("|")[1])
    c["material_substrings"] = subs
    m = re.search(r"under ~(\d+)k triangles", txt)
    c["tri_budget"] = int(m.group(1)) * 1000 if m else None
    m = re.search(r"avoid more than (\d+) materials", txt)
    c["max_materials"] = int(m.group(1)) if m else None
    m = re.search(r"more than (\d+)% off", txt)
    c["hips_tol"] = int(m.group(1)) / 100 if m else 0.2
    return c


def expected_joints(c, kind):
    """Unity-space joint positions for a biped kind."""
    if kind in c["tables"]:
        return {k: v for k, v in c["tables"][kind]["joints"].items() if k in c["parents"]}
    h, sw = EXTRA_BIPEDS[kind]
    s = h / 1.8
    J = K.compute_joints(sw)
    return {b: (-J[b].x * s, J[b].y * s, J[b].z * s) for b in c["bones"]}


def validate_port(c):
    """robokit.compute_joints must reproduce every documented table (to the 3 decimals printed)."""
    errs = []
    for kind, tab in c["tables"].items():
        J = K.compute_joints(tab["shoulder"])
        s = tab["height"] / 1.8
        for name, (x, y, z) in tab["joints"].items():
            if name not in J:
                continue
            p = (-J[name].x * s, J[name].y * s, J[name].z * s)
            if max(abs(p[0] - x), abs(p[1] - y), abs(p[2] - z)) > 0.0015:
                errs.append("%s.%s port %s vs table %s" % (kind, name, tuple(round(v, 3) for v in p), (x, y, z)))
    return errs


# ============================================================================ raw FBX (Unity view)
def _name(prop):
    return prop.split(b"\x00\x01")[0].decode("utf-8")


def _p70(el):
    out = {}
    for ch in el.elems:
        if ch.id == b"Properties70":
            for p in ch.elems:
                out[p.props[0].decode()] = p.props[4:]
    return out


def read_fbx(path):
    root, ver = parse_fbx.parse(path)
    top = {e.id: e for e in root.elems}
    gs = _p70(top[b"GlobalSettings"])
    models, geoms, mats, conns = {}, {}, {}, []
    for e in top[b"Objects"].elems:
        if e.id == b"Model":
            pr = _p70(e)
            models[e.props[0]] = {"name": _name(e.props[1]), "type": e.props[2].decode(),
                                  "T": tuple(pr.get("Lcl Translation", (0, 0, 0))),
                                  "R": tuple(pr.get("Lcl Rotation", (0, 0, 0))),
                                  "S": tuple(pr.get("Lcl Scaling", (1, 1, 1))),
                                  "PreR": tuple(pr.get("PreRotation", (0, 0, 0))),
                                  "PostR": tuple(pr.get("PostRotation", (0, 0, 0))),
                                  "parent": None, "geom": None, "mats": []}
        elif e.id == b"Geometry":
            tris = 0
            if not any(ch.id == b"LayerElementUV" for ch in e.elems):
                geoms.setdefault("_nouv", set()).add(e.props[0])
            for ch in e.elems:
                if ch.id == b"Vertices":
                    vz = ch.props[0][2::3]
                    geoms.setdefault("_z", {})[e.props[0]] = (min(vz), max(vz)) if len(vz) else (0, 0)
                if ch.id == b"PolygonVertexIndex":
                    n = 0
                    for idx in ch.props[0]:
                        n += 1
                        if idx < 0:
                            tris += n - 2
                            n = 0
            geoms[e.props[0]] = tris
        elif e.id == b"Material":
            mats[e.props[0]] = _name(e.props[1])
    anim = any(e.id in (b"AnimationStack", b"AnimationCurve") for e in top[b"Objects"].elems)
    deformers = any(e.id == b"Deformer" for e in top[b"Objects"].elems)
    for cc in top[b"Connections"].elems:
        if cc.props[0] != b"OO":
            continue
        ch, pa = cc.props[1], cc.props[2]
        if ch in models:
            if pa == 0:
                models[ch]["parent"] = 0
            elif pa in models:
                models[ch]["parent"] = pa
        elif ch in geoms and pa in models:
            models[pa]["geom"] = ch
        elif ch in mats and pa in models:
            models[pa]["mats"].append(mats[ch])
    unit = gs.get("UnitScaleFactor", (1.0,))[0] / 100.0      # Unity "Convert Units": 1 file unit -> unit metres
    byname = {}
    zr = geoms.pop("_z", {})
    nouv = geoms.pop("_nouv", set())
    for uid, m in models.items():
        m["tris"] = geoms.get(m["geom"], 0) if m["geom"] else 0
        m["zrange"] = zr.get(m["geom"]) if m["geom"] else None
        m["has_uv"] = m["geom"] not in nouv
        m["parent_name"] = models[m["parent"]]["name"] if m["parent"] not in (None, 0) else None
        byname[m["name"]] = m
    # Unity positions (all rotations must be identity for this sum to be the world position; checked below)
    for m in models.values():
        p, q = [0.0, 0.0, 0.0], m
        while q is not None:
            p[0] += -q["T"][0] * unit
            p[1] += q["T"][1] * unit
            p[2] += q["T"][2] * unit
            q = models[q["parent"]] if q["parent"] not in (None, 0) else None
        m["unity_pos"] = tuple(p)
    return {"version": ver, "global": {k: v[0] if v else None for k, v in gs.items()}, "models": byname,
            "roots": [m["name"] for m in models.values() if m["parent"] == 0], "unit": unit,
            "has_anim": anim, "has_deformers": deformers}


def runtime_material(kind, objname, matname, is_core):
    """Replay of RobotRig.TryBindModel's swap rule."""
    key = (matname + " " + objname).lower()
    if is_core or (kind == "guardian" and "core" in key):
        return "core"
    if "glow" in key or "emissive" in key:
        return "glow"
    for k in ("rotor", "shell", "frame", "joint"):
        if k in key:
            return k
    return None


# ============================================================================ checks
class Report:
    def __init__(self, kind):
        self.kind, self.errors, self.warnings, self.info = kind, [], [], {}

    def err(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)


def check_raw(c, kind, path, rep):
    f = read_fbx(path)
    g = f["global"]
    rep.info["fbx_version"] = f["version"]
    rep.info["unit_scale_factor"] = g.get("UnitScaleFactor")
    if abs(f["unit"] - 1.0) > 1e-6:
        rep.err("UnitScaleFactor %s: Unity would not import 1 unit = 1 m" % g.get("UnitScaleFactor"))
    axes = tuple(g.get(k) for k in ("UpAxis", "UpAxisSign", "FrontAxis", "FrontAxisSign", "CoordAxis", "CoordAxisSign"))
    if axes != (1, 1, 2, 1, 0, 1):
        rep.err("FBX axis system %s is not Y-up right-handed (Unity converts that one with a plain X flip)" % (axes,))
    if len(f["roots"]) < 2:
        rep.err("only one root node %s: Unity would collapse it into the prefab root and lose its name" % f["roots"])
    if f["has_anim"]:
        rep.err("FBX contains animation data (contract: no clips)")
    if f["has_deformers"]:
        rep.warn("FBX contains deformers (expected rigid parts)")
    M = f["models"]
    for n, m in M.items():
        for key in ("R", "PreR", "PostR"):
            if max(abs(v) for v in m[key]) > 1e-3:
                rep.err("%s has non-identity %s %s" % (n, key, m[key]))
        if max(abs(v - 1) for v in m["S"]) > 1e-4:
            rep.err("%s has non-unit scale %s" % (n, m["S"]))
    # names / parents / pivots
    exp = {}
    if kind == "drone":
        r = c["rotors"]
        exp["body"] = (None, (0.0, 0.0, 0.0))
        for i, a in enumerate(r["angles"][: r["count"]]):
            ar = math.radians(a)
            exp["rotor_%d" % i] = (r["parent"], (-math.sin(ar) * r["radius"], r["y"], math.cos(ar) * r["radius"]))
    else:
        J = expected_joints(c, kind)
        for b in c["bones"]:
            exp[b] = (c["parents"][b], J[b])
        if kind.startswith("guardian"):
            exp["core"] = (c["core"]["parent"], c["core"]["pos"])
            p = c["plates"]
            exp["plate_L"] = (p["parent"], (-p["x"], p["y"], p["z"]))
            exp["plate_R"] = (p["parent"], (p["x"], p["y"], p["z"]))
    worst = 0.0
    for n, (par, pos) in exp.items():
        m = M.get(n)
        if m is None:
            rep.err("missing transform '%s'" % n)
            continue
        if m["parent_name"] != par:
            rep.err("'%s' parent is '%s', contract wants '%s'" % (n, m["parent_name"], par))
        d = math.dist(m["unity_pos"], pos)
        worst = max(worst, d)
        if d > TOL:
            rep.err("'%s' pivot %s vs contract %s (%.3f m off)" % (n, tuple(round(v, 3) for v in m["unity_pos"]), pos, d))
    rep.info["max_pivot_error_m"] = round(worst, 5)
    rep.info["checked_transforms"] = len(exp)
    # duplicate contract names (RobotRig keeps the first match)
    names = [m["name"] for m in M.values()]
    for n in exp:
        if names.count(n) > 1:
            rep.err("duplicate transform name '%s'" % n)
    if kind == "drone":
        if "body" in M and M["body"]["parent_name"] is not None:
            rep.err("drone 'body' must be a child of the prefab root")
    if kind.startswith("guardian") and all(k in M for k in ("core", "plate_L", "plate_R")):
        if not (M["core"]["parent_name"] == M["plate_L"]["parent_name"] == M["plate_R"]["parent_name"]):
            rep.err("core and plates must share a parent (Guardian.cs computes the slide direction from it)")
        if not (M["plate_L"]["unity_pos"][0] < M["core"]["unity_pos"][0] < M["plate_R"]["unity_pos"][0]):
            rep.err("plate_L must be at -X of the core and plate_R at +X")
    if kind != "drone":
        # facing: toes must point to +Z in Unity (FBX z is not flipped by the importer)
        for ft in ("foot_L", "foot_R"):
            zr = M.get(ft, {}).get("zrange")
            if zr is None:
                rep.err("%s has no mesh to verify facing" % ft)
            elif not zr[1] > -zr[0]:
                rep.err("%s mesh extends further back (%.3f) than forward (%.3f): model not facing +Z" % (ft, zr[0], zr[1]))
        hips_y = M["hips"]["unity_pos"][1] if "hips" in M else 0
        h = c["heights"].get(kind, EXTRA_BIPEDS.get(kind, (None,))[0])
        expect = h / 1.8 * 0.955
        rep.info["hips_height"] = round(hips_y, 4)
        if abs(hips_y / expect - 1) > c["hips_tol"]:
            rep.err("hips height %.3f vs RobotRig expectation %.3f" % (hips_y, expect))
    # materials and the runtime swap
    used, tris = set(), 0
    core_name = "core" if kind.startswith("guardian") else None
    for n, m in M.items():
        if m["type"] != "Mesh":
            continue
        if not m["has_uv"]:
            rep.err("mesh '%s' has no UV layer" % n)
        tris += m["tris"]
        for mat in m["mats"]:
            used.add(mat)
            got = runtime_material("guardian" if kind.startswith("guardian") else kind, n, mat, n == core_name)
            want = runtime_material("", "", mat, n == core_name)
            if n == core_name:
                want = "core"
            if got != want:
                rep.err("renderer '%s' slot '%s' would be swapped to robot_%s instead of robot_%s" % (n, mat, got, want))
            if got is None:
                rep.warn("material '%s' on '%s' matches no runtime substring (kept as authored, no hit flash)" % (mat, n))
    rep.info["triangles"] = tris
    rep.info["materials"] = sorted(used)
    rep.info["mesh_objects"] = sum(1 for m in M.values() if m["type"] == "Mesh")
    rep.info["nodes"] = len(M)
    if c["max_materials"] and len(used) > c["max_materials"]:
        rep.warn("%d materials (contract guideline: max %d)" % (len(used), c["max_materials"]))
    if c["tri_budget"] and tris > c["tri_budget"]:
        rep.warn("%d triangles (contract guideline ~%d for WebGL)" % (tris, c["tri_budget"]))
    if kind == "drone":
        for i in range(c["rotors"]["count"]):
            rn = "rotor_%d" % i
            for n, m in M.items():
                if m["parent_name"] == rn and m["type"] == "Mesh" and "rotor" not in " ".join(m["mats"]).lower():
                    if "rotor" in n.lower():
                        rep.err("blade mesh '%s' under %s contains 'rotor' in its name (would become transparent)" % (n, rn))
    return f


def check_blender(c, kind, path, rep, raw):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=path)
    objs = {}
    for o in bpy.data.objects:
        n = re.split(r"[|:]", o.name)[-1]
        objs.setdefault(n, o)
    want = [n for n in raw["models"]]
    missing = [n for n in want if n not in objs]
    if missing:
        rep.err("blender re-import lost nodes: %s" % missing[:8])
    worst = 0.0
    for n, m in raw["models"].items():
        o = objs.get(n)
        if o is None:
            continue
        par = re.split(r"[|:]", o.parent.name)[-1] if o.parent else None
        if par != m["parent_name"]:
            rep.err("re-import: '%s' parent %s vs %s" % (n, par, m["parent_name"]))
        u = K.b2u(o.matrix_world.translation)
        d = math.dist(tuple(u), m["unity_pos"])
        worst = max(worst, d)
        # In Blender the FBX->Blender axis conversion is a +90 X rotation on the roots; identity in FBX/Unity space
        # therefore shows up as exactly that rotation here.
        q = K.R2B.to_quaternion().rotation_difference(o.matrix_world.to_quaternion())
        ang = math.degrees(q.angle)
        ang = min(ang, 360 - ang)
        if ang > 0.05:
            rep.err("re-import: '%s' world rotation differs from identity (Unity space) by %.2f deg" % (n, ang))
        sc = o.matrix_world.to_scale()
        if max(abs(v - 1) for v in sc) > 1e-4:
            rep.err("re-import: '%s' world scale %s" % (n, tuple(sc)))
    rep.info["reimport_max_delta_m"] = round(worst, 6)
    # height of the mesh (feet to top) vs contract
    dg = bpy.context.evaluated_depsgraph_get()
    zs = []
    for o in bpy.data.objects:
        if o.type == "MESH":
            zs += [(o.matrix_world @ v.co).z for v in o.data.vertices]
    if zs and kind != "drone":
        top, bottom = max(zs), min(zs)
        rep.info["mesh_top_m"] = round(top, 3)
        rep.info["mesh_bottom_m"] = round(bottom, 3)
        h = c["heights"].get(kind, EXTRA_BIPEDS.get(kind, (None,))[0])
        if abs(bottom) > 0.03:
            rep.err("feet are not on the ground plane (lowest vertex %.3f m)" % bottom)
        if h and abs(top / h - 1) > 0.08:
            rep.warn("mesh top %.2f m vs contract height %.2f m" % (top, h))


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    src_dir = RS.UNITY_ROBOTS
    if "--dir" in argv:
        i = argv.index("--dir")
        src_dir = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    kinds = [a for a in argv if not a.startswith("--")] or ALL
    c = parse_contract(CONTRACT)
    print("[check] contract: %d bones, tables %s, core %s, plates %s, rotors %s, budget %s tris / %s materials" % (
        len(c["bones"]), sorted(c["tables"]), c["core"]["pos"], c["plates"], c["rotors"], c["tri_budget"], c["max_materials"]))
    failed = []
    if len(c["bones"]) != c["bone_count"] or set(c["bones"]) != set(K.BONES):
        failed.append("contract")
        print("[check] FAIL contract bone list mismatch: %s" % c["bones"])
    for b, p in zip(K.BONES, K.PARENT):
        if c["parents"].get(b) != (K.BONES[p] if p >= 0 else None):
            failed.append("contract")
            print("[check] FAIL contract parent of %s: %s vs robokit %s" % (b, c["parents"].get(b), K.BONES[p] if p >= 0 else None))
    perr = validate_port(c)
    print("[check] ComputeJoints port vs contract tables: %s" % ("OK" if not perr else perr))
    if perr:
        failed.append("port")
    reports = {}
    for kind in kinds:
        path = os.path.join(src_dir, kind + ".fbx")
        rep = Report(kind)
        if not os.path.exists(path):
            rep.err("missing file %s" % path)
        else:
            raw = check_raw(c, kind, path, rep)
            check_blender(c, kind, path, rep, raw)
        status = "PASS" if not rep.errors else "FAIL"
        if rep.errors:
            failed.append(kind)
        print("[check] %s %-9s %s" % (status, kind, json.dumps(rep.info, sort_keys=True)))
        for e in rep.errors:
            print("        ERROR  " + e)
        for w in rep.warnings:
            print("        warn   " + w)
        reports[kind] = {"status": status, "errors": rep.errors, "warnings": rep.warnings, "info": rep.info}
    out = os.path.join(RS.OUT_DIR, "check_report.json")
    os.makedirs(RS.OUT_DIR, exist_ok=True)
    with open(out, "w") as fh:
        json.dump(reports, fh, indent=1, sort_keys=True)
    print("[check] report -> %s" % out)
    if failed:
        print("[check] FAILED: %s" % sorted(set(failed)))
        raise RuntimeError("robot contract check failed: %s" % sorted(set(failed)))
    print("[check] ALL PASS")


main()
