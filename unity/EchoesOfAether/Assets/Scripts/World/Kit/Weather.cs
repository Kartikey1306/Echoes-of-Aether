using UnityEngine;
using UnityEngine.Rendering;

namespace EOA
{
    /// <summary>Weather config (port of WeatherConfig): rain density 0..1, prototype wind (x, z), lightning interval.</summary>
    public sealed class WeatherSettings
    {
        public float Rain = 1;
        public Vector2 Wind = new(2.5f, 1);
        public bool Lightning = true;
        public Vector2 LightningInterval = new(14, 32);
        /// <summary>Ground height for splash rings (prototype metres).</summary>
        public float SplashHeight = 0.02f;
        public bool Indoor;
    }

    /// <summary>
    /// Rain and lightning for a zone.
    /// Rain: <see cref="RainField"/> (Blender FX): two GPU streak layers (near / far, wind slant and gusts, lit by the
    /// ambient, the neon field, Forward+ lamps and lightning), crown splashes and impact rings placed by raycasts where
    /// drops land, and the surface globals for road / wall shaders (_EOA_RainRipple, _EOA_RainRippleParams,
    /// _EOA_RainDrops, _EOA_RainStreaks, _EOA_RainSurfaceParams; see Shaders/EOA_RainRipple.hlsl). If the FX assets
    /// are missing it falls back to the original particle rain (EOA/CityFx particle mode, neon tinted, fog faded).
    /// Lightning: multi-strike flicker driving the zone <see cref="Atmosphere"/>, the thunder audio (Bus) and the sky
    /// (<see cref="SkyFx"/>: strike direction, cloud illumination around it, distant cloud-to-ground bolts).
    /// Publishes the global wetness (_EOA_Wetness, 0..1) and rain amount (_EOA_RainAmount): soaked while it rains,
    /// drying slowly to damp after it stops.
    /// </summary>
    public sealed class Weather : MonoBehaviour
    {
        public WeatherSettings Settings { get; private set; }
        ParticleSystem rain, splash;
        ParticleSystemRenderer rainR;
        Material rainMat;
        Atmosphere atmosphere;
        float nextFlash, flashT;
        float[] flashSeq;
        float wetness;
        RainField field;
        float boltVis;
        public float Flash { get; private set; }
        /// <summary>The GPU rain (null when the FX assets are missing and the particle fallback is used).</summary>
        public RainField Field => field;
        static Texture2D streakTex, ringTex;

        void OnDestroy()
        {
            CityFx.SetWetness(0, 0);
            SkyFx.Clear();
            RainField.ClearSurface();
        }

        public static Weather Create(Transform zoneRoot, WeatherSettings s, Atmosphere atmosphere)
        {
            var go = new GameObject("Weather");
            go.transform.SetParent(zoneRoot, false);
            var w = go.AddComponent<Weather>();
            w.Settings = s;
            w.atmosphere = atmosphere;
            w.Build();
            return w;
        }

        int QualityCount(int high, int medium, int low)
        {
            var e = G.Settings?.Data?.Graphics?.Effects ?? "high";
            return e == "low" ? low : e == "medium" ? medium : high;
        }

