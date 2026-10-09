using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.Controls;

namespace EOA
{
    /// <summary>
    /// Unified keyboard/mouse/gamepad input on the Input System. Actions are created in code with the
    /// game's default bindings; players can rebind them (overrides persist in settings).
    /// </summary>
    public sealed class GameInput : IDisposable
    {
        public static readonly string[] ButtonActions =
        {
            "jump", "dash", "light", "heavy", "bolt", "ability", "ultimate", "interact", "swap", "lockon", "crouch",
            "pause", "inventory", "map", "journal", "skills", "quick1", "quick2", "quick3", "quick4", "quick5", "skip", "debug",
            "handbrake", "horn", "vehicleReset",
        };

        /// <summary>
        /// Vehicle controls. They live in the Gameplay map next to the on-foot actions and may share keys with them
        /// (W/S/A/D, Space...): <see cref="Driving"/> only reads them while the player is in a car, the hero only out of
        /// one. Rebinding resolves key conflicts within each context (plus the shared interact / pause / map).
        /// </summary>
        public static readonly string[] DriveActions = { "throttle", "brake", "steerLeft", "steerRight", "handbrake", "horn", "vehicleReset" };

        /// <summary>Actions offered on the Controls settings page.</summary>
        public static readonly string[] Rebindable =
        {
            "move", "jump", "dash", "light", "heavy", "bolt", "ability", "ultimate", "interact", "swap", "lockon", "crouch",
            "inventory", "map", "journal", "skills", "quick1", "quick2", "quick3", "quick4", "quick5",
            "throttle", "brake", "steerLeft", "steerRight", "handbrake", "horn", "vehicleReset",
        };

        public readonly InputActionAsset Asset;
        public readonly InputActionMap Gameplay, UI;
        readonly Dictionary<string, InputAction> actions = new();
        readonly Dictionary<string, float> holdStart = new();
        public InputAction Move { get; }
        public InputAction Look { get; }
        public InputAction Navigate { get; }
        public InputAction Submit { get; }
        public InputAction Cancel { get; }
        public InputAction TabPrev { get; }
        public InputAction TabNext { get; }
        public bool UsingGamepad { get; private set; }
        public bool Rebinding => rebindOp != null;
        InputActionRebindingExtensions.RebindingOperation rebindOp;
        float rumbleUntil;

