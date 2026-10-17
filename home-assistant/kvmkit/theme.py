# Generated from _lib/kvmkit/theme.py by _utils/sync-kvmkit.py. Edit the master copy.
"""Shared colours, so Apps look like one family."""

from __future__ import annotations


def rgb(r, g, b):
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


BG = rgb(10, 12, 18)
PANEL = rgb(24, 28, 38)
PANEL_ACTIVE = rgb(40, 48, 64)
BORDER = rgb(60, 68, 86)
TEXT = rgb(255, 255, 255)
SUBTLE = rgb(150, 160, 175)
DIM = rgb(95, 102, 118)
ACCENT = rgb(90, 170, 210)
GOOD = rgb(40, 200, 110)
WARN = rgb(255, 170, 40)
BAD = rgb(240, 70, 70)
INFO = rgb(90, 130, 200)
