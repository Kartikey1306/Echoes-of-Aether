using System.Collections.Generic;
using UnityEngine;

namespace EOA
{
    /// <summary>Named districts of the open city around the plaza (map labels, building profiles).</summary>
    public enum CityDistrict { NeonMarket, KowloonStacks, ArcologyGate, CanalWard, FoundryRow }

    /// <summary>Axis-aligned rectangle in prototype XZ (metres).</summary>
    public struct PRect
    {
        public float X0, Z0, X1, Z1;

        public PRect(float x0, float z0, float x1, float z1)
        {
            X0 = Mathf.Min(x0, x1); X1 = Mathf.Max(x0, x1);
            Z0 = Mathf.Min(z0, z1); Z1 = Mathf.Max(z0, z1);
        }

        public float W => X1 - X0;
        public float D => Z1 - Z0;
        public float CX => (X0 + X1) * 0.5f;
        public float CZ => (Z0 + Z1) * 0.5f;
        public bool Overlaps(PRect o, float margin = 0) => X0 < o.X1 - margin && X1 > o.X0 + margin && Z0 < o.Z1 - margin && Z1 > o.Z0 + margin;
        public bool Contains(float x, float z) => x >= X0 && x <= X1 && z >= Z0 && z <= Z1;
        public PRect Inset(float a) => new(X0 + a, Z0 + a, X1 - a, Z1 - a);
    }

    /// <summary>Building faces in prototype space: W = -x, E = +x, N = -z, S = +z (PlazaZone's 'w', 'e', 'n', 's').</summary>
    public static class CityFace
    {
        public const byte W = 1, E = 2, N = 4, S = 8;
        public static readonly byte[] All = { W, E, N, S };

        /// <summary>Outward normal of a face (prototype XZ).</summary>
        public static Vector2 Normal(byte f) => f switch { W => new Vector2(-1, 0), E => new Vector2(1, 0), N => new Vector2(0, -1), _ => new Vector2(0, 1) };

        /// <summary>
        /// Face line of a footprint: the face runs from a0 to a1 along X (N/S faces) or Z (W/E faces) at the fixed
        /// coordinate `line`; n is the outward normal.
        /// </summary>
        public static void Line(PRect r, byte f, out float a0, out float a1, out float line, out Vector2 n, out bool alongX)
        {
            n = Normal(f);
            alongX = f == N || f == S;
            if (alongX) { a0 = r.X0; a1 = r.X1; line = f == N ? r.Z0 : r.Z1; }
            else { a0 = r.Z0; a1 = r.Z1; line = f == W ? r.X0 : r.X1; }
        }
    }

    /// <summary>One building on a lot (prototype space). Emitted by an <see cref="ICityBuildings"/>.</summary>
    public sealed class CityBuilding
    {
        public PRect Foot;
        /// <summary>Tower footprint above the podium (== Foot when PodiumHeight is 0).</summary>
        public PRect Tower;
        public float Height, PodiumHeight;
        public int Floors, Seed, Skin;
        public string Material;
        /// <summary>Faces on a street / canal quay, and faces on an alley or open lot (CityFace bits).</summary>
        public byte Street, Alley;
        public CityDistrict District;
        public bool Landmark;
        /// <summary>Lot sized for a complete kit building (<see cref="CityLayout.KitModels"/> index, -1 none); UseKit when it got the budget.</summary>
        public int Kit = -1;
        public bool UseKit;
        /// <summary>Detailed module asset (Building_Block_*) used instead of a procedural mass; null for boxes.</summary>
        public string Asset;
        public float AssetX, AssetZ, AssetYaw, AssetW, AssetD;
        /// <summary>
        /// One-off landmark model (CityLandmarks kit, <see cref="CityLayout.LandmarkSites"/>) on this lot, placed at
        /// AssetX/AssetZ/AssetYaw; null for ordinary lots. When its prefab is missing the lot is built procedurally from
        /// Height / Floors / PodiumHeight (the fallback values set by the layout).
        /// </summary>
        public string LandmarkAsset;
    }

