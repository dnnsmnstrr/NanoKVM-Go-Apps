#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: NANOKVM_HOST=root@DEVICE_IP $0 APP_DIRECTORY" >&2
  exit 2
fi

if [[ -z "${NANOKVM_HOST:-}" ]]; then
  echo "Set NANOKVM_HOST, for example root@192.168.178.83" >&2
  exit 2
fi

app_dir="$1"
if [[ ! -d "$app_dir" || ! -f "$app_dir/app.json" || ! -f "$app_dir/main.py" ]]; then
  echo "APP_DIRECTORY must contain app.json and main.py: $app_dir" >&2
  exit 2
fi

app_name="$(basename "$app_dir")"
scp -r "$app_dir" "$NANOKVM_HOST:/kvmcomm/apps/"
echo "Updated $app_name in place; its NanoKVM environment was left untouched."
