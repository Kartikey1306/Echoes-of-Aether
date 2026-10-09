using System.Collections.Generic;
using UnityEngine;
using static EOA.ProtoSpace;

namespace EOA
{
    /// <summary>
    /// Ground-floor storefront runs from the street kit (St_Shop_* modules: noodle bar, pharmacy, cyberware clinic,
    /// pawn / electronics, capsule hotel, arcade, shuttered shop, service bay) lined up edge to edge along building faces
    /// that touch a pavement, plus the wall life above them (AC units, fire escapes, hanging blade signs and lightboxes,
    /// neon glyph columns) and graffiti on the shutters.
    ///
    /// Faces are chosen once per city (<see cref="Prepare"/>): box buildings only (kit buildings, detailed modules and
    /// faces already skinned with the environment kit's facade modules are left alone; a physics probe in front of the
    /// face finds those), nearest the plaza and the avenue first, within an instance budget. The modules are 0.75 m deep
    /// with a 1.75 m canopy at 3.24-3.5 m that encloses the procedural awnings BoxBuildings put on the same faces; if the
    /// street kit has not been built nothing changes (BoxBuildings' shopfronts stay).
    /// </summary>
    public static class CityStorefronts
    {
        public const float Depth = 0.78f;

        public sealed class Run
        {
            public CityBuilding Building;
            public byte Face;
            public float A0, A1;
            public readonly List<(string kind, float s0, float s1)> Modules = new();
        }

        static readonly Dictionary<CityBlock, List<Run>> runs = new();
        static readonly HashSet<(CityBuilding, byte)> chosen = new();
        static bool prepared;
        static CityContext ctx;
        public static int Modules, Faces, WallProps;
        static int wallBudget;

        static readonly (string kind, float w)[] Types =
        {
            ("Noodle", 6), ("Pharmacy", 4), ("Clinic", 6), ("Pawn", 4), ("Capsule", 4), ("Arcade", 6), ("Shuttered", 4),
        };

        // weights per district: noodle, pharmacy, clinic, pawn, capsule, arcade, shuttered
        static readonly float[][] Weights =
        {
            new[] { 3f, 1f, 1f, 2f, 1f, 2.2f, 0.8f },   // NeonMarket
            new[] { 2f, 1f, 2f, 3f, 2f, 0.8f, 2f },     // KowloonStacks
            new[] { 0.6f, 2f, 3f, 0.6f, 2f, 1f, 0.4f }, // ArcologyGate
            new[] { 2.5f, 2f, 1f, 1f, 1.2f, 1f, 1f },   // CanalWard
            new[] { 1f, 0.5f, 1f, 2.5f, 0.6f, 0.4f, 3f }, // FoundryRow
        };

        static readonly Dictionary<string, (uint col, float s)> Glow = new()
        {
            ["Noodle"] = (0xff7a3au, 1.4f), ["Pharmacy"] = (0x5fffa8u, 1.2f), ["Clinic"] = (0x00e5ffu, 1.4f), ["Pawn"] = (0xffc040u, 1.1f),
            ["Capsule"] = (0x9ab8ffu, 1.1f), ["Arcade"] = (0xff2bd6u, 1.6f),
        };

        public static bool Available => CityKitAssets.Has("St_Shop_Noodle_A") && CityKitAssets.Has("St_Shop_Wall_2m");

        public static IReadOnlyList<Run> RunsOf(CityBlock b) => runs.TryGetValue(b, out var l) ? l : null;

        public static void Reset()
        {
            runs.Clear();
            chosen.Clear();
            prepared = false;
            ctx = null;
            Modules = Faces = WallProps = 0;
        }

        static bool KitBuilt(CityBuilding b) => b.Asset != null || b.LandmarkAsset != null || (b.UseKit && b.Kit >= 0 && b.Kit < CityLayout.KitModels.Length && CityKitAssets.Has(CityLayout.KitModels[b.Kit].name));

        static float Priority(PRect f)
        {
            var dx = Mathf.Max(0, Mathf.Abs(f.CX) - CityLayout.ResX);
            var dz = Mathf.Max(0, Mathf.Max(CityLayout.ResZ0 - f.CZ, f.CZ - CityLayout.ResZ1));
            var avenue = Mathf.Abs(f.CZ - CityLayout.AvenueZ) < 40 ? 0.5f : 1f;
            return (dx * dx + dz * dz) * avenue;
        }

