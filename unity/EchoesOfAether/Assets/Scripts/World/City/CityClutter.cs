using System.Collections.Generic;
using UnityEngine;
using static EOA.ProtoSpace;

namespace EOA
{
    /// <summary>
    /// Street-kit life on the pavements and over the roads of the open city (prototype coordinates):
    ///   * kerb clutter per block face: LED bollards and tactile strips at the crossings, yatai food carts with steam,
    ///     charging totems, data booths, tram shelters, garbage-bag piles, water barriers; vending machines and
    ///     capsule-toy banks in front of the storefront service bays (<see cref="CityStorefronts"/>);
    ///   * overhead cable bundles strung across the streets between facing buildings, some with paper lanterns
    ///     (merged into the city's static geometry);
    ///   * street decals: asphalt patches, skids, oil, cracks, manholes and puddles on the roads; stains, cracks,
    ///     litter and tactile paving on the pavements.
    /// Everything is seeded from the city RNG, keeps the pedestrian lanes clear (crowd obstacles registered) and is
    /// skipped when the street kit has not been built.
    /// </summary>
    public static class CityClutter
    {
        const float Y = CityLayout.Curb;
        const float H = CityLayout.RoadHalf;
        static readonly List<Vector3> occupied = new();   // prototype x, z, radius
        static int vendBudget, shelterBudget, bollardBudget, cartBudget;
        public static int Props, CableCount, Lanterns, Decals;
        static CityContext ctx;

        static void Begin(CityContext c)
        {
            if (ctx == c) return;
            ctx = c;
            occupied.Clear();
            var web = Application.platform == RuntimePlatform.WebGLPlayer;
            vendBudget = web ? 12 : 40;
            shelterBudget = web ? 4 : 12;
            bollardBudget = web ? 60 : 220;
            cartBudget = web ? 6 : 18;
            Props = CableCount = Lanterns = Decals = 0;
            foreach (var lp in c.LampPos) occupied.Add(new Vector3(-lp.x, lp.z, 0.6f));
            decalBudget = web ? 300 : 800;
        }

        static bool Free(float x, float z, float r)
        {
            foreach (var o in occupied)
            {
                var dx = o.x - x; var dz = o.y - z;
                if (dx * dx + dz * dz < (r + o.z) * (r + o.z)) return false;
            }
            return true;
        }

        static GameObject Put(CityContext c, string name, float x, float y, float z, float yaw, float radius, bool obstacle = true, int group = CityCuller.Small)
        {
            if (!CityKitAssets.Has(name) || !Free(x, z, radius)) return null;
            var go = c.Prop(name, x, y, z, yaw, group);
            occupied.Add(new Vector3(x, z, radius));
            if (obstacle) c.Obstacle(x, z, radius + 0.25f);
            c.KitPieces++;
            Props++;
            return go;
        }

        // ------------------------------------------------------------------ pavement clutter

