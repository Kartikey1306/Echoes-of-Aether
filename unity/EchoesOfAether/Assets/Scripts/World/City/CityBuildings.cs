using System.Collections.Generic;
using UnityEngine;
using static EOA.ProtoSpace;

namespace EOA
{
    /// <summary>
    /// Environment-kit assets (the artist's Building_* / neon / dressing kit) are used only once their prefabs exist in
    /// Resources/Env/Props (EOA → Build Environment Library); until then the procedural versions stand in, so the city
    /// never shows grey placeholder boxes.
    /// </summary>
    public static class CityKitAssets
    {
        static readonly Dictionary<string, bool> cache = new();

        public static bool Has(string name)
        {
            if (!cache.TryGetValue(name, out var has)) cache[name] = has = Resources.Load<GameObject>("Env/Props/" + name) != null;
            return has;
        }

        /// <summary>Prototype yaw that turns an asset's front (+Z) toward a building face's outward normal.</summary>
        public static float FaceYaw(byte face) => face switch { CityFace.S => 0f, CityFace.N => Mathf.PI, CityFace.E => Mathf.PI / 2, _ => -Mathf.PI / 2 };
    }

    /// <summary>
    /// Faces of the Central Plaza blocks that PzKit built from a bespoke CityLandmarks prefab (Plaza_Block_NN): the open
    /// city must not add procedural shopfronts / facade dressing on top of them (OpenCity.PlazaFace).
    /// </summary>
    public static class PlazaFacades
    {
        static readonly HashSet<(int, int, byte)> covered = new();

        static (int, int) Key(float x, float z) => (Mathf.RoundToInt(x * 2), Mathf.RoundToInt(z * 2));

        public static void Clear() => covered.Clear();

        /// <summary>Register a plaza block (prototype centre) built from a prefab with these CityFace bits detailed.</summary>
        public static void Add(float cx, float cz, byte faces)
        {
            var (a, b) = Key(cx, cz);
            foreach (var f in CityFace.All) if ((faces & f) != 0) covered.Add((a, b, f));
        }

        public static bool Covers(PRect foot, byte face)
        {
            var (a, b) = Key(foot.CX, foot.CZ);
            return covered.Contains((a, b, face));
        }
    }

    /// <summary>
    /// Emission for the building kits' prefabs. The library builder saves emissive URP/Lit materials with the GI flag
    /// 'None', and URP's material validation then drops the _EMISSION keyword, so lit windows, signs, LED strips and
    /// screens import dark. Until that is fixed at the source, the building / landmark / plaza prefabs get a runtime
    /// twin of each affected material (same name and maps, keyword on, realtime-emissive GI flag), shared by every
    /// instance. A no-op once the imported materials keep their keyword.
    /// </summary>
    public static class KitEmission
    {
        static readonly Dictionary<Material, Material> twins = new();

        static bool NeedsTwin(Material m) =>
            m.HasProperty("_EmissionColor") && !m.IsKeywordEnabled("_EMISSION") && m.GetColor("_EmissionColor").maxColorComponent > 0.01f &&
            (m.name.StartsWith("emit_") || m.name.StartsWith("window_lit") || m.name.StartsWith("screen"));

        public static GameObject Fix(GameObject go)
        {
            if (go == null) return go;
            foreach (var r in go.GetComponentsInChildren<Renderer>(true))
            {
                var mats = r.sharedMaterials;
                var changed = false;
                for (var i = 0; i < mats.Length; i++)
                {
                    var m = mats[i];
                    if (m == null) continue;
                    if (!twins.TryGetValue(m, out var t))
                    {
                        t = m;
                        if (NeedsTwin(m))
                        {
                            t = new Material(m) { name = m.name };
                            t.EnableKeyword("_EMISSION");
                            t.globalIlluminationFlags = MaterialGlobalIlluminationFlags.RealtimeEmissive;
                        }
                        twins[m] = t;
                    }
                    if (t != m) { mats[i] = t; changed = true; }
                }
                if (changed) r.sharedMaterials = mats;
            }
            return go;
        }
    }

    /// <summary>A building face queued for <see cref="CyberCity.DressFacades"/> (Unity-space box, prototype face bits).</summary>
    public struct CityDressJob
    {
        public Vector3 Center, Size;
        public byte Faces;
        public float Density;
        public int MaxPerFace, Seed;
    }

    /// <summary>
    /// Everything the open-city builders share while the district is generated: the level kit (merged static
    /// geometry and colliders, prototype coordinates), custom batches (window skins, glow decals), prop cells for
    /// culling, the facade dressing queue, lamp positions for the light pool and the map shapes.
    /// </summary>
    public sealed class CityContext
    {
        public LevelKit Kit;
        public CityBatch Skins, Glow;
        public Material[] SkinMats;
        public Material GlowMat;
        public CityCells Cells;
        public System.Random R;
        public bool Dawn;
        public CityLayout Layout;
        public readonly List<CityDressJob> Dress = new();
        /// <summary>Sidewalk obstacles pedestrians step around (Unity xyz + clearance radius in w).</summary>
        public readonly List<Vector4> Obstacles = new();
        public readonly List<Vector3> LampPos = new();
        public readonly List<Color> LampCol = new();
        /// <summary>Steam vent emitter positions (Unity space).</summary>
        public readonly List<Vector3> Steam = new();
        public readonly List<MapRect> Map = new();
        public readonly List<MapLabel> Labels = new();
        public int Props;
        /// <summary>Instance budgets for the detailed (many-material) kit pieces, spent around the plaza where players arrive.</summary>
        public int ModuleBudget = 260, VendBudget = 16, BillboardBudget = 10, AcBudget = 30, ShelterBudget = 10, ClutterBudget = 60;
        /// <summary>
        /// CityLandmarks kit: district buildings beyond OpenCity's kit budget (they are light: <= 8 atlas materials) and
        /// district roof sets / facade pieces on the procedural masses. WebGL gets about a third.
        /// </summary>
        public int LightKitBudget = Application.platform == RuntimePlatform.WebGLPlayer ? 40 : 120,
                   DistrictPieceBudget = Application.platform == RuntimePlatform.WebGLPlayer ? 260 : 800;
        /// <summary>Landmarks placed (report) and their root (outside the culling cells: they read from across the city).</summary>
        public int LandmarksPlaced, DistrictPieces;
        Transform landmarkRoot;

        public Transform LandmarkRoot
        {
            get
            {
                if (landmarkRoot == null)
                {
                    var go = new GameObject("Landmarks");
                    go.layer = CombatLayers.World;
                    go.transform.SetParent(Kit.Root, false);
                    landmarkRoot = go.transform;
                }
                return landmarkRoot;
            }
        }
        /// <summary>Kit pieces actually placed (report).</summary>
        public int KitPieces;

        /// <summary>True for footprints within ~100 m of the plaza ring (the showcase streets).</summary>
        public static bool NearPlaza(PRect r)
        {
            var dx = Mathf.Max(0, Mathf.Abs(r.CX) - CityLayout.ResX);
            var dz = Mathf.Max(0, Mathf.Max(CityLayout.ResZ0 - r.CZ, r.CZ - CityLayout.ResZ1));
            return dx * dx + dz * dz < 100 * 100;
        }

