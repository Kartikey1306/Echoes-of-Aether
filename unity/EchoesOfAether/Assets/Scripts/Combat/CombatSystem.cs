using System;
using System.Collections.Generic;
using UnityEngine;

namespace EOA
{
    /// <summary>Physics layer indices/masks used by combat (set up by the project setup editor script).</summary>
    public static class CombatLayers
    {
        public const int Default = 0, World = 6, Player = 7, Enemy = 8, NPC = 9, Interactable = 10, Projectile = 11, IgnoreCamera = 12, Pickup = 13;

        /// <summary>Static level geometry that blocks movement, sight and projectiles.</summary>
        public static readonly int WorldMask = (1 << World) | (1 << Default);
        public static readonly int PlayerMask = 1 << Player;
        public static readonly int EnemyMask = 1 << Enemy;
        public static readonly int ActorMask = PlayerMask | EnemyMask;

        /// <summary>Layers whose colliders may carry Team.Neutral IDamageables (destructibles). Empty by default;
        /// the world module may set e.g. a dedicated "Destructible" layer here.</summary>
        public static int NeutralTargetMask = 0;

        /// <summary>Layers holding things a given team can hit.</summary>
        public static int TargetsOf(Team attacker) => attacker switch
        {
            Team.Player => EnemyMask | NeutralTargetMask,
            Team.Enemy => PlayerMask | NeutralTargetMask,
            _ => ActorMask | NeutralTargetMask,
        };
    }

    /// <summary>Optional: IDamageables that know how much damage the last ReceiveHit actually applied
    /// (0 when blocked / invulnerable). Enemy implements it; Hero should too so hit-stop is exact.</summary>
    public interface IDamageReport
    {
        float LastAppliedDamage { get; }
    }

    /// <summary>Camera shake request on the Bus (camera rig subscribes). Amount is prototype "trauma" (0..1).</summary>
    public struct ShakeRequested { public float Amount; }

    /// <summary>Hit-stop request on the Bus (GameManager subscribes and drops Time.timeScale to ~0.06).</summary>
    public struct HitstopRequested { public float Seconds; }

    /// <summary>One result of an arc / radial query.</summary>
    public struct CombatHit
    {
        public IDamageable Target;
        public Vector3 Point;
        public float Distance;
    }

    /// <summary>
    /// Combat core: melee arc and radial queries (physics overlaps on the Player/Enemy layers filtered by team,
    /// capsule and angle), lock-on scoring, damage application helpers and pooled projectiles / beams
    /// (see CombatSystem.Projectiles.cs). Port of the prototype's Combat.ts.
    /// Create once at boot: <c>CombatSystem.Create(managerTransform)</c>.
    /// </summary>
    [DefaultExecutionOrder(50)]
    public sealed partial class CombatSystem : MonoBehaviour
    {
        public static CombatSystem Instance { get; private set; }

        /// <summary>Raised for every hit that applied damage (target, hit, applied damage). HUD hit markers,
        /// stats and hit-stop listeners subscribe here.</summary>
        public static event Action<IDamageable, HitInfo, float> OnHit;

        readonly Collider[] overlap = new Collider[128];
        readonly HashSet<IDamageable> seen = new();
        readonly List<CombatHit> scratch = new(32);

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void ResetStatics()
        {
            OnHit = null;
            Instance = null;
        }

        public static CombatSystem Create(Transform parent)
        {
            if (Instance != null) return Instance;
            var go = new GameObject("CombatSystem");
            if (parent != null) go.transform.SetParent(parent, false);
            else if (Application.isPlaying) DontDestroyOnLoad(go);
            return go.AddComponent<CombatSystem>();
        }

        /// <summary>The running instance, created on demand (parented nowhere, DontDestroyOnLoad).</summary>
        public static CombatSystem Ensure() => Instance != null ? Instance : Create(null);

