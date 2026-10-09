using UnityEngine;
using UnityEngine.Rendering.Universal;

namespace EOA
{
    /// <summary>
    /// Third-person orbit camera: smoothed focus, shoulder offset, sphere-cast collision, aim mode, lock-on,
    /// sprint FOV kick, trauma shake and a cinematic override. Heading h looks along (sin h, 0, cos h).
    /// Chase mode (<see cref="ChaseVehicle"/>, while the player drives): behind the car with a lagging heading that
    /// shows slides, speed-based distance and FOV, free look with the mouse / right stick that recentres while moving.
    /// </summary>
    [DefaultExecutionOrder(200)]
    public sealed class CameraRig : MonoBehaviour
    {
        public Camera Cam;
        public float Heading;            // radians
        public float Pitch = 0.18f;      // radians, positive looks down
        public float Distance = 4.3f;
        public float Shoulder = 0.42f;
        public float PivotHeight = 1.55f;
        public float BaseFov = 62f;
        public bool Aiming, Sprinting, Indoor;
        Light key, fill, rim;
        /// <summary>Character rim light strength.</summary>
        public float RimIntensity = 14f;
        /// <summary>
        /// Character light level (zone atmospheres set it, darker zones higher): drives the camera-relative key and its
        /// soft opposite fill.
        /// </summary>
        public float FillIntensity = 0.9f;
        /// <summary>Spot-light equivalent of FillIntensity (the zone atmospheres set FillIntensity on the old point-light scale).</summary>
        public float FillBoost = 4.5f;
        /// <summary>Character key: azimuth from the camera direction toward camera-right (deg), elevation (deg), share of the level.</summary>
        public float KeyAzimuth = 50f, KeyElevation = 33f, KeyShare = 1.0f;
        /// <summary>Rim colour with no neon nearby (cool moonlight).</summary>
        static readonly Color RimCool = new(0.62f, 0.82f, 1f);
        /// <summary>Opposite fill as a fraction of the key (key : fill about 4 : 1 plus ambient).</summary>
        public float FillRatio = 0.3f;
        public float CombatZoom;
        public Vector3? LockTarget;
        public Transform Follow;
        public float ShakeScale = 1f;

        /// <summary>When set, the camera holds this shot instead of orbiting.</summary>
        public (Vector3 pos, Vector3 look, float fov)? Cinematic;

        /// <summary>Chase mode: the car being driven (null on foot).</summary>
        public Rigidbody Vehicle { get; private set; }
        Vector2 vehicleSize = new(4.8f, 1.45f);
        float chaseYaw, lookYaw, lookPitch, lookIdle, chaseDist, chaseFov, chaseY;
        bool chaseInit;

        float curDist, curShoulder, curPivot, fov, curCombatZoom, trauma, shakeT;
        Vector3 smoothFocus;
        // Combat: directional kick spring (world offset), FOV punch, smoothed lock-on point and framing.
        Vector3 kick, kickVel;
        float fovPunch, fovPunchVel, lockW;
        Vector3 smoothLock;
        bool hadLock;
        bool initialized;
        Vector3 pivot;
        static readonly RaycastHit[] hits = new RaycastHit[8];

