using UnityEditor;
using UnityEngine;

namespace EOA.EditorTools
{
    /// <summary>
    /// Import rules for the Blender FX textures under Assets/Art/FX (see FxLibrary for the list): colour vs linear data,
    /// normal maps, wrap / mip settings per kind, 4K max for the sky panorama and band (2K elsewhere) and WebGL caps
    /// (sky 2048, everything else 1024).
    /// </summary>
    public sealed class FxTextureImport : AssetPostprocessor
    {
        /// <summary>Bump when the rules change: FxSetup reimports textures whose importer userData differs.</summary>
        public const string Version = "fx-import-2";

        public override uint GetVersion() => 2;

        void OnPreprocessTexture()
        {
            var p = assetPath.Replace('\\', '/');
            if (!p.Contains("/Art/FX/")) return;
            var ti = (TextureImporter)assetImporter;
            var name = System.IO.Path.GetFileNameWithoutExtension(p);
            ti.textureType = TextureImporterType.Default;
            ti.alphaIsTransparency = false;
            ti.alphaSource = TextureImporterAlphaSource.FromInput;
            ti.npotScale = TextureImporterNPOTScale.None;
            ti.isReadable = false;
            ti.anisoLevel = 1;
            ti.filterMode = FilterMode.Bilinear;
            ti.textureCompression = TextureImporterCompression.CompressedHQ;
            int max = 2048, web = 1024;
            var sRGB = false;
            var mips = true;
            var wrapU = TextureWrapMode.Clamp;
            var wrapV = TextureWrapMode.Clamp;
            if (name.EndsWith("_n"))
            {
                ti.textureType = TextureImporterType.NormalMap;
                wrapU = wrapV = TextureWrapMode.Repeat;
                ti.anisoLevel = 4;
                ti.filterMode = FilterMode.Trilinear;
            }
            else if (name == "sky_storm_pano")
            {
                sRGB = true; mips = false; max = 4096; web = 2048; wrapU = TextureWrapMode.Repeat;
            }
            else if (name == "sky_city_band")
            {
                sRGB = true; mips = false; max = 4096; web = 2048; wrapU = TextureWrapMode.Repeat;
            }
            else if (name == "sky_clouds" || name == "mist_tile" || name == "rain_streaks")
            {
                wrapU = wrapV = TextureWrapMode.Repeat;
                ti.filterMode = FilterMode.Trilinear;
                ti.anisoLevel = 2;
            }
            else if (name == "lightning_bolts")
            {
                mips = false;
            }
            ti.sRGBTexture = sRGB && ti.textureType != TextureImporterType.NormalMap;
            ti.mipmapEnabled = mips;
            ti.wrapModeU = wrapU;
            ti.wrapModeV = wrapV;
            ti.maxTextureSize = max;
            var webgl = ti.GetPlatformTextureSettings("WebGL");
            webgl.overridden = true;
            webgl.maxTextureSize = web;
            webgl.format = TextureImporterFormat.Automatic;
            webgl.textureCompression = TextureImporterCompression.Compressed;
            ti.SetPlatformTextureSettings(webgl);
        }
    }
}
