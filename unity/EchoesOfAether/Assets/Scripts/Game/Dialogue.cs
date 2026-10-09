using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using UnityEngine;

namespace EOA
{
    public sealed class ResolvedLine
    {
        public string Dialogue, Node, Text;
        public SpeakerDef Speaker;
    }

    public enum LineMode { Interactive, Auto }

    /// <summary>Presentation of dialogue (implemented by the UI).</summary>
    public interface IDialogueView
    {
        /// <summary>Show a line; completes when it should advance (input or auto timing).</summary>
        Task Line(ResolvedLine line, LineMode mode);
        /// <summary>Offer choices; completes with the chosen choice id.</summary>
        Task<string> Choose(ResolvedLine line, IReadOnlyList<DialogueChoice> choices);
        void End();
    }

    /// <summary>Data-driven dialogue runner: branches, conditions, choices and actions.</summary>
    public sealed class DialogueSystem
    {
        readonly Func<GameState> gs;
        readonly Func<IDialogueView> view;
        readonly Func<IReadOnlyList<ActionDef>, Task> runActions;
        bool cancelled;
        public string ActiveId { get; private set; }

        public DialogueSystem(Func<GameState> gs, Func<IDialogueView> view, Func<IReadOnlyList<ActionDef>, Task> runActions)
        {
            this.gs = gs; this.view = view; this.runActions = runActions;
        }

        public SpeakerDef ResolveSpeaker(string id)
        {
            var d = gs().D;
            var real = id == "active" ? d.Character : id == "partner" ? Characters.Partner(d.Character) : id;
            return GameData.Speakers.TryGetValue(real, out var s) ? s : GameData.Speakers["system"];
        }

        public string Text(string t)
        {
            var c = gs().D.Character;
            return t.Replace("{partner}", Characters.FirstName(Characters.Partner(c))).Replace("{active}", Characters.FirstName(c));
        }

        DialogueNode Enter(DialogueDef def, string nodeId)
        {
            var guard = 0;
            while (nodeId != null && guard++ < 50)
            {
                var node = def.Node(nodeId);
                if (node == null) { Debug.LogError($"[dialogue] missing node {def.Id}/{nodeId}"); return null; }
                if (node.Branch != null)
                {
                    nodeId = node.Branch.FirstOrDefault(b => gs().CheckAll(b.If))?.Goto;
                    continue;
                }
                if (node.Conditions != null && !gs().CheckAll(node.Conditions)) { nodeId = node.Else; continue; }
                return node;
            }
            return null;
        }

        ResolvedLine Resolve(string dlg, DialogueNode n) =>
            n.Text != null && n.Speaker != null ? new ResolvedLine { Dialogue = dlg, Node = n.Id, Speaker = ResolveSpeaker(n.Speaker), Text = Text(n.Text) } : null;

        /// <summary>Lines of a dialogue (resolving branches/conditions) without presenting them.</summary>
        public List<ResolvedLine> LinearLines(string id)
        {
            var res = new List<ResolvedLine>();
            if (!GameData.Dialogues.TryGetValue(id, out var def)) return res;
            var node = Enter(def, def.Start);
            var guard = 0;
            while (node != null && guard++ < 200)
            {
                var l = Resolve(id, node);
                if (l != null) res.Add(l);
                node = node.Next != null ? Enter(def, node.Next) : null;
            }
            return res;
        }

        public void Cancel() => cancelled = true;

        public async Task Play(string id, LineMode mode = LineMode.Interactive)
        {
            if (!GameData.Dialogues.TryGetValue(id, out var def)) { Debug.LogError($"[dialogue] unknown dialogue {id}"); return; }
            if (ActiveId != null) Debug.LogWarning($"[dialogue] {id} requested while {ActiveId} active");
            ActiveId = id;
            cancelled = false;
            Bus.Emit(new DialogueStarted { Id = id });
            try
            {
                var node = Enter(def, def.Start);
                var guard = 0;
                while (node != null && !cancelled && guard++ < 200)
                {
                    await runActions(node.Actions);
                    var line = Resolve(id, node);
                    var choices = (node.Choices ?? Array.Empty<DialogueChoice>()).Where(c => gs().CheckAll(c.Conditions)).ToList();
                    if (choices.Count > 0)
                    {
                        var shown = choices.Select(c => new DialogueChoice { Id = c.Id, Text = Text(c.Text), Next = c.Next, Conditions = c.Conditions, Actions = c.Actions }).ToList();
                        var picked = await view().Choose(line, shown);
                        var c = choices.FirstOrDefault(x => x.Id == picked) ?? choices[0];
                        Bus.Emit(new DialogueChoiceMade { Id = id, Node = node.Id, Choice = c.Id });
                        await runActions(c.Actions);
                        node = Enter(def, c.Next);
                    }
                    else
                    {
                        if (line != null) await view().Line(line, mode);
                        node = node.Next != null ? Enter(def, node.Next) : null;
                    }
                }
            }
            finally
            {
                view().End();
                ActiveId = null;
                Bus.Emit(new DialogueEnded { Id = id });
                if (def.Npc != null) Bus.Emit(new Talked { Npc = def.Npc });
            }
        }
    }
}