        /// <summary>Pick the faces that get storefront runs (all buildings exist by now: probe for facade-kit modules).</summary>
        static void Prepare(CityContext c)
        {
            prepared = true;
            ctx = c;
            if (!Available) return;
            Physics.SyncTransforms();
            var web = Application.platform == RuntimePlatform.WebGLPlayer;
            var budget = web ? 160 : 520;
            wallBudget = web ? 90 : 300;
            var cand = new List<(CityBuilding b, byte f, float len, float pri)>();
            var root = c.Kit.Root;
            foreach (var blk in c.Layout.Blocks)
            foreach (var bd in blk.Buildings)
            {
                if (KitBuilt(bd) || bd.Street == 0) continue;
                foreach (var f in CityFace.All)
                {
                    if ((bd.Street & f) == 0) continue;
                    CityFace.Line(bd.Foot, f, out var a0, out var a1, out var line, out var n, out var alongX);
                    var len = a1 - a0;
                    if (len < 3.9f) continue;
                    // something solid already in front of the face (facade-kit modules, kit buildings)?
                    var mid = (a0 + a1) / 2;
                    var p = alongX ? new Vector3(mid, 2.0f, line + n.y * 0.32f) : new Vector3(line + n.x * 0.32f, 2.0f, mid);
                    var half = alongX ? new Vector3((len - 1.2f) / 2, 0.9f, 0.18f) : new Vector3(0.18f, 0.9f, (len - 1.2f) / 2);
                    if (Physics.CheckBox(root.TransformPoint(V(p)), half, root.rotation, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore)) continue;
                    cand.Add((bd, f, len, Priority(bd.Foot) + (f == CityFace.N || f == CityFace.S ? 0 : 50)));
                }
            }
            cand.Sort((x, y) => x.pri.CompareTo(y.pri));
            foreach (var (b, f, len, _) in cand)
            {
                var est = Mathf.CeilToInt(len / 4.6f);
                if (budget - est < 0) continue;
                budget -= est;
                chosen.Add((b, f));
            }
        }

        /// <summary>Storefront runs and wall dressing for one block (call before the block's pavement furniture).</summary>
        public static void Block(CityContext c, CityBlock blk)
        {
            if (!prepared || ctx != c) { Reset(); Prepare(c); }
            if (!Available) return;
            var list = new List<Run>();
            runs[blk] = list;
            var w = Weights[(int)blk.District];
            foreach (var bd in blk.Buildings)
            foreach (var f in CityFace.All)
            {
                if (!chosen.Contains((bd, f))) continue;
                var run = Face(c, bd, f, w);
                if (run == null) continue;
                list.Add(run);
                WallLife(c, bd, f, run);
            }
        }

        static string PickKind(CityContext c, float[] w)
        {
            var sum = 0f;
            foreach (var x in w) sum += x;
            var r = c.Rand * sum;
            for (var i = 0; i < w.Length; i++) { r -= w[i]; if (r <= 0) return Types[i].kind; }
            return Types[0].kind;
        }

        static Run Face(CityContext c, CityBuilding bd, byte face, float[] weights)
        {
            CityFace.Line(bd.Foot, face, out var a0, out var a1, out var line, out var n, out _);
            var len = a1 - a0 - 0.04f;
            // choose a sequence of modules whose total width can be scaled to the face (0.88 .. 1.14)
            var seq = new List<(string kind, float w)>();
            var total = 0f;
            var guard = 0;
            while (total < len - 1.0f && guard++ < 40)
            {
                var rem = len - total;
                string kind;
                float mw;
                if (rem < 3.5f) { kind = "Wall"; mw = 2f; }
                else
                {
                    kind = PickKind(c, weights);
                    mw = System.Array.Find(Types, t => t.kind == kind).w;
                    if (mw > rem + 0.6f) { kind = c.Chance(0.5f) ? "Pharmacy" : "Shuttered"; mw = 4; }
                    // a plain service bay every few shops (doors, meters; vending machines stand in front of them)
                    if (seq.Count > 0 && seq.Count % 3 == 2 && c.Chance(0.45f)) { kind = "Wall"; mw = 2f; }
                }
                seq.Add((kind, mw));
                total += mw;
            }
            if (seq.Count == 0) return null;
            var scale = len / total;
            if (scale < 0.86f && seq.Count > 1)
            {
                // drop / shrink the last module until it fits
                var last = seq[^1];
                total -= last.w;
                seq.RemoveAt(seq.Count - 1);
                if (len - total >= 1.7f) { seq.Add(("Wall", 2f)); total += 2f; }
                scale = len / total;
            }
            scale = Mathf.Clamp(scale, 0.8f, 1.25f);
            var run = new Run { Building = bd, Face = face, A0 = a0, A1 = a1 };
            var yaw = CityKitAssets.FaceYaw(face);
            var s = a0 + 0.02f + (len - total * scale) / 2;
            var alongX = face == CityFace.N || face == CityFace.S;
            // pick a variant once per face so neighbouring identical shops differ by fascia colour at least
            foreach (var (kind, mw) in seq)
            {
                var width = mw * scale;
                var mid = s + width / 2;
                var name = kind == "Wall" ? "St_Shop_Wall_2m" : $"St_Shop_{kind}_{(c.Chance(0.5f) ? "A" : "B")}";
                if (!CityKitAssets.Has(name)) name = "St_Shop_Wall_2m";
                var p = CityContext.FacePoint(bd.Foot, face, mid, CityLayout.Curb, 0);
                // module X runs along the face: stretch it (±14 %) so the run fills the face edge to edge
                var go = c.Prop(name, p.x, CityLayout.Curb, p.z, yaw);
                go.transform.localScale = new Vector3(scale, 1, 1);
                c.KitPieces++;
                Modules++;
                run.Modules.Add((kind, s, s + width));
                if (Glow.TryGetValue(kind, out var g))
                {
                    var gp = CityContext.FacePoint(bd.Foot, face, mid, 0.18f, 2.0f);
                    c.GlowGround(gp.x, gp.y, gp.z, alongX ? width - 0.6f : 3.0f, alongX ? 3.0f : width - 0.6f, g.col, 0.22f);
                    var np = CityContext.FacePoint(bd.Foot, face, mid, 3.0f, 1.4f);
                    NeonField.Add(V(np), Hex(g.col), g.s, 7f);
                }
                if (kind == "Noodle" && c.Steam.Count < 20 && c.Chance(0.5f))
                    c.Steam.Add(V(CityContext.FacePoint(bd.Foot, face, mid, 1.15f, 0.65f)));
                if (kind == "Shuttered" || (kind == "Wall" && c.Chance(0.5f))) Graffiti(c, bd, face, mid, width, kind == "Shuttered");
                s += width;
            }
            Faces++;
            return run;
        }

