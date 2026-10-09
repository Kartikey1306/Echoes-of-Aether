using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;
using static EOA.ProtoSpace;

namespace EOA
{
    /// <summary>
    /// Static level construction (port of LevelBuilder.ts). All coordinates passed in are in prototype design
    /// space (see <see cref="ProtoSpace"/>) so layouts read like the level design; output is Unity space.
    /// Pieces get world-scale UVs (1 UV = 1 m) and are merged per material and 32 m cell into a few meshes on
    /// <see cref="Finish"/>. Colliders are separate static GameObjects on the World layer; invisible blockers use
    /// the IgnoreCamera layer (they stop characters but not the camera or projectiles).
    /// </summary>
    public sealed class LevelKit
    {
        const float Cell = 32f;

        public readonly Transform Root;
        readonly Transform geoRoot, colRoot, propRoot, lightRoot, fxRoot;

        sealed class Bucket
        {
            public Material Mat;
            public bool Shadow;
            public readonly List<Vector3> V = new();
            public readonly List<Vector3> N = new();
            public readonly List<Vector2> UV = new();
            public readonly List<int> T = new();
        }

        readonly Dictionary<(Material, int, int, bool), Bucket> buckets = new();
        int lightCount;
        /// <summary>Maximum realtime lights created by this kit (Forward+ handles many; keep it sane for WebGL).</summary>
        public int LightBudget = 24;
        /// <summary>Global multiplier from prototype light intensities to URP.</summary>
        public float LightScale = ProtoSpace.LightToUnity;
        /// <summary>Unity-space bounds of everything built.</summary>
        public Bounds Bounds;
        bool hasBounds;
        public int Pieces, Meshes, Triangles, Colliders;
        public readonly List<Light> Lights = new();

        public LevelKit(Transform root)
        {
            Root = root;
            geoRoot = Child("Geometry");
            colRoot = Child("Colliders");
            propRoot = Child("Props");
            lightRoot = Child("Lights");
            fxRoot = Child("Fx");
        }

        Transform Child(string n)
        {
            var go = new GameObject(n);
            go.transform.SetParent(Root, false);
            go.layer = CombatLayers.World;
            return go.transform;
        }

        public Transform PropRoot => propRoot;

        /// <summary>Static World-layer box colliders built by this kit (building masses, walls) for dressing passes.</summary>
        public IEnumerable<BoxCollider> WorldBoxes()
        {
            foreach (Transform c in colRoot)
                if (c.gameObject.layer == CombatLayers.World && c.TryGetComponent<BoxCollider>(out var bc)) yield return bc;
        }
        public Transform FxRoot => fxRoot;

        // ------------------------------------------------------------------ mesh accumulation

        Bucket GetBucket(Material m, Vector3 center, bool shadow)
        {
            var key = (m, Mathf.FloorToInt(center.x / Cell), Mathf.FloorToInt(center.z / Cell), shadow);
            if (!buckets.TryGetValue(key, out var b)) buckets[key] = b = new Bucket { Mat = m, Shadow = shadow };
            return b;
        }

        void Grow(Vector3 p)
        {
            if (!hasBounds) { Bounds = new Bounds(p, Vector3.zero); hasBounds = true; }
            else Bounds.Encapsulate(p);
        }

        static void Tri(Bucket b, int i0, int i1, int i2, Vector3 expectedNormal)
        {
            var a = b.V[i0];
            var n = Vector3.Cross(b.V[i1] - a, b.V[i2] - a);
            if (Vector3.Dot(n, expectedNormal) >= 0) { b.T.Add(i0); b.T.Add(i1); b.T.Add(i2); }
            else { b.T.Add(i0); b.T.Add(i2); b.T.Add(i1); }
        }

        /// <summary>Quad with explicit corners (counter-clockwise or clockwise; winding is fixed from the normal).</summary>
        void Quad(Bucket b, Vector3 p0, Vector3 p1, Vector3 p2, Vector3 p3, Vector3 n, Vector2 uv0, Vector2 uv1, Vector2 uv2, Vector2 uv3)
        {
            var i = b.V.Count;
            b.V.Add(p0); b.V.Add(p1); b.V.Add(p2); b.V.Add(p3);
            b.N.Add(n); b.N.Add(n); b.N.Add(n); b.N.Add(n);
            b.UV.Add(uv0); b.UV.Add(uv1); b.UV.Add(uv2); b.UV.Add(uv3);
            Tri(b, i, i + 1, i + 2, n);
            Tri(b, i, i + 2, i + 3, n);
            Grow(p0); Grow(p2);
        }

