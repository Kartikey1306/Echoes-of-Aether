using UnityEngine;
using UnityEngine.Rendering;

namespace EOA
{
    /// <summary>
    /// Swing ribbon: samples a base/tip segment every frame while emitting and draws a world-space ribbon through the
    /// samples (Catmull-Rom subdivided so fast 60 fps swings stay round), fading over <see cref="Fade"/> seconds.
    /// Additive HDR material; alpha is weighted by tip speed so a still weapon leaves no smear.
    /// Fixed-size buffers: no per-frame allocations. Owner calls <see cref="Tick"/> after animation (LateUpdate).
    /// </summary>
    public sealed class WeaponTrail
    {
        const int MaxSamples = 24, Sub = 3;
        const int MaxRows = (MaxSamples - 1) * Sub + 1;

        public float Fade = 0.15f;
        /// <summary>Tip speed (m/s) at which a sample is fully opaque.</summary>
        public float FullSpeed = 5f;

        readonly Vector3[] sBase = new Vector3[MaxSamples], sTip = new Vector3[MaxSamples];
        readonly float[] sTime = new float[MaxSamples], sAlpha = new float[MaxSamples];
        int head, count;

        readonly Vector3[] verts = new Vector3[MaxRows * 2];
        readonly Color[] colors = new Color[MaxRows * 2];
        readonly Vector2[] uvs = new Vector2[MaxRows * 2];
        static int[] indices;

        readonly GameObject go;
        readonly Mesh mesh;
        readonly Material mat;
        readonly MeshRenderer mr;
        Vector3 lastTip;
        bool hasLast;
        float time;

        static Texture2D tex;

        public WeaponTrail(string name, Color srgb, float intensity, Transform parent = null)
        {
            go = new GameObject(name);
            if (parent != null) go.transform.SetParent(parent, false);
            mesh = new Mesh { name = name };
            mesh.MarkDynamic();
            if (indices == null)
            {
                indices = new int[(MaxRows - 1) * 6];
                for (int r = 0, k = 0; r < MaxRows - 1; r++)
                {
                    int a = r * 2;
                    indices[k++] = a; indices[k++] = a + 1; indices[k++] = a + 2;
                    indices[k++] = a + 1; indices[k++] = a + 3; indices[k++] = a + 2;
                }
            }
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            mr = go.AddComponent<MeshRenderer>();
            mat = FxMaterials.Particle(true, Texture, true);
            mat.name = "fx_weapon_trail";
            SetColor(srgb, intensity);
            mr.sharedMaterial = mat;
            mr.shadowCastingMode = ShadowCastingMode.Off;
            mr.receiveShadows = false;
            mr.lightProbeUsage = LightProbeUsage.Off;
            mr.reflectionProbeUsage = ReflectionProbeUsage.Off;
            mr.enabled = false;
        }

        /// <summary>Across-ribbon gradient: faint at the base, white-hot core just inside the tip edge.</summary>
        static Texture2D Texture
        {
            get
            {
                if (tex != null) return tex;
                tex = new Texture2D(4, 64, TextureFormat.RGBA32, false) { name = "fx_trail_grad", wrapMode = TextureWrapMode.Clamp };
                var px = new Color32[4 * 64];
                for (int y = 0; y < 64; y++)
                {
                    float v = y / 63f;
                    float a = Mathf.SmoothStep(0f, 1f, v) * 0.75f + Mathf.Exp(-Mathf.Pow((v - 0.88f) / 0.07f, 2f)) * 0.6f;
                    a *= Mathf.SmoothStep(1f, 0.93f, v) * 0.85f + 0.15f;
                    byte b = (byte)Mathf.Clamp(Mathf.RoundToInt(Mathf.Clamp01(a) * 255f), 0, 255);
                    for (int x = 0; x < 4; x++) px[y * 4 + x] = new Color32(255, 255, 255, b);
                }
                tex.SetPixels32(px);
                tex.Apply(false, true);
                return tex;
            }
        }

