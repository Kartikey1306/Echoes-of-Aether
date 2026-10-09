"""UV unwrapping and atlas packing for the Giva meshes (works in background mode)."""
import bpy, bmesh, math
import numpy as np
import gv


def _edit(objs):
    bpy.ops.object.mode_set(mode="OBJECT") if bpy.context.object and bpy.context.object.mode != "OBJECT" else None
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.mode_set(mode="EDIT")


def select_faces(o, pred):
    bm = bmesh.from_edit_mesh(o.data)
    bm.faces.ensure_lookup_table()
    for f in bm.faces:
        f.select = bool(pred(f))
    bmesh.update_edit_mesh(o.data)


def mark_seams(o, seam_pred):
    """seam_pred(face_a_index, face_b_index) -> True for a seam between two faces (edit mode)."""
    bm = bmesh.from_edit_mesh(o.data)
    for e in bm.edges:
        lf = e.link_faces
        e.seam = len(lf) == 2 and bool(seam_pred(lf[0].index, lf[1].index))
    bmesh.update_edit_mesh(o.data)


def unwrap_atlas(groups, method="SMART", margin=0.004, angle=66.0, seams=None):
    """groups: [(obj, face predicate)]. Unwraps the selected faces of every object and packs all of their islands
    together into 0..1 (uniform texel density)."""
    objs = [g[0] for g in groups]
    _edit(objs)
    for o, pred in groups:
        select_faces(o, pred)
        if seams and o.name in seams:
            mark_seams(o, seams[o.name])
    bpy.ops.mesh.select_mode(type="FACE")
    bpy.context.scene.tool_settings.use_uv_select_sync = False
    if method == "SMART":
        bpy.ops.uv.smart_project(angle_limit=math.radians(angle), island_margin=0.0, area_weight=0.0,
                                 correct_aspect=True, scale_to_bounds=False)
    else:
        bpy.ops.uv.unwrap(method=method, margin=0.001, fill_holes=True, correct_aspect=True)
    # uv selection = face selection for packing (Blender 5 UV selection API)
    for o in objs:
        bm = bmesh.from_edit_mesh(o.data)
        try:
            bm.uv_select_sync_from_mesh()
        except Exception:
            for f in bm.faces:
                f.uv_select_set(f.select)
        bmesh.update_edit_mesh(o.data)
    try:
        bpy.ops.uv.average_islands_scale()
    except Exception as e:
        gv.log("average_islands_scale failed", e)
    bpy.ops.uv.pack_islands(udim_source="CLOSEST_UDIM", rotate=True, margin_method="SCALED", margin=margin, shape_method="CONCAVE")
    bpy.ops.object.mode_set(mode="OBJECT")


def mat_pred(o, names):
    idx = {i for i, m in enumerate(o.data.materials) if m and m.name in names}
    return lambda f: f.material_index in idx


def uv_coverage(o, names=None):
    me = o.data
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    return uv.min(0), uv.max(0)
