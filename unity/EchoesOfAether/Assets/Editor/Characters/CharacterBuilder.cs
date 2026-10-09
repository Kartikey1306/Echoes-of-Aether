using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;

namespace EOA.EditorTools
{
    /// <summary>
    /// Turns the Blender exports (Assets/Art/Characters/&lt;Name&gt;/&lt;Name&gt;.fbx + manifest + textures and
    /// Assets/Art/Animations/Anim_*.fbx) into URP materials, humanoid animator controllers and ready-to-spawn
    /// prefabs in Assets/Resources/Characters. Run from the menu or in batchmode:
    /// Unity -batchmode -projectPath . -executeMethod EOA.EditorTools.CharacterBuilder.BuildAll -quit
    /// </summary>
    public static class CharacterBuilder
    {
        const string CharRoot = "Assets/Art/Characters";
        const string AnimRoot = "Assets/Art/Animations";
        const string OutRoot = "Assets/Resources/Characters";

        [MenuItem("EOA/Build Characters")]
        public static void BuildAll()
        {
            Directory.CreateDirectory(OutRoot);
            ConfigureAnimations();
            // Mixamo clips from incoming/mixamo replace CMU clips of the same name (none present: all CMU).
            try { MixamoImporter.Import(); }
            catch (Exception e) { Debug.LogError($"[mixamo] import failed, building with CMU clips only: {e}"); }
            var male = BuildController("Male");
            var female = BuildController("Female");
            foreach (var dir in Directory.GetDirectories(CharRoot))
            {
                var name = Path.GetFileName(dir);
                var manifestPath = Path.Combine(dir, name + ".manifest.json");
                if (!File.Exists(manifestPath)) continue;
                try { BuildCharacter(dir, name, JObject.Parse(File.ReadAllText(manifestPath)), male, female); }
                catch (Exception e) { Debug.LogError($"[characters] {name}: {e}"); }
            }
            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();
            Debug.Log("[characters] build complete");
        }

        // ------------------------------------------------------------------ textures & materials

        static void ConfigureTexture(string path, bool normal, bool linear, bool readable, int maxSize = 2048)
        {
            var ti = AssetImporter.GetAtPath(path) as TextureImporter;
            if (ti == null) return;
            var dirty = false;
            void Set<T>(T cur, T want, Action<T> apply) { if (!EqualityComparer<T>.Default.Equals(cur, want)) { apply(want); dirty = true; } }
            Set(ti.textureType, normal ? TextureImporterType.NormalMap : TextureImporterType.Default, v => ti.textureType = v);
            Set(ti.sRGBTexture, !linear && !normal, v => ti.sRGBTexture = v);
            Set(ti.isReadable, readable, v => ti.isReadable = v);
            Set(ti.maxTextureSize, maxSize, v => ti.maxTextureSize = v);
            Set(ti.mipmapEnabled, true, v => ti.mipmapEnabled = v);
            Set(ti.alphaIsTransparency, !normal && !linear, v => ti.alphaIsTransparency = v);
            if (readable) Set(ti.textureCompression, TextureImporterCompression.Uncompressed, v => ti.textureCompression = v);
            if (dirty) ti.SaveAndReimport();
        }

        static Shader Lit => Shader.Find("Universal Render Pipeline/Lit");

        static Material MakeMat(string dir, string name, Action<Material> setup)
        {
            Directory.CreateDirectory(Path.Combine(dir, "Materials"));
            var path = Path.Combine(dir, "Materials", name + ".mat").Replace('\\', '/');
            var m = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (m == null)
            {
                m = new Material(Lit) { name = name };
                AssetDatabase.CreateAsset(m, path);
            }
            m.shader = Lit;
            setup(m);
            EditorUtility.SetDirty(m);
            return m;
        }

        static void AlphaClip(Material m, float cutoff = 0.5f, bool doubleSided = true)
        {
            m.SetFloat("_AlphaClip", 1);
            m.SetFloat("_Cutoff", cutoff);
            m.EnableKeyword("_ALPHATEST_ON");
            if (doubleSided) m.SetFloat("_Cull", 0);
            m.renderQueue = (int)UnityEngine.Rendering.RenderQueue.AlphaTest;
        }

        static void Emissive(Material m, Color c)
        {
            m.EnableKeyword("_EMISSION");
            m.SetColor("_EmissionColor", c);
            m.globalIlluminationFlags = MaterialGlobalIlluminationFlags.RealtimeEmissive;
        }

        static Texture2D Tex(string dir, string file) => string.IsNullOrEmpty(file) ? null : AssetDatabase.LoadAssetAtPath<Texture2D>(Path.Combine(dir, "Textures", file).Replace('\\', '/'));

        static Color Hex(string h) => ColorUtility.TryParseHtmlString(h, out var c) ? c : Color.gray;

        /// <summary>
        /// PBR maps from a manifest list [BaseColor, Normal, MaskMap] (MaskMap: R metallic, G occlusion, B paint mask,
        /// A smoothness). URP Lit reads metallic from R and smoothness from A of _MetallicGlossMap and occlusion from G
        /// of _OcclusionMap, so the same texture feeds both.
        /// </summary>
        static void PbrMaps(Material m, string dir, JArray files, bool baseMap = true, float bump = 1f, float occlusion = 1f)
        {
            if (files == null) return;
            string at(int i) => files.Count > i ? (string)files[i] : null;
            var bc = baseMap ? Tex(dir, at(0)) : null;
            if (bc != null) m.SetTexture("_BaseMap", bc);
            var nrm = Tex(dir, at(1));
            if (nrm != null) { m.SetTexture("_BumpMap", nrm); m.EnableKeyword("_NORMALMAP"); m.SetFloat("_BumpScale", bump); }
            var mask = at(2) != null && at(2).Contains("MaskMap") ? Tex(dir, at(2)) : null;
            if (mask == null) return;
            m.SetTexture("_MetallicGlossMap", mask);
            m.EnableKeyword("_METALLICSPECGLOSSMAP");
            m.SetFloat("_SmoothnessTextureChannel", 0);
            m.DisableKeyword("_SMOOTHNESS_TEXTURE_ALBEDO_CHANNEL_A");
            m.SetFloat("_Smoothness", 1f);
            m.SetTexture("_OcclusionMap", mask);
            m.EnableKeyword("_OCCLUSIONMAP");
            m.SetFloat("_OcclusionStrength", occlusion);
        }

