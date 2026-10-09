using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Safety net for slower PCs (release players only; never in the editor, batch tests or benchmarks). While the player
    /// is actually playing (no pause, dialogue, cinematic or designer), it averages the frame rate over 8-second windows
    /// after a 12-second settle. If a window averages under the target and the player hasn't picked graphics options
    /// themselves, it lowers the preset one step (Ultra → High → Medium → Low), tells the player, and measures again.
    /// Target: 40 fps (26 with the 30 FPS cap).
    /// </summary>
    public sealed class PerformanceGuard : MonoBehaviour
    {
        const float Settle = 12f, Window = 8f;
        float settle = Settle, acc;
        int frames;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Create()
        {
            if (Application.isEditor || Application.isBatchMode || Application.platform == RuntimePlatform.WebGLPlayer) return;
            var go = new GameObject("PerformanceGuard");
            DontDestroyOnLoad(go);
            go.AddComponent<PerformanceGuard>();
        }

        void Update()
        {
            var m = G.Manager;
            var s = G.Settings;
            var playing = m != null && s != null && m.Mode == GameMode.Play && !m.Paused && !m.InDialogue && !m.InCinematic
                && !m.DesignerActive && !Benchmark.Active;
            if (!playing || !s.Data.Graphics.AutoQuality) { settle = Settle; acc = 0; frames = 0; return; }
            var dt = Time.unscaledDeltaTime;
            if (settle > 0) { settle -= dt; return; }
            acc += dt; frames++;
            if (acc < Window) return;
            var fps = frames / acc;
            acc = 0; frames = 0;
            var target = s.Data.Graphics.FrameLimit == "30" ? 26f : 40f;
            if (fps >= target) return;
            var next = s.StepDownPreset();
            if (next == null) { enabled = false; return; }
            Debug.Log($"[perf] {fps:0} fps over {Window:0} s: graphics lowered to {next}");
            G.Presentation?.Toast($"Graphics set to {char.ToUpper(next[0]) + next.Substring(1)} for smoother play (change it in Settings > Graphics)", ToastKind.Info);
            settle = 6f;   // let the new settings take effect before measuring again
        }
    }
}
