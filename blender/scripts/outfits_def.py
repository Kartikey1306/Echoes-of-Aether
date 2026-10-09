"""Kael and Lyra outfits (spec sections 8 and 9), built with outfit.py primitives."""
import bpy, math
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
import outfit, texpaint, os
from texpaint import smoothstep as ss
from outfit import BodyData, Shell, Plate, Attached, tube, rounded_box, ray_ring, surface_patch


def mat(name, color, rough=0.6, metal=0.0, emit=None):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    c = tuple(int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    bsdf.inputs["Base Color"].default_value = (c[0] ** 2.2, c[1] ** 2.2, c[2] ** 2.2, 1)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if emit:
        e = tuple(int(emit[i:i + 2], 16) / 255 for i in (1, 3, 5))
        bsdf.inputs["Emission Color"].default_value = (e[0] ** 2.2, e[1] ** 2.2, e[2] ** 2.2, 1)
        bsdf.inputs["Emission Strength"].default_value = 6.0
    return m


SHELLS = []
TEX_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "unity", "EchoesOfAether", "Assets", "Art", "Characters"))


def hexrgb(h):
    return [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]


def garment_mat(name, spec, pants=False):
    """Preview material that colours zones from the painted mask (the Unity shader does the same)."""
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    m["eoa_kind"] = "garment"
    m["eoa_slot"] = "pants" if pants else "top"
    return m


def paint(obj, spec, part, fields):
    out = os.path.join(TEX_ROOT, spec["name"], "Textures")
    size = 2048 if part == "Top" else 1024
    texpaint.paint_garment(obj, size, fields, out, spec["name"] + "_" + part)
    m = obj.data.materials[0]
    nt = m.node_tree
    for n in list(nt.nodes):
        if n.type not in ("OUTPUT_MATERIAL",):
            nt.nodes.remove(n)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs[0], nt.nodes["Material Output"].inputs[0])
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(os.path.join(out, spec["name"] + "_" + part + "_Mask.png"))
    tex.image.colorspace_settings.name = "Non-Color"
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(tex.outputs["Color"], sep.inputs[0])
    cols = spec["colors"]
    def rgb(h):
        n = nt.nodes.new("ShaderNodeRGB"); c = hexrgb(h); n.outputs[0].default_value = (c[0] ** 2.2, c[1] ** 2.2, c[2] ** 2.2, 1); return n
    prim = rgb(cols["pants"] if part == "Pants" else cols["primary"])
    sec = rgb(cols["secondary"])
    trim = rgb(cols["trim"])
    mix1 = nt.nodes.new("ShaderNodeMix"); mix1.data_type = "RGBA"
    nt.links.new(sep.outputs[0], mix1.inputs["Factor"]); nt.links.new(prim.outputs[0], mix1.inputs[6]); nt.links.new(sec.outputs[0], mix1.inputs[7])
    mix2 = nt.nodes.new("ShaderNodeMix"); mix2.data_type = "RGBA"
    nt.links.new(sep.outputs[1], mix2.inputs["Factor"]); nt.links.new(mix1.outputs[2], mix2.inputs[6]); nt.links.new(trim.outputs[0], mix2.inputs[7])
    # Seam darkening
    inv = nt.nodes.new("ShaderNodeMath"); inv.operation = "MULTIPLY_ADD"; inv.inputs[1].default_value = -0.55; inv.inputs[2].default_value = 1.0
    nt.links.new(tex.outputs["Alpha"], inv.inputs[0])
    mul = nt.nodes.new("ShaderNodeMix"); mul.data_type = "RGBA"; mul.blend_type = "MULTIPLY"; mul.inputs["Factor"].default_value = 1.0
    nt.links.new(mix2.outputs[2], mul.inputs[6])
    gray = nt.nodes.new("ShaderNodeCombineColor")
    for i in range(3):
        nt.links.new(inv.outputs[0], gray.inputs[i])
    nt.links.new(gray.outputs[0], mul.inputs[7])
    nt.links.new(mul.outputs[2], bsdf.inputs["Base Color"])
    nt.links.new(sep.outputs[1], bsdf.inputs["Metallic"])
    bsdf.inputs["Roughness"].default_value = 0.72
    nmap = nt.nodes.new("ShaderNodeNormalMap")
    ntex = nt.nodes.new("ShaderNodeTexImage")
    ntex.image = bpy.data.images.load(os.path.join(out, spec["name"] + "_" + part + "_Normal.png"))
    ntex.image.colorspace_settings.name = "Non-Color"
    nt.links.new(ntex.outputs["Color"], nmap.inputs["Color"])
    nt.links.new(nmap.outputs[0], bsdf.inputs["Normal"])


