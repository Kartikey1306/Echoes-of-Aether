using System;
using System.Collections.Generic;
using System.IO;
using System.Threading.Tasks;
using Unity.Profiling;
using Unity.Profiling.LowLevel.Unsafe;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.LowLevel;
using static EOA.ProtoSpace;

namespace EOA
{
    /// <summary>
    /// Player-side performance benchmark. Development players only (ignored in release builds and never active in normal
    /// play). Start a development build with:
    ///   EchoesOfAether.app/Contents/MacOS/EchoesOfAether -benchmark out.json [-benchPreset high] [-benchRes 1920x1080]
    ///     [-benchScenes city,combat,zones] [-benchProfile capture.raw]
    /// Scripted run: main menu, new game (intro skipped), open-city traversal (avenue sprint, market street, arcology
    /// avenue, elevated vistas), a heavy plaza fight (drones + Sentinels, abilities, VFX) and a quick tour of every zone.
    /// Records per frame: wall frame time, CPU main/render thread, GPU time (FrameTimingManager), GC bytes, draw/SetPass/
    /// batch/triangle counts and a set of player-loop markers used to attribute spikes over 33 ms. Writes one JSON
    /// report (per-scenario avg, 1%/0.1% lows, percentiles, spikes with causes, zone build sections) and quits.
    /// Saves and settings go to a private directory next to the report, so a benchmark never touches player data.
    /// </summary>
    public sealed class Benchmark : MonoBehaviour
    {
        public static bool Active { get; private set; }

        const int Cap = 150000;
        static string outPath, preset = "high", scenes = "city,combat,zones", profilePath, profilePhase = "combat", tracePath;
        UnityEngine.Experimental.Rendering.GraphicsStateCollection trace;
        readonly List<object> sweep = new();
        readonly List<object> census = new();
        static float profileSeconds = 5;
        bool profiling;
        readonly HashSet<string> profiledPhases = new();
        double profileStop;
        static Vector2Int res = new(1920, 1080);

        // ------------------------------------------------------------------ per-frame samples (preallocated, no GC)
        float[] ft, cpu, rt, gpu, gpuCpu, present;
        int[] gc, draws, setpass, batches, phaseOf;
        long[] tris;
        int n;
        double lastT;
        readonly FrameTiming[] timing = new FrameTiming[1];

        ProfilerRecorder rMain, rRender, rGc, rGcCount, rDraws, rSetPass, rBatches, rTris, rPresent, rSysMem, rGfxMem;
        readonly Dictionary<string, long> memPeak = new();

        static readonly string[] MarkerNames =
        {
            "GC.Collect", "Shader.CreateGPUProgram", "Shader.Parse", "Loading.ReadObject", "Loading.AwakeFromLoad",
            "Update.ScriptRunBehaviourUpdate", "PreLateUpdate.ScriptRunBehaviourLateUpdate", "Update.ScriptRunDelayedTasks",
            "FixedUpdate.PhysicsFixedUpdate", "FixedUpdate.ScriptRunBehaviourFixedUpdate", "PreLateUpdate.DirectorUpdateAnimationBegin",
            "PreLateUpdate.DirectorUpdateAnimationEnd", "PostLateUpdate.FinishFrameRendering", "PostLateUpdate.UpdateAllSkinnedMeshes",
            "PreUpdate.AIUpdatePostScript", "PostLateUpdate.UpdateAudio", "UIElementsUpdatePanels", "UIR.DrawChain",
            "PostLateUpdate.PlayerUpdateCanvases", "Gfx.WaitForPresentOnGfxThread", "Gfx.WaitForGfxCommandsFromMainThread",
            "Gfx.WaitForRenderThread", "PreUpdate.UpdateVideo", "Physics.Processing", "ParticleSystem.Update",
            "PostLateUpdate.ParticleSystemEndUpdateAll", "NavMeshManager", "AsyncUploadManager.AsyncResourceUpload",
            "GpuProgramMetal.GetCachedPipeline", "GpuProgramMetal.CreateCachedPipelineAsync", "CreateGraphicsPipelineAsync", "CreateGraphicsPSOJobFunc",
            "Shader.CompileGPUProgram", "Gfx.PresentFrame", "Gfx.WaitForRenderThread", "Gfx.UploadTexture", "Gfx.CreateTexture",
            "Inl_UniversalRenderPipeline.RenderSingleCameraInternal: Reflection Probes Camera", "Inl_UniversalRenderPipeline.RenderSingleCameraInternal: Main Camera",
        };
        ProfilerRecorder[] markers;
        // Marker time per spike candidate (only kept for frames over the spike threshold).
        readonly List<Spike> spikes = new(512);
        readonly float[] markerMs = new float[MarkerNames.Length];

        struct Spike
        {
            public int Frame;
            public float T, Ms, Cpu, Gpu, Rt;
            public int Gc, Phase;
            public string Cause, Top;
        }

        readonly List<string> phases = new();
        int phase;
        readonly List<Dictionary<string, object>> loads = new();
        readonly List<Dictionary<string, object>> events = new();
        readonly List<string> errors = new();
        Gamepad pad;
        GamepadState padState;
        bool padDirty;
        double t0;

        // ------------------------------------------------------------------ entry

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void FromCommandLine()
        {
            var args = Environment.GetCommandLineArgs();
            var i = Array.IndexOf(args, "-benchmark");
            if (i < 0) return;
            if (!Debug.isDebugBuild && !Application.isEditor) { Debug.LogWarning("[bench] -benchmark ignored in release builds"); return; }
            outPath = i + 1 < args.Length && !args[i + 1].StartsWith("-") ? args[i + 1] : Path.Combine(Application.persistentDataPath, "benchmark.json");
            string Arg(string k) { var j = Array.IndexOf(args, k); return j >= 0 && j + 1 < args.Length ? args[j + 1] : null; }
            preset = Arg("-benchPreset") ?? preset;
            scenes = Arg("-benchScenes") ?? scenes;
            profilePath = Arg("-benchProfile");
            profilePhase = Arg("-benchProfilePhase") ?? profilePhase;
            tracePath = Arg("-benchTraceGsc");
            if (float.TryParse(Arg("-benchProfileSeconds") ?? "", System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out var ps)) profileSeconds = ps;
            var r = Arg("-benchRes");
            if (r != null && r.Split('x') is { Length: 2 } wh && int.TryParse(wh[0], out var w) && int.TryParse(wh[1], out var h)) res = new Vector2Int(w, h);
            Active = true;
            var go = new GameObject("Benchmark");
            DontDestroyOnLoad(go);
            go.AddComponent<Benchmark>();
        }