        void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }
            Instance = this;
            InitProjectiles();
        }

        void OnDestroy()
        {
            if (Instance == this) Instance = null;
            DestroyProjectiles();
        }

        // ------------------------------------------------------------------ Helpers

        /// <summary>True when d is a non-destroyed, alive damageable.</summary>
        public static bool IsLive(IDamageable d)
        {
            if (d == null) return false;
            if (d is UnityEngine.Object o && o == null) return false;
            return d.Alive;
        }

        /// <summary>Capsule height of a damageable (enemy height, CharacterController/CapsuleCollider, or estimate).</summary>
        public static float HeightOf(IDamageable d)
        {
            if (d is Enemy e) return e.Height;
            if (d is Component c && c != null)
            {
                if (c.TryGetComponent<CharacterController>(out var cc)) return cc.height * Mathf.Abs(c.transform.lossyScale.y);
                if (c.TryGetComponent<CapsuleCollider>(out var cap)) return cap.height * Mathf.Abs(c.transform.lossyScale.y);
            }
            // AimPoint is ~60% of the height for actors.
            return Mathf.Max(d.Radius * 2f, (d.AimPoint.y - d.Position.y) / 0.6f);
        }

        /// <summary>World line of sight (IWorld when available, else a linecast against level geometry).</summary>
        public static bool LineOfSight(Vector3 from, Vector3 to)
        {
            var w = G.World;
            if (w != null && !(w is UnityEngine.Object o && o == null)) return w.LineOfSight(from, to);
            return !Physics.Linecast(from, to, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore);
        }

        IDamageable FromCollider(Collider c) => c != null ? c.GetComponentInParent<IDamageable>() : null;

        // ------------------------------------------------------------------ Queries

        /// <summary>
        /// Melee arc query: every opposing, targetable damageable whose capsule lies within `range` (horizontal, from the
        /// capsule surface) and `halfAngleDeg` of `yawDeg`, and between yMin..yMax relative to origin.
        /// Results are appended to `results`; returns the number added.
        /// </summary>
        public int Arc(Team attacker, Vector3 origin, float yawDeg, float range, float halfAngleDeg, float yMin, float yMax, List<CombatHit> results)
        {
            float yaw = yawDeg * Mathf.Deg2Rad, half = halfAngleDeg * Mathf.Deg2Rad;
            int n = Physics.OverlapSphereNonAlloc(origin, range + 6f, overlap, CombatLayers.TargetsOf(attacker), QueryTriggerInteraction.Collide);
            seen.Clear();
            int added = 0;
            for (int i = 0; i < n; i++)
            {
                var d = FromCollider(overlap[i]);
                if (d == null || !seen.Add(d)) continue;
                if (!IsLive(d) || d.Team == attacker || !d.Targetable) continue;
                if (!CombatMath.InArc(origin, yaw, range, half, yMin, yMax, d.Position, d.Radius, HeightOf(d), out var point)) continue;
                results.Add(new CombatHit { Target = d, Point = point, Distance = CombatMath.DistXZ(origin, point) });
                added++;
            }
            return added;
        }

        /// <summary>
        /// Radial query: every opposing damageable whose capsule surface is within `radius` of center and within
        /// yRange vertically. Like the prototype it does not require Targetable (damage multipliers decide).
        /// </summary>
        public int Radial(Team attacker, Vector3 center, float radius, List<CombatHit> results, float yRange = 4f)
        {
            int n = Physics.OverlapSphereNonAlloc(center, radius + 6f, overlap, CombatLayers.TargetsOf(attacker), QueryTriggerInteraction.Collide);
            seen.Clear();
            int added = 0;
            for (int i = 0; i < n; i++)
            {
                var d = FromCollider(overlap[i]);
                if (d == null || !seen.Add(d)) continue;
                if (!IsLive(d) || d.Team == attacker) continue;
                if (!CombatMath.InRadial(center, radius, yRange, d.Position, d.Radius, HeightOf(d), out float dist, out var point)) continue;
                results.Add(new CombatHit { Target = d, Point = point, Distance = dist });
                added++;
            }
            return added;
        }

        /// <summary>
        /// Best target in front of `from` along `dir` for lock-on / auto-aim (score = distance * (1 + angle * 2.2)).
        /// Neutral damageables (destructible cars) only when `neutral`, and only ahead of nothing better: their score
        /// is tripled so enemies win the auto-aim.
        /// </summary>
        public IDamageable BestTarget(Team attacker, Vector3 from, Vector3 dir, float maxDist, float maxAngleDeg, bool needLos = true, bool neutral = true)
        {
            float maxAngle = maxAngleDeg * Mathf.Deg2Rad;
            int n = Physics.OverlapSphereNonAlloc(from, maxDist + 2f, overlap, CombatLayers.TargetsOf(attacker), QueryTriggerInteraction.Collide);
            seen.Clear();
            IDamageable best = null;
            float bestScore = float.PositiveInfinity;
            for (int i = 0; i < n; i++)
            {
                var d = FromCollider(overlap[i]);
                if (d == null || !seen.Add(d)) continue;
                if (!IsLive(d) || d.Team == attacker || !d.Targetable) continue;
                Vector3 aim = d.AimPoint;
                Vector3 v = aim - from;
                float dist = v.magnitude;
                if (dist > maxDist || dist < 0.01f) continue;
                float ang = CombatMath.Angle(v, dir);
                if (ang > maxAngle) continue;
                float score = CombatMath.TargetScore(dist, ang);
                if (d.Team == Team.Neutral) { if (!neutral) continue; score *= 3f; }
                if (score >= bestScore) continue;
                if (needLos && !LineOfSight(from, aim)) continue;
                bestScore = score;
                best = d;
            }
            return best;
        }

        // ------------------------------------------------------------------ Damage application

        /// <summary>
        /// Apply a hit and return the damage that actually landed (0 when blocked, invulnerable or dead).
        /// Raises <see cref="OnHit"/> when it landed. Use the return value for hit-stop / shake / sparks.
        /// </summary>
        public static float Apply(IDamageable target, HitInfo hit)
        {
            if (!IsLive(target)) return 0f;
            bool wasTargetable = target.Targetable;
            target.ReceiveHit(hit);
            float applied = target is IDamageReport r ? r.LastAppliedDamage : (wasTargetable ? hit.Damage : 0f);
            if (applied > 0f) OnHit?.Invoke(target, hit, applied);
            return applied;
        }

        /// <summary>Convenience: did the hit land?</summary>
        public static bool TryHit(IDamageable target, HitInfo hit) => Apply(target, hit) > 0f;

        /// <summary>
        /// Arc damage: hits every target in the arc once (tracked in `once` across frames of an active window),
        /// knocking it horizontally away from `origin` with `knock` m/s. `template` supplies damage/poise/kind/source.
        /// Returns the number of targets that took damage.
        /// </summary>
        public int ArcDamage(Team attacker, Vector3 origin, float yawDeg, float range, float halfAngleDeg, HitInfo template, float knock,
                             ISet<IDamageable> once = null, float yMin = -2f, float yMax = 2.5f, Action<IDamageable, Vector3, float> onApplied = null)
        {
            scratch.Clear();
            Arc(attacker, origin, yawDeg, range, halfAngleDeg, yMin, yMax, scratch);
            return ApplyAll(origin, template, knock, once, onApplied, 0f, 0f);
        }

        /// <summary>
        /// Radial damage around `center`. `falloff` (0..1) reduces damage linearly toward the edge
        /// (prototype hero AoE uses 0.4). Returns the number of targets that took damage.
        /// </summary>
        public int RadialDamage(Team attacker, Vector3 center, float radius, HitInfo template, float knock,
                                ISet<IDamageable> once = null, float yRange = 4f, float falloff = 0f, Action<IDamageable, Vector3, float> onApplied = null)
        {
            scratch.Clear();
            Radial(attacker, center, radius, scratch, yRange);
            return ApplyAll(center, template, knock, once, onApplied, falloff, radius);
        }

        int ApplyAll(Vector3 from, HitInfo template, float knock, ISet<IDamageable> once, Action<IDamageable, Vector3, float> onApplied, float falloff, float radius)
        {
            int landed = 0;
            // Copy: applying a hit may kill and destroy targets, or trigger nested queries (re-entrancy safe).
            int count = scratch.Count;
            var buffer = count <= stackBuffer.Length && applyDepth == 0 ? stackBuffer : new CombatHit[count];
            scratch.CopyTo(0, buffer, 0, count);
            applyDepth++;
            try
            {
                landed = ApplyBuffer(buffer, count, from, template, knock, once, onApplied, falloff, radius);
            }
            finally
            {
                applyDepth--;
            }
            return landed;
        }

        int applyDepth;

        static int ApplyBuffer(CombatHit[] buffer, int count, Vector3 from, HitInfo template, float knock, ISet<IDamageable> once,
                               Action<IDamageable, Vector3, float> onApplied, float falloff, float radius)
        {
            int landed = 0;
            for (int i = 0; i < count; i++)
            {
                var h = buffer[i];
                if (!IsLive(h.Target)) continue;
                if (once != null && !once.Add(h.Target)) continue;
                Vector3 dir = h.Target.Position - from;
                dir.y = 0f;
                dir = dir.sqrMagnitude > 1e-6f ? dir.normalized : Vector3.zero;
                var hit = template;
                hit.Point = h.Point;
                hit.Knock = dir * knock;
                if (falloff > 0f && radius > 0f) hit.Damage *= 1f - (h.Distance / radius) * falloff;
                float applied = Apply(h.Target, hit);
                if (applied > 0f)
                {
                    landed++;
                    onApplied?.Invoke(h.Target, h.Point, applied);
                }
            }
            return landed;
        }

        readonly CombatHit[] stackBuffer = new CombatHit[16];

        // ------------------------------------------------------------------ Feedback

        public static void Shake(float amount)
        {
            if (amount > 0f) Bus.Emit(new ShakeRequested { Amount = amount });
        }

        public static void Hitstop(float seconds)
        {
            if (seconds > 0f) Bus.Emit(new HitstopRequested { Seconds = seconds });
        }

        void Update()
        {
            UpdateTimeScale();
            float dt = Time.deltaTime;
            if (dt > 0f) UpdateProjectiles(dt);
        }
    }
}
