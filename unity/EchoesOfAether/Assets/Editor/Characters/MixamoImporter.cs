using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;
using Object = UnityEngine.Object;

namespace EOA.EditorTools
{
    /// <summary>
    /// Mixamo animation import (runs inside <see cref="CharacterBuilder.BuildAll"/> before the controllers are built,
    /// or alone: Unity -batchmode -quit -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.MixamoImporter.Import).
    ///
    /// Drop folder: &lt;repo&gt;/incoming/mixamo/&lt;clip&gt;.fbx (shared by both styles), with optional female/ and male/
    /// subfolders that override one style ("FBX for Unity", 30 fps, Without Skin, In Place for locomotion), and an optional
    /// T-pose reference character ybot.fbx whose avatar every clip then copies. Override the
    /// folder with -mixamoIncoming &lt;dir&gt; or EOA_MIXAMO_INCOMING. Every file whose name is a game clip name
    /// (idle.fbx, k_light1.fbx, ...) is copied to Assets/Art/Animations/Mixamo/ (the copy is what the project uses;
    /// delete it there to go back to the CMU clip), imported as Humanoid with an avatar built from the Mixamo bone names
    /// (<see cref="CharacterBuilder.ConfigureAvatar"/>), analysed on the hero rigs with <see cref="ClipProbe"/>, and
    /// registered under the game's clip name. <see cref="CharacterBuilder.LoadClips"/> then prefers it over the CMU clip.
    ///
    /// Gameplay timing stays the combat-tuned contract in clips_meta.json: attack and ability clips are re-timed
    /// (piecewise linear) so the detected strike (peak hand / foot speed) lands on the clip's hit time and the clip ends
    /// near its tuned duration; other one-shots are fitted to their duration with dead lead-in frames trimmed. Those
    /// re-timed clips are written to Mixamo/Generated/*.anim; loops and cinematic one-shots are used straight from the
    /// FBX. Locomotion blend thresholds / time scales come from each clip's measured stride speed. Everything is
    /// recorded in Assets/Art/Animations/clip_sources.json. An empty folder leaves every clip on CMU.
    /// </summary>
    public static partial class MixamoImporter
    {
        public const string AssetRoot = "Assets/Art/Animations/Mixamo";
        const string GeneratedRoot = AssetRoot + "/Generated";
        public const string ReportPath = "Assets/Art/Animations/clip_sources.json";
        const string MetaPath = "Assets/Art/Animations/clips_meta.json";
        static readonly string[] Styles = { "Male", "Female" };

        /// <summary>Attack and ability clips: re-timed so the detected strike lands on the gameplay hit time.</summary>
        static readonly HashSet<string> StrikeClips = new()
            { "k_light1", "k_light2", "k_light3", "k_heavy", "l_quick1", "l_quick2", "l_heavy", "k_pulse", "k_ult", "l_echo", "l_ult" };

        /// <summary>Gameplay one-shots fitted to their tuned duration (events scaled), lead-in trimmed.</summary>
        static readonly HashSet<string> FitClips = new()
            { "dash", "phase_step", "hit", "stagger", "land", "jump", "fire_r", "fire_l", "interact", "pickup" };

        /// <summary>One-shots kept at natural speed with the dead lead-in trimmed.</summary>
        static readonly HashSet<string> TrimClips = new() { "death" };

        /// <summary>Speeds the hero actually moves at (Hero.UpdatePlayer): walk, run, sprint.</summary>
        public static readonly (string clip, float game)[] GameGaits = { ("walk", 2.2f), ("run", 5.2f), ("sprint", 7.6f) };

        // Speed-factor limits for re-timing (source seconds per game second).
        const float MinRate = 0.5f, MaxWindupRate = 2.5f, MaxRate = 2.0f, MaxLengthOverMeta = 1.25f;

        public static string IncomingDir
        {
            get
            {
                var args = Environment.GetCommandLineArgs();
                var i = Array.IndexOf(args, "-mixamoIncoming");
                if (i >= 0 && i + 1 < args.Length) return Path.GetFullPath(args[i + 1]);
                var env = Environment.GetEnvironmentVariable("EOA_MIXAMO_INCOMING");
                if (!string.IsNullOrEmpty(env)) return Path.GetFullPath(env);
                return Path.GetFullPath(Path.Combine(Application.dataPath, "..", "..", "..", "incoming", "mixamo"));
            }
        }

        static JObject Meta() => JObject.Parse(File.ReadAllText(MetaPath));

        static string ClipName(string file) => Path.GetFileNameWithoutExtension(file).Trim().ToLowerInvariant().Replace(' ', '_').Replace('-', '_');

        /// <summary>
        /// Optional T-pose reference character (the Y Bot downloaded once "With Skin", T-pose): incoming/mixamo/ybot.fbx
        /// (also tpose.fbx / reference.fbx). Animation-only FBX files have no bind pose, so Unity builds their avatar from
        /// the file's default pose, which for some exports is the clip's first frame (its lean then counts as "neutral").
        /// With a reference, every clip copies the reference's avatar (the standard Mixamo setup).
        /// </summary>
        static readonly string[] ReferenceNames = { "ybot", "y_bot", "tpose", "t_pose", "reference" };
        const string ReferencePath = AssetRoot + "/Reference/reference.fbx";
        static Avatar referenceAvatar;

        // ------------------------------------------------------------------ sources on disk

        /// <summary>The Mixamo FBX (project copy) a style uses for a clip: style override folder, else the shared one.</summary>
        public static string FbxFor(string style, string clip)
        {
            foreach (var p in new[] { $"{AssetRoot}/{style.ToLowerInvariant()}/{clip}.fbx", $"{AssetRoot}/{clip}.fbx" })
                if (File.Exists(p)) return p;
            return null;
        }

