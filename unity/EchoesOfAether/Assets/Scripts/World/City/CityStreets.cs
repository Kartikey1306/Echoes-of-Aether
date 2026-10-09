using System.Collections.Generic;
using UnityEngine;
using static EOA.ProtoSpace;

namespace EOA
{
    /// <summary>
    /// Street-level construction of the open city (prototype coordinates through <see cref="LevelKit"/>): roads,
    /// intersections, lane markings and zebra crossings, sidewalk slabs, lamps, street furniture, parked cars, the
    /// canal with its bridges, pedestrian overpasses, skybridges and the megawall boundary with its sealed tunnels.
    /// </summary>
    public static class CityStreets
    {
        const float Y = CityLayout.Curb;
        const float H = CityLayout.RoadHalf;

        // ------------------------------------------------------------------ roads and slabs

        public static void Roads(CityContext c)
        {
            var k = c.Kit;
            var xl = CityLayout.XL; var zl = CityLayout.ZL;
            // HD street surfaces (street kit / EOA/StreetSurface; environment materials when the kit is missing)
            var surf = StreetSurfaces.Current = new StreetSurfaces();
            var gutter = StreetKit.Surface("gutter");
            void Road(float cx, float cz, float w, float d, bool worn)
            {
                surf.Top(StreetKit.Surface(worn ? "road_worn" : "road"), new PRect(cx - w / 2, cz - d / 2, cx + w / 2, cz + d / 2), 0);
                k.SolidCollider(cx, -0.25f, cz, w, 0.5f, d);
            }
            bool Worn(float x, float z, float p) => c.Chance(CityLayout.DistrictAt(x, z) is CityDistrict.FoundryRow or CityDistrict.KowloonStacks ? p + 0.35f : p);
            // Roads along z (x-lines) and their map runs.
            foreach (var x in xl)
            {
                float run0 = float.NaN, run1 = 0;
                for (var j = 0; j < zl.Length - 1; j++)
                {
                    float za = zl[j], zb = zl[j + 1];
                    if (!CityLayout.XSeg(x, za, zb)) { FlushRun(c, ref run0, run1, x, true); continue; }
                    var len = zb - za - 2 * H;
                    Road(x, (za + zb) / 2, 2 * H, len, Worn(x, (za + zb) / 2, 0.3f));
                    surf.Strip(gutter, new Vector2(x + H, za + H), new Vector2(x + H, zb - H), 0.003f, 0.6f, 0f, za);
                    surf.Strip(gutter, new Vector2(x - H, za + H), new Vector2(x - H, zb - H), 0.003f, -0.6f, 0f, za);
                    SegmentMarks(c, x, za, zb, true);
                    if (float.IsNaN(run0)) run0 = za - H;
                    run1 = zb + H;
                }
                FlushRun(c, ref run0, run1, x, true);
            }
            foreach (var z in zl)
            {
                float run0 = float.NaN, run1 = 0;
                for (var i = 0; i < xl.Length - 1; i++)
                {
                    float xa = xl[i], xb = xl[i + 1];
                    if (!CityLayout.ZSeg(z, xa, xb)) { FlushRun(c, ref run0, run1, z, false); continue; }
                    var len = xb - xa - 2 * H;
                    Road((xa + xb) / 2, z, len, 2 * H, Worn((xa + xb) / 2, z, 0.3f));
                    surf.Strip(gutter, new Vector2(xa + H, z - H), new Vector2(xb - H, z - H), 0.003f, 0.6f, 0f, xa);
                    surf.Strip(gutter, new Vector2(xa + H, z + H), new Vector2(xb - H, z + H), 0.003f, -0.6f, 0f, xa);
                    SegmentMarks(c, z, xa, xb, false);
                    if (float.IsNaN(run0)) run0 = xa - H;
                    run1 = xb + H;
                }
                FlushRun(c, ref run0, run1, z, false);
            }
            foreach (var x in xl)
                foreach (var z in zl)
                    if (CityLayout.NodeExists(x, z)) Road(x, z, 2 * H, 2 * H, Worn(x, z, 0.55f));
        }

        static void FlushRun(CityContext c, ref float r0, float r1, float line, bool alongZ)
        {
            if (float.IsNaN(r0)) return;
            if (alongZ) c.MapRect("road", line, (r0 + r1) / 2, 2 * H, r1 - r0);
            else c.MapRect("road", (r0 + r1) / 2, line, r1 - r0, 2 * H);
            r0 = float.NaN;
        }

        /// <summary>Centre line, parking lines, stop lines and zebra crossings of one road segment between nodes a and b.</summary>
        static void SegmentMarks(CityContext c, float line, float a, float b, bool alongZ)
        {
            var k = c.Kit;
            var len = b - a - 2 * H;
            var mid = (a + b) / 2;
            void Mark(float across, float along, float w, float l, string mat)
            {
                var surf = StreetSurfaces.Current;
                if (surf != null && !mat.StartsWith("emit_"))
                {
                    // worn road paint (alpha-cut thermoplastic) flush on the asphalt
                    var paint = StreetKit.Surface(mat == "metal_yellow" ? "paint_yellow" : "paint_white");
                    var r = alongZ ? new PRect(line + across - w / 2, along - l / 2, line + across + w / 2, along + l / 2)
                                   : new PRect(along - l / 2, line + across - w / 2, along + l / 2, line + across + w / 2);
                    surf.Top(paint, r, 0.004f);
                    return;
                }
                if (alongZ) k.Box(line + across, 0.006f, along, w, 0.012f, l, mat, collide: false, shadow: false);
                else k.Box(along, 0.006f, line + across, l, 0.012f, w, mat, collide: false, shadow: false);
            }
            Mark(-0.16f, mid, 0.1f, len, "metal_yellow");
            Mark(0.16f, mid, 0.1f, len, "metal_yellow");
            Mark(-4.3f, mid, 0.12f, len - 12, "metal_painted_white");
            Mark(4.3f, mid, 0.12f, len - 12, "metal_painted_white");
            // Zebra crossings at both ends (stripes run with the road, spaced across it).
            for (var s = 0; s < 12; s++)
            {
                var acr = -6.6f + s * 1.2f;
                Mark(acr, a + 10.3f, 0.55f, 3.3f, "metal_painted_white");
                Mark(acr, b - 10.3f, 0.55f, 3.3f, "metal_painted_white");
            }
            // Stop lines on the approach half (right-hand traffic in Unity space; the prototype X axis is mirrored).
            if (alongZ) { Mark(H / 2, a + 12.7f, H, 0.4f, "metal_painted_white"); Mark(-H / 2, b - 12.7f, H, 0.4f, "metal_painted_white"); }
            else { Mark(-H / 2, a + 12.7f, H, 0.4f, "metal_painted_white"); Mark(H / 2, b - 12.7f, H, 0.4f, "metal_painted_white"); }
            // The avenue that runs out of the plaza gets cyan kerb lights.
            if (!alongZ && line == CityLayout.AvenueZ)
            {
                Mark(-H + 0.12f, mid, 0.12f, len, "emit_strip_cyan");
                Mark(H - 0.12f, mid, 0.12f, len, "emit_strip_cyan");
            }
        }

