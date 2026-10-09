using System;
using System.Linq;
using UnityEngine;
using UnityEngine.UIElements;
using Random = UnityEngine.Random;

namespace EOA
{
    /// <summary>
    /// Character Designer: edits Kael and Lyra's <see cref="Appearance"/> on the menu stage (presets, body and face
    /// morphs, hair, outfit colours with swatches and an HSV picker, armour toggles). Changes are debounced by
    /// 120 ms and applied with GameManager.SetAppearance.
    /// </summary>
    public static class DesignerScreen
    {
        static readonly string[] SectionIds = { "presets", "body", "face", "hair", "ink", "outfit" };

        public static readonly (string id, string label)[] HairStyles =
        {
            ("curly", "Curly"), ("wavy", "Wavy"), ("short", "Short"), ("swept", "Swept"), ("undercut", "Undercut"), ("buzz", "Buzz"), ("bobshort", "Short bob"),
            ("bob", "Bob"), ("ponytail", "Ponytail"), ("braid", "Braid"), ("frenchbraid", "French braid"), ("bun", "Bun"),
            ("messy", "Messy"), ("long", "Long"), ("afro", "Afro"), ("none", "Shaved"),
        };

        public static readonly (string id, string label)[] FacialHair = { ("none", "None"), ("beard", "Beard"), ("moustache", "Moustache") };

        static readonly string[] AccentPalette = { "#1f2126", "#2a2431", "#24262b", "#3b2858", "#2b3550", "#4a2f3a", "#4a4237", "#2e3a4a" };
        static readonly string[] ArmorPalette = { "#a9a59a", "#6a6474", "#d6d3cc", "#4b4e54", "#2a2c30", "#3a4a5a", "#5a4a3a", "#7a8a96" };

        const float Debounce = 0.12f;

