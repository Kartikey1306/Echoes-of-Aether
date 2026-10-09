using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace EOA
{
    /// <summary>
    /// Runtime access to the Blender-built weapon assets (blender/weapons → Resources/Weapons):
    /// <list type="bullet">
    /// <item>PBR weapon models (kael_pistol, kael_holster, kael_emitter, giva_gauntlet, energy_cell, drone_blaster,
    /// sentinel_blade, guardian_weapons): two material slots each, the baked atlas ("*_pbr", URP Lit) and the glow
    /// parts ("*_glow"), plus anchor empties (muzzle, eject, blade_root, claw_N, palm, tip).</item>
    /// <item>Hard-light / FX meshes in weapon_fx (blade hull/core, claw hull/core, bolt hull/core, muzzle_flash,
    /// impact_burst) shaded by EOA/HardLight.</item>
    /// </list>
    /// Everything loads once and is cached; instancing a weapon clones the prefab and gives it its own glow material
    /// so each weapon can pulse independently. Missing assets degrade to null (callers fall back to the old FX).
    /// </summary>
    public static class WeaponLibrary
    {
        static readonly Dictionary<string, GameObject> prefabs = new();
        static Dictionary<string, Mesh> fxMeshes;
        static Material hardLightTemplate;
        static Shader hardLightShader;
        public static readonly int ColorId = Shader.PropertyToID("_Color"), CoreColorId = Shader.PropertyToID("_CoreColor"),
            IntensityId = Shader.PropertyToID("_Intensity"), AlphaId = Shader.PropertyToID("_Alpha"), ExtendId = Shader.PropertyToID("_Extend"),
            ModeId = Shader.PropertyToID("_Mode"), SeedId = Shader.PropertyToID("_Seed"), CullId = Shader.PropertyToID("_Cull"),
            BaseColorId = Shader.PropertyToID("_BaseColor"), EmissionColorId = Shader.PropertyToID("_EmissionColor"),
            EdgeBoostId = Shader.PropertyToID("_EdgeBoost"), FlowId = Shader.PropertyToID("_Flow"), FresnelId = Shader.PropertyToID("_Fresnel");

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void ResetStatics()
        {
            prefabs.Clear();
            fxMeshes = null;
            hardLightTemplate = null;
            hardLightShader = null;
        }

        public static GameObject Prefab(string name)
        {
            if (prefabs.TryGetValue(name, out var p)) return p;
            p = Resources.Load<GameObject>("Weapons/" + name);
            if (p == null) Debug.LogWarning("[weapons] missing Resources/Weapons/" + name);
            prefabs[name] = p;
            return p;
        }

        /// <summary>Hard-light / FX mesh by name (weapon_fx.fbx), or null.</summary>
        public static Mesh FxMesh(string name)
        {
            if (fxMeshes == null)
            {
                fxMeshes = new Dictionary<string, Mesh>();
                var go = Prefab("weapon_fx");
                if (go != null)
                {
                    // Meshes are used on our own transforms: bake any node transform the importer kept (e.g. an axis
                    // conversion rotation or unit scale) so the vertex data is in the authored weapon space.
                    foreach (var mf in go.GetComponentsInChildren<MeshFilter>(true))
                        if (mf.sharedMesh != null) fxMeshes[mf.gameObject.name] = Baked(mf.sharedMesh, go.transform.worldToLocalMatrix * mf.transform.localToWorldMatrix);
                    var r = go.GetComponentInChildren<Renderer>(true);
                    if (r != null && r.sharedMaterial != null && r.sharedMaterial.shader != null && r.sharedMaterial.shader.name == "EOA/HardLight")
                        hardLightTemplate = r.sharedMaterial;
                }
            }
            return fxMeshes.TryGetValue(name, out var m) ? m : null;
        }

        static readonly List<Mesh> bakedMeshes = new();

        static Mesh Baked(Mesh src, Matrix4x4 m)
        {
            if (IsIdentity(m)) return src;
            if (!src.isReadable)
            {
                Debug.LogWarning($"[weapons] {src.name}: node transform not identity and mesh not readable; using it as is");
                return src;
            }
            var mesh = Object.Instantiate(src);
            mesh.name = src.name;
            var v = mesh.vertices;
            var n = mesh.normals;
            var t = mesh.tangents;
            var nm = m.inverse.transpose;
            for (int i = 0; i < v.Length; i++) v[i] = m.MultiplyPoint3x4(v[i]);
            for (int i = 0; i < n.Length; i++) n[i] = nm.MultiplyVector(n[i]).normalized;
            for (int i = 0; i < t.Length; i++)
            {
                var d = m.MultiplyVector(new Vector3(t[i].x, t[i].y, t[i].z)).normalized;
                t[i] = new Vector4(d.x, d.y, d.z, t[i].w);
            }
            mesh.vertices = v;
            if (n.Length == v.Length) mesh.normals = n;
            if (t.Length == v.Length) mesh.tangents = t;
            mesh.RecalculateBounds();
            bakedMeshes.Add(mesh);
            return mesh;
        }

        static bool IsIdentity(Matrix4x4 m)
        {
            for (int r = 0; r < 4; r++)
                for (int c = 0; c < 4; c++)
                    if (Mathf.Abs(m[r, c] - (r == c ? 1f : 0f)) > 1e-4f) return false;
            return true;
        }

        /// <summary>New EOA/HardLight material (mode 0 hull, 1 core, 2 projectile, 3 burst).</summary>
        public static Material HardLight(Color color, Color core, float intensity, int mode, bool doubleSided = false)
        {
            FxMesh("_");
            Material m;
            if (hardLightTemplate != null) m = new Material(hardLightTemplate);
            else
            {
                hardLightShader ??= Shader.Find("EOA/HardLight");
                if (hardLightShader == null) return null;
                m = new Material(hardLightShader);
            }
            m.name = "fx_hardlight_" + mode;
            m.SetColor(ColorId, color);
            m.SetColor(CoreColorId, core);
            m.SetFloat(IntensityId, intensity);
            m.SetFloat(ModeId, mode);
            m.SetFloat(AlphaId, 1f);
            m.SetFloat(ExtendId, 1f);
            m.SetFloat(SeedId, Random.value * 10f);
            m.SetFloat(CullId, doubleSided ? (float)CullMode.Off : (float)CullMode.Back);
            return m;
        }

        /// <summary>
        /// Instantiate a weapon model under `parent`. Renderers get the character light layer (so rim lights catch the
        /// metal), shadows (small parts none) and a per-instance clone of the glow material, returned in `glow`
        /// (null if the model has no glow slot). The robot variant passes `robotGlow` to share the robot's own glow.
        /// </summary>
        public static GameObject Spawn(string name, Transform parent, int layer, out Material glow, Material robotGlow = null, bool shadows = true, string child = null,
            bool characterLight = true)
        {
            glow = null;
            var prefab = Prefab(name);
            if (prefab == null) return null;
            // The returned object is a pivot in the authored weapon space (x right, y up, z forward); the imported
            // model keeps whatever node transform the FBX importer gave it underneath, so callers can freely place the
            // pivot without losing an axis conversion.
            var go = new GameObject(child ?? name);
            go.transform.SetParent(parent, false);
            if (child != null)
            {
                var src = FindDeep(prefab.transform, child);
                if (src == null) { Object.Destroy(go); return null; }
                var inst = Object.Instantiate(src.gameObject, go.transform, false);
                // child of the file root: keep its transform relative to that root
                var rel = prefab.transform.worldToLocalMatrix * src.localToWorldMatrix;
                inst.transform.localPosition = rel.GetColumn(3);
                inst.transform.localRotation = rel.rotation;
                inst.transform.localScale = rel.lossyScale;
                inst.name = child + "_model";
            }
            else
            {
                var inst = Object.Instantiate(prefab, go.transform, false);
                inst.transform.localPosition = prefab.transform.localPosition;
                inst.transform.localRotation = prefab.transform.localRotation;
                inst.transform.localScale = prefab.transform.localScale;
                inst.name = name + "_model";
            }
            Material shared = null;
            foreach (var r in go.GetComponentsInChildren<Renderer>(true))
            {
                r.gameObject.layer = layer;
                if (characterLight) r.renderingLayerMask |= CharacterModel.CharacterLayerMask;
                r.shadowCastingMode = shadows ? ShadowCastingMode.On : ShadowCastingMode.Off;
                r.lightProbeUsage = LightProbeUsage.BlendProbes;
                var mats = r.sharedMaterials;
                for (int i = 0; i < mats.Length; i++)
                {
                    var m = mats[i];
                    if (m == null || !m.name.EndsWith("_glow")) continue;
                    if (robotGlow != null) mats[i] = robotGlow;
                    else
                    {
                        if (shared == null)
                        {
                            shared = new Material(m) { name = m.name + "_inst" };
                            glow = shared;
                        }
                        mats[i] = shared;
                    }
                }
                r.sharedMaterials = mats;
            }
            foreach (var t in go.GetComponentsInChildren<Transform>(true)) t.gameObject.layer = layer;
            return go;
        }

        /// <summary>Depth-first search by name; "name.001"-style duplicate suffixes from Blender also match.</summary>
        public static Transform FindDeep(Transform root, string name)
        {
            if (root == null) return null;
            var n = root.name;
            if (n == name || (n.Length > name.Length && n.StartsWith(name) && n[name.Length] == '.')) return root;
            for (int i = 0; i < root.childCount; i++)
            {
                var r = FindDeep(root.GetChild(i), name);
                if (r != null) return r;
            }
            return null;
        }

        /// <summary>Set an HDR glow on a URP Unlit/Lit glow material (base colour for Unlit, emission for Lit).</summary>
        public static void SetGlow(Material m, Color srgb, float intensity)
        {
            if (m == null) return;
            var c = FxMaterials.Hdr(srgb, intensity);
            if (m.HasProperty(BaseColorId)) m.SetColor(BaseColorId, c);
            if (m.HasProperty(EmissionColorId)) m.SetColor(EmissionColorId, c);
        }

        /// <summary>Renderer with a MeshFilter for an FX mesh (hard-light), hidden until used.</summary>
        public static MeshRenderer FxRenderer(string name, Mesh mesh, Material mat, Transform parent, int layer)
        {
            var go = new GameObject(name);
            go.layer = layer;
            go.transform.SetParent(parent, false);
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var mr = go.AddComponent<MeshRenderer>();
            mr.sharedMaterial = mat;
            mr.shadowCastingMode = ShadowCastingMode.Off;
            mr.receiveShadows = false;
            mr.lightProbeUsage = LightProbeUsage.Off;
            mr.reflectionProbeUsage = ReflectionProbeUsage.Off;
            return mr;
        }

        /// <summary>Accessibility flash scale (Settings → Accessibility → flash intensity).</summary>
        public static float FlashScale => Mathf.Clamp01(G.Settings?.Data?.Accessibility?.FlashIntensity ?? 1f);
    }
}