        public static void Slabs(CityContext c)
        {
            var k = c.Kit;
            foreach (var b in c.Layout.Blocks)
            {
                var s = b.Slab;
                if (!b.Canal) Slab(k, s);
                else
                {
                    Slab(k, new PRect(s.X0, s.Z0, s.X1, CityLayout.CanalZ0));
                    Slab(k, new PRect(s.X0, CityLayout.CanalZ1, s.X1, s.Z1));
                    // Sidewalks over the canal along both roads (the road itself is the bridge deck).
                    Slab(k, new PRect(s.X0, CityLayout.CanalZ0, b.Zone.X0, CityLayout.CanalZ1));
                    Slab(k, new PRect(b.Zone.X1, CityLayout.CanalZ0, s.X1, CityLayout.CanalZ1));
                }
                if (StreetSurfaces.Current == null) Curbs(k, s);
                c.MapRect("floor", s);
            }
            // Outer sidewalks along the megawall.
            const float wx = CityLayout.WallX, z0 = CityLayout.WallZ0, z1 = CityLayout.WallZ1;
            Slab(k, new PRect(-wx, z0, wx, z0 + CityLayout.Walk));
            Slab(k, new PRect(-wx, z1 - CityLayout.Walk, wx, z1));
            Slab(k, new PRect(-wx, z0 + CityLayout.Walk, -wx + CityLayout.Walk, z1 - CityLayout.Walk));
            Slab(k, new PRect(wx - CityLayout.Walk, z0 + CityLayout.Walk, wx, z1 - CityLayout.Walk));
        }

        public static void Slab(LevelKit k, PRect r, float top = Y, string mat = "concrete_wet")
        {
            if (r.W < 0.05f || r.D < 0.05f) return;
            var surf = StreetSurfaces.Current;
            if (surf == null) { k.Box(r.CX, top - 0.25f, r.CZ, r.W, 0.5f, r.D, mat); return; }
            // HD pavement (district paver / slab style) or road surface for the asphalt lots; kerbs are added where
            // the slab edge is exposed when the surfaces are finished
            var preset = mat == "asphalt" ? "road_worn" : mat == "concrete_dark" ? "slab" : StreetKit.Pavement(CityLayout.DistrictAt(r.CX, r.CZ));
            surf.Slab(r, top, preset);
            k.SolidCollider(r.CX, top - 0.25f, r.CZ, r.W, 0.5f, r.D);
        }

        static void Curbs(LevelKit k, PRect s)
        {
            const float w = 0.28f;
            k.Box(s.CX, Y - 0.07f, s.Z0 + w / 2, s.W, 0.16f, w, "concrete", collide: false);
            k.Box(s.CX, Y - 0.07f, s.Z1 - w / 2, s.W, 0.16f, w, "concrete", collide: false);
            k.Box(s.X0 + w / 2, Y - 0.07f, s.CZ, w, 0.16f, s.D - 2 * w, "concrete", collide: false);
            k.Box(s.X1 - w / 2, Y - 0.07f, s.CZ, w, 0.16f, s.D - 2 * w, "concrete", collide: false);
        }

        // ------------------------------------------------------------------ lamps

        public struct LampStyle { public uint Color; public string Lens, Strip; }

        // District street lighting: warm sodium / amber pools everywhere except the corporate Arcology Gate (cool white
        // with gold) and the canal (teal-white over the water with warm lamps between).
        public static LampStyle Style(CityDistrict d, int i) => d switch
        {
            CityDistrict.NeonMarket => i % 2 == 0 ? new LampStyle { Color = 0xffa452, Lens = "emit_panel_warm", Strip = "emit_strip_warm" }
                                                  : new LampStyle { Color = 0xff7442, Lens = "emit_panel_warm", Strip = "emit_red" },
            CityDistrict.KowloonStacks => i % 3 == 0 ? new LampStyle { Color = 0xdcffc4, Lens = "emit_panel_white", Strip = "emit_strip_yellow" }
                                                     : new LampStyle { Color = 0xffbe6a, Lens = "emit_panel_warm", Strip = "emit_strip_yellow" },
            CityDistrict.ArcologyGate => i % 3 == 2 ? new LampStyle { Color = 0xffd690, Lens = "emit_panel_warm", Strip = "emit_amber" }
                                                    : new LampStyle { Color = 0xd8eeff, Lens = "emit_panel_white", Strip = "emit_strip_cyan" },
            CityDistrict.CanalWard => i % 2 == 0 ? new LampStyle { Color = 0xa4f2e4, Lens = "emit_panel_cyan", Strip = "emit_strip_cyan" }
                                                 : new LampStyle { Color = 0xffb46e, Lens = "emit_panel_warm", Strip = "emit_strip_warm" },
            _ => new LampStyle { Color = 0xff8e30, Lens = "emit_panel_warm", Strip = "emit_strip_warm" },
        };

        /// <summary>Cyberpunk street light: pole with a neon strip, arm over the road (ax, az = unit toward the road).</summary>
        public static void Lamp(CityContext c, float x, float z, float ax, float az, LampStyle s)
        {
            var k = c.Kit;
            k.Box(x, Y + 0.3f, z, 0.45f, 0.6f, 0.45f, "metal_dark", collide: false);
            k.Box(x, Y + 3.75f, z, 0.2f, 7.5f, 0.2f, "metal_dark", collide: false);
            k.SolidCollider(x, Y + 3.75f, z, 0.32f, 7.5f, 0.32f);
            var alongX = Mathf.Abs(ax) > 0.5f;
            k.Box(x + ax * 1.15f, Y + 7.4f, z + az * 1.15f, alongX ? 2.4f : 0.14f, 0.14f, alongX ? 0.14f : 2.4f, "metal_dark", collide: false);
            float hx = x + ax * 2.3f, hz = z + az * 2.3f;
            k.Box(hx, Y + 7.3f, hz, alongX ? 1.3f : 0.5f, 0.16f, alongX ? 0.5f : 1.3f, "metal_dark", collide: false);
            k.Box(hx, Y + 7.2f, hz, alongX ? 1.1f : 0.36f, 0.04f, alongX ? 0.36f : 1.1f, s.Lens, collide: false, shadow: false);
            k.Box(x - ax * 0.12f, Y + 3.4f, z - az * 0.12f, 0.05f, 4.4f, 0.05f, s.Strip, collide: false, shadow: false);
            c.GlowGround(hx, 0.03f, hz, 9f, 9f, s.Color, 0.2f);
            c.GlowCross(hx, Y + 7.05f, hz, 1.3f, s.Color, 0.35f);
            c.LampPos.Add(V(hx, Y + 6.6f, hz));
            c.LampCol.Add(Hex(s.Color));
        }

