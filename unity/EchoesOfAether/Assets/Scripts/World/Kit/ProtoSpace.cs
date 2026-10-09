using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Conversion from the prototype's level-design space (three.js: right-handed, metres, yaw in radians)
    /// to Unity (left-handed). The prototype's X axis is mirrored: Unity = (-x, y, z). Rotations are conjugated by
    /// the mirror, so a three.js Euler XYZ (Rx·Ry·Rz) becomes Rx(a)·Ry(-b)·Rz(-c), and a yaw becomes -yaw (degrees).
    /// Zone layouts are authored with these helpers so numbers can be read side by side with the design docs.
    /// </summary>
    public static class ProtoSpace
    {
        /// <summary>
        /// Prototype light intensities (three.js physically based, Lambert divides by π) to URP (no π):
        /// multiply point/spot/directional intensities and hemisphere/ambient colours by this.
        /// </summary>
        public const float LightToUnity = 1f / Mathf.PI;

        public static Vector3 V(float x, float y, float z) => new(-x, y, z);
        public static Vector3 V(Vector3 proto) => new(-proto.x, proto.y, proto.z);

        /// <summary>Prototype yaw (radians) to Unity yaw (degrees, 0 faces +Z).</summary>
        public static float Yaw(float rad) => -rad * Mathf.Rad2Deg;

        public static Quaternion YawQ(float rad) => Quaternion.AngleAxis(-rad * Mathf.Rad2Deg, Vector3.up);

        /// <summary>three.js Euler 'XYZ' (radians) to a Unity rotation.</summary>
        public static Quaternion Rot(float rx, float ry, float rz) =>
            Quaternion.AngleAxis(rx * Mathf.Rad2Deg, Vector3.right) *
            Quaternion.AngleAxis(-ry * Mathf.Rad2Deg, Vector3.up) *
            Quaternion.AngleAxis(-rz * Mathf.Rad2Deg, Vector3.forward);

        /// <summary>three.js Euler 'YXZ' (radians, used for ramps and pitched shots) to a Unity rotation.</summary>
        public static Quaternion RotYXZ(float rx, float ry, float rz) =>
            Quaternion.AngleAxis(-ry * Mathf.Rad2Deg, Vector3.up) *
            Quaternion.AngleAxis(rx * Mathf.Rad2Deg, Vector3.right) *
            Quaternion.AngleAxis(-rz * Mathf.Rad2Deg, Vector3.forward);

        /// <summary>Prototype colour literal (0xRRGGBB, sRGB).</summary>
        public static Color Hex(uint rgb) => new(((rgb >> 16) & 255) / 255f, ((rgb >> 8) & 255) / 255f, (rgb & 255) / 255f, 1f);

        /// <summary>Prototype map rectangle (x, z centre; w, d size) in Unity map space.</summary>
        public static Vector2 MapXZ(float x, float z) => new(-x, z);
    }
}