        /// <summary>
        /// Shared hair shading (EOA/Hair): anisotropic dual highlight along the strand, wrapped diffuse, dithered alpha
        /// edge for TAA/FXAA; per-vertex strand data (root -> tip, inner occlusion) when the manifest's materialDefs
        /// mark the mesh with "strandData". Keeps _BaseMap / _BaseColor / _Cutoff / _Cull (runtime tint contract).
        /// </summary>
        static void HairShading(Material m, JObject manifest, string matName, float spec)
        {
            var sh = Shader.Find("EOA/Hair");
            if (sh == null || !sh.isSupported) return;
            var cutoff = m.GetFloat("_Cutoff");
            var tint = m.GetColor("_BaseColor");
            m.shader = sh;
            m.SetFloat("_Cutoff", cutoff);
            m.SetColor("_BaseColor", tint);
            m.SetFloat("_Cull", 0);
            m.SetFloat("_SpecStrength", spec);
            m.SetFloat("_Spec2Strength", spec * 3f);   // secondary lobe is hair-coloured (albedo-tinted)
            var def = (manifest["materialDefs"] as JObject)?[matName] as JObject;
            var strand = def?["strandData"] != null && (bool)def["strandData"];
            m.SetFloat("_StrandData", strand ? 1 : 0);
            if (strand) m.EnableKeyword("_STRAND_DATA"); else m.DisableKeyword("_STRAND_DATA");
            m.renderQueue = (int)UnityEngine.Rendering.RenderQueue.AlphaTest;
        }

        /// <summary>Tiled pore detail normal shared by the heroes' skin (Assets/Art/Characters/SkinDetail), or the
        /// character's own (manifest skinShading.poreMap).</summary>
        static Texture2D SkinPoreMap(string dir, JObject ss)
        {
            var own = (string)ss?["poreMap"];
            var path = !string.IsNullOrEmpty(own) ? Path.Combine(dir, "Textures", own).Replace('\\', '/') : "Assets/Art/Characters/SkinDetail/Skin_Pores_Normal.png";
            if (!File.Exists(path)) return null;
            var ti = AssetImporter.GetAtPath(path) as TextureImporter;
            if (ti != null && (ti.textureType != TextureImporterType.NormalMap || ti.wrapMode != TextureWrapMode.Repeat || ti.maxTextureSize != 1024))
            {
                ti.textureType = TextureImporterType.NormalMap;
                ti.wrapMode = TextureWrapMode.Repeat;
                ti.maxTextureSize = 1024;
                ti.mipmapEnabled = true;
                ti.SaveAndReimport();
            }
            return AssetDatabase.LoadAssetAtPath<Texture2D>(path);
        }

        static float Cutoff(JObject manifest, string key, float fallback) =>
            (float?)(manifest["hairAlphaCutoff"] as JObject)?[key] ?? (float?)(manifest["hairAlphaCutoff"] as JObject)?["default"] ?? fallback;

        /// <summary>Hair colour for characters that never receive an Appearance (NPCs): manifest tints, then palette.</summary>
        static Color? HairTint(JObject manifest)
        {
            var h = (string)manifest["tints"]?["hair"] ?? (string)manifest["palette"]?["hair"];
            return h != null ? Hex(h) : null;
        }

        /// <summary>Grey version of a coloured texture so hair can be tinted to any colour.</summary>
        static Texture2D Desaturated(string dir, string file)
        {
            var src = Path.Combine(dir, "Textures", file).Replace('\\', '/');
            var dst = Path.Combine(dir, "Textures", Path.GetFileNameWithoutExtension(file) + "_grey.png").Replace('\\', '/');
            if (!File.Exists(dst))
            {
                var t = new Texture2D(2, 2);
                t.LoadImage(File.ReadAllBytes(src));
                var px = t.GetPixels32();
                long sum = 0; var n = 0;
                foreach (var p in px) if (p.a > 128) { sum += (p.r + p.g + p.b) / 3; n++; }
                var mean = n > 0 ? sum / (float)n : 128;
                for (var i = 0; i < px.Length; i++)
                {
                    var l = (px[i].r + px[i].g + px[i].b) / 3f;
                    // Normalise mean brightness to ~0.75 so the tint colour reads true.
                    var v = (byte)Mathf.Clamp(l / Mathf.Max(1, mean) * 190f, 0, 255);
                    px[i] = new Color32(v, v, v, px[i].a);
                }
                t.SetPixels32(px);
                File.WriteAllBytes(dst, t.EncodeToPNG());
                UnityEngine.Object.DestroyImmediate(t);
                AssetDatabase.ImportAsset(dst);
            }
            ConfigureTexture(dst, false, false, false, 1024);
            return AssetDatabase.LoadAssetAtPath<Texture2D>(dst);
        }