        public const int SkinWarm = 0, SkinCool = 1, SkinSparse = 2, SkinNeon = 3, SkinWall = 4;

        public float Rand => (float)R.NextDouble();
        public float Range(float a, float b) => a + (float)R.NextDouble() * (b - a);
        public bool Chance(float p) => R.NextDouble() < p;
        public T Pick<T>(T[] a) => a[R.Next(a.Length)];

        // ------------------------------------------------------------------ materials

        static readonly int SeedId = Shader.PropertyToID("_Seed"), LitId = Shader.PropertyToID("_Lit"), CellId = Shader.PropertyToID("_Cell"),
            BandsId = Shader.PropertyToID("_Bands"), BaseId = Shader.PropertyToID("_Base"), FogKeepId = Shader.PropertyToID("_FogKeep");

        static Material[] nightSkins, dawnSkins;
        static Material glowShared;

        /// <summary>EOA/CityLights window skin variants (night or dawn, cached); dark glass when the shader is unavailable.</summary>
        public static Material[] MakeSkins(bool dawn)
        {
            var cached = dawn ? dawnSkins : nightSkins;
            if (cached != null && cached[0] != null) return cached;
            var template = Resources.Load<Material>("Env/CityLights");
            var shader = template != null ? template.shader : Shader.Find("EOA/CityLights");
            var ok = shader != null && shader.isSupported;
            //                lit    cellX  bands  seed
            var spec = new (float lit, float cx, float cy, float bands, float seed)[]
            {
                (0.40f, 2.2f, 3.4f, 37.4f, 11), (0.34f, 1.6f, 3.4f, 51f, 47), (0.18f, 3.2f, 3.4f, 1000f, 83), (0.46f, 2.0f, 3.4f, 23.8f, 131), (0.24f, 2.6f, 4.2f, 30f, 177),
            };
            var mats = new Material[spec.Length];
            for (var i = 0; i < spec.Length; i++)
            {
                Material m;
                if (ok)
                {
                    m = template != null ? new Material(template) : new Material(shader);
                    var s = spec[i];
                    m.SetFloat(SeedId, s.seed);
                    m.SetFloat(LitId, dawn ? s.lit * 0.25f : s.lit);
                    m.SetVector(CellId, new Vector4(s.cx, s.cy, 0, 0));
                    m.SetFloat(BandsId, dawn ? 1000f : s.bands);
                    // lit facades: daylight albedo and almost no self-glow at dawn (the low sun models the blocks)
                    if (dawn) { m.SetColor(BaseId, new Color(0.17f, 0.18f, 0.2f)); m.SetFloat(FogKeepId, 0.15f); m.SetColor("_Albedo", new Color(0.3f, 0.3f, 0.32f)); m.SetFloat("_Emit", 0.08f); }
                    else if (i == SkinWall) m.SetFloat(FogKeepId, 0.7f);
                }
                else m = FxMaterials.Lit(dawn ? new Color(0.2f, 0.21f, 0.23f) : new Color(0.04f, 0.045f, 0.06f), 0.4f, 0.8f, "city_skin_fallback");
                m.name = "city_skin_" + i;
                mats[i] = m;
            }
            if (dawn) dawnSkins = mats; else nightSkins = mats;
            return mats;
        }

        public static Material MakeGlow()
        {
            if (glowShared != null) return glowShared;
            var m = FxMaterials.Particle(true, FxMaterials.Glow, true);
            m.name = "city_glow";
            m.SetColor("_BaseColor", Color.white);
            return glowShared = m;
        }

        // ------------------------------------------------------------------ helpers (prototype coordinates in, Unity out)

        static Color Lin(uint color, float intensity)
        {
            var c = Hex(color).linear * intensity;
            c.a = 1;
            return c;
        }

        /// <summary>Additive glow pool on the ground (prototype centre, size along proto x/z).</summary>
        public void GlowGround(float x, float y, float z, float sx, float sz, uint color, float intensity) =>
            Glow.Ground(GlowMat, V(x, y, z), sx, sz, 0, Lin(color, intensity));

        /// <summary>Additive glow on a wall facing the prototype normal (nx, nz).</summary>
        public void GlowWall(float x, float y, float z, float nx, float nz, float w, float h, uint color, float intensity) =>
            Glow.Upright(GlowMat, V(x, y, z), new Vector3(-nx, 0, nz), w, h, Lin(color, intensity));

        /// <summary>Crossed glow quads (lamp halos, beacons) that read from every side.</summary>
        public void GlowCross(float x, float y, float z, float size, uint color, float intensity) =>
            Glow.Cross(GlowMat, V(x, y, z), size, Lin(color, intensity));

        /// <summary>Window skin around a prototype footprint from y0 to y1 (slightly proud of the wall).</summary>
        public void Skin(int variant, PRect r, float y0, float y1, float u0)
        {
            if (y1 - y0 < 1.5f) return;
            const float o = 0.06f;
            Skins.BoxSides(SkinMats[Mathf.Clamp(variant, 0, SkinMats.Length - 1)], -r.X1 - o, r.Z0 - o, -r.X0 + o, r.Z1 + o, y0, y1, u0);
        }

        /// <summary>
        /// Box on a building face (prototype): along the face from s - w/2 to s + w/2, height y0..y1, protruding from
        /// off0 to off1 metres outward from the face line.
        /// </summary>
        public void FaceBox(PRect foot, byte face, float s, float w, float y0, float y1, float off0, float off1, string mat, bool collide = false, bool shadow = true)
        {
            CityFace.Line(foot, face, out _, out _, out var line, out var n, out var alongX);
            var mid = (off0 + off1) * 0.5f;
            var depth = Mathf.Abs(off1 - off0);
            var h = y1 - y0;
            if (alongX) Kit.Box(s, y0 + h / 2, line + n.y * mid, w, h, depth, mat, collide: collide, shadow: shadow);
            else Kit.Box(line + n.x * mid, y0 + h / 2, s, depth, h, w, mat, collide: collide, shadow: shadow);
        }

        /// <summary>Prototype point on a face: along s, height y, off metres out.</summary>
        public static Vector3 FacePoint(PRect foot, byte face, float s, float y, float off)
        {
            CityFace.Line(foot, face, out _, out _, out var line, out var n, out var alongX);
            return alongX ? new Vector3(s, y, line + n.y * off) : new Vector3(line + n.x * off, y, s);
        }

        public void Obstacle(float x, float z, float radius) => Obstacles.Add(new Vector4(-x, CityLayout.Curb, z, radius));

        /// <summary>First available kit name, else the fallback (always an existing prop).</summary>
        public static string KitOr(string kit, string fallback) => CityKitAssets.Has(kit) ? kit : fallback;

        /// <summary>Environment prop placed into a culling cell (prototype coordinates, yaw in radians).</summary>
        public GameObject Prop(string name, float x, float y, float z, float yaw, int group = CityCuller.Small, float scale = 1, bool collide = true)
        {
            var go = Kit.Prop(name, x, y, z, yaw, scale, 0, 0, collide);
            Props++;
            return Cells.Put(go, group);
        }

