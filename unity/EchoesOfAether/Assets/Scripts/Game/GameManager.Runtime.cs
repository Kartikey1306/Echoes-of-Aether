using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.UIElements;

namespace EOA
{
    // Runtime half of the GameManager: boot wiring, modes, zone loading, heroes, actions, dialogue, saving, music.
    public sealed partial class GameManager
    {
        public CameraRig Cam { get; private set; }
        public UIManager UI { get; private set; }
        public ZoneRuntime World { get; private set; }
        public Cinematics Cinematics { get; private set; }
        public MenuStage Stage { get; private set; }
        public IMenuStage MenuStage => Stage;
        public PostFx Post { get; private set; }

        readonly Dictionary<string, Hero> heroes = new();
        Transform actorsRoot;
        float hitstopUntil, combatT, swapCd, fpsAcc;
        int fpsFrames;
        bool dying;
        string lastMood;

        public Hero Player => State != null && heroes.TryGetValue(State.D.Character, out var h) ? h : null;
        public Hero Companion
        {
            get
            {
                if (State == null || !State.Flag("swap_unlocked")) return null;
                return heroes.TryGetValue(Characters.Partner(State.D.Character), out var h) ? h : null;
            }
        }
        public Hero HeroOf(string character) => heroes.TryGetValue(character, out var h) ? h : null;
        public IDamageable PlayerTarget => Player != null && Player.Alive && Mode == GameMode.Play ? Player : null;
        public IDamageable CompanionTarget => Companion != null && Companion.isActiveAndEnabled && Companion.Alive ? Companion : null;
        public float KillY => World?.KillY ?? -50;
        public bool PlayerControllable => Mode == GameMode.Play && !Paused && !InDialogue && !InCinematic && !dying && !(World?.Loading ?? false);
        public bool Aiming => Player != null && Player.IsAiming;
        public ZoneMapData CurrentZoneMap => World?.Map;
        public IDamageable Boss
        {
            get
            {
                var all = Enemy.All;
                for (var i = 0; i < all.Count; i++) if (all[i] != null && all[i].Alive && all[i].IsBoss) return all[i];
                return null;
            }
        }
        public string InteractionPrompt =>
            Driving.Active ? (PlayerControllable ? Driving.Prompt : null) :
            PlayerControllable && World?.Candidate != null ? World.CandidateLocked ?? World.CandidatePrompt : null;

        partial void InitRuntime()
        {
            actorsRoot = new GameObject("Actors").transform;
            actorsRoot.SetParent(transform, false);
            CombatSystem.Create(transform);
            var vfx = VfxManager.Create(transform);
            G.Vfx = vfx;
            var audio = AudioManager.Create(transform);
            VoiceOver.Create(transform);
            G.Audio = audio;
            audio.SetVolumes(G.Settings.Data.Audio);
            Cam = CameraRig.Create(transform);
            Post = PostFx.Create(transform);
            World = new ZoneRuntime();
            G.World = World;
            Cinematics = new Cinematics(this);
            Stage = EOA.MenuStage.Create(transform);
            var panel = Resources.Load<PanelSettings>("UI/EOA_PanelSettings");
            UI = UIManager.Create(transform, panel);
            G.Presentation = UI;
            WireEvents();
            ApplySettings();
        }

        void Start()
        {
            ShaderWarmup.Begin(); // PSO / variant warm-up behind the menu (zone loads wait for it before revealing)
            CodeWarmup.Begin();   // JIT + UI font tables, time-sliced while the menu is up
            ShowMenu();
        }

