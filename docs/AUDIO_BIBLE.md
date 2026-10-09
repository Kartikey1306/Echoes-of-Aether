# Echoes of Aether — Audio Bible

Status date: 2026-10-03.

**Every sound in the game is synthesised by the project's own DSP code.** That covers music, ambience, sound effects
and thunder. No sample libraries, stock audio or generative-AI audio are used.

**Voices (updated 2026-10-06):** at the user's request every line was pre-rendered offline with the Kokoro-82M text-to-speech model (Apache 2.0, `tools/vo/gen_voices.py`); robots get a ring-modulated treatment. The game never synthesises speech at runtime. It plays recorded
voice-over when a recording exists and the player has turned voice-over on. **Voice-over is off by default**: the
player chooses on the character-select screen ("Voices off / on") or in Settings -> Audio -> Voice-over
(`AudioSettings.VoiceOver`). **0 lines have been recorded so far**, so subtitles carry all dialogue.

## 1. Pipeline

```
src/audio/AudioEngine.ts        WebAudio recipes: SFX, generative music moods, ambience beds, thunder (prototype)
        │  tools/audio/render.mjs   runs AudioEngine.ts unmodified in headless Chromium (Playwright + Vite on :5173),
        │                           captures the output, post-processes in Node (tools/audio/wav.mjs)
        ▼
unity/EchoesOfAether/Assets/Resources/Audio/
    SFX/<id>[_v1.._v3].wav        57 SFX ids (107 files)
    Music/<mood>.wav              7 loops
    Ambience/<bed>.wav            6 loops
    Thunder/thunder_1..3.wav      3 variants
    manifest.json                 ids, files, durations, levels, per-file playback gain, bus, loop data
        │  Assets/Editor/Audio/AudioImportPostprocessor.cs   (import settings by folder)
        ▼
Assets/Scripts/Audio/AudioManager.cs   pooled playback, buses, crossfading loops, ducking, thunder
```

### Render rules (`tools/audio/render.mjs`)

All files are mono, 44.1 kHz.

| Type | Processing |
|---|---|
| SFX | Leading and trailing silence trimmed, peak -1 dBFS. Recipes with random pitch or noise are rendered as 3 takes (`_v1.._v3`); deterministic recipes as one file. |
| Music | One file per mood, a whole number of chord cycles (60–120 s), seamless loop |
| Ambience | 40–60 s, length chosen so drones and noise loops are phase aligned |
| Thunder | 3 variants, peak -1 dBFS |

Loop seams:

* Random draws are reseeded so that the material after the loop end repeats the loop start.
* Each file begins with that real continuation and crossfades back where the two match best.
* Music is RMS-normalised to -16 dBFS and ambience to -18 dBFS, with a -1 dBFS peak ceiling.

Mix: `manifest.json` `files[].gain` is the playback volume that restores the prototype's relative balance, including
the effect of its master compressor (threshold -14 dB, knee 10, ratio 4).

Verification: `node tools/audio/verify.mjs` checks the set. Every WAV must decode as PCM16 mono 44.1 kHz and match
the manifest. Nothing may be silent or clip. Loops must wrap continuously, coverage must match the recipe names, and
there must be no stray files. **Result on 2026-10-03: PASS.**

Re-rendering:

```
node tools/audio/render.mjs     # starts the Vite dev server if needed
node tools/audio/verify.mjs
```

## 2. Music

Generative music moods are defined in `AudioEngine.ts` (`MOODS`). Each mood has a chord progression over a root note
and layer weights for pad, bass, arpeggio, percussion and pulse. The loop lengths are those of the rendered files.

| Mood | BPM | Root | Harmony | Character (layer weights) | Loop | Used |
|---|---:|---|---|---|---:|---|
| `menu` | 64 | D | Minor 9 / minor 7 voicings | Pad-led (0.9), soft arpeggio, no percussion | 90.0 s | Main menu, character select |
| `explore` | 76 | D | Minor 7 progression | Pad 0.7, arpeggio 0.4, light percussion 0.12 | 101.1 s | Central Plaza |
| `combat` | 128 | A | Minor triads | Bass 0.9, percussion 0.85, arpeggio 0.6 | 75.0 s | Any zone while enemies are aggressive |
| `boss` | 140 | G | Diminished and minor triads | Bass 1.0, percussion 1.0, pulse 0.8 | 82.3 s | Aether Core zone; while a boss is active |
| `sidequest` | 84 | G | Major 7 | Bright (0.7), arpeggio 0.5 | 68.6 s | Rooftop Sector |
| `tension` | 90 | F | Semitone clusters (0-1-7, 0-1-6) | Pad 0.8, pulse 0.55, sparse arpeggio | 85.3 s | Metro, Research Facility, Vault |
| `ending` | 70 | E | Major 9 | Pad 1.0, no percussion | 82.3 s | Credits; prototype dawn plaza |
| `silence` | — | — | — | No clip | — | Zone loading, death |

