using UnityEngine;
using UnityEngine.Rendering;

namespace EOA
{
    /// <summary>
    /// High-end rain for <see cref="Weather"/> built from the Blender FX (blender/fx/scripts):
    ///  * two GPU rain layers (EOA/RainStreaks): a near layer of larger, brighter streaks and a far sheet of fine ones.
    ///    Static quad meshes animated in the vertex shader (world-anchored, wrapped around the camera, wind slant,
    ///    min-pixel-width AA), lit by ambient, the neon field, Forward+ lamps and lightning. Zero CPU per frame.
    ///  * splashes where drops actually land: a few raycasts per frame from above the camera's surroundings place
    ///    crown splashes (side-view flipbook, vertical billboards) on any upward-facing surface (streets, roofs, car
    ///    tops) and impact rings on flat ground; covered spots stay dry. Pooled ParticleSystems fed by Emit.
    ///  * surface globals for road / wall shaders (EOA_RainRipple.hlsl): _EOA_RainRipple (+Params), _EOA_RainDrops,
    ///    _EOA_RainStreaks, _EOA_RainSurfaceParams.
    /// Counts scale with Settings > Effects (rebuilt on change). Returns null from <see cref="Create"/> when the shader
    /// or atlas is missing (Weather then keeps its particle rain).
    /// </summary>
    public sealed class RainField : MonoBehaviour
    {
        static readonly int RippleId = Shader.PropertyToID("_EOA_RainRipple"), RippleParamsId = Shader.PropertyToID("_EOA_RainRippleParams"),
            DropsId = Shader.PropertyToID("_EOA_RainDrops"), StreaksId = Shader.PropertyToID("_EOA_RainStreaks"),
            SurfaceId = Shader.PropertyToID("_EOA_RainSurfaceParams"), AmountId = Shader.PropertyToID("_Amount"),
            VelocityId = Shader.PropertyToID("_Velocity");

        WeatherSettings settings;
        Material nearMat, farMat;
        Mesh nearMesh, farMesh;
        GameObject nearGo, farGo;
        ParticleSystem crowns, rings, drips;
        float rain, splashAcc, dripAcc, gustT, ripplePhase, surfaceTime;
        Vector2 wind;
        uint rng = 0x9E3779B9u;
        string quality;
        public int NearCount { get; private set; }
        public int FarCount { get; private set; }
        public int SplashesPerSecond { get; private set; }
        public int DripsPerSecond { get; private set; }

        public static RainField Create(Transform parent, WeatherSettings s)
        {
            var sh = FxLibrary.RainShader;
            var atlas = FxLibrary.Tex(FxLibrary.RainStreaks);
            if (sh == null || atlas == null) return null;
            var go = new GameObject("RainField");
            go.transform.SetParent(parent, false);
            var f = go.AddComponent<RainField>();
            f.settings = s;
            f.rain = s.Rain;
            f.wind = s.Wind;
            f.Build();
            return f;
        }

