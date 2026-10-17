"""Home Assistant REST client, entity configuration and per-domain behaviour."""

from __future__ import annotations

import http.client
import json
import ssl
import urllib.parse

# Domains a tap acts on, and the service it calls. Everything else is
# read-only and opens a detail view instead.
TOGGLE_DOMAINS = ("light", "switch", "fan", "input_boolean", "automation", "siren", "humidifier", "cover")
PRESS_SERVICES = {
    "scene": "turn_on",
    "script": "turn_on",
    "button": "press",
    "input_button": "press",
}
# Covers that open a building need a second tap, as does unlocking a lock.
CONFIRM_COVER_CLASSES = ("garage", "door", "gate")

AUTO_DOMAINS = [
    ("light", "Lights"),
    ("switch", "Switches"),
    ("fan", "Fans"),
    ("cover", "Covers"),
    ("climate", "Climate"),
    ("media_player", "Media"),
    ("scene", "Scenes"),
    ("script", "Scripts"),
    ("lock", "Locks"),
    ("input_boolean", "Toggles"),
]

BINARY_LABELS = {
    "door": ("OPEN", "CLOSED"), "garage_door": ("OPEN", "CLOSED"), "window": ("OPEN", "CLOSED"),
    "opening": ("OPEN", "CLOSED"), "motion": ("MOTION", "CLEAR"), "occupancy": ("OCCUPIED", "CLEAR"),
    "presence": ("HOME", "AWAY"), "moisture": ("WET", "DRY"), "smoke": ("SMOKE", "CLEAR"),
    "lock": ("UNLOCKED", "LOCKED"), "plug": ("PLUGGED", "UNPLUGGED"), "connectivity": ("ONLINE", "OFFLINE"),
    "battery": ("LOW", "OK"), "problem": ("PROBLEM", "OK"),
}
STATE_WORDS = {
    "on": "ON", "off": "OFF", "open": "OPEN", "closed": "CLOSED", "opening": "OPENING", "closing": "CLOSING",
    "locked": "LOCKED", "unlocked": "UNLOCKED", "locking": "LOCKING", "unlocking": "UNLOCKING", "jammed": "JAMMED",
    "playing": "PLAYING", "paused": "PAUSED", "idle": "IDLE", "standby": "STANDBY", "home": "HOME",
    "not_home": "AWAY", "unavailable": "N/A", "unknown": "-", "above_horizon": "UP", "below_horizon": "DOWN",
    "heat": "HEAT", "cool": "COOL", "heat_cool": "AUTO", "auto": "AUTO", "dry": "DRY", "fan_only": "FAN",
    "not_found": "NOT FOUND",
}


class HAError(RuntimeError):
    """A failure with a short, drawable message."""


class HAClient:
    """Small REST client that keeps one HTTP connection alive."""

    def __init__(self, base_url, token, timeout=6.0):
        base_url = base_url.strip().rstrip("/")
        if "://" not in base_url:
            base_url = "http://" + base_url
        parsed = urllib.parse.urlparse(base_url)
        self.https = parsed.scheme == "https"
        self.host = parsed.hostname or ""
        self.port = parsed.port or (443 if self.https else 80)
        self.prefix = parsed.path.rstrip("/")
        self.token = token.strip()
        self.timeout = timeout
        self._conn = None

    def _connection(self):
        if self._conn is None:
            if self.https:
                self._conn = http.client.HTTPSConnection(
                    self.host, self.port, timeout=self.timeout, context=ssl._create_unverified_context())
            else:
                self._conn = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        return self._conn

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def request(self, method, path, body=None):
        headers = {"Authorization": "Bearer " + self.token, "Accept": "application/json"}
        payload = None
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        # A kept-alive connection may have been closed by HA; retry once fresh.
        for attempt in range(2):
            try:
                conn = self._connection()
                conn.request(method, self.prefix + path, body=payload, headers=headers)
                response = conn.getresponse()
                data = response.read()
                break
            except (http.client.HTTPException, OSError) as exc:
                self.close()
                if attempt == 1 or isinstance(exc, (TimeoutError, ConnectionRefusedError)):
                    raise HAError(describe_error(exc)) from exc
        if response.status == 401:
            raise HAError("HA TOKEN REJECTED")
        if response.status == 404:
            return None
        if response.status >= 400:
            raise HAError("HA HTTP %d" % response.status)
        return json.loads(data.decode("utf-8")) if data else None

    def check(self):
        return self.request("GET", "/api/")

    def states(self):
        return self.request("GET", "/api/states") or []

    def state(self, entity_id):
        return self.request("GET", "/api/states/" + urllib.parse.quote(entity_id))

    def call(self, domain, service, entity_id):
        return self.request("POST", "/api/services/%s/%s" % (domain, service), {"entity_id": entity_id}) or []


