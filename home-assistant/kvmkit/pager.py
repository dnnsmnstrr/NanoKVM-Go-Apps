# Generated from _lib/kvmkit/pager.py by _utils/sync-kvmkit.py. Edit the master copy.
"""Pagination plus the header and footer chrome that paged Apps share.

    layout = Layout(ctx.fb)
    pager = Pager(layout, count=len(pages))
    # input
    pager.on_swipe(kind)            # up = next page, down = previous
    action = pager.on_tap(x, y)     # "prev"/"next" (already applied),
                                    # "middle", or None outside the footer
    # drawing
    pager.draw_header(fb, "Lights", right="23:40", dot=GOOD)
    pager.draw_footer(fb, status="4S AGO")

Header and footer text stays inside `Layout.safe_span()`, so it never runs
into the panel's rounded corners.
"""

from __future__ import annotations

from appbase import DOWN, UP, Rect

from . import text as kt
from .theme import BORDER, DIM, SUBTLE, TEXT

DOT = 6


class Pager:
    def __init__(self, layout, count=1):
        self.layout = layout
        self.count = max(1, count)
        self.index = 0

    def set_count(self, count):
        self.count = max(1, count)
        self.index = min(self.index, self.count - 1)

    def go(self, index):
        index %= self.count
        changed = index != self.index
        self.index = index
        return changed

    def step(self, direction):
        return self.go(self.index + direction)

    def on_swipe(self, kind):
        """Handle an up/down swipe. Returns True if the page changed."""
        if kind == UP:
            return self.step(1)
        if kind == DOWN:
            return self.step(-1)
        return False

    def zones(self):
        """(previous, middle, next) tap targets across the footer."""
        footer = self.layout.footer
        third = footer.w // 3
        return (Rect(footer.x, footer.y, third, footer.h),
                Rect(footer.x + third, footer.y, footer.w - 2 * third, footer.h),
                Rect(footer.x + footer.w - third, footer.y, third, footer.h))

    def on_tap(self, x, y):
        """Classify a tap in the footer and apply page changes."""
        previous, middle, following = self.zones()
        if previous.contains(x, y):
            self.step(-1)
            return "prev"
        if following.contains(x, y):
            self.step(1)
            return "next"
        if middle.contains(x, y):
            return "middle"
        return None

    def draw_header(self, fb, title, right="", right_color=SUBTLE, dot=None, scale=2):
        header = self.layout.header
        y = header.y + (header.h - 4 - 8 * scale) // 2
        left, right_edge = self.layout.safe_span(y, y + 8 * scale)
        right = kt.text(right)
        right_w = kt.width(right, scale)
        if right:
            fb.draw_text(right_edge - right_w, y, right, right_color, scale)
        if dot is not None:
            dot_x = right_edge - right_w - (DOT + 6 if right else DOT)
            fb.fill_rect(dot_x, y + (8 * scale - DOT) // 2, DOT, DOT, dot)
            right_w += DOT + 6
        title_room = right_edge - left - right_w - (10 if right_w else 0)
        fb.draw_text(left, y, kt.fit(title, title_room, scale), TEXT, scale)
        line_y = header.y + header.h - 4
        line_left, line_right = self.layout.safe_span(line_y, line_y + 1, margin=0)
        fb.fill_rect(line_left, line_y, line_right - line_left, 1, BORDER)

    def draw_footer(self, fb, status="", status_color=DIM, label=None):
        previous, middle, following = self.zones()
        cy = previous.y + previous.h // 2
        if self.count > 1:
            fb.draw_line(previous.cx + 4, cy - 7, previous.cx - 4, cy, TEXT)
            fb.draw_line(previous.cx - 4, cy, previous.cx + 4, cy + 7, TEXT)
            fb.draw_line(following.cx - 4, cy - 7, following.cx + 4, cy, TEXT)
            fb.draw_line(following.cx + 4, cy, following.cx - 4, cy + 7, TEXT)
        if label is None:
            label = "%d/%d" % (self.index + 1, self.count)
        fb.text_center(middle.cx, cy - 10, kt.text(label), SUBTLE, 1)
        if status:
            left, right = self.layout.safe_span(cy + 3, cy + 11)
            # The status may run wider than the middle zone, but not past the corners.
            room = min(right - left, middle.w + 40)
            fb.text_center(middle.cx, cy + 3, kt.fit(status, room), status_color, 1)
