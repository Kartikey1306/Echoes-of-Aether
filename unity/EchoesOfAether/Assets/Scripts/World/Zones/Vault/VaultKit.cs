using System.Collections.Generic;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.AI;
using UnityEngine.Rendering;
using static EOA.ProtoSpace;

namespace EOA
{
    /// <summary>Deterministic PRNG (port of the prototype's mulberry32 `rng(seed)` in core/MathUtil.ts).</summary>
    public sealed class VaultRng
    {
        uint s;

        public VaultRng(uint seed) { s = seed; }

        public float Next()
        {
            unchecked
            {
                s += 0x6d2b79f5u;
                var t = s;
                t = (t ^ (t >> 15)) * (t | 1u);
                t ^= t + (t ^ (t >> 7)) * (t | 61u);
                return (float)((t ^ (t >> 14)) / 4294967296.0);
            }
        }

        public float Range(float a, float b) => a + (b - a) * Next();
        public bool Chance(float p) => Next() < p;
        public float Sign() => Next() < 0.5f ? -1f : 1f;
    }

    /// <summary>
    /// Level-building helpers shared by the Vault and Core zones: the prototype's interior `room()` (with grated floors
    /// built as see-through grating over a dark sub-floor), cylinder colliders, removable door blockers, material swaps
    /// on Blender props, debris scatter, and a few procedural meshes (arc torus segments, flat rings, glyph marks).
    /// All positions are prototype design space unless a parameter says Unity.
    /// </summary>
    public static class VaultKit
    {
        // ------------------------------------------------------------------ rooms (port of kit/Interior.room)

        public struct Door
        {
            public char Side;
            public float At, W, H;
            public Door(char side, float at, float w, float h) { Side = side; At = at; W = w; H = h; }
        }

        /// <summary>
        /// Port of Interior.room: sides n = min z, s = max z, w = min x, e = max x. `skip` lists sides as chars ("ns").
        /// A "grate" floor becomes a see-through grating plate over a dark sub-floor (the kit grating is alpha-cut),
        /// with the prototype's 0.5 m floor slab as its collider so walkable heights stay identical.
        /// </summary>
        public static void Room(LevelKit b, float x0, float z0, float x1, float z1, float h, string floor, string wall, string ceiling,
            string trim, string skip = "", Door[] doors = null, float thick = 0.4f, float y = 0)
        {
            var t = thick;
            float cx = (x0 + x1) / 2, cz = (z0 + z1) / 2;
            if (floor == "grate") GrateFloor(b, cx, y, cz, x1 - x0, z1 - z0);
            else b.Box(cx, y - 0.25f, cz, x1 - x0, 0.5f, z1 - z0, floor);
            if (ceiling != null) b.Box(cx, y + h + 0.25f, cz, x1 - x0 + t * 2, 0.5f, z1 - z0 + t * 2, ceiling, collide: false);
            foreach (var side in "nsew")
            {
                if (skip != null && skip.IndexOf(side) >= 0) continue;
                var along = side == 'n' || side == 's';
                var a0 = along ? x0 - t : z0 - t;
                var a1 = along ? x1 + t : z1 + t;
                var fix = side == 'n' ? z0 - t / 2 : side == 's' ? z1 + t / 2 : side == 'w' ? x0 - t / 2 : x1 + t / 2;
                var cur = a0;
                void Seg(float s0, float s1, float yb, float yt)
                {
                    if (s1 - s0 < 0.01f || yt - yb < 0.01f) return;
                    float mid = (s0 + s1) / 2, len = s1 - s0;
                    if (along) b.Box(mid, y + (yb + yt) / 2, fix, len, yt - yb, t, wall);
                    else b.Box(fix, y + (yb + yt) / 2, mid, t, yt - yb, len, wall);
                }
                if (doors != null)
                {
                    var list = new List<Door>();
                    foreach (var d in doors) if (d.Side == side) list.Add(d);
                    list.Sort((p, q) => p.At.CompareTo(q.At));
                    foreach (var d in list)
                    {
                        float d0 = d.At - d.W / 2, d1 = d.At + d.W / 2;
                        Seg(cur, d0, 0, h);
                        Seg(d0, d1, d.H > 0 ? d.H : Mathf.Min(h, 3), h);
                        cur = d1;
                    }
                }
                Seg(cur, a1, 0, h);
                if (trim != null)
                {
                    if (along) b.Box((a0 + a1) / 2, y + 0.08f, fix + (side == 'n' ? t / 2 + 0.02f : -t / 2 - 0.02f), a1 - a0, 0.16f, 0.04f, trim, collide: false, shadow: false);
                    else b.Box(fix + (side == 'w' ? t / 2 + 0.02f : -t / 2 - 0.02f), y + 0.08f, (a0 + a1) / 2, 0.04f, 0.16f, a1 - a0, trim, collide: false, shadow: false);
                }
            }
        }

