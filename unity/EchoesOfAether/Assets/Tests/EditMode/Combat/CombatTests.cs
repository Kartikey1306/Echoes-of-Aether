using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using NUnit.Framework;
using UnityEngine;

namespace EOA.Tests
{
    /// <summary>
    /// Runtime-type access for tests. The game runtime currently compiles into Assembly-CSharp, which an assembly
    /// definition (this test assembly) cannot reference, so the pure static helpers are reached through reflection.
    /// This keeps the tests compiling and running both now and after the runtime gets its own asmdef.
    /// </summary>
    static class Runtime
    {
        static readonly Dictionary<string, Type> types = new();

        public static Type Find(string fullName)
        {
            if (types.TryGetValue(fullName, out var t)) return t;
            foreach (var a in AppDomain.CurrentDomain.GetAssemblies())
            {
                t = a.GetType(fullName, false);
                if (t != null) break;
            }
            types[fullName] = t;
            return t;
        }

        public static T Fn<T>(string typeName, string method) where T : Delegate
        {
            var type = Find(typeName);
            if (type == null) Assert.Inconclusive($"{typeName} is not loaded");
            var ps = typeof(T).GetMethod("Invoke").GetParameters().Select(p => p.ParameterType).ToArray();
            var mi = type.GetMethod(method, BindingFlags.Public | BindingFlags.Static, null, ps, null);
            Assert.IsNotNull(mi, $"{typeName}.{method}({string.Join(", ", ps.Select(p => p.Name))}) not found");
            return (T)Delegate.CreateDelegate(typeof(T), mi);
        }
    }

    public class CombatMathTests
    {
        const string M = "EOA.CombatMath";
        const float Eps = 1e-4f;

        delegate bool InArcFn(Vector3 origin, float yaw, float range, float halfAngle, float yMin, float yMax, Vector3 feet, float radius, float height, out Vector3 point);
        delegate bool InRadialFn(Vector3 center, float radius, float yRange, Vector3 feet, float r, float height, out float dist, out Vector3 point);

        static Func<float, float> WrapAngle => Runtime.Fn<Func<float, float>>(M, "WrapAngle");
        static Func<Vector3, Vector3, float> YawTo => Runtime.Fn<Func<Vector3, Vector3, float>>(M, "YawTo");
        static Func<float, float, float, float, float> DampAngle => Runtime.Fn<Func<float, float, float, float, float>>(M, "DampAngle");
        static Func<float, float, float, float> SmoothStep => Runtime.Fn<Func<float, float, float, float>>(M, "SmoothStep");
        static Func<Vector3, float, float, Vector3, float> CapsuleDistance => Runtime.Fn<Func<Vector3, float, float, Vector3, float>>(M, "CapsuleDistance");
        static Func<Vector3, Vector3, float, Vector3, float> RayDistance => Runtime.Fn<Func<Vector3, Vector3, float, Vector3, float>>(M, "RayDistance");
        static Func<float, float, float> TargetScore => Runtime.Fn<Func<float, float, float>>(M, "TargetScore");
        static Func<Vector3, Vector3, float, float, IReadOnlyList<Vector3>, int> BestTargetIndex =>
            Runtime.Fn<Func<Vector3, Vector3, float, float, IReadOnlyList<Vector3>, int>>(M, "BestTargetIndex");
        static InArcFn InArc => Runtime.Fn<InArcFn>(M, "InArc");
        static InRadialFn InRadial => Runtime.Fn<InRadialFn>(M, "InRadial");

        static readonly float Deg = Mathf.Deg2Rad;

        // ------------------------------------------------------------------ Angles

        [Test]
        public void WrapAngle_MapsIntoMinusPiToPi()
        {
            var wrap = WrapAngle;
            Assert.AreEqual(0f, wrap(0f), Eps);
            Assert.AreEqual(-Mathf.PI / 2f, wrap(3f * Mathf.PI / 2f), Eps);
            Assert.AreEqual(Mathf.PI / 2f, wrap(-3f * Mathf.PI / 2f), Eps);
            Assert.AreEqual(0.5f, wrap(0.5f + 4f * Mathf.PI), 1e-3f);
            float w = wrap(Mathf.PI);
            Assert.That(w >= -Mathf.PI - Eps && w < Mathf.PI + Eps);
        }

