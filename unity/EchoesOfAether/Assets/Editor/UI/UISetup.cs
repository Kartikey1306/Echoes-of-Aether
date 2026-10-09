using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEngine;
using UnityEngine.TextCore.LowLevel;
using UnityEngine.TextCore.Text;
using UnityEngine.UIElements;
using FontAsset = UnityEngine.TextCore.Text.FontAsset;

namespace EOA.EditorTools
{
    /// <summary>
    /// Creates the UI assets from script: TextCore SDF font assets for the OFL fonts, the PanelSettings
    /// (ScaleWithScreenSize 1920x1080, match 0.5, EOA theme), panel text settings with glyph fallbacks, and the
    /// Resources/UI/UIRefs asset used by UIManager.Create. Menu: Tools/EOA/Setup UI.
    /// Batchmode: Unity -batchmode -quit -projectPath . -executeMethod EOA.EditorTools.UISetup.Run
    /// </summary>
    public static class UISetup
    {
        public const string UiDir = "Assets/UI";
        public const string FontsDir = "Assets/UI/Fonts";
        public const string ThemePath = "Assets/UI/EOA_Theme.tss";
        public const string MainUss = "Assets/UI/Styles/eoa.uss";
        public const string FontsUss = "Assets/UI/Styles/eoa_fonts.uss";
        public const string PanelSettingsPath = "Assets/UI/EOA_PanelSettings.asset";
        public const string TextSettingsPath = "Assets/UI/EOA_TextSettings.asset";
        public const string RefsPath = "Assets/Resources/UI/UIRefs.asset";

        static readonly string[] FontFiles =
        {
            "Inter/Inter-Regular", "Inter/Inter-Medium", "Inter/Inter-SemiBold", "Inter/Inter-Italic",
            "Rajdhani/Rajdhani-Medium", "Rajdhani/Rajdhani-SemiBold", "Rajdhani/Rajdhani-Bold",
        };

        [MenuItem("Tools/EOA/Setup UI")]
        public static void Run()
        {
            try
            {
                AssetDatabase.Refresh();
                ReimportTextures();
                var fonts = CreateFontAssets();
                RewriteFontStyles(fonts);
                var text = CreateTextSettings(fonts);
                var ps = CreatePanelSettings(text);
                CreateRefs(ps);
                ValidateIcons();
                AssetDatabase.SaveAssets();
                AssetDatabase.Refresh();
                Debug.Log("[ui-setup] UI assets ready: " + PanelSettingsPath);
            }
            catch (Exception e)
            {
                Debug.LogError("[ui-setup] failed: " + e);
                if (Application.isBatchMode) EditorApplication.Exit(1);
            }
        }

        // ------------------------------------------------------------------ Textures

        static void ReimportTextures()
        {
            foreach (var dir in new[] { "Assets/UI/Textures", "Assets/Resources/UI/Icons" })
            {
                if (!AssetDatabase.IsValidFolder(dir)) continue;
                foreach (var guid in AssetDatabase.FindAssets("t:Texture2D", new[] { dir }))
                    AssetDatabase.ImportAsset(AssetDatabase.GUIDToAssetPath(guid), ImportAssetOptions.ForceUpdate);
            }
        }

        // ------------------------------------------------------------------ Fonts

