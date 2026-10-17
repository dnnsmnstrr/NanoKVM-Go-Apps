"""Service reachability checks.

`.local` hosts resolve through kvmkit.net's mDNS fallback, which main()
installs, so Dashy URLs such as `http://raspberrypi.local:3001` work.
"""

from __future__ import annotations

import concurrent.futures
import http.client
import socket
import ssl
import threading
import time
import urllib.error
import urllib.request

HISTORY = 40

UP = "up"
WARN = "warn"
DOWN = "down"
OFF = "off"
PENDING = "pending"


# -- HTTP checks --------------------------------------------------------------

_SSL_CONTEXT = ssl._create_unverified_context()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _opener(follow_redirects):
    handlers = [urllib.request.HTTPSHandler(context=_SSL_CONTEXT)]
    if not follow_redirects:
        handlers.append(_NoRedirect())
    return urllib.request.build_opener(*handlers)


_OPENERS = {True: _opener(True), False: _opener(False)}


def describe_error(exc):
    """Map an exception to a short message the ASCII font can draw."""
    reason = getattr(exc, "reason", exc)
    if isinstance(reason, (socket.timeout, TimeoutError)) or "timed out" in str(reason):
        return "TIMEOUT"
    if isinstance(reason, ConnectionRefusedError):
        return "REFUSED"
    if isinstance(reason, ConnectionResetError):
        return "CONN RESET"
    if isinstance(reason, socket.gaierror):
        return "DNS FAIL"
    if isinstance(reason, ssl.SSLError):
        return "TLS ERROR"
    if isinstance(reason, OSError) and reason.errno in (113, 65):
        return "NO ROUTE"
    if isinstance(reason, OSError) and reason.errno in (101, 51):
        return "NET DOWN"
    if isinstance(exc, (http.client.HTTPException,)):
        return "BAD REPLY"
    text = str(reason).upper()
    return text[:24] if text else exc.__class__.__name__.upper()


def classify(code, accept_codes=frozenset()):
    """Dashy treats 2xx as up; we also accept 3xx and any listed codes."""
    if code in accept_codes or 200 <= code < 400:
        return UP
    return WARN


def check_url(url, timeout=6.0, accept_codes=frozenset(), follow_redirects=True):
    """Return (status, code, latency_ms, message) for one GET request."""
    request = urllib.request.Request(url, headers={
        "User-Agent": "NanoKVM-Homelab/1.0",
        "Accept": "*/*",
    })
    started = time.monotonic()
    try:
        response = _OPENERS[bool(follow_redirects)].open(request, timeout=timeout)
        code = response.status
        response.close()
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
    except Exception as exc:  # urllib raises many unrelated types
        return DOWN, None, None, describe_error(exc)
    latency = int((time.monotonic() - started) * 1000)
    status = classify(code, accept_codes)
    return status, code, latency, "HTTP %d" % code


class ServiceState:
    def __init__(self, service):
        self.service = service
        self.status = PENDING if service["enabled"] else OFF
        self.code = None
        self.latency = None
        self.message = "WAITING" if service["enabled"] else ("NO URL" if not service["check_url"] else "CHECK OFF")
        self.checked_at = None
        self.changed_at = None
        self.history = []
        self.busy = False


class Monitor:
    """Checks every service on an interval in a small background pool."""

    def __init__(self, sections, interval=60.0, timeout=6.0, workers=4, check=check_url):
        self.sections = [
            {"name": section["name"], "states": [ServiceState(item) for item in section["items"]]}
            for section in sections
        ]
        self.interval = max(5.0, float(interval))
        self.timeout = float(timeout)
        self.check = check
        # Reentrant so the UI can hold it for a whole frame and still call summary().
        self.lock = threading.RLock()
        self.version = 0
        self.last_round = None
        self._pool = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = None

    def states(self):
        for section in self.sections:
            yield from section["states"]

    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._wake.set()
        self._pool.shutdown(wait=False)

    def check_now(self, state=None):
        if state is None:
            self._wake.set()
        else:
            self._submit(state)

    def _loop(self):
        while not self._stop.is_set():
            self.last_round = time.monotonic()
            for state in list(self.states()):
                self._submit(state)
            self._wake.wait(self.interval)
            self._wake.clear()

    def _submit(self, state):
        service = state.service
        if not service["enabled"]:
            return
        with self.lock:
            if state.busy:
                return
            state.busy = True
            self.version += 1
        try:
            self._pool.submit(self._run, state)
        except RuntimeError:  # pool shut down while exiting
            state.busy = False

    def _run(self, state):
        service = state.service
        try:
            status, code, latency, message = self.check(
                service["check_url"], self.timeout, service["accept_codes"],
                service.get("max_redirects") != 0)
        except Exception as exc:
            status, code, latency, message = DOWN, None, None, describe_error(exc)
        now = time.time()
        with self.lock:
            if status != state.status:
                state.changed_at = now
            state.status = status
            state.code = code
            state.latency = latency
            state.message = message
            state.checked_at = now
            state.history.append((status, latency))
            del state.history[:-HISTORY]
            state.busy = False
            self.version += 1

    def summary(self):
        counts = {UP: 0, WARN: 0, DOWN: 0, OFF: 0, PENDING: 0}
        with self.lock:
            for state in self.states():
                counts[state.status] += 1
        return counts
