#!/usr/bin/env python3
"""Web View: show a web page from WEB_URL in reader mode on the touchscreen.

Swipe up/down or tap the footer arrows to page through it. Tap a link to
follow it, tap the header to go back, and tap the middle of the footer to
reload. There is no JavaScript or CSS; the App shows what the HTML holds.
"""

from __future__ import annotations

import ssl
import threading
import time
import urllib.parse
import urllib.request

from appbase import app

import htmlview
from kvmkit import env as kenv, net
from kvmkit.pager import Pager
from kvmkit.screen import Layout
from kvmkit.text import ago, draw_text, wrap
from kvmkit.theme import ACCENT, BAD, BG, BORDER, DIM, SUBTLE, TEXT, WARN, rgb

MAX_BYTES = 768 * 1024
STYLE_COLORS = {
    "normal": TEXT,
    "bold": rgb(255, 230, 140),
    "heading": rgb(255, 255, 255),
    "link": ACCENT,
    "code": rgb(150, 230, 160),
    "dim": DIM,
}
SSL_CONTEXT = ssl._create_unverified_context()


def fetch(url, timeout=12):
    """Return (final_url, content_type, text)."""
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (NanoKVM Web View; text-only)",
        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5",
    })
    with urllib.request.urlopen(request, timeout=timeout, context=SSL_CONTEXT) as response:
        content_type = response.headers.get("Content-Type", "")
        body = response.read(MAX_BYTES)
        return response.geturl(), content_type, htmlview.decode(body, content_type)


def describe_error(exc):
    text = str(getattr(exc, "reason", exc))
    if getattr(exc, "code", None):
        return "HTTP %d" % exc.code
    lowered = text.lower()
    if "timed out" in lowered:
        return "TIMEOUT"
    if "refused" in lowered:
        return "CONNECTION REFUSED"
    if "name" in lowered and ("resolution" in lowered or "known" in lowered):
        return "HOST NOT FOUND"
    return text.upper()[:60] or exc.__class__.__name__.upper()


