using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;
using Object = UnityEngine.Object;

namespace EOA.EditorTools
{
    /// <summary>
    /// Quaternius Universal Animation Library (UAL 1 and UAL 2, CC0 1.0, quaternius.com) as a clip source between Mixamo
    /// and CMU: a game clip uses Mixamo when a file was dropped for it, else its UAL take (<see cref="UalMap"/>), else the
    /// CMU clip. The two library FBX files are copied from &lt;repo&gt;/incoming/ual/ (any depth; -ualIncoming &lt;dir&gt; or
    /// EOA_UAL_INCOMING override it) to Assets/Art/Animations/UAL/ and imported as Humanoid, one clip per mapped game clip.
    ///
    /// Avatar: the libraries' bone names (Rigify DEF-* in UAL 1, UE-style in UAL 2) are mapped explicitly, and the avatar's
    /// T-pose is built exactly like the heroes' (<see cref="CharacterBuilder"/>): the rig's own neutral rest (the A_TPose
    /// take, first in the file, so Unity's default pose; upright trunk, square chest, natural clavicles) with the arms
    /// aimed straight out and the legs straight down. Both avatars thus define muscle zero the same way: rest maps to
    /// rest (no twisted or posed reference frame, the lesson of the CMU trunk twist) and the limbs share the canonical
    /// T-pose (no clavicle or arm offset, the lesson of the clasped hands). Matching bone directions to the hero instead
    /// was tried and rejected: UAL's pelvis and clavicle segments are built differently from MPFB's, so copying their
    /// directions pushed the heroes' shoulders back (head 14 cm ahead of the shoulders).
    ///
    /// Each clip then goes through the same steps as a Mixamo clip, per hero style: analysis on the style's hero rig
    /// (<see cref="ClipProbe"/>), combat re-timing (strike onto the tuned hit time) or duration fitting
    /// (<see cref="Plan"/>), the gait phase alignment, and the posture bands of <see cref="MocapPosture"/> (trunk lean,
    /// straight standing knees, neck in line, level gaze) solved on that hero and baked in. The result is written to
    /// UAL/Generated/&lt;style&gt;/&lt;clip&gt;.anim and recorded in clip_sources.json with source "ual"; gaits use their
    /// measured stride speed (<see cref="Gaits"/>).
    /// </summary>
    public static partial class MixamoImporter
    {
        public const string UalRoot = "Assets/Art/Animations/UAL";
        const string UalGeneratedRoot = UalRoot + "/Generated";

        /// <summary>Library project copies (UAL/&lt;name&gt;.fbx) and the file each is copied from in the drop folder.</summary>
        static readonly (string library, string file)[] UalLibraries =
            { ("UAL1", "AnimationLibrary_Unity_Standard.fbx"), ("UAL2", "UAL2_Standard.fbx") };

        public readonly struct UalClip
        {
            public readonly string Library, Take;
            /// <summary>Source range in seconds (To &lt; 0: to the end of the take).</summary>
            public readonly float From, To;
            public UalClip(string library, string take, float from = 0f, float to = -1f) { Library = library; Take = take; From = from; To = to; }
        }