        void Build()
        {
            Teardown();
            quality = G.Settings?.Data?.Graphics?.Effects ?? "high";
            // Near streaks around the camera + a mid sheet out to ~30 m; the distant rain is the animated veil in the
            // height fog (EOA/HeightFog) and the rain caught in the lamp cones (EOA/CityFx), never long lines.
            NearCount = FxLibrary.Quality(5200, 3200, 1400);
            FarCount = FxLibrary.Quality(9000, 5200, 2200);
            SplashesPerSecond = FxLibrary.Quality(520, 320, 120);
            DripsPerSecond = FxLibrary.Quality(70, 45, 0);
            var atlas = FxLibrary.Tex(FxLibrary.RainStreaks);
            var tmpl = Resources.Load<Material>(FxLibrary.RainStreaksMaterial);
            Material Mat(string name)
            {
                var m = tmpl != null ? new Material(tmpl) : new Material(FxLibrary.RainShader);
                m.name = name;
                m.SetTexture("_BaseMap", atlas);
                return m;
            }
            // Near: short (1/45 s exposure), hair-thin streaks around and just ahead of the camera; lit almost only by
            // the lamps and signs behind them (forward scattering), a faint ambient floor elsewhere.
            nearMat = Mat("rain_near");
            nearMat.SetVector("_Box", new Vector4(10, 10, 10, 3.5f));
            nearMat.SetVector("_Streak", new Vector4(0.026f, 0.0058f, 1.0f, 0.8f));
            nearMat.SetVector("_Fade", new Vector4(0.3f, 1.0f, 0.6f, 0));
            nearMat.SetVector("_Light", new Vector4(0.5f, 0.9f, 1.0f, 0.6f));
            nearMat.SetVector("_Gust", new Vector4(1.6f, 0.05f, 7f, 0.35f));
            nearMat.SetVector("_Phase", new Vector4(0.66f, 0.3f, 0.45f, 1f));
            // Mid: finer sheet out to ~30 m that dissolves into sheen (sub-pixel drops widen and fade), slightly longer
            // exposure so it reads as motion, faded out before it could form lines.
            farMat = Mat("rain_far");
            farMat.SetVector("_Box", new Vector4(40, 26, 40, 15));
            farMat.SetVector("_Streak", new Vector4(0.02f, 0.006f, 0.85f, 0.42f));
            farMat.SetVector("_Fade", new Vector4(3f, 7f, 0.55f, 32f));
            farMat.SetVector("_Light", new Vector4(0.32f, 1.0f, 1.15f, 0.45f));
            farMat.SetVector("_Gust", new Vector4(1.9f, 0.035f, 7f, 0.25f));
            farMat.SetVector("_Phase", new Vector4(0.7f, 0.35f, 0.3f, 0.8f));
            farMat.renderQueue = nearMat.renderQueue - 1;
            nearMesh = DropMesh(NearCount, 11);
            farMesh = DropMesh(FarCount, 23);
            nearGo = Layer("RainNear", nearMesh, nearMat);
            farGo = Layer("RainFar", farMesh, farMat);
            SetWind(wind);
            SetRain(rain);
            lateApplied = null;
            ApplyLate();

            if (!settings.Indoor)
            {
                var cm = FxLibrary.ParticleMaterial(FxLibrary.RainSplash, 0.12f, 1.5f, 0.15f, 12);
                if (cm != null)
                {
                    crowns = FxLibrary.NewSystem("RainSplashes", transform, Vector3.zero, Mathf.CeilToInt(SplashesPerSecond * 0.45f), cm);
                    var main = crowns.main;
                    main.startLifetime = new ParticleSystem.MinMaxCurve(0.26f, 0.36f);
                    main.startSpeed = 0;
                    FxLibrary.Flipbook(crowns, 4, 4);
                    var r = crowns.GetComponent<ParticleSystemRenderer>();
                    r.renderMode = ParticleSystemRenderMode.VerticalBillboard;
                    r.sortingFudge = -2;
                    crowns.Play();
                }
                var rm = FxLibrary.ParticleMaterial(FxLibrary.RainRing, 0.05f, 1.6f, 0.05f, 11);
                if (rm != null)
                {
                    rings = FxLibrary.NewSystem("RainRings", transform, Vector3.zero, Mathf.CeilToInt(SplashesPerSecond * 0.7f), rm);
                    var main = rings.main;
                    main.startLifetime = new ParticleSystem.MinMaxCurve(0.45f, 0.6f);
                    main.startSpeed = 0;
                    FxLibrary.Flipbook(rings, 4, 4);
                    var r = rings.GetComponent<ParticleSystemRenderer>();
                    r.renderMode = ParticleSystemRenderMode.HorizontalBillboard;
                    rings.Play();
                }
                // Drips falling from the overhangs around the camera (awnings, ledges, skywalks, shelters): drop sprites
                // under gravity, so near water reads in depth against the sheets of rain.
                var dm = DripsPerSecond > 0 ? FxLibrary.ParticleMaterial(FxLibrary.RainDrips, 0.1f, 1.4f, 0.1f) : null;
                if (dm != null)
                {
                    drips = FxLibrary.NewSystem("RainDrips", transform, Vector3.zero, DripsPerSecond * 2, dm);
                    var main = drips.main;
                    main.startSpeed = 0;
                    main.startSize3D = true;
                    main.startSizeX = new ParticleSystem.MinMaxCurve(0.025f, 0.045f);
                    main.startSizeY = new ParticleSystem.MinMaxCurve(0.1f, 0.18f);
                    main.startSizeZ = 1f;
                    main.gravityModifier = 1f;
                    FxLibrary.RandomFrame(drips, 2, 2);
                    drips.GetComponent<ParticleSystemRenderer>().renderMode = ParticleSystemRenderMode.VerticalBillboard;
                    drips.Play();
                }
            }
            PublishStatic();
        }

