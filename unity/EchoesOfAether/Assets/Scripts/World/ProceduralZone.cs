using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using UnityEngine;
using static EOA.ProtoSpace;

namespace EOA
{
    /// <summary>
    /// A zone whose environment is generated in C# at load time (port of the prototype's Zone subclasses):
    /// geometry via <see cref="LevelKit"/>, Blender props via <see cref="LevelKit.Prop"/>, atmosphere and weather,
    /// plus gameplay data (spawns, exits, triggers, encounters, collectibles, NPCs, markers, map) and live
    /// interactables with closures. All coordinates are prototype design space (see <see cref="ProtoSpace"/>).
    ///
    /// Lifecycle (driven by ZoneRuntime): Bind → <see cref="Build"/> (async, report progress) → NavMesh bake →
    /// NPCs / pickups / encounters → <see cref="ZoneScript.OnLoaded"/> → heroes placed → <see cref="ZoneScript.OnEnter"/>
    /// → <see cref="ZoneScript.Tick"/> every frame.
    /// </summary>
    public abstract class ProceduralZone : ZoneScript
    {
        /// <summary>Level builder ("b" in the prototype).</summary>
        protected LevelKit B { get; private set; }
        protected ZoneDefinition Def { get; private set; }
        protected Atmosphere Atmos { get; private set; }
        protected Weather Weather { get; private set; }
        /// <summary>Seconds since the zone was entered (prototype `this.time`).</summary>
        protected float ZoneTime { get; private set; }

        readonly Dictionary<string, Action> onReveal = new();
        readonly Dictionary<string, Action> onCleared = new();
        readonly List<Action> pendingRegistrations = new();
        Func<float, string, Task> progress;

        public abstract string ZoneId { get; }

        /// <summary>Build geometry and gameplay data. Call <c>await Progress(f, label)</c> between sections.</summary>
        protected abstract Task BuildZone();

        public LevelKit Kit => B;
        /// <summary>Weather/atmosphere of the zone (cinematics trigger lightning or change rain through these).</summary>
        public Weather ZoneWeather => Weather;
        public Atmosphere ZoneAtmosphere => Atmos;
        public ZoneDefinition Definition => Def;

        internal async Task Build(ZoneDefinition def, Func<float, string, Task> progressCallback)
        {
            Def = def;
            progress = progressCallback;
            B = new LevelKit(transform);
            await BuildZone();
            LoadTrace.Mark("Finish kit");
            B.Finish();
            LoadTrace.Mark("Reflection probes");
            Atmos?.BakeReflections(B.Bounds);
        }

        protected Task Progress(float frac, string label) => progress != null ? progress(frac, label) : Task.CompletedTask;

        public override void OnLoaded()
        {
            foreach (var r in pendingRegistrations) r();
            pendingRegistrations.Clear();
        }

        public override void Tick(float dt) => ZoneTime += dt;

        public override void OnRevealed(string id)
        {
            if (onReveal.TryGetValue(id, out var a)) a?.Invoke();
        }

        public override void OnEncounterCleared(string id)
        {
            if (onCleared.TryGetValue(id, out var a)) a?.Invoke();
        }

        // ------------------------------------------------------------------ environment

        protected Atmosphere SetAtmosphere(AtmosphereSettings s) => Atmos = EOA.Atmosphere.Apply(transform, s);

        protected Weather MakeWeather(WeatherSettings s) => Weather = EOA.Weather.Create(transform, s, Atmos);

        protected void ZoneSettings(float killY, bool indoor, string music, string ambience)
        {
            Def.KillY = killY;
            Def.Indoor = indoor;
            Def.Music = music;
            Def.Ambience = ambience;
        }

        // ------------------------------------------------------------------ gameplay data (prototype space)

        protected void Spawn(string name, float x, float y, float z, float yaw) =>
            Def.Spawns.Add(new ZoneSpawn { Name = name, Position = V(x, y, z), YawDeg = Yaw(yaw) });

        protected ZoneExit Exit(string id, string target, string entry, float x, float y, float z, float radius, string prompt,
            bool auto = false, string[] requires = null, string lockedText = null, Func<bool> requiresFn = null)
        {
            var e = new ZoneExit
            {
                Id = id, Target = target, Entry = entry, Position = V(x, y, z), Radius = radius, Prompt = prompt, Auto = auto,
                Requires = requires ?? Array.Empty<string>(), LockedText = lockedText, RequiresFn = requiresFn,
            };
            Def.Exits.Add(e);
            return e;
        }

        /// <summary>Box trigger from prototype min/max corners (three's Box3).</summary>
        protected ZoneTrigger Trigger(string id, Vector3 min, Vector3 max, bool once = false, string[] conditions = null, Func<bool> available = null, Action onEnter = null)
        {
            var a = V(min); var b = V(max);
            var t = new ZoneTrigger
            {
                Id = id, Center = (a + b) / 2, Size = new Vector3(Mathf.Abs(b.x - a.x), Mathf.Abs(b.y - a.y), Mathf.Abs(b.z - a.z)),
                Once = once, Conditions = conditions ?? Array.Empty<string>(), Available = available, OnEnter = onEnter,
            };
            Def.Triggers.Add(t);
            return t;
        }

