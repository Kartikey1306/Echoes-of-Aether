using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;

namespace EOA
{
    // Keyboard / gamepad focus navigation over the top screen (or the active dialogue choices), driven by
    // GameInput's UI actions. Focusable elements carry the "nav" class and a NavData in userData.
    public sealed partial class UIManager
    {
        enum Dir { None, Up, Down, Left, Right }

        VisualElement focused;
        Dir heldDir;
        float repeatT;
        int navBlockedUntilFrame;
        int choiceFocus;
        readonly List<VisualElement> navScratch = new();

        /// <summary>Ignore navigation input for a few frames (after rebinding, when a key may still be down).</summary>
        public void SuppressNavigation(int frames = 2) => navBlockedUntilFrame = Time.frameCount + frames;

        VisualElement NavScope(out bool choices)
        {
            choices = Dialogue != null && Dialogue.ChoicesActive && stack.Count == 0;
            if (choices) return Dialogue.ChoicesRoot;
            return Top?.Root;
        }

        int CurrentIndex
        {
            get
            {
                NavScope(out var choices);
                return choices ? choiceFocus : Top?.FocusIndex ?? 0;
            }
            set
            {
                NavScope(out var choices);
                if (choices) choiceFocus = value;
                else if (Top != null) Top.FocusIndex = value;
            }
        }

        /// <summary>Visible, enabled navigable elements of the current scope, in document order.</summary>
        public List<VisualElement> NavList()
        {
            navScratch.Clear();
            var scope = NavScope(out _);
            if (scope == null) return navScratch;
            scope.Query<VisualElement>(className: "nav").ForEach(e =>
            {
                if (e.enabledInHierarchy && IsDisplayed(e, scope)) navScratch.Add(e);
            });
            return navScratch;
        }

        static bool IsDisplayed(VisualElement e, VisualElement scope)
        {
            for (var p = e; p != null; p = p.parent)
            {
                if (!U.Shown(p)) return false;
                if (p.resolvedStyle.display == DisplayStyle.None || p.resolvedStyle.visibility == Visibility.Hidden) return false;
                if (p == scope) break;
            }
            return true;
        }

        /// <summary>Re-apply focus styling after a screen re-renders its content.</summary>
        public void Refocus() => PaintFocus();

        /// <summary>Dialogue choices appeared or disappeared: reset choice focus.</summary>
        public void ChoicesChanged()
        {
            choiceFocus = 0;
            heldDir = Dir.None;
            PaintFocus();
        }

        /// <summary>Focus a specific element of the current scope (if navigable).</summary>
        public void FocusElement(VisualElement el)
        {
            var list = NavList();
            var i = list.IndexOf(el);
            if (i < 0) return;
            CurrentIndex = i;
            PaintFocus();
        }

        void PaintFocus()
        {
            var list = NavList();
            if (list.Count == 0)
            {
                if (focused != null) { focused.RemoveFromClassList("focus"); focused = null; }
                return;
            }
            var idx = Mathf.Clamp(CurrentIndex, 0, list.Count - 1);
            CurrentIndex = idx;
            var el = list[idx];
            if (focused == el) return;
            focused?.RemoveFromClassList("focus");
            focused = el;
            el.AddToClassList("focus");
            ScrollIntoView(el);
            if (el.focusable && el.panel != null) el.Focus();
        }

        static void ScrollIntoView(VisualElement el)
        {
            ScrollView sv = null;
            for (var p = el.parent; p != null; p = p.parent)
                if (p is ScrollView s) { sv = s; break; }
            if (sv == null) return;
            el.schedule.Execute(() =>
            {
                if (el.panel == null || float.IsNaN(el.layout.height) || float.IsNaN(sv.contentViewport.layout.height)) return;
                sv.ScrollTo(el);
            });
        }

        /// <summary>Pointer hover moves keyboard focus (as in the prototype).</summary>
        public void HoverFocus(VisualElement el)
        {
            var list = NavList();
            var i = list.IndexOf(el);
            if (i < 0 || i == CurrentIndex && focused == el) return;
            CurrentIndex = i;
            PaintFocus();
            G.Audio?.PlayUi("ui_hover");
        }

