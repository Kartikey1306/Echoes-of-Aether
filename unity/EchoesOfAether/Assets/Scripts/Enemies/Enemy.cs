using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.AI;
using Random = UnityEngine.Random;

namespace EOA
{
    public enum EnemyState { Idle, Patrol, Alert, Pursue, Attack, Recover, Stagger, Return, Dead, Phase, Special }

    /// <summary>
    /// Every service an enemy needs from the rest of the game, in one place (GameManager / World / settings).
    /// If a GameManager member is renamed only this adapter changes.
    /// </summary>
    public static class EnemyHost
    {
        /// <summary>The controlled hero (IDamageable) or null.</summary>
        public static IDamageable Player => G.Manager != null ? G.Manager.PlayerTarget : null;

        /// <summary>The AI partner (IDamageable) or null.</summary>
        public static IDamageable Companion => G.Manager != null ? G.Manager.CompanionTarget : null;

        public static void DropItem(string item, Vector3 pos)
        {
            if (G.Manager != null) G.Manager.DropItem(item, pos);
        }

        public static void SetBoss(bool on)
        {
            if (G.Manager != null) G.Manager.SetBoss(on);
        }

        public static DifficultyMods Difficulty => G.Settings != null ? G.Settings.Difficulty : new DifficultyMods(1, 1, 1, 1);

        /// <summary>G.World unless it is a destroyed Unity object.</summary>
        public static IWorld World
        {
            get
            {
                var w = G.World;
                if (w is UnityEngine.Object o && o == null) return null;
                return w;
            }
        }

        public static bool EchoActive => World != null && World.EchoActive;

        public static bool RequestToken(UnityEngine.Object e) => World == null || World.RequestAttackToken(e);

        public static void ReleaseToken(UnityEngine.Object e) => World?.ReleaseAttackToken(e);

        public static float? GroundAt(Vector3 p, float maxDist)
        {
            if (World != null) return World.GroundAt(p, maxDist);
            return Physics.Raycast(p, Vector3.down, out var hit, maxDist, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore) ? hit.point.y : (float?)null;
        }

        /// <summary>Roughly on screen and within 60 m of the main camera (stuck recovery only teleports unseen enemies).</summary>
        public static bool CameraSees(Vector3 p)
        {
            var cam = Camera.main;
            if (cam == null) return false;
            Vector3 v = cam.WorldToViewportPoint(p);
            return v.z > 0f && v.z < 60f && v.x > -0.05f && v.x < 1.05f && v.y > -0.05f && v.y < 1.05f;
        }

        public static void Toast(string text, ToastKind kind)
        {
            if (G.Presentation != null) G.Presentation.Toast(text, kind);
            else Bus.Emit(new Toast { Text = text, Kind = kind });
        }

        public static void SpawnMinion(string type, Vector3 pos, string encounterId) => World?.SpawnMinion(type, pos, encounterId);
    }

    /// <summary>
    /// Common enemy behaviour (port of Enemy.ts): perception (sight range/cone + line of sight), alert sharing within
    /// an encounter, leash/return, stuck recovery, poise &amp; stagger, attack tokens, death, drops and events.
    /// Movement: NavMeshAgent-constrained steering when spawned on a NavMesh, CharacterController otherwise,
    /// free transform movement for flyers. Visuals live under the "Visual" child (VisualOffsetY, death sink).
    /// Created by <see cref="EnemyFactory.Create"/>.
    /// </summary>
    [DisallowMultipleComponent]
    public abstract class Enemy : MonoBehaviour, IDamageable, IDamageReport, IEnemyHealth
    {
        // ------------------------------------------------------------------ Registry

        static int nextId = 1;
        static readonly List<Enemy> all = new();

        /// <summary>All spawned, not yet destroyed enemies.</summary>
        public static IReadOnlyList<Enemy> All => all;

        /// <summary>Global cinematic freeze (prototype world.freezeEnemies): enemies animate but do not think.</summary>
        public static bool FreezeAll;

        /// <summary>Use NavMesh steering when a NavMesh exists near the spawn point.</summary>
        public static bool UseNavMesh = true;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void ResetStatics()
        {
            all.Clear();
            FreezeAll = false;
            UseNavMesh = true;
        }

        /// <summary>Alive, aggro'd enemies within `radius` of a point (combat music / "in combat" state).</summary>
        public static int CountAggro(Vector3 near, float radius = 35f)
        {
            int n = 0;
            float r2 = radius * radius;
            foreach (var e in all) if (e != null && e.Alive && e.Aggro && (e.position - near).sqrMagnitude < r2) n++;
            return n;
        }

        // ------------------------------------------------------------------ Identity

        public int Id { get; private set; }
        /// <summary>Factory type (drone, sentinel, warden, stalker, guardian, guardian_vault).</summary>
        public string Variant { get; private set; }
        public EnemyDef Def { get; private set; }
        /// <summary>Data id (EnemyDef.Id), used by quests and events.</summary>
        public string Type => Def != null ? Def.Id : Variant;
        public string DisplayName => Def != null ? Def.Name : Variant;
        public bool HasTag(string tag) => Def != null && Def.Tags != null && Array.IndexOf(Def.Tags, tag) >= 0;
        public bool IsBoss => HasTag("boss");
        public bool IsElite => HasTag("elite");

        /// <summary>Owning encounter (aggro is shared, World.OnEnemyKilled advances waves).</summary>
        public string EncounterId { get; set; }

        string spawnId;
        /// <summary>Spawn id reported in EnemyKilled (defaults to the encounter id like the prototype).</summary>
        public string SpawnId { get => spawnId ?? EncounterId; set => spawnId = value; }

        // ------------------------------------------------------------------ IDamageable

        public Team Team => Team.Enemy;
        public bool Alive { get; private set; } = true;
        /// <summary>Feet position.</summary>
        public Vector3 Position => position;
        public virtual Vector3 AimPoint => position + Vector3.up * (Height * 0.6f + VisualOffsetY);
        public float Radius { get; protected set; } = 0.5f;
        public float Height { get; protected set; } = 2f;
        public virtual bool Targetable => Alive && !Invulnerable;
        public float LastAppliedDamage { get; private set; }

