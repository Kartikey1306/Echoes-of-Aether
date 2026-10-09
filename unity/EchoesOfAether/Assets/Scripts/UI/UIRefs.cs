using UnityEngine;
using UnityEngine.UIElements;

namespace EOA
{
    /// <summary>
    /// Asset references for the UI, stored at Resources/UI/UIRefs.asset by the UI setup editor script so the UI can
    /// be created from code without scene references.
    /// </summary>
    public sealed class UIRefs : ScriptableObject
    {
        public PanelSettings PanelSettings;
        /// <summary>Style sheets added to the root when the panel has no theme style sheet.</summary>
        public StyleSheet[] StyleSheets;

        public static UIRefs Load() => Resources.Load<UIRefs>("UI/UIRefs");
    }
}
