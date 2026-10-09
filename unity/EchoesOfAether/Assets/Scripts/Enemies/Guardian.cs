using System;
using System.Collections.Generic;
using UnityEngine;
using Random = UnityEngine.Random;

namespace EOA
{
    /// <summary>
    /// Aether Guardian boss (port of Guardian.ts). Armoured everywhere except its core, which opens for 3.4 s after a
    /// slam (2.4x damage near the core / bolts / pulse / ultimate, otherwise 1.2x; armoured: 0.18 light, 0.35 heavy/pulse,
    /// 0.7 ultimate). Slams send out ground shockwave rings the player must jump over.
    /// Phase 1 (&gt;66% hp): slams + sweeps. Phase 2: chest laser, summons 2 drones. Phase 3 (&lt;33%): faster, summons
    /// 2 stalkers. Each phase change roars (ring + summons) and emits Bus BossPhase.
    /// The 'guardian_vault' variant cannot be harmed: survive until the blast door opens.
    /// </summary>
    public sealed class Guardian : Enemy
    {
        bool vault;
        int phase = 1;
        float attackCd = 2.5f;
        readonly HashSet<IDamageable> hitSet = new();
        bool hitActive;
        float curSpeed = 1f;
        string current;
        float exposedT;
        CombatBeam laser;
        bool laserOn;
        float laserTick;
        float sparkAcc;
        float deathBoomAcc;
        bool summonedP2, summonedP3, announced;
        float noEffectT;
        readonly IDamageable[] victims = new IDamageable[2];
        Action<string> onAttackEvent;
        Action onAttackEnd;
        EnemyWeaponFx weapons;

        sealed class Wave
        {
            public bool Active;
            public float R, MaxR, Speed;
            public Vector3 Center;
            public GameObject Go;
            public Material Mat;
            public readonly HashSet<IDamageable> Hit = new();
        }

        readonly List<Wave> waves = new();

        readonly List<Vector3> plateBase = new();
        readonly List<Vector3> plateOut = new();

        public bool VaultMode => vault;
        public int Phase => phase;
        public override int BossPhaseNumber => phase;
        /// <summary>Seconds left in the exposed-core window (0 when armoured).</summary>
        public float ExposedTime => exposedT;

        protected override void Configure()
        {
            vault = Variant == "guardian_vault";
            Height = 5.2f;
            Radius = 1.3f;
            Leash = 200f;
            Rig = RobotRig.Create(visual, RobotKind.Guardian, new RobotPalette(0x3a3f48, 0x1c1f24, vault ? 0xff5a3au : 0x5fd8ffu, 3.6f),
                                  vault ? "guardian_vault" : "guardian", vault ? "guardian" : null);
            Clips = RobotClips.Get(RobotClips.Kind.Guardian);
            weapons = EnemyWeaponFx.Attach(this, Rig, EnemyWeaponFx.Kind.Guardian);
            onAttackEvent = OnAttackEvent;
            onAttackEnd = OnAttackEnd;
            laser = CombatSystem.Ensure().CreateBeam(CombatMath.Hex(0xff3a2e), 0.44f);
            laser.Visible = false;
            if (vault)
            {
                MaxHealth = 99999f;
                Health = 99999f;
            }
            // Core plates slide sideways (away from the core) while exposed.
            foreach (var pl in Rig.Plates)
            {
                plateBase.Add(pl.localPosition);
                Vector3 outward = Vector3.zero;
                if (Rig.Core != null && Rig.Core.parent == pl.parent) outward = pl.localPosition - Rig.Core.localPosition;
                outward.y = 0f;
                outward.z = 0f;
                if (outward.sqrMagnitude < 1e-6f) outward = pl.name.EndsWith("_R", StringComparison.Ordinal) ? Vector3.right : Vector3.left;
                plateOut.Add(outward.normalized);
            }
        }

        protected override void OnSpawned() => SetAggro();

        public override Vector3 AimPoint => Rig != null && Rig.Core != null ? Rig.Core.position : base.AimPoint;