        // ------------------------------------------------------------------ Stats / flags

        public float Health { get; protected set; }
        public float MaxHealth { get; protected set; }
        public float Poise { get; protected set; }
        public float MaxPoise { get; protected set; }
        public float Health01 => MaxHealth > 0f ? Mathf.Clamp01(Health / MaxHealth) : 0f;
        /// <summary>Poise damage taken 0..1 (HUD stagger bar).</summary>
        public float PoiseDamage01 => MaxPoise > 0f ? Mathf.Clamp01(1f - Poise / MaxPoise) : 0f;

        // IEnemyHealth (HUD floating bars and the boss bar).
        float IEnemyHealth.Poise01 => PoiseDamage01;
        bool IEnemyHealth.Elite => IsElite;
        bool IEnemyHealth.Staggered => IsStaggered;
        float IEnemyHealth.BarHeight => Height + VisualOffsetY + 0.35f;
        /// <summary>Seconds since the last damage (health bar visibility).</summary>
        public float SinceHit { get; private set; } = 99f;
        /// <summary>Ignore all hits (cinematics, vault guardian uses its own rule).</summary>
        public bool Invulnerable { get; set; }
        /// <summary>Per-enemy cinematic freeze: animate only.</summary>
        public bool Frozen { get; set; }
        /// <summary>Visual-only vertical offset (cinematic staging, e.g. guardian rising out of the pit).</summary>
        public float VisualOffsetY { get; set; }
        public bool Flying { get; protected set; }
        public float Leash { get; protected set; }
        /// <summary>Boss phase for the HUD (0 = not a phased boss).</summary>
        public virtual int BossPhaseNumber => 0;

        public EnemyState State { get; private set; } = EnemyState.Idle;
        public float StateTime => stateT;
        public bool IsStaggered => State == EnemyState.Stagger;
        /// <summary>Seconds the current stagger lasts (poise break and deflect are long, knockdowns medium).</summary>
        public float StaggerTime => staggerTime;
        /// <summary>The last ReceiveHit was a critical (staggered target or a counter attack).</summary>
        public bool LastHitCrit { get; private set; }
        /// <summary>Seconds until the current attack's active frames (0 while active), or -1 when not attacking.
        /// Heroes use it for perfect dodges.</summary>
        public float ThreatIn
        {
            get
            {
                if (threatAt < 0f || !Alive) return -1f;
                float now = Time.time;
                if (now > threatEnd) return -1f;
                return Mathf.Max(0f, threatAt - now);
            }
        }
        public bool Aggro { get; private set; }
        public bool CanSeeTarget { get; private set; }
        /// <summary>Current target (player preferred, companion when clearly closer). May be null.</summary>
        public IDamageable Target { get; private set; }

        /// <summary>Facing in degrees (Unity yaw: 0 = +Z).</summary>
        public float YawDeg
        {
            get => yaw * Mathf.Rad2Deg;
            set => yaw = value * Mathf.Deg2Rad;
        }

        public Vector3 Home => home;
        /// <summary>Robot visuals (null if none).</summary>
        public RobotRig Model => Rig;

        // ------------------------------------------------------------------ Protected state

        protected Vector3 position;
        protected Vector3 velocity;
        /// <summary>Facing in radians.</summary>
        protected float yaw;
        protected Vector3 home;
        protected float homeYaw;
        protected float stateT;
        protected float deathT;
        /// <summary>Metres the visual sinks below the feet (death).</summary>
        protected float deathSink;
        protected float lastSeen;
        protected bool hasToken;
        protected float stunT;
        protected Transform visual;
        protected RobotRig Rig;
        protected Dictionary<string, RobotClip> Clips;

        protected bool hasArena;
        protected Vector3 arenaCenter;
        protected float arenaRadius;

        float seeT, stuckT, sideStepT, sideStepDir = 1f, noTargetT;
        Vector3 lastPos;
        bool disposed;
        Action<IDamageable, Vector3, float> meleeFx;

        // Feel: hit-stop, flinch, launch / knockdown, poise break, telegraph and threat timing.
        float freezeT, freezeDur, freezeAmp, freezePhase;
        Vector3 freezeDir;
        Vector3 flinch, flinchVel;
        float airY, airVy;
        protected float staggerTime = 1.2f;
        bool brokenStagger;
        float breakFxT;
        float threatAt = -1f, threatEnd = -1f, teleLead;
        bool glinted;
        Vector3 lastHitDir;
        HitKind lastHitKind;

        // Target velocity estimate
        IDamageable velTarget;
        CharacterController velTargetCC;
        Vector3 velLastPos, targetVel;

        // Movement
        enum MoveMode { Kinematic, Agent, Controller }
        MoveMode mode = MoveMode.Kinematic;
        NavMeshAgent agent;
        CharacterController cc;
        CapsuleCollider capsule;
        SphereCollider sphere;
        NavMeshPath path;
        readonly Vector3[] corners = new Vector3[32];
        int cornerCount, cornerIdx;
        Vector3 pathGoal;
        float repathT;

        public const float Gravity = -22f;

        // ------------------------------------------------------------------ Setup

        /// <summary>Called by the factory right after AddComponent.</summary>
        internal void Init(string variant, EnemyDef def)
        {
            Id = nextId++;
            Variant = variant;
            Def = def;
            var d = EnemyHost.Difficulty;
            MaxHealth = def.Health * d.EnemyHealth;
            Health = MaxHealth;
            MaxPoise = def.Poise;
            Poise = def.Poise;
            Leash = def.Leash;
            seeT = Random.value * 0.25f;
            gameObject.name = "enemy:" + variant;
            gameObject.layer = CombatLayers.Enemy;
            visual = new GameObject("Visual").transform;
            visual.gameObject.layer = CombatLayers.Enemy;
            visual.SetParent(transform, false);
            meleeFx = OnMeleeApplied;
            Configure();
        }

        /// <summary>Set Height/Radius/Flying, build the model under <see cref="visual"/>.</summary>
        protected abstract void Configure();

