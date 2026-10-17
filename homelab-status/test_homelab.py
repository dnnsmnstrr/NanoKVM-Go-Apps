"""Off-device tests for the Dashy parser, mDNS decoding and the monitor."""

import socket
import sys
import time
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.modules.setdefault("appbase", types.SimpleNamespace(
    DOWN="down", UP="up", WHITE=0xFFFF, Rect=None, app=lambda: (lambda f: f),
    rgb565=lambda r, g, b: ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)))

import checks  # noqa: E402
import dashy  # noqa: E402
import main  # noqa: E402

DASHY_CONFIG = """\
appConfig:
  theme: default
  customCss: 'footer { display: none }'
  statusCheck: false
  webSearch:
    searchBangs: {}
  auth:
    users: []
  customColors:
    default:
      primary: '#5cabca'  # trailing comment
pageInfo:
  title: Home Lab
sections:
  - name: NAS
    items:
      - title: UGOS
        url: http://192.168.1.10:9999
        id: 0_226_ugos
      - title: Paperless NGX
        description: "Docs: scanned"
        url: http://192.168.1.10:8000/#/home
    icon: fas fa-hard-drive
    displayData:
      collapsed: false
  - name: Server
    items:
    - title: Portainer
      url: https://pi.local:9443/
      statusCheckAcceptCodes: '401, 403'
    - title: Quiet
      url: http://pi.local:1234/
      statusCheck: false
    - title: Probe
      url: http://pi.local:80/
      statusCheckUrl: http://pi.local:80/health
    widgets: []
  - name: Media
    items:
      - title: Plex
        icon: plex.png
  - name: Fun
    widgets:
      - title: XKCD
        type: xkcd-comic
pages:
  - name: Lab
    path: lab.yml
"""


class YamlTests(unittest.TestCase):
    def test_scalars(self):
        self.assertEqual(dashy.parse_scalar("'it''s'"), "it's")
        self.assertEqual(dashy.parse_scalar('"a: b"'), "a: b")
        self.assertIs(dashy.parse_scalar("false"), False)
        self.assertEqual(dashy.parse_scalar("42"), 42)
        self.assertEqual(dashy.parse_scalar("[a, 'b, c']"), ["a", "b, c"])
        self.assertEqual(dashy.parse_scalar("{}"), {})
        self.assertEqual(dashy.parse_scalar("http://x:80/"), "http://x:80/")

    def test_nested_document(self):
        config = dashy.parse_yaml(DASHY_CONFIG)
        self.assertEqual(config["appConfig"]["customCss"], "footer { display: none }")
        self.assertEqual(config["appConfig"]["customColors"]["default"]["primary"], "#5cabca")
        self.assertEqual(config["appConfig"]["auth"]["users"], [])
        self.assertEqual(config["sections"][0]["items"][1]["url"], "http://192.168.1.10:8000/#/home")
        self.assertEqual(config["sections"][0]["items"][1]["description"], "Docs: scanned")
        self.assertEqual(config["sections"][0]["displayData"], {"collapsed": False})

    def test_block_scalar(self):
        config = dashy.parse_yaml("a: |\n  one\n  two\nb: >\n  x\n  y\nc: 1\n")
        self.assertEqual(config, {"a": "one\ntwo", "b": "x y", "c": 1})

    def test_bad_indent_raises(self):
        with self.assertRaises(dashy.YamlError):
            dashy.parse_yaml("a: 1\n    b: 2\n")


class ExtractTests(unittest.TestCase):
    def test_sections_and_items(self):
        title, sections, pages = dashy.extract_services(dashy.parse_yaml(DASHY_CONFIG))
        self.assertEqual(title, "Home Lab")
        self.assertEqual(pages, ["lab.yml"])
        self.assertEqual([section["name"] for section in sections], ["NAS", "Server", "Media"])
        server = {item["title"]: item for item in sections[1]["items"]}
        self.assertEqual(server["Portainer"]["accept_codes"], frozenset([401, 403]))
        self.assertFalse(server["Quiet"]["enabled"])
        self.assertEqual(server["Probe"]["check_url"], "http://pi.local:80/health")
        plex = sections[2]["items"][0]
        self.assertFalse(plex["enabled"])
        self.assertEqual(plex["check_url"], "")


