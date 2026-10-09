using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEngine;
using Object = UnityEngine.Object;

namespace EOA.EditorTools
{
    /// <summary>
    /// Samples humanoid clips on a hero rig (edit mode, <see cref="AnimationClip.SampleAnimation"/>) and measures what the
    /// animation pipeline needs: posture (torso / neck lean, knee bend, shoulder hunch), the strike moment of attack clips
    /// (peak hand or foot speed), dead lead-in frames, the ground speed of in-place locomotion (from the planted foot's
    /// stride), the left-foot-plant phase of loops, and root travel.
    /// Used by <see cref="MixamoImporter"/> and by the posture report:
    /// Unity -batchmode -quit -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.ClipProbe.Report
    /// </summary>
    public sealed class ClipProbe : IDisposable
    {
        public const float Fps = 60f;

        static readonly HumanBodyBones[] Bones =
        {
            HumanBodyBones.Hips, HumanBodyBones.Spine, HumanBodyBones.Chest, HumanBodyBones.UpperChest, HumanBodyBones.Neck, HumanBodyBones.Head,
            HumanBodyBones.LeftUpperArm, HumanBodyBones.RightUpperArm, HumanBodyBones.LeftHand, HumanBodyBones.RightHand,
            HumanBodyBones.LeftUpperLeg, HumanBodyBones.RightUpperLeg, HumanBodyBones.LeftLowerLeg, HumanBodyBones.RightLowerLeg,
            HumanBodyBones.LeftFoot, HumanBodyBones.RightFoot, HumanBodyBones.LeftToes, HumanBodyBones.RightToes,
            HumanBodyBones.LeftIndexProximal, HumanBodyBones.LeftIndexIntermediate, HumanBodyBones.RightIndexProximal, HumanBodyBones.RightIndexIntermediate,
        };

        const int Hips = 0, Chest = 2, UpperChest = 3, Neck = 4, Head = 5, LUpperArm = 6, RUpperArm = 7, LHand = 8, RHand = 9,
            LUpperLeg = 10, RUpperLeg = 11, LLowerLeg = 12, RLowerLeg = 13, LFoot = 14, RFoot = 15, LToes = 16, RToes = 17,
            LIndex1 = 18, LIndex2 = 19, RIndex1 = 20, RIndex2 = 21;

        readonly GameObject go;
        readonly Animator anim;
        readonly Transform[] tf;
        /// <summary>The head's local direction that faces the character's front in the bind pose (level gaze).</summary>
        readonly Vector3 gazeLocal = Vector3.forward;
        /// <summary>Bone rotations of the bind pose (the instance before any sampling), per entry of <see cref="Bones"/>.</summary>
        readonly Quaternion[] bindRot;
        public string RigName { get; }
        public float HumanScale => anim != null ? anim.humanScale : 1f;
        public bool Valid => anim != null && anim.isHuman && tf[Hips] != null && tf[Neck] != null && tf[Head] != null;

        public ClipProbe(GameObject rig)
        {
            RigName = rig != null ? rig.name : "none";
            if (rig == null) { tf = new Transform[Bones.Length]; return; }
            go = Object.Instantiate(rig);
            go.hideFlags = HideFlags.HideAndDontSave;
            go.transform.SetPositionAndRotation(Vector3.zero, Quaternion.identity);
            anim = go.GetComponent<Animator>();
            tf = Bones.Select(b => anim != null && anim.isHuman ? anim.GetBoneTransform(b) : null).ToArray();
            if (tf[Head] != null) gazeLocal = Quaternion.Inverse(tf[Head].rotation) * go.transform.forward;
            bindRot = tf.Select(t => t != null ? t.rotation : Quaternion.identity).ToArray();
        }

        /// <summary>The rig the CMU clips were authored on (the style's animation FBX model).</summary>
        public static ClipProbe ForAnimRig(string style) => new(AssetDatabase.LoadAssetAtPath<GameObject>($"Assets/Art/Animations/Anim_{style}.fbx"));

