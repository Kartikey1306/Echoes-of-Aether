using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Environment prop library. The editor setup turns every FBX in Art/Environment (manifest.json) into a prefab at
    /// Resources/Env/Props/&lt;Name&gt; with URP materials, an LODGroup and the manifest's colliders, and copies the
    /// manifest to Resources/Env/env_manifest.json. At runtime props are instantiated from those prefabs; a
    /// missing prefab becomes a box of the manifest size (pivot at base centre) so layouts remain playable.
    /// </summary>
    public static class EnvProps
    {
        public sealed class Info
        {
            public string Name, Category;
            public Vector3 Size = Vector3.one;
            /// <summary>"base" (base centre, default) or "center".</summary>
            public string Pivot = "base";
            public string Material = "concrete";
            /// <summary>Centre of the mesh bounds relative to the pivot (Unity axes).</summary>
            public Vector3 BoundsCenter;
        }

        static Dictionary<string, Info> infos;

        public sealed class DecalInfo
        {
            public string Name, Projection;
            public Vector2 Size;
            public float Depth;
            public string[] Tags;
        }

        static readonly List<DecalInfo> decals = new();
        /// <summary>Decal sets from the manifest ("floor" or "wall" projection, size in metres, tags).</summary>
        public static IReadOnlyList<DecalInfo> Decals { get { Load(); return decals; } }
        static readonly Dictionary<string, GameObject> prefabs = new();

        public static IReadOnlyDictionary<string, Info> All { get { Load(); return infos; } }

        /// <summary>Runtime manifests, one per art kit (written by EnvLibraryBuilder).</summary>
        public static readonly string[] Manifests = { "Env/env_manifest", "Env/vehicles_manifest", "Env/landmarks_manifest", "Env/street_manifest" };

        static void Load()
        {
            if (infos != null) return;
            infos = new Dictionary<string, Info>();
            foreach (var file in Manifests)
            {
                var ta = Resources.Load<TextAsset>(file);
                if (ta != null) LoadManifest(ta.text);
            }
        }

        static void LoadManifest(string text)
        {
            try
            {
                var root = JToken.Parse(text);
                if (root is JObject ro && ro["decals"] is JArray decalArr)
                    foreach (var d in decalArr.OfType<JObject>())
                    {
                        var size = d["sizeMeters"] is JArray sz && sz.Count >= 2 ? new Vector2((float)sz[0], (float)sz[1]) : Vector2.one;
                        var tags = (d["tags"] as JArray)?.Select(x => (string)x).ToArray() ?? System.Array.Empty<string>();
                        decals.Add(new DecalInfo { Name = (string)d["name"], Size = size, Projection = (string)d["projection"] ?? "floor", Tags = tags,
                            Depth = (float?)d["urp"]?["projectionDepth"] ?? 0.4f });
                    }
                IEnumerable<JToken> items = root is JObject o && o["assets"] != null ? o["assets"] is JObject ao ? ao.Properties() : (IEnumerable<JToken>)o["assets"] : root is JArray a ? a : null;
                if (items == null) return;
                foreach (var tok in items)
                {
                    var j = tok is JProperty p ? p.Value as JObject : tok as JObject;
                    if (j == null) continue;
                    var name = (string)j["name"] ?? (tok as JProperty)?.Name;
                    if (string.IsNullOrEmpty(name)) continue;
                    var info = new Info { Name = name, Category = (string)j["category"] };
                    var d = j["dimensions"] ?? j["dims"] ?? j["size"];
                    if (d is JArray da && da.Count >= 3) info.Size = new Vector3((float)da[0], (float)da[1], (float)da[2]);
                    else if (d is JObject dob) info.Size = new Vector3((float?)dob["w"] ?? (float?)dob["x"] ?? 1, (float?)dob["h"] ?? (float?)dob["y"] ?? 1, (float?)dob["d"] ?? (float?)dob["z"] ?? 1);
                    var pivot = j["pivot"];
                    if (pivot != null && pivot.Type == JTokenType.String)
                    {
                        var pv = ((string)pivot).ToLowerInvariant();
                        info.Pivot = pv.Contains("cent") && !pv.Contains("base") ? "center" : "base";
                    }
                    if (j["boundsCenter"] is JArray bc && bc.Count >= 3) info.BoundsCenter = new Vector3((float)bc[0], (float)bc[1], (float)bc[2]);
                    else info.BoundsCenter = info.Pivot == "center" ? Vector3.zero : new Vector3(0, info.Size.y / 2, 0);
                    if (j["materials"] is JArray ma && ma.Count > 0) info.Material = (string)ma[0];
                    infos[name] = info;
                }
            }
            catch (System.Exception e) { Debug.LogWarning("[env] manifest parse failed: " + e.Message); }
        }

        public static Info Get(string name)
        {
            Load();
            return infos.TryGetValue(name, out var i) ? i : null;
        }

        /// <summary>Size (w, h, d) in metres of a prop, from the manifest (1 m cube when unknown).</summary>
        public static Vector3 Size(string name) => Get(name)?.Size ?? Vector3.one;

        public static bool Exists(string name)
        {
            if (!prefabs.TryGetValue(name, out var p)) prefabs[name] = p = Resources.Load<GameObject>("Env/Props/" + name);
            return p != null || Get(name) != null;
        }

        public static GameObject Instantiate(string name, Transform parent, bool collide = true)
        {
            if (!prefabs.TryGetValue(name, out var prefab)) prefabs[name] = prefab = Resources.Load<GameObject>("Env/Props/" + name);
            GameObject go;
            if (prefab != null)
            {
                go = Object.Instantiate(prefab, parent, false);
                go.name = name;
                if (!collide) foreach (var c in go.GetComponentsInChildren<Collider>(true)) Object.Destroy(c);
                return go;
            }
            var info = Get(name);
            if (info == null) Debug.LogWarning($"[env] unknown prop '{name}' (no prefab, not in manifest)");
            var size = info?.Size ?? Vector3.one;
            go = new GameObject(name + "_Placeholder");
            go.layer = CombatLayers.World;
            go.transform.SetParent(parent, false);
            var box = GameObject.CreatePrimitive(PrimitiveType.Cube);
            box.layer = CombatLayers.World;
            box.transform.SetParent(go.transform, false);
            box.transform.localScale = size;
            box.transform.localPosition = info != null ? info.BoundsCenter : new Vector3(0, size.y / 2, 0);
            box.GetComponent<Renderer>().sharedMaterial = EnvMaterials.Get(info?.Material ?? "metal_dark");
            if (!collide) Object.Destroy(box.GetComponent<Collider>());
            return go;
        }
    }
}
