"""roboscene -- turns a robokit.Robot into Blender objects (contract hierarchy), materials, UVs and an FBX."""
import math
import os

import bmesh
import bpy
from mathutils import Vector

import robokit as K

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.abspath(os.path.join(HERE, "..", ".."))
UNITY_ROBOTS = os.path.join(GAME, "unity", "EchoesOfAether", "Assets", "Resources", "Models", "Robots")
TEX_DIR = os.path.join(UNITY_ROBOTS, "Textures")
OUT_DIR = os.path.join(HERE, "out")
PREVIEW_DIR = os.path.join(HERE, "previews")

# Code palettes from ROBOT_PARTS.md / RobotRig (shell, frame, glow, glow intensity); bolt from Npc.ts.
PALETTES = {
    "sentinel": (0x4A4F56, 0x24272C, 0xFF5A3A, 3.0),
    "warden": (0x3A2E30, 0x1F1C1E, 0xFF3B30, 3.4),
    "stalker": (0x2A2436, 0x141218, 0xB48CFF, 3.2),
    "guardian": (0x3A3F48, 0x1C1F24, 0x5FD8FF, 3.6),
    "guardian_vault": (0x3A3F48, 0x1C1F24, 0xFF5A3A, 3.6),
    "drone": (0x2B3036, 0x5A6068, 0x5FD8FF, 3.0),
    "bolt": (0x9A7A2A, 0x2A2A2E, 0xFFC24A, 2.2),
}
# (metallic, smoothness) like RobotRig.MakeMaterials (drone: RobotBodies.BuildDrone overrides)
SURF = {"shell": (0.65, 0.58), "frame": (0.75, 0.45), "joint": (0.6, 0.4)}
SURF_DRONE = {"shell": (0.8, 0.65), "frame": (0.85, 0.6), "joint": (0.6, 0.4)}
JOINT_COL = 0x15171A
ROTOR_COL = 0x202428


