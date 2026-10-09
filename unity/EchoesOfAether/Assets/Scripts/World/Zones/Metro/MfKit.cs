using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;
using static EOA.ProtoSpace;

namespace EOA
{
    /// <summary>Door opening in an <see cref="MfKit.Room"/> wall (prototype Interior.ts Door). H &lt;= 0 means min(room height, 3).</summary>
    public struct MfDoor
    {
        public char Side;
        public float At, W, H;
        public MfDoor(char side, float at, float w, float h = 0) { Side = side; At = at; W = w; H = h; }
    }

    /// <summary>Options of <see cref="MfKit.Room"/> (prototype RoomOpts). Null Ceiling = no ceiling.</summary>
    public sealed class MfRoomOptions
    {
        public string Floor = "floor_lab", Wall = "panel_lab", Ceiling = "concrete_dark";
        /// <summary>Skip the floor slab (the zone builds a custom floor, e.g. grating over a service void).</summary>
        public bool NoFloor;
        public MfDoor[] Doors;
        /// <summary>Sides without a wall, as chars: n = min z, s = max z, w = min x, e = max x.</summary>
        public string Skip = "";
        public float Thick = 0.4f, Y;
        /// <summary>Emissive ceiling panel material (prototype 1.6 x 0.6 boxes every 5 m) → Lab_CeilingLight props. Null = none.</summary>
        public string Panels;
        /// <summary>Baseboard trim material, null = none.</summary>
        public string Trim;
    }

    /// <summary>
    /// Swaps the emissive material slots of a prop instance (lamp diffusers, ceiling panels) between a lit and an unlit
    /// material. Material arrays are prepared once, so toggling allocates nothing. Empty when the prop is a placeholder.
    /// </summary>
    public sealed class MfSwitch
    {
        readonly List<Renderer> renderers = new();
        readonly List<Material[]> lit = new();
        readonly List<Material[]> unlit = new();
        public bool IsLit { get; private set; } = true;

        /// <param name="slotPrefix">Material name prefix of the slots to switch (e.g. "emit_").</param>
        /// <param name="litMat">Material when lit (null keeps the prop's own emissive material).</param>
        /// <param name="unlitMat">Material when dark.</param>
        public static MfSwitch Find(GameObject go, string slotPrefix, Material litMat, Material unlitMat)
        {
            var s = new MfSwitch();
            if (go == null) return s;
            foreach (var r in go.GetComponentsInChildren<Renderer>(true))
            {
                if (r is not MeshRenderer) continue;
                var mats = r.sharedMaterials;
                Material[] on = null, off = null;
                for (var i = 0; i < mats.Length; i++)
                {
                    if (mats[i] == null || !mats[i].name.StartsWith(slotPrefix)) continue;
                    on ??= (Material[])mats.Clone();
                    off ??= (Material[])mats.Clone();
                    if (litMat != null) on[i] = litMat;
                    off[i] = unlitMat;
                }
                if (on == null) continue;
                s.renderers.Add(r);
                s.lit.Add(on);
                s.unlit.Add(off);
            }
            return s;
        }

        public void Set(bool on)
        {
            IsLit = on;
            for (var i = 0; i < renderers.Count; i++)
                if (renderers[i] != null) renderers[i].sharedMaterials = on ? lit[i] : unlit[i];
        }
    }

    /// <summary>
    /// Random on/off flicker for a broken light (emissive switch, optional halo and point light). Call
    /// <see cref="Tick"/> every frame; it allocates nothing.
    /// </summary>
    public sealed class MfFlicker
    {
        public MfSwitch Switch;
        public GameObject Halo;
        public Light Light;
        public float LightOn;
        public bool Enabled = true;
        float t;
        bool on = true;

        public void Tick(float dt)
        {
            if (!Enabled) return;
            t -= dt;
            if (t > 0) return;
            on = !on;
            // Mostly on with short dropouts and the odd stutter.
            t = on ? (Random.value < 0.3f ? Random.Range(0.04f, 0.15f) : Random.Range(0.6f, 3.2f)) : Random.Range(0.03f, 0.22f);
            Apply(on);
        }

