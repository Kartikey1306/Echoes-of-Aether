using UnityEditor;
using UnityEngine;

namespace EOA.EditorTools
{
    /// <summary>
    /// Ground-truth check of the hard-light shader: renders Kael's blade mesh with a WeaponLibrary material (no post,
    /// HDR target) in an empty scene and logs the average / max linear colour it writes. Batch:
    ///   Unity -batchmode -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.HardLightProbe.Run -quit
    /// </summary>
    public static class HardLightProbe
    {
        [MenuItem("EOA/Weapons/Hard-light Probe")]
        public static void Run()
        {
            var mesh = WeaponLibrary.FxMesh("kael_blade_hull");
            var tmpl = AssetDatabase.LoadAssetAtPath<Material>("Assets/Art/Weapons/Materials/weapon_hardlight.mat");
            Debug.Log($"[probe] mesh {(mesh != null ? mesh.name + " v" + mesh.vertexCount + " colors " + mesh.colors.Length : "null")} template {(tmpl != null ? tmpl.shader.name + " supported " + tmpl.shader.isSupported : "null")}");
            if (mesh == null) return;
            var body = CombatMath.Hex(0x2ec0ff);
            var mat = WeaponLibrary.HardLight(FxMaterials.Hdr(body, 0.42f), FxMaterials.Hdr(Color.Lerp(body, Color.white, 0.7f), 0.9f), 1f, 0);
            mat.SetFloat("_EdgeBoost", 1.2f);
            Debug.Log($"[probe] mat {mat.shader.name} _Color {mat.GetColor("_Color")} _CoreColor {mat.GetColor("_CoreColor")} _Intensity {mat.GetFloat("_Intensity")} _Mode {mat.GetFloat("_Mode")} _Extend {mat.GetFloat("_Extend")} colorspace {QualitySettings.activeColorSpace}");
            var camGo = new GameObject("probe_cam");
            var cam = camGo.AddComponent<Camera>();
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = Color.black;
            cam.allowHDR = true;
            cam.transform.SetPositionAndRotation(new Vector3(0.6f, 0.15f, 0.5f), Quaternion.LookRotation(new Vector3(-0.6f, -0.15f, 0f)));
            cam.fieldOfView = 60f;
            var go = new GameObject("probe_blade");
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            go.AddComponent<MeshRenderer>().sharedMaterial = mat;
            go.transform.rotation = Quaternion.Euler(0, 0, 90);
            var rt = new RenderTexture(256, 256, 24, RenderTextureFormat.ARGBHalf);
            cam.targetTexture = rt;
            cam.Render();
            var prev = RenderTexture.active;
            RenderTexture.active = rt;
            var tex = new Texture2D(256, 256, TextureFormat.RGBAHalf, false, true);
            tex.ReadPixels(new Rect(0, 0, 256, 256), 0, 0);
            tex.Apply();
            RenderTexture.active = prev;
            var px = tex.GetPixels();
            Color sum = Color.black, max = Color.black;
            int n = 0;
            foreach (var c in px)
            {
                if (c.r + c.g + c.b < 1e-3f) continue;
                sum += c;
                n++;
                max = new Color(Mathf.Max(max.r, c.r), Mathf.Max(max.g, c.g), Mathf.Max(max.b, c.b));
            }
            Debug.Log($"[probe] covered px {n} avg {(n > 0 ? sum / n : Color.black)} max {max}");
            Object.DestroyImmediate(camGo);
            Object.DestroyImmediate(go);
            Object.DestroyImmediate(tex);
            rt.Release();
        }
    }
}