        void Awake()
        {
            ft = new float[Cap]; cpu = new float[Cap]; rt = new float[Cap]; gpu = new float[Cap]; gpuCpu = new float[Cap]; present = new float[Cap];
            gc = new int[Cap]; draws = new int[Cap]; setpass = new int[Cap]; batches = new int[Cap]; phaseOf = new int[Cap]; tris = new long[Cap];
            rMain = ProfilerRecorder.StartNew(ProfilerCategory.Internal, "Main Thread", 4);
            rRender = ProfilerRecorder.StartNew(ProfilerCategory.Render, "CPU Render Thread Frame Time", 4);
            rGc = ProfilerRecorder.StartNew(ProfilerCategory.Memory, "GC Allocated In Frame", 4);
            rGcCount = ProfilerRecorder.StartNew(ProfilerCategory.Memory, "GC Allocation In Frame Count", 4);
            rDraws = ProfilerRecorder.StartNew(ProfilerCategory.Render, "Draw Calls Count", 4);
            rSetPass = ProfilerRecorder.StartNew(ProfilerCategory.Render, "SetPass Calls Count", 4);
            rBatches = ProfilerRecorder.StartNew(ProfilerCategory.Render, "Batches Count", 4);
            rTris = ProfilerRecorder.StartNew(ProfilerCategory.Render, "Triangles Count", 4);
            rPresent = ProfilerRecorder.StartNew(ProfilerCategory.Render, "Gfx.WaitForPresentOnGfxThread", 4);
            rSysMem = ProfilerRecorder.StartNew(ProfilerCategory.Memory, "System Used Memory", 1);
            rGfxMem = ProfilerRecorder.StartNew(ProfilerCategory.Memory, "Gfx Used Memory", 1);
            markers = new ProfilerRecorder[MarkerNames.Length];
            for (var i = 0; i < markers.Length; i++) markers[i] = ProfilerRecorder.StartNew(ProfilerCategory.Internal, MarkerNames[i], 4);
            phases.Add("boot");
            Application.runInBackground = true;
            InputSystem.settings.backgroundBehavior = InputSettings.BackgroundBehavior.IgnoreFocus;
            Application.logMessageReceived += OnLog;
        }

        void OnDestroy()
        {
            Application.logMessageReceived -= OnLog;
            rSysMem.Dispose(); rGfxMem.Dispose();
            rMain.Dispose(); rRender.Dispose(); rGc.Dispose(); rGcCount.Dispose(); rDraws.Dispose(); rSetPass.Dispose(); rBatches.Dispose(); rTris.Dispose(); rPresent.Dispose();
            if (markers != null) foreach (var m in markers) m.Dispose();
        }

        void OnLog(string msg, string stack, LogType type)
        {
            if ((type == LogType.Error || type == LogType.Exception || type == LogType.Assert) && errors.Count < 200)
                errors.Add($"{type}: {msg}\n{(stack?.Length > 600 ? stack.Substring(0, 600) : stack)}");
        }

        static void Log(string m) => Debug.Log($"[bench] {Time.realtimeSinceStartup:0.0}s frame {Time.frameCount}: {m}");

        void SetPhase(string name)
        {
            var i = phases.IndexOf(name);
            if (i < 0) { phases.Add(name); i = phases.Count - 1; }
            phase = i;
            var want = ProfileSecondsFor(name);
            if (profilePath != null && !profiling && want > 0 && profiledPhases.Add(name))
            {
                // Binary profiler capture with managed allocation call stacks (open in the Profiler window, or
                // EOA.EditorTools.ProfileReport). Perturbs timings: use a separate run for the numbers.
                profiling = true;
                profileStop = Time.realtimeSinceStartupAsDouble + want;
                var file = Path.Combine(Path.GetDirectoryName(profilePath) ?? ".", Path.GetFileNameWithoutExtension(profilePath) + "_" + name.Replace(':', '_').Replace('(', '_').Replace(')', '_').Replace(' ', '_') + ".raw");
                UnityEngine.Profiling.Profiler.logFile = file;
                UnityEngine.Profiling.Profiler.enableBinaryLog = true;
                UnityEngine.Profiling.Profiler.enableAllocationCallstacks = true;
                UnityEngine.Profiling.Profiler.enabled = true;
                Event("profiler capture start → " + file);
            }
        }

        /// <summary>-benchProfilePhase "a,b=12,c": seconds per phase (default -benchProfileSeconds); 0 = not profiled.</summary>
        static float ProfileSecondsFor(string phaseName)
        {
            foreach (var item in profilePhase.Split(','))
            {
                var kv = item.Split('=');
                if (kv[0] != phaseName) continue;
                return kv.Length > 1 && float.TryParse(kv[1], System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out var v) ? v : profileSeconds;
            }
            return 0;
        }

        void StopProfile()
        {
            if (!profiling) return;
            profiling = false;
            UnityEngine.Profiling.Profiler.enabled = false;
            UnityEngine.Profiling.Profiler.enableBinaryLog = false;
            UnityEngine.Profiling.Profiler.logFile = "";
            Event("profiler capture stop");
        }

        void Event(string what) => events.Add(new Dictionary<string, object> { ["t"] = Math.Round(Time.realtimeSinceStartupAsDouble - t0, 3), ["frame"] = n, ["phase"] = phases[phase], ["event"] = what });

        // ------------------------------------------------------------------ recording (every frame)

