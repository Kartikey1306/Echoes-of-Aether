using UnityEngine;
using UnityEngine.Rendering;

namespace EOA
{
    /// <summary>
    /// Hero weapons, driven by <see cref="Hero"/> and attached at runtime to the Mixamo bones (the hero FBX is never touched):
    /// <list type="bullet">
    /// <item>Kael: a flush emitter ring in the right glove cuff (thin band, faint cyan line, slot on the back of the
    /// wrist) projects a 3D hard-light blade (bevelled single-edged hull + inner core, EOA/HardLight: fresnel, glowing
    /// edge, parallax inner light) only while he attacks: it grows out of the slot on the wind-up and withdraws after the
    /// recovery. Left-handed strikes project a matching blade straight from the left-forearm Aether Interface. Both
    /// mounts are fitted to the measured cuff surface at spawn (no floating, no clipping). The "Lancet" Aether pistol rides in a
    /// right-thigh holster; bolts draw it (procedural reach-to-holster, then a one-handed aim pose by two-bone arm IK),
    /// it recoils, ejects a spent energy cell, and is holstered again after a short idle or the moment a melee swing
    /// starts.</item>
    /// <item>Giva: energy gauntlets on both hands with three hard-light claws each (extend on attack), palm emitters her
    /// bolts leave from (left arm raised palm-forward by IK), and an animated hologram on her forearm-guard screen.</item>
    /// </list>
    /// Runs after the animator, HeroStance and HumanoidPolish (execution order 150), before TwistBones and the camera.
    /// Everything is built once in <see cref="Init"/>; per frame it is transform maths, a few material floats (no
    /// allocations) and the swing ribbons.
    /// </summary>
    [DefaultExecutionOrder(150)]
    public sealed class HeroWeaponFx : MonoBehaviour
    {
        /// <summary>Melee weapon drawn (blade lit / claws out).</summary>
        public bool Armed;
        /// <summary>Kael: which arm(s) carry the hard-light blade for the current action (striking arm).</summary>
        public bool BladeRight = true, BladeLeft;
        /// <summary>Swing in progress: trails emit.</summary>
        public bool Swing;
        /// <summary>A melee action owns the arms (attack, ultimate): the pistol is put away at once.</summary>
        public bool Melee;
        /// <summary>Hold-to-aim with the ranged weapon.</summary>
        public bool Aiming;
        /// <summary>World point the ranged weapon aims at (while aiming / right after a shot).</summary>
        public Vector3 AimPoint;
        /// <summary>Weapons hidden and arms released (cinematics, death).</summary>
        public bool Stowed;
        /// <summary>Brightness multiplier (heavies, counters).</summary>
        public float Boost = 1f;

        enum Gun { Holstered, Drawing, Drawn, Holstering }

        Animator anim;
        bool kael;
        CharacterModel model;
        Transform handR, foreR, upperR, handL, foreL, upperL, thighR;
        Vector3 fLocalR, bLocalR, fLocalL, bLocalL, dorsalForeLocalR, dorsalForeLocalL;
        readonly Transform[] fingersR = new Transform[12];
        Transform thumbR1, thumbR2, thumbR3;
        static readonly HumanBodyBones[] FingerBonesR =
        {
            HumanBodyBones.RightIndexProximal, HumanBodyBones.RightIndexIntermediate, HumanBodyBones.RightIndexDistal,
            HumanBodyBones.RightMiddleProximal, HumanBodyBones.RightMiddleIntermediate, HumanBodyBones.RightMiddleDistal,
            HumanBodyBones.RightRingProximal, HumanBodyBones.RightRingIntermediate, HumanBodyBones.RightRingDistal,
            HumanBodyBones.RightLittleProximal, HumanBodyBones.RightLittleIntermediate, HumanBodyBones.RightLittleDistal,
        };
        // grip curl per joint (proximal, intermediate, distal); the index rests on the trigger
        static readonly float[] GripCurl = { 38f, 52f, 26f, 72f, 88f, 46f, 76f, 88f, 46f, 78f, 84f, 44f };
        float handLenR = 0.08f, handLenL = 0.08f, scaleK = 1f;
        Color color;

        // Kael: wrist emitter ring + one hard-light blade per arm
        sealed class Blade
        {
            public Transform Root;
            public Material Hull, Core;
            public float Ignite;
            public WeaponTrail Trail;
            public bool Right;
            /// <summary>Blade root above the forearm axis at the wrist (measured cuff surface + clearance), metres.</summary>
            public float Lift = 0.04f;
            public Vector3 DorsalLocal;     // back-of-wrist direction in forearm-bone space
        }
        Transform emitter, emitterModel, bladeAnchor;
        Material emitterGlow;
        readonly Blade[] blades = new Blade[2];
        float ignite;
        const float BladeLen = 0.95f;
        float wristLateralR = 0.034f, wristDorsalR = 0.028f;
        // Kael: pistol + holster
        Transform pistol, holster, muzzle, eject;
        Material pistolGlow, holsterGlow;
        Gun gun = Gun.Holstered;
        float gunT, gunHold, recoil, armW, handW, drawDur, lastShot = -9f;
        bool fastDraw;
        Vector3 lastAimDir;
        // Giva: gauntlets, claws, palm aim
        Transform gauntL, gauntR;
        Material gauntGlowL, gauntGlowR, clawHullMat, clawCoreMat;
        readonly Transform[] claws = new Transform[6];
        float palmT = -9f, palmW;
        // forearm hologram
        float holoPulse;
        WeaponTrail trailA, trailB;

        // ------------------------------------------------------------------ setup

