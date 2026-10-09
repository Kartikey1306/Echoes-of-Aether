"""Merge material bake info + asset records into Assets/Art/Environment/manifest.json and ENV_ASSETS.md.

  python3 write_manifest.py        (plain Python 3, no Blender needed)
"""
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import envpaths  # noqa: E402
import matdefs  # noqa: E402

CONVENTIONS = {
    "units": "metres; FBX exported with apply_scale_options=FBX_SCALE_ALL, bake_space_transform=True, axis_forward=-Z, axis_up=Y -> import at scale 1, identity rotation",
    "axes": "Unity Y up. Asset FRONT faces +Z. Vehicles: long axis Z, front at +Z. Walls/barriers/benches/railings: long axis X, faces +/-Z.",
    "pivot": "base-centre unless the asset's 'pivot' field says otherwise (back-centre, top-centre, foot, centre, hinge, wall-base, ...)",
    "lods": "Each FBX holds <Name>_LOD0, <Name>_LOD1 (and <Name>_LOD2 for assets over 5k tris, see meshes) as siblings -> Unity's importer builds a LODGroup automatically. LOD1 is ~25-45% of LOD0 tris (fewer segments, no bevels, no small details); LOD2 ~10-15% (massing + glazing for buildings). lodTransitions has one value per LOD (last = cull).",
    "uv0": "World-scale metres for tiling materials (1 UV unit = 1 m, box/cylindrical projection per part, with a per-asset random offset). "
           "Material tiling = 1/tileSizeMeters. 'fit' materials (panels, screens, windows) get 0..1 per face; 'strip' materials get U = metres along the strip, V = 0..1 across.",
    "uv1": "Not authored: enable 'Generate Lightmap UVs' in the ModelImporter if baking lightmaps.",
    "normals": "Custom split normals (weighted, sharp > 50 deg) are exported; set ModelImporter normals = Import, tangents = Calculate Mikktspace.",
    "materialSlots": "Material slot names == material names below; remap FBX materials by name to Assets/Art/Environment/Materials/<name>.mat",
    "colliders": "Suggested colliders in Unity local space (center/size in metres). 'mesh' = use a MeshCollider on LOD1; 'none' = no collider needed.",
    "textures": {
        "BaseColor": "sRGB RGB (RGBA for 'grating': A = cutout mask). URP Lit _BaseMap.",
        "Normal": "Tangent-space, OpenGL convention (+Y = green up) = Unity's convention. Import as Normal map. URP Lit _BumpMap.",
        "MaskMap": "Linear RGBA: R = metallic, G = ambient occlusion, B = height (0..1, 'depth' metres), A = smoothness (1 - roughness). "
                   "URP Lit: assign to _MetallicGlossMap (reads R metallic + A smoothness; Smoothness Source = Metallic Alpha, _Smoothness = 1). "
                   "Same layout as the HDRP mask map except B = height instead of detail mask.",
        "Occlusion": "Linear greyscale AO (identical to MaskMap.G). URP Lit _OcclusionMap (URP samples .g, so the MaskMap could be used too).",
        "Emission": "sRGB RGB emission colour (emissive materials only). URP Lit _EmissionMap, _EmissionColor = white * emissionIntensity (HDR).",
    },
}


def lod_hint(size, cat, nlods=2):
    """Suggested LODGroup screen-relative transition heights: one per LOD (the last one is the cull height)."""
    m = max(size)
    if cat in ("building", "skyline"):
        return [0.25, 0.08, 0.0] if nlods == 3 else [0.12, 0.0]
    if cat in ("structure", "facade") and m >= 3.9:
        return [0.25, 0.08, 0.0] if nlods == 3 else [0.12, 0.0]
    if m < 1.5:
        return [0.3, 0.1, 0.02] if nlods == 3 else [0.3, 0.03]
    if m < 5:
        return [0.3, 0.1, 0.01] if nlods == 3 else [0.22, 0.012]
    return [0.25, 0.08, 0.004] if nlods == 3 else [0.15, 0.004]


