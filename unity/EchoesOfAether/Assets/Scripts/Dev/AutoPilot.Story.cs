using System;
using System.Linq;
using System.Threading.Tasks;
using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Full main-story play-through (port of tools/test/playthrough.mjs): M1 Awakening → M5 Core → ending → credits →
    /// menu, using teleports, interactions and debug kills, with screenshots at each beat. Run with
    /// EOA/Test/Smoke Test (story) or -executeMethod EOA.EditorTools.SmokeTest.RunStory. Prototype coordinates.
    /// </summary>
    public sealed partial class AutoPilot
    {
        static GameManager M => G.Manager;

        async Task Flush(int n = 40)
        {
            for (var i = 0; i < n; i++)
            {
                if (!M.InDialogue && M.Cinematics.Active == null) break;
                var dv = M.UI?.Dialogue;
                dv?.ForceAdvance();
                dv?.PickFirstChoice();
                if (M.Cinematics.Active != null) M.Cinematics.Stop();
                await Seconds(0.15f);
            }
        }

        async Task WaitFor(string desc, Func<bool> cond, float timeout = 60)
        {
            var end = Time.realtimeSinceStartup + timeout;
            while (Time.realtimeSinceStartup < end)
            {
                if (cond()) return;
                await Flush(3);
                await Seconds(0.25f);
            }
            throw new Exception("Timeout waiting for: " + desc);
        }

        static string StageOf(string q)
        {
            if (!G.State.D.Quests.TryGetValue(q, out var s)) return "none";
            if (s.Status == "done") return "done";
            var def = GameData.Quests[q];
            return s.Stage < def.Stages.Length ? def.Stages[s.Stage].Id : "?";
        }

        async Task ExpectStage(string q, string st, float timeout = 60)
        {
            await WaitFor($"{q} at {st} (now {StageOf(q)})", () => StageOf(q) == st, timeout);
            Log($"{q} -> {st}");
        }

        Task ZoneIs(string z) => WaitFor("zone " + z, () => M.World.ZoneId == z && M.Mode == GameMode.Play && !M.World.Loading, 120);

        static void Tp(float x, float y, float z) => M.Player.Teleport(ProtoSpace.V(x, y, z), M.Player.YawDeg);

        static bool Interact(string id)
        {
            var ok = M.World.InteractWith(id);
            if (!ok) Debug.LogWarning("[autopilot] interactable not available: " + id);
            return ok;
        }

        async Task Kill(string enc)
        {
            await WaitFor("enemies of " + enc, () => Enemy.All.Any(e => e != null && e.Alive && e.EncounterId == enc) || G.State.IsDefeated(enc), 30);
            for (var i = 0; i < 8; i++)
            {
                foreach (var e in Enemy.All.ToList())
                    if (e != null && e.Alive && e.EncounterId == enc)
                        e.ReceiveHit(new HitInfo { Damage = 99999, Poise = 999, Kind = HitKind.Heavy, Point = e.Position, Pierce = true });
                await Seconds(1.8f);
                if (G.State.IsDefeated(enc)) break;
            }
        }

        static void Invuln()
        {
            var p = M.Player;
            if (p == null) return;
            p.Invuln = 9999;
            p.Restore();
        }

        async Task Story()
        {
            var t0 = Time.realtimeSinceStartup;
            await Seconds(2);
            Log("story: new game");
            var ng = M.NewGame(Characters.Kael, 2);
            try { await WaitFor("zone plaza", () => ng.IsFaulted || (M.World.ZoneId == "plaza" && M.Mode == GameMode.Play && !M.World.Loading), 180); }
            catch (Exception) { throw new Exception($"new game did not reach the plaza (mode {M.Mode}, zone {M.World.ZoneId}, loading {M.World.Loading}, task {ng.Status})"); }
            if (ng.IsFaulted) throw new Exception("NewGame failed: " + ng.Exception);
            await Seconds(3); await Capture("s01_intro"); await Flush(60);
            await ExpectStage("m1_awakening", "wake");
            G.State.SetFlag("tut_moved");
            await ExpectStage("m1_awakening", "monument");
            Tp(0, 0.8f, 8.5f); await Seconds(0.5f); Interact("i_monument");
            await ExpectStage("m1_awakening", "fight");
            await Seconds(1); await Capture("s02_m1_fight");
            Invuln();
            await Kill("e_plaza_drones");
            await ExpectStage("m1_awakening", "powerup");
            Tp(3.5f, 0.2f, 9.4f); await Seconds(1.5f);
            await ExpectStage("m1_awakening", "meet");
            Tp(16, 0.3f, -16); await Seconds(2); await Capture("s03_m1_meeting"); await Flush(80);
            await ExpectStage("m1_awakening", "done");
            await ExpectStage("m2_dead_signal", "enter");

            // ---- M2
            Tp(-27, -4.0f, 16.4f); await ZoneIs("metro"); await Seconds(1); await Capture("s04_m2_metro");
            await ExpectStage("m2_dead_signal", "concourse");
            Invuln(); await Kill("e_metro_concourse");
            await ExpectStage("m2_dead_signal", "power");
            foreach (var (id, n) in new[] { ("i_junction_1", 3), ("i_junction_2", 2), ("i_junction_3", 1) })
                for (var i = 0; i < n; i++) { Interact(id); await Seconds(0.12f); }
            await ExpectStage("m2_dead_signal", "transmitter");
            Invuln(); await Kill("e_metro_platform");
            Tp(-34, 0.1f, 37.5f); await Seconds(0.4f); Interact("i_transmitter"); await Flush(60);
            await ExpectStage("m2_dead_signal", "spur");
            Invuln(); await Kill("e_metro_tunnel");
            Tp(64, -1.2f, 55); await ZoneIs("facility"); await Seconds(1); await Capture("s05_m3_facility");

            // ---- M3
            await ExpectStage("m3_researcher", "labs");
            Tp(-16, 0.1f, 15); await ExpectStage("m3_researcher", "logs");
            Invuln(); await Kill("e_fac_labs");
            foreach (var id in new[] { "i_log_echo", "i_log_keys", "i_log_cascade" }) { Interact(id); await Seconds(0.4f); await Flush(20); }
            await ExpectStage("m3_researcher", "data");
            Interact("i_maren_terminal"); await Flush(40);
            await ExpectStage("m3_researcher", "truth");
            // Echo Sight (Giva) next to the hidden wall.
            if (G.State.D.Character != Characters.Lyra) { M.SwapCharacter(); await Seconds(1); }
            Tp(-11, 0.1f, -10); await Seconds(0.4f);
            M.EchoPulse(M.Player.Position, 18, 3); await Seconds(2.5f);
            await Capture("s06_m3_echo");
            Tp(-24, 0.1f, -16); await Seconds(0.5f); Interact("i_maren_final"); await Flush(60);
            await ExpectStage("m3_researcher", "elite");
            Tp(0, 0.1f, 22); await Seconds(1.5f); await Capture("s07_m3_warden");
            Invuln(); await Kill("e_fac_warden");
            await ExpectStage("m3_researcher", "clearance");
            Tp(0, 0.1f, 10.5f); await Seconds(0.5f); Interact("pickup_clearance"); await Seconds(0.8f);
            await ExpectStage("m3_researcher", "done");
            await ExpectStage("m4_vault", "lift");

            // ---- M4
            Tp(-37, 0.1f, -9); await Seconds(0.4f); M.World.Interact(); await ZoneIs("vault"); await Seconds(1); await Capture("s08_m4_vault");
            await ExpectStage("m4_vault", "traverse");
            Invuln(); await Kill("e_vault_hall");
            Tp(0, 0.1f, 42); await ExpectStage("m4_vault", "puzzle");
            foreach (var (id, n) in new[] { ("i_resonator_1", 2), ("i_resonator_3", 3) })
                for (var i = 0; i < n; i++) { Interact(id); await Seconds(0.12f); }
            await ExpectStage("m4_vault", "upgrade");
            Tp(0, 0.1f, 63.5f); await Seconds(1.2f); Interact("i_attunement"); await Flush(40);
            await ExpectStage("m4_vault", "guardian");
            Invuln(); await Kill("e_vault_deep");
            Invuln();
            Tp(0, 0.1f, 87); await Seconds(1.5f); await Capture("s09_m4_guardian"); await Flush(60);
            await ExpectStage("m4_vault", "survive");
            for (var i = 0; i < 70; i++)
            {
                Invuln(); await Seconds(1);
                if (M.World.Script is VaultZone vz && vz.BlastOpen) break;
            }
            await Capture("s10_m4_door");
            Tp(0, 0.1f, 109); await ExpectStage("m4_vault", "access");
            Tp(0, 0.1f, 111); await Seconds(0.4f); M.World.Interact(); await ZoneIs("core"); await Seconds(1); await Capture("s11_m5_core");

            // ---- M5
            await ExpectStage("m5_core", "listen");
            Tp(0, 0.1f, 22); await Seconds(0.4f); Interact("i_core_terminal"); await Flush(60);
            await ExpectStage("m5_core", "waves");
            Invuln(); await Kill("e_core_waves");
            await ExpectStage("m5_core", "boss", 90);
            await Flush(30); Invuln(); await Seconds(4); await Capture("s12_m5_boss");
            await Kill("e_core_guardian");
            await ExpectStage("m5_core", "release", 60);
            Tp(0, 1.3f, 4.5f); await Seconds(0.6f); Interact("i_core_heart");
            await Seconds(6); await Capture("s13_m5_ending");
            await WaitFor("credits", () => M.UI != null && M.UI.HasScreen("credits"), 240);
            await Seconds(1.5f); await Capture("s14_credits");
            report["storySeconds"] = Time.realtimeSinceStartup - t0;
            report["storyFlags"] = string.Join(",", G.State.D.Flags.Keys);
            report["story"] = "PASS";
            Log("main story complete");
        }
    }
}
