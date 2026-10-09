using System;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace EOA.EditorTools
{
    /// <summary>
    /// Automated play-mode smoke test: opens the Boot scene, enters Play mode and runs <see cref="AutoPilot"/>
    /// (menu → character select → new game/intro → every zone → combat), writing screenshots and report.json to
    /// &lt;repo&gt;/Captures/smoke. Menu: EOA/Test/Smoke Test. Batch (exit code 1 on runtime errors):
    ///   Unity -batchmode -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.SmokeTest.Run
    /// </summary>
    public static class SmokeTest
    {
        const string Key = "EOA_SMOKE_ACTIVE";
        static string OutDir => Path.GetFullPath(Path.Combine(Application.dataPath, "..", "..", "..", "Captures",
            SessionState.GetString(Key + "_mode", "full") == "weapons" ? "weapons" : "smoke"));

        /// <summary>Plaza drone fight only (fast repro of combat issues).</summary>
        [MenuItem("EOA/Test/Smoke Test (combat only)")]
        public static void RunCombat()
        {
            SessionState.SetString(Key + "_mode", "combat");
            Start();
        }

        /// <summary>Full main story M1→M5, ending and credits (automated).</summary>
        [MenuItem("EOA/Test/Story Play-through (M1-M5 + credits)")]
        public static void RunStory()
        {
            SessionState.SetString(Key + "_mode", "story");
            Start();
        }

        /// <summary>Hero close-ups in the designer (body, face, back) for both leads: fast character art check.</summary>
        [MenuItem("EOA/Test/Hero Close-ups")]
        public static void RunHeroes()
        {
            SessionState.SetString(Key + "_mode", "heroes");
            Start();
        }

        /// <summary>Player hero standing / walking / running / sprinting in the plaza, side and front views.</summary>
        [MenuItem("EOA/Test/Gameplay Posture")]
        public static void RunPosture()
        {
            SessionState.SetString(Key + "_mode", "posture");
            Start();
        }

        /// <summary>Open-city driving: get in, route, drift, wall hit, safe exit, flip recovery (screenshots + telemetry).</summary>
        [MenuItem("EOA/Test/Driving")]
        public static void RunDriving()
        {
            SessionState.SetString(Key + "_mode", "driving");
            Start();
        }

        /// <summary>Weapon close-ups (both heroes' melee + ranged weapons in action, enemy weapons) → Captures/weapons.</summary>
        [MenuItem("EOA/Test/Weapon Close-ups")]
        public static void RunWeapons()
        {
            SessionState.SetString(Key + "_mode", "weapons");
            Start();
        }

        [MenuItem("EOA/Test/Smoke Test (play-through + screenshots)")]
        public static void Run()
        {
            SessionState.SetString(Key + "_mode", "full");
            Start();
        }

        static void Start()
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
                if (SessionState.GetBool(Key, false)) Debug.Log("[smoke] play mode state: " + s);
                if (s == PlayModeStateChange.EnteredPlayMode && SessionState.GetBool(Key, false)) AutoPilot.Begin(OutDir, SessionState.GetString(Key + "_mode", "full"));
            };
            EditorApplication.update += Poll;
        }

        static void Poll()
        {
            if (!SessionState.GetBool(Key, false)) return;
            var started = DateTime.TryParse(SessionState.GetString(Key + "_started", ""), null, System.Globalization.DateTimeStyles.RoundtripKind, out var t) ? t : DateTime.UtcNow;
            var timedOut = (DateTime.UtcNow - started).TotalMinutes > 25;
            if (!EditorApplication.isPlaying || (!AutoPilot.Done && !timedOut)) return;
            SessionState.SetBool(Key, false);
            var failed = AutoPilot.Failed || timedOut;
            Debug.Log($"[smoke] finished: {(failed ? "FAILED" : "OK")}{(timedOut ? " (timeout)" : "")} → {OutDir}");
            EditorApplication.ExitPlaymode();
            if (Application.isBatchMode) EditorApplication.delayCall += () => EditorApplication.Exit(failed ? 1 : 0);
        }
    }
}
