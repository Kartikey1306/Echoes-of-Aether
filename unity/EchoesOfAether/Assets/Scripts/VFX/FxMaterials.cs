using UnityEngine;
using UnityEngine.Rendering;

namespace EOA
{
    /// <summary>
    /// Runtime material / texture factory for URP. Everything is created in code; if template materials exist in
    /// Resources they are cloned instead (recommended for builds so the needed shader variants are not stripped):
    ///   Resources/VFX/Particle_Additive.mat, Resources/VFX/Particle_Alpha.mat  (URP Particles/Unlit)
    ///   Resources/VFX/Lit.mat (URP Lit, emission on), Resources/VFX/Unlit.mat (URP Unlit)
    /// </summary>
    public static class FxMaterials
    {
        static Shader particleShader, litShader, unlitShader;
        static Texture2D softDot, glow, smoke, beam, white;

        // ------------------------------------------------------------------ Shaders

        static Shader Find(params string[] names)
        {
            foreach (var n in names)
            {
                var s = Shader.Find(n);
                if (s != null) return s;
            }
            Debug.LogWarning("[vfx] none of the shaders found: " + string.Join(", ", names));
            return null;
        }

        public static Shader ParticleShader => particleShader != null ? particleShader : particleShader = Find("Universal Render Pipeline/Particles/Unlit", "Particles/Standard Unlit", "Sprites/Default");
        public static Shader LitShader => litShader != null ? litShader : litShader = Find("Universal Render Pipeline/Lit", "Universal Render Pipeline/Simple Lit", "Standard");
        public static Shader UnlitShader => unlitShader != null ? unlitShader : unlitShader = Find("Universal Render Pipeline/Unlit", "Unlit/Color", "Sprites/Default");

        static Material FromTemplate(string resource, Shader fallback)
        {
            var tmpl = Resources.Load<Material>(resource);
            if (tmpl != null) return new Material(tmpl);
            return new Material(fallback != null ? fallback : Shader.Find("Sprites/Default"));
        }

        // ------------------------------------------------------------------ Colour helpers

        /// <summary>
        /// HDR colour for Material.SetColor such that the shader receives linear(srgb) * intensity
        /// (matches three.js `color.setHex(c).multiplyScalar(k)` emissive/basic materials).
        /// </summary>
        public static Color Hdr(Color srgb, float intensity)
        {
            Color lin = srgb.linear * intensity;
            Color g = lin.gamma;
            g.a = srgb.a;
            return g;
        }

        // ------------------------------------------------------------------ Materials

        /// <summary>Transparent URP particle material (additive or alpha blended). Vertex colours multiply _BaseColor.</summary>
        public static Material Particle(bool additive, Texture tex, bool doubleSided = false)
        {
            var m = FromTemplate(additive ? "VFX/Particle_Additive" : "VFX/Particle_Alpha", ParticleShader);
            m.name = additive ? "fx_additive" : "fx_alpha";
            SetTransparent(m, true, additive);
            m.SetFloat("_Cull", doubleSided ? (float)CullMode.Off : (float)CullMode.Back);
            m.SetFloat("_ColorMode", 0f);
            if (tex != null)
            {
                m.SetTexture("_BaseMap", tex);
                if (m.HasProperty("_MainTex")) m.SetTexture("_MainTex", tex);
            }
            m.SetColor("_BaseColor", Color.white);
            return m;
        }

        /// <summary>URP Lit material (robot shell/frame/joint). Emission keyword is enabled so hit flashes can drive _EmissionColor.</summary>
        public static Material Lit(Color color, float metallic, float smoothness, string name = "robot_lit")
        {
            var m = FromTemplate("VFX/Lit", LitShader);
            m.name = name;
            m.SetColor("_BaseColor", color);
            if (m.HasProperty("_Color")) m.SetColor("_Color", color);
            m.SetFloat("_Metallic", metallic);
            m.SetFloat("_Smoothness", smoothness);
            if (m.HasProperty("_Glossiness")) m.SetFloat("_Glossiness", smoothness);
            m.EnableKeyword("_EMISSION");
            m.SetColor("_EmissionColor", Color.black);
            m.globalIlluminationFlags = MaterialGlobalIlluminationFlags.None;
            return m;
        }

        /// <summary>URP Unlit material (glow parts, bolt cores). Use <see cref="Hdr"/> for bright colours.</summary>
        public static Material Unlit(Color color, string name = "fx_unlit")
        {
            var m = FromTemplate("VFX/Unlit", UnlitShader);
            m.name = name;
            m.SetColor("_BaseColor", color);
            if (m.HasProperty("_Color")) m.SetColor("_Color", color);
            return m;
        }

