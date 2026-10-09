using System;
using UnityEditor;
using UnityEngine;

namespace EOA.EditorTools
{
    /// <summary>
    /// Import-time safety net for the CMU animation sets (Anim_Male/Anim_Female.fbx).
    ///
    /// The posture fix now happens at the source: blender/anim/posture.py (run by cmu_retarget.py before export)
    /// re-centres spine, neck, head and wrists on the rig's upright rest, brings the trunk lean into natural bands,
    /// levels heads and gaze and straightens standing knees. This postprocessor only steps in when a channel still arrives
    /// far off (an older export, a new clip): neck / head / wrist muscle medians more than 0.3 from the rig's rest pose are re-centred on it, near-straight
    /// hands get a relaxed curl, and any measured offsets in posture_fix.json (<see cref="MocapPosture"/>, empty while
    /// the clips are in band) are added. Each intervention is logged as "[mocap] safety net on ...".
    /// </summary>
    public sealed class MocapNeckFix : AssetPostprocessor
    {
        const float Gain = 0.75f;

        static readonly string[] Muscles =
        {
            "Neck Nod Down-Up", "Neck Tilt Left-Right", "Neck Turn Left-Right",
            "Head Nod Down-Up", "Head Tilt Left-Right", "Head Turn Left-Right",
        };

        /// <summary>
        /// Wrists carry the same retarget offset (direction-only alignment of the CMU hand): hands stayed bent
        /// 30-55 degrees through idle, walk and run. They are re-centred on straight (0) and keep half their motion.
        /// </summary>
        const float WristGain = 0.5f;

        static readonly string[] WristMuscles =
        {
            "Left Hand Down-Up", "Left Hand In-Out", "Right Hand Down-Up", "Right Hand In-Out",
        };

        /// <summary>Clips whose hands should hang relaxed (the CMU fingers were near-straight with odd thumbs).</summary>
        static readonly string[] RelaxedHandClips =
        {
            "idle", "walk", "run", "sprint", "talk", "wave", "npc_crossed", "npc_hips", "npc_look", "npc_work", // npc_react: startled spread hands on purpose
            "interact", "pickup", "sit", "kneel_work", "lie", "wake", "climb", "jump", "fall", "land",
        };

        /// <summary>Natural relaxed hand ("Stretched" muscles: negative = curled), more curl towards the little finger.</summary>
        static float? RelaxedFinger(string property)
        {
            var dot = property.IndexOf('.');
            if (dot < 0 || !property.StartsWith("LeftHand.") && !property.StartsWith("RightHand.")) return null;
            var rest = property.Substring(dot + 1); // e.g. "Index.2 Stretched", "Thumb.Spread"
            return rest switch
            {
                "Thumb.1 Stretched" => -0.25f, "Thumb.2 Stretched" => 0.15f, "Thumb.3 Stretched" => 0.1f, "Thumb.Spread" => 0.25f,
                "Index.1 Stretched" => -0.15f, "Index.2 Stretched" => -0.35f, "Index.3 Stretched" => -0.25f, "Index.Spread" => 0.05f,
                "Middle.1 Stretched" => -0.25f, "Middle.2 Stretched" => -0.45f, "Middle.3 Stretched" => -0.3f, "Middle.Spread" => 0f,
                "Ring.1 Stretched" => -0.35f, "Ring.2 Stretched" => -0.5f, "Ring.3 Stretched" => -0.35f, "Ring.Spread" => -0.1f,
                "Little.1 Stretched" => -0.45f, "Little.2 Stretched" => -0.55f, "Little.3 Stretched" => -0.4f, "Little.Spread" => -0.25f,
                _ => null,
            };
        }

        const float RelaxedHandBlend = 0.85f;

        /// <summary>
        /// Safety net only. Since 2026-10-06 the source clips are posture-corrected in Blender (blender/anim/posture.py:
        /// neck, head and wrists re-centred on the rig's upright rest, relaxed finger poses), so a clip is only touched
        /// here when a channel is still far off: neck / head / wrist medians beyond <see cref="Tolerance"/> muscle units
        /// (~12 deg) are re-centred, and hands that arrive nearly straight get the relaxed curl. Everything done is logged.
        /// </summary>
        const float Tolerance = 0.3f, HeadTolerance = 0.45f;

        /// <summary>Clips whose head pose the source keeps on purpose (lying, getting up, looking at the hands, leaps).</summary>
        static readonly string[] SourceHeadClips = { "lie", "wake", "death", "kneel_work", "pickup", "climb", "k_ult", "l_ult", "l_echo", "stagger" };
        const float StraightHand = -0.12f; // Index.2 Stretched median above this = a near-straight hand

        float[] restMuscles;

