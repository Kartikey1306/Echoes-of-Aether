using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.Profiling;
using UnityEngine.UIElements;

namespace EOA
{
    /// <summary>F1 debug overlay (development builds only): performance, scene, player, quest, enemies, audio, saves.</summary>
    public sealed class DebugOverlay
    {
        public readonly VisualElement Root;
        readonly Dictionary<string, Label> values = new();
        bool on;
        float t;
        float frameMs = 16.7f, fps = 60;

        static readonly string[] Rows = { "FPS", "Frame", "Memory", "Mode", "Zone", "Player", "Character", "Quest", "Enemies", "Audio", "Save" };

        public DebugOverlay()
        {
            Root = U.El("debug");
            Root.pickingMode = PickingMode.Ignore;
            foreach (var r in Rows)
            {
                var v = U.Label("-", "debug-v");
                values[r] = v;
                var row = U.El("debug-row", U.Label(r, "debug-k"), v);
                Root.Add(row);
            }
            Root.Query<VisualElement>().ForEach(e => e.pickingMode = PickingMode.Ignore);
            U.Show(Root, false);
        }

        public void Toggle()
        {
            on = !on && Debug.isDebugBuild;
            U.Show(Root, on);
            t = 0;
        }

        void Set(string k, string v)
        {
            if (values.TryGetValue(k, out var l) && l.text != v) l.text = v;
        }

        public void Tick(float dt)
        {
            if (dt > 0)
            {
                frameMs = Mathf.Lerp(frameMs, dt * 1000f, 0.1f);
                fps = Mathf.Lerp(fps, 1f / dt, 0.1f);
            }
            if (!on) return;
            t -= dt;
            if (t > 0) return;
            t = 0.25f;
            var gm = G.Manager;
            Set("FPS", (gm != null ? gm.Fps : fps).ToString("0"));
            Set("Frame", frameMs.ToString("0.0") + " ms");
            var total = Profiler.GetTotalAllocatedMemoryLong() / 1048576.0;
            var mono = GC.GetTotalMemory(false) / 1048576.0;
            Set("Memory", $"{total:0} MB total · {mono:0} MB managed");
            if (gm == null) return;
            Set("Mode", gm.Mode + (gm.Paused ? " (paused)" : "") + (gm.InCinematic ? " cine" : "") + (gm.InDialogue ? " dialogue" : "") + (gm.InCombat ? " combat" : ""));
            Set("Zone", G.World?.ZoneId ?? "-");
            var pp = Hud.PlayerPos(gm.PlayerStatus);
            Set("Player", pp.HasValue ? $"{pp.Value.x:0.0}, {pp.Value.y:0.0}, {pp.Value.z:0.0}" : "-");
            var p = gm.PlayerStatus;
            Set("Character", p != null ? $"{p.Character}  hp {p.Health:0}/{p.Stats.MaxHealth:0}  sh {p.Shield:0}  en {p.Energy:0}" : G.State?.D.Character ?? "-");
            var q = G.Quests?.Tracked();
            string stage = "-";
            if (q != null && G.State != null && G.State.D.Quests.TryGetValue(q.Id, out var qs) && qs.Stage < q.Stages.Length) stage = q.Stages[qs.Stage].Id;
            Set("Quest", q != null ? $"{q.Id} / {stage}" : "-");
            var enemies = G.World?.Enemies;
            var alive = enemies?.Count(e => e != null && e.Alive) ?? 0;
            var aggro = enemies?.Count(e => e is IEnemyHealth h && e.Alive && h.Aggro) ?? 0;
            Set("Enemies", $"{alive} alive  {aggro} aggro");
            var au = G.Audio as IAudioDebugInfo;
            Set("Audio", au != null ? $"music {au.Mood}  amb {au.Ambience}" : G.Audio != null ? "on" : "none");
            var sv = G.Saves;
            Set("Save", sv != null ? $"slot {sv.ActiveSlot}  {(sv.LastSaveTime > 0 ? (Time.realtimeSinceStartup - sv.LastSaveTime).ToString("0") + "s ago" : "never")}" : "-");
        }
    }
}