        static string GeneratedFor(string fbx)
        {
            var rel = fbx.Substring(AssetRoot.Length + 1); // "k_light1.fbx" or "female/k_light1.fbx"
            return $"{GeneratedRoot}/{Path.ChangeExtension(rel, ".anim")}";
        }

        /// <summary>Imported clips for a style (game clip name → clip): UAL, with Mixamo on top. Empty when neither has
        /// anything; <see cref="CharacterBuilder.LoadClips"/> fills the rest from CMU.</summary>
        public static Dictionary<string, AnimationClip> ClipsFor(string style)
        {
            var result = UalClipsFor(style);
            foreach (var kv in MixamoClipsFor(style)) result[kv.Key] = kv.Value;
            return result;
        }

        /// <summary>Mixamo clips registered for a style (game clip name → clip). Empty when nothing was imported.</summary>
        public static Dictionary<string, AnimationClip> MixamoClipsFor(string style)
        {
            var result = new Dictionary<string, AnimationClip>();
            if (!Directory.Exists(AssetRoot)) return result;
            // Files the last import could not use stay out (the clip falls back to CMU).
            var failed = new HashSet<string>();
            if (File.Exists(ReportPath))
                foreach (var f in JObject.Parse(File.ReadAllText(ReportPath))["failed"] as JArray ?? new JArray()) failed.Add((string)f);
            var names = Directory.GetFiles(AssetRoot, "*.fbx", SearchOption.AllDirectories).Select(ClipName).Distinct();
            foreach (var name in names)
            {
                var fbx = FbxFor(style, name);
                if (fbx == null || failed.Contains(fbx)) continue;
                var gen = GeneratedFor(fbx);
                var clip = File.Exists(gen) ? AssetDatabase.LoadAssetAtPath<AnimationClip>(gen) : null;
                clip ??= AssetDatabase.LoadAllAssetsAtPath(fbx).OfType<AnimationClip>().FirstOrDefault(c => c.name == name);
                if (clip != null) result[name] = clip;
            }
            return result;
        }

        public static bool IsMixamo(AnimationClip clip) => clip != null && AssetDatabase.GetAssetPath(clip).StartsWith(AssetRoot + "/", StringComparison.Ordinal);

        // ------------------------------------------------------------------ import

