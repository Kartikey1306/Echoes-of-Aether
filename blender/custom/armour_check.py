"""Pose test for armour sets: drive the hero rig with frames of the game's own animation clips (Anim_Male/Female.fbx),
measure body poke-through and render posed previews.

  blender -b --python blender/custom/armour_check.py -- <cid> <set> [--render]

Only body vertices that exist in the exported Unity Body (attribute 'exposed') can poke through in game; for those
under the suit we test the posed body against the posed suit shell (signed distance along the suit normal)."""
import bpy, os, sys, math, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
import common as C
import studio

POSES = [("run", 0.25), ("run", 0.6), ("k_heavy", 0.45), ("k_light2", 0.5), ("climb", 0.5), ("kneel_work", 0.5), ("sit", 0.6),
         ("aim_l", 0.5), ("dash", 0.4), ("death", 0.9), ("pickup", 0.5), ("jump", 0.4)]


def import_anim(cid):
    gender = "Male" if cid == "kael" else "Female"
    path = os.path.join(C.UNITY_ASSETS, "Art", "Animations", f"Anim_{gender}.fbx")
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=path, ignore_leaf_bones=True, automatic_bone_orientation=False)
    new = [o for o in bpy.data.objects if o not in before]
    arm = next(o for o in new if o.type == "ARMATURE")
    for o in new:
        if o is not arm:
            bpy.data.objects.remove(o, do_unlink=True)
    return arm


def apply_pose(src, dst, action, t):
    src.animation_data.action = action
    f0, f1 = action.frame_range
    bpy.context.scene.frame_set(int(round(f0 + (f1 - f0) * t)))
    bpy.context.view_layer.update()
    rest_s = {b.name: src.matrix_world @ b.matrix_local for b in src.data.bones}
    pose_s = {pb.name: src.matrix_world @ pb.matrix for pb in src.pose.bones}
    order = []
    def walk(b):
        order.append(b.name)
        for c in b.children:
            walk(c)
    for b in dst.data.bones:
        if b.parent is None:
            walk(b)
    for pb in dst.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()
    root = None
    for name in order:
        if name not in pose_s:
            continue
        pb = dst.pose.bones[name]
        rs = rest_s[name].to_3x3(); ps = pose_s[name].to_3x3()
        delta = ps @ rs.inverted()
        rest_d = dst.matrix_world @ dst.data.bones[name].matrix_local
        rot = (delta @ rest_d.to_3x3()).normalized()
        if root is None:
            root = name
            loc = rest_d.to_translation() + (pose_s[name].to_translation() - rest_s[name].to_translation())
        else:
            loc = (dst.matrix_world @ pb.matrix).to_translation() if False else None
        if loc is None:
            par = pb.parent
            par_m = dst.matrix_world @ par.matrix
            rel = (dst.matrix_world @ par.bone.matrix_local).inverted() @ rest_d
            loc = (par_m @ rel).to_translation()
        M = Matrix.Translation(loc) @ rot.to_4x4()
        pb.matrix = dst.matrix_world.inverted() @ M
        bpy.context.view_layer.update()


