"""Zero-network contract enforcement."""

from __future__ import annotations

import socket
from typing import Any

_PATCHED = False
_ORIGINAL_SOCKET = socket.socket


class NetworkBlockedError(RuntimeError):
    """Raised when code attempts to open a network socket."""


def _blocked_socket(*args: Any, **kwargs: Any) -> socket.socket:
    raise NetworkBlockedError(
        "coldcard-panic-drain never opens network sockets. "
        "Sync wallets in Sparrow first; only Sparrow should communicate over the wire."
    )


def enable_network_guard() -> None:
    """Patch socket.socket to block all outbound network creation."""
    global _PATCHED
    if _PATCHED:
        return
    socket.socket = _blocked_socket  # type: ignore[assignment,misc]
    _PATCHED = True


def disable_network_guard() -> None:
    """Restore socket.socket (tests only)."""
    global _PATCHED
    socket.socket = _ORIGINAL_SOCKET  # type: ignore[assignment,misc]
    _PATCHED = False
