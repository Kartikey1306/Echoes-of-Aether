# Echoes of Aether — Build Checklist

Status date: 2026-10-06. Exact steps to produce the WebGL (itch.io) and macOS builds from
`unity/EchoesOfAether`. Paths are relative to the repository root `/Users/kartikey/Desktop/Game` unless they start
with `/`.

```
UNITY="/Applications/Unity/Hub/Editor/6000.3.25f1/Unity.app/Contents/MacOS/Unity"
```

## 0. Prerequisites

| # | Step | Check |
|---|---|---|
| 0.1 | Install **Unity Hub** and **sign in** with the Unity account that holds the licence. The editor does not open or build without an active licence (Unity Personal is fine if eligible). | Unity Hub → Preferences → Licenses shows an active licence |
| 0.2 | Install the editor **Unity 6000.3.25f1** (6.3 LTS) with the **WebGL Build Support** module. Add **Mac Build Support** for the macOS build. | `/Applications/Unity/Hub/Editor/6000.3.25f1/PlaybackEngines/` contains `WebGLSupport` and `MacStandaloneSupport` (both present on this machine) |
| 0.3 | Node 22+ and Python 3 for the validators | `node --version`, `python3 --version` |
| 0.4 | Optional, only to regenerate art: Blender 5.2 with MPFB 2.0.17 | — |

## 1. Clean starting point

| # | Step |
|---|---|
| 1.1 | Commit everything. `git status` must be clean. Commit generated sources the build needs, such as character exports under `Assets/Art/Characters/<Name>/`. **Clean-build requirement:** release builds are made only from a committed, tagged state. |
| 1.2 | For a fully clean build: close Unity and delete `unity/EchoesOfAether/Library/` (and `Temp/`). Unity then re-imports everything from source, which proves the project builds from the repository alone. |
| 1.3 | Delete the previous output: `rm -rf Builds/WebGL Builds/macOS`. |
| 1.4 | Make sure `Builds/` is not committed. The root `.gitignore` does not list `Builds/` yet (it lists `unity/EchoesOfAether/[Bb]uild*/`, a different folder), so add `Builds/` to `.gitignore` before building. |

## 2. Open the project and run the setup

| # | Step | Expected |
|---|---|---|
| 2.1 | Unity Hub → Add → select `unity/EchoesOfAether` → open with **6000.3.25f1** | First import takes several minutes |
| 2.2 | The automatic first-open setup runs (`ProjectSetup`, `[InitializeOnLoad]`) when `ProjectSettings/EOA_Setup.txt` is missing. To run it by hand: **EOA → Setup Project (All)**. | Console: `[setup] ✓ Layers` … `✓ Boot scene`, then `[setup] Echoes of Aether project setup complete.`; `[env] environment library: 55 materials, 185 prefabs (0 failed)`; `[characters] build complete`; `[ui-setup] UI assets ready` |
| 2.3 | Alternative without the GUI | `"$UNITY" -batchmode -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.ProjectSetup.RunAllBatch -logFile setup.log`. Exit code 0 means every step succeeded. Check `setup.log` for `error CS` (expect none). |
| 2.4 | Confirm the generated assets | `Assets/Scenes/Boot.unity` (the only scene in Build Settings), `Assets/Settings/EOA_URP.asset`, `Assets/Resources/Characters/*.prefab` (7), `Assets/Resources/Env/Props` (185 prefabs), `Assets/UI/EOA_PanelSettings.asset`, `Assets/Resources/UI/UIRefs.asset`, `Assets/link.xml` |

The setup also applies these player settings: product "Echoes of Aether", company "EchoesOfAether", linear colour
space, WebGL Brotli with decompression fallback, data caching, explicitly-thrown exceptions only, minimal managed
stripping, Active Input Handling "Both".

## 3. Validate

All of these must pass before building (details in `QA_CHECKLIST.md` §1):

| # | Command | Must be |
|---|---|---|
| 3.1 | `node tools/validation/validate_unity.mjs --compile` | Exit code 0: no FAIL lines and every compile line OK. The two known validator false positives (`QA_CHECKLIST.md` A1) must be fixed in the validator, or confirmed to be the only remaining FAILs and signed off. |
| 3.2 | `node tools/audio/verify.mjs` | `PASS` |
| 3.3 | EditMode tests: Test Runner → EditMode → Run All, or `"$UNITY" -batchmode -projectPath unity/EchoesOfAether -runTests -testPlatform EditMode -testResults editmode.xml` | All pass |
| 3.4 | Smoke test: **EOA → Test → Smoke Test**, or `"$UNITY" -batchmode -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.SmokeTest.Run` | Exit code 0; `Captures/smoke/report.json` has no errors |

## 4. Play test in the editor

| # | Step |
|---|---|
| 4.1 | Open `Assets/Scenes/Boot.unity` and press **Play**. The main menu appears with no Console errors. |
| 4.2 | Run the release-candidate pass of `QA_CHECKLIST.md`: at minimum §2–§5 and §10, plus a full main-story playthrough on Normal. |
| 4.3 | Check the Console stays free of errors and exceptions during the pass. |