def evaluated_co(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    co = np.array([obj.matrix_world @ v.co for v in me.vertices])
    polys = [list(p.vertices) for p in me.polygons]
    mats = [p.material_index for p in me.polygons]
    ev.to_mesh_clear()
    return co, polys, mats


def main():
    a = C.args()
    cid, sid = a[0], a[1]
    bpy.ops.wm.open_mainfile(filepath=os.path.join(C.CACHE, f"armour_{cid}_{sid}.blend"))
    rig = bpy.data.objects[C.HEROES[cid]["name"]]
    body = bpy.data.objects[C.HEROES[cid]["name"] + ".body"]
    arm_obj = bpy.data.objects[f"{cid}_{sid}"]
    for o in (body, arm_obj):
        o.hide_viewport = False
        o.hide_set(False)
    exposed = np.array([d.value for d in body.data.attributes["exposed"].data]) > 0.5
    src = import_anim(cid)
    actions = {ac.name.split("|")[-1]: ac for ac in bpy.data.actions}
    results = []
    me = arm_obj.data
    suit_slot = [m.name for m in me.materials].index("SuitSecondary") if "SuitSecondary" in [m.name for m in me.materials] else 1
    worst = []
    # the under-suit shell = SuitSecondary faces carrying body coordinates (bx, by, bz); gaskets, cables, straps excluded
    bxa = arm_obj.data.attributes.get("bx")
    if bxa is not None:
        bb = np.empty(len(arm_obj.data.vertices)); bxa.data.foreach_get("value", bb)
        byv = np.empty(len(arm_obj.data.vertices)); arm_obj.data.attributes["bz"].data.foreach_get("value", byv)
        shellv = (np.abs(bb) + np.abs(byv)) > 1e-6
    else:
        shellv = np.ones(len(arm_obj.data.vertices), bool)
    def suit_faces(polys, mats):
        return [p for p, m in zip(polys, mats) if m == suit_slot and all(shellv[v] for v in p)]
    # rest pose: which exposed body vertices are actually covered by the suit (inside it, within 2 cm)?
    bco0, _, _ = evaluated_co(body)
    aco0, ap0, am0 = evaluated_co(arm_obj)
    tree0 = BVHTree.FromPolygons([Vector(v) for v in aco0], suit_faces(ap0, am0))
    covered = []
    for i in np.where(exposed)[0]:
        hit, n, fi, d = tree0.find_nearest(Vector(bco0[i]), 0.02)
        if hit is not None and (Vector(bco0[i]) - hit).dot(n) < 0:
            covered.append(i)
    covered = np.array(covered, int)
    print("covered exposed verts", len(covered), "of", int(exposed.sum()))
    for clip, t in POSES:
        ac = next((v for k, v in actions.items() if k == clip or k.endswith(clip)), None)
        if ac is None:
            continue
        apply_pose(src, rig, ac, t)
        bco, _, _ = evaluated_co(body)
        aco, apolys, amats = evaluated_co(arm_obj)
        suit_f = suit_faces(apolys, amats)
        tree = BVHTree.FromPolygons([Vector(v) for v in aco], suit_f)
        idx = covered
        pokes = []
        for i in idx:
            hit, n, fi, d = tree.find_nearest(Vector(bco[i]), 0.03)
            if hit is None:
                continue
            g = (Vector(bco[i]) - hit).dot(n)
            if g > 0.0005:
                pokes.append((i, g))
        mx = max([g for _, g in pokes], default=0.0)
        if pokes:
            names = {g.index: g.name for g in body.vertex_groups}
            reg = {}
            for i, g in pokes:
                gs = [x for x in body.data.vertices[i].groups if names[x.group].startswith("mixamorig:")]
                if gs:
                    bn = names[max(gs, key=lambda x: x.weight).group][10:]
                    reg[bn] = reg.get(bn, 0) + 1
            print("   poke regions", sorted(reg.items(), key=lambda x: -x[1])[:6])
        results.append({"clip": clip, "t": t, "body_verts_poking": len(pokes), "max_mm": round(mx * 1000, 2)})
        print("POSE", clip, t, "poking verts", len(pokes), "max mm", round(mx * 1000, 2))
        worst.append((len(pokes), clip, t))
    with open(os.path.join(C.CACHE, f"posecheck_{cid}_{sid}.json"), "w") as f:
        json.dump(results, f, indent=1)
    if "--render" in a:
        studio.world_and_lights(Vector((0, 0, 1.0)), 2.2, rim=1.0, yaw=30)
        for k, (clip, t) in enumerate([("k_heavy", 0.45), ("run", 0.25), ("climb", 0.5)]):
            ac = next((v for kk, v in actions.items() if kk == clip or kk.endswith(clip)), None)
            if ac is None:
                continue
            apply_pose(src, rig, ac, t)
            hips = rig.matrix_world @ rig.pose.bones["mixamorig:Hips"].head
            aim = Vector((hips.x, hips.y, hips.z + 0.2))
            studio.world_and_lights(aim, 2.2, rim=1.0, yaw=35)
            studio.camera(studio.view(aim, 35, 6, 4.2), aim, 50)
            studio.render(os.path.join(C.PREVIEWS, "armour", f"{cid}_{sid}_pose_{clip}.png"), 640)
    print("POSECHECK", json.dumps(results))


if __name__ == "__main__":
    main()