        void WireEvents()
        {
            Bus.On<HitstopRequested>(e => hitstopUntil = Mathf.Max(hitstopUntil, Time.unscaledTime + e.Seconds));
            Bus.On<Lightning>(e => G.Audio?.Thunder(e.Intensity));
            Bus.On<QuestCompleted>(e => { G.Audio?.Play("quest_complete"); UI?.QuestBanner(e.Id); });
            Bus.On<QuestStarted>(_ => G.Audio?.Play("quest_accept"));
            Bus.On<AbilityUnlocked>(_ => G.Audio?.Play("quest_complete"));
            Bus.On<SaveWritten>(e => UI?.SaveIndicator(e.Kind));
            Bus.On<SaveFailed>(e => UI?.Toast("Save failed: " + e.Reason, ToastKind.Warn));
            Bus.On<EnemyKilled>(_ => { if (State != null) State.D.Stats.Kills++; });
            Bus.On<SettingsChanged>(_ => ApplySettings());
            Bus.On<ItemAdded>(e =>
            {
                if (GameData.Items.TryGetValue(e.Id, out var d) && d.Category == ItemCategory.Upgrades) UI?.Toast("Upgrade: " + d.Name, ToastKind.Quest);
            });
            Bus.On<Toast>(e => UI?.Toast(e.Text, e.Kind));
        }

        public void ApplySettings()
        {
            var s = G.Settings.Data;
            G.Audio?.SetVolumes(s.Audio);
            if (Cam != null) Cam.ShakeScale = G.Settings.ShakeScale;
            if (World != null) World.MaxTokens = s.Gameplay.Difficulty == "story" ? 1 : s.Gameplay.Difficulty == "hard" ? 3 : 2;
            GraphicsConfig.Apply(s.Graphics, Cam != null ? Cam.Cam : null);
            Post?.ApplySettings(s);
            UI?.ApplySettings();
        }

        // ------------------------------------------------------------------ menu

        public void ShowMenu()
        {
            Mode = GameMode.Menu;
            SetPaused(false);
            Time.timeScale = 1;
            G.Input.EnableGameplay(false);
            GameInput.LockCursor(false);
            Cinematics.Stop();
            DisposeHeroes();
            World.Unload();
            Stage.Show(true);
            Stage.EnterMenu();
            Cam.Follow = null;
            UI.ShowMainMenu();
            G.Audio?.SetMusic("menu");
            G.Audio?.SetAmbience("rain_city");
        }

        public void ShowCharSelect()
        {
            Mode = GameMode.CharSelect;
            Stage.Focus(SelectedCharacter);
            UI.ShowCharacterSelect();
        }

        public async Task QuitToMenu()
        {
            await UI.Fade(true, 0.3f);
            ShowMenu();
            await UI.Fade(false, 0.4f);
        }

        // ------------------------------------------------------------------ new game / load

        public async Task NewGame(string character, int slot)
        {
            State = new GameState(GameState.NewGame(character));
            foreach (var c in new[] { Characters.Kael, Characters.Lyra }) State.D.Appearance[c] = Appearances.Get(c);
            G.Saves.ActiveSlot = slot;
            Powerups.Clear();
            DisposeHeroes();
            SelectedCharacter = character;
            await LoadZone("plaza", "start", intro: true);
        }

        public async Task LoadFromEnvelope(SaveEnvelope env)
        {
            var copy = Newtonsoft.Json.JsonConvert.DeserializeObject<GameStateData>(Newtonsoft.Json.JsonConvert.SerializeObject(env.State, GameData.Json), GameData.Json);
            State = new GameState(copy);
            G.Saves.ActiveSlot = env.Slot;
            Powerups.Clear();
            DisposeHeroes();
            G.Audio?.Play("load");
            var entry = State.D.Position != null ? "__saved" : State.D.Entry;
            await LoadZone(State.D.Zone, entry);
        }

        public async Task RespawnAtCheckpoint()
        {
            State.D.Stats.Deaths++;
            var z = State.D.Checkpoint?.Zone ?? State.D.Zone;
            foreach (var h in heroes.Values) h.Restore();
            Bus.Emit(new PlayerRespawned { Zone = z });
            await LoadZone(z, "__checkpoint", respawn: true);
        }

        // ------------------------------------------------------------------ zones

