"""Shared pieces for meme clips: the Clip interface, sprite and video players,
packed GIF assets, discovery and the MEMES filter.

A clip draws one animation. The player calls `start()` when the clip comes
on screen, `index(t)` every tick, and `draw()` only when the index changes,
so a 10 FPS sprite costs nothing in between its frames. `stop()` releases
whatever `start()` loaded, keeping memory low on the device.
"""

from __future__ import annotations

import importlib
import lzma
import struct
import sys
import zlib
from array import array
from pathlib import Path

from appbase import Rect
from kvmkit.screen import visible_rect  # noqa: F401  (re-exported for clips)

BLACK = 0x0000
WHITE = 0xFFFF


def rgb(r, g, b):
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


def hsv(h, s=1.0, v=1.0):
    """RGB565 colour from hue (0-360), saturation and value (0-1)."""
    h = (h % 360) / 60.0
    c = v * s
    x = c * (1 - abs(h % 2 - 1))
    r, g, b = [(c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x)][int(h) % 6]
    m = v - c
    return rgb(int((r + m) * 255), int((g + m) * 255), int((b + m) * 255))


# -- text with a few extra glyphs ------------------------------------------------
# The SDK font lacks punctuation that memes need. These 8x8 glyphs fill in.
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
}


def text_width(value, scale=1):
    return len(value) * 8 * scale


def draw_text(fb, x, y, value, color, scale=1):
    """Like fb.draw_text, plus the EXTRA_GLYPHS punctuation."""
    value = value.upper()
    start = 0
    for index, char in enumerate(value + "\0"):
        if char in EXTRA_GLYPHS or char == "\0":
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


