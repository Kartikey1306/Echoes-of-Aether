using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using UnityEngine;

namespace EOA
{
    /// <summary>Thrown inside cinematic scripts when the player skips.</summary>
    public sealed class CinematicSkipped : Exception { }

    /// <summary>
    /// Cinematic runner (port of Cinematics.ts): eased camera shots/cuts/drifts, subtitled lines with
    /// mouth animation, letterbox, fades, music cues, hold-to-skip, and conversation framing for NPC talks.
    /// Zone-specific scripts register themselves with <see cref="Register"/>.
    /// </summary>
    public sealed class Cinematics
    {
        public delegate Task Script(CineCtx c);
        readonly GameManager g;
        readonly Dictionary<string, (Script script, Action finalize)> scripts = new();
        public string Active { get; private set; }
        bool skipFlag;
        float skipHold;
        Vector3 fromPos, fromLook, toPos, toLook;
        float camT = 1, camDur = 1, fov = 50;
        bool framing;
        Vector3 framePos, frameLook;
        readonly List<GameObject> spawned = new();

        public Cinematics(GameManager g)
        {
            this.g = g;
            CinematicScripts.RegisterAll(this);
        }

        public void Register(string id, Script script, Action finalize = null) => scripts[id] = (script, finalize);
        public bool Has(string id) => scripts.ContainsKey(id);

        public void Stop()
        {
            if (Active != null) skipFlag = true;
            if (g.Cam != null) g.Cam.Cinematic = null;
            G.Presentation?.CinematicBars(false);
            G.Presentation?.ShowSkipPrompt(false);
        }

        public async Task Play(string id)
        {
            if (!scripts.TryGetValue(id, out var entry))
            {
                // No staged script: play the dialogue that carries its lines.
                if (GameData.Dialogues.ContainsKey(id + "_lines")) await g.PlayDialogue(id + "_lines", "cinematic");
                else Debug.LogWarning($"[cine] no script for {id}");
                return;
            }
            if (Active != null) return;
            Active = id;
            g.InCinematic = true;
            skipFlag = false;
            skipHold = 0;
            Bus.Emit(new CinematicStarted { Id = id });
            G.Input.EnableGameplay(false);
            GameInput.LockCursor(false);
            g.Player?.SetScripted(true);
            G.Presentation?.CinematicBars(true);
            G.Audio?.Duck(0.5f, 0.4f);
            var cam = g.Cam.Cam.transform;
            fromPos = toPos = cam.position;
            fromLook = toLook = cam.position + cam.forward;
            fov = g.Cam.Cam.fieldOfView;
            camT = camDur = 1;
            Enemy.FreezeAll = true;
            var skipped = false;
            try { await entry.script(new CineCtx(this, g)); }
            catch (CinematicSkipped) { skipped = true; }
            catch (Exception e) { Debug.LogError($"[cine] {id}: {e}"); }
            skipped |= skipFlag;
            Enemy.FreezeAll = false;
            g.Dialogue.Cancel();
            foreach (var go in spawned) if (go != null) UnityEngine.Object.Destroy(go);
            spawned.Clear();
            try { entry.finalize?.Invoke(); }
            catch (Exception e) { Debug.LogError($"[cine] finalize {id}: {e}"); }
            if (G.Presentation is UIManager ui) ui.FadeInstant(false);
            G.Presentation?.CinematicBars(false);
            G.Presentation?.ShowSkipPrompt(false);
            G.Audio?.Duck(0, 0.4f);
            g.Cam.Cinematic = null;
            g.Post?.CinematicDof(false);
            if (g.Player != null)
            {
                g.Player.SetScripted(false);
                g.Cam.SnapBehind(g.Player.YawDeg * Mathf.Deg2Rad);
            }
            Active = null;
            g.InCinematic = false;
            Bus.Emit(new CinematicEnded { Id = id, Skipped = skipped });
            if (g.Mode == GameMode.Play && !g.Paused)
            {
                G.Input.EnableGameplay(true);
                GameInput.LockCursor(true);
            }
        }

        // ------------------------------------------------------------------ per frame

        public void Tick(float dt)
        {
            if (Active != null)
            {
                // Hold to skip (or tap when hold-to-skip is disabled in accessibility settings).
                var hold = G.Settings.Data.Accessibility.HoldToSkip;
                if (G.Input.Held("skip") || G.Input.Held("pause"))
                {
                    skipHold += dt;
                    G.Presentation?.ShowSkipPrompt(true, Mathf.Clamp01(skipHold / 1.1f));
                    if (!hold || skipHold > 1.1f) skipFlag = true;
                }
                else if (skipHold > 0)
                {
                    skipHold = Mathf.Max(0, skipHold - dt * 2);
                    G.Presentation?.ShowSkipPrompt(skipHold > 0, skipHold / 1.1f);
                }
                camT += dt;
                var k = Ease(Mathf.Clamp01(camT / Mathf.Max(0.001f, camDur)));
                var pos = Vector3.Lerp(fromPos, toPos, k);
                var look = Vector3.Lerp(fromLook, toLook, k);
                g.Cam.Cinematic = (pos, look, fov);
                // Shallow depth of field on the subject during cinematics (High effects only).
                if (G.Settings.Data.Graphics.Effects == "high") g.Post?.CinematicDof(true, Vector3.Distance(pos, look));
            }
            else if (framing)
            {
                g.Cam.Cinematic = (framePos, frameLook, 42);
            }
        }

        static float Ease(float t) => t < 0.5f ? 4 * t * t * t : 1 - Mathf.Pow(-2 * t + 2, 3) / 2;

