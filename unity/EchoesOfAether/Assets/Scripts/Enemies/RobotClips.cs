using System.Collections.Generic;
using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Robot clip library: locomotion for the 'robot' / 'heavy' styles (port of Anims.ts gait + idle) and the
    /// attack/reaction clips of EnemyAnims.ts. Numbers are verbatim from the prototype (degrees, prototype axes).
    /// Events: telegraph (start glow), hit_start / hit_end (active window), impact (AoE moment), laser_on/off, roar.
    /// </summary>
    public static class RobotClips
    {
        public enum Kind { Sentinel, Stalker, Guardian }
        public enum Style { Robot, Heavy }

        static readonly Dictionary<Kind, Dictionary<string, RobotClip>> clipCache = new();
        static readonly Dictionary<Style, RobotLoco> locoCache = new();

        static PoseSpec P(string s) => PoseSpec.Parse(s);
        static PoseSpec M(params PoseSpec[] s) => PoseSpec.Merge(s);
        static (float, PoseSpec) K(float t, PoseSpec p) => (t, p);
        static RobotClipEvent E(float t, string name) => new RobotClipEvent(t, name);

        // ------------------------------------------------------------------ Attack / reaction clips

        public static Dictionary<string, RobotClip> Get(Kind kind)
        {
            if (clipCache.TryGetValue(kind, out var hit)) return hit;
            var c = new Dictionary<string, RobotClip>();
            void Add(RobotClip clip) => c[clip.Name] = clip;

            var robotStance = P("hipsPos:0,-0.06,0 spine:10,0,0 chest:6,0,0 head:-10,0,0 " +
                                "upperarm_S:-20,-10,6 forearm_S:-50,0,0 thigh_S:-16,0,4 shin_S:26,0,0 foot_S:-8,0,0");
            Add(new RobotKeyClip("stance", new[] { K(0, robotStance), K(1, M(robotStance, P("hipsPos:0,-0.08,0"))) }, 2f, true));

            if (kind == Kind.Sentinel || kind == Kind.Guardian)
            {
                bool big = kind == Kind.Guardian;
                // Overhead two-handed slam
                Add(new RobotKeyClip("slam", new[]
                {
                    K(0, robotStance),
                    K(big ? 0.8f : 0.55f, P("upperarm_S:-170,0,12 forearm_S:-40,0,0 thigh_S:-20,0,6 shin_S:30,0,0 hipsPos:0,0.02,-0.06 spine:-14,0,0 chest:-12,0,0 head:-14,0,0")),
                    K(big ? 1.05f : 0.72f, P("upperarm_S:-60,0,8 forearm_S:-6,0,0 thigh_S:-50,0,6 shin_S:80,0,0 foot_S:-26,0,0 hipsPos:0,-0.32,0.12 spine:40,0,0 chest:18,0,0 head:-26,0,0")),
                    K(big ? 1.6f : 1.1f, P("upperarm_S:-56,0,10 forearm_S:-10,0,0 thigh_S:-46,0,6 shin_S:76,0,0 foot_S:-26,0,0 hipsPos:0,-0.3,0.12 spine:36,0,0 chest:16,0,0 head:-24,0,0")),
                    K(big ? 2.2f : 1.5f, robotStance),
                }, big ? 2.2f : 1.5f, false,
                    E(0.05f, "telegraph"), E(big ? 1.0f : 0.68f, "hit_start"), E(big ? 1.05f : 0.72f, "impact"), E(big ? 1.15f : 0.82f, "hit_end")));
                // Horizontal sweep (right arm)
                Add(new RobotKeyClip("sweep", new[]
                {
                    K(0, robotStance),
                    K(big ? 0.65f : 0.42f, M(robotStance, P("hips:0,-20,0 chest:4,-40,0 upperarm_R:0,-30,-74 forearm_R:-40,0,0"))),
                    K(big ? 0.85f : 0.56f, M(robotStance, P("hips:0,10,0 chest:8,10,0 upperarm_R:0,85,-76 forearm_R:-10,0,0"))),
                    K(big ? 1.0f : 0.68f, M(robotStance, P("hips:0,24,0 chest:8,40,0 upperarm_R:0,150,-70 forearm_R:-20,0,0"))),
                    K(big ? 1.6f : 1.1f, robotStance),
                }, big ? 1.6f : 1.1f, false,
                    E(0.05f, "telegraph"), E(big ? 0.74f : 0.48f, "hit_start"), E(big ? 1.0f : 0.68f, "hit_end")));
                Add(new RobotKeyClip("stagger", new[]
                {
                    K(0, robotStance),
                    K(0.15f, M(robotStance, P("hipsPos:0,-0.1,-0.15 spine:-20,10,0 chest:-14,0,0 head:-20,0,0 upperarm_S:-10,0,40 forearm_S:-20,0,0"))),
                    K(0.7f, M(robotStance, P("hipsPos:0,-0.2,-0.05 spine:30,0,0 head:10,0,0 upperarm_S:0,0,10 forearm_S:-30,0,0"))),
                    K(1.3f, robotStance),
                }, 1.3f, false));
                Add(new RobotKeyClip("death", new[]
                {
                    K(0, robotStance),
                    K(0.4f, P("thigh_S:-70,0,8 shin_S:100,0,0 foot_S:30,0,0 upperarm_S:0,0,20 forearm_S:-10,0,0 hipsPos:0,-0.42,0 spine:30,0,10 head:30,0,0")),
                    K(1.1f, P("thigh_S:-80,0,8 shin_S:110,0,0 foot_S:30,0,0 upperarm_S:-20,0,40 forearm_S:0,0,0 root:70,0,10 hipsPos:0,-0.5,0 spine:20,0,0 head:20,0,0")),
                }, 1.1f, false));
                if (big)
                {
                    Add(new RobotKeyClip("roar", new[]
                    {
                        K(0, robotStance),
                        K(0.6f, P("upperarm_S:-20,0,70 forearm_S:-60,0,0 thigh_S:-20,0,8 shin_S:30,0,0 hipsPos:0,-0.04,0 spine:-16,0,0 chest:-18,0,0 head:-30,0,0")),
                        K(1.8f, P("upperarm_S:-24,0,74 forearm_S:-56,0,0 thigh_S:-20,0,8 shin_S:30,0,0 hipsPos:0,-0.04,0 spine:-18,0,0 chest:-20,0,0 head:-34,0,0")),
                        K(2.4f, robotStance),
                    }, 2.4f, false, E(0.6f, "roar")));
                    Add(new RobotKeyClip("laser", new[]
                    {
                        K(0, robotStance),
                        K(0.8f, M(robotStance, P("hips:0,-40,0 spine:0,-10,0 chest:-6,-10,0 head:-10,0,0 upperarm_S:-10,0,40 forearm_S:-80,0,0"))),
                        K(2.8f, M(robotStance, P("hips:0,40,0 spine:0,10,0 chest:-6,10,0 head:-10,0,0 upperarm_S:-10,0,40 forearm_S:-80,0,0"))),
                        K(3.4f, robotStance),
                    }, 3.4f, false, E(0.05f, "telegraph"), E(0.8f, "laser_on"), E(2.8f, "laser_off")));
                    Add(new RobotKeyClip("exposed", new[]
                    {
                        K(0, robotStance),
                        K(0.3f, P("upperarm_S:-10,0,50 forearm_S:-20,0,0 thigh_S:-60,0,8 shin_S:90,0,0 foot_S:-30,0,0 hipsPos:0,-0.36,0 spine:-24,0,0 chest:-20,0,0 head:-24,0,0")),
                        K(3.2f, P("upperarm_S:-12,0,48 forearm_S:-24,0,0 thigh_S:-60,0,8 shin_S:90,0,0 foot_S:-30,0,0 hipsPos:0,-0.37,0 spine:-22,0,0 chest:-18,0,0 head:-20,0,0")),
                        K(3.8f, robotStance),
                    }, 3.8f, false));
                }
            }
            if (kind == Kind.Stalker)
            {
                var crouch = P("upperarm_S:-10,0,30 forearm_S:-30,0,0 thigh_S:-40,0,8 shin_S:60,0,0 foot_S:-18,0,0 hipsPos:0,-0.22,0 spine:26,0,0 head:-24,0,0");
                Add(new RobotKeyClip("stance", new[] { K(0, crouch), K(0.8f, M(crouch, P("hipsPos:0,-0.24,0"))) }, 1.6f, true));
                Add(new RobotKeyClip("slash", new[]
                {
                    K(0, crouch),
                    K(0.22f, M(crouch, P("chest:0,30,0 upperarm_L:10,0,70 forearm_L:-60,0,0 upperarm_R:-60,40,-30 forearm_R:-90,0,0"))),
                    K(0.34f, M(crouch, P("hipsPos:0,-0.16,0.3 chest:10,-30,0 upperarm_L:-80,-60,40 forearm_L:-10,0,0"))),
                    K(0.48f, M(crouch, P("hipsPos:0,-0.16,0.35 chest:10,30,0 upperarm_R:-80,60,-40 forearm_R:-10,0,0 upperarm_L:-40,-60,40 forearm_L:-40,0,0"))),
                    K(0.9f, crouch),
                }, 0.9f, false, E(0.04f, "telegraph"), E(0.28f, "hit_start"), E(0.5f, "hit_end")));
                Add(new RobotKeyClip("stagger", new[]
                {
                    K(0, crouch),
                    K(0.15f, M(crouch, P("hipsPos:0,-0.2,-0.2 spine:-10,0,0"))),
                    K(0.8f, crouch),
                }, 0.8f, false));
                Add(new RobotKeyClip("death", new[]
                {
                    K(0, crouch),
                    K(0.8f, M(crouch, P("root:80,0,0 hipsPos:0,-0.3,0"))),
                }, 0.8f, false));
            }
            clipCache[kind] = c;
            return c;
        }

        // ------------------------------------------------------------------ Locomotion

        struct Cycle
        {
            public float Stance, ThighFwd, ThighBack, KneeStance, KneeSwing, FootStrike, FootPush, Bob, BobBase, BobOffset;
            public float HipYaw, HipRoll, SpineLean, ChestTwist, ArmMid, ArmSwing, ElbowBase, ElbowSwing, ArmZ, HeadComp;
        }

        static Cycle C(float stance, float thighFwd, float thighBack, float kneeStance, float kneeSwing, float footStrike, float footPush,
                       float bob, float bobBase, float bobOffset, float hipYaw, float hipRoll, float spineLean, float chestTwist,
                       float armMid, float armSwing, float elbowBase, float elbowSwing, float armZ, float headComp)
            => new Cycle
            {
                Stance = stance, ThighFwd = thighFwd, ThighBack = thighBack, KneeStance = kneeStance, KneeSwing = kneeSwing,
                FootStrike = footStrike, FootPush = footPush, Bob = bob, BobBase = bobBase, BobOffset = bobOffset,
                HipYaw = hipYaw, HipRoll = hipRoll, SpineLean = spineLean, ChestTwist = chestTwist, ArmMid = armMid,
                ArmSwing = armSwing, ElbowBase = elbowBase, ElbowSwing = elbowSwing, ArmZ = armZ, HeadComp = headComp,
            };

        // WALK / RUN tables for the robot and heavy styles (Anims.ts). Sprint = run for both.
        static readonly Cycle WalkRobot = C(0.62f, 22, 14, 16, 50, 6, 10, 0.03f, -0.04f, 0f, 4, 5, 8, 4, 0, 10, 24, 6, -4, 0.3f);
        static readonly Cycle WalkHeavy = C(0.64f, 20, 12, 18, 44, 4, 8, 0.05f, -0.06f, 0f, 5, 6, 12, 5, -5, 9, 30, 5, 2, 0.3f);
        static readonly Cycle RunRobot = C(0.42f, 40, 22, 26, 85, 4, 18, 0.05f, -0.06f, 0.12f, 6, 6, 16, 6, 6, 22, 50, 8, -2, 0.4f);
        static readonly Cycle RunHeavy = C(0.45f, 34, 20, 26, 70, 2, 12, 0.08f, -0.08f, 0.12f, 6, 7, 18, 6, 0, 18, 40, 6, 3, 0.3f);

        static float Bump(float q, float c, float w)
        {
            float d = Mathf.Abs(q - c);
            d = Mathf.Min(d, 1f - d);
            return Mathf.Exp(-(d / w) * (d / w));
        }

        static System.Action<float, RobotPose> Gait(Cycle p)
        {
            return (ph, output) =>
            {
                const float TAU = Mathf.PI * 2f;
                for (int s = 0; s < 2; s++)
                {
                    bool left = s == 0;
                    float q = left ? ph : (ph + 0.5f) % 1f;
                    float qw = q < p.Stance ? (q / p.Stance) * 0.5f : 0.5f + ((q - p.Stance) / (1f - p.Stance)) * 0.5f;
                    float mid = (p.ThighBack - p.ThighFwd) / 2f, amp = (p.ThighFwd + p.ThighBack) / 2f;
                    float thigh = mid - amp * Mathf.Cos(TAU * qw);
                    float knee = 4f + p.KneeStance * Bump(q, p.Stance * 0.22f, 0.09f) + p.KneeSwing * Bump(q, p.Stance + (1f - p.Stance) * 0.38f, 0.13f);
                    float foot = -p.FootStrike * Bump(q, 0f, 0.06f) + p.FootPush * Bump(q, p.Stance - 0.03f, 0.07f) - 8f * Bump(q, p.Stance + (1f - p.Stance) * 0.55f, 0.1f);
                    float sgn = left ? 1f : -1f;
                    output.Set(left ? RobotRig.ThighL : RobotRig.ThighR, thigh, 0, sgn * 1.5f);
                    output.Set(left ? RobotRig.ShinL : RobotRig.ShinR, knee, 0, 0);
                    output.Set(left ? RobotRig.FootL : RobotRig.FootR, foot, 0, 0);
                    float aq = left ? ph : (ph + 0.5f) % 1f;
                    float arm = p.ArmMid + p.ArmSwing * Mathf.Cos(TAU * aq);
                    float fwd = Mathf.Max(0f, -Mathf.Cos(TAU * aq));
                    output.Set(left ? RobotRig.UpperarmL : RobotRig.UpperarmR, arm, sgn * 4f, sgn * p.ArmZ);
                    output.Set(left ? RobotRig.ForearmL : RobotRig.ForearmR, -(p.ElbowBase + p.ElbowSwing * fwd), sgn * -6f, 0);
                    output.Set(left ? RobotRig.HandL : RobotRig.HandR, -6f, 0, sgn * -4f);
                    output.Set(left ? RobotRig.ClavicleL : RobotRig.ClavicleR, 0, 0, sgn * -2f);
                }
                float hipYaw = -p.HipYaw * Mathf.Cos(TAU * ph);
                float chestTwist = p.ChestTwist * Mathf.Cos(TAU * ph);
                output.Set(RobotRig.Hips, 0, hipYaw, p.HipRoll * Mathf.Sin(TAU * ph));
                output.Set(RobotRig.Spine, p.SpineLean * 0.6f, chestTwist * 0.4f, 0);
                output.Set(RobotRig.Chest, p.SpineLean * 0.4f, chestTwist * 0.6f, -p.HipRoll * 0.5f * Mathf.Sin(TAU * ph));
                output.Set(RobotRig.Neck, -p.SpineLean * 0.4f, 0, 0);
                output.Set(RobotRig.Head, -p.SpineLean * 0.3f + 2f, -(hipYaw + chestTwist) * p.HeadComp, 0);
                var hp = output.P;
                hp.y = p.BobBase - p.Bob * Mathf.Cos(2f * TAU * (ph - p.BobOffset));
                output.P = hp;
            };
        }

        static PoseSpec IdlePose(float shift)
        {
            var spec = new PoseSpec
            {
                ["hipsPos"] = new Vector3(shift * 0.012f, -0.006f - Mathf.Abs(shift) * 0.004f, 0f),
                ["hips"] = new Vector3(0, shift * 2f, shift * 2.2f),
                ["spine"] = new Vector3(2, 0, -shift * 1.2f),
                ["chest"] = new Vector3(-1.5f, 0, -shift),
                ["neck"] = new Vector3(-3, 0, 0),
                ["head"] = new Vector3(3, -shift * 3f, shift * 1.5f),
                ["thigh_L"] = new Vector3(-1f + (shift > 0 ? 0f : -3f), 0, 0.5f + shift * 1.5f),
                ["shin_L"] = new Vector3(shift > 0 ? 2f : 7f, 0, 0),
                ["thigh_R"] = new Vector3(-1f + (shift > 0 ? -3f : 0f), 0, -0.5f + shift * 1.5f),
                ["shin_R"] = new Vector3(shift > 0 ? 7f : 2f, 0, 0),
            };
            return PoseSpec.Merge(spec, P("clavicle_S:0,0,-2 upperarm_S:-1,6,-10 forearm_S:-13,-8,0 hand_S:-6,0,-4 foot_S:-1,4,0"));
        }

        /// <summary>Locomotion set for a style; CombatIdle is left null (enemies set it to their 'stance' clip).</summary>
        public static RobotLoco Loco(Style style, RobotClip combatIdle)
        {
            if (!locoCache.TryGetValue(style, out var baseLoco))
            {
                bool heavy = style == Style.Heavy;
                baseLoco = new RobotLoco
                {
                    Idle = new RobotKeyClip("idle", new[] { K(0, IdlePose(1f)), K(2.2f, IdlePose(0.85f)), K(4.0f, IdlePose(-0.9f)), K(6.2f, IdlePose(-1f)) }, 8f, true),
                    Walk = new RobotFnClip("walk", 1f, true, Gait(heavy ? WalkHeavy : WalkRobot)),
                    Run = new RobotFnClip("run", 1f, true, Gait(heavy ? RunHeavy : RunRobot)),
                    StrideWalk = heavy ? 1.9f : 1.6f,
                    StrideRun = 3.4f,
                    StrideSprint = 4.6f,
                };
                baseLoco.Sprint = baseLoco.Run;
                locoCache[style] = baseLoco;
            }
            // Per-enemy copy so CombatIdle can differ (stalker crouch vs sentinel stance).
            return new RobotLoco
            {
                Idle = baseLoco.Idle,
                Walk = baseLoco.Walk,
                Run = baseLoco.Run,
                Sprint = baseLoco.Sprint,
                CombatIdle = combatIdle,
                StrideWalk = baseLoco.StrideWalk,
                StrideRun = baseLoco.StrideRun,
                StrideSprint = baseLoco.StrideSprint,
            };
        }
    }
}
