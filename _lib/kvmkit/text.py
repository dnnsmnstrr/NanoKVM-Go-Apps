"""Text helpers for the SDK's 8x8 ASCII font."""

from __future__ import annotations

FONT_CHARS = set(" $%-./0123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ")
# Characters the font lacks: close ASCII stand-ins, and German transliteration.
SUBSTITUTES = {
    "_": "-", ",": ".", ";": ":", "!": ".", "?": ".", "&": ".", "=": ":", "+": "-", "|": "/",
    "(": " ", ")": " ", "'": "", "°": "", "Ä": "AE", "Ö": "OE", "Ü": "UE",
    "ä": "AE", "ö": "OE", "ü": "UE", "ß": "SS", "é": "E", "è": "E",
}

# 8x8 glyphs for punctuation the SDK font lacks, drawn by draw_text().
EXTRA_GLYPHS = {
    "!": ("...##...", "...##...", "...##...", "...##...", "...##...", "........", "...##...", "........"),
    "'": ("...##...", "...##...", "..##....", "........", "........", "........", "........", "........"),
    "?": ("..####..", ".##..##.", ".....##.", "....##..", "...##...", "........", "...##...", "........"),
    ",": ("........", "........", "........", "........", "........", "...##...", "...##...", "..##...."),
    "+": ("........", "...##...", "...##...", ".######.", "...##...", "...##...", "........", "........"),
    "*": ("........", ".##..##.", "..####..", "########", "..####..", ".##..##.", "........", "........"),
    "<": ("....##..", "...##...", "..##....", ".##.....", "..##....", "...##...", "....##..", "........"),
    ">": ("..##....", "...##...", "....##..", ".....##.", "....##..", "...##...", "..##....", "........"),
    "&": ("..###...", ".##.##..", "..###...", ".###.##.", "##.###..", "##..##..", ".###.##.", "........"),
    "(": ("....##..", "...##...", "..##....", "..##....", "..##....", "...##...", "....##..", "........"),
    ")": ("..##....", "...##...", "....##..", "....##..", "....##..", "...##...", "..##....", "........"),
    "[": ("..####..", "..##....", "..##....", "..##....", "..##....", "..##....", "..####..", "........"),
    "]": ("..####..", "....##..", "....##..", "....##..", "....##..", "....##..", "..####..", "........"),
    '"': (".##..##.", ".##..##.", "..#..#..", "........", "........", "........", "........", "........"),
    "#": (".##.##..", ".##.##..", "#######.", ".##.##..", "#######.", ".##.##..", ".##.##..", "........"),
    "@": (".#####..", "##...##.", "##.####.", "##.####.", "##.###..", "##......", ".#####..", "........"),
    "=": ("........", "........", ".######.", "........", ".######.", "........", "........", "........"),
    "_": ("........", "........", "........", "........", "........", "........", "........", "########"),
    "|": ("...##...", "...##...", "...##...", "...##...", "...##...", "...##...", "...##...", "........"),
    ";": ("........", "...##...", "...##...", "........", "...##...", "...##...", "..##....", "........"),
}


def text(value, extra=False):
    """Uppercase and replace characters the 8x8 font cannot draw.

    With extra=True, characters in EXTRA_GLYPHS are kept; draw such text
    with draw_text() below rather than fb.draw_text().
    """
    result = []
    for char in str(value):
        if extra and char in EXTRA_GLYPHS:
            result.append(char)
            continue
        if char in SUBSTITUTES:
            result.append(SUBSTITUTES[char])
            continue
        char = char.upper()
        result.append(char if char in FONT_CHARS else " ")
    return "".join(result)


def width(value, scale=1):
    return len(value) * 8 * scale


def fit(value, pixels, scale=1):
    """Font-safe text trimmed to `pixels` wide."""
    return text(value)[:max(0, pixels // (8 * scale))]


def wrap(value, pixels, lines, scale=1):
    """Wrap at spaces where possible; split words (and URLs) that are too long."""
    limit = max(1, pixels // (8 * scale))
    chunks = []
    for word in text(value).split():
        if chunks and len(chunks[-1]) + 1 + len(word) <= limit:
            chunks[-1] += " " + word
            continue
        while len(word) > limit:
            chunks.append(word[:limit])
            word = word[limit:]
        chunks.append(word)
    if len(chunks) > lines:
        chunks = chunks[:lines]
        chunks[-1] = chunks[-1][:limit - 2] + ".."
    return chunks


def ago(seconds):
    """Compact duration: 5S, 12M, 3H 4M, 2D 1H."""
    if seconds is None:
        return "-"
    seconds = max(0, int(seconds))
    if seconds < 60:
        return "%dS" % seconds
    if seconds < 3600:
        return "%dM" % (seconds // 60)
    if seconds < 86400:
        return "%dH %dM" % (seconds // 3600, seconds % 3600 // 60)
    return "%dD %dH" % (seconds // 86400, seconds % 86400 // 3600)


def draw_text(fb, x, y, value, color, scale=1):
    """fb.draw_text plus the EXTRA_GLYPHS punctuation."""
    value = str(value).upper()
    start = 0
    for index, char in enumerate(value + "\0"):
        if char not in EXTRA_GLYPHS and char != "\0":
            continue
        if index > start:
            fb.draw_text(x + start * 8 * scale, y, value[start:index], color, scale)
        if char != "\0":
            gx = x + index * 8 * scale
            for row_index, row in enumerate(EXTRA_GLYPHS[char]):
                column = row.find("#")
                while column >= 0:
                    end = column
                    while end < 8 and row[end] == "#":
                        end += 1
                    fb.fill_rect(gx + column * scale, y + row_index * scale, (end - column) * scale, scale, color)
                    column = row.find("#", end)
        start = index + 1


def draw_center(fb, cx, y, value, color, scale=1):
    draw_text(fb, cx - width(value, scale) // 2, y, value, color, scale)


def draw_shadow(fb, cx, y, value, color, shadow=0, scale=2):
    """Centered text with a drop shadow (two passes, cheap on the device)."""
    offset = max(1, scale // 2)
    draw_center(fb, cx + offset, y + offset, value, shadow, scale)
    draw_center(fb, cx, y, value, color, scale)