        /// <summary>
        /// Muscle values of the rig's rest pose (upright, level head, straight wrists): Unity's muscle zero is not this
        /// rig's rest (the neck / head sit at about -0.4 / +0.6 nod and -0.6 tilt in muscle space), so the safety net
        /// measures and re-centres against the rest pose. Built once per import from the model's bind pose.
        /// </summary>
        float[] RestMuscles(GameObject root)
        {
            if (restMuscles != null) return restMuscles;
            restMuscles = Array.Empty<float>();
            try
            {
                var hd = ((ModelImporter)assetImporter).humanDescription;
                if (hd.human == null || hd.human.Length == 0) return restMuscles;
                var copy = UnityEngine.Object.Instantiate(root);
                try
                {
                    // Rest (bind) pose of the copy: the importer's skeleton entries hold the T-posed arms/legs, so take
                    // the transforms as imported (the FBX rest) for the trunk, neck and head.
                    var avatar = AvatarBuilder.BuildHumanAvatar(copy, hd);
                    if (avatar == null || !avatar.isHuman) return restMuscles;
                    using var handler = new HumanPoseHandler(avatar, copy.transform);
                    var pose = new HumanPose();
                    handler.GetHumanPose(ref pose);
                    restMuscles = pose.muscles;
                    UnityEngine.Object.DestroyImmediate(avatar);
                }
                finally { UnityEngine.Object.DestroyImmediate(copy); }
            }
            catch (Exception e) { Debug.LogWarning($"[mocap] rest muscles unavailable for {assetPath}: {e.Message}"); }
            return restMuscles;
        }

        float Rest(GameObject root, string muscle)
        {
            var r = RestMuscles(root);
            var i = Array.IndexOf(HumanTrait.MuscleName, muscle);
            return i >= 0 && i < r.Length ? r[i] : 0f;
        }

        static float Median(AnimationCurve c)
        {
            var v = new float[c.length];
            for (var i = 0; i < c.length; i++) v[i] = c.keys[i].value;
            Array.Sort(v);
            return v[v.Length / 2];
        }

        void OnPostprocessAnimation(GameObject root, AnimationClip clip)
        {
            if (!assetPath.StartsWith("Assets/Art/Animations/Anim_", StringComparison.Ordinal)) return;
            var bindings = AnimationUtility.GetCurveBindings(clip);
            var done = new System.Collections.Generic.List<string>();
            var relaxedHands = false;
            if (Array.IndexOf(RelaxedHandClips, clip.name) >= 0)
                foreach (var b in bindings)
                    if (b.type == typeof(Animator) && b.propertyName == "LeftHand.Index.2 Stretched")
                    {
                        var c = AnimationUtility.GetEditorCurve(clip, b);
                        relaxedHands = c != null && c.length > 0 && Median(c) - Rest(root, "Left Index 2 Stretched") > StraightHand;
                    }
            foreach (var b in bindings)
            {
                if (b.type != typeof(Animator)) continue;
                if (relaxedHands && RelaxedFinger(b.propertyName) is { } target)
                {
                    var fc = AnimationUtility.GetEditorCurve(clip, b);
                    if (fc == null || fc.length == 0) continue;
                    var fk = fc.keys;
                    for (var i = 0; i < fk.Length; i++)
                    {
                        fk[i].value = Mathf.Lerp(fk[i].value, target, RelaxedHandBlend);
                        fk[i].inTangent *= 1 - RelaxedHandBlend;
                        fk[i].outTangent *= 1 - RelaxedHandBlend;
                    }
                    fc.keys = fk;
                    clip.SetCurve(b.path, b.type, b.propertyName, fc);
                    continue;
                }
                var wrist = Array.IndexOf(WristMuscles, b.propertyName) >= 0;
                if (!wrist && Array.IndexOf(Muscles, b.propertyName) < 0) continue;
                var curve = AnimationUtility.GetEditorCurve(clip, b);
                if (curve == null || curve.length == 0) continue;
                if (!wrist && Array.IndexOf(SourceHeadClips, clip.name) >= 0) continue;
                var median = Median(curve);
                var rest = Rest(root, b.propertyName);
                if (Mathf.Abs(median - rest) <= (wrist ? Tolerance : HeadTolerance)) continue;
                var gain = wrist ? WristGain : Gain;
                var keys = curve.keys;
                for (var i = 0; i < keys.Length; i++)
                {
                    keys[i].value = rest + (keys[i].value - median) * gain;
                    keys[i].inTangent *= gain;
                    keys[i].outTangent *= gain;
                }
                curve.keys = keys;
                clip.SetCurve(b.path, b.type, b.propertyName, curve);
                done.Add($"{b.propertyName} {median:0.00} (rest {rest:0.00})");
            }
            if (relaxedHands) done.Add("relaxed hands");
            if (done.Count > 0) Debug.Log($"[mocap] safety net on {assetPath}/{clip.name}: {string.Join(", ", done)}");
            // Measured posture offsets (torso lean, neck against torso, gaze) solved by MocapPosture.Calibrate; zero while
            // the source clips are in band.
            MocapPosture.Apply(clip, MocapPosture.Offsets(assetPath.Contains("Anim_Female") ? "Female" : "Male", clip.name));
        }
    }
}
