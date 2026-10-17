# Device

A dashboard for the NanoKVM itself, with QR codes so a phone can connect in
one scan.

- **System**: CPU load (with a two-minute history), SoC temperature, memory,
  disk, load average, uptime and hostname.
- **Network**: Wi-Fi network, signal strength, band, channel and link rate.
  Also the address and state of each interface (`wlan0`, the `usb0` network to
  the target, Tailscale), whether the target computer has the USB gadget
  connected, and whether keyboard/mouse emulation is on.
- **QR pages**: the web UI (`https://<current IP>`), the Tailscale address
  when Tailscale is up, an optional Wi-Fi join code, and any extra links you
  configure.

Swipe up/down, or tap the footer arrows, to change pages.

| Env | Default | Meaning |
| --- | --- | --- |
| `WIFI_PASSWORD` | empty (secret) | Adds a Wi-Fi join QR code when set |
| `WIFI_SSID` | current network | Network for the Wi-Fi QR code |
| `WIFI_SECURITY` | `WPA` | `WPA`, `WEP` or `nopass` |
| `WEB_UI_URL` | `https://<IP>` | Override the web UI link, for example a DNS name |
| `QR_LINKS` | empty | Extra QR pages: `Dashy=http://raspberrypi.local:4000, https://example.com` |

The QR codes come from a small built-in encoder (`qr.py`, byte mode,
versions 1–10), so a link can be up to about 210 characters.

## Tests

```sh
python3 -m unittest discover -s device-dashboard -p 'test_*.py'
```