        public async Task LoadZone(string zoneId, string entry, bool intro = false, bool respawn = false, bool cinematic = false)
        {
            Mode = GameMode.Loading;
            SetPaused(false);
            InDialogue = false;
            dying = false;
            G.Input.EnableGameplay(false);
            GameInput.LockCursor(false);
            if (!cinematic) Cinematics.Stop();
            Dialogue.Cancel();
            Stage.Show(false);
            GameData.Zones.TryGetValue(zoneId, out var meta);
            UI.HideAllScreens();
            if (!cinematic && meta != null) UI.ShowLoading(meta);
            G.Audio?.SetMusic("silence");
            var t0 = Time.realtimeSinceStartup;
            try
            {
                foreach (var h in heroes.Values) h.gameObject.SetActive(false);
                await World.Load(zoneId, (f, label) => UI.SetLoadingProgress(f, label));
                LoadTrace.Mark("Placing characters");
                UI.SetLoadingProgress(0.92f, "Placing characters");
                PlaceHeroes(entry);
                State.D.Zone = zoneId;
                if (entry != "__saved") State.D.Entry = entry;
                CurrentEntry = entry == "__saved" ? State.D.Entry : entry;
                var p = Player;
                State.D.Checkpoint = new Checkpoint { Zone = zoneId, Pos = new[] { p.Position.x, p.Position.y, p.Position.z }, Yaw = p.YawDeg };
                RestoreStageWorldActions();
                if (!ShaderWarmup.Done)
                {
                    LoadTrace.Mark("Shader warm-up wait");
                    UI.SetLoadingProgress(0.96f, "Preparing shaders");
                    var until = Time.realtimeSinceStartup + 20f;
                    while (!ShaderWarmup.Done && Time.realtimeSinceStartup < until) { ShaderWarmup.Tick(24); await Awaitable.NextFrameAsync(); }
                }
                LoadTrace.Mark("Ready (last loading frame)");
                UI.SetLoadingProgress(1, "Ready");
                await Awaitable.NextFrameAsync();
                LoadTrace.Finish();
                Debug.Log($"[game] zone {zoneId} loaded in {(Time.realtimeSinceStartup - t0) * 1000:0} ms");
            }
            catch (Exception e)
            {
                Debug.LogError($"[game] zone load failed: {e}");
                UI.LoadingError(e.Message);
                return;
            }
            UI.HideLoading();
            Mode = GameMode.Play;
            G.Input.EnableGameplay(true);
            G.Audio?.SetAmbience(World.Def.Ambience ?? meta?.Ambience ?? "none");
            UpdateMusic(true);
            Cam.Indoor = World.Def.Indoor;
            Cam.Follow = Player.transform;
            Cam.SnapBehind(Player.YawDeg * Mathf.Deg2Rad);
            Bus.Emit(new ZoneEntered { Zone = zoneId, Entry = entry });
            Quests.Refresh();
            World.Script?.OnEnter();
            if (cinematic) { G.Input.EnableGameplay(false); return; }
            if (intro)
            {
                await Cinematics.Play("cin_intro");
                if (!State.D.Quests.ContainsKey("m1_awakening")) _ = Quests.Start("m1_awakening");
            }
            else if (!respawn && entry != "__saved") Autosave();
            if (Mode == GameMode.Play && !Paused) GameInput.LockCursor(true);
        }

        public async Task ChangeZone(string target, string entry)
        {
            if (Mode != GameMode.Play || World.Loading) return;
            Bus.Emit(new ZoneLeaving { Zone = World.ZoneId });
            G.Audio?.Play("cinematic_whoosh");
            await UI.Fade(true, 0.35f);
            await LoadZone(target, entry);
            await UI.Fade(false, 0.4f);
        }