        /// <summary>The hero prefab of a style (target rig), else the style's animation FBX model.</summary>
        public static ClipProbe ForStyle(string style)
        {
            var prefab = Resources.Load<GameObject>("Characters/" + (style == "Female" ? "Lyra" : "Kael"));
            if (prefab == null || prefab.GetComponent<Animator>() == null || prefab.GetComponent<Animator>().avatar == null)
                prefab = AssetDatabase.LoadAssetAtPath<GameObject>($"Assets/Art/Animations/Anim_{style}.fbx");
            return new ClipProbe(prefab);
        }

        public void Dispose()
        {
            if (go != null) Object.DestroyImmediate(go);
        }

        // ------------------------------------------------------------------ sampling

        /// <summary>Bone positions per frame in the rig root's space (root reset before every sample).</summary>
        public sealed class Track
        {
            public string Clip;
            public float Length, Dt;
            public Vector3[][] P; // [frame][bone]
            public Vector3[] Gaze; // [frame] head gaze direction
            public int Frames => P.Length;
            public Vector3 Forward = Vector3.forward;
        }

        public Track Sample(AnimationClip clip, float fps = Fps)
        {
            var n = Mathf.Max(2, Mathf.CeilToInt(clip.length * fps) + 1);
            var tr = new Track { Clip = clip.name, Length = clip.length, Dt = clip.length / (n - 1), P = new Vector3[n][], Gaze = new Vector3[n] };
            var root = go.transform;
            for (var i = 0; i < n; i++)
            {
                root.SetPositionAndRotation(Vector3.zero, Quaternion.identity);
                clip.SampleAnimation(go, Mathf.Min(clip.length, i * tr.Dt));
                var row = new Vector3[Bones.Length];
                for (var b = 0; b < Bones.Length; b++) row[b] = tf[b] != null ? root.InverseTransformPoint(tf[b].position) : Vector3.zero;
                tr.P[i] = row;
                tr.Gaze[i] = tf[Head] != null ? root.InverseTransformDirection(tf[Head].rotation * gazeLocal) : Vector3.forward;
            }
            // Facing: perpendicular to the hip line, averaged over the clip.
            var right = Vector3.zero;
            foreach (var row in tr.P) right += row[RUpperLeg] - row[LUpperLeg];
            right.y = 0;
            if (right.sqrMagnitude > 1e-6f) tr.Forward = Vector3.Cross(right.normalized, Vector3.up);
            return tr;
        }

        /// <summary>Ankle joints at the given clip times: position in the root's space and world rotation (root at the
        /// origin, no IK).</summary>
        public (Vector3[] lp, Quaternion[] lq, Vector3[] rp, Quaternion[] rq) SampleFeet(AnimationClip clip, float[] times)
        {
            var root = go.transform;
            var n = times.Length;
            var r = (lp: new Vector3[n], lq: new Quaternion[n], rp: new Vector3[n], rq: new Quaternion[n]);
            for (var i = 0; i < n; i++)
            {
                root.SetPositionAndRotation(Vector3.zero, Quaternion.identity);
                clip.SampleAnimation(go, Mathf.Clamp(times[i], 0f, clip.length));
                r.lp[i] = root.InverseTransformPoint(tf[LFoot].position);
                r.lq[i] = tf[LFoot].rotation;
                r.rp[i] = root.InverseTransformPoint(tf[RFoot].position);
                r.rq[i] = tf[RFoot].rotation;
            }
            return r;
        }

        // ------------------------------------------------------------------ metrics

        public struct Stat
        {
            public float Mean, Min, Max;
            public override string ToString() => $"{Mean:0} ({Min:0}..{Max:0})";
        }

        static Stat Stats(IEnumerable<float> v)
        {
            var a = v.ToArray();
            return a.Length == 0 ? default : new Stat { Mean = a.Average(), Min = a.Min(), Max = a.Max() };
        }