def regions(B):
    W = B.wsum
    R = {
        "head": W(["mixamorig:Head", "mixamorig:HeadTop_End", "mixamorig:LeftEye", "mixamorig:RightEye"]),
        "neck": W(["mixamorig:Neck"]),
        "torso": W(["mixamorig:Spine", "mixamorig:Spine1", "mixamorig:Spine2", "mixamorig:LeftShoulder", "mixamorig:RightShoulder", "mixamorig:LeftBreast", "mixamorig:RightBreast"]),
        "hips": W(["mixamorig:Hips"]),
        "armL": W(["mixamorig:LeftArm", "mixamorig:LeftForeArm"]),
        "armR": W(["mixamorig:RightArm", "mixamorig:RightForeArm"]),
        "handL": W(["mixamorig:LeftHand*"]),
        "handR": W(["mixamorig:RightHand*"]),
        "legL": W(["mixamorig:LeftUpLeg", "mixamorig:LeftLeg"]),
        "legR": W(["mixamorig:RightUpLeg", "mixamorig:RightLeg"]),
        "footL": W(["mixamorig:LeftFoot", "mixamorig:LeftToe*"]),
        "footR": W(["mixamorig:RightFoot", "mixamorig:RightToe*"]),
    }
    return R


def faces_where(B, vmask):
    return [i for i, f in enumerate(B.faces) if all(vmask[v] for v in f)]


def landmarks(B):
    L = {}
    for b in ["Hips", "Spine", "Spine1", "Spine2", "Neck", "Head", "LeftShoulder", "RightShoulder", "LeftArm", "RightArm",
              "LeftForeArm", "RightForeArm", "LeftHand", "RightHand", "LeftUpLeg", "RightUpLeg", "LeftLeg", "RightLeg", "LeftFoot", "RightFoot"]:
        L[b] = B.head(b)
    return L


def build_common(B, rig, spec):
    """Shared garment layout driven by a spec dict. Returns created objects."""
    R = regions(B)
    L = landmarks(B)
    co = B.basis
    vn = B.normals(co)
    z = co[:, 2]
    x = co[:, 0]
    objs = []
    M = spec["materials"]

    # --- Top (jacket / suit top): torso + arms + upper hips, sleeves to the wrist.
    hem_z = L["Hips"][2] + spec["hem"]
    top_mask = (R["torso"] + R["armL"] + R["armR"] + R["hips"] * (z > hem_z)) > 0.5
    top_mask &= (R["handL"] < 0.35) & (R["handR"] < 0.35) & (R["neck"] < 0.6) & (R["head"] < 0.05)
    top_mask &= z > hem_z
    chest_z = L["Spine2"][2]

    def top_off(c, n, ids):
        o = np.full(len(ids), spec["top_offset"])
        o += np.clip((c[:, 2] - L["Spine"][2]) * 0.04, 0, 0.006)  # a little looser across chest/back
        return o

    def top_mat(fc, fi):
        if fc is None:
            return M["trim"].name
        n = vn[B.faces[fi]].mean(axis=0)
        return spec["top_zone"](fc, n, L).name

    top = Shell(B, faces_where(B, top_mask), top_off, smooth=5, name=spec["name"] + "_Top")
    SHELLS.append(top)
    top_m = garment_mat(spec["name"] + "_Top", spec)
    o = top.build(rig, lambda fc, fi: top_m.name, [top_m])
    paint(o, spec, "Top", spec["top_fields"](L))
    objs.append(o)

    # --- Pants / leggings: hips + legs above the boots, up to the waist.
    boot_z = L["LeftFoot"][2] + spec["boot_height"]
    waist_z = L["Spine"][2] + 0.02
    pants_bottom = L["LeftFoot"][2] + spec.get("pants_bottom", 0.07)
    pants_mask = ((R["hips"] + R["legL"] + R["legR"] + R["torso"] * (z < waist_z)) > 0.5) & (z < waist_z) & (z > pants_bottom)
    pants_mask &= (R["handL"] < 0.1) & (R["handR"] < 0.1)

    def pants_mat(fc, fi):
        if fc is None:
            return M["pants"].name
        n = vn[B.faces[fi]].mean(axis=0)
        return spec["pants_zone"](fc, n, L).name

    pants = Shell(B, faces_where(B, pants_mask), lambda c, n, ids: np.full(len(ids), spec["pants_offset"]), smooth=4, name=spec["name"] + "_Pants")
    SHELLS.append(pants)
    pants_m = garment_mat(spec["name"] + "_Pants", spec, pants=True)
    o = pants.build(rig, lambda fc, fi: pants_m.name, [pants_m])
    paint(o, spec, "Pants", spec["pants_fields"](L))
    objs.append(o)

    # --- Boots: feet + lower shin, thick sole (only when the character has no shoe asset).
    boot_mask = ((R["footL"] + R["footR"] + R["legL"] + R["legR"]) > 0.5) & (z < boot_z)

    def boot_off(c, n, ids):
        o = np.full(len(ids), 0.007)
        o[n[:, 2] < -0.6] = 0.016  # sole
        return o

    def boot_mat(fc, fi):
        if fc is None:
            return M["boot"].name
        n = vn[B.faces[fi]].mean(axis=0)
        if n[2] < -0.5 or fc[2] < L["LeftFoot"][2] * 0.35:
            return M["sole"].name
        return M["boot"].name

    if spec.get("boots", False):
        boots = Shell(B, faces_where(B, boot_mask), boot_off, smooth=3, name=spec["name"] + "_Boots")
        objs.append(boots.build(rig, boot_mat, [M["boot"], M["sole"]]))

    # --- Gloves.
    if spec.get("gloves", True):
        glove_mask = (R["handL"] + R["handR"]) > 0.3
        gl = Shell(B, faces_where(B, glove_mask), lambda c, n, ids: np.full(len(ids), 0.0022), smooth=0, name=spec["name"] + "_Gloves")
        objs.append(gl.build(rig, lambda fc, fi: M["glove"].name, [M["glove"]]))
    return objs, R, L


