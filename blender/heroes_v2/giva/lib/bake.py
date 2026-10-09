"""Cycles bakes for the Giva atlases (GPU): AO on the assembled low-poly, tangent-space normals high -> low."""
import bpy, os
import numpy as np
import gv

DUMMY = None


def _dummy():
    global DUMMY
    if DUMMY is None or DUMMY.name not in bpy.data.images:
        DUMMY = bpy.data.images.new("__bake_dummy", 8, 8, alpha=False, float_buffer=True)
    return DUMMY


def _set_active_image(mat, img):
    mat.use_nodes = True
    nt = mat.node_tree
    n = nt.nodes.get("__bake_img")
    if n is None:
        n = nt.nodes.new("ShaderNodeTexImage")
        n.name = "__bake_img"
    n.image = img
    for x in nt.nodes:
        x.select = False
    n.select = True
    nt.nodes.active = n


def _prepare(objs, target_mats, img):
    for o in objs:
        for slot in o.material_slots:
            m = slot.material
            if m is None:
                continue
            _set_active_image(m, img if m.name in target_mats else _dummy())


def _cleanup(objs):
    for o in objs:
        for slot in o.material_slots:
            m = slot.material
            if m and m.use_nodes and "__bake_img" in m.node_tree.nodes:
                m.node_tree.nodes.remove(m.node_tree.nodes["__bake_img"])


def setup(samples=64):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    gv.enable_gpu()
    sc.cycles.samples = samples
    sc.cycles.use_denoising = False
    sc.render.bake.margin = 10
    sc.render.bake.margin_type = "EXTEND"


def new_image(name, size, value=(0.0, 0.0, 0.0, 1.0)):
    img = bpy.data.images.get(name)
    if img:
        bpy.data.images.remove(img)
    img = bpy.data.images.new(name, size, size, alpha=True, float_buffer=True)
    img.colorspace_settings.name = "Non-Color"
    img.generated_color = value
    return img


def to_array(img):
    w, h = img.size
    a = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(h, w, 4)


def bake_ao(objs, target_mats, size, samples=96, distance=0.06):
    """AO of the target-material faces of objs (everything visible in the scene occludes)."""
    setup(samples)
    img = new_image("__ao", size, (1, 1, 1, 1))
    _prepare(objs, target_mats, img)
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if bpy.context.scene.world is None:
        bpy.context.scene.world = bpy.data.worlds.new("bake_world")
    bpy.context.scene.world.light_settings.distance = distance
    bpy.ops.object.bake(type="AO", use_selected_to_active=False, use_clear=True, margin=10)
    arr = to_array(img)[..., 0].copy()
    _cleanup(objs)
    bpy.data.images.remove(img)
    return arr


def bake_normal(pairs, target_mats, size, extrusion=0.004, max_ray=0.012):
    """pairs: [(low, [highs])]. Tangent-space normal of target-material faces, all lows into one atlas."""
    setup(1)
    img = new_image("__nrm", size, (0.5, 0.5, 1.0, 1.0))
    first = True
    for low, highs in pairs:
        if not highs:
            continue
        _prepare([low], target_mats, img)
        bpy.ops.object.select_all(action="DESELECT")
        for h in highs:
            h.hide_render = False
            h.hide_viewport = False
            h.select_set(True)
        low.select_set(True)
        bpy.context.view_layer.objects.active = low
        bpy.ops.object.bake(type="NORMAL", normal_space="TANGENT", use_selected_to_active=True, cage_extrusion=extrusion,
                            max_ray_distance=max_ray, use_clear=first, margin=10)
        first = False
        for h in highs:
            h.hide_render = True
        _cleanup([low])
    arr = to_array(img)[..., :3].copy()
    bpy.data.images.remove(img)
    return arr


def bake_emit_attr(objs, target_mats, size, attr):
    """Bake a float/colour attribute of the low meshes into the atlas (emission)."""
    setup(1)
    img = new_image("__attr", size, (0, 0, 0, 1))
    saved = {}
    for o in objs:
        for slot in o.material_slots:
            m = slot.material
            if m is None or m.name in saved:
                continue
            m.use_nodes = True
            nt = m.node_tree
            out = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None) or nt.nodes.new("ShaderNodeOutputMaterial")
            saved[m.name] = [(l.from_socket, l.to_socket) for l in nt.links if l.to_node == out]
            for l in list(nt.links):
                if l.to_node == out:
                    nt.links.remove(l)
            at = nt.nodes.new("ShaderNodeAttribute")
            at.name = "__ea"
            at.attribute_name = attr
            em = nt.nodes.new("ShaderNodeEmission")
            em.name = "__ee"
            nt.links.new(at.outputs["Color"], em.inputs["Color"])
            nt.links.new(em.outputs[0], out.inputs[0])
    _prepare(objs, target_mats, img)
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.bake(type="EMIT", use_clear=True, margin=4)
    arr = to_array(img)[..., :3].copy()
    for o in objs:
        for slot in o.material_slots:
            m = slot.material
            if m and m.use_nodes:
                nt = m.node_tree
                for nn in ("__ea", "__ee"):
                    if nn in nt.nodes:
                        nt.nodes.remove(nt.nodes[nn])
    for name, links in saved.items():
        nt = bpy.data.materials[name].node_tree
        for a, b in links:
            nt.links.new(a, b)
    _cleanup(objs)
    bpy.data.images.remove(img)
    return arr
