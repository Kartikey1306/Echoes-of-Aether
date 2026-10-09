using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using UnityEngine;

namespace EOA
{
    /// <summary>Forwards animation events from the model's Animator GameObject to the owning actor.</summary>
    public sealed class AnimEventRelay : MonoBehaviour
    {
        public event Action<string> Fired;
        public void OnAnimEvent(string name) => Fired?.Invoke(name);
    }

    /// <summary>
    /// Playable protagonist (Kael or Lyra). The same component runs as the player or as the AI companion.
    /// Port of the prototype's Hero.ts: camera-relative movement, combos, heavy finishers, bolts (tap / hold to aim),
    /// Aether Pulse / Echo Sight, ultimates, Phase Dash / Phase Step with i-frames, shields and regen, fall recovery,
    /// companion follow and support fire.
    /// Combat feel: one-slot input buffer (latest press wins, <see cref="CombatFeel.BufferTime"/>) with explicit cancel
    /// windows (dodge out of anticipation/recovery, abilities after the active frames, stick cancels recovery), facing
    /// snaps to the soft-lock target or stick at swing start, root-motion style step / magnetism curve, per-actor
    /// hit-stop by attack weight, camera kick / FOV punch, perfect dodge (slow motion + counter window) and heavy deflect.
    /// </summary>
    [RequireComponent(typeof(CharacterController))]
    public sealed class Hero : MonoBehaviour, IDamageable, IHeroStatus, IDamageReport
    {
        enum State { Move, Attack, Dash, Ability, Hit, Dead, Scripted, Aim, Ult }
        enum Cmd { None, Light, Heavy, Dash, Ability, Ult }

        /// <summary>One melee swing: damage, reach, hit-stop weight, step curve and phase times (clip seconds, from the
        /// clips_meta.json events: Active0 = hit_start, Active1 = hit_end).</summary>
        struct AttackDef
        {
            public string Clip;
            public float Damage, Poise, Knock, Range, Arc;
            public float Hitstop, Kick, Fov, Rumble;
            public float Step, StepFrom, StepTo;
            public float Active0, Active1, Recover;
            public float Speed, WindupSpeed;
            /// <summary>Clip seconds skipped at the start (near-static mocap lead-in) so the first frame already moves.</summary>
            public float StartAt;
            public bool Heavy, Finisher;
        }

        static readonly string[] KaelChain = { "k_light1", "k_light2", "k_light3" };
        static readonly string[] LyraChain = { "l_quick1", "l_quick2" };
        const float Gravity = -22f;

        public string Character { get; private set; }
        public CharacterModel Model { get; private set; }
        public bool IsPlayer { get; private set; }
        public Hero FollowLeader;

        public float Health { get; private set; } = 100;
        public float Shield { get; private set; } = 50;
        public float Energy { get; private set; } = 100;
        public float UltCharge { get; private set; }
        public float Ultimate => UltCharge / 100f;
        public CharStats Stats => G.Progression.Stats(Character);
        public bool Alive { get; private set; } = true;
        public Team Team => Team.Player;
        public Vector3 Position => transform.position;
        public float HeightM => cc != null ? cc.height + 0.05f : 1.8f;
        public Vector3 AimPoint => transform.position + Vector3.up * HeightM * 0.62f;
        public Vector3 Chest => transform.position + Vector3.up * HeightM * 0.72f;
        public float Radius => 0.36f;
        public bool Targetable => Alive && state != State.Scripted;
        public float LastAppliedDamage { get; private set; }
        public float YawDeg { get => yaw * Mathf.Rad2Deg; set => yaw = value * Mathf.Deg2Rad; }
        public IDamageable LockTarget { get; private set; }
        public bool IsAiming => state == State.Aim;
        /// <summary>Free movement (not attacking, dashing, staggered, scripted...): may get into a car.</summary>
        public bool InMoveState => state == State.Move;
        public Vector3 Velocity => velocity;
        public Vector3 LastSafe => lastSafe;
        public float Invuln { get => invuln; set => invuln = value; }

        CharacterController cc;
        State state = State.Move;
        HumanoidPolish polish;
        float yaw, stateT, coyote, jumpBuffer, airTime, lungeT, invuln, hurtCd, shieldDelay;
        float cdAbility, cdDash, cdBolt, dashSpeed, footstepT, safeT, stuckT, supportT = 2;
        int dashCharges = 1, comboIndex = -1;
        bool wasGrounded = true, comboOpen, hitActive, boltHeld;
        Vector3 velocity, dashDir, lastSafe, lastPos;
        IDamageable lungeTarget, lastTarget;
        readonly HashSet<IDamageable> hitSet = new();
        readonly List<Vector3> trail = new();
        string actionClip;
        Action actionEnd;
        float actionClipT, actionClipLen, actionSpeed = 1f;
        Func<string, bool> eventHandler;

        // Combat feel state
        Cmd buffered;
        float bufferedT, bufferedReal;
        int bufferedFrame, injected;
        AttackDef atk;
        bool swingStopped, swingCounter;
        int atkEvents;
        float stepDist, freezeT, freezeStartReal, deflectUntil, counterUntil = -1f, dashStartT = -9f, armedT, abilityEventT = -1f;
        bool perfectThisDash, wasFrozen, lockSwitchArmed = true;
        float lockFlickAcc;
        HeroWeaponFx weaponFx;
        // Telemetry probe (autopilot): hand pose at the press, compared after animation each frame.
        int probeFrame = -1;
        float probeReal;
        Vector3 probeHand, probeRoot;
        string probeKind;
        Transform scriptedTarget;
        Vector3? scriptedGoal;
        float scriptedSpeed;
        TaskCompletionSource<bool> scriptedDone;
        static readonly int SpeedId = Animator.StringToHash("Speed"), GroundedId = Animator.StringToHash("Grounded"),
            CombatId = Animator.StringToHash("Combat"), VSpeedId = Animator.StringToHash("VerticalSpeed"),
            MoveMulId = Animator.StringToHash("MoveSpeedMul"), ActionSpeedId = Animator.StringToHash("ActionSpeed"),
            CrouchId = Animator.StringToHash("Crouch");

        // ------------------------------------------------------------------ crouch (C / left ctrl / left stick press)

        /// <summary>Crouched move speed (m/s); the crouch_walk clip is time-scaled to it (CharacterBuilder).</summary>
        public const float CrouchSpeed = 1.5f;
        const float CrouchHeightFrac = 0.64f;
        bool crouched;
        float standHeight;
        public bool Crouched => crouched;

        /// <summary>Crouch / stand: lowers the capsule (sneak under obstacles); standing up waits for headroom.</summary>
        public bool SetCrouch(bool on)
        {
            if (cc == null || on == crouched) return crouched == on;
            if (standHeight <= 0) standHeight = cc.height;
            if (!on)
            {
                // Headroom for the standing capsule above the crouched one.
                var top = transform.position + Vector3.up * (cc.height + 0.02f);
                var rise = standHeight - cc.height;
                if (Physics.SphereCast(top - Vector3.up * cc.radius, cc.radius * 0.9f, Vector3.up, out _, rise, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore))
                    return false;
            }
            crouched = on;
            cc.height = on ? standHeight * CrouchHeightFrac : standHeight;
            cc.center = new Vector3(0, cc.height / 2 + 0.02f, 0);
            return true;
        }

        // ------------------------------------------------------------------ creation

        /// <summary>Instantiate a hero from its character prefab (Resources/Characters/&lt;Name&gt;).</summary>
        public static Hero Spawn(string character, Vector3 pos, float yawDeg, Transform parent)
        {
            var root = new GameObject(Characters.DisplayName(character));
            root.transform.SetParent(parent, false);
            root.layer = CombatLayers.Player;
            var cc = root.AddComponent<CharacterController>();
            var hero = root.AddComponent<Hero>();
            hero.Character = character;
            var prefab = Resources.Load<GameObject>("Characters/" + Characters.AssetName(character));
            if (prefab != null)
            {
                var model = Instantiate(prefab, root.transform);
                model.name = "Model";
                hero.Model = model.GetComponent<CharacterModel>();
                // Foot IK, head look and turn lean on top of the animation.
                var polish = model.GetComponent<HumanoidPolish>() ?? model.AddComponent<HumanoidPolish>();
                polish.IsGrounded = () => hero.cc != null && hero.cc.isGrounded;
                hero.polish = polish;
                // Upright torso/neck/head while standing still out of combat (the mocap idle slouches).
                var stance = model.GetComponent<HeroStance>() ?? model.AddComponent<HeroStance>();
                stance.UpperBodyOnly = true;
                var heroAnim = model.GetComponent<Animator>();
                var combatId = Animator.StringToHash("Combat");
                stance.WeightFn = () =>
                    hero.state == State.Move && hero.velocity.x * hero.velocity.x + hero.velocity.z * hero.velocity.z < 0.09f
                    && hero.cc != null && hero.cc.isGrounded && !hero.crouched && (heroAnim == null || !heroAnim.GetBool(combatId)) ? 0.75f : 0f;
                foreach (var t in model.GetComponentsInChildren<Transform>(true)) t.gameObject.layer = CombatLayers.Player;
                var relay = model.GetComponent<AnimEventRelay>() ?? model.AddComponent<AnimEventRelay>();
                relay.Fired += hero.OnAnimEvent;
                hero.Model.ApplyAppearance(G.Manager.AppearanceFor(character));
                // Kael's forearm emitter + hard-light blade and thigh-holstered Aether pistol / Giva's gauntlets, claws and
                // forearm hologram (Blender models from Resources/Weapons, attached to the bones at runtime).
                hero.weaponFx = model.AddComponent<HeroWeaponFx>();
                hero.weaponFx.Init(hero.Model, character == Characters.Kael);
            }
            else Debug.LogError($"[hero] missing prefab Resources/Characters/{Characters.AssetName(character)}");
            var h = hero.Model != null ? hero.Model.BaseHeight * hero.Model.transform.localScale.y : 1.8f;
            cc.radius = 0.36f;
            cc.height = h - 0.05f;
            cc.center = new Vector3(0, cc.height / 2 + 0.02f, 0);
            cc.slopeLimit = 50;
            cc.stepOffset = 0.42f;
            cc.skinWidth = 0.04f;
            hero.cc = cc;
            hero.Teleport(pos, yawDeg);
            var st = hero.Stats;
            hero.Health = st.MaxHealth; hero.Shield = st.MaxShield; hero.dashCharges = st.DashCharges;
            return hero;
        }

        Animator Anim => Model != null ? Model.Animator : null;