        static float Seed(float cx, float cy, float cz, float? uvSeed) => uvSeed ?? (cx * 0.37f + cz * 0.61f + cy * 0.13f);

        // ------------------------------------------------------------------ primitives

        /// <summary>Box (centre + full size) with world-scale UVs. Rotations are prototype radians (Euler XYZ).</summary>
        public LevelKit Box(float cx, float cy, float cz, float sx, float sy, float sz, string mat,
            float rotY = 0, bool collide = true, bool shadow = true, float rotX = 0, float rotZ = 0, float? uvSeed = null)
        {
            var c = V(cx, cy, cz);
            var q = Rot(rotX, rotY, rotZ);
            var m = EnvMaterials.Get(mat);
            var b = GetBucket(m, c, shadow && !EnvMaterials.NoShadow(mat));
            var seed = Seed(cx, cy, cz, uvSeed);
            var hx = sx / 2; var hy = sy / 2; var hz = sz / 2;
            var ax = q * Vector3.right; var ay = q * Vector3.up; var az = q * Vector3.forward;
            // Face: normal axis, u axis, v axis, half sizes, uv dims (mirrors three's BoxGeometry face UV extents).
            void Face(Vector3 n, float hn, Vector3 u, float hu, Vector3 v, float hv)
            {
                var o = c + n * hn;
                var p0 = o - u * hu - v * hv; var p1 = o + u * hu - v * hv; var p2 = o + u * hu + v * hv; var p3 = o - u * hu + v * hv;
                float du = hu * 2, dv = hv * 2;
                Quad(b, p0, p1, p2, p3, n,
                    new Vector2(seed, seed * 0.7f), new Vector2(du + seed, seed * 0.7f), new Vector2(du + seed, dv + seed * 0.7f), new Vector2(seed, dv + seed * 0.7f));
            }
            Face(ax, hx, az, hz, ay, hy); Face(-ax, hx, -az, hz, ay, hy);
            Face(ay, hy, ax, hx, az, hz); Face(-ay, hy, ax, hx, -az, hz);
            Face(az, hz, -ax, hx, ay, hy); Face(-az, hz, ax, hx, ay, hy);
            Pieces++;
            if (collide) AddBoxCollider(c, new Vector3(sx, sy, sz), q, CombatLayers.World);
            return this;
        }

        /// <summary>Box from its min corner (prototype space) + size.</summary>
        public LevelKit BoxMin(float x, float y, float z, float sx, float sy, float sz, string mat, float rotY = 0, bool collide = true, bool shadow = true) =>
            Box(x + sx / 2, y + sy / 2, z + sz / 2, sx, sy, sz, mat, rotY, collide, shadow);

