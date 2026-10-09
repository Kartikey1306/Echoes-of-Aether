"""Rebuild the committed Kael (git HEAD characters.py definition) as a MakeHuman-topology mesh and save its vertex
positions (same vertex order as BodyMH) to logs/mh_old.npz: the reference for refitting the old fitted hair cards.

  blender -b --python dump_old_mh.py
"""
import bpy, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kcommon as K
import numpy as np
import mpfb_build, meshutil
import characters_committed as CC

c = CC.CHARACTERS["kael"]
bpy.ops.wm.read_factory_settings(use_empty=True)
assets = {"eyebrows": c["eyebrows"], "eyelashes": c["eyelashes"], "skin": c["skin"]}
body = mpfb_build.build("Kael", c["phenotype"], c["targets"], assets)
rig = body.parent
co = meshutil.mix_co(body)
meshutil.bake_shape_keys(body)
meshutil.set_co(body, co)
del_groups = [m.vertex_group for m in body.modifiers if m.type == "MASK" and m.invert_vertex_group and m.vertex_group and m.vertex_group != "body"]
meshutil.delete_verts_in_groups(body, del_groups)
meshutil.delete_verts_not_in_group(body, "body")
co = K.get_co(body)
head = np.array(rig.matrix_world @ rig.data.bones["mixamorig:Head"].head_local)
np.savez(os.path.join(K.LOGS, "mh_old.npz"), co=co, head=head, faces=np.array([f for f in K.faces_of(body)], dtype=object), allow_pickle=True)
K.log("OLD MH", co.shape, "head", head.round(4))
