using System;
using System.Collections.Generic;
using UnityEngine;
using static EOA.ProtoSpace;

namespace EOA
{
    /// <summary>
    /// Port of the prototype's seeded generator <c>rng(seed)</c> (mulberry32, MathUtil.ts). The sequence is
    /// bit-identical to the JS one, so layouts that depend on it (market stalls, crate stacks, rubble) land on the
    /// same spots as in the prototype. Call order matters: mirror the TS argument evaluation order exactly.
    /// </summary>
    public sealed class PzRng
    {
        uint s;

        public PzRng(double seed) { s = ToUint32(seed); }

        /// <summary>JS ToUint32 (seed &gt;&gt;&gt; 0).</summary>
        static uint ToUint32(double d)
        {
            if (double.IsNaN(d) || double.IsInfinity(d)) return 0;
            var m = Math.Truncate(d) % 4294967296.0;
            if (m < 0) m += 4294967296.0;
            return (uint)m;
        }

        public double NextD()
        {
            unchecked
            {
                s += 0x6d2b79f5u;
                var t = s;
                t = (t ^ (t >> 15)) * (t | 1u);
                t ^= t + (t ^ (t >> 7)) * (t | 61u);
                return (t ^ (t >> 14)) / 4294967296.0;
            }
        }

        public float Next() => (float)NextD();
        public float Range(float a, float b) => (float)(a + (b - a) * NextD());
        /// <summary>Index for <c>r.pick(arr)</c> with arr.length == n.</summary>
        public int Pick(int n) => (int)Math.Floor(NextD() * n);
        public bool Chance(float p) => NextD() < p;
    }

    /// <summary>
    /// Plaza/rooftops set-dressing kit: replaces the prototype's procedural prop helpers (Props.ts) with the Blender
    /// environment assets (Art/Environment/manifest.json) while keeping each helper's footprint, collision and light
    /// placement. Every coordinate is prototype space (see <see cref="ProtoSpace"/>); yaw in radians.
    /// </summary>
    public sealed class PzKit
    {
        public readonly LevelKit B;
        /// <summary>Unbatched parent for props that move after the build (static batching freezes everything under the prop root).</summary>
        public readonly Transform Dynamic;

        public PzKit(LevelKit b)
        {
            B = b;
            var go = new GameObject("Dynamic");
            go.layer = CombatLayers.World;
            go.transform.SetParent(b.Root, false);
            Dynamic = go.transform;
        }

        // ------------------------------------------------------------------ basics

        /// <summary>Prototype <c>rot(x, z, yaw, lx, lz)</c>: local XZ offset rotated by yaw around (x, z). Returns (x, z).</summary>
        public static Vector2 Rot(float x, float z, float yaw, float lx, float lz)
        {
            float c = Mathf.Cos(yaw), s = Mathf.Sin(yaw);
            return new Vector2(x + lx * c + lz * s, z - lx * s + lz * c);
        }

        /// <summary>
        /// Prototype-space position of a manifest anchor (Unity-local metres, e.g. a lamp's 'light') of a prop placed
        /// at (x, y, z) with yaw and uniform scale. Unity local X is mirrored into prototype local X.
        /// </summary>
        public static Vector3 Anchor(float x, float y, float z, float yaw, float scale, float ux, float uy, float uz)
        {
            var p = Rot(x, z, yaw, -ux * scale, uz * scale);
            return new Vector3(p.x, y + uy * scale, p.y);
        }

        public GameObject Prop(string name, float x, float y, float z, float yaw = 0, float scale = 1, bool collide = true, float rotX = 0, float rotZ = 0) =>
            B.Prop(name, x, y, z, yaw, scale, rotX, rotZ, collide);

        /// <summary>Prop that will be animated: kept out of the static batch.</summary>
        public GameObject DynamicProp(string name, float x, float y, float z, float yaw = 0, float scale = 1, bool collide = false, float rotX = 0, float rotZ = 0)
        {
            var go = B.Prop(name, x, y, z, yaw, scale, rotX, rotZ, collide);
            go.transform.SetParent(Dynamic, false);
            return go;
        }

