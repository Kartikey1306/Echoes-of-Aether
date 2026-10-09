using System;
using System.Collections.Generic;
using UnityEngine;
using Random = UnityEngine.Random;

namespace EOA
{
    /// <summary>
    /// Phase Stalker: fast melee hunter that phases out of reality to flank (port of Stalker.ts). While phased it is
    /// nearly invisible, untargetable and immune unless Echo Sight is active (<see cref="IWorld.EchoActive"/>).
    /// Sustained combos (3 hits within 1.2 s) make it phase away evasively.
    /// </summary>
    public sealed class Stalker : Enemy
    {
        float attackCd = 1.5f;
        float phaseCd;
        readonly HashSet<IDamageable> hitSet = new();
        bool hitActive;
        float slashSpeed = 1f;
        Vector3 phaseTarget;
        int recentHits;
        float recentT;
        float strafe;
        float emberAcc;
        bool hidden;
        Action<string> onAttackEvent;
        Action onAttackEnd;

        public bool Phased => State == EnemyState.Phase;

        protected override void Configure()
        {
            Height = 2.0f;
            Radius = 0.42f;
            phaseCd = 5f + Random.value * 3f;
            strafe = Random.value < 0.5f ? -1f : 1f;
            Rig = RobotRig.Create(visual, RobotKind.Stalker, new RobotPalette(0x2a2436, 0x141218, 0xb48cff, 3.2f), "stalker");
            Clips = RobotClips.Get(RobotClips.Kind.Stalker);
            onAttackEvent = OnAttackEvent;
            onAttackEnd = OnAttackEnd;
        }

        public override bool Targetable
        {
            get
            {
                if (!Alive || Invulnerable) return false;
                if (State == EnemyState.Phase) return EnemyHost.EchoActive;
                return true;
            }
        }

        protected override float DamageTakenMul(HitInfo h) => State == EnemyState.Phase && !EnemyHost.EchoActive ? 0f : 1f;

        protected override void OnHurt(HitInfo h, float dmg)
        {
            Rig.HitFlash(1f);
            FxKit.Sfx("enemy_hit_metal", h.Point);
            recentHits++;
            recentT = 1.2f;
            // Evade sustained combos by phasing away.
            if (recentHits >= 3 && phaseCd < 3f && State != EnemyState.Stagger) StartPhase(true);
        }

        protected override void Stagger(HitInfo h)
        {
            base.Stagger(h);
            hitActive = false;
            Rig.Telegraph = 0f;
            Rig.Opacity = 1f;
            var clip = Clips["stagger"];
            Rig.Anim.Play(clip, 0.05f, 0.15f, Mathf.Clamp(clip.Duration / Mathf.Max(0.1f, StaggerTime), 0.45f, 1f));
            FxKit.Sfx("enemy_stagger", position);
        }

        protected override void Die(HitInfo? h)
        {
            base.Die(h);
            hitActive = false;
            Rig.Telegraph = 0f;
            Rig.Opacity = 1f;
            Rig.Anim.StopActions(0.05f);
            Rig.Anim.SetState(Clips["death"], 0.1f);
            FxKit.Sfx("sentinel_death", position);
        }

        protected override void UpdateDead(float dt)
        {
            if (deathT > 0.8f && deathT - dt <= 0.8f)
            {
                FxKit.Explode(position + Vector3.up * 0.4f, 0.9f, 0xb48cff);
                FxKit.Sfx("explosion", position);
                FxKit.Sfx("robot_break", position, 0.8f);
                HitFx.BreakApart(Rig, position + Vector3.up * Height * 0.45f, LastKnock, 5f, 8, CombatMath.Hex(0xc890ff));
            }
            if (deathT > 1.0f && !hidden)
            {
                hidden = true;
                Rig.SetVisible(false);
            }
            if (deathT > 3.2f) Dispose();
        }

        void StartPhase(bool evasive)
        {
            var p = Target;
            if (p == null) return;
            ReleaseToken();
            hitActive = false;
            Rig.Telegraph = 0f;
            Enter(EnemyState.Phase);
            phaseCd = 6f + Random.value * 3f;
            recentHits = 0;
            // Destination: behind or beside the target.
            float ty = TargetYaw(p);
            Vector3 behind = new Vector3(Mathf.Sin(ty), 0f, Mathf.Cos(ty)) * (evasive ? -6f : -2.6f);
            Vector3 side = new Vector3(behind.z, 0f, -behind.x).normalized * ((Random.value - 0.5f) * 3f);
            phaseTarget = p.Position + behind + side;
            if (hasArena && CombatMath.DistXZ(phaseTarget, arenaCenter) > arenaRadius) phaseTarget = p.Position;
            FxKit.Embers(AimPoint, 18, 0xb48cffu, 0.8f, 1f);
            FxKit.Sfx("step", position);
        }

        void StartAttack()
        {
            Enter(EnemyState.Attack);
            hitSet.Clear();
            hitActive = false;
            slashSpeed = Mathf.Min(1.3f, Aggression);
            Rig.Anim.Play(Clips["slash"], 0.06f, 0.15f, slashSpeed, onAttackEvent, onAttackEnd);
        }