        public GameInput()
        {
            Asset = ScriptableObject.CreateInstance<InputActionAsset>();
            Asset.name = "EOA Input";
            Gameplay = Asset.AddActionMap("Gameplay");
            UI = Asset.AddActionMap("UI");

            Move = Gameplay.AddAction("move", InputActionType.Value, expectedControlLayout: "Vector2");
            Move.AddCompositeBinding("2DVector").With("Up", "<Keyboard>/w").With("Down", "<Keyboard>/s").With("Left", "<Keyboard>/a").With("Right", "<Keyboard>/d");
            Move.AddCompositeBinding("2DVector").With("Up", "<Keyboard>/upArrow").With("Down", "<Keyboard>/downArrow").With("Left", "<Keyboard>/leftArrow").With("Right", "<Keyboard>/rightArrow");
            Move.AddBinding("<Gamepad>/leftStick").WithProcessor("stickDeadzone(min=0.15,max=0.95)");
            actions["move"] = Move;

            Look = Gameplay.AddAction("look", InputActionType.Value, expectedControlLayout: "Vector2");
            Look.AddBinding("<Mouse>/delta").WithGroup("Mouse");
            Look.AddBinding("<Gamepad>/rightStick").WithProcessor("stickDeadzone(min=0.12,max=0.95)").WithGroup("Gamepad");
            actions["look"] = Look;

            void Btn(string name, string[] kb, string[] pad)
            {
                var a = Gameplay.AddAction(name, InputActionType.Button);
                foreach (var b in kb) a.AddBinding(b).WithGroup("KeyboardMouse");
                foreach (var b in pad) a.AddBinding(b).WithGroup("Gamepad");
                actions[name] = a;
            }
            Btn("jump", new[] { "<Keyboard>/space" }, new[] { "<Gamepad>/buttonSouth" });
            Btn("dash", new[] { "<Keyboard>/leftShift" }, new[] { "<Gamepad>/buttonEast" });
            Btn("light", new[] { "<Mouse>/leftButton" }, new[] { "<Gamepad>/buttonWest" });
            Btn("heavy", new[] { "<Mouse>/rightButton" }, new[] { "<Gamepad>/buttonNorth" });
            Btn("bolt", new[] { "<Keyboard>/f" }, new[] { "<Gamepad>/leftTrigger" });
            Btn("ability", new[] { "<Keyboard>/q" }, new[] { "<Gamepad>/leftShoulder" });
            Btn("ultimate", new[] { "<Keyboard>/x" }, new[] { "<Gamepad>/rightShoulder" });
            Btn("interact", new[] { "<Keyboard>/e" }, new[] { "<Gamepad>/buttonSouth" });
            Btn("swap", new[] { "<Keyboard>/t" }, new[] { "<Gamepad>/dpad/down" });
            Btn("lockon", new[] { "<Mouse>/middleButton", "<Keyboard>/r" }, new[] { "<Gamepad>/rightStickPress" });
            // Crouch toggle (on foot; the left stick press is the horn only while driving).
            Btn("crouch", new[] { "<Keyboard>/c", "<Keyboard>/leftCtrl" }, new[] { "<Gamepad>/leftStickPress" });
            Btn("pause", new[] { "<Keyboard>/escape", "<Keyboard>/p" }, new[] { "<Gamepad>/start" });
            Btn("inventory", new[] { "<Keyboard>/i", "<Keyboard>/tab" }, new[] { "<Gamepad>/dpad/left" });
            Btn("map", new[] { "<Keyboard>/m" }, new[] { "<Gamepad>/select" });
            Btn("journal", new[] { "<Keyboard>/j" }, new[] { "<Gamepad>/dpad/up" });
            Btn("skills", new[] { "<Keyboard>/k" }, new[] { "<Gamepad>/dpad/right" });
            for (var i = 1; i <= 5; i++) Btn("quick" + i, new[] { "<Keyboard>/" + i }, Array.Empty<string>());
            Btn("skip", new[] { "<Keyboard>/space", "<Keyboard>/enter" }, new[] { "<Gamepad>/buttonSouth" });
            Btn("debug", new[] { "<Keyboard>/f1" }, Array.Empty<string>());

            // Driving: analog pedals / steering (0..1 values: keys give 1, triggers and the stick their travel).
            void AxisBtn(string name, string[] kb, string[] pad)
            {
                var a = Gameplay.AddAction(name, InputActionType.Value, expectedControlLayout: "Axis");
                foreach (var b in kb) a.AddBinding(b).WithGroup("KeyboardMouse");
                foreach (var b in pad) a.AddBinding(b).WithProcessor("axisDeadzone(min=0.1,max=0.97)").WithGroup("Gamepad");
                actions[name] = a;
            }
            AxisBtn("throttle", new[] { "<Keyboard>/w", "<Keyboard>/upArrow" }, new[] { "<Gamepad>/rightTrigger" });
            AxisBtn("brake", new[] { "<Keyboard>/s", "<Keyboard>/downArrow" }, new[] { "<Gamepad>/leftTrigger" });
            AxisBtn("steerLeft", new[] { "<Keyboard>/a", "<Keyboard>/leftArrow" }, new[] { "<Gamepad>/leftStick/left" });
            AxisBtn("steerRight", new[] { "<Keyboard>/d", "<Keyboard>/rightArrow" }, new[] { "<Gamepad>/leftStick/right" });
            Btn("handbrake", new[] { "<Keyboard>/space" }, new[] { "<Gamepad>/buttonEast" });
            Btn("horn", new[] { "<Keyboard>/h" }, new[] { "<Gamepad>/leftStickPress" });
            Btn("vehicleReset", new[] { "<Keyboard>/r" }, new[] { "<Gamepad>/buttonNorth" });

            Navigate = UI.AddAction("navigate", InputActionType.Value, expectedControlLayout: "Vector2");
            Navigate.AddCompositeBinding("2DVector").With("Up", "<Keyboard>/upArrow").With("Down", "<Keyboard>/downArrow").With("Left", "<Keyboard>/leftArrow").With("Right", "<Keyboard>/rightArrow");
            Navigate.AddBinding("<Gamepad>/dpad");
            Navigate.AddBinding("<Gamepad>/leftStick").WithProcessor("stickDeadzone(min=0.5,max=0.95)");
            Submit = UI.AddAction("submit", InputActionType.Button);
            Submit.AddBinding("<Keyboard>/enter"); Submit.AddBinding("<Keyboard>/space"); Submit.AddBinding("<Gamepad>/buttonSouth");
            Cancel = UI.AddAction("cancel", InputActionType.Button);
            Cancel.AddBinding("<Keyboard>/escape"); Cancel.AddBinding("<Gamepad>/buttonEast"); Cancel.AddBinding("<Gamepad>/start");
            TabPrev = UI.AddAction("tabPrev", InputActionType.Button);
            TabPrev.AddBinding("<Keyboard>/q"); TabPrev.AddBinding("<Gamepad>/leftShoulder");
            TabNext = UI.AddAction("tabNext", InputActionType.Button);
            TabNext.AddBinding("<Keyboard>/e"); TabNext.AddBinding("<Gamepad>/rightShoulder");

            Asset.Enable();
            InputSystem.onActionChange += OnActionChange;
        }