        /// <summary>Re-orient a placed prop: yaw, then a local pitch (about its X axis) and roll (about its Z axis), Unity degrees.</summary>
        public static void Tilt(GameObject go, float yaw, float pitchDeg, float rollDeg)
        {
            if (go == null) return;
            go.transform.localRotation = YawQ(yaw) * Quaternion.AngleAxis(pitchDeg, Vector3.right) * Quaternion.AngleAxis(rollDeg, Vector3.forward);
        }

        /// <summary>Collider-only vertical cylinder (centre + full height) that blocks movement and the camera.</summary>
        public void CylCollider(float x, float y, float z, float r, float h, int seg = 24)
        {
            var go = new GameObject("col_cyl");
            go.layer = CombatLayers.World;
            go.transform.SetParent(B.Root, false);
            go.transform.localPosition = V(x, y, z);
            go.AddComponent<MeshCollider>().sharedMesh = FxMesh.Cylinder(r, r, h, seg, true);
        }

        /// <summary>Thin pole collider (prototype cylinders on lamps, masts, shelter poles) from its base.</summary>
        public void PoleCollider(float x, float y, float z, float r, float h) => B.SolidCollider(x, y + h / 2, z, r * 2, h, r * 2);

        /// <summary>Flat quad with 0..1 UVs (fit materials: lit windows, screens), merged into the static geometry. Faces prototype +Z rotated by yaw.</summary>
        public void Panel(float x, float y, float z, float w, float h, float yaw, string mat, float pitch = 0)
        {
            var rot = YawQ(yaw) * Quaternion.AngleAxis(-pitch * Mathf.Rad2Deg, Vector3.right) * Quaternion.Euler(0, 180, 0);
            B.AddMesh(LevelKit.QuadMesh, mat, new Vector3(x, y, z), rot, new Vector3(w, h, 1), shadow: false);
        }

        /// <summary>Hanging cable between two points with a parabolic sag (prototype P.pipe with 'cable').</summary>
        public void Cable(float x1, float y1, float z1, float x2, float y2, float z2, float radius, float sag, string mat = "cable", int segs = 6)
        {
            var mesh = FxMesh.Cylinder(radius, radius, 1f, 5, false);
            var prev = new Vector3(x1, y1, z1);
            for (var i = 1; i <= segs; i++)
            {
                var t = i / (float)segs;
                var p = new Vector3(Mathf.Lerp(x1, x2, t), Mathf.Lerp(y1, y2, t) - sag * 4 * t * (1 - t), Mathf.Lerp(z1, z2, t));
                var dir = V(p) - V(prev);
                var len = dir.magnitude;
                if (len > 0.001f)
                    B.AddMesh(mesh, mat, (prev + p) / 2, Quaternion.FromToRotation(Vector3.up, dir / len), new Vector3(1, len, 1), shadow: false);
                prev = p;
            }
        }

        /// <summary>Rain puddle: a few overlapping water discs just above the surface.</summary>
        public void Puddle(float x, float y, float z, float r, int seed)
        {
            var rr = new PzRng(seed);
            var n = 2 + rr.Pick(2);
            for (var i = 0; i < n; i++)
            {
                var a = rr.Range(0, Mathf.PI * 2);
                var d = rr.Range(0, r * 0.5f);
                var s = r * rr.Range(0.45f, 0.8f);
                B.Cyl(x + Mathf.Cos(a) * d, y + 0.006f + i * 0.001f, z + Mathf.Sin(a) * d, s, s, 0.01f, "puddle", 20, collide: false, shadow: false);
            }
        }

        // ------------------------------------------------------------------ street props

        public struct Lamp
        {
            public Light Light;
            public GameObject Halo;
            public float Base;
            public Vector3 Head;
        }

