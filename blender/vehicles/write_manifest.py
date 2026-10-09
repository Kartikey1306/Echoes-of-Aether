"""Write Assets/Art/Vehicles/manifest.json (same schema as the environment kit manifest, read by
EnvLibraryBuilder) and VEHICLES.md from out/records/*.json, the material registry and the baked texture state.

python3 write_manifest.py
"""
import datetime
import json
import os

import vmatdefs as MD
import vpaths

ORDER = ["CyberCar_Coupe", "CyberCar_Sedan", "CyberCar_Taxi", "CyberVan", "CyberBike", "HoverCar_A", "HoverCar_B", "HoverTruck",
         "CyberCar_Sedan_Wrecked", "CyberVan_Burnt"]

DESCRIPTIONS = {
    "CyberCar_Coupe": "Cab-forward wedge supercar: one rising line from the blade nose over the canopy, blade character line, deep side cove into a rear intake, scissor-door seams, carbon roof/sills/splitter/diffuser/arch lips, hood vents, floating blade wing, fastback louvres, full-width LED bars front and rear, neon fender blades and exhaust-port rings, sill + nose underglow, 21in aero-disc wheels with neon rings.",
    "CyberCar_Sedan": "Armoured executive sedan: long hood, faceted creased panels, high armoured beltline with slit glass, chrome window line, chrome spine over hood/roof/boot, vertical chrome grille, twin slit headlights + DRL bar, rear light blade, bolt-on door armour, multi-spoke wheels.",
    "CyberCar_Taxi": "Compact upright cab: yellow body over black lower livery, black roof/pillars, checker band decals, roof holo-sign frame (veh_holo_sign both sides + neon cap strip), sliding rear door seams, light-bar face, rubber bumpers, six-spoke black wheels.",
    "CyberVan": "Forward-control utility van: chamfered box, raked cab glass, sliding cargo door (right side) + rear barn doors, louvred side vents, tubular roof rack with cargo cases and a light bar, amber hazard beacons + side markers, fleet markings, heavy 8-lug steel wheels.",
    "CyberBike": "Heavy hubless-wheel motorcycle: low lofted fairing hugging the wheel tops, static inner bearing C-arms, chrome fork blades, single-sided swingarm, battery heat-sink fins, glowing rim bands, neon side stripes, belly underglow, clip-ons and a small screen.",
    "HoverCar_A": "Spinner-style flyer: long tapered body, raised rear deck, canopy glasshouse, four thruster pods in recessed bays (Thruster_FL/FR/RL/RR), roof beacon bar, tail fins with strobes, nav lights, light bars.",
    "HoverCar_B": "Compact two-seat flyer: teardrop pod with a full bubble canopy, two big ducted fans on side pylons (Thruster_L/R, tilt) and two rear pods (Thruster_RL/RR), dorsal fin strobe.",
    "HoverTruck": "Heavy flying cargo hauler (~9.5 m): faceted cab with wraparound visor, ribbed cargo container with fleet markings, rear doors with lock bars, six thruster pods, roof hazard beacons, nav lights, cab light bars.",
    "CyberCar_Sedan_Wrecked": "Wrecked armoured sedan (static prop): crumpled front, dented roof and doors, cracked/shattered glass, rust + scorch paint, front-left wheel missing (rests on the hub), flat front-right tyre, debris.",
    "CyberVan_Burnt": "Fire-gutted van shell (static prop): charred steel with ash and heat rust, windows burst open, sagging roof, tyres burnt away (sits on the rims).",
}


def mat_entry(name, baked):
    d = MD.REGISTRY[name]
    e = {"kind": "baked" if d["kind"] in ("baked",) else d["kind"], "shader": "Universal Render Pipeline/Lit", "label": d.get("label", "")}
    u = d.get("unity", {})
    e["surface"] = u.get("surface", "Opaque")
    if u.get("blend"):
        e["blend"] = u["blend"]
    if u.get("cull"):
        e["cull"] = u["cull"]
    if d["kind"] == "param":
        e.update({k: u[k] for k in ("baseColor", "metallic", "smoothness") if k in u})
        return e
    tile = d.get("tile")
    e["uvMode"] = d["uv"]
    e["tileSizeMeters"] = tile
    e["tiling"] = [round(1.0 / tile, 6)] * 2 if tile else [1.0, 1.0]
    tex = {c: MD.tex_path(name, c) for c in MD.channels(name)}
    e["textures"] = tex
    e["texturesAssetPath"] = {c: "Assets/Art/Vehicles/" + p for c, p in tex.items()}
    e["textureSize"] = d["res"]
    e["maxTextureSize"] = {"desktop": min(2048, d["res"]), "webgl": min(1024, d["res"])}
    e["normalScale"] = 1.0
    e["occlusionStrength"] = 1.0
    if d["kind"] == "tint":
        e["sharesMapsWith"] = d["parent"]
    if d.get("emissive"):
        e["emissive"] = True
        e["emissionColor"] = [1.0, 1.0, 1.0]
        e["emissionTint"] = d.get("emission")
        e["emissionIntensity"] = d.get("emissionIntensity", 1.0)
        e["animate"] = "drive _EmissionColor = white * intensity (0 = off); each light type is its own slot"
    if d.get("clearCoat"):
        e["clearCoat"] = {"mask": 1.0, "smoothness": 0.95, "note": "optional: URP Complex Lit clear coat; Lit works without it"}
    st = baked.get(name, {}).get("stats")
    if st:
        e["stats"] = st
    return e