        protected override float DamageTakenMul(HitInfo h)
        {
            if (vault)
            {
                if (noEffectT <= 0f)
                {
                    noEffectT = 4f;
                    EnemyHost.Toast("It shrugs it off. Survive until the blast door opens!", ToastKind.Warn);
                }
                return 0f;
            }
            Vector3 corePos = AimPoint;
            bool nearCore = Vector3.Distance(h.Point, corePos) < 1.6f || h.Kind == HitKind.Bolt;
            if (exposedT > 0f) return nearCore || h.Kind == HitKind.Pulse || h.Kind == HitKind.Ultimate ? 2.4f : 1.2f;
            // Armoured: light hits barely scratch it, ultimates and heavies do more.
            return h.Kind == HitKind.Ultimate ? 0.7f : h.Kind == HitKind.Heavy || h.Kind == HitKind.Pulse ? 0.35f : 0.18f;
        }

        protected override void OnHurt(HitInfo h, float dmg)
        {
            Rig.HitFlash(exposedT > 0f ? 1f : 0.35f);
            FxKit.Sfx(exposedT > 0f ? "hit_heavy" : "shield_block", h.Point);
            if (exposedT <= 0f) FxKit.Sparks(h.Point, null, 6, 0xffd0a0u, 4f);
            float f = Health / MaxHealth;
            int newPhase = f < 0.33f ? 3 : f < 0.66f ? 2 : 1;
            if (newPhase > phase)
            {
                phase = newPhase;
                Bus.Emit(new BossPhase { Id = "guardian", Phase = newPhase });
                attackCd = 0.5f;
                QueueRoar();
            }
        }

        // Bosses don't stagger from poise; they are only exposed after slams.
        protected override void Stagger(HitInfo h) => Poise = MaxPoise;

        protected override void Die(HitInfo? h)
        {
            base.Die(h);
            weapons?.Hide();
            weapons?.Deploy(false);
            laserOn = false;
            laser?.SetVisibleSafe(false);
            foreach (var w in waves) Deactivate(w);
            Rig.Telegraph = 0f;
            Rig.Anim.StopActions(0.1f);
            Rig.Anim.SetState(Clips["death"], 0.2f);
            FxKit.Sfx("sentinel_death", position);
            EnemyHost.SetBoss(false);
        }

        protected override void UpdateDead(float dt)
        {
            if (deathT < 2.4f)
            {
                deathBoomAcc += dt * 21f;
                while (deathBoomAcc >= 1f)
                {
                    deathBoomAcc -= 1f;
                    FxKit.Explode(position + new Vector3((Random.value - 0.5f) * 3f, 1f + Random.value * 3f, (Random.value - 0.5f) * 3f), 0.6f, 0x5fd8ff);
                }
            }
            if (deathT > 2.4f && deathT - dt <= 2.4f)
            {
                FxKit.Explode(position + Vector3.up * 2f, 3f, 0x5fd8ff);
                FxKit.Sfx("robot_break", position);
                HitFx.BreakApart(Rig, position + Vector3.up * Height * 0.4f, Vector3.zero, 9f, 16, CombatMath.Hex(0x7fd8ff));
                FxKit.Sfx("ult_impact", position);
                FxKit.Shake(0.9f);
            }
            if (deathT > 3f) deathSink = (deathT - 3f) * 1.2f;
            if (deathT > 6f) Dispose();
        }

        void QueueRoar()
        {
            if (current != null || State == EnemyState.Dead) return;
            StartAttack("roar");
        }

        void StartAttack(string kind)
        {
            current = kind;
            Enter(EnemyState.Attack);
            hitSet.Clear();
            hitActive = false;
            float speed = (phase == 3 ? 1.25f : phase == 2 ? 1.1f : 1f) * Mathf.Min(1.2f, Aggression);
            curSpeed = speed;
            Rig.Anim.Play(Clips[kind], 0.15f, 0.15f, speed, onAttackEvent, onAttackEnd);
        }

        void OnAttackEnd()
        {
            hitActive = false;
            weapons?.SetSwing(false);
            weapons?.Deploy(false);
            Rig.Telegraph = 0f;
            EndThreat();
            laserOn = false;
            laser?.SetVisibleSafe(false);
            string was = current;
            current = null;
            if (State == EnemyState.Dead) return;
            if (was == "slam" && !vault)
            {
                // Exposed window.
                exposedT = 3.4f;
                Enter(EnemyState.Special);
                Rig.Anim.Play(Clips["exposed"], 0.15f);
                FxKit.Sfx("door", position);
            }
            else Enter(EnemyState.Recover);
        }

