using UnityEngine;
using UnityEngine.Rendering;

namespace EOA
{
    /// <summary>
    /// Pooled 3D weapon effects (no sprites, no per-shot allocations):
    /// <list type="bullet">
    /// <item><see cref="Muzzle"/>: Blender-modelled flash (petals + side star + cone, EOA/HardLight burst mode), random
    /// roll, 3-4 frames, with a short light.</item>
    /// <item><see cref="Impact"/>: 3D spike burst + shock ring at the hit, sparks and light; on world geometry also a
    /// scorch decal with a cooling ember core (<see cref="Decal"/>).</item>
    /// <item><see cref="Casing"/>: spent energy cells (Blender model) ejected from Kael's pistol, bouncing on the ground.</item>
    /// <item><see cref="Parry"/>: deflect / shield-block flare (big burst, ring, gold sparks).</item>
    /// </list>
    /// </summary>
    public sealed class WeaponFx : MonoBehaviour
    {
        const int MaxFlash = 14, MaxBurst = 20, MaxDecal = 40, MaxCasing = 16;

        struct Flash
        {
            public Transform T;
            public MeshRenderer R;
            public float Age, Life, Size;
            public Color Color, Core;
        }

        struct DecalSlot
        {
            public Transform T, Ember;
            public MeshRenderer R, ER;
            public float Age, Life, Size;
            public Color Color;
        }

        struct Cell
        {
            public Transform T;
            public Renderer Glow;
            public Vector3 V, Axis;
            public float Age, Spin, GroundY;
            public int Bounces;
        }

        static WeaponFx instance;
        readonly Flash[] flashes = new Flash[MaxFlash];
        readonly Flash[] bursts = new Flash[MaxBurst];
        readonly DecalSlot[] decals = new DecalSlot[MaxDecal];
        readonly Cell[] cells = new Cell[MaxCasing];
        int flashCursor, burstCursor, decalCursor, cellCursor;
        MaterialPropertyBlock mpb;
        Material flashMat, burstMat, scorchMat, emberMat;
        Mesh quad;
        static Texture2D scorchTex, emberTex;
        static readonly int BaseColorId = Shader.PropertyToID("_BaseColor");
        static readonly RaycastHit[] groundHits = new RaycastHit[1];

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void ResetStatics() => instance = null;

        static WeaponFx Ensure()
        {
            if (instance != null) return instance;
            var go = new GameObject("WeaponFx");
            var cs = CombatSystem.Instance;
            if (cs != null) go.transform.SetParent(cs.transform, false);
            else DontDestroyOnLoad(go);
            instance = go.AddComponent<WeaponFx>();
            return instance;
        }

