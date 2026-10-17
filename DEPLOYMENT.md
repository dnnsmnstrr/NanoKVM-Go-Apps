# NanoKVM connection and App deployment

This repository contains the NanoKVM Go App catalog. The device currently
advertised for this checkout is:

- Device IP: `192.168.178.83`
- Web UI: [https://192.168.178.83](https://192.168.178.83)
- Official quick-start guide: [Sipeed NanoKVM Go Quick Start](https://wiki.sipeed.com/hardware/en/kvm/NanoKVM_Go/quick_start.html)
- SSH user used by the repository's deployment notes: `root`
- Device App directory: `/kvmcomm/apps`
- Expected shared SDK files: `/kvmcomm/apps/appbase.py` and
  `/kvmcomm/apps/appbase.pyi`

## Connection status checked on 2026-10-17

- HTTPS responded successfully and served the NanoKVM web UI.
- SSH port 22 responded at `192.168.178.83`.
- `root@192.168.178.83` was rejected because this machine did not provide an
  accepted SSH key/password: `Permission denied (publickey,password,keyboard-interactive)`.
- The official quick-start guide documents the initial web UI login as
  username `admin`, password `admin`. That login succeeded at this address.
- The web App API requires the authenticated NanoKVM web session; unauthenticated
  requests return `401 unauthorized`.
- The older address in `_utils/record-nanokvm-fb0.sh`, `root@192.168.2.10`,
  was not reachable from the current network. Use the current IP above.

The complete `bad-apple` App was inspected and installed through the web API.
The post-install App list contains `bad-apple` with manifest
`com.sipeed.bad_apple`. `hello-world` was already installed before this check.
The `macro-pad` App was also installed successfully. It currently has only
the local MCP URL configured; set its protected `NANOKVM_MCP_KEY` environment
value before expecting buttons to send keys.
Do not put a NanoKVM password, private key, or web session cookie in this
repository. Change the default `admin` password after the first login, as
recommended by Sipeed.

## SSH deployment (recommended for development)

First verify that the supplied key is accepted. Replace `KEY` only if the
device was configured with a dedicated key:

```sh
ssh -i KEY -o IdentitiesOnly=yes root@192.168.178.83 \
  'hostname; uname -a; ls -ld /kvmcomm/apps'
```

The App SDK is maintained on the repository's `base` branch, while this
checkout is the catalog branch. Copy the SDK from the local Git object store
to a temporary file, then upload it together with one complete App directory:

```sh
git show origin/base:appbase.py > /tmp/nanokvm-appbase.py
git show origin/base:appbase.pyi > /tmp/nanokvm-appbase.pyi

scp -i KEY -o IdentitiesOnly=yes \
  /tmp/nanokvm-appbase.py /tmp/nanokvm-appbase.pyi \
  root@192.168.178.83:/kvmcomm/apps/

scp -i KEY -o IdentitiesOnly=yes -r device-dashboard \
  root@192.168.178.83:/kvmcomm/apps/
```

For Memes, upload the complete directory so `clips/` and `assets/` (including
the 1.6 MiB `assets/bad-apple.bin`) are preserved:

```sh
scp -i KEY -o IdentitiesOnly=yes -r memes \
  root@192.168.178.83:/kvmcomm/apps/
```

Then verify the device-side files:

```sh
ssh -i KEY -o IdentitiesOnly=yes root@192.168.178.83 \
  'find /kvmcomm/apps/device-dashboard -maxdepth 2 -type f -print; \
   find /kvmcomm/apps/memes -maxdepth 2 -type f -print'
```

The NanoKVM Go host rescans direct child App directories automatically. Allow
up to 10 seconds, then open **Settings > Apps**. An App directory must contain
`main.py` and a valid `app.json`; the directory name must match the final
component of `app_id` with hyphens converted to underscores.

### Updating an installed App

The NanoKVM firmware currently does not reliably preserve an App's effective
environment when its installed directory is copied over SSH. Use the tested
remove/reinstall workflow for updates, then re-enter protected values such as
`NANOKVM_MCP_KEY` in **Settings > Apps > Installed > Environment**.

An in-place updater is still available for experiments, but it is not the
recommended workflow because the device may reset or stop using the existing
environment after it rescans `app.json`:

```sh
NANOKVM_HOST=root@192.168.178.83 \
  ./_utils/update-app-in-place.sh macro-pad
```

Use the SSH key options from the deployment examples if required by the
device. The updater relies on SSH access; if SSH is not enabled or the key is
not accepted, use the web UI only for a first install and configure the
environment again after a remove/reinstall.

The reliable workflow is: create a ZIP with one top-level App directory,
remove the old App in the web UI, upload/install the ZIP, and restore the
protected environment values.

For the Macro Pad development loop, use the repository helper:

```sh
./_utils/deploy-macro-pad.sh
```

It uses the authenticated cookie at `/tmp/nanokvm-cookie2` by default and
deploys to `https://192.168.178.83`. Override those with `NANOKVM_COOKIE_FILE`
and `NANOKVM_URL` when needed.

## Web UI deployment

The device web UI has an authenticated **Settings > Apps > Installed > Upload**
flow. The upload is a ZIP with exactly one top-level App directory, for
example:

```sh
zip -r /tmp/device-dashboard.zip device-dashboard -x '*/__pycache__/*'
```

Log in at [https://192.168.178.83](https://192.168.178.83) using the initial
credentials documented by Sipeed (`admin` / `admin`), select the ZIP in
**Settings > Apps**, inspect the manifest, and install it. Change the password
afterward. The App API used by the UI is:

- `GET /api/apps` — list installed Apps
- `POST /api/apps/inspect` — inspect an uploaded ZIP
- `POST /api/apps/install/stream` — install the inspected upload
- `DELETE /api/apps/{app_id}` — remove an App

The browser session supplies authentication; do not copy its cookies into
shell history or this repository. The shared `appbase.py` and `appbase.pyi`
must already be installed on the device for these Apps.

## Local validation before upload

```sh
python3 -m json.tool memes/app.json >/dev/null
python3 -m py_compile memes/*.py memes/clips/*.py
```

`memes/assets/bad-apple.bin` is required for the Bad Apple meme; upload the
whole `memes` directory, not only `memes/main.py`.

## Macro Pad configuration

The prototype is in [`macro-pad/`](./macro-pad/). It uses the NanoKVM MCP
`press_keys` tool to send key combinations to the USB-connected target. Edit
[`macro-pad/buttons.json`](./macro-pad/buttons.json) to change the four
buttons, then create a ZIP and remove/reinstall the App. Re-enter the MCP key
after installation; this is currently required by the device workflow.

After installation, open **Settings > Apps > Installed**, edit Macro Pad's
environment, and set `NANOKVM_MCP_KEY` to the key shown under **Settings > AI >
MCP Service**. The App can be launched before the key is configured, but it
will display `SET MCP KEY` and will not send input. Keep the key out of source
files and ZIP archives.

## Useful device checks after authentication

```sh
ssh -i KEY -o IdentitiesOnly=yes root@192.168.178.83 \
  'cat /kvmcomm/apps/appbase.py | head -20; \
   find /kvmcomm/apps -maxdepth 2 -name app.json -print | sort; \
   ls -lh /kvmcomm/apps/memes/assets/bad-apple.bin'
```

Launch Apps from the NanoKVM Apps page rather than manually running
`main.py`; the host owns framebuffer/touch setup, orientation, and the reserved
edge-swipe exit gesture.