        /// <summary>Cylinder / frustum along Y with world-scale UVs (three's CylinderGeometry).</summary>
        public LevelKit Cyl(float cx, float cy, float cz, float rTop, float rBot, float h, string mat, int seg = 12,
            bool open = false, bool collide = true, bool shadow = true, float rotX = 0, float rotY = 0, float rotZ = 0)
        {
            var c = V(cx, cy, cz);
            var q = Rot(rotX, rotY, rotZ);
            var m = EnvMaterials.Get(mat);
            var b = GetBucket(m, c, shadow && !EnvMaterials.NoShadow(mat));
            var circ = Mathf.PI * 2 * Mathf.Max(rTop, rBot);
            var slope = (rBot - rTop) / Mathf.Max(0.0001f, h);
            var start = b.V.Count;
            for (var i = 0; i <= seg; i++)
            {
                var a = i / (float)seg * Mathf.PI * 2;
                var dir = new Vector3(Mathf.Sin(a), 0, Mathf.Cos(a));
                var n = (q * new Vector3(dir.x, slope, dir.z)).normalized;
                b.V.Add(c + q * (dir * rTop + Vector3.up * (h / 2))); b.N.Add(n); b.UV.Add(new Vector2(i / (float)seg * circ, h));
                b.V.Add(c + q * (dir * rBot - Vector3.up * (h / 2))); b.N.Add(n); b.UV.Add(new Vector2(i / (float)seg * circ, 0));
            }
            for (var i = 0; i < seg; i++)
            {
                var t0 = start + i * 2; var b0 = t0 + 1; var t1 = t0 + 2; var b1 = t0 + 3;
                var mid = (q * new Vector3(Mathf.Sin((i + 0.5f) / seg * Mathf.PI * 2), 0, Mathf.Cos((i + 0.5f) / seg * Mathf.PI * 2)));
                Tri(b, t0, b0, b1, mid); Tri(b, t0, b1, t1, mid);
            }
            if (!open)
            {
                for (var cap = 0; cap < 2; cap++)
                {
                    var r = cap == 0 ? rTop : rBot;
                    if (r <= 0.0001f) continue;
                    var y = cap == 0 ? h / 2 : -h / 2;
                    var n = q * (cap == 0 ? Vector3.up : Vector3.down);
                    var ci = b.V.Count;
                    var cc = c + q * (Vector3.up * y);
                    b.V.Add(cc); b.N.Add(n); b.UV.Add(new Vector2(cx, cz));
                    for (var i = 0; i <= seg; i++)
                    {
                        var a = i / (float)seg * Mathf.PI * 2;
                        var lp = new Vector3(Mathf.Sin(a) * r, y, Mathf.Cos(a) * r);
                        b.V.Add(c + q * lp); b.N.Add(n); b.UV.Add(new Vector2(cx + lp.x, cz + lp.z));
                    }
                    for (var i = 0; i < seg; i++) Tri(b, ci, ci + 1 + i, ci + 2 + i, n);
                }
            }
            Grow(c + Vector3.one * Mathf.Max(rTop, rBot) + Vector3.up * h / 2);
            Grow(c - Vector3.one * Mathf.Max(rTop, rBot) - Vector3.up * h / 2);
            Pieces++;
            if (collide)
            {
                var r = Mathf.Max(rTop, rBot);
                if (rotX == 0 && rotZ == 0) CylinderCollider(c, r, h, Mathf.Clamp(seg, 8, 32));
                else AddBoxCollider(c, new Vector3(r * 1.6f, h, r * 1.6f), q, CombatLayers.World);
            }
            return this;
        }

        /// <summary>
        /// Arbitrary mesh placed at a prototype position with a Unity rotation/scale (use <see cref="ProtoSpace.Rot"/>).
        /// Merged into the static geometry. Optional box collider of the given local size.
        /// </summary>
        public LevelKit AddMesh(Mesh mesh, string mat, Vector3 protoPos, Quaternion rot, Vector3? scale = null, bool shadow = true, Vector3? colliderSize = null)
        {
            var c = V(protoPos);
            var trs = Matrix4x4.TRS(c, rot, scale ?? Vector3.one);
            var m = EnvMaterials.Get(mat);
            var b = GetBucket(m, c, shadow && !EnvMaterials.NoShadow(mat));
            var verts = mesh.vertices; var norms = mesh.normals; var uvs = mesh.uv;
            var start = b.V.Count;
            for (var i = 0; i < verts.Length; i++)
            {
                var p = trs.MultiplyPoint3x4(verts[i]);
                b.V.Add(p);
                b.N.Add(norms.Length == verts.Length ? trs.MultiplyVector(norms[i]).normalized : Vector3.up);
                b.UV.Add(uvs.Length == verts.Length ? uvs[i] : new Vector2(p.x, p.z));
                Grow(p);
            }
            var tris = mesh.triangles;
            var det = Vector3.Dot(Vector3.Cross(trs.GetColumn(0), trs.GetColumn(1)), trs.GetColumn(2));
            for (var i = 0; i < tris.Length; i += 3)
            {
                if (det >= 0) { b.T.Add(start + tris[i]); b.T.Add(start + tris[i + 1]); b.T.Add(start + tris[i + 2]); }
                else { b.T.Add(start + tris[i]); b.T.Add(start + tris[i + 2]); b.T.Add(start + tris[i + 1]); }
            }
            Pieces++;
            if (colliderSize.HasValue) AddBoxCollider(c, Vector3.Scale(colliderSize.Value, scale ?? Vector3.one), rot, CombatLayers.World);
            return this;
        }

