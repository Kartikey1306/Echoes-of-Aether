using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;
using Random = UnityEngine.Random;

namespace EOA
{
    /// <summary>
    /// Street traffic of the open city: a pool of kit vehicles (CyberCar_Sedan / Taxi / Coupe, CyberVan, CyberBike in
    /// <see cref="VehicleKit.Street"/> proportions) driving the lane graph around the player (right-hand traffic),
    /// obeying the intersection signals, keeping distance to the vehicle ahead and stopping for the player and
    /// pedestrians. Each vehicle has a <see cref="VehicleRig"/> (wheel roll and steering, bike lean, emissive head /
    /// brake lights, neon and underglow in a per-instance colour, van hazards when stopped, taxi holo sign) and, at
    /// night, one merged additive mesh for its headlights (lens flares, fake volumetric cones, a light pool on the
    /// road) plus tail-lamp flares that brighten under braking: no realtime lights. Each car carries a kinematic
    /// collider (IgnoreCamera layer: blocks characters, not the camera) so nobody walks through it. Also drives the
    /// signal heads. The per-frame update allocates nothing.
    /// </summary>
    public sealed class Traffic : MonoBehaviour
    {
        sealed class Car
        {
            public GameObject Go;
            public Transform T;
            public VehicleRig Rig;
            public Renderer HeadFx, TailFx;
            public VehicleHealth Health;
            public bool Active, Turning, Committed, Braking, Lit;
            public int Lane, Next;
            public float S, Speed, Cruise, CruiseMin, CruiseMax, TurnLen, Length, Wait, Stun;
            public Vector3 P0, P1, P2, Pos, Fwd;
        }

        public const float SpawnMin = 70f, SpawnMax = 185f, DespawnR = 215f;
        const float Accel = 2.6f, Brake = 7f, Gap = 4.5f;

        RoadGraph g;
        Crowd crowd;
        readonly List<Car> cars = new();
        int target;
        float spawnTimer;
        bool filled;
        readonly Vector3[] pedBuf = new Vector3[48];
        int pedCount;
        static Material headFxMat, tailMat, tailBrakeMat;
        static readonly Dictionary<string, (Mesh head, Mesh tail)> fxMeshes = new();
        // Signal heads: per node, renderers for (Z red, Z green, X red, X green).
        Renderer[][] heads;
        int[] headPhase;

        public int Pool => cars.Count;
        /// <summary>The lane graph the cars drive (dev captures).</summary>
        public RoadGraph Graph => g;
        public int ActiveCount { get; private set; }

        public static int Budget()
        {
            var fx = G.Settings?.Data?.Graphics?.Effects ?? "high";
            var n = fx == "low" ? 8 : fx == "medium" ? 12 : 16;
            if (Application.platform == RuntimePlatform.WebGLPlayer) n = Mathf.Min(n, 10);
            return n;
        }

        // ------------------------------------------------------------------ creation

        static Material Glow(Color c, float k)
        {
            var m = FxMaterials.Particle(true, FxMaterials.Glow, true);
            m.name = "car_glow";
            m.SetColor("_BaseColor", FxMaterials.Hdr(c, k));
            return m;
        }

        static void EnsureFxMats()
        {
            if (headFxMat == null) headFxMat = Glow(new Color(0.86f, 0.93f, 1f), 3.2f);
            if (tailMat == null) tailMat = Glow(new Color(1f, 0.08f, 0.1f), 1.6f);
            if (tailBrakeMat == null) tailBrakeMat = Glow(new Color(1f, 0.08f, 0.1f), 4.2f);
        }

        /// <summary>
        /// Night light fx of a vehicle outside the pool (the player's car): headlight flares / beams / road pool and
        /// tail flares, as the traffic uses (renderers start disabled; <see cref="TailFx"/> swaps the brake look).
        /// </summary>
        public static (Renderer head, Renderer tail) LightFx(Transform car, VehicleKit.Spec spec)
        {
            EnsureFxMats();
            var fx = FxMeshes(spec);
            return (AddFx(car, "HeadlightFx", fx.head, headFxMat), AddFx(car, "TaillightFx", fx.tail, tailMat));
        }

        public static void TailFx(Renderer tail, bool braking)
        {
            if (tail != null) tail.sharedMaterial = braking ? tailBrakeMat : tailMat;
        }