        public void Teleport(Vector3 pos, float yawDeg)
        {
            if (cc == null) cc = GetComponent<CharacterController>();
            cc.enabled = false;
            transform.position = pos;
            cc.enabled = true;
            yaw = yawDeg * Mathf.Deg2Rad;
            transform.rotation = Quaternion.Euler(0, yawDeg, 0);
            velocity = Vector3.zero;
            lastSafe = pos;
            lastPos = pos;
            trail.Clear();
        }

        public void SetRole(bool player)
        {
            IsPlayer = player;
            if (!player) CancelActions();
        }

        /// <summary>Re-apply a (possibly changed) appearance and resize the capsule.</summary>
        public void RefreshAppearance()
        {
            if (Model == null) return;
            Model.ApplyAppearance(G.Manager.AppearanceFor(Character));
            var h = Model.BaseHeight * Model.transform.localScale.y;
            cc.height = h - 0.05f;
            cc.center = new Vector3(0, cc.height / 2 + 0.02f, 0);
        }

        public void Restore()
        {
            var st = Stats;
            Health = st.MaxHealth; Shield = st.MaxShield; Energy = 100;
            Alive = true;
            state = State.Move;
            invuln = 1.5f;
            StopActions(0.1f);
            SetCrouch(false);
            Anim?.Play("Locomotion", 0);
        }

        public void RestoreShield() => Shield = Stats.MaxShield;

        public float Cooldown01(string slot)
        {
            var st = Stats;
            return slot switch
            {
                "ability" => Mathf.Clamp01(cdAbility / Mathf.Max(0.01f, (Character == Characters.Kael ? 6 : 4) * st.CooldownMul)),
                "dash" => dashCharges > 0 ? 0 : Mathf.Clamp01(cdDash / Mathf.Max(0.01f, st.DashCooldown * st.CooldownMul)),
                "bolt" => Mathf.Clamp01(cdBolt / 0.28f),
                _ => 0,
            };
        }

        public int DashCharges => dashCharges;

        // ------------------------------------------------------------------ animation helpers

        void PlayAction(string clip, float fade, float speed = 1, Action onEnd = null, Func<string, bool> onEvent = null, float startAt = 0f)
        {
            var a = Anim;
            if (a == null) { onEnd?.Invoke(); return; }
            a.SetFloat(ActionSpeedId, speed);
            a.CrossFadeInFixedTime(clip, fade, 1, startAt);
            actionClip = clip;
            actionEnd = onEnd;
            eventHandler = onEvent;
            actionClipT = startAt;
            actionSpeed = Mathf.Max(0.05f, speed);
            actionClipLen = ClipLength(clip);
        }

        /// <summary>Change the playback speed of the running action (wind-up vs. swing pacing).</summary>
        void SetActionSpeed(float speed)
        {
            speed = Mathf.Max(0.05f, speed);
            if (Mathf.Abs(speed - actionSpeed) < 1e-3f) return;
            actionSpeed = speed;
            Anim?.SetFloat(ActionSpeedId, speed);
        }

        float ClipLength(string clip)
        {
            var a = Anim;
            if (a == null || a.runtimeAnimatorController == null) return 1f;
            // animationClips allocates a new array per call: look clips up once per controller (perf: no GC per attack).
            if (clipLengthsFor != a.runtimeAnimatorController)
            {
                clipLengthsFor = a.runtimeAnimatorController;
                clipLengths.Clear();
                foreach (var c in clipLengthsFor.animationClips) if (c != null && !clipLengths.ContainsKey(c.name)) clipLengths[c.name] = c.length;
            }
            return clipLengths.TryGetValue(clip, out var len) ? len : 1f;
        }
        readonly System.Collections.Generic.Dictionary<string, float> clipLengths = new();
        RuntimeAnimatorController clipLengthsFor;
        static readonly Vector3[] SafetyProbe = { new(0.5f, 0, 0), new(-0.5f, 0, 0), new(0, 0, 0.5f), new(0, 0, -0.5f) };

        static readonly int EmptyStateId = Animator.StringToHash("Empty");

        /// <summary>The Action layer still shows a clip (a looping action outlives its timed action: no exit transition).</summary>
        bool ActionLayerBusy(Animator a) =>
            a != null && a.layerCount > 1 && (a.GetCurrentAnimatorStateInfo(1).shortNameHash != EmptyStateId || a.IsInTransition(1));

        void StopActions(float fade)
        {
            var a = Anim;
            if (a != null && (actionClip != null || ActionLayerBusy(a))) a.CrossFadeInFixedTime("Empty", fade, 1, 0f);
            actionClip = null;
            actionEnd = null;
            eventHandler = null;
        }

        void PlayUpper(string clip, float fade)
        {
            Anim?.CrossFadeInFixedTime(clip, fade, 2, 0f);
        }

        void StopUpper(float fade) => Anim?.CrossFadeInFixedTime("Empty", fade, 2, 0f);

        void OnAnimEvent(string name)
        {
            if (eventHandler != null && eventHandler(name)) return;
        }

        void TickAction(float dt)
        {
            if (actionClip == null) { ReleaseOrphanLoop(); return; }
            actionClipT += dt * actionSpeed;
            if (actionClipT >= actionClipLen)
            {
                var end = actionEnd;
                actionClip = null; actionEnd = null; eventHandler = null;
                end?.Invoke();
            }
        }

        /// <summary>
        /// A looping action (talk, npc_*, sit...) played with PlayClip(clip) outlives its timed action: its state has no
        /// exit, so the full-body Action layer kept overriding locomotion (a hero running in the talk pose after the
        /// reunion). Once the hero is back under control (player controllable, or a companion following), fade it out.
        /// </summary>
        void ReleaseOrphanLoop()
        {
            if (state != State.Move) return;
            var free = IsPlayer ? G.Manager != null && G.Manager.PlayerControllable : FollowLeader != null && G.Manager != null && G.Manager.Mode == GameMode.Play;
            if (!free) return;
            var a = Anim;
            if (a == null || a.layerCount < 2 || a.IsInTransition(1)) return;
            var info = a.GetCurrentAnimatorStateInfo(1);
            if (info.shortNameHash != EmptyStateId && info.loop) a.CrossFadeInFixedTime("Empty", 0.25f, 1, 0f);
        }

        /// <summary>Play a named clip (cinematics, NPC-style gestures).</summary>
        public void PlayClip(string clip, bool hold = false)
        {
            PlayAction(clip, 0.2f, 1, null, null);
            if (hold) actionClipLen = float.PositiveInfinity;
        }

        public void CancelActions()
        {
            StopActions(0.12f);
            StopUpper(0.12f);
            state = Alive ? State.Move : State.Dead;
            comboIndex = -1; comboOpen = false; hitActive = false; boltHeld = false;
            if (G.Manager?.Cam != null && IsPlayer) G.Manager.Cam.Aiming = false;
        }

        // ------------------------------------------------------------------ damage

        public void ReceiveHit(HitInfo h)
        {
            LastAppliedDamage = 0;
            if (!Alive) return;
            // Deflect: the opening of a heavy swing turns a frontal melee blow back on the attacker.
            if (Time.time < deflectUntil && h.Kind == HitKind.Enemy && h.Source is Enemy foe && foe.Alive
                && Vector3.Angle(Facing, Flat(foe.Position - Position)) < 80f)
            {
                Deflect(foe, h.Point);
                return;
            }
            if (invuln > 0 || state == State.Ult || state == State.Scripted)
            {
                if (state == State.Dash && h.Kind != HitKind.Environment)
                {
                    if (!perfectThisDash && Time.time - dashStartT <= CombatFeel.PerfectDodgeReactive) PerfectDodge("reactive");
                    if (Character == Characters.Lyra && Stats.DashIframes > 0.5f)
                    {
                        Energy = Mathf.Min(100, Energy + 15); // dodge refund (Ghost Step)
                        G.Vfx?.Flash(Chest, FxColor(0xa47dff), 1.4f, 4, 0.15f);
                    }
                }
                return;
            }
            if (hurtCd > 0) return;
            var dmg = h.Damage * (h.Kind == HitKind.Environment ? 1 : G.Settings.Difficulty.EnemyDamage);
            var rem = dmg;
            if (!h.Pierce && Shield > 0)
            {
                var absorbed = Mathf.Min(Shield, rem);
                Shield -= absorbed; rem -= absorbed;
                if (Shield <= 0) G.Audio?.Play("shield_break", Position);
            }
            Health -= rem;
            LastAppliedDamage = dmg;
            shieldDelay = Stats.ShieldDelay;
            hurtCd = 0.22f;
            UltCharge = Mathf.Min(100, UltCharge + dmg * 0.5f);
            if (G.State != null) G.State.D.Stats.DamageTaken += dmg;
            Bus.Emit(new PlayerDamaged { Amount = dmg, Source = h.Kind.ToString().ToLowerInvariant() });
            Model?.HitFlash(rem > 0 ? 1 : 0.5f);
            if (IsPlayer)
            {
                CombatSystem.Shake(Mathf.Min(0.5f, 0.15f + dmg / 60f));
                G.Input?.Rumble(Mathf.Min(1, dmg / 30f), Mathf.Min(1, dmg / 30f), 0.16f, G.Settings.Data.Controls.Vibration);
            }
            G.Audio?.Play(rem > 0 ? "player_hurt" : "shield_hit", Position);
            if (Health <= 0) { Die(); return; }
            velocity.x += h.Knock.x; velocity.z += h.Knock.z;
            if (h.Poise >= 35 && state != State.Ability && state != State.Ult)
            {
                CancelActions();
                state = State.Hit;
                stateT = 0;
                PlayAction("stagger", 0.05f, 1, EndStagger);
                CombatTelemetry.Record("player_stagger", dmg);
            }
            else if (actionClip == null) PlayAction("hit", 0.05f, 1.2f);
        }

        /// <summary>Stagger over: a short grace (i-frames) so enemies cannot chain staggers.</summary>
        void EndStagger()
        {
            if (state != State.Hit) return;
            state = State.Move;
            invuln = Mathf.Max(invuln, 0.3f);
        }

        static Vector3 Flat(Vector3 v) { v.y = 0; return v; }

        void Die()
        {
            Health = 0;
            Alive = false;
            CancelActions();
            state = State.Dead;
            PlayAction("death", 0.15f);
            actionClipLen = float.PositiveInfinity;
            buffered = Cmd.None;
            G.Audio?.Play("player_death", Position);
            if (IsPlayer) G.Manager.OnPlayerDied(this);
        }

        // ------------------------------------------------------------------ update