        [MenuItem("EOA/Import Mixamo Animations")]
        public static void Import()
        {
            var meta = Meta();
            var known = new HashSet<string>(((JObject)meta["male"]).Properties().Select(p => p.Name));
            var report = new JObject
            {
                ["generated"] = DateTime.UtcNow.ToString("yyyy-MM-dd HH:mm:ss 'UTC'"),
                ["incoming"] = IncomingDir,
            };
            var log = new JArray();
            report["log"] = log;

            // 1) Copy new or changed files from the drop folder.
            Sync(known, log);
            AssetDatabase.Refresh();

            // CMU gaits: stride speed on the hero rigs (validated on the authoring rig) and the left-foot plant phase that
            // Mixamo loops are aligned to.
            var cmuGaits = MeasureCmuGaits(meta);
            report["cmuGaits"] = cmuGaits;
            plantRef = Styles.ToDictionary(st => st, st => (float?)cmuGaits[st.ToLowerInvariant()]?["walk"]?["plantPhase"] ?? 0.92f);

            // 2) Import settings for every project copy.
            var fbxFiles = Directory.Exists(AssetRoot)
                ? Directory.GetFiles(AssetRoot, "*.fbx", SearchOption.AllDirectories).Select(p => p.Replace('\\', '/'))
                    .Where(p => !p.StartsWith(GeneratedRoot + "/", StringComparison.Ordinal) && !p.StartsWith(AssetRoot + "/Reference/", StringComparison.Ordinal))
                    .OrderBy(p => p).ToArray()
                : Array.Empty<string>();
            referenceAvatar = null;
            if (File.Exists(ReferencePath))
            {
                var rmi = (ModelImporter)AssetImporter.GetAtPath(ReferencePath);
                rmi.animationType = ModelImporterAnimationType.Human;
                rmi.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
                CharacterBuilder.ConfigureAvatar(rmi, ReferencePath);
                rmi.importAnimation = false;
                rmi.materialImportMode = ModelImporterMaterialImportMode.None;
                rmi.SaveAndReimport();
                referenceAvatar = AssetDatabase.LoadAllAssetsAtPath(ReferencePath).OfType<Avatar>().FirstOrDefault(a => a.isHuman && a.isValid);
                log.Add(referenceAvatar != null ? $"reference avatar {ReferencePath}: every clip copies it" : $"reference {ReferencePath} gave no valid humanoid avatar; clips use their own");
                report["referenceAvatar"] = referenceAvatar != null ? ReferencePath : null;
            }
            var analyses = new Dictionary<string, JObject>();
            var failedFiles = new JArray();
            report["failed"] = failedFiles;
            foreach (var fbx in fbxFiles)
            {
                var name = ClipName(fbx);
                if (!known.Contains(name)) { log.Add($"ignored {fbx}: '{name}' is not a game clip name"); Debug.LogWarning($"[mixamo] ignored {fbx}: not a game clip name"); continue; }
                try { analyses[fbx] = ImportOne(fbx, name, meta, log); }
                catch (Exception e) { log.Add($"failed {fbx}: {e.Message}"); failedFiles.Add(fbx); Debug.LogError($"[mixamo] {fbx}: {e}"); }
            }

            // 3) Generated clips no longer backed by an FBX go away (the clip falls back to CMU).
            if (Directory.Exists(GeneratedRoot))
                foreach (var anim in Directory.GetFiles(GeneratedRoot, "*.anim", SearchOption.AllDirectories).Select(p => p.Replace('\\', '/')))
                {
                    var rel = anim.Substring(GeneratedRoot.Length + 1);
                    var fbx = $"{AssetRoot}/{Path.ChangeExtension(rel, ".fbx")}";
                    if (analyses.ContainsKey(fbx) && analyses[fbx]?["generated"] != null) continue;
                    AssetDatabase.DeleteAsset(anim);
                    log.Add($"removed stale {anim}");
                }

            // 3b) UAL library clips (the source for every mapped slot without a Mixamo file).
            var ual = ImportUal(meta, log);
            report["ualMap"] = new JObject(UalMap.OrderBy(kv => kv.Key).Select(kv => new JProperty(kv.Key, $"{kv.Value.Library}/{kv.Value.Take}")));

            // 4) Per-style source table and locomotion tuning: Mixamo > UAL > CMU.
            var styles = new JObject();
            foreach (var style in Styles)
            {
                var table = new JObject();
                var key = style.ToLowerInvariant();
                foreach (var prop in ((JObject)meta[key]).Properties().OrderBy(p => p.Name))
                {
                    var fbx = FbxFor(style, prop.Name);
                    if (fbx != null && analyses.TryGetValue(fbx, out var a) && a != null)
                    {
                        var entry = (JObject)a.DeepClone();
                        entry["source"] = "mixamo";
                        entry["file"] = fbx;
                        if (a["speed"] is JObject sp && sp[key] != null) entry["speed"] = sp[key];
                        else entry.Remove("speed");
                        table[prop.Name] = entry;
                    }
                    else if (ual.TryGetValue(prop.Name, out var u) && u[key] is JObject us && us["generated"] != null)
                    {
                        var entry = new JObject
                        {
                            ["source"] = "ual", ["file"] = (string)us["generated"], ["library"] = u["file"], ["take"] = u["take"],
                            ["category"] = u["category"], ["loop"] = u["loop"], ["sourceLength"] = u["sourceLength"], ["sha1"] = u["sha1"],
                        };
                        foreach (var kv in us) if (kv.Key != "generated") entry[kv.Key] = kv.Value;
                        table[prop.Name] = entry;
                    }
                    else
                    {
                        var entry = new JObject
                        {
                            ["source"] = "cmu", ["file"] = $"Assets/Art/Animations/Anim_{style}.fbx",
                            ["length"] = prop.Value["duration"], ["loop"] = prop.Value["loop"],
                        };
                        if (cmuGaits[key]?[prop.Name] is JObject g) foreach (var kv in g) entry[kv.Key] = kv.Value;
                        table[prop.Name] = entry;
                    }
                }
                styles[key] = table;
            }
            report["styles"] = styles;
            int Count(string src) => styles.Properties().Sum(s => ((JObject)s.Value).Properties().Count(c => (string)c.Value["source"] == src));
            report["summary"] = $"{Count("mixamo")} Mixamo, {Count("ual")} UAL, {Count("cmu")} CMU of {styles.Properties().Sum(s => ((JObject)s.Value).Count)} clip slots";
            WriteReport(report);
            AssetDatabase.SaveAssets();
            Debug.Log($"[mixamo] {report["summary"]} (drop folders {IncomingDir}, {UalIncomingDir}) -> {ReportPath}");
        }

        static void WriteReport(JObject report)
        {
            // Locomotion lines are filled in by CharacterBuilder when it builds the trees; keep the previous ones until then.
            var old = File.Exists(ReportPath) ? JObject.Parse(File.ReadAllText(ReportPath)) : null;
            if (old?["locomotion"] != null && report["locomotion"] == null) report["locomotion"] = old["locomotion"];
            File.WriteAllText(ReportPath, report.ToString(Newtonsoft.Json.Formatting.Indented));
            AssetDatabase.ImportAsset(ReportPath);
        }

        /// <summary>Record the locomotion tuning a controller was built with (called by CharacterBuilder).</summary>
        public static void RecordLocomotion(string style, IEnumerable<Gait> gaits)
        {
            if (!File.Exists(ReportPath)) return;
            var report = JObject.Parse(File.ReadAllText(ReportPath));
            var loco = report["locomotion"] as JObject ?? new JObject();
            loco[style.ToLowerInvariant()] = new JArray(gaits.Select(g => new JObject
            {
                ["clip"] = g.Clip, ["source"] = g.Source, ["authoredSpeed"] = Math.Round(g.Authored, 3),
                ["threshold"] = Math.Round(g.Threshold, 3), ["timeScale"] = Math.Round(g.TimeScale, 3),
            }));
            report["locomotion"] = loco;
            File.WriteAllText(ReportPath, report.ToString(Newtonsoft.Json.Formatting.Indented));
        }