        public void Apply(bool lit)
        {
            Switch?.Set(lit);
            if (Halo != null) Halo.SetActive(lit);
            if (Light != null) Light.intensity = lit ? LightOn : LightOn * 0.08f;
        }
    }

    /// <summary>
    /// Level helpers shared by the Metro and Facility zones (ports of kit/Interior.ts room/glassWall, railing runs with
    /// Blender railing modules, exact prototype collider shapes, light-intensity conversion and small mesh helpers).
    /// All positions are prototype design space unless stated otherwise.
    /// </summary>
    public static class MfKit
    {
        // ------------------------------------------------------------------ rooms (port of Interior.room)

        /// <summary>
        /// Interior room with door openings (prototype Interior.room). Walls and slabs are kit boxes with the same
        /// colliders as the prototype; emissive ceiling panels become Lab_CeilingLight props. Returns the panel props.
        /// </summary>
        public static List<GameObject> Room(this LevelKit b, float x0, float z0, float x1, float z1, float h, MfRoomOptions o)
        {
            var panels = new List<GameObject>();
            var t = o.Thick;
            var y = o.Y;
            float cx = (x0 + x1) / 2, cz = (z0 + z1) / 2;
            if (!o.NoFloor) b.Box(cx, y - 0.25f, cz, x1 - x0, 0.5f, z1 - z0, o.Floor);
            if (o.Ceiling != null) b.Box(cx, y + h + 0.25f, cz, x1 - x0 + t * 2, 0.5f, z1 - z0 + t * 2, o.Ceiling, collide: false);
            var doors = new List<MfDoor>();
            foreach (var side in "nsew")
            {
                if (o.Skip != null && o.Skip.IndexOf(side) >= 0) continue;
                var along = side == 'n' || side == 's';
                var a0 = along ? x0 - t : z0 - t;
                var a1 = along ? x1 + t : z1 + t;
                var fix = side == 'n' ? z0 - t / 2 : side == 's' ? z1 + t / 2 : side == 'w' ? x0 - t / 2 : x1 + t / 2;
                doors.Clear();
                if (o.Doors != null) foreach (var d in o.Doors) if (d.Side == side) doors.Add(d);
                doors.Sort((p, q) => p.At.CompareTo(q.At));
                var cur = a0;
                foreach (var d in doors)
                {
                    float d0 = d.At - d.W / 2, d1 = d.At + d.W / 2;
                    WallSeg(b, along, fix, y, t, o.Wall, cur, d0, 0, h);
                    WallSeg(b, along, fix, y, t, o.Wall, d0, d1, d.H > 0 ? d.H : Mathf.Min(h, 3), h);
                    cur = d1;
                }
                WallSeg(b, along, fix, y, t, o.Wall, cur, a1, 0, h);
                if (o.Trim != null)
                {
                    // Baseboard trim on the inner face.
                    if (along) b.Box((a0 + a1) / 2, y + 0.08f, fix + (side == 'n' ? t / 2 + 0.02f : -t / 2 - 0.02f), a1 - a0, 0.16f, 0.04f, o.Trim, collide: false, shadow: false);
                    else b.Box(fix + (side == 'w' ? t / 2 + 0.02f : -t / 2 - 0.02f), y + 0.08f, (a0 + a1) / 2, 0.04f, 0.16f, a1 - a0, o.Trim, collide: false, shadow: false);
                }
            }
            if (o.Panels != null)
            {
                var prop = o.Panels == "emit_warm" ? "Lab_CeilingLight_Warm" : "Lab_CeilingLight";
                for (var x = x0 + 2.5f; x < x1 - 1; x += 5)
                for (var z = z0 + 2.5f; z < z1 - 1; z += 5)
                    panels.Add(b.Prop(prop, x, y + h, z, 0, 1, collide: false));
            }
            return panels;
        }

        static void WallSeg(LevelKit b, bool along, float fix, float y, float t, string mat, float s0, float s1, float yb, float yt)
        {
            if (s1 - s0 < 0.01f || yt - yb < 0.01f) return;
            float mid = (s0 + s1) / 2, len = s1 - s0;
            if (along) b.Box(mid, y + (yb + yt) / 2, fix, len, yt - yb, t, mat);
            else b.Box(fix, y + (yb + yt) / 2, mid, t, yt - yb, len, mat);
        }