        void OnActionChange(object obj, InputActionChange change)
        {
            if (change != InputActionChange.ActionPerformed || obj is not InputAction a || a.activeControl == null) return;
            var dev = a.activeControl.device;
            if (dev is Gamepad) UsingGamepad = true;
            else if (dev is Keyboard || dev is Mouse) UsingGamepad = false;
        }

        public void Dispose()
        {
            InputSystem.onActionChange -= OnActionChange;
            rebindOp?.Dispose();
            Asset.Disable();
            UnityEngine.Object.Destroy(Asset);
        }

        public InputAction Action(string name) => actions.TryGetValue(name, out var a) ? a : null;

        public bool Pressed(string name) => !Rebinding && actions.TryGetValue(name, out var a) && a.WasPressedThisFrame();
        public bool Held(string name) => !Rebinding && actions.TryGetValue(name, out var a) && a.IsPressed();
        public bool Released(string name) => !Rebinding && actions.TryGetValue(name, out var a) && a.WasReleasedThisFrame();

        /// <summary>Seconds the action has been held (0 when not held). Call once per frame per action you query.</summary>
        public float HoldTime(string name)
        {
            if (!Held(name)) { holdStart.Remove(name); return 0; }
            if (!holdStart.TryGetValue(name, out var t)) holdStart[name] = t = Time.unscaledTime;
            return Time.unscaledTime - t;
        }

        public Vector2 MoveVector => Rebinding ? Vector2.zero : Vector2.ClampMagnitude(Move.ReadValue<Vector2>(), 1);

        /// <summary>Analog value of an axis action (0..1; 0 while rebinding or when the action is unknown).</summary>
        public float Value(string name) => !Rebinding && actions.TryGetValue(name, out var a) && a.enabled ? Mathf.Clamp01(a.ReadValue<float>()) : 0f;

        /// <summary>Look delta in degrees-ish units (mouse pixels or stick * dt * speed).</summary>
        public Vector2 LookDelta(float padSpeed)
        {
            if (Rebinding) return Vector2.zero;
            var v = Look.ReadValue<Vector2>();
            var ctl = Look.activeControl;
            if (ctl != null && ctl.device is Gamepad) return v * (220f * padSpeed * Time.unscaledDeltaTime);
            return v * 0.12f;
        }

        public void EnableGameplay(bool on)
        {
            if (on) Gameplay.Enable(); else Gameplay.Disable();
        }

        readonly Dictionary<(string, bool), string> labelCache = new();
        int labelVersion = -1;

        /// <summary>Human-readable label of the binding used for the current device (cached until bindings change).</summary>
        public string Label(string name)
        {
            // The HUD asks every half second; display strings allocate, so cache per action and device kind.
            var version = BindingVersion();
            if (version != labelVersion) { labelCache.Clear(); labelVersion = version; }
            if (labelCache.TryGetValue((name, UsingGamepad), out var cached)) return cached;
            var label = LabelUncached(name);
            labelCache[(name, UsingGamepad)] = label;
            return label;
        }

        /// <summary>Changes whenever a binding override is added/removed (rebind, reset, load).</summary>
        int BindingVersion()
        {
            var h = 17;
            foreach (var a in Gameplay.actions)
                for (var i = 0; i < a.bindings.Count; i++)
                {
                    var o = a.bindings[i].overridePath;
                    h = h * 31 + (o == null ? 0 : o.GetHashCode());
                }
            return h;
        }

        string LabelUncached(string name)
        {
            if (!actions.TryGetValue(name, out var a)) return "?";
            var group = UsingGamepad ? "Gamepad" : "KeyboardMouse";
            for (var i = 0; i < a.bindings.Count; i++)
            {
                var b = a.bindings[i];
                if (b.isComposite || b.isPartOfComposite) continue;
                var isPad = b.effectivePath.StartsWith("<Gamepad>");
                if (isPad != UsingGamepad) continue;
                if (!string.IsNullOrEmpty(b.groups) && !b.groups.Contains(group)) continue;
                return Pretty(a.GetBindingDisplayString(i, InputBinding.DisplayStringOptions.DontIncludeInteractions));
            }
            if (name == "move") return UsingGamepad ? "LS" : "WASD";
            return "—";
        }

