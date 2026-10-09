using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.UIElements;

namespace EOA
{
    /// <summary>
    /// Automated play-through used by the editor smoke test (EOA/Test/Smoke Test, or batch
    /// -executeMethod EOA.EditorTools.SmokeTest.Run) and by player builds started with "-autopilot &lt;dir&gt;".
    /// Boots to the menu, opens character select, starts a new game (intro cinematic), tours every zone, triggers a
    /// fight, and saves real in-game screenshots (game camera + UI) plus report.json with every error/exception,
    /// zone load times and frame times. Never active in normal play.
    /// </summary>
    public sealed partial class AutoPilot : MonoBehaviour
    {
        public static bool Done { get; private set; }
        public static bool Failed { get; private set; }
        public static string OutDir { get; private set; }

        readonly List<string> errors = new();
        readonly List<string> warnings = new();
        readonly Dictionary<string, object> report = new();
        readonly List<Dictionary<string, object>> zoneReports = new();

        /// <summary>"full" (menus, intro, every zone, combat) or "combat" (plaza fight only, with per-second state logs).</summary>
        public static string Mode = "full";

        public static void Begin(string outDir, string mode = "full")
        {
            Mode = mode;
            if (FindAnyObjectByType<AutoPilot>() != null) return;
            OutDir = outDir;
            Directory.CreateDirectory(outDir);
            Done = false;
            Failed = false;
            var go = new GameObject("AutoPilot");
            DontDestroyOnLoad(go);
            go.AddComponent<AutoPilot>();
        }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void FromCommandLine()
        {
            var args = Environment.GetCommandLineArgs();
            var i = Array.IndexOf(args, "-autopilot");
            if (i >= 0 && !Application.isEditor) Begin(i + 1 < args.Length ? args[i + 1] : Path.Combine(Application.persistentDataPath, "autopilot"));
        }

        void OnEnable() => Application.logMessageReceived += OnLog;
        void OnDisable() => Application.logMessageReceived -= OnLog;

        void OnLog(string msg, string stack, LogType type)
        {
            // Unity's own editor search indexer throws during batch startup; not game code.
            if (stack != null && stack.Contains("UnityEditor.Search.")) return;
            if (type == LogType.Error || type == LogType.Exception || type == LogType.Assert)
                errors.Add($"{type}: {msg}\n{(stack?.Length > 1200 ? stack.Substring(0, 1200) : stack)}");
            else if (type == LogType.Warning && warnings.Count < 400) warnings.Add(msg);
        }

        static void Log(string m) => Debug.Log($"[autopilot] {Time.realtimeSinceStartup:0.0}s frame {Time.frameCount}: {m}");

        async void Start()
        {
            Log("start");
            var t0 = Time.realtimeSinceStartup;
            try { await Run(); }
            catch (Exception e) { errors.Add("AutoPilot aborted: " + e); }
            report["seconds"] = Time.realtimeSinceStartup - t0;
            report["errors"] = errors;
            report["warnings"] = warnings.Distinct().Take(200).ToList();
            report["zones"] = zoneReports;
            Failed = errors.Count > 0;
            File.WriteAllText(Path.Combine(OutDir, "report.json"), Newtonsoft.Json.JsonConvert.SerializeObject(report, Newtonsoft.Json.Formatting.Indented));
            Debug.Log($"[autopilot] done: {errors.Count} errors, {warnings.Count} warnings → {OutDir}");
            Done = true;
            if (!Application.isEditor) Application.Quit(Failed ? 1 : 0);
        }

        static async Task Seconds(float s)
        {
            var end = Time.realtimeSinceStartup + s;
            while (Time.realtimeSinceStartup < end) await Awaitable.NextFrameAsync();
        }

        static async Task<bool> Until(Func<bool> cond, float timeout)
        {
            var end = Time.realtimeSinceStartup + timeout;
            while (!cond())
            {
                if (Time.realtimeSinceStartup > end) return false;
                await Awaitable.NextFrameAsync();
            }
            return true;
        }

