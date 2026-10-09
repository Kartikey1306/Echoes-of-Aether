using System;
using System.IO;
using System.Reflection;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace EOA.EditorTools
{
    /// <summary>
    /// Studio capture of a hero prefab for concept comparison: an empty scene with a light-grey cyclorama, soft studio
    /// key / fill / rim lights, ACES tonemapping, the hero with its default appearance standing in the idle pose (arms
    /// down), front / three-quarter / back views written to Captures/hero_concept/.
    /// Unity -batchmode -projectPath . -executeMethod EOA.EditorTools.HeroConceptCapture.Run [-hero kael]
    /// (batch mode: captures in play mode and exits by itself, so no -quit; the menu item captures in edit mode)
    /// </summary>
    public static class HeroConceptCapture
    {
        const string Key = "eoa_hero_concept_capture";
        static int frames;
        static string pendingHero;

        [MenuItem("EOA/Test/Hero Concept Capture")]
        public static void Run()
        {
            var args = Environment.GetCommandLineArgs();
            var hero = "kael";
            for (var i = 0; i < args.Length - 1; i++) if (args[i] == "-hero") hero = args[i + 1];
            // Batch mode: an edit-mode Camera.Render() comes back black (nothing is drawn), so capture in play mode
            // (like GivaConceptShot) and exit when done. Run it WITHOUT -quit in batch mode.
            if (Application.isBatchMode && !EditorApplication.isPlaying)
            {
                EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
                SessionState.SetString(Key + "_hero", hero);
                SessionState.SetBool(Key, true);
                EditorApplication.EnterPlaymode();
                return;
            }
            Capture(hero);
        }

        [InitializeOnLoadMethod]
        static void Hook()
        {
            EditorApplication.playModeStateChanged += s =>
            {
                if (s != PlayModeStateChange.EnteredPlayMode || !SessionState.GetBool(Key, false)) return;
                SessionState.SetBool(Key, false);
                pendingHero = SessionState.GetString(Key + "_hero", "kael");
                frames = 0;
                EditorApplication.update += Tick;
            };
        }

        static GameObject heroInst;
        static Animator heroAnim;

        static void Tick()
        {
            frames++;
            try
            {
                if (frames == 3)
                {
                    // the menu's upright stance: HeroStance on the full body (legs too) over the idle
                    (heroInst, heroAnim) = Setup(pendingHero, true);
                    return;
                }
                if (frames < 75) return;
            }
            catch (Exception e) { Debug.LogError("[concept] " + e); frames = 1000; }
            EditorApplication.update -= Tick;
            var failed = heroInst == null;
            var asyncPrev = ShaderUtil.allowAsyncCompilation;
            ShaderUtil.allowAsyncCompilation = false;            // no cyan placeholder shaders in the shots
            try { if (!failed) Shoot(pendingHero, heroInst, heroAnim); }
            catch (Exception e) { Debug.LogError("[concept] " + e); failed = true; }
            finally { ShaderUtil.allowAsyncCompilation = asyncPrev; }
            EditorApplication.ExitPlaymode();
            if (Application.isBatchMode) EditorApplication.delayCall += () => EditorApplication.Exit(failed ? 1 : 0);
        }

        static void Capture(string hero)
        {
            var (inst, anim) = Setup(hero, false);
            if (inst != null) Shoot(hero, inst, anim);
        }

        static (GameObject, Animator) Setup(string hero, bool stance)
        {
            if (!EditorApplication.isPlaying) EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            // backdrop: floor + curved wall (light grey, matte)
            var grey = new Material(Shader.Find("Universal Render Pipeline/Lit"));
            grey.SetColor("_BaseColor", new Color(0.66f, 0.67f, 0.7f));
            grey.SetFloat("_Smoothness", 0.15f);
            var floor = GameObject.CreatePrimitive(PrimitiveType.Plane);
            floor.transform.localScale = new Vector3(4, 1, 4);
            floor.GetComponent<Renderer>().sharedMaterial = grey;
            var wall = GameObject.CreatePrimitive(PrimitiveType.Plane);
            wall.transform.position = new Vector3(0, 3, 2.6f);
            wall.transform.rotation = Quaternion.Euler(-90, 0, 0);
            wall.transform.localScale = new Vector3(4, 1, 4);
            wall.GetComponent<Renderer>().sharedMaterial = grey;

            // lights: soft key from the upper left front, fill from the right, two cool rims behind
            Light L(string name, LightType t, Vector3 pos, Vector3 aim, float intensity, Color c, float range = 12f, float angle = 60f)
            {
                var go = new GameObject(name);
                var l = go.AddComponent<Light>();
                l.type = t; l.intensity = intensity; l.color = c; l.range = range; l.spotAngle = angle;
                l.shadows = t == LightType.Directional ? LightShadows.Soft : LightShadows.None;
                go.transform.position = pos;
                go.transform.rotation = Quaternion.LookRotation(aim - pos);
                l.renderingLayerMask = -1;
                return l;
            }
            var c0 = new Vector3(0, 1.0f, 0);
            L("Key", LightType.Directional, new Vector3(-2.2f, 3.0f, -3.2f), c0, 1.25f, new Color(1f, 0.98f, 0.95f));
            L("Fill", LightType.Spot, new Vector3(2.6f, 1.6f, -2.6f), c0, 9f, new Color(0.92f, 0.95f, 1f), 12f, 70f);
            L("RimL", LightType.Spot, new Vector3(-2.0f, 2.2f, 2.2f), c0 + Vector3.up * 0.3f, 12f, new Color(0.85f, 0.9f, 1f), 10f, 50f);
            L("RimR", LightType.Spot, new Vector3(2.0f, 2.2f, 2.2f), c0 + Vector3.up * 0.3f, 12f, new Color(0.85f, 0.9f, 1f), 10f, 50f);
            RenderSettings.ambientMode = AmbientMode.Trilight;
            RenderSettings.ambientSkyColor = new Color(0.55f, 0.56f, 0.6f);
            RenderSettings.ambientEquatorColor = new Color(0.45f, 0.46f, 0.48f);
            RenderSettings.ambientGroundColor = new Color(0.3f, 0.3f, 0.32f);

            // post: ACES like the game
            var vol = new GameObject("Volume").AddComponent<Volume>();
            vol.isGlobal = true;
            var profile = ScriptableObject.CreateInstance<VolumeProfile>();
            var tone = profile.Add<Tonemapping>(true);
            tone.mode.Override(TonemappingMode.ACES);
            var ca = profile.Add<ColorAdjustments>(true);
            ca.postExposure.Override(0.35f);
            var bloom = profile.Add<Bloom>(true);
            bloom.intensity.Override(0.6f); bloom.threshold.Override(1.1f);
            vol.sharedProfile = profile;

            // hero
            var prefab = Resources.Load<GameObject>("Characters/" + Characters.AssetName(hero));
            if (prefab == null) { Debug.LogError("[concept] no prefab for " + hero); return (null, null); }
            var inst = UnityEngine.Object.Instantiate(prefab);
            inst.transform.position = Vector3.zero;
            inst.transform.rotation = Quaternion.Euler(0, 180, 0);       // face the camera (-Z)
            var cm = inst.GetComponent<CharacterModel>();
            if (cm != null)
            {
                if (!Application.isPlaying) typeof(CharacterModel).GetMethod("Awake", BindingFlags.NonPublic | BindingFlags.Instance)?.Invoke(cm, null);
                cm.ApplyAppearance(Appearance.Default(hero));
            }
            var anim = inst.GetComponentInChildren<Animator>();
            if (anim != null)
            {
                anim.cullingMode = AnimatorCullingMode.AlwaysAnimate;
                if (stance)
                {
                    var st = inst.GetComponent<HeroStance>() ?? inst.AddComponent<HeroStance>();
                    st.Weight = 1f; st.UpperBodyOnly = false;
                }
                else
                {
                    anim.Rebind();
                    anim.Play("Locomotion", 0, 0.35f);
                    for (var i = 0; i < 30; i++) anim.Update(1f / 30f);
                }
            }
            return (inst, anim);
        }

        static void Shoot(string hero, GameObject inst, Animator anim)
        {
            var outDir = Path.GetFullPath(Path.Combine(Application.dataPath, "..", "..", "..", "Captures", "hero_concept"));
            Directory.CreateDirectory(outDir);
            // yaw the root so pelvis + shoulders face the camera (concept front view)
            if (anim != null && anim.isHuman)
            {
                Transform B(HumanBodyBones b) => anim.GetBoneTransform(b);
                var across = (B(HumanBodyBones.RightUpperLeg).position - B(HumanBodyBones.LeftUpperLeg).position).normalized
                           + (B(HumanBodyBones.RightUpperArm).position - B(HumanBodyBones.LeftUpperArm).position).normalized;
                across.y = 0;
                if (across.sqrMagnitude > 1e-6)
                {
                    // facing -Z (towards the camera) puts the character's right on -X
                    var q = Quaternion.FromToRotation(across.normalized, Vector3.left);
                    var yaw = q.eulerAngles.y > 180 ? q.eulerAngles.y - 360 : q.eulerAngles.y;
                    if (Mathf.Abs(yaw) > 1.5f) inst.transform.rotation = Quaternion.Euler(0, yaw, 0) * inst.transform.rotation;
                    Debug.Log("[concept] turned " + yaw.ToString("F1") + " deg to face the camera");
                }
            }

            // camera
            var camGo = new GameObject("Cam");
            var cam = camGo.AddComponent<Camera>();
            cam.fieldOfView = 26f;
            cam.nearClipPlane = 0.05f;
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = new Color(0.66f, 0.67f, 0.7f);
            var data = camGo.AddComponent<UniversalAdditionalCameraData>();
            data.renderPostProcessing = true;
            data.antialiasing = AntialiasingMode.SubpixelMorphologicalAntiAliasing;
            foreach (var (tag, yaw) in new[] { ("front", 0f), ("q34", 30f), ("back", 180f) })
            {
                var r = yaw * Mathf.Deg2Rad;
                var d = 4.4f;
                cam.transform.position = new Vector3(Mathf.Sin(r) * d, 1.0f, -Mathf.Cos(r) * d);
                cam.transform.LookAt(new Vector3(0, 0.96f, 0));
                var rt = new RenderTexture(1296, 1728, 24, RenderTextureFormat.ARGB32) { antiAliasing = 1 };   // MSAA x8 is not supported on Apple GPUs (black frames); SMAA below
                cam.targetTexture = rt;
                cam.Render();
                RenderTexture.active = rt;
                var tex = new Texture2D(rt.width, rt.height, TextureFormat.RGB24, false);
                tex.ReadPixels(new Rect(0, 0, rt.width, rt.height), 0, 0);
                tex.Apply();
                File.WriteAllBytes(Path.Combine(outDir, $"{hero}_{tag}.png"), tex.EncodeToPNG());
                RenderTexture.active = null;
                cam.targetTexture = null;
                UnityEngine.Object.DestroyImmediate(rt);
                UnityEngine.Object.DestroyImmediate(tex);
            }
            Debug.Log($"[concept] captured {hero} → {outDir}");
        }
    }
}
