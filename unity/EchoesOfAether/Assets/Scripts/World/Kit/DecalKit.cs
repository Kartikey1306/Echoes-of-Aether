using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.Rendering.Universal;

namespace EOA
{
    /// <summary>
    /// URP decal projectors from the environment kit's decal sets (Resources/Env/Decals/&lt;name&gt;.mat, built by the
    /// importer): puddles, oil, cracks, road paint and manholes on the ground; grime, rust streaks, posters and scorch
    /// marks on walls; and the street kit's St_* decals (graffiti, stickers, bill posters, asphalt patches, skids,
    /// pavement stains, tactile paving) placed by <see cref="CityClutter"/> / <see cref="CityStorefronts"/>.
    /// Unity-space placement.
    /// </summary>
    public static class DecalKit
    {
        static readonly Dictionary<string, Material> mats = new();
        static Dictionary<string, EnvProps.DecalInfo> infos;

        static Material Mat(string name)
        {
            if (!mats.TryGetValue(name, out var m)) mats[name] = m = Resources.Load<Material>("Env/Decals/" + name);
            return m;
        }

        /// <summary>Project a decal. Floor decals project straight down; wall decals into the wall along -normal.</summary>
        public static GameObject Place(Transform parent, string name, Vector3 pos, Vector3 normal, float yawDeg, float scale = 1, float depth = 0.4f)
        {
            var m = Mat(name);
            if (m == null) return null;
            if (infos == null)
            {
                infos = new Dictionary<string, EnvProps.DecalInfo>();
                foreach (var d in EnvProps.Decals) infos[d.Name] = d;
            }
            infos.TryGetValue(name, out var info);
            var size = (info?.Size ?? Vector2.one) * scale;
            var go = new GameObject("Decal_" + name);
            go.transform.SetParent(parent, false);
            go.transform.position = pos + normal * (depth * 0.5f);
            // The projector looks along its +Z: into the surface.
            var up = Mathf.Abs(Vector3.Dot(normal, Vector3.up)) > 0.9f ? Quaternion.Euler(0, yawDeg, 0) * Vector3.forward : Vector3.up;
            go.transform.rotation = Quaternion.LookRotation(-normal, up);
            var dp = go.AddComponent<DecalProjector>();
            dp.material = m;
            dp.size = new Vector3(size.x, size.y, depth);
            dp.pivot = Vector3.zero;
            dp.fadeFactor = 1f;
            dp.drawDistance = 70f;
            return go;
        }

        static string[] Pick(string projection, params string[] tags)
        {
            // Street-kit decals (St_*) are placed deliberately (tactile strips, road patches, graffiti), never scattered.
            var list = EnvProps.Decals.Where(d => d.Projection == projection && !d.Name.StartsWith("St_") && (tags.Length == 0 || d.Tags.Any(t => tags.Contains(t)))).Select(d => d.Name).ToArray();
            return list.Length > 0 ? list : EnvProps.Decals.Where(d => d.Projection == projection && !d.Name.StartsWith("St_")).Select(d => d.Name).ToArray();
        }

        /// <summary>Scatter street decals (puddles, oil, cracks, litter, manholes) on walkable ground around `center`.</summary>
        public static int ScatterGround(Transform parent, Vector3 center, float radius, int count, int seed)
        {
            var names = Pick("floor");
            if (names.Length == 0) return 0;
            Physics.SyncTransforms(); // colliders created this frame must be queryable
            var r = new System.Random(seed);
            var placed = 0;
            for (var i = 0; i < count * 3 && placed < count; i++)
            {
                var a = (float)r.NextDouble() * Mathf.PI * 2;
                var d = Mathf.Sqrt((float)r.NextDouble()) * radius;
                var p = center + new Vector3(Mathf.Sin(a) * d, 40f, Mathf.Cos(a) * d);
                if (!Physics.Raycast(p, Vector3.down, out var hit, 120f, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore)) continue;
                if (hit.normal.y < 0.9f) continue;
                Place(parent, names[r.Next(names.Length)], hit.point, hit.normal, (float)r.NextDouble() * 360f, 0.8f + (float)r.NextDouble() * 0.7f);
                placed++;
            }
            return placed;
        }
    }
}
