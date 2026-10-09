using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.UI;
using UnityEngine.UIElements;

namespace EOA
{
    /// <summary>
    /// Runtime UI root (UI Toolkit). Owns the screen stack with keyboard/gamepad navigation, the HUD, dialogue
    /// presentation, loading screen, toasts/hints/fades/cinematic bars and the debug overlay. Implements
    /// <see cref="IPresentation"/> and registers itself as <c>G.Presentation</c>; registers its dialogue view as
    /// <c>G.Manager.DialogueView</c>.
    /// </summary>
    [RequireComponent(typeof(UIDocument))]
    public sealed partial class UIManager : MonoBehaviour, IPresentation
    {
        public static UIManager Instance { get; private set; }

        public UIDocument Document { get; private set; }
        public VisualElement Root { get; private set; }
        public Hud Hud { get; private set; }
        public DialogueView Dialogue { get; private set; }
        public LoadingScreen Loading { get; private set; }
        /// <summary>Set false to force the HUD hidden in play mode (e.g. photo mode).</summary>
        public bool HudEnabled { get; set; } = true;
        public bool BarsOn { get; private set; }
        public bool LoadingVisible => Loading != null && Loading.Visible;
        /// <summary>True while a menu screen or a dialogue choice is consuming keyboard/gamepad input.</summary>
        public bool CapturesInput => stack.Count > 0 || (Dialogue != null && Dialogue.ChoicesActive);
        public UIScreen Top => stack.Count > 0 ? stack[stack.Count - 1] : null;
        public bool PlayerDead => playerDead;

        VisualElement hudLayer, dialogueLayer, hintLayer, screenLayer;
        readonly List<UIScreen> stack = new();
        readonly List<Action> unsubs = new();
        PanelSettings runtimeSettings;
        Vector2Int baseReference = new(1920, 1080);
        float baseScale = 1;
        bool built;
        float deathAt = -1;
        bool playerDead;
        bool probeReceived;
        bool settingsApplied;
        float probeT;
        DebugOverlay debug;

        const string RuntimeSuffix = " (runtime)";

        struct UiBusProbe { }

        // ------------------------------------------------------------------ Creation

        /// <summary>
        /// Create the UI under <paramref name="parent"/>. When <paramref name="settings"/> is null the PanelSettings
        /// from Resources/UI/UIRefs is used (created by Tools/EOA/Setup UI).
        /// </summary>
        public static UIManager Create(Transform parent, PanelSettings settings)
        {
            if (Instance != null) return Instance;
            if (settings == null) settings = UIRefs.Load()?.PanelSettings;
            var go = new GameObject("UI");
            go.SetActive(false);
            if (parent != null) go.transform.SetParent(parent, false);
            var doc = go.AddComponent<UIDocument>();
            if (settings != null) doc.panelSettings = RuntimeCopy(settings);
            else Debug.LogError("[ui] No PanelSettings available. Run Tools > EOA > Setup UI (UISetup.Run).");
            go.AddComponent<UIManager>();
            go.SetActive(true);
            var ui = go.GetComponent<UIManager>();
            ui.EnsureBuilt();
            return ui;
        }

        static PanelSettings RuntimeCopy(PanelSettings src)
        {
            if (src == null || src.name.EndsWith(RuntimeSuffix)) return src;
            var copy = Instantiate(src);
            copy.name = src.name + RuntimeSuffix;
            return copy;
        }