        static string Pretty(string s) => s switch
        {
            "LMB" or "Left Button" => "LMB", "RMB" or "Right Button" => "RMB", "Middle Button" => "MMB",
            "Left Shift" => "L-Shift", "Escape" => "Esc", "Space" => "Space", "Up Arrow" => "Up", "Down Arrow" => "Down",
            "Left Stick Left" or "LS Left" or "Left Stick/Left" => "LS Left", "Left Stick Right" or "LS Right" or "Left Stick/Right" => "LS Right",
            _ => s.Length == 1 ? s.ToUpperInvariant() : s,
        };

        /// <summary>Listen for a new key/button for an action (keyboard or pad depending on bindingIndex). Esc cancels.</summary>
        public void StartRebind(string name, bool gamepad, Action<bool> done)
        {
            if (!actions.TryGetValue(name, out var a) || name == "move") { done?.Invoke(false); return; }
            var idx = -1;
            for (var i = 0; i < a.bindings.Count; i++)
                if (!a.bindings[i].isComposite && a.bindings[i].effectivePath.StartsWith("<Gamepad>") == gamepad) { idx = i; break; }
            if (idx < 0) { done?.Invoke(false); return; }
            var wasEnabled = a.enabled;
            a.Disable();
            rebindOp = a.PerformInteractiveRebinding(idx)
                .WithControlsExcluding("<Mouse>/position").WithControlsExcluding("<Mouse>/delta")
                .WithCancelingThrough("<Keyboard>/escape")
                .WithControlsHavingToMatchPath(gamepad ? "<Gamepad>" : "<Keyboard>")
                .WithControlsHavingToMatchPath(gamepad ? "<Gamepad>" : "<Mouse>")
                .OnMatchWaitForAnother(0.1f)
                .OnComplete(op => Finish(true))
                .OnCancel(op => Finish(false))
                .Start();
            void Finish(bool ok)
            {
                rebindOp?.Dispose();
                rebindOp = null;
                if (wasEnabled) a.Enable();
                if (ok) SwapConflicts(a, idx);
                done?.Invoke(ok);
            }
        }

        /// <summary>If another gameplay action used the new control, give it this action's old control.</summary>
        void SwapConflicts(InputAction changed, int idx)
        {
            var path = changed.bindings[idx].effectivePath;
            foreach (var other in Gameplay.actions)
            {
                if (other == changed || other.name == "skip" || other.name == "move" || other.name == "look") continue;
                if (!SameContext(changed.name, other.name)) continue; // on-foot and driving keys may overlap
                for (var i = 0; i < other.bindings.Count; i++)
                {
                    if (other.bindings[i].effectivePath != path) continue;
                    var old = changed.bindings[idx].path; // default path
                    other.ApplyBindingOverride(i, old);
                }
            }
        }

        /// <summary>Both actions can be live at the same moment (both on foot, both driving, or one is shared).</summary>
        static bool SameContext(string a, string b)
        {
            var da = Array.IndexOf(DriveActions, a) >= 0;
            var db = Array.IndexOf(DriveActions, b) >= 0;
            if (da == db) return true;
            var other = da ? b : a;
            return other == "interact" || other == "pause" || other == "map";
        }

        public void ResetBindings()
        {
            foreach (var a in Gameplay.actions) a.RemoveAllBindingOverrides();
        }

        public string SaveOverrides() => Asset.SaveBindingOverridesAsJson();

        public void LoadOverrides(string json)
        {
            if (string.IsNullOrEmpty(json)) { ResetBindings(); return; }
            try { Asset.LoadBindingOverridesFromJson(json); }
            catch (Exception e) { Debug.LogWarning($"[input] bad binding overrides ignored: {e.Message}"); ResetBindings(); }
        }

        public void Rumble(float low, float high, float seconds, bool enabled)
        {
            if (!enabled || Gamepad.current == null) return;
            Gamepad.current.SetMotorSpeeds(low, high);
            rumbleUntil = Time.unscaledTime + seconds;
        }

        /// <summary>Call every frame (stops rumble, tracks device).</summary>
        public void Tick()
        {
            if (rumbleUntil > 0 && Time.unscaledTime > rumbleUntil) { Gamepad.current?.SetMotorSpeeds(0, 0); rumbleUntil = 0; }
        }

        public static void LockCursor(bool locked)
        {
            Cursor.lockState = locked ? CursorLockMode.Locked : CursorLockMode.None;
            Cursor.visible = !locked;
        }
    }
}
