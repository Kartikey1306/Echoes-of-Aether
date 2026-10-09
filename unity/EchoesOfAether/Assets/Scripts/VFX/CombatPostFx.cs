using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace EOA
{
    /// <summary>
    /// Short full-screen combat accents on two global URP volumes above the game's PostFx (priority 10):
    /// <list type="bullet">
    /// <item>Impact: chromatic split, lens "punch" and an exposure flash for finishers, ultimates and deflects.</item>
    /// <item>Focus: desaturated, cool, vignetted world during perfect-dodge slow motion.</item>
    /// </list>
    /// Accessibility: flash / chroma scale with Settings Accessibility.FlashIntensity, the lens punch with the camera-shake
    /// setting; nothing plays with Effects = low. Only volume weights change per frame (no allocations).
    /// </summary>
    public sealed class CombatPostFx : MonoBehaviour
    {
        static CombatPostFx instance;
        Volume impactVol, focusVol;
        ChromaticAberration impactCa, focusCa;
        LensDistortion lens;
        ColorAdjustments impactCol, focusCol;
        Vignette focusVig;
        float impact, focusHold, focus;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void ResetStatics() => instance = null;

        static CombatPostFx Ensure()
        {
            if (instance != null) return instance;
            var go = new GameObject("CombatPostFx");
            var cs = CombatSystem.Instance;
            if (cs != null) go.transform.SetParent(cs.transform, false);
            else DontDestroyOnLoad(go);
            instance = go.AddComponent<CombatPostFx>();
            return instance;
        }

        static float FlashScale => Mathf.Clamp01(G.Settings?.Data?.Accessibility?.FlashIntensity ?? 1f);
        static float MotionScale => Mathf.Clamp01(G.Settings?.ShakeScale ?? 1f);
        static bool Enabled => (G.Settings?.Data?.Graphics?.Effects ?? "high") != "low";

        /// <summary>Impact accent (0..1 strength): finisher, ultimate, deflect, poise break.</summary>
        public static void Impact(float strength)
        {
            if (!Enabled || strength <= 0f) return;
            var p = Ensure();
            float f = FlashScale, m = MotionScale;
            // a short punch, not a white-out: small exposure kick with a saturation pop
            p.impactCa.intensity.Override(Mathf.Clamp01(0.55f * f));
            p.impactCol.postExposure.Override(0.2f * f);
            p.impactCol.saturation.Override(12f * f);
            p.impactCol.contrast.Override(8f * f);
            p.lens.intensity.Override(-0.32f * m);
            p.impact = Mathf.Max(p.impact, Mathf.Clamp01(strength));
        }

        /// <summary>Perfect-dodge focus for `seconds` of real time.</summary>
        public static void Focus(float seconds)
        {
            if (!Enabled) return;
            var p = Ensure();
            p.focusCa.intensity.Override(0.45f * FlashScale);
            p.focusHold = Mathf.Max(p.focusHold, seconds);
        }

        void Awake()
        {
            impactVol = MakeVolume("Impact", 21);
            var ip = impactVol.sharedProfile;
            impactCa = ip.Add<ChromaticAberration>(true);
            lens = ip.Add<LensDistortion>(true);
            lens.scale.Override(1.03f);
            impactCol = ip.Add<ColorAdjustments>(true);

            focusVol = MakeVolume("Focus", 20);
            var fp = focusVol.sharedProfile;
            focusCa = fp.Add<ChromaticAberration>(true);
            focusCol = fp.Add<ColorAdjustments>(true);
            focusCol.saturation.Override(-55f);
            focusCol.colorFilter.Override(new Color(0.86f, 0.95f, 1.08f));
            focusCol.contrast.Override(18f);
            focusVig = fp.Add<Vignette>(true);
            focusVig.intensity.Override(0.46f);
            focusVig.smoothness.Override(0.5f);
            focusVig.color.Override(new Color(0.01f, 0.05f, 0.09f));
        }

        Volume MakeVolume(string name, int priority)
        {
            var go = new GameObject("Vol_" + name);
            go.transform.SetParent(transform, false);
            var v = go.AddComponent<Volume>();
            v.isGlobal = true;
            v.priority = priority;
            v.weight = 0f;
            v.sharedProfile = ScriptableObject.CreateInstance<VolumeProfile>();
            return v;
        }

        void Update()
        {
            float dt = Time.unscaledDeltaTime;
            impact = Mathf.Max(0f, impact - dt / 0.22f);
            impactVol.weight = impact * impact;
            impactVol.enabled = impact > 0.001f;
            if (focusHold > 0f)
            {
                focusHold -= dt;
                focus = Mathf.MoveTowards(focus, 1f, dt / 0.05f);
            }
            else focus = Mathf.MoveTowards(focus, 0f, dt / 0.25f);
            focusVol.weight = focus;
            focusVol.enabled = focus > 0.001f;
        }

        void OnDestroy()
        {
            if (impactVol != null && impactVol.sharedProfile != null) Destroy(impactVol.sharedProfile);
            if (focusVol != null && focusVol.sharedProfile != null) Destroy(focusVol.sharedProfile);
            if (instance == this) instance = null;
        }
    }
}
