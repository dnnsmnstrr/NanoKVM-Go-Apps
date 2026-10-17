# Home Assistant

Touch tiles for [Home Assistant](https://www.home-assistant.io). Tap a tile to
toggle a light, switch, fan, cover or input boolean, to run a scene, script or
button, or to play/pause a media player. Sensors, binary sensors, climate,
weather and people are shown read-only; tapping one opens a detail view with
its entity ID and when it last changed.

Unlocking a lock, and opening a cover whose device class is `garage`, `door`
or `gate`, needs a second tap within three seconds. The tile turns red and
shows `TAP AGAIN` in between.

## Setup

1. In Home Assistant, open your profile, go to **Security**, and create a
   **long-lived access token**.
2. On the NanoKVM, open **Settings > Apps > Installed > Home Assistant >
   Environment** and paste it into `HA_TOKEN`.
3. If Home Assistant is not reachable at `http://homeassistant.local:8123`,
   set `HA_URL`. `.local` names work: the App resolves them over mDNS itself.

| Env | Default | Meaning |
| --- | --- | --- |
| `HA_TOKEN` | empty (secret) | Long-lived access token |
| `HA_URL` | `http://homeassistant.local:8123` | Home Assistant address |
| `HA_ENTITIES` | empty | Pages of entities (see below) |
| `HA_REFRESH` | `5` | Seconds between updates of the visible tiles |

## Choosing entities

With `HA_ENTITIES` empty, the App groups available lights, switches, fans,
covers, climate devices, media players, scenes, scripts, locks and input
booleans onto one page per type.

To pick your own pages, set `HA_ENTITIES` on one line:

```text
Living: light.sofa=Sofa, switch.tv; Office: light.desk, sensor.office_temperature, climate.office
```

Pages are separated with `;`. Each entry is an entity ID, optionally with a
label as `entity_id=Label` or `Label=entity_id`. Without a label, the tile
uses the entity's friendly name. JSON works too:

```json
{"Living": {"Sofa": "light.sofa", "TV": "switch.tv"}, "Office": ["light.desk", "sensor.office_temperature"]}
```

Each screen holds six tiles; longer pages continue on the next screen.

## Controls

- Swipe up/down, or tap the footer arrows, to change pages.
- Tap the header or the middle of the footer to refresh now.
- The dot next to the clock turns red when Home Assistant cannot be reached.
  The footer shows the error, for example `HA TOKEN REJECTED`.

The 8x8 font is ASCII-only. Names are uppercased, German umlauts are
transliterated (`Küche` becomes `KUECHE`), and other non-ASCII characters are
dropped.

## Tests

```sh
python3 -m unittest discover -s home-assistant -p 'test_*.py'
```
