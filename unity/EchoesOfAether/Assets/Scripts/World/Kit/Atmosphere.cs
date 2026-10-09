using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;
using static EOA.ProtoSpace;

namespace EOA
{
    /// <summary>Per-zone sky, fog, ambient, sun, reflections and colour grade (prototype values; converted here).</summary>
    public sealed class AtmosphereSettings
    {
        // Sky gradient (sRGB hex) — matches the prototype's createSky / bakeEnvironment config.
        public uint SkyTop = 0x0a1422, SkyHorizon = 0x1a2838, SkyBottom = 0x05070a, Glow = 0x2a3a50;
        public float GlowStrength = 0.5f;
        public bool Stars, Storm;
        /// <summary>Indoor zones: clear to a solid colour (the fog colour) instead of drawing the sky.</summary>
        public bool SolidBackground;
        /// <summary>Exponential-squared fog (three's FogExp2 density).</summary>
        public uint FogColor = 0x0d141c;
        public float FogDensity = 0.012f;
        /// <summary>Hemisphere light (prototype intensity) and environment-map intensity; both feed the trilight ambient.</summary>
        public uint HemiSky = 0x5a6a80, HemiGround = 0x14161a;
        public float HemiIntensity = 0.8f, EnvIntensity = 0.8f;
        /// <summary>Key/sun directional light: prototype position (light aims at SunTarget), colour, intensity.</summary>
        public Vector3 SunPos = new(10, 40, 12), SunTarget = Vector3.zero;
        public uint SunColor = 0x9ab4d8;
        public float SunIntensity = 0.8f;
        public bool SunShadows = true;
        /// <summary>Colour grade (prototype multipliers): exposure, contrast, saturation; lift/gain RGB offsets; bloom threshold.</summary>
        public float Exposure = 1, Contrast = 1, Saturation = 1, BloomThreshold = 1.05f;
        public Vector3 Lift = Vector3.zero, Gain = Vector3.one;
        /// <summary>
        /// Fraction of a coloured practical light's chroma kept in the light it casts (the emissive source itself stays
        /// fully saturated). A single saturated key (cyan lab ring, teal vault lamp) no longer paints every surface and
        /// face one hue; colour reads from the sources, surfaces keep their own colour.
        /// </summary>
        public float LightChroma = 0.55f;
        /// <summary>Camera fill on the characters (CameraRig.FillIntensity); 0 = automatic from how dark the ambient is.</summary>
        public float CharacterFill;
        /// <summary>
        /// Screen-space exponential height fog (EOA/HeightFog, see CityFx): density at HeightFogBase (1/m, 0 = off),
        /// falloff with height (1/m), start distance (m) and max opacity; haze colour, glow toward GlowDir (prototype
        /// xz direction of the brightest district) and near the horizon, and lit-from-below ground glow.
        /// </summary>
        public float HeightFogDensity, HeightFogFalloff = 0.05f, HeightFogBase, HeightFogStart = 6f, HeightFogMax = 0.9f;
        public uint HeightFogColor = 0x10141c, HeightFogGlow = 0x000000;
        public float HeightFogGlowStrength, HeightFogGround;
        public Vector2 HeightFogGlowDir = new(1, 0);
        /// <summary>Light pollution under the low clouds (EOA/Sky): colour and strength (0 = none).</summary>
        public uint CityGlow = 0x000000;
        public float CityGlowStrength;
        /// <summary>Blender storm deck (SkyFx): tint (sRGB, white = as painted) and saturation (1 = as painted).</summary>
        public uint SkyTint = 0xffffff;
        public float SkySaturation = 1f;
        /// <summary>
        /// Cinematic grade layers (PostFx.ApplyZoneGrade), on top of the prototype grade above. Split toning: sRGB
        /// colours (0x808080 = neutral; default teal shadows / amber highlights) and balance (-100..100).
        /// GradeShadows / GradeHighlights: ShadowsMidtonesHighlights tints (1 = neutral), ShadowLift its shadow offset
        /// (small positive values keep dark streets readable). Temperature / WhiteTint: white balance (-100..100).
        /// Vignette strength and anamorphic lens-streak scale (0 = none).
        /// </summary>
        public uint SplitShadows = 0x758289, SplitHighlights = 0x8c8073;
        public float SplitBalance;
        public Vector3 GradeShadows = new(0.97f, 1f, 1.04f), GradeHighlights = new(1.03f, 1f, 0.96f);
        public float ShadowLift, Temperature, WhiteTint, Vignette = 0.3f, LensStreaks = 1f;
        /// <summary>Night city: regrade the built zone's magenta-heavy kit emissives, lights and neon field onto the
        /// district palettes (CityPalette) once it is built.</summary>
        public bool CityPalette;
        /// <summary>Rain zones: URP Lit ground (asphalt, paving, gravel) is built from wet clones (EnvMaterials.WetGround).</summary>
        public float WetGround;
    }

