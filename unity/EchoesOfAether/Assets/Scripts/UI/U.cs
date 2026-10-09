using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.UIElements;

namespace EOA
{
    /// <summary>How a focusable element reacts to left/right navigation.</summary>
    public enum NavKind
    {
        /// <summary>Left/right behave like up/down (previous/next).</summary>
        Button,
        /// <summary>Left/right step through options (segmented choice, swatches).</summary>
        Seg,
        /// <summary>Left/right change the value.</summary>
        Slider,
        /// <summary>Grid/tab cell: left/right move focus by one.</summary>
        Grid,
    }

    /// <summary>Navigation metadata stored in <see cref="VisualElement.userData"/> of focusable UI elements.</summary>
    public sealed class NavData
    {
        public NavKind Kind;
        public Action Submit;
        public Action<int> Step;
    }

    /// <summary>UI construction helpers, colours, formatting and key-label text.</summary>
    public static class U
    {
        // ------------------------------------------------------------------ Design tokens (match eoa.uss)
        public static readonly Color Text = Hex("#dfe7ee");
        public static readonly Color TextDim = Hex("#8a9aab");
        public static readonly Color TextFaint = Hex("#5b6876");
        public static readonly Color Cyan = Hex("#00e5ff");
        public static readonly Color Violet = Hex("#ff2bd6");
        public static readonly Color Amber = Hex("#ffe14d");
        public static readonly Color Red = Hex("#ff5a4a");
        public static readonly Color Green = Hex("#73e6b0");
        public static readonly Color KaelBlue = Hex("#00e5ff");
        public static readonly Color LockGrey = Hex("#8a9aab");

        public static Color HeroColor(string character) => character == Characters.Kael ? KaelBlue : Violet;

        public static Color Hex(string hex, Color? fallback = null)
        {
            if (!string.IsNullOrEmpty(hex) && ColorUtility.TryParseHtmlString(hex, out var c)) return c;
            return fallback ?? Color.white;
        }

        public static Color Alpha(Color c, float a) => new(c.r, c.g, c.b, a);

        public static Color RarityColor(string rarity) => rarity switch
        {
            "uncommon" => Hex("#00e5ff"),
            "rare" => Hex("#ff2bd6"),
            "epic" => Hex("#ffe14d"),
            _ => Hex("#c8d2dc"),
        };

        // ------------------------------------------------------------------ Element factory
        public static VisualElement El(string classes = null, params VisualElement[] children)
        {
            var e = new VisualElement();
            AddClasses(e, classes);
            foreach (var c in children) if (c != null) e.Add(c);
            return e;
        }

        public static Label Label(string text, string classes = null)
        {
            var l = new Label(text ?? "");
            AddClasses(l, classes);
            return l;
        }

        public static void AddClasses(VisualElement e, string classes)
        {
            if (string.IsNullOrEmpty(classes)) return;
            foreach (var c in classes.Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries)) e.AddToClassList(c);
        }

        /// <summary>A focusable, navigable button. Text is upper-cased for heading-style buttons.</summary>
        public static Button Btn(string text, Action onClick, string classes = "btn", NavKind kind = NavKind.Button, bool upper = true)
        {
            var b = new Button();
            b.RemoveFromClassList(Button.ussClassName);
            AddClasses(b, classes);
            b.text = upper ? Up(text) : text ?? "";
            Nav(b, kind, onClick);
            b.clicked += () => Activate(b);
            return b;
        }

        /// <summary>A button containing arbitrary child content (no text of its own).</summary>
        public static Button BtnBox(Action onClick, string classes, NavKind kind = NavKind.Button, params VisualElement[] children)
        {
            var b = Btn("", onClick, classes, kind, false);
            foreach (var c in children) if (c != null) b.Add(c);
            return b;
        }

        /// <summary>Mark an element as navigable (keyboard/gamepad focus, hover focus).</summary>
        public static T Nav<T>(T el, NavKind kind, Action submit, Action<int> step = null) where T : VisualElement
        {
            el.AddToClassList("nav");
            el.userData = new NavData { Kind = kind, Submit = submit, Step = step };
            el.RegisterCallback<PointerEnterEvent>(_ => UIManager.Instance?.HoverFocus(el));
            return el;
        }

        /// <summary>Invoke an element's submit action (pointer click or keyboard/gamepad submit).</summary>
        public static void Activate(VisualElement el)
        {
            if (el == null || !el.enabledInHierarchy || el.userData is not NavData nd || nd.Submit == null) return;
            G.Audio?.PlayUi("ui_click");
            try { nd.Submit(); }
            catch (Exception e) { Debug.LogException(e); }
        }

        public static void Show(VisualElement e, bool on)
        {
            if (e != null) e.style.display = on ? DisplayStyle.Flex : DisplayStyle.None;
        }

        public static bool Shown(VisualElement e) =>
            e != null && !(e.style.display.keyword == StyleKeyword.Undefined && e.style.display.value == DisplayStyle.None);

