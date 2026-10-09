using System;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace EOA.EditorTools
{
    /// <summary>
    /// Sky &amp; weather capture run (<see cref="FxShotPilot"/>) into &lt;repo&gt;/Captures/fx with report.json.
    /// Menu: EOA/Test/FX Shots. Batch (exit code 1 on runtime errors):
    ///   Unity -batchmode -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.FxShots.Run
    /// </summary>
    public static class FxShots
    {
        const string Key = "EOA_FX_SHOTS";
        static string OutDir => Path.GetFullPath(Path.Combine(Application.dataPath, "..", "..", "..", "Captures", "fx"));

        [MenuItem("EOA/Test/FX Shots (sky + rain)")]
        public static void Run()
        {
            FxSetup.Run();
            if (!File.Exists(ProjectSetup.BootScene)) ProjectSetup.RunAll();
            EditorSceneManager.OpenScene(ProjectSetup.BootScene);
            if (Directory.Exists(OutDir)) foreach (var f in Directory.GetFiles(OutDir)) File.Delete(f);
            SessionState.SetBool(Key, true);
            SessionState.SetString(Key + "_started", DateTime.UtcNow.ToString("o"));
            EditorApplication.EnterPlaymode();
        }

        [InitializeOnLoadMethod]
        static void Hook()
        {
            EditorApplication.playModeStateChanged += s =>
            {
                if (s == PlayModeStateChange.EnteredPlayMode && SessionState.GetBool(Key, false)) FxShotPilot.Begin(OutDir);
            };
            EditorApplication.update += Poll;
        }

        static void Poll()
        {
            if (!SessionState.GetBool(Key, false)) return;
            var started = DateTime.TryParse(SessionState.GetString(Key + "_started", ""), null, System.Globalization.DateTimeStyles.RoundtripKind, out var t) ? t : DateTime.UtcNow;
            var timedOut = (DateTime.UtcNow - started).TotalMinutes > 12;
            if (!EditorApplication.isPlaying || (!FxShotPilot.Done && !timedOut)) return;
            SessionState.SetBool(Key, false);
            var failed = FxShotPilot.Failed || timedOut;
            Debug.Log($"[fx] shots finished: {(failed ? "FAILED" : "OK")}{(timedOut ? " (timeout)" : "")} → {OutDir}");
            EditorApplication.ExitPlaymode();
            if (Application.isBatchMode) EditorApplication.delayCall += () => EditorApplication.Exit(failed ? 1 : 0);
        }
    }
}
