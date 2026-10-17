"""Tests for the shared kvmkit library, and that every App's copy is current."""

import dataclasses
import socket
import struct
import subprocess
import sys
import types
import unittest
from pathlib import Path


@dataclasses.dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int

    def contains(self, px, py):
        return self.x <= px < self.x + self.w and self.y <= py < self.y + self.h

    @property
    def cx(self):
        return self.x + self.w // 2

    @property
    def cy(self):
        return self.y + self.h // 2


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "_lib"))
sys.modules.setdefault("appbase", types.SimpleNamespace(UP="up", DOWN="down", Rect=Rect))

from kvmkit import env, net, screen, text  # noqa: E402
from kvmkit.pager import Pager  # noqa: E402


class FakeFB:
    """Defaults to the NanoKVM Go: 240x284 physical, 284x240 at rotation 90."""

    def __init__(self, width=284, height=240, rotate=90, phys=(240, 284)):
        self.width, self.height, self.rotate = width, height, rotate
        self.phys_w, self.phys_h = phys
        self.texts = []
        self.rects = []

    def draw_text(self, x, y, value, color, scale=1):
        self.texts.append((x, y, value, scale))

    def text_center(self, cx, y, value, color, scale=1):
        self.draw_text(cx - len(value) * 4 * scale, y, value, color, scale)

    def fill_rect(self, x, y, w, h, color):
        self.rects.append((x, y, w, h))

    def draw_line(self, *args):
        pass


class ScreenTests(unittest.TestCase):
    def test_corner_inset(self):
        self.assertEqual(screen.corner_inset(0, 22), 22)
        self.assertEqual(screen.corner_inset(8, 22), 6)
        self.assertEqual(screen.corner_inset(22, 22), 0)
        self.assertEqual(screen.corner_inset(5, 0), 0)

    def test_nanokvm_go_shows_the_whole_canvas(self):
        self.assertEqual(screen.visible_rect(FakeFB(284, 240, 90)), Rect(0, 0, 284, 240))
        self.assertEqual(screen.visible_rect(FakeFB(284, 240, 270)), Rect(0, 0, 284, 240))

    def test_sdk_documented_panel_hides_a_strip(self):
        documented = (284, 240)
        self.assertEqual(screen.visible_rect(FakeFB(240, 284, 90, documented)), Rect(0, 0, 240, 270))
        self.assertEqual(screen.visible_rect(FakeFB(240, 284, 270, documented)), Rect(0, 14, 240, 270))
        self.assertEqual(screen.visible_rect(FakeFB(284, 240, 0, documented)), Rect(14, 0, 270, 240))

    def test_safe_span_clears_corners(self):
        layout = screen.Layout(FakeFB(), radius=22)
        self.assertEqual(layout.safe_span(8, 24, margin=0), (6, 284 - 6))
        self.assertEqual(layout.safe_span(100, 120, margin=0), (0, 284))
        bottom = layout.view.y + layout.view.h
        self.assertEqual(layout.safe_span(bottom - 2, bottom, margin=0)[0], 22)
        self.assertEqual(layout.safe_span(bottom - 10, bottom - 2, margin=0)[0], 13)


class PagerTests(unittest.TestCase):
    def test_paging_and_footer_taps(self):
        layout = screen.Layout(FakeFB())
        pager = Pager(layout, count=3)
        self.assertTrue(pager.on_swipe("up"))
        self.assertEqual(pager.index, 1)
        self.assertFalse(pager.on_swipe("left"))
        previous, middle, following = pager.zones()
        self.assertEqual(pager.on_tap(following.cx, following.cy), "next")
        self.assertEqual(pager.index, 2)
        self.assertEqual(pager.on_tap(following.cx, following.cy), "next")
        self.assertEqual(pager.index, 0)  # wraps
        self.assertEqual(pager.on_tap(previous.cx, previous.cy), "prev")
        self.assertEqual(pager.on_tap(middle.cx, middle.cy), "middle")
        self.assertIsNone(pager.on_tap(10, 10))
        pager.set_count(1)
        self.assertEqual(pager.index, 0)

    def test_header_text_stays_inside_the_corners(self):
        fb = FakeFB()
        layout = screen.Layout(fb, radius=22)
        Pager(layout).draw_header(fb, "A very long page title for the header", right="23:40", dot=1)
        for x, y, value, scale in fb.texts:
            left, right = layout.safe_span(y, y + 8 * scale, margin=0)
            self.assertGreaterEqual(x, left, value)
            self.assertLessEqual(x + len(value) * 8 * scale, right, value)


