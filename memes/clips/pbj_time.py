"""Peanut Butter Jelly Time: the dancing banana, drawn procedurally as pixel art."""

import math

from engine import SpriteClip, hsv, rgb, text_outlined

W, H = 36, 52
PALETTE = {
    "Y": rgb(255, 225, 53),   # banana
    "O": rgb(222, 170, 20),   # shading
    "B": rgb(110, 70, 20),    # stem and tip
    "K": rgb(20, 16, 10),     # outline, eyes, limbs
    "W": rgb(255, 255, 255),  # eyes, gloves
    "R": rgb(200, 40, 40),    # mouth and shoes
}


def banana(lean, left_up, right_up, legs, mouth_open):
    grid = [[" "] * W for _ in range(H)]

    def put(x, y, char):
        if 0 <= x < W and 0 <= y < H:
            grid[y][x] = char

    def line(x0, y0, x1, y1, char):
        steps = max(abs(x1 - x0), abs(y1 - y0), 1)
        for step in range(steps + 1):
            put(round(x0 + (x1 - x0) * step / steps), round(y0 + (y1 - y0) * step / steps), char)

    top, bottom = 4, 40
    edges = {}
    for y in range(top, bottom + 1):
        u = (y - top) / (bottom - top)
        center = 15 + 4.5 * math.sin(math.pi * u) + lean * (0.5 - u) * 2.2
        half = 0.8 + 5.4 * math.sin(math.pi * u) ** 0.6
        x0, x1 = round(center - half), round(center + half)
        edges[y] = (x0, x1, round(center))
        for x in range(x0, x1 + 1):
            put(x, y, "Y")
        put(x1 - 1, y, "O")
        put(x0, y, "K")
        put(x1, y, "K")
    # Stem on top, dark tip at the bottom.
    stem_x = edges[top][2]
    for y in range(top - 3, top + 1):
        put(stem_x, y, "B")
        put(stem_x + 1, y, "B")
    put(edges[bottom][2], bottom, "B")
    put(edges[bottom][2], bottom + 1, "B")

    # Face.
    eye_y = top + 11
    x0, x1, cx = edges[eye_y]
    for ex in (cx - 3, cx + 1):
        for dx in range(2):
            for dy in range(3):
                put(ex + dx, eye_y + dy, "W")
        put(ex + 1, eye_y + 1, "K")
        put(ex + 1, eye_y + 2, "K")
    mouth_y = eye_y + 6
    if mouth_open:
        for dx in range(-2, 3):
            put(cx + dx, mouth_y, "K")
        for dx in range(-1, 2):
            put(cx + dx, mouth_y + 1, "R")
            put(cx + dx, mouth_y + 2, "K")
    else:
        put(cx - 2, mouth_y, "K")
        put(cx + 2, mouth_y, "K")
        for dx in range(-1, 2):
            put(cx + dx, mouth_y + 1, "K")

    # Arms with white gloves.
    shoulder_y = top + 21
    x0, x1, _ = edges[shoulder_y]
    for side, up in ((-1, left_up), (1, right_up)):
        sx = x0 if side < 0 else x1
        hx, hy = sx + side * 7, shoulder_y + (-8 if up else 5)
        line(sx, shoulder_y, hx, hy, "K")
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                put(hx + dx + side, hy + dy, "W")

    # Legs and shoes.
    hip_y = bottom - 3
    _, _, cx = edges[hip_y]
    spread = 4 if legs else 2
    for side in (-1, 1):
        fx = cx + side * spread + (lean // 2)
        line(cx + side, hip_y, fx, H - 4, "K")
        for dx in range(-1, 2):
            put(fx + dx + side, H - 3, "R")
            put(fx + dx + side, H - 2, "R")
    return ["".join(row) for row in grid]


FRAMES = [
    banana(-3, True, False, True, True),
    banana(0, False, False, False, False),
    banana(3, False, True, True, True),
    banana(0, True, True, False, False),
]
COLORS = [hsv(hue, 0.55, 0.55) for hue in (280, 210, 160, 330)]


class PBJTime(SpriteClip):
    def background(self, index, t):
        return COLORS[(index // 2) % len(COLORS)]

    def decorate(self, fb, t, index):
        top = self.area.y + 8
        bottom = self.area.y + self.area.h - 26
        flash = hsv(t * 240, 0.9, 1.0)
        text_outlined(fb, self.area.cx, top, "PEANUT BUTTER", flash, scale=2)
        text_outlined(fb, self.area.cx, bottom, "JELLY TIME!", flash, scale=2)


CLIP = PBJTime("pbj-time", "Peanut Butter Jelly Time", FRAMES, PALETTE, fps=8, order=30, margins=(30, 30))
