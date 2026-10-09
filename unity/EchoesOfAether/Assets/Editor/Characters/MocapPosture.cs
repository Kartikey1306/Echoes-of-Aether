using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;
using Object = UnityEngine.Object;

namespace EOA.EditorTools
{
    /// <summary>
    /// Measured posture correction for the CMU clips. Several captures lean far forward: the run 34–36° with the neck at
    /// 41°, the arms-crossed NPC idle 35°, the sprint 21–24° with the neck 11–14° ahead of the torso. Hand-picked
    /// muscle offsets cannot be trusted (muscle sign and gain depend on the rig), so the offsets are solved per clip and
    /// style. The solver samples the clip on the style's hero rig (<see cref="ClipProbe"/>) and runs a secant method on
    /// constant muscle offsets until the clip's average posture lands inside its band:
    /// <list type="bullet">
    /// <item>torso (hips→neck) forward lean, corrected by pitching the body (RootQ) back about its right axis — the
    /// captures lean from the pelvis, so spine muscles alone saturate and bend the neck backwards — with the thighs'
    /// Front-Back muscles solved so the legs keep their world motion (feet stay under the body);</item>
    /// <item>neck angle against the torso (nearly in line), corrected through Neck Nod;</item>
    /// <item>gaze (level), corrected through Head Nod.</item>
    /// </list>
    /// The stride's own sway is kept, because only constant offsets are added. The offsets live in
    /// Assets/Art/Animations/posture_fix.json; <see cref="MocapNeckFix"/> adds them at import time, and
    /// <see cref="CharacterBuilder"/> recalibrates on every build, re-importing only when an offset moved.
    /// </summary>
    public static class MocapPosture
    {
        public const string TablePath = "Assets/Art/Animations/posture_fix.json";

        public sealed class Spec
        {
            public (float min, float max)? Torso;
            public float NeckMax = 99f;
            public (float min, float max)? Gaze;
            /// <summary>Standing clips: the knees' average bend is brought down to this (degrees), the thighs then keep the
            /// feet under the body and the feet stay flat.</summary>
            public float? KneeMax;
            /// <summary>The head faces where the pelvis faces on average (Head Turn).</summary>
            public bool SquareHead;
            /// <summary>Arms hang at the sides: average arm abduction brought down to this (degrees, Arm Down-Up).</summary>
            public float? ArmMax;
            /// <summary>Share of the trunk's twist around its average that is kept (gaits whose shoulders swing far).</summary>
            public float TwistGain = 1f;
        }

        /// <summary>Bands in degrees, measured as clip averages on the hero rigs (+ = forward / up).</summary>
        /// Game-hero stance (2026-10-08): upright standing clips (trunk within a few degrees, straight knees), a run
        /// leaning under 10°, the neck nearly in line with the trunk (no head poke).
        public static readonly Dictionary<string, Spec> Specs = new()
        {
            ["run"] = new Spec { Torso = (5, 8), NeckMax = 4, Gaze = (-14, 4), TwistGain = 0.6f },
            ["sprint"] = new Spec { Torso = (9, 12), NeckMax = 4, Gaze = (-14, 4), TwistGain = 0.6f },
            ["walk"] = new Spec { Torso = (1, 5), NeckMax = 5, Gaze = (-12, 4), ArmMax = 12 },
            ["idle"] = new Spec { Torso = (-2, 3), NeckMax = 5, Gaze = (-10, 4), KneeMax = 3, SquareHead = true, ArmMax = 8 },
            ["combat_idle"] = new Spec { Torso = (0, 7), NeckMax = 6, Gaze = (-10, 4), SquareHead = true },
            ["talk"] = new Spec { Torso = (-2, 3), NeckMax = 5, Gaze = (-10, 4), KneeMax = 3, SquareHead = true },
            ["npc_crossed"] = new Spec { Torso = (0, 5), NeckMax = 6, Gaze = (-10, 4), KneeMax = 6, SquareHead = true },
            ["npc_hips"] = new Spec { Torso = (0, 5), NeckMax = 8, Gaze = (-10, 4) },
            ["npc_look"] = new Spec { Torso = (4, 9), NeckMax = 9, Gaze = (-15, 6) },
            ["npc_react"] = new Spec { NeckMax = 10 },
            ["sit"] = new Spec { Torso = (10, 15), NeckMax = 8, Gaze = (-14, 4) },
            ["fall"] = new Spec { Torso = (8, 14), NeckMax = 8, Gaze = (-20, 8) },
        };

