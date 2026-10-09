using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using UnityEngine;

namespace EOA
{
    /// <summary>Runs data-driven actions (implemented by the GameManager).</summary>
    public interface IActionHost
    {
        Task RunActions(IReadOnlyList<ActionDef> actions, string quest = null);
        string CurrentZone { get; }
        string PartnerName { get; }
    }

    public readonly struct ObjectiveStatus
    {
        public readonly ObjectiveDef Def; public readonly bool Done; public readonly int Progress, Required;
        public ObjectiveStatus(ObjectiveDef def, int progress, int required) { Def = def; Progress = progress; Required = required; Done = progress >= required; }
    }

    /// <summary>
    /// Data-driven quest engine. Game events advance objectives; stage transitions and their actions run
    /// through a serial queue so dialogue and cinematics triggered by quests never overlap.
    /// </summary>
    public sealed class QuestSystem : IDisposable
    {
        readonly Func<GameState> gs;
        readonly IActionHost host;
        readonly List<Action> unsubs = new();
        Task queue = Task.CompletedTask;

        public QuestSystem(Func<GameState> gs, IActionHost host)
        {
            this.gs = gs; this.host = host;
            unsubs.Add(Bus.On<Interacted>(p => Signal("interact", p.Id)));
            unsubs.Add(Bus.On<PickedUp>(p => Signal("interact", p.Id)));
            unsubs.Add(Bus.On<EncounterCleared>(p => Signal("kill", p.Id)));
            unsubs.Add(Bus.On<ItemAdded>(p => Signal("collect", p.Id)));
            unsubs.Add(Bus.On<TriggerEnter>(p => Signal("reach", p.Id)));
            unsubs.Add(Bus.On<ZoneEntered>(p => Signal("zone", p.Zone)));
            unsubs.Add(Bus.On<FlagSet>(p => Signal("flag", p.Flag)));
            unsubs.Add(Bus.On<Talked>(p => Signal("talk", p.Npc)));
        }

        public void Dispose() { foreach (var u in unsubs) u(); unsubs.Clear(); }

        Task Enqueue(Func<Task> fn)
        {
            var prev = queue;
            queue = Run();
            return queue;
            async Task Run()
            {
                try { await prev; } catch { /* already logged */ }
                try { await fn(); }
                catch (Exception e) { Debug.LogError($"[quests] {e}"); }
            }
        }

        /// <summary>Completes once all queued quest work has finished.</summary>
        public Task Idle() => queue;

        public List<QuestDef> Active() => GameData.QuestList.Where(d => gs().D.Quests.TryGetValue(d.Id, out var q) && q.Status == "active").ToList();
        public List<QuestDef> Completed() => GameData.QuestList.Where(d => gs().D.Quests.TryGetValue(d.Id, out var q) && q.Status == "done").ToList();

        public QuestDef Tracked()
        {
            var d = gs().D;
            if (d.Tracked != null && d.Quests.TryGetValue(d.Tracked, out var t) && t.Status == "active") return GameData.Quests[d.Tracked];
            // First active main quest, else the first active quest (called every frame by the HUD: no LINQ).
            QuestDef first = null;
            foreach (var q in GameData.QuestList)
            {
                if (!d.Quests.TryGetValue(q.Id, out var st) || st.Status != "active") continue;
                if (q.IsMain) return q;
                first ??= q;
            }
            return first;
        }

        public void Track(string id)
        {
            if (gs().D.Quests.TryGetValue(id, out var q) && q.Status == "active") gs().D.Tracked = id;
        }

        static int Required(ObjectiveDef o) => o.Type == "collect" ? Mathf.Max(1, o.Count ?? 1) : 1;

        public List<ObjectiveStatus> CurrentObjectives(string id) => CurrentObjectives(id, new List<ObjectiveStatus>());

        /// <summary>Non-allocating form for per-frame callers: clears and fills <paramref name="res"/>.</summary>
        public List<ObjectiveStatus> CurrentObjectives(string id, List<ObjectiveStatus> res)
        {
            res.Clear();
            if (!gs().D.Quests.TryGetValue(id, out var st) || !GameData.Quests.TryGetValue(id, out var def) || st.Status != "active") return res;
            if (st.Stage >= def.Stages.Length) return res;
            foreach (var o in def.Stages[st.Stage].Objectives)
                res.Add(new ObjectiveStatus(o, st.Progress.TryGetValue(o.Id, out var p) ? p : 0, Required(o)));
            return res;
        }

        public string ObjectiveText(ObjectiveDef o) => o.Text.Replace("{partner}", host.PartnerName);

