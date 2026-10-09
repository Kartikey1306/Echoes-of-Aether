using System.IO;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;

namespace EOA.EditorTools
{
    /// <summary>
    /// Import rules for the Blender weapon assets (blender/weapons/build_weapons.py):
    /// FBX in Assets/Resources/Weapons (metres, imported normals, Mikk tangents, no animation, material slots remapped
    /// to the materials in Assets/Art/Weapons/Materials) and the baked atlases in Assets/Art/Weapons/Textures
    /// (BaseColor sRGB, MetalSmooth / Occlusion linear, Normal as normal map).
    /// </summary>
    public sealed class WeaponImportRules : AssetPostprocessor
    {
        public const string ResDir = "Assets/Resources/Weapons/";
        public const string TexDir = "Assets/Art/Weapons/Textures/";
        public const string MatDir = "Assets/Art/Weapons/Materials/";
        public static readonly string[] MaterialSlots = { "hero_pbr", "hero_glow", "enemy_pbr", "enemy_glow", "hardlight" };

        void OnPreprocessModel()
        {
            if (!assetPath.StartsWith(ResDir)) return;
            var mi = (ModelImporter)assetImporter;
            mi.globalScale = 1f;
            mi.useFileScale = true;
            // build_weapons.py exports with "Apply Transform": vertex data is already in the authored Unity space
            // (x right, y up, z forward) and nodes are identity. (WeaponLibrary also tolerates leftover node transforms.)
            mi.bakeAxisConversion = false;
            mi.importBlendShapes = false;
            mi.importCameras = false;
            mi.importLights = false;
            mi.importVisibility = false;
            mi.animationType = ModelImporterAnimationType.None;
            mi.importAnimation = false;
            // FX meshes may need their node transform baked at runtime (WeaponLibrary.FxMesh)
            mi.isReadable = assetPath.EndsWith("weapon_fx.fbx");
            mi.importNormals = ModelImporterNormals.Import;
            mi.importTangents = ModelImporterTangents.CalculateMikk;
            mi.meshCompression = ModelImporterMeshCompression.Off;
            mi.materialImportMode = ModelImporterMaterialImportMode.ImportViaMaterialDescription;
            mi.materialLocation = ModelImporterMaterialLocation.InPrefab;
            foreach (var slot in MaterialSlots)
            {
                var m = AssetDatabase.LoadAssetAtPath<Material>(MatDir + (slot == "hardlight" ? "weapon_hardlight" : slot) + ".mat");
                if (m != null) mi.AddRemap(new AssetImporter.SourceAssetIdentifier(typeof(Material), slot), m);
            }
        }

        void OnPreprocessTexture()
        {
            if (!assetPath.StartsWith(TexDir)) return;
            var ti = (TextureImporter)assetImporter;
            var n = Path.GetFileNameWithoutExtension(assetPath);
            ti.maxTextureSize = 2048;
            ti.mipmapEnabled = true;
            ti.anisoLevel = 4;
            ti.textureCompression = TextureImporterCompression.CompressedHQ;
            if (n.EndsWith("_Normal"))
            {
                ti.textureType = TextureImporterType.NormalMap;
                ti.sRGBTexture = false;
            }
            else
            {
                ti.textureType = TextureImporterType.Default;
                ti.sRGBTexture = n.EndsWith("_BaseColor");
                ti.alphaSource = n.EndsWith("_MetalSmooth") ? TextureImporterAlphaSource.FromInput : TextureImporterAlphaSource.None;
                ti.alphaIsTransparency = false;
            }
        }
    }

    /// <summary>Creates / refreshes the weapon materials and reimports the weapon models (menu or batch).</summary>
    public static class WeaponAssets
    {
        [MenuItem("EOA/Weapons/Rebuild Weapon Materials")]
        public static void Build()
        {
            Directory.CreateDirectory(WeaponImportRules.MatDir);
            AssetDatabase.Refresh();
            foreach (var t in Directory.GetFiles(WeaponImportRules.TexDir, "*.png"))
                AssetDatabase.ImportAsset(t.Replace('\\', '/'), ImportAssetOptions.ForceUpdate);
            Pbr("hero_pbr", "hero");
            Pbr("enemy_pbr", "enemy");
            Glow("hero_glow", new Color(0.37f, 0.85f, 1f));
            Glow("enemy_glow", new Color(1f, 0.35f, 0.2f));
            var hl = Shader.Find("EOA/HardLight");
            if (hl != null) Save(new Material(hl) { name = "weapon_hardlight" }, WeaponImportRules.MatDir + "weapon_hardlight.mat");
            else Debug.LogError("[weapons] EOA/HardLight shader missing");
            var holo = Shader.Find("EOA/Hologram");
            if (holo != null) Save(new Material(holo) { name = "weapon_holo" }, WeaponImportRules.ResDir + "weapon_holo.mat");
            AssetDatabase.SaveAssets();
            foreach (var f in Directory.GetFiles(WeaponImportRules.ResDir, "*.fbx"))
                AssetDatabase.ImportAsset(f.Replace('\\', '/'), ImportAssetOptions.ForceUpdate);
            AssetDatabase.SaveAssets();
            Report();
            Debug.Log("[weapons] materials rebuilt and weapon models reimported");
        }

