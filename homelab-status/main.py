#!/usr/bin/env python3
"""Homelab status board that checks the services in a Dashy config."""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

from appbase import WHITE, Rect, app, rgb565

import checks
import dashy
from kvmkit import env as kenv, net
from kvmkit.pager import Pager
from kvmkit.screen import Layout
from kvmkit.text import ago, fit, text, wrap
from kvmkit.theme import BG, DIM, PANEL, PANEL_ACTIVE, SUBTLE

APP_DIR = Path(__file__).resolve().parent
LOCAL_CONFIG = APP_DIR / "conf.yml"
CACHE_CONFIG = APP_DIR / ".dashy-cache.yml"

STATUS_COLORS = {
    checks.UP: rgb565(40, 200, 110),
    checks.WARN: rgb565(255, 170, 40),
    checks.DOWN: rgb565(240, 70, 70),
    checks.OFF: rgb565(90, 96, 110),
    checks.PENDING: rgb565(90, 130, 200),
}
STATUS_LABELS = {
    checks.UP: "UP",
    checks.WARN: "WARN",
    checks.DOWN: "DOWN",
    checks.OFF: "OFF",
    checks.PENDING: "WAIT",
}
# Worst first: the colour of a group is the colour of its worst member.
SEVERITY = [checks.DOWN, checks.WARN, checks.PENDING, checks.UP, checks.OFF]

ROW_H = 32
HEADER_H = 30
FOOTER_H = 34

def worst(statuses):
    present = set(statuses)
    for status in SEVERITY:
        if status in present:
            return status
    return checks.OFF


# -- config loading -----------------------------------------------------------

def config_url(base):
    base = base.strip()
    if "://" not in base:
        base = "http://" + base
    path = urllib.parse.urlparse(base).path
    if path.endswith((".yml", ".yaml")):
        return base
    return base.rstrip("/") + "/conf.yml"


def fetch_text(url, timeout=8):
    request = urllib.request.Request(url, headers={"User-Agent": "NanoKVM-Homelab/1.0"})
    with urllib.request.urlopen(request, timeout=timeout, context=checks._SSL_CONTEXT) as response:
        return response.read(512 * 1024).decode("utf-8", "replace")


class ConfigError(RuntimeError):
    """A config problem to show on screen: a short title plus a hint line."""

    def __init__(self, title, hint):
        super().__init__(title)
        self.hint = hint


def load_remote(url):
    """Fetch Dashy's main config plus any sub-pages it lists."""
    raw = fetch_text(url)
    title, sections, pages = dashy.extract_services(dashy.parse_config_text(raw))
    for page in pages:
        try:
            page_raw = fetch_text(urllib.parse.urljoin(url, page))
            _, page_sections, _ = dashy.extract_services(dashy.parse_config_text(page_raw))
            sections.extend(page_sections)
        except Exception as exc:
            print("Homelab: skipping Dashy page", page, exc)
    return raw, title, sections


def load_config(env):
    """Return (title, sections, source). Raises ConfigError on failure.

    Order: HOMELAB_SERVICES (inline), DASHY_URL (or its cached copy), then a
    conf.yml bundled in the App directory.
    """
    inline = (env.get("HOMELAB_SERVICES") or "").strip()
    if inline:
        try:
            title, sections, _ = dashy.extract_services(dashy.parse_inline_services(inline))
        except (dashy.YamlError, ValueError) as exc:
            print("Homelab: HOMELAB_SERVICES rejected:", exc)
            raise ConfigError("BAD SERVICES CONFIG", "CHECK HOMELAB-SERVICES IN APP ENV") from exc
        return title, sections, "ENV"
    base = (env.get("DASHY_URL") or "").strip()
    if base:
        url = config_url(base)
        try:
            raw, title, sections = load_remote(url)
            try:
                CACHE_CONFIG.write_text(raw, encoding="utf-8")
            except OSError:
                pass
            return title, sections, "DASHY"
        except Exception as exc:
            print("Homelab: Dashy config fetch failed:", url, exc)
            if CACHE_CONFIG.is_file():
                title, sections, _ = dashy.extract_services(
                    dashy.parse_config_text(CACHE_CONFIG.read_text(encoding="utf-8")))
                return title, sections, "CACHED"
            if not LOCAL_CONFIG.is_file():
                if isinstance(exc, dashy.YamlError):
                    raise ConfigError("BAD DASHY CONFIG", "CHECK THE FILE AT DASHY-URL") from exc
                raise ConfigError("DASHY " + checks.describe_error(exc), "TAP TO RETRY") from exc
    if LOCAL_CONFIG.is_file():
        title, sections, _ = dashy.extract_services(
            dashy.parse_config_text(LOCAL_CONFIG.read_text(encoding="utf-8")))
        return title, sections, "LOCAL"
    raise ConfigError("NO SERVICES", "SET DASHY-URL OR HOMELAB-SERVICES")


