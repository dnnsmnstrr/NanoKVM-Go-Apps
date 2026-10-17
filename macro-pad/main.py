#!/usr/bin/env python3
"""Four-button NanoKVM MCP macro pad."""

from __future__ import annotations

import json
import ssl
import time
import urllib.request
from pathlib import Path

from appbase import DOWN, UP, WHITE, Rect, app, rgb565


BUTTONS_PATH = Path(__file__).with_name("buttons.json")
BG = rgb565(10, 12, 18)
BUTTON = rgb565(34, 40, 52)
BUTTON_ACTIVE = rgb565(34, 104, 76)
BORDER = rgb565(84, 96, 116)
ICON = rgb565(255, 205, 90)
SUBTLE = rgb565(150, 160, 175)

# The SDK's built-in font is ASCII-only. These aliases render common emoji as
# small pixel icons while keeping the App dependency-free.
ICON_ALIASES = {
    "🖥": "screen", "📋": "clipboard", "📎": "clip", "💾": "save",
    "🚀": "rocket", "🎵": "music", "💡": "bulb", "▶": "play",
    "⚙": "gear", "🌐": "globe", "🔒": "lock", "💬": "chat",
    "←": "arrow_left", "→": "arrow_right", "↵": "enter", "⇥": "tab",
    "⏸": "pause", "✅": "check", "✓": "check", "❌": "cross", "✕": "cross",
    "🎙": "mic", "🎤": "mic",
    "↑": "arrow_up", "↓": "arrow_down",
    "ArrowLeft": "arrow_left", "ArrowRight": "arrow_right",
    "ArrowUp": "arrow_up", "ArrowDown": "arrow_down",
}
ICONS = {
    "screen": ("01111110", "01000010", "01000010", "01111110", "00011000", "00011000", "00111100", "00000000"),
    "clipboard": ("00111100", "00100100", "01111110", "01000010", "01000010", "01000010", "01111110", "00000000"),
    "clip": ("00011000", "00100100", "01000010", "01000010", "00111100", "00011000", "00011000", "00000000"),
    "save": ("01111110", "01000010", "01011010", "01000010", "01000010", "01011010", "01111110", "00000000"),
    "rocket": ("00011000", "00111100", "01111110", "00111100", "01111110", "00011000", "00100100", "00000000"),
    "music": ("00001100", "00001100", "00001100", "00001100", "00111100", "01111100", "00111000", "00000000"),
    "bulb": ("00011000", "00111100", "01111110", "01111110", "00111100", "00011000", "00011000", "00000000"),
    "play": ("01000000", "01100000", "01111000", "01111110", "01111000", "01100000", "01000000", "00000000"),
    "gear": ("00100100", "00011000", "01111110", "00111100", "01111110", "00011000", "00100100", "00000000"),
    "globe": ("00111100", "01000010", "10011001", "10111101", "10111101", "10011001", "01000010", "00111100"),
    "lock": ("00111100", "01000010", "01000010", "01111110", "01000010", "01000010", "01111110", "00000000"),
    "chat": ("00111100", "01000010", "01011010", "01011010", "01000010", "01000010", "00111100", "00000000"),
    "arrow_left": ("00010000", "00110000", "01110000", "11111111", "01110000", "00110000", "00010000", "00000000"),
    "arrow_right": ("00010000", "00001100", "00001110", "11111111", "00001110", "00001100", "00010000", "00000000"),
    "arrow_up": ("00010000", "00111000", "01111100", "11111110", "00010000", "00010000", "00010000", "00000000"),
    "arrow_down": ("00010000", "00010000", "00010000", "11111110", "01111100", "00111000", "00010000", "00000000"),
    "enter": ("00000000", "00000010", "00000010", "00111110", "01000010", "01000010", "00111100", "00000000"),
    "tab": ("00000000", "01111110", "01011010", "01011010", "01011010", "01011010", "01111110", "00000000"),
    "pause": ("01100110", "01100110", "01100110", "01100110", "01100110", "01100110", "01100110", "00000000"),
    "check": ("00000000", "00000001", "00000011", "10000110", "11001100", "01111000", "00110000", "00000000"),
    "cross": ("11000011", "11100111", "01111110", "00111100", "00111100", "01111110", "11100111", "11000011"),
    "mic": ("00011000", "00111100", "00111100", "00111100", "00011000", "01111110", "00011000", "00000000"),
}