    /// <summary>City block between four roads (prototype space).</summary>
    public sealed class CityBlock
    {
        public int Index;
        /// <summary>Road centrelines around the block.</summary>
        public float X1, X2, Z1, Z2;
        /// <summary>Sidewalk slab (between the road edges) and building zone (inside the sidewalks).</summary>
        public PRect Slab, Zone;
        public CityDistrict District;
        public bool Canal;
        public readonly List<CityBuilding> Buildings = new();
        /// <summary>Lots kept open (pocket plazas, overpass landings, points of interest).</summary>
        public readonly List<PRect> Open = new();
        public readonly List<PRect> Alleys = new();
    }

    /// <summary>
    /// Seeded street grid and building lots of the open district around the plaza (prototype design space, metres).
    /// The plaza is the "reserve" in the middle of the grid; the four roads around it form its ring. Pure data: the
    /// geometry is emitted by <see cref="CityStreets"/> and the building factory.
    ///
    ///   x-lines (roads along z): ±348 (perimeter), ±264, ±180, ±96 (reserve ring) and 0 (outside the reserve only)
    ///   z-lines (roads along x): -280 (perimeter), -196, -112 (reserve ring), -26 and 59 (|x| ≥ 96 only), 152
    ///                            (reserve ring), 236, 320 (perimeter)
    ///   Roads are 16 m (one travel lane and one parking lane per direction), sidewalks 4.5 m; the megawall stands
    ///   just outside the perimeter sidewalks (|x| = 360.5, z = -292.5 / 332.5); a canal crosses the 152..236 row.
    /// </summary>
    public sealed class CityLayout
    {
        public static readonly float[] XL = { -348, -264, -180, -96, 0, 96, 180, 264, 348 };
        public static readonly float[] ZL = { -280, -196, -112, -26, 59, 152, 236, 320 };

        public const float RoadHalf = 8f, Walk = 4.5f, Curb = 0.15f;
        /// <summary>Distance from a road centreline to the sidewalk centreline (pedestrian ring).</summary>
        public const float Ring = RoadHalf + Walk * 0.5f;
        /// <summary>Stop line distance from an intersection centre.</summary>
        public const float Stop = 13f;
        public const float FloorH = 3.4f, GroundH = 4.4f;
        public const float ResX = 96f, ResZ0 = -112f, ResZ1 = 152f;
        /// <summary>Plaza reserve inside its ring sidewalks.</summary>
        public static readonly PRect ReserveInner = new(-ResX + RoadHalf + Walk, ResZ0 + RoadHalf + Walk, ResX - RoadHalf - Walk, ResZ1 - RoadHalf - Walk);
        public const float AvenueZ = 59f;
        public const float CanalZ0 = 188f, CanalZ1 = 200f, CanalRow0 = 152f, CanalRow1 = 236f, Quay = 3.5f, CanalWater = -2.4f;
        public const float WallX = 360.5f, WallZ0 = -292.5f, WallZ1 = 332.5f, WallT = 10f;

        public readonly List<CityBlock> Blocks = new();
        /// <summary>Lots that must stay open (pocket plazas etc.), registered before <see cref="Generate"/>.</summary>
        public readonly List<PRect> Reserved = new();
        public readonly List<CityBuilding> AllBuildings = new();

        public static bool IsPartialZ(float z) => z == -26f || z == AvenueZ;

