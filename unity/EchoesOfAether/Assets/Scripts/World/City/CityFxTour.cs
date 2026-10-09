using System;
using System.Collections.Generic;
using System.IO;
using System.Threading.Tasks;
using UnityEngine;
using static EOA.ProtoSpace;
#if UNITY_EDITOR
using UnityEditor;
using UnityEditor.SceneManagement;
#endif

namespace EOA
{
    /// <summary>
    /// Lighting review tour of the open city (dev only; never active in normal play): boots a new game, skips the
    /// intro, then frames fixed street-level shots (hero in frame) and elevated vistas in every district and writes
    /// PNGs plus report.json (errors, per-shot frame rate) to the output directory. Batch:
    ///   Unity -batchmode -projectPath unity/EchoesOfAether -executeMethod EOA.CityFxTourRunner.Run [-cityfxOut dir]
    /// </summary>
    public sealed class CityFxTour : MonoBehaviour
    {
        public static bool Done { get; private set; }
        public static bool Failed { get; private set; }
        static string outDir;
        readonly List<string> errors = new();
        readonly List<Dictionary<string, object>> shots = new();

        /// <summary>Prototype-space shots: street shots put the hero at P facing Dir; vistas place the camera at P looking at Look.</summary>
        struct Shot
        {
            public string Name;
            public Vector3 P, Look;
            public Vector2 Dir;
            public bool Street;
            public float Fov;
        }

        static readonly Shot[] Tour =
        {
            new() { Name = "01_plaza_monument", P = new(0, 0.15f, 18), Dir = new(0, -1), Street = true, Fov = 55 },
            new() { Name = "02_market_avenue", P = new(-118, 0.15f, 54), Dir = new(-1, 0), Street = true, Fov = 55 },
            new() { Name = "03_kowloon_street", P = new(-180, 0.05f, -140), Dir = new(0, -1), Street = true, Fov = 55 },
            new() { Name = "04_arcology_avenue", P = new(230, 0.05f, 54), Dir = new(1, 0), Street = true, Fov = 55 },
            new() { Name = "05_canal_bridge", P = new(-96, 0.15f, 222), Dir = new(0, -1), Street = true, Fov = 55 },
            new() { Name = "06_foundry_street", P = new(180, 0.05f, -150), Dir = new(0, -1), Street = true, Fov = 55 },
            new() { Name = "07_skywalk_market", P = new(-134, 9.5f, 62), Look = new(-250, 14, 10), Fov = 58 },
            new() { Name = "08_skywalk_canal", P = new(140, 9.5f, 232), Look = new(-40, 6, 194), Fov = 58 },
            new() { Name = "09_aerial_north", P = new(10, 95, 300), Look = new(0, 20, -120), Fov = 55 },
            new() { Name = "10_aerial_avenue_east", P = new(-300, 60, 70), Look = new(200, 30, 50), Fov = 55 },
            new() { Name = "11_rooftop_skyline", P = new(120, 48, -40), Look = new(420, 70, -260), Fov = 60 },
            new() { Name = "12_noodle_bar_steam", P = new(-112, 0.2f, 70), Dir = new(-0.35f, 1), Street = true, Fov = 55 },
        };

        public static void Begin(string dir)
        {
            if (FindAnyObjectByType<CityFxTour>() != null) return;
            outDir = dir;
            Directory.CreateDirectory(dir);
            Done = false;
            Failed = false;
            var go = new GameObject("CityFxTour");
            DontDestroyOnLoad(go);
            go.AddComponent<CityFxTour>();
        }

        void OnEnable() => Application.logMessageReceived += OnLog;
        void OnDisable() => Application.logMessageReceived -= OnLog;

        void OnLog(string msg, string stack, LogType type)
        {
            if (stack != null && stack.Contains("UnityEditor.Search.")) return;
            if (type == LogType.Error || type == LogType.Exception || type == LogType.Assert)
                errors.Add($"{type}: {msg}\n{(stack?.Length > 800 ? stack.Substring(0, 800) : stack)}");
        }

        static void Log(string m) => Debug.Log($"[cityfx-tour] {Time.realtimeSinceStartup:0.0}s: {m}");

