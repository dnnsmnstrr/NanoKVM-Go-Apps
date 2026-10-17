#!/usr/bin/env python3
"""Home Assistant tile panel: toggle lights and switches, run scenes, read sensors."""

from __future__ import annotations

import datetime
import queue
import threading
import time

from appbase import WHITE, Rect, app, rgb565

import hass
from kvmkit import env as kenv, net
from kvmkit.pager import Pager
from kvmkit.screen import Layout
from kvmkit.text import ago, fit, text, wrap
from kvmkit.theme import BAD, BG, DIM, GOOD, PANEL, SUBTLE

PANEL_ON = rgb565(70, 56, 18)
ICON_OFF = rgb565(120, 130, 150)
ICON_ON = rgb565(255, 205, 90)
CONFIRM = rgb565(240, 70, 70)

HEADER_H = 30
FOOTER_H = 34
COLUMNS = 2
ROWS = 3
GAP = 6
CONFIRM_SECONDS = 3.0

ICONS = {
    "bulb": ("00111100", "01111110", "01111110", "01111110", "00111100", "00011000", "00011000", "00011000"),
    "plug": ("00100100", "00100100", "01111110", "01111110", "01111110", "00111100", "00011000", "00011000"),
    "fan": ("01100110", "11110110", "01111100", "00011000", "00111110", "01101111", "01100110", "00000000"),
    "blind": ("11111111", "10000001", "11111111", "10000001", "11111111", "10000001", "11111111", "00011000"),
    "thermo": ("00011000", "00100100", "00101100", "00100100", "00101100", "01011010", "01011010", "00111100"),
    "drop": ("00011000", "00011000", "00111100", "01111110", "01111110", "01111110", "00111100", "00000000"),
    "bolt": ("00001110", "00011100", "00111000", "01111110", "00011100", "00111000", "01110000", "01000000"),
    "battery": ("00111100", "01111110", "01000010", "01011010", "01011010", "01011010", "01111110", "00000000"),
    "gauge": ("00111100", "01000010", "10000101", "10001001", "10010001", "10000001", "01000010", "00000000"),
    "door": ("01111110", "01000010", "01000010", "01000110", "01000010", "01000010", "01111110", "00000000"),
    "person": ("00011000", "00111100", "00011000", "01111110", "00011000", "00100100", "01000010", "00000000"),
    "play": ("01000000", "01100000", "01111000", "01111110", "01111000", "01100000", "01000000", "00000000"),
    "spark": ("00011000", "00011000", "11011011", "01111110", "00111100", "01111110", "11011011", "00011000"),
    "script": ("01111110", "01000010", "01011010", "01000010", "01011010", "01000010", "01111110", "00000000"),
    "lock": ("00111100", "01000010", "01000010", "11111111", "11100111", "11100111", "11111111", "00000000"),
    "unlock": ("00111100", "01000010", "01000000", "11111111", "11100111", "11100111", "11111111", "00000000"),
    "sun": ("10011001", "01000010", "00111100", "11111111", "00111100", "01000010", "10011001", "00000000"),
    "dot": ("00000000", "00111100", "01111110", "01111110", "01111110", "01111110", "00111100", "00000000"),
}


def changed_seconds(state):
    try:
        changed = datetime.datetime.fromisoformat(state["last_changed"])
        return (datetime.datetime.now(datetime.timezone.utc) - changed).total_seconds()
    except (KeyError, TypeError, ValueError):
        return None


def paginate(config_pages, per_page):
    pages = []
    for page in config_pages:
        entities = page["entities"]
        chunks = [entities[start:start + per_page] for start in range(0, len(entities), per_page)]
        for index, chunk in enumerate(chunks):
            name = page["name"] if len(chunks) == 1 else "%s %d" % (page["name"], index + 1)
            pages.append({"name": name, "entities": chunk})
    return pages


