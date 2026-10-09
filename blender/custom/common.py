"""Shared helpers for the character customisation pipeline (blender/custom).

Everything here is new work for the customiser: hair library, tattoos, eyewear and armour sets for the heroes
KAEL (`kael`) and GIVA (asset id `lyra`, files `Lyra/*`). The character artist's pipeline (blender/scripts) is
used read-only; the helper modules we depend on are frozen in blender/custom/lib (snapshot) so concurrent edits
to blender/scripts never break these builds.

Coordinate conventions
  Blender: Z up, the hero faces -Y, metres.
  Export : FBX with axis_forward='-Z', axis_up='Y', FBX_SCALE_ALL, bake_space_transform=True (same as the heroes),
           i.e. FBX(x, y, z) = (x, z, -y) of Blender; Unity then mirrors X (handedness), consistently for every node.
"""
import bpy, bmesh, os, sys, json, math, time
import numpy as np
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
ROOT = os.path.abspath(os.path.join(HERE, ".."))                      # blender/
GAME = os.path.abspath(os.path.join(ROOT, ".."))
UNITY_ASSETS = os.path.join(GAME, "unity", "EchoesOfAether", "Assets")
UNITY_CHARS = os.path.join(UNITY_ASSETS, "Art", "Characters")
CUSTOM_OUT = os.path.join(UNITY_ASSETS, "Resources", "Characters", "Custom")
CACHE = os.path.join(HERE, "cache")
PREVIEWS = os.path.join(HERE, "previews")
MPFB_DATA = os.path.expanduser("~/Library/Application Support/Blender/5.2/extensions/.user/user_default/mpfb/data")
for d in (CACHE, PREVIEWS, CUSTOM_OUT):
    os.makedirs(d, exist_ok=True)

HEROES = {
    "kael": {"name": "Kael", "gender": "male", "tone": "medium", "hair": "#1d1714", "hair_preview": "#3a2a20",
             "skin": "#b98a6e", "glow": "#00e5ff", "glow2": "#ff2bd6"},
    "lyra": {"name": "Lyra", "gender": "female", "tone": "medium", "hair": "#2b1b14", "hair_preview": "#4a2f22",
             "skin": "#c79878", "glow": "#ff2bd6", "glow2": "#8a5bff"},
}

T0 = time.time()


def log(*a):
    print(f"[custom {time.time() - T0:7.1f}s]", *a, flush=True)


def args():
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def hx(h):
    return np.array([int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)])


def srgb2lin(c):
    c = np.asarray(c, np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def ss(e0, e1, x):
    t = np.clip((np.asarray(x, np.float64) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def nrm(v):
    v = np.asarray(v, np.float64)
    return v / max(np.linalg.norm(v), 1e-12)


def nrm_rows(v):
    v = np.asarray(v, np.float64)
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


# ----------------------------------------------------------------------------- reference scene


def ref_path(cid):
    return os.path.join(CACHE, f"{cid}_ref.blend")


def load_ref(cid):
    """Open the prepared reference scene (rig, full body with morph keys, exported Unity meshes prefixed U_)."""
    bpy.ops.wm.open_mainfile(filepath=ref_path(cid))
    return ref_objects(cid)


def ref_objects(cid):
    cname = HEROES[cid]["name"]
    rig = bpy.data.objects[cname]
    body = bpy.data.objects[cname + ".body"]
    return rig, body


def head_info(cid):
    with open(os.path.join(CACHE, f"{cid}_ref.json")) as f:
        return json.load(f)


def get_co(obj):
    a = np.empty(len(obj.data.vertices) * 3)
    obj.data.vertices.foreach_get("co", a)
    return a.reshape(-1, 3)


def set_co(obj, co):
    obj.data.vertices.foreach_set("co", np.asarray(co, np.float32).ravel())
    obj.data.update()


def tris(obj):
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


# ----------------------------------------------------------------------------- FBX space


# Blender -> FBX axis conversion used by the exporter (forward -Z, up Y): (x, y, z) -> (x, z, -y)
C_B2F = Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, -1, 0, 0), (0, 0, 0, 1)))


def rigid_matrix(cid, bone="mixamorig:Head"):
    """4x4 (Blender space) that maps a world-space (rest pose) Blender point to the coordinates a mesh must have in
    Blender so that, exported with the hero FBX settings at the scene root and parented in Unity to `bone` with an
    identity local transform, it lands back on that world point.

    FBX: v_file = H^-1 * C * p * s, where H is the bone's global bind matrix in the hero FBX (read by prep.py) and s
    the file unit scale. The exporter writes C * q * s for a root mesh vertex q, hence q = C^-1 * H^-1 * C * p
    (the scale cancels for the rotation part, translation is in file units / s)."""
    info = head_info(cid)
    b = info["bones"][bone]
    H = Matrix([b["bindpose"][i * 4:(i + 1) * 4] for i in range(4)])   # row-major, FBX file space
    s = info["unit_scale"]
    S = Matrix.Diagonal((s, s, s, 1.0))
    return C_B2F.inverted() @ S.inverted() @ H.inverted() @ S @ C_B2F


def export_fbx(path, objs, armature=None):
    """Hero FBX conventions. objs: meshes (and optionally the armature) to write."""
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.hide_set(False)
        o.hide_viewport = False
        o.select_set(True)
    if armature:
        armature.hide_set(False)
        armature.select_set(True)
        bpy.context.view_layer.objects.active = armature
    else:
        bpy.context.view_layer.objects.active = objs[0]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    final, path = path, os.path.join(os.path.dirname(path), "." + os.path.basename(path) + ".part.fbx")   # atomic (Unity may be importing)
    bpy.ops.export_scene.fbx(
        filepath=path, use_selection=True, object_types={"ARMATURE", "MESH"}, apply_scale_options="FBX_SCALE_ALL",
        axis_forward="-Z", axis_up="Y", bake_space_transform=True, use_mesh_modifiers=False, mesh_smooth_type="FACE",
        use_tspace=True, add_leaf_bones=False, use_armature_deform_only=True, bake_anim=False, path_mode="STRIP",
        embed_textures=False, use_custom_props=False)
    os.replace(path, final)
    return final


# ----------------------------------------------------------------------------- catalog fragments


def write_fragment(category, cid, entries):
    """Each build writes its catalog entries to cache/catalog_<category>_<cid>.json; catalog.py merges them."""
    p = os.path.join(CACHE, f"catalog_{category}_{cid}.json")
    with open(p, "w") as f:
        json.dump(entries, f, indent=1)
    import catalog
    catalog.merge()
    return p


# ----------------------------------------------------------------------------- PNG


def write_png(arr, path, mode=None):
    import texbake as TB
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = os.path.join(os.path.dirname(path), "." + os.path.basename(path) + ".part.png")
    TB.write_png(arr, tmp, mode)
    os.replace(tmp, path)


def read_png(path, size=None):
    import texbake as TB
    return TB.read_image(path, size)