        /// <summary>The player's car hit this traffic car: it stops dead for a few seconds (and honks).</summary>
        public static void Bump(Collider col)
        {
            if (col == null) return;
            var tr = col.GetComponentInParent<Traffic>();
            if (tr == null) return;
            var rb = col.attachedRigidbody;
            var root = rb != null ? rb.transform : col.transform;
            foreach (var c in tr.cars)
            {
                if (!c.Active || (c.T != root && !root.IsChildOf(c.T))) continue;
                var first = c.Stun <= 0f;
                c.Stun = 3.5f;
                c.Speed = 0f;
                if (first) G.Audio?.Play("car_horn", c.Pos + Vector3.up, 0.8f, Random.Range(0.85f, 1.1f));
                return;
            }
        }

        public static Traffic Create(Transform parent, RoadGraph graph, Crowd crowd, int count, CityCells cells)
        {
            var go = new GameObject("Traffic");
            go.transform.SetParent(parent, false);
            var tr = go.AddComponent<Traffic>();
            tr.g = graph;
            tr.crowd = crowd;
            EnsureFxMats();
            var kit = VehicleKit.Available;
            var rng = new System.Random(4127);
            var mix = kit ? VehicleKit.Mix(VehicleKit.Street, count, rng) : null;
            for (var i = 0; i < count; i++)
            {
                var name = kit ? mix[i] : i % 3 == 1 ? "Car_Sedan_Red" : "Car_Sedan";
                if (kit && !CityKitAssets.Has(name)) name = "CyberCar_Sedan";
                var car = EnvProps.Instantiate(name, go.transform, true);
                car.name = "Car_" + i + "_" + name;
                var spec = VehicleKit.Get(name);
                var c = new Car { Go = car, T = car.transform, Length = spec.Length };
                // Cruise speeds (m/s): bikes quicker, vans slower.
                (c.CruiseMin, c.CruiseMax) = spec.Bike ? (10.5f, 14f) : spec.Van ? (8f, 10.5f) : (9f, 12.5f);
                foreach (var col in car.GetComponentsInChildren<Collider>(true)) col.gameObject.layer = CombatLayers.IgnoreCamera;
                var rb = car.AddComponent<Rigidbody>();
                rb.isKinematic = true;
                rb.useGravity = false;
                c.Health = VehicleHealth.Attach(car, spec, true);
                c.Rig = kit ? VehicleKit.AddRig(car, name, rng) : car.AddComponent<VehicleRig>();
                if (!kit) c.Rig.Setup(spec, rng);
                var fx = FxMeshes(spec);
                c.HeadFx = AddFx(car.transform, "HeadlightFx", fx.head, headFxMat);
                c.TailFx = AddFx(car.transform, "TaillightFx", fx.tail, tailMat);
                car.SetActive(false);
                tr.cars.Add(c);
            }
            tr.target = count;
            tr.BuildSignals(cells);
            return tr;
        }

        static Renderer AddFx(Transform parent, string name, Mesh mesh, Material m)
        {
            var go = new GameObject(name);
            go.transform.SetParent(parent, false);
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var r = go.AddComponent<MeshRenderer>();
            r.sharedMaterial = m;
            r.shadowCastingMode = ShadowCastingMode.Off;
            r.receiveShadows = false;
            r.lightProbeUsage = LightProbeUsage.Off;
            r.reflectionProbeUsage = ReflectionProbeUsage.Off;
            r.enabled = false;
            return r;
        }

        // ------------------------------------------------------------------ light fx meshes

