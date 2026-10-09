# Echoes of Aether — UI Bible

Status date: 2026-10-04. The Unity UI is built entirely in C# with **UI Toolkit**: no UXML files and no uGUI canvases.
It is a port of the prototype's DOM UI (`src/ui/*`, `src/ui/styles.css`).

| Area | Files |
|---|---|
| Code | `unity/EchoesOfAether/Assets/Scripts/UI/**` |
| Styles | `Assets/UI/Styles/eoa.uss`, `Assets/UI/Styles/eoa_fonts.uss`, theme `Assets/UI/EOA_Theme.tss` |
| Fonts | `Assets/UI/Fonts/Rajdhani` and `Assets/UI/Fonts/Inter` (SIL OFL 1.1; licence files beside the TTFs) |
| Icons | `Assets/Resources/UI/Icons/*.png` |
| Gradients | `Assets/UI/Textures/*.png` |

## 1. Visual language

* **Style.** Dark graphite panels with thin, precise lines and restrained cyan and violet accents. A cyan corner
  bracket sits top-left and a violet one bottom-right on panels (`ScreenKit.Panel`). No glows, no holographic
  noise.
* **Typography.**
  * Body text: Inter (Regular, Medium, SemiBold, Italic).
  * Headings, buttons, labels and numbers: Rajdhani (Medium, SemiBold, Bold), upper-cased in code because USS has
    no text-transform.
  * Base size 18 px at the 1920×1080 reference resolution.
  * Inter SemiBold supplies symbols Rajdhani lacks (check marks, arrows).
* **Tokens** (`.eoa-root` in `eoa.uss`, mirrored in `U.cs`):

| Token | Value | Use |
|---|---|---|
| `--text` / `--text-dim` / `--text-faint` | `#dfe7ee` / `#8a9aab` / `#5b6876` | Text hierarchy |
| `--bg-1` / `--bg-2` / `--bg-3` | `rgba(10,14,19,.92)` / `rgba(16,22,30,.88)` / `rgba(24,32,42,.9)` | Panels |
| `--line` / `--line-2` | `rgba(130,170,200,.18)` / `rgba(130,190,220,.34)` | Borders, rules |
| `--cyan` | `#5fd4f0` | Focus, primary accent, uncommon rarity |
| `--violet` | `#a68bff` | Giva, secondary accent, rare rarity |
| `--amber` | `#ffb45e` | Warnings, epic rarity |
| `--red` / `--green` | `#ff5a4a` / `#73e6b0` | Danger / success |
| Kael blue | `#5fb8ff` | Kael's HUD and icon tint |

* **Gradients.** USS has no gradients, so gradients and vignettes are baked PNGs in `Assets/UI/Textures` (`grad_*`,
  `vignette`, `shade_v`, `rule`) tinted at runtime.
* **Icons.** 128 px white-on-transparent glyphs rasterised from the prototype's SVG set (`src/ui/Icons.ts`) by
  `Assets/Editor/UI/Tools~/rasterize_icons.mjs`, and tinted per use.
* **Rendered art.** Item art, portraits, loading art and the title logo are optional Blender renders; see §5.

## 2. Architecture

* **`UIManager`** (`UIManager.cs`, `UIManager.Navigation.cs`, `UIManager.Feedback.cs`) is created at boot under the
  GameManager and needs a `UIDocument`.
  * **Panel settings.** It uses `PanelSettings` from `Resources/UI/UIRefs` (Scale With Screen Size, 1920×1080, match
    0.5, EOA theme), cloned at runtime so UI scale changes never touch the asset.
  * **Layers**, bottom to top:

    | Layer | Contents |
    |---|---|
    | HUD | Gameplay HUD |
    | Dialogue | Conversation panel and subtitles |
    | Hints | Hint cards |
    | Toasts and letterbox | Toasts, cinematic bars, skip prompt, save indicator |
    | Loading | Loading screen |
    | Screens | The screen stack |
    | Fader | Full-screen fades |
    | Debug | F1 overlay |

  * **Contracts.** It implements `IPresentation` (fades, cinematic bars, toasts, hints, skip prompt) and registers
    itself as `G.Presentation`. Its `DialogueView` is registered as `G.Manager.DialogueView`.
