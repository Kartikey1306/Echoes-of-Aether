# Echoes of Aether: jam submission

Status: updated 2026-10-08. Items marked **USER** need a decision or action from the project owner (jam rules, publishing). The store page text is in
`marketing/ITCH_PAGE.md`; this file is the submission summary for the jam entry and its rules.

## Entry summary

| Field | Value |
|---|---|
| Game | Echoes of Aether |
| Jam | DreamLayer Jam (named in the in-game credits). **USER: confirm the jam name, theme, deadline and rules.** |
| Genre | Third-person cyberpunk action-adventure |
| Engine | Unity 6.3 LTS (6000.3.25f1), URP, C# |
| Platforms | **Windows 10/11 x64** (`Builds/EchoesOfAether_Windows_x64.zip`, built 2026-10-07 with `tools/build/build_windows.sh`; D3D11/D3D12/Vulkan, hardware-picked preset), macOS and WebGL. The Windows zip has not yet been run on Windows hardware: **USER: test it on a Windows PC before submitting.** |
| Team | Kartikey (direction and production) |
| Length | About 45 minutes for the main story (design target; not measured in Unity) |
| Players | 1 |

## One-paragraph pitch

Two survivors wake in the rain of Aether-9, a neon city that went silent seven years ago. Following a signal from
under the city, they fight rogue machines, uncover what Dr. Ilse Maren did to save four thousand people, and decide
what to do with the Core that holds their echoes. Play as Kael (close combat) or Giva (speed and Echo Sight), design
your hero, and explore a cyberpunk district built in Blender.

## What exists (verified 2026-10-05)

- Story and systems: 5 missions, 4 side quests, 6 zones, 5 cinematics, 32 dialogues, boss fight. Validator:
  17 PASS, 1 WARN, 0 FAIL (`docs/PROJECT_AUDIT.md`). The automated story run (M1–M5, ending, credits) PASSes with
  0 errors (`docs/FINAL_QA_REPORT.md`).
- Two heroes with distinct move sets, AI companion, character switching, three difficulty levels.
- Heroes rebuilt in Blender to match the DreamLayer concepts (outfits, glows, hair, weapons), with custom skin, eye and hair shaders; twist bones and corrective shapes for clean joints; NPCs with techwear and cyberware.
- Customisation catalog: 34 hairstyles, 15 glasses (auto-fitted to the face), 8 armour sets, 16 glowing tattoos.
- Combat with input buffering, hit-stop, perfect dodge, deflect, weapon trails and robot debris deaths.
- City art: 15 Blender landmarks, 47 street assets, Blender storm sky, wet-street reflections (rain removed at the owner's request), per-district palettes.
- Measured performance (macOS, M4, 1080p, `docs/PERFORMANCE.md`): Low 110–210 fps, Medium 90–120 fps, High 50–70 fps; the game picks a preset from the hardware and lowers it if gameplay runs under 40 fps.
- Character designer: presets, body, face, hair, ink and outfit sections.
- Animation: Quaternius Universal Animation Library (CC0) for stance, talk, jumps, reactions and attacks; CMU motion capture for walk, run, sprint and crouch; posture corrected so the heroes stand upright and square.
- Open cyberpunk district (721 x 625 m, five districts) with crowd and traffic; 10 cyber vehicles.
- Subtitles, rebinding, UI scale, flash and shake limits, three save slots with backups.
- Full voice-over (161 lines, Kokoro TTS rendered offline), on by default.

## What does not exist yet (do not claim)

- AAA hand-sculpted faces: the heroes are MakeHuman-based; faces are softer and plainer than the concept paintings, and hair cards show some coarseness up close.
- Measured playtime and WebGL frame rate.
- Store images re-rendered with the remade heroes (current cover/key art use the previous models).
- A human play session (automated runs only; `docs/FINAL_QA_REPORT.md`).

## Rules compliance

**USER: check each item against the jam rules once they are confirmed.**

| Topic | Position |
|---|---|
| AI-generated assets | All in-game 3D art and renders are made in Blender or procedurally. Voice lines are rendered offline with Kokoro-82M text-to-speech (Apache 2.0). Two DreamLayer concept references guided the character remake (not shipped); six DreamLayer images ship as holographic adverts in the city. |
| DreamLayer | Integrated through MCP. 8 images generated with promotional credits: master concept references for Kael and Giva (guided the 3D character models, not shipped) and six fictional in-world adverts (cybernetic implant, ramen, Aether crystal, hover car, techwear fashion, energy drink) on the Arcology Gate mega-billboard, over the plaza Noodle Bar and on about one in three holographic billboards across the city (`docs/DREAMLAYER_ASSET_LOG.md`) |
| Third-party assets | MakeHuman (CC0; three AGPL3-headed assets were removed and replaced procedurally), CMU motion capture (credit required, included), Quaternius Universal Animation Library 1 & 2 (CC0), fonts under OFL, Newtonsoft.Json (MIT). Full list: `docs/THIRD_PARTY_LICENSES.md` |
| Pre-existing work | A TypeScript/three.js prototype (`src/`) was the design reference and is not the submission. **USER: confirm whether the jam allows pre-existing prototypes or code** |
| Secrets | None in the repository (validator secret scan: 191 files) |

## Submission checklist

| Step | Status |
|---|---|
| Unity WebGL build (`docs/BUILD_CHECKLIST.md`) | Built 2026-10-05 |
| Test in a browser | USER (not run by the agents) |
| macOS build (optional) | Built 2026-10-05 |
| Store images rendered | Done (previous hero models); re-render recommended |
| Fresh screenshots after the city art pass | `Captures/gfx_after/` |
| Page text final (`marketing/ITCH_PAGE.md`) | USER review before publishing |
| Credits screen matches the actual content | Updated 2026-10-06 (DreamLayer concept references, Kokoro voices) |
| Licence decision on three AGPL3-headed MakeHuman assets | Done: replaced procedurally (2026-10-04) |
| Remove orphan `Cloth_*` materials of the removed garments | Done |
| Final QA (`docs/FINAL_QA_REPORT.md`, `docs/VISUAL_AUDIT.md`) | Automated QA done; human play session pending |

## Credits (summary)

Directed and produced by Kartikey. Unity 6; Blender 5.2 with MakeHuman/MPFB (CC0
assets); CMU Graphics Lab Motion Capture Database ("The data used in this project was obtained from mocap.cs.cmu.edu.
The database was created with funding from NSF EIA-0196217."); Rajdhani and Inter (OFL 1.1); Newtonsoft.Json (MIT).
Details: `docs/THIRD_PARTY_LICENSES.md`, `docs/ANIMATION_CREDITS.md`, `marketing/ART_CREDITS.md`.