        /// <summary>
        /// Glass partition with a metal frame (port of Interior.glassWall; same collider) plus the frosted privacy band of
        /// the Blender Glass_Partition module.
        /// </summary>
        public static void GlassWall(this LevelKit b, float x0, float z0, float x1, float z1, float h, float y = 0)
        {
            var len = Mathf.Sqrt((x1 - x0) * (x1 - x0) + (z1 - z0) * (z1 - z0));
            var yaw = Mathf.Atan2(x1 - x0, z1 - z0);
            float cx = (x0 + x1) / 2, cz = (z0 + z1) / 2;
            b.Box(cx, y + h / 2, cz, 0.05f, h, len, "glass", rotY: yaw);
            b.Box(cx, y + 0.05f, cz, 0.12f, 0.1f, len, "metal_dark", rotY: yaw, collide: false);
            b.Box(cx, y + h, cz, 0.12f, 0.1f, len, "metal_dark", rotY: yaw, collide: false);
            b.Box(cx, y + 1.1f, cz, 0.07f, 0.1f, len, "metal_painted_white", rotY: yaw, collide: false, shadow: false);
            var n = Mathf.Max(1, (int)Mathf.Floor(len / 2.5f + 0.5f));
            for (var i = 0; i <= n; i++)
            {
                var k = i / (float)n;
                b.Box(x0 + (x1 - x0) * k, y + h / 2, z0 + (z1 - z0) * k, 0.08f, h, 0.08f, "metal_dark", collide: false);
            }
        }

        /// <summary>
        /// Straight railing from Blender Railing_2m modules (2 m along local X, posts at -1 and 0) and an end post.
        /// Visual only unless `collide` (then an invisible character blocker like the prototype's railing()).
        /// </summary>
        public static void RailingRun(this LevelKit b, float x1, float z1, float x2, float z2, float y, bool collide = false)
        {
            float dx = x2 - x1, dz = z2 - z1;
            var len = Mathf.Sqrt(dx * dx + dz * dz);
            if (len < 0.1f) return;
            float ux = dx / len, uz = dz / len;
            var a = Mathf.Atan2(dx, dz);
            // Unity local +X of a prop with prototype yaw ψ points along prototype (-cos ψ, sin ψ); ψ = a + π/2 aligns it with the run.
            var yaw = a + Mathf.PI / 2;
            var n = Mathf.Max(1, Mathf.CeilToInt(len / 2f - 0.01f));
            var step = len / n;
            for (var i = 0; i < n; i++)
            {
                var s = step * i + 1f;
                b.Prop("Railing_2m", x1 + ux * s, y, z1 + uz * s, yaw, 1, collide: false);
            }
            b.Prop("Railing_Post", x2, y, z2, yaw, 1, collide: false);
            if (collide) b.Wall((x1 + x2) / 2, y + 0.6f, (z1 + z2) / 2, 0.15f, 1.2f, len, a);
        }

        // ------------------------------------------------------------------ colliders

        /// <summary>The hidden ramp collider of LevelKit.Stairs / prototype stairs(), without the step visuals.</summary>
        public static BoxCollider StairsCollider(this LevelKit b, float x, float y, float z, float yaw, float width, int steps, float rise, float run)
        {
            float dx = Mathf.Sin(yaw), dz = Mathf.Cos(yaw);
            float len = run * steps, height = rise * steps;
            var ang = Mathf.Atan2(height, len);
            var hyp = Mathf.Sqrt(len * len + height * height);
            return b.AddBoxCollider(V(x + dx * len / 2, y + height / 2 - 0.12f, z + dz * len / 2), new Vector3(width, 0.2f, hyp), RotYXZ(-ang, yaw, 0), CombatLayers.World);
        }

        /// <summary>Box collider in prototype space (centre, full size, three Euler XYZ radians) on the World layer.</summary>
        public static BoxCollider SolidBox(this LevelKit b, float x, float y, float z, float sx, float sy, float sz, float rotY = 0, float rotX = 0, float rotZ = 0) =>
            b.AddBoxCollider(V(x, y, z), new Vector3(sx, sy, sz), Rot(rotX, rotY, rotZ), CombatLayers.World);