        /// <summary>Signed forward lean (degrees) of the segment a→b in the sagittal plane (+ = forward).</summary>
        static float Pitch(Vector3 a, Vector3 b, Vector3 fwd)
        {
            var d = b - a;
            return Mathf.Atan2(Vector3.Dot(d, fwd), d.y) * Mathf.Rad2Deg;
        }

        /// <summary>Forward swing (degrees) of a downward segment a→b from hanging straight down (+ = forward).</summary>
        static float Swing(Vector3 a, Vector3 b, Vector3 fwd)
        {
            var d = b - a;
            return Mathf.Atan2(Vector3.Dot(d, fwd), -d.y) * Mathf.Rad2Deg;
        }

        static float Knee(Vector3[] r, int up, int lo, int ft) => 180f - Vector3.Angle(r[up] - r[lo], r[ft] - r[lo]);

        /// <summary>Mean abduction of the two arms (shoulder joint → hand against the trunk's down axis, outward +).</summary>
        static float ArmAbduction(Vector3[] r)
        {
            var up = (r[Neck] - r[Hips]).normalized;
            var right = Vector3.ProjectOnPlane(r[RUpperLeg] - r[LUpperLeg], up).normalized;
            float A(int shoulder, int hand, float side)
            {
                var d = r[hand] - r[shoulder];
                return Mathf.Atan2(Vector3.Dot(d, right * side), Vector3.Dot(d, -up)) * Mathf.Rad2Deg;
            }
            return (A(LUpperArm, LHand, -1f) + A(RUpperArm, RHand, 1f)) * 0.5f;
        }

        /// <summary>Pitch of the foot (ankle → toes joint) against the ground, degrees (+ = toes up).</summary>
        static float FootPitchOf(Vector3 ankle, Vector3 toes, Vector3 fwd)
        {
            var d = toes - ankle;
            var h = Vector3.ProjectOnPlane(d, Vector3.up).magnitude;
            return Mathf.Atan2(d.y, Mathf.Max(1e-4f, h)) * Mathf.Rad2Deg;
        }

        public sealed class Posture
        {
            /// <summary>Same measures as the gameplay capture (angle from vertical), plus the signed sagittal pitch.</summary>
            public Stat Torso, Neck, TorsoPitch, NeckPitch, NeckVsTorso, Gaze, ThighPitch, KneeL, KneeR, ShoulderFwdCm, IndexCurl;
            /// <summary>Head joint ahead of the shoulder joints (cm, side view), hand-to-hand distance (m), the ankles' midpoint
            /// ahead of the hips (cm) and the feet's pitch (ankle → toes against the ground, degrees, + = toes up).</summary>
            public Stat HeadFwdCm, Hands, FeetFwdCm, FootPitch;
            /// <summary>Arm abduction: shoulder → hand line against the trunk, out to the side, degrees (mean of both arms).</summary>
            public Stat ArmAbd;
            public override string ToString() =>
                $"torso {Torso} pitch {TorsoPitch}, neck {Neck} pitch {NeckPitch} vs torso {NeckVsTorso}, gaze {Gaze}, knee L {KneeL} R {KneeR}, shoulders fwd {ShoulderFwdCm} cm, index curl {IndexCurl}, " +
                $"head ahead of shoulders {HeadFwdCm} cm, hands {Hands.Mean:0.00} m apart, arms out {ArmAbd} deg";
        }

