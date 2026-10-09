using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace EOA.EditorTools
{
    /// <summary>
    /// Giva concept-match capture (character art check, Giva remake): the built Lyra prefab in an empty scene under a soft
    /// grey studio rig, the designer's upright HeroStance on the idle (arms relaxed at the sides), default appearance,
    /// framed like the master concept (front, head to below the knees) plus a face close-up.
    ///   Unity -batchmode -projectPath . -executeMethod EOA.EditorTools.GivaConceptShot.Run [-givaHair waves] [-givaOut dir]
    /// Writes giva_concept_front.png / giva_concept_face.png / giva_concept_q34.png to Captures/giva_concept (or -givaOut).
    /// Editor-only; touches no game code or assets.
    /// </summary>
    public static class GivaConceptShot
    {
        const string Key = "eoa_giva_concept_shot";
        static int frame, faced;
        static GameObject hero;
        static Camera cam;
        static string outDir, hair;
        static bool fits;

        public static void Run()
        {
            var args = System.Environment.GetCommandLineArgs();
            string Arg(string k, string d) { var i = System.Array.IndexOf(args, k); return i >= 0 && i + 1 < args.Length ? args[i + 1] : d; }
            SessionState.SetString(Key + "_out", Arg("-givaOut", Path.GetFullPath(Path.Combine(Application.dataPath, "../../../Captures/giva_concept"))));
            SessionState.SetString(Key + "_hair", Arg("-givaHair", ""));
            SessionState.SetBool(Key + "_fits", System.Array.IndexOf(args, "-givaFits") >= 0);
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            SessionState.SetBool(Key, true);
            EditorApplication.EnterPlaymode();
        }

        [InitializeOnLoadMethod]
        static void Hook()
        {
            EditorApplication.playModeStateChanged += s =>
            {
                if (s != PlayModeStateChange.EnteredPlayMode || !SessionState.GetBool(Key, false)) return;
                SessionState.SetBool(Key, false);
                outDir = SessionState.GetString(Key + "_out", "Captures/giva_concept");
                hair = SessionState.GetString(Key + "_hair", "");
                fits = SessionState.GetBool(Key + "_fits", false);
                Setup();
                frame = 0; faced = 0;
                EditorApplication.update += Tick;
            };
        }

        static Light MakeLight(string n, LightType t, Color c, float intensity, Vector3 pos, Vector3 aim, bool shadows)
        {
            var go = new GameObject(n);
            go.transform.position = pos;
            go.transform.LookAt(aim);
            var l = go.AddComponent<Light>();
            l.type = t; l.color = c; l.intensity = intensity;
            l.shadows = shadows ? LightShadows.Soft : LightShadows.None;
            if (t != LightType.Directional) l.range = 12;
            if (t == LightType.Spot) l.spotAngle = 70;
            l.renderingLayerMask = -1;
            return l;
        }

        static void Setup()
        {
            var prefab = Resources.Load<GameObject>("Characters/" + Characters.AssetName(Characters.Lyra));
            hero = Object.Instantiate(prefab);
            hero.transform.position = Vector3.zero;
            hero.transform.rotation = Quaternion.identity;          // models face +Z
            hero.AddComponent<HeroStance>();
            var model = hero.GetComponent<CharacterModel>();
            foreach (var an in hero.GetComponentsInChildren<Animator>()) an.cullingMode = AnimatorCullingMode.AlwaysAnimate;
            var a = Appearance.Default(Characters.Lyra);
            if (!string.IsNullOrEmpty(hair)) a.HairStyle = hair;
            model?.ApplyAppearance(a);
            // soft grey studio
            RenderSettings.ambientMode = AmbientMode.Trilight;
            RenderSettings.ambientSkyColor = new Color(0.5f, 0.5f, 0.54f);
            RenderSettings.ambientEquatorColor = new Color(0.44f, 0.43f, 0.46f);
            RenderSettings.ambientGroundColor = new Color(0.32f, 0.31f, 0.33f);
            RenderSettings.fog = false;
            MakeLight("Key", LightType.Directional, new Color(1f, 0.97f, 0.94f), 0.8f, new Vector3(-1.6f, 2.4f, 3f), new Vector3(0, 1.1f, 0), false);
            MakeLight("Fill", LightType.Directional, new Color(0.93f, 0.95f, 1f), 0.42f, new Vector3(2.4f, 1.2f, 2.6f), new Vector3(0, 1.1f, 0), false);
            MakeLight("Back", LightType.Directional, new Color(1f, 0.96f, 1f), 0.6f, new Vector3(0.4f, 2.4f, -2.6f), new Vector3(0, 1.2f, 0), false);
            var floor = GameObject.CreatePrimitive(PrimitiveType.Plane);
            floor.transform.localScale = Vector3.one * 3;
            var fm = new Material(Shader.Find("Universal Render Pipeline/Lit"));
            fm.SetColor("_BaseColor", new Color(0.55f, 0.55f, 0.58f));
            fm.SetFloat("_Smoothness", 0.25f);
            floor.GetComponent<Renderer>().sharedMaterial = fm;
            var camGo = new GameObject("Cam");
            cam = camGo.AddComponent<Camera>();
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = new Color(0.72f, 0.72f, 0.75f);
            cam.allowHDR = true;
            cam.nearClipPlane = 0.02f;
            var data = camGo.AddComponent<UniversalAdditionalCameraData>();
            data.renderPostProcessing = true;
            data.antialiasing = AntialiasingMode.SubpixelMorphologicalAntiAliasing;
            // the game's own post stack (ACES, bloom threshold 1.0 / intensity 0.75, grading), so glow pixels measure true
            PostFx.Create(new GameObject("PostRoot").transform);
        }

        static Texture2D lastShot;

        static void Shot(string name, Vector3 pos, Vector3 aim, float fov, int w, int h) => Shot(name, pos, aim, fov, w, h, false);

        static void Shot(string name, Vector3 pos, Vector3 aim, float fov, int w, int h, bool keep)
        {
            cam.transform.position = pos;
            cam.transform.LookAt(aim);
            cam.fieldOfView = fov;
            var rt = new RenderTexture(w, h, 24, RenderTextureFormat.ARGB32) { antiAliasing = 4 };
            cam.targetTexture = rt;
            cam.Render();
            var prev = RenderTexture.active;
            RenderTexture.active = rt;
            var tex = new Texture2D(w, h, TextureFormat.RGB24, false);
            tex.ReadPixels(new Rect(0, 0, w, h), 0, 0);
            tex.Apply();
            RenderTexture.active = prev;
            cam.targetTexture = null;
            Directory.CreateDirectory(outDir);
            File.WriteAllBytes(Path.Combine(outDir, name + ".png"), tex.EncodeToPNG());
            if (lastShot != null) Object.DestroyImmediate(lastShot);
            lastShot = null;
            if (keep) lastShot = tex; else Object.DestroyImmediate(tex);
            rt.Release();
            Debug.Log("[giva-concept] wrote " + Path.Combine(outDir, name + ".png"));
        }

        /// <summary>Turn the root so the pelvis faces the camera (+Z), like the concept's front view.</summary>
        static void FaceCamera()
        {
            var anim = hero.GetComponentInChildren<Animator>();
            if (anim == null || !anim.isHuman) return;
            Transform B(HumanBodyBones b) => anim.GetBoneTransform(b);
            // average facing of the pelvis and the shoulders (left -> right across the body)
            var across = (B(HumanBodyBones.RightUpperLeg).position - B(HumanBodyBones.LeftUpperLeg).position).normalized
                       + (B(HumanBodyBones.RightUpperArm).position - B(HumanBodyBones.LeftUpperArm).position).normalized;
            across.y = 0;
            if (across.sqrMagnitude < 1e-6) return;
            // facing +Z means the character's right points along +X: rotate across onto +X about the vertical
            var q = Quaternion.FromToRotation(across.normalized, Vector3.right);
            var yaw = q.eulerAngles.y > 180 ? q.eulerAngles.y - 360 : q.eulerAngles.y;
            if (Mathf.Abs(yaw) > 1.5f) hero.transform.rotation = Quaternion.Euler(0, yaw, 0) * hero.transform.rotation;
            Debug.Log("[giva-concept] turned " + yaw.ToString("F1") + " deg to face the camera");
        }

        /// <summary>Catalog fit check: every Giva armour set (front, side, back) and every eyewear item (face close-up).
        /// One look per step; each step waits a few player frames so the attachment is built and skinned first.</summary>
        static readonly System.Collections.Generic.List<System.Action> steps = new();
        static float nextStep;

        static void QueueFits(Vector3 aim, Vector3 fwd, Vector3 hp)
        {
            var model = hero.GetComponent<CharacterModel>();
            var cat = CustomCatalog.Get();
            var baseLook = Appearance.Default(Characters.Lyra);
            if (!string.IsNullOrEmpty(hair)) baseLook.HairStyle = hair;
            var right = Vector3.Cross(Vector3.up, fwd);
            foreach (var it in cat.For("armour", Characters.Lyra))
            {
                var id = it.Id;
                steps.Add(() => { var a = baseLook.Clone(); a.ArmorSet = id; model.ApplyAppearance(a); });
                steps.Add(() =>
                {
                    Shot("fit_armour_" + id + "_front", aim + fwd * 3.0f + Vector3.up * 0.08f, aim, 28f, 648, 864);
                    Shot("fit_armour_" + id + "_back", aim - fwd * 3.0f + Vector3.up * 0.1f, aim, 28f, 648, 864);
                    Shot("fit_armour_" + id + "_side", aim + right * 3.0f + Vector3.up * 0.08f, aim, 28f, 648, 864);
                });
            }
            foreach (var it in cat.For("eyewear", Characters.Lyra))
            {
                var id = it.Id;
                steps.Add(() => { var a = baseLook.Clone(); a.Eyewear = id; model.ApplyAppearance(a); });
                steps.Add(() =>
                {
                    var hb = hero.GetComponentInChildren<Animator>().GetBoneTransform(HumanBodyBones.Head);
                    var h = hb.position + Vector3.up * 0.055f;
                    Shot("fit_eyewear_" + id, h + fwd * 0.55f + right * 0.22f + Vector3.up * 0.02f, h, 26f, 648, 648);
                });
            }
            steps.Add(() => model.ApplyAppearance(baseLook));
        }

        static void RunSteps()
        {
            if (Time.realtimeSinceStartup < nextStep) return;
            if (steps.Count == 0)
            {
                EditorApplication.update -= RunSteps;
                Debug.Log("[giva-concept] done");
                EditorApplication.ExitPlaymode();
                EditorApplication.delayCall += () => EditorApplication.Exit(0);
                return;
            }
            var st = steps[0];
            steps.RemoveAt(0);
            try { st(); } catch (System.Exception e) { Debug.LogError("[giva-concept] " + e); }
            nextStep = Time.realtimeSinceStartup + 0.6f;
        }

        // ------------------------------------------------------------------ glow probes
        static readonly string[] GlowMats = { "Glow", "Glow2", "Screen", "Holo" };

        /// <summary>World-space vertices of every glow sub-mesh of a character (posed), per material.</summary>
        static System.Collections.Generic.Dictionary<string, System.Collections.Generic.List<(Vector3 p, Vector3 n)>> GlowVerts(GameObject h)
        {
            var res = new System.Collections.Generic.Dictionary<string, System.Collections.Generic.List<(Vector3, Vector3)>>();
            foreach (var r in h.GetComponentsInChildren<SkinnedMeshRenderer>())
            {
                if (!r.gameObject.activeInHierarchy || r.sharedMesh == null) continue;
                var mats = r.sharedMaterials;
                var baked = new Mesh();
                r.BakeMesh(baked, true);
                var M = Matrix4x4.TRS(r.transform.position, r.transform.rotation, Vector3.one);
                var V = baked.vertices; var N = baked.normals;
                for (var sm = 0; sm < baked.subMeshCount && sm < mats.Length; sm++)
                {
                    if (mats[sm] == null || System.Array.IndexOf(GlowMats, mats[sm].name) < 0) continue;
                    if (!res.TryGetValue(mats[sm].name, out var list)) res[mats[sm].name] = list = new();
                    var seen = new System.Collections.Generic.HashSet<int>();
                    foreach (var i in baked.GetIndices(sm))
                        if (seen.Add(i)) list.Add((M.MultiplyPoint3x4(V[i]), M.MultiplyVector(N[i]).normalized));
                }
                Object.DestroyImmediate(baked);
            }
            return res;
        }

        static Vector3 GlowCentroid(GameObject h, string mat, System.Func<Vector3, bool> filter = null)
        {
            var g = GlowVerts(h);
            if (!g.TryGetValue(mat, out var list)) return Vector3.zero;
            var c = Vector3.zero; var n = 0;
            foreach (var (p, _) in list) if (filter == null || filter(p)) { c += p; n++; }
            return n > 0 ? c / n : Vector3.zero;
        }

        /// <summary>Shot + pixel probe: the rendered colour under every camera-facing glow vertex (median, saturation).</summary>
        static void ProbeShot(GameObject h, string tag, Vector3 pos, Vector3 aim, float fov, int w, int hh)
        {
            Shot(tag, pos, aim, fov, w, hh, true);
            var tex = lastShot;
            cam.transform.position = pos; cam.transform.LookAt(aim); cam.fieldOfView = fov; cam.aspect = w / (float)hh;
            foreach (var kv in GlowVerts(h))
            {
                var cols = new System.Collections.Generic.List<Color>();
                foreach (var (p, n) in kv.Value)
                {
                    if (Vector3.Dot(n, (pos - p).normalized) < 0.35f) continue;
                    var vp = cam.WorldToViewportPoint(p);
                    if (vp.z <= 0 || vp.x < 0 || vp.x > 1 || vp.y < 0 || vp.y > 1) continue;
                    cols.Add(tex.GetPixel((int)(vp.x * w), (int)(vp.y * hh)));
                }
                if (cols.Count < 5) { Debug.Log($"[glow-probe] {tag} {kv.Key} n {cols.Count}"); continue; }
                float Med(System.Func<Color, float> f) { var a = cols.ConvertAll(c => f(c)); a.Sort(); return a[a.Count / 2]; }
                float sat = 0, hot = 0;
                foreach (var c in cols)
                {
                    Color.RGBToHSV(c, out _, out var s_, out var v_);
                    sat += s_;
                    if (s_ > 0.6f && v_ > 0.75f) hot++;
                }
                Debug.Log($"[glow-probe] {tag} {kv.Key} n {cols.Count} median RGB ({Med(c => c.r) * 255:F0},{Med(c => c.g) * 255:F0},{Med(c => c.b) * 255:F0}) mean sat {sat / cols.Count:F2} saturated-bright share {hot / cols.Count:F2}");
            }
        }

        /// <summary>Emission transfer check: emissive quads at known linear levels through the game's post stack.</summary>
        static void SwatchProbe()
        {
            hero.SetActive(false);
            var root = new GameObject("Swatches");
            var cols = new[] { ("magenta", new Color(1f, 0.169f, 0.839f)), ("cyan", new Color(0f, 0.898f, 1f)), ("violet", new Color(0.608f, 0.361f, 1f)) };
            var levels = new[] { 0.5f, 0.8f, 1.2f, 1.6f, 2.2f, 3.0f };
            var quads = new System.Collections.Generic.List<(string, float, Vector3)>();
            for (var ci = 0; ci < cols.Length; ci++)
                for (var li = 0; li < levels.Length; li++)
                {
                    var q = GameObject.CreatePrimitive(PrimitiveType.Quad);
                    q.transform.SetParent(root.transform);
                    var pos = new Vector3(-1.0f + li * 0.4f, 1.6f - ci * 0.45f, 0f);
                    q.transform.position = pos;
                    q.transform.rotation = Quaternion.identity;          // a quad faces -Z: towards the camera
                    q.transform.localScale = Vector3.one * 0.14f;
                    var m = new Material(Shader.Find("Universal Render Pipeline/Lit"));
                    m.SetColor("_BaseColor", Color.black);
                    m.SetFloat("_Smoothness", 0.3f);
                    m.EnableKeyword("_EMISSION");
                    var lin = cols[ci].Item2.linear;
                    var mx = Mathf.Max(lin.r, Mathf.Max(lin.g, lin.b));
                    var e = new Color(Mathf.Pow(lin.r / mx, 1.6f), Mathf.Pow(lin.g / mx, 1.6f), Mathf.Pow(lin.b / mx, 1.6f), 1f) * levels[li];
                    e.a = 1;
                    m.SetColor("_EmissionColor", e.gamma);
                    q.GetComponent<Renderer>().sharedMaterial = m;
                    quads.Add((cols[ci].Item1, levels[li], pos));
                }
            var camPos = new Vector3(0, 1.15f, -3.2f);
            Shot("glow_swatches", camPos, new Vector3(0, 1.15f, 0), 30f, 1200, 700, true);
            var tex = lastShot;
            cam.transform.position = camPos; cam.transform.LookAt(new Vector3(0, 1.15f, 0)); cam.fieldOfView = 30f; cam.aspect = 1200 / 700f;
            foreach (var (n, l, p) in quads)
            {
                var vp = cam.WorldToViewportPoint(p);
                var c = tex.GetPixel((int)(vp.x * 1200), (int)(vp.y * 700));
                Debug.Log($"[glow-swatch] {n} level {l:F1} -> ({c.r * 255:F0},{c.g * 255:F0},{c.b * 255:F0})");
            }
            Object.Destroy(root);
            hero.SetActive(true);
        }

        static void QueueGlowProbes(Vector3 fwd)
        {
            steps.Add(SwatchProbe);
            var right = Vector3.Cross(Vector3.up, fwd);
            steps.Add(() =>
            {
                var core = GlowCentroid(hero, "Glow", p => p.y > 1.2f);
                ProbeShot(hero, "glow_giva_core", core + fwd * 0.55f + right * 0.1f, core, 30f, 864, 864);
                var scr = GlowCentroid(hero, "Glow2", p => p.y < 1.25f && p.y > 0.8f);
                ProbeShot(hero, "glow_giva_bracer", scr + fwd * 0.45f - right * 0.25f, scr, 30f, 864, 864);
                var boot = GlowCentroid(hero, "Glow", p => p.y < 0.55f);
                ProbeShot(hero, "glow_giva_boots", boot + fwd * 1.1f + Vector3.up * 0.15f, boot, 30f, 864, 864);
            });
            // Kael on the same stage, default look
            GameObject kael = null;
            steps.Add(() =>
            {
                hero.SetActive(false);
                var pf = Resources.Load<GameObject>("Characters/" + Characters.AssetName(Characters.Kael));
                kael = Object.Instantiate(pf);
                kael.transform.position = Vector3.zero;
                kael.transform.rotation = hero.transform.rotation;
                kael.AddComponent<HeroStance>();
                foreach (var an in kael.GetComponentsInChildren<Animator>()) an.cullingMode = AnimatorCullingMode.AlwaysAnimate;
                kael.GetComponent<CharacterModel>()?.ApplyAppearance(Appearance.Default(Characters.Kael));
            });
            steps.Add(() => { });
            steps.Add(() =>
            {
                var aim = new Vector3(0, 1.15f, 0);
                ProbeShot(kael, "glow_kael_front", aim + fwd * 3.2f + Vector3.up * 0.08f, aim, 28f, 864, 1152);
                var g = GlowVerts(kael);
                foreach (var m in GlowMats)
                {
                    var c = GlowCentroid(kael, m);
                    if (c == Vector3.zero) continue;
                    ProbeShot(kael, "glow_kael_" + m.ToLowerInvariant() + "_closeup", c + fwd * 0.6f + right * 0.15f + Vector3.up * 0.05f, c, 30f, 864, 864);
                }
            });
        }

        static bool Blinking()
        {
            foreach (var r in hero.GetComponentsInChildren<SkinnedMeshRenderer>())
            {
                var m = r.sharedMesh;
                if (m == null) continue;
                for (var i = 0; i < m.blendShapeCount; i++)
                    if (m.GetBlendShapeName(i).EndsWith("x_blink_L") && r.GetBlendShapeWeight(i) > 1f) return true;
            }
            return false;
        }

        static void Tick()
        {
            frame++;
            // drive by player time (editor updates can run far ahead of the player loop while shaders compile)
            var t = Time.timeSinceLevelLoad;
            if (t < 4f || Time.frameCount < 90) return;
            if (t < 6.5f) return;
            if (t < 20f && Blinking()) return;       // a blink can land on any frame: wait for open eyes
            EditorApplication.update -= Tick;
            try
            {
                // cameras follow the character's own facing (the idle stands slightly turned; HeroStance owns the body)
                var anim = hero.GetComponentInChildren<Animator>();
                Transform B(HumanBodyBones b) => anim.GetBoneTransform(b);
                var across = (B(HumanBodyBones.RightUpperLeg).position - B(HumanBodyBones.LeftUpperLeg).position).normalized
                           + (B(HumanBodyBones.RightUpperArm).position - B(HumanBodyBones.LeftUpperArm).position).normalized;
                across.y = 0;
                var fwd = Vector3.Cross(across.normalized, Vector3.up).normalized;
                var pelvis = B(HumanBodyBones.Hips).position; pelvis.y = 0;
                var head = B(HumanBodyBones.Head);
                var hp = head.position + Vector3.up * 0.055f;
                Debug.Log("[giva-concept] facing " + fwd.ToString("F2"));
                var aim = pelvis + Vector3.up * 1.12f;
                Shot("giva_concept_front", aim + fwd * 3.0f + Vector3.up * 0.08f, aim, 28f, 864, 1152);
                Shot("giva_concept_face", hp + fwd * 0.95f - Vector3.up * 0.04f, hp - Vector3.up * 0.05f, 24f, 864, 1152);
                var side = Quaternion.Euler(0, -38f, 0) * fwd;
                Shot("giva_concept_q34", aim + side * 3.0f + Vector3.up * 0.1f, aim, 30f, 864, 1152);
                if (fits)
                {
                    QueueFits(aim, fwd, hp);
                    QueueGlowProbes(fwd);
                    nextStep = Time.realtimeSinceStartup + 0.3f;
                    EditorApplication.update += RunSteps;
                    return;
                }
                Debug.Log("[giva-concept] done");
            }
            catch (System.Exception e) { Debug.LogError("[giva-concept] " + e); }
            EditorApplication.ExitPlaymode();
            EditorApplication.delayCall += () => EditorApplication.Exit(0);
        }
    }
}