        GameObject Layer(string name, Mesh mesh, Material mat)
        {
            var go = new GameObject(name) { layer = CityFx.FxLayer };
            go.transform.SetParent(transform, false);
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var r = go.AddComponent<MeshRenderer>();
            r.sharedMaterial = mat;
            r.shadowCastingMode = ShadowCastingMode.Off;
            r.receiveShadows = false;
            r.lightProbeUsage = LightProbeUsage.Off;
            r.reflectionProbeUsage = ReflectionProbeUsage.Off;
            r.allowOcclusionWhenDynamic = false;
            return go;
        }

        /// <summary>N quads sharing nothing: UV0 = corner, UV1 = seed (xyz box position, w per-drop random).</summary>
        static Mesh DropMesh(int count, int seed)
        {
            var rnd = new System.Random(seed);
            var verts = new Vector3[count * 4];
            var uv0 = new Vector2[count * 4];
            var uv1 = new Vector4[count * 4];
            var idx = new int[count * 6];
            for (var i = 0; i < count; i++)
            {
                var s = new Vector4((float)rnd.NextDouble(), (float)rnd.NextDouble(), (float)rnd.NextDouble(), (float)rnd.NextDouble());
                var v = i * 4;
                uv0[v] = new Vector2(-1, 0); uv0[v + 1] = new Vector2(1, 0); uv0[v + 2] = new Vector2(1, 1); uv0[v + 3] = new Vector2(-1, 1);
                for (var k = 0; k < 4; k++) uv1[v + k] = s;
                var t = i * 6;
                idx[t] = v; idx[t + 1] = v + 1; idx[t + 2] = v + 2; idx[t + 3] = v; idx[t + 4] = v + 2; idx[t + 5] = v + 3;
            }
            var m = new Mesh { name = "rain_drops_" + count, indexFormat = count * 4 > 65000 ? IndexFormat.UInt32 : IndexFormat.UInt16 };
            m.SetVertices(verts);
            m.SetUVs(0, uv0);
            m.SetUVs(1, uv1);
            m.SetIndices(idx, MeshTopology.Triangles, 0, false);
            // positions are computed in the shader: never cull
            m.bounds = new Bounds(Vector3.zero, Vector3.one * 100000f);
            m.UploadMeshData(true);
            return m;
        }

        public void SetRain(float r)
        {
            rain = Mathf.Clamp01(r);
            // Light drizzle keeps a fraction of the drops; the far sheet thins faster than the near streaks.
            if (nearMat != null) nearMat.SetFloat(AmountId, Mathf.Clamp01(rain * 1.05f));
            if (farMat != null) farMat.SetFloat(AmountId, Mathf.Clamp01(rain * rain));
            if (nearGo != null) nearGo.SetActive(rain > 0.005f);
            if (farGo != null) farGo.SetActive(rain > 0.005f);
        }

        public void SetWind(Vector2 w)
        {
            wind = w;
            ApplyVelocity(1f);
        }

        void ApplyVelocity(float gust)
        {
            // Prototype wind (x, z) -> Unity (-x, z); drift ~ wind x 0.8 m/s per unit as the old particle rain.
            var v = new Vector3(-wind.x * 0.8f * gust, -11f, wind.y * 0.8f * gust);
            if (nearMat != null) nearMat.SetVector(VelocityId, new Vector4(v.x, v.y, v.z, 0.18f));
            if (farMat != null) farMat.SetVector(VelocityId, new Vector4(v.x * 1.1f, v.y * 0.97f, v.z * 1.1f, 0.22f));
        }

