using System.Collections.Generic;
using System.Linq;
using System.Text;
using UnityEngine;
using UnityEngine.UIElements;

namespace EOA
{
    /// <summary>
    /// Gameplay HUD: vitals, abilities with cooldown rings, ultimate ring, quest tracker, rotating minimap,
    /// powerup timers, interaction prompt, crosshair, hit/kill markers, objective marker, enemy bars and boss bar.
    /// </summary>
    public sealed class Hud
    {
        sealed class Slot
        {
            public VisualElement Root, Box, Icon, Lock;
            public RingGauge Cd;
            public Label CdText, Key, Charges;
            public int CdShown = int.MinValue, ChargesShown = int.MinValue;
        }

        sealed class EnemyBar
        {
            public VisualElement Root, Fill, Poise;
            public Label Name;
            public string RawName;
        }

        sealed class PowerupEl
        {
            public VisualElement Root, Ring;
            public Label Time;
            public int Shown = int.MinValue;
        }

        public readonly VisualElement Root;
        readonly UIManager ui;

        // Vitals
        VisualElement portrait, swapKeyWrap, hpFill, hpTrail, shFill, enFill;
        Label portraitInitial, swapKey, nameLabel, hpNum, shNum;
        float trailW = 1;
        // Last values written to labels: text is rebuilt only when the shown number changes (no per-frame garbage).
        int hpShown = int.MinValue, maxHpShown = int.MinValue, shShown = int.MinValue, markerShown = int.MinValue;
        string promptRaw, zoneShown, bossRaw;
        int bossPhaseShown = -1;
        readonly List<string> puIds = new();
        int trackerHash;
        readonly List<ObjectiveStatus> objBuf = new();
        // Abilities (the driving HUD replaces them in a car)
        VisualElement abilities;
        DriveHud drive;
        bool drivingShown;
        Slot bolt, dash, ability;
        VisualElement ultRoot, ult, ultIcon;
        RingGauge ultRing;
        Label ultKey;
        // Tracker
        VisualElement tracker, trackerHead;
        string trackerKey = "";
        float trackerFlash;
        // Minimap
        MapView mini;
        Label miniZone;
        float miniT;
        // Powerups
        VisualElement pus;
        readonly Dictionary<string, PowerupEl> puEls = new();
        // Prompt, crosshair, markers
        VisualElement prompt, cross, hitm, marker;
        Label promptKey, promptText, markerD;
        float hitT;
        readonly List<EnemyBar> ebars = new();
        readonly Dictionary<int, float> lastHit = new();
        // Boss
        VisualElement boss, bossFill;
        Label bossName, bossPhase;
        int bossPhaseNum;

        string character;
        bool padLabels;
        float keyT;
        bool visible;
        Texture2D portraitTex;

        public Hud(UIManager ui)
        {
            this.ui = ui;
            Root = U.El("hud fade");
            Build();
            IgnorePicking(Root);
        }

        public void Dispose() { }

        static void IgnorePicking(VisualElement e) => e.Query<VisualElement>().ForEach(x => x.pickingMode = PickingMode.Ignore);

        // ------------------------------------------------------------------ Build

