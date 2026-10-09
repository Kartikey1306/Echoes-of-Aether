using System;
using System.Collections.Generic;
using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Getting in, driving and getting out of the open city's parked cars (plaza zone only).
    ///   • <see cref="Register"/> (OpenCity.OnLoaded) turns every parked kit car (sedan, coupe, taxi, van) into a
    ///     "Drive" interactable that follows the car wherever it is left. Not offered in combat (locked prompt).
    ///   • Entering: a short fade, the car becomes a <see cref="PlayerCar"/> (physics, rig, lights, audio; it leaves its
    ///     culling cell for good), the hero (and the companion) are set scripted (untargetable, immune) and hidden
    ///     while their transforms ride along with the car, so traffic, crowds, triggers, the minimap and the
    ///     objective marker keep working; the camera switches to its chase mode, the HUD to the speedometer.
    ///   • Driving: device input (or <see cref="AutoInput"/> in tests), interact to get out (the car brakes to a stop
    ///     first), reset to flip it back, horn. Impacts shake the camera, rumble, spark and stop the traffic car hit.
    ///   • Exiting: a free spot next to the car (driver side first, then the other side, rear, front, further out):
    ///     solid ground at the car's level, a clear hero capsule and no wall between car and spot. The car stays.
    ///   • Safety: a cinematic starting, a zone change, the menu, a missing car or player end the drive at once;
    ///     dialogues bring the car to a stop; manual saves are refused while driving and autosaves store the exit spot.
    /// </summary>
    public sealed class Driving : MonoBehaviour
    {
        public sealed class Entry
        {
            public string Id;
            public GameObject Go;
            public VehicleKit.Spec Spec;
            public ZoneInteractable Def;
            public PlayerCar Car;
        }

        /// <summary>Scripted controls for automated tests (used instead of the devices while set). Exit / Reset are
        /// one-shot presses (cleared once read).</summary>
        public struct Inputs
        {
            public float Throttle, Brake, Steer, Handbrake;
            public bool Exit, Reset, Horn;
        }

        static readonly HashSet<string> DrivableNames = new() { "CyberCar_Sedan", "CyberCar_Coupe", "CyberCar_Taxi", "CyberVan" };
        static readonly List<Entry> entries = new();
        static readonly List<PlayerCar> cars = new();
        static Driving inst;
        static Transform vehicleRoot;
        static string zoneAtEnter;
        static Hero driver, passenger;
        static Entry current;
        static bool busy, exitRequested;
        static float enteredAt;
        static Action unsubCine;

        /// <summary>The player is in a car.</summary>
        public static bool Active { get; private set; }
        /// <summary>The car being driven (null on foot).</summary>
        public static PlayerCar Car { get; private set; }
        /// <summary>Every car driven in this zone (they stay where they were left): traffic treats them as obstacles.</summary>
        public static IReadOnlyList<PlayerCar> Cars => cars;
        public static IReadOnlyList<Entry> Entries => entries;
        /// <summary>A get-in / get-out transition is running.</summary>
        public static bool Busy => busy;
        public static bool ExitPending => exitRequested;
        /// <summary>Interactable id of the car being driven (null on foot).</summary>
        public static string CurrentId => current?.Id;
        public static Inputs? AutoInput;
        /// <summary>Last exit (telemetry for tests): where the hero was placed and whether a checked spot was found.</summary>
        public static Vector3 LastExitSpot { get; private set; }
        public static bool LastExitChecked { get; private set; }

        /// <summary>HUD prompt while driving.</summary>
        public static string Prompt => exitRequested ? GameData.T("drive.stopping") : GameData.T("drive.exit");

        // ------------------------------------------------------------------ setup

        public static Driving Ensure()
        {
            if (inst != null) return inst;
            var parent = G.Manager != null ? G.Manager.transform : null;
            var go = new GameObject("Driving");
            if (parent != null) go.transform.SetParent(parent, false);
            else DontDestroyOnLoad(go);
            inst = go.AddComponent<Driving>();
            return inst;
        }

        void Awake()
        {
            if (inst != null && inst != this) { Destroy(gameObject); return; }
            inst = this;
            Subscribe();
        }

        static void Subscribe()
        {
            unsubCine?.Invoke();
            // Synchronous: the cinematic has not moved anyone yet when this runs.
            unsubCine = Bus.On<CinematicStarted>(_ => { if (Active) EndDrive(true); });
        }

        void OnDestroy()
        {
            if (inst != this) return;
            unsubCine?.Invoke();
            unsubCine = null;
            inst = null;
        }

        /// <summary>Make the parked kit cars of the open city drivable (called by OpenCity when the zone has loaded).</summary>
        public static void Register(ZoneRuntime rt, Transform cityRoot)
        {
            Ensure();
            Subscribe(); // (Bus.Clear on a manager restart drops subscriptions)
            ResetState();
            entries.Clear();
            cars.Clear();
            if (rt == null || cityRoot == null) return;
            var vr = new GameObject("PlayerVehicles");
            vr.transform.SetParent(cityRoot, false);
            vehicleRoot = vr.transform;
            foreach (var lg in cityRoot.GetComponentsInChildren<LODGroup>(true))
            {
                var go = lg.gameObject;
                if (!DrivableNames.Contains(go.name) || go.GetComponentInParent<Traffic>() != null) continue;
                var spec = VehicleKit.Get(go.name);
                var e = new Entry { Id = "veh_" + entries.Count, Go = go, Spec = spec };
                e.Def = new ZoneInteractable
                {
                    Id = e.Id, Kind = "vehicle", Position = Anchor(go.transform, spec), Radius = spec.Length * 0.5f + 1.1f, Report = false,
                };
                rt.AddInteractable(e.Def, () => CanEnter(e), () => PromptFor(e), () => Enter(e), () => Locked(e));
                entries.Add(e);
            }
            Debug.Log($"[drive] {entries.Count} parked cars drivable");
        }

        static Vector3 Anchor(Transform t, VehicleKit.Spec spec) => t.position + Vector3.up * 1.0f;

        static bool ZoneOk(GameManager m) => m != null && m.World != null && m.World.ZoneId == "plaza";

        static bool CanEnter(Entry e)
        {
            var m = G.Manager;
            if (Active || busy || e.Go == null || !e.Go.activeSelf || !ZoneOk(m) || !m.PlayerControllable || m.InCombat) return false;
            // Not into a burning (or blown up) car.
            if (e.Go.TryGetComponent<VehicleHealth>(out var vh) && (!vh.Alive || vh.State >= VehicleHealth.Stage.Burning)) return false;
            var p = m.Player;
            return p != null && p.Alive && p.gameObject.activeInHierarchy && p.InMoveState;
        }

        static string Locked(Entry e)
        {
            var m = G.Manager;
            return m != null && m.InCombat && !Active && e.Go != null ? GameData.T("drive.combat") : null;
        }

        static string PromptFor(Entry e) => e.Spec.Name switch
        {
            "CyberCar_Taxi" => GameData.T("drive.prompt.taxi"),
            "CyberCar_Coupe" => GameData.T("drive.prompt.coupe"),
            "CyberVan" => GameData.T("drive.prompt.van"),
            _ => GameData.T("drive.prompt.sedan"),
        };

        // ------------------------------------------------------------------ getting in

        /// <summary>Get into a registered car (interact; tests may call it directly).</summary>
        public static async void Enter(Entry e)
        {
            if (busy || Active || e == null || !CanEnter(e)) return;
            busy = true;
            var m = G.Manager;
            var hero = m.Player;
            var faded = false;
            try
            {
                hero.SetScripted(true);
                hero.FaceTowards(e.Go.transform.position);
                G.Audio?.Play("car_door", e.Go.transform.position + Vector3.up);
                if (m.UI != null) { faded = true; await m.UI.Fade(true, 0.15f); }
                if (e.Go == null || G.Manager != m || m.Mode != GameMode.Play || m.InCinematic || !ZoneOk(m) || m.Player != hero || hero == null || !hero.Alive)
                {
                    if (hero != null) hero.SetScripted(false);
                    return;
                }
                Begin(e, hero);
            }
            catch (Exception ex)
            {
                Debug.LogError("[drive] getting in failed: " + ex);
                ResetState();
                if (hero != null) { hero.gameObject.SetActive(true); hero.SetScripted(false); }
            }
            finally
            {
                busy = false;
                if (faded && m != null && m.UI != null && !m.InCinematic) _ = m.UI.Fade(false, 0.3f);
            }
        }

        static void Begin(Entry e, Hero hero)
        {
            var m = G.Manager;
            if (e.Car == null)
            {
                // Leaves its culling cell for good (it will be driven anywhere), then physics, rig, lights, audio.
                var culler = e.Go.GetComponentInParent<CityCuller>();
                if (culler != null) culler.Release(e.Go.transform);
                if (vehicleRoot != null) e.Go.transform.SetParent(vehicleRoot, true);
            }
            e.Car = PlayerCar.Attach(e.Go, e.Spec);
            if (e.Car == null) throw new Exception("no drivable rig on " + e.Go.name);
            if (!cars.Contains(e.Car)) cars.Add(e.Car);
            var car = e.Car;
            car.Throttle = car.Brake = car.Steer = car.Handbrake = 0f;
            car.Driven = true;
            current = e;
            Car = car;
            driver = hero;
            hero.gameObject.SetActive(false);
            passenger = null;
            var comp = m.Companion;
            if (comp != null && comp != hero && comp.gameObject.activeSelf)
            {
                comp.SetScripted(true);
                comp.gameObject.SetActive(false);
                passenger = comp;
            }
            Active = true;
            exitRequested = false;
            zoneAtEnter = m.World.ZoneId;
            enteredAt = Time.unscaledTime;
            SyncRiders();
            m.Cam.ChaseVehicle(car.Body, e.Spec.Length, e.Spec.Size.y);
            G.Input?.Rumble(0.15f, 0.1f, 0.15f, G.Settings.Data.Controls.Vibration);
            if (G.State != null && !G.State.Flag("tut_drive"))
            {
                G.State.SetFlag("tut_drive");
                m.UI?.Hint("drive");
            }
            Debug.Log($"[drive] driving {e.Go.name} ({e.Id}) from {car.transform.position}");
        }

        // ------------------------------------------------------------------ per frame

        void Update()
        {
            var m = G.Manager;
            if (!Active)
            {
                if (cars.Count > 0) TrackEntries();
                if (EnterKey()) TryEnterNearest();
                return;
            }
            // Anything that ends the drive outright.
            if (m == null || m.Mode != GameMode.Play || Car == null || !Car.gameObject.activeInHierarchy || m.World == null
                || m.World.ZoneId != zoneAtEnter || m.InCinematic || m.Player == null || m.Player != driver)
            {
                EndDrive(true);
                return;
            }
            var car = Car;
            var ctl = m.PlayerControllable && !busy;
            float thr = 0, brk = 0, steer = 0, hb = 0;
            bool exit = false, reset = false, horn = false;
            if (ctl) Read(out thr, out brk, out steer, out hb, out exit, out reset, out horn);
            if (!ctl || exitRequested)
            {
                // Hold: bring the car to a stop (dialogue, transitions, getting out).
                thr = 0; steer = 0; hb = 1;
                brk = car.ForwardSpeed > 0.6f ? 1f : 0f;
                horn = false;
            }
            car.Throttle = thr;
            car.Brake = brk;
            car.Steer = steer;
            car.Handbrake = hb;
            if (car.Audio != null) car.Audio.Horn = horn;
            if (ctl && reset && (car.Speed < 8f || !car.Upright)) car.Recover();
            if (ctl && exit && Time.unscaledTime - enteredAt > 0.4f) RequestExit();
            if (exitRequested && !busy && car.Speed < 2.5f) BeginExit();
            SyncRiders();
            TrackEntries();
        }

        static void Read(out float thr, out float brk, out float steer, out float hb, out bool exit, out bool reset, out bool horn)
        {
            if (AutoInput.HasValue)
            {
                var a = AutoInput.Value;
                thr = Mathf.Clamp01(a.Throttle); brk = Mathf.Clamp01(a.Brake); steer = Mathf.Clamp(a.Steer, -1f, 1f); hb = Mathf.Clamp01(a.Handbrake);
                exit = a.Exit; reset = a.Reset; horn = a.Horn;
                a.Exit = false; a.Reset = false;
                AutoInput = a;
                return;
            }
            var inp = G.Input;
            if (inp == null) { thr = brk = steer = hb = 0; exit = reset = horn = false; return; }
            thr = inp.Value("throttle");
            brk = inp.Value("brake");
            steer = inp.Value("steerRight") - inp.Value("steerLeft");
            hb = inp.Held("handbrake") ? 1f : 0f;
            exit = inp.Pressed("interact") || EnterKey();
            reset = inp.Pressed("vehicleReset");
            horn = inp.Held("horn");
        }

        /// <summary>Enter (or numpad Enter) gets in and out of cars, alongside the interact key.</summary>
        static bool EnterKey()
        {
            var k = UnityEngine.InputSystem.Keyboard.current;
            return !AutoInput.HasValue && k != null && (k.enterKey.wasPressedThisFrame || k.numpadEnterKey.wasPressedThisFrame);
        }

        /// <summary>Get into the nearest drivable car within its interaction reach (Enter key).</summary>
        static void TryEnterNearest()
        {
            var p = G.Manager != null ? G.Manager.Player : null;
            if (p == null) return;
            Entry best = null;
            var bestD = float.MaxValue;
            foreach (var e in entries)
            {
                if (e.Def == null || !CanEnter(e)) continue;
                var d = e.Def.Position - p.transform.position;
                d.y = 0;
                var dist = d.magnitude;
                if (dist <= e.Def.Radius + 0.5f && dist < bestD) { bestD = dist; best = e; }
            }
            if (best != null) Enter(best);
        }

        /// <summary>The hidden hero (and companion) ride along: their transforms follow the car.</summary>
        static void SyncRiders()
        {
            if (Car == null) return;
            var t = Car.transform;
            var f = t.forward; f.y = 0;
            var rot = f.sqrMagnitude > 1e-4f ? Quaternion.LookRotation(f.normalized) : Quaternion.identity;
            var seat = t.position + Vector3.up * 0.15f;
            if (driver != null) driver.transform.SetPositionAndRotation(seat, rot);
            if (passenger != null) passenger.transform.SetPositionAndRotation(seat, rot);
        }

        /// <summary>The "Drive" prompts of moved cars follow them.</summary>
        static void TrackEntries()
        {
            for (var i = 0; i < entries.Count; i++)
            {
                var e = entries[i];
                if (e.Car == null || e.Go == null) continue;
                e.Def.Position = Anchor(e.Go.transform, e.Spec);
            }
        }

        // ------------------------------------------------------------------ getting out

        /// <summary>Get out: at once when (nearly) stopped, else the car brakes to a stop first.</summary>
        public static void RequestExit()
        {
            if (!Active || busy) return;
            exitRequested = true;
        }

        static async void BeginExit()
        {
            if (!Active || busy) return;
            busy = true;
            var m = G.Manager;
            var faded = false;
            try
            {
                G.Audio?.Play("car_door", Car != null ? Car.transform.position + Vector3.up : (Vector3?)null);
                if (m != null && m.UI != null) { faded = true; await m.UI.Fade(true, 0.12f); }
                if (Active) EndDrive(false);
            }
            catch (Exception ex)
            {
                Debug.LogError("[drive] getting out failed: " + ex);
                EndDrive(true);
            }
            finally
            {
                busy = false;
                if (faded && m != null && m.UI != null && !m.InCinematic) _ = m.UI.Fade(false, 0.25f);
            }
        }

        /// <summary>
        /// End the drive: heroes back on foot next to the car (or, when the world is going away, just restored for
        /// the zone loader to place), camera back to the hero. `forced`: no transition (cinematics, zone changes).
        /// </summary>
        static void EndDrive(bool forced)
        {
            if (!Active) return;
            var m = G.Manager;
            var car = Car;
            var placeable = m != null && m.Mode == GameMode.Play && car != null && car.gameObject.activeInHierarchy && driver != null;
            Vector3 spot = default, spot2 = default;
            float yaw = 0, yaw2 = 0;
            var checkedSpot = false;
            if (placeable)
            {
                checkedSpot = ExitSpot(car, out spot, out yaw, null);
                if (!checkedSpot) { spot = driver.LastSafe; yaw = driver.YawDeg; }
                if (passenger != null && !ExitSpot(car, out spot2, out yaw2, spot)) { spot2 = spot; yaw2 = yaw; }
            }
            Active = false;
            exitRequested = false;
            if (car != null)
            {
                car.Driven = false;
                car.Throttle = car.Brake = car.Steer = car.Handbrake = 0f;
                if (car.Audio != null) car.Audio.Horn = false;
            }
            if (m != null && m.Cam != null) m.Cam.StopChase();
            if (driver != null)
            {
                if (placeable)
                {
                    driver.gameObject.SetActive(true);
                    driver.Teleport(spot, yaw);
                }
                else if (m != null && m.Mode == GameMode.Play) driver.gameObject.SetActive(true);
                driver.SetScripted(false);
                if (placeable && m.Cam != null) m.Cam.SnapBehind(m.Cam.Heading);
            }
            if (passenger != null)
            {
                if (placeable)
                {
                    passenger.gameObject.SetActive(true);
                    passenger.Teleport(spot2, yaw2);
                }
                else if (m != null && m.Mode == GameMode.Play) passenger.gameObject.SetActive(true);
                passenger.SetScripted(false);
            }
            LastExitSpot = spot;
            LastExitChecked = checkedSpot;
            if (placeable) Debug.Log($"[drive] out of {car.name} at {spot} ({(checkedSpot ? "checked spot" : "fallback: last safe")}){(forced ? " (forced)" : "")}");
            driver = null;
            passenger = null;
            Car = null;
            current = null;
            AutoInput = null;
        }

        /// <summary>Bail out at once (the car is about to blow up): heroes beside the car, no transition.</summary>
        public static void Eject()
        {
            if (!Active) return;
            EndDrive(true);
        }

        /// <summary>Drop any drive state without placing anyone (zone (re)load; the loader places the heroes).</summary>
        static void ResetState()
        {
            if (Active) EndDrive(true);
            busy = false;
            exitRequested = false;
            Active = false;
            Car = null;
            driver = null;
            passenger = null;
            current = null;
        }

        /// <summary>A car was destroyed (zone unload).</summary>
        public static void Forget(PlayerCar car)
        {
            if (car == null) return;
            if (Car == car) EndDrive(true);
            cars.Remove(car);
        }

        static readonly (float x, float z)[] Slots = { (-1, 0.25f), (1, 0.25f), (-1, -1.1f), (1, -1.1f), (0, -1), (0, 1), (-1, 1.3f), (1, 1.3f) };

        /// <summary>
        /// A free standing spot beside the car: ground at the car's level (no ledges / roofs), the hero's capsule
        /// clear of walls, props and vehicles, and a clear line from the car to it (never through a wall into a
        /// building). Driver side first, then the passenger side, rear, front, then further out.
        /// </summary>
        public static bool ExitSpot(PlayerCar car, out Vector3 pos, out float yawDeg, Vector3? avoid)
        {
            pos = default;
            yawDeg = 0;
            if (car == null) return false;
            var t = car.transform;
            var fwd = t.forward; fwd.y = 0;
            if (fwd.sqrMagnitude < 1e-4f) fwd = Vector3.forward;
            fwd.Normalize();
            var right = Vector3.Cross(Vector3.up, fwd);
            var c = t.position;
            // The ground under the car (it may lie on its roof or side: its pivot is then up in the air).
            var baseY = Physics.Raycast(c + Vector3.up * 3f, Vector3.down, out var under, 8f, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore) ? under.point.y : c.y;
            var hw = car.Spec.Size.x * 0.5f;
            var hl = car.Spec.Length * 0.5f;
            var from = new Vector3(c.x, baseY + 1.0f, c.z);
            var mask = CombatLayers.WorldMask | (1 << CombatLayers.IgnoreCamera) | (1 << CombatLayers.NPC) | (1 << CombatLayers.Enemy);
            foreach (var extra in new[] { 0.8f, 1.5f, 2.4f, 3.4f })
                foreach (var (sx, sz) in Slots)
                {
                    var off = sx != 0 ? right * sx * (hw + extra) + fwd * sz : fwd * sz * (hl + extra);
                    var p = c + off;
                    if (!Physics.Raycast(p + Vector3.up * 2.2f, Vector3.down, out var hit, 4.5f, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore)) continue;
                    if (Mathf.Abs(hit.point.y - baseY) > 1.1f || Vector3.Angle(hit.normal, Vector3.up) > 40f) continue;
                    var feet = hit.point + Vector3.up * 0.03f;
                    if (avoid.HasValue && (feet - avoid.Value).sqrMagnitude < 1.1f * 1.1f) continue;
                    const float r = 0.38f;
                    if (Physics.CheckCapsule(feet + Vector3.up * (r + 0.06f), feet + Vector3.up * (1.78f - r), r, mask, QueryTriggerInteraction.Ignore)) continue;
                    if (Physics.Linecast(from, feet + Vector3.up * 1.0f, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore)) continue;
                    pos = feet;
                    var face = feet - c; face.y = 0;
                    // Face along the car (like stepping out of it) on the sides, away from it at the ends.
                    var dir = sx != 0 ? fwd : face.normalized;
                    yawDeg = Mathf.Atan2(dir.x, dir.z) * Mathf.Rad2Deg;
                    return true;
                }
            return false;
        }

        /// <summary>Where a save made while driving puts the hero (beside the car, on foot).</summary>
        public static bool SaveSpot(out Vector3 pos, out float yawDeg)
        {
            pos = default;
            yawDeg = 0;
            if (!Active || Car == null) return false;
            if (ExitSpot(Car, out pos, out yawDeg, null)) return true;
            if (driver == null) return false;
            pos = driver.LastSafe;
            yawDeg = driver.YawDeg;
            return true;
        }

        // ------------------------------------------------------------------ impacts

        public static void OnImpact(PlayerCar car, Collider other, float dv, Vector3 point)
        {
            var k = Mathf.Clamp01((dv - 1.2f) / 10f);
            G.Audio?.Play("car_impact", point, 0.25f + 0.75f * k, UnityEngine.Random.Range(0.92f, 1.08f));
            if (car != null && car == Car)
            {
                var cam = G.Manager != null ? G.Manager.Cam : null;
                if (cam != null)
                {
                    cam.AddTrauma(Mathf.Min(0.5f, 0.06f + k * 0.45f));
                    var d = point - car.transform.position;
                    cam.Kick(d.sqrMagnitude > 1e-4f ? d.normalized : car.transform.forward, 0.1f + 0.4f * k, -1.2f * k);
                }
                G.Input?.Rumble(0.25f + 0.6f * k, 0.15f + 0.7f * k, 0.1f + 0.2f * k, G.Settings.Data.Controls.Vibration);
            }
            if (dv > 3f) VfxManager.Instance?.Sparks(point, new Color(1f, 0.7f, 0.32f), 6 + (int)(k * 14), 6f);
            Traffic.Bump(other);
            // Crash damage: hard hits wreck cars (yours and whatever you hit); a ~50 km/h head-on costs about 45 %.
            if (dv > 5f)
            {
                var k5 = (dv - 5f) * 0.05f;
                if (car != null && car.TryGetComponent<VehicleHealth>(out var own)) own.Damage(own.Max * k5, point);
                var hit = other != null ? other.GetComponentInParent<VehicleHealth>() : null;
                if (hit != null && (car == null || hit.gameObject != car.gameObject)) hit.Damage(hit.Max * k5 * 0.8f, point);
            }
        }
    }
}
