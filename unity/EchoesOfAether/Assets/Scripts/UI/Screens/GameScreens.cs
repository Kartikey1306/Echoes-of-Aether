using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.UIElements;

namespace EOA
{
    // ---------------------------------------------------------------------------------------------- Pause
    public static class PauseScreen
    {
        public static void Open(UIManager ui)
        {
            var gm = G.Manager;
            if (gm == null) return;
            var side = U.El("pause-side",
                U.Label(U.Up(gm.CurrentZoneMeta?.Name ?? ""), "kicker"),
                U.Label(U.Up(U.T("pause.title")), "h2 pause-title"));
            void Resume() => ui.Pop("pause");
            void Btn(string label, Action fn, bool disabled = false, string sub = null)
            {
                var b = U.BtnBox(fn, "btn", NavKind.Button,
                    U.Label(U.Up(label), "btn-main"),
                    string.IsNullOrEmpty(sub) ? null : U.Label(sub, "btn-sub"));
                b.SetEnabled(!disabled);
                side.Add(b);
            }
            var canSave = gm.CanSaveNow(out var why);
            Btn(U.T("pause.resume"), Resume);
            Btn(U.T("pause.save"), () => ui.OpenSaveScreen(true), !canSave, canSave ? null : why);
            Btn(U.T("pause.load"), () => ui.OpenSaveScreen(false));
            Btn(U.T("pause.inventory"), () => ui.OpenPanel("inventory"));
            Btn(U.T("pause.map"), () => ui.OpenPanel("map"));
            Btn(U.T("pause.journal"), () => ui.OpenPanel("journal"));
            Btn(U.T("pause.skills"), () => ui.OpenPanel("skills"));
            Btn(U.T("pause.appearance"), () => ui.OpenDesigner(G.State?.D.Character ?? gm.SelectedCharacter));
            Btn(U.T("pause.settings"), () => ui.OpenSettings(true));
            Btn(U.T("pause.quitMenu"), () => U.Run(async () =>
            {
                if (!await ui.Confirm(U.T("pause.quitMenu"), U.T("pause.quitConfirm"), U.T("pause.quitMenu"), true)) return;
                await gm.QuitToMenu(); // fades out over the pause screen; ShowMainMenu clears the stack
            }));

            var q = G.Quests?.Tracked();
            var d = G.State?.D;
            var summary = U.El("pause-summary",
                U.Label(q == null ? "" : U.Up(U.T(q.IsMain ? "hud.mission" : "hud.side")), "kicker"),
                U.Label(U.Up(q?.Title ?? "Aether-9"), "h1"),
                U.Label(q?.Summary ?? "", "pause-text"));
            if (d != null)
            {
                var done = d.Quests.Values.Count(x => x.Status == "done");
                summary.Add(U.El("stat-grid",
                    ScreenKit.Stat(U.FmtTime(d.Stats.Playtime), U.T("pause.playtime")),
                    ScreenKit.Stat(d.Stats.Kills.ToString(), U.T("pause.kills")),
                    ScreenKit.Stat(done.ToString(), "Quests done"),
                    ScreenKit.Stat($"{U.CollectedCount("fragment")}/{GameData.CollectibleTotal("fragment")}", "Aether Fragments"),
                    ScreenKit.Stat($"{U.CollectedCount("recording")}/{GameData.CollectibleTotal("recording")}", "Recordings"),
                    ScreenKit.Stat($"{U.CollectedCount("cache")}/{GameData.CollectibleTotal("cache")}", "Hidden Caches")));
            }
            var root = U.El("screen dim-bg pause", U.El("dim-vignette"), side, summary);
            ui.Push(new UIScreen("pause", root) { Back = Resume, Overlay = true });
        }
    }

