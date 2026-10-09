using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;

namespace EOA.EditorTools
{
    /// <summary>
    /// Turns the Blender environment kit (Assets/Art/Environment/manifest.json) into runtime assets:
    ///   • texture import settings (Normal maps, linear Mask/Occlusion, 1024, repeat)
    ///   • one URP Lit material per manifest material → Resources/Env/Materials/&lt;name&gt;.mat (world-scale tiling,
    ///     MaskMap as Metallic map with smoothness in alpha, Normal, Occlusion, Emission, alpha clip, double sided)
    ///   • FBX import settings + material remap by slot name, then a prefab per asset with LODGroup transitions,
    ///     the manifest's suggested colliders and the World layer → Resources/Env/Props/&lt;Name&gt;.prefab
    ///   • a copy of the manifest → Resources/Env/env_manifest.json (read by EnvProps at runtime)
    /// </summary>
    public static class EnvLibraryBuilder
    {
        /// <summary>Kit folder being processed (environment kit, then the vehicle kit).</summary>
        static string ArtRoot = "Assets/Art/Environment";
        const string MatDir = "Assets/Resources/Env/Materials";
        const string PropDir = "Assets/Resources/Env/Props";
        const int WorldLayer = 6;

        /// <summary>Kit folders and their runtime manifest names (Resources/Env/&lt;name&gt;.json, see EnvProps.Manifests).</summary>
        public static readonly (string root, string copyName)[] Kits =
        {
            ("Assets/Art/Environment", "env_manifest"),
            ("Assets/Art/Vehicles", "vehicles_manifest"),
            ("Assets/Art/CityLandmarks", "landmarks_manifest"),
            ("Assets/Art/CityStreet", "street_manifest"),
        };

        [MenuItem("EOA/Build Environment Library")]
        public static void Build()
        {
            EnsureFolder(MatDir);
            EnsureFolder(PropDir);
            // Environment kit first, then the other kits (same manifest schema, separate folders).
            foreach (var (root, copyName) in Kits)
            {
                var manifestPath = root + "/manifest.json";
                if (!File.Exists(manifestPath)) { if (root.EndsWith("Environment")) Debug.LogError("[env] missing " + manifestPath); continue; }
                ArtRoot = root;
                BuildKit(manifestPath, copyName);
            }
            ArtRoot = "Assets/Art/Environment";
            AssetDatabase.SaveAssets();
        }

        /// <summary>Vehicle kit only (Assets/Art/Vehicles): fast rebuild of the veh_ materials and the vehicle prefabs.</summary>
        [MenuItem("EOA/Build Vehicle Library")]
        public static void BuildVehicles()
        {
            EnsureFolder(MatDir);
            EnsureFolder(PropDir);
            const string root = "Assets/Art/Vehicles";
            if (!File.Exists(root + "/manifest.json")) { Debug.LogError("[env] missing " + root + "/manifest.json"); return; }
            ArtRoot = root;
            try { BuildKit(root + "/manifest.json", "vehicles_manifest"); }
            finally { ArtRoot = "Assets/Art/Environment"; }
            AssetDatabase.SaveAssets();
        }

        /// <summary>True while the vehicle kit (Assets/Art/Vehicles, veh_ materials) is being processed.</summary>
        static bool VehicleKit => ArtRoot.EndsWith("/Vehicles");

        static void BuildKit(string manifestPath, string copyName)
        {
            var manifest = JObject.Parse(File.ReadAllText(manifestPath));
            try
            {
                AssetDatabase.StartAssetEditing();
                ConfigureTextures(manifest);
            }
            finally { AssetDatabase.StopAssetEditing(); }
            AssetDatabase.Refresh();

            var mats = BuildMaterials(manifest["materials"] as JObject);
            if (VehicleKit) BuildVehicleOffMaterials(manifest, mats);
            BuildDecals(manifest["decals"] as JArray);
            // Props may reference materials defined by the other kit (e.g. vehicles using env metals).
            foreach (var guid in AssetDatabase.FindAssets("t:Material", new[] { MatDir }))
            {
                var m = AssetDatabase.LoadAssetAtPath<Material>(AssetDatabase.GUIDToAssetPath(guid));
                if (m != null && !mats.ContainsKey(m.name)) mats[m.name] = m;
            }
            var assets = (manifest["assets"] as JArray)?.OfType<JObject>().ToList() ?? new List<JObject>();
            int ok = 0, failed = 0;
            for (var i = 0; i < assets.Count; i++)
            {
                var a = assets[i];
                var name = (string)a["name"];
                EditorUtility.DisplayProgressBar("EOA " + Path.GetFileName(ArtRoot), name, i / (float)Math.Max(1, assets.Count));
                try { if (BuildPrefab(a, mats)) ok++; else failed++; }
                catch (Exception e) { failed++; Debug.LogError($"[env] {name}: {e}"); }
            }
            EditorUtility.ClearProgressBar();
            var copy = $"Assets/Resources/Env/{copyName}.json";
            File.Copy(manifestPath, copy, true);
            AssetDatabase.ImportAsset(copy);
            Debug.Log($"[env] {Path.GetFileName(ArtRoot)} library: {mats.Count} materials, {ok} prefabs ({failed} failed)");
        }