        void Build()
        {
            // Vitals
            portrait = U.El("portrait");
            portraitInitial = U.Label("", "portrait-initial");
            portrait.Add(portraitInitial);
            swapKey = U.Keycap("T");
            swapKeyWrap = U.El("portrait-swap", swapKey);
            portrait.Add(swapKeyWrap);
            nameLabel = U.Label("", "vit-name");
            var sh = U.El("bar sh", shFill = U.El("bar-fill"));
            var hp = U.El("bar hp", hpTrail = U.El("bar-trail"), hpFill = U.El("bar-fill"));
            var en = U.El("bar en", enFill = U.El("bar-fill"));
            hpNum = U.Label("", "vit-num-l");
            shNum = U.Label("", "vit-num-r");
            var bars = U.El("vit-bars", nameLabel, sh, hp, en, U.El("vit-num", hpNum, shNum));
            Root.Add(U.El("vitals", portrait, bars));

            // Abilities (bolt, dash, ability, ultimate)
            var abWrap = U.El("abilities");
            bolt = MakeSlot("hud.bolt");
            dash = MakeSlot("hud.dash");
            ability = MakeSlot("hud.ability");
            abWrap.Add(bolt.Root);
            abWrap.Add(dash.Root);
            abWrap.Add(ability.Root);
            ultRing = new RingGauge { Thickness = 3, Background = new Color(6 / 255f, 9 / 255f, 13 / 255f, 0.7f), TrackColor = new Color(1, 1, 1, 0.12f), FillColor = U.Cyan };
            ultRing.AddToClassList("ult-ring");
            ultIcon = U.El("icon ult-icon");
            ult = U.El("ult", ultRing, ultIcon);
            ultKey = U.Keycap("X");
            ultRoot = U.El("ab ult-wrap", ult, U.El("ab-kc", ultKey), U.Label(U.Up(U.T("hud.ult")), "ab-lbl"));
            abWrap.Add(ultRoot);
            Root.Add(abWrap);
            abilities = abWrap;
            drive = new DriveHud();
            Root.Add(drive.Root);

            // Tracker
            tracker = U.El("tracker");
            Root.Add(tracker);

            // Minimap
            mini = new MapView { Round = true, RadiusMeters = 55 };
            miniZone = U.Label("", "minimap-zone");
            Root.Add(U.El("minimap", U.El("minimap-disc", mini), miniZone));

            // Powerups
            pus = U.El("powerups");
            Root.Add(pus);

            // Prompt, crosshair, hit marker, objective marker
            promptKey = U.Keycap("E");
            promptText = U.Label("", "prompt-text");
            prompt = U.El("prompt", promptKey, promptText);
            U.Show(prompt, false);
            Root.Add(prompt);
            cross = U.El("crosshair", U.El("cross-v"), U.El("cross-h"));
            Root.Add(cross);
            hitm = U.El("hitmark");
            Root.Add(hitm);
            markerD = U.Label("", "marker-d");
            marker = U.El("marker", U.El("marker-m"), markerD);
            U.Show(marker, false);
            Root.Add(marker);

            for (var i = 0; i < 10; i++)
            {
                var b = new EnemyBar { Name = U.Label("", "ebar-n"), Fill = U.El("ebar-fill"), Poise = U.El("ebar-pfill") };
                b.Root = U.El("ebar", b.Name, U.El("ebar-b", b.Fill), U.El("ebar-p", b.Poise));
                U.Show(b.Root, false);
                ebars.Add(b);
                Root.Add(b.Root);
            }

            bossFill = U.El("bossbar-fill");
            bossName = U.Label("", "bossbar-n");
            bossPhase = U.Label("", "bossbar-ph");
            boss = U.El("bossbar", bossName, U.El("bossbar-b", bossFill), bossPhase);
            U.Show(boss, false);
            Root.Add(boss);
        }

        Slot MakeSlot(string labelKey)
        {
            var s = new Slot
            {
                Box = U.El("slot"),
                Icon = U.El("icon slot-icon"),
                Cd = new RingGauge { Pie = true, FillColor = new Color(0, 0, 0, 0.62f) },
                CdText = U.Label("", "slot-cdt"),
                Lock = U.Icon("lock", U.LockGrey, "icon slot-lock"),
                Charges = U.Label("", "charges"),
                Key = U.Keycap(""),
            };
            s.Cd.AddToClassList("slot-cd");
            s.Box.Add(s.Icon);
            s.Box.Add(s.Cd);
            s.Box.Add(s.CdText);
            s.Box.Add(s.Lock);
            s.Box.Add(s.Charges);
            s.Root = U.El("ab", s.Box, U.El("ab-kc", s.Key), U.Label(U.Up(U.T(labelKey)), "ab-lbl"));
            return s;
        }

        // ------------------------------------------------------------------ Events

        public void OnEnemyDamaged(int id)
        {
            lastHit[id] = Time.unscaledTime;
            HitMarker();
        }

        public void HitMarker()
        {
            hitT = 0.12f;
            hitm.RemoveFromClassList("kill");
            hitm.AddToClassList("on");
        }

        public void KillMarker()
        {
            hitT = 0.25f;
            hitm.AddToClassList("on");
            hitm.AddToClassList("kill");
        }

        public void OnBossPhase(string id, int phase)
        {
            bossPhaseNum = phase;
        }