        public void Queue(PRect r, float y0, float y1, byte faces, float density, int max, int seed)
        {
            foreach (var f in CityFace.All) if ((faces & f) != 0 && PlazaFacades.Covers(r, f)) faces &= (byte)~f;
            if (faces == 0 || y1 - y0 < 7f) return;
            Dress.Add(new CityDressJob
            {
                Center = V(r.CX, (y0 + y1) / 2, r.CZ), Size = new Vector3(r.W, y1 - y0, r.D), Faces = faces, Density = density, MaxPerFace = max, Seed = seed,
            });
        }

        public void MapRect(string kind, PRect r) => MapRect(kind, r.CX, r.CZ, r.W, r.D);

        public void MapRect(string kind, float x, float z, float w, float d)
        {
            var k = kind switch { "block" => MapRectKind.Block, "water" => MapRectKind.Water, "road" => MapRectKind.Road, _ => MapRectKind.Floor };
            Map.Add(new MapRect { Kind = k, Center = MapXZ(x, z), Size = new Vector2(w, d), RotationDeg = 0 });
        }

        public void Label(string text, float x, float z) => Labels.Add(new MapLabel { Text = text, Position = MapXZ(x, z) });
    }

    /// <summary>
    /// Building factory used by the open city. Swap <see cref="OpenCity.Buildings"/> to change how every lot is built
    /// (e.g. to assemble the environment artist's Building_* facade kit) without touching the layout or the streets.
    /// </summary>
    public interface ICityBuildings
    {
        /// <summary>Emit one building (geometry, colliders, dressing jobs, map shape) into the context.</summary>
        void Build(CityContext c, CityBuilding b);
    }

    /// <summary>
    /// Default buildings: PBR masses with colliders, EOA/CityLights window skins above the shop floor, shopfronts with
    /// awnings and lit interiors on street faces, back doors and AC units on alleys, parapets and roof clutter, and
    /// <see cref="CyberCity.DressFacades"/> neon on every street face. Lots that fit one of the detailed environment
    /// modules (Building_Block_*) use it instead.
    /// </summary>
    public sealed class BoxBuildings : ICityBuildings
    {
        // Few, shared materials: every extra material is another draw per 32 m cell.
        static readonly string[] Awnings = { "metal_dark", "tarp_blue", "metal_dark", "plastic_orange" };
        // awning light bands are big faces: deep red / amber / cyan (the warm-white strip textures read as blank glowing slabs)
        static readonly string[] AwningStrips = { "emit_strip_cyan", "emit_red", "emit_amber", "emit_red" };
        static readonly string[] ShopLit = { "window_lit_warm", "window_lit_cool", "window_lit_warm" };
        static readonly uint[] ShopGlow = { 0xffb878, 0x8fd0ff, 0xffb878 };

        static float DistrictNeon(CityDistrict d) => d switch
        {
            CityDistrict.NeonMarket => 1.0f, CityDistrict.KowloonStacks => 0.85f, CityDistrict.ArcologyGate => 0.55f, CityDistrict.CanalWard => 0.7f, _ => 0.35f,
        };

        public void Build(CityContext c, CityBuilding b)
        {
            if (b.LandmarkAsset != null && Landmark(c, b)) return;
            if (b.Asset != null) { Module(c, b); return; }
            if (b.UseKit && KitBuilding(c, b)) return;
            if (!b.UseKit && CityLayout.IsLandmarkKit(b.Kit) && c.LightKitBudget > 0 && KitBuilding(c, b)) { c.LightKitBudget--; b.UseKit = true; return; }
            var k = c.Kit;
            var f = b.Foot;
            var tower = b.PodiumHeight > 0;
            var massTop = tower ? b.PodiumHeight : b.Height;
            var u0 = (b.Seed % 997) * 2.2f;
            // Showcase streets around the plaza: the two lowest storeys of street faces use the kit's facade modules.
            var modular = b.Street != 0 && c.ModuleBudget > 0 && CityContext.NearPlaza(f) && massTop > 9f && ModulesAvailable(b.Material);
            k.Box(f.CX, massTop / 2, f.CZ, f.W, massTop, f.D, b.Material, uvSeed: (b.Seed % 101) * 0.37f);
            var skinY0 = modular ? CityLayout.Curb + 2 * CityLayout.FloorH + 0.15f : CityLayout.GroundH;
            c.Skin(b.Skin, f, skinY0, massTop - 0.7f, u0);
            Articulate(c, f, skinY0, massTop, b.Material, !tower);
            Parapet(c, f, massTop, b.Material, tower ? 1.1f : 1.0f);
            var faces = (byte)(b.Street | b.Alley);
            var neon = DistrictNeon(b.District);
            c.Queue(f, 0, massTop, faces, neon * (tower ? 0.6f : 0.9f), b.Landmark ? 3 : 2 + (neon > 0.8f ? 1 : 0), b.Seed);
            if (tower)
            {
                var t = b.Tower;
                var th = b.Height - b.PodiumHeight;
                k.Box(t.CX, b.PodiumHeight + th / 2, t.CZ, t.W, th, t.D, b.Material, uvSeed: (b.Seed % 89) * 0.41f);
                c.Skin(b.Skin, t, b.PodiumHeight + 0.4f, b.Height - 0.7f, u0 + 40);
                Parapet(c, t, b.Height, b.Material, 1.2f);
                Articulate(c, t, b.PodiumHeight + 0.4f, b.Height, b.Material, false);
                // Floor ledges every four floors break up the tower silhouette (and throw shadow lines down the facade).
                for (var y = b.PodiumHeight + CityLayout.FloorH * 4; y < b.Height - 3; y += CityLayout.FloorH * 4)
                    k.Box(t.CX, y, t.CZ, t.W + 0.6f, 0.3f, t.D + 0.6f, "concrete_dark", collide: false, shadow: true);
                c.Queue(t, b.PodiumHeight, b.Height, faces, neon * 0.5f, b.Landmark ? 3 : 2, b.Seed + 7);
                if (b.Landmark) Crown(c, b);
            }
            // District roof set (shanty roofs, pagoda pavilions, crowns, gardens, roof plant) or the generic clutter.
            var roofSet = DistrictPieces.Roof(c, b, tower ? b.Tower : f, b.Height);
            if (!roofSet) Roof(c, tower ? b.Tower : f, b.Height, b);
            foreach (var face in CityFace.All)
            {
                if ((b.Street & face) != 0) { if (!modular || !ModuleFace(c, b, face)) Shopfront(c, b, face); }
                else if ((b.Alley & face) != 0) AlleyFace(c, b, face);
            }
            if (b.District == CityDistrict.KowloonStacks && (b.Street != 0)) AcUnits(c, b);
            DistrictPieces.Facades(c, b, massTop);
            if (!roofSet && b.Height > 20 && c.Chance(b.Landmark ? 1f : 0.1f)) RoofBillboard(c, b);
            c.MapRect("block", f);
        }

        // ------------------------------------------------------------------ parts