        // ------------------------------------------------------------------ textures

        static void ConfigureTextures(JObject manifest)
        {
            if (manifest["materials"] is not JObject materials) return;
            var seen = new HashSet<string>();
            foreach (var p in materials.Properties())
            {
                if (p.Value["textures"] is not JObject tex) continue;
                foreach (var t in tex.Properties())
                {
                    var path = ArtRoot + "/" + (string)t.Value;
                    if (!seen.Add(path) || !File.Exists(path)) continue;
                    if (AssetImporter.GetAtPath(path) is not TextureImporter ti) continue;
                    var kind = t.Name;
                    if (VehicleKit) { ConfigureVehicleTexture(ti, kind, (JObject)p.Value); continue; }
                    ti.textureType = kind == "Normal" ? TextureImporterType.NormalMap : TextureImporterType.Default;
                    ti.sRGBTexture = kind == "BaseColor" || kind == "Emission";
                    ti.alphaSource = kind == "BaseColor" && (p.Value["alphaClip"] != null) ? TextureImporterAlphaSource.FromInput : kind == "MaskMap" ? TextureImporterAlphaSource.FromInput : TextureImporterAlphaSource.None;
                    ti.alphaIsTransparency = false;
                    ti.wrapMode = TextureWrapMode.Repeat;
                    ti.mipmapEnabled = true;
                    ti.anisoLevel = kind == "BaseColor" || kind == "Normal" ? 4 : 1;
                    // 2K sources on desktop, capped at 1K for WebGL downloads.
                    ti.maxTextureSize = 2048;
                    ti.textureCompression = TextureImporterCompression.Compressed;
                    ti.SetPlatformTextureSettings(new TextureImporterPlatformSettings { name = "WebGL", overridden = true, maxTextureSize = 1024, format = TextureImporterFormat.Automatic, textureCompression = TextureImporterCompression.Compressed });
                    ti.SaveAndReimport();
                }
            }
        }

        /// <summary>
        /// Vehicle kit textures: per-material size caps from the manifest (2K body paints / wreck / burnt, 1K details,
        /// 256 nav lights; WebGL 1K), clamped 'fit' atlases (decal, navlight, holo sign), alpha kept for the transparent
        /// RGBA maps (cracked glass, holo sign). Reimports only when a setting actually changes.
        /// </summary>
        static void ConfigureVehicleTexture(TextureImporter ti, string kind, JObject mat)
        {
            var desktop = (int?)mat["maxTextureSize"]?["desktop"] ?? (int?)mat["textureSize"] ?? 2048;
            var web = Math.Min(desktop, (int?)mat["maxTextureSize"]?["webgl"] ?? 1024);
            var fit = mat["tileSizeMeters"] == null || mat["tileSizeMeters"].Type == JTokenType.Null;
            var transparent = (string)mat["surface"] == "Transparent";
            var type = kind == "Normal" ? TextureImporterType.NormalMap : TextureImporterType.Default;
            var srgb = kind == "BaseColor" || kind == "Emission";
            var alpha = kind == "MaskMap" || (kind == "BaseColor" && transparent) ? TextureImporterAlphaSource.FromInput : TextureImporterAlphaSource.None;
            var wrap = fit ? TextureWrapMode.Clamp : TextureWrapMode.Repeat;
            var aniso = kind == "BaseColor" || kind == "Normal" ? (desktop >= 2048 ? 8 : 4) : 1;
            var webSettings = ti.GetPlatformTextureSettings("WebGL");
            var changed = ti.textureType != type || ti.sRGBTexture != srgb || ti.alphaSource != alpha || ti.alphaIsTransparency || ti.wrapMode != wrap
                          || !ti.mipmapEnabled || ti.anisoLevel != aniso || ti.maxTextureSize != desktop || ti.textureCompression != TextureImporterCompression.Compressed
                          || !webSettings.overridden || webSettings.maxTextureSize != web;
            if (!changed) return;
            ti.textureType = type;
            ti.sRGBTexture = srgb;
            ti.alphaSource = alpha;
            ti.alphaIsTransparency = false;
            ti.wrapMode = wrap;
            ti.mipmapEnabled = true;
            ti.anisoLevel = aniso;
            ti.maxTextureSize = desktop;
            ti.textureCompression = TextureImporterCompression.Compressed;
            ti.SetPlatformTextureSettings(new TextureImporterPlatformSettings { name = "WebGL", overridden = true, maxTextureSize = web, format = TextureImporterFormat.Automatic, textureCompression = TextureImporterCompression.Compressed });
            ti.SaveAndReimport();
        }

