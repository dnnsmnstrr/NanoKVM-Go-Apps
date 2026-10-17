# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

This checkout is the **catalog branch** (`main`) of NanoKVM Go Apps: the App
store list shown under **Settings > Apps > Store** on a Sipeed NanoKVM Go. Each
top-level directory (other than `_utils/`) is one self-contained App that runs
on the device's touchscreen in Python.

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
  must be pre-rendered bitmaps (see `hello-world/main.py`'s hex rows, and the
  emoji-to-pixel-icon map in `macro-pad/main.py`).
- After 90°/270° rotation the panel hides 14 px along one edge. See
  `visible_vertical_bounds()` in `hello-world/main.py`.
- Horizontal swipes are reserved for the host's exit gesture. Use taps or
  up/down swipes for App navigation.

Apps that send keyboard input to the USB-connected target computer (`macro-pad`,
`voice-bridge`) call the device's local NanoKVM MCP service
(`https://127.0.0.1/api/mcp`, tool `press_keys`, browser-style key names like
`MetaLeft` and `KeyA`). They need the protected `NANOKVM_MCP_KEY` env value from
**Settings > AI > MCP Service**. They never touch `/dev/hidg*` directly.

## Validation and tests

There is no build step or linter. Before uploading, check the changed App:

```sh
python3 -m json.tool <app>/app.json >/dev/null
python3 -m py_compile <app>/main.py
```

The only unit tests are in `voice-bridge/`. They stub `appbase`, `aiortc`, `av`
and `websockets` in `sys.modules`, so they run off-device:

```sh
python3 -m unittest discover -s voice-bridge -p 'test_*.py'
python3 -m unittest discover -s voice-bridge -p 'test_*.py' -k test_latest_app_manifest
```

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
- `bad-apple` must be uploaded with `assets/frames.bin` (regenerate it with
  `bad-apple/tools/pack_frames.py`).
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