# ----------------------------------------------------------------------------- per character


def kael(body, rig):
    B = BodyData(body, rig)
    M = {
        "jacket": mat("SuitMain", "#33363c", 0.78), "panel": mat("SuitSecondary", "#202226", 0.82),
        "trim": mat("Metal", "#8a8f96", 0.35, 0.9), "pants": mat("Pants", "#2b2d32", 0.85),
        "knee": mat("SuitSecondary", "#202226"), "boot": mat("Leather", "#2e2722", 0.55), "sole": mat("Rubber", "#141210", 0.9),
        "glove": mat("Gloves", "#26272a", 0.6), "armor": mat("Armor", "#4b4e54", 0.42, 0.45),
        "glow": mat("Glow", "#56b8ff", 0.3, 0.0, "#56b8ff"), "belt": mat("Belt", "#3b3530", 0.6), "screen": mat("Screen", "#0d1a22", 0.2, 0.0, "#4fb4ff"),
    }

    def top_zone(fc, n, L):
        # Diagonal zip from the left collar to the right hip (front), asymmetric jacket.
        a, b = np.array([0.065, -0.1, L["Neck"][2] - 0.02]), np.array([-0.11, -0.1, L["Hips"][2] - 0.02])
        if fc[1] < -0.02 and n[1] < -0.3:
            t = np.clip(np.dot(fc[[0, 2]] - a[[0, 2]], (b - a)[[0, 2]]) / np.dot((b - a)[[0, 2]], (b - a)[[0, 2]]), 0, 1)
            if np.linalg.norm(fc[[0, 2]] - (a + (b - a) * t)[[0, 2]]) < 0.011:
                return M["trim"]
        if fc[2] > L["Spine2"][2] + 0.09 and abs(fc[0]) < L["LeftArm"][0] - 0.02:
            return M["panel"]  # shoulder yoke
        if abs(n[0]) > 0.78 and fc[2] < L["Spine2"][2] + 0.05 and abs(fc[0]) < L["LeftArm"][0]:
            return M["panel"]  # side panels
        hand = L["LeftHand"] if fc[0] > 0 else L["RightHand"]
        if np.linalg.norm(fc - hand) < 0.085:
            return M["panel"]  # cuffs
        return M["jacket"]

    def pants_zone(fc, n, L):
        knee = L["LeftLeg"] if fc[0] > 0 else L["RightLeg"]
        if abs(fc[2] - knee[2]) < 0.07 and n[1] < -0.2:
            return M["knee"]
        return M["pants"]

    def top_fields(L):
        armx = L["LeftArm"][0]
        a = np.array([0.065, L["Neck"][2] - 0.02]); b = np.array([-0.11, L["Hips"][2] - 0.02])
        def fn(P, N):
            x, y, z = P.T; nx, ny, nz = N.T
            yoke = ss(L["Spine2"][2] + 0.085, L["Spine2"][2] + 0.091, z) * (1 - ss(armx - 0.035, armx - 0.028, np.abs(x)))
            side = ss(0.72, 0.8, np.abs(nx)) * (1 - ss(L["Spine2"][2] + 0.04, L["Spine2"][2] + 0.05, z)) * (1 - ss(armx - 0.012, armx - 0.004, np.abs(x)))
            hand = np.where(x[:, None] > 0, L["LeftHand"], L["RightHand"])
            cuff = 1 - ss(0.078, 0.084, np.linalg.norm(P - hand, axis=1))
            R = np.maximum(np.maximum(yoke, side), cuff)
            q = np.stack([x, z], 1); ab = b - a
            t = np.clip(((q - a) @ ab) / (ab @ ab), 0, 1)
            d = np.linalg.norm(q - (a + t[:, None] * ab), axis=1)
            front = ss(-0.25, -0.45, ny)
            G = (1 - ss(0.0075, 0.0095, d)) * front
            seam = np.maximum(4 * R * (1 - R), 4 * G * (1 - G))
            seam = np.maximum(seam, (1 - ss(0.0012, 0.0025, np.abs(d - 0.016))) * front * 0.6)  # stitch beside the zip
            return np.stack([R, G, np.zeros_like(R), np.clip(seam, 0, 1)], 1)
        return fn

    def pants_fields(L):
        def fn(P, N):
            x, y, z = P.T; nx, ny, nz = N.T
            knee = np.where(x[:, None] > 0, L["LeftLeg"], L["RightLeg"])
            dk = np.abs(z - knee[:, 2])
            R = (1 - ss(0.068, 0.074, dk)) * ss(-0.15, -0.3, ny)
            outer = (1 - ss(0.0015, 0.003, np.abs(np.abs(nx) - 0.97))) * ss(0.05, 0.08, np.abs(x))
            seam = np.maximum(4 * R * (1 - R), outer)
            return np.stack([R, np.zeros_like(R), np.zeros_like(R), np.clip(seam, 0, 1)], 1)
        return fn

    spec = {
        "name": "Kael", "materials": M, "top_fields": top_fields, "pants_fields": pants_fields,
        "colors": {"primary": "#33363c", "secondary": "#202226", "trim": "#8a8f96", "pants": "#2b2d32"}, "hem": 0.055, "top_offset": 0.011, "pants_offset": 0.006, "boot_height": 0.16,
        "top_zone": top_zone, "top_mats": [M["jacket"], M["panel"], M["trim"]],
        "pants_zone": pants_zone, "pants_mats": [M["pants"], M["knee"]],
    }
    objs, R, L = build_common(B, rig, spec)
    co, vn = B.basis, B.normals(B.basis)
    x, y, z = co[:, 0], co[:, 1], co[:, 2]

    tree = BVHTree.FromPolygons([Vector(c) for c in co], B.faces)
    # Shoulder pauldrons (left heavier), laid over the jacket.
    for side, sgn, bone, sc in (("L", 1, "LeftArm", 1.15), ("R", -1, "RightArm", 0.82)):
        sh = L["LeftArm" if sgn > 0 else "RightArm"]
        ctr = sh + np.array([sgn * 0.035, 0.0, 0.035])
        v, f = surface_patch(tree, ctr, (sgn * 0.75, 0, 0.66), (0, 0, 1), 0.075 * sc, 0.07 * sc, n_exp=2.8, offset=0.026, thickness=0.007, crown=0.008)
        objs.append(Attached(B, v, f, f"Kael_Pauldron{side}").build(rig, bone, [M["armor"]]))
        # Second, smaller lame below the main plate.
        v, f = surface_patch(tree, ctr + np.array([sgn * 0.03, 0, -0.07]), (sgn * 0.95, 0, 0.3), (0, 0, 1), 0.06 * sc, 0.035 * sc, n_exp=3.2, offset=0.022, thickness=0.006, crown=0.004)
        objs.append(Attached(B, v, f, f"Kael_PauldronLame{side}").build(rig, bone, [M["armor"]]))
    # Left chest plate.
    v, f = surface_patch(tree, (0.085, -0.2, L["Spine2"][2] + 0.04), (0.15, -1, 0.1), (0, 0, 1), 0.07, 0.085, n_exp=3.4, offset=0.024, thickness=0.008, crown=0.006, skew=0.15)
    objs.append(Attached(B, v, f, "Kael_ChestPlate").build(rig, "Spine2", [M["armor"]]))
    # Right forearm guard + Aether interface.
    fa, hd = L["RightForeArm"], L["RightHand"]
    axis = hd - fa
    mid = fa + axis * 0.55
    up_axis = Vector(axis).normalized()
    v, f = surface_patch(tree, mid, (0, 0, 1), tuple(up_axis), 0.035, np.linalg.norm(axis) * 0.36, n_exp=4, offset=0.017, thickness=0.006, crown=0.004)
    objs.append(Attached(B, v, f, "Kael_ForearmGuardR").build(rig, "RightForeArm", [M["armor"]]))
    rot = Vector(axis).to_track_quat("Y", "Z").to_matrix()
    hit, nn, _, _ = tree.ray_cast(Vector(mid) + Vector((0, 0, 0.3)), Vector((0, 0, -1)), 0.6)
    top_pt = (hit + nn * 0.03) if hit else Vector(mid) + Vector((0, 0, 0.05))
    v, f = rounded_box(top_pt, (0.038, 0.09, 0.016), rot, 0.4)
    dev = Attached(B, v, f, "Kael_Interface")
    objs.append(dev.build(rig, "RightForeArm", [M["armor"], M["screen"]], mat_index=lambda p: 1 if p.normal.z > 0.8 else 0))
    # Knee pads.
    for side, sgn in (("L", 1), ("R", -1)):
        kn = L["LeftLeg" if sgn > 0 else "RightLeg"]
        v, f = surface_patch(tree, kn + np.array([0, -0.02, 0.01]), (0, -1, 0.1), (0, 0, 1), 0.05, 0.065, n_exp=3.0, offset=0.02, thickness=0.007, crown=0.007)
        objs.append(Attached(B, v, f, f"Kael_KneePad{side}").build(rig, "LeftLeg" if sgn > 0 else "RightLeg", [M["armor"]]))
    # High collar (hugging the neck, open at the front for the diagonal zip).
    nz = L["Neck"][2] + 0.01
    nz = L["Neck"][2] - 0.035
    ring, nrm = ray_ring(tree, (L["Neck"][0], L["Neck"][1] + 0.005, nz), None, 0.08, 24, push=0.015)
    ring2, nrm2 = ray_ring(tree, (L["Neck"][0], L["Neck"][1] + 0.005, nz + 0.05), None, 0.065, 24, push=0.01)
    verts, faces = [], []
    for p, q in zip(ring, ring2):
        verts += [tuple(p - Vector((0, 0, 0.01))), tuple(q)]
    for i in range(len(ring)):
        a, b = i * 2, ((i + 1) % len(ring)) * 2
        faces.append([a, b, b + 1, a + 1])
    objs.append(Attached(B, verts, faces, "Kael_Collar").build(rig, "Neck", [M["panel"]], weights_from_body=True))
    # Belt with pouches.
    bz = L["Hips"][2] + 0.075
    ring, nrm = ray_ring(tree, (0, L["Hips"][1], bz), None, 0.17, 28, push=0.014)
    verts, faces = [], []
    for p in ring:
        verts += [tuple(p - Vector((0, 0, 0.022))), tuple(p + Vector((0, 0, 0.022)))]
    for i in range(len(ring)):
        a, b = i * 2, ((i + 1) % len(ring)) * 2
        faces.append([a, b, b + 1, a + 1])
    nb = len(verts)
    for ang in (0.9, 1.6, -1.2, 2.6):
        i = int(((ang % (2 * math.pi)) / (2 * math.pi)) * len(ring)) % len(ring)
        p, n = ring[i], nrm[i]
        rot = Vector((n.x, n.y, 0)).normalized().to_track_quat("Y", "Z").to_matrix()
        bv, bf = rounded_box(p + Vector((n.x, n.y, 0)).normalized() * 0.02 - Vector((0, 0, 0.012)), (0.07, 0.035, 0.065), rot, 0.35)
        faces += [[k + len(verts) for k in face] for face in bf]
        verts += bv
    objs.append(Attached(B, verts, faces, "Kael_Belt").build(rig, "Hips", [M["belt"]]))
    # Glow conduits: down the left jacket front and along the right forearm guard.
    pts = [Vector((0.09, -0.3, zz)) for zz in np.linspace(L["Spine2"][2] + 0.08, L["Hips"][2] + 0.02, 10)]
    line = []
    for p in pts:
        hit, n, _, _ = tree.ray_cast(p, Vector((0, 1, 0)), 0.5)
        if hit:
            line.append(hit + n * 0.015)
    if len(line) > 2:
        v, f = tube(line, 0.0035, 6)
        objs.append(Attached(B, v, f, "Kael_Conduit").build(rig, "Spine1", [M["glow"]], weights_from_body=True))
    return objs