        static Material MaterialFor(string dir, string matName, JObject manifest)
        {
            var textures = manifest["textures"] as JObject;
            string first(string m) => textures?[m] is JArray a && a.Count > 0 ? (string)a[0] : null;
            switch (matName)
            {
                case "Skin":
                    return MakeMat(dir, "Skin", m =>
                    {
                        m.SetTexture("_BaseMap", Tex(dir, "Skin_medium.png") ?? Tex(dir, "Skin_light.png"));
                        m.SetFloat("_Smoothness", 0.4f);
                        m.SetFloat("_Metallic", 0);
                        // HD skin: pore normal map and mask map (smoothness in A, cavity occlusion in G).
                        var maps = (manifest["skinMaps"] as JObject);
                        PbrMaps(m, dir, new JArray(null, (string)maps?["normal"] ?? "Skin_Normal.png", (string)maps?["maskMap"]), baseMap: false, bump: 1f, occlusion: 0.7f);
                        // Subsurface skin shader (falls back to URP Lit if it failed to compile).
                        var skin = Shader.Find("EOA/Skin");
                        if (skin != null && skin.isSupported)
                        {
                            m.shader = skin;
                            // Shared skin shading (EOA/Skin): red-tinted deep scattering, wrap, tiled pore detail normal.
                            // Per-character values come from the manifest ("skinShading"), the defaults suit both heroes.
                            var ss = manifest["skinShading"] as JObject;
                            float F(string k, float d) => ss?[k] != null ? (float)ss[k] : d;
                            m.SetColor("_SpecColor", ss?["sssTint"] is JArray st && st.Count >= 3
                                ? new Color((float)st[0], (float)st[1], (float)st[2]) : new Color(0.9f, 0.32f, 0.26f));
                            m.SetFloat("_ClearCoatMask", F("sssStrength", 0.6f));
                            m.SetFloat("_ClearCoatSmoothness", F("sssWrap", 0.55f));
                            var pores = SkinPoreMap(dir, ss);
                            m.SetTexture("_ParallaxMap", pores);
                            m.SetFloat("_Parallax", F("poreTiling", 20f));
                            m.SetFloat("_DetailNormalMapScale", pores != null ? F("poreStrength", 0.45f) : 0f);
                            m.DisableKeyword("_PARALLAXMAP");
                            // Tattoo ink designs use the detail albedo (x2) slot; keep the variant in builds.
                            m.EnableKeyword("_DETAIL_MULX2");
                        }
                        // Glowing tattoos: emission map from the manifest (keeps the _EMISSION variant in builds).
                        var tattoo = (string)manifest["tattoo"];
                        var tt = !string.IsNullOrEmpty(tattoo) ? Tex(dir, tattoo) : null;
                        if (tt != null)
                        {
                            m.SetTexture("_EmissionMap", tt);
                            m.EnableKeyword("_EMISSION");
                            m.globalIlluminationFlags = MaterialGlobalIlluminationFlags.RealtimeEmissive;
                            // Coloured design (Skin_Tattoo.png) for NPCs; heroes recolour it at runtime from the grey mask.
                            m.SetColor("_EmissionColor", Color.white * 2f);
                        }
                    });
                case "Eyes":
                    return MakeMat(dir, "Eyes", m =>
                    {
                        m.SetTexture("_BaseMap", Tex(dir, "Eye_grey.png"));
                        // Glossy enough for a crisp light catchlight, but without the environment reflection that
                        // washed the (tinted) iris out to sky blue.
                        m.SetFloat("_Smoothness", 0.78f);
                        m.SetFloat("_EnvironmentReflections", 0);
                        m.EnableKeyword("_ENVIRONMENTREFLECTIONS_OFF");
                        // Shared eye shading (EOA/Eye): iris parallax, limbal ring, wet cornea with a sharp highlight and
                        // a studio catchlight, upper-lid shadow (falls back to Lit if it failed to compile).
                        var eye = Shader.Find("EOA/Eye");
                        if (eye != null && eye.isSupported)
                        {
                            m.shader = eye;
                            m.SetFloat("_Smoothness", 0.93f);
                            m.SetFloat("_Parallax", 0.014f);
                            m.SetFloat("_ClearCoatMask", 0.75f);   // limbal ring (stronger iris contrast)
                            // Upper-lid shadow painted in eye space; lighter when the model has a real occlusion
                            // shell (EyeOcclusion mesh) that follows the actual lids.
                            var es = manifest["eyeShading"] as JObject;
                            m.SetFloat("_ClearCoatSmoothness", es?["lidShadow"] != null ? (float)es["lidShadow"] : 0.5f);
                            m.SetFloat("_DetailAlbedoMapScale", 0.9f);
                            m.SetFloat("_OcclusionStrength", 0.18f);
                            m.SetColor("_BaseColor", Color.white);
                        }
                    });
                case "EyeOcclusion":
                    return MakeMat(dir, matName, m =>
                    {
                        var sh = Shader.Find("EOA/EyeOcclusion");
                        if (sh != null && sh.isSupported) m.shader = sh;
                        m.SetFloat("_Strength", 0.8f);
                        m.renderQueue = (int)UnityEngine.Rendering.RenderQueue.Transparent - 20;
                    });
                case "EyeWet":
                    return MakeMat(dir, matName, m =>
                    {
                        var sh = Shader.Find("EOA/EyeWet");
                        if (sh != null && sh.isSupported) m.shader = sh;
                        m.renderQueue = (int)UnityEngine.Rendering.RenderQueue.Transparent - 19;
                    });
                case "Teeth":
                case "Tongue":
                    return MakeMat(dir, matName, m => { m.SetTexture("_BaseMap", Tex(dir, first(matName))); m.SetFloat("_Smoothness", 0.6f); });
                case "Brows":
                case "Lashes":
                    return MakeMat(dir, matName, m =>
                    {
                        m.SetTexture("_BaseMap", Desaturated(dir, first(matName)));
                        AlphaClip(m, Cutoff(manifest, matName, matName == "Lashes" ? 0.35f : 0.45f));
                        m.SetFloat("_Smoothness", 0.2f);
                        var hc = HairTint(manifest) ?? Hex("#2a2420");
                        m.SetColor("_BaseColor", Color.Lerp(hc, Color.black, matName == "Lashes" ? 0.5f : 0.15f));
                        HairShading(m, manifest, matName, matName == "Lashes" ? 0.03f : 0.05f);
                    });
                case "Boots":
                    return MakeMat(dir, "Boots", m =>
                    {
                        m.SetTexture("_BaseMap", Tex(dir, first("Boots")));
                        m.SetColor("_BaseColor", Color.white);
                        m.SetFloat("_Smoothness", 0.45f);
                        PbrMaps(m, dir, textures?["Boots"] as JArray);
                    });
                case "Garment_Top":
                case "Garment_Pants":
                    return MakeMat(dir, matName, m =>
                    {
                        var files = textures?[matName] as JArray;
                        var nrm = files != null && files.Count > 1 ? Tex(dir, (string)files[1]) : null;
                        if (nrm != null) { m.SetTexture("_BumpMap", nrm); m.EnableKeyword("_NORMALMAP"); }
                        m.SetColor("_BaseColor", Hex("#33363c"));
                        m.SetFloat("_Smoothness", 0.3f);
                    });
                // Hard-surface gear: baked BaseColor/Normal/MaskMap; the runtime tint multiplies the base colour
                // (Armor = appearance armour colour, Gloves = outfit × 0.75).
                case "Gloves":
                    return MakeMat(dir, matName, m =>
                    {
                        var gc = textures?["Gloves"] != null ? Color.Lerp(Color.black, Hex((string)manifest["palette"]?["outfit"] ?? "#5a5d63"), 0.75f) : Hex("#26272a");
                        m.SetColor("_BaseColor", gc);
                        m.SetFloat("_Smoothness", 0.45f);
                        PbrMaps(m, dir, textures?["Gloves"] as JArray);
                    });
                case "Armor":
                    return MakeMat(dir, matName, m =>
                    {
                        m.SetColor("_BaseColor", Hex((string)manifest["palette"]?["armor"] ?? "#4b4e54"));
                        m.SetFloat("_Metallic", 0.55f);
                        m.SetFloat("_Smoothness", 0.58f);
                        PbrMaps(m, dir, textures?["Armor"] as JArray);
                    });
                case "Metal": return MakeMat(dir, matName, m => { m.SetColor("_BaseColor", Hex("#8a8f96")); m.SetFloat("_Metallic", 0.9f); m.SetFloat("_Smoothness", 0.65f); });
                case "SuitSecondary": return MakeMat(dir, matName, m => { m.SetColor("_BaseColor", Hex("#202226")); m.SetFloat("_Smoothness", 0.3f); });
                case "Belt":
                case "Harness":
                case "Strap":
                    return MakeMat(dir, matName, m => { m.SetColor("_BaseColor", Hex("#3b3530")); m.SetFloat("_Smoothness", 0.4f); });
                case "Glow":
                case "Glow2":
                case "Screen":
                case "Lens":
                    return MakeMat(dir, matName, m =>
                    {
                        var c = matName == "Glow2" ? Hex("#a77bff") : Hex("#56b8ff");
                        m.SetColor("_BaseColor", Color.Lerp(c, Color.white, 0.3f));
                        Emissive(m, c * 2.2f);
                        m.SetFloat("_Smoothness", 0.8f);
                    });
                case "Holo":
                    // Translucent projected light (Kael's Aether sleeve): additive, unlit, double-sided. The tint follows the
                    // hero's glow colour at runtime (CharacterModel.Glow sets _EmissionColor).
                    return MakeMat(dir, matName, m =>
                    {
                        var holo = Shader.Find("EOA/HoloSleeve");
                        if (holo != null) m.shader = holo;
                        else Debug.LogWarning("[characters] EOA/HoloSleeve missing; Holo falls back to URP Lit");
                        m.SetTexture("_BaseMap", Tex(dir, first("Holo") ?? Path.GetFileName(dir) + "_Holo.png"));
                        m.SetColor("_EmissionColor", Hex("#00e5ff") * 3f);
                        m.renderQueue = (int)UnityEngine.Rendering.RenderQueue.Transparent;
                    });
                case "Gear": return MakeMat(dir, matName, m => { m.SetColor("_BaseColor", Hex("#3a3f46")); m.SetFloat("_Metallic", 0.3f); m.SetFloat("_Smoothness", 0.5f); });
                case "Scarf": return MakeMat(dir, matName, m => { m.SetColor("_BaseColor", Hex("#5a4a3a")); m.SetFloat("_Smoothness", 0.1f); });
            }
            if (matName.StartsWith("Hair_") || matName.StartsWith("Facial_"))
            {
                var f = first(matName);
                return MakeMat(dir, matName, m =>
                {
                    if (f != null) m.SetTexture("_BaseMap", Desaturated(dir, f));
                    AlphaClip(m, Cutoff(manifest, matName.Substring(matName.IndexOf('_') + 1), 0.4f));
                    m.SetFloat("_Smoothness", 0.3f);
                    if (HairTint(manifest) is { } hc) m.SetColor("_BaseColor", hc);
                    HairShading(m, manifest, matName, matName.StartsWith("Facial_") ? 0.06f : 0.1f);
                });
            }
            if (matName.StartsWith("Cloth_"))
            {
                var f = first(matName);
                return MakeMat(dir, matName, m =>
                {
                    if (f != null) m.SetTexture("_BaseMap", Tex(dir, f));
                    m.SetFloat("_Smoothness", 0.25f);
                    PbrMaps(m, dir, textures?[matName] as JArray, baseMap: false);
                });
            }
            return MakeMat(dir, matName, m => m.SetFloat("_Smoothness", 0.4f));
        }