        [Test]
        public void YawTo_FollowsUnityConvention()
        {
            var yawTo = YawTo;
            Assert.AreEqual(0f, yawTo(Vector3.zero, Vector3.forward), Eps, "+Z is yaw 0");
            Assert.AreEqual(90f * Deg, yawTo(Vector3.zero, Vector3.right), Eps, "+X is yaw +90 deg (clockwise from above)");
            Assert.AreEqual(Mathf.PI, Mathf.Abs(yawTo(Vector3.zero, Vector3.back)), Eps);
            // Same as Quaternion.Euler(0, yawDeg, 0) * forward
            float yaw = yawTo(new Vector3(1, 0, 1), new Vector3(4, 7, -3));
            Vector3 dir = Quaternion.Euler(0f, yaw * Mathf.Rad2Deg, 0f) * Vector3.forward;
            Vector3 expected = new Vector3(3, 0, -4).normalized;
            Assert.AreEqual(expected.x, dir.x, 1e-3f);
            Assert.AreEqual(expected.z, dir.z, 1e-3f);
        }

        [Test]
        public void DampAngle_TurnsTheShortWayAcrossPi()
        {
            float a = DampAngle(3.0f, -3.0f, 1000f, 1f);
            Assert.Greater(a, 3.0f, "should increase through +PI instead of sweeping back through 0");
            Assert.AreEqual(-3.0f, WrapAngle(a), 1e-3f);
        }

        [Test]
        public void SmoothStep_HasPrototypeEdgeSemantics()
        {
            var ss = SmoothStep;
            Assert.AreEqual(0f, ss(0.7f, 0.95f, 0.5f), Eps);
            Assert.AreEqual(1f, ss(0.7f, 0.95f, 1f), Eps);
            Assert.AreEqual(0.5f, ss(0f, 1f, 0.5f), Eps);
            // Reversed edges (used by the shockwave band and slash edge fade)
            Assert.AreEqual(1f, ss(1f, 0.95f, 0.9f), Eps);
            Assert.AreEqual(0f, ss(1f, 0.95f, 1f), Eps);
        }

        // ------------------------------------------------------------------ Capsules

        [Test]
        public void CapsuleDistance_MeasuresToSurface()
        {
            Assert.AreEqual(1.5f, CapsuleDistance(Vector3.zero, 0.5f, 2f, new Vector3(2f, 1f, 0f)), Eps);
            Assert.Less(CapsuleDistance(Vector3.zero, 0.5f, 2f, new Vector3(0f, 1f, 0f)), 0f, "inside is negative");
            // Above the top cap: axis ends at height - radius = 1.5
            Assert.AreEqual(1.0f, CapsuleDistance(Vector3.zero, 0.5f, 2f, new Vector3(0f, 3f, 0f)), Eps);
        }

        [Test]
        public void RayDistance_IsPerpendicularWithinTheBeam()
        {
            var rd = RayDistance;
            Assert.AreEqual(0.5f, rd(Vector3.zero, Vector3.forward, 10f, new Vector3(0.5f, 0f, 4f)), Eps);
            Assert.AreEqual(float.PositiveInfinity, rd(Vector3.zero, Vector3.forward, 10f, new Vector3(0f, 0f, -1f)), "behind the origin");
            Assert.AreEqual(float.PositiveInfinity, rd(Vector3.zero, Vector3.forward, 3f, new Vector3(0f, 0f, 4f)), "past the beam end");
        }

        // ------------------------------------------------------------------ Arc / radial queries

        static readonly Vector3 Origin = new Vector3(0f, 1f, 0f);

        bool Arc(Vector3 feet, float range = 3f, float halfDeg = 45f, float yawDeg = 0f, float yMin = -2f, float yMax = 2.5f)
            => InArc(Origin, yawDeg * Deg, range, halfDeg * Deg, yMin, yMax, feet, 0.5f, 2f, out _);