        /// <summary>
        /// Game clip → UAL take. Clips not listed keep Mixamo / CMU: the walk (both UAL walks are strolls authored for
        /// 1.05 m/s; the heroes walk at 2.2 m/s, so they slid 0.75 m/s or would need double cadence), the run and sprint
        /// (forefoot strides leaning 24° / 37°: brought upright on the heroes, the planted-foot slip rose from 0.3-0.9 to
        /// 2.7 m/s and 1.5-1.8 to 3.3 m/s; kept for a later pass), the combat stance (UAL has no boxing guard loop),
        /// crouch (UAL's is a deep stealth squat, trunk 44°), dash and phase step (a full roll does not fit a 0.36 s dash),
        /// stagger (UAL's knockback ends lying down), wave, the NPC look / hips / work / react idles, kneeling work, lying,
        /// waking, climbing, Kael's leap and Giva's spin ultimates, and Giva's left-handed aim and fire (UAL aims a pistol).
        /// </summary>
        public static readonly Dictionary<string, UalClip> UalMap = new()
        {
            // locomotion and stance
            ["idle"] = new("UAL1", "Idle_Loop"),
            ["jump"] = new("UAL1", "Jump_Start"),
            ["fall"] = new("UAL1", "Jump_Loop"),
            ["land"] = new("UAL1", "Jump_Land"),
            // reactions, interaction, NPC and conversation
            ["hit"] = new("UAL1", "Hit_Chest"),
            ["death"] = new("UAL1", "Death01"),
            ["interact"] = new("UAL1", "Interact"),
            ["pickup"] = new("UAL1", "PickUp_Table"),
            ["talk"] = new("UAL1", "Idle_Talking_Loop"),
            ["sit"] = new("UAL1", "Sitting_Idle_Loop"),
            ["npc_crossed"] = new("UAL2", "Idle_FoldArms_Loop"),
            // Kael: jab, cross, hook, overhead blade smash, forearm pulse; pistol aim and shot
            ["k_light1"] = new("UAL1", "Punch_Jab"),
            ["k_light2"] = new("UAL1", "Punch_Cross"),
            ["k_light3"] = new("UAL2", "Melee_Hook"),
            ["k_heavy"] = new("UAL1", "Sword_Attack"),
            ["k_pulse"] = new("UAL1", "Spell_Simple_Shoot"),
            ["aim_r"] = new("UAL1", "Pistol_Aim_Neutral"),
            ["fire_r"] = new("UAL1", "Pistol_Shoot"),
            // Giva: quick slashes, heavy slash, echo throw
            ["l_quick1"] = new("UAL2", "Sword_Regular_A"),
            ["l_quick2"] = new("UAL2", "Sword_Regular_B"),
            ["l_heavy"] = new("UAL2", "Sword_Regular_C"),
            ["l_echo"] = new("UAL2", "OverhandThrow"),
        };

        /// <summary>
        /// Ground speed (m/s) each UAL gait take was authored for on the UAL mannequin: median backward speed of the
        /// planted sole joint relative to the hips, measured in Blender on the source file (2026-10-08). The in-editor
        /// stride probes misread the short forefoot stances of the jog and sprint.
        /// </summary>
        static readonly Dictionary<string, float> UalGaitSpeed = new() { ["Walk_Loop"] = 1.06f, ["Jog_Fwd_Loop"] = 5.90f, ["Sprint_Loop"] = 8.90f };

        /// <summary>Humanoid bone map: UAL 1 (Rigify DEF-*), UAL 2 (UE-style) → Unity human bone.</summary>
        static readonly (string ual1, string ual2, string human)[] UalBones = BuildUalBones();

        static (string, string, string)[] BuildUalBones()
        {
            var list = new List<(string, string, string)>
            {
                ("DEF-hips", "pelvis", "Hips"), ("DEF-spine.001", "spine_01", "Spine"), ("DEF-spine.002", "spine_02", "Chest"),
                ("DEF-spine.003", "spine_03", "UpperChest"), ("DEF-neck", "neck_01", "Neck"), ("DEF-head", "Head", "Head"),
            };
            foreach (var (s1, s2, side) in new[] { (".L", "_l", "Left"), (".R", "_r", "Right") })
            {
                list.Add(($"DEF-shoulder{s1}", $"clavicle{s2}", $"{side}Shoulder"));
                list.Add(($"DEF-upper_arm{s1}", $"upperarm{s2}", $"{side}UpperArm"));
                list.Add(($"DEF-forearm{s1}", $"lowerarm{s2}", $"{side}LowerArm"));
                list.Add(($"DEF-hand{s1}", $"hand{s2}", $"{side}Hand"));
                list.Add(($"DEF-thigh{s1}", $"thigh{s2}", $"{side}UpperLeg"));
                list.Add(($"DEF-shin{s1}", $"calf{s2}", $"{side}LowerLeg"));
                list.Add(($"DEF-foot{s1}", $"foot{s2}", $"{side}Foot"));
                list.Add(($"DEF-toe{s1}", $"ball{s2}", $"{side}Toes"));
                foreach (var (f1, f2, human) in new[] { ("thumb", "thumb", "Thumb"), ("f_index", "index", "Index"), ("f_middle", "middle", "Middle"), ("f_ring", "ring", "Ring"), ("f_pinky", "pinky", "Little") })
                    for (var i = 1; i <= 3; i++)
                        list.Add(($"DEF-{f1}.0{i}{s1}", $"{f2}_0{i}{s2}", $"{side} {human} {(i == 1 ? "Proximal" : i == 2 ? "Intermediate" : "Distal")}"));
            }
            return list.ToArray();
        }

