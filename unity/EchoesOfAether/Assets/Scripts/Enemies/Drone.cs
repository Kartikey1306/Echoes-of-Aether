using UnityEngine;
using Random = UnityEngine.Random;

namespace EOA
{
    /// <summary>
    /// Aether Drone: flying ranged enemy (port of Drone.ts).
    /// idle -> patrol -> (detect) alert -> pursue (orbit at ~9 m, 2-shot bursts after a 0.55 s charge telegraph,
    /// periodic low dive that rams for 80% damage) ; stagger spins it ; death = spinning fall + explosion.
    /// </summary>
    public sealed class Drone : Enemy
    {
        float altitude = 4.5f;
        float orbitDir;
        float fireCd;
        int burstLeft;
        float burstT;
        float patrolA;
        float diveCd;
        float diving;
        float spin;
        bool falling;
        float vy;
        float pitch, roll; // prototype Euler convention (radians)
        float rotorAngle;
        float ceiling = 999f;
        float smokeAcc;
        EnemyWeaponFx weapons;

        protected override void Configure()
        {
            Flying = true;
            Radius = 0.55f;
            Height = 0.9f;
            orbitDir = Random.value < 0.5f ? -1f : 1f;
            fireCd = 1.5f + Random.value;
            patrolA = Random.value * Mathf.PI * 2f;
            diveCd = 6f + Random.value * 4f;
            Rig = RobotRig.Create(visual, RobotKind.Drone, new RobotPalette(0x2b3036, 0x5a6068, 0x5fd8ff, 3f), "drone");
            weapons = EnemyWeaponFx.Attach(this, Rig, EnemyWeaponFx.Kind.Drone);
        }

        public override void Spawn(Vector3 pos, float yawDeg)
        {
            base.Spawn(pos, yawDeg);
            float? g = EnemyHost.GroundAt(pos, 20f);
            altitude = Mathf.Clamp(pos.y - (g ?? 0f), 3f, 7f);
            // Indoor ceiling
            ceiling = Physics.Raycast(pos, Vector3.up, out var hit, 30f, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore) ? hit.point.y - 0.8f : 999f;
        }

        public override Vector3 AimPoint => position + Vector3.up * VisualOffsetY;

        protected override Vector3 Eye => position;

        protected override void OnHurt(HitInfo h, float dmg)
        {
            Rig.HitFlash(0.89f);
            FxKit.Sparks(h.Point, null, 6, 0xffc070u, 4f);
            FxKit.Sfx("enemy_hit_metal", position);
            Knock(h.Knock * 1.3f);
            roll += (Random.value - 0.5f) * 0.8f;
        }

        protected override void Stagger(HitInfo h)
        {
            base.Stagger(h);
            spin = 9f;
            burstLeft = 0;
        }

        protected override void Die(HitInfo? h)
        {
            base.Die(h);
            falling = true;
            vy = 1.5f;
            spin = 10f;
            FxKit.Sfx("drone_death", position);
            FxKit.Sparks(position, null, 18, 0xffb060u, 6f);
        }

        float GroundBelow()
        {
            float? g = EnemyHost.GroundAt(position + Vector3.up * 0.5f, 30f);
            return g ?? home.y - altitude;
        }