        // ------------------------------------------------------------------ materials

        static Dictionary<string, Material> BuildMaterials(JObject materials)
        {
            var result = new Dictionary<string, Material>();
            if (materials == null) return result;
            var lit = Shader.Find("Universal Render Pipeline/Lit");
            foreach (var p in materials.Properties())
            {
                var name = p.Name;
                var d = (JObject)p.Value;
                var path = $"{MatDir}/{name}.mat";
                Material m;
                if (name == "aether_energy")
                {
                    var sh = Shader.Find("EOA/Aether");
                    m = sh != null ? new Material(sh) : EnvMaterials.CreateFallback(name);
                    if (sh != null)
                    {
                        m.SetColor("_Color", new Color(0.37f, 0.85f, 1f));
                        m.SetColor("_Color2", new Color(0.65f, 0.48f, 1f));
                        m.SetFloat("_Intensity", 1f);
                    }
                }
                else if ((string)d["kind"] == "param" && d["textures"] == null)
                {
                    m = new Material(lit);
                    var bc = Col(d["baseColor"], Color.grey);
                    m.SetColor("_BaseColor", bc);
                    m.SetFloat("_Metallic", (float?)d["metallic"] ?? 0f);
                    m.SetFloat("_Smoothness", (float?)d["smoothness"] ?? 0.5f);
                    if (d["emission"] != null)
                    {
                        var intensity = (float?)d["emissionIntensity"] ?? 1f;
                        SetEmission(m, Col(d["emission"], Color.black), intensity);
                    }
                    if ((string)d["surface"] == "Transparent") SetTransparent(m, (string)d["blend"] == "Additive");
                }
                else
                {
                    m = new Material(lit);
                    var tex = d["textures"] as JObject;
                    m.SetColor("_BaseColor", Color.white);
                    var tiling = d["tiling"] is JArray ta && ta.Count >= 2 ? new Vector2((float)ta[0], (float)ta[1]) : Vector2.one;
                    var baseMap = Tex(tex, "BaseColor");
                    if (baseMap != null) m.SetTexture("_BaseMap", baseMap);
                    m.SetTextureScale("_BaseMap", tiling);
                    m.mainTextureScale = tiling;
                    var mask = Tex(tex, "MaskMap");
                    if (mask != null)
                    {
                        m.SetTexture("_MetallicGlossMap", mask);
                        m.EnableKeyword("_METALLICSPECGLOSSMAP");
                        m.SetFloat("_Metallic", 1f);
                        m.SetFloat("_Smoothness", 1f);
                        m.SetFloat("_SmoothnessTextureChannel", 0f);
                    }
                    var normal = Tex(tex, "Normal");
                    if (normal != null)
                    {
                        m.SetTexture("_BumpMap", normal);
                        m.SetFloat("_BumpScale", (float?)d["normalScale"] ?? 1f);
                        m.EnableKeyword("_NORMALMAP");
                    }
                    var occ = Tex(tex, "Occlusion");
                    if (occ != null)
                    {
                        m.SetTexture("_OcclusionMap", occ);
                        m.SetFloat("_OcclusionStrength", (float?)d["occlusionStrength"] ?? 1f);
                        m.EnableKeyword("_OCCLUSIONMAP");
                    }
                    var em = Tex(tex, "Emission");
                    if (em != null)
                    {
                        m.SetTexture("_EmissionMap", em);
                        SetEmission(m, Col(d["emissionColor"], Color.white), (float?)d["emissionIntensity"] ?? 1f);
                    }
                    if (d["alphaClip"] != null)
                    {
                        m.SetFloat("_AlphaClip", 1f);
                        m.SetFloat("_Cutoff", (float)d["alphaClip"]);
                        m.EnableKeyword("_ALPHATEST_ON");
                        m.SetOverrideTag("RenderType", "TransparentCutout");
                        m.renderQueue = (int)RenderQueue.AlphaTest;
                    }
                    if ((string)d["surface"] == "Transparent") SetTransparent(m, (string)d["blend"] == "Additive");
                }
                if ((string)d["cull"] == "Off" && m.HasProperty("_Cull")) { m.SetFloat("_Cull", (float)CullMode.Off); m.doubleSidedGI = true; }
                if (VehicleKit) m = VehicleMaterial(m, d, name);
                m.name = name;
                result[name] = SaveMaterial(m, path);
            }
            return result;
        }

