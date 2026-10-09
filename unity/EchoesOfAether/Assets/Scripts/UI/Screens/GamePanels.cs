using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.UIElements;

namespace EOA
{
    /// <summary>In-game panels: Inventory, Map, Journal and Ability Matrix, switched with tabs.</summary>
    public static class GamePanels
    {
        static readonly string[] Names = { "inventory", "map", "journal", "skills" };

        // Remembered between openings (like the prototype's module state).
        static ItemCategory invCat = ItemCategory.Aether;
        static string invSel;
        static string journalTab = "active";
        static string journalSel;

        public static void Open(UIManager ui, string start)
        {
            if (ui.HasScreen("panel")) ui.Pop("panel");
            var current = Mathf.Max(0, Array.IndexOf(Names, start));
            var rendered = -1;
            var m = ScreenKit.MakeModal("", true, "modal modal-panels");
            m.Head.Add(U.Btn(U.T("panel.close"), () => ui.Pop("panel"), "btn-small"));
            var pad = G.Input != null && G.Input.UsingGamepad;
            m.Foot.Add(ScreenKit.HintLine((pad ? "B" : "Esc", "close"), ("← →", "navigate"), (pad ? "LB RB" : "Q E", "switch tabs")));
            UIScreen screen = null;

            void Select(int i)
            {
                current = (i + Names.Length) % Names.Length;
                if (screen != null) screen.Tag = Names[current];
                Render();
            }

            void Render()
            {
                m.Title.text = U.Up(U.T("panel." + Names[current]));
                ScreenKit.FillTabs(m.Tabs, Names.Select(n => U.T("panel." + n)).ToArray(), current, Select);
                m.Body.Clear();
                if (rendered != current) m.Body.scrollOffset = Vector2.zero;
                rendered = current;
                switch (Names[current])
                {
                    case "inventory": Inventory(ui, m.Body, Render); break;
                    case "map": Map(m.Body); break;
                    case "journal": Journal(m.Body, Render); break;
                    default: Skills(ui, m.Body, Render); break;
                }
                if (ui.Top == screen) ui.Refocus();
            }

            screen = new UIScreen("panel", m.Root)
            {
                Back = () => ui.Pop("panel"),
                Overlay = true,
                Tag = Names[current],
                Tab = dir => Select(current + dir),
            };
            Render();
            ui.Push(screen);
        }

        // ------------------------------------------------------------------ Inventory

        static readonly (ItemCategory cat, string key)[] Cats =
        {
            (ItemCategory.Aether, "inv.aether"), (ItemCategory.Powerups, "inv.powerups"), (ItemCategory.Quest, "inv.quest"),
            (ItemCategory.Upgrades, "inv.upgrades"), (ItemCategory.Lore, "inv.lore"),
        };

        static void Inventory(UIManager ui, VisualElement body, Action rerender)
        {
            var inv = G.Inventory;
            if (inv == null) return;
            var opts = Cats.Select(c => (c.cat.ToString(), $"{U.T(c.key)} ({inv.List(c.cat).Count})")).ToArray();
            var seg = new Seg(opts, invCat.ToString(), v =>
            {
                invCat = Cats.First(c => c.cat.ToString() == v).cat;
                invSel = null;
                rerender();
            });
            seg.AddToClassList("seg-left");
            var items = inv.List(invCat);
            if (invSel == null || !items.Any(i => i.def.Id == invSel)) invSel = items.Count > 0 ? items[0].def.Id : null;

            var grid = U.El("inv-grid");
            foreach (var (def, qty) in items)
            {
                var id = def.Id;
                var cell = U.BtnBox(() => { invSel = id; rerender(); }, $"item r-{def.Rarity}" + (id == invSel ? " sel" : ""), NavKind.Grid,
                    U.ItemIcon(def.Icon, U.RarityColor(def.Rarity), "icon item-icon"),
                    qty > 1 ? U.Label("×" + qty, "item-q") : null);
                cell.tooltip = def.Name;
                grid.Add(cell);
            }
            if (items.Count == 0) grid.Add(U.Label(U.T("inv.empty"), "dim"));

            var detail = U.El("detail");
            if (invSel != null && GameData.Items.TryGetValue(invSel, out var sel))
            {
                var col = U.RarityColor(sel.Rarity);
                detail.Add(U.ItemIcon(sel.Icon, col, "icon detail-icon"));
                detail.Add(U.Label(U.Up(sel.Name), "detail-nm"));
                var rar = U.Label(U.Up($"{sel.Rarity} · {sel.Category}"), "detail-rar");
                rar.style.color = col;
                detail.Add(rar);
                detail.Add(U.Label(sel.Description, "detail-ds"));
                var questTitle = sel.Quest != null && GameData.Quests.TryGetValue(sel.Quest, out var q) ? q.Title : sel.Quest;
                detail.Add(U.Label($"Quantity {inv.Count(sel.Id)} / {sel.Stack}" + (sel.Quest != null ? " · Quest: " + questTitle : ""), "faint detail-q"));
                if (sel.EffectType == "powerup")
                {
                    var sid = sel.Id;
                    detail.Add(U.Btn(U.T("inv.use"), () =>
                    {
                        if (G.Manager != null && G.Manager.UsePowerupItem(sid)) rerender();
                    }, "btn-small primary detail-use"));
                }
                var lore = sel.EffectType == "lore" ? sel.EffectStr("lore") : null;
                if (lore != null && GameData.Dialogues.ContainsKey(lore) && G.Dialogue != null)
                    foreach (var l in G.Dialogue.LinearLines(lore))
                    {
                        var h = U.Label(U.Up(l.Speaker?.Name ?? ""), "lore-h");
                        h.style.color = U.Hex(l.Speaker?.Color, U.Text);
                        detail.Add(U.El("lore-entry", h, U.Label(l.Text, "lore-l")));
                    }
            }
            body.Add(seg);
            body.Add(U.El("inv", grid, detail));
        }

