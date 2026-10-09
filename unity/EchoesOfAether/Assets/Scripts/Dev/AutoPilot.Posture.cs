using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Gameplay posture check (-executeMethod EOA.EditorTools.SmokeTest.RunPosture): each lead (Kael, then Giva via the
    /// character swap) in the plaza, standing, walking, running, sprinting, in the combat stance, talking and crouching (idle and walk), filmed from
    /// the side and from the front three-quarter. The camera follows the hero every frame (shots of moving heroes used to
    /// miss them) and torso / neck lean, knee bend and the trunk / head twist against the pelvis are averaged over the shot from the final pose (after
    /// <see cref="HeroStance"/> and <see cref="HumanoidPolish"/>), logged as "[posture]" lines and written to report.json.
    /// </summary>
    public sealed partial class AutoPilot
    {
        /// <summary>Frames the hero (before the camera rig, LateUpdate 200) and samples the final pose every frame.</summary>
        [DefaultExecutionOrder(150)]
        sealed class PostureRig : MonoBehaviour
        {
            public Hero Hero;
            public bool Side = true, Track, Sample, Ramp;
            public readonly List<float> Torso = new(), Neck = new(), NeckRel = new(), KneeL = new(), KneeR = new(), Speed = new(), Slip = new();
            /// <summary>Twist against the pelvis (degrees, + = to the character's right): chest (UpperChest, else Chest),
            /// neck and head yaw about the hips' up axis, from the bones' side axes (all along the body's left-right line in
            /// the bind pose of these rigs).</summary>
            public readonly List<float> ChestYaw = new(), NeckYaw = new(), HeadYaw = new();
            /// <summary>Signed trunk pitch (hips→neck, + = forward), how far the head sits ahead of the shoulder joints (cm,
            /// side view) and the hand-to-hand distance (m).</summary>
            public readonly List<float> TrunkPitch = new(), HeadFwd = new(), Hands = new();
            /// <summary>Planted-point tracking for foot slip: bone and its last world position.</summary>
            Transform slipBone;
            Vector3 slipLast;
            /// <summary>Move start: (seconds since the command, hero speed, animator Speed parameter).</summary>
            public readonly List<(float t, float body, float anim)> RampLog = new();
            float rampT0;

            public void StartRamp() { RampLog.Clear(); rampT0 = Time.time; Ramp = true; }

            public void Clear() { Torso.Clear(); Neck.Clear(); NeckRel.Clear(); KneeL.Clear(); KneeR.Clear(); Speed.Clear(); Slip.Clear(); ChestYaw.Clear(); NeckYaw.Clear(); HeadYaw.Clear(); TrunkPitch.Clear(); HeadFwd.Clear(); Hands.Clear(); slipBone = null; }

            void LateUpdate()
            {
                if (Hero == null || G.Manager == null) return;
                if (Track)
                {
                    var p = Hero.Position;
                    var fwd = Hero.transform.forward;
                    var right = Hero.transform.right;
                    var camPos = Side ? p + right * 3.6f + Vector3.up * 1.0f : p + fwd * 3.4f + right * 1.6f + Vector3.up * 1.25f;
                    G.Manager.Cam.Cinematic = (camPos, p + Vector3.up * 0.95f, 40f);
                }
                var an = Hero.Model != null ? Hero.Model.Animator : null;
                if (an == null || !an.isHuman) return;
                if (Ramp) RampLog.Add((Time.time - rampT0, new Vector2(Hero.Velocity.x, Hero.Velocity.z).magnitude, an.GetFloat("Speed")));
                if (!Sample) return;
                Transform B(HumanBodyBones b) => an.GetBoneTransform(b);
                var f = Hero.transform.forward;
                float Pitch(Vector3 d) => Mathf.Atan2(Vector3.Dot(d, f), d.y) * Mathf.Rad2Deg;
                var torso = B(HumanBodyBones.Neck).position - B(HumanBodyBones.Hips).position;
                var neck = B(HumanBodyBones.Head).position - B(HumanBodyBones.Neck).position;
                Torso.Add(Vector3.Angle(torso, Vector3.up));
                Neck.Add(Vector3.Angle(neck, Vector3.up));
                NeckRel.Add(Pitch(neck) - Pitch(torso));
                TrunkPitch.Add(Pitch(torso));
                var shoulders = (B(HumanBodyBones.LeftUpperArm).position + B(HumanBodyBones.RightUpperArm).position) * 0.5f;
                HeadFwd.Add(Vector3.Dot(B(HumanBodyBones.Head).position - shoulders, f) * 100f);
                Hands.Add((B(HumanBodyBones.LeftHand).position - B(HumanBodyBones.RightHand).position).magnitude);
                float Knee(HumanBodyBones u, HumanBodyBones l, HumanBodyBones ft) =>
                    180f - Vector3.Angle(B(u).position - B(l).position, B(ft).position - B(l).position);
                KneeL.Add(Knee(HumanBodyBones.LeftUpperLeg, HumanBodyBones.LeftLowerLeg, HumanBodyBones.LeftFoot));
                KneeR.Add(Knee(HumanBodyBones.RightUpperLeg, HumanBodyBones.RightLowerLeg, HumanBodyBones.RightFoot));
                Speed.Add(new Vector2(Hero.Velocity.x, Hero.Velocity.z).magnitude);
                var hips = B(HumanBodyBones.Hips);
                var up = Vector3.up;
                // The bones' local X lies along the body's side axis in the bind pose (mixamo_unity rigs): the angle between
                // the hips' and a bone's side axis seen from above is that bone's yaw against the pelvis. Sign: + = the
                // bone turned towards the character's right.
                var pr = Vector3.ProjectOnPlane(hips.right, up);
                float Yaw(Transform t) => t == null ? 0f : Vector3.SignedAngle(pr, Vector3.ProjectOnPlane(t.right, up), up);
                ChestYaw.Add(Yaw(B(HumanBodyBones.UpperChest) ?? B(HumanBodyBones.Chest)));
                NeckYaw.Add(Yaw(B(HumanBodyBones.Neck)));
                HeadYaw.Add(Yaw(B(HumanBodyBones.Head)));
                // Foot slip: horizontal world speed of the planted contact (the lowest ankle / ball joint, within 4 cm
                // of the ground) between consecutive frames while it stays the planted one. 0 = feet locked to the ground.
                Transform low = null; var lowH = 0.04f;
                foreach (var b in new[] { HumanBodyBones.LeftFoot, HumanBodyBones.LeftToes, HumanBodyBones.RightFoot, HumanBodyBones.RightToes })
                {
                    var t = B(b);
                    if (t == null) continue;
                    var h = t.position.y - Hero.Position.y - (b == HumanBodyBones.LeftFoot ? an.leftFeetBottomHeight : b == HumanBodyBones.RightFoot ? an.rightFeetBottomHeight : 0.02f);
                    if (h < lowH) { lowH = h; low = t; }
                }
                if (low != null && low == slipBone && Time.deltaTime > 0)
                {
                    var d = low.position - slipLast; d.y = 0;
                    Slip.Add(d.magnitude / Time.deltaTime);
                }
                slipBone = low;
                slipLast = low != null ? low.position : Vector3.zero;
            }
        }

        PostureRig posture;
        readonly Dictionary<string, object> postureReport = new();

        async Task Posture()
        {
            if (System.Environment.GetCommandLineArgs().Contains("-storyDiag")) { await StoryOpeningDiag(); return; }
            await Seconds(2);
            var ng = M.NewGame(Characters.Kael, 2);
            await WaitFor("plaza", () => ng.IsFaulted || (M.World.ZoneId == "plaza" && M.Mode == GameMode.Play && !M.World.Loading), 180);
            await Seconds(2); await Flush(80); await Seconds(1);
            if (M.Player == null) { errors.Add("no player"); return; }
            posture = gameObject.AddComponent<PostureRig>();
            // Real-time pacing (batch mode runs uncapped) and animation every frame: heroes cull transform updates
            // while no camera renders them, which froze the sampled pose between captures.
            var prevRate = Application.targetFrameRate;
            QualitySettings.vSyncCount = 0;
            Application.targetFrameRate = 60;
            foreach (var c in new[] { Characters.Kael, Characters.Lyra })
                if (M.HeroOf(c)?.Model?.Animator is { } an) an.cullingMode = AnimatorCullingMode.AlwaysAnimate;
            foreach (var who in new[] { Characters.Kael, Characters.Lyra })
            {
                if (G.State.D.Character != who && !await SwapTo(who)) continue;
                var hero = M.Player;
                posture.Hero = hero;
                var tag = who == Characters.Kael ? "kael" : "giva";
                Invuln();
                // Open ground near the monument, facing a fixed direction.
                hero.Teleport(ProtoSpace.V(6, 0.2f, 14), 90);
                await Seconds(2.5f);
                await Shot(hero, $"p_{tag}_idle", 1.2f);
                foreach (var (name, speed) in new[] { ("walk", 2.2f), ("run", 5.2f), ("sprint", 7.6f) })
                {
                    hero.Teleport(ProtoSpace.V(-6, 0.2f, 22), 90);
                    await Seconds(0.6f);
                    posture.StartRamp();
                    _ = hero.WalkTo(hero.Position + hero.transform.forward * 45f, speed);
                    await Seconds(1.2f);
                    posture.Ramp = false;
                    LogRamp($"{tag}_{name}", speed);
                    await Shot(hero, $"p_{tag}_{name}", 0.8f);
                    hero.SetScripted(false);
                    await Seconds(0.4f);
                }
                // Combat stance: a frozen, aggro'd dummy at range puts the hero in combat (CombatLocomotion, combat_idle).
                hero.Teleport(ProtoSpace.V(6, 0.2f, 14), 90);
                var dummy = Spawn("sentinel", hero.Position + hero.transform.forward * 14f, hero.YawDeg + 180f, true);
                dummy.Frozen = true;
                await Until(() => M.InCombat, 5);
                await Seconds(1.5f);
                if (!M.InCombat) warnings.Add("posture: combat stance shot taken out of combat");
                await Shot(hero, $"p_{tag}_combat_idle", 1.2f);
                dummy.Despawn();
                await Until(() => !M.InCombat, 8);
                // Conversation idle.
                hero.PlayClip("talk");
                await Seconds(1.2f);
                await Shot(hero, $"p_{tag}_talk", 1.5f);
                hero.CancelActions();
                await Seconds(0.5f);
                // Crouch: stance and crouched walk (the animator must reach CrouchLocomotion).
                hero.Teleport(ProtoSpace.V(-6, 0.2f, 22), 90);
                await Seconds(0.4f);
                if (!hero.SetCrouch(true)) warnings.Add("posture: could not crouch");
                await Seconds(1.0f);
                var an = hero.Model != null ? hero.Model.Animator : null;
                var inCrouch = an != null && an.GetCurrentAnimatorStateInfo(0).IsName("CrouchLocomotion");
                Log($"[posture] crouch: animator in CrouchLocomotion {inCrouch}, capsule height {hero.GetComponent<CharacterController>().height:0.00} m");
                if (!inCrouch) errors.Add("posture: crouch did not reach the CrouchLocomotion state");
                await Shot(hero, $"p_{tag}_crouch_idle", 1.0f);
                _ = hero.WalkTo(hero.Position + hero.transform.forward * 20f, Hero.CrouchSpeed);
                await Seconds(1.2f);
                await Shot(hero, $"p_{tag}_crouch_walk", 0.8f);
                hero.SetScripted(false);
                hero.SetCrouch(false);
                await Seconds(0.5f);
            }
            Destroy(posture);
            Application.targetFrameRate = prevRate;
            M.Cam.Cinematic = null;
            report["postureShots"] = postureReport;
            report["posture"] = "PASS";
        }

        /// <summary>
        /// Diagnostic replay of the story opening (RunPosture -storyDiag): new game, intro skipped, the "wake" stage, the
        /// tut_moved flag, then once a second the quest stage and progress, the radio dialogue, cinematic and voice-over
        /// state until the stage advances (60 s).
        /// </summary>
        async Task StoryOpeningDiag()
        {
            await Seconds(2);
            var ng = M.NewGame(Characters.Kael, 2);
            await WaitFor("plaza", () => ng.IsFaulted || (M.World.ZoneId == "plaza" && M.Mode == GameMode.Play && !M.World.Loading), 180);
            await Seconds(3); await Flush(60);
            await ExpectStage("m1_awakening", "wake");
            G.State.SetFlag("tut_moved");
            var t0 = Time.realtimeSinceStartup;
            while (Time.realtimeSinceStartup - t0 < 60)
            {
                var st = G.State.D.Quests.TryGetValue("m1_awakening", out var q) ? q : null;
                var prog = st?.Progress != null ? string.Join(",", st.Progress.Select(kv => $"{kv.Key}={kv.Value}")) : "-";
                Log($"[storydiag] t+{Time.realtimeSinceStartup - t0:0.0}s frame {Time.frameCount} stage {StageOf("m1_awakening")} progress [{prog}] tut_moved {G.State.Flag("tut_moved")} " +
                    $"dialogue {M.Dialogue?.ActiveId ?? "none"} inDialogue {M.InDialogue} cinematic {(M.Cinematics.Active != null)} inCinematic {M.InCinematic} mode {M.Mode} paused {M.Paused} vo {VoiceOver.Remaining:0.0}s timeScale {Time.timeScale:0.00}");
                if (StageOf("m1_awakening") != "wake") break;
                await Seconds(1f);
            }
            report["storyDiag"] = StageOf("m1_awakening");
        }

        /// <summary>
        /// Swap to the other lead the way the story does after the reunion: the partner waits scripted at the camp until
        /// the meeting sets "swap_unlocked" (PlazaCinematics.MeetingFinalize), so do the same here, then swap.
        /// </summary>
        async Task<bool> SwapTo(string who)
        {
            var partner = M.HeroOf(who);
            if (partner == null) { errors.Add("posture: no hero " + who); return false; }
            G.State.SetFlag("swap_unlocked");
            partner.gameObject.SetActive(true);
            partner.CancelActions();
            partner.SetScripted(false);
            partner.FollowLeader = M.Player;
            await Seconds(1.4f); // swap cooldown
            M.SwapCharacter();
            await Seconds(1.5f);
            if (G.State.D.Character != who || M.Player != partner)
            {
                errors.Add($"posture: swap to {who} failed (player {G.State.D.Character})");
                return false;
            }
            // Park the other lead out of the shots.
            var other = M.HeroOf(Characters.Partner(who));
            if (other != null) { other.Teleport(ProtoSpace.V(20, 0.2f, 4), 0); other.SetScripted(true); }
            Log($"posture: swapped to {who}");
            return true;
        }

        /// <summary>Responsiveness: time for the hero's speed and the animator's Speed (what the gait blend sees) to reach
        /// 50% / 90% of the commanded speed after a move command.</summary>
        void LogRamp(string name, float target)
        {
            string Reach(System.Func<(float t, float body, float anim), float> f, float frac)
            {
                foreach (var r in posture.RampLog) if (f(r) >= target * frac) return $"{r.t * 1000f:0}";
                return ">1200";
            }
            var line = $"{name}: body 50%/90% at {Reach(r => r.body, 0.5f)}/{Reach(r => r.body, 0.9f)} ms, animator Speed 50%/90% at {Reach(r => r.anim, 0.5f)}/{Reach(r => r.anim, 0.9f)} ms";
            Log("[posture] ramp " + line);
            postureReport["ramp_" + name] = line;
        }

        async Task Shot(Hero hero, string name, float sampleSeconds)
        {
            foreach (var (view, side) in new[] { ("side", true), ("front", false) })
            {
                posture.Side = side;
                posture.Track = true;
                posture.Clear();
                posture.Sample = true;
                await Seconds(sampleSeconds);
                posture.Sample = false;
                static string S(List<float> v) => v.Count == 0 ? "-" : $"{v.Average():0} ({v.Min():0}..{v.Max():0})";
                var slip = posture.Slip.Count == 0 ? "-" : $"{posture.Slip.OrderBy(x => x).ElementAt(posture.Slip.Count / 2):0.00}";
                static string S2(List<float> v) => v.Count == 0 ? "-" : $"{v.Average():0.00} ({v.Min():0.00}..{v.Max():0.00})";
                var line = $"{name}_{view}: torso lean {S(posture.Torso)} deg (pitch {S(posture.TrunkPitch)}), neck lean {S(posture.Neck)} deg, neck vs torso {S(posture.NeckRel)} deg, " +
                           $"head ahead of shoulders {S(posture.HeadFwd)} cm, hands {S2(posture.Hands)} m apart, " +
                           $"knee bend L {S(posture.KneeL)} R {S(posture.KneeR)} deg, speed {S(posture.Speed)} m/s, planted-foot slip median {slip} m/s ({posture.Slip.Count} frames), " +
                           $"twist vs pelvis: chest {S(posture.ChestYaw)} neck {S(posture.NeckYaw)} head {S(posture.HeadYaw)} deg";
                Log("[posture] " + line);
                postureReport[$"{name}_{view}"] = line;
                await Capture($"{name}_{view}");
                posture.Track = false;
            }
        }
    }
}