        static readonly string[] LegMuscles = { "Left Upper Leg Front-Back", "Right Upper Leg Front-Back" };
        static readonly string[] KneeMuscles = { "Left Lower Leg Stretch", "Right Lower Leg Stretch" };
        static readonly string[] FootMuscles = { "Left Foot Up-Down", "Right Foot Up-Down" };
        static readonly string[] TwistMuscles = { "Spine Twist Left-Right", "Chest Twist Left-Right", "UpperChest Twist Left-Right" };
        static readonly string[] ArmMuscles = { "Left Arm Down-Up", "Right Arm Down-Up" };
        const string NeckMuscle = "Neck Nod Down-Up", HeadMuscle = "Head Nod Down-Up", TurnMuscle = "Head Turn Left-Right";
        const float NodPerDeg = 1f / 40f, LegPerDeg = 1f / 50f, KneePerDeg = 1f / 80f, FootPerDeg = 1f / 50f, TurnPerDeg = 1f / 40f, ArmPerDeg = 1f / 80f;

        /// <summary>Offsets: body pitch (degrees about the body's right axis), thigh Front-Back, Neck Nod, Head Nod, knee
        /// (Lower Leg Stretch) and foot (Foot Up-Down), degrees mapped to muscle units by the default ranges; the solver
        /// absorbs any gain or sign.</summary>
        public struct Offset
        {
            public float Body, Legs, Neck, Head, Knee, Foot, Turn, Arm;
            public Offset(float body, float legs, float neck, float head, float knee = 0, float foot = 0, float turn = 0, float arm = 0)
            { Body = body; Legs = legs; Neck = neck; Head = head; Knee = knee; Foot = foot; Turn = turn; Arm = arm; }
            public bool IsZero => Mathf.Abs(Body) + Mathf.Abs(Legs) + Mathf.Abs(Neck) + Mathf.Abs(Head) + Mathf.Abs(Knee) + Mathf.Abs(Foot) + Mathf.Abs(Turn) + Mathf.Abs(Arm) < 1e-4f;
            public override string ToString() => $"body {Body:0.0}, legs {Legs:0.0}, neck {Neck:0.0}, head {Head:0.0}, knee {Knee:0.0}, foot {Foot:0.0}, turn {Turn:0.0}, arm {Arm:0.0}";
        }

        // ------------------------------------------------------------------ table

        static JObject table;
        static DateTime tableStamp;

        static JObject Table()
        {
            if (!File.Exists(TablePath)) return table = new JObject();
            var stamp = File.GetLastWriteTimeUtc(TablePath);
            if (table == null || stamp != tableStamp) { table = JObject.Parse(File.ReadAllText(TablePath)); tableStamp = stamp; }
            return table;
        }

        public static Offset Offsets(string style, string clip)
        {
            var e = Table()[style.ToLowerInvariant()]?[clip];
            return e == null ? default : new Offset((float?)e["body"] ?? 0, (float?)e["legs"] ?? 0, (float?)e["neck"] ?? 0, (float?)e["head"] ?? 0,
                (float?)e["knee"] ?? 0, (float?)e["foot"] ?? 0, (float?)e["turn"] ?? 0, (float?)e["arm"] ?? 0);
        }

        /// <summary>Apply posture offsets to a clip (import postprocessor or an in-memory copy).</summary>
        public static void Apply(AnimationClip clip, Offset o)
        {
            if (o.IsZero) return;
            if (Mathf.Abs(o.Body) > 1e-4f) PitchBody(clip, o.Body);
            foreach (var b in AnimationUtility.GetCurveBindings(clip))
            {
                if (b.type != typeof(Animator)) continue;
                var add = 0f;
                if (Array.IndexOf(LegMuscles, b.propertyName) >= 0) add = o.Legs * LegPerDeg;
                if (Array.IndexOf(KneeMuscles, b.propertyName) >= 0) add = o.Knee * KneePerDeg;
                if (Array.IndexOf(FootMuscles, b.propertyName) >= 0) add = o.Foot * FootPerDeg;
                if (b.propertyName == TurnMuscle) add = o.Turn * TurnPerDeg;
                if (Array.IndexOf(ArmMuscles, b.propertyName) >= 0) add = o.Arm * ArmPerDeg;
                if (b.propertyName == NeckMuscle) add = o.Neck * NodPerDeg;
                if (b.propertyName == HeadMuscle) add = o.Head * NodPerDeg;
                if (add == 0f) continue;
                var c = AnimationUtility.GetEditorCurve(clip, b);
                if (c == null || c.length == 0) continue;
                var keys = c.keys;
                for (var i = 0; i < keys.Length; i++) keys[i].value += add;
                c.keys = keys;
                clip.SetCurve(b.path, b.type, b.propertyName, c);
            }
        }

