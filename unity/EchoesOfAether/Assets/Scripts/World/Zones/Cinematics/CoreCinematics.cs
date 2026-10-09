using System.Threading.Tasks;
using UnityEngine;
using static EOA.ProtoSpace;

namespace EOA
{
    /// <summary>
    /// Ending (port of endingScript / endingFinalize in src/game/Cinematics.ts, ~90 s): Dr. Maren's echo at the heart,
    /// the release (Core flares, echoes rise, white-out), then dawn over Aether-9 at the plaza camp (cinematic zone load).
    /// The quest's "credits" action follows the cinematic.
    /// </summary>
    public static class CoreCinematics
    {
        public static void Register(Cinematics c)
        {
            c.Register("cin_ending", EndingScript, EndingFinalize);
        }

        static async Task EndingScript(Cinematics.CineCtx c)
        {
            var g = c.G;
            var p = g.Player;
            var zone = g.World.Script as CoreZone;
            var def = g.World.Def;
            var heart = def != null ? def.Marker("heart") ?? V(0, 1.25f, 0) : V(0, 1.25f, 0);
            var core = def != null ? def.Marker("core") ?? V(0, 15, 0) : V(0, 15, 0);
            c.Music("ending");
            GameObject echo = null;
            var skipped = false;
            try
            {
                // Maren's echo stands on the heart pedestal (top y 1.2): the shot below frames her head at heart + 1.4.
                echo = VaultKit.SpawnEcho(c, heart + V(0, -0.05f, -1.5f), Yaw(0));
                c.Cut(heart + V(4.5f, 2.2f, 6), heart + V(0, 1.4f, -1), 38);
                await c.Wait(1);
                await c.Lines("cin_ending_lines", "n1", "n1");
                if (p != null) c.Cut(p.Position + V(1.4f, 1.8f, 2), p.Position + V(0, 1.5f, -1), 36);
                await c.Lines("cin_ending_lines", "n2", "n2");
                await c.Lines("cin_ending_lines", "n3", "n3");
                // Release: the Core flares and the echoes rise.
                if (zone != null) zone.Released = true;
                if (echo != null) { Object.Destroy(echo); echo = null; }
                var vfx = VfxManager.Instance;
                if (vfx != null)
                {
                    Keep(vfx.Emitter(new Vector3(core.x, 2, core.z), "aether", 120, 6), zone);
                    for (var i = 0; i < 6; i++) Keep(vfx.Emitter(V(Mathf.Sin(i) * 12, 0.5f, Mathf.Cos(i) * 12), "aether", 30, 8), zone);
                }
                CombatSystem.Shake(0.4f);
                c.Sfx("ult_impact", core);
                VaultKit.Quiet(c.Shot(heart + V(10, 3, 16), core + V(0, -6, 0), V(3, 24, 14), core + V(0, 10, 0), 9, 50));
                await c.Wait(3);
                VaultKit.Quiet(VaultKit.PostFlashPulse(0.6f, 0.9f));
                VfxManager.Instance?.FlashSprite(core, 26, Hex(0xe8f6ff), 0.6f);
                await c.Wait(4);
                await c.Fade(true, 1.8f);
            }
            catch (CinematicSkipped) { skipped = true; }
            finally
            {
                if (echo != null) Object.Destroy(echo);
            }

            // Dawn over Aether-9. A skip still lands the player at the dawn camp (the end-of-game save is written there).
            if (skipped) await c.Fade(true, 0.35f);
            await g.LoadZone("plaza", "camp", cinematic: true);
            if (skipped || c.Skipped) throw new CinematicSkipped();
            G.Input?.EnableGameplay(false);
            var pz = g.Player;
            if (pz != null) pz.SetScripted(true);
            c.Cut(V(-26, 14, 30), V(0, 6, 0), 50);
            await c.Fade(false, 2.5f);
            VaultKit.Quiet(c.Shot(V(-26, 14, 30), V(0, 6, 0), V(-14, 8, 22), V(0, 8, -10), 16, 48));
            await c.Lines("cin_ending_lines", "n4", "n4");
            await c.Lines("cin_ending_lines", "n5", "n5");
            var camp = g.World.Def != null ? g.World.Def.Marker("fire") ?? V(22, 1, -22) : V(22, 1, -22);
            c.Cut(camp + V(-6, 2.2f, 7), camp + V(0, 1.6f, 0), 40);
            await c.Wait(3.5f);
            var hp = pz != null ? pz.Position : camp;
            c.Cut(hp + V(2.2f, 1.7f, 3.2f), hp + V(0, 1.5f, 0), 36);
            await c.Lines("cin_ending_lines", "n6", "n6");
            await c.Lines("cin_ending_lines", "n7", "n7");
            VaultKit.Quiet(c.Shot(hp + V(2.2f, 1.7f, 3.2f), hp + V(0, 1.5f, 0), hp + V(6, 10, 14), V(0, 12, -40), 6, 50));
            await c.Wait(5);
            await c.Fade(true, 2.5f);
        }

        /// <summary>Tie a release emitter to the Core zone so it goes away with it.</summary>
        static void Keep(GameObject emitter, CoreZone zone)
        {
            if (emitter != null && zone != null) emitter.transform.SetParent(zone.transform, true);
        }

        static void EndingFinalize() => VaultKit.PostFlash(0);
    }
}