        // ------------------------------------------------------------------ avatar

        static readonly (string mixamo, string human)[] MixamoMap =
        {
            ("Hips", "Hips"), ("Spine", "Spine"), ("Spine1", "Chest"), ("Spine2", "UpperChest"), ("Neck", "Neck"), ("Head", "Head"),
            ("LeftEye", "LeftEye"), ("RightEye", "RightEye"),
            ("LeftShoulder", "LeftShoulder"), ("LeftArm", "LeftUpperArm"), ("LeftForeArm", "LeftLowerArm"), ("LeftHand", "LeftHand"),
            ("RightShoulder", "RightShoulder"), ("RightArm", "RightUpperArm"), ("RightForeArm", "RightLowerArm"), ("RightHand", "RightHand"),
            ("LeftUpLeg", "LeftUpperLeg"), ("LeftLeg", "LeftLowerLeg"), ("LeftFoot", "LeftFoot"), ("LeftToeBase", "LeftToes"),
            ("RightUpLeg", "RightUpperLeg"), ("RightLeg", "RightLowerLeg"), ("RightFoot", "RightFoot"), ("RightToeBase", "RightToes"),
        };

        static readonly (string mixamo, string human)[] FingerMap =
        {
            ("Thumb", "Thumb"), ("Index", "Index"), ("Middle", "Middle"), ("Ring", "Ring"), ("Pinky", "Little"),
        };

        /// <summary>
        /// Human bone map from Mixamo bone names plus a skeleton taken from the FBX's current rest pose. Falls back to
        /// the importer's auto-configuration when the model has no Mixamo rig.
        /// </summary>
        internal static void ConfigureAvatar(ModelImporter mi, string fbxPath)
        {
            var hd = mi.humanDescription;
            var model = AssetDatabase.LoadAssetAtPath<GameObject>(fbxPath);
            var transforms = model != null ? model.GetComponentsInChildren<Transform>(true) : Array.Empty<Transform>();
            var byShort = new Dictionary<string, string>();
            foreach (var t in transforms)
            {
                var c = t.name.LastIndexOf(':');
                byShort[c >= 0 ? t.name.Substring(c + 1) : t.name] = t.name;
            }
            var bones = new List<HumanBone>();
            void Map(string mixamo, string human)
            {
                if (byShort.TryGetValue(mixamo, out var bone))
                    bones.Add(new HumanBone { humanName = human, boneName = bone, limit = new HumanLimit { useDefaultValues = true } });
            }
            foreach (var (m, h) in MixamoMap) Map(m, h);
            foreach (var side in new[] { "Left", "Right" })
                foreach (var (m, h) in FingerMap)
                    for (var i = 1; i <= 3; i++)
                        Map($"{side}Hand{m}{i}", $"{side} {h} {(i == 1 ? "Proximal" : i == 2 ? "Intermediate" : "Distal")}");
            if (bones.Count < 15 || !bones.Any(b => b.humanName == "LeftLowerLeg"))
            {
                // Not a Mixamo rig: let the importer auto-configure.
                hd.human = Array.Empty<HumanBone>();
                hd.skeleton = Array.Empty<SkeletonBone>();
                mi.humanDescription = hd;
                return;
            }
            hd.human = bones.ToArray();
            hd.skeleton = TPoseSkeleton(model, bones);
            if (hd.upperArmTwist == 0 && hd.lowerArmTwist == 0)
            {
                hd.upperArmTwist = 0.5f; hd.lowerArmTwist = 0.5f; hd.upperLegTwist = 0.5f; hd.lowerLegTwist = 0.5f;
                hd.armStretch = 0.05f; hd.legStretch = 0.05f; hd.feetSpacing = 0;
            }
            mi.humanDescription = hd;
        }

