using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace EOA
{
    /// <summary>
    /// Static mesh accumulator for the city layers that LevelKit cannot express (custom materials such as the
    /// EOA/CityLights window skins, additive glow decals with vertex colours, harvested neon signage). Geometry is
    /// in Unity space and merged per material and per square cell so frustum and distance culling stay effective.
    /// </summary>
    public sealed class CityBatch
    {
        sealed class Bucket
        {
            public Material Mat;
            public readonly List<Vector3> V = new();
            public readonly List<Vector3> N = new();
            public readonly List<Vector2> UV = new();
            public readonly List<Color> C = new();
            public readonly List<int> T = new();
        }

        readonly Dictionary<(Material, int, int), Bucket> buckets = new();
        readonly float cell;
        readonly bool colors;
        public int Quads { get; private set; }

        public CityBatch(float cellSize, bool vertexColors)
        {
            cell = cellSize;
            colors = vertexColors;
        }

        Bucket Get(Material m, Vector3 p)
        {
            var key = (m, Mathf.FloorToInt(p.x / cell), Mathf.FloorToInt(p.z / cell));
            if (!buckets.TryGetValue(key, out var b)) buckets[key] = b = new Bucket { Mat = m };
            return b;
        }

        static void Tri(Bucket b, int i0, int i1, int i2, Vector3 n)
        {
            var a = b.V[i0];
            if (Vector3.Dot(Vector3.Cross(b.V[i1] - a, b.V[i2] - a), n) >= 0) { b.T.Add(i0); b.T.Add(i1); b.T.Add(i2); }
            else { b.T.Add(i0); b.T.Add(i2); b.T.Add(i1); }
        }

        /// <summary>Quad (corners in order around the edge) facing n; winding is fixed from the normal.</summary>
        public void Quad(Material m, Vector3 p0, Vector3 p1, Vector3 p2, Vector3 p3, Vector3 n, Vector2 uv0, Vector2 uv1, Vector2 uv2, Vector2 uv3, Color col)
        {
            var b = Get(m, (p0 + p2) * 0.5f);
            var i = b.V.Count;
            b.V.Add(p0); b.V.Add(p1); b.V.Add(p2); b.V.Add(p3);
            b.N.Add(n); b.N.Add(n); b.N.Add(n); b.N.Add(n);
            b.UV.Add(uv0); b.UV.Add(uv1); b.UV.Add(uv2); b.UV.Add(uv3);
            if (colors) { b.C.Add(col); b.C.Add(col); b.C.Add(col); b.C.Add(col); }
            Tri(b, i, i + 1, i + 2, n);
            Tri(b, i, i + 2, i + 3, n);
            Quads++;
        }

        /// <summary>
        /// The four vertical sides of an axis-aligned box (Unity XZ rect, y0..y1) facing outward, with UVs in metres:
        /// u runs around the perimeter from u0, v is the height above y0 (window rows line up with floors).
        /// </summary>
        public void BoxSides(Material m, float x0, float z0, float x1, float z1, float y0, float y1, float u0)
        {
            if (y1 <= y0 + 0.1f) return;
            var h = y1 - y0;
            Vector3 a = new(x0, 0, z0), b = new(x1, 0, z0), c = new(x1, 0, z1), d = new(x0, 0, z1);
            var u = u0;
            Side(m, a, b, Vector3.back, y0, h, ref u);
            Side(m, b, c, Vector3.right, y0, h, ref u);
            Side(m, c, d, Vector3.forward, y0, h, ref u);
            Side(m, d, a, Vector3.left, y0, h, ref u);
        }

        /// <summary>A single vertical wall face from a to b (XZ), y0..y0+h, facing n.</summary>
        public void Side(Material m, Vector3 a, Vector3 b, Vector3 n, float y0, float h, ref float u)
        {
            var len = Vector3.Distance(a, b);
            if (len < 0.05f) return;
            var up = Vector3.up;
            Quad(m, a + up * y0, b + up * y0, b + up * (y0 + h), a + up * (y0 + h), n,
                new Vector2(u, 0), new Vector2(u + len, 0), new Vector2(u + len, h), new Vector2(u, h), Color.white);
            u += len;
        }

        /// <summary>Horizontal quad (0..1 UVs) centred at c, sx by sz, rotated by yaw (Unity degrees).</summary>
        public void Ground(Material m, Vector3 c, float sx, float sz, float yawDeg, Color col)
        {
            var q = Quaternion.Euler(0, yawDeg, 0);
            var ax = q * new Vector3(sx * 0.5f, 0, 0);
            var az = q * new Vector3(0, 0, sz * 0.5f);
            Quad(m, c - ax - az, c + ax - az, c + ax + az, c - ax + az, Vector3.up,
                new Vector2(0, 0), new Vector2(1, 0), new Vector2(1, 1), new Vector2(0, 1), col);
        }

        /// <summary>Vertical quad (0..1 UVs) centred at c facing n (horizontal), w by h.</summary>
        public void Upright(Material m, Vector3 c, Vector3 n, float w, float h, Color col)
        {
            n.y = 0;
            n = n.sqrMagnitude > 1e-4f ? n.normalized : Vector3.forward;
            var side = Vector3.Cross(Vector3.up, n) * (w * 0.5f);
            var up = Vector3.up * (h * 0.5f);
            Quad(m, c - side - up, c + side - up, c + side + up, c - side + up, n,
                new Vector2(0, 0), new Vector2(1, 0), new Vector2(1, 1), new Vector2(0, 1), col);
        }

        /// <summary>Two crossed upright quads (beacons and halos that read from any horizontal direction).</summary>
        public void Cross(Material m, Vector3 c, float size, Color col)
        {
            Upright(m, c, Vector3.forward, size, size, col);
            Upright(m, c, Vector3.right, size, size, col);
        }

        /// <summary>Build the meshes (one renderer per material and cell) under parent.</summary>
        public void Finish(Transform parent, string name, bool shadows, List<Renderer> output)
        {
            foreach (var b in buckets.Values)
            {
                if (b.T.Count == 0) continue;
                var mesh = new Mesh { name = name };
                if (b.V.Count > 65000) mesh.indexFormat = IndexFormat.UInt32;
                mesh.SetVertices(b.V);
                mesh.SetNormals(b.N);
                mesh.SetUVs(0, b.UV);
                if (colors) mesh.SetColors(b.C);
                mesh.SetTriangles(b.T, 0);
                mesh.RecalculateBounds();
                mesh.UploadMeshData(true);
                var go = new GameObject(name);
                go.layer = CombatLayers.World;
                go.transform.SetParent(parent, false);
                go.AddComponent<MeshFilter>().sharedMesh = mesh;
                var r = go.AddComponent<MeshRenderer>();
                r.sharedMaterial = b.Mat;
                r.shadowCastingMode = shadows ? ShadowCastingMode.On : ShadowCastingMode.Off;
                r.receiveShadows = shadows;
                r.lightProbeUsage = LightProbeUsage.Off;
                r.reflectionProbeUsage = ReflectionProbeUsage.Off;
                output?.Add(r);
            }
            buckets.Clear();
        }
    }

    /// <summary>
    /// Merges static signage (neon tubes, sign boards, strips) produced by <see cref="CyberCity"/> / <see cref="NeonKit"/>
    /// into combined meshes per material and cell, and converts their spill decals into a vertex-coloured glow batch.
    /// Animated pieces (flickering tubes, holographic adverts, billboards) are left alone.
    /// </summary>
    public static class CityHarvest
    {
        static readonly int BaseColor = Shader.PropertyToID("_BaseColor");

        /// <summary>Move "GlowDecal" quads under root into the glow batch (shared additive material, vertex colours).</summary>
        public static int Decals(Transform root, CityBatch glow, Material glowMat)
        {
            var n = 0;
            var list = root.GetComponentsInChildren<MeshRenderer>(true);
            foreach (var r in list)
            {
                if (r == null || r.gameObject.name != "GlowDecal" || r.GetComponent<KitBillboard>() != null) continue;
                var t = r.transform;
                var m = r.sharedMaterial;
                var c = m != null && m.HasProperty(BaseColor) ? m.GetColor(BaseColor).linear : Color.white;
                var s = t.lossyScale;
                var hx = t.right * (s.x * 0.5f);
                var hy = t.up * (s.y * 0.5f);
                var p = t.position;
                var nrm = -t.forward;
                glow.Quad(glowMat, p - hx - hy, p + hx - hy, p + hx + hy, p - hx + hy, nrm,
                    new Vector2(0, 0), new Vector2(1, 0), new Vector2(1, 1), new Vector2(0, 1), c);
                if (m != null) Object.Destroy(m);
                r.gameObject.SetActive(false);
                Object.Destroy(r.gameObject);
                n++;
            }
            return n;
        }

        /// <summary>
        /// Combine every single-material static MeshRenderer under root (except NeonFlicker tubes, holograms and
        /// billboards) into meshes per material and cell under parent. Returns the number of source renderers merged.
        /// </summary>
        public static int Static(Transform root, Transform parent, float cell, List<Renderer> output)
        {
            var groups = new Dictionary<(Material, int, int), List<CombineInstance>>();
            var counts = new Dictionary<(Material, int, int), int>();
            var merged = 0;
            var toLocal = parent.worldToLocalMatrix;
            foreach (var r in root.GetComponentsInChildren<MeshRenderer>(true))
            {
                if (r == null || !r.gameObject.activeSelf) continue;
                if (r.sharedMaterials.Length != 1 || r.sharedMaterial == null) continue;
                if (r.GetComponent<NeonFlicker>() != null || r.GetComponent<KitBillboard>() != null) continue;
                var mat = r.sharedMaterial;
                if (mat.shader != null && mat.shader.name == "EOA/Hologram") continue;
                if (mat.name == "holo_ad" || r.gameObject.name == "HoloAd" || r.gameObject.name == "GlowDecal") continue;
                var mf = r.GetComponent<MeshFilter>();
                if (mf == null || mf.sharedMesh == null || !mf.sharedMesh.isReadable) continue;
                var p = r.bounds.center;
                var key = (mat, Mathf.FloorToInt(p.x / cell), Mathf.FloorToInt(p.z / cell));
                if (!groups.TryGetValue(key, out var list)) { groups[key] = list = new List<CombineInstance>(); counts[key] = 0; }
                var verts = mf.sharedMesh.vertexCount;
                if (counts[key] + verts > 60000)
                {
                    Emit(parent, mat, list, output);
                    list.Clear();
                    counts[key] = 0;
                }
                list.Add(new CombineInstance { mesh = mf.sharedMesh, subMeshIndex = 0, transform = toLocal * r.localToWorldMatrix });
                counts[key] += verts;
                r.gameObject.SetActive(false);
                Object.Destroy(r.gameObject);
                merged++;
            }
            foreach (var kv in groups) if (kv.Value.Count > 0) Emit(parent, kv.Key.Item1, kv.Value, output);
            return merged;
        }

        static void Emit(Transform parent, Material mat, List<CombineInstance> list, List<Renderer> output)
        {
            var mesh = new Mesh { name = "city_signs" };
            mesh.CombineMeshes(list.ToArray(), true, true);
            mesh.RecalculateBounds();
            mesh.UploadMeshData(true);
            var go = new GameObject("CitySigns");
            go.layer = CombatLayers.World;
            go.transform.SetParent(parent, false);
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var r = go.AddComponent<MeshRenderer>();
            r.sharedMaterial = mat;
            r.shadowCastingMode = ShadowCastingMode.Off;
            r.receiveShadows = false;
            r.lightProbeUsage = LightProbeUsage.Off;
            r.reflectionProbeUsage = ReflectionProbeUsage.Off;
            output?.Add(r);
        }
    }

    /// <summary>
    /// Distance culling for the open city (the fog hides everything past ~230 m; this keeps it from being drawn).
    /// Groups: merged geometry, window skins (visible further: lit windows glow through the fog) and small props.
    /// Prop cells are GameObjects toggled as a whole (their colliders go with them, only ever far from the camera).
    /// Time-sliced, allocation free.
    /// </summary>
    public sealed class CityCuller : MonoBehaviour
    {
        /// <summary>Groups: merged geometry, window skins, small props, complete kit buildings (heavy; nearest only).</summary>
        public const int Geo = 0, Skin = 1, Small = 2, Kit = 3;

        struct Item { public Renderer R; public Bounds B; public int G; public bool On; }
        struct Cell { public GameObject Go; public Bounds B; public int G; public bool On, Cooled; }
        struct Caster { public Renderer R; public Vector3 C; public ShadowCastingMode Mode; public bool On; }

        readonly List<Item> items = new();
        readonly List<Cell> cells = new();
        /// <summary>Small-prop shadow casters: shadows only within <see cref="shadowRadius"/> of the camera.</summary>
        readonly List<Caster> casters = new();
        float shadowRadius = 40f;
        readonly float[] radius = { 260, 420, 160, 190 };
        int cursor;

        public int Renderers => items.Count;
        public int Cells => cells.Count;

        public void SetRadii(float geo, float skin, float small, float kit)
        {
            radius[Geo] = geo; radius[Skin] = skin; radius[Small] = small; radius[Kit] = kit;
        }

        /// <summary>Live cullers (view-distance changes apply without rebuilding the district).</summary>
        public static readonly List<CityCuller> Live = new();
        void OnEnable() { Live.Add(this); CityQuality.ApplyTo(this); }
        void OnDisable() => Live.Remove(this);

        public void Add(Renderer r, int group)
        {
            if (r == null) return;
            items.Add(new Item { R = r, B = r.bounds, G = group, On = true });
        }

        public void AddRange(List<Renderer> list, int group)
        {
            foreach (var r in list) Add(r, group);
        }

        public void AddCell(GameObject go, Bounds b, int group) => cells.Add(new Cell { Go = go, B = b, G = group, On = true });

        public void SetShadowRadius(float r) => shadowRadius = r;

        /// <summary>
        /// Stop managing everything under `root` (a prop that leaves its cell for good, e.g. a parked car the player
        /// drives away): its shadow casters get their original mode back and are no longer toggled by distance.
        /// </summary>
        public void Release(Transform root)
        {
            if (root == null) return;
            for (var i = casters.Count - 1; i >= 0; i--)
            {
                var c = casters[i];
                if (c.R != null && !c.R.transform.IsChildOf(root)) continue;
                if (c.R != null) c.R.shadowCastingMode = c.Mode;
                casters.RemoveAt(i);
            }
            for (var i = items.Count - 1; i >= 0; i--)
            {
                var it = items[i];
                if (it.R != null && !it.R.transform.IsChildOf(root)) continue;
                if (it.R != null) it.R.enabled = true;
                items.RemoveAt(i);
            }
            cursor = 0;
        }

        static void NoPrewarm(GameObject go)
        {
            foreach (var ps in go.GetComponentsInChildren<ParticleSystem>(true))
            {
                var main = ps.main;
                if (main.prewarm) main.prewarm = false;
            }
        }

        /// <summary>
        /// Register the shadow-casting renderers of the small-prop cells (call once the district is built). Street
        /// clutter, vending machines, lanterns and parked cars are many-material props: drawn into every shadow cascade
        /// up to the shadow distance they were most of the shadow pass.
        /// </summary>
        public void CollectShadowCasters()
        {
            casters.Clear();
            foreach (var c in cells)
            {
                if (c.G != Small || c.Go == null) continue;
                foreach (var r in c.Go.GetComponentsInChildren<Renderer>(true))
                    if (r != null && r.shadowCastingMode != ShadowCastingMode.Off && r is not SkinnedMeshRenderer)
                        casters.Add(new Caster { R = r, C = r.bounds.center, Mode = r.shadowCastingMode, On = true });
            }
        }

        Vector3? CameraPos()
        {
            var rig = G.Manager != null ? G.Manager.Cam : null;
            var cam = rig != null && rig.Cam != null ? rig.Cam : Camera.main;
            return cam != null ? cam.transform.position : null;
        }

        void LateUpdate()
        {
            var cp = CameraPos();
            if (!cp.HasValue) return;
            var p = cp.Value;
            var total = items.Count + cells.Count + casters.Count;
            if (total == 0) return;
            var slice = total / 6 + 1;
            for (var k = 0; k < slice; k++)
            {
                if (cursor >= total) cursor = 0;
                if (cursor < items.Count)
                {
                    var it = items[cursor];
                    if (it.R != null)
                    {
                        var r = radius[it.G];
                        var d2 = it.B.SqrDistance(p);
                        var on = it.On ? d2 < (r + 12) * (r + 12) : d2 < r * r;
                        if (on != it.On) { it.On = on; it.R.enabled = on; items[cursor] = it; }
                    }
                }
                else if (cursor >= items.Count + cells.Count)
                {
                    var si = cursor - items.Count - cells.Count;
                    var s = casters[si];
                    if (s.R != null)
                    {
                        var d2 = (s.C - p).sqrMagnitude;
                        var on = s.On ? d2 < (shadowRadius + 6) * (shadowRadius + 6) : d2 < shadowRadius * shadowRadius;
                        if (on != s.On) { s.On = on; s.R.shadowCastingMode = on ? s.Mode : ShadowCastingMode.Off; casters[si] = s; }
                    }
                }
                else
                {
                    var ci = cursor - items.Count;
                    var c = cells[ci];
                    if (c.Go != null)
                    {
                        var r = radius[c.G];
                        var d2 = c.B.SqrDistance(p);
                        var on = c.On ? d2 < (r + 12) * (r + 12) : d2 < r * r;
                        if (on != c.On)
                        {
                            // First time a cell is culled: its particles stop prewarming, or every re-activation would
                            // re-simulate whole lifetimes in one frame (steam plumes: 200+ ms when cells pop back in).
                            if (!on && !c.Cooled) { c.Cooled = true; NoPrewarm(c.Go); }
                            c.On = on; c.Go.SetActive(on); cells[ci] = c;
                        }
                    }
                }
                cursor++;
            }
        }
    }

    /// <summary>Square prop cells (Unity space) parented under one root and registered with the culler.</summary>
    public sealed class CityCells
    {
        readonly Transform root;
        readonly CityCuller culler;
        readonly float size;
        readonly Dictionary<(int, int, int), Transform> map = new();

        public CityCells(Transform parent, CityCuller c, float cellSize)
        {
            var go = new GameObject("Cells");
            go.layer = CombatLayers.World;
            go.transform.SetParent(parent, false);
            root = go.transform;
            culler = c;
            size = cellSize;
        }

        public Transform Cell(Vector3 unityPos, int group)
        {
            var key = (Mathf.FloorToInt(unityPos.x / size), Mathf.FloorToInt(unityPos.z / size), group);
            if (map.TryGetValue(key, out var t)) return t;
            var go = new GameObject($"cell_{group}_{key.Item1}_{key.Item2}");
            go.layer = CombatLayers.World;
            go.transform.SetParent(root, false);
            t = go.transform;
            map[key] = t;
            var c = new Vector3((key.Item1 + 0.5f) * size, 40, (key.Item2 + 0.5f) * size);
            culler.AddCell(go, new Bounds(c, new Vector3(size, 120, size)), group);
            return t;
        }

        /// <summary>Re-parent an object into the cell at its position (world position kept).</summary>
        public GameObject Put(GameObject go, int group)
        {
            if (go != null) go.transform.SetParent(Cell(go.transform.position, group), true);
            return go;
        }
    }

    /// <summary>
    /// A handful of real point lights that follow the player from street lamp to street lamp (the rest of the city
    /// is lit by emissive heads and glow decals). Keeps the zone inside its realtime light budget while lamps near
    /// the player still light characters and wet asphalt. Fades between assignments; allocation free.
    /// </summary>
    public sealed class CityLightPool : MonoBehaviour
    {
        Vector3[] lampPos;
        Color[] lampCol;
        int lampCount;
        Light[] lights;
        int[] slotLamp;
        float[] slotLevel;
        readonly int[] want = new int[16];
        readonly float[] wantD = new float[16];
        float timer, intensity = 60f, range = 18f;

        public void Init(List<Vector3> positions, List<Color> colors, int count, float lampIntensity)
        {
            lampCount = positions.Count;
            lampPos = positions.ToArray();
            lampCol = colors.ToArray();
            count = Mathf.Clamp(count, 0, want.Length);
            intensity = lampIntensity;
            lights = new Light[count];
            slotLamp = new int[count];
            slotLevel = new float[count];
            for (var i = 0; i < count; i++)
            {
                var go = new GameObject("CityLamp" + i);
                go.transform.SetParent(transform, false);
                go.transform.rotation = Quaternion.LookRotation(Vector3.down, Vector3.forward);
                var l = go.AddComponent<Light>();
                // Downward wide spot: street lamps light the street and the walls below their heads (DepthCues gives
                // the nearest ones shadows; a spot costs one shadow slice, a point light six).
                l.type = LightType.Spot;
                l.spotAngle = 150f;
                l.innerSpotAngle = 120f;
                l.range = range;
                l.intensity = 0;
                l.shadows = LightShadows.None;
                l.enabled = false;
                lights[i] = l;
                slotLamp[i] = -1;
            }
        }

        public int Count => lights != null ? lights.Length : 0;

        void Update()
        {
            if (lights == null || lights.Length == 0 || lampCount == 0) return;
            var p = G.Manager != null && G.Manager.Player != null ? G.Manager.Player.Position : (Vector3?)null;
            if (!p.HasValue) return;
            var dt = Time.deltaTime;
            timer -= dt;
            var n = lights.Length;
            if (timer <= 0)
            {
                timer = 0.3f;
                // Nearest n lamps within 42 m (insertion into a small sorted buffer).
                var have = 0;
                for (var i = 0; i < lampCount; i++)
                {
                    var d = (lampPos[i] - p.Value).sqrMagnitude;
                    if (d > 42 * 42) continue;
                    if (have < n) { want[have] = i; wantD[have] = d; have++; }
                    else
                    {
                        var worst = 0;
                        for (var k = 1; k < n; k++) if (wantD[k] > wantD[worst]) worst = k;
                        if (d >= wantD[worst]) continue;
                        want[worst] = i; wantD[worst] = d;
                    }
                }
                for (var k = have; k < n; k++) want[k] = -1;
                // Release slots whose lamp is no longer wanted (they fade out), then hand free slots new lamps.
                for (var s = 0; s < n; s++)
                {
                    if (slotLamp[s] < 0) continue;
                    var keep = false;
                    for (var k = 0; k < n; k++) if (want[k] == slotLamp[s]) { keep = true; want[k] = -2; break; }
                    if (!keep) slotLamp[s] = -1 - slotLamp[s] - 1; // mark as fading (negative, < -1)
                }
                for (var k = 0; k < n; k++)
                {
                    if (want[k] < 0) continue;
                    for (var s = 0; s < n; s++)
                    {
                        if (slotLamp[s] != -1 || slotLevel[s] > 0.01f) continue;
                        slotLamp[s] = want[k];
                        var l = lights[s];
                        l.transform.position = lampPos[want[k]];
                        l.color = lampCol[want[k]];
                        l.enabled = true;
                        break;
                    }
                }
            }
            for (var s = 0; s < n; s++)
            {
                var target = slotLamp[s] >= 0 ? 1f : 0f;
                slotLevel[s] = Mathf.MoveTowards(slotLevel[s], target, dt * 2.5f);
                var l = lights[s];
                l.intensity = intensity * slotLevel[s];
                if (slotLamp[s] < -1 && slotLevel[s] <= 0.01f) { slotLamp[s] = -1; l.enabled = false; }
            }
        }
    }

    /// <summary>
    /// Open-city detail budget per View Distance (and platform). Distances are metres from the camera to the item's
    /// bounds; complete kit buildings swap to their box + window-skin stand-ins past the kit radius.
    /// </summary>
    public static class CityQuality
    {
        public static (float geo, float skin, float small, float kit) Radii { get; private set; } = (260, 380, 120, 150);

        public static void Apply(GraphicsSettings g)
        {
            var web = Application.platform == RuntimePlatform.WebGLPlayer;
            var view = g?.ViewDistance ?? "high";
            Radii = view switch
            {
                "low" => (140f, 150f, 70f, 90f),
                "medium" => (200f, 260f, 100f, 120f),
                _ => g != null && g.Preset == "ultra" ? (300f, 420f, 160f, 190f) : (260f, 380f, 120f, 150f),
            };
            if (web) Radii = (Mathf.Min(Radii.geo, 200f), Mathf.Min(Radii.skin, 260f), Mathf.Min(Radii.small, 90f), Mathf.Min(Radii.kit, 110f));
            ShadowRadius = (g?.Shadows ?? "high") switch { "low" => 18f, "medium" => 28f, _ => g != null && g.Preset == "ultra" ? 60f : 40f };
            if (web) ShadowRadius = Mathf.Min(ShadowRadius, 20f);
            foreach (var c in CityCuller.Live) ApplyTo(c);
        }

        /// <summary>Small-prop shadow radius (m) per Shadows setting.</summary>
        public static float ShadowRadius { get; private set; } = 40f;

        public static void ApplyTo(CityCuller c)
        {
            if (c == null) return;
            c.SetRadii(Radii.geo, Radii.skin, Radii.small, Radii.kit);
            c.SetShadowRadius(ShadowRadius);
        }
    }
}
