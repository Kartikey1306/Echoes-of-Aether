using UnityEngine;
using UnityEngine.Rendering;

namespace EOA
{
    /// <summary>
    /// Tyre marks of the player's car: one world-space mesh (a ring buffer of quads, the oldest overwritten), dark
    /// alpha-blended strips laid while a wheel slides, locks or spins. One draw call, no per-frame allocation; lives
    /// under the zone (destroyed with it).
    /// </summary>
    public sealed class SkidMarks : MonoBehaviour
    {
        const int MaxQuads = 640;
        const int Tracks = 8;
        static SkidMarks inst;
        Mesh mesh;
        Vector3[] verts;
        Color32[] cols;
        Vector2[] uvs;
        int next;
        bool dirty;
        readonly Vector3[] lastL = new Vector3[Tracks], lastR = new Vector3[Tracks], lastP = new Vector3[Tracks];
        readonly bool[] had = new bool[Tracks];
        readonly byte[] lastA = new byte[Tracks];

        /// <summary>The marks of the current zone (created under `parent` on first use).</summary>
        public static SkidMarks For(Transform parent)
        {
            if (inst != null) return inst;
            var go = new GameObject("SkidMarks");
            if (parent != null) go.transform.SetParent(parent, false);
            inst = go.AddComponent<SkidMarks>();
            return inst;
        }

        void Awake()
        {
            verts = new Vector3[MaxQuads * 4];
            cols = new Color32[MaxQuads * 4];
            uvs = new Vector2[MaxQuads * 4];
            var tris = new int[MaxQuads * 6];
            for (var i = 0; i < MaxQuads; i++)
            {
                int v = i * 4, t = i * 6;
                tris[t] = v; tris[t + 1] = v + 2; tris[t + 2] = v + 1;
                tris[t + 3] = v + 1; tris[t + 4] = v + 2; tris[t + 5] = v + 3;
                // Soft edges across the strip (the dot texture's horizontal profile), constant along it.
                uvs[v] = new Vector2(0.08f, 0.5f); uvs[v + 1] = new Vector2(0.92f, 0.5f); uvs[v + 2] = new Vector2(0.08f, 0.5f); uvs[v + 3] = new Vector2(0.92f, 0.5f);
            }
            mesh = new Mesh { name = "skid_marks", indexFormat = IndexFormat.UInt16 };
            mesh.MarkDynamic();
            mesh.vertices = verts;
            mesh.colors32 = cols;
            mesh.uv = uvs;
            mesh.triangles = tris;
            mesh.bounds = new Bounds(Vector3.zero, Vector3.one * 4000f);
            gameObject.AddComponent<MeshFilter>().sharedMesh = mesh;
            var r = gameObject.AddComponent<MeshRenderer>();
            var m = FxMaterials.Particle(false, FxMaterials.SoftDot);
            m.name = "skid_marks";
            r.sharedMaterial = m;
            r.shadowCastingMode = ShadowCastingMode.Off;
            r.receiveShadows = false;
            r.lightProbeUsage = LightProbeUsage.Off;
            r.reflectionProbeUsage = ReflectionProbeUsage.Off;
        }

        void OnDestroy()
        {
            if (inst == this) inst = null;
            if (mesh != null) Destroy(mesh);
        }

        /// <summary>Lay a mark for `track` (a wheel) at its contact point; strength 0 ends the strip.</summary>
        public void Mark(int track, Vector3 point, Vector3 normal, Vector3 side, float width, float strength)
        {
            if (track < 0 || track >= Tracks) return;
            if (strength <= 0.05f) { had[track] = false; return; }
            var p = point + normal * 0.025f;
            var half = side * (width * 0.5f);
            var l = p - half;
            var rr = p + half;
            var a = (byte)Mathf.Clamp(strength * 150f, 0f, 150f);
            if (had[track])
            {
                if ((p - lastP[track]).sqrMagnitude < 0.18f * 0.18f) return; // one quad every ~18 cm
                if ((p - lastP[track]).sqrMagnitude > 3f * 3f) { had[track] = false; }
                else
                {
                    var v = next * 4;
                    verts[v] = lastL[track]; verts[v + 1] = lastR[track]; verts[v + 2] = l; verts[v + 3] = rr;
                    var c0 = new Color32(10, 10, 12, lastA[track]);
                    var c1 = new Color32(10, 10, 12, a);
                    cols[v] = c0; cols[v + 1] = c0; cols[v + 2] = c1; cols[v + 3] = c1;
                    next = (next + 1) % MaxQuads;
                    dirty = true;
                }
            }
            had[track] = true;
            lastL[track] = l; lastR[track] = rr; lastP[track] = p; lastA[track] = a;
        }

        void LateUpdate()
        {
            if (!dirty) return;
            dirty = false;
            mesh.vertices = verts;
            mesh.colors32 = cols;
        }
    }
}