        /// <summary>Straight staircase rising along a prototype yaw; steps are visual, a hidden ramp collider smooths movement.</summary>
        public LevelKit Stairs(float x, float y, float z, float yaw, float width, int steps, float rise, float run, string mat)
        {
            float dx = Mathf.Sin(yaw), dz = Mathf.Cos(yaw);
            for (var i = 0; i < steps; i++)
            {
                var h = rise * (i + 1);
                Box(x + dx * run * (i + 0.5f), y + h / 2, z + dz * run * (i + 0.5f), width, h, run, mat, rotY: yaw, collide: false);
            }
            float len = run * steps, height = rise * steps;
            var ang = Mathf.Atan2(height, len);
            var hyp = Mathf.Sqrt(len * len + height * height);
            var c = V(x + dx * len / 2, y + height / 2 - 0.12f, z + dz * len / 2);
            AddBoxCollider(c, new Vector3(width, 0.2f, hyp), RotYXZ(-ang, yaw, 0), CombatLayers.World);
            return this;
        }

        /// <summary>Sloped slab rising `height` over `len` along a prototype yaw.</summary>
        public LevelKit Ramp(float x, float y, float z, float yaw, float width, float len, float height, float thick, string mat)
        {
            var ang = Mathf.Atan2(height, len);
            var hyp = Mathf.Sqrt(len * len + height * height);
            float dx = Mathf.Sin(yaw), dz = Mathf.Cos(yaw);
            var pc = new Vector3(x + dx * len / 2, y + height / 2, z + dz * len / 2);
            var q = RotYXZ(-ang, yaw, 0);
            var mesh = FxMesh.Box(width, thick, hyp);
            var c = V(pc);
            var m = EnvMaterials.Get(mat);
            var b = GetBucket(m, c, true);
            // World-scale UVs along the slab.
            var start = b.V.Count;
            var verts = mesh.vertices; var norms = mesh.normals;
            for (var i = 0; i < verts.Length; i++)
            {
                var p = c + q * verts[i];
                b.V.Add(p); b.N.Add(q * norms[i]);
                var lv = verts[i];
                var an = new Vector3(Mathf.Abs(norms[i].x), Mathf.Abs(norms[i].y), Mathf.Abs(norms[i].z));
                b.UV.Add(an.y > 0.5f ? new Vector2(lv.x, lv.z) : an.x > 0.5f ? new Vector2(lv.z, lv.y) : new Vector2(lv.x, lv.y));
                Grow(p);
            }
            foreach (var t in mesh.triangles) b.T.Add(start + t);
            Pieces++;
            AddBoxCollider(c, new Vector3(width, thick, hyp), q, CombatLayers.World);
            return this;
        }

        /// <summary>Invisible blocking wall: stops characters, not the camera or projectiles.</summary>
        public LevelKit Wall(float cx, float cy, float cz, float sx, float sy, float sz, float rotY = 0)
        {
            AddBoxCollider(V(cx, cy, cz), new Vector3(sx, sy, sz), Rot(0, rotY, 0), CombatLayers.IgnoreCamera);
            return this;
        }

        /// <summary>Collider without visuals that also blocks the camera and projectiles.</summary>
        public LevelKit SolidCollider(float cx, float cy, float cz, float sx, float sy, float sz, float rotY = 0)
        {
            AddBoxCollider(V(cx, cy, cz), new Vector3(sx, sy, sz), Rot(0, rotY, 0), CombatLayers.World);
            return this;
        }

        public BoxCollider AddBoxCollider(Vector3 unityCenter, Vector3 size, Quaternion rot, int layer)
        {
            var go = new GameObject("col");
            go.layer = layer;
            go.transform.SetParent(colRoot, false);
            go.transform.SetPositionAndRotation(Root.TransformPoint(unityCenter), Root.rotation * rot);
            var bc = go.AddComponent<BoxCollider>();
            bc.size = size;
            Colliders++;
            return bc;
        }

        void CylinderCollider(Vector3 unityCenter, float r, float h, int seg)
        {
            var go = new GameObject("col_cyl");
            go.layer = CombatLayers.World;
            go.transform.SetParent(colRoot, false);
            go.transform.position = Root.TransformPoint(unityCenter);
            var mc = go.AddComponent<MeshCollider>();
            mc.sharedMesh = FxMesh.Cylinder(r, r, h, seg, true);
            Colliders++;
        }

