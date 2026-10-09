using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Top-level orchestrator: owns the systems, game modes, zone loading, data-driven actions, saving and
    /// character swapping. Lives in the Boot scene and persists for the whole session.
    /// </summary>
    [DefaultExecutionOrder(-1000)]
    public sealed partial class GameManager : MonoBehaviour, IActionHost
    {
        public static readonly Dictionary<string, string> QuickSlots = new()
        {
            ["quick1"] = "pu_aether_shard", ["quick2"] = "pu_phase_core", ["quick3"] = "pu_overcharge",
            ["quick4"] = "pu_shield_fragment", ["quick5"] = "pu_echo_fragment",
        };

        public GameMode Mode { get; private set; } = GameMode.Boot;
        public GameState State { get; private set; }
        public Inventory Inventory { get; private set; }
        public Progression Progression { get; private set; }
        public QuestSystem Quests { get; private set; }
        public DialogueSystem Dialogue { get; private set; }
        public Powerups Powerups { get; } = new();

        /// <summary>Overlays that pause gameplay (pause menu, panels, save screen, death screen).</summary>
        public bool Paused { get; private set; }
        public bool InDialogue { get; private set; }
        public bool InCinematic { get; set; }
        public bool InCombat { get; private set; }
        public bool BossActive { get; private set; }
        /// <summary>True while the Character Designer is open.</summary>
        public bool DesignerActive { get; set; }
        public string CurrentEntry { get; private set; } = "start";
        public float Fps { get; private set; } = 60;

        /// <summary>UI-facing dialogue presenter (set by the UI module).</summary>
        public IDialogueView DialogueView { get; set; }

        // ------------------------------------------------------------------ IActionHost
        public string CurrentZone => G.World?.ZoneId ?? "";
        public string PartnerName => State == null ? "" : Characters.FirstName(Characters.Partner(State.D.Character));

        void Awake()
        {
            if (G.Manager != null && G.Manager != this) { Destroy(gameObject); return; }
            G.Manager = this;
            DontDestroyOnLoad(gameObject);
            Application.targetFrameRate = -1;
            GameData.EnsureLoaded();
            G.Settings = new Settings();
            G.Saves = new SaveSystem();
            G.Input = new GameInput();
            G.Input.LoadOverrides(G.Settings.Data.Controls.BindingOverrides);
            State = new GameState(GameState.NewGame(Characters.Kael));
            Inventory = new Inventory(() => State);
            Progression = new Progression(() => State, Inventory);
            Dialogue = new DialogueSystem(() => State, () => DialogueView, a => RunActions(a));
            Quests = new QuestSystem(() => State, this);
            InitRuntime();
        }

        void OnDestroy()
        {
            if (G.Manager != this) return;
            Quests?.Dispose();
            G.Input?.Dispose();
            Bus.Clear();
            G.Manager = null;
        }

        /// <summary>Pause/resume gameplay for overlays.</summary>
        public void SetPaused(bool paused)
        {
            Paused = paused;
            Time.timeScale = paused ? 0 : 1;
            GameInput.LockCursor(!paused && Mode == GameMode.Play && !InDialogue);
            G.Audio?.Duck(paused ? 0.5f : 0, 0.2f);
        }

        partial void InitRuntime();
    }
}
