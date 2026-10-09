using System;
using System.Collections.Generic;
using UnityEngine;
using Random = UnityEngine.Random;

namespace EOA
{
    /// <summary>
    /// Corrupted Sentinel (melee) and The Warden (elite variant: frontal shield that blocks most non-pierce damage
    /// from the front until staggered, and a slam whose shockwave reaches 5 m). Port of Sentinel.ts.
    /// </summary>
    public sealed class Sentinel : Enemy
    {
        bool elite;
        float attackCd;
        readonly HashSet<IDamageable> hitSet = new();
        bool hitActive;
        bool slamAttack;
        float strafeDir;
        float patrolT;
        bool shieldUp = true;
        GameObject shield;
        Material shieldMat;
        Action<string> onAttackEvent;
        Action onAttackEnd;
        RobotClip curClip;
        float curSpeed = 1f;
        EnemyWeaponFx weapons;

        public bool IsWarden => elite;
        /// <summary>Warden shield currently raised (and visible).</summary>
        public bool ShieldUp => elite && shieldUp && Aggro;

        protected override void Configure()
        {
            elite = Variant == "warden" || Def.Id == "warden";
            Height = elite ? 2.6f : 2.15f;
            Radius = elite ? 0.62f : 0.5f;
            attackCd = 1f + Random.value;
            strafeDir = Random.value < 0.5f ? -1f : 1f;
            var pal = elite ? new RobotPalette(0x3a2e30, 0x1f1c1e, 0xff3b30, 3.4f) : new RobotPalette(0x4a4f56, 0x24272c, 0xff5a3a, 3f);
            Rig = RobotRig.Create(visual, elite ? RobotKind.Warden : RobotKind.Sentinel, pal, elite ? "warden" : "sentinel");
            Clips = RobotClips.Get(RobotClips.Kind.Sentinel);
            weapons = EnemyWeaponFx.Attach(this, Rig, elite ? EnemyWeaponFx.Kind.Warden : EnemyWeaponFx.Kind.Sentinel);
            onAttackEvent = OnAttackEvent;
            onAttackEnd = OnAttackEnd;
            if (elite) BuildShield();
        }

        void BuildShield()
        {
            // Frontal energy dome (the prototype's partial sphere, centred on +Z).
            shield = new GameObject("Shield");
            shield.layer = CombatLayers.Enemy;
            shield.transform.SetParent(visual, false);
            shield.transform.localPosition = new Vector3(0f, 1.4f, 0.2f);
            shield.AddComponent<MeshFilter>().sharedMesh = FxMesh.SphereShell(1.25f, 24, 12, -Mathf.PI * 0.42f, Mathf.PI * 0.84f, Mathf.PI * 0.2f, Mathf.PI * 0.55f);
            var mr = shield.AddComponent<MeshRenderer>();
            shieldMat = FxMaterials.Particle(true, FxMaterials.White, true);
            shieldMat.SetColor("_BaseColor", WithAlpha(FxMaterials.Hdr(CombatMath.Hex(0xff5a3a), 0.9f), 0.22f));
            mr.sharedMaterial = shieldMat;
            mr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            mr.receiveShadows = false;
            shield.SetActive(false);
        }

        static Color WithAlpha(Color c, float a)
        {
            c.a = a;
            return c;
        }

        protected override float DamageTakenMul(HitInfo h)
        {
            if (!elite || !shieldUp || State == EnemyState.Stagger) return 1f;
            // Frontal shield blocks most damage from the front; flank or stagger to break through.
            Vector3 src = h.Source != null ? h.Source.transform.position : h.Point;
            float ang = FacingTo(src);
            if (ang < 70f * Mathf.Deg2Rad && !h.Pierce && h.Kind != HitKind.Pulse && h.Kind != HitKind.Ultimate)
            {
                FxKit.Sparks(h.Point, null, 8, 0xff6a4au, 5f);
                var away = src - h.Point;
                WeaponFx.Impact(h.Point, away.sqrMagnitude > 1e-4f ? away.normalized : Forward, CombatMath.Hex(0xff8a5a), 0.5f);
                FxKit.Sfx("shield_block", h.Point);
                FxKit.Sfx("parry_spark", h.Point, 0.5f);
                return h.Kind == HitKind.Heavy ? 0.45f : 0.15f;
            }
            return 1f;
        }

        protected override void OnHurt(HitInfo h, float dmg)
        {
            Rig.HitFlash(1f);
            FxKit.Sfx("enemy_hit_metal", h.Point);
        }

