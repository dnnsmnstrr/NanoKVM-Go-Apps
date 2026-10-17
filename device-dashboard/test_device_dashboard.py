"""Off-device tests for the QR encoder and the system-info parsers."""

import hashlib
import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.modules.setdefault("appbase", types.SimpleNamespace(
    DOWN="down", UP="up", WHITE=0xFFFF, Rect=None, app=lambda: (lambda f: f),
    rgb565=lambda r, g, b: ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)))

import main  # noqa: E402
import qr  # noqa: E402
import sysinfo  # noqa: E402


def matrix_hash(matrix):
    bits = "".join("".join("1" if value else "0" for value in row) for row in matrix)
    return hashlib.sha256(bits.encode()).hexdigest()


class QrTests(unittest.TestCase):
    def test_golden_matrix(self):
        # Verified to decode with OpenCV's QR detector when it was recorded.
        matrix = qr.encode("https://192.168.178.83")
        self.assertEqual(len(matrix), 25)
        self.assertEqual(matrix_hash(matrix), "56c5a2acdacd2d2c816210ffbb6430304f4cbc4aa5d4fbc89f73616c951d1f86")

    def test_function_patterns(self):
        for text in ("A", "x" * 120, "y" * 200):
            matrix = qr.encode(text)
            size = len(matrix)
            for cx, cy in ((3, 3), (size - 4, 3), (3, size - 4)):
                self.assertTrue(matrix[cy][cx])
                self.assertFalse(matrix[cy - 2][cx])
                self.assertTrue(matrix[cy - 3][cx])
            self.assertEqual([matrix[6][x] for x in range(8, size - 8)],
                             [x % 2 == 0 for x in range(8, size - 8)])
            self.assertTrue(matrix[size - 8][8])

    def test_version_selection(self):
        self.assertEqual(qr._choose(1), (1, "M"))
        self.assertEqual(qr._choose(22), (2, "M"))
        self.assertEqual(qr._choose(213), (10, "M"))
        self.assertEqual(qr._choose(230), (9, "L"))
        with self.assertRaises(ValueError):
            qr.encode("x" * 300)

    def test_wifi_payload_escapes(self):
        self.assertEqual(qr.wifi_payload("Home;Net", "p:a,ss"), "WIFI:T:WPA;S:Home\\;Net;P:p\\:a\\,ss;;")
        self.assertEqual(qr.wifi_payload("Open", ""), "WIFI:T:nopass;S:Open;;")


class SysinfoTests(unittest.TestCase):
    def test_iw_link(self):
        text = ("Connected to 3c:37:12:00:00:00 (on wlan0)\n\tSSID: Home Net\n\tfreq: 5220.0\n"
                "\tsignal: -56 dBm\n\ttx bitrate: 229.4 MBit/s 40MHz HE-MCS 9\n")
        self.assertEqual(sysinfo.parse_iw_link(text),
                         {"ssid": "Home Net", "freq": 5220.0, "signal": -56, "tx_rate": 229.4})
        self.assertEqual(sysinfo.parse_iw_link("Not connected.\n"), {})

    def test_cpu_and_memory(self):
        self.assertEqual(sysinfo.parse_cpu_times("cpu  10 0 5 80 5 0 0 0 0 0\ncpu0 1 2 3 4\n"), (15, 100))
        meminfo = "MemTotal:  122140 kB\nMemFree: 6584 kB\nMemAvailable: 38444 kB\n"
        self.assertEqual(sysinfo.parse_meminfo(meminfo), ((122140 - 38444) * 1024, 122140 * 1024))

    def test_wifi_helpers(self):
        self.assertEqual(sysinfo.wifi_channel(2437), 6)
        self.assertEqual(sysinfo.wifi_channel(5220.0), 44)
        self.assertEqual([sysinfo.signal_bars(v) for v in (-50, -60, -70, -79, -90, None)], [4, 3, 2, 1, 0, 0])

    def test_primary_ip_prefers_wifi_over_usb(self):
        snapshot = {"interfaces": [
            {"name": "tailscale0", "ip": "100.1.2.3"},
            {"name": "usb0", "ip": "10.134.217.1"},
            {"name": "wlan0", "ip": "192.168.1.83"},
        ]}
        self.assertEqual(sysinfo.primary_ip(snapshot), "192.168.1.83")


class UiHelperTests(unittest.TestCase):
    def test_parse_links(self):
        self.assertEqual(main.parse_links("Dashy=http://pi.local:4000, https://x.org/a?b=c"),
                         [("Dashy", "http://pi.local:4000"), ("x.org", "https://x.org/a?b=c")])

    def test_text_and_sizes(self):
        self.assertEqual(main.text("wlan_0!"), "WLAN-0.")
        self.assertEqual(main.size(15443529728), "14G")
        self.assertEqual(main.size(125071360), "119M")
        self.assertEqual(main.duration(4760), "1H 19M")


if __name__ == "__main__":
    unittest.main()
