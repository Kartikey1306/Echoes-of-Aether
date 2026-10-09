using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.UIElements;

namespace EOA
{
    // ---------------------------------------------------------------------------------------------- Main menu
    public static class MainMenuScreen
    {
        public static void Open(UIManager ui)
        {
            var list = U.El("menu-list");
            var version = $"{U.T("menu.version")} {Application.version} · {(Debug.isDebugBuild ? "development" : "release")}";
            var foot = U.El("menu-foot", U.Label(version), U.Label("Mouse / keyboard / controller supported"));
            // Rendered 3D logotype (Blender) when available; typographic title otherwise.
            var logo = U.Art("Title", "logo");
            VisualElement title;
            if (logo != null)
            {
                var img = U.El("title-logo");
                img.style.backgroundImage = new StyleBackground(logo);
                img.style.height = 620f * logo.height / Mathf.Max(1, logo.width);
                title = U.El("title-block", U.Label(U.Up(U.T("menu.kicker")), "kicker"), img);
            }
            else
                title = U.El("title-block",
                    U.Label(U.Up(U.T("menu.kicker")), "kicker"),
                    U.Label("ECHOES", "title"),
                    U.Label(U.Up(U.T("menu.subtitle")), "title-sub"));
            var col = U.El("menu-col", title, U.El("title-rule"), list, foot);
            var root = U.El("screen main-menu", U.El("menu-vignette"), col);

            Button Add(string label, Action fn, string sub = null, bool disabled = false, bool auto = false)
            {
                var b = U.BtnBox(fn, "btn" + (auto ? " autofocus" : ""), NavKind.Button,
                    U.Label(U.Up(label), "btn-main"),
                    sub != null ? U.Label(sub, "btn-sub") : null);
                b.SetEnabled(!disabled);
                list.Add(b);
                return b;
            }

            var latest = G.Saves?.Latest();
            Add(U.T("menu.continue"), () => U.Run(async () =>
            {
                ui.HideAllScreens();
                var ok = G.Manager != null && await G.Manager.ContinueGame();
                if (!ok)
                {
                    ui.Toast("No save found", ToastKind.Warn);
                    ui.ShowMainMenu();
                }
            }), latest != null ? $"{latest.Mission} · {U.FmtTime(latest.Playtime)}" : U.T("menu.noSave"), latest == null, latest != null);
            Add(U.T("menu.newGame"), () =>
            {
                ui.Pop("main");
                if (G.Manager != null) G.Manager.ShowCharSelect();
                else ui.ShowCharacterSelect();
            }, null, false, latest == null);
            Add(U.T("menu.loadGame"), () => ui.OpenSaveScreen(false));
            Add(U.T("menu.settings"), () => ui.OpenSettings(false));
            Add(U.T("menu.credits"), () => U.Run(() => ui.ShowCredits()));
            if (Application.platform != RuntimePlatform.WebGLPlayer)
            {
                Add(U.T("menu.exit"), () => U.Run(async () =>
                {
                    if (!await ui.Confirm(U.T("menu.exit"), U.T("menu.exitConfirm"), U.T("menu.exit"))) return;
#if UNITY_EDITOR
                    UnityEditor.EditorApplication.isPlaying = false;
#else
                    Application.Quit();
#endif
                }));
            }
            ui.Push(new UIScreen("main", root));
        }
    }

    // ---------------------------------------------------------------------------------------------- Character select
    public static class CharacterSelectScreen
    {
        static readonly Dictionary<string, (string icon, string name, string desc)[]> Abilities = new()
        {
            [Characters.Kael] = new[]
            {
                ("ab_pulse", "Aether Pulse", "Area shockwave: damage, knockback and stagger."),
                ("ab_dash", "Phase Dash", "Short-range phase through space with invulnerability."),
                ("ab_corebreak", "Core Break", "Ultimate: leap and drive the Core into the ground."),
            },
            [Characters.Lyra] = new[]
            {
                ("ab_echo", "Echo Sight", "Reveals hidden objects, collectibles, secret paths and lore."),
                ("ab_step", "Phase Step", "Fast evasive step with long invulnerability."),
                ("ab_resonance", "Resonance Burst", "Ultimate: a spinning burst that stuns everything nearby."),
            },
        };

