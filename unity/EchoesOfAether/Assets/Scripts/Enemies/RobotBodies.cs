using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Procedural robot bodies (port of buildSentinelBody / buildStalkerBody / buildGuardianBody in RobotModel.ts
    /// and the Drone.ts body). Offsets are written in prototype coordinates (left = +X, reference 1.8 m body) and
    /// mirrored/scaled by V(); rotations use prototype Euler radians via RobotAnimator.EulerXYZ.
    /// </summary>
    internal static class RobotBodies
    {
        static Mesh RBox(float w, float h, float d, float r) => FxMesh.RoundedBox(w, h, d, r);

        static void Segment(RobotRig m, string bone, string from, string to, float w, float d, Material mat, float inset = 0.08f, bool cyl = false)
        {
            Vector3 a = m.Joints[from], b = m.Joints[to];
            Vector3 ab = b - a;
            float len = ab.magnitude;
            Vector3 mid = (a + b) * 0.5f;
            Quaternion q = Quaternion.FromToRotation(Vector3.up, ab.normalized);
            float L = Mathf.Max(0.05f, len * (1f - inset * 2f));
            Mesh mesh = cyl ? FxMesh.Cylinder(w / 2f, d / 2f, L, 10) : RBox(w, L, d, Mathf.Min(w, d) * 0.25f);
            m.Attach(bone, mesh, mat, mid, q);
        }

        static void Ball(RobotRig m, string bone, Vector3 at, float r, Material mat) => m.Attach(bone, FxMesh.Sphere(r, 12, 8), mat, at);

        // ------------------------------------------------------------------ Sentinel / Warden

        public static void BuildSentinel(RobotRig m, bool elite)
        {
            var J = m.Joints;
            float s = m.S;
            Vector3 V(float x, float y, float z) => new Vector3(-x * s, y * s, z * s);
            Material Sh = m.ShellMat, Fr = m.FrameMat, Jo = m.JointMat, Gl = m.GlowMat;

            // Pelvis & abdomen
            m.Attach("hips", RBox(0.44f * s, 0.22f * s, 0.3f * s, 0.05f * s), Fr, J["hips"] + V(0, -0.02f, 0));
            m.Attach("spine", FxMesh.Cylinder(0.13f * s, 0.16f * s, 0.24f * s, 10), Jo, J["spine"] + V(0, 0.06f, 0));
            // Chest with core
            m.Attach("chest", RBox(0.62f * s, 0.46f * s, 0.4f * s, 0.08f * s), Sh, J["chest"] + V(0, 0.13f, 0.01f));
            m.Attach("chest", RBox(0.5f * s, 0.18f * s, 0.34f * s, 0.05f * s), Fr, J["chest"] + V(0, -0.06f, 0));
            m.Attach("chest", FxMesh.CylinderZ(0.075f * s, 0.075f * s, 0.05f * s, 16), Gl, J["chest"] + V(0, 0.16f, 0.215f), name: "chest_core");
            // Back vents
            m.Attach("chest", RBox(0.36f * s, 0.3f * s, 0.14f * s, 0.04f * s), Fr, J["chest"] + V(0, 0.16f, -0.24f));
            // Head with visor
            m.Attach("neck", FxMesh.Cylinder(0.06f * s, 0.07f * s, 0.12f * s, 8), Jo, J["neck"] + V(0, 0.05f, 0));
            m.Attach("head", RBox(0.22f * s, 0.24f * s, 0.26f * s, 0.06f * s), Sh, J["headCenter"] + V(0, -0.02f, 0));
            m.Attach("head", RBox(0.18f * s, 0.035f * s, 0.02f * s, 0.01f * s), Gl, J["headCenter"] + V(0, 0, 0.135f), name: "visor");
            // Arms
            for (int side = 0; side < 2; side++)
            {
                string sd = side == 0 ? "L" : "R";
                float sx = side == 0 ? 1f : -1f;
                m.Attach("clavicle_" + sd, RBox(0.3f * s, 0.22f * s, 0.34f * s, 0.07f * s), Sh, J["upperarm_" + sd] + V(sx * 0.04f, 0.08f, 0), RobotAnimator.EulerXYZ(0, 0, sx * -0.25f));
                Ball(m, "upperarm_" + sd, J["upperarm_" + sd], 0.09f * s, Jo);
                Segment(m, "upperarm_" + sd, "upperarm_" + sd, "forearm_" + sd, 0.13f * s, 0.13f * s, Fr, 0.1f, true);
                Ball(m, "forearm_" + sd, J["forearm_" + sd], 0.08f * s, Jo);
                Segment(m, "forearm_" + sd, "forearm_" + sd, "hand_" + sd, 0.2f * s, 0.2f * s, Sh, 0.04f);
                m.Attach("hand_" + sd, RBox(0.14f * s, 0.16f * s, 0.14f * s, 0.03f * s), Fr, Vector3.Lerp(J["hand_" + sd], J["handEnd_" + sd], 0.4f));
                // Glowing seam on forearms (telegraph)
                Vector3 fa = Vector3.Lerp(J["forearm_" + sd], J["hand_" + sd], 0.5f) + V(sx * 0.1f, 0, 0);
                m.Attach("forearm_" + sd, RBox(0.03f * s, 0.16f * s, 0.21f * s, 0.01f * s), Gl, fa);
            }
            // Blade on the right forearm
            m.Attach("forearm_R", RBox(0.03f * s, 0.6f * s, 0.1f * s, 0.01f * s), Gl, J["hand_R"] + V(-0.05f, -0.18f, 0.06f), RobotAnimator.EulerXYZ(0.15f, 0, 0), name: "blade");
            // Legs
            for (int side = 0; side < 2; side++)
            {
                string sd = side == 0 ? "L" : "R";
                Ball(m, "thigh_" + sd, J["thigh_" + sd], 0.1f * s, Jo);
                Segment(m, "thigh_" + sd, "thigh_" + sd, "shin_" + sd, 0.17f * s, 0.19f * s, Fr, 0.08f);
                m.Attach("shin_" + sd, RBox(0.16f * s, 0.16f * s, 0.2f * s, 0.05f * s), Sh, J["shin_" + sd] + V(0, 0.02f, 0.06f));
                Segment(m, "shin_" + sd, "shin_" + sd, "foot_" + sd, 0.16f * s, 0.18f * s, Sh, 0.1f);
                m.Attach("foot_" + sd, RBox(0.16f * s, 0.1f * s, 0.32f * s, 0.03f * s), Fr, J["foot_" + sd] + V(0, -0.04f, 0.08f));
            }
            if (elite)
            {
                // Warden: crest, extra plating and a shield emitter on the left arm.
                m.Attach("head", RBox(0.05f * s, 0.12f * s, 0.3f * s, 0.02f * s), Gl, J["headCenter"] + V(0, 0.15f, -0.02f), name: "crest");
                m.Attach("chest", RBox(0.7f * s, 0.12f * s, 0.44f * s, 0.04f * s), Sh, J["chest"] + V(0, 0.38f, 0));
                m.Attach("forearm_L", RBox(0.06f * s, 0.5f * s, 0.4f * s, 0.03f * s), Sh, Vector3.Lerp(J["forearm_L"], J["hand_L"], 0.5f) + V(0.13f, 0, 0), name: "shield_emitter");
            }
        }

        // ------------------------------------------------------------------ Stalker

        public static void BuildStalker(RobotRig m)
        {
            var J = m.Joints;
            float s = m.S;
            Vector3 V(float x, float y, float z) => new Vector3(-x * s, y * s, z * s);
            Material Sh = m.ShellMat, Fr = m.FrameMat, Jo = m.JointMat, Gl = m.GlowMat;

            m.Attach("hips", RBox(0.3f * s, 0.16f * s, 0.22f * s, 0.05f * s), Fr, J["hips"]);
            m.Attach("spine", FxMesh.Cylinder(0.07f * s, 0.1f * s, 0.26f * s, 8), Jo, J["spine"] + V(0, 0.08f, 0));
            m.Attach("chest", RBox(0.42f * s, 0.38f * s, 0.26f * s, 0.1f * s), Sh, J["chest"] + V(0, 0.12f, 0));
            m.Attach("chest", FxMesh.Sphere(0.06f * s, 12, 8), Gl, J["chest"] + V(0, 0.14f, 0.13f), name: "chest_core");
            m.Attach("head", FxMesh.ConeZ(0.11f * s, 0.34f * s, 6), Sh, J["headCenter"] + V(0, 0, 0.04f));
            m.Attach("head", RBox(0.16f * s, 0.025f * s, 0.02f * s, 0.01f * s), Gl, J["headCenter"] + V(0, 0.01f, 0.12f), name: "visor");
            for (int side = 0; side < 2; side++)
            {
                string sd = side == 0 ? "L" : "R";
                float sx = side == 0 ? 1f : -1f;
                m.Attach("clavicle_" + sd, RBox(0.16f * s, 0.1f * s, 0.2f * s, 0.04f * s), Sh, J["upperarm_" + sd] + V(sx * 0.02f, 0.05f, 0));
                Segment(m, "upperarm_" + sd, "upperarm_" + sd, "forearm_" + sd, 0.08f * s, 0.08f * s, Fr, 0.08f, true);
                Segment(m, "forearm_" + sd, "forearm_" + sd, "hand_" + sd, 0.1f * s, 0.1f * s, Sh, 0.06f);
                // Long blade extending past the hand
                Vector3 a = J["hand_" + sd], b = J["handEnd_" + sd];
                Vector3 dir = (b - a).normalized;
                m.Attach("hand_" + sd, RBox(0.025f * s, 0.75f * s, 0.07f * s, 0.01f * s), Gl, a + dir * (0.42f * s), Quaternion.FromToRotation(Vector3.up, dir), name: "blade_" + sd);
                Segment(m, "thigh_" + sd, "thigh_" + sd, "shin_" + sd, 0.11f * s, 0.12f * s, Fr, 0.06f);
                Segment(m, "shin_" + sd, "shin_" + sd, "foot_" + sd, 0.09f * s, 0.11f * s, Sh, 0.06f);
                m.Attach("foot_" + sd, RBox(0.1f * s, 0.06f * s, 0.26f * s, 0.02f * s), Fr, J["foot_" + sd] + V(0, -0.05f, 0.08f));
            }
        }

        // ------------------------------------------------------------------ Guardian

        public static void BuildGuardian(RobotRig m)
        {
            var J = m.Joints;
            float s = m.S;
            Vector3 V(float x, float y, float z) => new Vector3(-x * s, y * s, z * s);
            Material Sh = m.ShellMat, Fr = m.FrameMat, Jo = m.JointMat, Gl = m.GlowMat;

            m.Attach("hips", RBox(0.6f * s, 0.3f * s, 0.4f * s, 0.08f * s), Fr, J["hips"]);
            m.Attach("spine", FxMesh.Cylinder(0.17f * s, 0.22f * s, 0.3f * s, 10), Jo, J["spine"] + V(0, 0.08f, 0));
            m.Attach("chest", RBox(0.9f * s, 0.6f * s, 0.56f * s, 0.12f * s), Sh, J["chest"] + V(0, 0.14f, -0.04f));
            m.Core = m.Attach("chest", FxMesh.Sphere(0.13f * s, 16, 12), m.CoreMat, J["chest"] + V(0, 0.14f, 0.26f), name: "core");
            for (int i = 0; i < 2; i++)
            {
                float sx = i == 0 ? 1f : -1f;
                m.Plates.Add(m.Attach("chest", RBox(0.22f * s, 0.4f * s, 0.08f * s, 0.03f * s), Sh, J["chest"] + V(sx * 0.12f, 0.14f, 0.3f), name: i == 0 ? "plate_L" : "plate_R"));
            }
            m.Attach("chest", RBox(0.5f * s, 0.4f * s, 0.24f * s, 0.06f * s), Fr, J["chest"] + V(0, 0.2f, -0.36f));
            for (int i = 0; i < 3; i++) m.Attach("chest", FxMesh.Cylinder(0.04f * s, 0.04f * s, 0.5f * s, 8), Gl, J["chest"] + V(-0.15f + i * 0.15f, 0.45f, -0.42f), name: "exhaust_" + i);
            m.Attach("neck", FxMesh.Cylinder(0.1f * s, 0.12f * s, 0.14f * s, 10), Jo, J["neck"] + V(0, 0.05f, 0));
            m.Attach("head", RBox(0.26f * s, 0.2f * s, 0.3f * s, 0.07f * s), Sh, J["headCenter"] + V(0, -0.04f, 0.02f));
            m.Attach("head", RBox(0.2f * s, 0.03f * s, 0.02f * s, 0.01f * s), Gl, J["headCenter"] + V(0, -0.03f, 0.18f), name: "visor");
            for (int side = 0; side < 2; side++)
            {
                string sd = side == 0 ? "L" : "R";
                float sx = side == 0 ? 1f : -1f;
                m.Attach("clavicle_" + sd, RBox(0.42f * s, 0.32f * s, 0.46f * s, 0.1f * s), Sh, J["upperarm_" + sd] + V(sx * 0.08f, 0.12f, 0), RobotAnimator.EulerXYZ(0, 0, sx * -0.3f));
                m.Attach("clavicle_" + sd, RBox(0.06f * s, 0.25f * s, 0.4f * s, 0.02f * s), Gl, J["upperarm_" + sd] + V(sx * 0.3f, 0.12f, 0));
                Segment(m, "upperarm_" + sd, "upperarm_" + sd, "forearm_" + sd, 0.2f * s, 0.2f * s, Fr, 0.08f, true);
                Segment(m, "forearm_" + sd, "forearm_" + sd, "hand_" + sd, 0.32f * s, 0.32f * s, Sh, 0.02f);
                m.Attach("hand_" + sd, RBox(0.3f * s, 0.26f * s, 0.3f * s, 0.06f * s), Fr, Vector3.Lerp(J["hand_" + sd], J["handEnd_" + sd], 0.35f));
                m.Attach("forearm_" + sd, RBox(0.04f * s, 0.22f * s, 0.33f * s, 0.01f * s), Gl, Vector3.Lerp(J["forearm_" + sd], J["hand_" + sd], 0.5f) + V(sx * 0.165f, 0, 0));
                Segment(m, "thigh_" + sd, "thigh_" + sd, "shin_" + sd, 0.26f * s, 0.28f * s, Fr, 0.06f);
                Segment(m, "shin_" + sd, "shin_" + sd, "foot_" + sd, 0.26f * s, 0.3f * s, Sh, 0.06f);
                m.Attach("shin_" + sd, RBox(0.24f * s, 0.24f * s, 0.26f * s, 0.06f * s), Sh, J["shin_" + sd] + V(0, 0.02f, 0.09f));
                m.Attach("foot_" + sd, RBox(0.28f * s, 0.14f * s, 0.46f * s, 0.04f * s), Fr, J["foot_" + sd] + V(0, -0.06f, 0.1f));
            }
        }

        // ------------------------------------------------------------------ Drone

        public static void BuildDrone(RobotRig m)
        {
            // Drone materials are slightly shinier than the bipeds'.
            m.ShellMat.SetFloat("_Metallic", 0.8f);
            m.ShellMat.SetFloat("_Smoothness", 0.65f);
            m.FrameMat.SetFloat("_Metallic", 0.85f);
            m.FrameMat.SetFloat("_Smoothness", 0.6f);

            var body = new GameObject("body").transform;
            body.gameObject.layer = m.gameObject.layer;
            body.SetParent(m.transform, false);
            m.DroneBody = body;
            Quaternion id = Quaternion.identity;
            m.AttachTo(body, FxMesh.Sphere(0.42f, 20, 12), m.ShellMat, Vector3.zero, id, new Vector3(1f, 0.62f, 1.1f), "shell");
            m.AttachTo(body, FxMesh.TorusFlat(0.58f, 0.06f, 8, 32), m.FrameMat, Vector3.zero, id, Vector3.one, "ring");
            m.AttachTo(body, FxMesh.Sphere(0.13f, 16, 10), m.GlowMat, new Vector3(0, 0.02f, 0.42f), id, Vector3.one, "eye");
            m.AttachTo(body, FxMesh.Torus(0.16f, 0.03f, 6, 20), m.FrameMat, new Vector3(0, 0.02f, 0.43f), id, Vector3.one, "visor");
            m.AttachTo(body, FxMesh.CylinderZ(0.045f, 0.055f, 0.42f, 8), m.FrameMat, new Vector3(0, -0.2f, 0.32f), id, Vector3.one, "gun");
            m.AttachTo(body, FxMesh.DiscDown(0.16f, 16), m.GlowMat, new Vector3(0, -0.27f, 0), id, Vector3.one, "under");
            for (int i = 0; i < 4; i++)
            {
                float a = i / 4f * Mathf.PI * 2f + Mathf.PI / 4f;
                // Prototype positions mirrored on X; the arm's long axis points away from the centre.
                Vector3 radial = new Vector3(-Mathf.Sin(a), 0f, Mathf.Cos(a));
                Quaternion yaw = Quaternion.AngleAxis(-a * Mathf.Rad2Deg, Vector3.up);
                m.AttachTo(body, FxMesh.Box(0.08f, 0.05f, 0.5f), m.FrameMat, radial * 0.55f + Vector3.up * 0.05f, yaw, Vector3.one, "arm_" + i);
                m.Rotors.Add(m.AttachTo(body, FxMesh.Cylinder(0.22f, 0.22f, 0.02f, 16), m.RotorMat, radial * 0.82f + Vector3.up * 0.1f, id, Vector3.one, "rotor_" + i));
            }
        }
    }
}