        /// <summary>
        /// Per vehicle type: the headlight fx (lens flare quads at the lamps, a soft additive cone per lamp angled a few
        /// degrees down and fading out over ~13 m, and an elongated light pool on the road ahead) and the tail flares,
        /// each merged into one mesh. Vertex alpha scales the shared glow material (the cone uses the glow texture's
        /// bright centre; flares and pool its radial falloff).
        /// </summary>
        static (Mesh head, Mesh tail) FxMeshes(VehicleKit.Spec s)
        {
            if (fxMeshes.TryGetValue(s.Name, out var m)) return m;
            var v = new List<Vector3>();
            var uv = new List<Vector2>();
            var col = new List<Color>();
            var tri = new List<int>();
            var lamps = s.SingleLamp ? new[] { s.HeadL } : new[] { s.HeadL, s.HeadR };
            var flare = s.Bike ? 0.4f : 0.5f;
            foreach (var p in lamps)
            {
                Quad(v, uv, col, tri, p + new Vector3(0, 0, 0.06f), Vector3.right * flare, Vector3.up * flare * 0.55f, 1f);
                Cone(v, uv, col, tri, p + new Vector3(0, 0, 0.1f), Quaternion.Euler(5.5f, 0, 0) * Vector3.forward, s.Bike ? 11f : 13f, s.Bike ? 1.8f : 2.3f, s.Bike ? 0.05f : 0.042f);
            }
            // Light pool on the road ahead (flat, slightly above the asphalt).
            var zc = s.HeadL.z + (s.Bike ? 5.5f : 6.5f);
            var pool = new Vector3(0, 0.035f, zc);
            Quad(v, uv, col, tri, pool, Vector3.right * (s.Bike ? 2.2f : 2.9f), Vector3.forward * (s.Bike ? 5f : 6.5f), s.Bike ? 0.07f : 0.09f, true);
            var head = Build("car_head_fx", v, uv, col, tri);
            v.Clear(); uv.Clear(); col.Clear(); tri.Clear();
            var tails = s.SingleLamp ? new[] { s.TailL } : new[] { s.TailL, s.TailR };
            foreach (var p in tails) Quad(v, uv, col, tri, p + new Vector3(0, 0, -0.06f), Vector3.left * 0.34f, Vector3.up * 0.19f, 1f);
            var tail = Build("car_tail_fx", v, uv, col, tri);
            fxMeshes[s.Name] = m = (head, tail);
            return m;
        }

        static Mesh Build(string name, List<Vector3> v, List<Vector2> uv, List<Color> col, List<int> tri)
        {
            var mesh = new Mesh { name = name };
            mesh.SetVertices(v);
            mesh.SetUVs(0, uv);
            mesh.SetColors(col);
            mesh.SetTriangles(tri, 0);
            mesh.RecalculateBounds();
            return mesh;
        }

        /// <summary>Centred quad spanning ±a, ±b (double-sided material), full glow UVs, vertex alpha `alpha`.</summary>
        static void Quad(List<Vector3> v, List<Vector2> uv, List<Color> col, List<int> tri, Vector3 c, Vector3 a, Vector3 b, float alpha, bool flipUp = false)
        {
            var k = v.Count;
            v.Add(c - a - b); v.Add(c + a - b); v.Add(c + a + b); v.Add(c - a + b);
            uv.Add(new Vector2(0, 0)); uv.Add(new Vector2(1, 0)); uv.Add(new Vector2(1, 1)); uv.Add(new Vector2(0, 1));
            var cc = new Color(1, 1, 1, alpha);
            for (var i = 0; i < 4; i++) col.Add(cc);
            if (flipUp) tri.AddRange(new[] { k, k + 2, k + 1, k, k + 3, k + 2 });
            else tri.AddRange(new[] { k, k + 1, k + 2, k, k + 2, k + 3 });
        }

        /// <summary>Open cone from `apex` along `dir`: rings at increasing distance, alpha fading to zero at the far end.</summary>
        static void Cone(List<Vector3> v, List<Vector2> uv, List<Color> col, List<int> tri, Vector3 apex, Vector3 dir, float len, float radius, float alpha)
        {
            const int seg = 14;
            float[] ts = { 0f, 0.12f, 0.35f, 0.65f, 1f };
            float[] fade = { 1f, 0.8f, 0.45f, 0.18f, 0f };
            var rot = Quaternion.LookRotation(dir);
            var start = v.Count;
            for (var ri = 0; ri < ts.Length; ri++)
            {
                var r = Mathf.Lerp(0.09f, radius, ts[ri]);
                for (var i = 0; i < seg; i++)
                {
                    var an = i / (float)seg * Mathf.PI * 2f;
                    // Slightly flattened (wider than tall) like a real low beam.
                    v.Add(apex + rot * new Vector3(Mathf.Cos(an) * r * 1.25f, Mathf.Sin(an) * r * 0.7f, ts[ri] * len));
                    uv.Add(new Vector2(0.5f, 0.5f));
                    col.Add(new Color(1, 1, 1, alpha * fade[ri]));
                }
            }
            for (var ri = 0; ri < ts.Length - 1; ri++)
                for (var i = 0; i < seg; i++)
                {
                    int a = start + ri * seg + i, b = start + ri * seg + (i + 1) % seg, c = a + seg, d = b + seg;
                    tri.Add(a); tri.Add(c); tri.Add(b);
                    tri.Add(b); tri.Add(c); tri.Add(d);
                }
        }