        /// <summary>
        /// Vehicle kit material extras: body paints with a clear coat in the manifest move to URP Complex Lit (clear coat
        /// mask / smoothness, flake normal and MaskMap kept), MaskMap G doubles as the occlusion map, emissive slots get
        /// instancing-friendly HDR emission (white x intensity, driven per renderer by VehicleRig), glass stays in the
        /// transparent queue (double sided, no shadows) with the additive holo sign sorted after it.
        /// </summary>
        static Material VehicleMaterial(Material m, JObject d, string name)
        {
            var tex = d["textures"] as JObject;
            var mask = Tex(tex, "MaskMap");
            if (mask != null && Tex(tex, "Occlusion") == null && m.HasProperty("_OcclusionMap"))
            {
                // MaskMap G = ambient occlusion (manifest urpLitMapping: optional _OcclusionMap).
                m.SetTexture("_OcclusionMap", mask);
                m.SetFloat("_OcclusionStrength", (float?)d["occlusionStrength"] ?? 1f);
                m.EnableKeyword("_OCCLUSIONMAP");
            }
            if (d["clearCoat"] is JObject cc)
            {
                var complex = Shader.Find("Universal Render Pipeline/Complex Lit");
                if (complex != null)
                {
                    var keywords = m.shaderKeywords;
                    m.shader = complex;
                    m.shaderKeywords = keywords;
                    m.SetFloat("_ClearCoat", 1f);
                    m.SetFloat("_ClearCoatMask", (float?)cc["mask"] ?? 1f);
                    m.SetFloat("_ClearCoatSmoothness", (float?)cc["smoothness"] ?? 0.95f);
                    m.EnableKeyword("_CLEARCOAT");
                    m.SetFloat("_EnvironmentReflections", 1f);
                    m.SetFloat("_SpecularHighlights", 1f);
                }
                else Debug.LogWarning("[env] Complex Lit not found: " + name + " stays on Lit");
            }
            if ((string)d["surface"] == "Transparent")
            {
                var additive = (string)d["blend"] == "Additive";
                // Glass first, then the additive holo sign on top of it (same renderer, sorted by queue).
                m.renderQueue = (int)RenderQueue.Transparent + (additive ? 10 : 0);
                m.SetFloat("_Cull", (float)CullMode.Off);
                m.doubleSidedGI = true;
                m.SetFloat("_ReceiveShadows", additive ? 0f : 1f);
                if (additive) m.EnableKeyword("_RECEIVE_SHADOWS_OFF");
                // Glass keeps its specular reflections at low alpha (URP 'preserve specular lighting').
                if (!additive && m.HasProperty("_BlendModePreserveSpecular")) { m.SetFloat("_BlendModePreserveSpecular", 1f); m.EnableKeyword("_ALPHAPREMULTIPLY_ON"); }
                m.SetShaderPassEnabled("ShadowCaster", false);
            }
            if (d["emissionIntensity"] != null && m.IsKeywordEnabled("_EMISSION"))
            {
                // Emission map carries the tint; _EmissionColor = white x intensity (HDR), see VehicleRig.
                m.SetColor("_EmissionColor", FxMaterials.Hdr(Col(d["emissionColor"], Color.white), (float)d["emissionIntensity"]));
                // URP's material validation keeps _EMISSION only with an emissive GI flag (no realtime GI is baked here).
                m.globalIlluminationFlags = MaterialGlobalIlluminationFlags.RealtimeEmissive;
            }
            return m;
        }

        /// <summary>
        /// "Lights off" twin of every emissive vehicle slot (veh_headlight_off, ...: same maps, _EmissionColor black with
        /// the _EMISSION keyword kept so a MaterialPropertyBlock can light it; the additive holo sign also gets alpha 0).
        /// Vehicle prefabs use these, so parked cars and wrecks are dark wherever they are placed; VehicleRig drives
        /// the lights of moving vehicles per renderer.
        /// </summary>
        static void BuildVehicleOffMaterials(JObject manifest, Dictionary<string, Material> mats)
        {
            if (manifest["emissiveMaterials"] is not JArray emissive) return;
            foreach (var e in emissive)
            {
                var name = (string)e;
                if (!mats.TryGetValue(name, out var on) || on == null) continue;
                var off = new Material(on) { name = name + "_off" };
                // The _EMISSION keyword must survive URP's material validation (emissive GI flag) so the per-renderer
                // MaterialPropertyBlock can light the slot.
                off.SetColor("_EmissionColor", Color.black);
                off.EnableKeyword("_EMISSION");
                off.globalIlluminationFlags = MaterialGlobalIlluminationFlags.RealtimeEmissive;
                if (off.renderQueue >= (int)RenderQueue.Transparent && off.HasProperty("_BaseColor"))
                {
                    var c = off.GetColor("_BaseColor");
                    c.a = 0f;
                    off.SetColor("_BaseColor", c);
                }
                mats[off.name] = SaveMaterial(off, $"{MatDir}/{off.name}.mat");
            }
        }