        /// <summary>Pointer drag on an element rotates the menu-stage hero.</summary>
        public static void DragRotate(VisualElement drag)
        {
            var last = 0f;
            drag.RegisterCallback<PointerDownEvent>(e =>
            {
                drag.CapturePointer(e.pointerId);
                last = e.position.x;
            });
            drag.RegisterCallback<PointerMoveEvent>(e =>
            {
                if (!drag.HasPointerCapture(e.pointerId)) return;
                G.Manager?.MenuStage?.Rotate((e.position.x - last) * 0.4f);
                last = e.position.x;
            });
            drag.RegisterCallback<PointerUpEvent>(e =>
            {
                if (drag.HasPointerCapture(e.pointerId)) drag.ReleasePointer(e.pointerId);
            });
        }

        /// <summary>Right stick rotates the menu-stage hero.</summary>
        public static void StickRotate(float dt)
        {
            var pad = Gamepad.current;
            if (pad == null) return;
            var x = pad.rightStick.ReadValue().x;
            if (Mathf.Abs(x) > 0.2f) G.Manager?.MenuStage?.Rotate(x * 150f * dt);
        }

        public static void Open(UIManager ui)
        {
            var gm = G.Manager;
            var sel = gm != null ? gm.SelectedCharacter : Characters.Kael;
            var slots = G.Saves?.AllInfo() ?? new List<SlotInfo>();
            var firstEmpty = slots.FindIndex(x => x.Status == "empty");
            var slot = firstEmpty >= 0 ? firstEmpty + 1 : 1;
            var info = U.El("cs-info");
            var drag = U.El("cs-drag");
            DragRotate(drag);
            var root = U.El("screen char-select", U.El("cs-vignette"), drag, info);
            UIScreen screen = null;

            void Select(string c)
            {
                sel = c;
                if (gm != null) gm.SelectedCharacter = c;
                gm?.MenuStage?.Focus(c);
                Render();
            }

            void GoBack()
            {
                ui.Pop("charselect");
                if (gm != null) gm.ShowMenu();
                else ui.ShowMainMenu();
            }

            void Begin() => U.Run(async () =>
            {
                var si = slot - 1 < slots.Count ? slots[slot - 1] : null;
                if (si != null && si.Status != "empty")
                {
                    var ok = await ui.Confirm(U.T("saves.overwrite"), $"{U.T("saves.slot")} {slot}: {si.Envelope?.Mission ?? U.T("saves.corrupt")}", U.T("cs.begin"), true);
                    if (!ok) return;
                }
                ui.Pop("charselect");
                if (gm != null) await gm.NewGame(sel, slot);
            });

            void Render()
            {
                var kael = sel == Characters.Kael;
                info.Clear();
                var tabs = U.El("cs-tabs");
                foreach (var c in new[] { Characters.Kael, Characters.Lyra })
                {
                    var cc = c;
                    var tab = U.BtnBox(() => Select(cc), $"cs-tab {c}" + (c == sel ? " sel" : ""), NavKind.Grid,
                        U.Label(U.Up(Characters.DisplayName(c)), "cs-tab-n"),
                        U.Label(U.T($"cs.{c}.role"), "cs-tab-r"));
                    tabs.Add(tab);
                }
                var abilities = U.El("cs-abilities");
                foreach (var (ic, n, d) in Abilities[sel])
                    abilities.Add(U.El("cs-ab", U.Icon(ic, U.HeroColor(sel), "icon cs-ab-icon"),
                        U.El("cs-ab-text", U.Label(U.Up(n), "cs-ab-t"), U.Label(d, "cs-ab-d"))));
                var opts = new List<(string, string)>();
                for (var s = 1; s <= SaveSystem.SlotCount; s++)
                {
                    var si = s - 1 < slots.Count ? slots[s - 1] : null;
                    var label = si != null && si.Status == "ok" && si.Envelope != null
                        ? $"{U.T("saves.slot")} {s} · {si.Envelope.Mission}"
                        : $"{U.T("saves.slot")} {s} · {(si == null || si.Status == "empty" ? U.T("saves.empty") : U.T("saves.corrupt"))}";
                    opts.Add((s.ToString(), label));
                }
                var slotSeg = new Seg(opts, slot.ToString(), v => slot = int.Parse(v));
                slotSeg.AddToClassList("cs-slots");
                var back = U.Btn(U.T("cs.back"), GoBack, "btn-small");
                var custom = U.Btn(U.T("cs.customize"), () => ui.OpenDesigner(sel, Render), "btn-small");
                var begin = U.Btn(U.T("cs.begin"), Begin, "btn-small primary autofocus");
                info.Add(U.Label(U.Up(U.T("cs.title")), "kicker"));
                info.Add(tabs);
                info.Add(U.Label(U.Up(Characters.DisplayName(sel)), "cs-name"));
                info.Add(U.Label(U.Up(U.T($"cs.{sel}.role")), "cs-role" + (kael ? "" : " lyra")));
                info.Add(U.Label(U.T($"cs.{sel}.desc"), "cs-desc"));
                info.Add(U.El("cs-meta",
                    U.Label($"Playstyle: <b>{U.T($"cs.{sel}.style")}</b>", "cs-meta-i"),
                    U.Label($"Combo: <b>{(kael ? "L · L · L · Heavy" : "Q · Q · Heavy")}</b>", "cs-meta-i")));
                info.Add(abilities);
                info.Add(ScreenKit.SectionTitle(U.T("cs.slot")));
                info.Add(slotSeg);
                // Voice-over choice at the start of the game (off by default; subtitles are always shown).
                var voice = new Seg(new List<(string, string)> { ("off", "Voices off"), ("on", "Voices on") },
                    G.Settings != null && G.Settings.Data.Audio.VoiceOver ? "on" : "off",
                    v => G.Settings?.Update("audio", st => st.Audio.VoiceOver = v == "on"));
                voice.AddToClassList("cs-slots");
                info.Add(ScreenKit.SectionTitle("Voice-over"));
                info.Add(voice);
                info.Add(U.Label(U.T("cs.note"), "cs-hint"));
                info.Add(U.Label(U.T("cs.rotate"), "cs-hint"));
                info.Add(U.El("flex-spacer"));
                info.Add(U.El("cs-actions", back, custom, begin));
                if (ui.Top == screen) ui.Refocus();
            }

            screen = new UIScreen("charselect", root)
            {
                HidesBelow = true,
                Back = GoBack,
                Tick = StickRotate,
                Tab = _ => Select(sel == Characters.Kael ? Characters.Lyra : Characters.Kael),
            };
            Render();
            ui.Push(screen);
            gm?.MenuStage?.Focus(sel);
        }
    }