        void Update()
        {
            if (G.Manager == null || G.State == null || cc == null) return;
            var rawDt = Time.deltaTime;
            if (rawDt <= 0) return;
            // Hit-stop freezes this hero only (animation, movement, timers); presses are still buffered.
            // During perfect-dodge slow motion the player runs at up to 2x the world's time scale.
            var timeMul = IsPlayer ? Mathf.Lerp(1f, 2f, CombatSystem.SlowMoWeight) : 1f;
            if (freezeT > 0f)
            {
                // Count down first, ending on the frame closest to the requested duration.
                freezeT -= Time.unscaledDeltaTime;
                if (freezeT < Time.unscaledDeltaTime * 0.5f) freezeT = 0f;
            }
            var frozen = freezeT > 0f;
            var anim = Anim;
            if (anim != null) anim.speed = frozen ? 0f : timeMul;
            if (frozen)
            {
                wasFrozen = true;
                if (IsPlayer && G.Manager.PlayerControllable && state != State.Dead) ReadInput();
                return;
            }
            if (wasFrozen)
            {
                wasFrozen = false;
                CombatTelemetry.Record("freeze_real", Time.realtimeSinceStartup - freezeStartReal);
            }
            var dt = rawDt * timeMul;
            if (buffered != Cmd.None && !(state == State.Attack && !comboOpen && buffered is Cmd.Light or Cmd.Heavy))
                bufferedT -= Time.unscaledDeltaTime;
            var st = Stats;
            stateT += dt;
            invuln = Mathf.Max(0, invuln - dt);
            hurtCd = Mathf.Max(0, hurtCd - dt);
            cdAbility = Mathf.Max(0, cdAbility - dt);
            cdBolt = Mathf.Max(0, cdBolt - dt);
            if (dashCharges < st.DashCharges)
            {
                cdDash -= dt;
                if (cdDash <= 0) { dashCharges++; cdDash = dashCharges < st.DashCharges ? st.DashCooldown * st.CooldownMul : 0; }
            }
            var regen = G.Settings.Difficulty.PlayerRegen;
            shieldDelay -= dt;
            if (shieldDelay <= 0 && Shield < st.MaxShield) Shield = Mathf.Min(st.MaxShield, Shield + st.ShieldRegen * regen * dt);
            Energy = Mathf.Min(st.MaxEnergy, Energy + st.EnergyRegen * dt);
            if (!IsPlayer)
            {
                Health = Mathf.Min(st.MaxHealth, Health + 4 * dt);
                Shield = Mathf.Min(st.MaxShield, Shield + 10 * dt);
            }
            Health = Mathf.Min(Health, st.MaxHealth);
            TickAction(dt);

            if (state == State.Scripted) UpdateScripted(dt);
            else if (IsPlayer && G.Manager.PlayerControllable) UpdatePlayer(dt);
            else if (!IsPlayer && G.Manager.Mode == GameMode.Play) UpdateCompanion(dt);
            else UpdatePhysicsOnly(dt);

            transform.rotation = Quaternion.Euler(0, yaw * Mathf.Rad2Deg, 0);
            DriveWeapon(dt);
            if (polish != null)
            {
                // Look at the lock-on target, else whatever can be interacted with nearby.
                polish.LookTarget = LockTarget != null ? LockTarget.AimPoint
                    : IsPlayer && G.Manager?.World?.CandidatePosition is Vector3 cp ? cp : (Vector3?)null;
            }
            var a = Anim;
            if (a != null)
            {
                var sp = new Vector2(velocity.x, velocity.z).magnitude * (state == State.Move || state == State.Aim || state == State.Scripted ? 1 : 0.2f);
                // Light damping only: velocity is already smoothed by the acceleration, more lag reads as a delayed gait.
                a.SetFloat(SpeedId, sp, 0.05f, dt);
                a.SetBool(GroundedId, cc.isGrounded || coyote > 0.05f);
                a.SetFloat(VSpeedId, velocity.y);
                a.SetBool(CombatId, IsPlayer && G.Manager.InCombat);
                a.SetBool(CrouchId, crouched);
                a.SetFloat(MoveMulId, 1f);
            }
        }

        static Color FxColor(int hex) => new(((hex >> 16) & 255) / 255f, ((hex >> 8) & 255) / 255f, (hex & 255) / 255f);
        Color HeroColor => Character == Characters.Kael ? FxColor(0x5fb8ff) : FxColor(0xa47dff);

        void MoveBody(float dt, Vector3 horizontal)
        {
            if (state != State.Dash) velocity.y += Gravity * dt; else velocity.y = 0;
            var delta = new Vector3(horizontal.x * dt, velocity.y * dt, horizontal.z * dt);
            var flags = cc.Move(delta);
            var grounded = cc.isGrounded;
            if (grounded)
            {
                if (!wasGrounded && airTime > 0.25f) OnLand(-velocity.y);
                if (velocity.y < 0) velocity.y = -1.5f;
                coyote = 0.12f;
                airTime = 0;
            }
            else
            {
                coyote -= dt;
                airTime += dt;
                if (velocity.y > 0 && (flags & CollisionFlags.Above) != 0) velocity.y = 0;
            }
            wasGrounded = grounded;
        }

        void OnLand(float speed)
        {
            if (speed > 9 && IsPlayer)
            {
                CombatSystem.Shake(Mathf.Min(0.4f, speed / 50f));
                // Full-body landing only when landing (nearly) in place; a running landing stays in the gait.
                if (state == State.Move && new Vector2(velocity.x, velocity.z).magnitude < 1.5f) PlayAction("land", 0.04f);
            }
            G.Audio?.Play("land", Position, Mathf.Min(1, speed / 12f));
            Bus.Emit(new PlayerLanded { Speed = speed });
        }

        void UpdatePhysicsOnly(float dt)
        {
            var k = Mathf.Exp(-10 * dt);
            velocity.x *= k; velocity.z *= k;
            MoveBody(dt, velocity);
        }

        static float Damp(float a, float b, float lambda, float dt) => Mathf.Lerp(a, b, 1 - Mathf.Exp(-lambda * dt));
        static float DampAngle(float a, float b, float lambda, float dt) => a + Mathf.DeltaAngle(a * Mathf.Rad2Deg, b * Mathf.Rad2Deg) * Mathf.Deg2Rad * (1 - Mathf.Exp(-lambda * dt));
        static float YawTo(Vector3 from, Vector3 to) => Mathf.Atan2(to.x - from.x, to.z - from.z);
        Vector3 Facing => new(Mathf.Sin(yaw), 0, Mathf.Cos(yaw));

        void UpdatePlayer(float dt)
        {
            var inp = G.Input;
            var cam = G.Manager.Cam;
            var st = Stats;
            var mv = inp.MoveVector;
            var wish = cam.Forward * mv.y + cam.Right * mv.x;
            var mag = Mathf.Min(1, wish.magnitude);
            if (mag > 0.001f) wish /= Mathf.Max(wish.magnitude, 1e-6f);
            if (state == State.Dead) { UpdatePhysicsOnly(dt); return; }

            ReadInput();

            // Bolt: tap to fire, hold to aim.
            if (inp.Pressed("bolt") && (state == State.Move || state == State.Aim)) boltHeld = true;
            if (boltHeld)
            {
                if (inp.Held("bolt")) { if (inp.HoldTime("bolt") > 0.2f && state == State.Move) EnterAim(); }
                else
                {
                    boltHeld = false;
                    FireBolt(state == State.Aim);
                    if (state == State.Aim) ExitAim();
                }
            }

            TryExecuteBuffered(wish * mag);
            // Recovery frames: pushing the stick walks out of the swing (no "stuck in animation").
            if (state == State.Attack && buffered == Cmd.None && mag > 0.3f && actionClipT >= atk.Recover) EndAttack(0.12f);
            // Moving out of a landing / pickup gesture hands the legs back to the gait at once.
            if (state == State.Move && mag > 0.3f && actionClip is "land" or "pickup" or "interact") StopActions(0.12f);
            // Crouch toggle; any action (attack, dash, ability, hit) or a jump press stands the hero up (headroom allowing).
            if (state == State.Move && inp.Pressed("crouch") && cc.isGrounded) SetCrouch(!crouched);
            else if (crouched && state != State.Move && state != State.Aim) SetCrouch(false);
            var jumpPressed = state == State.Move && inp.Pressed("jump") && !(inp.UsingGamepad && G.Manager != null && G.Manager.World?.Candidate != null);
            if (jumpPressed && crouched) { SetCrouch(false); jumpPressed = false; }
            if (jumpPressed) jumpBuffer = 0.15f;

            var sprint = inp.Held("dash") && state == State.Move && mag > 0.5f && !crouched;
            float targetSpeed = 0;
            if (state == State.Move) targetSpeed = crouched ? CrouchSpeed * mag : mag < 0.55f ? 2.2f * (mag / 0.55f) : sprint ? 7.6f : 5.2f;
            else if (state == State.Aim) targetSpeed = 2.6f * mag;
            cam.Sprinting = sprint && mag > 0.5f;

            if (state == State.Move || state == State.Aim)
            {
                var grounded = cc.isGrounded;
                var accel = grounded ? (targetSpeed > new Vector2(velocity.x, velocity.z).magnitude ? 30 : 24) : 8;
                var want = wish * targetSpeed;
                velocity.x = Damp(velocity.x, want.x, accel / 4f, dt);
                velocity.z = Damp(velocity.z, want.z, accel / 4f, dt);
                if (state == State.Aim) yaw = DampAngle(yaw, cam.Heading, 20, dt);
                else if (mag > 0.05f) yaw = DampAngle(yaw, Mathf.Atan2(wish.x, wish.z), grounded ? 14 : 6, dt);
                if (jumpBuffer > 0)
                {
                    jumpBuffer -= dt;
                    if (coyote > 0 && state == State.Move)
                    {
                        velocity.y = 7.6f; coyote = 0; jumpBuffer = 0;
                        G.Audio?.Play("jump", Position);
                    }
                }
            }
            else if (state == State.Attack) UpdateAttack(dt, wish, mag);
            else if (state == State.Ability || state == State.Ult)
            {
                float lunge = 0;
                if (lungeT > 0)
                {
                    lungeT -= dt;
                    if (lungeTarget != null && lungeTarget.Alive)
                    {
                        var d = FlatDist(Position, lungeTarget.Position) - lungeTarget.Radius - Radius;
                        lunge = Mathf.Clamp((d - 0.9f) * 8, 0, 9);
                        yaw = DampAngle(yaw, YawTo(Position, lungeTarget.Position), 18, dt);
                    }
                    else lunge = 2.5f;
                }
                var f = Facing;
                velocity.x = Damp(velocity.x, f.x * lunge, 14, dt);
                velocity.z = Damp(velocity.z, f.z * lunge, 14, dt);
            }
            else if (state == State.Dash)
            {
                velocity.x = dashDir.x * dashSpeed;
                velocity.z = dashDir.z * dashSpeed;
                if (stateT > DashTime) { state = State.Move; stateT = 0; velocity *= 0.35f; TryExecuteBuffered(wish * mag); }
                if (UnityEngine.Random.value < 0.8f) VfxManager.Instance?.Embers(Chest, 2, HeroColor, 0.6f, 0.2f);
            }
            else if (state == State.Hit)
            {
                var k = Mathf.Exp(-6 * dt);
                velocity.x *= k; velocity.z *= k;
                if (stateT > 0.65f) EndStagger();
            }
            // Watchdog: never stay locked in an action whose clip/animator went missing.
            if ((state == State.Attack || state == State.Ability || state == State.Ult || state == State.Hit) && stateT > 3.5f)
            {
                Debug.LogWarning($"[hero] {state} watchdog after {stateT:0.0}s");
                CancelActions();
            }

            MoveBody(dt, velocity);
            TrackSafety(dt);
            Footsteps(dt);
            if (LockTarget != null && (!LockTarget.Alive || !LockTarget.Targetable || Vector3.Distance(LockTarget.Position, Position) > 30)) LockTarget = null;
            if (inp.Pressed("lockon"))
                LockTarget = LockTarget != null ? null : CombatSystem.Ensure().BestTarget(Team.Player, Chest, cam.LookDir, 25, 52, true, false);
            else if (LockTarget != null) UpdateLockSwitch(cam);
            cam.LockTarget = LockTarget?.AimPoint;
        }