        void PlaceHeroes(string entry)
        {
            var d = State.D;
            Vector3 pos; float yaw;
            if (entry == "__saved" && d.Position != null) { pos = new Vector3(d.Position[0], d.Position[1], d.Position[2]); yaw = d.Yaw; }
            else if (entry == "__checkpoint" && d.Checkpoint != null && d.Checkpoint.Zone == World.ZoneId) { pos = new Vector3(d.Checkpoint.Pos[0], d.Checkpoint.Pos[1], d.Checkpoint.Pos[2]); yaw = d.Checkpoint.Yaw; }
            else { var sp = World.Def.Spawn(entry); pos = sp.Position; yaw = sp.YawDeg; }
            var g = World.GroundAt(pos + Vector3.up * 1.5f, 6);
            if (g.HasValue) pos.y = g.Value + 0.02f;
            foreach (var c in new[] { Characters.Kael, Characters.Lyra })
                if (!heroes.ContainsKey(c)) heroes[c] = Hero.Spawn(c, pos, yaw, actorsRoot);
            var active = Player;
            active.gameObject.SetActive(true);
            active.SetRole(true);
            active.FollowLeader = null;
            active.Teleport(pos, yaw);
            active.Restore();
            var other = heroes[Characters.Partner(d.Character)];
            other.SetRole(false);
            other.FollowLeader = active;
            Physics.IgnoreCollision(active.GetComponent<CharacterController>(), other.GetComponent<CharacterController>());
            if (State.Flag("swap_unlocked"))
            {
                var r = yaw * Mathf.Deg2Rad;
                var back = pos + new Vector3(-Mathf.Sin(r) * 2 + Mathf.Cos(r) * 1.2f, 0, -Mathf.Cos(r) * 2 - Mathf.Sin(r) * 1.2f);
                var gb = World.GroundAt(back + Vector3.up * 1.5f, 4);
                other.gameObject.SetActive(true);
                other.Teleport(gb.HasValue && Mathf.Abs(gb.Value - pos.y) < 1 ? new Vector3(back.x, gb.Value + 0.02f, back.z) : pos, yaw);
                other.Restore();
                other.SetScripted(false);
            }
            else if (World.ZoneId == "plaza" && World.Def.Marker("partner_wait").HasValue)
            {
                // Before the meeting, the partner waits at the survivors' camp.
                other.gameObject.SetActive(true);
                other.Teleport(World.Def.Marker("partner_wait").Value, 200);
                other.SetScripted(true);
                other.PlayClip("npc_crossed", true);
            }
            else other.gameObject.SetActive(false);
        }

        /// <summary>Re-run idempotent world actions (encounters, pickups) for the current stage of every active quest.</summary>
        void RestoreStageWorldActions()
        {
            foreach (var q in Quests.Active())
            {
                var st = State.D.Quests[q.Id];
                if (st.Stage >= q.Stages.Length) continue;
                var world = q.Stages[st.Stage].OnStart?.Where(a => a.Do == "encounter" || a.Do == "spawnPickup").ToList();
                if (world != null && world.Count > 0) _ = RunActions(world);
            }
        }

        void DisposeHeroes()
        {
            foreach (var h in heroes.Values) if (h != null) Destroy(h.gameObject);
            heroes.Clear();
        }

        void RefreshAppearance(string character)
        {
            HeroOf(character)?.RefreshAppearance();
            Stage?.SetAppearance(character, AppearanceFor(character));
            UI?.Hud?.CharacterChanged();
        }

        // ------------------------------------------------------------------ actions

        public async Task RunActions(IReadOnlyList<ActionDef> actions, string quest = null)
        {
            if (actions == null) return;
            foreach (var a in actions)
            {
                try { await RunAction(a); }
                catch (Exception e) { Debug.LogError($"[actions] {a.Do} failed: {e}"); }
            }
        }