def describe_error(exc):
    text = str(exc).lower()
    if isinstance(exc, (TimeoutError,)) or "timed out" in text:
        return "HA TIMEOUT"
    if isinstance(exc, ConnectionRefusedError):
        return "HA REFUSED"
    if "name resolution" in text or "nodename" in text or "not known" in text:
        return "HA NOT FOUND"
    if isinstance(exc, OSError) and getattr(exc, "errno", None) in (113, 65, 101, 51):
        return "HA UNREACHABLE"
    return "HA CONNECTION ERR"


# -- configuration ------------------------------------------------------------

def _entity(entry, label=None):
    entry = str(entry).strip()
    if "=" in entry and label is None:
        left, right = (part.strip() for part in entry.split("=", 1))
        # Accept both "light.sofa=Sofa" and "Sofa=light.sofa".
        if "." in left and " " not in left:
            entry, label = left, right
        else:
            entry, label = right, left
    if "." not in entry:
        raise ValueError("not an entity id: %s" % entry)
    return {"entity_id": entry, "label": label or None}


def parse_entities_config(text):
    """Parse HA_ENTITIES into [{"name": page, "entities": [...]}].

    Accepted forms (all single-line friendly):
      - text:  "Living: light.sofa=Sofa, switch.tv; Climate: sensor.temp"
      - JSON:  {"Living": {"Sofa": "light.sofa", "TV": "switch.tv"}}
      - JSON:  {"Living": ["light.sofa", "switch.tv"]}
      - JSON:  [{"name": "Living", "entities": ["light.sofa"]}]
    """
    text = (text or "").strip()
    if not text:
        return []
    pages = []
    if text.startswith(("{", "[")):
        data = json.loads(text)
        if isinstance(data, dict):
            data = [{"name": name, "entities": value} for name, value in data.items()]
        if not isinstance(data, list):
            raise ValueError("HA_ENTITIES must be a JSON object or list")
        for page in data:
            if not isinstance(page, dict):
                raise ValueError("each page must be an object")
            entries = page.get("entities") or []
            if isinstance(entries, dict):
                entities = [_entity(entity_id, label) for label, entity_id in entries.items()]
            else:
                entities = [_entity(item["entity_id"], item.get("label")) if isinstance(item, dict) else _entity(item)
                            for item in entries]
            pages.append({"name": str(page.get("name") or "Home"), "entities": entities})
    else:
        for chunk in text.replace("\n", ";").split(";"):
            chunk = chunk.strip()
            if not chunk:
                continue
            name = "Home"
            colon = chunk.find(":")
            if colon > 0 and "." not in chunk[:colon] and "=" not in chunk[:colon]:
                name, chunk = chunk[:colon].strip(), chunk[colon + 1:]
            entities = [_entity(part) for part in chunk.split(",") if part.strip()]
            pages.append({"name": name, "entities": entities})
    return [page for page in pages if page["entities"]]


def auto_pages(states, limit_per_domain=24):
    """Group controllable entities by domain when HA_ENTITIES is empty."""
    by_domain = {}
    for state in states:
        entity_id = state.get("entity_id", "")
        domain = entity_id.split(".", 1)[0]
        if state.get("state") == "unavailable":
            continue
        by_domain.setdefault(domain, []).append(state)
    pages = []
    for domain, title in AUTO_DOMAINS:
        entries = sorted(by_domain.get(domain, []), key=lambda s: friendly_name(s).lower())
        if entries:
            pages.append({"name": title, "entities": [
                {"entity_id": s["entity_id"], "label": None} for s in entries[:limit_per_domain]]})
    return pages


# -- per-entity presentation ----------------------------------------------------

def friendly_name(state):
    return (state.get("attributes") or {}).get("friendly_name") or state.get("entity_id", "?")


def domain_of(entity_id):
    return entity_id.split(".", 1)[0]


