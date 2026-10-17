"""Off-device tests: discovery, the MEMES filter, MEM1 assets, the player and
a smoke test that draws every meme through a fake framebuffer."""

import dataclasses
import struct
import sys
import tempfile
import types
import unittest
import zlib
from pathlib import Path


@dataclasses.dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int

    @property
    def cx(self):
        return self.x + self.w // 2

    @property
    def cy(self):
        return self.y + self.h // 2


APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))
sys.modules.setdefault("appbase", types.SimpleNamespace(
    DOWN="down", UP="up", WHITE=0xFFFF, Rect=Rect, app=lambda: (lambda f: f),
    rgb565=lambda r, g, b: ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)))

import engine  # noqa: E402
import main  # noqa: E402

EXPECTED = ["bad-apple", "nyan-cat", "pbj-time", "party-parrot", "dvd-bounce", "keyboard-cat",
            "over-9000", "matrix-rain", "doge"]


class FakeFB:
    def __init__(self, rotate=90):
        self.rotate = rotate
        self.width, self.height = (240, 284) if rotate in (90, 270) else (284, 240)
        self.calls = 0

    def fill_rect(self, x, y, w, h, color):
        assert 0 <= color <= 0xFFFF
        self.calls += 1

    def draw_text(self, x, y, text, color, scale=1):
        self.calls += 1

    def clear(self, color=0):
        self.calls += 1


def fake_ctx(rotate=90, env=None):
    return types.SimpleNamespace(fb=FakeFB(rotate), env=env or {})


class DiscoveryTests(unittest.TestCase):
    def test_all_bundled_memes_are_found_in_order(self):
        self.assertEqual([clip.id for clip in engine.discover(APP_DIR)], EXPECTED)

    def test_every_meme_draws_in_every_rotation(self):
        for rotate in (90, 270, 0):
            ctx = fake_ctx(rotate)
            area = engine.visible_rect(ctx.fb)
            for clip in engine.discover(APP_DIR):
                with self.subTest(clip=clip.id, rotate=rotate):
                    clip.start(ctx, area)
                    try:
                        for step, t in enumerate((0.0, 0.4, 1.3, 3.0, 6.5)):
                            index = clip.index(t)
                            ctx.fb.clear(clip.background(index, t))
                            clip.draw(ctx.fb, t, index, step == 0)
                    finally:
                        clip.stop()
                    self.assertGreater(ctx.fb.calls, 0)


class SelectTests(unittest.TestCase):
    def setUp(self):
        self.clips = engine.discover(APP_DIR)

    def ids(self, spec):
        return [clip.id for clip in engine.select(self.clips, spec)]

    def test_empty_plays_everything(self):
        self.assertEqual(self.ids(""), EXPECTED)

    def test_order_and_exclusion(self):
        self.assertEqual(self.ids("doge nyan-cat dvd-bounce"), ["doge", "nyan-cat", "dvd-bounce"])
        self.assertEqual(self.ids("-bad-apple -matrix-rain"), [i for i in EXPECTED if i not in ("bad-apple", "matrix-rain")])

    def test_titles_underscores_and_unknown_names(self):
        self.assertEqual(self.ids("Nyan Cat, Peanut Butter Jelly Time, nope"), ["nyan-cat", "pbj-time"])
        self.assertEqual(self.ids("party_parrot"), ["party-parrot"])
        self.assertEqual(self.ids("nope"), EXPECTED)


def mem1(width, height, durations, palette, pixels, transparent=255, title=b"Tiny"):
    return (engine.MEM_HEADER.pack(b"MEM1", width, height, len(durations), len(palette), transparent, len(title))
            + title + struct.pack("<%dH" % len(durations), *durations)
            + struct.pack("<%dH" % len(palette), *palette) + zlib.compress(bytes(pixels)))


class PackedAssetTests(unittest.TestCase):
    def test_round_trip_and_discovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "clips").mkdir()
            (root / "assets").mkdir()
            # 2x2, two frames: a red pixel, then the transparent index everywhere.
            blob = mem1(2, 2, [100, 300], [0xF800, 0x0000], [0, 1, 1, 1, 2, 2, 2, 2], transparent=2)
            (root / "assets" / "tiny-gif.mem").write_bytes(blob)
            clips = engine.discover(root)
            self.assertEqual([(c.id, c.title) for c in clips], [("tiny-gif", "Tiny")])
            clip = clips[0]
            ctx = fake_ctx()
            clip.start(ctx, engine.visible_rect(ctx.fb))
            self.assertEqual([clip.index(t) for t in (0.0, 0.09, 0.15, 0.39, 0.45)], [0, 0, 1, 1, 0])
            self.assertEqual(len(clip.sprite_runs(1)), 0)  # fully transparent frame
            self.assertEqual(len(clip.sprite_runs(0)) // 5, 3)  # red, then two black runs

    def test_rejects_other_files(self):
        with tempfile.NamedTemporaryFile(suffix=".mem") as handle:
            handle.write(b"GIF89a" + bytes(20))
            handle.flush()
            with self.assertRaises(ValueError):
                engine.load_packed(handle.name)


class Broken(engine.Clip):
    id = "broken"
    title = "Broken"

    def start(self, ctx, area):
        raise RuntimeError("no asset")


class PlayerTests(unittest.TestCase):
    def player(self, clips, **kwargs):
        return main.Player(fake_ctx(), clips, **kwargs)

    def test_tap_and_swipes_cycle(self):
        clips = [c for c in engine.discover(APP_DIR) if c.id in ("nyan-cat", "doge", "dvd-bounce")]
        player = self.player(clips)
        self.assertEqual(player.clip.id, "nyan-cat")
        player.on_tap(10, 10)
        self.assertEqual(player.clip.id, "dvd-bounce")
        player.on_swipe("down", 0, 0)
        self.assertEqual(player.clip.id, "nyan-cat")
        player.on_swipe("down", 0, 0)
        self.assertEqual(player.clip.id, "doge")
        player.tick(0)

    def test_broken_clip_is_skipped(self):
        doge = [c for c in engine.discover(APP_DIR) if c.id == "doge"]
        player = self.player([Broken()] + doge)
        self.assertEqual(player.clip.id, "doge")

    def test_autoplay_and_title_expiry(self):
        clips = [c for c in engine.discover(APP_DIR) if c.id in ("nyan-cat", "doge")]
        player = self.player(clips, autoplay=5)
        player.tick(0)
        self.assertGreater(player.title_until, 0)
        player.title_until = 1.0  # long expired
        player.tick(0)
        self.assertEqual(player.title_until, 0.0)
        player.started -= 6
        player.tick(0)
        self.assertEqual(player.clip.id, "doge")

    def test_env_helpers(self):
        self.assertTrue(main.enabled("", True))
        self.assertFalse(main.enabled("off", True))
        self.assertTrue(main.enabled("on", False))
        self.assertEqual(main.seconds("12"), 12.0)
        self.assertEqual(main.seconds("x"), 0.0)


class TextTests(unittest.TestCase):
    def test_extra_glyphs_are_drawn(self):
        fb = FakeFB()
        engine.draw_text(fb, 0, 0, "IT'S 9000!", 0xFFFF, 2)
        # Two SDK text segments plus pixel runs for the apostrophe and "!".
        self.assertGreater(fb.calls, 4)


if __name__ == "__main__":
    unittest.main()