        /// <summary>
        /// Complete buildings of the environment kit (mass footprint along the street x depth, roof height). Lots for
        /// them are the mass width plus <see cref="KitMargin"/> on each side, for the facades' side projections.
        /// </summary>
        public static readonly (string name, float w, float d, float roof)[] KitModels =
        {
            ("Building_MidRise_A", 12, 12, 17f), ("Building_MidRise_B", 20, 12, 23.8f), ("Building_MidRise_C", 16, 12, 13.6f), ("Building_HighRise_D", 16, 16, 40.8f),
            // District buildings of the CityLandmarks kit (<= 8 materials each, see Art/CityLandmarks/LANDMARKS.md), indices 4..16.
            ("LB_NM_Shophouse_A", 12, 12, 21.4f), ("LB_NM_Shophouse_B", 16, 12, 24.8f), ("LB_NM_Arcade_C", 20, 14, 14.6f),
            ("LB_KS_Tenement_A", 12, 12, 42.4f), ("LB_KS_Tenement_B", 16, 12, 52f), ("LB_KS_Slab_C", 20, 12, 36f),
            ("LB_AG_Office_A", 20, 16, 45f), ("LB_AG_Office_B", 16, 16, 66.6f),
            ("LB_CW_House_A", 12, 12, 21.2f), ("LB_CW_House_B", 16, 12, 24.6f), ("LB_CW_Warehouse_C", 20, 14, 16.2f),
            ("LB_FR_Shed_A", 20, 14, 10.2f), ("LB_FR_Works_B", 16, 16, 18.6f),
        };

        /// <summary>True for the light (atlas-material) district buildings of the CityLandmarks kit.</summary>
        public static bool IsLandmarkKit(int kit) => kit >= 4 && kit < KitModels.Length;

        /// <summary>
        /// One-off landmarks (CityLandmarks kit), 2-3 per district. rect = lot in prototype space (the model's bounds are
        /// centred in it), face = street face the model's front looks at. fallback = procedural height when the prefab
        /// is missing (0 = podium megatower on the lot). A lot that fills its block zone replaces the whole block.
        /// </summary>
        public static readonly (string name, PRect rect, byte face, float fallback)[] LandmarkSites =
        {
            // Neon Market
            ("LM_NM_JadeLanternTower", new PRect(-224f, 15.5f, -192.5f, 46.5f), CityFace.S, 60f),
            ("LM_NM_SignCanyon", new PRect(-160f, -65.5f, -115.5f, -38.5f), CityFace.S, 26f),
            ("LM_NM_NightMarketHall", new PRect(-246f, 71.5f, -199f, 106f), CityFace.N, 18f),
            // Kowloon Stacks
            ("LM_KS_TheStack", new PRect(-71f, -160.5f, -25f, -125f), CityFace.S, 62f),
            ("LM_KS_BridgeTwins", new PRect(-243f, -147.5f, -201f, -125f), CityFace.S, 66f),
            ("LM_KS_SignalSpire", new PRect(-133f, -149f, -109f, -125f), CityFace.S, 44f),
            // Arcology Gate (the two former megatower blocks + the exchange)
            ("LM_AG_HelixArcology", new PRect(192.5f, -13.5f, 251.5f, 46.5f), CityFace.S, 0f),
            ("LM_AG_MeridianSpire", new PRect(283f, 72f, 329f, 118f), CityFace.N, 0f),
            ("LM_AG_ExchangeAtrium", new PRect(108.5f, -95f, 150f, -43.5f), CityFace.W, 22f),
            // Canal Ward
            ("LM_CW_WaterfrontRow", new PRect(-166f, 164.5f, -120f, 184.5f), CityFace.S, 28f),
            ("LM_CW_ClockPumpHouse", new PRect(29f, 248.5f, 66f, 275f), CityFace.N, 14f),
            ("LM_CW_StiltTower", new PRect(-237f, 164.5f, -219f, 184.5f), CityFace.S, 50f),
            // Foundry Row
            ("LM_FR_EmberRefinery", new PRect(192.5f, -267.5f, 251.5f, -208.5f), CityFace.S, 14f),
            ("LM_FR_CoolingTower", new PRect(276.5f, -183.5f, 335.5f, -124.5f), CityFace.W, 14f),
            ("LM_FR_SawtoothWorks", new PRect(111f, -167f, 166f, -125f), CityFace.S, 12f),
        };
        public const float KitMargin = 0.8f;

