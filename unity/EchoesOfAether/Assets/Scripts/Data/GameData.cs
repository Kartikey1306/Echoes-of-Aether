using System;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using Newtonsoft.Json.Serialization;
using UnityEngine;

namespace EOA
{
    // Typed access to the JSON game data in Resources/Data (shared verbatim with the original prototype).

    /// <summary>A data-driven action: { "do": "...", ...params }.</summary>
    [JsonConverter(typeof(ActionDefConverter))]
    public sealed class ActionDef
    {
        public readonly JObject Raw;
        public ActionDef(JObject raw) { Raw = raw; }
        public string Do => Str("do");
        public string Str(string key, string fallback = null) => Raw.TryGetValue(key, out var t) && t.Type != JTokenType.Null ? t.ToString() : fallback;
        public int Int(string key, int fallback = 0) => Raw.TryGetValue(key, out var t) && (t.Type == JTokenType.Integer || t.Type == JTokenType.Float) ? t.Value<int>() : fallback;
        public float Num(string key, float fallback = 0) => Raw.TryGetValue(key, out var t) && (t.Type == JTokenType.Integer || t.Type == JTokenType.Float) ? t.Value<float>() : fallback;
        public bool Has(string key) => Raw.ContainsKey(key);
        public override string ToString() => Raw.ToString(Formatting.None);
    }

    sealed class ActionDefConverter : JsonConverter<ActionDef>
    {
        public override ActionDef ReadJson(JsonReader reader, Type objectType, ActionDef existing, bool hasExisting, JsonSerializer serializer) => new ActionDef(JObject.Load(reader));
        public override void WriteJson(JsonWriter writer, ActionDef value, JsonSerializer serializer) => value.Raw.WriteTo(writer);
    }

    public enum ItemCategory { Aether, Powerups, Quest, Upgrades, Lore }

    public sealed class ItemDef
    {
        public string Id, Name, Description, Icon, Rarity;
        public ItemCategory Category;
        public int Stack;
        public JObject Effect;
        [JsonConverter(typeof(QuestRefConverter))] public string Quest; // false in JSON means none
        public string EffectType => Effect?.Value<string>("type");
        public string EffectStr(string key) => Effect?.Value<string>(key);
    }

    sealed class QuestRefConverter : JsonConverter<string>
    {
        public override string ReadJson(JsonReader reader, Type objectType, string existing, bool hasExisting, JsonSerializer serializer)
        {
            var t = JToken.Load(reader);
            return t.Type == JTokenType.String ? t.Value<string>() : null;
        }
        public override void WriteJson(JsonWriter writer, string value, JsonSerializer serializer)
        {
            if (value == null) writer.WriteValue(false); else writer.WriteValue(value);
        }
    }

    public sealed class PowerupDef { public string Id, Item, Name, Color, Icon, Stat, Sfx, Description; public float Duration, Value; }
    public sealed class AbilityDef { public string Id, Character, Name, Slot, Description, Unlock, Icon; public float Energy, Cooldown; }
    public sealed class SkillNode { public string Id, Ability, Name, Description; public int Cost; public string[] Requires = Array.Empty<string>(); }
    public sealed class EnemyDrop { public string Item; public float Chance; }
    public sealed class EnemyDef { public string Id, Name; public float Health, Poise, Damage, Speed, Sight, AttackRange, Leash; public string[] Tags = Array.Empty<string>(); public EnemyDrop[] Drops = Array.Empty<EnemyDrop>(); }

    public sealed class ObjectiveDef { public string Id, Type, Target, Text, Marker; public int? Count; }
    public sealed class StageDef { public string Id; public ObjectiveDef[] Objectives = Array.Empty<ObjectiveDef>(); public ActionDef[] OnStart, OnComplete; }
    public sealed class QuestDef { public string Id, Type, Title, Zone, Summary, Giver, Requires; public int Order; public StageDef[] Stages = Array.Empty<StageDef>(); public ActionDef[] OnComplete; public bool IsMain => Type == "main"; }

    public sealed class DialogueChoice { public string Id, Text, Next; public string[] Conditions; public ActionDef[] Actions; }
    public sealed class DialogueBranch { public string[] If; public string Goto; }
    public sealed class DialogueNode { public string Id, Speaker, Text, Next, Else; public string[] Conditions; public ActionDef[] Actions; public DialogueChoice[] Choices; public DialogueBranch[] Branch; }
    public sealed class DialogueDef
    {
        public string Id, Start, Npc; public bool Cinematic, Lore; public DialogueNode[] Nodes = Array.Empty<DialogueNode>();
        Dictionary<string, DialogueNode> byId;
        public DialogueNode Node(string id)
        {
            byId ??= Nodes.ToDictionary(n => n.Id);
            return id != null && byId.TryGetValue(id, out var n) ? n : null;
        }
    }
    public sealed class VoiceDef { public float Pitch, Rate; public string[] Prefer; }
    public sealed class SpeakerDef { public string Id, Name, Portrait, Color; public VoiceDef Voice; }
    public sealed class ZoneMeta { public string Id, Name, Subtitle, Art, Music, Ambience, Quote; public string[] Hints = Array.Empty<string>(); }
    public sealed class CollectibleDef { public string Id, Kind, Zone; public bool Hidden; public Dictionary<string, int> Give = new(); }
    public sealed class HintDef { public string Id, Text; }

