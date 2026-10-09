using System;
using System.Collections.Generic;
using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Procedural zone classes by zone id. Explicit (no reflection) so IL2CPP code stripping keeps every zone.
    /// </summary>
    public static class ZoneRegistry
    {
        static readonly Dictionary<string, Func<GameObject, ProceduralZone>> zones = new()
        {
            ["plaza"] = go => go.AddComponent<PlazaZone>(),
            ["metro"] = go => go.AddComponent<MetroZone>(),
            ["facility"] = go => go.AddComponent<FacilityZone>(),
            ["rooftops"] = go => go.AddComponent<RooftopsZone>(),
            ["vault"] = go => go.AddComponent<VaultZone>(),
            ["core"] = go => go.AddComponent<CoreZone>(),
        };

        public static bool Has(string id) => id != null && zones.ContainsKey(id);
        public static IEnumerable<string> Ids => zones.Keys;
        public static ProceduralZone Create(string id, GameObject root) => zones[id](root);
    }
}
