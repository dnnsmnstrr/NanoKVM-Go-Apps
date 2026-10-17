"""Keyboard Cat: a cat in a blue shirt plays him off. Fitting for a KVM."""

import math

from engine import SpriteClip, rgb

W, H = 44, 42
PALETTE = {
    "O": rgb(240, 150, 50),   # fur
    "D": rgb(180, 95, 25),    # stripes
    "L": rgb(255, 225, 190),  # muzzle
    "P": rgb(255, 130, 160),  # nose, inner ears
    "K": rgb(15, 15, 20),     # eyes, outlines
    "W": rgb(250, 250, 250),  # white keys, eye shine
    "G": rgb(55, 55, 65),     # keyboard body
    "S": rgb(40, 90, 200),    # shirt
    "s": rgb(25, 60, 150),    # shirt shade
    "Y": rgb(255, 220, 60),   # pressed key
    "N": rgb(180, 240, 255),  # music notes
}


def frame(step):
    grid = [[" "] * W for _ in range(H)]

    def put(x, y, char):
        if 0 <= x < W and 0 <= y < H:
            grid[y][x] = char

    bob = 1 if step % 2 else 0
    cx, cy = 22, 11 + bob
    # Shirt: a trapezoid under the head.
    for y in range(cy + 7, 32):
        spread = 7 + (y - cy - 7) // 2
        for x in range(cx - spread, cx + spread + 1):
            put(x, y, "s" if x in (cx - spread, cx + spread) else "S")
    # Head with ears.
    for y in range(cy - 8, cy + 9):
        for x in range(cx - 10, cx + 11):
            if ((x - cx) / 9.5) ** 2 + ((y - cy) / 7.5) ** 2 <= 1:
                put(x, y, "O")
    for side in (-1, 1):
        for row in range(5):
            for col in range(row + 2):
                x = cx + side * (9 - col)
                put(x, cy - 10 + row, "P" if 0 < col < row and row > 1 else "O")
    for sx in (-3, 0, 3):  # forehead stripes
        put(cx + sx, cy - 6, "D")
        put(cx + sx, cy - 5, "D")
    for side in (-1, 1):
        put(cx + side * 9, cy, "D")
        put(cx + side * 9, cy + 2, "D")
    for ex in (cx - 5, cx + 3):  # eyes
        for dx in range(3):
            for dy in range(3):
                put(ex + dx, cy - 2 + dy, "K")
        put(ex + 1, cy - 2, "W")
    for y in range(cy + 2, cy + 7):  # muzzle
        for x in range(cx - 4, cx + 5):
            if ((x - cx) / 4.5) ** 2 + ((y - cy - 4) / 2.6) ** 2 <= 1:
                put(x, y, "L")
    put(cx, cy + 2, "P")
    put(cx - 1, cy + 2, "P")
    put(cx, cy + 4, "K")
    put(cx - 2, cy + 5, "K")
    put(cx + 1, cy + 5, "K")

    # Keyboard with white and black keys.
    top = 33
    for y in range(top, top + 8):
        for x in range(1, W - 1):
            put(x, y, "G")
    keys = list(range(3, W - 4, 4))
    pressed = (keys[2 + (step % 3)], keys[-3 - (step * 2 % 3)])
    for kx in keys:
        for y in range(top + 1, top + 7):
            for x in range(kx, kx + 3):
                put(x, y, "Y" if kx in pressed and y > top + 1 else "W")
        if kx + 3 < W - 3:
            for y in range(top + 1, top + 4):
                put(kx + 3, y, "K")

    # Paws: one presses while the other lifts.
    for side, kx in ((-1, pressed[0]), (1, pressed[1])):
        down = (step % 2 == 0) == (side < 0)
        py = top - (0 if down else 3)
        shoulder_x = cx + side * 8
        for y in range(cy + 9, py):
            x = shoulder_x + round((kx + 1 - shoulder_x) * (y - cy - 9) / max(1, py - cy - 9))
            put(x, y, "S")
            put(x + 1, y, "S")
        for dx in range(-1, 3):
            for dy in range(2):
                put(kx + dx, py + dy, "O")

    # Two music notes drifting up.
    for index, base_x in enumerate((4, 37)):
        ny = 12 - ((step + index * 3) % 6) * 2
        put(base_x, ny, "N")
        put(base_x + 1, ny, "N")
        for y in range(ny - 4, ny):
            put(base_x + 1, y, "N")
        put(base_x + 2, ny - 4, "N")
    return ["".join(row) for row in grid]


CLIP = SpriteClip("keyboard-cat", "Keyboard Cat", [frame(step) for step in range(6)], PALETTE,
                  fps=6, bg=rgb(70, 40, 90), order=60, max_scale=5)