        /// <summary>
        /// Street lamp (P.streetLight): StreetLight asset (arm toward local +Z), light pool decal, halo and an optional
        /// real point light at the manifest 'light' anchor. Dead lamps use the buckled StreetLight_Broken.
        /// </summary>
        public Lamp StreetLamp(float x, float y, float z, float yaw, bool on = true, bool light = true, float intensity = 1, uint color = 0xffc98a)
        {
            var lamp = new Lamp();
            if (!on)
            {
                Prop("StreetLight_Broken", x, y, z, yaw, 1, false);
                PoleCollider(x, y, z, 0.12f, 2.4f);
                lamp.Head = new Vector3(x, y + 5.6f, z);
                return lamp;
            }
            Prop("StreetLight", x, y, z, yaw, 1, false);
            PoleCollider(x, y, z, 0.12f, 6.2f);
            var a = Anchor(x, y, z, yaw, 1, 0, 6.3f, 1.78f);
            lamp.Head = a;
            B.GlowDecal(a.x, y + 0.03f, a.z, 8, color, 0.22f * intensity);
            lamp.Halo = B.GlowSprite(a.x, a.y - 0.12f, a.z, 1.2f, color, 0.45f);
            if (light)
            {
                // Downward wide spot (a street lamp throws its light down: pools on the paving, walls lit from below,
                // and a shadowed spot costs one shadow slice where a point light costs six).
                lamp.Light = B.SpotLight(a.x, a.y - 0.35f, a.z, a.x, a.y - 10f, a.z, color, 140 * intensity, 22, 75f * Mathf.Deg2Rad, 0.2f, 1.7f);
                if (lamp.Light != null) lamp.Base = lamp.Light.intensity;
            }
            return lamp;
        }

        static readonly string[] CarByPaint = { "Car_Sedan", "Car_Sedan_Wrecked", "Car_Sedan_Wrecked", "Car_Sedan_Red" };
        /// <summary>Vehicle-kit replacements per slot (abandoned sedans in gunmetal / candy paint, lights off; the wrecks).</summary>
        static readonly string[] KitByPaint = { "CyberCar_Sedan", "CyberCar_Sedan_Wrecked", "CyberCar_Sedan_Wrecked", "CyberCar_Sedan" };
        static readonly string[] KitPaint = { "veh_paint_gunmetal", null, null, "veh_paint_magenta" };

        /// <summary>Abandoned car (P.car). The prototype body's long axis was local +X; the asset's front is +Z, hence +PI/2.</summary>
        public GameObject Car(float x, float y, float z, float yaw, int seed)
        {
            var r = new PzRng(seed);
            var paint = r.Pick(CarByPaint.Length);
            var tilt = r.Range(-0.05f, 0.05f);
            r.Chance(0.3f); // lowered onto its rims in the prototype (visual only)
            var kit = CityKitAssets.Has(KitByPaint[paint]);
            var go = Prop(kit ? KitByPaint[paint] : CarByPaint[paint], x, y, z, yaw + Mathf.PI / 2, 1, !kit);
            if (kit)
            {
                // Same blocking as the old Car_Sedan* props (their box collider), whatever the kit body's size.
                var bc = go.AddComponent<BoxCollider>();
                bc.center = new Vector3(0, 0.75f, 0);
                bc.size = new Vector3(1.84f, 1.3f, 4.3f);
                go.layer = CombatLayers.World;
                if (KitPaint[paint] != null) VehicleKit.SetPaint(go, VehicleKit.Get(KitByPaint[paint]), KitPaint[paint]);
            }
            Tilt(go, yaw + Mathf.PI / 2, tilt * Mathf.Rad2Deg, 0);
            return go;
        }

        /// <summary>
        /// Transit bus / tram pod (P.bus): 11 m bus, prototype box collider (2.7 x 2.8 x 11, top at 3.15 m: a collectible
        /// sits on the roof) oriented with the bus.
        /// </summary>
        public GameObject Bus(string name, float x, float y, float z, float yaw, int seed)
        {
            var r = new PzRng(seed);
            var tilt = r.Range(-0.06f, 0.06f);
            var by = yaw + Mathf.PI / 2;
            var go = Prop(name, x, y, z, by, 1, false);
            Tilt(go, by, tilt * Mathf.Rad2Deg, 0);
            B.AddBoxCollider(V(x, y + 1.75f, z), new Vector3(2.7f, 2.8f, 11f), YawQ(by), CombatLayers.World);
            return go;
        }