        /// <summary>Refresh portrait, name, icons and colours for the controlled hero.</summary>
        public void CharacterChanged()
        {
            var p = G.Manager?.PlayerStatus;
            character = p?.Character ?? G.State?.D.Character ?? Characters.Kael;
            var kael = character == Characters.Kael;
            var color = U.HeroColor(character);
            portrait.EnableInClassList("kael", kael);
            portrait.EnableInClassList("lyra", !kael);
            portraitTex = U.Portrait(character);
            portrait.style.backgroundImage = portraitTex != null ? new StyleBackground(portraitTex) : new StyleBackground(StyleKeyword.None);
            portraitInitial.text = portraitTex != null ? "" : Characters.FirstName(character).Substring(0, 1);
            portraitInitial.style.color = color;
            nameLabel.text = U.Up(Characters.DisplayName(character));
            U.SetIcon(ability.Icon, kael ? "ab_pulse" : "ab_echo", color);
            U.SetIcon(dash.Icon, kael ? "ab_dash" : "ab_step", color);
            U.SetIcon(bolt.Icon, "ab_bolt", color);
            U.SetIcon(ultIcon, kael ? "ab_corebreak" : "ab_resonance", color);
            ultRing.SetColors(color, new Color(1, 1, 1, 0.12f));
            RefreshKeys();
        }

        public void RefreshKeys()
        {
            var inp = G.Input;
            if (inp == null) return;
            padLabels = inp.UsingGamepad;
            ability.Key.text = inp.Label("ability");
            dash.Key.text = inp.Label("dash");
            bolt.Key.text = inp.Label("bolt");
            ultKey.text = inp.Label("ultimate");
            swapKey.text = inp.Label("swap");
            promptKey.text = inp.Label("interact");
            drive?.RefreshKeys(inp);
        }

        // ------------------------------------------------------------------ Frame

        void SetVisible(bool v)
        {
            if (v == visible) return;
            visible = v;
            Root.EnableInClassList("fade", !v);
        }

        public void Tick(float dt)
        {
            if (hitT > 0)
            {
                hitT -= dt;
                if (hitT <= 0) hitm.RemoveFromClassList("on");
            }
            var gm = G.Manager;
            var p = gm != null ? gm.PlayerStatus : null;
            var show = gm != null && p != null && ui.HudEnabled && gm.Mode == GameMode.Play && !gm.Paused && !ui.BarsOn && !ui.LoadingVisible;
            SetVisible(show);
            if (!show) return;

            if (p.Character != character) CharacterChanged();
            keyT -= dt;
            if (keyT <= 0 || G.Input != null && G.Input.UsingGamepad != padLabels)
            {
                keyT = 0.5f;
                RefreshKeys();
            }
            var st = p.Stats;
            UpdateVitals(p, st, dt);
            var driving = Driving.Active;
            if (driving != drivingShown) { drivingShown = driving; U.Show(abilities, !driving); }
            drive.Tick(driving);
            if (!driving) UpdateAbilities(p, st);
            UpdatePowerups();
            UpdateTracker(dt);
            UpdatePrompt(gm, p);
            cross.EnableInClassList("on", gm.Aiming);
            var cam = Camera.main;
            UpdateMarker(gm, p, cam);
            miniT -= dt;
            if (miniT <= 0)
            {
                miniT = 1f / 20f;
                UpdateMinimap(gm, p, cam);
            }
            UpdateEnemyBars(gm, p, cam);
        }

        void UpdateVitals(IHeroStatus p, CharStats st, float dt)
        {
            var hpF = st.MaxHealth > 0 ? Mathf.Clamp01(p.Health / st.MaxHealth) : 0;
            hpFill.style.width = Length.Percent(hpF * 100);
            trailW = Mathf.Max(hpF, trailW - dt * 0.4f);
            hpTrail.style.width = Length.Percent(trailW * 100);
            shFill.style.width = Length.Percent((st.MaxShield > 0 ? Mathf.Clamp01(p.Shield / st.MaxShield) : 0) * 100);
            enFill.style.width = Length.Percent((st.MaxEnergy > 0 ? Mathf.Clamp01(p.Energy / st.MaxEnergy) : 0) * 100);
            int hpI = Mathf.CeilToInt(p.Health), maxI = Mathf.RoundToInt(st.MaxHealth), shI = Mathf.FloorToInt(p.Shield);
            if (hpI != hpShown || maxI != maxHpShown) { hpShown = hpI; maxHpShown = maxI; hpNum.text = $"{hpI} / {maxI}"; }
            if (shI != shShown) { shShown = shI; shNum.text = $"{shI} SH"; }
            U.Show(swapKeyWrap, G.State != null && G.State.Flag("swap_unlocked"));
        }