* **Screen stack.** Each screen is a `UIScreen`: id, root element, `Back` and `Tab` handlers, `Tick`, `Overlay`
  flag, `HidesBelow` flag, `OnClose`. `Push`, `Pop` and `HideAllScreens` manage the stack.
  * Overlay screens pause gameplay.
  * Full-screen pages with `HidesBelow` (character select, designer, credits) hide every screen beneath them
    (`UIManager.UpdateVisibility`).
* **Screen builders.** Static classes in `Screens/`: `MainMenuScreen`, `CharacterSelectScreen`, `CreditsScreen`,
  `ConfirmDialog` (`MenuScreens.cs`); `PauseScreen`, `SavesScreen`, `DeathScreen` (`GameScreens.cs`); `GamePanels`;
  `SettingsScreen`; `DesignerScreen`. `ScreenKit` provides the standard modal (dimmed backdrop, panel, header, tabs,
  scrolling body, footer), rows, section titles and hint lines.
* **Custom controls** (`UIControls.cs`, `Painters.cs`):
  * `EoaSlider`, `Seg` (segmented choice), `ToggleSwitch`, `Swatches` and `ColorPicker` (HSV)
  * `RingGauge`, drawn with Painter2D: ultimate ring, cooldown pie, skip ring
  * `MapView`, drawn with Painter2D: full map and rotating minimap
* **Pointer input.** It reaches UI Toolkit through an `EventSystem` with `InputSystemUIInputModule`.
  The module's move, submit and cancel are cleared, because `GameInput` drives keyboard and gamepad navigation.

## 3. Screens