        void Awake()
        {
            mpb = new MaterialPropertyBlock();
            var flashMesh = WeaponLibrary.FxMesh("muzzle_flash");
            var burstMesh = WeaponLibrary.FxMesh("impact_burst");
            flashMat = WeaponLibrary.HardLight(Color.white, Color.white, 1f, 3, true);
            burstMat = WeaponLibrary.HardLight(Color.white, Color.white, 1f, 3, true);
            for (int i = 0; i < MaxFlash; i++)
            {
                if (flashMesh == null || flashMat == null) break;
                var r = WeaponLibrary.FxRenderer("MuzzleFlash", flashMesh, flashMat, transform, CombatLayers.Projectile);
                r.gameObject.SetActive(false);
                flashes[i] = new Flash { T = r.transform, R = r };
            }
            for (int i = 0; i < MaxBurst; i++)
            {
                if (burstMesh == null || burstMat == null) break;
                var r = WeaponLibrary.FxRenderer("ImpactBurst", burstMesh, burstMat, transform, CombatLayers.Projectile);
                r.gameObject.SetActive(false);
                bursts[i] = new Flash { T = r.transform, R = r };
            }
            // scorch decals: dark burnt mark (alpha) + glowing ember core (additive) that cools
            BuildDecalTextures();
            scorchMat = FxMaterials.Particle(false, scorchTex, false);
            scorchMat.name = "fx_impact_scorch";
            scorchMat.renderQueue = (int)RenderQueue.Transparent - 20;
            emberMat = FxMaterials.Particle(true, emberTex, false);
            emberMat.name = "fx_impact_ember";
            quad = new Mesh { name = "fx_decal_quad" };
            quad.SetVertices(new[] { new Vector3(-0.5f, -0.5f, 0), new Vector3(0.5f, -0.5f, 0), new Vector3(-0.5f, 0.5f, 0), new Vector3(0.5f, 0.5f, 0) });
            quad.SetUVs(0, new[] { new Vector2(0, 0), new Vector2(1, 0), new Vector2(0, 1), new Vector2(1, 1) });
            quad.SetNormals(new[] { Vector3.back, Vector3.back, Vector3.back, Vector3.back });
            quad.SetTriangles(new[] { 0, 2, 1, 1, 2, 3 }, 0);
            quad.RecalculateBounds();
            for (int i = 0; i < MaxDecal; i++)
            {
                var go = new GameObject("ImpactDecal");
                go.layer = CombatLayers.Projectile;
                go.transform.SetParent(transform, false);
                go.AddComponent<MeshFilter>().sharedMesh = quad;
                var r = go.AddComponent<MeshRenderer>();
                r.sharedMaterial = scorchMat;
                r.shadowCastingMode = ShadowCastingMode.Off;
                r.receiveShadows = false;
                r.lightProbeUsage = LightProbeUsage.Off;
                var eg = new GameObject("Ember");
                eg.layer = CombatLayers.Projectile;
                eg.transform.SetParent(go.transform, false);
                eg.transform.localPosition = new Vector3(0, 0, -0.002f);
                eg.AddComponent<MeshFilter>().sharedMesh = quad;
                var er = eg.AddComponent<MeshRenderer>();
                er.sharedMaterial = emberMat;
                er.shadowCastingMode = ShadowCastingMode.Off;
                er.receiveShadows = false;
                er.lightProbeUsage = LightProbeUsage.Off;
                go.SetActive(false);
                decals[i] = new DecalSlot { T = go.transform, Ember = eg.transform, R = r, ER = er };
            }
            for (int i = 0; i < MaxCasing; i++)
            {
                var c = WeaponLibrary.Spawn("energy_cell", transform, CombatLayers.Projectile, out _, null, false);
                if (c == null) break;
                Renderer glow = null;
                foreach (var r in c.GetComponentsInChildren<Renderer>(true)) { glow = r; break; }
                c.SetActive(false);
                cells[i] = new Cell { T = c.transform, Glow = glow };
            }
        }