        void OnAttackEvent(string e)
        {
            switch (e)
            {
                case "telegraph":
                {
                    var clip = Clips[current ?? "sweep"];
                    string to = current == "laser" ? "laser_on" : "hit_start";
                    BeginThreat(EventGap(clip, "telegraph", to, curSpeed), current == "laser" ? 0.4f : EventGap(clip, "hit_start", "hit_end", curSpeed) + 0.1f);
                    FxKit.Sfx("enemy_telegraph", position);
                    if (current == "sweep") weapons?.Deploy(true);
                    else if (current == "laser" && weapons?.CannonMuzzle != null) FxKit.Sfx("cannon_charge", weapons.CannonMuzzle.position);
                    break;
                }
                case "hit_start":
                    hitActive = true;
                    if (current == "sweep") weapons?.SetSwing(true);
                    ThreatActive(0.3f);
                    break;
                case "hit_end":
                    hitActive = false;
                    weapons?.SetSwing(false);
                    Rig.Telegraph = 0f;
                    EndThreat();
                    break;
                case "impact":
                {
                    Vector3 center = position + new Vector3(Mathf.Sin(yaw) * 2.8f, 0.1f, Mathf.Cos(yaw) * 2.8f);
                    // Close-range impact
                    var hit = new HitInfo { Damage = Def.Damage * 1.2f, Poise = 60f, Kind = HitKind.Enemy, Source = this };
                    CombatSystem.Ensure().RadialDamage(Team.Enemy, center, 3.6f, hit, 10f, null, 2f);
                    SpawnWave(center, phase >= 2 ? 16f : 13f);
                    FxKit.Sparks(center, Vector3.up, 50, 0xffc080u, 10f);
                    FxKit.Light(center + Vector3.up, 0xff9a50, 80f, 0.4f);
                    FxKit.Shake(0.6f);
                    FxKit.Sfx("slam", center);
                    break;
                }
                case "laser_on":
                    laserOn = true;
                    laser?.SetVisibleSafe(true);
                    if (weapons?.CannonMuzzle != null)
                        WeaponFx.Muzzle(weapons.CannonMuzzle.position, weapons.CannonMuzzle.forward, CombatMath.Hex(0xff5a3a), 1.6f);
                    FxKit.Sfx("ult_charge", position);
                    break;
                case "laser_off":
                    laserOn = false;
                    laser?.SetVisibleSafe(false);
                    break;
                case "roar":
                    FxKit.Sfx("ult_charge", position);
                    FxKit.Shake(0.4f);
                    SpawnWave(position + Vector3.up * 0.1f, 18f);
                    if (!vault)
                    {
                        if (phase >= 2 && !summonedP2)
                        {
                            summonedP2 = true;
                            for (int a = -1; a <= 1; a += 2) EnemyHost.SpawnMinion("drone", position + new Vector3(a * 8f, 6f, 0f), EncounterId);
                        }
                        else if (phase >= 3 && !summonedP3)
                        {
                            summonedP3 = true;
                            for (int a = -1; a <= 1; a += 2) EnemyHost.SpawnMinion("stalker", position + new Vector3(a * 9f, 0f, 4f), EncounterId);
                        }
                    }
                    break;
            }
        }

        // ------------------------------------------------------------------ Shockwave rings

        void SpawnWave(Vector3 center, float maxR)
        {
            Wave w = null;
            foreach (var x in waves) if (!x.Active) { w = x; break; }
            if (w == null)
            {
                w = new Wave();
                w.Go = new GameObject("GuardianWave");
                w.Go.layer = CombatLayers.Default;
                w.Go.transform.SetParent(transform.parent, false);
                w.Go.AddComponent<MeshFilter>().sharedMesh = FxMesh.TorusFlat(1f, 0.08f, 6, 64);
                var mr = w.Go.AddComponent<MeshRenderer>();
                w.Mat = FxMaterials.Particle(true, FxMaterials.White, true);
                mr.sharedMaterial = w.Mat;
                mr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
                mr.receiveShadows = false;
                waves.Add(w);
            }
            w.Active = true;
            w.R = 1f;
            w.MaxR = maxR;
            w.Speed = 11f;
            w.Center = center;
            w.Hit.Clear();
            w.Go.transform.SetPositionAndRotation(center + Vector3.up * 0.25f, Quaternion.identity);
            w.Go.transform.localScale = Vector3.one;
            var c = FxMaterials.Hdr(CombatMath.Hex(vault ? 0xff5a3au : 0x5fd8ffu), 2.2f);
            c.a = 0.9f;
            w.Mat.SetColor("_BaseColor", c);
            w.Go.SetActive(true);
        }