        /// <summary>Encounter: spawn "auto" | "quest" | "trigger:&lt;id&gt;"; arena centre in prototype space.</summary>
        protected ZoneEncounter Encounter(string id, string spawn, ZoneWave[] waves, Vector3? arenaCenter = null, float arenaRadius = 0, bool respawn = false, Action onClearedAction = null)
        {
            var e = new ZoneEncounter { Id = id, Spawn = spawn, Waves = new List<ZoneWave>(waves), Respawn = respawn };
            if (arenaCenter.HasValue) { e.ArenaCenter = V(arenaCenter.Value); e.ArenaRadius = arenaRadius; }
            Def.Encounters.Add(e);
            if (onClearedAction != null) onCleared[id] = onClearedAction;
            return e;
        }

        protected static ZoneWave Wave(params ZoneEnemy[] enemies) => new() { Enemies = new List<ZoneEnemy>(enemies) };

        /// <summary>Enemy placement; prototype yaw in radians (null = face the prototype default, +Z → Unity 180°).</summary>
        protected static ZoneEnemy E(string type, float x, float y, float z, float? yaw = null) =>
            new() { Type = type, Position = V(x, y, z), YawDeg = yaw.HasValue ? Yaw(yaw.Value) : 180 };

        protected void Collectible(string id, float x, float y, float z) => Def.Collectibles.Add(new ZonePlacement { Id = id, Position = V(x, y, z) });

        protected void ItemPickup(string id, string item, float x, float y, float z, string[] cond = null, string prompt = null) =>
            Def.ItemPickups.Add(new ZoneItemPickup { Id = id, Item = item, Position = V(x, y, z), Conditions = cond ?? Array.Empty<string>(), Prompt = prompt });

        protected ZoneNpc Npc(string id, float x, float y, float z, float yaw, string behaviour, string dialogue, bool echoOnly = false, string[] cond = null, Func<bool> available = null)
        {
            var n = new ZoneNpc { Id = id, Position = V(x, y, z), YawDeg = Yaw(yaw), Behaviour = behaviour, Dialogue = dialogue, EchoOnly = echoOnly, Conditions = cond ?? Array.Empty<string>(), Available = available };
            Def.Npcs.Add(n);
            return n;
        }

        protected void Marker(string name, float x, float y, float z) => Def.Markers.Add(new ZoneMarker { Name = name, Position = V(x, y, z) });

        // ------------------------------------------------------------------ map (prototype ZoneMapInfo)

        protected void MapBounds(float minX, float minZ, float maxX, float maxZ)
        {
            Def.MapMin = new Vector2(-maxX, minZ);
            Def.MapMax = new Vector2(-minX, maxZ);
        }

        /// <summary>kind: floor | block | water | road; x, z centre and w, d size; rot = prototype yaw (radians).</summary>
        protected void MapShape(string kind, float x, float z, float w, float d, float rot = 0)
        {
            var k = kind switch { "block" => MapRectKind.Block, "water" => MapRectKind.Water, "road" => MapRectKind.Road, _ => MapRectKind.Floor };
            Def.MapRects.Add(new MapRect { Kind = k, Center = MapXZ(x, z), Size = new Vector2(w, d), RotationDeg = Yaw(rot) });
        }

        protected void MapLabel(string text, float x, float z) => Def.MapLabels.Add(new MapLabel { Text = text, Position = MapXZ(x, z) });

        // ------------------------------------------------------------------ live interactables

        /// <summary>
        /// Interactable with closures (port of addInteractable). Registered with the runtime once the zone is loaded.
        /// Hidden ones become usable after Echo Sight reveals them; revealObject is shown and hideOnReveal hidden then.
        /// </summary>
        protected void Interactable(string id, string kind, Vector3 protoPos, float radius, Func<string> prompt, Action onInteract,
            Func<bool> available = null, Func<string> lockedReason = null, bool hidden = false, GameObject revealObject = null,
            GameObject hideOnReveal = null, Action onRevealAction = null, bool oneShot = false)
        {
            var def = new ZoneInteractable
            {
                Id = id, Kind = kind, Position = V(protoPos), Radius = radius, Hidden = hidden, RevealObject = revealObject,
                HideOnReveal = hideOnReveal, Report = false, OneShot = oneShot,
            };
            if (revealObject != null && !State.IsRevealed(id)) revealObject.SetActive(false);
            if (onRevealAction != null) onReveal[id] = onRevealAction;
            pendingRegistrations.Add(() => RT.AddInteractable(def, available, prompt, onInteract, lockedReason));
        }

