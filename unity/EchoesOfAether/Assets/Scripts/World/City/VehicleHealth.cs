using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Health of a city car (parked, street traffic or the player's): a neutral <see cref="IDamageable"/> on the car's
    /// root, so the hero's blade / strikes, Aether Bolts, Pulse and ultimates reach it through the normal CombatSystem
    /// queries (its colliders are on IgnoreCamera, which is in <see cref="CombatLayers.NeutralTargetMask"/>); crashes and
    /// explosions damage it directly. Stages (run by <see cref="VehicleDamage"/>): smoke from the hood at half health,
    /// fire at a fifth (it keeps burning down), a short fuse with a warning flicker at zero, then the explosion and a
    /// burnt wreck. No damage while a cinematic plays or outside gameplay. No per-frame work of its own.
    /// </summary>
    [DisallowMultipleComponent]
    public sealed class VehicleHealth : MonoBehaviour, IDamageable, IDamageReport
    {
        public enum Stage { Intact, Smoking, Burning, Fuse, Wrecked }

        public VehicleKit.Spec Spec { get; private set; }
        public float Max { get; private set; } = 200f;
        public float Health { get; private set; } = 200f;
        public Stage State { get; internal set; }
        /// <summary>Part of the street traffic pool (revived when the pool reuses the car).</summary>
        public bool InTraffic { get; private set; }
        public float LastAppliedDamage { get; private set; }
        /// <summary>Seconds left on the fuse (Fuse stage).</summary>
        internal float Fuse;
        /// <summary>Particle / flicker timers and the pooled light / fire-audio slots (VehicleDamage).</summary>
        internal float SmokeT, FireT, FlickT;
        internal int LightSlot = -1, AudioSlot = -1;
        internal bool Listed;
        float radius = 1.6f;

        public float Health01 => Max > 0f ? Mathf.Clamp01(Health / Max) : 0f;

        // ---------------------------------------------------------------- IDamageable

        public Team Team => Team.Neutral;
        public bool Alive => State != Stage.Wrecked && isActiveAndEnabled;
        public Vector3 Position => transform.position;
        public Vector3 AimPoint => transform.TransformPoint(Spec != null ? Spec.BoundsCenter : new Vector3(0, 0.7f, 0));
        /// <summary>Melee / radial reach: between the half width and the half length (a car is long, not round).</summary>
        public float Radius => radius;
        public bool Targetable => Alive;

        /// <summary>Health by body type (a van takes more, a bike less).</summary>
        /// (A sedan takes three or four of Kael's combos to catch fire; Aether Bolts chip at it.)
        public static float MaxFor(VehicleKit.Spec s) => s.Name switch
        {
            "CyberCar_Coupe" => 380f,
            "CyberCar_Taxi" => 420f,
            "CyberVan" => 540f,
            "CyberBike" => 230f,
            _ => 420f,
        };

        /// <summary>Make a car destructible (once). Its colliders move to IgnoreCamera (hit by attacks, not by the camera).</summary>
        public static VehicleHealth Attach(GameObject go, VehicleKit.Spec spec, bool traffic)
        {
            var h = go.GetComponent<VehicleHealth>();
            if (h == null) h = go.AddComponent<VehicleHealth>();
            h.Spec = spec;
            h.InTraffic = traffic;
            h.Max = MaxFor(spec);
            h.Health = h.Max;
            h.State = Stage.Intact;
            h.radius = Mathf.Lerp(spec.Size.x * 0.5f, spec.Length * 0.5f, 0.5f);
            foreach (var c in go.GetComponentsInChildren<Collider>(true)) if (!c.isTrigger) c.gameObject.layer = CombatLayers.IgnoreCamera;
            return h;
        }

        /// <summary>Full health again (the traffic pool reusing the car).</summary>
        public void Revive()
        {
            var vd = VehicleDamage.Instance;
            if (vd != null) vd.Release(this);
            Health = Max;
            State = Stage.Intact;
            Fuse = 0f;
        }

        public void ReceiveHit(HitInfo hit)
        {
            LastAppliedDamage = 0f;
            if (!Alive || !Allowed()) return;
            // Player attacks through the combat system; enemy fire and the environment (crashes, blasts) too.
            var mul = hit.Kind switch
            {
                HitKind.Bolt => 1.2f,
                HitKind.Pulse => 1.5f,
                HitKind.Ultimate => 3f,
                HitKind.Enemy => 0.8f,
                _ => 1f,
            };
            Damage(hit.Damage * mul, hit.Point);
        }

        /// <summary>Apply damage (crashes, explosions, attacks). Returns what was applied.</summary>
        public float Damage(float amount, Vector3 point)
        {
            LastAppliedDamage = 0f;
            if (!Alive || amount <= 0f || !Allowed()) return 0f;
            var before = Health;
            Health = Mathf.Max(0f, Health - amount);
            LastAppliedDamage = before - Health;
            var vd = VehicleDamage.Instance;
            if (vd != null) vd.Damaged(this, point, LastAppliedDamage);
            return LastAppliedDamage;
        }

        /// <summary>Burning down (VehicleDamage).</summary>
        internal void Drain(float amount) => Health = Mathf.Max(0f, Health - amount);

        /// <summary>Only in live gameplay: never during cinematics, loading or menus.</summary>
        public static bool Allowed()
        {
            var m = G.Manager;
            return m != null && m.Mode == GameMode.Play && !m.InCinematic;
        }

        void OnDisable()
        {
            var vd = VehicleDamage.Instance;
            if (vd != null) vd.Release(this);
        }
    }
}
