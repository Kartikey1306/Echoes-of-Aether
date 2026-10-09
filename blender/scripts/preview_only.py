"""Render HD previews from a saved *_hd.blend: blender -b out/hd/<cid>_hd.blend --python preview_only.py -- <cid> <lights> [shots] [--eyes]"""
import bpy, sys, os
sys.path.insert(0, os.path.dirname(__file__))
import hero_hd, skin_hd, characters
a = sys.argv[sys.argv.index("--") + 1:]
cid = a[0]
tex_dir = os.path.join(hero_hd.UNITY, characters.CHARACTERS[cid]["name"], "Textures")
if "--eyes" in a:
    skin_hd.eye_textures(tex_dir)
if cid in hero_hd.CFG:
    cfg = hero_hd.CFG[cid]
    shots = a[2].split(",") if len(a) > 2 and not a[2].startswith("--") else ["front", "back", "q34", "face", "face34", "game"]
else:
    import npc_hd
    n = npc_hd.NPC[cid]
    cfg = {"palette": {"skin": n["skin"], "hair": n["tints"]["hair"], "eyes": n["eyes"], "glow": n["glow"], "glow2": n["glow2"],
                       "outfit": n["outfit"], "accent": "#24262b", "armor": "#8a8a8a"}, "preview_tone": "medium", "default_hair": "default",
           "show_facial": bool(n.get("beard"))}
    hero_hd.CFG[cid] = cfg
    shots = a[2].split(",") if len(a) > 2 and not a[2].startswith("--") else ["front", "q34", "back", "face34"]
hero_hd.previews(cid, cfg, a[1].split(","), shots)
