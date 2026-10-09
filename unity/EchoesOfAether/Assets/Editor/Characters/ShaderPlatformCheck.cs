using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEditor.Rendering;
using UnityEngine;
using UnityEngine.Rendering;

namespace EOA.EditorTools
{
    /// <summary>
    /// Compiles the shared character shaders (EOA/Skin, EOA/Hair, EOA/Eye, EOA/EyeOcclusion, EOA/EyeWet) for the
    /// shipping graphics APIs (D3D11 for the Windows build, Vulkan, Metal) over a representative set of keyword
    /// combinations (High: Forward+, soft cascaded shadows, SSAO, light layers; Low: forward, per-vertex additional
    /// lights, hard shadows) without building a player. Errors go to the log as "[shadercheck]" lines and to
    /// Captures/shadercheck.txt.
    ///   Unity -batchmode -quit -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.ShaderPlatformCheck.Run
    /// </summary>
    public static class ShaderPlatformCheck
    {
        static readonly string[] Shaders = { "EOA/Skin", "EOA/Hair", "EOA/Eye", "EOA/EyeOcclusion", "EOA/EyeWet" };

        static readonly string[][] Sets =
        {
            new string[0],
            // High / Ultra (Forward+)
            new[] { "_MAIN_LIGHT_SHADOWS_CASCADE", "_ADDITIONAL_LIGHTS", "_CLUSTER_LIGHT_LOOP", "_ADDITIONAL_LIGHT_SHADOWS", "_SHADOWS_SOFT_HIGH",
                    "_SCREEN_SPACE_OCCLUSION", "_LIGHT_LAYERS", "_LIGHT_COOKIES", "_REFLECTION_PROBE_BLENDING", "_REFLECTION_PROBE_BOX_PROJECTION",
                    "_NORMALMAP", "_METALLICSPECGLOSSMAP", "_OCCLUSIONMAP", "_EMISSION", "_DETAIL_MULX2", "_STRAND_DATA", "_ALPHATEST_ON" },
            // Medium
            new[] { "_MAIN_LIGHT_SHADOWS_CASCADE", "_ADDITIONAL_LIGHTS", "_SHADOWS_SOFT", "_NORMALMAP", "_METALLICSPECGLOSSMAP", "_EMISSION" },
            // Low (forward, vertex additional lights, hard shadows)
            new[] { "_MAIN_LIGHT_SHADOWS", "_ADDITIONAL_LIGHTS_VERTEX", "_NORMALMAP", "_METALLICSPECGLOSSMAP", "_DETAIL_MULX2" },
            // screen-space shadows / reflection atlas / DBuffer / LOD crossfade / mixed SH
            new[] { "_MAIN_LIGHT_SHADOWS_SCREEN", "_REFLECTION_PROBE_ATLAS", "_DBUFFER_MRT3", "LOD_FADE_CROSSFADE", "EVALUATE_SH_MIXED", "_NORMALMAP",
                    "_STRAND_DATA", "_GBUFFER_NORMALS_OCT", "_CASTING_PUNCTUAL_LIGHT_SHADOW" },
        };

        static readonly (ShaderCompilerPlatform platform, BuildTarget target)[] Targets =
        {
            (ShaderCompilerPlatform.D3D, BuildTarget.StandaloneWindows64),
            (ShaderCompilerPlatform.Vulkan, BuildTarget.StandaloneWindows64),
            (ShaderCompilerPlatform.Metal, BuildTarget.StandaloneOSX),
        };

        public static void Run()
        {
            var report = new StringBuilder();
            int compiled = 0, errors = 0, warnings = 0; long bytes = 0; int empty = 0;
            foreach (var name in Shaders)
            {
                var shader = Shader.Find(name);
                if (shader == null)
                {
                    errors++;
                    Line(report, $"{name}: NOT FOUND");
                    continue;
                }
                foreach (var msg in ShaderUtil.GetShaderMessages(shader))
                    if (msg.severity == ShaderCompilerMessageSeverity.Error)
                    {
                        errors++;
                        Line(report, $"{name} (import): {msg.message} {msg.file}:{msg.line} [{msg.platform}]");
                    }
                var data = ShaderUtil.GetShaderData(shader);
                for (var si = 0; si < data.SubshaderCount; si++)
                {
                    var sub = data.GetSubshader(si);
                    for (var pi = 0; pi < sub.PassCount; pi++)
                    {
                        var pass = sub.GetPass(pi);
                        foreach (var (platform, target) in Targets)
                        foreach (var set in Sets)
                        foreach (var stage in new[] { ShaderType.Vertex, ShaderType.Fragment })
                        {
                            ShaderData.VariantCompileInfo info;
                            try
                            {
                                info = pass.CompileVariant(stage, set, platform, target);
                            }
                            catch (Exception e)
                            {
                                errors++;
                                Line(report, $"{name}/{pass.Name} {platform} {stage}: exception {e.Message}");
                                continue;
                            }
                            compiled++;
                            var n = info.ShaderData?.Length ?? 0;
                            bytes += n;
                            if (info.Success && n == 0) empty++;
                            var msgs = info.Messages ?? new ShaderMessage[0];
                            foreach (var m in msgs)
                            {
                                if (m.severity == ShaderCompilerMessageSeverity.Error)
                                {
                                    errors++;
                                    Line(report, $"{name}/{pass.Name} {platform} {stage} [{string.Join(" ", set)}]: ERROR {m.message} {m.messageDetails} {Path.GetFileName(m.file)}:{m.line}");
                                }
                                else warnings++;
                            }
                            if (!info.Success && !msgs.Any(m => m.severity == ShaderCompilerMessageSeverity.Error))
                            {
                                errors++;
                                Line(report, $"{name}/{pass.Name} {platform} {stage} [{string.Join(" ", set)}]: failed without a message");
                            }
                        }
                    }
                }
            }
            var summary = $"[shadercheck] done: {compiled} variant compiles ({bytes / 1024} KB bytecode, {empty} empty), {errors} errors, {warnings} warnings";
            report.AppendLine(summary);
            Debug.Log(summary);
            var outDir = Path.GetFullPath(Path.Combine(Application.dataPath, "..", "..", "..", "Captures"));
            Directory.CreateDirectory(outDir);
            File.WriteAllText(Path.Combine(outDir, "shadercheck.txt"), report.ToString());
            if (Application.isBatchMode) EditorApplication.Exit(errors == 0 ? 0 : 1);
        }

        static void Line(StringBuilder sb, string s)
        {
            sb.AppendLine(s);
            Debug.Log("[shadercheck] " + s);
        }
    }
}
