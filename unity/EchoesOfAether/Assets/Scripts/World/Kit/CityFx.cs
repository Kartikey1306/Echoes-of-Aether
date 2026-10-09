using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace EOA
{
    /// <summary>
    /// Night-city lighting and atmosphere layer (Unity space): global shader parameters, the screen-space height fog,
    /// the neon emitter field that rain / steam / mist pick their colour from, merged additive FX geometry (light cones
    /// under lamps and signs, mist cards, aircraft beacons, haze curtains between skyline layers, LED chase strips),
    /// steam plumes and per-district reflection probes.
    ///
    /// Global shader parameters (also documented in Shaders/EOA_CityFx.hlsl), readable by any shader:
    ///   _EOA_Wetness      float 0 dry .. 1 soaked. Weather eases it with the rain (dawn after the storm ~0.45 and drying).
    ///   _EOA_RainAmount   float current rain density 0..1.
    ///   _EOA_HFog, _EOA_HFogColor, _EOA_HFogGlow, _EOA_HFogGlowDir  height fog (see the hlsl for the layout).
    ///   _EOA_NeonPos[8], _EOA_NeonCol[8], _EOA_NeonCount  nearest neon emitters to the camera (xyz + radius, linear rgb).
    /// </summary>
    public static class CityFx
    {
        /// <summary>Distant skyline (exempt from the per-layer view-distance cull; drawn to the far clip plane).</summary>
        public const int SkylineLayer = 30;
        /// <summary>Transparent city FX (cones, mist, beacons): never in physics, NavMesh or reflection probes.</summary>
        public const int FxLayer = 29;

        public const int ModeCone = 0, ModeMist = 1, ModeBeacon = 2, ModeCurtain = 3, ModeStrip = 4, ModeParticle = 5;

        static readonly int HFogId = Shader.PropertyToID("_EOA_HFog"), HFogColorId = Shader.PropertyToID("_EOA_HFogColor"),
            HFogGlowId = Shader.PropertyToID("_EOA_HFogGlow"), HFogDirId = Shader.PropertyToID("_EOA_HFogGlowDir"),
            WetId = Shader.PropertyToID("_EOA_Wetness"), RainId = Shader.PropertyToID("_EOA_RainAmount");

        static object owner;

        // ------------------------------------------------------------------ globals

        /// <summary>Set the height fog / haze globals from a zone's atmosphere (density 0 turns the fog off).</summary>
        public static void ApplyAtmosphere(AtmosphereSettings s, object who)
        {
            owner = who;
            var dir = new Vector3(-s.HeightFogGlowDir.x, 0, s.HeightFogGlowDir.y);
            dir = dir.sqrMagnitude > 1e-4f ? dir.normalized : Vector3.right;
            Shader.SetGlobalVector(HFogId, new Vector4(s.HeightFogDensity, Mathf.Max(0.001f, s.HeightFogFalloff), s.HeightFogBase, s.HeightFogStart));
            var c = ProtoSpace.Hex(s.HeightFogColor).linear;
            Shader.SetGlobalVector(HFogColorId, new Vector4(c.r, c.g, c.b, s.HeightFogMax));
            var g = ProtoSpace.Hex(s.HeightFogGlow).linear;
            Shader.SetGlobalVector(HFogGlowId, new Vector4(g.r, g.g, g.b, s.HeightFogGlowStrength));
            Shader.SetGlobalVector(HFogDirId, new Vector4(dir.x, 0, dir.z, s.HeightFogGround));
            SetWetness(0, 0);
            NeonField.Clear();
        }

        /// <summary>Turn the city globals off (zone unloaded); ignored if another zone's atmosphere took over.</summary>
        public static void ClearAtmosphere(object who)
        {
            if (owner != who) return;
            owner = null;
            Shader.SetGlobalVector(HFogId, Vector4.zero);
            Shader.SetGlobalVector(HFogGlowId, Vector4.zero);
            NeonField.Clear();
        }

        public static void SetWetness(float wet, float rain)
        {
            Shader.SetGlobalFloat(WetId, Mathf.Clamp01(wet));
            Shader.SetGlobalFloat(RainId, Mathf.Clamp01(rain));
        }

        // ------------------------------------------------------------------ materials

        static Shader fxShader;
        static readonly Dictionary<(int, float, float, float, float, float), Material> mats = new();

        public static Shader FxShader
        {
            get
            {
                if (fxShader != null) return fxShader;
                var t = Resources.Load<Material>("Env/CityFx");
                fxShader = t != null ? t.shader : Shader.Find("EOA/CityFx");
                return fxShader;
            }
        }

        /// <summary>Shared EOA/CityFx material (null when the shader is unavailable: callers skip the effect).</summary>
        public static Material Mat(int mode, float intensity = 1, float soft = 1.5f, float alpha = 0, float neonGain = 0, float nearFade = 2)
        {
            var key = (mode, intensity, soft, alpha, neonGain, nearFade);
            if (mats.TryGetValue(key, out var m) && m != null) return m;
            var sh = FxShader;
            if (sh == null || !sh.isSupported) return null;
            m = new Material(sh) { name = "cityfx_" + mode };
            m.SetFloat("_Mode", mode);
            m.SetFloat("_Intensity", intensity);
            m.SetFloat("_Soft", soft);
            m.SetFloat("_Alpha", alpha);
            m.SetFloat("_NeonGain", neonGain);
            m.SetFloat("_NearFade", nearFade);
            mats[key] = m;
            return m;
        }

        /// <summary>Unshared particle material (EOA/CityFx mode 5) with a texture; premultiplied output.</summary>
        public static Material ParticleMat(Texture tex, float alpha, float neonGain, float soft, float intensity = 1)
        {
            var sh = FxShader;
            if (sh == null || !sh.isSupported) return null;
            var m = new Material(sh) { name = "cityfx_particles" };
            m.SetFloat("_Mode", ModeParticle);
            m.SetFloat("_Intensity", intensity);
            m.SetFloat("_Soft", soft);
            m.SetFloat("_Alpha", alpha);
            m.SetFloat("_NeonGain", neonGain);
            m.SetFloat("_NearFade", 0.6f);
            if (tex != null) m.SetTexture("_BaseMap", tex);
            m.SetColor("_BaseColor", Color.white);
            return m;
        }

        static Color Lin(Color srgb, float k)
        {
            var c = srgb.linear * k;
            c.a = 1;
            return c;
        }

        // ------------------------------------------------------------------ builders (all Unity space)

        /// <summary>Soft light cones under street lamps (lamp head positions as recorded by the street builder).</summary>
        public static int LampCones(FxBatch b, List<Vector3> heads, List<Color> colors, float groundY, float intensity = 0.11f)
        {
            var m = Mat(ModeCone, 1f, 1.2f, 0, 0, 3f);
            if (m == null) return 0;
            for (var i = 0; i < heads.Count; i++)
            {
                var apex = heads[i] + Vector3.up * 0.55f;
                var len = apex.y - groundY;
                if (len < 1.5f) continue;
                b.Cone(m, apex, Vector3.down, len + 0.4f, 0.4f, len * 0.5f, Lin(colors[i], intensity));
            }
            return heads.Count;
        }

        /// <summary>Light spill volume falling from a sign (outward and down from its face).</summary>
        public static void SignVolume(FxBatch b, Vector3 signCenter, Vector3 normal, float width, float groundY, Color color, float intensity = 0.06f)
        {
            var m = Mat(ModeCone, 1f, 1.2f, 0, 0, 3f);
            if (m == null) return;
            var h = signCenter.y - groundY;
            if (h < 1.5f) return;
            var dir = (Vector3.down * h + normal * Mathf.Min(3.2f, h * 0.6f)).normalized;
            b.Cone(m, signCenter + normal * 0.25f, dir, h / Mathf.Max(0.3f, -dir.y) + 0.3f, width * 0.3f, Mathf.Max(1.6f, width * 0.55f), Lin(color, intensity), 10);
        }

        /// <summary>Soft mist card near the ground (tinted by the neon field in the shader).</summary>
        public static void Mist(FxBatch b, Vector3 center, float halfSize, Color baseColor, float density, float phase)
        {
            var m = Mat(ModeMist, 2.2f, 2.5f, 0.25f, 0.06f, 4f);
            if (m == null) return;
            var c = baseColor.linear;
            c.a = density;
            b.Billboard(m, center, halfSize, c, phase);
        }

        /// <summary>Blinking aircraft-warning beacon.</summary>
        public static void Beacon(FxBatch b, Vector3 p, float halfSize, Color color, float phase, float intensity = 6f)
        {
            var m = Mat(ModeBeacon, 1f, 0.5f, 0, 0, 1f);
            if (m == null) return;
            b.Billboard(m, p, halfSize, Lin(color, intensity), phase);
        }

        /// <summary>Arc of glowing haze between skyline layers (centre, radius, angles in radians around +Z).</summary>
        public static void Curtain(FxBatch b, Vector3 center, float radius, float a0, float a1, float y0, float height, Color color, float intensity)
        {
            var m = Mat(ModeCurtain, 1f, 60f, 0, 0, 1f);
            if (m == null) return;
            b.Curtain(m, center, radius, a0, a1, y0, height, Lin(color, intensity), Mathf.Max(4, Mathf.CeilToInt((a1 - a0) * radius / 40f)));
        }

        /// <summary>Vertical LED chase strip (a pair of crossed thin quads so it reads from any side).</summary>
        public static void Strip(FxBatch b, Vector3 bottom, float height, float width, Color color, float phase, float intensity = 2.5f)
        {
            var m = Mat(ModeStrip, 1f, 0.5f, 0, 0, 1f);
            if (m == null) return;
            var col = Lin(color, intensity);
            var top = bottom + Vector3.up * height;
            foreach (var side in new[] { Vector3.right, Vector3.forward })
            {
                var w = side * (width * 0.5f);
                var n = Vector3.Cross(side, Vector3.up);
                b.Quad(m, bottom - w, bottom + w, top + w, top - w, n,
                    new Vector4(phase, 0, 0, 0), new Vector4(phase, 0, 0, 0), new Vector4(phase, height, 0, 0), new Vector4(phase, height, 0, 0), col);
            }
        }

        // ------------------------------------------------------------------ steam

        static Material steamMat;

        /// <summary>Rising steam plume lit by the neon field (premultiplied particles, ~30 alive).</summary>
        public static GameObject SteamPlume(Transform parent, Vector3 pos, float scale, int seed, Vector3 wind)
        {
            if (steamMat == null) steamMat = ParticleMat(FxMaterials.Smoke, 0.45f, 0.9f, 1.2f, 1f);
            if (steamMat == null) return null;
            var go = new GameObject("SteamPlume");
            go.layer = FxLayer;
            go.transform.SetParent(parent, false);
            go.transform.position = pos;
            var ps = go.AddComponent<ParticleSystem>();
            ps.Stop(true, ParticleSystemStopBehavior.StopEmittingAndClear);
            var r = new System.Random(seed);
            var main = ps.main;
            main.loop = true;
            main.playOnAwake = true;
            main.maxParticles = 40;
            main.simulationSpace = ParticleSystemSimulationSpace.World;
            main.startLifetime = new ParticleSystem.MinMaxCurve(3.2f, 4.8f);
            main.startSpeed = 0;
            main.startSize = new ParticleSystem.MinMaxCurve(0.7f * scale, 1.4f * scale);
            main.startRotation = new ParticleSystem.MinMaxCurve(0, Mathf.PI * 2);
            main.startColor = new Color(0.34f, 0.36f, 0.42f, 0.6f);
            main.prewarm = true;
            var em = ps.emission;
            em.rateOverTime = 7f + (float)r.NextDouble() * 3f;
            var shape = ps.shape;
            shape.shapeType = ParticleSystemShapeType.Cone;
            shape.angle = 9;
            shape.radius = 0.25f * scale;
            shape.rotation = new Vector3(-90, 0, 0);
            var vel = ps.velocityOverLifetime;
            vel.enabled = true;
            vel.space = ParticleSystemSimulationSpace.World;
            vel.x = new ParticleSystem.MinMaxCurve(wind.x * 0.25f, wind.x * 0.45f);
            vel.y = new ParticleSystem.MinMaxCurve(0.8f * scale, 1.5f * scale);
            vel.z = new ParticleSystem.MinMaxCurve(wind.z * 0.25f, wind.z * 0.45f);
            var size = ps.sizeOverLifetime;
            size.enabled = true;
            size.size = new ParticleSystem.MinMaxCurve(1f, AnimationCurve.EaseInOut(0, 0.5f, 1, 2.8f));
            var rot = ps.rotationOverLifetime;
            rot.enabled = true;
            rot.z = new ParticleSystem.MinMaxCurve(-0.4f, 0.4f);
            var col = ps.colorOverLifetime;
            col.enabled = true;
            var grad = new Gradient();
            grad.SetKeys(new[] { new GradientColorKey(Color.white, 0), new GradientColorKey(Color.white, 1) },
                         new[] { new GradientAlphaKey(0, 0), new GradientAlphaKey(1, 0.18f), new GradientAlphaKey(0.55f, 0.6f), new GradientAlphaKey(0, 1) });
            col.color = grad;
            var pr = go.GetComponent<ParticleSystemRenderer>();
            pr.renderMode = ParticleSystemRenderMode.Billboard;
            pr.sharedMaterial = steamMat;
            pr.shadowCastingMode = ShadowCastingMode.Off;
            pr.receiveShadows = false;
            pr.maxParticleSize = 2f;
            ps.Play();
            return go;
        }

        // ------------------------------------------------------------------ reflection probes

        /// <summary>
        /// Grid of box-projected realtime reflection probes over a Unity-space XZ rect (wet streets pick up the neon of
        /// their own blocks instead of one zone-wide cube). Probes render lazily, time-sliced over six frames, the first
        /// time the camera comes near them (the distance culler keeps far geometry switched off), via ProbeStreamer.
        /// Importance 0: a zone's own probe (importance 1) wins where they overlap.
        /// </summary>
        public static ProbeStreamer ProbeGrid(Transform parent, Rect area, int nx, int nz, float y, float height, int resolution, float intensity)
        {
            var root = new GameObject("DistrictProbes");
            root.transform.SetParent(parent, false);
            var streamer = root.AddComponent<ProbeStreamer>();
            var cw = area.width / nx;
            var cd = area.height / nz;
            for (var i = 0; i < nx; i++)
            for (var j = 0; j < nz; j++)
            {
                var go = new GameObject($"Probe_{i}_{j}");
                go.transform.SetParent(root.transform, false);
                go.transform.position = new Vector3(area.xMin + (i + 0.5f) * cw, y, area.yMin + (j + 0.5f) * cd);
                var p = go.AddComponent<ReflectionProbe>();
                p.mode = ReflectionProbeMode.Realtime;
                p.refreshMode = ReflectionProbeRefreshMode.ViaScripting;
                p.timeSlicingMode = ReflectionProbeTimeSlicingMode.IndividualFaces;
                p.size = new Vector3(cw + 16, height, cd + 16);
                p.center = new Vector3(0, height * 0.5f - y + 0.5f, 0);
                p.blendDistance = 8;
                p.boxProjection = true;
                p.resolution = resolution;
                p.hdr = true;
                p.intensity = intensity;
                p.importance = 0;
                p.nearClipPlane = 0.5f;
                p.farClipPlane = 260; // perf: each face re-renders the city; fog hides everything past ~230 m
                p.cullingMask = (1 << CombatLayers.World) | (1 << SkylineLayer);
                streamer.Probes.Add(p);
            }
            return streamer;
        }
    }

    /// <summary>Renders each registered probe once, the first time the camera is within Range (one probe at a time).</summary>
    public sealed class ProbeStreamer : MonoBehaviour
    {
        public readonly List<ReflectionProbe> Probes = new();
        public float Range = 60f;
        readonly HashSet<ReflectionProbe> done = new();
        int pending = -1;
        float timer;

        void Update()
        {
            if (pending >= 0)
            {
                if (pending < Probes.Count && Probes[pending] != null && !Probes[pending].IsFinishedRendering(renderId)) return;
                pending = -1;
            }
            timer -= Time.unscaledDeltaTime;
            if (timer > 0) return;
            timer = 0.4f;
            var cam = G.Manager != null && G.Manager.Cam != null ? G.Manager.Cam.Cam : Camera.main;
            if (cam == null || G.Manager == null || G.Manager.Mode != GameMode.Play) return;
            var c = cam.transform.position;
            for (var i = 0; i < Probes.Count; i++)
            {
                var p = Probes[i];
                if (p == null || done.Contains(p)) continue;
                var d = p.transform.position - c;
                d.y = 0;
                if (d.magnitude > Range + Mathf.Max(p.size.x, p.size.z) * 0.5f) continue;
                done.Add(p);
                renderId = p.RenderProbe();
                pending = i;
                return;
            }
        }

        int renderId;
    }

    /// <summary>
    /// Merged FX geometry for EOA/CityFx (per material and square cell, Unity space). UV0/UV1 are float4:
    /// cones/curtains use UV0.xy, billboards UV0 = (corner, half size) and UV1 = (centre, phase), strips UV0 = (phase, metres).
    /// </summary>
    public sealed class FxBatch
    {
        sealed class Bucket
        {
            public Material Mat;
            public readonly List<Vector3> V = new();
            public readonly List<Vector3> N = new();
            public readonly List<Color> C = new();
            public readonly List<Vector4> U0 = new();
            public readonly List<Vector4> U1 = new();
            public readonly List<int> T = new();
            public float Pad;
        }

        readonly Dictionary<(Material, int, int), Bucket> buckets = new();
        readonly float cell;
        public int Count { get; private set; }

        public FxBatch(float cellSize) => cell = cellSize;

        Bucket Get(Material m, Vector3 p)
        {
            var key = (m, Mathf.FloorToInt(p.x / cell), Mathf.FloorToInt(p.z / cell));
            if (!buckets.TryGetValue(key, out var b)) buckets[key] = b = new Bucket { Mat = m };
            return b;
        }

        void Add(Bucket b, Vector3 p, Vector3 n, Color c, Vector4 u0, Vector4 u1)
        {
            b.V.Add(p); b.N.Add(n); b.C.Add(c); b.U0.Add(u0); b.U1.Add(u1);
        }

        /// <summary>Open cone from apex along dir (length), radius r0 at the apex end and r1 at the far end. UV0.y 0..1 along.</summary>
        public void Cone(Material m, Vector3 apex, Vector3 dir, float length, float r0, float r1, Color col, int segs = 14)
        {
            dir.Normalize();
            var a = Vector3.Cross(dir, Mathf.Abs(dir.y) > 0.9f ? Vector3.right : Vector3.up).normalized;
            var bb = Vector3.Cross(dir, a);
            var b = Get(m, apex);
            var i0 = b.V.Count;
            for (var i = 0; i <= segs; i++)
            {
                var ang = i / (float)segs * Mathf.PI * 2;
                var radial = a * Mathf.Cos(ang) + bb * Mathf.Sin(ang);
                var n = (radial * length - dir * (r1 - r0)).normalized;
                Add(b, apex + radial * r0, n, col, new Vector4(i / (float)segs, 0, 0, 0), Vector4.zero);
                Add(b, apex + dir * length + radial * r1, n, col, new Vector4(i / (float)segs, 1, 0, 0), Vector4.zero);
            }
            for (var i = 0; i < segs; i++)
            {
                var k = i0 + i * 2;
                b.T.Add(k); b.T.Add(k + 1); b.T.Add(k + 3);
                b.T.Add(k); b.T.Add(k + 3); b.T.Add(k + 2);
            }
            Count++;
        }

        /// <summary>Camera-facing card expanded in the vertex shader from its centre.</summary>
        public void Billboard(Material m, Vector3 c, float half, Color col, float phase)
        {
            var b = Get(m, c);
            var i0 = b.V.Count;
            Vector2[] corners = { new(-1, -1), new(1, -1), new(1, 1), new(-1, 1) };
            foreach (var q in corners)
                Add(b, c + new Vector3(q.x * half, q.y * half, 0), Vector3.up, col, new Vector4(q.x, q.y, half, 0), new Vector4(c.x, c.y, c.z, phase));
            b.T.Add(i0); b.T.Add(i0 + 1); b.T.Add(i0 + 2);
            b.T.Add(i0); b.T.Add(i0 + 2); b.T.Add(i0 + 3);
            b.Pad = Mathf.Max(b.Pad, half);
            Count++;
        }

        /// <summary>Vertical arc band (inward facing) around centre; angles in radians measured from +Z toward +X.</summary>
        public void Curtain(Material m, Vector3 center, float radius, float a0, float a1, float y0, float height, Color col, int segs)
        {
            var mid = (a0 + a1) * 0.5f;
            var b = Get(m, center + new Vector3(Mathf.Sin(mid), 0, Mathf.Cos(mid)) * radius);
            var i0 = b.V.Count;
            for (var i = 0; i <= segs; i++)
            {
                var t = i / (float)segs;
                var a = Mathf.Lerp(a0, a1, t);
                var d = new Vector3(Mathf.Sin(a), 0, Mathf.Cos(a));
                var p = center + d * radius;
                Add(b, new Vector3(p.x, y0, p.z), -d, col, new Vector4(t, 0, 0, 0), Vector4.zero);
                Add(b, new Vector3(p.x, y0 + height, p.z), -d, col, new Vector4(t, 1, 0, 0), Vector4.zero);
            }
            for (var i = 0; i < segs; i++)
            {
                var k = i0 + i * 2;
                b.T.Add(k); b.T.Add(k + 1); b.T.Add(k + 3);
                b.T.Add(k); b.T.Add(k + 3); b.T.Add(k + 2);
            }
            Count++;
        }

        public void Quad(Material m, Vector3 p0, Vector3 p1, Vector3 p2, Vector3 p3, Vector3 n, Vector4 u0, Vector4 u1, Vector4 u2, Vector4 u3, Color col)
        {
            var b = Get(m, (p0 + p2) * 0.5f);
            var i0 = b.V.Count;
            Add(b, p0, n, col, u0, Vector4.zero);
            Add(b, p1, n, col, u1, Vector4.zero);
            Add(b, p2, n, col, u2, Vector4.zero);
            Add(b, p3, n, col, u3, Vector4.zero);
            b.T.Add(i0); b.T.Add(i0 + 1); b.T.Add(i0 + 2);
            b.T.Add(i0); b.T.Add(i0 + 2); b.T.Add(i0 + 3);
            Count++;
        }

        /// <summary>Build one renderer per material and cell under parent (no shadows, probes or light probes).</summary>
        public void Finish(Transform parent, string name, int layer, List<Renderer> output)
        {
            foreach (var b in buckets.Values)
            {
                if (b.T.Count == 0) continue;
                var mesh = new Mesh { name = name };
                if (b.V.Count > 65000) mesh.indexFormat = IndexFormat.UInt32;
                mesh.SetVertices(b.V);
                mesh.SetNormals(b.N);
                mesh.SetColors(b.C);
                mesh.SetUVs(0, b.U0);
                mesh.SetUVs(1, b.U1);
                mesh.SetTriangles(b.T, 0);
                mesh.RecalculateBounds();
                if (b.Pad > 0)
                {
                    var bounds = mesh.bounds;
                    bounds.Expand(b.Pad * 2.2f);
                    mesh.bounds = bounds;
                }
                mesh.UploadMeshData(true);
                var go = new GameObject(name);
                go.layer = layer;
                go.transform.SetParent(parent, false);
                go.AddComponent<MeshFilter>().sharedMesh = mesh;
                var r = go.AddComponent<MeshRenderer>();
                r.sharedMaterial = b.Mat;
                r.shadowCastingMode = ShadowCastingMode.Off;
                r.receiveShadows = false;
                r.lightProbeUsage = LightProbeUsage.Off;
                r.reflectionProbeUsage = ReflectionProbeUsage.Off;
                output?.Add(r);
            }
            buckets.Clear();
        }
    }

    /// <summary>
    /// Full-screen height fog (EOA/HeightFog) as a renderer on the game camera: a clip-space quad the shader expands
    /// over the whole target, drawn right after the opaques and the sky. Only exists while an outdoor city zone is loaded.
    /// </summary>
    public sealed class HeightFogPass : MonoBehaviour
    {
        static Mesh quad;
        Material mat;

        public static HeightFogPass Attach(Camera cam)
        {
            var existing = cam.GetComponentInChildren<HeightFogPass>(true);
            if (existing != null) Destroy(existing.gameObject);
            var t = Resources.Load<Material>("Env/HeightFog");
            var sh = t != null ? t.shader : Shader.Find("EOA/HeightFog");
            if (sh == null || !sh.isSupported) { Debug.LogWarning("[cityfx] EOA/HeightFog unavailable; no height fog"); return null; }
            if (quad == null)
            {
                quad = new Mesh { name = "heightfog_quad" };
                quad.vertices = new[] { new Vector3(-0.5f, -0.5f, 0), new Vector3(0.5f, -0.5f, 0), new Vector3(0.5f, 0.5f, 0), new Vector3(-0.5f, 0.5f, 0) };
                quad.triangles = new[] { 0, 2, 1, 0, 3, 2 };
                quad.bounds = new Bounds(Vector3.zero, Vector3.one * 100000f);
            }
            var go = new GameObject("HeightFog") { layer = CityFx.FxLayer };
            go.transform.SetParent(cam.transform, false);
            go.transform.localPosition = Vector3.forward * (cam.nearClipPlane + 1f);
            var p = go.AddComponent<HeightFogPass>();
            p.mat = t != null ? new Material(t) : new Material(sh);
            p.mat.name = "height_fog";
            go.AddComponent<MeshFilter>().sharedMesh = quad;
            var r = go.AddComponent<MeshRenderer>();
            r.sharedMaterial = p.mat;
            r.shadowCastingMode = ShadowCastingMode.Off;
            r.receiveShadows = false;
            r.lightProbeUsage = LightProbeUsage.Off;
            r.reflectionProbeUsage = ReflectionProbeUsage.Off;
            r.allowOcclusionWhenDynamic = false;
            return p;
        }

        void OnDestroy()
        {
            if (mat != null) Destroy(mat);
        }
    }

    /// <summary>
    /// Registry of neon emitters (lamp heads, signs, holo adverts) of the current zone; every 0.2 s the 8 nearest to
    /// the camera go to the _EOA_NeonPos/_EOA_NeonCol globals, which rain streaks, steam and mist use to catch the
    /// colour of the signs around them.
    /// </summary>
    public sealed class NeonField : MonoBehaviour
    {
        const int Max = 8;
        static readonly List<Vector4> pos = new();
        static readonly List<Color> col = new();
        static readonly int PosId = Shader.PropertyToID("_EOA_NeonPos"), ColId = Shader.PropertyToID("_EOA_NeonCol"), CountId = Shader.PropertyToID("_EOA_NeonCount");
        readonly Vector4[] outPos = new Vector4[Max];
        readonly Vector4[] outCol = new Vector4[Max];
        readonly float[] bestD = new float[Max];
        readonly int[] best = new int[Max];
        float timer;

        public static int Count => pos.Count;

        public static void Clear()
        {
            pos.Clear();
            col.Clear();
            Shader.SetGlobalFloat(CountId, 0);
        }

        /// <summary>
        /// The neon light reaching a point: summed linear colour of the emitters whose reach covers it (falloff squared),
        /// e.g. to tint a character's rim with the signs around it. Returns false when none reach.
        /// </summary>
        public static bool LightAt(Vector3 p, out Color linear)
        {
            linear = Color.black;
            var any = false;
            for (var i = 0; i < pos.Count; i++)
            {
                var e = pos[i];
                var dx = e.x - p.x; var dy = e.y - p.y; var dz = e.z - p.z;
                var r2 = e.w * e.w;
                var d2 = dx * dx + dy * dy + dz * dz;
                if (d2 >= r2) continue;
                var a = 1f - d2 / r2;
                linear += col[i] * (a * a);
                any = true;
            }
            linear.a = 1;
            return any;
        }

        /// <summary>Register an emitter: Unity position, sRGB colour, strength (linear multiplier) and reach (m).</summary>
        public static void Add(Vector3 p, Color srgb, float strength, float radius)
        {
            pos.Add(new Vector4(p.x, p.y, p.z, radius));
            var c = srgb.linear * strength;
            c.a = 1;
            col.Add(c);
        }

        /// <summary>
        /// Recolour registered emitters (palette regrade): f gets the Unity position and the emitter's sRGB chroma and
        /// returns the new sRGB colour (the strength is kept). Returns how many changed.
        /// </summary>
        public static int Remap(System.Func<Vector3, Color, Color> f)
        {
            var n = 0;
            for (var i = 0; i < col.Count; i++)
            {
                var c = col[i];
                var k = Mathf.Max(c.r, Mathf.Max(c.g, Mathf.Max(c.b, 1e-5f)));
                var srgb = new Color(c.r / k, c.g / k, c.b / k, 1).gamma;
                var p = new Vector3(pos[i].x, pos[i].y, pos[i].z);
                var to = f(p, srgb);
                if (to == srgb) continue;
                // keep the emitter's luminance (not its peak channel: yellow / orange carry far more luminance than magenta)
                var lin = to.linear;
                var lumOld = c.r * 0.2126f + c.g * 0.7152f + c.b * 0.0722f;
                var lumNew = Mathf.Max(lin.r * 0.2126f + lin.g * 0.7152f + lin.b * 0.0722f, 1e-5f);
                var nc = lin * (lumOld * 1.05f / lumNew);
                nc.a = 1;
                col[i] = nc;
                n++;
            }
            return n;
        }

        public static NeonField Ensure(Transform zoneRoot)
        {
            var f = zoneRoot.GetComponent<NeonField>();
            return f != null ? f : zoneRoot.gameObject.AddComponent<NeonField>();
        }

        void Update()
        {
            timer -= Time.unscaledDeltaTime;
            if (timer > 0) return;
            timer = 0.2f;
            var cam = G.Manager != null && G.Manager.Cam != null ? G.Manager.Cam.Cam : Camera.main;
            if (cam == null || pos.Count == 0) { Shader.SetGlobalFloat(CountId, 0); return; }
            var c = cam.transform.position;
            var have = 0;
            for (var i = 0; i < pos.Count; i++)
            {
                var p = pos[i];
                var dx = p.x - c.x; var dy = p.y - c.y; var dz = p.z - c.z;
                var d = dx * dx + dy * dy + dz * dz - p.w * p.w;
                if (have < Max) { best[have] = i; bestD[have] = d; have++; continue; }
                var worst = 0;
                for (var k = 1; k < Max; k++) if (bestD[k] > bestD[worst]) worst = k;
                if (d < bestD[worst]) { best[worst] = i; bestD[worst] = d; }
            }
            for (var k = 0; k < Max; k++)
            {
                if (k < have) { outPos[k] = pos[best[k]]; var cc = col[best[k]]; outCol[k] = new Vector4(cc.r, cc.g, cc.b, 1); }
                else { outPos[k] = new Vector4(0, -9999, 0, 1); outCol[k] = Vector4.zero; }
            }
            Shader.SetGlobalVectorArray(PosId, outPos);
            Shader.SetGlobalVectorArray(ColId, outCol);
            Shader.SetGlobalFloat(CountId, have);
        }

        void OnDestroy() => Shader.SetGlobalFloat(CountId, 0);
    }
}
