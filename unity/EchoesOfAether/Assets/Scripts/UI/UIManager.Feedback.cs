using System.Collections.Generic;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.UIElements;

namespace EOA
{
    // Toasts, hints, quest banner, save indicator, fades, cinematic bars and the skip prompt.
    public sealed partial class UIManager
    {
        sealed class TimedEl
        {
            public VisualElement El;
            public float Age;
            public float Life;
        }

        VisualElement toasts, barTop, barBot, skip, saveInd, saveSpin, fader;
        Label saveLabel, skipLabel, skipKey;
        RingGauge skipRing;
        readonly List<TimedEl> toastList = new();
        TimedEl hint, banner;
        float saveIndT;
        float spin;
        float fadeFrom, fadeTo, fadeT, fadeDur;
        TaskCompletionSource<bool> fadeTcs;

        void BuildFeedback()
        {
            var tl = Layer("layer-toasts");
            toasts = U.El("toasts");
            toasts.pickingMode = PickingMode.Ignore;
            tl.Add(toasts);

            barTop = U.El("letterbox top");
            barBot = U.El("letterbox bot");
            barTop.pickingMode = barBot.pickingMode = PickingMode.Ignore;
            Root.Add(barTop);
            Root.Add(barBot);

            skip = U.El("skip");
            skip.pickingMode = PickingMode.Ignore;
            skipRing = new RingGauge { Thickness = 2.5f, TrackColor = new Color(1, 1, 1, 0.2f), FillColor = U.Cyan };
            skipRing.AddToClassList("skip-ring");
            skipLabel = U.Label("", "skip-text");
            skipKey = U.Keycap("Space");
            skip.Add(skipRing);
            skip.Add(skipLabel);
            skip.Add(skipKey);
            Root.Add(skip);

            saveInd = U.El("saveind");
            saveInd.pickingMode = PickingMode.Ignore;
            saveSpin = U.El("saveind-spin");
            saveLabel = U.Label(U.Up(U.T("hud.saving")), "saveind-text");
            saveInd.Add(saveSpin);
            saveInd.Add(saveLabel);
            Root.Add(saveInd);
        }

        void BuildFader()
        {
            fader = U.El("fader");
            fader.pickingMode = PickingMode.Ignore;
            fader.style.opacity = 0;
            Root.Add(fader);
        }

        void FeedbackTick(float dt)
        {
            // Toasts: slide in, hold, fade out.
            for (var i = toastList.Count - 1; i >= 0; i--)
            {
                var t = toastList[i];
                t.Age += dt;
                if (t.Age >= t.Life)
                {
                    t.El.RemoveFromHierarchy();
                    toastList.RemoveAt(i);
                    continue;
                }
                float a, x;
                if (t.Age < 0.25f) { var k = 1 - Mathf.Pow(1 - t.Age / 0.25f, 3); a = k; x = (1 - k) * 27; }
                else if (t.Age > t.Life - 0.45f) { var k = (t.Age - (t.Life - 0.45f)) / 0.45f; a = 1 - k; x = k * 18; }
                else { a = 1; x = 0; }
                t.El.style.opacity = a;
                t.El.style.translate = new Translate(x, 0);
            }

            if (hint != null)
            {
                hint.Age += dt;
                var a = Mathf.Clamp01(hint.Age / 0.3f) * Mathf.Clamp01((hint.Life - hint.Age) / 0.3f);
                hint.El.style.opacity = a;
                if (hint.Age >= hint.Life) HideHint();
            }

            if (banner != null)
            {
                banner.Age += dt;
                var p = banner.Age / banner.Life;
                var a = p < 0.15f ? p / 0.15f : p > 0.8f ? 1 - (p - 0.8f) / 0.2f : 1;
                banner.El.style.opacity = Mathf.Clamp01(a);
                var title = banner.El.Q<Label>(className: "qb-t");
                if (title != null) title.style.letterSpacing = Mathf.Lerp(10, 4, Mathf.Clamp01(p / 0.3f));
                if (banner.Age >= banner.Life) { banner.El.RemoveFromHierarchy(); banner = null; }
            }

            if (saveIndT > 0)
            {
                saveIndT -= dt;
                spin = (spin + dt * 450) % 360;
                saveSpin.style.rotate = new Rotate(Angle.Degrees(spin));
                if (saveIndT <= 0) saveInd.RemoveFromClassList("on");
            }

            if (fadeDur > 0)
            {
                fadeT += dt;
                var k = Mathf.Clamp01(fadeT / fadeDur);
                var e = k * k * (3 - 2 * k);
                fader.style.opacity = Mathf.Lerp(fadeFrom, fadeTo, e);
                if (k >= 1)
                {
                    fadeDur = 0;
                    var tcs = fadeTcs;
                    fadeTcs = null;
                    tcs?.TrySetResult(true);
                }
            }
        }

