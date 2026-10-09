# DreamLayer Integration

Updated 2026-10-03.

## Current status: not used

* **No credits.** DreamLayer (an AI image-generation service) was set up as a possible 2D production tool at the
  start of the project. Its account had **0 credits**, so nothing was ever generated.
* **Policy.** The user then directed that **no AI-generated imagery be used for any game or marketing image**.
  DreamLayer is therefore not part of the art pipeline and must not be used for Echoes of Aether.
* **Replacement.** All art comes from Blender pipelines that use the game's own assets: the environment kit, robots,
  MakeHuman/MPFB CC0 characters and Cycles renders. See `ART_BIBLE.md`.
* **Log.** The asset log (`DREAMLAYER_ASSET_LOG.md`) records 0 images and 0 credits used.

The setup record below is kept for reference and for cleaning up the credentials.

## Setup record (2026-10-03)

| Item | State |
|---|---|
| API key | Provided by the project owner and stored in `~/.config/dreamlayer/credentials.env`, outside the repository. File mode `600` was confirmed on 2026-10-03; the contents were not read. |
| MCP server | Registered as a **user**-scope MCP server during setup (`npx -y @dreamlayer/mcp@0.4.0-beta.5`, key passed as `DREAMLAYER_API_KEY`). This is from the original setup notes and has not been re-checked since. |
| CLI wrapper | `tools/dreamlayer/dl.sh` wraps the `dreamlayer@0.4.0-beta.4` CLI through `npx`. It reads the key from the environment or the local credentials file and pipes all output through a redaction filter for the key pattern. |
| Node requirement | Node 22.12 or later (installed: 22.20) |
| Capabilities reported at setup | `key_mode: live`; operations `text_to_image`, `image_to_image`, `background_remove`, `upscale`, `sprite_sheet`; 1 credit per image |
| Balance at setup | **0 credits** (`promotional 0`, `purchased 0`). Generation was blocked. |
| Images generated | **0** |

The `dreamlayer/` folders in the repository (`characters/kael`, `characters/lyra`, `environments`, `keyart`,
`loading`, `references`, `rejected`, `ui`) were created for the original plan and are empty.

Sources for the setup: DreamLayer documentation ([docs.dreamlayer.io/cli](https://docs.dreamlayer.io/cli),
[docs.dreamlayer.io/mcp](https://docs.dreamlayer.io/mcp), [llms.txt](https://docs.dreamlayer.io/llms.txt)) and
[github.com/TheDesignFounder/dreamlayer-mcp](https://github.com/TheDesignFounder/dreamlayer-mcp).

## Security rules (still in force)

* The key never appears in source, data, game builds, screenshots, logs or committed docs.
* `.gitignore` excludes `.env`, `.env.*`, `*.local` and `secrets/`.
* Release builds are scanned for the key pattern:
  * `node tools/validation/validate_unity.mjs` scans scripts, data, docs, tools, marketing, Blender scripts and
    `Builds/`.
  * The manual equivalent is `grep -rlE 'dlr_(live|test)_[A-Za-z0-9]{20,}' . --exclude-dir=node_modules`.
  * Both returned no matches on 2026-10-03.
* The key was shared in a chat session during setup. Rotate or revoke it in the DreamLayer console after the jam.
  Remove the MCP server registration and the local credentials file if
  DreamLayer will not be used again.

## Wrapper commands (reference only; do not use for this project's art)

```bash
tools/dreamlayer/dl.sh balance        # account balance (no credits used)
tools/dreamlayer/dl.sh capabilities   # available operations (no credits used)
```

Generation commands (`generate`, `edit`, `cutout`, `upscale`) exist in the CLI but are excluded by the no-AI-imagery
directive.