        void UpdateAbilities(IHeroStatus p, CharStats st)
        {
            var kael = p.Character == Characters.Kael;
            var st8 = G.State;
            var abId = kael ? "pulse" : "echo";
            GameData.Abilities.TryGetValue(abId, out var abDef);
            var abCdMax = (abDef?.Cooldown ?? (kael ? 6 : 4)) * st.CooldownMul;
            var abCd = p.Cooldown01("ability");
            SetSlot(ability, st8 != null && st8.HasAbility(abId), abCd, abCd * abCdMax, p.Energy >= (abDef?.Energy ?? (kael ? 35 : 25)));

            var dashId = kael ? "dash" : "step";
            var dCd = p.Cooldown01("dash");
            SetSlot(dash, st8 != null && st8.HasAbility(dashId), dCd, dCd * st.DashCooldown * st.CooldownMul, true);
            var charges = p as IHeroDashInfo;
            var ch = charges != null && charges.MaxDashCharges > 1 ? charges.DashCharges : -1;
            if (ch != dash.ChargesShown) { dash.ChargesShown = ch; dash.Charges.text = ch >= 0 ? ch.ToString() : ""; }

            var bCd = p.Cooldown01("bolt");
            SetSlot(bolt, true, bCd, 0, p.Energy >= 6);

            var ultOn = st.Ultimates;
            ultRoot.EnableInClassList("locked", !ultOn);
            ultRing.Set(ultOn ? p.Ultimate : 0);
            ult.EnableInClassList("full", ultOn && p.Ultimate >= 0.999f);
        }

        static void SetSlot(Slot s, bool unlocked, float cd01, float cdSeconds, bool affordable)
        {
            s.Root.EnableInClassList("locked", !unlocked);
            s.Root.EnableInClassList("ready", unlocked && cd01 <= 0.001f && affordable);
            s.Cd.Set(unlocked ? cd01 : 1);
            U.Show(s.Lock, !unlocked);
            // Tenths under a second, whole seconds above; the label only changes when the shown value does.
            var key = !(unlocked && cdSeconds > 0.05f) ? -1 : cdSeconds < 1 ? Mathf.RoundToInt(cdSeconds * 10) : 1000 + Mathf.RoundToInt(cdSeconds);
            if (key != s.CdShown) { s.CdShown = key; s.CdText.text = key < 0 ? "" : cdSeconds.ToString(cdSeconds < 1 ? "0.0" : "0"); }
        }

        void UpdatePowerups()
        {
            var act = G.Powerups?.Active;
            if (act == null) return;
            var same = act.Count == puIds.Count;
            if (same) foreach (var id in act.Keys) if (!puIds.Contains(id)) { same = false; break; }
            if (!same)
            {
                puIds.Clear();
                puIds.AddRange(act.Keys);
                pus.Clear();
                puEls.Clear();
                foreach (var id in act.Keys)
                {
                    if (!GameData.Powerups.TryGetValue(id, out var d)) continue;
                    var col = U.Hex(d.Color);
                    var el = new PowerupEl { Ring = U.El("pu-ring"), Time = U.Label("", "pu-t") };
                    el.Ring.style.backgroundColor = col;
                    el.Root = U.El("pu", U.Icon(d.Icon, col), el.Ring, el.Time);
                    IgnorePicking(el.Root);
                    pus.Add(el.Root);
                    puEls[id] = el;
                }
            }
            foreach (var kv in act)
            {
                if (!puEls.TryGetValue(kv.Key, out var el)) continue;
                var f = kv.Value.Duration > 0 ? Mathf.Clamp01(kv.Value.Remaining / kv.Value.Duration) : 0;
                el.Ring.style.width = Length.Percent(f * 100);
                var secs = Mathf.CeilToInt(kv.Value.Remaining);
                if (secs != el.Shown) { el.Shown = secs; el.Time.text = secs + "s"; }
            }
        }