        /// <summary>Concrete jersey barrier (long axis along local X, as in the prototype).</summary>
        public GameObject Barrier(float x, float y, float z, float yaw, bool broken = false) =>
            Prop(broken ? "Barrier_Jersey_Broken" : "Barrier_Jersey", x, y, z, yaw);

        public GameObject Bench(float x, float y, float z, float yaw) => Prop("Bench_Street", x, y, z, yaw);

        public GameObject TrashBin(float x, float y, float z, bool tipped) =>
            tipped ? Prop("TrashBin_Tipped", x, y, z, x * 0.3f) : Prop("TrashBin", x, y, z, 0);

        /// <summary>
        /// Rubble scatter (P.debris): the same seeded layout as the prototype; the first (largest) piece becomes a rubble
        /// pile, pieces that collided in the prototype (size &gt; 0.45) become large chunks, the rest small chunks / scrap.
        /// </summary>
        public void Debris(float x, float y, float z, float radius, int count, int seed, bool dark = false, Func<float, float, float> ground = null)
        {
            var r = new PzRng(seed);
            for (var i = 0; i < count; i++)
            {
                var a = r.Range(0, Mathf.PI * 2);
                var d = Mathf.Sqrt(r.Next()) * radius;
                var s = r.Range(0.15f, 0.6f) * (i == 0 ? 2 : 1);
                r.Range(0.8f, 1.6f); r.Range(0.4f, 0.9f); r.Range(0.7f, 1.3f); // piece proportions (prototype boxes)
                var rust = !r.Chance(0.8f);
                var yaw = r.Range(0, 3);
                var rx = r.Range(-0.3f, 0.3f);
                var rz = r.Range(-0.3f, 0.3f);
                float px = x + Mathf.Cos(a) * d, pz = z + Mathf.Sin(a) * d;
                var py = ground != null ? ground(px, pz) : y;
                if (i == 0)
                {
                    Prop(dark ? "Debris_Pile_Dark" : radius >= 2.8f ? "Debris_Pile_B" : "Debris_Pile_A", px, py, pz, yaw);
                    continue;
                }
                if (s > 0.45f) Prop("Rubble_Chunk_L", px, py, pz, yaw, s / 0.55f, true, rx * 0.5f, rz * 0.5f);
                else if (rust && s > 0.3f) Prop("Scrap_Metal", px, py, pz, yaw, 0.6f, false);
                else if (rust) Prop("Rebar_Cluster", px, py, pz, yaw, 0.8f, false);
                else Prop("Rubble_Chunk_S", px, py, pz, yaw, s / 0.25f, false, rx, rz);
            }
        }

        static readonly string[] CrateByMat = { "Crate_Cargo", "Crate_Cargo_Red", "Crate_Cargo_Yellow", "Crate_Wood" };

        void Crate(string name, float x, float y, float z, float s, float yaw) =>
            Prop(name, x, y, z, yaw, name == "Crate_Wood" ? s / 0.82f : s);

        /// <summary>Crate stack (P.crateStack) with the prototype's seeded sizes and offsets.</summary>
        public void CrateStack(float x, float y, float z, float yaw, int seed)
        {
            var r = new PzRng(seed);
            var s = r.Range(0.7f, 1.0f);
            Crate(CrateByMat[r.Pick(4)], x, y, z, s, yaw);
            if (r.Chance(0.7f))
            {
                var o = Rot(x, z, yaw, s * 1.25f, r.Range(-0.2f, 0.2f));
                var y2 = yaw + r.Range(-0.3f, 0.3f);
                Crate(r.Pick(2) == 0 ? "Crate_Cargo" : "Crate_Wood", o.x, y, o.y, s * 0.9f, y2);
            }
            if (r.Chance(0.5f))
            {
                var dx = r.Range(-0.1f, 0.1f);
                var dz = r.Range(-0.1f, 0.1f);
                var y3 = yaw + r.Range(-0.4f, 0.4f);
                Crate("Crate_Cargo", x + dx, y + s, z + dz, s * 0.75f, y3);
            }
        }