        static Dictionary<string, FontAsset> CreateFontAssets()
        {
            var result = new Dictionary<string, FontAsset>();
            foreach (var f in FontFiles)
            {
                var ttf = $"{FontsDir}/{f}.ttf";
                var assetPath = $"{FontsDir}/{f}_SDF.asset";
                var existing = AssetDatabase.LoadAssetAtPath<FontAsset>(assetPath);
                if (existing != null) { result[f] = existing; continue; }
                var font = AssetDatabase.LoadAssetAtPath<Font>(ttf);
                if (font == null)
                {
                    Debug.LogWarning($"[ui-setup] missing font file {ttf}");
                    continue;
                }
                var fa = CreateDynamicFontAsset(font);
                if (fa == null)
                {
                    Debug.LogWarning($"[ui-setup] could not create a font asset for {ttf}; the UI keeps using the TTF.");
                    continue;
                }
                var name = Path.GetFileNameWithoutExtension(assetPath);
                fa.name = name;
                AssetDatabase.CreateAsset(fa, assetPath);
                // Atlas textures and material must be sub-assets so they survive serialization.
                var atlases = fa.atlasTextures;
                if (atlases != null)
                    for (var i = 0; i < atlases.Length; i++)
                    {
                        if (atlases[i] == null || AssetDatabase.Contains(atlases[i])) continue;
                        atlases[i].name = name + " Atlas" + (i > 0 ? " " + i : "");
                        AssetDatabase.AddObjectToAsset(atlases[i], fa);
                    }
                var mat = fa.material;
                if (mat != null && !AssetDatabase.Contains(mat))
                {
                    mat.name = name + " Material";
                    AssetDatabase.AddObjectToAsset(mat, fa);
                }
                EditorUtility.SetDirty(fa);
                result[f] = fa;
            }
            AssetDatabase.SaveAssets();

            // Rajdhani lacks arrows and check marks: fall back to Inter SemiBold.
            if (result.TryGetValue("Inter/Inter-SemiBold", out var interSemi))
                foreach (var kv in result.Where(k => k.Key.StartsWith("Rajdhani")))
                {
                    kv.Value.fallbackFontAssetTable = new List<FontAsset> { interSemi };
                    EditorUtility.SetDirty(kv.Value);
                }
            return result;
        }

        /// <summary>Dynamic SDF font asset (90 pt sampling, 9 px padding, 1024 atlas, multi-atlas).</summary>
        static FontAsset CreateDynamicFontAsset(Font font)
        {
            try { return FontAsset.CreateFontAsset(font, 90, 9, GlyphRenderMode.SDFAA, 1024, 1024, AtlasPopulationMode.Dynamic, true); }
            catch (Exception e)
            {
                Debug.LogWarning($"[ui-setup] CreateFontAsset failed for {font.name}: {e.Message}");
                return null;
            }
        }

        /// <summary>Add "-unity-font-definition" (SDF asset) next to every "-unity-font" (TTF) in eoa_fonts.uss.</summary>
        static void RewriteFontStyles(Dictionary<string, FontAsset> fonts)
        {
            if (!File.Exists(FontsUss)) return;
            var src = File.ReadAllText(FontsUss);
            src = Regex.Replace(src, @"[ \t]*-unity-font-definition:[^\n]*\n", "");
            var outText = Regex.Replace(src, @"([ \t]*)-unity-font: url\(""\.\./Fonts/([^""]+)\.ttf""\);", m =>
            {
                var key = m.Groups[2].Value;
                var line = m.Value;
                if (!fonts.ContainsKey(key)) return line;
                return $"{line}\n{m.Groups[1].Value}-unity-font-definition: url(\"../Fonts/{key}_SDF.asset\");";
            });
            if (outText == File.ReadAllText(FontsUss)) return;
            File.WriteAllText(FontsUss, outText);
            AssetDatabase.ImportAsset(FontsUss, ImportAssetOptions.ForceUpdate);
            AssetDatabase.ImportAsset(ThemePath, ImportAssetOptions.ForceUpdate);
        }

        static PanelTextSettings CreateTextSettings(Dictionary<string, FontAsset> fonts)
        {
            var ts = AssetDatabase.LoadAssetAtPath<PanelTextSettings>(TextSettingsPath);
            if (ts == null)
            {
                ts = ScriptableObject.CreateInstance<PanelTextSettings>();
                AssetDatabase.CreateAsset(ts, TextSettingsPath);
            }
            if (fonts.TryGetValue("Inter/Inter-Regular", out var regular)) ts.defaultFontAsset = regular;
            var fallback = new List<FontAsset>();
            if (fonts.TryGetValue("Inter/Inter-SemiBold", out var semi)) fallback.Add(semi);
            if (regular != null) fallback.Add(regular);
            if (fallback.Count > 0) ts.fallbackFontAssets = fallback;
            EditorUtility.SetDirty(ts);
            return ts;
        }

        // ------------------------------------------------------------------ Panel settings & refs

