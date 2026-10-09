using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;
using static EOA.ProtoSpace;

namespace EOA
{
    /// <summary>
    /// Street-level kit runtime (Assets/Art/CityStreet, blender/city_street): HD street surface materials on the
    /// EOA/StreetSurface shader (wet film, pore water, macro puddles from _EOA_Wetness, anti-tiling, neon glints) built
    /// from the kit's baked maps, and <see cref="StreetSurfaces"/>, the merged ground geometry of the open city (road
    /// tops, gutters, pavement slabs, kerbs, road paint) with world-space UVs. Every material falls back to the
    /// environment kit (or a flat colour) when the street kit has not been built, so the city always renders.
    /// </summary>
    public static class StreetKit
    {
        static readonly Dictionary<string, Material> mats = new();
        static Shader shader;
        static bool shaderChecked;

        public static bool Has(string prefab) => CityKitAssets.Has(prefab);

        static readonly int BaseMap = Shader.PropertyToID("_BaseMap"), BumpMap = Shader.PropertyToID("_BumpMap"),
            Gloss = Shader.PropertyToID("_MetallicGlossMap"), MaskMap = Shader.PropertyToID("_MaskMap"), MacroMap = Shader.PropertyToID("_MacroMap"),
            Tiling = Shader.PropertyToID("_Tiling"), MacroTiling = Shader.PropertyToID("_MacroTiling"), Puddle = Shader.PropertyToID("_PuddleAmount"),
            AntiTile = Shader.PropertyToID("_AntiTile"), AntiRot = Shader.PropertyToID("_AntiTileRot"), AntiOff = Shader.PropertyToID("_AntiTileOffset"),
            Cutoff = Shader.PropertyToID("_Cutoff"), UVMode = Shader.PropertyToID("_UVMode"), MacroStrength = Shader.PropertyToID("_MacroStrength"),
            NormalScale = Shader.PropertyToID("_NormalScale"), NeonReflect = Shader.PropertyToID("_NeonReflect");

        /// <summary>Surface presets: kit material, tile (m), macro map + tile, puddles, anti-tiling rotation / offset, UV mode, alpha clip.</summary>
        struct Preset
        {
            public string Kit, Fallback, Macro;
            public float Tile, MacroTile, Puddles, Rot, Cut, UV, Neon;
            public Vector2 Off;
        }

        static readonly Dictionary<string, Preset> Presets = new()
        {
            ["road"] = new Preset { Kit = "st_asphalt", Fallback = "asphalt", Macro = "st_macro_road", Tile = 6, MacroTile = 48, Puddles = 0.75f, Rot = 1.1f, Off = new Vector2(0.37f, 0.61f), Neon = 0.8f },
            ["road_worn"] = new Preset { Kit = "st_asphalt_worn", Fallback = "asphalt", Macro = "st_macro_road", Tile = 6, MacroTile = 48, Puddles = 0.9f, Rot = 2.3f, Off = new Vector2(0.71f, 0.13f), Neon = 0.8f },
            ["pavers"] = new Preset { Kit = "st_pavers", Fallback = "concrete_wet", Macro = "st_macro_walk", Tile = 3.6f, MacroTile = 40, Puddles = 0.45f, Rot = Mathf.PI / 2, Off = new Vector2(4f / 9f, 2f / 9f), Neon = 0.6f },
            ["slab"] = new Preset { Kit = "st_slab", Fallback = "concrete_wet", Macro = "st_macro_walk", Tile = 3.6f, MacroTile = 40, Puddles = 0.5f, Rot = Mathf.PI / 2, Off = new Vector2(1f / 3f, 2f / 3f), Neon = 0.6f },
            ["curb"] = new Preset { Kit = "st_curb", Fallback = "concrete", Macro = "st_macro_walk", Tile = 2, MacroTile = 40, Puddles = 0, Rot = 0, UV = 1, Neon = 0.3f },
            ["gutter"] = new Preset { Kit = "st_gutter", Fallback = "asphalt", Macro = "st_macro_road", Tile = 8, MacroTile = 48, Puddles = 0, Rot = 0, UV = 1, Neon = 1f },
            ["paint_white"] = new Preset { Kit = "st_paint_white", Fallback = "metal_painted_white", Macro = "st_macro_road", Tile = 2, MacroTile = 48, Puddles = 0.3f, Rot = 0.9f, Off = new Vector2(0.3f, 0.5f), Cut = 0.5f, Neon = 0.5f },
            ["paint_yellow"] = new Preset { Kit = "st_paint_yellow", Fallback = "metal_painted_yellow", Macro = "st_macro_road", Tile = 2, MacroTile = 48, Puddles = 0.3f, Rot = 0.9f, Off = new Vector2(0.3f, 0.5f), Cut = 0.5f, Neon = 0.5f },
        };

