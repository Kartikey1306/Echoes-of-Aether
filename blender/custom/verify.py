"""Re-import every customisation FBX listed in catalog.json and check it: mesh present, material slot names,
armature bone names identical to the hero FBX (skinned), vertex groups only on existing bones, blend shapes on armour,
rigid items in the expected place when transformed back to the head bone (eyewear in front of the eyes, hair around
the head), textures and thumbnails present.

  blender -b --python blender/custom/verify.py   ->  cache/verify_report.json
"""
import bpy, os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from mathutils import Matrix
import common as C

EXPECT = {"hair": ["Hair"], "eyewear": ["EyewearFrame", "EyewearLens", "Glow"], "armour": ["Armor", "SuitSecondary", "Glow", "Glow2", "Screen"]}


def clear():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for m in list(bpy.data.meshes):
        bpy.data.meshes.remove(m)
    for a in list(bpy.data.armatures):
        bpy.data.armatures.remove(a)


def hero_bones(cid):
    info = C.head_info(cid)
    return {n for n in info["bones"] if n.startswith("mixamorig:")}


def main():
    cat = json.load(open(os.path.join(C.CUSTOM_OUT, "catalog.json")))
    report = {"ok": 0, "fail": 0, "items": []}
    heads = {}
    for cid in ("kael", "lyra"):
        info = C.head_info(cid)
        b = info["bones"]["mixamorig:Head"]["bindpose"]
        H = Matrix([b[i * 4:(i + 1) * 4] for i in range(4)])
        heads[cid] = H
    for cat_name in ("hair", "eyewear", "armour", "tattoos"):
        for e in cat.get(cat_name, []):
            cid = e["hero"]
            res = {"cat": cat_name, "hero": cid, "id": e["id"], "errors": [], "warn": []}
            thumb = os.path.join(C.CUSTOM_OUT, e["thumb"] + ".png")
            if not os.path.exists(thumb):
                res["errors"].append("thumb missing")
            if cat_name == "tattoos":
                for k in ("ink", "glow"):
                    if not os.path.exists(os.path.join(C.CUSTOM_OUT, e[k] + ".png")):
                        res["errors"].append(k + " texture missing")
            else:
                path = os.path.join(C.CUSTOM_OUT, e["file"] + ".fbx")
                if not os.path.exists(path):
                    res["errors"].append("fbx missing")
                else:
                    clear()
                    bpy.ops.import_scene.fbx(filepath=path, ignore_leaf_bones=False)
                    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
                    arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
                    if len(meshes) != 1:
                        res["errors"].append(f"{len(meshes)} meshes")
                    if meshes:
                        o = meshes[0]
                        mats = [m.name.split(".")[0] for m in o.data.materials]
                        res["materials"] = mats
                        want = EXPECT[cat_name]
                        if cat_name == "eyewear":
                            if mats[:2] != want[:2] or any(m not in want for m in mats):
                                res["errors"].append(f"materials {mats}")
                        elif mats != want:
                            res["errors"].append(f"materials {mats} != {want}")
                        res["tris"] = sum(len(p.vertices) - 2 for p in o.data.polygons)
                        sk = [k.name for k in o.data.shape_keys.key_blocks[1:]] if o.data.shape_keys else []
                        res["shapes"] = len(sk)
                        if e.get("kind") == "skinned":
                            if len(arms) != 1:
                                res["errors"].append("no armature")
                            else:
                                bones = {b.name for b in arms[0].data.bones}
                                hb = hero_bones(cid)
                                if bones != hb:
                                    res["errors"].append(f"bone set differs: +{sorted(bones - hb)[:5]} -{sorted(hb - bones)[:5]}")
                                vg = {g.name for g in o.vertex_groups}
                                if not vg <= bones:
                                    res["errors"].append(f"groups not bones {sorted(vg - bones)[:5]}")
                                # all verts weighted
                                unw = sum(1 for v in o.data.vertices if not v.groups)
                                if unw:
                                    res["errors"].append(f"{unw} unweighted verts")
                            if cat_name == "armour":
                                need = [s for s in e.get("blendShapes", []) if s.startswith("m_")]
                                miss = [s for s in need if s not in sk]
                                if miss or not need:
                                    res["errors"].append(f"blend shapes missing {miss[:4]}")
                        else:
                            if arms:
                                res["errors"].append("rigid item has an armature")
                            # place under the head bone (Blender import space == original Blender space) and test
                            co = np.array([o.matrix_world @ v.co for v in o.data.vertices])
                            M = C.rigid_matrix(cid).inverted()
                            W = np.array([M @ __import__("mathutils").Vector(p) for p in co])
                            info = C.head_info(cid)
                            ctr = W.mean(0)
                            res["world_center"] = [round(float(x), 4) for x in ctr]
                            if cat_name == "eyewear":
                                # must be in front of the face at eye height
                                eye_z = {"kael": 1.7306, "lyra": 1.615}[cid]
                                if abs(W[:, 2].mean() - eye_z) > 0.05 or W[:, 1].min() > -0.13:
                                    res["errors"].append(f"eyewear misplaced {res['world_center']}")
                            if cat_name == "hair":
                                if W[:, 2].max() < {"kael": 1.85, "lyra": 1.73}[cid] - 0.01:
                                    res["errors"].append("hair below the head top")
                        for k in ("baseMap",):
                            if k in e and not os.path.exists(os.path.join(C.CUSTOM_OUT, e[k] + ".png")):
                                res["errors"].append("baseMap missing")
                        for sl, md in (e.get("materials") or {}).items():
                            for k in ("baseMap", "normal", "maskMap"):
                                if isinstance(md, dict) and md.get(k) and not os.path.exists(os.path.join(C.CUSTOM_OUT, md[k] + ".png")):
                                    res["errors"].append(f"{sl}.{k} missing")
            report["items"].append(res)
            if res["errors"]:
                report["fail"] += 1
                print("FAIL", cat_name, cid, e["id"], res["errors"])
            else:
                report["ok"] += 1
                print("OK  ", cat_name, cid, e["id"], res.get("materials"), res.get("tris"), res.get("shapes"))
    with open(os.path.join(C.CACHE, "verify_report.json"), "w") as f:
        json.dump(report, f, indent=1)
    print("VERIFY", report["ok"], "ok", report["fail"], "fail")


main()
