"""Party Parrot: a bobbing parrot that cycles through the rainbow."""

import math

from engine import SpriteClip, hsv, rgb

PARROT = [
    "         PPPPPP          ",
    "       PPPPPPPPPP        ",
    "      PPPPPPPPPPPP       ",
    "     PPFFFFPPPPPPPP      ",
    "    PPFFWWFFPPPPPPPP     ",
    "    PFFWKKWFPPPPPPPPP    ",
    "   BBFFWKKWFPPPPPPPPP    ",
    "  BBBBFFWWFFPPPPPPPPPP   ",
    " BBBBBBFFFFPPPPPPPPPPP   ",
    " BBBBBBBFFPPPPPPPPPPPPP  ",
    "  BBBBB FPPPPPDPPPPPPPP  ",
    "   BBB  PPPPPPDDPPPPPPP  ",
    "    B   PPPPPPPDDPPPPPPP ",
    "        PPPPPPPPDDPPPPPP ",
    "         PPPPPPPPDDPPPPP ",
    "          PPPPPPPPDDDPPP ",
    "           PPPPPPPPPDDD  ",
    "            PPPPPPPPDD   ",
    "              PPPPPDD    ",
    "                DDD      ",
]
STEPS = 10
SIZE = 31  # canvas leaves room for the bob


def frame(step):
    body, shade, face = chr(ord("0") + step), chr(ord("a") + step), chr(ord("k") + step)
    angle = 2 * math.pi * step / STEPS
    dx, dy = round(2.5 * math.cos(angle)), round(2.5 * math.sin(angle))
    rows = [" " * SIZE for _ in range(SIZE)]
    for y, row in enumerate(PARROT):
        line = list(rows[y + 4 + dy])
        for x, char in enumerate(row):
            if char != " ":
                line[x + 3 + dx] = {"P": body, "D": shade, "F": face}.get(char, char)
        rows[y + 4 + dy] = "".join(line)
    return rows


PALETTE = {"B": rgb(170, 170, 170), "W": rgb(255, 255, 255), "K": rgb(0, 0, 0)}
for step in range(STEPS):
    PALETTE[chr(ord("0") + step)] = hsv(step * 360 / STEPS, 0.85, 1.0)
    PALETTE[chr(ord("a") + step)] = hsv(step * 360 / STEPS, 0.9, 0.7)
    PALETTE[chr(ord("k") + step)] = hsv(step * 360 / STEPS + 30, 0.45, 1.0)

CLIP = SpriteClip("party-parrot", "Party Parrot", [frame(step) for step in range(STEPS)], PALETTE,
                  fps=15, bg=rgb(10, 10, 14), order=40, max_scale=8)