        /// <summary>True when the kit's surface materials exist (EOA > Build Environment Library ran on the street kit).</summary>
        public static bool SurfacesBuilt => Resources.Load<Material>("Env/Materials/st_asphalt") != null;

        /// <summary>Street surface material by preset name (road, road_worn, pavers, slab, curb, gutter, paint_white, paint_yellow).</summary>
        public static Material Surface(string preset)
        {
            if (mats.TryGetValue(preset, out var m) && m != null) return m;
            if (!Presets.TryGetValue(preset, out var p)) p = Presets["road"];
            var lit = Resources.Load<Material>("Env/Materials/" + p.Kit);
            if (lit == null) m = EnvMaterials.Get(p.Fallback);
            else
            {
                if (!shaderChecked)
                {
                    shaderChecked = true;
                    shader = Resources.Load<Shader>("CityStreet/EOA_StreetSurface");
                    if (shader == null) shader = Shader.Find("EOA/StreetSurface");
                    if (shader != null && !shader.isSupported) shader = null;
                }
                if (shader == null) m = lit;
                else
                {
                    m = new Material(shader) { name = "street_" + preset, enableInstancing = true };
                    m.SetTexture(BaseMap, lit.GetTexture(BaseMap));
                    m.SetTexture(BumpMap, lit.GetTexture(BumpMap));
                    m.SetTexture(MaskMap, lit.GetTexture(Gloss));
                    var macro = Resources.Load<Texture2D>("CityStreet/" + p.Macro);
                    if (macro != null) m.SetTexture(MacroMap, macro);
                    else m.SetFloat(MacroStrength, 0);
                    m.SetFloat(Tiling, 1f / p.Tile);
                    m.SetFloat(MacroTiling, 1f / p.MacroTile);
                    m.SetFloat(Puddle, p.Puddles);
                    m.SetFloat(AntiTile, p.UV > 0.5f ? 0 : 1);
                    m.SetFloat(AntiRot, p.Rot);
                    m.SetVector(AntiOff, new Vector4(p.Off.x, p.Off.y, 0, 0));
                    m.SetFloat(Cutoff, p.Cut);
                    m.SetFloat(UVMode, p.UV);
                    m.SetFloat(NeonReflect, p.Neon);
                    if (p.Cut > 0) m.renderQueue = (int)RenderQueue.AlphaTest;
                }
            }
            mats[preset] = m;
            return m;
        }

        /// <summary>Pavement material of a district (Asian-style pavers in the dense quarters, poured slabs elsewhere).</summary>
        public static string Pavement(CityDistrict d) => d == CityDistrict.ArcologyGate || d == CityDistrict.FoundryRow ? "slab" : "pavers";
    }

    /// <summary>
    /// Merged ground geometry of the open city: road tops, intersections, gutter strips, pavement tops, kerbs with a
    /// chamfered profile, road paint. Prototype coordinates in, Unity out; merged per material and 64 m cell into
    /// static meshes parented into the city's culling cells. Pavement edges are resolved at <see cref="Finish"/>:
    /// a kerb wherever a slab edge does not touch another slab of the same height.
    /// </summary>
    public sealed class StreetSurfaces
    {
        /// <summary>The batch of the city being built (set by CityStreets.Roads, finished by CityStreets.RoadDressing).</summary>
        public static StreetSurfaces Current;

        const float Cell = 64f;

        sealed class Bucket
        {
            public Material Mat;
            public bool Shadow;
            public readonly List<Vector3> V = new();
            public readonly List<Vector3> N = new();
            public readonly List<Vector2> UV = new();
            public readonly List<int> T = new();
        }

        readonly Dictionary<(Material, int, int), Bucket> buckets = new();
        readonly List<(PRect r, float top, string preset)> slabs = new();
        public int Quads { get; private set; }

        Bucket Get(Material m, Vector3 p, bool shadow)
        {
            var key = (m, Mathf.FloorToInt(p.x / Cell), Mathf.FloorToInt(p.z / Cell));
            if (!buckets.TryGetValue(key, out var b)) buckets[key] = b = new Bucket { Mat = m, Shadow = shadow };
            return b;
        }