        /// <summary>
        /// Railing run (P.railing) from (x1, z1) to (x2, z2): Railing_2m modules (long axis X, so yaw + PI/2) plus end
        /// posts, optionally sloping from y to y2; the invisible blocking wall of the prototype when collide.
        /// </summary>
        public void Railing(float x1, float z1, float x2, float z2, float y, bool collide = true, float y2 = float.NaN)
        {
            var len = Mathf.Sqrt((x2 - x1) * (x2 - x1) + (z2 - z1) * (z2 - z1));
            if (len < 0.01f) return;
            var yaw = Mathf.Atan2(x2 - x1, z2 - z1);
            var yEnd = float.IsNaN(y2) ? y : y2;
            var slopeDeg = Mathf.Atan2(yEnd - y, len) * Mathf.Rad2Deg;
            var n = Mathf.Max(1, Mathf.RoundToInt(len / 2f));
            for (var i = 0; i < n; i++)
            {
                var t = (i + 0.5f) / n;
                var go = Prop("Railing_2m", x1 + (x2 - x1) * t, y + (yEnd - y) * t, z1 + (z2 - z1) * t, yaw + Mathf.PI / 2, 1, false);
                if (Mathf.Abs(slopeDeg) > 0.01f) Tilt(go, yaw + Mathf.PI / 2, 0, slopeDeg);
            }
            Prop("Railing_Post", x1, y, z1, yaw, 1, false);
            Prop("Railing_Post", x2, yEnd, z2, yaw, 1, false);
            if (collide) B.Wall((x1 + x2) / 2, y + 0.6f, (z1 + z2) / 2, 0.15f, 1.2f, len, yaw);
        }

        /// <summary>Terminal / save kiosk (P.terminal). Returns the prototype screen centre (x, z) for interactables.</summary>
        public Vector2 Terminal(float x, float y, float z, float yaw)
        {
            Prop("Terminal_Kiosk", x, y, z, yaw);
            return Rot(x, z, yaw, 0, 0.19f);
        }

        public GameObject AcUnit(float x, float y, float z, float yaw) => Prop("AC_Unit", x, y, z, yaw);

        public GameObject Vent(float x, float y, float z) => Prop("Roof_Vent", x, y, z);

        /// <summary>Antenna mast (P.antenna) of height h: closest mast asset scaled to h, thin pole collider, red beacon halo.</summary>
        public GameObject Antenna(float x, float y, float z, float h, float yaw = 0, bool collide = true)
        {
            var (name, nominal) = h >= 8 ? ("Antenna_Mast_10m", 10f) : h >= 4 ? ("Antenna_Mast_5m", 5f) : ("Antenna_Mast_3m", 3f);
            var sc = h / nominal;
            Prop(name, x, y, z, yaw, sc, false);
            if (collide) PoleCollider(x, y, z, 0.12f, h);
            return B.GlowSprite(x, y + h + 0.1f, z, 0.6f, 0xff3030, 1.2f);
        }

        /// <summary>Rooftop water tank (P.waterTank): stand legs and tank colliders as in the prototype.</summary>
        public void WaterTank(float x, float y, float z, float yaw = 0)
        {
            Prop("WaterTank", x, y, z, yaw, 1, false);
            foreach (var (lx, lz) in new[] { (-1f, -1f), (1f, -1f), (-1f, 1f), (1f, 1f) }) PoleCollider(x + lx, y, z + lz, 0.08f, 2.4f);
            CylCollider(x, y + 3.6f, z, 1.6f, 2.4f);
        }

        // ------------------------------------------------------------------ buildings