def main():
    baked = json.load(open(os.path.join(envpaths.STATE, "materials_baked.json")))
    assets = json.load(open(os.path.join(envpaths.STATE, "assets.json")))
    reg = matdefs.REGISTRY
    mats = {}
    for name, d in reg.items():
        u = dict(d.get("unity", {}))
        if d["kind"] == "param":
            mats[name] = {"kind": "param", "shader": "Universal Render Pipeline/Lit", "surface": u.pop("surface", "Opaque"), **u}
            continue
        par = reg[d["parent"]] if d["kind"] == "tint" else d
        b = baked.get(name, {})
        tile = par["tile"]
        uv = par.get("uv", "world")
        tiling = [round(1 / tile, 6), round(1 / tile, 6)] if uv in ("world", "world0") else ([round(1 / tile, 6), 1.0] if uv == "strip" else [1.0, 1.0])
        pu = dict(par.get("unity", {}))
        pu.update(u)
        e = {
            "kind": d["kind"],
            "shader": "Universal Render Pipeline/Lit",
            "surface": pu.pop("surface", "Opaque"),
            "uvMode": uv,
            "tileSizeMeters": tile if uv != "fit" else None,
            "tiling": tiling,
            "textures": b.get("textures", {}),
            "heightDepthMeters": par.get("depth"),
            "textureSize": b.get("res", 1024),
            "maxTextureSize": {"desktop": b.get("res", 1024), "webgl": min(1024, b.get("res", 1024))},
            "normalScale": 1.0,
            "occlusionStrength": 1.0,
        }
        if d["kind"] == "tint":
            e["sharesMapsWith"] = d["parent"]
        if "Emission" in e["textures"]:
            e["emissionColor"] = [1.0, 1.0, 1.0]
            e["emissionIntensity"] = pu.pop("emissionIntensity", 1.0)
            pu.pop("emission", None)
        e.update(pu)
        if "stats" in b:
            e["stats"] = b["stats"]
        mats[name] = e
    recs = sorted(assets.values(), key=lambda r: (r["category"], r["name"]))
    cpath = os.path.join(envpaths.STATE, "fbx_check.json")
    checks = json.load(open(cpath)) if os.path.exists(cpath) else {}
    for r in recs:
        r["lodTransitions"] = lod_hint(r["size"], r["category"], len(r["meshes"]))
        if r["name"] in checks:
            r["fbxCheck"] = "ok" if checks[r["name"]]["ok"] else checks[r["name"]]["issues"]
    zones = {}
    for r in recs:
        for z in r.get("zones", []):
            zones.setdefault(z, []).append(r["name"])
    tex_bytes = 0
    for root, _, files in os.walk(envpaths.TEXTURES):
        for f in files:
            if f.endswith(".png"):
                tex_bytes += os.path.getsize(os.path.join(root, f))
    fbx_bytes = 0
    for root, _, files in os.walk(envpaths.MODELS):
        for f in files:
            if f.endswith(".fbx"):
                fbx_bytes += os.path.getsize(os.path.join(root, f))
    dpath = os.path.join(envpaths.STATE, "decals.json")
    decals = json.load(open(dpath)) if os.path.exists(dpath) else {}
    for root, _, files in os.walk(os.path.join(envpaths.UNITY_ENV, "Decals")):
        for f in files:
            if f.endswith(".png"):
                tex_bytes += os.path.getsize(os.path.join(root, f))
    manifest = {
        "name": "Echoes of Aether - Aether-9 environment kit",
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "generator": "blender/env (Blender 5.2, headless). Rebuild: see ENV_ASSETS.md",
        "conventions": CONVENTIONS,
        "textureImport": {
            "BaseColor": {"sRGB": True, "textureType": "Default", "alphaSource": "FromInput", "alphaIsTransparency": False},
            "Normal": {"textureType": "NormalMap"},
            "MaskMap": {"sRGB": False, "textureType": "Default"},
            "Occlusion": {"sRGB": False, "textureType": "Default", "singleChannel": "Red"},
            "Emission": {"sRGB": True, "textureType": "Default"},
            "all": {"wrapMode": "Repeat (fit materials: Clamp)", "maxSize": "per material: materials.<name>.maxTextureSize (desktop 2048 for the HD set, WebGL 1024)",
                    "mipmaps": True, "anisoLevel": 4,
                    "webglCompression": "ASTC/ETC2 or DXT per platform; normal maps BC5 where available"},
        },
        "urpLitMapping": {
            "_BaseMap": "BaseColor", "_BaseColor": "white (or 'baseColor' for param materials)", "_BaseMap_ST": "tiling (shared by all maps)",
            "_MetallicGlossMap": "MaskMap", "_Metallic": 1.0, "_Smoothness": 1.0, "_SmoothnessTextureChannel": 0,
            "_BumpMap": "Normal", "_BumpScale": "normalScale", "_OcclusionMap": "Occlusion", "_OcclusionStrength": "occlusionStrength",
            "_EmissionMap": "Emission", "_EmissionColor": "emissionColor * emissionIntensity (enable _EMISSION)",
            "keywords": ["_METALLICSPECGLOSSMAP", "_NORMALMAP", "_OCCLUSIONMAP", "_EMISSION (emissive only)", "_ALPHATEST_ON (alphaClip)"],
        },
        "materials": mats,
        "prototypeMaterialMap": matdefs.PROTO_MAP,
        "assets": recs,
        "decals": [decals[k] for k in sorted(decals)],
        "zones": zones,
        "stats": {"assets": len(recs), "materials": len(mats), "decals": len(decals), "textureMB": round(tex_bytes / 1e6, 1),
                  "fbxMB": round(fbx_bytes / 1e6, 1),
                  "textures2K": sorted(n for n, e in mats.items() if e.get("textureSize", 0) >= 2048)},
    }
    out = os.path.join(envpaths.UNITY_ENV, "manifest.json")
    json.dump(manifest, open(out, "w"), indent=1)
    print("wrote", out, manifest["stats"])
    write_md(manifest)