class CheckTests(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(checks.classify(200), checks.UP)
        self.assertEqual(checks.classify(302), checks.UP)
        self.assertEqual(checks.classify(401), checks.WARN)
        self.assertEqual(checks.classify(401, frozenset([401])), checks.UP)

    def test_describe_error(self):
        self.assertEqual(checks.describe_error(ConnectionRefusedError()), "REFUSED")
        self.assertEqual(checks.describe_error(socket.timeout("timed out")), "TIMEOUT")
        self.assertEqual(checks.describe_error(socket.gaierror(-3, "x")), "DNS FAIL")

    def test_monitor_records_results(self):
        results = {"http://a/": (checks.UP, 200, 12, "HTTP 200"),
                   "http://b/": (checks.DOWN, None, None, "REFUSED")}
        sections = [{"name": "S", "items": [
            {"title": "A", "url": "http://a/", "check_url": "http://a/", "enabled": True, "accept_codes": frozenset()},
            {"title": "B", "url": "http://b/", "check_url": "http://b/", "enabled": True, "accept_codes": frozenset()},
            {"title": "C", "url": "", "check_url": "", "enabled": False, "accept_codes": frozenset()},
        ]}]
        monitor = checks.Monitor(sections, interval=60, check=lambda url, *_: results[url])
        monitor.start()
        deadline = time.time() + 2
        while time.time() < deadline and monitor.summary()[checks.PENDING]:
            time.sleep(0.01)
        monitor.stop()
        self.assertEqual(monitor.summary(), {checks.UP: 1, checks.WARN: 0, checks.DOWN: 1, checks.OFF: 1, checks.PENDING: 0})
        state = monitor.sections[0]["states"][0]
        self.assertEqual((state.code, state.latency, state.history), (200, 12, [(checks.UP, 12)]))


class InlineServicesTests(unittest.TestCase):
    def sections(self, text):
        return dashy.extract_services(dashy.parse_inline_services(text))[1]

    def test_shorthand_json(self):
        sections = self.sections('{"Server": {"Gitea": "http://pi.local:8124"}, "NAS": [{"title": "UGOS", "url": "http://n:9999"}]}')
        self.assertEqual([(s["name"], [i["title"] for i in s["items"]]) for s in sections],
                         [("Server", ["Gitea"]), ("NAS", ["UGOS"])])
        self.assertEqual(sections[0]["items"][0]["check_url"], "http://pi.local:8124")

    def test_dashy_json_and_section_list(self):
        dashy_json = '{"pageInfo": {"title": "Lab"}, "sections": [{"name": "A", "items": [{"title": "X", "url": "http://x"}]}]}'
        self.assertEqual(dashy.extract_services(dashy.parse_inline_services(dashy_json))[0], "Lab")
        self.assertEqual(self.sections('[{"name": "A", "items": [{"title": "X", "url": "http://x"}]}]')[0]["name"], "A")

    def test_plain_text_list(self):
        sections = self.sections("Server: Gitea=http://pi.local:8124, http://pi.local:8090/; NAS: UGOS=http://n:9999")
        self.assertEqual([s["name"] for s in sections], ["Server", "NAS"])
        self.assertEqual([(i["title"], i["url"]) for i in sections[0]["items"]],
                         [("Gitea", "http://pi.local:8124"), ("pi.local:8090", "http://pi.local:8090/")])
        unnamed = self.sections("http://a.local/, B=https://b:9443")
        self.assertEqual(unnamed[0]["name"], "Services")
        self.assertEqual([i["title"] for i in unnamed[0]["items"]], ["a.local", "B"])

    def test_invalid_json_raises(self):
        with self.assertRaises(dashy.YamlError):
            dashy.parse_inline_services('{"Server": ')

    def test_load_config_prefers_env(self):
        title, sections, source = main.load_config({"HOMELAB_SERVICES": "Gitea=http://g", "DASHY_URL": "http://unused"})
        self.assertEqual((source, sections[0]["items"][0]["title"]), ("ENV", "Gitea"))
        with self.assertRaises(main.ConfigError) as caught:
            main.load_config({"HOMELAB_SERVICES": "{broken"})
        self.assertIn("HOMELAB-SERVICES", caught.exception.hint)


class UiHelperTests(unittest.TestCase):
    def test_text_only_uses_font_glyphs(self):
        self.assertEqual(main.text("my_app?x=1+2"), "MY-APP.X:1-2")

    def test_config_url(self):
        self.assertEqual(main.config_url("pi.local:4000"), "http://pi.local:4000/conf.yml")
        self.assertEqual(main.config_url("http://pi.local:4000/"), "http://pi.local:4000/conf.yml")
        self.assertEqual(main.config_url("http://x/y/my.yml"), "http://x/y/my.yml")

    def test_wrap_breaks_at_spaces(self):
        self.assertEqual(main.wrap("check homelab_services in app env", 216, 3), ["CHECK HOMELAB-SERVICES IN", "APP ENV"])
        self.assertEqual(main.wrap("http://raspberrypi.local:3001", 80, 3), ["HTTP://RAS", "PBERRYPI.L", "OCAL:3001"])

    def test_ago(self):
        self.assertEqual(main.ago(5), "5S")
        self.assertEqual(main.ago(3720), "1H 2M")


if __name__ == "__main__":
    unittest.main()