        public void Init(CharacterModel characterModel, bool isKael)
        {
            model = characterModel;
            anim = model != null ? model.Animator : GetComponent<Animator>();
            kael = isKael;
            if (anim == null || !anim.isHuman) return;
            handR = anim.GetBoneTransform(HumanBodyBones.RightHand);
            foreR = anim.GetBoneTransform(HumanBodyBones.RightLowerArm);
            upperR = anim.GetBoneTransform(HumanBodyBones.RightUpperArm);
            handL = anim.GetBoneTransform(HumanBodyBones.LeftHand);
            foreL = anim.GetBoneTransform(HumanBodyBones.LeftLowerArm);
            upperL = anim.GetBoneTransform(HumanBodyBones.LeftUpperArm);
            thighR = anim.GetBoneTransform(HumanBodyBones.RightUpperLeg);
            for (int i = 0; i < FingerBonesR.Length; i++) fingersR[i] = anim.GetBoneTransform(FingerBonesR[i]);
            thumbR1 = anim.GetBoneTransform(HumanBodyBones.RightThumbProximal);
            thumbR2 = anim.GetBoneTransform(HumanBodyBones.RightThumbIntermediate);
            thumbR3 = anim.GetBoneTransform(HumanBodyBones.RightThumbDistal);
            HandFrame(true, out fLocalR, out bLocalR, out handLenR);
            HandFrame(false, out fLocalL, out bLocalL, out handLenL);
            scaleK = Mathf.Clamp(transform.lossyScale.x, 0.01f, 100f);
            if (foreR != null && handR != null)
            {
                var axis = (handR.position - foreR.position).normalized;
                var back = Vector3.ProjectOnPlane(handR.rotation * bLocalR, axis).normalized;
                dorsalForeLocalR = Quaternion.Inverse(foreR.rotation) * back;
            }
            if (foreL != null && handL != null)
            {
                var axis = (handL.position - foreL.position).normalized;
                var back = Vector3.ProjectOnPlane(handL.rotation * bLocalL, axis).normalized;
                dorsalForeLocalL = Quaternion.Inverse(foreL.rotation) * back;
            }
            int layer = gameObject.layer;
            if (kael)
            {
                color = CombatMath.Hex(0x5fc8ff);
                BuildKael(layer);
                BuildHolo(CombatMath.Hex(0x3fd8ff), CombatMath.Hex(0x9fe8ff), 1.4f);
            }
            else
            {
                color = CombatMath.Hex(0xc040ff);
                BuildGiva(layer);
                trailA = new WeaponTrail("ClawTrailR", CombatMath.Hex(0xff4fd8), 4.2f) { Fade = 0.17f, FullSpeed = 3.5f };
                trailB = new WeaponTrail("ClawTrailL", CombatMath.Hex(0xa47dff), 4.2f) { Fade = 0.17f, FullSpeed = 3.5f };
                BuildHolo(CombatMath.Hex(0xff3fd0), CombatMath.Hex(0xff60e8), 1.5f);
            }
        }

        /// <summary>
        /// Hand frame from the finger bones, stored in hand-local space: F = wrist → middle knuckle, B = back of the hand.
        /// (Proximal finger bones are children of the hand, so the frame is fixed relative to the hand bone.)
        /// </summary>
        void HandFrame(bool right, out Vector3 fLocal, out Vector3 bLocal, out float len)
        {
            var hand = right ? handR : handL;
            var fore = right ? foreR : foreL;
            fLocal = Vector3.forward;
            bLocal = Vector3.up;
            len = 0.08f;
            if (hand == null) return;
            var mid = anim.GetBoneTransform(right ? HumanBodyBones.RightMiddleProximal : HumanBodyBones.LeftMiddleProximal);
            var idx = anim.GetBoneTransform(right ? HumanBodyBones.RightIndexProximal : HumanBodyBones.LeftIndexProximal);
            var lit = anim.GetBoneTransform(right ? HumanBodyBones.RightLittleProximal : HumanBodyBones.LeftLittleProximal);
            Vector3 F = mid != null ? mid.position - hand.position : fore != null ? hand.position - fore.position : transform.forward;
            len = mid != null ? F.magnitude / scaleKSafe() : 0.08f;
            F.Normalize();
            Vector3 across = idx != null && lit != null ? idx.position - lit.position : (right ? -transform.right : transform.right);
            var B = Vector3.Cross(across, F);
            if (!right) B = -B;
            B = Vector3.ProjectOnPlane(B, F);
            if (B.sqrMagnitude < 1e-6f) B = transform.up;
            B.Normalize();
            fLocal = Quaternion.Inverse(hand.rotation) * F;
            bLocal = Quaternion.Inverse(hand.rotation) * B;
        }

        float scaleKSafe() => Mathf.Clamp(transform.lossyScale.x, 0.01f, 100f);

        void HandWorld(bool right, out Vector3 F, out Vector3 B, out Vector3 T)
        {
            var hand = right ? handR : handL;
            F = hand.rotation * (right ? fLocalR : fLocalL);
            B = hand.rotation * (right ? bLocalR : bLocalL);
            T = Vector3.Cross(F, B) * (right ? 1f : -1f);
        }

        Quaternion HandRotationFor(bool right, Vector3 Ft, Vector3 Bt)
        {
            var fl = right ? fLocalR : fLocalL;
            var bl = right ? bLocalR : bLocalL;
            return Quaternion.LookRotation(Ft, Bt) * Quaternion.Inverse(Quaternion.LookRotation(fl, bl));
        }

