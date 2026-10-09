using System;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace EOA
{
    /// <summary>
    /// Applies the graphics settings to URP, quality settings and the camera. Every option changes real work:
    ///   Resolution    render scale 0.67 / 0.85 / 1.0 (native)
    ///   Shadows       off | low (1 cascade, 30 m, 1024) | medium (2 cascades, 45 m, 2048) | high (2 cascades, 70 m, 2048;
    ///                 ultra: 4 cascades, 100 m, 4096)
    ///   Effects       low: no SSAO, no screen-space decals, no bloom/grain/chroma, fewer particles and rain;
    ///                 medium: half-resolution SSAO with a cheaper blur, bloom; high: full SSAO, bloom, grain
    ///   Textures      mip limit 2 / 1 / 0 and anisotropic filtering
    ///   ViewDistance  camera far plane, per-layer cull distances, LOD bias, open-city detail radii, crowd/traffic density
    ///   Antialiasing  off / FXAA / SMAA (high) / TAA (rain drawn after the resolve) / MSAA 4x
    ///   Reflections   wet-street SSR (WetReflectionsPass) follows Effects: off on low and WebGL, 1/3 res on medium, 1/2 on high
    /// WebGL clamps to its own budget (no SSAO, no MSAA, short shadows) whatever the settings say.
    /// </summary>
    public static class GraphicsConfig
    {
        /// <summary>Benchmark overrides for measuring single passes (null = follow the settings).</summary>
        public static bool? ForceSsao, ForceDecals;

        /// <summary>Settings last applied (read by systems that size themselves on quality, e.g. the city culler).</summary>
        public static GraphicsSettings Current { get; private set; }

        /// <summary>
        /// Depth cues (<see cref="DepthCues"/>, CameraRig): shadow slots for the practical lights nearest the player
        /// (spot 1, point 3; Shadows off 0 / low 1 / medium 2 / high 3 / ultra 6; WebGL none), the character key's
        /// self-shadowing (medium and up, desktop) and the contact shadows under characters (always: one cheap draw).
        /// </summary>
        public static int LampShadowSlots { get; private set; } = 4;
        public static bool CharacterKeyShadows { get; private set; } = true;
        public static bool ContactShadows { get; private set; } = true;

        public static bool IsWebGL => Application.platform == RuntimePlatform.WebGLPlayer;

        static string aaOverride;
        static bool aaParsed;

        /// <summary>Dev / benchmark override of the antialiasing mode: command line "-aa off|fxaa|smaa|taa|msaa".</summary>
        static string AaOverride
        {
            get
            {
                if (aaParsed) return aaOverride;
                aaParsed = true;
                var args = Environment.GetCommandLineArgs();
                var i = Array.IndexOf(args, "-aa");
                if (i >= 0 && i + 1 < args.Length) aaOverride = args[i + 1];
                return aaOverride;
            }
        }

        static ScriptableRendererFeature ssao, decals;
        static object ssaoSettings;
        static System.Reflection.FieldInfo ssaoDownsample, ssaoBlur;
        static bool featuresSearched;
#if UNITY_EDITOR
        static bool editorRestoreHooked;
#endif

        public static void Apply(GraphicsSettings g, Camera cam)
        {
            Current = g;
            var aaMode = AaOverride ?? g.Antialiasing;
            var web = IsWebGL;
            var ultra = g.Preset == "ultra";
            var urp = UnityEngine.Rendering.GraphicsSettings.currentRenderPipeline as UniversalRenderPipelineAsset;
            var shadows = web && g.Shadows == "high" ? "medium" : g.Shadows;
            if (urp != null)
            {
                urp.renderScale = g.Resolution switch { "performance" => 0.67f, "balanced" => 0.85f, "quality" => 1f, _ => 1f };
                if (web) urp.renderScale = Mathf.Min(urp.renderScale, 0.85f);
                urp.shadowDistance = shadows switch { "off" => 0, "low" => 30, "medium" => 45, _ => ultra ? 100 : 70 };
                urp.shadowCascadeCount = shadows switch { "high" => ultra ? 4 : 2, "medium" => 2, _ => 1 };
                if (urp.shadowCascadeCount == 2) urp.cascade2Split = shadows == "high" ? 0.2f : 0.25f;
                urp.mainLightShadowmapResolution = shadows switch { "low" => 1024, "high" => ultra ? 4096 : 2048, _ => 2048 };
                // Additional-light shadow atlas (character key + the shadowed lamps of DepthCues; URP shrinks slices to fit).
                urp.additionalLightsShadowmapResolution = web ? 1024 : shadows switch { "low" => 1024, "high" => ultra ? 4096 : 2048, _ => 2048 };
                urp.msaaSampleCount = aaMode == "msaa" && !web ? 4 : 1;
            }
            QualitySettings.shadows = shadows == "off" ? UnityEngine.ShadowQuality.Disable : UnityEngine.ShadowQuality.All;
            LampShadowSlots = web ? 0 : shadows switch { "off" => 0, "low" => 1, "medium" => 2, _ => ultra ? 6 : 3 };
            CharacterKeyShadows = !web && (shadows == "medium" || shadows == "high");
            ContactShadows = true;
            QualitySettings.anisotropicFiltering = g.Textures == "low" ? AnisotropicFiltering.Disable : AnisotropicFiltering.ForceEnable;
            QualitySettings.globalTextureMipmapLimit = g.Textures switch { "low" => 2, "medium" => 1, _ => 0 };
            QualitySettings.lodBias = g.ViewDistance switch { "low" => 0.6f, "medium" => 1f, _ => ultra ? 2f : 1.4f };
            QualitySettings.vSyncCount = g.FrameLimit == "vsync" ? 1 : 0;
            Application.targetFrameRate = g.FrameLimit switch { "30" => 30, "60" => 60, "unlimited" => -1, _ => -1 };
            ApplyFeatures(g, web);
            // Wet-street screen-space reflections: off on low effects and WebGL, third resolution on medium, half
            // resolution on high (more steps on ultra).
            RenderPasses.Install();
            WetReflectionsPass.Quality = web || g.Effects == "low" ? 0 : g.Effects == "medium" ? 1 : ultra ? 3 : 2;
            if (cam != null)
            {
                // View distance per layer: everything keeps the old range (planar per-layer cull), except the distant
                // skyline layer, which is drawn out to the far plane so the horizon reads as a vast city.
                var view = g.ViewDistance switch { "low" => 150f, "medium" => 260f, _ => 420f };
                cam.farClipPlane = g.ViewDistance switch { "low" => 1400f, "medium" => 1800f, _ => 2200f };
                var cull = new float[32];
                for (var i = 0; i < cull.Length; i++) cull[i] = view;
                cull[CityFx.SkylineLayer] = 0;
                cam.layerCullDistances = cull;
                cam.layerCullSpherical = false;
                var data = cam.GetUniversalAdditionalCameraData();
                if (data != null)
                {
                    // TAA (desktop only, never with MSAA): clean hair cards and thin geometry; the rain streaks are then
                    // drawn after the resolve (RainLatePass) so they are not smeared. WebGL falls back to SMAA.
                    var taa = aaMode == "taa" && !web;
                    data.antialiasing = aaMode switch
                    {
                        "fxaa" => AntialiasingMode.FastApproximateAntialiasing,
                        "smaa" => AntialiasingMode.SubpixelMorphologicalAntiAliasing,
                        "taa" => taa ? AntialiasingMode.TemporalAntiAliasing : AntialiasingMode.SubpixelMorphologicalAntiAliasing,
                        _ => AntialiasingMode.None,
                    };
                    data.antialiasingQuality = AntialiasingQuality.High;
                    if (taa)
                    {
                        ref var ts = ref data.taaSettings;
                        ts.quality = TemporalAAQuality.High;
                        ts.baseBlendFactor = 0.86f;
                        ts.varianceClampScale = 0.9f;
                        // light sharpening and the default mip bias: stronger values brought back pore-level speckle and
                        // shimmer on skin and hair that the resolve had just removed
                        ts.contrastAdaptiveSharpening = 0.15f;
                        ts.mipBias = 0f;
                    }
                    RainLatePass.Active = taa;
                    data.renderPostProcessing = true;
                    data.renderShadows = shadows != "off";
                }
            }
            CityQuality.Apply(g);
#if !UNITY_WEBGL
            var mode = g.Fullscreen ? FullScreenMode.FullScreenWindow : FullScreenMode.Windowed;
            if (Screen.fullScreenMode != mode) Screen.fullScreenMode = mode;
#endif
        }

        /// <summary>SSAO and screen-space decals follow Effects (renderer features found once, toggled in place).</summary>
        static void ApplyFeatures(GraphicsSettings g, bool web)
        {
            FindFeatures();
            var ao = ForceSsao ?? (!web && g.Effects != "low");
            var dec = ForceDecals ?? g.Effects != "low";
            if (ssao != null && ssao.isActive != ao) ssao.SetActive(ao);
            if (decals != null && decals.isActive != dec) decals.SetActive(dec);
            // Medium: quarter-pixel SSAO with the Gaussian blur (no keyword change, so no new shader variants).
            if (ssaoSettings != null)
            {
                try
                {
                    ssaoDownsample?.SetValue(ssaoSettings, g.Effects == "medium");
                    if (ssaoBlur != null) ssaoBlur.SetValue(ssaoSettings, Enum.ToObject(ssaoBlur.FieldType, g.Effects == "high" ? 0 : 1));
                }
                catch (Exception e) { Debug.LogWarning("[graphics] SSAO quality: " + e.Message); ssaoSettings = null; }
            }
        }

        static void FindFeatures()
        {
            if (featuresSearched) return;
            featuresSearched = true;
            foreach (var f in Resources.FindObjectsOfTypeAll<ScriptableRendererFeature>())
            {
                if (f is ScreenSpaceAmbientOcclusion) ssao = f;
                else if (f is DecalRendererFeature) decals = f;
            }
            if (ssao != null)
            {
                const System.Reflection.BindingFlags bf = System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Public;
                ssaoSettings = typeof(ScreenSpaceAmbientOcclusion).GetField("m_Settings", bf)?.GetValue(ssao);
                if (ssaoSettings != null)
                {
                    ssaoDownsample = ssaoSettings.GetType().GetField("Downsample", bf);
                    ssaoBlur = ssaoSettings.GetType().GetField("BlurQuality", bf);
                }
            }
#if UNITY_EDITOR
            // Play mode toggles the renderer assets in place: put them back when leaving play mode.
            if (!editorRestoreHooked)
            {
                editorRestoreHooked = true;
                var aoWas = ssao != null && ssao.isActive; var decWas = decals != null && decals.isActive;
                object down = ssaoDownsample?.GetValue(ssaoSettings), blur = ssaoBlur?.GetValue(ssaoSettings);
                var settingsRef = ssaoSettings;
                Application.quitting += () =>
                {
                    if (ssao != null) ssao.SetActive(aoWas);
                    if (decals != null) decals.SetActive(decWas);
                    try { if (settingsRef != null) { ssaoDownsample?.SetValue(settingsRef, down); ssaoBlur?.SetValue(settingsRef, blur); } } catch { }
                };
            }
#endif
        }
    }

    /// <summary>
    /// Global post-processing volume plus gameplay feedback (low-health/damage vignette, Echo Sight desaturation and
    /// violet tint). The look (high-end night city): ACES filmic tonemapping, a per-zone colour grade (exposure,
    /// contrast, saturation, lift/gain, split toning teal shadows / warm highlights, shadows-midtones-highlights,
    /// white balance; <see cref="AtmosphereSettings"/>), a tight bloom with a procedural lens-dirt texture, faint
    /// anamorphic streaks off the brightest lights (screen-space lens flare, high effects only), fine film grain,
    /// chromatic aberration only toward the frame edges, and a soft vignette. Depth of field only in cinematics.
    /// </summary>
    public sealed class PostFx : MonoBehaviour
    {
        Volume volume;
        Bloom bloom;
        Vignette vignette;
        ColorAdjustments colour;
        FilmGrain grain;
        ChromaticAberration chroma;
        LiftGammaGain lgg;
        SplitToning split;
        ShadowsMidtonesHighlights smh;
        WhiteBalance white;
        ScreenSpaceLensFlare flare;
        DepthOfField dof;
        MotionBlur motion;
        bool cineDof, lensFx = true;
        float damagePulse, echoW, baseSaturation = -6, vignetteBase = 0.3f;
        static Texture2D lensDirt;

        public static PostFx Create(Transform parent)
        {
            var go = new GameObject("PostFx");
            go.transform.SetParent(parent, false);
            var p = go.AddComponent<PostFx>();
            go.AddComponent<DepthCues>();
            p.volume = go.AddComponent<Volume>();
            p.volume.isGlobal = true;
            p.volume.priority = 10;
            var profile = ScriptableObject.CreateInstance<VolumeProfile>();
            p.volume.sharedProfile = profile;
            var tone = profile.Add<Tonemapping>(true);
            tone.mode.Override(TonemappingMode.ACES);
            p.bloom = profile.Add<Bloom>(true);
            // Tight, crisp bloom: neon and lamps glow, impacts pop, nothing turns to milk. Low scatter keeps the halo
            // close to the source; the clamp caps how much a tiny over-bright texel (spark, flash core) can spread.
            p.bloom.threshold.Override(1.0f);
            p.bloom.intensity.Override(0.75f);
            p.bloom.scatter.Override(0.58f);
            p.bloom.clamp.Override(14f);
            p.bloom.highQualityFiltering.Override(true);
            p.bloom.dirtTexture.Override(LensDirt);
            p.bloom.dirtIntensity.Override(1.6f);
            // Split toning (0.5 grey = neutral, soft-light in gamma space): teal in the shadows, amber in the highlights.
            // Zones set their own amounts; colour still comes mostly from the lights.
            p.split = profile.Add<SplitToning>(true);
            p.split.shadows.Override(new Color(0.46f, 0.51f, 0.54f));
            p.split.highlights.Override(new Color(0.55f, 0.5f, 0.45f));
            p.split.balance.Override(0f);
            p.smh = profile.Add<ShadowsMidtonesHighlights>(true);
            p.white = profile.Add<WhiteBalance>(true);
            p.colour = profile.Add<ColorAdjustments>(true);
            p.colour.postExposure.Override(0.15f);
            p.colour.contrast.Override(12f);
            p.colour.saturation.Override(-6f);
            p.vignette = profile.Add<Vignette>(true);
            p.vignette.intensity.Override(0.3f);
            p.vignette.smoothness.Override(0.42f);
            p.vignette.rounded.Override(false);
            p.grain = profile.Add<FilmGrain>(true);
            // Fine, faint grain that lives in the shadows (high response keeps it off skin and other mid / bright
            // tones; the coarse Medium lookup read as speckle on faces in close-ups).
            p.grain.type.Override(FilmGrainLookup.Thin1);
            p.grain.intensity.Override(0.07f);
            p.grain.response.Override(0.95f);
            p.chroma = profile.Add<ChromaticAberration>(true);
            p.chroma.intensity.Override(0.07f);
            // Anamorphic streaks from the brightest lights only (no ghost flares).
            p.flare = profile.Add<ScreenSpaceLensFlare>(true);
            p.flare.intensity.Override(0.55f);
            p.flare.firstFlareIntensity.Override(0f);
            p.flare.secondaryFlareIntensity.Override(0f);
            p.flare.warpedFlareIntensity.Override(0f);
            p.flare.streaksIntensity.Override(0.55f);
            p.flare.streaksLength.Override(0.42f);
            p.flare.streaksOrientation.Override(0f);
            p.flare.streaksThreshold.Override(0.6f);
            p.flare.bloomMip.Override(1);
            p.flare.chromaticAbberationIntensity.Override(0.25f);
            p.flare.tintColor.Override(new Color(0.85f, 0.92f, 1f));
            p.dof = profile.Add<DepthOfField>(true);
            p.dof.mode.Override(DepthOfFieldMode.Off);
            p.motion = profile.Add<MotionBlur>(true);
            p.motion.mode.Override(MotionBlurMode.CameraOnly);
            p.motion.quality.Override(MotionBlurQuality.Medium);
            p.motion.intensity.Override(0.12f);
            p.motion.active = false;
            p.lgg = profile.Add<LiftGammaGain>(true);
            p.lgg.lift.Override(new Vector4(1f, 1f, 1f, 0f));
            p.lgg.gain.Override(new Vector4(1f, 1f, 1f, 0f));
            Bus.On<PlayerDamaged>(e => p.damagePulse = Mathf.Min(1, p.damagePulse + e.Amount / 40f));
            return p;
        }

        public void ApplySettings(SettingsData s)
        {
            var hi = s.Graphics.Effects == "high";
            var web = GraphicsConfig.IsWebGL;
            bloom.active = s.Graphics.Effects != "low";
            bloom.dirtIntensity.Override(hi ? 1.6f : 0.9f);
            bloom.highQualityFiltering.Override(hi);
            grain.active = hi;
            chroma.active = hi;
            chroma.intensity.Override(0.07f * s.Accessibility.FlashIntensity);
            lensFx = hi && !web;
            flare.active = lensFx;
            motion.active = false; // camera motion blur smears rain/edges (and WebGL motion vectors are unreliable)
        }

        /// <summary>Cinematic depth of field focused at a distance (metres); off returns to sharp gameplay.</summary>
        public void CinematicDof(bool on, float focusDistance = 5)
        {
            grain.intensity.Override(on ? 0.03f : 0.07f); // cinematic close-ups: almost no grain on faces
            if (on)
            {
                dof.mode.Override(DepthOfFieldMode.Bokeh);
                dof.focusDistance.Override(Mathf.Max(0.3f, focusDistance));
                dof.focalLength.Override(55f);
                dof.aperture.Override(2.8f);
            }
            else if (cineDof) dof.mode.Override(DepthOfFieldMode.Off);
            cineDof = on;
        }

        public void SetGrade(float exposure, float saturation, float contrast)
        {
            colour.postExposure.Override(exposure);
            baseSaturation = saturation;
            colour.saturation.Override(saturation);
            colour.contrast.Override(contrast);
        }

        /// <summary>
        /// Zone grade from prototype values: exposure/contrast/saturation multipliers, additive lift and
        /// multiplicative gain per channel, bloom threshold (linear).
        /// </summary>
        public void ApplyGrade(float exposure, float contrast, float saturation, Vector3 lift, Vector3 gain, float bloomThreshold)
        {
            SetGrade(Mathf.Log(Mathf.Max(0.05f, exposure), 2) + 0.15f, (saturation - 1) * 100 - 6, (contrast - 1) * 100 + 12);
            // URP keeps only the chroma of the lift/gain trackballs (input minus its luminance) and applies it in linear
            // space before tonemapping (lift x0.2, gain x0.8). The prototype's offsets are passed through 1:1 (an earlier
            // x4 "compensation" turned a +4% blue gain into +15% and lifted every black to navy) and each channel's
            // deviation is clamped so no zone grade can tint the whole frame.
            static float Tint(float v, float max) => Mathf.Clamp(v, -max, max);
            lgg.lift.Override(new Vector4(1 + Tint(lift.x, 0.02f), 1 + Tint(lift.y, 0.02f), 1 + Tint(lift.z, 0.02f), 0));
            lgg.gain.Override(new Vector4(1 + Tint(gain.x - 1, 0.04f), 1 + Tint(gain.y - 1, 0.04f), 1 + Tint(gain.z - 1, 0.04f), 0));
            // Never below 1 (linear): low thresholds bloomed whole lit walls and impacts into white haze.
            bloom.threshold.Override(Mathf.Max(1.0f, bloomThreshold + 0.12f));
        }

        /// <summary>Full zone grade: the prototype values above plus the cinematic layers of the zone.</summary>
        public void ApplyZoneGrade(AtmosphereSettings s)
        {
            ApplyGrade(s.Exposure, s.Contrast, s.Saturation, s.Lift, s.Gain, s.BloomThreshold);
            split.shadows.Override(ProtoSpace.Hex(s.SplitShadows));
            split.highlights.Override(ProtoSpace.Hex(s.SplitHighlights));
            split.balance.Override(s.SplitBalance);
            smh.shadows.Override(new Vector4(s.GradeShadows.x, s.GradeShadows.y, s.GradeShadows.z, s.ShadowLift));
            smh.midtones.Override(new Vector4(1, 1, 1, 0));
            smh.highlights.Override(new Vector4(s.GradeHighlights.x, s.GradeHighlights.y, s.GradeHighlights.z, 0));
            white.temperature.Override(s.Temperature);
            white.tint.Override(s.WhiteTint);
            vignetteBase = s.Vignette;
            if (lensFx) flare.streaksIntensity.Override(0.55f * s.LensStreaks);
        }

        /// <summary>
        /// Procedural lens dirt for the bloom (no textures from disk): faint smudges, a scatter of soft round specks of
        /// different sizes (dust and dried droplets on the front element) and a few wiped streaks. Only shows where the
        /// bloom lights it.
        /// </summary>
        static Texture2D LensDirt
        {
            get
            {
                if (lensDirt != null) return lensDirt;
                const int w = 512, h = 288;
                var px = new Color[w * h];
                var r = new System.Random(7341);
                float R() => (float)r.NextDouble();
                for (var y = 0; y < h; y++)
                for (var x = 0; x < w; x++)
                {
                    float u = x / (float)w, v = y / (float)h;
                    var n = Mathf.PerlinNoise(u * 5f + 3.1f, v * 3f + 1.7f) * 0.6f + Mathf.PerlinNoise(u * 13f, v * 9f) * 0.4f;
                    var smudge = Mathf.Clamp01((n - 0.48f) * 2.2f) * 0.07f;
                    px[y * w + x] = new Color(smudge, smudge, smudge * 1.05f, 1);
                }
                void Blob(float cx, float cy, float rad, float k, float sx, float sy, Color tint)
                {
                    int x0 = Mathf.Max(0, (int)(cx - rad * sx - 1)), x1 = Mathf.Min(w - 1, (int)(cx + rad * sx + 1));
                    int y0 = Mathf.Max(0, (int)(cy - rad * sy - 1)), y1 = Mathf.Min(h - 1, (int)(cy + rad * sy + 1));
                    for (var y = y0; y <= y1; y++)
                    for (var x = x0; x <= x1; x++)
                    {
                        float dx = (x - cx) / (rad * sx), dy = (y - cy) / (rad * sy);
                        var d = Mathf.Sqrt(dx * dx + dy * dy);
                        if (d >= 1) continue;
                        // soft disc with a slightly brighter rim (dried droplet)
                        var a = Mathf.SmoothStep(1f, 0.75f, d) * (0.65f + 0.35f * Mathf.SmoothStep(0.5f, 0.92f, d)) * k;
                        px[y * w + x] += tint * a;
                    }
                }
                for (var i = 0; i < 110; i++)
                {
                    var big = R();
                    var rad = 1.5f + big * big * big * 26f;
                    var k = (0.05f + R() * 0.22f) * (rad > 12 ? 0.55f : 1f);
                    var warm = R();
                    var tint = new Color(1f, 0.96f + warm * 0.04f, 0.9f + (1 - warm) * 0.12f);
                    Blob(R() * w, R() * h, rad, k, 1, 1, tint);
                }
                for (var i = 0; i < 6; i++)
                    Blob(R() * w, R() * h, 18 + R() * 30, 0.05f + R() * 0.05f, 2.6f + R() * 2f, 0.35f + R() * 0.2f, new Color(1f, 0.98f, 0.95f));
                lensDirt = new Texture2D(w, h, TextureFormat.RGBA32, false, true) { name = "lens_dirt_procedural", wrapMode = TextureWrapMode.Clamp };
                for (var i = 0; i < px.Length; i++) { var c = px[i]; px[i] = new Color(Mathf.Clamp01(c.r), Mathf.Clamp01(c.g), Mathf.Clamp01(c.b), 1); }
                lensDirt.SetPixels(px);
                lensDirt.Apply(false, true);
                return lensDirt;
            }
        }

        public void Tick(float dt, Hero p, ZoneRuntime world)
        {
            damagePulse = Mathf.Max(0, damagePulse - dt * 1.5f);
            var hp = p != null ? p.Health / Mathf.Max(1, p.Stats.MaxHealth) : 1;
            var low = hp < 0.3f ? (0.3f - hp) * 1.2f : 0;
            var dmg = Mathf.Clamp01(damagePulse + low);
            vignette.intensity.Override(vignetteBase + dmg * 0.25f);
            vignette.color.Override(Color.Lerp(Color.black, new Color(0.55f, 0.05f, 0.05f), dmg));
            var wantEcho = world != null && world.EchoActive ? Mathf.Min(1, world.EchoRemaining * 2) * 0.85f : 0;
            echoW = Mathf.MoveTowards(echoW, wantEcho, dt * 3);
            colour.colorFilter.Override(Color.Lerp(Color.white, new Color(0.82f, 0.78f, 1f), echoW));
            colour.saturation.Override(Mathf.Lerp(baseSaturation, -45, echoW));
        }
    }

    /// <summary>Dev captures: render a camera into a target, letting TAA converge over a few real frames.</summary>
    public static class CaptureUtil
    {
        public static async Awaitable RenderInto(Camera cam, RenderTexture rt)
        {
            var data = cam.GetUniversalAdditionalCameraData();
            var frames = data != null && data.antialiasing == AntialiasingMode.TemporalAntiAliasing ? 10 : 1;
            var prev = cam.targetTexture;
            try
            {
                cam.targetTexture = rt;
                for (var i = 0; i < frames; i++)
                {
                    cam.Render();
                    if (i < frames - 1) await Awaitable.NextFrameAsync();
                }
            }
            finally { cam.targetTexture = prev; }
        }
    }

    /// <summary>Small JPEG of the current view for save-slot thumbnails.</summary>
    public static class ThumbnailCapture
    {
        /// <summary>As <see cref="LastJpegBase64"/>, read back asynchronously (no CPU wait on the GPU).</summary>
        public static async Awaitable<string> CaptureAsync()
        {
            var cam = G.Manager?.Cam?.Cam;
            if (cam == null) return "";
            if (!SystemInfo.supportsAsyncGPUReadback) return LastJpegBase64;
            var rt = RenderTexture.GetTemporary(256, 144, 24, RenderTextureFormat.ARGB32);
            var prev = cam.targetTexture;
            try
            {
                try { cam.targetTexture = rt; cam.Render(); }
                finally { cam.targetTexture = prev; }
                var req = await AsyncGPUReadback.RequestAsync(rt, 0, TextureFormat.RGBA32);
                if (req.hasError) return "";
                using var jpg = ImageConversion.EncodeNativeArrayToJPG(req.GetData<byte>(), UnityEngine.Experimental.Rendering.GraphicsFormat.R8G8B8A8_UNorm, 256, 144, 0, 62);
                return "data:image/jpeg;base64," + Convert.ToBase64String(jpg.ToArray());
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[save] thumbnail failed: {e.Message}");
                return "";
            }
            finally { RenderTexture.ReleaseTemporary(rt); }
        }

        public static string LastJpegBase64
        {
            get
            {
                var cam = G.Manager?.Cam?.Cam;
                if (cam == null) return "";
                var rt = RenderTexture.GetTemporary(256, 144, 24, RenderTextureFormat.ARGB32);
                var prev = cam.targetTexture;
                try
                {
                    cam.targetTexture = rt;
                    cam.Render();
                    var active = RenderTexture.active;
                    RenderTexture.active = rt;
                    var tex = new Texture2D(256, 144, TextureFormat.RGB24, false);
                    tex.ReadPixels(new Rect(0, 0, 256, 144), 0, 0);
                    tex.Apply();
                    RenderTexture.active = active;
                    var jpg = tex.EncodeToJPG(62);
                    UnityEngine.Object.Destroy(tex);
                    return "data:image/jpeg;base64," + Convert.ToBase64String(jpg);
                }
                catch (Exception e)
                {
                    Debug.LogWarning($"[save] thumbnail failed: {e.Message}");
                    return "";
                }
                finally
                {
                    cam.targetTexture = prev;
                    RenderTexture.ReleaseTemporary(rt);
                }
            }
        }
    }
}