class TextTests(unittest.TestCase):
    def test_text_fit_wrap_ago(self):
        self.assertEqual(text.text("Küche_1!"), "KUECHE-1.")
        self.assertEqual(text.fit("abcdef", 32), "ABCD")
        self.assertEqual(text.wrap("one two three", 64, 2), ["ONE TWO", "THREE"])
        self.assertEqual(text.ago(3725), "1H 2M")
        self.assertEqual(text.ago(None), "-")

    def test_extra_glyphs(self):
        fb = FakeFB()
        text.draw_text(fb, 0, 0, "IT'S!", 0xFFFF, 1)
        self.assertEqual([value for _, _, value, _ in fb.texts], ["IT", "S"])
        self.assertTrue(fb.rects)


class EnvTests(unittest.TestCase):
    def test_sections(self):
        self.assertEqual(env.sections("Server: a=http://x, b; NAS: c", "Default"),
                         [("Server", ["a=http://x", "b"]), ("NAS", ["c"])])
        self.assertEqual(env.sections("http://x.local/, light.a=Sofa"), [(None, ["http://x.local/", "light.a=Sofa"])])
        self.assertEqual(env.pair("Sofa=light.sofa"), ("Sofa", "light.sofa"))
        self.assertEqual(env.pair("light.sofa"), ("light.sofa", None))

    def test_number_and_flag(self):
        self.assertEqual(env.number({"A": "7"}, "A", 5), 7.0)
        self.assertEqual(env.number({"A": "x"}, "A", 5), 5.0)
        self.assertEqual(env.number({"A": "0"}, "A", 5, minimum=1), 1.0)
        self.assertTrue(env.flag({}, "B", True))
        self.assertFalse(env.flag({"B": "off"}, "B", True))


def dns_name(name):
    return b"".join(bytes([len(part)]) + part.encode() for part in name.split(".")) + b"\x00"


class NetTests(unittest.TestCase):
    def test_query_sets_unicast_bit(self):
        packet = net.build_mdns_query("pi.local", 7)
        self.assertEqual(struct.unpack(">HHHHHH", packet[:12]), (7, 0, 1, 0, 0, 0))
        self.assertTrue(packet.endswith(dns_name("pi.local") + struct.pack(">HH", 1, 0x8001)))

    def test_parse_compressed_answer(self):
        header = struct.pack(">HHHHHH", 0, 0x8400, 1, 2, 0, 0)
        question = dns_name("pi.local") + struct.pack(">HH", 1, 1)
        aaaa = b"\xc0\x0c" + struct.pack(">HHIH", 28, 0x8001, 120, 16) + bytes(16)
        a_record = b"\xc0\x0c" + struct.pack(">HHIH", 1, 0x8001, 120, 4) + socket.inet_aton("192.168.1.74")
        self.assertEqual(net.parse_mdns_answer(header + question + aaaa + a_record, "PI.local."), ("192.168.1.74", 120))

    def test_parse_rejects_queries_and_garbage(self):
        self.assertIsNone(net.parse_mdns_answer(net.build_mdns_query("pi.local"), "pi.local"))
        self.assertIsNone(net.parse_mdns_answer(b"\x00\x00\x84\x00\x00\x01", "pi.local"))


class CopiesTests(unittest.TestCase):
    def test_every_app_copy_is_current(self):
        result = subprocess.run([sys.executable, str(ROOT / "_utils" / "sync-kvmkit.py"), "--check"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
