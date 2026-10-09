using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEngine;

namespace EOA.EditorTools
{
    /// <summary>
    /// Release builds. Menu: EOA/Build/WebGL, EOA/Build/macOS. Batch:
    ///   Unity -batchmode -quit -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.BuildScripts.WebGL
    ///   Unity -batchmode -quit -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.BuildScripts.MacOS
    /// Output: &lt;repo&gt;/Builds/WebGL and &lt;repo&gt;/Builds/macOS/EchoesOfAether.app. Runs the project setup first if needed.
    /// </summary>
    public static class BuildScripts
    {
        static string RepoRoot => Path.GetFullPath(Path.Combine(Application.dataPath, "..", "..", ".."));

        /// <summary>
        /// WebGL: textures are clamped to 1024 px for this build (the customization library and HD environment sets are
        /// authored at 2-4K for desktop; a browser download and WebGL memory cannot carry them). Restored afterwards.
        /// </summary>
        [MenuItem("EOA/Build/WebGL")]
        public static void WebGL()
        {
            // 1024 here can only be a leftover of an interrupted WebGL build: restore to "no override" then.
            var prevMax = EditorUserBuildSettings.overrideMaxTextureSize is WebGLTextureCap or 1024 ? 0 : EditorUserBuildSettings.overrideMaxTextureSize;
            // A previous interrupted WebGL build may have left excluded folders hidden: put them back first.
            foreach (var dir in WebGLExcluded)
            {
                var full = Path.GetFullPath(dir);
                if (Directory.Exists(full + "~") && !Directory.Exists(full)) { Directory.Move(full + "~", full); if (File.Exists(full + ".meta~")) File.Move(full + ".meta~", full + ".meta"); }
            }
            var prevTarget = EditorUserBuildSettings.activeBuildTarget;
            if (prevTarget == BuildTarget.WebGL) prevTarget = BuildTarget.StandaloneOSX; // likewise an interrupted build
            var prevGroup = BuildPipeline.GetBuildTargetGroup(prevTarget);
            var hidden = new List<(string from, string to)>();
            try
            {
                EditorUserBuildSettings.overrideMaxTextureSize = WebGLTextureCap;
                // Browser download budget: leave the heaviest optional content out of the WebGL player. Folders renamed
                // with a trailing "~" are ignored by Unity; the designer hides catalog items whose files are missing.
                foreach (var dir in WebGLExcluded)
                {
                    var full = Path.GetFullPath(dir);
                    if (!Directory.Exists(full)) continue;
                    Directory.Move(full, full + "~");
                    if (File.Exists(full + ".meta")) File.Move(full + ".meta", full + ".meta~");
                    hidden.Add((full, full + "~"));
                }
                if (hidden.Count > 0) AssetDatabase.Refresh();
                Build(BuildTarget.WebGL, NamedBuildTarget.WebGL, Path.Combine(RepoRoot, "Builds", "WebGL"));
            }
            finally
            {
                foreach (var (from, to) in hidden)
                {
                    if (Directory.Exists(to) && !Directory.Exists(from)) Directory.Move(to, from);
                    if (File.Exists(from + ".meta~")) File.Move(from + ".meta~", from + ".meta");
                }
                if (hidden.Count > 0) AssetDatabase.Refresh();
                EditorUserBuildSettings.overrideMaxTextureSize = prevMax;
                // Shared project: leave the editor on the platform it was on (the next session would otherwise open on
                // WebGL, define UNITY_WEBGL for play mode and reimport everything).
                if (EditorUserBuildSettings.activeBuildTarget != prevTarget) EditorUserBuildSettings.SwitchActiveBuildTarget(prevGroup, prevTarget);
            }
            ExitIfFailed();
        }

        [MenuItem("EOA/Build/macOS")]
        public static void MacOS() { Build(BuildTarget.StandaloneOSX, NamedBuildTarget.Standalone, Path.Combine(RepoRoot, "Builds", "macOS", "EchoesOfAether.app")); ExitIfFailed(); }

        /// <summary>
        /// Windows 10/11 x64 player (Mono, so it cross-builds from macOS): &lt;repo&gt;/Builds/Windows/EchoesOfAether.exe.
        /// Direct3D 11 first for the widest GPU support (feature level 10+ incl. Intel integrated), then D3D12 and Vulkan.
        /// Windows on ARM runs it through x64 emulation. The editor is switched back to macOS afterwards.
        /// </summary>
        [MenuItem("EOA/Build/Windows (x64)")]
        public static void Windows()
        {
            var prevTarget = EditorUserBuildSettings.activeBuildTarget;
            try
            {
                PlayerSettings.SetUseDefaultGraphicsAPIs(BuildTarget.StandaloneWindows64, false);
                PlayerSettings.SetGraphicsAPIs(BuildTarget.StandaloneWindows64,
                    new[] { UnityEngine.Rendering.GraphicsDeviceType.Direct3D11, UnityEngine.Rendering.GraphicsDeviceType.Direct3D12, UnityEngine.Rendering.GraphicsDeviceType.Vulkan });
                PlayerSettings.SetScriptingBackend(NamedBuildTarget.Standalone, ScriptingImplementation.Mono2x);
                PlayerSettings.fullScreenMode = FullScreenMode.FullScreenWindow;
                PlayerSettings.allowFullscreenSwitch = true;   // Alt+Enter
                PlayerSettings.resizableWindow = true;
                PlayerSettings.visibleInBackground = false;
                PlayerSettings.forceSingleInstance = true;
                Build(BuildTarget.StandaloneWindows64, NamedBuildTarget.Standalone, Path.Combine(RepoRoot, "Builds", "Windows", "EchoesOfAether.exe"));
            }
            finally
            {
                if (EditorUserBuildSettings.activeBuildTarget != prevTarget && prevTarget == BuildTarget.StandaloneOSX)
                    EditorUserBuildSettings.SwitchActiveBuildTarget(BuildTargetGroup.Standalone, BuildTarget.StandaloneOSX);
            }
            ExitIfFailed();
        }