        void PublishStatic()
        {
            var ripple = FxLibrary.Tex(FxLibrary.RainRipple);
            var drops = FxLibrary.Tex(FxLibrary.RainDropsN);
            var streaks = FxLibrary.Tex(FxLibrary.RainSurface);
            if (ripple != null) Shader.SetGlobalTexture(RippleId, ripple);
            if (drops != null) Shader.SetGlobalTexture(DropsId, drops);
            if (streaks != null) Shader.SetGlobalTexture(StreaksId, streaks);
        }

        /// <summary>Per-frame surface globals (ripple frame, rain strengths) for road / wall shaders.</summary>
        public static void PublishSurface(float ripplePos, float rippleStrength, float time, float wetness, float rain)
        {
            Shader.SetGlobalVector(RippleParamsId, new Vector4(ripplePos, 4, 16, rippleStrength));
            Shader.SetGlobalVector(SurfaceId, new Vector4(time, 0.35f, Mathf.Clamp01(wetness) * 0.8f, rain));
        }

        public static void ClearSurface()
        {
            Shader.SetGlobalVector(RippleParamsId, Vector4.zero);
            Shader.SetGlobalVector(SurfaceId, Vector4.zero);
        }

        float Rand()
        {
            rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5;
            return (rng & 0xFFFFFF) / 16777216f;
        }

        public void Tick(float dt, Camera cam, float wetness)
        {
            if ((G.Settings?.Data?.Graphics?.Effects ?? "high") != quality) Build();
            ApplyLate();
            // wind gusts: slow swell of the slant
            gustT += dt;
            ApplyVelocity(1f + 0.35f * Mathf.PerlinNoise(gustT * 0.12f, 3.7f) - 0.12f);
            // ripples keep going a moment after the rain stops
            ripplePhase = (ripplePhase + dt * 15f) % 16f;
            surfaceTime += dt;
            PublishSurface(ripplePhase, settings.Indoor ? 0 : rain, surfaceTime, wetness, settings.Indoor ? 0 : rain);
            if (cam == null || settings.Indoor || rain <= 0.01f) return;
            Drips(dt, cam);
            if (crowns == null && rings == null) return;
            splashAcc += SplashesPerSecond * rain * dt;
            var n = Mathf.Min((int)splashAcc, 32);
            splashAcc -= (int)splashAcc;
            var cp = cam.transform.position;
            var f = cam.transform.forward;
            var fh = new Vector2(f.x, f.z);
            fh = fh.sqrMagnitude > 1e-4f ? fh.normalized : Vector2.up;
            var ep = new ParticleSystem.EmitParams();
            for (var i = 0; i < n; i++)
            {
                // 75 % inside the view wedge (within ~16 m), the rest all around within 9 m
                Vector2 off;
                if (Rand() < 0.75f)
                {
                    var a = (Rand() - 0.5f) * 1.6f;
                    var d = Mathf.Lerp(0.8f, 16f, Mathf.Sqrt(Rand()));
                    var ca = Mathf.Cos(a); var sa = Mathf.Sin(a);
                    off = new Vector2(fh.x * ca - fh.y * sa, fh.x * sa + fh.y * ca) * d;
                }
                else
                {
                    var a = Rand() * Mathf.PI * 2f;
                    off = new Vector2(Mathf.Cos(a), Mathf.Sin(a)) * Mathf.Lerp(0.5f, 9f, Rand());
                }
                var origin = new Vector3(cp.x + off.x, cp.y + 30f, cp.z + off.y);
                if (!Physics.Raycast(origin, Vector3.down, out var hit, 80f, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore)) continue;
                if (hit.normal.y < 0.65f) continue;
                var big = Rand();
                if (crowns != null && Rand() < 0.6f)
                {
                    // the crown's base sits 10 % of the frame below the sprite centre (rain_splash.py camera)
                    // small, short and faint: the wet street and ripples sell the rain, not big crowns
                    ep.startSize = 0.1f + big * big * 0.18f;
                    ep.position = hit.point + hit.normal * 0.005f + Vector3.up * (ep.startSize * 0.1f);
                    ep.startLifetime = 0.2f + big * 0.08f;
                    ep.startColor = new Color(0.74f, 0.8f, 0.88f, 0.42f + big * 0.18f);
                    crowns.Emit(ep, 1);
                }
                if (rings != null && hit.normal.y > 0.9f)
                {
                    ep.position = hit.point + hit.normal * 0.012f;
                    ep.startSize = 0.14f + Rand() * 0.22f;
                    ep.startLifetime = 0.4f + Rand() * 0.15f;
                    ep.startColor = new Color(1, 1, 1, 0.45f);
                    rings.Emit(ep, 1);
                }
            }
        }

