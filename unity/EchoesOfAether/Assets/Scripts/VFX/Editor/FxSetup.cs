using System.IO;
using UnityEditor;
using UnityEngine;

namespace EOA.EditorTools
{
    /// <summary>
    /// Template materials for the FX shaders in Assets/Art/FX/Resources/FX/Materials (Resources keep EOA/RainStreaks and
    /// EOA/FxParticle in player builds; FxLibrary / RainField clone them). Idempotent. Menu: EOA/FX/Create FX Materials.
    /// Batch: -executeMethod EOA.EditorTools.FxSetup.Run
    /// </summary>
    public static class FxSetup
    {
        const string Dir = "Assets/Art/FX/Resources/FX/Materials";

        [MenuItem("EOA/FX/Create FX Materials")]
        public static void Run()
        {
            Directory.CreateDirectory(Dir);
            Make("EOA/RainStreaks", "RainStreaks");
            Make("EOA/FxParticle", "FxParticle");
            AssetDatabase.SaveAssets();
            // Textures imported before FxTextureImport existed (or after its rules changed) get reimported once.
            foreach (var guid in AssetDatabase.FindAssets("t:Texture2D", new[] { "Assets/Art/FX" }))
            {
                var p = AssetDatabase.GUIDToAssetPath(guid);
                if (AssetImporter.GetAtPath(p) is TextureImporter ti && ti.userData != FxTextureImport.Version)
                {
                    ti.userData = FxTextureImport.Version;
                    ti.SaveAndReimport();
                }
            }
        }

        static void Make(string shaderName, string file)
        {
            var path = $"{Dir}/{file}.mat";
            var sh = Shader.Find(shaderName);
            if (sh == null) { Debug.LogError($"[fx] shader {shaderName} failed to compile"); return; }
            var m = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (m != null) { if (m.shader != sh) m.shader = sh; EditorUtility.SetDirty(m); return; }
            AssetDatabase.CreateAsset(new Material(sh) { name = file }, path);
        }
    }
}
