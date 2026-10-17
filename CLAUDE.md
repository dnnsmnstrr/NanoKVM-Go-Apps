# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

This checkout is the **catalog branch** (`main`) of NanoKVM Go Apps: the App
store list shown under **Settings > Apps > Store** on a Sipeed NanoKVM Go. Each
top-level directory (other than `_utils/` and `_lib/`) is one self-contained App
that runs on the device's touchscreen in Python.

The shared SDK (`appbase.py`, `appbase.pyi`) and the official development
guide are **not on this branch**. They live on `origin/base`. Read them with:

```sh
git show origin/base:appbase.pyi     # public API contract
git show origin/base:appbase.py
git show origin/base:README.md       # official App development guide
```

`appbase` is only importable on the device (`/kvmcomm/apps/appbase.py`), so
Apps cannot be run locally.

## App structure and SDK model

Each App directory needs `main.py` plus a valid `app.json`. The directory name
must match the last component of `app_id` with `_` turned into `-` (for example
`com.example.macro_pad` → `macro-pad/`). The App is addressed by its directory
name in the device API (`DELETE /api/apps/macro-pad`).

`app.json` fields: `app_id`, `name`, `creator`, `create_time`, `version`,
`desc`, optional `category`, an optional `env` map (each entry has `label`,
`description`, `required`, `default`, `secret`) that the host shows as editable
settings, and optional `pre_script` (an install hook such as
`voice-bridge/pre-install.sh`, which gets `$NANOKVM_APP_DIR`).

Runtime pattern shared by every `main.py`:

- `@app()` decorates `main(ctx: AppContext)`. The host opens and closes the
  framebuffer and touch devices, sets orientation, and owns the reserved
  left-edge swipe exit gesture. Do not launch `main.py` by hand on the device.
- `ctx.run(tick, fps=..., on_tap=..., on_swipe=...)` drives the frame loop.
  `tick(dt)` redraws through `ctx.fb` (an RGB565 framebuffer with `fill_rect`,
  `draw_text`, `text_center`, `draw_sprite`, and so on).
- `ctx.env` is the Mapping of the App's configured `env` values.
- The built-in font is 8x8 and **ASCII-only**. Non-ASCII text (Chinese, emoji)
  must be pre-rendered bitmaps (see the emoji-to-pixel-icon map in
  `macro-pad/main.py`). `memes/engine.py` adds a few punctuation glyphs
  (`! ' ? , + * < > &`) through its own `draw_text`.
- The framebuffer is physically 240x284 (stride 480), so at the usual rotation
  90 Apps get a **landscape 284x240** canvas. The SDK README's portrait tables
  do not match this device. Layouts must adapt to `ctx.width`/`ctx.height`.
