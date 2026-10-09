using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Unity.AI.Navigation;
using UnityEngine;
using static EOA.ProtoSpace;

namespace EOA
{
    /// <summary>
    /// The open cyberpunk district around the Central Plaza (built by PlazaZone through a few marked hooks).
    ///
    /// Layout (prototype metres, see <see cref="CityLayout"/>): a 721 x 625 m street grid (x -360..360, z -292..332)
    /// with the plaza as its cordoned-off central square. Avenues leave the plaza west and east at z 59 (under the
    /// elevated rail on the east side) and two alleys leave its north corners; quarantine checkpoints mark the cordon.
    /// Around it: Neon Market (west), Arcology Gate (east, podium megatowers), Kowloon Stacks (north), Foundry Row
    /// (north-east) and the Canal Ward (south, with a canal and bridges). The megawall closes the district with sealed
    /// tunnels and the Arcology Gate at the end of the east avenue; the CyberCity skyline rises beyond it.
    ///
    /// Everything lives under one "OpenCity" root with its own <see cref="LevelKit"/> (merged per 32 m cell), excluded
    /// from the plaza NavMesh bake (enemies stay in the plaza arenas), culled by distance (<see cref="CityCuller"/>),
    /// and populated by <see cref="Crowd"/> and <see cref="Traffic"/>. Quest objects, arenas and exits are untouched.
    ///
    /// Environment kit (used as soon as its prefabs are built by EOA → Build Environment Library; procedural
    /// stand-ins otherwise, see <see cref="CityKitAssets"/>): complete Building_MidRise/HighRise models on kit-sized lots
    /// nearest the plaza (with a box + window-skin stand-in for distance), Building_Facade_* modules on the two lowest
    /// storeys of the showcase streets, the kit's vehicles in traffic and parking lanes, mast-arm signals, bus shelters,
    /// vending machines, kiosks, food counters, ramen stall, alley dressing, skybridges and skyline towers.
    /// </summary>
    public sealed class OpenCity
    {
        /// <summary>Master switch (false restores the original enclosed plaza).</summary>
        public static bool Enabled = true;

        /// <summary>
        /// Building factory for every lot. One-line swap point for the facade/building kit:
        /// <c>OpenCity.Buildings = new KitBuildings();</c>
        /// </summary>
        public static ICityBuildings Buildings = new BoxBuildings();

        public const int Seed = 7741;

        public CityLayout Layout { get; private set; }
        public LevelKit Kit { get; private set; }
        public Transform Root { get; private set; }
        public CityCuller Culler { get; private set; }
        public Crowd Crowd { get; private set; }
        public Traffic Traffic { get; private set; }
        public RoadGraph Roads { get; private set; }
        public PedGraph Peds { get; private set; }
        public CityLightPool Lamps { get; private set; }
        /// <summary>One-line build summary (also logged).</summary>
        public string Stats { get; private set; }

        CityCells cells;
        /// <summary>Merged additive FX of the district (lamp cones, sign spill volumes, mist, beacons).</summary>
        readonly FxBatch fx = new(64f);
        readonly List<Vector3> steam = new();
        readonly List<GameObject> emitters = new();
        bool dawn;

        // Points of interest (prototype space).
        static readonly Vector3 NoodleBar = new(-118, 0, 79);
        static readonly Vector3 Graffiti = new(-62, 0, -41);
        static readonly Vector3 SkywalkMarket = new(-138, 6.8f, 59);
        static readonly Vector3 SkywalkCanal = new(140, 6.8f, 236);

        /// <summary>Plaza blocks from PlazaZone.BuildBlocks (x, z, w, d, h): map shapes and street dressing of their outer faces.</summary>
        static readonly (float x, float z, float w, float d, float h)[] PlazaBlocks =
        {
            (-58, -60, 24, 22, 26), (-34, -60, 20, 22, 18), (-20, -62, 12, 18, 12), (20, -62, 12, 18, 14), (34, -60, 20, 22, 22), (58, -60, 24, 22, 30),
            (-60, -32, 22, 18, 20), (-62, -10, 22, 22, 15), (-60, 14, 22, 22, 24), (-62, 36, 22, 18, 17),
            (66, -34, 20, 20, 28), (66, -8, 20, 24, 18), (66, 18, 20, 22, 24), (66, 40, 20, 18, 16),
            (-30, 52, 24, 16, 16), (30, 52, 24, 16, 20), (-30, 66, 24, 10, 12), (30, 66, 24, 10, 14),
            (-44, 82, 26, 22, 14), (-44, 104, 26, 20, 18), (44, 80, 26, 20, 16), (44, 102, 26, 22, 22), (0, 126, 64, 22, 20),
        };

        // ================================================================== plaza hooks

        /// <summary>
        /// Replaces PlazaZone's outer boundary walls: same walls, with openings where the avenues (z 45..71) and the
        /// north-west / north-east alleys leave the plaza. The facility side, the market enclosure and the market street
        /// side walls are unchanged.
        /// </summary>
        public static void PlazaWalls(LevelKit B)
        {
            B.Wall(0, 3, -48.5f, 120, 8, 1);
            B.Wall(0, 3, 115, 120, 8, 1);
            B.Wall(-48.5f, 3, 2, 1, 8, 86);       // west z[-41, 45]
            B.Wall(-48.5f, 3, 93, 1, 8, 44);      // west z[71, 115]
            B.Wall(48.5f, 3, 2.5f, 1, 8, 93);     // east z[-44, 49]
            B.Wall(48.5f, 3, 92.5f, 1, 8, 45);    // east z[70, 115]
            B.Wall(-18.5f, 3, 56, 1, 8, 26);
            B.Wall(18.5f, 3, 56, 1, 8, 26);
            B.Wall(-31, 3, 71.5f, 26, 8, 1);
            B.Wall(31, 3, 71.5f, 26, 8, 1);
            B.Wall(-31, 3, 44.5f, 26, 8, 1);
            B.Wall(31, 3, 44.5f, 26, 8, 1);
            // The market street blocks now back onto the avenues: close the 1 m slot between each pair.
            B.Wall(-42.3f, 3, 60.5f, 0.6f, 8, 1.6f);
            B.Wall(42.3f, 3, 60.5f, 0.6f, 8, 1.6f);
        }

        /// <summary>
        /// Layered skyline ring past the district edge. The flying traffic is created once the district is built
        /// (<see cref="CreateSkyTraffic"/>) so its lanes can clear the roofs; if the district fails it flies high instead.
        /// </summary>
        public static void SkylineAndSkyTraffic(LevelKit B, Transform zoneRoot, bool dawnVariant)
        {
            CyberCity.Skyline(B, V(0, 0, 20), 470, 700, 48, 9002);
        }

        /// <summary>Flyers on lanes 80-140 m up, each lifted above the tallest roof it crosses (roofAt null: above every tower).</summary>
        static void CreateSkyTraffic(Transform zoneRoot, bool dawnVariant, Func<float, float, float> roofAt)
        {
            if (roofAt == null) { SkyTraffic.Create(zoneRoot, V(0, 0, 20), dawnVariant ? 14 : 36, 205, 240, 110, 360, 9003); return; }
            SkyTraffic.Create(zoneRoot, V(0, 0, 20), dawnVariant ? 14 : 36, 80, 140, 100, 360, 9003, roofAt);
        }

