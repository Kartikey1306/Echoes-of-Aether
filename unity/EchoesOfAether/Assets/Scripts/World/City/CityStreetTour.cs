using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using UnityEngine;
#if UNITY_EDITOR
using UnityEditor;
using UnityEditor.SceneManagement;
#endif

namespace EOA
{
    /// <summary>
    /// Street-level review tour of the street kit (dev only, never active in normal play): boots a new game, then frames
    /// close-ups at eye level of the placed kit pieces it finds in the open city (storefront runs of every shop type,
    /// food carts, alley dumpsters, tram shelters, cables with lanterns, kerbs / gutters / pavers, decals) and writes
    /// PNGs + report.json (errors, fps, street stats). Batch:
    ///   Unity -batchmode -projectPath unity/EchoesOfAether -executeMethod EOA.CityStreetTourRunner.Run [-streetOut dir]
    /// </summary>
    public sealed class CityStreetTour : MonoBehaviour
    {
        public static bool Done { get; private set; }
        public static bool Failed { get; private set; }
        static string outDir;
        readonly List<string> errors = new();
        readonly List<Dictionary<string, object>> shots = new();

        public static void Begin(string dir)
        {
            if (FindAnyObjectByType<CityStreetTour>() != null) return;
            outDir = dir;
            Directory.CreateDirectory(dir);
            Done = false;
            Failed = false;
            var go = new GameObject("CityStreetTour");
            DontDestroyOnLoad(go);
            go.AddComponent<CityStreetTour>();
        }

        void OnEnable() => Application.logMessageReceived += OnLog;
        void OnDisable() => Application.logMessageReceived -= OnLog;

        void OnLog(string msg, string stack, LogType type)
        {
            if (stack != null && stack.Contains("UnityEditor.Search.")) return;
            if (type == LogType.Error || type == LogType.Exception || type == LogType.Assert)
                errors.Add($"{type}: {msg}\n{(stack?.Length > 800 ? stack.Substring(0, 800) : stack)}");
        }

        static void Log(string m) => Debug.Log($"[street-tour] {Time.realtimeSinceStartup:0.0}s: {m}");

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

        static GameObject Find(string prefix, int skip = 0)
        {
            var all = FindObjectsByType<Transform>(FindObjectsInactive.Include, FindObjectsSortMode.None)
                .Where(t => t.name.StartsWith(prefix) && !t.name.Contains("_LOD") && !t.name.StartsWith("Collider")).OrderBy(t => t.position.sqrMagnitude).ToList();
            return all.Count > skip ? all[skip].gameObject : null;
        }

