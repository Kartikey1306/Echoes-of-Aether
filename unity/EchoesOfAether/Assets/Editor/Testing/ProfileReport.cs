using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEditor.Profiling;
using UnityEditorInternal;
using UnityEngine;

namespace EOA.EditorTools
{
    /// <summary>
    /// Summarises a player profiler capture (.raw, e.g. from the benchmark's -benchProfile) without the Profiler window:
    /// managed allocations grouped by call site (needs a capture made with allocation call stacks), the hottest markers
    /// by self time on the main thread, and the markers behind frames over 33 ms. Batch:
    ///   Unity -batchmode -quit -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.ProfileReport.Run
    ///     -profile capture.raw -profileOut report.txt
    /// </summary>
    public static class ProfileReport
    {
        public static void Run()
        {
            var args = Environment.GetCommandLineArgs();
            // Every -profile argument is analysed into <capture>.txt; -gsc traces are turned into warm-up data too.
            var failed = false;
            for (var i = 0; i < args.Length - 1; i++)
            {
                if (args[i] != "-profile") continue;
                var path = args[i + 1];
                var outPath = Path.ChangeExtension(path, ".txt");
                try { File.WriteAllText(outPath, Analyse(path)); Debug.Log("[profile] report → " + outPath); }
                catch (Exception e) { Debug.LogError("[profile] " + path + ": " + e); failed = true; }
            }
            if (Array.IndexOf(args, "-gsc") >= 0) ShaderWarmupBuilder.Build();
            if (failed && Application.isBatchMode) EditorApplication.Exit(1);
        }

        sealed class Agg { public long Bytes; public int Count; public HashSet<int> Frames = new(); }

        public static string Analyse(string path)
        {
            if (string.IsNullOrEmpty(path) || !File.Exists(path)) throw new FileNotFoundException("capture not found", path);
            if (!ProfilerDriver.LoadProfile(path, false)) throw new Exception("could not load " + path);
            int first = ProfilerDriver.firstFrameIndex, last = ProfilerDriver.lastFrameIndex;
            var allocs = new Dictionary<string, Agg>();
            var self = new Dictionary<string, double>();
            var spikeMarkers = new Dictionary<string, double>();
            var spikeFrames = new List<string>();
            var callstack = new List<ulong>();
            var methodCache = new Dictionary<ulong, string>();
            var frames = 0;
            double frameMsTotal = 0;
            // Render thread: self time per marker overall and in frames over 33 ms.
            var rtSelf = new Dictionary<string, double>();
            var rtSpike = new Dictionary<string, double>();
            var rtSpikeFrames = new List<string>();
            long allocBytes = 0;
            var allocFrames = 0;
            for (var f = first; f <= last; f++)
            {
                using var view = ProfilerDriver.GetRawFrameDataView(f, 0);
                if (view == null || !view.valid) continue;
                frames++;
                var frameMs = view.frameTimeMs;
                frameMsTotal += frameMs;
                var gcId = view.GetMarkerId("GC.Alloc");
                var n = view.sampleCount;
                // Depth-first walk: stack of (sample, remaining children); self time = total - children.
                var stack = new List<(int idx, int remaining, double childMs)>();
                var frameSelf = new Dictionary<string, double>();
                long frameAlloc = 0;
                for (var i = 0; i < n; i++)
                {
                    var name = view.GetSampleName(i);
                    var ms = view.GetSampleTimeMs(i);
                    if (stack.Count > 0)
                    {
                        var top = stack[^1];
                        top.remaining--;
                        top.childMs += ms;
                        stack[^1] = top;
                    }
                    if (view.GetSampleMarkerId(i) == gcId)
                    {
                        long bytes = 0;
                        try { bytes = view.GetSampleMetadataCount(i) > 0 ? view.GetSampleMetadataAsLong(i, 0) : 0; } catch { }
                        frameAlloc += bytes;
                        var sb = new StringBuilder();
                        // Ancestor chain (innermost 4, skipping player-loop plumbing).
                        var chain = new List<string>();
                        for (var s = stack.Count - 1; s >= 0 && chain.Count < 4; s--)
                        {
                            var an = view.GetSampleName(stack[s].idx);
                            if (an == "PlayerLoop" || an.StartsWith("Update.") || an.StartsWith("PreLateUpdate.") || an.StartsWith("PostLateUpdate.") || an.StartsWith("FixedUpdate.")) continue;
                            chain.Add(an);
                        }
                        chain.Reverse();
                        sb.Append(string.Join(" > ", chain));
                        callstack.Clear();
                        try { view.GetSampleCallstack(i, callstack); } catch { }
                        var userFrames = 0;
                        foreach (var addr in callstack)
                        {
                            if (!methodCache.TryGetValue(addr, out var m))
                            {
                                var mi = view.ResolveMethodInfo(addr);
                                m = string.IsNullOrEmpty(mi.methodName) ? "" : mi.methodName + (string.IsNullOrEmpty(mi.sourceFileName) ? "" : $" ({Path.GetFileName(mi.sourceFileName)}:{mi.sourceFileLine})");
                                methodCache[addr] = m;
                            }
                            if (m.Length == 0) continue;
                            sb.Append("\n      at ").Append(m);
                            if (++userFrames >= 6) break;
                        }
                        var key = sb.ToString();
                        if (!allocs.TryGetValue(key, out var a)) allocs[key] = a = new Agg();
                        a.Bytes += bytes; a.Count++; a.Frames.Add(f);
                    }
                    var children = view.GetSampleChildrenCount(i);
                    if (children > 0) stack.Add((i, children, 0));
                    else Close(i, ms, 0);
                    // Pop finished parents.
                    while (stack.Count > 0 && stack[^1].remaining == 0)
                    {
                        var done = stack[^1];
                        stack.RemoveAt(stack.Count - 1);
                        Close(done.idx, view.GetSampleTimeMs(done.idx), done.childMs);
                    }

                    void Close(int idx, double total, double childMs)
                    {
                        var nm = view.GetSampleName(idx);
                        var s = Math.Max(0, total - childMs);
                        frameSelf[nm] = (frameSelf.TryGetValue(nm, out var v) ? v : 0) + s;
                    }
                }
                RenderThread(f, frameMs, rtSelf, rtSpike, rtSpikeFrames);
                if (frameAlloc > 0) allocFrames++;
                allocBytes += frameAlloc;
                foreach (var kv in frameSelf) self[kv.Key] = (self.TryGetValue(kv.Key, out var v) ? v : 0) + kv.Value;
                if (frameMs > 33.4)
                {
                    var top = frameSelf.OrderByDescending(kv => kv.Value).Take(6).Select(kv => $"{kv.Key} {kv.Value:0.0}");
                    spikeFrames.Add($"  frame {f}: {frameMs:0.0} ms  ← {string.Join(", ", top)}");
                    foreach (var kv in frameSelf) spikeMarkers[kv.Key] = (spikeMarkers.TryGetValue(kv.Key, out var v) ? v : 0) + kv.Value;
                }
            }
            var o = new StringBuilder();
            o.AppendLine($"capture {path}: frames {first}..{last} ({frames} with main-thread data), avg frame {(frames > 0 ? frameMsTotal / frames : 0):0.00} ms");
            o.AppendLine($"managed allocations: {allocBytes / Math.Max(1, frames)} B/frame avg, {allocFrames}/{frames} frames allocate");
            o.AppendLine();
            o.AppendLine("== allocation sites (bytes over capture, count, frames)");
            foreach (var kv in allocs.OrderByDescending(k => k.Value.Bytes).Take(60))
                o.AppendLine($"{kv.Value.Bytes,10} B {kv.Value.Count,6}x {kv.Value.Frames.Count,5}f  {kv.Key}");
            o.AppendLine();
            o.AppendLine("== main thread self time (ms/frame)");
            foreach (var kv in self.OrderByDescending(k => k.Value).Take(60))
                o.AppendLine($"{kv.Value / Math.Max(1, frames),8:0.000}  {kv.Key}");
            o.AppendLine();
            o.AppendLine($"== frames over 33 ms ({spikeFrames.Count})");
            foreach (var s in spikeFrames.Take(60)) o.AppendLine(s);
            if (spikeMarkers.Count > 0)
            {
                o.AppendLine("  top markers across spike frames:");
                foreach (var kv in spikeMarkers.OrderByDescending(k => k.Value).Take(20)) o.AppendLine($"    {kv.Value,8:0.0} ms  {kv.Key}");
            }
            o.AppendLine();
            o.AppendLine("== render thread self time (ms/frame)");
            foreach (var kv in rtSelf.OrderByDescending(k => k.Value).Take(30)) o.AppendLine($"{kv.Value / Math.Max(1, frames),8:0.000}  {kv.Key}");
            o.AppendLine($"== render thread in frames over 33 ms ({rtSpikeFrames.Count})");
            foreach (var x in rtSpikeFrames.Take(40)) o.AppendLine(x);
            foreach (var kv in rtSpike.OrderByDescending(k => k.Value).Take(20)) o.AppendLine($"    {kv.Value,8:0.0} ms  {kv.Key}");
            return o.ToString();
        }