    // ---------------------------------------------------------------------------------------------- Credits
    public static class CreditsScreen
    {
        public static Task Open(UIManager ui)
        {
            var tcs = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            var roll = U.El("credits-roll");
            void Sec(string title, params string[] lines)
            {
                roll.Add(U.Label(U.Up(title), "credits-h2"));
                foreach (var l in lines) roll.Add(U.Label(l, "credits-p"));
            }
            roll.Add(U.Label("ECHOES OF AETHER", "credits-h1"));
            roll.Add(U.Label("A story of Aether-9", "credits-p"));
            Sec("Created by",
                "Directed and produced by <b>Kartikey</b>");
            Sec("Starring",
                "<b>Kael Voss</b> · survey lead",
                "<b>Giva Vale</b> · systems engineer",
                "<b>Dr. Ilse Maren</b> · Aether Research Division",
                "<b>Oren Hale</b>, <b>Mira Sato</b>, <b>Tomas Reyes</b>, <b>Nia</b>, <b>BOLT-7</b>");
            Sec("Technology",
                "Built with <b>Unity 6</b> · C# · Universal Render Pipeline (URP)",
                "Rajdhani & Inter typefaces (SIL Open Font License 1.1)");
            Sec("Characters & visual development",
                "Characters built in <b>Blender</b> with MakeHuman / MPFB (CC0 assets)",
                "City, vehicles, robots, props, materials and decals modelled and textured in Blender",
                "Loading screens, portraits, item art and key art rendered in Blender (Cycles)",
                "Character concept references and the city's holographic adverts generated with <b>DreamLayer</b>");
            Sec("Animation",
                "Universal Animation Library 1 & 2 by <b>Quaternius</b> (quaternius.com, CC0)",
                "Motion capture: CMU Graphics Lab Motion Capture Database",
                "The data used in this project was obtained from mocap.cs.cmu.edu.",
                "The database was created with funding from NSF EIA-0196217.");
            Sec("Audio",
                "All music, sound effects and ambience synthesized in code",
                "Voices generated offline with Kokoro-82M text-to-speech (Apache License 2.0)");
            Sec("Special thanks",
                "The DreamLayer Jam",
                "Everyone who stayed on the air until the very end");
            roll.Add(U.Label("\"Now we wake the rest of the city.\"", "credits-quote"));
            roll.pickingMode = PickingMode.Ignore;

            var root = U.El("screen credits", roll, U.Label(U.Up(U.T("credits.skip")), "credits-skip"));
            const float duration = 48f;
            var t = 0f;
            var done = false;

            void Finish()
            {
                if (done) return;
                done = true;
                ui.Pop("credits");
                tcs.TrySetResult(true);
            }

            root.RegisterCallback<ClickEvent>(_ => { if (t > 0.8f) Finish(); });
            ui.Push(new UIScreen("credits", root)
            {
                HidesBelow = true,
                Back = Finish,
                OnClose = () => { done = true; tcs.TrySetResult(true); },
                Tick = dt =>
                {
                    t += dt;
                    var h = root.layout.height;
                    var rh = roll.layout.height;
                    if (!float.IsNaN(h) && !float.IsNaN(rh))
                        roll.style.translate = new Translate(0, -(Mathf.Clamp01(t / duration) * (h + rh)));
                    if (t >= duration) { Finish(); return; }
                    if (t > 0.8f && AnyInput()) Finish();
                },
            });
            return tcs.Task;
        }