Selection logic (`GameManager.UpdateMusic`):

1. Start with the zone's music.
2. `boss` if a boss is active.
3. Otherwise `combat` while in combat. Combat ends 4 s after the last aggressive enemy within 35 m.
4. Otherwise `sidequest` when a side quest is tracked in the rooftops.
5. `silence` while dying.

Moods crossfade over 2 s on three alternating sources with an equal-power curve.

## 3. Ambience

| Bed | Zone | Content (manifest data) | Loop |
|---|---|---|---:|
| `rain_city` | Central Plaza, main menu | Rain noise with 0.07 Hz swell and about 1,100 sporadic drop/splash events per loop | 58 s |
| `metro_drip` | Abandoned Metro | 48 Hz drone, 0.05 Hz swell, about 340 drips | 60 s |
| `facility_hum` | Research Facility | 60 / 120 Hz electrical hum, 0.1 Hz swell, about 150 events | 60 s |
| `vault_hum` | Underground Vault | 41 / 61.7 Hz drones, 0.03 Hz swell, about 190 events | 60 s |
| `wind_roof` | Rooftop Sector | Wind with 0.09 and 0.13 Hz gusts | 54 s |
| `core_drone` | Aether Core | 36.7 / 55 / 73.4 Hz drones, 0.04 and 0.2 Hz modulation | 50 s |

**Thunder.**

* `Weather` emits a `Lightning` event on each strike. `AudioManager.Thunder` then plays one of three thunder takes
  after a distance delay of 0.6–2.8 s; stronger flashes arrive sooner and louder.
* Only zones with lightning have thunder: the Plaza (every 14–32 s) and the Rooftops (every 8–18 s).

## 4. Sound effects

The 57 SFX ids, grouped by use. The ids match the prototype recipe names, so game code calls them by name
(`G.Audio.Play("hit", position)`).

| Group | Ids |
|---|---|
| Player movement | `footstep`, `jump`, `land`, `dash`, `step`, `respawn` |
| Player combat | `swing_light`, `swing_heavy`, `hit`, `hit_heavy`, `charge`, `slam`, `bolt`, `pulse`, `echo`, `ult_charge`, `ult_impact`, `shield_hit`, `shield_break`, `player_hurt`, `player_death`, `error` |
| Enemies | `drone_charge`, `drone_shot`, `drone_dive`, `drone_death`, `enemy_telegraph`, `enemy_hit_metal`, `enemy_hit_player`, `enemy_stagger`, `sentinel_death`, `shield_block`, `explosion`, `metal_impact` |
| World and interaction | `door`, `terminal`, `interact`, `pickup`, `item`, `lore`, `reveal`, `checkpoint`, `cinematic_whoosh` |
| Powerups | `powerup_shard`, `powerup_phase`, `powerup_overcharge`, `powerup_shield`, `powerup_echo` |
| Interface | `ui_hover`, `ui_click`, `ui_back`, `error_ui`, `toast`, `quest_accept`, `quest_complete`, `save`, `load` |

The validator confirms that every sound id referenced in C# exists in the manifest: "71 audio clips; 43 referenced
sounds resolved".

## 5. Mix and playback (`AudioManager.cs`)

### Buses

There is no AudioMixer asset. Buses are volume multipliers set from Settings → Audio.

| Bus | Default | Settings slider |
|---|---:|---|
| master | 0.85 | Master volume |
| music | 0.60 | Music |
| sfx | 0.80 | Sound effects |
| ambience | 0.70 | Ambience |
| ui | 0.60 | Interface |
| voice | 0.90 | Voice-over playback only; off unless the player enables it (see §6) |

* The bus volume curve follows the prototype: gain = v².
* Each clip's manifest `gain` restores the prototype balance.
* UI sounds (`ui_*`, `quest_*`, `save`, `load`, `error_ui`, `checkpoint`, `item`, `lore`, `toast`) route to the ui
  bus.

### Sources

