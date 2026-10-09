using System.Collections.Generic;
using System.Threading.Tasks;
using UnityEngine;

namespace EOA
{
    // Shared runtime contracts between modules (actors, enemies, world, UI, audio, VFX).
    // Implementations live in their modules; GameManager wires them together.

    public enum Team { Player, Enemy, Neutral }

    public enum HitKind { Light, Heavy, Bolt, Pulse, Ultimate, Enemy, Environment }

    public struct HitInfo
    {
        public float Damage;
        public float Poise;          // stagger damage
        public Vector3 Knock;        // impulse direction * strength (m/s)
        public HitKind Kind;
        public Vector3 Point;
        public Component Source;     // attacker (may be null)
        public bool Pierce;          // ignores shields/blocking
        public bool Crit;
    }

    /// <summary>Anything that can be hit: heroes, enemies, destructibles.</summary>
    public interface IDamageable
    {
        Team Team { get; }
        bool Alive { get; }
        Vector3 Position { get; }
        /// <summary>World point to aim projectiles/lock-on at (chest height).</summary>
        Vector3 AimPoint { get; }
        float Radius { get; }
        /// <summary>False when currently untargetable (phased stalker, cinematic).</summary>
        bool Targetable { get; }
        void ReceiveHit(HitInfo hit);
    }

    /// <summary>Audio facade. Sound ids match the original SFX recipe names (e.g. "slash_light", "pickup").</summary>
    public interface IAudio
    {
        void Play(string id, Vector3? position = null, float volume = 1, float pitch = 1);
        void PlayUi(string id);
        /// <summary>menu | explore | combat | boss | sidequest | tension | ending | silence</summary>
        void SetMusic(string mood, float fade = 2f);
        /// <summary>rain_city | metro_drip | facility_hum | vault_hum | wind_roof | core_drone | none</summary>
        void SetAmbience(string id, float fade = 2f);
        void Duck(float amount, float seconds);
        void Thunder(float intensity);
        void SetVolumes(AudioSettings s);
    }

    /// <summary>Visual effects facade (pooled particle systems, flashes, rings).</summary>
    public interface IVfx
    {
        void Sparks(Vector3 pos, Color color, int count = 12, float speed = 6);
        void Impact(Vector3 pos, Vector3 normal, Color color, float scale = 1);
        void Explode(Vector3 pos, Color color, float scale = 1);
        void Ring(Vector3 pos, Color color, float radius, float duration = 0.5f);
        void Slash(Transform attachTo, Vector3 localOffset, float yawDeg, float rollDeg, Color color, float radius = 1.4f, float duration = 0.18f);
        void Flash(Vector3 pos, Color color, float intensity = 6, float range = 6, float duration = 0.12f);
        void EchoWave(Vector3 pos, float radius, float duration);
        void Aether(Vector3 pos, Color color, int count = 20);
        /// <summary>Persistent emitter (fire, sparks, steam, aether); returns a handle to stop it.</summary>
        GameObject Emitter(Vector3 pos, string kind, float rate = 1);
    }

    /// <summary>World services exposed to actors (implemented by ZoneRuntime).</summary>
    public interface IWorld
    {
        string ZoneId { get; }
        IReadOnlyList<IDamageable> Enemies { get; }
        bool EchoActive { get; }
        /// <summary>Simultaneous-attack limiter: enemies request a token before attacking.</summary>
        bool RequestAttackToken(Object enemy);
        void ReleaseAttackToken(Object enemy);
        bool LineOfSight(Vector3 from, Vector3 to);
        /// <summary>Ground height under a point (null if none within range).</summary>
        float? GroundAt(Vector3 p, float maxDist = 20);
        void OnEnemyKilled(Component enemy);
        void SpawnMinion(string type, Vector3 pos, string encounterId);
    }

    /// <summary>What the HUD/UI needs from a hero.</summary>
    public interface IHeroStatus
    {
        string Character { get; }
        float Health { get; }
        float Shield { get; }
        float Energy { get; }
        float Ultimate { get; } // 0..1 charge
        CharStats Stats { get; }
        /// <summary>Cooldown 0..1 remaining for "ability", "dash", "bolt".</summary>
        float Cooldown01(string slot);
    }

    /// <summary>Async cinematic/dialogue presentation helpers implemented by UI.</summary>
    public interface IPresentation
    {
        Task Fade(bool toBlack, float seconds);
        void CinematicBars(bool on);
        void Toast(string text, ToastKind kind = ToastKind.Info);
        void Hint(string id);
        void ShowSkipPrompt(bool on, float progress01 = 0);
    }
}