def lyra(body, rig):
    B = BodyData(body, rig)
    M = {
        "suit": mat("SuitMain", "#383b42", 0.72), "violet": mat("SuitSecondary", "#3b2858", 0.7),
        "trim": mat("Metal", "#8a8f96", 0.35, 0.9), "pants": mat("Pants", "#33363d", 0.78),
        "boot": mat("Leather", "#26252a", 0.55), "sole": mat("Rubber", "#121114", 0.9), "glove": mat("Gloves", "#25262b", 0.6),
        "armor": mat("Armor", "#4d5058", 0.42, 0.45), "harness": mat("Harness", "#24252b", 0.5),
        "glow": mat("Glow", "#62dcff", 0.3, 0.0, "#62dcff"), "glow2": mat("Glow2", "#a77bff", 0.3, 0.0, "#a77bff"),
    }

    def top_zone(fc, n, L):
        if abs(n[0]) > 0.72 and abs(fc[0]) < L["LeftArm"][0] - 0.01:
            return M["violet"]  # side panels
        # Inner sleeve panels
        arm = L["LeftArm"] if fc[0] > 0 else L["RightArm"]
        if abs(fc[0]) > abs(arm[0]) + 0.02 and n[2] < -0.45:
            return M["violet"]
        return M["suit"]

    def pants_zone(fc, n, L):
        if abs(n[0]) > 0.8 and abs(fc[0]) > 0.08:
            return M["violet"]  # outer thigh stripes
        return M["pants"]

    def top_fields(L):
        armx = L["LeftArm"][0]
        def fn(P, N):
            x, y, z = P.T; nx, ny, nz = N.T
            side = ss(0.66, 0.74, np.abs(nx)) * (1 - ss(armx - 0.016, armx - 0.008, np.abs(x)))
            inner = ss(np.abs(armx) + 0.01, np.abs(armx) + 0.03, np.abs(x)) * ss(-0.35, -0.55, nz)
            # Asymmetric violet chevron over the left chest.
            chev = (1 - ss(0.009, 0.013, np.abs((z - L["Spine2"][2]) - 0.55 * (x - 0.03)))) * ss(0.0, 0.02, x) * (1 - ss(0.12, 0.13, x)) * ss(-0.4, -0.6, ny)
            R = np.maximum(np.maximum(side, inner), chev)
            seam = 4 * R * (1 - R)
            return np.stack([R, np.zeros_like(R), np.zeros_like(R), np.clip(seam, 0, 1)], 1)
        return fn

    def pants_fields(L):
        def fn(P, N):
            x, y, z = P.T; nx, ny, nz = N.T
            R = ss(0.78, 0.86, np.abs(nx)) * ss(0.07, 0.09, np.abs(x))
            seam = 4 * R * (1 - R)
            return np.stack([R, np.zeros_like(R), np.zeros_like(R), np.clip(seam, 0, 1)], 1)
        return fn

    spec = {
        "name": "Lyra", "materials": M, "top_fields": top_fields, "pants_fields": pants_fields,
        "colors": {"primary": "#383b42", "secondary": "#3b2858", "trim": "#8a8f96", "pants": "#33363d"}, "hem": 0.045, "top_offset": 0.006, "pants_offset": 0.004, "boot_height": 0.24,
        "top_zone": top_zone, "top_mats": [M["suit"], M["violet"], M["trim"]],
        "pants_zone": pants_zone, "pants_mats": [M["pants"], M["violet"]],
    }
    objs, R, L = build_common(B, rig, spec)
    co, vn = B.basis, B.normals(B.basis)
    x, y, z = co[:, 0], co[:, 1], co[:, 2]
    # Light right shoulder plate.
    sh = L["RightArm"]
    m = (np.linalg.norm(co - (sh + np.array([-0.015, 0, 0.025])), axis=1) < 0.07) & (vn[:, 2] > -0.1) & (vn[:, 0] < 0.1)
    objs.append(Plate(B, m, offset=0.018, thickness=0.006, smooth=12, name="Lyra_ShoulderR").build(rig, "RightArm", M["armor"]))
    # Left forearm guard.
    fa, hd = L["LeftForeArm"], L["LeftHand"]
    axis = hd - fa
    t = ((co - fa) @ axis) / (axis @ axis)
    m = (R["armL"] > 0.5) & (t > 0.25) & (t < 0.88) & (vn[:, 2] > -0.15)
    objs.append(Plate(B, m, offset=0.013, thickness=0.005, smooth=8, name="Lyra_ForearmGuardL").build(rig, "LeftForeArm", M["armor"]))
    tree = BVHTree.FromPolygons([Vector(c) for c in co], B.faces)
    # Energy harness: two straps from the shoulders crossing to the opposite hips, plus a hip belt.
    def strap(a, b, n=14, push=0.013, width=0.016):
        a, b = Vector(a), Vector(b)
        pts = []
        for i in range(n):
            p = a.lerp(b, i / (n - 1))
            # Cast from in front of the body towards it so the first hit is the front surface.
            hit, nn, _, _ = tree.ray_cast(Vector((p.x, -0.6, p.z)), Vector((0, 1, 0)), 1.2)
            if hit:
                pts.append((hit + nn * push, nn))
        verts, faces = [], []
        for i, (p, nn) in enumerate(pts):
            t = (pts[min(i + 1, len(pts) - 1)][0] - pts[max(i - 1, 0)][0]).normalized()
            side = t.cross(nn).normalized() * width
            verts += [tuple(p - side), tuple(p + side)]
        for i in range(len(pts) - 1):
            faces.append([i * 2, i * 2 + 2, i * 2 + 3, i * 2 + 1])
        return verts, faces
    verts, faces = [], []
    for a, b in [((0.08, -0.2, L["Spine2"][2] + 0.14), (-0.1, -0.2, L["Hips"][2] + 0.06)),
                 ((-0.08, -0.2, L["Spine2"][2] + 0.14), (0.1, -0.2, L["Hips"][2] + 0.06))]:
        v, f = strap(a, b)
        faces += [[k + len(verts) for k in face] for face in f]
        verts += v
    bz = L["Hips"][2] + 0.06
    ring, nrm = ray_ring(tree, (0, L["Hips"][1], bz), None, 0.16, 28, push=0.01)
    base = len(verts)
    for p in ring:
        verts += [tuple(p - Vector((0, 0, 0.016))), tuple(p + Vector((0, 0, 0.016)))]
    for i in range(len(ring)):
        a, b = base + i * 2, base + ((i + 1) % len(ring)) * 2
        faces.append([a, b, b + 1, a + 1])
    objs.append(Attached(B, verts, faces, "Lyra_Harness").build(rig, "Spine1", [M["harness"]], weights_from_body=True))
    # Chest unit where the straps cross, with a glowing core.
    cz = L["Spine1"][2] + 0.03
    hit, nn, _, _ = tree.ray_cast(Vector((0, -0.4, cz)), Vector((0, 1, 0)), 0.8)
    if hit:
        rot = Vector((0, -1, 0)).to_track_quat("Y", "Z").to_matrix()
        v, f = rounded_box(hit + nn * 0.02, (0.075, 0.03, 0.075), rot, 0.45)
        objs.append(Attached(B, v, f, "Lyra_ChestUnit").build(rig, "Spine1", [M["armor"]]))
        v, f = rounded_box(hit + nn * 0.038, (0.026, 0.008, 0.026), rot, 0.9)
        objs.append(Attached(B, v, f, "Lyra_ChestCore").build(rig, "Spine1", [M["glow"]]))
    # Left hip module.
    i = int(len(ring) * 0.22)
    p, n = ring[i], nrm[i]
    rot = Vector((n.x, n.y, 0)).normalized().to_track_quat("Y", "Z").to_matrix()
    v, f = rounded_box(p + Vector((n.x, n.y, 0)).normalized() * 0.02 - Vector((0, 0, 0.03)), (0.08, 0.04, 0.1), rot, 0.4)
    objs.append(Attached(B, v, f, "Lyra_HipModule").build(rig, "Hips", [M["armor"], M["glow2"]], mat_index=lambda p: 1 if abs(p.normal.z) > 0.9 else 0))
    # Conduits along the outer arms.
    for side, sgn, col in (("L", 1, M["glow"]), ("R", -1, M["glow2"])):
        a0, f0, h0 = L["LeftArm" if sgn > 0 else "RightArm"], L["LeftForeArm" if sgn > 0 else "RightForeArm"], L["LeftHand" if sgn > 0 else "RightHand"]
        line = []
        for t in np.linspace(0.05, 0.95, 12):
            p = Vector(a0 + (f0 - a0) * (t * 2) if t < 0.5 else f0 + (h0 - f0) * ((t - 0.5) * 2))
            d = Vector((0, 0, -1))
            hit, nn, _, _ = tree.ray_cast(p - d * 0.2, d, 0.3)
            if hit:
                line.append(hit + nn * 0.01)
        if len(line) > 2:
            v, f = tube(line, 0.003, 6)
            objs.append(Attached(B, v, f, f"Lyra_Conduit{side}").build(rig, "LeftArm" if sgn > 0 else "RightArm", [col], weights_from_body=True))
    return objs


