using System;
using System.Collections.Generic;
using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Pose-driven corrective blend shapes for the hero rigs (elbows, knees, shoulders, hips, wrists): after animation,
    /// each shape's weight follows the bend of a bone relative to a parent bone. Shapes named
    /// <c>corr_&lt;Bone&gt;_&lt;axis&gt;_&lt;deg&gt;</c> are authored in Blender as rest-space deltas (they fix the linear-blend
    /// skinning collapse and restore volume at that bend) and exist on every mesh that needs them (body, sleeves,
    /// trousers, gloves): the weight is applied to all of them. CharacterBuilder fills <see cref="Entries"/> from the
    /// manifest key <c>"correctives"</c>:
    /// <code>{ "shape": "corr_LeftForeArm_x_120", "bone": "mixamorig:LeftForeArm", "parent": "mixamorig:LeftArm",
    ///   "axis": [x, y, z], "from": 30, "to": 120 }</code>
    /// Angle convention (shared by both heroes, see blender/heroes_v2/STYLE.md):
    ///   • the bone's direction is the vector from the bone to its main child (optional "child" key; twist bones are
    ///     ignored), expressed in the parent's frame;
    ///   • the angle is that direction's rotation away from its rest-pose (bind pose) direction, signed by the
    ///     right-hand rule about "axis", which is given in Blender world space of the rest pose (Z up, character
    ///     facing -Y, +X = character's left) — i.e. exactly what Blender reports for
    ///     <c>(arm.matrix_world @ bone.matrix_local).to_3x3() @ local_axis</c>;
    ///   • the weight rises linearly from 0 at "from" to 1 at "to" degrees (clamped).
    /// Optional "power" (default 1) shapes the ramp (w = ramp^power).
    /// </summary>
    [DefaultExecutionOrder(25010)]
    [DisallowMultipleComponent]
    public sealed class CorrectiveShapes : MonoBehaviour
    {
        [Serializable]
        public sealed class Entry
        {
            public string Shape, Bone, Parent, Child;
            /// <summary>Bend axis in Blender rest-pose world space (Z up, -Y forward, +X character left).</summary>
            public Vector3 Axis = Vector3.right;
            public float From = 30, To = 120;
            public float Power = 1;
        }

        public Entry[] Entries = Array.Empty<Entry>();

        sealed class Driver
        {
            public Entry E;
            public Transform Bone, Parent;
            public Vector3 Dir;          // bone-local direction to the main child
            public Vector3 Rest;         // rest direction in the parent's frame
            public Vector3 Axis;         // bend axis in the parent's frame (Unity coordinates)
            public (SkinnedMeshRenderer r, int i)[] Targets;
            public float Last = -1;
            public float Angle;
        }

        readonly List<Driver> drivers = new();

        /// <summary>Diagnostics: with the command-line flag -correctiveLog the driver logs its angles/weights twice a second.</summary>
        static readonly bool LogEnabled = Array.IndexOf(Environment.GetCommandLineArgs(), "-correctiveLog") >= 0;
        float logTimer;

        /// <summary>Current weight (0..1) and angle (degrees, Blender sign convention) of a shape, for tests/debugging.</summary>
        public bool TryGet(string shape, out float weight, out float angle)
        {
            foreach (var d in drivers)
                if (d.E.Shape == shape) { weight = Mathf.Max(0, d.Last); angle = d.Angle; return true; }
            weight = angle = 0;
            return false;
        }

        public int Count => drivers.Count;

        /// <summary>Editor/build-time setup: keeps entries whose bones and blend shapes exist under root.</summary>
        public int Configure(Transform root, IEnumerable<Entry> entries)
        {
            var bones = Index(root);
            var shapes = ShapeIndex(root);
            var keep = new List<Entry>();
            if (entries != null)
                foreach (var e in entries)
                    if (e != null && !string.IsNullOrEmpty(e.Shape) && Find(bones, e.Bone) != null && Find(bones, e.Parent) != null && shapes.ContainsKey(e.Shape))
                        keep.Add(e);
            Entries = keep.ToArray();
            return Entries.Length;
        }

        static Dictionary<string, Transform> Index(Transform root)
        {
            var d = new Dictionary<string, Transform>();
            foreach (var t in root.GetComponentsInChildren<Transform>(true))
            {
                d[t.name] = t;
                var c = t.name.LastIndexOf(':');
                if (c >= 0) d.TryAdd(t.name.Substring(c + 1), t);
            }
            return d;
        }

        static Transform Find(Dictionary<string, Transform> d, string n)
        {
            if (string.IsNullOrEmpty(n)) return null;
            if (d.TryGetValue(n, out var t)) return t;
            var c = n.LastIndexOf(':');
            return c >= 0 && d.TryGetValue(n.Substring(c + 1), out t) ? t : null;
        }

        static Dictionary<string, List<(SkinnedMeshRenderer, int)>> ShapeIndex(Transform root)
        {
            var map = new Dictionary<string, List<(SkinnedMeshRenderer, int)>>();
            foreach (var r in root.GetComponentsInChildren<SkinnedMeshRenderer>(true))
            {
                var mesh = r.sharedMesh;
                if (mesh == null) continue;
                for (var s = 0; s < mesh.blendShapeCount; s++)
                {
                    var n = mesh.GetBlendShapeName(s);
                    var dot = n.LastIndexOf('.');
                    if (dot >= 0) n = n.Substring(dot + 1);
                    if (!n.StartsWith("corr_")) continue;
                    if (!map.TryGetValue(n, out var l)) map[n] = l = new List<(SkinnedMeshRenderer, int)>();
                    l.Add((r, s));
                }
            }
            return map;
        }

        static Quaternion Relative(Transform parent, Transform bone) =>
            bone.parent == parent ? bone.localRotation : Quaternion.Inverse(parent.rotation) * bone.rotation;

        /// <summary>
        /// Blender world (rest) -> Unity world. The FBX export (forward -Z, up Y) plus Unity's handedness flip map
        /// Blender (x, y, z) to model space (-x, z, -y); checked against the skeleton (left = LeftArm - RightArm,
        /// up = Head - Hips) so an unexpected root orientation still resolves correctly.
        /// </summary>
        static Func<Vector3, Vector3> BlenderToWorld(Transform root, Dictionary<string, Transform> bones)
        {
            Vector3 ByRoot(Vector3 b) => root.TransformDirection(new Vector3(-b.x, b.z, -b.y));
            var la = Find(bones, "mixamorig:LeftArm");
            var ra = Find(bones, "mixamorig:RightArm");
            var head = Find(bones, "mixamorig:Head");
            var hips = Find(bones, "mixamorig:Hips");
            if (la == null || ra == null || head == null || hips == null) return ByRoot;
            var left = (la.position - ra.position).normalized;
            var up = Vector3.ProjectOnPlane(head.position - hips.position, left).normalized;
            var fwd = Vector3.Cross(-left, up);
            if (Vector3.Angle(ByRoot(Vector3.right), left) < 30 && Vector3.Angle(ByRoot(Vector3.forward), up) < 30) return ByRoot;
            return b => (b.x * left - b.y * fwd + b.z * up).normalized;
        }

        void Awake()
        {
            // Bind pose = the prefab's transforms at instantiation (before the Animator's first evaluation).
            var bones = Index(transform);
            var shapes = ShapeIndex(transform);
            var toWorld = BlenderToWorld(transform, bones);
            drivers.Clear();
            foreach (var e in Entries)
            {
                var b = Find(bones, e.Bone);
                var p = Find(bones, e.Parent);
                if (b == null || p == null || !shapes.TryGetValue(e.Shape, out var targets) || Mathf.Approximately(e.From, e.To)) continue;
                var dir = TwistBones.LocalDirection(b, e.Child);
                var restRel = Relative(p, b);
                var axisW = toWorld(e.Axis.sqrMagnitude > 1e-8f ? e.Axis.normalized : Vector3.right);
                drivers.Add(new Driver
                {
                    E = e, Bone = b, Parent = p, Dir = dir, Rest = (restRel * dir).normalized,
                    Axis = (Quaternion.Inverse(p.rotation) * axisW).normalized, Targets = targets.ToArray(),
                });
            }
            if (drivers.Count == 0) enabled = false;
        }

        void OnDisable()
        {
            foreach (var d in drivers)
            {
                foreach (var (r, i) in d.Targets) if (r != null) r.SetBlendShapeWeight(i, 0);
                d.Last = -1;
            }
        }

        void LateUpdate()
        {
            for (var k = 0; k < drivers.Count; k++)
            {
                var d = drivers[k];
                var cur = (Relative(d.Parent, d.Bone) * d.Dir).normalized;
                var cross = Vector3.Cross(d.Rest, cur);
                var s = cross.magnitude;
                // Unity is left-handed: the numeric cross product of the mirrored vectors flips the rotation sense,
                // so negate to get the right-hand-rule angle the Blender side authored.
                var angle = s < 1e-6f ? 0f : -Mathf.Atan2(s, Vector3.Dot(d.Rest, cur)) * Mathf.Rad2Deg * Vector3.Dot(cross / s, d.Axis);
                d.Angle = angle;
                var w = Mathf.Clamp01((angle - d.E.From) / (d.E.To - d.E.From));
                if (d.E.Power > 0 && !Mathf.Approximately(d.E.Power, 1)) w = Mathf.Pow(w, d.E.Power);
                if (Mathf.Abs(w - d.Last) < 0.002f) continue;
                d.Last = w;
                foreach (var (r, i) in d.Targets) if (r != null) r.SetBlendShapeWeight(i, w * 100f);
            }
            if (LogEnabled && (logTimer -= Time.unscaledDeltaTime) <= 0)
            {
                logTimer = 0.5f;
                var sb = new System.Text.StringBuilder("[corrective] ").Append(name).Append(':');
                foreach (var d in drivers) sb.Append(' ').Append(d.E.Shape).Append('=').Append(d.Angle.ToString("0")).Append("deg/").Append(Mathf.Max(0, d.Last).ToString("0.00"));
                Debug.Log(sb.ToString());
            }
        }
    }
}