        static void BuildDecalTextures()
        {
            if (scorchTex != null) return;
            const int N = 128;
            scorchTex = new Texture2D(N, N, TextureFormat.RGBA32, true) { name = "fx_scorch_decal", wrapMode = TextureWrapMode.Clamp };
            emberTex = new Texture2D(N, N, TextureFormat.RGBA32, true) { name = "fx_scorch_ember", wrapMode = TextureWrapMode.Clamp };
            var a = new Color32[N * N];
            var b = new Color32[N * N];
            for (int y = 0; y < N; y++)
                for (int x = 0; x < N; x++)
                {
                    float u = (x + 0.5f) / N * 2f - 1f, v = (y + 0.5f) / N * 2f - 1f;
                    float r = Mathf.Sqrt(u * u + v * v);
                    float ang = Mathf.Atan2(v, u);
                    // ragged burnt edge + radial streaks (splash) + soot noise
                    float rag = 0.62f + 0.12f * Mathf.Sin(ang * 7f + 1.3f) + 0.07f * Mathf.Sin(ang * 13f + 0.4f) + 0.05f * Mathf.Sin(ang * 23f);
                    float streak = Mathf.Pow(Mathf.Abs(Mathf.Sin(ang * 9f + Mathf.Sin(ang * 3f))), 6f) * 0.35f;
                    float edge = Mathf.Clamp01((rag + streak - r) / 0.25f);
                    float soot = Mathf.PerlinNoise(x * 0.11f, y * 0.11f) * 0.5f + Mathf.PerlinNoise(x * 0.31f + 7f, y * 0.31f) * 0.5f;
                    float alpha = edge * (0.55f + 0.45f * soot) * Mathf.Clamp01(1.15f - r * 0.4f);
                    byte g = (byte)(10 + 18 * soot);
                    a[y * N + x] = new Color32(g, (byte)(g * 0.95f), (byte)(g * 0.9f), (byte)(Mathf.Clamp01(alpha) * 235f));
                    float core = Mathf.Exp(-r * r / 0.05f) + 0.35f * Mathf.Exp(-r * r / 0.18f) * soot;
                    float cracks = Mathf.Pow(Mathf.Abs(Mathf.Sin(ang * 5f + r * 9f)), 18f) * Mathf.Clamp01(0.7f - r) * 1.2f;
                    float e = Mathf.Clamp01(core + cracks);
                    b[y * N + x] = new Color32(255, 255, 255, (byte)(e * 255f));
                }
            scorchTex.SetPixels32(a);
            scorchTex.Apply(true, true);
            emberTex.SetPixels32(b);
            emberTex.Apply(true, true);
        }

        // ------------------------------------------------------------------ API

        /// <summary>3D muzzle flash at `pos` firing along `dir`.</summary>
        public static void Muzzle(Vector3 pos, Vector3 dir, Color color, float size = 0.22f)
        {
            var fx = Ensure();
            if (fx.flashMat == null) { VfxManager.Instance?.FlashSprite(pos, size * 4f, color, 0.06f); return; }
            ref var f = ref fx.flashes[fx.flashCursor];
            fx.flashCursor = (fx.flashCursor + 1) % MaxFlash;
            if (f.T == null) return;
            if (dir.sqrMagnitude < 1e-6f) dir = Vector3.forward;
            f.T.SetPositionAndRotation(pos, Quaternion.LookRotation(dir) * Quaternion.Euler(0, 0, Random.value * 360f));
            f.Age = 0f;
            f.Life = 0.06f;
            f.Size = size * Random.Range(0.85f, 1.15f);
            f.Color = color;
            f.Core = Color.Lerp(color, Color.white, 0.7f);
            f.T.gameObject.SetActive(true);
            fx.ApplyFlash(ref f, 1.6f);
            VfxManager.Instance?.LightProto(pos + dir * 0.1f, color, 10f, 0.06f);
        }

        /// <summary>Impact at `pos` (normal = surface / away from the target). `world` adds a scorch decal.</summary>
        public static void Impact(Vector3 pos, Vector3 normal, Color color, float size = 0.35f, bool world = false, Transform surface = null)
        {
            var fx = Ensure();
            if (normal.sqrMagnitude < 1e-6f) normal = Vector3.up;
            normal.Normalize();
            ref var f = ref fx.bursts[fx.burstCursor];
            fx.burstCursor = (fx.burstCursor + 1) % MaxBurst;
            if (f.T != null)
            {
                f.T.SetPositionAndRotation(pos + normal * 0.02f, Quaternion.LookRotation(normal) * Quaternion.Euler(0, 0, Random.value * 360f));
                f.Age = 0f;
                f.Life = 0.14f;
                f.Size = size * Random.Range(0.85f, 1.2f);
                f.Color = color;
                f.Core = Color.Lerp(color, Color.white, 0.65f);
                f.T.gameObject.SetActive(true);
                fx.ApplyFlash(ref f, 2.2f);
            }
            VfxManager.Instance?.SparksDir(pos, normal, 10, color, 5f);
            VfxManager.Instance?.LightProto(pos + normal * 0.15f, color, 14f, 0.1f);
            if (world) Decal(pos, normal, color, size * 0.9f);
        }