        public static Posture Measure(Track t)
        {
            var f = t.Forward;
            var p = new Posture
            {
                Torso = Stats(t.P.Select(r => Vector3.Angle(r[Neck] - r[Hips], Vector3.up))),
                Neck = Stats(t.P.Select(r => Vector3.Angle(r[Head] - r[Neck], Vector3.up))),
                TorsoPitch = Stats(t.P.Select(r => Pitch(r[Hips], r[Neck], f))),
                NeckPitch = Stats(t.P.Select(r => Pitch(r[Neck], r[Head], f))),
                NeckVsTorso = Stats(t.P.Select(r => Pitch(r[Neck], r[Head], f) - Pitch(r[Hips], r[Neck], f))),
                // Gaze pitch (+ = up), from the head's bind-pose forward.
                Gaze = Stats(t.Gaze.Select(g => Mathf.Asin(Mathf.Clamp(g.normalized.y, -1f, 1f)) * Mathf.Rad2Deg)),
                // Mean world pitch of the two thighs (hip→knee): the legs' swing as seen from the ground.
                ThighPitch = Stats(t.P.Select(r => (Swing(r[LUpperLeg], r[LLowerLeg], f) + Swing(r[RUpperLeg], r[RLowerLeg], f)) * 0.5f)),
                KneeL = Stats(t.P.Select(r => Knee(r, LUpperLeg, LLowerLeg, LFoot))),
                KneeR = Stats(t.P.Select(r => Knee(r, RUpperLeg, RLowerLeg, RFoot))),
                // Shoulder joints ahead of the neck base, measured along the chest's forward (hunch).
                ShoulderFwdCm = Stats(t.P.Select(r => Vector3.Dot((r[LUpperArm] + r[RUpperArm]) * 0.5f - r[Neck], f) * 100f)),
                IndexCurl = Stats(t.P.Select(r => r[LIndex1] == Vector3.zero ? 0 : Vector3.Angle(r[LIndex1] - r[LHand], r[LIndex2] - r[LIndex1]))),
                HeadFwdCm = Stats(t.P.Select(r => Vector3.Dot(r[Head] - (r[LUpperArm] + r[RUpperArm]) * 0.5f, f) * 100f)),
                Hands = Stats(t.P.Select(r => (r[LHand] - r[RHand]).magnitude)),
                FeetFwdCm = Stats(t.P.Select(r => Vector3.Dot((r[LFoot] + r[RFoot]) * 0.5f - r[Hips], f) * 100f)),
                FootPitch = Stats(t.P.Select(r => (FootPitchOf(r[LFoot], r[LToes], f) + FootPitchOf(r[RFoot], r[RToes], f)) * 0.5f)),
                ArmAbd = Stats(t.P.Select(ArmAbduction)),
            };
            return p;
        }

        /// <summary>Speed of a joint relative to the hips (m/s) at every frame.</summary>
        static float[] RelSpeed(Track t, int bone)
        {
            var n = t.Frames;
            var s = new float[n];
            for (var i = 0; i < n; i++)
            {
                var a = t.P[Mathf.Max(0, i - 1)];
                var b = t.P[Mathf.Min(n - 1, i + 1)];
                var dt = (Mathf.Min(n - 1, i + 1) - Mathf.Max(0, i - 1)) * t.Dt;
                s[i] = dt > 0 ? ((b[bone] - b[Hips]) - (a[bone] - a[Hips])).magnitude / dt : 0;
            }
            return s;
        }

        public struct Strike
        {
            public float Time, Speed;
            public string Limb;
            public bool Valid => Speed > 0.5f;
        }

        /// <summary>The strike moment: peak speed of a hand or foot relative to the hips, between <paramref name="from"/>
        /// and 85% of the clip (follow-through and recovery excluded).</summary>
        public static Strike FindStrike(Track t, float from = 0f)
        {
            var best = new Strike();
            var lo = Mathf.Clamp(Mathf.RoundToInt(from / t.Dt), 1, t.Frames - 2);
            var hi = Mathf.Clamp(Mathf.RoundToInt(t.Length * 0.85f / t.Dt), lo + 1, t.Frames - 2);
            foreach (var (bone, limb) in new[] { (LHand, "left hand"), (RHand, "right hand"), (LFoot, "left foot"), (RFoot, "right foot") })
            {
                var s = RelSpeed(t, bone);
                for (var i = lo; i <= hi; i++)
                    if (s[i] > best.Speed) best = new Strike { Time = i * t.Dt, Speed = s[i], Limb = limb };
            }
            return best;
        }