        async Task RunAction(ActionDef a)
        {
            switch (a.Do)
            {
                case "dialogue":
                {
                    var id = a.Str("id");
                    var interactive = GameData.Dialogues.TryGetValue(id, out var def) && def.Nodes.Any(n => n.Choices != null && n.Choices.Length > 0);
                    await PlayDialogue(id, interactive ? "interactive" : "radio");
                    break;
                }
                case "cinematic":
                    await Cinematics.Play(a.Str("id"));
                    break;
                case "encounter":
                    State.SetFlag("enc_" + a.Str("id"));
                    World.SpawnEncounter(a.Str("id"));
                    break;
                case "despawn":
                    World.DespawnEncounter(a.Str("id"));
                    State.MarkDefeated(a.Str("id"));
                    break;
                case "spawnPickup":
                {
                    var id = a.Str("id");
                    if (State.IsCollected(id) || World.HasPickup(id)) break;
                    var at = World.Def?.Marker(a.Str("at")) ?? (Player != null ? Player.Position + Player.transform.forward * 2 : (Vector3?)null);
                    if (!at.HasValue) break;
                    var pu = a.Str("powerup");
                    World.AddPickup(id, pu != null ? PickupKind.Powerup : PickupKind.Quest, at.Value + Vector3.up, a.Str("item"), pu, auto: pu != null);
                    break;
                }
                case "hint":
                    UI.Hint(a.Str("id"));
                    break;
                case "give":
                {
                    var n = Inventory.Add(a.Str("item"), a.Int("qty", 1));
                    if (n > 0 && GameData.Items.TryGetValue(a.Str("item"), out var d)) UI.Toast($"+{n} {d.Name}", ToastKind.Item);
                    break;
                }
                case "take":
                    Inventory.Remove(a.Str("item"), a.Int("qty", 1));
                    break;
                case "setFlag":
                    State.SetFlag(a.Str("flag"), a.Has("value") ? (object)a.Raw["value"].ToObject<object>() : true);
                    World.Script?.OnFlag(a.Str("flag"));
                    break;
                case "startQuest":
                    _ = Quests.Start(a.Str("id"));
                    break;
                case "unlock":
                    State.Unlock(a.Str("ability"));
                    UI.Toast($"Ability unlocked: {(GameData.Abilities.TryGetValue(a.Str("ability"), out var ab) ? ab.Name : a.Str("ability"))}", ToastKind.Quest);
                    break;
                case "autosave":
                    Autosave(SaveKind.Checkpoint);
                    break;
                case "credits":
                    await RollCredits();
                    break;
                default:
                    Debug.LogWarning($"[actions] unknown action {a.Do}");
                    break;
            }
        }

        // ------------------------------------------------------------------ dialogue

        Npc talkingNpc;

        /// <summary>mode: interactive (blocks gameplay, choices), radio (subtitles while playing), cinematic.</summary>
        public async Task PlayDialogue(string id, string mode)
        {
            var interactive = mode == "interactive";
            if (interactive)
            {
                InDialogue = true;
                G.Input.EnableGameplay(false);
                Player?.CancelActions();
                GameInput.LockCursor(false);
            }
            G.Audio?.Duck(0.55f, 0.25f);
            var unsub = Bus.On<DialogueLineShown>(OnLineShown);
            try { await Dialogue.Play(id, interactive ? LineMode.Interactive : LineMode.Auto); }
            finally
            {
                unsub();
                SetSpeaker(null);
                G.Audio?.Duck(0, 0.25f);
                if (interactive)
                {
                    InDialogue = false;
                    if (Mode == GameMode.Play && !Paused && !InCinematic)
                    {
                        G.Input.EnableGameplay(true);
                        GameInput.LockCursor(true);
                    }
                }
            }
        }

        void OnLineShown(DialogueLineShown e) => SetSpeaker(e.Speaker);

        /// <summary>Animate the mouth of whoever is speaking (heroes, NPCs, echoes).</summary>
        void SetSpeaker(string speakerId)
        {
            foreach (var h in heroes.Values) if (h?.Model != null) h.Model.Talk = h.Character == speakerId ? 1 : 0;
            foreach (var n in World?.Npcs ?? new List<Npc>()) n?.SetSpeaking(n.Id == speakerId);
            Cinematics?.SetSpeaker(speakerId);
        }

        public void TalkTo(Npc npc)
        {
            if (InDialogue || InCinematic || npc == null) return;
            _ = TalkToAsync(npc);
        }

        async Task TalkToAsync(Npc npc)
        {
            var p = Player;
            if (p == null) return;
            talkingNpc = npc;
            npc.StartTalk(p.Position);
            p.FaceTowards(npc.Position);
            Cinematics.FrameConversation(p, npc);
            try { await PlayDialogue(npc.Place.Dialogue, "interactive"); }
            finally
            {
                npc.EndTalk();
                Cinematics.ReleaseFraming();
                talkingNpc = null;
            }
        }