        void BuildKael(int layer)
        {
            if (foreR == null || handR == null) return;
            // Fit the cuff ring and both blade roots to the real sleeve / glove / Interface surface at the wrists.
            var axisR = (handR.position - foreR.position).normalized;
            var wristR = handR.position - axisR * 0.012f * scaleK;
            var dorsalR = foreR.rotation * dorsalForeLocalR;
            var lateralR = Vector3.Cross(dorsalR, axisR);
            float dR = SurfaceDistance(wristR, axisR, dorsalR, 0.03f * scaleK);
            float lR = Mathf.Max(SurfaceDistance(wristR, axisR, lateralR, 0.03f * scaleK), SurfaceDistance(wristR, axisR, -lateralR, 0.03f * scaleK));
            wristDorsalR = Mathf.Clamp(dR / scaleK, 0.02f, 0.06f);
            wristLateralR = Mathf.Clamp(lR / scaleK, 0.024f, 0.07f);
            emitter = WeaponLibrary.Spawn("kael_emitter", transform, layer, out emitterGlow)?.transform;
            if (emitter != null)
            {
                bladeAnchor = WeaponLibrary.FindDeep(emitter, "blade_root");
                if (emitter.childCount > 0) emitterModel = emitter.GetChild(0);
                // ring authored for a 34 x 28 mm wrist: stretch it onto the measured cuff (+1.5 mm so it sits on it)
                emitter.localScale = new Vector3((wristLateralR + 0.0015f) / 0.034f, (wristDorsalR + 0.0015f) / 0.028f, 1f);
            }
            var hull = WeaponLibrary.FxMesh("kael_blade_hull");
            var core = WeaponLibrary.FxMesh("kael_blade_core");
            if (hull != null && core != null)
            {
                for (int i = 0; i < 2; i++)
                {
                    var b = new Blade { Right = i == 0 };
                    // Cyan body with a white-hot edge and a thin core, kept under the tonemapper's white point so the
                    // blade reads as coloured light with a visible edge (bloom adds the glow), not a white stick.
                    // dim saturated cyan body, white-hot cutting edge, cyan-white core
                    var body = CombatMath.Hex(0x2ec0ff);
                    b.Hull = WeaponLibrary.HardLight(FxMaterials.Hdr(body, 0.42f), FxMaterials.Hdr(Color.Lerp(body, Color.white, 0.7f), 0.9f), 1f, 0);
                    b.Core = WeaponLibrary.HardLight(FxMaterials.Hdr(body, 0.3f), FxMaterials.Hdr(Color.Lerp(body, Color.white, 0.12f), 0.4f), 1f, 1);
                    b.Hull.SetFloat(WeaponLibrary.EdgeBoostId, 1.2f);
                    var root = new GameObject(b.Right ? "HardLightBladeR" : "HardLightBladeL").transform;
                    root.SetParent(transform, false);
                    root.gameObject.layer = layer;
                    WeaponLibrary.FxRenderer("BladeHull", hull, b.Hull, root, layer);
                    WeaponLibrary.FxRenderer("BladeCore", core, b.Core, root, layer);
                    root.gameObject.SetActive(false);
                    b.Root = root;
                    b.Trail = new WeaponTrail(b.Right ? "BladeTrailR" : "BladeTrailL", CombatMath.Hex(0x3fb4ff), 3.2f) { Fade = 0.15f, FullSpeed = 5f };
                    blades[i] = b;
                }
                blades[0].Lift = (wristDorsalR + 0.0045f) * scaleK;
                blades[0].DorsalLocal = dorsalForeLocalR;
                if (foreL != null && handL != null)
                {
                    var axisL = (handL.position - foreL.position).normalized;
                    var wristL = handL.position - axisL * 0.03f * scaleK;
                    var dorsalL = foreL.rotation * dorsalForeLocalL;
                    // the left blade forms out of the Interface's glow: just above the guard surface
                    blades[1].Lift = Mathf.Clamp(SurfaceDistance(wristL, axisL, dorsalL, 0.04f * scaleK), 0.02f * scaleK, 0.07f * scaleK) + 0.003f * scaleK;
                    blades[1].DorsalLocal = dorsalForeLocalL;
                }
            }
            pistol = WeaponLibrary.Spawn("kael_pistol", transform, layer, out pistolGlow)?.transform;
            if (pistol != null)
            {
                muzzle = WeaponLibrary.FindDeep(pistol, "muzzle");
                eject = WeaponLibrary.FindDeep(pistol, "eject");
            }
            if (thighR != null)
            {
                holster = WeaponLibrary.Spawn("kael_holster", thighR, layer, out holsterGlow)?.transform;
                if (holster != null) PlaceHolster();
            }
            WeaponLibrary.SetGlow(emitterGlow, color, 0.45f);
            WeaponLibrary.SetGlow(pistolGlow, color, 0.9f);
            WeaponLibrary.SetGlow(holsterGlow, color, 0.8f);
        }

        /// <summary>
        /// Holster on the outer right thigh: muzzle down the leg, grip pointing back, its slim back plate resting on the
        /// measured trouser surface (holster space: thigh axis at x -0.104, y 0.05; plate inner radius 0.078).
        /// </summary>
        void PlaceHolster()
        {
            var knee = anim.GetBoneTransform(HumanBodyBones.RightLowerLeg);
            Vector3 down = knee != null ? (knee.position - thighR.position).normalized : -transform.up;
            Vector3 fwd = Vector3.ProjectOnPlane(transform.forward, down).normalized;
            Vector3 outward = Vector3.Cross(fwd, down).normalized; // right side of the character for the right leg
            if (Vector3.Dot(outward, transform.right) < 0f) outward = -outward;
            var rot = Quaternion.LookRotation(down, fwd);
            var a = thighR.position + down * 0.16f * scaleK;
            // thigh surface on the outer side, around the strap height
            float rt = SurfaceDistance(a + down * 0.09f * scaleK, down, outward, 0.05f * scaleK) / scaleK;
            if (rt < 0.04f || rt > 0.14f) rt = 0.075f;
            float off = Mathf.Max(rt + 0.003f, 0.078f) + 0.026f;
            var pos = a + (outward * off - fwd * 0.05f) * scaleK;
            holster.SetPositionAndRotation(pos, rot);
            holster.localScale = Vector3.one * scaleK / Mathf.Max(1e-4f, thighR.lossyScale.x);
        }

