using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace EOA
{
    /// <summary>
    /// Blender-rendered sky / weather / atmosphere FX (blender/fx/scripts, procedural only), loaded from
    /// Assets/Art/FX/Resources/FX. Textures and ready-made emitters for every agent:
    ///
    ///   Sky       FxLibrary.SkyPano      "FX/Sky/sky_storm_pano"     4096x2048 equirect storm deck (RGB, A flash response)
    ///             FxLibrary.SkyClouds    "FX/Sky/sky_clouds"         1024^2 tileable scud (R below-lit, G above-lit, B ambient, A coverage)
    ///             FxLibrary.SkyBand      "FX/Sky/sky_city_band"      4096x256 far megacity silhouette band (premultiplied RGBA, -3..12 deg)
    ///   Lightning FxLibrary.Bolts        "FX/Lightning/lightning_bolts"  1024^2, 4 vertical bolts (columns), R core+glow
    ///   Rain      FxLibrary.RainStreaks  "FX/Rain/rain_streaks_atlas"    512^2, 8 motion-blurred streak columns (R highlight, A coverage)
    ///             FxLibrary.RainSplash   "FX/Rain/rain_splash_4x4"       1024^2 crown splash flipbook (16 frames, side view)
    ///             FxLibrary.RainRing     "FX/Rain/rain_ring_4x4"         512^2 ground impact ring flipbook (16 frames, top view)
    ///             FxLibrary.RainDrips    "FX/Rain/rain_drips"            256x256, 4 drip / drizzle sprites (2x2)
    ///             FxLibrary.RainRipple   "FX/Rain/rain_ripple_n"         1024^2 puddle ripple NORMAL flipbook 4x4 (global _EOA_RainRipple)
    ///             FxLibrary.RainDropsN   "FX/Rain/rain_drops_n"          1024^2 tileable droplet NORMAL map (global _EOA_RainDrops)
    ///             FxLibrary.RainSurface  "FX/Rain/rain_streaks"          1024^2 tileable rivulets RG normal, B mask, A phase (global _EOA_RainStreaks)
    ///   Smoke     FxLibrary.Steam        "FX/Smoke/steam_8x8"            2048^2 rising steam puff flipbook (64 frames over the puff's life)
    ///             FxLibrary.Smoke        "FX/Smoke/smoke_8x8"            2048^2 dense dark smoke flipbook (64 frames)
    ///             FxLibrary.Mist         "FX/Smoke/mist_tile"            1024^2 tileable soft mist, 4 morph frames in R, G, B, A
    ///
    /// Emitters (pooled ParticleSystems, counts scale with Settings > Effects, EOA/FxParticle lit by ambient, the neon
    /// field and Forward+ lights): <see cref="SteamVent"/>, <see cref="SmokeColumn"/>, <see cref="GroundMist"/>,
    /// <see cref="Drips"/>. Materials: <see cref="ParticleMaterial"/> (shared per texture / settings).
    /// All loaders return null when an asset is missing so callers can keep their procedural fallbacks.
    /// </summary>
    public static class FxLibrary
    {
        public const string SkyPano = "FX/Sky/sky_storm_pano", SkyClouds = "FX/Sky/sky_clouds", SkyBand = "FX/Sky/sky_city_band",
            Bolts = "FX/Lightning/lightning_bolts",
            RainStreaks = "FX/Rain/rain_streaks_atlas", RainSplash = "FX/Rain/rain_splash_4x4", RainRing = "FX/Rain/rain_ring_4x4",
            RainDrips = "FX/Rain/rain_drips", RainRipple = "FX/Rain/rain_ripple_n", RainDropsN = "FX/Rain/rain_drops_n",
            RainSurface = "FX/Rain/rain_streaks",
            Steam = "FX/Smoke/steam_8x8", Smoke = "FX/Smoke/smoke_8x8", Mist = "FX/Smoke/mist_tile";

        /// <summary>Template materials (keep the shaders in builds): Resources/FX/Materials/*.mat.</summary>
        public const string RainStreaksMaterial = "FX/Materials/RainStreaks", FxParticleMaterial = "FX/Materials/FxParticle";

        static readonly Dictionary<string, Texture2D> textures = new();
        static readonly Dictionary<(string, float, float, float, int), Material> materials = new();
        static Shader particleShader, rainShader;

        public static Texture2D Tex(string path)
        {
            if (textures.TryGetValue(path, out var t) && t != null) return t;
            t = Resources.Load<Texture2D>(path);
            textures[path] = t;
            return t;
        }

        public static Shader ParticleShader => particleShader != null ? particleShader : particleShader = FindShader(FxParticleMaterial, "EOA/FxParticle");
        public static Shader RainShader => rainShader != null ? rainShader : rainShader = FindShader(RainStreaksMaterial, "EOA/RainStreaks");

        static Shader FindShader(string template, string name)
        {
            var m = Resources.Load<Material>(template);
            var s = m != null ? m.shader : Shader.Find(name);
            return s != null && s.isSupported ? s : null;
        }

        /// <summary>"low" | "medium" | "high" from Settings > Graphics > Effects.</summary>
        public static int Quality(int high, int medium, int low)
        {
            var e = G.Settings?.Data?.Graphics?.Effects ?? "high";
            return e == "low" ? low : e == "medium" ? medium : high;
        }

        public static float Quality(float high, float medium, float low)
        {
            var e = G.Settings?.Data?.Graphics?.Effects ?? "high";
            return e == "low" ? low : e == "medium" ? medium : high;
        }

        /// <summary>
        /// Shared EOA/FxParticle material for a flipbook texture. occlusion 0 = additive glow .. 1 alpha blended;
        /// neon = gain on the neon emitter field; soft = depth fade (m). Null if the texture or shader is missing.
        /// </summary>
        public static Material ParticleMaterial(string texture, float occlusion = 0.5f, float neon = 1f, float soft = 0.5f, int queueOffset = 0)
        {
            var key = (texture, occlusion, neon, soft, queueOffset);
            if (materials.TryGetValue(key, out var m) && m != null) return m;
            var tex = Tex(texture);
            var sh = ParticleShader;
            if (tex == null || sh == null) return null;
            var tmpl = Resources.Load<Material>(FxParticleMaterial);
            m = tmpl != null ? new Material(tmpl) : new Material(sh);
            m.name = "fx_" + texture.Substring(texture.LastIndexOf('/') + 1);
            m.SetTexture("_BaseMap", tex);
            m.SetFloat("_Alpha", occlusion);
            m.SetVector("_Light", new Vector4(1f, neon, 1f, 0.3f));
            m.SetFloat("_Soft", soft);
            m.renderQueue = (int)RenderQueue.Transparent + queueOffset;
            materials[key] = m;
            return m;
        }

        static readonly List<ParticleSystemVertexStream> flipStreams = new()
        {
            ParticleSystemVertexStream.Position, ParticleSystemVertexStream.Color,
            ParticleSystemVertexStream.UV, ParticleSystemVertexStream.UV2, ParticleSystemVertexStream.AnimBlend,
        };

        /// <summary>Texture-sheet animation over the particle's life with smooth frame blending (EOA/FxParticle).</summary>
        public static void Flipbook(ParticleSystem ps, int cols, int rows, float cycles = 1f, bool randomRow = false)
        {
            var ts = ps.textureSheetAnimation;
            ts.enabled = true;
            ts.mode = ParticleSystemAnimationMode.Grid;
            ts.numTilesX = cols;
            ts.numTilesY = rows;
            ts.animation = randomRow ? ParticleSystemAnimationType.SingleRow : ParticleSystemAnimationType.WholeSheet;
            if (randomRow) ts.rowMode = ParticleSystemAnimationRowMode.Random;
            ts.cycleCount = Mathf.Max(1, Mathf.RoundToInt(cycles));
            ts.frameOverTime = new ParticleSystem.MinMaxCurve(1f, AnimationCurve.Linear(0, 0, 1, 1));
            ps.GetComponent<ParticleSystemRenderer>().SetActiveVertexStreams(flipStreams);
        }

        /// <summary>Random fixed frame per particle (sprite atlases such as drips): startFrame random, no animation.</summary>
        public static void RandomFrame(ParticleSystem ps, int cols, int rows)
        {
            var ts = ps.textureSheetAnimation;
            ts.enabled = true;
            ts.mode = ParticleSystemAnimationMode.Grid;
            ts.numTilesX = cols;
            ts.numTilesY = rows;
            ts.animation = ParticleSystemAnimationType.WholeSheet;
            ts.frameOverTime = new ParticleSystem.MinMaxCurve(0f);
            ts.startFrame = new ParticleSystem.MinMaxCurve(0f, cols * rows - 0.01f);
        }

        /// <summary>Stopped, looping, world-space particle system on layer 29 (CityFx.FxLayer).</summary>
        public static ParticleSystem NewSystem(string name, Transform parent, Vector3 position, int maxParticles, Material material)
        {
            var go = new GameObject(name) { layer = CityFx.FxLayer };
            go.transform.SetParent(parent, false);
            go.transform.position = position;
            var ps = go.AddComponent<ParticleSystem>();
            ps.Stop(true, ParticleSystemStopBehavior.StopEmittingAndClear);
            var main = ps.main;
            main.loop = true;
            main.playOnAwake = false;
            main.maxParticles = maxParticles;
            main.simulationSpace = ParticleSystemSimulationSpace.World;
            main.scalingMode = ParticleSystemScalingMode.Hierarchy;
            main.gravityModifier = 0;
            var r = go.GetComponent<ParticleSystemRenderer>();
            r.sharedMaterial = material;
            r.shadowCastingMode = ShadowCastingMode.Off;
            r.receiveShadows = false;
            r.lightProbeUsage = LightProbeUsage.Off;
            r.reflectionProbeUsage = ReflectionProbeUsage.Off;
            return ps;
        }

        static Gradient Fade(float inAt, float holdTo, float peak = 1f)
        {
            var g = new Gradient();
            g.SetKeys(new[] { new GradientColorKey(Color.white, 0), new GradientColorKey(Color.white, 1) },
                      new[] { new GradientAlphaKey(0, 0), new GradientAlphaKey(peak, inAt), new GradientAlphaKey(peak * 0.7f, holdTo), new GradientAlphaKey(0, 1) });
            return g;
        }

        /// <summary>
        /// Rising steam plume from a vent / manhole / noodle-bar exhaust (Blender steam flipbook, neon-lit). scale ~1 for
        /// a manhole; wind is a world velocity (m/s) the plume leans into. Returns null if the assets are missing.
        /// </summary>
        public static ParticleSystem SteamVent(Transform parent, Vector3 position, float scale = 1f, Vector3 wind = default, int seed = 0)
        {
            var m = ParticleMaterial(Steam, 0.35f, 1.1f, 0.8f);
            if (m == null) return null;
            var n = Quality(26, 18, 10);
            var ps = NewSystem("SteamVent", parent, position, n + 4, m);
            var rnd = new System.Random(seed);
            var main = ps.main;
            main.startLifetime = new ParticleSystem.MinMaxCurve(3.0f, 4.2f);
            main.startSpeed = 0;
            main.startSize = new ParticleSystem.MinMaxCurve(0.9f * scale, 1.5f * scale);
            main.startRotation = new ParticleSystem.MinMaxCurve(0, Mathf.PI * 2);
            main.startColor = new Color(0.55f, 0.58f, 0.64f, 0.75f);
            main.prewarm = true;
            var em = ps.emission;
            em.rateOverTime = n / 3.6f * (0.9f + (float)rnd.NextDouble() * 0.2f);
            var shape = ps.shape;
            shape.shapeType = ParticleSystemShapeType.Cone;
            shape.angle = 10;
            shape.radius = 0.22f * scale;
            shape.rotation = new Vector3(-90, 0, 0);
            var vel = ps.velocityOverLifetime;
            vel.enabled = true;
            vel.space = ParticleSystemSimulationSpace.World;
            vel.x = new ParticleSystem.MinMaxCurve(wind.x * 0.3f, wind.x * 0.5f);
            vel.y = new ParticleSystem.MinMaxCurve(0.7f * scale, 1.3f * scale);
            vel.z = new ParticleSystem.MinMaxCurve(wind.z * 0.3f, wind.z * 0.5f);
            var size = ps.sizeOverLifetime;
            size.enabled = true;
            size.size = new ParticleSystem.MinMaxCurve(1f, AnimationCurve.EaseInOut(0, 0.6f, 1, 2.4f));
            var rot = ps.rotationOverLifetime;
            rot.enabled = true;
            rot.z = new ParticleSystem.MinMaxCurve(-0.25f, 0.25f);
            var col = ps.colorOverLifetime;
            col.enabled = true;
            col.color = Fade(0.12f, 0.55f);
            Flipbook(ps, 8, 8);
            ps.Play();
            return ps;
        }

        /// <summary>Dark smoke column (fires, wrecks, chimneys). Alpha-blended, still picks up neon and lamps.</summary>
        public static ParticleSystem SmokeColumn(Transform parent, Vector3 position, float scale = 1f, Vector3 wind = default, int seed = 0)
        {
            var m = ParticleMaterial(Smoke, 0.85f, 0.6f, 1f);
            if (m == null) return null;
            var n = Quality(30, 20, 10);
            var ps = NewSystem("SmokeColumn", parent, position, n + 4, m);
            var main = ps.main;
            main.startLifetime = new ParticleSystem.MinMaxCurve(4.5f, 6f);
            main.startSpeed = 0;
            main.startSize = new ParticleSystem.MinMaxCurve(1.2f * scale, 2f * scale);
            main.startRotation = new ParticleSystem.MinMaxCurve(0, Mathf.PI * 2);
            main.startColor = new Color(0.3f, 0.3f, 0.33f, 0.9f);
            main.prewarm = true;
            var em = ps.emission;
            em.rateOverTime = n / 5.2f;
            var shape = ps.shape;
            shape.shapeType = ParticleSystemShapeType.Circle;
            shape.radius = 0.4f * scale;
            shape.rotation = new Vector3(-90, 0, 0);
            var vel = ps.velocityOverLifetime;
            vel.enabled = true;
            vel.space = ParticleSystemSimulationSpace.World;
            vel.x = new ParticleSystem.MinMaxCurve(wind.x * 0.4f, wind.x * 0.7f);
            vel.y = new ParticleSystem.MinMaxCurve(1.2f * scale, 2.0f * scale);
            vel.z = new ParticleSystem.MinMaxCurve(wind.z * 0.4f, wind.z * 0.7f);
            var size = ps.sizeOverLifetime;
            size.enabled = true;
            size.size = new ParticleSystem.MinMaxCurve(1f, AnimationCurve.EaseInOut(0, 0.5f, 1, 3.2f));
            var rot = ps.rotationOverLifetime;
            rot.enabled = true;
            rot.z = new ParticleSystem.MinMaxCurve(-0.2f, 0.2f);
            var col = ps.colorOverLifetime;
            col.enabled = true;
            col.color = Fade(0.08f, 0.6f);
            Flipbook(ps, 8, 8);
            ps.Play();
            return ps;
        }

        /// <summary>
        /// Low drifting street mist over an area (size x/z in metres): a few large soft cards that morph slowly. Lit by the
        /// neon field so it glows under signs. Keep areas modest (≤ 30 m); stack several for long streets.
        /// </summary>
        public static ParticleSystem GroundMist(Transform parent, Vector3 center, Vector2 size, float density = 0.35f, Vector3 wind = default)
        {
            var m = ParticleMaterial(Steam, 0.15f, 1.2f, 1.5f, -2);
            if (m == null) return null;
            var area = Mathf.Max(1f, size.x * size.y);
            var n = Mathf.Clamp(Mathf.RoundToInt(area / 22f * Quality(1f, 0.7f, 0.4f)), 3, 40);
            var ps = NewSystem("GroundMist", parent, center, n + 2, m);
            var main = ps.main;
            main.startLifetime = new ParticleSystem.MinMaxCurve(10f, 14f);
            main.startSpeed = 0;
            main.startSize = new ParticleSystem.MinMaxCurve(4.5f, 7f);
            main.startRotation = new ParticleSystem.MinMaxCurve(0, Mathf.PI * 2);
            main.startColor = new Color(0.5f, 0.55f, 0.62f, density);
            main.prewarm = true;
            var em = ps.emission;
            em.rateOverTime = n / 12f;
            var shape = ps.shape;
            shape.shapeType = ParticleSystemShapeType.Box;
            shape.scale = new Vector3(size.x, 0.6f, size.y);
            var vel = ps.velocityOverLifetime;
            vel.enabled = true;
            vel.space = ParticleSystemSimulationSpace.World;
            vel.x = new ParticleSystem.MinMaxCurve(wind.x * 0.1f - 0.08f, wind.x * 0.15f + 0.08f);
            vel.y = new ParticleSystem.MinMaxCurve(0f, 0.05f);
            vel.z = new ParticleSystem.MinMaxCurve(wind.z * 0.1f - 0.08f, wind.z * 0.15f + 0.08f);
            var rot = ps.rotationOverLifetime;
            rot.enabled = true;
            rot.z = new ParticleSystem.MinMaxCurve(-0.05f, 0.05f);
            var col = ps.colorOverLifetime;
            col.enabled = true;
            col.color = Fade(0.25f, 0.7f);
            // slow drift through the second half of the steam life (wispy frames)
            var ts = ps.textureSheetAnimation;
            Flipbook(ps, 8, 8);
            ts.frameOverTime = new ParticleSystem.MinMaxCurve(1f, AnimationCurve.Linear(0, 0.45f, 1, 0.95f));
            var r = ps.GetComponent<ParticleSystemRenderer>();
            r.renderMode = ParticleSystemRenderMode.VerticalBillboard;
            r.maxParticleSize = 4f;
            ps.Play();
            return ps;
        }

        /// <summary>
        /// Water dripping off an edge (awning, pipe, roof gutter) between two world points: random drip sprites falling
        /// under gravity. rate = drips per second per metre of edge.
        /// </summary>
        public static ParticleSystem Drips(Transform parent, Vector3 edgeA, Vector3 edgeB, float rate = 1.5f)
        {
            var m = ParticleMaterial(RainDrips, 0.1f, 1.4f, 0.1f);
            if (m == null) return null;
            var len = Vector3.Distance(edgeA, edgeB);
            var n = Mathf.Clamp(Mathf.RoundToInt(len * rate * 1.6f * Quality(1f, 0.7f, 0.35f)), 2, 60);
            var ps = NewSystem("Drips", parent, (edgeA + edgeB) * 0.5f, n + 2, m);
            var main = ps.main;
            main.startLifetime = new ParticleSystem.MinMaxCurve(1.2f, 1.6f);
            main.startSpeed = 0;
            main.startSize3D = true;
            main.startSizeX = new ParticleSystem.MinMaxCurve(0.03f, 0.05f);
            main.startSizeY = new ParticleSystem.MinMaxCurve(0.09f, 0.16f);
            main.startSizeZ = 1f;
            main.startColor = new Color(0.8f, 0.86f, 0.95f, 0.8f);
            main.gravityModifier = 1f;
            var em = ps.emission;
            em.rateOverTime = len * rate * Quality(1f, 0.7f, 0.35f);
            var shape = ps.shape;
            shape.shapeType = ParticleSystemShapeType.SingleSidedEdge;
            shape.radius = len * 0.5f;
            var d = edgeB - edgeA;
            shape.rotation = new Vector3(0, -Mathf.Atan2(d.z, d.x) * Mathf.Rad2Deg, 0);
            RandomFrame(ps, 2, 2);
            var r = ps.GetComponent<ParticleSystemRenderer>();
            r.renderMode = ParticleSystemRenderMode.VerticalBillboard;
            ps.Play();
            return ps;
        }
    }
}