        /// <summary>Kerb-side and wall-side clutter for one block (after its storefronts).</summary>
        public static void Block(CityContext c, CityBlock b)
        {
            Begin(c);
            if (!CityKitAssets.Has("St_Bollard_LED")) return;
            var d = b.District;
            var dense = d == CityDistrict.NeonMarket || d == CityDistrict.KowloonStacks || d == CityDistrict.CanalWard;
            foreach (var face in CityFace.All)
            {
                CityFace.Line(b.Slab, face, out var a0, out var a1, out var kerb, out var n, out var alongX);
                var len = a1 - a0;
                float PX(float s, float dk) => alongX ? s : kerb - n.x * dk;
                float PZ(float s, float dk) => alongX ? kerb - n.y * dk : s;
                var toRoad = Mathf.Atan2(n.x, n.y);
                var toWall = Mathf.Atan2(-n.x, -n.y);
                // crossings at both ends: tactile paving + a pair of LED bollards
                foreach (var end in new[] { a0 + 2.3f, a1 - 2.3f })
                {
                    Decal(c, "St_Tactile_Strip", PX(end, 0.55f), Y, PZ(end, 0.55f), Vector3.up, alongX ? 0f : 90f, 1f);
                    if (bollardBudget > 1 && c.Chance(0.45f))
                    {
                        var side = end < (a0 + a1) / 2 ? 1f : -1f;
                        foreach (var off in new[] { 1.6f, 2.8f })
                            if (Put(c, "St_Bollard_LED", PX(end + side * off, 0.4f), Y, PZ(end + side * off, 0.4f), 0, 0.2f) != null) bollardBudget--;
                    }
                }
                // food cart (steam), charging totem, data booth, tram shelter, bags, barriers along the kerb
                if (dense && cartBudget > 0 && len > 30 && c.Chance(0.22f))
                {
                    var s = c.Range(a0 + 12, a1 - 12);
                    if (Put(c, "St_FoodCart_Yatai", PX(s, 1.6f), Y, PZ(s, 1.6f), toWall, 1.6f) != null)
                    {
                        cartBudget--;
                        if (c.Steam.Count < 24) c.Steam.Add(V(PX(s, 1.6f), Y + 1.3f, PZ(s, 1.6f)));
                        c.GlowGround(PX(s, 1.6f), 0.18f, PZ(s, 1.6f), 4f, 4f, 0xffa050, 0.3f);
                        NeonField.Add(V(PX(s, 1.6f), 1.8f, PZ(s, 1.6f)), Hex(0xff6a3a), 1.4f, 6f);
                    }
                }
                if (c.Chance(0.12f))
                {
                    var s = c.Range(a0 + 6, a1 - 6);
                    Put(c, "St_ChargeTotem", PX(s, 0.55f), Y, PZ(s, 0.55f), toWall, 0.4f);
                }
                if (c.Chance(0.08f))
                {
                    var s = c.Range(a0 + 8, a1 - 8);
                    Put(c, "St_DataBooth", PX(s, 0.95f), Y, PZ(s, 0.95f), toWall, 0.8f);
                }
                if (shelterBudget > 0 && len > 40 && !CityContext.NearPlaza(b.Zone) && c.Chance(0.22f))
                {
                    var s = c.Range(a0 + 15, a1 - 15);
                    if (Put(c, "St_TramShelter", PX(s, 1.25f), Y, PZ(s, 1.25f), toRoad, 2.3f) != null)
                    {
                        shelterBudget--;
                        c.GlowGround(PX(s, 1.2f), 0.18f, PZ(s, 1.2f), alongX ? 5 : 3, alongX ? 3 : 5, 0xbfe0ff, 0.22f);
                    }
                }
                if (c.Chance(dense ? 0.35f : 0.2f))
                {
                    var s = c.Range(a0 + 4, a1 - 4);
                    Put(c, "St_TrashBags_" + (char)('A' + c.R.Next(3)), PX(s, 0.75f), Y, PZ(s, 0.75f), c.Range(0, 6.28f), 0.7f);
                }
                if (d == CityDistrict.FoundryRow && c.Chance(0.3f))
                {
                    var s = c.Range(a0 + 6, a1 - 8);
                    Put(c, c.Chance(0.5f) ? "St_WaterBarrier_Orange" : "St_WaterBarrier_White", PX(s, 0.5f), Y, PZ(s, 0.5f), alongX ? 0 : Mathf.PI / 2, 0.9f);
                    Put(c, "TrafficCone", PX(s + 1.6f, 0.5f), Y, PZ(s + 1.6f, 0.5f), c.Range(0, 6.28f), 0.3f);
                }
            }
            // vending machines / capsule toys in front of the storefront service bays
            foreach (var (p, n, alongX) in CityStorefronts.ServiceBays(b))
            {
                if (!c.Chance(0.6f)) continue;
                var yaw = Mathf.Atan2(n.x, n.y);
                var toys = c.Chance(0.3f);
                var off = 0.45f;
                var x = p.x + n.x * off; var z = p.z + n.y * off;
                if (toys) Put(c, "St_CapsuleToys", p.x + n.x * 0.3f, Y, p.z + n.y * 0.3f, yaw, 0.7f);
                else if (vendBudget > 0 && CityKitAssets.Has("Vending_Machine_Drinks"))
                {
                    var along = alongX ? new Vector2(1, 0) : new Vector2(0, 1);
                    for (var k = 0; k < 2 && vendBudget > 0; k++)
                    {
                        var px = x + along.x * (k - 0.5f) * 0.95f; var pz = z + along.y * (k - 0.5f) * 0.95f;
                        if (Put(c, k == 0 ? "Vending_Machine_Drinks" : "Vending_Machine_Food", px, Y, pz, yaw, 0.45f) != null)
                        {
                            vendBudget--;
                            c.GlowGround(px + n.x * 0.9f, 0.18f, pz + n.y * 0.9f, 1.8f, 1.8f, 0xe8f2ff, 0.25f);
                        }
                    }
                    NeonField.Add(V(x + n.x * 0.6f, 1.2f, z + n.y * 0.6f), Hex(0xd8ecff), 1.0f, 4f);
                }
            }
        }