        public static CameraRig Create(Transform parent)
        {
            var go = new GameObject("CameraRig");
            go.transform.SetParent(parent, false);
            var rig = go.AddComponent<CameraRig>();
            var camGo = new GameObject("Main Camera") { tag = "MainCamera" };
            camGo.transform.SetParent(go.transform, false);
            rig.Cam = camGo.AddComponent<Camera>();
            rig.Cam.nearClipPlane = 0.08f;
            rig.Cam.farClipPlane = 400f;
            rig.Cam.fieldOfView = rig.BaseFov;
            camGo.AddComponent<AudioListener>();
            // Character key: camera-relative three-quarter light ~50 deg to camera-right and ~33 deg above the subject
            // (never from the lens: frontal light flattened faces and bodies), with soft shadows cast only by characters
            // (its rendering layers), so arms, chin and gear shadow the body. A soft, low fill from the opposite side
            // keeps the shadow side readable in dark zones (key : fill about 4 : 1).
            var keyGo = new GameObject("CharacterKey");
            keyGo.transform.SetParent(go.transform, false);
            rig.key = keyGo.AddComponent<Light>();
            rig.key.type = LightType.Spot;
            rig.key.range = 9f;
            rig.key.spotAngle = 52f;
            rig.key.innerSpotAngle = 34f;
            rig.key.color = new Color(1f, 0.95f, 0.88f);
            rig.key.intensity = 0;
            rig.key.shadows = GraphicsConfig.CharacterKeyShadows ? LightShadows.Soft : LightShadows.None;
            rig.key.shadowStrength = 0.9f;
            rig.key.shadowNearPlane = 0.5f;
            var keyData = rig.key.GetUniversalAdditionalLightData();
            var fillGo = new GameObject("CharacterFill");
            fillGo.transform.SetParent(go.transform, false);
            rig.fill = fillGo.AddComponent<Light>();
            rig.fill.type = LightType.Spot;
            rig.fill.range = 10f;
            rig.fill.spotAngle = 75f;
            rig.fill.innerSpotAngle = 20f;
            rig.fill.color = new Color(0.78f, 0.86f, 1f);
            rig.fill.intensity = 0;
            rig.fill.shadows = LightShadows.None;
            // Cool rim light behind the hero (relative to the camera) so silhouettes read in dark, rainy scenes.
            var rimGo = new GameObject("CharacterRim");
            rimGo.transform.SetParent(go.transform, false);
            rig.rim = rimGo.AddComponent<Light>();
            rig.rim.type = LightType.Spot;
            rig.rim.range = 9f;
            rig.rim.spotAngle = 55f;
            rig.rim.innerSpotAngle = 25f;
            rig.rim.color = new Color(0.62f, 0.82f, 1f);
            rig.rim.intensity = 0;
            rig.rim.shadows = LightShadows.None;
            // Key, fill and rim only affect renderers on the Characters rendering layer (URP rendering layers).
            keyData.renderingLayers = CharacterModel.CharacterLayerMask;
            rig.fill.GetUniversalAdditionalLightData().renderingLayers = CharacterModel.CharacterLayerMask;
            rig.rim.GetUniversalAdditionalLightData().renderingLayers = CharacterModel.CharacterLayerMask;
            return rig;
        }

        void Awake()
        {
            curDist = Distance; curShoulder = Shoulder; curPivot = PivotHeight; fov = BaseFov;
            Bus.On<ShakeRequested>(e => AddTrauma(e.Amount));
            Bus.On<CameraKickRequested>(e => Kick(e.Dir, e.Amount, e.Fov));
        }

        /// <summary>
        /// Directional hit kick: the view is shoved a few cm along `dir` (and pitched with it) on a stiff spring, plus an
        /// optional FOV punch (negative = punch in). Scaled by the camera-shake settings; runs on unscaled time so it
        /// plays through hit-stop.
        /// </summary>
        public void Kick(Vector3 dir, float amount, float fovDeg)
        {
            var scale = ShakeScale;
            if (scale <= 0f) return;
            if (dir.sqrMagnitude > 1e-4f) kickVel += dir.normalized * (amount * 1.6f * scale);
            fovPunchVel += fovDeg * 22f * Mathf.Min(1f, scale);
        }

        public Vector3 Forward => new(Mathf.Sin(Heading), 0, Mathf.Cos(Heading));
        public Vector3 Right => new(Mathf.Cos(Heading), 0, -Mathf.Sin(Heading));
        public Vector3 LookDir
        {
            get { var cp = Mathf.Cos(Pitch); return new Vector3(Mathf.Sin(Heading) * cp, -Mathf.Sin(Pitch), Mathf.Cos(Heading) * cp); }
        }

        public void AddTrauma(float t) => trauma = Mathf.Min(1, trauma + t * (G.Settings?.ShakeScale ?? 1f));

        /// <summary>Chase a car (length / height in metres frame it); snaps behind it.</summary>
        public void ChaseVehicle(Rigidbody body, float length, float height)
        {
            Vehicle = body;
            vehicleSize = new Vector2(Mathf.Max(2f, length), Mathf.Max(1f, height));
            chaseInit = false;
            lookYaw = 0; lookPitch = 0; lookIdle = 0;
            Aiming = false; Sprinting = false; LockTarget = null;
        }