        public static string UalIncomingDir
        {
            get
            {
                var args = Environment.GetCommandLineArgs();
                var i = Array.IndexOf(args, "-ualIncoming");
                if (i >= 0 && i + 1 < args.Length) return Path.GetFullPath(args[i + 1]);
                var env = Environment.GetEnvironmentVariable("EOA_UAL_INCOMING");
                if (!string.IsNullOrEmpty(env)) return Path.GetFullPath(env);
                return Path.GetFullPath(Path.Combine(Application.dataPath, "..", "..", "..", "incoming", "ual"));
            }
        }

        static string UalFbx(string library) => $"{UalRoot}/{library}.fbx";
        static string UalGenerated(string style, string clip) => $"{UalGeneratedRoot}/{style.ToLowerInvariant()}/{clip}.anim";

        /// <summary>UAL clips generated for a style (game clip name → clip).</summary>
        public static Dictionary<string, AnimationClip> UalClipsFor(string style)
        {
            var result = new Dictionary<string, AnimationClip>();
            foreach (var name in UalMap.Keys)
            {
                var path = UalGenerated(style, name);
                if (!File.Exists(path)) continue;
                var clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(path);
                if (clip != null) result[name] = clip;
            }
            return result;
        }

        /// <summary>"mixamo", "ual" or "cmu" by where a clip lives.</summary>
        public static string SourceOf(AnimationClip clip)
        {
            var path = clip != null ? AssetDatabase.GetAssetPath(clip) : "";
            return path.StartsWith(AssetRoot + "/", StringComparison.Ordinal) ? "mixamo"
                : path.StartsWith(UalRoot + "/", StringComparison.Ordinal) ? "ual" : "cmu";
        }

        /// <summary>Imported library clip (Mixamo or UAL): measured stride, analysed timing.</summary>
        public static bool IsImported(AnimationClip clip) => SourceOf(clip) != "cmu";

        // ------------------------------------------------------------------ copy and import

        static void SyncUal(JArray log)
        {
            var src = UalIncomingDir;
            if (!Directory.Exists(src)) { log.Add($"UAL drop folder {src} does not exist"); return; }
            foreach (var (library, file) in UalLibraries)
            {
                var found = Directory.GetFiles(src, file, SearchOption.AllDirectories).FirstOrDefault(f => f.Replace('\\', '/').Contains("/Unity/"))
                            ?? Directory.GetFiles(src, file, SearchOption.AllDirectories).FirstOrDefault();
                if (found == null) { log.Add($"UAL: {file} not found under {src}"); continue; }
                var dst = UalFbx(library);
                if (File.Exists(dst) && Hash(dst) == Hash(found)) continue;
                Directory.CreateDirectory(UalRoot);
                File.Copy(found, dst, true);
                log.Add($"copied {found} -> {dst}");
                Debug.Log($"[ual] copied {found} -> {dst}");
            }
        }