def write_md(m):
    L = []
    w = L.append
    w("# Aether-9 environment kit (Echoes of Aether, Unity 6 URP)\n")
    w("Generated by `blender/env` (Blender 5.2 headless, fully scripted). Data source of truth: `manifest.json` next to this file.\n")
    w(f"{m['stats']['assets']} assets, {m['stats']['materials']} materials, textures {m['stats']['textureMB']} MB, FBX {m['stats']['fbxMB']} MB.\n")
    w("## Art direction (cyberpunk restyle)\n")
    w("Rain-soaked cyberpunk megacity at night: grimy industrial base materials (wet concrete / asphalt / paving with puddles, dark glossy paint, "
      "scratched chrome, carbon panels, grimy tiles, rusted steel) with designed emissive accents: neon tubes (`emit_neon_*`), LED strips "
      "(`emit_strip_*`), light boxes (`emit_panel_*`), LED ad screens (`screen_ad_*`, invented glyphs only - no real words, brands or logos), "
      "holograms (`holo_*`) and skyline window grids (`skyline_windows_*`). Neon palette (sRGB): magenta #ff2bd6, hot pink #ff4f9a, cyan #00e5ff, "
      "electric blue #3d7bff, acid yellow #ffe14d, violet #9b5cff. Everything is procedural (Blender node bakes + numpy); no AI images.\n")
    w("Emissive slot rule: every light-emitting slot is an `emit_*` material (the zone code switches `emit_*` slots for power on/off and the importer "
      "disables shadows on emissive-only renderers). Assets with neon/light carry `light`/`lights` anchors (Unity local) and often `glowMaterial` "
      "so the zone code can add matching point lights; screens carry `screen`/`screens` rects for RenderTextures/animation.\n")
    w("## Conventions\n")
    c = m["conventions"]
    for k in ("units", "axes", "pivot", "lods", "uv0", "uv1", "normals", "materialSlots", "colliders"):
        w(f"- **{k}**: {c[k]}")
    w("\nBlender to Unity axis mapping used by the scripts: Blender +X -> Unity -X, Blender +Y -> Unity -Z, Blender +Z -> Unity +Y "
      "(assets are modelled facing Blender -Y).\n")
    w("## Texture channel layout\n")
    w("| Texture | Format | Content |\n|---|---|---|")
    for k, v in c["textures"].items():
        w(f"| `<name>_{k}.png` | {'sRGB' if k in ('BaseColor', 'Emission') else 'linear'} | {v} |")
    w("\nTextures are 2048 px for the HD surface set (see Texture budget) and 1024 px otherwise; PNG, tileable (procedural noise is evaluated on a 4D torus so every map wraps seamlessly). "
      "Normal maps are derived from the baked height in metres, so bump strength is physically scaled to the tile size. "
      "Tint variants (e.g. `metal_painted_red`) only have their own BaseColor and reuse the parent's Normal / MaskMap / Occlusion.\n")
    w("### URP Lit setup per textured material\n")
    w("```\n_BaseMap = BaseColor          _BaseColor = (1,1,1,1)        _BaseMap_ST = (tiling.x, tiling.y, 0, 0)\n"
      "_MetallicGlossMap = MaskMap   _Smoothness = 1               Smoothness source = Metallic Alpha (_SmoothnessTextureChannel = 0)\n"
      "_BumpMap = Normal (Normal map import)                     _OcclusionMap = Occlusion\n"
      "_EmissionMap = Emission      _EmissionColor = white * emissionIntensity (HDR), keyword _EMISSION\n"
      "grating: Alpha Clipping on, threshold 0.5, Render Face = Both.  tarp / glass: Render Face = Both.\n```\n")
    w("## Materials\n")
    w("| Material | Kind | UV | Tile (m) | Tiling | Notes |\n|---|---|---|---|---|---|")
    for n, e in m["materials"].items():
        if e["kind"] == "param":
            note = ", ".join(f"{k}={v}" for k, v in e.items() if k in ("surface", "baseColor", "metallic", "smoothness", "emission", "emissionIntensity", "blend"))
            w(f"| `{n}` | param | - | - | - | {note} |")
        else:
            note = []
            if e.get("sharesMapsWith"):
                note.append(f"tint of `{e['sharesMapsWith']}`")
            if "emissionIntensity" in e:
                note.append(f"emission x{e['emissionIntensity']}")
            if e.get("alphaClip"):
                note.append(f"alpha clip {e['alphaClip']}")
            if e.get("cull"):
                note.append(f"cull {e['cull']}")
            ts = e["tileSizeMeters"] if e["tileSizeMeters"] is not None else "fit"
            w(f"| `{n}` | {e['kind']} | {e['uvMode']} | {ts} | {e['tiling'][0]:g} x {e['tiling'][1]:g} | {'; '.join(note)} |")
    w("\n`aether_energy` and `water` are placeholders for the game's custom shaders (Aether fresnel/flow, rippling water); "
      "their parameters are a fallback only. `car_headlight` / `car_taillight` / `screen` have emission you can drive at runtime.\n")
    w("### Prototype material name -> kit material\n")
    w(", ".join(f"`{k}`->`{v}`" for k, v in m["prototypeMaterialMap"].items()) + "\n")
    w("## Using the city kit (zone integrator notes)\n")
    w("**Facade modules** (`Facade_*` originals upgraded in place, plus the new `Building_Facade_*` kit) share one convention: 4.0 m wide, one storey "
      "= 3.4 m, pivot base-centre, outer face +Z, module back plane at local z = -0.15. `PzKit.Building()` places them 0.16 m outside the mass box, "
      "so any `Building_Facade_*` name can replace a `Facade_*` name in that code. The originals keep their exact envelopes (4 x 3.4 x 0.4 m, shops "
      "0.75 m), window opening (1.6 x 1.6, sill 0.9, glass at local z -0.04) and shop transom (3.2 x 0.75 at 2.0 m, glass z -0.06) so the "
      "lit-window / transom overlay quads still line up. New modules project further (see each asset's `projection` in metres): "
      "`_Window_AC` 0.41, `_Window_Cage` 0.62, `_Window_Neon` 0.17, `_Balcony` 1.25 (walkable slab, colliders), `_Window_Double` 0.37, "
      "`_Pipes` 0.3, `_Damaged` 0.25; ground floor `_Shop_Glass` 0.44, `_Shop_Awning` 1.62, `_Shop_Shutter` 0.6, `_Shop_Noodle` 0.6 "
      "(counter collider), `_Entrance` 1.0, `_Shop_Boarded` 0.3. Styles: Concrete, Plaster, Brick, Panel (metal cladding with LED seams); "
      "ground-floor modules come in Concrete and Panel. Use `_Pier` (0.5 m) for odd lengths, `_Corner` at mass corners, `_Cornice_4m` on top of the last "
      "storey and `Building_Parapet_*_4m` on the roof edge.\n")
    w("**Complete buildings** (`Building_MidRise_A/B/C`, `Building_HighRise_D`): pivot = base centre of the structural mass; drop one in at a prototype "
      "block centre instead of `B.Box` + `PzKit.Building` (keep a box collider of the mass if you need NavMesh carving - the manifest collider is the mass). "
      "`massFootprint` [x, z] and `roofHeight` are in the manifest; facades project up to ~1.3 m beyond the mass (signs/balconies).\n")
    w("| Building | Mass footprint (m) | Roof (m) | Storeys | Style / features |\n|---|---|---|---|---|")
    for r in m["assets"]:
        if r["category"] == "building" and r.get("massFootprint"):
            w(f"| `{r['name']}` | {r['massFootprint'][0]:g} x {r['massFootprint'][1]:g} | {r['roofHeight']:g} | {r['floors']} | {r.get('notes', '').split('.')[0]} |")
    w("\n**Skyline** (`Skyline_Tower_A/B/C`, `Skyline_Twin_D`): low-poly distant towers with emissive window grids, LED fins, ad screens and beacons; "
      "no colliders; place 150-500 m out, uniform scale only (the window grid is in metres). The old `Building_Block_A..D` keep their exact sizes "
      "(used by `PzKit.SkylineBlock`, scaled 0.8-2.2) and were restyled with neon-tinted rooms, lit shopfronts, LED ad fascias, flat neon glyph "
      "signs and corner LED strips.\n")
    w("**Skybridges / catwalks**: `Skybridge_Enclosed_12m` and `Skybridge_Catwalk_8m` span 12 / 8 m along X, pivot at the walkway floor centre; "
      "`Catwalk_Wall_4m` mounts on a wall (wall plane at local z=0, deck toward +Z). The elevated rail (`ElevatedRail_Deck_14m`, `_Pier`) keeps its "
      "envelope and now has a lit LED underside / collar.\n")
    w("**Neon & signage kit** (`Neon_*`, `Sign_Blade_*`, `Billboard_*`, `Holo_*`, `Traffic_Light_*`, `Light_Strip_Bar_*`, `Bus_Shelter_Neon`, "
      "`Vending_Machine_*`, `Ramen_Stall`, `Street_Food_Counter`, `Kiosk_Neon`): wall signs use pivot `wall-back` (origin on the wall plane, sign "
      "projects toward +Z); each carries `light`/`lights` (position, colour, range, intensity) and `glow` (hex) for matching point lights, and "
      "`screen`/`screens` where Unity can animate content. Neon tubes are `emit_neon_*` (HDR 6) - put a Bloom override in the zone volume.\n")
    w("**Dressing** (`Cable_*`, `Pipe_Run_*`, `Wall_Vent_*`, `Electrical_*`, `Fire_Extinguisher_Cabinet`, `Wall_Lamp_*`, `AC_Unit_Stack_Wall`, "
      "`Satellite_*`, `Antenna_Cluster_Roof`, `Water_Tower_Roof`, `Roof_Clutter_Pack_A`, `Lantern_String_4m`, `Cardboard_*`, `Barrel_*`, `Pallet_*`, "
      "`Sandbag_Wall_2m`, `Barricade_Sheet_Metal_2m`, `Fence_ChainLink_*`, `Scaffolding_Section_2m`, `Plant_Pot_Dead_*`, `Rubble_Rebar_*`): see each "
      "asset's notes for its pivot (wall-mounted pieces pivot at the wall plane; cables at the left attach point with the span documented).\n")
    if m.get("decals"):
        w("## Decals (URP Decal Projector)\n")
        w("Texture sets under `Decals/<Name>/`: BaseColor (sRGB, alpha = opacity), Normal (OpenGL), MaskMap (MAOS: R metallic, G AO, A smoothness). "
          "Requires the URP Decal renderer feature. Sizes are the projector width x height in metres.\n")
        w("| Decal | Size (m) | Res | Projection | Use |\n|---|---|---|---|---|")
        for d in m["decals"]:
            sz = d.get("sizeMeters", [0, 0])
            w(f"| `{d.get('name')}` | {sz[0]:g} x {sz[1]:g} | {d.get('resolution', '')} | {d.get('projection', '')} | {str(d.get('use', '')).replace('|', '/')} |")
        w("")
    w("## Texture budget\n")
    w(f"Total PNG textures (materials + decals): {m['stats']['textureMB']} MB. 2048 px (desktop; WebGL import caps at 1024): "
      + ", ".join(f"`{n}`" for n in m['stats'].get('textures2K', [])) + ". Everything else 1024 px (each material's `textureSize` / `maxTextureSize`).\n")
    w("## Asset catalogue\n")
    w("Size = Unity (X width, Y height, Z depth) in metres. Tris = LOD0 / LOD1.\n")
    cat = None
    for r in m["assets"]:
        if r["category"] != cat:
            cat = r["category"]
            w(f"\n### {cat}\n")
            w("| Asset | File | Size (m) | Tris | Pivot | Zones | Notes |\n|---|---|---|---|---|---|---|")
        s = r["size"]
        w(f"| `{r['name']}` | `{r['file']}` | {s[0]:.2f} x {s[1]:.2f} x {s[2]:.2f} | {r['tris']['LOD0']} / {r['tris']['LOD1']} | {r['pivot']} | "
          f"{', '.join(r['zones'])} | {r.get('notes', '').replace('|', '/')} |")
    w("\n## Extra per-asset metadata in manifest.json\n")
    w("- `colliders`: suggested primitive colliders (box / capsule / cylinder, Unity local space) or `mesh` / `none`.\n"
      "- `screen` / `screens`: centre, size and normal (Unity local) of blank `screen` faces (UV 0..1) for TextMeshPro text or RenderTextures "
      "(signs, kiosks, terminals, transmitter, monument plaque).\n"
      "- `light` / `lights` / `beacon`: suggested point-light anchors. `lightSockets` (blast door): positions for `Vault_BlastDoor_Light`.\n"
      "- `placements` (Monument_Base): prototype world positions of the separate monument parts.\n"
      "- `lodTransitions`: suggested LODGroup screen-relative heights [LOD0->LOD1, cull] (0 = never cull).\n")
    w("## Known gaps / Unity-side notes\n")
    w("- No UV2: use the ModelImporter's Generate Lightmap UVs for baked lighting.\n"
      "- Decals need the URP Decal renderer feature (DBuffer for normal+MAOS) and the manifest's per-decal settings; the importer does not create "
      "Decal Projector materials yet (requested change: build one `Shader Graphs/Decal` material per `decals` entry, Normal textures as NormalMap).\n"
      "- Wet look: puddles/wetness are baked into `concrete_wet`, `asphalt`, `paving` (smoothness up to 0.98 in puddles). They only read as mirror "
      "puddles with reflection probes / SSR; place reflection probes in streets. Puddle decals add local variation on top.\n"
      "- `aether_energy` (crystals, pod columns), `water` and `holo_*` need the game's custom shaders for flicker/scanlines; the manifest values are fallbacks. "
      "`holo_*` is not an `emit_*` slot, so power-off code does not switch it.\n"
      "- `screen` faces are blank on purpose (TextMeshPro / RenderTextures on the published rects); `screen_ad_*` carry baked default art (invented glyphs).\n"
      "- Double-sided: `tarp`, `tarp_blue`, `glass`, `grating` (alpha clip), `holo_*`.\n"
      "- World-space box projection can show texture seams on curved parts where the projection axis switches; facade modules use a zero UV offset so "
      "textures continue across neighbouring modules (seams fall on the pilaster joints).\n"
      "- Complete buildings are 16-32k tris at LOD0 (detail tiered: street front full detail, upper/back faces massing-level) with LOD1/LOD2; skyline "
      "towers are 0.3-2.2k tris and rely on emissive textures.\n"
      "- Vehicles (`Car_*`, `Bus_*`, `TrainCar_*`) are frozen legacy exports here; the vehicle kit ships separately under Assets/Art/Vehicles/.\n"
      "- Rotated colliders carry `rotationEuler` (Unity degrees). Suggested colliders are approximations; use LOD1 MeshColliders for exact walkable surfaces.\n")
    w("## Rebuilding\n")
    w("```\ncd blender/env\nB=/Applications/Blender.app/Contents/MacOS/Blender\n"
      "$B -b --factory-startup --python build_materials.py -- --samples 6                # textures (per-material res, 2K set ~25 min)\n"
      "$B -b --factory-startup --python build_decals.py --                             # decal texture sets -> Decals/, out/decals.json\n"
      "$B -b --factory-startup --python build_assets.py --                             # all FBX (+ --list, --module vault, 'Car*')\n"
      "$B -b --factory-startup --python render_assets.py -- --sheet street 'Barrier*'   # re-import check + preview sheets\n"
      "$B -b --factory-startup --python render_materials.py --                         # material sphere sheets\n"
      "$B -b --factory-startup --python render_matscene.py -- --night asphalt paving    # HD material scene previews (wall+floor, neon night)\n"
      "$B -b --factory-startup --python render_cityscene.py -- --shot street           # assembled cyberpunk street hero render\n"
      "$B -b --factory-startup --python render_assets.py -- --check-only               # re-import check of every FBX (no renders)\n"
      "python3 check_regression.py                                                     # size/pivot/collider compatibility vs the pre-upgrade baseline\n"
      "python3 write_manifest.py                                                       # manifest.json + this file\n```\n")
    w("Scripts: `envkit.py` (geometry/UV/LOD0-2/export helpers, `placed()` instancing), `nodekit.py` (tileable shader-node DSL), `matdefs.py` "
      "(registry), `matdefs_hd.py` (2K HD + cyberpunk materials, numpy weathering post-process, glyph generator, ad/skyline art), `texops.py` "
      "(tileable drips/curvature/cavity ops), `bakekit.py` (Cycles bake + normal/AO derivation), `decaldefs.py`/`build_decals.py`, `pngio.py`, "
      "`preview.py`, `assets_*.py` (builders by category: facade, buildings, neon, dressing, street, interior, metro, vault, monument, rooftop, debris, structure).\n")
    out = os.path.join(envpaths.UNITY_ENV, "ENV_ASSETS.md")
    open(out, "w").write("\n".join(L) + "\n")
    print("wrote", out)


if __name__ == "__main__":
    main()