        /// <summary>Place the enemy (feet position, Unity yaw in degrees) and create its physics body.</summary>
        public virtual void Spawn(Vector3 pos, float yawDeg)
        {
            position = pos;
            home = pos;
            yaw = yawDeg * Mathf.Deg2Rad;
            homeYaw = yaw;
            lastPos = pos;
            SetupBody();
            if (!all.Contains(this)) all.Add(this);
            SyncModel();
            OnSpawned();
        }

        protected virtual void OnSpawned() { }

        public void SetArena(Vector3 center, float radius)
        {
            hasArena = true;
            arenaCenter = center;
            arenaRadius = radius;
        }

        public void ClearArena() => hasArena = false;

        public bool HasArena => hasArena;

        void SetupBody()
        {
            transform.position = position;
            if (Flying)
            {
                sphere = gameObject.AddComponent<SphereCollider>();
                sphere.radius = Radius;
                sphere.center = Vector3.zero;
                AddKinematicBody();
                mode = MoveMode.Kinematic;
                return;
            }
            if (UseNavMesh && NavMesh.SamplePosition(position, out var hit, 2f, NavMesh.AllAreas))
            {
                position = hit.position;
                home = position;
                lastPos = position;
                transform.position = position;
                agent = gameObject.AddComponent<NavMeshAgent>();
                agent.radius = Radius;
                agent.height = Height;
                agent.baseOffset = 0f;
                agent.speed = Mathf.Max(1f, Def.Speed * 1.5f);
                agent.acceleration = 40f;
                agent.angularSpeed = 0f;
                agent.autoBraking = false;
                agent.autoRepath = false;
                agent.obstacleAvoidanceType = ObstacleAvoidanceType.NoObstacleAvoidance;
                agent.updatePosition = false;
                agent.updateRotation = false;
                if (agent.isOnNavMesh)
                {
                    agent.Warp(position);
                    agent.isStopped = true;
                    path = new NavMeshPath();
                    // The agent only routes and constrains; hits/blocking use a capsule on a kinematic body.
                    capsule = gameObject.AddComponent<CapsuleCollider>();
                    capsule.radius = Radius;
                    capsule.height = Mathf.Max(Height, Radius * 2f);
                    capsule.center = new Vector3(0f, Height * 0.5f, 0f);
                    capsule.direction = 1;
                    AddKinematicBody();
                    mode = MoveMode.Agent;
                    return;
                }
                agent.enabled = false;
                Destroy(agent);
                agent = null;
            }
            cc = gameObject.AddComponent<CharacterController>();
            cc.radius = Radius;
            cc.height = Mathf.Max(Height, Radius * 2f + 0.01f);
            cc.center = new Vector3(0f, cc.height * 0.5f, 0f);
            cc.stepOffset = Mathf.Min(0.4f, Height * 0.3f);
            cc.slopeLimit = 50f;
            cc.skinWidth = 0.04f;
            cc.minMoveDistance = 0f;
            mode = MoveMode.Controller;
        }

        void AddKinematicBody()
        {
            var rb = gameObject.AddComponent<Rigidbody>();
            rb.isKinematic = true;
            rb.useGravity = false;
            rb.interpolation = RigidbodyInterpolation.None;
        }

        void DisableBody()
        {
            if (cc != null) cc.enabled = false;
            if (capsule != null) capsule.enabled = false;
            if (sphere != null) sphere.enabled = false;
            if (agent != null) agent.enabled = false;
            mode = MoveMode.Kinematic;
        }

        // ------------------------------------------------------------------ Damage

        public void ReceiveHit(HitInfo h)
        {
            LastAppliedDamage = 0f;
            LastHitCrit = false;
            if (!Alive || Invulnerable) return;
            // Crit window: a staggered (poise-broken / knocked-down / deflected) enemy, or a counter attack.
            bool crit = h.Kind != HitKind.Enemy && h.Kind != HitKind.Environment && (State == EnemyState.Stagger || h.Crit);
            float dmg = h.Damage * (crit ? 1.5f : 1f) * DamageTakenMul(h);
            if (dmg <= 0f) return;
            Health -= dmg;
            SinceHit = 0f;
            LastAppliedDamage = dmg;
            LastHitCrit = crit;
            Vector3 kd = h.Knock;
            kd.y = 0f;
            lastHitDir = kd.sqrMagnitude > 1e-4f ? kd.normalized : (h.Source != null ? Flat(position - h.Source.transform.position).normalized : -Forward);
            lastHitKind = h.Kind;
            OnHurt(h, dmg);
            Flinch(h, crit);
            if (crit) CritFx(h.Point);
            Bus.Emit(new EnemyDamaged { Id = Id, Type = Type, Amount = dmg });
            if (!Aggro) SetAggro();
            if (Health <= 0f)
            {
                Die(h);
                return;
            }
            bool heavy = h.Kind == HitKind.Heavy || h.Kind == HitKind.Ultimate;
            Poise -= h.Poise;
            if (Poise <= 0f)
            {
                // Poise break: long stagger = crit window.
                Poise = MaxPoise;
                staggerTime = IsBoss ? 1.2f : Flying ? 1.6f : IsElite ? 2.4f : 2.0f;
                brokenStagger = !IsBoss;
                if (!IsBoss) BreakFx(h.Point);
                Stagger(h);
                if (heavy && LightBody) Launch(h.Kind == HitKind.Ultimate ? 6.5f : 5f);
            }
            else if (heavy && LightBody && h.Poise >= 55f)
            {
                // Heavy finisher / ultimate on a light robot: launch and knock down.
                staggerTime = 1.5f;
                brokenStagger = false;
                Stagger(h);
                Launch(h.Kind == HitKind.Ultimate ? 6.5f : 5f);
            }
            else if (h.Kind == HitKind.Pulse && LightBody)
            {
                Knock(h.Knock);
                airVy = Mathf.Max(airVy, 2.6f); // pulse pops light robots off their feet
            }
            else Knock(h.Knock * 0.35f);
        }

        static Vector3 Flat(Vector3 v)
        {
            v.y = 0f;
            return v;
        }