        /// <summary>Max roof height on a 16 m grid (Unity space): district buildings, plaza blocks, the megawall, kit skyline towers.</summary>
        sealed class RoofGrid
        {
            const float Cell = 16f, Half = 720f;
            const int N = (int)(Half * 2 / Cell);
            readonly float[] h = new float[N * N];

            public void Add(float x0, float z0, float x1, float z1, float top, float pad = 8f)
            {
                int i0 = Idx(Mathf.Min(x0, x1) - pad), i1 = Idx(Mathf.Max(x0, x1) + pad);
                int j0 = Idx(Mathf.Min(z0, z1) - pad), j1 = Idx(Mathf.Max(z0, z1) + pad);
                for (var i = i0; i <= i1; i++)
                for (var j = j0; j <= j1; j++)
                    h[i * N + j] = Mathf.Max(h[i * N + j], top);
            }

            static int Idx(float v) => Mathf.Clamp(Mathf.FloorToInt((v + Half) / Cell), 0, N - 1);

            public float At(float x, float z) => h[Idx(x) * N + Idx(z)];
        }

        RoofGrid Roofs()
        {
            var g = new RoofGrid();
            foreach (var b in Layout.AllBuildings) g.Add(-b.Foot.X1, b.Foot.Z0, -b.Foot.X0, b.Foot.Z1, b.Height + 8f);
            foreach (var p in PlazaBlocks) g.Add(-(p.x + p.w / 2), p.z - p.d / 2, -(p.x - p.w / 2), p.z + p.d / 2, p.h + 4f);
            const float wx = CityLayout.WallX, z0 = CityLayout.WallZ0, z1 = CityLayout.WallZ1, t = CityLayout.WallT;
            g.Add(-wx - t, z0 - t, wx + t, z0 + t, 100f);
            g.Add(-wx - t, z1 - t, wx + t, z1 + t, 100f);
            g.Add(-wx - t, z0, -wx + t, z1, 100f);
            g.Add(wx - t, z0, wx + t, z1, 100f);
            var kit = Root.Find("KitSkyline");
            if (kit != null)
                foreach (Transform tower in kit)
                {
                    var rs = tower.GetComponentsInChildren<Renderer>();
                    if (rs.Length == 0) continue;
                    var bb = rs[0].bounds;
                    foreach (var r in rs) bb.Encapsulate(r.bounds);
                    g.Add(bb.min.x, bb.min.z, bb.max.x, bb.max.z, bb.max.y + 6f);
                }
            return g;
        }

        // ================================================================== build

        /// <summary>
        /// Build the district under the zone. Never throws: on failure the partial district is removed, the plaza's
        /// street openings are walled off again (the plaza stays exactly as playable as before) and null is returned.
        /// </summary>
        public static async Task<OpenCity> Build(ProceduralZone zone, LevelKit plazaKit, bool dawnVariant, Func<float, string, Task> progress)
        {
            try
            {
                return await BuildDistrict(zone, plazaKit, dawnVariant, progress);
            }
            catch (Exception e)
            {
                Debug.LogError("[city] open district build failed; plaza closed off again: " + e);
                var partial = zone.transform.Find("OpenCity");
                if (partial != null) UnityEngine.Object.Destroy(partial.gameObject);
                plazaKit.Wall(-48.5f, 3, -44.75f, 1, 8, 7.5f);
                plazaKit.Wall(-48.5f, 3, 58, 1, 8, 26);
                plazaKit.Wall(48.5f, 3, -46.25f, 1, 8, 4.5f);
                plazaKit.Wall(48.5f, 3, 59.5f, 1, 8, 21);
                CreateSkyTraffic(zone.transform, dawnVariant, null);
                return null;
            }
        }

