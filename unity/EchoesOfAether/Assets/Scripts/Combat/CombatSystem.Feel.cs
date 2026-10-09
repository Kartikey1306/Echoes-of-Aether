using System.Collections.Generic;
using UnityEngine;

namespace EOA
{
    /// <summary>Directional camera kick (+ optional FOV punch in degrees) requested on the Bus; the camera rig subscribes.</summary>
    public struct CameraKickRequested { public Vector3 Dir; public float Amount; public float Fov; }

    /// <summary>
    /// Combat feel tuning in one place: input buffer, hit-stop by attack weight, perfect dodge / deflect windows and
    /// slow motion. Hit-stop below <see cref="HitstopFinisher"/> freezes only the attacker and its targets (per actor);
    /// finishers and ultimates use the global time-scale hit-stop.
    /// </summary>
    public static class CombatFeel
    {
        /// <summary>Seconds a button press stays queued waiting for a legal moment (attack/dodge/ability).</summary>
        public const float BufferTime = 0.18f;

        public const float HitstopLight = 0.05f, HitstopMedium = 0.07f, HitstopHeavy = 0.11f, HitstopFinisher = 0.16f;

        /// <summary>A dodge started this close (s) before an enemy attack lands is perfect.</summary>
        public const float PerfectDodgeWindow = 0.16f;
        /// <summary>A hit that arrives this soon (s) after the dodge started also counts (reactive check).</summary>
        public const float PerfectDodgeReactive = 0.2f;
        public const float PerfectSlowScale = 0.3f, PerfectSlowSeconds = 0.4f;
        /// <summary>Real seconds after a perfect dodge / deflect in which the next attack is a counter (crit, extra poise).</summary>
        public const float CounterWindow = 1.4f;
        /// <summary>Game seconds at the start of a heavy attack that deflect a melee hit from the front.</summary>
        public const float DeflectWindow = 0.2f;
        /// <summary>Melee magnetism: the attack step closes at most this gap to the soft-locked target (m).</summary>
        public const float MagnetMax = 3.6f;
    }

    /// <summary>Opt-in combat timing log (the autopilot combat-feel test turns it on). No allocations when disabled.</summary>
    public static class CombatTelemetry
    {
        public struct Entry
        {
            public string Kind;
            public float A, B;
            public int Frame;
            public float Real;
        }

        public static bool Enabled;
        public static readonly List<Entry> Entries = new(512);

        public static void Record(string kind, float a = 0f, float b = 0f)
        {
            if (!Enabled || Entries.Count >= 8000) return;
            Entries.Add(new Entry { Kind = kind, A = a, B = b, Frame = Time.frameCount, Real = Time.realtimeSinceStartup });
        }
    }

    public sealed partial class CombatSystem
    {
        static float slowStart, slowUntil = -1f, slowDur = 1f, slowScale = 1f;

        /// <summary>0..1 while a combat slow motion (perfect dodge, deflect) is running. Heroes partly compensate.</summary>
        public static float SlowMoWeight { get; private set; }

        /// <summary>
        /// Slow the game to `scale` for `seconds` of real time (eases in fast, out over the last 30%). GameManager owns
        /// Time.timeScale (pause, global hit-stop); this only ever lowers it, after GameManager's Update.
        /// </summary>
        public static void SlowMo(float scale, float seconds)
        {
            float now = Time.unscaledTime;
            if (now < slowUntil && scale > slowScale) return;
            slowStart = now;
            slowDur = Mathf.Max(0.05f, seconds);
            slowUntil = now + slowDur;
            slowScale = Mathf.Clamp(scale, 0.05f, 1f);
            CombatTelemetry.Record("slowmo", scale, seconds);
        }

        /// <summary>Directional camera kick (dir = world direction the view is pushed) and FOV punch (degrees).</summary>
        public static void Kick(Vector3 dir, float amount, float fovPunch = 0f)
        {
            if (amount > 0f || fovPunch != 0f) Bus.Emit(new CameraKickRequested { Dir = dir, Amount = amount, Fov = fovPunch });
        }

        static void UpdateTimeScale()
        {
            var m = G.Manager;
            float now = Time.unscaledTime;
            if (m == null || m.Mode != GameMode.Play || m.Paused || now >= slowUntil)
            {
                SlowMoWeight = 0f;
                if (now >= slowUntil) slowScale = 1f;
                return;
            }
            float t = (now - slowStart) / slowDur;
            float w = t < 0.06f ? t / 0.06f : t > 0.7f ? 1f - (t - 0.7f) / 0.3f : 1f;
            SlowMoWeight = Mathf.Clamp01(w);
            float s = Mathf.Lerp(1f, slowScale, SlowMoWeight);
            if (Time.timeScale > s) Time.timeScale = s;
        }

        /// <summary>
        /// True when an enemy projectile will reach a sphere (pos, radius) within `seconds` (perfect-dodge check).
        /// </summary>
        public bool ProjectileThreat(Team victim, Vector3 pos, float radius, float seconds)
        {
            for (int i = 0; i < MaxProjectiles; i++)
            {
                var p = projectiles[i];
                if (p == null || !p.Active || p.Team == victim) continue;
                Vector3 to = pos - p.Pos;
                float speed = p.Vel.magnitude;
                if (speed < 0.1f) continue;
                Vector3 dir = p.Vel / speed;
                float along = Vector3.Dot(to, dir);
                if (along < -radius || along > speed * seconds + radius) continue;
                if ((to - dir * along).sqrMagnitude <= (radius + p.Radius) * (radius + p.Radius)) return true;
            }
            return false;
        }
    }
}
