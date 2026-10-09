using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.UIElements;

namespace EOA
{
    /// <summary>
    /// Dialogue presentation: interactive conversation panel (portrait, coloured speaker name, typewriter text,
    /// choices) and auto-paced radio/cinematic subtitles. Honours the accessibility subtitle settings.
    /// </summary>
    public sealed class DialogueView : IDialogueView
    {
        public readonly VisualElement Root;
        readonly UIManager ui;
        readonly VisualElement panel, pt, ch, cont, subs, subsLine;
        readonly Label ptInitial, nm, tx, contKey, subsWho, subsText;

        public VisualElement ChoicesRoot => ch;
        public bool ChoicesActive { get; private set; }
        /// <summary>True while an interactive line or choice is on screen.</summary>
        public bool PanelVisible => U.Shown(panel);

        bool subtitles = true, speakerNames = true;
        string full = "";
        float shown;
        const float TypeSpeed = 70;
        float canAdvanceAt;
        bool autoLine;
        float autoUntil;
        int lastAdvanceFrame = -1;
        TaskCompletionSource<bool> lineTcs;
        TaskCompletionSource<string> chooseTcs;
        IReadOnlyList<DialogueChoice> currentChoices;

        static readonly Dictionary<string, float> SubSize = new() { ["small"] = 17, ["medium"] = 21, ["large"] = 25, ["xl"] = 31 };

        public DialogueView(UIManager ui)
        {
            this.ui = ui;
            Root = U.El("dialogue-root");
            Root.pickingMode = PickingMode.Ignore;

            pt = U.El("dlg-pt");
            ptInitial = U.Label("", "dlg-pt-initial");
            pt.Add(ptInitial);
            nm = U.Label("", "dlg-nm");
            tx = U.Label("", "dlg-tx");
            ch = U.El("dlg-ch");
            contKey = U.Keycap("E");
            cont = U.El("dlg-cont", U.Label(U.Up(U.T("dlg.continue")), "dlg-cont-t"), contKey);
            cont.pickingMode = PickingMode.Ignore;
            panel = U.El("dialogue panel", U.El("corner-tl"), U.El("corner-br"), pt, U.El("dlg-body", nm, tx, ch), cont);
            panel.RegisterCallback<ClickEvent>(_ => TryAdvance());
            U.Show(panel, false);
            Root.Add(panel);

            subsWho = U.Label("", "subs-who");
            subsText = U.Label("", "subs-text");
            subsLine = U.El("subs-line", subsWho, subsText);
            subs = U.El("subs", subsLine);
            subs.pickingMode = PickingMode.Ignore;
            subsLine.pickingMode = PickingMode.Ignore;
            U.Show(subs, false);
            Root.Add(subs);
        }

        public void ApplySettings(AccessibilitySettings a)
        {
            if (a == null) return;
            subtitles = a.Subtitles;
            speakerNames = a.SpeakerNames;
            var size = SubSize.TryGetValue(a.SubtitleSize ?? "medium", out var s) ? s : 21;
            subsText.style.fontSize = size;
            subsWho.style.fontSize = Mathf.Round(size * 0.82f);
            tx.style.fontSize = size;
            subsLine.style.backgroundColor = new Color(0, 0, 0, Mathf.Clamp01(a.SubtitleBackground));
            U.Show(subsWho, speakerNames && !string.IsNullOrEmpty(subsWho.text));
        }

        void SetSpeaker(ResolvedLine l)
        {
            var sp = l.Speaker;
            var col = U.Hex(sp?.Color, U.Text);
            nm.text = U.Up(sp?.Name ?? "");
            nm.style.color = col;
            var hasPortrait = sp != null && sp.Portrait != "none";
            U.Show(pt, hasPortrait);
            panel.EnableInClassList("no-portrait", !hasPortrait);
            if (!hasPortrait) return;
            var tex = U.Portrait(sp.Portrait);
            pt.style.backgroundImage = tex != null ? new StyleBackground(tex) : new StyleBackground(StyleKeyword.None);
            ptInitial.text = tex != null ? "" : (string.IsNullOrEmpty(sp.Name) ? "?" : sp.Name.Substring(0, 1).ToUpperInvariant());
            ptInitial.style.color = col;
            pt.style.backgroundColor = tex != null ? new StyleColor(StyleKeyword.Null) : new StyleColor(new Color(col.r * 0.18f, col.g * 0.18f, col.b * 0.18f, 1));
        }

        // ------------------------------------------------------------------ IDialogueView

        public Task Line(ResolvedLine line, LineMode mode)
        {
            ui.EnsureBuilt();
            CompleteLine();
            if (line == null) return Task.CompletedTask;
            Bus.Emit(new DialogueLineShown { Speaker = line.Speaker?.Id, Dialogue = line.Dialogue, Node = line.Node });
            lineTcs = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            if (mode == LineMode.Interactive)
            {
                autoLine = false;
                U.Show(subs, false);
                U.Show(panel, true);
                SetSpeaker(line);
                ch.Clear();
                SetChoicesActive(false);
                full = line.Text ?? "";
                shown = 0;
                tx.text = "";
                contKey.text = G.Input != null && G.Input.UsingGamepad ? "A" : G.Input?.Label("interact") ?? "E";
                U.Show(cont, true);
                canAdvanceAt = Time.unscaledTime + 0.25f;
                return lineTcs.Task;
            }
            // Radio / cinematic: subtitles only, auto-paced by reading time.
            autoLine = true;
            U.Show(panel, false);
            if (subtitles)
            {
                subsWho.text = U.Up(line.Speaker?.Name ?? "");
                subsWho.style.color = U.Hex(line.Speaker?.Color, U.Text);
                U.Show(subsWho, speakerNames && !string.IsNullOrEmpty(subsWho.text));
                subsText.text = line.Text ?? "";
                U.Show(subs, true);
            }
            // Recorded voice-over (if any) holds the line until it has been spoken.
            autoUntil = Time.unscaledTime + Mathf.Max(AutoDuration(line.Text), VoiceOver.Remaining + 0.3f);
            return lineTcs.Task;
        }

