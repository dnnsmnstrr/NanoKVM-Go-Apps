"""Screen geometry: the visible area and the panel's rounded corners.

Everything that depends on the physical panel lives here, so a correction
fixes every App at once:

- HIDDEN_EDGE / HIDDEN_PX: the strip the SDK documents as hidden on a panel
  that is physically 284x240. The NanoKVM Go's framebuffer is 240x284, and a
  calibration photo (2026-10-18) showed all of its 284x240 landscape canvas,
  so no strip is removed there.
- CORNER_RADIUS: the radius of the display's rounded corners. Fitting circles
  to the corner curves in the calibration photo gave 46 px (insets of
  26/17/8/3 px at 5/10/20/30 px from the edge). Rows close to the top or
  bottom edge must stay away from the sides by `corner_inset()`.

`Layout` splits the visible area into header, content and footer, and
`safe_span()` gives the x range that is fully visible for a band of rows.
"""

from __future__ import annotations

import math

from appbase import Rect

HIDDEN_PX = 14
# Which logical edge the hidden strip is on, per framebuffer rotation, for
# panels that are physically 284x240 (the SDK README's geometry).
HIDDEN_EDGE = {0: "left", 90: "bottom", 180: "right", 270: "top"}
CORNER_RADIUS = 46


def visible_rect(fb):
    """The logical rectangle the panel actually shows."""
    phys_w = getattr(fb, "phys_w", 284)
    phys_h = getattr(fb, "phys_h", 240)
    edge = HIDDEN_EDGE.get(fb.rotate % 360) if phys_w > phys_h else None
    x, y, w, h = 0, 0, fb.width, fb.height
    if edge == "left":
        x, w = HIDDEN_PX, w - HIDDEN_PX
    elif edge == "right":
        w -= HIDDEN_PX
    elif edge == "top":
        y, h = HIDDEN_PX, h - HIDDEN_PX
    elif edge == "bottom":
        h -= HIDDEN_PX
    return Rect(x, y, w, h)


def corner_inset(distance, radius=CORNER_RADIUS):
    """Horizontal inset for a row `distance` px from the top or bottom edge.

    Inside a rounded corner of radius r, the row at depth d is visible from
    r - sqrt(r^2 - (r - d)^2) onwards.
    """
    if radius <= 0 or distance >= radius:
        return 0
    depth = radius - max(0, distance)
    return int(math.ceil(radius - math.sqrt(radius * radius - depth * depth)))


class Layout:
    """Header, content and footer rectangles inside the visible area."""

    def __init__(self, fb, header_h=30, footer_h=34, radius=None):
        self.fb = fb
        self.radius = CORNER_RADIUS if radius is None else radius
        self.view = view = visible_rect(fb)
        self.header = Rect(view.x, view.y, view.w, header_h)
        self.footer = Rect(view.x, view.y + view.h - footer_h, view.w, footer_h)
        self.content = Rect(view.x, view.y + header_h, view.w, view.h - header_h - footer_h)

    def inset(self, top, bottom):
        """Inset that keeps rows [top, bottom) clear of all four corners."""
        view = self.view
        return max(corner_inset(top - view.y, self.radius),
                   corner_inset(view.y + view.h - bottom, self.radius))

    def safe_span(self, top, bottom, margin=4):
        """(left, right) x bounds that are fully visible for rows [top, bottom)."""
        inset = self.inset(top, bottom) + margin
        return self.view.x + inset, self.view.x + self.view.w - inset

    def content_span(self, margin=4):
        """safe_span() for the whole content area between header and footer."""
        content = self.content
        return self.safe_span(content.y, content.y + content.h, margin)
