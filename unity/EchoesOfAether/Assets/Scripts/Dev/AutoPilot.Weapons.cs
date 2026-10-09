using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Weapon close-ups (-executeMethod EOA.EditorTools.SmokeTest.RunWeapons → Captures/weapons): for Kael and Giva the
    /// holstered / idle weapons, each melee swing frozen at its active frame and filmed from three angles, the aim pose,
    /// the shot (muzzle flash, bolt in flight, impact); then the drone blaster, the Sentinel blade and the Guardian's arm
    /// cannon / folding blade at rest and in action. A per-frame camera rig follows the weapon bones.
    /// </summary>
    public sealed partial class AutoPilot
    {
        [DefaultExecutionOrder(160)]
        sealed class WeaponCam : MonoBehaviour
        {
            public Func<(Vector3 pos, Vector3 look, float fov)> Shot;
            /// <summary>Inspection light next to the camera (enemy weapon close-ups only: the robots are near-black at night).</summary>
            public bool Lamp;
            Light lamp;

            void LateUpdate()
            {
                if (lamp == null)
                {
                    var go = new GameObject("WeaponInspectionLight");
                    lamp = go.AddComponent<Light>();
                    lamp.type = LightType.Point;
                    lamp.color = new Color(0.85f, 0.9f, 1f);
                    lamp.shadows = LightShadows.None;
                }
                lamp.enabled = Lamp && Shot != null;
                if (Shot == null || G.Manager == null || G.Manager.Cam == null) return;
                var s = Shot();
                G.Manager.Cam.Cinematic = s;
                if (lamp.enabled)
                {
                    float d = Vector3.Distance(s.pos, s.look);
                    lamp.transform.position = s.pos + Vector3.up * 0.4f * d;
                    lamp.range = d * 3f;
                    lamp.intensity = 3f + d * 0.6f;
                }
            }
        }

        /// <summary>Freeze the world (global hit-stop) for a capture of a short-lived effect.</summary>
        static void FreezeWorld(float seconds) => CombatSystem.Hitstop(seconds);

        WeaponCam wcam;
        readonly Dictionary<string, object> weaponReport = new();

        async Task WeaponShots()
        {
            await Seconds(2);
            var ng = M.NewGame(Characters.Kael, 2);
            await WaitFor("plaza", () => ng.IsFaulted || (M.World.ZoneId == "plaza" && M.Mode == GameMode.Play && !M.World.Loading), 180);
            if (M.Cinematics.Active != null) M.Cinematics.Stop();
            await Seconds(2);
            await Flush(60);
            if (M.Player == null) { errors.Add("weapons: no player"); return; }
            wcam = gameObject.AddComponent<WeaponCam>();
            foreach (var who in new[] { Characters.Kael, Characters.Lyra })
            {
                if (G.State.D.Character != who && !await SwapTo(who)) continue;
                try { await HeroWeaponShots(who); }
                catch (Exception e) { errors.Add($"weapons: {who} shots failed: {e}"); }
                wcam.Shot = null;
                M.Cam.Cinematic = null;
            }
            try { await EnemyWeaponShots(); }
            catch (Exception e) { errors.Add("weapons: enemy shots failed: " + e); }
            wcam.Shot = null;
            M.Cam.Cinematic = null;
            report["weapons"] = weaponReport;
        }

        static Vector3 EFwd(Enemy e) => Quaternion.Euler(0f, e.YawDeg, 0f) * Vector3.forward;
        static Vector3 ERight(Enemy e) => Quaternion.Euler(0f, e.YawDeg, 0f) * Vector3.right;

        static Transform Bone(Hero p, HumanBodyBones b) => p.Model != null ? p.Model.Bone(b) : null;

        /// <summary>Camera around a moving subject: offset in the hero's frame (right, up, forward).</summary>
        void Follow(Func<Vector3> subject, Hero frame, Vector3 offset, float fov)
        {
            wcam.Shot = () =>
            {
                var s = subject();
                var t = frame.transform;
                return (s + t.right * offset.x + Vector3.up * offset.y + t.forward * offset.z, s, fov);
            };
        }

        async Task HeroWeaponShots(string who)
        {
            var p = M.Player;
            var tag = who == Characters.Kael ? "kael" : "giva";
            var kael = who == Characters.Kael;
            Invuln();
            G.State.Unlock(kael ? "dash" : "step");
            foreach (var e in Enemy.All.ToList()) if (e != null) e.Despawn();
            await Seconds(1f);
            var handMain = kael ? HumanBodyBones.RightHand : HumanBodyBones.LeftHand;
            var foreMain = kael ? HumanBodyBones.RightLowerArm : HumanBodyBones.LeftLowerArm;
            Vector3 B(HumanBodyBones b) { var t = Bone(p, b); return t != null ? t.position : p.Chest; }
            Vector3 Hip() => Vector3.Lerp(B(HumanBodyBones.RightUpperLeg), B(HumanBodyBones.RightLowerLeg), 0.35f);
            Vector3 Forearm() => Vector3.Lerp(B(foreMain), B(handMain), 0.6f);
            // blade / claw centre: past the fist along the forearm
            Vector3 Weapon() { var h = B(handMain); var d = (h - B(foreMain)).normalized; return h + d * (kael ? 0.38f : 0.08f); }

            // 1) idle: weapons at rest
            Follow(Forearm, p, new Vector3(kael ? 0.75f : -0.75f, 0.2f, 0.45f), 30f);
            await Seconds(0.5f);
            await Capture($"w_{tag}_01_idle_forearm");
            if (kael)
            {
                Follow(Hip, p, new Vector3(0.9f, 0.12f, 0.3f), 32f);
                await Seconds(0.4f);
                await Capture($"w_{tag}_02_idle_holster");
                Follow(Hip, p, new Vector3(0.75f, 0.2f, -0.55f), 32f);
                await Seconds(0.3f);
                await Capture($"w_{tag}_03_idle_holster_back");
            }
            else
            {
                Follow(() => (B(HumanBodyBones.LeftHand) + B(HumanBodyBones.RightHand)) * 0.5f, p, new Vector3(0.25f, 0.2f, 1.2f), 40f);
                await Seconds(0.4f);
                await Capture($"w_{tag}_02_idle_gauntlets");
                Follow(() => B(HumanBodyBones.LeftHand), p, new Vector3(-0.55f, 0.15f, 0.35f), 30f);
                await Seconds(0.3f);
                await Capture($"w_{tag}_03_idle_gauntlet_close");
            }

            // 2) melee: each swing frozen at its active frame, three angles
            var dummy = Spawn("sentinel", p.Position + p.transform.forward * 2.7f, p.YawDeg + 180f);
            if (dummy != null) dummy.Frozen = true;
            await Seconds(0.8f);
            // swing i = the i-th hit of a chained combo (light1, light2 [Kael: left arm], light3, heavy)
            var swings = kael ? new[] { "light", "light", "light", "heavy" } : new[] { "light", "light", "heavy" };
            for (var i = 0; i < swings.Length; i++)
            {
                Invuln();
                for (var k = 0; k <= i; k++)
                {
                    p.InjectPress(swings[k]);
                    await Seconds(k < i ? 0.3f : swings[k] == "heavy" ? 0.36f : 0.2f);
                }
                p.DebugHold(2.8f);
                Follow(Weapon, p, new Vector3(2.3f, 0.3f, 0.3f), 40f);
                await Seconds(0.08f);
                await Capture($"w_{tag}_1{i}_swing_side");
                Follow(Weapon, p, new Vector3(-0.9f, 0.45f, 2.2f), 42f);
                await Seconds(0.08f);
                await Capture($"w_{tag}_1{i}_swing_front");
                Follow(Weapon, p, new Vector3(0.8f, 0.9f, -2.3f), 44f);
                await Seconds(0.08f);
                await Capture($"w_{tag}_1{i}_swing_back");
                await Seconds(2.6f);
            }
            dummy?.Despawn();
            p.Restore();
            await Seconds(1.2f);

            // 3) ranged: aim pose (gameplay camera sets the aim point, then close-ups keep it), shots at a target
            var target = Spawn("sentinel", p.Position + p.transform.forward * 8f, p.YawDeg + 180f);
            if (target != null) target.Frozen = true;
            M.Cam.SnapBehind(p.YawDeg * Mathf.Deg2Rad);
            wcam.Shot = null;
            M.Cam.Cinematic = null;
            await Seconds(0.6f);
            p.DebugAim(true);
            await Seconds(0.8f);
            await Capture($"w_{tag}_20_aim_gameplay");
            Follow(() => B(handMain), p, new Vector3(kael ? 1.0f : -1.0f, 0.15f, 0.35f), 36f);
            await Seconds(0.1f);
            await Capture($"w_{tag}_21_aim_side");
            Follow(() => B(handMain), p, new Vector3(kael ? 0.45f : -0.45f, 0.2f, 1.3f), 40f);
            await Seconds(0.1f);
            await Capture($"w_{tag}_22_aim_front");
            p.DebugAim(false);
            wcam.Shot = null;
            M.Cam.Cinematic = null;
            M.Cam.SnapBehind(p.YawDeg * Mathf.Deg2Rad);
            await Seconds(1.4f);
            // tap shot: world frozen on the muzzle flash
            Follow(() => B(handMain), p, new Vector3(kael ? 1.3f : -1.3f, 0.25f, 0.9f), 44f);
            await Seconds(0.15f);
            p.DebugBolt();
            await Awaitable.NextFrameAsync();
            FreezeWorld(0.8f);
            p.DebugHold(1.0f);
            await Capture($"w_{tag}_23_shot_muzzle");
            await Seconds(1.2f);
            // bolt in flight: frozen ~2.5 m out of the muzzle
            Follow(() => p.Chest + p.transform.forward * 2.6f, p, new Vector3(2.4f, 0.35f, 0f), 50f);
            await Seconds(0.15f);
            var cs = CombatSystem.Ensure();
            p.DebugBolt();
            await Seconds(0.05f);
            FreezeWorld(0.8f);
            await Capture($"w_{tag}_24_bolt_flight");
            await Seconds(1.0f);
            if (target != null)
            {
                Follow(() => target.AimPoint, p, new Vector3(2.0f, 0.5f, -1.4f), 45f);
                await Seconds(0.15f);
                p.DebugBolt();
                await Seconds(0.05f);
                await Until(() => cs.ActiveProjectiles == 0, 2f);
                FreezeWorld(0.8f);
                await Capture($"w_{tag}_25_impact");
            }
            // tap fire from the holster in the gameplay camera
            wcam.Shot = null;
            M.Cam.Cinematic = null;
            M.Cam.SnapBehind(p.YawDeg * Mathf.Deg2Rad);
            await Seconds(1.8f);
            p.DebugBolt();
            await Seconds(0.1f);
            await Capture($"w_{tag}_26_tapfire_gameplay");
            await Seconds(0.8f);
            target?.Despawn();
            // a wall / floor shot: scorch decal
            await Seconds(1.2f);
            p.DebugBolt();
            await Seconds(0.5f);
            weaponReport[tag + "_done"] = true;
            p.Restore();
        }

        async Task EnemyWeaponShots()
        {
            var p = M.Player;
            wcam.Lamp = true;
            Invuln();
            foreach (var e in Enemy.All.ToList()) if (e != null) e.Despawn();
            await Seconds(0.5f);
            var fwd = p.transform.forward;
            var right = p.transform.right;

            // Drone: at rest, then firing
            var drone = Spawn("drone", p.Position + fwd * 6f + Vector3.up * 3f, p.YawDeg + 180f);
            if (drone != null)
            {
                drone.Frozen = true;
                await Seconds(0.6f);
                wcam.Shot = () => (drone.AimPoint + EFwd(drone) * 1.3f + ERight(drone) * 0.9f + Vector3.down * 0.2f, drone.AimPoint, 40f);
                await Seconds(0.2f);
                await Capture("w_enemy_01_drone_blaster");
                drone.Frozen = false;
                drone.SetAggro();
                var cs = CombatSystem.Ensure();
                int before = cs.ActiveProjectiles;
                await Until(() => cs.ActiveProjectiles > before, 10f);
                wcam.Shot = () => (drone.AimPoint + ERight(drone) * 1.8f + Vector3.up * 0.3f, drone.AimPoint + EFwd(drone) * 0.6f, 44f);
                await Capture("w_enemy_02_drone_fire");
                drone.Despawn();
                await Seconds(0.4f);
            }

            // Sentinel: blade at rest, then mid-attack
            var s = Spawn("sentinel", p.Position + fwd * 3.2f, p.YawDeg + 180f);
            if (s != null)
            {
                s.Frozen = true;
                await Seconds(0.6f);
                wcam.Shot = () => (s.Position + Vector3.up * 1.2f + ERight(s) * 2.0f + EFwd(s) * 1.2f, s.Position + Vector3.up * 0.9f + ERight(s) * 0.3f, 42f);
                await Seconds(0.2f);
                await Capture("w_enemy_03_sentinel_blade");
                s.Frozen = false;
                s.SetAggro();
                await Until(() => s.ThreatIn >= 0f && s.ThreatIn < 0.05f, 10f);
                await Seconds(0.08f);
                FreezeWorld(0.8f);
                wcam.Shot = () => (s.Position + Vector3.up * 1.6f + ERight(s) * 3.2f - EFwd(s) * 0.6f, s.Position + Vector3.up * 1.1f, 48f);
                await Capture("w_enemy_04_sentinel_attack");
                s.Despawn();
                await Seconds(0.5f);
            }

            // Guardian: arm cannon (left forearm) and folding blade (right forearm) at rest, the sweep with the blade
            // out, and the laser from the cannon.
            var gpos = p.Position + fwd * 11f;
            var g = Spawn("guardian", gpos, p.YawDeg + 180f);
            if (g != null)
            {
                g.Frozen = true;
                await Seconds(0.8f);
                var cannon = WeaponLibrary.FindDeep(g.transform, "guardian_cannon");
                var blade = WeaponLibrary.FindDeep(g.transform, "guardian_blade");
                Vector3 CannonMid() => cannon != null ? cannon.position + cannon.forward * 0.7f : g.AimPoint;
                Vector3 BladeMid() => blade != null ? blade.position + blade.forward * 0.6f : g.AimPoint;
                wcam.Shot = () => (CannonMid() - ERight(g) * 3.2f + EFwd(g) * 2.2f + Vector3.up * 0.8f, CannonMid(), 42f);
                await Seconds(0.2f);
                await Capture("w_enemy_05_guardian_cannon");
                wcam.Shot = () => (BladeMid() + ERight(g) * 3.2f + EFwd(g) * 2.2f + Vector3.up * 0.8f, BladeMid(), 42f);
                await Seconds(0.2f);
                await Capture("w_enemy_06_guardian_blade_folded");
                // sweep: player in range in front, wait for the sweep's active frames
                g.Frozen = false;
                p.Teleport(g.Position + EFwd(g) * 3.6f, g.YawDeg + 180f);
                var sweptOk = false;
                for (var tries = 0; tries < 6 && !sweptOk; tries++)
                {
                    Invuln();
                    if (!await Until(() => g.ThreatIn >= 0f && g.ThreatIn < 0.08f, 6f)) continue;
                    await Seconds(0.05f);
                    FreezeWorld(1.0f);
                    wcam.Shot = () => (g.Position + Vector3.up * 3.2f + ERight(g) * 5.5f + EFwd(g) * 4.5f, BladeMid(), 50f);
                    await Awaitable.NextFrameAsync();
                    await Capture($"w_enemy_07_guardian_attack_{tries}");
                    sweptOk = tries >= 1;
                    await Seconds(1.2f);
                }
                // laser: damage it into phase 2 and stand at range
                g.ReceiveHit(new HitInfo { Damage = g.MaxHealth * 0.55f / 0.7f, Kind = HitKind.Ultimate, Source = p, Point = g.AimPoint, Pierce = true });
                p.Teleport(g.Position + EFwd(g) * 14f, g.YawDeg + 180f);
                wcam.Shot = () => (g.Position + Vector3.up * 3.6f - ERight(g) * 8f + EFwd(g) * 7f, g.Position + EFwd(g) * 5f + Vector3.up * 2f, 55f);
                for (var i = 0; i < 10; i++)
                {
                    Invuln();
                    await Seconds(0.8f);
                    await Capture($"w_enemy_1{i:00}_guardian_fight");
                }
                g.Despawn();
            }
            wcam.Lamp = false;
            wcam.Shot = null;
        }
    }
}
