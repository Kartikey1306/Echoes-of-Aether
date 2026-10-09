using System.Collections.Generic;
using UnityEngine;

namespace EOA
{
    /// <summary>
    /// One-time palette regrade of a built night-city zone (AtmosphereSettings.CityPalette; run by
    /// Atmosphere.BakeReflections once everything is built). The Blender kits, the street builders and the older
    /// signage bake a magenta / violet heavy neon set into shared emissive materials, practical lights and the neon
    /// field; this pass moves that family (hue ~250..345 degrees) onto the district palettes of <see cref="Neon"/>,
    /// keeping a small share as an occasional magenta accent:
    ///   * emissive materials (URP Lit with _EMISSION): flat colours are retinted, textured strips / panels are swapped
    ///     for the warm strip / panel texture tinted to the target (a violet texture cannot be multiplied into red);
    ///     one cached clone per source material and target colour, assets on disk are never touched;
    ///   * EOA/Hologram adverts (_Color / _Color2);
    ///   * practical lights (point / spot) and the neon emitter field that rain, mist and wet streets pick up.
    /// The district comes from each object's position (CityLayout.DistrictAt). Deterministic (hash of the position).
    /// </summary>
    public static class CityPalette
    {
        /// <summary>Share of magenta-family sources kept as accents.</summary>
        const float KeepAccent = 0.12f;

        static readonly Dictionary<(Material, int), Material> clones = new();
        static readonly int EmissionId = Shader.PropertyToID("_EmissionColor"), EmissionMapId = Shader.PropertyToID("_EmissionMap"),
            BaseColorId = Shader.PropertyToID("_BaseColor"), HoloA = Shader.PropertyToID("_Color"), HoloB = Shader.PropertyToID("_Color2");

        // Replacement targets per district (the magenta family maps onto these).
        static readonly Color[][] Targets =
        {
            new[] { Neon.Red, Neon.Red, Neon.Amber, Neon.Gold, Neon.Crimson, Neon.Orange },        // NeonMarket
            new[] { Neon.Lime, Neon.Yellow, Neon.Orange, Neon.Orange, Neon.Fluoro, Neon.Amber },   // KowloonStacks
            new[] { Neon.Cyan, Neon.IceWhite, Neon.Gold, Neon.Cyan, Neon.Teal, Neon.Gold },        // ArcologyGate
            new[] { Neon.Teal, Neon.Amber, Neon.Teal, Neon.Red, Neon.WarmWhite, Neon.Cyan },       // CanalWard
            new[] { Neon.Sodium, Neon.Orange, Neon.Amber, Neon.Red, Neon.Sodium, Neon.Amber },     // FoundryRow
        };

        /// <summary>Known textured emissive materials: colour of their emission map and the swap family.</summary>
        static readonly Dictionary<string, (uint col, bool strip)> Textured = new()
        {
            ["emit_strip_violet"] = (0xa77bff, true), ["emit_strip_magenta"] = (0xff2bd6, true), ["emit_strip_pink"] = (0xff4f9a, true),
            ["emit_panel_violet"] = (0xa77bff, false), ["emit_panel_magenta"] = (0xff2bd6, false),
        };

        public static int Materials, Lights, Holos, Emitters;

        static uint Hash(Vector3 p)
        {
            unchecked
            {
                var h = (uint)Mathf.FloorToInt(p.x * 0.5f) * 73856093u ^ (uint)Mathf.FloorToInt(p.y * 0.5f) * 19349663u ^ (uint)Mathf.FloorToInt(p.z * 0.5f) * 83492791u;
                h ^= h >> 13; h *= 0x5bd1e995; h ^= h >> 15;
                return h;
            }
        }

        /// <summary>True for violet / magenta / pink with enough saturation to read as neon.</summary>
        public static bool IsMagentaFamily(Color srgb)
        {
            Color.RGBToHSV(srgb, out var h, out var s, out var v);
            var deg = h * 360f;
            return s > 0.35f && v > 0.05f && deg >= 250f && deg <= 345f;
        }

        /// <summary>Target colour for a magenta-family source at a position; null = keep (accent).</summary>
        static Color? Target(Vector3 unityPos, int salt)
        {
            var h = Hash(unityPos) + (uint)salt * 2654435761u;
            if ((h & 1023) / 1024f < KeepAccent) return null;
            var d = (int)CityLayout.DistrictAt(-unityPos.x, unityPos.z);
            var t = Targets[Mathf.Clamp(d, 0, Targets.Length - 1)];
            return t[(int)((h >> 10) % (uint)t.Length)];
        }