        /// <summary>
        /// Seconds of near-static lead-in at the start: until any hand, foot or the head moves faster than 15% of the
        /// clip's peak limb speed (at least 0.35 m/s), less two frames of anticipation. Capped at 35% of the clip / 0.5 s.
        /// </summary>
        public static float LeadIn(Track t)
        {
            var speeds = new[] { LHand, RHand, LFoot, RFoot, Head }.Select(b => RelSpeed(t, b)).ToArray();
            var hipsSpeed = new float[t.Frames];
            for (var i = 1; i < t.Frames; i++) hipsSpeed[i] = (t.P[i][Hips] - t.P[i - 1][Hips]).magnitude / t.Dt;
            var peak = speeds.Max(s => s.Max());
            var thr = Mathf.Max(0.35f, peak * 0.15f);
            var first = t.Frames - 1;
            for (var i = 0; i < t.Frames; i++)
                if (speeds.Any(s => s[i] > thr) || hipsSpeed[i] > thr) { first = i; break; }
            var lead = Mathf.Max(0, first - 2) * t.Dt;
            return Mathf.Min(lead, Mathf.Min(0.5f, t.Length * 0.35f));
        }

        /// <summary>
        /// Ground speed the clip's feet are animated for (m/s, rig scale): the median forward speed of the hips over the
        /// planted contact point. Each frame the contact is the lower foot's ankle or ball (toes joint), whichever is
        /// closer to its own lowest height (heel strike → flat foot → push-off), within 1.5 cm of it, and moving back
        /// relative to the hips. Works for in-place clips (the foot slides back) and travelling ones (the hips move).
        /// </summary>
        public static float StrideSpeed(Track t) => StrideSpeed(t, out _);

        public static float StrideSpeed(Track t, out int samples)
        {
            var mins = new[] { LFoot, LToes, RFoot, RToes }.ToDictionary(b => b, b => t.P.Min(r => r[b].y));
            var v = new List<float>();
            for (var i = 1; i < t.Frames - 1; i++)
            {
                var r = t.P[i];
                var best = -1; var bestH = 0.015f;
                foreach (var b in new[] { LFoot, LToes, RFoot, RToes })
                {
                    var h = r[b].y - mins[b];
                    if (h < bestH) { bestH = h; best = b; }
                }
                if (best < 0) continue;
                var a = t.P[i - 1];
                var c = t.P[i + 1];
                var fwd = Vector3.Dot((c[Hips] - c[best]) - (a[Hips] - a[best]), t.Forward) / (2 * t.Dt);
                if (fwd > 0.2f) v.Add(fwd);
            }
            samples = v.Count;
            if (v.Count == 0) return 0;
            v.Sort();
            return v[v.Count / 2];
        }

        /// <summary>
        /// Ground speed of an in-place gait from foot contact (m/s, the true contact-point speed, no probe bias): the
        /// backward speed, relative to the hips, of the lowest sole joint (ankles, toes) at mid-stance, i.e. as it passes
        /// under the hips while within 6 cm of the clip's lowest contact height (twice per cycle; mean of the passes).
        /// Without passes it falls back to the median backward speed of the lowest joint while within 2.5 cm of the
        /// floor. Unlike <see cref="StrideSpeed"/> it needs no per-joint minimum, so the short stances of a run or sprint,
        /// whose flight phases put a lifting foot lowest, still read correctly.
        /// </summary>
        public static float ContactSpeed(Track t, out int samples)
        {
            var pts = new[] { LFoot, LToes, RFoot, RToes };
            var low = new int[t.Frames];
            var lowH = new float[t.Frames];
            for (var i = 0; i < t.Frames; i++)
            {
                var r = t.P[i];
                var best = pts[0];
                foreach (var b in pts) if (r[b].y < r[best].y) best = b;
                low[i] = best;
                lowH[i] = r[best].y;
            }
            var floor = lowH.Min();
            float Ahead(int frame, int bone) => Vector3.Dot(t.P[frame][bone] - t.P[frame][Hips], t.Forward);
            var pass = new List<float>();
            for (var i = 0; i < t.Frames - 1; i++)
            {
                if (lowH[i] > floor + 0.06f) continue;
                var b = low[i];
                var a0 = Ahead(i, b);
                var a1 = Ahead(i + 1, b);
                if (a0 >= 0f && a1 < 0f) pass.Add((a0 - a1) / t.Dt);
            }
            if (pass.Count > 0) { samples = pass.Count; return pass.Average(); }
            var v = new List<float>();
            for (var i = 0; i < t.Frames - 1; i++)
            {
                if (lowH[i] > floor + 0.025f) continue;
                var back = (Ahead(i, low[i]) - Ahead(i + 1, low[i])) / t.Dt;
                if (back > 0.2f) v.Add(back);
            }
            samples = v.Count;
            if (v.Count == 0) return 0;
            v.Sort();
            return v[v.Count / 2];
        }