        // ------------------------------------------------------------------ objects, props and lights

        /// <summary>Unmerged object (animated, interactive or unique). Position it before or after; parented to the zone.</summary>
        public GameObject AddObject(GameObject go, bool shadow = true)
        {
            go.transform.SetParent(propRoot, true);
            foreach (var r in go.GetComponentsInChildren<Renderer>(true))
            {
                var transparent = r.sharedMaterial != null && r.sharedMaterial.renderQueue >= 3000;
                r.shadowCastingMode = shadow && !transparent ? ShadowCastingMode.On : ShadowCastingMode.Off;
                r.receiveShadows = true;
            }
            return go;
        }

        /// <summary>Standalone mesh object (rotating rings, doors, cores): not merged, so it can be moved later.</summary>
        public GameObject MeshObject(string name, Mesh mesh, Material mat, Vector3 protoPos, Quaternion rot, bool shadow = true, Transform parent = null)
        {
            var go = new GameObject(name);
            go.layer = CombatLayers.World;
            go.transform.SetParent(parent != null ? parent : propRoot, false);
            go.transform.localPosition = V(protoPos);
            go.transform.localRotation = rot;
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var r = go.AddComponent<MeshRenderer>();
            r.sharedMaterial = mat;
            r.shadowCastingMode = shadow ? ShadowCastingMode.On : ShadowCastingMode.Off;
            Grow(go.transform.localPosition);
            return go;
        }

        /// <summary>
        /// Environment prop by asset name (Art/Environment manifest, e.g. "StreetLight", "Car_Sedan_Wrecked").
        /// Loads Resources/Env/Props/&lt;name&gt; (built by the editor setup with LODs and colliders); falls back to a
        /// grey box of the manifest dimensions so layouts stay testable.
        /// </summary>
        /// <summary>Prop with a non-uniform scale (e.g. pipes stretched along X).</summary>
        public GameObject Prop(string name, float x, float y, float z, float yaw, Vector3 scale, float rotX = 0, float rotZ = 0, bool collide = true)
        {
            var go = Prop(name, x, y, z, yaw, 1, rotX, rotZ, collide);
            go.transform.localScale = scale;
            return go;
        }

        public GameObject Prop(string name, float x, float y, float z, float yaw = 0, float scale = 1, float rotX = 0, float rotZ = 0, bool collide = true)
        {
            var go = EnvProps.Instantiate(name, propRoot, collide);
            go.transform.localPosition = V(x, y, z);
            go.transform.localRotation = Rot(rotX, yaw, rotZ);
            if (!Mathf.Approximately(scale, 1)) go.transform.localScale = Vector3.one * scale;
            Grow(go.transform.localPosition);
            Pieces++;
            return go;
        }

        float DecayComp(float decay, float distance)
        {
            if (Mathf.Abs(decay - 2) < 0.01f || distance <= 0) return 1;
            // URP is inverse-square; match the prototype's falloff at a third of the range.
            // (Capped: inverse-square is already brighter than the prototype close to the light.)
            var dRef = Mathf.Max(1, distance * 0.25f);
            return Mathf.Min(2.5f, Mathf.Pow(dRef, 2 - decay));
        }

        public Light PointLight(float x, float y, float z, uint color, float intensity, float distance, float decay = 2)
        {
            if (lightCount >= LightBudget) return null;
            var go = new GameObject("PointLight");
            go.transform.SetParent(lightRoot, false);
            go.transform.localPosition = V(x, y, z);
            var l = go.AddComponent<Light>();
            l.type = LightType.Point;
            l.color = Hex(color);
            l.range = distance > 0 ? distance : Mathf.Sqrt(intensity) * 4;
            l.intensity = intensity * LightScale * DecayComp(decay, l.range);
            l.shadows = LightShadows.None;
            l.renderMode = LightRenderMode.Auto;
            lightCount++;
            Lights.Add(l);
            return l;
        }

