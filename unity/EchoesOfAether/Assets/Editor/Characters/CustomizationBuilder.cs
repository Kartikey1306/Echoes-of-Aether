using System.IO;
using UnityEditor;
using UnityEngine;

namespace EOA.EditorTools
{
    /// <summary>
    /// Import settings for the customization library (Resources/Characters/Custom): tattoo ink maps are linear
    /// (detail albedo ×2: 0.5 grey = unchanged skin), glow maps sRGB, thumbnails UI-friendly, attachment FBX keep
    /// blendshapes and skeleton without animation. Run as part of EOA/Setup Project (All).
    /// </summary>
    public static class CustomizationBuilder
    {
        const string Root = "Assets/Resources/Characters/Custom";

        [MenuItem("EOA/Build Customization Library")]
        public static void Build()
        {
            if (!AssetDatabase.IsValidFolder(Root)) { Debug.Log("[custom] no customization library yet"); return; }
            int tex = 0, models = 0;
            foreach (var f in Directory.GetFiles(Root, "*.*", SearchOption.AllDirectories))
            {
                var p = f.Replace('\\', '/');
                if (p.EndsWith(".meta")) continue;
                var imp = AssetImporter.GetAtPath(p);
                if (imp is TextureImporter ti)
                {
                    var name = Path.GetFileNameWithoutExtension(p);
                    if (p.Contains("/Thumbs/"))
                    {
                        ti.textureType = TextureImporterType.Default;
                        ti.sRGBTexture = true; ti.mipmapEnabled = false; ti.alphaIsTransparency = true; ti.maxTextureSize = 256;
                    }
                    else if (name.EndsWith("_Ink")) { ti.sRGBTexture = false; ti.maxTextureSize = 2048; }
                    else if (name.EndsWith("_Glow")) { ti.sRGBTexture = true; ti.maxTextureSize = 2048; }
                    else if (name.EndsWith("_Hair"))
                    {
                        // Alpha-tested hair cards: keep alpha coverage in the mips so hair doesn't thin out with distance.
                        ti.sRGBTexture = true; ti.alphaIsTransparency = true; ti.mipmapEnabled = true; ti.maxTextureSize = 2048;
                        ti.mipMapsPreserveCoverage = true; ti.alphaTestReferenceValue = 0.4f;
                    }
                    else if (name.Contains("Normal") || name.EndsWith("_N")) ti.textureType = TextureImporterType.NormalMap;
                    else if (name.Contains("MaskMap") || name.Contains("_ORM")) { ti.sRGBTexture = false; ti.alphaSource = TextureImporterAlphaSource.FromInput; }
                    ti.SetPlatformTextureSettings(new TextureImporterPlatformSettings { name = "WebGL", overridden = true, maxTextureSize = Mathf.Min(ti.maxTextureSize, 1024), format = TextureImporterFormat.Automatic });
                    ti.SaveAndReimport();
                    tex++;
                }
                else if (imp is ModelImporter mi)
                {
                    // Generic (no avatar) keeps SkinnedMeshRenderers and their bones for skinned hair/armour; with
                    // None the skinning is dropped. Rigid items lose the generated Animator at attach time.
                    mi.animationType = ModelImporterAnimationType.Generic;
                    mi.avatarSetup = ModelImporterAvatarSetup.NoAvatar;
                    mi.importAnimation = false;
                    mi.importBlendShapes = true;
                    mi.importCameras = false;
                    mi.importLights = false;
                    mi.SaveAndReimport();
                    models++;
                }
            }
            Debug.Log($"[custom] customization library: {models} models, {tex} textures");
        }
    }
}