        static async Task<OpenCity> BuildDistrict(ProceduralZone zone, LevelKit plazaKit, bool dawnVariant, Func<float, string, Task> progress)
        {
            var t0 = Time.realtimeSinceStartup;
            var city = new OpenCity { dawn = dawnVariant };
            var rootGo = new GameObject("OpenCity");
            rootGo.layer = CombatLayers.World;
            rootGo.transform.SetParent(zone.transform, false);
            // Enemies only fight inside the plaza arenas: keep the district out of the NavMesh bake (fast loads).
            var nav = rootGo.AddComponent<NavMeshModifier>();
            nav.ignoreFromBuild = true;
            city.Root = rootGo.transform;
            var kit = new LevelKit(city.Root) { LightBudget = 2 };
            city.Kit = kit;
            city.Culler = rootGo.AddComponent<CityCuller>();
            city.cells = new CityCells(city.Root, city.Culler, 64f);
            var c = new CityContext
            {
                Kit = kit, Skins = new CityBatch(128f, false), Glow = new CityBatch(64f, true), SkinMats = CityContext.MakeSkins(dawnVariant),
                GlowMat = CityContext.MakeGlow(), Cells = city.cells, R = new System.Random(Seed), Dawn = dawnVariant,
            };

            // ---------------------------------------------------------------- layout
            var layout = new CityLayout();
            layout.Reserved.Add(new PRect(-150, 21, -126, 46.5f));     // market skywalk, north landing
            layout.Reserved.Add(new PRect(-150, 71.5f, -108.5f, 97));   // market skywalk south landing + noodle bar square
            layout.Reserved.Add(new PRect(128, 203.5f, 152, 223.5f));  // canal skywalk, north landing
            layout.Reserved.Add(new PRect(128, 248.5f, 152, 274));     // canal skywalk, south landing
            layout.Generate(Seed);
            city.Layout = layout;
            c.Layout = layout;
            await progress(0.9f, "City streets");

            CityStreets.Roads(c);
            CityStreets.Slabs(c);
            city.Reserve(c);
            await progress(0.91f, "City blocks");

            // Complete kit buildings go to the kit-sized lots nearest the plaza first (they are heavy: 40+ materials each).
            var web = Application.platform == RuntimePlatform.WebGLPlayer;
            AssignKit(layout, web ? 36 : 90);
            c.ModuleBudget = web ? 90 : 260;
            c.VendBudget = web ? 8 : 16;
            c.AcBudget = web ? 12 : 30;
            c.ShelterBudget = web ? 4 : 10;
            c.ClutterBudget = web ? 24 : 60;
            var built = 0;
            for (var i = 0; i < layout.Blocks.Count; i++)
            {
                foreach (var b in layout.Blocks[i].Buildings) { Buildings.Build(c, b); built++; }
                if (i % 10 == 9) await progress(0.91f + 0.02f * i / layout.Blocks.Count, "City blocks");
            }
            await progress(0.93f, "Canal and skywalks");

            var noLamps = new List<PRect>();
            CityStreets.Canal(c);
            CityStreets.Overpass(c, SkywalkMarket.x, 42, 76, SkywalkMarket.y, noLamps);
            CityStreets.Overpass(c, SkywalkCanal.x, 219, 253, SkywalkCanal.y, noLamps);
            CityStreets.Skybridges(c, 3);
            CityStreets.Megawall(c);
            noLamps.Add(new PRect(-84, 40, 84, 78)); // the cordon (avenue mouths) keeps its own lights
            foreach (var b in layout.Blocks)
            {
                CityStreets.LampRow(c, b.Slab, CityFace.E, b.District, noLamps);
                CityStreets.LampRow(c, b.Slab, CityFace.S, b.District, noLamps);
                if (b.X1 == CityLayout.XL[0]) CityStreets.LampRow(c, b.Slab, CityFace.W, b.District, noLamps);
                if (b.Z1 == CityLayout.ZL[0]) CityStreets.LampRow(c, b.Slab, CityFace.N, b.District, noLamps);
            }
            var ring = new PRect(-CityLayout.ResX + CityLayout.RoadHalf, CityLayout.ResZ0 + CityLayout.RoadHalf, CityLayout.ResX - CityLayout.RoadHalf, CityLayout.ResZ1 - CityLayout.RoadHalf);
            CityStreets.LampRow(c, ring, CityFace.E, CityDistrict.ArcologyGate, noLamps);
            CityStreets.LampRow(c, ring, CityFace.S, CityDistrict.CanalWard, noLamps);
            var holoBudget = 34;
            foreach (var b in layout.Blocks) CityStreets.Furniture(c, b, ref holoBudget);
            CityStreets.RoadDressing(c, 40, noLamps);
            city.PointsOfInterest(c);
            await progress(0.94f, "Neon signage");

            // ---------------------------------------------------------------- facade dressing, merging, culling
            var signs = new List<Renderer>();
            var signRoot = Child(city.Root, "Signage");
            var dressed = city.Dress(c, signRoot.transform, signs);
            // The plaza's own neon dressing (PlazaZone → CyberCity.DressFacades: ~200 sign boards, tubes and spill decals,
            // each its own renderer) merges per material and cell like the district's: hundreds of draws fewer around
            // the fight arena. Flickering tubes and holograms stay live.
            var plazaDress = plazaKit.FxRoot.Find("CyberDressing");
            if (plazaDress != null) CityHarvest.Static(plazaDress, signRoot.transform, 64f, signs);
            CityHarvest.Decals(plazaKit.FxRoot, c.Glow, c.GlowMat);
            // Remaining unmerged props of the kit (signs with text) go into culling cells.
            var loose = new List<Transform>();
            foreach (Transform t in kit.PropRoot) loose.Add(t);
            foreach (var t in loose) city.cells.Put(t.gameObject, CityCuller.Geo);
            kit.Finish();
            var geo = kit.Root.Find("Geometry");
            if (geo != null) foreach (Transform t in geo) if (t.TryGetComponent<Renderer>(out var r)) city.Culler.Add(r, CityCuller.Geo);
            var skinList = new List<Renderer>();
            c.Skins.Finish(Child(city.Root, "WindowSkins").transform, "city_skin", false, skinList);
            // the lit window skins receive the moon / lamp shadows (the masses behind them cast)
            foreach (var r in skinList) r.receiveShadows = true;
            city.Culler.AddRange(skinList, CityCuller.Skin);
            var glowList = new List<Renderer>();
            c.Glow.Finish(Child(city.Root, "Glow").transform, "city_glow", false, glowList);
            city.Culler.AddRange(glowList, CityCuller.Geo);
            city.Culler.AddRange(signs, CityCuller.Geo);
            CityQuality.ApplyTo(city.Culler); // per View Distance, updated live by GraphicsConfig
            city.Culler.CollectShadowCasters(); // small props only cast shadows near the camera
            city.KitSkyline();
            var roofs = city.Roofs();
            CreateSkyTraffic(zone.transform, dawnVariant, roofs.At);
            await progress(0.95f, "Crowds");

            // ---------------------------------------------------------------- life: crowds, traffic, lamps
            city.Roads = RoadGraph.Build();
            city.Peds = PedGraph.Build(city.Roads);
            city.Crowd = await Crowd.Create(city.Root, city.Peds, city.Roads, Crowd.Budget(), progress, c.Obstacles);
            city.Traffic = Traffic.Create(city.Root, city.Roads, city.Crowd, Traffic.Budget(), city.cells);
            // Forward+ handles many small lights: on desktop the street lamps near the player get real lights (warm pools
            // on the wet asphalt that also light the characters) per Effects; WebGL keeps the old shared budget.
            var effects = G.Settings?.Data?.Graphics?.Effects ?? "high";
            var slots = web ? Mathf.Clamp(24 - plazaKit.Lights.Count - kit.Lights.Count, 0, 6) : effects == "low" ? 6 : effects == "medium" ? 9 : 12;
            city.Lamps = rootGo.AddComponent<CityLightPool>();
            // The pooled lamp lights cast a tamed version of the lamp colour (the lamp heads and cones stay saturated).
            var poolCol = c.LampCol.ConvertAll(col => Atmosphere.TameLightColor(col, 0.55f));
            city.Lamps.Init(c.LampPos, poolCol, slots, dawnVariant ? 22f : 60f); // URP units, matching the plaza's lamp lights
            city.steam.AddRange(c.Steam);
            city.NightAtmosphere(c, web);

            // ---------------------------------------------------------------- map
            city.ApplyMap(zone.Definition, c);
            await progress(0.99f, "City ready");

            var ms = (Time.realtimeSinceStartup - t0) * 1000f;
            city.Stats = $"[city] open district built in {ms:0} ms: {layout.Blocks.Count} blocks, {built} buildings, {kit.Pieces} pieces, {kit.Meshes} meshes, " +
                         $"{kit.Triangles} tris, {kit.Colliders} colliders, {c.Props} props, {dressed} facade jobs, {c.KitPieces} kit pieces, {skinList.Count} skin / {glowList.Count} glow / {signs.Count} sign batches, " +
                         $"culler {city.Culler.Renderers} renderers + {city.Culler.Cells} cells, peds {city.Crowd.Pool}, cars {city.Traffic.Pool}, " +
                         $"lights {plazaKit.Lights.Count} plaza + {kit.Lights.Count} city + {city.Lamps.Count} pool, ped graph {city.Peds.Nodes}/{city.Peds.Edges}, road graph {city.Roads.Nodes}/{city.Roads.Lanes}";
            Debug.Log(city.Stats);
            return city;
        }

        static void AssignKit(CityLayout layout, int budget)
        {
            var list = new List<CityBuilding>();
            foreach (var b in layout.AllBuildings)
                if (b.Kit >= 0 && CityKitAssets.Has(CityLayout.KitModels[b.Kit].name)) list.Add(b);
            list.Sort((a, b) => Dist(a).CompareTo(Dist(b)));
            for (var i = 0; i < list.Count && i < budget; i++) list[i].UseKit = true;
            static float Dist(CityBuilding b)
            {
                var dx = Mathf.Max(0, Mathf.Abs(b.Foot.CX) - CityLayout.ResX);
                var dz = Mathf.Max(0, Mathf.Max(CityLayout.ResZ0 - b.Foot.CZ, b.Foot.CZ - CityLayout.ResZ1));
                // Main avenue frontage counts as closer.
                var avenue = Mathf.Abs(b.Foot.CZ - CityLayout.AvenueZ) < 30 ? 0.6f : 1f;
                return (dx * dx + dz * dz) * avenue;
            }
        }

        static GameObject Child(Transform parent, string name)
        {
            var go = new GameObject(name);
            go.layer = CombatLayers.World;
            go.transform.SetParent(parent, false);
            return go;
        }

        // ================================================================== reserve (the plaza and its cordon)