        /// <summary>Import settings of a library copy: Humanoid with the matched avatar, one clip per mapped game clip.
        /// Re-imports only when the settings changed.</summary>
        static void ConfigureUal(string library, JObject meta, JArray log)
        {
            var fbx = UalFbx(library);
            var mi = (ModelImporter)AssetImporter.GetAtPath(fbx);
            if (mi == null) throw new Exception($"{fbx} did not import");
            if (!mi.bakeAxisConversion)
            {
                // Quaternius' Unity setup: bake the axis conversion first; the reference pose is read from that import.
                mi.bakeAxisConversion = true;
                mi.SaveAndReimport();
            }
            var model = AssetDatabase.LoadAssetAtPath<GameObject>(fbx);
            if (model == null) throw new Exception($"{fbx} did not import");
            var names = new HashSet<string>(model.GetComponentsInChildren<Transform>(true).Select(t => t.name));
            var map = UalBones.Select(b => (bone: library == "UAL1" ? b.ual1 : b.ual2, b.human)).Where(b => names.Contains(b.bone))
                .Select(b => new HumanBone { humanName = b.human, boneName = b.bone, limit = new HumanLimit { useDefaultValues = true } }).ToList();
            if (map.Count < 20) throw new Exception($"{fbx}: only {map.Count} UAL bones found");
            var skeleton = UalSkeleton(model, map, out var aimLog);
            var takes = mi.importedTakeInfos;
            var clips = new List<ModelImporterClipAnimation>();
            foreach (var (name, uc) in UalMap.Where(kv => kv.Value.Library == library).OrderBy(kv => kv.Key))
            {
                var take = takes.FirstOrDefault(t => t.name == uc.Take || t.name.EndsWith("|" + uc.Take, StringComparison.Ordinal));
                if (string.IsNullOrEmpty(take.name)) { log.Add($"UAL {library}: no take {uc.Take} for {name}"); continue; }
                var loop = (bool?)meta["male"]?[name]?["loop"] ?? false;
                var c = RawClip(name, take, loop);
                if (uc.From > 0f) c.firstFrame = (take.startTime + uc.From) * take.sampleRate;
                if (uc.To > 0f) c.lastFrame = Mathf.Min(take.stopTime, take.startTime + uc.To) * take.sampleRate;
                clips.Add(c);
            }
            var fingerprint = string.Join(";", map.Select(b => $"{b.humanName}={b.boneName}")) + "|" +
                              string.Join(";", skeleton.Select(sb => $"{sb.name}:{sb.rotation.x:0.0000},{sb.rotation.y:0.0000},{sb.rotation.z:0.0000},{sb.rotation.w:0.0000}")) + "|" +
                              string.Join(";", clips.Select(c => $"{c.name}:{c.takeName}:{c.firstFrame:0.00}-{c.lastFrame:0.00}:{c.loopTime}"));
            fingerprint = "ual-v2 " + TextHash(fingerprint);
            if (mi.userData == fingerprint && mi.animationType == ModelImporterAnimationType.Human)
            {
                log.Add($"UAL {library}: import settings unchanged ({clips.Count} clips)");
                return;
            }
            mi.animationType = ModelImporterAnimationType.Human;
            mi.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
            mi.bakeAxisConversion = true;
            var hd = mi.humanDescription;
            hd.human = map.ToArray();
            hd.skeleton = skeleton;
            hd.upperArmTwist = 0.5f; hd.lowerArmTwist = 0.5f; hd.upperLegTwist = 0.5f; hd.lowerLegTwist = 0.5f;
            hd.armStretch = 0.05f; hd.legStretch = 0.05f; hd.feetSpacing = 0; hd.hasTranslationDoF = false;
            mi.humanDescription = hd;
            mi.importAnimation = true;
            mi.materialImportMode = ModelImporterMaterialImportMode.None;
            mi.importCameras = false;
            mi.importLights = false;
            mi.importVisibility = false;
            mi.importBlendShapes = false;
            mi.resampleCurves = true;
            mi.animationCompression = ModelImporterAnimationCompression.Off;
            mi.clipAnimations = clips.ToArray();
            mi.userData = fingerprint;
            mi.SaveAndReimport();
            var avatar = AssetDatabase.LoadAllAssetsAtPath(fbx).OfType<Avatar>().FirstOrDefault();
            if (avatar == null || !avatar.isHuman || !avatar.isValid) throw new Exception($"{fbx}: humanoid avatar is invalid");
            log.Add($"UAL {library}: imported {clips.Count} clips, avatar T-pose from the A_TPose rest ({aimLog})");
        }

