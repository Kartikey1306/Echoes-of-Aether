using System.Collections.Generic;
using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Pure combat / steering math (no scene access) shared by enemies, heroes, CombatSystem and tests.
    /// Angles are radians unless the name says Deg. Yaw follows Unity: 0 = +Z, positive turns toward +X
    /// (clockwise seen from above); direction of a yaw = (sin yaw, 0, cos yaw).
    /// Ported from the prototype's MathUtil.ts / Combat.ts.
    /// </summary>
    public static class CombatMath
    {
        public const float TAU = Mathf.PI * 2f;

        /// <summary>Wrap an angle to [-PI, PI).</summary>
        public static float WrapAngle(float a)
        {
            a = (a + Mathf.PI) % TAU;
            if (a < 0) a += TAU;
            return a - Mathf.PI;
        }

        /// <summary>Frame-rate independent exponential smoothing (prototype `damp`).</summary>
        public static float Damp(float a, float b, float rate, float dt) => a + (b - a) * (1f - Mathf.Exp(-rate * dt));

        /// <summary>Exponential smoothing of an angle along the shortest arc (prototype `dampAngle`).</summary>
        public static float DampAngle(float a, float b, float rate, float dt) => a + WrapAngle(b - a) * (1f - Mathf.Exp(-rate * dt));

        /// <summary>Hermite smoothstep with edges (prototype `smoothstep(a, b, v)`; differs from Mathf.SmoothStep).</summary>
        public static float SmoothStep(float a, float b, float v)
        {
            float t = Mathf.Clamp01((v - a) / (b - a));
            return t * t * (3f - 2f * t);
        }

        public static float YawTo(Vector3 from, Vector3 to) => Mathf.Atan2(to.x - from.x, to.z - from.z);

        public static Vector3 YawDir(float yaw) => new Vector3(Mathf.Sin(yaw), 0f, Mathf.Cos(yaw));

        public static float DistXZ(Vector3 a, Vector3 b)
        {
            float dx = a.x - b.x, dz = a.z - b.z;
            return Mathf.Sqrt(dx * dx + dz * dz);
        }

        /// <summary>Absolute angle between a facing yaw and the direction to a target (0..PI).</summary>
        public static float FacingAngle(Vector3 pos, float yaw, Vector3 target) => Mathf.Abs(WrapAngle(YawTo(pos, target) - yaw));

        /// <summary>Unsigned angle between two vectors in radians (three.js `angleTo`).</summary>
        public static float Angle(Vector3 a, Vector3 b)
        {
            float den = Mathf.Sqrt(a.sqrMagnitude * b.sqrMagnitude);
            if (den < 1e-12f) return Mathf.PI / 2f;
            return Mathf.Acos(Mathf.Clamp(Vector3.Dot(a, b) / den, -1f, 1f));
        }

        public static Vector3 ClosestOnSegment(Vector3 p, Vector3 a, Vector3 b)
        {
            Vector3 ab = b - a;
            float len2 = ab.sqrMagnitude;
            if (len2 < 1e-10f) return a;
            float t = Mathf.Clamp01(Vector3.Dot(p - a, ab) / len2);
            return a + ab * t;
        }

        /// <summary>Vertical capsule axis of an actor standing at `feet`.</summary>
        public static void CapsuleAxis(Vector3 feet, float radius, float height, out Vector3 a, out Vector3 b)
        {
            a = new Vector3(feet.x, feet.y + radius, feet.z);
            b = new Vector3(feet.x, feet.y + Mathf.Max(radius, height - radius), feet.z);
        }

        /// <summary>Closest point on an actor's capsule axis to p.</summary>
        public static Vector3 ClosestOnCapsule(Vector3 feet, float radius, float height, Vector3 p)
        {
            CapsuleAxis(feet, radius, height, out var a, out var b);
            return ClosestOnSegment(p, a, b);
        }

        /// <summary>Distance from p to the capsule surface (negative = inside).</summary>
        public static float CapsuleDistance(Vector3 feet, float radius, float height, Vector3 p)
            => (ClosestOnCapsule(feet, radius, height, p) - p).magnitude - radius;

        /// <summary>
        /// Melee arc test against one actor capsule (port of Combat.arc's per-target check).
        /// `yaw`/`halfAngle` in radians; yMin/yMax are the vertical reach relative to `origin`.
        /// Within 0.6 m the angle is ignored so point-blank targets are always hit.
        /// </summary>
        public static bool InArc(Vector3 origin, float yaw, float range, float halfAngle, float yMin, float yMax,
                                 Vector3 feet, float radius, float height, out Vector3 point)
        {
            Vector3 q = origin;
            q.y = Mathf.Min(Mathf.Max(origin.y, feet.y), feet.y + height);
            point = ClosestOnCapsule(feet, radius, height, q);
            float dx = point.x - origin.x, dz = point.z - origin.z;
            float dist = Mathf.Sqrt(dx * dx + dz * dz) - radius;
            if (dist > range) return false;
            float relY = feet.y + height * 0.5f - origin.y;
            if (relY < yMin - height * 0.5f || relY > yMax + height * 0.5f) return false;
            if (dist > 0.6f)
            {
                float ang = Mathf.Abs(WrapAngle(Mathf.Atan2(dx, dz) - yaw));
                if (ang > halfAngle) return false;
            }
            return true;
        }

        /// <summary>Radial (sphere) test against one actor capsule (port of Combat.radial's per-target check).</summary>
        public static bool InRadial(Vector3 center, float radius, float yRange, Vector3 feet, float r, float height,
                                    out float dist, out Vector3 point)
        {
            point = ClosestOnCapsule(feet, r, height, center);
            dist = (point - center).magnitude - r;
            if (dist > radius) return false;
            if (Mathf.Abs(feet.y + height * 0.5f - center.y) > yRange + height * 0.5f) return false;
            dist = Mathf.Max(0f, dist);
            return true;
        }

        /// <summary>Lock-on / auto-aim score (lower is better): distance weighted by off-axis angle.</summary>
        public static float TargetScore(float distance, float angle) => distance * (1f + angle * 2.2f);

        /// <summary>
        /// Index of the best aim point in front of `from` along `dir` (or -1). Candidates beyond maxDist,
        /// closer than 1 cm or outside maxAngle (radians) are rejected. Line of sight is the caller's job.
        /// </summary>
        public static int BestTargetIndex(Vector3 from, Vector3 dir, float maxDist, float maxAngle, IReadOnlyList<Vector3> aimPoints)
        {
            int best = -1;
            float bestScore = float.PositiveInfinity;
            for (int i = 0; i < aimPoints.Count; i++)
            {
                Vector3 v = aimPoints[i] - from;
                float d = v.magnitude;
                if (d > maxDist || d < 0.01f) continue;
                float ang = Angle(v, dir);
                if (ang > maxAngle) continue;
                float score = TargetScore(d, ang);
                if (score < bestScore)
                {
                    bestScore = score;
                    best = i;
                }
            }
            return best;
        }

        /// <summary>Perpendicular distance of p from a ray (from, dir normalised) if 0 &lt; along &lt; len, else +inf.</summary>
        public static float RayDistance(Vector3 from, Vector3 dir, float len, Vector3 p)
        {
            Vector3 to = p - from;
            float along = Vector3.Dot(to, dir);
            if (along <= 0f || along >= len) return float.PositiveInfinity;
            return (to - dir * along).magnitude;
        }

        /// <summary>Color from a 0xRRGGBB literal (sRGB), as used by the prototype.</summary>
        public static Color Hex(uint rgb, float alpha = 1f)
            => new Color(((rgb >> 16) & 0xff) / 255f, ((rgb >> 8) & 0xff) / 255f, (rgb & 0xff) / 255f, alpha);
    }
}