        void Reserve(CityContext c)
        {
            var k = c.Kit;
            var inner = CityLayout.ReserveInner;
            const float h = CityLayout.RoadHalf;
            // Ring sidewalks around the cordon and ground between the plaza slabs and the ring.
            CityStreets.Slab(k, new PRect(-CityLayout.ResX + h, CityLayout.ResZ0 + h, CityLayout.ResX - h, inner.Z0));
            CityStreets.Slab(k, new PRect(-CityLayout.ResX + h, inner.Z1, CityLayout.ResX - h, CityLayout.ResZ1 - h));
            CityStreets.Slab(k, new PRect(-CityLayout.ResX + h, inner.Z0, inner.X0, inner.Z1));
            CityStreets.Slab(k, new PRect(inner.X1, inner.Z0, CityLayout.ResX - h, inner.Z1));
            CityStreets.Slab(k, new PRect(-32, 137, 32, inner.Z1));
            CityStreets.Slab(k, new PRect(80, inner.Z0, inner.X1, inner.Z1), 0, "asphalt");
            CityStreets.Slab(k, new PRect(inner.X0, inner.Z0, -80, inner.Z1), 0, "asphalt");
            CityStreets.Slab(k, new PRect(-80, inner.Z0, 80, -80), 0, "concrete_dark");
            CityStreets.Slab(k, new PRect(-80, 130, 80, inner.Z1), 0, "asphalt");
            c.MapRect("floor", new PRect(-CityLayout.ResX + h, CityLayout.ResZ0 + h, CityLayout.ResX - h, CityLayout.ResZ1 - h));

            // Liner buildings hide the plaza blocks' backs and give the ring streets shopfronts.
            Liner(c, new PRect(76, -44, 83.5f, -14), CityFace.E, CityFace.N, 0);
            Liner(c, new PRect(76, -14, 83.5f, 18), CityFace.E, 0, 1);
            Liner(c, new PRect(76, 18, 83.5f, 46.5f), CityFace.E, CityFace.S, 2);
            Liner(c, new PRect(57, 71.5f, 83.5f, 113), (byte)(CityFace.E | CityFace.N), 0, 3);
            Liner(c, new PRect(32, 113, 83.5f, 139.5f), (byte)(CityFace.E | CityFace.S), 0, 4);
            Liner(c, new PRect(-83.5f, -41, -71, -11), CityFace.W, CityFace.N, 5);
            Liner(c, new PRect(-83.5f, -11, -71, 17), CityFace.W, 0, 6);
            Liner(c, new PRect(-83.5f, 17, -71, 46.5f), CityFace.W, CityFace.S, 7);
            Liner(c, new PRect(-83.5f, 71.5f, -57, 113), (byte)(CityFace.W | CityFace.N), 0, 8);
            Liner(c, new PRect(-83.5f, 113, -32, 139.5f), (byte)(CityFace.W | CityFace.S), 0, 9);

            // Outer faces of plaza blocks that now look onto the avenues, the alleys and the ring street.
            PlazaFace(c, 9, CityFace.S, true);     // (-62, 36) onto the west avenue
            PlazaFace(c, 13, CityFace.S, true);    // (66, 40) onto the east avenue
            PlazaFace(c, 18, CityFace.N, true);    // (-44, 82) onto the west avenue
            PlazaFace(c, 20, CityFace.N, true);    // (44, 80) onto the east avenue
            PlazaFace(c, 22, CityFace.S, true);    // (0, 126) onto the south ring street
            PlazaFace(c, 14, CityFace.W, false);   // market street blocks backing onto the avenue pockets
            PlazaFace(c, 16, CityFace.W, false);
            PlazaFace(c, 15, CityFace.E, false);
            PlazaFace(c, 17, CityFace.E, false);
            PlazaFace(c, 6, CityFace.N, false);    // (-60, -32) onto the north-west alley
            PlazaFace(c, 10, CityFace.N, false);   // (66, -34) onto the north-east alley
            for (var i = 0; i < PlazaBlocks.Length; i++)
            {
                var p = PlazaBlocks[i];
                c.MapRect("block", p.x, p.z, p.w, p.d);
            }

            Compound(c);
            Avenue(c, 1);
            Avenue(c, -1);
            Alley(c, new PRect(-83.5f, -49.5f, -48.5f, -41), true);
            Alley(c, new PRect(48.5f, -49.5f, 83.5f, -44), false);
        }

        void Liner(CityContext c, PRect foot, byte street, byte alley, int i)
        {
            var b = new CityBuilding
            {
                Foot = foot, Tower = foot, District = CityLayout.DistrictAt(foot.CX, foot.CZ), Seed = 5100 + i * 37,
                Material = i % 3 == 0 ? "concrete_dark" : i % 3 == 1 ? "plaster" : "brick", Skin = i % 2 == 0 ? CityContext.SkinWarm : CityContext.SkinNeon,
                Floors = 6 + (i * 5) % 8, Street = street, Alley = alley,
            };
            b.Height = CityLayout.GroundH + (b.Floors - 1) * CityLayout.FloorH;
            Buildings.Build(c, b);
        }

        static void PlazaFace(CityContext c, int index, byte face, bool shops)
        {
            var p = PlazaBlocks[index];
            var b = new CityBuilding { Foot = new PRect(p.x - p.w / 2, p.z - p.d / 2, p.x + p.w / 2, p.z + p.d / 2), Height = p.h, Seed = 6100 + index };
            if (shops) BoxBuildings.Shopfront(c, b, face);
            c.Queue(b.Foot, 0, p.h, face, shops ? 0.9f : 0.6f, 2, b.Seed);
        }

        /// <summary>Walled Aether Research Division compound behind the facility gate (north of the plaza).</summary>
        static void Compound(CityContext c)
        {
            var k = c.Kit;
            var inner = CityLayout.ReserveInner;
            const float wh = 12f;
            k.Box(0, wh / 2, inner.Z0 + 0.5f, 2 * inner.X1, wh, 1f, "concrete_dark");
            k.Box(inner.X1 - 0.5f, wh / 2, (inner.Z0 + 1 - 49.5f) / 2, 1f, wh, -49.5f - inner.Z0 - 1, "concrete_dark");
            k.Box(inner.X0 + 0.5f, wh / 2, (inner.Z0 + 1 - 49.5f) / 2, 1f, wh, -49.5f - inner.Z0 - 1, "concrete_dark");
            k.Box(76.75f, wh / 2, -49.75f, 13.5f, wh, 0.5f, "concrete_dark");
            k.Box(-76.75f, wh / 2, -49.75f, 13.5f, wh, 0.5f, "concrete_dark");
            // Red top strip, floodlit panels and warning signs facing the streets.
            k.Box(0, wh + 0.1f, inner.Z0 - 0.02f, 2 * inner.X1, 0.15f, 0.08f, "emit_red", collide: false, shadow: false);
            k.Box(inner.X1 + 0.02f, wh + 0.1f, -74.5f, 0.08f, 0.15f, 50, "emit_red", collide: false, shadow: false);
            k.Box(inner.X0 - 0.02f, wh + 0.1f, -74.5f, 0.08f, 0.15f, 50, "emit_red", collide: false, shadow: false);
            for (var x = -72f; x <= 72f; x += 24f)
            {
                k.Box(x, 6.5f, inner.Z0 - 0.06f, 9f, 4.2f, 0.12f, "lab_panel", collide: false);
                c.GlowWall(x, 9.6f, inner.Z0 - 0.1f, 0, -1, 10, 6, 0xbfe8ff, 0.25f);
            }
            k.Sign(-30, 7.2f, inner.Z0 - 0.2f, 16, 1.6f, Mathf.PI, new[] { "AETHER RESEARCH DIVISION" }, fg: 0x9fd8ee, bg: 0x0c141a, glow: 1.1f, border: 0);
            k.Sign(30, 7.2f, inner.Z0 - 0.2f, 13, 1.4f, Mathf.PI, new[] { "RESTRICTED  ·  NO ENTRY" }, fg: 0xff6a5a, bg: 0x160606, glow: 1.3f, border: 0xff2020);
            k.Sign(inner.X1 + 0.2f, 7.2f, -74, 13, 1.4f, Mathf.PI / 2, new[] { "RESTRICTED  ·  NO ENTRY" }, fg: 0xff6a5a, bg: 0x160606, glow: 1.3f, border: 0xff2020);
            k.Sign(inner.X0 - 0.2f, 7.2f, -74, 13, 1.4f, -Mathf.PI / 2, new[] { "RESTRICTED  ·  NO ENTRY" }, fg: 0xff6a5a, bg: 0x160606, glow: 1.3f, border: 0xff2020);
            c.MapRect("block", 0, (inner.Z0 - 71) / 2, 2 * inner.X1, -71 - inner.Z0);
            c.Label("AETHER RESEARCH", 0, -86);
        }