        /// <summary>
        /// Move the foot IK goal curves (LeftFootT/Q, RightFootT/Q) of a posture-corrected clip with its feet: the change
        /// of each ankle between <paramref name="src"/> (before the correction) and <paramref name="dst"/>, both sampled
        /// on the hero rig, is expressed in the body frame (RootT / RootQ, normalised by the human scale) and added to the
        /// goals, so the authored contact placement survives (a body pitched back no longer drags the goals with it) and a
        /// straightened standing knee is not bent again by the foot IK. The body-frame convention is checked against the
        /// source clip (the goals minus the sampled ankles must be near constant); otherwise the goals are left alone.
        /// </summary>
        static string SyncFootGoals(AnimationClip src, AnimationClip dst, ClipProbe probe)
        {
            EditorCurveBinding Bind(string p) => EditorCurveBinding.FloatCurve("", typeof(Animator), p);
            var keyCurve = AnimationUtility.GetEditorCurve(dst, Bind("LeftFootT.x"));
            if (keyCurve == null || keyCurve.length < 2) return "no foot goal curves";
            var times = keyCurve.keys.Select(k => k.time).ToArray();
            AnimationCurve[] Curves(AnimationClip c, string p, int n) =>
                (n == 3 ? new[] { "x", "y", "z" } : new[] { "x", "y", "z", "w" }).Select(a => AnimationUtility.GetEditorCurve(c, Bind($"{p}.{a}"))).ToArray();
            Vector3 V(AnimationCurve[] c, float t) => new(c[0].Evaluate(t), c[1].Evaluate(t), c[2].Evaluate(t));
            Quaternion Q(AnimationCurve[] c, float t) => Quaternion.Normalize(new Quaternion(c[0].Evaluate(t), c[1].Evaluate(t), c[2].Evaluate(t), c[3].Evaluate(t)));
            var rtO = Curves(src, "RootT", 3); var rqO = Curves(src, "RootQ", 4);
            var rtN = Curves(dst, "RootT", 3); var rqN = Curves(dst, "RootQ", 4);
            if (rtO.Concat(rqO).Concat(rtN).Concat(rqN).Any(c => c == null)) return "no body curves";
            var so = Neutral(src);
            var sn = Neutral(dst);
            try
            {
                var fo = probe.SampleFeet(so, times);
                var fn = probe.SampleFeet(sn, times);
                var hs = Mathf.Max(1e-4f, probe.HumanScale);
                var report = new List<string>();
                foreach (var (goal, left) in new[] { ("LeftFoot", true), ("RightFoot", false) })
                {
                    var gt = Curves(src, goal + "T", 3);
                    var gq = Curves(src, goal + "Q", 4);
                    if (gt.Concat(gq).Any(c => c == null)) { report.Add($"{goal}: no curves"); continue; }
                    var po = left ? fo.lp : fo.rp; var qo = left ? fo.lq : fo.rq;
                    var pn = left ? fn.lp : fn.rp; var qn = left ? fn.lq : fn.rq;
                    var n = times.Length;
                    // Ankle in the body frame (rotated by RootQ) or only offset from the body: the convention whose
                    // residual against the authored goal stays constant is the clip's.
                    Vector3 Local(Vector3 p, Vector3 rt, Quaternion rq, bool rotated) => rotated ? Quaternion.Inverse(rq) * (p / hs - rt) : p / hs - rt;
                    float Spread(bool rotated)
                    {
                        var res = Enumerable.Range(0, n).Select(i => V(gt, times[i]) - Local(po[i], V(rtO, times[i]), Q(rqO, times[i]), rotated)).ToArray();
                        var mean = res.Aggregate(Vector3.zero, (a, b) => a + b) / n;
                        return Mathf.Sqrt(res.Average(r => (r - mean).sqrMagnitude));
                    }
                    var spreadRot = Spread(true);
                    var spreadFlat = Spread(false);
                    var rotated = spreadRot <= spreadFlat;
                    var spread = Mathf.Min(spreadRot, spreadFlat);
                    var nt = new Vector3[n];
                    var nq = new Quaternion[n];
                    var maxShift = 0f;
                    // The hero's own feet differ from the authored goals (gaits: the library's feet are carried over by
                    // the foot IK, not by the hero's FK): keep each goal where it was in the character's space, i.e. only
                    // undo the body rotation the correction added (goals are stored in the body frame).
                    var keepPlacement = spread > 0.03f;
                    for (var i = 0; i < n; i++)
                    {
                        var t = times[i];
                        Quaternion q;
                        if (keepPlacement)
                        {
                            var turn = Quaternion.Inverse(Q(rqN, t)) * Q(rqO, t);
                            nt[i] = turn * V(gt, t);
                            maxShift = Mathf.Max(maxShift, (nt[i] - V(gt, t)).magnitude * hs);
                            q = Quaternion.Normalize(turn * Q(gq, t));
                        }
                        else
                        {
                            var lo = Local(po[i], V(rtO, t), Q(rqO, t), rotated);
                            var ln = Local(pn[i], V(rtN, t), Q(rqN, t), rotated);
                            nt[i] = V(gt, t) + (ln - lo);
                            maxShift = Mathf.Max(maxShift, (ln - lo).magnitude * hs);
                            var ro = rotated ? Quaternion.Inverse(Q(rqO, t)) * qo[i] : qo[i];
                            var rn = rotated ? Quaternion.Inverse(Q(rqN, t)) * qn[i] : qn[i];
                            q = Quaternion.Normalize(rn * Quaternion.Inverse(ro) * Q(gq, t));
                        }
                        if (i > 0 && Quaternion.Dot(q, nq[i - 1]) < 0) q = new Quaternion(-q.x, -q.y, -q.z, -q.w);
                        nq[i] = q;
                    }
                    var axes = new[] { "x", "y", "z", "w" };
                    for (var a = 0; a < 3; a++)
                        AnimationUtility.SetEditorCurve(dst, Bind($"{goal}T.{axes[a]}"), Smooth(times, nt.Select(v => v[a]).ToArray()));
                    for (var a = 0; a < 4; a++)
                        AnimationUtility.SetEditorCurve(dst, Bind($"{goal}Q.{axes[a]}"), Smooth(times, nq.Select(v => v[a]).ToArray()));
                    report.Add(keepPlacement
                        ? $"{goal}: authored placement kept through the body pitch (moved up to {maxShift * 100f:0.0} cm in the body frame; hero feet differ from the goals by {spread * 100f:0.0} cm)"
                        : $"{goal}: moved with the corrected feet, up to {maxShift * 100f:0.0} cm ({(rotated ? "body frame" : "body offset")}, residual spread {spread * 100f:0.0} cm)");
                }
                return string.Join("; ", report);
            }
            finally { Object.DestroyImmediate(so); Object.DestroyImmediate(sn); }
        }

