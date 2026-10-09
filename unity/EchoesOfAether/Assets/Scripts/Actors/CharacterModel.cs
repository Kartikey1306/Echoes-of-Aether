using System;
using System.Collections.Generic;
using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Visual layer of a human character built by the Blender/MakeHuman pipeline. Applies an Appearance
    /// (blendshape morphs, hair/facial-hair meshes, skin/eye/hair/outfit colours, armour toggles), drives
    /// facial animation (blink, talk, expressions) and simple effects (hit flash, echo hologram).
    /// The editor-side CharacterBuilder fills the serialized fields when it creates the prefab.
    /// </summary>
    public sealed class CharacterModel : MonoBehaviour
    {
        [Serializable]
        public sealed class GarmentTextures
        {
            public string Material;          // "Garment_Top" / "Garment_Pants"
            public Texture2D Mask;           // R secondary, G trim, B glow, A seam (readable)
            public Texture2D Normal;
        }

        public string CharacterId;
        public bool Female;
        public bool Npc;
        public bool Echo;
        public float BaseHeight = 1.8f;
        public Animator Animator;
        public SkinnedMeshRenderer[] Renderers = Array.Empty<SkinnedMeshRenderer>();
        public string[] HairStyles = Array.Empty<string>();
        public string[] FacialHair = Array.Empty<string>();
        public string DefaultHair = "short";
        public Texture2D[] SkinTones = Array.Empty<Texture2D>(); // light, medium, tan, dark
        public Texture2D EyeTexture;
        /// <summary>Glowing tattoo emission mask (Skin_Tattoo.png) when the character has one.</summary>
        public Texture2D TattooMap;
        Color tattooColor;
        Texture2D activeTattoo;

        sealed class CustomPart
        {
            public string Id;
            public GameObject Root;
            public readonly List<Material> Materials = new();
            public readonly List<(SkinnedMeshRenderer, int)> Shapes = new();
            public readonly Dictionary<(SkinnedMeshRenderer, int), string> ShapeNames = new();
            public string[] Replaces = Array.Empty<string>();
            public string Tint, Slot;
        }

        readonly Dictionary<string, CustomPart> custom = new();

        /// <summary>Apply catalog attachments (hair, eyewear, armour). Returns true when a catalog hair style is worn.</summary>
        bool ApplyCustom(Appearance a)
        {
            var cat = CustomCatalog.Get();
            var hair = cat.Find("hair", CharacterId, a.HairStyle);
            SetCustom("hair", hair);
            SetCustom("eyewear", cat.Find("eyewear", CharacterId, a.Eyewear));
            var armour = cat.Find("armour", CharacterId, a.ArmorSet);
            SetCustom("armour", armour);
            return hair != null;
        }

        /// <summary>Armour/eyewear slot from its catalog definition (PBR maps, lens glass or emissive colour).</summary>
        static void SetupCustomMaterial(Material m, CustomCatalog.MatDef d)
        {
            var bm = CustomCatalog.Load(d.BaseMap);
            if (bm != null) m.SetTexture(BaseMapId, bm);
            if (!string.IsNullOrEmpty(d.Tint)) m.SetColor(BaseColorId, Appearance.ToColor(d.Tint));
            var n = CustomCatalog.Load(d.Normal);
            if (n != null) { m.SetTexture("_BumpMap", n); m.EnableKeyword("_NORMALMAP"); m.SetFloat("_BumpScale", 1f); }
            var mm = CustomCatalog.Load(d.MaskMap);
            if (mm != null)
            {
                m.SetTexture("_MetallicGlossMap", mm);
                m.EnableKeyword("_METALLICSPECGLOSSMAP");
                m.SetFloat("_SmoothnessTextureChannel", 0);
                m.SetFloat("_Smoothness", 1f);
                m.SetTexture("_OcclusionMap", mm);
                m.EnableKeyword("_OCCLUSIONMAP");
            }
            if (!string.IsNullOrEmpty(d.LensTint))
            {
                // Eyewear lens: tinted glass.
                FxMaterials.SetTransparent(m, true, false, false);
                var c = Appearance.ToColor(d.LensTint);
                c.a = d.LensAlpha;
                m.SetColor(BaseColorId, c);
                m.SetFloat("_Smoothness", 0.95f);
            }
            if (!string.IsNullOrEmpty(d.Color) && m.HasProperty(EmissionId))
            {
                m.EnableKeyword("_EMISSION");
                m.SetColor(EmissionId, Appearance.ToColor(d.Color) * d.Intensity);
                m.globalIlluminationFlags = MaterialGlobalIlluminationFlags.None;
            }
        }

        /// <summary>
        /// Fits a pair of glasses to this face: the lenses are centred on the eyes (from the humanoid eye bones), sized
        /// to the eye spacing, and sat a fixed distance in front of the eyeballs. Catalog eyewear was authored on an
        /// earlier head, and heads also change with the face sliders, so the fit is measured, not assumed.
        /// </summary>
        void FitEyewear(GameObject root)
        {
            var an = Animator != null ? Animator : GetComponentInChildren<Animator>();
            var head = an != null ? an.GetBoneTransform(HumanBodyBones.Head) : null;
            var eyeL = an != null ? an.GetBoneTransform(HumanBodyBones.LeftEye) : null;
            var eyeR = an != null ? an.GetBoneTransform(HumanBodyBones.RightEye) : null;
            if (head == null || eyeL == null || eyeR == null || root.transform.parent != head)
            {
                Debug.Log($"[eyewear] {CharacterId}: no fit (head {head != null}, eyes {eyeL != null}/{eyeR != null}, parent {(root.transform.parent != null ? root.transform.parent.name : "-")})");
                return;
            }
            var t = root.transform;
            // Everything in head space (the glasses' parent).
            var min = new Vector3(float.MaxValue, float.MaxValue, float.MaxValue);
            var max = -min;
            var found = false;
            foreach (var mf in root.GetComponentsInChildren<MeshFilter>(true))
            {
                var mr = mf.GetComponent<Renderer>();
                if (mf.sharedMesh == null || mr == null) continue;
                // Lens sub-meshes (one renderer carries frame + lens materials).
                var mats = mr.sharedMaterials;
                for (var sm = 0; sm < mats.Length && sm < mf.sharedMesh.subMeshCount; sm++)
                {
                    if (mats[sm] == null || !mats[sm].name.Contains("Lens")) continue;
                    var b = mf.sharedMesh.GetSubMesh(sm).bounds;
                    for (var i = 0; i < 8; i++)
                    {
                        var c = new Vector3((i & 1) == 0 ? b.min.x : b.max.x, (i & 2) == 0 ? b.min.y : b.max.y, (i & 4) == 0 ? b.min.z : b.max.z);
                        var p = head.InverseTransformPoint(mf.transform.TransformPoint(c));
                        min = Vector3.Min(min, p); max = Vector3.Max(max, p);
                    }
                    found = true;
                }
            }
            if (!found)
            {
                var names = string.Join(",", System.Linq.Enumerable.Select(root.GetComponentsInChildren<Renderer>(true), r => r.name + ":" + (r.sharedMaterial != null ? r.sharedMaterial.name : "-") + ":" + (r.GetComponent<MeshFilter>() != null)));
                Debug.Log($"[eyewear] {CharacterId}: no lens renderers ({names})");
                return;
            }
            var lensCenter = (min + max) * 0.5f;
            var el = head.InverseTransformPoint(eyeL.position);
            var er = head.InverseTransformPoint(eyeR.position);
            var eyeMid = (el + er) * 0.5f;
            var eyeAxis = er - el;
            var ipd = eyeAxis.magnitude;
            if (ipd < 0.03f || ipd > 0.1f) return;
            eyeAxis /= ipd;
            // Forward = from the eyes towards the lenses (sideways component removed); up = the character's up.
            var fwd = Vector3.ProjectOnPlane(lensCenter - eyeMid, eyeAxis);
            if (fwd.sqrMagnitude < 1e-6f) return;
            fwd.Normalize();
            var up = Vector3.Cross(fwd, eyeAxis).normalized;
            if (Vector3.Dot(up, head.InverseTransformDirection(transform.up)) < 0) up = -up;
            var span = Mathf.Abs(Vector3.Dot(max - min, eyeAxis));
            var pair = span > ipd * 1.4f; // covers both eyes (not a monocle)
            var k = pair ? Mathf.Clamp(ipd * 2.05f / span, 0.75f, 1.25f) : 1f;
            // Uniform scale about the glasses' pivot, then move the lens centre onto the target: lens plane ~2.4 cm in
            // front of the eyeball centres, optical centre 2 mm above the pupils (monocles keep their side).
            var pivot = t.localPosition;
            t.localScale *= k;
            var scaledCenter = pivot + (lensCenter - pivot) * k;
            var lateral = pair ? 0f : Vector3.Dot(lensCenter - eyeMid, eyeAxis);
            var target = eyeMid + eyeAxis * lateral + fwd * 0.024f - up * 0.004f;
            t.localPosition = pivot + (target - scaledCenter);
            Debug.Log($"[eyewear] {CharacterId}/{root.name}: ipd {ipd * 1000:0} mm, lens span {span * 1000:0} mm -> scale {k:0.00}, moved {(target - scaledCenter).magnitude * 1000:0} mm");
        }

        void SetCustom(string slot, CustomCatalog.Item item)
        {
            custom.TryGetValue(slot, out var cur);
            if (cur != null && item != null && cur.Id == item.Id) return;
            if (cur != null)
            {
                foreach (var m in cur.Materials) if (m != null) Destroy(m);
                if (cur.Root != null) Destroy(cur.Root);
                foreach (var p in cur.Replaces) SetVisible(p, true);
                custom.Remove(slot);
            }
            if (item == null) return;
            var root = Attachments.Attach(this, item);
            if (root == null) return;
            if (slot == "eyewear" && !item.Fitted) FitEyewear(root); // hand-fitted pairs keep their authored placement
            var part = new CustomPart { Id = item.Id, Root = root, Replaces = item.Replaces ?? Array.Empty<string>(), Tint = item.Tint, Slot = slot };
            foreach (var r in root.GetComponentsInChildren<Renderer>(true))
            {
                r.renderingLayerMask |= CharacterLayerMask;
                var mats = r.sharedMaterials;
                for (var i = 0; i < mats.Length; i++)
                {
                    if (mats[i] == null) continue;
                    var inst = new Material(mats[i]) { name = mats[i].name };
                    if (inst.shader == null || !inst.shader.name.StartsWith("Universal Render Pipeline")) inst.shader = Shader.Find("Universal Render Pipeline/Lit");
                    if (slot == "hair")
                    {
                        // Hair cards: grey RGBA atlas tinted by the hair colour, opaque alpha-tested, double sided
                        // (no transparency sorting issues).
                        FxMaterials.SetTransparent(inst, false);
                        var tex = CustomCatalog.Load(item.BaseMap);
                        if (tex != null) inst.SetTexture(BaseMapId, tex);
                        if (inst.HasProperty("_AlphaClip")) inst.SetFloat("_AlphaClip", 1);
                        if (inst.HasProperty("_Cutoff")) inst.SetFloat("_Cutoff", item.AlphaCutoff);
                        if (inst.HasProperty("_Cull")) inst.SetFloat("_Cull", 0);
                        if (inst.HasProperty("_Smoothness")) inst.SetFloat("_Smoothness", 0.35f);
                        if (inst.HasProperty("_Metallic")) inst.SetFloat("_Metallic", 0);
                        inst.EnableKeyword("_ALPHATEST_ON");
                        inst.renderQueue = 2450;
                    }
                    else if (item.Materials != null && item.Materials.TryGetValue(inst.name, out var def)) SetupCustomMaterial(inst, def);
                    if (item.Frame != null && inst.name == "EyewearFrame")
                    {
                        inst.SetFloat("_Metallic", item.Frame.Metallic);
                        inst.SetFloat("_Smoothness", item.Frame.Smoothness);
                    }
                    part.Materials.Add(inst);
                    mats[i] = inst;
                }
                r.sharedMaterials = mats;
                if (r is SkinnedMeshRenderer smr && smr.sharedMesh != null)
                    for (var s = 0; s < smr.sharedMesh.blendShapeCount; s++)
                    {
                        var n = smr.sharedMesh.GetBlendShapeName(s);
                        var dot = n.LastIndexOf('.');
                        if (dot >= 0) n = n.Substring(dot + 1);
                        part.Shapes.Add((smr, s));
                        part.ShapeNames[(smr, s)] = n;
                    }
            }
            foreach (var p in part.Replaces) SetVisible(p, false);
            custom[slot] = part;
        }
        float tattooGlow;      // neutral (grey) iris, readable
        public GarmentTextures[] Garments = Array.Empty<GarmentTextures>();

        static readonly string[] ArmorPrefixes = { "Pauldron", "ChestPlate", "ChestRig", "KneePad", "ForearmGuard", "ShoulderR", "Interface" };
        static readonly int BaseColorId = Shader.PropertyToID("_BaseColor");
        static readonly int BaseMapId = Shader.PropertyToID("_BaseMap");
        static readonly int EmissionId = Shader.PropertyToID("_EmissionColor");

        readonly Dictionary<string, SkinnedMeshRenderer> byName = new();
        readonly Dictionary<string, List<(SkinnedMeshRenderer r, int index)>> shapeIndex = new();
        readonly Dictionary<string, Material> materials = new();
        readonly Dictionary<string, Texture2D> composited = new();
        readonly Dictionary<Material, Color> emissionBase = new();
        Appearance current;
        float blinkTimer = 2f, blinkPhase = -1f, talk, talkPhase, flash;
        readonly Dictionary<string, float> expressions = new();
        Texture2D eyeTex;

        public Appearance Current => current;

        /// <summary>Rendering layer bit for character-only lights (bit 1; bit 0 is Default).</summary>
        public const uint CharacterLayerMask = 1u << 1;

        void Awake()
        {
            if (Animator == null) Animator = GetComponentInChildren<Animator>();
            if (Renderers.Length == 0) Renderers = GetComponentsInChildren<SkinnedMeshRenderer>(true);
            foreach (var r in Renderers)
            {
                // Rendering layer 2 = "Characters": lit by the camera rig's character-only rim/fill lights.
                r.renderingLayerMask |= CharacterLayerMask;
                byName[r.name] = r;
                // Per-instance materials so tints never leak between characters.
                var mats = r.sharedMaterials;
                for (var i = 0; i < mats.Length; i++)
                {
                    if (mats[i] == null) continue;
                    if (!materials.TryGetValue(mats[i].name, out var inst))
                    {
                        inst = new Material(mats[i]) { name = mats[i].name };
                        materials[inst.name] = inst;
                        if (inst.HasProperty(EmissionId)) emissionBase[inst] = inst.GetColor(EmissionId);
                    }
                    mats[i] = inst;
                }
                r.sharedMaterials = mats;
                var mesh = r.sharedMesh;
                if (mesh == null) continue;
                for (var s = 0; s < mesh.blendShapeCount; s++)
                {
                    var n = mesh.GetBlendShapeName(s);
                    // FBX import may prefix shape names with the mesh name ("Body.m_jaw_incr").
                    var dot = n.LastIndexOf('.');
                    if (dot >= 0) n = n.Substring(dot + 1);
                    if (!shapeIndex.TryGetValue(n, out var list)) shapeIndex[n] = list = new List<(SkinnedMeshRenderer, int)>();
                    list.Add((r, s));
                }
            }
        }

        /// <summary>Enabled character models (for camera-proximity hiding).</summary>
        public static readonly List<CharacterModel> Active = new();
        bool cameraHidden;

        void OnEnable() => Active.Add(this);

        void OnDisable()
        {
            Active.Remove(this);
            if (cameraHidden) SetCameraHidden(false);
        }

        /// <summary>Hide/show every renderer of this character (body, gear, attachments) without touching visibility state.</summary>
        public void SetCameraHidden(bool hidden)
        {
            if (cameraHidden == hidden) return;
            cameraHidden = hidden;
            foreach (var r in GetComponentsInChildren<Renderer>(true)) r.forceRenderingOff = hidden;
        }

        void OnDestroy()
        {
            foreach (var m in materials.Values) Destroy(m);
            foreach (var cu in custom.Values) foreach (var m in cu.Materials) if (m != null) Destroy(m);
            foreach (var t in composited.Values) Destroy(t);
            if (eyeTex != null) Destroy(eyeTex);
        }

        public SkinnedMeshRenderer Part(string name) => byName.TryGetValue(name, out var r) ? r : null;
        public Material Mat(string name) => materials.TryGetValue(name, out var m) ? m : null;
        public Transform Bone(HumanBodyBones b) => Animator != null && Animator.isHuman ? Animator.GetBoneTransform(b) : null;

        /// <summary>Set a blendshape (0..1) on every mesh that has it.</summary>
        public void SetShape(string shape, float w01)
        {
            var w = Mathf.Clamp01(w01) * 100f;
            if (shapeIndex.TryGetValue(shape, out var list)) foreach (var (r, i) in list) r.SetBlendShapeWeight(i, w);
            foreach (var c in custom.Values)
                foreach (var (r, i) in c.Shapes)
                    if (r != null && c.ShapeNames[(r, i)] == shape) r.SetBlendShapeWeight(i, w);
        }

        void SetSigned(string morph, float v)
        {
            SetShape("m_" + morph + "_incr", Mathf.Max(0, v));
            SetShape("m_" + morph + "_decr", Mathf.Max(0, -v));
        }

        // ------------------------------------------------------------------ appearance

        public void ApplyAppearance(Appearance a)
        {
            current = a.Clone();
            var customHair = ApplyCustom(a);
            foreach (var m in Appearance.BodyMorphs) SetSigned(m, a.Get(m));
            foreach (var m in Appearance.FaceMorphs) if (m != "age") SetSigned(m, a.Get(m));
            SetShape("m_age_incr", a.Age);
            var h = 1f + Mathf.Clamp(a.Height, -1, 1) * 0.06f;
            transform.localScale = new Vector3(h, h, h);

            // Hair & facial hair: show one style.
            // "none" = shaved (no hair mesh); unknown ids fall back to the default style.
            var style = customHair || a.HairStyle == "none" ? null : Array.IndexOf(HairStyles, a.HairStyle) >= 0 ? a.HairStyle : DefaultHair;
            foreach (var s in HairStyles) SetVisible("Hair_" + s, s == style);
            foreach (var f in FacialHair) SetVisible("Facial_" + f, f == a.FacialHair);

            var hair = Appearance.ToColor(a.Hair);
            foreach (var s in HairStyles) Tint("Hair_" + s, hair);
            foreach (var f in FacialHair) Tint("Facial_" + f, hair);
            foreach (var cu in custom.Values)
                if (cu.Tint == "hair")
                    foreach (var m in cu.Materials) if (m.HasProperty(BaseColorId)) m.SetColor(BaseColorId, hair);
            // Brows a touch lighter than the hair (towards the skin) so they read as hair, not as painted blocks.
            var skinCol = Appearance.ToColor(a.Skin);
            Tint("Brows", Color.Lerp(hair, skinCol, 0.25f));
            Tint("Lashes", Color.Lerp(hair, Color.black, 0.35f));

            ApplySkin(Appearance.ToColor(a.Skin), a.Stubble);
            tattooColor = Appearance.ToColor(a.Tattoo);
            tattooGlow = a.TattooGlow;
            if (materials.TryGetValue("Skin", out var skinMat))
            {
                // Tattoo design from the catalog (ink as detail albedo ×2, glow as emission) or the model's own.
                var design = CustomCatalog.Get().Find("tattoos", CharacterId, a.TattooDesign);
                var ink = design?.Ink != null ? Resources.Load<Texture2D>("Characters/Custom/" + design.Ink) : null;
                activeTattoo = design?.Glow != null ? Resources.Load<Texture2D>("Characters/Custom/" + design.Glow) : TattooMap;
                if (skinMat.HasProperty("_DetailAlbedoMap"))
                {
                    skinMat.SetTexture("_DetailAlbedoMap", ink);
                    skinMat.SetFloat("_DetailAlbedoMapScale", 1f);
                    if (ink != null) skinMat.EnableKeyword("_DETAIL_MULX2"); else skinMat.DisableKeyword("_DETAIL_MULX2");
                }
                if (activeTattoo != null)
                {
                    skinMat.SetTexture("_EmissionMap", activeTattoo);
                    skinMat.EnableKeyword("_EMISSION");
                    skinMat.globalIlluminationFlags = MaterialGlobalIlluminationFlags.None;
                }
                else skinMat.SetColor(EmissionId, Color.black);
            }
            ApplyEyes(Appearance.ToColor(a.Eyes));

            // Outfit.
            var outfit = Appearance.ToColor(a.Outfit);
            var accent = Appearance.ToColor(a.Accent);
            var armor = Appearance.ToColor(a.Armor);
            var glow = Appearance.ToColor(a.Glow);
            var glow2 = Appearance.ToColor(a.Glow2);
            foreach (var g in Garments) CompositeGarment(g, g.Material == "Garment_Pants" ? Color.Lerp(outfit, Color.black, 0.12f) : outfit, accent);
            // Gloves stay neutral black-graphite (olive-tinted gloves read wrong against the concept designs).
            Tint("Gloves", new Color(0.36f, 0.36f, 0.37f));
            Tint("SuitSecondary", accent);
            Tint("Armor", armor);
            Glow("Glow", glow);
            Glow("Glow2", glow2);
            Glow("Screen", glow * 0.6f);
            Glow("Holo", glow);
            foreach (var r in Renderers)
            {
                var n = r.name;
                foreach (var p in ArmorPrefixes)
                {
                    if (!n.StartsWith(p)) continue;
                    var on = n.StartsWith("Pauldron") || n.StartsWith("ShoulderR") ? a.ShoulderPads
                        : n.StartsWith("ChestPlate") || n.StartsWith("ChestRig") ? a.ChestPlate
                        : n.StartsWith("KneePad") ? a.KneePads
                        : true;
                    r.gameObject.SetActive(on);
                }
                if (n == "Gloves") r.gameObject.SetActive(a.Gloves);
                if (n == "Harness" || n == "HipModule" || n == "ThighRig") r.gameObject.SetActive(a.Backpack);
                // Giva's built-in visor gives way to catalog eyewear.
                if (n == "Visor") r.gameObject.SetActive(!custom.ContainsKey("eyewear"));
            }
            // Parts replaced by an equipped armour set stay hidden.
            foreach (var cu in custom.Values) foreach (var p in cu.Replaces) SetVisible(p, false);
        }

        void SetVisible(string part, bool on)
        {
            if (byName.TryGetValue(part, out var r)) r.gameObject.SetActive(on);
        }

        void Tint(string material, Color c)
        {
            if (materials.TryGetValue(material, out var m) && m.HasProperty(BaseColorId)) m.SetColor(BaseColorId, c);
            foreach (var cu in custom.Values)
            {
                // Armour sets keep their designed colours (the outfit swatches tint the base outfit); glows still follow.
                if (cu.Slot == "armour") continue;
                foreach (var cm in cu.Materials)
                    if (cm.name == material && cm.HasProperty(BaseColorId)) cm.SetColor(BaseColorId, c);
            }
        }

        // Glows keep their hue: a dark base (no white diffuse) and moderate emission, so magenta reads hot pink and
        // cyan reads cyan through bloom and the tonemapper instead of washing out to pale pastel.
        // GlowEmission = level of the brightest channel in linear (see GlowEmissionColor), not a gamma multiplier.
        // Measured through the game's post stack (ACES + grading + bloom, emissive swatches): magenta stays saturated up
        // to ~1.6 ((230,69,216)) with a pink bloom halo above the 1.0 threshold; cyan bleaches from ~0.8 ((109,209,216)),
        // hence the second-channel cut below (cyan lands at ~0.45: (90,194,203) median on Kael's large sleeve panel).
        const float GlowBase = 0.15f, GlowEmission = 1.6f;

        /// <summary>
        /// Hue-preserving glow emission. Scaling the gamma colour (c * k through SetColor) put every channel far above 1
        /// in linear space (magenta x3 -> ~(13, 0.2, 9)), and ACES then bleached it to pale pink/white. Here the colour is
        /// taken to linear, its chroma raised (each channel relative to the brightest, to a power) and the brightest
        /// channel set to the emission level: bright enough for bloom, with the minor channels kept low so the
        /// tonemapper keeps the hue. Dimmer inputs (Screen = glow * 0.6) stay proportionally dimmer.
        /// </summary>
        static Color GlowEmissionColor(Color c, float level)
        {
            var lin = c.linear;
            var mx = Mathf.Max(lin.r, Mathf.Max(lin.g, lin.b));
            if (mx < 1e-4f) return Color.black;
            var bright = Mathf.Max(c.r, Mathf.Max(c.g, c.b));
            // violet / blue (blue leading, little green) needs extra chroma or the red share turns it lavender
            var k = GlowChroma + (lin.b >= mx && lin.g < 0.5f * lin.b ? 0.8f : 0f);
            float Ch(float v) => Mathf.Pow(Mathf.Clamp01(v / mx), k);
            float r = Ch(lin.r), g = Ch(lin.g), b = Ch(lin.b);
            // Two strong channels (cyan, yellow) bleach under ACES much sooner than one (magenta, violet): the second
            // channel's share lowers the level.
            var second = r + g + b - 1f - Mathf.Min(r, Mathf.Min(g, b));
            var lv = level * Mathf.Lerp(1f, 0.18f, Mathf.SmoothStep(0f, 1f, Mathf.Clamp01((second - 0.45f) / 0.3f)));
            var e = new Color(r, g, b, 1f) * (lv * bright);
            e.a = 1f;
            return e.gamma;                     // Material.SetColor converts gamma -> linear in this (linear) project
        }

        const float GlowChroma = 1.6f, HoloIntensity = 1.5f;

        void SetGlow(Material m, Color c)
        {
            if (m.HasProperty(BaseColorId)) m.SetColor(BaseColorId, c * GlowBase);
            if (m.HasProperty("_Smoothness")) m.SetFloat("_Smoothness", 0.35f);     // no white specular sheen on the light
            if (!m.HasProperty(EmissionId)) return;
            m.EnableKeyword("_EMISSION");
            // additive holo (EOA/HoloSleeve: _EmissionColor x _Intensity): scaled for this linear, hue-kept emission
            if (m.HasProperty("_Intensity")) m.SetFloat("_Intensity", HoloIntensity);
            var e = GlowEmissionColor(c, GlowEmission);
            m.SetColor(EmissionId, e);
            emissionBase[m] = e;
        }

        void Glow(string material, Color c)
        {
            foreach (var cu in custom.Values)
                foreach (var cm in cu.Materials)
                    if (cm.name == material) SetGlow(cm, c);
            if (materials.TryGetValue(material, out var m)) SetGlow(m, c);
        }

        void ApplySkin(Color skin, float stubble)
        {
            if (!materials.TryGetValue("Skin", out var m)) return;
            // Pick the closest base texture by brightness, then fine-tune with a tint.
            var lum = skin.r * 0.3f + skin.g * 0.59f + skin.b * 0.11f;
            float[] refs = { 0.78f, 0.62f, 0.5f, 0.3f };
            var best = 0;
            for (var i = 1; i < refs.Length; i++) if (Mathf.Abs(refs[i] - lum) < Mathf.Abs(refs[best] - lum)) best = i;
            if (SkinTones.Length > best && SkinTones[best] != null) m.SetTexture(BaseMapId, SkinTones[best]);
            var k = Mathf.Clamp(lum / refs[Mathf.Min(best, refs.Length - 1)], 0.75f, 1.25f);
            var tint = new Color(skin.r / Mathf.Max(0.05f, lum) * lum * k, skin.g / Mathf.Max(0.05f, lum) * lum * k, skin.b / Mathf.Max(0.05f, lum) * lum * k);
            tint = Color.Lerp(Color.white, tint / Mathf.Max(0.001f, tint.maxColorComponent) , 0.35f) * Mathf.Clamp(k, 0.85f, 1.1f);
            tint.a = 1;
            m.SetColor(BaseColorId, tint);
            // With the HD mask map, _Smoothness scales the per-pixel smoothness (A channel) instead of setting it.
            m.SetFloat("_Smoothness", m.IsKeywordEnabled("_METALLICSPECGLOSSMAP") ? 1.05f - stubble * 0.1f : 0.38f + stubble * 0.02f);
        }

        void ApplyEyes(Color iris)
        {
            if (!materials.TryGetValue("Eyes", out var m) || EyeTexture == null || !EyeTexture.isReadable) return;
            // Tint the iris only: pixels near the centre of the equirectangular eye texture.
            var src = EyeTexture.GetPixels32();
            var w = EyeTexture.width; var h = EyeTexture.height;
            if (eyeTex == null) eyeTex = new Texture2D(w, h, TextureFormat.RGBA32, true) { name = name + "_Eye", wrapMode = TextureWrapMode.Clamp };
            var dst = new Color32[src.Length];
            for (var y = 0; y < h; y++)
            for (var x = 0; x < w; x++)
            {
                var i = y * w + x;
                var c = src[i];
                // Iris region: low saturation grey texture -> distance from texture centre in angle space.
                var dx = (x + 0.5f) / w - 0.5f; var dy = (y + 0.5f) / h - 0.5f;
                var d = Mathf.Sqrt(dx * dx * 4 + dy * dy);
                var irisK = 1 - Mathf.SmoothStep(0.075f, 0.095f, d);
                var lum = (c.r + c.g + c.b) / (3f * 255f);
                var tinted = new Color(iris.r * lum * 1.45f, iris.g * lum * 1.45f, iris.b * lum * 1.45f);
                var o = Color.Lerp(new Color(c.r / 255f, c.g / 255f, c.b / 255f), tinted, irisK);
                dst[i] = new Color32((byte)(Mathf.Clamp01(o.r) * 255), (byte)(Mathf.Clamp01(o.g) * 255), (byte)(Mathf.Clamp01(o.b) * 255), 255);
            }
            eyeTex.SetPixels32(dst);
            eyeTex.Apply(true);
            m.SetTexture(BaseMapId, eyeTex);
        }

        void CompositeGarment(GarmentTextures g, Color primary, Color secondary)
        {
            if (g.Mask == null || !g.Mask.isReadable || !materials.TryGetValue(g.Material, out var m)) return;
            var src = g.Mask.GetPixels32();
            if (!composited.TryGetValue(g.Material, out var tex))
            {
                tex = new Texture2D(g.Mask.width, g.Mask.height, TextureFormat.RGBA32, true) { name = name + "_" + g.Material, anisoLevel = 4 };
                composited[g.Material] = tex;
            }
            var trim = new Color(0.54f, 0.56f, 0.59f);
            var p = (Color32)primary; var s = (Color32)secondary; var t = (Color32)trim;
            var dst = new Color32[src.Length];
            for (var i = 0; i < src.Length; i++)
            {
                var c = src[i];
                int r = p.r + (s.r - p.r) * c.r / 255, gg = p.g + (s.g - p.g) * c.r / 255, b = p.b + (s.b - p.b) * c.r / 255;
                r += (t.r - r) * c.g / 255; gg += (t.g - gg) * c.g / 255; b += (t.b - b) * c.g / 255;
                var seam = 255 - c.a * 140 / 255;
                // Alpha carries smoothness: trim is glossy, fabric matte, seams rougher.
                var smooth = (byte)Mathf.Clamp(70 + c.g * 110 / 255 - c.a * 40 / 255, 0, 255);
                dst[i] = new Color32((byte)(r * seam / 255), (byte)(gg * seam / 255), (byte)(b * seam / 255), smooth);
            }
            tex.SetPixels32(dst);
            tex.Apply(true);
            m.SetTexture(BaseMapId, tex);
            m.SetColor(BaseColorId, Color.white);
            if (g.Normal != null)
            {
                m.SetTexture("_BumpMap", g.Normal);
                m.EnableKeyword("_NORMALMAP");
            }
            // Smoothness from base-map alpha.
            m.SetFloat("_SmoothnessTextureChannel", 1);
            m.EnableKeyword("_SMOOTHNESS_TEXTURE_ALBEDO_CHANNEL_A");
            m.SetFloat("_Smoothness", 0.9f);
        }

        // ------------------------------------------------------------------ face & effects

        public void SetExpression(string name, float w) => expressions[name] = Mathf.Clamp01(w);

        /// <summary>Talking amount 0..1 (mouth flap while a line is spoken/shown).</summary>
        public float Talk { get => talk; set => talk = Mathf.Clamp01(value); }

        public void HitFlash(float strength = 1) => flash = Mathf.Max(flash, strength);

        public void SetEcho(bool on, Color tint)
        {
            Echo = on;
            foreach (var m in materials.Values)
            {
                if (!on) continue;
                // URP Lit transparent setup.
                m.SetFloat("_Surface", 1);
                m.SetFloat("_Blend", 1); // additive-ish via premultiply
                m.SetOverrideTag("RenderType", "Transparent");
                m.SetInt("_SrcBlend", (int)UnityEngine.Rendering.BlendMode.One);
                m.SetInt("_DstBlend", (int)UnityEngine.Rendering.BlendMode.One);
                m.SetInt("_ZWrite", 0);
                m.EnableKeyword("_SURFACE_TYPE_TRANSPARENT");
                m.renderQueue = (int)UnityEngine.Rendering.RenderQueue.Transparent;
                if (m.HasProperty(BaseColorId)) m.SetColor(BaseColorId, tint * 0.35f);
                if (m.HasProperty(EmissionId)) { m.EnableKeyword("_EMISSION"); m.SetColor(EmissionId, tint * 0.6f); emissionBase[m] = tint * 0.6f; }
            }
        }

        void LateUpdate()
        {
            var dt = Time.deltaTime;
            // Tattoo glow: slow breathing pulse.
            if (activeTattoo != null && materials.TryGetValue("Skin", out var sm))
                sm.SetColor(EmissionId, FxMaterials.Hdr(tattooColor, 2.6f * tattooGlow * (0.72f + 0.28f * Mathf.Sin(Time.time * 1.7f))));
            // Blinking.
            blinkTimer -= dt;
            if (blinkTimer <= 0 && blinkPhase < 0) { blinkPhase = 0; blinkTimer = UnityEngine.Random.Range(2.2f, 5.5f); }
            var blink = 0f;
            if (blinkPhase >= 0)
            {
                blinkPhase += dt / 0.16f;
                blink = blinkPhase < 0.5f ? blinkPhase * 2 : Mathf.Max(0, 2 - blinkPhase * 2);
                if (blinkPhase >= 1) blinkPhase = -1;
            }
            expressions.TryGetValue("blink", out var forcedBlink);
            SetShape("x_blink_L", Mathf.Max(blink, forcedBlink));
            SetShape("x_blink_R", Mathf.Max(blink, forcedBlink));
            // Talking: irregular mouth open/close while talk > 0.
            if (talk > 0)
            {
                talkPhase += dt * 11f;
                var open = (Mathf.Sin(talkPhase) * 0.5f + 0.5f) * (0.55f + 0.45f * Mathf.PerlinNoise(talkPhase * 0.31f, 0.7f)) * talk;
                SetShape("x_mouthOpen", Mathf.Max(open, expressions.TryGetValue("mouthOpen", out var mo) ? mo : 0));
            }
            else SetShape("x_mouthOpen", expressions.TryGetValue("mouthOpen", out var mo2) ? mo2 : 0);
            foreach (var kv in expressions)
                if (kv.Key != "blink" && kv.Key != "mouthOpen") SetShape("x_" + kv.Key, kv.Value);
            // Hit flash via emission boost.
            if (flash > 0)
            {
                flash = Mathf.Max(0, flash - dt * 6);
                foreach (var kv in emissionBase)
                    kv.Key.SetColor(EmissionId, kv.Value + new Color(1f, 0.55f, 0.4f) * flash * 0.8f);
            }
        }
    }

    /// <summary>Persists the protagonists' appearance between sessions (menus and new games).</summary>
    public sealed class AppearanceStore
    {
        readonly Dictionary<string, Appearance> data = new();
        readonly string path;

        public AppearanceStore(string dir = null)
        {
            path = System.IO.Path.Combine(dir ?? Application.persistentDataPath, "appearance.json");
            try
            {
                if (System.IO.File.Exists(path))
                {
                    var d = Newtonsoft.Json.JsonConvert.DeserializeObject<Dictionary<string, Appearance>>(System.IO.File.ReadAllText(path), GameData.Json);
                    if (d != null) foreach (var kv in d) if (kv.Value != null) data[kv.Key] = kv.Value.Sanitized(Appearance.Default(kv.Key));
                }
            }
            catch (Exception e) { Debug.LogWarning($"[appearance] stored appearance unreadable: {e.Message}"); }
        }

        public Appearance Get(string character) => data.TryGetValue(character, out var a) ? a.Clone() : Appearance.Default(character);

        public void Set(string character, Appearance a)
        {
            data[character] = a.Clone();
            try { SafeFile.WriteAtomic(path, Newtonsoft.Json.JsonConvert.SerializeObject(data, GameData.Json)); }
            catch (Exception e) { Debug.LogWarning($"[appearance] save failed: {e.Message}"); }
        }

        public void Reset(string character)
        {
            data.Remove(character);
            Set(character, Appearance.Default(character));
        }
    }
}