        void Update()
        {
            FrameTimingManager.CaptureFrameTimings();
            var now = Time.realtimeSinceStartupAsDouble;
            if (lastT == 0) { lastT = now; return; }
            var ms = (float)((now - lastT) * 1000.0);
            lastT = now;
            if (n >= Cap) return;
            ft[n] = ms;
            cpu[n] = rMain.Valid ? rMain.LastValue * 1e-6f : 0;
            rt[n] = rRender.Valid ? rRender.LastValue * 1e-6f : 0; // counter in ns
            gc[n] = rGc.Valid ? (int)rGc.LastValue : 0;
            draws[n] = rDraws.Valid ? (int)rDraws.LastValue : 0;
            setpass[n] = rSetPass.Valid ? (int)rSetPass.LastValue : 0;
            batches[n] = rBatches.Valid ? (int)rBatches.LastValue : 0;
            tris[n] = rTris.Valid ? rTris.LastValue : 0;
            present[n] = rPresent.Valid ? rPresent.LastValue * 1e-6f : 0;
            if (FrameTimingManager.GetLatestTimings(1, timing) > 0)
            {
                gpu[n] = (float)timing[0].gpuFrameTime;
                gpuCpu[n] = (float)timing[0].cpuMainThreadFrameTime;
            }
            phaseOf[n] = phase;
            if ((n & 63) == 0 && rSysMem.Valid)
            {
                var pn = phases[phase];
                var m = rSysMem.LastValue;
                if (!memPeak.TryGetValue(pn, out var old) || m > old) memPeak[pn] = m;
            }
            if (ms > 33.4f && spikes.Count < 4000) RecordSpike(ms);
            n++;
            if (padDirty && pad != null) { InputSystem.QueueStateEvent(pad, padState); padDirty = false; }
            if (profiling && now > profileStop) StopProfile();
        }

        void RecordSpike(float ms)
        {
            for (var i = 0; i < markers.Length; i++) markerMs[i] = markers[i].Valid ? markers[i].LastValue * 1e-6f : 0;
            var top = new List<(string, float)>();
            for (var i = 0; i < markers.Length; i++) if (markerMs[i] >= 1f) top.Add((MarkerNames[i], markerMs[i]));
            top.Sort((a, b) => b.Item2.CompareTo(a.Item2));
            var sb = new System.Text.StringBuilder();
            for (var i = 0; i < top.Count && i < 5; i++) sb.Append(i > 0 ? ", " : "").Append(top[i].Item1).Append(' ').Append(top[i].Item2.ToString("0.0"));
            float M(string name) { var k = Array.IndexOf(MarkerNames, name); return k >= 0 ? markerMs[k] : 0; }
            string cause;
            var pname = phases[phase];
            if (pname.StartsWith("load")) cause = "loading";
            else if (M("GC.Collect") >= 4) cause = "gc";
            else if (M("Shader.CreateGPUProgram") + M("Shader.Parse") + M("Shader.CompileGPUProgram") + M("GpuProgramMetal.GetCachedPipeline") + M("CreateGraphicsPipelineAsync") >= 3) cause = "shader/pso-compile";
            else if (M("Inl_UniversalRenderPipeline.RenderSingleCameraInternal: Reflection Probes Camera") >= 3) cause = "reflection-probe";
            else if (M("Loading.ReadObject") + M("Loading.AwakeFromLoad") + M("AsyncUploadManager.AsyncResourceUpload") >= 4) cause = "asset-load";
            else if (gpu[n] > 30 && gpu[n] > cpu[n]) cause = "gpu";
            else if (top.Count > 0) cause = top[0].Item1;
            else cause = "unknown";
            spikes.Add(new Spike { Frame = n, T = (float)(Time.realtimeSinceStartupAsDouble - t0), Ms = ms, Cpu = cpu[n], Gpu = gpu[n], Rt = rt[n], Gc = gc[n], Phase = phase, Cause = cause, Top = sb.ToString() });
        }

        // ------------------------------------------------------------------ virtual gamepad

        void Stick(Vector2 v) { if (padState.leftStick != v) { padState.leftStick = v; padDirty = true; } }

        void Button(GamepadButton b, bool down)
        {
            if (b == GamepadButton.LeftTrigger || b == GamepadButton.RightTrigger)
            {
                var v = down ? 1f : 0f;
                if (b == GamepadButton.LeftTrigger && padState.leftTrigger != v) { padState.leftTrigger = v; padDirty = true; }
                if (b == GamepadButton.RightTrigger && padState.rightTrigger != v) { padState.rightTrigger = v; padDirty = true; }
                return;
            }
            var bit = 1u << (int)b;
            var now = (padState.buttons & bit) != 0;
            if (now == down) return;
            padState.buttons = down ? padState.buttons | bit : padState.buttons & ~bit;
            padDirty = true;
        }

        async Awaitable Tap(GamepadButton b)
        {
            Button(b, true);
            await Awaitable.NextFrameAsync();
            await Awaitable.NextFrameAsync();
            Button(b, false);
            await Awaitable.NextFrameAsync();
        }

        /// <summary>Steer the stick toward a Unity-space point relative to the camera heading.</summary>
        void SteerTo(Vector3 target, float mag = 1)
        {
            var p = G.Manager.Player;
            var cam = G.Manager.Cam;
            if (p == null || cam == null) { Stick(Vector2.zero); return; }
            var d = target - p.Position; d.y = 0;
            if (d.sqrMagnitude < 0.01f) { Stick(Vector2.zero); return; }
            d.Normalize();
            Stick(new Vector2(Vector3.Dot(d, cam.Right), Vector3.Dot(d, cam.Forward)).normalized * mag);
        }

        // ------------------------------------------------------------------ scenario

        static async Awaitable Seconds(float s)
        {
            var end = Time.realtimeSinceStartup + s;
            while (Time.realtimeSinceStartup < end) await Awaitable.NextFrameAsync();
        }

        static async Awaitable<bool> Until(Func<bool> cond, float timeout)
        {
            var end = Time.realtimeSinceStartup + timeout;
            while (!cond())
            {
                if (Time.realtimeSinceStartup > end) return false;
                await Awaitable.NextFrameAsync();
            }
            return true;
        }

        async void Start()
        {
            t0 = Time.realtimeSinceStartupAsDouble;
            var ok = true;
            try { await Run(); }
            catch (Exception e) { errors.Add("benchmark aborted: " + e); ok = false; }
            Stick(Vector2.zero);
            StopProfile();
            if (trace != null)
            {
                try
                {
                    trace.EndTrace();
                    var ok2 = trace.SaveToFile(tracePath);
                    Event($"gsc trace saved={ok2}: {trace.variantCount} variants, {trace.totalGraphicsStateCount} states → {tracePath}");
                }
                catch (Exception e) { errors.Add("gsc trace: " + e.Message); }
            }
            try { WriteReport(ok); }
            catch (Exception e) { Debug.LogError("[bench] report failed: " + e); }
            Log("done → " + outPath);
            if (!Application.isEditor) Application.Quit(ok ? 0 : 1);
        }