        /// <summary>
        /// Real relief on a procedural mass (prototype footprint): corner piers up the skin, a projecting cornice under
        /// the parapet and (low blocks) a string course over the shop floor. They break the box silhouette, cast the
        /// moon / lamp shadows across the facade and catch light on their edges; the window skin adds the per-floor
        /// ledges and window reveals in the shader. No colliders.
        /// </summary>
        static void Articulate(CityContext c, PRect f, float y0, float top, string mat, bool course)
        {
            var k = c.Kit;
            var h = top - y0;
            if (h < 3f || f.W < 4f || f.D < 4f) return;
            const float proud = 0.34f, pier = 0.9f;
            foreach (var sx in new[] { -1, 1 })
            foreach (var sz in new[] { -1, 1 })
            {
                var x = sx < 0 ? f.X0 - proud + pier / 2 : f.X1 + proud - pier / 2;
                var z = sz < 0 ? f.Z0 - proud + pier / 2 : f.Z1 + proud - pier / 2;
                k.Box(x, y0 + h / 2, z, pier, h, pier, mat, collide: false);
            }
            // cornice: deep slab with a smaller bed moulding under it (a stepped profile, lit top / shadowed underside)
            const float cp = 0.42f, ch = 0.5f;
            Ring(k, f, top - ch / 2, ch, cp, "concrete_dark");
            Ring(k, f, top - ch - 0.12f, 0.24f, cp * 0.5f, "concrete_dark");
            if (course) Ring(k, f, y0 - 0.16f, 0.3f, 0.26f, "concrete_dark");
        }

        /// <summary>Band all around a footprint at height y (centre), thickness th, projecting p beyond the walls.</summary>
        static void Ring(LevelKit k, PRect f, float y, float th, float p, string mat)
        {
            k.Box(f.CX, y, f.Z0 - p / 2, f.W + 2 * p, th, p, mat, collide: false);
            k.Box(f.CX, y, f.Z1 + p / 2, f.W + 2 * p, th, p, mat, collide: false);
            k.Box(f.X0 - p / 2, y, f.CZ, p, th, f.D, mat, collide: false);
            k.Box(f.X1 + p / 2, y, f.CZ, p, th, f.D, mat, collide: false);
        }

        static void Parapet(CityContext c, PRect r, float top, string mat, float h)
        {
            var k = c.Kit;
            const float t = 0.3f;
            k.Box(r.CX, top + h / 2, r.Z0 + t / 2, r.W, h, t, mat, collide: false);
            k.Box(r.CX, top + h / 2, r.Z1 - t / 2, r.W, h, t, mat, collide: false);
            k.Box(r.X0 + t / 2, top + h / 2, r.CZ, t, h, r.D - 2 * t, mat, collide: false);
            k.Box(r.X1 - t / 2, top + h / 2, r.CZ, t, h, r.D - 2 * t, mat, collide: false);
            k.Box(r.CX, top + h + 0.04f, r.CZ, r.W + 0.1f, 0.08f, r.D + 0.1f, "metal_dark", collide: false, shadow: false);
        }

        static void Roof(CityContext c, PRect r, float top, CityBuilding b)
        {
            var k = c.Kit;
            var n = Mathf.Clamp(Mathf.RoundToInt(r.W * r.D / 220f), 1, 4);
            for (var i = 0; i < n; i++)
            {
                var x = c.Range(r.X0 + 2, r.X1 - 2);
                var z = c.Range(r.Z0 + 2, r.Z1 - 2);
                if (c.Chance(0.6f))
                {
                    k.Box(x, top + 0.55f, z, 1.6f, 1.1f, 1.2f, "metal_painted_white", collide: false);
                    k.Box(x, top + 1.12f, z, 1.0f, 0.06f, 0.7f, "grating", collide: false, shadow: false);
                }
                else k.Cyl(x, top + 1.6f, z, 1.3f, 1.3f, 3.2f, "metal_rusted", 10, collide: false);
            }
            if (b.Height > 30 || c.Chance(0.25f))
            {
                var ax = c.Range(r.X0 + 1.5f, r.X1 - 1.5f);
                var az = c.Range(r.Z0 + 1.5f, r.Z1 - 1.5f);
                var h = 4f + c.Rand * (b.Landmark ? 18f : 7f);
                k.Box(ax, top + h / 2, az, 0.18f, h, 0.18f, "metal_dark", collide: false);
                c.GlowCross(ax, top + h + 0.2f, az, b.Landmark ? 5f : 2.4f, 0xff3030, 1.6f);
            }
        }

        static void Crown(CityContext c, CityBuilding b)
        {
            var t = b.Tower;
            var k = c.Kit;
            // Setback crown, lit cornice band and a spire.
            var cw = t.W * 0.6f; var cd = t.D * 0.6f;
            k.Box(t.CX, b.Height + 6, t.CZ, cw, 12, cd, "glass_dark", collide: false);
            c.Skin(CityContext.SkinNeon, new PRect(t.CX - cw / 2, t.CZ - cd / 2, t.CX + cw / 2, t.CZ + cd / 2), b.Height + 0.5f, b.Height + 11.5f, 7);
            k.Box(t.CX, b.Height + 0.3f, t.CZ, t.W + 0.6f, 0.4f, t.D + 0.6f, "emit_strip_cyan", collide: false, shadow: false);
            k.Box(t.CX, b.Height + 12 + 14, t.CZ, 0.6f, 28, 0.6f, "metal_dark", collide: false);
            c.GlowCross(t.CX, b.Height + 40.5f, t.CZ, 9f, 0xff3030, 2f);
        }

        /// <summary>Shop units (lit interiors with awnings, shutters, dark glass) along the ground floor of a street face.</summary>
        public static void Shopfront(CityContext c, CityBuilding b, byte face)
        {
            if (PlazaFacades.Covers(b.Foot, face)) return;
            var f = b.Foot;
            CityFace.Line(f, face, out var a0, out var a1, out _, out _, out _);
            var len = a1 - a0;
            if (len < 3f) return;
            var units = Mathf.Max(1, Mathf.RoundToInt(len / 7f));
            var u = len / units;
            const float y0 = CityLayout.Curb;
            for (var i = 0; i < units; i++)
            {
                var mid = a0 + u * (i + 0.5f);
                if (i > 0) c.FaceBox(f, face, a0 + u * i, 0.5f, y0, CityLayout.GroundH, 0, 0.3f, "concrete_dark");
                var roll = c.Rand;
                if (roll < 0.62f)
                {
                    var kind = c.R.Next(ShopLit.Length);
                    c.FaceBox(f, face, mid, u - 1.3f, y0 + 0.35f, 3.1f, 0, 0.1f, ShopLit[kind], shadow: false);
                    c.FaceBox(f, face, mid, u - 0.7f, 3.3f, 3.45f, 0, 1.5f, c.Pick(Awnings));
                    c.FaceBox(f, face, mid, u - 0.7f, 3.22f, 3.3f, 1.42f, 1.5f, c.Pick(AwningStrips), shadow: false);
                    var g = CityContext.FacePoint(f, face, mid, 0.18f, 2.4f);
                    var alongX = face == CityFace.N || face == CityFace.S;
                    c.GlowGround(g.x, g.y, g.z, alongX ? u - 0.5f : 3.2f, alongX ? 3.2f : u - 0.5f, ShopGlow[kind], 0.3f);
                }
                else if (roll < 0.86f) c.FaceBox(f, face, mid, u - 1.2f, y0, 3.05f, 0, 0.12f, "corrugated");
                else c.FaceBox(f, face, mid, u - 1.2f, y0 + 0.3f, 3.1f, 0, 0.08f, "glass_dark");
            }
            // Thin trim under the window skin.
            c.FaceBox(f, face, (a0 + a1) / 2, len, CityLayout.GroundH - 0.12f, CityLayout.GroundH, 0, 0.06f, "metal_dark", shadow: false);
        }

