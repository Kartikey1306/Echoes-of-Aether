using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;

namespace EOA
{
    /// <summary>Horizontal value slider: drag/click with the pointer, left/right when focused.</summary>
    public sealed class EoaSlider : VisualElement
    {
        readonly VisualElement track, fill, knob;
        readonly Label val;
        readonly float min, max, step;
        readonly Func<float, string> fmt;
        readonly Action<float> onChange;
        public float Value { get; private set; }

        public EoaSlider(float value, float min, float max, float step, Func<float, string> fmt, Action<float> onChange, bool showValue = true)
        {
            this.min = min; this.max = max; this.step = step; this.fmt = fmt ?? (v => v.ToString("0.00")); this.onChange = onChange;
            AddToClassList("slider");
            track = U.El("slider-track");
            var rail = U.El("slider-rail");
            fill = U.El("slider-fill");
            knob = U.El("slider-knob");
            rail.pickingMode = PickingMode.Ignore;
            fill.pickingMode = PickingMode.Ignore;
            knob.pickingMode = PickingMode.Ignore;
            track.Add(rail);
            track.Add(fill);
            track.Add(knob);
            Add(track);
            val = U.Label("", "slider-val");
            if (showValue) Add(val);
            U.Nav(this, NavKind.Slider, null, dir => Set(Value + dir * this.step, true));
            track.RegisterCallback<PointerDownEvent>(e =>
            {
                track.CapturePointer(e.pointerId);
                FromPointer(e.position);
                e.StopPropagation();
            });
            track.RegisterCallback<PointerMoveEvent>(e =>
            {
                if (track.HasPointerCapture(e.pointerId)) FromPointer(e.position);
            });
            track.RegisterCallback<PointerUpEvent>(e =>
            {
                if (track.HasPointerCapture(e.pointerId)) track.ReleasePointer(e.pointerId);
            });
            Set(value, false);
        }

        void FromPointer(Vector2 panelPos)
        {
            var w = track.layout.width;
            if (float.IsNaN(w) || w <= 1) return;
            var x = track.WorldToLocal(panelPos).x;
            Set(Mathf.Lerp(min, max, Mathf.Clamp01(x / w)), true);
        }

        public void Set(float v, bool notify)
        {
            if (step > 0) v = Mathf.Round(v / step) * step;
            v = Mathf.Clamp(v, min, max);
            var changed = !Mathf.Approximately(v, Value);
            Value = v;
            var t = max > min ? (v - min) / (max - min) : 0;
            fill.style.width = Length.Percent(t * 100);
            knob.style.left = Length.Percent(t * 100);
            val.text = fmt(v);
            if (notify && changed) onChange?.Invoke(v);
        }
    }

    /// <summary>Segmented choice (one of N). Left/right or submit cycles; pointer clicks select.</summary>
    public sealed class Seg : VisualElement
    {
        readonly List<(string value, Button btn)> opts = new();
        readonly Action<string> onSet;
        public string Current { get; private set; }

        public Seg(IReadOnlyList<(string value, string label)> options, string value, Action<string> onSet, bool upper = true)
        {
            this.onSet = onSet;
            AddToClassList("seg");
            foreach (var (v, l) in options)
            {
                var vv = v;
                var b = new Button(() => { G.Audio?.PlayUi("ui_click"); Select(vv, true); });
                b.RemoveFromClassList(Button.ussClassName);
                b.AddToClassList("seg-btn");
                b.focusable = false;
                b.text = upper ? U.Up(l) : l;
                Add(b);
                opts.Add((v, b));
            }
            U.Nav(this, NavKind.Seg, () => Cycle(1), Cycle);
            Select(value, false);
        }

        public void Cycle(int dir)
        {
            if (opts.Count == 0) return;
            var i = Mathf.Max(0, opts.FindIndex(o => o.value == Current));
            Select(opts[(i + dir + opts.Count * 4) % opts.Count].value, true);
            G.Audio?.PlayUi("ui_hover");
        }

        public void Select(string v, bool notify)
        {
            Current = v;
            foreach (var (value, btn) in opts) btn.EnableInClassList("sel", value == v);
            if (notify) onSet?.Invoke(v);
        }
    }

    /// <summary>On/off switch.</summary>
    public sealed class ToggleSwitch : Button
    {
        readonly Action<bool> onSet;
        public bool On { get; private set; }