        /// <summary>Normalised time of the left foot's plant (most forward point of the left foot), for loop phase alignment.</summary>
        public static float LeftPlantPhase(Track t)
        {
            var best = 0; var bestD = float.MinValue;
            for (var i = 0; i < t.Frames - 1; i++)
            {
                var d = Vector3.Dot(t.P[i][LFoot] - t.P[i][Hips], t.Forward);
                if (d > bestD) { bestD = d; best = i; }
            }
            return t.Length > 0 ? best * t.Dt / t.Length : 0;
        }

        /// <summary>Horizontal root travel over the clip (m, normalised RootT × human scale).</summary>
        public static float RootTravel(AnimationClip clip, float humanScale)
        {
            float End(string prop, bool last)
            {
                var c = AnimationUtility.GetEditorCurve(clip, EditorCurveBinding.FloatCurve("", typeof(Animator), prop));
                if (c == null || c.length == 0) return 0;
                return c.keys[last ? c.length - 1 : 0].value;
            }
            var dx = End("RootT.x", true) - End("RootT.x", false);
            var dz = End("RootT.z", true) - End("RootT.z", false);
            return new Vector2(dx, dz).magnitude * humanScale;
        }

        // ------------------------------------------------------------------ report

        /// <summary>Posture, lead-in, strike and stride of every clip the controllers use, both styles: logs
        /// "[clipprobe]" lines and writes Captures/clip_probe.txt.</summary>
        [MenuItem("EOA/Test/Clip Probe (posture, timing, stride)")]
        public static void Report()
        {
            var sb = new StringBuilder();
            var meta = Newtonsoft.Json.Linq.JObject.Parse(File.ReadAllText("Assets/Art/Animations/clips_meta.json"));
            foreach (var style in new[] { "Male", "Female" })
            {
                using var probe = ForStyle(style);
                if (!probe.Valid) { sb.AppendLine($"{style}: no humanoid rig to probe"); continue; }
                var clips = CharacterBuilder.LoadClips(style);
                foreach (var kv in clips.OrderBy(k => k.Key))
                {
                    var clip = kv.Value;
                    var tr = probe.Sample(clip);
                    var post = Measure(tr);
                    var src = MixamoImporter.SourceOf(clip);
                    var line = new StringBuilder($"[clipprobe] {style}/{kv.Key} {src} len {clip.length:0.00}s: {post}");
                    var loop = clip.isLooping;
                    if (!loop) line.Append($"; lead-in {LeadIn(tr):0.000}s");
                    var info = meta[style.ToLowerInvariant()]?[kv.Key];
                    if (info?["events"] is Newtonsoft.Json.Linq.JArray ev && ev.Count > 0)
                    {
                        var s = FindStrike(tr, LeadIn(tr));
                        line.Append($"; strike {s.Time:0.000}s ({s.Limb} {s.Speed:0.0} m/s); events {string.Join(",", ev.Select(e => $"{e["name"]}@{(float)e["t"]:0.00}"))}");
                    }
                    if (kv.Key is "walk" or "run" or "sprint")
                    {
                        using var authoring = ForAnimRig(style);
                        var onAuthoring = authoring.Valid ? StrideSpeed(authoring.Sample(clip)) : 0;
                        var neutral = MixamoImporter.Neutral(clip);
                        var trN = probe.Sample(neutral);
                        Object.DestroyImmediate(neutral);
                        line.Append($"; contact speed {ContactSpeed(tr, out var nc):0.00} m/s ({nc} samples); stride speed {StrideSpeed(tr, out var ns):0.00} m/s ({ns} samples) on {probe.RigName} (neutral copy {StrideSpeed(trN):0.00}, authoring rig {onAuthoring:0.00}, meta {(float?)info?["speed"] ?? 0:0.0}); left plant phase {LeftPlantPhase(tr):0.00} (neutral copy {LeftPlantPhase(trN):0.00})");
                    }
                    line.Append($"; root travel {RootTravel(clip, probe.HumanScale):0.00} m");
                    sb.AppendLine(line.ToString());
                }
            }
            var outPath = Path.GetFullPath(Path.Combine(Application.dataPath, "../../../Captures/clip_probe.txt"));
            File.WriteAllText(outPath, sb.ToString());
            Debug.Log("[clipprobe] wrote " + outPath + "\n" + sb);
        }