        /// <summary>Grated floor: alpha-cut grating at y over a dark sub-floor 0.4 m below; collider = the prototype's 0.5 m slab.</summary>
        public static void GrateFloor(LevelKit b, float cx, float y, float cz, float w, float d)
        {
            b.Box(cx, y - 0.006f, cz, w, 0.012f, d, "grate", collide: false, shadow: false);
            b.Box(cx, y - 0.45f, cz, w, 0.1f, d, "metal_dark", collide: false, shadow: false);
            b.SolidCollider(cx, y - 0.25f, cz, w, 0.5f, d);
        }

        // ------------------------------------------------------------------ colliders

        /// <summary>Static cylinder collider (prototype LevelBuilder cyl collider) without visuals.</summary>
        public static MeshCollider CylCollider(LevelKit b, float x, float y, float z, float r, float h, int seg = 16)
        {
            var go = new GameObject("col_cyl");
            go.layer = CombatLayers.World;
            go.transform.SetParent(b.Root, false);
            go.transform.localPosition = V(x, y, z);
            var mc = go.AddComponent<MeshCollider>();
            mc.sharedMesh = FxMesh.Cylinder(r, r, h, Mathf.Clamp(seg, 8, 32), true);
            return mc;
        }

        /// <summary>
        /// Removable blocker (doors, the hidden wall): a World-layer box collider plus a carving NavMesh obstacle.
        /// Returned inactive so the zone's NavMesh bake (between Build and OnLoaded) paths through the opening;
        /// activate it in OnLoaded while the door is shut.
        /// </summary>
        public static GameObject DoorBlocker(LevelKit b, float x, float y, float z, float sx, float sy, float sz)
        {
            var bc = b.AddBoxCollider(V(x, y, z), new Vector3(sx, sy, sz), Quaternion.identity, CombatLayers.World);
            var go = bc.gameObject;
            go.name = "door_blocker";
            var ob = go.AddComponent<NavMeshObstacle>();
            ob.shape = NavMeshObstacleShape.Box;
            ob.size = new Vector3(sx, sy, sz);
            ob.carving = true;
            ob.carveOnlyStationary = true;
            go.SetActive(false);
            return go;
        }

        // ------------------------------------------------------------------ props

        /// <summary>Environment prop parented under `parent` (animated / togglable pieces live outside the static prop root).</summary>
        public static GameObject PropUnder(LevelKit b, Transform parent, string name, float x, float y, float z, float yaw = 0, float scale = 1, bool collide = false)
        {
            var go = b.Prop(name, x, y, z, yaw, scale, collide: collide);
            go.transform.SetParent(parent, true);
            return go;
        }

        public static bool IsPlaceholder(GameObject prop) => prop != null && prop.name.EndsWith("_Placeholder");

        /// <summary>
        /// Replace material slots whose name contains `slotKey` (e.g. "emit_red", "aether") on every renderer of a prop.
        /// When nothing matches (placeholder box) every slot is replaced if `allWhenMissing`. Returns the number of slots.
        /// Build-time only (allocates).
        /// </summary>
        public static int SwapMaterial(GameObject go, string slotKey, Material m, bool allWhenMissing = false)
        {
            if (go == null || m == null) return 0;
            var n = 0;
            var renderers = go.GetComponentsInChildren<Renderer>(true);
            foreach (var r in renderers)
            {
                var mats = r.sharedMaterials;
                var changed = false;
                for (var i = 0; i < mats.Length; i++)
                {
                    if (mats[i] == null || !mats[i].name.Contains(slotKey)) continue;
                    mats[i] = m;
                    changed = true;
                    n++;
                }
                if (changed) r.sharedMaterials = mats;
            }
            if (n == 0 && allWhenMissing)
            {
                foreach (var r in renderers)
                {
                    var mats = r.sharedMaterials;
                    for (var i = 0; i < mats.Length; i++) mats[i] = m;
                    r.sharedMaterials = mats;
                    n += mats.Length;
                }
            }
            return n;
        }