        /// <summary>Lamps along the curb of one slab side (each road gets lamps on one side only).</summary>
        public static void LampRow(CityContext c, PRect slab, byte face, CityDistrict d, List<PRect> skip)
        {
            CityFace.Line(slab, face, out var a0, out var a1, out var line, out var n, out var alongX);
            var len = a1 - a0;
            var count = Mathf.Max(1, Mathf.FloorToInt((len - 28) / 26f) + 1);
            var step = (len - 28) / Mathf.Max(1, count - 1);
            for (var i = 0; i < count; i++)
            {
                var s = count == 1 ? (a0 + a1) / 2 : a0 + 14 + step * i;
                var px = alongX ? s : line - n.x * 0.6f;
                var pz = alongX ? line - n.y * 0.6f : s;
                var blocked = false;
                foreach (var r in skip) if (r.Contains(px, pz)) { blocked = true; break; }
                if (blocked) continue;
                Lamp(c, px, pz, n.x, n.y, Style(d, i));
            }
        }

        // ------------------------------------------------------------------ furniture

        static readonly string[] VendBody = { "metal_painted_red", "plastic_dark", "metal_painted_white", "metal_painted_green" };
        static readonly string[] VendFace = { "emit_panel_cyan", "emit_panel_white", "screen", "emit_panel_violet", "emit_panel_warm" };
        static readonly uint[] VendGlow = { 0x5fd8ff, 0xe8f2ff, 0x7fd8ff, 0xffa040, 0xffd2a0 };

        /// <summary>Vending machine against a wall: n = outward face normal (prototype), along = unit along the wall.</summary>
        public static void Vending(CityContext c, float x, float z, Vector2 n, bool alongX)
        {
            var k = c.Kit;
            var body = c.Pick(VendBody);
            var fi = c.R.Next(VendFace.Length);
            float w = 1.1f, d = 0.85f, h = 1.95f;
            float cx = x + n.x * d / 2, cz = z + n.y * d / 2;
            k.Box(cx, Y + h / 2, cz, alongX ? w : d, h, alongX ? d : w, body, collide: false);
            k.SolidCollider(cx, Y + h / 2, cz, alongX ? w : d, h, alongX ? d : w);
            float fx = x + n.x * (d + 0.02f), fz = z + n.y * (d + 0.02f);
            k.Box(fx, Y + 1.15f, fz, alongX ? 0.9f : 0.04f, 1.35f, alongX ? 0.04f : 0.9f, VendFace[fi], collide: false, shadow: false);
            k.Box(fx, Y + 0.35f, fz, alongX ? 0.7f : 0.05f, 0.18f, alongX ? 0.05f : 0.7f, "black", collide: false, shadow: false);
            c.GlowGround(x + n.x * 1.6f, 0.17f, z + n.y * 1.6f, 2.2f, 2.2f, VendGlow[fi], 0.3f);
        }

        /// <summary>Street furniture along every sidewalk of a block: the street kit's storefront runs and wall life
        /// first (<see cref="CityStorefronts"/>), then kerb furniture and clutter (<see cref="CityClutter"/>).</summary>
        public static void Furniture(CityContext c, CityBlock b, ref int holoBudget)
        {
            CityStorefronts.Block(c, b);
            foreach (var face in CityFace.All)
            {
                CityFace.Line(b.Zone, face, out var a0, out var a1, out var line, out var n, out var alongX);
                CityFace.Line(b.Slab, face, out _, out _, out var curb, out _, out _);
                var len = a1 - a0;
                // wall-side furniture only where no storefront run covers the wall (vending then stands at the service bays)
                bool WallFree(float s) => CityStorefronts.WallOffset(b, face, line, s) <= 0;
                if (c.Chance(0.24f) && WallFree(c.Range(a0 + 6, a1 - 6)))
                {
                    var s = c.Range(a0 + 6, a1 - 6);
                    var m = 1 + c.R.Next(3);
                    var kit = c.VendBudget > 0 && CityContext.NearPlaza(b.Zone) && CityKitAssets.Has("Vending_Machine_Drinks") && CityKitAssets.Has("Vending_Machine_Food");
                    for (var i = 0; i < m; i++)
                    {
                        var si = s + i * 1.2f;
                        // Stand clear of the shopfront pilasters (0.3 m) on the wall line.
                        if (kit && c.VendBudget > 0)
                        {
                            var off = 0.32f + 0.46f;
                            c.Prop(i % 2 == 0 ? "Vending_Machine_Drinks" : "Vending_Machine_Food", alongX ? si : line + n.x * off, Y, alongX ? line + n.y * off : si, Mathf.Atan2(n.x, n.y));
                            c.VendBudget--;
                            c.KitPieces++;
                        }
                        else Vending(c, alongX ? si : line + n.x * 0.32f, alongX ? line + n.y * 0.32f : si, n, alongX);
                    }
                }
                if (c.Chance(0.3f))
                {
                    var s = c.Chance(0.5f) ? a0 + 3 : a1 - 3;
                    var px = alongX ? s : curb - n.x * 0.9f;
                    var pz = alongX ? curb - n.y * 0.9f : s;
                    c.Prop(c.Chance(0.2f) ? "TrashBin_Tipped" : "TrashBin", px, Y, pz, c.Range(0, 6.28f));
                }
                if (c.Chance(0.12f) && WallFree((a0 + a1) / 2))
                {
                    var s = c.Range(a0 + 8, a1 - 8);
                    var px = alongX ? s : line + n.x * 0.5f;
                    var pz = alongX ? line + n.y * 0.5f : s;
                    // Bench back against the wall, facing the street.
                    var yaw = Mathf.Atan2(n.x, n.y);
                    c.Prop("Bench_Street", px, Y, pz, yaw);
                }
                if (c.Chance(0.08f))
                {
                    var s = c.Range(a0 + 10, a1 - 10);
                    var px = alongX ? s : curb - n.x * 1.0f;
                    var pz = alongX ? curb - n.y * 1.0f : s;
                    c.Prop(CityContext.KitOr("Kiosk_Neon", "Terminal_Kiosk"), px, Y, pz, Mathf.Atan2(-n.x, -n.y));
                    c.Obstacle(px, pz, 1.0f);
                }
                if (holoBudget > 0 && c.Chance(0.1f))
                {
                    holoBudget--;
                    var s = c.Chance(0.5f) ? a0 + 1.5f : a1 - 1.5f;
                    var px = alongX ? s : curb - n.x * 1.2f;
                    var pz = alongX ? curb - n.y * 1.2f : s;
                    HoloPillar(c, px, pz, n);
                    c.Obstacle(px, pz, 0.8f);
                }
                if (c.ShelterBudget > 0 && len > 40 && CityContext.NearPlaza(b.Zone) && c.Chance(0.3f) && CityKitAssets.Has("Bus_Shelter_Neon"))
                {
                    // Bus shelter at the kerb, open side to the road.
                    var s = c.Range(a0 + 16, a1 - 16);
                    var px = alongX ? s : curb - n.x * 1.45f;
                    var pz = alongX ? curb - n.y * 1.45f : s;
                    c.Prop("Bus_Shelter_Neon", px, Y, pz, Mathf.Atan2(n.x, n.y));
                    c.GlowGround(px, 0.18f, pz, alongX ? 5 : 3, alongX ? 3 : 5, 0x00e5ff, 0.25f);
                    c.Obstacle(px, pz, 1.5f);
                    c.ShelterBudget--;
                    c.KitPieces++;
                }
            }
            // Kerb-side clutter, crossings, service-bay vending (street kit).
            CityClutter.Block(c, b);
            // Alleys: dumpster, bags, a lantern, sometimes steam or a food stall at the mouth.
            foreach (var a in b.Alleys) Alley(c, b, a);
        }