        float DashTime => Character == Characters.Kael ? 0.17f : 0.15f;

        // ------------------------------------------------------------------ input buffer & cancel windows

        static int Bit(Cmd c) => 1 << (int)c;

        /// <summary>Autopilot / tests: press a gameplay action this frame as if from the device ("light", "heavy",
        /// "dash", "ability", "ultimate").</summary>
        public void InjectPress(string action)
        {
            var c = action switch { "light" => Cmd.Light, "heavy" => Cmd.Heavy, "dash" => Cmd.Dash, "ability" => Cmd.Ability, "ultimate" => Cmd.Ult, _ => Cmd.None };
            if (c != Cmd.None) injected |= Bit(c);
        }

        bool Pressed(GameInput inp, string action, Cmd c) => (injected & Bit(c)) != 0 || (inp != null && inp.Pressed(action));

        /// <summary>Queue this frame's presses (latest wins; dash beats a simultaneous attack).</summary>
        void ReadInput()
        {
            var inp = G.Input;
            if (Pressed(inp, "light", Cmd.Light)) Buffer(Cmd.Light);
            if (Pressed(inp, "heavy", Cmd.Heavy)) Buffer(Cmd.Heavy);
            if (Pressed(inp, "ability", Cmd.Ability)) Buffer(Cmd.Ability);
            if (Pressed(inp, "ultimate", Cmd.Ult)) Buffer(Cmd.Ult);
            if (Pressed(inp, "dash", Cmd.Dash)) Buffer(Cmd.Dash);
            injected = 0;
        }

        void Buffer(Cmd c)
        {
            buffered = c;
            bufferedT = CombatFeel.BufferTime;
            bufferedFrame = Time.frameCount;
            bufferedReal = Time.realtimeSinceStartup;
        }

        /// <summary>Run the buffered command as soon as the current state allows it.</summary>
        void TryExecuteBuffered(Vector3 wish)
        {
            if (buffered == Cmd.None) return;
            if (bufferedT <= 0) { CombatTelemetry.Record("buffer_expired", (int)buffered); buffered = Cmd.None; return; }
            var c = buffered;
            bool ok;
            switch (state)
            {
                case State.Move:
                case State.Aim:
                    ok = true;
                    break;
                case State.Attack:
                    // Dodge cancels anticipation and recovery (not the active frames); combos chain from the combo
                    // window; abilities once the blow has landed.
                    ok = c == Cmd.Dash ? !hitActive : c is Cmd.Light or Cmd.Heavy ? comboOpen : actionClipT >= atk.Active1;
                    break;
                case State.Dash:
                    ok = stateT >= DashTime * 0.7f; // dodge -> counter attack flows straight on
                    break;
                case State.Ability:
                    ok = abilityEventT >= 0 && stateT - abilityEventT >= 0.12f && c != Cmd.Ability;
                    break;
                case State.Ult:
                    ok = c == Cmd.Dash && abilityEventT >= 0 && stateT - abilityEventT >= 0.3f;
                    break;
                case State.Hit:
                    ok = c == Cmd.Dash && stateT >= 0.3f;
                    break;
                default:
                    ok = false;
                    break;
            }
            if (!ok) return;
            buffered = Cmd.None;
            bufferedT = 0;
            if (state == State.Aim && c is Cmd.Light or Cmd.Heavy) ExitAim();
            var chain = Character == Characters.Kael ? KaelChain : LyraChain;
            var inCombo = state == State.Attack && comboOpen && comboIndex >= 0 && comboIndex < 99;
            switch (c)
            {
                case Cmd.Light:
                    if (inCombo && comboIndex < chain.Length - 1) StartAttack(comboIndex + 1, true);
                    else if (inCombo) StartHeavy(true); // light after the last light: finisher
                    else StartAttack(0, state == State.Attack);
                    break;
                case Cmd.Heavy:
                    StartHeavy(inCombo && comboIndex >= chain.Length - 1);
                    break;
                case Cmd.Dash:
                    var id = Character == Characters.Kael ? "dash" : "step";
                    if (G.State.HasAbility(id) && dashCharges > 0) StartDash(wish.sqrMagnitude > 0.01f ? wish : (Vector3?)null);
                    break;
                case Cmd.Ability:
                    if (state == State.Attack) EndAttack(0.06f);
                    UseAbility();
                    break;
                case Cmd.Ult:
                    if (state == State.Attack) EndAttack(0.06f);
                    UseUltimate();
                    break;
            }
            if (CombatTelemetry.Enabled)
            {
                CombatTelemetry.Record("exec_" + c, Time.frameCount - bufferedFrame, (Time.realtimeSinceStartup - bufferedReal) * 1000f);
                // Pipeline latency: from the frame the action starts (press frame when nothing blocks it).
                ArmProbe(c.ToString(), Time.frameCount == bufferedFrame);
            }
        }

        /// <summary>Lock-on switching: flick the right stick / mouse sideways to hop to the next target on that side.</summary>
        void UpdateLockSwitch(CameraRig cam)
        {
            var look = G.Input.Look.ReadValue<Vector2>();
            float dir = 0;
            if (G.Input.UsingGamepad)
            {
                if (Mathf.Abs(look.x) < 0.35f) lockSwitchArmed = true;
                else if (Mathf.Abs(look.x) > 0.8f && lockSwitchArmed) dir = Mathf.Sign(look.x);
            }
            else
            {
                lockFlickAcc = lockFlickAcc * Mathf.Exp(-10f * Time.unscaledDeltaTime) + look.x;
                if (Mathf.Abs(lockFlickAcc) < 8f) lockSwitchArmed = true;
                else if (Mathf.Abs(lockFlickAcc) > 70f && lockSwitchArmed) dir = Mathf.Sign(lockFlickAcc);
            }
            if (dir == 0) return;
            lockSwitchArmed = false;
            lockFlickAcc = 0;
            var c = cam.Cam;
            var cur = c.WorldToViewportPoint(LockTarget.AimPoint);
            IDamageable best = null;
            float bestScore = float.MaxValue;
            var all = Enemy.All;
            for (var i = 0; i < all.Count; i++)
            {
                var e = all[i];
                if (e == null || ReferenceEquals(e, LockTarget) || !e.Alive || !e.Targetable) continue;
                if (Vector3.Distance(e.Position, Position) > 25) continue;
                var v = c.WorldToViewportPoint(e.AimPoint);
                if (v.z <= 0) continue;
                var dx = v.x - cur.x;
                if (dx * dir <= 0.02f) continue;
                var score = Mathf.Abs(dx) + Mathf.Abs(v.y - cur.y) * 0.5f + v.z * 0.01f;
                if (score < bestScore && CombatSystem.LineOfSight(Chest, e.AimPoint)) { bestScore = score; best = e; }
            }
            if (best == null) return;
            LockTarget = best;
            G.Audio?.Play("ui_hover", null, 0.5f);
        }

        static float FlatDist(Vector3 a, Vector3 b) { a.y = 0; b.y = 0; return Vector3.Distance(a, b); }

        void Footsteps(float dt)
        {
            var sp = new Vector2(velocity.x, velocity.z).magnitude;
            if (!cc.isGrounded || sp < 1.2f || state == State.Dash) return;
            footstepT -= dt * sp;
            if (footstepT <= 0)
            {
                footstepT = sp > 6 ? 2.25f : sp > 3.5f ? 1.75f : 0.82f;
                G.Audio?.Play("footstep", Position, Mathf.Min(1, sp / 6f));
            }
        }

        void TrackSafety(float dt)
        {
            if (Position.y < G.Manager.KillY)
            {
                Teleport(lastSafe, YawDeg);
                ReceiveHit(new HitInfo { Damage = 10, Kind = HitKind.Environment, Point = Position, Pierce = true });
                invuln = 1f;
                G.Audio?.Play("respawn", Position);
                return;
            }
            safeT -= dt;
            if (safeT <= 0 && cc.isGrounded && state == State.Move)
            {
                safeT = 0.5f;
                var ok = true;
                foreach (var o in SafetyProbe)
                    if (!Physics.Raycast(Position + o + Vector3.up * 0.5f, Vector3.down, 1.7f, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore)) { ok = false; break; }
                if (ok) lastSafe = Position;
            }
        }

        // ------------------------------------------------------------------ combat actions

