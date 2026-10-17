"""The DVD screensaver logo. Will it hit the corner? Here it does, now and then."""

import math

from engine import Clip, hsv, rgb, text_center, text_outlined

LOGO_W, LOGO_H = 96, 54
SPEED = 28.0  # pixels per second
COLORS = [hsv(hue, 0.8, 1.0) for hue in (0, 50, 120, 190, 230, 290)]


class DvdBounce(Clip):
    id = "dvd-bounce"
    title = "DVD Corner"
    fps = 30.0
    order = 50

    def start(self, ctx, area):
        super().start(ctx, area)
        self.span_x = max(1, area.w - LOGO_W)
        self.span_y = max(1, area.h - LOGO_H)
        self.period = math.lcm(self.span_x, self.span_y) / SPEED
        # Start just after leaving the top-left corner.
        self.offset = 1.5

    def draw(self, fb, t, index, full):
        travel = (t + self.offset) * SPEED
        x = self.bounce(travel, self.span_x)
        y = self.bounce(travel, self.span_y)
        bounces = int(travel // self.span_x) + int(travel // self.span_y)
        color = COLORS[bounces % len(COLORS)]
        corners = int((t + self.offset) // self.period)
        since_corner = (t + self.offset) - corners * self.period
        celebrating = corners > 0 and since_corner < 2.0
        if celebrating:
            fb.fill_rect(self.area.x, self.area.y, self.area.w, self.area.h, hsv(t * 720, 0.7, 0.35))
        self.logo(fb, self.area.x + x, self.area.y + y, color)
        if celebrating:
            text_outlined(fb, self.area.cx, self.area.y + self.area.h // 2 - 16, "CORNER!", rgb(255, 255, 255), scale=4)
        if corners:
            text_center(fb, self.area.cx, self.area.y + 6, "CORNERS: %d" % corners, rgb(120, 120, 120), 1)

    @staticmethod
    def bounce(travel, span):
        position = travel % (2 * span)
        return int(position if position < span else 2 * span - position)

    @staticmethod
    def logo(fb, x, y, color):
        fb.draw_text(x, y, "DVD", color, 4)
        # The disc under the letters, with "VIDEO" cut out of it.
        cx, cy, a, b = x + LOGO_W // 2, y + 44, LOGO_W // 2, 9
        for dy in range(-b, b + 1):
            half = int(a * math.sqrt(max(0.0, 1 - (dy / (b + 0.5)) ** 2)))
            fb.fill_rect(cx - half, cy + dy, 2 * half, 1, color)
        fb.draw_text(cx - 20, cy - 4, "VIDEO", 0, 1)


CLIP = DvdBounce()