        /// <summary>Same value and roughly the same saturation as the source, the target's hue.</summary>
        static Color Retint(Color srcSrgb, Color targetSrgb)
        {
            Color.RGBToHSV(srcSrgb, out _, out var s, out var v);
            Color.RGBToHSV(targetSrgb, out var th, out var ts, out var tv);
            var c = Color.HSVToRGB(th, Mathf.Lerp(ts, s, 0.3f), Mathf.Max(v, tv * 0.8f));
            c.a = srcSrgb.a;
            return c;
        }

        static float Lum(Color lin) => lin.r * 0.2126f + lin.g * 0.7152f + lin.b * 0.0722f;

        /// <summary>Stored colour with its linear luminance capped (large panels: deep colour, never a white-hot slab).</summary>
        static Color CapLum(Color stored, float maxLum)
        {
            var c = stored.linear;
            var l = Lum(c);
            if (l <= maxLum) return stored;
            var g = (c * (maxLum / l)).gamma;
            g.a = stored.a;
            return g;
        }

        /// <summary>
        /// Stored (gamma-encoded, possibly HDR) colour with the target's hue and the SOURCE's luminance (x 1.05): a
        /// magenta panel turned yellow at the same peak channel would be twice as bright (yellow carries far more
        /// luminance), so big kit panels became glaring slabs.
        /// </summary>
        static Color MatchLum(Color storedSrc, Color targetSrgb)
        {
            var src = storedSrc.linear;
            var t = targetSrgb.linear;
            var f = Lum(src) * 1.05f / Mathf.Max(Lum(t), 1e-4f);
            var peak = Mathf.Max(src.r, Mathf.Max(src.g, src.b));
            var c = t * f;
            var cp = Mathf.Max(c.r, Mathf.Max(c.g, c.b));
            if (cp > peak * 1.8f) c *= peak * 1.8f / cp;
            var g = c.gamma;
            g.a = storedSrc.a;
            return g;
        }

        /// <summary>
        /// Material colours follow FxMaterials.Hdr: the value stored with SetColor is gamma encoded (may exceed 1) and the
        /// shader receives its linear. Chroma = the stored value over its largest channel (an sRGB colour), k = that channel.
        /// </summary>
        static Color Chroma(Color stored, out float k)
        {
            k = Mathf.Max(stored.r, Mathf.Max(stored.g, Mathf.Max(stored.b, 1e-4f)));
            return new Color(stored.r / k, stored.g / k, stored.b / k, 1);
        }

        /// <summary>Pale targets (yellow, gold, white) pushed to a deep saturated version for large emitters.</summary>
        static Color Deep(Color t)
        {
            Color.RGBToHSV(t, out var th, out var ts, out var tv);
            return ts < 0.8f ? Color.HSVToRGB(th, 0.88f, tv) : t;
        }