        /// <summary>Both leads in the designer: full body, face and back views.</summary>
        async Task Heroes()
        {
            await Seconds(3);
            G.Manager.ShowCharSelect();
            await Seconds(2.5f);
            await Capture("h00_character_select");
            foreach (var hero in new[] { Characters.Kael, Characters.Lyra })
            {
                var name = hero == Characters.Kael ? "kael" : "giva";
                G.Manager.UI.OpenDesigner(hero);
                await Seconds(2.5f);
                DumpAttachments();
                await Capture($"h_{name}_body");
                G.Manager.MenuStage.FocusFace(true);
                await Seconds(2f);
                await Capture($"h_{name}_face");
                // Eyewear check: two catalog glasses on the face close-up, then back to the saved look.
                var look = G.Manager.AppearanceFor(hero);
                foreach (var eye in new[] { "aviator", "rect_smart" })
                {
                    var test = look.Clone();
                    test.Eyewear = eye;
                    G.Manager.Stage.SetAppearance(hero, test);
                    await Seconds(1f);
                    await Capture($"h_{name}_face_{eye}");
                }
                G.Manager.Stage.SetAppearance(hero, look);
                G.Manager.MenuStage.FocusFace(false);
                G.Manager.MenuStage.Rotate(160);
                await Seconds(2f);
                await Capture($"h_{name}_back");
                G.Manager.MenuStage.Rotate(-160);
                G.Manager.UI.Pop("designer");
                await Seconds(1f);
            }
            report["heroes"] = "PASS";
        }

        /// <summary>Log every catalog attachment on the stage heroes (renderer, mesh, bones, bounds, material).</summary>
        void DumpAttachments()
        {
            foreach (var cm in FindObjectsByType<CharacterModel>(FindObjectsSortMode.None))
            {
                foreach (var r in cm.GetComponentsInChildren<Renderer>(true))
                    foreach (var em in r.sharedMaterials)
                        if (em != null && em.name.StartsWith("Eye"))
                            Log($"[eyes] {cm.CharacterId}/{r.name}: mat={em.name} shader={em.shader.name} tex={(em.GetTexture("_BaseMap") != null ? em.GetTexture("_BaseMap").name : "none")} " +
                                $"col={em.GetColor("_BaseColor")} smooth={em.GetFloat("_Smoothness"):0.00} eyeTexReadable={(cm.EyeTexture != null ? cm.EyeTexture.isReadable.ToString() : "null")} kw={string.Join(",", em.shaderKeywords)}");
                foreach (Transform c in cm.GetComponentsInChildren<Transform>(true))
                {
                    if (!c.name.StartsWith("Custom_")) continue;
                    foreach (var r in c.GetComponentsInChildren<Renderer>(true))
                    {
                        var smr = r as SkinnedMeshRenderer;
                        var mf = r.GetComponent<MeshFilter>();
                        var mesh = smr != null ? smr.sharedMesh : mf != null ? mf.sharedMesh : null;
                        var nullBones = smr != null ? smr.bones.Count(b => b == null) : 0;
                        var m = r.sharedMaterial;
                        Log($"[attach] {cm.CharacterId}/{c.name}/{r.name}: {r.GetType().Name} active={r.gameObject.activeInHierarchy} enabled={r.enabled} " +
                            $"mesh={(mesh != null ? mesh.name + ":" + mesh.vertexCount : "null")} bones={(smr != null ? smr.bones.Length : 0)} nullBones={nullBones} " +
                            $"root={(smr != null && smr.rootBone != null ? smr.rootBone.name : "-")} bounds={r.bounds.center:F2}/{r.bounds.size:F2} " +
                            $"mat={(m != null ? m.shader.name + " tex=" + (m.HasProperty("_BaseMap") && m.GetTexture("_BaseMap") != null ? m.GetTexture("_BaseMap").name : "none") + " col=" + (m.HasProperty("_BaseColor") ? m.GetColor("_BaseColor").ToString() : "-") + " cut=" + (m.HasProperty("_Cutoff") ? m.GetFloat("_Cutoff").ToString("0.00") : "-") : "null")}");
                    }
                }
            }
        }

