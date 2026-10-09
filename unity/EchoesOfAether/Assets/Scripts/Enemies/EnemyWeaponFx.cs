using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Enemy weapon models (blender/weapons → Resources/Weapons), attached at spawn to the robot's bones in its rest pose:
    /// <list type="bullet">
    /// <item>Drone: twin blaster under the chin turret; shots alternate barrels with a 3D muzzle flash and barrel recoil.</item>
    /// <item>Sentinel / Warden: heavy forearm blade on forearm_R with a heated cutting edge and a swing trail.</item>
    /// <item>Guardian: arm cannon on forearm_L (the chest laser now fires from its muzzle) and a folding arm blade on
    /// forearm_R that swings out of its sheath for the sweep and folds back afterwards.</item>
    /// </list>
    /// Glow faces use the robot's own glow material, so they brighten with attack telegraphs and take the variant colour.
    /// Purely visual: damage, ranges and timings stay in the enemy classes.
    /// </summary>
    public sealed class EnemyWeaponFx : MonoBehaviour
    {
        public enum Kind { Drone, Sentinel, Warden, Guardian }

        Kind kind;
        RobotRig rig;
        Transform[] muzzles = new Transform[0];
        Transform[] barrels = new Transform[0];
        Vector3[] barrelRest = new Vector3[0];
        float[] recoil = new float[0];
        int nextMuzzle;
        Transform blade, bladeTip, bladePivot;
        float deploy, deployTarget;
        bool swing;
        WeaponTrail trail;
        Color trailColor;

        /// <summary>Guardian cannon muzzle (laser origin), or null.</summary>
        public Transform CannonMuzzle { get; private set; }

        public static EnemyWeaponFx Attach(Enemy owner, RobotRig rig, Kind kind)
        {
            if (owner == null || rig == null) return null;
            var fx = owner.gameObject.AddComponent<EnemyWeaponFx>();
            fx.kind = kind;
            fx.rig = rig;
            try { fx.Build(); }
            catch (System.Exception e) { Debug.LogWarning("[weapons] enemy weapon attach failed: " + e.Message); }
            rig.RefreshRenderers();
            return fx;
        }

        void Build()
        {
            int layer = rig.gameObject.layer;
            switch (kind)
            {
                case Kind.Drone:
                {
                    var body = rig.DroneBody;
                    if (body == null) return;
                    var b = WeaponLibrary.Spawn("drone_blaster", body, layer, out _, rig.GlowMat, true, null, false);
                    if (b == null) return;
                    b.transform.localPosition = new Vector3(0f, -0.238f, 0.215f);
                    b.transform.localRotation = Quaternion.identity;
                    muzzles = new[] { WeaponLibrary.FindDeep(b.transform, "muzzle_0"), WeaponLibrary.FindDeep(b.transform, "muzzle_1") };
                    // the barrels recoil: we move the whole blaster back a touch per shot (single mesh)
                    barrels = new[] { b.transform };
                    barrelRest = new[] { b.transform.localPosition };
                    recoil = new float[1];
                    break;
                }
                case Kind.Sentinel:
                case Kind.Warden:
                {
                    var fore = rig.Bone("forearm_R");
                    var hand = rig.Bone("hand_R");
                    if (fore == null || hand == null) return;
                    var b = WeaponLibrary.Spawn("sentinel_blade", fore, layer, out _, rig.GlowMat, true, null, false);
                    if (b == null) return;
                    float k = kind == Kind.Warden ? 1.2f : 1f;
                    Vector3 dir = (hand.position - fore.position).normalized;
                    Vector3 outward = rig.transform.right;      // robot's right side (+X) for the right arm
                    Vector3 fwd = Vector3.ProjectOnPlane(rig.transform.forward, dir).normalized;
                    // edge (-y) faces the front of the robot: the leading side of its horizontal sweep
                    var rot = Quaternion.LookRotation(dir, -fwd);
                    float halfArm = 0.125f * k;
                    b.transform.SetPositionAndRotation(fore.position + dir * 0.07f * k + outward * (halfArm + 0.028f * k), rot);
                    b.transform.localScale = new Vector3(-k, k, k) / Mathf.Max(1e-4f, fore.lossyScale.x);   // mirrored: detail side faces out
                    blade = b.transform;
                    bladeTip = WeaponLibrary.FindDeep(b.transform, "tip");
                    trailColor = kind == Kind.Warden ? CombatMath.Hex(0xff3b30) : CombatMath.Hex(0xff6a3a);
                    trail = new WeaponTrail("SentinelBladeTrail", trailColor, 3f) { Fade = 0.14f, FullSpeed = 6f };
                    break;
                }
                case Kind.Guardian:
                {
                    var foreL = rig.Bone("forearm_L");
                    var handL = rig.Bone("hand_L");
                    var foreR = rig.Bone("forearm_R");
                    var handR = rig.Bone("hand_R");
                    if (foreL != null && handL != null)
                    {
                        var c = WeaponLibrary.Spawn("guardian_weapons", foreL, layer, out _, rig.GlowMat, true, "guardian_cannon", false);
                        if (c != null)
                        {
                            Vector3 dir = (handL.position - foreL.position).normalized;
                            Vector3 outward = Vector3.ProjectOnPlane(-rig.transform.right, dir).normalized;
                            c.transform.SetPositionAndRotation(foreL.position + dir * 0.12f + outward * 0.56f, Quaternion.LookRotation(dir, outward));
                            c.transform.localScale = Vector3.one / Mathf.Max(1e-4f, foreL.lossyScale.x);
                            CannonMuzzle = WeaponLibrary.FindDeep(c.transform, "muzzle");
                        }
                    }
                    if (foreR != null && handR != null)
                    {
                        Vector3 dir = (handR.position - foreR.position).normalized;
                        Vector3 outward = Vector3.ProjectOnPlane(rig.transform.right, dir).normalized;
                        Vector3 fwd = Vector3.ProjectOnPlane(rig.transform.forward, dir).normalized;
                        var rot = Quaternion.LookRotation(dir, -fwd);
                        var hinge = handR.position - dir * 0.05f + outward * 0.56f;
                        var m = WeaponLibrary.Spawn("guardian_weapons", foreR, layer, out _, rig.GlowMat, true, "guardian_blade_mount", false);
                        if (m != null)
                        {
                            m.transform.SetPositionAndRotation(hinge, rot);
                            m.transform.localScale = new Vector3(-1f, 1f, 1f) / Mathf.Max(1e-4f, foreR.lossyScale.x);
                        }
                        var pivot = new GameObject("BladeHinge").transform;
                        pivot.SetParent(foreR, false);
                        pivot.SetPositionAndRotation(hinge, rot);
                        pivot.localScale = new Vector3(-1f, 1f, 1f) / Mathf.Max(1e-4f, foreR.lossyScale.x);
                        var b = WeaponLibrary.Spawn("guardian_weapons", pivot, layer, out _, rig.GlowMat, true, "guardian_blade", false);
                        if (b != null)
                        {
                            b.transform.localPosition = Vector3.zero;
                            b.transform.localRotation = Quaternion.identity;
                            b.transform.localScale = Vector3.one;
                            bladePivot = pivot;
                            blade = b.transform;
                            bladeTip = WeaponLibrary.FindDeep(b.transform, "tip");
                            trailColor = CombatMath.Hex(0x5fd8ff);
                            trail = new WeaponTrail("GuardianBladeTrail", trailColor, 3f) { Fade = 0.2f, FullSpeed = 8f };
                            ApplyDeploy();
                        }
                    }
                    break;
                }
            }
        }

        // ------------------------------------------------------------------ API

        /// <summary>Next muzzle (alternating barrels) for a shot along `dir`: flash + recoil. Returns the muzzle position.</summary>
        public Vector3 Fire(Vector3 fallback, Vector3 dir, Color color)
        {
            if (muzzles.Length == 0 || muzzles[0] == null) { WeaponFx.Muzzle(fallback, dir, color, 0.2f); return fallback; }
            var m = muzzles[nextMuzzle % muzzles.Length];
            nextMuzzle++;
            var p = m != null ? m.position : fallback;
            WeaponFx.Muzzle(p, dir, color, 0.22f);
            if (recoil.Length > 0) recoil[0] = 1f;
            return p;
        }

        /// <summary>Guardian sweep: swing the folded arm blade out (true) or fold it back (false).</summary>
        public void Deploy(bool on)
        {
            if (bladePivot == null) return;
            if (on && deployTarget < 0.5f) G.Audio?.Play("blade_deploy", bladePivot.position, 0.9f);
            deployTarget = on ? 1f : 0f;
        }

        /// <summary>Melee active window: the blade leaves a trail.</summary>
        public void SetSwing(bool on) => swing = on;

        public void Hide()
        {
            swing = false;
            trail?.Clear();
        }

        // ------------------------------------------------------------------ update

        void ApplyDeploy()
        {
            if (bladePivot == null || blade == null) return;
            // folded: pointing back along the forearm, angled away from it; deployed: past the fist
            float e = Mathf.SmoothStep(0f, 1f, deploy);
            blade.localRotation = Quaternion.Euler(Mathf.Lerp(-168f, 0f, e), 0f, 0f);
        }

        void LateUpdate()
        {
            float dt = Time.deltaTime;
            if (dt <= 0f) return;
            for (int i = 0; i < barrels.Length; i++)
            {
                if (barrels[i] == null) continue;
                recoil[i] = Mathf.MoveTowards(recoil[i], 0f, dt / 0.12f);
                barrels[i].localPosition = barrelRest[i] - Vector3.forward * 0.045f * recoil[i] * recoil[i];
            }
            if (bladePivot != null && !Mathf.Approximately(deploy, deployTarget))
            {
                deploy = Mathf.MoveTowards(deploy, deployTarget, dt / (deployTarget > deploy ? 0.32f : 0.55f));
                ApplyDeploy();
            }
            if (trail != null && blade != null && bladeTip != null)
            {
                Vector3 tip = bladeTip.position;
                Vector3 baseP = Vector3.Lerp(blade.position, tip, 0.35f);
                trail.Tick(dt, swing && (bladePivot == null || deploy > 0.8f), baseP, tip);
            }
        }

        void OnDestroy() => trail?.Destroy();
    }
}