        async Task Shot(string name, GameObject target, float back, float side, float height, float lookUp, float fov = 55)
        {
            var m = G.Manager;
            if (target == null) { Log($"{name}: no target"); return; }
            var t = target.transform;
            // make the culling cell around the target active (cells toggle by distance from the camera)
            var fwd = t.forward; fwd.y = 0; fwd.Normalize();
            var right = Vector3.Cross(Vector3.up, fwd);
            var cam = t.position + fwd * back + right * side + Vector3.up * height;
            var look = t.position + fwd * 0.6f + Vector3.up * lookUp;
            m.Player?.Teleport(t.position + fwd * (back - 1.2f) + right * (side + 1.5f), Mathf.Atan2(-fwd.x, -fwd.z) * Mathf.Rad2Deg);
            m.Cam.Cinematic = (cam, look, fov);
            await Seconds(1.8f);
            var frames = 0; var ft = Time.realtimeSinceStartup;
            while (Time.realtimeSinceStartup - ft < 1) { frames++; await Awaitable.NextFrameAsync(); }
            Capture(name);
            shots.Add(new Dictionary<string, object> { ["shot"] = name, ["fps"] = frames, ["target"] = target.name, ["pos"] = target.transform.position.ToString() });
            Log($"{name}: {target.name} {frames} fps");
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
            await Shot("s01_noodle", Find("St_Shop_Noodle"), 6.5f, -3.5f, 1.7f, 2.2f);
            await Shot("s02_arcade", Find("St_Shop_Arcade"), 6.0f, 3.0f, 1.7f, 2.2f);
            await Shot("s03_clinic", Find("St_Shop_Clinic"), 6.0f, -2.5f, 1.7f, 2.2f);
            await Shot("s04_pharmacy_pawn", Find("St_Shop_Pharmacy"), 7.0f, 3.5f, 1.7f, 2.4f);
            await Shot("s05_capsule", Find("St_Shop_Capsule"), 6.0f, -3.0f, 1.7f, 2.4f);
            await Shot("s06_shutters", Find("St_Shop_Shuttered"), 5.0f, 2.5f, 1.6f, 1.8f);
            await Shot("s07_run_long", Find("St_Shop_Noodle", 3), 4.0f, -14f, 1.8f, 2.5f, 60);
            await Shot("s08_foodcart", Find("St_FoodCart"), -5.0f, 2.0f, 1.7f, 1.2f);
            await Shot("s09_dumpster", Find("St_Dumpster"), 4.5f, 1.5f, 1.6f, 0.8f);
            await Shot("s10_shelter", Find("St_TramShelter"), 6.0f, -2.5f, 1.7f, 1.6f);
            await Shot("s11_wall_life", Find("St_FireEscape"), 9.0f, -3f, 1.8f, 6.5f, 60);
            await Shot("s12_hanging", Find("St_HangingSign"), 9.0f, -6f, 1.7f, 5.0f, 60);
            await Shot("s13_service_bay", Find("St_Shop_Wall"), 4.5f, 1.8f, 1.6f, 1.4f);
            await Shot("s14_kerb", Find("St_Bollard"), 3.5f, 3.5f, 1.5f, 0.2f);
            m.Cam.Cinematic = null;
        }

        void Capture(string name, int w = 1600, int h = 900)
        {
            var cam = G.Manager?.Cam?.Cam;
            if (cam == null) { errors.Add("no camera for " + name); return; }
            var rt = RenderTexture.GetTemporary(w, h, 24, RenderTextureFormat.ARGB32);
            var prev = cam.targetTexture;
            try
            {
                cam.targetTexture = rt;
                cam.Render();
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
    /// <summary>Editor entry point for <see cref="CityStreetTour"/> (batch: -executeMethod EOA.CityStreetTourRunner.Run [-streetOut dir]).</summary>
    public static class CityStreetTourRunner
    {
        const string Key = "EOA_STREET_TOUR";

        public static void Run()
        {
            var args = Environment.GetCommandLineArgs();
            var i = Array.IndexOf(args, "-streetOut");
            var dir = i >= 0 && i + 1 < args.Length ? args[i + 1] : Path.GetFullPath(Path.Combine(Application.dataPath, "..", "..", "..", "Captures", "street"));
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
                if (s == PlayModeStateChange.EnteredPlayMode && SessionState.GetBool(Key, false)) CityStreetTour.Begin(SessionState.GetString(Key + "_dir", ""));
            };
            EditorApplication.update += Poll;
        }

        static void Poll()
        {
            if (!SessionState.GetBool(Key, false)) return;
            var started = DateTime.TryParse(SessionState.GetString(Key + "_started", ""), null, System.Globalization.DateTimeStyles.RoundtripKind, out var t) ? t : DateTime.UtcNow;
            var timedOut = (DateTime.UtcNow - started).TotalMinutes > 15;
            if (!EditorApplication.isPlaying || (!CityStreetTour.Done && !timedOut)) return;
            SessionState.SetBool(Key, false);
            var failed = CityStreetTour.Failed || timedOut;
            Debug.Log($"[street-tour] finished: {(failed ? "FAILED" : "OK")}{(timedOut ? " (timeout)" : "")}");
            EditorApplication.ExitPlaymode();
            if (Application.isBatchMode) EditorApplication.delayCall += () => EditorApplication.Exit(failed ? 1 : 0);
        }
    }
#endif
}