        /// <summary>Back to the on-foot orbit, looking the way the chase camera did.</summary>
        public void StopChase()
        {
            if (Vehicle == null) return;
            Vehicle = null;
            Heading = chaseYaw + lookYaw;
            Pitch = 0.18f;
            initialized = false;
        }

        public void SnapBehind(float yawRad)
        {
            Heading = yawRad;
            Pitch = 0.18f;
            initialized = false;
        }

        static float Damp(float a, float b, float lambda, float dt) => Mathf.Lerp(a, b, 1 - Mathf.Exp(-lambda * dt));
        static float DampAngle(float a, float b, float lambda, float dt) => a + Mathf.DeltaAngle(a * Mathf.Rad2Deg, b * Mathf.Rad2Deg) * Mathf.Deg2Rad * (1 - Mathf.Exp(-lambda * dt));

        void LateUpdate()
        {
            var dt = Time.unscaledDeltaTime;
            if (Cam == null) return;
            if (key != null && fill != null) PlaceCharacterLights(dt);
            if (rim != null)
            {
                var target = Follow != null && Vehicle == null ? Follow.position + Vector3.up * 1.35f : (Vector3?)null;
                var want = target.HasValue ? RimIntensity : 0f;
                rim.intensity = Mathf.MoveTowards(rim.intensity, want, dt * 4f);
                rim.enabled = rim.intensity > 0.001f;
                if (target.HasValue)
                {
                    var away = target.Value - Cam.transform.position;
                    away.y = 0;
                    away = away.sqrMagnitude > 0.01f ? away.normalized : Vector3.forward;
                    var p = target.Value + away * 2.4f + Vector3.up * 1.8f;
                    rim.transform.SetPositionAndRotation(p, Quaternion.LookRotation(target.Value - p));
                    // Neon spill: the rim takes on the colour of the signs and lamps around the hero (cool moonlight
                    // where there are none), so characters pick up the city's light like the walls do.
                    var rimCol = RimCool;
                    if (NeonField.LightAt(target.Value, out var neon))
                    {
                        var peak = Mathf.Max(neon.r, Mathf.Max(neon.g, Mathf.Max(neon.b, 1e-4f)));
                        var hue = new Color(neon.r / peak, neon.g / peak, neon.b / peak);
                        rimCol = Color.Lerp(RimCool, hue, Mathf.Clamp01(peak * 0.6f) * 0.7f);
                    }
                    rim.color = Color.Lerp(rim.color, rimCol, 1f - Mathf.Exp(-3f * dt));
                }
            }
            if (Cinematic.HasValue)
            {
                var c = Cinematic.Value;
                TickKick(dt);
                Cam.transform.position = c.pos + kick;
                Cam.transform.LookAt(c.look + kick * 0.5f);
                Cam.fieldOfView = c.fov + fovPunch;
                ApplyShake(dt);
                HideNearCharacters();
                initialized = false;
                return;
            }
            if (Vehicle != null) { Chase(dt); return; }
            if (Follow == null) return;
            // Look input (the hero/game decides when it's allowed).
            var allowLook = G.Manager != null && G.Manager.Mode == GameMode.Play && !G.Manager.Paused && !G.Manager.InDialogue && !G.Manager.InCinematic;
            if (allowLook && G.Input != null)
            {
                var s = G.Settings.Data.Gameplay;
                var look = G.Input.LookDelta(G.Settings.Data.Controls.PadLookSpeed) * (Aiming ? s.AimSensitivity : 1f) * s.CameraSensitivity * Mathf.Deg2Rad;
                // Locked on, horizontal look is a target-switch flick (the hero reads it), not a free orbit.
                Heading += LockTarget.HasValue ? look.x * 0.12f : look.x;
                Pitch = Mathf.Clamp(Pitch + (s.InvertY ? look.y : -look.y), -0.85f, 1.15f);
            }
            var focus = Follow.position;
            if (!initialized)
            {
                smoothFocus = focus;
                curDist = Distance;
                initialized = true;
            }
            smoothFocus.x = Damp(smoothFocus.x, focus.x, 18, dt);
            smoothFocus.z = Damp(smoothFocus.z, focus.z, 18, dt);
            smoothFocus.y = Damp(smoothFocus.y, focus.y, 10, dt);

            // Lock-on: glide to a newly picked target (smooth switching) and frame hero + target together.
            float lockExtra = 0f;
            Vector3 frameShift = Vector3.zero;
            lockW = Damp(lockW, LockTarget.HasValue ? 1f : 0f, 5f, dt);
            if (LockTarget.HasValue)
            {
                var t = LockTarget.Value;
                smoothLock = hadLock ? Vector3.Lerp(smoothLock, t, 1f - Mathf.Exp(-9f * dt)) : t;
                hadLock = true;
                var dx = smoothLock.x - smoothFocus.x; var dz = smoothLock.z - smoothFocus.z;
                var dist = Mathf.Sqrt(dx * dx + dz * dz);
                if (dist > 0.4f) Heading = DampAngle(Heading, Mathf.Atan2(dx, dz), 6, dt);
                var wantPitch = Mathf.Clamp(0.25f - (smoothLock.y - smoothFocus.y - 1.2f) / Mathf.Max(4, dist) * 0.6f, -0.1f, 0.6f);
                Pitch = Damp(Pitch, wantPitch, 2.5f, dt);
                // Pull back as the pair separates; nudge the pivot a little toward the target.
                lockExtra = Mathf.Clamp((dist - 3f) * 0.22f, 0f, 2.2f);
                frameShift = dist > 0.01f ? new Vector3(dx, 0f, dz) / dist * Mathf.Min(dist * 0.18f, 1.6f) : Vector3.zero;
            }
            else hadLock = false;

            var wantDist = Aiming ? 1.9f : Distance + curCombatZoom + (Indoor ? -0.4f : 0) + lockExtra * lockW;
            var wantShoulder = Aiming ? 0.62f : Shoulder;
            var wantPivot = Aiming ? 1.62f : PivotHeight;
            var wantFov = Aiming ? 50 : BaseFov + (Sprinting ? 7 : 0);
            curCombatZoom = Damp(curCombatZoom, CombatZoom, 2, dt);
            curShoulder = Damp(curShoulder, wantShoulder, 10, dt);
            curPivot = Damp(curPivot, wantPivot, 10, dt);
            fov = Damp(fov, wantFov, 6, dt);

            var right = Right;
            pivot = smoothFocus + Vector3.up * curPivot + frameShift * lockW;
            // Shoulder offset with collision so the pivot never sits inside a wall.
            var shoulder = curShoulder;
            if (Physics.SphereCast(pivot, 0.12f, right, out var sh, curShoulder + 0.25f, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore))
                shoulder = Mathf.Max(0, sh.distance - 0.25f);
            pivot += right * shoulder;
            var dir = LookDir;
            var allowed = wantDist;
            if (Physics.SphereCast(pivot, 0.2f, -dir, out var hit, wantDist + 0.3f, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore))
                allowed = Mathf.Max(0.55f, hit.distance - 0.3f);
            // Pull in fast, ease out slowly.
            curDist = allowed < curDist ? Damp(curDist, allowed, 30, dt) : Damp(curDist, allowed, 3.5f, dt);
            TickKick(dt);
            Cam.transform.position = pivot - dir * curDist + kick;
            Cam.transform.LookAt(pivot + dir * 6f + kick * 0.5f);
            Cam.fieldOfView = fov + fovPunch;
            ApplyShake(dt);
            HideNearCharacters();
        }