def main():
    recs = {}
    for f in os.listdir(vpaths.RECORDS):
        if f.endswith(".json"):
            r = json.load(open(os.path.join(vpaths.RECORDS, f)))
            recs[r["name"]] = r
    order = [n for n in ORDER if n in recs] + sorted(n for n in recs if n not in ORDER)
    baked = json.load(open(os.path.join(vpaths.OUT, "materials_baked.json")))
    verify = {}
    vp = os.path.join(vpaths.OUT, "verify_report.json")
    if os.path.exists(vp):
        verify = json.load(open(vp))
    used = []
    for n in order:
        for m in recs[n]["materials"]:
            if m not in used:
                used.append(m)
    mats = {m: mat_entry(m, baked) for m in sorted(used, key=lambda x: list(MD.REGISTRY).index(x))}
    assets = []
    for n in order:
        r = dict(recs[n])
        r.pop("fbxBytes", None)
        r["description"] = DESCRIPTIONS.get(n, "")
        r["zones"] = []
        r["fbxCheck"] = "ok" if verify.get(n, {}).get("ok") else ("FAIL: " + "; ".join(verify[n]["errors"]) if n in verify else "unverified")
        assets.append(r)
    tex_bytes = 0
    for root, _, files in os.walk(vpaths.TEXTURES):
        tex_bytes += sum(os.path.getsize(os.path.join(root, f)) for f in files if f.endswith(".png"))
    fbx_bytes = sum(os.path.getsize(os.path.join(vpaths.MODELS, f)) for f in os.listdir(vpaths.MODELS) if f.endswith(".fbx"))
    man = {
        "name": "Echoes of Aether - cyberpunk vehicle kit",
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "generator": "blender/vehicles (Blender 5.2, headless, procedural). Rebuild: see VEHICLES.md",
        "conventions": {
            "units": "metres; FBX exported with apply_scale_options=FBX_SCALE_ALL, bake_space_transform=True, axis_forward=-Z, axis_up=Y -> import at scale 1, identity rotation",
            "axes": "Unity Y up, vehicle FRONT = +Z, right = +X. Pivot = ground centre (bounds centre in X/Z, y = 0 at the lowest point: tyres / thruster pods / hull).",
            "hierarchy": "<Name>_LOD0/1/2 body meshes at the root; animated parts are empties at their pivot (Wheel_FL/FR/RL/RR, Wheel_F/R for the bike, Thruster_* for flyers) each with <Part>_LOD0/1/2 mesh children at identity local transform.",
            "lods": "LOD1 ~40% and LOD2 ~12% of LOD0 triangles (body + parts). Assign each <Part>_LODn renderer to LOD n of the root LODGroup.",
            "uv0": "World-scale metres (box projection) for tiling materials; tiling = 1 / tileSizeMeters. 'fit' materials (veh_decal atlas, veh_navlight, veh_holo_sign) use authored 0..1 UVs.",
            "uv1": "Not authored.",
            "normals": "Custom split normals (smooth, sharp > 38 deg) exported; ModelImporter normals = Import, tangents = Calculate Mikktspace.",
            "materialSlots": "Material slot names == material names below (all prefixed veh_); remap FBX materials by name.",
            "colliders": "Suggested box colliders in Unity local space (center/size in metres).",
            "lights": "Anchor points (Unity local) for spot/point lights: headlight / taillight centres plus every light unit under 'all'.",
            "textures": {
                "BaseColor": "sRGB RGB (RGBA for veh_glass_cracked / veh_holo_sign: A = opacity). URP Lit _BaseMap.",
                "Normal": "Tangent-space, OpenGL (+Y up) = Unity convention. Import as Normal map. URP Lit _BumpMap.",
                "MaskMap": "Linear RGBA: R = metallic, G = ambient occlusion, B = unused (0), A = smoothness. URP Lit _MetallicGlossMap, Smoothness Source = Metallic Alpha, _Smoothness = 1. URP samples occlusion from .g if MaskMap is also set as _OcclusionMap.",
                "Emission": "sRGB RGB emission colour (emissive materials only). URP Lit _EmissionMap, _EmissionColor = white * emissionIntensity (HDR).",
            },
        },
        "textureImport": {
            "BaseColor": {"sRGB": True, "textureType": "Default", "alphaSource": "FromInput"},
            "Normal": {"textureType": "NormalMap"},
            "MaskMap": {"sRGB": False, "textureType": "Default"},
            "Emission": {"sRGB": True, "textureType": "Default"},
            "all": {"wrapMode": "Repeat (fit materials: Clamp)", "maxSize": "desktop 2048 (body paints / wreck / burnt are 2K), WebGL 1024", "mipmaps": True, "anisoLevel": 4},
        },
        "urpLitMapping": {
            "_BaseMap": "BaseColor", "_BaseColor": "white (or 'baseColor' for param materials)", "_BaseMap_ST": "tiling",
            "_MetallicGlossMap": "MaskMap", "_Metallic": 1.0, "_Smoothness": 1.0, "_SmoothnessTextureChannel": 0,
            "_BumpMap": "Normal", "_OcclusionMap": "MaskMap (G) - optional", "_EmissionMap": "Emission",
            "_EmissionColor": "emissionColor * emissionIntensity (enable _EMISSION)",
        },
        "materials": mats,
        "emissiveMaterials": [m for m in mats if mats[m].get("emissive")],
        "assets": assets,
        "stats": {"assets": len(assets), "materials": len(mats), "textureMB": round(tex_bytes / 1e6, 1), "fbxMB": round(fbx_bytes / 1e6, 1)},
    }
    out = os.path.join(vpaths.UNITY_VEH, "manifest.json")
    json.dump(man, open(out, "w"), indent=1)
    print("wrote", out, man["stats"])
    write_md(man)


