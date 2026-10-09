using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;
using Newtonsoft.Json.Linq;

namespace EOA
{
    public static class Characters
    {
        public const string Kael = "kael", Lyra = "lyra";
        public static string Partner(string c) => c == Kael ? Lyra : Kael;
        // The female lead is named Giva in game; her asset/data id stays "lyra" (files Characters/Lyra…).
        public static string DisplayName(string c) => c == Kael ? "Kael Voss" : "Giva Vale";
        public static string FirstName(string c) => c == Kael ? "Kael" : "Giva";
        /// <summary>Resources/Characters prefab name.</summary>
        public static string AssetName(string c) => c == Kael ? "Kael" : "Lyra";
    }

    public sealed class QuestState
    {
        public string Status = "active"; // active | done
        public int Stage;
        public Dictionary<string, int> Progress = new();
    }

    public sealed class Checkpoint { public string Zone; public float[] Pos; public float Yaw; }

    public sealed class PlayStats { public float Playtime; public int Kills, Deaths; public float DamageDealt, DamageTaken; }

    /// <summary>The complete serializable progression state of one playthrough.</summary>
    public sealed class GameStateData
    {
        public int Schema = GameState.Schema;
        public string Character = Characters.Kael;
        public string StartCharacter = Characters.Kael;
        public string Zone = "plaza";
        public string Entry = "start";
        public float[] Position;
        public float Yaw;
        public Checkpoint Checkpoint;
        public Dictionary<string, QuestState> Quests = new();
        public string Tracked;
        public Dictionary<string, JToken> Flags = new();
        public Dictionary<string, int> Inventory = new();
        public List<string> Unlocked = new();
        public List<string> Skills = new();
        public List<string> Collected = new();
        public List<string> Defeated = new();
        public List<string> Revealed = new();
        public List<string> Lore = new();
        public PlayStats Stats = new();
        /// <summary>Player-customised appearance of the protagonists for this playthrough.</summary>
        public Dictionary<string, Appearance> Appearance = new();
    }

    public sealed class GameState
    {
        public const int Schema = 1;
        public readonly GameStateData D;

        public GameState(GameStateData d)
        {
            D = d;
            // Old saves stored lore by short id ('rec_01'); lore ids are dialogue ids.
            var legacy = new Dictionary<string, string> { ["log_testament"] = "lore_hidden_vault" };
            D.Lore = D.Lore.Select(id => GameData.Dialogues.ContainsKey(id) ? id : legacy.TryGetValue(id, out var l) ? l : "lore_" + id)
                .Where(id => GameData.Dialogues.ContainsKey(id)).Distinct().ToList();
        }

        public static GameStateData NewGame(string character) => new()
        {
            Character = character,
            StartCharacter = character,
            Unlocked = new List<string> { "pulse" },
        };

        /// <summary>Structural validation for loaded saves. Returns an error or null.</summary>
        public static string Validate(GameStateData d)
        {
            if (d == null) return "state missing";
            if (d.Schema != Schema) return $"unsupported schema {d.Schema}";
            if (d.Character != Characters.Kael && d.Character != Characters.Lyra) return "invalid character";
            if (d.Zone == null || !GameData.Zones.ContainsKey(d.Zone)) return $"unknown zone {d.Zone}";
            if (d.Quests == null) return "quests missing";
            foreach (var (id, q) in d.Quests)
            {
                if (!GameData.Quests.ContainsKey(id)) return $"unknown quest {id}";
                if (q == null || (q.Status != "active" && q.Status != "done") || q.Stage < 0) return $"bad quest state {id}";
            }
            if (d.Inventory == null) return "inventory missing";
            foreach (var (id, n) in d.Inventory)
            {
                if (!GameData.Items.ContainsKey(id)) return $"unknown item {id}";
                if (n < 0) return $"bad item count {id}";
            }
            if (d.Unlocked == null || d.Skills == null || d.Collected == null || d.Defeated == null || d.Revealed == null || d.Lore == null) return "lists missing";
            if (d.Stats == null || float.IsNaN(d.Stats.Playtime)) return "stats missing";
            if (d.Position != null && (d.Position.Length != 3 || d.Position.Any(v => float.IsNaN(v) || float.IsInfinity(v)))) return "bad position";
            return null;
        }