        /// <summary>Curve through the samples with finite-difference tangents.</summary>
        static AnimationCurve Smooth(float[] t, float[] v)
        {
            var keys = new Keyframe[t.Length];
            for (var i = 0; i < t.Length; i++)
            {
                var a = Mathf.Max(0, i - 1);
                var b = Mathf.Min(t.Length - 1, i + 1);
                var slope = b > a ? (v[b] - v[a]) / Mathf.Max(1e-5f, t[b] - t[a]) : 0f;
                keys[i] = new Keyframe(t[i], v[i], slope, slope);
            }
            return new AnimationCurve(keys);
        }

        static string TextHash(string text)
        {
            using var sha = System.Security.Cryptography.SHA1.Create();
            return BitConverter.ToString(sha.ComputeHash(System.Text.Encoding.UTF8.GetBytes(text))).Replace("-", "").ToLowerInvariant();
        }

        /// <summary>
        /// The library's avatar T-pose, the same construction as the heroes' (CharacterBuilder.TPoseSkeleton): the file's
        /// default pose (A_TPose) with the upper arm, forearm and hand aimed straight out to the side and the thigh and
        /// shin straight down; trunk, neck, head, clavicles and fingers keep the rig's rest.
        /// </summary>
        static SkeletonBone[] UalSkeleton(GameObject asset, List<HumanBone> map, out string aimLog)
        {
            var inst = Object.Instantiate(asset);
            try
            {
                var src = asset.GetComponentsInChildren<Transform>(true);
                var dst = inst.GetComponentsInChildren<Transform>(true);
                var byName = new Dictionary<string, Transform>();
                for (var i = 0; i < dst.Length && i < src.Length; i++) byName[src[i].name] = dst[i];
                Transform H(string human)
                {
                    var hb = map.FirstOrDefault(b => b.humanName == human);
                    return hb.boneName != null && byName.TryGetValue(hb.boneName, out var t) ? t : null;
                }
                var maxTurn = 0f;
                void Aim(Transform bone, Transform child, Vector3 target)
                {
                    if (bone == null || child == null) return;
                    var d = child.position - bone.position;
                    if (d.sqrMagnitude < 1e-10f) return;
                    var q = Quaternion.FromToRotation(d, target);
                    maxTurn = Mathf.Max(maxTurn, Quaternion.Angle(Quaternion.identity, q));
                    bone.rotation = q * bone.rotation;
                }
                var hips = H("Hips");
                foreach (var side in new[] { "Left", "Right" })
                {
                    var upper = H(side + "UpperArm");
                    if (upper != null && hips != null)
                    {
                        var outward = new Vector3(Mathf.Sign(upper.position.x - hips.position.x), 0, 0);
                        Aim(upper, H(side + "LowerArm"), outward);
                        Aim(H(side + "LowerArm"), H(side + "Hand"), outward);
                        Aim(H(side + "Hand"), H($"{side} Middle Proximal"), outward);
                    }
                    Aim(H(side + "UpperLeg"), H(side + "LowerLeg"), Vector3.down);
                    Aim(H(side + "LowerLeg"), H(side + "Foot"), Vector3.down);
                }
                aimLog = $"limbs aimed to the T-pose, largest turn {maxTurn:0.0} deg";
                var skeleton = new SkeletonBone[src.Length];
                for (var i = 0; i < src.Length; i++)
                    skeleton[i] = new SkeletonBone { name = src[i].name, position = dst[i].localPosition, rotation = dst[i].localRotation, scale = dst[i].localScale };
                return skeleton;
            }
            finally { Object.DestroyImmediate(inst); }
        }