        /// <summary>Small ground robots that can be launched / knocked down (not elites, bosses or flyers).</summary>
        protected virtual bool LightBody => !Flying && !IsElite && !IsBoss && Height <= 2.3f;

        void Launch(float vy)
        {
            airVy = Mathf.Max(airVy, vy);
            if (airY <= 0f) airY = 0.001f;
        }

        /// <summary>Directional flinch: the body jolts away from the blow (rig jolt sign + a sprung visual push).</summary>
        void Flinch(HitInfo h, bool crit)
        {
            float amount = h.Kind == HitKind.Heavy || h.Kind == HitKind.Ultimate ? 1f : h.Kind == HitKind.Pulse ? 0.8f : h.Kind == HitKind.Bolt ? 0.35f : 0.55f;
            if (crit) amount *= 1.25f;
            if (IsBoss) amount *= 0.3f;
            Vector3 local = transform.InverseTransformDirection(lastHitDir);
            if (Rig != null && Rig.Anim != null) Rig.Anim.Jolt(local.x >= 0f ? -1f : 1f, Mathf.Clamp01(0.45f + amount * 0.55f));
            flinchVel += lastHitDir * (2.2f * amount);
        }

        void CritFx(Vector3 point)
        {
            var p = point.sqrMagnitude > 0.01f ? point : AimPoint;
            FxKit.Sparks(p, Vector3.up, 14, 0xfff0c0u, 8f);
            FxKit.FlashSprite(p, 1.6f, 0xfff4d0u, 0.08f);
        }

        void BreakFx(Vector3 point)
        {
            var p = AimPoint;
            FxKit.FlashSprite(p, 3.4f, 0xffffffu, 0.14f);
            FxKit.Sparks(p, null, 36, 0xffd080u, 9f);
            FxKit.Shockwave(position, Radius * 3.5f, 0xffc060, 0.35f);
            FxKit.Sfx("enemy_stagger", p);
            FxKit.Sfx("poise_break", p);
            CombatPostFx.Impact(0.4f);
            CombatTelemetry.Record("poise_break", Id, staggerTime);
        }

        /// <summary>Hit-stop this enemy (AI and animation freeze for `seconds` of real time, the body shudders along `dir`).</summary>
        public void HitFreeze(float seconds, Vector3 dir, float amplitude)
        {
            if (!isActiveAndEnabled || seconds <= 0f) return;
            freezeT = Mathf.Max(freezeT, seconds);
            freezeDur = Mathf.Max(0.01f, freezeT);
            freezeAmp = IsBoss ? amplitude * 0.4f : amplitude;
            freezeDir = Flat(dir).sqrMagnitude > 1e-4f ? Flat(dir).normalized : -Forward;
        }

        /// <summary>Attack wind-up started: the blow lands in `lead` game seconds and stays active for `active`.
        /// Ramps the telegraph glow and flashes a glint just before impact.</summary>
        protected void BeginThreat(float lead, float active)
        {
            float now = Time.time;
            threatAt = now + Mathf.Max(0f, lead);
            threatEnd = threatAt + Mathf.Max(0.05f, active);
            teleLead = Mathf.Max(0.01f, lead);
            glinted = false;
            if (Rig != null) Rig.Telegraph = 0.3f;
        }

        /// <summary>The attack's active frames started (threat now).</summary>
        protected void ThreatActive(float active)
        {
            float now = Time.time;
            if (threatAt < 0f || threatAt > now) threatAt = now;
            threatEnd = Mathf.Max(threatEnd, now + Mathf.Max(0.05f, active));
        }

        protected void EndThreat()
        {
            threatAt = -1f;
            threatEnd = -1f;
            teleLead = 0f;
        }

        /// <summary>Lead (s) from one clip event to another at playback `speed` (telegraph -> hit_start).</summary>
        protected static float EventGap(RobotClip clip, string from, string to, float speed)
        {
            float a = -1f, b = -1f;
            foreach (var e in clip.Events)
            {
                if (e.Name == from && a < 0f) a = e.T;
                if (e.Name == to && b < 0f) b = e.T;
            }
            return a >= 0f && b >= a ? (b - a) / Mathf.Max(0.05f, speed) : 0.4f;
        }

        /// <summary>A hero's heavy turned this enemy's blow aside: long stagger (crit window). Bosses only reel.</summary>
        public virtual void Deflected(IDamageable by)
        {
            if (!Alive) return;
            EndThreat();
            if (Rig != null) Rig.Telegraph = 0f;
            var src = by is Component c && c != null ? c.transform.position : position - Forward;
            lastHitDir = Flat(position - src).normalized;
            if (Rig != null && Rig.Anim != null) Rig.Anim.Jolt(1f, 1f);
            flinchVel += lastHitDir * 3f;
            if (IsBoss) return;
            Poise = MaxPoise;
            staggerTime = IsElite ? 2.0f : 1.8f;
            brokenStagger = true;
            Stagger(new HitInfo { Knock = lastHitDir * 4f, Kind = HitKind.Heavy, Point = AimPoint, Source = by as Component });
        }

        /// <summary>Stun for `seconds` (abilities with a stun component; HitInfo has no stun field).</summary>
        public void Stun(float seconds)
        {
            if (Alive) stunT = Mathf.Max(stunT, seconds);
        }

        /// <summary>Kill immediately (scripted).</summary>
        public void Kill()
        {
            if (Alive) Die(null);
        }

        /// <summary>Multiplier for incoming damage (shields, armour, phasing).</summary>
        protected virtual float DamageTakenMul(HitInfo h) => 1f;

        protected virtual void OnHurt(HitInfo h, float dmg) { }

        protected void Knock(Vector3 v)
        {
            velocity.x += v.x;
            velocity.z += v.z;
        }

        /// <summary>Enter the stagger state for <see cref="StaggerTime"/> (set by the caller: poise break, knockdown,
        /// deflect). Subclasses play their stagger clip and leave when stateT &gt; StaggerTime.</summary>
        protected virtual void Stagger(HitInfo h)
        {
            Knock(h.Knock);
            ReleaseToken();
            EndThreat();
            Enter(EnemyState.Stagger);
        }