        /// <summary>Road along z at x between the z-lines za &lt; zb exists.</summary>
        public static bool XSeg(float x, float za, float zb) => x != 0f || zb <= ResZ0 || za >= ResZ1;

        /// <summary>Road along x at z between the x-lines xa &lt; xb exists.</summary>
        public static bool ZSeg(float z, float xa, float xb) => !IsPartialZ(z) || xa >= ResX || xb <= -ResX;

        public static bool NodeExists(float x, float z)
        {
            int i = System.Array.IndexOf(XL, x), j = System.Array.IndexOf(ZL, z);
            if (i < 0 || j < 0) return false;
            if (j > 0 && XSeg(x, ZL[j - 1], z)) return true;
            if (j < ZL.Length - 1 && XSeg(x, z, ZL[j + 1])) return true;
            if (i > 0 && ZSeg(z, XL[i - 1], x)) return true;
            if (i < XL.Length - 1 && ZSeg(z, x, XL[i + 1])) return true;
            return false;
        }

        public static bool InReserveCell(float x1, float x2, float z1, float z2) => x1 >= -ResX && x2 <= ResX && z1 >= ResZ0 && z2 <= ResZ1;

        public static CityDistrict DistrictAt(float x, float z)
        {
            if (z >= ResZ1) return CityDistrict.CanalWard;
            if (z < ResZ0) return x > ResX ? CityDistrict.FoundryRow : CityDistrict.KowloonStacks;
            return x < 0 ? CityDistrict.NeonMarket : CityDistrict.ArcologyGate;
        }

        public static string DistrictName(CityDistrict d) => d switch
        {
            CityDistrict.NeonMarket => "NEON MARKET",
            CityDistrict.KowloonStacks => "KOWLOON STACKS",
            CityDistrict.ArcologyGate => "ARCOLOGY GATE",
            CityDistrict.CanalWard => "CANAL WARD",
            _ => "FOUNDRY ROW",
        };

        // ------------------------------------------------------------------ profiles

        sealed class Profile
        {
            public int FloorMin, FloorMax;
            public float LotMin, LotMax, AlleyChance, CrossAlley, TowerChance, ModuleChance, KitChance;
            public int[] Kits = { 0, 1, 2 };
            public string[] Mats;
            public int[] Skins;
        }

        static readonly Profile[] Profiles =
        {
            // NeonMarket: dense low/mid rise, many small shops; market shophouses / arcades of the landmark kit.
            new() { FloorMin = 4, FloorMax = 9, LotMin = 11, LotMax = 19, AlleyChance = 0.6f, CrossAlley = 0.3f, TowerChance = 0.2f, ModuleChance = 0.12f,
                    Mats = new[] { "lm_plaster_pastel", "plaster", "lm_mosaic_tile", "concrete_dark" }, Skins = new[] { 0, 3, 0 }, KitChance = 0.75f,
                    Kits = new[] { 4, 5, 6, 4, 5, 0, 2 } },
            // KowloonStacks: narrow, tall, stacked tenements.
            new() { FloorMin = 8, FloorMax = 20, LotMin = 9, LotMax = 15, AlleyChance = 0.65f, CrossAlley = 0.35f, TowerChance = 0.1f, ModuleChance = 0.08f,
                    Mats = new[] { "lm_mosaic_tile", "lm_concrete_weathered", "concrete_dark", "corrugated" }, Skins = new[] { 0, 1, 2, 3 }, KitChance = 0.65f,
                    Kits = new[] { 7, 8, 9, 7, 8, 3 } },
            // ArcologyGate: corporate podium towers.
            new() { FloorMin = 12, FloorMax = 20, LotMin = 24, LotMax = 40, AlleyChance = 0.35f, CrossAlley = 0.1f, TowerChance = 0.75f, ModuleChance = 0f,
                    Mats = new[] { "lm_cladding_dark", "metal_plate", "concrete_dark", "glass_dark" }, Skins = new[] { 1, 1, 3 }, KitChance = 0.4f,
                    Kits = new[] { 10, 11, 10, 3 } },
            // CanalWard: mid rise brick and plaster.
            new() { FloorMin = 5, FloorMax = 12, LotMin = 13, LotMax = 22, AlleyChance = 0.5f, CrossAlley = 0.2f, TowerChance = 0.25f, ModuleChance = 0.12f,
                    Mats = new[] { "lm_brick_soot", "lm_plaster_pastel", "brick", "concrete" }, Skins = new[] { 0, 2 }, KitChance = 0.7f,
                    Kits = new[] { 12, 13, 14, 12, 13, 2, 0 } },
            // FoundryRow: industrial sheds and works.
            new() { FloorMin = 4, FloorMax = 8, LotMin = 18, LotMax = 30, AlleyChance = 0.5f, CrossAlley = 0.15f, TowerChance = 0f, ModuleChance = 0.1f,
                    Mats = new[] { "lm_corrugated_painted", "concrete_dark", "metal_rusted", "lm_brick_soot" }, Skins = new[] { 2 }, KitChance = 0.45f,
                    Kits = new[] { 15, 16, 15, 16 } },
        };