        static void Deactivate(Wave w)
        {
            w.Active = false;
            if (w.Go != null) w.Go.SetActive(false);
        }

        void UpdateWaves(float dt)
        {
            int n = Victims(victims);
            foreach (var w in waves)
            {
                if (!w.Active) continue;
                w.R += w.Speed * dt;
                w.Go.transform.localScale = new Vector3(w.R, 1f, w.R);
                FxMaterials.SetAlpha(w.Mat, Mathf.Max(0f, 1f - w.R / w.MaxR));
                for (int i = 0; i < n; i++)
                {
                    var v = victims[i];
                    if (w.Hit.Contains(v)) continue;
                    float d = CombatMath.DistXZ(v.Position, w.Center);
                    // Jump (or phase) over the ring to avoid it.
                    bool airborne = v.Position.y > w.Center.y + 0.55f;
                    if (Mathf.Abs(d - w.R) < 0.7f && !airborne)
                    {
                        w.Hit.Add(v);
                        Vector3 dir = v.Position - w.Center;
                        dir.y = 0f;
                        dir = dir.sqrMagnitude > 1e-6f ? dir.normalized : Vector3.forward;
                        HitTarget(v, Def.Damage * 0.6f, 40f, dir * 6f, v.Position);
                    }
                }
                if (w.R >= w.MaxR) Deactivate(w);
            }
        }

        // ------------------------------------------------------------------ Chest laser

        void UpdateLaser(float dt)
        {
            if (!laserOn || laser == null) return;
            Vector3 from = AimPoint;
            Vector3 hf = Rig.Anim != null ? Rig.PoseForward(RobotRig.Hips) : Forward;
            float hy = Mathf.Atan2(hf.x, hf.z);
            Vector3 dir = new Vector3(Mathf.Sin(hy), -0.18f, Mathf.Cos(hy)).normalized;
            float len = 40f;
            Vector3 end = from + dir * len;
            bool struck = Physics.Raycast(from, dir, out var hit, 40f, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore);
            if (struck) end = hit.point;
            // The beam sweeps exactly where the core-level ray lands (same timing / path), but it now leaves the arm
            // cannon's muzzle: damage is tested along that visible segment.
            if (weapons?.CannonMuzzle != null)
            {
                from = weapons.CannonMuzzle.position;
                var seg = end - from;
                len = Mathf.Max(0.5f, seg.magnitude);
                dir = seg / len;
            }
            else len = struck ? hit.distance : len;
            if (struck)
            {
                sparkAcc += dt * 60f;
                while (sparkAcc >= 1f)
                {
                    sparkAcc -= 1f;
                    FxKit.Sparks(hit.point, hit.normal, 2, 0xff6a4au, 3f);
                }
            }
            laser.SetPoints(from, end);
            laser.SetPulse(1f + Mathf.Sin(Time.time * 40f) * 0.08f);
            laserTick -= dt;
            if (laserTick > 0f) return;
            int n = Victims(victims);
            for (int i = 0; i < n; i++)
            {
                var v = victims[i];
                if (CombatMath.RayDistance(from, dir, len, v.AimPoint) < 0.9f)
                {
                    laserTick = 0.15f;
                    HitTarget(v, Def.Damage * 0.22f, 5f, Vector3.zero, v.Position);
                }
            }
        }

        // ------------------------------------------------------------------ AI

        void Brake(float rate, float dt)
        {
            float k = Mathf.Exp(-rate * dt);
            velocity.x *= k;
            velocity.z *= k;
        }