        /// <summary>Spot light from a position toward a target; `angle` is the prototype half-angle in radians.</summary>
        public Light SpotLight(float x, float y, float z, float tx, float ty, float tz, uint color, float intensity, float distance, float angle, float penumbra = 0.5f, float decay = 1.6f)
        {
            if (lightCount >= LightBudget) return null;
            var go = new GameObject("SpotLight");
            go.transform.SetParent(lightRoot, false);
            var p = V(x, y, z);
            go.transform.localPosition = p;
            var dir = V(tx, ty, tz) - p;
            go.transform.localRotation = Quaternion.LookRotation(dir.sqrMagnitude > 0.0001f ? dir : Vector3.down);
            var l = go.AddComponent<Light>();
            l.type = LightType.Spot;
            l.color = Hex(color);
            l.range = distance > 0 ? distance : 20;
            l.spotAngle = Mathf.Clamp(angle * 2 * Mathf.Rad2Deg, 1, 179);
            l.innerSpotAngle = l.spotAngle * (1 - penumbra);
            l.intensity = intensity * LightScale * DecayComp(decay, l.range);
            l.shadows = LightShadows.None;
            lightCount++;
            Lights.Add(l);
            return l;
        }

        Material GlowMaterial(uint color, float intensity)
        {
            var m = FxMaterials.Particle(true, FxMaterials.Glow, true);
            m.SetColor("_BaseColor", FxMaterials.Hdr(Hex(color), intensity));
            return m;
        }

        /// <summary>Additive glow pool on a surface (fake light). normal: "up" | "x" | "z".</summary>
        public GameObject GlowDecal(float x, float y, float z, float size, uint color, float intensity = 1, string normal = "up")
        {
            var go = new GameObject("GlowDecal");
            go.transform.SetParent(fxRoot, false);
            go.transform.localPosition = V(x, y, z);
            go.transform.localRotation = normal == "up" ? Quaternion.Euler(90, 0, 0) : normal == "x" ? Quaternion.Euler(0, 90, 0) : Quaternion.identity;
            go.transform.localScale = new Vector3(size, size, 1);
            go.AddComponent<MeshFilter>().sharedMesh = QuadMesh;
            var r = go.AddComponent<MeshRenderer>();
            r.sharedMaterial = GlowMaterial(color, intensity);
            r.shadowCastingMode = ShadowCastingMode.Off;
            r.receiveShadows = false;
            return go;
        }

        /// <summary>Camera-facing additive glow (lamp halos, distant lights).</summary>
        public GameObject GlowSprite(float x, float y, float z, float size, uint color, float intensity = 1)
        {
            var go = GlowDecal(x, y, z, size, color, intensity, "z");
            go.name = "GlowSprite";
            go.AddComponent<KitBillboard>();
            return go;
        }

        static Mesh quad;

        /// <summary>1×1 quad in the XY plane, facing -Z (double-sided materials recommended).</summary>
        public static Mesh QuadMesh
        {
            get
            {
                if (quad != null) return quad;
                quad = new Mesh { name = "kit_quad" };
                quad.vertices = new[] { new Vector3(-0.5f, -0.5f, 0), new Vector3(0.5f, -0.5f, 0), new Vector3(0.5f, 0.5f, 0), new Vector3(-0.5f, 0.5f, 0) };
                quad.uv = new[] { new Vector2(0, 0), new Vector2(1, 0), new Vector2(1, 1), new Vector2(0, 1) };
                quad.normals = new[] { Vector3.back, Vector3.back, Vector3.back, Vector3.back };
                quad.triangles = new[] { 0, 2, 1, 0, 3, 2 };
                quad.RecalculateBounds();
                return quad;
            }
        }