        static Texture2D Tex(JObject tex, string kind)
        {
            var rel = (string)tex?[kind];
            return string.IsNullOrEmpty(rel) ? null : AssetDatabase.LoadAssetAtPath<Texture2D>(ArtRoot + "/" + rel);
        }

        static Color Col(JToken t, Color fallback)
        {
            if (t is not JArray a || a.Count < 3) return fallback;
            return new Color((float)a[0], (float)a[1], (float)a[2], a.Count > 3 ? (float)a[3] : 1f);
        }

        static void SetEmission(Material m, Color c, float intensity)
        {
            m.EnableKeyword("_EMISSION");
            // URP's material validation strips _EMISSION unless an emissive GI flag is set (with flags None every kit
            // emissive - neon strips, screens, lit windows, shop signs - saved without the keyword and never glowed).
            // No realtime GI is baked in this project, so the flag costs nothing.
            m.globalIlluminationFlags = MaterialGlobalIlluminationFlags.RealtimeEmissive;
            m.SetColor("_EmissionColor", FxMaterials.Hdr(c, intensity));
        }

        static void SetTransparent(Material m, bool additive)
        {
            m.SetFloat("_Surface", 1f);
            m.SetFloat("_Blend", additive ? 2f : 0f);
            m.SetFloat("_SrcBlend", (float)BlendMode.SrcAlpha);
            m.SetFloat("_DstBlend", additive ? (float)BlendMode.One : (float)BlendMode.OneMinusSrcAlpha);
            m.SetFloat("_SrcBlendAlpha", (float)BlendMode.One);
            m.SetFloat("_DstBlendAlpha", additive ? (float)BlendMode.One : (float)BlendMode.OneMinusSrcAlpha);
            m.SetFloat("_ZWrite", 0f);
            m.EnableKeyword("_SURFACE_TYPE_TRANSPARENT");
            m.SetOverrideTag("RenderType", "Transparent");
            m.renderQueue = (int)RenderQueue.Transparent;
            m.SetShaderPassEnabled("ShadowCaster", false);
        }

        static Material SaveMaterial(Material m, string path)
        {
            var existing = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (existing == null)
            {
                AssetDatabase.CreateAsset(m, path);
                return m;
            }
            existing.shader = m.shader;
            existing.CopyPropertiesFromMaterial(m);
            existing.shaderKeywords = m.shaderKeywords;
            existing.renderQueue = m.renderQueue;
            existing.globalIlluminationFlags = m.globalIlluminationFlags;
            existing.SetOverrideTag("RenderType", m.GetTag("RenderType", false, "Opaque"));
            existing.SetShaderPassEnabled("ShadowCaster", m.GetShaderPassEnabled("ShadowCaster"));
            EditorUtility.SetDirty(existing);
            UnityEngine.Object.DestroyImmediate(m);
            return existing;
        }

        // ------------------------------------------------------------------ decals

        /// <summary>URP decal material per manifest decal → Resources/Env/Decals/&lt;name&gt;.mat (Shader Graphs/Decal).</summary>
        static void BuildDecals(JArray decals)
        {
            if (decals == null || decals.Count == 0) return;
            var shader = Shader.Find("Shader Graphs/Decal");
            if (shader == null) { Debug.LogError("[env] URP decal shader not found"); return; }
            const string dir = "Assets/Resources/Env/Decals";
            EnsureFolder(dir);
            var n = 0;
            foreach (var d in decals.OfType<JObject>())
            {
                var name = (string)d["name"];
                var tex = d["textures"] as JObject;
                if (string.IsNullOrEmpty(name) || tex == null) continue;
                Texture2D Load(string kind, bool normal)
                {
                    var rel = (string)tex[kind];
                    if (string.IsNullOrEmpty(rel)) return null;
                    var path = ArtRoot + "/" + rel;
                    if (AssetImporter.GetAtPath(path) is TextureImporter ti)
                    {
                        var want = normal ? TextureImporterType.NormalMap : TextureImporterType.Default;
                        if (ti.textureType != want || (!normal && ti.alphaSource != TextureImporterAlphaSource.FromInput) || ti.wrapMode != TextureWrapMode.Clamp)
                        {
                            ti.textureType = want;
                            ti.alphaSource = normal ? TextureImporterAlphaSource.None : TextureImporterAlphaSource.FromInput;
                            ti.alphaIsTransparency = !normal;
                            ti.wrapMode = TextureWrapMode.Clamp;
                            ti.maxTextureSize = 1024;
                            ti.SaveAndReimport();
                        }
                    }
                    return AssetDatabase.LoadAssetAtPath<Texture2D>(path);
                }
                var m = new Material(shader) { name = name };
                var bc = Load("BaseColor", false);
                if (bc != null) m.SetTexture("Base_Map", bc);
                var nm = Load("Normal", true);
                if (nm != null) m.SetTexture("Normal_Map", nm);
                var urp = d["urp"] as JObject;
                m.SetFloat("Normal_Blend", (float?)urp?["normalBlend"] ?? 1f);
                if (m.HasProperty("_DrawOrder")) m.SetFloat("_DrawOrder", (float?)urp?["drawOrder"] ?? 0f);
                m.enableInstancing = true;
                SaveMaterial(m, $"{dir}/{name}.mat");
                n++;
            }
            Debug.Log($"[env] {n} decal materials");
        }