## 5. Build

### WebGL

* Menu: **EOA → Build → WebGL**.
* Batch:

  ```
  "$UNITY" -batchmode -quit -projectPath unity/EchoesOfAether -buildTarget WebGL \
    -executeMethod EOA.EditorTools.BuildScripts.WebGL -logFile build_webgl.log
  ```

* Output: `Builds/WebGL/` with `index.html` at the top level.
* The build step caps textures at 512 px and leaves the armour-set library (`Resources/Characters/Custom/Armour`)
  out of the player (the folder is hidden during the build and restored afterwards; the designer hides missing
  catalog items). Last result (2026-10-06): **202 MB** — `WebGL.data.unityweb` 190 MB + `WebGL.wasm.unityweb` 12 MB.
* Do **not** use `-buildTarget WebGL` on the command line for the batch build: the script switches and restores the
  platform itself; `EOA.EditorTools.BuildScripts.RestoreEditorPlatform` repairs an interrupted build.

### macOS

* Menu: **EOA → Build → macOS**.
* Batch:

  ```
  "$UNITY" -batchmode -quit -projectPath unity/EchoesOfAether -buildTarget OSXUniversal \
    -executeMethod EOA.EditorTools.BuildScripts.MacOS -logFile build_macos.log
  ```

* Output: `Builds/macOS/EchoesOfAether.app`.

`-buildTarget` is optional. It sets the active platform before the project loads, which avoids a second asset
re-import.

### What `BuildScripts` does

`Assets/Editor/Build/BuildScripts.cs`:

1. Runs the project setup if `ProjectSettings/EOA_Setup.txt` is missing.
2. Stops if the Boot scene is missing.
3. Removes the `EOA_DEV` scripting define.
4. Builds the enabled Build Settings scenes (Boot only) with `BuildOptions.None`: a release, non-development player.
5. Logs `[build] <target>: Succeeded, <n> errors, <n> warnings, <size> MB, <time>`.
6. In batch mode, exits with code 1 if the build fails.

### Check the output

| # | Step |
|---|---|
| 5.1 | The build log shows `Succeeded` with 0 errors. |
| 5.2 | Secret scan over the build: `node tools/validation/validate_unity.mjs` (it scans `Builds/WebGL` and `Builds/macOS`). Expect `PASS [secrets] … or builds`. |
| 5.3 | macOS: open `Builds/macOS/EchoesOfAether.app`. The app is not code-signed or notarised by these scripts; on another Mac use right-click → Open. |
| 5.4 | WebGL local test: `cd Builds/WebGL && python3 -m http.server 8000`, then open `http://localhost:8000`. The decompression fallback lets the Brotli build run on a plain static server. Check the browser console for errors. |
| 5.5 | WebGL canvas size: the project uses the Default WebGL template with **960×600** (`defaultScreenWidthWeb` / `Height` in `ProjectSettings.asset`; the setup does not change it). The UI is authored for 16:9 at 1920×1080 (scale-with-screen, match 0.5). Consider a 16:9 size such as 1280×720 in Player Settings → Resolution and Presentation before building, and use the same size on itch.io. |

## 6. itch.io upload (WebGL)

| # | Step |
|---|---|
| 6.1 | Zip the **contents** of `Builds/WebGL` so that `index.html` is at the root of the zip: `cd Builds/WebGL && zip -r ../EchoesOfAether_WebGL.zip .` |
| 6.2 | On itch.io: create or edit the project → **Kind of project: HTML** → upload the zip → tick **"This file will be played in the browser"**. |
| 6.3 | Embed options: viewport width and height = the WebGL canvas size from 5.5 (960×600 unless changed). Enable **Fullscreen button**. Leave **SharedArrayBuffer support** off: the build is single-threaded (WebGL threads support is off). |
| 6.4 | **Compression.** The build uses **Brotli with the decompression fallback**. itch.io does not send `Content-Encoding` headers for these files, so the fallback decompresses in JavaScript and no server configuration is needed. Do not switch off the fallback for itch.io uploads. |
| 6.5 | Upload the macOS build (zip of `EchoesOfAether.app`) as a separate download marked for macOS, if it is being released. |
| 6.6 | Open the itch page in Chrome and Safari and run `QA_CHECKLIST.md` §16: load, save persistence after reload, audio after the first click, pointer lock, gamepad. |
| 6.7 | Page text: credit the fonts (OFL), MakeHuman CC0 assets and Newtonsoft.Json (MIT) as listed in `THIRD_PARTY_LICENSES.md`, and state that no AI-generated images are used. |

## 7. Release record

Record for each build:

* commit hash and tag
* Unity version (6000.3.25f1)
* validator summary line
* build log summary line (size, time)
* QA pass results
* itch.io upload date

Keep the logs (`setup.log`, `build_webgl.log`, `build_macos.log`, `editmode.xml`, `Captures/smoke/report.json`) with
the release notes.
