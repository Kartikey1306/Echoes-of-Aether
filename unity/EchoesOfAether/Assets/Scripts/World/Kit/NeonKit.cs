using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace EOA
{
    /// <summary>
    /// Night-city neon palette (sRGB). Cinematic, Cyberpunk-2077-like: warm reds, ambers, oranges and golds against
    /// electric cyan / teal, with magenta and pink only as occasional accents. <see cref="Pick(System.Random)"/> draws
    /// from the weighted city-wide mix; <see cref="Pick(System.Random, CityDistrict)"/> / <see cref="PickAt"/> from a
    /// district's own identity:
    ///   NeonMarket     red lanterns, amber, gold (warm market)
    ///   KowloonStacks  yellow-green fluorescent, yellow, orange
    ///   ArcologyGate   clean cyan and cool white corporate light with gold
    ///   CanalWard      teal over the water, warm amber windows, a little red
    ///   FoundryRow     orange sodium, amber, red sparks
    /// </summary>
    public static class Neon
    {
        public static readonly Color Red = ProtoSpace.Hex(0xff2a2e);
        public static readonly Color Crimson = ProtoSpace.Hex(0xe8163c);
        public static readonly Color Amber = ProtoSpace.Hex(0xffa020);
        public static readonly Color Orange = ProtoSpace.Hex(0xff6418);
        public static readonly Color Gold = ProtoSpace.Hex(0xffc85a);
        public static readonly Color Yellow = ProtoSpace.Hex(0xffe04a);
        public static readonly Color Lime = ProtoSpace.Hex(0xc4ff3a);
        public static readonly Color Fluoro = ProtoSpace.Hex(0xe2ffd2);
        public static readonly Color Cyan = ProtoSpace.Hex(0x22e4ff);
        public static readonly Color Teal = ProtoSpace.Hex(0x18f0c4);
        public static readonly Color IceWhite = ProtoSpace.Hex(0xd6f2ff);
        public static readonly Color WarmWhite = ProtoSpace.Hex(0xffe0b4);
        public static readonly Color Sodium = ProtoSpace.Hex(0xff8a24);
        public static readonly Color Blue = ProtoSpace.Hex(0x3d7bff);
        public static readonly Color Magenta = ProtoSpace.Hex(0xff2bd6);
        public static readonly Color Pink = ProtoSpace.Hex(0xff4f9a);
        public static readonly Color Violet = ProtoSpace.Hex(0x9b5cff);

        /// <summary>City-wide weighted mix (the old flat list was 3/7 magenta-pink-violet).</summary>
        static readonly (Color c, int w)[] CityMix =
        {
            (Red, 15), (Amber, 15), (Orange, 11), (Gold, 7), (Yellow, 7), (Cyan, 16), (Teal, 6), (WarmWhite, 7), (IceWhite, 5),
            (Lime, 3), (Magenta, 3), (Pink, 3), (Blue, 2),
        };

        static readonly (Color c, int w)[][] DistrictMix =
        {
            // NeonMarket
            new[] { (Red, 26), (Crimson, 8), (Amber, 22), (Gold, 14), (Orange, 10), (WarmWhite, 7), (Cyan, 8), (Magenta, 3), (Pink, 3) },
            // KowloonStacks
            new[] { (Lime, 18), (Yellow, 18), (Orange, 18), (Fluoro, 12), (Amber, 10), (Cyan, 10), (Red, 8), (Teal, 4), (Magenta, 2) },
            // ArcologyGate
            new[] { (IceWhite, 24), (Cyan, 26), (Gold, 18), (Teal, 8), (Amber, 7), (Blue, 4), (WarmWhite, 6), (Magenta, 2) },
            // CanalWard
            new[] { (Teal, 22), (Cyan, 14), (Amber, 18), (WarmWhite, 12), (Orange, 10), (Red, 10), (Yellow, 6), (Pink, 3) },
            // FoundryRow
            new[] { (Sodium, 24), (Orange, 22), (Amber, 20), (Red, 14), (Yellow, 8), (WarmWhite, 6), (Cyan, 4), (Teal, 2) },
        };

        static readonly int[] DistrictTotal = new int[5];
        static int cityTotal;

        public static readonly Color[] All = { Red, Amber, Orange, Gold, Yellow, Cyan, Teal, WarmWhite, Magenta };

        static Color Draw((Color c, int w)[] mix, ref int total, System.Random r)
        {
            if (total == 0) foreach (var e in mix) total += e.w;
            var k = r.Next(total);
            foreach (var e in mix)
            {
                if (k < e.w) return e.c;
                k -= e.w;
            }
            return mix[0].c;
        }

        /// <summary>Weighted city-wide neon colour.</summary>
        public static Color Pick(System.Random r) => Draw(CityMix, ref cityTotal, r);

        /// <summary>Weighted neon colour of a district's palette.</summary>
        public static Color Pick(System.Random r, CityDistrict d)
        {
            var i = Mathf.Clamp((int)d, 0, DistrictMix.Length - 1);
            return Draw(DistrictMix[i], ref DistrictTotal[i], r);
        }

        /// <summary>District palette at a Unity-space position (prototype x is mirrored).</summary>
        public static Color PickAt(System.Random r, Vector3 unityPos) => Pick(r, CityLayout.DistrictAt(-unityPos.x, unityPos.z));
    }

    /// <summary>
    /// Procedural cyberpunk signage built in Unity space: neon tube glyph signs (invented glyphs, never real words or
    /// brands), vertical blade signs, holographic advert panels and neon light strips. Tubes are merged into one mesh
    /// per sign; shared emissive materials per colour keep draw calls low (bloom provides the glow).
    /// </summary>
    public static class NeonKit
    {
        static readonly Dictionary<Color, Material> tubeMats = new();
        static Material backing;
        static Shader holoShader;

        // In-world adverts generated with DreamLayer (Resources/Art/DreamLayer/Ads; "*_tall" for portrait panels).
        static Texture2D[] adsWide, adsTall;

        /// <summary>
        /// About one holographic advert in three shows a DreamLayer image instead of a procedural layout, cropped to
        /// fill the panel (wide or tall image by the panel's shape). Deterministic per seed.
        /// </summary>
        static bool PickAd(Vector2 size, int seed, out Texture2D tex, out Vector2 scale, out Vector2 offset)
        {
            tex = null; scale = Vector2.one; offset = Vector2.zero;
            LoadAds();
            var h = (seed & 0x7fffffff) / 7;
            if (h % 3 != 0) return false;
            var aspect = size.x / Mathf.Max(0.01f, size.y);
            var set = aspect < 0.8f ? adsTall : adsWide;
            if (set.Length == 0) return false;
            tex = set[h / 3 % set.Length];
            CoverCrop(tex, aspect, out scale, out offset);
            return true;
        }

        static void LoadAds()
        {
            if (adsWide != null) return;
            var all = Resources.LoadAll<Texture2D>("Art/DreamLayer/Ads");
            adsTall = System.Array.FindAll(all, t => t.name.EndsWith("_tall"));
            adsWide = System.Array.FindAll(all, t => !t.name.EndsWith("_tall"));
        }

        /// <summary>Keep the image's proportions on a panel of the given aspect and trim the overflowing side.</summary>
        static void CoverCrop(Texture2D tex, float aspect, out Vector2 scale, out Vector2 offset)
        {
            var ia = tex.width / (float)tex.height;
            if (aspect > ia) { scale = new Vector2(1, ia / aspect); offset = new Vector2(0, (1 - scale.y) * 0.5f); }
            else { scale = new Vector2(aspect / ia, 1); offset = new Vector2((1 - scale.x) * 0.5f, 0); }
        }

        static void SetAd(Material m, Texture2D ad, Vector2 st, Vector2 so)
        {
            // Full-colour image: a neutral tint (the hologram colours would recolour it) at advert brightness.
            m.SetFloat("_UseTex", 1);
            m.SetTexture("_MainTex", ad);
            m.SetTextureScale("_MainTex", st);
            m.SetTextureOffset("_MainTex", so);
            m.SetColor("_Color", new Color(0.8f, 0.8f, 0.8f, 1));
        }

        /// <summary>Show a specific DreamLayer advert (by file name) on a hologram panel made by <see cref="HoloPanel"/>.</summary>
        public static void ShowAd(GameObject panel, string adName)
        {
            LoadAds();
            var ad = System.Array.Find(adsWide, t => t.name == adName) ?? System.Array.Find(adsTall, t => t.name == adName);
            var r = panel != null ? panel.GetComponent<MeshRenderer>() : null;
            if (ad == null || r == null || r.sharedMaterial == null || !r.sharedMaterial.HasProperty("_UseTex")) return;
            var s = panel.transform.localScale;
            CoverCrop(ad, s.x / Mathf.Max(0.01f, s.y), out var st, out var so);
            SetAd(r.sharedMaterial, ad, st, so);
        }

        public static Material TubeMaterial(Color c, float intensity = 5f)
        {
            if (tubeMats.TryGetValue(c, out var m) && m != null) return m;
            m = EnvMaterials.EmissiveInstance(c, intensity);
            m.name = "neon_tube";
            tubeMats[c] = m;
            return m;
        }

        static Material Backing
        {
            get
            {
                if (backing != null) return backing;
                backing = new Material(FxMaterials.LitShader) { name = "neon_backing" };
                backing.SetColor("_BaseColor", new Color(0.03f, 0.03f, 0.04f));
                backing.SetFloat("_Metallic", 0.6f);
                backing.SetFloat("_Smoothness", 0.7f);
                return backing;
            }
        }

        // ------------------------------------------------------------------ geometry helpers

        static void AddBox(List<Vector3> v, List<int> t, List<Vector3> n, Vector3 a, Vector3 b, float thick, Vector3 faceNormal)
        {
            var dir = b - a;
            var len = dir.magnitude;
            if (len < 1e-4f) return;
            var fwd = dir / len;
            var up = faceNormal.normalized;
            var side = Vector3.Cross(up, fwd).normalized * thick * 0.5f;
            var lift = up * thick * 0.5f;
            Vector3[] c =
            {
                a - side - lift, a + side - lift, a + side + lift, a - side + lift,
                b - side - lift, b + side - lift, b + side + lift, b - side + lift,
            };
            int[][] faces = { new[] { 0, 1, 2, 3 }, new[] { 5, 4, 7, 6 }, new[] { 4, 0, 3, 7 }, new[] { 1, 5, 6, 2 }, new[] { 3, 2, 6, 7 }, new[] { 4, 5, 1, 0 } };
            foreach (var f in faces)
            {
                var i0 = v.Count;
                var nn = Vector3.Cross(c[f[1]] - c[f[0]], c[f[2]] - c[f[0]]).normalized;
                for (var k = 0; k < 4; k++) { v.Add(c[f[k]]); n.Add(nn); }
                t.Add(i0); t.Add(i0 + 1); t.Add(i0 + 2); t.Add(i0); t.Add(i0 + 2); t.Add(i0 + 3);
            }
        }

        static Mesh Build(List<Vector3> v, List<int> t, List<Vector3> n)
        {
            var m = new Mesh { name = "neon" };
            if (v.Count > 65000) m.indexFormat = IndexFormat.UInt32;
            m.SetVertices(v); m.SetNormals(n); m.SetTriangles(t, 0);
            m.RecalculateBounds();
            return m;
        }

        static GameObject MeshGo(string name, Transform parent, Mesh mesh, Material mat, bool shadows = false)
        {
            var go = new GameObject(name);
            go.layer = CombatLayers.World;
            go.transform.SetParent(parent, false);
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var r = go.AddComponent<MeshRenderer>();
            r.sharedMaterial = mat;
            r.shadowCastingMode = shadows ? ShadowCastingMode.On : ShadowCastingMode.Off;
            r.receiveShadows = shadows;
            return go;
        }

        /// <summary>Strokes of one invented glyph on a 3×5 grid, in local units (x right, y up), seeded.</summary>
        static IEnumerable<(Vector2, Vector2)> GlyphStrokes(System.Random r)
        {
            var pts = new List<Vector2>();
            for (var y = 0; y < 5; y += 2) for (var x = 0; x < 3; x += 1) pts.Add(new Vector2(x * 0.5f, y * 0.25f));
            var count = 2 + r.Next(3);
            for (var i = 0; i < count; i++)
            {
                var a = pts[r.Next(pts.Count)];
                var b = pts[r.Next(pts.Count)];
                if ((a - b).sqrMagnitude < 0.01f) b = a + new Vector2(0.5f, 0);
                // Snap to orthogonal/diagonal strokes like real sign lettering.
                var d = b - a;
                if (Mathf.Abs(d.x) > 0.01f && Mathf.Abs(d.y) > 0.01f && r.NextDouble() < 0.6) b = new Vector2(b.x, a.y);
                yield return (a, b);
            }
        }

        /// <summary>
        /// Neon glyph sign: `glyphs` invented characters laid out horizontally (or vertically) with a dark backing
        /// board and an optional frame tube. Position/rotation in Unity space; the sign faces local +Z.
        /// </summary>
        public static GameObject GlyphSign(Transform parent, Vector3 pos, Quaternion rot, int glyphs, float glyphHeight, Color color, int seed, bool vertical = false, bool frame = true, bool flicker = false)
        {
            var r = new System.Random(seed);
            var root = new GameObject("NeonSign");
            root.layer = CombatLayers.World;
            root.transform.SetParent(parent, false);
            root.transform.SetPositionAndRotation(pos, rot);
            var v = new List<Vector3>(); var t = new List<int>(); var n = new List<Vector3>();
            var gw = glyphHeight * 0.62f;
            var pitch = vertical ? glyphHeight * 1.18f : gw * 1.3f;
            var thick = Mathf.Max(0.025f, glyphHeight * 0.06f);
            var totalW = vertical ? gw : glyphs * pitch;
            var totalH = vertical ? glyphs * pitch : glyphHeight;
            for (var g = 0; g < glyphs; g++)
            {
                var origin = vertical ? new Vector3(-gw / 2, totalH / 2 - (g + 1) * pitch + (pitch - glyphHeight) / 2, 0.06f)
                                      : new Vector3(-totalW / 2 + g * pitch + (pitch - gw) / 2, -glyphHeight / 2, 0.06f);
                foreach (var (a, b) in GlyphStrokes(r))
                {
                    var pa = origin + new Vector3(a.x * gw, a.y * glyphHeight, 0);
                    var pb = origin + new Vector3(b.x * gw, b.y * glyphHeight, 0);
                    AddBox(v, t, n, pa, pb, thick, Vector3.forward);
                }
            }
            if (frame)
            {
                var hw = totalW / 2 + glyphHeight * 0.25f; var hh = totalH / 2 + glyphHeight * 0.25f;
                var z = new Vector3(0, 0, 0.05f);
                AddBox(v, t, n, new Vector3(-hw, -hh) + z, new Vector3(hw, -hh) + z, thick * 0.7f, Vector3.forward);
                AddBox(v, t, n, new Vector3(hw, -hh) + z, new Vector3(hw, hh) + z, thick * 0.7f, Vector3.forward);
                AddBox(v, t, n, new Vector3(hw, hh) + z, new Vector3(-hw, hh) + z, thick * 0.7f, Vector3.forward);
                AddBox(v, t, n, new Vector3(-hw, hh) + z, new Vector3(-hw, -hh) + z, thick * 0.7f, Vector3.forward);
            }
            var mat = flicker ? EnvMaterials.EmissiveInstance(color, 5f) : TubeMaterial(color);
            var tubes = MeshGo("Tubes", root.transform, Build(v, t, n), mat);
            if (flicker) tubes.AddComponent<NeonFlicker>().Init(mat, color, 5f, seed);
            // Backing board.
            var board = GameObject.CreatePrimitive(PrimitiveType.Cube);
            Object.Destroy(board.GetComponent<Collider>());
            board.layer = CombatLayers.World;
            board.transform.SetParent(root.transform, false);
            board.transform.localScale = new Vector3(totalW + glyphHeight * 0.7f, totalH + glyphHeight * 0.7f, 0.08f);
            board.transform.localPosition = new Vector3(0, 0, -0.02f);
            board.GetComponent<Renderer>().sharedMaterial = Backing;
            return root;
        }

        /// <summary>Vertical blade sign sticking out from a wall (faces both sides along local ±X).</summary>
        public static GameObject BladeSign(Transform parent, Vector3 wallPos, Quaternion wallRot, float height, Color color, Color accent, int seed)
        {
            var root = new GameObject("BladeSign");
            root.layer = CombatLayers.World;
            root.transform.SetParent(parent, false);
            root.transform.SetPositionAndRotation(wallPos, wallRot);
            var depth = 0.9f;
            var body = GameObject.CreatePrimitive(PrimitiveType.Cube);
            Object.Destroy(body.GetComponent<Collider>());
            body.layer = CombatLayers.World;
            body.transform.SetParent(root.transform, false);
            body.transform.localScale = new Vector3(0.12f, height, depth);
            body.transform.localPosition = new Vector3(0, 0, depth / 2 + 0.05f);
            body.GetComponent<Renderer>().sharedMaterial = Backing;
            var glyphs = Mathf.Max(2, Mathf.RoundToInt(height / 0.9f));
            for (var side = -1; side <= 1; side += 2)
                GlyphSign(root.transform, root.transform.TransformPoint(new Vector3(0.07f * side, 0, depth / 2 + 0.05f)),
                    wallRot * Quaternion.Euler(0, 90 * side, 0), glyphs, Mathf.Min(0.7f, depth * 0.55f), side < 0 ? color : accent, seed + side, vertical: true, frame: true);
            // Edge tube along the outer edge.
            var v = new List<Vector3>(); var t = new List<int>(); var n = new List<Vector3>();
            AddBox(v, t, n, new Vector3(0, -height / 2, depth + 0.07f), new Vector3(0, height / 2, depth + 0.07f), 0.05f, Vector3.right);
            MeshGo("Edge", root.transform, Build(v, t, n), TubeMaterial(accent));
            return root;
        }

        /// <summary>
        /// Holographic advert panel (EOA/Hologram) of the given size, facing local -Z and +Z. Six procedural layouts
        /// (glyph columns, emblem rings, equaliser, waveforms, abstract logo, headline + ticker): callers passing the
        /// classic 0..2 get half their panels moved to the newer layouts by seed. fogScale &lt; 1 lets distant skyline
        /// adverts glow through the haze.
        /// </summary>
        public static GameObject HoloPanel(Transform parent, Vector3 pos, Quaternion rot, Vector2 size, Color a, Color b, int mode, int seed, float intensity = 2.2f, float fogScale = 1f)
        {
            if (holoShader == null)
            {
                var tmpl = Resources.Load<Material>("Env/Hologram");
                holoShader = tmpl != null ? tmpl.shader : Shader.Find("EOA/Hologram");
            }
            var layout = mode >= 3 ? mode % 6 : (mode + ((seed & 0x7fffffff) % 2) * 3) % 6;
            var go = new GameObject("HoloAd");
            go.layer = CombatLayers.World;
            go.transform.SetParent(parent, false);
            go.transform.SetPositionAndRotation(pos, rot);
            go.transform.localScale = new Vector3(size.x, size.y, 1);
            go.AddComponent<MeshFilter>().sharedMesh = LevelKit.QuadMesh;
            var r = go.AddComponent<MeshRenderer>();
            Material m;
            if (holoShader != null)
            {
                m = new Material(holoShader) { name = "holo_ad" };
                m.SetColor("_Color", HoloLevel(a));
                m.SetColor("_Color2", HoloLevel(b));
                m.SetFloat("_Mode", layout);
                m.SetFloat("_Seed", seed % 997);
                m.SetFloat("_Intensity", intensity);
                m.SetFloat("_Aspect", Mathf.Max(0.2f, size.x / Mathf.Max(0.01f, size.y)));
                m.SetFloat("_FogScale", fogScale);
                if (PickAd(size, seed, out var ad, out var st, out var so)) SetAd(m, ad, st, so);
            }
            else
            {
                m = FxMaterials.Particle(true, FxMaterials.Glow, true);
                m.SetColor("_BaseColor", FxMaterials.Hdr(a, intensity));
            }
            r.sharedMaterial = m;
            r.shadowCastingMode = ShadowCastingMode.Off;
            r.receiveShadows = false;
            return go;
        }

        /// <summary>
        /// Hologram colours at a common luminance (that of the old magenta adverts): yellow, amber and cyan carry two to
        /// three times the luminance of red / magenta at the same intensity, so big adverts in those hues turned into
        /// pale glowing slabs once tonemapped.
        /// </summary>
        static Color HoloLevel(Color srgb)
        {
            var c = srgb.linear;
            var l = c.r * 0.2126f + c.g * 0.7152f + c.b * 0.0722f;
            var k = Mathf.Clamp(0.28f / Mathf.Max(l, 1e-3f), 0.3f, 1.25f);
            var g = (c * k).gamma;
            g.a = srgb.a;
            return g;
        }

        /// <summary>Straight neon strip between two Unity-space points (building edges, canopies, railings).</summary>
        public static GameObject Strip(Transform parent, Vector3 a, Vector3 b, Color color, float thickness = 0.06f, Vector3? normal = null)
        {
            var v = new List<Vector3>(); var t = new List<int>(); var n = new List<Vector3>();
            var nn = normal ?? Vector3.up;
            if (Mathf.Abs(Vector3.Dot(nn.normalized, (b - a).normalized)) > 0.95f) nn = Vector3.forward;
            AddBox(v, t, n, a, b, thickness, nn);
            return MeshGo("NeonStrip", parent, Build(v, t, n), TubeMaterial(color));
        }
    }

    /// <summary>Occasional neon flicker (dying tube): drops emission briefly at random intervals.</summary>
    public sealed class NeonFlicker : MonoBehaviour
    {
        Material mat;
        Color color;
        float intensity, next, offT;
        System.Random r;

        public void Init(Material m, Color c, float i, int seed)
        {
            mat = m; color = c; intensity = i; r = new System.Random(seed);
            next = Time.time + (float)r.NextDouble() * 4f;
        }

        void Update()
        {
            if (mat == null) return;
            if (Time.time >= next)
            {
                offT = 0.04f + (float)r.NextDouble() * 0.18f;
                next = Time.time + 0.6f + (float)r.NextDouble() * 5f;
            }
            if (offT > 0)
            {
                offT -= Time.deltaTime;
                EnvMaterials.SetEmission(mat, color, offT > 0 ? intensity * 0.08f : intensity);
            }
        }
    }
}