        /// <summary>Per-frame sole joints of the gaits on the hero rigs (height above the clip's lowest, distance ahead of
        /// the hips), for checking contact and speed: Captures/gait_trace.txt.</summary>
        [MenuItem("EOA/Test/Gait Trace (feet per frame)")]
        public static void GaitTrace()
        {
            var sb = new StringBuilder();
            foreach (var style in new[] { "Male", "Female" })
            {
                using var probe = ForStyle(style);
                var clips = CharacterBuilder.LoadClips(style);
                // the raw library clips too (before re-timing and posture), when the UAL library is imported
                foreach (var kv in AssetDatabase.LoadAllAssetsAtPath(MixamoImporter.UalRoot + "/UAL1.fbx").OfType<AnimationClip>())
                    if (kv.name is "walk" or "run" or "sprint") clips["raw " + kv.name] = kv;
                foreach (var name in new[] { "walk", "run", "sprint", "raw walk", "raw run", "raw sprint" })
                {
                    if (!clips.TryGetValue(name, out var clip)) continue;
                    var neutral = MixamoImporter.Neutral(clip);
                    var t = probe.Sample(neutral, 120f);
                    Object.DestroyImmediate(neutral);
                    var floor = t.P.Min(r => Mathf.Min(Mathf.Min(r[LFoot].y, r[LToes].y), Mathf.Min(r[RFoot].y, r[RToes].y)));
                    sb.AppendLine($"== {style} {name} ({MixamoImporter.SourceOf(clip)}) len {clip.length:0.00}s, floor {floor:0.000}, contact speed {ContactSpeed(t, out var n):0.00} ({n})");
                    for (var i = 0; i < t.Frames; i += 2)
                    {
                        var r = t.P[i];
                        string J(int b) => $"{r[b].y - floor:0.00}/{Vector3.Dot(r[b] - r[Hips], t.Forward):+0.00;-0.00}";
                        sb.AppendLine($"  {i * t.Dt:0.000} hips {r[Hips].y:0.00}  Lf {J(LFoot)} Lt {J(LToes)}  Rf {J(RFoot)} Rt {J(RToes)}");
                    }
                }
            }
            var outPath = Path.GetFullPath(Path.Combine(Application.dataPath, "../../../Captures/gait_trace.txt"));
            File.WriteAllText(outPath, sb.ToString());
            Debug.Log("[gait] wrote " + outPath);
        }

        // ------------------------------------------------------------------ twist (yaw of the trunk and head against the pelvis)

        /// <summary>Per-frame yaw (degrees, + = towards the character's right) of the chest (UpperChest, else Chest),
        /// neck and head against the pelvis, from each bone's rotation relative to the rig's bind pose, plus the shoulder
        /// line against the hip line (what a front view shows).</summary>
        public sealed class Twist
        {
            public Stat Chest, Neck, Head, Shoulders;
            public float ChestMaxAbs, NeckMaxAbs, HeadMaxAbs;
            public override string ToString() =>
                $"chest {Chest.Mean,6:0.0} max|{ChestMaxAbs,5:0.0}|  neck {Neck.Mean,6:0.0} max|{NeckMaxAbs,5:0.0}|  head {Head.Mean,6:0.0} max|{HeadMaxAbs,5:0.0}|  shoulder line {Shoulders.Mean,6:0.0}";
        }