        // ------------------------------------------------------------------ prefabs

        static bool BuildPrefab(JObject a, Dictionary<string, Material> mats)
        {
            var name = (string)a["name"];
            var file = (string)a["file"];
            var fbxPath = ArtRoot + "/" + file;
            if (AssetImporter.GetAtPath(fbxPath) is not ModelImporter mi)
            {
                Debug.LogWarning($"[env] {name}: no model at {fbxPath}");
                return false;
            }
            var colliders = a["colliders"] as JArray;
            var meshCollider = colliders != null && colliders.Any(c => c.Type == JTokenType.String ? (string)c == "mesh" : (string)c["type"] == "mesh");
            mi.globalScale = 1f;
            mi.useFileScale = true;
            mi.importCameras = false;
            mi.importLights = false;
            mi.importVisibility = false;
            mi.animationType = ModelImporterAnimationType.None;
            mi.importAnimation = false;
            mi.importBlendShapes = false;
            mi.importNormals = ModelImporterNormals.Import;
            mi.importTangents = ModelImporterTangents.CalculateMikk;
            mi.meshCompression = ModelImporterMeshCompression.Off;
            mi.isReadable = meshCollider;
            mi.generateSecondaryUV = false;
            mi.addCollider = false;
            mi.materialImportMode = ModelImporterMaterialImportMode.ImportStandard;
            mi.materialLocation = ModelImporterMaterialLocation.InPrefab;
            var slots = new HashSet<string>((a["materials"] as JArray)?.Select(x => (string)x) ?? Enumerable.Empty<string>());
            foreach (var src in mi.GetExternalObjectMap().Keys.ToList()) mi.RemoveRemap(src);
            foreach (var slot in slots)
                if (mats.TryGetValue(slot, out var mat)) mi.AddRemap(new AssetImporter.SourceAssetIdentifier(typeof(Material), slot), mat);
                else Debug.LogWarning($"[env] {name}: no material '{slot}'");
            mi.SaveAndReimport();

            var model = AssetDatabase.LoadAssetAtPath<GameObject>(fbxPath);
            if (model == null) return false;
            var go = (GameObject)PrefabUtility.InstantiatePrefab(model);
            try
            {
                PrefabUtility.UnpackPrefabInstance(go, PrefabUnpackMode.OutermostRoot, InteractionMode.AutomatedAction);
                go.name = name;
                // Material slots that came through with a numeric suffix (".001") still map to the base name.
                foreach (var r in go.GetComponentsInChildren<Renderer>(true))
                {
                    var shared = r.sharedMaterials;
                    var changed = false;
                    for (var i = 0; i < shared.Length; i++)
                    {
                        var mn = shared[i] != null ? shared[i].name : "";
                        var baseName = mn.Contains('.') ? mn.Substring(0, mn.IndexOf('.')) : mn;
                        if (!mats.ContainsKey(mn) && mats.TryGetValue(baseName, out var mm)) { shared[i] = mm; changed = true; }
                    }
                    if (changed) r.sharedMaterials = shared;
                    var transparent = r.sharedMaterials.All(x => x != null && x.renderQueue >= 3000);
                    var emissiveOnly = r.sharedMaterials.All(x => x != null && x.name.StartsWith("emit_"));
                    r.shadowCastingMode = transparent || emissiveOnly ? ShadowCastingMode.Off : ShadowCastingMode.On;
                }
                // LOD transitions.
                var lodGroup = go.GetComponent<LODGroup>();
                if (lodGroup != null && a["lodTransitions"] is JArray lt && lt.Count >= 2)
                {
                    var lods = lodGroup.GetLODs();
                    for (var i = 0; i < lods.Length && i < lt.Count; i++) lods[i].screenRelativeTransitionHeight = (float)lt[i];
                    lodGroup.SetLODs(lods);
                    lodGroup.fadeMode = LODFadeMode.CrossFade;
                    lodGroup.animateCrossFading = true;
                }
                if (VehicleKit) { VehicleLights(go, mats); VehicleLods(go, a); }
                // Colliders from the manifest (Unity local space).
                if (colliders != null)
                {
                    foreach (var c in colliders)
                    {
                        var type = c.Type == JTokenType.String ? (string)c : (string)c["type"];
                        if (type == "box")
                        {
                            if (c["rotationEuler"] is JArray)
                            {
                                // Rotated boxes need their own transform.
                                var child = new GameObject("Collider_" + go.transform.childCount);
                                child.transform.SetParent(go.transform, false);
                                child.transform.localPosition = V3(c["center"], Vector3.zero);
                                child.transform.localRotation = Quaternion.Euler(V3(c["rotationEuler"], Vector3.zero));
                                child.AddComponent<BoxCollider>().size = V3(c["size"], Vector3.one);
                            }
                            else
                            {
                                var bc = go.AddComponent<BoxCollider>();
                                bc.center = V3(c["center"], Vector3.zero);
                                bc.size = V3(c["size"], Vector3.one);
                            }
                        }
                        else if (type == "cylinder" || (type == "capsule" && ((float?)c["height"] ?? 1f) < 2f * ((float?)c["radius"] ?? 0.5f)))
                        {
                            // Flat discs/pedestals: a convex cylinder mesh (a capsule this short would become a sphere).
                            var radius = (float?)c["radius"] ?? 0.5f;
                            var height = (float?)c["height"] ?? 1f;
                            var child = new GameObject("Collider_" + go.transform.childCount);
                            child.transform.SetParent(go.transform, false);
                            child.transform.localPosition = V3(c["center"], Vector3.zero);
                            child.transform.localRotation = AxisRotation((string)c["direction"]);
                            var mc = child.AddComponent<MeshCollider>();
                            mc.sharedMesh = CylinderColliderMesh(radius, height);
                            mc.convex = true;
                        }
                        else if (type == "mesh")
                        {
                            var mf = go.GetComponentsInChildren<MeshFilter>(true).OrderBy(f => f.name.EndsWith("_LOD1") ? 0 : 1).FirstOrDefault();
                            if (mf != null)
                            {
                                var mc = mf.gameObject.AddComponent<MeshCollider>();
                                mc.sharedMesh = mf.sharedMesh;
                                if (mf.gameObject != go && mf.name.EndsWith("_LOD1"))
                                {
                                    // A collider on the LOD1 renderer object would be disabled with it; move it to the root.
                                    UnityEngine.Object.DestroyImmediate(mc);
                                    var rc = go.AddComponent<MeshCollider>();
                                    rc.sharedMesh = mf.sharedMesh;
                                }
                            }
                        }
                        else if (type == "sphere")
                        {
                            var sc = go.AddComponent<SphereCollider>();
                            sc.center = V3(c["center"], Vector3.zero);
                            sc.radius = (float?)c["radius"] ?? 0.5f;
                        }
                        else if (type == "capsule")
                        {
                            var cc = go.AddComponent<CapsuleCollider>();
                            cc.center = V3(c["center"], Vector3.zero);
                            cc.radius = (float?)c["radius"] ?? 0.5f;
                            cc.height = (float?)c["height"] ?? 1f;
                            var dir = ((string)c["direction"] ?? "Y").ToUpperInvariant();
                            cc.direction = dir == "X" ? 0 : dir == "Z" ? 2 : 1;
                        }
                    }
                }
                SetLayer(go.transform, WorldLayer);
                PrefabUtility.SaveAsPrefabAsset(go, $"{PropDir}/{name}.prefab");
                return true;
            }
            finally { UnityEngine.Object.DestroyImmediate(go); }
        }