        /// <summary>Reading time: words / 2.6 per second + 0.5 s.</summary>
        public static float AutoDuration(string text)
        {
            if (string.IsNullOrEmpty(text)) return 0.5f;
            var words = text.Split(new[] { ' ', '\n', '\t' }, StringSplitOptions.RemoveEmptyEntries).Length;
            return words / 2.6f + 0.5f;
        }

        public Task<string> Choose(ResolvedLine line, IReadOnlyList<DialogueChoice> choices)
        {
            ui.EnsureBuilt();
            CompleteLine();
            chooseTcs?.TrySetResult(null);
            chooseTcs = new TaskCompletionSource<string>(TaskCreationOptions.RunContinuationsAsynchronously);
            U.Show(subs, false);
            U.Show(panel, true);
            U.Show(cont, false);
            if (line != null)
            {
                Bus.Emit(new DialogueLineShown { Speaker = line.Speaker?.Id, Dialogue = line.Dialogue, Node = line.Node });
                SetSpeaker(line);
                full = line.Text ?? "";
                shown = full.Length;
                tx.text = full;
            }
            ch.Clear();
            currentChoices = choices;
            if (choices == null || choices.Count == 0)
            {
                var t = chooseTcs;
                chooseTcs = null;
                t.TrySetResult(null);
                return t.Task;
            }
            for (var i = 0; i < choices.Count; i++)
            {
                var c = choices[i];
                var b = U.Btn($"{i + 1}. {c.Text}", () => Pick(c.Id), "btn dlg-choice", NavKind.Button, false);
                if (i == 0) b.AddToClassList("autofocus");
                ch.Add(b);
            }
            SetChoicesActive(true);
            GameInput.LockCursor(false);
            return chooseTcs.Task;
        }

        public void End()
        {
            U.Show(panel, false);
            U.Show(subs, false);
            ch.Clear();
            SetChoicesActive(false);
            currentChoices = null;
            CompleteLine();
            var t = chooseTcs;
            chooseTcs = null;
            t?.TrySetResult(null);
        }

        // ------------------------------------------------------------------ Control

        void SetChoicesActive(bool on)
        {
            if (ChoicesActive == on) return;
            ChoicesActive = on;
            ui.ChoicesChanged();
        }

        void Pick(string id)
        {
            if (!ChoicesActive) return;
            ch.Clear();
            SetChoicesActive(false);
            currentChoices = null;
            var t = chooseTcs;
            chooseTcs = null;
            t?.TrySetResult(id);
        }

        void CompleteLine()
        {
            var t = lineTcs;
            lineTcs = null;
            autoLine = false;
            if (t == null) return;
            U.Show(subs, false);
            t.TrySetResult(true);
        }

        /// <summary>Automation: pick the first offered choice (returns false when no choice is open).</summary>
        public bool PickFirstChoice()
        {
            if (!ChoicesActive || currentChoices == null || currentChoices.Count == 0) return false;
            Pick(currentChoices[0].Id);
            return true;
        }

        /// <summary>Skip the current line immediately (cinematic skip).</summary>
        public void ForceAdvance()
        {
            if (lineTcs == null) return;
            shown = full.Length;
            tx.text = full;
            CompleteLine();
        }

        void TryAdvance()
        {
            if (ChoicesActive || lineTcs == null || autoLine) return;
            if (lastAdvanceFrame == Time.frameCount) return;
            lastAdvanceFrame = Time.frameCount;
            if (shown < full.Length)
            {
                shown = full.Length;
                tx.text = full;
                return;
            }
            if (Time.unscaledTime < canAdvanceAt) return;
            CompleteLine();
        }

        public void Tick(float dt)
        {
            if (shown < full.Length && lineTcs != null && !autoLine)
            {
                shown = Mathf.Min(full.Length, shown + dt * TypeSpeed);
                tx.text = full.Substring(0, Mathf.FloorToInt(shown));
            }
            if (lineTcs != null && autoLine)
            {
                if (Time.unscaledTime >= autoUntil) CompleteLine();
                return;
            }
            if (ui.Top != null) return; // a menu is open on top of the conversation
            var inp = G.Input;
            if (inp == null || inp.Rebinding) return;
            if (lineTcs != null && !ChoicesActive && PanelVisible)
            {
                var mouse = Mouse.current != null && Mouse.current.leftButton.wasPressedThisFrame;
                if (inp.Submit.WasPressedThisFrame() || inp.Pressed("interact") || mouse) TryAdvance();
            }
            if (ChoicesActive && currentChoices != null && Keyboard.current != null)
            {
                for (var i = 0; i < currentChoices.Count && i < 9; i++)
                {
                    var key = Keyboard.current[Key.Digit1 + i];
                    if (key != null && key.wasPressedThisFrame)
                    {
                        G.Audio?.PlayUi("ui_click");
                        Pick(currentChoices[i].Id);
                        break;
                    }
                }
            }
        }
    }
}