        async Task Run()
        {
            var dir = Path.GetDirectoryName(Path.GetFullPath(outPath)) ?? ".";
            Directory.CreateDirectory(dir);
            if (!await Until(() => G.Manager != null && G.Manager.Mode == GameMode.Menu, 120)) throw new Exception("menu never appeared");
            // Private settings/saves so the run never touches player data; apply the requested preset without persisting.
            var priv = Path.Combine(dir, "bench_data");
            G.Settings = new Settings(priv);
            G.Saves = new SaveSystem(priv);
            // Uncapped by default (headroom); -benchFrameLimit vsync|60|30 measures what players see with a cap.
            var fl = Array.IndexOf(Environment.GetCommandLineArgs(), "-benchFrameLimit");
            G.Settings.Data.Graphics.FrameLimit = fl >= 0 && fl + 1 < Environment.GetCommandLineArgs().Length ? Environment.GetCommandLineArgs()[fl + 1] : "unlimited";
            var windowed = Array.IndexOf(Environment.GetCommandLineArgs(), "-benchWindowed") >= 0;
            G.Settings.Data.Graphics.Fullscreen = !windowed; // GraphicsConfig re-applies this on every settings change
            ApplyPreset(preset);
#if !UNITY_WEBGL
            // Fullscreen by default: a covered window stops presenting on macOS (frames pin at ~30 ms, no GPU times).
            Screen.SetResolution(res.x, res.y, windowed ? FullScreenMode.Windowed : FullScreenMode.FullScreenWindow);
#endif
            pad = InputSystem.AddDevice<Gamepad>("BenchPad");
            if (tracePath != null)
            {
                // Record every shader variant + graphics state the run touches (PSO warm-up data, see ShaderWarmup).
                trace = new UnityEngine.Experimental.Rendering.GraphicsStateCollection();
                Event("gsc trace " + (trace.BeginTrace() ? "started" : "FAILED to start"));
            }
            await Seconds(1);
            SetPhase("menu");
            await Seconds(4);

            SetPhase("load:plaza(new game)");
            var tl = Time.realtimeSinceStartupAsDouble;
            var ng = G.Manager.NewGame(Characters.Kael, 3);
            await Until(() => G.Manager.Cinematics.Active != null || ng.IsCompleted, 180);
            RecordLoad("plaza", tl, "new game");
            SetPhase("intro-cinematic");
            await Seconds(3);
            G.Manager.Cinematics.Stop();
            await Until(() => ng.IsCompleted, 60);
            await Until(() => G.Manager.Mode == GameMode.Play && G.Manager.Cinematics.Active == null, 30);
            SetPhase("postload:plaza");
            await Seconds(3);
            var gs = G.State;
            foreach (var a in new[] { "dash", "pulse", "step" }) if (!gs.HasAbility(a)) gs.Unlock(a);
            gs.SetFlag("tut_moved");
            Invuln();

            if (scenes.Contains("city") && OpenCity.Enabled) await City();
            if (scenes.Contains("combat")) await Combat();
            if (scenes.Contains("zones")) await Zones();
            if (scenes.Contains("sweep")) await Sweep();
            SetPhase("end");
            await Seconds(0.5f);
        }

        void ApplyPreset(string p)
        {
            Preset(G.Settings.Data.Graphics, p);
            G.Manager.ApplySettings();
        }

        static void Invuln()
        {
            var p = G.Manager.Player;
            if (p == null) return;
            p.Invuln = 99999;
            p.Restore();
        }

        void RecordLoad(string zone, double start, string how)
        {
            var d = new Dictionary<string, object> { ["zone"] = zone, ["how"] = how, ["seconds"] = Math.Round(Time.realtimeSinceStartupAsDouble - start, 3) };
            var sec = new List<object>();
            for (var i = 0; i < LoadTrace.Marks.Count; i++)
            {
                var end = i + 1 < LoadTrace.Marks.Count ? LoadTrace.Marks[i + 1].t : LoadTrace.End;
                var dur = end - LoadTrace.Marks[i].t;
                if (dur >= 0.005) sec.Add(new Dictionary<string, object> { ["section"] = LoadTrace.Marks[i].label, ["ms"] = Math.Round(dur * 1000, 1) });
            }
            d["sections"] = sec;
            loads.Add(d);
            Log($"load {zone}: {d["seconds"]} s");
        }

        // ---- city traversal (prototype-space routes, see CityLayout road grid)

        async Task City()
        {
            Log("city traversal");
            // 1. Market avenue sprint west along the avenue (z = 59 road), 2. market street south through Kowloon,
            // 3. arcology avenue east, 4. canal quay, 5. elevated vistas (skywalk + aerial).
            await Route("city:avenue-sprint", new[] { V(-104, 0.2f, 52), V(-175, 0.2f, 52), V(-250, 0.2f, 52), V(-335, 0.2f, 52) }, sprint: true, maxSeconds: 30);
            await Route("city:market-street", new[] { V(-176, 0.2f, 40), V(-176, 0.2f, -30), V(-176, 0.2f, -110), V(-176, 0.2f, -190) }, sprint: false, maxSeconds: 30);
            await Route("city:arcology-avenue", new[] { V(104, 0.2f, 52), V(180, 0.2f, 52), V(264, 0.2f, 52), V(340, 0.2f, 52) }, sprint: true, maxSeconds: 30);
            await Route("city:canal-quay", new[] { V(-90, 0.2f, 214), V(0, 0.2f, 214), V(90, 0.2f, 214), V(170, 0.2f, 214) }, sprint: true, maxSeconds: 25);
            await Vista("city:elevated", new[]
            {
                (V(-134, 9.5f, 62), V(-250, 14, 10)), (V(140, 9.5f, 232), V(-40, 6, 194)), (V(10, 95, 300), V(0, 20, -120)),
                (V(-300, 60, 70), V(200, 30, 50)), (V(120, 48, -40), V(420, 70, -260)),
            });
            Stick(Vector2.zero);
        }

