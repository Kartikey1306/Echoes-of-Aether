# Echoes of Aether — Unity port: shared brief for module authors

The game is being ported from a working TypeScript/three.js prototype (`/Users/kartikey/Desktop/Game/src`)
to **Unity 6.3 LTS (6000.3.25f1), C#, URP**. The prototype is the behavioural reference: port its
behaviour, tuning numbers and content faithfully, but implement it the idiomatic Unity way.

Unity project: `/Users/kartikey/Desktop/Game/unity/EchoesOfAether`

## Ground rules
- Namespace everything `EOA`. Target C# 9 (Unity 6). No `unsafe`, no threads, no `Task.Delay`/`Task.Run`
  (WebGL is single threaded). For waits use `await Awaitable.WaitForSecondsAsync(s)` /
  `await Awaitable.NextFrameAsync()`; compose flows with `async Task`.
- Packages available: URP 17.3, Input System 1.20, Cinemachine 3.1, AI Navigation 2.0 (NavMeshAgent /
  NavMeshSurface), Newtonsoft JSON 3.2, Timeline 1.8, UI Toolkit (built in), uGUI 2.0, Test Framework.
- Builds must work on **WebGL and macOS**. Use the built-in Particle System (not VFX Graph), no compute
  shaders, no geometry shaders.
- Never use `FindObjectOfType` in hot paths; use the `G` service locator.
- Only write files inside the folders you were assigned. Do not edit files owned by others; if you need
  an API that does not exist, add it in a new file in your folder as an extension method or adapter, or
  write it down in your final report as a requested change.
- The Unity editor is not licensed yet, so you cannot compile. Write code carefully against documented
  Unity 6 APIs; keep it compiling in your head (usings, types, nullability). Prefer simple, explicit code.

## Existing foundation (read these first)
- `Assets/Scripts/Core/Bus.cs` — typed event bus `Bus.On<T>/Emit<T>` + all event structs.
- `Assets/Scripts/Core/Contracts.cs` — `IDamageable`, `HitInfo`, `HitKind`, `Team`, `IAudio`, `IVfx`,
  `IWorld`, `IHeroStatus`, `IPresentation`.
- `Assets/Scripts/Core/GameInput.cs` — Input System actions (`G.Input.Pressed("light")`, `Held`, `HoldTime`,
  `MoveVector`, `LookDelta`, `Label(action)`, `StartRebind`, `UsingGamepad`, UI actions `Navigate/Submit/Cancel/TabPrev/TabNext`).
- `Assets/Scripts/Data/GameData.cs` — typed JSON data (`GameData.Items`, `Quests`, `Dialogues`, `Speakers`,
  `Zones`, `Enemies`, `Abilities`, `Skills`, `Powerups`, `Collectibles`, `Hints`, `GameData.T(key)` locale).
- `Assets/Scripts/Game/*.cs` — `GameState`, `QuestSystem`, `DialogueSystem` (+ `IDialogueView`), `Inventory`,
  `Progression` (+ `CharStats`), `Powerups` (+ `Buffs`), `Settings` (+ `SettingsData`), `SaveSystem`
  (+ `SlotInfo`, `SaveEnvelope`), `Appearance` (+ palettes, presets), `G` (service locator),
  `GameManager` (+ `GameManager.Api.cs`: NewGame/ContinueGame/LoadFromEnvelope/ManualSave/Autosave/
  UsePowerupItem/SetAppearance/AppearanceFor/RetryFromCheckpoint/LoadLastSave/SetPaused/CanSaveNow…).
- Data JSON lives in `Assets/Resources/Data/*.json` (identical to the prototype's `src/data`).

## Runtime architecture
- `Boot` scene: `GameManager` (DontDestroyOnLoad), UI root (`UIDocument`), audio, VFX pool, camera rig.
- Zones are additive scenes `Zone_<id>` with a `ZoneDefinition` component; the zone runtime implements `IWorld`.
- Heroes: `Hero` MonoBehaviour (CharacterController + humanoid Animator) implements `IDamageable` and
  `IHeroStatus`. `G.Manager.Player` is the controlled hero, `G.Manager.Companion` the AI partner.
- Physics layers (set up by the project setup editor script): `Default`(0), `World`(6), `Player`(7),
  `Enemy`(8), `NPC`(9), `Interactable`(10), `Projectile`(11), `IgnoreCamera`(12), `Pickup`(13).
- Character models come from Blender (FBX, Humanoid "mixamorig:" skeleton) and robots from Blender (FBX,
  rigid parts, see the enemies brief). Until they exist, code must degrade gracefully with primitives.