        void BuildGiva(int layer)
        {
            if (handL == null || handR == null) return;
            gauntL = AttachGauntlet("giva_gauntlet_L", handL, true, layer, out gauntGlowL);
            gauntR = AttachGauntlet("giva_gauntlet_R", handR, false, layer, out gauntGlowR);
            var hull = WeaponLibrary.FxMesh("giva_claw_hull");
            var core = WeaponLibrary.FxMesh("giva_claw_core");
            if (hull != null && core != null)
            {
                clawHullMat = WeaponLibrary.HardLight(FxMaterials.Hdr(CombatMath.Hex(0xd04cff), 0.45f), FxMaterials.Hdr(CombatMath.Hex(0xffc8f6), 0.9f), 1f, 0);
                clawCoreMat = WeaponLibrary.HardLight(FxMaterials.Hdr(CombatMath.Hex(0xd04cff), 0.3f), FxMaterials.Hdr(CombatMath.Hex(0xe070ff), 0.4f), 1f, 1);
                clawHullMat.SetFloat(WeaponLibrary.EdgeBoostId, 1.0f);
                for (int h = 0; h < 2; h++)
                {
                    var g = h == 0 ? gauntL : gauntR;
                    if (g == null) continue;
                    for (int i = 0; i < 3; i++)
                    {
                        var socket = WeaponLibrary.FindDeep(g, "claw_" + i);
                        if (socket == null) continue;
                        var c = new GameObject("Claw" + i).transform;
                        c.SetParent(socket, false);
                        c.gameObject.layer = layer;
                        // gentle fan: outer claws splay a few degrees, all tilt slightly to the palm
                        float fan = (i - 1) * (h == 0 ? -5f : 5f);
                        c.localRotation = Quaternion.Euler(4f, fan, 0f);
                        WeaponLibrary.FxRenderer("Hull", hull, clawHullMat, c, layer);
                        WeaponLibrary.FxRenderer("Core", core, clawCoreMat, c, layer);
                        c.gameObject.SetActive(false);
                        claws[h * 3 + i] = c;
                    }
                }
            }
            WeaponLibrary.SetGlow(gauntGlowL, CombatMath.Hex(0xe040ff), 0.9f);
            WeaponLibrary.SetGlow(gauntGlowR, CombatMath.Hex(0xe040ff), 0.9f);
        }

        Transform AttachGauntlet(string child, Transform hand, bool left, int layer, out Material glow)
        {
            var g = WeaponLibrary.Spawn("giva_gauntlet", hand, layer, out glow, null, true, child)?.transform;
            if (g == null) return null;
            HandWorld(!left, out var F, out var B, out _);
            g.rotation = Quaternion.LookRotation(F, B);
            g.position = hand.position - F * 0.006f * scaleK;
            float k = Mathf.Clamp((left ? handLenL : handLenR) / 0.078f, 0.85f, 1.3f);
            // cuff authored 40.5 x 31.5 mm (half axes) at the wrist: fit it to the measured glove / sleeve
            var fore = left ? foreL : foreR;
            float kx = k, ky = k;
            if (fore != null)
            {
                var axis = (hand.position - fore.position).normalized;
                var wp = hand.position - axis * 0.008f * scaleK;
                var lat = Vector3.Cross(B, F).normalized;
                float rl = Mathf.Max(SurfaceDistance(wp, axis, lat, 0.025f * scaleK), SurfaceDistance(wp, axis, -lat, 0.025f * scaleK)) / scaleK;
                float rd = SurfaceDistance(wp, axis, B, 0.025f * scaleK) / scaleK;
                if (rl > 0.015f) kx = Mathf.Clamp((rl + 0.004f) / 0.0405f, 0.7f, 1.2f);
                if (rd > 0.012f) ky = Mathf.Clamp((rd + 0.004f) / 0.0315f, 0.7f, 1.2f);
            }
            g.localScale = new Vector3(kx, ky, k) * scaleK / Mathf.Max(1e-4f, hand.lossyScale.x);
            return g;
        }

        /// <summary>
        /// Animated forearm screen: drives the hero's own "Screen" material (Giva's holo guard, Kael's Interface) with a
        /// live readout feel: slow breathing, scan-line flicker dips, a hotter faster pattern in combat and a flare on every
        /// shot / hit (no extra geometry, so it can never float off the arm).
        /// </summary>
        void BuildHolo(Color c1, Color c2, float intensity)
        {
            if (model == null) return;
            screenMat = model.Mat("Screen");
            if (screenMat == null || !screenMat.HasProperty(WeaponLibrary.EmissionColorId)) { screenMat = null; return; }
            screenMat.EnableKeyword("_EMISSION");
            screenBase = screenMat.GetColor(WeaponLibrary.EmissionColorId);
            if (screenBase.maxColorComponent < 0.05f) screenBase = FxMaterials.Hdr(c1, intensity);
            screenCombat = FxMaterials.Hdr(c2, intensity * 1.3f);
        }

        Material screenMat;
        Color screenBase, screenCombat;
        float screenCombatW, screenNoise;

        // ------------------------------------------------------------------ API (Hero)

        /// <summary>Flash the weapon brighter for a moment (hit confirm, counter).</summary>
        public void Pulse(float amount)
        {
            Boost = Mathf.Max(Boost, 1f + amount);
            holoPulse = 1f;
        }

        /// <summary>
        /// Where a bolt fired along `dir` leaves the weapon: the pistol muzzle / palm emitter in the aim pose (predicted
        /// when the weapon is not raised yet, so the shot and the drawn pose line up).
        /// </summary>
        public Vector3 MuzzleFor(Vector3 dir)
        {
            dir = dir.sqrMagnitude > 1e-6f ? dir.normalized : transform.forward;
            if (kael)
            {
                if (muzzle != null && gun == Gun.Drawn && armW > 0.9f && Vector3.Angle(lastAimDir, dir) < 8f) return muzzle.position;
                if (upperR == null) return transform.position + Vector3.up * 1.4f + dir * 0.6f;
                return AimHandTarget(upperR, foreR, handR, dir, true) + dir * 0.24f * scaleK + Vector3.up * 0.06f * scaleK;
            }
            if (upperL == null) return transform.position + Vector3.up * 1.3f + dir * 0.5f;
            return AimHandTarget(upperL, foreL, handL, dir, false) + dir * 0.06f * scaleK;
        }