        void OnAttackEvent(string e)
        {
            switch (e)
            {
                case "telegraph":
                    BeginThreat(EventGap(Clips["slash"], "telegraph", "hit_start", slashSpeed), EventGap(Clips["slash"], "hit_start", "hit_end", slashSpeed));
                    FxKit.Sfx("enemy_telegraph", position, 0.6f);
                    break;
                case "hit_start":
                    hitActive = true;
                    ThreatActive(EventGap(Clips["slash"], "hit_start", "hit_end", slashSpeed));
                    break;
                case "hit_end":
                    hitActive = false;
                    Rig.Telegraph = 0f;
                    EndThreat();
                    break;
            }
        }

        void OnAttackEnd()
        {
            hitActive = false;
            Rig.Telegraph = 0f;
            EndThreat();
            ReleaseToken();
            if (State == EnemyState.Attack) Enter(EnemyState.Recover);
        }

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
            phaseCd -= dt;
            recentT -= dt;
            if (recentT <= 0f) recentHits = 0;
            Rig.Anim.CombatStance = Aggro ? 1f : 0f;
            // Visual phase state
            float wantOpacity = State == EnemyState.Phase ? (EnemyHost.EchoActive ? 0.55f : 0.08f) : 1f;
            Rig.Opacity += (wantOpacity - Rig.Opacity) * Mathf.Min(1f, dt * 10f);
            if (Rig.Opacity > 0.995f) Rig.Opacity = 1f;
            switch (State)
            {
                case EnemyState.Idle:
                case EnemyState.Patrol:
                    Brake(6f, dt);
                    Integrate(dt);
                    yaw = CombatMath.DampAngle(yaw, homeYaw + Mathf.Sin(stateT * 0.6f) * 0.8f, 2f, dt);
                    break;
                case EnemyState.Alert:
                    Brake(6f, dt);
                    Integrate(dt);
                    if (p != null) yaw = CombatMath.DampAngle(yaw, YawTo(p.Position), 10f, dt);
                    if (stateT > 0.4f) Enter(EnemyState.Pursue);
                    break;
                case EnemyState.Pursue:
                {
                    if (p == null || !p.Alive)
                    {
                        Enter(EnemyState.Return);
                        break;
                    }
                    float d = CombatMath.DistXZ(position, p.Position) - p.Radius - Radius;
                    if (phaseCd <= 0f && d > 3f && d < 18f)
                    {
                        StartPhase(false);
                        break;
                    }
                    if (d <= Def.AttackRange && attackCd <= 0f && RequestToken())
                    {
                        StartAttack();
                        break;
                    }
                    if (!hasToken && d < 5f)
                    {
                        Vector3 away = position - p.Position;
                        away.y = 0f;
                        away = away.sqrMagnitude > 1e-6f ? away.normalized : -Forward;
                        Vector3 side = new Vector3(away.z, 0f, -away.x) * strafe;
                        SteerTo(p.Position + away * 4.5f + side * 3f, 4.5f, dt, 10f, false);
                        yaw = CombatMath.DampAngle(yaw, YawTo(p.Position), 10f, dt);
                        if (Random.value < dt * 0.4f) strafe *= -1f;
                    }
                    else SteerTo(p.Position, Def.Speed, dt, 10f);
                    break;
                }
                case EnemyState.Phase:
                {
                    // Glide to the flank position while phased (passes through the player's line of fire).
                    float d = SteerTo(phaseTarget, 11f, dt, 14f);
                    emberAcc += dt * 24f;
                    while (emberAcc >= 1f)
                    {
                        emberAcc -= 1f;
                        FxKit.Embers(AimPoint, 1, 0xb48cffu, 0.6f, 0.3f);
                    }
                    if (d < 0.8f || stateT > 1.4f)
                    {
                        FxKit.FlashSprite(AimPoint, 2f, 0xb48cffu, 0.15f);
                        if (p != null) yaw = YawTo(p.Position);
                        attackCd = 0f;
                        if (RequestToken()) StartAttack();
                        else Enter(EnemyState.Pursue);
                    }
                    break;
                }
                case EnemyState.Attack:
                {
                    if (p != null && stateT < 0.25f) yaw = CombatMath.DampAngle(yaw, YawTo(p.Position), 10f, dt);
                    float lunge = hitActive ? 6f : 0f;
                    velocity.x = Mathf.Sin(yaw) * lunge;
                    velocity.z = Mathf.Cos(yaw) * lunge;
                    Integrate(dt);
                    if (hitActive) MeleeArc(Def.AttackRange + 0.5f, 70f * Mathf.Deg2Rad, Def.Damage, 16f, 3f, hitSet);
                    if (stateT > 2f) Enter(EnemyState.Recover);
                    break;
                }
                case EnemyState.Recover:
                    Brake(8f, dt);
                    Integrate(dt);
                    if (stateT > 0.4f)
                    {
                        attackCd = (1.1f + Random.value * 0.8f) / Aggression;
                        Enter(Aggro ? EnemyState.Pursue : EnemyState.Return);
                    }
                    break;
                case EnemyState.Stagger:
                    Brake(5f, dt);
                    Integrate(dt);
                    if (stateT > StaggerTime) Enter(Aggro ? EnemyState.Pursue : EnemyState.Idle);
                    break;
                case EnemyState.Return:
                    UpdateReturn(dt, Def.Speed * 0.7f);
                    break;
                default:
                    Integrate(dt);
                    break;
            }
            Rig.Anim.Speed = new Vector2(velocity.x, velocity.z).magnitude;
        }
    }
}