        /// <summary>Avenue band from the plaza (x ±49) to the ring street (x ±83.5): sidewalks, markings, the quarantine checkpoint.</summary>
        void Avenue(CityContext c, int side)
        {
            var k = c.Kit;
            var inner = CityLayout.ReserveInner;
            float x0 = side > 0 ? 49 : inner.X0, x1 = side > 0 ? inner.X1 : -49;
            var xc = (x0 + x1) / 2; var len = x1 - x0;
            const float z = CityLayout.AvenueZ;
            CityStreets.Slab(k, new PRect(x0, z - 12.5f, x1, z - 8));
            CityStreets.Slab(k, new PRect(x0, z + 8, x1, z + 12.5f));
            k.Box(xc, 0.006f, z - 0.16f, len, 0.012f, 0.1f, "metal_yellow", collide: false, shadow: false);
            k.Box(xc, 0.006f, z + 0.16f, len, 0.012f, 0.1f, "metal_yellow", collide: false, shadow: false);
            k.Box(xc, 0.01f, z - 7.88f, len, 0.02f, 0.12f, "emit_strip_cyan", collide: false, shadow: false);
            k.Box(xc, 0.01f, z + 7.88f, len, 0.02f, 0.12f, "emit_strip_cyan", collide: false, shadow: false);
            c.MapRect("road", xc, z, len, 16);
            // Quarantine checkpoint: jersey barriers across the road with a walk-through gap, a frame with the sign and beacons.
            var cx = side * 74f;
            foreach (var bz in new[] { 52.6f, 55.3f, 62.7f, 65.4f })
                c.Prop(bz == 55.3f && side > 0 ? "Barrier_Jersey_Broken" : "Barrier_Jersey", cx, 0, bz, Mathf.PI / 2 + (bz - 59) * 0.01f);
            foreach (var pz in new[] { 51.4f, 66.6f })
            {
                k.Box(cx, 2.4f, pz, 0.25f, 4.8f, 0.25f, "metal_dark", collide: false);
                k.SolidCollider(cx, 2.4f, pz, 0.3f, 4.8f, 0.3f);
            }
            k.Box(cx, 4.9f, z, 0.25f, 0.25f, 15.5f, "metal_dark", collide: false);
            k.Sign(cx + side * 0.2f, 4.2f, z, 7.5f, 1.1f, side * Mathf.PI / 2, new[] { "QUARANTINE CORDON" }, fg: 0xffd25a, bg: 0x1a1404, glow: 1.4f, border: 0xffa21f);
            NeonField.Add(V(cx, 4.2f, z), ProtoSpace.Hex(0xffb030), 1.4f, 9f);
            k.Sign(cx - side * 0.2f, 4.2f, z, 7.5f, 1.1f, -side * Mathf.PI / 2, new[] { "CORDON EXIT" }, fg: 0xffd25a, bg: 0x1a1404, glow: 1.4f, border: 0xffa21f);
            c.GlowCross(cx, 5.2f, z - 3, 1.4f, 0xff2030, 1.6f);
            c.GlowCross(cx, 5.2f, z + 3, 1.4f, 0x2050ff, 1.6f);
            c.GlowGround(cx, 0.03f, z, 6, 16, 0xffb030, 0.2f);
            // Guard booth on the far sidewalk and an abandoned car inside the cordon.
            var bx = side * 79f;
            k.Box(bx, CityLayout.Curb + 1.3f, z - 10.2f, 2.4f, 2.6f, 2.2f, "metal_painted_white");
            k.Box(bx, CityLayout.Curb + 1.6f, z - 9.08f, 1.8f, 0.9f, 0.05f, "window_lit_cool", collide: false, shadow: false);
            k.Box(bx, CityLayout.Curb + 2.7f, z - 10.2f, 2.8f, 0.15f, 2.6f, "metal_dark", collide: false);
            if (CityKitAssets.Has("Barricade_Sheet_Metal_2m") && CityKitAssets.Has("Sandbag_Wall_2m"))
            {
                // Sheet-metal barricades close both sidewalks at the line; sandbags flank the walk-through gap.
                foreach (var sz in new[] { z - 11.4f, z - 9.2f, z + 9.2f, z + 11.4f })
                    c.Prop("Barricade_Sheet_Metal_2m", cx, CityLayout.Curb, sz, side > 0 ? Mathf.PI / 2 : -Mathf.PI / 2);
                c.Prop("Sandbag_Wall_2m", cx - side * 1.6f, 0, z - 3.2f, side > 0 ? -Mathf.PI / 2 : Mathf.PI / 2);
                c.Prop("Sandbag_Wall_2m", cx - side * 1.6f, 0, z + 3.2f, side > 0 ? -Mathf.PI / 2 : Mathf.PI / 2);
                c.KitPieces += 6;
            }
            c.Prop(CityContext.KitOr("CyberCar_Sedan_Wrecked", "Car_Sedan_Wrecked"), side * 63f, 0, z - 4.5f, side * 0.35f);
            c.Prop("TrafficCone", side * 69f, 0, z + 1.2f, 0.4f);
            c.Prop("TrafficCone", side * 68f, 0, z - 2.1f, 1.3f);
            if (side > 0)
            {
                // Underpass beneath the elevated rail: cyan wash and strips on the pier.
                c.GlowGround(52, 0.03f, z, 9, 18, 0x00e5ff, 0.28f);
                foreach (var sx in new[] { 51f, 53f })
                foreach (var sz in new[] { 55.16f, 56.84f })
                    k.Box(sx, 4, sz, 0.08f, 6, 0.06f, "emit_strip_cyan", collide: false, shadow: false);
            }
            c.Label("CORDON", side * 70, z + 16);
        }

