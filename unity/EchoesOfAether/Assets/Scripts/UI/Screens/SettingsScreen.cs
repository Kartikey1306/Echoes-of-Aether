using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.UIElements;

namespace EOA
{
    /// <summary>Settings: Gameplay, Graphics, Audio, Controls (rebinding), Accessibility, Language. Changes apply immediately.</summary>
    public static class SettingsScreen
    {
        static readonly string[] Sections = { "gameplay", "graphics", "audio", "controls", "accessibility", "language" };

        static readonly Dictionary<string, string> ActionLabels = new()
        {
            ["move"] = "Move", ["jump"] = "Jump", ["dash"] = "Sprint / Phase", ["light"] = "Light attack", ["heavy"] = "Heavy attack",
            ["bolt"] = "Aether Bolt (hold to aim)", ["ability"] = "Ability (Pulse / Echo Sight)", ["ultimate"] = "Ultimate",
            ["interact"] = "Interact", ["swap"] = "Switch character", ["lockon"] = "Lock on", ["crouch"] = "Crouch", ["inventory"] = "Inventory",
            ["map"] = "Map", ["journal"] = "Journal", ["skills"] = "Ability Matrix", ["quick1"] = "Use Aether Shard",
            ["quick2"] = "Use Phase Core", ["quick3"] = "Use Overcharge", ["quick4"] = "Use Shield Fragment", ["quick5"] = "Use Echo Fragment",
            ["throttle"] = "Accelerate", ["brake"] = "Brake / reverse", ["steerLeft"] = "Steer left", ["steerRight"] = "Steer right",
            ["handbrake"] = "Handbrake", ["horn"] = "Horn", ["vehicleReset"] = "Flip / reset car",
        };

        public static string ActionLabel(string a) => ActionLabels.TryGetValue(a, out var l) ? l : a;

        static string Pct(float v) => Mathf.RoundToInt(v * 100) + "%";
        static string F2(float v) => v.ToString("0.00");

