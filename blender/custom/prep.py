"""Prepare a hero reference scene for the customisation builds.

  blender -b blender/out/hd/<cid>_base.blend --python blender/custom/prep.py -- <cid>

Keeps the MPFB rig + full body (basis = baked phenotype, shape keys m_* / x_*), eyes, brows, lashes, teeth and
tongue from the base build, imports the exported Unity hero (Assets/Art/Characters/<Name>/<Name>.fbx) as U_* meshes
re-parented to the base rig (exported Body with its final UV layout, outfit pieces for collision and previews),
marks which full-body vertices survive in the exported Body ("exposed" attribute) and reads the bind matrices of
the bones from the FBX file (for rigid attachments). Saves cache/<cid>_ref.blend and cache/<cid>_ref.json.
"""
import bpy, os, sys, json, math
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
from mathutils import Matrix, Vector, Euler
from mathutils.kdtree import KDTree

sys.path.insert(0, "/Applications/Blender.app/Contents/Resources/5.2/scripts/addons_core")
from io_scene_fbx import parse_fbx


def fbx_bones(path):
    """Global bind matrices (FBX file space, row-major 4x4) for every Model node; computed from the Lcl properties
    along the parent chain, plus the BindPose matrices when present."""
    root, ver = parse_fbx.parse(path)
    def child(e, name):
        for c in e.elems:
            if c.id == name:
                return c
    objects = child(root, b"Objects")
    conns = child(root, b"Connections")
    models = {}
    for e in objects.elems:
        if e.id == b"Model":
            uid = e.props[0]
            name = e.props[1].split(b"\x00")[0].decode()
            props = {}
            p70 = child(e, b"Properties70")
            if p70:
                for p in p70.elems:
                    key = p.props[0].decode()
                    props[key] = p.props[4:]
            models[uid] = (name, props)
    parent = {}
    for c in conns.elems:
        if c.props[0] == b"OO" and c.props[1] in models and (c.props[2] in models or c.props[2] == 0):
            parent[c.props[1]] = c.props[2]
    def lcl(uid):
        name, pr = models[uid]
        t = pr.get("Lcl Translation", (0, 0, 0))
        r = pr.get("Lcl Rotation", (0, 0, 0))
        s = pr.get("Lcl Scaling", (1, 1, 1))
        pre = pr.get("PreRotation", (0, 0, 0))
        post = pr.get("PostRotation", (0, 0, 0))
        R = Euler([math.radians(x) for x in r], "XYZ").to_matrix().to_4x4()
        Rpre = Euler([math.radians(x) for x in pre], "XYZ").to_matrix().to_4x4()
        Rpost = Euler([math.radians(x) for x in post], "XYZ").to_matrix().to_4x4()
        return Matrix.Translation(Vector(t)) @ Rpre @ R @ Rpost.inverted() @ Matrix.Diagonal((*s, 1.0))
    glob = {}
    def G(uid):
        if uid in glob:
            return glob[uid]
        m = lcl(uid)
        p = parent.get(uid)
        if p in models:
            m = G(p) @ m
        glob[uid] = m
        return m
    out = {}
    for uid, (name, pr) in models.items():
        out[name] = {"global": [x for row in G(uid) for x in row], "lcl_t": list(pr.get("Lcl Translation", (0, 0, 0))),
                     "lcl_r": list(pr.get("Lcl Rotation", (0, 0, 0))), "lcl_s": list(pr.get("Lcl Scaling", (1, 1, 1))),
                     "pre": list(pr.get("PreRotation", (0, 0, 0))), "parent": models[parent[uid]][0] if parent.get(uid) in models else None}
    # BindPose
    for e in objects.elems:
        if e.id == b"Pose":
            for pn in e.elems:
                if pn.id == b"PoseNode":
                    node = child(pn, b"Node").props[0]
                    mat = child(pn, b"Matrix").props[0]
                    if node in models:
                        nm = models[node][0]
                        M = Matrix([list(mat[i * 4:(i + 1) * 4]) for i in range(4)]).transposed()  # FBX stores column-major
                        out[nm]["bindpose"] = [x for row in M for x in row]
    gs = child(root, b"GlobalSettings")
    settings = {}
    p70 = child(gs, b"Properties70") if gs else None
    if p70:
        for p in p70.elems:
            settings[p.props[0].decode()] = p.props[4:] if len(p.props) > 4 else None
    return out, settings