        void UpdateTracker(float dt)
        {
            var qs = G.Quests;
            var q = qs?.Tracked();
            if (trackerFlash > 0 && trackerHead != null)
            {
                trackerFlash = Mathf.Max(0, trackerFlash - dt);
                trackerHead.style.backgroundColor = new Color(95 / 255f, 212 / 255f, 240 / 255f, 0.25f * trackerFlash / 1.2f);
            }
            if (q == null)
            {
                if (trackerKey != "") { tracker.Clear(); trackerKey = ""; trackerHead = null; trackerHash = 0; }
                return;
            }
            qs.CurrentObjectives(q.Id, objBuf);
            var objs = objBuf;
            // Cheap change check first (no strings): quest, objectives, progress and character.
            var hash = q.Id.GetHashCode() * 31 + (character?.GetHashCode() ?? 0);
            foreach (var o in objs) hash = (hash * 31 + o.Def.Id.GetHashCode()) * 31 + o.Progress;
            if (hash == trackerHash && trackerKey != "") return;
            trackerHash = hash;
            var sb = new StringBuilder(q.Id).Append('|');
            foreach (var o in objs) sb.Append(o.Def.Id).Append(':').Append(o.Progress).Append(',');
            sb.Append('|').Append(character);
            var key = sb.ToString();
            if (key == trackerKey) return;
            var changed = trackerKey.Split('|')[0] == q.Id;
            trackerKey = key;
            tracker.Clear();
            trackerHead = U.El("tracker-q",
                U.Label(U.Up(U.T(q.IsMain ? "hud.mission" : "hud.side")), q.IsMain ? "tag" : "tag side"),
                U.Label(U.Up(q.Title), "tracker-title"));
            tracker.Add(trackerHead);
            foreach (var o in objs)
            {
                var txt = qs.ObjectiveText(o.Def) + (o.Required > 1 ? $" ({o.Progress}/{o.Required})" : "");
                var row = U.El("tracker-obj" + (o.Done ? " done" : ""), U.El("dot"), U.Label(o.Done ? $"<s>{txt}</s>" : txt, "tracker-obj-t"));
                tracker.Add(row);
            }
            IgnorePicking(tracker);
            trackerFlash = changed ? 1.2f : 0;
            if (!changed) trackerHead.style.backgroundColor = new StyleColor(StyleKeyword.Null);
        }

        void UpdatePrompt(GameManager gm, IHeroStatus p)
        {
            var text = gm.InteractionPrompt;
            var alive = (p as IDamageable)?.Alive ?? true;
            var on = !string.IsNullOrEmpty(text) && !gm.InDialogue && !gm.InCinematic && alive && !ui.PlayerDead;
            U.Show(prompt, on);
            if (on && !ReferenceEquals(text, promptRaw) && text != promptRaw) { promptRaw = text; promptText.text = U.Up(text); }
        }

        Vector2 PanelSize()
        {
            var r = ui.Root.layout;
            return new Vector2(float.IsNaN(r.width) ? 1920 : r.width, float.IsNaN(r.height) ? 1080 : r.height);
        }

        public static Vector3? PlayerPos(IHeroStatus p)
        {
            if (p is IDamageable d) return d.Position;
            if (p is Component c && c != null) return c.transform.position;
            return null;
        }

        void UpdateMarker(GameManager gm, IHeroStatus p, Camera cam)
        {
            var target = gm.ObjectiveWorldPosition;
            if (!target.HasValue || cam == null || gm.InCinematic || gm.InDialogue)
            {
                U.Show(marker, false);
                return;
            }
            var size = PanelSize();
            var vp = cam.WorldToViewportPoint(target.Value);
            var behind = vp.z < 0;
            var x = vp.x * size.x;
            var y = (1 - vp.y) * size.y;
            const float margin = 50;
            // Keep clear of the vitals, abilities and subtitles along the bottom edge.
            var maxY = size.y - Mathf.Max(margin, size.y * 0.22f);
            var edge = false;
            if (behind)
            {
                x = size.x - x;
                y = maxY;
                edge = true;
            }
            if (x < margin || x > size.x - margin || y < margin || y > maxY) edge = true;
            x = Mathf.Clamp(x, margin, size.x - margin);
            y = Mathf.Clamp(y, margin + 20, maxY);
            marker.style.left = x;
            marker.style.top = y;
            marker.EnableInClassList("edge", edge);
            var pp = PlayerPos(p);
            var d = pp.HasValue ? Vector3.Distance(pp.Value, target.Value) : 0;
            var dm = Mathf.RoundToInt(d);
            if (dm != markerShown) { markerShown = dm; markerD.text = $"{dm} m"; }
            U.Show(marker, d >= 2.5f);
        }