class WebView:
    def __init__(self, ctx):
        self.ctx = ctx
        self.layout = Layout(ctx.fb)
        self.pager = Pager(self.layout)
        self.view = self.layout.view
        env = ctx.env
        self.home = (env.get("WEB_URL") or "").strip()
        if self.home and "://" not in self.home:
            self.home = "http://" + self.home
        self.refresh = kenv.number(env, "WEB_REFRESH", 0, minimum=0)
        self.body_scale = 2 if (env.get("WEB_TEXT_SIZE") or "").strip().lower() in ("large", "2", "big") else 1
        self.lock = threading.Lock()
        self.history = []
        self.url = None
        self.title = ""
        self.lines = []
        self.pages = [(0, 0)]
        self.loading = False
        self.error = None if self.home else "SET WEB-URL"
        self.loaded_at = None
        self.dirty = True
        self.drawn_at = 0.0
        if self.home:
            self.open(self.home)

    # -- loading --
    def open(self, url, remember=True):
        with self.lock:
            if self.loading:
                return
            if remember and self.url and self.url != url:
                self.history.append((self.url, self.pager.index))
            self.loading = True
            self.dirty = True
        threading.Thread(target=self._load, args=(url,), daemon=True).start()

    def _load(self, url, page=0):
        try:
            final_url, content_type, body = fetch(url)
            if "html" in content_type or not content_type or body.lstrip()[:1] == "<":
                title, blocks = htmlview.parse_html(body, final_url)
            else:
                title, blocks = htmlview.parse_plain(body, content_type)
            left, right = self.layout.content_span()
            lines = htmlview.layout(blocks, right - left, self.body_scale)
            pages = htmlview.paginate(lines, self.layout.content.h - 4)
            with self.lock:
                self.url = final_url
                self.title = title or urllib.parse.urlparse(final_url).netloc
                self.lines = lines
                self.pages = pages
                self.pager.set_count(len(pages))
                self.pager.go(min(page, len(pages) - 1))
                self.error = None if lines else "NO TEXT ON THIS PAGE"
                self.loaded_at = time.monotonic()
        except Exception as exc:  # network and parse errors end up on screen
            print("Web View: loading %s failed: %r" % (url, exc))
            with self.lock:
                self.error = describe_error(exc)
                if self.url is None:
                    self.url = url
        finally:
            with self.lock:
                self.loading = False
                self.dirty = True

    def reload(self):
        if self.url:
            with self.lock:
                if self.loading:
                    return
                self.loading = True
                self.dirty = True
            threading.Thread(target=self._load, args=(self.url, self.pager.index), daemon=True).start()
        elif self.home:
            self.open(self.home, remember=False)

    def back(self):
        if not self.history:
            self.reload()
            return
        url, page = self.history.pop()
        with self.lock:
            if self.loading:
                return
            self.loading = True
            self.dirty = True
        threading.Thread(target=self._load, args=(url, page), daemon=True).start()

    # -- input --
    def on_swipe(self, kind, _x, _y):
        with self.lock:
            if self.pager.on_swipe(kind):
                self.dirty = True

    def on_tap(self, x, y):
        header, footer = self.layout.header, self.layout.footer
        if y < header.y + header.h:
            self.back()
            return
        if y >= footer.y:
            with self.lock:
                action = self.pager.on_tap(x, y)
                self.dirty = True
            if action == "middle":
                self.reload()
            return
        href = self.link_at(x, y)
        if href and href.startswith(("http://", "https://")):
            self.open(href.split("#", 1)[0] or href)

    def link_at(self, x, y):
        """The link under a tap, with a little slack around short links."""
        with self.lock:
            best, best_distance = None, 24
            for line, top in self.visible_lines():
                if not top - 4 <= y < top + line.height + 4:
                    continue
                for sx, word, _style, scale, href in line.segments:
                    if not href:
                        continue
                    left = self.text_left + sx
                    right = left + len(word) * 8 * scale
                    distance = 0 if left <= x < right else min(abs(x - left), abs(x - right))
                    if distance < best_distance:
                        best, best_distance = href, distance
            return best

    def visible_lines(self):
        start, end = self.pages[min(self.pager.index, len(self.pages) - 1)]
        top = self.layout.content.y + 2
        for index in range(start, end):
            line = self.lines[index]
            if index > start:
                top += line.gap
            yield line, top
            top += line.height

    @property
    def text_left(self):
        return self.layout.content_span()[0]

    # -- drawing --
    def tick(self, _dt):
        now = time.monotonic()
        if self.refresh and self.loaded_at and not self.loading and now - self.loaded_at >= self.refresh:
            self.loaded_at = now
            self.reload()
        # Repaint on changes, and every few seconds for the "updated" age.
        if self.dirty or now - self.drawn_at > 5:
            with self.lock:
                self.dirty = False
                self.drawn_at = now
                self.draw()
        return True

    def draw(self):
        fb = self.ctx.fb
        fb.clear(BG)
        if not self.lines:
            self.draw_message()
            return
        self.pager.draw_header(fb, self.title, right=time.strftime("%H:%M"),
                               dot=BAD if self.error else (WARN if self.loading else None))
        left = self.text_left
        for line, top in self.visible_lines():
            if line.rule:
                right = self.layout.content_span()[1]
                fb.fill_rect(left, top + 2, right - left, 1, BORDER)
                continue
            for sx, word, style, scale, href in line.segments:
                color = STYLE_COLORS.get(style, TEXT)
                draw_text(fb, left + sx, top, word, color, scale)
                if href and style == "link":
                    # Underline links (skipping the leading space of a word).
                    lead = len(word) - len(word.lstrip(" "))
                    fb.fill_rect(left + sx + lead * 8 * scale, top + 8 * scale,
                                 (len(word) - lead) * 8 * scale, 1, color)
        if self.loading:
            status, color = "LOADING", WARN
        elif self.error:
            status, color = self.error, BAD
        elif self.loaded_at is not None:
            status, color = ago(time.monotonic() - self.loaded_at) + " AGO", DIM
        else:
            status, color = "", DIM
        self.pager.draw_footer(fb, status, color)

    def draw_message(self):
        fb = self.ctx.fb
        view = self.view
        cy = view.y + view.h // 2
        fb.text_center(view.cx, view.y + 14, "WEB VIEW", SUBTLE, 1)
        if self.loading:
            title, hint = "LOADING", self.url or self.home
        elif self.error == "SET WEB-URL":
            title, hint = "SET WEB-URL", "ADD A PAGE ADDRESS IN THE APP SETTINGS"
        else:
            title, hint = self.error or "NO PAGE", "TAP TO RETRY"
        width = view.w - 48
        for index, line in enumerate(wrap(title, width, 2, 2)):
            fb.text_center(view.cx, cy - 26 + index * 20, line, TEXT, 2)
        for index, line in enumerate(wrap(hint, width, 3)):
            fb.text_center(view.cx, cy + 26 + index * 12, line, SUBTLE, 1)

    def on_tap_message(self, x, y):
        if not self.lines and not self.loading and self.home:
            self.reload()


@app()
def main(ctx):
    net.install_mdns_fallback()
    view = WebView(ctx)

    def on_tap(x, y):
        if not view.lines:
            view.on_tap_message(x, y)
        else:
            view.on_tap(x, y)

    ctx.run(view.tick, fps=10, on_tap=on_tap, on_swipe=view.on_swipe)


if __name__ == "__main__":
    main()