        static void Sync(HashSet<string> known, JArray log)
        {
            var src = IncomingDir;
            if (!Directory.Exists(src)) { log.Add($"drop folder {src} does not exist"); return; }
            foreach (var file in Directory.GetFiles(src, "*.*", SearchOption.AllDirectories))
            {
                if (!file.EndsWith(".fbx", StringComparison.OrdinalIgnoreCase)) continue;
                var rel = Path.GetRelativePath(src, file).Replace('\\', '/');
                var dir = Path.GetDirectoryName(rel)?.Replace('\\', '/').ToLowerInvariant() ?? "";
                if (dir != "" && dir != "female" && dir != "male") { log.Add($"ignored {rel}: only female/ and male/ subfolders are read"); continue; }
                var name = ClipName(file);
                if (dir == "" && Array.IndexOf(ReferenceNames, name) >= 0)
                {
                    if (!File.Exists(ReferencePath) || Hash(ReferencePath) != Hash(file))
                    {
                        Directory.CreateDirectory(Path.GetDirectoryName(ReferencePath)!);
                        File.Copy(file, ReferencePath, true);
                        log.Add($"copied {rel} -> {ReferencePath} (T-pose reference)");
                    }
                    continue;
                }
                if (!known.Contains(name)) { log.Add($"ignored {rel}: '{name}' is not a game clip name"); Debug.LogWarning($"[mixamo] ignored {rel}: not a game clip name"); continue; }
                var dst = dir == "" ? $"{AssetRoot}/{name}.fbx" : $"{AssetRoot}/{dir}/{name}.fbx";
                if (File.Exists(dst) && Hash(dst) == Hash(file)) continue;
                Directory.CreateDirectory(Path.GetDirectoryName(dst)!);
                File.Copy(file, dst, true);
                log.Add($"copied {rel} -> {dst}");
                Debug.Log($"[mixamo] copied {rel} -> {dst}");
            }
        }

        static string Hash(string path)
        {
            using var sha = SHA1.Create();
            using var fs = File.OpenRead(path);
            return BitConverter.ToString(sha.ComputeHash(fs)).Replace("-", "").ToLowerInvariant();
        }

        // ------------------------------------------------------------------ one file

        static JObject ImportOne(string fbx, string name, JObject meta, JArray log)
        {
            var info = (JObject)meta["male"][name];
            var loop = (bool)info["loop"];
            var styleOverride = fbx.Contains("/female/") ? "Female" : fbx.Contains("/male/") ? "Male" : null;
            var mi = AssetImporter.GetAtPath(fbx) as ModelImporter ?? throw new Exception("not a model");
            mi.animationType = ModelImporterAnimationType.Human;
            var restWarning = (string)null;
            if (referenceAvatar != null)
            {
                mi.avatarSetup = ModelImporterAvatarSetup.CopyFromOther;
                mi.sourceAvatar = referenceAvatar;
            }
            else
            {
                mi.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
                CharacterBuilder.ConfigureAvatar(mi, fbx);
                restWarning = DefaultPoseWarning(fbx);
                if (restWarning != null) { log.Add($"{fbx}: {restWarning}"); Debug.LogWarning($"[mixamo] {fbx}: {restWarning}"); }
            }
            mi.importAnimation = true;
            mi.materialImportMode = ModelImporterMaterialImportMode.None;
            mi.importCameras = false;
            mi.importLights = false;
            mi.importVisibility = false;
            mi.importBlendShapes = false;
            mi.resampleCurves = true;
            mi.animationCompression = ModelImporterAnimationCompression.Off; // exact data for analysis and re-timing
            var take = mi.importedTakeInfos.OrderByDescending(t => t.name.Contains("mixamo") ? 1 : 0).ThenByDescending(t => t.stopTime - t.startTime).FirstOrDefault();
            if (string.IsNullOrEmpty(take.name)) throw new Exception("no animation take");
            // Raw full take; loop, root bake and phase are runtime settings that leave the curves untouched.
            mi.clipAnimations = new[] { RawClip(name, take, loop) };
            mi.SaveAndReimport();
            var src = AssetDatabase.LoadAllAssetsAtPath(fbx).OfType<AnimationClip>().FirstOrDefault(c => c.name == name)
                      ?? throw new Exception("clip did not import (is it a Mixamo / humanoid skeleton?)");
            var srcLen = src.length;
            // With a reference the clip uses the reference's avatar (no avatar sub-asset of its own).
            var avatar = referenceAvatar != null ? referenceAvatar : AssetDatabase.LoadAllAssetsAtPath(fbx).OfType<Avatar>().FirstOrDefault();
            if (avatar == null || !avatar.isHuman || !avatar.isValid) throw new Exception("humanoid avatar is invalid (bone names not Mixamo?)");
            if (!src.humanMotion) throw new Exception("clip is not humanoid (skeleton does not match the reference?)");

            var a = new JObject
            {
                ["avatar"] = referenceAvatar != null ? "reference" : "own",
                ["restWarning"] = restWarning,
                ["take"] = take.name, ["sourceLength"] = Math.Round(src.length, 4), ["loop"] = loop,
                ["sha1"] = Hash(fbx), ["category"] = loop ? "loop" : StrikeClips.Contains(name) ? "strike" : FitClips.Contains(name) ? "fit" : TrimClips.Contains(name) ? "trim" : "natural",
            };

            // Analysis on the rig of the style that owns the file (shared files: Kael's rig; timing is rig independent).
            var raw = Neutral(src);
            try
            {
                var travel = 0f;
                var speeds = new JObject();
                ClipProbe.Track track = null;
                foreach (var style in styleOverride != null ? new[] { styleOverride } : Styles)
                {
                    using var probe = ClipProbe.ForStyle(style);
                    if (!probe.Valid) continue;
                    var tr = probe.Sample(raw);
                    if (track == null)
                    {
                        track = tr;
                        travel = ClipProbe.RootTravel(raw, probe.HumanScale);
                        a["posture"] = ClipProbe.Measure(tr).ToString();
                    }
                    if (name is "walk" or "run" or "sprint") speeds[style.ToLowerInvariant()] = Math.Round(ClipProbe.StrideSpeed(tr), 3);
                }
                if (track == null) throw new Exception("no hero rig to analyse on");
                var inPlace = travel < 0.15f || loop && name is not ("walk" or "run" or "sprint");
                a["rootTravel"] = Math.Round(travel, 3);
                a["inPlace"] = inPlace;
                if (speeds.Count > 0) a["speed"] = speeds;

                var settings = FinalSettings(name, loop, inPlace, src.length);
                if (name is "walk" or "run" or "sprint")
                {
                    // Left plant at the same normalised time as the CMU gaits, so mixed sources blend in phase.
                    var reference = plantRef.TryGetValue(styleOverride ?? "Male", out var r) ? r : 0.92f;
                    settings.cycleOffset = Mathf.Repeat(ClipProbe.LeftPlantPhase(track) - reference, 1f);
                    a["plantPhase"] = Math.Round(ClipProbe.LeftPlantPhase(track), 3);
                    a["cycleOffset"] = Math.Round(settings.cycleOffset, 3);
                }

                if (loop || a["category"].ToString() == "natural")
                {
                    // Used straight from the FBX: just the final clip settings.
                    var clips = mi.clipAnimations;
                    var c = clips[0];
                    c.loopTime = settings.loopTime; c.loopPose = settings.loopBlend;
                    c.lockRootRotation = settings.loopBlendOrientation; c.keepOriginalOrientation = settings.keepOriginalOrientation;
                    c.lockRootHeightY = settings.loopBlendPositionY; c.keepOriginalPositionY = settings.keepOriginalPositionY; c.heightFromFeet = settings.heightFromFeet;
                    c.lockRootPositionXZ = settings.loopBlendPositionXZ; c.keepOriginalPositionXZ = settings.keepOriginalPositionXZ;
                    c.cycleOffset = settings.cycleOffset;
                    c.events = Array.Empty<AnimationEvent>();
                    clips[0] = c;
                    mi.clipAnimations = clips;
                    mi.SaveAndReimport();
                    a["length"] = Math.Round(srcLen, 4);
                    log.Add($"{fbx}: {a["category"]} clip used from the FBX ({srcLen:0.00}s, in place {inPlace})");
                    return a;
                }

                // Re-timed one-shot → generated .anim.
                var category = a["category"].ToString();
                var (ss, ts, evs, length) = Plan(category, src, track, info, a);
                var gen = GeneratedFor(fbx);
                SaveClip(gen, BuildRetimed(src, name, ss, ts, settings, evs), name);
                a["generated"] = gen;
                log.Add($"{fbx}: {category}, lead-in {ss[0]:0.000}s trimmed, {src.length:0.00}s -> {length:0.00}s ({gen})");
                return a;
            }
            finally { Object.DestroyImmediate(raw); }
        }