        /// <summary>
        /// Character key and fill, placed relative to the camera around the subject (the hero's chest, or the shot's
        /// look point in cinematics): key from KeyAzimuth toward camera-right and KeyElevation above, fill low from the
        /// opposite side. The menu / designer stage has its own studio lights.
        /// </summary>
        void PlaceCharacterLights(float dt)
        {
            var onStage = G.Manager != null && (G.Manager.Mode == GameMode.Menu || G.Manager.DesignerActive);
            // (No hero to light while driving: the hero rides hidden in the car.)
            Vector3? subject = Follow != null && Vehicle == null ? Follow.position + Vector3.up * 1.3f : Cinematic.HasValue ? Cinematic.Value.look : (Vector3?)null;
            var level = !onStage && subject.HasValue ? FillIntensity * FillBoost * (Indoor ? 1f : 0.9f) : 0f;
            key.intensity = Mathf.MoveTowards(key.intensity, level * KeyShare, dt * 8f);
            fill.intensity = Mathf.MoveTowards(fill.intensity, level * KeyShare * FillRatio, dt * 8f);
            key.enabled = key.intensity > 0.001f;
            fill.enabled = fill.intensity > 0.001f;
            var ks = GraphicsConfig.CharacterKeyShadows ? LightShadows.Soft : LightShadows.None;
            if (key.shadows != ks) key.shadows = ks;
            if (!subject.HasValue) return;
            var s = subject.Value;
            var toCam = Cam.transform.position - s;
            toCam.y = 0;
            toCam = toCam.sqrMagnitude > 0.01f ? toCam.normalized : -Forward;
            var el = KeyElevation * Mathf.Deg2Rad;
            var kd = Quaternion.AngleAxis(-KeyAzimuth, Vector3.up) * toCam;
            var kp = s + kd * (2.8f * Mathf.Cos(el)) + Vector3.up * (2.8f * Mathf.Sin(el));
            var aim = s + Vector3.up * 0.1f;
            key.transform.SetPositionAndRotation(kp, Quaternion.LookRotation(aim - kp));
            var fd = Quaternion.AngleAxis(KeyAzimuth + 15f, Vector3.up) * toCam;
            var fp = s + fd * 3.2f + Vector3.up * 0.25f;
            fill.transform.SetPositionAndRotation(fp, Quaternion.LookRotation(s - fp));
        }