        protected void Interactable(string id, string kind, Vector3 protoPos, float radius, string prompt, Action onInteract,
            Func<bool> available = null, Func<string> lockedReason = null, bool hidden = false, GameObject revealObject = null,
            GameObject hideOnReveal = null, Action onRevealAction = null, bool oneShot = false) =>
            Interactable(id, kind, protoPos, radius, () => prompt, onInteract, available, lockedReason, hidden, revealObject, hideOnReveal, onRevealAction, oneShot);

        /// <summary>Interactable that reports `interact:&lt;id&gt;` to quests while all conditions hold (port of questPoint).</summary>
        protected void QuestPoint(string id, Vector3 protoPos, string prompt, string[] cond, float radius = 2.2f, bool hidden = false, Func<string> lockedReason = null) =>
            Interactable(id, "inspect", protoPos, radius, () => prompt, () => EmitInteract(id), () => cond == null || State.CheckAll(cond), lockedReason, hidden);

        /// <summary>Save terminal (opens the save screen).</summary>
        protected void SaveTerminal(string id, Vector3 protoPos, float radius = 2.2f) =>
            Def.Interactables.Add(new ZoneInteractable { Id = id, Kind = "save", Prompt = "Use save terminal", Position = V(protoPos), Radius = radius, Report = false });

        // ------------------------------------------------------------------ runtime helpers (prototype ZoneRuntime)

        protected static Vector3 P(float x, float y, float z) => new(x, y, z);
        protected Hero Player => G.Manager != null ? G.Manager.Player : null;
        /// <summary>Player position in Unity space.</summary>
        protected Vector3 PlayerPos => Player != null ? Player.Position : Vector3.zero;
        /// <summary>Player position in prototype space (for comparing with layout numbers).</summary>
        protected Vector3 PlayerProto => V(PlayerPos);
        protected bool Check(string cond) => State.Check(cond);
        protected bool Flag(string name) => State.Flag(name);
        protected void SetFlag(string name, bool value = true) => State.SetFlag(name, value);
        protected bool Revealed(string id) => State.IsRevealed(id);
        protected bool EchoActive => RT != null && RT.EchoActive;
        protected void EmitInteract(string id) => Bus.Emit(new Interacted { Id = id, Kind = "inspect" });
        protected void Toast(string text) => G.Presentation?.Toast(text, ToastKind.Info);
        /// <summary>Show a registered hint by id (hints.json), or toast free text.</summary>
        protected void Hint(string text)
        {
            if (string.IsNullOrEmpty(text)) return;
            if (GameData.Hints.ContainsKey(text)) G.Presentation?.Hint(text);
            else G.Presentation?.Toast(text, ToastKind.Info);
        }
        protected void Sfx(string id, Vector3? unityPos = null) => G.Audio?.Play(id, unityPos);
        protected void Shake(float amount) => CombatSystem.Shake(amount);
        protected VfxManager Vfx => VfxManager.Instance;
        protected void SpawnEncounter(string id) => RT.SpawnEncounter(id);
        protected bool IsDefeated(string id) => State.IsDefeated(id);
        protected void GiveItem(string id, int qty = 1) => G.Manager.Inventory.Add(id, qty);
        protected void PlayDialogue(string id) => _ = G.Manager.PlayDialogue(id, "talk");

        /// <summary>Damage the player from a hazard (Unity-space source position).</summary>
        protected void DamagePlayer(float amount, string source, Vector3? from = null)
        {
            var p = Player;
            if (p == null || !p.Alive) return;
            var src = from ?? p.Position;
            var away = p.Position - src; away.y = 0;
            var knock = (away.sqrMagnitude > 0.01f ? away.normalized : -p.transform.forward) * 3 + Vector3.up * 1.5f;
            p.ReceiveHit(new HitInfo { Damage = amount, Poise = amount, Knock = knock, Kind = HitKind.Environment, Point = src, Source = this });
        }

        /// <summary>Scripted traversal through prototype-space points (ladders, drops).</summary>
        protected Task Traverse(Vector3[] protoPoints, string clip, float duration, float? endYaw = null)
        {
            var pts = new Vector3[protoPoints.Length];
            for (var i = 0; i < pts.Length; i++) pts[i] = V(protoPoints[i]);
            return G.Manager.Traverse(pts, clip, duration, endYaw.HasValue ? Yaw(endYaw.Value) : null);
        }

        /// <summary>Call after opening doors/removing blockers so enemies can path through (background re-bake).</summary>
        protected void RefreshNavMesh() => RT?.RefreshNavMesh();

        /// <summary>Persistent VFX emitter (fire | sparks | steam | aether) at a prototype position, removed with the zone.</summary>
        protected GameObject Emitter(float x, float y, float z, string kind, float rate = 1, float radius = 1)
        {
            var go = Vfx?.Emitter(V(x, y, z), kind, rate, radius);
            if (go != null) go.transform.SetParent(transform, true);
            return go;
        }
    }
}