        public static void Open(UIManager ui, string start, Action onClose)
        {
            if (ui.HasScreen("designer")) return;
            var gm = G.Manager;
            var stage = gm?.MenuStage;
            var inGame = gm != null && gm.Mode == GameMode.Play;
            var hero = start ?? Characters.Kael;
            var section = 0;
            var face = false;
            var a = Load(hero);
            var pending = false;
            var due = 0f;
            string pickerFor = null;
            if (gm != null) gm.DesignerActive = true;
            stage?.EnterDesigner(hero);
            stage?.FocusFace(false);

            // Hide the screen underneath (character select / pause) while designing.
            var under = ui.Top;
            if (under != null) under.Root.style.visibility = Visibility.Hidden;

            var panel = U.El("cs-info designer");
            var drag = U.El("cs-drag");
            CharacterSelectScreen.DragRotate(drag);
            var root = U.El("screen char-select designer-screen", drag, panel);
            var body = ScreenKit.Scroll("dz-body"); // reused across renders to keep the scroll position
            var renderedSection = -1;
            UIScreen screen = null;

            Appearance Load(string h) => gm != null ? gm.AppearanceFor(h).Clone() : Appearance.Default(h);

            void Flush()
            {
                if (!pending) return;
                pending = false;
                gm?.SetAppearance(hero, a.Clone());
            }

            void Commit(bool rerender)
            {
                pending = true;
                due = Time.unscaledTime + Debounce;
                if (rerender) Render();
            }

            void SetFace(bool f)
            {
                face = f;
                stage?.FocusFace(f);
            }

            void Close() => ui.Pop("designer");

            VisualElement SliderRow(string label, float value, float min, float max, Action<float> set, bool signed = true)
            {
                var s = new EoaSlider(value, min, max, 0.02f, v => signed ? v.ToString("+0.00;-0.00;0.00") : Mathf.RoundToInt(v * 100) + "%", v => { set(v); Commit(false); });
                var row = U.El("dz-row", U.Label(U.Up(label), "dz-lab"), s);
                row.RegisterCallback<PointerEnterEvent>(_ => ui.HoverFocus(s));
                return row;
            }

            VisualElement SwatchRow(string key, string label, string[] palette, string value, Action<string> set)
            {
                var sw = new Swatches(palette, value, v => { set(v); Commit(true); }, () =>
                {
                    pickerFor = pickerFor == key ? null : key;
                    Render();
                });
                var row = U.El("dz-row", U.Label(U.Up(label), "dz-lab"), sw);
                if (pickerFor == key) row.Add(new ColorPicker(value, v => { set(v); Commit(false); }));
                row.RegisterCallback<PointerEnterEvent>(_ => ui.HoverFocus(sw));
                return row;
            }

            VisualElement ToggleRow(string label, bool value, Action<bool> set)
            {
                var t = new ToggleSwitch(value, v => { set(v); Commit(false); });
                var row = U.El("dz-row inline", U.Label(U.Up(label), "dz-lab"), t);
                row.RegisterCallback<PointerEnterEvent>(_ => ui.HoverFocus(t));
                return row;
            }

            VisualElement ChipGrid((string id, string label)[] items, string current, Action<string> set)
            {
                var grid = U.El("hairgrid");
                foreach (var (id, label) in items)
                {
                    var v = id;
                    grid.Add(U.Btn(label, () => { set(v); Commit(true); }, "btn-small chip" + (id == current ? " primary" : ""), NavKind.Grid));
                }
                return grid;
            }

            // Thumbnail grid of catalog options (hair styles, eyewear, armour sets, tattoo designs).
            VisualElement ImageGrid(string category, string current, Action<string> set, string noneLabel)
            {
                var grid = U.El("imggrid");
                VisualElement Chip(string id, string label, Texture2D tex)
                {
                    var img = U.El("imgchip-img");
                    img.pickingMode = PickingMode.Ignore;
                    if (tex != null) img.style.backgroundImage = new StyleBackground(tex);
                    else img.Add(U.Label(id == "none" ? "—" : label.Substring(0, 1), "imgchip-ph"));
                    var lab = U.Label(label, "imgchip-l");
                    lab.pickingMode = PickingMode.Ignore;
                    return U.BtnBox(() => { set(id); Commit(true); }, "imgchip" + (id == current ? " sel" : ""), NavKind.Grid, img, lab);
                }
                if (noneLabel != null) grid.Add(Chip("none", noneLabel, null));
                foreach (var it in CustomCatalog.Get().For(category, hero)) grid.Add(Chip(it.Id, it.Label, CustomCatalog.Thumb(it)));
                return grid;
            }

            bool HasCatalog(string category) => CustomCatalog.Get().For(category, hero).Any();

            void Render()
            {
                panel.Clear();
                var lyra = hero == Characters.Lyra;
                var heroTabs = U.El("cs-tabs");
                foreach (var c in new[] { Characters.Kael, Characters.Lyra })
                {
                    var cc = c;
                    heroTabs.Add(U.BtnBox(() =>
                    {
                        if (cc == hero) return;
                        Flush();
                        hero = cc;
                        a = Load(hero);
                        pickerFor = null;
                        stage?.EnterDesigner(hero);
                        stage?.FocusFace(face);
                        Render();
                    }, $"cs-tab {c}" + (c == hero ? " sel" : ""), NavKind.Grid,
                        U.Label(U.Up(Characters.DisplayName(c)), "cs-tab-n"),
                        U.Label("Edit appearance", "cs-tab-r")));
                }
                var secTabs = U.El("tabs dz-tabs");
                for (var i = 0; i < SectionIds.Length; i++)
                {
                    var idx = i;
                    secTabs.Add(U.Btn(SectionIds[i], () => SelectSection(idx), "tab" + (i == section ? " sel" : ""), NavKind.Grid));
                }
                body.Clear();
                if (renderedSection != section) body.scrollOffset = Vector2.zero;
                renderedSection = section;
                switch (SectionIds[section])
                {
                    case "presets":
                        foreach (var (name, apply) in AppearancePresets.For(hero))
                        {
                            var ap = apply;
                            body.Add(U.Btn(name, () =>
                            {
                                a = Appearance.Default(hero);
                                ap(a);
                                Commit(true);
                            }, "btn"));
                        }
                        body.Add(U.Label("Pick a starting point, then fine-tune Body, Face, Hair and Outfit. Changes are saved automatically and apply to new games and your current game.", "cs-hint dz-note"));
                        break;
                    case "body":
                        body.Add(SliderRow("Height", a.Height, -1, 1, v => a.Height = v));
                        body.Add(SliderRow("Muscle", a.Muscle, -1, 1, v => a.Muscle = v));
                        body.Add(SliderRow("Weight", a.Weight, -1, 1, v => a.Weight = v));
                        body.Add(SliderRow("Shoulders", a.Shoulders, -1, 1, v => a.Shoulders = v));
                        body.Add(SliderRow("Hips", a.Hips, -1, 1, v => a.Hips = v));
                        if (lyra) body.Add(SliderRow("Bust", a.Bust, -1, 1, v => a.Bust = v));
                        body.Add(SwatchRow("skin", "Skin tone", Appearance.SkinPalette, a.Skin, v => a.Skin = v));
                        break;
                    case "face":
                        body.Add(SwatchRow("eyes", "Eye colour", Appearance.EyePalette, a.Eyes, v => a.Eyes = v));
                        body.Add(SliderRow("Jaw width", a.Jaw, -1, 1, v => a.Jaw = v));
                        body.Add(SliderRow("Chin", a.Chin, -1, 1, v => a.Chin = v));
                        body.Add(SliderRow("Cheekbones", a.Cheeks, -1, 1, v => a.Cheeks = v));
                        body.Add(SliderRow("Nose size", a.NoseSize, -1, 1, v => a.NoseSize = v));
                        body.Add(SliderRow("Nose width", a.NoseWidth, -1, 1, v => a.NoseWidth = v));
                        body.Add(SliderRow("Lips", a.Lips, -1, 1, v => a.Lips = v));
                        body.Add(SliderRow("Eye size", a.EyeSize, -1, 1, v => a.EyeSize = v));
                        body.Add(SliderRow("Brow height", a.BrowHeight, -1, 1, v => a.BrowHeight = v));
                        body.Add(SliderRow("Age", a.Age, 0, 1, v => a.Age = v, false));
                        if (!lyra)
                        {
                            body.Add(U.El("dz-row", U.Label("FACIAL HAIR", "dz-lab"), ChipGrid(FacialHair, a.FacialHair, v => a.FacialHair = v)));
                        }
                        if (HasCatalog("eyewear"))
                            body.Add(U.El("dz-row", U.Label("GLASSES", "dz-lab"), ImageGrid("eyewear", a.Eyewear, v => a.Eyewear = v, "None")));
                        break;
                    case "hair":
                        if (HasCatalog("hair"))
                            body.Add(U.El("dz-row", U.Label("STYLE", "dz-lab"), ImageGrid("hair", a.HairStyle, v => a.HairStyle = v, null)));
                        else
                            body.Add(U.El("dz-row", U.Label("STYLE", "dz-lab"), ChipGrid(HairStyles, a.HairStyle, v => a.HairStyle = v)));
                        body.Add(SwatchRow("hair", "Hair colour", Appearance.HairPalette, a.Hair, v => a.Hair = v));
                        break;
                    case "ink":
                        if (HasCatalog("tattoos"))
                            body.Add(U.El("dz-row", U.Label("TATTOO DESIGN", "dz-lab"), ImageGrid("tattoos", string.IsNullOrEmpty(a.TattooDesign) ? "none" : a.TattooDesign, v => a.TattooDesign = v == "none" ? "" : v, "Signature")));
                        body.Add(SwatchRow("tattoo", "Tattoo glow", Appearance.GlowPalette, a.Tattoo, v => a.Tattoo = v));
                        body.Add(SliderRow("Glow intensity", a.TattooGlow, 0, 2, v => a.TattooGlow = v, false));
                        body.Add(U.Label("Glowing cyberpunk ink. Set intensity to 0 for ink only.", "cs-hint dz-note"));
                        break;
                    case "outfit":
                        if (HasCatalog("armour"))
                            body.Add(U.El("dz-row", U.Label("ARMOUR SET", "dz-lab"), ImageGrid("armour", a.ArmorSet, v => a.ArmorSet = v, "Standard")));
                        body.Add(SwatchRow("outfit", "Jacket / suit", Appearance.OutfitPalette, a.Outfit, v => a.Outfit = v));
                        body.Add(SwatchRow("accent", "Accent panels", AccentPalette, a.Accent, v => a.Accent = v));
                        body.Add(SwatchRow("armor", "Armour", ArmorPalette, a.Armor, v => a.Armor = v));
                        body.Add(SwatchRow("glow", "Aether glow", Appearance.GlowPalette, a.Glow, v => a.Glow = v));
                        body.Add(SwatchRow("glow2", "Glow secondary", Appearance.GlowPalette, a.Glow2, v => a.Glow2 = v));
                        // Only parts that exist on this hero's model.
                        body.Add(ToggleRow("Shoulder armour", a.ShoulderPads, v => a.ShoulderPads = v));
                        if (!lyra)
                        {
                            body.Add(ToggleRow("Chest plate & rig", a.ChestPlate, v => a.ChestPlate = v));
                            body.Add(ToggleRow("Knee pads", a.KneePads, v => a.KneePads = v));
                        }
                        else body.Add(ToggleRow("Utility harness", a.Backpack, v => a.Backpack = v));
                        body.Add(ToggleRow("Gloves", a.Gloves, v => a.Gloves = v));
                        break;
                }
                var view = U.Btn(face ? "View: Face" : "View: Body", () => { SetFace(!face); Render(); }, "btn-small");
                var rand = U.Btn("Randomize", () => { a = Randomized(hero); Commit(true); }, "btn-small");
                var reset = U.Btn("Reset", () => U.Run(async () =>
                {
                    if (!await ui.Confirm("Reset appearance", $"Restore {Characters.FirstName(hero)}'s original design?", "Reset")) return;
                    a = Appearance.Default(hero);
                    Commit(true);
                }), "btn-small");
                var done = U.Btn("Done", Close, "btn-small primary autofocus");
                panel.Add(U.Label("CHARACTER DESIGNER", "kicker"));
                panel.Add(heroTabs);
                panel.Add(secTabs);
                panel.Add(body);
                panel.Add(U.Label("Drag the character to rotate.", "cs-hint"));
                panel.Add(U.El("cs-actions", view, rand, reset, done));
                if (ui.Top == screen) ui.Refocus();
            }

            void SelectSection(int i)
            {
                section = (i + SectionIds.Length) % SectionIds.Length;
                pickerFor = null;
                var id = SectionIds[section];
                SetFace(id == "face" || id == "hair");
                Render();
            }

            screen = new UIScreen("designer", root)
            {
                HidesBelow = true,
                Back = Close,
                Overlay = inGame,
                Tab = dir => SelectSection(section + dir),
                Tick = dt =>
                {
                    if (pending && Time.unscaledTime >= due) Flush();
                    CharacterSelectScreen.StickRotate(dt);
                },
                OnClose = () =>
                {
                    Flush();
                    if (under != null) under.Root.style.visibility = StyleKeyword.Null;
                    if (gm != null) gm.DesignerActive = false;
                    stage?.FocusFace(false);
                    if (!inGame) stage?.Focus(gm != null ? gm.SelectedCharacter : hero);
                    onClose?.Invoke();
                },
            };
            Render();
            ui.Push(screen);
        }