        /// <summary>
        /// Chase camera: heading lags the car and leans toward its direction of travel in a slide; distance, height and
        /// FOV grow with speed; free look recentres after a moment while moving; sphere-cast collision with the level
        /// (the car's own colliders are on IgnoreCamera).
        /// </summary>
        void Chase(float dt)
        {
            var t = Vehicle.transform;
            var pos = t.position;
            var v = Vehicle.isKinematic ? Vector3.zero : Vehicle.linearVelocity;
            var flat = new Vector3(v.x, 0, v.z);
            var speed = flat.magnitude;
            var fwd = t.forward; fwd.y = 0;
            if (fwd.sqrMagnitude < 1e-3f) { fwd = t.up; fwd.y = 0; }
            if (fwd.sqrMagnitude < 1e-3f) fwd = Forward;
            fwd.Normalize();
            var carYaw = Mathf.Atan2(fwd.x, fwd.z);
            var target = carYaw;
            if (speed > 3f && Vector3.Dot(flat, fwd) > 0f)
                target = carYaw + Mathf.DeltaAngle(carYaw * Mathf.Rad2Deg, Mathf.Atan2(flat.x, flat.z) * Mathf.Rad2Deg) * Mathf.Deg2Rad * 0.4f;
            var speed01 = Mathf.Clamp01(speed / 45f);
            if (!chaseInit)
            {
                chaseInit = true;
                chaseYaw = target;
                chaseY = pos.y;
                chaseDist = vehicleSize.x + 2f;
                chaseFov = BaseFov;
            }
            chaseYaw = DampAngle(chaseYaw, target, 3.2f + speed01 * 3f, dt);
            var allowLook = G.Manager != null && G.Manager.Mode == GameMode.Play && !G.Manager.Paused && !G.Manager.InDialogue && !G.Manager.InCinematic;
            var looked = false;
            if (allowLook && G.Input != null && G.Settings != null)
            {
                var s = G.Settings.Data.Gameplay;
                var look = G.Input.LookDelta(G.Settings.Data.Controls.PadLookSpeed) * s.CameraSensitivity * Mathf.Deg2Rad;
                if (look.sqrMagnitude > 1e-7f)
                {
                    looked = true;
                    lookYaw = Mathf.Repeat(lookYaw + look.x + Mathf.PI, Mathf.PI * 2f) - Mathf.PI;
                    lookPitch = Mathf.Clamp(lookPitch + (s.InvertY ? look.y : -look.y), -0.3f, 0.9f);
                }
            }
            lookIdle = looked ? 0f : lookIdle + dt;
            if (lookIdle > 1.6f && speed > 2.5f)
            {
                lookYaw = DampAngle(lookYaw, 0f, 2.4f, dt);
                lookPitch = Damp(lookPitch, 0f, 2.4f, dt);
            }
            var yaw = chaseYaw + lookYaw;
            var pitch = 0.16f + lookPitch - speed01 * 0.03f;
            Heading = yaw;
            Pitch = pitch;
            var cp = Mathf.Cos(pitch);
            var dir = new Vector3(Mathf.Sin(yaw) * cp, -Mathf.Sin(pitch), Mathf.Cos(yaw) * cp);
            chaseY = Damp(chaseY, pos.y, 7f, dt);
            pivot = new Vector3(pos.x, chaseY + vehicleSize.y * 0.8f + 0.5f, pos.z);
            var wantDist = vehicleSize.x * 0.95f + 1.9f + speed01 * 2.4f;
            var allowed = wantDist;
            if (Physics.SphereCast(pivot, 0.25f, -dir, out var hit, wantDist + 0.3f, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore))
                allowed = Mathf.Max(1.4f, hit.distance - 0.3f);
            chaseDist = allowed < chaseDist ? Damp(chaseDist, allowed, 25f, dt) : Damp(chaseDist, allowed, 2.2f, dt);
            chaseFov = Damp(chaseFov, BaseFov + 2f + 15f * Mathf.Pow(speed01, 1.3f), 3f, dt);
            TickKick(dt);
            Cam.transform.position = pivot - dir * chaseDist + kick;
            Cam.transform.LookAt(pivot + dir * 8f + kick * 0.5f);
            Cam.fieldOfView = chaseFov + fovPunch;
            ApplyShake(dt);
            HideNearCharacters();
        }