        /// <summary>Detailed background modules from the environment kit: name, width, depth, height.</summary>
        static readonly (string name, float w, float d, float h)[] Modules =
        {
            ("Building_Block_A", 12.3f, 12.3f, 18.73f), ("Building_Block_B", 20.3f, 14.3f, 25.38f),
            ("Building_Block_C", 10.3f, 16.3f, 32.69f), ("Building_Block_D", 24.3f, 22.3f, 15.19f),
        };

        static float Range(System.Random r, float a, float b) => a + (float)r.NextDouble() * (b - a);

        // ------------------------------------------------------------------ generation

        public void Generate(int seed)
        {
            var r = new System.Random(seed);
            Blocks.Clear();
            AllBuildings.Clear();
            for (var i = 0; i < XL.Length - 1; i++)
            for (var j = 0; j < ZL.Length - 1; j++)
            {
                float x1 = XL[i], x2 = XL[i + 1], z1 = ZL[j], z2 = ZL[j + 1];
                if (InReserveCell(x1, x2, z1, z2)) continue;
                var b = new CityBlock
                {
                    Index = Blocks.Count, X1 = x1, X2 = x2, Z1 = z1, Z2 = z2,
                    Slab = new PRect(x1 + RoadHalf, z1 + RoadHalf, x2 - RoadHalf, z2 - RoadHalf),
                    Zone = new PRect(x1 + RoadHalf + Walk, z1 + RoadHalf + Walk, x2 - RoadHalf - Walk, z2 - RoadHalf - Walk),
                    District = DistrictAt((x1 + x2) / 2, (z1 + z2) / 2),
                    Canal = z1 == CanalRow0 && z2 == CanalRow1,
                };
                foreach (var o in Reserved)
                    if (o.Overlaps(b.Zone))
                        b.Open.Add(new PRect(Mathf.Max(o.X0, b.Zone.X0), Mathf.Max(o.Z0, b.Zone.Z0), Mathf.Min(o.X1, b.Zone.X1), Mathf.Min(o.Z1, b.Zone.Z1)));
                Blocks.Add(b);
                BuildBlock(b, r);
                AllBuildings.AddRange(b.Buildings);
            }
        }

        static bool IsLandmarkBlock(CityBlock b) =>
            (b.X1 == 180 && b.Z1 == -26) || (b.X1 == 264 && b.Z1 == AvenueZ);

        /// <summary>Landmark sites whose lot centre lies in this block's building zone.</summary>
        static List<int> SitesIn(CityBlock b)
        {
            var list = new List<int>();
            for (var i = 0; i < LandmarkSites.Length; i++)
                if (b.Zone.Contains(LandmarkSites[i].rect.CX, LandmarkSites[i].rect.CZ)) list.Add(i);
            return list;
        }

