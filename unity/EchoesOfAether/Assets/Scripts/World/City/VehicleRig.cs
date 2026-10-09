using System.Collections.Generic;
using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Animates a kit vehicle that something else moves (Traffic, SkyTraffic, a cutscene...): the driver only sets the
    /// root transform; the rig derives speed, acceleration and turn rate from it in LateUpdate and drives
    ///   • wheels: roll from speed (local +X rotation rolls forward), front-wheel steering yaw from the turn rate
    ///     (bicycle model), bikes lean into turns;
    ///   • flyers: hover bob, thruster pods pitching with acceleration / speed and rolling with lateral acceleration
    ///     (HoverCar_B's big fans tilt toward forward flight), thruster glow pulsing with throttle, nav strobes;
    ///   • lights through per-material-slot MaterialPropertyBlocks (no material copies): headlights (full at night,
    ///     DRL by day), tail lights that brighten under braking, neon / underglow in a per-instance colour, hazard
    ///     blink (vans when stopped, the hover truck always), the taxi's roof holo sign, optional paint tint.
    /// Cheap: no per-frame allocations, MPBs are only re-applied when a value changes, and nothing but the pose
    /// bookkeeping runs while the vehicle is culled or beyond <see cref="CullDistance"/>.
    /// A physically driven vehicle (<see cref="PlayerCar"/>) sets <see cref="External"/> and feeds the real wheel state
    /// instead (<see cref="ExternalSteer"/>, <see cref="ExternalSpin"/>, <see cref="ExternalDrop"/>): spin, steering and
    /// suspension travel then follow the simulation exactly (wheelspin, locked wheels under the handbrake).
    /// </summary>
    [DisallowMultipleComponent]
    public sealed class VehicleRig : MonoBehaviour
    {
        public enum Lamp { Off, Auto, On }

        const int Head = 0, Tail = 1, Neon = 2, Under = 3, Hazard = 4, Thruster = 5, Nav = 6, Holo = 7, Paint = 8, Channels = 9;
        static readonly string[] SlotNames = { "veh_headlight", "veh_taillight", "veh_neon", "veh_underglow", "veh_hazard", "veh_thruster", "veh_navlight", "veh_holo_sign" };
        static readonly int EmissionColorId = Shader.PropertyToID("_EmissionColor"), EmissionMapId = Shader.PropertyToID("_EmissionMap"), BaseColorId = Shader.PropertyToID("_BaseColor");
        static MaterialPropertyBlock mpb;

        struct Slot { public Renderer R; public int Index; }

        // ---------------------------------------------------------------- settings (drivers may change them any time)

        public Lamp Headlights = Lamp.Auto;
        /// <summary>-1: brake lights from the measured deceleration; 0 / 1: the driver says (released / braking).</summary>
        public int BrakeInput = -1;
        public bool HazardsAlways, HazardsWhenStopped, HoloOn = true, UnderglowOn = true;
        public Color NeonColor = new(1f, 0.1f, 0.72f), UnderColor = new(0f, 0.8f, 1f);
        /// <summary>Hover bob amplitude (m) for flyers.</summary>
        public float HoverBob = 0.14f;
        /// <summary>Wheels, thrusters and flicker within this distance of the camera; lights only beyond it.</summary>
        public float FullDistance = 90f;
        /// <summary>Nothing is updated beyond this distance (or while the vehicle is outside the camera frustum).</summary>
        public float CullDistance = 320f;

        /// <summary>Wheels follow <see cref="ExternalSteer"/> / <see cref="ExternalSpin"/> / <see cref="ExternalDrop"/> (player car).</summary>
        public bool External;
        /// <summary>Front-wheel steering angle (degrees, + = right) while <see cref="External"/>.</summary>
        public float ExternalSteer;
        /// <summary>Per wheel (index as <see cref="WheelName"/>): angular velocity (rad/s, + rolls forward) and suspension
        /// offset from the rest pose (m along the vehicle's up; + = wheel pushed up into the arch).</summary>
        public float[] ExternalSpin, ExternalDrop;

        public int WheelCount => wheels != null ? wheels.Length : 0;
        public string WheelName(int i) => wheels[i].name;
        public Transform WheelTransform(int i) => wheels[i];
        public Vector3 WheelRestLocal(int i) => wheelRestPos[i];
        public float WheelRadius(int i) => wheelR[i];

        public VehicleKit.Spec Spec { get; private set; }
        /// <summary>Signed forward speed (m/s), smoothed.</summary>
        public float Speed { get; private set; }
        public float Accel { get; private set; }
        public bool Braking { get; private set; }
        public bool Flyer { get; private set; }
        public bool Bike { get; private set; }

        // ---------------------------------------------------------------- state

        readonly Slot[][] slots = new Slot[Channels][];
        readonly float[] level = new float[Channels];
        readonly Color[] tint = new Color[Channels];
        readonly Texture[] map = new Texture[Channels];
        Color paintTint;
        Transform[] wheels;
        float[] wheelR, wheelSpin;
        bool[] wheelFront;
        Quaternion[] wheelRest;
        Vector3[] wheelRestPos;
        Transform[] thrusters;
        Quaternion[] thrRest;
        bool[] thrFan;
        Vector3 basePos, writtenPos, prevPos, prevFwd;
        Quaternion baseRot, writtenRot;
        bool wrote, hasPrev, ready;
        float yawRate, steer, lean, pitch, roll, fan, stopped, phase, throttle, travel;

        // ---------------------------------------------------------------- setup

        /// <summary>Collect wheels / thrusters / light slots and pick per-instance colours. Allocates (once).</summary>
        public void Setup(VehicleKit.Spec spec, System.Random r, Color? paint = null)
        {
            Spec = spec;
            Flyer = spec.Flyer;
            Bike = spec.Bike;
            mpb ??= new MaterialPropertyBlock();
            NeonColor = VehicleKit.Neons[r.Next(VehicleKit.Neons.Length)];
            UnderColor = r.NextDouble() < 0.55 ? NeonColor : VehicleKit.Neons[r.Next(VehicleKit.Neons.Length)];
            UnderglowOn = Flyer || r.NextDouble() < 0.8;
            HoloOn = r.NextDouble() < 0.7;
            HazardsWhenStopped = spec.Van;
            HazardsAlways = spec.Name == "HoverTruck";
            phase = (float)r.NextDouble() * 10f;
            if (Flyer) { HoverBob = spec.Size.z > 7f ? 0.08f : 0.14f; FullDistance = 160f; }

            var lists = new List<Slot>[Channels];
            for (var i = 0; i < Channels; i++) lists[i] = new List<Slot>();
            var paintName = paint.HasValue ? "veh_paint_pearl" : null;
            foreach (var rd in GetComponentsInChildren<Renderer>(true))
            {
                var mats = rd.sharedMaterials;
                for (var i = 0; i < mats.Length; i++)
                {
                    if (mats[i] == null) continue;
                    var mn = mats[i].name;
                    if (mn.EndsWith("_off")) mn = mn.Substring(0, mn.Length - 4);
                    var ch = System.Array.IndexOf(SlotNames, mn);
                    if (ch < 0 && paintName != null && mn == paintName) ch = Paint;
                    if (ch >= 0) lists[ch].Add(new Slot { R = rd, Index = i });
                }
            }
            for (var i = 0; i < Channels; i++) slots[i] = lists[i].Count > 0 ? lists[i].ToArray() : null;
            if (paint.HasValue) paintTint = paint.Value;

            for (var i = 0; i < Channels; i++) { tint[i] = Color.white; map[i] = null; level[i] = -1f; }
            var neutral = VehicleKit.NeutralLed;
            tint[Neon] = NeonColor; map[Neon] = neutral;
            tint[Under] = UnderColor; map[Under] = neutral;

            var w = new List<Transform>();
            var th = new List<Transform>();
            foreach (var t in GetComponentsInChildren<Transform>(true))
            {
                if (t.name.Contains("_LOD")) continue;
                if (t.name.StartsWith("Wheel_")) w.Add(t);
                else if (t.name.StartsWith("Thruster_")) th.Add(t);
            }
            wheels = w.ToArray();
            wheelR = new float[wheels.Length];
            wheelSpin = new float[wheels.Length];
            wheelFront = new bool[wheels.Length];
            wheelRest = new Quaternion[wheels.Length];
            wheelRestPos = new Vector3[wheels.Length];
            ExternalSpin = new float[wheels.Length];
            ExternalDrop = new float[wheels.Length];
            for (var i = 0; i < wheels.Length; i++)
            {
                wheelR[i] = Mathf.Max(0.15f, spec.Radius(wheels[i].name));
                wheelFront[i] = wheels[i].name.StartsWith("Wheel_F");
                wheelRest[i] = wheels[i].localRotation;
                wheelRestPos[i] = wheels[i].localPosition;
                wheelSpin[i] = (float)r.NextDouble() * 360f;
            }
            thrusters = th.ToArray();
            thrRest = new Quaternion[thrusters.Length];
            thrFan = new bool[thrusters.Length];
            for (var i = 0; i < thrusters.Length; i++)
            {
                thrRest[i] = thrusters[i].localRotation;
                thrFan[i] = spec.Name == "HoverCar_B" && (thrusters[i].name == "Thruster_L" || thrusters[i].name == "Thruster_R");
            }
            ready = true;
            ResetMotion();
            Lights(Time.time, false, true);
        }

        /// <summary>Call after teleporting the vehicle (spawn / respawn) so no speed is derived from the jump.</summary>
        public void ResetMotion()
        {
            hasPrev = false;
            wrote = false;
            Speed = 0; Accel = 0; yawRate = 0; steer = 0; lean = 0; stopped = 0;
        }

        // ---------------------------------------------------------------- per frame

        static int camFrame = -1;
        static Vector3 camPos;
        static bool hasCam;
        static readonly Plane[] frustum = new Plane[6];

        /// <summary>Game camera position and frustum planes, refreshed once per frame for all rigs.</summary>
        static void UpdateCamera()
        {
            if (Time.frameCount == camFrame) return;
            camFrame = Time.frameCount;
            var rig = G.Manager != null ? G.Manager.Cam : null;
            var cam = rig != null && rig.Cam != null ? rig.Cam : Camera.main;
            hasCam = cam != null;
            if (!hasCam) return;
            camPos = cam.transform.position;
            GeometryUtility.CalculateFrustumPlanes(cam, frustum);
        }

        /// <summary>Bounding sphere of the vehicle against the game camera's frustum (Renderer.isVisible also counts
        /// shadow casters and is not updated by manual Camera.Render calls).</summary>
        bool Visible(Vector3 p, Quaternion q)
        {
            if (!hasCam) return true;
            var c = p + q * Spec.BoundsCenter;
            var r = Spec.Size.magnitude * 0.5f + 0.5f;
            for (var i = 0; i < 6; i++) if (frustum[i].GetDistanceToPoint(c) < -r) return false;
            return true;
        }

        void OnDisable() => hasPrev = false;

        void LateUpdate()
        {
            if (!ready) return;
            var dt = Time.deltaTime;
            if (dt <= 0f) return;
            var tr = transform;
            tr.GetPositionAndRotation(out var p, out var q);
            // Our own offset from last frame still there (the driver did not move us): measure from the driver's pose.
            if (wrote && p == writtenPos && q == writtenRot) { p = basePos; q = baseRot; }
            basePos = p; baseRot = q;

            var fwd = q * Vector3.forward;
            if (!hasPrev) { prevPos = p; prevFwd = fwd; hasPrev = true; }
            var delta = p - prevPos;
            if (delta.sqrMagnitude > 120f * 120f * dt * dt) { delta = Vector3.zero; prevFwd = fwd; } // teleported
            var k = 1f - Mathf.Exp(-dt * 8f);
            travel = Vector3.Dot(delta, fwd); // metres driven this frame (wheels roll exactly this far)
            var v = travel / dt;
            var speed = Mathf.Lerp(Speed, v, k);
            Accel = Mathf.Lerp(Accel, (speed - Speed) / dt, 1f - Mathf.Exp(-dt * 4f));
            Speed = speed;
            yawRate = Mathf.Lerp(yawRate, Vector3.SignedAngle(prevFwd, fwd, Vector3.up) * Mathf.Deg2Rad / dt, k);
            prevPos = p; prevFwd = fwd;
            stopped = Mathf.Abs(Speed) < 0.3f ? stopped + dt : 0f;
            Braking = BrakeInput >= 0 ? BrakeInput == 1 : !Flyer && (Accel < -1.0f || stopped > 0.2f);

            UpdateCamera();
            var d2 = (p - camPos).sqrMagnitude;
            if (d2 > CullDistance * CullDistance || !Visible(p, q))
            {
                Restore();
                return;
            }
            var near = d2 < FullDistance * FullDistance;
            var t = Time.time;
            Lights(t, near, false);
            if (!near) { Restore(); return; }
            if (wheels.Length > 0) Wheels(dt);
            if (Flyer) Thrusters(dt, t);
            Pose(dt, t);
        }

        void Restore()
        {
            if (!wrote) return;
            wrote = false;
            transform.SetPositionAndRotation(basePos, baseRot);
        }

        void Wheels(float dt)
        {
            if (External && ExternalSpin != null && ExternalSpin.Length == wheels.Length)
            {
                steer = Mathf.Lerp(steer, ExternalSteer, 1f - Mathf.Exp(-dt * 20f));
                for (var i = 0; i < wheels.Length; i++)
                {
                    wheelSpin[i] = (wheelSpin[i] + ExternalSpin[i] * dt * Mathf.Rad2Deg) % 360f;
                    var spin = Quaternion.Euler(wheelSpin[i], 0, 0);
                    wheels[i].localRotation = wheelFront[i] ? wheelRest[i] * Quaternion.Euler(0, steer, 0) * spin : wheelRest[i] * spin;
                    wheels[i].localPosition = wheelRestPos[i] + Vector3.up * ExternalDrop[i];
                }
                return;
            }
            var abs = Mathf.Abs(Speed);
            var target = abs > 0.3f ? Mathf.Atan(Spec.WheelBase * yawRate / Mathf.Max(abs, 2f)) * Mathf.Rad2Deg * Mathf.Sign(Speed) : steer;
            target = Mathf.Clamp(target, Bike ? -10f : -34f, Bike ? 10f : 34f);
            steer = Mathf.Lerp(steer, target, 1f - Mathf.Exp(-dt * 6f));
            for (var i = 0; i < wheels.Length; i++)
            {
                wheelSpin[i] = (wheelSpin[i] + travel / wheelR[i] * Mathf.Rad2Deg) % 360f;
                var spin = Quaternion.Euler(wheelSpin[i], 0, 0);
                wheels[i].localRotation = wheelFront[i] ? wheelRest[i] * Quaternion.Euler(0, Bike ? steer * 0.35f : steer, 0) * spin : wheelRest[i] * spin;
            }
        }

        void Thrusters(float dt, float t)
        {
            var lat = Speed * yawRate; // lateral acceleration, + = toward the right
            var k = 1f - Mathf.Exp(-dt * 3f);
            // Nozzles face -Y: +X rotation swings them back (thrust forward), -Z rotation swings them left (thrust right).
            pitch = Mathf.Lerp(pitch, Mathf.Clamp(Accel * 3f + Speed * 0.35f, -18f, 22f), k);
            roll = Mathf.Lerp(roll, Mathf.Clamp(-lat * 2.5f, -16f, 16f), k);
            fan = Mathf.Lerp(fan, Mathf.Clamp(Mathf.Abs(Speed) * 2.4f, 0f, 72f) * Mathf.Sign(Speed + 0.001f), k);
            for (var i = 0; i < thrusters.Length; i++)
            {
                var wob = Mathf.Sin(t * 2.1f + phase + i * 1.7f) * 1.6f;
                thrusters[i].localRotation = thrRest[i] * Quaternion.Euler((thrFan[i] ? fan : pitch) + wob, 0, roll + wob * 0.5f);
            }
        }

        void Pose(float dt, float t)
        {
            if (Bike)
            {
                var target = Mathf.Clamp(-Mathf.Atan(Speed * yawRate / 9.81f) * Mathf.Rad2Deg, -32f, 32f);
                lean = Mathf.Lerp(lean, target, 1f - Mathf.Exp(-dt * 5f));
                if (Mathf.Abs(lean) < 0.05f) { Restore(); return; }
                writtenPos = basePos;
                writtenRot = baseRot * Quaternion.Euler(0, 0, lean);
            }
            else if (Flyer)
            {
                var bob = Mathf.Sin(t * 1.25f + phase) * HoverBob + Mathf.Sin(t * 2.9f + phase * 1.7f) * HoverBob * 0.3f;
                writtenPos = basePos + baseRot * new Vector3(0, bob, 0);
                writtenRot = baseRot * Quaternion.Euler(Mathf.Sin(t * 0.9f + phase) * 0.8f - Accel * 0.25f, 0, Mathf.Sin(t * 1.1f + phase * 0.6f) * 0.9f);
            }
            else { Restore(); return; }
            transform.SetPositionAndRotation(writtenPos, writtenRot);
            wrote = true;
        }

        // ---------------------------------------------------------------- lights

        void Lights(float t, bool near, bool force)
        {
            var night = VehicleKit.Night;
            var lit = Headlights == Lamp.On || (Headlights == Lamp.Auto && night);
            Set(Head, Headlights == Lamp.Off ? 0f : lit ? 5f : 1.4f, force);
            Set(Tail, Braking ? 9.5f : Headlights == Lamp.Off ? 0f : 3.2f, force);
            Set(Neon, 4.5f, force);
            Set(Under, UnderglowOn ? 3.6f : 0f, force);
            if (slots[Hazard] != null)
            {
                var blink = HazardsAlways || (HazardsWhenStopped && stopped > 12f); // beacons when stuck, not at every red light
                Set(Hazard, blink ? ((t + phase) % 0.8f < 0.4f ? 6f : 0.15f) : 1.1f, force);
            }
            if (slots[Thruster] != null)
            {
                throttle = Mathf.Clamp01(0.5f + Accel * 0.12f + Mathf.Abs(Speed * yawRate) * 0.04f + Mathf.Abs(Speed) * 0.008f);
                var k = 6f * (0.6f + 0.6f * throttle);
                if (near) k *= 1f + 0.07f * Mathf.Sin(t * 37f + phase) + 0.04f * Mathf.Sin(t * 13.7f + phase * 2f);
                Set(Thruster, Mathf.Round(k * 5f) / 5f, force);
            }
            if (slots[Nav] != null)
            {
                // Steady red / green with a white double strobe every 1.2 s.
                var s = (t + phase) % 1.2f;
                Set(Nav, s < 0.06f || (s > 0.16f && s < 0.22f) ? 11f : 3.5f, force);
            }
            if (slots[Holo] != null)
            {
                var h = HoloOn ? 2.4f : 0f;
                if (HoloOn && near) h *= Mathf.Sin(t * 23f + phase) > 0.97f ? 0.55f : 1f;
                Set(Holo, h, force);
            }
            if (force && slots[Paint] != null)
            {
                for (var i = 0; i < slots[Paint].Length; i++)
                {
                    mpb.Clear();
                    mpb.SetColor(BaseColorId, paintTint);
                    slots[Paint][i].R.SetPropertyBlock(mpb, slots[Paint][i].Index);
                }
            }
        }

        void Set(int ch, float k, bool force)
        {
            var s = slots[ch];
            if (s == null || (!force && Mathf.Abs(level[ch] - k) < 0.02f)) return;
            level[ch] = k;
            var col = k <= 0f ? Color.black : FxMaterials.Hdr(tint[ch], k);
            for (var i = 0; i < s.Length; i++)
            {
                if (s[i].R == null) continue;
                mpb.Clear();
                mpb.SetColor(EmissionColorId, col);
                if (map[ch] != null) mpb.SetTexture(EmissionMapId, map[ch]);
                if (ch == Holo) mpb.SetColor(BaseColorId, new Color(1f, 1f, 1f, k > 0f ? 1f : 0f));
                s[i].R.SetPropertyBlock(mpb, s[i].Index);
            }
        }
    }
}