        /// <summary>Scripted traversal (ladders, hatches): move the player through points with a clip.</summary>
        public async Task Traverse(Vector3[] points, string clip, float duration, float? endYawDeg = null)
        {
            var p = Player;
            if (p == null || points == null || points.Length < 2) return;
            p.SetScripted(true);
            if (!string.IsNullOrEmpty(clip)) p.PlayClip(clip, true);
            var seg = duration / (points.Length - 1);
            for (var i = 1; i < points.Length; i++)
            {
                var t0 = Time.time;
                while (true)
                {
                    var k = Mathf.Min(1, (Time.time - t0) / seg);
                    p.Teleport(Vector3.Lerp(points[i - 1], points[i], k), endYawDeg ?? p.YawDeg);
                    if (k >= 1 || Mode != GameMode.Play) break;
                    await Awaitable.NextFrameAsync();
                }
            }
            if (endYawDeg.HasValue) p.YawDeg = endYawDeg.Value;
            p.SetScripted(false);
            p.CancelActions();
            var c = Companion;
            if (c != null) c.Teleport(p.Position + new Vector3(1, 0, 1), p.YawDeg);
        }

        // ------------------------------------------------------------------ pickups, powerups, abilities

        public void OnPickup(Pickup p)
        {
            if (GameData.Collectibles.TryGetValue(p.Id, out var def))
            {
                foreach (var kv in def.Give) Inventory.Add(kv.Key, kv.Value, true);
                var first = def.Give.Keys.FirstOrDefault();
                var label = def.Kind == "fragment" ? "Aether Fragment" : def.Kind == "recording" ? (first != null && GameData.Items.TryGetValue(first, out var it) ? it.Name : "Recording") : "Hidden cache";
                UI.Toast($"{label} found", def.Kind == "recording" ? ToastKind.Lore : ToastKind.Item);
                G.Audio?.Play(def.Kind == "recording" ? "lore" : "pickup", p.Position);
                Bus.Emit(new CollectibleFound { Id = p.Id, Kind = def.Kind });
                if (def.Kind == "cache") foreach (var kv in def.Give) UI.Toast($"+{kv.Value} {(GameData.Items.TryGetValue(kv.Key, out var d2) ? d2.Name : kv.Key)}", ToastKind.Item);
                if (def.Kind == "recording" && first != null && GameData.Dialogues.ContainsKey(first)) _ = PlayDialogue(first, "radio");
                Player?.PlayClip("pickup");
                return;
            }
            if (p.PowerupId != null) { ActivatePowerup(p.PowerupId); return; }
            if (p.Item != null && GameData.Items.TryGetValue(p.Item, out var item))
            {
                if (item.EffectType == "powerup" && p.Id.StartsWith("drop_")) { ActivatePowerup(item.EffectStr("powerup")); return; }
                Inventory.Add(p.Item);
                UI.Toast($"Picked up {item.Name}", ToastKind.Item);
                G.Audio?.Play("item", p.Position);
                Player?.PlayClip("pickup");
            }
        }

        public void ActivatePowerup(string id)
        {
            if (!GameData.Powerups.TryGetValue(id, out var def)) return;
            var restore = Powerups.Activate(id);
            var p = Player;
            if (restore && p != null) p.RestoreShield();
            if (id == "echo_fragment" && p != null) World.EchoReveal(p.Position, 30, def.Duration);
            G.Audio?.Play(def.Sfx, p != null ? p.Position : (Vector3?)null);
            UI.Toast($"{def.Name}: {def.Description}", ToastKind.Item);
            if (p != null)
            {
                var col = Appearance.ToColor(def.Color);
                VfxManager.Instance?.Shockwave(p.Position, 2.4f, col, 0.45f);
                VfxManager.Instance?.Embers(p.Chest, 24, col, 0.8f, 1.6f);
                p.Model?.HitFlash(0.6f);
            }
        }