        protected virtual void Die(HitInfo? h)
        {
            Alive = false;
            Health = 0f;
            ReleaseToken();
            Enter(EnemyState.Dead);
            EndThreat();
            DisableBody();
            if (h.HasValue)
            {
                Knock(h.Value.Knock * (h.Value.Kind == HitKind.Heavy || h.Value.Kind == HitKind.Ultimate ? 1.1f : 0.6f));
                // Heavy kills throw small robots.
                if (LightBody && (h.Value.Kind == HitKind.Heavy || h.Value.Kind == HitKind.Ultimate || h.Value.Kind == HitKind.Pulse)) Launch(4f);
            }
            CombatTelemetry.Record("kill", Id);
            if (Def.Drops != null)
                foreach (var d in Def.Drops)
                    if (d != null && Random.value < d.Chance) EnemyHost.DropItem(d.Item, position + Vector3.up * 0.6f);
            Bus.Emit(new EnemyKilled { Id = Id, Type = Type, Tags = Def.Tags, SpawnId = SpawnId, Zone = EnemyHost.World?.ZoneId ?? "" });
            EnemyHost.World?.OnEnemyKilled(this);
        }

        public void SetAggro()
        {
            if (Aggro || !Alive) return;
            Aggro = true;
            // Share aggro within the encounter (prototype Game.onEnemyAggro).
            if (!string.IsNullOrEmpty(EncounterId))
                for (int i = 0; i < all.Count; i++)
                {
                    var x = all[i];
                    if (x != null && x != this && x.Alive && !x.Aggro && x.EncounterId == EncounterId) x.SetAggro();
                }
            Bus.Emit(new EnemyAggro { Id = Id, Type = Type });
            if (State is EnemyState.Idle or EnemyState.Patrol or EnemyState.Return) Enter(EnemyState.Alert);
        }

        public void Enter(EnemyState s)
        {
            State = s;
            stateT = 0f;
        }

        protected bool RequestToken()
        {
            if (hasToken) return true;
            hasToken = EnemyHost.RequestToken(this);
            return hasToken;
        }

        protected void ReleaseToken()
        {
            if (hasToken) EnemyHost.ReleaseToken(this);
            hasToken = false;
        }

        // ------------------------------------------------------------------ Perception / targets

        protected virtual Vector3 Eye => position + Vector3.up * (Height * 0.85f);

        void PickTarget()
        {
            var pl = EnemyHost.Player;
            var co = EnemyHost.Companion;
            bool pOk = CombatSystem.IsLive(pl);
            bool cOk = CombatSystem.IsLive(co) && !ReferenceEquals(co, pl);
            IDamageable pick;
            if (pOk && cOk)
            {
                // Prefer the controlled hero; switch to the partner only when it is clearly closer (with hysteresis).
                float dp = Vector3.Distance(position, pl.Position), dc = Vector3.Distance(position, co.Position);
                bool pT = pl.Targetable, cT = co.Targetable;
                if (!pT && cT) pick = co;
                else if (!cT) pick = pl;
                else if (ReferenceEquals(Target, co)) pick = dc < dp * 1.25f + 1f ? co : pl;
                else pick = dc < dp * 0.6f && dc < 10f ? co : pl;
            }
            else pick = pOk ? pl : cOk ? co : null;
            Target = pick;
        }

        void Perceive(float dt)
        {
            seeT -= dt;
            if (seeT > 0f) return;
            seeT = 0.22f;
            PickTarget();
            var p = Target;
            if (p == null || !p.Targetable)
            {
                CanSeeTarget = false;
                return;
            }
            float d = Vector3.Distance(position, p.Position);
            if (d > Def.Sight * (Aggro ? 1.5f : 1f))
            {
                CanSeeTarget = false;
                return;
            }
            // Non-alert enemies only see in a forward cone (unless very close).
            if (!Aggro && d > 6f && !Flying && CombatMath.FacingAngle(position, yaw, p.Position) > 1.4f)
            {
                CanSeeTarget = false;
                return;
            }
            CanSeeTarget = CombatSystem.LineOfSight(Eye, p.AimPoint);
            if (CanSeeTarget) lastSeen = 0f;
        }

        void UpdateTargetVelocity(float dt)
        {
            var t = Target;
            if (!CombatSystem.IsLive(t))
            {
                velTarget = null;
                targetVel = Vector3.zero;
                return;
            }
            if (!ReferenceEquals(t, velTarget))
            {
                velTarget = t;
                velTargetCC = t is Component c && c != null ? c.GetComponent<CharacterController>() : null;
                velLastPos = t.Position;
                targetVel = Vector3.zero;
                return;
            }
            Vector3 p = t.Position;
            Vector3 v = velTargetCC != null && velTargetCC.enabled ? velTargetCC.velocity : (p - velLastPos) / Mathf.Max(dt, 1e-4f);
            velLastPos = p;
            if (v.sqrMagnitude > 400f) v = v.normalized * 20f; // teleports / respawns
            targetVel = Vector3.Lerp(targetVel, v, 1f - Mathf.Exp(-10f * dt));
        }

        /// <summary>Estimated velocity of the current target (drones lead their shots with it).</summary>
        protected Vector3 TargetVelocity => targetVel;

        /// <summary>Facing of a target in radians (from its transform), 0 if unknown.</summary>
        protected static float TargetYaw(IDamageable t) => t is Component c && c != null ? c.transform.eulerAngles.y * Mathf.Deg2Rad : 0f;

        // ------------------------------------------------------------------ Update

        void Update()
        {
            float dt = Time.deltaTime;
            if (dt <= 0f || Def == null || disposed) return;
            if (freezeT > 0f)
            {
                freezeT -= Time.unscaledDeltaTime;
                if (freezeT < Time.unscaledDeltaTime * 0.5f) freezeT = 0f;
            }
            if (freezeT > 0f)
            {
                // Hit-stop: hold the pose (hit flash stays lit) and shudder along the blow.
                freezePhase += Time.unscaledDeltaTime;
                if (visual != null)
                {
                    float k = Mathf.Clamp01(freezeT / freezeDur);
                    Vector3 shake = transform.InverseTransformDirection(freezeDir) * (Mathf.Sin(freezePhase * 95f) * freezeAmp * k);
                    visual.localPosition = VisualLocal() + shake;
                }
                return;
            }
            if (Frozen || FreezeAll)
            {
                TickFeel(dt);
                UpdateModelOnly(dt);
                return;
            }
            Tick(dt);
        }