        // ------------------------------------------------------------------ signals

        static Material red, green;

        void BuildSignals(CityCells cells)
        {
            if (red == null) red = EnvMaterials.EmissiveInstance(new Color(1f, 0.12f, 0.1f), 4f);
            if (green == null) green = EnvMaterials.EmissiveInstance(new Color(0.2f, 1f, 0.55f), 3.5f);
            var housing = EnvMaterials.Get("metal_dark");
            var box = FxMesh.Box(0.22f, 0.22f, 0.22f);
            var pole = FxMesh.Box(0.16f, 5.2f, 0.16f);
            var head = FxMesh.Box(0.42f, 1.1f, 0.42f);
            heads = new Renderer[g.Nodes][];
            headPhase = new int[g.Nodes];
            var kitNodes = KitSignals(cells);
            var corner = CityLayout.RoadHalf + 1.1f;
            for (var n = 0; n < g.Nodes; n++)
            {
                if (kitNodes.Contains(n)) continue;
                var root = new GameObject("Signal");
                root.layer = CombatLayers.World;
                var c = g.Node[n];
                root.transform.position = c;
                var r = new Renderer[4];
                // Two diagonal corner poles; each carries one lamp pair per traffic axis.
                var lamps = new List<Vector3>[4];
                for (var k = 0; k < 4; k++) lamps[k] = new List<Vector3>(2);
                foreach (var s in new[] { -1f, 1f })
                {
                    var p = c + new Vector3(s * corner, 0, s * corner);
                    Part(root.transform, pole, housing, p + new Vector3(0, CityLayout.Curb + 2.6f, 0));
                    Part(root.transform, head, housing, p + new Vector3(0, CityLayout.Curb + 4.9f, 0));
                    lamps[0].Add(p + new Vector3(0, CityLayout.Curb + 5.2f, -s * 0.22f));
                    lamps[1].Add(p + new Vector3(0, CityLayout.Curb + 4.7f, -s * 0.22f));
                    lamps[2].Add(p + new Vector3(-s * 0.22f, CityLayout.Curb + 5.2f, 0));
                    lamps[3].Add(p + new Vector3(-s * 0.22f, CityLayout.Curb + 4.7f, 0));
                }
                for (var k = 0; k < 4; k++)
                {
                    var go = new GameObject(k % 2 == 0 ? "Red" : "Green");
                    go.transform.SetParent(root.transform, false);
                    var mesh = new Mesh { name = "signal_lamps" };
                    var ci = new CombineInstance[lamps[k].Count];
                    for (var i = 0; i < ci.Length; i++) ci[i] = new CombineInstance { mesh = box, transform = Matrix4x4.Translate(lamps[k][i] - c) };
                    mesh.CombineMeshes(ci, true, true);
                    go.AddComponent<MeshFilter>().sharedMesh = mesh;
                    var mr = go.AddComponent<MeshRenderer>();
                    mr.sharedMaterial = k % 2 == 0 ? red : green;
                    mr.shadowCastingMode = ShadowCastingMode.Off;
                    r[k] = mr;
                }
                heads[n] = r;
                headPhase[n] = -1;
                cells.Put(root, CityCuller.Small);
            }
        }

        sealed class KitPole { public int Node, Axis, State = -1; public Renderer[] R; public Material[][][] States; }
        readonly List<KitPole> poles = new();