        static void RenderThread(int frame, double frameMs, Dictionary<string, double> self, Dictionary<string, double> spike, List<string> spikeFrames)
        {
            for (var t = 1; t < 64; t++)
            {
                using var v = ProfilerDriver.GetRawFrameDataView(frame, t);
                if (v == null || !v.valid) return;
                if (v.threadName != "Render Thread") continue;
                var frameSelf = new Dictionary<string, double>();
                var stack = new List<(int idx, int remaining, double childMs)>();
                for (var i = 0; i < v.sampleCount; i++)
                {
                    var ms = v.GetSampleTimeMs(i);
                    if (stack.Count > 0) { var top = stack[^1]; top.remaining--; top.childMs += ms; stack[^1] = top; }
                    var children = v.GetSampleChildrenCount(i);
                    if (children > 0) stack.Add((i, children, 0));
                    else Add(v.GetSampleName(i), ms);
                    while (stack.Count > 0 && stack[^1].remaining == 0)
                    {
                        var d = stack[^1]; stack.RemoveAt(stack.Count - 1);
                        Add(v.GetSampleName(d.idx), Math.Max(0, v.GetSampleTimeMs(d.idx) - d.childMs));
                    }
                }
                foreach (var kv in frameSelf) self[kv.Key] = (self.TryGetValue(kv.Key, out var x) ? x : 0) + kv.Value;
                if (frameMs > 33.4)
                {
                    spikeFrames.Add($"  frame {frame}: {frameMs:0.0} ms  ← " + string.Join(", ", frameSelf.OrderByDescending(kv => kv.Value).Take(6).Select(kv => $"{kv.Key} {kv.Value:0.0}")));
                    foreach (var kv in frameSelf) spike[kv.Key] = (spike.TryGetValue(kv.Key, out var x) ? x : 0) + kv.Value;
                }
                return;

                void Add(string name, double ms) => frameSelf[name] = (frameSelf.TryGetValue(name, out var x) ? x : 0) + ms;
            }
        }
    }
}