        static readonly string[] BuildingMats = { "concrete", "plaster", "concrete_dark", "brick" };
        const float FloorH = 3.4f, ModuleW = 4f, FacadeOut = 0.16f;

        public struct ShopFront
        {
            public Vector3 Pos;
            public float Yaw;
        }

        /// <summary>
        /// City block (P.building): solid mass box (collider) with the prototype's seeded material, parapet with coping,
        /// and one-floor facade modules (shop fronts at street level, windows above; a few lit or smashed) on the faces
        /// that look into the playable area. faces: any of "nswe". Returns the street-level shop fronts.
        /// </summary>
        public List<ShopFront> Building(float x, float z, float w, float d, float h, int seed, float lit, bool broken, string faces,
            bool collide = true, bool collideFacades = true, bool roofClutter = true, float y0 = 0)
        {
            if (BespokeBlock(x, z, w, d, h, seed, faces, collide, collideFacades, y0)) return new List<ShopFront>();
            var r = new PzRng(seed);
            var mat = BuildingMats[r.Pick(4)];
            var style = mat == "brick" ? "brick" : mat == "plaster" ? "plaster" : "concrete";
            B.Box(x, y0 + h / 2, z, w, h, d, mat, collide: collide);
            Parapet(x - w / 2, z - d / 2, x + w / 2, z + d / 2, y0 + h, mat, 0.9f);
            var shops = new List<ShopFront>();
            var floors = Mathf.FloorToInt((h - 1) / FloorH);
            foreach (var face in faces)
            {
                var alongX = face == 'n' || face == 's';
                var len = alongX ? w : d;
                var n = Mathf.FloorToInt(len / ModuleW);
                if (n < 1) continue;
                var start = -n * ModuleW / 2 + ModuleW / 2;
                var yaw = face switch { 's' => 0f, 'n' => Mathf.PI, 'e' => Mathf.PI / 2, _ => -Mathf.PI / 2 };
                for (var f = 0; f < floors; f++)
                {
                    for (var c = 0; c < n; c++)
                    {
                        var t = start + c * ModuleW;
                        float px, pz;
                        switch (face)
                        {
                            case 's': px = x + t; pz = z + d / 2 + FacadeOut; break;
                            case 'n': px = x + t; pz = z - d / 2 - FacadeOut; break;
                            case 'e': px = x + w / 2 + FacadeOut; pz = z + t; break;
                            default: px = x - w / 2 - FacadeOut; pz = z + t; break;
                        }
                        var py = y0 + f * FloorH;
                        var roll = r.Next();
                        if (f == 0)
                        {
                            Prop(broken && roll < 0.55f ? "Facade_Shop_Broken" : "Facade_Shop", px, py, pz, yaw, 1, collideFacades);
                            shops.Add(new ShopFront { Pos = new Vector3(px, py, pz), Yaw = yaw });
                            continue;
                        }
                        string module, overlay = null;
                        var warm = roll < lit;
                        var cool = !warm && roll < lit * 1.3f;
                        switch (style)
                        {
                            case "brick":
                                module = broken && roll > 0.88f ? "Facade_Brick_Window_Broken" : "Facade_Brick_Window";
                                overlay = warm ? "win_warm" : cool ? "win_cool" : null;
                                break;
                            case "plaster":
                                module = warm ? "Facade_Plaster_Window_Lit" : roll > 0.94f ? "Facade_Plaster_Plain" : "Facade_Plaster_Window";
                                overlay = cool ? "win_cool" : broken && roll > 0.88f && roll <= 0.94f ? "black" : null;
                                break;
                            default:
                                module = "Facade_Concrete_Window";
                                overlay = warm ? "win_warm" : cool ? "win_cool" : broken && roll > 0.9f ? "black" : null;
                                break;
                        }
                        Prop(module, px, py, pz, yaw, 1, collideFacades);
                        if (overlay != null)
                        {
                            // Window opening 1.6 x 1.6 (sill 0.9): cover the recessed glass (local z -0.04) just in front of it.
                            var o = Rot(px, pz, yaw, 0, -0.026f);
                            Panel(o.x, py + 1.7f, o.y, 1.56f, 1.56f, yaw, overlay);
                        }
                    }
                }
            }
            if (roofClutter) RoofClutter(x, z, w, d, y0 + h, r);
            return shops;
        }

