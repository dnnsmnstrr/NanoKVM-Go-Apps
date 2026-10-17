# Memes

Animated memes on the NanoKVM screen. **Tap** for the next meme, **swipe
up/down** to go forward or back. Each meme's name shows for two seconds when it
starts.

| Id | Meme |
| --- | --- |
| `bad-apple` | Bad Apple!! shadow-art video (1-bit, 30 FPS) |
| `nyan-cat` | Nyan Cat, 12-frame sprite from klange/nyancat |
| `pbj-time` | Peanut Butter Jelly Time: the dancing banana |
| `party-parrot` | Party Parrot, cycling through the rainbow |
| `dvd-bounce` | The DVD logo. It does hit the corner, every ~15 s |
| `keyboard-cat` | Keyboard Cat plays him off |
| `over-9000` | A power level that climbs until it's over 9000! |
| `matrix-rain` | Matrix digital rain |
| `doge` | Doge: wow, such KVM |

Everything except Bad Apple is original pixel art or drawn in code, so the
App bundles no third-party GIFs.

## Settings

| Env | Default | Meaning |
| --- | --- | --- |
| `MEMES` | empty | Which memes to play, in order (see below) |
| `MEME_AUTOPLAY` | `0` | Seconds before moving on by itself; `0` waits for a tap |
| `MEME_SHUFFLE` | `off` | `on` plays them in random order |
| `MEME_TITLES` | `on` | `off` hides the name caption |

`MEMES` takes ids separated by spaces or commas, for example
`nyan-cat pbj-time dvd-bounce`. Only those memes play, in that order.
Prefix an id with `-` to keep everything except it, for example
`-bad-apple -matrix-rain`. With commas, titles work too:
`Nyan Cat, Peanut Butter Jelly Time`. Unknown names are ignored, and if
nothing matches, every meme plays.

## Adding memes

The App plays everything it finds in `clips/*.py` and `assets/*.mem`. A new
meme is one new file, with no registration step. After adding one, zip and
reinstall the App.

### From a GIF

Convert the GIF on your computer (needs Pillow):

```sh
python3 -m pip install pillow
memes/tools/gif_to_meme.py ~/Downloads/this-is-fine.gif --title "This Is Fine"
```

This writes `memes/assets/this-is-fine.mem`, and its id is the file name. The
GIF is scaled to fit 80 px (`--size`), reduced to 32 shared colours
(`--colors`), and keeps its frame timing and transparency. On screen it is
scaled back up with crisp pixels. Small GIFs work best: 64–96 px and up to
about 60 frames (`--max-frames`, or `--skip 2` to keep every second frame).
Use `--smooth` for photographic GIFs. Only add GIFs you are allowed to share.

### As pixel art (like Nyan Cat)

Draw frames as strings, one character per pixel, and map characters to
colours. Characters missing from the palette are transparent:

```python
# memes/clips/heart.py
from engine import SpriteClip, rgb

FRAMES = [
    [" RR RR ", "RRRRRRR", "RRRRRRR", " RRRRR ", "  RRR  ", "   R   "],
    ["       ", " RR RR ", " RRRRR ", "  RRR  ", "   R   ", "       "],
]
CLIP = SpriteClip("heart", "Heartbeat", FRAMES, {"R": rgb(230, 30, 60)}, fps=4, order=100)
```

`SpriteClip` scales the frames to fill the screen. It also takes `bg`,
`margins=(top, bottom)` to keep room for captions, `max_scale`, and per-frame
`durations`. Override `background()` or `decorate()` for flashing colours or
text, as `pbj_time.py` and `doge.py` do.

### As code

Subclass `engine.Clip` and implement `draw(fb, t, index, full)`. `t` is the
number of seconds since the meme started. `index` is `int(t * fps)`, and the
player only calls `draw()` when it changes. See `dvd_bounce.py` and
`over_9000.py`. Set `persistent = True` to keep the previous frame instead of
starting from a cleared screen (`matrix_rain.py`).

Drawing is pure Python on a slow CPU. Text is drawn pixel by pixel, and at
the usual 90° rotation a vertical `fill_rect` is cheap while a horizontal
line costs one write per column. Aim for a few milliseconds per frame.
`engine.draw_text()` adds `! ' ? , + * < > &` to the SDK's 8x8 font.

### Ideas that would fit

This Is Fine (the dog in the burning room), the Rickroll dance, Coffin Dance,
Dancing Baby, Hampster Dance, the Windows XP hill with a BSOD, "Loading..."
with a spinner that never finishes, a "Distracted Boyfriend" frame, or any
GIF in your own collection.

## Bad Apple asset

`assets/bad-apple.bin` is a `BAP2` container holding 240x180, 30 FPS, 1-bit
frames, packed in LZMA2-compressed chunks of 32. Only the chunk that holds the
current frame is decompressed. Regenerate it from the source video
(https://www.youtube.com/watch?v=FtutLA63Cp8) with:

```sh
ffmpeg -i bad-apple.mp4 -vf "fps=30,scale=240:180,format=monob" frames/%06d.pbm
memes/tools/pack_frames.py --output memes/assets/bad-apple.bin --fps 30 frames/*.pbm
```

## Tests

```sh
python3 -m unittest discover -s memes -p 'test_*.py'
```