        /// <summary>Rotate the body orientation curves (RootQ) by a constant pitch about the body's horizontal right axis.</summary>
        static void PitchBody(AnimationClip clip, float deg)
        {
            var props = new[] { "RootQ.x", "RootQ.y", "RootQ.z", "RootQ.w" };
            var curves = props.Select(p => AnimationUtility.GetEditorCurve(clip, EditorCurveBinding.FloatCurve("", typeof(Animator), p))).ToArray();
            if (curves.Any(c => c == null || c.length == 0)) return;
            var times = curves.SelectMany(c => c.keys.Select(k => k.time)).Distinct().OrderBy(t => t).ToArray();
            var vals = new float[4][];
            for (var i = 0; i < 4; i++) vals[i] = new float[times.Length];
            var prev = Quaternion.identity;
            for (var k = 0; k < times.Length; k++)
            {
                var t = times[k];
                var q = new Quaternion(curves[0].Evaluate(t), curves[1].Evaluate(t), curves[2].Evaluate(t), curves[3].Evaluate(t));
                q = Quaternion.Normalize(q);
                var right = q * Vector3.right;
                right.y = 0;
                right = right.sqrMagnitude > 1e-6f ? right.normalized : Vector3.right;
                var q2 = Quaternion.AngleAxis(deg, right) * q;
                if (k > 0 && Quaternion.Dot(q2, prev) < 0) q2 = new Quaternion(-q2.x, -q2.y, -q2.z, -q2.w);
                prev = q2;
                vals[0][k] = q2.x; vals[1][k] = q2.y; vals[2][k] = q2.z; vals[3][k] = q2.w;
            }
            for (var i = 0; i < 4; i++)
            {
                var keys = new Keyframe[times.Length];
                for (var k = 0; k < times.Length; k++)
                {
                    var a = Mathf.Max(0, k - 1);
                    var b = Mathf.Min(times.Length - 1, k + 1);
                    var slope = b > a ? (vals[i][b] - vals[i][a]) / (times[b] - times[a]) : 0f;
                    keys[k] = new Keyframe(times[k], vals[i][k], slope, slope);
                }
                clip.SetCurve("", typeof(Animator), props[i], new AnimationCurve(keys));
            }
        }

        /// <summary>Scale the trunk's twist muscles (spine, chest, upper chest) around their clip average by gain.</summary>
        public static void ScaleTwist(AnimationClip clip, float gain)
        {
            if (Mathf.Abs(gain - 1f) < 1e-4f) return;
            foreach (var b in AnimationUtility.GetCurveBindings(clip))
            {
                if (b.type != typeof(Animator) || Array.IndexOf(TwistMuscles, b.propertyName) < 0) continue;
                var c = AnimationUtility.GetEditorCurve(clip, b);
                if (c == null || c.length == 0) continue;
                var keys = c.keys;
                var mean = keys.Average(k => k.value);
                for (var i = 0; i < keys.Length; i++)
                {
                    keys[i].value = mean + (keys[i].value - mean) * gain;
                    keys[i].inTangent *= gain;
                    keys[i].outTangent *= gain;
                }
                c.keys = keys;
                clip.SetCurve(b.path, b.type, b.propertyName, c);
            }
        }

        // ------------------------------------------------------------------ calibration

        struct Avg { public float Torso, Neck, Gaze, Thigh, Knee, FeetFwd, FootPitch, HeadYaw, Arm; }

        static Avg Measure(ClipProbe probe, AnimationClip src, Offset extra, bool yaw = false)
        {
            var copy = Object.Instantiate(src);
            copy.hideFlags = HideFlags.HideAndDontSave;
            try
            {
                Apply(copy, extra);
                var fps = Mathf.Clamp(40f / Mathf.Max(0.1f, src.length), 10f, 30f);
                var p = ClipProbe.Measure(probe.Sample(copy, fps));
                return new Avg
                {
                    Torso = p.TorsoPitch.Mean, Neck = p.NeckVsTorso.Mean, Gaze = p.Gaze.Mean, Thigh = p.ThighPitch.Mean,
                    Knee = (p.KneeL.Mean + p.KneeR.Mean) * 0.5f, FeetFwd = p.FeetFwdCm.Mean, FootPitch = p.FootPitch.Mean,
                    HeadYaw = yaw ? probe.MeasureTwist(copy, fps).Head.Mean : 0f,
                    Arm = p.ArmAbd.Mean,
                };
            }
            finally { Object.DestroyImmediate(copy); }
        }