- A calibration photo (2026-10-18) showed the whole 284x240 canvas: the
  SDK's "14 px hidden strip" applies only to panels that are physically
  284x240, not to this one. The panel has rounded corners of 46 px
  radius (`CORNER_RADIUS = 46`, fitted from the photo's corner curves). Lay out against `kvmkit.screen.Layout`
  (`visible_rect()`, `safe_span()`), never the raw canvas, so text near the
  top and bottom edges stays clear of the corners. `_lib/kvmkit/screen.py`
  is the single place to correct the geometry.
- Drawing is pure Python: `fill_rect` along the physically contiguous axis
  (columns at the usual 90°/270° rotation) is cheap, a horizontal line costs
  one write per column, and text is drawn pixel by pixel. Redraw only when
  something changed, and measure on the device.
- Horizontal swipes are reserved for the host's exit gesture. Use taps or
  up/down swipes for App navigation.

Apps that send keyboard input to the USB-connected target computer (`macro-pad`,
`voice-bridge`) call the device's local NanoKVM MCP service
(`https://127.0.0.1/api/mcp`, tool `press_keys`, browser-style key names like
`MetaLeft` and `KeyA`). They need the protected `NANOKVM_MCP_KEY` env value from
**Settings > AI > MCP Service**. They never touch `/dev/hidg*` directly.

## Shared code: kvmkit

`_lib/kvmkit/` is the master copy of the shared library: `screen` (visible
area, rounded corners, `Layout`), `pager` (pagination with header and footer),
`text` (8x8 font helpers), `theme` (colours), `env` (setting parsers) and
`net` (mDNS for `.local` names). Apps install as self-contained ZIPs, so each
App that imports `kvmkit` carries a generated copy in `<app>/kvmkit/`. Never
edit those copies. Edit `_lib/kvmkit/`, then run:

```sh
python3 _utils/sync-kvmkit.py          # update every App's copy
python3 _utils/sync-kvmkit.py --check  # fails if a copy is stale
```

The script finds Apps by their `import kvmkit` / `from kvmkit` lines. Home
Assistant, Homelab and Device use its layout, pager, text and env helpers;
Memes uses its screen geometry. Macro Pad still has its own helpers.

## Validation and tests

There is no build step or linter. Before uploading, check the changed App:

```sh
python3 -m json.tool <app>/app.json >/dev/null
python3 -m py_compile <app>/main.py
```

Unit tests live in `_lib/` (kvmkit, including the stale-copy check),
`voice-bridge/`, `macro-pad/`, `homelab-status/`, `device-dashboard/`,
`home-assistant/` and `memes/`.
They stub `appbase` (and, for `voice-bridge`, `aiortc`, `av` and `websockets`)
in `sys.modules`, so they run off-device:

```sh
python3 -m unittest discover -s _lib -p 'test_*.py'
python3 -m unittest discover -s voice-bridge -p 'test_*.py'
python3 -m unittest discover -s voice-bridge -p 'test_*.py' -k test_latest_app_manifest
python3 -m unittest discover -s macro-pad -p 'test_*.py'
python3 -m unittest discover -s homelab-status -p 'test_*.py'
python3 -m unittest discover -s device-dashboard -p 'test_*.py'
python3 -m unittest discover -s home-assistant -p 'test_*.py'
python3 -m unittest discover -s memes -p 'test_*.py'
```

User configuration goes through `env` so nobody has to rebuild a ZIP:
`macro-pad` reads `MACRO_PAD_CONFIG` (JSON or a URL to JSON) and falls back to
`buttons.json`; `homelab-status` reads `HOMELAB_SERVICES`, then `DASHY_URL`,
then a gitignored `homelab-status/conf.yml`. Env fields in the web UI are
single-line inputs, so env-carried config must work as one-line JSON. Do not
commit `homelab-status/conf.yml`.

## Deploying to the device

See `DEPLOYMENT.md` for the full procedure. It covers the device IP, the web App
API (`/api/apps`, `/api/apps/inspect`, `/api/apps/install/stream`), and SSH
`scp` to `/kvmcomm/apps/`. Key points:

- Upload a ZIP that contains exactly one top-level App directory.
- To update an App, **remove and reinstall** it. Copying over SSH in place
  (`_utils/update-app-in-place.sh`) does not reliably keep the App's
  environment. Protected values such as `NANOKVM_MCP_KEY` must be entered
  again after a reinstall.
- Macro Pad dev loop: `./_utils/deploy-macro-pad.sh`. It zips the App, then
  inspects, deletes, and installs it through the web API. It uses an
  authenticated session cookie (default `/tmp/nanokvm-cookie2`; override with
  `NANOKVM_COOKIE_FILE` / `NANOKVM_URL`).
- `memes` must be uploaded with `assets/bad-apple.bin` (regenerate it with
  `memes/tools/pack_frames.py`). New memes are files in `memes/clips/` or
  GIFs converted with `memes/tools/gif_to_meme.py` into `memes/assets/`.
- `_utils/record-nanokvm-fb0.sh` records the device framebuffer to MP4 over SSH
  with ffmpeg. Its default host is outdated; set `NANOKVM_HOST`.

## Conventions

- For `macro-pad` changes, bump the patch `version` in `macro-pad/app.json`.
  The version is drawn in the App header, which confirms that a new build is
  running on the device.
- `macro-pad/buttons.json` is validated at startup by `load_buttons()` /
  `validate_buttons()`: exactly four buttons per page, `repeat` 1–3, `@MOD`
  expands to the configured `modifier`. Keep `macro-pad/README.md` in sync when
  you add button fields or icon aliases.
- `macro-pad` falls back to a bundled `macro-pad/.env` for development. Any ZIP
  that includes it bakes the MCP key into the App. `.env` files are gitignored.
  Never commit keys, device passwords, or web session cookies.
