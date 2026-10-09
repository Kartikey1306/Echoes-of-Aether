using System;
using System.Collections.Generic;
using System.Reflection;
using System.Runtime.CompilerServices;
using Unity.Jobs;
using UnityEngine;
using UnityEngine.Experimental.Rendering;
using UnityEngine.Rendering;

namespace EOA
{
    /// <summary>
    /// Pre-compiles the shader variants and pipeline states the game uses so the first time a material, light setup or
    /// effect appears on screen does not stall a frame (Metal compiles shaders and PSOs on first use).
    ///
    /// Data (built by EOA.EditorTools.ShaderWarmupBuilder from benchmark/tour traces, see EOA.Benchmark -benchTraceGsc):
    ///   Resources/Perf/EOA_Warmup_&lt;GraphicsDeviceType&gt; — GraphicsStateCollection (variants + render states, PSO warm-up)
    ///   Resources/Perf/EOA_Warmup                        — ShaderVariantCollection (WebGL / APIs without PSO warm-up)
    /// Started at boot behind the menu; zone loads wait for it (bounded) before the loading screen hides.
    /// </summary>
    public static class ShaderWarmup
    {
        static GraphicsStateCollection gsc;
        static ShaderVariantCollection svc;
        static JobHandle job;
        static bool started, jobRunning;
        static float t0;
        public static bool Done { get; private set; }
        public static string Status { get; private set; } = "idle";

        public static void Begin()
        {
            if (started) return;
            started = true;
            t0 = Time.realtimeSinceStartup;
            try
            {
                var api = SystemInfo.graphicsDeviceType;
                gsc = api is GraphicsDeviceType.Metal or GraphicsDeviceType.Vulkan or GraphicsDeviceType.Direct3D12
                    ? Resources.Load<GraphicsStateCollection>("Perf/EOA_Warmup_" + api)
                    : null;
                if (gsc != null && gsc.graphicsDeviceType == api)
                {
                    job = gsc.WarmUp();
                    jobRunning = true;
                    Status = $"warming {gsc.variantCount} variants / {gsc.totalGraphicsStateCount} states";
                    Debug.Log("[warmup] " + Status);
                    return;
                }
                svc = Resources.Load<ShaderVariantCollection>("Perf/EOA_Warmup");
                if (svc == null) { Finish("no warm-up data"); return; }
                Status = $"warming {svc.variantCount} variants (progressive)";
                Debug.Log("[warmup] " + Status);
            }
            catch (Exception e) { Finish("failed: " + e.Message); }
        }

        /// <summary>Advance progressive warm-up (WebGL) a few variants per call; poll the PSO job. Call every frame.</summary>
        public static void Tick(int variantsPerFrame = 6)
        {
            if (!started || Done) return;
            if (jobRunning)
            {
                if (!job.IsCompleted) return;
                job.Complete();
                jobRunning = false;
                Finish($"{gsc.completedWarmupCount} states");
                return;
            }
            if (svc == null) { Finish("none"); return; }
            try
            {
                if (svc.WarmUpProgressively(variantsPerFrame)) Finish($"{svc.warmedUpVariantCount} variants");
            }
            catch (Exception e) { Finish("failed: " + e.Message); }
        }

        static void Finish(string what)
        {
            Done = true;
            Status = "done: " + what;
            Debug.Log($"[warmup] {Status} in {(Time.realtimeSinceStartup - t0) * 1000:0} ms");
        }
    }

    /// <summary>
    /// First-use hitches outside rendering, paid behind the menu instead of in the first fight:
    ///  - Mono JIT: the game assembly's methods are compiled ahead of first call (main thread, a few ms per frame,
    ///    because JIT can run static constructors that touch Unity APIs). Players use Mono on macOS; IL2CPP
    ///    builds (WebGL) skip this.
    ///  - UI fonts: dynamic font assets get the printable ASCII set and its kerning/feature tables up front
    ///    (FontEngine GPOS lookups cost ~40 ms the first time the HUD shows new glyphs).
    /// </summary>
    public static class CodeWarmup
    {
        const string Charset = " !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~·•—–…’“”©×°";
        static List<RuntimeMethodHandle> methods;
        static int next;
        static bool started;
        static float t0;
        public static bool Done { get; private set; }

        public static void Begin()
        {
            if (started) return;
            started = true;
            t0 = Time.realtimeSinceStartup;
            if (Application.isEditor) { Done = true; return; } // editor: no dynamic-font asset churn, JIT irrelevant
            WarmFonts();
            if (Application.platform == RuntimePlatform.WebGLPlayer) { Done = true; return; }
            methods = new List<RuntimeMethodHandle>(16384);
            const BindingFlags all = BindingFlags.Instance | BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.DeclaredOnly;
            try
            {
                foreach (var t in typeof(GameManager).Assembly.GetTypes())
                {
                    if (t.ContainsGenericParameters || t.Namespace?.StartsWith("EOA") != true) continue;
                    foreach (var m in t.GetMethods(all))
                        if (!m.IsAbstract && !m.ContainsGenericParameters && (m.MethodImplementationFlags & MethodImplAttributes.InternalCall) == 0) methods.Add(m.MethodHandle);
                    foreach (var c in t.GetConstructors(all)) if (!c.IsStatic) methods.Add(c.MethodHandle);
                }
            }
            catch (Exception e) { Debug.LogWarning("[warmup] method scan: " + e.Message); }
        }

        static void WarmFonts()
        {
            try
            {
                var n = 0;
                foreach (var fa in Resources.FindObjectsOfTypeAll<UnityEngine.TextCore.Text.FontAsset>())
                {
                    if (fa == null || fa.atlasPopulationMode != UnityEngine.TextCore.Text.AtlasPopulationMode.Dynamic) continue;
                    fa.TryAddCharacters(Charset, out _, true);
                    n++;
                }
                Debug.Log($"[warmup] {n} dynamic font assets pre-populated");
            }
            catch (Exception e) { Debug.LogWarning("[warmup] fonts: " + e.Message); }
        }

        /// <summary>JIT up to <paramref name="budgetMs"/> of methods this frame.</summary>
        public static void Tick(float budgetMs)
        {
            if (!started || Done || methods == null) return;
            var until = Time.realtimeSinceStartupAsDouble + budgetMs / 1000.0;
            while (next < methods.Count && Time.realtimeSinceStartupAsDouble < until)
            {
                try { RuntimeHelpers.PrepareMethod(methods[next]); } catch { }
                next++;
            }
            if (next < methods.Count) return;
            Done = true;
            Debug.Log($"[warmup] JIT: {methods.Count} methods compiled ahead of use ({(Time.realtimeSinceStartup - t0):0.0} s since boot)");
            methods = null;
        }
    }
}