        void Alley(CityContext c, PRect a, bool aether)
        {
            var k = c.Kit;
            var zc = a.CZ;
            // Dumpster against the compound wall, bags, pipes, cables, lanterns and steam.
            var dx = a.CX + (aether ? -8 : 10);
            k.Box(dx, CityLayout.Curb + 0.5f, a.Z0 + 0.7f, 1.8f, 1.3f, 1.1f, "metal_painted_green");
            for (var i = 0; i < 4; i++) k.Box(dx + 1.6f + i * 0.6f, 0.25f, a.Z0 + 0.6f + (i % 2) * 0.3f, 0.6f, 0.5f, 0.55f, "black", collide: false);
            k.Box(a.CX, 3.2f, a.Z0 + 0.12f, a.W, 0.14f, 0.14f, "metal_rusted", collide: false);
            k.Box(a.CX, 4.0f, a.Z0 + 0.12f, a.W, 0.1f, 0.1f, "metal_dark", collide: false);
            for (var i = 0; i < 3; i++)
            {
                var x = a.X0 + a.W * (0.2f + 0.3f * i);
                CityStreets.Cable(k, x, 7 + i, a.Z0, x + 3, 6.5f + i, a.Z1, 0.25f);
                c.GlowCross(x + 1.5f, 4.4f, zc, 0.8f, aether ? 0x7fd8ffu : 0xff6a3au, 1.2f);
                c.GlowGround(x + 1.5f, 0.03f, zc, 3.5f, 3.5f, aether ? 0x7fd8ffu : 0xff6a3au, 0.2f);
            }
            steam.Add(V(a.X0 + a.W * 0.25f, 0.05f, zc));
            steam.Add(V(a.X0 + a.W * 0.8f, 0.05f, zc + 1));
            c.Prop("TrafficCone", aether ? a.X0 + 1.2f : a.X1 - 1.2f, 0, a.Z0 + 1.0f, 0.5f);
            c.Prop("TrafficCone", aether ? a.X0 + 1.4f : a.X1 - 1.4f, 0, a.Z1 - 1.0f, 2.1f);
            c.MapRect("road", a);
            if (aether) GraffitiWall(c);
        }

        /// <summary>The Aether graffiti: the monument's sigil painted in glowing light on the alley wall (north face of the (-60,-32) block).</summary>
        void GraffitiWall(CityContext c)
        {
            var k = c.Kit;
            var p = Graffiti;
            const float wallZ = -41.06f;
            var parent = c.Kit.FxRoot;
            var center = V(p.x, 4.4f, wallZ);
            var cyan = new Color(0.37f, 0.85f, 1f);
            var violet = new Color(0.65f, 0.48f, 1f);
            // Broken ring (two arcs), the core diamond and radiating strokes.
            const int seg = 18;
            for (var i = 0; i < seg; i++)
            {
                if (i == 4 || i == 13) continue;
                float a0 = i / (float)seg * Mathf.PI * 2, a1 = (i + 1) / (float)seg * Mathf.PI * 2;
                NeonKit.Strip(parent, center + new Vector3(Mathf.Cos(a0) * 1.9f, Mathf.Sin(a0) * 1.9f, -0.02f), center + new Vector3(Mathf.Cos(a1) * 1.9f, Mathf.Sin(a1) * 1.9f, -0.02f), cyan, 0.07f, Vector3.back);
            }
            NeonKit.Strip(parent, center + new Vector3(0, 0.9f, -0.03f), center + new Vector3(0.55f, 0, -0.03f), violet, 0.08f, Vector3.back);
            NeonKit.Strip(parent, center + new Vector3(0.55f, 0, -0.03f), center + new Vector3(0, -0.9f, -0.03f), violet, 0.08f, Vector3.back);
            NeonKit.Strip(parent, center + new Vector3(0, -0.9f, -0.03f), center + new Vector3(-0.55f, 0, -0.03f), violet, 0.08f, Vector3.back);
            NeonKit.Strip(parent, center + new Vector3(-0.55f, 0, -0.03f), center + new Vector3(0, 0.9f, -0.03f), violet, 0.08f, Vector3.back);
            for (var i = 0; i < 8; i++)
            {
                var a = i / 8f * Mathf.PI * 2 + 0.2f;
                var d = new Vector3(Mathf.Cos(a), Mathf.Sin(a), 0);
                NeonKit.Strip(parent, center + d * 2.3f + Vector3.back * 0.02f, center + d * (2.8f + (i % 3) * 0.3f) + Vector3.back * 0.02f, i % 2 == 0 ? cyan : violet, 0.05f, Vector3.back);
            }
            // Painted words under the sigil.
            var text = new GameObject("GraffitiText");
            text.transform.SetParent(parent, false);
            text.transform.SetPositionAndRotation(V(p.x, 0.75f, wallZ - 0.03f), Quaternion.identity);
            var tm = text.AddComponent<TextMesh>();
            tm.text = "THE AETHER LISTENS";
            tm.font = WorldText.Font;
            tm.fontSize = 96;
            tm.characterSize = 0.045f;
            tm.anchor = TextAnchor.MiddleCenter;
            tm.alignment = TextAlignment.Center;
            tm.color = new Color(0.5f, 0.9f, 1f);
            var mr = text.GetComponent<MeshRenderer>();
            mr.sharedMaterial = WorldText.Material;
            mr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            c.GlowWall(p.x, 4.0f, wallZ - 0.05f, 0, -1, 9, 8, 0x5fd8ff, 0.45f);
            c.GlowGround(p.x, 0.03f, -44.5f, 7, 5, 0x7fb8ff, 0.3f);
            k.PointLight(p.x, 3.6f, -44.6f, 0x7fd8ff, 70, 11, 1.6f);
            c.Label("AETHER ALLEY", p.x, -46);
        }

        // ================================================================== points of interest

        void PointsOfInterest(CityContext c)
        {
            var k = c.Kit;
            // Noodle bar in the market square at the foot of the skywalk (the kit's ramen stall when it is built).
            var x = NoodleBar.x; var z = NoodleBar.z;
            if (CityKitAssets.Has("Ramen_Stall"))
            {
                c.Prop("Ramen_Stall", x, CityLayout.Curb, z - 1.0f, Mathf.PI);
                c.KitPieces++;
            }
            else NoodleStand(c, x, z);
            k.Sign(x, 4.3f, z - 2.75f, 6.5f, 1.2f, Mathf.PI, new[] { "NOODLE BAR" }, fg: 0xffb070, bg: 0x200a08, glow: 1.8f, border: 0xff3a2a);
            // Holographic ramen advert floating over the sign (DreamLayer advert).
            var ramenAd = NeonKit.HoloPanel(k.FxRoot, V(x, 7.0f, z - 2.9f), Quaternion.Euler(0, 180, 0), new Vector2(5.4f, 3.04f), Neon.Gold, Neon.Magenta, 1, 4401, 2.4f);
            NeonKit.ShowAd(ramenAd, "ad_ramen");
            NeonField.Add(V(x, 3.8f, z - 4f), ProtoSpace.Hex(0xff6a9a), 1.6f, 9f);
            NeonField.Add(V(x, 2.6f, z - 1.5f), ProtoSpace.Hex(0xffb46a), 1.8f, 7f);
            c.GlowGround(x, 0.18f, z - 3, 10, 6, 0xffb46a, 0.4f);
            k.PointLight(x, 2.9f, z - 1.8f, 0xffb46a, 90, 12, 1.6f);
            steam.Add(V(x + 2.2f, 1.35f, z + 1.6f));
            for (var i = 0; i < 3; i++) c.Prop(i == 1 ? "MarketStall_Blue" : "MarketStall", -146 + i * 4.2f, CityLayout.Curb, 93.5f, Mathf.PI);
            c.Prop("Bench_Street", -128, CityLayout.Curb, 92, Mathf.PI);
            // Pylon billboards over the two skywalk squares.
            if (CityKitAssets.Has("Billboard_Pole_Double"))
            {
                c.Prop("Billboard_Pole_Double", -147, CityLayout.Curb, 78, Mathf.PI, CityCuller.Geo);
                c.Prop("Billboard_Pole_Double", 147, CityLayout.Curb, 268, 0, CityCuller.Geo);
                c.KitPieces += 2;
            }
            c.Prop("Bench_Street", -112, CityLayout.Curb, 92, Mathf.PI);
            c.Label("NOODLE BAR", x, z + 6);
            c.Label("SKYWALK", SkywalkMarket.x, SkywalkMarket.z);
            c.Label("CANAL SKYWALK", SkywalkCanal.x, SkywalkCanal.z);
            c.Label("NEON MARKET", -222, 10);
            c.Label("KOWLOON STACKS", -150, -205);
            c.Label("FOUNDRY ROW", 222, -205);
            c.Label("ARCOLOGY GATE", 222, 10);
            c.Label("CANAL WARD", -150, 280);
            c.Label("THE CANAL", 222, 194);
        }

