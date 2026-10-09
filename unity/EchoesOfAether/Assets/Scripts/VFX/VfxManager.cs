using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace EOA
{
    public enum FxQuality { Low, Medium, High }

    /// <summary>
    /// Pooled visual effects (port of the prototype's VFX.ts). Nothing is allocated during combat:
    /// four shared world-space ParticleSystems (sparks, glow motes, smoke, flash sprites) receive particles
    /// through Emit(), plus pools of shockwave rings, slash arcs, point lights and one echo wave.
    /// Create once at boot: <c>G.Vfx = VfxManager.Create(managerTransform);</c>
    /// Extra (non-IVfx) methods mirror the prototype API; gameplay code can use the static <see cref="FxKit"/> facade.
    /// </summary>
    [DefaultExecutionOrder(100)]
    public sealed class VfxManager : MonoBehaviour, IVfx
    {
        public static VfxManager Instance { get; private set; }

        public FxQuality Quality { get; private set; } = FxQuality.High;

        /// <summary>Particle count multiplier for the current quality (prototype: .4 / .7 / 1).</summary>
        public float CountMul => Quality == FxQuality.Low ? 0.4f : Quality == FxQuality.Medium ? 0.7f : 1f;

        /// <summary>Persistent emitter rate multiplier for the current quality.</summary>
        public float RateMul => CountMul;

        // Particle systems
        ParticleSystem sparksPs, glowPs, smokePs, flashPs;
        ParticleSystem.EmitParams ep;
        readonly List<Material> ownedMaterials = new();

        // Timed mesh effects
        sealed class Timed
        {
            public GameObject Go;
            public Transform T;
            public Material Mat;
            public Mesh Mesh;
            public bool Active;
            public float Time, Dur;
            public float Radius;
            public Color Color;
            // slash
            public Transform Follow;
            public Vector3 LocalOffset;
            public Quaternion LocalRot;
            public bool Mirror;
        }

        readonly List<Timed> rings = new();
        readonly List<Timed> slashes = new();
        Timed echo;
        Color[] slashColors;
        Vector2[] slashUv;
        Color[] echoColors;
        Vector3[] echoNormals;

        sealed class FlashLight
        {
            public Light L;
            public float T = 1, Dur = 1, Peak;
        }

        readonly List<FlashLight> lights = new();
        readonly List<VfxEmitter> emitters = new();
        Transform emitterRoot;
        System.Action unsubscribe;
        Camera cam;

        // ------------------------------------------------------------------ Lifecycle

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void ResetStatics() => Instance = null;

        public static VfxManager Create(Transform parent)
        {
            if (Instance != null) return Instance;
            var go = new GameObject("VFX");
            if (parent != null) go.transform.SetParent(parent, false);
            else if (Application.isPlaying) DontDestroyOnLoad(go);
            return go.AddComponent<VfxManager>();
        }

        void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }
            Instance = this;
            if (G.Vfx == null) G.Vfx = this;
            Build();
            ApplySettings();
            unsubscribe = Bus.On<SettingsChanged>(OnSettingsChanged);
        }

        void OnDestroy()
        {
            unsubscribe?.Invoke();
            if (Instance == this) Instance = null;
            if (ReferenceEquals(G.Vfx, this)) G.Vfx = null;
            foreach (var m in ownedMaterials) if (m != null) Destroy(m);
            foreach (var r in rings) if (r.Mesh != null) Destroy(r.Mesh);
            foreach (var s in slashes) if (s.Mesh != null) Destroy(s.Mesh);
            if (echo != null && echo.Mesh != null) Destroy(echo.Mesh);
        }

        void OnSettingsChanged(SettingsChanged e)
        {
            if (e.Section == null || e.Section == "graphics") ApplySettings();
        }

        string appliedEffects;
        float settingsPoll;

        /// <summary>Re-read the effects quality (low/medium/high) from settings.</summary>
        public void ApplySettings()
        {
            string q = G.Settings?.Data?.Graphics?.Effects ?? "high";
            if (q == appliedEffects) return;
            appliedEffects = q;
            SetQuality(q == "low" ? FxQuality.Low : q == "medium" ? FxQuality.Medium : FxQuality.High);
        }

        public void SetQuality(FxQuality q)
        {
            Quality = q;
            float k = q == FxQuality.Low ? 0.5f : q == FxQuality.Medium ? 0.75f : 1f;
            SetMax(sparksPs, (int)(1200 * k));
            SetMax(glowPs, (int)(900 * k));
            SetMax(smokePs, (int)(500 * k));
            int lightCount = q == FxQuality.Low ? 1 : q == FxQuality.Medium ? 2 : 3;
            for (int i = 0; i < lights.Count; i++)
            {
                if (i >= lightCount)
                {
                    lights[i].T = lights[i].Dur;
                    lights[i].L.enabled = false;
                }
            }
            activeLights = lightCount;
        }

        int activeLights = 3;

        static void SetMax(ParticleSystem ps, int max)
        {
            if (ps == null) return;
            var main = ps.main;
            main.maxParticles = Mathf.Max(16, max);
        }

        float FlashScale
        {
            get
            {
                float f = G.Settings?.Data?.Accessibility?.FlashIntensity ?? 1f;
                return Mathf.Lerp(0.35f, 1f, Mathf.Clamp01(f));
            }
        }

        // ------------------------------------------------------------------ Construction

        void Build()
        {
            float g = Mathf.Max(0.1f, Mathf.Abs(Physics.gravity.y));
            var fade = AlphaFade();
            sparksPs = MakeSystem("Sparks", 1200, Track(FxMaterials.Particle(true, FxMaterials.SoftDot)), ParticleSystemRenderMode.Stretch,
                                  14f / g, 2f, Shrink(0.12f), fade);
            var sr = sparksPs.GetComponent<ParticleSystemRenderer>();
            sr.velocityScale = 0.035f;
            sr.lengthScale = 1.6f;
            glowPs = MakeSystem("Glow", 900, Track(FxMaterials.Particle(true, FxMaterials.SoftDot)), ParticleSystemRenderMode.Billboard,
                                -0.6f / g, 0.6f, Shrink(0.15f), fade);
            smokePs = MakeSystem("Smoke", 500, Track(FxMaterials.Particle(false, FxMaterials.Smoke)), ParticleSystemRenderMode.Billboard,
                                 -0.3f / g, 1.1f, new ParticleSystem.MinMaxCurve(3.2f, AnimationCurve.Linear(0f, 1f / 3.2f, 1f, 1f)), SmokeFade());
            var flashMat = Track(FxMaterials.Particle(true, FxMaterials.Glow));
            flashMat.SetColor("_BaseColor", FxMaterials.Hdr(Color.white, 1.6f));
            flashPs = MakeSystem("Flash", 64, flashMat, ParticleSystemRenderMode.Billboard, 0f, 0f,
                                 new ParticleSystem.MinMaxCurve(1.6f, AnimationCurve.Linear(0f, 1f / 1.6f, 1f, 1f)), LinearFade());

            for (int i = 0; i < 6; i++) rings.Add(MakeMeshFx("Ring", FxMesh.ShockwaveRing(), FxMaterials.Particle(true, FxMaterials.White, true)));
            for (int i = 0; i < 6; i++)
            {
                var s = MakeMeshFx("Slash", FxMesh.SlashArc(), FxMaterials.Particle(true, FxMaterials.White, true));
                slashes.Add(s);
            }
            slashUv = slashes[0].Mesh.uv;
            slashColors = new Color[slashUv.Length];

            echo = MakeMeshFx("EchoWave", FxMesh.DynamicSphere(), FxMaterials.Particle(true, FxMaterials.White, true));
            echoNormals = echo.Mesh.normals;
            echoColors = new Color[echoNormals.Length];

            for (int i = 0; i < 3; i++)
            {
                var go = new GameObject("FlashLight");
                go.transform.SetParent(transform, false);
                var l = go.AddComponent<Light>();
                l.type = LightType.Point;
                l.intensity = 0f;
                l.range = 9f;
                l.shadows = LightShadows.None;
                l.renderMode = LightRenderMode.ForcePixel;
                l.enabled = false;
                lights.Add(new FlashLight { L = l });
            }

            emitterRoot = new GameObject("Emitters").transform;
            emitterRoot.SetParent(transform, false);
        }

        Material Track(Material m)
        {
            ownedMaterials.Add(m);
            return m;
        }

        Timed MakeMeshFx(string name, Mesh mesh, Material mat)
        {
            Track(mat);
            var go = new GameObject(name);
            go.layer = CombatLayers.Default;
            go.transform.SetParent(transform, false);
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var mr = go.AddComponent<MeshRenderer>();
            mr.sharedMaterial = mat;
            mr.shadowCastingMode = ShadowCastingMode.Off;
            mr.receiveShadows = false;
            mr.lightProbeUsage = LightProbeUsage.Off;
            mr.reflectionProbeUsage = ReflectionProbeUsage.Off;
            go.SetActive(false);
            return new Timed { Go = go, T = go.transform, Mat = mat, Mesh = mesh };
        }

        static ParticleSystem.MinMaxCurve Shrink(float endRatio) => new ParticleSystem.MinMaxCurve(1f, AnimationCurve.Linear(0f, 1f, 1f, endRatio));

        /// <summary>Prototype alpha = min(1, remaining * 2.2): opaque until 54.5% of life, then linear to 0.</summary>
        static Gradient AlphaFade()
        {
            var g = new Gradient();
            g.SetKeys(new[] { new GradientColorKey(Color.white, 0f), new GradientColorKey(Color.white, 1f) },
                      new[] { new GradientAlphaKey(1f, 0f), new GradientAlphaKey(1f, 0.545f), new GradientAlphaKey(0f, 1f) });
            return g;
        }

        static Gradient SmokeFade()
        {
            var g = new Gradient();
            g.SetKeys(new[] { new GradientColorKey(Color.white, 0f), new GradientColorKey(Color.white, 1f) },
                      new[] { new GradientAlphaKey(0f, 0f), new GradientAlphaKey(0.85f, 0.08f), new GradientAlphaKey(0.85f, 0.545f), new GradientAlphaKey(0f, 1f) });
            return g;
        }

        static Gradient LinearFade()
        {
            var g = new Gradient();
            g.SetKeys(new[] { new GradientColorKey(Color.white, 0f), new GradientColorKey(Color.white, 1f) },
                      new[] { new GradientAlphaKey(1f, 0f), new GradientAlphaKey(0f, 1f) });
            return g;
        }

        ParticleSystem MakeSystem(string name, int max, Material mat, ParticleSystemRenderMode mode, float gravityMod, float drag,
                                  ParticleSystem.MinMaxCurve size, Gradient alpha)
        {
            var go = new GameObject(name);
            go.layer = CombatLayers.Default;
            go.transform.SetParent(transform, false);
            var ps = go.AddComponent<ParticleSystem>();
            ps.Stop(true, ParticleSystemStopBehavior.StopEmittingAndClear);

            var main = ps.main;
            main.duration = 1f;
            main.loop = true;
            main.playOnAwake = false;
            main.maxParticles = max;
            main.simulationSpace = ParticleSystemSimulationSpace.World;
            main.scalingMode = ParticleSystemScalingMode.Hierarchy;
            main.cullingMode = ParticleSystemCullingMode.AlwaysSimulate;
            main.startLifetime = 1f;
            main.startSpeed = 0f;
            main.startSize = 0.1f;
            main.gravityModifier = gravityMod;

            var emission = ps.emission;
            emission.enabled = false;
            var shape = ps.shape;
            shape.enabled = false;

            var col = ps.colorOverLifetime;
            col.enabled = true;
            col.color = new ParticleSystem.MinMaxGradient(alpha);

            var sol = ps.sizeOverLifetime;
            sol.enabled = true;
            sol.size = size;

            if (drag > 0f)
            {
                var lv = ps.limitVelocityOverLifetime;
                lv.enabled = true;
                lv.limit = 10000f;
                lv.dampen = 0f;
                lv.drag = drag;
                lv.multiplyDragByParticleSize = false;
                lv.multiplyDragByParticleVelocity = false;
            }

            var r = go.GetComponent<ParticleSystemRenderer>();
            r.renderMode = mode;
            r.sharedMaterial = mat;
            r.shadowCastingMode = ShadowCastingMode.Off;
            r.receiveShadows = false;
            r.alignment = ParticleSystemRenderSpace.View;
            r.lightProbeUsage = LightProbeUsage.Off;
            r.reflectionProbeUsage = ReflectionProbeUsage.Off;
            r.minParticleSize = 0f;
            r.maxParticleSize = 2f;

            ps.Play();
            return ps;
        }

        // ------------------------------------------------------------------ Raw emitters

        void Emit(ParticleSystem ps, Vector3 pos, Vector3 vel, float life, float size, Color color, float rotationDeg = 0f)
        {
            if (ps == null) return;
            ep.position = pos;
            ep.velocity = vel;
            ep.startLifetime = life;
            ep.startSize = size;
            ep.startColor = color;
            ep.rotation = rotationDeg;
            ep.applyShapeToPosition = false;
            ps.Emit(ep, 1);
        }

        // Prototype point sizes are screen-scaled; ~0.75 converts them to world metres.
        const float PointToWorld = 0.75f;

        static Vector3 RandUnit(float yBias = -0.5f)
        {
            var v = new Vector3(Random.value - 0.5f, Random.value + yBias, Random.value - 0.5f);
            return v.sqrMagnitude > 1e-6f ? v.normalized : Vector3.up;
        }

        // ------------------------------------------------------------------ Prototype API

        /// <summary>Burst of hot sparks, optionally biased along `dir` (prototype sparks()).</summary>
        public void SparksDir(Vector3 pos, Vector3? dir, int count, Color color, float speed = 7f)
        {
            int n = Mathf.CeilToInt(count * CountMul);
            for (int i = 0; i < n; i++)
            {
                Vector3 v = RandUnit(-0.2f);
                if (dir.HasValue) v = (v + dir.Value * 1.2f).normalized;
                v *= speed * (0.4f + Random.value * 0.8f);
                Emit(sparksPs, pos, v, 0.25f + Random.value * 0.35f, (0.06f + Random.value * 0.05f) * PointToWorld, color);
            }
        }

        /// <summary>Slow rising motes (prototype embers()).</summary>
        public void Embers(Vector3 pos, int count, Color color, float spread = 0.5f, float up = 1.5f)
        {
            int n = Mathf.CeilToInt(count * (Quality == FxQuality.Low ? 0.6f : 1f));
            for (int i = 0; i < n; i++)
            {
                Vector3 p = pos + new Vector3((Random.value - 0.5f) * spread, (Random.value - 0.5f) * spread, (Random.value - 0.5f) * spread);
                Vector3 v = new Vector3((Random.value - 0.5f) * 0.6f, up * (0.5f + Random.value), (Random.value - 0.5f) * 0.6f);
                Emit(glowPs, p, v, 0.6f + Random.value * 0.8f, (0.1f + Random.value * 0.1f) * PointToWorld, color);
            }
        }

        /// <summary>
        /// Big rising flames (burning vehicles, fireballs): `count` additive glow particles of about `size` metres,
        /// scattered over `spread`, rising at `up` m/s in fire colours.
        /// </summary>
        public void Flames(Vector3 pos, float spread, float size, int count, float up = 1.6f)
        {
            if (Quality == FxQuality.Low) count = Mathf.CeilToInt(count / 2f);
            for (int i = 0; i < count; i++)
            {
                Vector3 p = pos + new Vector3((Random.value - 0.5f) * spread, Random.value * 0.3f, (Random.value - 0.5f) * spread);
                Vector3 v = new Vector3((Random.value - 0.5f) * 0.6f * up, up * (0.6f + Random.value * 0.8f), (Random.value - 0.5f) * 0.6f * up);
                float r = Random.value;
                Emit(glowPs, p, v, 0.45f + Random.value * 0.4f, size * (0.6f + Random.value * 0.6f), CombatMath.Hex(r < 0.4f ? 0xff5a18u : r < 0.75f ? 0xff9a38u : 0xffd27au));
            }
        }

        /// <summary>Dark smoke puffs (prototype smokePuff()).</summary>
        public void SmokePuff(Vector3 pos, int count, Color color, float size = 0.8f)
        {
            if (Quality == FxQuality.Low) count = Mathf.CeilToInt(count / 2f);
            for (int i = 0; i < count; i++)
            {
                Vector3 p = pos + new Vector3((Random.value - 0.5f) * 0.6f, Random.value * 0.4f, (Random.value - 0.5f) * 0.6f);
                Vector3 v = new Vector3((Random.value - 0.5f) * 1.2f, 0.6f + Random.value * 0.8f, (Random.value - 0.5f) * 1.2f);
                Emit(smokePs, p, v, 0.8f + Random.value * 0.8f, size * 0.5f * PointToWorld * 1.3f, color, Random.value * 360f);
            }
        }

        /// <summary>
        /// Additive glow sprite that expands 1.6x and fades (prototype flash()). Impacts read sharp, short and coloured
        /// instead of milky: big sizes are compressed, and the flash is a small hot core plus a dimmer coloured halo
        /// (white flashes get a warm halo), so bloom pops the core without whiting out the fighters.
        /// </summary>
        public void FlashSprite(Vector3 pos, float size, Color color, float duration = 0.12f)
        {
            var s = size <= 1.4f ? size : 1.4f + (size - 1.4f) * 0.45f;
            var life = Mathf.Max(0.02f, duration * 0.85f);
            Color.RGBToHSV(color, out _, out var sat, out _);
            var halo = sat < 0.2f ? new Color(1f, 0.7f, 0.42f) : color;
            halo *= 0.55f;
            halo.a = FlashScale * 0.8f;
            Emit(flashPs, pos, Vector3.zero, life * 1.15f, s, halo);
            var core = Color.Lerp(color, Color.white, 0.45f);
            core.a = FlashScale;
            Emit(flashPs, pos, Vector3.zero, life * 0.7f, s * 0.4f, core);
        }

        /// <summary>Pooled point light with quadratic fade. Intensity/range in Unity units.</summary>
        public void Light(Vector3 pos, Color color, float intensity, float range, float duration)
        {
            if (activeLights <= 0) return;
            FlashLight l = lights[0];
            for (int i = 0; i < activeLights; i++)
            {
                if (lights[i].T >= lights[i].Dur) { l = lights[i]; break; }
                if (lights[i].T / lights[i].Dur > l.T / l.Dur) l = lights[i];
            }
            l.L.transform.position = pos;
            l.L.color = color;
            l.L.range = range;
            l.T = 0f;
            l.Dur = Mathf.Max(0.02f, duration);
            l.Peak = intensity * FlashScale;
            l.L.intensity = l.Peak;
            l.L.enabled = true;
        }

        /// <summary>Prototype light(pos, color, peak, dur): converts three.js physical intensity to URP units.</summary>
        public void LightProto(Vector3 pos, Color color, float protoPeak, float duration = 0.18f)
            => Light(pos, color, Mathf.Clamp(protoPeak * 0.055f, 0.2f, 5.5f), 6f + Mathf.Sqrt(Mathf.Max(0f, protoPeak)) * 0.45f, duration);

        Timed Take(List<Timed> pool)
        {
            Timed best = pool[0];
            foreach (var p in pool)
            {
                if (!p.Active) return p;
                if (p.Time / p.Dur > best.Time / best.Dur) best = p;
            }
            return best;
        }

        /// <summary>Expanding ground shockwave ring (prototype shockwave()). Eases out to `radius`.</summary>
        public void Shockwave(Vector3 pos, float radius, Color color, float duration = 0.45f)
        {
            var r = Take(rings);
            r.Active = true;
            r.Time = 0f;
            r.Dur = Mathf.Max(0.02f, duration);
            r.Radius = radius;
            r.Color = color;
            r.T.SetPositionAndRotation(pos + Vector3.up * 0.08f, Quaternion.identity);
            r.T.localScale = Vector3.one * 0.3f;
            r.Mat.SetColor("_BaseColor", FxMaterials.Hdr(color, 2f));
            r.Go.SetActive(true);
        }

        /// <summary>
        /// Energy slash arc. With `follow` set the arc tracks that transform (offset/rotation are local to it),
        /// otherwise pos/yaw/roll are world space. `mirror` reverses the sweep (backhand).
        /// </summary>
        public void SlashArc(Transform follow, Vector3 offset, float yawDeg, float rollDeg, Color color, float radius, float duration, bool mirror)
        {
            var s = Take(slashes);
            s.Active = true;
            s.Time = 0f;
            s.Dur = Mathf.Max(0.02f, duration);
            s.Radius = radius;
            s.Color = color;
            s.Follow = follow;
            s.LocalOffset = offset;
            s.LocalRot = Quaternion.AngleAxis(yawDeg, Vector3.up) * Quaternion.AngleAxis(rollDeg, Vector3.forward);
            s.Mirror = mirror;
            Color lin = color.linear * 2.6f + new Color(0.6f, 0.6f, 0.6f, 0f);
            Color g = lin.gamma;
            g.a = 1f;
            s.Mat.SetColor("_BaseColor", g);
            PlaceSlash(s);
            WriteSlashColors(s, 0f);
            s.Go.SetActive(true);
        }

        void PlaceSlash(Timed s)
        {
            if (s.Follow != null) s.T.SetPositionAndRotation(s.Follow.TransformPoint(s.LocalOffset), s.Follow.rotation * s.LocalRot);
            else if (s.Time <= 0f) s.T.SetPositionAndRotation(s.LocalOffset, s.LocalRot);
            s.T.localScale = new Vector3(s.Mirror ? -s.Radius : s.Radius, s.Radius, s.Radius);
        }

        void WriteSlashColors(Timed s, float k)
        {
            float K = Mathf.Min(1.2f, k * 1.3f);
            float fadeAll = 1f - K * 0.6f;
            for (int i = 0; i < slashUv.Length; i++)
            {
                float along = slashUv[i].x, across = slashUv[i].y;
                float head = CombatMath.SmoothStep(K - 0.55f, K, along) * (along <= K + 0.02f ? 1f : 0f);
                float edge = CombatMath.SmoothStep(0f, 0.25f, across) * CombatMath.SmoothStep(1f, 0.55f, across);
                float a = Mathf.Clamp01(head * edge * fadeAll);
                slashColors[i] = new Color(a, a, a, a);
            }
            s.Mesh.colors = slashColors;
        }

        /// <summary>Echo Sight reveal sphere (prototype echoReveal()).</summary>
        public void EchoReveal(Vector3 pos, float radius, float duration = 1.1f)
        {
            echo.Active = true;
            echo.Time = 0f;
            echo.Dur = Mathf.Max(0.05f, duration);
            echo.Radius = radius;
            echo.T.SetPositionAndRotation(pos, Quaternion.identity);
            echo.T.localScale = Vector3.one * 0.5f;
            echo.Mat.SetColor("_BaseColor", FxMaterials.Hdr(CombatMath.Hex(0x8fd8ff), 2f));
            echo.Go.SetActive(true);
        }

        /// <summary>Large machine explosion (prototype explode(pos, scale, color)).</summary>
        public void Explosion(Vector3 pos, float scale, Color color)
        {
            FlashSprite(pos, 3.2f * scale, CombatMath.Hex(0xffe2b0), 0.18f);
            SparksDir(pos, null, Mathf.RoundToInt(36 * scale), CombatMath.Hex(0xffc070), 10f * scale);
            SparksDir(pos, null, Mathf.RoundToInt(16 * scale), color, 6f * scale);
            SmokePuff(pos, Mathf.RoundToInt(8 * scale), CombatMath.Hex(0x1c1f24), 1.2f * scale);
            LightProto(pos, CombatMath.Hex(0xffb060), 40f * scale, 0.35f);
            Shockwave(pos + Vector3.down * 0.6f, 3f * scale, CombatMath.Hex(0xffb060), 0.35f);
        }

        // ------------------------------------------------------------------ IVfx

        public void Sparks(Vector3 pos, Color color, int count = 12, float speed = 6) => SparksDir(pos, null, count, color, speed);

        public void Impact(Vector3 pos, Vector3 normal, Color color, float scale = 1)
        {
            SparksDir(pos, normal.sqrMagnitude > 1e-6f ? normal.normalized : (Vector3?)null, Mathf.Max(1, Mathf.RoundToInt(12 * scale)), color, 5f * Mathf.Sqrt(Mathf.Max(0.1f, scale)));
            FlashSprite(pos, 1.2f * scale, color, 0.1f);
        }

        public void Explode(Vector3 pos, Color color, float scale = 1) => Explosion(pos, scale, color);

        public void Ring(Vector3 pos, Color color, float radius, float duration = 0.5f) => Shockwave(pos, radius, color, duration);

        public void Slash(Transform attachTo, Vector3 localOffset, float yawDeg, float rollDeg, Color color, float radius = 1.4f, float duration = 0.18f)
            => SlashArc(attachTo, localOffset, yawDeg, rollDeg, color, radius, duration, false);

        /// <summary>Point-light flash (intensity/range in URP units) plus a glow sprite of diameter range * 0.3.</summary>
        public void Flash(Vector3 pos, Color color, float intensity = 6, float range = 6, float duration = 0.12f)
        {
            Light(pos, color, intensity, range, duration);
            FlashSprite(pos, range * 0.3f, color, duration);
        }

        public void EchoWave(Vector3 pos, float radius, float duration) => EchoReveal(pos, radius, duration);

        public void Aether(Vector3 pos, Color color, int count = 20) => Embers(pos, count, color, 0.6f, 1.2f);

        public GameObject Emitter(Vector3 pos, string kind, float rate = 1) => Emitter(pos, kind, rate, 1f);

        /// <summary>
        /// Persistent emitter: fire | sparks | steam | aether. Returns its GameObject (parented under the VFX root);
        /// destroy it (or call <see cref="ClearEmitters"/>) to stop. Re-parent it into a zone to tie it to that scene.
        /// </summary>
        public GameObject Emitter(Vector3 pos, string kind, float rate, float radius)
        {
            var go = new GameObject("Emitter_" + kind);
            go.transform.SetParent(emitterRoot, false);
            go.transform.position = pos;
            var e = go.AddComponent<VfxEmitter>();
            e.Kind = kind;
            e.Rate = rate;
            e.Radius = radius;
            emitters.Add(e);
            return go;
        }

        internal void EmitterTick(string kind, Vector3 p, float radius)
        {
            switch (kind)
            {
                case "fire":
                    Emit(glowPs, new Vector3(p.x + (Random.value - 0.5f) * 0.4f, p.y, p.z + (Random.value - 0.5f) * 0.4f),
                         new Vector3((Random.value - 0.5f) * 0.3f, 1.2f + Random.value, (Random.value - 0.5f) * 0.3f),
                         0.5f + Random.value * 0.4f, 0.35f * PointToWorld, CombatMath.Hex(Random.value < 0.5f ? 0xff7a2au : 0xffb050u));
                    if (Random.value < 0.15f)
                        Emit(smokePs, new Vector3(p.x, p.y + 0.8f, p.z), new Vector3((Random.value - 0.5f) * 0.4f, 1f, (Random.value - 0.5f) * 0.4f),
                             2f, 0.4f * PointToWorld, CombatMath.Hex(0x1a1c20), Random.value * 360f);
                    break;
                case "sparks":
                    if (Random.value < 0.08f) SparksDir(p, Vector3.down, 10, CombatMath.Hex(0xffd890), 4f);
                    break;
                case "steam":
                    Emit(smokePs, new Vector3(p.x + (Random.value - 0.5f) * 0.3f, p.y, p.z + (Random.value - 0.5f) * 0.3f),
                         new Vector3((Random.value - 0.5f) * 0.3f, 1.2f, (Random.value - 0.5f) * 0.3f),
                         1.6f, 0.3f * PointToWorld, CombatMath.Hex(0x8a96a2), Random.value * 360f);
                    break;
                case "aether":
                {
                    float a = Random.value * Mathf.PI * 2f;
                    Emit(glowPs, new Vector3(p.x + Mathf.Cos(a) * radius * Random.value, p.y + Random.value * 0.4f, p.z + Mathf.Sin(a) * radius * Random.value),
                         new Vector3(0f, 0.6f + Random.value * 0.8f, 0f), 1.4f, 0.08f * PointToWorld,
                         CombatMath.Hex(Random.value < 0.6f ? 0x5fd8ffu : 0xa47dffu));
                    break;
                }
            }
        }

        /// <summary>Destroy every persistent emitter.</summary>
        public void ClearEmitters()
        {
            foreach (var e in emitters) if (e != null) Destroy(e.gameObject);
            emitters.Clear();
        }

        /// <summary>Clear every effect and emitter (zone unload).</summary>
        public void Clear()
        {
            foreach (var ps in new[] { sparksPs, glowPs, smokePs, flashPs }) if (ps != null) ps.Clear(true);
            ClearEmitters();
            foreach (var r in rings) { r.Active = false; r.Go.SetActive(false); }
            foreach (var s in slashes) { s.Active = false; s.Follow = null; s.Go.SetActive(false); }
            if (echo != null) { echo.Active = false; echo.Go.SetActive(false); }
            foreach (var l in lights) { l.T = l.Dur; l.L.intensity = 0f; l.L.enabled = false; }
        }

        // ------------------------------------------------------------------ Update

        void LateUpdate()
        {
            // Poll too: Bus.Clear() (menu return) drops the SettingsChanged subscription.
            settingsPoll -= Time.unscaledDeltaTime;
            if (settingsPoll <= 0f)
            {
                settingsPoll = 1f;
                ApplySettings();
            }
            float dt = Time.deltaTime;
            if (dt <= 0f) return;

            foreach (var r in rings)
            {
                if (!r.Active) continue;
                r.Time += dt;
                float k = Mathf.Min(1f, r.Time / r.Dur);
                float e = 1f - Mathf.Pow(1f - k, 3f);
                r.T.localScale = Vector3.one * (0.3f + r.Radius * e);
                var c = FxMaterials.Hdr(r.Color, 2f);
                c.a = 1f - k;
                r.Mat.SetColor("_BaseColor", c);
                if (k >= 1f) { r.Active = false; r.Go.SetActive(false); }
            }

            foreach (var s in slashes)
            {
                if (!s.Active) continue;
                s.Time += dt;
                float k = Mathf.Min(1f, s.Time / s.Dur);
                PlaceSlash(s);
                WriteSlashColors(s, k);
                if (k >= 1f) { s.Active = false; s.Follow = null; s.Go.SetActive(false); }
            }

            if (echo.Active) UpdateEcho(dt);

            for (int i = 0; i < lights.Count; i++)
            {
                var l = lights[i];
                if (l.T < l.Dur)
                {
                    l.T += dt;
                    float k = Mathf.Min(1f, l.T / l.Dur);
                    l.L.intensity = l.Peak * (1f - k) * (1f - k);
                    if (k >= 1f) l.L.enabled = false;
                }
            }

            for (int i = emitters.Count - 1; i >= 0; i--) if (emitters[i] == null) emitters.RemoveAt(i);
        }

        void UpdateEcho(float dt)
        {
            echo.Time += dt;
            float k = Mathf.Min(1f, echo.Time / echo.Dur);
            echo.T.localScale = Vector3.one * (0.5f + echo.Radius * Mathf.Pow(k, 0.7f));
            if (cam == null || !cam.isActiveAndEnabled) cam = Camera.main;
            Vector3 camPos = cam != null ? cam.transform.position : echo.T.position + Vector3.back * 10f;
            Vector3 center = echo.T.position;
            float scale = echo.T.localScale.x;
            float fade = (1f - k) * 0.8f;
            for (int i = 0; i < echoNormals.Length; i++)
            {
                Vector3 n = echoNormals[i];
                Vector3 wp = center + n * scale;
                Vector3 v = (camPos - wp).normalized;
                float f = 1f - Mathf.Abs(Vector3.Dot(n, v));
                float a = f * f * f * fade;
                echoColors[i] = new Color(a, a, a, a);
            }
            echo.Mesh.colors = echoColors;
            if (k >= 1f) { echo.Active = false; echo.Go.SetActive(false); }
        }
    }

    /// <summary>Persistent particle emitter created by <see cref="VfxManager.Emitter(Vector3,string,float,float)"/>.</summary>
    public sealed class VfxEmitter : MonoBehaviour
    {
        public string Kind = "fire";
        public float Rate = 1f;
        public float Radius = 1f;
        float acc;

        void Update()
        {
            var m = VfxManager.Instance;
            float dt = Time.deltaTime;
            if (m == null || dt <= 0f) return;
            acc += dt * Rate * m.RateMul;
            int guard = 0;
            while (acc >= 1f && guard++ < 64)
            {
                acc -= 1f;
                m.EmitterTick(Kind, transform.position, Radius);
            }
        }
    }
}