* **Pools.** 20 positional (3D) sources and 8 non-positional sources, created once (no allocation during play).
* **Positional sounds.** Full volume within 2 m, logarithmic roll-off to 40 m, not started beyond 45 m.
* **Variation.** Non-UI SFX get ±4% pitch jitter. Randomised SFX pick a take, never the same one twice in a row.
* **Limits.** Minimum retrigger gap is 25 ms (60 ms for footsteps, 30 ms for UI). At most 4 concurrent instances
  per id (6 for `footstep` and `hit`).
* **Music and ambience.** Each is a three-source crossfading loop channel.
* **Ducking.** `Duck(amount, seconds)` lowers music by `amount` and ambience by 0.75 × `amount`.
  * Dialogue: 0.55 (music ×0.45)
  * Recorded voice-over: 0.45 while a recording plays
  * Pause and cinematics: 0.5

### Import settings

`AudioImportPostprocessor.cs`, by folder under `Assets/Resources/Audio/`:

| Folder | Channels | Load type | Format |
|---|---|---|---|
| `SFX/`, `Thunder/` | forced mono | Decompress On Load | Vorbis q0.7 |
| `Music/` | as authored | Streaming | Vorbis q0.6, load in background |
| `Ambience/` | as authored | Compressed In Memory | Vorbis q0.5, load in background |
| `Voice/` | forced mono | Compressed In Memory | Vorbis q0.7 |

The source WAVs total about 86 MB on disk; Unity compresses them on import. WebGL ignores load type and format
because the browser decodes the audio, so no WebGL override is set.

## 6. Voice-over: recorded human voice only

`Assets/Scripts/Audio/VoiceOver.cs`:

* **Lookup.**
  * On every `DialogueLineShown` event it looks for `Resources/Audio/Voice/<dialogueId>/<nodeId>_<speakerId>` and
    then `Resources/Audio/Voice/<dialogueId>/<nodeId>` (WAV or OGG).
  * Lines spoken by "the active hero" or "the partner" need one take per hero (`_kael`, `_lyra`).
* **Missing recording.** The line stays subtitle-only. No speech is synthesised anywhere.
* **Presence check.** `tools/validation/validate_unity.mjs` fails the build if a speech-synthesis API name appears in
  C#.
* **Playback.** While a recording plays, music is ducked. Auto-paced subtitle lines stay on screen for at least the
  remaining clip length + 0.3 s. Pausing the game pauses the voice. Skipping a cinematic stops it.

The recording script `docs/VO_SCRIPT.md` (and `tools/vo/vo_lines.csv`) is generated by
`python3 tools/vo/make_vo_script.py` from the dialogue data:

| Fact | Value |
|---|---|
| Total recordings | 161 across 16 speakers. `system` lines stay text-only. |
| Largest parts | Giva 40, Kael 32, Maren 23, Oren 14, Tomas 11, Mira 10, Narrator 6, Nia 5 |
| Delivery spec | Mono WAV, 48 kHz, 24-bit, peaks around -3 dBFS, about 0.2 s of room tone at both ends, dry |
| Location | `unity/EchoesOfAether/Assets/Resources/Audio/Voice/<dialogue>/<file>.wav` |
| **Recorded** | **0 of 161** (the `Voice/` folder does not exist). The validator reports "voice-over: 0 of 161 lines recorded (subtitle-only)". |

Known inconsistencies:

* `AudioSettings.Voice` (default 0.9) now has a "Voice volume" slider in Settings -> Audio. `VoiceOver` applies
  master × voice linearly, whereas the other buses use the v² curve.
* The credits say "Voices generated offline with Kokoro-82M text-to-speech (Apache License 2.0)". Voice-over is on by default.
* The prototype contains a browser speech-synthesis module (`src/audio/Voice.ts`). It is disabled there
  (`enabled = false`) and was not ported. The `voice` fields in `speakers.json` are unused by the Unity game.

## 7. Subtitles

All dialogue is presented as text (`Assets/Scripts/UI/DialogueView.cs`):

* **Interactive conversations.** Portrait (when rendered art exists), coloured speaker name, typewriter text and
  choices. The player advances with Interact, Submit or a click.
* **Radio and cinematic lines.** Auto-paced subtitles. The duration comes from the text length
  (`DialogueView.AutoDuration`), or the voice clip length if longer.

Accessibility settings that apply to subtitles:

* subtitles on or off
* size S / M / L / XL (17 / 21 / 25 / 31 px at 1080p)
* background opacity
* speaker names on or off
