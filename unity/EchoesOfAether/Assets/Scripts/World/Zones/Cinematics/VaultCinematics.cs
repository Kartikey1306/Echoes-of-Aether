using System.Threading.Tasks;
using UnityEngine;
using static EOA.ProtoSpace;

namespace EOA
{
    /// <summary>
    /// Vault cinematics (port of src/game/Cinematics.ts): cin_guardian_reveal (the Guardian rises from the containment
    /// pit, roars, boss bar on finalize) and cin_hidden_vault (Dr. Maren's echo in the secret room).
    /// Offsets are prototype vectors converted with <see cref="ProtoSpace.V(float,float,float)"/>; markers come from the
    /// zone definition (already Unity space).
    /// </summary>
    public static class VaultCinematics
    {
        public static void Register(Cinematics c)
        {
            c.Register("cin_guardian_reveal", GuardianScript, GuardianFinalize);
            c.Register("cin_hidden_vault", HiddenVaultScript);
        }

        /// <summary>The vault Guardian (factory type guardian_vault shares the "guardian" enemy data).</summary>
        static Enemy FindGuardian(bool aliveOnly)
        {
            var all = Enemy.All;
            for (var i = 0; i < all.Count; i++)
            {
                var e = all[i];
                if (e != null && e.Type == "guardian" && (!aliveOnly || e.Alive)) return e;
            }
            return null;
        }

        // ---------------------------------------------------------------- Guardian reveal (~30 s)

        static async Task GuardianScript(Cinematics.CineCtx c)
        {
            var g = c.G;
            var p = g.Player;
            if (p == null) return;
            var guardian = FindGuardian(true);
            var rise = g.World.Def != null ? g.World.Def.Marker("guardian_rise") ?? V(0, 0, 78) : V(0, 0, 78);
            if (guardian != null)
            {
                guardian.VisualOffsetY = -6;
                guardian.YawDeg = Mathf.Atan2(p.Position.x - rise.x, p.Position.z - rise.z) * Mathf.Rad2Deg;
            }
            c.Music("boss");
            c.Sfx("door", rise);
            CombatSystem.Shake(0.3f);
            var pp = p.Position;
            c.Cut(pp + V(2.2f, 1.7f, 2.5f), rise + V(0, 1.5f, 0), 45);
            await c.Lines("cin_guardian_lines", "n1", "n1");
            // The Guardian rises out of the containment pit.
            if (guardian != null) VaultKit.Quiet(RiseGuardian(guardian, g));
            VaultKit.Quiet(c.Shot(rise + V(-5, 1.2f, 9), rise + V(0, 3, 0), rise + V(-3.5f, 2.2f, 7), rise + V(0, 4.4f, 0), 5, 40));
            for (var i = 0; i < 4; i++)
            {
                VfxManager.Instance?.SparksDir(rise + V((Random.value - 0.5f) * 5, 0.3f, (Random.value - 0.5f) * 5), Vector3.up, 24, Hex(0xff8a5a), 7);
                CombatSystem.Shake(0.25f);
                await c.Wait(0.9f);
            }
            await c.Lines("cin_guardian_lines", "n2", "n2");
            c.Cut(rise + V(1.5f, 2.2f, 5.5f), rise + V(0, 4.3f, 0), 34);
            if (guardian != null) guardian.PlayAnimation("roar");
            CombatSystem.Shake(0.6f);
            await c.Lines("cin_guardian_lines", "n3", "n3");
            c.Cut(pp + V(-1.2f, 1.8f, -2.2f), pp + V(0, 1.6f, 0), 40);
            await c.Lines("cin_guardian_lines", "n4", "n5");
        }

        /// <summary>Ease the Guardian's visual up from 6 m below over 4.5 s (k(2-k)) while the cinematic runs.</summary>
        static async Task RiseGuardian(Enemy guardian, GameManager g)
        {
            var t0 = Time.time;
            while (true)
            {
                if (guardian == null || g.Cinematics.Active != "cin_guardian_reveal") return;
                var k = Mathf.Min(1, (Time.time - t0) / 4.5f);
                guardian.VisualOffsetY = -6 * (1 - k * (2 - k));
                if (k >= 1) return;
                await Awaitable.NextFrameAsync();
            }
        }

        static void GuardianFinalize()
        {
            var guardian = FindGuardian(false);
            if (guardian != null) guardian.VisualOffsetY = 0;
            G.Manager?.SetBoss(true);
        }

        // ---------------------------------------------------------------- Hidden Vault (~25 s)

        static async Task HiddenVaultScript(Cinematics.CineCtx c)
        {
            var g = c.G;
            var p = g.Player;
            if (p == null) return;
            var relic = g.World.Def != null ? g.World.Def.Marker("relic") ?? p.Position : p.Position;
            var echoPos = relic + V(1.4f, -1.65f, 1.2f);
            var echo = VaultKit.SpawnEcho(c, echoPos, Mathf.Atan2(p.Position.x - echoPos.x, p.Position.z - echoPos.z) * Mathf.Rad2Deg);
            try
            {
                c.Cut(p.Position + V(-1.2f, 1.8f, -1.6f), echoPos + V(0, 1.5f, 0), 38);
                c.Sfx("reveal", echoPos);
                await c.Wait(1.2f);
                await c.Lines("cin_hidden_vault_lines", "n1", "n1");
                c.Cut(echoPos + V(1.4f, 1.6f, 1.8f), echoPos + V(0, 1.5f, 0), 32);
                await c.Lines("cin_hidden_vault_lines", "n2", "n2");
                c.Cut(p.Position + V(1.5f, 1.7f, 1.2f), p.Position + V(0, 1.5f, 0), 36);
                await c.Lines("cin_hidden_vault_lines", "n3", "n3");
                await c.Wait(1);
            }
            finally
            {
                VfxManager.Instance?.Embers(echoPos + Vector3.up, 50, Hex(0x8fd8ff), 1.2f, 2);
                if (echo != null) Object.Destroy(echo);
            }
        }
    }
}