        /// <summary>
        /// Soft lock for melee: the hard lock if any, else the enemy that best matches the stick direction (or, without
        /// stick input, the hero's facing / camera view), weighted by distance; the last enemy struck is preferred so a
        /// combo stays on one target.
        /// </summary>
        IDamageable SoftLockTarget(float maxDist, Vector3 stickDir)
        {
            if (LockTarget != null && LockTarget.Alive && FlatDist(Position, LockTarget.Position) < maxDist + 4f) return LockTarget;
            var stick = stickDir.sqrMagnitude > 0.04f;
            var face = Facing;
            var camF = G.Manager.Cam.Forward;
            IDamageable best = null;
            var bestScore = float.MaxValue;
            var all = Enemy.All;
            for (var i = 0; i < all.Count; i++)
            {
                var e = all[i];
                if (e == null || !e.Alive || !e.Targetable) continue;
                var to = e.Position - Position;
                var dy = to.y;
                to.y = 0;
                var len = to.magnitude;
                var dist = len - e.Radius;
                if (dist > maxDist || Mathf.Abs(dy) > 3f) continue;
                var dir = len > 0.01f ? to / len : face;
                var ang = stick ? Vector3.Angle(stickDir, dir) : Mathf.Min(Vector3.Angle(face, dir), Vector3.Angle(camF, dir) + 15f);
                if (ang > (stick ? 75f : 100f) && dist > 1.2f) continue;
                var score = Mathf.Max(0.5f, dist) * (1f + ang / 45f);
                if (ReferenceEquals(e, lastTarget)) score *= 0.7f;
                if (score < bestScore) { bestScore = score; best = e; }
            }
            return best;
        }

        Vector3 StickWorld()
        {
            var mv = G.Input.MoveVector;
            if (mv.sqrMagnitude < 0.04f) return Vector3.zero;
            var cam = G.Manager.Cam;
            var w = cam.Forward * mv.y + cam.Right * mv.x;
            return w.normalized;
        }

        AttackDef AttackFor(int index, bool heavy, bool finisher)
        {
            var st = Stats;
            var kael = Character == Characters.Kael;
            var speed = G.Powerups.Current().AttackSpeed;
            if (!heavy && kael)
            {
                // k_light1/2/3 (0.53/0.53/0.63 s): active 0.12-0.26 / 0.13-0.27 / 0.17-0.34.
                var third = index == 2;
                return new AttackDef
                {
                    Clip = KaelChain[index], Damage = st.LightDamage * (third ? 1.25f : 1f), Poise = third ? 18 : 14, Knock = third ? 4f : 2.5f,
                    Range = 2.6f, Arc = 75, Hitstop = third ? CombatFeel.HitstopMedium : CombatFeel.HitstopLight,
                    Kick = third ? 0.55f : 0.32f, Fov = third ? -1.5f : 0f, Rumble = third ? 0.35f : 0.22f,
                    Step = third ? 0.8f : 0.55f, StepFrom = 0.03f, StepTo = third ? 0.22f : 0.16f,
                    Active0 = index == 0 ? 0.12f : index == 1 ? 0.13f : 0.17f, Active1 = index == 0 ? 0.26f : index == 1 ? 0.27f : 0.34f,
                    Recover = third ? 0.46f : 0.38f, Speed = speed, WindupSpeed = speed * 1.15f, StartAt = 0.035f,
                };
            }
            if (!heavy)
            {
                // l_quick1/2 (0.37/0.40 s): active 0.10-0.21 / 0.12-0.22.
                return new AttackDef
                {
                    Clip = LyraChain[index], Damage = st.LightDamage, Poise = 10, Knock = 1.6f, Range = 2.3f, Arc = 75,
                    Hitstop = CombatFeel.HitstopLight, Kick = 0.28f, Fov = 0f, Rumble = 0.18f,
                    Step = 0.5f, StepFrom = 0.02f, StepTo = index == 0 ? 0.12f : 0.14f,
                    Active0 = index == 0 ? 0.10f : 0.12f, Active1 = index == 0 ? 0.21f : 0.22f, Recover = index == 0 ? 0.29f : 0.3f,
                    Speed = speed * 1.12f, WindupSpeed = speed * 1.25f, StartAt = 0.02f,
                };
            }
            if (kael)
            {
                // k_heavy (0.93 s): active 0.36-0.50, impact 0.43.
                return new AttackDef
                {
                    Clip = "k_heavy", Damage = st.HeavyDamage * (finisher ? 1.4f : 1f), Poise = finisher ? 60 : 45, Knock = finisher ? 8 : 7,
                    Range = 3.4f, Arc = 100, Hitstop = finisher ? CombatFeel.HitstopFinisher : CombatFeel.HitstopHeavy,
                    Kick = finisher ? 1f : 0.75f, Fov = finisher ? -5f : -3f, Rumble = finisher ? 0.95f : 0.65f,
                    Step = 1f, StepFrom = 0.14f, StepTo = 0.42f, Active0 = 0.36f, Active1 = 0.5f, Recover = 0.68f,
                    Speed = speed, WindupSpeed = speed * 1.3f, StartAt = 0.1f, Heavy = true, Finisher = finisher,
                };
            }
            // l_heavy (0.77 s): active 0.20-0.46, impact 0.32.
            return new AttackDef
            {
                Clip = "l_heavy", Damage = st.HeavyDamage * (finisher ? 1.4f : 1f), Poise = finisher ? 50 : 36, Knock = finisher ? 6 : 5,
                Range = 3f, Arc = 180, Hitstop = finisher ? CombatFeel.HitstopFinisher : CombatFeel.HitstopHeavy,
                Kick = finisher ? 0.9f : 0.65f, Fov = finisher ? -4.5f : -2.5f, Rumble = finisher ? 0.85f : 0.55f,
                Step = 0.8f, StepFrom = 0.06f, StepTo = 0.3f, Active0 = 0.2f, Active1 = 0.46f, Recover = 0.58f,
                Speed = speed, WindupSpeed = speed * 1.15f, StartAt = 0.03f, Heavy = true, Finisher = finisher,
            };
        }

        void StartAttack(int index, bool chained)
        {
            comboIndex = index;
            BeginSwing(AttackFor(index, false, false), chained ? 0.04f : 0.05f);
        }

        void StartHeavy(bool finisher)
        {
            comboIndex = 99;
            BeginSwing(AttackFor(0, true, finisher), 0.05f);
            // The opening of a heavy deflects frontal melee blows (Sentinel / Warden / Guardian / Stalker).
            deflectUntil = Time.time + CombatFeel.DeflectWindow;
            G.Audio?.Play("charge", Position, 0.7f);
        }

        /// <summary>
        /// Start a swing: snap facing to the soft-lock target (else the stick), size the root-motion style step so it
        /// closes the gap to the target (magnetism up to <see cref="CombatFeel.MagnetMax"/>), and play the clip.
        /// </summary>
        void BeginSwing(AttackDef d, float fade)
        {
            state = State.Attack; stateT = 0;
            comboOpen = false; hitActive = false; hitSet.Clear();
            swingStopped = false; atkEvents = 0;
            swingCounter = Time.unscaledTime < counterUntil;
            atk = d;
            var stick = StickWorld();
            lungeTarget = SoftLockTarget(d.Heavy ? 7f : 6f, stick);
            if (lungeTarget != null)
            {
                yaw = YawTo(Position, lungeTarget.Position);
                var gap = FlatDist(Position, lungeTarget.Position) - lungeTarget.Radius - Radius - (d.Heavy ? 0.75f : 0.55f);
                stepDist = gap <= CombatFeel.MagnetMax ? Mathf.Clamp(gap, 0f, CombatFeel.MagnetMax) : d.Step + 0.6f;
            }
            else
            {
                if (stick.sqrMagnitude > 0.01f) yaw = Mathf.Atan2(stick.x, stick.z);
                stepDist = d.Step;
            }
            velocity.x = 0; velocity.z = 0;
            PlayAction(d.Clip, fade, d.WindupSpeed, EndAttackClip, OnAttackEvent, d.StartAt);
            if (swingCounter) VfxManager.Instance?.FlashSprite(Chest, 1.6f, Color.white, 0.1f);
            CombatTelemetry.Record(d.Heavy ? (d.Finisher ? "swing_finisher" : "swing_heavy") : "swing_light", comboIndex, stepDist);
        }

        void EndAttackClip()
        {
            if (state != State.Attack) return;
            state = State.Move;
            comboIndex = -1;
        }

        /// <summary>Leave a swing early (recovery cancel, ability cancel).</summary>
        void EndAttack(float fade)
        {
            StopActions(fade);
            state = State.Move;
            comboIndex = -1;
            comboOpen = false;
            hitActive = false;
        }

        void UpdateAttack(float dt, Vector3 wish, float mag)
        {
            var d = atk;
            var t = actionClipT;
            // Phase events from clip time (the clip's animation events normally fire first; each fires once).
            if (t >= d.Active0) OnAttackEvent("hit_start");
            if (d.Heavy && t >= (d.Active0 + d.Active1) * 0.5f) OnAttackEvent("impact");
            if (t >= d.Active1 - 0.04f) OnAttackEvent("combo");
            if (t >= d.Active1) OnAttackEvent("hit_end");
            // Wind-up plays a touch faster (snappy start), the swing and recovery at full weight.
            SetActionSpeed(t < d.Active0 - 0.03f ? d.WindupSpeed : d.Speed);

            var target = lungeTarget != null && lungeTarget.Alive ? lungeTarget : null;
            if (t < d.Active0)
            {
                if (target != null) yaw = DampAngle(yaw, YawTo(Position, target.Position), 20, dt);
                else if (mag > 0.3f) yaw = DampAngle(yaw, Mathf.Atan2(wish.x, wish.z), 8, dt);
            }
            // Root-motion style step: a sine bell over [StepFrom, StepTo] clip seconds that integrates to stepDist,
            // never pushing into the target.
            float v = 0;
            if (stepDist > 0.01f && t >= d.StepFrom && t <= d.StepTo)
            {
                var T = Mathf.Max(0.01f, d.StepTo - d.StepFrom);
                var u = (t - d.StepFrom) / T;
                v = stepDist * Mathf.PI / (2f * T) * Mathf.Sin(Mathf.PI * u) * actionSpeed;
                if (target != null)
                {
                    var gap = FlatDist(Position, target.Position) - target.Radius - Radius - 0.45f;
                    v = gap <= 0 ? 0 : Mathf.Min(v, gap / Mathf.Max(dt, 1e-4f));
                }
            }
            var f = Facing;
            velocity.x = f.x * v;
            velocity.z = f.z * v;
            if (hitActive) SweepHits();
        }

        static int EventBit(string e) => e switch { "hit_start" => 1, "impact" => 2, "combo" => 4, "hit_end" => 8, _ => 0 };