        void UpdateMinimap(GameManager gm, IHeroStatus p, Camera cam)
        {
            var map = gm.CurrentZoneMap;
            var zn = gm.CurrentZoneMeta?.Name ?? "";
            if (!ReferenceEquals(zn, zoneShown)) { zoneShown = zn; miniZone.text = U.Up(zn); }
            var pp = PlayerPos(p) ?? Vector3.zero;
            mini.Map = map;
            mini.Center = pp;
            mini.HeadingDeg = cam != null ? cam.transform.eulerAngles.y : 0;
            mini.Player = pp;
            mini.PlayerYawDeg = p is Component pc && pc != null ? pc.transform.eulerAngles.y : 0;
            mini.Companion = CompanionPos(gm);
            mini.Objective = gm.ObjectiveWorldPosition;
            mini.Npcs.Clear();
            var npcs = map?.Npcs?.Invoke();
            if (npcs != null) mini.Npcs.AddRange(npcs);
            mini.Enemies.Clear();
            var enemies = G.World?.Enemies;
            if (enemies != null)
                for (var ei = 0; ei < enemies.Count; ei++)
                {
                    var e = enemies[ei];
                    if (e == null || !e.Alive) continue;
                    var aggro = (e as IEnemyHealth)?.Aggro ?? false;
                    if (aggro || (e.Position - pp).sqrMagnitude < 25 * 25) mini.Enemies.Add(e.Position);
                }
            mini.Echo.Clear();
            if (G.World != null && G.World.EchoActive && G.Progression != null && G.Progression.HasSkill("echo_detect"))
            {
                var hidden = map?.HiddenPickups?.Invoke();
                if (hidden != null) mini.Echo.AddRange(hidden);
            }
            mini.Refresh();
        }

        public static Vector3? CompanionPos(GameManager gm)
        {
            var c = gm.CompanionStatus;
            if (c == null) return null;
            if (c is Component comp && (comp == null || !comp.gameObject.activeInHierarchy)) return null;
            if (c is IDamageable d) return d.Position;
            if (c is Component cc) return cc.transform.position;
            return null;
        }

        void UpdateEnemyBars(GameManager gm, IHeroStatus p, Camera cam)
        {
            var i = 0;
            var pp = PlayerPos(p);
            var bossD = gm.Boss;
            var enemies = G.World?.Enemies;
            if (cam != null && pp.HasValue && enemies != null)
            {
                var size = PanelSize();
                var now = Time.unscaledTime;
                for (var ei = 0; ei < enemies.Count; ei++)
                {
                    var e = enemies[ei];
                    if (i >= ebars.Count) break;
                    if (e == null || !e.Alive || ReferenceEquals(e, bossD)) continue;
                    if (e is not IEnemyHealth eh || eh.IsBoss) continue;
                    var d = Vector3.Distance(e.Position, pp.Value);
                    var since = lastHit.TryGetValue(eh.Id, out var t) ? now - t : 999;
                    if (d > 28 || (!eh.Aggro && since > 4)) continue;
                    var vp = cam.WorldToViewportPoint(e.Position + Vector3.up * (eh.BarHeight + 0.35f));
                    if (vp.z < 0 || vp.x < 0 || vp.x > 1 || vp.y < 0 || vp.y > 1) continue;
                    var b = ebars[i++];
                    U.Show(b.Root, true);
                    b.Root.style.left = vp.x * size.x;
                    b.Root.style.top = (1 - vp.y) * size.y;
                    var raw = eh.Elite ? eh.DisplayName : "";
                    if (!ReferenceEquals(raw, b.RawName)) { b.RawName = raw; b.Name.text = U.Up(raw); }
                    b.Fill.style.width = Length.Percent(Mathf.Clamp01(eh.Health01) * 100);
                    b.Poise.style.width = Length.Percent(Mathf.Clamp01(eh.Poise01) * 100);
                    b.Root.EnableInClassList("stag", eh.Staggered);
                }
            }
            for (; i < ebars.Count; i++) U.Show(ebars[i].Root, false);

            if (bossD != null && bossD.Alive)
            {
                var bh = bossD as IEnemyHealth;
                U.Show(boss, true);
                var bn = bh?.DisplayName ?? "Aether Guardian";
                if (!ReferenceEquals(bn, bossRaw)) { bossRaw = bn; bossName.text = U.Up(bn); }
                bossFill.style.width = Length.Percent(Mathf.Clamp01(bh?.Health01 ?? 1) * 100);
                if (bossPhaseNum != bossPhaseShown) { bossPhaseShown = bossPhaseNum; bossPhase.text = bossPhaseNum > 0 ? $"PHASE {bossPhaseNum}" : ""; }
            }
            else
            {
                U.Show(boss, false);
                if (bossD == null) bossPhaseNum = 0;
            }
            if (lastHit.Count > 64)
            {
                var now = Time.unscaledTime;
                foreach (var k in lastHit.Where(kv => now - kv.Value > 10).Select(kv => kv.Key).ToList()) lastHit.Remove(k);
            }
        }
    }
}