        /// <summary>
        /// Plaza blocks (PlazaZone.BuildBlocks, seed 100 + index) have bespoke CityLandmarks models (Plaza_Block_NN:
        /// Neon Market style west / market streets, Arcology Gate corporate style east) with the block's exact mass
        /// footprint and roof height. When the prefab exists and matches, it replaces the box + facade modules + parapet +
        /// roof clutter. Gameplay geometry is unchanged: the same mass box collider, and the same 0.3 m facade collider
        /// slab on the faces that look into the playable area (where the old facade modules' colliders stood).
        /// Its lit shops are part of the model, so no ShopFronts are returned (LitShop then has nothing to do).
        /// </summary>
        /// <summary>Plaza blocks built from bespoke prefabs (report).</summary>
        public static int BespokeBlocks;

        bool BespokeBlock(float x, float z, float w, float d, float h, int seed, string faces, bool collide, bool collideFacades, float y0)
        {
            var name = $"Plaza_Block_{seed - 100:00}";
            if (seed < 100 || !CityKitAssets.Has(name)) return false;
            var info = EnvProps.Get(name);
            // Footprint check against the manifest (mass footprint + facade projections < 3 m): never put a model on the wrong block.
            if (info == null || Mathf.Abs(info.Size.y - h) > 60f || info.Size.x < w - 0.5f || info.Size.z < d - 0.5f || info.Size.x > w + 6f || info.Size.z > d + 6f) return false;
            KitEmission.Fix(Prop(name, x, y0, z, 0, 1, false));
            if (collide) B.SolidCollider(x, y0 + h / 2, z, w, h, d);
            byte bits = 0;
            foreach (var face in faces)
            {
                var alongX = face == 'n' || face == 's';
                var len = alongX ? w : d;
                var n = Mathf.FloorToInt(len / ModuleW);
                bits |= face switch { 's' => CityFace.S, 'n' => CityFace.N, 'e' => CityFace.E, _ => CityFace.W };
                if (n < 1 || !collideFacades) continue;
                var floors = Mathf.FloorToInt((h - 1) / FloorH);
                var fh = floors * FloorH;
                const float t = 0.3f, off = FacadeOut;
                var span = n * ModuleW;
                switch (face)
                {
                    case 's': B.SolidCollider(x, y0 + fh / 2, z + d / 2 + off, span, fh, t); break;
                    case 'n': B.SolidCollider(x, y0 + fh / 2, z - d / 2 - off, span, fh, t); break;
                    case 'e': B.SolidCollider(x + w / 2 + off, y0 + fh / 2, z, t, fh, span); break;
                    default: B.SolidCollider(x - w / 2 - off, y0 + fh / 2, z, t, fh, span); break;
                }
            }
            // The open city's avenue dressing must not stack procedural shopfronts on this model.
            PlazaFacades.Add(x, z, (byte)(CityFace.S | CityFace.N | CityFace.E | CityFace.W));
            if (seed == 100) BespokeBlocks = 0;
            BespokeBlocks++;
            return true;
        }