        /// <summary>
        /// The kit's mast-arm signals at the intersections nearest the plaza (one pole per traffic axis, facing an
        /// inbound lane from the far-left corner with the arm over the road); their red/amber/green lens slots are
        /// switched with the signal phase. Returns the nodes that got them.
        /// </summary>
        HashSet<int> KitSignals(CityCells cells)
        {
            var set = new HashSet<int>();
            if (!CityKitAssets.Has("Traffic_Light_Cyber")) return set;
            var max = Application.platform == RuntimePlatform.WebGLPlayer ? 6 : 12;
            var order = new List<int>();
            for (var n = 0; n < g.Nodes; n++) order.Add(n);
            var center = new Vector3(0, 0, 20);
            order.Sort((a, b) => (g.Node[a] - center).sqrMagnitude.CompareTo((g.Node[b] - center).sqrMagnitude));
            var off = EnvMaterials.Get("glass_dark");
            var corner = CityLayout.RoadHalf + 1.2f;
            for (var i = 0; i < order.Count && set.Count < max; i++)
            {
                var n = order[i];
                var made = 0;
                for (var axis = 0; axis < 2; axis++)
                {
                    var lane = -1;
                    for (var l = 0; l < g.Lanes; l++) if (g.LaneTo[l] == n && g.LaneAxis[l] == axis) { lane = l; break; }
                    if (lane < 0) continue;
                    var d = g.LaneDir[lane];
                    var right = Vector3.Cross(Vector3.up, d);
                    var go = EnvProps.Instantiate("Traffic_Light_Cyber", transform, true);
                    go.transform.SetPositionAndRotation(g.Node[n] + d * corner - right * corner + Vector3.up * CityLayout.Curb, Quaternion.LookRotation(-d));
                    var pole = new KitPole { Node = n, Axis = axis, R = go.GetComponentsInChildren<Renderer>(true) };
                    pole.States = new Material[pole.R.Length][][];
                    for (var r = 0; r < pole.R.Length; r++)
                    {
                        var baseMats = pole.R[r].sharedMaterials;
                        pole.States[r] = new Material[3][];
                        for (var st = 0; st < 3; st++)
                        {
                            var arr = (Material[])baseMats.Clone();
                            for (var k = 0; k < arr.Length; k++)
                            {
                                var nm = arr[k] != null ? arr[k].name : "";
                                // State 0 green, 1 amber, 2 red.
                                if (nm.StartsWith("emit_green") && st != 0) arr[k] = off;
                                else if (nm.StartsWith("emit_amber") && st != 1) arr[k] = off;
                                else if (nm.StartsWith("emit_red") && st != 2) arr[k] = off;
                            }
                            pole.States[r][st] = arr;
                        }
                    }
                    poles.Add(pole);
                    cells.Put(go, CityCuller.Small);
                    made++;
                }
                if (made > 0) set.Add(n);
            }
            return set;
        }

        void UpdatePoles(float t)
        {
            for (var i = 0; i < poles.Count; i++)
            {
                var p = poles[i];
                var ph = g.Phase(p.Node, t);
                int st;
                if (p.Axis == 1) st = ph < 10f ? 0 : ph < 13f ? 1 : 2;
                else st = ph >= 15f && ph < 25f ? 0 : ph >= 25f && ph < 28f ? 1 : 2;
                if (st == p.State) continue;
                p.State = st;
                for (var r = 0; r < p.R.Length; r++) if (p.R[r] != null) p.R[r].sharedMaterials = p.States[r][st];
            }
        }

        static void Part(Transform parent, Mesh mesh, Material m, Vector3 world)
        {
            var go = new GameObject("part");
            go.transform.SetParent(parent, false);
            go.transform.position = world;
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var r = go.AddComponent<MeshRenderer>();
            r.sharedMaterial = m;
            r.shadowCastingMode = ShadowCastingMode.Off;
        }

        void UpdateSignals(float t)
        {
            UpdatePoles(t);
            for (var n = 0; n < heads.Length; n++)
            {
                if (heads[n] == null) continue;
                var ph = g.PhaseIndex(n, t);
                if (ph == headPhase[n]) continue;
                headPhase[n] = ph;
                var r = heads[n];
                // Axis Z lamps (indices 0, 1) are green in phase 0, axis X lamps (2, 3) in phase 2.
                r[0].enabled = ph != 0; r[1].enabled = ph == 0;
                r[2].enabled = ph != 2; r[3].enabled = ph == 2;
            }
        }


        // ------------------------------------------------------------------ spawning

