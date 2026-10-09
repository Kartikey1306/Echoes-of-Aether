using System.Collections.Generic;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEngine.Rendering;

namespace EOA
{
    /// <summary>
    /// Runtime side of the cyberpunk vehicle kit (Assets/Art/Vehicles, built by EOA → Build Environment Library into
    /// Resources/Env/Props/&lt;Name&gt; with one LODGroup over body + wheel/thruster LODs, and copied to
    /// Resources/Env/vehicles_manifest.json):
    ///   • <see cref="Spec"/> per vehicle from the manifest: size, wheel radii / wheelbase, head- and taillight anchors.
    ///   • traffic mixes (street, parked, wrecks, sky) and per-instance paint (shared veh_paint_* swaps, no material
    ///     copies; moving vehicles may also get a custom MaterialPropertyBlock tint over the pearl base).
    ///   • <see cref="Park"/> for static props (prefabs already ship with their lights off) and <see cref="AddRig"/>
    ///     for moving ones (<see cref="VehicleRig"/>: wheels, steering, thrusters, lights).
    /// Unity metres, vehicle front = +Z, pivot at the ground centre (wheels / pods touch y = 0).
    /// </summary>
    public static class VehicleKit
    {
        public sealed class Spec
        {
            public string Name, Category = "car";
            public Vector3 Size = new(2f, 1.45f, 4.6f), BoundsCenter = new(0, 0.72f, 0);
            /// <summary>Head / tail lamp anchors (left, right; a single-lamp bike repeats its centre).</summary>
            public Vector3 HeadL, HeadR, TailL, TailR;
            public bool SingleLamp;
            public float WheelBase = 2.9f;
            public readonly Dictionary<string, float> WheelRadius = new();
            public bool Flyer => Category == "hover";
            public bool Bike => Category == "bike";
            public bool Van => Category == "van";
            public bool Wreck => Category == "wreck";
            public float Length => Size.z;
            public float Radius(string wheel) => WheelRadius.TryGetValue(wheel, out var r) ? r : 0.36f;
        }

        // ------------------------------------------------------------------ mixes

        /// <summary>Street traffic weights.</summary>
        public static readonly (string name, float weight)[] Street =
            { ("CyberCar_Sedan", 0.27f), ("CyberCar_Taxi", 0.25f), ("CyberCar_Coupe", 0.17f), ("CyberVan", 0.16f), ("CyberBike", 0.15f) };

        /// <summary>Parked cars (static, lights off).</summary>
        public static readonly (string name, float weight)[] Parked =
            { ("CyberCar_Sedan", 0.32f), ("CyberCar_Coupe", 0.17f), ("CyberCar_Taxi", 0.13f), ("CyberVan", 0.24f), ("CyberBike", 0.14f) };

        /// <summary>Sky lanes.</summary>
        public static readonly (string name, float weight)[] Sky = { ("HoverCar_A", 0.42f), ("HoverCar_B", 0.36f), ("HoverTruck", 0.22f) };

        public static readonly string[] Wrecks = { "CyberCar_Sedan_Wrecked", "CyberVan_Burnt" };

        /// <summary>True once the vehicle prefabs are built.</summary>
        public static bool Available => CityKitAssets.Has("CyberCar_Sedan");

        /// <summary>Weighted pick.</summary>
        public static string Pick((string name, float weight)[] table, System.Random r)
        {
            var total = 0f;
            foreach (var e in table) total += e.weight;
            var x = (float)r.NextDouble() * total;
            foreach (var e in table)
            {
                x -= e.weight;
                if (x <= 0) return e.name;
            }
            return table[table.Length - 1].name;
        }

        /// <summary>`count` names in the table's proportions (largest remainder), shuffled: small pools still get the full mix.</summary>
        public static string[] Mix((string name, float weight)[] table, int count, System.Random r)
        {
            var total = 0f;
            foreach (var e in table) total += e.weight;
            var n = new int[table.Length];
            var rem = new float[table.Length];
            var used = 0;
            for (var i = 0; i < table.Length; i++)
            {
                var exact = table[i].weight / total * count;
                n[i] = Mathf.FloorToInt(exact);
                rem[i] = exact - n[i];
                used += n[i];
            }
            while (used < count)
            {
                var best = 0;
                for (var i = 1; i < table.Length; i++) if (rem[i] > rem[best]) best = i;
                n[best]++; rem[best] = -1; used++;
            }
            var list = new List<string>(count);
            for (var i = 0; i < table.Length; i++) for (var k = 0; k < n[i]; k++) list.Add(table[i].name);
            for (var i = list.Count - 1; i > 0; i--) { var j = r.Next(i + 1); (list[i], list[j]) = (list[j], list[i]); }
            return list.ToArray();
        }

