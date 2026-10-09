using System.Collections.Generic;
using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Procedural meshes for robots and effects (no colliders, unlike GameObject.CreatePrimitive). Meshes are
    /// cached by parameters and shared; never destroy a mesh returned from here. All shapes are centred on the
    /// origin, Y-up, in metres; winding is fixed so outward faces are front faces in Unity.
    /// </summary>
    public static class FxMesh
    {
        static readonly Dictionary<string, Mesh> cache = new();

        static Mesh Cached(string key, System.Func<Mesh> build)
        {
            if (cache.TryGetValue(key, out var m) && m != null) return m;
            m = build();
            m.name = key;
            cache[key] = m;
            return m;
        }

        static string K(string kind, params float[] p)
        {
            var sb = new System.Text.StringBuilder(kind);
            foreach (var f in p) sb.Append('|').Append(f.ToString("0.####", System.Globalization.CultureInfo.InvariantCulture));
            return sb.ToString();
        }

        // ------------------------------------------------------------------ Boxes

        /// <summary>Box with rounded edges (three's RoundedBoxGeometry look). r &lt;= 0 gives a sharp box.</summary>
        public static Mesh RoundedBox(float w, float h, float d, float r)
        {
            r = Mathf.Max(0f, Mathf.Min(r, w / 2.1f, h / 2.1f, d / 2.1f));
            return Cached(K("rbox", w, h, d, r), () => BuildRoundedBox(new Vector3(w, h, d) * 0.5f, r));
        }

        public static Mesh Box(float w, float h, float d) => RoundedBox(w, h, d, 0f);

        static float[] Coords(float half, float r)
        {
            if (r <= 0f) return new[] { -half, half };
            return new[] { -half, -half + 0.2f * r, -half + 0.6f * r, -half + r, half - r, half - 0.6f * r, half - 0.2f * r, half };
        }

        static Mesh BuildRoundedBox(Vector3 half, float r)
        {
            var verts = new List<Vector3>();
            var norms = new List<Vector3>();
            var uvs = new List<Vector2>();
            var tris = new List<int>();
            Vector3 inner = new Vector3(half.x - r, half.y - r, half.z - r);
            // Each face: fixed axis value, two varying axes.
            for (int face = 0; face < 6; face++)
            {
                int axis = face / 2;
                float sign = face % 2 == 0 ? 1f : -1f;
                int ua = (axis + 1) % 3, va = (axis + 2) % 3;
                float[] cu = Coords(half[ua], r), cv = Coords(half[va], r);
                int start = verts.Count;
                for (int j = 0; j < cv.Length; j++)
                {
                    for (int i = 0; i < cu.Length; i++)
                    {
                        Vector3 p = Vector3.zero;
                        p[axis] = sign * half[axis];
                        p[ua] = cu[i];
                        p[va] = cv[j];
                        Vector3 n;
                        if (r > 0f)
                        {
                            Vector3 c = new Vector3(Mathf.Clamp(p.x, -inner.x, inner.x), Mathf.Clamp(p.y, -inner.y, inner.y), Mathf.Clamp(p.z, -inner.z, inner.z));
                            n = (p - c).normalized;
                            p = c + n * r;
                        }
                        else
                        {
                            n = Vector3.zero;
                            n[axis] = sign;
                        }
                        verts.Add(p);
                        norms.Add(n);
                        uvs.Add(new Vector2((float)i / (cu.Length - 1), (float)j / (cv.Length - 1)));
                    }
                }
                int cols = cu.Length;
                for (int j = 0; j < cv.Length - 1; j++)
                {
                    for (int i = 0; i < cols - 1; i++)
                    {
                        int a = start + j * cols + i, b = a + 1, c = a + cols, e = c + 1;
                        tris.Add(a); tris.Add(c); tris.Add(b);
                        tris.Add(b); tris.Add(c); tris.Add(e);
                    }
                }
            }
            return Finish(verts, norms, uvs, tris, true);
        }

        // ------------------------------------------------------------------ Round shapes

        /// <summary>Cylinder / frustum along Y (three's CylinderGeometry: radiusTop, radiusBottom). rTop 0 = cone.</summary>
        public static Mesh Cylinder(float rTop, float rBottom, float height, int segments = 12, bool caps = true)
            => Cached(K("cyl", rTop, rBottom, height, segments, caps ? 1 : 0), () => BuildCylinder(rTop, rBottom, height, segments, caps, false));

        /// <summary>
        /// Same as <see cref="Cylinder"/> rotated +90 deg about X (three's geometry.rotateX(PI/2)), so the axis runs
        /// along Z and the "top" radius ends up at +Z (forward).
        /// </summary>
        public static Mesh CylinderZ(float rTop, float rBottom, float height, int segments = 12, bool caps = true)
            => Cached(K("cylz", rTop, rBottom, height, segments, caps ? 1 : 0), () => BuildCylinder(rTop, rBottom, height, segments, caps, true));

        /// <summary>Cone with its tip at +Z (stalker head: ConeGeometry.rotateX(PI/2)).</summary>
        public static Mesh ConeZ(float radius, float height, int segments = 6) => CylinderZ(0f, radius, height, segments, true);

        static Mesh BuildCylinder(float rTop, float rBottom, float height, int seg, bool caps, bool alongZ)
        {
            var verts = new List<Vector3>();
            var norms = new List<Vector3>();
            var uvs = new List<Vector2>();
            var tris = new List<int>();
            float hh = height * 0.5f;
            float slope = (rBottom - rTop) / Mathf.Max(1e-5f, height);
            for (int i = 0; i <= seg; i++)
            {
                float a = (float)i / seg * Mathf.PI * 2f;
                float s = Mathf.Sin(a), c = Mathf.Cos(a);
                Vector3 n = new Vector3(s, slope, c).normalized;
                verts.Add(new Vector3(s * rTop, hh, c * rTop)); norms.Add(n); uvs.Add(new Vector2((float)i / seg, 1));
                verts.Add(new Vector3(s * rBottom, -hh, c * rBottom)); norms.Add(n); uvs.Add(new Vector2((float)i / seg, 0));
            }
            for (int i = 0; i < seg; i++)
            {
                int t0 = i * 2, b0 = t0 + 1, t1 = t0 + 2, b1 = t0 + 3;
                tris.Add(t0); tris.Add(b0); tris.Add(t1);
                tris.Add(t1); tris.Add(b0); tris.Add(b1);
            }
            if (caps)
            {
                for (int capI = 0; capI < 2; capI++)
                {
                    bool top = capI == 0;
                    float r = top ? rTop : rBottom;
                    if (r <= 1e-5f) continue;
                    float y = top ? hh : -hh;
                    Vector3 n = top ? Vector3.up : Vector3.down;
                    int center = verts.Count;
                    verts.Add(new Vector3(0, y, 0)); norms.Add(n); uvs.Add(new Vector2(0.5f, 0.5f));
                    for (int i = 0; i <= seg; i++)
                    {
                        float a = (float)i / seg * Mathf.PI * 2f;
                        verts.Add(new Vector3(Mathf.Sin(a) * r, y, Mathf.Cos(a) * r)); norms.Add(n);
                        uvs.Add(new Vector2(0.5f + Mathf.Sin(a) * 0.5f, 0.5f + Mathf.Cos(a) * 0.5f));
                    }
                    for (int i = 0; i < seg; i++) { tris.Add(center); tris.Add(center + 1 + i); tris.Add(center + 2 + i); }
                }
            }
            if (alongZ)
            {
                // Rotate +90 deg about X: (x, y, z) -> (x, -z, y)
                for (int i = 0; i < verts.Count; i++)
                {
                    var v = verts[i];
                    verts[i] = new Vector3(v.x, -v.z, v.y);
                    var n = norms[i];
                    norms[i] = new Vector3(n.x, -n.z, n.y);
                }
            }
            return Finish(verts, norms, uvs, tris, true);
        }

        /// <summary>UV sphere.</summary>
        public static Mesh Sphere(float radius, int segments = 16, int rings = 10)
            => Cached(K("sph", radius, segments, rings), () => BuildSphere(radius, segments, rings, -Mathf.PI, Mathf.PI * 2f, 0f, Mathf.PI, false));

        /// <summary>
        /// Part of a sphere facing +Z (warden shield): phi is the horizontal angle from +Z (left/right),
        /// theta the polar angle from +Y. Double-sided materials recommended.
        /// </summary>
        public static Mesh SphereShell(float radius, int segments, int rings, float phiStart, float phiLength, float thetaStart, float thetaLength)
            => Cached(K("shell", radius, segments, rings, phiStart, phiLength, thetaStart, thetaLength),
                      () => BuildSphere(radius, segments, rings, phiStart, phiLength, thetaStart, thetaLength, true));

        static Mesh BuildSphere(float radius, int seg, int rings, float phiStart, float phiLen, float thetaStart, float thetaLen, bool open)
        {
            var verts = new List<Vector3>();
            var norms = new List<Vector3>();
            var uvs = new List<Vector2>();
            var tris = new List<int>();
            for (int y = 0; y <= rings; y++)
            {
                float v = (float)y / rings;
                float theta = thetaStart + v * thetaLen;
                for (int x = 0; x <= seg; x++)
                {
                    float u = (float)x / seg;
                    float phi = phiStart + u * phiLen;
                    Vector3 n = new Vector3(Mathf.Sin(phi) * Mathf.Sin(theta), Mathf.Cos(theta), Mathf.Cos(phi) * Mathf.Sin(theta));
                    verts.Add(n * radius);
                    norms.Add(n);
                    uvs.Add(new Vector2(u, 1f - v));
                }
            }
            int cols = seg + 1;
            for (int y = 0; y < rings; y++)
            {
                for (int x = 0; x < seg; x++)
                {
                    int a = y * cols + x, b = a + 1, c = a + cols, d = c + 1;
                    tris.Add(a); tris.Add(c); tris.Add(b);
                    tris.Add(b); tris.Add(c); tris.Add(d);
                }
            }
            return Finish(verts, norms, uvs, tris, true);
        }

        /// <summary>Torus in the XY plane facing +Z (three's TorusGeometry); rotate 90 deg about X for a horizontal ring.</summary>
        public static Mesh Torus(float radius, float tube, int radialSeg = 8, int tubularSeg = 32)
            => Cached(K("torus", radius, tube, radialSeg, tubularSeg), () => BuildTorus(radius, tube, radialSeg, tubularSeg, false));

        /// <summary>Torus lying in the XZ plane (horizontal ring).</summary>
        public static Mesh TorusFlat(float radius, float tube, int radialSeg = 6, int tubularSeg = 64)
            => Cached(K("torusxz", radius, tube, radialSeg, tubularSeg), () => BuildTorus(radius, tube, radialSeg, tubularSeg, true));

        static Mesh BuildTorus(float R, float r, int radialSeg, int tubularSeg, bool flat)
        {
            var verts = new List<Vector3>();
            var norms = new List<Vector3>();
            var uvs = new List<Vector2>();
            var tris = new List<int>();
            for (int j = 0; j <= radialSeg; j++)
            {
                for (int i = 0; i <= tubularSeg; i++)
                {
                    float u = (float)i / tubularSeg * Mathf.PI * 2f;
                    float v = (float)j / radialSeg * Mathf.PI * 2f;
                    Vector3 center = new Vector3(R * Mathf.Cos(u), R * Mathf.Sin(u), 0);
                    Vector3 p = new Vector3((R + r * Mathf.Cos(v)) * Mathf.Cos(u), (R + r * Mathf.Cos(v)) * Mathf.Sin(u), r * Mathf.Sin(v));
                    Vector3 n = (p - center).normalized;
                    if (flat)
                    {
                        p = new Vector3(p.x, p.z, p.y);
                        n = new Vector3(n.x, n.z, n.y);
                    }
                    verts.Add(p);
                    norms.Add(n);
                    uvs.Add(new Vector2((float)i / tubularSeg, (float)j / radialSeg));
                }
            }
            int cols = tubularSeg + 1;
            for (int j = 0; j < radialSeg; j++)
            {
                for (int i = 0; i < tubularSeg; i++)
                {
                    int a = j * cols + i, b = a + 1, c = a + cols, d = c + 1;
                    tris.Add(a); tris.Add(c); tris.Add(b);
                    tris.Add(b); tris.Add(c); tris.Add(d);
                }
            }
            return Finish(verts, norms, uvs, tris, true);
        }

        /// <summary>Flat disc in the XZ plane facing down (-Y) (drone under-glow).</summary>
        public static Mesh DiscDown(float radius, int segments = 16)
            => Cached(K("discdown", radius, segments), () =>
            {
                var verts = new List<Vector3> { Vector3.zero };
                var norms = new List<Vector3> { Vector3.down };
                var uvs = new List<Vector2> { new Vector2(0.5f, 0.5f) };
                var tris = new List<int>();
                for (int i = 0; i <= segments; i++)
                {
                    float a = (float)i / segments * Mathf.PI * 2f;
                    verts.Add(new Vector3(Mathf.Sin(a) * radius, 0, Mathf.Cos(a) * radius));
                    norms.Add(Vector3.down);
                    uvs.Add(new Vector2(0.5f + Mathf.Sin(a) * 0.5f, 0.5f + Mathf.Cos(a) * 0.5f));
                }
                for (int i = 0; i < segments; i++) { tris.Add(0); tris.Add(i + 1); tris.Add(i + 2); }
                return Finish(verts, norms, uvs, tris, true);
            });

        // ------------------------------------------------------------------ Effect meshes (not cached: per-instance colours)

        /// <summary>
        /// Flat annulus in the XZ plane (radius 1 at the outer edge) whose vertex alpha follows the prototype
        /// shockwave band: smoothstep(.7,.95,r) * smoothstep(1,.95,r).
        /// </summary>
        public static Mesh ShockwaveRing(int segments = 64)
        {
            float[] radii = { 0.7f, 0.8f, 0.875f, 0.92f, 0.95f, 0.975f, 1f };
            var verts = new List<Vector3>();
            var cols = new List<Color>();
            var uvs = new List<Vector2>();
            var norms = new List<Vector3>();
            var tris = new List<int>();
            for (int ri = 0; ri < radii.Length; ri++)
            {
                float r = radii[ri];
                float a = CombatMath.SmoothStep(0.7f, 0.95f, r) * CombatMath.SmoothStep(1f, 0.95f, r);
                for (int i = 0; i <= segments; i++)
                {
                    float ang = (float)i / segments * Mathf.PI * 2f;
                    verts.Add(new Vector3(Mathf.Sin(ang) * r, 0, Mathf.Cos(ang) * r));
                    cols.Add(new Color(1, 1, 1, a));
                    uvs.Add(new Vector2((float)i / segments, r));
                    norms.Add(Vector3.up);
                }
            }
            int c = segments + 1;
            for (int ri = 0; ri < radii.Length - 1; ri++)
            {
                for (int i = 0; i < segments; i++)
                {
                    int a = ri * c + i, b = a + 1, d = a + c, e = d + 1;
                    tris.Add(a); tris.Add(d); tris.Add(b);
                    tris.Add(b); tris.Add(d); tris.Add(e);
                }
            }
            var m = Finish(verts, norms, uvs, tris, false);
            m.SetColors(cols);
            m.name = "fx_ring";
            return m;
        }

        /// <summary>
        /// Crescent strip for slash arcs, in the XZ plane, sweeping from the right (+X) to the left (-X) of a
        /// character facing +Z, -70..+70 deg (1.25 rad each side). uv.x = along (0..1), uv.y = across (inner 0 .. outer 1).
        /// `along` x `across` vertices; colours are written per frame by the VFX manager.
        /// </summary>
        public static Mesh SlashArc(int along = 33, int across = 5)
        {
            var verts = new List<Vector3>();
            var uvs = new List<Vector2>();
            var norms = new List<Vector3>();
            var cols = new List<Color>();
            var tris = new List<int>();
            for (int i = 0; i < along; i++)
            {
                float t = (float)i / (along - 1);
                float a = (-1f + 2f * t) * 1.25f;
                float inner = 0.55f, outer = 1.0f + Mathf.Sin(t * Mathf.PI) * 0.12f;
                for (int j = 0; j < across; j++)
                {
                    float v = (float)j / (across - 1);
                    float rad = Mathf.Lerp(inner, outer, v);
                    // Mirrored X relative to three.js so the sweep runs right -> left in Unity.
                    verts.Add(new Vector3(-Mathf.Sin(a) * rad, 0, Mathf.Cos(a) * rad));
                    uvs.Add(new Vector2(t, v));
                    norms.Add(Vector3.up);
                    cols.Add(new Color(1, 1, 1, 0));
                }
            }
            for (int i = 0; i < along - 1; i++)
            {
                for (int j = 0; j < across - 1; j++)
                {
                    int a = i * across + j, b = a + 1, c = a + across, d = c + 1;
                    tris.Add(a); tris.Add(b); tris.Add(c);
                    tris.Add(b); tris.Add(d); tris.Add(c);
                }
            }
            var m = Finish(verts, norms, uvs, tris, false);
            m.SetColors(cols);
            m.MarkDynamic();
            m.name = "fx_slash";
            return m;
        }

        /// <summary>Sphere with per-vertex colours (echo wave rim, rewritten per frame).</summary>
        public static Mesh DynamicSphere(int segments = 32, int rings = 16)
        {
            var m = Object.Instantiate(Sphere(1f, segments, rings));
            var c = new Color[m.vertexCount];
            for (int i = 0; i < c.Length; i++) c[i] = new Color(1, 1, 1, 0);
            m.colors = c;
            m.MarkDynamic();
            m.name = "fx_echo";
            return m;
        }

        // ------------------------------------------------------------------ Finish

        static Mesh Finish(List<Vector3> verts, List<Vector3> norms, List<Vector2> uvs, List<int> tris, bool fixWinding)
        {
            if (fixWinding) FixWinding(verts, norms, tris);
            var m = new Mesh();
            if (verts.Count > 65000) m.indexFormat = UnityEngine.Rendering.IndexFormat.UInt32;
            m.SetVertices(verts);
            m.SetNormals(norms);
            m.SetUVs(0, uvs);
            m.SetTriangles(tris, 0);
            m.RecalculateBounds();
            return m;
        }

        /// <summary>Make every triangle front-facing along its vertices' normals (Unity: cross(b-a, c-a) points out).</summary>
        static void FixWinding(List<Vector3> v, List<Vector3> n, List<int> t)
        {
            for (int i = 0; i + 2 < t.Count; i += 3)
            {
                int a = t[i], b = t[i + 1], c = t[i + 2];
                Vector3 face = Vector3.Cross(v[b] - v[a], v[c] - v[a]);
                if (face.sqrMagnitude < 1e-14f) continue;
                Vector3 avg = n[a] + n[b] + n[c];
                if (Vector3.Dot(face, avg) < 0f)
                {
                    t[i + 1] = c;
                    t[i + 2] = b;
                }
            }
        }
    }
}