        // ------------------------------------------------------------------ Icons
        static readonly Dictionary<string, Texture2D> iconCache = new();

        public static Texture2D IconTexture(string name)
        {
            name ??= "unknown";
            if (iconCache.TryGetValue(name, out var t) && t != null) return t;
            t = Resources.Load<Texture2D>("UI/Icons/" + name);
            if (t == null) t = Resources.Load<Texture2D>("UI/Icons/unknown");
            iconCache[name] = t;
            return t;
        }

        /// <summary>White-on-transparent icon tinted with a colour.</summary>
        public static VisualElement Icon(string name, Color color, string classes = "icon")
        {
            var e = El(classes);
            e.pickingMode = PickingMode.Ignore;
            SetIcon(e, name, color);
            return e;
        }

        public static void SetIcon(VisualElement e, string name, Color color)
        {
            var tex = IconTexture(name);
            e.style.backgroundImage = tex != null ? new StyleBackground(tex) : new StyleBackground(StyleKeyword.None);
            e.style.unityBackgroundImageTintColor = color;
        }

        // ------------------------------------------------------------------ Rendered art (Blender)
        static readonly Dictionary<string, Texture2D> artCache = new();

        /// <summary>Texture from Resources/Art/&lt;folder&gt;/&lt;name&gt; (cached; null when not rendered).</summary>
        public static Texture2D Art(string folder, string name)
        {
            if (string.IsNullOrEmpty(name)) return null;
            var key = folder + "/" + name;
            if (artCache.TryGetValue(key, out var t)) return t;
            t = Resources.Load<Texture2D>("Art/" + key);
            artCache[key] = t;
            return t;
        }

        /// <summary>
        /// Item icon: the full-colour Blender render (Resources/Art/Items/&lt;icon&gt;) when present, otherwise the
        /// tinted glyph. A rarity-coloured underline keeps the rarity readable on rendered art.
        /// </summary>
        public static VisualElement ItemIcon(string icon, Color rarity, string classes)
        {
            var art = Art("Items", icon);
            if (art == null) return Icon(icon, rarity, classes);
            var e = El(classes + " item-art");
            e.pickingMode = PickingMode.Ignore;
            e.style.backgroundImage = new StyleBackground(art);
            e.style.unityBackgroundImageTintColor = Color.white;
            e.style.borderBottomColor = rarity;
            return e;
        }

        // ------------------------------------------------------------------ Portraits
        static readonly Dictionary<string, Texture2D> portraitCache = new();

        /// <summary>Portrait art from Resources/Art/Portraits/&lt;id&gt; (null when absent or id is "none").</summary>
        public static Texture2D Portrait(string id)
        {
            if (string.IsNullOrEmpty(id) || id == "none") return null;
            if (portraitCache.TryGetValue(id, out var t)) return t;
            t = Resources.Load<Texture2D>("Art/Portraits/" + id);
            portraitCache[id] = t;
            return t;
        }

        // ------------------------------------------------------------------ Keys
        public static Label Keycap(string text)
        {
            var l = Label(text, "keycap");
            l.pickingMode = PickingMode.Ignore;
            // Arrow glyphs are not in Rajdhani; render them with Inter.
            if (text != null && text.Length > 0 && text[0] >= ' ') l.AddToClassList("sym");
            return l;
        }

        static string Pretty(string s) => s switch
        {
            "LMB" or "Left Button" => "LMB",
            "RMB" or "Right Button" => "RMB",
            "Middle Button" => "MMB",
            "Left Shift" => "L-Shift",
            "Right Shift" => "R-Shift",
            "Escape" => "Esc",
            "Space" => "Space",
            "Up Arrow" => "↑",
            "Down Arrow" => "↓",
            "Left Arrow" => "←",
            "Right Arrow" => "→",
            null or "" => "—",
            _ => s.Length == 1 ? s.ToUpperInvariant() : s,
        };

        /// <summary>
        /// Key label for an action on the current device. Handles the prototype's split move actions
        /// (moveF/moveB/moveL/moveR) which map onto the composite parts of "move".
        /// </summary>
        public static string KeyLabel(string action)
        {
            var inp = G.Input;
            if (inp == null) return action;
            var part = action switch { "moveF" => "up", "moveB" => "down", "moveL" => "left", "moveR" => "right", _ => null };
            if (part == null) return inp.Label(action);
            if (inp.UsingGamepad) return part == "up" ? "LS" : "";
            return MovePartLabel(part) ?? "";
        }

        /// <summary>Keyboard label of one direction of the move composite (first keyboard composite).</summary>
        public static string MovePartLabel(string part)
        {
            var move = G.Input?.Move;
            if (move == null) return null;
            for (var i = 0; i < move.bindings.Count; i++)
            {
                var b = move.bindings[i];
                if (!b.isPartOfComposite || !string.Equals(b.name, part, StringComparison.OrdinalIgnoreCase)) continue;
                if (!b.effectivePath.StartsWith("<Keyboard>")) continue;
                return Pretty(move.GetBindingDisplayString(i, InputBinding.DisplayStringOptions.DontIncludeInteractions));
            }
            return null;
        }