        void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Debug.LogWarning("[ui] duplicate UIManager destroyed");
                Destroy(gameObject);
                return;
            }
            Instance = this;
            Document = GetComponent<UIDocument>();
            // Work on a private copy so UI scale changes never modify the PanelSettings asset.
            if (Document.panelSettings != null)
            {
                var copy = RuntimeCopy(Document.panelSettings);
                if (copy != Document.panelSettings) Document.panelSettings = copy;
                runtimeSettings = copy;
                baseReference = copy.referenceResolution;
                baseScale = copy.scale;
            }
        }

        void Start() => EnsureBuilt();

        void OnDestroy()
        {
            if (Instance != this) return;
            foreach (var u in unsubs) u();
            unsubs.Clear();
            Hud?.Dispose();
            if (ReferenceEquals(G.Presentation, this)) G.Presentation = null;
            if (G.Manager != null && ReferenceEquals(G.Manager.DialogueView, Dialogue)) G.Manager.DialogueView = null;
            Instance = null;
        }

        /// <summary>Build the visual tree once the UIDocument has a root element. Safe to call repeatedly.</summary>
        public void EnsureBuilt()
        {
            if (built) return;
            if (Document == null) Document = GetComponent<UIDocument>();
            var root = Document != null ? Document.rootVisualElement : null;
            if (root == null) return;
            built = true;
            GameData.EnsureLoaded();
            Root = root;
            Build();
        }

        void Build()
        {
            Root.AddToClassList("eoa-root");
            Root.pickingMode = PickingMode.Ignore;
            Root.style.position = Position.Absolute;
            Root.style.left = 0;
            Root.style.top = 0;
            Root.style.right = 0;
            Root.style.bottom = 0;
            var ps = Document.panelSettings;
            if (ps == null || ps.themeStyleSheet == null)
            {
                var refs = UIRefs.Load();
                if (refs != null && refs.StyleSheets != null)
                    foreach (var s in refs.StyleSheets)
                        if (s != null) Root.styleSheets.Add(s);
            }

            hudLayer = Layer("layer-hud");
            Hud = new Hud(this);
            hudLayer.Add(Hud.Root);
            dialogueLayer = Layer("layer-dialogue");
            Dialogue = new DialogueView(this);
            dialogueLayer.Add(Dialogue.Root);
            hintLayer = Layer("layer-hint");
            BuildFeedback();               // toasts, letterbox, skip prompt, save indicator
            Loading = new LoadingScreen(this);
            Root.Add(Loading.Root);
            screenLayer = Layer("layer-screens");
            BuildFader();
            debug = new DebugOverlay();
            Root.Add(debug.Root);

            Root.RegisterCallback<FocusInEvent>(OnFocusIn, TrickleDown.TrickleDown);
            EnsureEventSystem();
            Subscribe();
            G.Presentation = this;
            if (G.Manager != null) G.Manager.DialogueView = Dialogue;
            ApplySettings();
        }

        VisualElement Layer(string cls)
        {
            var l = U.El("layer " + cls);
            l.pickingMode = PickingMode.Ignore;
            Root.Add(l);
            return l;
        }

        /// <summary>UI Toolkit receives pointer input through an EventSystem with the Input System UI module.
        /// Keyboard/gamepad navigation is driven by GameInput instead, so the module's move/submit/cancel are cleared.</summary>
        void EnsureEventSystem()
        {
            var es = EventSystem.current != null ? EventSystem.current : FindAnyObjectByType<EventSystem>();
            if (es == null)
            {
                var go = new GameObject("EventSystem");
                go.transform.SetParent(transform, false);
                es = go.AddComponent<EventSystem>();
                es.sendNavigationEvents = false; // no uGUI-driven Tab/move/submit; GameInput drives navigation
                go.AddComponent<InputSystemUIInputModule>();
            }
            var module = es.GetComponent<InputSystemUIInputModule>();
            if (module != null)
            {
                module.move = null;
                module.submit = null;
                module.cancel = null;
            }
        }

        void Subscribe()
        {
            foreach (var u in unsubs) u();
            unsubs.Clear();
            unsubs.Add(Bus.On<UiBusProbe>(_ => probeReceived = true));
            // Toast, SaveWritten, SaveFailed and QuestCompleted are forwarded by GameManager (WireEvents) to
            // Toast / SaveIndicator / QuestBanner, so they are intentionally not subscribed here.
            unsubs.Add(Bus.On<PlayerDied>(_ =>
            {
                playerDead = true;
                deathAt = Time.unscaledTime + 2.4f;
                HideHint();
            }));
            unsubs.Add(Bus.On<PlayerRespawned>(_ => { playerDead = false; deathAt = -1; Pop("death"); }));
            unsubs.Add(Bus.On<ZoneEntered>(_ => { playerDead = false; deathAt = -1; }));
            unsubs.Add(Bus.On<EnemyDamaged>(e => Hud.OnEnemyDamaged(e.Id)));
            unsubs.Add(Bus.On<EnemyKilled>(_ => Hud.KillMarker()));
            unsubs.Add(Bus.On<BossPhase>(b => Hud.OnBossPhase(b.Id, b.Phase)));
            unsubs.Add(Bus.On<CharacterSwapped>(_ => Hud.CharacterChanged()));
            unsubs.Add(Bus.On<SettingsChanged>(_ => ApplySettings()));
        }

        // ------------------------------------------------------------------ Frame

        void Update()
        {
            EnsureBuilt();
            if (!built) return;
            var dt = Mathf.Min(Time.unscaledDeltaTime, 0.1f);

            // Re-register if something cleared the bus (e.g. Bus.Clear on returning to the menu).
            probeT -= dt;
            if (probeT <= 0)
            {
                probeT = 0.5f;
                probeReceived = false;
                Bus.Emit(new UiBusProbe());
                if (!probeReceived) Subscribe();
            }
            if (!settingsApplied && G.Settings != null) ApplySettings();
            if (G.Presentation == null) G.Presentation = this;
            if (G.Manager != null && G.Manager.DialogueView == null) G.Manager.DialogueView = Dialogue;

            if (Debug.isDebugBuild && Keyboard.current != null && Keyboard.current.f1Key.wasPressedThisFrame) debug.Toggle();

            var stackWasEmpty = stack.Count == 0;
            var cancelConsumed = NavigationTick(dt);
            HotkeysTick(stackWasEmpty, cancelConsumed);

            for (var i = stack.Count - 1; i >= 0; i--)
            {
                if (i >= stack.Count) continue;
                var s = stack[i];
                try { s.Tick?.Invoke(dt); }
                catch (Exception e) { Debug.LogException(e); }
            }

            if (deathAt > 0 && Time.unscaledTime >= deathAt)
            {
                deathAt = -1;
                if (playerDead && G.Manager != null && G.Manager.Mode == GameMode.Play) ShowDeath();
            }

            Hud.Tick(dt);
            Dialogue.Tick(dt);
            Loading.Tick(dt);
            FeedbackTick(dt);
            debug.Tick(dt);
        }

        /// <summary>Gameplay hotkeys that open UI (pause, inventory, map, journal, ability matrix).</summary>
        void HotkeysTick(bool stackWasEmpty, bool cancelConsumed)
        {
            var gm = G.Manager;
            var inp = G.Input;
            if (gm == null || inp == null || gm.Mode != GameMode.Play || LoadingVisible) return;
            if (gm.InCinematic || playerDead) return;
            if (stackWasEmpty)
            {
                if (gm.InDialogue || Dialogue.ChoicesActive) return;
                if (inp.Pressed("pause")) OpenPause();
                else if (inp.Pressed("inventory")) OpenPanel("inventory");
                else if (inp.Pressed("map")) OpenPanel("map");
                else if (inp.Pressed("journal")) OpenPanel("journal");
                else if (inp.Pressed("skills")) OpenPanel("skills");
                return;
            }
            if (cancelConsumed) return;
            var top = Top;
            if (top == null) return;
            if (top.Id == "pause" && inp.Pressed("pause")) top.Back?.Invoke();
            else if (top.Id == "panel" && !string.IsNullOrEmpty(top.Tag) && inp.Pressed(top.Tag)) top.Back?.Invoke();
        }

        // ------------------------------------------------------------------ Settings

        public void ApplySettings()
        {
            if (!built) return;
            var s = G.Settings?.Data;
            if (s == null) return;
            settingsApplied = true;
            ApplyUiScale(s.Accessibility.UiScale);
            Dialogue.ApplySettings(s.Accessibility);
        }

        /// <summary>Accessibility UI scale: shrinks the reference resolution so the whole UI scales and re-flows.</summary>
        void ApplyUiScale(float scale)
        {
            var ps = Document.panelSettings;
            if (ps == null || ps != runtimeSettings) return;
            scale = Mathf.Clamp(scale, 0.5f, 2f);
            if (ps.scaleMode == PanelScaleMode.ScaleWithScreenSize)
            {
                var r = new Vector2Int(Mathf.Max(1, Mathf.RoundToInt(baseReference.x / scale)), Mathf.Max(1, Mathf.RoundToInt(baseReference.y / scale)));
                if (ps.referenceResolution != r) ps.referenceResolution = r;
            }
            else ps.scale = baseScale * scale;
        }

        // ------------------------------------------------------------------ Screen stack

        public bool HasScreen(string id) => stack.Exists(s => s.Id == id);

        public void Push(UIScreen s)
        {
            EnsureBuilt();
            screenLayer.Add(s.Root);
            stack.Add(s);
            UpdateVisibility();
            var list = NavList();
            s.FocusIndex = Mathf.Max(0, list.FindIndex(e => e.ClassListContains("autofocus")));
            PaintFocus();
            SyncPause();
        }

        /// <summary>Remove a screen (the top one when id is null).</summary>
        public void Pop(string id = null)
        {
            var idx = id == null ? stack.Count - 1 : stack.FindLastIndex(x => x.Id == id);
            if (idx < 0) return;
            var s = stack[idx];
            stack.RemoveAt(idx);
            if (focused != null && (focused == s.Root || s.Root.Contains(focused))) { focused.RemoveFromClassList("focus"); focused = null; }
            s.Root.RemoveFromHierarchy();
            UpdateVisibility();
            try { s.OnClose?.Invoke(); }
            catch (Exception e) { Debug.LogException(e); }
            PaintFocus();
            SyncPause();
        }

        /// <summary>Show screens from the top down to (and including) the first full-screen page; hide the rest.</summary>
        void UpdateVisibility()
        {
            var visible = true;
            for (var i = stack.Count - 1; i >= 0; i--)
            {
                stack[i].Root.style.display = visible ? DisplayStyle.Flex : DisplayStyle.None;
                if (stack[i].HidesBelow) visible = false;
            }
        }

        public void HideAllScreens()
        {
            while (stack.Count > 0) Pop();
        }

        /// <summary>Close in-game overlays (pause, panels, saves) and resume.</summary>
        public void CloseOverlays()
        {
            for (var i = stack.Count - 1; i >= 0; i--)
                if (i < stack.Count && stack[i].Overlay) Pop(stack[i].Id);
        }

        void SyncPause()
        {
            var gm = G.Manager;
            if (gm == null || gm.Mode != GameMode.Play) return;
            var overlay = stack.Exists(x => x.Overlay);
            if (overlay != gm.Paused) gm.SetPaused(overlay);
        }

        // ------------------------------------------------------------------ Screens (public API)

        public void ShowMainMenu()
        {
            EnsureBuilt();
            HideAllScreens();
            CinematicBars(false);
            ShowSkipPrompt(false);
            FadeInstant(false);
            HideLoading();
            HideHint();
            Dialogue.End();
            playerDead = false;
            deathAt = -1;
            MainMenuScreen.Open(this);
        }

        public void ShowCharacterSelect()
        {
            EnsureBuilt();
            if (!HasScreen("charselect")) CharacterSelectScreen.Open(this);
        }

        public void OpenPause()
        {
            if (HasScreen("pause") || G.Manager == null || G.Manager.Mode != GameMode.Play) return;
            PauseScreen.Open(this);
        }

        public void OpenSettings(bool inGame) => SettingsScreen.Open(this, inGame);

        /// <summary>Save (true) or load (false) slots screen. Save terminals open it with save = true.</summary>
        public void OpenSaveScreen(bool save) => SavesScreen.Open(this, save);

        /// <summary>inventory | map | journal | skills</summary>
        public void OpenPanel(string name)
        {
            if (G.Manager == null || G.Manager.Mode != GameMode.Play) return;
            GamePanels.Open(this, name);
        }

        public void OpenDesigner(string character, Action onClose = null) => DesignerScreen.Open(this, character, onClose);

        public void ShowDeath()
        {
            EnsureBuilt();
            HideHint();
            if (!HasScreen("death")) DeathScreen.Open(this);
            GameInput.LockCursor(false);
        }

        /// <summary>Scrolling credits; completes when finished or skipped.</summary>
        public Task ShowCredits()
        {
            EnsureBuilt();
            return CreditsScreen.Open(this);
        }

        public Task<bool> Confirm(string title, string message, string okLabel = "Confirm", bool danger = false)
        {
            EnsureBuilt();
            return ConfirmDialog.Open(this, title, message, okLabel, danger);
        }

        // ------------------------------------------------------------------ Loading

        public void ShowLoading(ZoneMeta meta)
        {
            EnsureBuilt();
            HideHint();
            Loading.Show(meta);
        }

        public void SetLoadingProgress(float progress01, string stage) { if (built) Loading.Progress(progress01, stage); }
        public void LoadingError(string message) { if (built) Loading.Error(message); }
        public void HideLoading() { if (built) Loading.Hide(); }
    }
}
