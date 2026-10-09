using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Threading.Tasks;
using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Vehicle kit check (EOA/Test/Vehicle Shots, mode "vehicles"): in the open city around the plaza it lines up all
    /// ten kit vehicles on a street out of the traffic radius (lit by their rigs, flyers hovering) and captures 3/4
    /// close-ups, low side views (ground contact) and an LOD distance series; then chases a street-traffic car (wheel
    /// slip / orientation measured), a flyer on the sky lanes, a parked car, a wreck and a plaza car. Measurements go
    /// to report.json under "vehicles"; problems are errors.
    /// </summary>
    public sealed partial class AutoPilot
    {
        static readonly string[] KitVehicles =
        {
            "CyberCar_Coupe", "CyberCar_Sedan", "CyberCar_Taxi", "CyberVan", "CyberBike",
            "HoverCar_A", "HoverCar_B", "HoverTruck", "CyberCar_Sedan_Wrecked", "CyberVan_Burnt",
        };

        static string F(float v) => v.ToString("0.###", CultureInfo.InvariantCulture);

        async Task Shot(Vector3 pos, Vector3 look, float fov, string name, float settle = 0.35f)
        {
            G.Manager.Cam.Cinematic = (pos, look, fov);
            await Seconds(settle);
            await Capture(name);
        }

        async Task Vehicles()
        {
            var m = G.Manager;
            var ng = m.NewGame(Characters.Kael, 2);
            await Until(() => m.Cinematics.Active != null || ng.IsCompleted, 90);
            m.Cinematics.Stop();
            await Until(() => ng.IsCompleted, 180);
            await Until(() => m.Mode == GameMode.Play && m.Cinematics.Active == null, 30);
            await Seconds(5f);
            var checks = new Dictionary<string, object>();
            report["vehicles"] = checks;
            var traffic = FindAnyObjectByType<Traffic>();
            if (traffic == null || traffic.Graph == null) { errors.Add("vehicles: no street traffic (open city not built?)"); return; }
            checks["kitAvailable"] = VehicleKit.Available;
            checks["night"] = VehicleKit.Night;
            checks["trafficPool"] = traffic.Pool;
            checks["trafficActive"] = traffic.ActiveCount;
            var mix = new Dictionary<string, int>();
            foreach (Transform t in traffic.transform)
            {
                if (!t.name.StartsWith("Car_")) continue;
                var n = t.name.Substring(t.name.IndexOf('_', 4) + 1);
                mix[n] = mix.TryGetValue(n, out var k) ? k + 1 : 1;
            }
            checks["trafficMix"] = mix;
            Log("traffic mix " + string.Join(", ", mix.Select(kv => kv.Key + " x" + kv.Value)));

            await Lineup(traffic, checks);
            await TrafficChase(traffic, checks);
            await SkyChase(checks);
            await Parked(checks);
            m.Cam.Cinematic = null;
        }

        // ------------------------------------------------------------------ line-up

        async Task Lineup(Traffic traffic, Dictionary<string, object> checks)
        {
            var g = traffic.Graph;
            var player = G.Manager.Player != null ? G.Manager.Player.Position : Vector3.zero;
            // A long lane 240-330 m from the player (beyond the traffic despawn radius).
            var lane = -1;
            for (var l = 0; l < g.Lanes; l++)
            {
                if (g.LaneLen[l] < 70f) continue;
                var mid = g.LanePoint(l, g.LaneLen[l] * 0.5f);
                var d = Vector3.Distance(new Vector3(mid.x, 0, mid.z), new Vector3(player.x, 0, player.z));
                if (d > 240f && d < 330f) { lane = l; break; }
            }
            if (lane < 0) { errors.Add("vehicles: no lane for the line-up"); return; }
            var dir = g.LaneDir[lane];
            var right = Vector3.Cross(Vector3.up, dir);
            var root = new GameObject("VehicleLineup").transform;
            var placed = new List<(string name, GameObject go)>();
            var r = new System.Random(5);
            for (var i = 0; i < KitVehicles.Length; i++)
            {
                var name = KitVehicles[i];
                if (!CityKitAssets.Has(name)) { errors.Add("vehicles: missing prefab " + name); continue; }
                var go = EnvProps.Instantiate(name, root, false);
                var spec = VehicleKit.Get(name);
                // Two rows (this lane and the opposite one), 10 m apart along the street; flyers hover 1.4 m up.
                var p = g.LanePoint(lane, 8f + (i / 2) * 10f) - right * ((i % 2) * 4.4f) + Vector3.up * (spec.Flyer ? 1.4f : 0f);
                go.transform.SetPositionAndRotation(p, Quaternion.LookRotation(dir));
                if (!spec.Wreck)
                {
                    var rig = VehicleKit.AddRig(go, name, r, false);
                    rig.Headlights = VehicleRig.Lamp.On;
                    rig.HoloOn = true;
                }
                placed.Add((name, go));
            }
            await Seconds(0.5f);
            // Light slots: the rig's blocks on the emissive slots of each vehicle.
            var blk = new MaterialPropertyBlock();
            foreach (var (name, go) in placed)
            {
                var rig = go.GetComponent<VehicleRig>();
                int slots = 0, blocks = 0, kw = 0; var maxEm = 0f;
                foreach (var rd in go.GetComponentsInChildren<Renderer>(true))
                {
                    var mats = rd.sharedMaterials;
                    for (var i = 0; i < mats.Length; i++)
                    {
                        if (mats[i] == null || !mats[i].name.EndsWith("_off")) continue;
                        slots++;
                        if (mats[i].IsKeywordEnabled("_EMISSION")) kw++;
                        if (!rd.HasPropertyBlock()) continue;
                        rd.GetPropertyBlock(blk, i);
                        if (blk.isEmpty) continue;
                        blocks++;
                        maxEm = Mathf.Max(maxEm, blk.GetColor("_EmissionColor").maxColorComponent);
                    }
                }
                Log($"[lights] {name}: rig {(rig != null)} light slots {slots} (_EMISSION {kw}) with blocks {blocks}, max emission {F(maxEm)}");
            }

            // Ground contact: every wheel's lowest point vs the road under it.
            var contact = new Dictionary<string, object>();
            foreach (var (name, go) in placed)
            {
                var spec = VehicleKit.Get(name);
                if (spec.Flyer) continue;
                var worst = 0f;
                foreach (var t in go.GetComponentsInChildren<Transform>(true))
                {
                    if (!t.name.StartsWith("Wheel_") || t.name.Contains("_LOD")) continue;
                    var bottom = t.position.y - spec.Radius(t.name);
                    if (!Physics.Raycast(t.position + Vector3.up * 0.5f, Vector3.down, out var hit, 5f, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore)) continue;
                    var gap = bottom - hit.point.y;
                    if (Mathf.Abs(gap) > Mathf.Abs(worst)) worst = gap;
                }
                // Static wrecks: the lowest renderer bound instead (no wheel parts).
                if (spec.Wreck)
                {
                    var minY = float.MaxValue;
                    foreach (var rd in go.GetComponentsInChildren<Renderer>(true)) if (rd.name.EndsWith("_LOD0")) minY = Mathf.Min(minY, rd.bounds.min.y);
                    if (Physics.Raycast(go.transform.position + Vector3.up * 1.5f, Vector3.down, out var hit, 5f, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore)) worst = minY - hit.point.y;
                }
                contact[name] = F(worst);
                if (Mathf.Abs(worst) > 0.06f) errors.Add($"vehicles: {name} ground gap {F(worst)} m (floating > 0 / sinking < 0)");
            }
            checks["groundGap"] = contact;
            Log("ground gaps " + string.Join(", ", contact.Select(kv => kv.Key + " " + kv.Value)));

            // Overview, then a 3/4 front close-up of each vehicle and a few rear / low side views.
            var first = placed[0].go.transform.position;
            var last = placed[placed.Count - 1].go.transform.position;
            var centre = (first + last) * 0.5f;
            await Shot(centre + dir * 26f + right * 9f + Vector3.up * 5f, centre + Vector3.up * 0.8f, 50, "v_00_lineup");
            for (var i = 0; i < placed.Count; i++)
            {
                var (name, go) = placed[i];
                var spec = VehicleKit.Get(name);
                var t = go.transform;
                var s = Mathf.Max(spec.Size.z, 3.2f) / 4.8f;
                var look = t.position + Vector3.up * spec.Size.y * 0.45f;
                // Cameras on the outer side of the vehicle's row (row 0 on the lane, row 1 to its left).
                var outer = i % 2 == 0 ? 1f : -1f;
                await Shot(t.position + t.rotation * new Vector3(outer * 4.2f * s, 1.5f, 5.4f * s), look, 42, $"v_{i + 1:00}_{name}_fr");
                if (i < 5 || spec.Flyer) await Shot(t.position + t.rotation * new Vector3(outer * 4.2f * s, 1.7f, -5.6f * s), look, 42, $"v_{i + 1:00}_{name}_rr", 0.2f);
                // Low side view (ground contact, wheels).
                if (i == 1 || i == 3 || i == 4) await Shot(t.position + t.rotation * new Vector3(outer * 6.5f * s, 0.45f, 0), t.position + Vector3.up * 0.45f, 38, $"v_{i + 1:00}_{name}_side", 0.2f);
            }

            // LOD series on the sedan: which LOD level renders at each distance.
            var sedan = placed.FirstOrDefault(p => p.name == "CyberCar_Sedan").go;
            if (sedan != null)
            {
                var lods = new Dictionary<string, object>();
                var t = sedan.transform;
                var lg = sedan.GetComponent<LODGroup>();
                foreach (var d in new[] { 7f, 30f, 70f, 140f, 260f })
                {
                    // Down the empty street behind the line-up.
                    var pos = t.position + t.rotation * (d < 50f ? new Vector3(0.12f, 0.06f, -1f).normalized * d + Vector3.up * 1.2f : new Vector3(0.05f, 0.87f, -0.5f) * d);
                    await Shot(pos, t.position + Vector3.up * 0.7f, 30, $"v_lod_{d:000}m", 0.6f);
                    lods[F(d)] = LodLevel(lg, G.Manager.Cam.Cam);
                }
                checks["sedanLodByDistance"] = lods;
                Log("LOD by distance " + string.Join(", ", lods.Select(kv => kv.Key + "m:" + kv.Value)));
            }
            Destroy(root.gameObject);
            await Seconds(0.2f);
        }

        /// <summary>LOD level the group selects for this camera (screen-relative height vs the transitions; -1 culled).</summary>
        static int LodLevel(LODGroup lg, Camera cam)
        {
            if (lg == null || cam == null) return -2;
            var lods = lg.GetLODs();
            var t = lg.transform;
            var scale = Mathf.Max(Mathf.Abs(t.lossyScale.x), Mathf.Abs(t.lossyScale.y), Mathf.Abs(t.lossyScale.z));
            var d = Vector3.Distance(cam.transform.position, t.TransformPoint(lg.localReferencePoint));
            var h = lg.size * scale / (2f * d * Mathf.Tan(cam.fieldOfView * 0.5f * Mathf.Deg2Rad)) * QualitySettings.lodBias;
            for (var i = 0; i < lods.Length; i++) if (h >= lods[i].screenRelativeTransitionHeight) return i;
            return -1;
        }

        // ------------------------------------------------------------------ street traffic

        async Task TrafficChase(Traffic traffic, Dictionary<string, object> checks)
        {
            var player = G.Manager.Player != null ? G.Manager.Player.Position : Vector3.zero;
            // A moving traffic car (wait for one to get going), preferring a four-wheeler near the player.
            VehicleRig car = null;
            for (var tries = 0; tries < 40 && car == null; tries++)
            {
                var best = float.MaxValue;
                foreach (var rig in traffic.GetComponentsInChildren<VehicleRig>(false))
                {
                    var d = Vector3.Distance(rig.transform.position, player);
                    var moving = Mathf.Abs(rig.Speed) > 3f || tries > 30;
                    if (!moving || rig.Bike) continue;
                    if (d < best) { best = d; car = rig; }
                }
                if (car == null)
                {
                    // Rigs only measure speed near the camera: look at the traffic from above the player.
                    G.Manager.Cam.Cinematic = (player + new Vector3(0, 60, -40), player, 70);
                    await Seconds(0.5f);
                }
            }
            if (car == null) { errors.Add("vehicles: no moving traffic car"); return; }
            var ct = car.transform;
            Log($"chasing {ct.name} speed {F(car.Speed)}");
            // Follow it with the camera for a moment (rig animates within 90 m of the camera).
            for (var f = 0; f < 30; f++)
            {
                G.Manager.Cam.Cinematic = (ct.position + ct.right * 6.5f + Vector3.up * 1.1f, ct.position + Vector3.up * 0.5f, 45);
                await Awaitable.NextFrameAsync();
            }
            // Rolling: rear-wheel spin (about local +X) x radius over the distance driven: +1 rolls true, -1 reversed, 0 still.
            var rolls = new List<float>();
            var forward = new List<float>();
            var rear = ct.GetComponentsInChildren<Transform>(false).Where(t => t.name.StartsWith("Wheel_R") && !t.name.Contains("_LOD")).ToArray();
            for (var s = 0; s < 60 && rolls.Count < 24; s++)
            {
                G.Manager.Cam.Cinematic = (ct.position + ct.right * 6.5f + Vector3.up * 1.1f, ct.position + Vector3.up * 0.5f, 45);
                var q0 = rear.Select(w => w.localRotation).ToArray();
                var p0 = ct.position;
                for (var k = 0; k < 3; k++) await Awaitable.NextFrameAsync();
                var move = ct.position - p0;
                if (move.magnitude < 0.02f) { await Seconds(0.1f); continue; }
                forward.Add(Vector3.Dot(move.normalized, ct.forward));
                for (var i = 0; i < rear.Length; i++)
                {
                    (Quaternion.Inverse(q0[i]) * rear[i].localRotation).ToAngleAxis(out var deg, out var axis);
                    if (deg > 180f) deg -= 360f;
                    rolls.Add(deg * Mathf.Deg2Rad * Mathf.Sign(axis.x) * car.Spec.Radius(rear[i].name) / move.magnitude);
                }
            }
            var roll = rolls.Count > 0 ? rolls.Average() : 0f;
            var fwd = forward.Count > 0 ? forward.Average() : -1f;
            checks["trafficCar"] = ct.name;
            checks["wheelRollRatio"] = F(roll);
            checks["forwardDot"] = F(fwd);
            Log($"traffic wheel roll ratio {F(roll)} (+1 rolls true, -1 reversed, 0 still), forward dot {F(fwd)}, samples {rolls.Count}");
            if (rolls.Count == 0) warnings.Add("vehicles: traffic car never moved during the roll probe");
            else if (roll < 0.75f || roll > 1.25f) errors.Add($"vehicles: wheels do not roll with the car (ratio {F(roll)})");
            if (forward.Count > 0 && fwd < 0.95f) errors.Add($"vehicles: traffic does not drive forward (dot {F(fwd)})");
            await Capture("v_traffic_side");
            for (var k = 0; k < 3; k++)
            {
                for (var f = 0; f < 10; f++)
                {
                    G.Manager.Cam.Cinematic = (ct.position - ct.forward * 8f - ct.right * 2.5f + Vector3.up * 2.2f, ct.position + ct.forward * 6f + Vector3.up * 0.8f, 50);
                    await Awaitable.NextFrameAsync();
                }
                await Capture($"v_traffic_chase_{k}");
            }
            for (var f = 0; f < 10; f++)
            {
                G.Manager.Cam.Cinematic = (ct.position + ct.forward * 11f + ct.right * 3f + Vector3.up * 1.4f, ct.position + Vector3.up * 0.8f, 50);
                await Awaitable.NextFrameAsync();
            }
            await Capture("v_traffic_front");
            // Street level view down the road with traffic.
            await Shot(ct.position - ct.forward * 30f + Vector3.up * 1.7f, ct.position + Vector3.up * 1f, 55, "v_traffic_street", 0.1f);
        }

        // ------------------------------------------------------------------ sky lanes

        async Task SkyChase(Dictionary<string, object> checks)
        {
            var sky = FindAnyObjectByType<SkyTraffic>();
            if (sky == null) { warnings.Add("vehicles: no SkyTraffic"); return; }
            var rigs = sky.GetComponentsInChildren<VehicleRig>(false);
            checks["skyVehicles"] = rigs.Length;
            checks["skyMix"] = rigs.GroupBy(x => x.Spec.Name).ToDictionary(x => x.Key, x => x.Count());
            if (rigs.Length == 0) { errors.Add("vehicles: sky traffic has no kit flyers"); return; }
            foreach (var want in new[] { "HoverCar_A", "HoverCar_B", "HoverTruck" })
            {
                var rig = rigs.FirstOrDefault(x => x.Spec.Name == want);
                if (rig == null) continue;
                var t = rig.transform;
                for (var f = 0; f < 40; f++)
                {
                    var s = rig.Spec.Size.z / 5f;
                    G.Manager.Cam.Cinematic = (t.position - t.forward * 9f * s + t.right * 5f * s + Vector3.up * 2.5f * s, t.position + t.forward * 2f + Vector3.up * 0.5f, 45);
                    await Awaitable.NextFrameAsync();
                }
                await Capture("v_sky_" + want);
            }
            // From the middle of a street near the player, looking up at the nearest flyer.
            var traffic = FindAnyObjectByType<Traffic>();
            var pl = G.Manager.Player != null ? G.Manager.Player.Position : Vector3.zero;
            var street = pl;
            if (traffic != null && traffic.Graph != null)
            {
                var g = traffic.Graph;
                var best = float.MaxValue;
                for (var l = 0; l < g.Lanes; l++)
                {
                    var mid = g.LanePoint(l, g.LaneLen[l] * 0.5f);
                    var d = (mid - pl).sqrMagnitude;
                    if (d < best) { best = d; street = mid; }
                }
            }
            var nearest = rigs.OrderBy(x => (x.transform.position - street).sqrMagnitude).First().transform.position;
            await Shot(street + Vector3.up * 1.7f, nearest, 55, "v_sky_from_street", 0.3f);
        }

        // ------------------------------------------------------------------ parked / wrecks / plaza

        async Task Parked(Dictionary<string, object> checks)
        {
            var pl = G.Manager.Player != null ? G.Manager.Player.Position : Vector3.zero;
            var all = FindObjectsByType<LODGroup>(FindObjectsSortMode.None)
                .Where(x => x.GetComponentInParent<Traffic>() == null && x.GetComponentInParent<SkyTraffic>() == null && KitVehicles.Contains(x.name)).ToList();
            checks["parkedKitVehicles"] = all.GroupBy(x => x.name).ToDictionary(x => x.Key, x => x.Count());
            Log("static kit vehicles " + string.Join(", ", all.GroupBy(x => x.name).Select(x => x.Key + " x" + x.Count())));
            var lit = all.Count(x => x.GetComponentsInChildren<Renderer>(true).Any(r => r.sharedMaterials.Any(mm => mm != null && mm.name.StartsWith("veh_") && !mm.name.EndsWith("_off")
                && (mm.name.Contains("light") || mm.name.Contains("neon") || mm.name.Contains("glow")))));
            checks["parkedWithLightsOn"] = lit;
            if (lit > 0) errors.Add($"vehicles: {lit} static vehicles have their lights on");
            async Task Look(LODGroup v, string name)
            {
                if (v == null) return;
                var t = v.transform;
                var s = VehicleKit.Get(v.name).Size.z / 4.8f;
                await Shot(t.position + t.rotation * new Vector3(4.5f * s, 1.6f, 5.5f * s), t.position + Vector3.up * 0.7f, 42, name, 0.8f);
            }
            await Look(all.Where(x => !VehicleKit.Get(x.name).Wreck && x.transform.position.y < 1f && (x.transform.position - pl).magnitude > 40f)
                .OrderBy(x => (x.transform.position - pl).sqrMagnitude).FirstOrDefault(), "v_parked");
            await Look(all.Where(x => x.name == "CyberVan_Burnt").OrderBy(x => (x.transform.position - pl).sqrMagnitude).FirstOrDefault(), "v_wreck_van");
            await Look(all.Where(x => x.name == "CyberCar_Sedan_Wrecked").OrderBy(x => (x.transform.position - pl).sqrMagnitude).FirstOrDefault(), "v_wreck_sedan");
            // Plaza abandoned car (PzKit.Car at prototype (-38, -20) → Unity (38, y, -20)), with its kept box collider.
            var plaza = all.OrderBy(x => (x.transform.position - new Vector3(38, 0, -20)).sqrMagnitude).FirstOrDefault();
            if (plaza != null && (plaza.transform.position - new Vector3(38, plaza.transform.position.y, -20)).magnitude < 3f)
            {
                var box = plaza.GetComponent<BoxCollider>();
                checks["plazaCarCollider"] = box != null ? $"{box.center} {box.size} layer {plaza.gameObject.layer}" : "none";
                await Look(plaza, "v_plaza_car");
            }
        }
    }
}