        /// <summary>Scorch mark on static geometry with an ember core in the shot's colour; fades over ~7 s.</summary>
        public static void Decal(Vector3 pos, Vector3 normal, Color color, float size = 0.3f)
        {
            var fx = Ensure();
            ref var d = ref fx.decals[fx.decalCursor];
            fx.decalCursor = (fx.decalCursor + 1) % MaxDecal;
            if (d.T == null) return;
            if (normal.sqrMagnitude < 1e-6f) normal = Vector3.up;
            normal.Normalize();
            d.T.SetPositionAndRotation(pos + normal * 0.012f, Quaternion.LookRotation(-normal) * Quaternion.Euler(0, 0, Random.value * 360f));
            d.Size = size * Random.Range(0.8f, 1.25f);
            d.T.localScale = Vector3.one * d.Size;
            d.Age = 0f;
            d.Life = 7f;
            d.Color = color;
            d.T.gameObject.SetActive(true);
            fx.ApplyDecal(ref d);
        }

        /// <summary>Spent energy cell from an ejection port: tumbles, bounces, its glow band cools, then it fades.</summary>
        public static void Casing(Vector3 pos, Quaternion rot, Vector3 vel)
        {
            var fx = Ensure();
            ref var c = ref fx.cells[fx.cellCursor];
            fx.cellCursor = (fx.cellCursor + 1) % MaxCasing;
            if (c.T == null) return;
            c.T.SetPositionAndRotation(pos, rot * Quaternion.Euler(0, 90, 0));
            c.T.localScale = Vector3.one;
            c.V = vel + Random.insideUnitSphere * 0.4f;
            c.Axis = Random.onUnitSphere;
            c.Spin = Random.Range(500f, 1100f);
            c.Age = 0f;
            c.Bounces = 0;
            c.GroundY = Physics.RaycastNonAlloc(pos + Vector3.up * 0.2f, Vector3.down, groundHits, 4f, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore) > 0
                ? groundHits[0].point.y : pos.y - 1.2f;
            c.T.gameObject.SetActive(true);
        }

        /// <summary>Deflect / shield-block flare at `pos` facing `normal`.</summary>
        public static void Parry(Vector3 pos, Vector3 normal, Color color)
        {
            Impact(pos, normal, color, 0.75f);
            var fx = Ensure();
            ref var f = ref fx.bursts[fx.burstCursor];
            fx.burstCursor = (fx.burstCursor + 1) % MaxBurst;
            if (f.T != null)
            {
                f.T.SetPositionAndRotation(pos, Quaternion.LookRotation(-normal) * Quaternion.Euler(0, 0, Random.value * 360f));
                f.Age = 0f;
                f.Life = 0.12f;
                f.Size = 0.55f;
                f.Color = Color.white;
                f.Core = Color.white;
                f.T.gameObject.SetActive(true);
                fx.ApplyFlash(ref f, 2.4f);
            }
            VfxManager.Instance?.SparksDir(pos, normal + Vector3.up * 0.3f, 26, CombatMath.Hex(0xffd890), 9f);
            G.Audio?.Play("parry_spark", pos, 0.8f);
        }

        // ------------------------------------------------------------------ update

        void ApplyFlash(ref Flash f, float intensity)
        {
            float k = f.Age / f.Life;
            float grow = 0.65f + 0.55f * Mathf.Sqrt(Mathf.Clamp01(k * 1.5f));
            f.T.localScale = Vector3.one * f.Size * grow;
            float a = (1f - k * k) * WeaponLibrary.FlashScale;
            mpb.Clear();
            mpb.SetColor(WeaponLibrary.ColorId, FxMaterials.Hdr(f.Color, intensity));
            mpb.SetColor(WeaponLibrary.CoreColorId, FxMaterials.Hdr(f.Core, intensity * 1.6f));
            mpb.SetFloat(WeaponLibrary.AlphaId, a);
            mpb.SetFloat(WeaponLibrary.SeedId, f.Size * 37f);
            f.R.SetPropertyBlock(mpb);
        }