def main():
    cid = C.args()[0]
    H = C.HEROES[cid]
    cname = H["name"]
    rig = bpy.data.objects[cname]
    body = bpy.data.objects[cname + ".body"]
    keep_kw = ("high-poly", "eyebrow", "eyelash", "teeth", "tongue")
    for o in list(bpy.data.objects):
        if o.type == "MESH" and o is not body and not any(k in o.name for k in keep_kw):
            bpy.data.objects.remove(o, do_unlink=True)
    for o in list(bpy.data.objects):
        if o.type not in ("MESH", "ARMATURE"):
            bpy.data.objects.remove(o, do_unlink=True)
    # rest pose everywhere
    for pb in rig.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    existing = set(bpy.data.objects)
    fbx = os.path.join(C.UNITY_CHARS, cname, cname + ".fbx")
    bpy.ops.import_scene.fbx(filepath=fbx, use_custom_normals=True, ignore_leaf_bones=False, automatic_bone_orientation=False)
    new = [o for o in bpy.data.objects if o not in existing]
    urig = next(o for o in new if o.type == "ARMATURE")
    print("IMPORTED rig", urig.name, tuple(urig.matrix_world.to_euler()), tuple(urig.matrix_world.to_scale()))
    # bone comparison (world space)
    dmax = 0
    for b in urig.data.bones:
        bb = rig.data.bones.get(b.name)
        if bb:
            d = ((urig.matrix_world @ b.head_local) - (rig.matrix_world @ bb.head_local)).length
            dmax = max(dmax, d)
    print("BONE head max diff (m)", round(dmax, 6))
    for o in new:
        if o.type != "MESH":
            continue
        n = o.name.split(".")[0]
        if n.startswith(("Hair_", "Facial_")):
            bpy.data.objects.remove(o, do_unlink=True)
            continue
        mw = o.matrix_world.copy()
        o.parent = None
        o.data.transform(mw, shape_keys=True)
        o.matrix_world = Matrix.Identity(4)
        o.name = "U_" + n
        o.data.name = o.name
        o.parent = rig
        o.matrix_parent_inverse = rig.matrix_world.inverted()
        for m in o.modifiers:
            if m.type == "ARMATURE":
                m.object = rig
    bpy.data.objects.remove(urig, do_unlink=True)
    ub = bpy.data.objects["U_Body"]
    # exposed mask on the full body
    co = C.get_co(body)
    kd = KDTree(len(co))
    for i, p in enumerate(co):
        kd.insert(p, i)
    kd.balance()
    uco = C.get_co(ub)
    exposed = np.zeros(len(co), np.float32)
    far = 0
    for p in uco:
        _, i, d = kd.find(p)
        if d < 2e-4:
            exposed[i] = 1
        else:
            far += 1
    at = body.data.attributes.get("exposed") or body.data.attributes.new("exposed", "FLOAT", "POINT")
    at.data.foreach_set("value", exposed)
    print("EXPOSED", int(exposed.sum()), "of", len(co), "unmatched U_Body verts", far)
    bones, settings = fbx_bones(fbx)
    # unit scale: compare a bone's FBX global translation with the Blender rest head converted by C_B2F
    hb = rig.data.bones["mixamorig:Head"]
    p = C.C_B2F @ (rig.matrix_world @ hb.head_local)
    g = bones["mixamorig:Head"]["global"]
    t = Vector((g[3], g[7], g[11]))
    scale = t.length / p.length
    print("HEAD fbx t", tuple(round(x, 4) for x in t), "blender->fbx", tuple(round(x, 4) for x in p), "scale", scale)
    print("SETTINGS", {k: v for k, v in settings.items() if k in ("UpAxis", "UpAxisSign", "FrontAxis", "FrontAxisSign", "CoordAxis", "CoordAxisSign", "UnitScaleFactor", "OriginalUnitScaleFactor")})
    for nm in ("mixamorig:Hips", "mixamorig:Head", "mixamorig:Neck"):
        b = bones[nm]
        print(nm, "lcl_t", [round(x, 4) for x in b["lcl_t"]], "lcl_r", [round(x, 3) for x in b["lcl_r"]], "pre", b["pre"], "parent", b["parent"])
        print("   global", [round(x, 4) for x in b["global"]])
        if "bindpose" in b:
            print("   bind  ", [round(x, 4) for x in b["bindpose"]])
    roots = [n for n, b in bones.items() if b["parent"] is None]
    print("ROOT MODELS", roots[:10])
    info = {"cid": cid, "fbx": fbx, "unit_scale": scale, "bones": {n: b for n, b in bones.items() if n.startswith("mixamorig:") or b["parent"] is None},
            "bone_diff": dmax, "settings": {k: list(v) if isinstance(v, tuple) else v for k, v in settings.items() if k.endswith(("Axis", "AxisSign", "UnitScaleFactor"))}}
    with open(os.path.join(C.CACHE, f"{cid}_ref.json"), "w") as f:
        json.dump(info, f, indent=0, default=float)
    bpy.ops.wm.save_as_mainfile(filepath=C.ref_path(cid), compress=True)
    print("SAVED", C.ref_path(cid), [o.name for o in bpy.data.objects])


if __name__ == "__main__":
    main()
