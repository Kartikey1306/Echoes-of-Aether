using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace EOA
{
    /// <summary>
    /// Combat impact visuals that outlive a single particle burst, all pooled:
    /// <list type="bullet">
    /// <item>Scorch marks: hot glowing quads stuck to a robot where a blow landed (follow the hit enemy, fade ~1.4 s).</item>
    /// <item>Debris: on death a robot's rigid plates and limbs are detached and flung (gravity, ground bounce, spin, ember
    /// trails), then shrink away. Parts are the robot's own meshes (nothing is instantiated); simulation slots are fixed.</item>
    /// </list>
    /// </summary>
    public sealed class HitFx : MonoBehaviour
    {
        const int MaxScorch = 28, MaxDebris = 96;

        struct Scorch
        {
            public Transform T;
            public Transform Follow;
            public Vector3 Local;
            public Quaternion LocalRot;
            public float Age, Life, Size;
            public Color Color;
            public MeshRenderer R;
        }

        struct Debris
        {
            public Transform T;
            public Renderer R;
            public Vector3 V, Axis;
            public float Spin, Age, Life, GroundY, EmberT;
            public Vector3 Scale0;
            public Color Ember;
            public bool Resting;
        }

        static HitFx instance;
        readonly Scorch[] scorch = new Scorch[MaxScorch];
        readonly Debris[] debris = new Debris[MaxDebris];
        int scorchCursor;
        MaterialPropertyBlock mpb;
        Material scorchMat;
        Mesh quad;
        static readonly int BaseColorId = Shader.PropertyToID("_BaseColor");
        static readonly List<MeshRenderer> tmpRenderers = new(64);
        static readonly List<Transform> picked = new(16);

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void ResetStatics() => instance = null;

        static HitFx Ensure()
        {
            if (instance != null) return instance;
            var go = new GameObject("HitFx");
            var cs = CombatSystem.Instance;
            if (cs != null) go.transform.SetParent(cs.transform, false);
            else DontDestroyOnLoad(go);
            instance = go.AddComponent<HitFx>();
            return instance;
        }

        void Awake()
        {
            mpb = new MaterialPropertyBlock();
            scorchMat = FxMaterials.Particle(true, FxMaterials.Glow, true);
            scorchMat.name = "fx_scorch";
            quad = new Mesh { name = "fx_scorch_quad" };
            quad.SetVertices(new[] { new Vector3(-0.5f, -0.5f, 0), new Vector3(0.5f, -0.5f, 0), new Vector3(-0.5f, 0.5f, 0), new Vector3(0.5f, 0.5f, 0) });
            quad.SetUVs(0, new[] { new Vector2(0, 0), new Vector2(1, 0), new Vector2(0, 1), new Vector2(1, 1) });
            quad.SetTriangles(new[] { 0, 2, 1, 1, 2, 3 }, 0);
            quad.RecalculateBounds();
            for (int i = 0; i < MaxScorch; i++)
            {
                var go = new GameObject("Scorch");
                go.transform.SetParent(transform, false);
                go.AddComponent<MeshFilter>().sharedMesh = quad;
                var r = go.AddComponent<MeshRenderer>();
                r.sharedMaterial = scorchMat;
                r.shadowCastingMode = ShadowCastingMode.Off;
                r.receiveShadows = false;
                r.lightProbeUsage = LightProbeUsage.Off;
                go.SetActive(false);
                scorch[i] = new Scorch { T = go.transform, R = r };
            }
        }

        // ------------------------------------------------------------------ API

        /// <summary>Glowing impact mark on `follow` (an enemy) at a world point, facing `normal`.</summary>
        public static void Mark(Transform follow, Vector3 point, Vector3 normal, Color color, float size = 0.32f, float life = 1.4f)
        {
            if (follow == null) return;
            var fx = Ensure();
            ref var s = ref fx.scorch[fx.scorchCursor];
            fx.scorchCursor = (fx.scorchCursor + 1) % MaxScorch;
            if (normal.sqrMagnitude < 1e-6f) normal = Vector3.up;
            var rot = Quaternion.LookRotation(-normal.normalized) * Quaternion.Euler(0, 0, Random.value * 360f);
            s.Follow = follow;
            s.Local = follow.InverseTransformPoint(point + normal.normalized * 0.03f);
            s.LocalRot = Quaternion.Inverse(follow.rotation) * rot;
            s.Age = 0f;
            s.Life = life;
            s.Size = size * Random.Range(0.85f, 1.2f);
            s.Color = color;
            s.T.gameObject.SetActive(true);
            fx.PlaceScorch(ref s);
        }

        /// <summary>
        /// Break a robot apart: detach up to `maxParts` rigid meshes (never bones) and fling them away from `center`
        /// with `force` m/s plus `push`. Returns the number of parts released.
        /// </summary>
        public static int BreakApart(RobotRig rig, Vector3 center, Vector3 push, float force, int maxParts, Color ember)
        {
            if (rig == null) return 0;
            var fx = Ensure();
            tmpRenderers.Clear();
            rig.GetComponentsInChildren(false, tmpRenderers);
            picked.Clear();
            // Largest plausible chunks first (selection without sorting allocations).
            for (int n = 0; n < maxParts; n++)
            {
                int best = -1;
                float bestSize = 0f;
                for (int i = 0; i < tmpRenderers.Count; i++)
                {
                    var r = tmpRenderers[i];
                    if (r == null || !r.enabled) continue;
                    float size = r.bounds.size.magnitude;
                    if (size < 0.1f || size > 1.8f || size <= bestSize) continue;
                    if (!fx.Detachable(rig, r.transform)) continue;
                    best = i;
                    bestSize = size;
                }
                if (best < 0) break;
                picked.Add(tmpRenderers[best].transform);
                tmpRenderers[best] = null;
            }
            float ground = EnemyHost.GroundAt(center + Vector3.up, 6f) ?? rig.transform.position.y;
            int released = 0;
            for (int i = 0; i < picked.Count; i++)
            {
                int slot = fx.FreeDebris();
                if (slot < 0) break;
                var t = picked[i];
                rig.ReleasePart(t);
                t.SetParent(fx.transform, true);
                Vector3 away = t.position - center;
                away.y = 0f;
                away = away.sqrMagnitude > 1e-4f ? away.normalized : Random.insideUnitSphere;
                ref var d = ref fx.debris[slot];
                d.T = t;
                d.R = t.GetComponent<Renderer>();
                d.V = away * force * Random.Range(0.55f, 1.15f) + push + Vector3.up * Random.Range(2.5f, 5.5f);
                d.Axis = Random.onUnitSphere;
                d.Spin = Random.Range(200f, 720f);
                d.Age = 0f;
                d.Life = Random.Range(1.6f, 2.3f);
                d.GroundY = ground;
                d.EmberT = 0f;
                d.Scale0 = t.localScale;
                d.Ember = ember;
                d.Resting = false;
                released++;
            }
            picked.Clear();
            tmpRenderers.Clear();
            return released;
        }

        // ------------------------------------------------------------------ internals

        bool Detachable(RobotRig rig, Transform t)
        {
            if (t == rig.transform) return false;
            var bones = rig.Bones;
            for (int i = 0; i < bones.Length; i++)
            {
                var b = bones[i];
                if (b == null) continue;
                if (b == t || b.IsChildOf(t)) return false;
            }
            for (int i = 0; i < picked.Count; i++) if (t.IsChildOf(picked[i]) || picked[i].IsChildOf(t)) return false;
            return true;
        }

        int FreeDebris()
        {
            for (int i = 0; i < MaxDebris; i++) if (debris[i].T == null) return i;
            return -1;
        }

        void PlaceScorch(ref Scorch s)
        {
            s.T.SetPositionAndRotation(s.Follow.TransformPoint(s.Local), s.Follow.rotation * s.LocalRot);
            float k = 1f - s.Age / s.Life;
            s.T.localScale = Vector3.one * s.Size * (0.8f + 0.2f * k);
            // Hot white-orange core cooling to a dull ember.
            var c = Color.Lerp(new Color(0.9f, 0.2f, 0.05f), s.Color, k * k);
            var hdr = FxMaterials.Hdr(c, 1f + 3f * k * k);
            hdr.a = Mathf.Clamp01(k * 1.3f);
            mpb.SetColor(BaseColorId, hdr);
            s.R.SetPropertyBlock(mpb);
        }

        void Update()
        {
            float dt = Time.deltaTime;
            if (dt <= 0f) return;
            for (int i = 0; i < MaxScorch; i++)
            {
                ref var s = ref scorch[i];
                if (!s.T.gameObject.activeSelf) continue;
                s.Age += dt;
                if (s.Follow == null || s.Age >= s.Life)
                {
                    s.Follow = null;
                    s.T.gameObject.SetActive(false);
                    continue;
                }
                PlaceScorch(ref s);
            }
            for (int i = 0; i < MaxDebris; i++)
            {
                ref var d = ref debris[i];
                if (d.T == null) continue;
                d.Age += dt;
                // The owner robot's materials die with it: never draw a part without its material.
                if (d.Age >= d.Life || d.R == null || d.R.sharedMaterial == null)
                {
                    Destroy(d.T.gameObject);
                    d.T = null;
                    continue;
                }
                if (!d.Resting)
                {
                    d.V.y -= 18f * dt;
                    var p = d.T.position + d.V * dt;
                    if (p.y < d.GroundY + 0.06f && d.V.y < 0f)
                    {
                        p.y = d.GroundY + 0.06f;
                        d.V.y = -d.V.y * 0.32f;
                        d.V.x *= 0.55f;
                        d.V.z *= 0.55f;
                        d.Spin *= 0.5f;
                        if (d.V.y < 0.7f) d.Resting = true;
                    }
                    d.T.position = p;
                    d.T.Rotate(d.Axis, d.Spin * dt, Space.World);
                    d.EmberT -= dt;
                    if (d.Age < 0.7f && d.EmberT <= 0f)
                    {
                        d.EmberT = 0.06f;
                        VfxManager.Instance?.Embers(p, 1, d.Ember, 0.05f, 0.2f);
                    }
                }
                float shrink = Mathf.Clamp01((d.Life - d.Age) / 0.45f);
                d.T.localScale = d.Scale0 * shrink;
            }
        }

        void OnDestroy()
        {
            for (int i = 0; i < MaxDebris; i++) if (debris[i].T != null) Destroy(debris[i].T.gameObject);
            if (scorchMat != null) Destroy(scorchMat);
            if (quad != null) Destroy(quad);
            if (instance == this) instance = null;
        }
    }
}