        static void AlleyFace(CityContext c, CityBuilding b, byte face)
        {
            var f = b.Foot;
            CityFace.Line(f, face, out var a0, out var a1, out _, out _, out _);
            var len = a1 - a0;
            if (len < 4f) return;
            var s = c.Range(a0 + 1.5f, a1 - 1.5f);
            c.FaceBox(f, face, s, 1.3f, CityLayout.Curb, 2.4f, 0, 0.08f, "black", shadow: false);
            c.FaceBox(f, face, s, 0.4f, 2.6f, 2.75f, 0, 0.12f, "emit_amber", shadow: false);
            var g = CityContext.FacePoint(f, face, s, 0.18f, 1.6f);
            c.GlowGround(g.x, g.y, g.z, 3.2f, 3.2f, 0xffa21f, 0.22f);
            // Down pipe and a couple of AC boxes.
            var ps = Mathf.Clamp(s + (c.Chance(0.5f) ? 2f : -2f), a0 + 0.3f, a1 - 0.3f);
            c.FaceBox(f, face, ps, 0.16f, CityLayout.Curb, Mathf.Min(b.Height, 14f), 0.02f, 0.18f, "metal_rusted");
            for (var i = 0; i < 2; i++)
            {
                var y = c.Range(3.2f, Mathf.Min(b.Height - 2, 12f));
                c.FaceBox(f, face, c.Range(a0 + 1, a1 - 1), 0.9f, y, y + 0.65f, 0, 0.55f, "metal_painted_white");
            }
        }

        static void AcUnits(CityContext c, CityBuilding b)
        {
            foreach (var face in CityFace.All)
            {
                if ((b.Street & face) == 0) continue;
                CityFace.Line(b.Foot, face, out var a0, out var a1, out _, out _, out _);
                if (c.AcBudget > 0 && CityContext.NearPlaza(b.Foot) && CityKitAssets.Has("AC_Unit_Stack_Wall"))
                {
                    for (var i = 0; i < 2 && c.AcBudget > 0; i++)
                    {
                        var floor = 1 + c.R.Next(Mathf.Max(1, b.Floors - 2));
                        var p = CityContext.FacePoint(b.Foot, face, c.Range(a0 + 1.5f, a1 - 1.5f), CityLayout.GroundH + (floor - 1) * CityLayout.FloorH + 0.6f, 0.07f);
                        c.Prop("AC_Unit_Stack_Wall", p.x, p.y, p.z, CityKitAssets.FaceYaw(face), CityCuller.Small, 1, false);
                        c.AcBudget--;
                        c.KitPieces++;
                    }
                }
                var count = Mathf.Clamp(Mathf.RoundToInt((a1 - a0) * b.Floors / 40f), 2, 10);
                for (var i = 0; i < count; i++)
                {
                    var floor = 1 + c.R.Next(Mathf.Max(1, (b.PodiumHeight > 0 ? 2 : b.Floors - 1)));
                    var y = CityLayout.GroundH + (floor - 1) * CityLayout.FloorH + 0.4f;
                    c.FaceBox(b.Foot, face, c.Range(a0 + 1, a1 - 1), 0.9f, y, y + 0.6f, 0.06f, 0.6f, "metal_painted_white");
                }
            }
        }

        static void RoofBillboard(CityContext c, CityBuilding b)
        {
            byte face = 0;
            foreach (var fc in CityFace.All) if ((b.Street & fc) != 0) { face = fc; break; }
            if (face == 0) return;
            var r = b.PodiumHeight > 0 ? b.Tower : b.Foot;
            CityFace.Line(r, face, out var a0, out var a1, out _, out var n, out _);
            if (!b.Landmark && a1 - a0 >= 15f && c.BillboardBudget > 0 && CityKitAssets.Has("Billboard_Rooftop_Rig_12x6"))
            {
                var rp = CityContext.FacePoint(r, face, (a0 + a1) / 2, b.Height + 1.0f, -3.6f);
                c.Prop("Billboard_Rooftop_Rig_12x6", rp.x, rp.y, rp.z, CityKitAssets.FaceYaw(face), CityCuller.Geo, 1, false);
                c.BillboardBudget--;
                c.KitPieces++;
                return;
            }
            var w = Mathf.Min(a1 - a0 - 2, b.Landmark ? 22f : 12f);
            if (w < 5) return;
            var h = w * 0.5f;
            var top = b.Height + 1.2f;
            var p = CityContext.FacePoint(r, face, (a0 + a1) / 2, top + 1 + h / 2, -1.2f);
            var k = c.Kit;
            var alongX = face == CityFace.N || face == CityFace.S;
            // Frame legs.
            foreach (var side in new[] { -1f, 1f })
            {
                var lx = alongX ? p.x + side * w * 0.45f : p.x;
                var lz = alongX ? p.z : p.z + side * w * 0.45f;
                k.Box(lx, top + (h + 1) / 2, lz, 0.25f, h + 1, 0.25f, "metal_dark", collide: false);
            }
            var unity = V(p.x, p.y, p.z);
            var normal = new Vector3(-n.x, 0, n.y);
            var holo = NeonKit.HoloPanel(c.Kit.FxRoot, unity, Quaternion.LookRotation(-normal), new Vector2(w, h), Neon.Pick(c.R), Neon.Pick(c.R), c.R.Next(3), c.R.Next(), 2.4f);
            c.Cells.Put(holo, CityCuller.Geo);
        }

        // ------------------------------------------------------------------ environment kit pieces

        static readonly string[] GroundKinds = { "Shop_Awning", "Shop_Glass", "Shop_Shutter", "Shop_Noodle", "Entrance", "Shop_Glass", "Shop_Awning", "Shop_Boarded" };
        static readonly string[] UpperKinds = { "Window_AC", "Window_Cage", "Window_Double", "Window_Neon", "Balcony", "Window_AC", "Pipes", "Window_Neon", "Damaged" };

        /// <summary>Facade module style for a mass material (ground-floor modules exist in Concrete and Panel only).</summary>
        static string Style(string mat) => mat == "brick" ? "Brick" : mat == "plaster" ? "Plaster" :
            mat == "metal_plate" || mat == "glass_dark" || mat == "corrugated" ? "Panel" : "Concrete";

        static string GroundStyle(string style) => style == "Panel" ? "Panel" : "Concrete";