        /// <summary>
        /// Development macOS player for profiling and the benchmark (-benchmark out.json, see EOA.Benchmark):
        /// &lt;repo&gt;/Builds/macOS_dev/EchoesOfAether.app. Frame timing stats on (GPU times), profiler markers available.
        /// </summary>
        [MenuItem("EOA/Build/macOS (development, benchmark)")]
        public static void MacOSDev() { Build(BuildTarget.StandaloneOSX, NamedBuildTarget.Standalone, Path.Combine(RepoRoot, "Builds", "macOS_dev", "EchoesOfAether.app"), development: true); ExitIfFailed(); }

        const int WebGLTextureCap = 512;

        /// <summary>Optional content the WebGL player ships without (desktop builds keep everything).</summary>
        static readonly string[] WebGLExcluded = { "Assets/Resources/Characters/Custom/Armour" };

        /// <summary>Put the editor back on macOS with no import overrides (after an interrupted WebGL build). Batch-safe.</summary>
        [MenuItem("EOA/Build/Restore Editor Platform (macOS, no overrides)")]
        public static void RestoreEditorPlatform()
        {
            EditorUserBuildSettings.overrideMaxTextureSize = 0;
            EditorUserBuildSettings.overrideTextureCompression = OverrideTextureCompression.NoOverride;
            Debug.Log($"[build] editor platform was {EditorUserBuildSettings.activeBuildTarget}");
            if (EditorUserBuildSettings.activeBuildTarget != BuildTarget.StandaloneOSX)
                EditorUserBuildSettings.SwitchActiveBuildTarget(BuildTargetGroup.Standalone, BuildTarget.StandaloneOSX);
        }

        static void Build(BuildTarget target, NamedBuildTarget named, string output, bool development = false)
        {
            // Desktop players never ship with the WebGL texture cap (left behind if a WebGL build was interrupted).
            if (target != BuildTarget.WebGL && EditorUserBuildSettings.overrideMaxTextureSize != 0)
            {
                Debug.LogWarning($"[build] clearing texture size override {EditorUserBuildSettings.overrideMaxTextureSize} for {target}");
                EditorUserBuildSettings.overrideMaxTextureSize = 0;
            }
            if (!File.Exists("ProjectSettings/EOA_Setup.txt")) ProjectSetup.RunAll();
            if (!File.Exists(ProjectSetup.BootScene)) { Fail("Boot scene missing; run EOA/Setup Project (All)"); return; }
            // Release: no development player, no debug overlay automation hooks.
            if (!development) PlayerSettings.SetScriptingDefineSymbols(named, PlayerSettings.GetScriptingDefineSymbols(named).Replace("EOA_DEV", "").Trim(';'));
            // GPU frame times for the benchmark / debug overlay / dynamic resolution (negligible cost).
            PlayerSettings.enableFrameTimingStats = true;
            var opts = new BuildPlayerOptions
            {
                scenes = EditorBuildSettings.scenes.Where(s => s.enabled).Select(s => s.path).DefaultIfEmpty(ProjectSetup.BootScene).ToArray(),
                locationPathName = output,
                target = target,
                targetGroup = BuildPipeline.GetBuildTargetGroup(target),
                options = development ? BuildOptions.Development : BuildOptions.None,
            };
            Directory.CreateDirectory(Path.GetDirectoryName(output) ?? output);
            Debug.Log($"[build] {target} → {output}");
            var report = BuildPipeline.BuildPlayer(opts);
            var s = report.summary;
            Debug.Log($"[build] {target}: {s.result}, {s.totalErrors} errors, {s.totalWarnings} warnings, {s.totalSize / (1024f * 1024f):0.0} MB, {s.totalTime}");
            try
            {
                // Largest packed assets (helps keep the WebGL download reasonable).
                var biggest = report.packedAssets.SelectMany(p => p.contents).GroupBy(c => c.sourceAssetPath)
                    .Select(g => (path: g.Key, bytes: g.Sum(c => (long)c.packedSize))).OrderByDescending(x => x.bytes).Take(40);
                foreach (var b in biggest) Debug.Log($"[build] asset {b.bytes / 1024f:0} KB  {b.path}");
            }
            catch (Exception e) { Debug.LogWarning("[build] asset size report failed: " + e.Message); }
            if (s.result != BuildResult.Succeeded) Fail($"{target} build {s.result}");
        }

        static bool failed;

        static void Fail(string message)
        {
            Debug.LogError("[build] " + message);
            failed = true;
        }

        /// <summary>Batch builds report failure through the exit code (after any clean-up has run).</summary>
        static void ExitIfFailed()
        {
            if (failed && Application.isBatchMode) EditorApplication.Exit(1);
            failed = false;
        }
    }
}