def text_center(fb, cx, y, value, color, scale=1):
    draw_text(fb, cx - text_width(value, scale) // 2, y, value, color, scale)


def text_outlined(fb, cx, y, value, color, outline=BLACK, scale=2):
    """Centered text with a drop shadow, readable on busy backgrounds.

    Two passes instead of a full outline: text is drawn pixel by pixel, so
    every extra pass costs as much as the text itself on the device.
    """
    offset = max(1, scale // 2)
    text_center(fb, cx + offset, y + offset, value, outline, scale)
    text_center(fb, cx, y, value, color, scale)


# -- clip interface -----------------------------------------------------------------

class Clip:
    """Base class for a meme. Subclasses set id/title and override draw()."""

    id = ""
    title = ""
    fps = 10.0
    order = 100
    # A persistent clip keeps its pixels between frames instead of being
    # cleared first (for example, falling trails). It must repaint fully when
    # draw() is called with full=True.
    persistent = False

    def start(self, ctx, area):
        self.ctx = ctx
        self.area = area

    def stop(self):
        pass

    def index(self, t):
        return int(t * self.fps)

    def background(self, index, t):
        return BLACK

    def draw(self, fb, t, index, full):
        raise NotImplementedError


# -- sprite clips -------------------------------------------------------------------

def build_runs(pixels, width, height, colors, ox, oy, scale, vertical):
    """Turn indexed pixels into (x, y, w, h, colour) rectangles on screen.

    Runs follow the axis that is contiguous in the physical framebuffer
    (columns for the usual 90/270 degree panel), so each fill_rect is cheap.
    `colors[i]` is None for transparent indices.
    """
    runs = array("H")
    if vertical:
        for x in range(width):
            y = 0
            while y < height:
                value = pixels[y * width + x]
                color = colors[value] if value < len(colors) else None
                end = y + 1
                while end < height and pixels[end * width + x] == value:
                    end += 1
                if color is not None:
                    runs.extend((ox + x * scale, oy + y * scale, scale, (end - y) * scale, color))
                y = end
    else:
        for y in range(height):
            x = 0
            row = y * width
            while x < width:
                value = pixels[row + x]
                color = colors[value] if value < len(colors) else None
                end = x + 1
                while end < width and pixels[row + end] == value:
                    end += 1
                if color is not None:
                    runs.extend((ox + x * scale, oy + y * scale, (end - x) * scale, scale, color))
                x = end
    return runs


def draw_runs(fb, runs):
    fill = fb.fill_rect
    values = iter(runs)
    for x, y, w, h, color in zip(values, values, values, values, values):
        fill(x, y, w, h, color)


def frames_from_strings(frames, palette):
    """Convert pixel-string frames into (width, height, indexed bytes, colours).

    `palette` maps characters to RGB565 colours; any other character is
    transparent. Rows may differ in length; short rows are padded.
    """
    chars = list(palette)
    lookup = {char: index for index, char in enumerate(chars)}
    transparent = len(chars)
    width = max(len(row) for frame in frames for row in frame)
    height = max(len(frame) for frame in frames)
    indexed = []
    for frame in frames:
        data = bytearray([transparent]) * (width * height)
        for y, row in enumerate(frame):
            for x, char in enumerate(row):
                data[y * width + x] = lookup.get(char, transparent)
        indexed.append(bytes(data))
    return width, height, indexed, [palette[char] for char in chars]


class SpriteClip(Clip):
    """Pixel-art frames scaled to fit the screen.

    frames: pixel-string frames (see frames_from_strings) or, via
            from_indexed(), raw indexed frames.
    margins: (top, bottom) pixels kept free, for example for captions.
    durations: optional per-frame durations in seconds instead of fps.
    """

    def __init__(self, id, title, frames=None, palette=None, fps=10.0, bg=BLACK, order=100,
                 margins=(0, 0), max_scale=None, durations=None):
        self.id = id
        self.title = title
        self.fps = fps
        self.bg = bg
        self.order = order
        self.margins = margins
        self.max_scale = max_scale
        self.durations = durations
        self._source = (frames, palette)
        self._indexed = None
        self._runs = {}

    @classmethod
    def from_indexed(cls, id, title, width, height, indexed, colors, **kwargs):
        clip = cls(id, title, **kwargs)
        clip._indexed = (width, height, indexed, colors)
        return clip

    def frames(self):
        if self._indexed is None:
            frames, palette = self._source
            self._indexed = frames_from_strings(frames, palette)
        return self._indexed

    def start(self, ctx, area):
        super().start(ctx, area)
        width, height, indexed, _ = self.frames()
        top, bottom = self.margins
        room_h = area.h - top - bottom
        scale = max(1, min(area.w // width, room_h // height))
        if self.max_scale:
            scale = min(scale, self.max_scale)
        self.scale = scale
        self.box = Rect(area.x + (area.w - width * scale) // 2,
                        area.y + top + (room_h - height * scale) // 2,
                        width * scale, height * scale)
        self.vertical = ctx.fb.rotate in (90, 270)
        self.count = len(indexed)
        if self.durations:
            self.total = sum(self.durations)
        self._runs = {}

    def stop(self):
        self._runs = {}

    def index(self, t):
        if self.durations:
            t %= self.total
            for frame, duration in enumerate(self.durations):
                t -= duration
                if t < 0:
                    return frame
            return self.count - 1
        return int(t * self.fps)

    def background(self, index, t):
        return self.bg

    def sprite_runs(self, frame):
        runs = self._runs.get(frame)
        if runs is None:
            width, height, indexed, colors = self.frames()
            runs = build_runs(indexed[frame], width, height, colors, self.box.x, self.box.y,
                              self.scale, self.vertical)
            self._runs[frame] = runs
        return runs

    def draw(self, fb, t, index, full):
        draw_runs(fb, self.sprite_runs(index % self.count))
        self.decorate(fb, t, index)

    def decorate(self, fb, t, index):
        """Hook for captions or effects drawn over the sprite."""


# -- packed GIF assets ----------------------------------------------------------------
# MEM1: magic, u16 width, u16 height, u16 frames, u8 colours, u8 transparent
# index (255 = none), u8 title length, title, u16 frame durations in ms,
# u16 RGB565 palette, then zlib-compressed indexed pixels for all frames.
MEM_MAGIC = b"MEM1"
MEM_HEADER = struct.Struct("<4sHHHBBB")


def load_packed(path, order=200):
    data = Path(path).read_bytes()
    magic, width, height, count, ncolors, transparent, title_len = MEM_HEADER.unpack_from(data, 0)
    if magic != MEM_MAGIC:
        raise ValueError("%s is not a MEM1 asset" % path)
    offset = MEM_HEADER.size
    title = data[offset:offset + title_len].decode("utf-8")
    offset += title_len
    durations = struct.unpack_from("<%dH" % count, data, offset)
    offset += 2 * count
    colors = list(struct.unpack_from("<%dH" % ncolors, data, offset))
    offset += 2 * ncolors
    pixels = zlib.decompress(data[offset:])
    size = width * height
    if len(pixels) != size * count:
        raise ValueError("%s has a truncated pixel block" % path)
    if transparent < ncolors:
        colors[transparent] = None
    indexed = [pixels[i * size:(i + 1) * size] for i in range(count)]
    stem = Path(path).stem
    return SpriteClip.from_indexed(stem, title or stem.replace("-", " ").title(), width, height, indexed, colors,
                                   durations=[max(20, d) / 1000.0 for d in durations], order=order)


# -- 1-bit video (BAP2, used by Bad Apple) ------------------------------------------------
BAP_MAGIC = b"BAP2"
BAP_HEADER = struct.Struct("<4sHHHHHI")
BAP_CHUNK = struct.Struct("<II")


class FrameStore:
    """Read 1-bit frames from a chunked, LZMA2-compressed BAP2 asset.

    Only the chunk that holds the requested frame is decompressed, and it is
    reused for the following frames in that chunk.
    """

    def __init__(self, path):
        self.file = open(path, "rb")
        self.chunk_index = -1
        self.chunk_data = b""
        try:
            header = self.file.read(BAP_HEADER.size)
            (magic, self.width, self.height, self.fps_num, self.fps_den,
             self.chunk_frames, self.count) = BAP_HEADER.unpack(header)
            if magic != BAP_MAGIC or not (self.fps_num and self.fps_den and self.count and self.chunk_frames):
                raise ValueError("%s is not a valid BAP2 asset" % path)
            self.row_bytes = (self.width + 7) // 8
            self.frame_bytes = self.row_bytes * self.height
            chunks = (self.count + self.chunk_frames - 1) // self.chunk_frames
            self.index = [BAP_CHUNK.unpack(self.file.read(BAP_CHUNK.size)) for _ in range(chunks)]
            self.payload_offset = BAP_HEADER.size + BAP_CHUNK.size * chunks
        except Exception:
            self.close()
            raise

    @property
    def fps(self):
        return self.fps_num / self.fps_den

    def read(self, frame_number):
        chunk = frame_number // self.chunk_frames
        if chunk != self.chunk_index:
            offset, length = self.index[chunk]
            self.file.seek(self.payload_offset + offset)
            self.chunk_data = lzma.decompress(self.file.read(length))
            self.chunk_index = chunk
        start = (frame_number % self.chunk_frames) * self.frame_bytes
        return self.chunk_data[start:start + self.frame_bytes]

    def close(self):
        if getattr(self, "file", None) is not None:
            self.file.close()
            self.file = None


class VideoClip(Clip):
    """Full-screen 1-bit video, center-cropped to cover the visible area."""

    def __init__(self, id, title, path, order=100, color=WHITE):
        self.id = id
        self.title = title
        self.path = Path(path)
        self.order = order
        self.color = color
        self.frames = None
        self.fps = 30.0

    def start(self, ctx, area):
        super().start(ctx, area)
        self.frames = FrameStore(self.path)
        self.fps = self.frames.fps
        self.plan = self._plan(ctx.fb.rotate in (90, 270))

    def stop(self):
        if self.frames is not None:
            self.frames.close()
            self.frames = None

    def index(self, t):
        return int(t * self.fps) % self.frames.count

    def _plan(self, vertical):
        frames, area = self.frames, self.area
        sw, sh = frames.width, frames.height
        if area.w * sh > area.h * sw:
            crop_w, crop_h = sw, max(1, area.h * sw // area.w)
        else:
            crop_w, crop_h = max(1, area.w * sh // area.h), sh
        crop_x, crop_y = (sw - crop_w) // 2, (sh - crop_h) // 2
        return {
            "vertical": vertical,
            "crop_w": crop_w,
            "crop_h": crop_h,
            "x_bounds": [c * area.w // crop_w for c in range(crop_w + 1)],
            "y_bounds": [(r * area.h + crop_h - 1) // crop_h for r in range(crop_h + 1)],
            "row_starts": [(crop_y + r) * frames.row_bytes for r in range(crop_h)],
            "column_bytes": [(crop_x + c) // 8 for c in range(crop_w)],
            "column_masks": [0x80 >> ((crop_x + c) % 8) for c in range(crop_w)],
        }

    def draw(self, fb, t, index, full):
        frame = self.frames.read(index)
        plan = self.plan
        fill, color = fb.fill_rect, self.color
        ax, ay = self.area.x, self.area.y
        xb, yb = plan["x_bounds"], plan["y_bounds"]
        rows, cbytes, cmasks = plan["row_starts"], plan["column_bytes"], plan["column_masks"]
        crop_w, crop_h = plan["crop_w"], plan["crop_h"]
        if plan["vertical"]:
            for column in range(crop_w):
                start = None
                byte, mask = cbytes[column], cmasks[column]
                for row in range(crop_h + 1):
                    filled = row < crop_h and frame[rows[row] + byte] & mask
                    if filled and start is None:
                        start = row
                    elif not filled and start is not None:
                        x0, x1, y0, y1 = xb[column], xb[column + 1], yb[start], yb[row]
                        if x1 > x0 and y1 > y0:
                            fill(ax + x0, ay + y0, x1 - x0, y1 - y0, color)
                        start = None
            return
        for row in range(crop_h):
            start = None
            base = rows[row]
            for column in range(crop_w + 1):
                filled = column < crop_w and frame[base + cbytes[column]] & cmasks[column]
                if filled and start is None:
                    start = column
                elif not filled and start is not None:
                    x0, x1, y0, y1 = xb[start], xb[column], yb[row], yb[row + 1]
                    if x1 > x0 and y1 > y0:
                        fill(ax + x0, ay + y0, x1 - x0, y1 - y0, color)
                    start = None


# -- discovery and filtering -------------------------------------------------------------

def discover(app_dir):
    """Collect clips from clips/*.py (CLIP or CLIPS) and assets/*.mem files."""
    app_dir = Path(app_dir)
    if str(app_dir) not in sys.path:
        sys.path.insert(0, str(app_dir))
    clips = []
    for path in sorted((app_dir / "clips").glob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            module = importlib.import_module("clips." + path.stem)
            found = getattr(module, "CLIPS", None)
            clips.extend(found if found is not None else [module.CLIP])
        except Exception as exc:  # one broken meme must not break the others
            print("Memes: skipping clips/%s: %r" % (path.name, exc))
    known = {clip.id for clip in clips}
    for path in sorted((app_dir / "assets").glob("*.mem")):
        if path.stem in known:
            continue
        try:
            clips.append(load_packed(path))
        except Exception as exc:
            print("Memes: skipping assets/%s: %r" % (path.name, exc))
    clips.sort(key=lambda clip: (clip.order, clip.title.lower()))
    return clips


def normalize(name):
    return "".join(char if char.isalnum() else "-" for char in name.strip().lower()).strip("-")


def select(clips, spec):
    """Apply the MEMES filter.

    `spec` lists ids (or titles) in play order, separated by commas or spaces.
    Entries starting with "-" are excluded. With no positive entries every
    clip plays in the default order. Unknown names are ignored, and if
    nothing is left the full list is used.
    """
    by_name = {}
    for clip in clips:
        by_name.setdefault(clip.id, clip)
        by_name.setdefault(normalize(clip.title), clip)
    # Commas allow titles with spaces ("Nyan Cat, -Bad Apple"); otherwise
    # whitespace separates ids ("nyan-cat -bad-apple").
    parts = spec.split(",") if "," in spec else spec.split()
    tokens = [token.strip() for token in parts if token.strip().strip("-")]
    excluded = {by_name[normalize(token[1:])].id for token in tokens
                if token.startswith("-") and normalize(token[1:]) in by_name}
    included = [by_name[normalize(token)] for token in tokens
                if not token.startswith("-") and normalize(token) in by_name]
    chosen = included or list(clips)
    seen = set()
    result = []
    for clip in chosen:
        if clip.id not in excluded and clip.id not in seen:
            seen.add(clip.id)
            result.append(clip)
    return result or list(clips)