        /// <summary>
        /// Switch a URP Lit/Unlit/Particles material between opaque and transparent at runtime
        /// (stalker phasing). `additive` only applies when transparent.
        /// </summary>
        public static void SetTransparent(Material m, bool transparent, bool additive = false, bool zwrite = false)
        {
            if (m == null) return;
            if (transparent)
            {
                m.SetFloat("_Surface", 1f);
                m.SetFloat("_Blend", additive ? 2f : 0f);
                m.SetFloat("_SrcBlend", (float)BlendMode.SrcAlpha);
                m.SetFloat("_DstBlend", additive ? (float)BlendMode.One : (float)BlendMode.OneMinusSrcAlpha);
                m.SetFloat("_SrcBlendAlpha", (float)BlendMode.One);
                m.SetFloat("_DstBlendAlpha", additive ? (float)BlendMode.One : (float)BlendMode.OneMinusSrcAlpha);
                m.SetFloat("_ZWrite", zwrite ? 1f : 0f);
                m.EnableKeyword("_SURFACE_TYPE_TRANSPARENT");
                m.DisableKeyword("_ALPHAPREMULTIPLY_ON");
                m.DisableKeyword("_ALPHAMODULATE_ON");
                m.SetOverrideTag("RenderType", "Transparent");
                m.renderQueue = (int)RenderQueue.Transparent;
                m.SetShaderPassEnabled("ShadowCaster", false);
            }
            else
            {
                m.SetFloat("_Surface", 0f);
                m.SetFloat("_Blend", 0f);
                m.SetFloat("_SrcBlend", (float)BlendMode.One);
                m.SetFloat("_DstBlend", (float)BlendMode.Zero);
                m.SetFloat("_SrcBlendAlpha", (float)BlendMode.One);
                m.SetFloat("_DstBlendAlpha", (float)BlendMode.Zero);
                m.SetFloat("_ZWrite", 1f);
                m.DisableKeyword("_SURFACE_TYPE_TRANSPARENT");
                m.SetOverrideTag("RenderType", "Opaque");
                m.renderQueue = -1;
                m.SetShaderPassEnabled("ShadowCaster", true);
            }
        }

        /// <summary>Set _BaseColor alpha without touching rgb.</summary>
        public static void SetAlpha(Material m, float a)
        {
            if (m == null) return;
            var c = m.GetColor("_BaseColor");
            c.a = a;
            m.SetColor("_BaseColor", c);
        }

        // ------------------------------------------------------------------ Procedural textures

        public static Texture2D White => white != null ? white : white = Make(4, (x, y) => new Color32(255, 255, 255, 255), "fx_white");

        /// <summary>Soft round particle (sparks, embers, motes).</summary>
        public static Texture2D SoftDot => softDot != null ? softDot : softDot = Make(64, (x, y) =>
        {
            float r = Radius(x, y, 64);
            float a = Mathf.Clamp01(1f - r);
            a = a * a * (3f - 2f * a);
            return new Color32(255, 255, 255, (byte)(a * 255f));
        }, "fx_softdot");

        /// <summary>Glow sprite (port of the prototype's radial gradient: 1 / .55 / .12 / 0 at 0 / .25 / .6 / 1).</summary>
        public static Texture2D Glow => glow != null ? glow : glow = Make(128, (x, y) =>
        {
            float r = Radius(x, y, 128);
            float a = r < 0.25f ? Mathf.Lerp(1f, 0.55f, r / 0.25f)
                    : r < 0.6f ? Mathf.Lerp(0.55f, 0.12f, (r - 0.25f) / 0.35f)
                    : r < 1f ? Mathf.Lerp(0.12f, 0f, (r - 0.6f) / 0.4f) : 0f;
            return new Color32(255, 255, 255, (byte)(a * 255f));
        }, "fx_glow");

        /// <summary>Soft noisy smoke puff.</summary>
        public static Texture2D Smoke => smoke != null ? smoke : smoke = Make(64, (x, y) =>
        {
            float r = Radius(x, y, 64);
            float n = Mathf.PerlinNoise(x * 0.11f + 3.1f, y * 0.11f + 7.7f) * 0.6f + Mathf.PerlinNoise(x * 0.27f + 11f, y * 0.27f + 5f) * 0.4f;
            float a = Mathf.Clamp01(1f - r);
            a = a * a * (0.55f + 0.45f * n);
            return new Color32(255, 255, 255, (byte)(Mathf.Clamp01(a * 1.3f) * 255f));
        }, "fx_smoke");

        /// <summary>Beam cross-section (bright centre line, soft edges along V).</summary>
        public static Texture2D BeamTexture => beam != null ? beam : beam = Make(32, (x, y) =>
        {
            float v = Mathf.Abs((y + 0.5f) / 32f * 2f - 1f);
            float a = Mathf.Clamp01(1f - v);
            a = Mathf.Pow(a, 1.6f);
            return new Color32(255, 255, 255, (byte)(a * 255f));
        }, "fx_beam");

        static float Radius(int x, int y, int size)
        {
            float h = size * 0.5f;
            float dx = (x + 0.5f - h) / h, dy = (y + 0.5f - h) / h;
            return Mathf.Sqrt(dx * dx + dy * dy);
        }

        static Texture2D Make(int size, System.Func<int, int, Color32> f, string name)
        {
            var t = new Texture2D(size, size, TextureFormat.RGBA32, true)
            {
                name = name,
                wrapMode = TextureWrapMode.Clamp,
                filterMode = FilterMode.Bilinear,
                anisoLevel = 0,
            };
            var px = new Color32[size * size];
            for (int y = 0; y < size; y++)
                for (int x = 0; x < size; x++)
                    px[y * size + x] = f(x, y);
            t.SetPixels32(px);
            t.Apply(true, true);
            return t;
        }
    }
}
