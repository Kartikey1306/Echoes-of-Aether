using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace EOA
{
    /// <summary>
    /// Environment material library. Names are the Blender-baked PBR set (Art/Environment/Textures, see
    /// ENV_ASSETS.md); the prototype's material names are accepted too and mapped. The editor step
    /// (EOA/Setup Project → Environment) writes URP Lit materials to Resources/Env/Materials/&lt;name&gt;.mat with
    /// world-scale tiling (1 UV unit = 1 m, tiling = 1 / tile size). Without them a flat-colour fallback is built
    /// so zones always render.
    /// </summary>
    public static class EnvMaterials
    {
        /// <summary>Prototype MatName → environment material (mirrors PROTO_MAP in blender/env/matdefs.py).</summary>
        static readonly Dictionary<string, string> ProtoMap = new()
        {
            ["concrete"] = "concrete", ["curb"] = "concrete", ["concrete_dark"] = "concrete_dark", ["concrete_wet"] = "concrete_wet",
            ["asphalt"] = "asphalt", ["paving"] = "paving", ["plaster"] = "plaster", ["brick"] = "brick",
            ["metal"] = "metal_bare", ["metal_dark"] = "metal_dark", ["metal_painted"] = "metal_painted", ["metal_red"] = "metal_painted_red",
            ["metal_yellow"] = "metal_painted_yellow", ["rust"] = "metal_rusted", ["grate"] = "grating",
            ["tile_lab"] = "metro_tile", ["floor_lab"] = "lab_floor", ["panel_lab"] = "lab_panel",
            ["glass"] = "glass", ["glass_dark"] = "glass_dark", ["rubber"] = "rubber", ["wood"] = "wood", ["tarp"] = "tarp", ["tarp_blue"] = "tarp_blue",
            ["emit_cyan"] = "emit_cyan", ["emit_violet"] = "emit_violet", ["emit_warm"] = "emit_panel_warm", ["emit_red"] = "emit_red",
            ["emit_white"] = "emit_white", ["emit_amber"] = "emit_amber", ["emit_green"] = "emit_green",
            ["win_warm"] = "window_lit_warm", ["win_cool"] = "window_lit_cool", ["water"] = "water", ["aether"] = "aether_energy",
            ["black"] = "black", ["screen"] = "screen", ["vehicle"] = "car_paint_grey", ["vehicle_dark"] = "car_paint_dark", ["rock"] = "concrete_dark",
            ["cable"] = "rubber",
        };

        // Fallback look: sRGB base colour, metallic, smoothness, emission (sRGB) and intensity.
        struct Look { public Color C; public float M, S; public Color E; public float EI; public bool Transparent, Additive; }

        static Look L(uint c, double m, double s) => new() { C = ProtoSpace.Hex(c), M = (float)m, S = (float)s };
        static Look Em(uint c, float intensity) => new() { C = ProtoSpace.Hex(c) * 0.25f, S = 0.6f, E = ProtoSpace.Hex(c), EI = intensity };

        static readonly Dictionary<string, Look> Fallback = new()
        {
            ["concrete"] = L(0x8a8a88, 0, 0.12), ["concrete_dark"] = L(0x4a4e53, 0, 0.12), ["concrete_wet"] = L(0x55595c, 0, 0.55),
            ["asphalt"] = L(0x2b2d30, 0, 0.35), ["paving"] = L(0x6f6e6a, 0, 0.3), ["plaster"] = L(0x9a968e, 0, 0.1), ["brick"] = L(0x6e4436, 0, 0.12),
            ["gravel"] = L(0x5f5d58, 0, 0.1),
            ["metal_painted"] = L(0x3a4a52, 0.35, 0.45), ["metal_painted_red"] = L(0x6e1f17, 0.3, 0.45), ["metal_painted_yellow"] = L(0xb08a1c, 0.3, 0.45),
            ["metal_painted_white"] = L(0xbfc2c0, 0.3, 0.45), ["metal_painted_green"] = L(0x3b4733, 0.3, 0.45), ["metal_dark"] = L(0x2a2d31, 0.45, 0.45),
            ["metal_bare"] = L(0x8c8f93, 0.85, 0.55), ["metal_rusted"] = L(0x6a3d24, 0.35, 0.2), ["metal_plate"] = L(0x3c4045, 0.7, 0.45),
            ["corrugated"] = L(0x70757a, 0.6, 0.4), ["grating"] = L(0x50545a, 0.8, 0.45),
            ["metro_tile"] = L(0xc9cbc6, 0, 0.7), ["lab_panel"] = L(0xa3a7ab, 0.2, 0.55), ["lab_floor"] = L(0x5d6166, 0.05, 0.45),
            ["rubber"] = L(0x141414, 0, 0.2), ["tarp"] = L(0x3a3e33, 0, 0.15), ["tarp_blue"] = L(0x22374f, 0, 0.15), ["wood"] = L(0x6b4b2e, 0, 0.2),
            ["car_paint_grey"] = L(0x5a6068, 0.6, 0.65), ["car_paint_dark"] = L(0x23272c, 0.5, 0.55), ["car_paint_red"] = L(0x6a1b15, 0.5, 0.6),
            ["car_paint_white"] = L(0xb3b7b6, 0.5, 0.6),
            ["glass"] = new Look { C = new Color(0.56f, 0.71f, 0.78f, 0.22f), S = 0.95f, Transparent = true },
            ["glass_dark"] = L(0x0b1218, 0.6, 0.92), ["plastic_dark"] = L(0x101112, 0, 0.45), ["plastic_orange"] = L(0xbf3308, 0, 0.45),
            ["black"] = L(0x050505, 0, 0.1),
            ["water"] = new Look { C = new Color(0.04f, 0.078f, 0.094f, 0.85f), M = 0.2f, S = 0.94f, Transparent = true },
            // Rain puddles: a thin, mostly clear film over the wet paving, so the ground's screen-space reflections show
            // through and the film adds its own sharp highlights (the opaque water look read as flat black holes).
            ["puddle"] = new Look { C = new Color(0.045f, 0.06f, 0.07f, 0.16f), M = 0f, S = 0.97f, Transparent = true },
            ["emit_cyan"] = Em(0x5fd8ff, 3.2f), ["emit_violet"] = Em(0xa77bff, 3.0f), ["emit_red"] = Em(0xff3a2e, 3.0f), ["emit_green"] = Em(0x52ff9a, 2.6f),
            ["emit_amber"] = Em(0xffa21f, 2.8f), ["emit_white"] = Em(0xe8f2ff, 2.6f),
            ["emit_panel_cyan"] = Em(0x5fd8ff, 3f), ["emit_panel_violet"] = Em(0xa77bff, 3f), ["emit_panel_white"] = Em(0xe8f2ff, 2.6f), ["emit_panel_warm"] = Em(0xffd2a0, 2.5f),
            ["emit_strip_cyan"] = Em(0x5fd8ff, 4f), ["emit_strip_violet"] = Em(0xa77bff, 4f), ["emit_strip_warm"] = Em(0xffd2a0, 3f),
            ["window_lit_warm"] = Em(0xffb878, 1.0f), ["window_lit_cool"] = Em(0x8fd0ff, 0.9f), ["screen"] = Em(0x7fd8ff, 1.2f),
            ["car_headlight"] = L(0xc0c6cc, 0.2, 0.9), ["car_taillight"] = L(0x590808, 0, 0.85),
        };

        static readonly Dictionary<string, Material> cache = new();

        public static string Canonical(string name) => ProtoMap.TryGetValue(name, out var n) ? n : name;

        /// <summary>
        /// Ground wetness (0 dry .. 1 soaked) for materials fetched while a rain zone builds (set by Atmosphere from
        /// AtmosphereSettings.WetGround, reset when the zone unloads): asphalt, paving and gravel come back as wet
        /// clones (darker albedo, glossy uniform water film, calmer normals) so the URP Lit ground reads soaked and
        /// mirrors the lights like the street kit's EOA/StreetSurface.
        /// </summary>
        public static float WetGround;
        static readonly HashSet<string> WetNames = new() { "asphalt", "paving", "gravel" };
        static readonly Dictionary<(string, int), Material> wetCache = new();

        public static Material Get(string name)
        {
            var m = GetDry(name);
            if (WetGround <= 0.01f || m == null) return m;
            var canon = Canonical(string.IsNullOrEmpty(name) ? "concrete" : name);
            if (!WetNames.Contains(canon)) return m;
            var key = (canon, Mathf.RoundToInt(WetGround * 20));
            if (wetCache.TryGetValue(key, out var w) && w != null) return w;
            w = new Material(m) { name = m.name + "_wet" };
            var k = Mathf.Lerp(1f, 0.58f, WetGround);
            if (w.HasProperty("_BaseColor")) { var c = w.GetColor("_BaseColor"); w.SetColor("_BaseColor", new Color(c.r * k, c.g * k, c.b * k, c.a)); }
            w.DisableKeyword("_METALLICSPECGLOSSMAP");
            if (w.HasProperty("_Metallic")) w.SetFloat("_Metallic", 0f);
            if (w.HasProperty("_Smoothness")) w.SetFloat("_Smoothness", Mathf.Lerp(0.45f, 0.8f, WetGround));
            if (w.HasProperty("_BumpScale")) w.SetFloat("_BumpScale", 0.75f);
            wetCache[key] = w;
            return w;
        }

        static Material GetDry(string name)
        {
            if (string.IsNullOrEmpty(name)) name = "concrete";
            if (cache.TryGetValue(name, out var hit) && hit != null) return hit;
            var canon = Canonical(name);
            if (cache.TryGetValue(canon, out hit) && hit != null) { cache[name] = hit; return hit; }
            Material m = canon == "aether_energy" ? Aether(new Color(0.37f, 0.85f, 1f), 1f) : Resources.Load<Material>("Env/Materials/" + canon);
            if (m == null) m = Build(canon);
            cache[canon] = m;
            cache[name] = m;
            return m;
        }

        /// <summary>True when the material should not cast shadows (emissive panels, glass, water, energy).</summary>
        public static bool NoShadow(string name)
        {
            var c = Canonical(name);
            return c.StartsWith("emit_") || c.StartsWith("window_lit") || c == "glass" || c == "water" || c == "puddle" || c == "aether_energy" || c == "screen";
        }

        /// <summary>Untextured URP material for a name (used by the editor library builder for parameter-only materials).</summary>
        public static Material CreateFallback(string name) => Build(Canonical(name));

        static Material Build(string canon)
        {
            if (!Fallback.TryGetValue(canon, out var look))
            {
                Debug.LogWarning($"[env] unknown material '{canon}', using concrete");
                look = Fallback["concrete"];
            }
            var m = new Material(FxMaterials.LitShader) { name = "env_" + canon };
            m.SetColor("_BaseColor", look.C);
            m.SetFloat("_Metallic", look.M);
            m.SetFloat("_Smoothness", look.S);
            if (look.EI > 0)
            {
                m.EnableKeyword("_EMISSION");
                m.globalIlluminationFlags = MaterialGlobalIlluminationFlags.RealtimeEmissive;
                m.SetColor("_EmissionColor", FxMaterials.Hdr(look.E, look.EI));
            }
            if (look.Transparent) FxMaterials.SetTransparent(m, true, look.Additive, false);
            return m;
        }

        static Shader aetherShader;

        /// <summary>
        /// Flowing Aether energy (fresnel + scrolling noise, additive). Uses the EOA/Aether shader; falls back to an
        /// additive particle material. Each call returns a new instance so intensity can be animated per object.
        /// </summary>
        public static Material Aether(Color color, float intensity, Color? secondary = null)
        {
            if (aetherShader == null) aetherShader = Shader.Find("EOA/Aether");
            Material m;
            if (aetherShader != null)
            {
                m = new Material(aetherShader) { name = "env_aether" };
                m.SetColor("_Color", color);
                m.SetColor("_Color2", secondary ?? new Color(0.65f, 0.48f, 1f));
                m.SetFloat("_Intensity", intensity);
            }
            else
            {
                m = FxMaterials.Particle(true, FxMaterials.Glow);
                m.SetColor("_BaseColor", FxMaterials.Hdr(color, intensity * 1.5f));
            }
            return m;
        }

        /// <summary>Set the brightness of a material created by <see cref="Aether"/>.</summary>
        public static void SetAetherIntensity(Material m, float intensity)
        {
            if (m == null) return;
            if (m.HasProperty("_Intensity")) m.SetFloat("_Intensity", intensity);
        }

        /// <summary>Unshared copy of an environment material with an HDR emission colour (lamp heads, signs that flicker).</summary>
        public static Material EmissiveInstance(Color color, float intensity)
        {
            var m = new Material(FxMaterials.LitShader) { name = "env_emissive" };
            m.SetColor("_BaseColor", color * 0.2f);
            m.SetFloat("_Smoothness", 0.6f);
            m.EnableKeyword("_EMISSION");
            m.SetColor("_EmissionColor", FxMaterials.Hdr(color, intensity));
            return m;
        }

        public static void SetEmission(Material m, Color color, float intensity)
        {
            if (m == null) return;
            m.SetColor("_EmissionColor", FxMaterials.Hdr(color, intensity));
        }
    }
}