def format_number(value, unit=""):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value).upper()
    text = ("%d" % round(number)) if abs(number) >= 100 or number == int(number) else ("%.1f" % number)
    unit = (unit or "").replace("°", "").strip()
    return text + unit if unit in ("%", "C", "F") else (text + " " + unit if unit else text)


def state_text(state):
    """Short text for a tile: (primary, secondary)."""
    if state is None:
        return "MISSING", ""
    entity_id = state.get("entity_id", "")
    domain = domain_of(entity_id)
    value = str(state.get("state", ""))
    attrs = state.get("attributes") or {}
    if value in ("unavailable", "unknown", "not_found"):
        return STATE_WORDS[value], ""
    if domain == "sensor" or domain in ("input_number", "number"):
        return format_number(value, attrs.get("unit_of_measurement")), ""
    if domain == "binary_sensor":
        on, off = BINARY_LABELS.get(attrs.get("device_class"), ("ON", "OFF"))
        return (on if value == "on" else off), ""
    if domain == "light" and value == "on" and attrs.get("brightness") is not None:
        return "ON", "%d%%" % round(100 * attrs["brightness"] / 255)
    if domain == "cover" and attrs.get("current_position") is not None and value not in ("closed",):
        return STATE_WORDS.get(value, value.upper()), "%d%%" % attrs["current_position"]
    if domain == "climate":
        current = attrs.get("current_temperature")
        target = attrs.get("temperature")
        primary = format_number(current, "C") if current is not None else STATE_WORDS.get(value, value.upper())
        secondary = STATE_WORDS.get(value, value.upper())
        if target is not None and value != "off":
            secondary += " " + format_number(target, "C")
        return primary, secondary
    if domain == "weather":
        temp = attrs.get("temperature")
        unit = attrs.get("temperature_unit", "C")
        return (format_number(temp, unit) if temp is not None else ""), value.replace("_", " ").upper()
    if domain == "media_player" and value == "playing":
        return "PLAYING", str(attrs.get("media_title") or "")
    if domain in ("scene", "script", "button", "input_button"):
        return "", ""
    return STATE_WORDS.get(value, value.replace("_", " ").upper()), ""


def is_active(state):
    if state is None:
        return False
    value = state.get("state")
    return value in ("on", "open", "opening", "playing", "unlocked", "home", "heat", "cool", "heat_cool", "auto")


def action_for(state, entity_id):
    """Return (domain, service, needs_confirm) for a tap, or None for read-only."""
    domain = domain_of(entity_id)
    attrs = (state or {}).get("attributes") or {}
    value = (state or {}).get("state")
    if value in ("unavailable", "not_found"):
        return None
    if domain in PRESS_SERVICES:
        return domain, PRESS_SERVICES[domain], False
    if domain == "lock":
        if value == "locked":
            return "lock", "unlock", True
        return "lock", "lock", False
    if domain == "cover":
        return "cover", "toggle", attrs.get("device_class") in CONFIRM_COVER_CLASSES
    if domain in TOGGLE_DOMAINS:
        return domain, "toggle", False
    if domain == "media_player":
        return "media_player", "media_play_pause", False
    return None


def icon_name(entity_id, state):
    domain = domain_of(entity_id)
    attrs = (state or {}).get("attributes") or {}
    device_class = attrs.get("device_class")
    if domain == "sensor":
        unit = attrs.get("unit_of_measurement") or ""
        if device_class == "temperature" or "°" in unit:
            return "thermo"
        if device_class == "humidity":
            return "drop"
        if device_class in ("power", "energy", "current", "voltage") or unit in ("W", "kW", "kWh", "Wh", "A", "V"):
            return "bolt"
        if device_class == "battery":
            return "battery"
        return "gauge"
    if domain == "binary_sensor":
        if device_class in ("door", "garage_door", "window", "opening"):
            return "door"
        if device_class in ("motion", "occupancy", "presence"):
            return "person"
        return "dot"
    return {
        "light": "bulb", "switch": "plug", "input_boolean": "plug", "fan": "fan", "cover": "blind",
        "climate": "thermo", "media_player": "play", "scene": "spark", "script": "script",
        "button": "spark", "input_button": "spark", "lock": "lock", "person": "person",
        "device_tracker": "person", "weather": "sun", "sun": "sun", "automation": "script",
    }.get(domain, "dot")