        public ToggleSwitch(bool value, Action<bool> onSet)
        {
            this.onSet = onSet;
            RemoveFromClassList(ussClassName);
            AddToClassList("toggle");
            var knob = U.El("toggle-knob");
            knob.pickingMode = PickingMode.Ignore;
            Add(knob);
            U.Nav(this, NavKind.Button, Flip);
            clicked += () => U.Activate(this);
            Set(value, false);
        }

        void Flip() => Set(!On, true);

        public void Set(bool v, bool notify)
        {
            On = v;
            EnableInClassList("on", v);
            if (notify) onSet?.Invoke(v);
        }
    }

    /// <summary>Colour swatch palette with an optional custom-colour button.</summary>
    public sealed class Swatches : VisualElement
    {
        readonly string[] palette;
        readonly Action<string> onSet;
        readonly List<Button> buttons = new();
        readonly VisualElement custom;
        string current;

        public Swatches(string[] palette, string value, Action<string> onSet, Action onCustom)
        {
            this.palette = palette; this.onSet = onSet;
            AddToClassList("swatches");
            foreach (var hex in palette)
            {
                var h = hex;
                var b = new Button(() => { G.Audio?.PlayUi("ui_click"); Pick(h, true); });
                b.RemoveFromClassList(Button.ussClassName);
                b.AddToClassList("sw");
                b.focusable = false;
                b.style.backgroundColor = U.Hex(h);
                Add(b);
                buttons.Add(b);
            }
            if (onCustom != null)
            {
                var c = new Button(() => { G.Audio?.PlayUi("ui_click"); onCustom(); });
                c.RemoveFromClassList(Button.ussClassName);
                c.AddToClassList("sw-pick");
                c.focusable = false;
                c.text = "+";
                Add(c);
                custom = c;
            }
            U.Nav(this, NavKind.Seg, onCustom, Cycle);
            Pick(value, false);
        }

        void Cycle(int dir)
        {
            var i = Array.FindIndex(palette, p => string.Equals(p, current, StringComparison.OrdinalIgnoreCase));
            if (i < 0) i = dir > 0 ? -1 : 0;
            Pick(palette[(i + dir + palette.Length) % palette.Length], true);
            G.Audio?.PlayUi("ui_hover");
        }

        public void Pick(string hex, bool notify)
        {
            current = hex;
            var any = false;
            for (var i = 0; i < palette.Length; i++)
            {
                var sel = string.Equals(palette[i], hex, StringComparison.OrdinalIgnoreCase);
                any |= sel;
                buttons[i].EnableInClassList("sel", sel);
            }
            if (custom != null)
            {
                custom.EnableInClassList("sel", !any);
                custom.style.backgroundColor = any ? new StyleColor(StyleKeyword.Null) : new StyleColor(U.Hex(hex));
            }
            if (notify) onSet?.Invoke(hex);
        }
    }

    /// <summary>HSV colour picker: saturation/value square, hue bar and three navigable sliders.</summary>
    public sealed class ColorPicker : VisualElement
    {
        static Texture2D hueTex;
        Texture2D svTex;
        readonly VisualElement sv, svKnob, hue, hueKnob, preview;
        readonly Label hexLabel;
        readonly EoaSlider hs, ss, vs;
        readonly Action<string> changed;
        float h, s, v;
        float builtHue = -1;