        /// <summary>
        /// Per-renderer material arrays for a set of states, where slots matching `slotKey` take the state's material.
        /// Lets Tick switch looks with `renderer.sharedMaterials = sets[i][state]` without allocating.
        /// </summary>
        public static (Renderer[] renderers, Material[][][] sets) MaterialStates(GameObject go, string slotKey, Material[] states)
        {
            var rs = go.GetComponentsInChildren<Renderer>(true);
            var sets = new Material[rs.Length][][];
            // When no renderer carries the slot (placeholder box) the whole prop takes the state material.
            var any = false;
            foreach (var r in rs)
                foreach (var m in r.sharedMaterials)
                    if (m != null && m.name.Contains(slotKey)) any = true;
            for (var i = 0; i < rs.Length; i++)
            {
                var baseMats = rs[i].sharedMaterials;
                sets[i] = new Material[states.Length][];
                for (var s = 0; s < states.Length; s++)
                {
                    var arr = (Material[])baseMats.Clone();
                    for (var k = 0; k < arr.Length; k++)
                        if (!any || (arr[k] != null && arr[k].name.Contains(slotKey))) arr[k] = states[s];
                    sets[i][s] = arr;
                }
            }
            return (rs, sets);
        }

        public static void SetShadows(GameObject go, bool cast)
        {
            foreach (var r in go.GetComponentsInChildren<Renderer>(true)) r.shadowCastingMode = cast ? ShadowCastingMode.On : ShadowCastingMode.Off;
        }

        /// <summary>
        /// Port of Props.debris with Blender rubble: the same mulberry32 sequence places a dark debris pile for the big
        /// first piece and small rubble chunks for the rest (colliders only on pieces the prototype made solid, s &gt; 0.45).
        /// </summary>
        public static void Debris(LevelKit b, float x, float z, float radius, int count, uint seed, bool dark)
        {
            var r = new VaultRng(seed);
            for (var i = 0; i < count; i++)
            {
                var a = r.Range(0, Mathf.PI * 2);
                var d = Mathf.Sqrt(r.Next()) * radius;
                var s = r.Range(0.15f, 0.6f) * (i == 0 ? 2 : 1);
                var sx = s * r.Range(0.8f, 1.6f);
                r.Range(0.4f, 0.9f);
                r.Range(0.7f, 1.3f);
                r.Chance(0.8f);
                var yaw = r.Range(0, 3);
                r.Range(-0.3f, 0.3f);
                r.Range(-0.3f, 0.3f);
                var px = x + Mathf.Cos(a) * d;
                var pz = z + Mathf.Sin(a) * d;
                if (i == 0) b.Prop(dark ? "Debris_Pile_Dark" : "Debris_Pile_A", px, 0, pz, yaw, Mathf.Clamp(sx / 1.6f, 0.6f, 1.2f), collide: s > 0.45f);
                else if (s > 0.42f) b.Prop("Rubble_Chunk_L", px, 0, pz, yaw, Mathf.Clamp(sx / 0.9f, 0.4f, 1.1f), collide: s > 0.45f);
                else b.Prop("Rubble_Chunk_S", px, 0, pz, yaw, Mathf.Clamp(sx / 0.35f, 0.5f, 1.6f), collide: false);
            }
        }

        // ------------------------------------------------------------------ procedural meshes

        static void Tri(List<int> t, List<Vector3> v, int a, int b, int c, Vector3 n)
        {
            var cr = Vector3.Cross(v[b] - v[a], v[c] - v[a]);
            if (Vector3.Dot(cr, n) >= 0) { t.Add(a); t.Add(b); t.Add(c); }
            else { t.Add(a); t.Add(c); t.Add(b); }
        }