        /// <summary>
        /// The model's skeleton brought into a T-pose (arms horizontal, legs straight down), as Unity's humanoid muscle
        /// space expects; the rigs are authored in an A-pose. Taken from a temporary instance of the imported model.
        /// </summary>
        static SkeletonBone[] TPoseSkeleton(GameObject asset, List<HumanBone> map)
        {
            var inst = UnityEngine.Object.Instantiate(asset);
            try
            {
                var src = asset.GetComponentsInChildren<Transform>(true);
                var dst = inst.GetComponentsInChildren<Transform>(true);
                var byName = new Dictionary<string, Transform>();
                for (var i = 0; i < dst.Length && i < src.Length; i++) byName[src[i].name] = dst[i];
                Transform H(string human)
                {
                    foreach (var hb in map) if (hb.humanName == human) return byName.TryGetValue(hb.boneName, out var t) ? t : null;
                    return null;
                }
                void Aim(Transform bone, Transform child, Vector3 target)
                {
                    if (bone == null || child == null) return;
                    var d = child.position - bone.position;
                    if (d.sqrMagnitude < 1e-10f) return;
                    bone.rotation = Quaternion.FromToRotation(d, target) * bone.rotation;
                }
                var hips = H("Hips");
                foreach (var side in new[] { "Left", "Right" })
                {
                    var upper = H(side + "UpperArm");
                    if (upper != null && hips != null)
                    {
                        var outward = new Vector3(Mathf.Sign(upper.position.x - hips.position.x), 0, 0);
                        Aim(upper, H(side + "LowerArm"), outward);
                        Aim(H(side + "LowerArm"), H(side + "Hand"), outward);
                        Aim(H(side + "Hand"), H($"{side} Middle Proximal"), outward);
                    }
                    Aim(H(side + "UpperLeg"), H(side + "LowerLeg"), Vector3.down);
                    Aim(H(side + "LowerLeg"), H(side + "Foot"), Vector3.down);
                }
                var skeleton = new SkeletonBone[src.Length];
                for (var i = 0; i < src.Length; i++)
                    skeleton[i] = new SkeletonBone { name = src[i].name, position = dst[i].localPosition, rotation = dst[i].localRotation, scale = dst[i].localScale };
                return skeleton;
            }
            finally { UnityEngine.Object.DestroyImmediate(inst); }
        }

        // ------------------------------------------------------------------ characters

        static void BuildCharacter(string dir, string name, JObject manifest, AnimatorController maleCtrl, AnimatorController femaleCtrl)
        {
            dir = dir.Replace('\\', '/');
            foreach (var f in Directory.GetFiles(Path.Combine(dir, "Textures"), "*.png"))
            {
                var p = f.Replace('\\', '/');
                var fn = Path.GetFileName(p);
                // Generated desaturated hair copies are configured by Desaturated(); the eye texture (Eye_grey.png) is
                // a source texture that must be readable for the runtime iris tint.
                if (fn.EndsWith("_grey.png") && !fn.StartsWith("Eye_")) continue;
                var lower = fn.ToLowerInvariant();
                var normal = lower.Contains("normal") || lower.Contains("_nrm") || lower.Contains("objnorm") || lower.Contains("-norm") || lower.Contains("_norm.");
                // Linear data: garment composite masks, mask maps (metallic/occlusion/smoothness), spec and dye masks.
                var mask = fn.EndsWith("_Mask.png") || fn.Contains("MaskMap") || lower.Contains("spec") || fn.Contains("_Dye");
                var readable = fn.EndsWith("_Mask.png") || fn.StartsWith("Eye_");
                var hd = fn.StartsWith("Skin_") || fn.Contains("_Top_") || fn.Contains("_Armor_") || fn.Contains("_Pants_")
                         || fn.Contains("_Gear_") || fn.Contains("_Boots_") || fn.Contains("_Gloves_");
                ConfigureTexture(p, normal, mask, readable, hd ? 2048 : 1024);
            }
            var fbxPath = $"{dir}/{name}.fbx";
            var mi = AssetImporter.GetAtPath(fbxPath) as ModelImporter;
            if (mi == null) throw new Exception("missing " + fbxPath);
            // Materials referenced by the meshes.
            var matNames = new HashSet<string>();
            foreach (JObject m in manifest["meshes"]) foreach (var mn in m["materials"]) matNames.Add((string)mn);
            var mats = matNames.ToDictionary(n => n, n => MaterialFor(dir, n, manifest));
            mi.animationType = ModelImporterAnimationType.Human;
            mi.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
            // Fresh avatar on every build: a HumanDescription kept from an earlier export of this model holds the old
            // bone lengths/orientations and mis-retargets every clip ("Avatar Rig Configuration mis-match").
            // The bone map comes from the Mixamo names (deterministic; the auto-mapper can fail on extra garment
            // bones) and the skeleton from the FBX as it is now.
            ConfigureAvatar(mi, fbxPath);
            mi.importBlendShapes = true;
            // Blend shapes keep the base normals: recalculated shape normals break at the open edges of the stripped
            // body mesh and drew pale halos around lids, mouth and nostrils whenever a face slider moved.
            mi.importBlendShapeNormals = ModelImporterNormals.None;
            mi.importAnimation = false;
            mi.optimizeGameObjects = false;
            mi.materialImportMode = ModelImporterMaterialImportMode.ImportStandard;
            mi.materialLocation = ModelImporterMaterialLocation.InPrefab;
            // Drop remaps for materials the current FBX no longer has (garments removed in a rebuild).
            foreach (var id in mi.GetExternalObjectMap().Keys.ToList())
                if (id.type == typeof(Material) && !mats.ContainsKey(id.name)) mi.RemoveRemap(id);
            foreach (var kv in mats) mi.AddRemap(new AssetImporter.SourceAssetIdentifier(typeof(Material), kv.Key), kv.Value);
            mi.SaveAndReimport();

            var model = AssetDatabase.LoadAssetAtPath<GameObject>(fbxPath);
            var go = (GameObject)PrefabUtility.InstantiatePrefab(model);
            try
            {
                go.name = name;
                var female = (string)manifest["gender"] == "female";
                var anim = go.GetComponent<Animator>() ?? go.AddComponent<Animator>();
                anim.runtimeAnimatorController = female ? femaleCtrl : maleCtrl;
                anim.applyRootMotion = false;
                anim.cullingMode = AnimatorCullingMode.CullUpdateTransforms;
                var cm = go.GetComponent<CharacterModel>() ?? go.AddComponent<CharacterModel>();
                cm.CharacterId = (string)manifest["character"];
                cm.Female = female;
                cm.Npc = (bool?)manifest["npc"] ?? false;
                cm.Echo = (bool?)manifest["echo"] ?? false;
                cm.BaseHeight = (float?)manifest["height"] ?? 1.8f;
                cm.Animator = anim;
                cm.Renderers = go.GetComponentsInChildren<SkinnedMeshRenderer>(true);
                cm.HairStyles = (manifest["hairStyles"] as JArray)?.Select(x => (string)x).ToArray() ?? Array.Empty<string>();
                cm.FacialHair = (manifest["facialHair"] as JArray)?.Select(x => (string)x).ToArray() ?? Array.Empty<string>();
                cm.DefaultHair = (string)manifest["defaultHair"] ?? "short";
                var skins = manifest["skins"] as JObject;
                cm.SkinTones = new[] { "light", "medium", "tan", "dark" }.Select(t => skins?[t] != null ? Tex(dir, (string)skins[t]) : null).ToArray();
                cm.EyeTexture = Tex(dir, "Eye_grey.png");
                // Runtime tattoo glow (recoloured by Appearance.Tattoo): the grey mask when present, else the coloured map.
                var tattoo = (string)manifest["tattooMask"] ?? (string)manifest["tattoo"];
                cm.TattooMap = !string.IsNullOrEmpty(tattoo) ? Tex(dir, tattoo) ?? Tex(dir, (string)manifest["tattoo"]) : null;
                cm.Garments = new[] { "Top", "Pants" }
                    .Where(p => File.Exists($"{dir}/Textures/{name}_{p}_Mask.png"))
                    .Select(p => new CharacterModel.GarmentTextures { Material = "Garment_" + p, Mask = Tex(dir, $"{name}_{p}_Mask.png"), Normal = Tex(dir, $"{name}_{p}_Normal.png") })
                    .ToArray();
                // Only the default hair/facial hair is visible in the prefab.
                foreach (var r in cm.Renderers)
                {
                    r.updateWhenOffscreen = false;
                    r.skinnedMotionVectors = true;
                    if (r.name.StartsWith("Hair_")) r.gameObject.SetActive(r.name == "Hair_" + cm.DefaultHair);
                    // Heroes choose facial hair in the designer; NPCs (no Appearance) wear their manifest facial hair.
                    if (r.name.StartsWith("Facial_")) r.gameObject.SetActive(cm.Npc && cm.FacialHair.Contains(r.name.Substring("Facial_".Length)));
                    // Brows and lashes shadowing the eyes darkened them; they don't need to cast.
                    if (r.name == "Brows" || r.name == "Lashes") r.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
                }
                // Hero deformation drivers: twist bones (manifest "twistBones", else defaults) and pose correctives
                // (manifest "correctives"); removed again when the rig has neither (NPCs).
                var twist = go.GetComponent<TwistBones>() ?? go.AddComponent<TwistBones>();
                var nTwist = twist.Configure(go.transform, (manifest["twistBones"] as JArray)?.Select(t => new TwistBones.Entry
                    { Bone = (string)t["bone"], Source = (string)t["source"], Reference = (string)t["reference"], Weight = (float?)t["weight"] ?? 0.5f, Mode = (string)t["mode"] ?? "follow" }));
                if (nTwist == 0) UnityEngine.Object.DestroyImmediate(twist);
                var corr = go.GetComponent<CorrectiveShapes>() ?? go.AddComponent<CorrectiveShapes>();
                var nCorr = corr.Configure(go.transform, (manifest["correctives"] as JArray)?.Select(c => new CorrectiveShapes.Entry
                {
                    Shape = (string)c["shape"], Bone = (string)c["bone"], Parent = (string)c["parent"], Child = (string)c["child"],
                    Axis = c["axis"] is JArray ax && ax.Count >= 3 ? new Vector3((float)ax[0], (float)ax[1], (float)ax[2]) : Vector3.right,
                    From = (float?)c["from"] ?? 30f, To = (float?)c["to"] ?? 120f, Power = (float?)c["power"] ?? 1f,
                }));
                if (nCorr == 0) UnityEngine.Object.DestroyImmediate(corr);
                if (nTwist + nCorr > 0) Debug.Log($"[characters] {name}: {nTwist} twist bones, {nCorr} corrective shapes");
                PrefabUtility.SaveAsPrefabAsset(go, $"{OutRoot}/{name}.prefab");
                Debug.Log($"[characters] {name}: {cm.Renderers.Length} renderers, {mats.Count} materials");
            }
            finally { UnityEngine.Object.DestroyImmediate(go); }
        }