def validate_buttons(buttons):
    if not isinstance(buttons, list) or len(buttons) != 4:
        raise ValueError("each Macro Pad page must contain exactly four buttons")
    for button in buttons:
        if not isinstance(button, dict) or not isinstance(button.get("label"), str):
            raise ValueError("each button needs a string label")
        if "text" in button:
            if not isinstance(button["text"], str) or not button["text"]:
                raise ValueError("text buttons need non-empty text")
        else:
            keys = button.get("keys")
            if not isinstance(keys, list) or not keys or not all(isinstance(k, str) and k for k in keys):
                raise ValueError("each key button needs a non-empty keys array")
            repeat = button.get("repeat", 1)
            if not isinstance(repeat, int) or repeat < 1 or repeat > 3:
                raise ValueError("button repeat must be an integer from 1 to 3")


def load_buttons():
    with BUTTONS_PATH.open("r", encoding="utf-8") as stream:
        config = json.load(stream)
    if not isinstance(config, dict):
        raise ValueError("buttons.json must contain a configuration object")
    title = config.get("title", "MACRO PAD")
    modifier = config.get("modifier", "MetaLeft")
    if not isinstance(title, str) or not title:
        raise ValueError("buttons.json title must be a non-empty string")
    if modifier not in ("MetaLeft", "ControlLeft"):
        raise ValueError("modifier must be MetaLeft or ControlLeft")
    configured_pages = config.get("pages")
    if configured_pages is None:
        # Keep the original one-page format working.
        buttons = config.get("buttons")
        validate_buttons(buttons)
        pages = [{"name": "", "buttons": buttons}]
    else:
        if not isinstance(configured_pages, list) or not configured_pages:
            raise ValueError("pages must be a non-empty array")
        pages = []
        for page in configured_pages:
            if not isinstance(page, dict):
                raise ValueError("each page must be an object")
            name = page.get("name", "")
            if not isinstance(name, str):
                raise ValueError("page names must be strings")
            buttons = page.get("buttons")
            validate_buttons(buttons)
            pages.append({"name": name, "buttons": buttons})
    return title, modifier, pages


def load_dotenv():
    """Load simple KEY=value settings bundled beside the App for development."""
    values = {}
    env_path = BUTTONS_PATH.with_name(".env")
    if not env_path.is_file():
        return values
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            values[key] = value
    return values


class MCPClient:
    """Small dependency-free MCP streamable-HTTP client for press_keys."""

    def __init__(self, url, api_key):
        self.url = url
        self.api_key = api_key
        self.session_id = ""
        self.request_id = 0
        self.ssl_context = ssl._create_unverified_context()

    def _request(self, method, params=None, initialize=False, notification=False):
        self.request_id += 1
        payload = {"jsonrpc": "2.0", "method": method}
        if not notification:
            payload["id"] = self.request_id
        if params is not None:
            payload["params"] = params
        headers = {
            "Authorization": "Bearer " + self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if not initialize:
            headers["Mcp-Session-Id"] = self.session_id
        request = urllib.request.Request(
            self.url, json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
        )
        with urllib.request.urlopen(request, context=self.ssl_context, timeout=8) as response:
            if initialize:
                self.session_id = response.headers.get("Mcp-Session-Id", "")
                if not self.session_id:
                    raise RuntimeError("MCP returned no session ID")
            body = response.read().decode("utf-8")
        for line in body.splitlines():
            if line.startswith("data:"):
                body = line[5:].strip()
                break
        if notification and not body.strip():
            return None
        result = json.loads(body)
        if result.get("error"):
            raise RuntimeError("MCP: " + str(result["error"]))
        return result.get("result")

    def initialize(self):
        self._request("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "nanokvm-macro-pad", "version": "0.1.7"},
        }, initialize=True)
        self._request("notifications/initialized", {}, notification=True)
        result = self._request("tools/list") or {}
        names = {tool.get("name") for tool in result.get("tools", [])}
        if "press_keys" not in names:
            raise RuntimeError("MCP press_keys tool unavailable")

    def press_keys(self, keys):
        result = self._request("tools/call", {
            "name": "press_keys", "arguments": {"keys": keys}
        })
        if result and result.get("isError"):
            content = result.get("content", [{}])
            raise RuntimeError(content[0].get("text", "press_keys failed"))

    def type_text(self, text):
        result = self._request("tools/call", {
            "name": "type_text", "arguments": {"text": text}
        })
        if result and result.get("isError"):
            content = result.get("content", [{}])
            raise RuntimeError(content[0].get("text", "type_text failed"))


def button_layout(ctx):
    margin_x, gap = 16, 12
    top, bottom, gap_y = 28, 44, 12
    width = (ctx.width - 2 * margin_x - gap) // 2
    height = (ctx.height - top - bottom - gap_y) // 2
    return [
        Rect(margin_x, top, width, height),
        Rect(margin_x + width + gap, top, width, height),
        Rect(margin_x, top + height + gap_y, width, height),
        Rect(margin_x + width + gap, top + height + gap_y, width, height),
    ]