        void Tick(float dt)
        {
            stateT += dt;
            SinceHit += dt;
            lastSeen += dt;
            TickFeel(dt);
            if (State == EnemyState.Dead)
            {
                deathT += dt;
                // Corpses keep the blow's momentum for a moment (slide + launch arc).
                if (!Flying && !IsBoss && velocity.sqrMagnitude > 0.01f)
                {
                    velocity *= Mathf.Exp(-4f * dt);
                    velocity.y = 0f;
                    Integrate(dt);
                }
                UpdateDead(dt);
                SyncModel();
                UpdateModel(dt);
                return;
            }
            if (stunT > 0f)
            {
                stunT -= dt;
                velocity *= Mathf.Exp(-6f * dt);
                Integrate(dt);
                SyncModel();
                UpdateModel(dt);
                return;
            }
            if (Target != null && !CombatSystem.IsLive(Target)) PickTarget();
            UpdateTargetVelocity(dt);
            Perceive(dt);
            if (CanSeeTarget && !Aggro) SetAggro();
            // Leash: lose interest when the target leaves the area for a while.
            if (Aggro)
            {
                var p = Target;
                if (p == null)
                {
                    noTargetT += dt;
                    if (noTargetT > 1f) DropAggro();
                }
                else
                {
                    noTargetT = 0f;
                    float fromHome = CombatMath.DistXZ(p.Position, hasArena ? arenaCenter : home);
                    float limit = hasArena ? arenaRadius + 8f : Leash;
                    if ((fromHome > limit && lastSeen > 2.5f) || !p.Alive || lastSeen > 14f) DropAggro();
                }
            }
            if (State != EnemyState.Stagger) Poise = Mathf.Min(MaxPoise, Poise + MaxPoise * 0.12f * dt);
            UpdateAI(dt);
            SyncModel();
            UpdateModel(dt);
        }

        /// <summary>Launch arc, flinch spring, telegraph ramp/glint and the broken-poise sparking.</summary>
        void TickFeel(float dt)
        {
            if (airY > 0f || airVy > 0f)
            {
                airVy += Gravity * dt;
                airY += airVy * dt;
                if (airY <= 0f)
                {
                    bool hard = airVy < -5f;
                    airY = 0f;
                    airVy = 0f;
                    if (hard)
                    {
                        // Knockdown landing.
                        FxKit.Smoke(position + Vector3.up * 0.1f, 5, 0x5a5f66u, 0.8f);
                        FxKit.Sparks(position + Vector3.up * 0.1f, Vector3.up, 10, 0xffb060u, 4f);
                        FxKit.Sfx("land", position, 0.9f);
                        if (Alive && Rig != null && Rig.Anim != null) Rig.Anim.Jolt(1f, 1f);
                    }
                }
            }
            // Critically damped-ish spring back from the flinch push.
            flinchVel += (-flinch * 160f - flinchVel * 18f) * dt;
            flinch += flinchVel * dt;
            if (flinch.sqrMagnitude > 0.09f) flinch = flinch.normalized * 0.3f;
            if (teleLead > 0f && Alive && Rig != null)
            {
                float remain = threatAt - Time.time;
                if (remain > 0f)
                {
                    float k = 1f - Mathf.Clamp01(remain / teleLead);
                    Rig.Telegraph = 0.3f + 0.7f * k * k;
                    if (!glinted && remain <= 0.2f)
                    {
                        // Readable "about to strike" glint, timed for a perfect dodge.
                        glinted = true;
                        Vector3 g = GlintPoint;
                        FxKit.FlashSprite(g, IsBoss ? 3.2f : 1.5f, 0xfff0d0u, 0.16f);
                        FxKit.Light(g, 0xffb070u, 20f, 0.18f);
                        FxKit.Sfx("enemy_glint", g, 0.8f);
                    }
                }
                else teleLead = 0f;
            }
            if (State == EnemyState.Stagger && brokenStagger && Alive)
            {
                breakFxT -= dt;
                if (breakFxT <= 0f)
                {
                    breakFxT = 0.16f + Random.value * 0.12f;
                    FxKit.Sparks(AimPoint + Random.insideUnitSphere * Radius * 0.6f, null, 4, 0x9fe0ffu, 3.5f);
                    if (Rig != null) Rig.HitFlash(0.35f);
                }
            }
            else if (State != EnemyState.Stagger) brokenStagger = false;
        }

        /// <summary>Direction * speed of the last blow (debris and corpses fly with it).</summary>
        protected Vector3 LastKnock => lastHitDir * (lastHitKind == HitKind.Heavy || lastHitKind == HitKind.Ultimate ? 4.5f : 2.5f);

        /// <summary>Where the wind-up glint flashes (head / eye).</summary>
        protected virtual Vector3 GlintPoint
        {
            get
            {
                var head = Rig != null ? Rig.Bone("head") : null;
                return head != null ? head.position + Forward * 0.2f : Eye + Forward * 0.25f;
            }
        }

        /// <summary>Local position of the visual root: cinematic offset, death sink, launch height and flinch push.</summary>
        protected Vector3 VisualLocal()
        {
            Vector3 push = transform != null ? transform.InverseTransformDirection(flinch) : flinch;
            return new Vector3(push.x, VisualOffsetY - deathSink + airY, push.z);
        }

        void DropAggro()
        {
            Aggro = false;
            noTargetT = 0f;
            ReleaseToken();
            Enter(EnemyState.Return);
        }

        /// <summary>Animate without thinking (cinematics).</summary>
        public void UpdateModelOnly(float dt)
        {
            SyncModel();
            UpdateModel(dt);
        }

        protected abstract void UpdateAI(float dt);

