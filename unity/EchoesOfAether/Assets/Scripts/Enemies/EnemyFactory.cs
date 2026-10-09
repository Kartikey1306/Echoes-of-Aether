using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Creates enemies by type (port of World.ts enemyFactories):
    /// drone, sentinel, warden, stalker, guardian, guardian_vault.
    /// </summary>
    public static class EnemyFactory
    {
        public static readonly string[] Types = { "drone", "sentinel", "warden", "stalker", "guardian", "guardian_vault" };

        public static bool IsKnown(string type) => System.Array.IndexOf(Types, type) >= 0;

        /// <summary>EnemyDef id used for a factory type (the vault guardian shares the guardian's data).</summary>
        public static string DefIdFor(string type) => type == "guardian_vault" ? "guardian" : type;

        /// <summary>
        /// Create and spawn an enemy. `pos` is the feet position (drones: hover position), `yaw` in degrees
        /// (Unity convention: 0 faces +Z; the prototype's default spawn yaw PI is 180). Returns null for unknown types.
        /// </summary>
        public static Enemy Create(string type, Vector3 pos, float yaw, Transform parent) => Create(type, pos, yaw, parent, null);

        /// <summary>
        /// Create with the encounter id set before spawning (aggro sharing and the guardian's spawn-time aggro use it).
        /// `aggro` makes it hunt immediately (later waves, quest spawns, boss minions).
        /// </summary>
        public static Enemy Create(string type, Vector3 pos, float yaw, Transform parent, string encounterId, bool aggro = false)
        {
            GameData.EnsureLoaded();
            if (!GameData.Enemies.TryGetValue(DefIdFor(type), out var def))
            {
                Debug.LogError($"[enemies] no enemy data for type '{type}'");
                return null;
            }
            var go = new GameObject("enemy:" + type);
            go.layer = CombatLayers.Enemy;
            if (parent != null) go.transform.SetParent(parent, false);
            go.transform.SetPositionAndRotation(pos, Quaternion.Euler(0f, yaw, 0f));
            Enemy e;
            switch (type)
            {
                case "drone": e = go.AddComponent<Drone>(); break;
                case "sentinel":
                case "warden": e = go.AddComponent<Sentinel>(); break;
                case "stalker": e = go.AddComponent<Stalker>(); break;
                case "guardian":
                case "guardian_vault": e = go.AddComponent<Guardian>(); break;
                default:
                    Debug.LogError($"[enemies] no enemy factory for '{type}'");
                    Object.Destroy(go);
                    return null;
            }
            CombatSystem.Ensure();
            e.EncounterId = encounterId;
            e.Init(type, def);
            e.Spawn(pos, yaw);
            if (aggro) e.SetAggro();
            return e;
        }

        /// <summary>
        /// Minion helper for IWorld.SpawnMinion implementations (prototype World.spawnMinion): ground enemies are
        /// snapped to the ground below `pos`, drones keep their height; the minion is aggro'd and a red flash marks it.
        /// </summary>
        public static Enemy SpawnMinion(string type, Vector3 pos, string encounterId, Transform parent)
        {
            Vector3 at = pos;
            if (type != "drone")
            {
                float? g = EnemyHost.GroundAt(pos + Vector3.up * 2f, 12f);
                at.y = (g ?? pos.y) + 0.05f;
            }
            var e = Create(type, at, 0f, parent, encounterId, true);
            if (e != null)
            {
                FxKit.FlashSprite(at + Vector3.up, 2.4f, 0xff5a3au, 0.25f);
                FxKit.Embers(at + Vector3.up, 20, 0xff5a3au, 1f, 1f);
            }
            return e;
        }
    }
}