        static void HoloPillar(CityContext c, float x, float z, Vector2 n)
        {
            var k = c.Kit;
            k.Box(x, Y + 2.1f, z, 0.22f, 4.2f, 0.22f, "metal_dark", collide: false);
            k.SolidCollider(x, Y + 2.1f, z, 0.3f, 4.2f, 0.3f);
            k.Box(x, Y + 4.25f, z, 0.5f, 0.1f, 0.5f, "emit_strip_cyan", collide: false, shadow: false);
            var p = V(x, Y + 3.1f, z);
            var face = new Vector3(-n.x, 0, n.y);
            var holo = NeonKit.HoloPanel(c.Kit.FxRoot, p + face * 0.2f, Quaternion.LookRotation(-face), new Vector2(1.5f, 2.4f), Neon.Pick(c.R), Neon.Pick(c.R), c.R.Next(3), c.R.Next(), 2.2f);
            c.Cells.Put(holo, CityCuller.Small);
        }

        static void Alley(CityContext c, CityBlock b, PRect a)
        {
            var k = c.Kit;
            var alongX = a.W > a.D;
            var len = alongX ? a.W : a.D;
            var mid = alongX ? a.CX : a.CZ;
            var across = alongX ? a.CZ : a.CX;
            float P(float along, float acr, bool wantX) => wantX ? (alongX ? along : acr) : (alongX ? acr : along);
            // Dumpster against one side.
            var ds = mid + c.Range(-len / 4, len / 4);
            var side = (alongX ? a.D : a.W) / 2 - 0.7f;
            float dx = P(ds, across + side, true), dz = P(ds, across + side, false);
            if (!CityClutter.AlleyBins(c, dx, dz, alongX, ds, P, across, side))
            {
                k.Box(dx, Y + 0.65f, dz, alongX ? 1.8f : 1.1f, 1.3f, alongX ? 1.1f : 1.8f, "metal_painted_green");
                k.Box(dx, Y + 1.33f, dz, alongX ? 1.85f : 1.15f, 0.06f, alongX ? 1.15f : 1.85f, "plastic_dark", collide: false);
                for (var i = 0; i < 3; i++)
                {
                    var bs = ds + 1.4f + i * 0.55f;
                    k.Box(P(bs, across + side - 0.2f, true), Y + 0.25f, P(bs, across + side - 0.2f, false), 0.6f, 0.5f, 0.55f, "black", collide: false);
                }
            }
            // Hanging lantern glow mid alley.
            var lx = P(mid, across, true); var lz = P(mid, across, false);
            var warm = b.District == CityDistrict.NeonMarket ? 0xff4a30u : 0xffb46au; // red paper lantern / warm bulb
            c.GlowCross(lx, Y + 4.2f, lz, 0.9f, warm, 1.2f);
            c.GlowGround(lx, 0.18f, lz, 4f, 4f, warm, 0.22f);
            k.Box(lx, Y + 4.2f, lz, 0.25f, 0.35f, 0.25f, "emit_panel_warm", collide: false, shadow: false);
            if (b.District == CityDistrict.KowloonStacks || b.District == CityDistrict.NeonMarket)
            {
                // Cables strung across the alley.
                for (var i = 0; i < 3; i++)
                {
                    var cs = mid + c.Range(-len / 3, len / 3);
                    var hw = (alongX ? a.D : a.W) / 2;
                    var y1 = 6 + c.Rand * 6; var y2 = y1 + c.Range(-1, 1);
                    Cable(k, P(cs, across - hw, true), y1, P(cs, across - hw, false), P(cs, across + hw, true), y2, P(cs, across + hw, false), 0.3f);
                }
            }
            if (c.Chance(0.35f) && c.Steam.Count < 18) c.Steam.Add(V(P(mid + len * 0.2f, across, true), Y + 0.05f, P(mid + len * 0.2f, across, false)));
            var hw2 = (alongX ? a.D : a.W) / 2;
            // Wall side facing into the alley: prototype yaw of an asset whose front (+z) points from the +side wall inward.
            var inward = alongX ? Mathf.PI : -Mathf.PI / 2;
            if (c.ClutterBudget > 0 && CityContext.NearPlaza(a) && CityKitAssets.Has("Cardboard_Box_Stack"))
            {
                // Kit clutter by the dumpster, a caged wall lamp and a junction box on the walls.
                c.Prop("Cardboard_Box_Stack", P(ds - 1.8f, across + side - 0.1f, true), Y, P(ds - 1.8f, across + side - 0.1f, false), inward, CityCuller.Small, 1, false);
                c.Prop(c.Chance(0.5f) ? "Barrel_Plastic_Blue" : "Barrel_Plastic_Black", P(ds + 3.4f, across + side, true), Y, P(ds + 3.4f, across + side, false), c.Range(0, 6.28f));
                var ls = mid - len * 0.25f;
                c.Prop("Wall_Lamp_Cage", P(ls, across + hw2, true), Y + 3f, P(ls, across + hw2, false), inward, CityCuller.Small, 1, false);
                c.Prop("Electrical_Box_A", P(ls + 2f, across + hw2, true), Y + 1.5f, P(ls + 2f, across + hw2, false), inward, CityCuller.Small, 1, false);
                c.GlowGround(P(ls, across + hw2 - 1.2f, true), 0.18f, P(ls, across + hw2 - 1.2f, false), 3f, 3f, 0xffb070, 0.25f);
                if (!alongX && a.W <= 4.6f && CityKitAssets.Has("Lantern_String_4m"))
                    for (var i = 0; i < 3; i++)
                        c.Prop("Lantern_String_4m", a.X0 + 0.25f, Y + 4.6f + (i % 2) * 0.6f, a.Z0 + len * (0.25f + 0.25f * i), 0, CityCuller.Small, 1, false);
                c.ClutterBudget -= 4;
                c.KitPieces += 4;
            }
            if (b.District == CityDistrict.NeonMarket && c.Chance(0.5f))
            {
                // Food stall just inside the alley mouth, facing the street (the kit's hole-in-the-wall counter when built).
                var end = c.Chance(0.5f);
                var ss = end ? (alongX ? a.X1 : a.Z1) - 3f : (alongX ? a.X0 : a.Z0) + 3f;
                if (CityKitAssets.Has("Street_Food_Counter"))
                {
                    c.Prop("Street_Food_Counter", P(ss, across + hw2, true), Y, P(ss, across + hw2, false), inward);
                    c.GlowGround(P(ss, across + hw2 - 1.5f, true), 0.18f, P(ss, across + hw2 - 1.5f, false), 4f, 4f, 0xffb46a, 0.32f);
                    c.KitPieces++;
                }
                else
                {
                    var yaw = alongX ? (end ? Mathf.PI / 2 : -Mathf.PI / 2) : (end ? 0 : Mathf.PI);
                    c.Prop(c.Chance(0.5f) ? "MarketStall" : "MarketStall_Blue", P(ss, across, true), Y, P(ss, across, false), yaw);
                    c.GlowGround(P(ss, across, true), 0.18f, P(ss, across, false), 5f, 5f, 0xffb46a, 0.3f);
                }
            }
        }

