"""Matrix digital rain: every hacker movie meme, in 8x8 glyphs."""

import random

from engine import Clip, rgb

CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ$%:./-"
HEAD = rgb(220, 255, 220)
BRIGHT = rgb(60, 255, 100)
MID = rgb(20, 170, 60)
DIM = rgb(10, 80, 30)
CELL_W, CELL_H = 8, 10


class MatrixRain(Clip):
    id = "matrix-rain"
    title = "Matrix Rain"
    fps = 15.0
    order = 80
    persistent = True

    def start(self, ctx, area):
        super().start(ctx, area)
        self.rng = random.Random(1999)
        self.cols = area.w // CELL_W
        self.rows = area.h // CELL_H
        self.ox = area.x + (area.w - self.cols * CELL_W) // 2
        self.drops = [self.new_drop(initial=True) for _ in range(self.cols)]
        self.last = None

    def new_drop(self, initial=False):
        start = -self.rng.randint(0, self.rows if initial else self.rows // 2)
        return {"head": start, "length": self.rng.randint(6, 18), "speed": self.rng.choice((1, 1, 1, 2))}

    def glyph(self, fb, column, row, color):
        if 0 <= row < self.rows:
            x, y = self.ox + column * CELL_W, self.area.y + row * CELL_H
            fb.fill_rect(x, y, CELL_W, CELL_H, 0)
            if color:
                fb.draw_text(x, y + 1, self.rng.choice(CHARS), color, 1)

    def draw(self, fb, t, index, full):
        steps = 1 if self.last is None or full else max(1, min(4, index - self.last))
        self.last = index
        for _ in range(steps):
            for column, drop in enumerate(self.drops):
                if index % drop["speed"]:
                    continue
                head = drop["head"]
                self.glyph(fb, column, head - 1, BRIGHT)
                self.glyph(fb, column, head - 4, MID)
                self.glyph(fb, column, head - drop["length"] // 2 - 3, DIM)
                self.glyph(fb, column, head - drop["length"], None)
                self.glyph(fb, column, head, HEAD)
                drop["head"] = head + 1
                if head - drop["length"] > self.rows:
                    self.drops[column] = self.new_drop()


CLIP = MatrixRain()
