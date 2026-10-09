"""Re-import Anim_Male.fbx / Anim_Female.fbx and check take names, lengths and loop seams against clips_meta.json.

blender -b --python tools/anim/verify_fbx.py
"""
import json
import math
import os

import bpy

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ANIM = os.path.join(ROOT, "unity", "EchoesOfAether", "Assets", "Art", "Animations")
EXPECTED = ["land", "k_light1", "k_light2", "k_light3", "k_heavy", "l_quick1", "l_quick2", "l_heavy", "dash", "phase_step",
            "k_pulse", "k_ult", "l_echo", "l_ult", "aim_r", "fire_r", "aim_l", "fire_l", "hit", "stagger", "death", "interact",
            "pickup", "climb", "talk", "npc_crossed", "npc_hips", "npc_work", "npc_look", "npc_react", "wave", "sit",
            "kneel_work", "lie", "wake", "idle", "walk", "run", "sprint", "jump", "fall", "combat_idle"]
meta = json.load(open(os.path.join(ANIM, "clips_meta.json")))
ok = True
for style in ("Male", "Female"):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=os.path.join(ANIM, f"Anim_{style}.fbx"))
    rig = [o for o in bpy.data.objects if o.type == "ARMATURE"][0]
    acts = {a.name.split("|")[-1]: a for a in bpy.data.actions}
    m = meta[style.lower()]
    missing = [n for n in EXPECTED if n not in acts]
    extra = [n for n in acts if n not in EXPECTED]
    print(f"[verify] {style}: {len(acts)} takes, missing={missing} extra={extra}")
    ok &= not missing and not extra
    rig.animation_data_create()
    for n in EXPECTED:
        a = acts.get(n)
        if a is None:
            continue
        f0, f1 = a.frame_range
        dur = (f1 - f0) / 30.0
        md = m[n]["duration"]
        line = f"  {n:12s} frames {f0:.0f}-{f1:.0f} = {dur:.3f}s meta {md:.3f}s loop={m[n]['loop']}"
        if abs(dur - md) > 0.02:
            line += "  DURATION MISMATCH"
            ok = False
        if m[n]["loop"]:
            # seam: world-space pose difference between first and last frame (max bone angle, hips offset)
            rig.animation_data.action = a
            sc = bpy.context.scene
            sc.frame_set(int(f0))
            p0 = {pb.name: pb.matrix.copy() for pb in rig.pose.bones}
            sc.frame_set(int(f1))
            worst = 0.0
            for pb in rig.pose.bones:
                q = (p0[pb.name].to_quaternion().rotation_difference(pb.matrix.to_quaternion()))
                worst = max(worst, math.degrees(q.angle) if q.angle <= math.pi else 360 - math.degrees(q.angle))
            hips = [pb for pb in rig.pose.bones if pb.name.endswith("Hips")][0]
            dpos = (p0[hips.name].translation - hips.matrix.translation).length
            line += f"  seam {worst:.2f} deg / {dpos * 100:.2f} cm"
            if worst > 1.0 or dpos > 0.01:
                line += "  SEAM!"
                ok = False
        for e in m[n]["events"]:
            if not (0 <= e["t"] <= md + 1e-6):
                line += f"  EVENT OUT OF RANGE {e}"
                ok = False
        print(line)
print("[verify] RESULT", "OK" if ok else "PROBLEMS")