        /// <summary>Landmark lot: the model is centred in the site rect facing the site's street face; the procedural
        /// fallback (prefab missing) is a mass of the site's fallback height or, for 0, the old podium megatower.</summary>
        static CityBuilding LandmarkLot(CityBlock b, int site, Profile p, System.Random r)
        {
            var s = LandmarkSites[site];
            var lot = new PRect(Mathf.Max(s.rect.X0, b.Zone.X0), Mathf.Max(s.rect.Z0, b.Zone.Z0), Mathf.Min(s.rect.X1, b.Zone.X1), Mathf.Min(s.rect.Z1, b.Zone.Z1));
            var t = new CityBuilding
            {
                Foot = lot, Tower = lot, District = b.District, Landmark = true, LandmarkAsset = s.name, Seed = r.Next(),
                Material = p.Mats[0], Skin = p.Skins[0], AssetX = lot.CX, AssetZ = lot.CZ, AssetYaw = CityKitAssets.FaceYaw(s.face),
            };
            if (s.fallback <= 0)
            {
                // Arcology megatower: podium over the lot, 30 m tower rising 170-190 m.
                t.Tower = new PRect(lot.CX - 15, lot.CZ - 15, lot.CX + 15, lot.CZ + 15);
                t.Material = "concrete_dark";
                t.Skin = 1;
                t.Floors = 48 + r.Next(9);
                t.PodiumHeight = GroundH + 3 * FloorH;
            }
            else t.Floors = Mathf.Max(2, Mathf.RoundToInt((s.fallback - GroundH) / FloorH) + 1);
            t.Height = GroundH + (t.Floors - 1) * FloorH;
            return t;
        }

        void BuildBlock(CityBlock b, System.Random r)
        {
            var p = Profiles[(int)b.District];
            var z = b.Zone;
            var sites = SitesIn(b);
            var landmarks = new List<CityBuilding>();
            var full = false;
            foreach (var i in sites)
            {
                var lm = LandmarkLot(b, i, p, r);
                landmarks.Add(lm);
                // A lot covering (almost) the whole zone replaces the block; otherwise the rows flow around it.
                if (lm.Foot.W * lm.Foot.D > 0.8f * z.W * z.D) full = true;
                else b.Open.Add(new PRect(lm.Foot.X0 - 1.5f, lm.Foot.Z0 - 1.5f, lm.Foot.X1 + 1.5f, lm.Foot.Z1 + 1.5f));
            }
            if (sites.Count == 0 && IsLandmarkBlock(b) && b.Open.Count == 0)
            {
                // (no site registered for a former landmark block) arcology megatower fallback
                var t = new CityBuilding
                {
                    Foot = z, Tower = new PRect(z.CX - 15, z.CZ - 15, z.CX + 15, z.CZ + 15), District = b.District, Landmark = true,
                    Seed = r.Next(), Material = "concrete_dark", Skin = 1, Floors = 48 + r.Next(9),
                };
                t.PodiumHeight = GroundH + 3 * FloorH;
                t.Height = GroundH + (t.Floors - 1) * FloorH;
                b.Buildings.Add(t);
                Faces(b);
                return;
            }
            if (full)
            {
                b.Buildings.AddRange(landmarks);
                Faces(b);
                return;
            }
            if (b.Canal)
            {
                Row(b, new PRect(z.X0, z.Z0, z.X1, CanalZ0 - Quay), p, r);
                Row(b, new PRect(z.X0, CanalZ1 + Quay, z.X1, z.Z1), p, r);
            }
            else if (z.D < 34)
            {
                Row(b, z, p, r);
            }
            else
            {
                var alley = r.NextDouble() < p.AlleyChance;
                var mid = z.CZ + Range(r, -4, 4);
                var half = alley ? 3f : 0f;
                Row(b, new PRect(z.X0, z.Z0, z.X1, mid - half), p, r);
                Row(b, new PRect(z.X0, mid + half, z.X1, z.Z1), p, r);
                if (alley) b.Alleys.Add(new PRect(z.X0, mid - half, z.X1, mid + half));
            }
            // Alleys never run through a landmark lot: clip the long ones, drop cross alleys.
            foreach (var lm in landmarks) ClipAlleys(b, lm.Foot);
            b.Buildings.AddRange(landmarks);
            Faces(b);
            foreach (var bd in b.Buildings) if (bd.LandmarkAsset == null) Finalise(b, bd, p, r);
        }

