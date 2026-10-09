using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Static effects/feedback facade with the prototype's call shapes (hex colours, optional spark direction,
    /// three.js light peaks). Uses <see cref="VfxManager.Instance"/> when present, otherwise falls back to the
    /// generic <see cref="IVfx"/> in G.Vfx, otherwise does nothing. Safe to call from anywhere.
    /// </summary>
    public static class FxKit
    {
        public static Color Hex(uint rgb) => CombatMath.Hex(rgb);

        static VfxManager M => VfxManager.Instance;

        public static void Sparks(Vector3 pos, Vector3? dir, int count, Color color, float speed = 7f)
        {
            if (M != null) M.SparksDir(pos, dir, count, color, speed);
            else if (dir.HasValue) G.Vfx?.Impact(pos, dir.Value, color, count / 12f);
            else G.Vfx?.Sparks(pos, color, count, speed);
        }

        public static void Sparks(Vector3 pos, Vector3? dir, int count, uint color, float speed = 7f) => Sparks(pos, dir, count, Hex(color), speed);

        public static void Embers(Vector3 pos, int count, Color color, float spread = 0.5f, float up = 1.5f)
        {
            if (M != null) M.Embers(pos, count, color, spread, up);
            else G.Vfx?.Aether(pos, color, count);
        }

        public static void Embers(Vector3 pos, int count, uint color, float spread = 0.5f, float up = 1.5f) => Embers(pos, count, Hex(color), spread, up);

        public static void Smoke(Vector3 pos, int count, uint color, float size = 0.8f)
        {
            if (M != null) M.SmokePuff(pos, count, Hex(color), size);
        }

        /// <summary>Glow sprite flash (prototype vfx.flash(pos, size, color, dur)).</summary>
        public static void FlashSprite(Vector3 pos, float size, Color color, float duration = 0.12f)
        {
            if (M != null) M.FlashSprite(pos, size, color, duration);
            else G.Vfx?.Flash(pos, color, size * 2f, size * 3f, duration);
        }

        public static void FlashSprite(Vector3 pos, float size, uint color, float duration = 0.12f) => FlashSprite(pos, size, Hex(color), duration);

        /// <summary>Point light with a prototype (three.js) peak intensity, e.g. 18 for hits, 80 for the guardian slam.</summary>
        public static void Light(Vector3 pos, uint color, float protoPeak, float duration = 0.18f)
        {
            if (M != null) M.LightProto(pos, Hex(color), protoPeak, duration);
            else G.Vfx?.Flash(pos, Hex(color), Mathf.Clamp(protoPeak * 0.08f, 0.2f, 10f), 8f, duration);
        }

        public static void Shockwave(Vector3 pos, float radius, uint color, float duration = 0.45f)
        {
            if (M != null) M.Shockwave(pos, radius, Hex(color), duration);
            else G.Vfx?.Ring(pos, Hex(color), radius, duration);
        }

        public static void Explode(Vector3 pos, float scale, uint color)
        {
            if (M != null) M.Explosion(pos, scale, Hex(color));
            else G.Vfx?.Explode(pos, Hex(color), scale);
        }

        // ------------------------------------------------------------------ Non-visual feedback helpers

        /// <summary>Play a positional sound through G.Audio (ids are the prototype SFX recipe names).</summary>
        public static void Sfx(string id, Vector3? pos = null, float volume = 1f) => G.Audio?.Play(id, pos, volume);

        /// <summary>Camera trauma request (Bus ShakeRequested).</summary>
        public static void Shake(float amount) => CombatSystem.Shake(amount);
    }
}