        static Mesh cableMesh;

        /// <summary>Sagging cable between two prototype points (merged segments).</summary>
        public static void Cable(LevelKit k, float x1, float y1, float z1, float x2, float y2, float z2, float sag)
        {
            if (cableMesh == null) cableMesh = FxMesh.Cylinder(0.025f, 0.025f, 1f, 5, false);
            var prev = new Vector3(x1, y1, z1);
            const int segs = 6;
            for (var i = 1; i <= segs; i++)
            {
                var t = i / (float)segs;
                var p = new Vector3(Mathf.Lerp(x1, x2, t), Mathf.Lerp(y1, y2, t) - sag * 4 * t * (1 - t), Mathf.Lerp(z1, z2, t));
                var dir = V(p) - V(prev);
                var len = dir.magnitude;
                if (len > 0.001f) k.AddMesh(cableMesh, "rubber", (prev + p) / 2, Quaternion.FromToRotation(Vector3.up, dir / len), new Vector3(1, len, 1), shadow: false);
                prev = p;
            }
        }

        /// <summary>Parked cars in the parking lanes and steam vents on the roads.</summary>
        public static void RoadDressing(CityContext c, int maxCars, List<PRect> skip)
        {
            var xl = CityLayout.XL; var zl = CityLayout.ZL;
            var cars = 0;
            var grates = 0;
            // Parked cars so far per kerb line (pass, line, side): along position and half length. Two cars drawn
            // too close are not both placed (the RNG draws stay the same, so the rest of the layout is unchanged).
            var parked = new List<(int pass, float line, float acr, float along, float half)>();
            for (var pass = 0; pass < 2; pass++)
            {
                var lines = pass == 0 ? xl : zl;
                var others = pass == 0 ? zl : xl;
                foreach (var line in lines)
                    for (var j = 0; j < others.Length - 1; j++)
                    {
                        float a = others[j], b = others[j + 1];
                        var exists = pass == 0 ? CityLayout.XSeg(line, a, b) : CityLayout.ZSeg(line, a, b);
                        if (!exists) continue;
                        if (cars < maxCars && c.Chance(0.3f))
                        {
                            var n = 1 + c.R.Next(2);
                            for (var i = 0; i < n && cars < maxCars; i++)
                            {
                                var along = c.Range(a + 18, b - 18);
                                var acr = c.Chance(0.5f) ? -6.1f : 6.1f;
                                float px = pass == 0 ? line + acr : along, pz = pass == 0 ? along : line + acr;
                                var blocked = false;
                                foreach (var r in skip) if (r.Contains(px, pz)) { blocked = true; break; }
                                if (blocked) continue;
                                c.Chance(0.5f); // (kept: same layout RNG sequence)
                                // Parked with the traffic of their side of the road (right-hand traffic; prototype yaw).
                                var yaw = (pass == 0 ? (acr > 0 ? Mathf.PI : 0) : (acr > 0 ? Mathf.PI / 2 : Mathf.PI * 1.5f)) + c.Range(-0.04f, 0.04f);
                                var district = CityLayout.DistrictAt(px, pz);
                                string name;
                                var seed = 0;
                                if (VehicleKit.Available)
                                {
                                    // Kit vehicles (paint varies, lights off); wrecks in Foundry Row and Kowloon Stacks.
                                    seed = c.R.Next();
                                    name = CityContext.KitOr(VehicleKit.ParkedName(district, seed), "CyberCar_Sedan");
                                }
                                else name = district == CityDistrict.FoundryRow && c.Chance(0.4f) ? "Car_Sedan_Wrecked" : c.Chance(0.45f) ? "Car_Sedan_Red" : "Car_Sedan";
                                var half = VehicleKit.Available ? VehicleKit.Get(name).Length * 0.5f : 2.4f;
                                var overlap = false;
                                foreach (var q in parked)
                                    if (q.pass == pass && Mathf.Abs(q.line - line) < 0.01f && Mathf.Abs(q.acr - acr) < 0.01f && Mathf.Abs(q.along - along) < q.half + half + 0.8f) { overlap = true; break; }
                                if (!overlap)
                                {
                                    parked.Add((pass, line, acr, along, half));
                                    VehicleKit.Park(c.Prop(name, px, 0, pz, yaw), name, seed);
                                }
                                cars++;
                            }
                        }
                        if (grates < 14 && c.Chance(0.08f))
                        {
                            grates++;
                            var along = c.Range(a + 20, b - 20);
                            float px = pass == 0 ? line - 2.2f : along, pz = pass == 0 ? along : line - 2.2f;
                            if (CityKitAssets.Has("St_SteamGrate")) c.Prop("St_SteamGrate", px, 0.004f, pz, pass == 0 ? 0 : Mathf.PI / 2, CityCuller.Small, 1, false);
                            else c.Kit.Box(px, 0.008f, pz, 1.0f, 0.016f, 1.0f, "grating", collide: false, shadow: false);
                            c.Steam.Add(V(px, 0.05f, pz));
                        }
                    }
            }
            // Street-kit passes over the whole district, then the merged street surfaces (kerbs resolved now that
            // every slab is known) go into the culling cells.
            CityClutter.Cables(c);
            CityClutter.StreetDecals(c);
            var surf = StreetSurfaces.Current;
            if (surf != null)
            {
                surf.Finish(c.Kit.Root, c.Cells);
                StreetSurfaces.Current = null;
            }
            Debug.Log($"[street] storefronts {CityStorefronts.Modules} modules on {CityStorefronts.Faces} faces, {CityStorefronts.WallProps} wall props; " +
                      $"clutter {CityClutter.Props} props, {CityClutter.CableCount} cables, {CityClutter.Lanterns} lanterns, {CityClutter.Decals} decals; surfaces {(StreetKit.SurfacesBuilt ? "HD" : "fallback")}");
            CityClutter.End();
            CityStorefronts.Reset();
        }

        // ------------------------------------------------------------------ canal