        [Test]
        public void Arc_HitsTargetsInFrontWithinRange()
        {
            Assert.IsTrue(Arc(new Vector3(0f, 0f, 2f)));
            Assert.IsTrue(InArc(Origin, 0f, 3f, 45f * Deg, -2f, 2.5f, new Vector3(0f, 0f, 2f), 0.5f, 2f, out var point));
            Assert.AreEqual(2f, point.z, Eps, "contact point is on the capsule axis");
            Assert.AreEqual(1f, point.y, Eps, "at the attacker's height");
        }

        [Test]
        public void Arc_RangeIsMeasuredFromTheCapsuleSurface()
        {
            // Axis 4 m away, radius 0.5 -> surface at 3.5 m
            Assert.IsFalse(Arc(new Vector3(0f, 0f, 4f), range: 3f));
            Assert.IsTrue(Arc(new Vector3(0f, 0f, 4f), range: 3.6f));
        }

        [Test]
        public void Arc_RejectsTargetsOutsideTheHalfAngle()
        {
            Vector3 at60 = new Vector3(Mathf.Sin(60f * Deg), 0f, Mathf.Cos(60f * Deg)) * 2.5f;
            Assert.IsFalse(Arc(at60, halfDeg: 45f));
            Assert.IsTrue(Arc(at60, halfDeg: 70f));
            Assert.IsFalse(Arc(new Vector3(0f, 0f, -2f)), "behind");
            Assert.IsTrue(Arc(new Vector3(0f, 0f, -2f), yawDeg: 180f), "behind but facing it");
            Assert.IsTrue(Arc(new Vector3(2f, 0f, 0f), yawDeg: 90f), "+X is yaw 90");
        }

        [Test]
        public void Arc_IgnoresAngleAtPointBlankRange()
        {
            // Within 0.6 m of the surface the angle test is skipped (prototype behaviour).
            Assert.IsTrue(Arc(new Vector3(0f, 0f, -0.9f)));
        }

        [Test]
        public void Arc_RespectsVerticalReach()
        {
            Assert.IsFalse(Arc(new Vector3(0f, 6f, 2f)), "far above");
            Assert.IsFalse(Arc(new Vector3(0f, -6f, 2f)), "far below");
            Assert.IsTrue(Arc(new Vector3(0f, 2.5f, 2f)), "on a ledge within reach");
        }

        [Test]
        public void Radial_UsesCapsuleSurfaceAndYRange()
        {
            Assert.IsTrue(InRadial(new Vector3(0f, 0.5f, 0f), 3.6f, 2f, new Vector3(3.5f, 0f, 0f), 0.5f, 2f, out float d, out var p));
            Assert.AreEqual(3.0f, d, 1e-3f, "distance from the centre to the capsule surface (axis 3.5 m away, radius 0.5)");
            Assert.AreEqual(3.5f, p.x, 1e-3f, "point on the capsule axis");
            Assert.IsFalse(InRadial(Vector3.zero, 3f, 2f, new Vector3(4f, 0f, 0f), 0.5f, 2f, out _, out _), "out of radius");
            Assert.IsFalse(InRadial(Vector3.zero, 10f, 1f, new Vector3(0f, 4f, 1f), 0.5f, 2f, out _, out _), "outside the vertical range");
            Assert.IsTrue(InRadial(Vector3.zero, 10f, 4f, new Vector3(0f, 4f, 1f), 0.5f, 2f, out _, out _), "inside a larger vertical range");
        }

        // ------------------------------------------------------------------ Target scoring

        [Test]
        public void TargetScore_PenalisesOffAxisTargets()
        {
            var score = TargetScore;
            Assert.AreEqual(10f, score(10f, 0f), Eps);
            Assert.Less(score(10f, 0f), score(6f, 40f * Deg), "a centred target beats a closer one 40 deg off-axis");
            Assert.Less(score(5f, 5f * Deg), score(10f, 0f), "a close, nearly centred target beats a far centred one");
        }

