using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;

namespace EOA
{
    /// <summary>Data-driven inventory backed by GameState.D.Inventory.</summary>
    public sealed class Inventory
    {
        readonly Func<GameState> gs;
        public Inventory(Func<GameState> gs) { this.gs = gs; }

        public int Count(string id) => gs().D.Inventory.TryGetValue(id, out var n) ? n : 0;
        public bool Has(string id, int n = 1) => Count(id) >= n;

        /// <summary>Adds up to the stack limit. Returns the number actually added.</summary>
        public int Add(string id, int qty = 1, bool silent = false)
        {
            if (!GameData.Items.TryGetValue(id, out var def))
            {
                Debug.LogWarning($"[inventory] unknown item {id}");
                return 0;
            }
            var inv = gs().D.Inventory;
            var cur = Count(id);
            var added = Mathf.Max(0, Mathf.Min(qty, def.Stack - cur));
            if (added <= 0)
            {
                if (!silent) Bus.Emit(new Toast { Text = $"{def.Name}: inventory full", Kind = ToastKind.Warn });
                return 0;
            }
            inv[id] = cur + added;
            if (def.EffectType == "lore")
            {
                var lore = def.EffectStr("lore");
                if (lore != null && !gs().D.Lore.Contains(lore)) gs().D.Lore.Add(lore);
            }
            Bus.Emit(new ItemAdded { Id = id, Qty = added, Total = inv[id] });
            return added;
        }

        public bool Remove(string id, int qty = 1)
        {
            var inv = gs().D.Inventory;
            var cur = Count(id);
            if (cur < qty) return false;
            inv[id] = cur - qty;
            if (inv[id] <= 0) inv.Remove(id);
            Bus.Emit(new ItemRemoved { Id = id, Qty = qty, Total = Count(id) });
            return true;
        }

        public List<(ItemDef def, int qty)> List(ItemCategory? category = null) =>
            gs().D.Inventory.Where(kv => kv.Value > 0 && GameData.Items.ContainsKey(kv.Key) && (category == null || GameData.Items[kv.Key].Category == category))
                .Select(kv => (GameData.Items[kv.Key], kv.Value))
                .OrderBy(x => x.Item1.Name, StringComparer.Ordinal).ToList();
    }

    public struct CharStats
    {
        public float MaxHealth, MaxShield, ShieldDelay, ShieldRegen, MaxEnergy, EnergyRegen, CooldownMul;
        public float PulseRadius, PulseDamage, PulseStagger;
        public float DashDistance, DashCooldown, DashIframes; public int DashCharges;
        public float EchoRange, EchoDuration; public bool EchoDetect, Ultimates;
        public float LightDamage, HeavyDamage, BoltDamage;
    }

    /// <summary>Ability unlocks, the Ability Matrix (skill tree) and derived character stats.</summary>
    public sealed class Progression
    {
        readonly Func<GameState> gs; readonly Inventory inv;
        public Progression(Func<GameState> gs, Inventory inv) { this.gs = gs; this.inv = inv; }

        public bool HasSkill(string id) => gs().D.Skills.Contains(id);

        /// <summary>Spendable points: 1 per Aether Fragment, 3 per Aether Core.</summary>
        public int Points() => inv.Count("aether_fragment") + inv.Count("aether_core") * 3;

        public (bool ok, string reason) CanBuy(string id)
        {
            if (!GameData.Skills.TryGetValue(id, out var n)) return (false, "Unknown node");
            if (HasSkill(id)) return (false, "Already unlocked");
            if (!gs().HasAbility(n.Ability)) return (false, $"Requires {(GameData.Abilities.TryGetValue(n.Ability, out var a) ? a.Name : n.Ability)}");
            foreach (var r in n.Requires) if (!HasSkill(r)) return (false, $"Requires {(GameData.Skills.TryGetValue(r, out var s) ? s.Name : r)}");
            if (Points() < n.Cost) return (false, "Not enough Aether");
            return (true, null);
        }

        public bool Buy(string id)
        {
            if (!CanBuy(id).ok) return false;
            var cost = GameData.Skills[id].Cost;
            while (cost > 0)
            {
                if (inv.Count("aether_fragment") > 0) { inv.Remove("aether_fragment"); cost--; }
                else if (inv.Count("aether_core") > 0) { inv.Remove("aether_core"); inv.Add("aether_fragment", 3, true); }
                else return false;
            }
            gs().D.Skills.Add(id);
            Bus.Emit(new Toast { Text = $"Ability Matrix: {GameData.Skills[id].Name}", Kind = ToastKind.Item });
            return true;
        }

        public CharStats Stats(string ch)
        {
            bool Has(string s) => HasSkill(s);
            bool Up(string id) => inv.Has(id);
            var resonant = Up("up_resonant_core");
            var kael = ch == Characters.Kael;
            return new CharStats
            {
                MaxHealth = (kael ? 110 : 95) + (resonant ? 15 : 0),
                MaxShield = 50 + (Up("up_shield_matrix") ? 40 : 0),
                ShieldDelay = Up("up_shield_matrix") ? 2.6f : 3.5f,
                ShieldRegen = Up("up_shield_matrix") ? 24 : 16,
                MaxEnergy = 100,
                EnergyRegen = 9,
                CooldownMul = resonant ? 0.8f : 1,
                PulseRadius = 5.5f * (Has("pulse_radius") ? 1.4f : 1),
                PulseDamage = 32 * (Has("pulse_damage") ? 1.5f : 1),
                PulseStagger = Has("pulse_stagger") ? 2.2f : 1,
                DashDistance = kael ? 6.5f * (Has("dash_distance") ? 1.4f : 1) : 4.6f * (Has("step_distance") ? 1.4f : 1),
                DashCooldown = kael ? 1.4f * (Has("dash_cooldown") ? 0.65f : 1) : 1.0f * (Has("step_cooldown") ? 0.65f : 1),
                DashCharges = kael && Has("dash_double") ? 2 : 1,
                DashIframes = kael ? 0.28f : 0.34f * (Has("step_iframes") ? 2 : 1),
                EchoRange = 28 * (Has("echo_range") ? 1.5f : 1) * (Up("up_echo_amplifier") ? 1.5f : 1),
                EchoDuration = 10 + (Has("echo_duration") ? 6 : 0) + (Up("up_echo_amplifier") ? 4 : 0),
                EchoDetect = Has("echo_detect"),
                Ultimates = Up("up_core_attunement"),
                LightDamage = kael ? 15 : 11,
                HeavyDamage = kael ? 38 : 28,
                BoltDamage = kael ? 12 : 8,
            };
        }
    }
}