        public void DropItem(string itemId, Vector3 position)
        {
            if (!GameData.Items.TryGetValue(itemId, out var def) || World.Root == null) return;
            var isPu = def.EffectType == "powerup";
            World.AddPickup("drop_" + Guid.NewGuid().ToString("N").Substring(0, 6), isPu ? PickupKind.Powerup : PickupKind.Item, position, itemId, isPu ? def.EffectStr("powerup") : null, auto: true, persist: false);
        }

        public void EchoPulse(Vector3 center, float range, float duration) => World.EchoReveal(center, range, duration);

        public void OpenSaveTerminal() => UI.OpenSaveScreen(true);

        public void SetBoss(bool on)
        {
            BossActive = on;
            UpdateMusic();
        }

        public void OnPlayerDied(Hero h)
        {
            if (dying) return;
            dying = true;
            Cam.LockTarget = null;
            Bus.Emit(new PlayerDied { Zone = World.ZoneId });
            G.Audio?.SetMusic("silence");
            GameInput.LockCursor(false);
        }

        public void SwapCharacter()
        {
            if (!State.Flag("swap_unlocked") || swapCd > 0) return;
            var cur = Player; var next = Companion;
            if (cur == null || next == null || !cur.Alive || !next.isActiveAndEnabled) return;
            swapCd = 1.2f;
            cur.CancelActions();
            State.D.Character = next.Character;
            cur.SetRole(false); cur.FollowLeader = next;
            next.SetRole(true); next.FollowLeader = null;
            Cam.Follow = next.transform;
            Cam.SnapBehind(Cam.Heading);
            foreach (var h in new[] { cur, next })
            {
                var col = h.Character == Characters.Kael ? new Color(0.37f, 0.72f, 1f) : new Color(0.64f, 0.49f, 1f);
                VfxManager.Instance?.FlashSprite(h.Chest, 2.2f, col, 0.25f);
                VfxManager.Instance?.Embers(h.Chest, 16, col, 0.8f, 1);
            }
            G.Audio?.Play("step", next.Position);
            Bus.Emit(new CharacterSwapped { Character = next.Character });
            UI?.Hud?.CharacterChanged();
        }

        // ------------------------------------------------------------------ saving & credits

        void CaptureState()
        {
            var p = Player;
            if (p == null || State == null) return;
            var pos = p.Position;
            var yaw = p.YawDeg;
            // Saved while driving (autosave): on foot beside the car.
            if (Driving.Active && Driving.SaveSpot(out var spot, out var spotYaw)) { pos = spot; yaw = spotYaw; }
            State.D.Position = new[] { pos.x, pos.y, pos.z };
            State.D.Yaw = yaw;
        }

        public async Task RollCredits()
        {
            Mode = GameMode.Credits;
            G.Input.EnableGameplay(false);
            GameInput.LockCursor(false);
            G.Audio?.SetMusic("ending");
            CaptureState();
            G.Saves.Write(G.Saves.ActiveSlot, SaveKind.Checkpoint, State.D, G.Settings.Data, Thumbnail());
            await UI.ShowCredits();
            ShowMenu();
        }

        // ------------------------------------------------------------------ objective marker

        /// <summary>Where the HUD objective marker should point: the tracked objective's marker, routed through
        /// the exit towards the objective's zone when it lies elsewhere.</summary>
        public Vector3? ObjectiveWorldPosition
        {
            get
            {
                if (Mode != GameMode.Play || World?.Def == null) return null;
                var q = Quests.Tracked();
                if (q == null) return null;
                foreach (var o in Quests.CurrentObjectives(q.Id, objectiveBuf))
                {
                    if (o.Done) continue;
                    var marker = o.Def.Marker ?? (o.Def.Type == "talk" ? TalkMarker(o.Def.Target) : o.Def.Type == "zone" ? null : o.Def.Target);
                    if (o.Def.Type == "zone" && o.Def.Target != World.ZoneId) return World.ExitTo(o.Def.Target)?.Position;
                    var p = marker != null ? World.ResolveMarker(marker) : null;
                    if (p.HasValue) return p;
                    if (q.Zone != World.ZoneId) return World.ExitTo(q.Zone)?.Position;
                }
                return null;
            }
        }