        static Material Swap(Material src, Vector3 pos, int salt, bool big)
        {
            if (src == null || !src.HasProperty(EmissionId) || !src.IsKeywordEnabled("_EMISSION")) return null;
            // NeonKit tubes already come from the district palettes (and the Aether graffiti keeps its violet motif)
            if (src.name.StartsWith("neon_tube") || src.name.StartsWith("env_emissive")) return null;
            var name = src.name.Replace(" (Instance)", "");
            Color srcColor;
            var textured = Textured.TryGetValue(name, out var tex);
            if (textured) srcColor = ProtoSpace.Hex(tex.col);
            else
            {
                if (src.HasProperty(EmissionMapId) && src.GetTexture(EmissionMapId) != null) return null; // atlases: leave
                srcColor = Chroma(src.GetColor(EmissionId), out _);
            }
            if (!IsMagentaFamily(srcColor)) return null;
            var target = Target(pos, salt);
            if (target == null) return null;
            var key = (src, ((Color32)target.Value).GetHashCode() * 2 + (big ? 1 : 0));
            if (clones.TryGetValue(key, out var m) && m != null) return m;
            Chroma(src.GetColor(EmissionId), out var k);
            if (textured)
            {
                // the warm strip / panel texture (warm white) tinted to the target hue
                var basis = EnvMaterials.Get(tex.strip ? "emit_strip_warm" : "emit_panel_warm");
                m = new Material(basis) { name = name + "_regrade" };
                var warm = ProtoSpace.Hex(0xffd2a0).linear;
                // source = texture colour x emission; match its luminance with the target hue, then divide out the
                // warm texture's own colour
                var srcLin = ProtoSpace.Hex(tex.col).linear * Mathf.GammaToLinearSpace(k);
                // big LED panels: deep saturated colours a little below the source level (pale yellow / white panels
                // read as blank glowing slabs once tonemapped)
                var tgt = target.Value;
                if (!tex.strip || big)
                {
                    tgt = Deep(tgt);
                    srcLin *= 0.3f;
                }
                var want = MatchLum(srcLin.gamma, tgt).linear;
                if (!tex.strip || big) want = CapLum(want.gamma, 0.45f).linear;
                var lin = new Color(want.r / Mathf.Max(warm.r, 0.05f), want.g / Mathf.Max(warm.g, 0.05f), want.b / Mathf.Max(warm.b, 0.05f));
                m.SetColor(EmissionId, lin.gamma);
            }
            else
            {
                m = new Material(src) { name = name + "_regrade" };
                // large emissive surfaces (LED walls, banners) go deep and a little dimmer; small tubes keep their level
                // (ACES shifts very bright orange / amber toward pale yellow-white, so big panels sit at ~1/4 of the
                // source luminance to keep a deep, saturated colour)
                var c = big ? CapLum(MatchLum(src.GetColor(EmissionId) * 0.5f, Deep(target.Value)), 0.45f) : MatchLum(src.GetColor(EmissionId), target.Value);
                c.a = 1;
                m.SetColor(EmissionId, c);
                if (m.HasProperty(BaseColorId)) m.SetColor(BaseColorId, Retint(src.GetColor(BaseColorId), target.Value));
            }
            clones[key] = m;
            Materials++;
            return m;
        }

        /// <summary>Regrade everything under root (call once after the zone is built).</summary>
        public static void Regrade(Transform root)
        {
            Materials = Lights = Holos = Emitters = 0;
            var tmp = new List<Material>(4);
            foreach (var r in root.GetComponentsInChildren<Renderer>(true))
            {
                if (r == null || r is ParticleSystemRenderer) continue;
                r.GetSharedMaterials(tmp);
                var pos = r.bounds.center;
                var changed = false;
                for (var i = 0; i < tmp.Count; i++)
                {
                    var m = tmp[i];
                    if (m == null) continue;
                    if (m.shader != null && m.shader.name == "EOA/Hologram")
                    {
                        // per-panel instances: retint in place
                        var a = m.GetColor(HoloA); var b = m.GetColor(HoloB);
                        var ta = IsMagentaFamily(Chroma(a, out var ka)) ? Target(pos, 1) : null;
                        var tb = IsMagentaFamily(Chroma(b, out var kb)) ? Target(pos, 2) : null;
                        if (ta != null) m.SetColor(HoloA, MatchLum(a, ta.Value));
                        if (tb != null) m.SetColor(HoloB, MatchLum(b, tb.Value));
                        if (ta != null || tb != null) Holos++;
                        continue;
                    }
                    var ext = r.bounds.extents;
                    var big = Mathf.Max(ext.x, Mathf.Max(ext.y, ext.z)) > 2.5f && Mathf.Min(ext.x + ext.z, ext.y) > 1.2f;
                    var swap = Swap(m, pos, i, big);
                    if (swap == null) continue;
                    tmp[i] = swap;
                    changed = true;
                }
                if (changed) r.SetSharedMaterials(tmp);
            }
            foreach (var l in root.GetComponentsInChildren<Light>(true))
            {
                if (l == null || l.type == LightType.Directional || !IsMagentaFamily(l.color)) continue;
                var t = Target(l.transform.position, 3);
                if (t == null) continue;
                l.color = Retint(l.color, t.Value);
                Lights++;
            }
            Emitters = NeonField.Remap((p, c) => IsMagentaFamily(c) && Target(p, 4) is Color t ? Retint(c, t) : c);
            Debug.Log($"[palette] city regrade: {Materials} emissive materials, {Holos} holograms, {Lights} lights, {Emitters} neon emitters");
        }
    }
}