        /// <summary>Parked vehicle for a district: wrecks in the grittier districts (Foundry Row, Kowloon Stacks).</summary>
        public static string ParkedName(CityDistrict district, int seed)
        {
            var r = new System.Random(seed);
            var wreck = district == CityDistrict.FoundryRow ? 0.35f : district == CityDistrict.KowloonStacks ? 0.18f : 0f;
            if (r.NextDouble() < wreck) return Wrecks[r.NextDouble() < 0.55 ? 0 : 1];
            return Pick(Parked, r);
        }

        /// <summary>Stable seed from a placement (prototype metres).</summary>
        public static int Seed(float x, float z) => Mathf.RoundToInt(x * 7.31f) * 73856093 ^ Mathf.RoundToInt(z * 5.17f) * 19349663;

        // ------------------------------------------------------------------ specs

        static Dictionary<string, Spec> specs;

        public static Spec Get(string name)
        {
            Load();
            if (specs.TryGetValue(name, out var s)) return s;
            s = new Spec { Name = name };
            Lamps(s, null, true);
            Lamps(s, null, false);
            specs[name] = s;
            return s;
        }

        static void Load()
        {
            if (specs != null) return;
            specs = new Dictionary<string, Spec>();
            var ta = Resources.Load<TextAsset>("Env/vehicles_manifest");
            if (ta == null) return;
            try
            {
                var root = JObject.Parse(ta.text);
                if (root["assets"] is not JArray assets) return;
                foreach (var tok in assets)
                {
                    if (tok is not JObject a) continue;
                    var s = new Spec { Name = (string)a["name"], Category = (string)a["category"] ?? "car" };
                    if (string.IsNullOrEmpty(s.Name)) continue;
                    s.Size = V3(a["size"], s.Size);
                    s.BoundsCenter = V3(a["boundsCenter"], new Vector3(0, s.Size.y / 2, 0));
                    s.SingleLamp = s.Bike;
                    Lamps(s, a["lights"]?["headlight"] as JObject, true);
                    Lamps(s, a["lights"]?["taillight"] as JObject, false);
                    float zMin = float.MaxValue, zMax = float.MinValue;
                    if (a["animatedParts"] is JArray parts)
                        foreach (var p in parts)
                        {
                            if ((string)p["type"] != "wheel") continue;
                            var pn = (string)p["name"];
                            s.WheelRadius[pn] = (float?)p["radius"] ?? 0.36f;
                            var pv = V3(p["pivot"], Vector3.zero);
                            zMin = Mathf.Min(zMin, pv.z); zMax = Mathf.Max(zMax, pv.z);
                        }
                    if (zMax > zMin) s.WheelBase = zMax - zMin;
                    specs[s.Name] = s;
                }
            }
            catch (System.Exception e) { Debug.LogWarning("[vehicles] manifest parse failed: " + e.Message); }
        }

        static void Lamps(Spec s, JObject l, bool head)
        {
            var z = head ? s.Size.z * 0.48f : -s.Size.z * 0.48f;
            var center = V3(l?["center"], new Vector3(0, head ? s.Size.y * 0.45f : s.Size.y * 0.55f, z));
            Vector3 left, right;
            if (!s.SingleLamp && l?["left"] is JArray && l["right"] is JArray && Mathf.Abs(V3(l["left"], center).x - V3(l["right"], center).x) > 0.3f)
            {
                left = V3(l["left"], center);
                right = V3(l["right"], center);
                if (left.x > right.x) (left, right) = (right, left);
            }
            else if (s.SingleLamp) left = right = center;
            else
            {
                // Full-width LED bars: two virtual lamps a third of the width out from the centre.
                var dx = s.Size.x * 0.34f;
                left = center + new Vector3(-dx, 0, 0);
                right = center + new Vector3(dx, 0, 0);
            }
            if (head) { s.HeadL = left; s.HeadR = right; }
            else { s.TailL = left; s.TailR = right; }
        }

