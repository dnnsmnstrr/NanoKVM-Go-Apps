#!/usr/bin/env python3
"""Convert an animated GIF into a Memes App asset (assets/<id>.mem).

Run this on your computer, not on the NanoKVM (it needs Pillow):

    python3 -m pip install pillow
    tools/gif_to_meme.py party.gif --title "Party Time" --size 80

The GIF is scaled to fit --size pixels (the App scales it up again with
crisp pixels), reduced to --colors shared colours, and stored as MEM1:

    magic "MEM1", u16 width, u16 height, u16 frame count, u8 colour count,
    u8 transparent index (255 = none), u8 title length, UTF-8 title,
    u16 frame durations in ms, u16 RGB565 palette,
    zlib-compressed indexed pixels (one byte per pixel, all frames).

Smaller sizes and fewer frames keep the device fast: the App precomputes
pixel runs per frame, so 64-96 px and up to ~60 frames work well.
"""

from __future__ import annotations

import argparse
import struct
import sys
import zlib
from pathlib import Path

try:
    from PIL import Image, ImageSequence
except ImportError:  # pragma: no cover - only hit without Pillow
    sys.exit("This tool needs Pillow: python3 -m pip install pillow")

MAGIC = b"MEM1"
HEADER = struct.Struct("<4sHHHBBB")


def rgb565(r, g, b):
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


def load_frames(path, size, smooth, max_frames, skip):
    image = Image.open(path)
    frames, durations = [], []
    for index, frame in enumerate(ImageSequence.Iterator(image)):
        duration = frame.info.get("duration", image.info.get("duration", 100)) or 100
        if skip > 1 and index % skip:
            if durations:
                durations[-1] += duration
            continue
        rgba = frame.convert("RGBA")
        scale = min(size / rgba.width, size / rgba.height, 1.0)
        target = (max(1, round(rgba.width * scale)), max(1, round(rgba.height * scale)))
        if target != rgba.size:
            rgba = rgba.resize(target, Image.LANCZOS if smooth else Image.NEAREST)
        frames.append(rgba)
        durations.append(duration)
        if len(frames) >= max_frames:
            break
    if not frames:
        raise SystemExit("%s has no frames" % path)
    return frames, durations


def pack(frames, durations, colors, title):
    width, height = frames[0].size
    # One palette for all frames: quantize a strip that holds every frame.
    strip = Image.new("RGB", (width, height * len(frames)))
    masks = []
    for index, frame in enumerate(frames):
        strip.paste(frame.convert("RGB"), (0, index * height))
        masks.append([alpha < 128 for alpha in frame.getchannel("A").tobytes()])
    transparent = any(any(mask) for mask in masks)
    usable = min(colors, 254 if transparent else 255)
    quantized = strip.quantize(colors=usable, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    raw_palette = quantized.getpalette()[:usable * 3]
    palette = [rgb565(*raw_palette[i:i + 3]) for i in range(0, len(raw_palette), 3)]
    pixels = bytearray(quantized.tobytes())
    transparent_index = 255
    if transparent:
        transparent_index = len(palette)
        palette.append(0)
        size = width * height
        for index, mask in enumerate(masks):
            base = index * size
            for offset, clear in enumerate(mask):
                if clear:
                    pixels[base + offset] = transparent_index
    title_bytes = title.encode("utf-8")[:255]
    return (HEADER.pack(MAGIC, width, height, len(frames), len(palette), transparent_index, len(title_bytes))
            + title_bytes
            + struct.pack("<%dH" % len(durations), *[min(65535, d) for d in durations])
            + struct.pack("<%dH" % len(palette), *palette)
            + zlib.compress(bytes(pixels), 9))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("gif", type=Path)
    parser.add_argument("--output", type=Path, help="default: assets/<gif name>.mem next to this tool")
    parser.add_argument("--title", help="name shown in the App (default: from the file name)")
    parser.add_argument("--size", type=int, default=80, help="longest side in pixels (default 80)")
    parser.add_argument("--colors", type=int, default=32, help="palette size, 2-255 (default 32)")
    parser.add_argument("--max-frames", type=int, default=60)
    parser.add_argument("--skip", type=int, default=1, help="keep every Nth frame (default 1)")
    parser.add_argument("--smooth", action="store_true", help="smooth scaling for photos (default: crisp pixels)")
    args = parser.parse_args(argv)

    meme_id = "".join(c if c.isalnum() else "-" for c in args.gif.stem.lower()).strip("-")
    output = args.output or Path(__file__).resolve().parent.parent / "assets" / (meme_id + ".mem")
    title = args.title or args.gif.stem.replace("-", " ").replace("_", " ").title()
    frames, durations = load_frames(args.gif, args.size, args.smooth, args.max_frames, max(1, args.skip))
    blob = pack(frames, durations, max(2, min(255, args.colors)), title)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(blob)
    width, height = frames[0].size
    print("%s: %d frames %dx%d, %d KiB, id %r" % (output, len(frames), width, height, len(blob) // 1024, output.stem))
    return 0


if __name__ == "__main__":
    sys.exit(main())
