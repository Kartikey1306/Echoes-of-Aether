using System.IO;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEngine;

namespace EOA.EditorTools
{
    /// <summary>
    /// Avatar diagnostics: human bone mapping of the animation and character FBXs, and the head pose (relative to the
    /// chest) of the idle clip sampled on each hero. Writes Captures/avatar_diag.txt.
    /// Unity -batchmode -quit -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.AvatarDiag.Run
    /// </summary>
    public static class AvatarDiag
    {
        [MenuItem("EOA/Test/Avatar Diagnostics")]
        public static void Run()
        {
            var sb = new StringBuilder();
            foreach (var path in new[]
                     {
                         "Assets/Art/Animations/Anim_Female.fbx", "Assets/Art/Animations/Anim_Male.fbx",
                         "Assets/Art/Characters/Lyra/Lyra.fbx", "Assets/Art/Characters/Kael/Kael.fbx", "Assets/Art/Characters/Oren/Oren.fbx",
                     })
            {
                var mi = AssetImporter.GetAtPath(path) as ModelImporter;
                if (mi == null) { sb.AppendLine("missing " + path); continue; }
                var hd = mi.humanDescription;
                sb.AppendLine($"== {path}: {hd.human?.Length ?? 0} human bones, {hd.skeleton?.Length ?? 0} skeleton bones");
                foreach (var h in hd.human ?? new HumanBone[0])
                    if (h.humanName.Contains("Head") || h.humanName.Contains("Neck") || h.humanName.Contains("Chest") || h.humanName.Contains("Spine") || h.humanName.Contains("Jaw") || h.humanName.Contains("Eye") || h.humanName.Contains("Hips") || h.humanName.Contains("LowerLeg"))
                        sb.AppendLine($"   {h.humanName,-14} -> {h.boneName}");
                var avatar = AssetDatabase.LoadAllAssetsAtPath(path).OfType<Avatar>().FirstOrDefault();
                sb.AppendLine($"   avatar valid={avatar != null && avatar.isValid} human={avatar != null && avatar.isHuman}");
            }

            foreach (var (hero, anim) in new[] { ("Lyra", "Female"), ("Kael", "Male") })
            {
                var prefab = Resources.Load<GameObject>("Characters/" + hero);
                var clip = AssetDatabase.LoadAllAssetsAtPath($"Assets/Art/Animations/Anim_{anim}.fbx").OfType<AnimationClip>().FirstOrDefault(c => c.name == "idle");
                if (prefab == null || clip == null) { sb.AppendLine($"skip {hero}: prefab {prefab != null} clip {clip != null}"); continue; }
                var go = Object.Instantiate(prefab);
                var an = go.GetComponent<Animator>();
                var head = an.GetBoneTransform(HumanBodyBones.Head);
                var chest = an.GetBoneTransform(HumanBodyBones.UpperChest) ?? an.GetBoneTransform(HumanBodyBones.Chest);
                var rest = Quaternion.Inverse(chest.rotation) * head.rotation;
                sb.AppendLine($"== {hero} idle ({clip.length:0.00}s): head vs chest, degrees from rest pose (pitch, yaw, roll)");
                for (var i = 0; i <= 8; i++)
                {
                    var t = clip.length * i / 8f;
                    clip.SampleAnimation(go, t);
                    var rel = Quaternion.Inverse(rest) * (Quaternion.Inverse(chest.rotation) * head.rotation);
                    var e = rel.eulerAngles;
                    float W(float a) => a > 180 ? a - 360 : a;
                    float ArmDown(HumanBodyBones u, HumanBodyBones l) => Vector3.Angle(an.GetBoneTransform(l).position - an.GetBoneTransform(u).position, Vector3.down);
                    sb.AppendLine($"   t={t:0.00}  head ({W(e.x):0.0}, {W(e.y):0.0}, {W(e.z):0.0})  upper arms from vertical L {ArmDown(HumanBodyBones.LeftUpperArm, HumanBodyBones.LeftLowerArm):0} R {ArmDown(HumanBodyBones.RightUpperArm, HumanBodyBones.RightLowerArm):0}");
                }
                Object.DestroyImmediate(go);
            }
            // Locomotion check: wrist bend/twist and foot contact for the clips the player sees most.
            foreach (var (hero, anim) in new[] { ("Lyra", "Female"), ("Kael", "Male") })
            {
                var prefab = Resources.Load<GameObject>("Characters/" + hero);
                var clips = AssetDatabase.LoadAllAssetsAtPath($"Assets/Art/Animations/Anim_{anim}.fbx").OfType<AnimationClip>().ToDictionary(c => c.name);
                if (prefab == null) continue;
                var go = Object.Instantiate(prefab);
                var an = go.GetComponent<Animator>();
                Transform B(HumanBodyBones b) => an.GetBoneTransform(b);
                foreach (var name in new[] { "idle", "walk", "run", "sprint", "combat_idle", "k_light1", "l_quick1", "talk" })
                {
                    if (!clips.TryGetValue(name, out var clip)) continue;
                    float maxBendL = 0, maxBendR = 0, sumBend = 0, minFoot = 99, maxFoot = -99, sumLowFoot = 0; var n = 0;
                    for (var i = 0; i < 16; i++)
                    {
                        clip.SampleAnimation(go, clip.length * i / 16f);
                        float Bend(HumanBodyBones fore, HumanBodyBones hand, HumanBodyBones mid)
                        {
                            var f = B(hand).position - B(fore).position;
                            var h = B(mid) != null ? B(mid).position - B(hand).position : f;
                            return Vector3.Angle(f, h);
                        }
                        var bl = Bend(HumanBodyBones.LeftLowerArm, HumanBodyBones.LeftHand, HumanBodyBones.LeftMiddleProximal);
                        var br = Bend(HumanBodyBones.RightLowerArm, HumanBodyBones.RightHand, HumanBodyBones.RightMiddleProximal);
                        maxBendL = Mathf.Max(maxBendL, bl); maxBendR = Mathf.Max(maxBendR, br); sumBend += (bl + br) / 2;
                        var lf = Mathf.Min(B(HumanBodyBones.LeftFoot).position.y, B(HumanBodyBones.LeftToes) != null ? B(HumanBodyBones.LeftToes).position.y : 9);
                        var rf = Mathf.Min(B(HumanBodyBones.RightFoot).position.y, B(HumanBodyBones.RightToes) != null ? B(HumanBodyBones.RightToes).position.y : 9);
                        var low = Mathf.Min(lf, rf) - go.transform.position.y;
                        minFoot = Mathf.Min(minFoot, low); maxFoot = Mathf.Max(maxFoot, low); sumLowFoot += low; n++;
                    }
                    sb.AppendLine($"== {hero} {name}: wrist bend avg {sumBend / n:0} deg, max L {maxBendL:0} R {maxBendR:0}; lowest foot/toe joint height min {minFoot:0.000} avg {sumLowFoot / n:0.000} max {maxFoot:0.000} m");
                }
                Object.DestroyImmediate(go);
            }
            // Posture and hands: torso pitch, finger curl, and the clip's spine/finger muscle medians (binding names).
            foreach (var (hero, anim) in new[] { ("Lyra", "Female"), ("Kael", "Male") })
            {
                var prefab = Resources.Load<GameObject>("Characters/" + hero);
                var clips = AssetDatabase.LoadAllAssetsAtPath($"Assets/Art/Animations/Anim_{anim}.fbx").OfType<AnimationClip>().ToDictionary(c => c.name);
                if (prefab == null) continue;
                var go = Object.Instantiate(prefab);
                var an = go.GetComponent<Animator>();
                Transform B(HumanBodyBones b) => an.GetBoneTransform(b);
                foreach (var name in new[] { "idle", "walk", "run", "combat_idle", "talk" })
                {
                    if (!clips.TryGetValue(name, out var clip)) continue;
                    float pitch = 0, headFwd = 0, curl = 0; var n = 0;
                    for (var i = 0; i < 8; i++)
                    {
                        clip.SampleAnimation(go, clip.length * i / 8f);
                        var torso = B(HumanBodyBones.Neck).position - B(HumanBodyBones.Hips).position;
                        pitch += Vector3.Angle(torso, Vector3.up);
                        var neck = B(HumanBodyBones.Head).position - B(HumanBodyBones.Neck).position;
                        headFwd += Vector3.Angle(neck, Vector3.up);
                        var p1 = B(HumanBodyBones.LeftIndexIntermediate).position - B(HumanBodyBones.LeftIndexProximal).position;
                        var p0 = B(HumanBodyBones.LeftIndexProximal).position - B(HumanBodyBones.LeftHand).position;
                        curl += Vector3.Angle(p0, p1);
                        n++;
                    }
                    sb.AppendLine($"== {hero} {name}: torso tilt from vertical {pitch / n:0.0} deg, neck tilt {headFwd / n:0.0} deg, index finger curl {curl / n:0.0} deg");
                }
                if (clips.TryGetValue("idle", out var idle))
                {
                    var med = new StringBuilder();
                    foreach (var bnd in AnimationUtility.GetCurveBindings(idle))
                    {
                        if (bnd.type != typeof(Animator)) continue;
                        var pn = bnd.propertyName;
                        if (!(pn.Contains("Spine") || pn.Contains("Chest") || pn.Contains("Index") || pn.Contains("Shoulder") || pn.Contains("Arm Down") || pn.Contains("Thumb"))) continue;
                        var c = AnimationUtility.GetEditorCurve(idle, bnd);
                        var vals = c.keys.Select(k => k.value).OrderBy(v => v).ToArray();
                        med.Append($"{pn}={vals[vals.Length / 2]:0.00}; ");
                    }
                    sb.AppendLine($"   {anim} idle medians: {med}");
                }
                Object.DestroyImmediate(go);
            }
            var outPath = Path.GetFullPath(Path.Combine(Application.dataPath, "../../../Captures/avatar_diag.txt"));
            File.WriteAllText(outPath, sb.ToString());
            Debug.Log("[avatar] wrote " + outPath + "\n" + sb);
        }
    }
}