        protected override void Stagger(HitInfo h)
        {
            base.Stagger(h);
            hitActive = false;
            weapons?.SetSwing(false);
            Rig.Telegraph = 0f;
            // Long staggers (poise break, deflect) play the reel slower: a dazed, open robot.
            var clip = Clips["stagger"];
            Rig.Anim.Play(clip, 0.05f, 0.15f, Mathf.Clamp(clip.Duration / Mathf.Max(0.1f, StaggerTime), 0.55f, 1f));
            FxKit.Sfx("enemy_stagger", position);
            if (elite) shieldUp = false;
        }

        protected override void Die(HitInfo? h)
        {
            base.Die(h);
            hitActive = false;
            weapons?.Hide();
            Rig.Telegraph = 0f;
            Rig.Anim.StopActions(0.05f);
            Rig.Anim.SetState(Clips["death"], 0.1f);
            FxKit.Sfx("sentinel_death", position);
            FxKit.Sparks(AimPoint, null, 24, 0xffb060u, 7f);
            FxKit.FlashSprite(AimPoint, 2.4f, 0xffd0a0u, 0.12f);
            if (shield != null) shield.SetActive(false);
        }

        protected override void UpdateDead(float dt)
        {
            if (deathT > 0.75f && deathT - dt <= 0.75f)
            {
                // Mid-collapse the core blows: plates and limbs fly apart.
                FxKit.Explode(position + Vector3.up * 0.9f, elite ? 1.6f : 1.1f, 0xff6a4a);
                FxKit.Sfx("explosion", position);
                FxKit.Sfx("robot_break", position);
                FxKit.Shake(elite ? 0.4f : 0.2f);
                HitFx.BreakApart(Rig, position + Vector3.up * Height * 0.45f, LastKnock, elite ? 6f : 5f, elite ? 12 : 9, CombatMath.Hex(0xff8a4a));
            }
            if (deathT > 1.5f) deathSink = (deathT - 1.5f) * 0.6f;
            if (deathT > 3.5f) Dispose();
        }

        void StartAttack(bool slam)
        {
            slamAttack = slam;
            Enter(EnemyState.Attack);
            hitSet.Clear();
            hitActive = false;
            float speed = (elite ? 1.05f : 1f) * Mathf.Min(1.25f, Aggression);
            curClip = Clips[slam ? "slam" : "sweep"];
            curSpeed = speed;
            Rig.Anim.Play(curClip, 0.1f, 0.15f, speed, onAttackEvent, onAttackEnd);
        }

        void OnAttackEvent(string e)
        {
            switch (e)
            {
                case "telegraph":
                    BeginThreat(EventGap(curClip, "telegraph", "hit_start", curSpeed), EventGap(curClip, "hit_start", "hit_end", curSpeed));
                    FxKit.Sfx("enemy_telegraph", position);
                    break;
                case "hit_start":
                    hitActive = true;
                    weapons?.SetSwing(true);
                    ThreatActive(EventGap(curClip, "hit_start", "hit_end", curSpeed));
                    break;
                case "hit_end":
                    hitActive = false;
                    weapons?.SetSwing(false);
                    Rig.Telegraph = 0f;
                    EndThreat();
                    break;
                case "impact":
                {
                    Vector3 center = position + Forward * 1.6f;
                    FxKit.Shockwave(center, elite ? 5f : 2.6f, 0xff5a3a, 0.4f);
                    FxKit.Sparks(center + Vector3.up * 0.2f, Vector3.up, 18, 0xffa060u, 6f);
                    FxKit.Shake(elite ? 0.35f : 0.18f);
                    FxKit.Sfx("slam", center);
                    if (elite)
                    {
                        // Shockwave reaches further than the fists.
                        var hit = new HitInfo { Damage = Def.Damage * 0.8f, Poise = 40f, Kind = HitKind.Enemy, Source = this };
                        CombatSystem.Ensure().RadialDamage(Team.Enemy, center, 5f, hit, 7f, hitSet, 1.2f);
                    }
                    break;
                }
            }
        }