    /// <summary>
    /// Applies an <see cref="AtmosphereSettings"/> to RenderSettings, the sky material (EOA/Sky), a directional sun,
    /// a realtime reflection probe and the post-processing grade. Lives on the zone root; lightning flashes from
    /// <see cref="Weather"/> brighten the sky, ambient and registered flash lights.
    /// </summary>
    public sealed class Atmosphere : MonoBehaviour
    {
        public AtmosphereSettings Settings { get; private set; }
        public Light Sun { get; private set; }
        Material sky;
        ReflectionProbe probe;
        HeightFogPass fogPass;
        Cubemap envCube;
        Color ambSky, ambEq, ambGround;
        float flash;
        readonly List<(Light light, float baseIntensity, float boost)> flashLights = new();
        static Atmosphere wetOwner;

        public static Atmosphere Apply(Transform zoneRoot, AtmosphereSettings s)
        {
            var a = zoneRoot.gameObject.AddComponent<Atmosphere>();
            EnvMaterials.WetGround = Mathf.Clamp01(s.WetGround);
            wetOwner = a;
            a.Settings = s;
            a.Build();
            return a;
        }

        void Build()
        {
            var s = Settings;
            var shader = s.SolidBackground ? null : Shader.Find("EOA/Sky");
            if (shader != null)
            {
                sky = new Material(shader) { name = "zone_sky" };
                sky.SetColor("_Top", Hex(s.SkyTop));
                sky.SetColor("_Horizon", Hex(s.SkyHorizon));
                sky.SetColor("_Bottom", Hex(s.SkyBottom));
                sky.SetColor("_Glow", Hex(s.Glow));
                sky.SetFloat("_GlowStrength", s.GlowStrength);
                sky.SetFloat("_Storm", s.Storm ? 1 : 0);
                sky.SetFloat("_Stars", s.Stars ? 1 : 0);
                sky.SetFloat("_Flash", 0);
                sky.SetColor("_CityGlow", Hex(s.CityGlow));
                sky.SetFloat("_CityGlowStrength", s.CityGlowStrength);
                SkyFx.Apply(sky, s); // [FX hook] Blender storm sky textures for the night storm zones (procedural fallback otherwise)
                sky.SetColor("_SkyTint", Hex(s.SkyTint));
                sky.SetFloat("_SkySaturation", s.SkySaturation);
                RenderSettings.skybox = sky;
            }
            else
            {
                RenderSettings.skybox = null;
                if (!s.SolidBackground) Debug.LogWarning("[env] EOA/Sky shader missing; using a solid background");
            }
            var cam = G.Manager != null && G.Manager.Cam != null ? G.Manager.Cam.Cam : Camera.main;
            if (cam != null)
            {
                cam.clearFlags = sky != null ? CameraClearFlags.Skybox : CameraClearFlags.SolidColor;
                cam.backgroundColor = s.SolidBackground ? Hex(s.FogColor) : Hex(s.SkyHorizon);
            }
            RenderSettings.fog = s.FogDensity > 0;
            RenderSettings.fogMode = FogMode.ExponentialSquared;
            RenderSettings.fogColor = Hex(s.FogColor);
            RenderSettings.fogDensity = s.FogDensity;
            // Ambient: hemisphere light + the diffuse part of the prototype's baked environment map.
            var k = s.HemiIntensity * LightToUnity;
            var e = s.EnvIntensity * LightToUnity * 1.4f;
            // The sky gradient and horizon glow are saturated accents in the sky; in the ambient they keep only a hint of
            // their hue (a full-chroma magenta glow on the equator term painted every wall and character pink).
            Color Sky(uint hex, float keep = 0.25f)
            {
                var c = Hex(hex).linear;
                var l = c.r * 0.2126f + c.g * 0.7152f + c.b * 0.0722f;
                return Color.Lerp(new Color(l, l, l), c, keep);
            }
            ambSky = Hex(s.HemiSky).linear * k + Sky(s.SkyTop) * e + Sky(s.Glow) * e * s.GlowStrength * 0.5f;
            ambEq = Color.Lerp(Hex(s.HemiSky).linear, Hex(s.HemiGround).linear, 0.5f) * k + (Sky(s.SkyHorizon) + Sky(s.Glow) * s.GlowStrength) * e;
            ambGround = Hex(s.HemiGround).linear * k + Sky(s.SkyBottom) * e;
            RenderSettings.ambientMode = AmbientMode.Trilight;
            SetAmbient(0);
            RenderSettings.reflectionIntensity = Mathf.Clamp01(s.EnvIntensity);
            // Default environment reflection (everything outside a reflection probe): a small HDR cube of this zone's
            // own sky / fog instead of Unity's default procedural sky, whose brown ground tinted glass and paint tan.
            envCube = SkyCube(s);
            RenderSettings.defaultReflectionMode = DefaultReflectionMode.Custom;
            RenderSettings.customReflectionTexture = envCube;
            // Characters stay readable in dark zones: the camera fill (characters' rendering layer only) scales with how
            // little ambient light the zone has.
            var lum = ambEq.r * 0.2126f + ambEq.g * 0.7152f + ambEq.b * 0.0722f;
            var dark = 0.1f / Mathf.Max(0.01f, lum);
            var fill = s.CharacterFill > 0 ? s.CharacterFill : Mathf.Clamp(0.9f * dark, 0.9f, 3.2f);
            if (G.Manager != null && G.Manager.Cam != null)
            {
                G.Manager.Cam.FillIntensity = fill;
                G.Manager.Cam.RimIntensity = 14f * Mathf.Clamp(Mathf.Sqrt(dark), 1f, 1.8f);
            }
            // City atmosphere globals (height fog, haze colours); zones without height fog reset them to off.
            CityFx.ApplyAtmosphere(s, this);
            NeonField.Ensure(transform);
            if (s.HeightFogDensity > 0 && cam != null) fogPass = HeightFogPass.Attach(cam);
            // Sun / key light.
            var go = new GameObject("Sun");
            go.transform.SetParent(transform, false);
            var dir = V(s.SunTarget) - V(s.SunPos);
            go.transform.rotation = Quaternion.LookRotation(dir.sqrMagnitude > 0.001f ? dir.normalized : Vector3.down);
            Sun = go.AddComponent<Light>();
            Sun.type = LightType.Directional;
            Sun.color = Hex(s.SunColor);
            Sun.intensity = s.SunIntensity * LightToUnity;
            Sun.shadows = s.SunShadows ? LightShadows.Soft : LightShadows.None;
            // Full-strength moon / sun shadows (the ambient still fills them): soft 0.85 shadows washed out the one
            // cue that tells where things stand.
            Sun.shadowStrength = 0.97f;
            Sun.shadowBias = 0.04f;
            Sun.shadowNormalBias = 0.3f;
            RenderSettings.sun = Sun;
            AddFlashLight(Sun, 3);
            G.Manager?.Post?.ApplyZoneGrade(s);
        }