        static void Graffiti(CityContext c, CityBuilding bd, byte face, float mid, float width, bool shutter)
        {
            CityFace.Line(bd.Foot, face, out _, out _, out _, out var n, out _);
            var names = shutter ? new[] { "St_Graffiti_Throwup_A", "St_Graffiti_Throwup_B", "St_Graffiti_Tag_A", "St_Graffiti_Tag_B", "St_Graffiti_Tag_C", "St_Graffiti_Tag_D" }
                                : new[] { "St_Posters_D", "St_Posters_E", "St_Stickers_A", "St_Graffiti_Stencil_A", "St_Graffiti_Tag_D" };
            var name = c.Pick(names);
            var off = shutter ? Depth - 0.02f : Depth - 0.04f;
            var p = CityContext.FacePoint(bd.Foot, face, mid + c.Range(-0.3f, 0.3f) * width * 0.3f, shutter ? c.Range(1.2f, 1.9f) : c.Range(1.0f, 1.6f), off);
            var world = c.Kit.Root.TransformPoint(V(p));
            var normal = c.Kit.Root.TransformDirection(new Vector3(-n.x, 0, n.y));
            var parent = c.Cells.Cell(world, CityCuller.Small);
            DecalKit.Place(parent, name, world, normal, 0, Mathf.Min(1f, width / 2.4f) * c.Range(0.8f, 1.0f), 0.3f);
        }

