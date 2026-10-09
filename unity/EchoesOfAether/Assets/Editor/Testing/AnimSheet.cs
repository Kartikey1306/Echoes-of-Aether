using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace EOA.EditorTools
{
    /// <summary>
    /// Renders every hero animation clip on the hero prefabs into contact sheets (Captures/anim_sheet_&lt;hero&gt;.png):
    /// one cell per clip at 35% and 70% of its length, front three-quarter view. Catches retarget problems (twisted
    /// torsos, flipped limbs, broken wrists) that the idle-only hero captures miss.
    /// Unity -batchmode -quit -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.AnimSheet.Run
    /// </summary>
    public static class AnimSheet
    {
        const int CellW = 220, CellH = 300;

        [MenuItem("EOA/Test/Animation Contact Sheet")]
        public static void Run()
        {
            var outDir = Path.GetFullPath(Path.Combine(Application.dataPath, "../../../Captures"));
            Directory.CreateDirectory(outDir);
            foreach (var (hero, style) in new[] { ("Kael", "Male"), ("Lyra", "Female") })
            {
                var prefab = Resources.Load<GameObject>("Characters/" + hero);
                // The clips the controller uses (Mixamo where imported, else CMU).
                var clips = CharacterBuilder.LoadClips(style).Values.OrderBy(c => c.name).ToArray();
                if (prefab == null || clips.Length == 0) { Debug.LogError($"[animsheet] missing {hero} or clips"); continue; }

                var go = Object.Instantiate(prefab);
                go.transform.position = new Vector3(0, -800, 0);
                // Batch-mode edit renders do not run skinning: the meshes stayed in the bind pose whatever the sampled
                // clip. Each visible skinned mesh is baked into a static proxy per cell instead.
                var skins = go.GetComponentsInChildren<SkinnedMeshRenderer>().Where(r => r.enabled && r.gameObject.activeInHierarchy && r.sharedMesh != null).ToArray();
                var proxies = skins.Select(r =>
                {
                    var p = new GameObject(r.name + "_baked");
                    p.AddComponent<MeshFilter>().sharedMesh = new Mesh();
                    p.AddComponent<MeshRenderer>().sharedMaterials = r.sharedMaterials;
                    return p;
                }).ToArray();
                foreach (var r in skins) r.forceRenderingOff = true;
                var camGo = new GameObject("SheetCam");
                var cam = camGo.AddComponent<Camera>();
                cam.clearFlags = CameraClearFlags.SolidColor;
                cam.backgroundColor = new Color(0.16f, 0.18f, 0.22f);
                cam.fieldOfView = 30;
                var lightGo = new GameObject("SheetKey");
                var key = lightGo.AddComponent<Light>();
                key.type = LightType.Directional;
                key.intensity = 1.4f;
                lightGo.transform.rotation = Quaternion.Euler(35, 150, 0);
                var rt = new RenderTexture(CellW, CellH, 24);
                cam.targetTexture = rt;

                const int perRow = 8;
                var cells = clips.Length * 2;
                var rows = (cells + perRow - 1) / perRow;
                var sheet = new Texture2D(CellW * perRow, CellH * rows, TextureFormat.RGB24, false);
                var cell = new Texture2D(CellW, CellH, TextureFormat.RGB24, false);
                var idx = 0;
                foreach (var clip in clips)
                    foreach (var f in new[] { 0.35f, 0.7f })
                    {
                        clip.SampleAnimation(go, clip.length * f);
                        for (var k = 0; k < skins.Length; k++)
                        {
                            skins[k].BakeMesh(proxies[k].GetComponent<MeshFilter>().sharedMesh, true);
                            proxies[k].transform.SetPositionAndRotation(skins[k].transform.position, skins[k].transform.rotation);
                        }
                        // Frame the hips: humanoid clips can move the root.
                        var anim = go.GetComponent<Animator>();
                        var hips = anim != null ? anim.GetBoneTransform(HumanBodyBones.Hips) : go.transform;
                        var c = hips.position;
                        cam.transform.position = c + new Vector3(2.2f, 0.35f, 3.6f);
                        cam.transform.LookAt(c + Vector3.up * 0.05f);
                        cam.Render();
                        RenderTexture.active = rt;
                        cell.ReadPixels(new Rect(0, 0, CellW, CellH), 0, 0);
                        cell.Apply();
                        RenderTexture.active = null;
                        var x = idx % perRow * CellW;
                        var y = (rows - 1 - idx / perRow) * CellH;
                        sheet.SetPixels(x, y, CellW, CellH, cell.GetPixels());
                        idx++;
                    }
                sheet.Apply();
                var path = Path.Combine(outDir, $"anim_sheet_{hero.ToLowerInvariant()}.png");
                File.WriteAllBytes(path, sheet.EncodeToPNG());
                File.WriteAllText(Path.ChangeExtension(path, ".txt"), string.Join("\n", clips.Select((c, i) => $"{i * 2,3}-{i * 2 + 1,-3} {c.name}")));
                Debug.Log($"[animsheet] {hero}: {clips.Length} clips -> {path}");
                foreach (var p in proxies) { Object.DestroyImmediate(p.GetComponent<MeshFilter>().sharedMesh); Object.DestroyImmediate(p); }
                Object.DestroyImmediate(go); Object.DestroyImmediate(camGo); Object.DestroyImmediate(lightGo);
                rt.Release();
            }
        }
    }
}
