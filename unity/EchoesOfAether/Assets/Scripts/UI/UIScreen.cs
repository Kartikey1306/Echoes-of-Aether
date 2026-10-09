using System;
using UnityEngine.UIElements;

namespace EOA
{
    /// <summary>An entry on the UI screen stack.</summary>
    public sealed class UIScreen
    {
        public readonly string Id;
        public readonly VisualElement Root;
        /// <summary>Cancel / Esc / B handler (null = cancel does nothing).</summary>
        public Action Back;
        /// <summary>Overlays pause gameplay while open (pause menu, panels, in-game settings/saves, death).</summary>
        public bool Overlay;
        /// <summary>Full-screen page: screens below it are hidden while it is on the stack (character select, designer, credits).</summary>
        public bool HidesBelow;
        public Action OnClose;
        /// <summary>Per-frame update while on the stack (unscaled seconds).</summary>
        public Action<float> Tick;
        /// <summary>TabPrev/TabNext (Q/E, LB/RB) handler: -1 or +1.</summary>
        public Action<int> Tab;
        /// <summary>Free-form tag (e.g. the current panel tab).</summary>
        public string Tag;

        internal int FocusIndex;

        public UIScreen(string id, VisualElement root)
        {
            Id = id;
            Root = root;
        }
    }
}