        static Dictionary<string, float> plantRef = new();

        /// <summary>
        /// Stride speed and plant phase of the CMU gaits on each hero rig and on their authoring rig. CMU gaits play at
        /// their authored clips_meta speeds (the gameplay foot-slip capture confirmed those); the authoring-rig reading
        /// against the authored speed gives the stride probe's bias (about 0.91), used to calibrate Mixamo strides.
        /// </summary>
        static JObject MeasureCmuGaits(JObject meta)
        {
            var result = new JObject();
            foreach (var style in Styles)
            {
                var key = style.ToLowerInvariant();
                var st = new JObject();
                var clips = CharacterBuilder.LoadCmuClips(style);
                using var hero = ClipProbe.ForStyle(style);
                using var authoring = ClipProbe.ForAnimRig(style);
                foreach (var name in GameGaits.Select(g => g.clip).Append("crouch_walk"))
                {
                    if (!clips.TryGetValue(name, out var clip) || !hero.Valid) continue;
                    var raw = Neutral(clip);
                    try
                    {
                        var tr = hero.Sample(raw);
                        var onHero = ClipProbe.StrideSpeed(tr);
                        var onAuthoring = authoring.Valid ? ClipProbe.StrideSpeed(authoring.Sample(raw)) : 0f;
                        var authored = (float?)meta[key]?[name]?["speed"] ?? 0f;
                        // Reported only. The gameplay foot-slip capture settled it: playing the gaits at the measured
                        // strides tripled the walk slip (0.10 -> 0.33 m/s), so CMU gaits keep their authored speeds and
                        // the measurement's bias (authoring-rig reading / authored speed) calibrates Mixamo strides.
                        var valid = false;
                        st[name] = new JObject
                        {
                            ["speed"] = Math.Round(onHero, 3), ["speedOnAuthoringRig"] = Math.Round(onAuthoring, 3), ["metaSpeed"] = authored,
                            ["useMeasured"] = valid && onHero > 0.3f, ["plantPhase"] = Math.Round(ClipProbe.LeftPlantPhase(tr), 3),
                        };
                    }
                    finally { Object.DestroyImmediate(raw); }
                }
                result[key] = st;
            }
            return result;
        }

        /// <summary>Without a reference: warn when the file's default pose is not upright (trunk or neck tilted more than
        /// 8 degrees), i.e. the avatar would take a posed frame as neutral.</summary>
        static string DefaultPoseWarning(string fbx)
        {
            var model = AssetDatabase.LoadAssetAtPath<GameObject>(fbx);
            if (model == null) return null;
            Transform Find(string bone) => model.GetComponentsInChildren<Transform>(true).FirstOrDefault(t => t.name.EndsWith(bone, StringComparison.Ordinal) && (t.name.Length == bone.Length || t.name[t.name.Length - bone.Length - 1] == ':'));
            var hips = Find("Hips"); var neck = Find("Neck"); var head = Find("Head");
            if (hips == null || neck == null || head == null) return null;
            var trunk = Vector3.Angle(neck.position - hips.position, Vector3.up);
            var neckTilt = Vector3.Angle(head.position - neck.position, Vector3.up);
            return trunk > 8f || neckTilt > 25f
                ? $"default pose is not upright (trunk {trunk:0} deg, neck {neckTilt:0} deg): the avatar would treat that pose as neutral; add the T-pose character as incoming/mixamo/ybot.fbx"
                : null;
        }