        static bool ModulesAvailable(string mat)
        {
            var st = Style(mat);
            return CityKitAssets.Has("Building_Facade_" + GroundStyle(st) + "_Shop_Glass") && CityKitAssets.Has("Building_Facade_" + st + "_Window_AC");
        }

        static string Pick(CityContext c, string prefix, string[] kinds, string fallback)
        {
            var name = prefix + kinds[c.R.Next(kinds.Length)];
            return CityKitAssets.Has(name) ? name : prefix + fallback;
        }

        /// <summary>
        /// Skin the two lowest storeys of a street face with facade modules on the kit's 4 m grid (shops, noodle bars,
        /// entrances below; balconies, AC, cages, neon windows above), with piers at odd ends. False when over budget.
        /// </summary>
        static bool ModuleFace(CityContext c, CityBuilding b, byte face)
        {
            var f = b.Foot;
            CityFace.Line(f, face, out var a0, out var a1, out _, out _, out _);
            var len = a1 - a0;
            var n = Mathf.FloorToInt(len / 4f);
            if (n < 1 || c.ModuleBudget < n * 2) return false;
            var st = Style(b.Material);
            var gp = "Building_Facade_" + GroundStyle(st) + "_";
            var up = "Building_Facade_" + st + "_";
            var yaw = CityKitAssets.FaceYaw(face);
            var alongX = face == CityFace.N || face == CityFace.S;
            const float y0 = CityLayout.Curb, y1 = CityLayout.Curb + CityLayout.FloorH;
            var s0 = a0 + (len - n * 4f) / 2 + 2f;
            for (var i = 0; i < n; i++)
            {
                var s = s0 + i * 4f;
                var g = Pick(c, gp, GroundKinds, "Shop_Glass");
                var p = CityContext.FacePoint(f, face, s, y0, 0.16f);
                c.Prop(g, p.x, y0, p.z, yaw, CityCuller.Small);
                if (!g.EndsWith("Boarded") && !g.EndsWith("Entrance"))
                {
                    var gl = CityContext.FacePoint(f, face, s, 0.18f, 2.4f);
                    c.GlowGround(gl.x, gl.y, gl.z, alongX ? 4 : 3.2f, alongX ? 3.2f : 4, g.EndsWith("Noodle") ? 0xff9a6au : 0xffc890u, 0.26f);
                }
                p = CityContext.FacePoint(f, face, s, y1, 0.16f);
                c.Prop(Pick(c, up, UpperKinds, "Window_AC"), p.x, y1, p.z, yaw, CityCuller.Small);
            }
            var rest = (len - n * 4f) / 2;
            if (rest >= 0.5f && CityKitAssets.Has(up + "Pier") && CityKitAssets.Has(gp + "Pier"))
                foreach (var e in new[] { s0 - 2f - 0.26f, s0 + (n - 1) * 4f + 2f + 0.26f })
                {
                    var p = CityContext.FacePoint(f, face, e, y0, 0.16f);
                    c.Prop(gp + "Pier", p.x, y0, p.z, yaw, CityCuller.Small, 1, false);
                    c.Prop(up + "Pier", p.x, y1, p.z, yaw, CityCuller.Small, 1, false);
                    c.KitPieces += 2;
                }
            c.ModuleBudget -= n * 2;
            c.KitPieces += n * 2;
            return true;
        }

        /// <summary>
        /// Complete kit building on its lot: the model fronts the street (margins left and right for its side
        /// projections), a simple mass + window skin inside it stands in when the model is culled at distance, and a
        /// lower back wing fills the rest of the lot to the alley or the neighbouring row.
        /// </summary>
        static bool KitBuilding(CityContext c, CityBuilding b)
        {
            var m = CityLayout.KitModels[b.Kit];
            if (!CityKitAssets.Has(m.name)) return false;
            var face = (b.Street & CityFace.S) != 0 ? CityFace.S : CityFace.N;
            var k = c.Kit;
            var f = b.Foot;
            var x = f.CX;
            var z = face == CityFace.S ? f.Z1 - m.d / 2 : f.Z0 + m.d / 2;
            var yaw = CityKitAssets.FaceYaw(face);
            KitEmission.Fix(c.Prop(m.name, x, CityLayout.Curb, z, yaw, CityCuller.Kit));
            c.KitPieces++;
            // Far stand-in (hidden inside the model up close) and the mass collider.
            var inset = CityLayout.IsLandmarkKit(b.Kit) ? 2.2f : 0.35f;
            var mass = new PRect(x - m.w / 2 + inset, z - m.d / 2 + inset, x + m.w / 2 - inset, z + m.d / 2 - inset);
            k.Box(mass.CX, (m.roof - 0.4f) / 2, mass.CZ, mass.W, m.roof - 0.4f, mass.D, "concrete_dark", collide: false);
            c.Skin(b.Skin, mass, CityLayout.GroundH, m.roof - 1.2f, (b.Seed % 997) * 2.2f);
            k.SolidCollider(x, m.roof / 2, z, m.w, m.roof, m.d);
            // Keep players out of the narrow side slots.
            var front = face == CityFace.S ? f.Z1 : f.Z0;
            k.Wall(f.X0 + CityLayout.KitMargin / 2, 1.5f, front, CityLayout.KitMargin, 3f, 0.3f);
            k.Wall(f.X1 - CityLayout.KitMargin / 2, 1.5f, front, CityLayout.KitMargin, 3f, 0.3f);
            var g = CityContext.FacePoint(f, face, x, 0.18f, 2.6f);
            c.GlowGround(g.x, g.y, g.z, m.w, 4f, 0xffc890, 0.3f);
            // Back wing.
            var back = face == CityFace.S ? new PRect(f.X0, f.Z0, f.X1, z - m.d / 2) : new PRect(f.X0, z + m.d / 2, f.X1, f.Z1);
            if (back.D > 1f)
            {
                var h = Mathf.Clamp(m.roof * c.Range(0.6f, 0.9f), 9f, 30f);
                k.Box(back.CX, h / 2, back.CZ, back.W, h, back.D, b.Material, uvSeed: (b.Seed % 101) * 0.37f);
                c.Skin(b.Skin, back, CityLayout.GroundH, h - 0.7f, (b.Seed % 997) * 2.2f + 30);
                Parapet(c, back, h, b.Material, 1f);
                var wing = new CityBuilding { Foot = back, Tower = back, Height = h, Floors = Mathf.RoundToInt(h / CityLayout.FloorH), Seed = b.Seed + 3,
                    Material = b.Material, District = b.District, Street = (byte)(b.Street & (CityFace.E | CityFace.W)), Alley = (byte)(b.Alley & ~face) };
                foreach (var fc in CityFace.All)
                {
                    if ((wing.Street & fc) != 0) Shopfront(c, wing, fc);
                    else if ((wing.Alley & fc) != 0) AlleyFace(c, wing, fc);
                }
                c.Queue(back, 0, h, (byte)(wing.Street | wing.Alley), DistrictNeon(b.District) * 0.7f, 2, b.Seed + 5);
                Roof(c, back, h, wing);
            }
            c.MapRect("block", f);
            return true;
        }

        // ------------------------------------------------------------------ landmarks (CityLandmarks kit)