        public static void Canal(CityContext c)
        {
            var k = c.Kit;
            const float z0 = CityLayout.CanalZ0, z1 = CityLayout.CanalZ1, w = CityLayout.WallX;
            var zc = (z0 + z1) / 2;
            k.Box(0, CityLayout.CanalWater, zc, 2 * w, 0.1f, z1 - z0, "water", collide: false, shadow: false);
            k.Box(0, -2.5f, z0 - 0.25f, 2 * w, 4.3f, 0.5f, "concrete_dark", collide: false);
            k.Box(0, -2.5f, z1 + 0.25f, 2 * w, 4.3f, 0.5f, "concrete_dark", collide: false);
            k.Box(0, -4.8f, zc, 2 * w, 0.4f, z1 - z0, "concrete_dark", collide: false);
            c.MapRect("water", 0, zc, 2 * w, z1 - z0);
            foreach (var b in c.Layout.Blocks)
            {
                if (!b.Canal) continue;
                float x0 = b.Zone.X0, x1 = b.Zone.X1;
                var xc = (x0 + x1) / 2; var len = x1 - x0;
                Railing(c, x0, z0, x1, z0);
                Railing(c, x0, z1, x1, z1);
                Railing(c, x0, z0, x0, z1);
                Railing(c, x1, z0, x1, z1);
                // Neon strips along the channel walls reflect in the water.
                k.Box(xc, -0.9f, z0 + 0.03f, len, 0.07f, 0.07f, (b.Index & 1) == 0 ? "emit_strip_cyan" : "emit_strip_violet", collide: false, shadow: false);
                k.Box(xc, -0.9f, z1 - 0.03f, len, 0.07f, 0.07f, (b.Index & 1) == 0 ? "emit_strip_violet" : "emit_strip_cyan", collide: false, shadow: false);
                for (var i = 0; i < 3; i++)
                {
                    var gx = c.Range(x0 + 4, x1 - 4);
                    c.GlowGround(gx, CityLayout.CanalWater + 0.07f, zc + c.Range(-3, 3), 2.5f, 9f, c.Chance(0.5f) ? 0xffa040u : 0x18f0c4u, 0.35f);
                }
            }
            // Bridge fascias where the roads cross the canal.
            foreach (var x in CityLayout.XL)
            {
                foreach (var side in new[] { -1f, 1f })
                {
                    var fx = x + side * (H + CityLayout.Walk + 0.25f);
                    k.Box(fx, -0.6f, zc, 0.5f, 1.5f, z1 - z0, "concrete", collide: false);
                    k.Box(fx, -1.38f, zc, 0.06f, 0.06f, z1 - z0, "emit_strip_violet", collide: false, shadow: false);
                }
            }
        }

        /// <summary>Railing (posts, rails) with an invisible blocking wall between two prototype points at sidewalk level.</summary>
        public static void Railing(CityContext c, float x1, float z1, float x2, float z2, float y = Y)
        {
            var k = c.Kit;
            var len = Mathf.Sqrt((x2 - x1) * (x2 - x1) + (z2 - z1) * (z2 - z1));
            if (len < 0.5f) return;
            var alongX = Mathf.Abs(x2 - x1) > Mathf.Abs(z2 - z1);
            float cx = (x1 + x2) / 2, cz = (z1 + z2) / 2;
            k.Box(cx, y + 1.08f, cz, alongX ? len : 0.07f, 0.07f, alongX ? 0.07f : len, "metal_dark", collide: false);
            k.Box(cx, y + 0.55f, cz, alongX ? len : 0.04f, 0.04f, alongX ? 0.04f : len, "metal_dark", collide: false, shadow: false);
            var posts = Mathf.Max(1, Mathf.RoundToInt(len / 2.5f));
            for (var i = 0; i <= posts; i++)
            {
                var t = i / (float)posts;
                k.Box(Mathf.Lerp(x1, x2, t), y + 0.55f, Mathf.Lerp(z1, z2, t), 0.07f, 1.1f, 0.07f, "metal_dark", collide: false);
            }
            k.Wall(cx, y + 0.9f, cz, alongX ? len : 0.25f, 1.8f, alongX ? 0.25f : len);
        }

        // ------------------------------------------------------------------ overpasses and skybridges

        /// <summary>
        /// Accessible pedestrian overpass along z at x from zDeck0 to zDeck1 (deck top y), with stairs down to both
        /// landings, glass parapets, neon underglow and blocking walls.
        /// </summary>
        public static void Overpass(CityContext c, float x, float zDeck0, float zDeck1, float y, List<PRect> noLamps)
        {
            var k = c.Kit;
            const float w = 4f;
            var len = zDeck1 - zDeck0;
            var zc = (zDeck0 + zDeck1) / 2;
            k.Box(x, y - 0.45f, zc, w, 0.9f, len, "concrete_dark");
            foreach (var side in new[] { -1f, 1f })
            {
                var sx = x + side * (w / 2 - 0.08f);
                k.Box(sx, y + 0.55f, zc, 0.06f, 1.1f, len, "glass", collide: false, shadow: false);
                k.Box(sx, y + 1.12f, zc, 0.14f, 0.08f, len, "metal_dark", collide: false);
                k.Box(x + side * (w / 2 + 0.02f), y - 0.94f, zc, 0.07f, 0.07f, len, "emit_strip_cyan", collide: false, shadow: false);
                k.Wall(x + side * (w / 2), y + 0.9f, zc, 0.25f, 1.8f, len);
            }
            // Stairs down to both landings.
            var rise = y - Y;
            var steps = Mathf.CeilToInt(rise / 0.32f);
            const float run = 0.58f;
            var runLen = steps * run;
            k.Stairs(x, Y, zDeck0 - runLen, 0, w, steps, rise / steps, run, "concrete");
            k.Stairs(x, Y, zDeck1 + runLen, Mathf.PI, w, steps, rise / steps, run, "concrete");
            foreach (var side in new[] { -1f, 1f })
            {
                k.Wall(x + side * (w / 2 + 0.05f), (y + 1.8f) / 2, zDeck0 - runLen / 2, 0.25f, y + 1.8f, runLen);
                k.Wall(x + side * (w / 2 + 0.05f), (y + 1.8f) / 2, zDeck1 + runLen / 2, 0.25f, y + 1.8f, runLen);
                // Neon handrails along the flights (negative pitch rises toward +z, as LevelKit.Stairs).
                var slope = Mathf.Atan2(rise, runLen);
                var hyp = Mathf.Sqrt(rise * rise + runLen * runLen);
                k.Box(x + side * (w / 2 + 0.05f), Y + rise / 2 + 0.95f, zDeck0 - runLen / 2, 0.1f, 0.08f, hyp, "emit_strip_violet", collide: false, shadow: false, rotX: -slope);
                k.Box(x + side * (w / 2 + 0.05f), Y + rise / 2 + 0.95f, zDeck1 + runLen / 2, 0.1f, 0.08f, hyp, "emit_strip_violet", collide: false, shadow: false, rotX: slope);
            }
            // Columns under both ends of the span.
            k.Box(x, (y - 0.9f) / 2, zDeck0 + 1.2f, 1.1f, y - 0.9f, 1.1f, "concrete_dark");
            k.Box(x, (y - 0.9f) / 2, zDeck1 - 1.2f, 1.1f, y - 0.9f, 1.1f, "concrete_dark");
            c.GlowGround(x, 0.03f, zc, 6f, len * 0.7f, 0x00e5ff, 0.18f);
            c.MapRect("floor", x, zc, w, len + 2 * runLen);
            noLamps.Add(new PRect(x - 6, zDeck0 - runLen - 2, x + 6, zDeck1 + runLen + 2));
        }

