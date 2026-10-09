using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace EOA
{
    public enum RobotKind { Drone, Sentinel, Warden, Stalker, Guardian, Bolt }

    /// <summary>Robot colour scheme (sRGB). Glow colours are rendered HDR at GlowIntensity.</summary>
    public struct RobotPalette
    {
        public Color Shell, Frame, Glow;
        public float GlowIntensity;

        public RobotPalette(uint shell, uint frame, uint glow, float glowIntensity)
        {
            Shell = CombatMath.Hex(shell);
            Frame = CombatMath.Hex(frame);
            Glow = CombatMath.Hex(glow);
            GlowIntensity = glowIntensity;
        }
    }

    /// <summary>
    /// Robot visuals (port of RobotModel.ts + the drone body of Drone.ts). Tries
    /// <c>Resources.Load&lt;GameObject&gt;("Models/Robots/" + model)</c> first and binds its transforms by name
    /// (contract: Assets/Scripts/Enemies/ROBOT_PARTS.md); otherwise builds rigid parts from procedural meshes
    /// parented to a 20-bone humanoid hierarchy with identity rest rotations. Drives the bones from a
    /// <see cref="RobotAnimator"/>, handles hit flash, telegraph glow and opacity (stalker phasing).
    /// Ticked explicitly by the owning enemy (<see cref="Tick"/>).
    /// </summary>
    [DisallowMultipleComponent]
    public sealed class RobotRig : MonoBehaviour
    {
        // ------------------------------------------------------------------ Skeleton contract

        public static readonly string[] BoneNames =
        {
            "root", "hips", "spine", "chest", "neck", "head",
            "clavicle_L", "upperarm_L", "forearm_L", "hand_L",
            "clavicle_R", "upperarm_R", "forearm_R", "hand_R",
            "thigh_L", "shin_L", "foot_L",
            "thigh_R", "shin_R", "foot_R",
        };

        public static readonly int[] ParentOf = { -1, 0, 1, 2, 3, 4, 3, 6, 7, 8, 3, 10, 11, 12, 1, 14, 15, 1, 17, 18 };

        public const int Root = 0, Hips = 1, Spine = 2, Chest = 3, Neck = 4, Head = 5,
            ClavicleL = 6, UpperarmL = 7, ForearmL = 8, HandL = 9,
            ClavicleR = 10, UpperarmR = 11, ForearmR = 12, HandR = 13,
            ThighL = 14, ShinL = 15, FootL = 16, ThighR = 17, ShinR = 18, FootR = 19;

        static Dictionary<string, int> boneIndex;

        public static int BoneIndex(string name)
        {
            if (boneIndex == null)
            {
                boneIndex = new Dictionary<string, int>();
                for (int i = 0; i < BoneNames.Length; i++) boneIndex[BoneNames[i]] = i;
            }
            return name != null && boneIndex.TryGetValue(name, out var i2) ? i2 : -1;
        }

        /// <summary>
        /// Bind-pose joint positions (metres, Unity space: facing +Z, robot's left on -X) for a humanoid robot of
        /// `height` (port of HumanRig.computeJoints, male build, A-pose arm angle 14 deg). Also returns helper
        /// points headCenter, headTop, handEnd_L/R, toe_L/R, heel_L/R.
        /// </summary>
        public static Dictionary<string, Vector3> ComputeJoints(float height, float shoulderWidth, out float s)
        {
            s = height / 1.8f;
            float sc = s;
            var j = new Dictionary<string, Vector3>();
            // Prototype coordinates (left = +X) mirrored to Unity (left = -X).
            Vector3 V(float x, float y, float z) => new Vector3(-x * sc, y * sc, z * sc);
            float sw = 0.186f * shoulderWidth, hw = 0.094f;
            j["root"] = V(0, 0, 0);
            j["hips"] = V(0, 0.955f, 0);
            j["spine"] = V(0, 1.075f, -0.012f);
            j["chest"] = V(0, 1.245f, -0.022f);
            j["neck"] = V(0, 1.47f, -0.026f);
            j["head"] = V(0, 1.56f, -0.012f);
            j["headCenter"] = V(0, 1.56f + 0.103f, 0.014f);
            j["headTop"] = V(0, 1.56f + 0.103f + 0.118f, 0.01f);
            float a = 14f * Mathf.Deg2Rad, a2 = a - 0.04f;
            const float armY = 1.458f, up = 0.305f, fo = 0.262f, hand = 0.185f;
            for (int side = 0; side < 2; side++)
            {
                string sd = side == 0 ? "L" : "R";
                float sx = side == 0 ? 1f : -1f;
                j["clavicle_" + sd] = V(sx * 0.028f, armY - 0.005f, -0.006f);
                float shx = sx * sw, shy = armY, shz = -0.022f;
                float elx = shx + sx * Mathf.Sin(a) * up, ely = shy - Mathf.Cos(a) * up, elz = shz - 0.012f;
                float wrx = elx + sx * Mathf.Sin(a2) * fo, wry = ely - Mathf.Cos(a2) * fo, wrz = elz + 0.022f;
                j["upperarm_" + sd] = V(shx, shy, shz);
                j["forearm_" + sd] = V(elx, ely, elz);
                j["hand_" + sd] = V(wrx, wry, wrz);
                j["handEnd_" + sd] = V(wrx + sx * Mathf.Sin(a2) * hand, wry - Mathf.Cos(a2) * hand, wrz + 0.008f);
                j["thigh_" + sd] = V(sx * hw, 0.93f, 0f);
                j["shin_" + sd] = V(sx * (hw + 0.008f), 0.515f, 0.016f);
                j["foot_" + sd] = V(sx * (hw + 0.012f), 0.088f, -0.022f);
                j["toe_" + sd] = V(sx * (hw + 0.02f), 0.03f, 0.165f);
                j["heel_" + sd] = V(sx * (hw + 0.012f), 0.03f, -0.075f);
            }
            return j;
        }

        // ------------------------------------------------------------------ State

        public RobotKind Kind { get; private set; }
        public float Height { get; private set; }
        /// <summary>Uniform scale relative to the 1.8 m reference body.</summary>
        public float S { get; private set; } = 1f;
        /// <summary>True when bound to an artist model from Resources/Models/Robots.</summary>
        public bool FromModel { get; private set; }
        /// <summary>Null for the drone.</summary>
        public RobotAnimator Anim { get; private set; }
        /// <summary>Bind-pose joints (rig-local, Unity space). Empty for the drone.</summary>
        public Dictionary<string, Vector3> Joints { get; private set; } = new();

        public readonly Transform[] Bones = new Transform[20];
        readonly Quaternion[] restModel = new Quaternion[20];
        readonly Quaternion[] poseModel = new Quaternion[20];
        Vector3 rootRestPos, hipsRestRel;

        // Special parts (may be null)
        public Transform Core { get; internal set; }
        public readonly List<Transform> Plates = new();
        public Transform DroneBody { get; internal set; }
        public readonly List<Transform> Rotors = new();

        // Materials (owned)
        public Material ShellMat { get; private set; }
        public Material FrameMat { get; private set; }
        public Material JointMat { get; private set; }
        public Material GlowMat { get; private set; }
        public Material RotorMat { get; private set; }
        /// <summary>Separate glow material for the guardian core (so its exposed pulse reads on its own).</summary>
        public Material CoreMat { get; private set; }

        readonly List<Material> owned = new();
        readonly List<Renderer> renderers = new();

        Color glowColor;
        float glowIntensity;
        float flash, appliedFlash = -1f;
        float appliedGlow = -1f;
        Color appliedGlowColor;
        float appliedOpacity = 1f;
        bool transparent;

        /// <summary>0..1: glow brightens toward an attack (x(1 + 1.6 t)).</summary>
        public float Telegraph;
        /// <summary>1 = solid; below 1 the shell/frame/joint materials switch to transparent (phasing).</summary>
        public float Opacity = 1f;
        /// <summary>Extra glow multiplier (drone charge pulse).</summary>
        public float GlowBoost = 1f;

        // ------------------------------------------------------------------ Factory

        /// <summary>
        /// Build or bind a robot under `parent`. `model` is the Resources name (e.g. "sentinel", "guardian_vault");
        /// `fallbackModel` is tried next (e.g. "guardian"); with neither found the procedural body for `kind` is built.
        /// </summary>
        public static RobotRig Create(Transform parent, RobotKind kind, RobotPalette pal, string model, string fallbackModel = null)
        {
            var go = new GameObject("Robot_" + kind);
            go.layer = parent != null ? parent.gameObject.layer : 0;
            go.transform.SetParent(parent, false);
            var rig = go.AddComponent<RobotRig>();
            rig.Init(kind, pal, model, fallbackModel);
            return rig;
        }

        public static float HeightOf(RobotKind kind) => kind switch
        {
            RobotKind.Drone => 0.9f,
            RobotKind.Sentinel => 2.15f,
            RobotKind.Warden => 2.6f,
            RobotKind.Stalker => 2.0f,
            RobotKind.Bolt => 1.55f,
            _ => 5.2f,
        };

        void Init(RobotKind kind, RobotPalette pal, string model, string fallbackModel)
        {
            Kind = kind;
            Height = HeightOf(kind);
            glowColor = pal.Glow;
            glowIntensity = pal.GlowIntensity;
            MakeMaterials(pal);

            bool bound = TryBindModel(model) || (!string.IsNullOrEmpty(fallbackModel) && TryBindModel(fallbackModel));
            if (!bound)
            {
                if (kind == RobotKind.Drone) RobotBodies.BuildDrone(this);
                else
                {
                    BuildSkeleton();
                    switch (kind)
                    {
                        case RobotKind.Sentinel:
                        case RobotKind.Bolt: RobotBodies.BuildSentinel(this, false); break;
                        case RobotKind.Warden: RobotBodies.BuildSentinel(this, true); break;
                        case RobotKind.Stalker: RobotBodies.BuildStalker(this); break;
                        case RobotKind.Guardian: RobotBodies.BuildGuardian(this); break;
                    }
                }
            }
            if (kind != RobotKind.Drone)
            {
                CaptureRest();
                var clipKind = kind == RobotKind.Stalker ? RobotClips.Kind.Stalker : kind == RobotKind.Guardian ? RobotClips.Kind.Guardian : RobotClips.Kind.Sentinel;
                var clips = RobotClips.Get(clipKind);
                var style = kind == RobotKind.Guardian ? RobotClips.Style.Heavy : RobotClips.Style.Robot;
                Anim = new RobotAnimator(RobotClips.Loco(style, clips["stance"]), S);
            }
            CollectRenderers();
            ApplyMaterials(true);
        }

        void MakeMaterials(RobotPalette pal)
        {
            // Worn-metal detail set (BaseColor/Normal/MetallicSmoothness, 1 UV = 1 m) from the Blender robot kit; the
            // editor setup writes Resources/Models/Robots/robot_metal.mat. Palette colours tint it (texture is ~0.78 grey).
            var metal = Resources.Load<Material>("Models/Robots/robot_metal");
            ShellMat = Own(metal != null ? Tinted(metal, pal.Shell, "robot_shell") : FxMaterials.Lit(pal.Shell, 0.65f, 1f - 0.42f, "robot_shell"));
            FrameMat = Own(metal != null ? Tinted(metal, pal.Frame, "robot_frame") : FxMaterials.Lit(pal.Frame, 0.75f, 1f - 0.55f, "robot_frame"));
            JointMat = Own(FxMaterials.Lit(CombatMath.Hex(0x15171a), 0.6f, 1f - 0.6f, "robot_joint"));
            GlowMat = Own(FxMaterials.Unlit(FxMaterials.Hdr(pal.Glow, pal.GlowIntensity), "robot_glow"));
            CoreMat = Own(FxMaterials.Unlit(FxMaterials.Hdr(pal.Glow, pal.GlowIntensity), "robot_core"));
            RotorMat = Own(FxMaterials.Particle(false, FxMaterials.White, true));
            RotorMat.name = "robot_rotor";
            RotorMat.SetColor("_BaseColor", CombatMath.Hex(0x202428, 0.55f));
        }

        static Material Tinted(Material template, Color tint, string name)
        {
            var m = new Material(template) { name = name };
            var c = new Color(Mathf.Min(1, tint.r * 1.25f), Mathf.Min(1, tint.g * 1.25f), Mathf.Min(1, tint.b * 1.25f), 1);
            m.SetColor("_BaseColor", c);
            m.EnableKeyword("_EMISSION");
            m.SetColor("_EmissionColor", Color.black);
            m.globalIlluminationFlags = MaterialGlobalIlluminationFlags.None;
            return m;
        }

        Material Own(Material m)
        {
            owned.Add(m);
            return m;
        }

        void OnDestroy()
        {
            foreach (var m in owned) if (m != null) Destroy(m);
            owned.Clear();
        }

        // ------------------------------------------------------------------ Procedural skeleton

        void BuildSkeleton()
        {
            float shoulder = Kind == RobotKind.Guardian ? 1.35f : 1.15f;
            Joints = ComputeJoints(Height, shoulder, out float s);
            S = s;
            for (int i = 0; i < BoneNames.Length; i++)
            {
                var t = new GameObject(BoneNames[i]).transform;
                t.gameObject.layer = gameObject.layer;
                int p = ParentOf[i];
                t.SetParent(p < 0 ? transform : Bones[p], false);
                Vector3 jp = Joints[BoneNames[i]];
                t.localPosition = p < 0 ? jp : jp - Joints[BoneNames[p]];
                t.localRotation = Quaternion.identity;
                Bones[i] = t;
            }
        }

        /// <summary>Attach a rigid part to a bone at a bind-pose (rig-local) position. Used by RobotBodies.</summary>
        internal Transform Attach(string bone, Mesh mesh, Material mat, Vector3 rigPos, Quaternion? rot = null, Vector3? scale = null, string name = null)
        {
            int bi = BoneIndex(bone);
            Transform parent = bi >= 0 ? Bones[bi] : transform;
            Vector3 jointPos = bi >= 0 ? Joints[bone] : Vector3.zero;
            return AttachTo(parent, mesh, mat, rigPos - jointPos, rot ?? Quaternion.identity, scale ?? Vector3.one, name ?? (bone + "_part"));
        }

        internal Transform AttachTo(Transform parent, Mesh mesh, Material mat, Vector3 localPos, Quaternion localRot, Vector3 scale, string name)
        {
            var go = new GameObject(name);
            go.layer = gameObject.layer;
            var t = go.transform;
            t.SetParent(parent, false);
            t.localPosition = localPos;
            t.localRotation = localRot;
            t.localScale = scale;
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var mr = go.AddComponent<MeshRenderer>();
            mr.sharedMaterial = mat;
            bool glow = mat == GlowMat || mat == CoreMat || mat == RotorMat;
            mr.shadowCastingMode = glow ? ShadowCastingMode.Off : ShadowCastingMode.On;
            mr.receiveShadows = !glow;
            return t;
        }

        // ------------------------------------------------------------------ Artist model binding

        bool TryBindModel(string model)
        {
            if (string.IsNullOrEmpty(model)) return false;
            var prefab = Resources.Load<GameObject>("Models/Robots/" + model);
            if (prefab == null) return false;
            var inst = Instantiate(prefab, transform, false);
            inst.name = prefab.name;
            inst.transform.localPosition = Vector3.zero;
            inst.transform.localRotation = Quaternion.identity;
            foreach (var an in inst.GetComponentsInChildren<Animator>(true)) an.enabled = false;
            foreach (var col in inst.GetComponentsInChildren<Collider>(true))
            {
                col.enabled = false;
                Destroy(col);
            }
            SetLayer(inst.transform, gameObject.layer);

            var map = new Dictionary<string, Transform>();
            foreach (var t in inst.GetComponentsInChildren<Transform>(true))
            {
                string n = t.name;
                int c = Mathf.Max(n.LastIndexOf(':'), n.LastIndexOf('|'));
                if (c >= 0) n = n.Substring(c + 1);
                if (!map.ContainsKey(n)) map[n] = t;
            }

            if (Kind == RobotKind.Drone)
            {
                if (!map.TryGetValue("body", out var body))
                {
                    Debug.LogWarning($"[robot] model '{model}' has no 'body' transform; using procedural drone");
                    Discard(inst);
                    return false;
                }
                DroneBody = body;
                for (int i = 0; i < 8; i++) if (map.TryGetValue("rotor_" + i, out var r)) Rotors.Add(r);
            }
            else
            {
                for (int i = 0; i < BoneNames.Length; i++)
                {
                    if (!map.TryGetValue(BoneNames[i], out var b))
                    {
                        Debug.LogWarning($"[robot] model '{model}' is missing bone '{BoneNames[i]}'; using procedural {Kind}");
                        Discard(inst);
                        System.Array.Clear(Bones, 0, Bones.Length);
                        return false;
                    }
                    Bones[i] = b;
                }
                // Sanity check: hips should sit at 0.955 * S (reference body) above the root.
                S = HeightOf(Kind) / 1.8f;
                float hipsY = transform.InverseTransformPoint(Bones[Hips].position).y;
                float expected = S * 0.955f;
                if (Mathf.Abs(hipsY / expected - 1f) > 0.2f)
                    Debug.LogWarning($"[robot] model '{model}' hips at {hipsY:0.00} m, expected ~{expected:0.00} m (check scale / ROBOT_PARTS.md)");
                Joints = new Dictionary<string, Vector3>();
                for (int i = 0; i < BoneNames.Length; i++) Joints[BoneNames[i]] = transform.InverseTransformPoint(Bones[i].position);
                if (map.TryGetValue("plate_L", out var pl)) Plates.Add(pl);
                if (map.TryGetValue("plate_R", out var pr)) Plates.Add(pr);
            }
            if (map.TryGetValue("core", out var core)) Core = core;

            // Swap known materials (by material or object name) for the runtime ones so flash/telegraph/opacity work.
            foreach (var r in inst.GetComponentsInChildren<Renderer>(true))
            {
                var mats = r.sharedMaterials;
                bool changed = false;
                for (int m = 0; m < mats.Length; m++)
                {
                    string key = ((mats[m] != null ? mats[m].name : "") + " " + r.name).ToLowerInvariant();
                    Material rep = null;
                    if (r.transform == Core || (Kind == RobotKind.Guardian && key.Contains("core"))) rep = CoreMat;
                    else if (key.Contains("glow") || key.Contains("emissive")) rep = GlowMat;
                    else if (key.Contains("rotor")) rep = RotorMat;
                    else if (key.Contains("shell")) rep = ShellMat;
                    else if (key.Contains("frame")) rep = FrameMat;
                    else if (key.Contains("joint")) rep = JointMat;
                    if (rep != null) { mats[m] = rep; changed = true; }
                }
                if (changed) r.sharedMaterials = mats;
                bool glowOnly = System.Array.TrueForAll(mats, x => x == GlowMat || x == CoreMat || x == RotorMat);
                if (glowOnly) r.shadowCastingMode = ShadowCastingMode.Off;
            }
            FromModel = true;
            return true;
        }

        static void Discard(GameObject inst)
        {
            inst.SetActive(false);
            inst.transform.SetParent(null, false);
            Destroy(inst);
        }

        static void SetLayer(Transform t, int layer)
        {
            t.gameObject.layer = layer;
            for (int i = 0; i < t.childCount; i++) SetLayer(t.GetChild(i), layer);
        }

        void CaptureRest()
        {
            Quaternion inv = Quaternion.Inverse(transform.rotation);
            for (int i = 0; i < BoneNames.Length; i++) restModel[i] = inv * Bones[i].rotation;
            rootRestPos = transform.InverseTransformPoint(Bones[Root].position);
            // Hips offset relative to the root, in the root's canonical (world-aligned) frame.
            hipsRestRel = transform.InverseTransformPoint(Bones[Hips].position) - rootRestPos;
        }

        void CollectRenderers()
        {
            renderers.Clear();
            GetComponentsInChildren(true, renderers);
        }

        // ------------------------------------------------------------------ Runtime

        public Transform Bone(string name)
        {
            int i = BoneIndex(name);
            return i >= 0 ? Bones[i] : null;
        }

        /// <summary>World forward of a bone in the animated pose (independent of the model's rest orientation).</summary>
        public Vector3 PoseForward(int bone) => transform.rotation * poseModel[bone] * Vector3.forward;

        /// <summary>Glow colour override (drone eye: calm cyan vs hostile red).</summary>
        public void SetGlow(Color srgb, float intensity)
        {
            glowColor = srgb;
            glowIntensity = intensity;
        }

        public void HitFlash(float amount = 1f) => flash = Mathf.Max(flash, amount);

        /// <summary>Set the guardian core colour (HDR intensity).</summary>
        public void SetCore(Color srgb, float intensity)
        {
            if (CoreMat != null) CoreMat.SetColor("_BaseColor", WithAlpha(FxMaterials.Hdr(srgb, intensity), transparent ? Mathf.Max(0.2f, Opacity) : 1f));
        }

        static Color WithAlpha(Color c, float a)
        {
            c.a = a;
            return c;
        }

        /// <summary>Advance animation and materials. Call once per frame from the owning enemy.</summary>
        public void Tick(float dt)
        {
            if (Anim != null)
            {
                Anim.Update(dt);
                ApplyPose();
            }
            if (flash > 0f) flash = Mathf.Max(0f, flash - dt * 7f);
            ApplyMaterials(false);
        }

        void ApplyPose()
        {
            Quaternion rigRot = transform.rotation;
            for (int i = 0; i < BoneNames.Length; i++)
            {
                int p = ParentOf[i];
                poseModel[i] = p < 0 ? Anim.Local[i] : poseModel[p] * Anim.Local[i];
                var b = Bones[i];
                if (b == null) continue;
                b.rotation = rigRot * poseModel[i] * restModel[i];
                if (i == Hips) b.position = transform.TransformPoint(rootRestPos + poseModel[Root] * (hipsRestRel + Anim.HipsOffset * S));
            }
        }

        static readonly int EmissionColorId = Shader.PropertyToID("_EmissionColor");

        void ApplyMaterials(bool force)
        {
            if (force || !Mathf.Approximately(flash, appliedFlash))
            {
                appliedFlash = flash;
                // Hit flash: a short cool-white pop that reads as impact without whiting the robot out under bloom.
                ShellMat.SetColor(EmissionColorId, new Color(flash * 0.22f, flash * 0.25f, flash * 0.28f, 1f));
                FrameMat.SetColor(EmissionColorId, new Color(flash * 0.12f, flash * 0.13f, flash * 0.15f, 1f));
            }

            bool wantTransparent = Opacity < 0.999f;
            if (wantTransparent != transparent || force)
            {
                transparent = wantTransparent;
                foreach (var m in new[] { ShellMat, FrameMat, JointMat }) FxMaterials.SetTransparent(m, transparent, false, false);
                FxMaterials.SetTransparent(GlowMat, transparent, false, false);
                FxMaterials.SetTransparent(CoreMat, transparent, false, false);
                foreach (var r in renderers)
                    if (r != null && r.sharedMaterial != GlowMat && r.sharedMaterial != CoreMat && r.sharedMaterial != RotorMat)
                        r.shadowCastingMode = transparent ? ShadowCastingMode.Off : ShadowCastingMode.On;
                appliedOpacity = -1f;
                appliedGlow = -1f;
            }
            if (transparent && !Mathf.Approximately(Opacity, appliedOpacity))
            {
                appliedOpacity = Opacity;
                foreach (var m in new[] { ShellMat, FrameMat, JointMat })
                {
                    FxMaterials.SetAlpha(m, Opacity);
                    m.SetFloat("_ZWrite", Opacity > 0.6f ? 1f : 0f);
                }
            }

            float g = glowIntensity * (1f + Telegraph * 1.6f) * GlowBoost;
            if (force || !Mathf.Approximately(g, appliedGlow) || appliedGlowColor != glowColor)
            {
                appliedGlow = g;
                appliedGlowColor = glowColor;
                GlowMat.SetColor("_BaseColor", WithAlpha(FxMaterials.Hdr(glowColor, g), transparent ? Mathf.Max(0.2f, Opacity) : 1f));
            }
        }

        /// <summary>Re-collect renderers after parts were attached at runtime (weapon models), so visibility and phasing
        /// include them.</summary>
        public void RefreshRenderers()
        {
            CollectRenderers();
            ApplyMaterials(true);
        }

        /// <summary>Stop managing a detached part (death debris): its renderers leave the visibility list.</summary>
        public void ReleasePart(Transform part)
        {
            if (part == null) return;
            for (int i = renderers.Count - 1; i >= 0; i--)
            {
                var r = renderers[i];
                if (r == null || r.transform == part || r.transform.IsChildOf(part)) renderers.RemoveAt(i);
            }
        }

        /// <summary>Show/hide every renderer (death explosions hide the wreck).</summary>
        public void SetVisible(bool visible)
        {
            foreach (var r in renderers) if (r != null) r.enabled = visible;
        }
    }
}
