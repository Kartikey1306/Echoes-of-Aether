using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;
using UnityEngine.Experimental.Rendering;
using UnityEngine.Rendering;

namespace EOA.EditorTools
{
    /// <summary>
    /// Builds the shader warm-up data used by <see cref="ShaderWarmup"/> from player traces (benchmark runs with
    /// -benchTraceGsc file.graphicsstate; see tools/perf). Copies the trace to Resources/Perf/EOA_Warmup_&lt;API&gt;
    /// (PSO warm-up on Metal) and derives a ShaderVariantCollection Resources/Perf/EOA_Warmup.shadervariants
    /// (variant warm-up on WebGL). Batch:
    ///   Unity -batchmode -quit -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.ShaderWarmupBuilder.Build
    ///     -gsc trace.graphicsstate [-gsc more.graphicsstate]
    /// </summary>
    public static class ShaderWarmupBuilder
    {
        const string Dir = "Assets/Resources/Perf";

        public static void Build()
        {
            var args = Environment.GetCommandLineArgs();
            var traces = new List<string>();
            for (var i = 0; i < args.Length - 1; i++) if (args[i] == "-gsc") traces.Add(args[i + 1]);
            try { Build(traces); }
            catch (Exception e) { Debug.LogError("[warmup] " + e); if (Application.isBatchMode) EditorApplication.Exit(1); }
        }

        public static void Build(List<string> traces)
        {
            if (traces.Count == 0) throw new ArgumentException("no -gsc trace given");
            Directory.CreateDirectory(Dir);
            var svc = new ShaderVariantCollection();
            int added = 0, skipped = 0;
            foreach (var t in traces)
            {
                var probe = new GraphicsStateCollection();
                if (!probe.LoadFromFile(t)) throw new Exception("cannot load trace " + t);
                var api = probe.graphicsDeviceType;
                var dst = $"{Dir}/EOA_Warmup_{api}.graphicsstate";
                File.Copy(t, dst, true);
                AssetDatabase.ImportAsset(dst, ImportAssetOptions.ForceUpdate);
                var asset = AssetDatabase.LoadAssetAtPath<GraphicsStateCollection>(dst);
                Debug.Log($"[warmup] {t}: {probe.variantCount} variants, {probe.totalGraphicsStateCount} states, {api}/{probe.runtimePlatform} → {dst} (asset {(asset != null ? "ok" : "NOT IMPORTED")})");
                var variants = new List<GraphicsStateCollection.ShaderVariant>();
                probe.GetVariants(variants);
                foreach (var v in variants)
                {
                    if (v.shader == null) { skipped++; continue; }
                    var passType = PassTypeOf(v.shader, v.passId);
                    var kw = v.keywords?.Where(k => !string.IsNullOrEmpty(k.name)).Select(k => k.name).ToArray() ?? Array.Empty<string>();
                    try
                    {
                        if (svc.Add(new ShaderVariantCollection.ShaderVariant(v.shader, passType, kw))) added++;
                    }
                    catch (Exception) { skipped++; }
                }
            }
            var svcPath = $"{Dir}/EOA_Warmup.shadervariants";
            var old = AssetDatabase.LoadAssetAtPath<ShaderVariantCollection>(svcPath);
            if (old != null) { EditorUtility.CopySerialized(svc, old); EditorUtility.SetDirty(old); }
            else AssetDatabase.CreateAsset(svc, svcPath);
            AssetDatabase.SaveAssets();
            Debug.Log($"[warmup] ShaderVariantCollection {svcPath}: {added} variants ({skipped} skipped), {svc.shaderCount} shaders");
        }

        static PassType PassTypeOf(Shader shader, PassIdentifier id)
        {
            try
            {
                var data = ShaderUtil.GetShaderData(shader);
                var sub = data.GetSerializedSubshader((int)id.SubshaderIndex);
                var pass = sub.GetPass((int)id.PassIndex);
                var mode = pass.FindTagValue(new ShaderTagId("LightMode")).name;
                return mode switch
                {
                    "ShadowCaster" => PassType.ShadowCaster,
                    "" or null or "SRPDefaultUnlit" => PassType.ScriptableRenderPipelineDefaultUnlit,
                    "Meta" => PassType.Meta,
                    _ => PassType.ScriptableRenderPipeline,
                };
            }
            catch { return PassType.ScriptableRenderPipeline; }
        }
    }
}
