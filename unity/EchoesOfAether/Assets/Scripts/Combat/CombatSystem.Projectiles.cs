using System;
using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Parameters for <see cref="CombatSystem.Fire"/>. Zero/unset optional fields fall back to the prototype
    /// defaults (Radius 0.25, Life 2.5 s, Poise 6, Size 0.12, Kind Bolt).
    /// </summary>
    public struct ProjectileSpec
    {
        public Vector3 From;
        public Vector3 Dir;
        public float Speed;
        public float Damage;
        public Team Team;
        /// <summary>sRGB colour of the bolt, trail and impact sparks.</summary>
        public Color Color;
        public float Radius;
        public float Life;
        /// <summary>Homing target (may be null) and turn rate (per second, prototype 2..6).</summary>
        public IDamageable Homing;
        public float Turn;
        public Component Source;
        /// <summary>Defaults to Bolt for player projectiles and Enemy for enemy projectiles.</summary>
        public HitKind? Kind;
        public float Poise;
        public float Size;
        public bool Pierce;
        /// <summary>The caller already drew its own muzzle flash (weapon models with barrels).</summary>
        public bool NoMuzzle;

        public static ProjectileSpec Make(Vector3 from, Vector3 dir, float speed, float damage, Team team, Color color, Component source = null)
            => new ProjectileSpec { From = from, Dir = dir, Speed = speed, Damage = damage, Team = team, Color = color, Source = source };
    }

    /// <summary>
    /// A continuous energy beam (guardian chest laser) drawn with two LineRenderers (glow + hot core).
    /// Owned by the caller: create with <see cref="CombatSystem.CreateBeam"/>, call <see cref="Dispose"/> when done.
    /// </summary>
    public sealed class CombatBeam
    {
        readonly GameObject go;
        readonly LineRenderer outer, core;
        readonly Material outerMat, coreMat;
        readonly float width;

        internal CombatBeam(Transform parent, Color color, float width)
        {
            this.width = width;
            go = new GameObject("Beam");
            go.layer = CombatLayers.Projectile;
            if (parent != null) go.transform.SetParent(parent, false);
            outerMat = FxMaterials.Particle(true, FxMaterials.BeamTexture, true);
            outerMat.SetColor("_BaseColor", FxMaterials.Hdr(color, 3f));
            coreMat = FxMaterials.Particle(true, FxMaterials.BeamTexture, true);
            coreMat.SetColor("_BaseColor", FxMaterials.Hdr(Color.Lerp(color, Color.white, 0.6f), 4f));
            outer = MakeLine(go.transform, "glow", outerMat, width);
            core = MakeLine(go.transform, "core", coreMat, width * 0.35f);
            go.SetActive(false);
        }

        static LineRenderer MakeLine(Transform parent, string name, Material mat, float width)
        {
            var child = new GameObject(name);
            child.layer = CombatLayers.Projectile;
            child.transform.SetParent(parent, false);
            var lr = child.AddComponent<LineRenderer>();
            lr.sharedMaterial = mat;
            lr.positionCount = 2;
            lr.useWorldSpace = true;
            lr.widthMultiplier = width;
            lr.numCapVertices = 4;
            lr.alignment = LineAlignment.View;
            lr.textureMode = LineTextureMode.Stretch;
            lr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            lr.receiveShadows = false;
            lr.startColor = Color.white;
            lr.endColor = Color.white;
            return lr;
        }

        public bool Visible
        {
            get => go != null && go.activeSelf;
            set { if (go != null && go.activeSelf != value) go.SetActive(value); }
        }

        public void SetPoints(Vector3 from, Vector3 to)
        {
            if (go == null) return;
            outer.SetPosition(0, from);
            outer.SetPosition(1, to);
            core.SetPosition(0, from);
            core.SetPosition(1, to);
        }

        /// <summary>Flicker/pulse the width (1 = nominal).</summary>
        public void SetPulse(float k)
        {
            if (go == null) return;
            outer.widthMultiplier = width * k;
            core.widthMultiplier = width * 0.35f * k;
        }

        public void Dispose()
        {
            if (go != null) UnityEngine.Object.Destroy(go);
            if (outerMat != null) UnityEngine.Object.Destroy(outerMat);
            if (coreMat != null) UnityEngine.Object.Destroy(coreMat);
        }
    }

    public sealed partial class CombatSystem
    {
        const int MaxProjectiles = 48;

        sealed class Projectile
        {
            public bool Active;
            public Vector3 Pos, Vel;
            public float Life, Damage, Radius, Turn, Poise;
            public Team Team;
            public Color Color;
            public IDamageable Homing;
            public Component Source;
            public HitKind Kind;
            public bool Pierce;
            public GameObject Go;
            public MeshRenderer Renderer, Core;
            public TrailRenderer Trail;
            public float Size;
        }

        readonly Projectile[] projectiles = new Projectile[MaxProjectiles];
        readonly RaycastHit[] castHits = new RaycastHit[24];
        MaterialPropertyBlock mpb;
        Material boltMat, coreMat, trailMat;
        Texture2D trailTex;
        Transform projectileRoot;
        int cursor;
        bool meshBolts;

        /// <summary>
        /// Pooled bolts: a Blender-modelled faceted energy slug (EOA/HardLight crystal hull + white-hot core, oriented
        /// along the velocity) with a tapered ribbon trail. Falls back to an unlit sphere if the weapon assets are missing.
        /// </summary>
        void InitProjectiles()
        {
            mpb = new MaterialPropertyBlock();
            var hullMesh = WeaponLibrary.FxMesh("bolt_hull");
            var coreMesh = WeaponLibrary.FxMesh("bolt_core");
            if (hullMesh != null && coreMesh != null)
            {
                boltMat = WeaponLibrary.HardLight(Color.white, Color.white, 1f, 2);
                coreMat = WeaponLibrary.HardLight(Color.white, Color.white, 1f, 1);
            }
            meshBolts = boltMat != null && coreMat != null;
            if (!meshBolts)
            {
                boltMat = FxMaterials.Unlit(Color.white);
                hullMesh = FxMesh.Sphere(1f, 10, 8);
            }
            trailTex = TrailTexture();
            trailMat = FxMaterials.Particle(true, trailTex, true);
            trailMat.name = "fx_bolt_trail";
            projectileRoot = new GameObject("Projectiles").transform;
            projectileRoot.SetParent(transform, false);
            var width = new AnimationCurve(new Keyframe(0f, 1f), new Keyframe(0.35f, 0.55f), new Keyframe(1f, 0f));
            for (int i = 0; i < MaxProjectiles; i++)
            {
                var go = new GameObject("Bolt");
                go.layer = CombatLayers.Projectile;
                go.transform.SetParent(projectileRoot, false);
                go.AddComponent<MeshFilter>().sharedMesh = hullMesh;
                var mr = go.AddComponent<MeshRenderer>();
                mr.sharedMaterial = boltMat;
                mr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
                mr.receiveShadows = false;
                mr.lightProbeUsage = UnityEngine.Rendering.LightProbeUsage.Off;
                MeshRenderer core = null;
                if (meshBolts)
                {
                    core = WeaponLibrary.FxRenderer("Core", coreMesh, coreMat, go.transform, CombatLayers.Projectile);
                }
                var tr = go.AddComponent<TrailRenderer>();
                tr.sharedMaterial = trailMat;
                tr.time = 0.13f;
                tr.minVertexDistance = 0.04f;
                tr.numCapVertices = 2;
                tr.widthCurve = width;
                tr.alignment = LineAlignment.View;
                tr.textureMode = LineTextureMode.Stretch;
                tr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
                tr.receiveShadows = false;
                tr.emitting = false;
                go.SetActive(false);
                projectiles[i] = new Projectile { Go = go, Renderer = mr, Core = core, Trail = tr };
            }
        }

        /// <summary>Across-trail gradient: hot thin core with a soft falloff (no sprite dots).</summary>
        static Texture2D TrailTexture()
        {
            var tex = new Texture2D(32, 32, TextureFormat.RGBA32, false) { name = "fx_bolt_trail", wrapMode = TextureWrapMode.Clamp };
            var px = new Color32[32 * 32];
            for (int y = 0; y < 32; y++)
            {
                float v = Mathf.Abs(y / 31f * 2f - 1f);
                float a = Mathf.Exp(-v * v / 0.06f) + 0.45f * Mathf.Exp(-v * v / 0.35f);
                for (int x = 0; x < 32; x++)
                {
                    float u = x / 31f;
                    float along = Mathf.SmoothStep(0f, 0.15f, u);
                    px[y * 32 + x] = new Color32(255, 255, 255, (byte)Mathf.Clamp(Mathf.RoundToInt(Mathf.Clamp01(a * along) * 255f), 0, 255));
                }
            }
            tex.SetPixels32(px);
            tex.Apply(false, true);
            return tex;
        }

        void DestroyProjectiles()
        {
            if (boltMat != null) Destroy(boltMat);
            if (coreMat != null) Destroy(coreMat);
            if (trailMat != null) Destroy(trailMat);
            if (trailTex != null) Destroy(trailTex);
        }

        /// <summary>Number of projectiles in flight.</summary>
        public int ActiveProjectiles
        {
            get
            {
                int n = 0;
                foreach (var p in projectiles) if (p != null && p.Active) n++;
                return n;
            }
        }

        /// <summary>Fire a pooled projectile (homing player bolt or enemy bolt). Reuses the oldest when the pool is full.</summary>
        public void Fire(ProjectileSpec o)
        {
            Projectile p = null;
            int i0 = cursor;
            for (int i = 0; i < MaxProjectiles; i++)
            {
                var c = projectiles[(cursor + i) % MaxProjectiles];
                if (!c.Active) { p = c; i0 = (cursor + i) % MaxProjectiles; break; }
            }
            if (p == null) p = projectiles[cursor];
            cursor = (cursor + 1) % MaxProjectiles;

            Vector3 dir = o.Dir.sqrMagnitude > 1e-8f ? o.Dir.normalized : Vector3.forward;
            p.Active = true;
            p.Pos = o.From;
            p.Vel = dir * o.Speed;
            p.Life = o.Life > 0f ? o.Life : 2.5f;
            p.Damage = o.Damage;
            p.Team = o.Team;
            p.Radius = o.Radius > 0f ? o.Radius : 0.25f;
            p.Color = o.Color;
            p.Homing = o.Homing;
            p.Turn = o.Turn;
            p.Source = o.Source;
            p.Kind = o.Kind ?? (o.Team == Team.Enemy ? HitKind.Enemy : HitKind.Bolt);
            p.Poise = o.Poise > 0f ? o.Poise : 6f;
            p.Pierce = o.Pierce;
            float size = o.Size > 0f ? o.Size : 0.12f;

            var t = p.Go.transform;
            p.Size = size;
            t.SetPositionAndRotation(p.Pos, Quaternion.LookRotation(dir));
            t.localScale = Vector3.one * size;
            p.Go.SetActive(true);
            // Prototype: enemy bolts use the red emissive, player bolts the cyan one; tint by the given colour.
            Color core = o.Team == Team.Enemy ? CombatMath.Hex(0xff3a2e) : Color.Lerp(o.Color, Color.white, 0.35f);
            mpb.Clear();
            if (meshBolts)
            {
                mpb.SetColor(WeaponLibrary.ColorId, FxMaterials.Hdr(o.Color, 1.5f));
                mpb.SetColor(WeaponLibrary.CoreColorId, FxMaterials.Hdr(Color.Lerp(core, Color.white, 0.5f), 2.2f));
                mpb.SetFloat(WeaponLibrary.SeedId, i0 * 1.37f);
                p.Renderer.SetPropertyBlock(mpb);
                p.Core.SetPropertyBlock(mpb);
            }
            else
            {
                mpb.SetColor("_BaseColor", FxMaterials.Hdr(core, 3.2f));
                p.Renderer.SetPropertyBlock(mpb);
            }
            p.Trail.Clear();
            p.Trail.widthMultiplier = size * 1.9f;
            var c0 = o.Color;
            c0.a = 0.9f;
            var c1 = o.Color;
            c1.a = 0f;
            p.Trail.startColor = c0;
            p.Trail.endColor = c1;
            p.Trail.emitting = true;
            if (!o.NoMuzzle) WeaponFx.Muzzle(o.From, dir, o.Color, Mathf.Clamp(size * 1.7f, 0.14f, 0.3f));
        }

        /// <summary>Remove every projectile (zone unload, death screen).</summary>
        public void ClearProjectiles()
        {
            foreach (var p in projectiles) if (p != null && p.Active) Kill(p);
        }

        void Kill(Projectile p)
        {
            p.Active = false;
            p.Homing = null;
            p.Source = null;
            p.Trail.emitting = false;
            p.Trail.Clear();
            p.Go.SetActive(false);
        }

        void UpdateProjectiles(float dt)
        {
            int mask = CombatLayers.WorldMask | CombatLayers.ActorMask | CombatLayers.NeutralTargetMask;
            for (int i = 0; i < MaxProjectiles; i++)
            {
                var p = projectiles[i];
                if (!p.Active) continue;
                p.Life -= dt;
                if (p.Life <= 0f)
                {
                    Kill(p);
                    continue;
                }
                float speed = p.Vel.magnitude;
                if (p.Homing != null && p.Turn > 0f && IsLive(p.Homing))
                {
                    Vector3 want = (p.Homing.AimPoint - p.Pos).normalized * speed;
                    p.Vel = Vector3.Lerp(p.Vel, want, Mathf.Min(1f, p.Turn * dt));
                    float m = p.Vel.magnitude;
                    p.Vel = m > 1e-5f ? p.Vel * (speed / m) : want;
                }
                if (speed < 1e-4f)
                {
                    Kill(p);
                    continue;
                }
                Vector3 d = p.Vel / speed;
                float step = speed * dt;

                // Swept sphere: first opposing targetable damageable vs first piece of level geometry.
                int n = Physics.SphereCastNonAlloc(p.Pos, p.Radius, d, castHits, step, mask, QueryTriggerInteraction.Ignore);
                float worldDist = float.PositiveInfinity, struckDist = float.PositiveInfinity;
                Vector3 worldPoint = default, worldNormal = Vector3.up, struckPoint = default;
                IDamageable struck = null;
                for (int k = 0; k < n; k++)
                {
                    var h = castHits[k];
                    if (h.collider == null) continue;
                    Vector3 point = h.distance <= 0f && h.point == Vector3.zero ? p.Pos : h.point;
                    var dmg = h.collider.GetComponentInParent<IDamageable>();
                    if (dmg != null)
                    {
                        if (!IsLive(dmg) || dmg.Team == p.Team || !dmg.Targetable) continue; // pass through
                        if (h.distance < struckDist)
                        {
                            struckDist = h.distance;
                            struck = dmg;
                            struckPoint = point;
                        }
                        continue;
                    }
                    if ((CombatLayers.WorldMask & (1 << h.collider.gameObject.layer)) == 0) continue;
                    if (h.distance < worldDist)
                    {
                        worldDist = h.distance;
                        worldPoint = point;
                        worldNormal = h.distance <= 0f ? -d : h.normal;
                    }
                }

                if (struck != null && struckDist <= worldDist + 0.5f)
                {
                    var hit = new HitInfo
                    {
                        Damage = p.Damage,
                        Poise = p.Poise,
                        Knock = d * 2f,
                        Kind = p.Kind,
                        Point = struckPoint,
                        Source = p.Source,
                        Pierce = p.Pierce,
                    };
                    Apply(struck, hit);
                    WeaponFx.Impact(struckPoint, -d, p.Color, Mathf.Clamp(p.Size * 3.2f, 0.28f, 0.6f));
                    if (struck is Enemy en && en != null) HitFx.Mark(en.transform, struckPoint, -d, p.Color, 0.22f, 1.1f);
                    G.Audio?.Play("impact_energy", struckPoint, 0.6f);
                    Kill(p);
                    continue;
                }
                if (worldDist < float.PositiveInfinity)
                {
                    WeaponFx.Impact(worldPoint, worldNormal, p.Color, Mathf.Clamp(p.Size * 2.8f, 0.25f, 0.5f), true);
                    G.Audio?.Play("impact_energy", worldPoint, 0.45f);
                    Kill(p);
                    continue;
                }
                p.Pos += p.Vel * dt;
                p.Go.transform.SetPositionAndRotation(p.Pos, Quaternion.LookRotation(d));
            }
        }

        // ------------------------------------------------------------------ Beams

        /// <summary>Create a beam (LineRenderer) owned by the caller. Width in metres (guardian laser: 0.44).</summary>
        public CombatBeam CreateBeam(Color color, float width)
        {
            return new CombatBeam(transform, color, width);
        }
    }
}