        /// <summary>Copy, import and analyse the UAL clips; returns game clip → analysis (one object per style inside).</summary>
        static Dictionary<string, JObject> ImportUal(JObject meta, JArray log)
        {
            var result = new Dictionary<string, JObject>();
            SyncUal(log);
            AssetDatabase.Refresh();
            var libraries = new HashSet<string>();
            foreach (var (library, _) in UalLibraries)
            {
                if (!File.Exists(UalFbx(library))) continue;
                try { ConfigureUal(library, meta, log); libraries.Add(library); }
                catch (Exception e) { log.Add($"UAL {library} failed: {e.Message}"); Debug.LogError($"[ual] {library}: {e}"); }
            }
            var probes = Styles.ToDictionary(st => st, ClipProbe.ForStyle);
            try
            {
            foreach (var (name, uc) in UalMap.OrderBy(kv => kv.Key))
            {
                if (!libraries.Contains(uc.Library)) continue;
                if (meta["male"]?[name] == null) { log.Add($"UAL map: {name} is not a game clip"); continue; }
                try { result[name] = AnalyseUal(name, uc, meta, log, probes); }
                catch (Exception e)
                {
                    log.Add($"UAL {name} failed: {e.Message}");
                    Debug.LogError($"[ual] {name}: {e}");
                    foreach (var style in Styles) AssetDatabase.DeleteAsset(UalGenerated(style, name));
                }
            }
            }
            finally { foreach (var p in probes.Values) p.Dispose(); }
            // Generated clips no longer mapped (or whose library is gone) go away: the slot falls back to CMU.
            if (Directory.Exists(UalGeneratedRoot))
                foreach (var anim in Directory.GetFiles(UalGeneratedRoot, "*.anim", SearchOption.AllDirectories).Select(p => p.Replace('\\', '/')))
                    if (!result.ContainsKey(Path.GetFileNameWithoutExtension(anim)))
                    {
                        AssetDatabase.DeleteAsset(anim);
                        log.Add($"removed stale {anim}");
                    }
            return result;
        }