        async Task Route(string name, Vector3[] pts, bool sprint, float maxSeconds)
        {
            var p = G.Manager.Player;
            if (p == null) return;
            SetPhase("settle");
            var g0 = G.World.GroundAt(pts[0] + Vector3.up * 3, 10);
            p.Teleport(g0.HasValue ? new Vector3(pts[0].x, g0.Value + 0.02f, pts[0].z) : pts[0], Mathf.Atan2(pts[1].x - pts[0].x, pts[1].z - pts[0].z) * Mathf.Rad2Deg);
            G.Manager.Cam.SnapBehind(p.YawDeg * Mathf.Deg2Rad);
            await Seconds(1.0f);
            Census(name);
            await Awaitable.NextFrameAsync(); await Awaitable.NextFrameAsync(); // census garbage stays in "settle"
            SetPhase(name);
            Event("route start");
            Button(GamepadButton.East, sprint);
            var end = Time.realtimeSinceStartup + maxSeconds;
            var idx = 1;
            var lastProgress = Time.realtimeSinceStartup;
            var lastPos = p.Position;
            var travelled = 0f;
            var unstuck = 0;
            while (idx < pts.Length && Time.realtimeSinceStartup < end)
            {
                var target = pts[idx];
                var flat = new Vector2(target.x - p.Position.x, target.z - p.Position.z);
                if (flat.magnitude < 3f) { idx++; continue; }
                SteerTo(target);
                // Turn the camera toward the route so the view looks down the street.
                var cam = G.Manager.Cam;
                var want = Mathf.Atan2(target.x - p.Position.x, target.z - p.Position.z);
                cam.Heading += Mathf.DeltaAngle(cam.Heading * Mathf.Rad2Deg, want * Mathf.Rad2Deg) * Mathf.Deg2Rad * Mathf.Min(1, Time.unscaledDeltaTime * 3);
                await Awaitable.NextFrameAsync();
                var moved = (p.Position - lastPos).magnitude;
                travelled += moved;
                lastPos = p.Position;
                if (moved > 0.02f) lastProgress = Time.realtimeSinceStartup;
                else if (Time.realtimeSinceStartup - lastProgress > 1.2f)
                {
                    // Blocked by a prop or car: hop a few metres along the route.
                    var dir = new Vector3(flat.x, 0, flat.y).normalized;
                    var hop = p.Position + dir * 4 + Vector3.up * 3;
                    var gh = G.World.GroundAt(hop, 10);
                    p.Teleport(gh.HasValue ? new Vector3(hop.x, gh.Value + 0.02f, hop.z) : hop - Vector3.up * 3, p.YawDeg);
                    lastPos = p.Position;
                    lastProgress = Time.realtimeSinceStartup;
                    unstuck++;
                }
            }
            Button(GamepadButton.East, false);
            Stick(Vector2.zero);
            Event($"route end: {travelled:0} m, {unstuck} unstuck hops, reached {idx}/{pts.Length}");
        }

        async Task Vista(string name, (Vector3 pos, Vector3 look)[] shots)
        {
            SetPhase(name);
            foreach (var (pos, look) in shots)
            {
                // Slow dolly toward the look point so culling/LOD work like a moving camera.
                var t = 0f;
                while (t < 3f)
                {
                    var k = t / 3f;
                    var at = Vector3.Lerp(pos, Vector3.Lerp(pos, look, 0.15f), k);
                    G.Manager.Cam.Cinematic = (at, look, 55);
                    await Awaitable.NextFrameAsync();
                    t += Time.unscaledDeltaTime;
                }
                SetPhase("settle");
                Census($"{name}@{pos.x:0},{pos.y:0},{pos.z:0}");
                await Awaitable.NextFrameAsync(); await Awaitable.NextFrameAsync();
                SetPhase(name);
            }
            G.Manager.Cam.Cinematic = null;
        }

        // ---- heavy plaza fight

        async Task Combat()
        {
            Log("combat");
            var p = G.Manager.Player;
            SetPhase("settle");
            var start = V(0, 0.2f, 6);
            var gs = G.World.GroundAt(start + Vector3.up * 3, 10);
            p.Teleport(gs.HasValue ? new Vector3(start.x, gs.Value + 0.02f, start.z) : start, 180);
            G.Manager.Cam.SnapBehind(Mathf.PI);
            await Seconds(1);
            SetPhase("combat:spawn");
            Event("spawn e_plaza_drones + sentinels");
            G.Manager.World.SpawnEncounter("e_plaza_drones");
            SpawnSentinels(3, p.Position);
            await Seconds(1.5f);
            SetPhase("combat");
            var censusAt = Time.realtimeSinceStartup + 4;
            var censusDone = false;
            var end = Time.realtimeSinceStartup + 35;
            var next = 0f;
            var step = 0;
            while (Time.realtimeSinceStartup < end)
            {
                Invuln();
                var target = NearestEnemy(p.Position);
                if (target != null)
                {
                    var d = (target.Position - p.Position); d.y = 0;
                    if (d.magnitude > 3.2f) SteerTo(target.Position); else Stick(Vector2.zero);
                }
                else Stick(Vector2.zero);
                if (Time.realtimeSinceStartup >= next)
                {
                    step++;
                    // Light combo, heavy finisher, pulse ability, bolt, dash: the whole kit with its VFX.
                    if (step % 9 == 0) _ = Tap(GamepadButton.LeftShoulder);
                    else if (step % 7 == 0) _ = Tap(GamepadButton.North);
                    else if (step % 11 == 0) _ = Tap(GamepadButton.East);
                    else if (step % 13 == 0) { Button(GamepadButton.LeftTrigger, true); _ = ReleaseLater(GamepadButton.LeftTrigger, 0.05f); }
                    else _ = Tap(GamepadButton.West);
                    next = Time.realtimeSinceStartup + 0.32f;
                }
                if (!censusDone && Time.realtimeSinceStartup > censusAt)
                {
                    censusDone = true;
                    SetPhase("settle");
                    Census("combat");
                    await Awaitable.NextFrameAsync(); await Awaitable.NextFrameAsync();
                    SetPhase("combat");
                }
                // Keep the arena busy: top up drones and Sentinels as they fall.
                if (CountAlive() < 4 && Time.frameCount % 30 == 0)
                {
                    Event("respawn wave");
                    SpawnSentinels(2, p.Position);
                    EnemyFactory.Create("drone", p.Position + new Vector3(6, 6, 6), 0, G.Manager.World.Root, null, true);
                }
                await Awaitable.NextFrameAsync();
            }
            Stick(Vector2.zero);
            SetPhase("settle");
            foreach (var e in new List<Enemy>(Enemy.All)) if (e != null) e.Despawn();
            await Seconds(1);
        }