        readonly List<ObjectiveStatus> objectiveBuf = new();
        readonly Dictionary<string, string> talkMarkers = new();

        /// <summary>"npc_" + id, cached (the objective marker is resolved every frame).</summary>
        string TalkMarker(string npc)
        {
            if (npc == null) return "npc_";
            if (!talkMarkers.TryGetValue(npc, out var m)) talkMarkers[npc] = m = "npc_" + npc;
            return m;
        }

        // ------------------------------------------------------------------ frame

        void Update()
        {
            var dt = Time.unscaledDeltaTime;
            G.Input?.Tick();
            ShaderWarmup.Tick();
            if (!CodeWarmup.Done) CodeWarmup.Tick(Mode == GameMode.Play ? 1.5f : Mode == GameMode.Loading ? 12f : 5f);
            fpsAcc += dt; fpsFrames++;
            if (fpsAcc >= 0.5f) { Fps = fpsFrames / fpsAcc; fpsAcc = 0; fpsFrames = 0; }
            if (Mode != GameMode.Play)
            {
                if (Mode != GameMode.Loading) Stage?.Tick(dt);
                return;
            }
            if (Paused)
            {
                if (DesignerActive) Stage?.Tick(dt);
                return;
            }
            // Hit-stop
            Time.timeScale = Time.unscaledTime < hitstopUntil ? 0.06f : Mathf.MoveTowards(Time.timeScale, 1, dt * 20);
            var gdt = Time.deltaTime;
            State.D.Stats.Playtime += dt;
            swapCd = Mathf.Max(0, swapCd - dt);
            Powerups.Update(gdt);
            var p = Player;
            var canAct = PlayerControllable && p != null && p.Alive;
            // In a car, Driving reads the controls (interact gets out) and nothing is picked up on the way.
            var driving = Driving.Active || Driving.Busy;
            if (canAct && !driving)
            {
                if (G.Input.Pressed("interact") && World.Interact()) G.Audio?.Play("interact");
                if (G.Input.Pressed("swap")) SwapCharacter();
                foreach (var kv in QuickSlots) if (G.Input.Pressed(kv.Key)) UsePowerupItem(kv.Value);
                if (!State.Flag("tut_moved") && Vector3.Distance(p.Position, p.LastSafe) > 4) State.SetFlag("tut_moved");
            }
            World.Tick(gdt, p != null ? p.Position : (Vector3?)null, canAct && !driving, Powerups.Current().Reveal);
            Cinematics.Tick(dt);
            if (p != null)
            {
                var was = InCombat;
                if (World.AggroCount(p.Position) > 0) { InCombat = true; combatT = 4; }
                else { combatT -= dt; if (combatT <= 0) InCombat = false; }
                if (was != InCombat) { Bus.Emit(new CombatState { InCombat = InCombat }); UpdateMusic(); }
                Cam.CombatZoom = InCombat ? 0.6f : 0;
                Post?.Tick(dt, p, World);
            }
        }

        void UpdateMusic(bool force = false)
        {
            if (Mode != GameMode.Play || World?.Def == null) return;
            GameData.Zones.TryGetValue(World.ZoneId, out var meta);
            var mood = World.Def.Music ?? meta?.Music ?? "explore";
            if (BossActive) mood = "boss";
            else if (InCombat) mood = "combat";
            else if (Quests.Tracked()?.Type == "side" && World.ZoneId == "rooftops") mood = "sidequest";
            if (dying) mood = "silence";
            if (force || mood != lastMood) { G.Audio?.SetMusic(mood); lastMood = mood; }
        }

        void OnApplicationFocus(bool focus)
        {
            if (!focus && !Benchmark.Active && Mode == GameMode.Play && !Paused && !InCinematic && !InDialogue && !dying) UI?.OpenPause();
        }
    }

    /// <summary>Raised by the dialogue view when a line appears (speaker id) so faces can animate.</summary>
    public struct DialogueLineShown { public string Speaker; public string Dialogue; public string Node; }
}