        // ------------------------------------------------------------------ Map

        static void Map(VisualElement body)
        {
            var gm = G.Manager;
            if (gm == null) return;
            var map = gm.CurrentZoneMap;
            var meta = gm.CurrentZoneMeta;
            var pstat = gm.PlayerStatus;
            var pp = Hud.PlayerPos(pstat);
            var mv = new MapView { Fit = map != null, Round = false, Map = map, RadiusMeters = 80, Center = pp ?? Vector3.zero };
            mv.AddToClassList("map-canvas");
            mv.Player = pp;
            mv.PlayerYawDeg = pstat is Component pc && pc != null ? pc.transform.eulerAngles.y : 0;
            mv.Companion = Hud.CompanionPos(gm);
            mv.Objective = gm.ObjectiveWorldPosition;
            var npcs = map?.Npcs?.Invoke();
            if (npcs != null) mv.Npcs.AddRange(npcs);

            var objText = U.TrackedObjectiveText();
            var legend = U.El("legend",
                U.Label(U.Up(meta?.Name ?? gm.CurrentZone), "h2 legend-title"),
                U.Label(meta?.Subtitle ?? "", "faint"),
                Key(Color.white, "You"),
                Key(U.Violet, "Partner"),
                Key(U.Green, "Survivors"),
                Key(U.Amber, mv.Objective.HasValue && objText != null ? "Objective: " + objText : "No active objective"),
                ScreenKit.SectionTitle("Exits"));
            if (map != null)
                foreach (var mk in map.Markers.Where(x => x != null && x.Kind == MapMarkerKind.Exit))
                {
                    var locked = mk.Locked != null && mk.Locked();
                    legend.Add(Key(U.Cyan, $"{mk.Label} → {U.ZoneName(mk.TargetZone)}{(locked ? " (locked)" : "")}"));
                }
            if (map == null) legend.Add(U.Label("No map data for this area.", "faint"));
            body.Add(U.El("map-wrap", U.El("map-frame", mv), legend));
        }

        static VisualElement Key(Color c, string text)
        {
            var sw = U.El("legend-sw");
            sw.style.backgroundColor = c;
            return U.El("legend-row", sw, U.Label(text, "legend-t"));
        }

        // ------------------------------------------------------------------ Journal