        static Mesh Build(string name, List<Vector3> v, List<Vector3> n, List<int> t)
        {
            var m = new Mesh { name = name };
            m.SetVertices(v);
            m.SetNormals(n);
            m.SetTriangles(t, 0);
            WhiteColors(m);
            m.RecalculateBounds();
            return m;
        }

        /// <summary>White vertex colours (particle materials multiply by them).</summary>
        static void WhiteColors(Mesh m)
        {
            var c = new Color[m.vertexCount];
            for (var i = 0; i < c.Length; i++) c[i] = Color.white;
            m.colors = c;
        }

        /// <summary>Unshared copy of a box with white vertex colours, for additive (particle-shader) volumes.</summary>
        public static Mesh GlowBox(float w, float h, float d)
        {
            var m = Object.Instantiate(FxMesh.Box(w, h, d));
            m.name = "vault_glowbox";
            WhiteColors(m);
            return m;
        }

        /// <summary>
        /// Horizontal torus arc in Unity space (prototype TorusGeometry in the XY plane laid flat with rotation.x = PI/2):
        /// prototype angle u maps to Unity (-R cos u, 0, R sin u).
        /// </summary>
        public static Mesh ArcTorusFlat(float R, float r, float start, float arc, int radialSeg = 6, int tubularSeg = 16)
        {
            var v = new List<Vector3>(); var n = new List<Vector3>(); var t = new List<int>();
            for (var j = 0; j <= radialSeg; j++)
            {
                var tv = j / (float)radialSeg * Mathf.PI * 2;
                for (var i = 0; i <= tubularSeg; i++)
                {
                    var u = start + i / (float)tubularSeg * arc;
                    var d = new Vector3(-Mathf.Cos(u), 0, Mathf.Sin(u));
                    var nn = d * Mathf.Cos(tv) + Vector3.up * Mathf.Sin(tv);
                    v.Add(d * R + nn * r);
                    n.Add(nn);
                }
            }
            var cols = tubularSeg + 1;
            for (var j = 0; j < radialSeg; j++)
                for (var i = 0; i < tubularSeg; i++)
                {
                    int a = j * cols + i, b2 = a + 1, c = a + cols, e = c + 1;
                    var nn = (n[a] + n[e]).normalized;
                    Tri(t, v, a, c, b2, nn);
                    Tri(t, v, b2, c, e, nn);
                }
            return Build("vault_arc", v, n, t);
        }

        /// <summary>Flat ring in the XZ plane facing up (prototype RingGeometry(inner, outer).rotateX(-PI/2)).</summary>
        public static Mesh FlatRing(float inner, float outer, int seg = 32)
        {
            var v = new List<Vector3>(); var n = new List<Vector3>(); var t = new List<int>();
            for (var i = 0; i <= seg; i++)
            {
                var a = i / (float)seg * Mathf.PI * 2;
                var d = new Vector3(Mathf.Sin(a), 0, Mathf.Cos(a));
                v.Add(d * inner); n.Add(Vector3.up);
                v.Add(d * outer); n.Add(Vector3.up);
            }
            for (var i = 0; i < seg; i++)
            {
                int a = i * 2, b2 = a + 1, c = a + 2, e = a + 3;
                Tri(t, v, a, b2, c, Vector3.up);
                Tri(t, v, c, b2, e, Vector3.up);
            }
            return Build("vault_ring", v, n, t);
        }