        [Test]
        public void BestTargetIndex_PicksLowestScoreWithinLimits()
        {
            var best = BestTargetIndex;
            Vector3 from = Vector3.zero, dir = Vector3.forward;
            var aims = new List<Vector3>
            {
                new Vector3(0f, 0f, 10f),                                       // 0: dead ahead, 10 m  -> 10
                new Vector3(Mathf.Sin(40f * Deg), 0f, Mathf.Cos(40f * Deg)) * 6f, // 1: 6 m at 40 deg -> ~15.2
                new Vector3(-3f, 0f, -3f),                                      // 2: behind -> rejected
                new Vector3(0f, 0f, 30f),                                       // 3: too far -> rejected
            };
            Assert.AreEqual(0, best(from, dir, 25f, 60f * Deg, aims));
            aims.Add(new Vector3(Mathf.Sin(5f * Deg), 0f, Mathf.Cos(5f * Deg)) * 5f); // 4: 5 m at 5 deg -> ~5.96
            Assert.AreEqual(4, best(from, dir, 25f, 60f * Deg, aims));
            Assert.AreEqual(-1, best(from, dir, 25f, 2f * Deg, new List<Vector3> { new Vector3(1f, 0f, 1f) }), "outside the cone");
            Assert.AreEqual(-1, best(from, dir, 25f, 60f * Deg, new List<Vector3>()), "no candidates");
            Assert.AreEqual(-1, best(from, dir, 25f, 60f * Deg, new List<Vector3> { new Vector3(0f, 0f, 0.001f) }), "on top of the shooter");
        }
    }

    /// <summary>The prototype (three.js, right-handed, left = +X) to Unity (left-handed, left = -X) pose conversion.</summary>
    public class RobotPoseConventionTests
    {
        static Func<float, float, float, Quaternion> EulerXYZ => Runtime.Fn<Func<float, float, float, Quaternion>>("EOA.RobotAnimator", "EulerXYZ");

        static void AssertDir(Vector3 expected, Vector3 actual, string msg)
        {
            Assert.AreEqual(expected.x, actual.x, 1e-4f, msg + " (x)");
            Assert.AreEqual(expected.y, actual.y, 1e-4f, msg + " (y)");
            Assert.AreEqual(expected.z, actual.z, 1e-4f, msg + " (z)");
        }

        [Test]
        public void NegativeX_SwingsLimbForward()
        {
            // Prototype: "thigh/upperarm x<0 swings forward".
            AssertDir(Vector3.forward, EulerXYZ(-90f * Mathf.Deg2Rad, 0f, 0f) * Vector3.down, "thigh x=-90");
        }

        [Test]
        public void PositiveZ_RaisesLeftArmOutToTheRobotsLeft()
        {
            // Prototype: "upperarm_L z>0 raises arm out to the side"; the robot's left is -X in Unity.
            AssertDir(Vector3.left, EulerXYZ(0f, 0f, 90f * Mathf.Deg2Rad) * Vector3.down, "upperarm_L z=+90");
        }

        [Test]
        public void PositiveY_TwistsTowardTheRobotsLeft()
        {
            // Prototype: "spine/chest y>0 twists left".
            AssertDir(Vector3.left, EulerXYZ(0f, 90f * Mathf.Deg2Rad, 0f) * Vector3.forward, "chest y=+90");
        }

        [Test]
        public void EulerOrderIsXThenYThenZIntrinsic()
        {
            // three.js 'XYZ' = Rx * Ry * Rz (Rz applied first). Mirrored: Rx(x) * Ry(-y) * Rz(-z) in Unity.
            float x = 0.3f, y = -0.7f, z = 1.1f;
            Quaternion expected = Quaternion.AngleAxis(x * Mathf.Rad2Deg, Vector3.right)
                                * Quaternion.AngleAxis(-y * Mathf.Rad2Deg, Vector3.up)
                                * Quaternion.AngleAxis(-z * Mathf.Rad2Deg, Vector3.forward);
            Quaternion q = EulerXYZ(x, y, z);
            Assert.AreEqual(1f, Mathf.Abs(Quaternion.Dot(expected, q)), 1e-4f);
        }
    }
}