        static void Journal(VisualElement body, Action rerender)
        {
            var st = G.State;
            var qs = G.Quests;
            if (st == null || qs == null) return;
            body.Add(U.El("completion",
                ScreenKit.Stat($"{U.CollectedCount("fragment")}/{GameData.CollectibleTotal("fragment")}", "Aether Fragments"),
                ScreenKit.Stat($"{U.CollectedCount("recording")}/{GameData.CollectibleTotal("recording")}", "Memory Recordings"),
                ScreenKit.Stat($"{U.CollectedCount("cache")}/{GameData.CollectibleTotal("cache")}", "Hidden Caches")));
            var seg = new Seg(new[] { ("active", U.T("journal.active")), ("completed", U.T("journal.completed")), ("lore", U.T("journal.lore")) }, journalTab, v =>
            {
                journalTab = v;
                journalSel = null;
                rerender();
            });
            seg.AddToClassList("seg-left");
            body.Add(seg);

            if (journalTab == "lore")
            {
                var wrap = U.El("lore-list");
                if (st.D.Lore.Count == 0) wrap.Add(U.Label("No lore discovered yet. Recordings and research logs appear here.", "dim"));
                foreach (var id in st.D.Lore)
                {
                    var item = GameData.ItemList.FirstOrDefault(i => i.EffectType == "lore" && i.EffectStr("lore") == id);
                    var entry = U.El("lore-entry", U.Label(U.Up(item?.Name ?? id), "lore-h"));
                    if (G.Dialogue != null)
                        foreach (var l in G.Dialogue.LinearLines(id))
                        {
                            var hex = l.Speaker?.Color ?? "#dfe7ee";
                            entry.Add(U.Label($"<color={hex}><b>{l.Speaker?.Name}:</b></color> {l.Text}", "lore-l"));
                        }
                    wrap.Add(entry);
                }
                body.Add(wrap);
                return;
            }

            var active = journalTab == "active";
            var quests = active ? qs.Active() : qs.Completed();
            if (journalSel == null || !quests.Any(q => q.Id == journalSel)) journalSel = quests.Count > 0 ? quests[0].Id : null;
            var list = U.El("qlist");
            foreach (var q in quests)
            {
                var id = q.Id;
                list.Add(U.BtnBox(() => { journalSel = id; rerender(); }, "btn qbtn" + (id == journalSel ? " current" : ""), NavKind.Button,
                    U.Label(U.Up(q.Title), "btn-main"),
                    U.Label(U.T(q.IsMain ? "hud.mission" : "hud.side"), "btn-sub")));
            }
            if (quests.Count == 0) list.Add(U.Label(active ? "No active quests." : "Nothing completed yet.", "dim"));

            var detail = U.El("qd");
            if (journalSel != null && GameData.Quests.TryGetValue(journalSel, out var qd))
            {
                detail.Add(U.Label(U.Up(qd.IsMain ? $"{U.T("hud.mission")} {qd.Order}" : U.T("hud.side")), "kicker"));
                detail.Add(U.Label(U.Up(qd.Title), "qd-t"));
                detail.Add(U.Label(qd.Summary ?? "", "qd-s"));
                if (active)
                {
                    foreach (var o in qs.CurrentObjectives(qd.Id))
                    {
                        var txt = qs.ObjectiveText(o.Def) + (o.Required > 1 ? $" ({o.Progress}/{o.Required})" : "");
                        detail.Add(U.El("qd-o" + (o.Done ? " done" : ""), U.El("dot"), U.Label(o.Done ? $"<s>{txt}</s>" : txt, "qd-o-t")));
                    }
                    var tracked = qs.Tracked()?.Id == qd.Id;
                    var qid = qd.Id;
                    var tb = U.Btn(U.T(tracked ? "journal.tracked" : "journal.track"), () =>
                    {
                        if (G.Manager != null) G.Manager.TrackQuest(qid);
                        else qs.Track(qid);
                        rerender();
                    }, "btn-small qd-track" + (tracked ? "" : " primary"));
                    tb.SetEnabled(!tracked);
                    detail.Add(tb);
                }
                else detail.Add(U.Label("✓ Completed", "dim"));
            }
            body.Add(U.El("journal", list, detail));
        }

        // ------------------------------------------------------------------ Ability Matrix

        static void Skills(UIManager ui, VisualElement body, Action rerender)
        {
            var prog = G.Progression;
            var st = G.State;
            if (prog == null || st == null) return;
            body.Add(U.El("skills-head",
                U.Label("Spend Aether to upgrade abilities. Each Aether Fragment is worth 1 point and each Aether Core is worth 3. Nodes unlock in order.", "dim skills-desc"),
                U.El("skills-points", U.Label(U.Up(U.T("skills.points")), "faint skills-points-l"), U.Label(prog.Points().ToString(), "points"))));
            var tree = U.El("tree");
            foreach (var ch in new[] { Characters.Kael, Characters.Lyra })
            {
                var head = U.Label(U.Up(Characters.DisplayName(ch)), "tree-h");
                head.style.color = U.HeroColor(ch);
                var col = U.El("tree-col", head);
                foreach (var ab in GameData.AbilityList.Where(x => x.Character == ch && x.Slot != "ultimate"))
                {
                    var unlocked = st.HasAbility(ab.Id);
                    col.Add(U.Label(U.Up(ab.Name + (unlocked ? "" : " · locked")), "tree-ab faint"));
                    var row = U.El("tree-row");
                    foreach (var n in GameData.SkillList.Where(s => s.Ability == ab.Id))
                    {
                        var owned = prog.HasSkill(n.Id);
                        var (ok, reason) = prog.CanBuy(n.Id);
                        var nid = n.Id;
                        var node = U.BtnBox(() =>
                        {
                            if (owned) return;
                            if (prog.Buy(nid))
                            {
                                G.Audio?.PlayUi("quest_accept");
                                rerender();
                            }
                            else
                            {
                                G.Audio?.PlayUi("error_ui");
                                ui.Toast(reason ?? "Unavailable", ToastKind.Warn);
                            }
                        }, "node " + (owned ? "owned" : ok ? "avail" : "locked"), NavKind.Grid,
                            U.Label(owned ? "✓" : n.Cost.ToString(), "node-c"),
                            U.Label(U.Up(n.Name), "node-n"),
                            U.Label(n.Description, "node-d"));
                        node.tooltip = owned ? "Unlocked" : ok ? U.T("skills.unlock") : reason ?? "";
                        row.Add(node);
                    }
                    col.Add(row);
                }
                tree.Add(col);
            }
            body.Add(tree);
        }
    }
}
