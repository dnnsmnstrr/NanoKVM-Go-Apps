"""Off-device tests for Macro Pad's button configuration loading."""

import json
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.modules.setdefault("appbase", types.SimpleNamespace(
    DOWN="down", UP="up", WHITE=0xFFFF, Rect=None, app=lambda: (lambda f: f),
    rgb565=lambda r, g, b: ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)))

import main  # noqa: E402

CUSTOM = {
    "title": "MY PAD",
    "modifier": "ControlLeft",
    "pages": [{"name": "One", "buttons": [{"label": "Copy", "keys": ["@MOD", "KeyC"]}]}],
}


class ConfigTests(unittest.TestCase):
    def test_bundled_buttons_are_valid(self):
        title, modifier, pages, notice = main.load_buttons({})
        self.assertTrue(title and pages)
        self.assertEqual(notice, "")

    def test_inline_json_config(self):
        title, modifier, pages, notice = main.load_buttons({"MACRO_PAD_CONFIG": json.dumps(CUSTOM)})
        self.assertEqual((title, modifier, notice), ("MY PAD", "ControlLeft", ""))
        self.assertEqual(pages[0]["buttons"][0]["label"], "Copy")

    def test_invalid_config_falls_back_with_notice(self):
        bundled = main.load_buttons({})
        title, _, pages, notice = main.load_buttons({"MACRO_PAD_CONFIG": '{"pages": ['})
        self.assertEqual((title, pages), (bundled[0], bundled[2]))
        self.assertTrue(notice.startswith("CONFIG JSON ERR"))
        _, _, _, notice = main.load_buttons({"MACRO_PAD_CONFIG": '{"pages": [{"buttons": []}]}'})
        self.assertEqual(notice, "CONFIG INVALID")

    def test_modifier_override(self):
        env = {"MACRO_PAD_CONFIG": json.dumps(CUSTOM), "MACRO_PAD_MODIFIER": "mac"}
        self.assertEqual(main.load_buttons(env)[1], "MetaLeft")
        env["MACRO_PAD_MODIFIER"] = "unknown"
        self.assertEqual(main.load_buttons(env)[1], "ControlLeft")

    def test_url_config_uses_cache_when_offline(self):
        with mock.patch.object(main, "CONFIG_CACHE_PATH", Path(self.id() + ".missing")), \
                mock.patch.object(main.urllib.request, "urlopen", side_effect=OSError("down")):
            _, _, _, notice = main.load_buttons({"MACRO_PAD_CONFIG": "http://example.invalid/pad.json"})
        self.assertEqual(notice, "CONFIG URL ERR")


if __name__ == "__main__":
    unittest.main()