        /// <summary>Log each weapon model's node transforms, mesh bounds and anchors (import sanity check).</summary>
        [MenuItem("EOA/Weapons/Report Weapon Imports")]
        public static void Report()
        {
            foreach (var f in Directory.GetFiles(WeaponImportRules.ResDir, "*.fbx"))
            {
                var go = AssetDatabase.LoadAssetAtPath<GameObject>(f.Replace('\\', '/'));
                if (go == null) continue;
                var sb = new System.Text.StringBuilder();
                sb.Append($"[weapons] import {go.name}: root rot {go.transform.localEulerAngles} scale {go.transform.localScale}");
                foreach (var t in go.GetComponentsInChildren<Transform>(true))
                {
                    if (t == go.transform) continue;
                    var mf = t.GetComponent<MeshFilter>();
                    sb.Append($"\n   {t.name} pos {t.localPosition.ToString("F3")} rot {t.localEulerAngles.ToString("F1")} scale {t.localScale.ToString("F2")}");
                    if (mf != null && mf.sharedMesh != null) sb.Append($" mesh bounds c{mf.sharedMesh.bounds.center.ToString("F3")} s{mf.sharedMesh.bounds.size.ToString("F3")} tris {mf.sharedMesh.triangles.Length / 3}");
                }
                var rmf = go.GetComponent<MeshFilter>();
                if (rmf != null && rmf.sharedMesh != null) sb.Append($"\n   (root mesh) bounds c{rmf.sharedMesh.bounds.center.ToString("F3")} s{rmf.sharedMesh.bounds.size.ToString("F3")}");
                Debug.Log(sb.ToString());
            }
        }

        static Texture2D Tex(string atlas, string kind) =>
            AssetDatabase.LoadAssetAtPath<Texture2D>(WeaponImportRules.TexDir + atlas + "_" + kind + ".png");

        static void Pbr(string name, string atlas)
        {
            var sh = Shader.Find("Universal Render Pipeline/Lit");
            var m = new Material(sh) { name = name };
            m.SetTexture("_BaseMap", Tex(atlas, "BaseColor"));
            m.SetColor("_BaseColor", Color.white);
            m.SetTexture("_BumpMap", Tex(atlas, "Normal"));
            m.SetFloat("_BumpScale", 1f);
            m.SetTexture("_MetallicGlossMap", Tex(atlas, "MetalSmooth"));
            m.SetFloat("_Metallic", 1f);
            m.SetFloat("_Smoothness", 1f);
            m.SetFloat("_SmoothnessTextureChannel", 0f);
            m.SetTexture("_OcclusionMap", Tex(atlas, "Occlusion"));
            m.SetFloat("_OcclusionStrength", 1f);
            m.SetFloat("_EnvironmentReflections", 1f);
            m.SetFloat("_SpecularHighlights", 1f);
            m.EnableKeyword("_NORMALMAP");
            m.EnableKeyword("_METALLICSPECGLOSSMAP");
            m.EnableKeyword("_OCCLUSIONMAP");
            m.DisableKeyword("_SMOOTHNESS_TEXTURE_ALBEDO_CHANNEL_A");
            // Hit flashes / pulses can drive emission on instances.
            m.EnableKeyword("_EMISSION");
            m.SetColor("_EmissionColor", Color.black);
            m.globalIlluminationFlags = MaterialGlobalIlluminationFlags.None;
            Save(m, WeaponImportRules.MatDir + name + ".mat");
        }

        static void Glow(string name, Color c)
        {
            var sh = Shader.Find("Universal Render Pipeline/Unlit");
            var m = new Material(sh) { name = name };
            m.SetColor("_BaseColor", c.linear * 2.2f);
            Save(m, WeaponImportRules.MatDir + name + ".mat");
        }

        static void Save(Material m, string path)
        {
            var existing = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (existing != null)
            {
                existing.shader = m.shader;
                existing.CopyPropertiesFromMaterial(m);
                existing.shaderKeywords = m.shaderKeywords;
                EditorUtility.SetDirty(existing);
                Object.DestroyImmediate(m);
            }
            else AssetDatabase.CreateAsset(m, path);
        }
    }
}
