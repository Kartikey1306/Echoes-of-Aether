using System;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json;
using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Character customization catalog (Resources/Characters/Custom/catalog.json, produced by the Blender pipeline):
    /// hair styles, eyewear, armour sets and tattoo designs per hero, each with a thumbnail. Items are attachments
    /// bound to the hero skeleton at runtime by <see cref="CharacterModel"/>.
    /// </summary>
    public sealed class CustomCatalog
    {
        public sealed class Item
        {
            public string Id, Label, Hero, File, Kind, Bone, Thumb, Ink, Glow;
            /// <summary>Hair: grey RGBA atlas tinted by the hair colour (Tint = "hair") on the material slot Material.</summary>
            public string BaseMap, Material, Tint;
            public float AlphaCutoff = 0.4f;
            public string[] Replaces = Array.Empty<string>();
            public float[] LocalPos, LocalRot;
            /// <summary>Armour/eyewear: per material slot maps and colours.</summary>
            public Dictionary<string, MatDef> Materials;
            /// <summary>Eyewear frame finish (EyewearFrame slot).</summary>
            public FrameDef Frame;
            /// <summary>Eyewear authored against the current hero heads (clearances, temples over the ears): no runtime fit.</summary>
            public bool Fitted;
        }

        public sealed class FrameDef
        {
            public float Metallic = 0.6f, Smoothness = 0.8f;
        }

        /// <summary>Material slot definition (Resources paths without extension; MaskMap: R metallic, G occlusion, A smoothness).</summary>
        public sealed class MatDef
        {
            public string BaseMap, Normal, MaskMap, Tint, Color, LensTint;
            public float Intensity = 1f, LensAlpha = 0.35f;
        }

        public int Version;
        public List<Item> Hair = new(), Eyewear = new(), Armour = new(), Tattoos = new();
        public Dictionary<string, Dictionary<string, string>> Defaults = new();

        static CustomCatalog instance;
        static bool loaded;

        public static CustomCatalog Get()
        {
            if (loaded) return instance;
            loaded = true;
            var ta = Resources.Load<TextAsset>("Characters/Custom/catalog");
            if (ta == null) return instance = new CustomCatalog();
            try { instance = JsonConvert.DeserializeObject<CustomCatalog>(ta.text, GameData.Json) ?? new CustomCatalog(); }
            catch (Exception e) { Debug.LogWarning("[custom] catalog parse failed: " + e.Message); instance = new CustomCatalog(); }
            return instance;
        }

        public List<Item> List(string category) => category switch
        {
            "hair" => Hair, "eyewear" => Eyewear, "armour" => Armour, "tattoos" => Tattoos, _ => new List<Item>(),
        };

        /// <summary>Items of a category for a hero whose assets are present (half-exported items are skipped).</summary>
        public IEnumerable<Item> For(string category, string hero) => List(category).Where(i => i.Hero == hero && Available(i));

        public Item Find(string category, string hero, string id) =>
            string.IsNullOrEmpty(id) || id == "none" ? null : List(category).FirstOrDefault(i => i.Hero == hero && i.Id == id && Available(i));

        static readonly Dictionary<Item, bool> available = new();

        static bool Available(Item i)
        {
            if (available.TryGetValue(i, out var ok)) return ok;
            ok = i.File != null ? Resources.Load<GameObject>("Characters/Custom/" + i.File) != null
                : i.Ink != null || i.Glow != null ? Load(i.Ink) != null || Load(i.Glow) != null
                : false;
            return available[i] = ok;
        }

        static readonly Dictionary<string, Texture2D> textures = new();

        /// <summary>Catalog texture by Resources path (relative to Characters/Custom, no extension); cached.</summary>
        public static Texture2D Load(string path)
        {
            if (string.IsNullOrEmpty(path)) return null;
            if (!textures.TryGetValue(path, out var t)) textures[path] = t = Resources.Load<Texture2D>("Characters/Custom/" + path);
            return t;
        }

        public string Default(string hero, string category) =>
            Defaults != null && Defaults.TryGetValue(hero, out var d) && d.TryGetValue(category, out var v) ? v : null;

        static readonly Dictionary<string, Texture2D> thumbs = new();

        public static Texture2D Thumb(Item i)
        {
            if (i?.Thumb == null) return null;
            if (!thumbs.TryGetValue(i.Thumb, out var t)) thumbs[i.Thumb] = t = Resources.Load<Texture2D>("Characters/Custom/" + i.Thumb);
            return t;
        }
    }

    /// <summary>Binds catalog attachments (hair, eyewear, armour) to a character's skeleton.</summary>
    public static class Attachments
    {
        /// <summary>
        /// Instantiate a catalog item on `model`. Rigid items are parented to their bone; skinned items have their
        /// renderers re-bound to the character's bones by name and the imported armature removed.
        /// </summary>
        public static GameObject Attach(CharacterModel model, CustomCatalog.Item item)
        {
            var prefab = Resources.Load<GameObject>("Characters/Custom/" + item.File);
            if (prefab == null) { Debug.LogWarning($"[custom] missing {item.File}"); return null; }
            var bones = new Dictionary<string, Transform>();
            foreach (var t in model.GetComponentsInChildren<Transform>(true))
            {
                bones[t.name] = t;
                var c = t.name.LastIndexOf(':');
                if (c >= 0) bones[t.name.Substring(c + 1)] = t;
            }
            Transform Bone(string n)
            {
                if (string.IsNullOrEmpty(n)) return null;
                if (bones.TryGetValue(n, out var b)) return b;
                var c = n.LastIndexOf(':');
                return c >= 0 && bones.TryGetValue(n.Substring(c + 1), out b) ? b : null;
            }
            var inst = UnityEngine.Object.Instantiate(prefab);
            inst.name = "Custom_" + item.Id;
            SetLayer(inst.transform, model.gameObject.layer);
            if (item.Kind == "skinned" && inst.GetComponentInChildren<SkinnedMeshRenderer>(true) == null)
                Debug.LogWarning($"[custom] {item.File}: no skinned renderer (re-run EOA/Build Customization Library); attaching rigidly");
            if (item.Kind == "skinned" && inst.GetComponentInChildren<SkinnedMeshRenderer>(true) != null)
            {
                var holder = new GameObject("Custom_" + item.Id);
                holder.transform.SetParent(model.transform, false);
                holder.layer = model.gameObject.layer;
                foreach (var smr in inst.GetComponentsInChildren<SkinnedMeshRenderer>(true))
                {
                    var bs = smr.bones;
                    for (var i = 0; i < bs.Length; i++) if (bs[i] != null) bs[i] = Bone(bs[i].name) ?? bs[i];
                    smr.bones = bs;
                    if (smr.rootBone != null) smr.rootBone = Bone(smr.rootBone.name) ?? smr.rootBone;
                    smr.updateWhenOffscreen = false;
                    smr.transform.SetParent(holder.transform, false);
                }
                UnityEngine.Object.Destroy(inst);
                return holder;
            }
            var parent = Bone(item.Bone ?? "mixamorig:Head") ?? model.transform;
            inst.transform.SetParent(parent, false);
            inst.transform.localPosition = item.LocalPos is { Length: >= 3 } p ? new Vector3(p[0], p[1], p[2]) : Vector3.zero;
            inst.transform.localRotation = item.LocalRot is { Length: >= 3 } r ? Quaternion.Euler(r[0], r[1], r[2]) : Quaternion.identity;
            // Rigid items keep their mesh in the bone's space: strip any imported armature/animator.
            foreach (var an in inst.GetComponentsInChildren<Animator>(true)) UnityEngine.Object.Destroy(an);
            return inst;
        }

        static void SetLayer(Transform t, int layer)
        {
            t.gameObject.layer = layer;
            foreach (Transform c in t) SetLayer(c, layer);
        }
    }
}