def write_md(man):
    L = []
    a = L.append
    st = man["stats"]
    a("# Cyberpunk vehicle kit (Echoes of Aether, Unity 6 URP)")
    a("")
    a(f"Generated by `blender/vehicles` (Blender 5.2 headless, fully procedural: lofted subdivision shells, bmesh, modifiers, "
      f"booleans; textures generated by script). Data source of truth: `manifest.json` next to this file (same schema as "
      f"`Assets/Art/Environment/manifest.json`, so `EnvLibraryBuilder` builds the materials and prefabs).")
    a("")
    a(f"{st['assets']} vehicles, {st['materials']} materials, textures {st['textureMB']} MB, FBX {st['fbxMB']} MB. No real brands, logos or real-world text: every badge, plate and sign uses an invented glyph script.")
    a("")
    a("## Line-up")
    a("")
    a("| Vehicle | Tris LOD0 / LOD1 / LOD2 | Size X x Y x Z (m) | Animated parts | Check |")
    a("|---|---|---|---|---|")
    for r in man["assets"]:
        t = r["tris"]
        parts = ", ".join(p["name"] for p in r["animatedParts"]) or "none (static prop)"
        a(f"| `{r['name']}` | {t['LOD0']} / {t['LOD1']} / {t['LOD2']} | {r['size'][0]:.2f} x {r['size'][1]:.2f} x {r['size'][2]:.2f} | {parts} | {r['fbxCheck'].split(':')[0]} |")
    a("")
    for r in man["assets"]:
        a(f"- **{r['name']}**: {r['description']}")
    a("")
    a("## Conventions")
    a("")
    for k, v in man["conventions"].items():
        if isinstance(v, str):
            a(f"- **{k}**: {v}")
    a("")
    a("FBX hierarchy (example):")
    a("")
    a("```")
    a("CyberCar_Coupe.fbx")
    a("  CyberCar_Coupe_LOD0 / _LOD1 / _LOD2      body (root, identity)")
    a("  Wheel_FL (empty @ wheel centre)          -> Wheel_FL_LOD0 / _LOD1 / _LOD2")
    a("  Wheel_FR, Wheel_RL, Wheel_RR             (same)")
    a("HoverCar_A.fbx: ... Thruster_FL/FR/RL/RR (empty @ pod pivot) -> Thruster_XX_LOD0..2")
    a("```")
    a("")
    a("## Materials")
    a("")
    a("| Material | Kind | Tile (m) | Maps | Emission | Notes |")
    a("|---|---|---|---|---|---|")
    for n, d in man["materials"].items():
        maps = ", ".join(d.get("textures", {}).keys()) or "-"
        em = f"x{d['emissionIntensity']} tint {d.get('emissionTint')}" if d.get("emissive") else "-"
        tile = d.get("tileSizeMeters") or ("fit" if d.get("textures") else "-")
        extra = []
        if d.get("sharesMapsWith"):
            extra.append(f"shares Normal with `{d['sharesMapsWith']}`")
        if d.get("surface") == "Transparent":
            extra.append(f"transparent {d.get('blend', 'Alpha')}")
        if d["kind"] == "param":
            extra.append(f"baseColor {d.get('baseColor')}, smoothness {d.get('smoothness')}")
        a(f"| `{n}` | {d['kind']} | {tile} | {maps} | {em} | {d.get('label', '')}{'; ' if extra else ''}{'; '.join(extra)} |")
    a("")
    a(f"Emissive slots (each its own material so Unity can animate them independently): {', '.join('`' + m + '`' for m in man['emissiveMaterials'])}.")
    a("")
    a("## Notes for the Unity integrator")
    a("")
    a("- **Build**: EOA -> Build Environment Library already processes `Assets/Art/Vehicles/manifest.json` (materials -> `Resources/Env/Materials/veh_*.mat`, prefabs with LODGroup + box colliders). All vehicle materials are prefixed `veh_` so they never collide with the environment kit.")
    a("- **LODGroup with nested parts**: the body LOD meshes are root siblings; wheel / thruster LOD meshes are children of their pivot empties. If the auto-generated LODGroup only lists the body renderers, add each `<Part>_LODn` renderer to LOD n (one LODGroup on the root). The parts are counted in the manifest triangle totals.")
    a("- **Wheels**: rotate `Wheel_*` about local X to roll (positive = forward roll for all four wheels); yaw the front pivots about local Y to steer. Calipers are in the body at the top of each disc, so steering never clips them. Wheel radius is in `animatedParts[].radius`.")
    a("- **Thrusters**: `Thruster_*` pivots sit at the pod's centre; nozzles face -Y. Tilt them about local X/Z for banking, and pulse `veh_thruster` emission (x6 HDR default) with throttle. HoverCar_B's `Thruster_L/R` are large ducted fans meant to tilt +-90 deg for forward flight. The pivot is the ground centre of the hull's lowest point (pods), so set the hover height in code.")
    a("- **Lights**: `veh_headlight`, `veh_taillight`, `veh_underglow`, `veh_neon`, `veh_hazard`, `veh_thruster`, `veh_navlight`, `veh_holo_sign` are separate slots: drive `_EmissionColor` (white x intensity) per material or via MaterialPropertyBlock per renderer. Brake = raise `veh_taillight` from 4.5 to ~9; hazards = blink `veh_hazard`; nav strobes = blink `veh_navlight`. `lights.headlight/taillight` give anchor points for real Light components (spot lights at the head anchors, small red point lights at the tail).")
    a("- **Glass**: `veh_glass` is transparent (alpha 0.62, double-sided) over a modelled cabin (tub, seats, dash with a neon strip, steering yoke). Keep it in the transparent queue; shadows off for glass renderers.")
    a("- **Paint**: `veh_paint_*` share one flake normal map and have their own MaskMap (metal flake in R/A). For a stronger clear-coat look use URP Complex Lit with Clear Coat (mask 1, smoothness 0.95); plain Lit also works. Any paint can go on any vehicle by swapping the paint slot.")
    a("- **Wrecks**: `CyberCar_Sedan_Wrecked` and `CyberVan_Burnt` are static props (wheels merged into the body, no animated parts). The wreck keeps its light slots (default off; a flickering tail light reads well). The burnt van uses only `veh_burnt`.")
    a("- **Colliders**: the manifest gives one to three boxes per vehicle (hull + cabin, plus duct pylons for HoverCar_B). Use a convex MeshCollider on LOD2 if you need tighter collision.")
    a("")
    a("## Rebuild")
    a("")
    a("```")
    a("cd blender/vehicles")
    a("B=/Applications/Blender.app/Contents/MacOS/Blender")
    a("python3 build_materials.py                                   # textures (numpy, tileable) -> Textures/")
    a("$B -b --factory-startup --python build_vehicles.py --        # all FBX + out/records/*.json  (or list names)")
    a("$B -b --factory-startup --python verify_fbx.py --            # re-import every FBX, check names/transforms/sizes/LODs/slots")
    a("python3 write_manifest.py                                    # manifest.json + VEHICLES.md")
    a("$B -b --factory-startup --python render_previews.py -- CyberCar_Coupe --scenes street,studio --views fr,rr")
    a("```")
    a("")
    a("Previews: `blender/vehicles/previews/` (Cycles + Metal, AgX; neon wet street and dark studio; 3/4 front and rear).")
    open(os.path.join(vpaths.UNITY_VEH, "VEHICLES.md"), "w").write("\n".join(L) + "\n")
    print("wrote VEHICLES.md")


if __name__ == "__main__":
    main()
