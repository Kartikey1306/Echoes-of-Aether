using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace EOA
{
    /// <summary>
    /// Cyberpunk city layer for outdoor zones (procedural, seeded, Unity space):
    ///   • <see cref="DressFacades"/>: neon glyph shop signs, blade signs, holo adverts and edge strips on every
    ///     building face that looks onto the play area, plus coloured light spill on the wet ground.
    ///   • <see cref="Skyline"/>: a ring of distant megatowers with procedural lit windows (EOA/CityLights), roof beacons
    ///     and giant holo billboards.
    ///   • <see cref="SkyTraffic"/>: flying vehicles with head/tail lights circulating on elevated lanes.
    /// </summary>
    public static class CyberCity
    {
        /// <summary>
        /// Dress building faces (World-layer box colliders taller than 7 m) that face `focus` within `radius`. Signs are
        /// registered with the <see cref="NeonField"/> (rain and mist catch their colour) and shop signs get a soft light
        /// spill volume; pass `fx` to collect those volumes in a caller's batch (otherwise they are merged here).
        /// </summary>
        public static int DressFacades(LevelKit kit, Vector3 focus, float radius, int seed, float density = 1f, int maxElements = 160, float groundY = 0, FxBatch fx = null)
        {
            var r = new System.Random(seed);
            var fr = new System.Random(seed ^ 0x2f6b31);
            var parent = new GameObject("CyberDressing").transform;
            parent.SetParent(kit.FxRoot, false);
            var ownFx = fx == null;
            fx ??= new FxBatch(64f);
            var count = 0;
            foreach (var bc in kit.WorldBoxes())
            {
                var t = bc.transform;
                var size = Vector3.Scale(bc.size, t.lossyScale);
                if (size.y < 7f || (size.x < 4f && size.z < 4f)) continue;
                var c = t.TransformPoint(bc.center);
                var bottom = Mathf.Max(c.y - size.y / 2, groundY);
                var top = c.y + size.y / 2;
                if (top - bottom < 6f) continue;
                for (var f = 0; f < 4; f++)
                {
                    var axisX = f < 2;
                    var normal = (axisX ? t.right : t.forward) * (f % 2 == 0 ? 1 : -1);
                    var along = axisX ? t.forward : t.right;
                    var half = axisX ? size.x / 2 : size.z / 2;
                    var width = axisX ? size.z : size.x;
                    var face = c + normal * half;
                    var toFocus = focus - face; toFocus.y = 0;
                    if (Vector3.Dot(normal, toFocus) <= 0 || toFocus.magnitude > radius || width < 3f) continue;
                    var slots = Mathf.Max(1, Mathf.RoundToInt(width / 7f * density + (float)r.NextDouble()));
                    for (var s = 0; s < slots && count < maxElements; s++)
                    {
                        var u = ((s + 0.5f) / slots - 0.5f) * (width - 3f) + ((float)r.NextDouble() - 0.5f) * 1.5f;
                        var basePos = new Vector3(face.x, 0, face.z) + along * u;
                        var rot = Quaternion.LookRotation(normal, Vector3.up);
                        var roll = r.NextDouble();
                        // district identity (NeonMarket red/amber lanterns, Kowloon fluorescent, Arcology cyan/white...)
                        var col = Neon.PickAt(r, basePos);
                        if (roll < 0.42)
                        {
                            // Shop sign above the ground floor + light spill on the street.
                            var h = bottom + 3.4f + (float)r.NextDouble() * 1.6f;
                            var gh = 0.55f + (float)r.NextDouble() * 0.45f;
                            var glyphs = 3 + r.Next(4);
                            var signPos = basePos + Vector3.up * h + normal * 0.12f;
                            NeonKit.GlyphSign(parent, signPos, rot, glyphs, gh, col, r.Next(), flicker: r.NextDouble() < 0.18);
                            NeonField.Add(signPos + normal * 0.6f, col, 1.4f, 7f);
                            if (fr.NextDouble() < 0.55) CityFx.SignVolume(fx, signPos - Vector3.up * gh * 0.5f, normal, glyphs * gh * 0.8f, groundY, col);
                            var spill = basePos + normal * 2.2f;
                            kit.GlowDecal(-spill.x, groundY + 0.04f, spill.z, 5.5f, ToHex(col), 0.32f);
                        }
                        else if (roll < 0.68 && top - bottom > 10)
                        {
                            var h = bottom + 5f + (float)r.NextDouble() * Mathf.Min(10f, top - bottom - 9f);
                            NeonKit.BladeSign(parent, basePos + Vector3.up * h + normal * 0.05f, rot, 2.5f + (float)r.NextDouble() * 3.5f, col, Neon.PickAt(r, basePos), r.Next());
                            NeonField.Add(basePos + Vector3.up * h + normal * 0.6f, col, 1.2f, 6f);
                        }
                        else if (roll < 0.9 && top - bottom > 12)
                        {
                            var w = Mathf.Min(width - 2f, 4f + (float)r.NextDouble() * 6f);
                            var hh = w * (0.55f + (float)r.NextDouble() * 0.35f);
                            var y = Mathf.Min(top - hh / 2 - 1.5f, bottom + 8f + (float)r.NextDouble() * (top - bottom - 10f));
                            NeonKit.HoloPanel(parent, basePos + Vector3.up * y + normal * 0.35f, rot, new Vector2(w, hh), col, Neon.PickAt(r, basePos), r.Next(3), r.Next(), 1.6f + (float)r.NextDouble());
                            NeonField.Add(basePos + Vector3.up * y + normal * 1.5f, col, 1.0f, Mathf.Max(6f, w));
                        }
                        else
                        {
                            // Vertical neon strip up the facade.
                            var p = basePos + normal * 0.08f;
                            NeonKit.Strip(parent, p + Vector3.up * (bottom + 2.5f), p + Vector3.up * (top - 0.5f), col, 0.07f, normal);
                        }
                        count++;
                    }
                    // Weathering decals on the facade (grime / rust streaks / posters) near street level.
                    if (count < maxElements && r.NextDouble() < 0.7)
                    {
                        var wall = WallDecals;
                        if (wall.Length > 0)
                        {
                            var u = ((float)r.NextDouble() - 0.5f) * (width - 2f);
                            var p = new Vector3(face.x, bottom + 1.2f + (float)r.NextDouble() * 4f, face.z) + along * u;
                            DecalKit.Place(parent, wall[r.Next(wall.Length)], p, normal, 0, 0.8f + (float)r.NextDouble() * 0.8f);
                        }
                    }
                    // Neon cornice along the top edge of tall faces.
                    if (top - bottom > 14 && r.NextDouble() < 0.5 && count < maxElements)
                    {
                        var a = face + Vector3.up * (top - c.y - 0.6f) - along * (width / 2 - 0.2f) + normal * 0.06f;
                        var b = face + Vector3.up * (top - c.y - 0.6f) + along * (width / 2 - 0.2f) + normal * 0.06f;
                        a.y = top - 0.6f; b.y = top - 0.6f;
                        NeonKit.Strip(parent, a, b, Neon.PickAt(r, face), 0.08f, normal);
                        count++;
                    }
                }
            }
            if (ownFx) fx.Finish(parent, "sign_fx", CityFx.FxLayer, null);
            return count;
        }

        static string[] wallDecals;
        static string[] WallDecals => wallDecals ??= System.Linq.Enumerable.ToArray(System.Linq.Enumerable.Select(System.Linq.Enumerable.Where(EnvProps.Decals, d => d.Projection == "wall"), d => d.Name));

        static uint ToHex(Color c) => ((uint)Mathf.RoundToInt(c.r * 255) << 16) | ((uint)Mathf.RoundToInt(c.g * 255) << 8) | (uint)Mathf.RoundToInt(c.b * 255);

        // ------------------------------------------------------------------ skyline

        static Material[] skylineMats;

        /// <summary>
        /// EOA/CityLights materials for the skyline: 0 near band, 1 mega towers, 2 megastructures, 3 dark (antennas,
        /// spires). Tower identity comes from UV2.x (_Skyline = 1); interior mapping is off at these distances and each
        /// band keeps a little more of its window glow through the fog than its facade (layered depth).
        /// </summary>
        static Material SkylineMaterial(int band)
        {
            if (skylineMats == null || skylineMats[0] == null)
            {
                var t = Resources.Load<Material>("Env/CityLights");
                var sh = t != null ? t.shader : Shader.Find("EOA/CityLights");
                skylineMats = new Material[4];
                for (var k = 0; k < 4; k++)
                {
                    Material m;
                    if (sh != null && sh.isSupported)
                    {
                        m = t != null ? new Material(t) : new Material(sh);
                        var b = Mathf.Min(k, 2);
                        m.SetFloat("_Skyline", 1);
                        m.SetFloat("_Seed", 17 + k * 31);
                        m.SetFloat("_Detail", 1);
                        m.SetFloat("_Lit", b == 0 ? 0.46f : b == 1 ? 0.42f : 0.34f);
                        m.SetVector("_Cell", b == 0 ? new Vector4(2.2f, 3.6f, 0, 0) : b == 1 ? new Vector4(2.8f, 4.2f, 0, 0) : new Vector4(3.4f, 5f, 0, 0));
                        m.SetFloat("_Bands", b == 0 ? 46 : b == 1 ? 70 : 1000);
                        m.SetFloat("_FogKeep", b == 0 ? 0.8f : b == 1 ? 0.7f : 0.6f);
                        // atmospheric perspective: each band further out sinks further into the haze (their windows still glow
                        // through, _FogKeep), so the skyline recedes in layers instead of reading as a flat backdrop
                        m.SetFloat("_FogScale", b == 0 ? 0.5f : b == 1 ? 0.42f : 0.36f);
                        m.SetFloat("_Brightness", k == 3 ? 0f : b == 0 ? 1.35f : b == 1 ? 1.15f : 0.95f);
                        m.SetFloat("_Media", k == 3 ? 0f : b == 0 ? 0.16f : b == 1 ? 0.1f : 0.05f);
                        m.SetFloat("_Strips", k == 3 ? 0f : b == 0 ? 0.18f : 0.1f);
                        m.SetFloat("_Glass", 0.35f);
                        if (k == 3) m.SetFloat("_Bands", 1000);
                    }
                    else
                    {
                        m = new Material(FxMaterials.UnlitShader);
                        m.SetColor("_BaseColor", new Color(0.05f, 0.05f, 0.08f));
                    }
                    m.name = "skyline_" + k;
                    skylineMats[k] = m;
                }
            }
            return skylineMats[Mathf.Clamp(band, 0, 3)];
        }

        /// <summary>Skyline geometry accumulated per band and 45° sector (merged meshes, tower id in UV2.x).</summary>
        sealed class SkyMeshes
        {
            sealed class Part { public readonly List<Vector3> V = new(), N = new(); public readonly List<Vector2> UV = new(); public readonly List<Vector4> UV2 = new(); public readonly List<int> T = new(); }
            readonly Dictionary<(int, int), Part> parts = new();
            readonly Vector3 center;

            public SkyMeshes(Vector3 c) => center = c;

            Part Get(int mat, Vector3 p)
            {
                var a = Mathf.Atan2(p.x - center.x, p.z - center.z);
                var sector = Mathf.FloorToInt((a + Mathf.PI) / (Mathf.PI / 4)) & 7;
                var key = (mat, sector);
                if (!parts.TryGetValue(key, out var part)) parts[key] = part = new Part();
                return part;
            }

            /// <summary>Prism with `sides` faces (4 = box w x d), base centre c at y0, height h; u from u0, v from v0.</summary>
            public void Prism(int mat, Vector3 c, float w, float d, float y0, float h, float yaw, int sides, float u0, float v0, float id)
            {
                var p = Get(mat, c);
                var corners = new Vector3[sides];
                var q = Quaternion.Euler(0, yaw, 0);
                for (var i = 0; i < sides; i++)
                {
                    Vector3 local;
                    if (sides == 4) local = i switch { 0 => new Vector3(-w / 2, 0, -d / 2), 1 => new Vector3(w / 2, 0, -d / 2), 2 => new Vector3(w / 2, 0, d / 2), _ => new Vector3(-w / 2, 0, d / 2) };
                    else
                    {
                        var ang = (i + 0.5f) / sides * Mathf.PI * 2;
                        local = new Vector3(Mathf.Cos(ang) * w / 2, 0, Mathf.Sin(ang) * d / 2);
                    }
                    corners[i] = c + q * local;
                    corners[i].y = y0;
                }
                var u = u0;
                for (var i = 0; i < sides; i++)
                {
                    var a = corners[i]; var b = corners[(i + 1) % sides];
                    var len = Vector3.Distance(a, b);
                    var n = Vector3.Cross(Vector3.up, b - a).normalized;
                    var k = p.V.Count;
                    p.V.Add(a); p.V.Add(b); p.V.Add(b + Vector3.up * h); p.V.Add(a + Vector3.up * h);
                    for (var j = 0; j < 4; j++) { p.N.Add(n); p.UV2.Add(new Vector4(id, 0, 0, 0)); }
                    p.UV.Add(new Vector2(u, v0)); p.UV.Add(new Vector2(u + len, v0)); p.UV.Add(new Vector2(u + len, v0 + h)); p.UV.Add(new Vector2(u, v0 + h));
                    p.T.Add(k); p.T.Add(k + 2); p.T.Add(k + 1); p.T.Add(k); p.T.Add(k + 3); p.T.Add(k + 2);
                    u += len;
                }
                // Roof cap (fan).
                var top = p.V.Count;
                foreach (var cc in corners) { p.V.Add(cc + Vector3.up * h); p.N.Add(Vector3.up); p.UV.Add(Vector2.zero); p.UV2.Add(new Vector4(id, 0, 0, 0)); }
                for (var i = 1; i < sides - 1; i++) { p.T.Add(top); p.T.Add(top + i + 1); p.T.Add(top + i); }
            }

            public int Finish(Transform parent, int layer)
            {
                var n = 0;
                foreach (var kv in parts)
                {
                    var part = kv.Value;
                    var mesh = new Mesh { name = "skyline" };
                    if (part.V.Count > 65000) mesh.indexFormat = IndexFormat.UInt32;
                    mesh.SetVertices(part.V); mesh.SetNormals(part.N); mesh.SetUVs(0, part.UV); mesh.SetUVs(1, part.UV2);
                    mesh.SetTriangles(part.T, 0);
                    mesh.RecalculateBounds();
                    mesh.UploadMeshData(true);
                    var go = new GameObject("SkylineBand" + kv.Key.Item1) { layer = layer };
                    go.transform.SetParent(parent, false);
                    go.AddComponent<MeshFilter>().sharedMesh = mesh;
                    var r = go.AddComponent<MeshRenderer>();
                    r.sharedMaterial = SkylineMaterial(kv.Key.Item1);
                    r.shadowCastingMode = ShadowCastingMode.Off;
                    r.receiveShadows = false;
                    r.lightProbeUsage = LightProbeUsage.Off;
                    r.reflectionProbeUsage = ReflectionProbeUsage.Off;
                    n++;
                }
                return n;
            }
        }

        static readonly Color BeaconRed = new(1f, 0.16f, 0.12f);

        /// <summary>
        /// Layered skyline around `center` (Unity space): a detailed band of towers between innerRadius and outerRadius
        /// (setbacks, slabs, octagonal towers, twins with skybridges, crowns and antennas, LED corner strips, giant holo
        /// billboards), a band of mega towers beyond, and a band of megastructure silhouettes (stepped arcologies, spires,
        /// wall slabs) on the horizon, with glowing haze curtains between the layers and blinking aircraft beacons.
        /// Drawn on <see cref="CityFx.SkylineLayer"/> (visible to the far clip plane), merged per band and sector.
        /// </summary>
        public static void Skyline(LevelKit kit, Vector3 center, float innerRadius, float outerRadius, int count, int seed, float baseY = 0)
        {
            var r = new System.Random(seed);
            float Rnd() => (float)r.NextDouble();
            var parent = new GameObject("Skyline").transform;
            parent.SetParent(kit.FxRoot, false);
            var meshes = new SkyMeshes(center);
            var fx = new FxBatch(500f);
            var y0 = baseY - 6f;

            void Beacons(Vector3 p, float w, float d, float yaw, float dist, bool corners)
            {
                var half = 1.2f + dist * 0.0028f;
                if (!corners) { CityFx.Beacon(fx, p, half, BeaconRed, Rnd()); return; }
                var q = Quaternion.Euler(0, yaw, 0);
                var ph = Rnd();
                foreach (var s in new[] { new Vector3(-1, 0, -1), new Vector3(1, 0, 1) })
                    CityFx.Beacon(fx, p + q * new Vector3(s.x * w * 0.45f, 0, s.z * d * 0.45f), half, BeaconRed, ph);
            }

            void CornerStrips(Vector3 c, float w, float d, float yaw, float yA, float h, Color col)
            {
                var q = Quaternion.Euler(0, yaw, 0);
                var ph = Rnd();
                foreach (var s in new[] { new Vector3(-1, 0, -1), new Vector3(1, 0, -1), new Vector3(1, 0, 1), new Vector3(-1, 0, 1) })
                    CityFx.Strip(fx, c + q * new Vector3(s.x * (w / 2 + 0.3f), 0, s.z * (d / 2 + 0.3f)) + Vector3.up * yA, h, 0.9f, col, ph, 2.2f);
            }

            /// Tower made of stacked sections; returns the roof top position.
            Vector3 Tower(int band, Vector3 c, float w, float d, float h, float yaw, int kind, float dist)
            {
                var id = Rnd();
                var u0 = Rnd() * 500f;
                var mat = band;
                var top = c + Vector3.up * (y0 + h);
                switch (kind)
                {
                    case 0: // setbacks
                    {
                        var tiers = 2 + r.Next(2);
                        float y = y0, cw = w, cd = d, v = 0;
                        for (var t = 0; t < tiers; t++)
                        {
                            var th = t == tiers - 1 ? h - (y - y0) : h * (0.45f + Rnd() * 0.2f) / (t + 1);
                            meshes.Prism(mat, c, cw, cd, y, th, yaw, 4, u0, v, id);
                            y += th; v += th;
                            cw *= 0.7f + Rnd() * 0.15f; cd *= 0.7f + Rnd() * 0.15f;
                        }
                        top = c + Vector3.up * y;
                        break;
                    }
                    case 1: // slab
                        meshes.Prism(mat, c, w * 1.5f, d * 0.45f, y0, h, yaw, 4, u0, 0, id);
                        break;
                    case 2: // octagonal tower with a crown ring
                        meshes.Prism(mat, c, w, w, y0, h, yaw, 8, u0, 0, id);
                        meshes.Prism(mat, c, w * 0.75f, w * 0.75f, y0 + h, h * 0.08f, yaw, 8, u0, h, id);
                        top = c + Vector3.up * (y0 + h * 1.08f);
                        break;
                    case 3: // twin towers with a skybridge
                    {
                        var q = Quaternion.Euler(0, yaw, 0);
                        var off = q * new Vector3(w * 0.55f, 0, 0);
                        var h2 = h * (0.75f + Rnd() * 0.2f);
                        meshes.Prism(mat, c - off, w * 0.7f, d, y0, h, yaw, 4, u0, 0, id);
                        meshes.Prism(mat, c + off, w * 0.7f, d, y0, h2, yaw, 4, u0 + 300, 0, id + 0.37f);
                        meshes.Prism(mat, c, w * 0.5f, d * 0.35f, y0 + h2 * 0.62f, 7f, yaw, 4, u0 + 150, h2 * 0.62f, id + 0.71f);
                        top = c - off + Vector3.up * (y0 + h);
                        break;
                    }
                    default:
                        meshes.Prism(mat, c, w, d, y0, h, yaw, 4, u0, 0, id);
                        break;
                }
                // Crown and antenna.
                if (Rnd() < 0.55f)
                {
                    var ch = 6f + Rnd() * 14f;
                    meshes.Prism(3, top - Vector3.up * 0.1f, w * 0.35f, d * 0.35f, top.y - 0.1f, ch, yaw, 4, u0, 0, id);
                    top += Vector3.up * ch;
                    if (Rnd() < 0.7f)
                    {
                        var ah = 12f + Rnd() * (band == 0 ? 30f : 60f);
                        meshes.Prism(3, top, 1.2f, 1.2f, top.y, ah, yaw, 4, 0, 0, id);
                        top += Vector3.up * ah;
                        Beacons(top + Vector3.up * 0.8f, 0, 0, yaw, dist, false);
                    }
                    else Beacons(top + Vector3.up * 0.6f, w * 0.35f, d * 0.35f, yaw, dist, true);
                }
                else Beacons(top + Vector3.up * 0.6f, kind == 1 ? w * 1.5f : w, kind == 1 ? d * 0.45f : d, yaw, dist, true);
                return top;
            }

            // ---------------------------------------------------------------- band 0: detailed towers
            for (var i = 0; i < count; i++)
            {
                var a = (i + Rnd() * 0.7f) / count * Mathf.PI * 2;
                var dist = Mathf.Lerp(innerRadius, outerRadius, Rnd());
                var w = 18f + Rnd() * 36f;
                var d = 18f + Rnd() * 30f;
                var h = 70f + Rnd() * (Rnd() < 0.25f ? 300f : 170f);
                var c = center + new Vector3(Mathf.Sin(a) * dist, 0, Mathf.Cos(a) * dist);
                var yaw = Rnd() * 90f;
                var roll = Rnd();
                var kind = roll < 0.38f ? 0 : roll < 0.58f ? 1 : roll < 0.74f ? 2 : roll < 0.86f ? 3 : 4;
                Tower(0, c, w, d, h, yaw, kind, dist);
                if (Rnd() < 0.28f && kind != 2) CornerStrips(c, kind == 1 ? w * 1.5f : w, kind == 1 ? d * 0.45f : d, yaw, y0 + h * 0.25f, h * 0.7f, Neon.PickAt(r, c));
                // Giant holo billboard on some towers, facing the city centre.
                if (Rnd() < 0.38f)
                {
                    var toC = center - c; toC.y = 0; toC.Normalize();
                    var bw = Mathf.Min(w, d) * (0.8f + Rnd() * 0.5f);
                    var bpos = c + toC * (Mathf.Max(w, d) * 0.5f + 2f) + Vector3.up * (y0 + h * (0.4f + Rnd() * 0.35f));
                    var holo = NeonKit.HoloPanel(parent, bpos, Quaternion.LookRotation(toC), new Vector2(bw, bw * (0.5f + Rnd() * 0.5f)), Neon.PickAt(r, c), Neon.PickAt(r, c), r.Next(6), r.Next(), 3.2f, 0.3f);
                    holo.layer = CityFx.SkylineLayer;
                }
            }

            // ---------------------------------------------------------------- band 1: mega towers
            var megaCount = Mathf.RoundToInt(count * 0.8f);
            for (var i = 0; i < megaCount; i++)
            {
                var a = (i + Rnd() * 0.8f) / megaCount * Mathf.PI * 2;
                var dist = Mathf.Lerp(outerRadius * 1.3f, outerRadius * 1.75f, Rnd());
                var w = 36f + Rnd() * 50f;
                var d = 30f + Rnd() * 40f;
                var h = 170f + Rnd() * 300f;
                var c = center + new Vector3(Mathf.Sin(a) * dist, 0, Mathf.Cos(a) * dist);
                var roll = Rnd();
                Tower(1, c, w, d, h, Rnd() * 90f, roll < 0.5f ? 0 : roll < 0.7f ? 2 : roll < 0.9f ? 1 : 3, dist);
                if (Rnd() < 0.12f) CornerStrips(c, w, d, 0, y0 + h * 0.3f, h * 0.6f, Neon.PickAt(r, c));
            }

            // ---------------------------------------------------------------- band 2: megastructures on the horizon
            var farCount = Mathf.Max(8, Mathf.RoundToInt(count * 0.4f));
            for (var i = 0; i < farCount; i++)
            {
                var a = (i + Rnd() * 0.6f) / farCount * Mathf.PI * 2;
                var dist = Mathf.Lerp(outerRadius * 1.95f, outerRadius * 2.5f, Rnd());
                var c = center + new Vector3(Mathf.Sin(a) * dist, 0, Mathf.Cos(a) * dist);
                var yaw = a * Mathf.Rad2Deg + (Rnd() - 0.5f) * 30f;
                var id = Rnd();
                var roll = Rnd();
                if (roll < 0.4f)
                {
                    // Stepped arcology: wide tiers shrinking to a crown.
                    float w = 160f + Rnd() * 140f, d = 120f + Rnd() * 80f, y = y0, v = 0;
                    var tiers = 4 + r.Next(3);
                    for (var t = 0; t < tiers; t++)
                    {
                        var th = 50f + Rnd() * 40f;
                        meshes.Prism(2, c, w, d, y, th, yaw, 4, Rnd() * 500f, v, id);
                        y += th; v += th; w *= 0.74f; d *= 0.74f;
                    }
                    Beacons(c + Vector3.up * (y + 1), w, d, yaw, dist, true);
                }
                else if (roll < 0.7f)
                {
                    // Spire: podium, tall octagonal shaft, needle.
                    var w = 70f + Rnd() * 50f;
                    var h = 380f + Rnd() * 320f;
                    meshes.Prism(2, c, w * 2f, w * 1.6f, y0, 70f, yaw, 4, 0, 0, id);
                    meshes.Prism(2, c, w, w, y0 + 70, h, yaw, 8, 0, 70, id);
                    meshes.Prism(3, c, 6f, 6f, y0 + 70 + h, 80f + Rnd() * 60f, yaw, 4, 0, 0, id);
                    Beacons(c + Vector3.up * (y0 + 70 + h + 145f), 0, 0, yaw, dist, false);
                }
                else
                {
                    // Wall slab.
                    var w = 180f + Rnd() * 120f;
                    var h = 220f + Rnd() * 200f;
                    meshes.Prism(2, c, w, 36f + Rnd() * 30f, y0, h, yaw, 4, Rnd() * 500f, 0, id);
                    Beacons(c + Vector3.up * (y0 + h + 1), w, 30f, yaw, dist, true);
                }
            }

            // ---------------------------------------------------------------- glowing haze between the layers
            // warm sodium light pollution and cool teal haze alternate between the layers (was magenta / teal)
            var hazeA = new Color(0.62f, 0.34f, 0.16f);
            var hazeB = new Color(0.14f, 0.42f, 0.5f);
            for (var s = 0; s < 8; s++)
            {
                float a0 = s / 8f * Mathf.PI * 2, a1 = (s + 1) / 8f * Mathf.PI * 2 + 0.06f;
                CityFx.Curtain(fx, center, outerRadius * 1.16f, a0, a1, y0, 150f, s % 2 == 0 ? hazeA : hazeB, 0.07f);
                CityFx.Curtain(fx, center, outerRadius * 1.88f, a0 + 0.2f, a1 + 0.2f, y0, 280f, s % 3 == 0 ? hazeB : hazeA, 0.09f);
            }

            meshes.Finish(parent, CityFx.SkylineLayer);
            fx.Finish(parent, "skyline_fx", CityFx.SkylineLayer, null);
        }
    }

    /// <summary>Flying vehicles with head/tail lights on elevated elliptical lanes (outdoor city zones).</summary>
    public sealed class SkyTraffic : MonoBehaviour
    {
        struct Car { public Transform T; public Vector3 Center; public float Rx, Rz, Angle, Speed, Y, Bob; }
        readonly List<Car> cars = new();
        static Mesh body;
        static Material bodyMat, headMat, tailMat;

        /// <summary>
        /// Flyers on elliptical lanes around center. With roofAt (Unity x, z -> roof height) every lane is sampled along
        /// its whole ellipse and flies at least 14 m above the highest roof under it; lanes that would have to climb far
        /// above maxY are re-rolled so the traffic stays low enough to read from the street.
        /// </summary>
        public static SkyTraffic Create(Transform parent, Vector3 center, int count, float minY, float maxY, float minR, float maxR, int seed, System.Func<float, float, float> roofAt = null)
        {
            var go = new GameObject("SkyTraffic");
            go.transform.SetParent(parent, false);
            var st = go.AddComponent<SkyTraffic>();
            var r = new System.Random(seed);
            if (body == null) body = FxMesh.RoundedBox(1.8f, 0.6f, 4.2f, 0.25f);
            if (bodyMat == null) bodyMat = FxMaterials.Lit(new Color(0.05f, 0.055f, 0.07f), 0.8f, 0.75f, "skycar");
            if (headMat == null) headMat = EnvMaterials.EmissiveInstance(new Color(0.85f, 0.95f, 1f), 6f);
            if (tailMat == null) tailMat = EnvMaterials.EmissiveInstance(new Color(1f, 0.12f, 0.15f), 5f);
            for (var i = 0; i < count; i++)
            {
                var accent = Neon.Pick(r);
                // Kit flyers (HoverCar_A/B, HoverTruck) with a VehicleRig (thrusters, nav strobes, lights); procedural stand-in until the kit is built.
                var car = VehicleKit.SkyCar(go.transform, seed * 7919 + i);
                if (car == null)
                {
                    car = new GameObject("SkyCar");
                    car.transform.SetParent(go.transform, false);
                    AddPart(car.transform, body, bodyMat, Vector3.zero, Vector3.one);
                    AddPart(car.transform, FxMesh.Box(1.5f, 0.12f, 0.1f), headMat, new Vector3(0, 0.05f, 2.12f), Vector3.one);
                    AddPart(car.transform, FxMesh.Box(1.6f, 0.1f, 0.1f), tailMat, new Vector3(0, 0.1f, -2.12f), Vector3.one);
                    AddPart(car.transform, FxMesh.Box(0.06f, 0.06f, 3.6f), NeonKit.TubeMaterial(accent), new Vector3(0, -0.32f, 0), Vector3.one);
                }
                Vector3 lc; float rx, rz, y; var tries = 0;
                while (true)
                {
                    lc = center + new Vector3(((float)r.NextDouble() - 0.5f) * 60f, 0, ((float)r.NextDouble() - 0.5f) * 60f);
                    rx = Mathf.Lerp(minR, maxR, (float)r.NextDouble());
                    rz = Mathf.Lerp(minR, maxR, (float)r.NextDouble());
                    y = Mathf.Lerp(minY, maxY, (float)r.NextDouble());
                    if (roofAt == null) break;
                    var top = 0f;
                    for (var k = 0; k < 160; k++)
                    {
                        var a = k / 160f * Mathf.PI * 2;
                        top = Mathf.Max(top, roofAt(lc.x + Mathf.Sin(a) * rx, lc.z + Mathf.Cos(a) * rz));
                    }
                    y = Mathf.Max(y, top + 14f);
                    if (y <= maxY + 25f || ++tries >= 16) break;
                }
                st.cars.Add(new Car
                {
                    T = car.transform,
                    Center = lc,
                    Rx = rx,
                    Rz = rz,
                    Angle = (float)r.NextDouble() * Mathf.PI * 2,
                    Speed = (r.NextDouble() < 0.5 ? -1 : 1) * (0.05f + (float)r.NextDouble() * 0.08f),
                    Y = y,
                    Bob = (float)r.NextDouble() * 6f,
                });
            }
            return st;
        }

        static void AddPart(Transform parent, Mesh mesh, Material mat, Vector3 pos, Vector3 scale)
        {
            var go = new GameObject("part");
            go.transform.SetParent(parent, false);
            go.transform.localPosition = pos;
            go.transform.localScale = scale;
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var r = go.AddComponent<MeshRenderer>();
            r.sharedMaterial = mat;
            r.shadowCastingMode = ShadowCastingMode.Off;
        }

        void Update()
        {
            var t = Time.time;
            for (var i = 0; i < cars.Count; i++)
            {
                var c = cars[i];
                c.Angle += c.Speed * Time.deltaTime;
                cars[i] = c;
                var p = c.Center + new Vector3(Mathf.Sin(c.Angle) * c.Rx, c.Y + Mathf.Sin(t * 0.5f + c.Bob) * 0.6f, Mathf.Cos(c.Angle) * c.Rz);
                var tangent = new Vector3(Mathf.Cos(c.Angle) * c.Rx, 0, -Mathf.Sin(c.Angle) * c.Rz) * Mathf.Sign(c.Speed);
                c.T.SetPositionAndRotation(p, Quaternion.LookRotation(tangent.sqrMagnitude > 0.001f ? tangent : Vector3.forward) * Quaternion.Euler(0, 0, -Mathf.Sign(c.Speed) * 8f));
            }
        }
    }
}
