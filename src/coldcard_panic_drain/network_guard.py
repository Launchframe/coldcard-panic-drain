"""Localhost-only network contract enforcement."""

from __future__ import annotations

import ipaddress
import socket
import threading
from typing import Any

_PATCHED = False
_ORIGINAL_SOCKET = socket.socket
_ORIGINAL_CREATE_CONNECTION = socket.create_connection

# RFC 6598 Carrier-Grade NAT / shared address space (not always in is_private).
_SHARED_ADDRESS_SPACE = ipaddress.ip_network("100.64.0.0/10")

# During create_connection("host.local", ...), DNS may resolve to a LAN/CGNAT IP
# that is then passed to socket.connect. Track the pending hostname so connect()
# can allow those resolved targets for the same thread.
_pending = threading.local()

_LOCALHOST_MSG = (
    "coldcard-panic-drain only connects to localhost or local *.local hosts. "
    "Remote nodes are not supported — broadcast manually via Sparrow if needed."
)


class NetworkBlockedError(RuntimeError):
    """Raised when code attempts a non-localhost network connection."""


def _strip_ipv6_zone(host: str) -> str:
    """Remove IPv6 zone ID (e.g. fe80::1%en0 → fe80::1) for ipaddress parsing."""
    if "%" not in host:
        return host
    # IPv6 literals may appear as fe80::1%eth0 (not bracketed in connect tuples).
    if host.count(":") >= 2:
        return host.split("%", 1)[0]
    return host


def _is_local_mdns_host(host: str) -> bool:
    h = host.strip().lower().rstrip(".")
    return h == "localhost" or h.endswith(".local")


def _is_allowed_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if ip.is_loopback or ip.is_private or ip.is_link_local:
        return True
    if isinstance(ip, ipaddress.IPv4Address) and ip in _SHARED_ADDRESS_SPACE:
        return True
    return False


def _is_allowed_host(host: str) -> bool:
    if not host:
        return False
    h = host.strip().lower()
    if h in ("127.0.0.1", "::1") or _is_local_mdns_host(h):
        return True
    # Resolved IP from an in-flight create_connection to a *.local host.
    pending = getattr(_pending, "hostname", None)
    if pending is not None and _is_local_mdns_host(pending):
        return True
    try:
        ip = ipaddress.ip_address(_strip_ipv6_zone(h))
        return _is_allowed_ip(ip)
    except ValueError:
        return False


def _check_host(host: str) -> None:
    if not _is_allowed_host(host):
        raise NetworkBlockedError(_LOCALHOST_MSG)


class _LocalhostSocket(_ORIGINAL_SOCKET):  # type: ignore[misc,valid-type]
    def connect(self, address: Any) -> None:
        if isinstance(address, tuple) and address:
            _check_host(str(address[0]))
        super().connect(address)

    def connect_ex(self, address: Any) -> int:
        if isinstance(address, tuple) and address:
            _check_host(str(address[0]))
        return super().connect_ex(address)


def _guarded_create_connection(address, *args, **kwargs):
    pending_set = False
    if isinstance(address, tuple) and address:
        host = str(address[0])
        _check_host(host)
        if _is_local_mdns_host(host):
            _pending.hostname = host
            pending_set = True
    try:
        return _ORIGINAL_CREATE_CONNECTION(address, *args, **kwargs)
    finally:
        if pending_set:
            _pending.hostname = None


def enable_localhost_guard() -> None:
    """Allow sockets only to localhost and local-network (*.local) targets."""
    global _PATCHED
    if _PATCHED:
        return
    socket.socket = _LocalhostSocket  # type: ignore[assignment,misc]
    socket.create_connection = _guarded_create_connection  # type: ignore[assignment]
    _PATCHED = True


def disable_localhost_guard() -> None:
    """Restore socket primitives (tests only)."""
    global _PATCHED
    socket.socket = _ORIGINAL_SOCKET  # type: ignore[assignment,misc]
    socket.create_connection = _ORIGINAL_CREATE_CONNECTION  # type: ignore[assignment]
    _PATCHED = False


# Backward-compatible aliases for tests migrating from zero-network guard.
enable_network_guard = enable_localhost_guard
disable_network_guard = disable_localhost_guard