        /// <summary>Procedural noodle stand (counter, kitchen wall, awning, stools, lanterns) used until the kit's Ramen_Stall is built.</summary>
        static void NoodleStand(CityContext c, float x, float z)
        {
            var k = c.Kit;
            k.Box(x, CityLayout.Curb + 2.0f, z + 2.6f, 8.4f, 4f, 1.6f, "metal_dark");
            k.Box(x, 2.6f, z + 1.76f, 5f, 1.1f, 0.06f, "emit_panel_warm", collide: false, shadow: false);
            k.Box(x, CityLayout.Curb + 0.55f, z - 1.4f, 7.2f, 1.1f, 0.8f, "wood");
            k.Box(x, CityLayout.Curb + 1.13f, z - 1.4f, 7.5f, 0.06f, 1.0f, "metal_bare", collide: false);
            k.Box(x, 3.5f, z - 0.4f, 9.2f, 0.12f, 4.6f, "tarp", collide: false);
            k.Box(x, 3.42f, z - 2.7f, 9.2f, 0.08f, 0.08f, "emit_strip_warm", collide: false, shadow: false);
            foreach (var px in new[] { -4.4f, 4.4f })
            {
                k.Box(x + px, 1.8f, z - 2.5f, 0.12f, 3.3f, 0.12f, "metal_dark", collide: false);
                k.SolidCollider(x + px, 1.8f, z - 2.5f, 0.2f, 3.3f, 0.2f);
            }
            for (var i = 0; i < 5; i++)
            {
                var sx = x - 3 + i * 1.5f;
                k.Cyl(sx, CityLayout.Curb + 0.38f, z - 2.4f, 0.22f, 0.18f, 0.75f, "metal_dark", 8, collide: false);
                k.Cyl(sx, CityLayout.Curb + 0.78f, z - 2.4f, 0.26f, 0.26f, 0.06f, "rubber", 8, collide: false);
                k.Box(sx, 2.9f, z - 2.2f, 0.28f, 0.36f, 0.28f, "emit_panel_warm", collide: false, shadow: false);
                c.GlowCross(sx, 2.9f, z - 2.2f, 0.9f, i % 2 == 0 ? 0xff5a4au : 0xffc06au, 1.3f);
            }
        }

        /// <summary>The kit's distant skyline towers outside the megawall (not culled: they stand in for the city beyond).</summary>
        void KitSkyline()
        {
            string[] names = { "Skyline_Tower_A", "Skyline_Tower_B", "Skyline_Tower_C" };
            var have = new List<string>();
            foreach (var n in names) if (CityKitAssets.Has(n)) have.Add(n);
            if (have.Count == 0 && !CityKitAssets.Has("Skyline_Twin_D")) return;
            var parent = Child(Root, "KitSkyline").transform;
            var r = new System.Random(Seed + 17);
            void Tower(string name, float x, float z, float yaw, float scale)
            {
                var go = EnvProps.Instantiate(name, parent, false);
                go.transform.SetPositionAndRotation(V(x, 0, z), YawQ(yaw));
                go.transform.localScale = Vector3.one * scale;
            }
            if (CityKitAssets.Has("Skyline_Twin_D")) Tower("Skyline_Twin_D", CityLayout.WallX + 140, CityLayout.AvenueZ, Mathf.PI / 2, 1.2f); // hero vista down the avenue
            if (have.Count == 0) return;
            for (var i = 0; i < 18; i++)
            {
                // Outside the megawall: pick a side, then a spot 50-170 m beyond it.
                var side = i % 4;
                var along = (float)r.NextDouble() * 2 - 1;
                var outD = 50 + (float)r.NextDouble() * 120;
                float x, z;
                if (side == 0) { x = along * 420; z = CityLayout.WallZ0 - outD; }
                else if (side == 1) { x = along * 420; z = CityLayout.WallZ1 + outD; }
                else if (side == 2) { x = -CityLayout.WallX - outD; z = 20 + along * 360; }
                else { x = CityLayout.WallX + outD; z = 20 + along * 360; if (Mathf.Abs(z - CityLayout.AvenueZ) < 60) z += 120; }
                Tower(have[r.Next(have.Count)], x, z, (float)r.NextDouble() * 6.28f, 0.9f + (float)r.NextDouble() * 0.6f);
            }
        }

        // ================================================================== night atmosphere

        static readonly Color BeaconRed = new(1f, 0.16f, 0.12f);