        /// <summary>Over-the-shoulder two-shot for NPC conversations.</summary>
        public void FrameConversation(Hero p, Npc npc)
        {
            var a = p.Position + Vector3.up * 1.55f;
            var b = npc.Position + Vector3.up * (npc.Id == "nia" ? 1.05f : 1.55f);
            var mid = (a + b) / 2;
            var dir = b - a; dir.y = 0;
            var side = Vector3.Cross(Vector3.up, dir.normalized);
            var dist = Mathf.Max(1.2f, dir.magnitude);
            framePos = a - dir.normalized * 1.5f + side * 0.95f * Mathf.Sign(UnityEngine.Random.value - 0.5f + 0.01f) + Vector3.up * 0.15f;
            frameLook = Vector3.Lerp(mid, b, 0.6f);
            if (Physics.Linecast(mid, framePos, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore)) framePos = mid + side * dist * 1.1f + Vector3.up * 0.3f;
            framing = true;
        }

        public void ReleaseFraming()
        {
            framing = false;
            if (Active == null && g.Cam != null) g.Cam.Cinematic = null;
        }

        public void SetSpeaker(string id) { }

        // ------------------------------------------------------------------ context

        public sealed class CineCtx
        {
            readonly Cinematics c;
            public readonly GameManager G;
            internal CineCtx(Cinematics c, GameManager g) { this.c = c; G = g; }

            void Guard() { if (c.skipFlag) throw new CinematicSkipped(); }

            async Task Until(Func<bool> cond)
            {
                while (!cond())
                {
                    if (c.skipFlag) throw new CinematicSkipped();
                    await Awaitable.NextFrameAsync();
                }
            }

            public bool Skipped => c.skipFlag;

            /// <summary>Move from (posA, lookA) to (posB, lookB) over dur seconds (eased).</summary>
            public async Task Shot(Vector3 posA, Vector3 lookA, Vector3 posB, Vector3 lookB, float dur, float fov = 0)
            {
                Guard();
                c.fromPos = posA; c.fromLook = lookA; c.toPos = posB; c.toLook = lookB;
                c.camT = 0; c.camDur = dur;
                if (fov > 0) c.fov = fov;
                await Until(() => c.camT >= c.camDur);
            }

            public void Cut(Vector3 pos, Vector3 look, float fov = 0)
            {
                c.fromPos = c.toPos = pos; c.fromLook = c.toLook = look;
                c.camT = c.camDur = 1;
                if (fov > 0) c.fov = fov;
            }

            public void Drift(Vector3 posB, Vector3 lookB, float dur)
            {
                c.fromPos = G.Cam.Cam.transform.position; c.fromLook = c.toLook;
                c.toPos = posB; c.toLook = lookB;
                c.camT = 0; c.camDur = dur;
            }

            public async Task Wait(float seconds)
            {
                Guard();
                var end = Time.time + seconds;
                await Until(() => Time.time >= end);
            }

            /// <summary>Play the lines of a dialogue (optionally a node range) as cinematic subtitles.</summary>
            public async Task Lines(string dialogueId, string from = null, string to = null)
            {
                Guard();
                var all = G.Dialogue.LinearLines(dialogueId);
                var started = from == null;
                foreach (var l in all)
                {
                    if (!started && l.Node == from) started = true;
                    if (!started) continue;
                    Guard();
                    Bus.Emit(new DialogueLineShown { Speaker = l.Speaker?.Id, Dialogue = l.Dialogue, Node = l.Node });
                    var view = G.DialogueView;
                    var task = view != null ? view.Line(l, LineMode.Auto) : Delay(Mathf.Max(2f, VoiceOver.Remaining + 0.3f));
                    while (!task.IsCompleted)
                    {
                        if (c.skipFlag) { view?.End(); throw new CinematicSkipped(); }
                        await Awaitable.NextFrameAsync();
                    }
                    if (to != null && l.Node == to) break;
                }
                G.DialogueView?.End();
                Bus.Emit(new DialogueLineShown { Speaker = null });
            }

            static async Task Delay(float s) => await Awaitable.WaitForSecondsAsync(s);

            public async Task Fade(bool toBlack, float seconds)
            {
                Guard();
                var t = global::EOA.G.Presentation?.Fade(toBlack, seconds) ?? Task.CompletedTask;
                while (!t.IsCompleted)
                {
                    if (c.skipFlag) throw new CinematicSkipped();
                    await Awaitable.NextFrameAsync();
                }
            }
            public void Music(string mood) => global::EOA.G.Audio?.SetMusic(mood);
            public void Sfx(string id, Vector3? pos = null) => global::EOA.G.Audio?.Play(id, pos);
            public void Toast(string text) => global::EOA.G.Presentation?.Toast(text, ToastKind.Quest);

            /// <summary>Translucent Aether echo of a character (e.g. Dr. Maren) for staging; removed after the cinematic.</summary>
            public CharacterModel SpawnEcho(string prefabName, Vector3 pos, float yawDeg)
            {
                var prefab = Resources.Load<GameObject>("Characters/" + prefabName);
                if (prefab == null) return null;
                var go = UnityEngine.Object.Instantiate(prefab, pos, Quaternion.Euler(0, yawDeg, 0));
                c.spawned.Add(go);
                var m = go.GetComponent<CharacterModel>();
                m?.SetEcho(true, new Color(0.62f, 0.75f, 1f));
                return m;
            }

            public void Track(GameObject go) => c.spawned.Add(go);
        }
    }

    /// <summary>Zone cinematic scripts (cin_intro, cin_meeting, cin_guardian_reveal, cin_ending, cin_hidden_vault).</summary>
    public static partial class CinematicScripts
    {
        static partial void RegisterZoneScripts(Cinematics c);
        public static void RegisterAll(Cinematics c) => RegisterZoneScripts(c);
    }
}