        protected virtual void UpdateModel(float dt)
        {
            if (Rig != null) Rig.Tick(dt);
        }

        protected virtual void UpdateDead(float dt)
        {
            if (deathT > 4f) Dispose();
        }

        protected virtual void SyncModel()
        {
            if (mode != MoveMode.Controller) transform.position = position;
            transform.rotation = Quaternion.Euler(0f, yaw * Mathf.Rad2Deg, 0f);
            if (visual != null) visual.localPosition = VisualLocal();
        }

        // ------------------------------------------------------------------ Movement

        /// <summary>Move by the current velocity (gravity for ground enemies, NavMesh-constrained when on one).</summary>
        protected void Integrate(float dt)
        {
            switch (mode)
            {
                case MoveMode.Agent:
                {
                    Vector3 delta = KeepOutOfActors(new Vector3(velocity.x, 0f, velocity.z) * dt);
                    if (agent != null && agent.isOnNavMesh)
                    {
                        agent.Move(delta);
                        position = agent.nextPosition;
                    }
                    else position += delta;
                    velocity.y = 0f;
                    break;
                }
                case MoveMode.Controller:
                    velocity.y += Gravity * dt;
                    if (cc != null && cc.enabled)
                    {
                        var flags = cc.Move(velocity * dt);
                        if ((flags & CollisionFlags.Below) != 0 && velocity.y < 0f) velocity.y = -1f;
                        position = transform.position;
                    }
                    break;
                default:
                    if (Flying)
                    {
                        position += velocity * dt;
                        return;
                    }
                    // Physics-free ground movement with ground snap.
                    position += KeepOutOfActors(new Vector3(velocity.x, 0f, velocity.z) * dt);
                    var g = EnemyHost.GroundAt(position + Vector3.up * 1.5f, 4f);
                    if (g.HasValue) position.y = g.Value;
                    break;
            }
            if (position.y < home.y - 50f) TeleportHome();
        }

        /// <summary>
        /// Non-physics movers (NavMesh agent / kinematic) do not collide with the heroes' CharacterControllers,
        /// so clamp the step to stay outside their capsules (what the prototype's character bodies did).
        /// </summary>
        Vector3 KeepOutOfActors(Vector3 delta)
        {
            Vector3 next = position + delta;
            for (int i = 0; i < 2; i++)
            {
                var t = i == 0 ? EnemyHost.Player : EnemyHost.Companion;
                if (!CombatSystem.IsLive(t)) continue;
                Vector3 tp = t.Position;
                if (Mathf.Abs(next.y - tp.y) > Height) continue;
                Vector3 d = next - tp;
                d.y = 0f;
                float minD = Radius + t.Radius;
                float m = d.magnitude;
                if (m >= minD) continue;
                Vector3 n = m > 1e-4f ? d / m : -Forward;
                next += n * (minD - m);
            }
            return next - position;
        }

        /// <summary>Move instantly (cinematics / recovery). Keeps NavMesh and CharacterController in sync.</summary>
        public void Teleport(Vector3 p)
        {
            position = p;
            if (mode == MoveMode.Agent && agent != null && agent.isOnNavMesh)
            {
                agent.Warp(p);
                position = agent.nextPosition;
            }
            else if (mode == MoveMode.Controller && cc != null)
            {
                bool was = cc.enabled;
                cc.enabled = false;
                transform.position = p;
                cc.enabled = was;
            }
            transform.position = position;
            lastPos = position;
            cornerCount = 0;
        }

        public void TeleportHome()
        {
            stuckT = 0f;
            velocity = Vector3.zero;
            Teleport(home);
            yaw = homeYaw;
        }

        /// <summary>
        /// Ground steering toward a goal (port of steerTo): NavMesh path corners when available, otherwise feeler
        /// rays, plus separation from other enemies and side-steps / teleport-home when stuck. Returns the remaining
        /// horizontal distance.
        /// </summary>
        protected float SteerTo(Vector3 goal, float speed, float dt, float accel = 8f, bool face = true)
        {
            Vector3 to = goal - position;
            to.y = 0f;
            float dist = to.magnitude;
            Vector3 dir = dist > 0.001f ? to / dist : Vector3.zero;
            if (dist > 0.3f && !Flying)
            {
                bool pathed = mode == MoveMode.Agent && dist > 1f && PathDirection(goal, dt, ref dir);
                if (!pathed)
                {
                    // Feelers
                    Vector3 origin = position + Vector3.up * (Height * 0.4f);
                    if (Physics.Raycast(origin, dir, 1.6f, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore))
                    {
                        Vector3 left = Quaternion.AngleAxis(-0.8f * Mathf.Rad2Deg, Vector3.up) * dir;
                        Vector3 right = Quaternion.AngleAxis(0.8f * Mathf.Rad2Deg, Vector3.up) * dir;
                        bool hl = Physics.Raycast(origin, left, out var hitL, 2.2f, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore);
                        bool hr = Physics.Raycast(origin, right, out var hitR, 2.2f, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore);
                        dir = (!hl ? left : !hr ? right : (hitL.distance > hitR.distance ? left : right)).normalized;
                    }
                }
                // Separation from other enemies
                for (int i = 0; i < all.Count; i++)
                {
                    var c = all[i];
                    if (c == null || c == this || !c.Alive) continue;
                    float d = CombatMath.DistXZ(c.position, position);
                    if (d < 1.6f && d > 0.01f)
                    {
                        dir.x += ((position.x - c.position.x) / d) * (1.6f - d) * 0.8f;
                        dir.z += ((position.z - c.position.z) / d) * (1.6f - d) * 0.8f;
                    }
                }
                if (sideStepT > 0f)
                {
                    sideStepT -= dt;
                    dir = Quaternion.AngleAxis(sideStepDir * 1.2f * Mathf.Rad2Deg, Vector3.up) * dir;
                }
                dir.y = 0f;
                dir = dir.sqrMagnitude > 1e-6f ? dir.normalized : Vector3.zero;
            }
            float want = dist > 0.25f ? speed : 0f;
            velocity.x = CombatMath.Damp(velocity.x, dir.x * want, accel, dt);
            velocity.z = CombatMath.Damp(velocity.z, dir.z * want, accel, dt);
            if (face && want > 0.2f && dir.sqrMagnitude > 1e-6f) yaw = CombatMath.DampAngle(yaw, Mathf.Atan2(dir.x, dir.z), 8f, dt);
            Integrate(dt);
            // Stuck detection
            float moved = CombatMath.DistXZ(position, lastPos);
            lastPos = position;
            if (want > 0.5f && moved < want * dt * 0.15f)
            {
                stuckT += dt;
                if (stuckT > 1f && sideStepT <= 0f)
                {
                    sideStepT = 0.8f;
                    sideStepDir = Random.value < 0.5f ? -1f : 1f;
                    cornerCount = 0;
                }
                if (stuckT > 4f && !EnemyHost.CameraSees(position)) TeleportHome();
            }
            else stuckT = Mathf.Max(0f, stuckT - dt * 2f);
            return dist;
        }

