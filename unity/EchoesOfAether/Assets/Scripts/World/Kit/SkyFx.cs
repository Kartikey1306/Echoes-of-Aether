using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Blender storm sky for the outdoor night zones (AtmosphereSettings.Storm, not SolidBackground): assigns the storm
    /// deck panorama, scud layer, far-city band and lightning atlas (<see cref="FxLibrary"/>) to the EOA/Sky material and
    /// publishes the lightning globals the sky, rain and FX particles read. If any texture is missing the material keeps
    /// the procedural sky (prototype look).
    ///
    /// Globals:
    ///   _EOA_LightningDir   xyz unit direction of the current strike (world), w flash 0..~1.5 (0 between strikes)
    ///   _EOA_LightningBolt  x bolt atlas column 0..3, y bolt visibility 0..1, z half width (rad), w top elevation (rad)
    /// </summary>
    public static class SkyFx
    {
        static readonly int DirId = Shader.PropertyToID("_EOA_LightningDir"), BoltId = Shader.PropertyToID("_EOA_LightningBolt");
        static Vector3 dir;
        static Vector4 bolt;

        /// <summary>Night storm zones only. Returns true when the Blender sky is active.</summary>
        public static bool Apply(Material sky, AtmosphereSettings s)
        {
            Clear();
            if (sky == null || s == null || s.SolidBackground || !s.Storm || !sky.HasProperty("_UseSkyTex")) return false;
            var pano = FxLibrary.Tex(FxLibrary.SkyPano);
            if (pano == null) return false;
            sky.SetTexture("_SkyTex", pano);
            var clouds = FxLibrary.Tex(FxLibrary.SkyClouds);
            var band = FxLibrary.Tex(FxLibrary.SkyBand);
            var bolts = FxLibrary.Tex(FxLibrary.Bolts);
            if (clouds != null) sky.SetTexture("_CloudTex", clouds);
            else sky.SetVector("_CloudParams", new Vector4(0.36f, 0f, 0.12f, 0.3f));
            // band: latitude range of sky_horizon.py's strip (-3 .. 12 deg), light gain, alpha
            if (band != null) { sky.SetTexture("_BandTex", band); sky.SetVector("_BandParams", new Vector4(-3f, 12f, 1f, 1f)); }
            else sky.SetVector("_BandParams", new Vector4(-3f, 12f, 0f, 0f));
            if (bolts != null) sky.SetTexture("_BoltTex", bolts);
            // A zone with a stronger horizon glow (rooftops: up above the haze) gets a slightly brighter deck.
            sky.SetFloat("_SkyExposure", 0.5f * Mathf.Lerp(0.9f, 1.15f, Mathf.InverseLerp(0.5f, 1f, s.GlowStrength)));
            sky.SetFloat("_UseSkyTex", 1);
            return true;
        }

        /// <summary>Strike direction (world), flash intensity and the optional visible bolt (column 0..3, visibility).</summary>
        public static void SetLightning(Vector3 direction, float flash, int boltColumn, float boltVisibility, float halfWidthRad, float topRad)
        {
            dir = direction.sqrMagnitude > 1e-4f ? direction.normalized : Vector3.zero;
            bolt = new Vector4(boltColumn, boltVisibility, halfWidthRad, topRad);
            Shader.SetGlobalVector(DirId, new Vector4(dir.x, dir.y, dir.z, flash));
            Shader.SetGlobalVector(BoltId, bolt);
        }

        /// <summary>Per-frame update of the flash intensity and bolt visibility for the current strike.</summary>
        public static void SetFlash(float flash, float boltVisibility)
        {
            bolt.y = boltVisibility;
            Shader.SetGlobalVector(DirId, new Vector4(dir.x, dir.y, dir.z, flash));
            Shader.SetGlobalVector(BoltId, bolt);
        }

        public static void Clear()
        {
            dir = Vector3.zero;
            bolt = Vector4.zero;
            Shader.SetGlobalVector(DirId, Vector4.zero);
            Shader.SetGlobalVector(BoltId, Vector4.zero);
        }
    }
}