        protected override void UpdateAI(float dt)
        {
            var p = Target;
            float ground = GroundBelow();
            Vector3 goal = home;
            float speed = Def.Speed;
            float wantAlt = altitude;
            fireCd -= dt;
            diveCd -= dt;
            switch (State)
            {
                case EnemyState.Idle:
                    if (stateT > 2f) Enter(EnemyState.Patrol);
                    goal = home;
                    speed = 1.5f;
                    break;
                case EnemyState.Patrol:
                    patrolA += dt * 0.35f;
                    goal = new Vector3(home.x + Mathf.Cos(patrolA) * 5f, 0f, home.z + Mathf.Sin(patrolA) * 5f);
                    speed = 2.2f;
                    break;
                case EnemyState.Alert:
                    velocity *= Mathf.Exp(-4f * dt);
                    if (p != null) yaw = CombatMath.DampAngle(yaw, YawTo(p.Position), 10f, dt);
                    if (stateT > 0.5f) Enter(EnemyState.Pursue);
                    Move(dt, position, 0f, wantAlt, ground);
                    return;
                case EnemyState.Pursue:
                case EnemyState.Attack:
                {
                    if (p == null)
                    {
                        Enter(EnemyState.Return);
                        break;
                    }
                    float d = CombatMath.DistXZ(position, p.Position);
                    Vector3 toward = p.Position - position;
                    toward.y = 0f;
                    toward = toward.sqrMagnitude > 1e-6f ? toward.normalized : Forward;
                    Vector3 side = new Vector3(toward.z, 0f, -toward.x) * orbitDir;
                    float ideal = diving > 0f ? 2.2f : 9f;
                    goal = position + toward * ((d - ideal) * 0.9f) + side * 4f;
                    speed = diving > 0f ? 8f : Def.Speed;
                    wantAlt = diving > 0f ? 1.9f : altitude;
                    if (Random.value < dt * 0.2f) orbitDir *= -1f;
                    yaw = CombatMath.DampAngle(yaw, YawTo(p.Position), 8f, dt);
                    // Dive: swoop low near the target (opens a melee window), then climb.
                    if (diving > 0f)
                    {
                        diving -= dt;
                        if (d < 3.2f && diving > 0.4f) MeleeTouch(p);
                    }
                    else if (diveCd <= 0f && d < 14f && CanSeeTarget)
                    {
                        diving = 2.2f;
                        diveCd = 8f + Random.value * 5f;
                        FxKit.Sfx("drone_dive", position);
                    }
                    // Firing
                    if (burstLeft > 0)
                    {
                        burstT -= dt;
                        if (burstT <= 0f)
                        {
                            burstLeft--;
                            burstT = 0.22f;
                            Shoot(p);
                            if (burstLeft == 0)
                            {
                                ReleaseToken();
                                fireCd = (1.8f + Random.value * 1.2f) / Aggression;
                            }
                        }
                    }
                    else if (fireCd <= 0f && CanSeeTarget && d < Def.AttackRange + 4f && diving <= 0f)
                    {
                        if (RequestToken())
                        {
                            burstLeft = 2;
                            burstT = 0.55f; // charge time (telegraph)
                            FxKit.Sfx("drone_charge", position);
                        }
                        else fireCd = 0.6f;
                    }
                    break;
                }
                case EnemyState.Stagger:
                    velocity *= Mathf.Exp(-3f * dt);
                    if (stateT > StaggerTime) Enter(Aggro ? EnemyState.Pursue : EnemyState.Idle);
                    Move(dt, position, 0f, wantAlt - 0.8f, ground);
                    return;
                case EnemyState.Return:
                    goal = home;
                    speed = 3.5f;
                    Health = Mathf.Min(MaxHealth, Health + MaxHealth * 0.25f * dt);
                    if (CombatMath.DistXZ(position, home) < 1.5f || stateT > 12f)
                    {
                        if (stateT > 12f) Teleport(home);
                        Enter(EnemyState.Idle);
                    }
                    if (CanSeeTarget) SetAggro();
                    break;
            }
            // Stay inside the arena
            if (hasArena && CombatMath.DistXZ(goal, arenaCenter) > arenaRadius)
            {
                Vector3 off = goal - arenaCenter;
                off.y = 0f;
                goal = arenaCenter + off.normalized * arenaRadius;
            }
            Move(dt, goal, speed, wantAlt, ground);
        }

        void MeleeTouch(IDamageable p)
        {
            // Diving drones ram the target if they get very close.
            if (Vector3.Distance(position, p.AimPoint) >= 1.4f) return;
            Vector3 dir = p.Position - position;
            dir.y = 0f;
            dir = dir.sqrMagnitude > 1e-6f ? dir.normalized : Forward;
            if (HitTarget(p, Def.Damage * 0.8f, 10f, dir * 4f, position)) diving = Mathf.Min(diving, 0.3f);
        }

        void Shoot(IDamageable p)
        {
            Vector3 from = position + new Vector3(Mathf.Sin(yaw) * 0.6f, -0.2f, Mathf.Cos(yaw) * 0.6f);
            Vector3 target = p.AimPoint;
            var shotColor = CombatMath.Hex(0xff5a4a);
            // leave from the blaster's next barrel (muzzle flash + recoil); aim is solved from there
            if (weapons != null) from = weapons.Fire(from, target - from, shotColor);
            // Lead the target slightly (imperfect so strafing works).
            float t = Vector3.Distance(from, target) / 24f;
            target += TargetVelocity * (t * 0.55f);
            target.x += (Random.value - 0.5f) * 0.8f;
            target.z += (Random.value - 0.5f) * 0.8f;
            Vector3 dir = (target - from).normalized;
            CombatSystem.Ensure().Fire(new ProjectileSpec
            {
                From = from,
                Dir = dir,
                Speed = 24f,
                Damage = Def.Damage,
                Team = Team.Enemy,
                Color = shotColor,
                Source = this,
                Kind = HitKind.Enemy,
                Poise = 8f,
                Size = 0.12f,
                Life = 3f,
                NoMuzzle = weapons != null,
            });
            FxKit.Sfx("drone_shot", from);
            FxKit.Sfx("blaster_shot", from, 0.7f);
        }