        /// <summary>Label of an action's first keyboard/mouse or gamepad binding, independent of the active device.</summary>
        public static string BindingLabel(string action, bool gamepad)
        {
            var a = G.Input?.Action(action);
            if (a == null) return "—";
            if (action == "move")
                return gamepad ? "LS" : $"{MovePartLabel("up")}{MovePartLabel("left")}{MovePartLabel("down")}{MovePartLabel("right")}";
            for (var i = 0; i < a.bindings.Count; i++)
            {
                var b = a.bindings[i];
                if (b.isComposite || b.isPartOfComposite) continue;
                if (b.effectivePath.StartsWith("<Gamepad>") != gamepad) continue;
                return Pretty(a.GetBindingDisplayString(i, InputBinding.DisplayStringOptions.DontIncludeInteractions));
            }
            return "—";
        }

        static readonly Regex Placeholder = new(@"(\{\w+\})");

        /// <summary>
        /// Flowing text with {action} placeholders rendered as keycaps of the current bindings.
        /// Words are separate labels in a wrapping row so keycaps can sit inline.
        /// </summary>
        public static VisualElement KeyText(string text, string classes = "keytext")
        {
            var row = El(classes);
            row.pickingMode = PickingMode.Ignore;
            FillKeyText(row, text);
            return row;
        }

        public static void FillKeyText(VisualElement row, string text)
        {
            row.Clear();
            if (string.IsNullOrEmpty(text)) return;
            foreach (var part in Placeholder.Split(text))
            {
                if (part.Length == 0) continue;
                if (part.Length > 2 && part[0] == '{' && part[part.Length - 1] == '}')
                {
                    var label = KeyLabel(part.Substring(1, part.Length - 2));
                    if (!string.IsNullOrEmpty(label)) row.Add(Keycap(label));
                    continue;
                }
                var words = part.Split(' ');
                for (var k = 0; k < words.Length; k++)
                {
                    if (words[k].Length == 0) continue;
                    var w = Label(words[k], k < words.Length - 1 ? "kt-w sp" : "kt-w");
                    w.pickingMode = PickingMode.Ignore;
                    row.Add(w);
                }
            }
        }

        // ------------------------------------------------------------------ Formatting
        public static string Up(string s) => string.IsNullOrEmpty(s) ? "" : s.ToUpperInvariant();

        public static string T(string key) => GameData.T(key);

        public static string FmtTime(float seconds)
        {
            var s = Mathf.Max(0, Mathf.FloorToInt(seconds));
            int hh = s / 3600, mm = s % 3600 / 60, ss = s % 60;
            return hh > 0 ? $"{hh}h {mm}m" : $"{mm}m {ss:00}s";
        }

        public static string FmtDate(string iso)
        {
            if (DateTime.TryParse(iso, CultureInfo.InvariantCulture, DateTimeStyles.RoundtripKind, out var d))
                return d.ToLocalTime().ToString("MMM d, HH:mm", CultureInfo.InvariantCulture);
            return iso ?? "";
        }

        public static string ZoneName(string zone) => zone != null && GameData.Zones.TryGetValue(zone, out var z) ? z.Name : zone ?? "";

        public static int CollectedCount(string kind)
        {
            var st = G.State;
            if (st == null) return 0;
            var n = 0;
            foreach (var id in st.D.Collected)
                if (GameData.Collectibles.TryGetValue(id, out var c) && c.Kind == kind) n++;
            return n;
        }

        /// <summary>Text of the first unfinished objective of the tracked quest (or null).</summary>
        public static string TrackedObjectiveText()
        {
            var q = G.Quests?.Tracked();
            if (q == null) return null;
            foreach (var o in G.Quests.CurrentObjectives(q.Id))
                if (!o.Done) return G.Quests.ObjectiveText(o.Def);
            return null;
        }

        /// <summary>Fire-and-forget an async UI operation, logging failures.</summary>
        public static async void Run(Func<Task> work)
        {
            try { await work(); }
            catch (Exception e) { Debug.LogException(e); }
        }

        /// <summary>Decode a base64 JPEG/PNG (optionally a data: URL). Caller owns the texture.</summary>
        public static Texture2D DecodeImage(string base64)
        {
            if (string.IsNullOrEmpty(base64)) return null;
            try
            {
                var comma = base64.IndexOf(',');
                if (base64.StartsWith("data:") && comma >= 0) base64 = base64.Substring(comma + 1);
                var bytes = Convert.FromBase64String(base64);
                var tex = new Texture2D(2, 2, TextureFormat.RGBA32, false) { wrapMode = TextureWrapMode.Clamp };
                if (tex.LoadImage(bytes, true)) return tex;
                UnityEngine.Object.Destroy(tex);
            }
            catch (Exception e) { Debug.LogWarning($"[ui] thumbnail decode failed: {e.Message}"); }
            return null;
        }
    }
}
