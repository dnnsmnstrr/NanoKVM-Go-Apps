#!/usr/bin/env python3
"""Meme player: tap for the next meme, swipe up/down to move through the list.

Memes are discovered from clips/*.py and assets/*.mem (see README.md), and
the MEMES env value picks and orders them.
"""

from __future__ import annotations

import random
import time
from pathlib import Path

from appbase import DOWN as SWIPE_DOWN, UP as SWIPE_UP, app

import engine
from kvmkit.screen import Layout

APP_DIR = Path(__file__).resolve().parent
TITLE_SECONDS = 2.0
BAND = engine.rgb(0, 0, 0)
BAND_TEXT = engine.rgb(255, 255, 255)
BAND_DIM = engine.rgb(150, 160, 175)


def enabled(value, default):
    value = (value or "").strip().lower()
    if not value:
        return default
    return value not in ("0", "off", "no", "false")


def seconds(value):
    try:
        return max(0.0, float(value or 0))
    except ValueError:
        return 0.0


class Player:
    def __init__(self, ctx, clips, titles=True, autoplay=0.0):
        self.ctx = ctx
        self.clips = clips
        self.titles = titles
        self.autoplay = autoplay
        self.area = engine.visible_rect(ctx.fb)
        self.layout = Layout(ctx.fb)
        self.position = 0
        self.clip = None
        self.show(0)

    def show(self, position, direction=1):
        if self.clip is not None:
            self.clip.stop()
            self.clip = None
        # Skip clips that fail to load, but never loop forever.
        for _ in range(len(self.clips)):
            clip = self.clips[position % len(self.clips)]
            try:
                clip.start(self.ctx, self.area)
            except Exception as exc:
                print("Memes: cannot start %s: %r" % (clip.id, exc))
                position += direction
                continue
            self.position = position % len(self.clips)
            self.clip = clip
            break
        self.started = time.monotonic()
        self.last_index = None
        self.full = True
        self.title_until = self.started + TITLE_SECONDS if self.titles else 0.0

    def step(self, direction):
        self.show(self.position + direction, direction)

    def on_tap(self, _x, _y):
        self.step(1)

    def on_swipe(self, kind, _x, _y):
        if kind == SWIPE_UP:
            self.step(1)
        elif kind == SWIPE_DOWN:
            self.step(-1)

    def tick(self, _dt):
        clip = self.clip
        if clip is None:
            if self.full:
                self.full = False
                self.ctx.fb.clear(BAND)
                engine.text_center(self.ctx.fb, self.area.cx, self.area.cy - 8, "NO MEMES", BAND_TEXT, 2)
            return True
        now = time.monotonic()
        t = now - self.started
        if self.autoplay and t >= self.autoplay and len(self.clips) > 1:
            self.step(1)
            return True
        title = now < self.title_until
        if not title and self.title_until:
            # The caption just expired: repaint the clip underneath it.
            self.title_until = 0.0
            self.full = True
        index = clip.index(t)
        if index == self.last_index and not self.full:
            return True
        fb = self.ctx.fb
        try:
            if self.full or not clip.persistent:
                fb.clear(clip.background(index, t))
            clip.draw(fb, t, index, self.full)
        except Exception as exc:
            print("Memes: %s failed: %r" % (clip.id, exc))
            self.step(1)
            return True
        if title:
            self.draw_title(clip)
        self.last_index = index
        self.full = False
        return True

    def draw_title(self, clip):
        fb = self.ctx.fb
        area = self.area
        band_h = 30
        y = area.y + area.h - band_h
        fb.fill_rect(area.x, y, area.w, band_h, BAND)
        counter = "%d/%d" % (self.position + 1, len(self.clips))
        # The band sits on the bottom edge: keep its text clear of the rounded corners.
        left, right = self.layout.safe_span(y + 7, y + 23)
        room = right - left - engine.text_width(counter) - 12
        scale = 2 if engine.text_width(clip.title, 2) <= room else 1
        title = clip.title[:max(0, room // (8 * scale))]
        engine.draw_text(fb, left, y + (7 if scale == 2 else 11), title, BAND_TEXT, scale)
        engine.draw_text(fb, right - engine.text_width(counter), y + 11, counter, BAND_DIM, 1)


@app()
def main(ctx):
    clips = engine.select(engine.discover(APP_DIR), ctx.env.get("MEMES") or "")
    if enabled(ctx.env.get("MEME_SHUFFLE"), False):
        random.shuffle(clips)
    player = Player(ctx, clips, titles=enabled(ctx.env.get("MEME_TITLES"), True),
                    autoplay=seconds(ctx.env.get("MEME_AUTOPLAY")))
    try:
        ctx.run(player.tick, fps=30, on_tap=player.on_tap, on_swipe=player.on_swipe)
    finally:
        if player.clip is not None:
            player.clip.stop()


if __name__ == "__main__":
    main()
