"""It's over 9000! A scouter reading climbs until it breaks the scale."""

import random

from engine import Clip, rgb, text_center, text_outlined

LOOP = 8.0
CLIMB = 3.5
GREEN = rgb(80, 255, 120)
DARK = rgb(4, 30, 12)
SCAN = rgb(10, 48, 22)
RED = rgb(255, 60, 40)
YELLOW = rgb(255, 230, 60)


class Over9000(Clip):
    id = "over-9000"
    title = "It's Over 9000"
    fps = 20.0
    order = 70

    def background(self, index, t):
        return DARK

    def draw(self, fb, t, index, full):
        area = self.area
        # Scanline texture along the axis that is contiguous in the physical
        # framebuffer: one cheap column write per line instead of 240.
        if fb.rotate in (90, 270):
            for x in range(area.x, area.x + area.w, 6):
                fb.fill_rect(x, area.y, 2, area.h, SCAN)
        else:
            for y in range(area.y, area.y + area.h, 6):
                fb.fill_rect(area.x, y, area.w, 2, SCAN)
        phase = t % LOOP
        cy = area.y + area.h // 2
        if phase < CLIMB:
            progress = phase / CLIMB
            value = int(9001 * progress ** 3)
            text_center(fb, area.cx, cy - 60, "POWER LEVEL", GREEN, 2)
            color = GREEN if value < 8000 else YELLOW
            text_center(fb, area.cx, cy - 20, "%d" % value, color, 5)
            bar = int((area.w - 40) * progress)
            fb.fill_rect(area.x + 20, cy + 40, area.w - 40, 10, SCAN)
            fb.fill_rect(area.x + 20, cy + 40, bar, 10, color)
            return
        rng = random.Random(index)
        jx, jy = rng.randint(-3, 3), rng.randint(-3, 3)
        flash = RED if index % 4 < 2 else YELLOW
        text_outlined(fb, area.cx + jx, cy - 70 + jy, "IT'S", flash, scale=4)
        text_outlined(fb, area.cx + jx, cy - 30 + jy, "OVER", flash, scale=4)
        text_outlined(fb, area.cx - jx, cy + 16 - jy, "9000!", flash, scale=5)


CLIP = Over9000()