        /// <summary>32 px HDR cube (linear) of the sky gradient, horizon glow and city light pollution; mips box-filtered.</summary>
        static Cubemap SkyCube(AtmosphereSettings s)
        {
            const int n = 32;
            var cube = new Cubemap(n, TextureFormat.RGBAHalf, true) { name = "zone_env_reflection" };
            Color top, hor, bot;
            if (s.SolidBackground)
            {
                hor = Hex(s.FogColor).linear;
                top = Color.Lerp(hor, Hex(s.HemiSky).linear * 0.35f, 0.5f);
                bot = Hex(s.HemiGround).linear * 0.3f;
            }
            else { top = Hex(s.SkyTop).linear; hor = Hex(s.SkyHorizon).linear; bot = Hex(s.SkyBottom).linear; }
            var glow = s.SolidBackground ? Color.black : Hex(s.Glow).linear * s.GlowStrength;
            var city = Hex(s.CityGlow).linear * s.CityGlowStrength;
            // (warm glow of the brightest districts mixed in: wet streets and glass pick up teal haze and amber light)
            var haze = s.SolidBackground ? Color.black : s.HeightFogDensity > 0
                ? new Color(0.03f, 0.042f, 0.05f) + Hex(s.HeightFogColor).linear * 2f + Hex(s.HeightFogGlow).linear * (s.HeightFogGlowStrength * 0.6f)
                : hor * 0.5f;
            var px = new Color[n * n];
            for (var f = 0; f < 6; f++)
            {
                for (var y = 0; y < n; y++)
                for (var x = 0; x < n; x++)
                {
                    float u = (x + 0.5f) / n * 2 - 1, v = (y + 0.5f) / n * 2 - 1;
                    var d = f switch
                    {
                        0 => new Vector3(1, -v, -u), 1 => new Vector3(-1, -v, u), 2 => new Vector3(u, 1, v),
                        3 => new Vector3(u, -1, -v), 4 => new Vector3(u, -v, 1), _ => new Vector3(-u, -v, -1),
                    };
                    var dy = d.normalized.y;
                    var c = dy > 0 ? Color.Lerp(hor, top, Mathf.Pow(dy, 0.55f)) : Color.Lerp(hor, bot, Mathf.Clamp01(-dy * 4));
                    c += glow * Mathf.Exp(-Mathf.Abs(dy) * 9f) * 0.6f + city * Mathf.Exp(-Mathf.Max(dy, 0) * 5f) * 0.25f;
                    // Lit city haze around the horizon: the sheen wet streets and glass pick up between the neon.
                    c += haze * Mathf.Exp(-Mathf.Abs(dy) * 3f);
                    c.a = 1;
                    px[y * n + x] = c;
                }
                cube.SetPixels(px, (CubemapFace)f);
            }
            cube.Apply(true, false);
            return cube;
        }