        static ModelImporterClipAnimation RawClip(string name, TakeInfo take, bool loop) => new()
        {
            name = name, takeName = take.name,
            firstFrame = take.startTime * take.sampleRate, lastFrame = take.stopTime * take.sampleRate,
            loopTime = loop, loopPose = loop,
            lockRootRotation = true, keepOriginalOrientation = true,
            lockRootHeightY = true, keepOriginalPositionY = true, heightFromFeet = false,
            lockRootPositionXZ = true, keepOriginalPositionXZ = true,
        };

        /// <summary>Copy of a clip with neutral settings (everything baked, original root, no loop or phase offset).</summary>
        internal static AnimationClip Neutral(AnimationClip src)
        {
            var c = Object.Instantiate(src);
            c.hideFlags = HideFlags.HideAndDontSave;
            var s = AnimationUtility.GetAnimationClipSettings(c);
            s.loopTime = false; s.loopBlend = false; s.cycleOffset = 0; s.mirror = false;
            s.loopBlendOrientation = true; s.keepOriginalOrientation = true;
            s.loopBlendPositionY = true; s.keepOriginalPositionY = true; s.heightFromFeet = false;
            s.loopBlendPositionXZ = true; s.keepOriginalPositionXZ = true;
            AnimationUtility.SetAnimationClipSettings(c, s);
            return c;
        }

        /// <summary>
        /// Final clip settings. Root rotation and height are baked into the pose (the CharacterController owns the
        /// root); height is based on the feet so they stay grounded (jump / fall keep the authored height). In-place clips
        /// keep their small horizontal sway; travelling ones have it extracted as root motion, which the heroes discard
        /// (applyRootMotion off), so the body stays over the controller instead of drifting and snapping back.
        /// </summary>
        static AnimationClipSettings FinalSettings(string name, bool loop, bool inPlace, float length)
        {
            var airborne = name is "jump" or "fall";
            return new AnimationClipSettings
            {
                startTime = 0, stopTime = length,
                loopTime = loop, loopBlend = loop,
                loopBlendOrientation = true, keepOriginalOrientation = true,
                loopBlendPositionY = true, keepOriginalPositionY = airborne, heightFromFeet = !airborne,
                loopBlendPositionXZ = inPlace, keepOriginalPositionXZ = inPlace,
            };
        }

        /// <summary>Where the strike should land (clip seconds) from the tuned events: just before a heavy's impact, early in
        /// a light's active window, on an ability's single effect event.</summary>
        static float Anchor(JArray events, float dur)
        {
            float? T(string n)
            {
                var ev = events.FirstOrDefault(x => (string)x["name"] == n);
                return ev != null ? (float)ev["t"] : null;
            }
            if (T("impact") is { } imp && T("hit_start") != null) return imp - 0.02f;
            if (T("hit_start") is { } hs && T("hit_end") is { } he) return hs + (he - hs) * 0.3f;
            foreach (var n in new[] { "impact", "pulse", "echo", "fire", "use" })
                if (T(n) is { } t) return t;
            return dur * 0.35f;
        }

        // ------------------------------------------------------------------ re-timed clip

        /// <summary>
        /// Re-time plan of a clip by category: strike (the detected strike lands on the tuned hit time), fit (fitted to the
        /// tuned duration, lead-in trimmed), trim (lead-in trimmed), else as authored. Source knots ss (seconds) map to
        /// clip knots ts; events move with it; analysis fields go into <paramref name="a"/>.
        /// </summary>
        static (float[] ss, float[] ts, AnimationEvent[] evs, float length) Plan(string category, AnimationClip src, ClipProbe.Track track, JObject info, JObject a)
        {
            var dur = (float)info["duration"];
            var events = info["events"] as JArray ?? new JArray();
            var lead = ClipProbe.LeadIn(track);
            var end = src.length;
            float[] ss, ts;
            if (category == "strike")
            {
                var anchor = Anchor(events, dur);
                var strike = ClipProbe.FindStrike(track, lead);
                var peak = strike.Valid ? strike.Time : lead + (end - lead) * 0.35f;
                a["strike"] = new JObject { ["time"] = Math.Round(peak, 3), ["limb"] = strike.Limb, ["speed"] = Math.Round(strike.Speed, 2), ["detected"] = strike.Valid };
                a["anchor"] = Math.Round(anchor, 3);
                // Wind-up [lead, peak] → [0, anchor]; trim more lead-in if it would play faster than MaxWindupRate.
                var start = Mathf.Max(lead, peak - anchor * MaxWindupRate);
                var windRate = (peak - start) / Mathf.Max(0.01f, anchor);
                var anchorT = anchor;
                if (windRate < MinRate) { anchorT = (peak - start) / MinRate; windRate = MinRate; }
                // Recovery [peak, end] → [anchor, dur], within the rate limits; overly long tails are cut.
                var tailRate = Mathf.Clamp((end - peak) / Mathf.Max(0.01f, dur - anchorT), 0.6f, MaxRate);
                var maxLen = dur * MaxLengthOverMeta;
                var srcEnd = Mathf.Min(end, peak + (maxLen - anchorT) * tailRate);
                ss = new[] { start, peak, srcEnd };
                ts = new[] { 0f, anchorT, anchorT + (srcEnd - peak) / tailRate };
                a["windupRate"] = Math.Round(windRate, 3);
                a["recoveryRate"] = Math.Round(tailRate, 3);
            }
            else if (category == "fit")
            {
                var rate = Mathf.Clamp((end - lead) / dur, 0.6f, MaxRate);
                var srcEnd = Mathf.Min(end, lead + dur * MaxLengthOverMeta * rate);
                ss = new[] { lead, srcEnd };
                ts = new[] { 0f, (srcEnd - lead) / rate };
                a["rate"] = Math.Round(rate, 3);
            }
            else if (category == "trim")
            {
                ss = new[] { lead, end };
                ts = new[] { 0f, end - lead };
            }
            else
            {
                ss = new[] { 0f, end };
                ts = new[] { 0f, end };
            }
            a["trimmedLeadIn"] = Math.Round(ss[0], 3);
            a["warp"] = new JArray(ss.Zip(ts, (s, t) => new JArray(Math.Round(s, 4), Math.Round(t, 4))));
            var length = ts[ts.Length - 1];
            var evs = events.Select(e =>
            {
                var t = (float)e["t"];
                // Strike clips keep the tuned event seconds (the strike was moved onto them); others scale.
                var nt = category == "strike" ? t : t / dur * length;
                return new AnimationEvent { time = Mathf.Min(nt, length - 1f / 60f), functionName = "OnAnimEvent", stringParameter = (string)e["name"] };
            }).ToArray();
            a["events"] = new JArray(evs.Select(e => new JObject { ["name"] = e.stringParameter, ["t"] = Math.Round(e.time, 4) }));
            a["length"] = Math.Round(length, 4);
            a["metaDuration"] = dur;
            return (ss, ts, evs, length);
        }