        void ApplyDecal(ref DecalSlot d)
        {
            float k = d.Age / d.Life;
            float fade = k < 0.75f ? 1f : 1f - (k - 0.75f) / 0.25f;
            mpb.Clear();
            mpb.SetColor(BaseColorId, new Color(1f, 1f, 1f, 0.92f * fade));
            d.R.SetPropertyBlock(mpb);
            // ember: shot colour -> orange -> dark over ~1.6 s
            float heat = Mathf.Clamp01(1f - d.Age / 1.6f);
            var c = Color.Lerp(new Color(1f, 0.35f, 0.08f), d.Color, heat * heat);
            var hdr = FxMaterials.Hdr(c, 0.4f + 3.2f * heat * heat);
            hdr.a = heat;
            mpb.Clear();
            mpb.SetColor(BaseColorId, hdr);
            d.ER.SetPropertyBlock(mpb);
            if (d.ER.enabled != heat > 0.01f) d.ER.enabled = heat > 0.01f;
        }

        void Update()
        {
            float dt = Time.deltaTime;
            if (dt <= 0f) return;
            for (int i = 0; i < MaxFlash; i++) TickFlash(ref flashes[i], dt, 1.6f);
            for (int i = 0; i < MaxBurst; i++) TickFlash(ref bursts[i], dt, 2.2f);
            for (int i = 0; i < MaxDecal; i++)
            {
                ref var d = ref decals[i];
                if (d.T == null || !d.T.gameObject.activeSelf) continue;
                d.Age += dt;
                if (d.Age >= d.Life) { d.T.gameObject.SetActive(false); continue; }
                ApplyDecal(ref d);
            }
            for (int i = 0; i < MaxCasing; i++)
            {
                ref var c = ref cells[i];
                if (c.T == null || !c.T.gameObject.activeSelf) continue;
                c.Age += dt;
                if (c.Age > 3.2f) { c.T.gameObject.SetActive(false); continue; }
                c.V.y -= 16f * dt;
                var p = c.T.position + c.V * dt;
                if (p.y < c.GroundY + 0.006f && c.V.y < 0f)
                {
                    p.y = c.GroundY + 0.006f;
                    c.V.y = -c.V.y * 0.38f;
                    c.V.x *= 0.6f;
                    c.V.z *= 0.6f;
                    c.Spin *= 0.55f;
                    if (c.Bounces++ < 2 && c.V.y > 0.35f) G.Audio?.Play("casing_tink", p, 0.35f / (1 + c.Bounces), Random.Range(0.92f, 1.12f));
                    if (c.V.y < 0.25f) c.V.y = 0f;
                }
                c.T.position = p;
                if (c.Spin > 5f) c.T.Rotate(c.Axis, c.Spin * dt, Space.World);
                if (c.Age > 2.6f) c.T.localScale = Vector3.one * Mathf.Clamp01((3.2f - c.Age) / 0.6f);
            }
        }

        void TickFlash(ref Flash f, float dt, float intensity)
        {
            if (f.T == null || !f.T.gameObject.activeSelf) return;
            f.Age += dt;
            if (f.Age >= f.Life) { f.T.gameObject.SetActive(false); return; }
            ApplyFlash(ref f, intensity);
        }

        void OnDestroy()
        {
            if (flashMat != null) Destroy(flashMat);
            if (burstMat != null) Destroy(burstMat);
            if (scorchMat != null) Destroy(scorchMat);
            if (emberMat != null) Destroy(emberMat);
            if (quad != null) Destroy(quad);
            if (instance == this) instance = null;
        }
    }
}