        public bool Flag(string name)
        {
            if (!D.Flags.TryGetValue(name, out var v) || v == null) return false;
            return v.Type switch
            {
                JTokenType.Boolean => v.Value<bool>(),
                JTokenType.Integer => v.Value<long>() != 0,
                JTokenType.Float => v.Value<double>() != 0,
                JTokenType.String => v.Value<string>().Length > 0,
                _ => false,
            };
        }

        public void SetFlag(string name, object value = null)
        {
            var token = value == null ? new JValue(true) : JToken.FromObject(value);
            if (D.Flags.TryGetValue(name, out var cur) && JToken.DeepEquals(cur, token)) return;
            D.Flags[name] = token;
            Bus.Emit(new FlagSet { Flag = name, Value = value ?? true });
        }

        public bool HasAbility(string id) => D.Unlocked.Contains(id);
        public void Unlock(string id)
        {
            if (HasAbility(id)) return;
            D.Unlocked.Add(id);
            Bus.Emit(new AbilityUnlocked { Ability = id });
        }

        public bool IsCollected(string id) => D.Collected.Contains(id);
        public void MarkCollected(string id) { if (!IsCollected(id)) D.Collected.Add(id); }
        public bool IsRevealed(string id) => D.Revealed.Contains(id);
        public void Reveal(string id) { if (!IsRevealed(id)) D.Revealed.Add(id); }
        public bool IsDefeated(string id) => D.Defeated.Contains(id);
        public void MarkDefeated(string id) { if (!IsDefeated(id)) D.Defeated.Add(id); }

        public string QuestStatus(string id) => D.Quests.TryGetValue(id, out var q) ? q.Status : "none";

        static readonly Regex ItemCond = new(@"^([a-z0-9_]+)(>=(\d+))?$");

        /// <summary>A condition string parsed once (conditions are evaluated every frame by interactables/triggers).</summary>
        sealed class ParsedCond
        {
            public bool Neg;
            public string Kind, A, B;
            public int Count = 1;
        }

        static readonly Dictionary<string, ParsedCond> parsed = new();

        static ParsedCond Parse(string cond)
        {
            if (parsed.TryGetValue(cond, out var pc)) return pc;
            pc = new ParsedCond { Neg = cond.StartsWith("!") };
            var p = (pc.Neg ? cond.Substring(1) : cond).Split(':');
            pc.Kind = p[0];
            pc.A = p.Length > 1 ? p[1] : "";
            pc.B = p.Length > 2 ? p[2] : "";
            if (pc.Kind == "item")
            {
                var m = ItemCond.Match(pc.A);
                if (m.Success) { pc.A = m.Groups[1].Value; pc.Count = m.Groups[3].Success ? int.Parse(m.Groups[3].Value) : 1; }
                else pc.Kind = "invalid";
            }
            parsed[cond] = pc;
            return pc;
        }

        /// <summary>Evaluate a dialogue/quest condition string (flag:x, quest:id:none|active|done, stage:q:s, item:id>=n, char:c, ability:a, revealed:id, collected:id).</summary>
        public bool Check(string cond)
        {
            if (string.IsNullOrEmpty(cond)) return true;
            var c = Parse(cond);
            bool r;
            switch (c.Kind)
            {
                case "flag": r = Flag(c.A); break;
                case "quest": r = QuestStatus(c.A) == c.B; break;
                case "stage":
                    r = D.Quests.TryGetValue(c.A, out var q) && q.Status == "active" && GameData.Quests.TryGetValue(c.A, out var def) && q.Stage < def.Stages.Length && def.Stages[q.Stage].Id == c.B;
                    break;
                case "item": r = (D.Inventory.TryGetValue(c.A, out var n) ? n : 0) >= c.Count; break;
                case "char": r = D.Character == c.A; break;
                case "ability": r = HasAbility(c.A); break;
                case "revealed": r = IsRevealed(c.A); break;
                case "collected": r = IsCollected(c.A); break;
                default: r = false; break;
            }
            return c.Neg ? !r : r;
        }

        public bool CheckAll(IEnumerable<string> conds)
        {
            if (conds == null) return true;
            if (conds is string[] arr) { for (var i = 0; i < arr.Length; i++) if (!Check(arr[i])) return false; return true; }
            foreach (var c in conds) if (!Check(c)) return false;
            return true;
        }
    }
}