        /// <summary>Secant solve of f(x) = target from f(0) = y0; returns x (0 when the clip does not respond).</summary>
        static float Solve(Func<float, float> f, float y0, float target, float firstStep)
        {
            float x0 = 0, x1 = firstStep;
            var y1 = f(x1);
            for (var it = 0; it < 6 && Mathf.Abs(y1 - target) > 0.3f; it++)
            {
                if (Mathf.Abs(y1 - y0) < 0.05f) return 0;
                var x2 = x1 + (target - y1) * (x1 - x0) / (y1 - y0);
                x2 = Mathf.Clamp(x2, x1 - 40f, x1 + 40f);
                x0 = x1; y0 = y1; x1 = x2; y1 = f(x1);
            }
            return x1;
        }

        static float Into((float min, float max) band, float v) => Mathf.Clamp(v, band.min, band.max);

        /// <summary>
        /// Measure the style's clips as currently imported (offsets included), solve the remaining correction and add it
        /// to the table. Returns true when an offset moved by more than 0.4° (the FBX then needs re-importing).
        /// </summary>
        public static bool Calibrate(string style, Dictionary<string, AnimationClip> clips, StringBuilder log)
        {
            using var probe = ClipProbe.ForStyle(style);
            if (!probe.Valid) { log.AppendLine($"[posture-fix] {style}: no rig to calibrate on"); return false; }
            var t = Table();
            var key = style.ToLowerInvariant();
            var styleTable = t[key] as JObject ?? new JObject();
            var changed = false;
            foreach (var (name, spec) in Specs)
            {
                if (!clips.TryGetValue(name, out var clip) || clip == null) continue;
                var old = Offsets(style, name);
                var d = Solve(probe, clip, spec, out var report);
                var moved = Mathf.Abs(d.Body) > 0.4f || Mathf.Abs(d.Legs) > 0.4f || Mathf.Abs(d.Neck) > 0.4f || Mathf.Abs(d.Head) > 0.4f
                            || Mathf.Abs(d.Knee) > 0.4f || Mathf.Abs(d.Foot) > 0.4f || Mathf.Abs(d.Turn) > 0.4f || Mathf.Abs(d.Arm) > 0.4f;
                if (moved || styleTable[name] == null)
                {
                    styleTable[name] = new JObject
                    {
                        ["body"] = Math.Round(old.Body + d.Body, 2), ["legs"] = Math.Round(old.Legs + d.Legs, 2),
                        ["neck"] = Math.Round(old.Neck + d.Neck, 2), ["head"] = Math.Round(old.Head + d.Head, 2),
                        ["knee"] = Math.Round(old.Knee + d.Knee, 2), ["foot"] = Math.Round(old.Foot + d.Foot, 2), ["turn"] = Math.Round(old.Turn + d.Turn, 2), ["arm"] = Math.Round(old.Arm + d.Arm, 2),
                        ["measured"] = report,
                    };
                }
                changed |= moved;
                log.AppendLine($"[posture-fix] {style}/{name}: {report}; offsets +({d}){(moved ? "" : " (in band)")}");
            }
            t[key] = styleTable;
            t["note"] = "Generated by MocapPosture.Calibrate (CharacterBuilder.BuildAll). Degrees: body = RootQ pitch about the body right axis, legs = Upper Leg Front-Back, neck = Neck Nod, head = Head Nod, knee = Lower Leg Stretch, foot = Foot Up-Down.";
            File.WriteAllText(TablePath, t.ToString(Newtonsoft.Json.Formatting.Indented));
            table = null;
            return changed;
        }