        public static void Open(UIManager ui, bool inGame)
        {
            if (ui.HasScreen("settings")) return;
            var S = G.Settings;
            if (S == null) return;
            var section = 0;
            var renderedSection = -1;
            var dirty = false;
            string dirtySection = null;
            var saveDue = 0f;
            var m = ScreenKit.MakeModal(U.T("settings.title"), true);
            UIScreen screen = null;

            void Close() => ui.Pop("settings");

            // Slider drags mutate the data live and persist shortly after (avoids a disk write per pointer move).
            void Live(string sec, Action<SettingsData> change, bool deferEmit = false)
            {
                change(S.Data);
                dirty = true;
                dirtySection = sec;
                saveDue = Time.unscaledTime + (deferEmit ? 0.6f : 0.4f);
                if (!deferEmit) Bus.Emit(new SettingsChanged { Section = sec });
            }

            void Flush()
            {
                if (!dirty) return;
                dirty = false;
                var sec = dirtySection ?? "settings";
                S.Update(sec, _ => { }); // validate + persist + notify
            }

            void Upd(string sec, Action<SettingsData> change)
            {
                Flush();
                S.Update(sec, change);
            }

            m.Head.Add(U.Btn(U.T("settings.reset"), () => U.Run(async () =>
            {
                var sec = Sections[section];
                if (!await ui.Confirm(U.T("settings.reset"), $"Reset {U.T("settings." + sec)} settings to defaults?", U.T("settings.reset"))) return;
                Flush();
                S.ResetSection(sec);
                if (sec == "controls")
                {
                    G.Input?.LoadOverrides(S.Data.Controls.BindingOverrides);
                    ui.Hud?.RefreshKeys();
                }
                Render();
            }), "btn-small"));
            m.Head.Add(U.Btn(U.T("settings.close"), Close, "btn-small"));
            m.Foot.Add(U.Label("Changes apply immediately and are saved automatically.", "foot-note"));

            VisualElement Toggle(bool v, Action<bool> set) => new ToggleSwitch(v, set);
            VisualElement Choice(string v, (string, string)[] opts, Action<string> set) => new Seg(opts, v, set);
            VisualElement Slide(float v, float min, float max, float step, Func<float, string> fmt, Action<float> set) => new EoaSlider(v, min, max, step, fmt, set);
            void Add(VisualElement e) => m.Body.Add(e);
            VisualElement Row(string l, string d, VisualElement c) => ScreenKit.Row(l, d, c);

            void Render()
            {
                ScreenKit.FillTabs(m.Tabs, Array.ConvertAll(Sections, s => U.T("settings." + s)), section, i => { section = i; Render(); });
                m.Body.Clear();
                if (renderedSection != section) m.Body.scrollOffset = Vector2.zero;
                renderedSection = section;
                var d = S.Data;
                switch (Sections[section])
                {
                    case "gameplay":
                        Add(Row("Difficulty", "Story: gentler enemies and faster recovery. Hard: enemies hit harder and attack more often.",
                            Choice(d.Gameplay.Difficulty, new[] { ("story", "Story"), ("normal", "Normal"), ("hard", "Hard") }, v => Upd("gameplay", s => s.Gameplay.Difficulty = v))));
                        Add(Row("Camera sensitivity", null, Slide(d.Gameplay.CameraSensitivity, 0.2f, 3, 0.05f, F2, v => Live("gameplay", s => s.Gameplay.CameraSensitivity = v))));
                        Add(Row("Aim sensitivity", "Used while holding Aether Bolt to aim.", Slide(d.Gameplay.AimSensitivity, 0.1f, 2, 0.05f, F2, v => Live("gameplay", s => s.Gameplay.AimSensitivity = v))));
                        Add(Row("Invert Y axis", null, Toggle(d.Gameplay.InvertY, v => Upd("gameplay", s => s.Gameplay.InvertY = v))));
                        Add(Row("Camera shake", null, Slide(d.Gameplay.CameraShake, 0, 1.5f, 0.05f, Pct, v => Live("gameplay", s => s.Gameplay.CameraShake = v))));
                        break;
                    case "graphics":
                        Add(Row("Preset", "Applies a group of settings below.",
                            Choice(d.Graphics.Preset, new[] { ("low", "Low"), ("medium", "Medium"), ("high", "High"), ("ultra", "Ultra"), ("custom", "Custom") }, v =>
                            {
                                Flush();
                                if (v != "custom") S.ApplyPreset(v);
                                else S.Update("graphics", s => s.Graphics.Preset = "custom");
                                Render();
                            })));
                        Add(Row("Render scale", "Internal 3D resolution relative to the window (UI stays sharp).",
                            Choice(d.Graphics.Resolution == "native" ? "quality" : d.Graphics.Resolution, new[] { ("performance", "67%"), ("balanced", "85%"), ("quality", "100%") }, v => Gfx(s => s.Graphics.Resolution = v))));
                        Add(Row("Display mode", null,
                            Choice(d.Graphics.Fullscreen ? "full" : "win", new[] { ("win", "Windowed"), ("full", "Fullscreen") }, v => Upd("graphics", s => s.Graphics.Fullscreen = v == "full"))));
                        Add(Row("VSync / frame limit", "VSync follows your display refresh. 30 FPS caps rendering to save power.",
                            Choice(d.Graphics.FrameLimit, new[] { ("vsync", "VSync"), ("30", "30 FPS"), ("60", "60 FPS"), ("unlimited", "Unlimited") }, v => Upd("graphics", s => s.Graphics.FrameLimit = v))));
                        Add(Row("Shadows", null,
                            Choice(d.Graphics.Shadows, new[] { ("off", "Off"), ("low", "Low"), ("medium", "Medium"), ("high", "High") }, v => Gfx(s => s.Graphics.Shadows = v))));
                        Add(Row("Effects", "Bloom, particles, film grain and chromatic aberration.",
                            Choice(d.Graphics.Effects, new[] { ("low", "Low"), ("medium", "Medium"), ("high", "High") }, v => Gfx(s => s.Graphics.Effects = v))));
                        Add(Row("Textures", "Texture quality. Applies on the next area load.",
                            Choice(d.Graphics.Textures, new[] { ("low", "Low"), ("medium", "Medium"), ("high", "High") }, v => Gfx(s => s.Graphics.Textures = v))));
                        Add(Row("View distance", null,
                            Choice(d.Graphics.ViewDistance, new[] { ("low", "Low"), ("medium", "Medium"), ("high", "High") }, v => Gfx(s => s.Graphics.ViewDistance = v))));
                        Add(Row("Anti-aliasing", null,
                            Choice(d.Graphics.Antialiasing, new[] { ("off", "Off"), ("fxaa", "FXAA"), ("smaa", "SMAA"), ("taa", "TAA"), ("msaa", "MSAA 4x") }, v => Gfx(s => s.Graphics.Antialiasing = v))));
                        break;
                    case "audio":
                        Add(Row("Master volume", null, Slide(d.Audio.Master, 0, 1, 0.01f, Pct, v => Live("audio", s => s.Audio.Master = v))));
                        Add(Row("Music", null, Slide(d.Audio.Music, 0, 1, 0.01f, Pct, v => Live("audio", s => s.Audio.Music = v))));
                        Add(Row("Sound effects", null, Slide(d.Audio.Sfx, 0, 1, 0.01f, Pct, v => Live("audio", s => s.Audio.Sfx = v))));
                        Add(Row("Ambience", null, Slide(d.Audio.Ambience, 0, 1, 0.01f, Pct, v => Live("audio", s => s.Audio.Ambience = v))));
                        Add(Row("Voice-over", "Recorded dialogue (human recordings only). Off by default; subtitles are always available.",
                            Choice(d.Audio.VoiceOver ? "on" : "off", new[] { ("off", "Off"), ("on", "On") }, v => Upd("audio", s => s.Audio.VoiceOver = v == "on"))));
                        Add(Row("Voice volume", null, Slide(d.Audio.Voice, 0, 1, 0.01f, Pct, v => Live("audio", s => s.Audio.Voice = v))));
                        Add(Row("Interface", null, Slide(d.Audio.Ui, 0, 1, 0.01f, Pct, v => Live("audio", s => s.Audio.Ui = v))));
                        break;
                    case "controls":
                        Add(Row("Controller look speed", null, Slide(d.Controls.PadLookSpeed, 0.2f, 3, 0.05f, F2, v => Live("controls", s => s.Controls.PadLookSpeed = v))));
                        Add(Row("Controller vibration", null, Toggle(d.Controls.Vibration, v => Upd("controls", s => s.Controls.Vibration = v))));
                        var pad = Gamepad.current != null;
                        Add(ScreenKit.SectionTitle(pad ? "Bindings · Keyboard & Mouse / Controller" : "Bindings · Keyboard & Mouse (connect a controller to edit its bindings)"));
                        Add(U.El("bind-head", U.Label("", "row-l"), U.El("bind", U.Label("KEYBOARD / MOUSE", "bind-col"), U.Label("CONTROLLER", "bind-col"))));
                        foreach (var a in GameInput.Rebindable)
                        {
                            if (a == GameInput.DriveActions[0]) Add(ScreenKit.SectionTitle(U.T("settings.driving")));
                            Add(BindRow(a));
                        }
                        break;
                    case "accessibility":
                        Add(Row("Subtitles", null, Toggle(d.Accessibility.Subtitles, v => Upd("accessibility", s => s.Accessibility.Subtitles = v))));
                        Add(Row("Subtitle size", null,
                            Choice(d.Accessibility.SubtitleSize, new[] { ("small", "S"), ("medium", "M"), ("large", "L"), ("xl", "XL") }, v => Upd("accessibility", s => s.Accessibility.SubtitleSize = v))));
                        Add(Row("Subtitle background", null, Slide(d.Accessibility.SubtitleBackground, 0, 1, 0.05f, Pct, v => Live("accessibility", s => s.Accessibility.SubtitleBackground = v))));
                        Add(Row("Speaker names", null, Toggle(d.Accessibility.SpeakerNames, v => Upd("accessibility", s => s.Accessibility.SpeakerNames = v))));
                        Add(Row("Flash intensity", "Lightning, explosions and screen flashes.", Slide(d.Accessibility.FlashIntensity, 0, 1, 0.05f, Pct, v => Live("accessibility", s => s.Accessibility.FlashIntensity = v))));
                        Add(Row("Camera shake limit", "Caps all camera shake regardless of the gameplay setting.", Slide(d.Accessibility.CameraShake, 0, 1, 0.05f, Pct, v => Live("accessibility", s => s.Accessibility.CameraShake = v))));
                        Add(Row("UI scale", "Applies when you stop adjusting.", Slide(d.Accessibility.UiScale, 0.75f, 1.5f, 0.05f, Pct, v => Live("accessibility", s => s.Accessibility.UiScale = v, true))));
                        Add(Row("Hold to skip cinematics", "When off, a single press skips.", Toggle(d.Accessibility.HoldToSkip, v => Upd("accessibility", s => s.Accessibility.HoldToSkip = v))));
                        break;
                    case "language":
                        Add(Row("Language", "Additional languages can be added as locale files.",
                            Choice(string.IsNullOrEmpty(d.Language.Locale) ? "en" : d.Language.Locale, new[] { ("en", "English") }, v => Upd("language", s => s.Language.Locale = v))));
                        break;
                }
                if (ui.Top == screen) ui.Refocus();
            }

            void Gfx(Action<SettingsData> change)
            {
                Upd("graphics", s => { change(s); s.Graphics.Preset = "custom"; });
                Render();
            }

            VisualElement BindRow(string a)
            {
                var wrap = U.El("bind");
                foreach (var gamepad in new[] { false, true })
                {
                    var isPad = gamepad;
                    Button b = null;
                    b = U.Btn(U.BindingLabel(a, isPad), () => StartRebind(a, isPad, b), "bind-btn", NavKind.Grid, false);
                    if (a == "move") b.SetEnabled(false);
                    wrap.Add(b);
                }
                return ScreenKit.Row(ActionLabel(a), null, wrap);
            }

            void StartRebind(string action, bool gamepad, Button btn)
            {
                var inp = G.Input;
                if (inp == null || inp.Rebinding || action == "move") return;
                if (gamepad && Gamepad.current == null)
                {
                    ui.Toast("Connect a controller to rebind it.", ToastKind.Warn);
                    return;
                }
                var before = new Dictionary<string, string>();
                foreach (var x in GameInput.Rebindable) before[x] = U.BindingLabel(x, gamepad);
                btn.AddToClassList("listen");
                btn.text = "PRESS…";
                U.Run(async () =>
                {
                    // Let the key/click that opened the prompt go first so it is not captured as the new binding.
                    while (inp.Submit.IsPressed() || (Mouse.current != null && Mouse.current.leftButton.isPressed) ||
                           (Gamepad.current != null && Gamepad.current.buttonSouth.isPressed))
                        await Awaitable.NextFrameAsync();
                    inp.StartRebind(action, gamepad, ok =>
                    {
                        ui.SuppressNavigation(3);
                        if (ok)
                        {
                            S.Update("controls", s => s.Controls.BindingOverrides = inp.SaveOverrides());
                            foreach (var x in GameInput.Rebindable)
                            {
                                if (x == action) continue;
                                var now = U.BindingLabel(x, gamepad);
                                if (before.TryGetValue(x, out var old) && old != now) ui.Toast($"{ActionLabel(x)} now uses {now}");
                            }
                            ui.Hud?.RefreshKeys();
                        }
                        if (ui.HasScreen("settings")) Render();
                    });
                });
            }

            screen = new UIScreen("settings", m.Root)
            {
                Back = Close,
                Overlay = inGame && G.Manager != null && G.Manager.Mode == GameMode.Play,
                Tab = dir => { section = (section + dir + Sections.Length) % Sections.Length; Render(); },
                // Persist pending slider changes; Flush also notifies (applies a deferred UI scale change).
                Tick = _ =>
                {
                    if (dirty && Time.unscaledTime >= saveDue) Flush();
                },
                OnClose = Flush,
            };
            Render();
            ui.Push(screen);
        }
    }
}