        protected override void UpdateAI(float dt)
        {
            var p = Target;
            attackCd -= dt;
            noEffectT -= dt;
            exposedT = Mathf.Max(0f, exposedT - dt);
            Rig.Anim.CombatStance = 1f;
            if (!announced && Aggro)
            {
                announced = true;
                if (!vault) EnemyHost.SetBoss(true);
            }
            // Core plates open while exposed.
            float open = exposedT > 0f ? 1f : 0f;
            for (int i = 0; i < Rig.Plates.Count && i < plateBase.Count; i++)
            {
                var pl = Rig.Plates[i];
                if (pl == null) continue;
                Vector3 target = plateBase[i] + plateOut[i] * (open * 0.16f * Rig.S);
                pl.localPosition += (target - pl.localPosition) * Mathf.Min(1f, dt * 8f);
            }
            Rig.SetCore(exposedT > 0f ? CombatMath.Hex(0xffe0a0) : CombatMath.Hex(vault ? 0xff5a3au : 0x5fd8ffu),
                        exposedT > 0f ? 4f + Mathf.Sin(stateT * 20f) : 3f);
            UpdateWaves(dt);
            UpdateLaser(dt);
            if (p == null || !p.Alive)
            {
                Brake(4f, dt);
                Integrate(dt);
                Rig.Anim.Speed = new Vector2(velocity.x, velocity.z).magnitude;
                return;
            }
            float speedMul = phase == 3 ? 1.3f : 1f;
            switch (State)
            {
                case EnemyState.Idle:
                case EnemyState.Alert:
                case EnemyState.Patrol:
                case EnemyState.Return:
                    Enter(EnemyState.Pursue);
                    break;
                case EnemyState.Pursue:
                {
                    float d = CombatMath.DistXZ(position, p.Position) - Radius - p.Radius;
                    yaw = CombatMath.DampAngle(yaw, YawTo(p.Position), 2.2f, dt);
                    if (attackCd <= 0f && FacingTo(p.Position) < 0.5f)
                    {
                        string kind;
                        if (d < 4.5f) kind = Random.value < 0.55f ? "slam" : "sweep";
                        else if (phase >= 2 && d < 26f && Random.value < 0.55f) kind = "laser";
                        else kind = d < 8f ? "slam" : "sweep";
                        if (kind != "laser" && d > 7f)
                        {
                            SteerTo(p.Position, Def.Speed * speedMul, dt, 4f, false);
                            break;
                        }
                        StartAttack(kind);
                        break;
                    }
                    if (d > 4f) SteerTo(p.Position, Def.Speed * speedMul, dt, 4f, false);
                    else
                    {
                        Brake(6f, dt);
                        Integrate(dt);
                    }
                    break;
                }
                case EnemyState.Attack:
                    if (current != "laser" && stateT < 0.5f) yaw = CombatMath.DampAngle(yaw, YawTo(p.Position), 3f, dt);
                    Brake(6f, dt);
                    Integrate(dt);
                    if (hitActive && current == "sweep") MeleeArc(Def.AttackRange, 70f * Mathf.Deg2Rad, Def.Damage, 50f, 9f, hitSet);
                    if (stateT > 5f)
                    {
                        current = null;
                        Enter(EnemyState.Recover);
                    }
                    break;
                case EnemyState.Special:
                    Brake(8f, dt);
                    Integrate(dt);
                    if (exposedT <= 0f)
                    {
                        attackCd = phase == 3 ? 0.8f : 1.6f;
                        Enter(EnemyState.Pursue);
                    }
                    break;
                case EnemyState.Recover:
                    Brake(8f, dt);
                    Integrate(dt);
                    if (stateT > (phase == 3 ? 0.4f : 0.9f))
                    {
                        attackCd = (phase == 3 ? 0.9f : 1.6f) / Aggression;
                        Enter(EnemyState.Pursue);
                    }
                    break;
                default:
                    Integrate(dt);
                    break;
            }
            Rig.Anim.Speed = new Vector2(velocity.x, velocity.z).magnitude;
        }

        protected override void OnDestroy()
        {
            base.OnDestroy();
            laser?.Dispose();
            laser = null;
            foreach (var w in waves)
            {
                if (w.Go != null) Destroy(w.Go);
                if (w.Mat != null) Destroy(w.Mat);
            }
            waves.Clear();
            EnemyHost.SetBoss(false);
        }
    }

    static class CombatBeamExtensions
    {
        /// <summary>Visible setter that tolerates a destroyed beam (combat system torn down first).</summary>
        public static void SetVisibleSafe(this CombatBeam b, bool on)
        {
            if (b != null) b.Visible = on;
        }
    }
}
