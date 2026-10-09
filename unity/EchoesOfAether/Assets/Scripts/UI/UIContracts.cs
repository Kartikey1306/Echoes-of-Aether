using System;
using System.Collections.Generic;
using UnityEngine;

namespace EOA
{
    // Small contracts the UI reads from other modules. Implementations live elsewhere (menu stage, zones,
    // enemies, audio); the UI only depends on these interfaces and degrades gracefully when they are absent.

    /// <summary>
    /// The 3D stage behind the main menu / character select / designer (implemented by the menu stage module,
    /// exposed as <c>G.Manager.MenuStage</c>).
    /// </summary>
    public interface IMenuStage
    {
        /// <summary>Frame and highlight a hero on the character-select stage (also leaves designer framing).</summary>
        void Focus(string character);
        /// <summary>Spin the displayed hero around its vertical axis.</summary>
        void Rotate(float deltaDegrees);
        /// <summary>Switch to the designer framing for a hero (full body, close camera).</summary>
        void EnterDesigner(string character);
        /// <summary>Designer camera: true = close-up on the face, false = full body.</summary>
        void FocusFace(bool face);
    }

    /// <summary>Health-bar data of an enemy (implemented by the enemy component next to IDamageable).</summary>
    public interface IEnemyHealth
    {
        /// <summary>Same id as used in EnemyDamaged / EnemyKilled events.</summary>
        int Id { get; }
        string DisplayName { get; }
        float Health01 { get; }
        /// <summary>Accumulated stagger 0..1 (1 = about to stagger).</summary>
        float Poise01 { get; }
        bool Elite { get; }
        bool IsBoss { get; }
        bool Aggro { get; }
        bool Staggered { get; }
        /// <summary>Metres above Position where the floating health bar is anchored.</summary>
        float BarHeight { get; }
    }

    /// <summary>Optional: dash charges for the HUD (implemented by the hero).</summary>
    public interface IHeroDashInfo
    {
        int DashCharges { get; }
        int MaxDashCharges { get; }
    }

    /// <summary>Optional: what the audio module is playing (debug overlay).</summary>
    public interface IAudioDebugInfo
    {
        string Mood { get; }
        string Ambience { get; }
    }

    // ------------------------------------------------------------------ Zone map

    public enum MapRectKind { Floor, Block, Water, Road }
    public enum MapMarkerKind { Exit, Npc, Save, PointOfInterest }

    /// <summary>Axis-aligned (optionally rotated) rectangle in world metres; Center/Size are (x, z).</summary>
    [Serializable]
    public sealed class MapRect
    {
        public MapRectKind Kind;
        public Vector2 Center;
        public Vector2 Size;
        /// <summary>Yaw in degrees, same convention as Transform.eulerAngles.y.</summary>
        public float RotationDeg;
    }

    /// <summary>A line (wall, rail, path) in world metres (x, z).</summary>
    [Serializable]
    public sealed class MapLine
    {
        public Vector2 From, To;
        public float Width = 1;
        public Color Color = new(0.55f, 0.67f, 0.76f, 0.35f);
    }

    [Serializable]
    public sealed class MapLabel
    {
        public string Text;
        /// <summary>World (x, z).</summary>
        public Vector2 Position;
    }

    [Serializable]
    public sealed class MapMarker
    {
        public MapMarkerKind Kind;
        public Vector3 Position;
        /// <summary>Exit prompt ("Enter the Metro") or point-of-interest name.</summary>
        public string Label;
        /// <summary>Exits: destination zone id.</summary>
        public string TargetZone;
        /// <summary>Exits: true while the exit cannot be used (optional).</summary>
        [NonSerialized] public Func<bool> Locked;
    }

    /// <summary>
    /// Vector map of a zone in world metres, drawn by the full map and the minimap. Built by the zone runtime and
    /// exposed as <c>G.Manager.CurrentZoneMap</c>. North (+Z) is up on the full map.
    /// </summary>
    public sealed class ZoneMapData
    {
        public string ZoneId;
        /// <summary>World XZ extents of the drawable area.</summary>
        public Vector2 Min, Max;
        public List<MapRect> Rects = new();
        public List<MapLine> Lines = new();
        public List<MapLabel> Labels = new();
        public List<MapMarker> Markers = new();
        /// <summary>Optional live NPC positions (survivors).</summary>
        public Func<IEnumerable<Vector3>> Npcs;
        /// <summary>Optional uncollected hidden collectibles (shown while Echo Sight detection is active).</summary>
        public Func<IEnumerable<Vector3>> HiddenPickups;
    }
}
