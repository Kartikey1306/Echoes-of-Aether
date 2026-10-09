using System;
using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Heroic standing posture on top of the motion-capture idle. The CMU idles are real people shifting weight —
    /// knees bent inward, hips swung, shoulders slumped, head tilted — which reads as a "bent" character on a pedestal.
    /// This blends the humanoid muscles of the torso, neck, head and (optionally) legs towards an upright stance taken
    /// from the character's own rest pose (straight legs, natural spine curve), adds a slow breathing motion, and leaves
    /// arms, hands and fingers to the animation.
    ///
    /// Menu / designer: full body at weight 1. Gameplay: upper body only (foot IK owns the legs), faded in while the
    /// hero stands still and out as soon as they move, attack or react.
    ///
    /// Posture guard (<see cref="Guard"/>, on in locomotion and the combat stance, off during actions): measures the final
    /// pose every frame and keeps the slowly averaged torso lean, neck-against-torso angle and gaze inside natural bands
    /// for the current speed (standing upright, under 10° at a run, ~14° at a sprint, neck nearly in line with the torso,
    /// gaze level). Only the averaged excess is removed, so the stride's own sway stays; clips already inside the bands
    /// (Mixamo) are left untouched.
    /// </summary>
    [DefaultExecutionOrder(-100)] // before HumanoidPolish (lean), TwistBones and CorrectiveShapes read the final pose
    public sealed class HeroStance : MonoBehaviour
    {
        /// <summary>Target blend weight (0..1); WeightFn, when set, overrides it every frame.</summary>
        public float Weight = 1f;
        public Func<float> WeightFn;
        /// <summary>Torso, neck and head only (gameplay); false also straightens the legs (menu stage).</summary>
        public bool UpperBodyOnly;
        /// <summary>Breathing amplitude in muscle units (chest rise).</summary>
        public float Breath = 0.025f;

        Animator anim;
        HumanPoseHandler handler;
        HumanPose pose;
        float[] rest;
        float w;
        int[] upper, legs;
        int chestFB, upperChestFB, neckNod, headNod;

        /// <summary>Keep locomotion / combat-stance posture inside natural bands (see class summary).</summary>
        public bool Guard = true;
        Transform hips, spine, chest, upperChest, neck, head;
        Vector3 gazeLocal;
        float guardW, leanAvg, neckAvg, gazeAvg;
        bool guardInit;
        static readonly int SpeedId = Animator.StringToHash("Speed"), CombatId = Animator.StringToHash("Combat"),
            LocoId = Animator.StringToHash("Locomotion"), CombatLocoId = Animator.StringToHash("CombatLocomotion"), EmptyId = Animator.StringToHash("Empty");
        /// <summary>Last frame's guard corrections (degrees; diagnostics).</summary>
        public float TorsoFix { get; private set; }
        public float NeckFix { get; private set; }
        public float HeadFix { get; private set; }

        static readonly string[] UpperMuscles =
        {
            "Spine Front-Back", "Spine Left-Right", "Spine Twist Left-Right",
            "Chest Front-Back", "Chest Left-Right", "Chest Twist Left-Right",
            "UpperChest Front-Back", "UpperChest Left-Right", "UpperChest Twist Left-Right",
            "Neck Nod Down-Up", "Neck Tilt Left-Right", "Neck Turn Left-Right",
            "Head Nod Down-Up", "Head Tilt Left-Right", "Head Turn Left-Right",
            // No clavicles (Shoulder Down-Up / Front-Back): their rest is the rig's A-pose, raised for arms held out. Since
            // the animation avatar is built from the true rest pose (Anim_*.fbx "_rest" take), the clips' clavicles arrive
            // as captured, and pulling them to that rest swung both arms 15-23 deg across the body, hands clasped in front
            // (EOA.EditorTools.ArmProbe). The arms hang from the animation's clavicles.
            "Jaw Close", "Jaw Left-Right", // mouth at rest (the mocap jaw hung open: visible teeth line)
        };

        static readonly string[] LegMuscles =
        {
            "Left Upper Leg Front-Back", "Left Upper Leg In-Out", "Left Upper Leg Twist In-Out",
            "Left Lower Leg Stretch", "Left Lower Leg Twist In-Out", "Left Foot Up-Down", "Left Foot Twist In-Out", "Left Toes Up-Down",
            "Right Upper Leg Front-Back", "Right Upper Leg In-Out", "Right Upper Leg Twist In-Out",
            "Right Lower Leg Stretch", "Right Lower Leg Twist In-Out", "Right Foot Up-Down", "Right Foot Twist In-Out", "Right Toes Up-Down",
        };

        void Awake()
        {
            anim = GetComponent<Animator>();
            if (anim == null || anim.avatar == null || !anim.avatar.isHuman) { enabled = false; return; }
            handler = new HumanPoseHandler(anim.avatar, anim.transform);
            // The rest (bind) pose before the animator first evaluates: straight legs, the rig's natural spine curve.
            handler.GetHumanPose(ref pose);
            rest = (float[])pose.muscles.Clone();
            upper = Indices(UpperMuscles);
            legs = Indices(LegMuscles);
            chestFB = Index("Chest Front-Back");
            upperChestFB = Index("UpperChest Front-Back");
            neckNod = Index("Neck Nod Down-Up");
            headNod = Index("Head Nod Down-Up");
            // Rest neck leans forward on these rigs: carry it a little higher, head nodded back to a level gaze.
            if (neckNod >= 0) rest[neckNod] += 0.25f;
            if (headNod >= 0) rest[headNod] -= 0.1f;
            // Chest slightly open (confident stance).
            if (upperChestFB >= 0) rest[upperChestFB] -= 0.06f;
            w = WeightFn?.Invoke() ?? Weight;
            hips = anim.GetBoneTransform(HumanBodyBones.Hips);
            spine = anim.GetBoneTransform(HumanBodyBones.Spine);
            chest = anim.GetBoneTransform(HumanBodyBones.Chest);
            upperChest = anim.GetBoneTransform(HumanBodyBones.UpperChest);
            neck = anim.GetBoneTransform(HumanBodyBones.Neck);
            head = anim.GetBoneTransform(HumanBodyBones.Head);
            // Gaze: the head's local direction that faces the character's front in the (level-headed) bind pose.
            if (head != null) gazeLocal = Quaternion.Inverse(head.rotation) * transform.forward;
        }

        static int Index(string muscle) => Array.IndexOf(HumanTrait.MuscleName, muscle);

        static int[] Indices(string[] names)
        {
            var list = new System.Collections.Generic.List<int>(names.Length);
            foreach (var n in names) { var i = Index(n); if (i >= 0) list.Add(i); }
            return list.ToArray();
        }

        void OnDestroy() => handler?.Dispose();

        void LateUpdate()
        {
            if (handler == null) return;
            var target = Mathf.Clamp01(WeightFn?.Invoke() ?? Weight);
            w = Mathf.MoveTowards(w, target, Time.deltaTime * (target > w ? 2.5f : 6f));
            if (w >= 0.001f) Stance();
            if (w < 0.999f) PostureGuard(Time.deltaTime);
        }

        void Stance()
        {
            handler.GetHumanPose(ref pose);
            var m = pose.muscles;
            var breath = Mathf.Sin(Time.time * 1.7f) * Breath;
            foreach (var i in upper)
            {
                var t = rest[i];
                if (i == chestFB || i == upperChestFB) t -= breath;
                m[i] = Mathf.Lerp(m[i], t, w);
            }
            if (!UpperBodyOnly)
                foreach (var i in legs) m[i] = Mathf.Lerp(m[i], rest[i], w);
            // Keep the body exactly where the animation put it (only joint angles change).
            var hp = hips != null ? hips.position : Vector3.zero;
            handler.SetHumanPose(ref pose);
            if (hips != null) hips.position = hp;
        }

        // ------------------------------------------------------------------ posture guard

        /// <summary>Forward lean allowed for the averaged torso (hips→neck) at a locomotion speed (m/s): upright when
        /// standing (4°), ~6° walking, under 10° running (9°), ~14° sprinting; the combat stance may hunch forward 9° at
        /// most.</summary>
        static float MaxLean(float speed, bool combat)
        {
            var lean = speed < 2.2f ? Mathf.Lerp(4f, 6f, speed / 2.2f)
                : speed < 5.2f ? Mathf.Lerp(6f, 9f, (speed - 2.2f) / 3f)
                : Mathf.Lerp(9f, 14f, (speed - 5.2f) / 2.4f);
            return combat && speed < 1f ? Mathf.Max(lean, 9f) : lean;
        }

        static float Pitch(Vector3 d, Vector3 fwd, Vector3 up) => Mathf.Atan2(Vector3.Dot(d, fwd), Vector3.Dot(d, up)) * Mathf.Rad2Deg;

        void PostureGuard(float dt)
        {
            if (hips == null || neck == null || head == null || spine == null) return;
            var on = Guard;
            if (on && anim.runtimeAnimatorController != null)
            {
                var b = anim.GetCurrentAnimatorStateInfo(0).shortNameHash;
                on = (b == LocoId || b == CombatLocoId) && !anim.IsInTransition(0);
                if (on && anim.layerCount > 1)
                    on = anim.GetCurrentAnimatorStateInfo(1).shortNameHash == EmptyId && !anim.IsInTransition(1);
            }
            guardW = Mathf.MoveTowards(guardW, on ? 1f : 0f, dt * (on ? 3f : 8f));
            TorsoFix = NeckFix = HeadFix = 0;
            if (guardW < 0.001f) { guardInit = false; return; }

            var up = transform.up;
            var fwd = transform.forward;
            var right = transform.right;
            var lean = Pitch(neck.position - hips.position, fwd, up);
            var neckRel = Pitch(head.position - neck.position, fwd, up) - lean;
            // Averages over ~0.3 s: the stride's own sway passes through, the constant hunch is removed.
            var k = guardInit ? 1f - Mathf.Exp(-dt / 0.3f) : 1f;
            leanAvg = Mathf.Lerp(leanAvg, lean, k);
            neckAvg = Mathf.Lerp(neckAvg, neckRel, k);

            var speed = anim.GetFloat(SpeedId);
            var combat = anim.GetBool(CombatId);
            var torsoFix = (Mathf.Clamp(leanAvg, -4f, MaxLean(speed, combat)) - leanAvg) * guardW;
            // Neck nearly in line with the torso (a little forward is natural; no head poke).
            var neckFix = (Mathf.Clamp(neckAvg, -4f, 6f) - neckAvg) * guardW;
            // Spread the torso correction over the spine so the back bends evenly (+ = forward about the right axis).
            if (Mathf.Abs(torsoFix) > 0.01f)
            {
                var parts = upperChest != null && chest != null ? new[] { (spine, 0.4f), (chest, 0.35f), (upperChest, 0.25f) }
                    : chest != null ? new[] { (spine, 0.5f), (chest, 0.5f) } : new[] { (spine, 1f) };
                foreach (var (bone, share) in parts) bone.rotation = Quaternion.AngleAxis(torsoFix * share, right) * bone.rotation;
            }
            if (Mathf.Abs(neckFix) > 0.01f) neck.rotation = Quaternion.AngleAxis(neckFix, right) * neck.rotation;

            // Gaze: after the fixes, keep the averaged view between 15° down and 5° up.
            var gaze = head.rotation * gazeLocal;
            var gazePitch = Mathf.Asin(Mathf.Clamp(Vector3.Dot(gaze.normalized, up), -1f, 1f)) * Mathf.Rad2Deg;
            gazeAvg = guardInit ? Mathf.Lerp(gazeAvg, gazePitch, k) : gazePitch;
            var headFix = -(Mathf.Clamp(gazeAvg, -15f, 5f) - gazeAvg) * guardW;
            if (Mathf.Abs(headFix) > 0.01f) head.rotation = Quaternion.AngleAxis(headFix, right) * head.rotation;
            guardInit = true;
            TorsoFix = torsoFix; NeckFix = neckFix; HeadFix = headFix;
        }
    }
}