        public Task Start(string id) => Enqueue(async () =>
        {
            if (!GameData.Quests.TryGetValue(id, out var def)) { Debug.LogError($"[quests] unknown quest {id}"); return; }
            var d = gs().D;
            if (d.Quests.ContainsKey(id)) return;
            d.Quests[id] = new QuestState();
            if (def.IsMain || d.Tracked == null) d.Tracked = id;
            Bus.Emit(new QuestStarted { Id = id });
            Bus.Emit(new Toast { Text = $"{(def.IsMain ? "Mission" : "Side quest")}: {def.Title}", Kind = ToastKind.Quest });
            await EnterStage(id);
        });

        async Task EnterStage(string id)
        {
            var def = GameData.Quests[id];
            var st = gs().D.Quests[id];
            if (st.Stage >= def.Stages.Length) return;
            var stage = def.Stages[st.Stage];
            st.Progress = new Dictionary<string, int>();
            Bus.Emit(new QuestStage { Id = id, Stage = stage.Id });
            await host.RunActions(stage.OnStart, id);
            // Objectives already satisfied complete immediately.
            EvaluateInstant(id);
            await CheckStage(id);
        }

        void EvaluateInstant(string id)
        {
            var g = gs();
            var st = g.D.Quests[id];
            foreach (var o in CurrentObjectives(id))
            {
                if (o.Done) continue;
                var t = o.Def.Target;
                var v = o.Def.Type switch
                {
                    "collect" => g.D.Inventory.TryGetValue(t, out var n) ? n : 0,
                    "flag" => g.Flag(t) ? 1 : 0,
                    "zone" => host.CurrentZone == t ? 1 : 0,
                    "kill" => g.IsDefeated(t) ? 1 : 0,
                    "interact" => g.IsCollected(t) ? 1 : 0,
                    _ => 0,
                };
                if (v > 0) st.Progress[o.Def.Id] = Mathf.Min(o.Required, Mathf.Max(st.Progress.TryGetValue(o.Def.Id, out var p) ? p : 0, v));
            }
        }

        void Signal(string type, string target)
        {
            var g = gs();
            var touched = false;
            foreach (var q in Active())
            {
                var st = g.D.Quests[q.Id];
                foreach (var o in CurrentObjectives(q.Id))
                {
                    if (o.Done || o.Def.Type != type || o.Def.Target != target) continue;
                    // Collect progress is absolute (inventory count); the rest are one-shot.
                    var v = type == "collect" ? Mathf.Min(o.Required, g.D.Inventory.TryGetValue(target, out var n) ? n : 0) : o.Required;
                    if (v > (st.Progress.TryGetValue(o.Def.Id, out var p) ? p : 0))
                    {
                        st.Progress[o.Def.Id] = v;
                        Bus.Emit(new QuestObjective { Id = q.Id, Objective = o.Def.Id, Progress = v, Required = o.Required });
                        if (v >= o.Required) Bus.Emit(new Toast { Text = "✓ " + ObjectiveText(o.Def), Kind = ToastKind.Quest });
                        touched = true;
                    }
                }
            }
            if (touched) foreach (var q in Active()) { var qid = q.Id; Enqueue(() => CheckStage(qid)); }
        }

        async Task CheckStage(string id)
        {
            if (!gs().D.Quests.TryGetValue(id, out var st) || st.Status != "active") return;
            var objs = CurrentObjectives(id);
            if (objs.Count == 0 || !objs.All(o => o.Done)) return;
            var def = GameData.Quests[id];
            await host.RunActions(def.Stages[st.Stage].OnComplete, id);
            st.Stage++;
            if (st.Stage >= def.Stages.Length)
            {
                st.Status = "done";
                if (gs().D.Tracked == id) gs().D.Tracked = null;
                Bus.Emit(new QuestCompleted { Id = id });
                Bus.Emit(new Toast { Text = $"{(def.IsMain ? "Mission complete" : "Quest complete")}: {def.Title}", Kind = ToastKind.Quest });
                await host.RunActions(def.OnComplete, id);
                return;
            }
            await EnterStage(id);
        }

        /// <summary>Re-check all active quests (after load or zone change).</summary>
        public void Refresh()
        {
            foreach (var q in Active())
            {
                EvaluateInstant(q.Id);
                var qid = q.Id;
                Enqueue(() => CheckStage(qid));
            }
        }

        /// <summary>Debug/test: complete the current stage of a quest.</summary>
        public Task DebugCompleteStage(string id)
        {
            if (!gs().D.Quests.TryGetValue(id, out var st)) return Task.CompletedTask;
            foreach (var o in CurrentObjectives(id)) st.Progress[o.Def.Id] = o.Required;
            return Enqueue(() => CheckStage(id));
        }
    }
}