def page_nav_layout(ctx):
    y = ctx.height - 30
    return Rect(16, y, 72, 24), Rect(ctx.width - 88, y, 72, 24)


def page_indicator_rect(ctx):
    return Rect(ctx.width // 2 - 32, ctx.height - 30, 64, 24)


def page_picker_layout(ctx, pages):
    row_height = 36
    top = 28
    panel_height = min(ctx.height - top - 36, row_height * len(pages) + 8)
    panel = Rect(16, top, ctx.width - 32, panel_height)
    rows = []
    for index, _page in enumerate(pages):
        rows.append(Rect(panel.x + 4, panel.y + 4 + index * row_height, panel.w - 8, row_height - 6))
    return panel, rows


def draw_icon(fb, button, rect):
    icon_value = button.get("icon", "")
    icon = ICON_ALIASES.get(icon_value, icon_value)
    if len(icon_value) == 1 and icon_value.isascii() and icon_value.isprintable():
        fb.text_center(rect.cx, rect.y + 12, icon_value, ICON, 3)
        return
    rows = button.get("icon_rows") or ICONS.get(icon)
    if not rows:
        return
    scale = 3
    width = max(len(row) for row in rows)
    x0 = rect.cx - width * scale // 2
    y0 = rect.y + 10
    for row_index, row in enumerate(rows):
        for column, value in enumerate(row):
            if value in ("1", "#", "X"):
                fb.fill_rect(x0 + column * scale, y0 + row_index * scale, scale, scale, ICON)


def draw(ctx, title, version, page, page_index, page_count, active, message, pages=None, picker=False):
    fb = ctx.fb
    fb.clear(BG)
    header_margin = 16
    fb.draw_text(header_margin, 14, title[:24], WHITE, 1)
    version_text = "v" + version
    fb.draw_text(ctx.width - fb.text_width(version_text, 1) - header_margin, 14, version_text, SUBTLE, 1)
    buttons = page["buttons"]
    for index, (button, rect) in enumerate(zip(buttons, button_layout(ctx))):
        bg = BUTTON_ACTIVE if index == active else BUTTON
        fb.fill_rect(rect.x, rect.y, rect.w, rect.h, bg)
        fb.draw_line(rect.x, rect.y, rect.x + rect.w - 1, rect.y, BORDER)
        fb.draw_line(rect.x, rect.y, rect.x, rect.y + rect.h - 1, BORDER)
        fb.draw_line(rect.x + rect.w - 1, rect.y, rect.x + rect.w - 1, rect.y + rect.h - 1, BORDER)
        fb.draw_line(rect.x, rect.y + rect.h - 1, rect.x + rect.w - 1, rect.y + rect.h - 1, BORDER)
        draw_icon(fb, button, rect)
        label = button["label"]
        fb.text_center(rect.cx, rect.y + rect.h - 14, label, WHITE, 1)
    if page_count > 1:
        previous, next_page = page_nav_layout(ctx)
        for rect, direction in ((previous, -1), (next_page, 1)):
            # Keep the full rect as a generous invisible hit target; only the
            # small centered chevron is shown.
            if direction < 0:
                fb.draw_line(rect.cx + 5, rect.y + 5, rect.cx - 4, rect.y + 12, WHITE)
                fb.draw_line(rect.cx - 4, rect.y + 12, rect.cx + 5, rect.y + 19, WHITE)
            else:
                fb.draw_line(rect.cx - 5, rect.y + 5, rect.cx + 4, rect.y + 12, WHITE)
                fb.draw_line(rect.cx + 4, rect.y + 12, rect.cx - 5, rect.y + 19, WHITE)
        page_text = "%d/%d" % (page_index + 1, page_count)
        fb.text_center(ctx.width // 2, ctx.height - 22, page_text, SUBTLE, 1)
    if message:
        fb.text_center(ctx.width // 2, ctx.height - 12, message[:28], SUBTLE, 1)
    if picker and pages:
        panel, rows = page_picker_layout(ctx, pages)
        fb.fill_rect(panel.x, panel.y, panel.w, panel.h, BG)
        fb.draw_line(panel.x, panel.y, panel.x + panel.w - 1, panel.y, BORDER)
        fb.draw_line(panel.x, panel.y, panel.x, panel.y + panel.h - 1, BORDER)
        fb.draw_line(panel.x + panel.w - 1, panel.y, panel.x + panel.w - 1, panel.y + panel.h - 1, BORDER)
        fb.draw_line(panel.x, panel.y + panel.h - 1, panel.x + panel.w - 1, panel.y + panel.h - 1, BORDER)
        for index, (page_item, row) in enumerate(zip(pages, rows)):
            row_bg = BUTTON_ACTIVE if index == page_index else BUTTON
            fb.fill_rect(row.x, row.y, row.w, row.h, row_bg)
            label = page_item["name"] or "Page %d" % (index + 1)
            fb.draw_text(row.x + 10, row.y + 10, label[:24], WHITE, 1)
    fb.flush()


def error_status(exc):
    text = str(exc).replace("\n", " ").replace("'", "")
    if "HTTP Error 401" in text:
        return "ERR MCP KEY"
    if "HTTP Error 404" in text:
        return "ERR MCP PATH"
    if "timed out" in text.lower():
        return "ERR TIMEOUT"
    text = "ERR " + text.upper()
    return text[-28:]


@app()
def main(ctx):
    title, modifier, pages = load_buttons()
    with BUTTONS_PATH.with_name("app.json").open("r", encoding="utf-8") as stream:
        version = json.load(stream).get("version", "?")
    active = None
    page_index = 0
    page_picker = False
    message = "READY"
    client = None
    bundled_env = load_dotenv()
    api_key = (ctx.env.get("NANOKVM_MCP_KEY") or bundled_env.get("NANOKVM_MCP_KEY", "")).strip()
    mcp_url = (ctx.env.get("NANOKVM_MCP_URL") or bundled_env.get(
        "NANOKVM_MCP_URL", "https://127.0.0.1/api/mcp"
    )).strip()

    if api_key:
        message = "CONNECTING"
        draw(ctx, title, version, pages[page_index], page_index, len(pages), active, message, pages, page_picker)
        try:
            client = MCPClient(mcp_url, api_key)
            client.initialize()
            message = "READY"
        except Exception as exc:
            message = error_status(exc)
            print("Macro Pad MCP initialization failed:", exc)
    else:
        message = "SET MCP KEY"
    draw(ctx, title, version, pages[page_index], page_index, len(pages), active, message, pages, page_picker)

    def change_page(direction):
        nonlocal page_index, message, page_picker
        if direction > 0:
            page_index = (page_index + 1) % len(pages)
        else:
            page_index = (page_index - 1) % len(pages)
        message = ""
        page_picker = False
        draw(ctx, title, version, pages[page_index], page_index, len(pages), None, message, pages, page_picker)

    def on_tap(x, y):
        nonlocal active, message, page_index, page_picker
        if len(pages) > 1 and page_picker:
            panel, rows = page_picker_layout(ctx, pages)
            selected = next((i for i, rect in enumerate(rows) if rect.contains(x, y)), None)
            if selected is not None:
                page_index = selected
            page_picker = False
            message = ""
            draw(ctx, title, version, pages[page_index], page_index, len(pages), None, message, pages, page_picker)
            return
        if len(pages) > 1 and page_indicator_rect(ctx).contains(x, y):
            page_picker = True
            draw(ctx, title, version, pages[page_index], page_index, len(pages), None, "", pages, page_picker)
            return
        if len(pages) > 1:
            previous, next_page = page_nav_layout(ctx)
            if previous.contains(x, y):
                change_page(-1)
                return
            if next_page.contains(x, y):
                change_page(1)
                return
        buttons = pages[page_index]["buttons"]
        index = next((i for i, rect in enumerate(button_layout(ctx)) if rect.contains(x, y)), None)
        if index is None:
            return
        active = index
        draw(ctx, title, version, pages[page_index], page_index, len(pages), active, "SENDING", pages, page_picker)
        if client is None:
            message = "NO MCP CONNECTION"
        else:
            try:
                button = buttons[index]
                if "text" in button:
                    client.type_text(button["text"])
                else:
                    keys = [modifier if key == "@MOD" else key for key in button["keys"]]
                    for repeat_index in range(button.get("repeat", 1)):
                        if repeat_index:
                            time.sleep(0.08)
                        client.press_keys(keys)
                message = "SENT: " + button["label"]
            except Exception as exc:
                message = error_status(exc)
                print("Macro Pad press_keys failed:", exc)
        time.sleep(0.15)
        active = None
        draw(ctx, title, version, pages[page_index], page_index, len(pages), active, message, pages, page_picker)

    def on_swipe(kind, _x, _y):
        nonlocal page_index, message
        if len(pages) == 1:
            return
        if kind == UP:
            change_page(1)
        elif kind == DOWN:
            change_page(-1)

    ctx.run(lambda _dt: True, fps=10, on_tap=on_tap, on_swipe=on_swipe)


if __name__ == "__main__":
    main()