        /// <summary>Quad in Unity space (corners in order), facing n, explicit UVs.</summary>
        public void Quad(Material m, Vector3 a, Vector3 b, Vector3 c, Vector3 d, Vector3 n, Vector2 ua, Vector2 ub, Vector2 uc, Vector2 ud, bool shadow = false)
        {
            if (m == null) return;
            var k = Get(m, (a + c) * 0.5f, shadow);
            var i = k.V.Count;
            k.V.Add(a); k.V.Add(b); k.V.Add(c); k.V.Add(d);
            k.N.Add(n); k.N.Add(n); k.N.Add(n); k.N.Add(n);
            k.UV.Add(ua); k.UV.Add(ub); k.UV.Add(uc); k.UV.Add(ud);
            var face = Vector3.Cross(b - a, c - a);
            if (Vector3.Dot(face, n) >= 0) { k.T.Add(i); k.T.Add(i + 1); k.T.Add(i + 2); k.T.Add(i); k.T.Add(i + 2); k.T.Add(i + 3); }
            else { k.T.Add(i); k.T.Add(i + 2); k.T.Add(i + 1); k.T.Add(i); k.T.Add(i + 3); k.T.Add(i + 2); }
            Quads++;
        }

        /// <summary>Horizontal rectangle (prototype rect) at height y, UV = world metres (Unity x, z). Long rects are split
        /// into ≤ 32 m pieces so they fall into the right culling cells.</summary>
        public void Top(Material m, PRect r, float y)
        {
            const float step = 32f;
            for (var x0 = r.X0; x0 < r.X1 - 0.001f; x0 += step)
            for (var z0 = r.Z0; z0 < r.Z1 - 0.001f; z0 += step)
            {
                var x1 = Mathf.Min(r.X1, x0 + step);
                var z1 = Mathf.Min(r.Z1, z0 + step);
                Vector3 a = V(x0, y, z0), b = V(x1, y, z0), c = V(x1, y, z1), d = V(x0, y, z1);
                Quad(m, a, b, c, d, Vector3.up, new Vector2(a.x, a.z), new Vector2(b.x, b.z), new Vector2(c.x, c.z), new Vector2(d.x, d.z));
            }
        }

        /// <summary>Strip along a prototype line (from p0 to p1 at height y) with a cross width; U = metres along, V = 0..1 across
        /// (0 at the -side). Used for gutters.</summary>
        public void Strip(Material m, Vector2 p0, Vector2 p1, float y, float w0, float w1, float u0 = 0)
        {
            var dir = (p1 - p0);
            var len = dir.magnitude;
            if (len < 0.05f) return;
            dir /= len;
            var side = new Vector2(-dir.y, dir.x);
            const float step = 24f;
            for (var s = 0f; s < len - 0.001f; s += step)
            {
                var e = Mathf.Min(len, s + step);
                Vector2 a = p0 + dir * s + side * w0, b = p0 + dir * e + side * w0, c = p0 + dir * e + side * w1, d = p0 + dir * s + side * w1;
                Quad(m, V(a.x, y, a.y), V(b.x, y, b.y), V(c.x, y, c.y), V(d.x, y, d.y), Vector3.up,
                    new Vector2(u0 + s, 0), new Vector2(u0 + e, 0), new Vector2(u0 + e, 1), new Vector2(u0 + s, 1));
            }
        }

        /// <summary>Register a pavement slab (top drawn now; kerbs / edges at <see cref="Finish"/>).</summary>
        public void Slab(PRect r, float top, string preset)
        {
            Top(StreetKit.Surface(preset), r, top);
            slabs.Add((r, top, preset));
        }

        bool Covered(float x, float z, float top, int self)
        {
            for (var i = 0; i < slabs.Count; i++)
            {
                if (i == self) continue;
                var s = slabs[i];
                if (s.top >= top - 0.05f && s.r.Contains(x, z)) return true;
            }
            return false;
        }