# -- pages ----------------------------------------------------------------------

def build_pages(monitor, rows_per_page):
    """Overview pages first, then one or more pages per section."""
    pages = []
    sections = monitor.sections
    for start in range(0, len(sections), rows_per_page):
        pages.append({"kind": "overview", "name": "Overview", "sections": sections[start:start + rows_per_page]})
    for section in sections:
        states = section["states"]
        chunks = [states[start:start + rows_per_page] for start in range(0, len(states), rows_per_page)]
        for index, chunk in enumerate(chunks):
            name = section["name"]
            if len(chunks) > 1:
                name += " %d" % (index + 1)
            pages.append({"kind": "section", "name": name, "section": section, "states": chunk})
    return pages


class Board:
    def __init__(self, ctx):
        self.ctx = ctx
        self.layout = Layout(ctx.fb, HEADER_H, FOOTER_H)
        self.pager = Pager(self.layout)
        self.view = self.layout.view
        with (APP_DIR / "app.json").open("r", encoding="utf-8") as stream:
            self.version = json.load(stream).get("version", "?")
        self.interval = kenv.number(ctx.env, "CHECK_INTERVAL", 60)
        self.timeout = kenv.number(ctx.env, "CHECK_TIMEOUT", 6)
        self.monitor = None
        self.pages = []
        self.detail = None
        self.title = "Homelab"
        self.source = ""
        self.error = None
        self.loading = True
        self.dirty = True
        self.drawn_version = -1
        self.drawn_at = 0.0
        self.content_top = self.layout.content.y
        self.content_bottom = self.layout.footer.y
        self.rows_per_page = max(1, (self.content_bottom - self.content_top) // ROW_H)
        self.reload()

    # -- lifecycle --
    def reload(self):
        self.loading = True
        self.error = None
        self.error_hint = ""
        self.dirty = True
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        try:
            title, sections, source = load_config(self.ctx.env)
            if not sections:
                raise ConfigError("NO SERVICES", "CONFIG HAS NO ITEMS WITH A URL")
        except Exception as exc:
            if isinstance(exc, ConfigError):
                self.error, self.error_hint = str(exc), exc.hint
            else:
                print("Homelab: config load failed:", exc)
                self.error, self.error_hint = "CONFIG ERROR", checks.describe_error(exc)
            self.loading = False
            self.dirty = True
            return
        if self.monitor:
            self.monitor.stop()
        monitor = checks.Monitor(sections, interval=self.interval, timeout=self.timeout)
        self.title = title or "Homelab"
        self.source = source
        self.pages = build_pages(monitor, self.rows_per_page)
        self.pager.set_count(len(self.pages))
        self.detail = None
        self.monitor = monitor
        monitor.start()
        self.loading = False
        self.dirty = True

    # -- layout --
    def row_rect(self, index):
        return Rect(self.view.x + 2, self.content_top + index * ROW_H, self.view.w - 4, ROW_H - 3)

    def detail_buttons(self):
        y = self.view.y + self.view.h - 36
        half = (self.view.w - 40) // 2
        return (Rect(self.view.x + 16, y, half, 30),
                Rect(self.view.x + 24 + half, y, half, 30))

    @property
    def page_index(self):
        return self.pager.index

    # -- input --
    def on_swipe(self, kind, _x, _y):
        if self.detail is None and self.pages and self.pager.on_swipe(kind):
            self.dirty = True

    def on_tap(self, x, y):
        self.dirty = True
        if self.error:
            self.reload()
            return
        if not self.pages:
            return
        if self.detail is not None:
            back, recheck = self.detail_buttons()
            if recheck.contains(x, y):
                self.monitor.check_now(self.detail)
            elif back.contains(x, y) or y < self.content_bottom:
                self.detail = None
            return
        if y < self.content_top:
            # The header doubles as a "reload Dashy config" control.
            self.reload()
            return
        if y >= self.content_bottom:
            if self.pager.on_tap(x, y) == "middle":
                self.monitor.check_now()
            return
        page = self.pages[self.page_index]
        index = (y - self.content_top) // ROW_H
        if page["kind"] == "overview":
            if index < len(page["sections"]):
                section = page["sections"][index]
                for page_index, candidate in enumerate(self.pages):
                    if candidate.get("section") is section:
                        self.pager.go(page_index)
                        break
        elif index < len(page["states"]):
            self.detail = page["states"][index]

    # -- drawing --
    def tick(self, _dt):
        now = time.monotonic()
        version = self.monitor.version if self.monitor else -1
        if self.dirty or version != self.drawn_version or now - self.drawn_at > 2.0:
            self.dirty = False
            self.drawn_version = version
            self.drawn_at = now
            if self.monitor:
                with self.monitor.lock:
                    self.draw()
            else:
                self.draw()
        return True

    def draw(self):
        fb = self.ctx.fb
        fb.clear(BG)
        if self.loading and not self.pages:
            self.draw_message("LOADING", "READING DASHY CONFIG")
        elif self.error:
            self.draw_message(self.error, self.error_hint)
        elif self.detail is not None:
            self.draw_detail(self.detail)
        else:
            page = self.pages[self.page_index]
            self.draw_header(page)
            if page["kind"] == "overview":
                self.draw_overview(page)
            else:
                self.draw_section(page)
            self.draw_footer()

    def draw_message(self, title, hint):
        fb = self.ctx.fb
        cy = self.view.y + self.view.h // 2
        fb.text_center(self.view.cx, self.view.y + 14, fit(self.title, self.view.w - 16), SUBTLE, 1)
        for index, line in enumerate(wrap(title, self.view.w - 24, 3, 2)):
            fb.text_center(self.view.cx, cy - 30 + index * 20, line, WHITE, 2)
        for index, line in enumerate(wrap(hint, self.view.w - 24, 2)):
            fb.text_center(self.view.cx, cy + 34 + index * 12, line, SUBTLE, 1)

    def draw_header(self, page):
        fb = self.ctx.fb
        if page["kind"] == "overview":
            label = self.title
            states = list(self.monitor.states())
        else:
            label = page["name"]
            states = page["section"]["states"]
        status = worst(state.status for state in states)
        checked = [state for state in states if state.status in (checks.UP, checks.WARN, checks.DOWN)]
        up = sum(1 for state in checked if state.status == checks.UP)
        summary = "%d/%d" % (up, len(checked)) if checked else "..."
        self.pager.draw_header(fb, label, right=summary, right_color=STATUS_COLORS[status])

    def draw_overview(self, page):
        fb = self.ctx.fb
        for index, section in enumerate(page["sections"]):
            rect = self.row_rect(index)
            states = section["states"]
            checked = [state for state in states if state.status in (checks.UP, checks.WARN, checks.DOWN)]
            up = sum(1 for state in checked if state.status == checks.UP)
            status = worst(state.status for state in states)
            fb.fill_rect(rect.x, rect.y, rect.w, rect.h, PANEL)
            fb.fill_rect(rect.x, rect.y, 4, rect.h, STATUS_COLORS[status])
            count = "%d/%d" % (up, len(checked)) if checked else "-"
            count_w = fb.text_width(count, 1)
            fb.draw_text(rect.x + 8, rect.y + 4, fit(section["name"], rect.w - count_w - 22, 2), WHITE, 2)
            fb.draw_text(rect.x + rect.w - count_w - 6, rect.y + 8, count, STATUS_COLORS[status], 1)
            x = rect.x + 8
            for state in states:
                if x + 8 > rect.x + rect.w - 4:
                    break
                fb.fill_rect(x, rect.y + 20, 8, 7, STATUS_COLORS[state.status])
                x += 11
        self.draw_issues(self.content_top + len(page["sections"]) * ROW_H + 4)

    def draw_issues(self, top):
        """List failing services in the space left under the overview rows."""
        fb = self.ctx.fb
        lines = (self.content_bottom - top - 14) // 11
        if lines < 1:
            return
        x = self.view.x + 10
        width = self.view.w - 20
        issues = [state for state in self.monitor.states() if state.status in (checks.DOWN, checks.WARN)]
        if not issues:
            if any(state.status == checks.PENDING for state in self.monitor.states()):
                return
            fb.draw_text(x, top + 4, "ALL SERVICES UP", STATUS_COLORS[checks.UP], 1)
            return
        issues.sort(key=lambda state: SEVERITY.index(state.status))
        if lines < 2:
            # Room for one line only: count plus as many names as fit.
            summary = "%d ISSUES: %s" % (len(issues), " / ".join(state.service["title"] for state in issues))
            fb.draw_text(x, top + 4, fit(summary, width), STATUS_COLORS[issues[0].status], 1)
            return
        fb.draw_text(x, top + 2, "ISSUES", DIM, 1)
        y = top + 15
        for index, state in enumerate(issues[:lines]):
            if index == lines - 1 and len(issues) > lines:
                fb.draw_text(x, y, "AND %d MORE" % (len(issues) - index), DIM, 1)
                break
            message = state.message
            message_w = fb.text_width(fit(message, 96), 1)
            fb.draw_text(x, y, fit(state.service["title"], width - message_w - 8), WHITE, 1)
            fb.draw_text(x + width - message_w, y, fit(message, 96), STATUS_COLORS[state.status], 1)
            y += 11

    def draw_section(self, page):
        fb = self.ctx.fb
        for index, state in enumerate(page["states"]):
            rect = self.row_rect(index)
            color = STATUS_COLORS[state.status]
            fb.fill_rect(rect.x, rect.y, rect.w, rect.h, PANEL)
            fb.fill_rect(rect.x, rect.y, 4, rect.h, color)
            fb.draw_text(rect.x + 8, rect.y + 3, fit(state.service["title"], rect.w - 8, 2), WHITE, 2)
            if state.busy and state.status != checks.PENDING:
                right = "..."
            elif state.latency is not None:
                right = "%dMS" % state.latency
            else:
                right = ""
            right_w = fb.text_width(right, 1)
            detail = STATUS_LABELS[state.status] + "  " + state.message
            if state.status == checks.UP and state.code is not None:
                detail = "UP  %d" % state.code
            fb.draw_text(rect.x + 8, rect.y + 20, fit(detail, rect.w - right_w - 22), color, 1)
            fb.draw_text(rect.x + rect.w - right_w - 6, rect.y + 20, right, SUBTLE, 1)

    def draw_footer(self):
        if any(state.busy for state in self.monitor.states()):
            status = "CHECKING"
        elif self.monitor.last_round:
            status = ago(time.monotonic() - self.monitor.last_round) + " AGO"
        else:
            status = ""
        if self.source == "CACHED":
            status = "CACHED CFG"
        self.pager.draw_footer(self.ctx.fb, status, DIM)

    def draw_detail(self, state):
        fb = self.ctx.fb
        service = state.service
        color = STATUS_COLORS[state.status]
        y = self.view.y + 8
        left, right = self.layout.safe_span(y, y + 36)
        x, width = left, right - left
        for line in wrap(service["title"], width, 2, 2):
            fb.draw_text(x, y, line, WHITE, 2)
            y += 20
        fb.fill_rect(x, y + 2, width, 30, PANEL)
        fb.fill_rect(x, y + 2, 6, 30, color)
        fb.draw_text(x + 14, y + 9, STATUS_LABELS[state.status], color, 2)
        if state.latency is not None:
            latency = "%dMS" % state.latency
            fb.draw_text(x + width - fb.text_width(latency, 2) - 8, y + 9, latency, WHITE, 2)
        y += 42
        for line in wrap(service["check_url"] or "NO URL", width, 3):
            fb.draw_text(x, y, line, SUBTLE, 1)
            y += 11
        y += 6
        now = time.time()
        rows = [("RESULT", state.message)]
        rows.append(("CHECKED", ago(now - state.checked_at) + " AGO" if state.checked_at else "-"))
        if state.changed_at:
            rows.append(("SINCE", ago(now - state.changed_at)))
        if state.history:
            up = sum(1 for status, _ in state.history if status == checks.UP)
            rows.append(("UPTIME", "%d%% OF %d" % (round(100 * up / len(state.history)), len(state.history))))
        for label, value in rows:
            fb.draw_text(x, y, label, DIM, 1)
            fb.draw_text(x + 64, y, fit(value, width - 64), WHITE, 1)
            y += 12
        self.draw_history(state, Rect(x, y + 6, width, 34))
        back, recheck = self.detail_buttons()
        self.ctx.button(back, "BACK", PANEL_ACTIVE, WHITE, 1)
        self.ctx.button(recheck, "..." if state.busy else "RECHECK", PANEL_ACTIVE, WHITE, 1)

    def draw_history(self, state, rect):
        fb = self.ctx.fb
        fb.fill_rect(rect.x, rect.y, rect.w, rect.h, PANEL)
        history = state.history[-checks.HISTORY:]
        if not history:
            fb.text_center(rect.cx, rect.cy - 4, "NO HISTORY YET", DIM, 1)
            return
        peak = max([latency for _, latency in history if latency] + [1])
        bar_w = max(2, (rect.w - 4) // checks.HISTORY)
        x = rect.x + rect.w - 2 - bar_w * len(history)
        for status, latency in history:
            if latency is None:
                height = rect.h - 4
            else:
                height = max(2, int((rect.h - 4) * latency / peak))
            fb.fill_rect(x, rect.y + rect.h - 2 - height, bar_w - 1, height, STATUS_COLORS[status])
            x += bar_w


@app()
def main(ctx):
    net.install_mdns_fallback()
    board = Board(ctx)
    try:
        ctx.run(board.tick, fps=10, on_tap=board.on_tap, on_swipe=board.on_swipe)
    finally:
        if board.monitor:
            board.monitor.stop()


if __name__ == "__main__":
    main()