        /// <summary>A bolt left the weapon along `dir` (draw + aim + recoil + casing for Kael, palm blast for Giva).</summary>
        public void Fired(Vector3 dir)
        {
            dir = dir.sqrMagnitude > 1e-6f ? dir.normalized : transform.forward;
            lastAimDir = dir;
            lastShot = Time.time;
            AimPoint = transform.position + Vector3.up * 1.4f + dir * 20f;
            if (kael)
            {
                // quick-draw: the gun is in the raised hand on the shot frame (the bolt and flash leave its muzzle)
                if (gun == Gun.Holstered || gun == Gun.Holstering) { gun = Gun.Drawn; fastDraw = true; G.Audio?.Play("pistol_draw", transform.position, 0.6f); }
                armW = 1f;
                handW = 1f;
                gunHold = 0.75f;
                recoil = 1f;
                WeaponLibrary.SetGlow(pistolGlow, color, 3.2f);
                if (eject != null && pistol != null)
                    WeaponFx.Casing(eject.position, pistol.rotation, pistol.right * 1.6f + pistol.up * 1.9f - pistol.forward * 0.4f);
            }
            else
            {
                palmT = Time.time;
                palmW = 1f;     // the palm is up on the shot frame (the bolt leaves it)
                WeaponLibrary.SetGlow(gauntGlowL, CombatMath.Hex(0xff70f0), 3.5f);
            }
            holoPulse = 1f;
        }

        // ------------------------------------------------------------------ update

        void LateUpdate()
        {
            if (anim == null) return;
            float dt = Time.deltaTime * anim.speed;
            float rdt = Time.deltaTime;
            Boost = Mathf.MoveTowards(Boost, 1f, rdt * 4f);
            if (kael) TickKael(dt, rdt);
            else TickGiva(dt, rdt);
            TickHolo(rdt);
        }

        // ---- Kael

        void TickKael(float dt, float rdt)
        {
            if (handR == null || foreR == null) return;
            TickGun(dt, rdt);
            // cuff ring: on the wrist end of the forearm, oriented by the forearm axis and the back of the wrist
            Frame(true, out var axisR, out var dorsalR);
            if (emitter != null)
                emitter.SetPositionAndRotation(handR.position - axisR * 0.012f * scaleK, Quaternion.LookRotation(axisR, dorsalR));
            bool gunAway = gun == Gun.Holstered;
            float any = 0f;
            for (int i = 0; i < 2; i++)
            {
                var b = blades[i];
                if (b == null) continue;
                bool want = Armed && !Stowed && gunAway && (b.Right ? BladeRight : BladeLeft);
                TickBlade(b, want, dt, rdt);
                any = Mathf.Max(any, b.Ignite);
            }
            // ring line: faint at rest, flares while a blade is out
            if (emitterGlow != null)
            {
                var cur = emitterGlow.GetColor(WeaponLibrary.BaseColorId);
                var tgt = FxMaterials.Hdr(color, 0.45f + 1.6f * (blades[0] != null ? blades[0].Ignite : 0f) * Boost);
                emitterGlow.SetColor(WeaponLibrary.BaseColorId, Color.Lerp(cur, tgt, 1f - Mathf.Exp(-rdt * 12f)));
            }
            ignite = any;
        }

        /// <summary>Forearm axis (elbow → wrist) and the back-of-wrist direction for one arm (half forearm roll, half hand
        /// roll, like the twist bones that carry the sleeve and guard).</summary>
        void Frame(bool right, out Vector3 axis, out Vector3 dorsal)
        {
            var hand = right ? handR : handL;
            var fore = right ? foreR : foreL;
            axis = (hand.position - fore.position).normalized;
            var dHand = Vector3.ProjectOnPlane(hand.rotation * (right ? bLocalR : bLocalL), axis).normalized;
            var dFore = Vector3.ProjectOnPlane(fore.rotation * (right ? dorsalForeLocalR : dorsalForeLocalL), axis).normalized;
            dorsal = (dHand + dFore).normalized;
            if (dorsal.sqrMagnitude < 1e-4f) dorsal = transform.up;
        }

        void TickBlade(Blade b, bool want, float dt, float rdt)
        {
            var hand = b.Right ? handR : handL;
            var fore = b.Right ? foreR : foreL;
            if (hand == null || fore == null) return;
            // forms fast on the wind-up, withdraws after the recovery
            b.Ignite = want ? Mathf.MoveTowards(b.Ignite, 1f, dt / 0.08f) : Mathf.MoveTowards(b.Ignite, 0f, Mathf.Max(dt, rdt * 0.5f) / 0.13f);
            bool vis = b.Ignite > 0.005f;
            if (b.Root.gameObject.activeSelf != vis)
            {
                b.Root.gameObject.SetActive(vis);
                if (vis && want) G.Audio?.Play("blade_ignite", hand.position, 0.55f);
                else if (!vis) G.Audio?.Play("blade_retract", hand.position, 0.35f);
            }
            Frame(b.Right, out var axis, out var dorsal);
            Vector3 root;
            if (b.Right && bladeAnchor != null) root = bladeAnchor.position;
            else root = hand.position - axis * (b.Right ? 0.012f : 0.03f) * scaleK + dorsal * b.Lift;
            // along the strike: the forearm line, tipped a hair over the knuckles so the fist never cuts it
            var bdir = (axis + dorsal * 0.05f).normalized;
            if (vis)
            {
                // edge (+x) towards the little-finger side for the right arm, mirrored for the left
                b.Root.SetPositionAndRotation(root, Quaternion.LookRotation(bdir, dorsal));
                float flick = 1f + Mathf.Sin(Time.time * 53f + (b.Right ? 0f : 1.7f)) * 0.02f;
                b.Root.localScale = new Vector3(b.Right ? flick : -flick, flick, BladeLen);
                float e = Mathf.SmoothStep(0f, 1f, b.Ignite);
                b.Hull.SetFloat(WeaponLibrary.ExtendId, e);
                b.Core.SetFloat(WeaponLibrary.ExtendId, Mathf.Clamp01(e * 1.04f - 0.02f));
                b.Hull.SetFloat(WeaponLibrary.IntensityId, Boost);
                b.Core.SetFloat(WeaponLibrary.IntensityId, Boost);
            }
            float len = BladeLen * scaleK * Mathf.SmoothStep(0f, 1f, b.Ignite);
            b.Trail?.Tick(dt, Swing && b.Ignite > 0.6f, root + bdir * len * 0.3f, root + bdir * len);
        }

