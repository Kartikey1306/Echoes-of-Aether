using System;
using System.Linq;
using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Runtime motion polish for humanoid characters (lives next to the Animator):
    ///   • foot IK — feet plant on stairs, ramps and uneven ground, pelvis lowers to the lower foot;
    ///   • head/eye look-at — towards a lock-on target, an interactable or a conversation partner;
    ///   • lean — the upper body banks into turns proportionally to speed × turn rate;
    ///   • standing knees — standing still out of combat with both feet planted, the pelvis rises until the straighter
    ///     leg is nearly straight (<see cref="StandKneeBend"/>); the feet stay planted by the foot IK. The motion-capture
    ///     idles stand on 20–26° of knee bend, which read as a crouch;
    ///   • foot lock — a foot on the ground is pinned where it touched down until it lifts (or would have to stretch
    ///     more than <see cref="LockMaxDrift"/>), so a gait whose stride does not exactly match the move speed does not
    ///     slide its stance foot.
    /// Requires "IK Pass" on the base Animator layer (set by CharacterBuilder).
    /// </summary>
    [RequireComponent(typeof(Animator))]
    public sealed class HumanoidPolish : MonoBehaviour
    {
        public Func<bool> IsGrounded;
        /// <summary>World point to look at (null = look ahead).</summary>
        public Vector3? LookTarget;
        public bool FootIK = true;
        public float MaxLeanDeg = 11f;
        /// <summary>Sole heights below this (m) count as "should be planted" and are eased onto the ground.</summary>
        public float FloatBand = 0.08f;
        /// <summary>Knee bend (degrees) the straighter leg is brought to when standing; ≤ 0 disables it.</summary>
        public float StandKneeBend = 3f;
        public float MaxStandRaise = 0.07f;
        /// <summary>Current pelvis raise for straighter standing knees (m).</summary>
        public float StandRaise => standRaise;
        /// <summary>Pin feet on the ground where they touched down (see class summary).</summary>
        public bool FootLock = true;
        /// <summary>Sole height (m) under which a foot counts as on the ground for the lock.</summary>
        public float LockContact = 0.025f;
        /// <summary>Horizontal distance (m) between the pinned point and the animated foot at which the lock lets go.</summary>
        public float LockMaxDrift = 0.16f;

        struct FootPin { public bool On; public Vector3 Point; public float W; }
        FootPin pinL, pinR;

        Animator anim;
        Transform spine;
        Transform[] legL, legR; // upper leg, lower leg, foot
        float thighL, shinL, thighR, shinR;
        float pelvisOffset, lean, lastYaw, lookW, footW = 1, standRaise, standWant;
        bool plantedL, plantedR;
        Vector3 lookPoint;
        static readonly int SpeedId = Animator.StringToHash("Speed"), CombatId = Animator.StringToHash("Combat"), CrouchId = Animator.StringToHash("Crouch");

        void Awake()
        {
            anim = GetComponent<Animator>();
            lastYaw = transform.eulerAngles.y;
            if (anim != null && anim.isHuman)
            {
                Transform B(HumanBodyBones b) => anim.GetBoneTransform(b);
                legL = new[] { B(HumanBodyBones.LeftUpperLeg), B(HumanBodyBones.LeftLowerLeg), B(HumanBodyBones.LeftFoot) };
                legR = new[] { B(HumanBodyBones.RightUpperLeg), B(HumanBodyBones.RightLowerLeg), B(HumanBodyBones.RightFoot) };
                if (legL.Any(t => t == null) || legR.Any(t => t == null)) legL = legR = null;
                else
                {
                    thighL = Vector3.Distance(legL[0].position, legL[1].position); shinL = Vector3.Distance(legL[1].position, legL[2].position);
                    thighR = Vector3.Distance(legR[0].position, legR[1].position); shinR = Vector3.Distance(legR[1].position, legR[2].position);
                }
            }
        }

        void OnAnimatorIK(int layerIndex)
        {
            if (layerIndex != 0 || anim == null || !anim.isHuman) return;
            var dt = Mathf.Max(Time.deltaTime, 0.0001f);
            var grounded = IsGrounded == null || IsGrounded();
            footW = Mathf.MoveTowards(footW, FootIK && grounded ? 1 : 0, dt * 6);

            // ----- feet
            float dl = 0, dr = 0, sinkL = 0, sinkR = 0;
            plantedL = plantedR = false;
            if (footW > 0.001f)
            {
                dl = SolveFoot(AvatarIKGoal.LeftFoot, ref pinL, dt, out sinkL, out plantedL);
                dr = SolveFoot(AvatarIKGoal.RightFoot, ref pinR, dt, out sinkR, out plantedR);
            }
            else pinL = pinR = default;
            // Lower the pelvis to the lower foot (and by the amount the planted foot was settled onto the ground) so
            // the legs bend instead of stretching.
            var want = (Mathf.Min(0, Mathf.Min(dl, dr)) - Mathf.Max(sinkL, sinkR)) * footW;
            pelvisOffset = Mathf.Lerp(pelvisOffset, want, 1 - Mathf.Exp(-12 * dt));
            // Standing knees: only while both feet are pinned by the IK (else raising the body would lift them).
            var canStand = footW > 0.99f && plantedL && plantedR;
            standRaise = Mathf.MoveTowards(standRaise, canStand ? standWant : 0f, dt * (canStand && standWant > standRaise ? 0.08f : 0.25f));
            anim.bodyPosition += Vector3.up * (pelvisOffset + standRaise);

            // ----- head look
            var wantLook = LookTarget.HasValue ? 1f : 0f;
            if (LookTarget.HasValue)
            {
                var to = LookTarget.Value - anim.GetBoneTransform(HumanBodyBones.Head).position;
                // Only look within a comfortable cone in front.
                if (Vector3.Dot(to.normalized, transform.forward) < 0.15f) wantLook = 0;
                lookPoint = Vector3.Lerp(lookPoint == Vector3.zero ? LookTarget.Value : lookPoint, LookTarget.Value, 1 - Mathf.Exp(-8 * dt));
            }
            lookW = Mathf.MoveTowards(lookW, wantLook, dt * 2.5f);
            if (lookW > 0.001f)
            {
                anim.SetLookAtWeight(lookW, 0.15f, 0.65f, 1f, 0.6f);
                anim.SetLookAtPosition(lookPoint);
            }
        }

        /// <summary>
        /// Re-base one foot's animated lift onto the ground under it. Returns the ground height under the foot relative
        /// to the character's ground plane (+ step up, − step down).
        /// </summary>
        float SolveFoot(AvatarIKGoal goal, ref FootPin pin, float dt, out float sink, out bool planted)
        {
            sink = 0;
            planted = false;
            var foot = anim.GetIKPosition(goal);
            var rootY = transform.position.y;
            var lift = foot.y - rootY;
            // Settle near-ground feet onto the ground: the retargeted clips hover the planted foot a few cm (it read as
            // gliding). Sole heights under FloatBand are eased towards 0; swing heights above it are untouched.
            var bottom = goal == AvatarIKGoal.LeftFoot ? anim.leftFeetBottomHeight : anim.rightFeetBottomHeight;
            var sole = lift - bottom;
            if (sole > 0 && sole < FloatBand)
            {
                var settled = sole * (sole / FloatBand);
                sink = sole - settled;
                lift -= sink;
            }
            if (!Physics.Raycast(new Vector3(foot.x, rootY + 0.6f, foot.z), Vector3.down, out var hit, 1.3f, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore))
            {
                sink = 0;
                pin = default;
                return 0;
            }
            var groundDelta = hit.point.y - rootY;
            if (Mathf.Abs(groundDelta) > 0.45f) { sink = 0; pin = default; return 0; }
            var target = new Vector3(foot.x, hit.point.y + lift, foot.z);
            // Foot lock: pinned where it touched down while the sole stays on the ground; released when it lifts or the
            // animation has moved on too far (turning in place, a big stride mismatch, a teleport), eased in and out.
            if (FootLock && lift - bottom < LockContact)
            {
                if (!pin.On) { pin.On = true; pin.Point = target; }
                else if (new Vector2(target.x - pin.Point.x, target.z - pin.Point.z).magnitude > LockMaxDrift) pin.On = false;
            }
            else pin.On = false;
            pin.W = Mathf.MoveTowards(pin.W, pin.On ? 1f : 0f, dt * (pin.On ? 25f : 12f));
            if (pin.W > 0.001f)
            {
                target.x = Mathf.Lerp(target.x, pin.Point.x, pin.W);
                target.z = Mathf.Lerp(target.z, pin.Point.z, pin.W);
            }
            anim.SetIKPositionWeight(goal, footW);
            anim.SetIKPosition(goal, target);
            planted = lift - bottom < 0.03f;
            // Align planted feet to the surface normal; swinging feet keep their animated rotation.
            var stance = Mathf.Clamp01(1 - (lift - 0.12f) / 0.2f);
            anim.SetIKRotationWeight(goal, footW * stance);
            anim.SetIKRotation(goal, Quaternion.FromToRotation(Vector3.up, hit.normal) * anim.GetIKRotation(goal));
            return groundDelta;
        }

        /// <summary>
        /// Pelvis raise (applied next frame in the IK pass) that brings the straighter leg to <see cref="StandKneeBend"/>,
        /// from the final pose: standing still (Speed &lt; 0.3), out of combat, grounded.
        /// </summary>
        void UpdateStandRaise()
        {
            if (legL == null || StandKneeBend <= 0) { standWant = 0; return; }
            var standing = anim.GetFloat(SpeedId) < 0.3f && !anim.GetBool(CombatId) && !anim.GetBool(CrouchId) && (IsGrounded == null || IsGrounded());
            if (!standing) { standWant = 0; return; }
            float Need(Transform[] leg, float a, float b)
            {
                var d = Vector3.Distance(leg[0].position, leg[2].position);
                var interior = (180f - StandKneeBend) * Mathf.Deg2Rad;
                var dt = Mathf.Sqrt(a * a + b * b - 2 * a * b * Mathf.Cos(interior));
                return dt - d;
            }
            var need = Mathf.Min(Need(legL, thighL, shinL), Need(legR, thighR, shinR));
            standWant = Mathf.Clamp(standRaise + need, 0f, MaxStandRaise);
        }

        void LateUpdate()
        {
            if (anim == null || !anim.isHuman) return;
            UpdateStandRaise();
            var dt = Mathf.Max(Time.deltaTime, 0.0001f);
            var yaw = transform.eulerAngles.y;
            var turnRate = Mathf.DeltaAngle(lastYaw, yaw) / dt; // deg/s
            lastYaw = yaw;
            var speed = anim.GetFloat(SpeedId);
            var want = Mathf.Clamp(-turnRate * speed * 0.012f, -MaxLeanDeg, MaxLeanDeg);
            lean = Mathf.Lerp(lean, want, 1 - Mathf.Exp(-6 * dt));
            if (Mathf.Abs(lean) < 0.05f) return;
            if (spine == null) spine = anim.GetBoneTransform(HumanBodyBones.Spine);
            if (spine != null) spine.rotation = Quaternion.AngleAxis(lean, transform.forward) * spine.rotation;
        }
    }
}
