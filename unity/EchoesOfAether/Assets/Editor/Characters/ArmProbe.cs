using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using UnityEditor;
using UnityEngine;
using Object = UnityEngine.Object;

namespace EOA.EditorTools
{
    /// <summary>
    /// Arm pose of the hero clips on the hero prefabs: upper-arm abduction and forward flexion against the torso, the
    /// hand-to-hand distance (against the shoulder width) and how far the hands sit in front of the pelvis, for idle, talk
    /// and walk. Each clip is measured four ways, so a difference can be pinned to its stage: sampled
    /// (<see cref="AnimationClip.SampleAnimation"/>), played by the hero's Animator controller, played with a
    /// <see cref="HumanPoseHandler"/> get/set round trip on top, and played with <see cref="HeroStance"/> on top (gameplay:
    /// upper body at 0.75; menu / designer: full body at 1). Arm muscles (Unity humanoid) are listed as read back after
    /// the controller. When Assets/_ArmDiag/&lt;Style&gt;/Anim_&lt;Style&gt;.fbx exists (an earlier export with its own import
    /// settings) its clips are measured too, through an override controller.
    /// Unity -batchmode -quit -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.ArmProbe.Report
    /// → Captures/arm_report.txt
    /// </summary>
    public static class ArmProbe
    {
        static readonly string[] ClipNames = { "idle", "talk", "walk" };
        static readonly string[] ArmMuscles =
        {
            "Left Shoulder Down-Up", "Left Shoulder Front-Back", "Left Arm Down-Up", "Left Arm Front-Back", "Left Arm Twist In-Out",
            "Left Forearm Stretch", "Left Forearm Twist In-Out",
            "Right Arm Down-Up", "Right Arm Front-Back", "Right Arm Twist In-Out", "Right Forearm Stretch",
        };

        public struct Arms
        {
            public float AbdL, AbdR, FlexL, FlexR, Hands, Shoulders, HandsFwd;
            public override string ToString() =>
                $"abduction L {AbdL,5:0.0} R {AbdR,5:0.0}  flexion L {FlexL,5:0.0} R {FlexR,5:0.0}  hands {Hands:0.00} m apart (shoulders {Shoulders:0.00}), {HandsFwd * 100f,4:0} cm in front of the pelvis";
        }

        /// <summary>Upper-arm abduction (out to the side, + = away from the body) and flexion (+ = forward) against the
        /// torso frame (up: hips→neck, side: the hip line), degrees from hanging straight down.</summary>
        public static Arms Measure(Animator a)
        {
            Transform B(HumanBodyBones b) => a.GetBoneTransform(b);
            var hips = B(HumanBodyBones.Hips).position;
            var up = (B(HumanBodyBones.Neck).position - hips).normalized;
            var right = Vector3.ProjectOnPlane(B(HumanBodyBones.RightUpperLeg).position - B(HumanBodyBones.LeftUpperLeg).position, up).normalized;
            var fwd = Vector3.Cross(right, up);
            float Abd(HumanBodyBones u, HumanBodyBones l, float side)
            {
                var v = B(l).position - B(u).position;
                return Mathf.Atan2(Vector3.Dot(v, right * side), Vector3.Dot(v, -up)) * Mathf.Rad2Deg;
            }
            float Flex(HumanBodyBones u, HumanBodyBones l)
            {
                var v = B(l).position - B(u).position;
                return Mathf.Atan2(Vector3.Dot(v, fwd), Vector3.Dot(v, -up)) * Mathf.Rad2Deg;
            }
            var lh = B(HumanBodyBones.LeftHand).position;
            var rh = B(HumanBodyBones.RightHand).position;
            return new Arms
            {
                AbdL = Abd(HumanBodyBones.LeftUpperArm, HumanBodyBones.LeftLowerArm, -1f),
                AbdR = Abd(HumanBodyBones.RightUpperArm, HumanBodyBones.RightLowerArm, 1f),
                FlexL = Flex(HumanBodyBones.LeftUpperArm, HumanBodyBones.LeftLowerArm),
                FlexR = Flex(HumanBodyBones.RightUpperArm, HumanBodyBones.RightLowerArm),
                Hands = (lh - rh).magnitude,
                Shoulders = (B(HumanBodyBones.LeftUpperArm).position - B(HumanBodyBones.RightUpperArm).position).magnitude,
                HandsFwd = Vector3.Dot((lh + rh) * 0.5f - hips, fwd),
            };
        }

        static Arms Mean(List<Arms> v) => new()
        {
            AbdL = v.Average(x => x.AbdL), AbdR = v.Average(x => x.AbdR), FlexL = v.Average(x => x.FlexL), FlexR = v.Average(x => x.FlexR),
            Hands = v.Average(x => x.Hands), Shoulders = v.Average(x => x.Shoulders), HandsFwd = v.Average(x => x.HandsFwd),
        };

        static Dictionary<string, AnimationClip> Clips(string path) =>
            AssetDatabase.LoadAllAssetsAtPath(path).OfType<AnimationClip>().Where(c => !c.name.StartsWith("__preview__"))
                .GroupBy(c => c.name).ToDictionary(g => g.Key, g => g.First());

        enum Mode { Sample, Animator, RoundTrip, StanceGame, StanceMenu }