        async void Start()
        {
            var t0 = Time.realtimeSinceStartup;
            try { await Run(); }
            catch (Exception e) { errors.Add("tour aborted: " + e); }
            var report = new Dictionary<string, object> { ["seconds"] = Time.realtimeSinceStartup - t0, ["errors"] = errors, ["shots"] = shots };
            File.WriteAllText(Path.Combine(outDir, "report.json"), Newtonsoft.Json.JsonConvert.SerializeObject(report, Newtonsoft.Json.Formatting.Indented));
            Failed = errors.Count > 0;
            Log($"done: {errors.Count} errors -> {outDir}");
            Done = true;
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

        async Task Run()
        {
            if (!await Until(() => G.Manager != null && G.Manager.Mode == GameMode.Menu, 120)) { errors.Add("menu never appeared"); return; }
            await Seconds(1);
            var m = G.Manager;
            var ng = m.NewGame(Characters.Kael, 2);
            await Until(() => m.Cinematics.Active != null || ng.IsCompleted, 120);
            m.Cinematics.Stop();
            await Until(() => ng.IsCompleted, 120);
            await Until(() => m.Mode == GameMode.Play && !m.World.Loading, 60);
            if (m.Cinematics.Active != null) m.Cinematics.Stop();
            await Seconds(2);
            foreach (var s in Tour)
            {
                if (m.Cinematics.Active != null) m.Cinematics.Stop();
                var p = m.Player;
                if (s.Street)
                {
                    var dir = new Vector3(-s.Dir.x, 0, s.Dir.y).normalized;
                    var pos = V(s.P);
                    p?.Teleport(pos, Mathf.Atan2(dir.x, dir.z) * Mathf.Rad2Deg);
                    m.Cam.Cinematic = (pos - dir * 4.4f + Vector3.up * 2.1f + Vector3.Cross(Vector3.up, dir) * 0.9f, pos + dir * 14f + Vector3.up * 2.2f, s.Fov);
                }
                else
                {
                    var pos = V(s.P);
                    p?.Teleport(new Vector3(pos.x, 0.2f, pos.z), 0);
                    m.Cam.Cinematic = (pos, V(s.Look), s.Fov);
                }
                await Seconds(1.6f);
                var frames = 0; var ft = Time.realtimeSinceStartup;
                while (Time.realtimeSinceStartup - ft < 1) { frames++; await Awaitable.NextFrameAsync(); }
                await Capture(s.Name);
                shots.Add(new Dictionary<string, object> { ["shot"] = s.Name, ["fps"] = frames });
                Log($"{s.Name}: {frames} fps");
            }
            m.Cam.Cinematic = null;
            await DepthShots(m);
            // Dawn variant of the plaza (post-ending epilogue): morning mist instead of the night haze.
            G.State.SetFlag("game_complete");
            var load = m.LoadZone("plaza", "start");
            await Until(() => load.IsCompleted, 180);
            if (m.Cinematics.Active != null) m.Cinematics.Stop();
            await Seconds(2);
            m.Cam.Cinematic = (V(0, 22, 90), V(0, 4, -40), 55);
            await Seconds(1.6f);
            await Capture("13_dawn_plaza");
            m.Cam.Cinematic = (V(-10, 70, 200), V(0, 20, -200), 55);
            await Seconds(1.6f);
            await Capture("14_dawn_aerial");
            m.Cam.Cinematic = null;
            // Interior zone at the gameplay camera.
            var fac = m.LoadZone("facility", "start");
            await Until(() => fac.IsCompleted, 180);
            if (m.Cinematics.Active != null) m.Cinematics.Stop();
            await Seconds(2.5f);
            await Capture("24_facility_gameplay");
        }

        /// <summary>
        /// Depth / form review shots: the real gameplay camera in the plaza and on a street, hero close-ups from the front
        /// three-quarter and the side (character key / fill / rim), and a low rain close-up against shop light.
        /// </summary>
        async Task DepthShots(GameManager m)
        {
            var p = m.Player;
            if (p == null) return;
            async Task Gameplay(string name, Vector3 proto, Vector2 dir2)
            {
                var dir = new Vector3(-dir2.x, 0, dir2.y).normalized;
                var yaw = Mathf.Atan2(dir.x, dir.z);
                m.Cam.Cinematic = null;
                p.Teleport(V(proto), yaw * Mathf.Rad2Deg);
                m.Cam.SnapBehind(yaw);
                await Seconds(1.8f);
                await Capture(name);
            }
            await Gameplay("15_plaza_gameplay", new Vector3(6, 0.15f, 22), new Vector2(-0.3f, -1));
            await Gameplay("16_street_gameplay", new Vector3(-118, 0.15f, 54), new Vector2(-1, 0.05f));
            // Close-ups (cinematic camera, hero idle in the plaza under the lamps).
            var hp = V(new Vector3(4, 0.15f, 12));
            p.Teleport(hp, 200);
            var fwd = Quaternion.Euler(0, 200, 0) * Vector3.forward;
            var side = Vector3.Cross(Vector3.up, fwd);
            m.Cam.Cinematic = (hp + (fwd * 0.8f + side * 0.6f).normalized * 2.3f + Vector3.up * 1.62f, hp + Vector3.up * 1.4f, 38);
            await Seconds(1.6f);
            await Capture("17_hero_three_quarter");
            m.Cam.Cinematic = (hp + side * 3.0f + Vector3.up * 1.4f, hp + Vector3.up * 1.1f, 42);
            await Seconds(1.2f);
            await Capture("18_hero_side");
            m.Cam.Cinematic = (hp - fwd * 3.2f + Vector3.up * 1.9f, hp + fwd * 6f + Vector3.up * 1.2f, 50);
            await Seconds(1.2f);
            await Capture("19_hero_back_gameplay");
            // Rain close-up: low camera across a lit shop street.
            var rp = V(new Vector3(-118, 0.15f, 60));
            p.Teleport(rp + new Vector3(0, 0, 3), 90);
            m.Cam.Cinematic = (rp + Vector3.up * 1.3f, rp + new Vector3(10, 2.2f, 6), 50);
            await Seconds(1.4f);
            await Capture("20_rain_closeup");
            m.Cam.Cinematic = null;
        }

        async Task Capture(string name, int w = 1600, int h = 900)
        {
            var cam = G.Manager?.Cam?.Cam;
            if (cam == null) { errors.Add("no camera for " + name); return; }
            var rt = RenderTexture.GetTemporary(w, h, 24, RenderTextureFormat.ARGB32);
            var prev = cam.targetTexture;
            try
            {
                await CaptureUtil.RenderInto(cam, rt);
                var active = RenderTexture.active;
                RenderTexture.active = rt;
                var tex = new Texture2D(w, h, TextureFormat.RGB24, false);
                tex.ReadPixels(new Rect(0, 0, w, h), 0, 0);
                tex.Apply();
                RenderTexture.active = active;
                File.WriteAllBytes(Path.Combine(outDir, name + ".png"), tex.EncodeToPNG());
                Destroy(tex);
            }
            catch (Exception e) { errors.Add($"capture {name} failed: {e.Message}"); }
            finally
            {
                cam.targetTexture = prev;
                RenderTexture.ReleaseTemporary(rt);
            }
        }
    }

#if UNITY_EDITOR
    /// <summary>Editor entry point for <see cref="CityFxTour"/> (batch: -executeMethod EOA.CityFxTourRunner.Run [-cityfxOut dir]).</summary>
    public static class CityFxTourRunner
    {
        const string Key = "EOA_CITYFX_TOUR";

