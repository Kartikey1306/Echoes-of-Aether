using System;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace EOA.EditorTools
{
    /// <summary>
    /// Vehicle kit capture run (AutoPilot mode "vehicles": line-up close-ups, ground contact, LOD series, traffic /
    /// sky / parked shots) into &lt;repo&gt;/Captures/vehicles with report.json. Menu: EOA/Test/Vehicle Shots. Batch:
    ///   Unity -batchmode -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.VehicleShots.Run
    /// (exit code 1 on runtime errors or failed checks).
    /// </summary>
    public static class VehicleShots
    {
        const string Key = "EOA_VEHICLE_SHOTS";
        static string OutDir => Path.GetFullPath(Path.Combine(Application.dataPath, "..", "..", "..", "Captures", "vehicles"));

        [MenuItem("EOA/Test/Vehicle Shots")]
        public static void Run()
        {
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
                if (s == PlayModeStateChange.EnteredPlayMode && SessionState.GetBool(Key, false)) AutoPilot.Begin(OutDir, "vehicles");
            };
            EditorApplication.update += Poll;
        }

        static void Poll()
        {
            if (!SessionState.GetBool(Key, false)) return;
            var started = DateTime.TryParse(SessionState.GetString(Key + "_started", ""), null, System.Globalization.DateTimeStyles.RoundtripKind, out var t) ? t : DateTime.UtcNow;
            var timedOut = (DateTime.UtcNow - started).TotalMinutes > 15;
            if (!EditorApplication.isPlaying || (!AutoPilot.Done && !timedOut)) return;
            SessionState.SetBool(Key, false);
            var failed = AutoPilot.Failed || timedOut;
            Debug.Log($"[vehicles] finished: {(failed ? "FAILED" : "OK")}{(timedOut ? " (timeout)" : "")} → {OutDir}");
            EditorApplication.ExitPlaymode();
            if (Application.isBatchMode) EditorApplication.delayCall += () => EditorApplication.Exit(failed ? 1 : 0);
        }
    }
}
