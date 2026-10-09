using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Combat-feel capture (autopilot mode "feel", or the combat smoke test started with -combatFeel):
    /// for Kael then Giva it scripts input-latency probes, a full combo + finisher on a Sentinel, a perfect dodge and a
    /// counter, a heavy deflect, Aether Pulse on a group and an ultimate, through the hero's real input path
    /// (<see cref="Hero.InjectPress"/>). Writes frame-sequence contact sheets (feel_*.png) and feel_report.json with
    /// input-to-motion latency, hit-stop durations (requested and measured), perfect dodges / deflects / poise breaks
    /// and frame times.
    /// </summary>
    public sealed partial class AutoPilot
    {
        /// <summary>Frame-time log and GPU frame bursts, after the camera rig has moved (LateUpdate order 1000).</summary>
        [DefaultExecutionOrder(1000)]
        sealed class FeelRecorder : MonoBehaviour
        {
            public bool RecordFrames;
            public readonly List<float> FrameMs = new(4096);
            public RenderTexture[] Rts;
            public int Want, Got, Every = 1;
            int skip;
            float globalStop = -1f;

            void LateUpdate()
            {
                if (RecordFrames) FrameMs.Add(Time.unscaledDeltaTime * 1000f);
                // Measure global (time-scale) hit-stops: real time spent below 0.1x.
                if (Time.timeScale < 0.1f && Time.timeScale > 0f && G.Manager != null && !G.Manager.Paused)
                {
                    if (globalStop < 0f) globalStop = Time.realtimeSinceStartup;
                }
                else if (globalStop >= 0f)
                {
                    CombatTelemetry.Record("global_stop_real", Time.realtimeSinceStartup - globalStop);
                    globalStop = -1f;
                }
                if (Rts == null || Got >= Want) return;
                if (skip-- > 0) return;
                skip = Every - 1;
                var cam = G.Manager != null && G.Manager.Cam != null ? G.Manager.Cam.Cam : null;
                if (cam == null) return;
                var prev = cam.targetTexture;
                cam.targetTexture = Rts[Got];
                cam.Render();
                cam.targetTexture = prev;
                Got++;
            }
        }

        const int BurstW = 640, BurstH = 360, BurstMax = 24;
        Vector3 arenaPos;
        float arenaYaw;
        FeelRecorder rec;
        readonly List<Dictionary<string, object>> feelSegments = new();

        static bool FeelRequested => Mode == "feel" || Environment.GetCommandLineArgs().Contains("-combatFeel");

        async Task CombatFeel()
        {
            rec = gameObject.AddComponent<FeelRecorder>();
            rec.Rts = new RenderTexture[BurstMax];
            for (var i = 0; i < BurstMax; i++) rec.Rts[i] = new RenderTexture(BurstW, BurstH, 24, RenderTextureFormat.ARGB32) { name = "feel_burst_" + i };
            CombatTelemetry.Entries.Clear();
            CombatTelemetry.Enabled = true;
            // Batch mode presents nothing and would run uncapped (~700 fps): pace it like a 60 Hz game so
            // frame-count latency and hit-stop measurements are representative.
            var prevRate = Application.targetFrameRate;
            QualitySettings.vSyncCount = 0;
            Application.targetFrameRate = 60;
            try
            {
                await FeelHero(Characters.Kael);
                await FeelHero(Characters.Lyra);
            }
            catch (Exception e) { errors.Add("combat feel aborted: " + e); }
            finally
            {
                CombatTelemetry.Enabled = false;
                Application.targetFrameRate = prevRate;
                WriteFeelReport();
                foreach (var rt in rec.Rts) if (rt != null) rt.Release();
            }
        }

        // ------------------------------------------------------------------ scripted fight

        async Task FeelHero(string character)
        {
            var tag = character == Characters.Kael ? "kael" : "giva";
            Log("feel: new game as " + tag);
            var ng = M.NewGame(character, 2);
            await Until(() => M.Cinematics.Active != null || ng.IsCompleted, 90);
            if (M.Cinematics.Active != null) M.Cinematics.Stop();
            await Until(() => ng.IsCompleted, 90);
            await Until(() => M.Mode == GameMode.Play && M.Cinematics.Active == null && !M.World.Loading, 30);
            await Flush(10);
            await Seconds(1.5f);
            var p = M.Player;
            G.State.Unlock(character == Characters.Kael ? "dash" : "step");
            G.State.Unlock("echo");
            G.Inventory.Add("up_core_attunement", 1, true);
            foreach (var e in Enemy.All.ToList()) if (e != null) e.Despawn();
            arenaPos = p.Position;
            arenaYaw = p.YawDeg;
            rec.RecordFrames = true;

            // 1) Input -> first visible motion (idle hero, frozen dummy so nothing else moves the hand).
            var fwd = p.transform.forward;
            var dummy = Spawn("sentinel", p.Position + fwd * 3.3f, p.YawDeg + 180f);
            dummy.Frozen = true;
            M.Cam.SnapBehind(p.YawDeg * Mathf.Deg2Rad);
            await Seconds(1.2f);
            for (var i = 0; i < 3; i++)
            {
                p.InjectPress(i == 1 ? "heavy" : "light");
                await Seconds(1.6f);
            }
            dummy.Frozen = false;
            dummy.Despawn();
            p.Restore();
            await Seconds(1f);

            // 2) Full combo + heavy finisher on a Sentinel, captured as a frame sequence.
            ResetArena(p);
            var s = Spawn("sentinel", p.Position + p.transform.forward * 3.2f, p.YawDeg + 180f);
            await Seconds(0.3f);
            var seg = Segment(tag + "_combo");
            var chainLen = character == Characters.Kael ? 3 : 2;
            // Gameplay camera, then the same string from a side camera (trails and reactions read best side-on).
            for (var pass = 0; pass < 2; pass++)
            {
                if (pass == 1)
                {
                    if (s != null) s.Despawn();
                    p.Restore();
                    ResetArena(p);
                    s = Spawn("sentinel", p.Position + p.transform.forward * 3.2f, p.YawDeg + 180f);
                    await Seconds(0.6f);
                    SideCam(p, s);
                }
                StartBurst(24, character == Characters.Kael ? 4 : 3);
                for (var i = 0; i < chainLen; i++) { p.InjectPress("light"); await Seconds(0.22f); }
                p.InjectPress("heavy");
                await FinishBurst($"feel_{tag}_combo{(pass == 1 ? "_side" : "")}");
            }
            await Seconds(1.2f);
            M.Cam.Cinematic = null;
            seg["sentinelHealth01"] = s != null && s.Alive ? s.Health01 : 0f;
            seg["sentinelStaggered"] = s != null && s.IsStaggered;
            await Capture($"feel_{tag}_after_combo");
            if (s != null && s.Alive) s.Despawn();
            p.Restore();
            await Seconds(0.8f);

            // 3) Perfect dodge against a Sentinel blow, then the counter.
            for (var attempt = 0; attempt < 3; attempt++)
            {
                ResetArena(p);
                var foe = Spawn("sentinel", p.Position + p.transform.forward * 2.6f, p.YawDeg + 180f, true);
                var landing = await Until(() => foe != null && foe.Alive && foe.ThreatIn >= 0f && foe.ThreatIn <= 0.1f, 10);
                if (!landing) { warnings.Add($"feel: {tag} sentinel never attacked (dodge attempt {attempt})"); foe?.Despawn(); continue; }
                var pdBefore = Count("perfect_dodge");
                SideCam(p, foe);
                StartBurst(16, 3);
                p.InjectPress("dash");
                await Seconds(0.35f);
                p.InjectPress("heavy");
                await FinishBurst($"feel_{tag}_perfect_dodge");
                var ok = Count("perfect_dodge") > pdBefore;
                Segment(tag + "_perfect_dodge")["ok"] = ok;
                await Seconds(1f);
                M.Cam.Cinematic = null;
                foe?.Despawn();
                p.Restore();
                await Seconds(0.8f);
                if (ok) break;
            }

            // 4) Deflect: heavy timed into a Sentinel blow.
            for (var attempt = 0; attempt < 3; attempt++)
            {
                ResetArena(p);
                var foe = Spawn("sentinel", p.Position + p.transform.forward * 2.6f, p.YawDeg + 180f, true);
                var landing = await Until(() => foe != null && foe.Alive && foe.ThreatIn >= 0f && foe.ThreatIn <= 0.08f, 10);
                if (!landing) { warnings.Add($"feel: {tag} sentinel never attacked (deflect attempt {attempt})"); foe?.Despawn(); continue; }
                var before = Count("deflect");
                SideCam(p, foe);
                StartBurst(16, 2);
                p.InjectPress("heavy");
                await FinishBurst($"feel_{tag}_deflect");
                var ok = Count("deflect") > before;
                Segment(tag + "_deflect")["ok"] = ok;
                await Seconds(1f);
                M.Cam.Cinematic = null;
                foe?.Despawn();
                p.Restore();
                await Seconds(0.8f);
                if (ok) break;
            }

            // 5) Ability on a group (Aether Pulse for Kael; Echo Sight for Giva).
            ResetArena(p);
            var group = Ring(p, 4, 3.4f);
            await Seconds(0.4f);
            StartBurst(16, 3);
            p.InjectPress("ability");
            await FinishBurst($"feel_{tag}_ability");
            Segment(tag + "_ability")["alive"] = group.Count(e => e != null && e.Alive);
            await Seconds(0.8f);
            await Capture($"feel_{tag}_ability_after");
            foreach (var e in group) if (e != null && e.Alive) e.Despawn();
            p.Restore();
            await Seconds(0.8f);

            // 6) Ultimate on a group.
            ResetArena(p);
            group = Ring(p, 3, 4f);
            await Seconds(0.4f);
            p.DebugFillUltimate();
            p.InjectPress("ultimate");
            await Seconds(character == Characters.Kael ? 0.55f : 0.3f);
            StartBurst(16, 3);
            await FinishBurst($"feel_{tag}_ultimate");
            Segment(tag + "_ultimate")["alive"] = group.Count(e => e != null && e.Alive);
            await Seconds(1.5f);
            foreach (var e in group) if (e != null && e.Alive) e.Despawn();

            // 7) Free fight: two Sentinels and a Stalker with real AI for frame times and robustness (debug finish).
            p.Restore();
            ResetArena(p);
            group = Ring(p, 3, 6f, true);
            var t0 = Time.realtimeSinceStartup;
            var presses = new[] { "light", "light", "light", "heavy", "dash", "light", "light", "heavy" };
            var k = 0;
            while (Time.realtimeSinceStartup - t0 < 10f && group.Any(e => e != null && e.Alive))
            {
                p.InjectPress(presses[k++ % presses.Length]);
                await Seconds(0.28f);
                if (p.Health < 30) p.Restore();
            }
            await Capture($"feel_{tag}_free_fight");
            foreach (var e in group) if (e != null && e.Alive) e.Kill();
            await Seconds(2.5f);
            rec.RecordFrames = false;
            Log($"feel: {tag} done");
        }

        /// <summary>Back to the open spot the hero started on, facing the same way (enemies spawn in front).</summary>
        void ResetArena(Hero p)
        {
            p.Teleport(arenaPos, arenaYaw);
            M.Cam.SnapBehind(arenaYaw * Mathf.Deg2Rad);
        }

        /// <summary>Side-on framing of the hero and a foe for the frame bursts.</summary>
        static void SideCam(Hero p, Enemy foe)
        {
            var a = p.Position;
            var b = foe != null ? foe.Position : a + p.transform.forward * 3f;
            var mid = (a + b) * 0.5f;
            var along = b - a; along.y = 0;
            along = along.sqrMagnitude > 0.01f ? along.normalized : p.transform.forward;
            var side = new Vector3(along.z, 0, -along.x);
            M.Cam.Cinematic = (mid + side * 4.6f - along * 0.6f + Vector3.up * 1.6f, mid + Vector3.up * 1.05f, 48f);
        }

        Dictionary<string, object> Segment(string name)
        {
            var d = new Dictionary<string, object> { ["name"] = name, ["frame"] = Time.frameCount };
            feelSegments.Add(d);
            return d;
        }

        static int Count(string prefix) => CombatTelemetry.Entries.Count(e => e.Kind.StartsWith(prefix, StringComparison.Ordinal));

        static Enemy Spawn(string type, Vector3 pos, float yawDeg, bool aggro = false)
        {
            var g = EnemyHost.GroundAt(pos + Vector3.up * 2f, 6f);
            if (g.HasValue) pos.y = g.Value;
            return EnemyFactory.Create(type, pos, yawDeg, null, "feel_test", aggro);
        }

        static List<Enemy> Ring(Hero p, int n, float r, bool aggro = false)
        {
            var list = new List<Enemy>();
            for (var i = 0; i < n; i++)
            {
                var a = p.YawDeg * Mathf.Deg2Rad + (i - (n - 1) * 0.5f) * (Mathf.PI * 2f / Mathf.Max(3, n + 1));
                var pos = p.Position + new Vector3(Mathf.Sin(a), 0, Mathf.Cos(a)) * r;
                var e = Spawn(i % 3 == 2 ? "stalker" : "sentinel", pos, a * Mathf.Rad2Deg + 180f, aggro);
                if (e != null) list.Add(e);
            }
            return list;
        }

        // ------------------------------------------------------------------ frame bursts

        void StartBurst(int frames, int every)
        {
            rec.Got = 0;
            rec.Every = Mathf.Max(1, every);
            rec.Want = Mathf.Min(frames, BurstMax);
            CombatTelemetry.Record("burst_start");
        }

        /// <summary>Wait for the burst, then write a contact sheet (4 columns, time runs left-to-right, top-to-bottom).</summary>
        async Task FinishBurst(string name)
        {
            await Until(() => rec.Got >= rec.Want, 15);
            var n = rec.Got;
            rec.Want = 0;
            CombatTelemetry.Record("burst_end");
            if (n == 0) { warnings.Add("empty burst " + name); return; }
            const int cols = 4;
            var rows = (n + cols - 1) / cols;
            var sheet = new Texture2D(BurstW * cols, BurstH * rows, TextureFormat.RGBA32, false);
            var clear = new Color32[BurstW * cols * BurstH * rows];
            sheet.SetPixels32(clear);
            for (var i = 0; i < n; i++)
            {
                var tex = Read(rec.Rts[i], BurstW, BurstH);
                var col = i % cols;
                var row = rows - 1 - i / cols;
                sheet.SetPixels(col * BurstW, row * BurstH, BurstW, BurstH, tex.GetPixels());
                Destroy(tex);
            }
            sheet.Apply();
            File.WriteAllBytes(Path.Combine(OutDir, name + ".png"), sheet.EncodeToPNG());
            Destroy(sheet);
            Log("burst " + name + " frames " + n);
        }

        // ------------------------------------------------------------------ report

        void WriteFeelReport()
        {
            var entries = CombatTelemetry.Entries.ToList();
            object Stats(IEnumerable<float> xs)
            {
                var a = xs.OrderBy(x => x).ToArray();
                if (a.Length == 0) return null;
                return new { n = a.Length, min = a[0], avg = a.Average(), p50 = a[a.Length / 2], p95 = a[Mathf.Min(a.Length - 1, (int)(a.Length * 0.95f))], max = a[a.Length - 1] };
            }
            // Frames inside capture bursts are slowed by the extra camera renders: keep them out of the timing stats.
            var bursts = new List<(int a, int b)>();
            for (var i = 0; i < entries.Count; i++)
                if (entries[i].Kind == "burst_start")
                {
                    var end = entries.Skip(i).FirstOrDefault(x => x.Kind == "burst_end");
                    bursts.Add((entries[i].Frame, end.Kind != null ? end.Frame : int.MaxValue));
                }
            bool Clean(CombatTelemetry.Entry e) => !bursts.Any(r => e.Frame >= r.a - 2 && e.Frame <= r.b + 2);
            var firstMotion = entries.Where(e => e.Kind.StartsWith("first_motion_", StringComparison.Ordinal) && !e.Kind.EndsWith("_queued", StringComparison.Ordinal)).ToList();
            var report2 = new Dictionary<string, object>
            {
                ["firstMotionFrames"] = Stats(firstMotion.Select(e => e.A)),
                ["firstMotionMs"] = Stats(firstMotion.Select(e => e.B)),
                ["firstMotion"] = firstMotion.Select(e => new { e.Kind, frames = e.A, ms = e.B }).ToList(),
                ["noMotion"] = entries.Count(e => e.Kind.StartsWith("no_motion_", StringComparison.Ordinal)),
                ["bufferedExecFrames"] = Stats(entries.Where(e => e.Kind.StartsWith("exec_", StringComparison.Ordinal)).Select(e => e.A)),
                ["bufferExpired"] = entries.Count(e => e.Kind == "buffer_expired"),
                ["hitstopLocalRequested"] = Stats(entries.Where(e => e.Kind == "hitstop_local").Select(e => e.A * 1000f)),
                ["hitstopGlobalRequested"] = Stats(entries.Where(e => e.Kind == "hitstop_global").Select(e => e.A * 1000f)),
                ["hitstopLocalMeasuredMs"] = Stats(entries.Where(e => e.Kind == "freeze_real").Select(e => e.A * 1000f)),
                ["hitstopLocalMeasuredMsClean"] = Stats(entries.Where(e => e.Kind == "freeze_real" && Clean(e)).Select(e => e.A * 1000f)),
                ["firstMotionCleanFrames"] = Stats(firstMotion.Where(Clean).Select(e => e.A)),
                ["firstMotionCleanMs"] = Stats(firstMotion.Where(Clean).Select(e => e.B)),
                ["hitstopGlobalMeasuredMs"] = Stats(entries.Where(e => e.Kind == "global_stop_real").Select(e => e.A * 1000f)),
                ["slowmo"] = entries.Where(e => e.Kind == "slowmo").Select(e => new { scale = e.A, seconds = e.B }).ToList(),
                ["hitstopByWeightMs"] = entries.Where(e => e.Kind.StartsWith("hitstop_", StringComparison.Ordinal)).GroupBy(e => Mathf.RoundToInt(e.A * 1000f)).ToDictionary(g => g.Key.ToString(), g => g.Count()),
                ["swings"] = entries.Count(e => e.Kind.StartsWith("swing_", StringComparison.Ordinal)),
                ["perfectDodges"] = entries.Where(e => e.Kind.StartsWith("perfect_dodge", StringComparison.Ordinal)).Select(e => new { e.Kind, sinceDash = e.A }).ToList(),
                ["deflects"] = entries.Count(e => e.Kind == "deflect"),
                ["poiseBreaks"] = entries.Count(e => e.Kind == "poise_break"),
                ["kills"] = entries.Count(e => e.Kind == "kill"),
                ["playerStaggers"] = entries.Count(e => e.Kind == "player_stagger"),
                ["frameMs"] = Stats(rec != null ? rec.FrameMs : new List<float>()),
                ["segments"] = feelSegments,
                ["log"] = entries.Take(1500).Select(e => $"{e.Frame} {e.Real:0.000} {e.Kind} {e.A:0.###} {e.B:0.###}").ToList(),
            };
            report["feel"] = report2;
            try
            {
                File.WriteAllText(Path.Combine(OutDir, "feel_report.json"), Newtonsoft.Json.JsonConvert.SerializeObject(report2, Newtonsoft.Json.Formatting.Indented));
            }
            catch (Exception e) { errors.Add("feel report: " + e.Message); }
        }
    }
}