class Panel:
    def __init__(self, ctx):
        self.ctx = ctx
        env = ctx.env
        self.layout = Layout(ctx.fb, HEADER_H, FOOTER_H)
        self.pager = Pager(self.layout)
        self.view = self.layout.view
        self.content_top = self.layout.content.y
        self.content_bottom = self.layout.footer.y
        self.refresh_seconds = kenv.number(env, "HA_REFRESH", 5, minimum=1)
        self.client = None
        token = (env.get("HA_TOKEN") or "").strip()
        url = (env.get("HA_URL") or "").strip() or "http://homeassistant.local:8123"
        if token:
            self.client = hass.HAClient(url, token)
        self.entities_config = env.get("HA_ENTITIES") or ""
        self.lock = threading.RLock()
        self.states = {}
        self.pages = []
        self.pending = {}
        self.confirm = None
        self.detail = None
        self.error = None if token else "SET HA TOKEN"
        self.loading = bool(token)
        self.updated_at = None
        self.version = 0
        self.drawn = None
        self.drawn_at = 0.0
        self.jobs = queue.Queue()
        self.stop = threading.Event()

    @property
    def page_index(self):
        return self.pager.index

    # -- background worker ------------------------------------------------------
    def start(self):
        if self.client is not None:
            threading.Thread(target=self.worker, daemon=True).start()

    def worker(self):
        while not self.stop.is_set():
            if not self.pages:
                self.load()
                if not self.pages:
                    try:
                        self.jobs.get(timeout=10)  # a tap queues a retry
                    except queue.Empty:
                        pass
                    continue
            try:
                job = self.jobs.get(timeout=self.refresh_seconds)
            except queue.Empty:
                job = ("refresh",)
            try:
                if job[0] == "call":
                    self.run_call(*job[1:])
                elif job[0] == "reload":
                    with self.lock:
                        self.pages = []
                    continue
                self.refresh_visible()
                self.set_error(None)
            except hass.HAError as exc:
                self.set_error(str(exc))
            except Exception as exc:  # keep the panel alive on unexpected data
                print("Home Assistant: worker error:", repr(exc))
                self.set_error("HA ERROR")

    def set_error(self, message):
        with self.lock:
            if message != self.error:
                self.error = message
                self.version += 1

    def load(self):
        """Build pages from HA_ENTITIES, or from discovered entities."""
        try:
            self.client.check()
            if self.entities_config.strip():
                try:
                    config_pages = hass.parse_entities_config(self.entities_config)
                except ValueError as exc:
                    print("Home Assistant: HA_ENTITIES rejected:", exc)
                    raise hass.HAError("BAD HA-ENTITIES") from exc
                states = {}
            else:
                all_states = self.client.states()
                config_pages = hass.auto_pages(all_states)
                wanted = {entity["entity_id"] for page in config_pages for entity in page["entities"]}
                states = {state["entity_id"]: state for state in all_states if state["entity_id"] in wanted}
                del all_states
            if not config_pages:
                raise hass.HAError("NO ENTITIES FOUND")
        except hass.HAError as exc:
            with self.lock:
                self.loading = False
            self.set_error(str(exc))
            return
        with self.lock:
            self.states.update(states)
            self.pages = paginate(config_pages, COLUMNS * ROWS)
            self.pager.set_count(len(self.pages))
            self.loading = False
            self.error = None
            self.version += 1
        self.refresh_visible()

    def visible_ids(self):
        with self.lock:
            if not self.pages:
                return []
            return [entity["entity_id"] for entity in self.pages[self.page_index]["entities"]]

    def refresh_visible(self):
        started = time.monotonic()
        for entity_id in self.visible_ids():
            state = self.client.state(entity_id)
            if state is None:
                state = {"entity_id": entity_id, "state": "not_found", "attributes": {}}
            with self.lock:
                self.states[entity_id] = state
                # A tap shows "..." until a refresh that began after it lands.
                if self.pending.get(entity_id, started) < started:
                    del self.pending[entity_id]
                self.version += 1
        with self.lock:
            self.updated_at = time.monotonic()
            self.version += 1

    def run_call(self, entity_id, domain, service):
        try:
            changed = self.client.call(domain, service, entity_id)
            with self.lock:
                for state in changed:
                    if isinstance(state, dict) and state.get("entity_id") in self.states:
                        self.states[state["entity_id"]] = state
                self.version += 1
        finally:
            # Lights and covers report their new state a moment later.
            self.stop.wait(0.6)

    # -- input ------------------------------------------------------------------
    def tile_rects(self):
        # Six tiles either way: 3x2 on a wide (landscape) screen, 2x3 on a tall one.
        columns, rows = (3, 2) if self.view.w > self.view.h else (COLUMNS, ROWS)
        width = (self.view.w - 8 - (columns - 1) * GAP) // columns
        height = (self.content_bottom - self.content_top - 4 - (rows - 1) * GAP) // rows
        return [Rect(self.view.x + 4 + (index % columns) * (width + GAP),
                     self.content_top + 2 + (index // columns) * (height + GAP), width, height)
                for index in range(columns * rows)]

    def detail_back(self):
        return Rect(self.view.x + 16, self.view.y + self.view.h - 36, self.view.w - 32, 30)

    def page_changed(self):
        with self.lock:
            self.confirm = None
            self.version += 1
        self.jobs.put(("refresh",))

    def on_swipe(self, kind, _x, _y):
        if self.detail is not None or not self.pages:
            return
        with self.lock:
            changed = self.pager.on_swipe(kind)
        if changed:
            self.page_changed()

    def on_tap(self, x, y):
        with self.lock:
            self.version += 1
            if self.detail is not None:
                self.detail = None
                return
            if not self.pages:
                if self.client is not None and not self.loading:
                    self.loading = True
                    self.jobs.put(("reload",))
                return
        if y < self.content_top:
            self.jobs.put(("refresh",))
            return
        if y >= self.content_bottom:
            with self.lock:
                action = self.pager.on_tap(x, y)
            if action in ("prev", "next"):
                self.page_changed()
            else:
                self.jobs.put(("refresh",))
            return
        with self.lock:
            entities = self.pages[self.page_index]["entities"]
            index = next((i for i, rect in enumerate(self.tile_rects()) if rect.contains(x, y)), None)
            if index is None or index >= len(entities):
                return
            entity_id = entities[index]["entity_id"]
            state = self.states.get(entity_id)
            action = hass.action_for(state, entity_id)
            if action is None:
                self.detail = entities[index]
                return
            domain, service, needs_confirm = action
            now = time.monotonic()
            if needs_confirm and not (self.confirm and self.confirm[0] == entity_id and self.confirm[1] > now):
                self.confirm = (entity_id, now + CONFIRM_SECONDS, service)
                return
            self.confirm = None
            self.pending[entity_id] = now
        self.jobs.put(("call", entity_id, domain, service))

    # -- drawing ------------------------------------------------------------------
    def tick(self, _dt):
        now = time.monotonic()
        with self.lock:
            if self.confirm and self.confirm[1] <= now:
                self.confirm = None
                self.version += 1
            key = (self.version, time.strftime("%H:%M"))
            if key != self.drawn or now - self.drawn_at > 2.0:
                self.drawn = key
                self.drawn_at = now
                self.draw()
        return True

    def draw(self):
        fb = self.ctx.fb
        fb.clear(BG)
        if not self.pages:
            self.draw_message()
            return
        if self.detail is not None:
            self.draw_detail(self.detail)
            return
        page = self.pages[self.page_index]
        self.draw_header(page["name"])
        rects = self.tile_rects()
        for entity, rect in zip(page["entities"], rects):
            self.draw_tile(entity, rect)
        self.draw_footer()

    def draw_message(self):
        fb = self.ctx.fb
        cy = self.view.y + self.view.h // 2
        fb.text_center(self.view.cx, self.view.y + 14, "HOME ASSISTANT", SUBTLE, 1)
        if self.loading:
            title, hint = "CONNECTING", (self.ctx.env.get("HA_URL") or "homeassistant.local:8123")
        elif self.error == "SET HA TOKEN":
            title, hint = "SET HA TOKEN", "CREATE A LONG-LIVED TOKEN IN HA UNDER PROFILE - SECURITY"
        elif self.error == "BAD HA-ENTITIES":
            title, hint = "BAD HA-ENTITIES", "CHECK THE APP ENV. TAP TO RETRY"
        else:
            title, hint = self.error or "NO DATA", "TAP TO RETRY"
        for index, line in enumerate(wrap(title, self.view.w - 24, 2, 2)):
            fb.text_center(self.view.cx, cy - 26 + index * 20, line, WHITE, 2)
        for index, line in enumerate(wrap(hint, self.view.w - 24, 3)):
            fb.text_center(self.view.cx, cy + 26 + index * 12, line, SUBTLE, 1)

    def draw_header(self, name):
        self.pager.draw_header(self.ctx.fb, name, right=time.strftime("%H:%M"), dot=BAD if self.error else GOOD)

    def draw_icon(self, name, x, y, color, scale=2):
        for row_index, row in enumerate(ICONS.get(name, ICONS["dot"])):
            column = 0
            while column < len(row):
                if row[column] != "1":
                    column += 1
                    continue
                start = column
                while column < len(row) and row[column] == "1":
                    column += 1
                self.ctx.fb.fill_rect(x + start * scale, y + row_index * scale, (column - start) * scale, scale, color)

    def draw_tile(self, entity, rect):
        fb = self.ctx.fb
        entity_id = entity["entity_id"]
        state = self.states.get(entity_id)
        active = hass.is_active(state)
        unavailable = state is None or state.get("state") == "unavailable"
        confirming = self.confirm is not None and self.confirm[0] == entity_id
        fb.fill_rect(rect.x, rect.y, rect.w, rect.h, PANEL_ON if active else PANEL)
        if confirming:
            for inset in (0, 1):
                fb.fill_rect(rect.x + inset, rect.y + inset, rect.w - 2 * inset, 1, CONFIRM)
                fb.fill_rect(rect.x + inset, rect.y + rect.h - 1 - inset, rect.w - 2 * inset, 1, CONFIRM)
                fb.fill_rect(rect.x + inset, rect.y + inset, 1, rect.h - 2 * inset, CONFIRM)
                fb.fill_rect(rect.x + rect.w - 1 - inset, rect.y + inset, 1, rect.h - 2 * inset, CONFIRM)
        icon = hass.icon_name(entity_id, state)
        if icon == "lock" and state and state.get("state") == "unlocked":
            icon = "unlock"
        self.draw_icon(icon, rect.x + 8, rect.y + 8, ICON_ON if active else (DIM if unavailable else ICON_OFF))

        primary, secondary = hass.state_text(state)
        if entity_id in self.pending or entity_id not in self.states:
            primary, secondary = "...", ""
        if confirming:
            primary, secondary = ("UNLOCK" if self.confirm[2] == "unlock" else "OPEN"), "TAP AGAIN"
        room = rect.w - 36
        color = DIM if unavailable else WHITE
        if primary:
            scale = 2 if fb.text_width(text(primary), 2) <= room else 1
            primary = fit(primary, room, scale)
            fb.draw_text(rect.x + rect.w - 6 - fb.text_width(primary, scale), rect.y + (8 if scale == 2 else 12),
                         primary, CONFIRM if confirming else color, scale)
        if secondary:
            secondary = fit(secondary, rect.w - 12)
            fb.draw_text(rect.x + rect.w - 6 - fb.text_width(secondary), rect.y + 26,
                         secondary, CONFIRM if confirming else SUBTLE, 1)
        label = entity.get("label") or (hass.friendly_name(state) if state else entity_id)
        lines = wrap(label, rect.w - 8, 2)
        y = rect.y + rect.h - 4 - 11 * len(lines)
        for line in lines:
            fb.draw_text(rect.x + 4, y, line, SUBTLE if not active else WHITE, 1)
            y += 11

    def draw_footer(self):
        if self.error:
            status, color = self.error, BAD
        elif self.updated_at is not None:
            status, color = ago(time.monotonic() - self.updated_at) + " AGO", DIM
        else:
            status, color = "", DIM
        self.pager.draw_footer(self.ctx.fb, status, color)

    def draw_detail(self, entity):
        fb = self.ctx.fb
        entity_id = entity["entity_id"]
        state = self.states.get(entity_id)
        y = self.view.y + 10
        left, right = self.layout.safe_span(y, y + 36)
        x, width = left, right - left
        label = entity.get("label") or (hass.friendly_name(state) if state else entity_id)
        for line in wrap(label, width, 2, 2):
            fb.draw_text(x, y, line, WHITE, 2)
            y += 20
        y += 6
        primary, secondary = hass.state_text(state)
        self.draw_icon(hass.icon_name(entity_id, state), x, y + 4, ICON_ON if hass.is_active(state) else ICON_OFF, 3)
        scale = 3 if fb.text_width(text(primary), 3) <= width - 36 else 2
        fb.draw_text(x + 36, y + (4 if scale == 3 else 8), fit(primary, width - 36, scale), WHITE, scale)
        y += 36
        if secondary:
            for line in wrap(secondary, width, 2):
                fb.draw_text(x, y, line, SUBTLE, 1)
                y += 11
        y += 8
        rows = [("ENTITY", entity_id)]
        seconds = changed_seconds(state) if state else None
        if seconds is not None:
            rows.append(("CHANGED", ago(seconds) + " AGO"))
        attrs = (state or {}).get("attributes") or {}
        for key in ("device_class", "unit_of_measurement"):
            if attrs.get(key):
                rows.append((key.split("_")[0].upper(), str(attrs[key])))
        for label, value in rows:
            fb.draw_text(x, y, label, DIM, 1)
            for line in wrap(value, width - 72, 2):
                fb.draw_text(x + 72, y, line, WHITE, 1)
                y += 11
            y += 3
        back = self.detail_back()
        self.ctx.button(back, "BACK", PANEL, WHITE, 1)


@app()
def main(ctx):
    net.install_mdns_fallback()
    panel = Panel(ctx)
    panel.start()
    try:
        ctx.run(panel.tick, fps=10, on_tap=panel.on_tap, on_swipe=panel.on_swipe)
    finally:
        panel.stop.set()


if __name__ == "__main__":
    main()