        /// <summary>
        /// Furthest skinned-mesh surface point from a limb axis in direction `dir`, within ±slab along the axis
        /// (sleeve / glove / guard / thigh), measured once at spawn on the bind pose. 0 when nothing is found.
        /// </summary>
        float SurfaceDistance(Vector3 p, Vector3 axis, Vector3 dir, float slab)
        {
            if (model == null) return 0f;
            float best = 0f;
            var tmp = surfaceMesh ??= new Mesh();
            float maxR = 0.16f * scaleK;
            foreach (var r in model.Renderers)
            {
                if (r == null || !r.enabled || !r.gameObject.activeInHierarchy || r.sharedMesh == null) continue;
                if (r.bounds.SqrDistance(p) > maxR * maxR) continue;
                r.BakeMesh(tmp, true);
                var verts = tmp.vertices;
                var tr = r.transform;
                for (int i = 0; i < verts.Length; i++)
                {
                    var d = tr.position + tr.rotation * verts[i] - p;
                    float along = Vector3.Dot(d, axis);
                    if (along > slab || along < -slab) continue;
                    var radial = d - axis * along;
                    float m = radial.magnitude;
                    if (m > maxR || m < 1e-4f) continue;
                    float proj = Vector3.Dot(radial, dir);
                    if (proj > best && proj > m * 0.85f) best = proj;
                }
            }
            return best;
        }
        Mesh surfaceMesh;

        void TickGun(float dt, float rdt)
        {
            if (pistol == null) return;
            bool stow = Stowed || Melee;
            if (stow && gun != Gun.Holstered)
            {
                // a swing (or cutscene) takes the arm: snap the gun home
                if (gun != Gun.Holstering || Melee) { gun = Gun.Holstered; G.Audio?.Play("pistol_holster", transform.position, 0.45f); }
                if (Melee) { armW = 0f; handW = 0f; }
            }
            if (!stow)
            {
                if (Aiming && gun == Gun.Holstered) { gun = Gun.Drawing; gunT = 0f; fastDraw = false; drawDur = 0.2f; G.Audio?.Play("pistol_draw", transform.position, 0.7f); }
                if (Aiming && gun == Gun.Holstering) { gun = Gun.Drawn; }
            }
            Vector3 aimDir = AimPoint - (upperR != null ? upperR.position : transform.position);
            aimDir = aimDir.sqrMagnitude > 1e-4f ? aimDir.normalized : transform.forward;
            if (Aiming) lastAimDir = aimDir;
            else if (lastAimDir.sqrMagnitude < 0.5f) lastAimDir = transform.forward;
            recoil = Mathf.MoveTowards(recoil, 0f, rdt / 0.14f);
            float wantArm = 0f, wantHand = 0f;
            bool inHand = false;
            switch (gun)
            {
                case Gun.Holstered:
                    break;
                case Gun.Drawing:
                    gunT += dt;
                    {
                        float u = gunT / drawDur;
                        wantArm = 1f;
                        wantHand = 1f;
                        inHand = u > 0.42f;
                        if (u >= 1f) { gun = Gun.Drawn; gunHold = 0.75f; }
                    }
                    break;
                case Gun.Drawn:
                    inHand = true;
                    wantArm = wantHand = 1f;
                    if (!Aiming)
                    {
                        gunHold -= dt;
                        if (gunHold <= 0f) { gun = Gun.Holstering; gunT = 0f; }
                    }
                    break;
                case Gun.Holstering:
                    gunT += dt;
                    inHand = gunT < 0.2f;
                    wantArm = wantHand = gunT < 0.2f ? 1f : 0f;
                    if (gunT >= 0.2f && gunT - dt < 0.2f) G.Audio?.Play("pistol_holster", transform.position, 0.5f);
                    if (gunT >= 0.3f) gun = Gun.Holstered;
                    break;
            }
            float rate = fastDraw ? 1f / 0.06f : 1f / 0.12f;
            armW = Mathf.MoveTowards(armW, wantArm, rdt * rate);
            handW = Mathf.MoveTowards(handW, wantHand, rdt * rate);
            if (gun == Gun.Drawn) fastDraw = false;
            // arm pose: reach to the holster while drawing / holstering, else aim
            if (armW > 0.001f && upperR != null && foreR != null && handR != null)
            {
                Vector3 target;
                Quaternion handRot;
                bool towardHolster = (gun == Gun.Drawing && gunT / drawDur < 0.42f) || (gun == Gun.Holstering && gunT > 0.08f);
                if (towardHolster && holster != null)
                {
                    // hand to the grip in the holster (the pistol's grip frame inverted)
                    GripFrameFromGun(holster.position, holster.rotation, out target, out handRot);
                }
                else
                {
                    var dir = lastAimDir;
                    if (recoil > 0f) dir = Quaternion.AngleAxis(-9f * recoil, Vector3.Cross(Vector3.up, dir).normalized) * dir;
                    target = AimHandTarget(upperR, foreR, handR, dir, true) - dir * 0.035f * recoil * scaleK;
                    var up = Vector3.ProjectOnPlane(Vector3.up, dir).normalized;
                    // a slight inward cant reads as a natural one-handed hold
                    up = Quaternion.AngleAxis(12f, dir) * up;
                    var Bt = Vector3.Cross(up, dir);
                    handRot = HandRotationFor(true, dir, Bt);
                }
                var elbowPole = upperR.position - transform.up * 0.5f * scaleK + transform.right * 0.35f * scaleK - transform.forward * 0.1f * scaleK;
                IK.TwoBone(upperR, foreR, handR, target, elbowPole, armW);
                handR.rotation = Quaternion.Slerp(handR.rotation, handRot, handW * armW);
            }
            // gun placement (fingers close round the grip)
            if (inHand)
            {
                CurlGrip(handW * armW);
                GunInHand();
            }
            else if (holster != null) pistol.SetPositionAndRotation(holster.position, holster.rotation);
            if (pistolGlow != null)
            {
                var cur = pistolGlow.GetColor(WeaponLibrary.BaseColorId);
                pistolGlow.SetColor(WeaponLibrary.BaseColorId, Color.Lerp(cur, FxMaterials.Hdr(color, inHand ? 1.4f : 0.8f), 1f - Mathf.Exp(-rdt * 10f)));
            }
        }