        /// <summary>
        /// One-off landmark on its lot: the model's bounds are centred in the lot, front toward the site's street face.
        /// It lives outside the culling cells (its LODGroup handles distance; LOD2 keeps the silhouette and the lit
        /// windows) and keeps its manifest colliders (World layer). False when the prefab is missing (procedural fallback).
        /// </summary>
        static bool Landmark(CityContext c, CityBuilding b)
        {
            var name = b.LandmarkAsset;
            if (!CityKitAssets.Has(name)) { b.LandmarkAsset = null; return false; }
            var info = EnvProps.Get(name);
            var bc = info != null ? info.BoundsCenter : Vector3.zero;
            // Bounds centre (Unity local) -> prototype offset after the yaw.
            var off = YawQ(b.AssetYaw) * new Vector3(bc.x, 0, bc.z);
            float px = b.AssetX + off.x, pz = b.AssetZ - off.z;
            var go = KitEmission.Fix(c.Kit.Prop(name, px, CityLayout.Curb, pz, b.AssetYaw));
            go.transform.SetParent(c.LandmarkRoot, true);
            c.Props++;
            c.KitPieces++;
            c.LandmarksPlaced++;
            // From here on the lot counts as an asset building (no street storefront runs or skybridges onto it).
            b.Asset = name;
            if (c.LandmarksPlaced == CityLayout.LandmarkSites.Length)
                Debug.Log($"[landmarks] {c.LandmarksPlaced} landmarks placed; plaza bespoke blocks {PzKit.BespokeBlocks}; district pieces so far {c.DistrictPieces}, light kit budget left {c.LightKitBudget}");
            // Pavement glow in front of the entrance and a map shape of the lot.
            CityFace.Line(b.Foot, FaceOf(b.AssetYaw), out var a0, out var a1, out _, out _, out var alongX);
            var g = CityContext.FacePoint(b.Foot, FaceOf(b.AssetYaw), (a0 + a1) / 2, 0.18f, 2.6f);
            c.GlowGround(g.x, g.y, g.z, alongX ? Mathf.Min(24f, a1 - a0) : 4f, alongX ? 4f : Mathf.Min(24f, a1 - a0), DistrictGlow(b.District), 0.32f);
            c.MapRect("block", b.Foot);
            return true;
        }

        static byte FaceOf(float yaw)
        {
            foreach (var f in CityFace.All) if (Mathf.Abs(Mathf.DeltaAngle(CityKitAssets.FaceYaw(f) * Mathf.Rad2Deg, yaw * Mathf.Rad2Deg)) < 1f) return f;
            return CityFace.S;
        }

        static uint DistrictGlow(CityDistrict d) => d switch
        {
            CityDistrict.NeonMarket => 0xff6a3a, CityDistrict.KowloonStacks => 0xffc070, CityDistrict.ArcologyGate => 0x9adcff, CityDistrict.CanalWard => 0xffc890, _ => 0xff8e30,
        };

        // ------------------------------------------------------------------ detailed modules

        static void Module(CityContext c, CityBuilding b)
        {
            c.Prop(b.Asset, b.AssetX, CityLayout.Curb, b.AssetZ, b.AssetYaw, CityCuller.Geo);
            var r = new PRect(b.AssetX - b.AssetW / 2, b.AssetZ - b.AssetD / 2, b.AssetX + b.AssetW / 2, b.AssetZ + b.AssetD / 2);
            byte faces = 0;
            foreach (var fc in CityFace.All)
            {
                if ((b.Street & fc) == 0) continue;
                // Only faces that actually reach the street line get dressing.
                CityFace.Line(r, fc, out _, out _, out var line, out _, out _);
                CityFace.Line(b.Foot, fc, out _, out _, out var lotLine, out _, out _);
                if (Mathf.Abs(line - lotLine) < 1f) faces |= fc;
            }
            c.Queue(r, 0, b.Height, faces, DistrictNeon(b.District) * 0.7f, 2, b.Seed);
            c.MapRect("block", r);
        }
    }

    /// <summary>
    /// District identity for the procedural masses (CityLandmarks kit pieces, seeded per building): Kowloon shanty roofs,
    /// cage stacks and cantilevered rooms; Neon Market rooftop pagodas, sign frames, sign armatures and blade signs;
    /// Arcology crowns, spires and LED fins; Canal Ward roof gardens and balcony stacks; Foundry roof plant and pipe
    /// risers. Pieces sit on the city's storey grid (ground 4.4 m, storeys 3.4 m), never collide (they are above the
    /// pavement) and go into culling cells. Missing prefabs are simply skipped.
    /// </summary>
    public static class DistrictPieces
    {
        static readonly (string name, float w, float d, float minH)[] RoofNM = { ("LMM_Roof_NM_Pagoda", 10.6f, 10.6f, 9f), ("LMM_Roof_NM_SignFrame", 12.4f, 3.6f, 9f) };
        static readonly (string name, float w, float d, float minH)[] RoofKS = { ("LMM_Roof_KS_Shanties_A", 9.2f, 9.2f, 12f), ("LMM_Roof_KS_Shanties_B", 12.2f, 7.2f, 12f) };
        static readonly (string name, float w, float d, float minH)[] RoofAG = { ("LMM_Roof_AG_Crown_A", 14.6f, 14.6f, 30f), ("LMM_Roof_AG_Crown_B", 10.6f, 10.6f, 24f), ("LMM_Roof_AG_Spire", 10.4f, 10.4f, 30f) };
        static readonly (string name, float w, float d, float minH)[] RoofCW = { ("LMM_Roof_CW_Garden", 9.4f, 8.4f, 9f) };
        static readonly (string name, float w, float d, float minH)[] RoofFR = { ("LMM_Roof_FR_Vents", 10.4f, 8.4f, 7f) };

        static (string name, float w, float d, float minH)[] RoofSets(CityDistrict d) => d switch
        {
            CityDistrict.NeonMarket => RoofNM, CityDistrict.KowloonStacks => RoofKS, CityDistrict.ArcologyGate => RoofAG, CityDistrict.CanalWard => RoofCW, _ => RoofFR,
        };

        static float RoofChance(CityDistrict d) => d switch
        {
            CityDistrict.KowloonStacks => 0.85f, CityDistrict.NeonMarket => 0.55f, CityDistrict.ArcologyGate => 0.75f, CityDistrict.CanalWard => 0.5f, _ => 0.6f,
        };

        /// <summary>Distance weight: full density within ~110 m of the plaza ring, thinning to half at the megawall.</summary>
        static float Near(PRect r)
        {
            var dx = Mathf.Max(0, Mathf.Abs(r.CX) - CityLayout.ResX);
            var dz = Mathf.Max(0, Mathf.Max(CityLayout.ResZ0 - r.CZ, r.CZ - CityLayout.ResZ1));
            return Mathf.Lerp(1f, 0.5f, Mathf.InverseLerp(110f, 260f, Mathf.Sqrt(dx * dx + dz * dz)));
        }