        /// <summary>Alley dumpster + garbage bags (kit versions); false when the kit is missing (caller keeps the boxes).</summary>
        public static bool AlleyBins(CityContext c, float x, float z, bool alongX, float ds, System.Func<float, float, bool, float> P, float across, float side)
        {
            Begin(c);
            if (!CityKitAssets.Has("St_Dumpster_Green")) return false;
            var yaw = alongX ? (side > 0 ? Mathf.PI : 0) : (side > 0 ? -Mathf.PI / 2 : Mathf.PI / 2);
            c.Prop(c.Chance(0.6f) ? "St_Dumpster_Green" : "St_Dumpster_Blue", x, Y, z, yaw);
            var bx = P(ds + 1.9f, across + side - 0.15f, true); var bz = P(ds + 1.9f, across + side - 0.15f, false);
            c.Prop("St_TrashBags_" + (char)('A' + c.R.Next(3)), bx, Y, bz, c.Range(0, 6.28f), CityCuller.Small, 1, false);
            if (c.Chance(0.5f))
            {
                var gx = P(ds - 2.4f, across, true); var gz = P(ds - 2.4f, across, false);
                c.Prop("St_SteamGrate", gx, Y + 0.002f, gz, alongX ? 0 : Mathf.PI / 2, CityCuller.Small, 1, false);
                if (c.Steam.Count < 24) c.Steam.Add(V(gx, Y + 0.05f, gz));
            }
            c.KitPieces += 2;
            return true;
        }

        // ------------------------------------------------------------------ overhead cables

        static Mesh lanternMesh;

        static Mesh LanternMesh()
        {
            if (lanternMesh != null) return lanternMesh;
            // lathe: paper lantern (barrel) 0.32 m wide, 0.4 m tall, hanging from the origin
            var prof = new (float r, float y)[] { (0.06f, 0), (0.12f, -0.05f), (0.16f, -0.2f), (0.12f, -0.35f), (0.06f, -0.4f) };
            const int n = 10;
            var v = new List<Vector3>(); var nr = new List<Vector3>(); var uv = new List<Vector2>(); var t = new List<int>();
            for (var k = 0; k < prof.Length; k++)
                for (var i = 0; i <= n; i++)
                {
                    var a = i / (float)n * Mathf.PI * 2;
                    var dir = new Vector3(Mathf.Cos(a), 0, Mathf.Sin(a));
                    v.Add(dir * prof[k].r + Vector3.up * prof[k].y);
                    var dr = k == 0 ? prof[1].r - prof[0].r : k == prof.Length - 1 ? prof[k].r - prof[k - 1].r : prof[k + 1].r - prof[k - 1].r;
                    nr.Add((dir + Vector3.up * dr * 2f).normalized);
                    uv.Add(new Vector2(i / (float)n, k / (float)(prof.Length - 1)));
                }
            for (var k = 0; k < prof.Length - 1; k++)
                for (var i = 0; i < n; i++)
                {
                    int a = k * (n + 1) + i, b = a + 1, c2 = a + n + 1, d2 = c2 + 1;
                    t.Add(a); t.Add(c2); t.Add(b); t.Add(b); t.Add(c2); t.Add(d2);
                }
            lanternMesh = new Mesh { name = "street_lantern" };
            lanternMesh.SetVertices(v); lanternMesh.SetNormals(nr); lanternMesh.SetUVs(0, uv); lanternMesh.SetTriangles(t, 0);
            return lanternMesh;
        }

        static CityBuilding BuildingAt(CityContext c, float x, float z)
        {
            foreach (var b in c.Layout.AllBuildings) if (b.Foot.Contains(x, z)) return b;
            return null;
        }