| Screen | Contents |
|---|---|
| Main menu | Rendered logo or typographic "ECHOES of Aether" title over the 3D menu stage. Buttons: **Continue** (shows the latest save's mission and playtime; disabled without a save), New Game, Load Game, Settings, Credits, Exit (hidden on WebGL; asks for confirmation). The footer shows the version, release/development, and "Mouse / keyboard / controller supported". |
| Character select | Kael / Giva tabs (LB/RB or Q/E switch); name, role, description, playstyle and combo; the three abilities with icons; save-slot choice (defaults to the first empty slot; overwriting asks for confirmation); **Voice-over choice** ("Voices off" / "Voices on"; off by default; subtitles always show; the same setting as Settings -> Audio -> Voice-over); Back, **Customize** (opens the designer) and **Begin**. The hero rotates by mouse drag or right stick. |
| Character designer | Hero tabs (Kael / Giva) and six section tabs: Presets, Body, Face, Hair, Ink, Outfit. Sliders, colour swatches and toggles; thumbnail grids for hair styles, glasses, tattoo designs and armour sets (each grid appears only when the customisation catalog has items of that kind; the catalog file is missing in the repository at 2026-10-04, so hair falls back to text chips and the other grids are hidden). Ink: tattoo glow colour and intensity. View Face/Body, Randomize, Reset, Done. See `CHARACTER_BIBLE.md` §5. |
| Loading | Zone art with a slow pan (when rendered); zone name, subtitle and quote; one gameplay hint from the zone's hint list; progress bar with stage labels reported by the zone builder; an error panel if the zone fails to load |
| HUD | See §4 |
| Dialogue | Interactive panel: portrait when rendered, coloured speaker name, typewriter text, choices, continue key. Radio and cinematic subtitles: auto-paced, with speaker name. |
| Pause | Zone name and "Paused". Resume, Save Game (disabled with the reason during combat, dialogue or cinematics), Load Game, Inventory, Map, Journal, Ability Matrix, Appearance, Settings, Quit to Main Menu (with confirmation). Summary: tracked quest title and summary; playtime, machines destroyed, quests done, Aether Fragments x/12, Recordings x/6, Hidden Caches x/5. |
| Panels | One modal with tabs (LB/RB or Q/E): **Inventory** (category filter Aether / Powerups / Quest / Upgrades / Lore with counts; item grid with rarity colour; detail with description, quantity/stack and quest; Use for powerups; lore entries show their full text), **Map** (current zone map, player arrow, exits with lock state, legend), **Journal** (Active / Completed / Lore; objectives with progress; lore text with coloured speaker names), **Ability Matrix** (12 nodes in four columns, points available, buy with reason when locked). Footer hints adapt to the device. |
| Settings | 6 sections, see §6 |
| Save / Load | Three slot cards: thumbnail (256×144 JPEG captured at save time), "Slot n · Mission", zone, hero, playtime, date, save kind. Actions: Save Here (confirms overwrite of another slot), Load, Load (backup), Restore Backup, Delete (confirmation). Damaged slots show "Damaged save" or "Damaged - backup available" with the error. Footer: "Atomic writes with a rolling backup per slot". |
| Death ("Signal Lost") | Appears 2.4 s after death: Retry from Checkpoint (autofocus), Load Last Save, Quit to Main Menu |
| Credits | Scrolling roll (48 s; any key, click or button after 0.8 s skips): directed and produced by Kartikey; cast; Unity 6 / URP; Rajdhani and Inter (OFL); characters built in Blender with MakeHuman/MPFB (CC0 assets); city, vehicles and robots modelled in Blender; renders in Blender Cycles; "No AI-generated images"; CMU motion-capture credit; synthesised audio; "No synthesized voices · dialogue presented with subtitles"; thanks to the DreamLayer Jam |
| Confirm dialog | Title, message, OK and Cancel; a danger style for destructive actions |

## 4. HUD (`Hud.cs`)

| Element | Behaviour |
|---|---|
| Vitals (top left) | Portrait, or the initial letter in the hero colour when no portrait is rendered; hero name; shield, health (with damage trail) and energy bars with numbers; swap key badge |
| Ability slots | Ability (Pulse or Echo Sight), Phase (dash or step), Bolt: icon tinted with the hero colour, cooldown pie, key label for the current device |
| Ultimate | Ring gauge 0–100% with key label; drawn in a "locked" style until Core Attunement is owned |
| Quest tracker | Tracked quest (Mission or Side), title, current objectives with check state and progress; `{partner}` replaced by the partner's name |
| Minimap | Rotating disc map of the zone: player, NPCs (not echo-only), exits, objective. With Deep Echo, hidden collectibles are marked while Echo Sight is active. |
| Powerup timers | Icon and ring countdown per active buff |
| Interaction prompt | Key and text for the current interaction candidate, or the locked reason |
| Crosshair | While aiming |
| Hit / kill markers | Flash on hits; a distinct kill marker |
| Objective marker | Diamond and distance toward the tracked objective, routed through the exit toward the objective's zone when it is elsewhere |
| Enemy bars | Health and poise bars over on-screen enemies within 28 m that are aggressive or were hit in the last 4 s. Only elites show a name. |
| Boss bar | Name, health and phase label |
| Feedback layer | Toasts (Info, Quest, Item, Warn, Lore styles), hint cards with inline keycaps, quest-complete banner, save indicator ("Saving" / "Game saved" / "Autosaved"), cinematic letterbox bars, hold-to-skip ring, fades |

The HUD is shown only in Play mode when the game is not paused, no letterbox bars are up and no loading screen is
visible. Code can also force it off with `HudEnabled = false`.

## 5. Rendered-art hooks and fallbacks

| Hook | Loads | Fallback |
|---|---|---|
| `U.Art("Title","logo")` | `Resources/Art/Title/logo` | Typographic title |
| `LoadingScreen` | `Resources/Art/Loading/<zoneId>` | Dark background |
| `U.Portrait(id)` | `Resources/Art/Portraits/<id>` | Initial letter (HUD); no portrait in dialogue |
| `U.ItemIcon(icon, ...)` | `Resources/Art/Items/<icon>` (full colour, rarity underline) | Tinted glyph from `Resources/UI/Icons` |

At 2026-10-04 the six loading images, nine portraits, 18 item images and the logo exist in `Resources/Art/`
(`ART_BIBLE.md` §10). Every screen still works with the fallbacks if a file is missing.

## 6. Settings (6 sections)

Changes apply immediately and save automatically. Slider drags persist after 0.4 s; UI scale applies when the
slider stops moving. Each section has a "Reset" button (with confirmation). Data is in
`Assets/Scripts/Game/Settings.cs` and is sanitised on load.

| Section | Options |
|---|---|
| Gameplay | Difficulty (Story / Normal / Hard), camera sensitivity (0.2–3), aim sensitivity (0.1–2), invert Y, camera shake (0–150%) |
| Graphics | Preset (Low / Medium / High / Ultra / Custom), resolution (labelled 720p / 1080p / 1440p / Native; implemented as URP render scale 0.67 / 0.85 / 1.0 / 1.0), display mode (Windowed / Fullscreen; not applied on WebGL), VSync / 30 / 60 / Unlimited, shadows (Off / Low / Medium / High → shadow distance 0 / 25 / 45 / 70 m), effects (Low / Medium / High), textures (Low / Medium / High → mip limit 2 / 1 / 0; applies on the next area load), view distance (Low / Medium / High → far clip 150 / 260 / 420 m and LOD bias), anti-aliasing (Off / FXAA / SMAA / MSAA 4x) |
| Audio | Master, Music, Sound effects, Ambience, **Voice-over** (Off / On, default Off; "Recorded dialogue (human recordings only)"), Voice volume, Interface |
| Controls | Controller look speed, controller vibration, and a binding table: one row per rebindable action, with keyboard/mouse and controller columns. Controller bindings can be edited only while a pad is connected. |
| Accessibility | Subtitles on/off, subtitle size S/M/L/XL, subtitle background opacity, speaker names, flash intensity (lightning, explosions, screen flashes), camera-shake limit (caps all shake), UI scale (75–150%), hold to skip cinematics |
| Language | English only ("Additional languages can be added as locale files"; strings come from `Resources/Data/locale/en.json`) |

**Rebinding** (`GameInput.StartRebind`):

* Click a binding, then press the new key or button. Esc cancels.
* The key that opened the prompt is ignored.
* If another action used that control, the two swap, and a toast names the action that changed.
* Overrides are stored as JSON in `settings.json` and reloaded at boot.
* Move cannot be rebound.

**Inconsistencies:**

* The resolution labels suggest fixed resolutions, but the setting is a render scale, and "1440p" and "Native" are
  identical (1.0).
* `GameplaySettings.AutoLock` exists in data but is neither exposed nor used.

## 7. Navigation

| Input | Effect |
|---|---|
| Arrow keys / D-pad / left stick | Move focus (0.4 s initial delay, then repeats every 0.12 s). Lists wrap; grids move spatially up and down. On a focused slider or segmented control, left and right change the value. |
| Enter / Space / A | Activate the focused element |
| Esc / B / Start | Back (closes the top screen); plays `ui_back` |
| Q / E, LB / RB | Previous / next tab in tabbed screens |
| Mouse | Hover moves focus; click activates; drag rotates the hero on the menu stage |
| Gameplay hotkeys | Pause (Esc / P / Start), Inventory (I / Tab / D-pad left), Map (M / Select), Journal (J / D-pad up), Ability Matrix (K / D-pad right). Pressing a panel's own key again closes it. |

* **Focus model.** Focusable elements carry the `nav` class with `NavData` (Button, Grid, Seg or Slider) and get a
  focus style. Screens open with the `autofocus` element focused.
* **Hover sounds.** Focus changes play `ui_hover`.
* **Device-aware labels.** Key labels, keycaps in hints and footers switch with the last device used:
  `GameInput.UsingGamepad` flips on the last performed input.
* **Dialogue choices.** These take focus when no screen is open.

## 8. Accessibility summary

* **Subtitles.** All dialogue is always subtitled, with adjustable size, background and speaker names. Voice-over is
  optional and off by default (no recordings exist yet).
* **Comfort.** Flash intensity scales lightning, explosions and screen flashes; camera shake has a global limit.
* **Scaling.** UI scale runs from 75% to 150% by re-flowing the layout, not by zooming a bitmap.
* **Cinematics.** Can be skipped by hold or single press.
* **Input.** Full keyboard, mouse and gamepad support with rebinding; controller vibration toggle.
* **Difficulty.** Selectable at any time, with a Story mode.
* **Cues.** Interaction prompts and objectives are always text, not colour only. Enemy telegraphs are colour plus
  animation plus sound (`enemy_telegraph`).

## 9. Debug overlay (F1)

`DebugOverlay.cs`, available only in development builds (`Debug.isDebugBuild`). It is toggled directly by the F1
key. Values refresh every 0.25 s:

| Row | Content |
|---|---|
| FPS / Frame | Frame rate and frame time |
| Memory | Total allocated and managed |
| Mode | Game mode, plus paused / cinematic / dialogue / combat |
| Zone | Current zone |
| Player | Player position |
| Character | Health, shield, energy |
| Quest | Tracked quest and stage |
| Enemies | Alive and aggressive counts |
| Audio | Music mood and ambience |
| Save | Active slot and time since the last save |

Release builds made with `BuildScripts` remove the `EOA_DEV` scripting define and are non-development, so F1 does
nothing there.