def srgb_to_lin(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_lin(h):
    return (srgb_to_lin((h >> 16) & 255), srgb_to_lin((h >> 8) & 255), srgb_to_lin(h & 255))


# ============================================================================ scene
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 1.0


def export_materials(kind):
    """Plain Principled materials (no textures, so Unity keeps the material names that RobotRig matches)."""
    shell, frame, glow, gi = PALETTES[kind]
    surf = SURF_DRONE if kind == "drone" else SURF
    mats = []
    for i, name in enumerate(K.MAT_NAMES):
        m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        m.use_nodes = True
        b = m.node_tree.nodes.get("Principled BSDF")
        if i == K.SHELL:
            col, (met, sm) = shell, surf["shell"]
        elif i == K.FRAME:
            col, (met, sm) = frame, surf["frame"]
        elif i == K.JOINT:
            col, (met, sm) = JOINT_COL, surf["joint"]
        elif i == K.GLOW:
            col, met, sm = glow, 0.0, 0.5
        else:
            col, met, sm = ROTOR_COL, 0.2, 0.5
        b.inputs["Base Color"].default_value = (*hex_lin(col), 1.0)
        b.inputs["Metallic"].default_value = met
        b.inputs["Roughness"].default_value = 1.0 - sm
        if i == K.GLOW:
            b.inputs["Emission Color"].default_value = (*hex_lin(glow), 1.0)
            b.inputs["Emission Strength"].default_value = gi
        if i == K.ROTOR:
            b.inputs["Alpha"].default_value = 0.55
            m.surface_render_method = "BLENDED"
        m.diffuse_color = (*hex_lin(col), 1.0)
        mats.append(m)
    return mats


def _mesh_object(name, part, pivot_m, s, mats):
    me = bpy.data.meshes.new(name + "_mesh")
    verts = [v * s - pivot_m for v in part.v]   # robot space == FBX space (see build_objects)
    used = sorted(set(part.m))
    remap = {m: i for i, m in enumerate(used)}
    me.from_pydata(verts, [], part.f)
    me.validate(clean_customdata=False)
    for p, m in zip(me.polygons, part.m):
        p.material_index = remap[m]
    for m in used:
        me.materials.append(mats[m])
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    ng = [f for f in bm.faces if len(f.verts) > 4]
    if ng:
        bmesh.ops.triangulate(bm, faces=ng, quad_method="BEAUTY", ngon_method="BEAUTY")
    bm.to_mesh(me)
    bm.free()
    me.shade_smooth()
    me.set_sharp_from_angle(angle=math.radians(48.0))
    ob = bpy.data.objects.new(name, me)
    wn = ob.modifiers.new("WeightedNormal", "WEIGHTED_NORMAL")
    wn.mode = "FACE_AREA"
    wn.weight = 50
    wn.keep_sharp = True
    return ob


def _make(name, part, pivot_m, s, mats):
    if part is None or not part.f:
        ob = bpy.data.objects.new(name, None)
        ob.empty_display_size = 0.06 * max(1.0, s)
        ob.empty_display_type = "PLAIN_AXES"
    else:
        ob = _mesh_object(name, part, pivot_m, s, mats)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def build_objects(robot, kind):
    """Create the contract hierarchy. Returns {name: object}.

    Axis handling: the FBX exporter maps Blender -> FBX with G = axis_conversion(-Z forward, Y up), i.e.
    (bx, by, bz) -> (bx, bz, -by), and applies G only to root nodes. Robot space (x = robot's left, y = up,
    z = forward) *is* that FBX space, so every node below a root is authored directly in robot space (identity
    rotations, robot-space offsets, robot-space vertices) and each root node gets the rotation G^-1 (+90 deg about
    X). The exporter then writes G @ G^-1 = identity on the roots and the untouched robot-space data below, which
    Unity reads as (-x, y, z): identity local rotations everywhere, robot facing +Z, robot's left at -X.
    (bake_space_transform is not used: Blender 5.2 mis-converts nodes deeper than one level with it.)"""
    mats = export_materials(kind)
    s = robot.s
    objs, piv = {}, {}
    decl = []
    if robot.skeleton:
        for i, b in enumerate(K.BONES):
            p = K.PARENT[i]
            decl.append((b, K.BONES[p] if p >= 0 else None, robot.J[b] * s))
    for name, (parent, pivot) in robot.extra.items():
        decl.append((name, parent, pivot * s))

    def link(ob, parent, pivot_m):
        if parent is not None:
            ob.parent = objs[parent]
            ob.matrix_parent_inverse.identity()
            ob.location = pivot_m - piv[parent]
        else:
            ob.rotation_euler = (math.pi / 2, 0.0, 0.0)
            ob.location = K.r2b(pivot_m)

    for name, parent, pivot_m in decl:
        ob = _make(name, robot.parts.get(name), pivot_m, s, mats)
        link(ob, parent, pivot_m)
        objs[name], piv[name] = ob, pivot_m
    leftovers = [n for n in robot.parts if n not in objs]
    if leftovers:
        raise RuntimeError("geometry added to undeclared objects: %s" % leftovers)
    # Second root node so Unity creates an explicit prefab root and keeps the 'root' / 'body' names.
    meta = bpy.data.objects.new("meta_" + kind, None)
    meta.empty_display_size = 0.01
    bpy.context.scene.collection.objects.link(meta)
    link(meta, None, Vector((0, 0, 0)))
    objs[meta.name] = meta
    bpy.context.view_layer.update()
    return objs


def uv_unwrap(objs, texel_m=1.0):
    """Smart-project all meshes together (one shared island layout), then scale so 1 UV unit = texel_m metres."""
    meshes = [o for o in objs.values() if o.type == "MESH"]
    if not meshes:
        return
    for o in bpy.context.scene.objects:
        o.select_set(False)
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(60.0), island_margin=0.002, area_weight=0.0,
                             correct_aspect=True, scale_to_bounds=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    a3, auv = 0.0, 0.0
    for o in meshes:
        me = o.data
        uv = me.uv_layers.active.data
        for p in me.polygons:
            a3 += p.area
            pts = [uv[li].uv for li in p.loop_indices]
            ar = 0.0
            for k in range(1, len(pts) - 1):
                e1, e2 = pts[k] - pts[0], pts[k + 1] - pts[0]
                ar += abs(e1.x * e2.y - e1.y * e2.x) * 0.5
            auv += ar
    k = math.sqrt(a3 / max(auv, 1e-9)) / texel_m
    for o in meshes:
        for d in o.data.uv_layers.active.data:
            d.uv = d.uv * k
    for o in meshes:
        o.select_set(False)


def export_fbx(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.export_scene.fbx(
        filepath=path, use_selection=False, object_types={"EMPTY", "MESH"},
        axis_forward="-Z", axis_up="Y", apply_unit_scale=True, apply_scale_options="FBX_SCALE_ALL", global_scale=1.0,
        bake_space_transform=False, use_mesh_modifiers=True, mesh_smooth_type="OFF", use_triangles=True,
        use_tspace=False, add_leaf_bones=False, bake_anim=False, path_mode="STRIP", embed_textures=False,
        use_custom_props=False, colors_type="NONE", use_mesh_edges=False)


def stats(objs):
    """Triangle counts (after modifiers) per object and per material."""
    dg = bpy.context.evaluated_depsgraph_get()
    per_obj, per_mat, total = {}, {}, 0
    for name, o in objs.items():
        if o.type != "MESH":
            continue
        me = o.evaluated_get(dg).to_mesh()
        n = 0
        for p in me.polygons:
            t = len(p.vertices) - 2
            n += t
            mn = o.data.materials[p.material_index].name if o.data.materials else "?"
            per_mat[mn] = per_mat.get(mn, 0) + t
        o.evaluated_get(dg).to_mesh_clear()
        per_obj[name] = n
        total += n
    return {"total": total, "objects": per_obj, "materials": per_mat}