        // ------------------------------------------------------------------ IPresentation

        public void Toast(string text, ToastKind kind = ToastKind.Info)
        {
            if (!built || string.IsNullOrEmpty(text)) return;
            var el = U.Label(text, "toast k-" + kind.ToString().ToLowerInvariant());
            el.pickingMode = PickingMode.Ignore;
            el.style.opacity = 0;
            toasts.Insert(0, el);
            toastList.Add(new TimedEl { El = el, Life = 4.3f });
            while (toastList.Count > 5)
            {
                // Drop the oldest.
                var oldest = toastList[0];
                oldest.El.RemoveFromHierarchy();
                toastList.RemoveAt(0);
            }
            if (kind == ToastKind.Item) G.Audio?.PlayUi("item");
        }

        public void Hint(string id)
        {
            if (!built || id == null || GameData.Hints == null || !GameData.Hints.TryGetValue(id, out var def)) return;
            HideHint();
            var box = U.El("hintbox");
            box.pickingMode = PickingMode.Ignore;
            box.Add(U.KeyText(def.Text, "keytext center"));
            box.style.opacity = 0;
            hintLayer.Add(box);
            hint = new TimedEl { El = box, Life = 8 };
        }

        public void HideHint()
        {
            if (hint == null) return;
            hint.El.RemoveFromHierarchy();
            hint = null;
        }

        public void QuestBanner(string questId)
        {
            if (!built || questId == null || !GameData.Quests.TryGetValue(questId, out var q)) return;
            if (banner != null) banner.El.RemoveFromHierarchy();
            var el = U.El("questbanner",
                U.Label(U.Up(U.T(q.IsMain ? "hud.missionComplete" : "hud.questComplete")), "qb-k"),
                U.Label(U.Up(q.Title), "qb-t"));
            el.pickingMode = PickingMode.Ignore;
            el.style.opacity = 0;
            hintLayer.Add(el);
            banner = new TimedEl { El = el, Life = 4.2f };
        }

        /// <summary>Save indicator; kind is "manual" | "auto" | "checkpoint".</summary>
        public void SaveIndicator(string kind)
        {
            if (!built) return;
            saveLabel.text = U.Up(U.T(kind == "manual" ? "hud.saved" : "hud.autosaved"));
            saveInd.AddToClassList("on");
            saveIndT = 2.2f;
        }

        public Task Fade(bool toBlack, float seconds)
        {
            EnsureBuilt();
            if (!built) return Task.CompletedTask;
            fadeTcs?.TrySetResult(false);
            var target = toBlack ? 1f : 0f;
            if (seconds <= 0)
            {
                FadeInstant(toBlack);
                return Task.CompletedTask;
            }
            fadeFrom = fader.resolvedStyle.opacity;
            if (!float.IsNaN(fader.style.opacity.value) && fader.style.opacity.keyword == StyleKeyword.Undefined) fadeFrom = fader.style.opacity.value;
            fadeTo = target;
            fadeT = 0;
            fadeDur = seconds;
            fadeTcs = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            return fadeTcs.Task;
        }

        public void FadeInstant(bool toBlack)
        {
            if (!built) return;
            fadeDur = 0;
            var tcs = fadeTcs;
            fadeTcs = null;
            tcs?.TrySetResult(false);
            fader.style.opacity = toBlack ? 1 : 0;
        }

        public void CinematicBars(bool on)
        {
            if (!built) return;
            BarsOn = on;
            barTop.EnableInClassList("on", on);
            barBot.EnableInClassList("on", on);
            if (!on) skip.RemoveFromClassList("on");
        }

        public void ShowSkipPrompt(bool on, float progress01 = 0)
        {
            if (!built) return;
            skip.EnableInClassList("on", on);
            if (!on) return;
            var hold = G.Settings?.Data.Accessibility.HoldToSkip ?? true;
            skipLabel.text = U.Up(U.T(hold ? "cine.holdSkip" : "cine.pressSkip"));
            skipKey.text = G.Input?.Label("skip") ?? "Space";
            skipRing.Set(hold ? progress01 : 0);
        }
    }
}
