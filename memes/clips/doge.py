"""Doge: such pixels, much KVM, wow."""

from engine import SpriteClip, rgb, text_outlined

FACE = [
    "     T            T     ",
    "    TTT          TTT    ",
    "    TdTT        TTdT    ",
    "   TTddTTTTTTTTTTddTT   ",
    "   TTTTTTTTTTTTTTTTTT   ",
    "  TTTddTTTTTTTTTTddTTT  ",
    "  TTTCCTTTTTTTTTTCCTTT  ",
    "  TTCWKCTTTTTTTTCWKCTT  ",
    " TTTCWKKCTTTTTTCWKKCTTT ",
    " TTTTCCCTTTTTTTTCCCTTTT ",
    " TTTTTTTTTTTTTTTTTTTTTT ",
    " TTCCCCCCCCKKKCCCCCCCTT ",
    "TTCCCCCCCCKKKKKCCCCCCCTT",
    "TCCCCCCCCCCKKKCCCCCCCCCT",
    "TCCCCCCCCCCCKCCCCCCCCCCT",
    "TCCCCCCCCCKKCKKCCCCCCCCT",
    " CCCCCCCCCCCCCCCCCCCCCC ",
    "  CCCCCCCCCCCCCCCCCCCC  ",
    "    CCCCCCCCCCCCCCCC    ",
    "       CCCCCCCCCC       ",
]
PALETTE = {
    "T": rgb(225, 165, 80),   # tan fur
    "d": rgb(150, 95, 40),    # inner ears
    "C": rgb(250, 235, 205),  # cream face
    "K": rgb(25, 20, 15),     # eyes, nose
    "W": rgb(255, 255, 255),  # eye shine
}
PHRASES = [
    ("WOW", rgb(255, 60, 200), 0.50, 0.12),
    ("SUCH KVM", rgb(60, 220, 255), 0.30, 0.82),
    ("MUCH REMOTE", rgb(255, 230, 40), 0.55, 0.92),
    ("VERY HDMI", rgb(120, 255, 90), 0.32, 0.20),
    ("SO USB", rgb(255, 120, 40), 0.70, 0.28),
    ("AMAZE", rgb(180, 120, 255), 0.72, 0.76),
]


class Doge(SpriteClip):
    def decorate(self, fb, t, index):
        shown = int(t / 0.7) % (len(PHRASES) + 3)
        for text, color, fx, fy in PHRASES[:shown]:
            x = self.area.x + int(self.area.w * fx)
            y = self.area.y + int(self.area.h * fy)
            text_outlined(fb, x, y, text, color, scale=2)


CLIP = Doge("doge", "Doge", [FACE], PALETTE, fps=1 / 0.7, bg=rgb(245, 245, 240), order=90, max_scale=8,
            margins=(40, 40))