        public void SetColor(Color srgb, float intensity) => mat.SetColor("_BaseColor", FxMaterials.Hdr(srgb, intensity));

        public void Clear()
        {
            count = 0;
            hasLast = false;
            mr.enabled = false;
        }

        /// <summary>Advance (real seconds), optionally add a sample, rebuild the ribbon.</summary>
        public void Tick(float dt, bool emit, Vector3 basePos, Vector3 tipPos)
        {
            time += dt;
            if (emit)
            {
                float speed = hasLast && dt > 1e-5f ? (tipPos - lastTip).magnitude / dt : 0f;
                lastTip = tipPos;
                hasLast = true;
                head = (head + 1) % MaxSamples;
                sBase[head] = basePos;
                sTip[head] = tipPos;
                sTime[head] = time;
                sAlpha[head] = Mathf.Clamp01(speed / FullSpeed);
                if (count < MaxSamples) count++;
            }
            else hasLast = false;
            // Drop samples older than the fade.
            while (count > 0 && time - sTime[(head - count + 1 + MaxSamples) % MaxSamples] > Fade) count--;
            if (count < 2)
            {
                mr.enabled = false;
                return;
            }
            Build();
            mr.enabled = true;
        }

        int Idx(int k) => (head - count + 1 + k + MaxSamples * 2) % MaxSamples; // k = 0 oldest .. count-1 newest

        void Build()
        {
            int rows = 0;
            for (int k = 0; k < count - 1; k++)
            {
                int i0 = Idx(Mathf.Max(0, k - 1)), i1 = Idx(k), i2 = Idx(k + 1), i3 = Idx(Mathf.Min(count - 1, k + 2));
                int steps = k == count - 2 ? Sub + 1 : Sub;
                for (int s = 0; s < steps; s++)
                {
                    float u = s / (float)Sub;
                    Vector3 b = CatmullRom(sBase[i0], sBase[i1], sBase[i2], sBase[i3], u);
                    Vector3 t = CatmullRom(sTip[i0], sTip[i1], sTip[i2], sTip[i3], u);
                    float age = time - Mathf.Lerp(sTime[i1], sTime[i2], u);
                    float life = Mathf.Clamp01(1f - age / Fade);
                    float a = life * life * Mathf.Lerp(sAlpha[i1], sAlpha[i2], u);
                    int v = rows * 2;
                    verts[v] = b;
                    verts[v + 1] = t;
                    var c = new Color(1f, 1f, 1f, a);
                    colors[v] = c;
                    colors[v + 1] = c;
                    float along = 1f - life;
                    uvs[v] = new Vector2(along, 0f);
                    uvs[v + 1] = new Vector2(along, 1f);
                    rows++;
                    if (rows >= MaxRows) break;
                }
                if (rows >= MaxRows) break;
            }
            mesh.Clear(true);
            mesh.SetVertices(verts, 0, rows * 2);
            mesh.SetColors(colors, 0, rows * 2);
            mesh.SetUVs(0, uvs, 0, rows * 2);
            mesh.SetIndices(indices, 0, (rows - 1) * 6, MeshTopology.Triangles, 0, false);
            mesh.RecalculateBounds();
        }

        static Vector3 CatmullRom(Vector3 p0, Vector3 p1, Vector3 p2, Vector3 p3, float t)
        {
            float t2 = t * t, t3 = t2 * t;
            return 0.5f * (2f * p1 + (p2 - p0) * t + (2f * p0 - 5f * p1 + 4f * p2 - p3) * t2 + (3f * p1 - p0 - 3f * p2 + p3) * t3);
        }

        public void Destroy()
        {
            if (go != null) Object.Destroy(go);
            if (mesh != null) Object.Destroy(mesh);
            if (mat != null) Object.Destroy(mat);
        }
    }
}