def npc_gear(body, rig, gear):
    """Small props for NPCs: headset, satchel, goggles, scarf."""
    B = BodyData(body, rig)
    L = landmarks(B)
    co = B.basis
    tree = BVHTree.FromPolygons([Vector(c) for c in co], B.faces)
    name = rig.name
    M = {"gear": mat("Gear", "#3a3f46", 0.5, 0.3), "strap": mat("Strap", "#3b3530", 0.6), "lens": mat("Lens", "#1a2a30", 0.1, 0.0, "#3fa8c8"),
         "scarf": mat("Scarf", "#5a4a3a", 0.9)}
    objs = []
    hc = L["Head"] + np.array([0, -0.01, 0.09])
    if "headset" in gear:
        for sgn in (1, -1):
            hit, nn, _, _ = tree.ray_cast(Vector(hc + np.array([sgn * 0.3, 0, 0])), Vector((-sgn, 0, 0)), 0.5)
            if hit:
                v, f = rounded_box(hit + nn * 0.015, (0.03, 0.05, 0.05), None, 0.6)
                objs.append(Attached(B, v, f, f"{name}_Earpiece{'L' if sgn > 0 else 'R'}").build(rig, "Head", [M["gear"]]))
        ring, _ = ray_ring(tree, (hc[0], hc[1] + 0.02, hc[2] + 0.07), None, 0.08, 16, start_angle=math.pi * 0.5, end_angle=math.pi * 1.5, push=0.025)
        v, f = tube([tuple(p) for p in ring], 0.006, 6)
        objs.append(Attached(B, v, f, f"{name}_HeadsetBand").build(rig, "Head", [M["gear"]]))
        hit, nn, _, _ = tree.ray_cast(Vector(hc + np.array([0.3, -0.05, -0.05])), Vector((-1, 0, 0)), 0.5)
        if hit:
            v, f = tube([tuple(hit + nn * 0.02), tuple(Vector(hc + np.array([0.05, -0.1, -0.07])))], 0.003, 5)
            objs.append(Attached(B, v, f, f"{name}_HeadsetMic").build(rig, "Head", [M["gear"]]))
    if "satchel" in gear:
        hip = L["Hips"] + np.array([-0.17, 0.0, 0.0])
        v, f = rounded_box(hip, (0.05, 0.22, 0.18), None, 0.35)
        objs.append(Attached(B, v, f, f"{name}_Satchel").build(rig, "Hips", [M["strap"]]))
        pts = []
        for t in np.linspace(0, 1, 14):
            a = Vector((0.12, -0.3, L["Spine2"][2] + 0.12)).lerp(Vector((-0.15, -0.3, L["Hips"][2] + 0.05)), t)
            hit, nn, _, _ = tree.ray_cast(Vector((a.x, -0.6, a.z)), Vector((0, 1, 0)), 1.2)
            if hit:
                pts.append(hit + nn * 0.012)
        if len(pts) > 2:
            v, f = tube(pts, 0.008, 4)
            objs.append(Attached(B, v, f, f"{name}_SatchelStrap").build(rig, "Spine1", [M["strap"]], weights_from_body=True))
    if "goggles" in gear:
        ring, _ = ray_ring(tree, (hc[0], hc[1], hc[2] + 0.06), None, 0.09, 20, push=0.012)
        v, f = tube([tuple(p) for p in ring] + [tuple(ring[0])], 0.008, 5)
        objs.append(Attached(B, v, f, f"{name}_GoggleStrap").build(rig, "Head", [M["strap"]]))
        for sgn in (1, -1):
            hit, nn, _, _ = tree.ray_cast(Vector((sgn * 0.035, -0.4, hc[2] + 0.075)), Vector((0, 1, 0)), 0.8)
            if hit:
                v, f = rounded_box(hit + nn * 0.012, (0.042, 0.02, 0.032), None, 0.8)
                objs.append(Attached(B, v, f, f"{name}_GoggleLens{'L' if sgn > 0 else 'R'}").build(rig, "Head", [M["lens"]]))
    if "scarf" in gear:
        nz = L["Neck"][2] - 0.01
        ring, _ = ray_ring(tree, (L["Neck"][0], L["Neck"][1], nz), None, 0.08, 20, push=0.03)
        ring2, _ = ray_ring(tree, (L["Neck"][0], L["Neck"][1], nz + 0.06), None, 0.07, 20, push=0.025)
        verts, faces = [], []
        for p_, q in zip(ring, ring2):
            verts += [tuple(p_ - Vector((0, 0, 0.03))), tuple(q)]
        for i in range(len(ring)):
            a, b = i * 2, ((i + 1) % len(ring)) * 2
            faces.append([a, b, b + 1, a + 1])
        objs.append(Attached(B, verts, faces, f"{name}_Scarf").build(rig, "Neck", [M["scarf"]], weights_from_body=True))
    return objs


OUTFITS = {"kael": kael, "lyra": lyra}
