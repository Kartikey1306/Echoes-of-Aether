using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Physics of the car the player drives: arcade-realistic handling on a Rigidbody with sphere-cast suspension
    /// (Unity's WheelColliders jitter at the 50 Hz step and fight a tuned arcade feel).
    ///   • Suspension: one sphere cast per wheel from above its rest pose, spring / bump / rebound damper per wheel,
    ///     anti-roll bars and bump stops: the body rolls in corners, dives under braking, squats under power and
    ///     the wheels climb kerbs (the body colliders are raised off the road so only the wheels touch it).
    ///   • Tyres: lateral grip from the contact patch velocity, saturating at load x grip (past it the car slides),
    ///     a friction circle shared with drive and brakes, front / rear drive split, engine braking, aero drag and a
    ///     little downforce; speed-sensitive steering; the handbrake locks the rear wheels and drops their side grip
    ///     (drift), a light yaw-stability assist otherwise; brake pedal reverses once stopped.
    ///   • Air control levels the car on jumps; flip / stuck detection and <see cref="Recover"/> (auto after a few
    ///     seconds on its roof, or the reset action); falls into the canal / under the world restore the last safe pose.
    ///   • Feeds <see cref="VehicleRig"/> the real wheel state (spin incl. wheelspin and locked wheels, steering,
    ///     suspension travel), brake lights, headlights (+ beams and a real spot light at night) and <see cref="CarAudio"/>.
    /// Without a driver it brakes, settles and turns kinematic again: only the driven car costs physics.
    /// Vehicle space: front +Z, pivot at the ground centre (kit convention).
    /// </summary>
    [DisallowMultipleComponent]
    public sealed class PlayerCar : MonoBehaviour
    {
        sealed class Wheel
        {
            public int RigIndex;
            public Vector3 Local;      // rest centre, vehicle space
            public float R;
            public bool Front, Left;
            public bool Grounded;
            public float X, PrevX;     // compression from full droop (m)
            public float Load;         // suspension force (N)
            public Vector3 Point, Normal;
            public float Omega;        // rad/s, + rolls forward (visual / audio)
            public float Slip;         // sliding speed at the contact (m/s)
            public Collider Ground;
        }

        sealed class Tuning
        {
            public float Mass = 1350, Accel = 6.6f, TopSpeed = 50f, Grip = 1.25f, SteerLow = 34f, SteerHigh = 7.5f;
            public float ComY = 0.42f, FrontDrive = 0.35f, Brake = 1.05f, Freq = 1.55f, Assist = 1.2f;
        }

        static Tuning TuningFor(VehicleKit.Spec s) => s.Name switch
        {
            "CyberCar_Coupe" => new Tuning { Mass = 1240, Accel = 7.8f, TopSpeed = 57f, Grip = 1.32f, SteerLow = 35f, SteerHigh = 7f, ComY = 0.36f, FrontDrive = 0.25f, Freq = 1.75f },
            "CyberCar_Taxi" => new Tuning { Mass = 1420, Accel = 6.2f, TopSpeed = 48f, Grip = 1.22f, ComY = 0.48f, FrontDrive = 0.4f, Freq = 1.5f },
            "CyberVan" => new Tuning { Mass = 1950, Accel = 5.0f, TopSpeed = 41f, Grip = 1.12f, SteerLow = 32f, SteerHigh = 8f, ComY = 0.62f, FrontDrive = 0.5f, Freq = 1.35f, Assist = 1.6f },
            _ => new Tuning(),
        };

        /// <summary>Suspension travel above (bump) and below (droop) the modelled wheel position (m).</summary>
        public const float Bump = 0.15f, Droop = 0.1f;
        public const float MaxReverse = 11f;
        const float RearGrip = 1.1f;
        /// <summary>Lowest body collider edge (m above the road): kerbs and small debris are the wheels' business.</summary>
        const float BodyFloor = 0.3f;
        static PhysicsMaterial bodyMat;
        static readonly RaycastHit[] hits = new RaycastHit[12];

        /// <summary>What the wheels stand on: level geometry and other vehicles.</summary>
        public static int GroundMask => CombatLayers.WorldMask | (1 << CombatLayers.IgnoreCamera);

        // ---------------------------------------------------------------- driver inputs (set every frame)

        /// <summary>Pedals 0..1, steering -1..1 (+ = right), handbrake 0..1.</summary>
        [System.NonSerialized] public float Throttle, Brake, Steer, Handbrake;
        /// <summary>Someone is at the wheel. Without a driver the car brakes, settles and goes kinematic.</summary>
        [System.NonSerialized] public bool Driven;

        // ---------------------------------------------------------------- state / telemetry

        public VehicleKit.Spec Spec { get; private set; }
        public VehicleRig Rig { get; private set; }
        public Rigidbody Body { get; private set; }
        public CarAudio Audio { get; private set; }
        /// <summary>Signed speed along the car's heading (m/s).</summary>
        public float ForwardSpeed { get; private set; }
        public float Speed => Body != null && !Body.isKinematic ? Body.linearVelocity.magnitude : 0f;
        public int GroundedWheels { get; private set; }
        public int WheelCount => wheels != null ? wheels.Length : 0;
        public bool WheelGrounded(int i) => wheels[i].Grounded;
        public float WheelCompression(int i) => wheels[i].X;
        public float WheelLoad(int i) => wheels[i].Load;
        /// <summary>Front-wheel angle (degrees, + = right).</summary>
        public float SteerAngle { get; private set; }
        /// <summary>Angle between heading and travel (degrees; + = sliding to the right).</summary>
        public float SlipAngle { get; private set; }
        /// <summary>Tyre squeal 0..1 (sliding, locked or spinning wheels).</summary>
        public float Skid { get; private set; }
        public float Rpm01 { get; private set; }
        /// <summary>-1 reverse, 0 neutral (stopped), 1..5.</summary>
        public int Gear { get; private set; }
        public bool Reversing { get; private set; }
        public bool Braking { get; private set; }
        public float YawRate { get; private set; }
        public bool Upright => transform.up.y > 0.45f;
        public bool Parked => Body == null || Body.isKinematic;
        public float TopSpeed => tune.TopSpeed;
        public int Impacts { get; private set; }
        public float LastImpact { get; private set; }
        public float LastImpactTime { get; private set; } = -10f;
        public int Recoveries { get; private set; }
        public Vector3 SafePosition => safePos;

        Tuning tune = new();
        Wheel[] wheels;
        int frontCount, rearCount;
        int[] axleL, axleR;
        float k, cBump, cReb, antiRoll, dragK, wheelBase;
        float stuckT, safeT, lowT, settleT, driftT, gearT;
        Vector3 safePos;
        Quaternion safeRot;
        bool hasSafe;
        Light beam;
        Renderer headFx, tailFx;
        bool tailBrake;
        SkidMarks marks;
        float smokeT;

        // ---------------------------------------------------------------- setup

        /// <summary>Make a kit car drivable (once) and wake it. Returns null for vehicles without wheels.</summary>
        public static PlayerCar Attach(GameObject go, VehicleKit.Spec spec)
        {
            if (go == null || spec == null) return null;
            var car = go.GetComponent<PlayerCar>();
            if (car == null)
            {
                car = go.AddComponent<PlayerCar>();
                if (!car.Init(spec)) { Destroy(car); return null; }
            }
            car.Wake();
            return car;
        }

        bool Init(VehicleKit.Spec spec)
        {
            Spec = spec;
            tune = TuningFor(spec);
            Rig = GetComponent<VehicleRig>();
            if (Rig == null)
            {
                Rig = gameObject.AddComponent<VehicleRig>();
                Rig.Setup(spec, new System.Random(GetInstanceID()));
            }
            if (Rig.WheelCount < 3) return false;
            Rig.External = true;
            Rig.FullDistance = 400f;
            Rig.CullDistance = 900f;

            // Wheels (rest pose from the model).
            var n = Rig.WheelCount;
            wheels = new Wheel[n];
            float zMin = float.MaxValue, zMax = float.MinValue;
            for (var i = 0; i < n; i++)
            {
                var wt = Rig.WheelTransform(i);
                var local = transform.InverseTransformPoint(wt.position);
                wheels[i] = new Wheel { RigIndex = i, Local = local, R = Rig.WheelRadius(i), Front = Rig.WheelName(i).StartsWith("Wheel_F"), Left = local.x < 0 };
                if (wheels[i].Front) frontCount++; else rearCount++;
                zMin = Mathf.Min(zMin, local.z); zMax = Mathf.Max(zMax, local.z);
            }
            wheelBase = Mathf.Max(1.5f, zMax - zMin);
            int fl = -1, fr = -1, rl = -1, rr = -1;
            for (var i = 0; i < n; i++)
            {
                var w = wheels[i];
                if (w.Front) { if (w.Left) fl = i; else fr = i; }
                else { if (w.Left) rl = i; else rr = i; }
            }
            axleL = new[] { fl, rl };
            axleR = new[] { fr, rr };

            // Body colliders: raised off the road, slippery against walls, on IgnoreCamera (the chase camera never hits its own car).
            if (bodyMat == null)
                bodyMat = new PhysicsMaterial("car_body")
                {
                    dynamicFriction = 0.18f, staticFriction = 0.22f, bounciness = 0.06f,
                    frictionCombine = PhysicsMaterialCombine.Minimum, bounceCombine = PhysicsMaterialCombine.Average,
                };
            var any = false;
            foreach (var col in GetComponentsInChildren<Collider>(true))
            {
                if (col.isTrigger) continue;
                any = true;
                col.gameObject.layer = CombatLayers.IgnoreCamera;
                col.sharedMaterial = bodyMat;
                if (col is BoxCollider bc)
                {
                    var c = bc.center; var sz = bc.size;
                    float bottom = c.y - sz.y * 0.5f, top = c.y + sz.y * 0.5f;
                    if (bottom < BodyFloor && top > BodyFloor + 0.25f)
                    {
                        bottom = BodyFloor;
                        bc.center = new Vector3(c.x, (bottom + top) * 0.5f, c.z);
                        bc.size = new Vector3(sz.x, top - bottom, sz.z);
                    }
                }
            }
            if (!any)
            {
                var bc = gameObject.AddComponent<BoxCollider>();
                bc.center = new Vector3(0, (BodyFloor + spec.Size.y * 0.8f) * 0.5f, 0);
                bc.size = new Vector3(spec.Size.x * 0.95f, spec.Size.y * 0.8f - BodyFloor, spec.Size.z * 0.96f);
                bc.sharedMaterial = bodyMat;
                gameObject.layer = CombatLayers.IgnoreCamera;
            }

            // Rigidbody.
            Body = GetComponent<Rigidbody>();
            if (Body == null) Body = gameObject.AddComponent<Rigidbody>();
            var m = tune.Mass;
            Body.mass = m;
            Body.linearDamping = 0.02f;
            Body.angularDamping = 0.3f;
            Body.useGravity = true;
            Body.interpolation = RigidbodyInterpolation.Interpolate;
            Body.collisionDetectionMode = CollisionDetectionMode.ContinuousDynamic;
            Body.maxAngularVelocity = 14f;
            Body.solverIterations = 10;
            Body.centerOfMass = new Vector3(0, tune.ComY, 0.05f);
            float L = spec.Size.z, W = spec.Size.x, H = Mathf.Min(spec.Size.y, 1.6f);
            Body.inertiaTensor = new Vector3(m / 12f * (H * H + L * L), m / 12f * (W * W + L * L) * 0.9f, m / 12f * (W * W + H * H) * 1.1f);
            Body.inertiaTensorRotation = Quaternion.identity;

            // Suspension: rest pose = modelled wheel position, ride frequency per car, ~0.4 damping ratio.
            var g = -Physics.gravity.y;
            var wm = m / n;
            k = wm * g / Droop;
            var omega = 2f * Mathf.PI * tune.Freq;
            k = Mathf.Max(k, wm * omega * omega);
            var cc = 2f * Mathf.Sqrt(k * wm);
            cBump = cc * 0.32f;
            cReb = cc * 0.5f;
            antiRoll = k * 0.55f;
            dragK = 0.28f * m * tune.Accel / (tune.TopSpeed * tune.TopSpeed);

            Audio = gameObject.AddComponent<CarAudio>();
            Audio.Init(this);

            // Night lights: flare / beam / pool meshes (as street traffic) and one real spot light for the road.
            (headFx, tailFx) = Traffic.LightFx(transform, spec);
            var lg = new GameObject("HeadlightBeam");
            lg.transform.SetParent(transform, false);
            lg.transform.localPosition = new Vector3(0, (spec.HeadL.y + spec.HeadR.y) * 0.5f + 0.05f, Mathf.Max(spec.HeadL.z, spec.HeadR.z) + 0.15f);
            lg.transform.localRotation = Quaternion.Euler(7.5f, 0, 0);
            beam = lg.AddComponent<Light>();
            beam.type = LightType.Spot;
            beam.range = 42f;
            beam.spotAngle = 72f;
            beam.innerSpotAngle = 38f;
            beam.color = new Color(0.86f, 0.92f, 1f);
            beam.intensity = 0f;
            beam.shadows = LightShadows.None;
            beam.enabled = false;
            return true;
        }

        Vector3 frozenV, frozenW;
        /// <summary>Held in place by <see cref="Freeze"/> (tests).</summary>
        public bool Frozen { get; private set; }

        /// <summary>Hold the car exactly as it is (tests: screenshots in motion), then resume with its velocity.</summary>
        public void Freeze(bool on)
        {
            if (Body == null || on == Frozen) return;
            if (on && Body.isKinematic) return;
            Frozen = on;
            if (on)
            {
                frozenV = Body.linearVelocity;
                frozenW = Body.angularVelocity;
                Body.isKinematic = true;
            }
            else
            {
                Body.isKinematic = false;
                Body.linearVelocity = frozenV;
                Body.angularVelocity = frozenW;
            }
        }

        /// <summary>Make it dynamic again (getting in).</summary>
        public void Wake()
        {
            if (Body == null) return;
            if (Body.isKinematic)
            {
                Body.isKinematic = false;
                Body.linearVelocity = Vector3.zero;
                Body.angularVelocity = Vector3.zero;
            }
            Body.WakeUp();
            if (marks == null) marks = SkidMarks.For(transform.parent);
            settleT = 0;
            stuckT = 0;
            Rig.External = true;
            Rig.Headlights = VehicleRig.Lamp.Auto;
            if (!hasSafe && Upright) { safePos = transform.position; safeRot = transform.rotation; hasSafe = true; }
        }

        // ---------------------------------------------------------------- physics

        void FixedUpdate()
        {
            if (Body == null || Body.isKinematic || wheels == null) return;
            var dt = Time.fixedDeltaTime;
            var t = transform;
            var up = t.up;
            var fwd = t.forward;
            var v = Body.linearVelocity;
            var speed = v.magnitude;
            ForwardSpeed = Vector3.Dot(v, fwd);
            YawRate = Vector3.Dot(Body.angularVelocity, up);
            // Slip angle: heading vs travel (telemetry, drift limiter; > 90 when sliding backwards).
            var flatV = new Vector3(v.x, 0, v.z);
            var flatF = new Vector3(fwd.x, 0, fwd.z);
            SlipAngle = flatV.sqrMagnitude > 4f && flatF.sqrMagnitude > 0.01f ? Vector3.SignedAngle(flatF, flatV, Vector3.up) : 0f;

            // ---- driver
            float thr = 0f, brk = 1f, hb = 1f, steerIn = 0f;
            if (Driven)
            {
                thr = Mathf.Clamp01(Throttle);
                brk = Mathf.Clamp01(Brake);
                hb = Mathf.Clamp01(Handbrake);
                steerIn = Mathf.Clamp(Steer, -1f, 1f);
            }
            // Brake pedal reverses once (nearly) stopped; throttle brakes a backwards roll first.
            if (Driven && !Reversing && brk > 0.1f && thr < 0.1f && ForwardSpeed < 0.6f) Reversing = true;
            else if (Reversing && (!Driven || (thr > 0.1f && ForwardSpeed > -0.6f))) Reversing = false;
            float drive, service;
            if (Reversing)
            {
                drive = -brk;
                service = ForwardSpeed < -0.6f ? thr : 0f;
            }
            else
            {
                drive = thr;
                service = Driven ? (ForwardSpeed > 0.6f || thr < 0.1f ? brk : 0f) : 1f;
            }
            Braking = service > 0.1f;
            var vmax = Reversing ? MaxReverse : tune.TopSpeed;
            var sp01 = Mathf.Clamp01(Mathf.Abs(ForwardSpeed) / vmax);
            var engine = tune.Mass * tune.Accel * (1f - sp01 * sp01 * sp01) * (Reversing ? 0.6f : 1f);
            // Launch: a touch more shove off the line (feels punchy, still traction limited).
            if (!Reversing && Mathf.Abs(ForwardSpeed) < 8f) engine *= 1.15f;
            var driveForce = drive * engine;

            // ---- steering (speed sensitive; rate limited so keys feel analog)
            var limit = Mathf.Lerp(tune.SteerLow, tune.SteerHigh, Mathf.Pow(Mathf.Clamp01(Mathf.Abs(ForwardSpeed) / 42f), 0.75f));
            if (hb > 0.5f) limit = Mathf.Max(limit, tune.SteerLow * 0.75f); // handbrake turns: more lock
            var target = steerIn * limit;
            var rate = Mathf.Abs(target) < Mathf.Abs(SteerAngle) || target * SteerAngle < 0 ? 190f : 125f;
            SteerAngle = Mathf.MoveTowards(SteerAngle, target, rate * dt);

            // ---- suspension
            var grounded = 0;
            var totalLoad = 0f;
            for (var i = 0; i < wheels.Length; i++)
            {
                var w = wheels[i];
                var anchor = t.TransformPoint(w.Local + Vector3.up * Bump);
                var castR = w.R * 0.6f;
                var travel = Bump + Droop;
                var maxD = travel + (w.R - castR);
                w.Grounded = Cast(anchor, castR, -up, maxD, out var hit);
                if (w.Grounded)
                {
                    var len = Mathf.Clamp(hit.distance - (w.R - castR), 0f, travel);
                    w.X = travel - len;
                    var cv = (w.X - w.PrevX) / dt;
                    var f = k * w.X + (cv > 0 ? cBump * cv : cReb * cv);
                    if (len < 0.03f) f += k * 4f * (0.03f - len) / 0.03f; // bump stop
                    w.Load = Mathf.Clamp(f, 0f, tune.Mass * 9.81f * 2.5f);
                    w.Point = hit.point;
                    w.Normal = Vector3.Dot(hit.normal, up) > 0.55f ? hit.normal : up;
                    w.Ground = hit.collider;
                    Body.AddForceAtPosition(up * w.Load, anchor);
                    grounded++;
                    totalLoad += w.Load;
                }
                else
                {
                    w.X = 0f;
                    w.Load = 0f;
                    w.Ground = null;
                }
                w.PrevX = w.X;
            }
            GroundedWheels = grounded;
            // Anti-roll bars.
            for (var a = 0; a < 2; a++)
            {
                int l = axleL[a], r = axleR[a];
                if (l < 0 || r < 0) continue;
                var arf = (wheels[l].X - wheels[r].X) * antiRoll;
                if (wheels[l].Grounded) Body.AddForceAtPosition(up * arf, t.TransformPoint(wheels[l].Local));
                if (wheels[r].Grounded) Body.AddForceAtPosition(-up * arf, t.TransformPoint(wheels[r].Local));
            }

            // ---- tyres
            var frontDir = Quaternion.AngleAxis(SteerAngle, up) * fwd;
            var skid = 0f;
            var traction = false;
            for (var i = 0; i < wheels.Length; i++)
            {
                var w = wheels[i];
                if (!w.Grounded || totalLoad <= 1f)
                {
                    if (marks != null) marks.Mark(i, Vector3.zero, Vector3.up, Vector3.right, 0f, 0f);
                    // Airborne wheels coast (and spin up under throttle).
                    var driven = w.Front ? tune.FrontDrive > 0.01f : tune.FrontDrive < 0.99f;
                    w.Omega = Mathf.MoveTowards(w.Omega, driven && Driven && thr > 0.2f ? 60f : 0f, dt * 25f);
                    w.Slip = 0;
                    continue;
                }
                var n = w.Normal;
                var f = Vector3.ProjectOnPlane(w.Front ? frontDir : fwd, n).normalized;
                var s = Vector3.Cross(n, f);
                var pv = Body.GetPointVelocity(w.Point);
                // Moving ground (a car underneath): relative velocity.
                if (w.Ground != null && w.Ground.attachedRigidbody != null && w.Ground.attachedRigidbody != Body) pv -= w.Ground.attachedRigidbody.GetPointVelocity(w.Point);
                var vL = Vector3.Dot(pv, f);
                var vS = Vector3.Dot(pv, s);
                var mEff = Body.mass * (w.Load / totalLoad);
                var mu = tune.Grip;
                var locked = !w.Front && hb > 0.5f;

                var stopF = Mathf.Abs(vL) * mEff / dt;
                var sideStop = Mathf.Abs(vS) * mEff / dt * 0.55f;
                float fx, fy;
                if (locked)
                {
                    // Handbrake: the locked rear wheels slide. Kinetic friction opposes the sliding direction as a whole
                    // (mostly along the car at first, so the tail steps out instead of the car just scrubbing speed).
                    var slide = Mathf.Sqrt(vL * vL + vS * vS);
                    var kin = mu * 0.62f * w.Load;
                    var inv = 1f / Mathf.Max(slide, 0.6f);
                    fx = -Mathf.Sign(vL) * Mathf.Min(kin * Mathf.Abs(vL) * inv, stopF);
                    fy = -Mathf.Sign(vS) * Mathf.Min(kin * Mathf.Abs(vS) * inv, sideStop);
                }
                else
                {
                    // Lateral: cancel the side slip, up to the grip limit (kinetic grip once well into a slide).
                    var latMu = mu * Mathf.Lerp(1f, 0.8f, Mathf.InverseLerp(1.5f, 7f, Mathf.Abs(vS)));
                    // A little more grip at the rear (stable at the limit: it understeers unless you provoke it);
                    // just off the handbrake the rear stays loose so the slide can be held.
                    if (!w.Front) latMu *= RearGrip * (driftT > 0f ? Mathf.Lerp(1f, 0.74f, driftT) : 1f);
                    fy = Mathf.Clamp(-vS * mEff / dt * 0.55f, -latMu * w.Load, latMu * w.Load);
                    // Longitudinal: drive, brakes, coast.
                    var share = w.Front ? tune.FrontDrive / Mathf.Max(1, frontCount) : (1f - tune.FrontDrive) / Mathf.Max(1, rearCount);
                    fx = driveForce * share;
                    var brakeF = service * tune.Mass * 9.81f * tune.Brake * (w.Front ? 0.6f : 0.4f) / Mathf.Max(1, w.Front ? frontCount : rearCount);
                    if (Mathf.Abs(drive) < 0.05f) brakeF += mEff * (0.45f + 0.012f * Mathf.Abs(vL)); // engine braking + rolling
                    fx -= Mathf.Sign(vL) * Mathf.Min(brakeF, stopF);
                }
                // Friction circle.
                var maxF = mu * w.Load;
                var mag = Mathf.Sqrt(fx * fx + fy * fy);
                var spinning = false;
                if (mag > maxF && mag > 1e-3f)
                {
                    var kk = maxF / mag;
                    if (Mathf.Abs(fx) > Mathf.Abs(fy) && Mathf.Abs(driveForce) > 1f) spinning = true;
                    fx *= kk; fy *= kk;
                }
                if (spinning) traction = true;
                // Applied a little above the contact patch: body roll without tipping the car over.
                Body.AddForceAtPosition(f * fx + s * fy, w.Point + n * 0.12f);

                // Visual wheel speed and squeal.
                var roll = vL / w.R;
                if (locked || (service > 0.9f && Mathf.Abs(vL) > 6f && !w.Front && Driven)) w.Omega = Mathf.MoveTowards(w.Omega, 0f, dt * 200f);
                else if (spinning && Mathf.Abs(drive) > 0.3f) w.Omega = Mathf.MoveTowards(w.Omega, roll + Mathf.Sign(drive) * 30f, dt * 120f);
                else w.Omega = roll;
                w.Slip = Mathf.Abs(vS) + (locked ? Mathf.Abs(vL) : 0f) + (spinning ? 6f : 0f);
                skid = Mathf.Max(skid, Mathf.InverseLerp(2.2f, 8f, w.Slip));
                if (marks != null) marks.Mark(i, w.Point, n, s, w.R * 0.6f, speed > 2f ? Mathf.InverseLerp(3f, 9f, w.Slip) : 0f);
            }
            Skid = Mathf.MoveTowards(Skid, speed > 1.5f || traction ? skid : 0f, dt * 6f);

            // ---- aero, downforce
            Body.AddForce(-v * speed * dragK);
            if (grounded > 0) Body.AddForce(-up * tune.Mass * 0.0016f * speed * speed);

            // ---- stability: yaw assist off the handbrake (none while drifting on purpose), air control
            if (hb > 0.5f && Mathf.Abs(ForwardSpeed) > 4f) driftT = 1f;
            else driftT = Mathf.MoveTowards(driftT, 0f, dt / 0.9f);
            if (grounded >= 3 && speed > 3f && Driven)
            {
                // Target yaw rate from the steering (bicycle model), never more than the tyres can hold.
                var desired = ForwardSpeed * Mathf.Tan(SteerAngle * Mathf.Deg2Rad) / wheelBase;
                var cap = 0.85f * tune.Grip * 9.81f / Mathf.Max(Mathf.Abs(ForwardSpeed), 3f);
                desired = Mathf.Clamp(desired, -cap, cap);
                var excess = YawRate - desired;
                var assist = tune.Assist * (1f - driftT) * (hb > 0.5f ? 0f : 1f);
                if (assist > 0f) Body.AddTorque(-up * excess * assist, ForceMode.Acceleration);
            }
            // Drift angle limiter: past ~35 deg of slide, rotation that opens it further is damped (big, holdable
            // drifts instead of spinning out); the handbrake can still swing the car round at low speed.
            if (grounded >= 2 && Driven && ForwardSpeed > 4f && YawRate * SlipAngle < 0f)
            {
                var over = Mathf.InverseLerp(32f, 65f, Mathf.Abs(SlipAngle)) * (hb > 0.5f ? 0.6f : 1f);
                if (over > 0f) Body.AddTorque(-up * YawRate * over * 7f, ForceMode.Acceleration);
            }
            if (grounded == 0)
            {
                // Keep the nose roughly level in the air and damp tumbling (lands on its wheels).
                var axis = Vector3.Cross(up, Vector3.up);
                var w = Body.angularVelocity;
                var yawPart = Vector3.Project(w, Vector3.up);
                Body.AddTorque(axis * 5f - (w - yawPart) * 1.2f, ForceMode.Acceleration);
            }

            Engine(dt, thr, drive);
            Safety(dt, speed, grounded);
        }

        bool Cast(Vector3 origin, float radius, Vector3 dir, float dist, out RaycastHit best)
        {
            best = default;
            var n = Physics.SphereCastNonAlloc(origin, radius, dir, hits, dist, GroundMask, QueryTriggerInteraction.Ignore);
            var bestD = float.MaxValue;
            for (var i = 0; i < n; i++)
            {
                var h = hits[i];
                if (h.collider == null || h.distance <= 0f) continue;
                if (h.rigidbody == Body || h.collider.transform.IsChildOf(transform)) continue;
                if (h.distance < bestD) { bestD = h.distance; best = h; }
            }
            return bestD < float.MaxValue;
        }

        // ---------------------------------------------------------------- engine (audio / HUD model)

        static readonly float[] GearTop = { 0.2f, 0.36f, 0.54f, 0.75f, 1.02f };

        void Engine(float dt, float thr, float drive)
        {
            var v = Mathf.Abs(ForwardSpeed);
            var vmax = tune.TopSpeed;
            int gear;
            float rpm;
            if (Reversing && ForwardSpeed < 0.3f) { gear = -1; rpm = Mathf.Lerp(0.18f, 0.85f, v / MaxReverse); }
            else if (v < 0.4f && Mathf.Abs(drive) < 0.05f) { gear = 0; rpm = 0.12f; }
            else
            {
                gear = Mathf.Max(1, Gear);
                gearT -= dt;
                var u = v / vmax;
                // Shift up near the top of the gear, down well below the previous one (hysteresis + shift delay).
                if (gearT <= 0f && gear < GearTop.Length && u > GearTop[gear - 1] * 0.97f) { gear++; gearT = 0.35f; }
                else if (gearT <= 0f && gear > 1 && u < GearTop[gear - 2] * 0.72f) { gear--; gearT = 0.3f; }
                var lo = gear > 1 ? GearTop[gear - 2] * 0.55f : 0f;
                rpm = Mathf.Lerp(0.16f, 1f, Mathf.InverseLerp(lo, GearTop[gear - 1], u));
            }
            if (gear <= 0 && thr > 0.1f) rpm = Mathf.Max(rpm, 0.2f + thr * 0.55f); // revving
            if (Skid > 0.5f && thr > 0.5f) rpm = Mathf.Max(rpm, 0.85f);           // wheelspin
            Gear = gear;
            Rpm01 = Mathf.MoveTowards(Rpm01, Mathf.Clamp01(rpm), dt * (rpm > Rpm01 ? 3.2f : 2.2f));
        }

        // ---------------------------------------------------------------- safety: flips, falls, settling

        void Safety(float dt, float speed, int grounded)
        {
            // Last safe pose: upright, all wheels down, on solid level-ish ground.
            safeT -= dt;
            if (safeT <= 0f && grounded == wheels.Length && Upright && transform.up.y > 0.9f && transform.position.y > -1f)
            {
                safeT = 0.5f;
                safePos = transform.position;
                safeRot = Quaternion.Euler(0, transform.eulerAngles.y, 0);
                hasSafe = true;
            }
            // On its roof / side (or wedged without wheel contact) for a few seconds: put it back on its wheels.
            if ((!Upright || grounded == 0) && speed < 1.2f) stuckT += dt;
            else stuckT = 0f;
            if (stuckT > 2.5f) { Recover(); return; }
            // Fell into the canal / below the street level.
            if (transform.position.y < -1.6f || transform.position.y < (G.Manager != null ? G.Manager.KillY : -50f)) lowT += dt;
            else lowT = 0f;
            if (lowT > 1.0f && hasSafe) { ResetTo(safePos, safeRot); return; }
            // Parking: no driver, stopped: freeze (kinematic) until someone gets in again.
            if (!Driven)
            {
                settleT = speed < 0.25f && Body.angularVelocity.sqrMagnitude < 0.05f ? settleT + dt : 0f;
                if (settleT > 0.6f || (settleT > 0f && !Upright))
                {
                    if (!Upright) Recover();
                    Body.linearVelocity = Vector3.zero;
                    Body.angularVelocity = Vector3.zero;
                    Body.isKinematic = true;
                    GroundedWheels = 0;
                    Skid = 0;
                }
            }
        }

        /// <summary>Back on its wheels where it is (same heading), or at the last safe pose if that spot is blocked.</summary>
        public void Recover()
        {
            if (Body == null) return;
            Recoveries++;
            var p = transform.position;
            var fwd = transform.forward; fwd.y = 0;
            if (fwd.sqrMagnitude < 0.01f) fwd = transform.up.y < 0 ? transform.up : Vector3.forward;
            var rot = Quaternion.LookRotation(new Vector3(fwd.x, 0, fwd.z).normalized, Vector3.up);
            var probe = p + Vector3.up * 3f;
            float? ground = null;
            var n = Physics.RaycastNonAlloc(probe, Vector3.down, hits, 8f, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore);
            var best = float.MaxValue;
            for (var i = 0; i < n; i++)
                if (hits[i].distance < best && !hits[i].collider.transform.IsChildOf(transform)) { best = hits[i].distance; ground = hits[i].point.y; }
            if (ground.HasValue && Fits(new Vector3(p.x, ground.Value + 0.25f, p.z), rot)) ResetTo(new Vector3(p.x, ground.Value + 0.25f, p.z), rot);
            else if (hasSafe) ResetTo(safePos + Vector3.up * 0.2f, safeRot);
            else ResetTo(new Vector3(p.x, (ground ?? p.y) + 0.6f, p.z), rot);
        }

        bool Fits(Vector3 pos, Quaternion rot)
        {
            var half = new Vector3(Spec.Size.x * 0.48f, (Spec.Size.y - BodyFloor) * 0.45f, Spec.Size.z * 0.48f);
            var c = pos + rot * new Vector3(0, BodyFloor + half.y + 0.05f, 0);
            var cols = Physics.OverlapBox(c, half, rot, GroundMask, QueryTriggerInteraction.Ignore);
            foreach (var col in cols) if (!col.transform.IsChildOf(transform)) return false;
            return true;
        }

        /// <summary>Teleport (stopped) to a pose: recovery, tests.</summary>
        public void ResetTo(Vector3 pos, Quaternion rot)
        {
            if (Body == null) return;
            var kin = Body.isKinematic;
            Body.isKinematic = true;
            Body.position = pos;
            Body.rotation = rot;
            transform.SetPositionAndRotation(pos, rot);
            Body.isKinematic = kin;
            if (!kin)
            {
                Body.linearVelocity = Vector3.zero;
                Body.angularVelocity = Vector3.zero;
            }
            foreach (var w in wheels) { w.X = w.PrevX = Droop; w.Omega = 0; }
            stuckT = 0; lowT = 0; Skid = 0;
            Rig.ResetMotion();
            Physics.SyncTransforms();
        }

        // ---------------------------------------------------------------- collisions

        void OnCollisionEnter(Collision c)
        {
            if (Body == null || Body.isKinematic) return;
            var dv = c.impulse.magnitude / Body.mass;
            if (dv < 1.2f) return;
            Impacts++;
            LastImpact = dv;
            LastImpactTime = Time.time;
            var p = c.contactCount > 0 ? c.GetContact(0).point : transform.position;
            Driving.OnImpact(this, c.collider, dv, p);
        }

        float scrapeT;

        void OnCollisionStay(Collision c)
        {
            if (Body == null || Body.isKinematic || c.contactCount == 0) return;
            scrapeT -= Time.fixedDeltaTime;
            if (scrapeT > 0f) return;
            var cp = c.GetContact(0);
            var rel = Body.GetPointVelocity(cp.point);
            var tangential = Vector3.ProjectOnPlane(rel, cp.normal).magnitude;
            if (tangential < 4f || c.collider.attachedRigidbody != null) return;
            scrapeT = 0.07f;
            VfxManager.Instance?.SparksDir(cp.point, -rel.normalized + cp.normal * 0.5f, 4, new Color(1f, 0.62f, 0.25f), 5f);
            Audio?.Scrape(Mathf.Clamp01(tangential / 18f));
        }

        // ---------------------------------------------------------------- visuals

        void Update()
        {
            if (Rig == null || wheels == null || Frozen) return;
            var kinematic = Body == null || Body.isKinematic;
            for (var i = 0; i < wheels.Length; i++)
            {
                var w = wheels[i];
                Rig.ExternalSpin[w.RigIndex] = kinematic ? 0f : w.Omega;
                // Wheel centre offset from the modelled rest pose (+ = up into the arch).
                Rig.ExternalDrop[w.RigIndex] = kinematic ? 0f : w.Grounded ? w.X - Droop : -Droop;
            }
            Rig.ExternalSteer = SteerAngle;
            // Tyre smoke off sliding / spinning wheels.
            smokeT -= Time.deltaTime;
            if (!kinematic && smokeT <= 0f && VfxManager.Instance != null)
            {
                smokeT = 0.07f;
                for (var i = 0; i < wheels.Length; i++)
                {
                    var w = wheels[i];
                    if (w.Grounded && w.Slip > 6.5f) VfxManager.Instance.SmokePuff(w.Point + Vector3.up * 0.15f, 1, new Color(0.62f, 0.64f, 0.68f, 0.5f), Mathf.Min(1.6f, 0.7f + 0.06f * w.Slip));
                }
            }
            Rig.BrakeInput = Driven && (Braking || (Mathf.Abs(ForwardSpeed) < 0.3f && !kinematic)) ? 1 : 0;
            if (!Driven && kinematic) { Rig.Headlights = VehicleRig.Lamp.Off; Rig.BrakeInput = 0; }
            else if (Driven) Rig.Headlights = VehicleRig.Lamp.Auto;
            var night = VehicleKit.Night;
            var lit = Driven && night;
            if (headFx != null) headFx.enabled = lit;
            if (tailFx != null)
            {
                tailFx.enabled = lit;
                var br = Rig.BrakeInput == 1;
                if (br != tailBrake) { tailBrake = br; Traffic.TailFx(tailFx, br); }
            }
            if (beam != null)
            {
                beam.enabled = lit;
                if (lit) beam.intensity = 60f;
            }
        }

        void OnDestroy()
        {
            Driving.Forget(this);
        }
    }
}