        /// <summary>
        /// Lighting layer of the district (CityFx): soft light cones under every street lamp and spill volumes under shop
        /// signs, low street mist and mist over the canal (tinted by the nearest neon), blinking aircraft beacons on
        /// the tall roofs, steam plumes on the vents, the neon emitter field for rain / steam colour, and streamed
        /// district reflection probes for the wet streets. All merged per 64 m cell and distance-culled.
        /// </summary>
        void NightAtmosphere(CityContext c, bool web)
        {
            var r = new System.Random(Seed + 99);
            float Rnd() => (float)r.NextDouble();
            for (var i = 0; i < c.LampPos.Count; i++) NeonField.Add(c.LampPos[i], c.LampCol[i], 1.6f, 10f);
            if (!dawn)
            {
                CityFx.LampCones(fx, c.LampPos, c.LampCol, CityLayout.Curb);
                var mist = new Color(0.17f, 0.19f, 0.27f);
                for (var i = 0; i < c.LampPos.Count; i++)
                {
                    if (Rnd() > (web ? 0.3f : 0.55f)) continue;
                    var p = c.LampPos[i];
                    CityFx.Mist(fx, new Vector3(p.x + (Rnd() - 0.5f) * 12f, CityLayout.Curb + 1.0f + Rnd() * 0.8f, p.z + (Rnd() - 0.5f) * 12f), 4f + Rnd() * 3f, mist, 0.5f, Rnd());
                }
                var cz = (CityLayout.CanalZ0 + CityLayout.CanalZ1) * 0.5f;
                for (var x = -CityLayout.WallX + 10; x <= CityLayout.WallX - 10; x += web ? 22f : 13f)
                    CityFx.Mist(fx, V(x + (Rnd() - 0.5f) * 6f, CityLayout.CanalWater + 1.1f, cz + (Rnd() - 0.5f) * 5f), 5f + Rnd() * 3f, new Color(0.15f, 0.21f, 0.27f), 0.7f, Rnd());
            }
            // Aircraft-warning beacons on the tall roofs (two diagonal corners blink together).
            foreach (var b in Layout.AllBuildings)
            {
                if (b.Height < 34f || Rnd() > 0.75f) continue;
                var f = b.PodiumHeight > 0 ? b.Tower : b.Foot;
                var ph = Rnd();
                var half = 0.8f + b.Height * 0.006f;
                CityFx.Beacon(fx, V(f.X0 + 0.6f, b.Height + 1.2f, f.Z0 + 0.6f), half, BeaconRed, ph);
                CityFx.Beacon(fx, V(f.X1 - 0.6f, b.Height + 1.2f, f.Z1 - 0.6f), half, BeaconRed, ph);
            }
            var list = new List<Renderer>();
            fx.Finish(Child(Root, "CityFx").transform, "city_fx", CityFx.FxLayer, list);
            Culler.AddRange(list, CityCuller.Geo);
            // Steam plumes on the vents, manholes and the noodle bar (plus the small VfxManager puffs on enter).
            var wind = new Vector3(-2.5f, 0, 1f);
            for (var i = 0; i < steam.Count; i++)
            {
                var go = CityFx.SteamPlume(Root, steam[i], steam[i].y > 0.5f ? 0.7f : 1.15f, Seed + i * 13, wind);
                if (go != null) cells.Put(go, CityCuller.Small);
            }
            CityFx.ProbeGrid(Root, new Rect(-CityLayout.WallX, CityLayout.WallZ0, 2 * CityLayout.WallX, CityLayout.WallZ1 - CityLayout.WallZ0), 4, 4, 5f, 70f, web ? 64 : 128, 1f);
        }

        // ================================================================== facade dressing

        int Dress(CityContext c, Transform signParent, List<Renderer> signs)
        {
            var probeGo = new GameObject("DressProbe");
            probeGo.transform.SetParent(Root, false);
            var probe = new LevelKit(probeGo.transform);
            var used = new GameObject("used");
            used.transform.SetParent(probeGo.transform, false);
            foreach (var job in c.Dress)
            {
                var col = probe.AddBoxCollider(job.Center, job.Size, Quaternion.identity, CombatLayers.World);
                foreach (var f in CityFace.All)
                {
                    if ((job.Faces & f) == 0) continue;
                    var n = CityFace.Normal(f);
                    var focus = job.Center + new Vector3(-n.x, 0, n.y) * 1000f;
                    CyberCity.DressFacades(probe, focus, 3000f, job.Seed + f * 31, job.Density, job.MaxPerFace, CityLayout.Curb, fx);
                }
                col.transform.SetParent(used.transform, false); // out of the probe's WorldBoxes for the next job
            }
            // The graffiti strips were built under the city kit's Fx root: merge them with the signage too.
            CityHarvest.Decals(probe.FxRoot, c.Glow, c.GlowMat);
            CityHarvest.Static(probe.FxRoot, signParent, 64f, signs);
            CityHarvest.Static(Kit.FxRoot, signParent, 64f, signs);
            // Animated leftovers (flickering tubes, holographic adverts) go into culling cells.
            foreach (var r in probe.FxRoot.GetComponentsInChildren<MeshRenderer>(false)) cells.Put(r.gameObject, CityCuller.Geo);
            UnityEngine.Object.Destroy(probeGo);
            return c.Dress.Count;
        }

        // ================================================================== map

        void ApplyMap(ZoneDefinition def, CityContext c)
        {
            if (def == null) return;
            def.MapRects.InsertRange(0, c.Map);
            def.MapLabels.AddRange(c.Labels);
            const float pad = CityLayout.WallT;
            // Prototype bounds (MapBounds convention): x mirrored into map space.
            def.MapMin = new Vector2(-(CityLayout.WallX + pad), CityLayout.WallZ0 - pad);
            def.MapMax = new Vector2(CityLayout.WallX + pad, CityLayout.WallZ1 + pad);
        }

        // ================================================================== runtime hooks

        /// <summary>After the zone is loaded: the district's interactables (points of interest, drivable parked cars).</summary>
        public void OnLoaded(ZoneRuntime rt)
        {
            if (rt == null) return;
            VehicleDamage.Register(Root); // every car can be wrecked and blown up
            Driving.Register(rt, Root);   // the parked cars can be driven
            rt.AddInteractable(new ZoneInteractable { Id = "i_city_noodles", Kind = "inspect", Position = V(NoodleBar.x, 1.2f, NoodleBar.z - 2.8f), Radius = 2.6f, Report = false },
                () => true, () => "Order a bowl of noodles", () =>
                {
                    G.Manager?.Player?.RestoreShield();
                    G.Audio?.Play("item", null);
                    G.Presentation?.Toast("Hot broth, synthetic pork, real chili. The cook doesn't ask about the plaza. (Shield restored)", ToastKind.Info);
                });
            rt.AddInteractable(new ZoneInteractable { Id = "i_city_graffiti", Kind = "inspect", Position = V(Graffiti.x, 1.4f, -43.2f), Radius = 2.6f, Report = false },
                () => true, () => "Study the glowing graffiti", () =>
                    G.Presentation?.Toast(rt.EchoActive
                        ? "Under Echo Sight the paint hums like the monument core. Whoever drew this heard the Deep too."
                        : "The monument's broken-ring sigil, drawn in paint that glows like Aether. \"THE AETHER LISTENS.\"", ToastKind.Info));
            rt.AddInteractable(new ZoneInteractable { Id = "i_city_view_market", Kind = "inspect", Position = V(SkywalkMarket.x, SkywalkMarket.y + 1.2f, SkywalkMarket.z), Radius = 3f, Report = false },
                () => true, () => "Take in the view", () =>
                    G.Presentation?.Toast("Neon Market below, Kowloon Stacks to the north, and down the avenue the Arcology Gate, sealed since the night the Aether went dark.", ToastKind.Info));
            rt.AddInteractable(new ZoneInteractable { Id = "i_city_view_canal", Kind = "inspect", Position = V(SkywalkCanal.x, SkywalkCanal.y + 1.2f, SkywalkCanal.z), Radius = 3f, Report = false },
                () => true, () => "Take in the view", () =>
                    G.Presentation?.Toast("The Canal Ward hums under its lanterns. Past the megawall, the towers of the arcology never go dark.", ToastKind.Info));
        }

        /// <summary>When the zone is entered: persistent steam vents (re-created after a reload, as the plaza's emitters).</summary>
        public void OnEnter()
        {
            var vfx = VfxManager.Instance;
            if (vfx == null) return;
            foreach (var e in emitters) if (e != null) UnityEngine.Object.Destroy(e);
            emitters.Clear();
            foreach (var p in steam)
            {
                var go = vfx.Emitter(p, "steam", 1.4f, 0.4f);
                if (go == null) continue;
                cells.Put(go, CityCuller.Small);
                emitters.Add(go);
            }
            var motes = vfx.Emitter(V(Graffiti.x, 0.5f, -42.6f), "aether", 2.5f, 1.4f);
            if (motes != null) { cells.Put(motes, CityCuller.Small); emitters.Add(motes); }
        }
    }
}