        /// <summary>Vertical cylinder collider (prototype cyl() collider) without visuals.</summary>
        public static GameObject SolidCylinder(this LevelKit b, float x, float y, float z, float r, float h, int seg = 32)
        {
            var go = new GameObject("col_cyl") { layer = CombatLayers.World };
            go.transform.SetParent(b.Root, false);
            go.transform.localPosition = V(x, y, z);
            go.AddComponent<MeshCollider>().sharedMesh = FxMesh.Cylinder(r, r, h, seg, true);
            return go;
        }

        // ------------------------------------------------------------------ meshes & materials

        /// <summary>Flat quad facing prototype +Z rotated by yaw (screens, overlays). Parent defaults to the kit's props.</summary>
        public static GameObject Quad(this LevelKit b, string name, Transform parent, float x, float y, float z, float yaw, float w, float h, Material mat)
        {
            var go = b.MeshObject(name, LevelKit.QuadMesh, mat, new Vector3(x, y, z), YawQ(yaw) * Quaternion.Euler(0, 180, 0), false, parent);
            go.transform.localScale = new Vector3(w, h, 1);
            go.GetComponent<MeshRenderer>().receiveShadows = false;
            return go;
        }

        /// <summary>Quad in Unity local space of a prop (e.g. a dark overlay on a monitor's screen rect from the manifest).</summary>
        public static GameObject LocalQuad(Transform parent, Vector3 unityLocalCenter, float w, float h, Material mat)
        {
            var go = new GameObject("ScreenOverlay") { layer = CombatLayers.World };
            go.transform.SetParent(parent, false);
            go.transform.localPosition = unityLocalCenter;
            go.transform.localRotation = Quaternion.Euler(0, 180, 0);
            go.transform.localScale = new Vector3(w, h, 1);
            go.AddComponent<MeshFilter>().sharedMesh = LevelKit.QuadMesh;
            var r = go.AddComponent<MeshRenderer>();
            r.sharedMaterial = mat;
            r.shadowCastingMode = ShadowCastingMode.Off;
            return go;
        }

        /// <summary>Additive energy material (prototype MeshBasicMaterial, AdditiveBlending, transparent, double sided).</summary>
        public static Material Additive(uint color, float intensity, float alpha)
        {
            var m = FxMaterials.Particle(true, FxMaterials.White, true);
            var c = FxMaterials.Hdr(Hex(color), intensity);
            c.a = alpha;
            m.SetColor("_BaseColor", c);
            return m;
        }

        /// <summary>Unlit HDR material (prototype MeshBasicMaterial colour × k).</summary>
        public static Material Glow(uint color, float k, string name) => FxMaterials.Unlit(FxMaterials.Hdr(Hex(color), k), name);

        public static void SetGlow(Material m, uint color, float k)
        {
            if (m != null) m.SetColor("_BaseColor", FxMaterials.Hdr(Hex(color), k));
        }

        /// <summary>Material of a kit glow sprite/decal (unique per sprite, so it can be dimmed).</summary>
        public static Material SpriteMat(GameObject sprite) => sprite != null ? sprite.GetComponent<MeshRenderer>().sharedMaterial : null;

        public static void SetSprite(Material m, uint color, float intensity)
        {
            if (m != null) m.SetColor("_BaseColor", FxMaterials.Hdr(Hex(color), intensity));
        }

        // ------------------------------------------------------------------ lights

        /// <summary>
        /// Unity intensity per prototype intensity unit for a kit point light of the given range and decay (mirrors
        /// LevelKit.PointLight), so scripts can animate lights in prototype units.
        /// </summary>
        public static float LightUnit(LevelKit b, float range, float decay)
        {
            var comp = Mathf.Abs(decay - 2) < 0.01f || range <= 0 ? 1 : Mathf.Pow(Mathf.Max(1, range * 0.35f), 2 - decay);
            return b.LightScale * comp;
        }

        /// <summary>Transform for animated / scripted objects: kept out of the kit's static batching.</summary>
        public static Transform DynamicRoot(Transform zone)
        {
            var go = new GameObject("Dynamic") { layer = CombatLayers.World };
            go.transform.SetParent(zone, false);
            return go.transform;
        }
    }
}