        // ------------------------------------------------------------------ animations

        static JObject ClipMeta() => JObject.Parse(File.ReadAllText($"{AnimRoot}/clips_meta.json"));

        static void ConfigureAnimations()
        {
            var meta = ClipMeta();
            foreach (var style in new[] { "Male", "Female" })
            {
                var path = $"{AnimRoot}/Anim_{style}.fbx";
                var mi = AssetImporter.GetAtPath(path) as ModelImporter;
                if (mi == null) { Debug.LogError("missing " + path); continue; }
                mi.animationType = ModelImporterAnimationType.Human;
                mi.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
                ConfigureAvatar(mi, path); // same deterministic bone map as the characters
                mi.importAnimation = true;
                mi.materialImportMode = ModelImporterMaterialImportMode.None;
                var styleMeta = (JObject)meta[style.ToLowerInvariant()];
                var takes = mi.importedTakeInfos;
                var clips = new List<ModelImporterClipAnimation>();
                foreach (var t in takes)
                {
                    var clipName = t.name.Contains("|") ? t.name.Substring(t.name.LastIndexOf('|') + 1) : t.name;
                    var info = styleMeta[clipName] as JObject;
                    var c = new ModelImporterClipAnimation
                    {
                        name = clipName,
                        takeName = t.name,
                        firstFrame = t.startTime * t.sampleRate,
                        lastFrame = t.stopTime * t.sampleRate,
                        loopTime = info != null && (bool)info["loop"],
                        loopPose = false,
                        lockRootRotation = true,
                        lockRootHeightY = true,
                        lockRootPositionXZ = true,
                        keepOriginalOrientation = true,
                        keepOriginalPositionY = true,
                        keepOriginalPositionXZ = true,
                        heightFromFeet = false,
                    };
                    var dur = Mathf.Max(0.001f, t.stopTime - t.startTime);
                    if (info?["events"] is JArray evs)
                        c.events = evs.Select(e => new AnimationEvent
                        {
                            time = Mathf.Clamp01((float)e["t"] / (float)info["duration"]),
                            functionName = "OnAnimEvent",
                            stringParameter = (string)e["name"],
                        }).ToArray();
                    clips.Add(c);
                }
                mi.clipAnimations = clips.ToArray();
                mi.SaveAndReimport();
                // Force the clip post-processing (MocapNeckFix) to run even when the import settings didn't change.
                AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceUpdate);
            }
            // Posture: measure the hunched clips on the hero rigs and solve their spine / neck / head offsets; re-import
            // when an offset moved (two rounds: solve, then verify).
            for (var round = 0; round < 2; round++)
            {
                var log = new System.Text.StringBuilder();
                var changed = false;
                foreach (var style in new[] { "Male", "Female" }) changed |= MocapPosture.Calibrate(style, LoadCmuClips(style), log);
                Debug.Log($"[characters] posture calibration round {round + 1}{(changed ? " (offsets updated, re-importing)" : " (all in band)")}\n{log}");
                if (!changed) break;
                foreach (var style in new[] { "Male", "Female" }) AssetDatabase.ImportAsset($"{AnimRoot}/Anim_{style}.fbx", ImportAssetOptions.ForceUpdate);
            }
        }