        void OnFocusIn(FocusInEvent e)
        {
            if (e.target is not VisualElement ve || !ve.ClassListContains("nav") || ve == focused) return;
            var list = NavList();
            var i = list.IndexOf(ve);
            if (i < 0) return;
            CurrentIndex = i;
            PaintFocus();
        }

        /// <summary>Process navigation input. Returns true when Cancel was consumed by a screen.</summary>
        bool NavigationTick(float dt)
        {
            var inp = G.Input;
            if (inp == null) return false;
            if (inp.Rebinding) { SuppressNavigation(); return true; }
            if (Time.frameCount <= navBlockedUntilFrame) return stack.Count > 0;
            var scope = NavScope(out var choices);
            if (scope == null) { heldDir = Dir.None; return false; }

            if (inp.Cancel.WasPressedThisFrame() && !choices)
            {
                var top = Top;
                if (top?.Back != null)
                {
                    G.Audio?.PlayUi("ui_back");
                    top.Back();
                }
                return true;
            }
            if (inp.Submit.WasPressedThisFrame())
            {
                var list = NavList();
                if (list.Count > 0) U.Activate(list[Mathf.Clamp(CurrentIndex, 0, list.Count - 1)]);
                return false;
            }
            if (!choices)
            {
                if (inp.TabPrev.WasPressedThisFrame()) { Top?.Tab?.Invoke(-1); return false; }
                if (inp.TabNext.WasPressedThisFrame()) { Top?.Tab?.Invoke(1); return false; }
            }

            var v = inp.Navigate.ReadValue<Vector2>();
            var d = Dir.None;
            if (v.sqrMagnitude > 0.25f)
                d = Mathf.Abs(v.x) > Mathf.Abs(v.y) ? (v.x > 0 ? Dir.Right : Dir.Left) : (v.y > 0 ? Dir.Up : Dir.Down);
            if (d == Dir.None) { heldDir = Dir.None; return false; }
            if (d != heldDir)
            {
                heldDir = d;
                repeatT = 0.4f;
                Navigate(d);
            }
            else
            {
                repeatT -= dt;
                if (repeatT <= 0)
                {
                    repeatT = 0.12f;
                    Navigate(d);
                }
            }
            return false;
        }

        void Navigate(Dir d)
        {
            var list = NavList();
            if (list.Count == 0) return;
            var idx = Mathf.Clamp(CurrentIndex, 0, list.Count - 1);
            var cur = list[idx];
            var nd = cur.userData as NavData;
            var kind = nd?.Kind ?? NavKind.Button;
            if ((d == Dir.Left || d == Dir.Right) && (kind == NavKind.Seg || kind == NavKind.Slider))
            {
                nd?.Step?.Invoke(d == Dir.Left ? -1 : 1);
                return;
            }
            var next = -1;
            // Grids: up/down move spatially to the nearest element in that direction.
            if ((d == Dir.Up || d == Dir.Down) && kind == NavKind.Grid) next = Spatial(list, idx, d == Dir.Down);
            if (next < 0)
            {
                var back = d == Dir.Up || d == Dir.Left;
                next = back ? (idx - 1 + list.Count) % list.Count : (idx + 1) % list.Count;
            }
            if (next == idx) return;
            CurrentIndex = next;
            PaintFocus();
            G.Audio?.PlayUi("ui_hover");
        }

        static int Spatial(List<VisualElement> list, int from, bool down)
        {
            var a = list[from].worldBound;
            if (float.IsNaN(a.width)) return -1;
            var best = -1;
            var bestScore = float.MaxValue;
            for (var i = 0; i < list.Count; i++)
            {
                if (i == from) continue;
                var b = list[i].worldBound;
                if (float.IsNaN(b.width)) continue;
                var dy = down ? b.center.y - a.center.y : a.center.y - b.center.y;
                if (dy < 4) continue;
                var score = dy + Mathf.Abs(b.center.x - a.center.x) * 2;
                if (score < bestScore) { bestScore = score; best = i; }
            }
            return best;
        }
    }
}