        /// <summary>
        /// Glyph marks facing local +Z (port of VaultZone.makeGlyph): `order` bars at the top (which resonator) and
        /// `value` dots in the centre (the target tuning). Offsets are in the plate's local XY plane.
        /// </summary>
        public static Mesh GlyphMarks(int order, int value, float z)
        {
            var v = new List<Vector3>(); var n = new List<Vector3>(); var t = new List<int>();
            void Quad(float cx, float cy, float w, float h)
            {
                var i0 = v.Count;
                v.Add(new Vector3(cx - w / 2, cy - h / 2, z)); v.Add(new Vector3(cx + w / 2, cy - h / 2, z));
                v.Add(new Vector3(cx + w / 2, cy + h / 2, z)); v.Add(new Vector3(cx - w / 2, cy + h / 2, z));
                for (var k = 0; k < 4; k++) n.Add(Vector3.forward);
                Tri(t, v, i0, i0 + 1, i0 + 2, Vector3.forward);
                Tri(t, v, i0, i0 + 2, i0 + 3, Vector3.forward);
            }
            void Disc(float cx, float cy, float r)
            {
                var c = v.Count;
                v.Add(new Vector3(cx, cy, z)); n.Add(Vector3.forward);
                for (var k = 0; k <= 12; k++)
                {
                    var a = k / 12f * Mathf.PI * 2;
                    v.Add(new Vector3(cx + Mathf.Cos(a) * r, cy + Mathf.Sin(a) * r, z));
                    n.Add(Vector3.forward);
                }
                for (var k = 0; k < 12; k++) Tri(t, v, c, c + 1 + k, c + 2 + k, Vector3.forward);
            }
            for (var k = 0; k <= order; k++) Quad(-0.15f * order / 2 + k * 0.15f, 0.55f, 0.08f, 0.3f);
            for (var k = 0; k < value; k++) Disc((k - (value - 1) / 2f) * 0.28f, -0.05f, 0.09f);
            return Build("vault_glyph", v, n, t);
        }

        /// <summary>Standalone renderer for a procedural mesh under `parent` at a Unity-space local pose.</summary>
        public static GameObject MeshGo(string name, Mesh mesh, Material mat, Transform parent, Vector3 localPos, Quaternion localRot, bool shadow = false)
        {
            var go = new GameObject(name);
            go.layer = CombatLayers.World;
            go.transform.SetParent(parent, false);
            go.transform.localPosition = localPos;
            go.transform.localRotation = localRot;
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var r = go.AddComponent<MeshRenderer>();
            r.sharedMaterial = mat;
            r.shadowCastingMode = shadow ? ShadowCastingMode.On : ShadowCastingMode.Off;
            r.receiveShadows = false;
            return go;
        }

        /// <summary>Unlit glow material (prototype MeshBasicMaterial color.multiplyScalar(k)).</summary>
        public static Material Glow(uint hex, float k) => FxMaterials.Unlit(FxMaterials.Hdr(Hex(hex), k), "vault_glow");

        /// <summary>Additive transparent material whose _BaseColor alpha acts as the prototype's opacity.</summary>
        public static Material Additive(uint hex, float k)
        {
            var m = FxMaterials.Particle(true, FxMaterials.White, true);
            var c = FxMaterials.Hdr(Hex(hex), k);
            c.a = 0;
            m.SetColor("_BaseColor", c);
            return m;
        }

        // ------------------------------------------------------------------ quest state without allocations

        /// <summary>Non-allocating `stage:quest:stage` check (GameState.Check splits strings; Tick must not allocate).</summary>
        public static bool StageIs(string quest, string stage)
        {
            var s = G.State;
            if (s == null || !s.D.Quests.TryGetValue(quest, out var q) || q.Status != "active") return false;
            if (!GameData.Quests.TryGetValue(quest, out var def) || q.Stage >= def.Stages.Length) return false;
            return def.Stages[q.Stage].Id == stage;
        }

        // ------------------------------------------------------------------ cinematics

        /// <summary>Fire-and-forget a cinematic camera move (prototype `void c.shot(...)`); a skip ends it quietly.</summary>
        public static async void Quiet(Task t)
        {
            try { await t; }
            catch (CinematicSkipped) { }
            catch (System.Exception e) { Debug.LogWarning("[cine] " + e.Message); }
        }

