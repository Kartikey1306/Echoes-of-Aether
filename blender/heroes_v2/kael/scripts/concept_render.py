"""Blender studio render matching the master concept (dreamlayer/characters/kael/kael_master_front.png): soft studio
light, light grey backdrop, front full-body framing and a relaxed arms-down stance; turntable views; and a side by side
(concept left, render right).

  blender -b blends/kael_s6_deform.blend --python concept_render.py -- <tag> [--samples 128]
"""
import bpy, sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kcommon as K
import numpy as np
from mathutils import Vector, Matrix, Euler
import preview_k2 as PV
import texbake as TB

a = K.args()
tag = a[0] if a else "concept"
samples = int(K.opt(a, "--samples") or 128)
CONCEPT = os.path.join(K.ROOT, "dreamlayer", "characters", "kael", "kael_master_front.png")
OUT = os.path.join(K.PREVIEWS, "concept")
os.makedirs(OUT, exist_ok=True)
rig = bpy.data.objects["Kael"]
# hair: the built-in concept style
hair = None
hb = os.path.join(K.BLENDS, "hair_k3.blend")
if os.path.exists(hb):
    with bpy.data.libraries.load(hb) as (src, dst):
        dst.objects = [n for n in src.objects if n.startswith("Hair_")]
    for o in dst.objects:
        bpy.context.scene.collection.objects.link(o)
        hair = o
for o in bpy.data.objects:
    if o.type == "MESH" and (o.name in ("BodyMH", "BodyFull") or o.name.endswith(("_HI", "_HIB", "_HPG"))):
        o.hide_render = True
    if o.type == "MESH" and o.name.startswith(("Hair_", "Facial_")) and o is not hair:
        o.hide_render = True
PV.setup_materials()
if hair is not None:
    # Unity: grey-normalised hair texture x hair tint (#4f3a2e, sRGB) -> card_material takes the sRGB tint
    m = PV.card_material("cr_hair", os.path.join(K.TEX, "Hair_swept_fade_Color.png"), PV.hexc("#4f3a2e"), 0.4, rough=0.42)
    hair.data.materials.clear(); hair.data.materials.append(m)
    # follow the head bone in the posed render
    mw = hair.matrix_world.copy()
    hair.parent = rig; hair.parent_type = "BONE"; hair.parent_bone = K.PRE + "Head"
    hair.matrix_world = mw
# face morphs the export bakes into the basis (build_export.BAKE_MORPHS) + optional extra keys (--keys a=0.2,b=0.1)
KEYS = {"m_jaw_incr": 0.45, "m_chin_incr": 0.3, "m_cheeks_incr": 0.3, "m_lips_decr": 0.3}
try:
    import build_export_morphs as BEM
    KEYS = dict(BEM.BAKE_MORPHS)
except Exception:
    pass
for kv in (K.opt(a, "--keys") or "").split(","):
    if "=" in kv:
        k_, v_ = kv.split("=")
        KEYS[k_] = float(v_)
for o in bpy.data.objects:
    if o.type == "MESH" and o.data.shape_keys:
        for k_, v_ in KEYS.items():
            kb = o.data.shape_keys.key_blocks.get(k_)
            if kb is not None:
                kb.value = v_
# pose: the concept stance (arms close to the body, soft elbows, feet under the hips)
import kpose
if K.opt(a, "--clip"):
    import posing
    src_, acts_ = posing.load_anim()
    cname, cfr = K.opt(a, "--clip").split(":")
    key = next((k for k in acts_ if k.lower() == cname.lower()), None) or next(k for k in acts_ if cname.lower() in k.lower())
    posing.apply_clip(rig, key, int(cfr), src_, acts_)
    posing.drive_twist(rig)
    K.log("CLIP", key, cfr)
elif not K.opt(a, "--rest"):
    kpose.concept_stance(rig)
# glow materials a bit stronger, like the concept's emissives
# CharacterModel.Glow: base = colour x 0.15, emission = colour x 1.4 (Screen: colour x 0.6)
for mn, col, base, st in (("Glow", "#00e5ff", "#002226", 6.0), ("Glow2", "#ff2bd6", "#260620", 5.0), ("Screen", "#00e5ff", "#001416", 3.0)):
    mm = bpy.data.materials.get(mn)
    if mm and mm.use_nodes:
        b = mm.node_tree.nodes.get("Principled BSDF")
        if b:
            b.inputs["Base Color"].default_value = (*(PV.hexc(base) ** 2.2), 1)
            b.inputs["Emission Color"].default_value = (*(PV.hexc(col) ** 2.2), 1)
            b.inputs["Emission Strength"].default_value = st
            b.inputs["Roughness"].default_value = 0.5


def bloom(strength=0.4, threshold=2.2, size=0.5):
    """Soft bloom on the emissives (the concept's holo sleeve and light strips glow; Unity's capture has bloom too)."""
    sc = bpy.context.scene
    try:
        ng = bpy.data.node_groups.get("k_comp") or bpy.data.node_groups.new("k_comp", "CompositorNodeTree")
        for n in list(ng.nodes):
            ng.nodes.remove(n)
        if not any(it.in_out == "OUTPUT" for it in ng.interface.items_tree):
            ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
        rl = ng.nodes.new("CompositorNodeRLayers")
        gl = ng.nodes.new("CompositorNodeGlare")
        gl.inputs["Type"].default_value = "Bloom"
        gl.inputs["Threshold"].default_value = threshold
        gl.inputs["Strength"].default_value = strength
        gl.inputs["Size"].default_value = size
        out = ng.nodes.new("NodeGroupOutput")
        ng.links.new(rl.outputs["Image"], gl.inputs["Image"])
        ng.links.new(gl.outputs["Image"], out.inputs[0])
        sc.compositing_node_group = ng
    except Exception as e:
        print("bloom skipped", e)


