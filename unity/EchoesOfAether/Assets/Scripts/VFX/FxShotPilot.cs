using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Sky &amp; weather capture run (EOA/Test/FX Shots, editor only: Assets/Scripts/VFX/Editor/FxShots.cs). Starts a new
    /// game, then in the plaza / open city and on the rooftops frames the sky toward each district glow, the zenith, the
    /// rain against street lamps, splashes and ripples on the ground, and a lightning strike (bolt + lit clouds).
    /// Writes &lt;repo&gt;/Captures/fx/*.png and report.json (errors, rain counts, frame times).
    /// </summary>
    public sealed class FxShotPilot : MonoBehaviour
    {
        public static bool Done { get; private set; }
        public static bool Failed { get; private set; }
        string outDir;
        readonly List<string> errors = new();
        readonly Dictionary<string, object> report = new();

        public static void Begin(string dir)
        {
            if (FindAnyObjectByType<FxShotPilot>() != null) return;
            Directory.CreateDirectory(dir);
            Done = false;
            Failed = false;
            var go = new GameObject("FxShotPilot");
            DontDestroyOnLoad(go);
            go.AddComponent<FxShotPilot>().outDir = dir;
        }

        void OnEnable() => Application.logMessageReceived += OnLog;
        void OnDisable() => Application.logMessageReceived -= OnLog;

        void OnLog(string msg, string stack, LogType type)
        {
            if (stack != null && stack.Contains("UnityEditor.Search.")) return;
            if (type == LogType.Error || type == LogType.Exception || type == LogType.Assert) errors.Add(msg);
        }

        async void Start()
        {
            try { await Run(); }
            catch (Exception e) { errors.Add("fx shots: " + e); }
            report["errors"] = errors;
            Failed = errors.Count > 0;
            File.WriteAllText(Path.Combine(outDir, "report.json"), Json(report));
            Done = true;
        }

        static async Task<bool> Until(Func<bool> c, float timeout)
        {
            var t = Time.realtimeSinceStartup;
            while (!c())
            {
                if (Time.realtimeSinceStartup - t > timeout) return false;
                await Awaitable.NextFrameAsync();
            }
            return true;
        }

        static async Task Seconds(float s)
        {
            var t = Time.realtimeSinceStartup;
            while (Time.realtimeSinceStartup - t < s) await Awaitable.NextFrameAsync();
        }

        async Task Run()
        {
            if (!await Until(() => G.Manager != null && G.Manager.Mode == GameMode.Menu, 90)) { errors.Add("menu never appeared"); return; }
            var m = G.Manager;
            var ng = m.NewGame(Characters.Kael, 2);
            await Until(() => m.Cinematics.Active != null || ng.IsCompleted, 90);
            m.Cinematics.Stop();
            await Until(() => ng.IsCompleted, 180);
            await Until(() => m.Mode == GameMode.Play && m.Cinematics.Active == null, 30);
            await Seconds(3f);
            await Zone("plaza");
            var load = m.LoadZone("rooftops", "start");
            await Until(() => load.IsCompleted, 120);
            if (m.Cinematics.Active != null) m.Cinematics.Stop();
            await Seconds(3f);
            await Zone("rooftops");
            m.Cam.Cinematic = null;
        }

        async Task Zone(string zone)
        {
            var m = G.Manager;
            var pz = m.World?.Script as ProceduralZone;
            var weather = pz != null ? pz.ZoneWeather : null;
            var field = weather != null ? weather.Field : null;
            var z = new Dictionary<string, object>
            {
                ["skyTextures"] = RenderSettings.skybox != null && RenderSettings.skybox.HasProperty("_UseSkyTex") && RenderSettings.skybox.GetFloat("_UseSkyTex") > 0.5f,
                ["gpuRain"] = field != null,
                ["rainNear"] = field != null ? field.NearCount : 0,
                ["rainFar"] = field != null ? field.FarCount : 0,
                ["splashesPerSecond"] = field != null ? field.SplashesPerSecond : 0,
            };
            report[zone] = z;
            var p = m.Player != null ? m.Player.Position : Vector3.zero;
            var eye = p + Vector3.up * 1.7f;
            // frame time over 2 s
            var frames = 0; var ft = Time.realtimeSinceStartup;
            while (Time.realtimeSinceStartup - ft < 2) { frames++; await Awaitable.NextFrameAsync(); }
            z["fps"] = frames / 2f;

            // Sky toward the four horizons (Unity -X magenta gate, +Z amber, +X cyan, -Z blue) and up.
            var dirs = new (string name, Vector3 d)[] { ("west", Vector3.left), ("north", Vector3.forward), ("east", Vector3.right), ("south", Vector3.back) };
            foreach (var (name, d) in dirs)
                await Shot(eye, eye + d * 100f + Vector3.up * 22f, 70, $"{zone}_sky_{name}");
            await Shot(eye, eye + Vector3.forward * 40f + Vector3.up * 100f, 75, $"{zone}_sky_up");
            // Rain: street level toward the nearest bright lights, then low toward the ground for splashes / ripples.
            var lights = FindObjectsByType<Light>(FindObjectsSortMode.None).Where(l => l.type != LightType.Directional && l.isActiveAndEnabled)
                .OrderBy(l => (l.transform.position - eye).sqrMagnitude).ToList();
            var target = lights.Count > 0 ? lights[0].transform.position : eye + Vector3.forward * 10f;
            var flat = target - eye; flat.y = 0;
            var away = flat.sqrMagnitude > 0.01f ? -flat.normalized : Vector3.back;
            await Shot(eye + away * 3f, target, 55, $"{zone}_rain_lamp");
            var fwd = flat.sqrMagnitude > 0.01f ? flat.normalized : Vector3.forward;
            await Shot(p + Vector3.up * 0.9f - fwd * 1.5f, p + fwd * 5f, 50, $"{zone}_splashes", 1.0f);
            // Lightning: a bolt straight ahead, simulated at a fixed 60 fps so the flicker sequence is not skipped by the
            // slow batch-mode frames; first stroke and the dimmer re-strike.
            if (weather != null)
            {
                var look = eye + Vector3.forward * 100f + Vector3.up * 14f;
                m.Cam.Cinematic = (eye, look, 70);
                await Seconds(0.6f);
                Time.captureDeltaTime = 1f / 60f;
                weather.TriggerLightning(1f, new Vector3(0.12f, 0.22f, 1f).normalized, true);
                await Awaitable.NextFrameAsync();
                await Capture($"{zone}_lightning");
                for (var k = 0; k < 7; k++) await Awaitable.NextFrameAsync();
                await Capture($"{zone}_lightning_restrike");
                // above the roofs: the whole bolt against the deck
                var high = eye + Vector3.up * 45f;
                m.Cam.Cinematic = (high, high + Vector3.forward * 100f + Vector3.up * 12f, 70);
                Time.captureDeltaTime = 0;
                await Seconds(0.6f);
                Time.captureDeltaTime = 1f / 60f;
                weather.TriggerLightning(1f, new Vector3(-0.15f, 0.2f, 1f).normalized, true);
                await Awaitable.NextFrameAsync();
                await Capture($"{zone}_lightning_high");
                Time.captureDeltaTime = 0;
                await Seconds(0.5f);
            }
            // Wide establishing shot from above.
            await Shot(p + new Vector3(-30, 45, -60), p + new Vector3(0, 30, 80), 60, $"{zone}_aerial");
        }

        async Task Shot(Vector3 pos, Vector3 look, float fov, string name, float settle = 0.5f)
        {
            G.Manager.Cam.Cinematic = (pos, look, fov);
            await Seconds(settle);
            await Capture(name);
        }

        async Task Capture(string name, int w = 1600, int h = 900)
        {
            await Awaitable.NextFrameAsync();
            var cam = G.Manager?.Cam?.Cam;
            if (cam == null) { errors.Add("no camera for " + name); return; }
            var rt = RenderTexture.GetTemporary(w, h, 24, RenderTextureFormat.ARGB32);
            var prev = cam.targetTexture;
            try
            {
                await CaptureUtil.RenderInto(cam, rt);
                var act = RenderTexture.active;
                RenderTexture.active = rt;
                var tex = new Texture2D(w, h, TextureFormat.RGBA32, false);
                tex.ReadPixels(new Rect(0, 0, w, h), 0, 0);
                tex.Apply();
                RenderTexture.active = act;
                File.WriteAllBytes(Path.Combine(outDir, name + ".png"), tex.EncodeToPNG());
                Destroy(tex);
            }
            catch (Exception e) { errors.Add($"capture {name}: {e.Message}"); }
            finally
            {
                cam.targetTexture = prev;
                RenderTexture.ReleaseTemporary(rt);
            }
        }

        static string Json(object o)
        {
            var sb = new StringBuilder();
            void W(object v, int ind)
            {
                var pad = new string(' ', ind * 2);
                switch (v)
                {
                    case null: sb.Append("null"); break;
                    case string s: sb.Append('"').Append(s.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\n", "\\n")).Append('"'); break;
                    case bool b: sb.Append(b ? "true" : "false"); break;
                    case float f: sb.Append(f.ToString("0.###", System.Globalization.CultureInfo.InvariantCulture)); break;
                    case int i: sb.Append(i); break;
                    case Dictionary<string, object> d:
                        sb.Append("{\n");
                        var k = 0;
                        foreach (var kv in d)
                        {
                            sb.Append(pad).Append("  \"").Append(kv.Key).Append("\": ");
                            W(kv.Value, ind + 1);
                            sb.Append(++k < d.Count ? ",\n" : "\n");
                        }
                        sb.Append(pad).Append('}');
                        break;
                    case List<string> l:
                        sb.Append('[');
                        for (var j = 0; j < l.Count; j++) { if (j > 0) sb.Append(", "); W(l[j], ind + 1); }
                        sb.Append(']');
                        break;
                    default: sb.Append('"').Append(v).Append('"'); break;
                }
            }
            W(o, 0);
            return sb.ToString();
        }
    }
}
