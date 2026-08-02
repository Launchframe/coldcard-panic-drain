"""Localhost-only network contract enforcement."""

from __future__ import annotations

import ipaddress
import socket
from typing import Any

_PATCHED = False
_ORIGINAL_SOCKET = socket.socket
_ORIGINAL_CREATE_CONNECTION = socket.create_connection

_LOCALHOST_MSG = (
    "coldcard-panic-drain only connects to localhost (127.0.0.1 / ::1). "
    "Remote nodes are not supported — broadcast manually via Sparrow if needed."
)


class NetworkBlockedError(RuntimeError):
    """Raised when code attempts a non-localhost network connection."""


def _is_loopback_host(host: str) -> bool:
    if not host:
        return False
    h = host.strip().lower()
    if h in ("localhost", "127.0.0.1", "::1"):
        return True
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        return False


def _check_host(host: str) -> None:
    if not _is_loopback_host(host):
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
    if isinstance(address, tuple) and address:
        _check_host(str(address[0]))
    return _ORIGINAL_CREATE_CONNECTION(address, *args, **kwargs)


def enable_localhost_guard() -> None:
    """Allow sockets only to loopback addresses."""
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
