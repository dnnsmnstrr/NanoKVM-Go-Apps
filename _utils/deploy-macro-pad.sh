#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
device_url="${NANOKVM_URL:-https://192.168.178.83}"
cookie_file="${NANOKVM_COOKIE_FILE:-/tmp/nanokvm-cookie2}"
temp_dir="$(mktemp -d /tmp/macro-pad-deploy.XXXXXX)"
archive="$temp_dir/macro-pad.zip"
inspect_response="$temp_dir/inspect.json"
delete_response="$temp_dir/delete.json"
install_response="$temp_dir/install.jsonl"
trap 'rm -rf "$temp_dir"' EXIT

if [[ ! -f "$cookie_file" ]]; then
  echo "Missing authenticated NanoKVM cookie: $cookie_file" >&2
  echo "Log into the NanoKVM web UI first or set NANOKVM_COOKIE_FILE." >&2
  exit 1
fi

(cd "$repo_root" && zip -qr "$archive" macro-pad)

http_code="$(curl -ksS -o "$inspect_response" -w '%{http_code}' \
  -b "$cookie_file" \
  -H "Origin: $device_url" \
  -H "Referer: $device_url/" \
  -F "file=@$archive;type=application/zip" \
  "$device_url/api/apps/inspect")"
if [[ "$http_code" != 200 ]]; then
  echo "App inspection failed (HTTP $http_code)." >&2
  cat "$inspect_response" >&2
  exit 1
fi

version="$(python3 - "$inspect_response" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as stream:
    print(json.load(stream)["data"]["manifest"]["version"])
PY
)"
echo "Deploying Macro Pad v$version to $device_url"

http_code="$(curl -ksS -o "$delete_response" -w '%{http_code}' \
  -b "$cookie_file" -X DELETE \
  -H "Origin: $device_url" \
  -H "Referer: $device_url/" \
  "$device_url/api/apps/macro-pad")"
if [[ "$http_code" != 200 ]]; then
  echo "Existing App removal failed (HTTP $http_code)." >&2
  cat "$delete_response" >&2
  exit 1
fi

http_code="$(curl -ksS -o "$install_response" -w '%{http_code}' \
  -b "$cookie_file" \
  -H "Origin: $device_url" \
  -H "Referer: $device_url/" \
  -F "file=@$archive;type=application/zip" \
  "$device_url/api/apps/install/stream")"
if [[ "$http_code" != 200 ]] || ! grep -q 'Installation completed successfully' "$install_response"; then
  echo "App installation failed (HTTP $http_code)." >&2
  cat "$install_response" >&2
  exit 1
fi

echo "Installed Macro Pad v$version successfully."
