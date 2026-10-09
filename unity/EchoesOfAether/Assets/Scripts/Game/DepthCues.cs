using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace EOA
{
    /// <summary>
    /// Depth cues that every zone shares (lives on the PostFx object, so it survives zone loads):
    ///  * contact shadows: one instanced, depth-aware AO volume (EOA/ContactShadow) under every character near the
    ///    camera, raycast to the ground, softer and fainter as the character leaves the ground; grounds characters on
    ///    floors, steps and curbs (one draw call);
    ///  * shadowed practical lights: the few street lamps / room lights nearest the player get real soft shadows
    ///    (faded in and out as the player moves; spot = 1 slot, point = 3 slots of GraphicsConfig.LampShadowSlots),
    ///    every other light stays unshadowed. Characters, props and cars then cast lamp shadows across the street;
    ///  * wet sheen: characters out in the rain (nothing overhead) soak in a few seconds and dry slowly under cover;
    ///    their materials' smoothness rises with the wetness (per-material property blocks on the nearest characters),
    ///    so suits, skin and hair catch sharp highlights from the key, lamps and neon.
    /// </summary>
    public sealed class DepthCues : MonoBehaviour
    {
        const int MaxBlobs = 64;
        static readonly int AmountId = Shader.PropertyToID("_Amount");
        Material blobMat;
        Mesh box;
        MaterialPropertyBlock mpb;
        readonly Matrix4x4[] blobs = new Matrix4x4[MaxBlobs];
        readonly float[] amounts = new float[MaxBlobs];

        readonly List<Light> candidates = new();
        readonly List<Light> chosen = new();
        readonly Dictionary<Light, float> levels = new();
        readonly List<Light> fading = new();
        float refreshT, pickT;

        static readonly int SmoothId = Shader.PropertyToID("_Smoothness"), WetGlobalId = Shader.PropertyToID("_EOA_Wetness"),
            RainGlobalId = Shader.PropertyToID("_EOA_RainAmount");
        const int MaxWet = 12;
        readonly Dictionary<CharacterModel, float> wet = new();
        readonly List<CharacterModel> wetDead = new();
        readonly List<Renderer> rbuf = new();
        MaterialPropertyBlock wetMpb;
        float wetT;

        void Awake()
        {
            var t = Resources.Load<Material>("Env/ContactShadow");
            var sh = t != null ? t.shader : Shader.Find("EOA/ContactShadow");
            if (sh != null && sh.isSupported)
            {
                blobMat = t != null ? new Material(t) : new Material(sh);
                blobMat.name = "contact_shadow";
                blobMat.enableInstancing = true;
            }
            else Debug.LogWarning("[depth] EOA/ContactShadow unavailable; no contact shadows");
            mpb = new MaterialPropertyBlock();
            wetMpb = new MaterialPropertyBlock();
            box = UnitBox();
        }

        void OnDestroy()
        {
            if (blobMat != null) Destroy(blobMat);
            if (box != null) Destroy(box);
        }

        static Mesh UnitBox()
        {
            var m = new Mesh { name = "contact_shadow_box" };
            var v = new Vector3[8];
            for (var i = 0; i < 8; i++) v[i] = new Vector3((i & 1) - 0.5f, ((i >> 1) & 1) - 0.5f, ((i >> 2) & 1) - 0.5f);
            m.vertices = v;
            m.triangles = new[]
            {
                0, 2, 1, 1, 2, 3, 4, 5, 6, 5, 7, 6, 0, 1, 4, 1, 5, 4, 2, 6, 3, 3, 6, 7, 0, 4, 2, 2, 4, 6, 1, 3, 5, 3, 7, 5,
            };
            m.bounds = new Bounds(Vector3.zero, Vector3.one);
            return m;
        }

        void LateUpdate()
        {
            var dt = Time.unscaledDeltaTime;
            var cam = G.Manager != null && G.Manager.Cam != null ? G.Manager.Cam.Cam : null;
            if (cam == null) return;
            ShadowLights(dt, cam);
            ContactShadows(cam);
            WetSheen(dt, cam);
        }

        // ------------------------------------------------------------------ contact shadows

        void ContactShadows(Camera cam)
        {
            if (blobMat == null || !GraphicsConfig.ContactShadows) return;
            var list = CharacterModel.Active;
            var cp = cam.transform.position;
            var n = 0;
            for (var i = 0; i < list.Count && n < MaxBlobs; i++)
            {
                var m = list[i];
                if (m == null || !m.isActiveAndEnabled) continue;
                var p = m.transform.position;
                if ((p - cp).sqrMagnitude > 45f * 45f) continue;
                if (!Physics.Raycast(p + Vector3.up * 0.5f, Vector3.down, out var hit, 3.5f, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore)) continue;
                var h = Mathf.Max(0f, p.y - hit.point.y);
                var a = Mathf.Clamp01(1f - h / 1.6f);
                if (a <= 0.02f) continue;
                var scale = Mathf.Max(0.5f, m.transform.lossyScale.y);
                var r = (0.5f + h * 0.3f) * scale;
                blobs[n] = Matrix4x4.TRS(hit.point, Quaternion.identity, new Vector3(r * 2f, 0.7f, r * 2f));
                amounts[n] = a;
                n++;
            }
            if (n == 0) return;
            mpb.SetFloatArray(AmountId, amounts);
            var rp = new RenderParams(blobMat)
            {
                camera = cam,
                layer = CityFx.FxLayer,
                shadowCastingMode = ShadowCastingMode.Off,
                receiveShadows = false,
                matProps = mpb,
                worldBounds = new Bounds(cp, Vector3.one * 200f),
            };
            Graphics.RenderMeshInstanced(rp, box, 0, blobs, n);
        }

        // ------------------------------------------------------------------ wet sheen

        void WetSheen(float dt, Camera cam)
        {
            wetT -= dt;
            if (wetT > 0f) return;
            const float step = 0.5f;
            wetT = step;
            var rain = Shader.GetGlobalFloat(RainGlobalId);
            var ground = Shader.GetGlobalFloat(WetGlobalId);
            var onStage = G.Manager == null || G.Manager.Mode == GameMode.Menu || G.Manager.DesignerActive;
            var cp = cam.transform.position;
            var list = CharacterModel.Active;
            var budget = MaxWet;
            for (var i = 0; i < list.Count; i++)
            {
                var m = list[i];
                if (m == null || !m.isActiveAndEnabled) continue;
                wet.TryGetValue(m, out var w);
                var near = (m.transform.position - cp).sqrMagnitude < 22f * 22f && budget > 0;
                if (!near && w <= 0f) continue;
                var target = 0f;
                if (near && !onStage && rain > 0.05f)
                {
                    budget--;
                    var head = m.transform.position + Vector3.up * 1.9f;
                    var covered = Physics.Raycast(head, Vector3.up, 30f, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore);
                    target = covered ? 0f : Mathf.Clamp01(rain) * Mathf.Max(ground, 0.5f);
                }
                // soaks in ~3 s, dries in ~15 s
                var nw = Mathf.MoveTowards(w, target, step * (target > w ? 0.35f : 0.065f));
                if (Mathf.Abs(nw - w) < 0.005f) continue;
                wet[m] = nw;
                ApplyWet(m, nw);
            }
            wetDead.Clear();
            foreach (var kv in wet) if (kv.Key == null) wetDead.Add(kv.Key);
            foreach (var k in wetDead) wet.Remove(k);
        }

        void ApplyWet(CharacterModel m, float w)
        {
            m.GetComponentsInChildren(true, rbuf);
            foreach (var r in rbuf)
            {
                if (r is not SkinnedMeshRenderer && r is not MeshRenderer) continue;
                var mats = r.sharedMaterials;
                for (var i = 0; i < mats.Length; i++)
                {
                    var mat = mats[i];
                    if (mat == null || !mat.HasProperty(SmoothId)) continue;
                    var b = mat.GetFloat(SmoothId);
                    // with a mask map _Smoothness scales the map's gloss (raise the scale), otherwise it is the gloss
                    var v = mat.IsKeywordEnabled("_METALLICSPECGLOSSMAP") ? b * (1f + 0.35f * w) : Mathf.Min(b + w * 0.32f, Mathf.Max(b, 0.86f));
                    r.GetPropertyBlock(wetMpb, i);
                    wetMpb.SetFloat(SmoothId, v);
                    r.SetPropertyBlock(wetMpb, i);
                }
            }
        }

        // ------------------------------------------------------------------ shadowed lamps

        static bool Eligible(Light l)
        {
            if (l == null || (l.type != LightType.Point && l.type != LightType.Spot)) return false;
            if (l.range < 5f) return false;
            var name = l.name;
            if (name.StartsWith("Character") || name.Contains("Flash") || name.Contains("Glow") || name.Contains("Muzzle")) return false;
            // lights that do not touch the default rendering layer (character-only rigs, stage lights) never cast
            if (l.TryGetComponent<UniversalAdditionalLightData>(out var d) && ((uint)d.renderingLayers & 1u) == 0) return false;
            return true;
        }

        void ShadowLights(float dt, Camera cam)
        {
            refreshT -= dt;
            if (refreshT <= 0f)
            {
                refreshT = 1f;
                candidates.Clear();
                foreach (var l in FindObjectsByType<Light>(FindObjectsInactive.Exclude, FindObjectsSortMode.None))
                    if (Eligible(l)) candidates.Add(l);
            }
            pickT -= dt;
            if (pickT <= 0f)
            {
                pickT = 0.25f;
                chosen.Clear();
                // the menu / designer stage keeps its own studio lighting
                var onStage = G.Manager == null || G.Manager.Mode == GameMode.Menu || G.Manager.DesignerActive;
                var slots = onStage ? 0 : GraphicsConfig.LampShadowSlots;
                var focus = G.Manager != null && G.Manager.Player != null ? G.Manager.Player.Position : cam.transform.position;
                while (slots > 0)
                {
                    Light best = null;
                    var bestD = float.MaxValue;
                    foreach (var l in candidates)
                    {
                        if (l == null || !l.isActiveAndEnabled || l.intensity < 1f || chosen.Contains(l)) continue;
                        var cost = l.type == LightType.Point ? 3 : 1;
                        if (cost > slots) continue;
                        var d = (l.transform.position - focus).sqrMagnitude;
                        // the light must reach the player's surroundings
                        var reach = l.range * 0.85f + 3f;
                        if (d > reach * reach) continue;
                        // a light that already casts keeps a small advantage (less swapping between equal lamps)
                        if (levels.ContainsKey(l)) d *= 0.8f;
                        if (d < bestD) { bestD = d; best = l; }
                    }
                    if (best == null) break;
                    chosen.Add(best);
                    slots -= best.type == LightType.Point ? 3 : 1;
                    if (!levels.ContainsKey(best))
                    {
                        levels[best] = 0f;
                        best.shadows = LightShadows.Soft;
                        best.shadowStrength = 0f;
                        best.shadowNearPlane = 0.3f;
                    }
                }
            }
            // fade shadows in and out (no popping as the player walks from lamp to lamp)
            fading.Clear();
            foreach (var kv in levels) fading.Add(kv.Key);
            foreach (var l in fading)
            {
                if (l == null) { levels.Remove(l); continue; }
                var target = chosen.Contains(l) ? 1f : 0f;
                var v = Mathf.MoveTowards(levels[l], target, dt * 2.5f);
                if (v <= 0f && target <= 0f)
                {
                    l.shadows = LightShadows.None;
                    levels.Remove(l);
                    continue;
                }
                levels[l] = v;
                l.shadowStrength = v * 0.92f;
            }
        }
    }
}
