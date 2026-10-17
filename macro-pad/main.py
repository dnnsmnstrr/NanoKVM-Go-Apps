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
    y = ctx.height - 24
    return Rect(16, y, 36, 16), Rect(ctx.width - 52, y, 36, 16)


def draw_icon(fb, button, rect):
    icon = ICON_ALIASES.get(button.get("icon", ""), button.get("icon", ""))
    rows = button.get("icon_rows") or ICONS.get(icon)
    if not rows:
        return
    scale = 2
    width = max(len(row) for row in rows)
    x0 = rect.cx - width * scale // 2
    y0 = rect.y + 20
    for row_index, row in enumerate(rows):
        for column, value in enumerate(row):
            if value in ("1", "#", "X"):
                fb.fill_rect(x0 + column * scale, y0 + row_index * scale, scale, scale, ICON)


def draw(ctx, title, version, page, page_index, page_count, active, message):
    fb = ctx.fb
    fb.clear(BG)
    header_margin = 16
    fb.draw_text(header_margin, 4, title[:24], WHITE, 1)
    version_text = "v" + version
    fb.draw_text(ctx.width - fb.text_width(version_text, 1) - header_margin, 4, version_text, SUBTLE, 1)
    page_text = "%d/%d" % (page_index + 1, page_count)
    fb.text_center(ctx.width // 2, 4, page_text, SUBTLE, 1)
    if page["name"]:
        fb.text_center(ctx.width // 2, 15, page["name"][:20], SUBTLE, 1)
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
        scale = 2 if fb.text_width(label, 2) <= rect.w - 10 else 1
        fb.text_center(rect.cx, rect.y + rect.h - 24, label, WHITE, scale)
    if page_count > 1:
        previous, next_page = page_nav_layout(ctx)
        for rect, label in ((previous, "<"), (next_page, ">")):
            fb.fill_rect(rect.x, rect.y, rect.w, rect.h, BUTTON)
            fb.draw_line(rect.x, rect.y, rect.x + rect.w - 1, rect.y, BORDER)
            fb.draw_line(rect.x, rect.y + rect.h - 1, rect.x + rect.w - 1, rect.y + rect.h - 1, BORDER)
            fb.text_center(rect.cx, rect.y + 4, label, WHITE, 1)
    if message:
        fb.text_center(ctx.width // 2, ctx.height - 12, message[:28], SUBTLE, 1)
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
    message = "READY"
    client = None
    api_key = ctx.env.get("NANOKVM_MCP_KEY", "").strip()
    mcp_url = ctx.env.get("NANOKVM_MCP_URL", "https://127.0.0.1/api/mcp").strip()

    if api_key:
        message = "CONNECTING"
        draw(ctx, title, version, pages[page_index], page_index, len(pages), active, message)
        try:
            client = MCPClient(mcp_url, api_key)
            client.initialize()
            message = "READY"
        except Exception as exc:
            message = error_status(exc)
            print("Macro Pad MCP initialization failed:", exc)
    else:
        message = "SET MCP KEY"
    draw(ctx, title, version, pages[page_index], page_index, len(pages), active, message)

    def change_page(direction):
        nonlocal page_index, message
        if direction > 0:
            page_index = (page_index + 1) % len(pages)
        else:
            page_index = (page_index - 1) % len(pages)
        message = "PAGE %d/%d" % (page_index + 1, len(pages))
        draw(ctx, title, version, pages[page_index], page_index, len(pages), None, message)

    def on_tap(x, y):
        nonlocal active, message
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
        draw(ctx, title, version, pages[page_index], page_index, len(pages), active, "SENDING")
        if client is None:
            message = "NO MCP CONNECTION"
        else:
            try:
                button = buttons[index]
                if "text" in button:
                    client.type_text(button["text"])
                else:
                    keys = [modifier if key == "@MOD" else key for key in button["keys"]]
                    client.press_keys(keys)
                message = "SENT: " + button["label"]
            except Exception as exc:
                message = error_status(exc)
                print("Macro Pad press_keys failed:", exc)
        time.sleep(0.15)
        active = None
        draw(ctx, title, version, pages[page_index], page_index, len(pages), active, message)

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