        static Vector3 V3(JToken t, Vector3 fallback) =>
            t is JArray a && a.Count >= 3 ? new Vector3((float)a[0], (float)a[1], (float)a[2]) : fallback;

        // ------------------------------------------------------------------ paint

        static readonly string[] PaintCoupe = { "veh_paint_magenta", "veh_paint_cyan", "veh_paint_pearl", "veh_paint_midnight", "veh_paint_gunmetal", "veh_paint_magenta" };
        static readonly string[] PaintSedan = { "veh_paint_midnight", "veh_paint_gunmetal", "veh_paint_pearl", "veh_paint_midnight", "veh_paint_magenta", "veh_paint_cyan", "veh_paint_gunmetal" };
        static readonly string[] PaintVan = { "veh_paint_gunmetal", "veh_paint_pearl", "veh_paint_midnight", "veh_paint_gunmetal" };
        static readonly string[] PaintBike = { "veh_paint_midnight", "veh_paint_magenta", "veh_paint_cyan", "veh_paint_pearl", "veh_paint_gunmetal" };
        static readonly string[] PaintHoverA = { "veh_paint_pearl", "veh_paint_midnight", "veh_paint_gunmetal", "veh_paint_cyan", "veh_paint_pearl" };
        static readonly string[] PaintHoverB = { "veh_paint_cyan", "veh_paint_magenta", "veh_paint_pearl", "veh_paint_midnight" };
        static readonly string[] PaintTruck = { "veh_paint_gunmetal", "veh_paint_pearl", "veh_paint_midnight" };

        static string[] Palette(string vehicle) => vehicle switch
        {
            "CyberCar_Coupe" => PaintCoupe,
            "CyberCar_Sedan" => PaintSedan,
            "CyberVan" => PaintVan,
            "CyberBike" => PaintBike,
            "HoverCar_A" => PaintHoverA,
            "HoverCar_B" => PaintHoverB,
            "HoverTruck" => PaintTruck,
            _ => null, // taxi livery and wrecks keep their paint
        };

        /// <summary>Custom colours laid over the pearl paint with a MaterialPropertyBlock (moving vehicles only).</summary>
        public static readonly Color[] Tints =
        {
            new(0.62f, 0.05f, 0.07f), new(0.05f, 0.36f, 0.24f), new(0.95f, 0.38f, 0.06f), new(0.3f, 0.1f, 0.55f),
            new(0.08f, 0.2f, 0.62f), new(0.55f, 0.6f, 0.62f),
        };

        /// <summary>Neon / underglow colours.</summary>
        public static readonly Color[] Neons =
        {
            new(1f, 0.1f, 0.72f), new(0f, 0.8f, 1f), new(0.62f, 0.25f, 1f), new(0.25f, 1f, 0.45f), new(1f, 0.5f, 0.06f),
            new(1f, 0.12f, 0.16f), new(0.85f, 0.92f, 1f),
        };

        static readonly Dictionary<string, Material> matCache = new();
        static readonly Dictionary<string, string> primary = new();

        public static Material Mat(string name)
        {
            if (!matCache.TryGetValue(name, out var m)) matCache[name] = m = Resources.Load<Material>("Env/Materials/" + name);
            return m;
        }

        /// <summary>The body's main paint slot (veh_paint_* with the most triangles on LOD0), cached per vehicle.</summary>
        public static string PrimaryPaint(GameObject go, Spec spec)
        {
            if (primary.TryGetValue(spec.Name, out var p)) return p;
            p = null;
            var best = 0u;
            foreach (var mf in go.GetComponentsInChildren<MeshFilter>(true))
            {
                if (mf.gameObject.name != spec.Name + "_LOD0" || mf.sharedMesh == null || !mf.TryGetComponent<Renderer>(out var r)) continue;
                var mats = r.sharedMaterials;
                for (var i = 0; i < mats.Length && i < mf.sharedMesh.subMeshCount; i++)
                {
                    if (mats[i] == null || !mats[i].name.StartsWith("veh_paint_")) continue;
                    var n = mf.sharedMesh.GetIndexCount(i);
                    if (n > best) { best = n; p = mats[i].name; }
                }
            }
            primary[spec.Name] = p;
            return p;
        }