        /// <summary>Close the right hand round the pistol grip (flex every finger joint towards the palm; thumb wraps over).</summary>
        void CurlGrip(float w)
        {
            if (w <= 0.001f) return;
            HandWorld(true, out var F, out var B, out var T);
            var axis = Vector3.Cross(B, F).normalized;            // rotates the fingers from F towards the palm (-B)
            for (int i = 0; i < fingersR.Length; i++)
            {
                var b = fingersR[i];
                if (b == null) continue;
                b.rotation = Quaternion.AngleAxis(GripCurl[i] * w, axis) * b.rotation;
            }
            if (thumbR1 != null)
            {
                // thumb folds across the grip, under the slide
                thumbR1.rotation = Quaternion.AngleAxis(-18f * w, F) * thumbR1.rotation;
                var td = thumbR2 != null ? (thumbR2.position - thumbR1.position).normalized : F;
                var tax = Vector3.Cross(td, -B).normalized;
                if (thumbR2 != null) thumbR2.rotation = Quaternion.AngleAxis(24f * w, tax) * thumbR2.rotation;
                if (thumbR3 != null) thumbR3.rotation = Quaternion.AngleAxis(20f * w, tax) * thumbR3.rotation;
            }
        }

        /// <summary>The pistol in the right fist: grip through the palm, slide on the thumb side, barrel along the fingers.</summary>
        void GunInHand()
        {
            HandWorld(true, out var F, out var B, out var T);
            float k = Mathf.Clamp(handLenR / 0.08f, 0.85f, 1.25f) * scaleK;
            var rot = Quaternion.LookRotation(F, T) * Quaternion.Euler(-6f, 0f, 0f);
            var pos = handR.position + F * 0.062f * k - B * 0.026f * k + T * 0.004f * k;
            pistol.SetPositionAndRotation(pos, rot);
        }

        /// <summary>Inverse of <see cref="GunInHand"/>: the hand pose that holds a gun at (pos, rot).</summary>
        void GripFrameFromGun(Vector3 gunPos, Quaternion gunRot, out Vector3 handPos, out Quaternion handRot)
        {
            var r = gunRot * Quaternion.Inverse(Quaternion.Euler(-6f, 0f, 0f));
            var F = r * Vector3.forward;
            var T = r * Vector3.up;
            var B = Vector3.Cross(T, F);
            float k = Mathf.Clamp(handLenR / 0.08f, 0.85f, 1.25f) * scaleK;
            handPos = gunPos - F * 0.062f * k + B * 0.026f * k - T * 0.004f * k;
            handRot = HandRotationFor(true, F, B);
        }

        /// <summary>Hand target for an outstretched arm aiming along `dir` from the shoulder.</summary>
        Vector3 AimHandTarget(Transform upper, Transform lower, Transform hand, Vector3 dir, bool pistolHold)
        {
            float reach = (Vector3.Distance(upper.position, lower.position) + Vector3.Distance(lower.position, hand.position));
            var p = upper.position + dir * reach * (pistolHold ? 0.9f : 0.86f);
            return p - transform.up * 0.03f * scaleK;
        }

        // ---- Giva

        void TickGiva(float dt, float rdt)
        {
            ignite = Armed && !Stowed ? Mathf.MoveTowards(ignite, 1f, dt / 0.07f) : Mathf.MoveTowards(ignite, 0f, Mathf.Max(dt, rdt * 0.5f) / 0.18f);
            bool vis = ignite > 0.005f;
            for (int i = 0; i < claws.Length; i++)
            {
                var c = claws[i];
                if (c == null) continue;
                if (c.gameObject.activeSelf != vis)
                {
                    c.gameObject.SetActive(vis);
                    if (vis && i == 0) G.Audio?.Play("claw_extend", c.position, 0.5f);
                }
            }
            if (vis && clawHullMat != null)
            {
                float e = Mathf.SmoothStep(0f, 1f, ignite);
                clawHullMat.SetFloat(WeaponLibrary.ExtendId, e);
                clawCoreMat.SetFloat(WeaponLibrary.ExtendId, Mathf.Clamp01(e * 1.05f - 0.03f));
                clawHullMat.SetFloat(WeaponLibrary.IntensityId, Boost);
                clawCoreMat.SetFloat(WeaponLibrary.IntensityId, Boost);
            }
            ClawTrail(trailA, 1, dt);
            ClawTrail(trailB, 4, dt);
            // palm blast pose: the left arm snaps up palm-forward for the shot, holds, then eases down
            float since = Time.time - palmT;
            if (Aiming) lastAimDir = (AimPoint - (upperL != null ? upperL.position : transform.position)).normalized;
            float want = Stowed || Melee ? 0f : since < 0.32f || Aiming ? 1f : 0f;
            palmW = Mathf.MoveTowards(palmW, want, rdt * (want > palmW ? 1f / 0.05f : 1f / 0.22f));
            if (palmW > 0.001f && upperL != null && foreL != null && handL != null)
            {
                var dir = lastAimDir.sqrMagnitude > 0.5f ? lastAimDir : transform.forward;
                var target = AimHandTarget(upperL, foreL, handL, dir, false);
                var up = Vector3.ProjectOnPlane(Vector3.up, dir).normalized;
                // fingers up and a little out, palm (−B) facing the target
                var Ft = (up * 0.9f - Vector3.Cross(up, dir) * 0.25f + dir * 0.15f).normalized;
                var Bt = Vector3.ProjectOnPlane(-dir, Ft).normalized;
                var pole = upperL.position - transform.up * 0.5f * scaleK - transform.right * 0.35f * scaleK - transform.forward * 0.1f * scaleK;
                IK.TwoBone(upperL, foreL, handL, target, pole, palmW);
                handL.rotation = Quaternion.Slerp(handL.rotation, HandRotationFor(false, Ft, Bt), palmW);
            }
            float g = 0.9f + 1.4f * ignite * Boost;
            FadeGlow(gauntGlowL, CombatMath.Hex(0xe040ff), g, rdt);
            FadeGlow(gauntGlowR, CombatMath.Hex(0xe040ff), g, rdt);
        }