        static bool AnyInput()
        {
            if (Keyboard.current != null && Keyboard.current.anyKey.wasPressedThisFrame) return true;
            if (Mouse.current != null && Mouse.current.leftButton.wasPressedThisFrame) return true;
            var pad = Gamepad.current;
            return pad != null && (pad.buttonSouth.wasPressedThisFrame || pad.buttonEast.wasPressedThisFrame || pad.startButton.wasPressedThisFrame);
        }
    }

    // ---------------------------------------------------------------------------------------------- Confirm
    public static class ConfirmDialog
    {
        static int seq;

        public static Task<bool> Open(UIManager ui, string title, string message, string okLabel, bool danger)
        {
            var tcs = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            var id = "confirm-" + ++seq;
            void Done(bool v)
            {
                if (tcs.Task.IsCompleted) return;
                tcs.TrySetResult(v); // before Pop: OnClose would otherwise resolve it as cancelled
                ui.Pop(id);
            }
            var box = ScreenKit.Panel("confirm");
            box.Add(U.Label(U.Up(title), "confirm-t"));
            box.Add(U.Label(message, "confirm-m"));
            box.Add(U.El("confirm-acts",
                U.Btn("Cancel", () => Done(false), "btn-small autofocus"),
                U.Btn(okLabel, () => Done(true), "btn-small " + (danger ? "danger" : "primary"))));
            ScreenKit.Corners(box);
            var root = U.El("screen dim-bg", U.El("dim-vignette"), U.El("center-wrap", box));
            ui.Push(new UIScreen(id, root)
            {
                Back = () => Done(false),
                Overlay = G.Manager != null && G.Manager.Mode == GameMode.Play,
                OnClose = () => tcs.TrySetResult(false),
            });
            return tcs.Task;
        }
    }
}
