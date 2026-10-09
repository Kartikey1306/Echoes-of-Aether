using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Material for world-space TextMesh signs using the EOA/WorldText shader (depth tested, fogged, HDR tint), so sign
    /// text no longer draws through walls like Unity's GUI/Text Shader. Tracks the dynamic font atlas when it rebuilds.
    /// </summary>
    public static class WorldText
    {
        static Material mat;
        static Font font;

        public static Font Font => font != null ? font : font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");

        /// <summary>Shared material (glow = HDR multiplier on the TextMesh colour).</summary>
        public static Material Material
        {
            get
            {
                if (mat != null) return mat;
                var shader = Shader.Find("EOA/WorldText");
                if (shader == null) return Font.material;
                mat = new Material(shader) { name = "world_text" };
                mat.mainTexture = Font.material.mainTexture;
                mat.SetColor("_Color", FxMaterials.Hdr(Color.white, 1.6f));
                Font.textureRebuilt += f => { if (mat != null && f == font) mat.mainTexture = f.material.mainTexture; };
                return mat;
            }
        }
    }
}