        void OnAttackEnd()
        {
            hitActive = false;
            weapons?.SetSwing(false);
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
            if (shield != null)
            {
                if (!shieldUp && State != EnemyState.Stagger && stateT > 2f) shieldUp = true;
                bool vis = shieldUp && Aggro;
                if (shield.activeSelf != vis) shield.SetActive(vis);
                if (vis) shieldMat.SetColor("_BaseColor", WithAlpha(FxMaterials.Hdr(CombatMath.Hex(0xff5a3a), 0.9f), 0.16f + Mathf.Sin(stateT * 6f) * 0.05f));
            }
            var anim = Rig.Anim;
            anim.CombatStance = Aggro ? 1f : 0f;
            switch (State)
            {
                case EnemyState.Idle:
                    Brake(6f, dt);
                    Integrate(dt);
                    yaw = CombatMath.DampAngle(yaw, homeYaw + Mathf.Sin(stateT * 0.4f) * 0.6f, 1.5f, dt);
                    patrolT += dt;
                    if (patrolT > 6f)
                    {
                        patrolT = 0f;
                        Enter(EnemyState.Patrol);
                    }
                    break;
                case EnemyState.Patrol:
                {
                    Vector3 goal = home + new Vector3(Mathf.Sin(Id * 3.1f) * 3f, 0f, Mathf.Cos(Id * 3.1f) * 3f);
                    float d = SteerTo(stateT < 4f ? goal : home, 1.4f, dt);
                    if (stateT > 8f && d < 0.6f) Enter(EnemyState.Idle);
                    break;
                }
                case EnemyState.Alert:
                    Brake(6f, dt);
                    Integrate(dt);
                    if (p != null) yaw = CombatMath.DampAngle(yaw, YawTo(p.Position), 8f, dt);
                    if (stateT > 0.6f) Enter(EnemyState.Pursue);
                    break;
                case EnemyState.Pursue:
                {
                    if (p == null || !p.Alive)
                    {
                        Enter(EnemyState.Return);
                        break;
                    }
                    float d = CombatMath.DistXZ(position, p.Position) - p.Radius - Radius;
                    float range = Def.AttackRange * (elite ? 1.1f : 1f);
                    if (d <= range && attackCd <= 0f && FacingTo(p.Position) < 0.6f && RequestToken())
                    {
                        bool slam = elite ? Random.value < 0.55f : Random.value < 0.35f;
                        StartAttack(slam);
                        break;
                    }
                    if (d > range * 0.8f || attackCd > 0.8f)
                    {
                        // Circle at medium range while waiting; once the attack is ready, take a token and close in
                        // (requesting only when already in range left a passive player circled forever).
                        bool closeIn = hasToken || (attackCd <= 0.3f && RequestToken());
                        if (!closeIn && d < 5f)
                        {
                            Vector3 away = position - p.Position;
                            away.y = 0f;
                            away = away.sqrMagnitude > 1e-6f ? away.normalized : -Forward;
                            Vector3 side = new Vector3(away.z, 0f, -away.x) * strafeDir;
                            Vector3 goal = p.Position + away * 4.2f + side * 2f;
                            if (Random.value < dt * 0.3f) strafeDir *= -1f;
                            SteerTo(goal, 2.2f, dt, 8f, false);
                            yaw = CombatMath.DampAngle(yaw, YawTo(p.Position), 8f, dt);
                        }
                        else
                        {
                            float speed = d > 8f ? Def.Speed * 1.35f : Def.Speed;
                            SteerTo(p.Position, speed, dt);
                        }
                    }
                    else
                    {
                        Brake(8f, dt);
                        Integrate(dt);
                        yaw = CombatMath.DampAngle(yaw, YawTo(p.Position), 9f, dt);
                    }
                    break;
                }
                case EnemyState.Attack:
                {
                    // Slight tracking during wind-up, committed during the swing.
                    if (p != null && stateT < 0.35f) yaw = CombatMath.DampAngle(yaw, YawTo(p.Position), 6f, dt);
                    float lunge = hitActive ? 3.5f : 0f;
                    velocity.x = Mathf.Sin(yaw) * lunge;
                    velocity.z = Mathf.Cos(yaw) * lunge;
                    Integrate(dt);
                    if (hitActive)
                    {
                        float dmg = Def.Damage * (slamAttack ? 1.5f : 1f);
                        MeleeArc(Def.AttackRange + 0.6f, (slamAttack ? 50f : 80f) * Mathf.Deg2Rad, dmg, slamAttack ? 45f : 22f, slamAttack ? 6f : 4f, hitSet);
                    }
                    if (stateT > 3f) Enter(EnemyState.Recover);
                    break;
                }
                case EnemyState.Recover:
                    Brake(8f, dt);
                    Integrate(dt);
                    if (stateT > (elite ? 0.5f : 0.7f))
                    {
                        attackCd = (elite ? 1.2f : 1.6f + Random.value) / Aggression;
                        Enter(Aggro ? EnemyState.Pursue : EnemyState.Return);
                    }
                    break;
                case EnemyState.Stagger:
                    Brake(5f, dt);
                    Integrate(dt);
                    if (stateT > StaggerTime) Enter(Aggro ? EnemyState.Pursue : EnemyState.Idle);
                    break;
                case EnemyState.Return:
                    UpdateReturn(dt, Def.Speed);
                    break;
                default:
                    Integrate(dt);
                    break;
            }
            anim.Speed = new Vector2(velocity.x, velocity.z).magnitude;
        }

        protected override void OnDestroy()
        {
            base.OnDestroy();
            if (shieldMat != null) Destroy(shieldMat);
        }
    }
}