        /// <summary>A plausible random look within the hero's style.</summary>
        public static Appearance Randomized(string hero)
        {
            var a = Appearance.Default(hero);
            var fem = hero == Characters.Lyra;
            static float R(float lo, float hi) => Random.Range(lo, hi);
            static string Pick(string[] p) => p[Random.Range(0, p.Length)];
            a.Height = R(-0.6f, 0.6f);
            a.Muscle = R(-0.4f, 0.7f);
            a.Weight = R(-0.5f, 0.5f);
            a.Shoulders = R(-0.6f, 0.6f);
            a.Hips = R(-0.6f, 0.6f);
            a.Bust = fem ? R(-0.5f, 0.6f) : 0;
            a.Jaw = R(-0.7f, 0.7f);
            a.Chin = R(-0.7f, 0.7f);
            a.Cheeks = R(-0.7f, 0.7f);
            a.NoseSize = R(-0.6f, 0.6f);
            a.NoseWidth = R(-0.6f, 0.6f);
            a.Lips = R(-0.6f, 0.7f);
            a.EyeSize = R(-0.5f, 0.5f);
            a.BrowHeight = R(-0.6f, 0.6f);
            a.Age = R(0, 0.4f);
            a.Skin = Pick(Appearance.SkinPalette);
            a.Eyes = Pick(Appearance.EyePalette);
            a.Hair = Pick(Appearance.HairPalette);
            a.HairStyle = HairStyles[Random.Range(0, HairStyles.Length - 1)].id; // never "none"
            a.Stubble = fem ? 0 : R(0, 1);
            a.FacialHair = fem || Random.value > 0.3f ? "none" : FacialHair[Random.Range(1, FacialHair.Length)].id;
            a.Scar = Random.value < 0.3f;
            a.Outfit = Pick(Appearance.OutfitPalette);
            a.Accent = Pick(AccentPalette);
            a.Armor = Pick(ArmorPalette);
            a.Glow = Pick(Appearance.GlowPalette);
            a.Glow2 = Pick(Appearance.GlowPalette);
            return a;
        }
    }
}