        /// <summary>Sagging tube through prototype points (Unity-space mesh, merged into the static geometry).</summary>
        static void Tube(LevelKit k, List<Vector3> pts, float r, string mat)
        {
            const int sides = 5;
            var v = new List<Vector3>(); var nr = new List<Vector3>(); var uv = new List<Vector2>(); var t = new List<int>();
            for (var i = 0; i < pts.Count; i++)
            {
                var p = V(pts[i]);
                var fwd = (i < pts.Count - 1 ? V(pts[i + 1]) - p : p - V(pts[i - 1])).normalized;
                var side = Vector3.Cross(fwd, Vector3.up).normalized;
                var up = Vector3.Cross(side, fwd);
                for (var s = 0; s <= sides; s++)
                {
                    var a = s / (float)sides * Mathf.PI * 2;
                    var d = side * Mathf.Cos(a) + up * Mathf.Sin(a);
                    v.Add(p + d * r); nr.Add(d); uv.Add(new Vector2(s / (float)sides, i));
                }
            }
            for (var i = 0; i < pts.Count - 1; i++)
                for (var s = 0; s < sides; s++)
                {
                    int a = i * (sides + 1) + s, b = a + 1, c2 = a + sides + 1, d2 = c2 + 1;
                    t.Add(a); t.Add(b); t.Add(c2); t.Add(b); t.Add(d2); t.Add(c2);
                }
            var m = new Mesh { name = "street_cable" };
            m.SetVertices(v); m.SetNormals(nr); m.SetUVs(0, uv); m.SetTriangles(t, 0);
            k.AddMesh(m, mat, Vector3.zero, Quaternion.identity, null, false);
            Object.Destroy(m);
        }

        static string Mat(string name, string fallback) => Resources.Load<Material>("Env/Materials/" + name) != null ? name : fallback;