        void Move(float dt, Vector3 goal, float speed, float wantAlt, float ground)
        {
            Vector3 to = goal - position;
            to.y = 0f;
            float d = to.magnitude;
            if (d > 0.3f && speed > 0f) to *= Mathf.Min(speed, d * 2f) / d;
            else to = Vector3.zero;
            // Obstacle avoidance
            if (to.sqrMagnitude > 0.01f && Physics.Raycast(position, to.normalized, out var hit, 2.5f, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore))
            {
                to += hit.normal * (speed * 1.2f);
                wantAlt += 1.5f;
            }
            velocity.x = CombatMath.Damp(velocity.x, to.x, 3f, dt);
            velocity.z = CombatMath.Damp(velocity.z, to.z, 3f, dt);
            float targetY = Mathf.Min(ground + wantAlt + Mathf.Sin(stateT * 2f + Id) * 0.25f, ceiling);
            velocity.y = CombatMath.Damp(velocity.y, (targetY - position.y) * 2.2f, 4f, dt);
            position += velocity * dt;
            // Never clip into the ground
            if (position.y < ground + 0.8f)
            {
                position.y = ground + 0.8f;
                velocity.y = Mathf.Max(0f, velocity.y);
            }
            // Tilt in the direction of travel (local: z forward, x right).
            Vector3 local = Quaternion.Euler(0f, -yaw * Mathf.Rad2Deg, 0f) * velocity;
            pitch = CombatMath.Damp(pitch, Mathf.Clamp(local.z * 0.06f, -0.4f, 0.4f), 6f, dt);
            // Prototype roll = -leftward velocity * 0.06; Unity local.x is rightward.
            roll = CombatMath.Damp(roll, Mathf.Clamp(local.x * 0.06f, -0.4f, 0.4f), 6f, dt);
        }

        protected override void UpdateDead(float dt)
        {
            if (falling)
            {
                vy -= 18f * dt;
                position.y += vy * dt;
                position += velocity * dt;
                velocity *= Mathf.Exp(-1f * dt);
                spin = Mathf.Max(2f, spin - dt * 3f);
                yaw += spin * dt;
                smokeAcc += dt * 30f;
                while (smokeAcc >= 1f)
                {
                    smokeAcc -= 1f;
                    FxKit.Smoke(position, 1, 0x15171a, 0.5f);
                }
                float? g = EnemyHost.GroundAt(position + Vector3.up * 0.5f, 3f);
                if ((g.HasValue && position.y <= g.Value + 0.3f) || deathT > 2.5f)
                {
                    falling = false;
                    FxKit.Explode(new Vector3(position.x, (g ?? position.y) + 0.4f, position.z), 0.9f, 0x5fd8ff);
                    FxKit.Sfx("explosion", position);
                    FxKit.Shake(0.15f);
                    FxKit.Sfx("robot_break", position, 0.7f);
                    HitFx.BreakApart(Rig, position, LastKnock + velocity * 0.5f, 4f, 6, CombatMath.Hex(0x7fd8ff));
                    Rig.SetVisible(false);
                }
            }
            if (deathT > 3f) Dispose();
        }

        protected override void UpdateModel(float dt)
        {
            if (Alive) spin = Mathf.Max(0f, spin - dt * 6f);
            rotorAngle += dt * 40f;
            Quaternion rotor = Quaternion.AngleAxis(rotorAngle * Mathf.Rad2Deg, Vector3.up);
            foreach (var r in Rig.Rotors) if (r != null) r.localRotation = rotor;
            if (Rig.DroneBody != null)
                Rig.DroneBody.localRotation = RobotAnimator.EulerXYZ(pitch, State == EnemyState.Stagger ? stateT * spin : 0f, roll);
            uint baseColor = Aggro ? 0xff4a3au : 0x5fd8ffu;
            float charge = burstLeft > 0 && burstT > 0.25f ? 1f + Mathf.Sin(stateT * 40f) * 0.5f + 1.5f : 1f;
            Rig.SetGlow(CombatMath.Hex(baseColor), 3f * charge);
            Rig.Tick(dt);
        }
    }
}
