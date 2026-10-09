"""Blender preview materials equivalent to the Unity URP setup, built from the baked PNGs.

Paints/carbon get a clear-coat layer in the preview (Unity: URP Complex Lit clear coat, see VEHICLES.md).
"""
import os

import bpy

import vmatdefs as MD
import vpaths


def _img(rel, noncolor):
    full = os.path.join(vpaths.UNITY_VEH, rel)
    if not os.path.exists(full):
        return None
    im = bpy.data.images.load(full, check_existing=True)
    if noncolor:
        im.colorspace_settings.name = "Non-Color"
    im.alpha_mode = "CHANNEL_PACKED"
    return im


def _inp(node, ident_or_name):
    for i in node.inputs:
        if i.identifier == ident_or_name or i.name == ident_or_name:
            return i
    raise KeyError(ident_or_name)


def build(name, mat=None):
    d = MD.REGISTRY.get(name)
    m = mat or bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    L = nt.links.new
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    L(bsdf.outputs[0], out.inputs["Surface"])
    if d is None:
        bsdf.inputs["Base Color"].default_value = (0.3, 0.3, 0.3, 1)
        return m
    pv = d.get("preview", {})
    if pv.get("coat"):
        bsdf.inputs["Coat Weight"].default_value = pv["coat"]
        bsdf.inputs["Coat Roughness"].default_value = pv.get("coat_rough", 0.03)
        bsdf.inputs["Coat IOR"].default_value = 1.5
    if d["kind"] == "param":
        u = d["unity"]
        c = u.get("baseColor", [0.5, 0.5, 0.5, 1.0])
        bsdf.inputs["Base Color"].default_value = (c[0], c[1], c[2], 1.0)
        bsdf.inputs["Metallic"].default_value = u.get("metallic", 0.0)
        bsdf.inputs["Roughness"].default_value = 1.0 - u.get("smoothness", 0.5)
        if name == "veh_glass":
            # thin tinted glass: transmission with a dark tint so the interior silhouette reads
            bsdf.inputs["Transmission Weight"].default_value = 1.0
            bsdf.inputs["Thin Wall"].default_value = True
            bsdf.inputs["IOR"].default_value = 1.5
            bsdf.inputs["Base Color"].default_value = (0.10, 0.13, 0.16, 1.0)
            bsdf.inputs["Roughness"].default_value = 0.02
        return m
    tile = d.get("tile")
    tc = nt.nodes.new("ShaderNodeUVMap")
    tc.uv_map = "UVMap"
    mp = nt.nodes.new("ShaderNodeMapping")
    if tile:
        mp.inputs["Scale"].default_value = (1 / tile, 1 / tile, 1)
    L(tc.outputs[0], mp.inputs["Vector"])
    vec = mp.outputs[0]

    def tex(chan, noncolor):
        im = _img(MD.tex_path(name, chan), noncolor)
        if im is None:
            return None
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = im
        n.interpolation = "Cubic" if chan == "Normal" else "Linear"
        L(vec, n.inputs[0])
        return n
    bc = tex("BaseColor", False) if d["kind"] != "shared" else None
    mk = tex("MaskMap", True)
    nm = tex("Normal", True)
    em = tex("Emission", False) if d.get("emissive") else None
    if bc:
        L(bc.outputs["Color"], bsdf.inputs["Base Color"])
    else:
        c = MD.preview_colour(name)
        bsdf.inputs["Base Color"].default_value = (c[0], c[1], c[2], 1)
    if mk:
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        L(mk.outputs["Color"], sep.inputs[0])
        L(sep.outputs[0], bsdf.inputs["Metallic"])
        inv = nt.nodes.new("ShaderNodeMath")
        inv.operation = "SUBTRACT"
        inv.inputs[0].default_value = 1.0
        L(mk.outputs["Alpha"], inv.inputs[1])
        L(inv.outputs[0], bsdf.inputs["Roughness"])
    if nm:
        nmap = nt.nodes.new("ShaderNodeNormalMap")
        nmap.uv_map = "UVMap"
        L(nm.outputs["Color"], nmap.inputs["Color"])
        L(nmap.outputs[0], bsdf.inputs["Normal"])
        if pv.get("coat"):
            pass  # clear coat stays smooth (no flake normal on the coat) -> glossy top layer
    if em:
        L(em.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = d.get("emissionIntensity", 1.0)
    u = d.get("unity", {})
    if u.get("surface") == "Transparent":
        if u.get("blend") == "Additive":
            # additive holo: emission + transparency
            tr = nt.nodes.new("ShaderNodeBsdfTransparent")
            add = nt.nodes.new("ShaderNodeAddShader")
            emn = nt.nodes.new("ShaderNodeEmission")
            emn.inputs["Strength"].default_value = d.get("emissionIntensity", 1.0)
            if em:
                L(em.outputs["Color"], emn.inputs["Color"])
            L(tr.outputs[0], add.inputs[0])
            L(emn.outputs[0], add.inputs[1])
            L(add.outputs[0], out.inputs["Surface"])
        elif bc:
            L(bc.outputs["Alpha"], bsdf.inputs["Alpha"])
    return m


def build_all(names=None):
    for n in (names or [m.name for m in bpy.data.materials]):
        if n in MD.REGISTRY:
            build(n, bpy.data.materials.get(n))
