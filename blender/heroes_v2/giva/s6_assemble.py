"""Stage 6: assemble the game meshes and build their corrective blend shapes.

  blender -b out/giva_bg.blend --python s6_assemble.py
Top = Top + Collar + CuffRight. Correctives (definitions in out/correctives.json, runtime convention of
CorrectiveShapes.cs) are computed per deforming mesh with CoR skinning on its own topology (Body is already done
in stage 2; Top, Pants, Gloves, Boots here); gear layered on the suit (straps, belts, cables) gets the suit's
rest-space deltas through a surface binding so layers never separate. Saves out/giva_asm.blend.
"""
import bpy, sys, os, json, math, importlib
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "lib"), HERE]
import numpy as np
import gv, deform
for m in (gv, deform):
    importlib.reload(m)
P = gv.P

rig = bpy.data.objects[gv.RIG]
DEFS = json.load(open(os.path.join(gv.OUT, "correctives.json")))


def join(target, others):
    objs = [bpy.data.objects[n] for n in others if n in bpy.data.objects]
    if not objs:
        return bpy.data.objects[target]
    bpy.ops.object.select_all(action="DESELECT")
    t = bpy.data.objects[target]
    for o in objs:
        o.select_set(True)
    t.select_set(True)
    bpy.context.view_layer.objects.active = t
    bpy.ops.object.join()
    return t


def mesh_correctives(o, defs, strength=None):
    me = o.data
    X = gv.basis_co(o)
    tris = gv.tri_index(me)
    names, W = gv.bone_weights(o)
    n_add = 0
    for d in defs:
        if d["bone"] not in names and not any(n in deform.descendants(rig, d["bone"]) for n in names):
            continue
        desc = deform.descendants(rig, d["bone"])
        cols = [j for j, n in enumerate(names) if n in desc]
        alpha = W[:, cols].sum(1) if cols else np.zeros(len(X))
        if not ((alpha > 1e-3) & (alpha < 1 - 1e-3)).any():
            continue
        delta = deform.cor_corrective(rig, X, W, names, tris, d["bone"], d["axis"], d["to"], d["from"] or None)
        k = strength(d) if strength else 1.0
        delta *= k
        if np.linalg.norm(delta, axis=1).max() < 2e-4:
            continue
        gv.add_shape(o, d["shape"], X + delta)
        n_add += 1
    gv.log(o.name, "correctives", n_add)


def transfer_correctives(o, src):
    """Rest-space corrective deltas of `src` (the suit) carried onto layered gear by a surface binding."""
    ks = src.data.shape_keys
    if not ks:
        return
    Xs = gv.basis_co(src)
    ts = gv.tri_index(src.data)
    Xo = gv.basis_co(o)
    b = gv.Binding(Xs, ts, Xo, 0.08)
    n = 0
    for k in ks.key_blocks[1:]:
        if not k.name.startswith("corr_"):
            continue
        co = np.empty(len(Xs) * 3, dtype=np.float32)
        k.data.foreach_get("co", co)
        d = b.transfer(co.reshape(-1, 3) - Xs)
        d[b.D > 0.06] = 0
        if np.abs(d).max() > 2e-4:
            gv.add_shape(o, k.name, Xo + d)
            n += 1
    gv.log(o.name, "correctives transferred from", src.name, n)


def transfer_shapes(o, src):
    ks = src.data.shape_keys
    if not ks:
        return
    Xs = gv.basis_co(src)
    ts = gv.tri_index(src.data)
    Xo = gv.basis_co(o)
    b = gv.Binding(Xs, ts, Xo, 0.08)
    for k in ks.key_blocks[1:]:
        co = np.empty(len(Xs) * 3, dtype=np.float32)
        k.data.foreach_get("co", co)
        d = b.transfer(co.reshape(-1, 3) - Xs)
        gv.add_shape(o, k.name, Xo + d)
    gv.log(o.name, "shapes transferred from", src.name, len(ks.key_blocks) - 1)


def strength(d):
    if "UpLeg" in d["bone"] and d["to"] > 100:
        return 0.5
    if "UpLeg" in d["bone"]:
        return 0.8
    return 1.0


def main():
    top = join("Top", ["Collar"])
    for o in (top, bpy.data.objects["Pants"], bpy.data.objects["Gloves"], bpy.data.objects["Boots"]):
        # drop stale correctives (they are rebuilt here)
        if o.data.shape_keys:
            for k in list(o.data.shape_keys.key_blocks[1:]):
                if k.name.startswith("corr_"):
                    o.shape_key_remove(k)
        mesh_correctives(o, DEFS, strength)
    pants = bpy.data.objects["Pants"]
    # glowing piping on the left leg: carries every shape of the pants (morphs + correctives), then joins them
    pip = bpy.data.objects.get("Piping")
    if pip is not None:
        transfer_shapes(pip, pants)
        pants = join("Pants", ["Piping"])
    # layered gear: deltas from the garment underneath (rigid pieces keep their single transform: the binding
    # deltas of a rigid piece are averaged so the plate moves as a whole)
    for name, src in (("Harness", top), ("ThighRig", pants), ("ShoulderR", top)):
        o = bpy.data.objects.get(name)
        if o is None:
            continue
        transfer_correctives(o, src)
        rigid_average(o)
    gv.save(os.path.join(gv.OUT, "giva_asm.blend"))


def rigid_average(o):
    me = o.data
    if not me.shape_keys or "pid" not in me.attributes:
        return
    pid = np.zeros(len(me.vertices))
    me.attributes["pid"].data.foreach_get("value", pid)
    fcls = np.zeros(len(me.polygons))
    me.attributes["cls"].data.foreach_get("value", fcls)
    vcls = np.full(len(me.vertices), -1.0)
    for f, c in zip(me.polygons, fcls):
        for v in f.vertices:
            vcls[v] = c
    X = gv.basis_co(o)
    for k in me.shape_keys.key_blocks[1:]:
        if not k.name.startswith("corr_"):
            continue
        co = np.empty(len(X) * 3, dtype=np.float32)
        k.data.foreach_get("co", co)
        D = co.reshape(-1, 3) - X
        for p_ in np.unique(pid):
            sel = pid == p_
            if o.name == "ShoulderR" and p_ <= o.get("flex_pids", 1):
                continue                         # the pauldron follows the corrected shoulder surface
            if np.isin(vcls[sel], (0.0, 3.0, 4.0, 6.0, 7.0)).all():
                D[sel] = D[sel].mean(0)
        k.data.foreach_set("co", (X + D).astype(np.float32).ravel())


main()