        static Camera Cam()
        {
            var rig = G.Manager != null ? G.Manager.Cam : null;
            return rig != null && rig.Cam != null ? rig.Cam : Camera.main;
        }

        static bool InView(Camera cam, Vector3 p)
        {
            if (cam == null) return false;
            var v = cam.WorldToViewportPoint(p + Vector3.up);
            return v.z > 0 && v.x > -0.2f && v.x < 1.2f && v.y > -0.2f && v.y < 1.2f;
        }

        bool TrySpawn(Car c, Vector3 player, Camera cam, bool initial)
        {
            for (var tries = 0; tries < 14; tries++)
            {
                var lane = Random.Range(0, g.Lanes);
                var len = g.LaneLen[lane];
                if (len < 20) continue;
                var s = Random.Range(6f, len - 6f);
                var pos = g.LanePoint(lane, s);
                var d = Vector3.Distance(pos, new Vector3(player.x, 0, player.z));
                if (d < (initial ? 25f : SpawnMin) || d > SpawnMax) continue;
                if (!initial && d < 120f && InView(cam, pos)) continue;
                var clear = true;
                for (var i = 0; i < cars.Count && clear; i++)
                    if (cars[i].Active && (cars[i].Pos - pos).sqrMagnitude < 18f * 18f) clear = false;
                var pcs = Driving.Cars;
                for (var i = 0; i < pcs.Count && clear; i++)
                    if (pcs[i] != null && (pcs[i].transform.position - pos).sqrMagnitude < 18f * 18f) clear = false;
                if (!clear) continue;
                c.Lane = lane; c.S = s; c.Turning = false; c.Committed = false; c.Next = -1; c.Wait = 0;
                c.Cruise = Random.Range(c.CruiseMin, c.CruiseMax);
                c.Speed = c.Cruise * 0.8f;
                c.Pos = pos; c.Fwd = g.LaneDir[lane];
                c.Active = true;
                c.Stun = 0f;
                c.Go.SetActive(true);
                c.Health?.Revive();
                c.T.SetPositionAndRotation(pos, Quaternion.LookRotation(c.Fwd));
                c.Rig.ResetMotion();
                SetLit(c, VehicleKit.Night);
                return true;
            }
            return false;
        }

        /// <summary>Night: headlight flares / cones / pool and tail flares on (the emissive lamps are the rig's).</summary>
        static void SetLit(Car c, bool lit)
        {
            c.Lit = lit;
            if (c.HeadFx != null) c.HeadFx.enabled = lit;
            if (c.TailFx != null) c.TailFx.enabled = lit;
        }

        // ------------------------------------------------------------------ update

        void Update()
        {
            var m = G.Manager;
            if (g == null || m == null || m.Mode != GameMode.Play || m.Paused) return;
            var t = Time.time;
            if (heads != null) UpdateSignals(t);
            if (cars.Count == 0) return;
            var player = m.Player;
            if (player == null) return;
            var pp = player.Position;
            var dt = Mathf.Min(Time.deltaTime, 0.1f);
            var cam = Cam();
            pedCount = crowd != null ? crowd.ActivePositions(pedBuf) : 0;
            var night = VehicleKit.Night;

            var active = 0;
            for (var i = 0; i < cars.Count; i++)
            {
                var c = cars[i];
                if (!c.Active) continue;
                // Blown up (VehicleDamage left a wreck): back to the pool.
                if (!c.Go.activeSelf || (c.Health != null && c.Health.State == VehicleHealth.Stage.Wrecked)) { c.Active = false; c.Go.SetActive(false); continue; }
                var dx = c.Pos.x - pp.x; var dz = c.Pos.z - pp.z;
                // Far away, or stuck for a long time (gridlock behind a parked player), and out of view: recycle.
                if ((dx * dx + dz * dz > DespawnR * DespawnR || c.Wait > 25f) && !InView(cam, c.Pos)) { c.Active = false; c.Go.SetActive(false); continue; }
                if (c.Lit != night) SetLit(c, night);
                active++;
            }
            spawnTimer -= dt;
            if (spawnTimer <= 0)
            {
                spawnTimer = filled ? 0.5f : 0f;
                var budget = filled ? 1 : target;
                for (var i = 0; i < cars.Count && active < target && budget > 0; i++)
                {
                    if (cars[i].Active) continue;
                    if (TrySpawn(cars[i], pp, cam, !filled)) { active++; budget--; }
                    else break;
                }
                filled = true;
            }
            ActiveCount = active;
            for (var i = 0; i < cars.Count; i++) if (cars[i].Active) Drive(cars[i], pp, dt, t);
        }