        async Awaitable ReleaseLater(GamepadButton b, float s)
        {
            await Seconds(s);
            Button(b, false);
        }

        static void SpawnSentinels(int count, Vector3 around)
        {
            for (var i = 0; i < count; i++)
            {
                var a = (i + Time.frameCount % 7) * 2.1f;
                var pos = around + new Vector3(Mathf.Cos(a) * 9, 0, Mathf.Sin(a) * 9);
                var g = G.World.GroundAt(pos + Vector3.up * 3, 10);
                if (g.HasValue) pos.y = g.Value + 0.05f;
                EnemyFactory.Create(i % 3 == 2 ? "stalker" : "sentinel", pos, 0, G.Manager.World.Root, null, true);
            }
        }

        static Enemy NearestEnemy(Vector3 p)
        {
            Enemy best = null;
            var bd = float.MaxValue;
            var all = Enemy.All;
            for (var i = 0; i < all.Count; i++)
            {
                var e = all[i];
                if (e == null || !e.Alive) continue;
                var d = (e.Position - p).sqrMagnitude;
                if (d < bd) { bd = d; best = e; }
            }
            return best;
        }

        static int CountAlive()
        {
            var c = 0;
            var all = Enemy.All;
            for (var i = 0; i < all.Count; i++) if (all[i] != null && all[i].Alive) c++;
            return c;
        }

        // ---- zone tour

        async Task Zones()
        {
            foreach (var zone in new[] { "metro", "facility", "rooftops", "vault", "core", "plaza" })
            {
                Log("zone " + zone);
                SetPhase("load:" + zone);
                var tl = Time.realtimeSinceStartupAsDouble;
                var load = G.Manager.LoadZone(zone, "start");
                await Until(() => load.IsCompleted || G.Manager.Cinematics.Active != null, 180);
                if (G.Manager.Cinematics.Active != null) G.Manager.Cinematics.Stop();
                await Until(() => load.IsCompleted, 120);
                RecordLoad(zone, tl, "zone tour");
                SetPhase("postload:" + zone);
                Event("loading screen hidden");
                Invuln();
                await Seconds(3);
                // Walk around: forward with a slow camera sweep.
                SetPhase("zone:" + zone);
                var p = G.Manager.Player;
                var end = Time.realtimeSinceStartup + 6;
                while (Time.realtimeSinceStartup < end && p != null)
                {
                    Stick(new Vector2(0.25f, 1));
                    G.Manager.Cam.Heading += Time.unscaledDeltaTime * 0.35f;
                    await Awaitable.NextFrameAsync();
                }
                Stick(Vector2.zero);
            }
        }

        // ---- settings sweep: cost of each option at fixed views (Settings must change performance)

        async Task Sweep()
        {
            var views = new List<(string zone, Vector3 pos, float yaw)>
            {
                ("plaza", V(-104, 0.2f, 52), 90),  // avenue mouth looking down the market avenue (city, crowds, traffic)
                ("plaza", V(0, 0.2f, 6), 180),     // plaza arena (combat area) toward the monument and the city
                ("metro", Vector3.zero, 0),       // metro start (indoor, many lights)
            };
            var configs = new (string name, Action<GraphicsSettings> set, bool? ao, bool? dec)[]
            {
                ("high", g => { }, null, null),
                ("ssao off", g => { }, false, null),
                ("decals off", g => { }, null, false),
                ("shadows off", g => g.Shadows = "off", null, null),
                ("shadows low", g => g.Shadows = "low", null, null),
                ("shadows medium", g => g.Shadows = "medium", null, null),
                ("effects medium", g => g.Effects = "medium", null, null),
                ("effects low", g => g.Effects = "low", null, null),
                ("textures low", g => g.Textures = "low", null, null),
                ("view medium", g => g.ViewDistance = "medium", null, null),
                ("view low", g => g.ViewDistance = "low", null, null),
                ("scale 0.85", g => g.Resolution = "balanced", null, null),
                ("scale 0.67", g => g.Resolution = "performance", null, null),
                ("aa off", g => g.Antialiasing = "off", null, null),
                ("aa fxaa", g => g.Antialiasing = "fxaa", null, null),
                ("aa msaa", g => g.Antialiasing = "msaa", null, null),
                ("aa smaa", g => g.Antialiasing = "smaa", null, null),
                ("aa taa", g => g.Antialiasing = "taa", null, null),
                ("preset low", g => Preset(g, "low"), null, null),
                ("preset medium", g => Preset(g, "medium"), null, null),
                ("preset ultra", g => Preset(g, "ultra"), null, null),
            };
            foreach (var (zone, pos, yaw) in views)
            {
                if (G.World.ZoneId != zone)
                {
                    SetPhase("load:" + zone + "(sweep)");
                    var load = G.Manager.LoadZone(zone, "start");
                    await Until(() => load.IsCompleted || G.Manager.Cinematics.Active != null, 180);
                    if (G.Manager.Cinematics.Active != null) G.Manager.Cinematics.Stop();
                    await Until(() => load.IsCompleted, 120);
                }
                var p = G.Manager.Player;
                if (pos != Vector3.zero)
                {
                    var gp = G.World.GroundAt(pos + Vector3.up * 3, 10);
                    p.Teleport(gp.HasValue ? new Vector3(pos.x, gp.Value + 0.02f, pos.z) : pos, yaw);
                }
                G.Manager.Cam.SnapBehind(p.YawDeg * Mathf.Deg2Rad);
                Invuln();
                SetPhase("settle");
                await Seconds(3);
                var view = $"{zone}@{p.Position.x:0},{p.Position.z:0}";
                foreach (var (name, set, ao, dec) in configs)
                {
                    ApplyPreset(preset);
                    set(G.Settings.Data.Graphics);
                    GraphicsConfig.ForceSsao = ao; GraphicsConfig.ForceDecals = dec;
                    G.Manager.ApplySettings();
                    SetPhase("settle");
                    await Seconds(1.2f);
                    var from = n;
                    var ph = "sweep:" + view + ":" + name;
                    SetPhase(ph);
                    await Seconds(2.5f);
                    var st = Stats(f => f == phases.IndexOf(ph), ph);
                    if (st != null) { st["view"] = view; st["config"] = name; sweep.Add(st); }
                }
                GraphicsConfig.ForceSsao = null; GraphicsConfig.ForceDecals = null;
                ApplyPreset(preset);
            }
        }