        /// <summary>AC units, fire escapes, hanging signs and neon columns on the wall above a storefront run.</summary>
        static void WallLife(CityContext c, CityBuilding bd, byte face, Run run)
        {
            var top = bd.PodiumHeight > 0 ? bd.PodiumHeight : bd.Height;
            if (top < 9f) return;
            var yaw = CityKitAssets.FaceYaw(face);
            var len = run.A1 - run.A0;
            var used = new List<(float s0, float s1, float y0, float y1)>();
            bool Free(float s0, float s1, float y0, float y1)
            {
                foreach (var u in used) if (s0 < u.s1 && s1 > u.s0 && y0 < u.y1 && y1 > u.y0) return false;
                return s0 > run.A0 + 0.4f && s1 < run.A1 - 0.4f;
            }
            bool Put(string name, float s, float y, float off, float w, float h, int group = CityCuller.Small)
            {
                if (wallBudget <= 0) return false;
                wallBudget--;
                var p = CityContext.FacePoint(bd.Foot, face, s, y, off);
                c.Prop(name, p.x, y, p.z, yaw, group, 1, false);
                used.Add((s - w / 2, s + w / 2, y - h, y + 0.6f));
                WallProps++;
                c.KitPieces++;
                return true;
            }
            // fire escape on taller tenements (two floors per segment)
            if (top > 14f && len > 8f && c.Chance(bd.District == CityDistrict.KowloonStacks || bd.District == CityDistrict.NeonMarket ? 0.4f : 0.2f) && CityKitAssets.Has("St_FireEscape_2F"))
            {
                var s = c.Range(run.A0 + 2.2f, run.A1 - 2.2f);
                var y = CityLayout.GroundH + CityLayout.FloorH;
                for (var k = 0; k < 2 && y + 6.8f < top - 1f; k++, y += 2 * CityLayout.FloorH)
                    Put("St_FireEscape_2F", s, y, 0, 3.2f, 3.0f + (k == 0 ? 2.4f : 0));
            }
            // hanging blade signs / lightboxes over the pavement
            var signs = c.Chance(0.55f) ? 1 + (len > 14 && c.Chance(0.4f) ? 1 : 0) : 0;
            for (var i = 0; i < signs; i++)
            {
                var big = c.Chance(0.6f);
                var name = big ? "St_HangingSign_" + (char)('A' + c.R.Next(6)) : "St_HangingBox_" + (char)('A' + c.R.Next(4));
                if (!CityKitAssets.Has(name)) continue;
                var s = c.Range(run.A0 + 1f, run.A1 - 1f);
                var y = big ? c.Range(7.6f, 8.6f) : c.Range(5.6f, 6.4f);
                if (y > top - 0.5f || !Free(s - 0.4f, s + 0.4f, y - (big ? 3.3f : 1.8f), y)) continue;
                if (!Put(name, s, y, 0, 0.8f, big ? 3.3f : 1.8f, CityCuller.Geo)) continue;
                var gp = CityContext.FacePoint(bd.Foot, face, s, y - 1.5f, 1.9f);
                NeonField.Add(V(gp), Hex(c.Pick(new[] { 0xff2bd6u, 0x00e5ffu, 0xffe14du, 0xff4f9au })), 1.2f, 6f);
            }
            // vertical neon glyph column
            if (top > 13f && c.Chance(0.14f) && CityKitAssets.Has("St_NeonColumn_A"))
            {
                var s = c.Range(run.A0 + 1f, run.A1 - 1f);
                if (Free(s - 0.5f, s + 0.5f, 5.0f, 9.5f))
                {
                    if (Put(c.Chance(0.5f) ? "St_NeonColumn_A" : "St_NeonColumn_B", s, 5.0f, 0, 1f, 0f, CityCuller.Geo))
                        used[^1] = (s - 0.5f, s + 0.5f, 5.0f, 9.5f);
                    NeonField.Add(V(CityContext.FacePoint(bd.Foot, face, s, 7f, 1f)), Hex(0x00e5ff), 1.5f, 8f);
                }
            }
            // split AC units on the floors above the shops
            if (CityKitAssets.Has("St_AC_Unit_Wall"))
            {
                var n = Mathf.Clamp(Mathf.RoundToInt(len / 6f * c.Range(0.4f, 1.3f)), 0, 5);
                var floors = Mathf.Min(bd.Floors - 1, 4);
                for (var i = 0; i < n && floors > 0; i++)
                {
                    var floor = 1 + c.R.Next(floors);
                    var y = CityLayout.GroundH + (floor - 1) * CityLayout.FloorH + 0.9f;
                    var s = c.Range(run.A0 + 0.8f, run.A1 - 0.8f);
                    if (y > top - 1.2f || !Free(s - 0.5f, s + 0.5f, y - 0.5f, y + 0.6f)) continue;
                    Put("St_AC_Unit_Wall", s, y, 0, 1.0f, 0.6f);
                }
            }
        }

        /// <summary>Spots in front of the plain service bays (prototype XZ on the pavement, outward normal) for vending
        /// machines / capsule-toy banks.</summary>
        public static IEnumerable<(Vector3 p, Vector2 n, bool alongX)> ServiceBays(CityBlock blk)
        {
            if (!runs.TryGetValue(blk, out var list)) yield break;
            foreach (var r in list)
            {
                CityFace.Line(r.Building.Foot, r.Face, out _, out _, out _, out var n, out var alongX);
                foreach (var (kind, s0, s1) in r.Modules)
                    if (kind == "Wall") yield return (CityContext.FacePoint(r.Building.Foot, r.Face, (s0 + s1) / 2, CityLayout.Curb, Depth), n, alongX);
            }
        }

        /// <summary>Distance from the face line that is free pavement at `s` on the face of the building containing it
        /// (storefront depth where a run covers it, else 0).</summary>
        public static float WallOffset(CityBlock blk, byte face, float line, float s)
        {
            if (!runs.TryGetValue(blk, out var list)) return 0;
            foreach (var r in list)
            {
                if (r.Face != face) continue;
                CityFace.Line(r.Building.Foot, face, out _, out _, out var l, out _, out _);
                if (Mathf.Abs(l - line) > 0.6f) continue;
                if (s >= r.A0 - 0.3f && s <= r.A1 + 0.3f) return Depth;
            }
            return 0;
        }
    }
}