        /// <summary>Enclosed glass skybridges between tall buildings facing each other across an x-line road.</summary>
        public static void Skybridges(CityContext c, int max)
        {
            var made = 0;
            var blocks = c.Layout.Blocks;
            foreach (var a in blocks)
            {
                if (made >= max) break;
                if (!c.Chance(0.25f)) continue;
                CityBlock other = null;
                foreach (var b in blocks) if (b.X1 == a.X2 && b.Z1 == a.Z1) { other = b; break; }
                if (other == null) continue;
                foreach (var ba in a.Buildings)
                {
                    if (made >= max || ba.Asset != null || ba.Height < 30 || (ba.Street & CityFace.E) == 0) continue;
                    var ra = ba.PodiumHeight > 0 ? ba.Tower : ba.Foot;
                    foreach (var bb in other.Buildings)
                    {
                        if (bb.Asset != null || bb.Height < 30 || (bb.Street & CityFace.W) == 0) continue;
                        var rb = bb.PodiumHeight > 0 ? bb.Tower : bb.Foot;
                        float z0 = Mathf.Max(ra.Z0, rb.Z0), z1 = Mathf.Min(ra.Z1, rb.Z1);
                        if (z1 - z0 < 10) continue;
                        var y = Mathf.Min(ba.Height, bb.Height) * c.Range(0.45f, 0.7f);
                        if (y < Mathf.Max(ba.PodiumHeight, bb.PodiumHeight) + 6) continue;
                        Bridge(c, ra.X1, rb.X0, (z0 + z1) / 2, y);
                        made++;
                        break;
                    }
                    if (made >= max) break;
                }
            }
        }

        static void Bridge(CityContext c, float x0, float x1, float z, float y)
        {
            var k = c.Kit;
            var xc = (x0 + x1) / 2; var len = x1 - x0;
            if (CityKitAssets.Has("Skybridge_Enclosed_12m"))
            {
                // Kit skybridge spans (12 m along the asset's X) stretched to fit the gap exactly.
                var count = Mathf.Max(1, Mathf.CeilToInt(len / 12f));
                var sx = len / (count * 12f);
                for (var i = 0; i < count; i++)
                {
                    var go = k.Prop("Skybridge_Enclosed_12m", x0 + (i + 0.5f) * len / count, y - 1.6f, z, 0, new Vector3(sx, 1, 1), 0, 0, false);
                    c.Cells.Put(go, CityCuller.Geo);
                    c.KitPieces++;
                }
                return;
            }
            k.Box(xc, y, z, len, 3.2f, 5f, "glass_dark", collide: false);
            k.Box(xc, y - 1.75f, z, len, 0.3f, 5.6f, "metal_dark", collide: false);
            k.Box(xc, y + 1.75f, z, len, 0.3f, 5.6f, "metal_dark", collide: false);
            k.Box(xc, y - 1.95f, z - 2.7f, len, 0.08f, 0.08f, "emit_strip_violet", collide: false, shadow: false);
            k.Box(xc, y - 1.95f, z + 2.7f, len, 0.08f, 0.08f, "emit_strip_cyan", collide: false, shadow: false);
            k.Box(xc, y, z, len - 0.2f, 0.9f, 5.05f, "window_lit_cool", collide: false, shadow: false);
        }

        // ------------------------------------------------------------------ megawall

        /// <summary>
        /// The district boundary: arcology megawall sections (55-95 m, lit window skins, beacons, giant holo panels),
        /// sealed tunnel mouths with barricades where streets meet it, invisible walls, and the Arcology Gate.
        /// </summary>
        public static void Megawall(CityContext c)
        {
            const float wx = CityLayout.WallX, z0 = CityLayout.WallZ0, z1 = CityLayout.WallZ1, t = CityLayout.WallT;
            // north (-z), south (+z), west (-x), east (+x): inner face line, extent, inward normal (prototype).
            WallRun(c, true, z0, -wx - t, wx + t, new Vector2(0, 1));
            WallRun(c, true, z1, -wx - t, wx + t, new Vector2(0, -1));
            WallRun(c, false, -wx, z0, z1, new Vector2(1, 0));
            WallRun(c, false, wx, z0, z1, new Vector2(-1, 0));
            var k = c.Kit;
            k.Wall(0, 10, z0 - 0.5f, 2 * wx, 20, 1);
            k.Wall(0, 10, z1 + 0.5f, 2 * wx, 20, 1);
            k.Wall(-wx - 0.5f, 10, (z0 + z1) / 2, 1, 20, z1 - z0);
            k.Wall(wx + 0.5f, 10, (z0 + z1) / 2, 1, 20, z1 - z0);
            c.MapRect("block", 0, z0 - t / 2, 2 * (wx + t), t);
            c.MapRect("block", 0, z1 + t / 2, 2 * (wx + t), t);
            c.MapRect("block", -wx - t / 2, (z0 + z1) / 2, t, z1 - z0);
            c.MapRect("block", wx + t / 2, (z0 + z1) / 2, t, z1 - z0);
            // Sealed tunnels where the grid would continue.
            for (var i = 1; i < CityLayout.XL.Length - 1; i++)
            {
                Tunnel(c, CityLayout.XL[i], z0, new Vector2(0, 1), i);
                Tunnel(c, CityLayout.XL[i], z1, new Vector2(0, -1), i + 20);
            }
            for (var j = 1; j < CityLayout.ZL.Length - 1; j++)
            {
                Tunnel(c, -wx, CityLayout.ZL[j], new Vector2(1, 0), j + 40);
                if (CityLayout.ZL[j] == CityLayout.AvenueZ) ArcologyGate(c);
                else Tunnel(c, wx, CityLayout.ZL[j], new Vector2(-1, 0), j + 60);
            }
        }