        static void Preset(GraphicsSettings g, string p)
        {
            if (!Settings.PresetValues(g, p)) Settings.PresetValues(g, "high");
        }

        /// <summary>Visible renderers / submeshes (≈ draws per pass) / shadow casters by scene category (dev diagnostics; allocates).</summary>
        void Census(string label)
        {
            var groups = new Dictionary<string, int[]>();
            int all = 0, vis = 0, sub = 0, cast = 0, skinned = 0;
            foreach (var r in FindObjectsByType<Renderer>(FindObjectsInactive.Exclude, FindObjectsSortMode.None))
            {
                if (!r.enabled || r is ParticleSystemRenderer) continue;
                all++;
                if (!r.isVisible) continue;
                var key = Category(r.transform);
                if (!groups.TryGetValue(key, out var g)) groups[key] = g = new int[4];
                var m = r.sharedMaterials.Length;
                var c = r.shadowCastingMode != UnityEngine.Rendering.ShadowCastingMode.Off;
                g[0]++; g[1] += m; if (c) g[2] += m; if (r is SkinnedMeshRenderer) { g[3]++; skinned++; }
                vis++; sub += m; if (c) cast += m;
            }
            var top = new List<KeyValuePair<string, int[]>>(groups);
            top.Sort((a, b) => b.Value[1].CompareTo(a.Value[1]));
            var rows = new List<string>();
            for (var i = 0; i < top.Count && i < 30; i++) rows.Add($"{top[i].Value[1],5} sub {top[i].Value[0],5} rend {top[i].Value[2],5} cast {top[i].Value[3],3} skin  {top[i].Key}");
            census.Add(new Dictionary<string, object>
            {
                ["label"] = label, ["enabledRenderers"] = all, ["visibleRenderers"] = vis, ["visibleSubmeshes"] = sub,
                ["visibleShadowCasterSubmeshes"] = cast, ["visibleSkinned"] = skinned, ["groups"] = rows,
            });
        }

        static string Category(Transform t)
        {
            // Up to three ancestors from the root, with cell coordinates and numbers folded ("cell_2_3_-4" → "cell_2").
            var parts = new List<string>();
            for (var p = t; p != null; p = p.parent) parts.Add(p.name);
            parts.Reverse();
            var sb = new System.Text.StringBuilder();
            for (var i = 0; i < parts.Count && i < 3; i++)
            {
                var nm = parts[i];
                if (nm.StartsWith("cell_")) { var k = nm.IndexOf('_', 5); nm = k > 0 ? nm.Substring(0, k) : nm; }
                else nm = System.Text.RegularExpressions.Regex.Replace(nm, @"[_ ]?\(?\d+\)?$", "");
                if (i > 0) sb.Append('/');
                sb.Append(nm);
            }
            if (parts.Count > 3) sb.Append("/…").Append(System.Text.RegularExpressions.Regex.Replace(parts[parts.Count - 1], @"[_ ]?\(?\d+\)?$", ""));
            return sb.ToString();
        }

        // ------------------------------------------------------------------ report

        void WriteReport(bool ok)
        {
            var report = new Dictionary<string, object>
            {
                ["ok"] = ok,
                ["version"] = Application.version,
                ["unity"] = Application.unityVersion,
                ["device"] = SystemInfo.deviceModel,
                ["gpu"] = SystemInfo.graphicsDeviceName,
                ["api"] = SystemInfo.graphicsDeviceType.ToString(),
                ["screen"] = $"{Screen.width}x{Screen.height}",
                ["camera"] = G.Manager?.Cam?.Cam != null ? $"{G.Manager.Cam.Cam.pixelWidth}x{G.Manager.Cam.Cam.pixelHeight}" : "-",
                ["preset"] = preset,
                ["graphics"] = G.Settings?.Data.Graphics,
                ["frames"] = n,
                ["seconds"] = Math.Round(Time.realtimeSinceStartupAsDouble - t0, 1),
                ["gpuTiming"] = FrameTimingManager.IsFeatureEnabled(),
                ["recorders"] = new Dictionary<string, bool> { ["mainThread"] = rMain.Valid, ["renderThread"] = rRender.Valid, ["gc"] = rGc.Valid, ["draws"] = rDraws.Valid, ["setpass"] = rSetPass.Valid, ["present"] = rPresent.Valid },
            };
            try
            {
                var handles = new List<ProfilerRecorderHandle>();
                ProfilerRecorderHandle.GetAvailable(handles);
                var names = new List<string>();
                foreach (var h in handles)
                {
                    var d = ProfilerRecorderHandle.GetDescription(h);
                    var nm = d.Name;
                    if (nm.Contains("Thread") || nm.Contains("Shader") || nm.Contains("Pipeline") || nm.Contains("Probe") || nm.StartsWith("Gfx.") || nm.Contains("PSO") || nm.Contains("Culling") || nm.Contains("Render"))
                        names.Add($"{d.Category.Name}/{nm}");
                }
                names.Sort();
                report["availableMarkers"] = names;
            }
            catch (Exception e) { report["availableMarkers"] = e.Message; }
            var valid = new List<string>();
            for (var i = 0; i < markers.Length; i++) if (markers[i].Valid) valid.Add(MarkerNames[i]);
            report["markersValid"] = valid;

            var sc = new List<object>();
            for (var ph = 0; ph < phases.Count; ph++)
            {
                var s = Stats(ph);
                if (s != null) sc.Add(s);
            }
            report["scenarios"] = sc;
            // Aggregates: gameplay = all city/combat/zone phases (no loading, no settle).
            report["summary"] = new Dictionary<string, object>
            {
                ["city"] = Stats(ph => phases[ph].StartsWith("city:"), "city (all)"),
                ["combat"] = Stats(ph => phases[ph] == "combat", "combat"),
                ["zones"] = Stats(ph => phases[ph].StartsWith("zone:"), "zones (all)"),
                ["postload"] = Stats(ph => phases[ph].StartsWith("postload:"), "after loading screen (3 s each)"),
                ["gameplay"] = Stats(ph => phases[ph].StartsWith("city:") || phases[ph] == "combat" || phases[ph].StartsWith("zone:"), "gameplay (all)"),
            };
            var sp = new List<object>();
            var causes = new Dictionary<string, int>();
            foreach (var s in spikes)
            {
                var key = phases[s.Phase].Split(':')[0] + "/" + s.Cause;
                causes[key] = causes.TryGetValue(key, out var c) ? c + 1 : 1;
                if (phases[s.Phase].StartsWith("load")) continue;
                if (sp.Count < 300)
                    sp.Add(new Dictionary<string, object>
                    {
                        ["frame"] = s.Frame, ["t"] = Math.Round(s.T, 2), ["phase"] = phases[s.Phase], ["ms"] = Math.Round(s.Ms, 1), ["cpuMain"] = Math.Round(s.Cpu, 1),
                        ["gpu"] = Math.Round(s.Gpu, 1), ["render"] = Math.Round(s.Rt, 1), ["gcBytes"] = s.Gc, ["cause"] = s.Cause, ["markers"] = s.Top,
                    });
            }
            report["spikeCauses"] = causes;
            var mem = new Dictionary<string, double>();
            foreach (var kv in memPeak) mem[kv.Key] = Math.Round(kv.Value / 1048576.0);
            report["systemMemoryPeakMB"] = mem;
            report["gfxMemoryMB"] = rGfxMem.Valid ? Math.Round(rGfxMem.LastValue / 1048576.0) : -1;
            report["sweep"] = sweep;
            report["census"] = census;
            report["spikes"] = sp;
            report["loads"] = loads;
            report["events"] = events;
            report["errors"] = errors;
            File.WriteAllText(outPath, Newtonsoft.Json.JsonConvert.SerializeObject(report, Newtonsoft.Json.Formatting.Indented));
            // Compact per-frame CSV for plotting / deeper analysis.
            using var w = new StreamWriter(Path.ChangeExtension(outPath, ".frames.csv"));
            w.WriteLine("frame,phase,ms,cpuMain,render,gpu,gcBytes,draws,setpass,batches,tris,present");
            for (var i = 0; i < n; i++)
                w.WriteLine($"{i},{phases[phaseOf[i]]},{ft[i]:0.00},{cpu[i]:0.00},{rt[i]:0.00},{gpu[i]:0.00},{gc[i]},{draws[i]},{setpass[i]},{batches[i]},{tris[i]},{present[i]:0.00}");
        }