        void ChooseNext(Car c)
        {
            var node = g.LaneTo[c.Lane];
            var outs = g.Out[node];
            var rev = g.Reverse[c.Lane];
            var count = 0;
            for (var i = 0; i < outs.Length; i++) if (outs[i] != rev) count++;
            if (count == 0) { c.Next = rev; return; }
            // Straight on more often than turning.
            var straight = -1;
            for (var i = 0; i < outs.Length; i++) if (outs[i] != rev && Vector3.Dot(g.LaneDir[outs[i]], g.LaneDir[c.Lane]) > 0.9f) straight = outs[i];
            if (straight >= 0 && Random.value < 0.55f) { c.Next = straight; return; }
            var k = Random.Range(0, count);
            for (var i = 0; i < outs.Length; i++)
            {
                if (outs[i] == rev) continue;
                if (k-- == 0) { c.Next = outs[i]; return; }
            }
        }

        /// <summary>Distance to the nearest obstacle in the car's path (other cars, the player, pedestrians).</summary>
        float Ahead(Car c, Vector3 player)
        {
            var best = float.MaxValue;
            var fwd = c.Fwd;
            var half = c.Length * 0.5f;
            for (var i = 0; i < cars.Count; i++)
            {
                var o = cars[i];
                if (o == c || !o.Active) continue;
                var rel = o.Pos - c.Pos; rel.y = 0;
                var along = Vector3.Dot(rel, fwd);
                if (along <= 0 || along > 26f) continue;
                var lat = Mathf.Abs(rel.x * fwd.z - rel.z * fwd.x);
                if (lat > 2.0f || Vector3.Dot(o.Fwd, fwd) < 0.2f) continue;
                var d = along - half - o.Length * 0.5f;
                if (d < best) best = d;
            }
            if (!Driving.Active) Check(player, 1.9f, ref best);
            // Cars the player drives or left in the street: their nose, middle and tail.
            var pcs = Driving.Cars;
            for (var i = 0; i < pcs.Count; i++)
            {
                var pc = pcs[i];
                if (pc == null) continue;
                var pt = pc.transform;
                var ph = pc.Spec.Length * 0.42f;
                var pf = pt.forward; pf.y = 0;
                var w = 1.1f + pc.Spec.Size.x * 0.5f;
                Check(pt.position + pf * ph, w, ref best);
                Check(pt.position, w, ref best);
                Check(pt.position - pf * ph, w, ref best);
            }
            // Burnt wrecks left in the street.
            var vd = VehicleDamage.Instance;
            if (vd != null)
                for (var i = 0; i < vd.WreckCount; i++)
                {
                    if (!vd.WreckAt(i, out var wp, out var wf, out var wh, out var ww)) continue;
                    wf.y = 0;
                    Check(wp + wf * wh * 0.8f, 1.1f + ww, ref best);
                    Check(wp, 1.1f + ww, ref best);
                    Check(wp - wf * wh * 0.8f, 1.1f + ww, ref best);
                }
            for (var i = 0; i < pedCount; i++) Check(pedBuf[i], 1.5f, ref best);
            return best;

            void Check(Vector3 p, float width, ref float b)
            {
                var rel = p - c.Pos; rel.y = 0;
                var along = Vector3.Dot(rel, fwd);
                if (along <= 0 || along > 16f) return;
                var lat = Mathf.Abs(rel.x * fwd.z - rel.z * fwd.x);
                if (lat > width) return;
                var d = along - half - 0.6f;
                if (d < b) b = d;
            }
        }