        void SetAmbient(float f)
        {
            var boost = new Color(0.55f, 0.6f, 0.75f) * f * 0.6f;
            RenderSettings.ambientSkyColor = (ambSky + boost).gamma;
            RenderSettings.ambientEquatorColor = (ambEq + boost * 0.6f).gamma;
            RenderSettings.ambientGroundColor = (ambGround + boost * 0.25f).gamma;
        }

        /// <summary>Lights brightened by lightning (base intensity + boost × flash, prototype boost units).</summary>
        public void AddFlashLight(Light l, float boost)
        {
            if (l != null) flashLights.Add((l, l.intensity, boost * LightToUnity));
        }

        /// <summary>
        /// Practical lights keep <see cref="AtmosphereSettings.LightChroma"/> of their chroma (luminance preserved), so
        /// coloured keys tint a scene instead of turning it monochrome. Directional lights are left alone.
        /// </summary>
        public static Color TameLightColor(Color srgb, float keep)
        {
            var c = srgb.linear;
            var l = c.r * 0.2126f + c.g * 0.7152f + c.b * 0.0722f;
            var t = Color.Lerp(new Color(l, l, l), c, Mathf.Clamp01(keep)).gamma;
            t.a = 1;
            return t;
        }

        void TameLights()
        {
            if (Settings.LightChroma >= 0.999f) return;
            foreach (var l in GetComponentsInChildren<Light>(true))
                if (l != null && l.type != LightType.Directional) l.color = TameLightColor(l.color, Settings.LightChroma);
        }

        /// <summary>Realtime reflection probe covering the built geometry, rendered once (call after the zone is built).</summary>
        public void BakeReflections(Bounds bounds)
        {
            if (Settings.CityPalette)
            {
                try { EOA.CityPalette.Regrade(transform); }
                catch (System.Exception e) { Debug.LogWarning("[palette] regrade failed: " + e.Message); }
            }
            TameLights();
            var go = new GameObject("ReflectionProbe");
            go.transform.SetParent(transform, false);
            go.transform.position = bounds.center + Vector3.up * 2;
            probe = go.AddComponent<ReflectionProbe>();
            probe.mode = ReflectionProbeMode.Realtime;
            probe.refreshMode = ReflectionProbeRefreshMode.ViaScripting;
            probe.timeSlicingMode = ReflectionProbeTimeSlicingMode.AllFacesAtOnce;
            probe.size = bounds.size + Vector3.one * 20;
            probe.resolution = 128;
            probe.hdr = true;
            probe.intensity = Mathf.Max(0.4f, Settings.EnvIntensity);
            probe.cullingMask = 1 << CombatLayers.World;
            probe.boxProjection = false;
            probe.RenderProbe();
        }

        public void SetFlash(float f)
        {
            if (Mathf.Approximately(f, flash)) return;
            flash = f;
            if (sky != null) sky.SetFloat("_Flash", f);
            SetAmbient(f);
            foreach (var (l, b, boost) in flashLights) if (l != null) l.intensity = b + boost * f;
        }

        void OnDestroy()
        {
            if (RenderSettings.skybox == sky) RenderSettings.skybox = null;
            if (sky != null) Destroy(sky);
            if (fogPass != null) Destroy(fogPass.gameObject);
            if (RenderSettings.customReflectionTexture == envCube) RenderSettings.customReflectionTexture = null;
            if (envCube != null) Destroy(envCube);
            CityFx.ClearAtmosphere(this);
            if (wetOwner == this) { EnvMaterials.WetGround = 0; wetOwner = null; }
        }
    }
}