        static string Run(GameObject prefab, RuntimeAnimatorController ctrl, AnimationClip clip, string name, Mode mode, out string muscles)
        {
            muscles = "";
            var go = Object.Instantiate(prefab);
            try
            {
                go.transform.SetPositionAndRotation(Vector3.zero, Quaternion.identity);
                var anim = go.GetComponent<Animator>();
                if (anim == null || !anim.isHuman) return "no humanoid animator";
                var frames = Mathf.Clamp(Mathf.RoundToInt(clip.length * 30f), 8, 150);
                var list = new List<Arms>();
                if (mode == Mode.Sample)
                {
                    for (var i = 0; i < frames; i++) { clip.SampleAnimation(go, clip.length * i / frames); list.Add(Measure(anim)); }
                    return Mean(list).ToString();
                }
                anim.runtimeAnimatorController = ctrl;
                anim.cullingMode = AnimatorCullingMode.AlwaysAnimate;
                anim.Rebind();
                HeroStance stance = null;
                MethodInfo late = null;
                if (mode is Mode.StanceGame or Mode.StanceMenu)
                {
                    stance = go.GetComponent<HeroStance>() ?? go.AddComponent<HeroStance>();
                    stance.UpperBodyOnly = mode == Mode.StanceGame;
                    stance.Weight = mode == Mode.StanceGame ? 0.75f : 1f;
                    typeof(HeroStance).GetMethod("Awake", BindingFlags.NonPublic | BindingFlags.Instance)?.Invoke(stance, null);
                    late = typeof(HeroStance).GetMethod("LateUpdate", BindingFlags.NonPublic | BindingFlags.Instance);
                }
                using var handler = new HumanPoseHandler(anim.avatar, anim.transform);
                var pose = new HumanPose();
                if (name == "talk") anim.Play("talk", anim.GetLayerIndex("Action"), 0f);
                else
                {
                    anim.SetFloat("Speed", name == "walk" ? 2.2f : 0f);
                    anim.Play("Locomotion", 0, 0f);
                }
                var idx = ArmMuscles.Select(m => Array.IndexOf(HumanTrait.MuscleName, m)).ToArray();
                var sum = new float[idx.Length];
                var n = 0;
                for (var i = 0; i < frames + 10; i++)
                {
                    anim.Update(1f / 30f);
                    if (mode == Mode.RoundTrip) { handler.GetHumanPose(ref pose); handler.SetHumanPose(ref pose); }
                    if (late != null) late.Invoke(stance, null);
                    if (i < 10) continue; // let the speed blend settle
                    list.Add(Measure(anim));
                    handler.GetHumanPose(ref pose);
                    for (var k = 0; k < idx.Length; k++) if (idx[k] >= 0) sum[k] += pose.muscles[idx[k]];
                    n++;
                }
                if (mode == Mode.Animator)
                    muscles = string.Join(", ", ArmMuscles.Select((m, k) => $"{m} {sum[k] / Mathf.Max(1, n):0.00}"));
                return Mean(list).ToString();
            }
            finally { Object.DestroyImmediate(go); }
        }

        [MenuItem("EOA/Test/Arm Probe (hero arm pose per stage)")]
        public static void Report()
        {
            var sb = new StringBuilder("abduction / flexion: upper arm against the torso, degrees from hanging straight down (+ = out / forward)\n");
            foreach (var (hero, style) in new[] { ("Kael", "Male"), ("Lyra", "Female") })
            {
                var prefab = Resources.Load<GameObject>("Characters/" + hero);
                var ctrl = prefab != null ? prefab.GetComponent<Animator>()?.runtimeAnimatorController : null;
                if (prefab == null || ctrl == null) { sb.AppendLine($"{hero}: no prefab / controller"); continue; }
                var variants = new List<(string tag, Dictionary<string, AnimationClip> clips, RuntimeAnimatorController ctrl)>
                    { ("now", CharacterBuilder.LoadClips(style), ctrl) };
                var oldPath = $"Assets/_ArmDiag/{style}/Anim_{style}.fbx";
                if (File.Exists(oldPath))
                {
                    var old = Clips(oldPath);
                    var ov = new AnimatorOverrideController(ctrl);
                    var pairs = new List<KeyValuePair<AnimationClip, AnimationClip>>();
                    ov.GetOverrides(pairs);
                    for (var i = 0; i < pairs.Count; i++)
                        if (pairs[i].Key != null && old.TryGetValue(pairs[i].Key.name, out var oc)) pairs[i] = new KeyValuePair<AnimationClip, AnimationClip>(pairs[i].Key, oc);
                    ov.ApplyOverrides(pairs);
                    variants.Insert(0, ("old", old, ov));
                }
                foreach (var (tag, clips, c) in variants)
                    foreach (var name in ClipNames)
                    {
                        if (!clips.TryGetValue(name, out var clip)) continue;
                        foreach (var mode in (Mode[])Enum.GetValues(typeof(Mode)))
                        {
                            var line = Run(prefab, c, clip, name, mode, out var muscles);
                            sb.AppendLine($"[arms] {hero,-5} {tag,-4} {name,-5} {mode,-10} {line}");
                            if (muscles.Length > 0) sb.AppendLine($"[arms] {hero,-5} {tag,-4} {name,-5} muscles {muscles}");
                        }
                    }
            }
            var outPath = Path.GetFullPath(Path.Combine(Application.dataPath, "../../../Captures/arm_report.txt"));
            File.WriteAllText(outPath, sb.ToString());
            Debug.Log("[arms] wrote " + outPath + "\n" + sb);
        }
    }
}