        async Task Run()
        {
            Log("waiting for menu");
            if (!await Until(() => G.Manager != null && G.Manager.Mode == GameMode.Menu, 90)) { errors.Add($"menu never appeared (manager {(G.Manager != null ? G.Manager.Mode.ToString() : "null")})"); return; }
            Log("menu up");
            if (FeelRequested && (Mode == "combat" || Mode == "feel")) { await CombatFeel(); return; }
            if (Mode == "combat") { await CombatOnly(); return; }
            if (Mode == "story") { await Story(); return; }
            if (Mode == "heroes") { await Heroes(); return; }
            if (Mode == "posture") { await Posture(); return; }
            if (Mode == "vehicles") { await Vehicles(); return; }
            if (Mode == "driving") { await DriveTest(); return; }
            if (Mode == "weapons") { await WeaponShots(); return; }
            await Seconds(3);
            await Capture("00_main_menu");
            G.Manager.ShowCharSelect();
            await Seconds(2.5f);
            await Capture("01_character_select");

            // New game: intro cinematic, then skip it.
            var newGame = G.Manager.NewGame(Characters.Kael, 2);
            if (await Until(() => G.Manager.Cinematics.Active != null, 120))
            {
                await Seconds(4);
                await Capture("02_intro_cinematic_a");
                await Seconds(5);
                await Capture("03_intro_cinematic_b");
                G.Manager.Cinematics.Stop();
            }
            else errors.Add("intro cinematic did not start");
            await Until(() => newGame.IsCompleted, 60);
            await Until(() => G.Manager.Mode == GameMode.Play && G.Manager.Cinematics.Active == null, 30);
            await Seconds(2);
            await Capture("04_plaza_gameplay");

            foreach (var zone in new[] { "plaza", "metro", "facility", "rooftops", "vault", "core" })
                await TourZone(zone);

            // Combat: spawn the first drone encounter in the plaza and watch the fight.
            await G.Manager.LoadZone("plaza", "start");
            await Seconds(1);
            G.Manager.World.SpawnEncounter("e_plaza_drones");
            await Seconds(4);
            await Capture("20_combat_drones");
            report["enemiesAlive"] = Enemy.All.Count(e => e != null && e.Alive);
        }

        async Task CombatOnly()
        {
            var ng = G.Manager.NewGame(Characters.Kael, 2);
            await Until(() => G.Manager.Cinematics.Active != null || ng.IsCompleted, 60);
            G.Manager.Cinematics.Stop();
            await Until(() => ng.IsCompleted, 60);
            await Seconds(1);
            Log("spawning e_plaza_drones");
            G.Manager.World.SpawnEncounter("e_plaza_drones");
            for (var i = 0; i < 20; i++)
            {
                await Seconds(0.5f);
                var p = G.Manager.Player;
                Log($"t+{i * 0.5f:0.0}s enemies {Enemy.All.Count(e => e != null && e.Alive)} hp {(p != null ? p.Health : -1):0} pos {(p != null ? p.Position : Vector3.zero)}");
                if (i == 6) await Capture("20_combat_drones");
            }
        }

        async Task TourZone(string zone)
        {
            Log("zone " + zone);
            var z = new Dictionary<string, object> { ["zone"] = zone };
            var errorsBefore = errors.Count;
            var t = Time.realtimeSinceStartup;
            var load = G.Manager.LoadZone(zone, "start");
            await Until(() => load.IsCompleted, 120);
            z["loadSeconds"] = Time.realtimeSinceStartup - t;
            if (G.Manager.Cinematics.Active != null) G.Manager.Cinematics.Stop();
            await Seconds(2.5f);
            // Frame time over 2 s of play.
            var frames = 0; var ft = Time.realtimeSinceStartup;
            while (Time.realtimeSinceStartup - ft < 2) { frames++; await Awaitable.NextFrameAsync(); }
            z["fps"] = frames / 2f;
            await Capture($"10_{zone}_start");
            // Overview from above the built geometry.
            if (G.Manager.World.Script is ProceduralZone pz && pz.Kit != null)
            {
                var b = pz.Kit.Bounds;
                z["bounds"] = $"{b.center} {b.size}";
                z["pieces"] = pz.Kit.Pieces;
                z["meshes"] = pz.Kit.Meshes;
                z["triangles"] = pz.Kit.Triangles;
                z["colliders"] = pz.Kit.Colliders;
                z["lights"] = pz.Kit.Lights.Count;
                var look = b.center;
                var pos = b.center + new Vector3(-b.extents.x * 0.55f, Mathf.Max(18, b.extents.y + 12), -b.extents.z * 0.85f);
                G.Manager.Cam.Cinematic = (pos, look, 50);
                await Seconds(0.5f);
                await Capture($"11_{zone}_overview");
                // Eye-level view across the zone from the player's position.
                var p = G.Manager.Player != null ? G.Manager.Player.Position : b.center;
                G.Manager.Cam.Cinematic = (p + new Vector3(0, 1.7f, 0) - (look - p).normalized * 2f, look + Vector3.up * 1.5f, 55);
                await Seconds(0.5f);
                await Capture($"12_{zone}_vista");
                G.Manager.Cam.Cinematic = null;
            }
            z["errors"] = errors.Count - errorsBefore;
            zoneReports.Add(z);
        }

