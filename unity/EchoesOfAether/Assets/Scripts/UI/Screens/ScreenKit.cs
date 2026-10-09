using System;
using UnityEngine.UIElements;

namespace EOA
{
    /// <summary>A standard modal: dimmed screen, centred panel with header, optional tabs, scrolling body and footer.</summary>
    public sealed class Modal
    {
        public VisualElement Root, Box, Head, Tabs, Foot;
        public Label Title;
        public ScrollView Body;
    }

    /// <summary>Shared building blocks for screens.</summary>
    public static class ScreenKit
    {
        /// <summary>Panel surface with the cyan (top-left) and violet (bottom-right) corner brackets.</summary>
        public static VisualElement Panel(string classes)
        {
            var p = U.El("panel " + classes);
            return p;
        }

        /// <summary>Add the corner brackets last so they draw above the panel's content.</summary>
        public static void Corners(VisualElement panel)
        {
            var tl = U.El("corner-tl");
            var br = U.El("corner-br");
            tl.pickingMode = PickingMode.Ignore;
            br.pickingMode = PickingMode.Ignore;
            panel.Add(tl);
            panel.Add(br);
        }

        public static ScrollView Scroll(string classes)
        {
            var sv = new ScrollView(ScrollViewMode.Vertical);
            U.AddClasses(sv, classes);
            sv.horizontalScrollerVisibility = ScrollerVisibility.Hidden;
            sv.verticalScrollerVisibility = ScrollerVisibility.Auto;
            sv.mouseWheelScrollSize = 60;
            return sv;
        }

        public static Modal MakeModal(string title, bool tabs, string boxClasses = "modal")
        {
            var m = new Modal();
            m.Title = U.Label(U.Up(title), "h2 modal-title");
            m.Head = U.El("modal-head", m.Title);
            m.Tabs = tabs ? U.El("tabs") : null;
            m.Body = Scroll("modal-body");
            m.Foot = U.El("modal-foot");
            m.Box = Panel(boxClasses);
            m.Box.Add(m.Head);
            if (m.Tabs != null) m.Box.Add(m.Tabs);
            m.Box.Add(m.Body);
            m.Box.Add(m.Foot);
            Corners(m.Box);
            m.Root = U.El("screen dim-bg", U.El("dim-vignette"), U.El("center-wrap", m.Box));
            return m;
        }

        /// <summary>Settings-style row: label (+ description) on the left, control on the right.</summary>
        public static VisualElement Row(string label, string desc, VisualElement control)
        {
            var lab = U.El("row-lab", U.Label(label, "row-l"));
            if (!string.IsNullOrEmpty(desc)) lab.Add(U.Label(desc, "row-d"));
            var ctl = U.El("row-ctl", control);
            var row = U.El("row", lab, ctl);
            // Hovering anywhere on the row focuses its control.
            row.RegisterCallback<PointerEnterEvent>(_ => UIManager.Instance?.HoverFocus(control));
            return row;
        }

        public static Label SectionTitle(string text) => U.Label(U.Up(text), "section-title");

        /// <summary>Hint line in a modal footer: keycap + text pairs.</summary>
        public static VisualElement HintLine(params (string key, string text)[] items)
        {
            var line = U.El("hintline");
            foreach (var (key, text) in items)
            {
                var item = U.El("hint-item");
                foreach (var k in key.Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries)) item.Add(U.Keycap(k));
                item.Add(U.Label(text, "hint-t"));
                line.Add(item);
            }
            return line;
        }

        public static VisualElement Stat(string value, string label) =>
            U.El("stat", U.Label(value, "stat-v"), U.Label(U.Up(label), "stat-l"));

        /// <summary>Make a panel's tab bar from labels; selected index gets the "sel" class.</summary>
        public static void FillTabs(VisualElement tabs, string[] labels, int selected, Action<int> onSelect)
        {
            tabs.Clear();
            for (var i = 0; i < labels.Length; i++)
            {
                var idx = i;
                var b = U.Btn(labels[i], () => onSelect(idx), "tab" + (i == selected ? " sel autofocus" : ""), NavKind.Grid);
                tabs.Add(b);
            }
        }
    }
}
