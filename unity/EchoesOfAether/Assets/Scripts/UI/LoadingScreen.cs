using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;

namespace EOA
{
    /// <summary>Zone loading screen: art with a slow pan, zone name/subtitle/quote, a gameplay hint and progress.</summary>
    public sealed class LoadingScreen
    {
        static readonly Dictionary<string, (string a, string b)> ZoneTint = new()
        {
            ["plaza"] = ("#1b2a3a", "#0a0f16"),
            ["metro"] = ("#2a1a14", "#0a0808"),
            ["facility"] = ("#162630", "#080c10"),
            ["vault"] = ("#1a1636", "#07060f"),
            ["rooftops"] = ("#1c2232", "#07090e"),
            ["core"] = ("#13283a", "#05080e"),
        };

        public readonly VisualElement Root;
        readonly UIManager ui;
        readonly VisualElement artBack, art, fill, hint, errBox;
        readonly Label name, sub, quote, stage, pct, err;
        Texture2D artTex;
        float t;
        public bool Visible { get; private set; }

        public LoadingScreen(UIManager ui)
        {
            this.ui = ui;
            artBack = U.El("loading-artback");
            art = U.El("loading-art");
            name = U.Label("", "zone-name");
            sub = U.Label("", "zone-sub");
            quote = U.Label("", "quote");
            hint = U.El("loading-hint");
            fill = U.El("loading-fill");
            stage = U.Label("", "loading-stage-l");
            pct = U.Label("", "loading-stage-r");
            err = U.Label("", "loading-err");
            errBox = err;
            var left = U.El("loading-left", U.Label(U.Up(U.T("loading.loading")), "kicker"), U.El("spacer-s"), name, sub, quote);
            var right = U.El("loading-right", hint, U.El("loading-bar", fill), U.El("loading-stage", stage, pct), err);
            Root = U.El("screen loading", artBack, art, U.El("loading-vignette"), U.El("loading-shade"), U.El("loading-content", left, right));
            Root.Query<VisualElement>().ForEach(e => e.pickingMode = PickingMode.Ignore);
            Root.pickingMode = PickingMode.Position; // block clicks while loading
            U.Show(Root, false);
        }

        public void Show(ZoneMeta meta)
        {
            Visible = true;
            U.Show(Root, true);
            U.Show(errBox, false);
            name.text = U.Up(meta?.Name ?? "");
            sub.text = U.Up(meta?.Subtitle ?? "");
            quote.text = meta?.Quote ?? "";
            var hints = meta?.Hints;
            var h = hints != null && hints.Length > 0 ? hints[Random.Range(0, hints.Length)] : "";
            U.FillKeyText(hint, h);
            (string a, string b) tint = meta != null && ZoneTint.TryGetValue(meta.Id, out var z) ? z : ("#1b2a3a", "#0a0f16");
            Root.style.backgroundColor = U.Hex(tint.b);
            artBack.style.backgroundColor = U.Hex(tint.a);
            ReleaseArt();
            artTex = meta != null ? Resources.Load<Texture2D>("Art/Loading/" + meta.Id) : null;
            art.style.backgroundImage = artTex != null ? new StyleBackground(artTex) : new StyleBackground(StyleKeyword.None);
            U.Show(art, artTex != null);
            t = 0;
            Pan();
            Progress(0, "");
        }

        public void Progress(float f, string label)
        {
            f = Mathf.Clamp01(f);
            fill.style.width = Length.Percent(f * 100);
            if (!string.IsNullOrEmpty(label)) stage.text = U.Up(label);
            pct.text = Mathf.RoundToInt(f * 100) + "%";
        }

        public void Error(string msg)
        {
            err.text = "Failed to load: " + msg;
            U.Show(errBox, true);
        }

        public void Hide()
        {
            if (!Visible) return;
            Visible = false;
            U.Show(Root, false);
            ReleaseArt();
        }

        void ReleaseArt()
        {
            if (artTex == null) return;
            art.style.backgroundImage = new StyleBackground(StyleKeyword.None);
            Resources.UnloadAsset(artTex);
            artTex = null;
        }

        public void Tick(float dt)
        {
            if (!Visible) return;
            t += dt;
            Pan();
        }

        /// <summary>Slow Ken Burns pan: scale 1.04 to 1.12 and drift left over 30 s (ease-out).</summary>
        void Pan()
        {
            var k = Mathf.Clamp01(t / 30f);
            k = 1 - (1 - k) * (1 - k);
            var s = 1.04f + 0.08f * k;
            art.style.scale = new Scale(new Vector3(s, s, 1));
            art.style.translate = new Translate(Length.Percent(-1.5f * k), 0);
        }
    }
}