        /// <summary>Stiff, slightly under-damped springs: a quick shove that settles in ~0.2 s without wobble.</summary>
        void TickKick(float dt)
        {
            dt = Mathf.Min(dt, 0.05f);
            kickVel += (-kick * 260f - kickVel * 22f) * dt;
            kick += kickVel * dt;
            if (kick.sqrMagnitude > 0.04f) kick = kick.normalized * 0.2f;
            fovPunchVel += (-fovPunch * 220f - fovPunchVel * 20f) * dt;
            fovPunch = Mathf.Clamp(fovPunch + fovPunchVel * dt, -9f, 6f);
        }

        /// <summary>
        /// Characters whose body capsule comes within ~half a metre of the lens (a companion stepping beside the camera,
        /// tight interiors) are hidden instead of filling the frame with a cut-open head.
        /// </summary>
        void HideNearCharacters()
        {
            var cam = Cam.transform.position;
            var list = CharacterModel.Active;
            for (var i = list.Count - 1; i >= 0; i--)
            {
                var m = list[i];
                if (m == null) continue;
                var feet = m.transform.position;
                var h = m.BaseHeight * m.transform.lossyScale.y;
                var y = Mathf.Clamp(cam.y, feet.y + 0.2f, feet.y + h - 0.1f);
                var d = Vector3.Distance(cam, new Vector3(feet.x, y, feet.z));
                var limit = Follow != null && (m.transform == Follow || m.transform.IsChildOf(Follow)) ? 0.42f : 0.62f;
                m.SetCameraHidden(d < limit);
            }
        }

        void ApplyShake(float dt)
        {
            trauma = Mathf.Max(0, trauma - dt * 1.6f);
            if (trauma <= 0 || ShakeScale <= 0) return;
            shakeT += dt * 40;
            var s = trauma * trauma * ShakeScale;
            float N(float o) => Mathf.Sin(shakeT * (1.1f + o) + o * 17) * Mathf.Cos(shakeT * 0.7f + o * 3);
            Cam.transform.Rotate(N(1) * 1.7f * s, N(2) * 1.7f * s, N(3) * 2.3f * s, Space.Self);
        }

        /// <summary>World point under the screen centre (for aiming).</summary>
        public Vector3 AimPoint(float maxDist = 80)
        {
            var o = Cam.transform.position; var d = Cam.transform.forward;
            return Physics.Raycast(o, d, out var h, maxDist, CombatLayers.WorldMask | CombatLayers.EnemyMask, QueryTriggerInteraction.Ignore) ? h.point : o + d * maxDist;
        }

        public bool Sees(Vector3 p)
        {
            var v = Cam.WorldToViewportPoint(p);
            return v.z > 0 && v.x > -0.1f && v.x < 1.1f && v.y > -0.1f && v.y < 1.1f;
        }
    }
}
