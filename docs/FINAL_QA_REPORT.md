# Final QA Report

Status date: 2026-10-06 (final pass 01:08–02:00 on the final content: remade heroes, hair v5, fitted eyewear, armour refit, re-rendered art). Engine: Unity 6000.3.25f1, URP 17.3. This report separates **automated
verification that was actually run** from items that still need a **human play session**. Nothing below is claimed
as verified unless a run or capture backs it.

## 1. Automated verification (run on 2026-10-05)

| Check | Result | Evidence |
|---|---|---|
| C# compile, editor + player (`tools/unitycheck/check.py --player`) | **0 errors** (129 runtime / 17 editor files) | last run 23:3x |
| Project validator (`node tools/validation/validate_unity.mjs`) | **17 PASS, 1 WARN, 0 FAIL** | WARN = 0 of 161 voice-over lines recorded (subtitle-only by design) |
| Full main story autopilot M1 → M5 → ending → credits (`SmokeTest.RunStory`) | **PASS**, 0 errors (final pass) | `Captures/final_story/` |
| Zone tour, all 6 zones incl. the open city (`SmokeTest.Run`) | **0 errors** (final pass) | `Captures/final_tour/` |
| Combat feel (both heroes: combo, finisher, perfect dodge, deflect, ability, ultimate) | **OK**, 0 errors | `Captures/gfx_after/compare/combat_*`, `Captures/combat_feel/` |
| Hero close-ups incl. eyewear (`SmokeTest.RunHeroes`) | **OK**, 0 errors (final pass) | `Captures/final_heroes/` |
| Avatar / animation diagnostics (`AvatarDiag`) | wrists 0–4°, neck 10–18°, relaxed fingers, feet planted | `Captures/avatar_diag.txt` |
| Character build (`CharacterBuilder.BuildAll`) | 7 prefabs, **0 Rig Errors**; Kael 4 twist bones / 14 correctives, Giva 4 / 22 | build logs |
| Kit build (`EnvLibraryBuilder.Build`) | Environment 332, Vehicles 10, Landmarks 67, Street 47 prefabs, **0 failed** | build logs |
| macOS player build | **Success** (final pass) — `Builds/macOS/EchoesOfAether.app`, 2.3 GB | build log |
| WebGL player build | **Success** — 202 MB (190 MB data + 12 MB wasm, Brotli); textures capped at 512 px, armour sets desktop-only | build log |
| Player benchmark (M4, 1080p, High; development build) | city 84.8 fps avg, combat 65.7 windowed / 129.8 fullscreen (1% low 80.9), zones 110 fps; plaza load 2.2 s | `docs/PROJECT_AUDIT.md`, perf report |
| Secrets scan (DreamLayer key pattern) | **no matches** in scripts, data, docs or builds | validator |

## 2. QA checklist coverage

Legend: **A** = covered by an automated run above · **C** = exercised by code paths in the autopilot but not
asserted · **H** = needs a human play session (not done).

| Area | Coverage | Notes |
|---|---|---|
| Boot, main menu, character select, designer | A | RunHeroes / RunStory boot through the menu |
| New Game, story missions M1–M5, ending, credits | A | RunStory |
| Movement, camera, lock-on | C / H | Autopilot teleports; feel needs a human |
| Combat, abilities, perfect dodge, deflect | A | Combat-feel run (scripted inputs) |
| Enemies (drone, sentinel, warden, stalker, guardian boss) | A | Story + combat runs |
| Quests and side quests | A (main) / C (side) | Validator checks all 9 quests' data; side quests not auto-played |
| Inventory, powerups, collectibles | C | Data validated; pickups occur in runs |
| Dialogue and cinematics, skip | A | Story run advances and skips |
| Save / load / autosave / corrupt-save recovery | C | CRC + backup + atomic writes validated statically; not asserted in Unity this cycle |
| Settings (graphics presets, audio, accessibility) | C | Benchmark settings sweep shows presets change performance |
| Pause, death, respawn | H | |
| Controller, remapping, window resize | H | |
| Rapid menu clicks / rapid transitions / falling out of the world | H | |

## 3. Known issues (open)

1. **Hero faces** read as stylised MakeHuman faces, not hand-sculpted AAA faces.
2. **Default hair** (v5) reads well at game distance; at close range the alpha-tested hairline is still a fairly
   clean edge (softer with TAA on High/Ultra).
3. **Armour sets** refitted to the remade bodies (0 mm on Kael, up to 3 mm on Giva in one aiming pose).
4. **Portraits, key art and loading screens** re-rendered with the remade heroes and new city art (done).
5. **Voice-over**: 0 of 161 lines recorded; voice-over is off by default and the game is subtitle-only.
6. **City 1% lows** in fast traversal are below the 50 fps target (worst case ~16 fps windowed, ~28 sustained).
7. **WebGL** ships without the 8 armour sets and with 512 px textures to stay near 200 MB (was 412 MB); the desktop build has everything.
8. **Human play session** not performed by the development agents (see §2, H rows).

## 4. Build outputs

| Target | Path | Status |
|---|---|---|
| macOS (release) | `Builds/macOS/EchoesOfAether.app` | Built 2026-10-05 |
| WebGL | `Builds/WebGL/` | Built 2026-10-06, 202 MB; not yet tested in a browser by the agents |
