"""Off-device tests for entity config parsing and per-domain behaviour."""

import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.modules.setdefault("appbase", types.SimpleNamespace(
    DOWN="down", UP="up", WHITE=0xFFFF, Rect=None, app=lambda: (lambda f: f),
    rgb565=lambda r, g, b: ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)))

import hass  # noqa: E402
import main  # noqa: E402


def state(entity_id, value, **attributes):
    return {"entity_id": entity_id, "state": value, "attributes": attributes}


class ConfigTests(unittest.TestCase):
    def test_text_pages_and_labels(self):
        pages = hass.parse_entities_config("Living: light.sofa=Sofa, Lamp=light.lamp, switch.tv; Climate: sensor.temp")
        self.assertEqual([page["name"] for page in pages], ["Living", "Climate"])
        self.assertEqual(pages[0]["entities"], [
            {"entity_id": "light.sofa", "label": "Sofa"},
            {"entity_id": "light.lamp", "label": "Lamp"},
            {"entity_id": "switch.tv", "label": None},
        ])

    def test_unnamed_page(self):
        self.assertEqual(hass.parse_entities_config("light.a, light.b")[0]["name"], "Home")

    def test_json_forms(self):
        by_map = hass.parse_entities_config('{"Living": {"Sofa": "light.sofa"}}')
        by_list = hass.parse_entities_config('{"Living": ["light.sofa"]}')
        pages = hass.parse_entities_config('[{"name": "Living", "entities": [{"entity_id": "light.sofa", "label": "Sofa"}]}]')
        self.assertEqual(by_map, pages)
        self.assertEqual(by_list[0]["entities"], [{"entity_id": "light.sofa", "label": None}])

    def test_invalid_entries(self):
        with self.assertRaises(ValueError):
            hass.parse_entities_config("Living: sofa")
        with self.assertRaises(ValueError):
            hass.parse_entities_config('{"Living": ')

    def test_auto_pages_skip_unavailable_and_sort(self):
        pages = hass.auto_pages([
            state("light.b", "on", friendly_name="Beta"),
            state("light.a", "off", friendly_name="Alpha"),
            state("light.c", "unavailable"),
            state("sensor.t", "21"),
            state("scene.movie", "x"),
        ])
        self.assertEqual([(p["name"], [e["entity_id"] for e in p["entities"]]) for p in pages],
                         [("Lights", ["light.a", "light.b"]), ("Scenes", ["scene.movie"])])

    def test_paginate(self):
        pages = main.paginate([{"name": "All", "entities": list(range(8))}], 6)
        self.assertEqual([(p["name"], len(p["entities"])) for p in pages], [("All 1", 6), ("All 2", 2)])


class PresentationTests(unittest.TestCase):
    def test_state_text(self):
        self.assertEqual(hass.state_text(state("sensor.t", "21.44", unit_of_measurement="°C")), ("21.4C", ""))
        self.assertEqual(hass.state_text(state("sensor.p", "1234.56", unit_of_measurement="W")), ("1235 W", ""))
        self.assertEqual(hass.state_text(state("light.a", "on", brightness=128)), ("ON", "50%"))
        self.assertEqual(hass.state_text(state("binary_sensor.w", "on", device_class="window")), ("OPEN", ""))
        self.assertEqual(hass.state_text(state("climate.x", "heat", current_temperature=20.5, temperature=22)),
                         ("20.5C", "HEAT 22C"))
        self.assertEqual(hass.state_text(state("person.d", "not_home")), ("AWAY", ""))
        self.assertEqual(hass.state_text(state("light.x", "unavailable")), ("N/A", ""))

    def test_actions(self):
        self.assertEqual(hass.action_for(state("light.a", "off"), "light.a"), ("light", "toggle", False))
        self.assertEqual(hass.action_for(state("scene.s", "x"), "scene.s"), ("scene", "turn_on", False))
        self.assertEqual(hass.action_for(state("lock.d", "locked"), "lock.d"), ("lock", "unlock", True))
        self.assertEqual(hass.action_for(state("lock.d", "unlocked"), "lock.d"), ("lock", "lock", False))
        self.assertEqual(hass.action_for(state("cover.g", "closed", device_class="garage"), "cover.g"),
                         ("cover", "toggle", True))
        self.assertEqual(hass.action_for(state("cover.b", "open", device_class="blind"), "cover.b"),
                         ("cover", "toggle", False))
        self.assertIsNone(hass.action_for(state("sensor.t", "21"), "sensor.t"))
        self.assertIsNone(hass.action_for(state("light.a", "unavailable"), "light.a"))

    def test_text_transliterates_german(self):
        self.assertEqual(main.text("Küche & Büro (Straße)"), "KUECHE . BUERO  STRASSE ")


class ClientTests(unittest.TestCase):
    def test_url_parsing(self):
        client = hass.HAClient("homeassistant.local:8123/", "t")
        self.assertEqual((client.https, client.host, client.port, client.prefix), (False, "homeassistant.local", 8123, ""))
        client = hass.HAClient("https://ha.example.com/sub", "t")
        self.assertEqual((client.https, client.port, client.prefix), (True, 443, "/sub"))


if __name__ == "__main__":
    unittest.main()