        /// <summary>Swap the primary paint slot (every LOD and part) for another shared veh_paint_* material.</summary>
        public static void SetPaint(GameObject go, Spec spec, string paint)
        {
            var from = PrimaryPaint(go, spec);
            var to = Mat(paint);
            if (from == null || to == null || from == paint) return;
            foreach (var r in go.GetComponentsInChildren<Renderer>(true))
            {
                var mats = r.sharedMaterials;
                var changed = false;
                for (var i = 0; i < mats.Length; i++)
                    if (mats[i] != null && mats[i].name == from) { mats[i] = to; changed = true; }
                if (changed) r.sharedMaterials = mats;
            }
        }

        /// <summary>Random paint from the vehicle's palette (null palette: keeps its livery). Returns the chosen material name.</summary>
        public static string RandomPaint(GameObject go, Spec spec, System.Random r)
        {
            var pal = Palette(spec.Name);
            if (pal == null) return PrimaryPaint(go, spec);
            var paint = pal[r.Next(pal.Length)];
            SetPaint(go, spec, paint);
            return paint;
        }

        // ------------------------------------------------------------------ placement

        /// <summary>
        /// Static parked vehicle (already placed): random paint, lights stay off (the prefab default), parked bikes lean
        /// on their stand. No per-frame cost.
        /// </summary>
        public static void Park(GameObject go, string name, int seed)
        {
            if (go == null || !CityKitAssets.Has(name)) return;
            var spec = Get(name);
            var r = new System.Random(seed);
            if (!spec.Wreck) RandomPaint(go, spec, r);
            if (spec.Bike) go.transform.localRotation *= Quaternion.Euler(0, 0, 8.5f);
        }

        /// <summary>Moving vehicle: random paint (sometimes a custom tint), neon colours and a <see cref="VehicleRig"/>.</summary>
        public static VehicleRig AddRig(GameObject go, string name, System.Random r, bool customTints = true)
        {
            var spec = Get(name);
            Color? tint = null;
            if (!spec.Wreck && Palette(spec.Name) != null)
            {
                if (customTints && Mat("veh_paint_pearl") != null && r.NextDouble() < 0.3)
                {
                    SetPaint(go, spec, "veh_paint_pearl");
                    tint = Tints[r.Next(Tints.Length)];
                }
                else RandomPaint(go, spec, r);
            }
            var rig = go.GetComponent<VehicleRig>() ?? go.AddComponent<VehicleRig>();
            rig.Setup(spec, r, tint);
            return rig;
        }

        /// <summary>A sky-lane flyer (no colliders, no shadows at altitude) with its rig; null when the kit is not built.</summary>
        public static GameObject SkyCar(Transform parent, int seed)
        {
            if (!CityKitAssets.Has("HoverCar_A")) return null;
            var r = new System.Random(seed);
            var name = Pick(Sky, r);
            if (!CityKitAssets.Has(name)) name = "HoverCar_A";
            var go = EnvProps.Instantiate(name, parent, false);
            foreach (var rd in go.GetComponentsInChildren<Renderer>(true)) rd.shadowCastingMode = ShadowCastingMode.Off;
            var rig = AddRig(go, name, r);
            rig.FullDistance = 160f;
            rig.CullDistance = 900f;
            rig.Headlights = VehicleRig.Lamp.On;
            return go;
        }

        // ------------------------------------------------------------------ environment

        static float nightAt = -10f;
        static bool night = true;

        /// <summary>Dark zone lighting (the night city; false in the dawn epilogue): headlights, cones and pools on.</summary>
        public static bool Night
        {
            get
            {
                if (Time.unscaledTime - nightAt < 1.5f && nightAt >= 0) return night;
                nightAt = Time.unscaledTime;
                if (RenderSettings.fog) night = RenderSettings.fogColor.grayscale < 0.3f;
                else night = RenderSettings.sun == null || RenderSettings.sun.intensity < 2.5f;
                return night;
            }
        }

        /// <summary>Neutral (near white) LED emission map so neon / underglow slots can take any colour.</summary>
        public static Texture NeutralLed
        {
            get
            {
                if (neutralLed == null)
                {
                    var m = Mat("veh_headlight") ?? Mat("veh_headlight_off");
                    neutralLed = m != null && m.HasProperty("_EmissionMap") ? m.GetTexture("_EmissionMap") : null;
                }
                return neutralLed;
            }
        }

        static Texture neutralLed;
    }
}