        static PanelSettings CreatePanelSettings(PanelTextSettings text)
        {
            var ps = AssetDatabase.LoadAssetAtPath<PanelSettings>(PanelSettingsPath);
            if (ps == null)
            {
                ps = ScriptableObject.CreateInstance<PanelSettings>();
                AssetDatabase.CreateAsset(ps, PanelSettingsPath);
            }
            ps.scaleMode = PanelScaleMode.ScaleWithScreenSize;
            ps.referenceResolution = new Vector2Int(1920, 1080);
            ps.screenMatchMode = PanelScreenMatchMode.MatchWidthOrHeight;
            ps.match = 0.5f;
            ps.sortingOrder = 100;
            ps.clearColor = false;
            AssetDatabase.ImportAsset(ThemePath, ImportAssetOptions.ForceUpdate);
            var theme = AssetDatabase.LoadAssetAtPath<ThemeStyleSheet>(ThemePath);
            if (theme == null) Debug.LogWarning($"[ui-setup] theme not found at {ThemePath}; UIManager will add the style sheets itself");
            ps.themeStyleSheet = theme;
            if (text != null) ps.textSettings = text;
            EditorUtility.SetDirty(ps);
            return ps;
        }

        static void CreateRefs(PanelSettings ps)
        {
            if (!AssetDatabase.IsValidFolder("Assets/Resources/UI"))
            {
                if (!AssetDatabase.IsValidFolder("Assets/Resources")) AssetDatabase.CreateFolder("Assets", "Resources");
                AssetDatabase.CreateFolder("Assets/Resources", "UI");
            }
            var refs = AssetDatabase.LoadAssetAtPath<UIRefs>(RefsPath);
            if (refs == null)
            {
                refs = ScriptableObject.CreateInstance<UIRefs>();
                AssetDatabase.CreateAsset(refs, RefsPath);
            }
            refs.PanelSettings = ps;
            refs.StyleSheets = new[] { AssetDatabase.LoadAssetAtPath<StyleSheet>(MainUss), AssetDatabase.LoadAssetAtPath<StyleSheet>(FontsUss) }
                .Where(s => s != null).ToArray();
            EditorUtility.SetDirty(refs);
        }

        // ------------------------------------------------------------------ Validation

        /// <summary>Warn about icon ids used by the game data that have no rasterized PNG.</summary>
        static void ValidateIcons()
        {
            try
            {
                GameData.EnsureLoaded();
                var ids = new HashSet<string>();
                foreach (var i in GameData.ItemList) if (!string.IsNullOrEmpty(i.Icon)) ids.Add(i.Icon);
                foreach (var p in GameData.PowerupList) if (!string.IsNullOrEmpty(p.Icon)) ids.Add(p.Icon);
                foreach (var a in GameData.AbilityList) if (!string.IsNullOrEmpty(a.Icon)) ids.Add(a.Icon);
                foreach (var extra in new[] { "ab_bolt", "lock", "swap", "unknown" }) ids.Add(extra);
                var missing = ids.Where(id => AssetDatabase.LoadAssetAtPath<Texture2D>($"Assets/Resources/UI/Icons/{id}.png") == null).ToList();
                if (missing.Count > 0) Debug.LogWarning("[ui-setup] missing icons: " + string.Join(", ", missing));
            }
            catch (Exception e) { Debug.LogWarning("[ui-setup] icon validation skipped: " + e.Message); }
        }
    }

    /// <summary>Import settings for UI textures and icons: uncompressed, clamped, alpha is transparency.</summary>
    public sealed class UITextureImporter : AssetPostprocessor
    {
        void OnPreprocessTexture()
        {
            var icons = assetPath.StartsWith("Assets/Resources/UI/Icons/");
            if (!icons && !assetPath.StartsWith("Assets/UI/Textures/")) return;
            var ti = (TextureImporter)assetImporter;
            ti.textureType = TextureImporterType.Default;
            ti.alphaSource = TextureImporterAlphaSource.FromInput;
            ti.alphaIsTransparency = true;
            ti.sRGBTexture = true;
            ti.mipmapEnabled = icons;
            ti.wrapMode = TextureWrapMode.Clamp;
            ti.filterMode = FilterMode.Bilinear;
            ti.npotScale = TextureImporterNPOTScale.None;
            ti.textureCompression = TextureImporterCompression.Uncompressed;
        }
    }
}