        /// <summary>Cable bundles (and lantern strings) across the road segments where buildings face each other.</summary>
        public static void Cables(CityContext c)
        {
            Begin(c);
            var k = c.Kit;
            var lanternMat = Mat("emit_st_lantern_red", "emit_panel_warm");
            var lanternWarm = Mat("emit_st_lantern_warm", "emit_panel_warm");
            var web = Application.platform == RuntimePlatform.WebGLPlayer;
            var budget = web ? 70 : 200;
            var xl = CityLayout.XL; var zl = CityLayout.ZL;
            for (var pass = 0; pass < 2; pass++)
            {
                var lines = pass == 0 ? xl : zl;
                var others = pass == 0 ? zl : xl;
                foreach (var line in lines)
                    for (var j = 0; j < others.Length - 1; j++)
                    {
                        float a = others[j], b = others[j + 1];
                        if (!(pass == 0 ? CityLayout.XSeg(line, a, b) : CityLayout.ZSeg(line, a, b))) continue;
                        var district = pass == 0 ? CityLayout.DistrictAt(line, (a + b) / 2) : CityLayout.DistrictAt((a + b) / 2, line);
                        var dense = district == CityDistrict.NeonMarket || district == CityDistrict.KowloonStacks || district == CityDistrict.CanalWard;
                        var n = dense ? 3 + c.R.Next(4) : district == CityDistrict.ArcologyGate ? c.R.Next(2) : 1 + c.R.Next(3);
                        var face = H + CityLayout.Walk;
                        for (var i = 0; i < n && budget > 0; i++)
                        {
                            var s = c.Range(a + 16, b - 16);
                            // facade points on both sides (prototype); both must be buildings tall enough
                            float x0 = pass == 0 ? line - face : s, z0 = pass == 0 ? s : line - face;
                            float x1 = pass == 0 ? line + face : s, z1 = pass == 0 ? s : line + face;
                            var b0 = BuildingAt(c, x0 + (pass == 0 ? -0.6f : 0), z0 + (pass == 1 ? -0.6f : 0));
                            var b1 = BuildingAt(c, x1 + (pass == 0 ? 0.6f : 0), z1 + (pass == 1 ? 0.6f : 0));
                            if (b0 == null || b1 == null) continue;
                            var top = Mathf.Min(b0.PodiumHeight > 0 ? b0.PodiumHeight : b0.Height, b1.PodiumHeight > 0 ? b1.PodiumHeight : b1.Height);
                            if (top < 8f) continue;
                            var y0 = c.Range(6.2f, Mathf.Min(11f, top - 1f));
                            var y1 = Mathf.Clamp(y0 + c.Range(-1.2f, 1.2f), 6f, top - 1f);
                            var span = face * 2;
                            var sag = c.Range(0.4f, 1.0f) + span * 0.02f;
                            var bundle = 1 + c.R.Next(3);
                            var lanterns = dense && c.Chance(0.3f);
                            for (var q = 0; q < bundle; q++)
                            {
                                var dy = q * c.Range(0.08f, 0.22f); var ds = q * c.Range(-0.25f, 0.25f);
                                var pts = new List<Vector3>();
                                const int segs = 12;
                                for (var t = 0; t <= segs; t++)
                                {
                                    var f = t / (float)segs;
                                    var y = Mathf.Lerp(y0, y1, f) - dy - (sag + q * 0.15f) * 4 * f * (1 - f);
                                    pts.Add(pass == 0 ? new Vector3(Mathf.Lerp(x0, x1, f), y, s + ds) : new Vector3(s + ds, y, Mathf.Lerp(z0, z1, f)));
                                }
                                Tube(k, pts, q == 0 ? 0.03f : 0.018f, "rubber");
                            }
                            // wall anchors
                            k.Box(x0, y0, z0, 0.18f, 0.18f, 0.18f, "metal_dark", collide: false, shadow: false);
                            k.Box(x1, y1, z1, 0.18f, 0.18f, 0.18f, "metal_dark", collide: false, shadow: false);
                            CableCount++;
                            budget--;
                            if (lanterns)
                            {
                                var cnt = 6 + c.R.Next(4);
                                var warm = c.Chance(0.4f);
                                for (var q = 1; q <= cnt; q++)
                                {
                                    var f = q / (float)(cnt + 1);
                                    var y = Mathf.Lerp(y0, y1, f) - sag * 4 * f * (1 - f) - 0.05f;
                                    var p = pass == 0 ? new Vector3(Mathf.Lerp(x0, x1, f), y, s) : new Vector3(s, y, Mathf.Lerp(z0, z1, f));
                                    k.AddMesh(LanternMesh(), warm ? lanternWarm : lanternMat, p, Quaternion.identity, null, false);
                                    c.GlowCross(p.x, y - 0.2f, p.z, 0.9f, warm ? 0xffb060u : 0xff4020u, 0.9f);
                                    Lanterns++;
                                }
                                var mid = pass == 0 ? new Vector3(line, (y0 + y1) / 2 - sag, s) : new Vector3(s, (y0 + y1) / 2 - sag, line);
                                NeonField.Add(V(mid), Hex(warm ? 0xffb060u : 0xff4020u), 1.3f, 12f);
                            }
                        }
                    }
            }
        }

        // ------------------------------------------------------------------ decals

        static int decalBudget;

        static void Decal(CityContext c, string name, float x, float y, float z, Vector3 normalProto, float yawDeg, float scale)
        {
            if (decalBudget <= 0) return;
            var world = c.Kit.Root.TransformPoint(V(x, y, z));
            var normal = c.Kit.Root.TransformDirection(new Vector3(-normalProto.x, normalProto.y, normalProto.z));
            var go = DecalKit.Place(c.Cells.Cell(world, CityCuller.Small), name, world, normal, -yawDeg, scale, normalProto.y > 0.5f ? 0.3f : 0.3f);
            if (go == null) return;
            decalBudget--;
            Decals++;
        }