        Dictionary<string, object> Stats(int ph) => Stats(p => p == ph, phases[ph]);

        Dictionary<string, object> Stats(Func<int, bool> include, string name)
        {
            var idx = new List<int>();
            for (var i = 0; i < n; i++) if (include(phaseOf[i])) idx.Add(i);
            if (idx.Count < 5) return null;
            var times = new float[idx.Count];
            double sum = 0, sCpu = 0, sGpu = 0, sRt = 0, sGc = 0, sDraw = 0, sSet = 0, sBatch = 0, sTris = 0, sPresent = 0;
            int gcFrames = 0, over33 = 0, over50 = 0, maxGc = 0, gpuN = 0, gpuZero = 0;
            for (var k = 0; k < idx.Count; k++)
            {
                var i = idx[k];
                times[k] = ft[i];
                sum += ft[i]; sCpu += cpu[i]; sRt += rt[i]; sGc += gc[i]; sDraw += draws[i]; sSet += setpass[i]; sBatch += batches[i]; sTris += tris[i]; sPresent += present[i];
                if (gpu[i] > 0) { sGpu += gpu[i]; gpuN++; } else gpuZero++;
                if (gc[i] > 0) gcFrames++;
                maxGc = Math.Max(maxGc, gc[i]);
                if (ft[i] > 33.4f) over33++;
                if (ft[i] > 50f) over50++;
            }
            Array.Sort(times);
            var c = times.Length;
            float Pct(float q) => times[Mathf.Clamp((int)Math.Ceiling(q * c) - 1, 0, c - 1)];
            double WorstAvg(float frac)
            {
                var k = Math.Max(1, (int)Math.Round(c * frac));
                double s = 0;
                for (var i = c - k; i < c; i++) s += times[i];
                return s / k;
            }
            double R(double v, int d = 2) => Math.Round(v, d);
            return new Dictionary<string, object>
            {
                ["name"] = name,
                ["frames"] = c,
                ["seconds"] = R(sum / 1000, 1),
                ["avgFps"] = R(c / (sum / 1000), 1),
                ["avgMs"] = R(sum / c),
                ["p50Ms"] = R(Pct(0.5f)), ["p95Ms"] = R(Pct(0.95f)), ["p99Ms"] = R(Pct(0.99f)), ["maxMs"] = R(times[c - 1], 1),
                ["low1Fps"] = R(1000 / WorstAvg(0.01f), 1),
                ["low01Fps"] = R(1000 / WorstAvg(0.001f), 1),
                ["spikes33"] = over33, ["spikes50"] = over50,
                ["cpuMainMs"] = R(sCpu / c), ["renderThreadMs"] = R(sRt / c), ["gpuMs"] = gpuN > 0 ? R(sGpu / gpuN) : -1, ["waitPresentMs"] = R(sPresent / c),
                ["gcBytesPerFrame"] = R(sGc / c, 0), ["gcFramesPct"] = R(100.0 * gcFrames / c, 1), ["gcMaxBytes"] = maxGc,
                ["noGpuTimingPct"] = R(100.0 * gpuZero / c, 1),
                ["drawCalls"] = R(sDraw / c, 0), ["setPass"] = R(sSet / c, 0), ["batches"] = R(sBatch / c, 0), ["triangles"] = R(sTris / c, 0),
            };
        }
    }

    /// <summary>Zone-load section timestamps (only recorded while a benchmark runs; no cost otherwise).</summary>
    public static class LoadTrace
    {
        public static readonly List<(string label, double t)> Marks = new();
        public static double End;
        static string last;

        public static void Begin()
        {
            if (!Benchmark.Active) return;
            Marks.Clear();
            last = null;
        }

        public static void Mark(string label)
        {
            if (!Benchmark.Active || label == last) return;
            last = label;
            var t = Time.realtimeSinceStartupAsDouble;
            Marks.Add((label, t));
            End = t;
        }

        public static void Finish()
        {
            if (Benchmark.Active) End = Time.realtimeSinceStartupAsDouble;
        }
    }
}