        static void ClipAlleys(CityBlock b, PRect lot)
        {
            var keep = new List<PRect>();
            foreach (var a in b.Alleys)
            {
                if (!a.Overlaps(lot, 0.05f)) { keep.Add(a); continue; }
                if (a.W <= a.D) continue;
                if (lot.X0 - 1.5f - a.X0 > 6f) keep.Add(new PRect(a.X0, a.Z0, lot.X0 - 1.5f, a.Z1));
                if (a.X1 - lot.X1 - 1.5f > 6f) keep.Add(new PRect(lot.X1 + 1.5f, a.Z0, a.X1, a.Z1));
            }
            b.Alleys.Clear();
            b.Alleys.AddRange(keep);
        }

        static bool OpenOverlapsRow(CityBlock b, PRect row, float x0, float x1)
        {
            foreach (var o in b.Open) if (o.Z0 < row.Z1 && o.Z1 > row.Z0 && o.X0 < x1 && o.X1 > x0) return true;
            return false;
        }

        void Row(CityBlock b, PRect row, Profile p, System.Random r)
        {
            var x = row.X0;
            var guard = 0;
            while (x < row.X1 - 1f && guard++ < 64)
            {
                var jumped = false;
                foreach (var o in b.Open)
                    if (o.Z0 < row.Z1 && o.Z1 > row.Z0 && x >= o.X0 - 0.5f && x < o.X1) { x = o.X1; jumped = true; }
                if (jumped) continue;
                var kit = -1;
                var end = Mathf.Min(row.X1, x + Range(r, p.LotMin, p.LotMax));
                if (r.NextDouble() < p.KitChance)
                {
                    // Lot sized for a complete kit building (falls back to a box building of the same lot).
                    var k = p.Kits[r.Next(p.Kits.Length)];
                    var m = KitModels[k];
                    var lot = m.w + 2 * KitMargin;
                    if (row.D >= m.d + 0.5f && x + lot <= row.X1 + 0.01f && !OpenOverlapsRow(b, row, x, x + lot)) { kit = k; end = x + lot; }
                }
                foreach (var o in b.Open)
                    if (o.Z0 < row.Z1 && o.Z1 > row.Z0 && o.X0 > x && o.X0 < end) { end = o.X0; kit = -1; }
                if (kit < 0 && row.X1 - end < p.LotMin * 0.7f && !OpenOverlapsRow(b, row, end, row.X1)) end = row.X1;
                if (end - x >= 6f)
                    b.Buildings.Add(new CityBuilding
                    {
                        Foot = new PRect(x, row.Z0, end, row.Z1), District = b.District, Seed = r.Next(),
                        Material = p.Mats[r.Next(p.Mats.Length)], Skin = p.Skins[r.Next(p.Skins.Length)],
                        Floors = r.Next(p.FloorMin, p.FloorMax + 1), Kit = kit,
                    });
                x = end;
                if (x < row.X1 - p.LotMin && r.NextDouble() < p.CrossAlley)
                {
                    b.Alleys.Add(new PRect(x, row.Z0, x + 4.5f, row.Z1));
                    x += 4.5f;
                }
            }
        }