        internal static Dictionary<string, AnimationClip> LoadCmuClips(string style) =>
            AssetDatabase.LoadAllAssetsAtPath($"{AnimRoot}/Anim_{style}.fbx").OfType<AnimationClip>()
                .Where(c => !c.name.StartsWith("__preview__")).GroupBy(c => c.name).ToDictionary(g => g.Key, g => g.First());

        /// <summary>The clips a style's controller uses: the Mixamo clip of a name when one was imported, else CMU.</summary>
        internal static Dictionary<string, AnimationClip> LoadClips(string style)
        {
            var clips = LoadCmuClips(style);
            foreach (var kv in MixamoImporter.ClipsFor(style)) clips[kv.Key] = kv.Value;
            return clips;
        }

        public static readonly string[] LoopActions = { "talk", "npc_crossed", "npc_hips", "npc_work", "npc_look", "sit", "kneel_work", "lie", "aim_r", "aim_l", "climb" };

        static AvatarMask UpperBodyMask()
        {
            var path = $"{AnimRoot}/UpperBody.mask";
            var mask = AssetDatabase.LoadAssetAtPath<AvatarMask>(path);
            if (mask == null) { mask = new AvatarMask(); AssetDatabase.CreateAsset(mask, path); }
            for (var i = 0; i < (int)AvatarMaskBodyPart.LastBodyPart; i++)
            {
                var part = (AvatarMaskBodyPart)i;
                var upper = part == AvatarMaskBodyPart.Body || part == AvatarMaskBodyPart.Head || part == AvatarMaskBodyPart.LeftArm || part == AvatarMaskBodyPart.RightArm
                            || part == AvatarMaskBodyPart.LeftFingers || part == AvatarMaskBodyPart.RightFingers || part == AvatarMaskBodyPart.LeftHandIK || part == AvatarMaskBodyPart.RightHandIK;
                mask.SetHumanoidBodyPartActive(part, upper);
            }
            EditorUtility.SetDirty(mask);
            return mask;
        }

