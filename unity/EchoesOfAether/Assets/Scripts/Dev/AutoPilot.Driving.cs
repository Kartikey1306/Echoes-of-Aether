using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Driving test (-executeMethod EOA.EditorTools.SmokeTest.RunDriving, mode "driving"): new game, then in the open
    /// city: walk up to a parked car (prompt), get in, drive a route along the street lanes with a pure-pursuit driver
    /// (pull out, accelerate, turn at the intersection, full-throttle straight), brake test, handbrake drift, a
    /// head-on hit into a building, get out next to the wall (placement checked), re-enter, flip recovery, save
    /// rules while driving, a cinematic interrupting the drive, night headlights. Screenshots (chase, side view,
    /// speedometer, drift, impact, exit) and 4 Hz telemetry (speed, wheel contact and compression, slip, inputs)
    /// go to report.json under "driving"; failed checks are errors.
    /// </summary>
    public sealed partial class AutoPilot
    {
        sealed class DriveRoute
        {
            public readonly List<Vector3> P = new();
            public readonly List<float> V = new();
            public void Add(Vector3 p, float v) { P.Add(new Vector3(p.x, 0, p.z)); V.Add(v); }
        }

        Dictionary<string, object> drv;
        List<string> drvSamples;
        float drvT0;
        string drvPhase = "";
        int drvGrounded, drvSamplesN, drvAllDown;
        float drvMaxSpeed, drvMaxSlip;

        async Task DriveTest()
        {
            await Seconds(2);
            var ng = M.NewGame(Characters.Kael, 2);
            // (Generous: the plaza's NavMesh bake is slow on a busy machine.)
            await WaitFor("plaza", () => ng.IsFaulted || (M.World.ZoneId == "plaza" && M.Mode == GameMode.Play && !M.World.Loading), 600);
            await Seconds(2); await Flush(80); await Seconds(1);
            drv = new Dictionary<string, object>();
            drvSamples = new List<string>();
            report["driving"] = drv;
            drv["samples"] = drvSamples;
            drvT0 = Time.realtimeSinceStartup;
            var entries = Driving.Entries;
            drv["drivableCars"] = entries.Count;
            drv["mix"] = entries.GroupBy(e => e.Spec.Name).ToDictionary(x => x.Key, x => x.Count());
            if (entries.Count == 0) { errors.Add("driving: no drivable parked cars registered"); return; }
            var traffic = FindAnyObjectByType<Traffic>();
            var g = traffic != null ? traffic.Graph : null;
            if (g == null) { errors.Add("driving: no road graph (open city not built?)"); return; }

            // ---- a parked sedan / coupe / taxi near the plaza with a long lane ahead of it
            Driving.Entry pick = null;
            int lane = -1; float laneS = 0;
            foreach (var e in entries.OrderBy(e => (e.Spec.Name == "CyberVan" ? 1000f : 0f) + (e.Go.transform.position - new Vector3(0, 0, 20)).magnitude))
            {
                var t = e.Go.transform;
                var f = t.forward; f.y = 0; f.Normalize();
                for (var l = 0; l < g.Lanes; l++)
                {
                    if (Vector3.Dot(g.LaneDir[l], f) < 0.95f) continue;
                    var rel = t.position - g.LaneStart[l]; rel.y = 0;
                    var s = Vector3.Dot(rel, g.LaneDir[l]);
                    var lat = Vector3.Cross(g.LaneDir[l], rel).magnitude;
                    if (lat > 5.5f || s < 2f || g.LaneLen[l] - s < 55f) continue;
                    // Room to pull out: nothing within 7 m ahead of its nose (another car, a post).
                    var nose = t.position + f * (e.Spec.Length * 0.5f) + Vector3.up * 0.75f;
                    if (Physics.BoxCast(nose, new Vector3(e.Spec.Size.x * 0.45f, 0.3f, 0.2f), f, Quaternion.LookRotation(f), 7f, CombatLayers.WorldMask | (1 << CombatLayers.IgnoreCamera), QueryTriggerInteraction.Ignore)) continue;
                    pick = e; lane = l; laneS = s;
                    break;
                }
                if (pick != null) break;
            }
            if (pick == null) { errors.Add("driving: no parked car with a free lane ahead"); return; }
            var spec = pick.Spec;
            var ct = pick.Go.transform;
            drv["car"] = pick.Go.name;
            drv["carStart"] = ct.position.ToString("F1");
            Log($"[drive] test car {pick.Id} {pick.Go.name} at {ct.position:F1}, lane {lane} s {laneS:0.0}/{g.LaneLen[lane]:0.0}");

            // ---- walk-up: prompt
            var hero = M.Player;
            var door = ct.position - ct.right * (spec.Size.x * 0.5f + 0.9f) + ct.forward * 0.3f;
            var gy = M.World.GroundAt(door + Vector3.up * 1.5f, 4);
            hero.Teleport(new Vector3(door.x, (gy ?? door.y) + 0.03f, door.z), Mathf.Atan2(ct.right.x, ct.right.z) * Mathf.Rad2Deg);
            M.Cam.SnapBehind(Mathf.Atan2(ct.right.x, ct.right.z) - 0.5f);
            await Seconds(1.2f);
            var prompt = M.InteractionPrompt;
            drv["prompt"] = prompt ?? "none";
            if (M.World.Candidate != pick.Id || string.IsNullOrEmpty(prompt) || !prompt.ToLowerInvariant().Contains("drive")) errors.Add($"driving: no Drive prompt next to the car (candidate {M.World.Candidate}, prompt '{prompt}')");
            await Capture("d01_prompt");

            // ---- get in
            if (!M.World.Interact()) errors.Add("driving: interact did nothing next to the car");
            if (!await Until(() => Driving.Active, 5f)) { errors.Add("driving: did not get into the car"); return; }
            var car = Driving.Car;
            await Seconds(1.0f);
            drv["enteredHeroHidden"] = !hero.gameObject.activeSelf;
            drv["hudPrompt"] = M.InteractionPrompt ?? "none";
            if (hero.gameObject.activeSelf) errors.Add("driving: hero still visible in the car");
            if (!M.CanSaveNow(out var saveWhy)) drv["saveWhileDriving"] = "blocked: " + saveWhy;
            else errors.Add("driving: manual save allowed while driving");
            Sample("parked");
            if (car.GroundedWheels != car.WheelCount) errors.Add($"driving: parked car has {car.GroundedWheels}/{car.WheelCount} wheels on the ground");
            await Capture("d02_in_car");

            // ---- route: pull out, along the lane, turn at the next intersection, along the cross street
            var route = new DriveRoute();
            var startS = Mathf.Min(laneS + 9f, g.LaneLen[lane] - 30f);
            route.Add(ct.position + ct.forward * 3f, 10f);
            for (var s = startS; s < g.LaneLen[lane] - 1f; s += 2f) route.Add(g.LanePoint(lane, s), 26f);
            var node = g.LaneTo[lane];
            var next = -1;
            foreach (var o in g.Out[node])
            {
                if (o == g.Reverse[lane] || Mathf.Abs(Vector3.Dot(g.LaneDir[o], g.LaneDir[lane])) > 0.2f) continue;
                if (next < 0 || g.LaneLen[o] > g.LaneLen[next]) next = o;
            }
            if (next < 0) foreach (var o in g.Out[node]) if (o != g.Reverse[lane]) { next = o; break; }
            if (next >= 0)
            {
                Vector3 p0 = g.LaneEnd[lane], p2 = g.LaneStart[next];
                var p1 = p0 + g.LaneDir[lane] * Vector3.Dot(p2 - p0, g.LaneDir[lane]);
                for (var i = 1; i < 12; i++)
                {
                    var u = i / 12f;
                    route.Add(Vector3.Lerp(Vector3.Lerp(p0, p1, u), Vector3.Lerp(p1, p2, u), u), 9f);
                }
                for (var s = 0f; s < Mathf.Min(g.LaneLen[next] - 4f, 110f); s += 2f) route.Add(g.LanePoint(next, s), 30f);
            }
            // Speed plan: brake ahead of slow sections (5 m/s^2).
            for (var i = route.P.Count - 2; i >= 0; i--)
                route.V[i] = Mathf.Min(route.V[i], Mathf.Sqrt(route.V[i + 1] * route.V[i + 1] + 2f * 5f * Vector3.Distance(route.P[i], route.P[i + 1])));
            route.V[route.V.Count - 1] = 0f;
            drv["routeMetres"] = Mathf.Round(Length(route));

            var start = ct.position;
            var idx = 0;
            var shotSpeed = false; var shotSide = false; var shotTurn = false;
            var turnStart = (next >= 0) ? route.P.Count - Mathf.Min(route.P.Count, Mathf.CeilToInt(Mathf.Min(g.LaneLen[next] - 4f, 110f) / 2f)) - 11 : -1;
            var tEnd = Time.realtimeSinceStartup + 45f;
            var sampleT = 0f;
            drvPhase = "route";
            while (Time.realtimeSinceStartup < tEnd && idx < route.P.Count - 3)
            {
                Pursue(car, route, ref idx, 1f);
                sampleT -= Time.deltaTime;
                if (sampleT <= 0f) { sampleT = 0.25f; Sample(idx >= turnStart && turnStart >= 0 && idx < turnStart + 12 ? "turn" : "route"); }
                if (!shotSpeed && car.ForwardSpeed > 16f) { shotSpeed = true; await CaptureMoving(car, "d03_chase_speed"); }
                else if (shotSpeed && !shotSide && car.ForwardSpeed > 18f) { shotSide = true; await SideShot(car, "d04_side_view"); }
                else if (!shotTurn && turnStart >= 0 && idx >= turnStart + 5) { shotTurn = true; await CaptureMoving(car, "d05_turn"); }
                else await Awaitable.NextFrameAsync();
                if (car == null || !Driving.Active) break;
            }
            var travelled = Vector3.Distance(new Vector3(start.x, 0, start.z), new Vector3(car.transform.position.x, 0, car.transform.position.z));
            drv["routeProgress"] = $"{idx}/{route.P.Count}";
            drv["travelledStraightLine"] = Mathf.Round(travelled);
            drv["maxSpeedKmh"] = Mathf.Round(drvMaxSpeed * 3.6f);
            drv["allWheelsDownRatio"] = drvSamplesN > 0 ? Mathf.Round(100f * drvAllDown / drvSamplesN) / 100f : 0f;
            if (idx < route.P.Count * 0.85f) errors.Add($"driving: the route was not completed ({idx}/{route.P.Count} points)");
            if (drvMaxSpeed < 18f) errors.Add($"driving: top speed on the route only {drvMaxSpeed * 3.6f:0} km/h");
            if (drvSamplesN > 0 && drvAllDown < drvSamplesN * 0.9f) errors.Add($"driving: wheels lost contact on the route ({drvAllDown}/{drvSamplesN} samples with all wheels down)");
            drv["audio"] = car.Audio != null ? (car.Audio.ClipsLoaded ? "clips ok; " : "MISSING CLIPS; ") + car.Audio.Levels : "none";
            if (car.Audio == null || !car.Audio.ClipsLoaded) errors.Add("driving: engine / tyre audio clips missing");
            if (car.Recoveries > 0) errors.Add($"driving: the car needed {car.Recoveries} recoveries on a plain route");

            // ---- brake test from speed
            drvPhase = "brake";
            var brakeFrom = car.ForwardSpeed;
            var bp = car.transform.position;
            var bt = Time.realtimeSinceStartup;
            await Hold(car, 0, 1, 0, 0, () => car.ForwardSpeed < 0.5f, 8f);
            drv["brakeFromKmh"] = Mathf.Round(brakeFrom * 3.6f);
            drv["brakeDistance"] = Mathf.Round(Vector3.Distance(bp, car.transform.position) * 10f) / 10f;
            drv["brakeSeconds"] = Mathf.Round((Time.realtimeSinceStartup - bt) * 100f) / 100f;
            Log($"[drive] braking from {brakeFrom * 3.6f:0} km/h: {drv["brakeDistance"]} m, {drv["brakeSeconds"]} s");
            await Hold(car, 0, 0, 0, 0, () => false, 0.4f);

            // ---- handbrake drift on the cross street (accelerate, then steer + handbrake, release, recover)
            drvPhase = "drift";
            var dirFwd = car.transform.forward;
            await Hold(car, 1, 0, 0, 0, () => car.ForwardSpeed > 17f, 6f);
            drvMaxSlip = 0;
            var y0 = car.transform.eulerAngles.y;
            var k = 0f; // simulated seconds into the manoeuvre (captures freeze the car)
            var shotDrift = false;
            while (k < 1.6f)
            {
                // 0-0.7 s: steer left + handbrake; 0.7-1.6 s: countersteer on the throttle.
                if (k < 0.7f) SetInput(0.3f, 0, -1f, 1);
                else SetInput(0.7f, 0, Mathf.Clamp(car.SlipAngle / 25f, -1f, 1f), 0);
                if (Mathf.Abs(car.SlipAngle) < 100f) drvMaxSlip = Mathf.Max(drvMaxSlip, Mathf.Abs(car.SlipAngle));
                if (!shotDrift && k > 0.75f) { shotDrift = true; await CaptureMoving(car, "d06_drift"); }
                else await Awaitable.NextFrameAsync();
                k += Time.deltaTime;
                sampleT -= Time.deltaTime;
                if (sampleT <= 0f) { sampleT = 0.1f; Sample("drift"); }
            }
            var yawTurned = Mathf.Abs(Mathf.DeltaAngle(y0, car.transform.eulerAngles.y));
            drv["driftMaxSlipDeg"] = Mathf.Round(drvMaxSlip);
            drv["driftYawDeg"] = Mathf.Round(yawTurned);
            drv["driftEndSpeedKmh"] = Mathf.Round(car.ForwardSpeed * 3.6f);
            if (drvMaxSlip < 12f) errors.Add($"driving: handbrake does not drift (max slip {drvMaxSlip:0} deg)");
            if (car.ForwardSpeed < 0f) warnings.Add($"driving: the handbrake drift spun the car round (heading changed {yawTurned:0} deg)");
            await Hold(car, 0, 1, 0, 1, () => car.Speed < 0.6f, 6f);
            if (!car.Upright) errors.Add("driving: the car rolled over in the drift");
            drv["afterDriftUpright"] = car.Upright;

            // ---- head-on into a building facade
            drvPhase = "wall";
            var wallOk = await WallImpact(car);
            drv["wallImpact"] = wallOk;

            // ---- get out next to the wall
            drvPhase = "exit";
            SetInput(0, 0, 0, 0, exit: true);
            if (!await Until(() => !Driving.Active, 6f)) { errors.Add("driving: could not get out"); Driving.AutoInput = null; return; }
            Driving.AutoInput = null;
            await Seconds(0.8f);
            CheckExit(hero, car, "afterWall");
            M.Cam.SnapBehind(Mathf.Atan2((car.transform.position - hero.Position).x, (car.transform.position - hero.Position).z) + 0.4f);
            await Seconds(0.6f);
            await Capture("d08_exit");

            // ---- the car stays; back in, flip it, recovery
            drvPhase = "flip";
            var parkedAt = car.transform.position;
            await Seconds(1.0f);
            drv["carParkedKinematic"] = car.Parked;
            drv["carStayed"] = Vector3.Distance(parkedAt, car.transform.position) < 0.3f;
            if (!car.Parked) warnings.Add("driving: the left car did not settle (still simulated)");
            var entry = Driving.Entries.FirstOrDefault(e => e.Car == car);
            if (entry != null && Vector3.Distance(entry.Def.Position, car.transform.position + Vector3.up) > 0.5f) errors.Add("driving: the Drive prompt did not follow the car");
            await Seconds(0.3f);
            Driving.Enter(entry);
            if (!await Until(() => Driving.Active, 5f)) { errors.Add("driving: could not get back into the car"); return; }
            await Hold(car, 0, 0, 0, 0, () => false, 0.5f);
            // Back away from the wall, then flip it onto its roof.
            await Hold(car, 0, 1, 0, 0, () => car.ForwardSpeed < -3f, 3f);
            await Hold(car, 0, 0, 0, 1, () => car.Speed < 0.3f, 3f);
            var fr = car.transform.rotation;
            car.ResetTo(car.transform.position + Vector3.up * 1.6f, Quaternion.Euler(0, fr.eulerAngles.y, 180f));
            await Seconds(1.2f);
            await Capture("d09_flipped");
            var recBefore = car.Recoveries;
            await Hold(car, 0, 0, 0, 0, () => car.Recoveries > recBefore && car.Upright && car.GroundedWheels >= 3, 7f);
            drv["flipRecovered"] = car.Upright && car.Recoveries > recBefore;
            if (!car.Upright) errors.Add("driving: the flipped car was not put back on its wheels");
            await Seconds(0.8f);
            await Capture("d10_recovered");

            // ---- headlights at night, front three-quarter (parked, engine on)
            drv["night"] = VehicleKit.Night;
            var cf = car.transform;
            M.Cam.Cinematic = (cf.position + cf.forward * 7.5f + cf.right * 3.2f + Vector3.up * 1.4f, cf.position + Vector3.up * 0.7f, 50);
            await Seconds(0.5f);
            await Capture("d11_headlights");
            M.Cam.Cinematic = null;

            // ---- autosave while driving stores a spot beside the car
            M.Autosave(SaveKind.Checkpoint);
            await Seconds(1.6f);
            var sp = G.State.D.Position;
            if (sp != null)
            {
                var spos = new Vector3(sp[0], sp[1], sp[2]);
                var local = car.transform.InverseTransformPoint(spos);
                var inside = Mathf.Abs(local.x) < spec.Size.x * 0.5f && Mathf.Abs(local.z) < spec.Length * 0.5f;
                drv["autosaveSpot"] = spos.ToString("F1") + (inside ? " (inside the car!)" : " (beside the car)");
                if (inside) errors.Add("driving: autosave stored a position inside the car");
            }

            // ---- a cinematic starting ends the drive at once (event only: no real cinematic is played)
            drvPhase = "cinematic";
            Bus.Emit(new CinematicStarted { Id = "drive_test" });
            await Awaitable.NextFrameAsync();
            drv["cinematicEndsDrive"] = !Driving.Active && hero.gameObject.activeSelf;
            if (Driving.Active || !hero.gameObject.activeSelf) errors.Add("driving: a cinematic did not end the drive");
            await Seconds(0.5f);
            CheckExit(hero, car, "afterCinematic");

            // ---- explosions: attack a parked car until it blows up
            drvPhase = "explosion";
            await ExplosionTest(hero);

            drv["crowdDodges"] = Crowd.Dodges;
            drv["impacts"] = car.Impacts;
            drv["seconds"] = Mathf.Round(Time.realtimeSinceStartup - drvT0);
            report["driving_result"] = errors.Count == 0 ? "PASS" : "FAIL";
            Log($"[drive] test done: max {drvMaxSpeed * 3.6f:0} km/h, drift {drvMaxSlip:0} deg, impacts {car.Impacts}, dodges {Crowd.Dodges}");
        }

        /// <summary>
        /// Hero attacks a parked car (light combo + heavy finisher through the normal combat path) until it burns, steps
        /// back to the edge of the blast radius and watches: smoke, fire, fuse flicker, explosion (slow motion for the
        /// shot), wreck, chain reaction. Checks the hero takes fair damage and survives, a wreck is left, cinematics
        /// block damage, and lock-on ignores cars.
        /// </summary>
        async Task ExplosionTest(Hero hero)
        {
            var vd = VehicleDamage.Instance;
            var ex = new Dictionary<string, object>();
            drv["explosion"] = ex;
            if (vd == null) { errors.Add("explosions: no VehicleDamage in the open city"); return; }
            ex["destructibleCars"] = vd.Registered;
            // A parked car near the hero (prefer one with a neighbour for a chain reaction), with room to stand beside it.
            VehicleHealth target = null;
            Vector3 stand = default;
            var best = float.MaxValue;
            foreach (var v in vd.All)
            {
                if (v == null || !v.Alive || v.InTraffic || v.Spec.Bike || v.GetComponent<PlayerCar>() != null) continue;
                var vt = v.transform;
                // (Alive: only cars in streamed-in cells, i.e. within view distance.)
                var d = Vector3.Distance(vt.position, hero.Position);
                var neighbour = false;
                foreach (var u in vd.All)
                    if (u != null && u != v && u.Alive && !u.InTraffic && Vector3.Distance(u.transform.position, vt.position) < 7f) { neighbour = true; break; }
                var score = d - (neighbour ? 1000f : 0f);
                if (score >= best) continue;
                foreach (var side in new[] { -1f, 1f })
                {
                    var p = vt.position + vt.right * side * (v.Spec.Size.x * 0.5f + 0.85f);
                    var gy = M.World.GroundAt(p + Vector3.up * 1.5f, 4);
                    if (!gy.HasValue || Mathf.Abs(gy.Value - vt.position.y) > 0.6f) continue;
                    var feet = new Vector3(p.x, gy.Value + 0.03f, p.z);
                    if (Physics.CheckCapsule(feet + Vector3.up * 0.45f, feet + Vector3.up * 1.4f, 0.36f, CombatLayers.WorldMask | (1 << CombatLayers.IgnoreCamera), QueryTriggerInteraction.Ignore)) continue;
                    best = score; target = v; stand = feet;
                    break;
                }
            }
            if (target == null) { errors.Add("explosions: no parked car to attack"); return; }
            var t = target.transform;
            ex["target"] = target.name + " " + t.position.ToString("F1");
            Log($"[explode] attacking {target.name} at {t.position:F1} ({target.Health:0}/{target.Max:0} hp)");
            hero.Teleport(stand, Mathf.Atan2(t.position.x - stand.x, t.position.z - stand.z) * Mathf.Rad2Deg);
            var toCar = t.position - stand; toCar.y = 0;
            M.Cam.SnapBehind(Mathf.Atan2(toCar.x, toCar.z) + 0.6f);
            await Seconds(0.8f);

            // Lock-on never picks a car.
            var lockPick = CombatSystem.Ensure().BestTarget(Team.Player, hero.Chest, toCar.normalized, 25, 52, true, false);
            if (lockPick is VehicleHealth) errors.Add("explosions: lock-on picked a car");

            // An Aether Bolt through the projectile path.
            var hBolt = target.Health;
            var spec = ProjectileSpec.Make(hero.Chest, (target.AimPoint - hero.Chest).normalized, 42f, 12f, Team.Player, new Color(0.44f, 0.82f, 1f), hero);
            spec.Kind = HitKind.Bolt;
            CombatSystem.Ensure().Fire(spec);
            await Seconds(0.6f);
            ex["boltDamage"] = Mathf.Round(hBolt - target.Health);
            if (target.Health >= hBolt) errors.Add("explosions: an Aether Bolt did not damage the car");

            var presses = 0;
            var t0 = Time.realtimeSinceStartup;
            var shotSmoke = false;
            while (target.Alive && target.State < VehicleHealth.Stage.Burning && Time.realtimeSinceStartup - t0 < 60f)
            {
                hero.FaceTowards(t.position);
                hero.InjectPress(presses % 4 == 3 ? "heavy" : "light");
                presses++;
                await Seconds(presses % 4 == 0 ? 0.75f : 0.34f);
                if (!shotSmoke && target.State >= VehicleHealth.Stage.Smoking)
                {
                    shotSmoke = true;
                    ex["attacksToSmoke"] = presses;
                    await Capture("e01_smoking");
                }
            }
            ex["attacksToFire"] = presses;
            ex["healthAtFire"] = Mathf.Round(target.Health);
            Log($"[explode] {presses} attacks: stage {target.State}, {target.Health:0} hp");
            if (target.State < VehicleHealth.Stage.Burning) { errors.Add($"explosions: {presses} attacks did not set the car on fire ({target.Health:0}/{target.Max:0} hp)"); return; }

            // Back off to the edge of the blast and watch.
            var away = stand - t.position; away.y = 0; away = away.sqrMagnitude > 0.01f ? away.normalized : -t.right;
            var back = t.position + away * 6.4f;
            var by = M.World.GroundAt(back + Vector3.up * 1.5f, 4);
            hero.Teleport(new Vector3(back.x, (by ?? back.y) + 0.03f, back.z), Mathf.Atan2(-away.x, -away.z) * Mathf.Rad2Deg);
            var camPos = t.position + away * 13f + Vector3.Cross(Vector3.up, away) * 5f + Vector3.up * 3.2f;
            M.Cam.Cinematic = (camPos, t.position + Vector3.up * 1.0f, 52);
            await Seconds(0.9f);
            await Capture("e02_burning");
            // Chain reaction: (test setup) another parked car pulled up right behind the burning one.
            VehicleHealth second = null;
            var sd = float.MaxValue;
            foreach (var v in vd.All)
            {
                if (v == null || v == target || !v.Alive || v.InTraffic || v.Spec.Bike || v.GetComponent<PlayerCar>() != null) continue;
                var d = (v.transform.position - t.position).sqrMagnitude;
                if (d < sd) { sd = d; second = v; }
            }
            if (second != null)
            {
                second.transform.SetParent(vd.transform, true); // out of its culling cell
                second.transform.SetPositionAndRotation(t.position - t.forward * ((target.Spec.Length + second.Spec.Length) * 0.5f + 0.9f), t.rotation);
                Physics.SyncTransforms();
                ex["chainCar"] = second.name;
            }
            var hpBefore = hero.Health + hero.Shield;
            var booms = vd.Explosions;
            if (await Until(() => target.State == VehicleHealth.Stage.Fuse || !target.Alive, 12f) && target.Alive)
            {
                await Seconds(0.5f);
                await Capture("e03_fuse");
            }
            var exploded = await Until(() => vd.Explosions > booms, 12f);
            if (!exploded) { errors.Add("explosions: the burning car never exploded"); M.Cam.Cinematic = null; return; }
            CombatSystem.Hitstop(1.4f); // slow motion for the shot (the capture takes real time)
            await Capture("e04_explosion");
            await Seconds(1.2f);
            var hpAfter = hero.Health + hero.Shield;
            ex["heroDamage"] = Mathf.Round(hpBefore - hpAfter);
            ex["heroAlive"] = hero.Alive;
            ex["targetGone"] = !t.gameObject.activeSelf;
            ex["wrecks"] = vd.WreckCount;
            if (!hero.Alive) errors.Add("explosions: the hero died from a car explosion at the blast edge");
            if (hpBefore - hpAfter > 70f) errors.Add($"explosions: unfair damage to the hero ({hpBefore - hpAfter:0})");
            if (vd.WreckCount == 0 || t.gameObject.activeSelf) errors.Add("explosions: no wreck left behind");
            await Seconds(1.5f);
            await Capture("e05_wreck");
            // Chain reactions (cars caught in the blast burn / blow up on a short fuse).
            if (second != null && await Until(() => vd.Explosions > booms + 1, 6f))
            {
                CombatSystem.Hitstop(1.2f);
                await Capture("e06_chain");
            }
            if (second != null && second.State != VehicleHealth.Stage.Wrecked) errors.Add($"explosions: no chain reaction (the car behind is {second.State}, {second.Health:0} hp)");
            await Seconds(2f);
            var burning = 0;
            foreach (var v in vd.All) if (v != null && v != target && v.State >= VehicleHealth.Stage.Burning) burning++;
            ex["explosions"] = vd.Explosions - booms;
            ex["otherCarsBurningOrWrecked"] = burning;
            M.Cam.Cinematic = null;
            Log($"[explode] boom: hero took {hpBefore - hpAfter:0} (alive {hero.Alive}), {vd.Explosions - booms} explosions, {burning} other cars hit, {vd.WreckCount} wrecks");

            // Cinematics: no damage at all.
            VehicleHealth other = null;
            foreach (var v in vd.All) if (v != null && v.Alive && v.State == VehicleHealth.Stage.Intact && !v.InTraffic) { other = v; break; }
            if (other != null)
            {
                M.InCinematic = true;
                var applied = other.Damage(500f, other.transform.position);
                M.InCinematic = false;
                ex["damageDuringCinematic"] = applied;
                if (applied > 0f || other.State != VehicleHealth.Stage.Intact) errors.Add("explosions: a car took damage during a cinematic");
            }
            if (!hero.Alive) return;
            hero.Restore();
        }

        static float Length(DriveRoute r)
        {
            var l = 0f;
            for (var i = 1; i < r.P.Count; i++) l += Vector3.Distance(r.P[i - 1], r.P[i]);
            return l;
        }

        static void SetInput(float thr, float brk, float steer, float hb, bool exit = false) =>
            Driving.AutoInput = new Driving.Inputs { Throttle = thr, Brake = brk, Steer = steer, Handbrake = hb, Exit = exit };

        async Task Hold(PlayerCar car, float thr, float brk, float steer, float hb, System.Func<bool> until, float timeout)
        {
            var end = Time.realtimeSinceStartup + timeout;
            var st = 0f;
            while (Time.realtimeSinceStartup < end && !until())
            {
                SetInput(thr, brk, steer, hb);
                st -= Time.deltaTime;
                if (st <= 0f) { st = 0.25f; Sample(drvPhase); }
                await Awaitable.NextFrameAsync();
                if (car == null) return;
            }
            SetInput(0, 0, 0, 0);
        }

        /// <summary>Pure pursuit along the route (look-ahead grows with speed) with a speed plan.</summary>
        void Pursue(PlayerCar car, DriveRoute r, ref int idx, float speedScale)
        {
            var t = car.transform;
            var p = new Vector3(t.position.x, 0, t.position.z);
            while (idx < r.P.Count - 1 && (r.P[idx + 1] - p).sqrMagnitude <= (r.P[idx] - p).sqrMagnitude) idx++;
            var look = 6f + Mathf.Abs(car.ForwardSpeed) * 0.45f;
            var j = idx;
            var acc = 0f;
            while (j < r.P.Count - 1 && acc < look) { acc += Vector3.Distance(r.P[j], r.P[j + 1]); j++; }
            var to = r.P[j] - p;
            var fwd = t.forward; fwd.y = 0;
            var alpha = Vector3.SignedAngle(fwd, to, Vector3.up) * Mathf.Deg2Rad;
            var ld = Mathf.Max(3f, to.magnitude);
            var delta = Mathf.Atan(2f * 2.9f * Mathf.Sin(alpha) / ld) * Mathf.Rad2Deg;
            var lim = Mathf.Lerp(34f, 7.5f, Mathf.Pow(Mathf.Clamp01(Mathf.Abs(car.ForwardSpeed) / 42f), 0.75f));
            var steer = Mathf.Clamp(delta / lim, -1f, 1f);
            var want = r.V[Mathf.Min(idx + 2, r.V.Count - 1)] * speedScale;
            // Something big in the lane ahead (traffic): slow down.
            if (Physics.SphereCast(t.position + Vector3.up * 0.8f + t.forward * (car.Spec.Length * 0.5f + 0.5f), 1.0f, t.forward, out var hit, 18f, 1 << CombatLayers.IgnoreCamera, QueryTriggerInteraction.Ignore))
                want = Mathf.Min(want, Mathf.Max(0f, (hit.distance - 5f) * 0.9f));
            var err = want - car.ForwardSpeed;
            var thr = Mathf.Clamp01(err * 0.4f + (want > 1f ? 0.1f : 0f));
            var brk = err < -1.2f ? Mathf.Clamp01(-err * 0.3f) : 0f;
            SetInput(thr, brk, steer, 0);
        }

        void Sample(string phase)
        {
            var car = Driving.Car;
            if (car == null) return;
            var down = car.GroundedWheels;
            var comp = "";
            for (var i = 0; i < car.WheelCount; i++) comp += (i > 0 ? "/" : "") + car.WheelCompression(i).ToString("0.00");
            var a = Driving.AutoInput ?? default;
            drvMaxSpeed = Mathf.Max(drvMaxSpeed, car.ForwardSpeed);
            if (phase == "route")
            {
                drvSamplesN++;
                if (down == car.WheelCount) drvAllDown++;
            }
            if (drvSamples.Count < 600)
                drvSamples.Add($"{Time.realtimeSinceStartup - drvT0:0.00}s {phase} v={car.ForwardSpeed * 3.6f:0}km/h gear={car.Gear} rpm={car.Rpm01:0.00} wheels={down}/{car.WheelCount} comp={comp} " +
                               $"slip={car.SlipAngle:0}deg yaw={car.YawRate * Mathf.Rad2Deg:0}deg/s steer={car.SteerAngle:0.0} skid={car.Skid:0.00} in=({a.Throttle:0.0},{a.Brake:0.0},{a.Steer:0.0},{a.Handbrake:0}) " +
                               $"pos={car.transform.position:F1} up={car.transform.up.y:0.00}");
        }

        /// <summary>Low side view of the moving car from whichever side has room (never inside a facade).</summary>
        async Task SideShot(PlayerCar car, string name)
        {
            var t = car.transform;
            Vector3 Pos()
            {
                var c = t.position + Vector3.up * 0.9f;
                var best = c + t.right * 2f;
                var bestD = 0f;
                foreach (var side in new[] { 1f, -1f })
                {
                    var dir = (t.right * side * 6.5f + t.forward * 1.5f).normalized;
                    var d = Physics.SphereCast(c, 0.3f, dir, out var h, 6.7f, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore) ? h.distance - 0.4f : 6.7f;
                    if (d > bestD) { bestD = d; best = c + dir * d; }
                }
                return best;
            }
            for (var f = 0; f < 6; f++)
            {
                M.Cam.Cinematic = (Pos(), t.position + Vector3.up * 0.55f, 42);
                await Awaitable.NextFrameAsync();
            }
            await CaptureMoving(car, name);
            M.Cam.Cinematic = null;
        }

        /// <summary>Screenshot of the car in motion: frozen for the (slow, real-time) capture, then it carries on.</summary>
        async Task CaptureMoving(PlayerCar car, string name)
        {
            car.Freeze(true);
            try { await Capture(name); }
            finally { if (car != null) car.Freeze(false); }
        }

        /// <summary>
        /// A building facade near the car with a clear run-up (nothing on the sidewalk in between: lamp posts, bins),
        /// the car placed 15 m out facing it, then full throttle into it.
        /// </summary>
        async Task<bool> WallImpact(PlayerCar car)
        {
            var t = car.transform;
            var best = float.MaxValue;
            Vector3 hitP = default, n = default, startPos = default;
            var mask = CombatLayers.WorldMask | (1 << CombatLayers.IgnoreCamera);
            var half = new Vector3(car.Spec.Size.x * 0.5f, 0.3f, 0.25f);
            var origins = new List<Vector3> { t.position };
            for (var k = 1; k <= 6; k++) { origins.Add(t.position + t.forward * 18f * k); origins.Add(t.position - t.forward * 18f * k); }
            foreach (var o in origins)
                for (var a = 0; a < 16; a++)
                {
                    var d = Quaternion.Euler(0, a * 22.5f, 0) * Vector3.forward;
                    if (!Physics.Raycast(o + Vector3.up * 1.2f, d, out var h, 45f, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore)) continue;
                    if (Mathf.Abs(h.normal.y) > 0.3f || h.distance < 6f) continue;
                    // A wall at least 3 m tall (not a kerb or a bench).
                    if (!Physics.Raycast(h.point + h.normal * 0.3f + Vector3.up * 2.2f, -h.normal, 0.8f, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore)) continue;
                    var nn = new Vector3(h.normal.x, 0, h.normal.z).normalized;
                    var sp = new Vector3(h.point.x, 0, h.point.z) + nn * 15f;
                    var gy = M.World.GroundAt(sp + Vector3.up * 2f, 5);
                    if (!gy.HasValue || Mathf.Abs(gy.Value) > 0.3f) continue;
                    sp.y = gy.Value + 0.05f;
                    var rot = Quaternion.LookRotation(-nn);
                    // Room for the car at the start, and the first thing on the way is the facade itself.
                    if (Physics.CheckBox(sp + Vector3.up * 0.9f, new Vector3(car.Spec.Size.x * 0.55f, 0.55f, car.Spec.Length * 0.55f), rot, mask, QueryTriggerInteraction.Ignore)) continue;
                    var from = sp + Vector3.up * 0.75f + (-nn) * (car.Spec.Length * 0.5f + 0.3f);
                    if (!Physics.BoxCast(from, half, -nn, out var bh, rot, 16f, mask, QueryTriggerInteraction.Ignore)) continue;
                    var wallD = Vector3.Dot(from - h.point, nn);
                    if (bh.distance < wallD - 0.8f) continue;
                    var score = Vector3.Distance(o, t.position) + h.distance;
                    if (score < best) { best = score; hitP = h.point; n = nn; startPos = sp; }
                }
            if (best == float.MaxValue) { errors.Add("driving: no wall with a clear run-up found for the impact test"); return false; }
            car.ResetTo(startPos, Quaternion.LookRotation(-n));
            await Hold(car, 0, 0, 0, 0, () => false, 0.6f);
            var impacts = car.Impacts;
            var maxV = 0f;
            var end = Time.realtimeSinceStartup + 7f;
            var st = 0f;
            var slow = 0f;
            float NoseGap() => Vector3.Dot(car.transform.position + car.transform.forward * (car.Spec.Length * 0.5f) - hitP, n);
            // Until it hits the facade (props on the sidewalk may be hit first: keep going), or gets stuck.
            while (Time.realtimeSinceStartup < end && !(car.Impacts > impacts && NoseGap() < 1.5f) && slow < 1.2f)
            {
                slow = car.ForwardSpeed < 0.5f && Time.realtimeSinceStartup > end - 6f ? slow + Time.deltaTime : 0f;
                // Straight at the wall (steer to hold the heading).
                var err = Vector3.SignedAngle(new Vector3(car.transform.forward.x, 0, car.transform.forward.z), -n, Vector3.up);
                SetInput(1f, 0, Mathf.Clamp(err / 10f, -1f, 1f), 0);
                maxV = Mathf.Max(maxV, car.ForwardSpeed);
                st -= Time.deltaTime;
                if (st <= 0f) { st = 0.1f; Sample("wall"); }
                await Awaitable.NextFrameAsync();
            }
            SetInput(0, 1, 0, 1);
            var hitImpact = car.Impacts > impacts;
            drv["wallSpeedKmh"] = Mathf.Round(maxV * 3.6f);
            drv["wallDeltaV"] = Mathf.Round(car.LastImpact * 10f) / 10f;
            await Seconds(0.25f);
            await Capture("d07_wall_impact");
            await Hold(car, 0, 1, 0, 1, () => car.Speed < 0.3f, 4f);
            // Never through the wall: the car's nose stays on the street side of the facade plane.
            var nose = car.transform.position + car.transform.forward * (car.Spec.Length * 0.5f);
            var depth = Vector3.Dot(nose - hitP, n);
            drv["wallNoseDepth"] = Mathf.Round(depth * 100f) / 100f;
            if (!hitImpact) errors.Add("driving: no impact registered driving into the wall");
            if (depth < -0.6f) errors.Add($"driving: the car went into the wall ({depth:0.00} m past the facade)");
            if (!car.Upright) errors.Add("driving: the car flipped hitting the wall");
            Log($"[drive] wall hit at {maxV * 3.6f:0} km/h, dv {car.LastImpact:0.0} m/s, nose {depth:0.00} m from the facade");
            return hitImpact && depth >= -0.6f;
        }

        void CheckExit(Hero hero, PlayerCar car, string tag)
        {
            var p = hero.Position;
            var ok = true;
            var why = new List<string>();
            if (!hero.gameObject.activeSelf) { ok = false; why.Add("hero hidden"); }
            if (Hero.LastState(hero) != "Move") { ok = false; why.Add("hero state " + Hero.LastState(hero)); }
            const float r = 0.34f;
            var mask = CombatLayers.WorldMask | (1 << CombatLayers.IgnoreCamera);
            foreach (var c in Physics.OverlapCapsule(p + Vector3.up * (r + 0.1f), p + Vector3.up * (1.7f - r), r, mask, QueryTriggerInteraction.Ignore))
            {
                ok = false; why.Add("overlaps " + c.name);
                break;
            }
            if (!Physics.Raycast(p + Vector3.up * 0.5f, Vector3.down, 1.2f, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore)) { ok = false; why.Add("no ground"); }
            if (Physics.Linecast(car.transform.position + Vector3.up * 1f, p + Vector3.up * 1f, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore)) { ok = false; why.Add("wall between car and hero"); }
            var d = Vector3.Distance(new Vector3(p.x, 0, p.z), new Vector3(car.transform.position.x, 0, car.transform.position.z));
            if (d > 6f) { ok = false; why.Add($"{d:0.0} m from the car"); }
            drv["exit_" + tag] = ok ? $"OK {p:F1}, {d:0.0} m from the car, checked spot {Driving.LastExitChecked}" : "FAIL: " + string.Join(", ", why);
            Log($"[drive] exit {tag}: {(ok ? "safe" : string.Join(", ", why))} at {p:F1}");
            if (!ok) errors.Add($"driving: unsafe exit ({tag}): {string.Join(", ", why)}");
        }
    }
}