        /// <summary>Parapet walls (no collision, as in the prototype) with a steel coping and corner blocks.</summary>
        public void Parapet(float x0, float z0, float x1, float z1, float top, string mat, float ph)
        {
            float cx = (x0 + x1) / 2, cz = (z0 + z1) / 2, w = x1 - x0, d = z1 - z0;
            B.Box(cx, top + ph / 2, z0 + 0.12f, w, ph, 0.24f, mat, collide: false);
            B.Box(cx, top + ph / 2, z1 - 0.12f, w, ph, 0.24f, mat, collide: false);
            B.Box(x0 + 0.12f, top + ph / 2, cz, 0.24f, ph, d, mat, collide: false);
            B.Box(x1 - 0.12f, top + ph / 2, cz, 0.24f, ph, d, mat, collide: false);
            B.Box(cx, top + ph + 0.03f, z0 + 0.12f, w + 0.04f, 0.06f, 0.32f, "metal_dark", collide: false, shadow: false);
            B.Box(cx, top + ph + 0.03f, z1 - 0.12f, w + 0.04f, 0.06f, 0.32f, "metal_dark", collide: false, shadow: false);
            B.Box(x0 + 0.12f, top + ph + 0.03f, cz, 0.32f, 0.06f, d, "metal_dark", collide: false, shadow: false);
            B.Box(x1 - 0.12f, top + ph + 0.03f, cz, 0.32f, 0.06f, d, "metal_dark", collide: false, shadow: false);
        }

        static readonly string[] Clutter = { "AC_Unit", "Roof_Vent", "Roof_TurbineVent", "AC_Unit" };

        /// <summary>Silhouette dressing on unreachable roofs (no collision).</summary>
        void RoofClutter(float x, float z, float w, float d, float top, PzRng r)
        {
            var count = Mathf.Clamp(Mathf.RoundToInt(w * d / 160f), 1, 4);
            for (var i = 0; i < count; i++)
            {
                var px = x + r.Range(-w / 2 + 2, w / 2 - 2);
                var pz = z + r.Range(-d / 2 + 2, d / 2 - 2);
                Prop(Clutter[r.Pick(Clutter.Length)], px, top, pz, r.Pick(4) * Mathf.PI / 2, 1, false);
            }
            var roll = r.Next();
            if (roll < 0.25f) Prop("Antenna_Mast_5m", x + r.Range(-w / 4, w / 4), top, z + r.Range(-d / 4, d / 4), r.Range(0, 6.28f), 1, false);
            else if (roll < 0.4f && w > 11 && d > 11) Prop("WaterTank", x + r.Range(-w / 4, w / 4), top, z + r.Range(-d / 4, d / 4), r.Range(0, 6.28f), 1, false);
        }

        static readonly (string name, float roof)[] Blocks =
            { ("Building_Block_D", 14.2f), ("Building_Block_A", 17.6f), ("Building_Block_B", 24.4f), ("Building_Block_C", 31.2f) };

        /// <summary>Distant skyline block (no collision): the background building asset closest in height, scaled to h.</summary>
        public GameObject SkylineBlock(float x, float y, float z, float h, float yaw)
        {
            var best = Blocks[0];
            foreach (var b in Blocks) if (Mathf.Abs(b.roof - h) < Mathf.Abs(best.roof - h)) best = b;
            return Prop(best.name, x, y, z, yaw, Mathf.Clamp(h / best.roof, 0.8f, 2.2f), false);
        }

        // ------------------------------------------------------------------ text

        /// <summary>Text on an existing surface (monument plaque, asset screens): legacy TextMesh, readable from prototype +Z rotated by yaw, tilted back by pitch.</summary>
        public GameObject Label(float x, float y, float z, float yaw, float pitch, string text, float w, float h, uint color)
        {
            var go = new GameObject("Label");
            go.transform.SetParent(B.Root, false);
            go.transform.localPosition = V(x, y, z);
            go.transform.localRotation = YawQ(yaw) * Quaternion.AngleAxis(-pitch * Mathf.Rad2Deg, Vector3.right) * Quaternion.Euler(0, 180, 0);
            var font = WorldText.Font;
            var tm = go.AddComponent<TextMesh>();
            tm.text = text;
            tm.font = font;
            tm.fontSize = 96;
            tm.characterSize = Mathf.Min(h * 0.62f, w / Mathf.Max(4, text.Length) * 1.6f) * 0.1f;
            tm.anchor = TextAnchor.MiddleCenter;
            tm.alignment = TextAlignment.Center;
            tm.color = Hex(color);
            var mr = go.GetComponent<MeshRenderer>();
            mr.sharedMaterial = WorldText.Material;
            mr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            return go;
        }
    }
}
