using System;
using System.Collections.Generic;
using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Drives the hero rigs' extra roll ("twist") bones after animation, so wrists and upper arms rotate along their
    /// length instead of collapsing at one joint (candy-wrap). Unity's humanoid ignores these bones, so they stay at
    /// their bind pose unless driven here. CharacterBuilder adds this component when the FBX has the bones and fills
    /// <see cref="Entries"/> from the manifest key <c>"twistBones"</c> (or the defaults below).
    ///
    /// Contract (shared by both heroes, see blender/heroes_v2/STYLE.md):
    ///   mixamorig:LeftForeArmTwist / RightForeArmTwist — child of ForeArm, on the forearm axis (~60 % along).
    ///       mode "follow": its roll about the forearm axis = Weight (0.5) × the hand's roll relative to the forearm.
    ///       Weight the forearm from mid-forearm to the wrist onto it.
    ///   mixamorig:LeftArmTwist / RightArmTwist — child of Arm, on the upper-arm axis (~60 % along).
    ///       mode "counter": it keeps Weight (0.5) of the upper arm's roll relative to the shoulder (it un-rolls the
    ///       other half), so the deltoid / upper half of the upper arm turns half as much as the elbow end.
    ///       Weight the shoulder-side half of the upper arm onto it, blending into Arm towards the elbow.
    /// Swing (bending) is never touched: a twist bone only rolls about its parent's long axis, so its position and
    /// direction stay exactly those of the parent bone.
    /// </summary>
    [DefaultExecutionOrder(25000)]
    [DisallowMultipleComponent]
    public sealed class TwistBones : MonoBehaviour
    {
        [Serializable]
        public sealed class Entry
        {
            /// <summary>Twist bone transform name (e.g. "mixamorig:LeftForeArmTwist").</summary>
            public string Bone;
            /// <summary>Bone whose roll is measured: the hand for "follow", the upper arm itself for "counter".</summary>
            public string Source;
            /// <summary>Frame the roll is measured against: the forearm for "follow", the shoulder for "counter".</summary>
            public string Reference;
            /// <summary>Fraction of the source roll (relative to Reference) the twist bone ends up with.</summary>
            [Range(0, 1)] public float Weight = 0.5f;
            /// <summary>"follow" (twist bone is a child of Reference) or "counter" (twist bone is a child of Source).</summary>
            public string Mode = "follow";
        }

        public Entry[] Entries = Array.Empty<Entry>();

        sealed class Driver
        {
            public Entry E;
            public Transform Bone, Source, Reference;
            public Quaternion BoneRest, SourceRest;
            public Vector3 Axis;        // roll axis: in Reference space ("follow") / in Source rest-local space ("counter")
            public bool Counter;
        }

        readonly List<Driver> drivers = new();

        /// <summary>Defaults used when the manifest has no "twistBones" entry (both heroes use these bone names).</summary>
        public static Entry[] DefaultEntries()
        {
            var list = new List<Entry>();
            foreach (var s in new[] { "Left", "Right" })
            {
                list.Add(new Entry { Bone = $"mixamorig:{s}ForeArmTwist", Source = $"mixamorig:{s}Hand", Reference = $"mixamorig:{s}ForeArm", Weight = 0.5f, Mode = "follow" });
                list.Add(new Entry { Bone = $"mixamorig:{s}ArmTwist", Source = $"mixamorig:{s}Arm", Reference = $"mixamorig:{s}Shoulder", Weight = 0.5f, Mode = "counter" });
            }
            return list.ToArray();
        }

        /// <summary>
        /// Editor/build-time setup from the manifest JSON array (null or empty = defaults). Keeps only entries whose
        /// bones exist under <paramref name="root"/>; returns how many are active.
        /// </summary>
        public int Configure(Transform root, IEnumerable<Entry> entries)
        {
            var bones = Index(root);
            var keep = new List<Entry>();
            foreach (var e in entries ?? DefaultEntries())
                if (e != null && Find(bones, e.Bone) != null && Find(bones, e.Source) != null && Find(bones, e.Reference) != null) keep.Add(e);
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

        /// <summary>Direction from a bone to its main child (bone-local), ignoring twist/helper children.</summary>
        internal static Vector3 LocalDirection(Transform bone, string preferChild = null)
        {
            Transform best = null;
            var bestLen = -1f;
            foreach (Transform c in bone)
            {
                if (c.name.Contains("Twist")) continue;
                if (!string.IsNullOrEmpty(preferChild) && c.name.EndsWith(preferChild)) { best = c; break; }
                var l = c.localPosition.sqrMagnitude;
                if (bone.name.EndsWith("Hand") && c.name.Contains("Middle1")) { best = c; break; }
                if (l > bestLen) { bestLen = l; best = c; }
            }
            if (best == null || best.localPosition.sqrMagnitude < 1e-10f) return Vector3.up;
            return best.localPosition.normalized;
        }

        void Awake()
        {
            // Bind pose = the prefab's transforms at instantiation (before the Animator's first evaluation).
            var bones = Index(transform);
            drivers.Clear();
            foreach (var e in Entries)
            {
                var b = Find(bones, e.Bone);
                var s = Find(bones, e.Source);
                var r = Find(bones, e.Reference);
                if (b == null || s == null || r == null) continue;
                var counter = e.Mode == "counter";
                var d = new Driver { E = e, Bone = b, Source = s, Reference = r, Counter = counter, BoneRest = b.localRotation, SourceRest = Relative(r, s) };
                if (counter)
                {
                    // Roll of the upper arm about its own long axis (rest-local), relative to Reference.
                    d.Axis = LocalDirection(s);
                }
                else
                {
                    // Roll of the hand about the forearm axis (the direction Reference -> Source, in Reference space).
                    d.Axis = s.parent == r ? s.localPosition.normalized : (Quaternion.Inverse(r.rotation) * (s.position - r.position)).normalized;
                    if (d.Axis.sqrMagnitude < 0.5f) d.Axis = LocalDirection(r);
                }
                drivers.Add(d);
            }
            if (drivers.Count == 0) enabled = false;
        }

        /// <summary>Twist part of q about the unit axis (swing-twist decomposition q = swing * twist).</summary>
        internal static Quaternion TwistAbout(Quaternion q, Vector3 axis)
        {
            var p = Vector3.Dot(new Vector3(q.x, q.y, q.z), axis) * axis;
            var t = new Quaternion(p.x, p.y, p.z, q.w);
            var n = Mathf.Sqrt(t.x * t.x + t.y * t.y + t.z * t.z + t.w * t.w);
            if (n < 1e-6f) return Quaternion.identity;
            t = new Quaternion(t.x / n, t.y / n, t.z / n, t.w / n);
            return t.w < 0 ? new Quaternion(-t.x, -t.y, -t.z, -t.w) : t;
        }

        static Quaternion Relative(Transform reference, Transform bone) =>
            bone.parent == reference ? bone.localRotation : Quaternion.Inverse(reference.rotation) * bone.rotation;

        void LateUpdate()
        {
            for (var i = 0; i < drivers.Count; i++)
            {
                var d = drivers[i];
                var w = Mathf.Clamp01(d.E.Weight);
                if (d.Counter)
                {
                    // Source local = swing * rest * twistL (twistL about the source's own rest-local axis).
                    var q = Quaternion.Inverse(d.SourceRest) * Relative(d.Reference, d.Source);
                    var twistL = TwistAbout(q, d.Axis);
                    // Child of the source: un-roll (1 - w) of it.
                    d.Bone.localRotation = Quaternion.SlerpUnclamped(Quaternion.identity, Quaternion.Inverse(twistL), 1f - w) * d.BoneRest;
                }
                else
                {
                    // Hand delta in forearm space: local = delta * rest; its roll about the forearm axis.
                    var delta = Relative(d.Reference, d.Source) * Quaternion.Inverse(d.SourceRest);
                    var twist = TwistAbout(delta, d.Axis);
                    d.Bone.localRotation = Quaternion.SlerpUnclamped(Quaternion.identity, twist, w) * d.BoneRest;
                }
            }
        }
    }
}