    public static class GameData
    {
        public static Dictionary<string, ItemDef> Items { get; private set; }
        public static List<ItemDef> ItemList { get; private set; }
        public static Dictionary<string, PowerupDef> Powerups { get; private set; }
        public static List<PowerupDef> PowerupList { get; private set; }
        public static Dictionary<string, AbilityDef> Abilities { get; private set; }
        public static List<AbilityDef> AbilityList { get; private set; }
        public static Dictionary<string, SkillNode> Skills { get; private set; }
        public static List<SkillNode> SkillList { get; private set; }
        public static Dictionary<string, EnemyDef> Enemies { get; private set; }
        public static Dictionary<string, QuestDef> Quests { get; private set; }
        public static List<QuestDef> QuestList { get; private set; }
        public static Dictionary<string, DialogueDef> Dialogues { get; private set; }
        public static Dictionary<string, SpeakerDef> Speakers { get; private set; }
        public static Dictionary<string, ZoneMeta> Zones { get; private set; }
        public static List<ZoneMeta> ZoneList { get; private set; }
        public static Dictionary<string, CollectibleDef> Collectibles { get; private set; }
        public static List<CollectibleDef> CollectibleList { get; private set; }
        public static Dictionary<string, HintDef> Hints { get; private set; }
        public static Dictionary<string, string> Locale { get; private set; }
        public static bool Loaded { get; private set; }

        public static readonly JsonSerializerSettings Json = new()
        {
            ContractResolver = new DefaultContractResolver { NamingStrategy = new CamelCaseNamingStrategy() },
            Converters = { new Newtonsoft.Json.Converters.StringEnumConverter(new CamelCaseNamingStrategy()) },
            MissingMemberHandling = MissingMemberHandling.Ignore,
            NullValueHandling = NullValueHandling.Ignore,
        };

        static List<T> Load<T>(string file, string key)
        {
            var asset = Resources.Load<TextAsset>("Data/" + file);
            if (asset == null) throw new Exception($"Missing data file Resources/Data/{file}.json");
            var root = JObject.Parse(asset.text);
            return root[key].ToObject<List<T>>(JsonSerializer.Create(Json));
        }

        static Dictionary<string, T> ById<T>(List<T> list, Func<T, string> id) => list.ToDictionary(id);

        public static void EnsureLoaded()
        {
            if (Loaded) return;
            ItemList = Load<ItemDef>("items", "items"); Items = ById(ItemList, x => x.Id);
            PowerupList = Load<PowerupDef>("powerups", "powerups"); Powerups = ById(PowerupList, x => x.Id);
            AbilityList = Load<AbilityDef>("abilities", "abilities"); Abilities = ById(AbilityList, x => x.Id);
            SkillList = Load<SkillNode>("abilities", "tree"); Skills = ById(SkillList, x => x.Id);
            Enemies = ById(Load<EnemyDef>("enemies", "enemies"), x => x.Id);
            QuestList = Load<QuestDef>("quests", "quests").OrderBy(q => q.Order).ToList(); Quests = ById(QuestList, x => x.Id);
            Dialogues = ById(Load<DialogueDef>("dialogue", "dialogues"), x => x.Id);
            Speakers = ById(Load<SpeakerDef>("speakers", "speakers"), x => x.Id);
            ZoneList = Load<ZoneMeta>("zones", "zones"); Zones = ById(ZoneList, x => x.Id);
            CollectibleList = Load<CollectibleDef>("collectibles", "collectibles"); Collectibles = ById(CollectibleList, x => x.Id);
            Hints = ById(Load<HintDef>("hints", "hints"), x => x.Id);
            var loc = Resources.Load<TextAsset>("Data/locale/en");
            Locale = loc != null ? JsonConvert.DeserializeObject<Dictionary<string, string>>(loc.text) : new Dictionary<string, string>();
            Loaded = true;
        }

        public static int CollectibleTotal(string kind) => CollectibleList.Count(c => c.Kind == kind);

        /// <summary>Localised UI string (falls back to the key).</summary>
        public static string T(string key) => Locale != null && Locale.TryGetValue(key, out var v) ? v : key;
    }
}
