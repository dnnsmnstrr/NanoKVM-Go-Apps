# Generated from _lib/kvmkit/net.py by _utils/sync-kvmkit.py. Edit the master copy.
"""`.local` name lookup over mDNS.

The NanoKVM's libc cannot resolve mDNS names, so `install_mdns_fallback()`
wraps `socket.getaddrinfo` and queries the network directly when a `.local`
lookup fails. Every urllib/http.client request then works with `.local` URLs.
"""

from __future__ import annotations

import socket
import struct
import threading
import time

MDNS_GROUP = ("224.0.0.251", 5353)
MDNS_TTL_CAP = 300


# -- mDNS -------------------------------------------------------------------

def build_mdns_query(name, query_id=0):
    """Return an A-record query asking for a unicast reply (QU bit)."""
    labels = b"".join(bytes([len(part)]) + part.encode("ascii")
                      for part in name.rstrip(".").split("."))
    return (struct.pack(">HHHHHH", query_id, 0, 1, 0, 0, 0)
            + labels + b"\x00" + struct.pack(">HH", 1, 0x8001))


def _read_name(data, offset):
    """Decode a possibly compressed DNS name; return (name, next_offset)."""
    labels = []
    jumped = False
    next_offset = offset
    for _ in range(64):
        length = data[offset]
        if length & 0xC0 == 0xC0:
            pointer = ((length & 0x3F) << 8) | data[offset + 1]
            if not jumped:
                next_offset = offset + 2
            jumped = True
            offset = pointer
            continue
        if length == 0:
            if not jumped:
                next_offset = offset + 1
            return ".".join(labels), next_offset
        labels.append(data[offset + 1:offset + 1 + length].decode("ascii", "replace"))
        offset += 1 + length
    raise ValueError("DNS name loop")


def parse_mdns_answer(data, name):
    """Return (ipv4, ttl) for name from a DNS response, or None."""
    wanted = name.rstrip(".").lower()
    try:
        _, flags, qdcount, ancount, nscount, arcount = struct.unpack_from(">HHHHHH", data, 0)
        if not flags & 0x8000:
            return None
        offset = 12
        for _ in range(qdcount):
            _, offset = _read_name(data, offset)
            offset += 4
        for _ in range(ancount + nscount + arcount):
            record_name, offset = _read_name(data, offset)
            rtype, _, ttl, length = struct.unpack_from(">HHIH", data, offset)
            offset += 10
            rdata = data[offset:offset + length]
            offset += length
            if rtype == 1 and length == 4 and record_name.lower() == wanted:
                return socket.inet_ntoa(rdata), ttl
    except (IndexError, struct.error, ValueError):
        return None
    return None


_mdns_cache = {}
_mdns_lock = threading.Lock()


def mdns_resolve(name, timeout=1.5):
    """Resolve a `.local` name to an IPv4 address string, or None."""
    key = name.rstrip(".").lower()
    now = time.monotonic()
    with _mdns_lock:
        cached = _mdns_cache.get(key)
        if cached and cached[1] > now:
            return cached[0]
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
        query_id = int(now * 1000) & 0xFFFF
        deadline = now + timeout
        for attempt in range(2):
            sock.sendto(build_mdns_query(key, query_id), MDNS_GROUP)
            # Retry once halfway through, in case the first packet was lost.
            retry_at = min(deadline, time.monotonic() + timeout / 2) if attempt == 0 else deadline
            while True:
                remaining = retry_at - time.monotonic()
                if remaining <= 0:
                    break
                sock.settimeout(remaining)
                try:
                    data, _ = sock.recvfrom(4096)
                except socket.timeout:
                    break
                answer = parse_mdns_answer(data, key)
                if answer:
                    address, ttl = answer
                    ttl = max(10, min(ttl, MDNS_TTL_CAP))
                    with _mdns_lock:
                        _mdns_cache[key] = (address, time.monotonic() + ttl)
                    return address
    except OSError:
        return None
    finally:
        sock.close()
    return None


_original_getaddrinfo = socket.getaddrinfo


def _getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    try:
        return _original_getaddrinfo(host, port, family, type, proto, flags)
    except socket.gaierror:
        if isinstance(host, bytes):
            host = host.decode("ascii", "ignore")
        if isinstance(host, str) and host.rstrip(".").lower().endswith(".local"):
            address = mdns_resolve(host)
            if address:
                return _original_getaddrinfo(address, port, family, type, proto, flags)
        raise


def install_mdns_fallback():
    socket.getaddrinfo = _getaddrinfo