def studio(center):
    K.clear_preview()
    sc = bpy.context.scene
    K.world((0.62, 0.635, 0.66), 0.3)
    # backdrop cyclorama
    me = bpy.data.meshes.new("cyc")
    verts, faces = [], []
    n = 24
    for i in range(n + 1):
        t = i / n
        ang = t * math.pi / 2
        y = 1.6 + math.sin(ang) * 1.2
        z = 1.2 - math.cos(ang) * 1.2
        verts += [(-6, y if t > 0 else 1.6, z if t > 0 else 0.0)]
        verts += [(6, y if t > 0 else 1.6, z if t > 0 else 0.0)]
    verts = [(-6, -6, 0.0), (6, -6, 0.0)] + [(x, 1.6 + 1.2 * math.sin(i / n * math.pi / 2), 1.2 - 1.2 * math.cos(i / n * math.pi / 2))
                                             for i in range(n + 1) for x in (-6, 6)] + [(-6, 2.8, 6.0), (6, 2.8, 6.0)]
    for i in range(len(verts) // 2 - 1):
        faces.append((2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2))
    me.from_pydata(verts, [], faces)
    cyc = bpy.data.objects.new("k_prev_cyc", me)
    bpy.context.scene.collection.objects.link(cyc)
    cm = bpy.data.materials.new("cyc_mat"); cm.use_nodes = True
    bb = cm.node_tree.nodes["Principled BSDF"]
    bb.inputs["Base Color"].default_value = (0.62, 0.63, 0.66, 1); bb.inputs["Roughness"].default_value = 0.85
    cyc.data.materials.append(cm)
    for p in cyc.data.polygons:
        p.use_smooth = True
    cyc["k_preview"] = True

    def area(name, loc, size, power, color=(1, 1, 1)):
        ld = bpy.data.lights.new(name, "AREA"); ld.size = size; ld.energy = power; ld.color = color
        lo = bpy.data.objects.new(name, ld); bpy.context.scene.collection.objects.link(lo)
        lo.location = loc
        d = (Vector(center) - Vector(loc)).normalized()
        lo.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        lo["k_preview"] = True
    area("k_key", (-2.2, -3.2, 2.9), 3.2, 235)
    area("k_fill", (2.6, -2.6, 1.6), 3.5, 55, (0.96, 0.98, 1.0))
    area("k_top", (0.0, -0.6, 4.2), 2.5, 60)
    area("k_rimL", (-2.0, 2.2, 2.2), 1.5, 90, (0.9, 0.95, 1.0))
    area("k_rimR", (2.0, 2.2, 2.2), 1.5, 90, (0.9, 0.95, 1.0))
    sc.render.engine = "CYCLES"
    K.cycles(samples=samples, res=(1296, 1728))
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    sc.view_settings.exposure = 0.0
    if K.opt(a, "--bloom"):
        bloom()


center = (0, 0, 0.98)
out = []
VIEWS = {"front": (0, 5.05, 1.0, 0.955), "q34": (30, 5.05, 1.0, 0.955), "side": (90, 5.05, 1.0, 0.955), "back": (180, 5.05, 1.0, 0.955),
         "q34b": (-30, 5.05, 1.0, 0.955), "face": (0, 1.0, 1.74, 1.73), "face34": (28, 1.0, 1.74, 1.73), "bust": (12, 2.0, 1.45, 1.4),
         "legs_side": (90, 2.6, 0.5, 0.45), "legs_back": (180, 1.45, 0.5, 0.45), "legs_front": (0, 2.6, 0.5, 0.45),
         "arm": (-40, 1.6, 1.2, 1.2)}
for nm in (K.opt(a, "--views") or "front,q34,side,back,q34b").split(","):
    yaw, d, cz, az = VIEWS[nm]
    studio(center)
    if nm.startswith(("face", "bust", "legs", "arm")):
        bpy.context.scene.render.resolution_x, bpy.context.scene.render.resolution_y = (1000, 1100) if nm.startswith("face") else (1100, 1100)
    r = math.radians(yaw)
    K.camera(Vector((math.sin(r) * d, -math.cos(r) * d, cz)), Vector((0, 0, az)), 85)
    out.append(K.render_to(os.path.join(OUT, f"{tag}_{nm}.png")))
if len(out) > 1:
    K.contact_sheet(out, os.path.join(OUT, f"{tag}_turntable.png"), cols=5, width=520)
# side by side: concept | render (front)
try:
    from PIL import Image
except ImportError:
    Image = None
c = TB.read_image(CONCEPT)
r_ = TB.read_image(out[0])
H = 1200
def fit(img, h):
    import numpy as _np
    ih, iw = img.shape[:2]
    w = int(iw * h / ih)
    ys = (_np.arange(h) * ih / h).astype(int); xs = (_np.arange(w) * iw / w).astype(int)
    return img[ys][:, xs]
A_ = fit(c[..., :3], H); B_ = fit(r_[..., :3], H)
canvas = np.ones((H, A_.shape[1] + B_.shape[1] + 20, 3), np.float32)
canvas[:, :A_.shape[1]] = A_
canvas[:, A_.shape[1] + 20:] = B_
TB.write_png(canvas, os.path.join(OUT, f"{tag}_vs_concept.png"), "RGB")
K.log("CONCEPT", os.path.join(OUT, f"{tag}_vs_concept.png"))