        bool OnAttackEvent(string e)
        {
            if (state != State.Attack) return false;
            var bit = EventBit(e);
            if (bit == 0) return false;
            if ((atkEvents & bit) != 0) return true;
            // A chained swing cross-fades out of the previous clip, whose late events (hit_end, combo) still fire:
            // only accept an event near its own phase in the current swing.
            var gate = bit switch { 1 => atk.Active0 - 0.06f, 2 => atk.Active0, 4 => atk.Active1 - 0.12f, _ => atk.Active1 - 0.06f };
            if (actionClipT < gate) return true;
            atkEvents |= bit;
            var a = atk;
            var kael = Character == Characters.Kael;
            var color = kael ? FxColor(0x6fc8ff) : comboIndex % 2 == 0 ? FxColor(0xd45cff) : FxColor(0xa47dff);
            switch (e)
            {
                case "hit_start":
                    hitActive = true;
                    G.Audio?.Play(a.Heavy ? "swing_heavy" : kael ? "swing_heavy" : "swing_light", Position, a.Heavy ? 1f : 0.8f, a.Heavy ? 0.85f : 1.05f);
                    G.Audio?.Play("blade_swish", Position, a.Heavy ? 0.9f : 0.6f);
                    // Lyra's palm strikes and the heavies keep the energy arc; Kael's lights read through the blade trail.
                    if (!kael || a.Heavy)
                    {
                        var tilt = comboIndex == 99 ? 8f : comboIndex == 1 ? -15f : 12f;
                        VfxManager.Instance?.SlashArc(transform, new Vector3(0, HeightM * 0.72f, 0.3f), 0, tilt, color, a.Range * 0.95f, a.Heavy ? 0.24f : 0.16f, comboIndex == 1);
                    }
                    SweepHits();
                    return true;
                case "hit_end":
                    hitActive = false;
                    return true;
                case "combo":
                    comboOpen = true;
                    return true;
                case "impact":
                    var center = Position + Facing * (kael ? 1.4f : 0);
                    var radius = kael ? 3.4f : 3.2f;
                    Aoe(center, radius, a.Damage, a.Poise, a.Knock, HitKind.Heavy);
                    VfxManager.Instance?.Shockwave(center, radius * 1.2f, kael ? FxColor(0x6fc8ff) : FxColor(0xb48cff));
                    if (kael) VfxManager.Instance?.SparksDir(center + Vector3.up * 0.2f, Vector3.up, 30, FxColor(0x9fe0ff), 8);
                    VfxManager.Instance?.SmokePuff(center, 6, new Color(0.35f, 0.38f, 0.42f), 0.9f);
                    CombatSystem.Shake(a.Finisher ? 0.4f : 0.3f);
                    CombatSystem.Kick(Vector3.down, a.Finisher ? 0.8f : 0.5f, 0f);
                    G.Input?.Rumble(0.6f, 0.6f, 0.2f, G.Settings.Data.Controls.Vibration);
                    G.Audio?.Play("slam", center);
                    return true;
            }
            return false;
        }

        void SweepHits()
        {
            if (state != State.Attack) return;
            var a = atk;
            var kind = a.Heavy ? HitKind.Heavy : HitKind.Light;
            var b = G.Powerups.Current();
            var tmpl = new HitInfo { Damage = a.Damage * b.DamageMul, Poise = a.Poise * (swingCounter ? 2f : 1f), Kind = kind, Source = this, Crit = swingCounter };
            CombatSystem.Ensure().ArcDamage(Team.Player, Chest, yaw * Mathf.Rad2Deg, a.Range, a.Arc, tmpl, a.Knock, hitSet, -1.6f, 2.4f, OnDealt);
        }

        /// <summary>
        /// Per landed hit: hit-stop by weight (attacker once per swing + every target; finishers/ultimates freeze the
        /// whole world), directional camera kick and FOV punch, rumble, layered impact audio, sparks and a scorch mark.
        /// </summary>
        void OnDealt(IDamageable target, Vector3 point, float applied)
        {
            var ult = state == State.Ult;
            var pulse = state == State.Ability;
            var heavy = ult || (state == State.Attack && atk.Heavy);
            var en = target as Enemy;
            var crit = en != null && en.LastHitCrit;
            var counter = state == State.Attack && swingCounter;
            // Smashing cars gives the full hit feel but no ultimate / energy / stats (no farming parked cars).
            if (target.Team != Team.Neutral)
            {
                UltCharge = Mathf.Min(100, UltCharge + applied * 0.35f);
                Energy = Mathf.Min(100, Energy + (heavy ? 1 : 3));
                if (G.State != null) G.State.D.Stats.DamageDealt += applied;
            }
            lastTarget = target;

            var hs = ult ? CombatFeel.HitstopFinisher : pulse ? CombatFeel.HitstopMedium : state == State.Attack ? atk.Hitstop : CombatFeel.HitstopLight;
            if (crit || counter) hs = Mathf.Max(hs, CombatFeel.HitstopHeavy);
            var global = hs >= CombatFeel.HitstopFinisher - 1e-4f;
            var dir = target.Position - Position; dir.y = 0;
            dir = dir.sqrMagnitude > 1e-4f ? dir.normalized : Facing;
            en?.HitFreeze(hs, dir, heavy ? 0.06f : 0.035f);
            if (!swingStopped)
            {
                swingStopped = true;
                if (global) CombatSystem.Hitstop(hs);
                else Freeze(hs);
                CombatTelemetry.Record(global ? "hitstop_global" : "hitstop_local", hs, applied);
                var kick = ult ? 1.2f : pulse ? 0.45f : state == State.Attack ? atk.Kick : 0.3f;
                var fov = ult ? -6f : pulse ? -2.5f : state == State.Attack ? atk.Fov : 0f;
                if (crit || counter) { kick *= 1.3f; fov -= 1.5f; }
                CombatSystem.Kick(dir, kick, fov);
                CombatSystem.Shake(heavy ? 0.22f : 0.08f);
                var rumble = state == State.Attack ? atk.Rumble : heavy ? 0.9f : 0.4f;
                if (crit || counter) rumble = Mathf.Max(rumble, 0.7f);
                G.Input?.Rumble(rumble * 0.8f, rumble, heavy ? 0.16f : 0.08f, G.Settings.Data.Controls.Vibration);
                if (global || crit || counter) CombatPostFx.Impact(global ? 1f : 0.55f);
                weaponFx?.Pulse(heavy ? 1.2f : 0.6f);
                if (counter) counterUntil = -1f;
            }
            var col = Character == Characters.Kael ? FxColor(0x9fe0ff) : FxColor(0xe0a8ff);
            VfxManager.Instance?.SparksDir(point, dir, heavy ? 26 : crit ? 20 : 12, col, heavy ? 9 : 7);
            VfxManager.Instance?.SparksDir(point, Vector3.Reflect(-dir, Vector3.up) + Vector3.up * 0.4f, heavy ? 12 : 6, FxColor(0xffc070), 6);
            VfxManager.Instance?.FlashSprite(point, heavy ? 1.8f : crit ? 1.6f : 1.1f, Color.white, heavy ? 0.09f : 0.06f);
            VfxManager.Instance?.LightProto(point, Character == Characters.Kael ? FxColor(0x7fd0ff) : FxColor(0xc890ff), heavy ? 28 : 18, 0.12f);
            if (en != null) HitFx.Mark(en.transform, point, -dir, Character == Characters.Kael ? FxColor(0xffd9a0) : FxColor(0xffb0f0), heavy ? 0.45f : 0.3f);
            // Layered impact: body thud + metal clang + aether zap (+ crit sting).
            G.Audio?.Play(heavy ? "hit_heavy" : "hit", point);
            G.Audio?.Play("impact_clang", point, heavy ? 0.9f : 0.6f, heavy ? 0.85f : 1f);
            G.Audio?.Play("impact_zap", point, heavy ? 0.7f : 0.45f);
            if (crit || counter) G.Audio?.Play("crit_hit", point, 0.9f);
        }

        /// <summary>Hit-stop this hero for `seconds` of real time (animation and movement freeze).</summary>
        void Freeze(float seconds)
        {
            if (freezeT <= 0f) freezeStartReal = Time.realtimeSinceStartup;
            freezeT = Mathf.Max(freezeT, seconds);
        }

        int Aoe(Vector3 center, float radius, float damage, float poise, float knock, HitKind kind)
        {
            var b = G.Powerups.Current();
            var tmpl = new HitInfo { Damage = damage * b.DamageMul, Poise = poise, Kind = kind, Source = this };
            return CombatSystem.Ensure().RadialDamage(Team.Player, center, radius, tmpl, knock, null, 4f, 0.4f, OnDealt);
        }

        void UseAbility()
        {
            var st = Stats;
            if (cdAbility > 0) { G.Audio?.Play("error", Position); return; }
            if (Character == Characters.Kael)
            {
                if (!G.State.HasAbility("pulse")) return;
                if (Energy < 35) { G.Audio?.Play("error", Position); return; }
                Energy -= 35;
                cdAbility = 6 * st.CooldownMul;
                state = State.Ability; stateT = 0; abilityEventT = -1;
                velocity = new Vector3(0, velocity.y, 0);
                Bus.Emit(new AbilityUsed { Ability = "pulse", Character = Character });
                G.Audio?.Play("charge", Position);
                CombatTelemetry.Record("ability_pulse");
                PlayAction("k_pulse", 0.06f, 1, () => { if (state == State.Ability) state = State.Move; }, e =>
                {
                    if (e != "pulse") return false;
                    abilityEventT = stateT;
                    var c = Position;
                    var r = st.PulseRadius;
                    var hits = Aoe(c, r, st.PulseDamage, 30 * st.PulseStagger + 30, 8 * st.PulseStagger, HitKind.Pulse);
                    VfxManager.Instance?.Shockwave(c, r, FxColor(0x5fd8ff), 0.5f);
                    VfxManager.Instance?.Shockwave(c, r * 0.6f, Color.white, 0.3f);
                    VfxManager.Instance?.SparksDir(c + Vector3.up * 0.3f, Vector3.up, 40, FxColor(0x7fd8ff), 9);
                    VfxManager.Instance?.LightProto(c + Vector3.up, FxColor(0x5fd8ff), 60, 0.4f);
                    CombatSystem.Shake(0.45f);
                    CombatSystem.Kick(Vector3.down, 0.6f, -3f);
                    CombatPostFx.Impact(0.35f);
                    G.Input?.Rumble(0.8f, 0.8f, 0.26f, G.Settings.Data.Controls.Vibration);
                    G.Audio?.Play("pulse", c);
                    CombatTelemetry.Record("pulse_hits", hits);
                    return true;
                });
            }
            else
            {
                if (!G.State.HasAbility("echo") || Energy < 25) { G.Audio?.Play("error", Position); return; }
                Energy -= 25;
                cdAbility = 4 * st.CooldownMul;
                state = State.Ability; stateT = 0; abilityEventT = -1;
                Bus.Emit(new AbilityUsed { Ability = "echo", Character = Character });
                PlayAction("l_echo", 0.08f, 1, () => { if (state == State.Ability) state = State.Move; }, e =>
                {
                    if (e != "echo") return false;
                    abilityEventT = stateT;
                    G.Manager.EchoPulse(Position, st.EchoRange, st.EchoDuration);
                    G.Audio?.Play("echo", Position);
                    return true;
                });
            }
        }