        /// <summary>
        /// Vehicle prefabs: one LODGroup on the root that lists every &lt;Body|Part&gt;_LODn renderer (the wheel / thruster
        /// LOD meshes are children of their pivot empties) under LOD n; nested LODGroups are removed. Flyers keep their
        /// last LOD down to a far smaller screen height so sky traffic still reads as lit silhouettes at distance.
        /// </summary>
        /// <summary>Vehicle prefabs ship with their lights off (emissive slots → the _off twins, see BuildVehicleOffMaterials).</summary>
        static void VehicleLights(GameObject go, Dictionary<string, Material> mats)
        {
            foreach (var r in go.GetComponentsInChildren<Renderer>(true))
            {
                var shared = r.sharedMaterials;
                var changed = false;
                for (var i = 0; i < shared.Length; i++)
                    if (shared[i] != null && !shared[i].name.EndsWith("_off") && mats.TryGetValue(shared[i].name + "_off", out var off)) { shared[i] = off; changed = true; }
                if (changed) r.sharedMaterials = shared;
            }
        }

        static void VehicleLods(GameObject go, JObject a)
        {
            var name = (string)a["name"];
            foreach (var nested in go.GetComponentsInChildren<LODGroup>(true))
                if (nested.gameObject != go) UnityEngine.Object.DestroyImmediate(nested);
            var byLod = new SortedDictionary<int, List<Renderer>>();
            foreach (var r in go.GetComponentsInChildren<Renderer>(true))
            {
                var n = r.gameObject.name;
                var i = n.LastIndexOf("_LOD", StringComparison.Ordinal);
                if (i < 0 || !int.TryParse(n.Substring(i + 4), out var lod)) { Debug.LogWarning($"[env] {name}: renderer '{n}' has no _LODn suffix"); continue; }
                if (!byLod.TryGetValue(lod, out var list)) byLod[lod] = list = new List<Renderer>();
                list.Add(r);
            }
            if (byLod.Count == 0) return;
            var heights = a["lodTransitions"] is JArray lt ? lt.Select(x => (float)x).ToList() : new List<float> { 0.3f, 0.1f, 0.02f };
            while (heights.Count < byLod.Count) heights.Add(heights[^1] * 0.4f);
            if ((string)a["category"] == "hover") heights[byLod.Count - 1] = Mathf.Min(heights[byLod.Count - 1], 0.004f);
            var lods = new LOD[byLod.Count];
            var k = 0;
            foreach (var kv in byLod) { lods[k] = new LOD(heights[k], kv.Value.ToArray()); k++; }
            var group = go.GetComponent<LODGroup>() ?? go.AddComponent<LODGroup>();
            group.SetLODs(lods);
            group.fadeMode = LODFadeMode.CrossFade;
            group.animateCrossFading = true;
            group.RecalculateBounds();
            var parts = (a["animatedParts"] as JArray)?.Count ?? 0;
            var counts = string.Join("/", byLod.Values.Select(l => l.Count));
            if (byLod.Values.Any(l => l.Count != parts + 1)) Debug.LogWarning($"[env] {name}: LOD renderer counts {counts}, expected {parts + 1} each (body + {parts} parts)");
            Debug.Log($"[env] vehicle {name}: LODGroup {byLod.Count} levels, renderers {counts}, transitions {string.Join(", ", lods.Select(l => l.screenRelativeTransitionHeight.ToString("0.###")))}");
        }

        static Quaternion AxisRotation(string direction)
        {
            var d = (direction ?? "Y").ToUpperInvariant();
            return d == "X" ? Quaternion.Euler(0, 0, 90) : d == "Z" ? Quaternion.Euler(90, 0, 0) : Quaternion.identity;
        }

        /// <summary>16-sided cylinder (Y axis) saved as an asset so prefabs can reference it.</summary>
        static Mesh CylinderColliderMesh(float radius, float height)
        {
            const string dir = "Assets/Resources/Env/ColliderMeshes";
            EnsureFolder(dir);
            var path = $"{dir}/cyl_{radius:0.###}_{height:0.###}.asset";
            var existing = AssetDatabase.LoadAssetAtPath<Mesh>(path);
            if (existing != null) return existing;
            const int seg = 16;
            var v = new Vector3[seg * 2];
            for (var i = 0; i < seg; i++)
            {
                var a = i / (float)seg * Mathf.PI * 2;
                var x = Mathf.Sin(a) * radius; var z = Mathf.Cos(a) * radius;
                v[i] = new Vector3(x, height / 2, z);
                v[i + seg] = new Vector3(x, -height / 2, z);
            }
            var tris = new System.Collections.Generic.List<int>();
            for (var i = 0; i < seg; i++)
            {
                var j = (i + 1) % seg;
                tris.AddRange(new[] { i, j, i + seg, j, j + seg, i + seg });
                if (i > 0 && i < seg - 1) { tris.AddRange(new[] { 0, i + 1, i }); tris.AddRange(new[] { seg, seg + i, seg + i + 1 }); }
            }
            var m = new Mesh { name = System.IO.Path.GetFileNameWithoutExtension(path), vertices = v, triangles = tris.ToArray() };
            m.RecalculateNormals();
            m.RecalculateBounds();
            AssetDatabase.CreateAsset(m, path);
            return m;
        }

        static Vector3 V3(JToken t, Vector3 fallback) =>
            t is JArray a && a.Count >= 3 ? new Vector3((float)a[0], (float)a[1], (float)a[2]) : fallback;

        static void SetLayer(Transform t, int layer)
        {
            t.gameObject.layer = layer;
            foreach (Transform c in t) SetLayer(c, layer);
        }

        internal static void EnsureFolder(string path)
        {
            if (AssetDatabase.IsValidFolder(path)) return;
            var parent = Path.GetDirectoryName(path)?.Replace('\\', '/');
            if (!string.IsNullOrEmpty(parent) && !AssetDatabase.IsValidFolder(parent)) EnsureFolder(parent);
            AssetDatabase.CreateFolder(parent, Path.GetFileName(path));
        }
    }
}