        public static void Run()
        {
            var args = Environment.GetCommandLineArgs();
            var i = Array.IndexOf(args, "-cityfxOut");
            var dir = i >= 0 && i + 1 < args.Length ? args[i + 1] : Path.GetFullPath(Path.Combine(Application.dataPath, "..", "..", "..", "Captures", "cityfx"));
            SessionState.SetString(Key + "_dir", dir);
            SessionState.SetString(Key + "_started", DateTime.UtcNow.ToString("o"));
            SessionState.SetBool(Key, true);
            EditorSceneManager.OpenScene("Assets/Scenes/Boot.unity");
            EditorApplication.EnterPlaymode();
        }

        [InitializeOnLoadMethod]
        static void Hook()
        {
            EditorApplication.playModeStateChanged += s =>
            {
                if (s == PlayModeStateChange.EnteredPlayMode && SessionState.GetBool(Key, false)) CityFxTour.Begin(SessionState.GetString(Key + "_dir", ""));
            };
            EditorApplication.update += Poll;
        }

        static void Poll()
        {
            if (!SessionState.GetBool(Key, false)) return;
            var started = DateTime.TryParse(SessionState.GetString(Key + "_started", ""), null, System.Globalization.DateTimeStyles.RoundtripKind, out var t) ? t : DateTime.UtcNow;
            var timedOut = (DateTime.UtcNow - started).TotalMinutes > 15;
            if (!EditorApplication.isPlaying || (!CityFxTour.Done && !timedOut)) return;
            SessionState.SetBool(Key, false);
            var failed = CityFxTour.Failed || timedOut;
            Debug.Log($"[cityfx-tour] finished: {(failed ? "FAILED" : "OK")}{(timedOut ? " (timeout)" : "")}");
            EditorApplication.ExitPlaymode();
            if (Application.isBatchMode) EditorApplication.delayCall += () => EditorApplication.Exit(failed ? 1 : 0);
        }
    }
#endif
}