        static void FadeGlow(Material m, Color c, float intensity, float rdt)
        {
            if (m == null) return;
            var cur = m.GetColor(WeaponLibrary.BaseColorId);
            m.SetColor(WeaponLibrary.BaseColorId, Color.Lerp(cur, FxMaterials.Hdr(c, intensity), 1f - Mathf.Exp(-rdt * 9f)));
        }

        void ClawTrail(WeaponTrail trail, int clawIndex, float dt)
        {
            if (trail == null) return;
            var c = claws[clawIndex];
            if (c == null)
            {
                var hand = clawIndex < 3 ? handL : handR;
                var fore = clawIndex < 3 ? foreL : foreR;
                if (hand == null || fore == null) return;
                Vector3 dir = (hand.position - fore.position).normalized;
                trail.Tick(dt, Swing && ignite > 0.5f, hand.position - dir * 0.02f, hand.position + dir * 0.36f);
                return;
            }
            float len = 0.165f * c.lossyScale.z * ignite;
            trail.Tick(dt, Swing && ignite > 0.5f, c.position, c.position + c.forward * len);
        }

        // ---- hologram

        void TickHolo(float rdt)
        {
            if (screenMat == null) return;
            holoPulse = Mathf.MoveTowards(holoPulse, 0f, rdt * 1.6f);
            bool combat = Armed || Aiming || Time.time - lastShot < 1.5f || Time.time - palmT < 1.5f;
            screenCombatW = Mathf.MoveTowards(screenCombatW, combat ? 1f : 0f, rdt * 2.5f);
            float t = Time.time;
            // scan flicker: brief dips at irregular intervals, faster in combat
            screenNoise -= rdt * (1f + 2f * screenCombatW);
            float dip = 1f;
            if (screenNoise < 0f)
            {
                dip = 0.35f;
                if (screenNoise < -0.05f) screenNoise = Random.Range(0.4f, 2.2f);
            }
            float breathe = 0.85f + 0.15f * Mathf.Sin(t * (2.1f + 5f * screenCombatW));
            var c = Color.Lerp(screenBase, screenCombat, screenCombatW * 0.7f);
            float k = breathe * dip * (1f + screenCombatW * 0.4f + holoPulse * 1.8f) * (Stowed ? 0.6f : 1f);
            screenMat.SetColor(WeaponLibrary.EmissionColorId, c * k);
        }

        void OnDestroy()
        {
            trailA?.Destroy();
            trailB?.Destroy();
            if (screenMat != null) screenMat.SetColor(WeaponLibrary.EmissionColorId, screenBase);
            foreach (var m in new[] { emitterGlow, pistolGlow, holsterGlow, gauntGlowL, gauntGlowR, clawHullMat, clawCoreMat })
                if (m != null) Destroy(m);
            foreach (var b in blades)
            {
                if (b == null) continue;
                b.Trail?.Destroy();
                if (b.Hull != null) Destroy(b.Hull);
                if (b.Core != null) Destroy(b.Core);
            }
            if (surfaceMesh != null) Destroy(surfaceMesh);
            if (pistol != null) Destroy(pistol.gameObject);
            if (holster != null) Destroy(holster.gameObject);
        }
    }

    /// <summary>Analytic two-bone IK (shoulder-elbow-wrist) applied on top of the animated pose, blended by weight.</summary>
    public static class IK
    {
        public static void TwoBone(Transform upper, Transform lower, Transform end, Vector3 target, Vector3 pole, float weight)
        {
            if (weight <= 0f || upper == null || lower == null || end == null) return;
            Quaternion u0 = upper.localRotation, l0 = lower.localRotation;
            Vector3 a = upper.position, b = lower.position, c = end.position;
            float lab = (b - a).magnitude, lcb = (c - b).magnitude;
            if (lab < 1e-5f || lcb < 1e-5f) return;
            float lat = Mathf.Clamp((target - a).magnitude, 0.02f * (lab + lcb), (lab + lcb) * 0.999f);
            float cur = Vector3.Angle(a - b, c - b);
            float want = Mathf.Acos(Mathf.Clamp((lab * lab + lcb * lcb - lat * lat) / (2f * lab * lcb), -1f, 1f)) * Mathf.Rad2Deg;
            Vector3 axis = Vector3.Cross(c - b, a - b);
            if (axis.sqrMagnitude < 1e-10f) axis = Vector3.Cross(target - a, pole - a);
            if (axis.sqrMagnitude < 1e-10f) return;
            axis.Normalize();
            lower.rotation = Quaternion.AngleAxis(cur - want, axis) * lower.rotation;
            c = end.position;
            upper.rotation = Quaternion.FromToRotation(c - a, target - a) * upper.rotation;
            Vector3 ax = (target - a).normalized;
            b = lower.position;
            Vector3 pe = Vector3.ProjectOnPlane(b - a, ax), pp = Vector3.ProjectOnPlane(pole - a, ax);
            if (pe.sqrMagnitude > 1e-8f && pp.sqrMagnitude > 1e-8f)
                upper.rotation = Quaternion.AngleAxis(Vector3.SignedAngle(pe, pp, ax), ax) * upper.rotation;
            if (weight < 0.999f)
            {
                upper.localRotation = Quaternion.Slerp(u0, upper.localRotation, weight);
                lower.localRotation = Quaternion.Slerp(l0, lower.localRotation, weight);
            }
        }
    }
}
