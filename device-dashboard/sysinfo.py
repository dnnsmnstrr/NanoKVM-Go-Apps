"""Read NanoKVM device status from /proc, /sys and a few system tools."""

from __future__ import annotations

import fcntl
import os
import re
import socket
import struct
import subprocess
import threading
import time
from pathlib import Path

SIOCGIFADDR = 0x8915
SKIP_INTERFACES = ("lo", "sit0")


def read(path, default=""):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").strip("\x00\n ")
    except OSError:
        return default


def run(args, timeout=3):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout + result.stderr


def interface_ipv4(name):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        packed = fcntl.ioctl(sock.fileno(), SIOCGIFADDR, struct.pack("256s", name[:15].encode()))
        return socket.inet_ntoa(packed[20:24])
    except OSError:
        return None
    finally:
        sock.close()


def parse_cpu_times(text):
    """Return (busy, total) jiffies from the aggregate `cpu` line of /proc/stat."""
    for line in text.splitlines():
        if line.startswith("cpu "):
            values = [int(value) for value in line.split()[1:]]
            idle = values[3] + (values[4] if len(values) > 4 else 0)
            total = sum(values[:8])
            return total - idle, total
    return 0, 0


def parse_meminfo(text):
    values = {}
    for line in text.splitlines():
        match = re.match(r"(\w+):\s+(\d+)", line)
        if match:
            values[match.group(1)] = int(match.group(2)) * 1024
    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", values.get("MemFree", 0))
    return total - available, total


def parse_iw_link(text):
    """Parse `iw dev wlan0 link` into a dict (empty when not connected)."""
    if "Connected to" not in text:
        return {}
    info = {}
    patterns = {
        "ssid": r"SSID:\s*(.+)",
        "freq": r"freq:\s*([\d.]+)",
        "signal": r"signal:\s*(-?\d+)",
        "tx_rate": r"tx bitrate:\s*([\d.]+)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if match:
            info[key] = match.group(1).strip()
    if "freq" in info:
        info["freq"] = float(info["freq"])
    if "signal" in info:
        info["signal"] = int(info["signal"])
    if "tx_rate" in info:
        info["tx_rate"] = float(info["tx_rate"])
    return info


def wifi_channel(freq):
    if freq is None:
        return None
    freq = int(freq)
    if 2412 <= freq <= 2472:
        return (freq - 2407) // 5
    if freq == 2484:
        return 14
    if 5000 <= freq <= 5900:
        return (freq - 5000) // 5
    if 5955 <= freq <= 7115:
        return (freq - 5950) // 5
    return None


def signal_bars(dbm):
    """0-4 bars from an RSSI in dBm."""
    if dbm is None:
        return 0
    for bars, threshold in ((4, -55), (3, -65), (2, -72), (1, -80)):
        if dbm >= threshold:
            return bars
    return 0


class SystemInfo:
    """Collects a snapshot in the background; read `snapshot` from the UI."""

    def __init__(self, fast_interval=2.0, slow_interval=10.0):
        self.fast_interval = fast_interval
        self.slow_interval = slow_interval
        self.lock = threading.Lock()
        self.snapshot = {}
        self.version = 0
        self.cpu_history = []
        self._last_cpu = None
        self._slow_at = 0.0
        self._slow = {}
        self._stop = threading.Event()

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.refresh()
            except Exception as exc:  # keep the UI alive if one source breaks
                print("Device: refresh failed:", exc)
            self._stop.wait(self.fast_interval)

    def refresh(self):
        data = {}
        data["hostname"] = socket.gethostname()
        data["model"] = read("/proc/device-tree/model") or "NanoKVM"
        uptime = read("/proc/uptime", "0").split()
        data["uptime"] = float(uptime[0]) if uptime else 0.0
        data["load"] = read("/proc/loadavg", "0 0 0").split()[:3]
        busy, total = parse_cpu_times(read("/proc/stat"))
        if self._last_cpu and total > self._last_cpu[1]:
            data["cpu"] = 100.0 * (busy - self._last_cpu[0]) / (total - self._last_cpu[1])
        else:
            data["cpu"] = None
        self._last_cpu = (busy, total)
        temp = read("/sys/class/thermal/thermal_zone0/temp")
        data["temp"] = int(temp) / 1000.0 if temp.lstrip("-").isdigit() else None
        data["mem"] = parse_meminfo(read("/proc/meminfo"))
        try:
            stat = os.statvfs("/")
            data["disk"] = ((stat.f_blocks - stat.f_bfree) * stat.f_frsize, stat.f_blocks * stat.f_frsize)
        except OSError:
            data["disk"] = (0, 0)
        interfaces = []
        for name in sorted(os.listdir("/sys/class/net")) if os.path.isdir("/sys/class/net") else []:
            if name in SKIP_INTERFACES:
                continue
            interfaces.append({
                "name": name,
                "ip": interface_ipv4(name),
                "state": read("/sys/class/net/%s/operstate" % name, "unknown"),
                "mac": read("/sys/class/net/%s/address" % name),
            })
        data["interfaces"] = interfaces
        udc_states = [read(path) for path in Path("/sys/class/udc").glob("*/state")] if Path("/sys/class/udc").is_dir() else []
        data["usb"] = udc_states[0] if udc_states else "unknown"
        data["hid"] = read("/tmp/kvm/hid_enable") == "1"

        now = time.monotonic()
        if now - self._slow_at >= self.slow_interval:
            self._slow_at = now
            wifi = next((item["name"] for item in interfaces if item["name"].startswith("wl")), None)
            self._slow = {
                "wifi": parse_iw_link(run(["iw", "dev", wifi, "link"])) if wifi else {},
                "wifi_iface": wifi,
                "tailscale": self._tailscale(interfaces),
            }
        data.update(self._slow)
        data["time"] = time.strftime("%H:%M")
        with self.lock:
            if data["cpu"] is not None:
                self.cpu_history.append(data["cpu"])
                del self.cpu_history[:-60]
            self.snapshot = data
            self.version += 1

    def _tailscale(self, interfaces):
        iface = next((item for item in interfaces if item["name"].startswith("tailscale")), None)
        if iface and iface["ip"]:
            return {"state": "UP", "ip": iface["ip"]}
        status = run(["tailscale", "status"], timeout=4)
        if not status and iface is None:
            return None
        if "NeedsLogin" in status or "Logged out" in status:
            return {"state": "NEEDS LOGIN", "ip": None}
        if "stopped" in status.lower():
            return {"state": "STOPPED", "ip": None}
        return {"state": "DOWN", "ip": None}


def primary_ip(snapshot):
    """The address people reach the web UI on: Wi-Fi or Ethernet first."""
    interfaces = snapshot.get("interfaces") or []
    for prefix in ("eth", "wl", "en"):
        for item in interfaces:
            if item["name"].startswith(prefix) and item["ip"]:
                return item["ip"]
    for item in interfaces:
        if item["ip"] and not item["name"].startswith(("usb", "tailscale")):
            return item["ip"]
    return None
