#!/usr/bin/env python3
"""Compose the before/after posture contact sheet from blender/anim/posture_sheet.py frames.

  python3 tools/anim/posture_sheet_compose.py <frames_root> <out.png>

<frames_root> holds male_before/, male_after/, female_before/, female_after/ with <clip>_<view>.png. Rows per hero:
before (front 3/4), after (front 3/4), before (side), after (side); one column per clip (crouch_idle / crouch_walk are new, so their "before" cells are empty).
"""
import os
import sys

from PIL import Image, ImageDraw

root, out = sys.argv[1], sys.argv[2]
CLIPS = ["idle", "talk", "walk", "run", "sprint", "combat_idle", "npc_crossed", "k_light1", "k_heavy", "l_heavy", "crouch_idle", "crouch_walk"]
CW, CH, LW, TH = 180, 240, 150, 26
rows = []
for style, hero in (("male", "Kael (male set)"), ("female", "Giva (female set)")):
    for view, vname in (("q34", "front 3/4"), ("side", "side")):
        for phase in ("before", "after"):
            rows.append((f"{style}_{phase}", view, f"{hero}\n{phase.upper()}\n{vname}", phase))
sheet = Image.new("RGB", (LW + CW * len(CLIPS), TH + CH * len(rows)), (24, 26, 30))
d = ImageDraw.Draw(sheet)
for j, c in enumerate(CLIPS):
    d.text((LW + j * CW + 8, 7), c, fill=(230, 230, 230))
for i, (folder, view, label, phase) in enumerate(rows):
    y = TH + i * CH
    d.rectangle([0, y, LW - 4, y + CH - 2], fill=(60, 34, 34) if phase == "before" else (30, 58, 40))
    d.multiline_text((8, y + 8), label, fill=(240, 240, 240), spacing=4)
    for j, c in enumerate(CLIPS):
        p = os.path.join(root, folder, f"{c}_{view}.png")
        if os.path.exists(p):
            sheet.paste(Image.open(p).convert("RGB").resize((CW, CH)), (LW + j * CW, y))
sheet.save(out)
print("wrote", out, sheet.size)