        void UseUltimate()
        {
            var st = Stats;
            if (!st.Ultimates) return;
            if (UltCharge < 100) { G.Audio?.Play("error", Position); return; }
            UltCharge = 0;
            state = State.Ult; stateT = 0; abilityEventT = -1;
            invuln = 1.8f;
            var kael = Character == Characters.Kael;
            Bus.Emit(new AbilityUsed { Ability = kael ? "core_break" : "resonance", Character = Character });
            G.Audio?.Play("ult_charge", Position);
            CombatTelemetry.Record("ultimate");
            lungeTarget = SoftLockTarget(8, StickWorld());
            lungeT = kael ? 0.85f : 0;
            PlayAction(kael ? "k_ult" : "l_ult", 0.08f, 1, () => { if (state == State.Ult) state = State.Move; }, e =>
            {
                if (e != "impact") return false;
                abilityEventT = stateT;
                var c = Position;
                var r = kael ? 9 : 8;
                Aoe(c, r, kael ? 150 : 115, 200, kael ? 12 : 6, HitKind.Ultimate);
                if (!kael) foreach (var en in Enemy.All) if (en != null && en.Alive && Vector3.Distance(en.Position, c) < r) en.Stun(3);
                var col = kael ? FxColor(0x5fd8ff) : FxColor(0xb48cff);
                VfxManager.Instance?.Shockwave(c, r, col, 0.7f);
                VfxManager.Instance?.Shockwave(c, r * 0.7f, Color.white, 0.45f);
                VfxManager.Instance?.Shockwave(c + Vector3.up * 1.2f, r * 0.5f, col, 0.6f);
                VfxManager.Instance?.SparksDir(c + Vector3.up * 0.5f, Vector3.up, 80, col, 14);
                VfxManager.Instance?.FlashSprite(c + Vector3.up, 8, col, 0.3f);
                VfxManager.Instance?.LightProto(c + Vector3.up * 2, col, 120, 0.6f);
                CombatSystem.Shake(0.8f);
                CombatSystem.Kick(Vector3.down, 1.2f, -7f);
                CombatPostFx.Impact(1f);
                G.Input?.Rumble(1, 1, 0.5f, G.Settings.Data.Controls.Vibration);
                CombatSystem.Hitstop(CombatFeel.HitstopFinisher);
                G.Audio?.Play("ult_impact", c);
                return true;
            });
        }

        void StartDash(Vector3? wish)
        {
            var st = Stats;
            var kael = Character == Characters.Kael;
            CancelActions();
            dashDir = wish.HasValue ? new Vector3(wish.Value.x, 0, wish.Value.z).normalized : kael ? Facing : -Facing;
            var dist = st.DashDistance * G.Powerups.Current().DashMul;
            dashSpeed = dist / DashTime;
            state = State.Dash; stateT = 0;
            invuln = Mathf.Max(invuln, st.DashIframes);
            dashCharges--;
            if (cdDash <= 0) cdDash = st.DashCooldown * st.CooldownMul;
            if (wish.HasValue) yaw = Mathf.Atan2(dashDir.x, dashDir.z);
            PlayAction(kael ? "dash" : "phase_step", 0.03f);
            VfxManager.Instance?.FlashSprite(Chest, 2, HeroColor, 0.12f);
            VfxManager.Instance?.Embers(Chest, 14, HeroColor, 0.8f, 0.5f);
            G.Audio?.Play(kael ? "dash" : "step", Position);
            Bus.Emit(new AbilityUsed { Ability = kael ? "dash" : "step", Character = Character });
            dashStartT = Time.time;
            perfectThisDash = false;
            CombatTelemetry.Record("dash");
            // Predictive perfect dodge: an enemy blow (or bolt) is about to land as the dodge starts.
            var threat = ImminentThreat();
            if (threat != null) PerfectDodge(threat);
        }

        /// <summary>"melee"/"projectile" when an enemy attack will reach the hero within the perfect-dodge window.</summary>
        string ImminentThreat()
        {
            var all = Enemy.All;
            for (var i = 0; i < all.Count; i++)
            {
                var e = all[i];
                if (e == null || !e.Alive) continue;
                var tin = e.ThreatIn;
                if (tin < 0f || tin > CombatFeel.PerfectDodgeWindow) continue;
                var reach = (e.Def != null ? e.Def.AttackRange : 2.5f) + e.Radius + Radius + 1.6f;
                if (FlatDist(Position, e.Position) > reach || e.FacingTo(Position) > 1.2f) continue;
                return "melee";
            }
            var cs = CombatSystem.Instance;
            return cs != null && cs.ProjectileThreat(Team.Player, AimPoint, 0.9f, 0.2f) ? "projectile" : null;
        }

        /// <summary>
        /// Perfect dodge (Wukong style): brief slow motion, a cool desaturated "focus" frame, an afterimage burst, extended
        /// i-frames and a counter window in which the next swing crits with double poise damage.
        /// </summary>
        void PerfectDodge(string kind)
        {
            if (perfectThisDash) return;
            perfectThisDash = true;
            invuln = Mathf.Max(invuln, 0.5f);
            counterUntil = Time.unscaledTime + CombatFeel.CounterWindow;
            CombatSystem.SlowMo(CombatFeel.PerfectSlowScale, CombatFeel.PerfectSlowSeconds);
            CombatPostFx.Focus(CombatFeel.PerfectSlowSeconds);
            Energy = Mathf.Min(100, Energy + 10);
            UltCharge = Mathf.Min(100, UltCharge + 6);
            var col = Character == Characters.Kael ? FxColor(0x9fe8ff) : FxColor(0xe0b0ff);
            // Afterimage burst: kept small, it plays in slow motion (~3x longer on screen).
            VfxManager.Instance?.FlashSprite(Chest, 1.5f, col, 0.08f);
            VfxManager.Instance?.Shockwave(Position + Vector3.up * 0.05f, 1.4f, col, 0.18f);
            VfxManager.Instance?.Embers(Chest, 18, col, 0.7f, 0.5f);
            G.Audio?.Play("perfect_dodge", Position);
            G.Input?.Rumble(0.25f, 0.5f, 0.12f, G.Settings.Data.Controls.Vibration);
            if (CombatTelemetry.Enabled) CombatTelemetry.Record("perfect_dodge_" + kind, Time.time - dashStartT);
        }

        /// <summary>Heavy-swing deflect: the blow is turned aside, the attacker reels (long stagger) and a counter opens.</summary>
        void Deflect(Enemy foe, Vector3 point)
        {
            deflectUntil = 0;
            LastAppliedDamage = 0;
            foe.Deflected(this);
            Freeze(CombatFeel.HitstopHeavy);
            var dir = Flat(foe.Position - Position).normalized;
            foe.HitFreeze(CombatFeel.HitstopHeavy, dir, 0.08f);
            counterUntil = Time.unscaledTime + CombatFeel.CounterWindow;
            CombatSystem.SlowMo(0.5f, 0.3f);
            CombatPostFx.Impact(0.7f);
            CombatSystem.Kick(dir, 0.9f, -3f);
            var p = point.sqrMagnitude > 0.01f ? point : Chest + dir * 0.8f;
            VfxManager.Instance?.SparksDir(p, -dir + Vector3.up * 0.3f, 40, FxColor(0xffe0a0), 10);
            WeaponFx.Parry(p, -dir, FxColor(0xffe0a0));
            weaponFx?.Pulse(1.5f);
            VfxManager.Instance?.LightProto(p, FxColor(0xffe0a0), 60, 0.2f);
            G.Audio?.Play("parry", p);
            G.Audio?.Play("shield_block", p, 0.8f, 0.8f);
            G.Input?.Rumble(0.9f, 0.6f, 0.2f, G.Settings.Data.Controls.Vibration);
            CombatTelemetry.Record("deflect");
        }

        void DriveWeapon(float dt)
        {
            if (weaponFx == null) return;
            var fighting = state == State.Attack || state == State.Ult || (state == State.Ability && Character == Characters.Lyra);
            if (fighting) armedT = 0.9f;
            else armedT -= dt;
            var kaelHero = Character == Characters.Kael;
            // Kael's hard-light blade exists only during the attack (wind-up to recovery), on the striking arm: k_light2
            // leads with the left hand (blade from the left Interface), the ultimate uses both. Giva's claws linger.
            weaponFx.Armed = Alive && state != State.Scripted && state != State.Dead && (kaelHero ? state == State.Attack || state == State.Ult : fighting || armedT > 0f);
            weaponFx.BladeLeft = state == State.Ult || (state == State.Attack && atk.Clip == "k_light2");
            weaponFx.BladeRight = state == State.Ult || !(state == State.Attack && atk.Clip == "k_light2");
            weaponFx.Swing = (state == State.Attack && actionClipT >= atk.Active0 - 0.07f && actionClipT <= atk.Active1 + 0.05f)
                             || (state == State.Ult && actionClipT > 0.6f && actionClipT < 1.0f);
            // Ranged weapon: drawn while aiming (and briefly after a shot); any melee / dodge / stagger puts it away.
            weaponFx.Stowed = !Alive || state == State.Scripted || state == State.Dead;
            weaponFx.Melee = state == State.Attack || state == State.Ult || state == State.Ability || state == State.Dash || state == State.Hit;
            weaponFx.Aiming = state == State.Aim;
            if (state == State.Aim && G.Manager?.Cam != null && !G.Manager.Cam.Cinematic.HasValue) weaponFx.AimPoint = G.Manager.Cam.AimPoint();
        }

        // ------------------------------------------------------------------ telemetry (autopilot combat-feel test)

        public static string LastState(Hero h) => h != null ? h.state.ToString() : "-";
        public bool CounterReady => Time.unscaledTime < counterUntil;
        public bool Frozen => freezeT > 0f;

        /// <summary>Test hooks (weapon close-up capture): hold the aim, fire a bolt, hold the current pose (hit-stop style).</summary>
        public void DebugAim(bool on)
        {
            if (on && state == State.Move) EnterAim();
            else if (!on && state == State.Aim) ExitAim();
        }