        /// <summary>One UAL clip, per style: timing plan, gait phase, posture bands on the style's hero, generated clip.</summary>
        static JObject AnalyseUal(string name, UalClip uc, JObject meta, JArray log, Dictionary<string, ClipProbe> probes)
        {
            var fbx = UalFbx(uc.Library);
            var src = AssetDatabase.LoadAllAssetsAtPath(fbx).OfType<AnimationClip>().FirstOrDefault(c => c.name == name)
                      ?? throw new Exception($"clip {name} ({uc.Take}) did not import from {fbx}");
            if (!src.humanMotion) throw new Exception($"{name} is not a humanoid clip");
            var loop = (bool)meta["male"][name]["loop"];
            var category = loop ? "loop" : StrikeClips.Contains(name) ? "strike" : FitClips.Contains(name) ? "fit" : TrimClips.Contains(name) ? "trim" : "natural";
            var a = new JObject
            {
                ["source"] = "ual", ["file"] = fbx, ["take"] = uc.Take, ["sourceLength"] = Math.Round(src.length, 4), ["loop"] = loop,
                ["category"] = category, ["sha1"] = Hash(fbx),
            };
            var raw = Neutral(src);
            try
            {
                foreach (var style in Styles)
                {
                    var key = style.ToLowerInvariant();
                    var info = (JObject)(meta[key]?[name] ?? meta["male"][name]);
                    var probe = probes[style];
                    if (!probe.Valid) throw new Exception($"no {style} hero rig to analyse on");
                    var track = probe.Sample(raw);
                    var travel = ClipProbe.RootTravel(raw, probe.HumanScale);
                    var inPlace = travel < 0.15f || loop && name is not ("walk" or "run" or "sprint");
                    var s = new JObject { ["rootTravel"] = Math.Round(travel, 3), ["inPlace"] = inPlace };
                    var settings = FinalSettings(name, loop, inPlace, src.length);
                    // UAL's root faces off the body in the source files: orient the clip by the body (Unity's "Body
                    // Orientation"), so the heroes face where they move and stand square to their forward.
                    settings.keepOriginalOrientation = false;
                    var (ss, ts, evs, length) = Plan(category, src, track, info, s);
                    var clip = BuildRetimed(src, name, ss, ts, settings, evs);
                    if (MocapPosture.Specs.TryGetValue(name, out var spec))
                    {
                        var before = Object.Instantiate(clip);
                        try
                        {
                            MocapPosture.ScaleTwist(clip, spec.TwistGain);
                            if (spec.TwistGain < 1f) s["twistGain"] = spec.TwistGain;
                            var offset = MocapPosture.Solve(probe, clip, spec, out var report);
                            MocapPosture.Apply(clip, offset);
                            s["posture"] = report;
                            s["offsets"] = offset.ToString();
                            // The foot IK goals (used by the gaits' and idles' foot IK) follow the corrected pose.
                            s["footGoals"] = SyncFootGoals(before, clip, probe);
                        }
                        finally { Object.DestroyImmediate(before); }
                    }
                    var check = Neutral(clip);
                    try
                    {
                        var tr = probe.Sample(check, name is "walk" or "run" or "sprint" ? 120f : ClipProbe.Fps);
                        s["measured"] = ClipProbe.Measure(tr).ToString();
                        if (name is "walk" or "run" or "sprint")
                        {
                            // Ground speed the feet are planted for: the authored contact speed of the take on the UAL
                            // mannequin (UalGaitSpeed, measured in Blender), scaled by the hero's human scale (the foot IK
                            // goals carry the authored feet over, scaled the same way). Contact-point speed, no probe
                            // bias: Gaits uses it as authored.
                            using var lib = new ClipProbe(AssetDatabase.LoadAssetAtPath<GameObject>(fbx));
                            var onHero = ClipProbe.ContactSpeed(tr, out _);
                            var ratio = lib.Valid ? probe.HumanScale / Mathf.Max(1e-4f, lib.HumanScale) : 1f;
                            var authored = UalGaitSpeed.TryGetValue(uc.Take, out var sp) ? sp : onHero;
                            s["speed"] = Math.Round(authored * ratio, 3);
                            s["speedAuthoredOnMannequin"] = authored;
                            s["humanScaleRatio"] = Math.Round(ratio, 3);
                            s["speedOnHeroFk"] = Math.Round(onHero, 3);
                            s["contactSpeed"] = true;
                            // Left plant at the same normalised time as the CMU gaits, so mixed sources blend in phase.
                            var reference = plantRef.TryGetValue(style, out var r) ? r : 0.92f;
                            var phase = ClipProbe.LeftPlantPhase(tr);
                            var cs = AnimationUtility.GetAnimationClipSettings(clip);
                            cs.cycleOffset = Mathf.Repeat(phase - reference, 1f);
                            AnimationUtility.SetAnimationClipSettings(clip, cs);
                            s["plantPhase"] = Math.Round(phase, 3);
                            s["cycleOffset"] = Math.Round(cs.cycleOffset, 3);
                        }
                    }
                    finally { Object.DestroyImmediate(check); }
                    var gen = UalGenerated(style, name);
                    SaveClip(gen, clip, name);
                    s["generated"] = gen;
                    a[key] = s;
                    log.Add($"UAL {name} ({uc.Take}) {style}: {category}, {src.length:0.00}s -> {length:0.00}s{(s["posture"] != null ? $", posture {s["posture"]}" : "")} ({gen})");
                }
            }
            finally { Object.DestroyImmediate(raw); }
            return a;
        }
    }
}