        /// <summary>Road and pavement decals across the whole district (after all blocks).</summary>
        public static void StreetDecals(CityContext c)
        {
            Begin(c);
            if (!CityKitAssets.Has("St_Bollard_LED")) return;
            var xl = CityLayout.XL; var zl = CityLayout.ZL;
            // (standing water comes from EOA/StreetSurface: macro basins filled by _EOA_Wetness, no puddle decals on roads)
            string[] oil = { "Oil_Stain_A", "Oil_Stain_B" };
            for (var pass = 0; pass < 2; pass++)
            {
                var lines = pass == 0 ? xl : zl;
                var others = pass == 0 ? zl : xl;
                foreach (var line in lines)
                    for (var j = 0; j < others.Length - 1; j++)
                    {
                        float a = others[j], b = others[j + 1];
                        if (!(pass == 0 ? CityLayout.XSeg(line, a, b) : CityLayout.ZSeg(line, a, b))) continue;
                        float PX(float along, float acr) => pass == 0 ? line + acr : along;
                        float PZ(float along, float acr) => pass == 0 ? along : line + acr;
                        var roadYaw = pass == 0 ? 90f : 0f;
                        var len = b - a;
                        for (var i = 0; i < Mathf.RoundToInt(len / 30f); i++)
                            if (c.Chance(0.6f)) { var s = c.Range(a + 14, b - 14); var acr = c.Range(-5.5f, 5.5f); Decal(c, c.Chance(0.5f) ? "St_Asphalt_Patch_A" : "St_Asphalt_Patch_B", PX(s, acr), 0, PZ(s, acr), Vector3.up, roadYaw + c.Range(-3, 3), c.Range(0.8f, 1.3f)); }
                        if (c.Chance(0.18f)) { var s = c.Range(a + 16, b - 16); var acr = c.Chance(0.5f) ? -2.4f : 2.4f; Decal(c, "St_Skid_Marks", PX(s, acr), 0, PZ(s, acr), Vector3.up, roadYaw + c.Range(-6, 6), c.Range(0.9f, 1.4f)); }
                        for (var i = 0; i < c.R.Next(3); i++) { var s = c.Range(a + 14, b - 14); var acr = c.Chance(0.5f) ? -6.1f : 6.1f; Decal(c, c.Pick(oil), PX(s, acr), 0, PZ(s, acr), Vector3.up, c.Range(0, 360), c.Range(0.6f, 0.9f)); }
                        if (c.Chance(0.5f)) { var s = c.Range(a + 14, b - 14); var acr = c.Range(-4, 4); Decal(c, "Crack_Asphalt_Network", PX(s, acr), 0, PZ(s, acr), Vector3.up, c.Range(0, 360), c.Range(0.8f, 1.3f)); }
                        if (c.Chance(0.7f)) { var s = c.Range(a + 14, b - 14); var acr = c.Range(-2.5f, 2.5f); Decal(c, "Manhole_Cover", PX(s, acr), 0, PZ(s, acr), Vector3.up, c.Range(0, 360), 1f); }
                    }
            }
            // pavements
            string[] litter = { "Litter_Paper_A", "Litter_Paper_B", "Debris_Scatter_A" };
            string[] concrete = { "Crack_Concrete_A", "Crack_Concrete_B", "Crack_Concrete_C" };
            foreach (var blk in c.Layout.Blocks)
                foreach (var face in CityFace.All)
                {
                    CityFace.Line(blk.Slab, face, out var a0, out var a1, out var kerb, out var n, out var alongX);
                    float PX(float s, float dk) => alongX ? s : kerb - n.x * dk;
                    float PZ(float s, float dk) => alongX ? kerb - n.y * dk : s;
                    var yaw = alongX ? 0f : 90f;
                    for (var i = 0; i < 1 + c.R.Next(2); i++) { var s = c.Range(a0 + 4, a1 - 4); var dk = c.Range(1.0f, 3.0f); Decal(c, "St_Pavement_Stains", PX(s, dk), Y, PZ(s, dk), Vector3.up, c.Range(0, 360), c.Range(0.8f, 1.2f)); }
                    if (c.Chance(0.5f)) { var s = c.Range(a0 + 4, a1 - 4); var dk = c.Range(1.0f, 3.0f); Decal(c, c.Pick(concrete), PX(s, dk), Y, PZ(s, dk), Vector3.up, c.Range(0, 360), c.Range(0.8f, 1.1f)); }
                    if (c.Chance(0.6f)) { var s = c.Range(a0 + 4, a1 - 4); var dk = c.Range(2.8f, 3.4f); Decal(c, c.Pick(litter), PX(s, dk), Y, PZ(s, dk), Vector3.up, yaw + c.Range(-30, 30), c.Range(0.7f, 1.0f)); }
                }
        }

        /// <summary>Reset the static state for the next city build (zone reload).</summary>
        public static void End()
        {
            ctx = null;
            occupied.Clear();
        }
    }
}