        static void WallRun(CityContext c, bool alongX, float line, float a0, float a1, Vector2 n)
        {
            var k = c.Kit;
            const float t = CityLayout.WallT;
            var a = a0;
            var mat = c.SkinMats[CityContext.SkinWall];
            while (a < a1 - 1)
            {
                var len = Mathf.Min(a1 - a, c.Range(48, 92));
                if (a1 - (a + len) < 30) len = a1 - a;
                var h = c.Range(55, 95);
                var mid = a + len / 2;
                // Mass (behind the inner face line).
                var back = line - (alongX ? n.y : n.x) * t / 2;
                if (alongX) k.Box(mid, h / 2, back, len, h, t, "concrete_dark");
                else k.Box(back, h / 2, mid, t, h, len, "concrete_dark");
                // Street plinth and hazard strip on the inner face.
                float off = 0.2f;
                var px = alongX ? mid : line + n.x * off;
                var pz = alongX ? line + n.y * off : mid;
                k.Box(px, 4f, pz, alongX ? len : 0.4f, 8f, alongX ? 0.4f : len, "metal_dark", collide: false);
                var hx = alongX ? mid : line + n.x * 0.45f;
                var hz = alongX ? line + n.y * 0.45f : mid;
                k.Box(hx, 8.2f, hz, alongX ? len : 0.08f, 0.18f, alongX ? 0.08f : len, "emit_red", collide: false, shadow: false);
                // Lit window skin on the inner face above the plinth.
                Vector3 pa, pb;
                if (alongX) { pa = V(a, 0, line + n.y * 0.05f); pb = V(a + len, 0, line + n.y * 0.05f); }
                else { pa = V(line + n.x * 0.05f, 0, a); pb = V(line + n.x * 0.05f, 0, a + len); }
                var u = a * 1.7f;
                c.Skins.Side(mat, pa, pb, new Vector3(-n.x, 0, n.y), 9f, h - 12f, ref u);
                // Beacons along the top.
                for (var s = a + 8; s < a + len - 4; s += 36)
                {
                    var bx = alongX ? s : line - n.x * 2;
                    var bz = alongX ? line - n.y * 2 : s;
                    c.GlowCross(bx, h + 1.2f, bz, 4.5f, 0xff3030, 1.6f);
                }
                if (c.Chance(0.3f))
                {
                    var hw = Mathf.Min(len - 10, 34f);
                    var hp = alongX ? V(mid, h * 0.55f, line + n.y * 0.6f) : V(line + n.x * 0.6f, h * 0.55f, mid);
                    var face = new Vector3(-n.x, 0, n.y);
                    var holo = NeonKit.HoloPanel(c.Kit.FxRoot, hp, Quaternion.LookRotation(-face), new Vector2(hw, hw * 0.55f), Neon.Pick(c.R), Neon.Pick(c.R), c.R.Next(3), c.R.Next(), 3f);
                    holo.name = "HoloAd";
                }
                a += len;
            }
        }

        static void Tunnel(CityContext c, float x, float z, Vector2 n, int seed)
        {
            var k = c.Kit;
            var alongX = Mathf.Abs(n.y) > 0.5f; // wall runs along x
            float P(float along, float off, bool wantX) => wantX ? (alongX ? x + along : x + n.x * off) : (alongX ? z + n.y * off : z + along);
            // Dark mouth, frame, shutter and warning header.
            k.Box(P(0, 0.05f, true), 5f, P(0, 0.05f, false), alongX ? 14 : 0.1f, 10f, alongX ? 0.1f : 14, "black", collide: false, shadow: false);
            k.Box(P(0, 0.2f, true), 4.4f, P(0, 0.2f, false), alongX ? 13 : 0.15f, 8.6f, alongX ? 0.15f : 13, "corrugated", collide: false);
            foreach (var s in new[] { -7.6f, 7.6f })
                k.Box(P(s, 0.5f, true), 5.5f, P(s, 0.5f, false), alongX ? 1.4f : 1.0f, 11f, alongX ? 1.0f : 1.4f, "concrete", collide: false);
            k.Box(P(0, 0.5f, true), 11.6f, P(0, 0.5f, false), alongX ? 16.6f : 1.0f, 1.4f, alongX ? 1.0f : 16.6f, "concrete", collide: false);
            k.Box(P(0, 1.05f, true), 10.7f, P(0, 1.05f, false), alongX ? 13 : 0.08f, 0.22f, alongX ? 0.08f : 13, "emit_red", collide: false, shadow: false);
            c.GlowWall(P(0, 0.3f, true), 9.2f, P(0, 0.3f, false), n.x, n.y, 16, 5, 0xff2020, 0.35f);
            c.GlowGround(P(0, 3f, true), 0.17f, P(0, 3f, false), alongX ? 14 : 5, alongX ? 5 : 14, 0xff2020, 0.18f);
            // Barricade on the sidewalk in front of it.
            var yaw = alongX ? 0f : Mathf.PI / 2;
            c.Prop("Barrier_Jersey", P(-2.6f, 2.6f, true), Y, P(-2.6f, 2.6f, false), yaw);
            c.Prop((seed & 1) == 0 ? "Barrier_Jersey_Broken" : "Barrier_Jersey", P(1.6f, 2.4f, true), Y, P(1.6f, 2.4f, false), yaw + 0.15f);
            c.Prop("TrafficCone", P(4.6f, 2.2f, true), Y, P(4.6f, 2.2f, false), seed);
            if (seed % 3 == 0)
            {
                var signYaw = Mathf.Atan2(n.x, n.y);
                k.Sign(P(0, 0.7f, true), 13.4f, P(0, 0.7f, false), 9, 1.4f, signYaw, new[] { "SECTOR SEALED" }, fg: 0xff6a5a, bg: 0x1a0606, glow: 1.6f, border: 0xff2020);
            }
        }

        static void ArcologyGate(CityContext c)
        {
            var k = c.Kit;
            const float x = CityLayout.WallX, z = CityLayout.AvenueZ;
            // Pylons stand proud of the wall onto the outer sidewalk; the sealed door sits between them.
            foreach (var side in new[] { -1f, 1f })
            {
                k.Box(x + 4, 55, z + side * 21, 15, 110, 10, "concrete_dark");
                k.Box(x - 3.55f, 55, z + side * 16.4f, 0.1f, 100, 0.3f, "emit_strip_cyan", collide: false, shadow: false);
                k.Box(x - 3.55f, 55, z + side * 25.6f, 0.1f, 100, 0.3f, "emit_strip_violet", collide: false, shadow: false);
                c.GlowCross(x - 3, 112, z + side * 21, 8f, 0xff3030, 1.8f);
            }
            k.Box(x + 4, 102, z, 15, 12, 52, "metal_dark", collide: false);
            k.Box(x - 1, 40, z, 2, 80, 32.2f, "metal_dark");
            k.Box(x - 2.05f, 40, z, 0.1f, 80, 0.5f, "emit_cyan", collide: false, shadow: false);
            for (var i = 0; i < 6; i++) k.Box(x - 2.05f, 8 + i * 12.5f, z, 0.1f, 0.18f, 30, "emit_strip_cyan", collide: false, shadow: false);
            var holo = NeonKit.HoloPanel(c.Kit.FxRoot, V(x - 2.6f, 56, z), Quaternion.LookRotation(new Vector3(-1, 0, 0)), new Vector2(28, 17), Neon.Cyan, Neon.Gold, 1, 9091, 3.2f);
            holo.name = "HoloAd";
            // The Arcology's own billboard advertises the Aether crystal (DreamLayer advert).
            NeonKit.ShowAd(holo, "ad_aethercore");
            k.Sign(x - 2.4f, 13, z, 22, 2.6f, -Mathf.PI / 2, new[] { "ARCOLOGY GATE" }, fg: 0xbfeaff, bg: 0x081018, glow: 1.6f, border: 0x00e5ff);
            k.Sign(x - 2.4f, 10.3f, z, 16, 1.3f, -Mathf.PI / 2, new[] { "RESIDENTS ONLY  ·  SEALED" }, fg: 0xff6a5a, bg: 0x140606, glow: 1.2f, border: 0);
            c.GlowGround(x - 9, 0.03f, z, 10, 34, 0x00e5ff, 0.3f);
            foreach (var s in new[] { -9f, -4f, 4f, 9f }) c.Prop("Barrier_Jersey", x - 3.3f, Y, z + s, Mathf.PI / 2);
        }
    }
}