        void Build()
        {
            var s = Settings;
            nextFlash = s.LightningInterval.x * 0.5f;
            wetness = WetTarget();
            CityFx.SetWetness(wetness, s.Indoor ? 0 : s.Rain);
            SkyFx.Clear();
            // Blender FX rain (also built at Rain 0 so SetRain can start a storm later); particle rain as the fallback.
            field = RainField.Create(transform, s);
            if (field != null) return;
            var count = s.Rain <= 0 ? 0 : (int)(QualityCount(9000, 5500, 2800) * s.Rain);
            if (count > 0)
            {
                rain = MakeSystem("Rain", count);
                var main = rain.main;
                main.startLifetime = new ParticleSystem.MinMaxCurve(1.5f, 1.9f);
                main.startSpeed = 0;
                main.startSize3D = false;
                main.startSize = new ParticleSystem.MinMaxCurve(0.012f, 0.02f);
                main.startColor = new Color(0.62f, 0.72f, 0.8f, 0.2f * s.Rain);
                var em = rain.emission;
                em.rateOverTime = count / 1.7f;
                var shape = rain.shape;
                shape.shapeType = ParticleSystemShapeType.Box;
                shape.scale = new Vector3(36, 1, 36);
                var vel = rain.velocityOverLifetime;
                vel.enabled = true;
                vel.space = ParticleSystemSimulationSpace.World;
                // Wind drift = wind × 0.05 × fall speed (prototype shader); X mirrored into Unity space.
                vel.x = new ParticleSystem.MinMaxCurve(-s.Wind.x * 0.8f * 0.85f, -s.Wind.x * 0.8f * 1.15f);
                vel.y = new ParticleSystem.MinMaxCurve(-13f, -19f);
                vel.z = new ParticleSystem.MinMaxCurve(s.Wind.y * 0.8f * 0.85f, s.Wind.y * 0.8f * 1.15f);
                rainR = rain.GetComponent<ParticleSystemRenderer>();
                rainR.renderMode = ParticleSystemRenderMode.Stretch;
                rainR.lengthScale = 2f;
                rainR.velocityScale = 0.042f;
                // Neon-lit streaks (premultiplied additive); plain additive particles if the city shader is unavailable.
                rainMat = CityFx.ParticleMat(StreakTexture, 0f, 0.9f, 0.4f);
                if (rainMat == null) rainMat = FxMaterials.Particle(true, StreakTexture, true);
                rainMat.name = "rain";
                rainR.sharedMaterial = rainMat;
                rainR.shadowCastingMode = ShadowCastingMode.Off;
                rainR.receiveShadows = false;
                rainR.maxParticleSize = 1f;
                rain.Play();

                if (!s.Indoor)
                {
                    var sCount = QualityCount(320, 320, 120);
                    splash = MakeSystem("Splashes", sCount * 2);
                    var sm = splash.main;
                    sm.startLifetime = new ParticleSystem.MinMaxCurve(0.55f, 0.85f);
                    sm.startSpeed = 0;
                    sm.startSize = 1f;
                    sm.startColor = new Color(0.75f, 0.82f, 0.9f, 0.35f * s.Rain);
                    var sem = splash.emission;
                    sem.rateOverTime = sCount * 1.5f;
                    var ss = splash.shape;
                    ss.shapeType = ParticleSystemShapeType.Box;
                    ss.scale = new Vector3(22, 0, 22);
                    var size = splash.sizeOverLifetime;
                    size.enabled = true;
                    size.size = new ParticleSystem.MinMaxCurve(1f, AnimationCurve.Linear(0, 0.05f, 1, 0.37f));
                    var col = splash.colorOverLifetime;
                    col.enabled = true;
                    var grad = new Gradient();
                    grad.SetKeys(new[] { new GradientColorKey(Color.white, 0), new GradientColorKey(Color.white, 1) },
                                 new[] { new GradientAlphaKey(1, 0), new GradientAlphaKey(0, 1) });
                    col.color = grad;
                    var sr = splash.GetComponent<ParticleSystemRenderer>();
                    sr.renderMode = ParticleSystemRenderMode.HorizontalBillboard;
                    sr.sharedMaterial = FxMaterials.Particle(true, RingTexture, true);
                    sr.shadowCastingMode = ShadowCastingMode.Off;
                    sr.receiveShadows = false;
                    splash.Play();
                }
            }
        }

        ParticleSystem MakeSystem(string name, int max)
        {
            var go = new GameObject(name);
            go.transform.SetParent(transform, false);
            var ps = go.AddComponent<ParticleSystem>();
            ps.Stop(true, ParticleSystemStopBehavior.StopEmittingAndClear);
            var main = ps.main;
            main.loop = true;
            main.playOnAwake = false;
            main.maxParticles = max;
            main.simulationSpace = ParticleSystemSimulationSpace.World;
            main.scalingMode = ParticleSystemScalingMode.Shape;
            main.gravityModifier = 0;
            return ps;
        }

        /// <summary>Rain density 0..1 (e.g. dawn after the storm).</summary>
        public void SetRain(float r)
        {
            Settings.Rain = r;
            field?.SetRain(r);
            if (rain != null)
            {
                var em = rain.emission;
                em.enabled = r > 0.01f;
                var main = rain.main;
                main.startColor = new Color(0.62f, 0.72f, 0.8f, 0.2f * r);
            }
            if (splash != null)
            {
                var em = splash.emission;
                em.enabled = r > 0.01f && !Settings.Indoor;
            }
        }

        public void TriggerLightning(float intensity = 1) => TriggerLightning(intensity, null, null);

        /// <summary>
        /// Lightning strike. direction: where in the sky it strikes (world; null = random, often in view);
        /// bolt: show a cloud-to-ground bolt (null = ~2/3 of strikes). Cinematics can aim a strike behind a character.
        /// </summary>
        public void TriggerLightning(float intensity, Vector3? direction, bool? showBolt)
        {
            // Double/triple strike flicker (time, brightness pairs).
            flashSeq = new[] { 0f, intensity, 0.06f, 0.2f * intensity, 0.11f, intensity * 0.8f, 0.3f, 0f };
            flashT = 0;
            // Where it strikes: half the time inside the camera's view, otherwise anywhere around; ~2/3 of the strikes
            // show a cloud-to-ground bolt beyond the far city (the rest light the clouds from inside).
            var cam = Camera.main;
            var yaw = Random.value * Mathf.PI * 2f;
            if (cam != null && Random.value < 0.55f)
            {
                var f = cam.transform.forward;
                yaw = Mathf.Atan2(f.x, f.z) + (Random.value - 0.5f) * 1.3f;
            }
            var el = Random.Range(0.12f, 0.32f);
            var dir = direction ?? new Vector3(Mathf.Sin(yaw) * Mathf.Cos(el), Mathf.Sin(el), Mathf.Cos(yaw) * Mathf.Cos(el));
            var bolt = showBolt ?? Random.value < 0.68f;
            // bolt from the cloud base (17..29 deg, well above the skyline) down behind the city; sprite aspect 1:4
            var top = Random.Range(0.3f, 0.5f);
            SkyFx.SetLightning(dir, 0f, Random.Range(0, 4), 0f, top * Random.Range(0.11f, 0.15f), top);
            boltVis = bolt ? 1f : 0f;
            Bus.Emit(new Lightning { Intensity = intensity });
        }