        /// <summary>
        /// Sign board with text lines (port of Props.sign): dark panel, thin emissive border (border 0 = none), legacy TextMesh lines.
        /// Position is the board centre (prototype space); yaw faces the text toward prototype +Z rotated by yaw.
        /// </summary>
        public GameObject Sign(float x, float y, float z, float w, float h, float yaw, string[] lines, uint fg = 0xd8ecff, uint bg = 0x0b1016, float glow = 1.4f, uint border = 0x5fd8ff)
        {
            var go = new GameObject("Sign");
            go.transform.SetParent(propRoot, false);
            go.transform.localPosition = V(x, y, z);
            go.transform.localRotation = YawQ(yaw);
            var panel = GameObject.CreatePrimitive(PrimitiveType.Cube);
            UnityEngine.Object.Destroy(panel.GetComponent<Collider>());
            panel.transform.SetParent(go.transform, false);
            panel.transform.localScale = new Vector3(w, h, 0.06f);
            var pm = EnvMaterials.EmissiveInstance(Hex(bg), 0.15f);
            pm.SetColor("_BaseColor", Hex(bg));
            panel.GetComponent<Renderer>().sharedMaterial = pm;
            if (border != 0)
            {
            var frame = GameObject.CreatePrimitive(PrimitiveType.Cube);
            UnityEngine.Object.Destroy(frame.GetComponent<Collider>());
            frame.transform.SetParent(go.transform, false);
            frame.transform.localScale = new Vector3(w + 0.06f, h + 0.06f, 0.04f);
            frame.transform.localPosition = new Vector3(0, 0, -0.01f);
            frame.GetComponent<Renderer>().sharedMaterial = EnvMaterials.EmissiveInstance(Hex(border), glow * 0.6f);
            }
            var font = WorldText.Font;
            var n = Mathf.Max(1, lines.Length);
            for (var i = 0; i < lines.Length; i++)
            {
                var t = new GameObject("Line" + i);
                t.transform.SetParent(go.transform, false);
                // Text reads on the side facing prototype +Z of the board (the Unity +Z side after the yaw).
                t.transform.localPosition = new Vector3(0, h * (0.5f - (i + 0.5f) / n), 0.04f);
                t.transform.localRotation = Quaternion.Euler(0, 180, 0);
                var tm = t.AddComponent<TextMesh>();
                tm.text = lines[i];
                tm.font = font;
                tm.fontSize = 96;
                tm.characterSize = Mathf.Min(h / n * 0.62f, w / Mathf.Max(4, lines[i].Length) * 1.6f) * 0.1f;
                tm.anchor = TextAnchor.MiddleCenter;
                tm.alignment = TextAlignment.Center;
                tm.color = Hex(fg);
                var mr = t.GetComponent<MeshRenderer>();
                mr.sharedMaterial = WorldText.Material;
                mr.shadowCastingMode = ShadowCastingMode.Off;
            }
            Grow(go.transform.localPosition);
            return go;
        }

        // ------------------------------------------------------------------ finalize

        /// <summary>Merge all buckets into static meshes. Call once after building.</summary>
        public void Finish()
        {
            foreach (var b in buckets.Values)
            {
                if (b.T.Count == 0) continue;
                var mesh = new Mesh { name = "kit_" + b.Mat.name };
                if (b.V.Count > 65000) mesh.indexFormat = IndexFormat.UInt32;
                mesh.SetVertices(b.V);
                mesh.SetNormals(b.N);
                mesh.SetUVs(0, b.UV);
                mesh.SetTriangles(b.T, 0);
                mesh.RecalculateBounds();
                mesh.RecalculateTangents();
                mesh.UploadMeshData(true);
                var go = new GameObject(mesh.name);
                go.layer = CombatLayers.World;
                go.transform.SetParent(geoRoot, false);
                go.AddComponent<MeshFilter>().sharedMesh = mesh;
                var r = go.AddComponent<MeshRenderer>();
                r.sharedMaterial = b.Mat;
                var transparent = b.Mat.renderQueue >= 3000;
                r.shadowCastingMode = b.Shadow && !transparent ? ShadowCastingMode.On : ShadowCastingMode.Off;
                r.receiveShadows = !transparent;
                Meshes++;
                Triangles += b.T.Count / 3;
            }
            buckets.Clear();
            // Props are left unbatched on purpose: zones animate some of them (doors, rings) and the SRP Batcher
            // already makes many draws of shared materials cheap.
        }

        /// <summary>Opt-in static batching of a sub-tree that will never move (meshes must be readable).</summary>
        public void BatchStatic(GameObject go) => StaticBatchingUtility.Combine(go);
    }

    /// <summary>Keeps a quad facing the active camera (glow halos).</summary>
    public sealed class KitBillboard : MonoBehaviour
    {
        void LateUpdate()
        {
            var cam = Camera.main;
            if (cam == null) return;
            transform.rotation = Quaternion.LookRotation(transform.position - cam.transform.position, Vector3.up);
        }
    }
}
