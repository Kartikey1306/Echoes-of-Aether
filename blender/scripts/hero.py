"""Build a game-ready hero: MPFB human + customisation/expression blendshapes on every mesh + outfit,
then export FBX for Unity.

blender -b --python hero.py -- <kael|lyra> [--render-morphs] [--export] [--blend file]
"""
import bpy, sys, os, math, importlib
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
import characters, meshutil, morphs, build_human, outfit, outfits_def, export_hero
for m in (characters, meshutil, morphs, build_human, outfit, outfits_def, export_hero):
    importlib.reload(m)
from meshutil import SurfaceBinding, add_shape_key, bake_shape_keys, get_co, set_co

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "out")
UNITY = os.path.abspath(os.path.join(ROOT, "..", "unity", "EchoesOfAether", "Assets", "Art", "Characters"))


def rig_of(body):
    return body.parent if body.parent and body.parent.type == "ARMATURE" else None


def attachments(body):
    rig = rig_of(body)
    return [o for o in bpy.data.objects if o.type == "MESH" and o is not body and (o.parent is rig or o.parent is body)]


def assemble(cid):
    c = characters.CHARACTERS[cid]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    body = build_human.build(cid)
    female = c["phenotype"]["gender"] < 0.5
    base, deltas = morphs.capture(body, female, custom=not c.get("npc"))
    # Bake the phenotype into the mesh; morphs become plain shape keys relative to it.
    bake_shape_keys(body)
    set_co(body, base)
    # Bind attachments (hair, brows, lashes, eyes, teeth, tongue) to the full body incl. helper geometry.
    for o in attachments(body):
        if o.data.shape_keys:
            bake_shape_keys(o)
        pts = get_co(o)
        bind = SurfaceBinding(body, base, pts, max_dist=0.2)
        is_eye = "high-poly" in o.name or "low-poly" in o.name
        for name, d in deltas.items():
            if is_eye and name.startswith("x_"):
                continue  # eyeballs don't move with lid/mouth expressions
            dd = bind.transfer(d)
            if np.abs(dd).max() > 1e-5:
                add_shape_key(o, name, pts + dd)
        print("ATTACH", o.name, len(pts), "shapes", len(o.data.shape_keys.key_blocks) - 1 if o.data.shape_keys else 0)
    for name, d in deltas.items():
        add_shape_key(body, name, base + d)
    # Drop helper geometry (now that bindings are done) and the masking modifiers. Body regions hidden by
    # clothing (MPFB "delete" groups, e.g. feet inside boots) are removed for real so they never poke through.
    del_groups = [m.vertex_group for m in body.modifiers if m.type == "MASK" and m.invert_vertex_group and m.vertex_group and m.vertex_group != "body"]
    print("DELETE GROUPS", del_groups)
    meshutil.delete_verts_in_groups(body, del_groups)
    meshutil.delete_verts_not_in_group(body, "body")
    for m in list(body.modifiers):
        if m.type == "MASK":
            body.modifiers.remove(m)
    meshutil.remove_groups(body, lambda n: n.startswith(("joint-", "helper-")) or n in ("HelperGeometry", "JointCubes"))
    print("BODY verts", len(body.data.vertices), "shapes", len(body.data.shape_keys.key_blocks) - 1)
    return body


def set_shape(objs, name, value):
    for o in objs:
        if o.data.shape_keys and name in o.data.shape_keys.key_blocks:
            o.data.shape_keys.key_blocks[name].value = value


def render_morphs(cid, body):
    objs = [body] + attachments(body)
    rig = rig_of(body)
    hb = rig.data.bones["mixamorig:Head"]
    face_z = (rig.matrix_world @ hb.head_local).z + 0.08
    tests = [("base", {}), ("jaw+", {"m_jaw_incr": 1}), ("nose+", {"m_noseSize_incr": 1, "m_noseWidth_incr": 1}),
             ("eyes+lips+", {"m_eyeSize_incr": 1, "m_lips_incr": 1}), ("blink", {"x_blink_L": 1, "x_blink_R": 1}),
             ("smile_open", {"x_smile": 1, "x_mouthOpen": 0.6, "x_browsUp": 0.7})]
    for tag, vals in tests:
        for o in objs:
            if o.data.shape_keys:
                for k in o.data.shape_keys.key_blocks[1:]:
                    k.value = 0
        for n, v in vals.items():
            set_shape(objs, n, v)
        build_human.setup_render(body, f"{cid}_morph_{tag}", {"face": (0.95, face_z, 18, 85)})


if __name__ == "__main__":
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    cid = a[0] if a else "kael"
    body = assemble(cid)
    if "--outfit" in a and cid in outfits_def.OUTFITS:
        objs = outfits_def.OUTFITS[cid](body, rig_of(body))
        print("OUTFIT", [(o.name, len(o.data.vertices), len(o.data.polygons)) for o in objs])
    if characters.CHARACTERS[cid].get("gear"):
        objs = outfits_def.npc_gear(body, rig_of(body), characters.CHARACTERS[cid]["gear"])
        print("GEAR", [o.name for o in objs])
    if "--render-body" in a:
        rig = rig_of(body)
        top = (rig.matrix_world @ rig.data.bones["mixamorig:Head"].tail_local).z + 0.03
        build_human.setup_render(body, f"{cid}_outfit", {"front": (3.0, top * 0.55, 0, 55), "q34": (3.0, top * 0.6, 35, 55), "back": (3.0, top * 0.6, 180, 55), "face": (0.9, top - 0.1, 20, 85)})
    if "--render-morphs" in a:
        render_morphs(cid, body)
    if "--export" in a:
        c = characters.CHARACTERS[cid]
        rig = rig_of(body)
        ev = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
        height = max((body.matrix_world @ v.co).z for v in ev.data.vertices)
        gender = "female" if c["phenotype"]["gender"] < 0.5 else "male"
        extra = {"npc": bool(c.get("npc")), "echo": bool(c.get("echo")), "tints": c.get("tints", {})}
        export_hero.export(cid, c["name"], body, rig, gender, c.get("default_hair", "default"), outfits_def.SHELLS, round(height, 3), extra)
    if "--blend" in a:
        bpy.ops.wm.save_as_mainfile(filepath=a[a.index("--blend") + 1])
