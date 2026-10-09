using System;
using System.Linq;
using System.Threading.Tasks;
using UnityEngine;

namespace EOA
{
    // Public operations used by the UI and tools. Zone/actor specifics live in GameManager.Runtime.cs.
    public sealed partial class GameManager
    {
        /// <summary>Character selected on the character-select screen (also the menu stage focus).</summary>
        public string SelectedCharacter { get; set; } = Characters.Kael;

        /// <summary>Appearance per hero for menus/new games, persisted between sessions.</summary>
        // Created lazily: AppearanceStore reads persistentDataPath, which Unity forbids in field initializers.
        AppearanceStore appearances;
        public AppearanceStore Appearances => appearances ??= new AppearanceStore();

        /// <summary>Active hero status for the HUD (null outside gameplay).</summary>
        public IHeroStatus PlayerStatus => Player;
        public IHeroStatus CompanionStatus => Companion;

        public ZoneMeta CurrentZoneMeta => GameData.Zones.TryGetValue(CurrentZone, out var z) ? z : null;

        public Appearance AppearanceFor(string character)
        {
            if (State != null && Mode == GameMode.Play && State.D.Appearance.TryGetValue(character, out var a) && a != null)
                return a.Sanitized(Appearance.Default(character));
            return Appearances.Get(character);
        }

        /// <summary>Change a hero's look (designer). Applies to menus, the current game and future new games.</summary>
        public void SetAppearance(string character, Appearance a)
        {
            a = a.Sanitized(Appearance.Default(character));
            Appearances.Set(character, a);
            if (State != null && Mode == GameMode.Play) State.D.Appearance[character] = a.Clone();
            RefreshAppearance(character);
        }

        public bool CanSaveNow(out string reason)
        {
            reason = null;
            if (Mode != GameMode.Play) { reason = "Not in game"; return false; }
            if (InCombat) { reason = "Can't save during combat"; return false; }
            if (InCinematic || InDialogue) { reason = "Can't save right now"; return false; }
            if (Driving.Active || Driving.Busy) { reason = GameData.T("drive.noSave"); return false; }
            if (G.Saves.Writing) { reason = "Saving..."; return false; }
            return true;
        }

        public bool ManualSave(int slot)
        {
            if (!CanSaveNow(out var why)) { G.Presentation?.Toast(why, ToastKind.Warn); return false; }
            G.Saves.ActiveSlot = slot;
            CaptureState();
            return G.Saves.Write(slot, SaveKind.Manual, State.D, G.Settings.Data, Thumbnail());
        }

        public void Autosave(SaveKind kind = SaveKind.Auto)
        {
            if (Mode != GameMode.Play || State == null) return;
            _ = AutosaveAsync(kind);
        }

        /// <summary>
        /// Autosave without a frame stall: zone-entry saves wait a moment (the first frames after a loading screen stay
        /// free), the thumbnail comes back through an async GPU readback and the file work runs on a worker thread.
        /// </summary>
        async Awaitable AutosaveAsync(SaveKind kind)
        {
            try
            {
                if (kind == SaveKind.Auto)
                {
                    var until = Time.realtimeSinceStartup + 0.75f;
                    while (Time.realtimeSinceStartup < until) await Awaitable.NextFrameAsync();
                    if (Mode != GameMode.Play || State == null) return;
                }
                CaptureState();
                var thumb = await ThumbnailCapture.CaptureAsync();
                if (State == null) return;
                await G.Saves.WriteAsync(G.Saves.ActiveSlot, kind, State.D, G.Settings.Data, thumb);
            }
            catch (Exception e) { Debug.LogWarning("[save] autosave failed: " + e.Message); }
        }

        /// <summary>Use a powerup item from the inventory (quick slots / inventory screen).</summary>
        public bool UsePowerupItem(string itemId)
        {
            if (Mode != GameMode.Play || Player == null || !Player.Alive) return false;
            if (!GameData.Items.TryGetValue(itemId, out var def) || def.EffectType != "powerup") return false;
            var pu = def.EffectStr("powerup");
            if (!Inventory.Has(itemId)) { G.Presentation?.Toast($"No {def.Name} left", ToastKind.Warn); return false; }
            Inventory.Remove(itemId);
            if (Powerups.Activate(pu)) Player.RestoreShield();
            if (GameData.Powerups.TryGetValue(pu, out var pdef)) G.Audio?.Play(pdef.Sfx);
            G.Presentation?.Toast($"{def.Name} activated", ToastKind.Item);
            return true;
        }

        public void TrackQuest(string id) => Quests.Track(id);

        /// <summary>Death screen: retry from the last checkpoint.</summary>
        public Task RetryFromCheckpoint() => RespawnAtCheckpoint();

        /// <summary>Death screen / pause: load the most recent save of the active slot.</summary>
        public async Task LoadLastSave()
        {
            var env = G.Saves.Load(G.Saves.ActiveSlot) ?? G.Saves.Latest();
            if (env != null) await LoadFromEnvelope(env);
            else await RespawnAtCheckpoint();
        }

        /// <summary>Main menu "Continue".</summary>
        public async Task<bool> ContinueGame()
        {
            var env = G.Saves.Latest();
            if (env == null) return false;
            await LoadFromEnvelope(env);
            return true;
        }

        public bool HasAnySave() => G.Saves.AllInfo().Any(i => i.Envelope != null || i.Backup != null);

        string Thumbnail()
        {
            try { return ThumbnailCapture.LastJpegBase64; }
            catch (Exception) { return ""; }
        }
    }
}