        bool PathDirection(Vector3 goal, float dt, ref Vector3 dir)
        {
            repathT -= dt;
            if (repathT <= 0f || (goal - pathGoal).sqrMagnitude > 1f)
            {
                repathT = 0.35f;
                pathGoal = goal;
                cornerCount = 0;
                Vector3 target = goal;
                if (NavMesh.SamplePosition(goal, out var gh, 3f, NavMesh.AllAreas)) target = gh.position;
                Vector3 from = agent != null && agent.isOnNavMesh ? agent.nextPosition : position;
                if (NavMesh.CalculatePath(from, target, NavMesh.AllAreas, path) && path.status != NavMeshPathStatus.PathInvalid)
                {
                    cornerCount = path.GetCornersNonAlloc(corners);
                    cornerIdx = 1;
                }
            }
            if (cornerCount < 2) return false;
            while (cornerIdx < cornerCount - 1 && CombatMath.DistXZ(position, corners[cornerIdx]) < 0.6f) cornerIdx++;
            if (cornerIdx >= cornerCount) return false;
            Vector3 c = corners[cornerIdx] - position;
            c.y = 0f;
            if (c.sqrMagnitude < 1e-4f) return false;
            dir = c.normalized;
            return true;
        }

        /// <summary>Return-home behaviour shared by all ground enemies (heals 20%/s, teleports after 10 s).</summary>
        protected void UpdateReturn(float dt, float speed)
        {
            float d = SteerTo(home, speed, dt);
            Health = Mathf.Min(MaxHealth, Health + MaxHealth * 0.2f * dt);
            if (d < 1f || stateT > 10f)
            {
                if (d >= 1f) TeleportHome();
                Enter(EnemyState.Idle);
            }
            if (CanSeeTarget) SetAggro();
        }

        /// <summary>Absolute angle (radians) between our facing and a point.</summary>
        public float FacingTo(Vector3 p) => CombatMath.FacingAngle(position, yaw, p);

        protected float YawTo(Vector3 p) => CombatMath.YawTo(position, p);

        protected Vector3 Forward => CombatMath.YawDir(yaw);

        // ------------------------------------------------------------------ Attacks

        /// <summary>Damage opposing actors in an arc in front of this enemy (once per hitSet).</summary>
        protected int MeleeArc(float range, float halfAngle, float damage, float poise, float knock, HashSet<IDamageable> hitSet)
        {
            var cs = CombatSystem.Ensure();
            Vector3 origin = position + Vector3.up * (Height * 0.5f);
            var template = new HitInfo { Damage = damage, Poise = poise, Kind = HitKind.Enemy, Source = this };
            return cs.ArcDamage(Team.Enemy, origin, yaw * Mathf.Rad2Deg, range, halfAngle * Mathf.Rad2Deg, template, knock, hitSet, -2f, 2.5f, meleeFx);
        }

        void OnMeleeApplied(IDamageable target, Vector3 point, float applied)
        {
            Vector3 dir = target.Position - position;
            dir.y = 0f;
            FxKit.Sparks(point, dir.sqrMagnitude > 1e-6f ? dir.normalized : (Vector3?)null, 10, 0xff6a4au, 6f);
            FxKit.Sfx("enemy_hit_player", point);
        }

        /// <summary>Hit a single target; returns true when the damage landed.</summary>
        protected bool HitTarget(IDamageable t, float damage, float poise, Vector3 knock, Vector3 point, bool pierce = false)
            => CombatSystem.TryHit(t, new HitInfo { Damage = damage, Poise = poise, Knock = knock, Kind = HitKind.Enemy, Point = point, Source = this, Pierce = pierce });

        /// <summary>Player and companion (when alive), for area attacks that are not physics queries (waves, laser).</summary>
        protected int Victims(IDamageable[] buffer)
        {
            int n = 0;
            var p = EnemyHost.Player;
            var c = EnemyHost.Companion;
            if (CombatSystem.IsLive(p)) buffer[n++] = p;
            if (CombatSystem.IsLive(c) && !ReferenceEquals(c, p)) buffer[n++] = c;
            return n;
        }

        protected float Aggression => EnemyHost.Difficulty.Aggression;

        // ------------------------------------------------------------------ Animation helpers

        /// <summary>Play a named robot clip (cinematics, e.g. the guardian 'roar'). Returns false if unknown.</summary>
        public virtual bool PlayAnimation(string clip, float fadeIn = 0.2f)
        {
            if (Rig == null || Rig.Anim == null || Clips == null || !Clips.TryGetValue(clip, out var c)) return false;
            Rig.Anim.Play(c, fadeIn);
            return true;
        }

        // ------------------------------------------------------------------ Disposal

        /// <summary>Destroy the enemy (after its death animation).</summary>
        protected void Dispose()
        {
            if (disposed) return;
            disposed = true;
            ReleaseToken();
            Destroy(gameObject);
        }

        public bool Disposed => disposed;

        /// <summary>Remove immediately without death effects (encounter despawn, zone unload).</summary>
        public void Despawn() => Dispose();

        protected virtual void OnDestroy()
        {
            ReleaseToken();
            all.Remove(this);
        }
    }
}