    // ---------------------------------------------------------------------------------------------- Save / Load
    public static class SavesScreen
    {
        public static void Open(UIManager ui, bool save)
        {
            if (ui.HasScreen("saves")) return;
            var gm = G.Manager;
            var m = ScreenKit.MakeModal(U.T(save ? "saves.saveTitle" : "saves.loadTitle"), false, "modal modal-saves");
            m.Head.Add(U.Btn(U.T("panel.close"), () => ui.Pop("saves"), "btn-small"));
            m.Foot.Add(U.Label("Atomic writes with a rolling backup per slot", "foot-note"));
            var thumbs = new List<Texture2D>();
            UIScreen screen = null;

            void FreeThumbs()
            {
                foreach (var t in thumbs) if (t != null) UnityEngine.Object.Destroy(t);
                thumbs.Clear();
            }

            void Render()
            {
                FreeThumbs();
                m.Body.Clear();
                var list = U.El("slots");
                foreach (var info in G.Saves.AllInfo())
                {
                    var i = info;
                    var e = i.Envelope;
                    var thumb = U.El("slot-thumb");
                    var tex = e != null ? U.DecodeImage(e.Thumbnail) : null;
                    if (tex != null)
                    {
                        thumbs.Add(tex);
                        thumb.style.backgroundImage = new StyleBackground(tex);
                    }
                    else thumb.Add(U.Label(e != null ? "" : i.Status == "empty" ? U.Up(U.T("saves.empty")) : "!", "slot-thumb-t"));

                    var col = U.El("slot-info", U.Label(U.Up($"{U.T("saves.slot")} {i.Slot}{(e != null ? " · " + e.Mission : "")}"), "slot-t"));
                    if (e != null)
                        col.Add(U.Label($"{U.ZoneName(e.Zone)} · {Characters.FirstName(e.Character)} · {U.FmtTime(e.Playtime)}\n{U.FmtDate(e.Timestamp)} · {e.Kind}", "slot-m"));
                    else if (i.Status == "empty")
                        col.Add(U.Label(U.T("saves.empty"), "slot-m"));
                    else
                    {
                        var rec = i.Status == "recovered";
                        col.Add(U.Label(U.Up(U.T(rec ? "saves.recovered" : "saves.corrupt")), "slot-st " + (rec ? "rec" : "bad")));
                        col.Add(U.Label(i.Error ?? "", "slot-m"));
                    }

                    var acts = U.El("slot-acts");
                    void Act(string label, string cls, Action fn) => acts.Add(U.Btn(label, fn, "btn-small " + cls));
                    if (save)
                    {
                        Act(U.T("saves.save"), "primary", () => U.Run(async () =>
                        {
                            if (i.Status != "empty" && i.Slot != G.Saves.ActiveSlot &&
                                !await ui.Confirm(U.T("saves.overwrite"), $"{U.T("saves.slot")} {i.Slot}", U.T("saves.save"), true)) return;
                            if (gm != null && gm.ManualSave(i.Slot)) Render();
                        }));
                    }
                    else if (e != null)
                    {
                        Act(U.T("saves.load"), "primary", () => U.Run(async () =>
                        {
                            ui.HideAllScreens();
                            if (gm != null) await gm.LoadFromEnvelope(e);
                        }));
                    }
                    if (i.Status != "ok" && i.Backup != null)
                        Act(U.T("saves.recover"), "", () => { G.Saves.Recover(i.Slot); Render(); });
                    if (!save && e == null && i.Backup != null && i.Status == "recovered")
                    {
                        var bak = i.Backup;
                        Act(U.T("saves.load") + " (backup)", "", () => U.Run(async () =>
                        {
                            ui.HideAllScreens();
                            if (gm != null) await gm.LoadFromEnvelope(bak);
                        }));
                    }
                    if (i.Status != "empty")
                    {
                        Act(U.T("saves.delete"), "danger", () => U.Run(async () =>
                        {
                            if (!await ui.Confirm(U.T("saves.delete"), U.T("saves.deleteConfirm"), U.T("saves.delete"), true)) return;
                            G.Saves.Delete(i.Slot);
                            Render();
                        }));
                    }
                    list.Add(U.El("slot-card", thumb, col, acts));
                }
                m.Body.Add(list);
                if (ui.Top == screen) ui.Refocus();
            }

            screen = new UIScreen("saves", m.Root)
            {
                Back = () => ui.Pop("saves"),
                Overlay = gm != null && gm.Mode == GameMode.Play,
                OnClose = FreeThumbs,
            };
            Render();
            ui.Push(screen);
        }
    }

    // ---------------------------------------------------------------------------------------------- Death
    public static class DeathScreen
    {
        public static void Open(UIManager ui)
        {
            var gm = G.Manager;
            var acts = U.El("death-acts",
                U.Btn(U.T("death.retry"), () =>
                {
                    ui.Pop("death");
                    if (gm != null) U.Run(() => gm.RetryFromCheckpoint());
                }, "btn autofocus"),
                U.Btn(U.T("death.load"), () =>
                {
                    ui.Pop("death");
                    if (gm != null) U.Run(() => gm.LoadLastSave());
                }),
                U.Btn(U.T("death.quit"), () =>
                {
                    ui.Pop("death");
                    if (gm != null) U.Run(() => gm.QuitToMenu());
                }));
            var box = U.El("death-box",
                U.Label(U.Up(U.T("death.title")), "death-t"),
                U.Label(U.T("death.sub"), "death-s"),
                acts);
            var root = U.El("screen death", U.El("death-vignette"), box);
            ui.Push(new UIScreen("death", root) { Overlay = true });
        }
    }
}