        /// <summary>Classify each face of each building: street (sidewalk or canal quay), alley/open lot, or party wall.</summary>
        static void Faces(CityBlock b)
        {
            foreach (var bd in b.Buildings)
            {
                bd.Street = 0; bd.Alley = 0;
                foreach (var f in CityFace.All)
                {
                    CityFace.Line(bd.Foot, f, out var a0, out var a1, out var line, out var n, out var alongX);
                    var s = (a0 + a1) * 0.5f;
                    var qx = alongX ? s : line + n.x * 1.2f;
                    var qz = alongX ? line + n.y * 1.2f : s;
                    if (!b.Zone.Contains(qx, qz) || (b.Canal && qz > CanalZ0 - Quay - 0.01f && qz < CanalZ1 + Quay + 0.01f)) bd.Street |= f;
                    else
                    {
                        var blocked = false;
                        foreach (var o in b.Buildings) if (o != bd && o.Foot.Contains(qx, qz)) { blocked = true; break; }
                        if (!blocked) bd.Alley |= f;
                    }
                }
            }
        }

        static int Bits(byte v) { var c = 0; for (; v != 0; v &= (byte)(v - 1)) c++; return c; }

        static void Finalise(CityBlock b, CityBuilding bd, Profile p, System.Random r)
        {
            // Kit lots must front a street (or the canal quay) on their long N/S side.
            if (bd.Kit >= 0 && (bd.Street & (CityFace.N | CityFace.S)) == 0) bd.Kit = -1;
            if (bd.Kit >= 0)
            {
                var m = KitModels[bd.Kit];
                bd.Height = m.roof;
                bd.Floors = Mathf.RoundToInt(m.roof / FloorH);
                bd.Tower = bd.Foot;
                return;
            }
            if (Bits(bd.Street) >= 2) bd.Floors = Mathf.Min(20, bd.Floors + 1 + r.Next(3)); // corner buildings stand taller
            bd.Height = GroundH + (bd.Floors - 1) * FloorH;
            bd.Tower = bd.Foot;
            var f = bd.Foot;
            if (bd.Floors >= 13 && f.W >= 22 && f.D >= 20 && r.NextDouble() < p.TowerChance)
            {
                bd.PodiumHeight = GroundH + 2 * FloorH;
                bd.Tower = f.Inset(3f + (float)r.NextDouble() * 2.5f);
            }
            else if (bd.Street != 0 && r.NextDouble() < p.ModuleChance) TryModule(bd, r);
        }

        /// <summary>Use a detailed environment building module when one fits the lot (front toward a street).</summary>
        static void TryModule(CityBuilding bd, System.Random r)
        {
            var f = bd.Foot;
            byte face = 0;
            foreach (var c in CityFace.All) if ((bd.Street & c) != 0) { face = c; break; }
            var start = r.Next(Modules.Length);
            for (var k = 0; k < Modules.Length; k++)
            {
                var m = Modules[(start + k) % Modules.Length];
                var side = face == CityFace.W || face == CityFace.E;
                float mw = side ? m.d : m.w, md = side ? m.w : m.d;
                if (f.W < mw || f.D < md || f.W - mw > 6f || f.D - md > 8f) continue;
                bd.Asset = m.name;
                bd.AssetW = mw; bd.AssetD = md;
                bd.Height = m.h;
                // Front aligned with the street face; asset front is +Z (prototype yaw 0 faces +z).
                switch (face)
                {
                    case CityFace.S: bd.AssetX = f.CX; bd.AssetZ = f.Z1 - md / 2; bd.AssetYaw = 0; break;
                    case CityFace.N: bd.AssetX = f.CX; bd.AssetZ = f.Z0 + md / 2; bd.AssetYaw = Mathf.PI; break;
                    case CityFace.E: bd.AssetX = f.X1 - mw / 2; bd.AssetZ = f.CZ; bd.AssetYaw = Mathf.PI / 2; break;
                    default: bd.AssetX = f.X0 + mw / 2; bd.AssetZ = f.CZ; bd.AssetYaw = -Mathf.PI / 2; break;
                }
                return;
            }
        }
    }
}