        /// <summary>A re-timed copy of <paramref name="src"/> (see <see cref="Retime"/>) with the final settings and events.</summary>
        static AnimationClip BuildRetimed(AnimationClip src, string name, float[] ss, float[] ts, AnimationClipSettings settings, AnimationEvent[] events)
        {
            var clip = Object.Instantiate(src);
            clip.name = name;
            var bindings = AnimationUtility.GetCurveBindings(src);
            var curves = bindings.Select(b => Retime(AnimationUtility.GetEditorCurve(src, b), ss, ts)).ToArray();
            AnimationUtility.SetEditorCurves(clip, bindings, curves);
            settings.stopTime = ts[ts.Length - 1];
            settings.startTime = 0;
            AnimationUtility.SetAnimationClipSettings(clip, settings);
            AnimationUtility.SetAnimationEvents(clip, events);
            return clip;
        }

        /// <summary>Write a clip asset (in place when it exists, so references to it survive); consumes <paramref name="clip"/>.</summary>
        static void SaveClip(string path, AnimationClip clip, string name)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            var existing = AssetDatabase.LoadAssetAtPath<AnimationClip>(path);
            if (existing != null)
            {
                EditorUtility.CopySerialized(clip, existing);
                existing.name = name;
                EditorUtility.SetDirty(existing);
                Object.DestroyImmediate(clip);
            }
            else AssetDatabase.CreateAsset(clip, path);
        }

        /// <summary>
        /// Piecewise-linear re-time of one curve: source seconds ss[i] map to clip seconds ts[i]. Source keys inside the
        /// range keep their values, tangents are scaled by the segment's rate, and keys are added at the knots (with
        /// one-sided slopes) so the motion before and after the strike keeps its shape.
        /// </summary>
        static AnimationCurve Retime(AnimationCurve c, float[] ss, float[] ts)
        {
            if (c == null || c.length == 0) return c;
            const float eps = 1e-4f;
            var s0 = ss[0];
            var sN = ss[ss.Length - 1];
            var src = c.keys;
            var times = new SortedSet<float>(ss);
            foreach (var k in src) if (k.time > s0 + eps && k.time < sN - eps) times.Add(k.time);
            int Seg(float s, bool right)
            {
                for (var i = 0; i < ss.Length - 1; i++)
                    if (right ? s < ss[i + 1] - eps : s <= ss[i + 1] + eps) return i;
                return ss.Length - 2;
            }
            float Rate(int i) => (ss[i + 1] - ss[i]) / Mathf.Max(1e-5f, ts[i + 1] - ts[i]);
            float ToT(float s) { var i = Seg(s, false); return ts[i] + (s - ss[i]) / Rate(i); }
            var keys = new List<Keyframe>();
            var lastT = float.NegativeInfinity;
            foreach (var s in times)
            {
                float inS, outS;
                var match = Array.FindIndex(src, k => Mathf.Abs(k.time - s) < eps);
                if (match >= 0) { inS = src[match].inTangent; outS = src[match].outTangent; }
                else
                {
                    const float h = 1e-3f;
                    var v = c.Evaluate(s);
                    inS = (v - c.Evaluate(s - h)) / h;
                    outS = (c.Evaluate(s + h) - v) / h;
                }
                var t = ToT(s);
                if (t <= lastT + eps) continue;
                lastT = t;
                var inRate = Rate(Seg(s, false));
                var outRate = Rate(Mathf.Min(Seg(s, true), ss.Length - 2));
                keys.Add(new Keyframe(t, c.Evaluate(s),
                    float.IsInfinity(inS) ? inS : inS * inRate,
                    float.IsInfinity(outS) ? outS : outS * outRate));
            }
            // Constant channels (held fists, idle fingers) keep two keys.
            if (keys.Count > 2)
            {
                var min = keys.Min(k => k.value);
                var max = keys.Max(k => k.value);
                if (max - min < 1e-5f) keys = new List<Keyframe> { new(keys[0].time, keys[0].value, 0, 0), new(keys[keys.Count - 1].time, keys[0].value, 0, 0) };
            }
            return new AnimationCurve(keys.ToArray()) { preWrapMode = c.preWrapMode, postWrapMode = c.postWrapMode };
        }