        /// <summary>Roof set on the roof rect r (top = roof slab height). True when one was placed.</summary>
        public static bool Roof(CityContext c, CityBuilding b, PRect r, float top)
        {
            if (c.DistrictPieceBudget <= 0 || b.Landmark) return false;
            var rng = new System.Random(b.Seed * 31 + 7);
            if (rng.NextDouble() > RoofChance(b.District) * Near(r)) return false;
            var sets = RoofSets(b.District);
            var start = rng.Next(sets.Length);
            for (var k = 0; k < sets.Length; k++)
            {
                var s = sets[(start + k) % sets.Length];
                if (top < s.minH || !CityKitAssets.Has(s.name)) continue;
                // Unrotated (front toward +z) or turned 90 degrees, whichever fits inside the parapet with 0.6 m to spare.
                var yaw = 0f;
                float w = s.w, d = s.d;
                if (r.W - 1.2f < w || r.D - 1.2f < d)
                {
                    if (r.W - 1.2f >= d && r.D - 1.2f >= w) { yaw = Mathf.PI / 2; (w, d) = (d, w); }
                    else continue;
                }
                if (rng.NextDouble() < 0.5) yaw += Mathf.PI;
                var x = r.CX + (float)(rng.NextDouble() - 0.5) * Mathf.Max(0, r.W - 1.2f - w);
                var z = r.CZ + (float)(rng.NextDouble() - 0.5) * Mathf.Max(0, r.D - 1.2f - d);
                KitEmission.Fix(c.Prop(s.name, x, top, z, yaw, CityCuller.Geo, 1, false));
                c.DistrictPieceBudget--;
                c.DistrictPieces++;
                return true;
            }
            return false;
        }

        /// <summary>Facade pieces on the street faces of a procedural mass of height `top`.</summary>
        public static void Facades(CityContext c, CityBuilding b, float top)
        {
            if (c.DistrictPieceBudget <= 0 || b.Landmark || b.Street == 0) return;
            var rng = new System.Random(b.Seed * 17 + 3);
            var near = Near(b.Foot);
            var placed = 0;
            foreach (var face in CityFace.All)
            {
                if ((b.Street & face) == 0 || placed >= 4) continue;
                CityFace.Line(b.Foot, face, out var a0, out var a1, out _, out _, out _);
                var len = a1 - a0;
                if (len < 6f) continue;
                var yaw = CityKitAssets.FaceYaw(face);
                switch (b.District)
                {
                    case CityDistrict.KowloonStacks:
                        for (var i = 0; i < 3 && placed < 4; i++)
                        {
                            if (rng.NextDouble() > 0.8 * near) continue;
                            var cant = rng.NextDouble() < 0.4;
                            var name = cant ? "LMM_Fac_KS_Cantilever" : "LMM_Fac_KS_CageStack";
                            var storeys = cant ? 2 : 3;
                            var floors = Mathf.FloorToInt((top - CityLayout.GroundH - 0.6f) / CityLayout.FloorH);
                            if (floors < storeys + 1) continue;
                            var k = 1 + rng.Next(floors - storeys);
                            if (Put(c, b, face, name, Along(rng, a0, a1, 2f), CityLayout.GroundH + (k - 1) * CityLayout.FloorH, yaw, CityCuller.Small)) placed++;
                        }
                        break;
                    case CityDistrict.NeonMarket:
                        if (top > CityLayout.GroundH + 10.6f && rng.NextDouble() < 0.6 * near && Put(c, b, face, "LMM_Fac_NM_SignStack", Along(rng, a0, a1, 2.5f), CityLayout.GroundH + 0.1f, yaw, CityCuller.Geo)) placed++;
                        if (top > CityLayout.GroundH + 9.5f && rng.NextDouble() < 0.5 * near && Put(c, b, face, "LMM_Fac_NM_Blade", rng.NextDouble() < 0.5 ? a0 + 0.6f : a1 - 0.6f, CityLayout.GroundH, yaw, CityCuller.Geo)) placed++;
                        break;
                    case CityDistrict.CanalWard:
                        for (var i = 0; i < 2 && placed < 4; i++)
                        {
                            var floors = Mathf.FloorToInt((top - CityLayout.GroundH - 0.6f) / CityLayout.FloorH);
                            if (floors < 4 || rng.NextDouble() > 0.65 * near) continue;
                            var k = 1 + rng.Next(floors - 3);
                            if (Put(c, b, face, "LMM_Fac_CW_Balconies", Along(rng, a0, a1, 2f), CityLayout.GroundH + (k - 1) * CityLayout.FloorH, yaw, CityCuller.Small)) placed++;
                        }
                        break;
                    case CityDistrict.FoundryRow:
                        if (top > CityLayout.GroundH + 12.5f && rng.NextDouble() < 0.5 * near && Put(c, b, face, "LMM_Fac_FR_PipeRiser", Along(rng, a0, a1, 2f), CityLayout.GroundH, yaw, CityCuller.Small)) placed++;
                        break;
                    case CityDistrict.ArcologyGate:
                        // LED fins on the two ends of a street face (podium masses only reach 11 m: towers carry them on the shaft)
                        var shaft = b.PodiumHeight > 0 ? b.Tower : b.Foot;
                        var y0 = b.PodiumHeight > 0 ? b.PodiumHeight : CityLayout.GroundH;
                        if (b.Height - y0 < 21f || rng.NextDouble() > 0.55 * near) break;
                        CityFace.Line(shaft, face, out var t0, out var t1, out _, out _, out _);
                        if (Put(c, b, face, "LMM_Fac_AG_LEDFin", t0 + 0.4f, y0, yaw, CityCuller.Geo, shaft)) placed++;
                        if (Put(c, b, face, "LMM_Fac_AG_LEDFin", t1 - 0.4f, y0, yaw, CityCuller.Geo, shaft)) placed++;
                        break;
                }
            }
        }

        static float Along(System.Random rng, float a0, float a1, float margin) => a0 + margin + (float)rng.NextDouble() * Mathf.Max(0, a1 - a0 - 2 * margin);

        static bool Put(CityContext c, CityBuilding b, byte face, string name, float s, float y, float yaw, int group, PRect? on = null)
        {
            if (c.DistrictPieceBudget <= 0 || !CityKitAssets.Has(name)) return false;
            // Just in front of the window skin (0.06 m proud of the mass).
            var p = CityContext.FacePoint(on ?? b.Foot, face, s, y, 0.07f);
            KitEmission.Fix(c.Prop(name, p.x, y, p.z, yaw, group, 1, false));
            c.DistrictPieceBudget--;
            c.DistrictPieces++;
            return true;
        }
    }

    /// <summary>
    /// Placeholder for the environment artist's high-detail cyberpunk building kit (Building_* facade modules).
    /// When those assets land, implement the assembly here (stack the facade modules on the lot faces using
    /// <see cref="CityContext.Prop"/> and keep the mass collider), then set <c>OpenCity.Buildings = new KitBuildings();</c>.
    /// Until then it falls back to <see cref="BoxBuildings"/> for every lot.
    /// </summary>
    public sealed class KitBuildings : ICityBuildings
    {
        readonly BoxBuildings fallback = new();

        public void Build(CityContext c, CityBuilding b) => fallback.Build(c, b);
    }
}