        /// <summary>Soaked while raining; after the rain stops the city stays damp (0.45) and dries slowly. Indoors: dry.</summary>
        float WetTarget() => Settings.Indoor ? 0f : Settings.Rain > 0.01f ? 0.6f + 0.4f * Settings.Rain : 0.45f;

        void LateUpdate()
        {
            var dt = Time.deltaTime;
            var wt = WetTarget();
            wetness = Mathf.MoveTowards(wetness, wt, dt * (wt > wetness ? 0.08f : 0.01f));
            CityFx.SetWetness(wetness, Settings.Indoor ? 0 : Settings.Rain);
            var cam = Camera.main;
            if (field != null) field.Tick(dt, cam, wetness);
            if (cam != null)
            {
                var p = cam.transform.position;
                if (rain != null) rain.transform.position = new Vector3(p.x, p.y + 15f, p.z);
                if (splash != null) splash.transform.position = new Vector3(p.x, Settings.SplashHeight + 0.01f, p.z);
            }
            if (Settings.Lightning && G.Manager != null && G.Manager.Mode == GameMode.Play && !G.Manager.Paused)
            {
                nextFlash -= dt;
                if (nextFlash <= 0)
                {
                    var iv = Settings.LightningInterval;
                    nextFlash = iv.x + Random.value * (iv.y - iv.x);
                    TriggerLightning(0.6f + Random.value * 0.4f);
                }
            }
            var f = 0f;
            if (flashSeq != null)
            {
                flashT += dt;
                for (var i = 0; i < flashSeq.Length; i += 2) if (flashT >= flashSeq[i]) f = flashSeq[i + 1];
                f *= Mathf.Exp(-((flashT % 0.12f) * 18));
                if (flashT > flashSeq[flashSeq.Length - 2] + 0.2f) flashSeq = null;
            }
            Flash = f * (G.Settings?.Data?.Accessibility?.FlashIntensity ?? 1);
            atmosphere?.SetFlash(Flash);
            // bolt: visible on the strokes (flicker with the flash), gone with the sequence
            SkyFx.SetFlash(Flash, flashSeq != null ? boltVis * Mathf.Clamp01(f * 2.2f) * (G.Settings?.Data?.Accessibility?.FlashIntensity ?? 1) : 0f);
            if (rainMat != null) rainMat.SetColor("_BaseColor", new Color(1 + Flash * 3, 1 + Flash * 3, 1 + Flash * 3, 1 + Flash * 2));
        }

        static Texture2D StreakTexture
        {
            get
            {
                if (streakTex != null) return streakTex;
                streakTex = new Texture2D(8, 64, TextureFormat.RGBA32, false) { name = "rain_streak", wrapMode = TextureWrapMode.Clamp };
                var px = new Color32[8 * 64];
                for (var y = 0; y < 64; y++)
                for (var x = 0; x < 8; x++)
                {
                    var edge = 1 - Mathf.Abs((x + 0.5f) / 8f - 0.5f) * 2;
                    var tail = Mathf.SmoothStep(0, 1, y / 64f / 0.3f);
                    var a = (byte)(Mathf.Clamp01(edge * tail) * 255);
                    px[y * 8 + x] = new Color32(255, 255, 255, a);
                }
                streakTex.SetPixels32(px);
                streakTex.Apply(false, true);
                return streakTex;
            }
        }

        static Texture2D RingTexture
        {
            get
            {
                if (ringTex != null) return ringTex;
                const int n = 64;
                ringTex = new Texture2D(n, n, TextureFormat.RGBA32, false) { name = "splash_ring", wrapMode = TextureWrapMode.Clamp };
                var px = new Color32[n * n];
                for (var y = 0; y < n; y++)
                for (var x = 0; x < n; x++)
                {
                    var r = new Vector2((x + 0.5f) / n - 0.5f, (y + 0.5f) / n - 0.5f).magnitude * 2;
                    var ring = Mathf.SmoothStep(0.75f, 0.9f, r) * (1 - Mathf.SmoothStep(0.92f, 1f, r));
                    px[y * n + x] = new Color32(255, 255, 255, (byte)(Mathf.Clamp01(ring) * 255));
                }
                ringTex.SetPixels32(px);
                ringTex.Apply(false, true);
                return ringTex;
            }
        }
    }
}
