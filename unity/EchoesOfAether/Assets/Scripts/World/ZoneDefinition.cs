using System;
using System.Collections.Generic;
using UnityEngine;

namespace EOA
{
    // Serialized gameplay layout of a zone scene. The zone builder (editor) fills these from the level
    // design; ZoneRuntime turns them into live triggers, exits, interactables, encounters, pickups and NPCs.
    // Conventions: positions in world metres, yaw in degrees (0 faces +Z, Unity's Euler convention).

    [Serializable] public sealed class ZoneSpawn { public string Name; public Vector3 Position; public float YawDeg; }

    [Serializable]
    public sealed class ZoneExit
    {
        public string Id, Target, Entry, Prompt, LockedText;
        public Vector3 Position;
        public float Radius = 1.6f;
        /// <summary>Walk-in exits (tunnels) fire automatically; others need Interact.</summary>
        public bool Auto;
        /// <summary>Conditions (GameState.Check syntax) that must hold to use the exit.</summary>
        public string[] Requires = Array.Empty<string>();
        /// <summary>Extra code condition (procedural zones).</summary>
        [NonSerialized] public Func<bool> RequiresFn;
    }

    [Serializable]
    public sealed class ZoneTrigger
    {
        public string Id;
        public Vector3 Center, Size = Vector3.one * 4;
        public bool Once;
        public string[] Conditions = Array.Empty<string>();
        /// <summary>Extra code condition and enter callback (procedural zones).</summary>
        [NonSerialized] public Func<bool> Available;
        [NonSerialized] public Action OnEnter;
    }

    [Serializable]
    public sealed class ZoneInteractable
    {
        public string Id;
        /// <summary>inspect | terminal | save | door | ladder | puzzle | lore | npc | pickup | cache</summary>
        public string Kind = "inspect";
        public string Prompt, LockedReason;
        public Vector3 Position;
        public float Radius = 2.2f;
        /// <summary>Only usable after Echo Sight reveals it.</summary>
        public bool Hidden;
        public string[] Conditions = Array.Empty<string>();
        /// <summary>Activated when revealed by Echo Sight.</summary>
        public GameObject RevealObject;
        /// <summary>Deactivated when revealed (e.g. an illusory wall).</summary>
        public GameObject HideOnReveal;
        /// <summary>Report an Interacted event to quests when used (unless the zone script handles it).</summary>
        public bool Report = true;
        /// <summary>Can only be used once (persisted as collected).</summary>
        public bool OneShot;
    }

    [Serializable] public sealed class ZoneEnemy { public string Type; public Vector3 Position; public float YawDeg = 180; }
    [Serializable] public sealed class ZoneWave { public List<ZoneEnemy> Enemies = new(); }

    [Serializable]
    public sealed class ZoneEncounter
    {
        public string Id;
        /// <summary>auto | quest | trigger:&lt;id&gt;</summary>
        public string Spawn = "auto";
        public List<ZoneWave> Waves = new();
        public Vector3 ArenaCenter;
        public float ArenaRadius;
        /// <summary>Respawn on every zone load even when defeated (ambient patrols).</summary>
        public bool Respawn;
    }

    [Serializable] public sealed class ZonePlacement { public string Id; public Vector3 Position; }

    [Serializable]
    public sealed class ZoneItemPickup
    {
        public string Id, Item, Prompt;
        public Vector3 Position;
        public string[] Conditions = Array.Empty<string>();
    }

    [Serializable]
    public sealed class ZoneNpc
    {
        public string Id;
        public Vector3 Position;
        public float YawDeg;
        /// <summary>Looping clip (npc_crossed, npc_hips, npc_work, npc_look, sit, kneel_work, lie, idle).</summary>
        public string Behaviour = "idle";
        public string Dialogue;
        /// <summary>Visible and talkable only while Echo Sight is active (echoes of the past).</summary>
        public bool EchoOnly;
        public string[] Conditions = Array.Empty<string>();
        /// <summary>Extra code condition (procedural zones).</summary>
        [NonSerialized] public Func<bool> Available;
    }

    [Serializable] public sealed class ZoneMarker { public string Name; public Vector3 Position; }

    /// <summary>Gameplay layout of a zone scene (one per zone scene, on the scene root object).</summary>
    public sealed class ZoneDefinition : MonoBehaviour
    {
        public string ZoneId;
        public List<ZoneSpawn> Spawns = new();
        public List<ZoneExit> Exits = new();
        public List<ZoneTrigger> Triggers = new();
        public List<ZoneInteractable> Interactables = new();
        public List<ZoneEncounter> Encounters = new();
        public List<ZonePlacement> Collectibles = new();
        public List<ZoneItemPickup> ItemPickups = new();
        public List<ZoneNpc> Npcs = new();
        public List<ZoneMarker> Markers = new();
        [Header("Map")]
        public Vector2 MapMin = new(-60, -60), MapMax = new(60, 60);
        public List<MapRect> MapRects = new();
        public List<MapLine> MapLines = new();
        public List<MapLabel> MapLabels = new();
        [Header("Environment")]
        public float KillY = -20;
        public bool Indoor;
        public string Music, Ambience;

        public ZoneSpawn Spawn(string name)
        {
            foreach (var s in Spawns) if (s.Name == name) return s;
            foreach (var s in Spawns) if (s.Name == "start") return s;
            return Spawns.Count > 0 ? Spawns[0] : new ZoneSpawn { Name = "origin" };
        }

        public Vector3? Marker(string name)
        {
            foreach (var m in Markers) if (m.Name == name) return m.Position;
            return null;
        }

        void OnDrawGizmos()
        {
            Gizmos.color = Color.green;
            foreach (var s in Spawns) Gizmos.DrawWireSphere(s.Position + Vector3.up * 0.9f, 0.4f);
            Gizmos.color = Color.cyan;
            foreach (var e in Exits) Gizmos.DrawWireSphere(e.Position, e.Radius);
            Gizmos.color = Color.yellow;
            foreach (var t in Triggers) Gizmos.DrawWireCube(t.Center, t.Size);
            Gizmos.color = new Color(1, 0.5f, 0);
            foreach (var i in Interactables) Gizmos.DrawWireSphere(i.Position, 0.3f);
        }
    }

    /// <summary>
    /// Per-zone behaviour: puzzles, doors, hazards, scripted props. Lives next to the ZoneDefinition.
    /// Every hook is optional; return true from OnInteract when the zone fully handled an interaction.
    /// </summary>
    public abstract class ZoneScript : MonoBehaviour
    {
        protected ZoneRuntime RT { get; private set; }
        protected GameState State => G.State;

        public void Bind(ZoneRuntime rt) => RT = rt;

        /// <summary>After geometry, NPCs, pickups and encounters are placed. Restore state from flags here.</summary>
        public virtual void OnLoaded() { }
        /// <summary>After the heroes are placed and the zone is playable.</summary>
        public virtual void OnEnter() { }
        public virtual bool OnInteract(string id) => false;
        /// <summary>Override the prompt of an interactable (null keeps the default).</summary>
        public virtual string PromptFor(string id) => null;
        /// <summary>Extra availability rule for an interactable (combined with its Conditions).</summary>
        public virtual bool IsAvailable(string id) => true;
        public virtual void OnTrigger(string id) { }
        public virtual void OnEncounterCleared(string id) { }
        public virtual void OnRevealed(string id) { }
        public virtual void OnFlag(string flag) { }
        public virtual void Tick(float dt) { }
        /// <summary>Zone-specific value for the HUD objective marker (e.g. a moving target).</summary>
        public virtual Vector3? ResolveMarker(string id) => null;
    }
}