        public Twist MeasureTwist(AnimationClip clip, float fps = 30f)
        {
            var ci = tf[UpperChest] != null ? UpperChest : Chest;
            Transform hips = tf[Hips], chest = tf[ci], neck = tf[Neck], head = tf[Head];
            var bind = new[] { bindRot[Hips], bindRot[ci], bindRot[Neck], bindRot[Head] };
            var root = go.transform;
            float Yaw(Quaternion dHips, Quaternion d)
            {
                var up = dHips * Vector3.up;
                return Vector3.SignedAngle(Vector3.ProjectOnPlane(dHips * Vector3.forward, up), Vector3.ProjectOnPlane(d * Vector3.forward, up), up);
            }
            float Across(Vector3 l, Vector3 r)
            {
                var d = r - l; d.y = 0;
                return Mathf.Atan2(-d.z, d.x) * Mathf.Rad2Deg; // facing yaw implied by a left→right line (+ = right)
            }
            var n = Mathf.Max(2, Mathf.CeilToInt(clip.length * fps) + 1);
            var c = new List<float>(); var nk = new List<float>(); var h = new List<float>(); var sh = new List<float>();
            for (var i = 0; i < n; i++)
            {
                root.SetPositionAndRotation(Vector3.zero, Quaternion.identity);
                clip.SampleAnimation(go, clip.length * i / (n - 1));
                var dHips = hips.rotation * Quaternion.Inverse(bind[0]);
                c.Add(Yaw(dHips, chest.rotation * Quaternion.Inverse(bind[1])));
                nk.Add(Yaw(dHips, neck.rotation * Quaternion.Inverse(bind[2])));
                h.Add(Yaw(dHips, head.rotation * Quaternion.Inverse(bind[3])));
                sh.Add(Mathf.DeltaAngle(Across(tf[LUpperLeg].position, tf[RUpperLeg].position), Across(tf[LUpperArm].position, tf[RUpperArm].position)));
            }
            return new Twist
            {
                Chest = Stats(c), Neck = Stats(nk), Head = Stats(h), Shoulders = Stats(sh),
                ChestMaxAbs = c.Max(Mathf.Abs), NeckMaxAbs = nk.Max(Mathf.Abs), HeadMaxAbs = h.Max(Mathf.Abs),
            };
        }

        /// <summary>Trunk / head twist of every clip the controllers use, on the hero prefab and on the authoring rig
        /// (the animation FBX itself): logs "[twist]" lines and writes Captures/clip_twist.txt.
        /// Unity -batchmode -quit -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.ClipProbe.TwistReport</summary>
        [MenuItem("EOA/Test/Clip Twist (trunk and head yaw)")]
        public static void TwistReport()
        {
            var sb = new StringBuilder("yaw against the pelvis, degrees, + = to the character's right (mean, max |yaw|)\n");
            foreach (var style in new[] { "Male", "Female" })
            {
                using var hero = ForStyle(style);
                using var authoring = ForAnimRig(style);
                foreach (var kv in CharacterBuilder.LoadClips(style).OrderBy(k => k.Key))
                {
                    if (hero.Valid) sb.AppendLine($"[twist] {style,-6} {kv.Key,-12} {hero.RigName,-12} {hero.MeasureTwist(kv.Value)}");
                    if (authoring.Valid) sb.AppendLine($"[twist] {style,-6} {kv.Key,-12} {"authoring",-12} {authoring.MeasureTwist(kv.Value)}");
                }
            }
            var outPath = Path.GetFullPath(Path.Combine(Application.dataPath, "../../../Captures/clip_twist.txt"));
            File.WriteAllText(outPath, sb.ToString());
            Debug.Log("[twist] wrote " + outPath + "\n" + sb);
        }
    }
}