        static AnimatorController BuildController(string style)
        {
            var clips = LoadClips(style);
            var path = $"{AnimRoot}/Humanoid_{style}.controller";
            AssetDatabase.DeleteAsset(path);
            var ac = AnimatorController.CreateAnimatorControllerAtPath(path);
            ac.AddParameter("Speed", AnimatorControllerParameterType.Float);
            ac.AddParameter("Grounded", AnimatorControllerParameterType.Bool);
            ac.AddParameter("Combat", AnimatorControllerParameterType.Bool);
            ac.AddParameter("VerticalSpeed", AnimatorControllerParameterType.Float);
            ac.AddParameter("MoveSpeedMul", AnimatorControllerParameterType.Float);
            ac.AddParameter("ActionSpeed", AnimatorControllerParameterType.Float);
            ac.AddParameter("Crouch", AnimatorControllerParameterType.Bool);
            // Float parameters default to 0; speed multipliers must start at 1.
            var ps = ac.parameters;
            foreach (var p in ps) if (p.name == "MoveSpeedMul" || p.name == "ActionSpeed") p.defaultFloat = 1f;
            ac.parameters = ps;
            AnimationClip C(string n) => clips.TryGetValue(n, out var c) ? c : null;

            // Base layer: locomotion blend trees (relaxed and combat stance), jump and fall.
            var baseSm = ac.layers[0].stateMachine;
            var gaits = MixamoImporter.Gaits(style, C);
            MixamoImporter.RecordLocomotion(style, gaits);
            foreach (var g in gaits)
                Debug.Log($"[characters] {style} {g.Clip}: {g.Source} authored {g.Authored:0.00} m/s, threshold {g.Threshold:0.00}, time scale {g.TimeScale:0.00}");
            BlendTree Tree(string name, string idle)
            {
                var tree = new BlendTree { name = name, blendType = BlendTreeType.Simple1D, blendParameter = "Speed", useAutomaticThresholds = false };
                AssetDatabase.AddObjectToAsset(tree, ac);
                if (C(idle) != null) tree.AddChild(C(idle), 0f);
                // Thresholds are the speeds Hero moves at (2.2 / 5.2 / 7.6 m/s); each clip plays at game speed ÷ the
                // speed its feet were authored for (CMU: 1.9 / 5.0 / 7.4; Mixamo: measured from the stride) so the
                // planted foot does not slide (MixamoImporter.Gaits).
                foreach (var g in gaits) tree.AddChild(C(g.Clip), g.Threshold);
                var ch = tree.children;
                for (var i = 0; i < ch.Length; i++)
                    foreach (var g in gaits)
                        if (ch[i].motion == C(g.Clip)) ch[i].timeScale = g.TimeScale;
                tree.children = ch;
                return tree;
            }
            var loco = baseSm.AddState("Locomotion");
            loco.motion = Tree("LocomotionTree", "idle");
            loco.speedParameterActive = true; loco.speedParameter = "MoveSpeedMul";
            loco.iKOnFeet = true;
            var combat = baseSm.AddState("CombatLocomotion");
            combat.motion = Tree("CombatTree", "combat_idle");
            combat.speedParameterActive = true; combat.speedParameter = "MoveSpeedMul";
            combat.iKOnFeet = true;
            var jump = baseSm.AddState("Jump"); jump.motion = C("jump");
            var fall = baseSm.AddState("Fall"); fall.motion = C("fall");
            var land = baseSm.AddState("Land"); land.motion = C("land");
            baseSm.defaultState = loco;
            AnimatorStateTransition T(AnimatorState a, AnimatorState b, float dur, bool exit = false, float exitTime = 0.9f)
            {
                var t = a.AddTransition(b);
                t.duration = dur; t.hasExitTime = exit; t.exitTime = exitTime; t.hasFixedDuration = true;
                return t;
            }
            T(loco, combat, 0.25f).AddCondition(AnimatorConditionMode.If, 0, "Combat");
            T(combat, loco, 0.4f).AddCondition(AnimatorConditionMode.IfNot, 0, "Combat");
            foreach (var g in new[] { loco, combat })
            {
                var tj = T(g, jump, 0.08f); tj.AddCondition(AnimatorConditionMode.IfNot, 0, "Grounded"); tj.AddCondition(AnimatorConditionMode.Greater, 1.5f, "VerticalSpeed");
                var tf = T(g, fall, 0.2f); tf.AddCondition(AnimatorConditionMode.IfNot, 0, "Grounded"); tf.AddCondition(AnimatorConditionMode.Less, -3f, "VerticalSpeed");
            }
            T(jump, fall, 0.25f, true, 0.85f);
            T(jump, land, 0.06f).AddCondition(AnimatorConditionMode.If, 0, "Grounded");
            T(fall, land, 0.06f).AddCondition(AnimatorConditionMode.If, 0, "Grounded");
            // Moving on landing goes straight into the gait (no wait for the landing clip's exit time).
            foreach (var (to, inCombat) in new[] { (loco, false), (combat, true) })
            {
                var run = T(land, to, 0.1f);
                run.AddCondition(AnimatorConditionMode.Greater, 1.2f, "Speed");
                run.AddCondition(inCombat ? AnimatorConditionMode.If : AnimatorConditionMode.IfNot, 0, "Combat");
            }
            T(land, loco, 0.15f, true, 0.6f).AddCondition(AnimatorConditionMode.IfNot, 0, "Combat");
            T(land, combat, 0.15f, true, 0.6f).AddCondition(AnimatorConditionMode.If, 0, "Combat");

            // Crouch stance (Hero crouch toggle): crouch_idle → crouch_walk at the crouched move speed.
            if (C("crouch_idle") != null && C("crouch_walk") != null)
            {
                var crouchTree = new BlendTree { name = "CrouchTree", blendType = BlendTreeType.Simple1D, blendParameter = "Speed", useAutomaticThresholds = false };
                AssetDatabase.AddObjectToAsset(crouchTree, ac);
                crouchTree.AddChild(C("crouch_idle"), 0f);
                var cg = MixamoImporter.CrouchGait(style, C("crouch_walk"));
                crouchTree.AddChild(C("crouch_walk"), cg.Threshold);
                var cch = crouchTree.children;
                cch[1].timeScale = cg.TimeScale;
                crouchTree.children = cch;
                Debug.Log($"[characters] {style} crouch_walk: authored {cg.Authored:0.00} m/s, threshold {cg.Threshold:0.00}, time scale {cg.TimeScale:0.00}");
                var crouch = baseSm.AddState("CrouchLocomotion");
                crouch.motion = crouchTree;
                crouch.speedParameterActive = true; crouch.speedParameter = "MoveSpeedMul";
                crouch.iKOnFeet = true;
                foreach (var g in new[] { loco, combat }) T(g, crouch, 0.22f).AddCondition(AnimatorConditionMode.If, 0, "Crouch");
                var up = T(crouch, loco, 0.22f); up.AddCondition(AnimatorConditionMode.IfNot, 0, "Crouch"); up.AddCondition(AnimatorConditionMode.IfNot, 0, "Combat");
                var upC = T(crouch, combat, 0.22f); upC.AddCondition(AnimatorConditionMode.IfNot, 0, "Crouch"); upC.AddCondition(AnimatorConditionMode.If, 0, "Combat");
                var cf = T(crouch, fall, 0.2f); cf.AddCondition(AnimatorConditionMode.IfNot, 0, "Grounded"); cf.AddCondition(AnimatorConditionMode.Less, -3f, "VerticalSpeed");
            }

            // Action layer (full body override): one state per action clip, played from code by name.
            var actionLayer = new AnimatorControllerLayer { name = "Action", defaultWeight = 1f, blendingMode = AnimatorLayerBlendingMode.Override, stateMachine = new AnimatorStateMachine { name = "Action" } };
            AssetDatabase.AddObjectToAsset(actionLayer.stateMachine, ac);
            ac.AddLayer(actionLayer);
            var asm = actionLayer.stateMachine;
            var empty = asm.AddState("Empty");
            asm.defaultState = empty;
            var locoNames = new HashSet<string> { "idle", "walk", "run", "sprint", "jump", "fall", "land", "combat_idle", "aim_r", "aim_l", "fire_r", "fire_l", "crouch_idle", "crouch_walk" };
            foreach (var kv in clips)
            {
                if (locoNames.Contains(kv.Key)) continue;
                var s = asm.AddState(kv.Key);
                s.motion = kv.Value;
                s.speedParameterActive = true;
                s.speedParameter = "ActionSpeed";
                if (!LoopActions.Contains(kv.Key) && kv.Key != "death")
                {
                    var back = s.AddTransition(empty);
                    back.hasExitTime = true; back.exitTime = 0.92f; back.duration = 0.14f; back.hasFixedDuration = true;
                }
            }

            // Upper-body layer: aiming / firing bolts while moving.
            var mask = UpperBodyMask();
            var upper = new AnimatorControllerLayer { name = "UpperBody", defaultWeight = 1f, avatarMask = mask, blendingMode = AnimatorLayerBlendingMode.Override, stateMachine = new AnimatorStateMachine { name = "UpperBody" } };
            AssetDatabase.AddObjectToAsset(upper.stateMachine, ac);
            ac.AddLayer(upper);
            // Foot IK / look-at (HumanoidPolish) needs the IK pass on the base layer.
            var allLayers = ac.layers;
            allLayers[0].iKPass = true;
            ac.layers = allLayers;
            var usm = upper.stateMachine;
            var uEmpty = usm.AddState("Empty");
            usm.defaultState = uEmpty;
            foreach (var n in new[] { "aim_r", "aim_l", "fire_r", "fire_l" })
            {
                if (C(n) == null) continue;
                var s = usm.AddState(n);
                s.motion = C(n);
                if (n.StartsWith("fire"))
                {
                    var back = s.AddTransition(uEmpty);
                    back.hasExitTime = true; back.exitTime = 0.9f; back.duration = 0.1f; back.hasFixedDuration = true;
                }
            }
            EditorUtility.SetDirty(ac);
            AssetDatabase.SaveAssets();
            var bySource = clips.GroupBy(kv => MixamoImporter.SourceOf(kv.Value)).OrderBy(g => g.Key)
                .Select(g => $"{g.Count()} {g.Key}{(g.Key == "cmu" ? "" : ": " + string.Join(", ", g.Select(kv => kv.Key).OrderBy(n => n)))}");
            Debug.Log($"[characters] controller {style}: {clips.Count} clips ({string.Join("; ", bySource)})");
            return ac;
        }
    }
}