        /// <summary>Kerb profile along one exposed slab edge from a to b (prototype XZ), outward normal n: chamfered top
        /// arris, vertical face down to the road and a short apron, U = metres along.</summary>
        void Kerb(Material kerb, Vector2 a, Vector2 b, Vector2 n, float top, float u0)
        {
            var len = Vector2.Distance(a, b);
            if (len < 0.05f) return;
            var dir = (b - a) / len;
            const float step = 16f;
            // Profile (offset outward from the edge line, height): top band, chamfer, face.
            var prof = new (float o, float y)[] { (-0.28f, top + 0.004f), (-0.03f, top + 0.004f), (0f, top - 0.026f), (0f, 0.005f) };
            for (var s = 0f; s < len - 0.001f; s += step)
            {
                var e = Mathf.Min(len, s + step);
                var vAcc = 0f;
                for (var k = 0; k < prof.Length - 1; k++)
                {
                    var (o0, y0) = prof[k];
                    var (o1, y1) = prof[k + 1];
                    Vector2 p0 = a + dir * s + n * o0, p1 = a + dir * e + n * o0, p2 = a + dir * e + n * o1, p3 = a + dir * s + n * o1;
                    var segLen = Mathf.Sqrt((o1 - o0) * (o1 - o0) + (y1 - y0) * (y1 - y0));
                    var nrm2 = new Vector2(y0 - y1, o1 - o0).normalized; // (outward, up) of this facet
                    var nWorld = V(n.x * nrm2.x, nrm2.y, n.y * nrm2.x);
                    nWorld.Normalize();
                    Quad(kerb, V(p0.x, y0, p0.y), V(p1.x, y0, p1.y), V(p2.x, y1, p2.y), V(p3.x, y1, p3.y), nWorld,
                        new Vector2(u0 + s, vAcc * 0.5f), new Vector2(u0 + e, vAcc * 0.5f), new Vector2(u0 + e, (vAcc + segLen) * 0.5f), new Vector2(u0 + s, (vAcc + segLen) * 0.5f), true);
                    vAcc += segLen;
                }
            }
        }

        /// <summary>Kerbs on every exposed slab edge, then the meshes into the culling cells.</summary>
        public void Finish(Transform parent, CityCells cells)
        {
            var kerb = StreetKit.Surface("curb");
            for (var i = 0; i < slabs.Count; i++)
            {
                var (r, top, _) = slabs[i];
                if (top < 0.05f) continue;
                foreach (var f in CityFace.All)
                {
                    CityFace.Line(r, f, out var a0, out var a1, out var line, out var n, out var alongX);
                    // walk the edge in 1 m steps, emitting runs that are not covered by a neighbouring slab
                    float run0 = float.NaN;
                    for (var s = a0; s <= a1 + 0.001f; s += 1f)
                    {
                        var sc = Mathf.Min(s + 0.5f, a1 - 0.01f);
                        var qx = alongX ? sc : line + n.x * 0.3f;
                        var qz = alongX ? line + n.y * 0.3f : sc;
                        var exposed = s < a1 - 0.01f && !Covered(qx, qz, top, i);
                        if (exposed && float.IsNaN(run0)) run0 = s;
                        if ((!exposed || s + 1f > a1) && !float.IsNaN(run0))
                        {
                            var e = exposed ? a1 : s;
                            Vector2 pa = alongX ? new Vector2(run0, line) : new Vector2(line, run0);
                            Vector2 pb = alongX ? new Vector2(e, line) : new Vector2(line, e);
                            Kerb(kerb, pa, pb, n, top, run0);
                            run0 = float.NaN;
                        }
                    }
                }
            }
            var root = new GameObject("StreetSurfaces");
            root.layer = CombatLayers.World;
            root.transform.SetParent(parent, false);
            foreach (var b in buckets.Values)
            {
                if (b.T.Count == 0) continue;
                var lo = b.V[0]; var hi = b.V[0];
                foreach (var v in b.V) { lo = Vector3.Min(lo, v); hi = Vector3.Max(hi, v); }
                var ctr = (lo + hi) * 0.5f;
                var go = new GameObject("street_" + b.Mat.name);
                go.layer = CombatLayers.World;
                go.transform.SetParent(root.transform, false);
                go.transform.localPosition = ctr;
                go.AddComponent<MeshFilter>().sharedMesh = Recentre(b, ctr, go.name, b.V.Count > 65000);
                var mr = go.AddComponent<MeshRenderer>();
                mr.sharedMaterial = b.Mat;
                mr.shadowCastingMode = b.Shadow ? ShadowCastingMode.On : ShadowCastingMode.Off;
                mr.receiveShadows = true;
                mr.reflectionProbeUsage = ReflectionProbeUsage.BlendProbes;
                mr.lightProbeUsage = LightProbeUsage.BlendProbes;
                if (cells != null) cells.Put(go, CityCuller.Geo);
            }
            buckets.Clear();
            slabs.Clear();
        }

        static Mesh Recentre(Bucket b, Vector3 c, string name, bool big)
        {
            var vs = new List<Vector3>(b.V.Count);
            foreach (var v in b.V) vs.Add(v - c);
            var m = new Mesh { name = name };
            if (big) m.indexFormat = IndexFormat.UInt32;
            m.SetVertices(vs);
            m.SetNormals(b.N);
            m.SetUVs(0, b.UV);
            m.SetTriangles(b.T, 0);
            m.RecalculateBounds();
            m.RecalculateTangents();
            m.UploadMeshData(true);
            return m;
        }
    }
}