        public void DebugBolt()
        {
            cdBolt = 0f;
            Energy = Mathf.Max(Energy, 30f);
            FireBolt(state == State.Aim);
            // in play the facing snap lands in the same Update; a test press arrives outside it
            transform.rotation = Quaternion.Euler(0, yaw * Mathf.Rad2Deg, 0);
        }

        public void DebugHold(float seconds) => Freeze(seconds);

        /// <summary>Test hook: fill the ultimate gauge.</summary>
        public void DebugFillUltimate() => UltCharge = 100;

        void ArmProbe(string kind, bool fromPress)
        {
            if (!fromPress) kind += "_queued";
            var hand = Model != null ? Model.Bone(Character == Characters.Kael ? HumanBodyBones.RightHand : HumanBodyBones.LeftHand) : null;
            if (hand == null) return;
            probeFrame = Time.frameCount;
            probeReal = Time.realtimeSinceStartup;
            probeHand = transform.InverseTransformPoint(hand.position);
            probeRoot = transform.position;
            probeKind = kind;
        }

        void LateUpdate()
        {
            if (probeFrame < 0 || !CombatTelemetry.Enabled) return;
            var hand = Model != null ? Model.Bone(Character == Characters.Kael ? HumanBodyBones.RightHand : HumanBodyBones.LeftHand) : null;
            if (hand == null) { probeFrame = -1; return; }
            var moved = (transform.InverseTransformPoint(hand.position) - probeHand).magnitude;
            var rootMoved = (transform.position - probeRoot).magnitude;
            if (moved > 0.02f || rootMoved > 0.01f)
            {
                CombatTelemetry.Record("first_motion_" + probeKind, Time.frameCount - probeFrame, (Time.realtimeSinceStartup - probeReal) * 1000f);
                probeFrame = -1;
            }
            else if (Time.frameCount - probeFrame > 30)
            {
                CombatTelemetry.Record("no_motion_" + probeKind, 30);
                probeFrame = -1;
            }
        }

        void EnterAim()
        {
            state = State.Aim; stateT = 0;
            G.Manager.Cam.Aiming = true;
            PlayUpper(Character == Characters.Kael ? "aim_r" : "aim_l", 0.1f);
        }

        void ExitAim()
        {
            state = State.Move;
            G.Manager.Cam.Aiming = false;
            StopUpper(0.2f);
        }

        Vector3 BoltOrigin()
        {
            var hand = Model?.Bone(Character == Characters.Kael ? HumanBodyBones.RightHand : HumanBodyBones.LeftHand);
            return hand != null ? hand.position + Facing * 0.15f : Chest + Facing * 0.3f;
        }

        void FireBolt(bool aimed)
        {
            if (cdBolt > 0) return;
            if (Energy < 6) { G.Audio?.Play("error", Position); return; }
            Energy -= 6;
            cdBolt = 0.28f;
            var kael = Character == Characters.Kael;
            var cam = G.Manager.Cam;
            var cs = CombatSystem.Ensure();
            IDamageable target;
            Vector3 dir;
            // The bolt leaves the weapon: Kael's pistol muzzle / Giva's palm emitter in the aim pose.
            var aimAt = aimed ? cam.AimPoint() : Vector3.zero;
            if (!aimed)
            {
                target = LockTarget ?? cs.BestTarget(Team.Player, Chest, cam.LookDir, 40, 28, true) ?? cs.BestTarget(Team.Player, Chest, Facing, 25, 40, true);
                aimAt = target != null ? target.AimPoint : cam.AimPoint();
            }
            else target = cs.BestTarget(Team.Player, cam.Cam.transform.position, cam.Cam.transform.forward, 60, 4, true);
            var from = weaponFx != null ? weaponFx.MuzzleFor(aimAt - Chest) : BoltOrigin();
            dir = (aimAt - from).normalized;
            if (!aimed) yaw = Mathf.Atan2(dir.x, dir.z);
            var st = Stats;
            var color = kael ? FxColor(0x6fd0ff) : FxColor(0xb48cff);
            var shots = kael ? 1 : 2;
            for (var i = 0; i < shots; i++)
            {
                var d = i > 0 ? Quaternion.Euler(0, 2.3f, 0) * dir : dir;
                var spec = ProjectileSpec.Make(from, d, 42, st.BoltDamage * G.Powerups.Current().DamageMul, Team.Player, color, this);
                spec.Homing = target; spec.Turn = aimed ? 2 : 6; spec.Kind = HitKind.Bolt; spec.Poise = 6; spec.Size = kael ? 0.13f : 0.1f;
                cs.Fire(spec);
            }
            weaponFx?.Fired(dir);
            PlayUpper(kael ? "fire_r" : "fire_l", aimed ? 0.02f : 0.04f);
            G.Audio?.Play(kael ? "pistol_shot" : "gauntlet_shot", from);
            G.Audio?.Play("bolt", from, 0.55f);
        }

        // ------------------------------------------------------------------ scripted & companion

        void UpdateScripted(float dt)
        {
            if (scriptedGoal.HasValue)
            {
                var g = scriptedGoal.Value;
                if (FlatDist(Position, g) < 0.25f)
                {
                    scriptedGoal = null;
                    velocity = new Vector3(0, velocity.y, 0);
                    scriptedDone?.TrySetResult(true);
                }
                else
                {
                    var dir = g - Position; dir.y = 0; dir.Normalize();
                    velocity.x = Damp(velocity.x, dir.x * scriptedSpeed, 8, dt);
                    velocity.z = Damp(velocity.z, dir.z * scriptedSpeed, 8, dt);
                    yaw = DampAngle(yaw, Mathf.Atan2(dir.x, dir.z), 8, dt);
                }
            }
            else
            {
                var k = Mathf.Exp(-10 * dt);
                velocity.x *= k; velocity.z *= k;
            }
            MoveBody(dt, velocity);
        }

        /// <summary>Walk to a point (cinematics). Completes on arrival.</summary>
        public Task WalkTo(Vector3 target, float speed = 1.6f)
        {
            scriptedDone?.TrySetResult(false);
            state = State.Scripted;
            scriptedGoal = target;
            scriptedSpeed = speed;
            scriptedDone = new TaskCompletionSource<bool>();
            return scriptedDone.Task;
        }

        public void SetScripted(bool on)
        {
            if (on)
            {
                SetCrouch(false);
                CancelActions();
                state = State.Scripted;
                velocity = Vector3.zero;
            }
            else
            {
                scriptedGoal = null;
                scriptedDone?.TrySetResult(false);
                if (state == State.Scripted) state = Alive ? State.Move : State.Dead;
            }
        }

        public void FaceTowards(Vector3 p) => yaw = YawTo(Position, p);

        void UpdateCompanion(float dt)
        {
            var leader = FollowLeader;
            if (leader == null) { UpdatePhysicsOnly(dt); return; }
            if (trail.Count == 0 || Vector3.Distance(trail[trail.Count - 1], leader.Position) > 0.8f)
            {
                trail.Add(leader.Position);
                if (trail.Count > 40) trail.RemoveAt(0);
            }
            var lf = leader.Facing;
            var side = new Vector3(lf.z, 0, -lf.x);
            var slot = leader.Position - lf * 2.0f + side * 1.3f;
            var dist = FlatDist(Position, leader.Position);
            var goal = slot;
            if (dist > 6 && trail.Count > 0)
            {
                while (trail.Count > 1 && FlatDist(trail[0], Position) < 1.2f) trail.RemoveAt(0);
                goal = trail[0];
            }
            var toGoal = goal - Position; toGoal.y = 0;
            var dGoal = toGoal.magnitude;
            float speed = 0;
            if (dGoal > 0.6f) speed = dist > 9 ? 7.4f : dist > 4 ? 5.2f : 2.6f;
            var want = dGoal > 0.01f ? toGoal.normalized * speed : Vector3.zero;
            velocity.x = Damp(velocity.x, want.x, 7, dt);
            velocity.z = Damp(velocity.z, want.z, 7, dt);
            if (speed > 0.5f) yaw = DampAngle(yaw, Mathf.Atan2(want.x, want.z), 9, dt);
            else yaw = DampAngle(yaw, leader.yaw, 3, dt);
            if (leader.Position.y - Position.y > 0.6f && cc.isGrounded && dGoal < 3) velocity.y = 7.6f;
            MoveBody(dt, velocity);
            var moved = Vector3.Distance(Position, lastPos);
            lastPos = Position;
            if (speed > 2 && moved < speed * dt * 0.2f) stuckT += dt; else stuckT = Mathf.Max(0, stuckT - dt);
            if (dist > 28 || stuckT > 1.6f || Mathf.Abs(leader.Position.y - Position.y) > 6)
            {
                var behind = leader.Position - lf * 2.5f;
                var target = leader.Position;
                if (Physics.Raycast(behind + Vector3.up * 1.5f, Vector3.down, out var hit, 4, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore) && Mathf.Abs(hit.point.y - leader.Position.y) < 1.5f)
                    target = hit.point + Vector3.up * 0.05f;
                var cam = G.Manager.Cam;
                if (cam == null || !cam.Sees(target + Vector3.up)) // teleport out of sight when possible
                {
                    Teleport(target, YawDeg);
                    stuckT = 0;
                    VfxManager.Instance?.Embers(Chest, 10, HeroColor, 0.6f, 0.6f);
                }
            }
            supportT -= dt;
            if (supportT <= 0 && G.Manager.InCombat)
            {
                supportT = 2.2f + UnityEngine.Random.value * 1.5f;
                var t = CombatSystem.Ensure().BestTarget(Team.Player, Chest, Facing, 22, 180, true, false);
                if (t != null)
                {
                    var from = weaponFx != null ? weaponFx.MuzzleFor(t.AimPoint - Chest) : Chest;
                    var dir = (t.AimPoint - from).normalized;
                    yaw = Mathf.Atan2(dir.x, dir.z);
                    weaponFx?.Fired(dir);
                    var spec = ProjectileSpec.Make(from, dir, 36, Stats.BoltDamage * 0.6f, Team.Player, Character == Characters.Kael ? FxColor(0x6fd0ff) : FxColor(0xb48cff), this);
                    spec.Homing = t; spec.Turn = 4; spec.Kind = HitKind.Bolt; spec.Poise = 4; spec.Size = 0.09f;
                    CombatSystem.Ensure().Fire(spec);
                    PlayUpper(Character == Characters.Kael ? "fire_r" : "fire_l", 0.05f);
                    G.Audio?.Play("bolt", from, 0.5f);
                }
            }
        }
    }
}