        // ------------------------------------------------------------------ locomotion tuning

        public readonly struct Gait
        {
            public readonly string Clip;
            public readonly float Threshold, TimeScale, Authored;
            /// <summary>"mixamo", "ual" or "cmu".</summary>
            public readonly string Source;
            /// <summary>An imported library clip (Mixamo or UAL), tuned from its measured stride.</summary>
            public bool Mixamo => Source != "cmu";
            public Gait(string clip, float threshold, float timeScale, float authored, string source)
            { Clip = clip; Threshold = threshold; TimeScale = timeScale; Authored = authored; Source = source; }
        }

        /// <summary>
        /// Stride-probe calibration for a style: mean of (authoring-rig reading ÷ authored speed) over the CMU gaits
        /// (about 0.91: the probe reads planted-joint speed, a little below the contact-point speed the clips were
        /// authored to). Measured Mixamo strides are divided by it. 1 when unknown.
        /// </summary>
        static float StrideBias(JObject report, string key)
        {
            var g = report?["cmuGaits"]?[key] as JObject;
            if (g == null) return 1f;
            var r = g.Properties().Select(p => p.Value as JObject)
                .Where(o => o != null && (float?)o["metaSpeed"] > 0.3f && (float?)o["speedOnAuthoringRig"] > 0.3f)
                .Select(o => (float)o["speedOnAuthoringRig"] / (float)o["metaSpeed"]).ToArray();
            return r.Length == 0 ? 1f : Mathf.Clamp(r.Average(), 0.7f, 1.3f);
        }

        /// <summary>Crouched move speed of the heroes (Hero.CrouchSpeed).</summary>
        public const float CrouchSpeed = 1.5f;

        /// <summary>Crouch walk tuning: measured stride speed on the hero rig (cmuGaits / Mixamo analysis), else the
        /// clips_meta speed; playback scale = crouch speed ÷ authored.</summary>
        public static Gait CrouchGait(string style, AnimationClip clip)
        {
            var meta = Meta();
            var report = File.Exists(ReportPath) ? JObject.Parse(File.ReadAllText(ReportPath)) : null;
            var key = style.ToLowerInvariant();
            var mixamo = IsImported(clip);
            var ce = report?["styles"]?[key]?["crouch_walk"];
            var measured = mixamo ? (float?)ce?["speed"] / ((bool?)ce?["contactSpeed"] == true ? 1f : StrideBias(report, key)) : null;
            var metaSpeed = (float?)meta[key]?["crouch_walk"]?["speed"] ?? 0f;
            var authored = measured is > 0.3f ? measured.Value : metaSpeed > 0.3f ? metaSpeed : CrouchSpeed;
            var scale = Mathf.Clamp(CrouchSpeed / authored, 0.6f, 1.6f);
            return new Gait("crouch_walk", authored * scale, scale, authored, SourceOf(clip));
        }

        /// <summary>
        /// Blend thresholds and playback scales for walk / run / sprint. Feet stay planted when a clip plays at
        /// game speed ÷ authored speed. CMU clips were authored at the clips_meta speeds; Mixamo clips use their measured
        /// stride speed (calibrated by <see cref="StrideBias"/>), with the playback scale limited to 0.75–1.4 (cadence
        /// stays natural) and the threshold moved to the speed the clip then matches.
        /// </summary>
        public static Gait[] Gaits(string style, Func<string, AnimationClip> clipOf)
        {
            var meta = Meta();
            var report = File.Exists(ReportPath) ? JObject.Parse(File.ReadAllText(ReportPath)) : null;
            var list = new List<Gait>();
            var prev = 0.3f;
            foreach (var (name, game) in GameGaits)
            {
                var clip = clipOf(name);
                if (clip == null) continue;
                var mixamo = IsImported(clip);
                float authored, scale, threshold;
                var entry = report?["styles"]?[style.ToLowerInvariant()]?[name];
                // UAL gaits record the contact-point speed (ClipProbe.ContactSpeed, no probe bias); Mixamo the stride probe's.
                var bias = (bool?)entry?["contactSpeed"] == true ? 1f : StrideBias(report, style.ToLowerInvariant());
                var measured = mixamo ? (float?)entry?["speed"] / bias : null;
                var cmuMeasured = !mixamo && entry != null && (bool?)entry["useMeasured"] == true ? (float?)entry["speed"] : null;
                if (mixamo && measured is > 0.3f)
                {
                    authored = measured.Value;
                    scale = Mathf.Clamp(game / authored, 0.75f, 1.4f);
                    threshold = authored * scale;
                }
                else
                {
                    var metaSpeed = (float?)meta[style.ToLowerInvariant()]?[name]?["speed"] ?? 0f;
                    authored = cmuMeasured is > 0.3f ? cmuMeasured.Value : metaSpeed > 0.3f ? metaSpeed : game;
                    scale = game / authored;
                    threshold = game;
                }
                threshold = Mathf.Max(threshold, prev + 0.3f);
                prev = threshold;
                list.Add(new Gait(name, threshold, scale, authored, SourceOf(clip)));
            }
            return list.ToArray();
        }
    }
}
