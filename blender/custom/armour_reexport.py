"""Re-export armour FBX files from the saved build scenes (cache/armour_<cid>_<sid>.blend) after fixing unweighted
vertices; no geometry or texture changes.  blender -b --python blender/custom/armour_reexport.py -- <cid>:<set> ..."""
import bpy, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import armour

for spec in C.args():
    cid, sid = spec.split(":")
    bpy.ops.wm.open_mainfile(filepath=os.path.join(C.CACHE, f"armour_{cid}_{sid}.blend"))
    rig = bpy.data.objects[C.HEROES[cid]["name"]]
    obj = bpy.data.objects[f"{cid}_{sid}"]
    n = armour.fill_weights(obj)
    for i, m in enumerate(obj.data.materials):
        obj.data.materials[i] = bpy.data.materials.get(armour.SLOTS[i]) or bpy.data.materials.new(armour.SLOTS[i])
    C.export_fbx(os.path.join(armour.OUT_DIR, f"{cid}_{sid}.fbx"), [obj], armature=rig)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(C.CACHE, f"armour_{cid}_{sid}.blend"), compress=True)
    print("REEXPORT", cid, sid, "filled", n, [m.name for m in obj.data.materials])