        /// <summary>
        /// The constant offsets that bring a clip (as it is now) inside its band on a hero rig: trunk lean (body pitch,
        /// thighs keeping their world swing), neck against the trunk, gaze, and for standing clips the knee bend (thighs
        /// then keep the feet where they were under the body, feet stay flat). <paramref name="report"/> gets the
        /// before → after numbers.
        /// </summary>
        public static Offset Solve(ClipProbe probe, AnimationClip clip, Spec spec, out string report)
        {
            var m0 = Measure(probe, clip, default);
            var d = new Offset();
            var m = m0;
            if (spec.Torso is { } tb && Mathf.Abs(Into(tb, m.Torso) - m.Torso) > 0.4f)
            {
                var want = Into(tb, m.Torso);
                d.Body = Solve(x => Measure(probe, clip, new Offset(x, 0, 0, 0)).Torso, m.Torso, want, want - m.Torso);
                // Legs keep their world swing: thighs back to the original average pitch.
                var thigh = Measure(probe, clip, new Offset(d.Body, 0, 0, 0)).Thigh;
                d.Legs = Solve(x => Measure(probe, clip, new Offset(d.Body, x, 0, 0)).Thigh, thigh, m0.Thigh, m0.Thigh - thigh);
                m = Measure(probe, clip, d);
            }
            if (spec.KneeMax is { } km && m.Knee > km + 0.4f)
            {
                var feet = m.FeetFwd;
                var foot = m.FootPitch;
                var o = d;
                d.Knee = Solve(x => Measure(probe, clip, new Offset(o.Body, o.Legs, 0, 0, x)).Knee, m.Knee, km, km - m.Knee);
                // A straighter knee swings the foot forward: the thighs come back until the feet are under the body again,
                // then the feet are levelled to their original pitch.
                var o2 = d;
                var f1 = Measure(probe, clip, d).FeetFwd;
                var dl = Solve(x => Measure(probe, clip, new Offset(o2.Body, o2.Legs + x, 0, 0, o2.Knee)).FeetFwd, f1, feet, (feet - f1) * 0.5f);
                d.Legs += dl;
                var o3 = d;
                var p1 = Measure(probe, clip, d).FootPitch;
                d.Foot = Solve(x => Measure(probe, clip, new Offset(o3.Body, o3.Legs, 0, 0, o3.Knee, x)).FootPitch, p1, foot, foot - p1);
                m = Measure(probe, clip, d);
            }
            var arm0 = m.Arm;
            if (spec.ArmMax is { } am && m.Arm > am + 0.4f)
            {
                var o = d;
                d.Arm = Solve(x => Measure(probe, clip, new Offset(o.Body, o.Legs, 0, 0, o.Knee, o.Foot, 0, x)).Arm, m.Arm, am, am - m.Arm);
                m = Measure(probe, clip, d);
            }
            if (m.Neck > spec.NeckMax + 0.4f)
            {
                var o = d;
                d.Neck = Solve(x => Measure(probe, clip, new Offset(o.Body, o.Legs, x, 0, o.Knee, o.Foot, 0, o.Arm)).Neck, m.Neck, spec.NeckMax, spec.NeckMax - m.Neck);
                m = Measure(probe, clip, d);
            }
            if (spec.Gaze is { } gb && Mathf.Abs(Into(gb, m.Gaze) - m.Gaze) > 0.4f)
            {
                var o = d;
                d.Head = Solve(x => Measure(probe, clip, new Offset(o.Body, o.Legs, o.Neck, x, o.Knee, o.Foot, 0, o.Arm)).Gaze, m.Gaze, Into(gb, m.Gaze), Into(gb, m.Gaze) - m.Gaze);
                m = Measure(probe, clip, d);
            }
            var yaw0 = 0f;
            if (spec.SquareHead)
            {
                yaw0 = Measure(probe, clip, d, true).HeadYaw;
                if (Mathf.Abs(yaw0) > 1f)
                {
                    var o = d;
                    d.Turn = Solve(x => Measure(probe, clip, new Offset(o.Body, o.Legs, o.Neck, o.Head, o.Knee, o.Foot, x, o.Arm), true).HeadYaw, yaw0, 0f, -yaw0);
                }
            }
            var yaw1 = spec.SquareHead ? Measure(probe, clip, d, true).HeadYaw : 0f;
            report = $"torso {m0.Torso:0.0} -> {m.Torso:0.0}, neck vs torso {m0.Neck:0.0} -> {m.Neck:0.0}, gaze {m0.Gaze:0.0} -> {m.Gaze:0.0}, " +
                     $"knees {m0.Knee:0.0} -> {m.Knee:0.0}, feet ahead of hips {m0.FeetFwd:0.0} -> {m.FeetFwd:0.0} cm, thighs {m0.Thigh:0.0} -> {m.Thigh:0.0} deg" +
                     (spec.SquareHead ? $", head yaw {yaw0:0.0} -> {yaw1:0.0}" : "") + (spec.ArmMax != null ? $", arms out {arm0:0.0} -> {m.Arm:0.0}" : "");
            return d;
        }
    }
}