        // ------------------------------------------------------------------ capture (camera + UI Toolkit overlay)

        async Task Capture(string name, int w = 1600, int h = 900)
        {
            Log("capture " + name);
            // (WaitForEndOfFrame never fires in batch-mode editors without a Game view; cameras are rendered manually.)
            await Awaitable.NextFrameAsync();
            var cam = G.Manager?.Cam?.Cam;
            if (cam == null) { warnings.Add("no camera for capture " + name); return; }
            var camRt = RenderTexture.GetTemporary(w, h, 24, RenderTextureFormat.ARGB32);
            var uiRt = RenderTexture.GetTemporary(w, h, 24, RenderTextureFormat.ARGB32);
            var doc = FindAnyObjectByType<UIDocument>();
            var ps = doc != null ? doc.panelSettings : null;
            var prevTarget = cam.targetTexture;
            RenderTexture prevUi = null;
            bool prevClear = false;
            Color prevClearValue = default;
            try
            {
                await CaptureUtil.RenderInto(cam, camRt);
                var shot = Read(camRt, w, h);
                if (ps != null)
                {
                    prevUi = ps.targetTexture;
                    prevClear = ps.clearColor;
                    prevClearValue = ps.colorClearValue;
                    ps.targetTexture = uiRt;
                    ps.clearColor = true;
                    ps.colorClearValue = new Color(0, 0, 0, 0);
                    await Awaitable.NextFrameAsync();
                    await Awaitable.NextFrameAsync();
                    var ui = Read(uiRt, w, h);
                    ps.targetTexture = prevUi;
                    ps.clearColor = prevClear;
                    ps.colorClearValue = prevClearValue;
                    var a = shot.GetPixels32();
                    var u = ui.GetPixels32();
                    for (var i = 0; i < a.Length; i++)
                    {
                        var al = u[i].a;
                        if (al == 0) continue;
                        // UI Toolkit writes premultiplied colour into a cleared target.
                        a[i].r = (byte)Mathf.Min(255, u[i].r + a[i].r * (255 - al) / 255);
                        a[i].g = (byte)Mathf.Min(255, u[i].g + a[i].g * (255 - al) / 255);
                        a[i].b = (byte)Mathf.Min(255, u[i].b + a[i].b * (255 - al) / 255);
                    }
                    shot.SetPixels32(a);
                    Destroy(ui);
                }
                File.WriteAllBytes(Path.Combine(OutDir, name + ".png"), shot.EncodeToPNG());
                Destroy(shot);
            }
            catch (Exception e) { errors.Add($"capture {name} failed: {e.Message}"); }
            finally
            {
                if (ps != null && ps.targetTexture == uiRt) ps.targetTexture = prevUi;
                cam.targetTexture = prevTarget;
                RenderTexture.ReleaseTemporary(camRt);
                RenderTexture.ReleaseTemporary(uiRt);
            }
        }

        static Texture2D Read(RenderTexture rt, int w, int h)
        {
            var prev = RenderTexture.active;
            RenderTexture.active = rt;
            var tex = new Texture2D(w, h, TextureFormat.RGBA32, false);
            tex.ReadPixels(new Rect(0, 0, w, h), 0, 0);
            tex.Apply();
            RenderTexture.active = prev;
            return tex;
        }
    }
}