        void Drive(Car c, Vector3 player, float dt, float t)
        {
            var want = c.Cruise;
            if (!c.Turning)
            {
                if (c.Next < 0) ChooseNext(c);
                var remain = g.LaneLen[c.Lane] - c.S;
                var node = g.LaneTo[c.Lane];
                var green = g.CarGreen(node, g.LaneAxis[c.Lane], t);
                if (green && remain < 2f) c.Committed = true;
                if (!green && !c.Committed)
                {
                    // Too close to stop when it turned red: go through (amber).
                    if (remain < c.Speed * c.Speed / (2 * Brake) - 1f && remain < 6f) c.Committed = true;
                    else want = Mathf.Min(want, Mathf.Sqrt(Mathf.Max(0, 2 * Brake * (remain - 0.6f))));
                }
                if (c.Next >= 0 && Vector3.Dot(g.LaneDir[c.Next], g.LaneDir[c.Lane]) < 0.9f)
                    want = Mathf.Min(want, Mathf.Max(5f, Mathf.Sqrt(2 * Brake * Mathf.Max(0, remain)) + 5f)); // slow for turns
            }
            var ahead = Ahead(c, player);
            if (ahead < float.MaxValue) want = Mathf.Min(want, Mathf.Max(0, (ahead - Gap) * 1.1f));
            if (c.Stun > 0f) { c.Stun -= dt; want = 0f; }
            if (c.Health != null && c.Health.State >= VehicleHealth.Stage.Burning) { want = 0f; c.Wait = 0f; } // on fire: stops dead
            c.Speed = Mathf.MoveTowards(c.Speed, want, (want > c.Speed ? Accel : Brake) * dt);
            c.Wait = c.Speed < 0.2f ? c.Wait + dt : 0;
            c.S += c.Speed * dt;
            if (!c.Turning)
            {
                var len = g.LaneLen[c.Lane];
                if (c.S >= len)
                {
                    if (!c.Committed && !g.CarGreen(g.LaneTo[c.Lane], g.LaneAxis[c.Lane], t)) { c.S = len; c.Speed = 0; }
                    else
                    {
                        if (c.Next < 0) ChooseNext(c);
                        c.P0 = g.LaneEnd[c.Lane];
                        c.P2 = g.LaneStart[c.Next];
                        var d0 = g.LaneDir[c.Lane];
                        var d1 = g.LaneDir[c.Next];
                        if (Vector3.Dot(d0, d1) > 0.9f) c.P1 = (c.P0 + c.P2) * 0.5f;
                        else if (Vector3.Dot(d0, d1) < -0.9f) c.P1 = (c.P0 + c.P2) * 0.5f + d0 * 6f;
                        else c.P1 = c.P0 + d0 * Vector3.Dot(c.P2 - c.P0, d0);
                        c.TurnLen = Mathf.Max(1f, (Vector3.Distance(c.P0, c.P1) + Vector3.Distance(c.P1, c.P2) + Vector3.Distance(c.P0, c.P2)) * 0.5f);
                        c.S -= len;
                        c.Turning = true;
                    }
                }
            }
            if (c.Turning && c.S >= c.TurnLen)
            {
                c.S -= c.TurnLen;
                c.Lane = c.Next;
                c.Next = -1;
                c.Turning = false;
                c.Committed = false;
            }
            // Pose.
            Vector3 pos, fwd;
            if (c.Turning)
            {
                var u = Mathf.Clamp01(c.S / c.TurnLen);
                var a = Vector3.Lerp(c.P0, c.P1, u);
                var b = Vector3.Lerp(c.P1, c.P2, u);
                pos = Vector3.Lerp(a, b, u);
                fwd = b - a;
                if (fwd.sqrMagnitude < 1e-6f) fwd = g.LaneDir[c.Next];
                fwd.Normalize();
            }
            else
            {
                pos = g.LanePoint(c.Lane, c.S);
                fwd = g.LaneDir[c.Lane];
            }
            c.Pos = pos;
            c.Fwd = fwd;
            c.T.SetPositionAndRotation(pos, Quaternion.LookRotation(fwd));
            // Brake lights while slowing or stopped (the rig brightens the lamps, the flares swap material).
            var braking = want < c.Speed - 0.3f || c.Speed < 0.5f;
            c.Rig.BrakeInput = braking ? 1 : 0;
            if (braking != c.Braking)
            {
                c.Braking = braking;
                if (c.TailFx != null) c.TailFx.sharedMaterial = braking ? tailBrakeMat : tailMat;
            }
        }
    }
}
