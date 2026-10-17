#!/usr/bin/env python3
"""NanoKVM device dashboard: system health, network status and QR codes."""

from __future__ import annotations

import time

from appbase import WHITE, Rect, app, rgb565

import qr
import sysinfo
from kvmkit import env as kenv
from kvmkit.pager import Pager
from kvmkit.screen import Layout
from kvmkit.text import fit, text
from kvmkit.theme import BAD, BG, BORDER, DIM, GOOD, PANEL, SUBTLE, WARN

QR_DARK = rgb565(0, 0, 0)
QR_LIGHT = rgb565(255, 255, 255)

HEADER_H = 30
FOOTER_H = 34

def duration(seconds):
    seconds = int(seconds)
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return "%dD %dH" % (days, hours)
    if hours:
        return "%dH %dM" % (hours, minutes)
    return "%dM" % minutes


def size(value):
    for unit, factor in (("G", 1 << 30), ("M", 1 << 20), ("K", 1 << 10)):
        if value >= factor:
            amount = value / factor
            return ("%.1f%s" if amount < 10 else "%d%s") % (amount, unit)
    return "%dB" % value


def level_color(value, warn, bad):
    if value is None:
        return DIM
    if value >= bad:
        return BAD
    if value >= warn:
        return WARN
    return GOOD


def parse_links(value):
    """Parse `Label=URL, URL, ...` into [(label, url)]."""
    links = []
    for _name, entries in kenv.sections(value.replace(";", ",")):
        for entry in entries:
            label, url = kenv.pair(entry)
            if url is None or "/" in label or ":" in label:
                label, url = "", entry
            if not label:
                label = url.split("://", 1)[-1].split("/", 1)[0]
            links.append((label, url))
    return links