        /// <summary>
        /// A few upward probes per frame near the camera (mostly in view) look for an underside within 9 m overhead; a
        /// hit spawns a drip just under it that falls to the ground below (lifetime from the fall height).
        /// </summary>
        void Drips(float dt, Camera cam)
        {
            if (drips == null) return;
            dripAcc += DripsPerSecond * rain * dt;
            var n = Mathf.Min((int)dripAcc, 6);
            dripAcc -= (int)dripAcc;
            if (n <= 0) return;
            var cp = cam.transform.position;
            var f = cam.transform.forward;
            var fh = new Vector2(f.x, f.z);
            fh = fh.sqrMagnitude > 1e-4f ? fh.normalized : Vector2.up;
            var ep = new ParticleSystem.EmitParams();
            for (var i = 0; i < n; i++)
            {
                var a = (Rand() - 0.5f) * 1.9f;
                var d = Mathf.Lerp(1.2f, 14f, Rand());
                var ca = Mathf.Cos(a); var sa = Mathf.Sin(a);
                var off = new Vector2(fh.x * ca - fh.y * sa, fh.x * sa + fh.y * ca) * d;
                var origin = new Vector3(cp.x + off.x, cp.y - 0.6f, cp.z + off.y);
                if (!Physics.Raycast(origin, Vector3.up, out var up, 9f, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore)) continue;
                if (up.normal.y > -0.6f) continue;
                var start = up.point - Vector3.up * 0.04f;
                var fall = Physics.Raycast(start, Vector3.down, out var down, 14f, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore) ? down.distance : 6f;
                ep.position = start;
                ep.velocity = Vector3.down * 0.3f;
                ep.startLifetime = Mathf.Sqrt(2f * fall / 9.81f) + 0.02f;
                ep.startColor = new Color(0.8f, 0.86f, 0.95f, 0.55f + 0.35f * Rand());
                drips.Emit(ep, 1);
            }
        }

        bool? lateApplied;

        /// <summary>
        /// With TAA the streaks are drawn after post-processing (RainLatePass, LightMode EOARainLate): the temporal
        /// resolve would otherwise smear thin fast drops into ghosts or fade them out. Otherwise the normal transparent
        /// pass draws them (tonemapped and bloomed with the scene).
        /// </summary>
        void ApplyLate()
        {
            var late = RainLatePass.Active;
            if (lateApplied == late) return;
            lateApplied = late;
            foreach (var m in new[] { nearMat, farMat })
            {
                if (m == null) continue;
                m.SetShaderPassEnabled("UniversalForward", !late);
                m.SetShaderPassEnabled("EOARainLate", late);
            }
        }

        void Teardown()
        {
            if (nearGo != null) Destroy(nearGo);
            if (farGo != null) Destroy(farGo);
            if (crowns != null) Destroy(crowns.gameObject);
            if (rings != null) Destroy(rings.gameObject);
            if (drips != null) Destroy(drips.gameObject);
            if (nearMesh != null) Destroy(nearMesh);
            if (farMesh != null) Destroy(farMesh);
            if (nearMat != null) Destroy(nearMat);
            if (farMat != null) Destroy(farMat);
            nearGo = farGo = null;
            crowns = rings = drips = null;
        }

        void OnDestroy()
        {
            Teardown();
            ClearSurface();
        }
    }
}