        public ColorPicker(string hex, Action<string> changed)
        {
            this.changed = changed;
            AddToClassList("picker");
            Color.RGBToHSV(U.Hex(hex), out h, out s, out v);

            var top = U.El("picker-top");
            sv = U.El("picker-sv");
            svKnob = U.El("picker-knob");
            svKnob.pickingMode = PickingMode.Ignore;
            sv.Add(svKnob);
            var side = U.El("picker-side");
            preview = U.El("picker-preview");
            hexLabel = U.Label("", "picker-hex");
            side.Add(preview);
            side.Add(hexLabel);
            top.Add(sv);
            top.Add(side);
            Add(top);

            hue = U.El("picker-hue");
            hueKnob = U.El("picker-hue-knob");
            hueKnob.pickingMode = PickingMode.Ignore;
            hue.Add(hueKnob);
            Add(hue);
            hue.style.backgroundImage = new StyleBackground(HueTexture());

            hs = new EoaSlider(h * 360, 0, 360, 4, x => Mathf.RoundToInt(x) + "°", x => { h = x / 360f; Apply(true, false); });
            ss = new EoaSlider(s, 0, 1, 0.04f, x => Mathf.RoundToInt(x * 100) + "%", x => { s = x; Apply(true, false); });
            vs = new EoaSlider(v, 0, 1, 0.04f, x => Mathf.RoundToInt(x * 100) + "%", x => { v = x; Apply(true, false); });
            Add(Row("Hue", hs));
            Add(Row("Saturation", ss));
            Add(Row("Brightness", vs));

            Drag(sv, p =>
            {
                s = Mathf.Clamp01(p.x);
                v = 1 - Mathf.Clamp01(p.y);
                Apply(true, true);
            });
            Drag(hue, p =>
            {
                h = Mathf.Clamp01(p.x) * 0.9999f;
                Apply(true, true);
            });
            RegisterCallback<DetachFromPanelEvent>(_ =>
            {
                if (svTex != null) UnityEngine.Object.Destroy(svTex);
                svTex = null;
            });
            RegisterCallback<GeometryChangedEvent>(_ => PlaceKnobs());
            Apply(false, true);
        }

        static VisualElement Row(string label, VisualElement control)
        {
            var r = U.El("picker-row", U.Label(U.Up(label), "dz-lab"));
            r.Add(control);
            return r;
        }

        static void Drag(VisualElement el, Action<Vector2> at)
        {
            void Emit(Vector2 panelPos)
            {
                var r = el.layout;
                if (float.IsNaN(r.width) || r.width <= 1 || r.height <= 1) return;
                var lp = el.WorldToLocal(panelPos);
                at(new Vector2(lp.x / r.width, lp.y / r.height));
            }
            el.RegisterCallback<PointerDownEvent>(e => { el.CapturePointer(e.pointerId); Emit(e.position); e.StopPropagation(); });
            el.RegisterCallback<PointerMoveEvent>(e => { if (el.HasPointerCapture(e.pointerId)) Emit(e.position); });
            el.RegisterCallback<PointerUpEvent>(e => { if (el.HasPointerCapture(e.pointerId)) el.ReleasePointer(e.pointerId); });
        }

        static Texture2D HueTexture()
        {
            if (hueTex != null) return hueTex;
            hueTex = new Texture2D(128, 1, TextureFormat.RGBA32, false) { wrapMode = TextureWrapMode.Clamp, filterMode = FilterMode.Bilinear, hideFlags = HideFlags.DontSave };
            for (var x = 0; x < 128; x++) hueTex.SetPixel(x, 0, Color.HSVToRGB(x / 127f, 1, 1));
            hueTex.Apply(false);
            return hueTex;
        }

        void RebuildSv()
        {
            if (Mathf.Approximately(builtHue, h) && svTex != null) return;
            const int n = 48;
            if (svTex == null)
                svTex = new Texture2D(n, n, TextureFormat.RGBA32, false) { wrapMode = TextureWrapMode.Clamp, filterMode = FilterMode.Bilinear, hideFlags = HideFlags.DontSave };
            var px = new Color32[n * n];
            for (var y = 0; y < n; y++)
                for (var x = 0; x < n; x++)
                    px[y * n + x] = Color.HSVToRGB(h, x / (n - 1f), y / (n - 1f));
            svTex.SetPixels32(px);
            svTex.Apply(false);
            builtHue = h;
            sv.style.backgroundImage = new StyleBackground(svTex);
        }

        void Apply(bool notify, bool syncSliders)
        {
            RebuildSv();
            var c = Color.HSVToRGB(h, s, v);
            var hex = "#" + ColorUtility.ToHtmlStringRGB(c).ToLowerInvariant();
            preview.style.backgroundColor = c;
            hexLabel.text = hex;
            if (syncSliders)
            {
                hs.Set(h * 360, false);
                ss.Set(s, false);
                vs.Set(v, false);
            }
            PlaceKnobs();
            if (notify) changed?.Invoke(hex);
        }

        void PlaceKnobs()
        {
            svKnob.style.left = Length.Percent(s * 100);
            svKnob.style.top = Length.Percent((1 - v) * 100);
            hueKnob.style.left = Length.Percent(h * 100);
        }
    }
}