class Dashboard:
    def __init__(self, ctx, info):
        self.ctx = ctx
        self.info = info
        self.layout = Layout(ctx.fb, HEADER_H, FOOTER_H)
        self.pager = Pager(self.layout)
        self.view = self.layout.view
        self.content_top = self.layout.content.y
        self.content_bottom = self.layout.footer.y
        self.drawn_key = None
        self.qr_cache = {}
        env = ctx.env
        self.web_ui_url = (env.get("WEB_UI_URL") or "").strip()
        self.wifi_ssid = (env.get("WIFI_SSID") or "").strip()
        self.wifi_password = env.get("WIFI_PASSWORD") or ""
        self.wifi_security = (env.get("WIFI_SECURITY") or "WPA").strip() or "WPA"
        self.links = parse_links(env.get("QR_LINKS") or "")

    @property
    def page_index(self):
        return self.pager.index

    # -- pages --
    def pages(self, snapshot):
        """Return [(kind, title, qr_payload, caption)] for the current snapshot."""
        pages = [("system", "System", None, None), ("network", "Network", None, None)]
        ip = sysinfo.primary_ip(snapshot)
        web_ui = self.web_ui_url or ("https://%s" % ip if ip else "")
        pages.append(("qr", "Web UI", web_ui, web_ui))
        tailscale = snapshot.get("tailscale") or {}
        if tailscale.get("ip") and not self.web_ui_url:
            url = "https://%s" % tailscale["ip"]
            pages.append(("qr", "Tailnet UI", url, url))
        ssid = self.wifi_ssid or (snapshot.get("wifi") or {}).get("ssid", "")
        if self.wifi_password and ssid:
            pages.append(("qr", "Wi-Fi", qr.wifi_payload(ssid, self.wifi_password, self.wifi_security), "JOIN " + ssid))
        for label, url in self.links:
            pages.append(("qr", label, url, url))
        return pages

    def sync_page_count(self):
        with self.info.lock:
            self.pager.set_count(len(self.pages(self.info.snapshot)) if self.info.snapshot else 1)

    def on_swipe(self, kind, _x, _y):
        self.sync_page_count()
        self.pager.on_swipe(kind)

    def on_tap(self, x, y):
        if y >= self.content_bottom:
            self.sync_page_count()
            self.pager.on_tap(x, y)

    # -- drawing --
    def tick(self, _dt):
        with self.info.lock:
            snapshot = self.info.snapshot
            history = list(self.info.cpu_history)
            version = self.info.version
        pages = self.pages(snapshot) if snapshot else []
        self.pager.set_count(len(pages))
        kind = pages[self.page_index][0] if pages else None
        # QR pages only change with their payload; live pages with every sample.
        if kind == "qr":
            key = (self.page_index, len(pages), pages[self.page_index][2], snapshot.get("time"))
        else:
            key = (self.page_index, len(pages), version)
        if key == self.drawn_key:
            return True
        self.drawn_key = key
        self.draw(snapshot, pages, history)
        return True

    def draw(self, snapshot, pages, history):
        fb = self.ctx.fb
        fb.clear(BG)
        if not snapshot:
            fb.text_center(self.view.cx, self.view.y + self.view.h // 2 - 8, "LOADING", WHITE, 2)
            return
        kind, name, payload, caption = pages[self.page_index]
        self.draw_header(name, snapshot)
        if kind == "system":
            self.draw_system(snapshot, history)
        elif kind == "network":
            self.draw_network(snapshot)
        else:
            self.draw_qr(payload, caption)
        self.draw_footer(len(pages))

    def draw_header(self, name, snapshot):
        self.pager.draw_header(self.ctx.fb, name, right=snapshot.get("time", ""))

    def draw_footer(self, count):
        self.pager.draw_footer(self.ctx.fb)

    def tile(self, rect, label, value, color, detail="", fraction=None):
        fb = self.ctx.fb
        fb.fill_rect(rect.x, rect.y, rect.w, rect.h, PANEL)
        fb.draw_text(rect.x + 8, rect.y + 6, label, DIM, 1)
        fb.draw_text(rect.x + 8, rect.y + 18, fit(value, rect.w - 12, 3), color, 3)
        if detail:
            fb.draw_text(rect.x + rect.w - fb.text_width(fit(detail, rect.w - 16)) - 6, rect.y + 6,
                         fit(detail, rect.w - 16), SUBTLE, 1)
        if fraction is not None:
            bar_w = rect.w - 16
            fb.fill_rect(rect.x + 8, rect.y + rect.h - 9, bar_w, 4, BORDER)
            fb.fill_rect(rect.x + 8, rect.y + rect.h - 9, int(bar_w * max(0.0, min(1.0, fraction))), 4, color)

    def draw_system(self, snapshot, history):
        fb = self.ctx.fb
        x = self.view.x + 4
        gap = 6
        wide = self.view.w > self.view.h
        tile_w = (self.view.w - 8 - gap) // 2
        tile_h = 50 if wide else 56
        y = self.content_top
        cpu = snapshot.get("cpu")
        self.tile(Rect(x, y, tile_w, tile_h), "CPU", "-" if cpu is None else "%d%%" % round(cpu),
                  level_color(cpu, 70, 90), fraction=(cpu or 0) / 100)
        temp = snapshot.get("temp")
        self.tile(Rect(x + tile_w + gap, y, tile_w, tile_h), "TEMP", "-" if temp is None else "%dC" % round(temp),
                  level_color(temp, 65, 80), fraction=None if temp is None else temp / 100)
        y += tile_h + gap
        used, total = snapshot.get("mem", (0, 0))
        mem = 100.0 * used / total if total else None
        self.tile(Rect(x, y, tile_w, tile_h), "MEM", "-" if mem is None else "%d%%" % round(mem),
                  level_color(mem, 80, 92), size(total), (mem or 0) / 100)
        used, total = snapshot.get("disk", (0, 0))
        disk = 100.0 * used / total if total else None
        self.tile(Rect(x + tile_w + gap, y, tile_w, tile_h), "DISK", "-" if disk is None else "%d%%" % round(disk),
                  level_color(disk, 80, 92), size(total), (disk or 0) / 100)
        y += tile_h + gap
        # Landscape: the CPU graph and the text rows share the last band.
        graph_w = tile_w if wide else self.view.w - 8
        graph = Rect(x, y, graph_w, min(38, self.content_bottom - y - 2))
        fb.fill_rect(graph.x, graph.y, graph.w, graph.h, PANEL)
        fb.draw_text(graph.x + 6, graph.y + 4, "CPU %dS" % int(len(history) * self.info.fast_interval), DIM, 1)
        if history:
            bar_w = max(1, (graph.w - 8) // 60)
            bx = graph.x + graph.w - 4 - bar_w * len(history)
            plot_h = graph.h - 16
            for value in history:
                height = max(1, int(plot_h * min(100.0, value) / 100))
                fb.fill_rect(bx, graph.y + graph.h - 3 - height, max(1, bar_w - 1), height, level_color(value, 70, 90))
                bx += bar_w
        if wide:
            row_x, y = x + tile_w + gap, y + 4
        else:
            row_x, y = x, y + graph.h + 8
        row_w = self.view.x + self.view.w - 4 - row_x
        load = " ".join(snapshot.get("load", []))
        rows = [("LOAD", load), ("UPTIME", duration(snapshot.get("uptime", 0))), ("HOST", snapshot.get("hostname", ""))]
        for label, value in rows:
            if y + 8 > self.content_bottom:
                break
            fb.draw_text(row_x + 6, y, label, DIM, 1)
            fb.draw_text(row_x + 62, y, fit(value, row_w - 64), WHITE, 1)
            y += 12

    def draw_network(self, snapshot):
        fb = self.ctx.fb
        x = self.view.x + 4
        width = self.view.w - 8
        y = self.content_top
        wifi = snapshot.get("wifi") or {}
        wide = self.view.w > self.view.h
        panel = Rect(x, y, width, 40 if wide else 52)
        fb.fill_rect(panel.x, panel.y, panel.w, panel.h, PANEL)
        if wifi:
            signal = wifi.get("signal")
            bars = sysinfo.signal_bars(signal)
            color = (BAD, BAD, WARN, GOOD, GOOD)[bars]
            for index in range(4):
                bar_h = 4 + index * 4
                bx = panel.x + panel.w - 40 + index * 8
                fb.fill_rect(bx, panel.y + panel.h - 6 - bar_h, 6, bar_h, color if index < bars else BORDER)
            fb.draw_text(panel.x + 8, panel.y + 6, fit(wifi.get("ssid", "WI-FI"), panel.w - 12, 2), WHITE, 2)
            freq = wifi.get("freq")
            band = "%s GHZ" % ("2.4" if freq and freq < 3000 else ("6" if freq and freq > 5925 else "5")) if freq else ""
            channel = sysinfo.wifi_channel(freq)
            line = "%s DBM  %s%s" % (signal if signal is not None else "-", band, "  CH %d" % channel if channel else "")
            if wide and wifi.get("tx_rate"):
                line += "  %d MBIT/S" % wifi["tx_rate"]
            fb.draw_text(panel.x + 8, panel.y + 26, fit(line, panel.w - 56), color, 1)
            if not wide and wifi.get("tx_rate"):
                fb.draw_text(panel.x + 8, panel.y + 40, "%d MBIT/S" % wifi["tx_rate"], SUBTLE, 1)
        else:
            fb.draw_text(panel.x + 8, panel.y + 8, "WI-FI", WHITE, 2)
            fb.draw_text(panel.x + 8, panel.y + 30, "NOT CONNECTED", WARN, 1)
        y += panel.h + 6

        rows = []
        tailscale = snapshot.get("tailscale")
        # Wi-Fi and Ethernet first: they carry the address people connect to.
        interfaces = sorted(snapshot.get("interfaces", []), key=lambda item: not item["name"].startswith(("eth", "wl", "en")))
        for item in interfaces:
            name = item["name"]
            if name.startswith("tailscale"):
                continue
            label = name.upper()
            if name.startswith("usb"):
                label += " TARGET NET"
            state = item["state"].upper()
            color = GOOD if state == "UP" else (DIM if state == "DOWN" else SUBTLE)
            rows.append((label, state, color, item["ip"] or "NO ADDRESS"))
        if tailscale:
            state = tailscale["state"]
            rows.append(("TAILSCALE", state, GOOD if state == "UP" else WARN, tailscale.get("ip") or "-"))
        # Rows shrink a little in landscape so every interface still fits.
        footer_lines = 14 if wide else 26
        row_h = max(26, min(32, (self.content_bottom - y - footer_lines) // max(1, len(rows))))
        for label, state, color, address in rows:
            if y + 26 > self.content_bottom - footer_lines:
                break
            fb.draw_text(x + 6, y, fit(label, width - 100), DIM, 1)
            fb.draw_text(x + width - fb.text_width(state) - 6, y, state, color, 1)
            fb.draw_text(x + 6, y + 10, fit(address, width - 8, 2), WHITE if address[0].isdigit() else DIM, 2)
            y += row_h
        usb = snapshot.get("usb", "unknown")
        usb_text, usb_color = {
            "configured": ("CONNECTED", GOOD),
            "not attached": ("UNPLUGGED", DIM),
        }.get(usb, (usb.upper(), WARN))
        hid = "ON" if snapshot.get("hid") else "OFF"
        hid_color = GOOD if hid == "ON" else WARN
        if wide:
            # One line, two columns: TARGET USB ... | KEYBOARD/MOUSE ...
            y = self.content_bottom - 12
            half = width // 2
            fb.draw_text(x + 6, y, "USB", DIM, 1)
            fb.draw_text(x + half - 6 - fb.text_width(usb_text), y, usb_text, usb_color, 1)
            fb.draw_text(x + half + 6, y, "KEYS/MOUSE", DIM, 1)
            fb.draw_text(x + width - fb.text_width(hid) - 6, y, hid, hid_color, 1)
            return
        y = max(y, self.content_bottom - 24)
        fb.draw_text(x + 6, y, "TARGET USB", DIM, 1)
        fb.draw_text(x + width - fb.text_width(usb_text) - 6, y, usb_text, usb_color, 1)
        fb.draw_text(x + 6, y + 12, "KEYBOARD/MOUSE", DIM, 1)
        fb.draw_text(x + width - fb.text_width(hid) - 6, y + 12, hid, hid_color, 1)

    def qr_matrix(self, payload):
        if payload not in self.qr_cache:
            try:
                self.qr_cache[payload] = qr.encode(payload)
            except ValueError:
                self.qr_cache[payload] = None
        return self.qr_cache[payload]

    def draw_qr(self, payload, caption):
        fb = self.ctx.fb
        caption_h = 26
        if not payload:
            fb.text_center(self.view.cx, self.view.y + self.view.h // 2 - 8, "NO NETWORK", WARN, 2)
            return
        matrix = self.qr_matrix(payload)
        if matrix is None:
            fb.text_center(self.view.cx, self.view.y + self.view.h // 2 - 8, "TOO LONG", WARN, 2)
            return
        modules = len(matrix)
        room = min(self.view.w - 8, self.content_bottom - self.content_top - caption_h - 4)
        quiet = 4 if room // (modules + 8) >= 3 else 2
        scale = max(1, room // (modules + 2 * quiet))
        panel_size = scale * (modules + 2 * quiet)
        px = self.view.cx - panel_size // 2
        py = self.content_top + 2
        fb.fill_rect(px, py, panel_size, panel_size, QR_LIGHT)
        origin_x = px + quiet * scale
        origin_y = py + quiet * scale
        for row_index, row in enumerate(matrix):
            column = 0
            # Draw horizontal runs of dark modules as single rectangles.
            while column < modules:
                if not row[column]:
                    column += 1
                    continue
                start = column
                while column < modules and row[column]:
                    column += 1
                fb.fill_rect(origin_x + start * scale, origin_y + row_index * scale,
                             (column - start) * scale, scale, QR_DARK)
        caption = caption.split("://", 1)[-1]
        fb.text_center(self.view.cx, py + panel_size + 6, fit(caption, self.view.w - 8), SUBTLE, 1)


@app()
def main(ctx):
    info = sysinfo.SystemInfo()
    info.refresh()
    info.start()
    dashboard = Dashboard(ctx, info)
    try:
        ctx.run(dashboard.tick, fps=10, on_tap=dashboard.on_tap, on_swipe=dashboard.on_swipe)
    finally:
        info.stop()


if __name__ == "__main__":
    main()
