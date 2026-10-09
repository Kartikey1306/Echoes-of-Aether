using System.Collections.Generic;
using System.Linq;

namespace EOA
{
    public struct Buffs { public float DamageMul, AttackSpeed, DashMul; public bool Reveal; }

    /// <summary>Timed powerup effects.</summary>
    public sealed class Powerups
    {
        public sealed class ActiveBuff { public float Remaining, Duration; }
        public readonly Dictionary<string, ActiveBuff> Active = new();

        /// <summary>Returns true when the powerup restores shields instantly.</summary>
        public bool Activate(string id)
        {
            if (!GameData.Powerups.TryGetValue(id, out var def)) return false;
            if (def.Duration > 0) Active[id] = new ActiveBuff { Remaining = def.Duration, Duration = def.Duration };
            Bus.Emit(new PowerupActivated { Id = id, Duration = def.Duration });
            return def.Stat == "shieldRestore";
        }

        readonly List<string> expireBuf = new();

        public void Update(float dt)
        {
            if (Active.Count == 0) return;
            // Copy keys into a reused buffer (Active changes while iterating): no per-frame garbage.
            expireBuf.Clear();
            expireBuf.AddRange(Active.Keys);
            foreach (var id in expireBuf)
            {
                var s = Active[id];
                s.Remaining -= dt;
                if (s.Remaining <= 0)
                {
                    Active.Remove(id);
                    Bus.Emit(new PowerupExpired { Id = id });
                }
            }
        }

        public Buffs Current()
        {
            float V(string id) => GameData.Powerups.TryGetValue(id, out var p) ? p.Value : 0;
            return new Buffs
            {
                DamageMul = Active.ContainsKey("aether_shard") ? 1 + V("aether_shard") : 1,
                AttackSpeed = Active.ContainsKey("overcharge") ? 1 + V("overcharge") : 1,
                DashMul = Active.ContainsKey("phase_core") ? 1 + V("phase_core") : 1,
                Reveal = Active.ContainsKey("echo_fragment"),
            };
        }

        public void Clear() => Active.Clear();
    }
}