        /// <summary>
        /// Dr. Maren's Aether echo for a cinematic (prototype spawnEcho): the translucent character model via
        /// <see cref="Cinematics.CineCtx.SpawnEcho"/>, fading in over 1.5 s with a burst of motes. Without the character
        /// prefab a glowing Aether silhouette stands in. Unity-space position, yaw in degrees; removed after the cinematic.
        /// </summary>
        public static GameObject SpawnEcho(Cinematics.CineCtx c, Vector3 pos, float yawDeg)
        {
            GameObject go = null;
            if (Resources.Load<GameObject>("Characters/Maren") != null)
            {
                var m = c.SpawnEcho("Maren", pos, yawDeg);
                if (m != null) go = m.gameObject;
            }
            else
            {
                go = new GameObject("MarenEcho");
                var root = G.Manager != null && G.Manager.World != null ? G.Manager.World.Root : null;
                if (root != null) go.transform.SetParent(root, true);
                go.transform.SetPositionAndRotation(pos, Quaternion.Euler(0, yawDeg, 0));
                var mat = EnvMaterials.Aether(new Color(0.56f, 0.78f, 1f), 0.7f);
                MeshGo("Body", FxMesh.Cylinder(0.16f, 0.24f, 1.3f, 12, true), mat, go.transform, new Vector3(0, 0.75f, 0), Quaternion.identity);
                MeshGo("Head", FxMesh.Sphere(0.13f, 12, 8), mat, go.transform, new Vector3(0, 1.6f, 0), Quaternion.identity);
                c.Track(go);
            }
            if (go != null) go.AddComponent<VaultEchoFade>();
            VfxManager.Instance?.Embers(pos + Vector3.up, 40, Hex(0x8fd8ff), 1.2f, 1.2f);
            return go;
        }

        /// <summary>
        /// Prototype post `flash` (exposure × (1 + 1.5 flash)) on top of the current zone's colour grade; 0 restores it.
        /// </summary>
        public static void PostFlash(float flash)
        {
            var gm = G.Manager;
            var atm = gm != null && gm.World != null ? (gm.World.Script as ProceduralZone)?.ZoneAtmosphere : null;
            if (atm == null || gm.Post == null) return;
            var s = atm.Settings;
            gm.Post.ApplyGrade(s.Exposure * (1 + flash * 1.5f), s.Contrast, s.Saturation, s.Lift, s.Gain, s.BloomThreshold);
        }

        /// <summary>
        /// Short white-out: the prototype sets post `flash` once, and its frame loop overwrites it on the next frame,
        /// so on screen it reads as a bright pulse. Here the boost decays to 0 over `seconds`.
        /// </summary>
        public static async Task PostFlashPulse(float flash, float seconds)
        {
            var t = 0f;
            while (t < seconds)
            {
                var k = 1 - t / seconds;
                PostFlash(flash * k * k);
                await Awaitable.NextFrameAsync();
                t += Time.deltaTime;
            }
            PostFlash(0);
        }
    }

    /// <summary>
    /// Fades an Aether echo in over 1.5 s (prototype spawnEcho opacity ramp) by scaling the emission and base colour
    /// of the echo's materials. Works on any renderer set; caches everything at start (no per-frame allocations).
    /// </summary>
    public sealed class VaultEchoFade : MonoBehaviour
    {
        static readonly int BaseColorId = Shader.PropertyToID("_BaseColor");
        static readonly int EmissionId = Shader.PropertyToID("_EmissionColor");
        public float Duration = 1.5f;
        Material[] mats;
        Color[] baseCols, emitCols;
        float t;

        void Start()
        {
            var list = new List<Material>();
            foreach (var r in GetComponentsInChildren<Renderer>(true))
                foreach (var m in r.sharedMaterials)
                    if (m != null && !list.Contains(m)) list.Add(m);
            mats = list.ToArray();
            baseCols = new Color[mats.Length];
            emitCols = new Color[mats.Length];
            for (var i = 0; i < mats.Length; i++)
            {
                baseCols[i] = mats[i].HasProperty(BaseColorId) ? mats[i].GetColor(BaseColorId) : Color.white;
                emitCols[i] = mats[i].HasProperty(EmissionId) ? mats[i].GetColor(EmissionId) : Color.black;
            }
            Apply(0);
        }

        void Update()
        {
            if (mats == null || t >= Duration) return;
            t += Time.deltaTime;
            Apply(Mathf.Clamp01(t / Duration));
        }

        void Apply(float k)
        {
            for (var i = 0; i < mats.Length; i++)
            {
                if (mats[i] == null) continue;
                if (mats[i].HasProperty(BaseColorId)) mats[i].SetColor(BaseColorId, baseCols[i] * k);
                if (mats[i].HasProperty(EmissionId)) mats[i].SetColor(EmissionId, emitCols[i] * k);
            }
        }
    }
}
