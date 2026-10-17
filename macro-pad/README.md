# Macro Pad

`macro-pad` turns the NanoKVM Go touchscreen into a multi-page, four-button
Stream Deck-style controller. Each button calls NanoKVM MCP's `press_keys`
tool, so the keypress is sent to the USB-connected target computer.

## Configure buttons

Edit [`buttons.json`](./buttons.json), then remove and reinstall the App.
The configuration object contains:

- `title`: the small header title shown on the screen;
- `modifier`: `MetaLeft` for macOS Command, or `ControlLeft` for Windows/Linux;
- `buttons`: exactly four button definitions in the original one-page format;
  use `pages` for multiple pages.

Each `pages` entry contains:

- `name`: optional page name shown below the header;
- `buttons`: exactly four button definitions.

Tap the `<` and `>` controls at the bottom of the screen to move between
pages. These are the reliable navigation method. Swipe up/down is also
supported when the NanoKVM host reports those gestures, while horizontal
swipes remain unused because they are reserved for the app-exit gesture. Page
numbers are shown between the navigation controls. Tap the page number to
open a named page list and jump directly to a page. The original top-level
`buttons` format remains supported for one-page configurations.

After reinstalling, re-enter `NANOKVM_MCP_KEY` under the App's environment
settings. `ERR MCP KEY` means the key is missing, expired, or does not match
the key currently shown under **Settings > AI > MCP Service**.

Each button contains:

- `label`: short ASCII label drawn below the icon;
- `icon`: a built-in icon name, supported emoji alias, or single ASCII
  character; single ASCII characters are rendered directly at icon size;
- `keys`: browser-style key names sent together as one shortcut; `@MOD` is
  replaced by the configured modifier;
- `text`: optional text to type instead of sending a shortcut.

Example:

```json
{
  "label": "Save",
  "icon": "💾",
  "keys": ["@MOD", "KeyS"]
}
```

Text example:

```json
{
  "label": "Type Hello",
  "icon": "💬",
  "text": "Hello from NanoKVM"
}
```

Multi-page example:

```json
{
  "title": "MACRO PAD",
  "modifier": "MetaLeft",
  "pages": [
    {
      "name": "Clipboard",
      "buttons": [
        {"label": "Copy", "keys": ["@MOD", "KeyC"]},
        {"label": "Paste", "keys": ["@MOD", "KeyV"]},
        {"label": "Hello", "text": "Hello from NanoKVM"},
        {"label": "A", "keys": ["KeyA"]}
      ]
    },
    {
      "name": "Navigation",
      "buttons": [
        {"label": "Left", "keys": ["ArrowLeft"]},
        {"label": "Right", "keys": ["ArrowRight"]},
        {"label": "Space", "keys": ["Space"]},
        {"label": "Enter", "keys": ["Enter"]}
      ]
    }
  ]
}
```

The framebuffer's built-in font is ASCII-only, so arbitrary emoji cannot be
rendered directly as text. The prototype maps common emoji to pixel icons and
also accepts custom `icon_rows` made from `0`/`1`, `.`/`#`, or spaces. A later
version could add a bitmap font or image assets for arbitrary icons.

Built-in aliases include `←`, `→`, `↑`, `↓`, `↵`, `⇥`, `⏸`, `✅`, `✓`, `❌`,
and `✕` for directional arrows, Enter, Tab, pause, checkmark, and cross
icons. `ArrowLeft`, `ArrowRight`, `ArrowUp`, and `ArrowDown` can also be used
as icon values. `🎙` and `🎤` render as microphone icons. The corresponding key
names include `ArrowLeft`, `ArrowRight`, `ArrowUp`, `ArrowDown`, `Enter`,
`Tab`, `Space`, and `Escape`.

Buttons may set `repeat` from 1 to 3 to send a shortcut multiple times as
separate keypresses. The example Dictate button sends `ControlLeft` twice for
macOS Dictation.

## Device setup

1. Enable **Settings > AI > MCP Service** on NanoKVM Go.
2. Copy the MCP API key into the App's protected `NANOKVM_MCP_KEY` setting.
   The App can be installed before this is configured; it will show `SET MCP
   KEY` and will not send anything until a key is present.
3. Leave `NANOKVM_MCP_URL` at `https://127.0.0.1/api/mcp`.
4. Launch **Macro Pad** from the NanoKVM Apps page.

For development convenience, copy `.env.example` to `.env` in this App
directory and fill in `NANOKVM_MCP_KEY`. The App uses the NanoKVM-provided
environment first, then falls back to the bundled `.env` file. Therefore a
ZIP containing `.env` effectively bakes the key into the App. This is
convenient but less secure: anyone who can download or inspect that App can
recover the key. Keep `.env` out of Git and use the protected App environment
for shared or production installs.

MCP uses browser-style key names: `ControlLeft`, `ShiftLeft`, `AltLeft`,
`MetaLeft`, `KeyA` through `KeyZ`, `Digit1` through `Digit0`, `Enter`,
`Escape`, `Tab`, `Space`, `ArrowUp`, `ArrowDown`, `ArrowLeft`, `ArrowRight`,
and `F1` through `F12`. The remote OS and keyboard layout determine how
character keys are interpreted.

The app requires the manifest-based App SDK and a device build that exposes
the `press_keys` MCP tool. It does not access `/dev/hidg*` directly.
